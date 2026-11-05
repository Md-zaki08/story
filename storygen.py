#!/usr/bin/env python3
"""StoryGen 1.2 CLI — a fully automated, self-escalating story maker."""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from story import __version__, io_utils  # noqa: E402


# ---------------------------------------------------------------------------
# v1 commands (preserved)
# ---------------------------------------------------------------------------

def cmd_corpus_check(args) -> None:
    manifest = io_utils.load_json(ROOT / "corpus" / "manifest.json", {}) or {}
    if not manifest:
        raise SystemExit("corpus/manifest.json missing or empty")
    counts = {"A": 0, "B": 0}
    kinds = {"fetched": 0, "synthesized": 0}
    problems = []
    for sid, meta in sorted(manifest.items()):
        path = ROOT / "corpus" / f"{sid}.md"
        diet = str(meta.get("diet", "?"))
        kind = str(meta.get("kind", "?"))
        counts[diet] = counts.get(diet, 0) + 1
        kinds[kind] = kinds.get(kind, 0) + 1
        if not path.exists():
            problems.append(f"{sid}: missing file {path.name}")
            continue
        _, body = io_utils.read_source(path)
        wc = io_utils.word_count(body)
        if wc < 150:
            problems.append(f"{sid}: only {wc} words")
    print("diet counts:", json.dumps(counts))
    print("kind counts:", json.dumps(kinds))
    print(f"sources: {len(manifest)}")
    if problems:
        print("problems:")
        for p in problems:
            print("  -", p)
    else:
        print("all source files present")


def cmd_atomize_init(args) -> None:
    manifest = io_utils.load_json(ROOT / "corpus" / "manifest.json", {}) or {}
    missing = []
    for sid in sorted(manifest):
        path = ROOT / "atoms" / f"{sid}.json"
        if not path.exists():
            missing.append(sid)
            continue
        doc = io_utils.load_json(path, {}) or {}
        atoms = doc.get("atoms", [])
        meta = manifest.get(sid, {})
        minimum = 6 if str(meta.get("medium")) == "live-research" else 12
        if len(atoms) < minimum:
            missing.append(f"{sid} (only {len(atoms)} atoms, need {minimum})")
    if missing:
        print(f"{len(missing)} source(s) need atoms:")
        for sid in missing:
            print(" ", sid)
    else:
        print("all sources atomized")


def cmd_cluster(args) -> None:
    from story import cluster_atoms

    cluster_atoms.run(
        seed=args.seed,
        apply_names_only=args.apply_names,
        force_embed=args.reembed,
        auto_name=args.auto_name,
    )


def cmd_name_clusters(args) -> None:
    from story import cluster_atoms

    cluster_atoms.name_clusters(limit=args.limit)


def cmd_sample(args) -> None:
    from story import sample

    betas = tuple(float(b) for b in args.betas.split(",")) if args.betas else (0.5, 0.7, 0.85)
    if args.beta is not None:
        betas = (float(args.beta),)
    sample.run(
        seed=args.seed,
        k=args.k,
        betas=betas,
        top_k=args.top_k,
        n_draws=args.n_draws,
        output_dir=args.output_dir,
    )


def cmd_stats(args) -> None:
    manifest = io_utils.load_json(ROOT / "corpus" / "manifest.json", {}) or {}
    atoms = io_utils.load_json(ROOT / "atoms" / "all.json", []) or []
    clusters = io_utils.load_json(ROOT / "clusters" / "clusters.json", {}) or {}
    meta = io_utils.load_json(ROOT / "clusters" / "meta.json", {}) or {}
    diets: dict[str, int] = {}
    for m in manifest.values():
        diets[str(m.get("diet"))] = diets.get(str(m.get("diet")), 0) + 1
    print(f"sources: {len(manifest)} {diets}")
    print(f"atoms: {len(atoms)}")
    if clusters:
        print(f"clusters: {len(clusters.get('clusters', []))}")
        print(f"coverage: {meta.get('coverage')}")
    runs = sorted((ROOT / "candidates").glob("*")) if (ROOT / "candidates").exists() else []
    runs = [r for r in runs if r.is_dir()]
    if runs:
        latest = runs[-1]
        print(f"latest run: {latest.name}")
        for beta_dir in sorted(latest.glob("beta_*")):
            results = io_utils.load_json(beta_dir / "results.json", {}) or {}
            cands = results.get("candidates", [])
            if cands:
                top = cands[0]
                print(
                    f"  {beta_dir.name}: pool={results['config']['n_pool']} "
                    f"top1={top['fusion']} :: {' + '.join(top['cluster_names'])}"
                )


# ---------------------------------------------------------------------------
# v2 setup / diagnostics
# ---------------------------------------------------------------------------

def _ollama_binary() -> Path | None:
    for path in (
        ROOT / ".ollama" / "bin" / "ollama",
        Path.home() / ".local" / "bin" / "ollama",
        Path("/usr/local/bin/ollama"),
        Path("/usr/bin/ollama"),
    ):
        if path.exists() and os.access(path, os.X_OK):
            return path
    import shutil

    found = shutil.which("ollama")
    return Path(found) if found else None


def cmd_setup(args) -> None:
    from story import collector, embeddings, judge, ledger, llm

    print(f"== StoryGen {__version__} setup ==")
    runtime = llm.describe_runtime()
    print("llm config:", runtime["config"])
    print("providers available:", ", ".join(runtime["providers"]) or "NONE")
    print("provider order:", " -> ".join(runtime["order"]))
    print("models:", json.dumps(runtime["models"]))
    print("ollama reachable:", runtime["ollama_reachable"])
    models = llm.ollama_models()
    if models:
        print("ollama models:", ", ".join(models))

    method, fn, attempts = embeddings.get_embedder(verbose=True)
    test = fn(["a story about a machine that learns to grieve"])
    print(f"embeddings: {method}, dim={len(test[0])}")
    for attempt in attempts:
        if attempt.get("status") == "failed":
            print("  -", attempt["method"], "failed:", attempt.get("error", "")[:120])

    works, _matrix = judge.load_canon()
    print(f"canon: {len(works)} famous works indexed")
    print("ledger:", json.dumps(ledger.stats()))

    binary = _ollama_binary()
    print("ollama binary:", str(binary) if binary else "not installed")
    if args.pull:
        if binary is None:
            print("Cannot --pull: Ollama is not installed. Download it from https://ollama.com/download")
            return
        env = dict(os.environ)
        env.setdefault("OLLAMA_MODELS", str(ROOT / ".ollama" / "models"))
        if not llm.ollama_reachable(llm.load_config()):
            print("starting Ollama server...")
            subprocess.Popen(
                [str(binary), "serve"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(2)
        model = llm.load_config()["models"]["ollama"]
        print(f"pulling {model} (this can take a while)...")
        subprocess.run([str(binary), "pull", model], env=env, check=False)
    if args.test:
        try:
            answer = llm.quick_ping()
            print("llm ping:", answer.strip()[:80])
        except Exception as exc:  # noqa: BLE001
            print("llm ping FAILED:", exc)
    print("\nnext: python storygen.py new \"your brief\" --full")


def cmd_ledger_stats(args) -> None:
    from story import ledger

    data = ledger.stats()
    print(json.dumps(data, indent=2))
    sources = ledger.source_stats()
    print("sources by diet:", json.dumps(sources))
    if data["premises"]:
        print("\nrecent premises:")
        for row in data["recent"]:
            print(f"  {row['created_at']}  {row['title']}  ({row['run_id']})")


# ---------------------------------------------------------------------------
# v2 pipeline
# ---------------------------------------------------------------------------

def _run_dir(run_id: str) -> Path:
    path = ROOT / "runs" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_beta_candidates(run_name: str, beta: float) -> dict:
    path = ROOT / "candidates" / run_name / f"beta_{beta:g}" / "results.json"
    return io_utils.load_json(path, {}) or {}


def _pick_new_candidates(
    results: list[dict],
    judged_keys: set[tuple[int, ...]],
    limit: int,
) -> list[dict]:
    picked = []
    for cand in results:
        key = tuple(sorted(int(x) for x in cand.get("cluster_ids", [])))
        if key in judged_keys:
            continue
        if float(cand.get("ledger_overlap", 0.0)) > 0.4:
            continue
        picked.append(cand)
        if len(picked) >= limit:
            break
    return picked


def _escalation_queries(brief_doc: dict, round_index: int) -> list[str]:
    from story import collector

    themes = [str(t) for t in brief_doc.get("themes") or []]
    rng = random.Random(1000 + round_index)
    extra = rng.sample(collector.FOREIGN_DOMAINS, k=min(3, len(collector.FOREIGN_DOMAINS)))
    if themes:
        extra.append(themes[round_index % len(themes)] + " history")
    return extra


def _preflight_provider(provider: str | None) -> None:
    from story import llm

    if provider and provider not in llm.load_config()["provider_order"]:
        raise SystemExit(f"Unknown provider {provider!r}. Choose from {llm.load_config()['provider_order']}")
    runtime = llm.describe_runtime()
    if not runtime["providers"]:
        raise SystemExit(
            "No LLM provider is available.\n"
            "Options:\n"
            "  - set GEMINI_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY, or\n"
            "  - install Ollama and run: python storygen.py setup --pull"
        )
    non_local = [p for p in runtime["providers"] if p != "ollama"]
    if not non_local and "ollama" in runtime["providers"]:
        wanted = llm.load_config()["models"]["ollama"]
        installed = llm.ollama_models()
        if installed and wanted not in installed:
            raise SystemExit(
                f"Ollama is running but {wanted!r} is not installed (have: {', '.join(installed)}).\n"
                f"Run: python storygen.py setup --pull"
            )


def run_pipeline(
    brief: str,
    *,
    mode: str = "outline",
    k: int = 3,
    beta: float | None = None,
    sources: int = 8,
    auto_escalate: bool = True,
    provider: str | None = None,
    count: int = 3,
    seed: int = 42,
    target_words: int = 3000,
    no_research: bool = False,
) -> str:
    from story import collector, judge, ledger, llm, sample, writer

    _preflight_provider(provider)
    run_id = time.strftime("%Y%m%dT%H%M%S") + f"-v2-seed{seed}"
    run_path = _run_dir(run_id)
    ledger.record_run(run_id, brief, {"mode": mode, "provider": provider})
    print(f"== run {run_id} ==", flush=True)
    print(f"brief: {brief}", flush=True)

    brief_doc = collector.parse_brief(brief, provider=provider)
    io_utils.save_json(run_path / "brief.json", brief_doc)

    research: dict = {"sources": [], "new_clusters": []}
    if not no_research and sources > 0:
        research = collector.collect(brief, n_sources=sources, provider=provider, brief_doc=brief_doc)
        io_utils.save_json(run_path / "research.json", research)

    anchors = collector.anchor_cluster_ids(brief, top_n=6)
    past = ledger.past_combos()
    judged_keys: set[tuple[int, ...]] = set()
    judged_all: list[dict] = []
    kept_all: list[dict] = []
    round_summaries: list[dict] = []

    rounds = 3 if auto_escalate else 1
    for round_index in range(rounds):
        if len(kept_all) >= count:
            break
        round_k = k
        if round_index == 1:
            round_k = 4 if k == 3 else k
        elif round_index >= 2:
            round_k = 2 if k == 3 else k
        round_beta = beta if beta is not None else min(0.9, 0.7 + 0.1 * round_index)
        if beta is not None:
            round_beta = min(0.92, beta + 0.06 * round_index)
        print(
            f"\n-- round {round_index + 1}/{rounds}: k={round_k}, beta={round_beta:g}, "
            f"anchors={len(anchors)}, history={len(past)} --",
            flush=True,
        )
        sample_name = f"{run_id}-r{round_index + 1}"
        sample.run(
            seed=seed + round_index * 17,
            k=round_k,
            betas=(round_beta,),
            top_k=max(30, count * 10),
            n_draws=20000,
            output_dir=sample_name,
            anchor_ids=anchors,
            past_combos=past,
            max_history_overlap=0.4,
            min_anchor=1,
        )
        results = _load_beta_candidates(sample_name, round_beta).get("candidates", [])
        picked = _pick_new_candidates(results, judged_keys, limit=max(12, count * 4))
        if not picked:
            print("[pipeline] no fresh candidates in this round", flush=True)
            round_summaries.append({"round": round_index + 1, "picked": 0, "survivors": 0})
            continue
        judged = judge.judge_candidates(picked, brief_doc, provider=provider)
        judged_all.extend(judged)
        judge.record_kills(judged, run_id)
        judge.save_judgments(run_path, round_beta, judged)
        for cand in judged:
            judged_keys.add(tuple(sorted(int(x) for x in cand.get("cluster_ids", []))))
        survivors = judge.survivors(judged)
        survivors = [s for s in survivors if all(
            tuple(sorted(int(x) for x in s.get("cluster_ids", []))) !=
            tuple(sorted(int(x) for x in kept.get("cluster_ids", [])))
            for kept in kept_all
        )]
        for s in survivors:
            if len(kept_all) < count:
                kept_all.append(s)
        round_summaries.append(
            {
                "round": round_index + 1,
                "k": round_k,
                "beta": round_beta,
                "picked": len(picked),
                "survivors": len(survivors),
                "kept_total": len(kept_all),
            }
        )
        print(
            f"[pipeline] round {round_index + 1}: {len(picked)} judged, "
            f"{len(survivors)} kept, total {len(kept_all)}/{count}",
            flush=True,
        )

        if len(kept_all) >= count or not auto_escalate:
            break
        # Self-escalation: hunt new domains for the next round, then re-anchor.
        print("[pipeline] shortfall — escalating research and diversity", flush=True)
        try:
            extra = collector.collect(
                brief,
                n_sources=max(3, sources // 2),
                provider=provider,
                brief_doc={**brief_doc, "search_queries": list(brief_doc.get("search_queries") or []) + _escalation_queries(brief_doc, round_index)},
            )
            research["sources"].extend(extra.get("sources", []))
            research["new_clusters"].extend(extra.get("new_clusters", []))
            io_utils.save_json(run_path / "research.json", research)
        except Exception as exc:  # noqa: BLE001 - escalation must not crash the run
            print(f"[pipeline] escalation research failed: {type(exc).__name__}: {exc}", flush=True)
        anchors = collector.anchor_cluster_ids(brief, top_n=6)
        past = ledger.past_combos()

    if judged_all:
        table_path = judge.save_judgment_table(run_path, judged_all)
        print(f"[pipeline] judgment table: {table_path}", flush=True)

    if not kept_all:
        io_utils.save_json(
            run_path / "run.json",
            {
                "run_id": run_id,
                "brief": brief,
                "brief_doc": brief_doc,
                "mode": mode,
                "error": "no survivors",
                "rounds": round_summaries,
                "sources": research.get("sources", []),
            },
        )
        raise SystemExit(
            "No premises survived the freshness gate. Honest result: the brief may be "
            "too close to a famous work, or the local judge may be too weak. Try a more "
            "specific brief, --sources 10, or a stronger provider."
        )
    if len(kept_all) < count:
        print(
            f"[pipeline] HONEST SHORTFALL: {len(kept_all)}/{count} premises survived. "
            "The bar was not lowered.",
            flush=True,
        )

    premises_out = []
    for i, candidate in enumerate(kept_all[:count], start=1):
        print(f"\n-- writing premise {i}/{min(count, len(kept_all))} --", flush=True)
        try:
            premise = writer.write_premise(candidate, brief_doc, provider=provider)
        except writer.WriterError as exc:
            print(f"[pipeline] premise rejected: {exc}", flush=True)
            continue
        premise_path = writer.save_premise(run_path, i, premise)
        record = {
            "index": i,
            "title": premise["title"],
            "logline": premise["logline"],
            "premise": premise["premise"],
            "why_fresh": premise["why_fresh"],
            "built_from": premise.get("built_from", []),
            "cluster_ids": premise.get("cluster_ids", []),
            "cluster_names": premise.get("cluster_names", []),
            "judge": premise.get("judge", {}),
            "files": {"premise": premise_path.name},
        }
        if mode in ("outline", "full"):
            try:
                outline = writer.write_outline(premise, brief_doc, provider=provider)
                outline_path = writer.save_outline(run_path, i, outline, premise)
                record["outline"] = outline
                record["files"]["outline"] = outline_path.name
            except writer.WriterError as exc:
                print(f"[pipeline] outline failed for {premise['title']}: {exc}", flush=True)
        if mode == "full":
            try:
                story = writer.write_story(
                    premise,
                    record.get("outline") or {"acts": []},
                    brief_doc,
                    provider=provider,
                    target_words=target_words,
                )
                story_path = writer.save_story(run_path, i, story, premise)
                record["story"] = {
                    "word_count": story["word_count"],
                    "repetition": story["repetition"],
                }
                record["files"]["story"] = story_path.name
            except writer.WriterError as exc:
                print(f"[pipeline] full story failed for {premise['title']}: {exc}", flush=True)
        ledger.record_premise(
            run_id,
            premise["title"],
            premise["logline"],
            premise["premise"],
            brief,
            [int(x) for x in premise.get("cluster_ids", [])],
            [str(x) for x in premise.get("cluster_names", [])],
            float(premise.get("fusion") or 0.0),
        )
        premises_out.append(record)
        print(f"[pipeline] saved: {premise_path}", flush=True)

    if len(premises_out) < count:
        print(
            f"[pipeline] FINAL SHORTFALL: {len(premises_out)}/{count} premises saved. "
            "Rejected premises were not replaced with weaker ones.",
            flush=True,
        )
    summary = {
        "run_id": run_id,
        "brief": brief,
        "brief_doc": brief_doc,
        "mode": mode,
        "provider": provider or llm.available_providers(llm.load_config())[0],
        "rounds": round_summaries,
        "sources": research.get("sources", []),
        "premises": premises_out,
        "judged": len(judged_all),
        "survivors": len(kept_all),
        "count_requested": count,
    }
    io_utils.save_json(run_path / "run.json", summary)

    # The spec's Gate 8 asks for premises under premises/. Keep the full run in
    # runs/<id>/ and publish the human-facing deliverables alongside it.
    premises_dir = ROOT / "premises" / run_id
    premises_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run_path / "run.json", premises_dir / "run.json")
    if (run_path / "judgment.md").exists():
        shutil.copy2(run_path / "judgment.md", premises_dir / "judgment.md")
    for record in premises_out:
        for rel in record["files"].values():
            src = run_path / rel
            if src.exists():
                shutil.copy2(src, premises_dir / rel)
    extras = kept_all[count:]
    if extras:
        lines = ["# Runners-up", ""]
        for cand in extras:
            lines.append(
                f"- {' + '.join(cand.get('cluster_names', []))} "
                f"(fusion {float(cand.get('fusion') or 0):.3f})"
            )
        (premises_dir / "runners-up.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n== done: {len(premises_out)} premise(s) in {run_path} ==")
    print(f"   published: {premises_dir}")
    for record in premises_out:
        print(f"  {record['index']:02d}. {record['title']} — {record['logline']}")
        for kind, name in record["files"].items():
            print(f"      {kind}: {run_path / name}")
    return run_id


# ---------------------------------------------------------------------------
# v2 commands
# ---------------------------------------------------------------------------

def cmd_new(args) -> None:
    run_pipeline(
        args.brief,
        mode="full" if args.full else ("outline" if not args.premises_only else "premise"),
        k=args.k,
        beta=args.beta,
        sources=args.sources,
        auto_escalate=not args.no_escalate,
        provider=args.provider,
        count=args.count,
        seed=args.seed,
        target_words=args.target_words,
        no_research=args.no_research,
    )


def cmd_judge(args) -> None:
    """Rate the top-N candidates of an existing sample run (Gate 7 artifact)."""
    from story import collector, judge

    sample_dir = Path(args.sample)
    if not sample_dir.is_absolute():
        sample_dir = ROOT / "candidates" / args.sample
    results_path = sample_dir / f"beta_{args.beta:g}" / "results.json"
    results = io_utils.load_json(results_path, {}) or {}
    candidates = results.get("candidates", [])[: args.top]
    if not candidates:
        raise SystemExit(f"No candidates in {results_path}")

    # Refresh cluster labels in case the sample predates a naming pass.
    clusters = io_utils.load_json(ROOT / "clusters" / "clusters.json", {}) or {}
    name_by_id = {int(c["id"]): c.get("name") for c in clusters.get("clusters", [])}
    for c in candidates:
        c["cluster_names"] = [
            name_by_id.get(int(cid)) or f"cluster-{cid}" for cid in c.get("cluster_ids", [])
        ]

    brief = args.brief
    if args.brief_file:
        brief = Path(args.brief_file).read_text(encoding="utf-8")
    brief_doc = collector.parse_brief(brief, provider=args.provider)
    judged = judge.judge_candidates(
        candidates, brief_doc, provider=args.provider, batch_size=args.batch_size
    )

    out_dir = Path(args.output) if args.output else ROOT / "runs" / f"{sample_dir.name}-judged"
    out_dir.mkdir(parents=True, exist_ok=True)
    judge.save_judgments(out_dir, args.beta, judged)
    table = judge.save_judgment_table(
        out_dir, judged, title=f"Judgment Table — {sample_dir.name} β={args.beta:g}"
    )
    kept = judge.survivors(judged)
    io_utils.save_json(
        out_dir / "judge_run.json",
        {
            "sample": sample_dir.name,
            "beta": args.beta,
            "brief": brief,
            "brief_doc": brief_doc,
            "judged": len(judged),
            "survivors": len(kept),
            "table": table.name,
        },
    )
    print(f"[judge] {len(kept)}/{len(judged)} survived; table: {table}", flush=True)


def cmd_discover(args) -> None:
    from story import io_utils as iu
    from story import llm

    clusters = iu.load_json(ROOT / "clusters" / "clusters.json", {}) or {}
    names = [c.get("name") or f"cluster-{c['id']}" for c in clusters.get("clusters", [])]
    if not names:
        raise SystemExit("No clusters found; run `storygen.py cluster` first")
    rng = random.Random(args.seed)
    picks = rng.sample(names, k=min(3, len(names)))
    foreign = rng.choice(
        [
            "deep-sea biology",
            "medieval beekeeping",
            "Antarctic logistics",
            "Soviet radio cryptography",
            "cathedral bell casting",
            "migratory bird tracking",
        ]
    )
    prompt = f"""Invent a one-sentence story brief for an automated story engine.
Force together these strange ingredients without using a chosen-one or rebellion arc:
- {picks[0]}
- {picks[1]}
- {foreign}
The brief must imply human stakes and a specific world, not a genre label.
Return ONLY JSON: {{"brief": "..."}}
"""
    try:
        data = llm.complete_json(prompt, stage_name="collector", provider=args.provider)
        brief = str((data or {}).get("brief") or "").strip() if isinstance(data, dict) else ""
    except Exception as exc:  # noqa: BLE001
        print(f"[discover] LLM brief failed ({exc}); using a deterministic composition", flush=True)
        brief = ""
    if not brief:
        brief = (
            f"A story that crosses {picks[0]} with {picks[1]} and the material logic of "
            f"{foreign}; the protagonist must choose between two kinds of loyalty, "
            f"and no prophecy or chosen-one arc exists."
        )
    print(f"[discover] brief: {brief}", flush=True)
    run_pipeline(
        brief,
        mode="full" if args.full else ("outline" if not args.premises_only else "premise"),
        k=args.k,
        beta=args.beta,
        sources=args.sources,
        auto_escalate=not args.no_escalate,
        provider=args.provider,
        count=args.count,
        seed=args.seed,
        target_words=args.target_words,
        no_research=args.no_research,
    )


def cmd_expand(args) -> None:
    from story import writer

    run_path = Path(args.run)
    if not run_path.is_absolute():
        candidates = [ROOT / "runs" / args.run, ROOT / args.run]
        run_path = next((p for p in candidates if p.exists()), candidates[0])
    data = io_utils.load_json(run_path / "run.json", {}) or {}
    premises = data.get("premises") or []
    if not premises:
        raise SystemExit(f"No premises in {run_path / 'run.json'}")
    record = None
    for item in premises:
        if int(item.get("index", -1)) == int(args.index):
            record = item
            break
    if record is None:
        raise SystemExit(f"No premise with index {args.index}; available: {[p['index'] for p in premises]}")
    premise = {
        "title": record["title"],
        "logline": record["logline"],
        "premise": record["premise"],
        "why_fresh": record.get("why_fresh", ""),
    }
    brief_doc = data.get("brief_doc") or {}
    mode = "full" if args.full else "outline"
    if mode == "outline" and not record.get("outline"):
        outline = writer.write_outline(premise, brief_doc, provider=args.provider)
        path = writer.save_outline(run_path, int(record["index"]), outline, premise)
        record["outline"] = outline
        record.setdefault("files", {})["outline"] = path.name
        print("outline:", path)
    if mode == "full":
        outline = record.get("outline")
        if not outline:
            outline = writer.write_outline(premise, brief_doc, provider=args.provider)
            path = writer.save_outline(run_path, int(record["index"]), outline, premise)
            record["outline"] = outline
            record.setdefault("files", {})["outline"] = path.name
            print("outline:", path)
        story = writer.write_story(
            premise,
            outline,
            brief_doc,
            provider=args.provider,
            target_words=args.target_words,
        )
        path = writer.save_story(run_path, int(record["index"]), story, premise)
        record["story"] = {"word_count": story["word_count"], "repetition": story["repetition"]}
        record.setdefault("files", {})["story"] = path.name
        print("story:", path, f"({story['word_count']} words)")
    io_utils.save_json(run_path / "run.json", data)


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------

def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def _ask_choice(prompt: str, options: list[str], default: int = 1) -> int:
    print(prompt)
    for i, option in enumerate(options, start=1):
        print(f"  {i}) {option}")
    raw = _ask("choose", str(default))
    try:
        value = int(raw)
        if 1 <= value <= len(options):
            return value
    except ValueError:
        pass
    return default


def cmd_wizard(args) -> None:
    print("StoryGen wizard — press Ctrl-C to leave.\n")
    while True:
        action = _ask_choice(
            "What do you want to do?",
            ["New story from a brief", "Surprise me (discover)", "Expand an old premise", "Ledger stats", "Setup check", "Quit"],
        )
        if action == 6:
            return
        if action == 4:
            cmd_ledger_stats(argparse.Namespace())
            continue
        if action == 5:
            cmd_setup(argparse.Namespace(pull=False, test=True))
            continue
        if action == 2:
            fmt = _ask_choice("Output?", ["Premises only", "Premises + outlines", "Full story drafts"], 2)
            ns = argparse.Namespace(
                full=fmt == 3,
                premises_only=fmt == 1,
                k=3,
                beta=None,
                sources=int(_ask("Fresh sources per run", "8")),
                no_escalate=_ask_choice("If fewer than 3 survive?", ["Escalate automatically", "Stop honestly"], 1) == 2,
                provider=_ask("Provider (blank = auto)", "") or None,
                count=int(_ask("How many premises", "3")),
                seed=42,
                target_words=int(_ask("Target story words (full mode)", "3000")),
                no_research=False,
            )
            cmd_discover(ns)
            continue
        if action == 3:
            runs = sorted((ROOT / "runs").glob("*/run.json")) if (ROOT / "runs").exists() else []
            if not runs:
                print("No runs yet.")
                continue
            for i, path in enumerate(runs, start=1):
                print(f"  {i}) {path.parent.name}")
            choice = int(_ask("Choose run", str(len(runs))))
            ns = argparse.Namespace(
                run=str(runs[max(0, min(choice - 1, len(runs) - 1))].parent),
                index=int(_ask("Premise index", "1")),
                full=_ask_choice("Expand to?", ["Outline", "Full story"], 1) == 2,
                provider=_ask("Provider (blank = auto)", "") or None,
                target_words=int(_ask("Target words", "3000")),
            )
            cmd_expand(ns)
            continue

        brief = _ask("Brief (constraints welcome)")
        if not brief:
            print("A brief is required.")
            continue
        fmt = _ask_choice("Output?", ["Premises only", "Premises + outlines", "Full story drafts"], 2)
        no_escalate = _ask_choice("If fewer than 3 survive?", ["Escalate automatically", "Stop honestly"], 1) == 2
        ns = argparse.Namespace(
            brief=brief,
            full=fmt == 3,
            premises_only=fmt == 1,
            k=3,
            beta=None,
            sources=int(_ask("Fresh sources per run", "8")),
            no_escalate=no_escalate,
            provider=_ask("Provider (blank = auto)", "") or None,
            count=int(_ask("How many premises", "3")),
            seed=42,
            target_words=int(_ask("Target story words (full mode)", "3000")),
            no_research=False,
        )
        cmd_new(ns)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _add_v2_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--full", action="store_true", help="also draft the full 2-5k word story")
    parser.add_argument("--premises-only", action="store_true", help="stop at logline + premise")
    parser.add_argument("--k", type=int, default=3, choices=[2, 3, 4])
    parser.add_argument("--beta", type=float, default=None)
    parser.add_argument("--sources", type=int, default=8, help="fresh sources to fetch this run")
    parser.add_argument("--no-escalate", action="store_true", help="one round only, no self-escalation")
    parser.add_argument("--no-research", action="store_true", help="skip live web research")
    parser.add_argument("--provider", type=str, default=None, help="gemini | anthropic | openai | ollama")
    parser.add_argument("--count", type=int, default=3, help="premises to keep")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--target-words", type=int, default=3000)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="storygen.py",
        description=f"StoryGen {__version__} — fully automated, self-escalating story maker",
    )
    parser.add_argument(
        "--version", action="version", version=f"StoryGen {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("setup", help="check providers, embedder, canon, ledger; optionally pull Ollama")
    p.add_argument("--pull", action="store_true", help="start Ollama and pull the configured model")
    p.add_argument("--test", action="store_true", help="make one tiny LLM call")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("new", help="full-auto story run from a brief")
    p.add_argument("brief", type=str)
    _add_v2_run_args(p)
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("discover", help="surprise-me run: the engine composes its own brief")
    _add_v2_run_args(p)
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("judge", help="rate the top-N candidates of an existing sample run")
    p.add_argument("--sample", required=True, help="sample name under candidates/ or a path")
    p.add_argument("--beta", type=float, default=0.7)
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--batch-size", type=int, default=3)
    p.add_argument("--brief", default=(
        "A fresh, human-centered story in the AI era. Avoid famous works and the "
        "chosen-one, prophecy, and generic-dystopia gravity wells."
    ))
    p.add_argument("--brief-file", default=None)
    p.add_argument("--provider", default=None)
    p.add_argument("--output", default=None)
    p.set_defaults(func=cmd_judge)

    p = sub.add_parser("expand", help="grow an old premise into an outline or full story")
    p.add_argument("--run", required=True, help="run directory or id")
    p.add_argument("--index", type=int, default=1)
    p.add_argument("--full", action="store_true")
    p.add_argument("--provider", type=str, default=None)
    p.add_argument("--target-words", type=int, default=3000)
    p.set_defaults(func=cmd_expand)

    p = sub.add_parser("ledger-stats", help="permanent anti-repetition memory")
    p.set_defaults(func=cmd_ledger_stats)

    p = sub.add_parser("name-clusters", help="LLM-name clusters still using keyword fallback names")
    p.add_argument("--limit", type=int, default=None, help="rename only the N largest fallback clusters")
    p.set_defaults(func=cmd_name_clusters)

    p = sub.add_parser("wizard", help="interactive prompts for new/discover/expand")
    p.set_defaults(func=cmd_wizard)

    # v1 compatibility
    p = sub.add_parser("corpus-check", help="validate corpus manifest and files")
    p.set_defaults(func=cmd_corpus_check)

    p = sub.add_parser("atomize-init", help="list sources still missing atoms")
    p.set_defaults(func=cmd_atomize_init)

    p = sub.add_parser("cluster", help="embed atoms, cluster, write clusters/")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--apply-names", action="store_true", help="merge clusters/names.json into clusters.json")
    p.add_argument("--reembed", action="store_true", help="force re-embedding (e.g. after a model2vec upgrade)")
    p.add_argument("--auto-name", action="store_true", help="reuse names by atom overlap, then LLM-name the rest")
    p.set_defaults(func=cmd_cluster)

    p = sub.add_parser("sample", help="build candidates, score, fuse, write candidates/<run>/")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--k", type=int, default=3, choices=[2, 3, 4])
    p.add_argument("--beta", type=float, default=None)
    p.add_argument("--betas", type=str, default="0.5,0.7,0.85")
    p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--n-draws", type=int, default=20000)
    p.add_argument("--output-dir", type=str, default=None)
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("stats", help="corpus/atoms/clusters/pool report")
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    if args.command == "wizard" and not sys.stdin.isatty():
        raise SystemExit("wizard needs an interactive terminal")
    args.func(args)


if __name__ == "__main__":
    main()
