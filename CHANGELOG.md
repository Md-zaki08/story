# Changelog

All notable changes to StoryGen are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] — 2026-11-05

### Added

- Public documentation set: `README.md`, `docs/ARCHITECTURE.md`,
  `docs/CONFIGURATION.md`, `docs/TROUBLESHOOTING.md`, and `CONTRIBUTING.md`.
- Apache License 2.0 (`LICENSE`) and `NOTICE`.
- `--version` flag on the CLI.
- `VERSION` file and this changelog.
- `requirements.txt` with the tested dependency versions.
- GitHub Actions workflow that runs the unit tests and the eight build gates.
- Automatic closing repair for acts that hit the token limit mid-sentence.
- Premise-length repair for premises outside the 120–200-word band.
- Partial-batch salvage in the judge: valid verdicts are kept and missing candidates are
  retried individually.
- Gate-7 judgment table for 50 candidates, with one candidate per judge call.

### Changed

- Rebranded the public project as **StoryGen 1.2**.
- Ollama timeout raised to 1,800 seconds and act token budgets bounded so a single act
  cannot hang a full run.
- Canon threshold and judge behavior documented honestly: the local 3B judge is a soft
  filter; the canon wall and ledger are the hard guards.
- Live-research clusters with fewer than three atoms are folded into their nearest
  neighbours, keeping the space stable.

### Fixed

- Full drafts can no longer be saved with a truncated final sentence.
- Duplicate titles across the permanent ledger are rejected and regenerated.
- Thin live-research sources no longer create undersized clusters.
- Judge batches that lose JSON structure no longer discard usable verdicts.

### Verified

- `python check_gates.py` → 8/8 checks pass.
- `python -m unittest tests.test_v2_core` → 10 tests pass.
- Reference full draft: 4,215 words, ending on a complete sentence.
- Gate 7: 50 rows, 50 survivors, maximum canon similarity 0.618.

## Earlier internal iterations

The pre-release build history is preserved in [`BUILD_LOG.md`](BUILD_LOG.md). It documents
the original corpus construction, clustering experiments, sampling sweeps, and the
Definition-of-Done gates that shaped 1.2.0.
