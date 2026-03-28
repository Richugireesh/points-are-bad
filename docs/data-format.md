# Data Format

All game state is stored in a single JSON file. Default path: `points_are_bad_data.json` in the working directory. Override with the `POINTS_DATA_FILE` environment variable.

## Root schema

```json
{
    "players": ["richu", "sam", "danny"],
    "races": [ ...race objects... ]
}
```

| Field | Type | Description |
|---|---|---|
| `players` | `string[]` | Player names; order is display order |
| `races` | `race[]` | All races for the season |

## Race object

```json
{
    "name": "Australian Grand Prix",
    "date": "2026-03-08",
    "actual_results": [ ...result entries... ],
    "predictions": {
        "richu": ["russell", "antonelli", "leclerc", "piastri", "verstappen",
                  "hadjar", "hamilton", "norris", "lindblad", "bortoleto"],
        "sam":   ["russell", "leclerc", "piastri", "hadjar", "hamilton",
                  "antonelli", "norris", "verstappen", "lindblad", "bortoleto"]
    }
}
```

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Official race name (must match FastF1 event names for auto-fetch) |
| `date` | `string` | ISO 8601 date (`YYYY-MM-DD`); empty string if unknown |
| `actual_results` | `result[]` | Top-10 finishers; empty array until results are entered |
| `predictions` | `object` | Maps player name → ordered list of driver keys (P1–P10) |

## Prediction list

A prediction is an ordered array of **driver keys** — canonical lowercase last-name strings:

```json
["russell", "antonelli", "leclerc", "piastri", "verstappen",
 "hamilton", "norris", "hadjar", "lindblad", "bortoleto"]
```

- Position in the array = finishing position predicted (index 0 = P1)
- Values are canonical keys from `drivers.py` → `ROSTER[n]["key"]`
- Fewer than 10 entries is valid — missing positions score +1 each
- A player absent from `predictions` entirely scores a flat +10 penalty

### Alias resolution

The scoring engine resolves aliases at match time, so `"kimi"`, `"ant"`, or `"antonelli"` all match Kimi Antonelli. However, **predictions entered via the TUI driver picker always store the canonical key**. Only manually edited JSON or legacy entries may contain aliases.

## Result entry

Results can be stored in two formats depending on how they were entered:

### API-fetched (preferred)

```json
{"abbr": "RUS", "name": "George Russell"}
```

| Field | Type | Description |
|---|---|---|
| `abbr` | `string` | 3-letter FIA abbreviation |
| `name` | `string` | Full display name (`First Last`) |

### Manual entry

```json
{"abbr": "", "name": "George Russell"}
```

Plain strings are also accepted by the scoring engine (legacy support):

```json
"George Russell"
```

## Driver keys (2026 roster)

| Key | Driver | Team |
|---|---|---|
| `norris` | Lando Norris | McLaren |
| `piastri` | Oscar Piastri | McLaren |
| `leclerc` | Charles Leclerc | Ferrari |
| `hamilton` | Lewis Hamilton | Ferrari |
| `russell` | George Russell | Mercedes |
| `antonelli` | Kimi Antonelli | Mercedes |
| `verstappen` | Max Verstappen | Red Bull |
| `hadjar` | Isack Hadjar | Red Bull |
| `lawson` | Liam Lawson | Racing Bulls |
| `lindblad` | Arvid Lindblad | Racing Bulls |
| `alonso` | Fernando Alonso | Aston Martin |
| `stroll` | Lance Stroll | Aston Martin |
| `sainz` | Carlos Sainz | Williams |
| `albon` | Alexander Albon | Williams |
| `gasly` | Pierre Gasly | Alpine |
| `colapinto` | Franco Colapinto | Alpine |
| `ocon` | Esteban Ocon | Haas |
| `bearman` | Oliver Bearman | Haas |
| `hulkenberg` | Nico Hulkenberg | Audi |
| `bortoleto` | Gabriel Bortoleto | Audi |
| `perez` | Sergio Perez | Cadillac |
| `bottas` | Valtteri Bottas | Cadillac |

## Example: complete data file (two races)

```json
{
    "players": ["alice", "bob"],
    "races": [
        {
            "name": "Australian Grand Prix",
            "date": "2026-03-08",
            "actual_results": [
                {"abbr": "RUS", "name": "George Russell"},
                {"abbr": "ANT", "name": "Kimi Antonelli"},
                {"abbr": "LEC", "name": "Charles Leclerc"},
                {"abbr": "HAM", "name": "Lewis Hamilton"},
                {"abbr": "NOR", "name": "Lando Norris"},
                {"abbr": "VER", "name": "Max Verstappen"},
                {"abbr": "BEA", "name": "Oliver Bearman"},
                {"abbr": "LIN", "name": "Arvid Lindblad"},
                {"abbr": "BOR", "name": "Gabriel Bortoleto"},
                {"abbr": "GAS", "name": "Pierre Gasly"}
            ],
            "predictions": {
                "alice": ["russell", "antonelli", "leclerc", "piastri",
                          "verstappen", "hadjar", "hamilton", "norris",
                          "lindblad", "bortoleto"],
                "bob":   ["piastri", "russell", "hadjar", "leclerc",
                          "verstappen", "antonelli", "norris", "hamilton",
                          "alonso", "perez"]
            }
        },
        {
            "name": "Chinese Grand Prix",
            "date": "2026-03-15",
            "actual_results": [],
            "predictions": {}
        }
    ]
}
```
