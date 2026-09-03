import textwrap

import pytest

from badminton_stats.load import ValidationError, load_matches, load_players

PLAYERS = ["Ace", "Nok", "Tom", "Pim", "Somchai"]
HEADER = "Timestamp,date,player_a1,player_a2,player_b1,player_b2,winner,score_a,score_b\n"


def _csv(tmp_path, body):
    p = tmp_path / "m.csv"
    p.write_text(HEADER + textwrap.dedent(body), encoding="utf-8")
    return str(p)


def test_good_file_sorted_stable_with_match_ids(tmp_path):
    src = _csv(tmp_path, """\
        x,2026-02-01,Ace,Nok,Tom,Pim,A,21,15
        x,2026-01-05,Tom,Pim,Ace,Nok,B,,
        x,2026-01-05,Ace,Tom,Nok,Pim,A,22,20
        """)
    df = load_matches(src, PLAYERS)
    assert list(df["match_id"]) == [1, 2, 3]
    assert [d.strftime("%Y-%m-%d") for d in df["date"]] == ["2026-01-05", "2026-01-05", "2026-02-01"]
    # same-day rows keep sheet order: the Tom/Pim row was first in the sheet
    assert df.iloc[0]["player_a1"] == "Tom"
    assert df.iloc[0]["score_a"] is not None and str(df.iloc[0]["score_a"]) == "<NA>"
    assert int(df.iloc[2]["score_a"]) == 21


def test_unknown_player_fails_with_hint_and_row(tmp_path):
    src = _csv(tmp_path, "x,2026-01-05,Ace,Nokk,Tom,Pim,A,21,15\n")
    with pytest.raises(ValidationError) as ei:
        load_matches(src, PLAYERS)
    msg = str(ei.value)
    assert "row 2" in msg and "'Nokk'" in msg and "did you mean 'Nok'" in msg


def test_all_problems_reported_at_once(tmp_path):
    src = _csv(tmp_path, """\
        x,2026-01-05,Ace,Ace,Tom,Pim,A,21,15
        x,2026-01-06,Ace,Nok,Tom,Pim,C,21,15
        x,2026-01-07,Ace,Nok,Tom,Pim,A,15,21
        x,2026-01-08,Ace,Nok,Tom,Pim,A,21,
        x,not-a-date,Ace,Nok,Tom,Pim,A,21,15
        x,2026-01-10,Ace,Nok,Tom,Pim,A,21,21
        x,,Ace,Nok,Tom,Pim,A,21,15
        """)
    with pytest.raises(ValidationError) as ei:
        load_matches(src, PLAYERS)
    msg = str(ei.value)
    assert "7 problem(s)" in msg
    assert "row 2: same player appears twice" in msg
    assert "row 3: winner must be exactly 'A' or 'B'" in msg
    assert "row 4: score 15-21 says team B won but winner column says A" in msg
    assert "row 5: only one score" in msg
    assert "row 6: cannot parse date 'not-a-date'" in msg
    assert "row 7: scores are equal" in msg
    assert "row 8: date is blank" in msg


def test_missing_column_is_reported(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("date,player_a1,player_a2,player_b1,player_b2,winner\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="missing required column"):
        load_matches(str(p), PLAYERS)


def test_blank_trailing_rows_ignored_and_headers_normalised(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("Date, Player A1 ,player_a2,player_b1,player_b2,Winner,score_a,score_b\n"
                 "2026-01-05, Ace ,Nok,Tom,Pim,A,21,15\n,,,,,,,\n", encoding="utf-8")
    df = load_matches(str(p), PLAYERS)
    assert len(df) == 1 and df.iloc[0]["player_a1"] == "Ace"


def test_players_file(tmp_path):
    p = tmp_path / "players.csv"
    p.write_text("name\nAce\n Nok \n\nTom\n", encoding="utf-8")
    assert load_players(str(p)) == ["Ace", "Nok", "Tom"]
    p.write_text("name\nAce\nAce\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="duplicate"):
        load_players(str(p))
    p.write_text("player\nAce\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="'name' column"):
        load_players(str(p))
