# Points Are Bad - F1 Prediction Game

A Python-based CLI application to play "Points are Bad" - a Formula 1 prediction game among friends where players predict the Top 10 finishers of every Grand Prix. The objective is to accumulate the *least* amount of points across the season.

## Rules
- Players predict the Top 10 finishers before every GP (usually after qualifying).
- For every position a prediction is wrong, the player gets points. (e.g., if you predicted a driver P4 and they finished P1, that's not right, so you get a penalty point for that slot not matching). The current logic gives +1 point for every incorrect prediction slot. A missing prediction gives a flat +10 penalty points for that race.
- The player with the fewest points at the end of the season wins.

## Features
- **Player Management**: Add or remove players from the game.
- **Race Management**: Automatically fetches the 24-race schedule for the current year from **FastF1**.
- **Prediction Entry**: CLI interface to quickly add Top 10 predictions for any player.
- **Automated Results Fetching**:
  1. Attempts to use the **FastF1** API to fetch official race classification.
  2. If the fastf1 / Ergast official results are not yet published, instantly falls back to the **OpenF1** API to fetch real-time session results.
  3. If both APIs are down, drops back to user manual entry.
- **Points Calculation & Standings**: Auto-calculates the points gap for every prediction slot and prints season standings based on the `points_are_bad_data.json` local storage.

## Usage
Activate your virtual environment and run the CLI script:
```bash
source .venv/bin/activate
python points_are_bad.py
```
