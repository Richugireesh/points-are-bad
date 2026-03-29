use crate::storage::{ActualResult, AppData};
use std::collections::HashMap;
use std::sync::OnceLock;

// ---------------------------------------------------------------------------
// Alias table
// ---------------------------------------------------------------------------

static ALIASES: OnceLock<HashMap<&'static str, &'static str>> = OnceLock::new();

fn aliases() -> &'static HashMap<&'static str, &'static str> {
    ALIASES.get_or_init(|| {
        let mut m = HashMap::new();
        m.insert("kimi",    "antonelli");
        m.insert("lec",     "leclerc");
        m.insert("ver",     "verstappen");
        m.insert("max",     "verstappen");
        m.insert("ham",     "hamilton");
        m.insert("nor",     "norris");
        m.insert("pia",     "piastri");
        m.insert("rus",     "russell");
        m.insert("lind",    "lindblad");
        m.insert("linblad", "lindblad");
        m.insert("bor",     "bortoleto");
        m.insert("gabby",   "bortoleto");
        m.insert("gab",     "bortoleto");
        m.insert("hadj",    "hadjar");
        m.insert("alo",     "alonso");
        m.insert("per",     "perez");
        m.insert("checo",   "perez");
        m.insert("gas",     "gasly");
        m.insert("oco",     "ocon");
        m.insert("tsu",     "tsunoda");
        m.insert("yuki",    "tsunoda");
        m.insert("hul",     "hulkenberg");
        m.insert("str",     "stroll");
        m.insert("mag",     "magnussen");
        m.insert("alb",     "albon");
        m.insert("col",     "colapinto");
        m.insert("bea",     "bearman");
        m.insert("ollie",   "bearman");
        m.insert("sai",     "sainz");
        m.insert("zho",     "zhou");
        m.insert("bot",     "bottas");
        m.insert("law",     "lawson");
        m.insert("doo",     "doohan");
        m
    })
}

// ---------------------------------------------------------------------------
// Core matching logic
// ---------------------------------------------------------------------------

/// Lowercase, strip hidden Unicode formatting chars (U+2060, U+200B), then
/// resolve aliases.  Mirrors `scoring._normalize()` in Python exactly.
pub(crate) fn normalize(s: &str) -> String {
    let cleaned: String = s
        .chars()
        .filter(|&c| c != '\u{2060}' && c != '\u{200B}')
        .collect();
    let lower = cleaned.trim().to_lowercase();
    aliases()
        .get(lower.as_str())
        .copied()
        .unwrap_or(lower.as_str())
        .to_string()
}

/// Return `true` if *prediction* matches *actual*.
///
/// Matching is case-insensitive and alias-aware.  A substring match on
/// normalised values is accepted (e.g. "perez" matches "S PEREZ").
pub(crate) fn matches_actual(prediction: &str, actual: &ActualResult) -> bool {
    let p = normalize(prediction);
    let check = |val: &str| -> bool {
        if val.is_empty() {
            return false;
        }
        let v = normalize(val);
        p == v || v.contains(p.as_str())
    };
    match actual {
        ActualResult::DriverResult { abbr, name } => check(abbr) || check(name),
        ActualResult::Plain(s) => check(s),
    }
}

/// Return `0` (match) or `1` (mismatch) for one finishing position.
///
/// Both `None` → 0 (no comparison possible).  One `None` → 1 (mismatch).
pub(crate) fn score_position(pred: Option<&str>, actual: Option<&ActualResult>) -> u32 {
    match (pred, actual) {
        (None, None) => 0,
        (None, Some(_)) | (Some(_), None) => 1,
        (Some(p), Some(a)) => u32::from(!matches_actual(p, a)),
    }
}

/// Total points for one player in one race.
///
/// Iterates over all 10 positions (or however many exist in either list).
/// The +10 missing-prediction penalty is the **caller's responsibility**.
pub(crate) fn player_points_for_race(prediction: &[String], actual: &[ActualResult]) -> u32 {
    let n = prediction.len().max(actual.len()).max(10);
    (0..n)
        .map(|i| {
            score_position(
                prediction.get(i).map(String::as_str),
                actual.get(i),
            )
        })
        .sum()
}

/// Return `(player -> total_points, races_with_results_count)`.
///
/// Applies the +10 missing-prediction penalty for every race that has actual
/// results but no prediction from a given player.
#[must_use]
pub(crate) fn season_standings(data: &AppData) -> (HashMap<String, u32>, usize) {
    let mut scores: HashMap<String, u32> = data.players.iter()
        .map(|p| (p.clone(), 0))
        .collect();
    let mut counted = 0;

    for race in &data.races {
        if race.actual_results.is_empty() {
            continue;
        }
        counted += 1;
        for player in &data.players {
            let pts = race.predictions.get(player).map_or(10, |pred| {
                player_points_for_race(pred, &race.actual_results)
            });
            *scores.entry(player.clone()).or_insert(0) += pts;
        }
    }

    (scores, counted)
}

// ---------------------------------------------------------------------------
// Tests (ported from tests/test_scoring.py)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn plain(s: &str) -> ActualResult {
        ActualResult::Plain(s.to_string())
    }

    fn driver(abbr: &str, name: &str) -> ActualResult {
        ActualResult::DriverResult {
            abbr: abbr.to_string(),
            name: name.to_string(),
        }
    }

    // --- normalize ---

    #[test]
    fn normalize_lowercases() {
        assert_eq!(normalize("Verstappen"), "verstappen");
        assert_eq!(normalize("NORRIS"), "norris");
    }

    #[test]
    fn normalize_strips_whitespace() {
        assert_eq!(normalize("  norris  "), "norris");
    }

    #[test]
    fn normalize_removes_hidden_chars() {
        assert_eq!(normalize("nor\u{2060}ris"), "norris");
        assert_eq!(normalize("norris\u{200B}"), "norris");
    }

    #[test]
    fn normalize_resolves_aliases() {
        assert_eq!(normalize("ver"), "verstappen");
        assert_eq!(normalize("max"), "verstappen");
        assert_eq!(normalize("kimi"), "antonelli");
        assert_eq!(normalize("checo"), "perez");
        assert_eq!(normalize("ollie"), "bearman");
    }

    #[test]
    fn normalize_passthrough() {
        assert_eq!(normalize("verstappen"), "verstappen");
        assert_eq!(normalize("norris"), "norris");
    }

    // --- matches_actual (string) ---

    #[test]
    fn matches_plain_exact() {
        assert!(matches_actual("norris", &plain("norris")));
    }

    #[test]
    fn matches_plain_case_insensitive() {
        assert!(matches_actual("Norris", &plain("norris")));
        assert!(matches_actual("norris", &plain("NORRIS")));
    }

    #[test]
    fn matches_plain_substring() {
        assert!(matches_actual("perez", &plain("S PEREZ")));
    }

    #[test]
    fn matches_plain_alias() {
        assert!(matches_actual("ver", &plain("verstappen")));
        assert!(matches_actual("max", &plain("verstappen")));
    }

    #[test]
    fn matches_plain_no_match() {
        assert!(!matches_actual("norris", &plain("verstappen")));
    }

    #[test]
    fn matches_plain_hidden_chars() {
        assert!(matches_actual("norris\u{2060}", &plain("norris")));
    }

    // --- matches_actual (dict / DriverResult) ---

    #[test]
    fn matches_driver_result_by_name() {
        assert!(matches_actual("russell", &driver("RUS", "George Russell")));
    }

    #[test]
    fn matches_driver_result_by_abbr() {
        assert!(matches_actual("rus", &driver("RUS", "George Russell")));
    }

    #[test]
    fn matches_driver_result_substring() {
        assert!(matches_actual("perez", &driver("PER", "Sergio Perez")));
    }

    #[test]
    fn matches_driver_result_alias() {
        assert!(matches_actual("max", &driver("VER", "Max Verstappen")));
    }

    #[test]
    fn matches_driver_result_no_match() {
        assert!(!matches_actual("norris", &driver("VER", "Max Verstappen")));
    }

    // --- score_position ---

    #[test]
    fn score_both_none() {
        assert_eq!(score_position(None, None), 0);
    }

    #[test]
    fn score_pred_none() {
        assert_eq!(score_position(None, Some(&plain("norris"))), 1);
    }

    #[test]
    fn score_actual_none() {
        assert_eq!(score_position(Some("norris"), None), 1);
    }

    #[test]
    fn score_match() {
        assert_eq!(score_position(Some("norris"), Some(&plain("norris"))), 0);
    }

    #[test]
    fn score_mismatch() {
        assert_eq!(score_position(Some("norris"), Some(&plain("verstappen"))), 1);
    }

    #[test]
    fn score_alias_match() {
        assert_eq!(score_position(Some("ver"), Some(&plain("verstappen"))), 0);
    }

    // --- player_points_for_race ---

    #[test]
    fn points_perfect_prediction() {
        let pred: Vec<String> = ["norris","verstappen","piastri","leclerc","hamilton",
                                  "russell","antonelli","alonso","stroll","sainz"]
            .iter().map(|s| s.to_string()).collect();
        let actual: Vec<ActualResult> = pred.iter().map(|s| plain(s)).collect();
        assert_eq!(player_points_for_race(&pred, &actual), 0);
    }

    #[test]
    fn points_all_wrong() {
        let pred: Vec<String> = vec!["norris".to_string(); 10];
        let actual: Vec<ActualResult> = vec![plain("verstappen"); 10];
        assert_eq!(player_points_for_race(&pred, &actual), 10);
    }

    #[test]
    fn points_empty_prediction() {
        let actual: Vec<ActualResult> = ["norris","verstappen","piastri","leclerc","hamilton",
                                          "russell","antonelli","alonso","stroll","sainz"]
            .iter().map(|s| plain(s)).collect();
        assert_eq!(player_points_for_race(&[], &actual), 10);
    }

    #[test]
    fn points_short_prediction() {
        let pred: Vec<String> = vec!["norris".to_string()];
        let actual: Vec<ActualResult> = vec![plain("norris"), plain("verstappen")];
        // n = max(1, 2, 10) = 10
        // P1: norris==norris -> 0
        // P2: pred=None, actual=verstappen -> 1
        // P3-P10: both None -> 0
        // Total = 1
        assert_eq!(player_points_for_race(&pred, &actual), 1);
    }

    #[test]
    fn points_with_driver_result() {
        let pred = vec!["russell".to_string()];
        let actual = vec![driver("RUS", "George Russell")];
        // 1 match, then 9 mismatches (pred=None, actual=None after pos 1)
        // actual.len()=1, pred.len()=1, n=max(1,1,10)=10
        // P1: match=0, P2-P10: both None=0 => total 0
        assert_eq!(player_points_for_race(&pred, &actual), 0);
    }

    // --- season_standings ---

    fn make_data_single_race() -> AppData {
        use crate::storage::Race;
        use std::collections::HashMap;
        let mut predictions = HashMap::new();
        predictions.insert("alice".to_string(),
            vec!["norris".to_string(), "verstappen".to_string()]);
        AppData {
            players: vec!["alice".to_string(), "bob".to_string()],
            races: vec![Race {
                name: "Bahrain GP".to_string(),
                date: "2026-03-01".to_string(),
                actual_results: vec![plain("norris"), plain("verstappen")],
                predictions,
            }],
        }
    }

    #[test]
    fn standings_counted_races() {
        let data = make_data_single_race();
        let (_, counted) = season_standings(&data);
        assert_eq!(counted, 1);
    }

    #[test]
    fn standings_player_with_prediction() {
        let data = make_data_single_race();
        let (scores, _) = season_standings(&data);
        // alice: P1 norris=norris(0), P2 ver=verstappen(0), P3-P10 both None(0) = 0 pts
        assert_eq!(scores["alice"], 0);
    }

    #[test]
    fn standings_missing_prediction_penalty() {
        let data = make_data_single_race();
        let (scores, _) = season_standings(&data);
        // bob has no prediction -> +10 penalty
        assert_eq!(scores["bob"], 10);
    }

    #[test]
    fn standings_no_results_skipped() {
        use crate::storage::Race;
        let data = AppData {
            players: vec!["alice".to_string()],
            races: vec![Race {
                name: "Future GP".to_string(),
                date: "2099-01-01".to_string(),
                actual_results: vec![],
                predictions: HashMap::new(),
            }],
        };
        let (scores, counted) = season_standings(&data);
        assert_eq!(counted, 0);
        assert_eq!(scores["alice"], 0);
    }
}
