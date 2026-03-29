use anyhow::Context;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

// ---------------------------------------------------------------------------
// Data model
// ---------------------------------------------------------------------------

/// One entry in `actual_results` — either a plain string (manual entry) or
/// an API result object from OpenF1.  The `#[serde(untagged)]` attribute makes
/// serde try `DriverResult` first (requires both `abbr` and `name` keys), then
/// fall back to `Plain`, matching the existing JSON file format exactly.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub(crate) enum ActualResult {
    DriverResult { abbr: String, name: String },
    Plain(String),
}

impl ActualResult {
    /// Returns a human-readable display string for this result entry.
    pub(crate) fn display_name(&self) -> &str {
        match self {
            ActualResult::DriverResult { name, .. } => name,
            ActualResult::Plain(s) => s,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct Race {
    pub(crate) name: String,
    #[serde(default)]
    pub(crate) date: String,
    #[serde(default)]
    pub(crate) actual_results: Vec<ActualResult>,
    #[serde(default)]
    pub(crate) predictions: HashMap<String, Vec<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub(crate) struct AppData {
    #[serde(default)]
    pub(crate) players: Vec<String>,
    #[serde(default)]
    pub(crate) races: Vec<Race>,
}

// ---------------------------------------------------------------------------
// I/O
// ---------------------------------------------------------------------------

pub(crate) fn data_file_path() -> PathBuf {
    std::env::var("POINTS_DATA_FILE")
        .unwrap_or_else(|_| "points_are_bad_data.json".to_string())
        .into()
}

/// Load game data from `path`.  Returns an empty `AppData` if the file does
/// not exist, matching the Python behaviour.
pub(crate) fn load_from_path(path: &Path) -> anyhow::Result<AppData> {
    if !path.exists() {
        return Ok(AppData::default());
    }
    let file = std::fs::File::open(path)
        .with_context(|| format!("opening {}", path.display()))?;
    serde_json::from_reader(file)
        .with_context(|| format!("parsing {}", path.display()))
}

/// Persist game data to `path` with pretty-printed JSON.
pub(crate) fn save_to_path(data: &AppData, path: &Path) -> anyhow::Result<()> {
    let json = serde_json::to_string_pretty(data)
        .context("serialising data")?;
    std::fs::write(path, json)
        .with_context(|| format!("writing {}", path.display()))
}

/// Load game data from the path given by `data_file_path()`.
pub(crate) fn load_data() -> anyhow::Result<AppData> {
    load_from_path(&data_file_path())
}

/// Persist game data to the path given by `data_file_path()`.
pub(crate) fn save_data(data: &AppData) -> anyhow::Result<()> {
    save_to_path(data, &data_file_path())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    fn write_json(json: &str) -> NamedTempFile {
        let mut tmp = NamedTempFile::new().unwrap();
        tmp.write_all(json.as_bytes()).unwrap();
        tmp
    }

    #[test]
    fn test_load_missing_file() {
        let data = load_from_path(Path::new("/tmp/nonexistent_points_test_xyz.json")).unwrap();
        assert!(data.players.is_empty());
        assert!(data.races.is_empty());
    }

    #[test]
    fn test_roundtrip_basic() {
        let tmp = write_json(r#"{"players":["alice","bob"],"races":[]}"#);
        let data = load_from_path(tmp.path()).unwrap();
        assert_eq!(data.players, vec!["alice", "bob"]);
        assert!(data.races.is_empty());
    }

    #[test]
    fn test_roundtrip_with_driver_result() {
        let json = r#"{
            "players": ["richu"],
            "races": [{
                "name": "Australian GP",
                "date": "2026-03-16",
                "actual_results": [{"abbr":"RUS","name":"George Russell"}],
                "predictions": {"richu": ["russell"]}
            }]
        }"#;
        let tmp = write_json(json);
        let data = load_from_path(tmp.path()).unwrap();
        assert_eq!(data.races.len(), 1);
        let r = &data.races[0];
        assert_eq!(r.actual_results.len(), 1);
        assert!(matches!(
            &r.actual_results[0],
            ActualResult::DriverResult { name, .. } if name == "George Russell"
        ));
    }

    #[test]
    fn test_roundtrip_plain_actual_result() {
        let json = r#"{
            "players": [],
            "races": [{
                "name": "Bahrain GP",
                "date": "2026-03-01",
                "actual_results": ["norris", "verstappen"],
                "predictions": {}
            }]
        }"#;
        let tmp = write_json(json);
        let data = load_from_path(tmp.path()).unwrap();
        let r = &data.races[0];
        assert!(matches!(&r.actual_results[0], ActualResult::Plain(s) if s == "norris"));
    }

    #[test]
    fn test_save_and_reload() {
        let tmp = NamedTempFile::new().unwrap();
        let mut data = AppData::default();
        data.players.push("richu".to_string());
        save_to_path(&data, tmp.path()).unwrap();
        let loaded = load_from_path(tmp.path()).unwrap();
        assert_eq!(loaded.players, vec!["richu"]);
    }

    #[test]
    fn test_live_data_roundtrip() {
        // Only run if the live data file is present
        let path = Path::new("points_are_bad_data.json");
        if !path.exists() {
            return;
        }
        let real = load_from_path(path).expect("live data file should parse cleanly");
        assert!(!real.players.is_empty());
        assert!(!real.races.is_empty());
    }
}
