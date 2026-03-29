/// External API integration (OpenF1).
///
/// IMPORTANT: Follow the strict endpoint sequence for fetching race results:
///   /meetings → /sessions → /session_result → /drivers (using meeting_key,
///   NOT session_key — using session_key returns null broadcast_name values).
///
/// Functions here may print progress messages but do NOT call `save_data` or
/// mutate shared state — that is the CLI layer's job.
use crate::storage::{ActualResult, Race};
use serde::de::DeserializeOwned;
use serde::Deserialize;
use std::collections::HashMap;
use std::time::Duration;

// ---------------------------------------------------------------------------
// Public (crate-internal) types
// ---------------------------------------------------------------------------

/// Slim driver result returned from OpenF1, stored in `actual_results`.
/// Serialized as `{"abbr": "RUS", "name": "George Russell"}`.
pub(crate) struct FetchedDriver {
    pub(crate) abbr: String,
    pub(crate) name: String,
}

impl From<FetchedDriver> for ActualResult {
    fn from(d: FetchedDriver) -> Self {
        ActualResult::DriverResult { abbr: d.abbr, name: d.name }
    }
}

pub(crate) struct DateUpdate {
    pub(crate) race_index: usize,
    pub(crate) new_date: String,
}

// ---------------------------------------------------------------------------
// Internal OpenF1 serde types
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct OpenF1Meeting {
    meeting_key: u64,
    meeting_name: String,
    country_name: Option<String>,
    location: Option<String>,
    date_start: Option<String>,
}

#[derive(Deserialize)]
struct OpenF1Session {
    session_key: u64,
    session_name: Option<String>,
}

#[derive(Deserialize)]
struct OpenF1SessionResult {
    driver_number: serde_json::Value,
    position: u32,
}

#[derive(Deserialize)]
struct OpenF1Driver {
    driver_number: serde_json::Value,
    name_acronym: Option<String>,
    first_name: Option<String>,
    last_name: Option<String>,
    broadcast_name: Option<String>,
}

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

/// Fetch JSON from `url` with a 10-second timeout.  Returns `None` on any
/// network or parse error, printing a brief message to stderr.
fn fetch_json<T: DeserializeOwned>(url: &str) -> Option<T> {
    let result = ureq::get(url)
        .timeout(Duration::from_secs(10))
        .set("User-Agent", "points-are-bad/1.0")
        .call();

    match result {
        Ok(resp) => {
            match resp.into_json::<T>() {
                Ok(v) => Some(v),
                Err(e) => {
                    eprintln!("  [!] JSON parse error from {url}: {e}");
                    None
                }
            }
        }
        Err(e) => {
            eprintln!("  [!] Request error for {url}: {e}");
            None
        }
    }
}

fn driver_number_str(val: &serde_json::Value) -> String {
    match val {
        serde_json::Value::Number(n) => n.to_string(),
        serde_json::Value::String(s) => s.clone(),
        _ => val.to_string(),
    }
}

// ---------------------------------------------------------------------------
// OpenF1 race results
// ---------------------------------------------------------------------------

/// Fetch the top-10 results for `race_name` from the OpenF1 API.
///
/// Follows the required endpoint sequence:
///   /meetings → /sessions → /session_result → /drivers (meeting_key)
///
/// Returns `None` when results are unavailable.
pub(crate) fn fetch_openf1_results(year: i32, race_name: &str) -> Option<Vec<FetchedDriver>> {
    println!("\n  Fetching from OpenF1 API: {race_name} ({year})...");

    // Step 1: resolve meeting key
    let meetings: Vec<OpenF1Meeting> =
        fetch_json(&format!("https://api.openf1.org/v1/meetings?year={year}"))?;

    let target = meetings.iter().find(|m| {
        let mn = m.meeting_name.to_lowercase();
        let rn = race_name.to_lowercase();
        mn.contains(&rn) || rn.contains(&mn)
    }).or_else(|| {
        meetings.iter().find(|m| {
            let rn = race_name.to_lowercase();
            m.country_name.as_deref().unwrap_or("").to_lowercase().contains(&rn)
                || rn.contains(&m.country_name.as_deref().unwrap_or("").to_lowercase())
                || m.location.as_deref().unwrap_or("").to_lowercase().contains(&rn)
                || rn.contains(&m.location.as_deref().unwrap_or("").to_lowercase())
        })
    })?;

    let meeting_key = target.meeting_key;
    let meeting_name = &target.meeting_name;

    // Step 2: find the Race session
    let sessions: Vec<OpenF1Session> = fetch_json(
        &format!("https://api.openf1.org/v1/sessions?meeting_key={meeting_key}&session_type=Race")
    )?;

    if sessions.is_empty() {
        eprintln!("  [!] No Race session found for {meeting_name}.");
        return None;
    }

    let session_key = sessions[0].session_key;
    let session_name = sessions[0].session_name.as_deref().unwrap_or("Race");
    println!("  Found: {meeting_name} – {session_name} (key: {session_key})");

    // Step 3: fetch session results (top 10 by position)
    let mut res_data: Vec<OpenF1SessionResult> = fetch_json(
        &format!("https://api.openf1.org/v1/session_result?session_key={session_key}&position<=10")
    )?;

    if res_data.is_empty() {
        eprintln!("  [!] OpenF1 does not have session_results populated yet.");
        return None;
    }

    res_data.sort_by_key(|r| r.position);

    // Step 4: fetch driver metadata via meeting_key (NOT session_key —
    // session_key can return null broadcast_name values)
    let drivers_data: Vec<OpenF1Driver> = fetch_json(
        &format!("https://api.openf1.org/v1/drivers?meeting_key={meeting_key}")
    ).unwrap_or_default();

    // Build driver map: driver_number -> best driver entry
    let mut driver_map: HashMap<String, &OpenF1Driver> = HashMap::new();
    for d in &drivers_data {
        let num = driver_number_str(&d.driver_number);
        let should_replace = driver_map.get(&num).is_none_or(|existing| {
            // Prefer entries with a broadcast_name or full_name over those without
            d.broadcast_name.is_some() || d.first_name.is_some() || d.last_name.is_some()
                && existing.broadcast_name.is_none() && existing.first_name.is_none()
        });
        if should_replace {
            driver_map.insert(num, d);
        }
    }

    let results: Vec<FetchedDriver> = res_data.iter().take(10).map(|res| {
        let num = driver_number_str(&res.driver_number);
        let info = driver_map.get(&num);
        let first = info.and_then(|d| d.first_name.as_deref()).unwrap_or("").trim().to_string();
        let last = info.and_then(|d| d.last_name.as_deref()).unwrap_or("").trim().to_string();
        let name = if first.is_empty() && last.is_empty() {
            num.clone()
        } else if first.is_empty() {
            last
        } else {
            format!("{first} {last}")
        };
        let abbr = info
            .and_then(|d| d.name_acronym.as_deref())
            .unwrap_or("")
            .trim()
            .to_string();
        FetchedDriver { abbr, name }
    }).collect();

    Some(results)
}

// ---------------------------------------------------------------------------
// Schedule updates
// ---------------------------------------------------------------------------

/// Fetch the current-season F1 schedule from OpenF1 and diff it against
/// `existing_races`.
///
/// Returns `(new_races, date_updates)`:
/// - `new_races`    — races in the schedule not yet in `existing_races`
/// - `date_updates` — existing races whose date should be updated
///
/// Does not mutate `existing_races` or call `save_data`.
pub(crate) fn get_schedule_updates(
    existing_races: &[Race],
) -> anyhow::Result<(Vec<Race>, Vec<DateUpdate>)> {
    let year = chrono::Local::now().format("%Y").to_string();
    let url = format!("https://api.openf1.org/v1/meetings?year={year}");

    let meetings: Vec<OpenF1Meeting> = fetch_json(&url)
        .ok_or_else(|| anyhow::anyhow!("Failed to fetch schedule from OpenF1"))?;

    let mut new_races = Vec::new();
    let mut date_updates = Vec::new();

    for m in meetings {
        // Skip pre-season testing
        if m.meeting_name.to_lowercase().contains("test") {
            continue;
        }

        // Extract YYYY-MM-DD from the ISO datetime string
        let date_str = m.date_start
            .as_deref()
            .and_then(|s| s.get(..10))
            .unwrap_or("")
            .to_string();

        let existing_idx = existing_races.iter().position(|r| {
            r.name.to_lowercase() == m.meeting_name.to_lowercase()
        });

        match existing_idx {
            Some(idx) => {
                let existing = &existing_races[idx];
                if existing.date.is_empty() && !date_str.is_empty() {
                    date_updates.push(DateUpdate { race_index: idx, new_date: date_str });
                }
            }
            None => {
                new_races.push(Race {
                    name: m.meeting_name.clone(),
                    date: date_str,
                    actual_results: Vec::new(),
                    predictions: HashMap::new(),
                });
            }
        }
    }

    Ok((new_races, date_updates))
}
