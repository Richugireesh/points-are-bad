# Architecture & Design Decisions

## Overview

Points Are Bad is a web dashboard for a Formula 1 prediction game. Players predict the Top 10 finishers before each Grand Prix; incorrect picks score +1pt, missing a race scores +10pt. Lowest score wins.

The app runs as a Flask + Gunicorn server with a vanilla HTML/CSS/JS frontend — no build step, no framework. Data is persisted in SQLite with WAL journal mode.

## Design Decisions

### 1. Web-only (no CLI)

Originally the app had both a Textual TUI and a web dashboard. The TUI was removed to simplify the architecture. The web dashboard is accessible via localhost or Tailscale (private mesh VPN), which covers all use cases — friends can submit predictions from their phones.

### 2. SQLite with WAL journal mode

**Why not JSON:** The original storage was a flat JSON file with an in-memory lock for concurrency. This broke under Gunicorn's multi-worker model (each worker has its own lock copy). SQLite with WAL journal mode handles concurrent reads and writes safely across threads and processes without application-level locking.

**Why not PostgreSQL:** SQLite requires zero setup, zero configuration, and zero administration. The dataset is small (a few KB per season). The database file lives in a Docker volume and can be backed up with `cp`.

Migration from legacy JSON is automatic on first run (`storage._migrate_json_to_sqlite`).

### 3. Targeted SQL operations vs. full-state save

The web server never calls `save_data()` (a destructive full-state rewrite). Instead, it uses targeted operations — `add_player()`, `set_prediction()`, `set_results()` — each using `BEGIN IMMEDIATE` transactions. This avoids read-modify-write races between concurrent Gunicorn workers and keeps writes to exactly the data that changed.

### 4. Bearer token auth injected into the frontend

All write endpoints require `Authorization: Bearer <API_TOKEN>`. The token is set once via environment variable and never exposed to the client... until they need to submit predictions.

**The problem:** The frontend (vanilla JS, no build step) couldn't securely store the token. The solution: Flask injects the token into the HTML page as a JS variable (`const _API_TOKEN = "..."`). The frontend uses a `_writeHeaders()` helper that includes the `Authorization` header on all write fetch calls. The token is visible in the page source but the dashboard is only accessible over Tailscale or localhost — both trusted contexts.

### 5. FastF1 → OpenF1 → manual entry fallback chain

Race results are fetched via a three-tier chain:

1. **FastF1** (official F1 timing data) — primary source, requires `fastf1` Python package
2. **OpenF1** (community REST API) — fallback when FastF1 is unavailable or returns no results
3. **Manual entry** — user types results into the dashboard

**Critical quirk:** FastF1 globally monkey-patches `requests` with aggressive caching. All OpenF1 calls must use `urllib.request` directly to bypass stale cached responses.

**OpenF1 endpoint order is strict:** `/meetings` → `/sessions` → `/session_result` → `/drivers`. Driver names must be fetched with `meeting_key` (not `session_key`) to avoid null `broadcast_name` values.

### 6. Test database isolation via autouse fixture

Every test redirects `storage.DATA_DB_FILE` to a temporary path via an autouse fixture in `conftest.py`. This ensures no test can accidentally read or write the production database. The fixture also patches private module globals (`_JSON_FILE`, `_DB_PATH`) so legacy migration checks don't try to parse SQLite files as JSON.

### 7. JavaScript scoring mirrors Python exactly

The dashboard scoring logic (`calcPlayerPoints`, `calcStrEquality`) in `index.html` is a line-by-line JavaScript port of `scoring.py`. On page load, the frontend fetches `/aliases` and merges the server's alias table into its local `ALIASES` dict, keeping both in sync without a build step.

### 8. Rate limiting by endpoint

Write endpoints have stricter rate limits than reads:

| Endpoint | Rate limit |
|----------|-----------|
| `GET /data`, `GET /aliases` | 300/hr, 60/min |
| `POST /predictions` | 60/hr, 10/min |
| `POST /results` | 30/hr, 5/min |
| `POST /races/fetch-results` | 10/hr, 2/min |
| `POST /players`, `POST /races`, `DELETE` | 20/hr, 5/min |

Request bodies are capped at 16 KB. Rate limiting uses in-memory storage (flask-limiter) and is disabled during tests.

### 9. 409 for duplicates, not 400

When a resource already exists (player, race, prediction, results), the API returns `409 Conflict` — not `400 Bad Request`. This lets clients distinguish "that name is taken" from "that name is invalid" without parsing error messages.

### 10. Docker + Tailscale sidecar

The Docker Compose setup runs two containers sharing a network namespace:

- **web** — Gunicorn with 2 workers, SQLite WAL, data volume at `./data:/data`
- **tailscale** — Official Tailscale image, exposes port 5001 on your tailnet

The Tailscale container uses `TS_SERVE_PORT=5001` to auto-configure `tailscale serve`. The dashboard is then available at `https://<hostname>.<tailnet>.ts.net`.

### 11. No CSS framework, no JS framework, no build step

The frontend is a single `index.html` with embedded CSS and JS. The styling uses CSS custom properties for theming (aerospace-inspired dark mode). The scoring logic is reimplemented in JS but kept in sync with the Python backend via the `/aliases` endpoint.

This eliminates:
- Node.js dependency
- `npm install` / `yarn` step
- Webpack/Vite/esbuild configuration
- Framework churn

The tradeoff is that the HTML file is ~2300 lines. For a single-page dashboard of this size, that's acceptable.

## Module Boundaries

| Module | Role | Dependencies |
|--------|------|-------------|
| `scoring.py` | Pure game math | stdlib only |
| `drivers.py` | Hardcoded 2026 roster | stdlib only |
| `models.py` | TypedDict type definitions | stdlib only |
| `exceptions.py` | Error hierarchy | stdlib only |
| `storage.py` | SQLite persistence, JSON migration | stdlib, `exceptions`, `models` |
| `api.py` | FastF1/OpenF1 result fetching | stdlib, `fastf1`, `models`, `exceptions` |
| `web/server.py` | Flask HTTP layer | `flask`, `flask-limiter`, `points_are_bad.*` |
| `web/index.html` | Dashboard UI | none (fetches `/data`, `/aliases`) |

The dependency graph is intentionally layered: `scoring`/`drivers`/`models`/`exceptions` are leaf modules. `storage` and `api` depend on them. `web/server.py` orchestrates everything.

## Data Model

```
players          races              race_results       predictions
────────         ─────              ────────────       ───────────
name (PK)   ─┬── id (PK)      ┌─── race_id (FK)  ┌── race_id (FK)
             ├── name (UNIQUE) ┤    position       ┤   player_name (FK)
             └── date          ┤    abbr           ┤   position
                               └─── driver_name    ┤   driver_key
                                                   └── (race_id, player_name, position) PK
```

Predictions are stored as lowercase canonical driver keys from `drivers.py`. Actual results are `{name, abbr}` dicts. All player names are lowercased on write.

## File Layout

```
.
├── src/points_are_bad/    # Python package
│   ├── api.py
│   ├── drivers.py
│   ├── exceptions.py
│   ├── models.py
│   ├── scoring.py
│   └── storage.py
├── web/                   # Web layer
│   ├── server.py
│   └── index.html
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_drivers.py
│   ├── test_models.py
│   ├── test_scoring.py
│   ├── test_storage.py
│   └── test_web_server.py
├── scripts/               # Docker helpers
│   ├── build.sh
│   ├── start.sh
│   └── stop.sh
├── Dockerfile
├── docker-compose.yml
├── gunicorn.conf.py
├── pyproject.toml
└── data/                  # Docker volume mount (gitignored)
    └── points_are_bad_data.db
```
