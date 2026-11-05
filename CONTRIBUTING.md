# Contributing to StoryGen

Thanks for taking a look. This project is a self-contained research and writing engine,
so contributions are most useful when they keep the pipeline inspectable and the
freshness guarantees honest.

## Development setup

```bash
git clone https://github.com/Md-zaki08/story.git
cd story
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python storygen.py setup
```

A local Ollama model is enough for end-to-end testing:

```bash
python storygen.py setup --pull --test
```

## Before opening a pull request

```bash
python -m unittest tests.test_v2_core -v
python check_gates.py
```

Both should pass. If you changed the corpus, atoms, clusters, or Canon data, `check_gates.py`
will verify the affected gates.

## Guidelines

- Keep deterministic logic (sampling, scoring, canon checks, ledger) separate from LLM
  calls, and keep both testable without a network.
- Do not weaken a freshness guard to make a test pass. An honest shortfall is a valid
  result.
- Add a test for every bug fix that can be expressed without an LLM.
- Preserve the output contract: `runs/<run-id>/` for pipeline artifacts and
  `premises/<run-id>/` for published copies.
- Keep documentation and `README.md` in sync with CLI changes.
- Do not commit `.venv/`, `.ollama/`, `ledger.db`, API keys, or private session notes.

## Reporting an issue

Include:

- the command you ran,
- the provider and model,
- the run id and the relevant part of `run.json` or the judgment table,
- the traceback or the last 30 lines of output.

## License

By contributing, you agree that your contributions are licensed under the Apache License
2.0 (see `LICENSE`).
