"""Freshness judge: canon collision detection + LLM rubric verdicts."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import numpy as np

from . import embeddings, io_utils, ledger, llm, stats

ROOT = io_utils.ROOT
CANON_PATH = ROOT / "canon" / "canon.json"
CANON_CACHE = ROOT / "canon" / "canon_emb.npz"
PROMPT = ROOT / "prompts" / "judge_json.md"

DEFAULT_CANON_KILL = 0.68


# ---------------------------------------------------------------------------
# Canon index
# ---------------------------------------------------------------------------

_CANON_CACHE: tuple[list[dict[str, Any]], np.ndarray] | None = None


def load_canon() -> tuple[list[dict[str, Any]], np.ndarray]:
    global _CANON_CACHE
    if _CANON_CACHE is not None:
        return _CANON_CACHE
    doc = io_utils.load_json(CANON_PATH, {}) or {}
    works = doc.get("works", []) if isinstance(doc, dict) else doc
    if not works:
        works = []
    texts = [f"{w['title']} ({w.get('year', '')}). {w.get('text', '')}" for w in works]
    fingerprint = io_utils.sha1("|".join(texts))
    if CANON_CACHE.exists() and works:
        try:
            data = np.load(CANON_CACHE, allow_pickle=True)
            cached_titles = [str(x) for x in data["titles"]]
            cached_fp = str(data["fingerprint"]) if "fingerprint" in data else ""
            if cached_titles == [str(w["title"]) for w in works] and cached_fp == fingerprint:
                _CANON_CACHE = (works, data["matrix"].astype(np.float64))
                return _CANON_CACHE
        except Exception:
            pass
    matrix, method = embeddings.embed_texts(texts) if texts else (np.zeros((0, 1)), "none")
    if works:
        np.savez_compressed(
            CANON_CACHE,
            titles=np.array([w["title"] for w in works], dtype=object),
            matrix=np.asarray(matrix, dtype=np.float32),
            method=np.array([method]),
            fingerprint=np.array([fingerprint]),
        )
    _CANON_CACHE = (works, np.asarray(matrix, dtype=np.float64))
    return _CANON_CACHE


def canon_neighbors(text: str, top_k: int = 3) -> dict[str, Any]:
    works, matrix = load_canon()
    if not works or not text.strip():
        return {"max_similarity": 0.0, "closest": []}
    query, _method = embeddings.embed_texts([text])
    q = stats.normalize_rows(np.asarray(query, dtype=np.float64))[0]
    m = stats.normalize_rows(matrix)
    sims = m @ q
    order = np.argsort(-sims)[:top_k]
    closest = [
        {
            "title": works[int(i)]["title"],
            "year": works[int(i)].get("year"),
            "similarity": round(float(sims[int(i)]), 4),
        }
        for i in order
    ]
    return {"max_similarity": round(float(sims[int(order[0])]), 4), "closest": closest}


def candidate_text(candidate: dict[str, Any]) -> str:
    parts = []
    for name, atom in zip(candidate.get("cluster_names", []), candidate.get("exemplar_atoms", [])):
        parts.append(f"{name}: {atom}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# LLM judgment
# ---------------------------------------------------------------------------

_DEFAULT_PROMPT = """You are the freshness gate for a cross-domain story generator. Judge each
candidate COMBINATION as a story engine, not its individual cluster names. Be ruthless
about a candidate that is a coat of paint on a famous work, but do not kill a candidate
merely because one ingredient is familiar.

BRIEF (constraints are binding):
{brief}

STEP 1 - name the engine. In one sentence: who wants what, and what blocks them?
If you cannot name a protagonist, a want, and an obstacle, the combination is weak.

STEP 2 - score 0-10. Use the full range; do not default to 0.
coherence: 3 = pretty words, no engine; 6 = workable stakes; 7 = clear stakes;
9 = pressure on both world and protagonist identity. A usable engine is 6-8.
freshness: 2 = the same story as a famous work; 6 = individual parts fresh but
the arc is known; 7 = no obvious famous occupant; 9 = genuinely novel combination.
viability: can this sustain a film/novel/game with human stakes? A normal answer is 6-8.

CANON BANDS (embedding similarity, not taste; printed per candidate):
- below 0.55: faint echo only. This is NOT a kill reason and NOT evidence of copying.
- 0.55 to 0.67: warning. Kill only if the actual story engine is the same as that work.
- 0.68 and above: automatic kill by the system; you may still give your own verdict.
Never call a candidate derivative on the strength of a title alone. Name the shared
engine if you claim derivation.

KILL only if coherence < 6 OR freshness < 7 OR the closest canon work is effectively
the same story. Name the dead-weight cluster when killing.

CANDIDATES
{candidates}

Return ONLY one JSON object. No markdown, no prose before or after, no code fences.
Give exactly one verdict per candidate, numbered 1..N, with the engine filled in:
{{"verdicts": [
  {{"candidate": 1, "engine": "who wants what and what blocks them",
    "coherence": 7, "freshness": 7, "viability": 6,
    "decision": "KEEP", "kill_cluster": null,
    "reason": "one sentence naming the engine or the dead weight",
    "closest_canon": "title"}}
]}}
"""


def _load_prompt() -> str:
    if PROMPT.exists():
        text = PROMPT.read_text(encoding="utf-8")
        if text.strip():
            return text
    return _DEFAULT_PROMPT


def _format_candidates(candidates: list[dict[str, Any]]) -> str:
    blocks = []
    for i, c in enumerate(candidates, start=1):
        names = " + ".join(c.get("cluster_names", []))
        atoms = "\n".join(f"  - {a}" for a in c.get("exemplar_atoms", []))
        canon = c.get("_canon", {})
        max_sim = float(canon.get("max_similarity", 0.0))
        if max_sim >= 0.68:
            band = "collision band: automatic kill"
        elif max_sim >= 0.55:
            band = "warning band: kill only if the engine is the same"
        else:
            band = "faint echo only: NOT grounds for a derivation claim"
        hits = ", ".join(
            f"{h['title']} (sim {h['similarity']:.2f})" for h in canon.get("closest", [])[:3]
        ) or "none"
        wells = ", ".join(c.get("_wells") or []) or "none"
        blocks.append(
            f"CANDIDATE {i}\nclusters: {names}\natoms:\n{atoms}\n"
            f"gravity wells present: {wells}\n"
            f"canon max similarity: {max_sim:.2f} ({band})\ncanon hits: {hits}"
        )
    return "\n\n".join(blocks)


def _heuristic_verdicts(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Conservative fallback when the model cannot produce JSON."""
    verdicts = []
    for i, c in enumerate(candidates, start=1):
        canon = c.get("_canon", {})
        max_canon = float(canon.get("max_similarity", 0.0))
        freshness = max(0, min(10, round(10.0 - max(0.0, max_canon - 0.55) * 20.0)))
        coherence = 7 if c.get("fusion", 0) >= 0 else 6
        viability = 6
        decision = "KILL" if freshness < 7 or max_canon >= DEFAULT_CANON_KILL else "KEEP"
        verdicts.append(
            {
                "candidate": i,
                "coherence": coherence,
                "freshness": freshness,
                "viability": viability,
                "decision": decision,
                "kill_cluster": None,
                "reason": (
                    "heuristic fallback: closest canon work "
                    + (canon.get("closest", [{}])[0].get("title", "none") if canon.get("closest") else "none")
                ),
                "closest_canon": (canon.get("closest", [{}])[0].get("title", "") if canon.get("closest") else ""),
                "fallback": True,
            }
        )
    return verdicts


def _verdict_items(raw: Any, n: int) -> dict[int, dict[str, Any]]:
    """Parse any usable verdicts from a batch response, even a partial one."""
    if isinstance(raw, dict):
        raw = raw.get("verdicts")
    if not isinstance(raw, list):
        return {}
    by_index: dict[int, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("candidate") or item.get("index") or 0)
        except Exception:
            continue
        if not (1 <= idx <= n):
            continue
        try:
            coh = float(item.get("coherence"))
            fresh = float(item.get("freshness"))
            via = float(item.get("viability", 6))
        except Exception:
            continue
        decision = str(item.get("decision") or "").upper()
        if decision not in {"KEEP", "KILL"}:
            decision = "KEEP" if coh >= 6 and fresh >= 7 else "KILL"
        by_index[idx] = {
            "candidate": idx,
            "coherence": max(0.0, min(10.0, coh)),
            "freshness": max(0.0, min(10.0, fresh)),
            "viability": max(0.0, min(10.0, via)),
            "decision": decision,
            "kill_cluster": item.get("kill_cluster"),
            "engine": str(item.get("engine") or "").strip()[:300],
            "reason": str(item.get("reason") or "").strip()[:400],
            "closest_canon": str(item.get("closest_canon") or "").strip()[:120],
        }
    return by_index


def _validate_verdicts(raw: Any, n: int) -> list[dict[str, Any]] | None:
    by_index = _verdict_items(raw, n)
    if len(by_index) < n:
        return None
    return [by_index[i] for i in range(1, n + 1)]


def judge_candidates(
    candidates: list[dict[str, Any]],
    brief_doc: dict[str, Any],
    provider: str | None = None,
    batch_size: int = 3,
    canon_kill: float = DEFAULT_CANON_KILL,
) -> list[dict[str, Any]]:
    """Attach canon hits + LLM verdicts to candidates; return enriched copies."""
    enriched: list[dict[str, Any]] = []
    wells_doc = io_utils.load_json(ROOT / "clusters" / "gravity_wells.json", {}) or {}
    well_names = {int(w["cluster_id"]): w.get("name") for w in wells_doc.get("wells", [])}
    for c in candidates:
        text = candidate_text(c)
        c = dict(c)
        c["_canon"] = canon_neighbors(text, top_k=3)
        c["_wells"] = [
            f"{cid}:{well_names[cid]}" for cid in c.get("cluster_ids", []) if int(cid) in well_names
        ]
        enriched.append(c)

    prompt_tpl = _load_prompt()
    brief_lines = [
        brief_doc.get("brief", ""),
        f"Hard constraints: {brief_doc.get('hard_constraints_summary') or 'none'}",
        f"Must include: {', '.join(brief_doc.get('must_include') or []) or 'none'}",
        f"Must avoid: {', '.join(brief_doc.get('must_avoid') or []) or 'none'}",
        f"Banned tropes: {', '.join(brief_doc.get('banned_tropes') or []) or 'none'}",
        f"Genre/tone: {brief_doc.get('genre') or 'open'} / {brief_doc.get('tone') or 'open'}",
        "Gravity wells to avoid becoming: "
        + (", ".join(str(n) for n in well_names.values()) or "none"),
    ]
    brief_text = "\n".join(brief_lines)

    def run_prompt(cands: list[dict[str, Any]], label: str) -> dict[int, dict[str, Any]] | None:
        prompt = prompt_tpl.replace("{brief}", brief_text).replace(
            "{candidates}", _format_candidates(cands)
        )
        for attempt in range(2):
            try:
                raw = llm.complete_json(prompt, stage_name="judge", provider=provider)
                verdicts = _verdict_items(raw, len(cands))
                if verdicts:
                    return verdicts
                print(
                    f"[judge] {label} returned JSON but no usable verdicts "
                    f"({len(cands)} candidate(s)): {str(raw)[:400]}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[judge] {label} attempt {attempt + 1} failed: {exc}", flush=True)
        return None

    results: list[dict[str, Any]] = []
    for start in range(0, len(enriched), batch_size):
        batch = enriched[start : start + batch_size]
        label = f"batch {start // batch_size + 1}"
        verdict_map = run_prompt(batch, label) or {}
        if len(verdict_map) < len(batch):
            # A 3B model can lose one verdict across a batch. Keep the valid ones
            # and escalate only the missing candidates to their own call.
            if len(batch) > 1:
                print(
                    f"[judge] {label}: {len(verdict_map)}/{len(batch)} usable; "
                    "retrying missing candidates one at a time",
                    flush=True,
                )
            for pos, cand in enumerate(batch, start=1):
                if pos in verdict_map:
                    continue
                one = run_prompt([cand], "single") or {}
                if 1 in one:
                    verdict_map[pos] = one[1]
                else:
                    verdict_map[pos] = _heuristic_verdicts([cand])[0]
        verdicts = [verdict_map[i] for i in range(1, len(batch) + 1)]

        for cand, verdict in zip(batch, verdicts):
            canon = cand.get("_canon") or {"max_similarity": 0.0, "closest": []}
            cand.pop("_canon", None)
            cid_names = cand.get("cluster_names", [])
            kill_cluster = verdict.get("kill_cluster")
            if kill_cluster is not None:
                try:
                    kill_cluster = int(kill_cluster)
                except Exception:
                    kill_cluster = None
            # Binding overrides: canon collision or missing constraints kill.
            reasons = [verdict.get("reason", "")]
            decision = verdict["decision"]
            if canon.get("max_similarity", 0.0) >= canon_kill:
                decision = "KILL"
                top = canon["closest"][0]
                reasons.append(
                    f"canon collision: {top['title']} ({top['similarity']:.2f})"
                )
            forbidden = _hits_forbidden(cand, brief_doc)
            if forbidden:
                decision = "KILL"
                reasons.append(f"violates brief constraint: {forbidden}")
            if verdict["coherence"] < 6 or verdict["freshness"] < 7:
                decision = "KILL"
            if decision == "KILL" and not reasons[-1]:
                reasons.append("below rubric floor")
            out = dict(cand)
            out["judge"] = {
                "coherence": verdict["coherence"],
                "freshness": verdict["freshness"],
                "viability": verdict["viability"],
                "decision": decision,
                "engine": verdict.get("engine", ""),
                "kill_cluster": kill_cluster,
                "kill_cluster_name": (
                    cid_names[kill_cluster] if isinstance(kill_cluster, int) and 0 <= kill_cluster < len(cid_names) else None
                ),
                "reason": "; ".join(r for r in reasons if r),
                "closest_canon": canon.get("closest", []),
                "canon_max_similarity": canon.get("max_similarity", 0.0),
                "fallback": bool(verdict.get("fallback")),
            }
            out["quality"] = round(
                verdict["freshness"] * 2.0
                + verdict["coherence"]
                + verdict["viability"] * 0.5
                + float(cand.get("fusion", 0.0)) * 0.5
                - canon.get("max_similarity", 0.0) * 6.0,
                3,
            )
            results.append(out)
            status = "KEEP" if decision == "KEEP" else "KILL"
            print(
                f"[judge] {status} {out['quality']:6.2f} :: {' + '.join(cid_names)} "
                f"(coh {verdict['coherence']:.0f}/fresh {verdict['freshness']:.0f}) {out['judge']['reason'][:120]}",
                flush=True,
            )
    return results


def _hits_forbidden(candidate: dict[str, Any], brief_doc: dict[str, Any]) -> str:
    text = candidate_text(candidate).lower()
    for term in (brief_doc.get("must_avoid") or []) + (brief_doc.get("banned_tropes") or []):
        term = str(term).strip()
        if len(term) < 3:
            continue
        phrase = term.lower()
        variants = {phrase}
        for prefix in ("no ", "no more ", "without ", "avoid ", "never "):
            if phrase.startswith(prefix):
                variants.add(phrase[len(prefix) :].strip())
        for variant in variants:
            if len(variant) >= 3 and re.search(rf"\b{re.escape(variant)}\b", text):
                return term
    return ""


def survivors(judged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept = [c for c in judged if c.get("judge", {}).get("decision") == "KEEP"]
    return sorted(kept, key=lambda c: -float(c.get("quality", 0.0)))


def record_kills(judged: list[dict[str, Any]], run_id: str) -> None:
    for c in judged:
        j = c.get("judge", {})
        if j.get("decision") != "KEEP":
            ledger.record_kill(
                run_id,
                [int(x) for x in c.get("cluster_ids", [])],
                j.get("reason", "killed"),
                {
                    "coherence": j.get("coherence"),
                    "freshness": j.get("freshness"),
                    "viability": j.get("viability"),
                    "closest_canon": j.get("closest_canon"),
                },
            )


def save_judgments(run_dir: str | Path, beta: float, judged: list[dict[str, Any]]) -> None:
    io_utils.save_json(
        Path(run_dir) / f"judgments_beta_{beta:g}.json",
        {"beta": beta, "judged": judged, "survivors": len(survivors(judged))},
    )


def save_judgment_table(
    run_dir: str | Path,
    judged: list[dict[str, Any]],
    title: str = "Judgment Table",
) -> Path:
    """Write the human-readable Gate-7 table for a set of judged candidates."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {title}",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| # | clusters | coherence | freshness | viability | canon max | decision | reason |",
        "|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for i, c in enumerate(judged, start=1):
        j = c.get("judge", {})
        names = " + ".join(c.get("cluster_names", [])) or "none"
        reason = str(j.get("reason", "")).replace("|", "/").replace("\n", " ")[:180]
        lines.append(
            f"| {i} | {names} | {j.get('coherence', '')} | {j.get('freshness', '')} | "
            f"{j.get('viability', '')} | {j.get('canon_max_similarity', '')} | "
            f"{j.get('decision', '')} | {reason} |"
        )
    lines += ["", f"**Survivors: {len(survivors(judged))} / {len(judged)}**", ""]
    path = run_dir / "judgment.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
