import json
import os
import sys
import datetime
import logging
import re

try:
    import fastf1
    HAS_FASTF1 = True
    logging.getLogger('fastf1.req').setLevel(logging.CRITICAL)
except ImportError:
    HAS_FASTF1 = False

import urllib.request
import urllib.error

from textual.app import App, ComposeResult
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Header, Footer, ListView, ListItem, Label, Button,
    Input, TextArea, DataTable, LoadingIndicator, Static, Markdown
)
from textual.containers import Vertical, Horizontal, VerticalScroll, Center
from textual.binding import Binding
from textual import work
from rich.text import Text

DATA_FILE = "points_are_bad_data.json"

# ─────────────────────────────────────────────
#  Data helpers (unchanged logic)
# ─────────────────────────────────────────────

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"players": [], "races": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def parse_raw_input_lines(lines, max_items):
    text = "\n".join(lines)
    text = text.replace('\u2060', '').replace('\u200b', '')
    cleaned_text = re.sub(r'\d+\s*[.)]', '|', text)
    parts = []
    for chunk in re.split(r'[|\n,]', cleaned_text):
        chunk = chunk.strip()
        if chunk.startswith('('):
            chunk = chunk[1:].strip()
        if chunk:
            parts.append(chunk)
    return parts[:max_items]

def calculate_str_equality(a, b):
    p = str(a).strip().lower()
    p = p.replace('\u2060', '').replace('\u200b', '').strip()
    aliases = {
        "kimi": "antonelli", "lec": "leclerc", "ver": "verstappen",
        "max": "verstappen", "ham": "hamilton", "nor": "norris",
        "pia": "piastri", "rus": "russell", "lind": "lindblad",
        "linblad": "lindblad", "bor": "bortoleto", "gabby": "bortoleto",
        "gab": "bortoleto", "hadj": "hadjar", "alo": "alonso",
        "per": "perez", "checo": "perez", "gas": "gasly", "oco": "ocon",
        "tsu": "tsunoda", "yuki": "tsunoda", "hul": "hulkenberg",
        "str": "stroll", "mag": "magnussen", "alb": "albon",
        "col": "colapinto", "bea": "bearman", "ollie": "bearman",
        "sai": "sainz", "zho": "zhou", "bot": "bottas",
        "law": "lawson", "doo": "doohan"
    }
    if p in aliases:
        p = aliases[p]
    if isinstance(b, dict):
        for val in b.values():
            if val and p == str(val).strip().lower():
                return True
        for val in b.values():
            if val and p in str(val).strip().lower():
                return True
        return False
    else:
        b_str = str(b).strip().lower()
        if b_str in aliases:
            b_str = aliases[b_str]
        return p == b_str or p in b_str

def calculate_player_points_for_race(prediction, actual):
    points = 0
    for i in range(min(len(prediction), len(actual))):
        if not calculate_str_equality(prediction[i], actual[i]):
            points += 1
    diff = abs(len(prediction) - len(actual))
    points += diff
    return points

def fetch_fastf1_results(year, race_name):
    if not HAS_FASTF1:
        return None
    try:
        cache_dir = os.path.abspath('fastf1_cache')
        os.makedirs(cache_dir, exist_ok=True)
        fastf1.Cache.enable_cache(cache_dir)
        session = fastf1.get_session(year, race_name, 'R')
        session.load(telemetry=False, laps=False, weather=False)
        if 'Position' not in session.results.columns or session.results['Position'].isnull().all():
            return None
        results = session.results.dropna(subset=['Position']).sort_values(by='Position').head(10)
        drivers = []
        for _, row in results.iterrows():
            drivers.append({
                "BroadcastName": str(row.get("BroadcastName", "")),
                "FirstName": str(row.get("FirstName", "")),
                "LastName": str(row.get("LastName", "")),
                "Abbreviation": str(row.get("Abbreviation", ""))
            })
        return drivers
    except Exception:
        return None

def _fetch_openf1_json(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 points-are-bad/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status != 200:
                return None
            return json.loads(response.read().decode())
    except Exception:
        return None

def fetch_openf1_results(year, race_name):
    try:
        meetings_url = f"https://api.openf1.org/v1/meetings?year={year}"
        meetings = _fetch_openf1_json(meetings_url)
        if not meetings:
            return None
        target_meeting = None
        for m in meetings:
            if m.get('meeting_name', '').lower() in race_name.lower() or race_name.lower() in m.get('meeting_name', '').lower():
                target_meeting = m
                break
        if not target_meeting:
            for m in meetings:
                if m.get('country_name', '').lower() in race_name.lower() or m.get('location', '').lower() in race_name.lower():
                    target_meeting = m
                    break
        if not target_meeting:
            return None
        meeting_key = target_meeting['meeting_key']
        session_url = f"https://api.openf1.org/v1/sessions?meeting_key={meeting_key}&session_type=Race"
        sessions = _fetch_openf1_json(session_url)
        if not sessions or (isinstance(sessions, dict) and 'detail' in sessions):
            return None
        target_session = sessions[0]
        session_key = target_session['session_key']
        res_url = f"https://api.openf1.org/v1/session_result?session_key={session_key}&position<=10"
        res_data = _fetch_openf1_json(res_url)
        if isinstance(res_data, dict) and 'detail' in res_data:
            return None
        if not res_data:
            return None
        sorted_results = sorted(res_data, key=lambda x: x['position'])
        drivers_url = f"https://api.openf1.org/v1/drivers?meeting_key={meeting_key}"
        drivers_data = _fetch_openf1_json(drivers_url)
        driver_map = {}
        if isinstance(drivers_data, list):
            for d in drivers_data:
                d_num = str(d.get('driver_number', ''))
                if d_num not in driver_map or d.get('broadcast_name') or d.get('full_name'):
                    driver_map[d_num] = d
        results = []
        for res in sorted_results[:10]:
            driver_id = str(res['driver_number'])
            driver_info = driver_map.get(driver_id, {})
            b_name = driver_info.get("broadcast_name") or driver_info.get("full_name") or str(driver_id)
            results.append({
                "BroadcastName": b_name,
                "FirstName": driver_info.get("first_name") or "",
                "LastName": driver_info.get("last_name") or "",
                "Abbreviation": driver_info.get("name_acronym") or ""
            })
        return results
    except Exception:
        return None

# ─────────────────────────────────────────────
#  Shared UI helpers
# ─────────────────────────────────────────────

TITLE = "Points Are Bad 🏎"
SUBTITLE = "F1 Prediction Game"

CSS = """
/* ── Global ────────────────────────────── */
Screen {
    background: $surface;
}

/* ── Menu list ──────────────────────────── */
#menu-list {
    width: 60;
    height: auto;
    border: round $primary;
    padding: 1 2;
    margin: 1 0;
    background: $panel;
}

#menu-list ListItem {
    padding: 0 1;
    margin: 0;
}

#menu-list ListItem:hover {
    background: $primary 30%;
}

#menu-list ListItem.--highlight {
    background: $primary 60%;
    color: $text;
}

/* ── Screen titles ──────────────────────── */
.screen-title {
    text-style: bold;
    color: $primary;
    text-align: center;
    padding: 1 0;
    width: 100%;
}

.subtitle {
    color: $text-muted;
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}

/* ── Cards / panels ─────────────────────── */
.card {
    border: round $accent;
    padding: 1 2;
    margin: 1 2;
    background: $panel;
    height: auto;
}

/* ── Buttons ─────────────────────────────── */
.btn-row {
    height: 3;
    align: center middle;
    margin-top: 1;
}

Button {
    margin: 0 1;
}

Button.primary-btn {
    background: $primary;
}

Button.danger-btn {
    background: $error;
}

/* ── Inputs ──────────────────────────────── */
Input {
    margin: 0 0 1 0;
}

.field-label {
    color: $text-muted;
    margin-bottom: 0;
    padding: 0;
}

/* ── Data table ─────────────────────────── */
DataTable {
    height: 1fr;
    margin: 0 2;
}

/* ── TextArea for paste ─────────────────── */
#paste-area {
    height: 16;
    margin: 0 2 1 2;
    border: round $accent;
}

/* ── Loading overlay ─────────────────────── */
LoadingIndicator {
    height: 100%;
    background: $panel 70%;
}

/* ── Status bar inside screens ───────────── */
.status-bar {
    color: $success;
    text-align: center;
    height: 1;
    margin-top: 1;
}

.error-bar {
    color: $error;
    text-align: center;
    height: 1;
    margin-top: 1;
}

/* ── Standings ───────────────────────────── */
.trophy {
    text-align: center;
    color: $warning;
    text-style: bold;
    margin-bottom: 1;
}

/* ── Modal confirm ──────────────────────── */
ConfirmModal {
    align: center middle;
}

#confirm-box {
    width: 60;
    height: auto;
    border: round $warning;
    padding: 2 4;
    background: $panel;
}

#confirm-msg {
    text-align: center;
    margin-bottom: 2;
    color: $text;
}

.confirm-buttons {
    align: center middle;
    height: 3;
}

/* ── Race detail breakdown ──────────────── */
.breakdown-header {
    text-style: bold;
    color: $accent;
    margin-top: 1;
    padding: 0 2;
}

.correct-row {
    color: $success;
    padding: 0 4;
}

.wrong-row {
    color: $error;
    padding: 0 4;
}
"""


# ─────────────────────────────────────────────
#  Confirm Modal
# ─────────────────────────────────────────────

class ConfirmModal(ModalScreen):
    """A yes/no confirmation dialog."""

    BINDINGS = [Binding("escape", "dismiss(False)", "Cancel")]

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self.message, id="confirm-msg")
            with Horizontal(classes="confirm-buttons"):
                yield Button("Yes", id="yes-btn", variant="success")
                yield Button("No", id="no-btn", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes-btn")


# ─────────────────────────────────────────────
#  Main Menu
# ─────────────────────────────────────────────

MENU_ITEMS = [
    ("👤  Manage Players",         "players"),
    ("🏁  Manage Races",            "races"),
    ("🔮  Enter Predictions",       "predict"),
    ("📋  Enter Actual Results",    "results"),
    ("📊  View Race Points",        "view_race"),
    ("🏆  Season Standings",        "standings"),
    ("🚪  Exit",                    "exit"),
]

class MainMenuScreen(Screen):
    BINDINGS = [Binding("q", "quit_app", "Quit")]

    CSS = """
    MainMenuScreen {
        align: center middle;
    }

    #main-card {
        width: 64;
        height: auto;
        border: double $primary;
        padding: 1 3 2 3;
        background: $panel;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-card"):
            yield Label(TITLE, classes="screen-title")
            yield Label(SUBTITLE, classes="subtitle")
            yield ListView(
                *[ListItem(Label(name), id=f"menu-{key}") for name, key in MENU_ITEMS],
                id="menu-list",
            )
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        key = item_id.replace("menu-", "")
        dispatch = {
            "players":   lambda: self.app.push_screen(ManagePlayersScreen()),
            "races":     lambda: self.app.push_screen(ManageRacesScreen()),
            "predict":   lambda: self.app.push_screen(EnterPredictionsScreen()),
            "results":   lambda: self.app.push_screen(EnterResultsScreen()),
            "view_race": lambda: self.app.push_screen(ViewRacePointsScreen()),
            "standings": lambda: self.app.push_screen(StandingsScreen()),
            "exit":      lambda: self.app.action_quit_app(),
        }
        if key in dispatch:
            dispatch[key]()

    def action_quit_app(self) -> None:
        save_data(self.app.data)
        self.app.exit()


# ─────────────────────────────────────────────
#  Manage Players
# ─────────────────────────────────────────────

class ManagePlayersScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("👤  Manage Players", classes="screen-title")
            yield Static("", id="player-status", classes="status-bar")
            with Vertical(classes="card"):
                yield Label("Current Players:", classes="field-label")
                yield ListView(id="player-list")
            with Vertical(classes="card"):
                yield Label("Player Name", classes="field-label")
                yield Input(placeholder="e.g. Alice", id="player-name-input")
                with Horizontal(classes="btn-row"):
                    yield Button("➕ Add", id="add-player-btn", classes="primary-btn")
                    yield Button("🗑 Remove Selected", id="remove-player-btn", classes="danger-btn")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        lv = self.query_one("#player-list", ListView)
        lv.clear()
        for p in self.app.data["players"]:
            lv.append(ListItem(Label(p), id=f"player-{p}"))

    def _set_status(self, msg: str, error: bool = False) -> None:
        bar = self.query_one("#player-status", Static)
        bar.update(msg)
        bar.remove_class("status-bar", "error-bar")
        bar.add_class("error-bar" if error else "status-bar")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-player-btn":
            inp = self.query_one("#player-name-input", Input)
            name = inp.value.strip()
            if not name:
                self._set_status("Please enter a name.", error=True)
            elif name in self.app.data["players"]:
                self._set_status(f"'{name}' already exists.", error=True)
            else:
                self.app.data["players"].append(name)
                save_data(self.app.data)
                inp.value = ""
                self._refresh_list()
                self._set_status(f"✅  Player '{name}' added.")
        elif event.button.id == "remove-player-btn":
            lv = self.query_one("#player-list", ListView)
            if lv.highlighted_child is None:
                self._set_status("Select a player first.", error=True)
                return
            item_id = lv.highlighted_child.id or ""
            name = item_id.replace("player-", "", 1)
            def _confirm(ok):
                if ok:
                    self.app.data["players"].remove(name)
                    save_data(self.app.data)
                    self._refresh_list()
                    self._set_status(f"🗑  Player '{name}' removed.")
            self.app.push_screen(ConfirmModal(f"Remove player '{name}'?"), _confirm)

    def action_pop_screen(self) -> None:
        self.app.pop_screen()


# ─────────────────────────────────────────────
#  Manage Races
# ─────────────────────────────────────────────

class ManageRacesScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("🏁  Manage Races", classes="screen-title")
            yield Static("", id="race-status", classes="status-bar")
            with Vertical(classes="card"):
                yield Label("Current Races:", classes="field-label")
                yield ListView(id="race-list")
            with Vertical(classes="card"):
                yield Label("Race Name (e.g. Bahrain Grand Prix)", classes="field-label")
                yield Input(placeholder="Race name", id="race-name-input")
                yield Label("Date (YYYY-MM-DD, optional)", classes="field-label")
                yield Input(placeholder="2025-03-02", id="race-date-input")
                with Horizontal(classes="btn-row"):
                    yield Button("➕ Add Race", id="add-race-btn", classes="primary-btn")
                    yield Button("🗑 Remove Selected", id="remove-race-btn", classes="danger-btn")
                    if HAS_FASTF1:
                        yield Button("📅 Auto-populate Schedule", id="auto-populate-btn")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        lv = self.query_one("#race-list", ListView)
        lv.clear()
        for r in self.app.data["races"]:
            date = r.get("date") or "No date"
            has_results = "✅" if r.get("actual_results") else "⏳"
            lv.append(ListItem(
                Label(f"{has_results} {r['name']}  [{date}]"),
                id=f"race-{r['name']}"
            ))

    def _set_status(self, msg: str, error: bool = False) -> None:
        bar = self.query_one("#race-status", Static)
        bar.update(msg)
        bar.remove_class("status-bar", "error-bar")
        bar.add_class("error-bar" if error else "status-bar")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-race-btn":
            name = self.query_one("#race-name-input", Input).value.strip()
            date = self.query_one("#race-date-input", Input).value.strip()
            if not name:
                self._set_status("Enter a race name.", error=True)
                return
            if any(r['name'].lower() == name.lower() for r in self.app.data["races"]):
                self._set_status(f"'{name}' already exists.", error=True)
                return
            self.app.data["races"].append({
                "name": name, "date": date,
                "actual_results": [], "predictions": {}
            })
            save_data(self.app.data)
            self.query_one("#race-name-input", Input).value = ""
            self.query_one("#race-date-input", Input).value = ""
            self._refresh_list()
            self._set_status(f"✅  Race '{name}' added.")
        elif event.button.id == "remove-race-btn":
            lv = self.query_one("#race-list", ListView)
            if lv.highlighted_child is None:
                self._set_status("Select a race first.", error=True)
                return
            item_id = lv.highlighted_child.id or ""
            name = item_id.replace("race-", "", 1)
            def _confirm(ok):
                if ok:
                    self.app.data["races"] = [r for r in self.app.data["races"] if r['name'] != name]
                    save_data(self.app.data)
                    self._refresh_list()
                    self._set_status(f"🗑  Race '{name}' removed.")
            self.app.push_screen(ConfirmModal(f"Remove race '{name}'?"), _confirm)
        elif event.button.id == "auto-populate-btn":
            self._auto_populate()

    @work(thread=True)
    def _auto_populate(self) -> None:
        self.app.call_from_thread(self._set_status, "⏳ Fetching F1 schedule…")
        year = datetime.datetime.now().year
        try:
            cache_dir = os.path.abspath('fastf1_cache')
            os.makedirs(cache_dir, exist_ok=True)
            fastf1.Cache.enable_cache(cache_dir)
            schedule = fastf1.get_event_schedule(year)
            races = schedule[schedule['EventFormat'] != 'testing']
            added_count = 0
            for _, row in races.iterrows():
                race_name = row.get('EventName')
                event_date = row.get('EventDate')
                date_str = str(event_date.date()) if hasattr(event_date, 'date') else ""
                existing_race = next((r for r in self.app.data["races"] if r['name'].lower() == race_name.lower()), None)
                if existing_race:
                    if not existing_race.get('date') and date_str:
                        existing_race['date'] = date_str
                        added_count += 1
                elif race_name:
                    self.app.data["races"].append({
                        "name": race_name, "date": date_str,
                        "actual_results": [], "predictions": {}
                    })
                    added_count += 1
            if added_count > 0:
                save_data(self.app.data)
            self.app.call_from_thread(self._refresh_list)
            msg = f"✅  {added_count} race(s) updated." if added_count else "Schedule already up to date."
            self.app.call_from_thread(self._set_status, msg)
        except Exception as e:
            self.app.call_from_thread(self._set_status, f"Error: {e}", True)

    def action_pop_screen(self) -> None:
        self.app.pop_screen()


# ─────────────────────────────────────────────
#  Enter Predictions
# ─────────────────────────────────────────────

class EnterPredictionsScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected_race = None
        self._selected_player = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("🔮  Enter Predictions", classes="screen-title")
            yield Static("", id="pred-status", classes="status-bar")

            with Vertical(classes="card"):
                yield Label("Select Race:", classes="field-label")
                yield ListView(id="race-picker")

            with Vertical(classes="card"):
                yield Label("Select Player:", classes="field-label")
                yield ListView(id="player-picker")

            with Vertical(classes="card"):
                yield Label("Paste or type Top 10 drivers (one per line):", classes="field-label")
                yield TextArea(id="paste-area")
                with Horizontal(classes="btn-row"):
                    yield Button("💾 Save Prediction", id="save-pred-btn", classes="primary-btn")
        yield Footer()

    def on_mount(self) -> None:
        today = datetime.datetime.now().date().isoformat()
        upcoming = [
            r for r in self.app.data["races"]
            if not r.get("actual_results") and (not r.get("date") or r["date"] >= today)
        ]
        upcoming.sort(key=lambda x: x.get("date", "9999-12-31"))

        race_lv = self.query_one("#race-picker", ListView)
        for r in upcoming:
            tag = " [NEXT]" if r == upcoming[0] else ""
            date = r.get("date") or "?"
            race_lv.append(ListItem(Label(f"🏁 {r['name']}  ({date}){tag}"), id=f"pr-{r['name']}"))

        player_lv = self.query_one("#player-picker", ListView)
        for p in self.app.data["players"]:
            player_lv.append(ListItem(Label(f"👤 {p}"), id=f"pp-{p}"))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id == "race-picker" and event.item:
            name = (event.item.id or "").replace("pr-", "", 1)
            self._selected_race = next((r for r in self.app.data["races"] if r['name'] == name), None)
        elif event.list_view.id == "player-picker" and event.item:
            self._selected_player = (event.item.id or "").replace("pp-", "", 1)

    def _set_status(self, msg: str, error: bool = False) -> None:
        bar = self.query_one("#pred-status", Static)
        bar.update(msg)
        bar.remove_class("status-bar", "error-bar")
        bar.add_class("error-bar" if error else "status-bar")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save-pred-btn":
            return
        if not self._selected_race:
            self._set_status("Select a race first.", error=True)
            return
        if not self._selected_player:
            self._set_status("Select a player first.", error=True)
            return
        raw = self.query_one("#paste-area", TextArea).text
        parsed = parse_raw_input_lines(raw.splitlines(), 10)
        if not parsed:
            self._set_status("Enter at least one driver name.", error=True)
            return

        race = self._selected_race
        player = self._selected_player

        def _do_save():
            race["predictions"][player] = parsed
            save_data(self.app.data)
            self._set_status(f"✅  Saved {len(parsed)} predictions for {player} at {race['name']}.")
            self.query_one("#paste-area", TextArea).clear()

        if player in race.get("predictions", {}):
            def _confirm(ok):
                if ok:
                    _do_save()
            self.app.push_screen(
                ConfirmModal(f"Overwrite existing prediction for {player}?"), _confirm
            )
        else:
            _do_save()

    def action_pop_screen(self) -> None:
        self.app.pop_screen()


# ─────────────────────────────────────────────
#  Enter Results
# ─────────────────────────────────────────────

class EnterResultsScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected_race = None
        self._loading = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("📋  Enter Actual Race Results", classes="screen-title")
            yield Static("", id="result-status", classes="status-bar")

            with Vertical(classes="card"):
                yield Label("Select a Completed Race:", classes="field-label")
                yield ListView(id="result-race-picker")

            with Vertical(classes="card"):
                yield Label("Year (for API fetch):", classes="field-label")
                year_val = str(datetime.datetime.now().year)
                yield Input(value=year_val, placeholder="2025", id="year-input")
                with Horizontal(classes="btn-row"):
                    yield Button("🌐 Fetch from F1 APIs", id="fetch-btn")
                    yield Button("✏️  Manual Entry", id="manual-btn")

            with Vertical(classes="card", id="manual-card"):
                yield Label("Paste or type Top 10 results (one per line):", classes="field-label")
                yield TextArea(id="results-area")
                with Horizontal(classes="btn-row"):
                    yield Button("💾 Save Results", id="save-results-btn", classes="primary-btn")
        yield Footer()

    def on_mount(self) -> None:
        today = datetime.datetime.now().date().isoformat()
        past = [r for r in self.app.data["races"] if r.get("date") and r["date"] <= today]
        past.sort(key=lambda x: x.get("date", "0000-00-00"))
        lv = self.query_one("#result-race-picker", ListView)
        for r in past:
            tag = "✅ " if r.get("actual_results") else "⏳ "
            lv.append(ListItem(Label(f"{tag}{r['name']}  ({r.get('date','?')})"), id=f"rr-{r['name']}"))
        # Hide manual card initially
        self.query_one("#manual-card").display = False

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id == "result-race-picker" and event.item:
            name = (event.item.id or "").replace("rr-", "", 1)
            self._selected_race = next((r for r in self.app.data["races"] if r['name'] == name), None)

    def _set_status(self, msg: str, error: bool = False) -> None:
        bar = self.query_one("#result-status", Static)
        bar.update(msg)
        bar.remove_class("status-bar", "error-bar")
        bar.add_class("error-bar" if error else "status-bar")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "manual-btn":
            self.query_one("#manual-card").display = True
            self._set_status("Enter results manually below.")
        elif event.button.id == "fetch-btn":
            if not self._selected_race:
                self._set_status("Select a race first.", error=True)
                return
            year_str = self.query_one("#year-input", Input).value.strip()
            try:
                year = int(year_str)
            except ValueError:
                self._set_status("Invalid year.", error=True)
                return
            self._fetch_results(year)
        elif event.button.id == "save-results-btn":
            if not self._selected_race:
                self._set_status("Select a race first.", error=True)
                return
            raw = self.query_one("#results-area", TextArea).text
            parsed = parse_raw_input_lines(raw.splitlines(), 10)
            if not parsed:
                self._set_status("Enter at least one result.", error=True)
                return
            def _do_save():
                self._selected_race["actual_results"] = parsed
                save_data(self.app.data)
                self._set_status(f"✅  Results saved for {self._selected_race['name']}.")
            race = self._selected_race
            if race.get("actual_results"):
                self.app.push_screen(
                    ConfirmModal(f"Overwrite existing results for {race['name']}?"),
                    lambda ok: _do_save() if ok else None
                )
            else:
                _do_save()

    @work(thread=True)
    def _fetch_results(self, year: int) -> None:
        race = self._selected_race
        self.app.call_from_thread(self._set_status, f"⏳ Fetching results for {race['name']} ({year})…")
        fetched = fetch_fastf1_results(year, race['name']) if HAS_FASTF1 else None
        if not fetched:
            fetched = fetch_openf1_results(year, race['name'])
        if not fetched:
            self.app.call_from_thread(self._set_status, "Could not fetch results. Try manual entry.", error=True)
            def _show_manual():
                self.query_one("#manual-card").display = True
            self.app.call_from_thread(_show_manual)
            return
        preview = "\n".join(
            f"{i+1}. {d.get('BroadcastName', str(d))}" for i, d in enumerate(fetched)
        )
        def _show_confirm():
            def _confirm(ok):
                if ok:
                    race["actual_results"] = fetched
                    save_data(self.app.data)
                    self._set_status(f"✅  Results saved for {race['name']}.")
            self.app.push_screen(
                ConfirmModal(f"Save these results?\n\n{preview}"), _confirm
            )
        self.app.call_from_thread(_show_confirm)

    def action_pop_screen(self) -> None:
        self.app.pop_screen()


# ─────────────────────────────────────────────
#  View Race Points
# ─────────────────────────────────────────────

class ViewRacePointsScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected_race = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label("📊  View Race Points", classes="screen-title")
            with Horizontal():
                with Vertical(id="race-selector-panel"):
                    yield Label("Select Race:", classes="field-label")
                    yield ListView(id="points-race-picker")
                with VerticalScroll(id="points-detail-panel"):
                    yield Static("← Select a race to view points", id="points-content")
        yield Footer()

    CSS = """
    ViewRacePointsScreen > Vertical {
        height: 100%;
    }
    ViewRacePointsScreen Horizontal {
        height: 1fr;
    }
    #race-selector-panel {
        width: 40;
        border-right: solid $accent;
        padding: 0 1;
    }
    #race-selector-panel ListView {
        height: 1fr;
    }
    #points-detail-panel {
        width: 1fr;
        padding: 1 2;
    }
    """

    def on_mount(self) -> None:
        today = datetime.datetime.now().date().isoformat()
        sorted_races = sorted(self.app.data["races"], key=lambda x: x.get("date", "9999-12-31"))
        lv = self.query_one("#points-race-picker", ListView)
        for r in sorted_races:
            has = "✅" if r.get("actual_results") else "⏳"
            lv.append(ListItem(Label(f"{has} {r['name']}"), id=f"vr-{r['name']}"))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id == "points-race-picker" and event.item:
            name = (event.item.id or "").replace("vr-", "", 1)
            race = next((r for r in self.app.data["races"] if r['name'] == name), None)
            if race:
                self._selected_race = race
                self._render_points(race)

    def _render_points(self, race: dict) -> None:
        content_widget = self.query_one("#points-content", Static)
        actual = race.get("actual_results", [])

        if not actual:
            content_widget.update(f"[yellow]No results yet for {race['name']}.[/]")
            return

        lines = [f"[bold white]{race['name']}[/]\n"]

        # Summary scores
        lines.append("[bold cyan]Scores  (lower = better)[/]")
        if not race.get("predictions"):
            lines.append("  [dim]No predictions made.[/]")
        else:
            scores = []
            for player, pred in race["predictions"].items():
                pts = calculate_player_points_for_race(pred, actual)
                scores.append((player, pts))
            scores.sort(key=lambda x: x[1])
            for i, (player, pts) in enumerate(scores):
                icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "  "
                lines.append(f"  {icon} [bold]{player}[/]: [green]{pts}[/] pts")

        # Breakdown
        lines.append("\n[bold cyan]Detailed Breakdown[/]")
        for player, pred in race.get("predictions", {}).items():
            lines.append(f"\n[bold yellow]{player}[/]")
            for i in range(10):
                p = pred[i] if i < len(pred) else "(none)"
                if i < len(actual):
                    act_val = actual[i]
                    act = act_val.get("BroadcastName", str(act_val)) if isinstance(act_val, dict) else str(act_val)
                else:
                    act = "(none)"
                correct = calculate_str_equality(p, actual[i] if i < len(actual) else "(none)")
                if correct:
                    lines.append(f"  [green]P{i+1}: {act} ✓[/]")
                else:
                    lines.append(f"  [red]P{i+1}: predicted [bold]{p}[/], actual [bold]{act}[/] +1[/]")

        content_widget.update("\n".join(lines))

    def action_pop_screen(self) -> None:
        self.app.pop_screen()


# ─────────────────────────────────────────────
#  Season Standings
# ─────────────────────────────────────────────

class StandingsScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("🏆  Season Standings", classes="screen-title")
            yield Label("Lower points = better!", classes="subtitle")
            yield DataTable(id="standings-table")
            yield Static("", id="standings-note", classes="subtitle")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#standings-table", DataTable)
        table.add_columns("Pos", "Player", "Points", "Races With Pred")

        data = self.app.data
        player_scores = {p: 0 for p in data["players"]}
        player_races = {p: 0 for p in data["players"]}
        races_counted = 0

        for race in data["races"]:
            actual = race.get("actual_results")
            if actual:
                races_counted += 1
                for player, prediction in race["predictions"].items():
                    if player in player_scores:
                        pts = calculate_player_points_for_race(prediction, actual)
                        player_scores[player] += pts
                        player_races[player] += 1
                for player in data["players"]:
                    if player not in race["predictions"]:
                        player_scores[player] += 10  # Penalty

        sorted_players = sorted(player_scores.items(), key=lambda x: x[1])

        medals = ["🥇", "🥈", "🥉"]
        for i, (player, score) in enumerate(sorted_players):
            pos = medals[i] if i < 3 else str(i + 1)
            style = "bold green" if i == 0 else ""
            table.add_row(pos, player, str(score), str(player_races.get(player, 0)), key=player)

        note = self.query_one("#standings-note", Static)
        note.update(f"📈 {races_counted} race(s) with results counted.  Missing prediction = +10 pts penalty.")

    def action_pop_screen(self) -> None:
        self.app.pop_screen()


# ─────────────────────────────────────────────
#  Auto-update loading screen (startup)
# ─────────────────────────────────────────────

class AutoUpdateScreen(Screen):
    """Shows briefly while checking past races for missing results."""

    def compose(self) -> ComposeResult:
        with Center():
            yield LoadingIndicator()
            yield Label("⏳  Checking for missing race results…", classes="screen-title")

    def on_mount(self) -> None:
        self._do_update()

    @work(thread=True)
    def _do_update(self) -> None:
        data = self.app.data
        today = datetime.datetime.now().date().isoformat()
        updated = False
        for race in data["races"]:
            r_date = race.get("date")
            if r_date and r_date <= today and not race["actual_results"]:
                year = int(r_date[:4])
                fetched = fetch_fastf1_results(year, race['name']) if HAS_FASTF1 else None
                if not fetched:
                    fetched = fetch_openf1_results(year, race['name'])
                if fetched:
                    race["actual_results"] = fetched
                    updated = True
        if updated:
            save_data(data)
        self.app.call_from_thread(self._go_to_menu)

    def _go_to_menu(self) -> None:
        self.app.switch_screen(MainMenuScreen())


# ─────────────────────────────────────────────
#  App entry point
# ─────────────────────────────────────────────

class PointsAreBadApp(App):
    CSS = CSS
    TITLE = TITLE
    SUB_TITLE = SUBTITLE
    BINDINGS = [Binding("q", "quit_app", "Quit", show=True)]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = load_data()

    def on_mount(self) -> None:
        self.push_screen(AutoUpdateScreen())

    def action_quit_app(self) -> None:
        save_data(self.data)
        self.exit()


def main_menu():
    app = PointsAreBadApp()
    app.run()


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        sys.exit(0)
