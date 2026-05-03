"""External API integration: FastF1 and OpenF1.

IMPORTANT architectural notes (see AGENT_INSTRUCTIONS.md):

1. FastF1 globally monkey-patches ``requests`` with aggressive caching.
   All secondary HTTP calls (OpenF1) MUST use ``urllib.request`` – never
   ``requests`` – to avoid stale data and traceback noise.

2. OpenF1 endpoint order MUST be:
   /meetings  ->  /sessions  ->  /session_result  ->  /drivers
   Using ``meeting_key`` (not ``session_key``) for the drivers endpoint
   prevents null broadcast_name values.

Functions in this module may print progress messages but do NOT call
``save_data`` or mutate shared state – that is the CLI layer's job.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from .models import DriverResult, RaceData

__all__ = [
    "HAS_FASTF1",
    "fetch_fastf1_results",
    "fetch_openf1_results",
    "fetch_results",
    "get_schedule_updates",
]

_log = logging.getLogger(__name__)

try:
    import fastf1

    HAS_FASTF1 = True
    logging.getLogger("fastf1.req").setLevel(logging.CRITICAL)
except ImportError:
    HAS_FASTF1 = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _setup_fastf1_cache() -> None:
    """Ensure the FastF1 cache directory exists and is enabled."""
    cache_dir = os.path.abspath("fastf1_cache")
    os.makedirs(cache_dir, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)


def _fetch_openf1_json(url: str) -> Optional[Union[list[Any], dict[str, Any]]]:
    """Fetch *url* with ``urllib.request`` and return parsed JSON.

    Using urllib bypasses FastF1's global requests-cache monkey-patch.
    Returns ``None`` on any network or parse error.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 points-are-bad/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status != 200:
                return None
            return json.loads(response.read().decode())  # type: ignore[no-any-return]
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
    ) as e:
        _log.warning("Error fetching %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# FastF1
# ---------------------------------------------------------------------------


def fetch_fastf1_results(year: int, race_name: str) -> Optional[list[DriverResult]]:
    """Return the top-10 results for *race_name* from the FastF1 API.

    Each entry is a :class:`~models.DriverResult` dict ``{"abbr": ..., "name": ...}``.
    Returns ``None`` when results are unavailable or FastF1 is not installed.
    """
    if not HAS_FASTF1:
        return None

    _log.info("Fetching official FastF1 data for %s (%s)...", race_name, year)
    _setup_fastf1_cache()
    try:

        session = fastf1.get_session(year, race_name, "R")
        session.load(telemetry=False, laps=False, weather=False)

        if "Position" not in session.results.columns or session.results["Position"].isnull().all():
            _log.info("Official race results not yet available in FastF1 for %s.", race_name)
            return None

        results = session.results.dropna(subset=["Position"]).sort_values(by="Position").head(10)
        drivers: list[DriverResult] = []
        for _, row in results.iterrows():
            first = str(row.get("FirstName", "")).strip()
            last = str(row.get("LastName", "")).strip()
            drivers.append(
                {
                    "abbr": str(row.get("Abbreviation", "")).strip(),
                    "name": f"{first} {last}".strip(),
                }
            )
        return drivers
    except Exception as e:  # noqa: BLE001 — FastF1 raises many undocumented types
        _log.warning("Error fetching FastF1 data: %s", e)
        return None


# ---------------------------------------------------------------------------
# OpenF1
# ---------------------------------------------------------------------------


def fetch_openf1_results(year: int, race_name: str) -> Optional[list[DriverResult]]:
    """Return the top-10 results for *race_name* from the OpenF1 API.

    Follows the required endpoint sequence:
      /meetings -> /sessions -> /session_result -> /drivers (meeting_key)

    Returns ``None`` when results are unavailable.
    """
    _log.info("Attempting to fetch from OpenF1 API for %s (%s)...", race_name, year)
    try:
        # Step 1: resolve meeting key
        meetings = _fetch_openf1_json(f"https://api.openf1.org/v1/meetings?year={year}")
        if not meetings or not isinstance(meetings, list):
            return None

        target_meeting: Optional[dict[str, Any]] = None
        for m in meetings:
            m_name = m.get("meeting_name", "").lower()
            if m_name in race_name.lower() or race_name.lower() in m_name:
                target_meeting = m
                break

        if not target_meeting:
            for m in meetings:
                if (
                    m.get("country_name", "").lower() in race_name.lower()
                    or m.get("location", "").lower() in race_name.lower()
                ):
                    target_meeting = m
                    break

        if not target_meeting:
            _log.warning("Could not find meeting matching '%s' in OpenF1.", race_name)
            return None

        meeting_key = target_meeting["meeting_key"]

        # Step 2: find the Race session
        sessions = _fetch_openf1_json(
            f"https://api.openf1.org/v1/sessions?meeting_key={meeting_key}&session_type=Race"
        )
        if not sessions or (isinstance(sessions, dict) and "detail" in sessions):
            _log.warning(
                "Could not find a Race session for meeting %s.",
                target_meeting.get("meeting_name"),
            )
            return None

        target_session = sessions[0]  # type: ignore[index]
        session_key = target_session["session_key"]
        _log.info(
            "Found OpenF1 session: %s - %s (Key: %s)",
            target_meeting.get("meeting_name"),
            target_session.get("session_name"),
            session_key,
        )

        # Step 3: fetch session results
        res_data = _fetch_openf1_json(
            f"https://api.openf1.org/v1/session_result?session_key={session_key}&position<=10"
        )
        if isinstance(res_data, dict) and "detail" in res_data:
            _log.info("OpenF1 API info: %s", res_data["detail"])
            return None
        if not res_data:
            _log.info("OpenF1 session_results not yet populated for %s.", race_name)
            return None

        sorted_results = sorted(res_data, key=lambda x: x["position"])

        # Step 4: fetch driver metadata via meeting_key (avoids null names)
        drivers_data = _fetch_openf1_json(
            f"https://api.openf1.org/v1/drivers?meeting_key={meeting_key}"
        )

        driver_map: dict[str, dict[str, Any]] = {}
        if isinstance(drivers_data, list):
            for d in drivers_data:
                d_num = str(d.get("driver_number", ""))
                if d.get("broadcast_name") or d.get("full_name") or d_num not in driver_map:
                    driver_map[d_num] = d

        api_results: list[DriverResult] = []
        for res in sorted_results[:10]:
            driver_id = str(res["driver_number"])
            info = driver_map.get(driver_id, {})
            first = (info.get("first_name") or "").strip()
            last = (info.get("last_name") or "").strip()
            name = f"{first} {last}".strip() or str(driver_id)
            api_results.append(
                {
                    "abbr": (info.get("name_acronym") or "").strip(),
                    "name": name,
                }
            )

        return api_results
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        OSError,
    ) as e:
        _log.warning("OpenF1 fetching error: %s", e)
        return None


def fetch_results(year: int, race_name: str) -> Optional[list[DriverResult]]:
    """Try FastF1 first, fall back to OpenF1.  Returns ``None`` if both fail."""
    result = fetch_fastf1_results(year, race_name)
    return result or fetch_openf1_results(year, race_name)


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


def get_schedule_updates(
    existing_races: list[RaceData],
) -> tuple[list[RaceData], list[tuple[RaceData, str]]]:
    """Fetch the current-season schedule and diff it against *existing_races*.

    Returns ``(new_races, date_updates)`` where:
    - *new_races*    – list of new race dicts ready to append to data
    - *date_updates* – list of ``(existing_race_dict, new_date_str)`` pairs

    Does **not** mutate *existing_races* or call ``save_data``.
    Raises ``RuntimeError`` when FastF1 is unavailable.
    """
    if not HAS_FASTF1:
        raise RuntimeError("FastF1 is not installed.")

    year = datetime.datetime.now().year
    _setup_fastf1_cache()

    schedule = fastf1.get_event_schedule(year)
    events = schedule[schedule["EventFormat"] != "testing"]

    new_races: list[RaceData] = []
    date_updates: list[tuple[RaceData, str]] = []

    for _, row in events.iterrows():
        race_name = row.get("EventName")
        if not race_name:
            continue
        event_date = row.get("EventDate")
        date_str = str(event_date.date()) if hasattr(event_date, "date") else ""

        existing = next(
            (r for r in existing_races if r["name"].lower() == race_name.lower()),
            None,
        )

        if existing:
            if date_str and existing.get("date") != date_str:
                date_updates.append((existing, date_str))
        else:
            new_races.append(
                {
                    "name": race_name,
                    "date": date_str,
                    "actual_results": [],
                    "predictions": {},
                }
            )

    return new_races, date_updates
