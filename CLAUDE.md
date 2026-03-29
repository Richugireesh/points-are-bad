# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (uses uv)
uv venv && uv pip install -e .[dev]

# Run
.venv/bin/points-are-bad

# Test
pytest tests/ -v

# Single test
pytest tests/test_scoring.py::test_function_name -v

# With coverage
pytest tests/ --cov=points_are_bad
```

## Architecture

The app is a CLI/TUI game where players predict F1 Top-10 finishers and compete for the **lowest** score (wrong prediction = +1pt, missing = +10pt, perfect = 0pt).

**Module responsibilities:**

- `cli.py` — Primary entry point. Full terminal UI: menus, input loops, box-drawing display, and orchestration. No scoring math or HTTP requests live here.
- `scoring.py` — Pure game logic with no external imports. `calculate_str_equality()` does flexible driver name matching (case-insensitive, alias-aware substrings). `calculate_season_standings()` aggregates scores.
- `api.py` — FastF1 (primary) → OpenF1 (fallback) → manual entry. **Critical quirk:** FastF1 monkey-patches `requests` with aggressive caching, so all OpenF1 calls must use `urllib.request`, never `requests`.
- `storage.py` — Loads/saves `points_are_bad_data.json`. Override path with `POINTS_DATA_FILE` env var.
- `drivers.py` — Hardcoded 2026 grid (22 drivers). Predictions are stored as canonical driver `key` values from this file.

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
