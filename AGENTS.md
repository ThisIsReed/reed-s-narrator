# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `src/narrator/`. Keep domain models in `models/`, orchestration flow in `orchestrator/`, provider adapters in `llm/`, persistence code in `persistence/`, and reusable simulation rules in `core/`, `knowledge/`, and `phenology/`. Runtime entry scripts are in `scripts/` (`run.py`, `replay.py`). Configuration defaults live in `config/default.yaml`; schema-like allowlists belong under `config/schemas/`. Tests are split into `tests/unit/` and `tests/integration/`. Design notes and architecture drafts belong in `docs/`.

## Build, Test, and Development Commands
Use Python 3.11+.

- `python -m pip install -e .[dev]` installs the package and test dependencies in editable mode.
- `python scripts/run.py` loads `config/default.yaml` and `.env` to verify the main bootstrap path.
- `python scripts/replay.py --db data/narrator.db list --source checkpoint` inspects persisted replay data.
- `pytest` runs the full test suite.
- `pytest tests/unit -q` runs fast unit coverage while iterating.
- `pytest tests/integration -q` runs replay, loop, and agent-flow integration scenarios.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, explicit type hints, small functions, and immutable-first models (`frozen=True`, `model_copy`, readonly-style patterns). Use `snake_case` for modules, functions, and variables; use `PascalCase` for classes; keep constants uppercase like `MAX_PREVIEW_ITEMS`. Prefer direct failures over silent fallbacks: surface invalid config, missing files, and provider errors explicitly.

## Testing Guidelines
This repository uses `pytest`. Name test files `test_*.py` and test functions `test_<behavior>()`. Mirror the source layout where practical, for example `src/narrator/llm/router.py` maps to `tests/unit/llm/test_router.py`. Add unit tests for pure logic and integration tests when changing CLI flow, orchestration, replay persistence, or database interactions.

## Commit & Pull Request Guidelines
Recent history uses short imperative subjects, sometimes with Conventional Commit prefixes, for example `feat: load llm provider settings from env file` and `Implement WP-10 replay tooling and long-run coverage`. Keep commit subjects concise, action-led, and specific. PRs should describe the behavior change, list verification commands you ran, link the relevant work package or issue, and include sample CLI output when changing replay or bootstrap flows.

## Security & Configuration Tips
Never commit real API keys. Copy `.env.example` to `.env` and fill in provider settings locally. Treat `config/default.yaml` as the canonical config entrypoint and keep environment substitution names aligned with `src/narrator/config.py`.
