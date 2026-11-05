# Architecture

This document explains how StoryGen is put together, why the pieces are separated the way
they are, and where to change things.

## Design principles

1. **The idea space is explicit.** Atoms, embeddings, clusters, canon fingerprints, and
   candidate scores are files on disk. You can audit every creative decision.
2. **Hard guards are programmatic.** Freshness cannot depend on a small model's opinion.
   The canon wall and ledger are deterministic checks that run before and after writing.
3. **LLMs do language, not bookkeeping.** The model parses briefs, proposes research
   queries, atomizes sources, judges candidates, and writes prose. It does not decide
   whether a candidate is too close to a famous work.
4. **Failure is honest.** If the pipeline cannot produce the requested number of fresh
   premises, it reports a shortfall instead of lowering the bar.
5. **Every stage is resumable.** A run writes its brief, research, candidates, judgments,
   and outputs incrementally. A crash does not erase completed stages.

## Module map

| Module | Responsibility |
|---|---|
| `storygen.py` | CLI dispatch, pipeline orchestration, publishing |
| `story/io_utils.py` | Paths, JSON, slugs, word counts, source parsing |
| `story/embeddings.py` | Embedding backend chain and cache |
| `story/cluster_atoms.py` | Atom clustering, naming, space repair |
| `story/sample.py` | Candidate generation, coherence/rarity scoring, fusion |
| `story/collector.py` | Brief parsing, live research, atomization, integration |
| `story/judge.py` | Canon wall, LLM judging, verdict parsing, tables |
| `story/writer.py` | Premise, outline, full draft, length/closing repairs |
| `story/ledger.py` | SQLite memory for premises, runs, sources, kills |
| `story/llm.py` | Provider detection, LiteLLM/direct HTTP, retries, timeouts |
| `story/stats.py` | Normalization, z-scores, similarity helpers |
| `check_gates.py` | Build-quality verifier for the eight gates |

## Data model

### Atom

Stored in `atoms/<source-id>.json` and aggregated in `atoms/all.json`.

```json
{
  "id": "her-2013:03",
  "source": "her-2013",
  "diet": "A",
  "text": "A man falls in love with an operating system that outgrows him.",
  "quality": "high",
  "kind": "situation"
}
```

- `diet` is `A` for narrative sources and `B` for cross-domain sources.
- `quality` is a coarse rating used when a cluster needs an exemplar.
- `kind` is a free-form label such as `situation`, `image`, `mechanism`, or `pressure`.

### Cluster

Stored in `clusters/clusters.json`.

```json
{
  "id": 17,
  "name": "Grief Simulation",
  "atom_ids": ["her-2013:03", "..."],
  "size": 12,
  "centroid": [0.01, -0.03, "..."],
  "keywords": ["grief", "simulation", "memory"]
}
```

`clusters/meta.json` records the embedding method, dimension, linkage, threshold, cluster
count, coverage, and the threshold sweep used to choose the final space.

`clusters/embeddings.npz` caches the atom matrix and atom ids. If it is deleted,
`python storygen.py cluster --reembed` rebuilds it.

### Canon entry

`canon/canon.json` stores a title, year, medium, short description, and tags for each of
the 122 famous works. `canon/canon_emb.npz` caches their embeddings. The canon is used
only for similarity checking; no full text is stored.

### Candidate

`candidates/<run-id>-rN/beta_<value>/results.json` contains the ranked candidate sets with
cluster ids, names, per-component scores, and fusion score. `config.json` records the seed,
`k`, β, draw count, pool size, anchors, and history size.

### Run

`runs/<run-id>/run.json` is the complete record: brief, parsed brief, rounds, provider,
premises, cluster combinations, judge results, file names, and story metadata.

## Pipeline

### Brief parsing

`collector.parse_brief()` sends the brief to the LLM with a JSON schema. The result is a
`brief_doc` with:

```json
{
  "genre": "...",
  "tone": "...",
  "setting": "...",
  "time_period": "...",
  "must_include": ["..."],
  "must_avoid": ["..."],
  "banned_tropes": ["..."],
  "themes": ["..."],
  "search_queries": ["..."]
}
```

If the brief is sparse, the parser fills in reasonable themes and queries. If it is
detailed, constraints are preserved verbatim and later enforced by the writer.

### Research

`collector.collect()`:

1. Builds relevant and foreign search queries from the brief.
2. Searches Wikipedia and Project Gutenberg.
3. Skips URLs already recorded in the ledger.
4. Over-discovers (requests `n + 4` candidates) to survive fetch failures.
5. Fetches and extracts plaintext.
6. Atomizes each usable source with the LLM.
7. Embeds and integrates new atoms into the existing space.
8. Returns source metadata, atoms, and any new clusters.

Live sources produce 6–10 atoms. The standing corpus keeps its deeper 16-atom treatment.

### Embedding and clustering

`story/embeddings.py` tries, in order:

1. `model2vec` (`minishlab/potion-base-8M`)
2. `fastembed` (`BAAI/bge-small-en-v1.5`)
3. `sentence-transformers` (`all-MiniLM-L6-v2`)
4. TF-IDF + SVD (pure NumPy/SciPy)

The backend actually used is written to `clusters/meta.json`. The shipped space uses
model2vec at 256 dimensions.

`story/cluster_atoms.py` performs average-linkage agglomerative clustering on cosine
distance. Undersized clusters are merged into their nearest neighbours, and new live
clusters must have at least three atoms. The space is capped at 120 clusters.

### Sampling

`story/sample.py`:

1. Computes cluster centroids and exemplars.
2. Builds a source-overlap matrix for co-occurrence bridging.
3. Ranks "gravity wells" — clusters that draw too much from one source or one diet.
4. Draws 20,000 random `k`-cluster sets.
5. Anchors at least one slot to a brief-relevant cluster.
6. Scores each set.

The scoring definitions are:

```
coherence      = 0.5 * z(mean pairwise cosine)
               + 0.5 * z(co-occurrence bridging)

unavailability = 0.65 * z(pair rarity)
               + 0.35 * z(cliché distance)

fusion         = (1 - beta) * z(coherence)
               + beta * z(unavailability)
```

`z()` is a robust z-score computed over the sampled pool. A coherence floor prevents
top-ranked sets from being incoherent noise. `beta` controls how much the engine prefers
safe combinations over strange ones.

### Hard filters

`story/judge.py`:

- `canon_neighbors(text)` embeds the candidate text and compares it with the canon matrix.
- `DEFAULT_CANON_KILL = 0.68`; anything at or above this is rejected.
- `ledger.max_combo_overlap()` rejects combinations that overlap too much with history.
- `ledger.similarity_to_history()` rejects full-text repeats above the configured
  threshold.

The judge prints a canon band for every candidate so the LLM does not kill on a title
alone.

### LLM judging

`judge.judge_candidates()` sends batches to the provider. Each verdict contains:

```json
{
  "index": 0,
  "coherence": 7,
  "freshness": 7,
  "viability": 6,
  "decision": "KEEP",
  "reason": "..."
}
```

The parser salvages valid verdicts from partial batches and retries only the missing
candidates individually. If a single call still fails, a conservative heuristic is used.

### Escalation

`run_pipeline()` keeps a `kept_all` list. If it is shorter than `--count` and escalation is
enabled, it:

1. increments the round,
2. raises β (0.7 → 0.8 → 0.9),
3. optionally changes `k`,
4. runs another research pass with new foreign queries,
5. re-anchors and judges.

Up to three rounds. The loop never lowers the canon threshold or the ledger overlap limit.

### Writing

`story/writer.py`:

- `write_premise()` produces a 120–200-word premise, repairs length, checks constraints,
  and retries or rejects.
- `write_outline()` produces three acts with beats, characters, setting rules, and ending.
- `write_story()` writes acts sequentially with a rolling recap, runs a repetition check,
  revises weak acts, and repairs a truncated ending with `_finish_act_text()`.

`_ends_cleanly()` detects a missing terminal punctuation mark, an unclosed parenthesis, or
an unclosed quotation mark. `_finish_act_text()` asks for a bounded continuation and
appends it, so a saved draft cannot end mid-sentence.

### Publishing

`save_premise()`, `save_outline()`, and `save_story()` write into `runs/<run-id>/`. The CLI
then copies the published files into `premises/<run-id>/` and records the premise in the
ledger.

## Extension points

- **New research sources** — add a fetcher in `collector.py` and return the same source
  descriptor shape.
- **New embedding backend** — add a `_try_*` function in `embeddings.py`; the fallback
  chain and metadata are already generic.
- **New scoring term** — add it to `sample.py`, keep it z-scored, and document the weight.
- **New canon entries** — add to `canon/canon.json`, then rebuild `canon/canon_emb.npz`.
- **New provider** — add it to `llm_config.json` and the environment-key map in `llm.py`.

## Why these choices

- **model2vec** is small, fast on CPU, and does not need a GPU. It is good enough for
  neighborhood clustering; the LLM handles nuance.
- **Average linkage** avoids chaining long, diffuse clusters better than single linkage.
- **20,000 draws** is enough to cover a large fraction of the top space without making a
  run feel slow.
- **A hard canon wall** is necessary because small judges are permissive. The Gate-7
  reference run is the evidence: the 3B judge kept all 50 candidates, so the wall did the
  real filtering.
- **SQLite** keeps the ledger dependency-free and inspectable with any SQLite client.
