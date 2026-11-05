# StoryGen 1.2 — Personal User Guide

> This is the hands-on user guide. It is written for the reference machine and checkout,
> but the commands, workflows, and troubleshooting steps apply to any copy of StoryGen 1.2.

---

## 0. The one-page cheat sheet

```bash
cd /home/zaki/story
source .venv/bin/activate

# Check everything
python storygen.py setup

# Fast idea session (premises only, one round)
python storygen.py new "your brief" --premises-only --no-escalate --count 2 --sources 4

# Normal run: 3 premises + 3 outlines
python storygen.py new "your brief"

# Full drafts: 2,000–5,000 words each
python storygen.py new "your brief" --full --target-words 3000

# Grow an existing premise
python storygen.py expand --run <run-id> --index 1
python storygen.py expand --run <run-id> --index 1 --full

# Let the engine invent a brief
python storygen.py discover --premises-only --count 1

# Interactive
python storygen.py wizard

# Memory and health
python storygen.py ledger-stats
python storygen.py stats
python -m unittest tests.test_v2_core -v
python check_gates.py
```

Expected on this CPU-only machine:

| Task | Approx. time |
|---|---|
| `setup` | 10–60 s |
| Brief parsing | ~1 min |
| One research source + atomization | ~1.5 min |
| 12-candidate judging round | ~10–15 min |
| One premise | ~1–2 min |
| One outline | ~5 min |
| Full draft (3 acts + revision) | ~45–75 min |
| 50-candidate Gate-7 judge | ~50 min |

Outputs land in:

```
runs/<run-id>/          full record
premises/<run-id>/      human-facing copies
candidates/<run-id>/    sampling scores
```

---

## 1. What StoryGen is

StoryGen is an **autonomous story-idea engine**. Give it a brief — one sentence or a page
of constraints — and it:

1. Parses the brief into structured constraints.
2. Researches fresh material from Wikipedia and Project Gutenberg.
3. Breaks sources into small narrative atoms.
4. Embeds and clusters the atoms into an explicit idea space.
5. Samples combinations of clusters that normally do not meet.
6. Filters them through a canon wall and a permanent ledger.
7. Asks an LLM to judge the survivors.
8. Writes a 120–200-word premise and a three-act outline.
9. Optionally writes a complete 2,000–5,000-word draft.

It does **not** train a model. The creative search is a file-backed, inspectable system.
The LLM is the reader, judge, and writer — not the database of ideas.

### What it is good at

- Producing premises that are not the obvious first idea.
- Combining a familiar emotional pressure with an unrelated domain.
- Enforcing hard brief constraints (names, setting, banned tropes).
- Keeping a permanent memory so it does not repeat itself.
- Running unattended for an hour.

### What it is not

- A prose stylist on a 3B local model.
- A replacement for human editing.
- A guarantee that no human has ever written something similar.
- A fast interactive chatbot. A full draft is a batch job.

---

## 2. The mental model

```
source text
   ↓  atomizer
narrative atoms              small, reusable pieces of situation/image/conflict
   ↓  embeddings + clustering
clusters                     semantic neighbourhoods of atoms
   ↓  sampling
candidate                    a set of 3 clusters
   ↓  hard filters
survivor                     passes canon wall + ledger + constraints
   ↓  LLM judge
kept candidate               rated coherent, fresh, viable
   ↓  writer
premise → outline → draft
```

### Why clusters, not whole plots?

Whole plots are too close to existing stories. A cluster is a *pressure* or *domain* —
“grief simulation”, “actuarial coldness”, “the repair ethic”. Combining pressures leaves
room for a new story; copying plots does not.

### Why three clusters?

- Two clusters often collapse into a simple A-meets-B premise.
- Four clusters tend to become incoherent.
- Three is the default sweet spot. `--k 2` is safer; `--k 4` is stranger.

### The three guards

| Guard | Type | What it does |
|---|---|---|
| Canon wall | hard, programmatic | Rejects candidates too close to 122 famous works |
| Permanent ledger | hard, programmatic | Rejects repeats of your own premises and source URLs |
| LLM judge | soft | Rates coherence, freshness, viability; can be wrong |

The local 3B judge is **permissive**. In the reference Gate-7 run it kept all 50
candidates and clustered its scores at 7/7/6. Trust the canon number and your own reading
more than the judge's “KEEP”.

---

## 3. This machine

| Item | Value |
|---|---|
| Project root | `/home/zaki/story` |
| Python | 3.14.4 in `.venv` |
| LLM runtime | Ollama 0.40.14, native `/api/chat` |
| Model | `qwen2.5:3b` (Q4, 1.9 GB, 4096 context) |
| Acceleration | CPU only |
| Ollama binary | `.ollama/bin/ollama` |
| Ollama host | `http://127.0.0.1:11434` |
| Request timeout | 1,800 s |
| Corpus | 94 sources (67 narrative, 27 cross-domain) |
| Atoms | 1,394 |
| Clusters | 117, coverage 100%, sizes 3–41 |
| Canon works | 122 |
| Ledger | 8 premises, 4 runs, 18 sources (at the time of writing) |

The `.venv/` and `.ollama/` directories are local runtime, not repository content. Do not
commit them.

---

## 4. First-time setup

### 4.1 Activate the environment

```bash
cd /home/zaki/story
source .venv/bin/activate
python --version
```

### 4.2 Check the runtime

```bash
python storygen.py setup
```

You should see something like:

```
== StoryGen 1.2.0 setup ==
providers available: ollama
provider order: gemini -> anthropic -> openai -> ollama
models: {... "ollama": "qwen2.5:3b"}
ollama reachable: True
ollama models: qwen2.5:3b
embeddings: model2vec:minishlab/potion-base-8M, dim=256
canon: 122 famous works indexed
ledger: {...}
ollama binary: /home/zaki/story/.ollama/bin/ollama
```

If `providers available` says `NONE`, either Ollama is not running or no API key is set.

### 4.3 Start Ollama and pull the model

```bash
python storygen.py setup --pull --test
```

`--pull` starts the local server and runs `ollama pull qwen2.5:3b`. `--test` sends one
tiny request and prints the answer. The model is ~1.9 GB; a slow connection is normal.

Manual equivalent:

```bash
.ollama/bin/ollama serve
.ollama/bin/ollama pull qwen2.5:3b
```

### 4.4 Add a hosted provider (optional)

```bash
export GEMINI_API_KEY="..."
# or
export ANTHROPIC_API_KEY="..."
# or
export OPENAI_API_KEY="..."
```

Then force it if you want:

```bash
python storygen.py new "..." --provider gemini
```

### 4.5 Sanity checks

```bash
python storygen.py --version
python storygen.py stats
python storygen.py ledger-stats
python -m unittest tests.test_v2_core -v
python check_gates.py
```

Expected:

- version `StoryGen 1.2.0`
- `sources: 94`, `atoms: 1394`, `clusters: 117`, `coverage: 1.0`
- 10 unit tests pass
- 8/8 gates pass

---

## 5. Your first run

### 5.1 A fast smoke test

This is the cheapest way to confirm the whole pipeline works:

```bash
python storygen.py new "A quiet story about a repair engineer who inherits a house that remembers its owners" \
  --premises-only --no-escalate --count 1 --sources 2
```

It still parses the brief, researches, samples, judges, and writes one premise, but skips
outlines and escalation. Expect roughly 5–15 minutes on this machine, depending on how
many sources are fetched and judged.

### 5.2 A normal run

```bash
python storygen.py new "A horror western about a memory broker in a dying mining town"
```

Defaults: 3 premises + 3 outlines, 8 research sources, automatic escalation, seed 42.

### 5.3 What the log means

```
== run 20261105T...-v2-seed42 ==
[collector] brief: ... | searches=6 relevant / 3 foreign
[collector] 1/8 A :: Title -> 9 atoms
[embeddings] embedding 1394 texts
[collector] integrated 30/30 new atoms (0 new clusters...)
[sample] k=3, seed=42, draws=20000...
[sample] pool=4052...
[judge] KEEP 22.04 :: Cluster A + Cluster B + Cluster C (coh 7/fresh 7)
[pipeline] round 1: 12 judged, 12 kept, total 3/3
-- writing premise 1/3 --
[writer] premise: Title (155 words) :: ...
[pipeline] saved: runs/<id>/01-title.md
```

- `pool` is the number of distinct candidate sets after sampling.
- `coh`/`fresh` are the judge's 1–10 scores.
- “honest shortfall” means fewer candidates survived than requested. The engine does not
  lower the bar to fill the quota.
- An empty log during a full act does **not** mean it is stuck. Check CPU:

```bash
ps -o pid,etime,pcpu,cmd -C llama-server
```

If `llama-server` is using CPU, generation is active. A single act can take 20 minutes.

### 5.4 Where the results are

```bash
ls runs/ | tail -1
ls premises/ | tail -1
```

Open the newest `premises/<run-id>/` directory. The premise files are the fastest way to
judge the run.

---

## 6. Reading a run, file by file

### `brief.json`

The parsed brief. Check this first when a run ignores a constraint.

Typical fields:

```json
{
  "genre": "horror western",
  "tone": "dry, ominous",
  "setting": "a dying mining town",
  "time_period": "late 19th century",
  "must_include": ["a memory broker"],
  "must_avoid": ["prophecy"],
  "banned_tropes": ["chosen one"],
  "themes": ["memory as property", "debt"],
  "search_queries": ["..."]
}
```

If a hard requirement is missing here, the writer cannot enforce it. Rephrase the brief
more explicitly and rerun.

### `research.json`

Sources fetched this run:

- title, URL, diet (`A` narrative / `B` cross-domain)
- atom count
- whether the source was new
- new clusters created

If research failed, this file is short or empty. The run still uses the standing corpus.

### `run.json`

The complete machine-readable record:

- run id, brief, parsed brief
- mode (`premise`, `outline`, `full`)
- rounds, judged count, survivor count
- each premise: title, logline, premise, why-fresh, clusters, judge scores, files
- outline object
- story metadata (word count, repetition)

This is the file `expand` reads. Editing the Markdown premise does **not** update
`run.json`.

### `01-<title>.md`

The premise:

- title
- logline
- 120–200-word premise
- clusters it was built from
- “why it's fresh”
- judge scores and reason

Read the logline first. A weak logline usually means a weak premise.

### `01-<title>.outline.md`

- title and logline
- characters: want, pressure, secret
- three acts, each with beats
- setting rules
- ending
- “why it holds”

### `01-<title>.story.md`

The full draft, only with `--full`. Acts are separated by `* * *`. The file ends with a
complete sentence thanks to the closing-repair pass.

### `judgment.md`

The candidate table. Columns:

| Column | Meaning |
|---|---|
| coherence / freshness / viability | LLM scores, 1–10 |
| canon max | highest similarity to a famous work |
| decision | KEEP / KILL |
| reason | the judge's one-line explanation |

Canon bands:

- `< 0.55` — faint echo, usually fine
- `0.55–0.67` — warning, read the closest title
- `≥ 0.68` — automatic kill

### `candidates/<run-id>-r1/beta_0.7/results.json`

The ranked candidate sets. Each candidate has:

- cluster ids and names
- exemplar atoms
- coherence, unavailability, fusion
- rank

This is where to look if you want to understand *why* a premise exists.

### `candidates/<run-id>-r1/config.json`

The sampling configuration: seed, k, beta, draws, pool size, anchors, history size. Use
this to reproduce a run.

---

## 7. Full-story workflow

### 7.1 Two ways to get a full draft

**A. From the start**

```bash
python storygen.py new "your brief" --full --target-words 3000
```

This writes premises, outlines, and full drafts, and publishes all of them to
`premises/<run-id>/`.

**B. Expand an existing premise**

```bash
python storygen.py expand --run 20261104T181019-v2-seed42 --index 2 --full
```

`expand` writes the outline/story into `runs/<run-id>/` and updates `run.json`. It does
**not** copy to `premises/<run-id>/`. If you want the published copy:

```bash
cp runs/<run-id>/02-*.story.md premises/<run-id>/
cp runs/<run-id>/02-*.outline.md premises/<run-id>/
```

### 7.2 What happens inside a full draft

1. The outline is loaded (or written if missing).
2. The story is split into three acts with target words per act.
3. Each act is written with the premise, outline, brief, and a recap of previous acts.
4. If an act is under 60% of its target, it is retried once.
5. A revision pass removes obvious repetition.
6. A closing-repair pass checks the ending. If it is mid-sentence, unclosed parenthesis,
   or unclosed quote, it asks for a bounded continuation and appends it.
7. The draft is saved with a header and act separators.

### 7.3 Choosing a target

- `--target-words 2000` — fastest, still a complete short story.
- `--target-words 3000` — default; reference produced ~4,200 words after repair.
- `--target-words 4000` — pushes the 3B model; expect more time and more repetition.
- Above 5,000 is outside the design range and not recommended on this hardware.

### 7.4 Finishing the draft yourself

The 3B model is not a stylist. Expect to:

- cut repeated phrases,
- fix contradictions between acts,
- rename characters that drifted,
- tighten dialogue,
- replace generic sensory detail with specific detail.

Use the outline as the source of truth for structure. If you change the premise
substantially, edit `run.json` before calling `expand`, because `expand` reads the record,
not the Markdown.

---

## 8. Command reference

### `setup`

```bash
python storygen.py setup
python storygen.py setup --pull
python storygen.py setup --test
python storygen.py setup --pull --test
```

Checks provider availability, embedding backend, canon, ledger, and Ollama. `--pull`
starts Ollama and pulls the configured model. `--test` makes one tiny LLM call.

### `new`

```bash
python storygen.py new "<brief>" [options]
```

The main command. Parses the brief, researches, samples, judges, escalates, writes
premises and outlines (and full drafts with `--full`), publishes to `premises/`, and
records the premises in the ledger.

### `discover`

```bash
python storygen.py discover [options]
```

Same pipeline, but the engine writes its own brief first. Useful when you want a surprise.
Inspect the invented brief in the log and in `brief.json`; it can be odd. Start with
`--premises-only --count 1` to test.

### `expand`

```bash
python storygen.py expand --run <run-id> --index <n>
python storygen.py expand --run <run-id> --index <n> --full
python storygen.py expand --run <run-id> --index <n> --full --target-words 3500
```

Grows an existing premise. Without `--full`, writes an outline. With `--full`, writes an
outline if needed and then the story. Writes only to `runs/<run-id>/`.

### `wizard`

```bash
python storygen.py wizard
```

Interactive menu:

1. New story from a brief
2. Surprise me (discover)
3. Expand an old premise
4. Ledger stats
5. Setup check
6. Quit

The wizard always uses seed 42 and asks for output format, sources, escalation, provider,
count, and target words.

### `judge`

```bash
python storygen.py judge --sample gate-sweep --beta 0.7 --top 50 --batch-size 1
```

Rates the top-N candidates of an existing sample and writes a judgment table to
`runs/<sample>-judged/`. Use `--batch-size 1` on the 3B model for reliable JSON. The
default brief is a generic “fresh, human-centered story” unless you pass
`--brief` or `--brief-file`.

### `ledger-stats`

```bash
python storygen.py ledger-stats
```

Prints premise count, kills, runs, source count, recent premises, and sources by diet.
This is the fastest check that the permanent memory is alive.

### `name-clusters`

```bash
python storygen.py name-clusters
python storygen.py name-clusters --limit 20
```

LLM-names clusters that still use keyword fallback names. `--limit` renames only the N
largest fallback clusters.

### `corpus-check`

```bash
python storygen.py corpus-check
```

Validates the manifest and source files. Reports diet counts, kind counts, missing files,
and sources under 150 words.

### `atomize-init`

```bash
python storygen.py atomize-init
```

Lists sources that do not yet have enough atoms. It does not atomize by itself; it is a
readiness check.

### `cluster`

```bash
python storygen.py cluster
python storygen.py cluster --reembed
python storygen.py cluster --reembed --auto-name
python storygen.py cluster --apply-names
```

Re-embeds (with `--reembed`), re-clusters, repairs undersized clusters, and optionally
names them. `--apply-names` merges `clusters/names.json` into `clusters.json` without
reclustering.

### `sample`

```bash
python storygen.py sample --seed 42 --k 3 --beta 0.7 --top-k 50
python storygen.py sample --betas 0.5,0.7,0.85 --n-draws 30000
```

Builds and scores candidates without writing a premise. Useful for exploring the space or
reproducing a Gate-6 sample.

### `stats`

```bash
python storygen.py stats
```

Reports source counts, atom count, cluster count, coverage, and the latest candidate pool.

### `check_gates.py`

```bash
python check_gates.py
```

The eight build-quality gates. Exit code 0 means all pass.

---

## 9. Every flag explained

### `new` / `discover`

| Flag | Default | What it does |
|---|---:|---|
| `--full` | off | Write complete 2–5k drafts |
| `--premises-only` | off | Stop after premise (no outline) |
| `--k` | `3` | Clusters per candidate: 2, 3, or 4 |
| `--beta` | auto | Coherence/strangeness. Auto: 0.7, 0.8, 0.9 per round |
| `--sources` | `8` | Fresh sources fetched this run. `0` skips research |
| `--count` | `3` | Premises to keep. Honest shortfall if fewer survive |
| `--no-escalate` | off | One round only |
| `--no-research` | off | Offline; use only the standing corpus |
| `--provider` | auto | `gemini`, `anthropic`, `openai`, `ollama` |
| `--seed` | `42` | Sampling seed; rounds add 17 per round |
| `--target-words` | `3000` | Target for full drafts |

Notes:

- If both `--full` and `--premises-only` are passed, `--full` wins.
- `--beta` given explicitly still escalates by +0.06 per round, capped at 0.92.
- The number of judged candidates per round is `max(12, count * 4)`, capped by the pool.
- `--count 5` is allowed, but Gate 8’s checker looks for 3–5 valid premises.

### `judge`

| Flag | Default | What it does |
|---|---:|---|
| `--sample` | required | Sample directory under `candidates/` or a path |
| `--beta` | `0.7` | Which beta directory to read |
| `--top` | `50` | Number of candidates to judge |
| `--batch-size` | `3` | Candidates per call; use 1 for 3B reliability |
| `--brief` | generic | Brief used to anchor the judge |
| `--brief-file` | none | Read the brief from a file |
| `--provider` | auto | Provider override |
| `--output` | `runs/<sample>-judged` | Output directory |

### `expand`

| Flag | Default | What it does |
|---|---:|---|
| `--run` | required | Run id or path |
| `--index` | `1` | Premise index within the run |
| `--full` | off | Write a story; otherwise outline only |
| `--provider` | auto | Provider override |
| `--target-words` | `3000` | Story target |

### `cluster`

| Flag | What it does |
|---|---|
| `--seed` | Clustering seed (default 42) |
| `--reembed` | Force re-embedding |
| `--auto-name` | Reuse names by atom overlap, then LLM-name the rest |
| `--apply-names` | Merge `clusters/names.json` without reclustering |

### `sample`

| Flag | Default | What it does |
|---|---:|---|
| `--seed` | `42` | Sampling seed |
| `--k` | `3` | Clusters per set |
| `--beta` | none | Single beta |
| `--betas` | `0.5,0.7,0.85` | Multiple betas when `--beta` is absent |
| `--top-k` | `50` | Candidates to keep |
| `--n-draws` | `20000` | Random draws |
| `--output-dir` | auto | Output folder under `candidates/` |

---

## 10. Writing briefs that work

The parser is literal about hard constraints and generous about mood. The best briefs are
specific about what must be true and open about how it feels.

### 10.1 A good template

```text
Genre: <genre>.
Tone: <3–5 adjectives>.
Setting: <place and time>.
Must include: <concrete person/object/place/event>.
Must avoid: <tropes, themes, words>.
Length: <premise / outline / full draft>.
```

Example:

```text
Genre: quiet science fiction.
Tone: patient, elegiac, wry.
Setting: a coastal repair yard in 2041.
Must include: a woman named Mara, a house that remembers its owners, a flooded basement.
Must avoid: chosen one, prophecy, AI rebellion, generic dystopia.
Length: full draft, about 3,500 words.
```

### 10.2 What the parser handles well

- Explicit names: “a woman named Mara”
- Places and periods: “1970s Punjab”, “a dying mining town”
- Must-include objects: “a brass key”, “a flooded basement”
- Banned tropes: “no prophecy”, “no chosen one”
- Tone words: “wry”, “elegiac”, “claustrophobic”
- Genre blends: “horror western”, “domestic noir”

### 10.3 What it handles poorly

- Vague requirements: “something about memory” (no enforceable check)
- Negations of style: “not too dark” (subjective)
- Contradictions: “cozy apocalypse”
- Massive lists of must-include items (the premise becomes a checklist)
- Requests for a specific existing work (“like Blade Runner”) — the canon wall may kill
  the idea, and the result is derivative by design

### 10.4 Getting variety

- Change `--seed`.
- Change `--k` (2 = safer, 4 = stranger).
- Raise `--beta` (0.8–0.9) for stranger combinations.
- Give a more specific brief; broad briefs collapse into familiar shapes.
- Run `discover` for a completely different starting point.

### 10.5 Getting coherence

- Use `--k 2`.
- Lower `--beta` to 0.55–0.65.
- Name a concrete protagonist and place.
- Ask for a tone rather than a plot.
- Prefer a hosted model for judging and prose.

---

## 11. Providers, models, cost, and time

### 11.1 Auto-selection

Order: **Gemini → Anthropic → OpenAI → Ollama**. The first available wins. `--provider`
forces one.

### 11.2 Hosted providers

```bash
export GEMINI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export OPENAI_API_KEY="..."
```

Models live in `llm_config.json`. Swap them there or use `--provider`.

A full run makes many calls:

- 1 brief parse
- several research queries (one LLM call)
- ~8 atomization calls (one per source)
- 12–20 judge calls
- 1 premise per kept candidate
- 1 outline per premise
- 3 acts + 1 revision per full draft

Budget accordingly. Check current provider pricing; this project does not bundle a cost
calculator.

### 11.3 Local Ollama

- Free and offline after the model is pulled.
- CPU-only on this machine.
- 3B prose is serviceable but flat; 7B–8B is a real upgrade if you have the hardware.
- Long acts can approach the 1,800-second timeout. Do not lower it casually.

### 11.4 Model recommendations

| Situation | Model |
|---|---|
| Fast iteration on this CPU | `qwen2.5:3b` |
| Better prose, still local | `qwen2.5:7b` or `llama3.1:8b` |
| Best judgment and prose | a hosted Sonnet/GPT/Gemini model |
| Offline, no keys | any pulled Ollama model |

Change the local model:

```json
"models": { "ollama": "qwen2.5:7b" }
```

Then `python storygen.py setup --pull --test`.

---

## 12. Configuration cookbook

All settings are in `llm_config.json`.

### 12.1 Prefer a provider

```json
"provider_order": ["anthropic", "gemini", "openai", "ollama"]
```

### 12.2 Change a model

```json
"models": {
  "gemini": "gemini-2.5-pro",
  "anthropic": "claude-sonnet-4-5",
  "openai": "gpt-4.1",
  "ollama": "qwen2.5:7b"
}
```

### 12.3 Make prose more controlled

```json
"stages": {
  "writer": { "temperature": 0.65, "max_tokens": 4200 }
}
```

### 12.4 Make judging stricter

```json
"stages": {
  "judge": { "temperature": 0.0, "max_tokens": 2500 }
}
```

Temperature alone does not make a 3B judge strict; a stronger model does.

### 12.5 Longer timeout

```json
"request_timeout": 2400
```

Useful for slow CPU acts. Do not set it low.

### 12.6 Bigger Ollama context

```json
"ollama": { "host": "http://127.0.0.1:11434", "num_ctx": 8192 }
```

Only if your model and memory can handle it. Expect slower generation.

### 12.7 Custom endpoint

```json
"base_urls": {
  "openai": "https://your-gateway.example/v1"
}
```

Leave empty for the provider default.

### 12.8 Disable LiteLLM

```json
"litellm": false
```

The engine falls back to direct HTTP. Ollama always uses direct HTTP.

---

## 13. Quality control

### 13.1 Read the logline first

A good logline is a sentence you would repeat to a friend. If it is generic, the premise
will be generic.

### 13.2 Check the canon number

In `judgment.md`, look at `canon max`:

- `< 0.55` — comfortable
- `0.55–0.67` — read the closest title; decide if the resemblance is structural
- `≥ 0.68` — should have been killed; report it if it survived

### 13.3 Check the combination

In the premise file, read “Built from”. A strong premise usually has one emotional anchor
and one genuinely foreign domain. A weak one is three variations of the same idea.

### 13.4 Red flags

- The logline names a “chosen one”, “prophecy”, or “savior”.
- The premise is a list of constraints rather than a situation.
- The same character name appears across unrelated runs (ledger should prevent this; if
  not, check `ledger-stats`).
- The outline's acts are interchangeable.
- The ending is stated twice.
- The full draft repeats a phrase more than a few times.
- The story contradicts the outline's character secrets.

### 13.5 A manual rubric

Rate each premise 1–5:

| Dimension | Question |
|---|---|
| Clarity | Can I state the story in one sentence? |
| Tension | Is there a real cost or dilemma? |
| Freshness | Have I seen this exact engine before? |
| Fit | Does it honor the brief? |
| Writability | Can I imagine three acts? |

Keep 4s and 5s. Rewrite 3s. Discard 1s and 2s.

---

## 14. Editing and finishing

### 14.1 Edit the premise

The premise file is plain Markdown. Edit it for clarity. But remember: `expand` reads
`run.json`, not the Markdown. If you want the edited premise to drive an outline, update
the matching record in `run.json` first:

```bash
python - <<'PY'
import json
p = "runs/<run-id>/run.json"
d = json.load(open(p))
for rec in d["premises"]:
    if rec["index"] == 1:
        rec["title"] = "New Title"
        rec["logline"] = "New logline."
        rec["premise"] = "New 120–200-word premise..."
json.dump(d, open(p, "w"), indent=2)
PY
```

Then:

```bash
python storygen.py expand --run <run-id> --index 1 --full
```

### 14.2 Edit the outline

The outline is also Markdown. `expand --full` reads the outline object stored in
`run.json`, not the Markdown file. To change structure before drafting, edit the
`outline` object in `run.json` (acts, beats, ending) or write the outline manually and
accept that the draft uses the stored version.

### 14.3 Edit the draft

The story file is plain Markdown. Fix:

- repeated phrases,
- inconsistent names,
- scenes that summarize instead of dramatize,
- endings that explain the theme.

Keep the `* * *` separators if you want act structure preserved.

### 14.4 Publish an expanded story

`expand` does not copy to `premises/`. Do it manually:

```bash
run=<run-id>
cp runs/$run/01-*.story.md premises/$run/
cp runs/$run/01-*.outline.md premises/$run/
```

---

## 15. Managing the ledger

### 15.1 What it stores

SQLite tables:

| Table | Contents |
|---|---|
| `premises` | every saved premise: title, logline, text, clusters, fusion, timestamp |
| `runs` | every run id, brief, metadata |
| `sources` | every fetched URL hash, source id, title, diet |
| `kills` | rejected candidates and reasons |

### 15.2 Inspect

```bash
python storygen.py ledger-stats
sqlite3 ledger.db "select id, title, run_id, created_at from premises order by id desc limit 10;"
sqlite3 ledger.db "select count(*) from sources;"
```

### 15.3 Back up

```bash
cp ledger.db ledger.db.$(date +%Y%m%d-%H%M%S).bak
```

Do this before any reset or bulk experiment.

### 15.4 Reset the whole memory

```bash
mv ledger.db ledger.db.bak
python storygen.py ledger-stats   # creates a fresh ledger
```

This forgets all premises and source URLs. Existing files remain on disk.

### 15.5 Remove one premise

```bash
sqlite3 ledger.db "delete from premises where title = 'The Silent Trade';"
```

The next run can reuse that combination. Be careful: the title is not unique across runs.

### 15.6 Remove one run

```bash
sqlite3 ledger.db "delete from premises where run_id = '<run-id>';"
sqlite3 ledger.db "delete from runs where run_id = '<run-id>';"
rm -rf runs/<run-id> premises/<run-id> candidates/<run-id>-r*
```

### 15.7 Why source URLs are in the ledger

The collector skips URLs it has already fetched. This keeps research fresh and avoids
re-downloading the same Wikipedia page. If you want to re-fetch a URL, delete its row from
`sources`.

---

## 16. Managing the idea space

### 16.1 Check the numbers

```bash
python storygen.py stats
```

Expected: `sources: 94`, `atoms: 1394`, `clusters: 117`, `coverage: 1.0`.

### 16.2 Rebuild embeddings

```bash
rm clusters/embeddings.npz
python storygen.py cluster --reembed
```

Use after changing atoms or upgrading `model2vec`.

### 16.3 Re-cluster and rename

```bash
python storygen.py cluster --reembed --auto-name
python storygen.py name-clusters
```

`--auto-name` reuses names by atom overlap, then asks the LLM to name the rest.
`name-clusters` only touches fallback names.

### 16.4 Add material the supported way

Use live research: run `new` or `discover` with `--sources N`. New sources are atomized,
integrated into the nearest clusters, and recorded in the ledger.

### 16.5 Add a permanent source manually (advanced)

There is no single CLI command for this, but the functions exist:

```python
from story import collector, io_utils

title = "My Source"
text = open("/path/to/source.txt", encoding="utf-8").read()
atoms = collector.atomize_text(title, text, provider="ollama")
# Then write atoms/<source-id>.json, append records to atoms/all.json,
# add the source to corpus/manifest.json, and call:
# collector.integrate_new_atoms(records, [source_id])
```

Do this on a copy of the project first. A malformed record can break clustering. The
safe, supported path is live research.

### 16.6 Change the clustering threshold

`clusters/meta.json` records the chosen distance threshold. The clustering code is in
`story/cluster_atoms.py`. If you change it, rerun `cluster --reembed` and then
`check_gates.py` — Gate 5 expects 60–120 clusters, coverage ≥ 90%, and min size ≥ 3.

---

## 17. Troubleshooting

### “No LLM provider is available”

```bash
python storygen.py setup
ollama serve
ollama pull qwen2.5:3b
# or
export GEMINI_API_KEY="..."
```

### Ollama answers very slowly

Expected on CPU. Check:

```bash
ps -o pid,etime,pcpu,cmd -C llama-server
```

If CPU is high, it is working. Do not restart. Lower `--target-words` or switch provider.

### “request timed out”

The 1,800-second cap was hit. Raise `request_timeout` in `llm_config.json`, or lower the
target. A timeout is not retried three times by design.

### The log is empty for 20 minutes during a full draft

The Python process is waiting on HTTP; `llama-server` is generating. Check CPU. Do not
interrupt unless you accept losing the act.

### “No premises survived the freshness gate”

The brief may be too close to a famous work, or the judge/provider failed. Try:

```bash
python storygen.py new "more specific brief" --beta 0.6 --sources 10
python storygen.py new "..." --k 2 --no-escalate
```

Use a stronger provider if possible.

### “HONEST SHORTFALL: 1/3 premises survived”

This is intentional. The engine will not fill the quota with weak ideas. Re-run with a
stronger provider, a broader brief, or more sources.

### The judge keeps everything

A 3B judge is permissive. Check `canon max` yourself. Use a hosted model for sharper
judging. `--batch-size 1` improves JSON reliability, not judgment quality.

### Premise is too short / too long

The writer repairs to 120–200 words. If repair fails, the premise is rejected. A stronger
model reduces retries. You can also edit the premise manually.

### Premise ignores a constraint

Check `brief.json`. If the constraint is missing there, rephrase it explicitly:

```text
Must include: a woman named Mara.
Must avoid: prophecy, chosen one.
```

### Duplicate titles

The ledger rejects duplicate titles and regenerates. If you see one, check
`ledger-stats` and delete the stale row.

### Full draft ends mid-sentence

The closing-repair pass should prevent this. If it happens:

```bash
python storygen.py expand --run <run-id> --index <n> --full
```

### Full draft is short

The writer retries an act once when it is under 60% of target. If the retry is also short,
it keeps the longer version. Raise the target only if the model can sustain it.

### Repetition

The revision pass reduces loops, but a 3B model still repeats. Lower `writer` temperature,
use a larger model, or edit manually.

### Embedding error / corrupt cache

```bash
rm clusters/embeddings.npz
python storygen.py cluster --reembed
```

### Stale or bad cluster names

```bash
python storygen.py name-clusters
```

### CI fails after a change

Run locally first:

```bash
python -m unittest tests.test_v2_core -v
python check_gates.py
```

The CI workflow creates `.venv`, installs `requirements.txt`, and runs both.

---

## 18. Performance and timing

### 18.1 Reference timings on this machine

| Stage | Time |
|---|---|
| Brief parse | ~72 s |
| One source atomization | ~86 s |
| Judge one candidate | ~56 s |
| One premise | ~78 s |
| One outline | ~289 s |
| Act 1 (1,349 words) | ~1,250 s |
| Act 2 (933 words) | ~409 s |
| Act 3 (1,426 words) | ~919 s |
| Revision pass | included in act loop |
| Gate-7 50 candidates | ~50 min |

### 18.2 How to go faster

- `--premises-only`
- `--no-escalate`
- `--sources 2` or `--no-research`
- `--count 1`
- `--target-words 2000`
- a hosted provider
- a smaller local model

### 18.3 What not to do

- Do not run two full drafts at once on CPU Ollama. Requests serialize and time out.
- Do not kill an act because the log is quiet. Check `llama-server` CPU first.
- Do not lower `request_timeout` below the time your model needs for a long act.

---

## 19. Playbooks

### 19.1 15-minute idea session

```bash
python storygen.py new "A domestic story about a family that rents its memories" \
  --premises-only --no-escalate --count 3 --sources 3 --provider ollama
```

Then read the three premises and pick one.

### 19.2 Tightly constrained brief

```bash
python storygen.py new "1970s Punjab; a woman named Mara; a failing sugar mill; no prophecy; wry tone; must include a brass key" \
  --premises-only --count 2 --sources 6
```

Check `brief.json` before writing outlines.

### 19.3 Full draft from a strong premise

```bash
python storygen.py new "your best brief" --premises-only --count 3
# pick the best run/index
python storygen.py expand --run <run-id> --index 2 --full --target-words 3500
```

This avoids paying for three full drafts when you only want one.

### 19.4 Series / story bible

1. Run `new` with the shared world constraints.
2. Keep 3–5 premises that share a setting but differ in engine.
3. Expand each into an outline.
4. Use the outlines as a bible; draft only the strongest.
5. The ledger prevents accidental repetition across the series.

### 19.5 Offline run

```bash
python storygen.py new "your brief" --no-research --provider ollama --premises-only
```

Uses only the standing corpus. Faster and deterministic-ish, but less fresh.

### 19.6 Research-heavy run

```bash
python storygen.py new "your brief" --sources 10 --count 3
```

More sources, more atomization time, more novelty.

### 19.7 High-diversity run

```bash
python storygen.py new "your brief" --k 4 --beta 0.85 --count 3
```

Stranger combinations, lower coherence. Read carefully.

### 19.8 Safe/coherent run

```bash
python storygen.py new "your brief" --k 2 --beta 0.55 --count 2
```

More conventional, easier to outline.

### 19.9 Debug the judge

```bash
python storygen.py judge --sample <sample-name> --beta 0.7 --top 20 --batch-size 1
```

Inspect `runs/<sample>-judged/judgment.md` and compare the judge's KEEP with the canon
numbers.

---

## 20. FAQ

**Does it train a model?**
No. It builds an explicit atom/cluster space and uses an LLM for language tasks.

**Does it need the internet?**
Only for live research and the first embedding-model download. `--no-research` works
offline if the model and cache are present.

**Can I use it commercially?**
The code is Apache 2.0. Check your LLM provider's terms. The corpus contains Wikipedia
excerpts (CC BY-SA) and public-domain Gutenberg text; see `NOTICE` and
`corpus/manifest.json`.

**Why does Gate 8 expect 3–5 premises?**
The build checker treats 3–5 as the deep-dive band. `--count` can be higher, but the
checker selects the best 3–5-premise run.

**Why do I keep seeing the same names?**
The 3B model has naming habits. The ledger rejects duplicate titles, but it cannot stop
similar-sounding names. Use a stronger model or edit the premise.

**Can I write in another language?**
The prompts and corpus are English. A multilingual model may handle a non-English brief,
but quality is not guaranteed.

**Can I use GPT-4.1 / Claude / Gemini?**
Yes. Set the key, optionally set `--provider`, and adjust `models` in `llm_config.json`.

**How do I delete a bad premise from memory?**
See §15.5. Back up `ledger.db` first.

**Why is the full draft only 2,500 words when I asked for 3,000?**
The model stops early; the writer retries once. It prefers an honest short draft over
padding. Raise the target or use a stronger model.

**Why did the judge keep a bad idea?**
The 3B judge is soft. The canon wall and ledger are the hard guards; use your own reading.

**Where are the logs?**
The CLI prints to stdout. Redirect with `2>&1 | tee run.log`.

**How do I update the project?**
`git pull`, reinstall requirements if they changed, then run tests and gates. Back up
`ledger.db` and any custom corpus first.

**Is `USER_GUIDE.md` published?**
Yes. It is part of the repository and is included in the published documentation.

---

## 21. Glossary

| Term | Meaning |
|---|---|
| **Atom** | A small narrative fragment: situation, image, mechanism, pressure |
| **Cluster** | A semantic neighbourhood of atoms |
| **Candidate** | A set of `k` clusters proposed by the sampler |
| **Anchor** | A cluster chosen because it is relevant to the brief |
| **Coherence** | Whether the clusters can plausibly belong to one story |
| **Unavailability** | How rare/under-used the combination is |
| **Fusion** | Weighted combination of coherence and unavailability |
| **Beta** | Weight on unavailability; higher = stranger |
| **Canon wall** | Programmatic similarity check against famous works |
| **Ledger** | SQLite memory of premises, runs, sources, kills |
| **Escalation** | Extra rounds with higher beta, different k, more research |
| **Honest shortfall** | Fewer premises than requested; the bar was not lowered |
| **Premise** | 120–200-word story idea with title, logline, why-fresh |
| **Outline** | Three acts with beats, characters, setting rules, ending |
| **Closing repair** | Automatic continuation when an act ends mid-sentence |
| **Brief doc** | Structured JSON produced from the brief |

---

## 22. File map

```
/home/zaki/story/
  storygen.py                 CLI
  check_gates.py              8-gate verifier
  llm_config.json             provider/model/stage config
  requirements.txt            dependencies
  README.md                   public overview
  WORKFLOW.md                 public workflow
  USER_GUIDE.md               this guide
  BUILD_LOG.md                build history
  CHANGELOG.md                release history
  VERSION                     1.2.0
  LICENSE / NOTICE            Apache 2.0 + attribution

  story/
    __init__.py               version
    io_utils.py               files, JSON, slugs, word counts
    embeddings.py             model2vec + fallbacks
    cluster_atoms.py          clustering and naming
    sample.py                 candidate generation/scoring
    collector.py              research, atomization, integration
    judge.py                  canon wall + LLM judging
    writer.py                 premise/outline/story + repairs
    ledger.py                 SQLite memory
    llm.py                    provider runtime
    stats.py                  normalization/z-scores

  atoms/                      atoms per source + all.json
  corpus/                     source texts + manifest.json
  clusters/                   clusters, names, embeddings, meta
  canon/                      canon.json + canon_emb.npz
  candidates/                 sampling runs
  runs/                       full pipeline runs
  premises/                   published copies
  prompts/                    prompt templates
  tests/                      unit tests
  docs/                       architecture/configuration/troubleshooting
  .github/workflows/ci.yml    CI
```

Runtime-only, not committed:

```
.venv/                        Python environment
.ollama/                      local models and server
ledger.db                     permanent memory
ledger.db-*                   backups
__pycache__/                  Python cache
```

---

## 23. Maintenance checklist

### Before a long session

- [ ] `source .venv/bin/activate`
- [ ] `python storygen.py setup`
- [ ] `python storygen.py ledger-stats`
- [ ] Back up `ledger.db`
- [ ] Check disk space (`df -h .`)
- [ ] Close other CPU-heavy processes

### After a session

- [ ] Read the premises and pick keepers
- [ ] Delete bad runs if disk is tight
- [ ] Back up `runs/`, `premises/`, and `ledger.db` if the work matters
- [ ] Note the run ids you want to revisit

### Monthly

- [ ] `python -m unittest tests.test_v2_core -v`
- [ ] `python check_gates.py`
- [ ] `python storygen.py stats`
- [ ] `python storygen.py ledger-stats`
- [ ] Check for stale/tiny clusters (Gate 5)
- [ ] Review `llm_config.json` for model updates
- [ ] Rotate API keys
- [ ] Prune old `candidates/` and `runs/` if disk is tight

### After changing atoms or clustering

- [ ] `python storygen.py cluster --reembed --auto-name`
- [ ] `python storygen.py stats`
- [ ] `python check_gates.py`
- [ ] Run a small `new --premises-only` smoke test

---

## 24. Security and privacy

- Put API keys in environment variables, never in `llm_config.json` or committed files.
- `.gitignore` excludes `.env`, `ledger.db`, `.venv/`, `.ollama/`, and private notes.
- The ledger stores briefs, premises, run ids, and source URLs. Treat it as private.
- Research queries and prompts are sent to your chosen LLM provider. Do not put sensitive
  personal data in a brief if you are using a hosted provider.
- Research fetches public pages from Wikipedia and Project Gutenberg. It does not log in
  anywhere.
- The repository is public. Do not commit `ledger.db`, `.env`, session logs, or private
  briefs unless you intend to publish them.
- If you paste a token into a chat or terminal, revoke it afterward.

---

## 25. Version and license

- Version: **1.2.0**
- License: **Apache License 2.0** (`LICENSE`)
- Attribution: `NOTICE`
- Public repository: <https://github.com/Md-zaki08/story>
- Release: <https://github.com/Md-zaki08/story/releases/tag/v1.2.0>

Third-party content:

- Wikipedia excerpts are CC BY-SA; source URLs are in `corpus/manifest.json`.
- Project Gutenberg texts are public domain in the United States.
- The canon list stores titles and short descriptions for similarity checking, not full
  text.

---

## 26. My run log

Use this space to track the runs you care about.

| Date | Run id | Brief | Mode | Kept | Notes |
|---|---|---|---|---|---|
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |

---

*End of guide.*
