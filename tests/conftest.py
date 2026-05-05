"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


# ── Test database isolation ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr(storage_module, "_JSON_PATH", tmp_path / "nonexistent.json")
    monkeypatch.setattr(storage_module, "_DB_PATH", db_path)
