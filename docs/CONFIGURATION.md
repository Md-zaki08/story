# Configuration

StoryGen is configured through `llm_config.json` and environment variables. The shipped
file is a working default; edit it in place or override per run with CLI flags.

## `llm_config.json`

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
  "ollama": {
    "host": "http://127.0.0.1:11434",
    "num_ctx": 4096
  },
  "base_urls": {
    "gemini": "",
    "anthropic": "",
    "openai": ""
  },
  "request_timeout": 1800,
  "litellm": true
}
```

### `provider_order`

The order in which providers are tried. The engine picks the first provider that has a
usable key (or a reachable Ollama). Reorder to prefer a different provider by default.

### `models`

The model id passed to each provider. Examples:

| Provider | Model id |
|---|---|
| Gemini | `gemini-2.5-flash`, `gemini-2.5-pro` |
| Anthropic | `claude-sonnet-4-5`, `claude-haiku-4-5` |
| OpenAI | `gpt-4.1-mini`, `gpt-4.1` |
| Ollama | any pulled model, e.g. `qwen2.5:3b`, `llama3.1:8b` |

Change `models.ollama` to a larger local model if your machine can handle it. Larger
models judge better and write better prose, at the cost of speed.

### `stages`

Each stage has its own temperature and token budget:

| Stage | Used for | Default temp | Default max tokens |
|---|---|---:|---:|
| `collector` | brief parsing, research queries, atomization | 0.6 | 2,200 |
| `judge` | candidate verdicts | 0.2 | 2,500 |
| `writer` | premise, outline, prose, revision | 0.85 | 4,200 |

Lower `judge` temperature for more stable verdicts. Lower `writer` temperature for more
controlled prose. Raise it for variety.

The writer applies its own per-act budgets on top of `max_tokens` to keep a single act from
hanging a CPU-only run.

### `ollama`

- `host` — the Ollama server URL. Default `http://127.0.0.1:11434`.
- `num_ctx` — the context window. 4,096 is safe for small models; raise it if your model
  supports it.

Ollama calls use the native `/api/chat` endpoint, which supports `format: "json"` and
`num_ctx`. The engine waits up to `request_timeout` seconds and does not blindly retry a
timeout three times.

### `base_urls`

Optional custom endpoints for OpenAI-compatible gateways, proxies, or self-hosted
services. Leave empty to use the provider default.

### `request_timeout`

Per-request timeout in seconds. Default `1800` (30 minutes). A 3B model on a CPU can take
20+ minutes for a long act, so do not lower this unless you are using a fast hosted model.

### `litellm`

When `true`, the engine prefers LiteLLM for hosted providers. If LiteLLM is unavailable or
fails, it falls back to direct HTTP. Ollama always uses direct HTTP to preserve
`format: "json"` and `num_ctx`.

## Environment variables

| Provider | Variables | Notes |
|---|---|---|
| Gemini | `GEMINI_API_KEY`, `GOOGLE_API_KEY` | Either name works |
| Anthropic | `ANTHROPIC_API_KEY` | |
| OpenAI | `OPENAI_API_KEY` | |
| Ollama | — | Uses `ollama.host`; no key |

Set them in your shell, a `.env` file, or your process manager. `.env` is ignored by git.

```bash
export GEMINI_API_KEY="..."
python storygen.py new "..." --provider gemini
```

## Provider selection

1. `--provider X` forces a provider. If it is unavailable, the run fails with a clear
   message.
2. Otherwise, providers are tried in `provider_order`.
3. The provider and model that actually answered are printed and recorded in the run.

Use `python storygen.py setup` to see what is available without making a paid call.

## Ollama

### Install and serve

```bash
ollama serve
ollama pull qwen2.5:3b
```

Or:

```bash
python storygen.py setup --pull --test
```

`--pull` starts Ollama if needed and pulls `models.ollama`. `--test` makes one tiny call.

### Choosing a local model

| Model | Size | Trade-off |
|---|---:|---|
| `qwen2.5:3b` | ~1.9 GB | Fastest; weakest prose and judging |
| `qwen2.5:7b` | ~4.7 GB | Better prose; slower on CPU |
| `llama3.1:8b` | ~4.9 GB | Strong general prose; slower |
| `mistral-nemo` | ~7 GB | Good long-context behavior |

For a CPU-only machine, 3B is the practical default. For a GPU or Apple Silicon machine,
7B–8B is a meaningful upgrade.

### Context

`num_ctx` is the model's context window. 4,096 is enough for the shipped prompts. If you
raise it, expect more memory use and slower generation.

## Sampling configuration

These are CLI flags, not `llm_config.json` keys:

| Flag | Default | Effect |
|---|---:|---|
| `--k` | 3 | Clusters per candidate. Higher = stranger, less coherent |
| `--beta` | auto (0.7) | Coherence/strangeness balance |
| `--seed` | 42 | Sampling seed |
| `--sources` | 8 | Fresh sources fetched per run |
| `--count` | 3 | Premises to keep |
| `--target-words` | 3000 | Full-draft target |
| `--no-escalate` | off | Disable the multi-round escalation |
| `--no-research` | off | Fully offline run |

The pipeline's internal constants are deliberately visible in code:

- `DEFAULT_CANON_KILL = 0.68`
- max combination overlap = `0.4`
- cluster cap = `120`
- minimum live cluster size = `3`
- reference cluster space = `117` clusters
- reference corpus = `94` sources

## Data configuration

The engine reads these paths relative to the project root:

| Path | Purpose |
|---|---|
| `corpus/manifest.json` | Source metadata and licensing URLs |
| `atoms/all.json` | Aggregated atoms |
| `clusters/clusters.json` | Cluster definitions |
| `clusters/embeddings.npz` | Atom embedding cache |
| `clusters/meta.json` | Embedding and clustering metadata |
| `canon/canon.json` | Canon titles and descriptions |
| `canon/canon_emb.npz` | Canon embedding cache |
| `ledger.db` | Runtime memory (git-ignored) |
| `runs/` | Run records and outputs |
| `premises/` | Published copies |

To rebuild the embedding cache:

```bash
rm clusters/embeddings.npz
python storygen.py cluster --reembed
```

To re-cluster and rename:

```bash
python storygen.py cluster --reembed --auto-name
python storygen.py name-clusters
```

## Timeouts and budgets

- `request_timeout`: 1,800 seconds per LLM request.
- Act generation: bounded token budget (1,200–2,000 tokens) with a 1,600-token reference
  target.
- Premise repair: up to two continuation attempts and one compression pass.
- Closing repair: up to two bounded continuations of 120–200 words.
- Judge retries: missing candidates are retried individually after a partial batch.

## Logging

The CLI prints stage-level progress:

```
[collector] brief: ...
[collector] 1/8 A :: Title -> 9 atoms
[embeddings] embedding 1394 texts
[sample] pool=4052 ...
[judge] KEEP 22.04 :: ...
[pipeline] round 1: 12 judged, 12 kept, total 3/3
[writer] act 1: 1349 words in 1250s
```

Redirect to a file if you want a full transcript:

```bash
python storygen.py new "..." --full 2>&1 | tee run.log
```
