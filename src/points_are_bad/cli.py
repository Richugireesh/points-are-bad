"""CLI presentation layer.

Responsible for: menus, input loops, print/input calls, and orchestrating
calls to api, scoring, and storage modules.  No scoring math or HTTP
requests live here.
"""

from __future__ import annotations

__all__ = ["main_menu"]

import datetime
import os
import re
import sys
from typing import TYPE_CHECKING, TypeVar

from .api import HAS_FASTF1, fetch_results, get_schedule_updates
from .drivers import ROSTER, by_key
from .scoring import calculate_player_points_for_race, calculate_season_standings, score_position
from .storage import load_data, save_data

if TYPE_CHECKING:
    from collections.abc import Callable

    from .models import DriverInfo, DriverResult, GameData, RaceData

_T = TypeVar("_T")

# ---------------------------------------------------------------------------
# Layout constants & helpers
# ---------------------------------------------------------------------------

_W = 50  # usable content width inside the box


def _box_top() -> str:
    return f"╔{'═' * (_W + 2)}╗"


def _box_bot() -> str:
    return f"╚{'═' * (_W + 2)}╝"


def _box_row(text: str) -> str:
    return f"║  {text:<{_W}}║"


def _header(*lines: str) -> None:
    """Print a consistent framed box header."""
    print(_box_top())
    for line in lines:
        print(_box_row(line))
    print(_box_bot())


def _rule(label: str = "") -> None:
    """Print a horizontal section divider with an optional inline label."""
    if label:
        dash_len = max(_W - len(label) - 1, 0)
        print(f"  {label} {'─' * dash_len}")
    else:
        print(f"  {'─' * (_W + 2)}")


def _fmt_date(date_str: str) -> str:
    """'2026-03-16'  ->  'Mar 16'.  Returns 'Unknown' on bad input."""
    if not date_str:
        return "Unknown"
    try:
        return datetime.date.fromisoformat(date_str).strftime("%b %d")
    except ValueError:
        return date_str


def _season_context(data: GameData) -> str:
    n = len(data["players"])
    done = sum(1 for r in data["races"] if r.get("actual_results"))
    total = len(data["races"])
    year = datetime.datetime.now().year
    word = "player" if n == 1 else "players"
    return f"Season {year}  •  {n} {word}  •  {done}/{total} races done"


# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def parse_raw_input_lines(lines: list[str], max_items: int) -> list[str]:
    """Parse a block of pasted or typed lines into a clean list of driver names."""
    text = "\n".join(lines)
    text = text.replace("\u2060", "").replace("\u200b", "")
    cleaned = re.sub(r"\d+\s*[.)]", "|", text)

    parts: list[str] = []
    for chunk in re.split(r"[|\n,]", cleaned):
        chunk = chunk.strip()
        if chunk.startswith("("):
            chunk = chunk[1:].strip()
        if chunk:
            parts.append(chunk)

    return parts[:max_items]


def get_input_list(prompt: str, min_items: int = 10, max_items: int = 10) -> list[str]:
    print(f"\n  {prompt}")
    print("  (Paste a list directly, or type one per line. Empty line to finish.)")

    lines: list[str] = []
    while True:
        try:
            label = f"  {len(lines) + 1:>2}. " if len(lines) < max_items else "  ... "
            line = input(label).strip()
        except EOFError:
            break

        if not line:
            if not lines:
                continue
            parsed = parse_raw_input_lines(lines, max_items)
            if len(parsed) >= min_items:
                break
            confirm = input(f"\n  Only {len(parsed)} items entered. Done? (y/n): ").strip().lower()
            if confirm == "y":
                break
            continue

        lines.append(line)
        parsed = parse_raw_input_lines(lines, max_items)
        if len(parsed) >= max_items:
            break

    return parse_raw_input_lines(lines, max_items)


def select_item(
    items: list[_T],
    item_name: str,
    display_func: Callable[[_T], str] = str,
) -> _T | None:
    """Print a numbered list and return the chosen item, or None on bad input."""
    if not items:
        input(f"\n  No {item_name}s exist. Add one first. Press Enter...")
        return None

    print()
    for i, item in enumerate(items):
        print(f"  [{i + 1}] {display_func(item)}")

    try:
        idx = int(input(f"\n  Select [1-{len(items)}]: ")) - 1
        if not (0 <= idx < len(items)):
            raise ValueError
        return items[idx]
    except ValueError:
        input("  Invalid selection. Press Enter...")
        return None


# ---------------------------------------------------------------------------
# Auto-update on startup
# ---------------------------------------------------------------------------


def auto_update_past_races(data: GameData) -> None:
    today = datetime.datetime.now().date().isoformat()
    # Collect races with past dates and no results yet
    pending = [
        race
        for race in data["races"]
        if race.get("date") and race["date"] <= today and not race["actual_results"]
    ]

    if not pending:
        return

    clear_screen()
    _header("Auto-updating past race results...")
    print()

    for race in pending:
        print(f"  Fetching: {race['name']} ({_fmt_date(race.get('date', ''))}) ...")
    print()

    # Fetch results concurrently — both FastF1 and OpenF1 are I/O bound.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    updated = False
    with ThreadPoolExecutor(max_workers=min(4, len(pending))) as executor:
        future_map = {
            executor.submit(fetch_results, int(r["date"][:4]), r["name"]): r for r in pending
        }
        for future in as_completed(future_map):
            race = future_map[future]
            try:
                fetched = future.result()
            except Exception:
                fetched = None
            if fetched:
                race["actual_results"] = fetched
                updated = True
                print(f"  ✓  {race['name']}")
            else:
                print(f"  -  {race['name']} — not available yet")

    if updated:
        save_data(data)

    input("\n  Press Enter to continue to the Main Menu...")


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------


def main_menu() -> None:
    data = load_data()
    auto_update_past_races(data)

    while True:
        clear_screen()
        _header("Points are Bad  •  F1 Prediction Game", _season_context(data))
        print()
        print("  Play")
        print("    [1]  Enter Predictions")
        print("    [2]  View Race Results & Points")
        print("    [3]  View Season Standings")
        print()
        print("  Admin")
        print("    [4]  Manage Players")
        print("    [5]  Manage Races")
        print("    [6]  Enter Race Results")
        print()
        print("    [7]  Exit")
        print()

        choice = input("  Select [1-7]: ").strip()

        if choice == "1":
            enter_predictions(data)
        elif choice == "2":
            view_race_points(data)
        elif choice == "3":
            view_standings(data)
        elif choice == "4":
            manage_players(data)
        elif choice == "5":
            manage_races(data)
        elif choice == "6":
            enter_results(data)
        elif choice == "7":
            save_data(data)
            print("\n  Scores saved! Goodbye.")
            sys.exit(0)
        else:
            input("  Invalid choice. Press Enter to try again.")


# ---------------------------------------------------------------------------
# Player management
# ---------------------------------------------------------------------------


def manage_players(data: GameData) -> None:
    while True:
        clear_screen()
        _header("Manage Players")
        print()

        if not data["players"]:
            print("  No players added yet.")
        else:
            joined = "  •  ".join(data["players"])
            print(f"  Players ({len(data['players'])}):  {joined}")

        print()
        _rule()
        print("  [1]  Add Player")
        print("  [2]  Remove Player")
        print()
        print("  [3]  Back")
        print()
        choice = input("  Select [1-3]: ").strip()

        if choice == "1":
            name = input("\n  Player name: ").strip()
            if name and name not in data["players"]:
                data["players"].append(name)
                save_data(data)
                print(f"  ✓  '{name}' added.")
            elif name in data["players"]:
                print("  Player already exists.")
            input("  Press Enter to continue...")
        elif choice == "2":
            name = input("\n  Name to remove: ").strip()
            if name in data["players"]:
                data["players"].remove(name)
                save_data(data)
                print(f"  ✓  '{name}' removed.")
            else:
                print("  Player not found.")
            input("  Press Enter to continue...")
        elif choice == "3":
            break


# ---------------------------------------------------------------------------
# Race management
# ---------------------------------------------------------------------------


def manage_races(data: GameData) -> None:
    while True:
        clear_screen()
        _header("Manage Races")
        print()

        if not data["races"]:
            print("  No races added yet.")
        else:
            done = sum(1 for r in data["races"] if r.get("actual_results"))
            print(f"  {len(data['races'])} races scheduled  •  {done} with results")

        print()
        _rule()
        print("  [1]  Add Race")
        print("  [2]  Remove Race")
        print("  [3]  Auto-populate Season Schedule (FastF1)")
        print()
        print("  [4]  Back")
        print()
        choice = input("  Select [1-4]: ").strip()

        if choice == "1":
            name = input("\n  Race name (e.g. 'Bahrain GP'): ").strip()
            if not name:
                input("  Name cannot be empty. Press Enter...")
                continue
            if any(r["name"].lower() == name.lower() for r in data["races"]):
                print("  Race already exists.")
            else:
                date_str = input("  Date (YYYY-MM-DD) or leave blank: ").strip()
                if date_str:
                    try:
                        datetime.datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        input("  Invalid date format — use YYYY-MM-DD. Press Enter...")
                        continue
                data["races"].append(
                    {
                        "name": name,
                        "date": date_str,
                        "actual_results": [],
                        "predictions": {},
                    }
                )
                # Keep races sorted by date (dateless races sort to the end)
                data["races"].sort(key=lambda r: r.get("date") or "9999-12-31")
                save_data(data)
                print(f"  ✓  '{name}' added.")
            input("  Press Enter to continue...")
        elif choice == "2":
            if not data["races"]:
                input("\n  No races to remove. Press Enter...")
                continue
            race = select_item(data["races"], "race to remove", lambda r: r["name"])
            if race:
                confirm = input(f"\n  Remove '{race['name']}'? (y/n): ").strip().lower()
                if confirm == "y":
                    data["races"].remove(race)
                    save_data(data)
                    print(f"  ✓  '{race['name']}' removed.")
                else:
                    print("  Cancelled.")
            input("  Press Enter to continue...")
        elif choice == "3":
            _auto_populate_schedule(data)
        elif choice == "4":
            break


def _auto_populate_schedule(data: GameData) -> None:
    """CLI wrapper: call api.get_schedule_updates, apply changes, save."""
    if not HAS_FASTF1:
        input("\n  FastF1 is not installed. Please install it to use this feature. Press Enter...")
        return

    year = datetime.datetime.now().year
    print(f"\n  Fetching official F1 schedule for {year}...")
    try:
        new_races, date_updates = get_schedule_updates(data["races"])
        change_count = 0

        for race, new_date in date_updates:
            race["date"] = new_date
            change_count += 1
            print(f"  Updated date: {race['name']}  →  {new_date}")

        for race in new_races:
            data["races"].append(race)
            change_count += 1
            print(f"  Added: {race['name']} ({race['date']})")

        if change_count > 0:
            save_data(data)
            print(f"\n  ✓  {change_count} change(s) saved.")
        else:
            print("\n  Schedule is already up to date.")

    except Exception as e:
        print(f"  Error fetching schedule: {e}")

    input("  Press Enter to continue...")


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------


def _render_driver_list(roster: list[DriverInfo], picked: list[DriverInfo]) -> None:
    """Print the numbered driver roster, marking already-picked drivers."""
    current_team = ""
    for i, d in enumerate(roster):
        # Blank line between teams for visual grouping
        if d["team"] != current_team:
            if current_team:  # not the very first team
                print()
            current_team = d["team"]

        pick_pos = next((j + 1 for j, p in enumerate(picked) if p is d), None)
        if pick_pos:
            tag = f"✓ P{pick_pos:<2}"
            print(f"  [{i + 1:>2}]  {d['abbr']}  {d['name']:<22}  {tag}")
        else:
            print(f"  [{i + 1:>2}]  {d['abbr']}  {d['name']:<22}  {d['team']}")


def _build_prediction(
    race_name: str,
    player: str,
    prefill: list[str] | None = None,
) -> list[str] | None:
    """Interactive driver-select loop.  Returns the prediction as a list of
    canonical driver keys, or None if the user cancels.

    Pass *prefill* (a list of driver keys from an existing prediction) to
    pre-populate the picker when editing rather than starting from scratch.
    """
    roster = ROSTER  # module-level list; can be narrowed in future
    # Seed picked from an existing prediction (edit flow).
    picked: list[DriverInfo] = []
    if prefill:
        for key in prefill:
            driver = by_key(key)
            if driver and driver not in picked:
                picked.append(driver)

    while True:
        # --- Selection loop: keep picking until 10 chosen or user exits ---
        while len(picked) < 10:
            pos = len(picked) + 1
            clear_screen()
            _header(
                f"Prediction  –  {player}",
                f"{race_name}  •  Choose P{pos} of 10",
            )

            # Already-picked summary
            print()
            _rule("Picked so far")
            if not picked:
                print("  (none yet)")
            else:
                for j, d in enumerate(picked):
                    print(f"  P{j + 1:>2}  {d['abbr']}  {d['name']}")

            # Driver list
            print()
            _rule("Drivers")
            _render_driver_list(roster, picked)

            print()
            print("  [0]  Done / finish with fewer than 10")
            print()

            raw = input(f"  P{pos} – enter number (or 0 to finish): ").strip()

            if raw == "0":
                if not picked:
                    confirm = (
                        input("  No drivers picked yet. Cancel prediction? (y/n): ").strip().lower()
                    )
                    if confirm == "y":
                        return None
                    continue
                confirm = input(f"  {len(picked)}/10 picked. Finish early? (y/n): ").strip().lower()
                if confirm == "y":
                    break
                continue

            try:
                idx = int(raw) - 1
                if not (0 <= idx < len(roster)):
                    raise ValueError
            except ValueError:
                input("  Invalid number. Press Enter...")
                continue

            driver = roster[idx]
            existing = next((j + 1 for j, p in enumerate(picked) if p is driver), None)
            if existing:
                input(f"  {driver['name']} is already at P{existing}. Press Enter...")
                continue

            picked.append(driver)

        # --- Confirmation screen ---
        clear_screen()
        _header(
            f"Confirm Prediction  –  {player}",
            race_name,
        )
        print()
        for j, d in enumerate(picked):
            print(f"  P{j + 1:>2}  {d['abbr']}  {d['name']:<22}  {d['team']}")
        if len(picked) < 10:
            for j in range(len(picked), 10):
                print(f"  P{j + 1:>2}  ---  (not predicted)")
        print()

        answer = input("  Save? [y = yes / r = redo / n = cancel]: ").strip().lower()
        if answer == "y":
            return [d["key"] for d in picked]
        if answer == "r":
            picked = []
            continue  # restart the selection loop
        # anything else = cancel
        return None


def enter_predictions(data: GameData) -> None:
    clear_screen()
    _header("Enter Predictions")

    today = datetime.datetime.now().date().isoformat()
    upcoming = [
        r
        for r in data["races"]
        if not r.get("actual_results") and (not r.get("date") or r["date"] >= today)
    ]
    upcoming.sort(key=lambda x: x.get("date", "9999-12-31"))

    if not upcoming:
        input("\n  No upcoming races to predict for. Press Enter...")
        return

    max_name = max(len(r["name"]) for r in upcoming)

    def display_upcoming(r: RaceData) -> str:
        date_part = _fmt_date(r.get("date", ""))
        tag = "← next" if r is upcoming[0] else ""
        return f"{date_part}   {r['name']:<{max_name}}   {tag}"

    race = select_item(upcoming, "upcoming race", display_upcoming)
    if not race:
        return

    player = select_item(data["players"], "player")
    if not player:
        return

    existing = race["predictions"].get(player)
    if existing:
        clear_screen()
        _header(f"Edit Prediction  –  {player}", race["name"])
        print()
        _rule("Current prediction")
        for j, key in enumerate(existing):
            d = by_key(key)
            if d:
                print(f"  P{j + 1:>2}  {d['abbr']}  {d['name']}")
            else:
                print(f"  P{j + 1:>2}  ???  {key}")
        print()
        answer = input("  [e] Edit  [c] Cancel: ").strip().lower()
        if answer != "e":
            return
        prefill: list[str] | None = existing
    else:
        prefill = None

    prediction = _build_prediction(race["name"], player, prefill=prefill)
    if prediction is None:
        input("\n  Prediction cancelled. Press Enter...")
        return

    race["predictions"][player] = prediction
    save_data(data)
    action = "updated" if existing else "saved"
    input(f"\n  ✓  Prediction for {player} {action}. Press Enter...")


# ---------------------------------------------------------------------------
# Results entry
# ---------------------------------------------------------------------------


def enter_results(data: GameData) -> None:
    clear_screen()
    _header("Enter Race Results")

    today = datetime.datetime.now().date().isoformat()
    past_races = [r for r in data["races"] if r.get("date") and r["date"] <= today]
    past_races.sort(key=lambda x: x.get("date", "0000-00-00"))

    if not past_races:
        input("\n  No completed races available yet. Press Enter...")
        return

    max_name = max(len(r["name"]) for r in past_races)

    def display_past(r: RaceData) -> str:
        date_part = _fmt_date(r.get("date", ""))
        tag = "(logged)" if r.get("actual_results") else "(needed)"
        return f"{date_part}   {r['name']:<{max_name}}   {tag}"

    race = select_item(past_races, "completed race", display_past)
    if not race:
        return

    if race["actual_results"]:
        print(f"\n  WARNING: {race['name']} already has results logged.")
        if input("  Overwrite? (y/n): ").strip().lower() != "y":
            return

    if input("\n  Fetch results automatically via F1 APIs? (y/n): ").strip().lower() == "y":
        try:
            year = int(input("  Race year (e.g. 2025): ").strip())
            fetched = fetch_results(year, race["name"])

            if fetched:
                print("\n  Fetched Top 10:")
                for i, d in enumerate(fetched):
                    print(f"    {i + 1:>2}.  {d['name']}")
                if input("\n  Save these results? (y/n): ").strip().lower() == "y":
                    race["actual_results"] = fetched
                    save_data(data)
                    input(f"\n  ✓  Results for {race['name']} saved. Press Enter...")
                    return
            else:
                print("  Could not fetch data. Falling back to manual entry.")
        except ValueError:
            print("  Invalid year. Falling back to manual entry.")

    print(f"\n  Enter the TOP 10 results for {race['name']}:")
    print("  The system ignores case — use any consistent name format.")

    actual = get_input_list("Top 10:", max_items=10)
    race["actual_results"] = [{"name": s, "abbr": ""} for s in actual]
    save_data(data)
    input(f"\n  ✓  Results for {race['name']} saved. Press Enter...")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def _act_display(actual_entry: DriverResult | str | None) -> str:
    """Return a display string for one actual-result entry."""
    if actual_entry is None:
        return "(none)"
    if isinstance(actual_entry, dict):
        return actual_entry.get("name", str(actual_entry))
    return str(actual_entry)


def view_race_points(data: GameData) -> None:
    clear_screen()
    _header("View Race Points")

    today = datetime.datetime.now().date().isoformat()
    sorted_races = sorted(data["races"], key=lambda x: x.get("date", "9999-12-31"))

    max_name = max((len(r["name"]) for r in sorted_races), default=0)

    def display_race(r: RaceData) -> str:
        date_part = _fmt_date(r.get("date", ""))
        has_results = bool(r.get("actual_results"))
        tag = "(results logged)" if has_results else "(no results yet)"
        status = "[done]" if has_results or (r.get("date") and r["date"] < today) else "[upcoming]"
        return f"{date_part}   {r['name']:<{max_name}}   {status}  {tag}"

    race = select_item(sorted_races, "race", display_race)
    if not race:
        return

    actual = race["actual_results"]
    date_label = _fmt_date(race.get("date", ""))
    print()
    _header(f"{race['name']}  •  {date_label}")
    print()

    if not actual:
        print("  No results logged for this race yet.")
        input("\n  Press Enter to continue...")
        return

    # --- Score summary ---
    _rule("Scores  (lower is better)")
    max_pname = max((len(p) for p in data["players"]), default=0)
    for player in data["players"]:
        if player in race["predictions"]:
            pts = calculate_player_points_for_race(race["predictions"][player], actual)
            print(f"  {player:<{max_pname}}   {pts} pts")
        else:
            print(f"  {player:<{max_pname}}   10 pts  (no prediction – penalty)")
    _rule()

    # --- Per-player breakdown ---
    print()
    for player in data["players"]:
        _rule(f"Breakdown – {player}")

        if player not in race["predictions"]:
            print("  No prediction submitted – +10 point penalty")
            print()
            continue

        prediction = race["predictions"][player]
        pts = 0

        for i in range(10):
            pred = prediction[i] if i < len(prediction) else None
            actual_entry = actual[i] if i < len(actual) else None

            if pred is None and actual_entry is None:
                continue

            act = _act_display(actual_entry)
            delta = score_position(pred, actual_entry)
            pts += delta

            if delta == 0:
                print(f"  P{i + 1:>2}   OK   {act}")
            else:
                pred_str = pred if pred is not None else "(none)"
                print(f"  P{i + 1:>2}   +1   {pred_str!r}  →  {act}")

        print(f"  {'─' * 30}")
        print(f"  Total: {pts} pts")
        print()

    input("  Press Enter to continue...")


def view_standings(data: GameData) -> None:
    clear_screen()
    scores, races_counted = calculate_season_standings(data)
    sorted_players = sorted(scores.items(), key=lambda x: x[1])

    _header(
        "Season Standings  •  Lowest Score Wins",
        f"After {races_counted} of {len(data['races'])} races",
    )
    print()

    if not sorted_players:
        print("  No players yet.")
    else:
        max_pname = max(len(p) for p, _ in sorted_players)
        _rule()
        print(f"  {'#':<4} {'Player':<{max_pname}}   Points")
        _rule()
        for i, (player, score) in enumerate(sorted_players):
            print(f"  {i + 1:<4} {player:<{max_pname}}   {score}")
        _rule()

    print()
    print("  * Missing a prediction for a completed race = +10 pts")
    input("\n  Press Enter to continue...")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n  Exiting...")
        sys.exit(0)
