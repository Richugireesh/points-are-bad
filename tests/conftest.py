"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from points_are_bad.models import GameData


# ── Test data fixtures ──────────────────────────────────────────────────────


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


# ── Test database isolation ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path: "Path", monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect storage to a temp SQLite database for every test session.

    This fixture is autouse — it ensures **no** test can accidentally read
    or write the production database.  All storage module globals that
    reference persistent paths are redirected to a temporary directory.

    The database is not created here; individual tests or their fixtures
    create it on demand via ``init_db()`` or ``_ensure_db()``.
    """
    if "points_are_bad.storage" not in sys.modules:
        return

    import points_are_bad.storage as storage_module

    db_path = tmp_path / "test_data.db"
    db_file = str(db_path)

    monkeypatch.setattr(storage_module, "DATA_DB_FILE", db_file)
    monkeypatch.setattr(storage_module, "DATA_FILE", db_file)
    monkeypatch.setattr(storage_module, "_JSON_FILE", str(tmp_path / "nonexistent.json"))
    monkeypatch.setattr(storage_module, "_DB_PATH", db_path)


# ── Environment guards ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def no_clear_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent os.system('clear'/'cls') from clearing the pytest terminal."""
    monkeypatch.setattr("os.system", lambda cmd: None)
