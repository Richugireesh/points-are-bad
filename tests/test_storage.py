"""Tests for points_are_bad.storage."""

import json
import os
import pathlib

import pytest

import points_are_bad.storage as storage_module
from points_are_bad.exceptions import StorageError
from points_are_bad.storage import load_data, save_data


@pytest.fixture(autouse=True)
def isolated_data_file(tmp_path, monkeypatch):
    """Redirect DATA_FILE to a temp directory for every test."""
    tmp_file = str(tmp_path / "test_data.json")
    monkeypatch.setattr(storage_module, "DATA_FILE", tmp_file)
    yield tmp_file


# ---------------------------------------------------------------------------
# load_data
# ---------------------------------------------------------------------------


class TestLoadData:
    def test_returns_default_when_no_file(self, isolated_data_file):
        assert not os.path.exists(isolated_data_file)
        data = load_data()
        assert data["players"] == []
        assert data["races"] == []
        # load_data writes the default so callers always have a file-backed object
        assert os.path.exists(isolated_data_file)

    def test_loads_existing_file(self, isolated_data_file):
        payload = {"players": ["alice"], "races": []}
        with open(isolated_data_file, "w") as f:
            json.dump(payload, f)
        data = load_data()
        assert data["players"] == ["alice"]
        assert data["races"] == []

    def test_loads_nested_data(self, isolated_data_file):
        payload = {
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
        with open(isolated_data_file, "w") as f:
            json.dump(payload, f)
        data = load_data()
        assert data["players"] == payload["players"]
        assert data["races"] == payload["races"]

    def test_migration_adds_version(self, isolated_data_file):
        """v0 data (no version field) gets version=1 after load."""
        with open(isolated_data_file, "w") as f:
            json.dump({"players": [], "races": []}, f)
        data = load_data()
        assert data["version"] == 1  # type: ignore[typeddict-item]

    def test_migration_normalises_plain_string_results(self, isolated_data_file):
        """v0 plain-string actual_results are converted to DriverResult dicts."""
        with open(isolated_data_file, "w") as f:
            json.dump({
                "players": [],
                "races": [{"name": "R", "date": "2026-01-01",
                           "actual_results": ["verstappen", "norris"],
                           "predictions": {}}],
            }, f)
        race = load_data()["races"][0]
        assert race["actual_results"] == [
            {"name": "verstappen", "abbr": ""},
            {"name": "norris", "abbr": ""},
        ]


# ---------------------------------------------------------------------------
# save_data
# ---------------------------------------------------------------------------


class TestSaveData:
    def test_creates_file(self, isolated_data_file):
        data = {"players": ["alice"], "races": []}
        save_data(data)
        assert os.path.exists(isolated_data_file)

    def test_written_content_is_valid_json(self, isolated_data_file):
        data = {"players": ["alice"], "races": []}
        save_data(data)
        with open(isolated_data_file) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_indented_output(self, isolated_data_file):
        save_data({"players": [], "races": []})
        with open(isolated_data_file) as f:
            raw = f.read()
        assert "\n" in raw  # indented output spans multiple lines

    def test_overwrites_existing_file(self, isolated_data_file):
        save_data({"players": ["alice"], "races": []})
        save_data({"players": ["bob"], "races": []})
        assert load_data()["players"] == ["bob"]

    def test_unicode_preserved(self, isolated_data_file):
        """Non-ASCII characters must survive the round-trip without escaping."""
        save_data({"players": ["São Paulo"], "races": []})
        raw = pathlib.Path(isolated_data_file).read_text(encoding="utf-8")
        assert "São Paulo" in raw  # not \u00e3

    def test_three_backups_created(self, isolated_data_file):
        """After four saves the three .bak files exist with correct contents."""
        import pathlib as _pl
        p = _pl.Path(isolated_data_file)
        for i in range(1, 5):
            save_data({"players": [f"save{i}"], "races": []})

        bak1 = json.loads(p.with_suffix(".bak1").read_text())
        bak2 = json.loads(p.with_suffix(".bak2").read_text())
        bak3 = json.loads(p.with_suffix(".bak3").read_text())
        live = json.loads(p.read_text())

        assert live["players"] == ["save4"]
        assert bak1["players"] == ["save3"]
        assert bak2["players"] == ["save2"]
        assert bak3["players"] == ["save1"]

    def test_fourth_backup_not_kept(self, isolated_data_file):
        """Only three .bak files exist — no .bak4."""
        import pathlib as _pl
        p = _pl.Path(isolated_data_file)
        for i in range(5):
            save_data({"players": [f"s{i}"], "races": []})
        assert not p.with_suffix(".bak4").exists()


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_save_then_load_identity(self, isolated_data_file):
        original = {
            "players": ["alice", "bob"],
            "races": [
                {
                    "name": "Bahrain GP",
                    "date": "2026-03-01",
                    "actual_results": [
                        {
                            "BroadcastName": "M VERSTAPPEN",
                            "Abbreviation": "VER",
                            "FirstName": "Max",
                            "LastName": "Verstappen",
                        }
                    ],
                    "predictions": {"alice": ["verstappen", "norris"]},
                }
            ],
            "version": 1,
        }
        save_data(original)
        assert load_data() == original


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestStorageErrors:
    def test_load_raises_storage_error_on_corrupt_json(self, isolated_data_file):
        with open(isolated_data_file, "w") as f:
            f.write("{ not valid json }")
        with pytest.raises(StorageError, match="Could not read"):
            load_data()

    def test_save_raises_storage_error_on_bad_path(self, monkeypatch, tmp_path):
        bad_path = str(tmp_path / "no_such_dir" / "data.json")
        monkeypatch.setattr(storage_module, "DATA_FILE", bad_path)
        with pytest.raises(StorageError, match="Could not write"):
            save_data({"players": [], "races": []})

    def test_save_raises_on_non_serializable_data(self, isolated_data_file):
        payload: dict = {"players": ["alice"], "races": [], "bad": object()}
        with pytest.raises(StorageError, match="Could not write"):
            save_data(payload)  # type: ignore[arg-type]
