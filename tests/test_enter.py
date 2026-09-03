import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from enter_matches import match_name, validate  # noqa: E402

PLAYERS = ["Somchai", "Som", "Nok", "Noknoi", "Jib", "Tom", "Anna", "Ann"]


def test_exact_beats_prefix():
    assert match_name("som", PLAYERS) == ["Som"]
    assert match_name("Ann", PLAYERS) == ["Ann"]
    assert match_name("NOK", PLAYERS) == ["Nok"]


def test_unique_prefix():
    assert match_name("somc", PLAYERS) == ["Somchai"]
    assert match_name("j", PLAYERS) == ["Jib"]


def test_ambiguous_prefix_lists_all():
    assert set(match_name("no", PLAYERS)) == {"Nok", "Noknoi"}
    assert set(match_name("an", PLAYERS)) == {"Anna", "Ann"}


def test_substring_and_fuzzy():
    assert match_name("chai", PLAYERS) == ["Somchai"]
    assert match_name("tmo", PLAYERS) == ["Tom"]          # typo -> close match
    assert match_name("zzzz", PLAYERS) == []
    assert match_name("   ", PLAYERS) == []


def test_validate_good_row():
    row, err = validate(PLAYERS, "2026-03-14", ["nok", "ji", "tom", "somc"], "21-15")
    assert err == ""
    assert row["player_a1"] == "Nok" and row["player_a2"] == "Jib"
    assert row["player_b1"] == "Tom" and row["player_b2"] == "Somchai"
    assert row["winner"] == "A" and row["score_a"] == "21" and row["score_b"] == "15"
    assert row["date"] == "2026-03-14"


def test_validate_errors():
    assert "Date" in validate(PLAYERS, "14/03/2026", ["nok", "jib", "tom", "som"], "")[1]
    assert "could be" in validate(PLAYERS, "2026-03-14", ["no", "jib", "tom", "som"], "")[1]
    assert "no player" in validate(PLAYERS, "2026-03-14", ["xyz", "jib", "tom", "som"], "")[1]
    assert "twice" in validate(PLAYERS, "2026-03-14", ["nok", "nok", "tom", "som"], "")[1]
    assert "Score" in validate(PLAYERS, "2026-03-14", ["nok", "jib", "tom", "som"], "21")[1]
    assert "higher" in validate(PLAYERS, "2026-03-14", ["nok", "jib", "tom", "som"], "15-21")[1]
    row, err = validate(PLAYERS, "2026-03-14", ["nok", "jib", "tom", "som"], "")
    assert err == "" and row["score_a"] == "" and row["score_b"] == ""
