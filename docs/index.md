# Points are Bad — Documentation

F1 prediction game where players predict the Top 10 finishers of every Grand Prix. Lower score wins.

## Quick navigation

| Document | Contents |
|---|---|
| [Game Rules & Scoring](scoring.md) | How points work, tie-breaking, examples |
| [Architecture](architecture.md) | Module layout, data flow, design decisions |
| [Data Format](data-format.md) | JSON schema, driver key system |
| [API Reference](api-reference.md) | All public functions across every module |
| [TUI Guide](tui.md) | Screens, keybindings, navigation |
| [Development Guide](development.md) | Dev setup, tests, adding drivers/seasons |

---

## Installation

Requires Python 3.9+ and [uv](https://github.com/astral-sh/uv).

```bash
git clone <repo>
cd points-are-bad
uv venv
uv pip install -e .[dev]   # [dev] adds pytest
```

## Running

```bash
source .venv/bin/activate
points-are-bad
```

Or without activating the venv:

```bash
.venv/bin/points-are-bad
```

The TUI opens immediately. Data is stored in `points_are_bad_data.json` in the working directory (auto-created on first launch).

To use a different data file:

```bash
POINTS_DATA_FILE=/path/to/other.json points-are-bad
```

## Running tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

All 56 tests should pass.
