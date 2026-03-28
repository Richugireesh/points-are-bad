# Points Are Bad - F1 Prediction Game

A Python CLI for playing "Points are Bad" — a Formula 1 prediction game among friends where players predict the Top 10 finishers of every Grand Prix. The objective is to accumulate the *least* amount of points across the season.

## Rules

- Players predict the Top 10 finishers before every GP (usually after qualifying).
- Each incorrect prediction slot scores **+1 point**.
- A missing prediction for a race scores a flat **+10 point penalty**.
- The player with the fewest points at the end of the season wins.

## Installation

Requires Python 3.9+ and [uv](https://github.com/astral-sh/uv).

```bash
git clone <repo>
cd points-are-bad
uv venv
uv pip install -e .[dev]   # omit [dev] to skip pytest
```

## Running

```bash
source .venv/bin/activate
points-are-bad
```

Or without activating the virtual environment:

```bash
.venv/bin/points-are-bad
```

Data is stored in `points_are_bad_data.json` in the working directory (auto-created on first run).

## Testing

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Features

- **Player Management**: Add or remove players from the game.
- **Race Schedule**: Fetches the current-season schedule from FastF1 and syncs it to local data.
- **Driver-Select UI**: Interactive picker grouped by team — scroll through the 2026 grid (22 drivers, 11 teams) and select your Top 10. Includes a confirmation screen before saving.
- **Automated Results Fetching**:
  1. Attempts **FastF1** for official race classification.
  2. Falls back to **OpenF1** if FastF1 results are not yet published.
  3. Falls back to manual entry if both APIs are unavailable.
- **Points Breakdown**: Per-position scoring breakdown for any race, showing all players.
- **Season Standings**: Live standings table based on `points_are_bad_data.json`.

## Package Structure

```
src/points_are_bad/
    cli.py        # menus, UI, all user interaction
    scoring.py    # points calculation and alias resolution
    api.py        # FastF1 + OpenF1 data fetching
    storage.py    # load/save points_are_bad_data.json
    drivers.py    # 2026 F1 roster (22 drivers, 11 teams)
tests/
    test_scoring.py
    test_storage.py
```
