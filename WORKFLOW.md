# WORKFLOW — StoryGen 1.2

StoryGen is a self-contained, fully automated story engine. One command takes a brief
and produces premises, outlines, and (with `--full`) a complete short-story draft. No
agent is needed once it is running.

- Concept and architecture: [`README.md`](README.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Configuration reference: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)
- Troubleshooting: [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)

## Quick start (this machine)

```bash
cd /home/zaki/story
source .venv/bin/activate

# 1. Check the runtime (embedder, provider, canon, ledger)
python storygen.py setup

# 2. If Ollama is installed but the model is missing
python storygen.py setup --pull --test

# 3. Make stories
python storygen.py new "A horror western about a memory broker in a dying mining town"
python storygen.py new "A horror western about a memory broker in a dying mining town" --full
python storygen.py new "Brief with hard constraints: set in 1970s Punjab; must include a woman named Mara; no prophecy; tone wry" --premises-only
```

`new` is fully automatic: parse brief → live research → atomize → sample → judge →
escalate if needed → write premises + outlines → save. With `--full` it also drafts the
story act by act and runs a revision pass. Premises are enforced at 120–200 words; an act
that hits the token limit mid-sentence receives an automatic closing continuation.

## Outputs

Every run gets `runs/<run-id>/`:

| File | Contents |
|---|---|
| `brief.json` | the parsed brief: hard constraints, banned tropes, search intents |
| `research.json` | fresh sources fetched this run and any new atoms/clusters |
| `run.json` | complete run record, premise metadata, outline/story pointers |
| `01-<title>.md` | premise: title, logline, premise, built-from, why-fresh, judge reasons |
| `01-<title>.outline.md` | title page, characters, 3 acts with beats, setting rules, ending |
| `01-<title>.story.md` | full draft (only with `--full`) |
| `judgment.md` | Gate-7 table: coherence / freshness / viability, canon max, verdict, reason |

A copy of the premise, outline, and story files is published to
`premises/<run-id>/`. Sampling artifacts stay in
`candidates/<run-id>-rN/beta_*/results.json`; judgments live in
`runs/<run-id>/judgments_beta_*.json`.

## Commands

```bash
python storygen.py new "<brief>" [options]
python storygen.py discover [options]          # engine invents its own brief
python storygen.py expand --run <run-id> --index 1 --full
python storygen.py ledger-stats                # permanent anti-repeat memory
python storygen.py wizard                      # interactive prompts
python storygen.py setup [--pull] [--test]     # runtime check / install
python storygen.py name-clusters               # LLM-name keyword fallback clusters
python storygen.py judge --sample gate-sweep --beta 0.7 --top 50 --batch-size 1
                                               # Gate-7 table for an existing sample
python check_gates.py                          # verify all 8 Definition-of-Done gates
```

Options for `new` / `discover`:

| Flag | Meaning |
|---|---|
| `--full` | draft the whole story (2–5k words) |
| `--premises-only` | stop after logline + premise |
| `--k 2..4` | clusters per combination (default 3) |
| `--beta 0.5..0.9` | coherence vs. strangeness (default escalates 0.7 → 0.8 → 0.9) |
| `--sources N` | fresh web sources fetched this run (default 8) |
| `--count N` | premises to keep (default 3) |
| `--no-escalate` | one judging round only |
| `--no-research` | skip live web research |
| `--provider X` | `gemini`, `anthropic`, `openai`, or `ollama` |
| `--seed N` | reproducible sampling seed |
| `--target-words N` | full-draft length target (default 3000) |

## Switching LLM providers

Default order is **Gemini → Anthropic → OpenAI → Ollama**. The engine picks the first
available provider automatically. To add a paid/free API, just set a key:

```bash
export GEMINI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export OPENAI_API_KEY="..."
```

Models and stage temperatures live in `llm_config.json`. Edit `models` to pin a different
model, or use `--provider` per run:

```bash
python storygen.py new "..." --provider ollama
python storygen.py new "..." --provider gemini
```

The Ollama fallback is local and free. This machine uses `qwen2.5:3b` at 4096 context, CPU
only. It is slow and prose is weaker than an API model; that is a hardware limit, not a
pipeline limit. Swap `models.ollama` in `llm_config.json` to any pulled model.

## How uniqueness is enforced

Four independent gates:

1. **Cross-domain combination space** — 117 clusters, k=3 → hundreds of thousands of
   possible sets;
   brief-relevant clusters anchor at least one slot per candidate, while the other slots
   stay deliberately unrelated.
2. **Fresh web DNA** — every run searches Wikipedia/Project Gutenberg, fetches new
   sources, atomizes them, and adds them to the living space. Already-fetched URLs are
   skipped via the SQLite ledger.
3. **Canon wall** — `canon/canon.json` embeds 122 famous works/arcs. A candidate whose
   closest canon neighbor is too close is killed whether or not the LLM notices.
4. **Permanent memory** — `ledger.db` stores every premise ever output. Candidate combos
   overlapping past premises are filtered, and written premises are re-embedded and
   checked against the entire history before being saved. Duplicate-injection is a
   regression test.

Honest limit: this guarantees freshness against the corpus, the canon, and your own
output history. It cannot prove a story matches nothing ever written by any human. It
does guarantee no recognizable famous work or previously generated premise survives.

## Live research

No API keys are needed for research. The collector uses:

- Wikipedia search + plaintext extracts
- Project Gutenberg / Gutendex
- LLM-generated relevant and deliberately foreign search queries

Briefs can specify a little or a lot. `must_include`, `must_avoid`, and `banned_tropes`
are extracted and enforced in the writer; a premise that omits a hard constraint is
regenerated, then rejected rather than silently shipped.

## Lower-level commands

```bash
python storygen.py corpus-check
python storygen.py atomize-init
python storygen.py cluster [--reembed] [--auto-name] [--apply-names]
python storygen.py sample --seed 77 --beta 0.85 --top-k 50
python storygen.py stats
```

`cluster --reembed --auto-name` re-embeds with model2vec, re-clusters into the 60–120
band, reuses names by atom-overlap Jaccard, then LLM-names the rest.

## Tests

```bash
.venv/bin/python -m unittest tests.test_v2_core -v
```

Covers canon collision (The Matrix dies), ledger duplicate injection, combo-overlap
memory, brief-constraint enforcement, premise-length repair, partial-verdict salvage, and
closing repair.

## Troubleshooting

- **“No LLM provider is available”** — set an API key, or run
  `python storygen.py setup --pull --test`.
- **Ollama pull is slow** — the model is ~1.9 GB; resume by re-running the same command.
- **A run reports an honest shortfall** — fewer than 3 candidates survived. The engine
  raises β, changes k, and hunts new domains for up to 3 rounds. It never lowers the
  freshness bar. Try a more specific brief, `--sources 10`, or a stronger provider.
- **No research sources found** — the standing 94-source corpus is used; check network.
- **Wrong / stale cluster names** — run `python storygen.py name-clusters`.
- **Embedding error** — delete `clusters/embeddings.npz` and run
  `python storygen.py cluster --reembed`.

See [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) for the longer list.
