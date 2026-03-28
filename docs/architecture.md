# Architecture

## Module overview

```
src/points_are_bad/
├── cli.py        Entry point — launches TUI; legacy CLI preserved as _cli_main()
├── tui.py        Textual TUI: all screens, views, modals, widgets
├── scoring.py    Pure scoring logic: alias resolution, per-position and season scoring
├── api.py        External data: FastF1 + OpenF1 results, race schedule
├── storage.py    JSON read/write for points_are_bad_data.json
└── drivers.py    2026 F1 driver roster (22 drivers, 11 teams)
```

## Dependency graph

```
cli.py / tui.py          (presentation)
    │
    ├── scoring.py        (pure math, no I/O)
    ├── api.py            (HTTP, no state mutation)
    ├── storage.py        (JSON I/O only)
    └── drivers.py        (static data)
```

- `scoring.py`, `api.py`, `storage.py`, and `drivers.py` do **not** import from each other.
- Only the presentation layer (`cli.py` / `tui.py`) coordinates between modules.
- No module calls `save_data` except the presentation layer and `auto_update_past_races`.

## Data flow

```
User action (TUI)
    │
    ├─ read  ──► storage.load_data() ──► points_are_bad_data.json
    │
    ├─ score ──► scoring.calculate_*()   (pure, no I/O)
    │
    ├─ fetch ──► api.fetch_results()
    │                 ├── FastF1 (requests, cached)
    │                 └── OpenF1 (urllib.request, uncached)
    │
    └─ write ──► storage.save_data() ──► points_are_bad_data.json
```

## Key design decisions

### Predictions stored as canonical keys

Predictions are stored as lowercase driver keys (`"verstappen"`, `"norris"`) rather than full names or abbreviations. This makes the data human-readable, resilient to API response format changes, and easy to type. The alias table in `scoring.py` resolves common shorthands at scoring time.

### Actual results stored as `{"abbr": "VER", "name": "Max Verstappen"}`

Actual results from the API are slimmed to two fields before saving:
- `abbr`: 3-letter FIA code (for uniqueness)
- `name`: Full display name (for readability and substring scoring)

The scoring engine checks whether a prediction is a substring of the name, so `"verstappen"` correctly matches `"Max Verstappen"`.

### urllib vs requests for OpenF1

FastF1 globally monkey-patches the `requests` library with aggressive disk caching. Any secondary HTTP call made with `requests` (including to OpenF1) would be served stale or cause cache-related errors. All OpenF1 fetches use `urllib.request` to bypass this. See `api.py` → `_fetch_openf1_json`.

### OpenF1 endpoint sequence

OpenF1 requires a specific call order to get fully-populated driver names:

```
/meetings?year=X          → meeting_key
/sessions?meeting_key=X   → session_key
/session_result?session_key=X  → position data
/drivers?meeting_key=X    → driver names (must use meeting_key, not session_key)
```

Using `session_key` for the drivers endpoint returns null `broadcast_name` values.

### Background threads in the TUI

API fetches (results, schedule sync) run on background threads via Textual's `@work(thread=True)` decorator. UI updates from those threads use `call_from_thread` / `app.call_from_thread`. This keeps the TUI responsive during network calls.

### No scoring logic in the TUI

The TUI never computes points directly — it always calls into `scoring.py`. This keeps the presentation layer thin and makes scoring testable independently.

## Threading model

```
Main thread (Textual event loop)
    │
    ├── UI rendering and user input
    ├── Screen/modal push/pop
    └── call_from_thread() ─────────────────────────────┐
                                                         │
Background workers (@work thread=True)                  │
    ├── api.fetch_results()      ──► call_from_thread() ─┤
    └── api.get_schedule_updates() ──► call_from_thread() ┘
```
