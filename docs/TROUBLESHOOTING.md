# Troubleshooting

## Setup and environment

### `ModuleNotFoundError: No module named 'litellm'` (or `model2vec`)

The virtual environment is not active, or dependencies were installed elsewhere.

```bash
source .venv/bin/activate
pip install -r requirements.txt
python storygen.py setup
```

### `No LLM provider is available`

No API key is set and Ollama is not reachable.

```bash
# Option 1: local model
ollama serve
ollama pull qwen2.5:3b
python storygen.py setup --test

# Option 2: hosted provider
export GEMINI_API_KEY="..."
python storygen.py setup
```

You can also force a provider with `--provider ollama` or `--provider gemini`.

### `ollama: command not found`

Install Ollama from <https://ollama.com/download>, or point the engine at an existing
server by editing `ollama.host` in `llm_config.json`.

### Ollama pull is slow or resumes from zero

The default model is ~1.9 GB. Re-run the same pull command; Ollama resumes completed
layers. A slow connection is the usual cause.

### Ollama answers very slowly

A 3B model on a CPU can take many minutes for a long act. This is expected. Options:

- lower `--target-words`
- use a smaller model
- use a hosted provider
- keep `request_timeout` at 1,800 seconds or higher

Do not interrupt an act unless you are willing to lose that act's work.

### `request timed out`

The per-request limit is 1,800 seconds. On CPU-only hardware, a long act can approach it.
The engine does not retry a timeout three times; it reports the failure. Raise
`request_timeout` in `llm_config.json`, or lower the act budget/target length.

## Embeddings and clustering

### First run is stuck downloading a model

The first `model2vec` call downloads `minishlab/potion-base-8M` into the Hugging Face
cache. Give it a minute and check network access. Later runs use the cache.

### `Embedding error` or a corrupt cache

```bash
rm clusters/embeddings.npz
python storygen.py cluster --reembed
```

The shipped `clusters/embeddings.npz` is enough for normal runs; rebuilding is only needed
if you change the atoms.

### Clusters are named badly or are stale

```bash
python storygen.py name-clusters
# or a full rebuild:
python storygen.py cluster --reembed --auto-name
```

`name-clusters` only renames clusters still using keyword fallback names.

### A live-research run created a tiny cluster

This should not happen: new clusters require at least three atoms, and undersized
clusters are folded into their nearest neighbours. If you see one, run:

```bash
python storygen.py cluster --reembed
```

and report the run id.

## Research

### `No research sources found`

The collector could not fetch usable sources. Check:

- network access,
- whether Wikipedia or Project Gutenberg is rate-limiting you,
- whether the brief's queries are too narrow.

The run continues with the standing 94-source corpus. You can also run with
`--no-research`.

### Research keeps finding the same pages

Those URLs are in the ledger. The collector skips them by design. To allow re-fetching,
back up and remove `ledger.db` (this also forgets your premise history), or inspect the
`source_url` table with any SQLite client.

### A fetched page is a disambiguation page or a stub

The collector skips thin pages and tries other candidates. If a bad source still gets
through, it will produce weak atoms. Delete the corresponding `atoms/<id>.json` and
re-cluster, or leave it; the quality rating is recorded.

## Sampling and judging

### `No premises survived the freshness gate`

This is an honest result, not a crash. The brief may be too close to a famous work, or
the local judge may be too weak. Try:

- a more specific brief,
- `--sources 10`,
- a stronger provider,
- a different `--beta` (lower is safer),
- `--no-escalate` to inspect a single round.

The engine never lowers the canon threshold to manufacture a result.

### `HONEST SHORTFALL: 1/3 premises survived`

Fewer candidates cleared the guards. The run reports exactly what survived. This is
preferred over filling the quota with weak ideas. Re-run with a stronger provider or a
broader brief.

### The judge keeps everything

A small local model is permissive. In the reference Gate-7 run, `qwen2.5:3b` kept all 50
candidates and clustered its scores at 7/7/6. This is expected. The canon wall and ledger
are the real filters. Use a hosted model for sharper judging.

### Batch judgment lost JSON

The judge salvages valid partial verdicts and retries missing candidates individually. If
you still see failures, use `--batch-size 1` for the `judge` command or switch to a
stronger provider.

## Writing

### Premise is too short or too long

The writer repairs premises to 120–200 words: short ones get concrete continuation
sentences, long ones are compressed or trimmed at sentence boundaries. If repair fails
repeatedly, the premise is rejected rather than shipped. A stronger model reduces
retries.

### Premise omits a must-include item

The writer checks hard constraints and regenerates once, then rejects. Check `brief.json`
to confirm the constraint was parsed correctly. Vague constraints (“something about
memory”) are harder to enforce than concrete ones (“a woman named Mara”).

### Full draft ends mid-sentence

The closing-repair pass should prevent this. If it happens:

```bash
python storygen.py expand --run <run-id> --index <n> --full
```

The repair pass detects a missing terminal punctuation mark, an unclosed parenthesis, or
an unclosed quotation mark, and appends a bounded continuation.

### Full draft is much shorter than the target

Small models often stop early. The writer retries an act once when it falls below 60% of
the target. If the retry is also short, the longer of the two is kept. Raise
`--target-words` only if your model can sustain it; otherwise the result is an honest
short draft, not a padded one.

### Full draft repeats itself

The writer measures 4-gram repetition and runs a revision pass. A 3B model still loops
more than a hosted model. Options:

- use a larger model,
- lower `writer` temperature slightly,
- run `expand --full` again,
- edit the draft manually.

## Performance

### A run takes a long time

The main costs are LLM calls: brief parsing, research queries, atomization, judging,
premises, outlines, and acts. On CPU-only Ollama, a full draft can take an hour or more.
Use `--premises-only` for fast iteration, or a hosted provider for drafting.

### The process looks idle

Ollama may be generating with high CPU while the Python process waits on HTTP. Check:

```bash
ps -o pid,etime,pcpu,cmd -C llama-server
```

If `llama-server` is using CPU, generation is active. Do not restart it.

## Data and state

### Reset the permanent ledger

Back it up first:

```bash
mv ledger.db ledger.db.bak
python storygen.py ledger-stats
```

A new empty ledger is created on the next run. This forgets all previous premises and
source URLs; only do it intentionally.

### Reset a single run

Delete `runs/<run-id>/`, `premises/<run-id>/`, and the matching
`candidates/<run-id>-r*/` directories. The ledger still contains the premises; remove
those rows too if you want the engine to forget them.

### Move the project

The engine uses paths relative to `storygen.py`, so moving the whole directory is safe.
If you move only part of it, keep `corpus/`, `atoms/`, `clusters/`, and `canon/` together.

## Getting more help

When reporting an issue, include:

- the exact command,
- the provider and model (`python storygen.py setup`),
- the run id,
- the relevant part of `run.json` or `judgment.md`,
- the last 30 lines of output.

Open an issue at <https://github.com/Md-zaki08/story/issues>.
