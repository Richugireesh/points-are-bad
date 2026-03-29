"""Tests for points_are_bad.api.

Mocks all external I/O (urllib.request, fastf1) so no network calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import points_are_bad.api as api_mod
from points_are_bad.api import (
    _fetch_openf1_json,
    fetch_openf1_results,
    fetch_results,
    get_schedule_updates,
)

# ---------------------------------------------------------------------------
# _fetch_openf1_json
# ---------------------------------------------------------------------------


def _make_urlopen_response(data: object, status: int = 200) -> MagicMock:
    """Build a mock context-manager response for urllib.request.urlopen."""
    body = json.dumps(data).encode()
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestFetchOpenF1Json:
    def test_returns_parsed_json_on_success(self):
        payload = [{"key": "value"}]
        with patch("urllib.request.urlopen", return_value=_make_urlopen_response(payload)):
            result = _fetch_openf1_json("https://example.com/data")
        assert result == payload

    def test_returns_none_on_non_200(self):
        with patch("urllib.request.urlopen", return_value=_make_urlopen_response({}, status=404)):
            result = _fetch_openf1_json("https://example.com/data")
        assert result is None

    def test_returns_none_on_url_error(self):
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            result = _fetch_openf1_json("https://example.com/data")
        assert result is None

    def test_returns_none_on_bad_json(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"not valid json {"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _fetch_openf1_json("https://example.com/data")
        assert result is None

    def test_returns_none_on_timeout(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = _fetch_openf1_json("https://example.com/data")
        assert result is None


# ---------------------------------------------------------------------------
# fetch_results — dispatch logic
# ---------------------------------------------------------------------------


class TestFetchResults:
    def test_returns_none_when_fastf1_absent(self, monkeypatch):
        monkeypatch.setattr(api_mod, "HAS_FASTF1", False)
        with patch.object(api_mod, "fetch_openf1_results", return_value=None):
            result = fetch_results(2026, "Australian Grand Prix")
        assert result is None

    def test_uses_fastf1_when_available(self, monkeypatch):
        expected = [{"abbr": "VER", "name": "Max Verstappen"}]
        monkeypatch.setattr(api_mod, "HAS_FASTF1", True)
        with patch.object(api_mod, "fetch_fastf1_results", return_value=expected):
            result = fetch_results(2026, "Australian Grand Prix")
        assert result == expected

    def test_falls_back_to_openf1_when_fastf1_returns_none(self, monkeypatch):
        openf1_result = [{"abbr": "NOR", "name": "Lando Norris"}]
        monkeypatch.setattr(api_mod, "HAS_FASTF1", True)
        with (
            patch.object(api_mod, "fetch_fastf1_results", return_value=None),
            patch.object(api_mod, "fetch_openf1_results", return_value=openf1_result),
        ):
            result = fetch_results(2026, "Australian Grand Prix")
        assert result == openf1_result


# ---------------------------------------------------------------------------
# fetch_openf1_results — integration flow (all helpers mocked)
# ---------------------------------------------------------------------------

_MEETING = [
    {
        "meeting_key": 1234,
        "meeting_name": "Australian Grand Prix",
        "country_name": "Australia",
        "location": "Melbourne",
    }
]
_SESSIONS = [{"session_key": 9999, "session_name": "Race", "session_type": "Race"}]
_SESSION_RESULTS = [
    {"position": 1, "driver_number": "1"},
    {"position": 2, "driver_number": "4"},
]
_DRIVERS = [
    {
        "driver_number": "1",
        "broadcast_name": "M VERSTAPPEN",
        "first_name": "Max",
        "last_name": "Verstappen",
        "name_acronym": "VER",
    },
    {
        "driver_number": "4",
        "broadcast_name": "L NORRIS",
        "first_name": "Lando",
        "last_name": "Norris",
        "name_acronym": "NOR",
    },
]


class TestFetchOpenF1Results:
    def _mock_helper(self, responses: list) -> patch:
        """Patch _fetch_openf1_json to return values in sequence."""
        return patch.object(api_mod, "_fetch_openf1_json", side_effect=responses)

    def test_returns_top2_on_success(self):
        with self._mock_helper([_MEETING, _SESSIONS, _SESSION_RESULTS, _DRIVERS]):
            result = fetch_openf1_results(2026, "Australian Grand Prix")
        assert result is not None
        assert len(result) == 2
        assert result[0]["abbr"] == "VER"
        assert result[1]["abbr"] == "NOR"

    def test_returns_none_when_meetings_empty(self):
        with self._mock_helper([[], None, None, None]):
            result = fetch_openf1_results(2026, "Australian Grand Prix")
        assert result is None

    def test_returns_none_when_no_matching_meeting(self):
        other_meeting = [
            {
                "meeting_key": 1,
                "meeting_name": "Bahrain GP",
                "country_name": "Bahrain",
                "location": "Sakhir",
            }  # noqa: E501
        ]
        with self._mock_helper([other_meeting, None, None, None]):
            result = fetch_openf1_results(2026, "Australian Grand Prix")
        assert result is None

    def test_returns_none_when_sessions_unavailable(self):
        no_sessions = {"detail": "Not found"}
        with self._mock_helper([_MEETING, no_sessions, None, None]):
            result = fetch_openf1_results(2026, "Australian Grand Prix")
        assert result is None

    def test_returns_none_when_session_results_empty(self):
        with self._mock_helper([_MEETING, _SESSIONS, [], None]):
            result = fetch_openf1_results(2026, "Australian Grand Prix")
        assert result is None

    def test_returns_none_when_session_results_detail_error(self):
        error_resp = {"detail": "No data yet"}
        with self._mock_helper([_MEETING, _SESSIONS, error_resp, None]):
            result = fetch_openf1_results(2026, "Australian Grand Prix")
        assert result is None

    def test_matches_by_country_name_fallback(self):
        # Meeting name doesn't match, but country_name does
        country_meeting = [
            {
                "meeting_key": 1234,
                "meeting_name": "Round 3",
                "country_name": "Australia",
                "location": "Melbourne",
            }  # noqa: E501
        ]
        with self._mock_helper([country_meeting, _SESSIONS, _SESSION_RESULTS, _DRIVERS]):
            result = fetch_openf1_results(2026, "Australian Grand Prix")
        assert result is not None

    def test_matches_by_location_fallback(self):
        # Neither name nor country matches, but location does
        location_meeting = [
            {
                "meeting_key": 1234,
                "meeting_name": "Round 3",
                "country_name": "AUS",
                "location": "Melbourne",
            }  # noqa: E501
        ]
        with self._mock_helper([location_meeting, _SESSIONS, _SESSION_RESULTS, _DRIVERS]):
            result = fetch_openf1_results(2026, "Melbourne Grand Prix")
        assert result is not None

    def test_returns_none_on_exception_in_fetch(self):
        # Trigger a KeyError by returning a session with no session_key
        bad_session = [{"session_name": "Race"}]  # missing session_key
        with self._mock_helper([_MEETING, bad_session, None, None]):
            result = fetch_openf1_results(2026, "Australian Grand Prix")
        assert result is None

    def test_driver_fallback_when_no_name(self):
        nameless_driver = [
            {
                "driver_number": "1",
                "broadcast_name": None,
                "first_name": None,
                "last_name": None,
                "name_acronym": "",
            }  # noqa: E501
        ]
        with self._mock_helper([_MEETING, _SESSIONS, _SESSION_RESULTS[:1], nameless_driver]):
            result = fetch_openf1_results(2026, "Australian Grand Prix")
        assert result is not None
        # Name falls back to driver_number string
        assert result[0]["name"] == "1"


# ---------------------------------------------------------------------------
# get_schedule_updates
# ---------------------------------------------------------------------------


class TestGetScheduleUpdates:
    def test_raises_when_fastf1_absent(self, monkeypatch):
        monkeypatch.setattr(api_mod, "HAS_FASTF1", False)
        with pytest.raises(RuntimeError, match="FastF1 is not installed"):
            get_schedule_updates([])

    def test_skips_events_with_no_name(self, monkeypatch):
        """Rows with no EventName (pre-season testing) are skipped."""
        monkeypatch.setattr(api_mod, "HAS_FASTF1", True)
        import pandas as pd

        schedule = pd.DataFrame(
            [
                {
                    "EventName": None,
                    "EventDate": pd.Timestamp("2026-02-15"),
                    "EventFormat": "testing",
                },  # noqa: E501
                {
                    "EventName": "Bahrain Grand Prix",
                    "EventDate": pd.Timestamp("2026-03-01"),
                    "EventFormat": "conventional",
                },  # noqa: E501
            ]
        )
        mock_fastf1 = MagicMock()
        mock_fastf1.get_event_schedule.return_value = schedule
        mock_fastf1.Cache.enable_cache = MagicMock()
        monkeypatch.setattr(api_mod, "fastf1", mock_fastf1)

        new_races, _ = get_schedule_updates([])
        # testing row is filtered by EventFormat != "testing"; None-name row skipped
        assert all(r["name"] for r in new_races)

    def test_returns_new_races_and_date_updates(self, monkeypatch):
        """Verify that new events are classified as new_races and
        existing events with no date trigger date_updates."""

        monkeypatch.setattr(api_mod, "HAS_FASTF1", True)

        # Build a minimal fake schedule DataFrame
        import pandas as pd

        schedule = pd.DataFrame(
            [
                {
                    "EventName": "Bahrain Grand Prix",
                    "EventDate": pd.Timestamp("2026-03-01"),
                    "EventFormat": "conventional",
                },  # noqa: E501
                {
                    "EventName": "Saudi Arabian Grand Prix",
                    "EventDate": pd.Timestamp("2026-03-09"),
                    "EventFormat": "conventional",
                },  # noqa: E501
            ]
        )
        mock_fastf1 = MagicMock()
        mock_fastf1.get_event_schedule.return_value = schedule
        mock_fastf1.Cache.enable_cache = MagicMock()

        monkeypatch.setattr(api_mod, "fastf1", mock_fastf1)

        existing = [
            {"name": "Bahrain Grand Prix", "date": "", "actual_results": [], "predictions": {}}
        ]  # noqa: E501
        new_races, date_updates = get_schedule_updates(existing)

        assert len(new_races) == 1
        assert new_races[0]["name"] == "Saudi Arabian Grand Prix"

        assert len(date_updates) == 1
        assert date_updates[0][1] == "2026-03-01"
