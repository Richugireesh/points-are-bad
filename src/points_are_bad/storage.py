"""Persistence layer — load and save ``points_are_bad_data.json``.

The data file path defaults to ``points_are_bad_data.json`` in the current
working directory and can be overridden with the ``POINTS_DATA_FILE``
environment variable (useful for testing and alternate installs).
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from .exceptions import StorageError

if TYPE_CHECKING:
    from .models import GameData

__all__ = ["DATA_FILE", "load_data", "save_data"]

DATA_FILE = os.environ.get("POINTS_DATA_FILE", "points_are_bad_data.json")


def load_data() -> GameData:
    """Return game data from *DATA_FILE*, or a fresh default if absent."""
    if not os.path.exists(DATA_FILE):
        return {"players": [], "races": []}
    try:
        with open(DATA_FILE) as f:
            return json.load(f)  # type: ignore[no-any-return]
    except (OSError, json.JSONDecodeError) as e:
        raise StorageError(f"Could not read data file '{DATA_FILE}': {e}") from e


def save_data(data: GameData) -> None:
    """Write *data* to *DATA_FILE* as indented JSON."""
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except OSError as e:
        raise StorageError(f"Could not write data file '{DATA_FILE}': {e}") from e
