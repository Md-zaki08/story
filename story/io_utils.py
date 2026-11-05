"""Shared I/O helpers: JSON, front-matter markdown, ids, hashing, resume."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def load_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str | Path, data: Any, indent: int = 2) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.write("\n")
    tmp.replace(p)


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    header = text[3:end].strip("\n")
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, str] = {}
    for line in header.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, body


def read_source(path: str | Path) -> tuple[dict[str, str], str]:
    text = Path(path).read_text(encoding="utf-8")
    return parse_front_matter(text)


def write_source(path: str | Path, meta: dict[str, Any], body: str) -> None:
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n\n" + body.strip() + "\n", encoding="utf-8")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-+", "-", slug)


def run_id(seed: int) -> str:
    return time.strftime("%Y%m%dT%H%M%S") + f"-seed{seed}"


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()
