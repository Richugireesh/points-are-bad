"""Tests for the Flask web server endpoints."""
from __future__ import annotations

import json
import pathlib
from typing import Generator

import pytest

import points_are_bad.storage as storage_module
import web.server as web_server
from web.server import app, limiter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_OPEN_PRED = [
    "verstappen", "norris", "leclerc", "hamilton", "russell",
    "piastri", "antonelli", "gasly", "hadjar", "lawson",
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
                "alice": ["verstappen", "norris", "leclerc", "hamilton",
                          "russell", "piastri", "antonelli", "gasly",
                          "hadjar", "lawson"],
            },
        },
        {
            "name": "Bahrain Grand Prix",
            "date": "2026-04-12",
            "actual_results": [],
            "predictions": {},
        },
    ],
}


@pytest.fixture()
def tmp_data(tmp_path: pathlib.Path) -> pathlib.Path:
    f = tmp_path / "data.json"
    f.write_text(json.dumps(_MINIMAL_DATA, indent=4), encoding="utf-8")
    return f


@pytest.fixture()
def client(
    tmp_data: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Generator:
    # server.py now calls storage.load_data() / storage.save_data(), so patch
    # DATA_FILE on the storage module (the single source of truth).
    monkeypatch.setattr(storage_module, "DATA_FILE", str(tmp_data))
    # flask-limiter v4 sets self.enabled once at init_app time — the config key
    # has no effect after that.  Patch the instance attribute directly so tests
    # making multiple requests to the same endpoint don't trip rate limits.
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

def test_post_prediction_saves_to_file(client, tmp_data: pathlib.Path) -> None:
    res = client.post("/predictions", json={
        "player": "alice",
        "race_name": "Bahrain Grand Prix",
        "prediction": _OPEN_PRED,
    })
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    saved = json.loads(tmp_data.read_text())
    assert saved["races"][1]["predictions"]["alice"] == _OPEN_PRED


def test_post_prediction_bob_independent(client, tmp_data: pathlib.Path) -> None:
    client.post("/predictions", json={
        "player": "alice", "race_name": "Bahrain Grand Prix",
        "prediction": _OPEN_PRED,
    })
    client.post("/predictions", json={
        "player": "bob", "race_name": "Bahrain Grand Prix",
        "prediction": list(reversed(_OPEN_PRED)),
    })
    saved = json.loads(tmp_data.read_text())
    preds = saved["races"][1]["predictions"]
    assert preds["alice"] == _OPEN_PRED
    assert preds["bob"] == list(reversed(_OPEN_PRED))


# ---------------------------------------------------------------------------
# POST /predictions — validation errors
# ---------------------------------------------------------------------------

def test_post_prediction_unknown_player(client) -> None:
    res = client.post("/predictions", json={
        "player": "ghost", "race_name": "Bahrain Grand Prix",
        "prediction": _OPEN_PRED,
    })
    assert res.status_code == 400
    assert "Unknown player" in res.get_json()["error"]


def test_post_prediction_unknown_race(client) -> None:
    res = client.post("/predictions", json={
        "player": "alice", "race_name": "Fake Grand Prix",
        "prediction": _OPEN_PRED,
    })
    assert res.status_code == 400
    assert "Unknown race" in res.get_json()["error"]


def test_post_prediction_race_has_results(client) -> None:
    res = client.post("/predictions", json={
        "player": "alice", "race_name": "Australian Grand Prix",
        "prediction": _OPEN_PRED,
    })
    assert res.status_code == 400
    assert "Results already entered" in res.get_json()["error"]


def test_post_prediction_wrong_length_short(client) -> None:
    res = client.post("/predictions", json={
        "player": "alice", "race_name": "Bahrain Grand Prix",
        "prediction": ["verstappen", "norris"],
    })
    assert res.status_code == 400
    assert "10" in res.get_json()["error"]


def test_post_prediction_wrong_length_long(client) -> None:
    res = client.post("/predictions", json={
        "player": "alice", "race_name": "Bahrain Grand Prix",
        "prediction": _OPEN_PRED + ["colapinto"],
    })
    assert res.status_code == 400


def test_post_prediction_not_a_list(client) -> None:
    res = client.post("/predictions", json={
        "player": "alice", "race_name": "Bahrain Grand Prix",
        "prediction": "verstappen",
    })
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# POST /predictions — duplicate / overwrite
# ---------------------------------------------------------------------------

def test_post_prediction_duplicate_rejected_with_409(client) -> None:
    payload = {"player": "alice", "race_name": "Bahrain Grand Prix",
               "prediction": _OPEN_PRED}
    client.post("/predictions", json=payload)
    res = client.post("/predictions", json=payload)
    assert res.status_code == 409
    assert "already submitted" in res.get_json()["error"]


def test_post_prediction_overwrite_accepted(client, tmp_data: pathlib.Path) -> None:
    new_pred = list(reversed(_OPEN_PRED))
    client.post("/predictions", json={
        "player": "alice", "race_name": "Bahrain Grand Prix",
        "prediction": _OPEN_PRED,
    })
    res = client.post("/predictions", json={
        "player": "alice", "race_name": "Bahrain Grand Prix",
        "prediction": new_pred, "overwrite": True,
    })
    assert res.status_code == 200
    saved = json.loads(tmp_data.read_text())
    assert saved["races"][1]["predictions"]["alice"] == new_pred


# ---------------------------------------------------------------------------
# POST /players
# ---------------------------------------------------------------------------

def test_add_player_happy_path(client, tmp_data: pathlib.Path) -> None:
    res = client.post("/players", json={"name": "charlie"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["name"] == "charlie"

    saved = json.loads(tmp_data.read_text())
    assert "charlie" in saved["players"]


def test_add_player_normalises_to_lowercase(client, tmp_data: pathlib.Path) -> None:
    res = client.post("/players", json={"name": "Charlie"})
    assert res.status_code == 200
    saved = json.loads(tmp_data.read_text())
    assert "charlie" in saved["players"]
    assert "Charlie" not in saved["players"]


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

def test_add_race_happy_path(client, tmp_data: pathlib.Path) -> None:
    res = client.post("/races", json={"name": "Monaco Grand Prix", "date": "2026-05-25"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["name"] == "Monaco Grand Prix"
    saved = json.loads(tmp_data.read_text())
    names = [r["name"] for r in saved["races"]]
    assert "Monaco Grand Prix" in names


def test_add_race_without_date(client, tmp_data: pathlib.Path) -> None:
    res = client.post("/races", json={"name": "TBD Grand Prix"})
    assert res.status_code == 200
    saved = json.loads(tmp_data.read_text())
    race = next(r for r in saved["races"] if r["name"] == "TBD Grand Prix")
    assert race["date"] == ""


def test_add_race_sorted_by_date(client, tmp_data: pathlib.Path) -> None:
    """Races are kept sorted by date after insertion."""
    client.post("/races", json={"name": "Early GP", "date": "2026-01-01"})
    client.post("/races", json={"name": "Late GP", "date": "2099-12-31"})
    saved = json.loads(tmp_data.read_text())
    dates = [r.get("date", "") for r in saved["races"] if r.get("date")]
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

def test_delete_race_removes_from_file(client, tmp_data: pathlib.Path) -> None:
    res = client.delete("/races", json={"race_name": "Bahrain Grand Prix"})
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    saved = json.loads(tmp_data.read_text())
    assert not any(r["name"] == "Bahrain Grand Prix" for r in saved["races"])


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
    {"name": "Max Verstappen",  "abbr": "VER"},
    {"name": "Lando Norris",    "abbr": "NOR"},
    {"name": "Charles Leclerc", "abbr": "LEC"},
    {"name": "Lewis Hamilton",  "abbr": "HAM"},
    {"name": "George Russell",  "abbr": "RUS"},
    {"name": "Oscar Piastri",   "abbr": "PIA"},
    {"name": "Andrea Kimi Antonelli", "abbr": "ANT"},
    {"name": "Pierre Gasly",    "abbr": "GAS"},
    {"name": "Isack Hadjar",    "abbr": "HAD"},
    {"name": "Liam Lawson",     "abbr": "LAW"},
]

# Bahrain GP in _MINIMAL_DATA is 2026-04-12 (future).  These tests need a past
# race with no results, so we patch the data file with a backdated entry.
_PAST_RACE_NAME = "Saudi Arabian Grand Prix"


@pytest.fixture()
def client_with_past_race(
    tmp_data: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Generator:
    """Client fixture that adds a past race with no results to the data file."""
    data = json.loads(tmp_data.read_text())
    data["races"].append({
        "name": _PAST_RACE_NAME,
        "date": "2026-03-15",   # safely in the past
        "actual_results": [],
        "predictions": {},
    })
    tmp_data.write_text(json.dumps(data, indent=4), encoding="utf-8")
    monkeypatch.setattr(storage_module, "DATA_FILE", str(tmp_data))
    monkeypatch.setattr(limiter, "enabled", False)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_fetch_results_saves_to_file(
    client_with_past_race, tmp_data: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web_server, "_fetch_results", lambda *_: _FAKE_RESULTS)
    res = client_with_past_race.post(
        "/races/fetch-results", json={"race_name": _PAST_RACE_NAME}
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["count"] == 10
    saved = json.loads(tmp_data.read_text())
    race = next(r for r in saved["races"] if r["name"] == _PAST_RACE_NAME)
    assert race["actual_results"] == _FAKE_RESULTS


def test_fetch_results_api_unavailable_returns_404(
    client_with_past_race, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web_server, "_fetch_results", lambda *_: None)
    res = client_with_past_race.post(
        "/races/fetch-results", json={"race_name": _PAST_RACE_NAME}
    )
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


def test_fetch_results_future_race_returns_400(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web_server, "_fetch_results", lambda *_: _FAKE_RESULTS)
    # Bahrain GP date is 2026-04-12 — still in the future on test day (2026-04-07)
    res = client.post("/races/fetch-results", json={"race_name": "Bahrain Grand Prix"})
    assert res.status_code == 400
    assert "not happened yet" in res.get_json()["error"]
