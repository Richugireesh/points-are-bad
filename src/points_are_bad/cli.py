import json
import os
import sys
import datetime
import logging
import re

try:
    import fastf1
    HAS_FASTF1 = True
    logging.getLogger('fastf1.req').setLevel(logging.CRITICAL)
except ImportError:
    HAS_FASTF1 = False

import urllib.request
import urllib.error

DATA_FILE = "points_are_bad_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"players": [], "races": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def parse_raw_input_lines(lines, max_items):
    text = "\n".join(lines)
    # Remove hidden characters like Word Joiner or Zero Width Space
    text = text.replace('\u2060', '').replace('\u200b', '')
    # Replace common list numbering like "1.", "2)", "3 ." with a delimiter "|"
    cleaned_text = re.sub(r'\d+\s*[.)]', '|', text)
    
    parts = []
    # Split by the new delimiter, newlines, or commas
    for chunk in re.split(r'[|\n,]', cleaned_text):
        chunk = chunk.strip()
        # Clean up stray left over parenthesis if they typed "(1)"
        if chunk.startswith('('):
            chunk = chunk[1:].strip()
        if chunk:
            parts.append(chunk)
            
    return parts[:max_items]

def get_input_list(prompt, min_items=10, max_items=10):
    print(prompt)
    print("(You can paste a list directly here, or type them one by one. Press Enter on an empty line to finish.)")
    
    lines = []
    while True:
        try:
            line = input(f"  {len(lines)+1}. " if len(lines) < max_items else "  ... ").strip()
        except EOFError:
            break
            
        if not line:
            if len(lines) == 0:
                continue
            parsed = parse_raw_input_lines(lines, max_items)
            if len(parsed) >= min_items:
                break
                
            confirm = input(f"You only entered {len(parsed)} items. Are you sure you're done? (y/n): ").strip().lower()
            if confirm == 'y':
                break
            else:
                continue
                
        lines.append(line)
        parsed = parse_raw_input_lines(lines, max_items)
        if len(parsed) >= max_items:
            break
            
    return parse_raw_input_lines(lines, max_items)

def select_item(items, item_name, display_func=str):
    if not items:
        input(f"No {item_name}s exist. Please add a {item_name} first. Press Enter...")
        return None
        
    print(f"\nAvailable {item_name}s:")
    for i, item in enumerate(items):
        print(f"{i+1}. {display_func(item)}")
        
    try:
        idx = int(input(f"\nSelect a {item_name} by number: ")) - 1
        if not (0 <= idx < len(items)):
            raise ValueError()
        return items[idx]
    except ValueError:
        input(f"Invalid {item_name} selection. Press Enter...")
        return None

def auto_update_past_races(data):
    today = datetime.datetime.now().date().isoformat()
    updated = False
    
    # We'll need to briefly inform the user if we perform an update
    first_update = True
    
    for race in data["races"]:
        r_date = race.get("date")
        if r_date and r_date <= today and not race["actual_results"]:
            if first_update:
                clear_screen()
                print("=== Performing Auto-Updates ===")
                first_update = False
                
            print(f"Fetching missing results for completed race: {race['name']} ({r_date})...")
            year = int(r_date[:4])
            fetched = fetch_fastf1_results(year, race['name']) if HAS_FASTF1 else None
            
            if not fetched:
                fetched = fetch_openf1_results(year, race['name'])
                
            if fetched:
                race["actual_results"] = fetched
                updated = True
                print(f" -> Successfully saved results for {race['name']}!\n")
            else:
                print(f" -> Could not fetch results yet.\n")
                
    if updated:
        save_data(data)
    if not first_update:
        input("Press Enter to continue to the Main Menu...")

def main_menu():
    data = load_data()
    auto_update_past_races(data)
    
    while True:
        clear_screen()
        print("=== Points are Bad: F1 Prediction Game ===")
        print("1. Manage Players")
        print("2. Manage Races")
        print("3. Enter Predictions")
        print("4. Enter Actual Race Results")
        print("5. View Race Results & Points")
        print("6. View Season Standings")
        print("7. Exit")
        
        choice = input("\nSelect an option: ").strip()
        
        if choice == '1':
            manage_players(data)
        elif choice == '2':
            manage_races(data)
        elif choice == '3':
            enter_predictions(data)
        elif choice == '4':
            enter_results(data)
        elif choice == '5':
            view_race_points(data)
        elif choice == '6':
            view_standings(data)
        elif choice == '7':
            save_data(data)
            print("Scores saved! Exiting...")
            sys.exit(0)
        else:
            input("Invalid choice. Press Enter to try again.")

def manage_players(data):
    while True:
        clear_screen()
        print("--- Manage Players ---")
        if not data["players"]:
            print("No players added yet.")
        else:
            print("Current players:")
            for p in data["players"]:
                print(f" - {p}")
        
        print("\n1. Add Player")
        print("2. Remove Player")
        print("3. Back to Main Menu")
        choice = input("Select an option: ").strip()
        
        if choice == '1':
            name = input("Enter player name: ").strip()
            if name and name not in data["players"]:
                data["players"].append(name)
                save_data(data)
                print(f"Player '{name}' added!")
            elif name in data["players"]:
                print("Player already exists.")
            input("Press Enter to continue...")
        elif choice == '2':
            name = input("Enter player name to remove: ").strip()
            if name in data["players"]:
                data["players"].remove(name)
                save_data(data)
                print(f"Player '{name}' removed!")
            else:
                print("Player not found.")
            input("Press Enter to continue...")
        elif choice == '3':
            break

def manage_races(data):
    while True:
        clear_screen()
        print("--- Manage Races ---")
        if not data["races"]:
            print("No races added yet.")
        else:
            print("Current races:")
            for r in data["races"]:
                print(f" - {r['name']}")
                
        print("\n1. Add Race")
        print("2. Remove Race")
        print("3. Auto-populate Current Season Schedule (FastF1)")
        print("4. Back to Main Menu")
        choice = input("Select an option: ").strip()
        
        if choice == '1':
            name = input("Enter race name (e.g. 'Bahrain GP'): ").strip()
            # check if exists
            if any(r['name'].lower() == name.lower() for r in data["races"]):
                print("Race already exists.")
            elif name:
                date_str = input("Enter race date (YYYY-MM-DD) or leave blank: ").strip()
                data["races"].append({
                    "name": name,
                    "date": date_str,
                    "actual_results": [],
                    "predictions": {}
                })
                save_data(data)
                print(f"Race '{name}' added!")
            input("Press Enter to continue...")
        elif choice == '2':
            name = input("Enter race name to remove: ").strip()
            found = False
            for r in data["races"]:
                if r['name'].lower() == name.lower():
                    data["races"].remove(r)
                    save_data(data)
                    print(f"Race '{r['name']}' removed!")
                    found = True
                    break
            if not found:
                print("Race not found.")
            input("Press Enter to continue...")
        elif choice == '3':
            auto_populate_schedule(data)
        elif choice == '4':
            break

def auto_populate_schedule(data):
    if not HAS_FASTF1:
        input("\nFastF1 is not installed. Please install it to use this feature. Press Enter...")
        return
        
    year = datetime.datetime.now().year
    print(f"\nFetching official F1 schedule for {year}...")
    try:
        cache_dir = os.path.abspath('fastf1_cache')
        os.makedirs(cache_dir, exist_ok=True)
        fastf1.Cache.enable_cache(cache_dir)
        
        schedule = fastf1.get_event_schedule(year)
        races = schedule[schedule['EventFormat'] != 'testing']
        
        added_count = 0
        existing_names = [r['name'].lower() for r in data["races"]]
        
        for _, row in races.iterrows():
            race_name = row.get('EventName')
            event_date = row.get('EventDate')
            date_str = str(event_date.date()) if hasattr(event_date, 'date') else ""
            
            existing_race = next((r for r in data["races"] if r['name'].lower() == race_name.lower()), None)
            
            if existing_race:
                if not existing_race.get('date') and date_str:
                    existing_race['date'] = date_str
                    added_count += 1
                    print(f" Updated Date: {race_name} -> {date_str}")
            elif race_name:
                data["races"].append({
                    "name": race_name,
                    "date": date_str,
                    "actual_results": [],
                    "predictions": {}
                })
                added_count += 1
                print(f" Added: {race_name} ({date_str})")
                
        if added_count > 0:
            save_data(data)
            print(f"\nSuccessfully updated {added_count} races in the schedule!")
        else:
            print("\nSchedule is already up to date. No new races added.")
            
    except Exception as e:
        print(f"Error fetching schedule: {e}")
        
    input("Press Enter to continue...")

def enter_predictions(data):
    clear_screen()
    print("--- Enter Predictions ---")
    
    today = datetime.datetime.now().date().isoformat()
    upcoming_races = [r for r in data["races"] if not r.get("actual_results") and (not r.get("date") or r["date"] >= today)]
    upcoming_races.sort(key=lambda x: x.get("date", "9999-12-31"))
    
    if not upcoming_races:
        input("No upcoming races to predict for. Press Enter...")
        return
        
    def display_upcoming(r):
        base = f"{r['name']} (Date: {r.get('date', 'Unknown')})"
        if r == upcoming_races[0]:
            return f"{base} [NEXT UPCOMING]"
        return base
        
    race = select_item(upcoming_races, "upcoming race", display_upcoming)
    if not race:
        return
        
    player = select_item(data["players"], "player")
    if not player:
        return
    
    if player in race["predictions"]:
        print("\nWARNING: Prediction already exists for this player and race!")
        overwrite = input("Do you want to overwrite? (y/n): ").strip().lower()
        if overwrite != 'y':
            return
            
    print(f"\nEnter top 10 prediction for {player} at {race['name']}:")
    print("Enter the names of the drivers (e.g., 'Verstappen', 'Max', 'VER' etc.)")
    print("Be consistent with naming to make checking easier.")
    
    prediction = get_input_list("Top 10:", max_items=10)
    race["predictions"][player] = prediction
    save_data(data)
    input(f"\nPrediction for {player} saved successfully! Press Enter...")

def fetch_fastf1_results(year, race_name):
    if not HAS_FASTF1:
        return None
    print(f"\nFetching official FastF1 data for {race_name} ({year})...")
    try:
        cache_dir = os.path.abspath('fastf1_cache')
        os.makedirs(cache_dir, exist_ok=True)
        fastf1.Cache.enable_cache(cache_dir)
        
        session = fastf1.get_session(year, race_name, 'R')
        session.load(telemetry=False, laps=False, weather=False)
        
        if 'Position' not in session.results.columns or session.results['Position'].isnull().all():
            print("\n[!] Official race results are not yet available for this session in FastF1.")
            return None
            
        results = session.results.dropna(subset=['Position']).sort_values(by='Position').head(10)
        drivers = []
        for _, row in results.iterrows():
            drivers.append({
                "BroadcastName": str(row.get("BroadcastName", "")),
                "FirstName": str(row.get("FirstName", "")),
                "LastName": str(row.get("LastName", "")),
                "Abbreviation": str(row.get("Abbreviation", ""))
            })
        return drivers
    except Exception as e:
        print(f"Error fetching FastF1 data: {e}")
        return None

def _fetch_openf1_json(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 points-are-bad/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status != 200:
                return None
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def fetch_openf1_results(year, race_name):
    print(f"\nAttempting to fetch from OpenF1 API for {race_name} ({year})...")
    try:
        # First get the meeting key for this specific race
        meetings_url = f"https://api.openf1.org/v1/meetings?year={year}"
        meetings = _fetch_openf1_json(meetings_url)
        if not meetings:
            return None
            
        target_meeting = None
        for m in meetings:
            if m.get('meeting_name', '').lower() in race_name.lower() or race_name.lower() in m.get('meeting_name', '').lower():
                target_meeting = m
                break
                
        if not target_meeting:
            # Fallback fuzzy matching
            for m in meetings:
                if m.get('country_name', '').lower() in race_name.lower() or m.get('location', '').lower() in race_name.lower():
                    target_meeting = m
                    break
                    
        if not target_meeting:
            print(f"[!] Could not find meeting matching '{race_name}' in OpenF1.")
            return None
            
        meeting_key = target_meeting['meeting_key']
        
        # Now get the Race session for this meeting
        session_url = f"https://api.openf1.org/v1/sessions?meeting_key={meeting_key}&session_type=Race"
        sessions = _fetch_openf1_json(session_url)
        
        if not sessions or (isinstance(sessions, dict) and 'detail' in sessions):
            print(f"[!] Could not find a Race session for meeting {target_meeting.get('meeting_name')}.")
            return None
            
        target_session = sessions[0]
        session_key = target_session['session_key']
        print(f"Found OpenF1 session: {target_meeting.get('meeting_name')} - {target_session.get('session_name')} (Key: {session_key})")
        
        # Now fetch the actual session results
        res_url = f"https://api.openf1.org/v1/session_result?session_key={session_key}&position<=10"
        res_data = _fetch_openf1_json(res_url)
        
        if isinstance(res_data, dict) and 'detail' in res_data:
            print(f"[!] OpenF1 API Info: {res_data['detail']}")
            return None
            
        if not res_data:
             print("[!] OpenF1 does not have session_results populated yet.")
             return None
             
        sorted_results = sorted(res_data, key=lambda x: x['position'])
        
        # Get driver metadata for the entire meeting to ensure we get non-null names
        drivers_url = f"https://api.openf1.org/v1/drivers?meeting_key={meeting_key}"
        drivers_data = _fetch_openf1_json(drivers_url)
             
        driver_map = {}
        if isinstance(drivers_data, list):
            for d in drivers_data:
                d_num = str(d.get('driver_number', ''))
                # Only map if it has a valid broadcast or full name, or if it's the first time
                if d_num not in driver_map or d.get('broadcast_name') or d.get('full_name'):
                    if d.get('broadcast_name') or d.get('full_name') or d_num not in driver_map:
                        driver_map[d_num] = d
                
        results = []
        for res in sorted_results[:10]:
            driver_id = str(res['driver_number'])
            driver_info = driver_map.get(driver_id, {})
            b_name = driver_info.get("broadcast_name") or driver_info.get("full_name") or str(driver_id)
            results.append({
                "BroadcastName": b_name,
                "FirstName": driver_info.get("first_name") or "",
                "LastName": driver_info.get("last_name") or "",
                "Abbreviation": driver_info.get("name_acronym") or ""
            })
            
        return results
    except Exception as e:
        print(f"OpenF1 fetching error: {e}")
        return None

def enter_results(data):
    clear_screen()
    print("--- Enter Actual Race Results ---")
    
    today = datetime.datetime.now().date().isoformat()
    past_races = [r for r in data["races"] if r.get("date") and r["date"] <= today]
    past_races.sort(key=lambda x: x.get("date", "0000-00-00"))
    
    if not past_races:
        input("No completed races available yet. Press Enter...")
        return
        
    def display_past(r):
        status = "(Results Logged)" if r.get("actual_results") else "(Needs Results!)"
        return f"{r['name']} (Date: {r.get('date', 'Unknown')}) {status}"
        
    race = select_item(past_races, "completed race", display_past)
    if not race:
        return
    
    if race["actual_results"]:
        print("\nWARNING: Actual results already exist for this race!")
        overwrite = input("Do you want to overwrite? (y/n): ").strip().lower()
        if overwrite != 'y':
            return
            
    choice = input("\nDo you want to fetch results automatically using Official F1 APIs? (y/n): ").strip().lower()
    if choice == 'y':
        try:
            year = int(input("Enter the race year (e.g. 2024): ").strip())
            fetched = fetch_fastf1_results(year, race['name']) if HAS_FASTF1 else None
            
            if not fetched: # Always fallback to OpenF1 if FastF1 fails or isn't installed
                fetched = fetch_openf1_results(year, race['name'])
                
            if fetched:
                print("\nSuccessfully fetched Top 10:")
                for i, d in enumerate(fetched):
                    print(f"  {i+1}. {d['BroadcastName']}")
                confirm = input("\nSave these results? (y/n): ").strip().lower()
                if confirm == 'y':
                    race["actual_results"] = fetched
                    save_data(data)
                    input(f"\nActual results for {race['name']} saved! Press Enter...")
                    return
            else:
                print("Could not fetch data. Falling back to manual entry.")
        except ValueError:
            print("Invalid year. Falling back to manual entry.")
                
    print(f"\nEnter the TOP 10 actual race results for {race['name']}:")
    print("IMPORTANT: Try to use names identically to what players typed,")
    print("However the system will ignore case spaces temporarily.")
    
    actual = get_input_list("Top 10:", max_items=10)
    race["actual_results"] = actual
    save_data(data)
    input(f"\nActual results for {race['name']} saved! Press Enter...")

def calculate_str_equality(a, b):
    # a is prediction, b is either string or dict (fastf1)
    p = str(a).strip().lower()
    # Remove any word joiner or invisible characters that sometimes appear when pasting
    p = p.replace('\u2060', '').replace('\u200b', '').strip()
    
    aliases = {
        "kimi": "antonelli",
        "lec": "leclerc",
        "ver": "verstappen",
        "max": "verstappen",
        "ham": "hamilton",
        "nor": "norris",
        "pia": "piastri",
        "rus": "russell",
        "lind": "lindblad",
        "linblad": "lindblad",
        "bor": "bortoleto",
        "gabby": "bortoleto",
        "gab": "bortoleto",
        "hadj": "hadjar",
        "alo": "alonso",
        "per": "perez",
        "checo": "perez",
        "gas": "gasly",
        "oco": "ocon",
        "tsu": "tsunoda",
        "yuki": "tsunoda",
        "hul": "hulkenberg",
        "str": "stroll",
        "mag": "magnussen",
        "alb": "albon",
        "col": "colapinto",
        "bea": "bearman",
        "ollie": "bearman",
        "sai": "sainz",
        "zho": "zhou",
        "bot": "bottas",
        "law": "lawson",
        "doo": "doohan"
    }
    
    if p in aliases:
        p = aliases[p]

    if isinstance(b, dict):
        # Exact match of any field
        for val in b.values():
            if val and p == str(val).strip().lower():
                return True
        # Substring match on BroadcastName or LastName
        for val in b.values():
            if val and p in str(val).strip().lower():
                return True
        return False
    else:
        b_str = str(b).strip().lower()
        if b_str in aliases:
            b_str = aliases[b_str]
        return p == b_str or p in b_str

def calculate_player_points_for_race(prediction, actual):
    points = 0
    # Both lists should be length 10
    for i in range(min(len(prediction), len(actual))):
        if not calculate_str_equality(prediction[i], actual[i]):
            points += 1
    # Adding points for missing predictions or results up to 10
    diff = abs(len(prediction) - len(actual))
    points += diff 
    return points

def view_race_points(data):
    clear_screen()
    print("--- View Race Points ---")
    
    today = datetime.datetime.now().date().isoformat()
    sorted_races = sorted(data["races"], key=lambda x: x.get("date", "9999-12-31"))
    
    def display_race(r):
        status = "(Results Added)" if r.get("actual_results") else "(No Results Yet)"
        is_past = "[COMPLETED]" if r.get("actual_results") or (r.get("date") and r["date"] < today) else "[UPCOMING]"
        return f"{r['name']} {is_past} - {status}"
        
    race = select_item(sorted_races, "race", display_race)
    if not race:
        return
    actual = race["actual_results"]
    
    print(f"\n--- {race['name']} Points ---")
    if not actual:
        print("Actual results not yet added for this race. Cannot calculate points.")
    else:
        if not race["predictions"]:
            print("No predictions were made for this race.")
        else:
            print("Scores (Lower is better!):")
            for player, prediction in race["predictions"].items():
                pts = calculate_player_points_for_race(prediction, actual)
                print(f" - {player}: {pts} points")
                
            print("\nBreakdown for each player:")
            for player, prediction in race["predictions"].items():
                print(f"\n{player}'s Prediction Breakdown:")
                pts = 0
                for i in range(10):
                    pred = prediction[i] if i < len(prediction) else "(None)"
                    
                    if i < len(actual):
                        act_val = actual[i]
                        act = act_val.get("BroadcastName", str(act_val)) if isinstance(act_val, dict) else str(act_val)
                    else:
                        act = "(None)"
                        
                    if calculate_str_equality(pred, actual[i] if i < len(actual) else "(None)"):
                        print(f"  P{i+1}: {act} [CORRECT]")
                    else:
                        print(f"  P{i+1}: Predicted {pred}, Actual was {act} [+1 Point]")
                        pts += 1
                print(f"  Total for {player}: {pts} points")
                
    input("\nPress Enter to continue...")

def view_standings(data):
    clear_screen()
    print("=== SEASON STANDINGS (Lowest Points = WINNING) ===")
    
    player_scores = {p: 0 for p in data["players"]}
    
    races_counted = 0
    for race in data["races"]:
        actual = race["actual_results"]
        if actual:
            races_counted += 1
            for player, prediction in race["predictions"].items():
                # Add score if player exists and made prediction
                if player in player_scores:
                    pts = calculate_player_points_for_race(prediction, actual)
                    player_scores[player] += pts
                # What if they didn't predict? They should probably get max points (10)?
                # Or maybe 10 points penalty if missing prediction?
            
            # For players who didn't predict this round but are part of the game:
            for player in data["players"]:
                if player not in race["predictions"]:
                    player_scores[player] += 10 # 10 penalty for not predicting
                    
    # Sort by lowest score
    sorted_players = sorted(player_scores.items(), key=lambda x: x[1])
    
    print(f"\nStandings after {races_counted} race(s) with actual results:")
    print("-------------------------------------------------")
    for i, (player, score) in enumerate(sorted_players):
        print(f"{i+1}. {player} - {score} points")
    print("-------------------------------------------------")
    print("* Note: Missing a prediction for a completed race gives you +10 points.")
    
    input("\nPress Enter to continue...")

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
