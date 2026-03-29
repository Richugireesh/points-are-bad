"""Tests for pure utility functions and mocked interactive helpers in cli.py."""

from __future__ import annotations

import datetime

import pytest

import points_are_bad.cli as cli_mod
from points_are_bad.cli import (
    _act_display,
    _fmt_date,
    _season_context,
    parse_raw_input_lines,
    select_item,
)


# ---------------------------------------------------------------------------
# _fmt_date
# ---------------------------------------------------------------------------

class TestFmtDate:
    def test_valid_iso_date(self):
        assert _fmt_date("2026-03-16") == "Mar 16"

    def test_empty_string_returns_unknown(self):
        assert _fmt_date("") == "Unknown"

    def test_bad_string_returned_as_is(self):
        result = _fmt_date("not-a-date")
        assert result == "not-a-date"

    def test_year_month_day_parsed(self):
        assert _fmt_date("2026-11-22") == "Nov 22"


# ---------------------------------------------------------------------------
# _season_context
# ---------------------------------------------------------------------------

class TestSeasonContext:
    def test_output_contains_year(self):
        data = {"players": ["alice"], "races": []}
        result = _season_context(data)
        assert str(datetime.datetime.now().year) in result

    def test_singular_player_word(self):
        data = {"players": ["alice"], "races": []}
        assert "1 player" in _season_context(data)

    def test_plural_player_word(self):
        data = {"players": ["alice", "bob"], "races": []}
        assert "2 players" in _season_context(data)

    def test_race_counts(self):
        races = [
            {"name": "R1", "date": "2026-01-01", "actual_results": ["ver"], "predictions": {}},
            {"name": "R2", "date": "2026-02-01", "actual_results": [], "predictions": {}},
        ]
        data = {"players": ["alice"], "races": races}
        result = _season_context(data)
        assert "1/2" in result


# ---------------------------------------------------------------------------
# _act_display
# ---------------------------------------------------------------------------

class TestActDisplay:
    def test_none_returns_none_str(self):
        assert _act_display(None) == "(none)"

    def test_string_returned_as_is(self):
        assert _act_display("verstappen") == "verstappen"

    def test_dict_with_name_key(self):
        assert _act_display({"abbr": "VER", "name": "Max Verstappen"}) == "Max Verstappen"

    def test_dict_without_name_falls_back_to_str(self):
        result = _act_display({"abbr": "VER"})
        assert "VER" in result


# ---------------------------------------------------------------------------
# parse_raw_input_lines
# ---------------------------------------------------------------------------

class TestParseRawInputLines:
    def test_numbered_list(self):
        lines = ["1. verstappen", "2. norris", "3. piastri"]
        result = parse_raw_input_lines(lines, 10)
        assert result == ["verstappen", "norris", "piastri"]

    def test_paren_numbers(self):
        lines = ["1) verstappen", "2) norris"]
        result = parse_raw_input_lines(lines, 10)
        assert result == ["verstappen", "norris"]

    def test_comma_separated(self):
        lines = ["verstappen, norris, piastri"]
        result = parse_raw_input_lines(lines, 10)
        assert result == ["verstappen", "norris", "piastri"]

    def test_max_items_truncates(self):
        lines = [f"driver{i}" for i in range(15)]
        result = parse_raw_input_lines(lines, 5)
        assert len(result) == 5

    def test_hidden_chars_stripped(self):
        lines = ["ver\u2060stappen"]
        result = parse_raw_input_lines(lines, 10)
        assert result == ["verstappen"]

    def test_zero_width_space_stripped(self):
        lines = ["nor\u200bris"]
        result = parse_raw_input_lines(lines, 10)
        assert result == ["norris"]

    def test_leading_paren_stripped(self):
        lines = ["1. (verstappen)"]
        result = parse_raw_input_lines(lines, 10)
        # content after "1." split is "(verstappen)" — leading "(" is stripped
        assert result[0] == "verstappen)"  # only leading ( is stripped

    def test_empty_lines_ignored(self):
        lines = ["verstappen", "", "norris"]
        result = parse_raw_input_lines(lines, 10)
        assert "verstappen" in result
        assert "norris" in result


# ---------------------------------------------------------------------------
# select_item
# ---------------------------------------------------------------------------

class TestSelectItem:
    def test_valid_selection_returns_item(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "1")
        result = select_item(["alice", "bob"], "player")
        assert result == "alice"

    def test_second_item_selection(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "2")
        result = select_item(["alice", "bob"], "player")
        assert result == "bob"

    def test_empty_list_returns_none(self, monkeypatch, capsys):
        # select_item prompts input when list is empty too
        monkeypatch.setattr("builtins.input", lambda _: "")
        result = select_item([], "player")
        assert result is None

    def test_out_of_range_returns_none(self, monkeypatch):
        # select_item calls input() twice when invalid: for the choice, then "Press Enter"
        responses = iter(["99", ""])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        result = select_item(["alice"], "player")
        assert result is None

    def test_non_numeric_returns_none(self, monkeypatch):
        responses = iter(["abc", ""])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        result = select_item(["alice"], "player")
        assert result is None

    def test_custom_display_func(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "1")
        items = [{"name": "Max", "abbr": "VER"}]
        select_item(items, "driver", lambda d: d["name"])
        captured = capsys.readouterr()
        assert "Max" in captured.out


# ---------------------------------------------------------------------------
# Box drawing helpers
# ---------------------------------------------------------------------------

class TestBoxHelpers:
    def test_box_top_starts_with_corner(self):
        from points_are_bad.cli import _box_top
        result = _box_top()
        assert result.startswith("╔")
        assert result.endswith("╗")

    def test_box_bot_starts_with_corner(self):
        from points_are_bad.cli import _box_bot
        result = _box_bot()
        assert result.startswith("╚")
        assert result.endswith("╝")

    def test_box_row_contains_text(self):
        from points_are_bad.cli import _box_row
        result = _box_row("hello")
        assert "hello" in result
        assert result.startswith("║")
        assert result.endswith("║")
