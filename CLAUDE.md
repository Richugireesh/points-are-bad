# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (uses uv)
uv venv && uv pip install -e '.[dev,web]'

# Run CLI
.venv/bin/points-are-bad

# Run web dashboard — development (Flask dev server, → http://localhost:5001)
uv run web/server.py
# or after installing scripts:
points-are-bad-web

# Run web dashboard — production (Gunicorn, workers=1 required — see gunicorn.conf.py)
gunicorn -c gunicorn.conf.py web.server:app

# Docker
docker build -t points-are-bad . && docker run -p 5001:5001 -v $(pwd)/data:/data points-are-bad
# or: mkdir -p data && API_TOKEN=$(openssl rand -hex 32) docker compose up

# Test
pytest tests/ -v

# Single test
pytest tests/test_scoring.py::TestNormalize -v

# Web server tests only
pytest tests/test_web_server.py -v

# With coverage
pytest tests/ --cov=points_are_bad
```

## Architecture

The app is a CLI/TUI game where players predict F1 Top-10 finishers and compete for the **lowest** score (wrong prediction = +1pt, missing = +10pt, perfect = 0pt).

Source lives under `src/points_are_bad/`. **Module responsibilities:**

- `cli.py` — Primary entry point. Full terminal UI: menus, input loops, box-drawing display, and orchestration. No scoring math or HTTP requests live here.
- `scoring.py` — Pure game logic with no external imports. `calculate_str_equality()` does flexible driver name matching (case-insensitive, alias-aware substrings). `calculate_season_standings()` aggregates scores. `ALIASES` dict is the single source of truth for driver shorthands — the web API exposes it via `GET /aliases`.
- `api.py` — FastF1 (primary) → OpenF1 (fallback) → manual entry. **Critical quirk:** FastF1 monkey-patches `requests` with aggressive caching, so all OpenF1 calls must use `urllib.request`, never `requests`.
- `storage.py` — Loads/saves `points_are_bad_data.json`. Override path with `POINTS_DATA_FILE` env var.
- `drivers.py` — Hardcoded 2026 grid (22 drivers). Predictions are stored as canonical driver `key` values from this file.
- `models.py` — `TypedDict` definitions (`GameData`, `RaceData`, `DriverResult`, `DriverInfo`) mirroring the JSON structure. `actual_results` entries can be `DriverResult` dicts (API path) or plain strings (manual entry).
- `exceptions.py` — Exception hierarchy rooted at `PointsAreBadError`: `ApiError`, `StorageError`, `DataValidationError`.

**Web layer** lives under `web/`:

- `web/server.py` — Flask server. Endpoints: `GET /data`, `GET /aliases`, `POST /predictions`, `POST /results`, `POST /players`. All writes use `_data_lock` (threading.Lock). Errors use `_err(msg, code)` helper; duplicates return 409 so clients can distinguish them from invalid-input 400s. Write endpoints are protected by Bearer token auth (`API_TOKEN` env var) and per-route rate limits via flask-limiter. Request bodies are capped at 16 KB (`MAX_CONTENT_LENGTH`). Rate limiting is disabled in tests by monkeypatching `limiter.enabled = False` in the `client` fixture.
- `web/index.html` — Single-page dashboard. No build step. Fetches `/aliases` on load and merges into local `ALIASES` dict. JS scoring (`calcPlayerPoints`) mirrors `scoring.py` exactly.

## API Quirks

**FastF1 caching:** FastF1 patches `requests` globally. Any secondary HTTP calls (OpenF1, schedule fetching) must use `urllib.request` to avoid stale cached responses.

**OpenF1 endpoint order matters:** Must call in sequence: `/meetings` → `/sessions` → `/session_result` → `/drivers`. Use `meeting_key` (not `session_key`) when fetching drivers to avoid null names.

## Data Model

JSON structure in `points_are_bad_data.json`:
```json
{
  "players": ["Alice", "Bob"],
  "races": [{
    "name": "Australian Grand Prix",
    "date": "2026-03-08",
    "actual_results": [{"name": "Max Verstappen", "abbr": "VER"}, ...],
    "predictions": {
      "Alice": ["verstappen", "norris", ...],
      "Bob": ["leclerc", "piastri", ...]
    }
  }]
}
```

Predictions are stored as lowercase driver keys (from `drivers.py`); `actual_results` entries are dicts with `name`/`abbr`.
