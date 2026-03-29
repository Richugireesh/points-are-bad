/// CLI presentation layer.
///
/// Responsible for: menus, input loops, printing, and orchestrating calls to
/// api, scoring, and storage modules.  No scoring math or HTTP requests here.
use crate::api::{fetch_openf1_results, get_schedule_updates};
use crate::drivers::ROSTER;
use crate::scoring::{player_points_for_race, score_position, season_standings};
use crate::storage::{load_data, save_data, ActualResult, AppData};
use anyhow::Context;
use std::io::{self, Write};

// ---------------------------------------------------------------------------
// Layout constants & helpers
// ---------------------------------------------------------------------------

const W: usize = 50;

fn box_top() -> String {
    format!("╔{:═<width$}╗", "", width = W + 2)
}

fn box_bot() -> String {
    format!("╚{:═<width$}╝", "", width = W + 2)
}

fn box_row(text: &str) -> String {
    format!("║  {text:<W$}║")
}

fn header(lines: &[&str]) {
    println!("{}", box_top());
    for line in lines {
        println!("{}", box_row(line));
    }
    println!("{}", box_bot());
}

fn rule(label: Option<&str>) {
    match label {
        Some(l) if !l.is_empty() => {
            let dash_len = W.saturating_sub(l.len() + 1);
            println!("  {l} {:─<dash_len$}", "");
        }
        _ => println!("  {:─<width$}", "", width = W + 2),
    }
}

/// "2026-03-16" → "Mar 16".  Returns "Unknown" on bad input.
fn fmt_date(date_str: &str) -> String {
    if date_str.is_empty() {
        return "Unknown".to_string();
    }
    // Parse YYYY-MM-DD manually for no-dep formatting
    let parts: Vec<&str> = date_str.splitn(3, '-').collect();
    if parts.len() < 3 {
        return date_str.to_string();
    }
    let month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                        "Jul","Aug","Sep","Oct","Nov","Dec"];
    let month_idx: usize = parts[1].parse::<usize>().unwrap_or(0);
    if month_idx == 0 || month_idx > 12 {
        return date_str.to_string();
    }
    let day: u32 = parts[2].parse().unwrap_or(0);
    format!("{} {:02}", month_names[month_idx - 1], day)
}

fn season_context(data: &AppData) -> String {
    let n = data.players.len();
    let done = data.races.iter().filter(|r| !r.actual_results.is_empty()).count();
    let total = data.races.len();
    let year = chrono::Local::now().format("%Y");
    let word = if n == 1 { "player" } else { "players" };
    format!("Season {year}  •  {n} {word}  •  {done}/{total} races done")
}

fn clear_screen() {
    if cfg!(windows) {
        let _ = std::process::Command::new("cls").status();
    } else {
        let _ = std::process::Command::new("clear").status();
        // Fallback: ANSI escape
        print!("\x1B[2J\x1B[H");
        let _ = io::stdout().flush();
    }
}

// ---------------------------------------------------------------------------
// Input helpers
// ---------------------------------------------------------------------------

/// Print a prompt and read a trimmed line from stdin.
fn prompt(label: &str) -> String {
    print!("{label}");
    let _ = io::stdout().flush();
    let mut buf = String::new();
    let _ = io::stdin().read_line(&mut buf);
    buf.trim().to_string()
}

/// Print a numbered list of items and return the chosen index (0-based),
/// or `None` on invalid/empty input.
fn select_item<T>(
    items: &[T],
    item_name: &str,
    display: impl Fn(&T) -> String,
) -> Option<usize> {
    if items.is_empty() {
        prompt(&format!("\n  No {item_name}s exist. Add one first. Press Enter..."));
        return None;
    }
    println!();
    for (i, item) in items.iter().enumerate() {
        println!("  [{}] {}", i + 1, display(item));
    }
    let raw = prompt(&format!("\n  Select [1-{}]: ", items.len()));
    match raw.parse::<usize>() {
        Ok(n) if n >= 1 && n <= items.len() => Some(n - 1),
        _ => {
            prompt("  Invalid selection. Press Enter...");
            None
        }
    }
}

/// Return today's date as a "YYYY-MM-DD" string.
fn today_str() -> String {
    chrono::Local::now().format("%Y-%m-%d").to_string()
}

// ---------------------------------------------------------------------------
// Auto-update on startup
// ---------------------------------------------------------------------------

fn auto_update_past_races(data: &mut AppData) -> anyhow::Result<()> {
    let today = today_str();
    let mut updated = false;
    let mut first_update = true;

    // Collect indices of races that need updating to avoid borrowing issues
    let indices: Vec<usize> = data.races.iter().enumerate()
        .filter(|(_, r)| {
            !r.date.is_empty() && r.date <= today && r.actual_results.is_empty()
        })
        .map(|(i, _)| i)
        .collect();

    for idx in indices {
        if first_update {
            clear_screen();
            header(&["Auto-updating past race results..."]);
            println!();
            first_update = false;
        }

        let (race_name, race_date) = {
            let r = &data.races[idx];
            (r.name.clone(), r.date.clone())
        };

        println!("  Fetching: {race_name} ({}) ...", fmt_date(&race_date));
        let year: i32 = race_date[..4].parse().unwrap_or(2026);
        let fetched = fetch_openf1_results(year, &race_name);

        if let Some(results) = fetched {
            let actual: Vec<ActualResult> = results.into_iter().map(Into::into).collect();
            data.races[idx].actual_results = actual;
            updated = true;
            println!("  ✓  Results saved for {race_name}\n");
        } else {
            println!("  -  Could not fetch results yet.\n");
        }
    }

    if updated {
        save_data(data)?;
    }
    if !first_update {
        prompt("  Press Enter to continue to the Main Menu...");
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

pub fn run() -> anyhow::Result<()> {
    let mut data = load_data().context("loading game data")?;
    auto_update_past_races(&mut data)?;

    loop {
        clear_screen();
        header(&[
            "Points are Bad  •  F1 Prediction Game",
            &season_context(&data),
        ]);
        println!();
        println!("  Play");
        println!("    [1]  Enter Predictions");
        println!("    [2]  View Race Results & Points");
        println!("    [3]  View Season Standings");
        println!();
        println!("  Admin");
        println!("    [4]  Manage Players");
        println!("    [5]  Manage Races");
        println!("    [6]  Enter Race Results");
        println!();
        println!("    [7]  Exit");
        println!();

        let choice = prompt("  Select [1-7]: ");

        match choice.as_str() {
            "1" => enter_predictions(&mut data)?,
            "2" => view_race_points(&data)?,
            "3" => view_standings(&data),
            "4" => manage_players(&mut data)?,
            "5" => manage_races(&mut data)?,
            "6" => enter_results(&mut data)?,
            "7" => {
                save_data(&data)?;
                println!("\n  Scores saved! Goodbye.");
                return Ok(());
            }
            _ => { prompt("  Invalid choice. Press Enter to try again."); }
        }
    }
}

// ---------------------------------------------------------------------------
// Player management
// ---------------------------------------------------------------------------

fn manage_players(data: &mut AppData) -> anyhow::Result<()> {
    loop {
        clear_screen();
        header(&["Manage Players"]);
        println!();

        if data.players.is_empty() {
            println!("  No players added yet.");
        } else {
            let joined = data.players.join("  •  ");
            println!("  Players ({}):  {joined}", data.players.len());
        }

        println!();
        rule(None);
        println!("  [1]  Add Player");
        println!("  [2]  Remove Player");
        println!();
        println!("  [3]  Back");
        println!();

        let choice = prompt("  Select [1-3]: ");
        match choice.as_str() {
            "1" => {
                let name = prompt("\n  Player name: ");
                if name.is_empty() {
                    // skip
                } else if data.players.contains(&name) {
                    print!("  Player already exists.");
                } else {
                    data.players.push(name.clone());
                    save_data(data)?;
                    println!("  ✓  '{name}' added.");
                }
                prompt("  Press Enter to continue...");
            }
            "2" => {
                let name = prompt("\n  Name to remove: ");
                if let Some(pos) = data.players.iter().position(|p| p == &name) {
                    data.players.remove(pos);
                    save_data(data)?;
                    println!("  ✓  '{name}' removed.");
                } else {
                    println!("  Player not found.");
                }
                prompt("  Press Enter to continue...");
            }
            "3" => break,
            _ => {}
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Race management
// ---------------------------------------------------------------------------

fn manage_races(data: &mut AppData) -> anyhow::Result<()> {
    loop {
        clear_screen();
        header(&["Manage Races"]);
        println!();

        if data.races.is_empty() {
            println!("  No races added yet.");
        } else {
            let done = data.races.iter().filter(|r| !r.actual_results.is_empty()).count();
            println!("  {} races scheduled  •  {done} with results", data.races.len());
        }

        println!();
        rule(None);
        println!("  [1]  Add Race");
        println!("  [2]  Remove Race");
        println!("  [3]  Auto-populate Season Schedule (OpenF1)");
        println!();
        println!("  [4]  Back");
        println!();

        let choice = prompt("  Select [1-4]: ");
        match choice.as_str() {
            "1" => {
                let name = prompt("\n  Race name (e.g. 'Bahrain GP'): ");
                if data.races.iter().any(|r| r.name.to_lowercase() == name.to_lowercase()) {
                    println!("  Race already exists.");
                } else if !name.is_empty() {
                    let date_str = prompt("  Date (YYYY-MM-DD) or leave blank: ");
                    data.races.push(crate::storage::Race {
                        name: name.clone(),
                        date: date_str,
                        actual_results: Vec::new(),
                        predictions: std::collections::HashMap::new(),
                    });
                    save_data(data)?;
                    println!("  ✓  '{name}' added.");
                }
                prompt("  Press Enter to continue...");
            }
            "2" => {
                let name = prompt("\n  Race name to remove: ");
                if let Some(pos) = data.races.iter().position(|r| r.name.to_lowercase() == name.to_lowercase()) {
                    let removed_name = data.races[pos].name.clone();
                    data.races.remove(pos);
                    save_data(data)?;
                    println!("  ✓  '{removed_name}' removed.");
                } else {
                    println!("  Race not found.");
                }
                prompt("  Press Enter to continue...");
            }
            "3" => auto_populate_schedule(data)?,
            "4" => break,
            _ => {}
        }
    }
    Ok(())
}

fn auto_populate_schedule(data: &mut AppData) -> anyhow::Result<()> {
    let year = chrono::Local::now().format("%Y");
    println!("\n  Fetching official F1 schedule for {year}...");

    match get_schedule_updates(&data.races) {
        Ok((new_races, date_updates)) => {
            let mut change_count = 0;

            for update in &date_updates {
                let race = &mut data.races[update.race_index];
                println!("  Updated date: {}  →  {}", race.name, update.new_date);
                race.date = update.new_date.clone();
                change_count += 1;
            }

            for race in new_races {
                println!("  Added: {} ({})", race.name, race.date);
                data.races.push(race);
                change_count += 1;
            }

            if change_count > 0 {
                save_data(data)?;
                println!("\n  ✓  {change_count} change(s) saved.");
            } else {
                println!("\n  Schedule is already up to date.");
            }
        }
        Err(e) => println!("  Error fetching schedule: {e}"),
    }

    prompt("  Press Enter to continue...");
    Ok(())
}

// ---------------------------------------------------------------------------
// Predictions
// ---------------------------------------------------------------------------

fn render_driver_list(picked_keys: &[String]) {
    let mut current_team = "";
    for (i, d) in ROSTER.iter().enumerate() {
        if d.team != current_team {
            if !current_team.is_empty() {
                println!();
            }
            current_team = d.team;
        }

        let pick_pos = picked_keys.iter().position(|k| k == d.key).map(|p| p + 1);
        if let Some(pos) = pick_pos {
            println!("  [{:>2}]  {}  {:<22}  ✓ P{:<2}", i + 1, d.abbr, d.name, pos);
        } else {
            println!("  [{:>2}]  {}  {:<22}  {}", i + 1, d.abbr, d.name, d.team);
        }
    }
}

fn build_prediction(race_name: &str, player: &str) -> Option<Vec<String>> {
    let mut picked: Vec<String> = Vec::new(); // stores driver keys in pick order

    'outer: loop {
        // Selection loop
        'pick: loop {
            if picked.len() >= 10 {
                break 'pick;
            }
            let pos = picked.len() + 1;
            clear_screen();
            header(&[
                &format!("Prediction  –  {player}"),
                &format!("{race_name}  •  Choose P{pos} of 10"),
            ]);

            println!();
            rule(Some("Picked so far"));
            if picked.is_empty() {
                println!("  (none yet)");
            } else {
                for (j, key) in picked.iter().enumerate() {
                    let d = crate::drivers::by_key(key);
                    let abbr = d.map(|d| d.abbr).unwrap_or("???");
                    let name = d.map(|d| d.name).unwrap_or(key.as_str());
                    println!("  P{:>2}  {abbr}  {name}", j + 1);
                }
            }

            println!();
            rule(Some("Drivers"));
            render_driver_list(&picked);

            println!();
            println!("  [0]  Done / finish with fewer than 10");
            println!();

            let raw = prompt(&format!("  P{pos} – enter number (or 0 to finish): "));

            if raw == "0" {
                if picked.is_empty() {
                    let c = prompt("  No drivers picked yet. Cancel prediction? (y/n): ");
                    if c.to_lowercase() == "y" {
                        return None;
                    }
                    continue 'pick;
                }
                let c = prompt(&format!("  {}/10 picked. Finish early? (y/n): ", picked.len()));
                if c.to_lowercase() == "y" {
                    break 'pick;
                }
                continue 'pick;
            }

            let idx = match raw.parse::<usize>() {
                Ok(n) if n >= 1 && n <= ROSTER.len() => n - 1,
                _ => {
                    prompt("  Invalid number. Press Enter...");
                    continue 'pick;
                }
            };

            let driver = &ROSTER[idx];
            if let Some(existing_pos) = picked.iter().position(|k| k == driver.key) {
                prompt(&format!("  {} is already at P{}. Press Enter...", driver.name, existing_pos + 1));
                continue 'pick;
            }

            picked.push(driver.key.to_string());
        }

        // Confirmation screen
        clear_screen();
        header(&[
            &format!("Confirm Prediction  –  {player}"),
            race_name,
        ]);
        println!();
        for (j, key) in picked.iter().enumerate() {
            let d = crate::drivers::by_key(key);
            let abbr = d.map(|d| d.abbr).unwrap_or("???");
            let name = d.map(|d| d.name).unwrap_or(key.as_str());
            let team = d.map(|d| d.team).unwrap_or("");
            println!("  P{:>2}  {abbr}  {name:<22}  {team}", j + 1);
        }
        for j in picked.len()..10 {
            println!("  P{:>2}  ---  (not predicted)", j + 1);
        }
        println!();

        let answer = prompt("  Save? [y = yes / r = redo / n = cancel]: ");
        match answer.to_lowercase().as_str() {
            "y" => return Some(picked),
            "r" => { picked.clear(); continue 'outer; }
            _ => return None,
        }
    }
}

fn enter_predictions(data: &mut AppData) -> anyhow::Result<()> {
    clear_screen();
    header(&["Enter Predictions"]);

    let today = today_str();
    let mut upcoming: Vec<usize> = data.races.iter().enumerate()
        .filter(|(_, r)| {
            r.actual_results.is_empty() && (r.date.is_empty() || r.date >= today)
        })
        .map(|(i, _)| i)
        .collect();
    upcoming.sort_by(|&a, &b| {
        let da = data.races[a].date.as_str();
        let db = data.races[b].date.as_str();
        let da = if da.is_empty() { "9999-12-31" } else { da };
        let db = if db.is_empty() { "9999-12-31" } else { db };
        da.cmp(db)
    });

    if upcoming.is_empty() {
        prompt("\n  No upcoming races to predict for. Press Enter...");
        return Ok(());
    }

    let max_name = upcoming.iter().map(|&i| data.races[i].name.len()).max().unwrap_or(0);
    let first_idx = upcoming[0];

    let display_upcoming: Vec<String> = upcoming.iter().map(|&i| {
        let r = &data.races[i];
        let date_part = fmt_date(&r.date);
        let tag = if i == first_idx { "← next" } else { "" };
        format!("{date_part}   {:<max_name$}   {tag}", r.name)
    }).collect();

    let sel = select_item(&display_upcoming, "upcoming race", |s| s.clone());
    let race_idx = match sel {
        Some(i) => upcoming[i],
        None => return Ok(()),
    };

    let player = {
        let sel = select_item(&data.players, "player", |p| p.clone());
        match sel {
            Some(i) => data.players[i].clone(),
            None => return Ok(()),
        }
    };

    if data.races[race_idx].predictions.contains_key(&player) {
        let rname = data.races[race_idx].name.clone();
        println!("\n  WARNING: {player} already has a prediction for {rname}.");
        if prompt("  Overwrite? (y/n): ").to_lowercase() != "y" {
            return Ok(());
        }
    }

    let race_name = data.races[race_idx].name.clone();
    let prediction = build_prediction(&race_name, &player);

    match prediction {
        None => { prompt("\n  Prediction cancelled. Press Enter..."); }
        Some(keys) => {
            data.races[race_idx].predictions.insert(player.clone(), keys);
            save_data(data)?;
            prompt(&format!("\n  ✓  Prediction for {player} saved. Press Enter..."));
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Results entry
// ---------------------------------------------------------------------------

fn enter_results(data: &mut AppData) -> anyhow::Result<()> {
    clear_screen();
    header(&["Enter Race Results"]);

    let today = today_str();
    let mut past: Vec<usize> = data.races.iter().enumerate()
        .filter(|(_, r)| !r.date.is_empty() && r.date <= today)
        .map(|(i, _)| i)
        .collect();
    past.sort_by(|&a, &b| data.races[a].date.cmp(&data.races[b].date));

    if past.is_empty() {
        prompt("\n  No completed races available yet. Press Enter...");
        return Ok(());
    }

    let max_name = past.iter().map(|&i| data.races[i].name.len()).max().unwrap_or(0);
    let display: Vec<String> = past.iter().map(|&i| {
        let r = &data.races[i];
        let date_part = fmt_date(&r.date);
        let tag = if r.actual_results.is_empty() { "(needed)" } else { "(logged)" };
        format!("{date_part}   {:<max_name$}   {tag}", r.name)
    }).collect();

    let sel = select_item(&display, "completed race", |s| s.clone());
    let race_idx = match sel {
        Some(i) => past[i],
        None => return Ok(()),
    };

    if !data.races[race_idx].actual_results.is_empty() {
        let rname = &data.races[race_idx].name.clone();
        println!("\n  WARNING: {rname} already has results logged.");
        if prompt("  Overwrite? (y/n): ").to_lowercase() != "y" {
            return Ok(());
        }
    }

    if prompt("\n  Fetch results automatically via OpenF1 API? (y/n): ").to_lowercase() == "y" {
        let year_str = prompt("  Race year (e.g. 2025): ");
        match year_str.parse::<i32>() {
            Ok(year) => {
                let race_name = data.races[race_idx].name.clone();
                let fetched = fetch_openf1_results(year, &race_name);
                if let Some(results) = fetched {
                    println!("\n  Fetched Top 10:");
                    for (i, d) in results.iter().enumerate() {
                        println!("    {:>2}.  {}", i + 1, d.name);
                    }
                    if prompt("\n  Save these results? (y/n): ").to_lowercase() == "y" {
                        let actual: Vec<ActualResult> = results.into_iter().map(Into::into).collect();
                        data.races[race_idx].actual_results = actual;
                        save_data(data)?;
                        let rname = &data.races[race_idx].name;
                        prompt(&format!("\n  ✓  Results for {rname} saved. Press Enter..."));
                        return Ok(());
                    }
                } else {
                    println!("  Could not fetch data. Falling back to manual entry.");
                }
            }
            Err(_) => println!("  Invalid year. Falling back to manual entry."),
        }
    }

    // Manual entry
    let race_name = data.races[race_idx].name.clone();
    println!("\n  Enter the TOP 10 results for {race_name}:");
    println!("  The system ignores case — use any consistent name format.");
    println!("  (Enter one driver per line, empty line to finish)");
    println!();

    let mut entries: Vec<String> = Vec::new();
    for i in 1..=10usize {
        let entry = prompt(&format!("  {:>2}. ", i));
        if entry.is_empty() {
            break;
        }
        entries.push(entry);
    }

    if !entries.is_empty() {
        data.races[race_idx].actual_results = entries.iter()
            .map(|s| ActualResult::Plain(s.clone()))
            .collect();
        save_data(data)?;
        prompt(&format!("\n  ✓  Results for {race_name} saved. Press Enter..."));
    } else {
        prompt("\n  No results entered. Press Enter...");
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Views
// ---------------------------------------------------------------------------

fn view_race_points(data: &AppData) -> anyhow::Result<()> {
    clear_screen();
    header(&["View Race Points"]);

    let today = today_str();
    let mut sorted_indices: Vec<usize> = (0..data.races.len()).collect();
    sorted_indices.sort_by(|&a, &b| {
        let da = if data.races[a].date.is_empty() { "9999-12-31" } else { &data.races[a].date };
        let db = if data.races[b].date.is_empty() { "9999-12-31" } else { &data.races[b].date };
        da.cmp(db)
    });

    let max_name = sorted_indices.iter()
        .map(|&i| data.races[i].name.len())
        .max()
        .unwrap_or(0);

    let display: Vec<String> = sorted_indices.iter().map(|&i| {
        let r = &data.races[i];
        let date_part = fmt_date(&r.date);
        let has_results = !r.actual_results.is_empty();
        let tag = if has_results { "(results logged)" } else { "(no results yet)" };
        let status = if has_results || (!r.date.is_empty() && r.date < today) {
            "[done]"
        } else {
            "[upcoming]"
        };
        format!("{date_part}   {:<max_name$}   {status}  {tag}", r.name)
    }).collect();

    let sel = select_item(&display, "race", |s| s.clone());
    let race_idx = match sel {
        Some(i) => sorted_indices[i],
        None => return Ok(()),
    };

    let race = &data.races[race_idx];
    let date_label = fmt_date(&race.date);
    println!();
    header(&[&format!("{}  •  {date_label}", race.name)]);
    println!();

    if race.actual_results.is_empty() {
        println!("  No results logged for this race yet.");
        prompt("\n  Press Enter to continue...");
        return Ok(());
    }

    let actual = &race.actual_results;

    // Score summary
    rule(Some("Scores  (lower is better)"));
    let max_pname = data.players.iter().map(|p| p.len()).max().unwrap_or(0);
    for player in &data.players {
        if let Some(pred) = race.predictions.get(player) {
            let pts = player_points_for_race(pred, actual);
            println!("  {player:<max_pname$}   {pts} pts");
        } else {
            println!("  {player:<max_pname$}   10 pts  (no prediction – penalty)");
        }
    }
    rule(None);

    // Per-player breakdown
    println!();
    for player in &data.players {
        rule(Some(&format!("Breakdown – {player}")));

        if let Some(prediction) = race.predictions.get(player) {
            let mut pts: u32 = 0;
            for i in 0..10 {
                let pred = prediction.get(i).map(|s| s.as_str());
                let actual_entry = actual.get(i);

                if pred.is_none() && actual_entry.is_none() {
                    continue;
                }

                let act_str = actual_entry.map(ActualResult::display_name).unwrap_or("(none)");
                let delta = score_position(pred, actual_entry);
                pts += delta;

                if delta == 0 {
                    println!("  P{:>2}   OK   {act_str}", i + 1);
                } else {
                    let pred_str = pred.unwrap_or("(none)");
                    println!("  P{:>2}   +1   {pred_str:?}  →  {act_str}", i + 1);
                }
            }
            println!("  {:─<30}", "");
            println!("  Total: {pts} pts");
        } else {
            println!("  No prediction submitted – +10 point penalty");
        }
        println!();
    }

    prompt("  Press Enter to continue...");
    Ok(())
}

fn view_standings(data: &AppData) {
    clear_screen();
    let (scores, races_counted) = season_standings(data);
    let mut sorted: Vec<(&String, u32)> = scores.iter().map(|(k, &v)| (k, v)).collect();
    sorted.sort_by_key(|(_, v)| *v);

    header(&[
        "Season Standings  •  Lowest Score Wins",
        &format!("After {races_counted} of {} races", data.races.len()),
    ]);
    println!();

    if sorted.is_empty() {
        println!("  No players yet.");
    } else {
        let max_pname = sorted.iter().map(|(p, _)| p.len()).max().unwrap_or(0);
        rule(None);
        println!("  {:<4} {:<max_pname$}   Points", "#", "Player");
        rule(None);
        for (i, (player, score)) in sorted.iter().enumerate() {
            println!("  {:<4} {player:<max_pname$}   {score}", i + 1);
        }
        rule(None);
    }

    println!();
    println!("  * Missing a prediction for a completed race = +10 pts");
    prompt("\n  Press Enter to continue...");
}
