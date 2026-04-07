"""Tests for the interactive menu and view functions in cli.py.

All input() calls are mocked via monkeypatch; clear_screen (os.system) is
suppressed globally by the conftest.py autouse fixture.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import points_are_bad.cli as cli_mod
from points_are_bad.cli import (
    _auto_populate_schedule,
    _header,
    _render_driver_list,
    _rule,
    auto_update_past_races,
    enter_predictions,
    enter_results,
    get_input_list,
    main_menu,
    manage_players,
    manage_races,
    view_race_points,
    view_standings,
)
from points_are_bad.drivers import ROSTER

# ---------------------------------------------------------------------------
# _header / _rule
# ---------------------------------------------------------------------------


class TestHeaderRule:
    def test_header_prints_border_and_content(self, capsys):
        _header("Title Line", "Subtitle")
        out = capsys.readouterr().out
        assert "Title Line" in out
        assert "Subtitle" in out
        assert "╔" in out
        assert "╚" in out

    def test_rule_no_label_prints_dashes(self, capsys):
        _rule()
        out = capsys.readouterr().out
        assert "─" in out

    def test_rule_with_label(self, capsys):
        _rule("Section")
        out = capsys.readouterr().out
        assert "Section" in out
        assert "─" in out


# ---------------------------------------------------------------------------
# get_input_list
# ---------------------------------------------------------------------------


class TestGetInputList:
    def test_ten_items_inline(self, monkeypatch):
        drivers = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
        responses = iter(drivers)
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        result = get_input_list("Enter 10:", min_items=10, max_items=10)
        assert len(result) == 10

    def test_finishes_early_on_y_confirmation(self, monkeypatch):
        # Three drivers then empty line, confirm early finish
        responses = iter(["a", "b", "c", "", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        result = get_input_list("Enter:", min_items=3, max_items=10)
        assert len(result) == 3

    def test_continues_on_n_confirmation(self, monkeypatch):
        # Two drivers, empty → n (not done) → three more drivers, empty → y
        responses = iter(["a", "b", "", "n", "c", "d", "e", "", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        result = get_input_list("Enter:", min_items=3, max_items=10)
        assert len(result) >= 3


# ---------------------------------------------------------------------------
# auto_update_past_races
# ---------------------------------------------------------------------------


class TestAutoUpdatePastRaces:
    def test_no_past_races_does_nothing(self, sample_data):
        # Remove the past race; only the upcoming race remains
        sample_data["races"] = [sample_data["races"][1]]
        auto_update_past_races(sample_data)  # should not raise

    def test_past_race_already_has_results_skipped(self, sample_data):
        # Bahrain already has results — no fetch should happen
        with patch.object(cli_mod, "fetch_results") as mock_fetch:
            auto_update_past_races(sample_data)
        mock_fetch.assert_not_called()

    def test_past_race_without_results_triggers_fetch(self, monkeypatch, sample_data):
        # Clear Bahrain results so it looks incomplete
        sample_data["races"][0]["actual_results"] = []
        fetched = [{"abbr": "VER", "name": "Max Verstappen"}]
        monkeypatch.setattr("builtins.input", lambda _: "")
        with (
            patch.object(cli_mod, "fetch_results", return_value=fetched),
            patch.object(cli_mod, "save_data"),
        ):
            auto_update_past_races(sample_data)
        assert sample_data["races"][0]["actual_results"] == fetched

    def test_failed_fetch_leaves_results_empty(self, monkeypatch, sample_data):
        sample_data["races"][0]["actual_results"] = []
        monkeypatch.setattr("builtins.input", lambda _: "")
        with (
            patch.object(cli_mod, "fetch_results", return_value=None),
            patch.object(cli_mod, "save_data") as mock_save,
        ):
            auto_update_past_races(sample_data)
        mock_save.assert_not_called()
        assert sample_data["races"][0]["actual_results"] == []


# ---------------------------------------------------------------------------
# manage_players
# ---------------------------------------------------------------------------


class TestManagePlayers:
    def test_back_exits(self, monkeypatch, sample_data):
        monkeypatch.setattr("builtins.input", lambda _: "3")
        manage_players(sample_data)  # should return without error

    def test_add_player(self, monkeypatch, sample_data):
        responses = iter(["1", "Charlie", "", "3"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data"):
            manage_players(sample_data)
        assert "Charlie" in sample_data["players"]

    def test_add_duplicate_player_no_change(self, monkeypatch, sample_data):
        original_count = len(sample_data["players"])
        responses = iter(["1", "Alice", "", "3"])  # Alice already exists
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data"):
            manage_players(sample_data)
        assert len(sample_data["players"]) == original_count

    def test_remove_player(self, monkeypatch, sample_data):
        responses = iter(["2", "Alice", "", "3"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data"):
            manage_players(sample_data)
        assert "Alice" not in sample_data["players"]

    def test_remove_nonexistent_player(self, monkeypatch, sample_data):
        original = list(sample_data["players"])
        responses = iter(["2", "Nobody", "", "3"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data"):
            manage_players(sample_data)
        assert sample_data["players"] == original


# ---------------------------------------------------------------------------
# manage_races
# ---------------------------------------------------------------------------


class TestManageRaces:
    def test_back_exits(self, monkeypatch, sample_data):
        monkeypatch.setattr("builtins.input", lambda _: "4")
        manage_races(sample_data)

    def test_add_race(self, monkeypatch, sample_data):
        responses = iter(["1", "Monaco GP", "2026-05-25", "", "4"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data"):
            manage_races(sample_data)
        names = [r["name"] for r in sample_data["races"]]
        assert "Monaco GP" in names

    def test_remove_race(self, monkeypatch, sample_data):
        # "2" → Remove Race, "1" → pick Bahrain (first in list), "y" → confirm,
        # "" → Press Enter, "4" → Back
        responses = iter(["2", "1", "y", "", "4"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data"):
            manage_races(sample_data)
        names = [r["name"] for r in sample_data["races"]]
        assert "Bahrain Grand Prix" not in names

    def test_remove_race_cancelled_leaves_list_unchanged(self, monkeypatch, sample_data):
        original_len = len(sample_data["races"])
        # "2" → Remove Race, "1" → pick Bahrain, "n" → cancel, "" → Press Enter, "4" → Back
        responses = iter(["2", "1", "n", "", "4"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data") as mock_save:
            manage_races(sample_data)
        mock_save.assert_not_called()
        assert len(sample_data["races"]) == original_len

    def test_add_race_invalid_date_rejected(self, monkeypatch, capsys, sample_data):
        """Invalid date format is rejected and the race is not added."""
        original_count = len(sample_data["races"])
        # "1" → Add Race, "Test GP" → name, "banana" → bad date,
        # "" → Press Enter (error), "4" → Back
        responses = iter(["1", "Test GP", "banana", "", "4"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data") as mock_save:
            manage_races(sample_data)
        mock_save.assert_not_called()
        assert len(sample_data["races"]) == original_count

    def test_add_race_blank_date_accepted(self, monkeypatch, sample_data):
        """A blank date is valid — the race is added without a date."""
        responses = iter(["1", "Test GP", "", "", "4"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data"):
            manage_races(sample_data)
        race = next(r for r in sample_data["races"] if r["name"] == "Test GP")
        assert race["date"] == ""

    def test_add_race_sorted_by_date(self, monkeypatch, sample_data):
        """Races are sorted by date after adding a new one."""
        responses = iter(["1", "Early GP", "2020-01-01", "", "4"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data"):
            manage_races(sample_data)
        dates = [r.get("date", "") for r in sample_data["races"] if r.get("date")]
        assert dates == sorted(dates)

    def test_auto_populate_no_fastf1(self, monkeypatch, sample_data):
        monkeypatch.setattr(cli_mod, "HAS_FASTF1", False)
        responses = iter(["3", "", "4"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        manage_races(sample_data)  # should handle missing FastF1 gracefully


# ---------------------------------------------------------------------------
# _auto_populate_schedule
# ---------------------------------------------------------------------------


class TestAutoPopulateSchedule:
    def test_no_fastf1_prompts_with_message(self, monkeypatch, sample_data):
        monkeypatch.setattr(cli_mod, "HAS_FASTF1", False)
        prompts: list[str] = []
        monkeypatch.setattr("builtins.input", lambda p: prompts.append(p) or "")
        _auto_populate_schedule(sample_data)
        assert any("FastF1" in p for p in prompts)

    def test_adds_new_races_from_schedule(self, monkeypatch, sample_data):
        monkeypatch.setattr(cli_mod, "HAS_FASTF1", True)
        new_race = {
            "name": "Monaco GP",
            "date": "2026-05-25",
            "actual_results": [],
            "predictions": {},
        }
        monkeypatch.setattr("builtins.input", lambda _: "")
        with (
            patch.object(cli_mod, "get_schedule_updates", return_value=([new_race], [])),
            patch.object(cli_mod, "save_data"),
        ):
            _auto_populate_schedule(sample_data)
        names = [r["name"] for r in sample_data["races"]]
        assert "Monaco GP" in names

    def test_handles_api_error_gracefully(self, monkeypatch, capsys, sample_data):
        monkeypatch.setattr(cli_mod, "HAS_FASTF1", True)
        monkeypatch.setattr("builtins.input", lambda _: "")
        with patch.object(cli_mod, "get_schedule_updates", side_effect=RuntimeError("boom")):
            _auto_populate_schedule(sample_data)
        out = capsys.readouterr().out
        assert "Error" in out or "boom" in out


# ---------------------------------------------------------------------------
# _render_driver_list
# ---------------------------------------------------------------------------


class TestRenderDriverList:
    def test_prints_all_drivers(self, capsys):
        roster = ROSTER[:4]
        _render_driver_list(roster, [])
        out = capsys.readouterr().out
        for driver in roster[:4]:
            assert driver["abbr"] in out

    def test_marks_picked_drivers(self, capsys):
        roster = ROSTER[:3]
        picked = [roster[0]]
        _render_driver_list(roster, picked)
        out = capsys.readouterr().out
        assert "P1" in out
        assert "✓" in out


# ---------------------------------------------------------------------------
# enter_predictions
# ---------------------------------------------------------------------------


class TestEnterPredictions:
    def test_no_upcoming_races_exits_early(self, monkeypatch, sample_data):
        # Remove the upcoming race; only completed race remains
        sample_data["races"] = [sample_data["races"][0]]
        prompts: list[str] = []
        monkeypatch.setattr("builtins.input", lambda p: prompts.append(p) or "")
        enter_predictions(sample_data)
        assert any("No upcoming races" in p for p in prompts)

    def test_no_players_returns_none(self, monkeypatch, sample_data):
        sample_data["players"] = []
        # select_item for race returns None (empty list)
        responses = iter(["", ""])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        enter_predictions(sample_data)  # should return gracefully

    def test_edit_existing_prediction_cancel_does_not_save(self, monkeypatch, sample_data):
        """When a player already has a prediction and chooses 'c', nothing is saved."""
        existing = [
            "verstappen", "norris", "leclerc", "hamilton", "russell",
            "piastri", "antonelli", "gasly", "hadjar", "lawson",
        ]
        sample_data["races"][1]["predictions"]["Alice"] = existing[:]

        responses = iter([
            "1",  # select Australian GP (the only upcoming race)
            "1",  # select Alice (who already has a prediction)
            "c",  # cancel edit
        ])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data") as mock_save:
            enter_predictions(sample_data)
        mock_save.assert_not_called()
        # Prediction unchanged
        assert sample_data["races"][1]["predictions"]["Alice"] == existing

    def test_edit_existing_prediction_saves_updated(self, monkeypatch, sample_data):
        """When a player edits their prediction, the new one is stored."""
        old_pred = [
            "verstappen", "norris", "leclerc", "hamilton", "russell",
            "piastri", "antonelli", "gasly", "hadjar", "lawson",
        ]
        new_pred = list(reversed(old_pred))
        sample_data["races"][1]["predictions"]["Alice"] = old_pred[:]

        responses = iter([
            "1",  # select Australian GP
            "1",  # select Alice
            "e",  # edit
            "",   # Press Enter after save confirmation
        ])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        # Bypass the full picker UI — return a canned new prediction
        monkeypatch.setattr(cli_mod, "_build_prediction", lambda *a, **kw: new_pred)
        with patch.object(cli_mod, "save_data") as mock_save:
            enter_predictions(sample_data)
        mock_save.assert_called_once()
        assert sample_data["races"][1]["predictions"]["Alice"] == new_pred

    def test_build_prediction_prefill_pre_populates_picks(self, monkeypatch):
        """_build_prediction with prefill seeds the picker with existing drivers."""
        from points_are_bad.cli import _build_prediction

        prefill = ["verstappen", "norris"]
        # Picker starts at P3 (2 already filled); "0" → finish early → "y" confirm
        responses = iter(["0", "y", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        result = _build_prediction("Test Race", "alice", prefill=prefill)
        # First two slots must be the pre-filled drivers in order
        assert result is not None
        assert result[:2] == prefill


# ---------------------------------------------------------------------------
# enter_results
# ---------------------------------------------------------------------------


class TestEnterResults:
    def test_no_past_races_exits_early(self, monkeypatch, sample_data):
        # Only keep the future race
        sample_data["races"] = [sample_data["races"][1]]
        prompts: list[str] = []
        monkeypatch.setattr("builtins.input", lambda p: prompts.append(p) or "")
        enter_results(sample_data)
        assert any("No completed races" in p for p in prompts)

    def test_manual_entry_saves_results(self, monkeypatch, sample_data):
        # Select race 1 (Bahrain, with existing results), overwrite, manual entry
        responses = iter(
            [
                "1",  # select Bahrain
                "y",  # overwrite existing results
                "n",  # don't auto-fetch
                "ver",
                "nor",
                "pia",
                "lec",
                "ham",  # 5 drivers
                "rus",
                "sai",
                "alo",
                "per",
                "str",  # 5 more
                "",  # finish input
                "",  # "Press Enter to continue"
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with patch.object(cli_mod, "save_data"):
            enter_results(sample_data)
        # actual_results updated with manual string list
        assert len(sample_data["races"][0]["actual_results"]) > 0


# ---------------------------------------------------------------------------
# view_race_points
# ---------------------------------------------------------------------------


class TestViewRacePoints:
    def test_race_without_results_shows_message(self, monkeypatch, capsys, sample_data):
        # Select the upcoming race (no results)
        responses = iter(["2", ""])  # select race 2, then press Enter
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        view_race_points(sample_data)
        out = capsys.readouterr().out
        assert "No results logged" in out

    def test_race_with_results_shows_scores(self, monkeypatch, capsys, sample_data):
        responses = iter(["1", ""])  # select Bahrain, then press Enter
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        view_race_points(sample_data)
        out = capsys.readouterr().out
        assert "Alice" in out or "Bob" in out

    def test_no_race_selected(self, monkeypatch, sample_data):
        # Select out-of-range → None returned → function exits
        responses = iter(["99", ""])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        view_race_points(sample_data)  # should not raise


# ---------------------------------------------------------------------------
# view_standings
# ---------------------------------------------------------------------------


class TestViewStandings:
    def test_shows_standings(self, monkeypatch, capsys, sample_data):
        monkeypatch.setattr("builtins.input", lambda _: "")
        view_standings(sample_data)
        out = capsys.readouterr().out
        assert "Alice" in out
        assert "Bob" in out

    def test_no_players_shows_message(self, monkeypatch, capsys):
        data = {"players": [], "races": []}
        monkeypatch.setattr("builtins.input", lambda _: "")
        view_standings(data)
        out = capsys.readouterr().out
        assert "No players yet" in out


# ---------------------------------------------------------------------------
# main_menu
# ---------------------------------------------------------------------------


class TestMainMenu:
    def test_exit_choice_saves_and_exits(self, monkeypatch, sample_data):
        responses = iter(["7"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with (
            patch.object(cli_mod, "load_data", return_value=sample_data),
            patch.object(cli_mod, "auto_update_past_races"),
            patch.object(cli_mod, "save_data"),
            pytest.raises(SystemExit),
        ):
            main_menu()

    def test_invalid_choice_loops(self, monkeypatch, sample_data):
        responses = iter(["x", "", "7"])  # invalid → press enter → exit
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        with (
            patch.object(cli_mod, "load_data", return_value=sample_data),
            patch.object(cli_mod, "auto_update_past_races"),
            patch.object(cli_mod, "save_data"),
            pytest.raises(SystemExit),
        ):
            main_menu()
