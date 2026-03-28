# API Reference

Module-by-module reference for all public functions and constants.

---

## `storage.py`

Handles reading and writing `points_are_bad_data.json`.

### Constants

| Name | Type | Default | Description |
|---|---|---|---|
| `DATA_FILE` | `str` | `"points_are_bad_data.json"` | Path to data file. Override via `POINTS_DATA_FILE` env var. |

### Functions

#### `load_data() -> dict`

Loads game state from `DATA_FILE`.

Returns `{"players": [], "races": []}` if the file does not exist. Never raises — a missing file is treated as an empty game.

```python
data = load_data()
players = data["players"]   # list[str]
races   = data["races"]     # list[dict]
```

---

#### `save_data(data: dict) -> None`

Writes `data` to `DATA_FILE` as indented JSON (4 spaces). Creates the file if it doesn't exist, overwrites it if it does.

```python
data["players"].append("alice")
save_data(data)
```

---

## `scoring.py`

Pure scoring logic. No I/O. All functions are deterministic.

### Constants

#### `ALIASES: dict[str, str]`

Maps driver shorthands to canonical last-name keys used in predictions. Applied by `_normalize()`. ~53 entries.

Selected aliases:

| Alias(es) | Canonical key |
|---|---|
| `ver`, `max` | `verstappen` |
| `ant`, `kimi` | `antonelli` |
| `nor`, `lando` | `norris` |
| `pia`, `oscar` | `piastri` |
| `lec`, `charles` | `leclerc` |
| `ham`, `lewis` | `hamilton` |
| `rus`, `george` | `russell` |
| `had`, `hadj` | `hadjar` |
| `lin`, `linblad` | `lindblad` |
| `bor`, `gabby` | `bortoleto` |

Full table is in `src/points_are_bad/scoring.py`.

### Functions

#### `calculate_str_equality(prediction: str, actual: str | dict) -> bool`

Returns `True` if `prediction` matches `actual`.

**Matching rules:**
1. Both sides are normalized (lowercased, stripped, aliases resolved).
2. Match succeeds if the normalized prediction is a **substring** of the normalized actual, or vice versa.
3. When `actual` is a dict (API result), all values are checked: `name`, `abbr`, `BroadcastName`, `FirstName`, `LastName`, `Abbreviation`.
4. The special string `"(none)"` never matches anything.

```python
calculate_str_equality("rus", "George Russell")  # True  (alias → substring)
calculate_str_equality("nor", {"name": "Lando Norris", "abbr": "NOR"})  # True
calculate_str_equality("piastri", "Max Verstappen")  # False
```

---

#### `score_position(pred: str | None, actual_entry: str | dict | None) -> int`

Scores a single prediction slot.

| `pred` | `actual_entry` | Return |
|---|---|---|
| `None` | `None` | `0` (nothing to compare) |
| non-None | `None` | `1` (predicted something, no actual) |
| `None` | non-None | `1` (no prediction, actual exists) |
| match | match | `0` |
| mismatch | mismatch | `1` |

```python
score_position("russell", {"name": "George Russell", "abbr": "RUS"})  # 0
score_position("norris",  {"name": "George Russell", "abbr": "RUS"})  # 1
score_position(None, None)   # 0
score_position(None, "RUS")  # 1
```

---

#### `calculate_player_points_for_race(prediction: list, actual: list) -> int`

Total points for one player in one race.

Iterates positions 0–9. At each position: if either list is shorter, that side is treated as `None`. Sums `score_position` results.

**Does not apply the +10 missing-prediction penalty** — that is applied by `calculate_season_standings`.

```python
actual = [{"abbr": "RUS", "name": "George Russell"}, ...]
pred   = ["russell", "antonelli", "leclerc", "piastri", ...]
pts = calculate_player_points_for_race(pred, actual)   # e.g. 7
```

---

#### `calculate_season_standings(data: dict) -> tuple[dict[str, int], int]`

Returns `(scores, races_counted)` across the whole season.

- `scores`: `{player_name: total_points}` — includes all players in `data["players"]`
- `races_counted`: number of races that have actual results

For each race with results, each player in `data["players"]` who has **no prediction** for that race receives a flat +10 penalty instead of being scored normally.

```python
scores, n = calculate_season_standings(data)
# scores == {"richu": 17, "sam": 18, "danny": 19}
# n      == 2
```

---

## `drivers.py`

Static 2026 F1 driver roster.

### Constants

#### `ROSTER: list[dict]`

22 drivers across 11 teams. Each entry:

```python
{
    "abbr": "VER",           # 3-letter FIA code
    "name": "Max Verstappen", # Full display name
    "team": "Red Bull",       # Team name
    "key":  "verstappen",     # Canonical key (used in predictions)
}
```

Order: McLaren, Ferrari, Mercedes, Red Bull, Racing Bulls, Aston Martin, Williams, Alpine, Haas, Audi, Cadillac.

### Functions

#### `by_key(key: str) -> dict | None`

Returns the driver dict for a canonical key, or `None`.

```python
by_key("verstappen")   # {"abbr": "VER", "name": "Max Verstappen", ...}
by_key("VER")          # None  (use by_abbr for abbreviations)
by_key("unknown")      # None
```

---

#### `by_abbr(abbr: str) -> dict | None`

Returns the driver dict for a 3-letter abbreviation, or `None`. Case-insensitive.

```python
by_abbr("VER")   # {"abbr": "VER", "name": "Max Verstappen", ...}
by_abbr("ver")   # same
```

---

## `api.py`

Fetches race results and schedules from FastF1 and OpenF1.

### Constants

| Name | Type | Description |
|---|---|---|
| `HAS_FASTF1` | `bool` | `True` if the `fastf1` package is installed |

### Functions

#### `fetch_fastf1_results(year: int, race_name: str) -> list[dict] | None`

Fetches official top-10 race results via FastF1. Enables local disk caching in `./fastf1_cache/`.

Returns a list of 10 `{"abbr": "...", "name": "..."}` dicts (P1 first), or `None` if:
- FastF1 is not installed
- Results are not yet published for this session
- Any exception occurs

Prints progress messages to stdout.

```python
results = fetch_fastf1_results(2026, "Australian Grand Prix")
# [{"abbr": "RUS", "name": "George Russell"}, ...]
```

---

#### `fetch_openf1_results(year: int, race_name: str) -> list[dict] | None`

Fallback results source using the OpenF1 public API.

Follows the required endpoint sequence:
1. `/meetings?year=X` → resolve `meeting_key` by fuzzy-matching `race_name`
2. `/sessions?meeting_key=X&session_type=Race` → get `session_key`
3. `/session_result?session_key=X&position<=10` → position data
4. `/drivers?meeting_key=X` → driver names (meeting_key avoids null names)

Returns the same format as `fetch_fastf1_results`, or `None` on failure.

**Important:** Uses `urllib.request`, never `requests`, to bypass FastF1's global cache monkey-patch.

---

#### `fetch_results(year: int, race_name: str) -> list[dict] | None`

Unified entry point. Tries FastF1 first; falls back to OpenF1 if FastF1 fails or is unavailable. Returns `None` if both fail.

```python
results = fetch_results(2026, "Chinese Grand Prix")
```

---

#### `get_schedule_updates(existing_races: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]`

Fetches the current-season schedule from FastF1 and diffs it against `existing_races`.

Returns `(new_races, date_updates)`:
- `new_races`: list of race dicts ready to append to `data["races"]`
- `date_updates`: list of `(existing_race_dict, new_date_str)` pairs

**Does not mutate `existing_races` or call `save_data`**. The caller is responsible for applying changes and saving.

Raises `RuntimeError` if FastF1 is not installed.

```python
new, updates = get_schedule_updates(data["races"])
for race, date in updates:
    race["date"] = date
data["races"].extend(new)
save_data(data)
```

---

## `cli.py`

Entry point and legacy terminal CLI.

### Entry point

#### `main_menu() -> None`

Registered as the `points-are-bad` console script. Launches the Textual TUI via `tui.run()`.

### Legacy terminal CLI

#### `_cli_main() -> None`

Plain terminal menu loop (no Textual dependency). Preserved as a fallback. Provides:
- Enter Predictions
- View Race Results & Points
- View Season Standings
- Manage Players / Races
- Enter Race Results

#### `auto_update_past_races(data: dict) -> None`

Called on startup by `_cli_main`. Scans all races where:
- `date` ≤ today's date
- `actual_results` is empty

For each, calls `fetch_results` and saves if successful. Prints progress and waits for user confirmation.

---

## `tui.py`

Textual TUI application. All screens, views, modals, and widgets.

### Entry point

#### `run() -> None`

Instantiates `PointsAreBadApp` and calls `.run()`. Called by `cli.main_menu`.

### App

#### `PointsAreBadApp(App)`

Main application. Holds `data: dict` as an instance attribute (loaded on mount, saved on quit).

**Keybindings:**

| Key | Action |
|---|---|
| `q` | Quit (saves data) |
| `1` | Switch to Dashboard |
| `2` | Switch to Standings |
| `3` | Switch to Race Points |
| `4` | Switch to Predictions |
| `5` | Switch to Admin |

### Modal screens

All modals are pushed via `app.push_screen(modal, callback)` and dismissed with a typed return value.

#### `ConfirmModal(title: str, body: str) -> bool`

Yes/No dialog. Returns `True` (yes) or `False` (no/Esc).

Keybindings: `y` → yes, `n`/`Esc` → no.

#### `InputModal(title: str, placeholder: str = "") -> str | None`

Single text field. Returns the trimmed string, or `None` if canceled/empty.

Submits on Enter or "OK" button.

#### `SelectModal(title: str, items: list[tuple[str, object]]) -> object | None`

Scrollable list of `(display_label, payload)` pairs. Returns the chosen payload, or `None` if canceled.

### Interactive screens

#### `DriverPickerScreen(race_name: str, player: str, existing: list[str] | None = None) -> list[str] | None`

Full-screen driver picker. Shows all 22 drivers grouped by team with team accent colours. Selecting a driver toggles it in/out of the pick list.

Returns a list of canonical driver keys (up to 10), or `None` if canceled.

**Keybindings:**

| Key | Action |
|---|---|
| `↑` / `↓` | Navigate driver list |
| `Enter` | Toggle driver in/out of picks |
| `Del` / `Backspace` | Remove last pick |
| `F10` | Save current picks |
| `Esc` | Cancel (discard picks) |

#### `ManualResultsScreen(race: dict) -> None`

Screen for entering top-10 results one per line. Saves directly to `race["actual_results"]` on "Save".

### Views (ContentSwitcher panes)

#### `DashboardView`

Shows: season context (year, player count, races done), next upcoming race, current standings with medal emojis and gap-to-lead.

Refreshes when shown.

#### `StandingsView`

DataTable: rank (medal), player name, total points, gap to leader. Refreshes when shown.

#### `RacePointsView`

"Select Race" button → `SelectModal` → displays:
- Score summary for all players (with mini bar visualization)
- Per-player position-by-position breakdown (green ✓ / red ✗)

#### `PredictionsView`

Two-step selection (race, then player), then launches `DriverPickerScreen`. Shows any existing prediction. Warns before overwriting.

#### `AdminView`

| Button | Action |
|---|---|
| Add Player | `InputModal` → append to `data["players"]` |
| Remove Player | `SelectModal` → `ConfirmModal` → remove |
| Auto-Fetch Results | `SelectModal` (race) → `_do_autofetch` (background thread) |
| Manual Entry | `SelectModal` (race) → `ManualResultsScreen` |
| Sync from FastF1 | `_do_sync_schedule` (background thread) |
| Add Race | Two `InputModal`s (name, date) → append to `data["races"]` |
| Remove Race | `SelectModal` → `ConfirmModal` → remove |
