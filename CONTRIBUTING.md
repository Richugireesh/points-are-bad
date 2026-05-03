# Contributing

## Dev environment setup

```bash
git clone <repo>
cd points-are-bad
uv venv
uv pip install -e '.[dev,web]'   # includes Flask for web server tests
```

Optionally install pre-commit hooks (runs ruff and mypy on staged files):

```bash
.venv/bin/pre-commit install
```

## Running the app

```bash
# One-time install
uv pip install -e '.[web]'

# CLI
.venv/bin/points-are-bad

# Web dashboard — development (Flask dev server)
uv run web/server.py            # → http://localhost:5001
PORT=8080 uv run web/server.py  # custom port

# Web dashboard — production (Gunicorn, same command used in Docker)
gunicorn -c gunicorn.conf.py web.server:app
```

Override the data file path or set auth for local testing:

```bash
POINTS_DATA_FILE=/tmp/test_data.json .venv/bin/points-are-bad
POINTS_DATA_FILE=/tmp/test_data.json uv run web/server.py

# Enable token auth — enter the same token in the dashboard header
API_TOKEN=mysecret uv run web/server.py
# The dashboard stores the token in localStorage so you only enter it once.

# Disable rate limiting during manual testing
RATELIMIT_ENABLED=false uv run web/server.py
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
.venv/bin/pytest tests/ -v                                   # all tests with coverage
.venv/bin/pytest tests/test_scoring.py -v                    # single module
.venv/bin/pytest tests/test_scoring.py::TestNormalize -v     # single class
.venv/bin/pytest tests/test_web_server.py -v                 # web server only
.venv/bin/pytest tests/ --no-cov -x                          # stop on first failure, no coverage
```

Coverage must stay at or above 80%. The threshold is enforced by `pytest-cov` via `pyproject.toml`. The coverage scope is `points_are_bad` (the `src/` package); web server tests contribute to passing count but not to the coverage metric.

## Project conventions

### Type annotations
- All public function signatures must be fully annotated.
- Use `from __future__ import annotations` at the top of every module.
- Use `Optional` / `Union` (not `X | Y`) — Python 3.9 compatibility. Ruff rules `UP007` and `UP045` are suppressed in `pyproject.toml` because they push toward `X | Y` syntax.
- `GameData` uses `total=False` so the `version` field is optional for test fixtures and callers.
- Run `mypy src/` and fix all errors before opening a PR.

### Modules and responsibilities

Keep the module boundaries strict:

| Module | Allowed imports | Not allowed |
|---|---|---|
| `scoring.py` | stdlib only | `api`, `storage`, `cli` |
| `storage.py` | stdlib, `exceptions`, `models` | `api`, `cli`, `scoring` |
| `api.py` | stdlib, `fastf1`, `models`, `exceptions` | `cli`, `storage`, `scoring` |
| `cli.py` | any internal module | — |
| `web/server.py` | stdlib, `hmac`, `flask`, `flask_limiter`, `points_are_bad.*` | `cli`, `api` |

`web/server.py` is intentionally kept thin — it reads/writes the JSON file directly and delegates alias logic to `scoring.ALIASES`. It must not grow into a second CLI.

### Web server conventions

- All file mutations hold `_data_lock` (a `threading.Lock`) for the full read-modify-write cycle.
- Error responses use `_err(msg, code)` — never return raw `jsonify({"error": ...})` inline.
- The `/aliases` endpoint must stay in sync with `scoring.ALIASES`; it imports and re-exports the same dict.
- **409 for duplicates, not 400** — `POST /predictions`, `POST /results`, `POST /players`, `POST /races` all return `409` when the resource already exists. `400` means the input itself is invalid. `DELETE /players` and `DELETE /races` return `404` for unknown resources. Clients rely on this distinction.
- **Race lookups** use the `_find_race(game, race_name)` helper to avoid repeated O(n) scans.
- **Token auth** uses `hmac.compare_digest` for timing-safe comparison.
- **Rate limiting** is applied per-endpoint via `@limiter.limit(...)` (flask-limiter). The `Limiter` instance is module-level so all routes share the same in-memory counter. Do not bypass or remove these decorators. In tests, the `client` fixture monkeypatches `limiter.enabled = False` so tests making multiple requests to the same endpoint don't trip limits.
- **Request size** is capped at 16 KB via `MAX_CONTENT_LENGTH`. The `413` error handler returns JSON (not Flask's default HTML). Keep all write payloads well under this limit.
- **Workers must stay at 1** in Gunicorn (`gunicorn.conf.py`). The threading.Lock is in-process. Multiple workers each get their own lock copy, making it useless. If you ever need to scale beyond 1 worker, migrate storage to SQLite (or any external store) first.
- **Player names are lowercase** — both `POST /players` and the CLI `manage_players` enforce this. The prediction endpoint (`POST /predictions`) lowercases the player field before checking. All internal lookups are case-sensitive against the lowercase list.

### JavaScript scoring

`web/index.html` contains a JS reimplementation of `scoring.py` (`calcPlayerPoints`, `calcStrEquality`, `ALIASES`). On init, the page fetches `/aliases` and merges the result into the local `ALIASES` dict — this keeps the two in sync without a build step. If you add an alias to `scoring.py`, it will automatically appear in the web UI on next page load.

### API quirk — do not use `requests` in `api.py`

FastF1 monkey-patches `requests` globally with aggressive caching. All secondary HTTP calls (OpenF1, custom endpoints) must use `urllib.request` to bypass the cache. FastF1 cache-dir setup is centralized in `_setup_fastf1_cache()` — use this helper in any new FastF1 call sites.

### Adding a driver to the roster

Edit `src/points_are_bad/drivers.py`. The `key` field must be the lowercase last name that `scoring._normalize()` resolves to. If the driver has an alias (e.g. nickname), add it to `ALIASES` in `scoring.py` — it will propagate to the web UI automatically via the `/aliases` endpoint.

### Commit style

Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`.

## CI

GitHub Actions runs on every push to `master` / `stable` and on PRs:
- `ruff check` + `ruff format --check`
- `mypy src/` strict mode
- `pytest tests/ -v` with 80% coverage threshold
- Matrix: Python 3.9 and 3.12
