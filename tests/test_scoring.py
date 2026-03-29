"""Tests for points_are_bad.scoring.

Covers every public function as well as critical edge cases identified in the
code review:
  - Alias normalisation (module-level constant, not rebuilt per call)
  - Hidden-character stripping
  - Dict vs string matching for FastF1/OpenF1 result objects
  - score_position as the single source of truth for per-position points
  - calculate_player_points_for_race with short/long prediction/actual lists
  - calculate_season_standings with missing predictions (+10 penalty)
"""

from points_are_bad.scoring import (
    ALIASES,
    _normalize,
    calculate_player_points_for_race,
    calculate_season_standings,
    calculate_str_equality,
    score_position,
)

# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_lowercases(self):
        assert _normalize("Verstappen") == "verstappen"

    def test_strips_whitespace(self):
        assert _normalize("  norris  ") == "norris"

    def test_removes_word_joiner(self):
        assert _normalize("ver\u2060stappen") == "verstappen"

    def test_removes_zero_width_space(self):
        assert _normalize("ver\u200bstappen") == "verstappen"

    def test_alias_resolution(self):
        assert _normalize("ver") == "verstappen"
        assert _normalize("max") == "verstappen"
        assert _normalize("kimi") == "antonelli"
        assert _normalize("checo") == "perez"

    def test_no_alias_passthrough(self):
        assert _normalize("hamilton") == "hamilton"

    def test_alias_table_is_module_constant(self):
        # ALIASES must be a dict at module level (not rebuilt per call).
        assert isinstance(ALIASES, dict)
        assert len(ALIASES) > 0


# ---------------------------------------------------------------------------
# calculate_str_equality – string vs string
# ---------------------------------------------------------------------------


class TestCalculateStrEqualityStrings:
    def test_exact_match(self):
        assert calculate_str_equality("verstappen", "verstappen")

    def test_case_insensitive(self):
        assert calculate_str_equality("Verstappen", "VERSTAPPEN")

    def test_alias_prediction_side(self):
        assert calculate_str_equality("ver", "verstappen")

    def test_alias_both_sides(self):
        assert calculate_str_equality("ver", "max")  # both -> "verstappen"

    def test_substring_match(self):
        # "perez" is contained in "s perez"
        assert calculate_str_equality("perez", "s perez")

    def test_no_match(self):
        assert not calculate_str_equality("hamilton", "verstappen")

    def test_hidden_chars_stripped_from_prediction(self):
        assert calculate_str_equality("ver\u2060", "verstappen")

    def test_none_string_sentinel_does_not_match_driver(self):
        # "(None)" should not match a real driver name.
        assert not calculate_str_equality("(None)", "verstappen")

    def test_none_string_matches_itself(self):
        # This edge case is handled upstream by score_position.
        assert calculate_str_equality("(None)", "(None)")


# ---------------------------------------------------------------------------
# calculate_str_equality – dict (FastF1 / OpenF1 result object)
# ---------------------------------------------------------------------------


class TestCalculateStrEqualityDict:
    VERSTAPPEN = {
        "BroadcastName": "M VERSTAPPEN",
        "FirstName": "Max",
        "LastName": "Verstappen",
        "Abbreviation": "VER",
    }

    def test_exact_last_name(self):
        assert calculate_str_equality("verstappen", self.VERSTAPPEN)

    def test_abbreviation_match(self):
        assert calculate_str_equality("VER", self.VERSTAPPEN)

    def test_alias_to_dict(self):
        assert calculate_str_equality("max", self.VERSTAPPEN)

    def test_first_name_match(self):
        assert calculate_str_equality("Max", self.VERSTAPPEN)

    def test_broadcast_name_substring(self):
        # "verstappen" is a substring of "M VERSTAPPEN" after normalisation
        assert calculate_str_equality("verstappen", self.VERSTAPPEN)

    def test_no_match(self):
        assert not calculate_str_equality("hamilton", self.VERSTAPPEN)

    def test_empty_values_in_dict_ignored(self):
        sparse = {
            "BroadcastName": "",
            "FirstName": None,
            "LastName": "Verstappen",
            "Abbreviation": "",
        }  # noqa: E501
        assert calculate_str_equality("verstappen", sparse)

    def test_none_sentinel_does_not_match_dict(self):
        assert not calculate_str_equality("(None)", self.VERSTAPPEN)


# ---------------------------------------------------------------------------
# score_position
# ---------------------------------------------------------------------------


class TestScorePosition:
    VER_DICT = {
        "BroadcastName": "M VERSTAPPEN",
        "FirstName": "Max",
        "LastName": "Verstappen",
        "Abbreviation": "VER",
    }

    def test_match_returns_zero(self):
        assert score_position("verstappen", self.VER_DICT) == 0

    def test_mismatch_returns_one(self):
        assert score_position("hamilton", self.VER_DICT) == 1

    def test_both_none_returns_zero(self):
        assert score_position(None, None) == 0

    def test_pred_none_actual_present_returns_one(self):
        assert score_position(None, self.VER_DICT) == 1

    def test_actual_none_pred_present_returns_one(self):
        assert score_position("verstappen", None) == 1

    def test_string_actual_match(self):
        assert score_position("perez", "perez") == 0

    def test_string_actual_mismatch(self):
        assert score_position("perez", "hamilton") == 1


# ---------------------------------------------------------------------------
# calculate_player_points_for_race
# ---------------------------------------------------------------------------

# Fixture helpers: use plain strings for simplicity (string path of
# calculate_str_equality is exercised).
ACTUAL_10 = [
    "verstappen",
    "norris",
    "piastri",
    "leclerc",
    "hamilton",
    "russell",
    "sainz",
    "alonso",
    "perez",
    "stroll",
]


class TestCalculatePlayerPointsForRace:
    def test_perfect_prediction_zero_points(self):
        prediction = list(ACTUAL_10)
        assert calculate_player_points_for_race(prediction, ACTUAL_10) == 0

    def test_all_wrong_ten_points(self):
        # Use values that cannot accidentally substring-match any driver name.
        # Single-char values like "j" would match "stroll" via the substring
        # path, which is intentional app behaviour, not a bug.
        prediction = [
            "zzz1",
            "zzz2",
            "zzz3",
            "zzz4",
            "zzz5",
            "zzz6",
            "zzz7",
            "zzz8",
            "zzz9",
            "zzz10",
        ]
        assert calculate_player_points_for_race(prediction, ACTUAL_10) == 10

    def test_one_wrong_one_point(self):
        prediction = list(ACTUAL_10)
        prediction[0] = "hamilton"  # P1 wrong
        assert calculate_player_points_for_race(prediction, ACTUAL_10) == 1

    def test_alias_counted_as_correct(self):
        prediction = list(ACTUAL_10)
        prediction[0] = "max"  # alias for verstappen
        assert calculate_player_points_for_race(prediction, ACTUAL_10) == 0

    def test_prediction_shorter_than_actual(self):
        # Prediction has 8 entries, actual has 10 -> +2 for missing positions
        prediction = ACTUAL_10[:8]
        assert calculate_player_points_for_race(prediction, ACTUAL_10) == 2

    def test_actual_shorter_than_prediction(self):
        # Actual has 8 entries, prediction has 10 -> +2 for missing actuals
        actual = ACTUAL_10[:8]
        prediction = list(ACTUAL_10)
        assert calculate_player_points_for_race(prediction, actual) == 2

    def test_both_lists_shorter_than_ten_same_entries(self):
        # Both have 8 correct entries, positions 9-10 are both None -> 0 pts
        short = ACTUAL_10[:8]
        assert calculate_player_points_for_race(short, short) == 0

    def test_empty_prediction_gives_ten_points(self):
        assert calculate_player_points_for_race([], ACTUAL_10) == 10

    def test_uses_dict_actual(self):
        actual_dicts = [
            {
                "BroadcastName": n.upper(),
                "FirstName": "",
                "LastName": n,
                "Abbreviation": n[:3].upper(),
            }
            for n in ACTUAL_10
        ]
        prediction = list(ACTUAL_10)
        assert calculate_player_points_for_race(prediction, actual_dicts) == 0


# ---------------------------------------------------------------------------
# calculate_season_standings
# ---------------------------------------------------------------------------


def _make_race(name, actual, predictions):
    return {
        "name": name,
        "date": "2026-03-01",
        "actual_results": actual,
        "predictions": predictions,
    }


class TestCalculateSeasonStandings:
    def test_no_races_with_results(self):
        data = {
            "players": ["alice", "bob"],
            "races": [_make_race("Bahrain GP", [], {})],
        }
        scores, counted = calculate_season_standings(data)
        assert counted == 0
        assert scores == {"alice": 0, "bob": 0}

    def test_perfect_predictions_zero_points(self):
        actual = list(ACTUAL_10)
        data = {
            "players": ["alice"],
            "races": [_make_race("Bahrain GP", actual, {"alice": actual})],
        }
        scores, counted = calculate_season_standings(data)
        assert counted == 1
        assert scores["alice"] == 0

    def test_missing_prediction_adds_ten_point_penalty(self):
        actual = list(ACTUAL_10)
        data = {
            "players": ["alice", "bob"],
            "races": [_make_race("Bahrain GP", actual, {"alice": actual})],
            # bob has no prediction
        }
        scores, counted = calculate_season_standings(data)
        assert counted == 1
        assert scores["alice"] == 0
        assert scores["bob"] == 10

    def test_multiple_races_accumulate(self):
        actual = list(ACTUAL_10)
        race1 = _make_race("Bahrain GP", actual, {"alice": actual})
        race2 = _make_race("Saudi GP", actual, {"alice": actual})
        data = {"players": ["alice"], "races": [race1, race2]}
        scores, counted = calculate_season_standings(data)
        assert counted == 2
        assert scores["alice"] == 0

    def test_missing_prediction_penalty_per_race(self):
        actual = list(ACTUAL_10)
        race1 = _make_race("Bahrain GP", actual, {})
        race2 = _make_race("Saudi GP", actual, {})
        data = {"players": ["alice"], "races": [race1, race2]}
        scores, counted = calculate_season_standings(data)
        assert counted == 2
        assert scores["alice"] == 20  # 10 per race

    def test_player_not_in_predictions_penalised(self):
        actual = list(ACTUAL_10)
        data = {
            "players": ["alice", "bob"],
            "races": [_make_race("Bahrain GP", actual, {"alice": actual})],
        }
        scores, _ = calculate_season_standings(data)
        assert scores["bob"] == 10

    def test_one_wrong_prediction(self):
        actual = list(ACTUAL_10)
        wrong = list(ACTUAL_10)
        wrong[0] = "hamilton"
        data = {
            "players": ["alice"],
            "races": [_make_race("Bahrain GP", actual, {"alice": wrong})],
        }
        scores, _ = calculate_season_standings(data)
        assert scores["alice"] == 1

    def test_no_players(self):
        actual = list(ACTUAL_10)
        data = {
            "players": [],
            "races": [_make_race("Bahrain GP", actual, {})],
        }
        scores, counted = calculate_season_standings(data)
        assert counted == 1
        assert scores == {}
