"""Agglomerative clustering of narrative atoms + coverage metrics (§10)."""

from __future__ import annotations

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

from . import embeddings, io_utils, stats

ATOMS = io_utils.ROOT / "atoms" / "all.json"
CLUSTERS = io_utils.ROOT / "clusters" / "clusters.json"
META = io_utils.ROOT / "clusters" / "meta.json"
NAMES = io_utils.ROOT / "clusters" / "names.json"
DIGEST = io_utils.ROOT / "clusters" / "digest.json"
SUPER_MD = io_utils.ROOT / "clusters" / "super_atoms.md"


def _merge_small(labels: np.ndarray, matrix: np.ndarray, min_size: int = 3):
    labels = np.asarray(labels).copy()
    uniq, counts = np.unique(labels, return_counts=True)
    big = uniq[counts >= min_size]
    if len(big) == 0:
        return labels, 0
    centroids = np.vstack(
        [stats.normalize_rows(matrix[labels == b]).mean(axis=0) for b in big]
    )
    centroids = stats.normalize_rows(centroids)
    small_ids = uniq[counts < min_size]
    mask = np.isin(labels, small_ids)
    moved = int(mask.sum())
    if moved:
        sims = stats.normalize_rows(matrix[mask]) @ centroids.T
        nearest = big[np.argmax(sims, axis=1)]
        labels[mask] = nearest
    return labels, moved


def _apply_names() -> None:
    clusters = io_utils.load_json(CLUSTERS)
    names = io_utils.load_json(NAMES, {}) or {}
    if clusters is None:
        raise SystemExit("clusters/clusters.json missing")
    filled = 0
    for cluster in clusters["clusters"]:
        entry = names.get(str(cluster["id"])) or names.get(cluster["id"])
        if entry:
            cluster["name"] = entry.get("name", cluster.get("name"))
            cluster["super_atom"] = entry.get("super_atom", cluster.get("super_atom"))
            filled += 1
    io_utils.save_json(CLUSTERS, clusters)
    _write_super_md(clusters)
    print(f"[cluster] applied names to {filled}/{len(clusters['clusters'])} clusters")


def _write_super_md(clusters: dict) -> None:
    lines = ["# Super Atoms", "", "| id | name | size | diet mix | super atom |", "|---|---|---|---|---|"]
    for c in sorted(clusters["clusters"], key=lambda x: x["id"]):
        mix = ", ".join(f"{k}:{v}" for k, v in sorted(c.get("diet_mix", {}).items()))
        lines.append(
            f"| {c['id']} | {c.get('name') or '_(unnamed)_'} | {c['size']} | {mix} | "
            f"{c.get('super_atom') or ''} |"
        )
    SUPER_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_digest(clusters: dict, atoms: list[dict], matrix: np.ndarray, index: dict[str, int]) -> None:
    digest = {"clusters": []}
    for c in sorted(clusters["clusters"], key=lambda x: x["id"]):
        rows = [index[a] for a in c["atom_ids"] if a in index]
        if not rows:
            continue
        centroid = stats.normalize_rows(matrix[rows].mean(axis=0, keepdims=True))[0]
        sims = stats.normalize_rows(matrix[rows]) @ centroid
        order = np.argsort(-sims)[:6]
        by_id = {a["id"]: a for a in atoms}
        samples = []
        for r in order:
            atom = by_id.get(c["atom_ids"][r])
            if atom:
                samples.append(
                    {"id": atom["id"], "kind": atom["kind"], "text": atom["text"][:260]}
                )
        digest["clusters"].append(
            {
                "id": c["id"],
                "size": c["size"],
                "diet_mix": c["diet_mix"],
                "sample_atoms": samples,
            }
        )
    io_utils.save_json(DIGEST, digest)


def _reuse_names(new_clusters: list[dict], old_clusters: list[dict], matrix=None,
                 index=None) -> dict[str, dict]:
    """Reuse an old name when a new cluster overlaps its atoms or centroid."""
    old = []
    seen_members = set()
    for c in old_clusters:
        if not c.get("name") or c.get("name_origin") == "keyword-fallback":
            continue
        key = tuple(sorted(c.get("atom_ids", [])))
        if key in seen_members:
            continue
        seen_members.add(key)
        old.append((set(c.get("atom_ids", [])), c))
    reused = {}
    used_names: set[str] = set()
    old_cents = {}
    if matrix is not None and index is not None:
        for _members, c in old:
            rows = [index[a] for a in c.get("atom_ids", []) if a in index]
            if rows:
                vec = matrix[rows].mean(axis=0, keepdims=True)
                old_cents[c["id"]] = (vec / max(float(np.linalg.norm(vec)), 1e-9))[0]
    for c in new_clusters:
        member = set(c.get("atom_ids", []))
        candidates = []
        for old_members, old_cluster in old:
            if old_cluster.get("name") in used_names:
                continue
            if not member or not old_members:
                continue
            overlap = len(member & old_members) / len(member | old_members)
            candidates.append((overlap, "jaccard", old_cluster))
        best = max(candidates, key=lambda x: x[0]) if candidates else (0.0, "jaccard", None)
        chosen = best if best[0] >= 0.25 else None
        if chosen is None and old_cents and matrix is not None and index is not None:
            rows = [index[a] for a in c.get("atom_ids", []) if a in index]
            if rows:
                vec = matrix[rows].mean(axis=0, keepdims=True)
                new_cent = (vec / max(float(np.linalg.norm(vec)), 1e-9))[0]
                cent_scores = []
                for old_members, old_cluster in old:
                    if old_cluster.get("name") in used_names or old_cluster["id"] not in old_cents:
                        continue
                    cent_scores.append((float(np.dot(new_cent, old_cents[old_cluster["id"]])), "centroid", old_cluster))
                if cent_scores:
                    top = max(cent_scores, key=lambda x: x[0])
                    if top[0] >= 0.78:
                        chosen = top
        if chosen is not None:
            _score, origin, old_cluster = chosen
            c["name"] = old_cluster["name"]
            c["super_atom"] = old_cluster.get("super_atom")
            c["name_origin"] = f"reused:{old_cluster['id']} ({origin} {_score:.2f})"
            used_names.add(c["name"])
            reused[str(c["id"])] = {
                "name": c["name"],
                "super_atom": c.get("super_atom"),
                "reused_from": old_cluster["id"],
                "origin": origin,
                "score": round(float(_score), 3),
            }
    print(f"[cluster] reused names for {len(reused)}/{len(new_clusters)} clusters")
    return reused


def _keyword_name(texts: list[str]) -> tuple[str, str]:
    import re
    from collections import Counter

    stop = set(
        "the and for are but not you all any can had her was one our out day get has him his "
        "how man new now old see two way who boy did its let put say she too use that with have "
        "this will your from they know want been good much some time very when come here just "
        "like long make many more only over such take than them well were what where which while "
        "would there their about into then these those also story atom mechanic".split()
    )
    counts: Counter = Counter()
    for text in texts:
        for word in re.findall(r"[a-zA-Z][a-zA-Z'-]{3,}", text.lower()):
            if word not in stop:
                counts[word] += 1
    top = [w for w, _ in counts.most_common(3)]
    name = " ".join(top).title() if top else "Unnamed Cluster"
    super_atom = (texts[0][:240] if texts else "A newly formed cluster awaiting a mechanism summary.")
    return name, super_atom


def _auto_name_clusters(
    new_clusters: list[dict],
    batch_size: int = 6,
    limit: int | None = None,
    on_batch=None,
) -> dict[str, dict]:
    """LLM-name clusters that did not inherit a name. Falls back to keywords."""
    from . import llm

    atoms = io_utils.load_json(ATOMS, []) or []
    by_id = {a["id"]: a for a in atoms}
    pending = [c for c in new_clusters if not c.get("name")]
    if limit is not None and limit > 0:
        pending = sorted(pending, key=lambda c: -len(c.get("atom_ids", [])))[:limit]
    if not pending:
        return {}
    prompt_path = io_utils.ROOT / "prompts" / "cluster_names.md"
    template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    generated: dict[str, dict] = {}
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        blocks = []
        for c in batch:
            sample = []
            for aid in c.get("atom_ids", [])[:5]:
                atom = by_id.get(aid)
                if atom:
                    sample.append(f"- {atom['text'][:240]}")
            blocks.append(f"CLUSTER {c['id']}\n" + "\n".join(sample))
        prompt = template.replace("{clusters}", "\n\n".join(blocks))
        ok = False
        try:
            raw = llm.complete_json(prompt, stage_name="collector")
            items = raw.get("clusters") if isinstance(raw, dict) else raw
            if isinstance(items, list):
                by_cluster = {}
                for item in items:
                    if isinstance(item, dict) and item.get("id") is not None:
                        try:
                            by_cluster[int(item["id"])] = item
                        except Exception:
                            continue
                for c in batch:
                    item = by_cluster.get(int(c["id"]))
                    if item and str(item.get("name") or "").strip():
                        c["name"] = str(item["name"]).strip()[:70]
                        c["super_atom"] = str(item.get("super_atom") or "").strip()[:320]
                        c["name_origin"] = "llm"
                        generated[str(c["id"])] = {
                            "name": c["name"],
                            "super_atom": c.get("super_atom"),
                        }
                        ok = True
        except Exception as exc:  # noqa: BLE001
            print(f"[cluster] naming batch failed: {type(exc).__name__}: {exc}", flush=True)
        for c in batch:
            if not c.get("name"):
                texts = [by_id[aid]["text"] for aid in c.get("atom_ids", []) if aid in by_id]
                name, super_atom = _keyword_name(texts)
                c["name"] = name
                c["super_atom"] = super_atom
                c["name_origin"] = "keyword-fallback"
                generated[str(c["id"])] = {"name": name, "super_atom": super_atom}
        if ok:
            print(f"[cluster] named {len(batch)} clusters with the LLM", flush=True)
        if on_batch is not None:
            on_batch()
    return generated


def name_clusters(limit: int | None = None) -> None:
    """Upgrade keyword/unnamed clusters with the LLM (safe to re-run)."""
    clusters_doc = io_utils.load_json(CLUSTERS, {}) or {}
    clusters = clusters_doc.get("clusters", [])
    if not clusters:
        raise SystemExit("clusters/clusters.json missing")
    fallback = [
        c
        for c in clusters
        if not c.get("name") or c.get("name_origin") == "keyword-fallback"
    ]
    if not fallback:
        print("[cluster] every cluster already has a reused or LLM name")
        return
    target = len(fallback) if limit is None else min(limit, len(fallback))
    # Only detach the clusters this pass will actually rename. A limited pass must
    # never leave the rest of the space unnamed.
    selected = sorted(fallback, key=lambda c: -len(c.get("atom_ids", [])))[:target]
    for c in selected:
        c["name"] = None
        c["super_atom"] = None
    print(f"[cluster] naming {target} of {len(fallback)} fallback cluster(s) with the LLM")

    def save_progress() -> None:
        names = io_utils.load_json(NAMES, {}) or {}
        for c in selected:
            if c.get("name"):
                names[str(c["id"])] = {
                    "name": c["name"],
                    "super_atom": c.get("super_atom"),
                }
        io_utils.save_json(NAMES, names)
        io_utils.save_json(CLUSTERS, clusters_doc)

    generated = _auto_name_clusters(selected, limit=None, on_batch=save_progress)
    save_progress()
    _write_super_md(clusters_doc)
    print(f"[cluster] named {sum(1 for c in clusters if c.get('name'))}/{len(clusters)} clusters")


def run(seed: int = 42, min_size: int = 3, lo: int = 60, hi: int = 120,
        apply_names_only: bool = False, force_embed: bool = False,
        auto_name: bool = False) -> None:
    if apply_names_only:
        _apply_names()
        return

    atoms = io_utils.load_json(ATOMS)
    if not atoms:
        raise SystemExit("atoms/all.json missing or empty — run atomization first")
    old_clusters = (io_utils.load_json(CLUSTERS, {}) or {}).get("clusters", [])
    v1_path = io_utils.ROOT / "clusters" / "clusters_v1.json"
    if v1_path.exists():
        old_clusters = old_clusters + ((io_utils.load_json(v1_path, {}) or {}).get("clusters", []))
    atom_ids = [a["id"] for a in atoms]
    texts = [a["text"] for a in atoms]
    matrix, method = embeddings.embed_atoms(atom_ids, texts, force=force_embed)
    index = {a: i for i, a in enumerate(atom_ids)}

    print(f"[cluster] {len(atoms)} atoms, dim {matrix.shape[1]}, method {method}", flush=True)
    distances = pdist(matrix, metric="cosine")
    tree = linkage(distances, method="average")

    sweep = []
    best = None
    for t in np.arange(0.20, 0.981, 0.01):
        labels = fcluster(tree, t=float(t), criterion="distance")
        labels, moved = _merge_small(labels, matrix, min_size)
        counts = np.bincount(labels)
        counts = counts[counts > 0]
        n_clusters = int(len(counts))
        sweep.append(
            {
                "threshold": round(float(t), 3),
                "clusters": n_clusters,
                "merged": moved,
                "max_size": int(counts.max()) if len(counts) else 0,
            }
        )
        if lo <= n_clusters <= hi:
            # Prefer a balance of many clusters AND no single giant cluster.
            score = (int(counts.max()) if len(counts) else 10**9, abs(n_clusters - 90))
            if best is None or score < best[0]:
                best = (score, float(t), labels.copy(), moved)

    if best is None:
        closest = min(sweep, key=lambda s: abs(s["clusters"] - 90))
        t = closest["threshold"]
        labels = fcluster(tree, t=t, criterion="distance")
        labels, moved = _merge_small(labels, matrix, min_size)
        best = (abs(closest["clusters"] - 90), t, labels, moved)
        print(
            f"[cluster] WARNING: no threshold hit {lo}-{hi}; using closest "
            f"({closest['clusters']} clusters at t={t})",
            flush=True,
        )

    _, threshold, labels, moved = best
    uniq = np.unique(labels)
    # deterministic remap: biggest clusters first, ties by smallest member id
    ordered = sorted(uniq, key=lambda u: (-int((labels == u).sum()), str(min(np.array(atom_ids)[labels == u]))))
    remap = {u: i for i, u in enumerate(ordered)}
    labels = np.array([remap[u] for u in labels])

    atoms_out = []
    clusters_out = []
    for new_id in range(len(ordered)):
        mask = labels == new_id
        member_ids = sorted(str(a) for a in np.array(atom_ids)[mask])
        diet_mix: dict[str, int] = {}
        for a in atoms:
            if a["id"] in member_ids:
                diet_mix[a["diet"]] = diet_mix.get(a["diet"], 0) + 1
        clusters_out.append(
            {
                "id": new_id,
                "name": None,
                "super_atom": None,
                "atom_ids": member_ids,
                "size": int(mask.sum()),
                "diet_mix": diet_mix,
            }
        )
    member_map = {}
    for c in clusters_out:
        for aid in c["atom_ids"]:
            member_map[aid] = c["id"]
    for a in atoms:
        a["cluster"] = member_map.get(a["id"])
        atoms_out.append(a)

    clusters_doc = {"clusters": clusters_out}
    reused = _reuse_names(clusters_out, old_clusters, matrix, index)
    if auto_name:
        generated = _auto_name_clusters(clusters_out)
    else:
        generated = {}
        atoms_by_id = {a["id"]: a for a in atoms_out}
        for c in clusters_out:
            if not c.get("name"):
                texts = [atoms_by_id[aid]["text"] for aid in c.get("atom_ids", []) if aid in atoms_by_id]
                name, super_atom = _keyword_name(texts)
                c["name"] = name
                c["super_atom"] = super_atom
                c["name_origin"] = "keyword-fallback"
                generated[str(c["id"])] = {"name": name, "super_atom": super_atom}
    names = io_utils.load_json(NAMES, {}) or {}
    names.update(reused)
    names.update(generated)
    io_utils.save_json(NAMES, names)
    named = sum(1 for c in clusters_out if c.get("name"))
    print(f"[cluster] {named}/{len(clusters_out)} clusters named (reuse + {'LLM' if auto_name else 'keyword'})")

    io_utils.save_json(ATOMS, atoms_out)
    io_utils.save_json(CLUSTERS, clusters_doc)
    _write_super_md(clusters_doc)
    _write_digest(clusters_doc, atoms_out, matrix, index)

    sizes = [c["size"] for c in clusters_out]
    coverage = float(len(member_map)) / len(atoms)
    meta = io_utils.load_json(META, {}) or {}
    meta.update(
        {
            "embedding_method": method,
            "cluster_seed": seed,
            "linkage": "average",
            "metric": "cosine",
            "distance_threshold": round(threshold, 3),
            "min_cluster_size": min_size,
            "n_clusters": len(clusters_out),
            "n_atoms": len(atoms),
            "coverage": round(coverage, 4),
            "residual_unclustered": 0,
            "orphans_merged": int(moved),
            "sizes": {
                "min": int(min(sizes)),
                "median": float(np.median(sizes)),
                "max": int(max(sizes)),
            },
            "threshold_sweep": sweep,
        }
    )
    io_utils.save_json(META, meta)
    print(
        f"[cluster] {len(clusters_out)} clusters, sizes {min(sizes)}-{max(sizes)} "
        f"(median {np.median(sizes):.0f}), coverage {coverage:.1%}, threshold {threshold:.2f}",
        flush=True,
    )
    print(f"[cluster] digest written to {DIGEST} — name clusters via clusters/names.json", flush=True)
