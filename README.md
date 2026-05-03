# Points Are Bad — F1 Prediction Game

A Python CLI and web dashboard for playing "Points are Bad" — a Formula 1 prediction game among friends where players predict the Top 10 finishers of every Grand Prix. The objective is to accumulate the *fewest* points across the season.

## Rules

- Players predict the Top 10 finishers before every GP (usually after qualifying).
- Each incorrect prediction slot scores **+1 point**.
- A missing prediction for a race scores a flat **+10 point penalty**.
- The player with the fewest points at the end of the season wins.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.9+ |
| Package manager | [uv](https://github.com/astral-sh/uv) |
| Web server | [Flask](https://flask.palletsprojects.com/) 3.x + [Gunicorn](https://gunicorn.org/) 22.x (production) |
| Rate limiting | [flask-limiter](https://flask-limiter.readthedocs.io/) 3.x |
| Frontend | Vanilla HTML / CSS / JS — no build step, no framework |
| F1 data (primary) | [FastF1](https://docs.fastf1.dev/) 3.x — official timing & results |
| F1 data (fallback) | [OpenF1](https://openf1.org/) REST API via `urllib` |
| Data storage | JSON flat-file with atomic writes and 3 rolling backups |
| Testing | [pytest](https://pytest.org/) + [pytest-cov](https://pytest-cov.readthedocs.io/) (80% threshold enforced) |
| CI | GitHub Actions (lint + test on push/PR) |
| Linting | pre-commit hooks (ruff, mypy) |

## Requirements

- Python 3.9+
- [uv](https://github.com/astral-sh/uv)

## Installation

```bash
git clone <repo>
cd points-are-bad
uv venv
uv pip install -e '.[dev,web]'   # CLI + Flask + Gunicorn + dev tools
```

`[web]` pulls in Flask, flask-limiter, and Gunicorn. `[dev]` adds pytest, ruff, mypy, and pre-commit.

## CLI

```bash
.venv/bin/points-are-bad
```

Data is auto-created at `points_are_bad_data.json` in the working directory. Override with `POINTS_DATA_FILE=/path/to/file.json`. Player names are stored lowercase.

## Web Dashboard

### Development (Flask dev server)

```bash
# One-time install (if you haven't already)
uv pip install -e '.[web]'

# Then run
uv run web/server.py            # → http://localhost:5001
# or, after installing scripts:
points-are-bad-web

PORT=8080 points-are-bad-web   # custom port

# Enable authentication (required for write endpoints)
API_TOKEN=mysecret uv run web/server.py
# Then enter the token in the dashboard header (stored in localStorage)
```

### Production (Gunicorn)

```bash
gunicorn -c gunicorn.conf.py web.server:app
```

The `gunicorn.conf.py` pins `workers=1` (required — the threading.Lock used for JSON writes is in-process), `threads=4`, and logs to stdout/stderr. See the file for the full rationale.

### Docker

```bash
# Build and run
docker build -t points-are-bad .
docker run -p 5001:5001 -v $(pwd)/data:/data -e API_TOKEN=<secret> points-are-bad

# Or with docker-compose (recommended — handles the data volume automatically)
mkdir -p data
API_TOKEN=$(openssl rand -hex 32) docker compose up
```

The Docker image uses a single-stage build with `uv`, runs as a non-root `pab` user, and includes a `docker-entrypoint.sh` that fixes volume permissions on startup. A `.dockerignore` excludes caches, tests, and dev files from the build context.

`API_TOKEN` is a shared secret required by all write endpoints (`POST /predictions`, `POST /results`, `POST/DELETE /players`, `POST/DELETE /races`, `/races/fetch-results`). Without it, those endpoints are open — suitable only for local dev. Pass it as a `Bearer` token:

```bash
curl -X POST http://localhost:5001/players \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "alice"}'
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5001` | TCP port the server listens on |
| `POINTS_DATA_FILE` | `points_are_bad_data.json` | Path to the JSON data file |
| `API_TOKEN` | *(unset — open)* | Bearer token required for write endpoints |
| `RATELIMIT_ENABLED` | `true` | Set to `false` to disable rate limiting |

The dashboard provides:
- **Season standings** with score bars (lowest score = largest bar) and delta from the leader
- **Race log** — click any completed race to see a full position-by-position breakdown
- **Pending predictions** — clicking an upcoming race shows who has submitted picks and who hasn't
- **Prediction entry** — `+ PREDICT` opens a 3-step modal: select pilot → select race → pick P1–P10 from the driver roster
- **New pilot creation / removal** — add or remove a player inline from step 1 of the prediction modal
- **Auth token** — input in the header bar, persisted in localStorage; sent as `Bearer` with all write requests

### Web API

All write endpoints require `Authorization: Bearer <API_TOKEN>` when `API_TOKEN` is set. Requests exceeding 16 KB are rejected with `413`. Rate limits apply per IP (write endpoints are stricter than reads).

| Method | Path | Auth | Rate limit | Description |
|--------|------|------|------------|-------------|
| `GET` | `/data` | — | 300/hr, 60/min | Full game state as JSON |
| `GET` | `/aliases` | — | 300/hr, 60/min | Driver alias table (mirrors `scoring.ALIASES`) |
| `POST` | `/predictions` | Bearer | 60/hr, 10/min | Submit or overwrite a prediction |
| `POST` | `/results` | Bearer | 30/hr, 5/min | Enter actual race results |
| `POST` | `/players` | Bearer | 20/hr, 5/min | Add a new player |
| `DELETE` | `/players` | Bearer | 20/hr, 5/min | Remove a player and all their predictions |
| `POST` | `/races` | Bearer | 20/hr, 5/min | Add a race to the schedule |
| `DELETE` | `/races` | Bearer | 20/hr, 5/min | Remove a race (must not have results) |
| `POST` | `/races/fetch-results` | Bearer | 10/hr, 2/min | Auto-fetch results from FastF1/OpenF1 for a past race |

`POST /predictions` body:
```json
{
  "player": "alice",
  "race_name": "Bahrain Grand Prix",
  "prediction": ["verstappen", "norris", "leclerc", ...],
  "overwrite": false
}
```
Returns `409` if a prediction already exists and `overwrite` is not `true`.

`POST /results` body:
```json
{
  "race_name": "Bahrain Grand Prix",
  "results": [
    {"name": "Max Verstappen", "abbr": "VER"},
    ...
  ]
}
```
Returns `409` if results are already entered for that race.

`POST /players` body:
```json
{ "name": "alice" }
```
Returns `409` if the player already exists (not `400` — so clients can distinguish "name taken" from "name invalid"). Player names are stored lowercase.

`DELETE /players` body:
```json
{ "name": "alice" }
```
Removes the player and all their predictions from every race. Returns `404` if unknown.

## Testing

```bash
.venv/bin/pytest tests/ -v                    # run all tests
.venv/bin/pytest tests/test_scoring.py -v     # single module
.venv/bin/pytest tests/ --cov=points_are_bad  # with coverage
```

Coverage threshold is 80%, enforced by `pytest-cov`.

## Architecture

```
src/points_are_bad/
  cli.py        Interactive menus, input/output, orchestration
  scoring.py    Pure scoring logic; no I/O (fully unit-testable)
  api.py        FastF1 → OpenF1 → manual fallback chain for results
  storage.py    JSON load/save (points_are_bad_data.json)
  drivers.py    Hardcoded 2026 roster (22 drivers, 11 teams)
  models.py     TypedDicts: GameData, RaceData, DriverResult, DriverInfo
  exceptions.py PointsAreBadError hierarchy (ApiError, StorageError, …)

web/
  server.py     Flask server: serves index.html + JSON API endpoints
  index.html    Single-page dashboard (pure HTML/CSS/JS, no build step)

tests/
  conftest.py           Shared fixtures (sample_data, no_clear_screen)
  test_scoring.py       100% coverage of scoring.py
  test_storage.py       Round-trip + error-path tests — 100% storage.py
  test_drivers.py       Roster integrity, lookup helpers
  test_cli_utils.py     Pure CLI helpers, mocked select_item
  test_cli_menus.py     Interactive menus with mocked input()
  test_api.py           urllib + fastf1 mocked, all fallback paths
  test_web_server.py    Flask test client — all endpoints + validation paths
```

### Key data flow

1. `cli.py:main_menu()` loads `GameData` from JSON via `storage.load_data()`.
2. On startup it calls `auto_update_past_races()` which fetches missing results via `api.fetch_results()`.
3. Scoring is always delegated to `scoring.calculate_player_points_for_race()` — the single source of truth for per-race points. The web dashboard replicates this logic in JavaScript (`calcPlayerPoints` in `index.html`) and verifies it by fetching `ALIASES` from `/aliases` on load.
4. All writes go through `storage.save_data()` (CLI) or directly via the Flask endpoints (web), both of which hold a `threading.Lock` during read-modify-write.

### API quirk — FastF1 monkey-patches `requests`

FastF1 aggressively caches via `requests`. All OpenF1 calls inside `api.py` therefore use `urllib.request` directly to avoid stale cached responses. Do **not** introduce `requests` calls in `api.py`.

### OpenF1 endpoint order

Must call in sequence: `/meetings` → `/sessions` → `/session_result` → `/drivers`. Use `meeting_key` (not `session_key`) when fetching drivers to avoid null `broadcast_name` values.

## Features

- **Player management** — add/remove players via CLI or web dashboard (removal cleans up predictions).
- **Race schedule** — add/remove/auto-populate from FastF1; dates kept in sync.
- **Driver-select UI** — interactive picker grouped by team, available in both CLI and web.
- **Automated result fetching** — FastF1 (official) → OpenF1 (community) → manual entry.
- **Points breakdown** — per-position view for any race across all players.
- **Season standings** — live table sorted by fewest points; bars scale inversely (best = widest).
- **Web dashboard** — aerospace-aesthetic dark-mode SPA; no build step required.
- **Auth token UI** — enter `API_TOKEN` in the header; persisted in localStorage across sessions.
