#!/usr/bin/env python3
"""Web server for the Points Are Bad dashboard.

Usage:
    uv run web/server.py            # development (Flask dev server)
    gunicorn -c gunicorn.conf.py web.server:app   # production

Environment variables:
    PORT              TCP port to listen on (default: 5001)
    POINTS_DATA_FILE  Override path to the data file (SQLite database)
    API_TOKEN         Shared secret required for all write endpoints.
                      If unset, writes are open (suitable only for local/dev use).
    RATELIMIT_ENABLED Set to "false" to disable rate limiting (default: true).
"""

from __future__ import annotations

import datetime
import functools
import hmac
import json
import logging
import os
import pathlib
import sys
from typing import Callable, TypeVar, Union

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# The `sys.path` manipulation below is required so that `uv run web/server.py`
# works without a full editable install (e.g. in Docker, where Gunicorn imports
# `web.server:app` directly).  When the package is installed via `pip install -e`,
# the already-installed version takes precedence.
_SRC = pathlib.Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from points_are_bad.api import fetch_results as _fetch_results
from points_are_bad.drivers import ROSTER as _ROSTER
from points_are_bad.scoring import ALIASES
from points_are_bad.storage import (
    add_player as _add_player,
    add_race as _add_race,
    find_player as _find_player,
    find_race as _find_race,
    load_data,
    remove_player as _remove_player,
    remove_race as _remove_race,
    set_prediction as _set_prediction,
    set_results as _set_results,
)

_VALID_DRIVER_KEYS: frozenset[str] = frozenset(d["key"] for d in _ROSTER)

ROOT = pathlib.Path(__file__).parent.parent
WEB_DIR = pathlib.Path(__file__).parent

# ---------------------------------------------------------------------------
# Logging — structured single-line format; Flask's werkzeug logger is separate
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("points_are_bad.web")

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder=None)

# Hard cap on incoming request bodies — protects against memory exhaustion
# before any application code runs.  16 KB is generous for any valid request.
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # 16 KB

# ---------------------------------------------------------------------------
# Rate limiting — flask-limiter automatically disables limits when
# so the test suite is unaffected.  Set RATELIMIT_ENABLED=false to opt out in dev.
# ---------------------------------------------------------------------------
_rate_limit_enabled = os.environ.get("RATELIMIT_ENABLED", "true").lower() != "false"
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    enabled=_rate_limit_enabled,
    storage_uri="memory://",
    # Broad defaults for read endpoints; write routes set their own stricter limits.
    default_limits=["300 per hour", "60 per minute"],
)

_RouteReturn = Union[Response, tuple[Response, int]]
_F = TypeVar("_F", bound=Callable[..., _RouteReturn])

# Shared secret for write endpoints.  None → open (dev only).
_API_TOKEN: str | None = os.environ.get("API_TOKEN") or None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _err(msg: str, code: int = 400) -> tuple[Response, int]:
    return jsonify({"error": msg}), code  # type: ignore[return-value]


def _validate_date(value: str) -> str | None:
    """Return *value* unchanged if it is a valid YYYY-MM-DD string, else ``None``."""
    try:
        datetime.date.fromisoformat(value)
        return value
    except (ValueError, TypeError):
        return None


def _require_token(fn: _F) -> _F:
    """Decorator: reject requests missing the correct Bearer token when API_TOKEN is set."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        if _API_TOKEN is not None:
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or not hmac.compare_digest(
                auth[len("Bearer ") :], _API_TOKEN
            ):
                log.warning("Unauthorized write attempt from %s", request.remote_addr)
                return _err("Unauthorized", 401)
        return fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Global error handlers — always return JSON, never HTML
# ---------------------------------------------------------------------------


@app.errorhandler(404)
def _not_found(e: Exception) -> tuple[Response, int]:
    return _err("Not found", 404)


@app.errorhandler(405)
def _method_not_allowed(e: Exception) -> tuple[Response, int]:
    return _err("Method not allowed", 405)


@app.errorhandler(413)
def _too_large(e: Exception) -> tuple[Response, int]:
    return _err("Request body too large (max 16 KB)", 413)


@app.errorhandler(429)
def _rate_limited(e: Exception) -> tuple[Response, int]:
    return _err("Too many requests — slow down", 429)


@app.errorhandler(500)
def _internal(e: Exception) -> tuple[Response, int]:
    log.exception("Unhandled exception: %s", e)
    return _err("Internal server error", 500)


# ---------------------------------------------------------------------------
# Security headers — added to every response
# ---------------------------------------------------------------------------


@app.after_request
def _security_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    )
    return response


# ── Routes ──────────────────────────────────────────────────────────────────


@app.route("/")
def index() -> Response:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    token_line = f"<script>const _API_TOKEN = {json.dumps(_API_TOKEN)};</script>"
    html = html.replace("</head>", f"  {token_line}\n</head>", 1)
    return Response(html, mimetype="text/html")


@app.route("/data")
def data() -> Response:
    game = load_data()
    return jsonify(game)


@app.route("/aliases")
def aliases() -> Response:
    """Return the driver alias table from scoring.py so the frontend stays in sync."""
    return jsonify(ALIASES)


@app.route("/predictions", methods=["POST"])
@limiter.limit("60 per hour; 10 per minute")
@_require_token
def save_prediction() -> _RouteReturn:
    body = request.get_json(force=True, silent=True) or {}
    player: str = str(body.get("player", "")).strip().lower()
    race_name: str = str(body.get("race_name", "")).strip()
    prediction = body.get("prediction", [])
    overwrite: bool = bool(body.get("overwrite", False))

    if not _find_player(player):
        return _err(f"Unknown player: {player}")

    race = _find_race(race_name)
    if race is None:
        return _err(f"Unknown race: {race_name}")

    if race.get("actual_results"):
        return _err("Results already entered for this race — no changes allowed")

    race_date = race.get("date", "")
    if race_date and race_date < datetime.date.today().isoformat():
        return _err("Cannot submit prediction for a race that has already passed")

    if not isinstance(prediction, list) or len(prediction) != 10:
        return _err("Prediction must be a list of exactly 10 driver keys")

    invalid = [k for k in prediction if k not in _VALID_DRIVER_KEYS]
    if invalid:
        return _err(f"Unknown driver keys: {', '.join(invalid)}")

    existing_preds = race.get("predictions", {}).get(player)
    if existing_preds and not overwrite:
        return _err("Prediction already submitted for this race", 409)

    try:
        _set_prediction(race_name, player, prediction)
    except Exception as e:
        if "Unknown race" in str(e):
            return _err(f"Unknown race: {race_name}")
        raise

    log.info("Prediction saved: player=%s race=%r", player, race_name)
    return jsonify({"ok": True})


@app.route("/results", methods=["POST"])
@limiter.limit("30 per hour; 5 per minute")
@_require_token
def save_results() -> _RouteReturn:
    body = request.get_json(force=True, silent=True) or {}
    race_name: str = str(body.get("race_name", "")).strip()
    results = body.get("results", [])

    if not isinstance(results, list) or len(results) != 10:
        return _err("Results must be a list of exactly 10 entries")

    for entry in results:
        if (
            not isinstance(entry, dict)
            or not str(entry.get("name", "")).strip()
            or not str(entry.get("abbr", "")).strip()
        ):
            return _err("Each result entry must have non-empty 'name' and 'abbr' fields")

    race = _find_race(race_name)
    if race is None:
        return _err(f"Unknown race: {race_name}")

    if race.get("actual_results"):
        return _err("Results already entered for this race", 409)

    cleaned = [
        {"name": str(e["name"]).strip(), "abbr": str(e["abbr"]).strip().upper()} for e in results
    ]
    try:
        _set_results(race_name, cleaned)
    except Exception as e:
        if "Unknown race" in str(e):
            return _err(f"Unknown race: {race_name}")
        raise

    log.info("Results saved: race=%r", race_name)
    return jsonify({"ok": True})


@app.route("/races/fetch-results", methods=["POST"])
@limiter.limit("10 per hour; 2 per minute")
@_require_token
def fetch_race_results() -> _RouteReturn:
    body = request.get_json(force=True, silent=True) or {}
    race_name: str = str(body.get("race_name", "")).strip()

    if not race_name:
        return _err("race_name is required")

    race = _find_race(race_name)
    if race is None:
        return _err(f"Unknown race: {race_name}", 404)

    if race.get("actual_results"):
        return _err("Results already entered for this race", 409)

    race_date = race.get("date", "")
    if race_date and race_date > datetime.date.today().isoformat():
        return _err("Race has not happened yet", 400)

    year = int(race_date[:4]) if race_date else datetime.date.today().year
    log.info("Fetching results for %r (%s)...", race_name, year)

    results = _fetch_results(year, race_name)
    if not results:
        return _err("Results not available yet — try again after the race", 404)

    try:
        _set_results(race_name, results)
    except Exception as e:
        if "Unknown race" in str(e):
            return _err(f"Unknown race: {race_name}", 404)
        raise

    log.info("Auto-fetched results for %r (%d drivers)", race_name, len(results))
    return jsonify({"ok": True, "count": len(results)})


@app.route("/races", methods=["POST"])
@limiter.limit("20 per hour; 5 per minute")
@_require_token
def add_race() -> _RouteReturn:
    body = request.get_json(force=True, silent=True) or {}
    name: str = str(body.get("name", "")).strip()
    date_str: str = str(body.get("date", "")).strip()

    if not name:
        return _err("Race name is required")
    if len(name) > 100:
        return _err("Race name too long (max 100 characters)")

    if date_str and _validate_date(date_str) is None:
        return _err("Invalid date format — use YYYY-MM-DD")

    try:
        _add_race(name, date_str)
    except Exception as e:
        if "already exists" in str(e):
            return _err(f"Race '{name}' already exists", 409)
        raise

    log.info("Race added: %r (%s)", name, date_str or "no date")
    return jsonify({"ok": True, "name": name})


@app.route("/races", methods=["DELETE"])
@limiter.limit("20 per hour; 5 per minute")
@_require_token
def delete_race() -> _RouteReturn:
    body = request.get_json(force=True, silent=True) or {}
    race_name: str = str(body.get("race_name", "")).strip()

    if not race_name:
        return _err("race_name is required")

    race = _find_race(race_name)
    if race is None:
        return _err(f"Unknown race: {race_name}", 404)

    if race.get("actual_results"):
        return _err("Cannot remove a race that already has results entered", 409)

    try:
        _remove_race(race_name)
    except Exception as e:
        if "Unknown race" in str(e):
            return _err(f"Unknown race: {race_name}", 404)
        raise

    log.info("Race removed: %r", race_name)
    return jsonify({"ok": True})


@app.route("/players", methods=["POST"])
@limiter.limit("20 per hour; 5 per minute")
@_require_token
def add_player() -> _RouteReturn:
    body = request.get_json(force=True, silent=True) or {}
    name: str = str(body.get("name", "")).strip().lower()

    if not name:
        return _err("Player name is required")
    if len(name) > 30:
        return _err("Player name too long (max 30 characters)")

    try:
        _add_player(name)
    except Exception as e:
        if "already exists" in str(e):
            return _err(f"Player '{name}' already exists", 409)
        raise

    log.info("Player added: %s", name)
    return jsonify({"ok": True, "name": name})


@app.route("/players", methods=["DELETE"])
@limiter.limit("20 per hour; 5 per minute")
@_require_token
def remove_player() -> _RouteReturn:
    body = request.get_json(force=True, silent=True) or {}
    name: str = str(body.get("name", "")).strip().lower()

    if not name:
        return _err("Player name is required")

    try:
        _remove_player(name)
    except Exception as e:
        if "Unknown player" in str(e):
            return _err(f"Unknown player: {name}", 404)
        raise

    log.info("Player removed: %s", name)
    return jsonify({"ok": True})


# ── Entry point ─────────────────────────────────────────────────────────────


def run() -> None:
    port = int(os.environ.get("PORT", "5001"))
    print(f"\n  Points Are Bad dashboard → http://localhost:{port}\n")
    if _API_TOKEN is None:
        log.warning("API_TOKEN not set — write endpoints are unauthenticated")
    app.run(debug=False, port=port, host="0.0.0.0")


if __name__ == "__main__":
    run()
