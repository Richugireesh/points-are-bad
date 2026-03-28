"""Textual TUI for Points are Bad - F1 Prediction Game."""

from __future__ import annotations

import datetime

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    ContentSwitcher,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Rule,
    Static,
)

from .api import HAS_FASTF1, fetch_results, get_schedule_updates
from .drivers import ROSTER
from .scoring import (
    calculate_player_points_for_race,
    calculate_season_standings,
    score_position,
)
from .storage import load_data, save_data


# ---------------------------------------------------------------------------
# Theme / helpers
# ---------------------------------------------------------------------------

TEAM_COLORS: dict[str, str] = {
    "McLaren":      "#FF8000",
    "Ferrari":      "#E8002D",
    "Mercedes":     "#27F4D2",
    "Red Bull":     "#3671C6",
    "Racing Bulls": "#6692FF",
    "Aston Martin": "#229971",
    "Williams":     "#64C4FF",
    "Alpine":       "#FF87BC",
    "Haas":         "#B6BABD",
    "Audi":         "#C9C9C9",
    "Cadillac":     "#FFFFFF",
}

APP_CSS = """
Screen {
    background: #0d0d1a;
}

Header {
    background: #e10600;
    color: white;
}

Footer {
    background: #13131f;
}

/* ── Sidebar ── */
.sidebar {
    width: 22;
    background: #13131f;
    border-right: tall #e10600;
    padding: 1 0;
}

.sidebar-brand {
    padding: 0 2 1 2;
    color: #e10600;
    text-style: bold;
    border-bottom: solid #2a2a3e;
    margin-bottom: 1;
}

.nav-btn {
    width: 100%;
    height: 3;
    background: transparent;
    color: #777777;
    border: none;
    text-align: left;
    padding-left: 3;
    margin: 0;
}

.nav-btn:hover {
    background: #1a1a2e;
    color: #dddddd;
}

.nav-btn.-active {
    background: #1a1a2e;
    color: #e10600;
    border-left: outer #e10600;
}

.nav-sep {
    height: 1;
    margin: 0 2;
    color: #2a2a3e;
}

/* ── Content area ── */
.content-pane {
    background: #0d0d1a;
    padding: 1 2;
}

.view-title {
    color: #e10600;
    text-style: bold;
    padding: 0 0 0 0;
}

.view-sub {
    color: #666666;
    padding: 0 0 1 0;
}

.card {
    background: #1a1a2e;
    border: round #2a2a3e;
    padding: 1 2;
    margin: 0 0 1 0;
    height: auto;
}

.card-title {
    color: #00d2be;
    text-style: bold;
}

/* ── DataTable ── */
DataTable {
    background: #1a1a2e;
}

DataTable > .datatable--header {
    background: #13131f;
    color: #e10600;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #2a2a5e;
    color: white;
}

DataTable > .datatable--even-row {
    background: #1a1a2e;
}

DataTable > .datatable--odd-row {
    background: #161628;
}

/* ── Buttons ── */
Button {
    background: #e10600;
    color: white;
    border: none;
    margin: 0 1;
    min-width: 14;
}

Button:hover {
    background: #ff3320;
}

Button.secondary {
    background: #2a2a4e;
    color: #cccccc;
}

Button.secondary:hover {
    background: #3a3a6e;
}

Button.danger {
    background: #6b0000;
    color: #ffaaaa;
}

/* ── Driver picker ── */
.picker-layout {
    height: 1fr;
}

.driver-list-panel {
    width: 1fr;
    background: #13131f;
    border-right: solid #2a2a3e;
    padding: 1;
}

.picks-panel {
    width: 30;
    background: #1a1a2e;
    padding: 1;
}

.panel-label {
    color: #e10600;
    text-style: bold;
    margin-bottom: 1;
}

/* ── Modals ── */
ModalScreen {
    align: center middle;
    background: rgba(0,0,0,0.6);
}

.modal-box {
    background: #1a1a2e;
    border: round #e10600;
    padding: 2 4;
    min-width: 50;
    max-width: 70;
    height: auto;
}

.modal-title {
    color: #e10600;
    text-style: bold;
    margin-bottom: 1;
}

.modal-body {
    color: #cccccc;
    margin-bottom: 1;
}

.modal-buttons {
    height: 3;
    align: right middle;
    margin-top: 1;
}

/* ── Input ── */
Input {
    background: #1a1a2e;
    border: solid #2a2a4e;
    color: #e0e0e0;
}

Input:focus {
    border: solid #e10600;
}

/* ── ListView ── */
ListView {
    background: #13131f;
    border: none;
    padding: 0;
}

ListItem {
    background: #13131f;
    padding: 0 1;
}

ListItem:hover {
    background: #1e1e30;
}

ListItem.-highlight {
    background: #2a2a5e;
}

.list-selected-marker {
    color: #27ae60;
}

.list-team-sep {
    color: #666666;
    text-style: italic;
    background: #0d0d1a;
    padding: 0 1;
}

/* ── Admin form ── */
.form-label {
    color: #888888;
    height: 1;
    margin-bottom: 0;
}

.action-row {
    height: 3;
    margin-top: 1;
    align: left middle;
}

.status-ok {
    color: #27ae60;
}

.status-miss {
    color: #e74c3c;
}
"""


def _fmt_date(date_str: str) -> str:
    if not date_str:
        return "?"
    try:
        return datetime.date.fromisoformat(date_str).strftime("%b %d")
    except ValueError:
        return date_str


def _act_name(entry) -> str:
    if entry is None:
        return "(none)"
    if isinstance(entry, dict):
        return entry.get("name", str(entry))
    return str(entry)


# ---------------------------------------------------------------------------
# Custom ListItem subclasses (for type-safe data attachment)
# ---------------------------------------------------------------------------

class DriverItem(ListItem):
    """ListItem that carries a ROSTER driver dict."""

    def __init__(self, driver: dict, picked_pos: int | None = None) -> None:
        self.driver = driver
        color = TEAM_COLORS.get(driver["team"], "#aaaaaa")
        if picked_pos:
            label_text = f"  ✓ P{picked_pos:<2}  [{color}]{driver['abbr']}[/]  {driver['name']}"
        else:
            label_text = f"       [{color}]{driver['abbr']}[/]  {driver['name']}"
        super().__init__(Label(label_text))


class TeamSepItem(ListItem):
    """Non-interactive team separator in the driver list."""

    def __init__(self, team: str) -> None:
        color = TEAM_COLORS.get(team, "#888888")
        super().__init__(Label(f"  [{color}]── {team}[/]", classes="list-team-sep"))
        self.disabled = True


class SelectableItem(ListItem):
    """Generic selectable list item carrying a payload."""

    def __init__(self, label: str, payload) -> None:
        self.payload = payload
        super().__init__(Label(label))


# ---------------------------------------------------------------------------
# Modal screens
# ---------------------------------------------------------------------------

class ConfirmModal(ModalScreen[bool]):
    """Simple yes/no confirmation dialog."""

    BINDINGS = [
        Binding("escape", "dismiss_no", "Cancel"),
        Binding("y", "dismiss_yes", "Yes"),
        Binding("n", "dismiss_no", "No"),
    ]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(self._title, classes="modal-title")
            yield Label(self._body, classes="modal-body")
            with Horizontal(classes="modal-buttons"):
                yield Button("Yes", id="yes-btn")
                yield Button("No", id="no-btn", classes="secondary")

    def action_dismiss_yes(self) -> None:
        self.dismiss(True)

    def action_dismiss_no(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#yes-btn")
    def on_yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no-btn")
    def on_no(self) -> None:
        self.dismiss(False)


class InputModal(ModalScreen[str | None]):
    """Single-field text input dialog."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, placeholder: str = "") -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(self._title, classes="modal-title")
            yield Input(placeholder=self._placeholder, id="modal-input")
            with Horizontal(classes="modal-buttons"):
                yield Button("OK", id="ok-btn")
                yield Button("Cancel", id="cancel-btn", classes="secondary")

    def on_mount(self) -> None:
        self.query_one("#modal-input", Input).focus()

    @on(Input.Submitted)
    def on_submitted(self) -> None:
        self._submit()

    @on(Button.Pressed, "#ok-btn")
    def on_ok(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_btn(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        value = self.query_one("#modal-input", Input).value.strip()
        self.dismiss(value if value else None)


class SelectModal(ModalScreen):
    """Scrollable list selector — dismisses with the chosen payload."""

    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

    def __init__(self, title: str, items: list[tuple[str, object]]) -> None:
        super().__init__()
        self._title = title
        self._items = items  # list of (display_label, payload)

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(self._title, classes="modal-title")
            yield ListView(id="select-list")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="cancel-btn", classes="secondary")

    def on_mount(self) -> None:
        lv = self.query_one("#select-list", ListView)
        for label, payload in self._items:
            lv.append(SelectableItem(label, payload))

    @on(ListView.Selected, "#select-list")
    def on_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, SelectableItem):
            self.dismiss(event.item.payload)

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_btn(self) -> None:
        self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Driver picker screen
# ---------------------------------------------------------------------------

class DriverPickerScreen(Screen[list[str] | None]):
    """Full-screen interactive driver picker."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("f10", "confirm", "Save Picks", show=True),
        Binding("delete,backspace", "undo_last", "Undo Last"),
    ]

    def __init__(self, race_name: str, player: str, existing: list[str] | None = None) -> None:
        super().__init__()
        self.race_name = race_name
        self.player = player
        self.picks: list[dict] = []

        if existing:
            from .drivers import by_key
            for key in existing:
                d = by_key(key)
                if d:
                    self.picks.append(d)

    def compose(self) -> ComposeResult:
        pos = len(self.picks) + 1
        pos_str = f"  Picking P{pos} of 10" if pos <= 10 else "  All 10 selected"
        yield Header()
        with Horizontal(classes="picker-layout"):
            with Vertical(classes="driver-list-panel"):
                yield Label("Drivers  (↑↓ navigate · Enter select · Del undo)", classes="panel-label")
                yield ListView(id="driver-lv")
            with Vertical(classes="picks-panel"):
                yield Label("Your Picks", classes="panel-label")
                yield Static(id="picks-display")
                yield Label("", id="picker-status", classes="view-sub")
                yield Rule()
                yield Button("Save  [F10]", id="save-picks-btn")
                yield Button("Cancel  [Esc]", id="cancel-btn", classes="secondary")
        yield Footer()

    def on_mount(self) -> None:
        sub = f"{self.player}  ·  {self.race_name}"
        self.app.sub_title = sub
        self._rebuild_list()
        self._refresh_picks()

    def _rebuild_list(self) -> None:
        lv = self.query_one("#driver-lv", ListView)
        lv.clear()
        current_team = ""
        for driver in ROSTER:
            if driver["team"] != current_team:
                if current_team:
                    lv.append(TeamSepItem(driver["team"]))
                else:
                    lv.append(TeamSepItem(driver["team"]))
                current_team = driver["team"]
            pick_pos = next((j + 1 for j, p in enumerate(self.picks) if p is driver), None)
            lv.append(DriverItem(driver, pick_pos))

    def _refresh_picks(self) -> None:
        lines = []
        for i in range(10):
            if i < len(self.picks):
                d = self.picks[i]
                color = TEAM_COLORS.get(d["team"], "#aaaaaa")
                lines.append(f"  [bold]P{i+1:>2}[/]  [{color}]{d['abbr']}[/]  {d['name']}")
            else:
                lines.append(f"  [dim]P{i+1:>2}  ─ ─ ─[/]")
        self.query_one("#picks-display", Static).update("\n".join(lines))

        remaining = 10 - len(self.picks)
        if remaining > 0:
            status = f"  {len(self.picks)}/10 picked · {remaining} remaining"
        else:
            status = "  [bold #27ae60]All 10 selected![/]"
        self.query_one("#picker-status", Label).update(status)

    @on(ListView.Selected, "#driver-lv")
    def on_driver_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, DriverItem):
            return
        driver = event.item.driver
        existing_idx = next((j for j, p in enumerate(self.picks) if p is driver), None)
        if existing_idx is not None:
            self.picks.pop(existing_idx)
        elif len(self.picks) < 10:
            self.picks.append(driver)
        self._rebuild_list()
        self._refresh_picks()

    def action_undo_last(self) -> None:
        if self.picks:
            self.picks.pop()
            self._rebuild_list()
            self._refresh_picks()

    def action_confirm(self) -> None:
        if self.picks:
            self.dismiss([d["key"] for d in self.picks])

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save-picks-btn")
    def on_save(self) -> None:
        self.action_confirm()

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_btn(self) -> None:
        self.action_cancel()


# ---------------------------------------------------------------------------
# View widgets (mounted inside ContentSwitcher)
# ---------------------------------------------------------------------------

class DashboardView(VerticalScroll):
    """Season overview: next race + current standings."""

    DEFAULT_CSS = "DashboardView { padding: 1 2; }"

    def compose(self) -> ComposeResult:
        yield Label("Dashboard", classes="view-title")
        yield Static(id="dash-content")

    def on_show(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        scores, races_counted = calculate_season_standings(data)
        sorted_players = sorted(scores.items(), key=lambda x: x[1])

        today = datetime.date.today().isoformat()
        upcoming = [
            r for r in data["races"]
            if not r.get("actual_results") and r.get("date", "9999") >= today
        ]
        upcoming.sort(key=lambda x: x.get("date", "9999-12-31"))
        next_race = upcoming[0] if upcoming else None

        parts: list[str] = []

        # Season context
        done = sum(1 for r in data["races"] if r.get("actual_results"))
        year = datetime.datetime.now().year
        parts.append(
            f"[dim]Season {year}  ·  {len(data['players'])} players"
            f"  ·  {done}/{len(data['races'])} races complete[/]"
        )
        parts.append("")

        # Next race
        if next_race:
            date_str = next_race.get("date", "")
            try:
                date_fmt = datetime.date.fromisoformat(date_str).strftime("%B %d, %Y")
            except ValueError:
                date_fmt = date_str
            parts.append("[bold #00d2be]── Next Race ──────────────────────────[/]")
            parts.append(f"  [bold white]{next_race['name']}[/]")
            parts.append(f"  [dim]{date_fmt}[/]")
            parts.append("")

        # Standings
        medals = {0: "🥇", 1: "🥈", 2: "🥉"}
        parts.append(
            f"[bold #00d2be]── Standings  [dim](after {races_counted} races)[/]"
            f" ─────────────[/]"
        )
        if sorted_players:
            for i, (player, pts) in enumerate(sorted_players):
                medal = medals.get(i, f"  {i+1}.")
                gap = pts - sorted_players[0][1] if i > 0 else 0
                gap_str = f"  [dim]+{gap}[/]" if gap else ""
                parts.append(f"  {medal}  [bold]{player:<14}[/] {pts} pts{gap_str}")
        else:
            parts.append("  [dim]No standings yet.[/]")

        self.query_one("#dash-content", Static).update("\n".join(parts))


class StandingsView(VerticalScroll):
    """Full season standings table."""

    DEFAULT_CSS = "StandingsView { padding: 1 2; }"

    def compose(self) -> ComposeResult:
        yield Label("Season Standings", classes="view-title")
        yield Label("Lowest score wins  ·  missing prediction = +10 pts", classes="view-sub")
        yield DataTable(id="standings-table", zebra_stripes=True)

    def on_show(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        scores, races_counted = calculate_season_standings(data)
        sorted_players = sorted(scores.items(), key=lambda x: x[1])

        table = self.query_one("#standings-table", DataTable)
        table.clear(columns=True)
        table.add_columns("#", "Player", "Points", "Gap to lead")

        medals = {0: "🥇", 1: "🥈", 2: "🥉"}
        lead = sorted_players[0][1] if sorted_players else 0

        for i, (player, pts) in enumerate(sorted_players):
            medal = medals.get(i, str(i + 1))
            gap = f"+{pts - lead}" if i > 0 else "─"
            table.add_row(medal, player, str(pts), gap)

        sub = self.query_one(".view-sub", Label)
        sub.update(
            f"Lowest score wins  ·  after {races_counted} of"
            f" {len(data['races'])} races  ·  missing prediction = +10 pts"
        )


class RacePointsView(VerticalScroll):
    """Pick a race, view per-player scores and breakdown."""

    DEFAULT_CSS = "RacePointsView { padding: 1 2; }"

    def compose(self) -> ComposeResult:
        yield Label("Race Points", classes="view-title")
        yield Label("Select a race to view results", classes="view-sub")
        with Horizontal(classes="action-row"):
            yield Button("Select Race", id="pick-race-btn")
        yield Static(id="race-summary")

    def on_show(self) -> None:
        self.query_one("#race-summary", Static).update("")

    @on(Button.Pressed, "#pick-race-btn")
    def on_pick_race(self) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        races_with_results = [r for r in data["races"] if r.get("actual_results")]
        if not races_with_results:
            self.app.notify("No races have results yet.", severity="warning")
            return

        races_with_results.sort(key=lambda x: x.get("date", "9999-12-31"))
        items = [(_fmt_date(r.get("date", "")) + "  " + r["name"], r) for r in races_with_results]

        def on_race_chosen(race) -> None:
            if race:
                self._show_race(race)

        self.app.push_screen(SelectModal("Select Race", items), on_race_chosen)

    def _show_race(self, race: dict) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        actual = race["actual_results"]
        date_label = _fmt_date(race.get("date", ""))

        parts: list[str] = []

        # Header
        parts.append(f"[bold #e10600]{race['name']}[/]  [dim]{date_label}[/]")
        parts.append("")

        # Score summary
        parts.append("[bold #00d2be]── Scores (lower = better) ──────────────[/]")
        for player in data["players"]:
            if player in race["predictions"]:
                pts = calculate_player_points_for_race(race["predictions"][player], actual)
                bar = "█" * pts + "░" * (10 - pts) if pts <= 10 else "█" * 10
                parts.append(f"  [bold]{player:<14}[/] {pts:>3} pts  [dim]{bar}[/]")
            else:
                parts.append(f"  [bold]{player:<14}[/]  10 pts  [dim #e74c3c](no prediction – penalty)[/]")
        parts.append("")

        # Per-player breakdown
        for player in data["players"]:
            parts.append(f"[bold #00d2be]── {player} ──────────────────────────[/]")

            if player not in race["predictions"]:
                parts.append("  [dim]No prediction submitted — +10 point penalty[/]")
                parts.append("")
                continue

            prediction = race["predictions"][player]
            total = 0
            for i in range(10):
                pred = prediction[i] if i < len(prediction) else None
                act_entry = actual[i] if i < len(actual) else None
                if pred is None and act_entry is None:
                    continue
                act = _act_name(act_entry)
                delta = score_position(pred, act_entry)
                total += delta
                if delta == 0:
                    parts.append(f"  [#27ae60]P{i+1:>2}  ✓  {act}[/]")
                else:
                    pred_str = pred if pred is not None else "(none)"
                    parts.append(
                        f"  [#e74c3c]P{i+1:>2}  ✗  predicted [italic]{pred_str}[/italic]"
                        f"  →  {act}[/]"
                    )
            parts.append(f"  [bold]Total: {total} pts[/]")
            parts.append("")

        self.query_one("#race-summary", Static).update("\n".join(parts))


class PredictionsView(VerticalScroll):
    """Enter a prediction for any upcoming race."""

    DEFAULT_CSS = "PredictionsView { padding: 1 2; }"

    def compose(self) -> ComposeResult:
        yield Label("Enter Predictions", classes="view-title")
        yield Label("", id="pred-sub", classes="view-sub")
        with Horizontal(classes="action-row"):
            yield Button("Select Race", id="pick-race-btn")
            yield Button("Select Player", id="pick-player-btn", classes="secondary")
            yield Button("Pick Drivers  →", id="start-picker-btn")
        yield Static(id="pred-status")
        yield Static(id="pred-preview")

    _selected_race: reactive[dict | None] = reactive(None)
    _selected_player: reactive[str | None] = reactive(None)

    def on_show(self) -> None:
        self._update_status()

    def _update_status(self) -> None:
        race = self._selected_race
        player = self._selected_player
        parts = []
        if race:
            parts.append(f"  Race:    [bold]{race['name']}[/]  [dim]{_fmt_date(race.get('date',''))}[/]")
        else:
            parts.append("  Race:    [dim]not selected[/]")
        if player:
            parts.append(f"  Player:  [bold]{player}[/]")
        else:
            parts.append("  Player:  [dim]not selected[/]")
        self.query_one("#pred-status", Static).update("\n".join(parts))

        # Show existing prediction if both selected
        preview = self.query_one("#pred-preview", Static)
        if race and player and player in race.get("predictions", {}):
            preds = race["predictions"][player]
            lines = ["\n  [dim]Existing prediction:[/]"]
            for i, key in enumerate(preds):
                lines.append(f"  [dim]P{i+1:>2}  {key}[/]")
            preview.update("\n".join(lines))
        else:
            preview.update("")

        sub = self.query_one("#pred-sub", Label)
        if race and player:
            sub.update("Ready — click 'Pick Drivers' to open the picker")
        else:
            sub.update("Select a race and player, then pick drivers")

    @on(Button.Pressed, "#pick-race-btn")
    def on_pick_race(self) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        today = datetime.date.today().isoformat()
        upcoming = [
            r for r in data["races"]
            if not r.get("actual_results") and r.get("date", "9999") >= today
        ]
        upcoming.sort(key=lambda x: x.get("date", "9999-12-31"))
        if not upcoming:
            self.app.notify("No upcoming races without results.", severity="warning")
            return
        items = [(_fmt_date(r.get("date", "")) + "  " + r["name"], r) for r in upcoming]

        def on_race_chosen(race) -> None:
            if race:
                self._selected_race = race
                self._update_status()

        self.app.push_screen(SelectModal("Select Upcoming Race", items), on_race_chosen)

    @on(Button.Pressed, "#pick-player-btn")
    def on_pick_player(self) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        if not data["players"]:
            self.app.notify("No players yet. Add one in Admin.", severity="warning")
            return
        items = [(p, p) for p in data["players"]]

        def on_player_chosen(player) -> None:
            if player:
                self._selected_player = player
                self._update_status()

        self.app.push_screen(SelectModal("Select Player", items), on_player_chosen)

    @on(Button.Pressed, "#start-picker-btn")
    def on_start_picker(self) -> None:
        race = self._selected_race
        player = self._selected_player
        if not race or not player:
            self.app.notify("Select a race and player first.", severity="warning")
            return

        existing = race.get("predictions", {}).get(player)
        if existing:
            def on_confirm(overwrite: bool) -> None:
                if overwrite:
                    self._open_picker(race, player, existing)

            self.app.push_screen(
                ConfirmModal(
                    "Overwrite Prediction?",
                    f"{player} already has a prediction for {race['name']}.",
                ),
                on_confirm,
            )
        else:
            self._open_picker(race, player, None)

    def _open_picker(self, race: dict, player: str, existing: list[str] | None) -> None:
        def on_picker_done(prediction: list[str] | None) -> None:
            if prediction is not None:
                race.setdefault("predictions", {})[player] = prediction
                save_data(self.app.data)  # type: ignore[attr-defined]
                self.app.notify(
                    f"✓ Prediction for {player} saved ({len(prediction)} drivers).",
                    severity="information",
                )
                self._update_status()

        self.app.push_screen(
            DriverPickerScreen(race["name"], player, existing),
            on_picker_done,
        )


class AdminView(VerticalScroll):
    """Admin panel: manage players, races, results."""

    DEFAULT_CSS = "AdminView { padding: 1 2; }"

    def compose(self) -> ComposeResult:
        yield Label("Admin", classes="view-title")
        yield Label("Manage players, races, and results", classes="view-sub")
        yield Rule()

        yield Label("[bold #00d2be]Players[/]", classes="card-title")
        with Horizontal(classes="action-row"):
            yield Button("Add Player", id="add-player-btn")
            yield Button("Remove Player", id="remove-player-btn", classes="secondary")
        yield Static(id="players-list", classes="card")

        yield Rule()

        yield Label("[bold #00d2be]Race Results[/]", classes="card-title")
        with Horizontal(classes="action-row"):
            yield Button("Auto-Fetch Results", id="autofetch-btn")
            yield Button("Manual Entry", id="manual-results-btn", classes="secondary")
        yield Static(id="fetch-status")

        yield Rule()

        yield Label("[bold #00d2be]Schedule[/]", classes="card-title")
        with Horizontal(classes="action-row"):
            yield Button("Sync from FastF1", id="sync-schedule-btn")
            yield Button("Add Race", id="add-race-btn", classes="secondary")
            yield Button("Remove Race", id="remove-race-btn", classes="danger")

    def on_show(self) -> None:
        self._refresh_players()

    def _refresh_players(self) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        players = data["players"]
        if players:
            text = "  " + "  ·  ".join(f"[bold]{p}[/]" for p in players)
        else:
            text = "  [dim]No players yet.[/]"
        self.query_one("#players-list", Static).update(text)

    # ── Player management ─────────────────────────────────────────────────

    @on(Button.Pressed, "#add-player-btn")
    def on_add_player(self) -> None:
        def on_name(name: str | None) -> None:
            if not name:
                return
            data: dict = self.app.data  # type: ignore[attr-defined]
            if name in data["players"]:
                self.app.notify(f"'{name}' already exists.", severity="warning")
            else:
                data["players"].append(name)
                save_data(data)
                self.app.notify(f"✓ Player '{name}' added.")
                self._refresh_players()

        self.app.push_screen(InputModal("Add Player", placeholder="Player name"), on_name)

    @on(Button.Pressed, "#remove-player-btn")
    def on_remove_player(self) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        if not data["players"]:
            self.app.notify("No players to remove.", severity="warning")
            return
        items = [(p, p) for p in data["players"]]

        def on_player(player: str | None) -> None:
            if not player:
                return

            def on_confirm(yes: bool) -> None:
                if yes:
                    d: dict = self.app.data  # type: ignore[attr-defined]
                    d["players"].remove(player)
                    save_data(d)
                    self.app.notify(f"'{player}' removed.")
                    self._refresh_players()

            self.app.push_screen(
                ConfirmModal("Remove Player?", f"Remove '{player}' from the game?"),
                on_confirm,
            )

        self.app.push_screen(SelectModal("Remove Player", items), on_player)

    # ── Results entry ─────────────────────────────────────────────────────

    @on(Button.Pressed, "#autofetch-btn")
    def on_autofetch(self) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        today = datetime.date.today().isoformat()
        past = [r for r in data["races"] if r.get("date") and r["date"] <= today]
        if not past:
            self.app.notify("No past races found.", severity="warning")
            return
        items = [
            (
                _fmt_date(r.get("date", "")) + "  " + r["name"]
                + ("  [results logged]" if r.get("actual_results") else ""),
                r,
            )
            for r in sorted(past, key=lambda x: x.get("date", ""))
        ]

        def on_race(race) -> None:
            if race:
                self._do_autofetch(race)

        self.app.push_screen(SelectModal("Select Race to Fetch", items), on_race)

    @work(thread=True)
    def _do_autofetch(self, race: dict) -> None:
        date_str = race.get("date", "")
        year = int(date_str[:4]) if date_str else datetime.datetime.now().year
        self.call_from_thread(
            self.query_one("#fetch-status", Static).update,
            f"  [dim]Fetching {race['name']} ({year})…[/]",
        )
        results = fetch_results(year, race["name"])
        if results:
            race["actual_results"] = results
            data: dict = self.app.data  # type: ignore[attr-defined]
            save_data(data)
            self.call_from_thread(
                self.query_one("#fetch-status", Static).update,
                f"  [bold #27ae60]✓ Results saved for {race['name']}[/]",
            )
            self.app.call_from_thread(
                self.app.notify,
                f"✓ {race['name']} results fetched.",
                severity="information",
            )
        else:
            self.call_from_thread(
                self.query_one("#fetch-status", Static).update,
                f"  [#e74c3c]Could not fetch results for {race['name']}.[/]",
            )
            self.app.call_from_thread(
                self.app.notify,
                f"Could not fetch {race['name']} — try manual entry.",
                severity="error",
            )

    @on(Button.Pressed, "#manual-results-btn")
    def on_manual_results(self) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        today = datetime.date.today().isoformat()
        past = [r for r in data["races"] if r.get("date") and r["date"] <= today]
        if not past:
            self.app.notify("No past races found.", severity="warning")
            return
        items = [
            (_fmt_date(r.get("date", "")) + "  " + r["name"], r)
            for r in sorted(past, key=lambda x: x.get("date", ""))
        ]

        def on_race(race) -> None:
            if race:
                self.app.push_screen(ManualResultsScreen(race))

        self.app.push_screen(SelectModal("Select Race", items), on_race)

    # ── Schedule ──────────────────────────────────────────────────────────

    @on(Button.Pressed, "#sync-schedule-btn")
    def on_sync_schedule(self) -> None:
        if not HAS_FASTF1:
            self.app.notify("FastF1 not installed.", severity="error")
            return
        self._do_sync_schedule()

    @work(thread=True)
    def _do_sync_schedule(self) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        try:
            new_races, date_updates = get_schedule_updates(data["races"])
            for race, new_date in date_updates:
                race["date"] = new_date
            for race in new_races:
                data["races"].append(race)
            if new_races or date_updates:
                self.call_from_thread(save_data, data)
                msg = f"✓ {len(new_races)} added, {len(date_updates)} dates updated."
            else:
                msg = "Schedule already up to date."
            self.app.call_from_thread(self.app.notify, msg)
        except Exception as e:
            self.app.call_from_thread(
                self.app.notify, f"Schedule sync failed: {e}", severity="error"
            )

    @on(Button.Pressed, "#add-race-btn")
    def on_add_race(self) -> None:
        def on_name(name: str | None) -> None:
            if not name:
                return
            data: dict = self.app.data  # type: ignore[attr-defined]
            if any(r["name"].lower() == name.lower() for r in data["races"]):
                self.app.notify(f"'{name}' already exists.", severity="warning")
                return

            def on_date(date_str: str | None) -> None:
                d: dict = self.app.data  # type: ignore[attr-defined]
                d["races"].append(
                    {"name": name, "date": date_str or "", "actual_results": [], "predictions": {}}
                )
                save_data(d)
                self.app.notify(f"✓ Race '{name}' added.")

            self.app.push_screen(
                InputModal("Race Date (YYYY-MM-DD)", placeholder="2026-06-01 or leave blank"),
                on_date,
            )

        self.app.push_screen(InputModal("Race Name", placeholder="e.g. Monaco Grand Prix"), on_name)

    @on(Button.Pressed, "#remove-race-btn")
    def on_remove_race(self) -> None:
        data: dict = self.app.data  # type: ignore[attr-defined]
        items = [
            (_fmt_date(r.get("date", "")) + "  " + r["name"], r)
            for r in data["races"]
        ]

        def on_race(race) -> None:
            if not race:
                return

            def on_confirm(yes: bool) -> None:
                if yes:
                    d: dict = self.app.data  # type: ignore[attr-defined]
                    d["races"].remove(race)
                    save_data(d)
                    self.app.notify(f"'{race['name']}' removed.")

            self.app.push_screen(
                ConfirmModal("Remove Race?", f"Remove '{race['name']}'? This cannot be undone."),
                on_confirm,
            )

        self.app.push_screen(SelectModal("Remove Race", items), on_race)


# ---------------------------------------------------------------------------
# Manual results entry screen
# ---------------------------------------------------------------------------

class ManualResultsScreen(Screen):
    """Enter top-10 results manually, one driver at a time."""

    BINDINGS = [Binding("escape", "go_back", "Back")]

    def __init__(self, race: dict) -> None:
        super().__init__()
        self.race = race
        self.entries: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(classes="content-pane"):
            yield Label(f"Manual Results — {self.race['name']}", classes="view-title")
            yield Label("Enter P1 → P10, one per line. Press Enter after each.", classes="view-sub")
            yield Static(id="entries-display")
            yield Input(placeholder="Driver name", id="entry-input")
            with Horizontal(classes="action-row"):
                yield Button("Save", id="save-btn")
                yield Button("Clear", id="clear-btn", classes="secondary")
                yield Button("Back", id="back-btn", classes="secondary")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()
        self.query_one("#entry-input", Input).focus()

    def _refresh(self) -> None:
        lines = []
        for i, name in enumerate(self.entries):
            lines.append(f"  P{i+1:>2}  {name}")
        for i in range(len(self.entries), 10):
            lines.append(f"  [dim]P{i+1:>2}  ─[/]")
        self.query_one("#entries-display", Static).update("\n".join(lines))

    @on(Input.Submitted, "#entry-input")
    def on_entry(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        if name and len(self.entries) < 10:
            self.entries.append(name)
            self.query_one("#entry-input", Input).value = ""
            self._refresh()
            if len(self.entries) == 10:
                self.app.notify("All 10 entered — press Save.")

    @on(Button.Pressed, "#save-btn")
    def on_save(self) -> None:
        if not self.entries:
            self.app.notify("No entries yet.", severity="warning")
            return
        self.race["actual_results"] = [
            {"abbr": "", "name": name} for name in self.entries
        ]
        save_data(self.app.data)  # type: ignore[attr-defined]
        self.app.notify(f"✓ Results for {self.race['name']} saved.")
        self.app.pop_screen()

    @on(Button.Pressed, "#clear-btn")
    def on_clear(self) -> None:
        self.entries = []
        self._refresh()

    @on(Button.Pressed, "#back-btn")
    def on_back_btn(self) -> None:
        self.app.pop_screen()

    def action_go_back(self) -> None:
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

class Sidebar(Vertical):
    """Navigation sidebar with active-state highlighting."""

    DEFAULT_CSS = "Sidebar { width: 22; background: #13131f; border-right: tall #e10600; padding: 1 0; }"

    NAV_ITEMS = [
        ("nav-dashboard", "  Dashboard"),
        ("nav-standings", "  Standings"),
        ("nav-race-points", "  Race Points"),
        ("nav-predictions", "  Predictions"),
        None,  # separator
        ("nav-admin", "  Admin"),
    ]

    def compose(self) -> ComposeResult:
        yield Label("  🏎 POINTS ARE BAD", classes="sidebar-brand")
        for item in self.NAV_ITEMS:
            if item is None:
                yield Rule(classes="nav-sep")
            else:
                btn_id, label = item
                btn = Button(label, id=btn_id, classes="nav-btn")
                yield btn

    def set_active(self, view_id: str) -> None:
        for btn in self.query(".nav-btn"):
            btn.remove_class("-active")
        target_id = f"nav-{view_id}"
        try:
            self.query_one(f"#{target_id}", Button).add_class("-active")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

class PointsAreBadApp(App):
    """The Points are Bad TUI application."""

    CSS = APP_CSS
    TITLE = "Points are Bad"
    SUB_TITLE = "F1 Prediction Game"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("1", "switch_view('dashboard')", "Dashboard"),
        Binding("2", "switch_view('standings')", "Standings"),
        Binding("3", "switch_view('race-points')", "Race Points"),
        Binding("4", "switch_view('predictions')", "Predictions"),
        Binding("5", "switch_view('admin')", "Admin"),
    ]

    data: dict = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Sidebar()
            with ContentSwitcher(initial="dashboard", id="switcher"):
                yield DashboardView(id="dashboard")
                yield StandingsView(id="standings")
                yield RacePointsView(id="race-points")
                yield PredictionsView(id="predictions")
                yield AdminView(id="admin")
        yield Footer()

    def on_mount(self) -> None:
        self.data = load_data()
        self.query_one(Sidebar).set_active("dashboard")
        self._refresh_active()

    def _refresh_active(self) -> None:
        view_id = self.query_one(ContentSwitcher).current
        try:
            view = self.query_one(f"#{view_id}")
            if hasattr(view, "refresh_data"):
                view.refresh_data()
        except Exception:
            pass

    @on(Button.Pressed, ".nav-btn")
    def on_nav_pressed(self, event: Button.Pressed) -> None:
        view_id = event.button.id.replace("nav-", "")
        self._switch_to(view_id)
        event.stop()

    def action_switch_view(self, view_id: str) -> None:
        self._switch_to(view_id)

    def _switch_to(self, view_id: str) -> None:
        self.query_one(ContentSwitcher).current = view_id
        self.query_one(Sidebar).set_active(view_id)
        self._refresh_active()

    def action_quit(self) -> None:
        save_data(self.data)
        self.exit()


def run() -> None:
    """Entry point for the TUI app."""
    app = PointsAreBadApp()
    app.run()
