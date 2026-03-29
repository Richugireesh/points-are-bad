"""Shared TypedDict definitions for the points-are-bad data model.

These types mirror the structure of ``points_are_bad_data.json`` and are used
throughout the package to give mypy and editors a precise view of the data.

JSON structure::

    {
        "players": ["Alice", "Bob"],
        "races": [{
            "name": "Australian Grand Prix",
            "date": "2026-03-08",
            "actual_results": [{"name": "Max Verstappen", "abbr": "VER"}, ...],
            "predictions": {
                "Alice": ["verstappen", "norris", ...],
                "Bob": ["leclerc", "piastri", ...]
            }
        }]
    }

Notes
-----
``actual_results`` may also contain plain strings from the manual-entry
path in ``cli.py``.  The union ``DriverResult | str`` captures both forms.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "DriverInfo",
    "DriverResult",
    "GameData",
    "RaceData",
]


class DriverResult(TypedDict):
    """A single finishing-position entry as returned by the API layer."""

    abbr: str
    name: str


class RaceData(TypedDict):
    """One Grand Prix entry stored in ``points_are_bad_data.json``."""

    name: str
    date: str
    # May be DriverResult dicts (from API) or plain strings (manual entry).
    actual_results: list[DriverResult | str]
    # player name -> ordered list of canonical driver keys (lowercase)
    predictions: dict[str, list[str]]


class GameData(TypedDict):
    """Top-level structure of ``points_are_bad_data.json``."""

    players: list[str]
    races: list[RaceData]


class DriverInfo(TypedDict):
    """One row from the hardcoded driver roster in ``drivers.py``."""

    abbr: str
    name: str
    team: str
    key: str
