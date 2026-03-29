"""Tests for points_are_bad.drivers."""

from points_are_bad.drivers import ROSTER, by_abbr, by_key


class TestRoster:
    def test_has_22_drivers(self):
        assert len(ROSTER) == 22

    def test_all_drivers_have_required_fields(self):
        for driver in ROSTER:
            assert driver["abbr"]
            assert driver["name"]
            assert driver["team"]
            assert driver["key"]

    def test_no_duplicate_abbrs(self):
        abbrs = [d["abbr"] for d in ROSTER]
        assert len(abbrs) == len(set(abbrs))

    def test_no_duplicate_keys(self):
        keys = [d["key"] for d in ROSTER]
        assert len(keys) == len(set(keys))

    def test_all_keys_lowercase(self):
        for driver in ROSTER:
            assert driver["key"] == driver["key"].lower()

    def test_all_abbrs_uppercase(self):
        for driver in ROSTER:
            assert driver["abbr"] == driver["abbr"].upper()


class TestByKey:
    def test_returns_driver_for_known_key(self):
        driver = by_key("verstappen")
        assert driver is not None
        assert driver["abbr"] == "VER"

    def test_returns_none_for_unknown_key(self):
        assert by_key("nobody") is None

    def test_case_insensitive(self):
        assert by_key("VERSTAPPEN") == by_key("verstappen")

    def test_returns_correct_team(self):
        driver = by_key("norris")
        assert driver is not None
        assert driver["team"] == "McLaren"

    def test_all_roster_keys_are_findable(self):
        for d in ROSTER:
            assert by_key(d["key"]) is not None


class TestByAbbr:
    def test_returns_driver_for_known_abbr(self):
        driver = by_abbr("VER")
        assert driver is not None
        assert driver["key"] == "verstappen"

    def test_returns_none_for_unknown_abbr(self):
        assert by_abbr("ZZZ") is None

    def test_case_insensitive(self):
        assert by_abbr("ver") == by_abbr("VER")

    def test_all_roster_abbrs_are_findable(self):
        for d in ROSTER:
            assert by_abbr(d["abbr"]) is not None
