"""Tests for points_are_bad.storage."""

import os
import pathlib
import sqlite3
import threading

import pytest

import points_are_bad.storage as storage_module
from points_are_bad.exceptions import StorageError
from points_are_bad.storage import (
    add_player,
    add_race,
    backup_db,
    find_race,
    init_db,
    load_data,
    remove_player,
    remove_race,
    save_data,
    set_prediction,
    set_results,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirect DATA_DB_FILE to a temp path for every test."""
    db_file = str(tmp_path / "test_data.db")
    monkeypatch.setattr(storage_module, "DATA_DB_FILE", db_file)
    monkeypatch.setattr(storage_module, "DATA_FILE", db_file)
    yield db_file


# ---------------------------------------------------------------------------
# load_data
# ---------------------------------------------------------------------------


class TestLoadData:
    def test_returns_default_when_no_file(self, isolated_db):
        assert not os.path.exists(isolated_db)
        data = load_data()
        assert data["players"] == []
        assert data["races"] == []
        assert os.path.exists(isolated_db)

    def test_loads_after_save(self, isolated_db):
        init_db()
        save_data(
            {
                "players": ["alice", "bob"],
                "races": [
                    {
                        "name": "Bahrain GP",
                        "date": "2026-03-01",
                        "actual_results": [],
                        "predictions": {"alice": ["verstappen"]},
                    }
                ],
            }
        )
        data = load_data()
        assert data["players"] == ["alice", "bob"]
        assert data["races"][0]["predictions"]["alice"] == ["verstappen"]


# ---------------------------------------------------------------------------
# save_data
# ---------------------------------------------------------------------------


class TestSaveData:
    def test_creates_db(self, isolated_db):
        init_db()
        save_data({"players": ["alice"], "races": []})
        assert os.path.exists(isolated_db)

    def test_writes_to_database(self, isolated_db):
        init_db()
        save_data({"players": ["alice"], "races": []})
        conn = sqlite3.connect(isolated_db)
        rows = conn.execute("SELECT name FROM players").fetchall()
        assert ("alice",) in rows
        conn.close()

    def test_overwrites(self, isolated_db):
        init_db()
        save_data({"players": ["alice"], "races": []})
        save_data({"players": ["bob"], "races": []})
        assert load_data()["players"] == ["bob"]

    def test_unicode_preserved(self, isolated_db):
        init_db()
        save_data({"players": ["São Paulo"], "races": []})
        data = load_data()
        assert "são paulo" in data["players"]  # save_data lowercases

    def test_round_trip_with_results(self, isolated_db):
        init_db()
        data = {
            "players": ["alice"],
            "races": [
                {
                    "name": "Bahrain GP",
                    "date": "2026-03-01",
                    "actual_results": [{"abbr": "VER", "name": "Max Verstappen"}],
                    "predictions": {"alice": ["verstappen"]},
                }
            ],
        }
        save_data(data)
        loaded = load_data()
        assert loaded["races"][0]["actual_results"] == data["races"][0]["actual_results"]
        assert loaded["races"][0]["predictions"] == data["races"][0]["predictions"]


# ---------------------------------------------------------------------------
# Targeted operations
# ---------------------------------------------------------------------------


class TestAddPlayer:
    def test_adds_to_db(self, isolated_db):
        init_db()
        add_player("alice")
        assert "alice" in load_data()["players"]

    def test_duplicate_raises(self, isolated_db):
        init_db()
        add_player("alice")
        with pytest.raises(StorageError, match="already exists"):
            add_player("alice")


class TestRemovePlayer:
    def test_removes_from_db(self, isolated_db):
        init_db()
        add_player("alice")
        remove_player("alice")
        assert "alice" not in load_data()["players"]

    def test_unknown_raises(self, isolated_db):
        init_db()
        with pytest.raises(StorageError, match="Unknown player"):
            remove_player("nobody")

    def test_cleans_predictions(self, isolated_db):
        init_db()
        add_player("alice")
        add_race("Monaco GP")
        set_prediction("Monaco GP", "alice", ["verstappen"] * 10)
        remove_player("alice")
        race = find_race("Monaco GP")
        assert race is not None
        assert "alice" not in race["predictions"]


class TestAddRace:
    def test_adds_race(self, isolated_db):
        init_db()
        add_race("Monaco GP", "2026-05-25")
        race = find_race("Monaco GP")
        assert race is not None
        assert race["name"] == "Monaco GP"
        assert race["date"] == "2026-05-25"

    def test_duplicate_raises(self, isolated_db):
        init_db()
        add_race("Monaco GP")
        with pytest.raises(StorageError, match="already exists"):
            add_race("Monaco GP")


class TestRemoveRace:
    def test_removes_race(self, isolated_db):
        init_db()
        add_race("Monaco GP")
        remove_race("Monaco GP")
        assert find_race("Monaco GP") is None

    def test_unknown_raises(self, isolated_db):
        init_db()
        with pytest.raises(StorageError, match="Unknown race"):
            remove_race("Fake GP")


class TestSetPrediction:
    def test_sets_and_reads(self, isolated_db):
        init_db()
        add_player("alice")
        add_race("Monaco GP")
        pred = [
            "verstappen",
            "norris",
            "leclerc",
            "hamilton",
            "russell",
            "piastri",
            "antonelli",
            "gasly",
            "hadjar",
            "lawson",
        ]
        set_prediction("Monaco GP", "alice", pred)
        race = find_race("Monaco GP")
        assert race is not None
        assert race["predictions"]["alice"] == pred

    def test_unknown_race_raises(self, isolated_db):
        init_db()
        with pytest.raises(StorageError, match="Unknown race"):
            set_prediction("Fake GP", "alice", ["verstappen"] * 10)

    def test_overwrites_existing(self, isolated_db):
        init_db()
        add_player("alice")
        add_race("Monaco GP")
        set_prediction("Monaco GP", "alice", ["verstappen"] * 10)
        new_pred = ["norris"] * 10
        set_prediction("Monaco GP", "alice", new_pred)
        race = find_race("Monaco GP")
        assert race is not None
        assert race["predictions"]["alice"] == new_pred


class TestSetResults:
    def test_sets_results(self, isolated_db):
        init_db()
        add_race("Monaco GP")
        results = [
            {"abbr": "VER", "name": "Max Verstappen"},
            {"abbr": "NOR", "name": "Lando Norris"},
        ]
        set_results("Monaco GP", results)
        race = find_race("Monaco GP")
        assert race is not None
        assert race["actual_results"] == results

    def test_unknown_race_raises(self, isolated_db):
        init_db()
        with pytest.raises(StorageError, match="Unknown race"):
            set_results("Fake GP", [{"abbr": "VER", "name": "Max Verstappen"}])


class TestEnsureDb:
    def test_autocreates_db_when_missing(self, isolated_db, monkeypatch):
        """_ensure_db should create the DB and tables when they don't exist."""
        # No JSON file to migrate
        monkeypatch.setattr(storage_module, "_JSON_PATH", pathlib.Path("/nonexistent/path.json"))
        assert not os.path.exists(isolated_db)
        # Calling a targeted op triggers _ensure_db
        add_player("alice")
        assert os.path.exists(isolated_db)
        assert "alice" in load_data()["players"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestStorageErrors:
    def test_bad_db_path_raises(self, monkeypatch):
        monkeypatch.setattr(storage_module, "DATA_DB_FILE", "/nonexistent/dir/sub/db.db")
        with pytest.raises((StorageError, sqlite3.OperationalError)):
            save_data({"players": [], "races": []})


# ---------------------------------------------------------------------------
# JSON → SQLite migration
# ---------------------------------------------------------------------------


class TestMigrateJsonToSqlite:
    def test_migrates_players_and_races(self, tmp_path, monkeypatch):
        import json
        from pathlib import Path

        db_file = str(tmp_path / "migrated.db")
        monkeypatch.setattr(storage_module, "DATA_DB_FILE", db_file)
        storage_module.init_db()

        json_path = tmp_path / "legacy.json"
        legacy = {
            "version": 1,
            "players": ["alice", "bob"],
            "races": [
                {
                    "name": "Bahrain GP",
                    "date": "2026-03-01",
                    "actual_results": [
                        {"abbr": "VER", "name": "Max Verstappen"},
                        {"abbr": "NOR", "name": "Lando Norris"},
                    ],
                    "predictions": {
                        "alice": ["verstappen", "norris"],
                        "bob": ["norris", "verstappen"],
                    },
                }
            ],
        }
        json_path.write_text(json.dumps(legacy), encoding="utf-8")

        storage_module._migrate_json_to_sqlite(Path(str(json_path)))

        data = load_data()
        assert set(data["players"]) == {"alice", "bob"}
        assert len(data["races"]) == 1
        assert data["races"][0]["name"] == "Bahrain GP"
        assert data["races"][0]["actual_results"] == [
            {"abbr": "VER", "name": "Max Verstappen"},
            {"abbr": "NOR", "name": "Lando Norris"},
        ]
        assert data["races"][0]["predictions"] == {
            "alice": ["verstappen", "norris"],
            "bob": ["norris", "verstappen"],
        }

        # JSON file should be renamed to .migrated
        assert not json_path.exists()
        assert json_path.with_suffix(".json.migrated").exists()

    def test_migrates_v0_plain_string_results(self, tmp_path, monkeypatch):
        import json
        from pathlib import Path

        db_file = str(tmp_path / "migrated_v0.db")
        monkeypatch.setattr(storage_module, "DATA_DB_FILE", db_file)
        storage_module.init_db()

        json_path = tmp_path / "legacy_v0.json"
        legacy = {
            "version": 0,
            "players": ["alice"],
            "races": [
                {
                    "name": "Sprint Race",
                    "date": "2026-02-15",
                    "actual_results": ["Max Verstappen", "Lando Norris"],
                    "predictions": {"alice": ["verstappen", "norris"]},
                }
            ],
        }
        json_path.write_text(json.dumps(legacy), encoding="utf-8")

        storage_module._migrate_json_to_sqlite(Path(str(json_path)))

        data = load_data()
        results = data["races"][0]["actual_results"]
        assert results == [
            {"name": "Max Verstappen", "abbr": ""},
            {"name": "Lando Norris", "abbr": ""},
        ]


# ---------------------------------------------------------------------------
# Concurrent access (SQLite WAL)
# ---------------------------------------------------------------------------


class TestConcurrentAccess:
    def test_concurrent_reads_dont_block(self, isolated_db):
        init_db()
        save_data({"players": ["alice"], "races": []})
        errors: list[Exception] = []

        def reader():
            try:
                for _ in range(20):
                    data = load_data()
                    assert "alice" in data["players"]
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

    def test_concurrent_writes_dont_corrupt(self, isolated_db):
        init_db()
        save_data({"players": ["alice", "bob", "charlie"], "races": []})
        errors: list[Exception] = []

        def writer(player: str):
            try:
                pred = [
                    "verstappen",
                    "norris",
                    "leclerc",
                    "hamilton",
                    "russell",
                    "piastri",
                    "antonelli",
                    "gasly",
                    "hadjar",
                    "lawson",
                ]
                add_race(f"GP-{player}")
                set_prediction(f"GP-{player}", player, pred)
                # Read back to verify
                race = find_race(f"GP-{player}")
                assert race is not None
                assert race["predictions"][player] == pred
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(p,)) for p in ("alice", "bob", "charlie")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # All three races should exist
        data = load_data()
        assert len(data["races"]) == 3

    def test_read_while_writing(self, isolated_db):
        init_db()
        save_data({"players": ["alice"], "races": []})
        errors: list[Exception] = []
        write_done = threading.Event()

        def writer():
            try:
                for i in range(10):
                    add_player(f"player_{i}")
                write_done.set()
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                while not write_done.is_set():
                    data = load_data()
                    assert isinstance(data["players"], list)
            except Exception as e:
                errors.append(e)

        w = threading.Thread(target=writer)
        r = threading.Thread(target=reader)
        w.start()
        r.start()
        w.join()
        r.join()

        assert not errors


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


class TestBackup:
    def test_backup_creates_file(self, isolated_db):
        init_db()
        save_data({"players": ["alice"], "races": []})
        backup_path = backup_db()
        assert os.path.exists(backup_path)
        # Backup should be a valid SQLite database
        conn = sqlite3.connect(backup_path)
        rows = conn.execute("SELECT name FROM players").fetchall()
        assert ("alice",) in rows
        conn.close()

    def test_backup_custom_path(self, tmp_path, isolated_db):
        init_db()
        save_data({"players": ["alice"], "races": []})
        custom = str(tmp_path / "custom.backup")
        result = backup_db(custom)
        assert result == custom
        assert os.path.exists(custom)
