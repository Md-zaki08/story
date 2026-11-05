#!/usr/bin/env python3
"""Artifact checker for the StoryGen 1.2 Definition of Done.

Run from the project root:  python check_gates.py
Exit code 0 only when every gate has evidence on disk.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS: list[tuple[int, str, bool, str]] = []


def add(gate: int, label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((gate, label, bool(ok), detail))


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


# Gate 1 — scaffold -----------------------------------------------------------
have = [
    (ROOT / "storygen.py").is_file(),
    (ROOT / "story" / "__init__.py").is_file(),
    (ROOT / "prompts" / "premise_v2.md").is_file(),
    (ROOT / "WORKFLOW.md").is_file(),
]
add(1, "storygen.py + story/ + prompts/ + WORKFLOW.md", all(have), str(have))

# Gate 2 — environment --------------------------------------------------------
meta = load(ROOT / "clusters" / "meta.json", {})
method = str(meta.get("embedding_method") or "")
add(2, "venv + embedding method recorded", (ROOT / ".venv").exists() and bool(method), method)

# Gate 3 — corpus -------------------------------------------------------------
manifest = load(ROOT / "corpus" / "manifest.json", {})
if isinstance(manifest, dict) and "sources" not in manifest:
    items = [{"id": key, **value} for key, value in manifest.items() if isinstance(value, dict)]
elif isinstance(manifest, dict):
    items = manifest["sources"]
else:
    items = manifest
if isinstance(items, dict):
    items = [{"id": key, **value} for key, value in items.items() if isinstance(value, dict)]
diet_a = sum(1 for s in items if str(s.get("diet", "")).upper() == "A")
diet_b = sum(1 for s in items if str(s.get("diet", "")).upper() == "B")
add(3, "corpus ≥45 diet-A + ≥25 diet-B", diet_a >= 45 and diet_b >= 25, f"A={diet_a} B={diet_b}")

# Gate 4 — atomization --------------------------------------------------------
atom_bad: list[str] = []
atom_counts: list[int] = []
for src in items:
    sid = src.get("id") or src.get("source_id")
    if not sid:
        continue
    doc = load(ROOT / "atoms" / f"{sid}.json", {})
    atoms = doc.get("atoms", []) if isinstance(doc, dict) else doc
    atom_counts.append(len(atoms))
    low = 6 if str(src.get("medium")) == "live-research" else 12
    high = 10 if str(src.get("medium")) == "live-research" else 25
    if not (low <= len(atoms) <= high):
        atom_bad.append(f"{sid}:{len(atoms)}")
    if atoms and not all(isinstance(a, dict) and a.get("quality") for a in atoms):
        atom_bad.append(f"{sid}:quality")
add(
    4,
    "every source atomized (12–25 corpus / 6–10 live)",
    not atom_bad,
    f"{len(atom_counts)} files, range {min(atom_counts) if atom_counts else 0}-{max(atom_counts) if atom_counts else 0}; bad={atom_bad[:5]}",
)

# Gate 5 — clustering ---------------------------------------------------------
clusters_doc = load(ROOT / "clusters" / "clusters.json", {})
clusters = clusters_doc.get("clusters", [])
sizes = [int(c.get("size") or len(c.get("atom_ids", []))) for c in clusters]
coverage = float(meta.get("coverage") or 0.0)
unnamed = [c.get("id") for c in clusters if not c.get("name") or not c.get("super_atom")]
add(
    5,
    "60–120 clusters, coverage ≥90%, min size ≥3, all named",
    60 <= len(clusters) <= 120 and coverage >= 0.9 and (min(sizes) if sizes else 0) >= 3 and not unnamed,
    f"{len(clusters)} clusters, coverage={coverage}, sizes={min(sizes) if sizes else 0}-{max(sizes) if sizes else 0}, unnamed={unnamed[:5]}",
)

# Gate 6 — sampling sweep -----------------------------------------------------
sweep = load(ROOT / "candidates" / "gate-sweep" / "config.json", {})
betas = [float(b) for b in sweep.get("betas", [])]
n_pool = int(sweep.get("n_pool") or 0)
sweep_files = all(
    (ROOT / "candidates" / "gate-sweep" / f"beta_{b:g}" / "results.json").exists()
    for b in (0.5, 0.7, 0.85)
)
add(
    6,
    "k=3 β=0.7 sample ≥3000 sets + β sweep 0.5/0.7/0.85",
    n_pool >= 3000 and sweep_files and {0.5, 0.7, 0.85}.issubset(set(betas)),
    f"pool={n_pool}, betas={betas}",
)

# Gate 7 — judgment table -----------------------------------------------------
best_judgment = (0, 0, "")
for md in sorted(list(ROOT.glob("runs/*/judgment.md")) + list(ROOT.glob("premises/*/judgment.md"))):
    text = md.read_text(encoding="utf-8", errors="replace")
    rows = len(re.findall(r"^\|\s*\d+\s*\|", text, flags=re.MULTILINE))
    m = re.search(r"Survivors:\s*(\d+)\s*/\s*(\d+)", text)
    kept = int(m.group(1)) if m else 0
    if rows > best_judgment[0] or (rows == best_judgment[0] and kept > best_judgment[1]):
        best_judgment = (rows, kept, str(md))
add(
    7,
    "top-50 judged table with ≥8 survivors",
    best_judgment[0] >= 50 and best_judgment[1] >= 8,
    f"best={best_judgment[2]} rows={best_judgment[0]} survivors={best_judgment[1]}",
)

# Gate 8 — premises -----------------------------------------------------------
best_run = (0, "")
for run_json in sorted(list(ROOT.glob("runs/*/run.json")) + list(ROOT.glob("premises/*/run.json"))):
    data = load(run_json, {})
    premises = data.get("premises") or []
    titles: set[str] = set()
    valid = []
    for p in premises:
        rel = p.get("files", {}).get("premise") or ""
        if not (run_json.parent / rel).is_file():
            continue
        text = str(p.get("premise") or "")
        words = len(re.findall(r"\b\w+\b", text))
        title = str(p.get("title") or "").strip().lower()
        if not (120 <= words <= 200) or not title or title in titles:
            continue
        titles.add(title)
        valid.append(p)
    if len(valid) > best_run[0]:
        best_run = (len(valid), str(run_json.parent))
add(
    8,
    "3–5 deep-dive premises saved with files",
    3 <= best_run[0] <= 5,
    f"best={best_run[1]} premises={best_run[0]}",
)

# Report ----------------------------------------------------------------------
print("StoryGen 1.2 — Definition of Done\n")
for gate, label, ok, detail in RESULTS:
    print(f"[{'PASS' if ok else 'FAIL'}] gate {gate}: {label}")
    if detail:
        print(f"       {detail}")
failed = [r for r in RESULTS if not r[2]]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks pass")
sys.exit(0 if not failed else 1)
