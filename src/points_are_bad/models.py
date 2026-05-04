"""Shared TypedDict definitions for the points-are-bad data model.

These types are backed by SQLite tables (see ``storage.py`` for the schema)
and are used throughout the package to give mypy and editors a precise view
of the data.  The structure mirrors the original JSON format for backward
compatibility with legacy data files.

Legacy JSON structure (auto-migrated to SQLite on first run)::

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
``actual_results`` entries are always ``DriverResult`` dicts (``{"abbr": ..., "name": ...}``)
once loaded.  Legacy plain-string entries from the manual-entry path
are normalised to dicts by ``storage._migrate_json_to_sqlite`` during migration.
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
    """One Grand Prix entry in the database."""

    name: str
    date: str
    # Always a list of DriverResult dicts — plain-string manual entries are
    # normalised to {"name": ..., "abbr": ""} by storage._migrate_json_to_sqlite
    # during migration.
    actual_results: list[DriverResult]
    # player name -> ordered list of canonical driver keys (lowercase)
    predictions: dict[str, list[str]]


class GameData(TypedDict, total=False):
    """Top-level database state returned by ``storage.load_data()``.

    ``version`` is written by the storage layer to track the schema version.
    It is declared with ``total=False`` so callers and tests that construct
    GameData dicts without a version key don't need to supply it.
    """

    players: list[str]
    races: list[RaceData]
    version: int


class DriverInfo(TypedDict):
    """One row from the hardcoded driver roster in ``drivers.py``."""

    abbr: str
    name: str
    team: str
    key: str
