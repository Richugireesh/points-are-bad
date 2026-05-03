"""Persistence layer — load and save ``points_are_bad_data.json``.

The data file path defaults to ``points_are_bad_data.json`` in the current
working directory and can be overridden with the ``POINTS_DATA_FILE``
environment variable (useful for testing and alternate installs).

Save behaviour
--------------
* Writes are atomic: data is flushed to a temp file in the same directory
  then ``os.replace``-d over the target (POSIX rename — no partial writes).
* Three rolling backups are kept alongside the live file:
    <file>.bak1  — previous save
    <file>.bak2  — save before that
    <file>.bak3  — oldest kept backup
  Each successful save rotates them: bak2→bak3, bak1→bak2, live→bak1,
  then the new file lands in place.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import tempfile
from typing import TYPE_CHECKING, Any

from .exceptions import StorageError

if TYPE_CHECKING:
    from .models import GameData

__all__ = ["DATA_FILE", "load_data", "save_data"]

DATA_FILE = os.environ.get("POINTS_DATA_FILE", "points_are_bad_data.json")

# Current schema version — bump when adding required fields and add a
# migration branch in _migrate().
_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def _migrate(raw: dict[str, Any]) -> GameData:
    """Upgrade *raw* JSON (any version) to the current schema in-place.

    Safe to call on already-current data — a no-op when ``raw["version"]``
    already equals ``_SCHEMA_VERSION``.
    """
    v = raw.get("version", 0)

    if v < 1:
        # v0 → v1: actual_results may contain plain strings from manual CLI
        # entry.  Normalise everything to {"name": ..., "abbr": ""} so callers
        # never need to handle the str branch.
        for race in raw.get("races", []):
            raw_results = race.get("actual_results", [])
            normalised = []
            for entry in raw_results:
                if isinstance(entry, str):
                    normalised.append({"name": entry, "abbr": ""})
                else:
                    normalised.append(entry)
            race["actual_results"] = normalised

    raw["version"] = _SCHEMA_VERSION
    return raw  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_data() -> GameData:
    """Return game data from *DATA_FILE*, migrating to the current schema.

    If the file does not exist yet a fresh default is written to disk and
    returned — so the caller always receives a file-backed object.
    """
    path = pathlib.Path(DATA_FILE)
    if not path.exists():
        default: GameData = {"players": [], "races": [], "version": _SCHEMA_VERSION}
        save_data(default)
        return default
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise StorageError(f"Could not read data file '{DATA_FILE}': {e}") from e
    return _migrate(raw)


def save_data(data: GameData) -> None:
    """Write *data* to *DATA_FILE* atomically, keeping three rolling backups.

    The write sequence is:
      1. Serialise to a temp file in the same directory (same filesystem →
         rename is atomic on POSIX).
      2. Rotate backups: bak2→bak3, bak1→bak2, live→bak1.
      3. Rename temp file over the live path.
    """
    path = pathlib.Path(DATA_FILE)
    try:
        # 1. Write to temp (same dir ensures same filesystem for atomic rename)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=4, ensure_ascii=False)
        except Exception as e:
            os.unlink(tmp_name)
            raise StorageError(
                f"Could not write data file '{DATA_FILE}': {e}"
            ) from e

        # 2. Rotate backups (ignore missing files — first run has none)
        _rotate_backups(path)

        # 3. Atomic replace
        os.replace(tmp_name, path)

    except OSError as e:
        raise StorageError(f"Could not write data file '{DATA_FILE}': {e}") from e


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rotate_backups(path: pathlib.Path) -> None:
    """Rotate .bak1/.bak2/.bak3 before each save.

    bak2 → bak3  (oldest kept; previous bak3 is dropped)
    bak1 → bak2
    live → bak1
    """
    bak = [path.with_suffix(f".bak{i}") for i in (1, 2, 3)]
    # Drop oldest first so we never have 4 copies simultaneously
    if bak[2].exists():
        bak[2].unlink()
    if bak[1].exists():
        bak[1].replace(bak[2])
    if bak[0].exists():
        bak[0].replace(bak[1])
    if path.exists():
        # Copy (not rename) so the live file persists until the atomic replace
        shutil.copy2(path, bak[0])
