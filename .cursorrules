# AI Agent Context & Instructions

If you are an AI reading this codebase, pay close attention to the following architectural details, API quirks, and data modeling decisions implemented in this project.

## 1. Project Structure & Storage
- **Main App**: Contains a zero-dependency (from a UI perspective) built-in CLI loop inside `points_are_bad.py`.
- **Data Persistence**: State is stored purely in a local JSON file (`points_are_bad_data.json`).
- **Dependencies**: The only mandatory non-standard-library dependency is `fastf1`, and optionally `pandas` (which comes with FastF1). `requests` was originally used, but removed in favor of `urllib.request`.

## 2. API Quirk 1: FastF1 Request Caching Restriction
- **The Issue**: When `fastf1` is imported, it silently, globally monkey-patches `requests` with a highly aggressive `requests-cache`. Once this is done, ANY standard `requests.get()` calls to other APIs (like OpenF1) may load stale data or hit weird timeout tracebacks if FastF1 fails.
- **The Fix**: Do not use the `requests` library when making secondary API calls in this app. The script intentionally implements a custom `_fetch_openf1_json` method utilizing the standard `urllib.request` library which successfully bypasses FastF1's caching layer. Maintain this pattern for any new network requests.
- **Logging**: FastF1's `req` logger is set to `CRITICAL` at the very top of the script so it doesn't spam the user's terminal with tracing errors when Ergast invariably times out out pulling recent un-cached races.

## 3. API Quirk 2: OpenF1 Session Tracking Logic
If you ever modify the OpenF1 fetch logic (`fetch_openf1_results`), adhere strictly to the following OpenF1 endpoint flow:
- **Never rely on `session_name` for lookup**: OpenF1's `session_name` just returns `"Race"` or `"Practice 1"`. To match user inputs like `"Australian Grand Prix"`, you MUST first hit `/meetings?year=X` to get the `meeting_key`, then query `/sessions?meeting_key=X&session_type=Race` to find the exact session for the GP.
- **Null Driver Names Bug**: The driver data endpoints in OpenF1 occasionally return multiple telemetry rows for a single driver in a `session_key`. Specifically, the rows tagged to the `Race` session sometimes return `null` for `broadcast_name` or `full_name`. 
- **The Fix**: When pulling driver maps to populate names, you MUST hit `/drivers?meeting_key=X` instead of `session_key`. This guarantees returning all tracker permutations for the weekend, preventing the app from rendering "None" or blank names in the final results list. This logic is already implemented in `points_are_bad.py` and must not be "optimized" away.

## 4. Matching User Input string to API Models
- In `calculate_str_equality`, user strings are loosely pattern matched against the driver dictionaries downloaded from FastF1/OpenF1 APIs. The CLI tells the user the system ignores case, but they should still use names. The string matching logic converts the API's dict properties (like `"BroadcastName"` or `"LastName"`) to lower-case substrings and does a `.`/`in` check.

## 5. F1 Game Rules Math
- **Perfect Match** = 0 points.
- **Mismatch Position** = +1 point.
- **Missing Prediction completely** = flat +10 point penalty per race.
- At the end of the script in `view_standings`, the total sum calculates who is winning (lowest score).
