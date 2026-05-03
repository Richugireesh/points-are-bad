"""Tests for points_are_bad.models.

TypedDicts are pure structural type declarations.  These tests verify that
all public types are importable and constructible at runtime, and that the
expected keys are present.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from points_are_bad.models import DriverInfo, DriverResult, GameData, RaceData


class TestDriverResult:
    def test_constructible(self):
        result: DriverResult = {"abbr": "VER", "name": "Max Verstappen"}
        assert result["abbr"] == "VER"
        assert result["name"] == "Max Verstappen"


class TestRaceData:
    def test_constructible(self):
        race: RaceData = {
            "name": "Bahrain Grand Prix",
            "date": "2026-03-01",
            "actual_results": [],
            "predictions": {},
        }
        assert race["name"] == "Bahrain Grand Prix"
        assert race["actual_results"] == []

    def test_with_results(self):
        race: RaceData = {
            "name": "Bahrain Grand Prix",
            "date": "2026-03-01",
            "actual_results": [{"abbr": "VER", "name": "Max Verstappen"}],
            "predictions": {"alice": ["verstappen"]},
        }
        assert len(race["actual_results"]) == 1
        assert race["predictions"]["alice"] == ["verstappen"]


class TestGameData:
    def test_constructible(self):
        data: GameData = {"players": ["alice"], "races": []}
        assert data["players"] == ["alice"]
        assert data["races"] == []


class TestDriverInfo:
    def test_constructible(self):
        info: DriverInfo = {
            "abbr": "VER",
            "name": "Max Verstappen",
            "team": "Red Bull",
            "key": "verstappen",
        }
        assert info["key"] == "verstappen"
