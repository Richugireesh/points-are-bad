"""Core game-scoring logic.

Rules:
  - Perfect match at a position  ->  0 points
  - Mismatch at a position       -> +1 point
  - Missing prediction for a race -> +10 points (applied by the caller)

This module has no I/O or external-API dependencies and is fully unit-testable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .models import DriverResult, GameData

    _ActualEntry = Union[DriverResult, str]  # str kept for legacy callers only

__all__ = [
    "ALIASES",
    "calculate_player_points_for_race",
    "calculate_season_standings",
    "calculate_str_equality",
    "score_position",
]

# ---------------------------------------------------------------------------
# Driver alias table
# Maps common shorthand / nicknames -> canonical last-name fragment used for
# substring matching.  Kept at module level so it is constructed once, not on
# every scoring call.
# ---------------------------------------------------------------------------
ALIASES: dict[str, str] = {
    # McLaren
    "nor": "norris",
    "pia": "piastri",
    # Ferrari
    "lec": "leclerc",
    "ham": "hamilton",
    # Mercedes
    "rus": "russell",
    "kimi": "antonelli",
    # Red Bull
    "ver": "verstappen",
    "max": "verstappen",
    "hadj": "hadjar",
    "had": "hadjar",
    # Racing Bulls
    "law": "lawson",
    "lind": "lindblad",
    "linblad": "lindblad",
    "lin": "lindblad",
    # Aston Martin
    "alo": "alonso",
    "str": "stroll",
    # Williams
    "sai": "sainz",
    "alb": "albon",
    # Alpine
    "gas": "gasly",
    "col": "colapinto",
    # Haas
    "oco": "ocon",
    "bea": "bearman",
    "ollie": "bearman",
    # Audi
    "hul": "hulkenberg",
    "bor": "bortoleto",
    "gabby": "bortoleto",
    "gab": "bortoleto",
    # Cadillac
    "per": "perez",
    "checo": "perez",
    "bot": "bottas",
}

# Translation table that strips hidden Unicode formatting characters that can
# sneak in when users paste text from messaging apps.
_HIDDEN_CHARS = str.maketrans("", "", "\u2060\u200b")


def _normalize(s: str) -> str:
    """Lowercase, strip whitespace + hidden chars, then resolve aliases."""
    s = str(s).strip().lower().translate(_HIDDEN_CHARS)
    return ALIASES.get(s, s)


def calculate_str_equality(prediction: str, actual: _ActualEntry) -> bool:
    """Return ``True`` if *prediction* matches *actual*.

    *actual* may be:
      - a dict with keys ``abbr`` / ``name`` (stored :class:`~models.DriverResult`)
      - a dict with keys ``BroadcastName`` / ``FirstName`` / ``LastName`` /
        ``Abbreviation`` (FastF1 / OpenF1 result — passed directly before storage)
      - a plain string (legacy; normalised to dicts by storage._migrate on load)

    Matching is case-insensitive and alias-aware.  A substring match on
    normalised values is accepted (e.g. "perez" matches "S PEREZ").
    """
    p = _normalize(prediction)

    if isinstance(actual, dict):
        for val in actual.values():
            if not val:
                continue
            v = _normalize(str(val))
            if p == v or (v and p in v):
                return True
        return False

    # Plain-string path: only reached for unsaved in-memory results or tests.
    b = _normalize(actual)
    return p == b or bool(b and p in b)


def score_position(
    pred: str | None,
    actual_entry: _ActualEntry | None,
) -> int:
    """Return 0 (match) or 1 (mismatch) for one finishing position.

    Both arguments being ``None`` means neither player nor results have an
    entry for this position – no comparison is possible, so 0 is returned.
    One argument being ``None`` while the other has a value counts as a
    mismatch (+1).
    """
    if pred is None and actual_entry is None:
        return 0
    if pred is None or actual_entry is None:
        return 1
    return 0 if calculate_str_equality(pred, actual_entry) else 1


def calculate_player_points_for_race(
    prediction: Sequence[str],
    actual: Sequence[_ActualEntry],
) -> int:
    """Total points for one player in one race.

    Iterates over all 10 positions (or however many exist in either list),
    using :func:`score_position` as the single source of truth so that any
    caller – summary display, per-position breakdown, season standings –
    always produces the same number.

    The +10 missing-prediction penalty is the **caller's responsibility**
    (apply it when a player has no prediction entry at all for a race).
    """
    n = max(len(prediction), len(actual), 10)
    return sum(
        score_position(
            prediction[i] if i < len(prediction) else None,
            actual[i] if i < len(actual) else None,
        )
        for i in range(n)
    )


def calculate_season_standings(data: GameData) -> tuple[dict[str, int], int]:
    """Return ``(player -> total_points, races_with_results_count)``.

    Applies the +10 missing-prediction penalty for every race that has
    actual results but no prediction from a given player.
    """
    scores: dict[str, int] = {p: 0 for p in data["players"]}
    counted = 0

    for race in data["races"]:
        if not race["actual_results"]:
            continue
        counted += 1
        for player in data["players"]:
            if player in race["predictions"]:
                scores[player] += calculate_player_points_for_race(
                    race["predictions"][player], race["actual_results"]
                )
            else:
                scores[player] += 10  # missing-prediction penalty

    return scores, counted
