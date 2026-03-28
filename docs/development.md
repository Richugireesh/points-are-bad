# Development Guide

## Setup

```bash
git clone <repo>
cd points-are-bad
uv venv
uv pip install -e .[dev]
source .venv/bin/activate
```

## Project layout

```
points-are-bad/
├── src/points_are_bad/
│   ├── __init__.py
│   ├── cli.py          Entry point + legacy CLI
│   ├── tui.py          Textual TUI
│   ├── scoring.py      Scoring logic
│   ├── api.py          FastF1 + OpenF1
│   ├── storage.py      JSON I/O
│   └── drivers.py      2026 driver roster
├── tests/
│   ├── test_scoring.py
│   └── test_storage.py
├── docs/               This documentation
├── pyproject.toml
└── points_are_bad_data.json   (runtime, not committed)
```

## Running tests

```bash
pytest tests/ -v
```

56 tests cover scoring (48) and storage (8). All tests must pass before merging.

```bash
pytest tests/ -v --cov=src/points_are_bad --cov-report=term-missing
```

## Key principles

1. **No scoring logic outside `scoring.py`** — the TUI and CLI always delegate to `scoring.calculate_*`.
2. **No `save_data` outside the presentation layer** — `api.py`, `scoring.py`, and `drivers.py` never write to disk.
3. **No `requests` in `api.py`** — OpenF1 calls use `urllib.request` only to bypass FastF1's global cache patch. See [Architecture](architecture.md#urllib-vs-requests-for-openf1).
4. **Predictions stored as canonical keys** — always lowercase driver last names (e.g. `"verstappen"`), never aliases.

## Adding a driver or updating the roster

Edit `src/points_are_bad/drivers.py` → `ROSTER`:

```python
{"abbr": "NEW", "name": "New Driver", "team": "Some Team", "key": "driver"},
```

- `key` must be a unique lowercase string matching what `scoring._normalize()` produces (usually the last name).
- Add aliases for common shorthands to `ALIASES` in `scoring.py`:
  ```python
  "nd":       "driver",
  "newdriver":"driver",
  ```
- Update `TEAM_COLORS` in `tui.py` if a new team is added.

## Adding a new season

1. Update `ROSTER` in `drivers.py` with any driver changes.
2. Add/update aliases in `scoring.py` → `ALIASES`.
3. Update team colours in `tui.py` → `TEAM_COLORS` if team names changed.
4. Use **Admin → Sync from FastF1** in the TUI to pull the new season schedule.

## Writing tests

Tests live in `tests/`. Use `monkeypatch` for isolation:

```python
@pytest.fixture
def isolated_data_file(tmp_path, monkeypatch):
    path = tmp_path / "test_data.json"
    monkeypatch.setattr("points_are_bad.storage.DATA_FILE", str(path))
    return path
```

Scoring tests should not touch the filesystem — `scoring.py` is pure.

## Branches

| Branch | Purpose |
|---|---|
| `master` | Stable, tagged releases |
| `stable` | Current stable working state |
| `tui-interface` | TUI development (current active branch) |

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `POINTS_DATA_FILE` | `points_are_bad_data.json` | Path to data file |

## FastF1 cache

FastF1 writes session data to `./fastf1_cache/`. This directory is created automatically. Add it to `.gitignore` if not already present. It can grow large (100s of MB) over a season.

## Textual version

The TUI targets Textual 8.x. Key API notes for this version:

- `ModalScreen` is imported from `textual.screen`, not `textual.widgets`.
- Background tasks use `@work(thread=True)` + `call_from_thread` for UI updates.
- `ListView.Selected` event carries the selected `ListItem` as `event.item`.
- `ContentSwitcher` uses `.current` (a string ID) to switch panes.
