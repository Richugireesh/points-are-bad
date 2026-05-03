"""Current F1 driver roster.

Update this list at the start of each season or when a substitute driver
races.  The ``key`` field is the canonical lowercase last name stored in
prediction lists — it must match what ``scoring._normalize`` resolves to so
that predictions made via driver-select score correctly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .models import DriverInfo

__all__ = ["ROSTER", "by_abbr", "by_key"]

# ---------------------------------------------------------------------------
# 2026 F1 driver roster
# ---------------------------------------------------------------------------

ROSTER: list[DriverInfo] = [
    # McLaren
    {"abbr": "NOR", "name": "Lando Norris", "team": "McLaren", "key": "norris"},
    {"abbr": "PIA", "name": "Oscar Piastri", "team": "McLaren", "key": "piastri"},
    # Ferrari
    {"abbr": "LEC", "name": "Charles Leclerc", "team": "Ferrari", "key": "leclerc"},
    {"abbr": "HAM", "name": "Lewis Hamilton", "team": "Ferrari", "key": "hamilton"},
    # Mercedes
    {"abbr": "RUS", "name": "George Russell", "team": "Mercedes", "key": "russell"},
    {"abbr": "ANT", "name": "Kimi Antonelli", "team": "Mercedes", "key": "antonelli"},
    # Red Bull
    {"abbr": "VER", "name": "Max Verstappen", "team": "Red Bull", "key": "verstappen"},
    {"abbr": "HAD", "name": "Isack Hadjar", "team": "Red Bull", "key": "hadjar"},
    # Racing Bulls
    {"abbr": "LAW", "name": "Liam Lawson", "team": "Racing Bulls", "key": "lawson"},
    {"abbr": "LIN", "name": "Arvid Lindblad", "team": "Racing Bulls", "key": "lindblad"},
    # Aston Martin
    {"abbr": "ALO", "name": "Fernando Alonso", "team": "Aston Martin", "key": "alonso"},
    {"abbr": "STR", "name": "Lance Stroll", "team": "Aston Martin", "key": "stroll"},
    # Williams
    {"abbr": "SAI", "name": "Carlos Sainz", "team": "Williams", "key": "sainz"},
    {"abbr": "ALB", "name": "Alexander Albon", "team": "Williams", "key": "albon"},
    # Alpine
    {"abbr": "GAS", "name": "Pierre Gasly", "team": "Alpine", "key": "gasly"},
    {"abbr": "COL", "name": "Franco Colapinto", "team": "Alpine", "key": "colapinto"},
    # Haas
    {"abbr": "OCO", "name": "Esteban Ocon", "team": "Haas", "key": "ocon"},
    {"abbr": "BEA", "name": "Oliver Bearman", "team": "Haas", "key": "bearman"},
    # Audi
    {"abbr": "HUL", "name": "Nico Hulkenberg", "team": "Audi", "key": "hulkenberg"},
    {"abbr": "BOR", "name": "Gabriel Bortoleto", "team": "Audi", "key": "bortoleto"},
    # Cadillac (new constructor 2026)
    {"abbr": "PER", "name": "Sergio Perez", "team": "Cadillac", "key": "perez"},
    {"abbr": "BOT", "name": "Valtteri Bottas", "team": "Cadillac", "key": "bottas"},
]

# Lookup helpers — built once at import time
_BY_KEY: dict[str, DriverInfo] = {d["key"]: d for d in ROSTER}
_BY_ABBR: dict[str, DriverInfo] = {d["abbr"]: d for d in ROSTER}


def by_key(key: str) -> Optional[DriverInfo]:
    """Return the driver dict for a canonical key, or ``None``."""
    return _BY_KEY.get(key.lower())


def by_abbr(abbr: str) -> Optional[DriverInfo]:
    """Return the driver dict for a 3-letter abbreviation, or ``None``."""
    return _BY_ABBR.get(abbr.upper())
