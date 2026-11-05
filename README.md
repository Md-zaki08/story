# StoryGen 1.2

**An autonomous, self-escalating story engine.** Give it one brief and it researches,
invents, judges, and writes — from a 120–200-word premise and a three-act outline all the
way to a complete 2,000–5,000-word short story.

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.2.0-informational.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)

---

## Contents

- [The concept](#the-concept)
- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Command reference](#command-reference)
- [How it works](#how-it-works)
- [The idea space](#the-idea-space)
- [How originality is enforced](#how-originality-is-enforced)
- [Live research](#live-research)
- [LLM providers and configuration](#llm-providers-and-configuration)
- [Output layout](#output-layout)
- [The permanent ledger](#the-permanent-ledger)
- [Reproducibility](#reproducibility)
- [Testing and verification](#testing-and-verification)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Project structure](#project-structure)
- [Third-party content](#third-party-content)
- [Versioning](#versioning)
- [License](#license)

---

## The concept

Most story generators start from a prompt and ask a language model to “be creative.” That
produces fluent prose, but it tends to collapse toward the same familiar shapes: the
chosen one, the prophecy, the generic dystopia, the AI that becomes human.

StoryGen takes a different route. It treats originality as a **search problem over an
explicit idea space**.

1. A large collection of narrative material — films, novels, games, philosophy,
   biology, economics, folklore, history — is broken into small **narrative atoms**:
   reusable fragments of situation, image, conflict, relationship, or mechanism.
2. The atoms are embedded and clustered into semantic neighbourhoods. Each cluster is a
   *domain of narrative pressure*: grief simulation, actuarial coldness, inheritance
   traps, repair ethics, and so on.
3. The engine samples **combinations of clusters that usually do not meet**, then scores
   each combination for internal coherence and for how under-used that pairing is.
4. Hard filters remove anything too close to a famous work or to something the engine has
   already written.
5. A language model judges the survivors and, only then, writes the premise, outline, and
   optional full draft.

The engine does **not** train a model. The idea space is inspectable on disk: atoms,
embeddings, clusters, canon fingerprints, candidate scores, and judgments are all saved.
The LLM is the writer and the critic, not the source of the search space.

The result is a pipeline that is deterministic where it should be (sampling, scoring,
uniqueness checks) and generative where it needs to be (research queries, judging,
premise, outline, prose).

---

## What it does

| Capability | Detail |
|---|---|
| **Brief → premise** | Parses constraints, tone, setting, must-include and must-avoid items, then writes a 120–200-word premise |
| **Brief → outline** | Three acts with beats, characters, setting rules, and an ending |
| **Brief → full draft** | 2,000–5,000 words, act by act, with a revision pass and automatic closing repair |
| **Live research** | Fetches fresh Wikipedia and Project Gutenberg sources on every run |
| **Self-escalation** | If too few candidates survive, it raises diversity, widens research, and tries again — up to three rounds |
| **Permanent memory** | SQLite ledger prevents repeating its own premises and source URLs |
| **Canon wall** | 122 famous works are fingerprinted; close matches are rejected programmatically |
| **Provider agnostic** | Gemini, Anthropic, OpenAI, or local Ollama; auto-detected at runtime |
| **Autonomous mode** | `discover` invents its own brief when you do not want to supply one |
| **Interactive mode** | `wizard` walks through the same options with prompts |

The default run produces **three premises and three outlines**. Add `--full` to draft the
stories.

---

## Requirements

- **Python 3.10+** (tested on Python 3.14.4)
- **~2 GB free disk** for the Python environment and embedding model
- **Network access** for live research and for downloading the embedding model on first
  use
- **One LLM provider**:
  - a Gemini, Anthropic, or OpenAI API key, **or**
  - a local [Ollama](https://ollama.com/) installation (free, offline, slower)

No API keys are needed for research. Wikipedia and Project Gutenberg are accessed
directly.

---

## Installation

```bash
git clone https://github.com/Md-zaki08/story.git
cd story

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Check the runtime:

```bash
python storygen.py setup
```

This reports the available provider, the embedding backend, the number of canon works,
and the current ledger state. It does not make a paid API call.

### Option A — local Ollama (free)

Install Ollama from <https://ollama.com/download>, then:

```bash
ollama serve
ollama pull qwen2.5:3b
```

Or let StoryGen do it:

```bash
python storygen.py setup --pull --test
```

The default local model is `qwen2.5:3b`. It is small enough to run on a CPU, but it is
slow and its prose is weaker than a hosted model. Change `models.ollama` in
`llm_config.json` to any model you have pulled.

### Option B — hosted API

```bash
export GEMINI_API_KEY="..."
# or
export ANTHROPIC_API_KEY="..."
# or
export OPENAI_API_KEY="..."
```

StoryGen checks providers in this order: **Gemini → Anthropic → OpenAI → Ollama**. The
first available one wins. You can force one with `--provider`.

### First-run note

The first embedding call downloads `minishlab/potion-base-8M` and caches it in the
Hugging Face cache. This can take a minute. The repository already ships with
`clusters/embeddings.npz`, so normal runs do not need to recompute embeddings.

---

## Quick start

```bash
# Three premises + three outlines
python storygen.py new "A horror western about a memory broker in a dying mining town"

# Premises only, with hard constraints
python storygen.py new "1970s Punjab; a woman named Mara; no prophecy; wry tone" \
  --premises-only --count 2

# Full drafts (2,000–5,000 words each)
python storygen.py new "A quiet science-fiction story about a repair engineer who
 inherits a house that remembers its owners" --full --target-words 3500

# Let the engine invent its own brief
python storygen.py discover --premises-only --count 1

# Interactive mode
python storygen.py wizard
```

A run prints its progress and saves everything under `runs/<run-id>/`. The published
copies go to `premises/<run-id>/`.

---

## Command reference

```bash
python storygen.py --help
python storygen.py --version
```

| Command | Purpose |
|---|---|
| `new "<brief>"` | Full automatic run from a brief |
| `discover` | The engine writes its own brief, then runs |
| `expand --run <id> --index N` | Grow an existing premise into an outline or full story |
| `wizard` | Interactive prompts for `new`, `discover`, and `expand` |
| `setup [--pull] [--test]` | Check providers, embedder, canon, and ledger; optionally install/test Ollama |
| `judge --sample <name>` | Rate the top-N candidates of an existing sample |
| `ledger-stats` | Show the permanent anti-repetition memory |
| `name-clusters` | LLM-name clusters that still use keyword fallback names |
| `corpus-check` | Validate the corpus manifest and files |
| `atomize-init` | List sources still missing atoms |
| `cluster [--reembed] [--auto-name]` | Re-embed, re-cluster, and name the idea space |
| `sample` | Build and score candidates without writing |
| `stats` | Report corpus, atom, cluster, and pool statistics |
| `check_gates.py` | Verify the eight build-quality gates |

### Options for `new` and `discover`

| Flag | Default | Meaning |
|---|---:|---|
| `--full` | off | Draft the complete story (2–5k words) |
| `--premises-only` | off | Stop after the logline and premise |
| `--k` | `3` | Clusters per combination (`2`, `3`, or `4`) |
| `--beta` | auto | Coherence/strangeness trade-off; auto-escalates `0.7 → 0.8 → 0.9` |
| `--sources` | `8` | Fresh web sources to fetch this run |
| `--count` | `3` | Premises to keep |
| `--no-escalate` | off | One judging round only |
| `--no-research` | off | Skip live web research |
| `--provider` | auto | `gemini`, `anthropic`, `openai`, or `ollama` |
| `--seed` | `42` | Sampling seed |
| `--target-words` | `3000` | Target length for a full draft |

---

## How it works

```
                         ┌──────────────────────┐
                         │        brief         │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │   brief parser (LLM) │
                         │ constraints, tone,   │
                         │ must-include/avoid   │
                         └──────────┬───────────┘
                                    │
              ┌─────────────────────▼─────────────────────┐
              │        live research collector            │
              │ Wikipedia + Gutenberg + LLM query design  │
              │ 5–10 fresh sources per run                │
              └─────────────────────┬─────────────────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  atomizer (LLM)      │
                         │  6–25 narrative      │
                         │  atoms per source    │
                         └──────────┬───────────┘
                                    │
              ┌─────────────────────▼─────────────────────┐
              │  embedding + clustering (model2vec)      │
              │  ~1,400 atoms → 117 semantic clusters     │
              └─────────────────────┬─────────────────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  anchored sampler    │
                         │  20,000 draws, k=3   │
                         │  coherence + rarity  │
                         └──────────┬───────────┘
                                    │
              ┌─────────────────────▼─────────────────────┐
              │  hard filters                            │
              │  canon wall · ledger · constraints       │
              └─────────────────────┬─────────────────────┘
                                    │
                         ┌──────────▼───────────┐
                         │   LLM judge          │
                         │ coherence/freshness/ │
                         │ viability            │
                         └──────────┬───────────┘
                                    │
                     too few survivors? ──yes──► escalate research,
                                    │            β, k; retry (≤3 rounds)
                                    no
                                    │
                         ┌──────────▼───────────┐
                         │  premise (120–200 w) │
                         │  outline (3 acts)    │
                         │  optional full draft │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │ save run + publish   │
                         │ update ledger        │
                         └──────────────────────┘
```

### 1. Brief parsing

The LLM converts the brief into a structured document: genre, tone, setting, time period,
must-include items, must-avoid items, banned tropes, themes, and search queries. Sparse
briefs produce broad searches; detailed briefs produce tightly constrained ones. The
structured document is saved as `brief.json` and drives every later stage.

### 2. Live research

The collector turns the brief and its themes into several search intents, deliberately
mixing **relevant** queries with **foreign** ones. It searches Wikipedia and Project
Gutenberg, skips URLs already in the ledger, downloads the best candidates, and keeps
fetching until it has enough usable sources. Research failures are non-fatal: the standing
corpus is always available.

### 3. Atomization

Each new source is read by the LLM and broken into 6–10 compact narrative atoms. Atoms
are deliberately smaller than a plot: a pressure, an image, a relationship, a mechanism,
a moral trade-off. Corpus sources keep a deeper 16-atom treatment.

### 4. Embedding and clustering

Atoms are embedded with `model2vec` (`minishlab/potion-base-8M`, 256 dimensions) and
clustered by cosine similarity. The shipped space has **1,394 atoms in 117 clusters**,
with 100% coverage and a minimum cluster size of 3. Tiny live-research clusters are folded
into their nearest neighbours so the space stays stable.

### 5. Anchored sampling

A candidate is a set of `k` clusters (default 3). At least one cluster is **anchored** to
the brief; the remaining slots are chosen to be as unrelated as possible. This is the
central creative move: a familiar pressure from the brief collides with material from a
different domain.

### 6. Scoring

Candidates are ranked by:

```
fusion        = (1 − β) · z(coherence) + β · z(unavailability)
coherence     = 0.5 · z(mean pairwise cosine) + 0.5 · z(co-occurrence bridging)
unavailability = 0.65 · z(pair rarity) + 0.35 · z(cliché distance)
```

- **Coherence** asks whether the pieces can plausibly belong to one story.
- **Unavailability** asks how rarely the pairing occurs in the corpus and how far it is
  from known clichés.
- **β** slides between safe (0.5) and wild (0.85). The default run starts at 0.7 and
  escalates if needed.

The sampler performs 20,000 draws, deduplicates sets, and writes the top candidates to
`candidates/<run-id>/beta_*/results.json`.

### 7. Hard filters

Before any LLM sees a candidate, the programmatic checks run:

- **Canon wall** — embed the candidate and compare it with 122 famous works. Above the
  kill threshold (0.68), the candidate is rejected regardless of what the judge says.
- **Permanent ledger** — reject combinations that overlap too much with past output.
- **Constraint checks** — reject candidates that cannot satisfy the brief's hard
  requirements.

### 8. LLM judging

Survivors go to the judge, which rates **coherence**, **freshness**, and **viability** on
a 1–10 scale and returns a verdict plus a short reason. The judge is a soft filter; the
canon wall and ledger are the hard guards. Partial or malformed batch responses are
salvaged, and missing candidates are retried individually.

### 9. Self-escalation

If fewer than `--count` candidates survive, the engine does not lower the bar. It:

1. raises β toward strangeness,
2. changes `k`,
3. runs additional research with new foreign queries,
4. re-anchors and judges another round.

This repeats for up to three rounds. If the run still cannot meet the target, it reports
an **honest shortfall** and saves what genuinely survived.

### 10. Writing

- **Premise** — 120–200 words, with title, logline, built-from clusters, and a
  why-fresh explanation. Short premises are extended with concrete detail; overlong ones
  are compressed at sentence boundaries.
- **Outline** — three acts with beats, characters, setting rules, and an ending.
- **Full draft** — acts are written in sequence with a rolling recap. A revision pass
  removes obvious repetition. If an act hits the token limit mid-sentence, a closing
  continuation repairs it before saving.

### 11. Publishing and memory

The run record, premise, outline, and optional story are written to `runs/<run-id>/` and
copied to `premises/<run-id>/`. The premise is embedded and checked once more against the
entire ledger before it is recorded.

---

## The idea space

The engine ships with a prebuilt space:

| Component | Count |
|---|---:|
| Corpus sources | 94 (67 narrative, 27 cross-domain) |
| Narrative atoms | 1,394 |
| Semantic clusters | 117 |
| Cluster coverage | 100% |
| Cluster size range | 3–41 atoms |
| Canon works | 122 |
| Candidate sets in the reference sweep | 4,052 |

The corpus mixes:

- **Narrative sources** — films, television, novels, games, and stories about artificial
  intelligence, memory, identity, and human connection.
- **Cross-domain sources** — philosophy of mind, attachment theory, ecology, economics,
  linguistics, anthropology, biology, and history.

Atoms are stored in `atoms/`; clusters and their centroids in `clusters/`. The cluster
space is inspectable JSON plus a NumPy embedding cache, so you can audit why a candidate
was proposed.

---

## How originality is enforced

There are four independent layers, and they fail in different ways on purpose:

| Layer | What it catches | Where it lives |
|---|---|---|
| **Cross-domain sampling** | Obvious, overused combinations | `story/sample.py` |
| **Canon wall** | Close matches to famous works | `canon/canon.json`, `story/judge.py` |
| **Permanent ledger** | Repeating the engine's own output | `ledger.db`, `story/ledger.py` |
| **LLM judge** | Flat, incoherent, or unviable ideas | `story/judge.py`, `prompts/` |

The canon wall is the important one. A candidate may look fresh to a small local model but
still be a thin disguise for a well-known story. The wall compares embeddings against 122
famous works and kills anything above the threshold. In the shipped Gate-7 sweep, the
maximum canon similarity among survivors was **0.618**, below the **0.68** kill line.

**Honest limit:** this guarantees freshness against the shipped corpus, the canon list,
and your own history. It cannot prove that no human has ever written something similar.
It does guarantee that no recognized famous work or previously generated premise survives
the pipeline unchanged.

---

## Live research

Research is built in and needs no API key:

- Wikipedia search and plaintext extracts
- Project Gutenberg / Gutendex
- LLM-designed relevant and deliberately foreign queries

Every run records what it fetched in `research.json`: title, URL, diet, atom count, and
whether it was new. Already-fetched URLs are skipped through the ledger.

The collector over-discovers and then keeps fetching until it has the requested number of
**usable** sources. Fetch failures, thin pages, and disambiguation pages are skipped
rather than crashing the run.

Disable research with `--no-research` when you want a fully offline run.

---

## LLM providers and configuration

Provider order and models live in `llm_config.json`:

```json
{
  "provider_order": ["gemini", "anthropic", "openai", "ollama"],
  "models": {
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4.1-mini",
    "ollama": "qwen2.5:3b"
  },
  "stages": {
    "collector": {"temperature": 0.6, "max_tokens": 2200},
    "judge":     {"temperature": 0.2, "max_tokens": 2500},
    "writer":    {"temperature": 0.85, "max_tokens": 4200}
  },
  "ollama": {"host": "http://127.0.0.1:11434", "num_ctx": 4096},
  "request_timeout": 1800,
  "litellm": true
}
```

Environment variables:

| Provider | Variables |
|---|---|
| Gemini | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Ollama | none; uses `ollama.host` |

Ollama uses its native `/api/chat` endpoint so `format: "json"` and `num_ctx` are honored.
The other providers go through LiteLLM. If LiteLLM is unavailable, the engine falls back
to direct HTTP for the supported providers.

See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for every key and stage.

---

## Output layout

```
runs/<run-id>/
  brief.json                 parsed brief and constraints
  research.json              sources fetched this run, new atoms/clusters
  run.json                   full run record and premise metadata
  judgment.md                candidate table with scores and verdicts
  judgments_beta_*.json      raw judge output
  01-<title>.md              premise
  01-<title>.outline.md      three-act outline
  01-<title>.story.md        full draft (with --full)

premises/<run-id>/           published copies of the above
candidates/<run-id>-r1/
  beta_0.7/results.json      ranked candidate sets, scores, cluster names
  config.json                seed, k, pool size, anchors, history size
```

A premise file contains:

- title and logline
- the 120–200-word premise
- the cluster combination it was built from
- a short “why fresh” explanation
- the judge's scores and reason

An outline contains:

- title page and logline
- characters
- three acts, each with beats
- setting rules
- the ending the story is moving toward

---

## The permanent ledger

`ledger.db` is a SQLite database created at runtime. It records:

- every pipeline run and its brief
- every saved premise (title, logline, text, clusters, fusion score)
- every research source URL already fetched
- rejected/killed candidates

It serves two purposes: **anti-repetition** and **research de-duplication**. A fresh clone
starts with no ledger unless one is present; the engine creates it on first use.

To reset history intentionally:

```bash
mv ledger.db ledger.db.bak
python storygen.py ledger-stats
```

Do this only when you actually want the engine to forget its previous output. The
repository's `.gitignore` excludes `ledger.db` because it is local runtime state.

---

## Reproducibility

- `--seed` controls candidate sampling.
- The corpus, atoms, embeddings, clusters, and canon are versioned in the repository.
- `config.json` in each candidate directory records the seed, `k`, β, pool size, anchors,
  and history size.
- LLM calls are **not** deterministic by default; temperatures are set per stage. A
  hosted model with temperature 0 will be more reproducible than a local 3B model.

To reproduce a sampling run without writing:

```bash
python storygen.py sample --seed 42 --k 3 --beta 0.7 --top-k 50
```

---

## Testing and verification

```bash
# Unit tests (no LLM required)
python -m unittest tests.test_v2_core -v

# Build-quality gates
python check_gates.py

# Corpus and space statistics
python storygen.py corpus-check
python storygen.py stats
```

The unit tests cover:

- canon collision (a Matrix-like premise is rejected)
- ledger duplicate injection
- combination-overlap memory
- brief-constraint enforcement
- premise-length repair
- partial judge-verdict salvage
- truncated-act closing repair

`check_gates.py` verifies the eight build gates described in
[`BUILD_LOG.md`](BUILD_LOG.md): scaffold, environment, corpus, atomization, clustering,
sampling, judging, and premise delivery.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| “No LLM provider is available” | Set an API key, or run `python storygen.py setup --pull --test` |
| Ollama pull is slow | The model is ~1.9 GB; re-run the same command to resume |
| “Honest shortfall” | Fewer candidates survived than requested. The engine escalates automatically; try a more specific brief, `--sources 10`, or a stronger provider |
| No research sources found | Check network access; the standing corpus is still used |
| Embedding download fails | Check network/Hugging Face access; the shipped `clusters/embeddings.npz` is enough for normal runs |
| Stale cluster names | `python storygen.py name-clusters` |
| Corrupt embedding cache | Delete `clusters/embeddings.npz`, then `python storygen.py cluster --reembed` |
| Full draft is slow on CPU | Expected with a 3B local model; use a hosted provider or a smaller target |
| Draft ended mid-sentence | The closing-repair pass should prevent this; if it happens, re-run `expand --full` |

More detail: [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

---

## Limitations

- **The freshness guarantee is bounded.** It covers the 94-source corpus, the 122-work
  canon, and your ledger — not all of human literature.
- **A small local judge is permissive.** In the reference Gate-7 run, `qwen2.5:3b` kept all
  50 candidates and clustered its scores at 7/7/6. The canon wall and ledger are the real
  filters. A hosted model makes judging meaningfully sharper.
- **CPU-only drafting is slow.** A 1,349-word act took about 21 minutes on the reference
  machine. Full drafts can take an hour or more.
- **Local 3B prose is weaker** than hosted-model prose. The revision pass reduces
  repetition but does not make a small model into a stylist.
- **Research depends on public sources.** Wikipedia and Gutenberg availability, rate
  limits, and network quality affect the run.
- **LLM costs are real** when using a hosted provider. The collector and judge make many
  calls; watch your usage.
- **This is a drafting engine, not a publisher.** Human editing is still required for
  anything you intend to release.

---

## Project structure

```
storygen.py                 CLI entry point
check_gates.py              eight-gate build verifier
llm_config.json             provider, model, stage, and timeout configuration
requirements.txt            Python dependencies
VERSION                     release version
CHANGELOG.md                release history
LICENSE / NOTICE            Apache 2.0 terms and attribution

story/
  __init__.py               package version
  io_utils.py               files, JSON, slugs, word counts
  embeddings.py             model2vec → fallback embedding chain
  cluster_atoms.py          atom clustering and naming
  sample.py                 candidate generation, scoring, fusion
  collector.py              live research, atomization, space integration
  judge.py                  canon wall, LLM judging, judgment tables
  writer.py                 premise, outline, full draft, repairs
  ledger.py                 SQLite permanent memory
  llm.py                    provider runtime (LiteLLM / direct HTTP)
  stats.py                  normalization and z-scores

atoms/                      narrative atoms per source + all.json
corpus/                     source texts and manifest
clusters/                   cluster definitions, names, embeddings, metadata
canon/                      famous-work fingerprints
candidates/                 sampling runs and scores
runs/                       full pipeline runs
premises/                   published premises, outlines, stories
prompts/                    LLM prompt templates
tests/                      unit tests
docs/                       architecture, configuration, troubleshooting
```

---

## Third-party content

The **code and original documentation** in this repository are licensed under the Apache
License 2.0 (see `LICENSE`).

The `corpus/` directory contains short excerpts and summaries derived from public
sources:

- Wikipedia text is available under the **Creative Commons Attribution-ShareAlike**
  license. Source URLs are recorded in `corpus/manifest.json`.
- Project Gutenberg texts are in the **public domain** in the United States.
- The canon list stores titles and short descriptions of famous works for similarity
  checking; it does not reproduce their text.

Those third-party materials remain under their original licenses. The Apache 2.0 license
does not override them. If you redistribute the corpus, keep the source URLs and
attribution in `corpus/manifest.json`.

---

## Versioning

This release is **1.2.0**. See [`CHANGELOG.md`](CHANGELOG.md) for the change history.

- `1.2.0` — documentation, licensing, packaging, and public-release preparation; the
  working engine and its verified gates are unchanged.
- Earlier internal iterations are described in [`BUILD_LOG.md`](BUILD_LOG.md).

---

## License

Apache License 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

Copyright 2026 Md Zaki.
