"""Premise, outline and full-story writing for StoryGen."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from . import io_utils, judge, ledger, llm

ROOT = io_utils.ROOT
PROMPTS = ROOT / "prompts"


class WriterError(RuntimeError):
    pass


PREMISE_MIN_WORDS = 120
PREMISE_MAX_WORDS = 200
LOGLINE_MAX_WORDS = 35


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _read_prompt(name: str, fallback: str) -> str:
    path = PROMPTS / name
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if text.strip():
            return text
    return fallback


def brief_block(brief_doc: dict[str, Any]) -> str:
    lines = [brief_doc.get("brief", "")]
    if brief_doc.get("hard_constraints_summary"):
        lines.append(f"Non-negotiable: {brief_doc['hard_constraints_summary']}")
    if brief_doc.get("soft_constraints_summary"):
        lines.append(f"Style wishes: {brief_doc['soft_constraints_summary']}")
    if brief_doc.get("genre"):
        lines.append(f"Genre: {brief_doc['genre']}")
    if brief_doc.get("tone"):
        lines.append(f"Tone: {brief_doc['tone']}")
    return "\n".join(str(x) for x in lines if x)


def constraints_block(brief_doc: dict[str, Any]) -> str:
    lines = []
    if brief_doc.get("must_include"):
        lines.append("Must include: " + "; ".join(str(x) for x in brief_doc["must_include"]))
    if brief_doc.get("must_avoid"):
        lines.append("Must avoid: " + "; ".join(str(x) for x in brief_doc["must_avoid"]))
    if brief_doc.get("banned_tropes"):
        lines.append("Banned tropes: " + "; ".join(str(x) for x in brief_doc["banned_tropes"]))
    if brief_doc.get("setting"):
        lines.append("Setting: " + str(brief_doc["setting"]))
    if brief_doc.get("time_period"):
        lines.append("Time period: " + str(brief_doc["time_period"]))
    if brief_doc.get("audience"):
        lines.append("Audience: " + str(brief_doc["audience"]))
    return "\n".join(lines) if lines else "None beyond the brief text."


def mechanics_block(candidate: dict[str, Any]) -> str:
    lines = []
    for name, atom in zip(candidate.get("cluster_names", []), candidate.get("exemplar_atoms", [])):
        lines.append(f"- {name}: {atom}")
    return "\n".join(lines)


def _joined_premise(doc: dict[str, Any]) -> str:
    return " ".join(
        str(doc.get(k) or "")
        for k in ("title", "logline", "premise", "why_fresh")
    )


def _core_premise(doc: dict[str, Any]) -> str:
    return " ".join(str(doc.get(k) or "") for k in ("title", "logline", "premise"))


# ---------------------------------------------------------------------------
# Premise
# ---------------------------------------------------------------------------

def _extend_premise(
    premise: str,
    brief_doc: dict[str, Any],
    provider: str | None,
) -> str:
    """Grow a short premise by appending concrete continuation sentences."""
    current = premise.strip()
    for step in range(3):
        words = io_utils.word_count(current)
        if words >= PREMISE_MIN_WORDS:
            break
        need = max(35, PREMISE_MIN_WORDS - words + 20)
        prompt = f"""The story premise below is {words} words. Continue it by adding 2-3
new sentences (at least {need} words) of concrete scene, consequence, or dialogue.
Do not repeat what is already there. Keep the same protagonist, world-rule and hard
constraints. Do not end with a rhetorical question. Return ONLY JSON:
{{"addition": "the new sentences"}}

HARD CONSTRAINTS
{constraints_block(brief_doc)}

PREMISE
{current}
"""
        try:
            raw = llm.complete_json(prompt, stage_name="writer", provider=provider)
        except Exception as exc:  # noqa: BLE001
            print(f"[writer] length extension failed: {type(exc).__name__}: {exc}", flush=True)
            break
        if isinstance(raw, list) and raw:
            raw = raw[0]
        if not isinstance(raw, dict):
            break
        addition = str(
            raw.get("addition") or raw.get("premise") or raw.get("text") or ""
        ).strip()
        if not addition or io_utils.word_count(addition) < 8:
            break
        current = (current.rstrip() + " " + addition.lstrip()).strip()
        print(
            f"[writer] length extension {step + 1}: {words} -> "
            f"{io_utils.word_count(current)} words",
            flush=True,
        )
    return current


def _compress_premise(
    premise: str,
    brief_doc: dict[str, Any],
    provider: str | None,
) -> str:
    """Shrink an overlong premise, falling back to dropping trailing sentences."""
    words = io_utils.word_count(premise)
    prompt = f"""Compress the story premise below to 140-180 words. It is currently
{words} words. Remove repetition and secondary detail; keep the protagonist, the
world-rule, the central conflict, the human stake and the final turn. Do not add a
theme essay or a logline. Return ONLY JSON: {{"premise": "140-180 words"}}

HARD CONSTRAINTS
{constraints_block(brief_doc)}

PREMISE
{premise}
"""
    try:
        raw = llm.complete_json(prompt, stage_name="writer", provider=provider)
        if isinstance(raw, list) and raw:
            raw = raw[0]
        if isinstance(raw, dict):
            text = str(raw.get("premise") or raw.get("text") or "").strip()
            if text and io_utils.word_count(text) <= PREMISE_MAX_WORDS:
                print(
                    f"[writer] length compression: {words} -> "
                    f"{io_utils.word_count(text)} words",
                    flush=True,
                )
                return text
    except Exception as exc:  # noqa: BLE001
        print(f"[writer] length compression failed: {type(exc).__name__}: {exc}", flush=True)

    # Last resort: drop whole trailing sentences, never cut mid-sentence.
    sentences = re.split(r"(?<=[.!?])\s+", premise.strip())
    while len(sentences) > 3 and io_utils.word_count(" ".join(sentences)) > PREMISE_MAX_WORDS:
        sentences.pop()
    trimmed = " ".join(sentences).strip()
    if trimmed and io_utils.word_count(trimmed) <= PREMISE_MAX_WORDS:
        print(
            f"[writer] length compression by sentence trim: {words} -> "
            f"{io_utils.word_count(trimmed)} words",
            flush=True,
        )
        return trimmed
    return premise


def _fit_premise_length(
    premise: str,
    brief_doc: dict[str, Any],
    provider: str | None,
) -> str | None:
    """Move a premise into the 120-200 word band using targeted edits."""
    prepared = premise
    for _step in range(3):
        words = io_utils.word_count(prepared)
        if PREMISE_MIN_WORDS <= words <= PREMISE_MAX_WORDS:
            return prepared
        if words < PREMISE_MIN_WORDS:
            prepared = _extend_premise(prepared, brief_doc, provider)
        else:
            prepared = _compress_premise(prepared, brief_doc, provider)
    if PREMISE_MIN_WORDS <= io_utils.word_count(prepared) <= PREMISE_MAX_WORDS:
        return prepared
    print(
        f"[writer] length repair could not reach the band "
        f"({io_utils.word_count(prepared)} words)",
        flush=True,
    )
    return None


def write_premise(
    candidate: dict[str, Any],
    brief_doc: dict[str, Any],
    provider: str | None = None,
    max_attempts: int = 4,
) -> dict[str, Any]:
    prompt_tpl = _read_prompt(
        "premise_v2.md",
        "Write a premise from these mechanics.\nBrief: {brief}\n{mechanics}\nJSON only.",
    )
    missing: list[str] = []
    data: dict[str, Any] | None = None
    last_error = ""
    length_note = ""
    for attempt in range(1, max_attempts + 1):
        prompt = (
            prompt_tpl.replace("{brief}", brief_block(brief_doc))
            .replace("{constraints}", constraints_block(brief_doc))
            .replace("{mechanics}", mechanics_block(candidate))
        )
        if missing:
            prompt += (
                "\n\nYour previous attempt OMITTED required elements: "
                + "; ".join(f"'{m}'" for m in missing)
                + ". Rewrite the premise so each of these exact terms appears naturally "
                "in the title, logline, or premise, while keeping the story strange."
            )
        if length_note:
            prompt += "\n\n" + length_note
        try:
            raw = llm.complete_json(prompt, stage_name="writer", provider=provider)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"[writer] premise attempt {attempt} failed: {last_error}", flush=True)
            continue
        if isinstance(raw, list) and raw:
            raw = raw[0]
        if not isinstance(raw, dict):
            last_error = "premise response was not an object"
            continue
        premise = str(raw.get("premise") or "").strip()
        word_count = io_utils.word_count(premise)
        if not (PREMISE_MIN_WORDS <= word_count <= PREMISE_MAX_WORDS):
            repaired = _fit_premise_length(premise, brief_doc, provider)
            if repaired:
                repaired_words = io_utils.word_count(repaired)
                if PREMISE_MIN_WORDS <= repaired_words <= PREMISE_MAX_WORDS:
                    premise, word_count = repaired, repaired_words
                    print(f"[writer] premise length repaired to {word_count} words", flush=True)
        if not (PREMISE_MIN_WORDS <= word_count <= PREMISE_MAX_WORDS):
            last_error = (
                f"premise must be {PREMISE_MIN_WORDS}-{PREMISE_MAX_WORDS} words, "
                f"got {word_count}"
            )
            length_note = (
                f"LENGTH CORRECTION: your previous premise was {word_count} words. "
                f"Rewrite it as one continuous paragraph of {PREMISE_MIN_WORDS}-"
                f"{PREMISE_MAX_WORDS} words. Keep the same story but add concrete scene "
                "detail and consequences if it is too short; cut repetition if too long. "
                "Count the words before returning."
            )
            print(f"[writer] premise attempt {attempt}: {last_error}", flush=True)
            missing = []
            continue
        title = str(raw.get("title") or "").strip()[:160]
        logline = str(raw.get("logline") or "").strip()
        logline_words = io_utils.word_count(logline)
        if not title or title.lower() in {"untitled", "title"}:
            last_error = "premise has no usable title"
            length_note = ""
            print(f"[writer] premise attempt {attempt}: {last_error}", flush=True)
            missing = []
            continue
        prior_titles = {
            str(h.get("title") or "").strip().lower() for h in ledger.history_texts()
        }
        if title.lower() in prior_titles:
            last_error = f"duplicate premise title {title!r}"
            length_note = ""
            print(f"[writer] premise attempt {attempt}: {last_error}; retrying", flush=True)
            missing = []
            continue
        if not logline or logline_words > LOGLINE_MAX_WORDS:
            last_error = (
                f"logline must be 1-{LOGLINE_MAX_WORDS} words, got {logline_words}"
            )
            length_note = (
                f"LOGLINE CORRECTION: your previous logline was {logline_words} words. "
                f"Return one sentence of at most {LOGLINE_MAX_WORDS} words."
            )
            print(f"[writer] premise attempt {attempt}: {last_error}", flush=True)
            missing = []
            continue
        length_note = ""
        doc = {
            "title": title,
            "logline": logline[:400],
            "premise": premise[:3000],
            "built_from": (
                raw.get("built_from")
                if isinstance(raw.get("built_from"), list)
                else candidate.get("cluster_names", [])
            ),
            "why_fresh": str(raw.get("why_fresh") or "").strip()[:1500],
            "content_warnings": (
                raw.get("content_warnings")
                if isinstance(raw.get("content_warnings"), list)
                else []
            ),
            "word_count": word_count,
        }
        missing = _missing_constraints(doc, brief_doc)
        forbidden = _forbidden_hits(doc, brief_doc)
        if missing:
            print(f"[writer] premise attempt {attempt} missing constraints: {missing}", flush=True)
            continue
        if forbidden:
            print(f"[writer] premise attempt {attempt} contains forbidden elements: {forbidden}", flush=True)
            continue
        canon = judge.canon_neighbors(_core_premise(doc), top_k=2)
        if canon["max_similarity"] >= judge.DEFAULT_CANON_KILL:
            hit = canon["closest"][0]
            print(
                f"[writer] premise attempt {attempt} too close to canon "
                f"'{hit['title']}' (cos {canon['max_similarity']:.3f}); retrying",
                flush=True,
            )
            last_error = f"canon collision with {hit['title']} ({canon['max_similarity']:.3f})"
            missing = []  # divergence, not missing terms
            continue
        doc["canon_check"] = canon
        sim, prior = ledger.similarity_to_history(_joined_premise(doc))
        if sim > 0.82:
            print(
                f"[writer] premise attempt {attempt} too close to past premise "
                f"'{prior}' (cos {sim:.3f}); retrying",
                flush=True,
            )
            last_error = f"ledger collision with {prior} ({sim:.3f})"
            missing = []  # the fix is divergence, not missing terms
            continue
        doc["ledger_similarity"] = round(float(sim), 4)
        doc["cluster_ids"] = candidate.get("cluster_ids", [])
        doc["cluster_names"] = candidate.get("cluster_names", [])
        doc["fusion"] = candidate.get("fusion")
        doc["judge"] = candidate.get("judge", {})
        print(
            f"[writer] premise: {doc['title']} ({doc['word_count']} words) :: "
            f"{' + '.join(doc['cluster_names'])}",
            flush=True,
        )
        return doc

    raise WriterError(
        f"Could not satisfy brief + ledger constraints after {max_attempts} attempts"
        + (f" ({last_error})" if last_error else "")
    )


def _missing_constraints(doc: dict[str, Any], brief_doc: dict[str, Any]) -> list[str]:
    text = _core_premise(doc).lower()
    missing = []
    for term in brief_doc.get("must_include") or []:
        term = str(term).strip()
        if not term:
            continue
        # Accept the term or its significant words (the model may inflect).
        words = [w for w in re.findall(r"[a-z0-9]{4,}", term.lower())]
        if term.lower() in text:
            continue
        if words and sum(1 for w in words if w in text) >= max(1, len(words) - 1):
            continue
        missing.append(term)
    return missing


def _forbidden_hits(doc: dict[str, Any], brief_doc: dict[str, Any]) -> list[str]:
    text = _core_premise(doc).lower()
    hits = []
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
                hits.append(term)
                break
    return hits


# ---------------------------------------------------------------------------
# Outline
# ---------------------------------------------------------------------------

def write_outline(
    premise: dict[str, Any],
    brief_doc: dict[str, Any],
    provider: str | None = None,
) -> dict[str, Any]:
    tpl = _read_prompt(
        "outline.md",
        "Expand this premise into a 3-act outline.\nBrief: {brief}\nPremise: {premise}\nJSON only.",
    )
    prompt = (
        tpl.replace("{brief}", brief_block(brief_doc))
        .replace("{constraints}", constraints_block(brief_doc))
        .replace("{premise}", render_premise(premise))
    )
    last_error = ""
    for attempt in range(1, 3):
        try:
            raw = llm.complete_json(prompt, stage_name="writer", provider=provider)
            if isinstance(raw, list) and raw:
                raw = raw[0]
            if not isinstance(raw, dict):
                raise ValueError("outline was not an object")
            acts = raw.get("acts")
            if not isinstance(acts, list) or len(acts) < 3:
                raise ValueError(f"outline has {len(acts) if isinstance(acts, list) else 0} acts")
            for i, act in enumerate(acts, start=1):
                if not isinstance(act, dict):
                    raise ValueError("act is not an object")
                act["number"] = int(act.get("number") or i)
                act.setdefault("title", f"Act {i}")
                act.setdefault("summary", "")
                beats = act.get("beats")
                if not isinstance(beats, list) or not beats:
                    raise ValueError(f"act {i} has no beats")
                act["beats"] = [str(b).strip() for b in beats if str(b).strip()]
            out = {
                "title": str(raw.get("title") or premise.get("title") or "Untitled"),
                "logline": str(raw.get("logline") or premise.get("logline") or ""),
                "characters": raw.get("characters") or [],
                "acts": acts[:5],
                "setting_rules": raw.get("setting_rules") or [],
                "ending": str(raw.get("ending") or ""),
                "why_it_holds": str(raw.get("why_it_holds") or ""),
            }
            print(
                f"[writer] outline: {out['title']} — {len(out['acts'])} acts, "
                f"{len(out.get('characters') or [])} characters",
                flush=True,
            )
            return out
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"[writer] outline attempt {attempt} failed: {last_error}", flush=True)
    print("[writer] using structural outline fallback (LLM failed twice)", flush=True)
    return _structural_outline(premise)


def _structural_outline(premise: dict[str, Any]) -> dict[str, Any]:
    """Last-resort outline built from the premise, so a run never loses its expansion."""
    text = str(premise.get("premise") or "").strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    while len(sentences) < 6:
        sentences.append("The pressure tightens and a cost must be paid.")
    third = max(1, len(sentences) // 3)
    acts = []
    labels = [("The Hook", "The world-rule is revealed through a costly choice."),
              ("The Escalation", "The mechanism turns against the protagonist's want."),
              ("The Reckoning", "The protagonist chooses what the mechanism cannot give.")]
    for i, (title, summary) in enumerate(labels, start=1):
        chunk = sentences[(i - 1) * third : i * third] or sentences[:2]
        beats = [s[:220] for s in chunk[:4]]
        while len(beats) < 3:
            beats.append("A consequence lands that cannot be undone.")
        acts.append({"number": i, "title": title, "summary": summary, "beats": beats})
    return {
        "title": premise.get("title", "Untitled"),
        "logline": premise.get("logline", ""),
        "characters": [],
        "acts": acts,
        "setting_rules": ["The premise's central mechanism is enforced by the world."],
        "ending": "The final beat pays the mechanism's price in full.",
        "why_it_holds": "Structural fallback generated because the model did not return a valid outline.",
        "fallback": True,
    }


# ---------------------------------------------------------------------------
# Full story
# ---------------------------------------------------------------------------

def _ngram_repetition(text: str, n: int = 8) -> float:
    words = re.findall(r"[a-z']+", text.lower())
    if len(words) < n * 2:
        return 0.0
    grams = [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]
    counts: dict[tuple[str, ...], int] = {}
    for gram in grams:
        counts[gram] = counts.get(gram, 0) + 1
    repeated = sum(c - 1 for c in counts.values() if c > 1)
    return repeated / max(1, len(grams))


def _act_prompt(
    premise: dict[str, Any],
    outline: dict[str, Any],
    brief_doc: dict[str, Any],
    act: dict[str, Any],
    recap: str,
    target_words: int,
) -> str:
    tpl = _read_prompt("story_act.md", "")
    beats = "\n".join(f"- {b}" for b in act.get("beats", []))
    outline_summary = "\n".join(
        f"Act {a.get('number')}: {a.get('title')} — {a.get('summary')}" for a in outline.get("acts", [])
    )
    return (
        tpl.replace("{act_number}", str(act.get("number")))
        .replace("{brief}", brief_block(brief_doc))
        .replace("{premise}", render_premise(premise))
        .replace("{outline}", outline_summary + "\nEnding: " + str(outline.get("ending") or ""))
        .replace("{recap}", recap or "This is the opening act.")
        .replace("{beats}", beats)
        .replace("{target_words}", str(target_words))
        .replace("{constraints}", constraints_block(brief_doc))
    )


def _ends_cleanly(text: str) -> bool:
    tail = text.rstrip()
    if not tail:
        return False
    if tail[-1] not in ".!?…\"'”’":
        return False
    # A dangling opening quote or an unclosed parenthesis also signals truncation.
    if tail.count("(") > tail.count(")"):
        return False
    if tail.count("“") > tail.count("”") and tail.count("“") > tail.count("‘"):
        return False
    return True


def _finish_act_text(
    text: str,
    premise: dict[str, Any],
    outline: dict[str, Any],
    brief_doc: dict[str, Any],
    act: dict[str, Any],
    provider: str | None,
) -> str:
    """Continue an act that hit the token limit mid-sentence."""
    if _ends_cleanly(text):
        return text
    for attempt in range(2):
        tail = text[-900:]
        prompt = f"""The act below stops mid-sentence because of a length limit. Continue it
immediately in the same voice. Write 120-200 words that finish the unfinished sentence
and land the act on a turn. Do not restart, do not summarize, and do not repeat the
last paragraph. End with complete punctuation. Return prose only.

BRIEF
{brief_block(brief_doc)}

PREMISE
{render_premise(premise)}

ACT {act.get('number')} — {act.get('title')}
Beats covered: {'; '.join(str(b) for b in act.get('beats', []))}
ENDING THE WHOLE STORY IS MOVING TOWARD: {outline.get('ending') or ''}

LAST {len(tail)} CHARACTERS
{tail}

CONTINUATION:
"""
        try:
            addition = _complete_prose(
                prompt, provider, max_tokens=520, temperature=0.7
            ).strip()
        except Exception as exc:  # noqa: BLE001 - keep the draft even if repair fails
            print(f"[writer] act {act.get('number')} finish failed: {exc}", flush=True)
            break
        if not addition:
            break
        combined = (text.rstrip() + " " + addition).strip()
        if _ends_cleanly(combined):
            print(
                f"[writer] act {act.get('number')} finished: "
                f"{io_utils.word_count(text)} -> {io_utils.word_count(combined)} words",
                flush=True,
            )
            return combined
        text = combined
    return text


def write_story(
    premise: dict[str, Any],
    outline: dict[str, Any],
    brief_doc: dict[str, Any],
    provider: str | None = None,
    target_words: int = 3000,
) -> dict[str, Any]:
    acts = outline.get("acts") or []
    if not acts:
        raise WriterError("outline has no acts")
    per_act = max(700, target_words // len(acts))
    rendered: list[dict[str, Any]] = []
    recap = ""

    for act in acts:
        prompt = _act_prompt(premise, outline, brief_doc, act, recap, per_act)
        token_budget = min(2000, max(1200, int(per_act * 1.6)))
        started = time.time()
        text = _complete_prose(prompt, provider, max_tokens=token_budget)
        words = io_utils.word_count(text)
        if words < per_act * 0.6:
            print(f"[writer] act {act.get('number')}: {words} words — extending", flush=True)
            retry = prompt + (
                f"\n\nYour previous draft was only {words} words. Write the act again at "
                f"least {per_act} words. Add scene, consequence and sensory specificity."
            )
            longer = _complete_prose(
                retry, provider, max_tokens=min(2200, max(1400, int(per_act * 1.8)))
            )
            if io_utils.word_count(longer) > words:
                text = longer
                words = io_utils.word_count(text)

        issues = []
        if words < per_act * 0.55:
            issues.append("the act is still thin: add consequential scene work, not summary")
        if _ngram_repetition(text) > 0.035:
            issues.append("phrases repeat; vary the images and sentence openings")
        if issues:
            revised = _revise_act(text, issues, provider)
            if io_utils.word_count(revised) >= words * 0.65:
                text = revised
                words = io_utils.word_count(text)
        text = _finish_act_text(text, premise, outline, brief_doc, act, provider)
        words = io_utils.word_count(text)
        rendered.append({"number": act.get("number"), "title": act.get("title"), "text": text.strip()})
        recap = _recap(rendered)
        print(
            f"[writer] act {act.get('number')}: {words} words "
            f"in {time.time() - started:.0f}s",
            flush=True,
        )

    story_text = "\n\n* * *\n\n".join(r["text"] for r in rendered).strip()
    total = io_utils.word_count(story_text)
    print(f"[writer] draft complete: {total} words", flush=True)
    if total < 1800:
        print("[writer] WARNING: draft below the 2,000-word target", flush=True)
    return {
        "text": story_text,
        "acts": rendered,
        "word_count": total,
        "repetition": round(_ngram_repetition(story_text), 4),
        "target_words": target_words,
    }


def _revise_act(text: str, issues: list[str], provider: str | None) -> str:
    tpl = _read_prompt("revise_act.md", "")
    prompt = tpl.replace("{issues}", "\n".join(f"- {i}" for i in issues)).replace("{text}", text)
    try:
        revised = _complete_prose(prompt, provider, max_tokens=1800, temperature=0.55)
        if revised.strip():
            print(f"[writer] revision pass: {io_utils.word_count(text)} -> {io_utils.word_count(revised)} words", flush=True)
            return revised
    except Exception as exc:  # noqa: BLE001
        print(f"[writer] revision failed ({exc}); keeping draft", flush=True)
    return text


def _complete_prose(
    prompt: str,
    provider: str | None,
    max_tokens: int,
    temperature: float = 0.85,
) -> str:
    text = llm.complete(
        prompt,
        stage_name="writer",
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = re.sub(r"^\s*#+\s*.*\n+", "", text)  # drop accidental headings at the top
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise WriterError("empty prose response")
    return text


def _recap(rendered: list[dict[str, Any]]) -> str:
    chunks = []
    for act in rendered:
        words = act["text"].split()
        chunks.append(f"Act {act['number']}: " + " ".join(words[-140:]))
    return "\n".join(chunks)


# ---------------------------------------------------------------------------
# Rendering / saving
# ---------------------------------------------------------------------------

def render_premise(doc: dict[str, Any]) -> str:
    built = "\n".join(f"- {x}" for x in doc.get("built_from") or [])
    judge = doc.get("judge") or {}
    score = ""
    if judge:
        score = (
            f"\n\n**Judge:** coherence {judge.get('coherence')}/10, "
            f"freshness {judge.get('freshness')}/10, viability {judge.get('viability')}/10. "
            f"{judge.get('reason', '')}"
        )
    return (
        f"# {doc.get('title', 'Untitled')}\n\n"
        f"**Logline:** {doc.get('logline', '')}\n\n"
        f"## Premise\n\n{doc.get('premise', '')}\n\n"
        f"## Built from\n\n{built}\n\n"
        f"## Why it's fresh\n\n{doc.get('why_fresh', '')}{score}\n"
    )


def render_outline(doc: dict[str, Any], premise: dict[str, Any] | None = None) -> str:
    lines = [f"# {doc.get('title', 'Untitled')}", ""]
    if doc.get("logline"):
        lines += [f"**Logline:** {doc['logline']}", ""]
    chars = doc.get("characters") or []
    if chars:
        lines += ["## Characters", ""]
        for c in chars:
            if not isinstance(c, dict):
                continue
            lines.append(
                f"- **{c.get('name', '?')}** — {c.get('role', '')}. "
                f"Wants: {c.get('want', '')}. Pressure: {c.get('pressure', '')}. "
                f"Secret: {c.get('secret', '')}."
            )
        lines.append("")
    for act in doc.get("acts") or []:
        lines += [f"## Act {act.get('number')} — {act.get('title', '')}", ""]
        if act.get("summary"):
            lines += [str(act["summary"]), ""]
        for beat in act.get("beats") or []:
            lines.append(f"1. {beat}")
        lines.append("")
    rules = doc.get("setting_rules") or []
    if rules:
        lines += ["## Setting rules", ""] + [f"- {r}" for r in rules] + [""]
    if doc.get("ending"):
        lines += ["## Ending", "", str(doc["ending"]), ""]
    if doc.get("why_it_holds"):
        lines += ["## Why it holds", "", str(doc["why_it_holds"]), ""]
    if premise:
        lines += ["---", "", f"*Expanded from: {premise.get('title', '')}*", ""]
    return "\n".join(lines)


def save_premise(run_dir: Path, index: int, doc: dict[str, Any]) -> Path:
    slug = io_utils.slugify(doc.get("title", "premise"))[:60] or "premise"
    path = run_dir / f"{index:02d}-{slug}.md"
    path.write_text(render_premise(doc), encoding="utf-8")
    return path


def save_outline(run_dir: Path, index: int, doc: dict[str, Any], premise: dict[str, Any]) -> Path:
    slug = io_utils.slugify(premise.get("title", "premise"))[:60] or "premise"
    path = run_dir / f"{index:02d}-{slug}.outline.md"
    path.write_text(render_outline(doc, premise), encoding="utf-8")
    return path


def save_story(run_dir: Path, index: int, doc: dict[str, Any], premise: dict[str, Any]) -> Path:
    slug = io_utils.slugify(premise.get("title", "premise"))[:60] or "premise"
    path = run_dir / f"{index:02d}-{slug}.story.md"
    header = (
        f"# {premise.get('title', 'Untitled')}\n\n"
        f"*{premise.get('logline', '')}*\n\n"
    )
    path.write_text(header + doc["text"].strip() + "\n", encoding="utf-8")
    return path
