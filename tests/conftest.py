"""Shared pytest fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from points_are_bad.models import GameData


@pytest.fixture()
def sample_data() -> GameData:
    """Minimal GameData with two players, one completed race, one upcoming."""
    return {
        "players": ["Alice", "Bob"],
        "races": [
            {
                "name": "Bahrain Grand Prix",
                "date": "2026-01-01",
                "actual_results": [
                    {"abbr": "VER", "name": "Max Verstappen"},
                    {"abbr": "NOR", "name": "Lando Norris"},
                ],
                "predictions": {
                    "Alice": ["verstappen", "norris"],
                    "Bob": ["norris", "verstappen"],
                },
            },
            {
                "name": "Australian Grand Prix",
                "date": "2099-03-16",
                "actual_results": [],
                "predictions": {},
            },
        ],
    }


@pytest.fixture(autouse=True)
def no_clear_screen(monkeypatch):
    """Prevent os.system('clear'/'cls') from clearing the pytest terminal."""
    monkeypatch.setattr("os.system", lambda cmd: None)
