# Points Are Bad — F1 Prediction Game

A Python CLI for playing "Points are Bad" — a Formula 1 prediction game among friends where players predict the Top 10 finishers of every Grand Prix. The objective is to accumulate the *fewest* points across the season.

## Rules

- Players predict the Top 10 finishers before every GP (usually after qualifying).
- Each incorrect prediction slot scores **+1 point**.
- A missing prediction for a race scores a flat **+10 point penalty**.
- The player with the fewest points at the end of the season wins.

## Requirements

- Python 3.9+
- [uv](https://github.com/astral-sh/uv)

## Installation

```bash
git clone <repo>
cd points-are-bad
uv venv
uv pip install -e .[dev]   # omit [dev] to skip test/lint tools
```

## Running

```bash
.venv/bin/points-are-bad
```

Data is auto-created at `points_are_bad_data.json` in the working directory. Override with `POINTS_DATA_FILE=/path/to/file.json`.

## Testing

```bash
.venv/bin/pytest tests/ -v                    # run all tests
.venv/bin/pytest tests/test_scoring.py -v     # single module
.venv/bin/pytest tests/ --cov=points_are_bad  # with coverage
```

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

tests/
  conftest.py         Shared fixtures (sample_data, no_clear_screen)
  test_scoring.py     56 tests — 100% coverage of scoring.py
  test_storage.py     Round-trip, error-path tests — 100% storage.py
  test_drivers.py     Roster integrity, lookup helpers
  test_cli_utils.py   Pure CLI helpers, mocked select_item
  test_cli_menus.py   Interactive menus with mocked input()
  test_api.py         urllib + fastf1 mocked, all fallback paths
```

### Key data flow

1. `cli.py:main_menu()` loads `GameData` from JSON via `storage.load_data()`.
2. On startup it calls `auto_update_past_races()` which fetches missing results via `api.fetch_results()`.
3. Scoring is always delegated to `scoring.calculate_player_points_for_race()` — the single source of truth for per-race points.
4. All writes go through `storage.save_data()`.

### API quirk — FastF1 monkey-patches `requests`

FastF1 aggressively caches via `requests`. All OpenF1 calls inside `api.py` therefore use `urllib.request` directly to avoid stale cached responses. Do **not** introduce `requests` calls in `api.py`.

### OpenF1 endpoint order

Must call in sequence: `/meetings` → `/sessions` → `/session_result` → `/drivers`. Use `meeting_key` (not `session_key`) when fetching drivers to avoid null `broadcast_name` values.

## Features

- **Player management** — add/remove players at any time.
- **Race schedule** — auto-populate from FastF1; dates are kept in sync.
- **Driver-select UI** — interactive picker grouped by team, with a confirmation screen.
- **Automated result fetching** — FastF1 (official) → OpenF1 (community) → manual entry.
- **Points breakdown** — per-position view for any race across all players.
- **Season standings** — live table sorted by fewest points.
