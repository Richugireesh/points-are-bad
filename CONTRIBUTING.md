# Contributing

## Dev environment setup

```bash
git clone <repo>
cd points-are-bad
uv venv
uv pip install -e .[dev]
```

Optionally install pre-commit hooks (runs ruff and mypy on staged files):

```bash
.venv/bin/pre-commit install
```

## Running the app

```bash
.venv/bin/points-are-bad
```

Override the data file path for local testing:

```bash
POINTS_DATA_FILE=/tmp/test_data.json .venv/bin/points-are-bad
```

## Linting and formatting

```bash
.venv/bin/ruff check src/ tests/     # lint
.venv/bin/ruff format src/ tests/    # format
.venv/bin/mypy src/                  # type-check (strict)
```

All three must pass clean before merging. The CI workflow enforces this on every push and PR.

## Running tests

```bash
.venv/bin/pytest tests/ -v                         # all tests with coverage
.venv/bin/pytest tests/test_scoring.py -v          # single module
.venv/bin/pytest tests/test_scoring.py::TestNormalize -v  # single class
.venv/bin/pytest tests/ --no-cov -x               # stop on first failure, no coverage
```

Coverage must stay at or above 80%. The threshold is enforced by `pytest-cov` via `pyproject.toml`.

## Project conventions

### Type annotations
- All public function signatures must be fully annotated.
- Use `from __future__ import annotations` at the top of every module.
- Use `Optional` / `Union` (not `X | Y`) in module-level type alias assignments for Python 3.9 compatibility.
- Run `mypy src/` and fix all errors before opening a PR.

### Modules and responsibilities
Keep the module boundaries strict:

| Module | Allowed imports | Not allowed |
|---|---|---|
| `scoring.py` | stdlib only | `api`, `storage`, `cli` |
| `storage.py` | stdlib, `exceptions`, `models` | `api`, `cli`, `scoring` |
| `api.py` | stdlib, `fastf1`, `models`, `exceptions` | `cli`, `storage`, `scoring` |
| `cli.py` | any internal module | — |

### API quirk — do not use `requests` in `api.py`
FastF1 monkey-patches `requests` globally with aggressive caching. All secondary HTTP calls (OpenF1, custom endpoints) must use `urllib.request` to bypass the cache.

### Adding a driver to the roster
Edit `src/points_are_bad/drivers.py`. The `key` field must be the lowercase last name that `scoring._normalize()` resolves to. If the driver has an alias (e.g. nickname), add it to `ALIASES` in `scoring.py`.

### Commit style
Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`.

## CI

GitHub Actions runs on every push to `master` / `stable` and on PRs:
- `ruff check` + `ruff format --check`
- `mypy src/` strict mode
- `pytest tests/ -v` with 80% coverage threshold
- Matrix: Python 3.9 and 3.12
