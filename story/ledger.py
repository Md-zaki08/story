"""Permanent anti-repetition ledger (SQLite).

Every premise, kill, fetched source and run is recorded. Future runs:

- exclude candidate cluster sets that overlap past premises (Jaccard);
- reject written premises whose text is too close to anything ever output
  (embedding cosine against the full history, computed in one shared space).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import numpy as np

from . import embeddings, io_utils, stats as stat_utils

ROOT = io_utils.ROOT
DB = ROOT / "ledger.db"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS premises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            title TEXT NOT NULL,
            logline TEXT,
            premise TEXT,
            brief TEXT,
            cluster_ids TEXT,
            cluster_names TEXT,
            fusion REAL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS kills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            cluster_ids TEXT,
            reason TEXT,
            scores TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sources (
            url_hash TEXT PRIMARY KEY,
            source_id TEXT,
            url TEXT,
            title TEXT,
            diet TEXT,
            fetched_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            brief TEXT,
            meta TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    return con


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def source_seen(url_hash: str) -> bool:
    with connect() as con:
        row = con.execute("SELECT 1 FROM sources WHERE url_hash = ?", (url_hash,)).fetchone()
        return row is not None


def record_source(url_hash: str, source_id: str, url: str, title: str, diet: str) -> None:
    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO sources (url_hash, source_id, url, title, diet, fetched_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (url_hash, source_id, url, title, diet, _now()),
        )


def source_stats() -> dict:
    with connect() as con:
        rows = con.execute("SELECT diet, COUNT(*) AS n FROM sources GROUP BY diet").fetchall()
        return {row["diet"]: row["n"] for row in rows}


# ---------------------------------------------------------------------------
# Runs / premises
# ---------------------------------------------------------------------------

def record_run(run_id: str, brief: str, meta: dict | None = None) -> None:
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO runs (run_id, brief, meta, created_at) VALUES (?, ?, ?, ?)",
            (run_id, brief, json.dumps(meta or {}), _now()),
        )


def record_premise(
    run_id: str,
    title: str,
    logline: str,
    premise: str,
    brief: str,
    cluster_ids: list[int],
    cluster_names: list[str],
    fusion: float,
) -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO premises (run_id, title, logline, premise, brief, cluster_ids,"
            " cluster_names, fusion, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                title,
                logline,
                premise,
                brief,
                json.dumps(cluster_ids),
                json.dumps(cluster_names),
                float(fusion),
                _now(),
            ),
        )
        return int(cur.lastrowid)


def record_kill(run_id: str, cluster_ids: list[int], reason: str, scores: dict | None = None) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO kills (run_id, cluster_ids, reason, scores, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (run_id, json.dumps(cluster_ids), reason, json.dumps(scores or {}), _now()),
        )


def history_texts() -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT title, logline, premise FROM premises ORDER BY id").fetchall()
    return [
        {
            "title": row["title"],
            "text": f"{row['title']}. {row['logline'] or ''} {row['premise'] or ''}".strip(),
        }
        for row in rows
    ]


def similarity_to_history(text: str) -> tuple[float, str | None]:
    """Max cosine similarity of `text` against every premise ever written."""
    history = history_texts()
    if not history:
        return 0.0, None
    texts = [text] + [h["text"] for h in history]
    matrix, _method = embeddings.embed_texts(texts)
    matrix = stat_utils.normalize_rows(matrix)
    sims = matrix[0] @ matrix[1:].T
    idx = int(np.argmax(sims))
    return float(sims[idx]), history[idx]["title"]


def past_combos() -> list[tuple[int, ...]]:
    with connect() as con:
        rows = con.execute("SELECT cluster_ids FROM premises").fetchall()
    combos = []
    for row in rows:
        try:
            combos.append(tuple(sorted(int(x) for x in json.loads(row["cluster_ids"]))))
        except Exception:
            continue
    return combos


def max_combo_overlap(cluster_ids: list[int], past: list[tuple[int, ...]] | None = None) -> float:
    """Max Jaccard overlap of a candidate set with any premise ever written."""
    past = past_combos() if past is None else past
    a = set(cluster_ids)
    best = 0.0
    for combo in past:
        b = set(combo)
        if not a or not b:
            continue
        best = max(best, len(a & b) / len(a | b))
    return best


def stats() -> dict:
    with connect() as con:
        n_prem = con.execute("SELECT COUNT(*) FROM premises").fetchone()[0]
        n_kills = con.execute("SELECT COUNT(*) FROM kills").fetchone()[0]
        n_runs = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        n_sources = con.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        recent = con.execute(
            "SELECT run_id, title, created_at FROM premises ORDER BY id DESC LIMIT 5"
        ).fetchall()
    return {
        "premises": n_prem,
        "kills": n_kills,
        "runs": n_runs,
        "sources": n_sources,
        "recent": [dict(row) for row in recent],
    }
