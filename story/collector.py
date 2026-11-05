"""Autonomous research collector for StoryGen.

Given a free-form brief, this module:

1. parses the brief into hard/soft constraints and search intents (LLM),
2. searches Wikipedia and Project Gutenberg for *fresh* sources,
3. atomizes the fetched material with the LLM,
4. appends the atoms to the living atom space and assigns them to clusters.

Everything is cached in ``corpus/``, ``atoms/`` and the SQLite ledger, so a
source is never fetched twice.
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from . import embeddings, io_utils, ledger, llm

ROOT = io_utils.ROOT
CORPUS = ROOT / "corpus"
MANIFEST = CORPUS / "manifest.json"
ATOMS = ROOT / "atoms" / "all.json"
CLUSTERS = ROOT / "clusters" / "clusters.json"
NAMES = ROOT / "clusters" / "names.json"
META = ROOT / "clusters" / "meta.json"

USER_AGENT = "StoryGen/1.2 (local autonomous story research; contact: local user)"

# Domains deliberately far from the usual AI-story gravity well. Used when a
# brief does not ask for enough foreign material of its own.
FOREIGN_DOMAINS = [
    "deep sea bioluminescence",
    "medieval beekeeping",
    "Soviet radio cryptography",
    "desert kites archaeology",
    "mushroom foraging folklore",
    "Antarctic supply logistics",
    "traditional Japanese papermaking",
    "tidal clock mechanisms",
    "nomadic falconry",
    "cathedral bell casting",
    "peat bog preservation",
    "volcanic glass toolmaking",
    "seed vaults",
    "lighthouse keepers",
    "migratory bird ringing",
    "river ferry law",
    "glacier moulins",
    "salt caravan routes",
    "insect metamorphosis",
    "cartographic errors",
]

_DEFAULT_CONSTRAINTS = {
    "genre": "",
    "tone": "",
    "setting": "",
    "time_period": "",
    "must_include": [],
    "must_avoid": [],
    "banned_tropes": [],
    "themes": [],
    "search_queries": [],
    "foreign_queries": [],
    "hard_constraints_summary": "",
    "soft_constraints_summary": "",
    "audience": "",
}


# ---------------------------------------------------------------------------
# Small HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------

def _get(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_json(url: str, timeout: float = 30.0) -> Any:
    return json.loads(_get(url, timeout=timeout).decode("utf-8", errors="replace"))


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Brief parsing
# ---------------------------------------------------------------------------

def parse_brief(brief: str, provider: str | None = None) -> dict[str, Any]:
    """Turn a one-line or novel-length brief into structured constraints."""
    prompt = f"""You are the intake editor for an automated story engine. Parse the brief
into JSON. Preserve EVERY explicit requirement. Do not invent constraints the
brief does not state. If the brief is vague, leave fields empty and choose
surprising search directions.

BRIEF:
\"\"\"{brief.strip()}\"\"\"

Return ONLY JSON with this exact shape:
{{
  "genre": "short label or empty",
  "tone": "short label or empty",
  "setting": "short label or empty",
  "time_period": "short label or empty",
  "audience": "short label or empty",
  "must_include": ["explicit people/places/objects/events the brief requires"],
  "must_avoid": ["explicit things the brief forbids"],
  "banned_tropes": ["tropes that would make this feel generic for this brief"],
  "themes": ["2-5 abstract themes"],
  "search_queries": ["3-6 web search queries for relevant fiction/folklore/history"],
  "foreign_queries": ["2-4 web search queries for deliberately distant, unrelated domains"],
  "hard_constraints_summary": "one sentence listing non-negotiables",
  "soft_constraints_summary": "one sentence listing tone/style wishes"
}}
"""
    try:
        data = llm.complete_json(prompt, stage_name="collector", provider=provider)
        if isinstance(data, list) and data:
            data = data[0]
        if not isinstance(data, dict):
            raise ValueError("brief parser did not return an object")
    except Exception as exc:  # noqa: BLE001 - fall back to a usable heuristic
        print(f"[collector] brief parse failed ({type(exc).__name__}: {exc}); using heuristic", flush=True)
        data = _heuristic_brief(brief)

    out = dict(_DEFAULT_CONSTRAINTS)
    for key, value in data.items():
        if key in out:
            out[key] = value
    for key in ("must_include", "must_avoid", "banned_tropes", "themes", "search_queries", "foreign_queries"):
        value = out.get(key)
        if isinstance(value, str):
            out[key] = [x.strip() for x in re.split(r"[,;]\s*", value) if x.strip()]
        elif not isinstance(value, list):
            out[key] = []
    if not out["search_queries"]:
        out["search_queries"] = _keywords_to_queries(brief)
    if not out["foreign_queries"]:
        out["foreign_queries"] = _pick_foreign_queries(brief, 3)
    out["brief"] = brief.strip()
    print(
        "[collector] brief: "
        + (out.get("hard_constraints_summary") or out.get("genre") or "open brief")
        + f" | searches={len(out['search_queries'])} relevant / {len(out['foreign_queries'])} foreign",
        flush=True,
    )
    return out


def _heuristic_brief(brief: str) -> dict[str, Any]:
    data = dict(_DEFAULT_CONSTRAINTS)
    data["search_queries"] = _keywords_to_queries(brief)
    data["foreign_queries"] = _pick_foreign_queries(brief, 3)
    lower = brief.lower()
    for word in ("horror", "romance", "comedy", "western", "fantasy", "science fiction", "thriller", "mystery"):
        if word in lower:
            data["genre"] = word
            break
    data["hard_constraints_summary"] = brief.strip()
    return data


def _keywords_to_queries(brief: str) -> list[str]:
    words = [
        w
        for w in re.findall(r"[a-zA-Z][a-zA-Z'-]{3,}", brief.lower())
        if w not in {"story", "about", "with", "that", "this", "have", "want", "where", "when", "must", "should", "would"}
    ]
    seen: list[str] = []
    for w in words:
        if w not in seen:
            seen.append(w)
    queries = []
    if len(seen) >= 2:
        queries.append(" ".join(seen[:4]))
        queries.append(" ".join(seen[2:6]))
    elif seen:
        queries.append(seen[0])
    queries.extend(_pick_foreign_queries(brief, 2))
    return queries[:5] or ["speculative fiction"]


def _pick_foreign_queries(brief: str, n: int) -> list[str]:
    lower = brief.lower()
    pool = [q for q in FOREIGN_DOMAINS if q not in lower]
    if not pool:
        pool = FOREIGN_DOMAINS
    start = abs(hash(brief)) % len(pool)
    return [pool[(start + i) % len(pool)] for i in range(min(n, len(pool)))]


# ---------------------------------------------------------------------------
# Web search / fetch
# ---------------------------------------------------------------------------

def _known_urls() -> set[str]:
    urls = set()
    manifest = io_utils.load_json(MANIFEST, {}) or {}
    for meta in manifest.values():
        url = str(meta.get("source_url") or "")
        if url:
            urls.add(url)
    return urls


def _is_generic_title(title: str) -> bool:
    return bool(
        re.match(
            r"^(list of|index of|outline of|timeline of|glossary of|history of|"
            r"science fiction|fantasy|horror fiction|fiction|literature|genre)\b",
            title.strip(),
            re.I,
        )
    )


def _wiki_search(query: str, limit: int = 5) -> list[dict[str, str]]:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
            "utf8": 1,
        }
    )
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    try:
        data = _get_json(url, timeout=20)
    except Exception as exc:  # noqa: BLE001 - search is best effort
        print(f"[collector] wikipedia search failed for {query!r}: {exc}", flush=True)
        return []
    out = []
    for item in data.get("query", {}).get("search", []):
        title = str(item.get("title") or "")
        if not title:
            continue
        out.append(
            {
                "title": title,
                "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                "snippet": _clean(str(item.get("snippet") or "")),
                "origin": "wikipedia",
                "query": query,
            }
        )
    return out


def _wiki_extract(title: str) -> str:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "redirects": 1,
            "titles": title,
            "format": "json",
            "utf8": 1,
        }
    )
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    data = _get_json(url, timeout=30)
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        extract = str(page.get("extract") or "")
        if extract:
            return _clean(extract)
    return ""


def _gutendex_search(query: str, limit: int = 4) -> list[dict[str, str]]:
    url = "https://gutendex.com/books/?" + urllib.parse.urlencode({"search": query})
    try:
        data = _get_json(url, timeout=30)
    except Exception as exc:  # noqa: BLE001
        print(f"[collector] gutendex search failed for {query!r}: {exc}", flush=True)
        return []
    out = []
    for book in data.get("results", [])[:limit]:
        formats = book.get("formats") or {}
        text_url = ""
        for key in ("text/plain; charset=utf-8", "text/plain; charset=us-ascii", "text/plain"):
            if formats.get(key):
                text_url = str(formats[key])
                break
        if not text_url:
            continue
        authors = ", ".join(a.get("name", "") for a in book.get("authors", [])[:2])
        out.append(
            {
                "title": str(book.get("title") or "Untitled"),
                "url": text_url,
                "snippet": f"{authors} — Gutenberg #{book.get('id')}",
                "origin": "gutenberg",
                "query": query,
            }
        )
    return out


def _gutendex_text(url: str, max_chars: int = 9000) -> str:
    # Gutenberg serves large plain text files; cap the read.
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read(max_chars * 4)
    text = raw.decode("utf-8", errors="replace")
    start = text.find("*** START OF")
    if start != -1:
        text = text[start:]
    return _clean(text)[:max_chars]


def _slug_for(title: str, used: set[str]) -> str:
    base = io_utils.slugify(title)[:52] or "source"
    slug = base
    i = 2
    while slug in used:
        slug = f"{base}-{i}"
        i += 1
    used.add(slug)
    return slug


def discover_sources(
    brief_doc: dict[str, Any],
    n_sources: int = 8,
    provider: str | None = None,
) -> list[dict[str, str]]:
    """Search for fresh, unseen sources and return fetch descriptors."""
    known = _known_urls()
    relevant_queries = list(brief_doc.get("search_queries") or [])[:6]
    foreign_queries = list(brief_doc.get("foreign_queries") or [])[:4] or _pick_foreign_queries(
        brief_doc.get("brief", ""), 3
    )

    wanted_relevant = max(1, min(n_sources - 2, round(n_sources * 0.6)))
    wanted_foreign = max(1, n_sources - wanted_relevant)
    picked: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    seen_urls: set[str] = set(known)

    def add(candidates: list[dict[str, str]], diet: str, limit: int) -> None:
        for cand in candidates:
            if len([p for p in picked if p["diet"] == diet]) >= limit:
                return
            title_key = cand["title"].strip().lower()
            if title_key in seen_titles or cand["url"] in seen_urls:
                continue
            if _is_generic_title(cand["title"]):
                continue
            seen_titles.add(title_key)
            seen_urls.add(cand["url"])
            cand = dict(cand)
            cand["diet"] = diet
            picked.append(cand)

    for query in relevant_queries:
        add(_wiki_search(query, limit=4), "A", wanted_relevant)
        if len([p for p in picked if p["diet"] == "A"]) >= wanted_relevant:
            break
    for query in foreign_queries:
        add(_wiki_search(query, limit=4), "B", wanted_foreign)
        if len([p for p in picked if p["diet"] == "B"]) >= wanted_foreign:
            break

    # If a query yields nothing, widen with the other query family and, finally,
    # with Gutenberg fiction for the relevant slot.
    if len(picked) < n_sources:
        for query in foreign_queries + relevant_queries:
            add(_wiki_search(query, limit=8), "B", n_sources - len(picked))
            if len(picked) >= n_sources:
                break
    if len([p for p in picked if p["diet"] == "A"]) == 0:
        for query in relevant_queries[:2]:
            add(_gutendex_search(query, limit=3), "A", wanted_relevant)
    if not picked:
        for query in FOREIGN_DOMAINS[:3]:
            add(_wiki_search(query, limit=4), "B", n_sources)
    return picked[:n_sources]


def fetch_source(candidate: dict[str, str]) -> tuple[str, str] | None:
    """Fetch the text for one candidate. Returns (title, text) or None."""
    try:
        if candidate.get("origin") == "gutenberg":
            text = _gutendex_text(candidate["url"])
        else:
            text = _wiki_extract(candidate["title"])
    except Exception as exc:  # noqa: BLE001
        print(f"[collector] fetch failed for {candidate.get('title')!r}: {exc}", flush=True)
        return None
    if len(text.split()) < 150:
        return None
    return candidate["title"], text[:12000]


# ---------------------------------------------------------------------------
# Atomization
# ---------------------------------------------------------------------------

_ATOM_PROMPT = """Extract reusable narrative atoms from the source text below.

A narrative atom is one self-contained story mechanic: a plot device, character
dynamic, world rule, setting pressure, theme engine, or structure trick that a
writer who has never seen this source could lift into a different story today.
State the mechanism AND why it creates tension or meaning. 1-3 sentences each.
Extract 6-10 atoms. Prefer conceptual mechanics over trivia or plot summary.
Classify each atom as one of: plot_device, character_dynamic, world_rule,
setting_pressure, theme_engine, structure_trick.

SOURCE TITLE: {title}
SOURCE TEXT:
\"\"\"
{text}
\"\"\"

Output JSON only: {{"atoms": [{{"text": "...", "kind": "plot_device"}}, ...]}}
"""

_ALLOWED_KINDS = {
    "plot_device",
    "character_dynamic",
    "world_rule",
    "setting_pressure",
    "theme_engine",
    "structure_trick",
}


def atomize_text(title: str, text: str, provider: str | None = None) -> list[dict[str, str]]:
    chunks = [text]
    if len(text) > 7000:
        chunks = [text[:7000], text[7000:12000]]
    atoms: list[dict[str, str]] = []
    for chunk in chunks:
        prompt = _ATOM_PROMPT.format(title=title, text=chunk[:7000])
        try:
            data = llm.complete_json(prompt, stage_name="collector", provider=provider)
        except Exception as exc:  # noqa: BLE001
            print(f"[collector] atomization failed for {title!r}: {type(exc).__name__}: {exc}", flush=True)
            continue
        raw = data.get("atoms") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, str):
                item = {"text": item, "kind": "plot_device"}
            if not isinstance(item, dict):
                continue
            atom_text = str(item.get("text") or "").strip()
            if len(atom_text.split()) < 8:
                continue
            kind = str(item.get("kind") or "plot_device").strip().lower()
            if kind not in _ALLOWED_KINDS:
                kind = "plot_device"
            if any(_norm(atom_text) == _norm(a["text"]) for a in atoms):
                continue
            atoms.append({"text": atom_text, "kind": kind, "quality": "medium"})
        if len(atoms) >= 10:
            break
    return atoms[:10]


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


# ---------------------------------------------------------------------------
# Persist + integrate
# ---------------------------------------------------------------------------

def _append_atoms(
    source_id: str,
    title: str,
    source_url: str,
    diet: str,
    brief: str,
    fetched_at: str,
    atoms: list[dict[str, str]],
) -> list[dict[str, Any]]:
    existing = io_utils.load_json(ATOMS, []) or []
    existing_norm = {_norm(a["text"]) for a in existing}
    new_records = []
    for i, atom in enumerate(atoms, start=1):
        if _norm(atom["text"]) in existing_norm:
            continue
        existing_norm.add(_norm(atom["text"]))
        new_records.append(
            {
                "id": f"{source_id}-{i:02d}",
                "text": atom["text"],
                "kind": atom["kind"],
                "quality": str(atom.get("quality") or "medium"),
                "source": source_id,
                "diet": diet,
                "cluster": None,
                "origin": "live-research",
                "brief": brief[:180],
                "fetched_at": fetched_at,
            }
        )
    if new_records:
        io_utils.save_json(ATOMS, existing + new_records)
    return new_records


MIN_CLUSTER_SIZE = 3
MAX_CLUSTERS = 120


def _repair_small_clusters(
    clusters: list[dict[str, Any]],
    matrix: np.ndarray,
    index: dict[str, int],
    atoms_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Merge clusters below the minimum size into their nearest neighbour.

    The Gate-5 contract is at least three atoms per cluster. Live-research
    integration can produce a two-atom source cluster; those atoms are still
    useful, so keep them by folding them into a well-formed neighbour.
    """
    repaired = 0
    while len(clusters) > 1:
        small = [c for c in clusters if len(c.get("atom_ids", [])) < MIN_CLUSTER_SIZE]
        if not small:
            break
        cents: dict[int, np.ndarray] = {}
        for c in clusters:
            rows = [index[a] for a in c.get("atom_ids", []) if a in index]
            if rows:
                cents[int(c["id"])] = _centroid(matrix[rows])
        moved = False
        for c in small:
            cid = int(c["id"])
            if cid not in cents:
                clusters.remove(c)
                repaired += 1
                moved = True
                break
            options = [(other, cents[int(other["id"])]) for other in clusters if int(other["id"]) != cid]
            if not options:
                break
            sims = [float(cents[cid] @ cent) for _other, cent in options]
            target = options[int(np.argmax(sims))][0]
            existing = set(target.get("atom_ids", []))
            for aid in c.get("atom_ids", []):
                if aid in existing:
                    continue
                target.setdefault("atom_ids", []).append(aid)
                atom = atoms_by_id.get(aid) or {}
                diet = str(atom.get("diet") or "")
                if diet:
                    mix = target.setdefault("diet_mix", {})
                    mix[diet] = int(mix.get(diet, 0)) + 1
            target["size"] = len(target.get("atom_ids", []))
            clusters.remove(c)
            repaired += 1
            moved = True
            break
        if not moved:
            break
    return clusters, repaired


def repair_space() -> int:
    """Apply the min-cluster-size invariant to the persisted space."""
    atoms = io_utils.load_json(ATOMS, []) or []
    clusters_doc = io_utils.load_json(CLUSTERS, {}) or {"clusters": []}
    clusters = clusters_doc.get("clusters", [])
    if not atoms or not clusters:
        return 0
    atom_ids = [a["id"] for a in atoms]
    matrix, method = embeddings.embed_atoms(atom_ids, [a["text"] for a in atoms], force=False)
    index = {a: i for i, a in enumerate(atom_ids)}
    atoms_by_id = {a["id"]: a for a in atoms}
    clusters, repaired = _repair_small_clusters(clusters, matrix, index, atoms_by_id)
    if not repaired:
        return 0
    cluster_of = {aid: c["id"] for c in clusters for aid in c.get("atom_ids", [])}
    for atom in atoms:
        atom["cluster"] = cluster_of.get(atom["id"], atom.get("cluster"))
    io_utils.save_json(ATOMS, atoms)
    io_utils.save_json(CLUSTERS, {"clusters": clusters})
    meta = io_utils.load_json(META, {}) or {}
    meta.update({"n_clusters": len(clusters), "n_atoms": len(atoms), "coverage": 1.0})
    io_utils.save_json(META, meta)
    try:
        from . import cluster_atoms

        cluster_atoms._write_super_md({"clusters": clusters})
        cluster_atoms._write_digest({"clusters": clusters}, atoms, matrix, index)
    except Exception as exc:  # noqa: BLE001 - digest is convenience only
        print(f"[collector] repair digest refresh skipped: {exc}", flush=True)
    print(f"[collector] repaired {repaired} undersized cluster(s)", flush=True)
    return repaired


def integrate_new_atoms(new_records: list[dict[str, Any]], source_ids: list[str]) -> dict[str, Any]:
    """Embed all atoms and assign new ones to the nearest cluster (no re-cluster)."""
    if not new_records:
        return {"assigned": 0, "new_clusters": []}
    atoms = io_utils.load_json(ATOMS, []) or []
    atom_ids = [a["id"] for a in atoms]
    matrix, method = embeddings.embed_atoms(atom_ids, [a["text"] for a in atoms], force=False)
    index = {a: i for i, a in enumerate(atom_ids)}
    clusters_doc = io_utils.load_json(CLUSTERS, {}) or {"clusters": []}
    clusters = clusters_doc.get("clusters", [])
    if not clusters:
        raise SystemExit("clusters/clusters.json missing — run `storygen.py cluster` first")

    atoms_by_id = {a["id"]: a for a in atoms}
    clusters, repaired = _repair_small_clusters(clusters, matrix, index, atoms_by_id)
    if repaired:
        print(f"[collector] merged {repaired} undersized cluster(s) before integration", flush=True)

    cents = {}
    for c in clusters:
        rows = [index[a] for a in c["atom_ids"] if a in index]
        if not rows:
            continue
        cents[c["id"]] = _centroid(matrix[rows])
    cent_ids = list(cents)
    C = np.vstack([cents[c] for c in cent_ids])

    new_ids = [a["id"] for a in new_records]
    new_rows = [index[a] for a in new_ids]
    new_matrix = matrix[new_rows]
    sims = new_matrix @ C.T
    best = np.argmax(sims, axis=1)
    best_sim = sims[np.arange(len(new_rows)), best]

    next_id = max((c["id"] for c in clusters), default=-1) + 1
    new_clusters: list[dict[str, Any]] = []
    # Group unassigned atoms by source so each brand-new cluster has a coherent
    # origin instead of being a grab bag.
    by_source: dict[str, list[int]] = {}
    for pos, record in enumerate(new_records):
        if float(best_sim[pos]) >= 0.24:
            cid = int(cent_ids[int(best[pos])])
            for c in clusters:
                if c["id"] == cid:
                    c["atom_ids"].append(record["id"])
                    c["size"] = len(c["atom_ids"])
                    c["diet_mix"][record["diet"]] = c["diet_mix"].get(record["diet"], 0) + 1
                    break
            record["cluster"] = cid
        else:
            by_source.setdefault(record["source"], []).append(pos)

    for source_id, positions in by_source.items():
        if len(positions) < MIN_CLUSTER_SIZE or len(clusters) >= MAX_CLUSTERS:
            # Attaching thin leftovers to existing clusters keeps every cluster at
            # >=3 atoms and stops live research from pushing the space past 120.
            for p in positions:
                cid = int(cent_ids[int(best[p])])
                target = next(c for c in clusters if int(c["id"]) == cid)
                record = new_records[p]
                target.setdefault("atom_ids", []).append(record["id"])
                target["size"] = len(target["atom_ids"])
                target.setdefault("diet_mix", {})[
                    record["diet"]
                ] = target["diet_mix"].get(record["diet"], 0) + 1
                record["cluster"] = cid
            continue
        cid = next_id
        next_id += 1
        member_ids = [new_records[p]["id"] for p in positions]
        diet_mix: dict[str, int] = {}
        for p in positions:
            diet = new_records[p]["diet"]
            diet_mix[diet] = diet_mix.get(diet, 0) + 1
            new_records[p]["cluster"] = cid
        name, super_atom = _name_cluster([new_records[p]["text"] for p in positions], source_id)
        member_texts = [a["text"] for a in new_records if a["id"] in member_ids]
        new_cluster = {
            "id": cid,
            "name": name,
            "super_atom": super_atom,
            "atom_ids": member_ids,
            "size": len(member_ids),
            "diet_mix": diet_mix,
            "origin": "live-research",
        }
        clusters.append(new_cluster)
        new_clusters.append({"id": cid, "name": name, "size": len(member_ids)})
        print(f"[collector] new cluster {cid}: {name} ({len(member_texts)} atoms)", flush=True)

    # Keep every atom's cluster pointer in sync.
    cluster_of = {}
    for c in clusters:
        for aid in c["atom_ids"]:
            cluster_of[aid] = c["id"]
    for a in atoms:
        a["cluster"] = cluster_of.get(a["id"], a.get("cluster"))

    io_utils.save_json(ATOMS, atoms)
    io_utils.save_json(CLUSTERS, {"clusters": clusters})
    try:
        from . import cluster_atoms

        cluster_atoms._write_super_md({"clusters": clusters})
        cluster_atoms._write_digest({"clusters": clusters}, atoms, matrix, index)
    except Exception as exc:  # noqa: BLE001 - digest is convenience only
        print(f"[collector] digest refresh skipped: {exc}", flush=True)

    meta = io_utils.load_json(META, {}) or {}
    meta.update(
        {
            "embedding_method": method,
            "n_clusters": len(clusters),
            "n_atoms": len(atoms),
            "coverage": 1.0,
            "live_atoms": sum(1 for a in atoms if a.get("origin") == "live-research"),
        }
    )
    io_utils.save_json(META, meta)
    assigned = sum(1 for r in new_records if r["cluster"] is not None)
    print(
        f"[collector] integrated {assigned}/{len(new_records)} new atoms "
        f"({len(new_clusters)} new clusters, space now {len(clusters)} clusters / {len(atoms)} atoms)",
        flush=True,
    )
    return {"assigned": assigned, "new_clusters": new_clusters, "method": method}


def _centroid(rows: np.ndarray) -> np.ndarray:
    vec = rows.mean(axis=0, keepdims=True)
    norm = float(np.linalg.norm(vec))
    return (vec / max(norm, 1e-9))[0]


def _name_cluster(texts: list[str], fallback: str) -> tuple[str, str]:
    sample = "\n".join(f"- {t}" for t in texts[:10])
    prompt = f"""Name the shared narrative mechanism in these atoms. Return JSON only:
{{"name": "2-5 word label", "super_atom": "one sentence: the mechanism and the pressure it creates"}}

ATOMS:
{sample}
"""
    try:
        data = llm.complete_json(prompt, stage_name="collector")
        if isinstance(data, dict):
            name = str(data.get("name") or "").strip()[:60]
            super_atom = str(data.get("super_atom") or "").strip()[:300]
            if name:
                return name, super_atom
    except Exception as exc:  # noqa: BLE001
        print(f"[collector] cluster naming failed: {exc}", flush=True)
    clean = re.sub(r"[_-]+", " ", fallback).strip().title()
    return clean or "Fresh Research", "Atoms gathered from live research; the shared mechanism awaits naming."


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def collect(
    brief: str,
    n_sources: int = 8,
    provider: str | None = None,
    brief_doc: dict[str, Any] | None = None,
    extra_queries: list[str] | None = None,
) -> dict[str, Any]:
    """Run brief parsing + research + atomization + space integration."""
    brief_doc = brief_doc or parse_brief(brief, provider=provider)
    if extra_queries:
        brief_doc = dict(brief_doc)
        brief_doc["search_queries"] = list(brief_doc.get("search_queries") or []) + extra_queries
    # Over-discover: fetch failures and thin sources are common, and the run
    # contract is a minimum number of *usable* fresh sources.
    candidates = discover_sources(
        brief_doc, n_sources=max(n_sources, n_sources + 4), provider=provider
    )
    if not candidates:
        print("[collector] no fresh sources found — continuing with the standing corpus", flush=True)
        return {"brief": brief_doc, "sources": [], "atoms": [], "new_clusters": []}

    used_slugs = set((io_utils.load_json(MANIFEST, {}) or {}).keys())
    manifest = io_utils.load_json(MANIFEST, {}) or {}
    added_sources: list[dict[str, Any]] = []
    new_atoms_all: list[dict[str, Any]] = []
    fetched = 0
    for cand in candidates:
        if fetched >= n_sources:
            break
        title_url = cand["url"]
        if ledger.source_seen(io_utils.sha1(title_url)):
            print(f"[collector] already in ledger: {cand['title']}", flush=True)
            continue
        fetched_pair = fetch_source(cand)
        if fetched_pair is None:
            continue
        title, text = fetched_pair
        atoms = atomize_text(title, text, provider=provider)
        if len(atoms) < 6:
            print(f"[collector] {title!r}: only {len(atoms)} usable atoms, skipping", flush=True)
            continue
        sid = _slug_for(title, used_slugs)
        fetched_at = _now()
        body = text[:10000]
        io_utils.write_source(
            CORPUS / f"{sid}.md",
            {
                "id": sid,
                "title": title,
                "year": "",
                "medium": "live-research",
                "diet": cand["diet"],
                "kind": "fetched",
                "source_url": title_url,
                "word_count": len(body.split()),
                "fetched_at": fetched_at,
                "brief": brief[:160].replace("\n", " "),
                "origin_query": cand.get("query", ""),
            },
            body,
        )
        io_utils.save_json(
            ROOT / "atoms" / f"{sid}.json",
            {
                "source": sid,
                "title": title,
                "diet": cand["diet"],
                "atoms": atoms,
            },
        )
        manifest[sid] = {
            "title": title,
            "year": "",
            "medium": "live-research",
            "diet": cand["diet"],
            "kind": "fetched",
            "source_url": title_url,
            "word_count": len(body.split()),
            "fetched_at": fetched_at,
            "brief": brief[:160].replace("\n", " "),
        }
        io_utils.save_json(MANIFEST, manifest)
        ledger.record_source(io_utils.sha1(title_url), sid, title_url, title, cand["diet"])
        records = _append_atoms(sid, title, title_url, cand["diet"], brief, fetched_at, atoms)
        new_atoms_all.extend(records)
        added_sources.append(
            {
                "id": sid,
                "title": title,
                "url": title_url,
                "diet": cand["diet"],
                "atoms": len(records),
                "query": cand.get("query", ""),
            }
        )
        fetched += 1
        print(
            f"[collector] {fetched}/{n_sources} {cand['diet']} :: {title} -> {len(records)} atoms",
            flush=True,
        )

    integration = integrate_new_atoms(new_atoms_all, [s["id"] for s in added_sources])
    return {
        "brief": brief_doc,
        "sources": added_sources,
        "atoms": [{"id": r["id"], "text": r["text"], "source": r["source"]} for r in new_atoms_all],
        "new_clusters": integration.get("new_clusters", []),
    }


def anchor_cluster_ids(brief: str, top_n: int = 6) -> list[int]:
    """Rank clusters by semantic closeness to the brief (for anchored sampling)."""
    clusters_doc = io_utils.load_json(CLUSTERS, {}) or {}
    clusters = clusters_doc.get("clusters", [])
    if not clusters:
        return []
    atoms = io_utils.load_json(ATOMS, []) or []
    by_id = {a["id"]: a for a in atoms}
    cluster_texts = []
    for c in clusters:
        names = " ".join(
            str(by_id[aid].get("text", "")) for aid in c["atom_ids"][:4] if aid in by_id
        )
        cluster_texts.append(f"{c.get('name') or ''}. {c.get('super_atom') or ''} {names}")
    matrix, method = embeddings.embed_texts([brief] + cluster_texts)
    matrix = matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-9)
    sims = matrix[1:] @ matrix[0]
    order = np.argsort(-sims)[:top_n]
    anchors = [(int(clusters[i]["id"]), float(sims[i]), clusters[i].get("name")) for i in order]
    print(
        "[collector] brief anchors: "
        + ", ".join(f"{cid}:{name} ({sim:.2f})" for cid, sim, name in anchors[:4]),
        flush=True,
    )
    return [cid for cid, _sim, _name in anchors]
