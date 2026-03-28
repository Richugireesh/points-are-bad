# Game Rules & Scoring

## The game

Before each Grand Prix — usually after qualifying — every player submits a predicted Top 10 finishing order. After the race, predictions are compared to the actual results and points are awarded. **Lower score wins** (like golf).

## Points rules

| Situation | Points |
|---|---|
| Prediction matches result at that position | 0 |
| Prediction is wrong (or missing) at a position | +1 |
| Player submitted no prediction for the race | +10 (flat penalty) |

Each race scores a minimum of 0 (perfect prediction) and a maximum of 10 (all wrong, or no prediction).

### Example

Actual P1–P10: Russell, Antonelli, Leclerc, Hamilton, Norris, Verstappen, Bearman, Lindblad, Bortoleto, Gasly

Player prediction: Russell, Antonelli, Leclerc, **Piastri**, Verstappen, **Hadjar**, Hamilton, Norris, Lindblad, Bortoleto

| Pos | Actual | Predicted | Score |
|---|---|---|---|
| P1 | Russell | russell | 0 |
| P2 | Antonelli | antonelli | 0 |
| P3 | Leclerc | leclerc | 0 |
| P4 | Hamilton | piastri | +1 |
| P5 | Norris | verstappen | +1 |
| P6 | Verstappen | hadjar | +1 |
| P7 | Bearman | hamilton | +1 |
| P8 | Lindblad | norris | +1 |
| P9 | Bortoleto | lindblad | +1 |
| P10 | Gasly | bortoleto | +1 |
| **Total** | | | **7 pts** |

## Driver name matching

The scoring engine uses case-insensitive **substring matching** with alias resolution. This means:

- `"russell"` matches "George Russell" ✓
- `"nor"` matches "Lando Norris" ✓
- `"kimi"` resolves to `"antonelli"` via the alias table ✓
- `"max"` resolves to `"verstappen"` ✓

See `scoring.py` → `ALIASES` for the full alias table, and `scoring.md` in the [API reference](api-reference.md#scoringpy) for the matching rules.

### Alias table (selected entries)

| Alias | Resolves to |
|---|---|
| `ver`, `max` | `verstappen` |
| `ant`, `kimi` | `antonelli` |
| `nor`, `lando` | `norris` |
| `pia`, `oscar` | `piastri` |
| `lec`, `charles` | `leclerc` |
| `ham`, `lewis` | `hamilton` |
| `rus`, `george` | `russell` |
| `had`, `hadj` | `hadjar` |
| `lin`, `linblad` | `lindblad` |
| `bor`, `gabby` | `bortoleto` |

Full list is in `src/points_are_bad/scoring.py` → `ALIASES`.

## Season standings

Season points = sum of all race scores. Races without results are not counted. A player missing from a race's prediction dict receives the full +10 penalty for that race when standings are calculated.

Tie-breaking is not currently implemented — tied players are shown at equal rank.
