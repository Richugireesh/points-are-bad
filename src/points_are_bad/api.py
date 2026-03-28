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

try:
    import fastf1  # type: ignore[import-untyped]

    HAS_FASTF1 = True
    logging.getLogger("fastf1.req").setLevel(logging.CRITICAL)
except ImportError:
    HAS_FASTF1 = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_openf1_json(url: str) -> "list | dict | None":
    """Fetch *url* with ``urllib.request`` and return parsed JSON.

    Using urllib bypasses FastF1's global requests-cache monkey-patch.
    Returns ``None`` on any network or parse error.
    """
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 points-are-bad/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status != 200:
                return None
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# FastF1
# ---------------------------------------------------------------------------

def fetch_fastf1_results(year: int, race_name: str) -> "list[dict] | None":
    """Return the top-10 results for *race_name* from the FastF1 API.

    Each entry is a slim dict ``{"abbr": "RUS", "name": "George Russell"}``.
    Returns ``None`` when results are unavailable or FastF1 is not installed.
    """
    if not HAS_FASTF1:
        return None

    print(f"\nFetching official FastF1 data for {race_name} ({year})...")
    try:
        cache_dir = os.path.abspath("fastf1_cache")
        os.makedirs(cache_dir, exist_ok=True)
        fastf1.Cache.enable_cache(cache_dir)

        session = fastf1.get_session(year, race_name, "R")
        session.load(telemetry=False, laps=False, weather=False)

        if (
            "Position" not in session.results.columns
            or session.results["Position"].isnull().all()
        ):
            print(
                "\n[!] Official race results are not yet available for this"
                " session in FastF1."
            )
            return None

        results = (
            session.results.dropna(subset=["Position"])
            .sort_values(by="Position")
            .head(10)
        )
        drivers = []
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
    except Exception as e:
        print(f"Error fetching FastF1 data: {e}")
        return None


# ---------------------------------------------------------------------------
# OpenF1
# ---------------------------------------------------------------------------

def fetch_openf1_results(year: int, race_name: str) -> "list[dict] | None":
    """Return the top-10 results for *race_name* from the OpenF1 API.

    Follows the required endpoint sequence:
      /meetings -> /sessions -> /session_result -> /drivers (meeting_key)

    Returns ``None`` when results are unavailable.
    """
    print(f"\nAttempting to fetch from OpenF1 API for {race_name} ({year})...")
    try:
        # Step 1: resolve meeting key
        meetings = _fetch_openf1_json(
            f"https://api.openf1.org/v1/meetings?year={year}"
        )
        if not meetings:
            return None

        target_meeting = None
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
            print(f"[!] Could not find meeting matching '{race_name}' in OpenF1.")
            return None

        meeting_key = target_meeting["meeting_key"]

        # Step 2: find the Race session
        sessions = _fetch_openf1_json(
            f"https://api.openf1.org/v1/sessions"
            f"?meeting_key={meeting_key}&session_type=Race"
        )
        if not sessions or (isinstance(sessions, dict) and "detail" in sessions):
            print(
                f"[!] Could not find a Race session for meeting"
                f" {target_meeting.get('meeting_name')}."
            )
            return None

        target_session = sessions[0]
        session_key = target_session["session_key"]
        print(
            f"Found OpenF1 session: {target_meeting.get('meeting_name')}"
            f" - {target_session.get('session_name')} (Key: {session_key})"
        )

        # Step 3: fetch session results
        res_data = _fetch_openf1_json(
            f"https://api.openf1.org/v1/session_result"
            f"?session_key={session_key}&position<=10"
        )
        if isinstance(res_data, dict) and "detail" in res_data:
            print(f"[!] OpenF1 API Info: {res_data['detail']}")
            return None
        if not res_data:
            print("[!] OpenF1 does not have session_results populated yet.")
            return None

        sorted_results = sorted(res_data, key=lambda x: x["position"])

        # Step 4: fetch driver metadata via meeting_key (avoids null names)
        drivers_data = _fetch_openf1_json(
            f"https://api.openf1.org/v1/drivers?meeting_key={meeting_key}"
        )

        driver_map: dict[str, dict] = {}
        if isinstance(drivers_data, list):
            for d in drivers_data:
                d_num = str(d.get("driver_number", ""))
                if (
                    d.get("broadcast_name")
                    or d.get("full_name")
                    or d_num not in driver_map
                ):
                    driver_map[d_num] = d

        results = []
        for res in sorted_results[:10]:
            driver_id = str(res["driver_number"])
            info = driver_map.get(driver_id, {})
            first = (info.get("first_name") or "").strip()
            last = (info.get("last_name") or "").strip()
            name = f"{first} {last}".strip() or str(driver_id)
            results.append(
                {
                    "abbr": (info.get("name_acronym") or "").strip(),
                    "name": name,
                }
            )

        return results
    except Exception as e:
        print(f"OpenF1 fetching error: {e}")
        return None


def fetch_results(year: int, race_name: str) -> "list[dict] | None":
    """Try FastF1 first, fall back to OpenF1.  Returns ``None`` if both fail."""
    result = fetch_fastf1_results(year, race_name) if HAS_FASTF1 else None
    return result or fetch_openf1_results(year, race_name)


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def get_schedule_updates(
    existing_races: list[dict],
) -> "tuple[list[dict], list[tuple[dict, str]]]":
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
    cache_dir = os.path.abspath("fastf1_cache")
    os.makedirs(cache_dir, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)

    schedule = fastf1.get_event_schedule(year)
    events = schedule[schedule["EventFormat"] != "testing"]

    new_races: list[dict] = []
    date_updates: list[tuple[dict, str]] = []

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
            if not existing.get("date") and date_str:
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
