"""Candidate generation + scoring + fusion (§11)."""

from __future__ import annotations

import math

import numpy as np

from . import io_utils, stats

ROOT = io_utils.ROOT
ATOMS = ROOT / "atoms" / "all.json"
CLUSTERS = ROOT / "clusters" / "clusters.json"
EMB = ROOT / "clusters" / "embeddings.npz"
WELLS = ROOT / "clusters" / "gravity_wells.json"
CAND = ROOT / "candidates"

FORMULA = "(1-beta)*z(coherence) + beta*z(unavailability)"
COH_DEF = "0.5*z(mean_pairwise_cosine) + 0.5*z(cooccurrence_bridging)"
UNAV_DEF = "0.65*z(pair_rarity) + 0.35*z(cliche_distance)"


def _load():
    atoms = io_utils.load_json(ATOMS)
    clusters = io_utils.load_json(CLUSTERS)
    if not atoms or not clusters:
        raise SystemExit("atoms/all.json and clusters/clusters.json are required")
    data = np.load(EMB, allow_pickle=True)
    ids = [str(x) for x in data["atom_ids"]]
    matrix = data["matrix"].astype(np.float64)
    index = {a: i for i, a in enumerate(ids)}
    return atoms, clusters, matrix, index


def _centroids(clusters, matrix, index):
    cents = {}
    exemplars = {}
    for c in clusters["clusters"]:
        rows = [index[a] for a in c["atom_ids"] if a in index]
        if not rows:
            continue
        centroid = stats.normalize_rows(matrix[rows].mean(axis=0, keepdims=True))[0]
        cents[c["id"]] = centroid
        sims = stats.normalize_rows(matrix[rows]) @ centroid
        best = rows[int(np.argmax(sims))]
        exemplars[c["id"]] = best
    return cents, exemplars


def _bridge(clusters, atoms):
    atom_by_id = {a["id"]: a for a in atoms}
    sources = {}
    for c in clusters["clusters"]:
        sources[c["id"]] = {
            atom_by_id[aid]["source"] for aid in c["atom_ids"] if aid in atom_by_id
        }
    ids = sorted(sources)
    pos = {cid: p for p, cid in enumerate(ids)}
    n = len(ids)
    B = np.zeros((n, n), dtype=np.int32)
    for i in range(n):
        for j in range(i + 1, n):
            value = len(sources[ids[i]] & sources[ids[j]])
            B[i, j] = B[j, i] = value
    return ids, pos, B


def _gravity_wells(clusters, atoms, top=12):
    atom_by_id = {a["id"]: a for a in atoms}
    counts = {}
    names = {}
    for c in clusters["clusters"]:
        diet_a_sources = {
            atom_by_id[aid]["source"]
            for aid in c["atom_ids"]
            if aid in atom_by_id and atom_by_id[aid]["diet"] == "A"
        }
        counts[c["id"]] = len(diet_a_sources)
        names[c["id"]] = c.get("name")
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    wells = [
        {"cluster_id": cid, "name": names.get(cid), "diet_a_source_count": n}
        for cid, n in ranked
    ]
    io_utils.save_json(
        WELLS,
        {
            "method": "top-12 clusters by number of diet-A sources holding member atoms",
            "wells": wells,
        },
    )
    return wells


def _generate(ids, cents, B, n_sources, n_draws, seed, k, anchor_positions=None, min_anchor=1,
              max_pool=6000):
    rng = np.random.default_rng(seed)
    K = len(ids)
    C = np.vstack([cents[i] for i in ids])
    bridged = [(i, j) for i in range(K) for j in range(i + 1, K) if B[i, j] >= 1]
    if not bridged:
        bridged = [(i, j) for i in range(K) for j in range(i + 1, K)]
    pair_cache: dict[tuple[int, int], np.ndarray] = {}

    anchor_positions = set(anchor_positions or ())
    anchor_list = sorted(anchor_positions)
    non_anchor = [i for i in range(K) if i not in anchor_positions]

    def pair_sims(i, j):
        key = (min(i, j), max(i, j))
        if key not in pair_cache:
            mean = stats.normalize_rows((C[i] + C[j])[None, :])[0]
            pair_cache[key] = C @ mean
        return pair_cache[key]

    seen: set[tuple[int, ...]] = set()
    for _ in range(n_draws):
        r = rng.random()
        combo: list[int] = []
        if k == 2:
            if r < 0.6:
                i, j = bridged[int(rng.integers(len(bridged)))]
                combo = [i, j]
            else:
                combo = [int(x) for x in rng.choice(K, size=2, replace=False)]
        elif r < 0.5:
            i, j = bridged[int(rng.integers(len(bridged)))]
            sims = pair_sims(i, j)
            far = np.argsort(sims)[: max(3, K // 4)]
            third = int(far[int(rng.integers(len(far)))])
            combo = [i, j, third]
        elif r < 0.75:
            i, j = bridged[int(rng.integers(len(bridged)))]
            sims = pair_sims(i, j)
            lo, hi = np.quantile(sims, [1.0 / 3.0, 2.0 / 3.0])
            mid = np.where((sims >= lo) & (sims <= hi))[0]
            third = int(mid[int(rng.integers(len(mid)))]) if len(mid) else int(rng.integers(K))
            combo = [i, j, third]
        else:
            combo = [int(x) for x in rng.choice(K, size=k, replace=False)]
        if k > len(combo):
            pool = [x for x in range(K) if x not in combo]
            extra = [int(x) for x in rng.choice(pool, size=k - len(combo), replace=False)]
            combo = combo + extra
        if len(set(combo)) != k:
            continue
        seen.add(tuple(sorted(combo)))

    # Targeted brief-anchor generation: every candidate must carry at least
    # `min_anchor` brief-relevant cluster; the remaining slots stay unrelated.
    if anchor_list and k >= 2:
        n_anchor_slots = min(len(anchor_list), max(min_anchor, 1))
        n_anchor_slots = min(n_anchor_slots, k - 1) if k > 1 else 1
        for _ in range(n_draws * 2):
            take = n_anchor_slots
            if take < len(anchor_list) and rng.random() < 0.5:
                take = min(len(anchor_list), take + 1)
            take = min(take, max(1, k - 1))  # always leave at least one unrelated slot
            chosen = [int(x) for x in rng.choice(anchor_list, size=take, replace=False)]
            need = k - take
            if need > 0:
                if not non_anchor:
                    continue
                extra = [int(x) for x in rng.choice(non_anchor, size=need, replace=False)]
                chosen += extra
            if len(set(chosen)) != k:
                continue
            seen.add(tuple(sorted(chosen)))

    combos = np.array(sorted(seen), dtype=np.int64)
    if len(combos) == 0:
        raise SystemExit("candidate generation produced no sets")
    vecs = C[combos]
    sims = []
    for a in range(k):
        for b in range(a + 1, k):
            sims.append(np.sum(vecs[:, a] * vecs[:, b], axis=1))
    mean_cos = np.mean(np.vstack(sims), axis=0)
    keep = mean_cos >= 0.08
    combos = combos[keep]
    if len(combos) > max_pool:
        pick = rng.choice(len(combos), size=max_pool, replace=False)
        combos = combos[np.sort(pick)]
    return combos


def _filter_combos(combos, pos, anchor_ids, past_combos, max_overlap, min_anchor):
    """Keep sets with enough brief anchors and low overlap with output history."""
    if len(combos) == 0:
        return combos
    keep = np.ones(len(combos), dtype=bool)
    anchor_positions = {pos[a] for a in (anchor_ids or []) if a in pos}
    if anchor_positions:
        hit = np.isin(combos, list(anchor_positions)).sum(axis=1)
        keep &= hit >= max(1, min_anchor)
        keep &= hit <= min(2, combos.shape[1] - 1)
    if past_combos:
        position_to_id = {p: cid for cid, p in pos.items()}
        overlaps = np.zeros(len(combos), dtype=np.float64)
        for i, combo in enumerate(combos):
            a = {position_to_id[int(p)] for p in combo}
            best = 0.0
            for prior in past_combos:
                b = set(prior)
                if a and b:
                    best = max(best, len(a & b) / len(a | b))
            overlaps[i] = best
        keep &= overlaps <= max_overlap
    return combos[keep]


def _score(combos, C, B, n_sources, wells_cent, k):
    vecs = C[combos]
    sims = []
    for a in range(k):
        for b in range(a + 1, k):
            sims.append(np.sum(vecs[:, a] * vecs[:, b], axis=1))
    coh_embed = np.mean(np.vstack(sims), axis=0)

    total_pairs = k * (k - 1) // 2
    cooc = np.zeros(len(combos), dtype=np.float64)
    rarity_terms = []
    for a in range(k):
        for b in range(a + 1, k):
            bridge = B[combos[:, a], combos[:, b]].astype(np.float64)
            cooc += (bridge >= 1).astype(np.float64)
            rarity_terms.append(np.log1p(n_sources / (1.0 + bridge)))
    coh_cooc = cooc / (total_pairs + 1.0)
    pair_rarity = np.mean(np.vstack(rarity_terms), axis=0)

    set_cent = stats.normalize_rows(np.mean(vecs, axis=1))
    cliche_distance = 1.0 - np.max(set_cent @ wells_cent.T, axis=1)

    z_coh_embed = stats.zscore(coh_embed)
    z_coh_cooc = stats.zscore(coh_cooc)
    coherence = 0.5 * z_coh_embed + 0.5 * z_coh_cooc
    z_rarity = stats.zscore(pair_rarity)
    z_cliche = stats.zscore(cliche_distance)
    unavailability = 0.65 * z_rarity + 0.35 * z_cliche

    return {
        "coh_embed": coh_embed,
        "coh_cooc": coh_cooc,
        "pair_rarity": pair_rarity,
        "cliche_distance": cliche_distance,
        "coherence": coherence,
        "unavailability": unavailability,
        "z_coherence": stats.zscore(coherence),
        "z_unavailability": stats.zscore(unavailability),
    }


def _sort_keys(combos):
    power = 1000 ** np.arange(combos.shape[1] - 1, -1, -1)
    return (combos * power).sum(axis=1)


def _top_indices(fusion, combos, top_k):
    keys = _sort_keys(combos)
    order = np.lexsort((keys, -fusion))
    return order[:top_k]


def run(seed: int = 42, k: int = 3, betas=(0.5, 0.7, 0.85), top_k: int = 50,
        n_draws: int = 20000, output_dir: str | None = None,
        anchor_ids: list[int] | None = None,
        past_combos: list[tuple[int, ...]] | None = None,
        max_history_overlap: float = 0.4,
        min_anchor: int = 1) -> str:
    atoms, clusters, matrix, index = _load()
    cents, exemplar_rows = _centroids(clusters, matrix, index)
    ids, pos, B = _bridge(clusters, atoms)
    n_sources = len({a["source"] for a in atoms})
    wells = _gravity_wells(clusters, atoms)
    wells_cent = stats.normalize_rows(np.vstack([cents[w["cluster_id"]] for w in wells]))
    C = np.vstack([cents[i] for i in ids])
    id_to_name = {c["id"]: c.get("name") or f"cluster-{c['id']}" for c in clusters["clusters"]}
    row_to_atom = {}
    emb_ids = list(np.load(EMB, allow_pickle=True)["atom_ids"])
    for cid, row in exemplar_rows.items():
        row_to_atom[cid] = str(emb_ids[row])
    atom_text = {a["id"]: a["text"] for a in atoms}

    print(
        f"[sample] k={k}, seed={seed}, draws={n_draws}, clusters={len(ids)}, "
        f"sources={n_sources}, bridged pairs={int((B >= 1).sum() // 2)}, "
        f"anchors={len(anchor_ids or [])}, history={len(past_combos or [])}",
        flush=True,
    )

    anchor_positions = {pos[a] for a in (anchor_ids or []) if a in pos}
    max_pool = 12000 if (anchor_positions or past_combos) else 6000
    combos = None
    attempts = 0
    while attempts < 5:
        raw = _generate(
            ids,
            cents,
            B,
            n_sources,
            n_draws * (2 ** attempts),
            seed + attempts,
            k,
            anchor_positions=anchor_positions,
            min_anchor=min_anchor,
            max_pool=max_pool,
        )
        combos = _filter_combos(
            raw,
            pos,
            anchor_ids or [],
            past_combos or [],
            max_history_overlap,
            min_anchor,
        )
        if len(combos) >= 3000:
            break
        attempts += 1
        print(
            f"[sample] only {len(combos)} sets after anchor/history filters; increasing draws",
            flush=True,
        )
    if combos is None or len(combos) < 3000:
        raise SystemExit(
            "Could not reach 3000 distinct candidate sets after brief-anchor and "
            "ledger filters — loosen --max-history-overlap or run with fewer anchors"
        )

    scored = _score(combos, C, B, n_sources, wells_cent, k)
    run_name = output_dir or io_utils.run_id(seed)
    run_dir = CAND / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    coh = scored["coherence"]
    unav = scored["unavailability"]
    z_coh = scored["z_coherence"]
    z_unav = scored["z_unavailability"]

    rank_coh = np.empty(len(combos), dtype=np.int64)
    rank_unav = np.empty(len(combos), dtype=np.int64)
    order_coh = np.argsort(-coh)
    order_unav = np.argsort(-unav)
    rank_coh[order_coh] = np.arange(1, len(combos) + 1)
    rank_unav[order_unav] = np.arange(1, len(combos) + 1)

    config = {
        "run_id": run_name,
        "k": k,
        "top_k": top_k,
        "n_pool": int(len(combos)),
        "n_draws": int(n_draws),
        "seed": seed,
        "formula": FORMULA,
        "coherence_def": COH_DEF,
        "unavailability_def": UNAV_DEF,
        "n_sources": n_sources,
        "n_clusters": len(ids),
        "corr_coherence_unavailability": round(stats.pearson(coh, unav), 4),
        "gravity_wells": [w["cluster_id"] for w in wells],
        "betas": list(betas),
        "anchor_ids": list(anchor_ids or []),
        "brief_fit_rule": f"at least {max(1, min_anchor)} anchor cluster(s) per candidate",
        "max_history_overlap": max_history_overlap,
        "history_combos_excluded": len(past_combos or []),
        "floor_applied": False,
        "per_beta": {},
    }

    # acceptance check at beta 0.7 (or nearest requested beta)
    check_beta = min(betas, key=lambda b: abs(b - 0.7))
    check_fusion = (1.0 - check_beta) * z_coh + check_beta * z_unav
    check_top = _top_indices(check_fusion, combos, top_k)
    floor_applied = False
    if float(np.median(z_coh[check_top])) < 0.0:
        floor_applied = True
        keep = z_coh >= -0.5
        print(
            "[sample] top sets skewed incoherent — applying coherence floor z>=-0.5",
            flush=True,
        )
        combos = combos[keep]
        for key in scored:
            scored[key] = scored[key][keep]
        rank_coh = rank_coh[keep]
        rank_unav = rank_unav[keep]
        coh, unav = scored["coherence"], scored["unavailability"]
        z_coh, z_unav = scored["z_coherence"], scored["z_unavailability"]
        config["n_pool"] = int(len(combos))
        config["floor_applied"] = True

    for beta in betas:
        fusion = (1.0 - beta) * z_coh + beta * z_unav
        top = _top_indices(fusion, combos, top_k)
        candidates = []
        for rank, idx in enumerate(top, start=1):
            cids = [int(x) for x in combos[idx]]
            overlap = 0.0
            if past_combos:
                a = set(cids)
                for prior in past_combos:
                    b = set(prior)
                    if a and b:
                        overlap = max(overlap, len(a & b) / len(a | b))
            candidates.append(
                {
                    "rank_fused": rank,
                    "cluster_ids": cids,
                    "cluster_names": [id_to_name[c] for c in cids],
                    "exemplar_atoms": [atom_text.get(row_to_atom[c], "") for c in cids],
                    "brief_anchors": sorted({int(x) for x in cids if int(x) in anchor_positions}),
                    "ledger_overlap": round(float(overlap), 4),
                    "coherence_raw": {
                        "mean_pairwise_cosine": round(float(scored["coh_embed"][idx]), 5),
                        "cooccurrence_bridging": round(float(scored["coh_cooc"][idx]), 5),
                    },
                    "unavailability_raw": {
                        "pair_rarity": round(float(scored["pair_rarity"][idx]), 5),
                        "cliche_distance": round(float(scored["cliche_distance"][idx]), 5),
                    },
                    "z_coherence": round(float(z_coh[idx]), 4),
                    "z_unavailability": round(float(z_unav[idx]), 4),
                    "fusion": round(float(fusion[idx]), 4),
                    "rank_coherence": int(rank_coh[idx]),
                    "rank_unavailability": int(rank_unav[idx]),
                }
            )
        payload = {
            "config": {
                "run_id": run_name,
                "k": k,
                "beta": beta,
                "top_k": top_k,
                "n_pool": int(len(combos)),
                "seed": seed,
                "formula": FORMULA,
                "coherence_def": COH_DEF,
                "unavailability_def": UNAV_DEF,
            },
            "candidates": candidates,
        }
        beta_dir = run_dir / f"beta_{beta:g}"
        io_utils.save_json(beta_dir / "results.json", payload)
        top20 = fusion[top[:20]]
        config["per_beta"][f"{beta:g}"] = {
            "top20_fusion_min": round(float(np.min(top20)), 4),
            "top20_fusion_max": round(float(np.max(top20)), 4),
            "top1_fusion": round(float(fusion[top[0]]), 4),
        }
        print(
            f"[sample] beta={beta:g}: top1 fusion={fusion[top[0]]:.3f}, "
            f"top20 range [{np.min(top20):.3f}, {np.max(top20):.3f}] -> {beta_dir}",
            flush=True,
        )

    # exemplar text lookup for judging convenience
    config["exemplar_texts"] = {
        str(cid): atom_text.get(row_to_atom[cid], "") for cid in row_to_atom
    }
    io_utils.save_json(run_dir / "config.json", config)
    print(
        f"[sample] pool={len(combos)}, corr(coherence,unavailability)="
        f"{config['corr_coherence_unavailability']}, run={run_name}",
        flush=True,
    )
    return run_name
