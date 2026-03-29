"""Tests for points_are_bad.storage."""

import json
import os

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
        assert data == {"players": [], "races": []}

    def test_loads_existing_file(self, isolated_data_file):
        payload = {"players": ["alice"], "races": []}
        with open(isolated_data_file, "w") as f:
            json.dump(payload, f)
        assert load_data() == payload

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
        assert load_data() == payload


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
                        {"BroadcastName": "M VERSTAPPEN", "Abbreviation": "VER",
                         "FirstName": "Max", "LastName": "Verstappen"}
                    ],
                    "predictions": {"alice": ["verstappen", "norris"]},
                }
            ],
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
