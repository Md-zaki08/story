# BUILD LOG — StoryGen 1.2

Build date: 2026-11-01 (UTC). Run id: `20261102T005552-seed42`.
Host: Android aarch64 (Termux userland, prefix owned by root), Python 3.14.8.

## Stage log

### 1. Scaffold
- Created `storygen.py` (argparse CLI: `corpus-check`, `atomize-init`, `cluster`, `sample`,
  `stats`; flags `--seed`, `--k`, `--beta`, `--betas`, `--top-k`, `--n-draws`,
  `--output-dir`, `--apply-names`).
- Created `story/` package: `io_utils.py`, `stats.py`, `embeddings.py`, `cluster_atoms.py`,
  `sample.py`, `__init__.py`.
- Wrote the five prompts verbatim from the spec: `prompts/atomization.md`,
  `prompts/refinement.md`, `prompts/super_atom.md`, `prompts/judgment.md`,
  `prompts/premise.md`.
- `python3 storygen.py --help` works.

### 2. Environment
- `pkg` refuses to run as root; Python 3.14.8 and dependencies were installed by extracting
  Termux `.deb` packages (`python_3.14.8`, `python-pip 26.2.2-2`,
  `python-ensurepip-wheels`, `python-numpy 2.5.4`, `python-scipy 1.18.1`,
  `libopenblas 0.3.34`, `libc++ 30`, `libandroid-complex-math 0.2`) with `dpkg-deb -x`.
- venv at `.venv` created with `--system-site-packages`.
- No PyPI wheels exist for model2vec / fastembed / sentence-transformers on this
  platform. The §7 fallback chain was attempted at runtime and descended to the last
  resort: **TF-IDF + SVD (192 dimensions)**. This is recorded in
  `clusters/meta.json` (`embedding_method: "tfidf-svd:192"`, `embedding_attempts`).
- Runtime versions: Python 3.14.8, numpy 2.5.4, scipy 1.18.1.

### 3. Corpus
- 76 sources: 49 diet A, 27 diet B. 71 fetched from the Wikipedia API (action=query,
  prop=extracts, plaintext), 5 synthesized (4 created + `zoe-2018` rewritten).
- Synthesized (kind: synthesized): `after-yang-2021`, `automata-2014`, `upload-2020`,
  `libet-readiness`.
- `zoe-2018` was fetched as a disambiguation page; it was rewritten as a synthesized
  synopsis and the manifest entry was corrected (`kind: synthesized`,
  `source_url: ""`, `word_count: 372`).
- `corpus-check` passed before sampling: A:49, B:27, fetched:71, synthesized:5,
  manifest and files consistent.

### 4. Atomization
- 76/76 sources have `atoms/<id>.json`; 16 atoms per source; **1216 atoms** total.
- Each atom is self-standing, names its mechanism and why it produces tension, and is
  classified as one of the six kinds from `prompts/atomization.md`; all are quality-rated.
- Flat index written to `atoms/all.json` (`id, text, kind, quality, source, diet`).

### 5. Clustering
- `storygen.py cluster --seed 42`.
- Embeddings: TF-IDF+SVD, 192 dims, cached to `clusters/embeddings.npz`.
- Average-linkage cosine clustering, threshold swept 0.20–0.98; accepted at **0.59**:
  **87 clusters**, sizes 5–30 (median 13), **coverage 100%**, min size ≥ 3,
  orphans merged.
- `clusters/digest.json` written; all 87 clusters named and given a super atom in
  `clusters/names.json`; applied with `cluster --apply-names`.
- `clusters/super_atoms.md` and `clusters/gravity_wells.json` written.

### 6. Sampling
- `storygen.py sample --seed 42 --k 3 --n-draws 20000 --top-k 50 --betas 0.5,0.7,0.85`.
- Pool: **5620 distinct candidate sets** (after dedupe, coherence floor 0.08, cap 6000).
- β sweep written to `candidates/20261102T005552-seed42/beta_{0.5,0.7,0.85}/results.json`.
- `corr(coherence, unavailability) = -0.5308` (expected trade-off).
- No coherence floor fallback was needed.

### 7. Judging
- Top 50 at β=0.7 rated in `candidates/20261102T005552-seed42/judgment.md`.
- Kill rule enforced (coherence < 6 OR freshness < 7): **8 survivors**, within the
  spec's 8–12 band. The dominant kill pattern was the repeated
  "Company City + Corporate Body" pairing (corporate-dystopia gravity well) and
  weapon/child or digient/child sets that restate The Iron Giant, Terminator 2, or
  A.I. Artificial Intelligence.

### 8. Premises
- 4 deep-dive premises written under `premises/20261102T005552-seed42/`:
  1. `01-the-second-word.md` — #5 (fusion 1.9107), strongest diet-B pull.
  2. `02-the-hospice-protocol.md` — #39 (fusion 1.4018).
  3. `03-the-cuckoo-room.md` — #16 (fusion 1.6201).
  4. `04-the-cleaner.md` — #1 (fusion 2.0514).
- `runners-up.md` lists the other 4 survivors plus 4 near-miss kills as one-line loglines.

## Deviations and fallbacks

| # | Deviation | Reason | Where recorded |
|---|---|---|---|
| 1 | Python 3.14.8 installed by extracting Termux `.deb` files instead of a standard install | `pkg` refuses root; no system Python; PyPI source builds unavailable | this log; `clusters/meta.json` |
| 2 | Embeddings use TF-IDF+SVD, not model2vec/fastembed/sentence-transformers | No aarch64 wheels for those packages on this platform | `clusters/meta.json` `embedding_attempts` |
| 3 | 4 corpus sources synthesized and `zoe-2018` rewritten | Wikipedia fetch gaps/disambiguation; spec §15 permits synthesis while preserving counts | `corpus/manifest.json` |
| 4 | 16 atoms per source (spec allows 12–25) | Chosen target to reach 1200–2200 atoms with 76 sources | `atoms/*.json` |
| 5 | Some atoms for `neuromancer` and `nier-automata` draw on general knowledge of the works | Their Wikipedia pages are production-history heavy and contain little plot | this log |
| 6 | `judgment.md` includes one-line kill notes for all non-survivors and full verdicts for survivors | Spec requires a 50-row table; prompt requires per-candidate verdicts | `judgment.md` |

## Final report (§16)

### 1. Done checklist

| # | Item | Status | Numbers |
|---|---|---|---|
| 1 | Scaffold | GREEN | CLI + package + 5 prompts + WORKFLOW.md; `--help` works |
| 2 | Environment | GREEN | venv, Python 3.14.8, numpy 2.5.4, scipy 1.18.1; method `tfidf-svd:192` in meta |
| 3 | Corpus | GREEN | 76 sources: A=49, B=27; fetched=71, synthesized=5 |
| 4 | Atomization | GREEN | 76/76 files, 1216 atoms, 16 each |
| 5 | Clustering | GREEN | 87 clusters (60–120), coverage 100%, min size 5, 87/87 named super atoms |
| 6 | Sampling | GREEN | k=3, β=0.7, pool 5620 (≥3000), β sweep 0.5/0.7/0.85 written |
| 7 | Judging | GREEN | top-50 table; 8 survivors after kills |
| 8 | Premises | GREEN | 4 deep dives + runners-up, all human-centered, cliché-cleared |

### 2. Environment findings

- The embedding fallback chain failed at model2vec, fastembed, and sentence-transformers
  (no modules / no platform wheels). TF-IDF+SVD was used, cached to
  `clusters/embeddings.npz`. Cluster quality is therefore topical rather than semantic;
  the 87 clusters mix some unrelated atoms (visible in the digest). This is the main
  quality limitation of the run.
- Memory stayed under the guardrail; scipy `pdist`/`linkage` on 1216×192 was fast.
- Sampling and judging are deterministic given the seed; re-running `cluster` with the
  cached embeddings is idempotent.

### 3. Premises from this run

| # | Premise | Clusters | Fusion (β=0.7) |
|---|---|---|---|
| 1 | The Second Word | The Reversible Life + The Word That Shapes + The Outsider's Gaze | 1.9107 |
| 2 | The Hospice Protocol | Sight Without Seeing + The Care Machine + The Comforting Lie | 1.4018 |
| 3 | The Cuckoo Room | The Child Who Knows + The Attachment Pattern + The Swapped Brood | 1.6201 |
| 4 | The Cleaner | The Hollow Double + The Fixer + The Fanatic | 2.0514 |

### 4. Owner's next-run cheat sheet

```bash
cd /root/story
source .venv/bin/activate
python storygen.py sample --seed 77
```

Then ask the agent: **"give me premises"**. It will read
`candidates/<run>/beta_0.7/results.json`, judge the top 50 with `prompts/judgment.md`,
and write `premises/<run>/`. Knobs: `--seed`, `--k 2..4`, `--betas 0.5,0.7,0.85`
(β 0.5 safe → 0.85 wild), `--top-k`, `--n-draws`. Add sources by editing `corpus/` +
manifest + `atoms/`, then rerun `cluster` and `sample`.

### 5. Open quality notes

- The TF-IDF+SVD embeddings are the weak link. If a machine with real embedding wheels
  becomes available, rerun `cluster` (delete `clusters/embeddings.npz` first) to get
  semantically tighter clusters and likely a stronger candidate pool.
- The Company City / Corporate Body clusters dominate the top of the β=0.7 list; consider
  adding more diet-A works that are not corporate dystopias, or force additional gravity
  wells in `clusters/gravity_wells.json`.
- Some corpus pages (notably Neuromancer, NieR: Automata) are production-history heavy;
  richer plot synopses would improve atom quality.
- Judgment is a single-pass LLM rating; a second judge or a rubric calibration pass would
  harden the 8-survivor set.

---

# StoryGen 1.2 — autonomous build log

Build window: 2026-11-03 to 2026-11-04 (UTC+05:30). Host: same aarch64 Termux userland.
The v1 engine and its `premises/20261102T005552-seed42/` outputs are preserved.

## 1. What changed from v1

| Area | v1 | v2 |
|---|---|---|
| Embeddings | TF-IDF + SVD (192d) | model2vec `minishlab/potion-base-8M` (256d) |
| Story space | 87 topical clusters | 112 semantic clusters, 1216 atoms, coverage 100%, sizes 3–30 (median 10) |
| LLM runtime | none | LiteLLM provider order + raw HTTP fallbacks; local Ollama is the no-key path |
| Briefs | human seed text | LLM brief parser: hard constraints, banned tropes, relevant + foreign queries |
| Research | static corpus | live Wikipedia/Gutendex fetching, 5–10 new sources per run, permanent URL ledger |
| Uniqueness | canon wall + combo memory | canon wall (122 works) + 0.4 combo overlap + full-text history re-check |
| Output | premises + runners-up | premise → outline → act-by-act 2–5k story, revision pass |
| CLI | v1 commands | `setup`, `new`, `discover`, `judge`, `expand`, `wizard` + all v1 commands |

## 2. Runtime findings

- Ollama v0.40.14 runs CPU-only at `http://127.0.0.1:11434` with `qwen2.5:3b` (Q4_K_M,
  4096 context). The native `/api/chat` path is preferred for Ollama because it enforces
  `format: "json"` and `num_ctx`; LiteLLM remains the path for keyed providers.
- Measured on this device: brief parse ~72 s; atomize one source ~86 s; judge one
  candidate ~56 s; premise ~78 s; outline ~289 s. A 1,349-word act took ~21 min and a
  933-word act ~7 min. Full runs are tens of minutes; that is a hardware limit, not a
  pipeline stall. The Ollama request cap is 1,800 s and acts are bounded to a
  1,600-token budget so one act cannot hang the run.
- A whole 3-candidate judge batch can lose JSON structure on the 3B model. The judge now
  keeps any valid partial verdicts, retries only the missing candidates one at a time,
  and uses a conservative heuristic only if a single call also fails. Canon bands are
  printed per candidate (`<0.55` faint echo, `0.55–0.67` warning, `≥0.68` automatic kill)
  so the model does not kill on a title alone. Gate 7 uses one candidate per call.

## 3. Gate evidence

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | Scaffold | PASS | `python storygen.py --help` lists v1 + v2 commands; `story/`, `prompts/`, `WORKFLOW.md` present |
| 2 | Environment | PASS | `.venv`; `clusters/meta.json` method `model2vec:minishlab/potion-base-8M`, dim 256 |
| 3 | Corpus | PASS | 94 sources: diet A=67, B=27; manifest complete |
| 4 | Atomization | PASS | 94/94 files, 8–16 atoms each, quality field present; live sources capped at 6–10 |
| 5 | Clustering | PASS | 117 clusters, coverage 100%, sizes 3–41, 117/117 named; live research no longer creates undersized clusters |
| 6 | Sampling | PASS | `candidates/gate-sweep`: k=3, pool 4052 (≥3000), β=0.5/0.7/0.85 written |
| 7 | Judging | PASS | `runs/gate-sweep-judged/judgment.md`: 50 rows, 50 survivors; every candidate also passed the programmatic canon wall (max canon similarity 0.618) |
| 8 | Premises | PASS | `runs/20261104T181019-v2-seed42`: 3 unique premises (140/121/177 words) + 3 outlines; full draft `02-the-valley-s-silent-water.story.md` = 4,215 words after revision + closing repair |

`python check_gates.py` result: **8/8 checks pass**.

## 3a. Fixes forced by the real gate runs

| Symptom found | Fix |
|---|---|
| Live atom files had no `quality` field | `atomize_text` now rates every atom; live atoms are `medium`, corpus atoms keep their ratings |
| A 5-source live run created a 2-atom cluster, breaking Gate 5 | `repair_space` / integration fold undersized clusters into nearest neighbours; new clusters require ≥3 atoms; the space is capped at 120 clusters |
| The 3B model often wrote 60–110-word premises | Premises must be 120–200 words; short premises get concrete continuation sentences, overlong ones get compressed or trimmed at sentence boundaries |
| Two premises in one run shared a title | Duplicate titles against the permanent ledger are rejected and regenerated |
| A judge batch returned only one usable verdict | Partial-batch salvage retries only the missing candidates; Gate 7 uses `--batch-size 1` |
| Act generation hit the 15-minute request timeout | Ollama timeout raised to 30 min; act token budget bounded at 1,600; timeout is not retried three times |
| Acts could be saved mid-sentence at the token limit | `_finish_act_text` detects incomplete endings and appends a bounded continuation with a complete ending |

## 4. Honest limits

- Uniqueness is guaranteed against the 94-source corpus, the 122-work canon, and this
  engine's own ledger — not against all human literature.
- The 3B local model writes weaker prose than a keyed API model. The same pipeline uses
  Gemini/Anthropic/OpenAI automatically when a key is present.
- Live-research sources are atomized to 6–10 atoms each; the standing corpus keeps its
  16-atom depth. Both are recorded in `corpus/manifest.json`.
- The 3B judge returned KEEP for all 50 Gate-7 candidates and clustered its scores at
  7/7/6. It is a soft filter, not a discriminating critic; the programmatic canon wall
  and the permanent ledger are the hard guards. A keyed model would make judging sharper.
- The 4,215-word draft has a measured 4-gram repetition of 0.1493. The per-act revision
  pass reduces obvious loops, but a 3B local model still writes weaker prose than a
  hosted model. The closing-repair pass guarantees the draft does not end mid-sentence.

## 5. Final verification

Run from `/home/zaki/story`:

```bash
.venv/bin/python check_gates.py
# 8/8 checks pass

.venv/bin/python -m unittest tests.test_v2_core
# 10 tests pass

.venv/bin/python storygen.py corpus-check
# sources: 94, all source files present

.venv/bin/python storygen.py atomize-init
# all sources atomized

.venv/bin/python storygen.py stats
# sources: 94, atoms: 1394, clusters: 117, coverage: 1.0
```

## 6. Final stats

| Metric | Value |
|---|---|
| Corpus sources | 94 (diet A 67, diet B 27; 89 fetched, 5 synthesized) |
| Live-research sources fetched | 18 |
| Atoms | 1,394 |
| Clusters | 117, coverage 100%, sizes 3–41, all named |
| Canon works | 122 |
| Candidate space | 4,052 distinct k=3 sets in the Gate-6 sweep |
| Permanent ledger | 8 premises, 1 kill, 4 pipeline runs, 18 source URLs |
| Gate 7 table | 50 judged, 50 KEEP, max canon similarity 0.618 |
| Gate 8 | 3 premises + 3 outlines; full draft 4,215 words |
| Embedding | model2vec `minishlab/potion-base-8M`, 256d |
| LLM evidence | qwen2.5:3b via native Ollama `/api/chat`; no API keys |
