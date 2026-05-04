"""Persistence layer — SQLite backend with JSON fallback migration.

The database file defaults to ``points_are_bad_data.db`` in the current
working directory and can be overridden with the ``POINTS_DATA_FILE``
environment variable (the extension is swapped from .json to .db).

SQLite is used with WAL journal mode for concurrent read/write safety
across threads and Gunicorn workers.  On first run, existing JSON data
is migrated into the database automatically.

Thread-safety
-------------
SQLite in WAL mode with ``check_same_thread=False`` handles concurrent
access from multiple threads (and even multiple processes — i.e. Gunicorn
workers).  No application-level lock is needed.

Data integrity
--------------
Mutations use explicit ``BEGIN IMMEDIATE`` transactions.  Read operations
use immediate-mode queries which are consistent within a single connection
under WAL mode.
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from .exceptions import StorageError

if TYPE_CHECKING:
    from .models import GameData, RaceData

__all__ = [
    "DATA_FILE",
    "DATA_DB_FILE",
    "add_player",
    "add_race",
    "backup_db",
    "find_player",
    "find_race",
    "init_db",
    "load_data",
    "remove_player",
    "remove_race",
    "save_data",
    "set_prediction",
    "set_results",
]

# Point at the JSON file (legacy / migration source) and the SQLite database.
_JSON_FILE = os.environ.get("POINTS_DATA_FILE", "points_are_bad_data.json")
_DB_PATH = pathlib.Path(_JSON_FILE).with_suffix(".db")
DATA_DB_FILE = str(_DB_PATH)
DATA_FILE = _JSON_FILE  # kept for backward compat with test imports

# Current schema version — bump when changing the SQLite schema.
_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


def _get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection in WAL mode."""
    conn = sqlite3.connect(DATA_DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS players (
        name TEXT PRIMARY KEY
    );

    CREATE TABLE IF NOT EXISTS races (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        date TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS race_results (
        race_id INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        abbr TEXT NOT NULL DEFAULT '',
        driver_name TEXT NOT NULL,
        PRIMARY KEY (race_id, position)
    );

    CREATE TABLE IF NOT EXISTS predictions (
        race_id INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
        player_name TEXT NOT NULL REFERENCES players(name) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        driver_key TEXT NOT NULL,
        PRIMARY KEY (race_id, player_name, position)
    );
"""


def init_db() -> None:
    """Create tables and schema if they do not exist.

    Safe to call repeatedly — all DDL uses ``IF NOT EXISTS``.
    Also applies any pending incremental schema migrations.
    Callers that also need legacy JSON migration should use :func:`_ensure_db`
    which wraps this function with auto-migration logic.
    """
    conn = _get_conn()
    try:
        conn.executescript(_SCHEMA_SQL)
        _apply_migrations(conn)
        conn.commit()
    finally:
        conn.close()


def backup_db(backup_path: str | None = None) -> str:
    """Create a lightweight backup of the SQLite database.

    Uses SQLite's online backup API so reads/writes can continue during
    the copy.  Returns the path to the backup file.

    If *backup_path* is ``None``, the backup is written alongside the
    database file with a ``.backup`` extension.
    """
    src = _get_conn()
    try:
        dest_path = backup_path or f"{DATA_DB_FILE}.backup"
        dest = sqlite3.connect(dest_path)
        try:
            src.backup(dest)
        finally:
            dest.close()
        return dest_path
    finally:
        src.close()


# ---------------------------------------------------------------------------
# JSON → SQLite migration
# ---------------------------------------------------------------------------

# Ordered list of schema migrations past version 1.
# Append new entries when the schema changes:
#   (target_version, "description", [sql_statement, ...])
_MIGRATIONS: list[tuple[int, str, list[str]]] = []


def _current_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version from the database, or 0 if unset."""
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] if row and row[0] is not None else 0


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply any pending schema migrations in order."""
    current = _current_schema_version(conn)
    for target, description, stmts in _MIGRATIONS:
        if target <= current:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in stmts:
                conn.execute(stmt)
            conn.execute(
                "INSERT OR REPLACE INTO schema_version(version) VALUES (?)",
                (target,),
            )
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise StorageError(f"Schema migration to v{target} ({description}) failed") from None


def _migrate_json_to_sqlite(json_path: pathlib.Path) -> None:
    """Import a legacy JSON data file into the SQLite database.

    Called once on first startup when SQLite is empty but JSON exists.
    """
    raw = json.loads(json_path.read_text(encoding="utf-8"))

    # Handle v0 plain-string actual_results (same as old _migrate)
    v = raw.get("version", 0)
    if v < 1:
        for race in raw.get("races", []):
            raw_results = race.get("actual_results", [])
            normalised = []
            for entry in raw_results:
                if isinstance(entry, str):
                    normalised.append({"name": entry, "abbr": ""})
                else:
                    normalised.append(entry)
            race["actual_results"] = normalised

    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")

        conn.execute(
            "INSERT OR REPLACE INTO schema_version(version) VALUES (?)",
            (_SCHEMA_VERSION,),
        )

        for name in raw.get("players", []):
            conn.execute("INSERT OR IGNORE INTO players(name) VALUES (?)", (str(name).lower(),))

        for race in raw.get("races", []):
            race_name = race.get("name", "")
            race_date = race.get("date", "")
            conn.execute(
                "INSERT OR IGNORE INTO races(name, date) VALUES (?, ?)",
                (race_name, race_date),
            )
            race_id = conn.execute("SELECT id FROM races WHERE name = ?", (race_name,)).fetchone()[
                0
            ]

            for pos, entry in enumerate(race.get("actual_results", [])):
                abbr = str(entry.get("abbr", "")) if isinstance(entry, dict) else ""
                name = str(entry.get("name", entry)) if isinstance(entry, dict) else str(entry)
                conn.execute(
                    "INSERT INTO race_results"
                    "(race_id, position, abbr, driver_name) VALUES (?, ?, ?, ?)",
                    (race_id, pos + 1, abbr, name),
                )

            for player, preds in race.get("predictions", {}).items():
                for i, key in enumerate(preds):
                    conn.execute(
                        "INSERT INTO predictions"
                        "(race_id, player_name, position, driver_key)"
                        " VALUES (?, ?, ?, ?)",
                        (race_id, str(player).lower(), i + 1, key),
                    )

        conn.commit()

        # Rename JSON to .bak so it isn't re-imported on next start
        bak_path = json_path.with_suffix(".json.migrated")
        json_path.rename(bak_path)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_data() -> GameData:
    """Return the full game state as a GameData dict.

    On first run, if no SQLite database exists but a JSON file does,
    the JSON data is migrated into SQLite automatically.
    """
    db_path = pathlib.Path(DATA_DB_FILE)
    json_path = pathlib.Path(_JSON_FILE)

    # First run: no DB yet
    if not db_path.exists():
        init_db()
        if json_path.exists():
            _migrate_json_to_sqlite(json_path)

    conn = _get_conn()
    try:
        # Load players
        players: list[str] = [
            row["name"] for row in conn.execute("SELECT name FROM players ORDER BY name")
        ]

        # Load races with results and predictions
        races = []
        for race_row in conn.execute("SELECT id, name, date FROM races ORDER BY date, name"):
            race_id = race_row["id"]

            # Load results for this race
            actual_results: list[dict[str, str]] = []
            for res_row in conn.execute(
                "SELECT abbr, driver_name FROM race_results WHERE race_id = ? ORDER BY position",
                (race_id,),
            ):
                actual_results.append({"abbr": res_row["abbr"], "name": res_row["driver_name"]})

            # Load predictions for this race
            predictions: dict[str, list[str]] = {}
            for pred_row in conn.execute(
                "SELECT player_name, driver_key FROM predictions"
                " WHERE race_id = ? ORDER BY position",
                (race_id,),
            ):
                player = pred_row["player_name"]
                if player not in predictions:
                    predictions[player] = []
                predictions[player].append(pred_row["driver_key"])

            race_dict: RaceData = {
                "name": race_row["name"],
                "date": race_row["date"],
                "actual_results": actual_results,  # type: ignore[typeddict-item]
                "predictions": predictions,
            }
            races.append(race_dict)

    finally:
        conn.close()

    return {
        "players": players,
        "races": races,
        "version": _SCHEMA_VERSION,
    }


def save_data(data: GameData) -> None:
    """Write the full game state to the SQLite database.

    Uses a transaction: clears existing data and re-inserts everything
    from the GameData dict.  This ensures the database always reflects
    the exact state provided by the caller.
    """
    # Ensure tables exist
    db_path = pathlib.Path(DATA_DB_FILE)
    if not db_path.exists():
        init_db()

    # Snapshot the current state before the destructive rewrite.
    if db_path.exists() and db_path.stat().st_size > 0:
        backup_db()

    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")

        # Clear existing data (bottom-up to respect foreign keys)
        conn.execute("DELETE FROM predictions")
        conn.execute("DELETE FROM race_results")
        conn.execute("DELETE FROM races")
        conn.execute("DELETE FROM players")

        # Re-insert
        for name in data.get("players", []):
            conn.execute("INSERT INTO players(name) VALUES (?)", (str(name).lower(),))

        for race in data.get("races", []):
            race_name = race.get("name", "")
            race_date = race.get("date", "")
            conn.execute(
                "INSERT INTO races(name, date) VALUES (?, ?)",
                (race_name, race_date),
            )
            race_id = conn.execute("SELECT id FROM races WHERE name = ?", (race_name,)).fetchone()[
                0
            ]

            for pos, entry in enumerate(race.get("actual_results", [])):
                abbr = str(entry.get("abbr", "")) if isinstance(entry, dict) else ""
                name = str(entry.get("name", entry)) if isinstance(entry, dict) else str(entry)
                conn.execute(
                    "INSERT INTO race_results"
                    "(race_id, position, abbr, driver_name) VALUES (?, ?, ?, ?)",
                    (race_id, pos + 1, abbr, name),
                )

            for player, preds in race.get("predictions", {}).items():
                for i, key in enumerate(preds):
                    conn.execute(
                        "INSERT INTO predictions"
                        "(race_id, player_name, position, driver_key)"
                        " VALUES (?, ?, ?, ?)",
                        (race_id, str(player).lower(), i + 1, key),
                    )

        conn.execute(
            "INSERT OR REPLACE INTO schema_version(version) VALUES (?)",
            (_SCHEMA_VERSION,),
        )
        conn.commit()

    except sqlite3.Error as e:
        conn.rollback()
        raise StorageError(f"Could not write database '{DATA_DB_FILE}': {e}") from e
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Targeted operations — safe for concurrent use under SQLite WAL
# ---------------------------------------------------------------------------


def _ensure_db() -> None:
    """Create the database and tables if they don't exist.  Idempotent.

    On first run, the legacy JSON file (if present) is migrated into
    SQLite.  The rename of the JSON file is atomic, so racing workers
    will either find the file already gone or hit an integrity error
    on the duplicate INSERT — both cases are caught and are harmless.
    """
    if not pathlib.Path(DATA_DB_FILE).exists():
        init_db()
    json_path = pathlib.Path(_JSON_FILE)
    if json_path.exists():
        with suppress(FileNotFoundError, sqlite3.IntegrityError):
            # Racing worker already completed the migration.
            _migrate_json_to_sqlite(json_path)


def find_race(race_name: str) -> dict[str, Any] | None:
    """Return a race dict (name, date, actual_results, predictions) or None."""
    _ensure_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, name, date FROM races WHERE name = ?", (race_name,)
        ).fetchone()
        if row is None:
            return None

        race_id = row["id"]
        results = [
            {"abbr": r["abbr"], "name": r["driver_name"]}
            for r in conn.execute(
                "SELECT abbr, driver_name FROM race_results WHERE race_id = ? ORDER BY position",
                (race_id,),
            )
        ]
        predictions: dict[str, list[str]] = {}
        for pr in conn.execute(
            "SELECT player_name, driver_key FROM predictions WHERE race_id = ? ORDER BY position",
            (race_id,),
        ):
            predictions.setdefault(pr["player_name"], []).append(pr["driver_key"])

        return {
            "name": row["name"],
            "date": row["date"],
            "actual_results": results,
            "predictions": predictions,
        }
    finally:
        conn.close()


def find_player(name: str) -> bool:
    """Return ``True`` if the player exists.

    Lightweight existence check — opens a single connection and runs a
    ``SELECT 1`` query without loading full game state.  Prefer this over
    ``load_data()`` when the caller only needs to validate a player name.
    """
    _ensure_db()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT 1 FROM players WHERE name = ?", (name.lower(),)).fetchone()
        return row is not None
    finally:
        conn.close()


def add_player(name: str) -> None:
    """Add a player.  Raises StorageError if already exists."""
    _ensure_db()
    conn = _get_conn()
    try:
        conn.execute("INSERT INTO players(name) VALUES (?)", (name.lower(),))
        conn.commit()
    except sqlite3.IntegrityError:
        raise StorageError(f"Player '{name}' already exists") from None
    finally:
        conn.close()


def remove_player(name: str) -> None:
    """Remove a player and all their predictions (CASCADE)."""
    _ensure_db()
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM players WHERE name = ?", (name.lower(),))
        conn.commit()
        if cur.rowcount == 0:
            raise StorageError(f"Unknown player: {name}")
    finally:
        conn.close()


def add_race(race_name: str, race_date: str = "") -> None:
    """Add a race.  Raises StorageError if already exists."""
    _ensure_db()
    conn = _get_conn()
    try:
        conn.execute("INSERT INTO races(name, date) VALUES (?, ?)", (race_name, race_date))
        conn.commit()
    except sqlite3.IntegrityError:
        raise StorageError(f"Race '{race_name}' already exists") from None
    finally:
        conn.close()


def remove_race(race_name: str) -> None:
    """Remove a race and its results + predictions (CASCADE)."""
    _ensure_db()
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM races WHERE name = ?", (race_name,))
        conn.commit()
        if cur.rowcount == 0:
            raise StorageError(f"Unknown race: {race_name}")
    finally:
        conn.close()


def set_prediction(race_name: str, player: str, driver_keys: list[str]) -> None:
    """Upsert a player's prediction for a race."""
    _ensure_db()
    conn = _get_conn()
    try:
        race_row = conn.execute("SELECT id FROM races WHERE name = ?", (race_name,)).fetchone()
        if race_row is None:
            raise StorageError(f"Unknown race: {race_name}")

        race_id = race_row["id"]
        player_lower = player.lower()

        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM predictions WHERE race_id = ? AND player_name = ?",
            (race_id, player_lower),
        )
        for i, key in enumerate(driver_keys):
            conn.execute(
                "INSERT INTO predictions"
                "(race_id, player_name, position, driver_key)"
                " VALUES (?, ?, ?, ?)",
                (race_id, player_lower, i + 1, key),
            )
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise StorageError(f"Could not save prediction: {e}") from e
    finally:
        conn.close()


def set_results(race_name: str, results: list[dict[str, str]]) -> None:
    """Set actual race results (list of {name, abbr} dicts)."""
    _ensure_db()
    conn = _get_conn()
    try:
        race_row = conn.execute("SELECT id FROM races WHERE name = ?", (race_name,)).fetchone()
        if race_row is None:
            raise StorageError(f"Unknown race: {race_name}")

        race_id = race_row["id"]

        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM race_results WHERE race_id = ?", (race_id,))
        for i, entry in enumerate(results):
            conn.execute(
                "INSERT INTO race_results"
                "(race_id, position, abbr, driver_name) VALUES (?, ?, ?, ?)",
                (race_id, i + 1, str(entry.get("abbr", "")), str(entry.get("name", ""))),
            )
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise StorageError(f"Could not save results: {e}") from e
    finally:
        conn.close()
