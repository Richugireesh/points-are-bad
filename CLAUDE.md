# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An F1 prediction game CLI where players predict Top 10 race finishers. Scoring is inverted — **lowest score wins**. Points are awarded for mismatches (+1 per wrong position), with a +10 penalty for missing a prediction entirely.

## Commands

```bash
# Build
cargo build --release

# Run the app
cargo run
# or after release build:
./target/release/points-are-bad

# Run all tests
cargo test

# Run integration tests (requires network — OpenF1 API)
cargo test -- --ignored

# Lint and format
cargo clippy
cargo fmt
```

## Architecture

```
src/
├── main.rs      # Entry point — calls cli::run()
├── cli.rs       # All UI and menu logic — no scoring/API logic
├── storage.rs   # load_data() / save_data() + all data types (AppData, Race, ActualResult)
├── scoring.rs   # Pure scoring functions; ALIASES map for driver name shortcuts
├── api.rs       # OpenF1 HTTP integration
└── drivers.rs   # Hard-coded 2026 F1 roster with by_key() / by_abbr() helpers
```

**Data file:** `points_are_bad_data.json` (configurable via `POINTS_DATA_FILE` env var)

**Startup flow:** `cli::run()` → `load_data()` → `auto_update_past_races()` (fetches missing results for past races via OpenF1) → interactive menu loop.

## OpenF1 API Quirk

Must follow this exact endpoint sequence to avoid null driver name bugs:
1. `/meetings?year=X` → get `meeting_key`
2. `/sessions?meeting_key=X&session_type=Race` → get `session_key`
3. `/session_result?session_key=X` → get results
4. `/drivers?meeting_key=X` (**not** `session_key`) — `session_key` here returns null `broadcast_name`

## Scoring Logic

`scoring::matches_actual()` uses flexible substring matching (case-insensitive, strips hidden Unicode chars U+2060/U+200B). The `ALIASES` map (via `OnceLock`) resolves shortcuts like `"ver"` → `"verstappen"`. Handles both `ActualResult::Plain(String)` and `ActualResult::DriverResult { abbr, name }`.

## Data Model

```json
{
  "players": ["alice", "bob"],
  "races": [{
    "name": "Bahrain GP",
    "date": "2026-03-01",
    "actual_results": [
      {"abbr": "RUS", "name": "George Russell"},
      "norris"
    ],
    "predictions": {
      "alice": ["verstappen", "norris", "..."]
    }
  }]
}
```

`actual_results` uses `#[serde(untagged)]` — entries are either `DriverResult { abbr, name }` (from OpenF1 fetch) or `Plain(String)` (manual entry). Driver `"key"` is the canonical identifier (lowercase last name), used in predictions and resolved through `ALIASES` in scoring.
