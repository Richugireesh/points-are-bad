# AGENTS.md

This file provides guidance to OpenCode agents working in this repository.

## Commands

Use `uv` for everything (prepend `.venv/bin/` or `uv run`). Never use plain `pip` or `python`.

```bash
uv pip install -e '.[dev,web]'          # full install for dev
ruff check src/ tests/                  # lint
ruff format --check src/ tests/         # format check
mypy src/                               # typecheck (strict, Python 3.9 target)
pytest tests/ -v                        # all tests (coverage enforced at 80%)
pytest tests/test_scoring.py::TestNormalize -v   # single test case
pytest tests/ --no-cov -x               # stop on first failure, skip coverage
```

CI runs `ruff check` + `ruff format --check` + `mypy src/` + `pytest tests/ -v` on Python 3.9 and 3.12.

## Architecture

The app is an F1 prediction game — players predict Top-10 finishers, lowest score wins.

Source lives under `src/points_are_bad/`. Module boundaries are strict:
- `scoring.py` — pure logic, **stdlib only**. No I/O, no external imports.
- `api.py` — FastF1 → OpenF1 → manual fallback for fetching race results. Cache-dir setup centralized in `_setup_fastf1_cache()`.
- `storage.py` — SQLite persistence with WAL journal mode; auto-migration from legacy JSON.
- `drivers.py` — hardcoded 2026 grid (22 drivers). Predictions use lowercase `key` values from here.
- `models.py` — TypedDicts: `GameData`, `RaceData`, `DriverResult`, `DriverInfo`.
- `exceptions.py` — `PointsAreBadError` → `ApiError`, `StorageError`, `DataValidationError`.

Web layer (`web/`):
- `server.py` — Flask. Write endpoints require Bearer `API_TOKEN`. SQLite WAL handles concurrency.
- `index.html` — vanilla HTML/CSS/JS dashboard. No build step. JS scoring mirrors `scoring.py` exactly.

## API quirks — DO NOT BREAK THESE

**Never use `requests` in `api.py`.** FastF1 monkey-patches `requests` globally with aggressive caching. All secondary HTTP calls (OpenF1, schedule) must use `urllib.request` directly.

**OpenF1 endpoint order:** `/meetings` → `/sessions` → `/session_result` → `/drivers`. Use `meeting_key` (not `session_key`) when fetching drivers — otherwise `broadcast_name` can be `null`.

## Web server gotchas

**`workers` defaults to 2** in Gunicorn. SQLite WAL mode handles concurrent access safely across workers and threads. `threads=4` is the default.

**409 vs 400:** Write endpoints return `409` when a duplicate already exists, `400` for malformed input. `DELETE` endpoints return `404` for unknown resources. The dashboard JS relies on this distinction.

**Race lookups:** Use the `_find_race(game, race_name)` helper — avoid inline `next((r for r in game["races"] ...))` scans.

**Token auth** uses `hmac.compare_digest` for timing-safe comparison. New auth checks must do the same.

**Player names are lowercase** — enforced by both `POST /players` and the prediction endpoint lowercases the player field before lookup.

**Rate limiting** is disabled in tests: the `client` fixture in `tests/test_web_server.py` monkeypatches `limiter.enabled = False`. New web tests must do the same.

## Docker

Single-stage build with `uv`, non-root `pab` user. The `docker-entrypoint.sh` script `chown`s the `/data` volume as root before dropping to `pab` via `su`. The `.dockerignore` excludes caches, tests, and dev files from the build context.

## Python 3.9 compatibility

- Always include `from __future__ import annotations` at the top of every module.
- Use `Optional[X]` / `Union[X, Y]`, never `X | Y` (even with `from __future__ import annotations` — it fails at runtime on 3.9 for some patterns like `isinstance` checks and type-alias assignments).
- `mypy` runs in strict mode. All public functions must be fully annotated.

## Testing

- The `isolated_test_db` fixture (autouse) in `conftest.py` redirects storage to a temp SQLite database for every test session.
- Coverage scope is `points_are_bad` (the `src/` package, not `web/`). Threshold: 80%, enforced by `pytest-cov`.
- Use `--no-cov` to skip coverage when iterating on tests.

## Adding drivers or aliases

Edit `drivers.py` for the roster. The `key` field = lowercase last name as resolved by `scoring._normalize()`. Aliases go in `scoring.ALIASES` — the web UI picks them up automatically via `GET /aliases`.

## Commit style

Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`.
