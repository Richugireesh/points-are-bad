"""Tests for the Flask web server endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Generator

import points_are_bad.storage as storage_module
import web.server as web_server
from web.server import app, limiter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_OPEN_PRED = [
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

_MINIMAL_DATA: dict = {
    "players": ["alice", "bob"],
    "races": [
        {
            "name": "Australian Grand Prix",
            "date": "2026-03-08",
            "actual_results": [
                {"abbr": "VER", "name": "Max Verstappen"},
                {"abbr": "NOR", "name": "Lando Norris"},
            ],
            "predictions": {
                "alice": [
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
                ],
            },
        },
        {
            "name": "Bahrain Grand Prix",
            "date": "2099-12-31",
            "actual_results": [],
            "predictions": {},
        },
    ],
}


@pytest.fixture()
def tmp_data(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Create a temp SQLite database pre-populated with _MINIMAL_DATA."""
    db_file = tmp_path / "data.db"
    monkeypatch.setattr(storage_module, "DATA_DB_FILE", str(db_file))
    storage_module.init_db()
    storage_module.save_data(_MINIMAL_DATA)
    return db_file


@pytest.fixture()
def client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Generator:
    # Point both DATA_FILE and DATA_DB_FILE at the temp db
    db_file = str(tmp_path / "data.db")
    monkeypatch.setattr(storage_module, "DATA_DB_FILE", db_file)
    monkeypatch.setattr(storage_module, "DATA_FILE", db_file)
    storage_module.init_db()
    storage_module.save_data(_MINIMAL_DATA)
    monkeypatch.setattr(limiter, "enabled", False)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# GET /data
# ---------------------------------------------------------------------------


def test_get_data_returns_players_and_races(client) -> None:
    res = client.get("/data")
    assert res.status_code == 200
    body = res.get_json()
    assert body["players"] == ["alice", "bob"]
    assert len(body["races"]) == 2


# ---------------------------------------------------------------------------
# GET /aliases
# ---------------------------------------------------------------------------


def test_get_aliases_returns_dict(client) -> None:
    res = client.get("/aliases")
    assert res.status_code == 200
    aliases = res.get_json()
    assert isinstance(aliases, dict)
    assert aliases["kimi"] == "antonelli"
    assert aliases["ver"] == "verstappen"


# ---------------------------------------------------------------------------
# POST /predictions — happy path
# ---------------------------------------------------------------------------


def test_post_prediction_saves_to_file(client) -> None:
    res = client.post(
        "/predictions",
        json={
            "player": "alice",
            "race_name": "Bahrain Grand Prix",
            "prediction": _OPEN_PRED,
        },
    )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    race = storage_module.find_race("Bahrain Grand Prix")
    assert race is not None
    assert race["predictions"]["alice"] == _OPEN_PRED


def test_post_prediction_bob_independent(client) -> None:
    client.post(
        "/predictions",
        json={
            "player": "alice",
            "race_name": "Bahrain Grand Prix",
            "prediction": _OPEN_PRED,
        },
    )
    client.post(
        "/predictions",
        json={
            "player": "bob",
            "race_name": "Bahrain Grand Prix",
            "prediction": list(reversed(_OPEN_PRED)),
        },
    )
    race = storage_module.find_race("Bahrain Grand Prix")
    assert race is not None
    assert race["predictions"]["alice"] == _OPEN_PRED
    assert race["predictions"]["bob"] == list(reversed(_OPEN_PRED))


# ---------------------------------------------------------------------------
# POST /predictions — validation errors
# ---------------------------------------------------------------------------


def test_post_prediction_unknown_player(client) -> None:
    res = client.post(
        "/predictions",
        json={
            "player": "ghost",
            "race_name": "Bahrain Grand Prix",
            "prediction": _OPEN_PRED,
        },
    )
    assert res.status_code == 400
    assert "Unknown player" in res.get_json()["error"]


def test_post_prediction_unknown_race(client) -> None:
    res = client.post(
        "/predictions",
        json={
            "player": "alice",
            "race_name": "Fake Grand Prix",
            "prediction": _OPEN_PRED,
        },
    )
    assert res.status_code == 400
    assert "Unknown race" in res.get_json()["error"]


def test_post_prediction_race_has_results(client) -> None:
    res = client.post(
        "/predictions",
        json={
            "player": "alice",
            "race_name": "Australian Grand Prix",
            "prediction": _OPEN_PRED,
        },
    )
    assert res.status_code == 400
    assert "Results already entered" in res.get_json()["error"]


def test_post_prediction_wrong_length_short(client) -> None:
    res = client.post(
        "/predictions",
        json={
            "player": "alice",
            "race_name": "Bahrain Grand Prix",
            "prediction": ["verstappen", "norris"],
        },
    )
    assert res.status_code == 400
    assert "10" in res.get_json()["error"]


def test_post_prediction_wrong_length_long(client) -> None:
    res = client.post(
        "/predictions",
        json={
            "player": "alice",
            "race_name": "Bahrain Grand Prix",
            "prediction": _OPEN_PRED + ["colapinto"],
        },
    )
    assert res.status_code == 400


def test_post_prediction_not_a_list(client) -> None:
    res = client.post(
        "/predictions",
        json={
            "player": "alice",
            "race_name": "Bahrain Grand Prix",
            "prediction": "verstappen",
        },
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# POST /predictions — duplicate / overwrite
# ---------------------------------------------------------------------------


def test_post_prediction_duplicate_rejected_with_409(client) -> None:
    payload = {"player": "alice", "race_name": "Bahrain Grand Prix", "prediction": _OPEN_PRED}
    client.post("/predictions", json=payload)
    res = client.post("/predictions", json=payload)
    assert res.status_code == 409
    assert "already submitted" in res.get_json()["error"]


def test_post_prediction_overwrite_accepted(client, tmp_data: pathlib.Path) -> None:
    new_pred = list(reversed(_OPEN_PRED))
    client.post(
        "/predictions",
        json={
            "player": "alice",
            "race_name": "Bahrain Grand Prix",
            "prediction": _OPEN_PRED,
        },
    )
    res = client.post(
        "/predictions",
        json={
            "player": "alice",
            "race_name": "Bahrain Grand Prix",
            "prediction": new_pred,
            "overwrite": True,
        },
    )
    assert res.status_code == 200
    assert storage_module.find_race("Bahrain Grand Prix")["predictions"]["alice"] == new_pred


# ---------------------------------------------------------------------------
# POST /players
# ---------------------------------------------------------------------------


def test_add_player_happy_path(client) -> None:
    res = client.post("/players", json={"name": "charlie"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["name"] == "charlie"

    assert "charlie" in storage_module.load_data()["players"]


def test_add_player_normalises_to_lowercase(client) -> None:
    res = client.post("/players", json={"name": "Charlie"})
    assert res.status_code == 200
    assert "charlie" in storage_module.load_data()["players"]


def test_add_player_duplicate_rejected(client) -> None:
    res = client.post("/players", json={"name": "alice"})
    assert res.status_code == 409
    assert "already exists" in res.get_json()["error"]


def test_add_player_empty_name(client) -> None:
    res = client.post("/players", json={"name": ""})
    assert res.status_code == 400


def test_add_player_name_too_long(client) -> None:
    res = client.post("/players", json={"name": "a" * 31})
    assert res.status_code == 400


def test_add_player_whitespace_only(client) -> None:
    res = client.post("/players", json={"name": "   "})
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# POST /races
# ---------------------------------------------------------------------------


def test_add_race_happy_path(client) -> None:
    res = client.post("/races", json={"name": "Monaco Grand Prix", "date": "2026-05-25"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["name"] == "Monaco Grand Prix"
    assert storage_module.find_race("Monaco Grand Prix") is not None


def test_add_race_without_date(client) -> None:
    res = client.post("/races", json={"name": "TBD Grand Prix"})
    assert res.status_code == 200
    race = storage_module.find_race("TBD Grand Prix")
    assert race is not None
    assert race["date"] == ""


def test_add_race_sorted_by_date(client) -> None:
    """Races are returned sorted by date from the database."""
    client.post("/races", json={"name": "Early GP", "date": "2026-01-01"})
    client.post("/races", json={"name": "Late GP", "date": "2099-12-31"})
    data = storage_module.load_data()
    dates = [r.get("date", "") for r in data["races"] if r.get("date")]
    assert dates == sorted(dates)


def test_add_race_empty_name(client) -> None:
    res = client.post("/races", json={"name": ""})
    assert res.status_code == 400


def test_add_race_name_too_long(client) -> None:
    res = client.post("/races", json={"name": "x" * 101})
    assert res.status_code == 400


def test_add_race_duplicate_rejected(client) -> None:
    res = client.post("/races", json={"name": "Australian Grand Prix"})
    assert res.status_code == 409
    assert "already exists" in res.get_json()["error"]


def test_add_race_invalid_date_rejected(client) -> None:
    res = client.post("/races", json={"name": "Test GP", "date": "banana"})
    assert res.status_code == 400
    assert "YYYY-MM-DD" in res.get_json()["error"]


def test_add_race_bad_date_format_rejected(client) -> None:
    res = client.post("/races", json={"name": "Test GP", "date": "25-12-2026"})
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /races
# ---------------------------------------------------------------------------


def test_delete_race_removes_from_file(client) -> None:
    res = client.delete("/races", json={"race_name": "Bahrain Grand Prix"})
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    assert storage_module.find_race("Bahrain Grand Prix") is None


def test_delete_race_unknown_returns_404(client) -> None:
    res = client.delete("/races", json={"race_name": "Fake Grand Prix"})
    assert res.status_code == 404
    assert "Unknown race" in res.get_json()["error"]


def test_delete_race_missing_name_returns_400(client) -> None:
    res = client.delete("/races", json={})
    assert res.status_code == 400


def test_delete_race_with_results_returns_409(client) -> None:
    # Australian GP has actual_results in _MINIMAL_DATA
    res = client.delete("/races", json={"race_name": "Australian Grand Prix"})
    assert res.status_code == 409
    assert "already has results" in res.get_json()["error"]


# ---------------------------------------------------------------------------
# POST /races/fetch-results
# ---------------------------------------------------------------------------

_FAKE_RESULTS = [
    {"name": "Max Verstappen", "abbr": "VER"},
    {"name": "Lando Norris", "abbr": "NOR"},
    {"name": "Charles Leclerc", "abbr": "LEC"},
    {"name": "Lewis Hamilton", "abbr": "HAM"},
    {"name": "George Russell", "abbr": "RUS"},
    {"name": "Oscar Piastri", "abbr": "PIA"},
    {"name": "Andrea Kimi Antonelli", "abbr": "ANT"},
    {"name": "Pierre Gasly", "abbr": "GAS"},
    {"name": "Isack Hadjar", "abbr": "HAD"},
    {"name": "Liam Lawson", "abbr": "LAW"},
]

# Bahrain GP in _MINIMAL_DATA is 2026-04-12 (future).  These tests need a past
# race with no results, so we patch the data file with a backdated entry.
_PAST_RACE_NAME = "Saudi Arabian Grand Prix"


@pytest.fixture()
def client_with_past_race(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Generator:
    """Client fixture with a past race (no results) already in the database."""
    db_file = str(tmp_path / "data.db")
    monkeypatch.setattr(storage_module, "DATA_DB_FILE", db_file)
    monkeypatch.setattr(storage_module, "DATA_FILE", db_file)
    storage_module.init_db()
    data = dict(_MINIMAL_DATA)
    data["races"] = list(data["races"])
    data["races"].append(
        {
            "name": _PAST_RACE_NAME,
            "date": "2026-03-15",
            "actual_results": [],
            "predictions": {},
        }
    )
    storage_module.save_data(data)
    monkeypatch.setattr(limiter, "enabled", False)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_fetch_results_saves_to_file(
    client_with_past_race, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web_server, "_fetch_results", lambda *_: _FAKE_RESULTS)
    res = client_with_past_race.post("/races/fetch-results", json={"race_name": _PAST_RACE_NAME})
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["count"] == 10
    race = storage_module.find_race(_PAST_RACE_NAME)
    assert race is not None
    assert race["actual_results"] == _FAKE_RESULTS


def test_fetch_results_api_unavailable_returns_404(
    client_with_past_race, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web_server, "_fetch_results", lambda *_: None)
    res = client_with_past_race.post("/races/fetch-results", json={"race_name": _PAST_RACE_NAME})
    assert res.status_code == 404
    assert "not available yet" in res.get_json()["error"]


def test_fetch_results_unknown_race_returns_404(client) -> None:
    res = client.post("/races/fetch-results", json={"race_name": "Fake Grand Prix"})
    assert res.status_code == 404


def test_fetch_results_race_already_has_results_returns_409(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web_server, "_fetch_results", lambda *_: _FAKE_RESULTS)
    # Australian GP already has results in _MINIMAL_DATA
    res = client.post("/races/fetch-results", json={"race_name": "Australian Grand Prix"})
    assert res.status_code == 409


def test_fetch_results_future_race_returns_400(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_server, "_fetch_results", lambda *_: _FAKE_RESULTS)
    # Bahrain GP date is 2026-04-12 — still in the future on test day (2026-04-07)
    res = client.post("/races/fetch-results", json={"race_name": "Bahrain Grand Prix"})
    assert res.status_code == 400
    assert "not happened yet" in res.get_json()["error"]
