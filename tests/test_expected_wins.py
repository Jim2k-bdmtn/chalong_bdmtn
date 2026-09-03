import pytest

from badminton_stats import config
from badminton_stats.elo import EloState, process_match
from badminton_stats.stats import partner_table


def _results(spec):
    """spec: list of (team_a, team_b, winner, ratings_before). Each builds a fresh state so the
    pre-match probabilities are exactly the ones we set."""
    out = []
    for i, (ta, tb, w, ratings) in enumerate(spec, 1):
        st = EloState()
        st.rating.update(ratings)
        for p in ratings:
            st.n_matches[p] = 20
        out.append(process_match(st, i, ta, tb, w))
    return out


def test_expected_wins_sum_pre_match_probabilities():
    even = {"me": 1000, "pal": 1000, "x": 1000, "y": 1000}
    strong = {"me": 1200, "pal": 1200, "x": 1000, "y": 1000}   # 200 gap -> p ~ 0.7597
    res = _results([
        (("me", "pal"), ("x", "y"), "A", even),
        (("x", "y"), ("me", "pal"), "B", even),     # we are team B here, still a win
        (("me", "pal"), ("x", "y"), "B", strong),   # favourites lose
    ])
    rows = partner_table("me", res)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "pal"
    assert row["matches"] == 3
    assert row["wins"] == 2
    p_strong = 1 / (1 + 10 ** (-200 / 400))
    assert row["expected_wins"] == pytest.approx(0.5 + 0.5 + p_strong)
    assert row["diff"] == pytest.approx(2 - (1.0 + p_strong))


def test_partners_sorted_by_matches_and_capped(monkeypatch):
    monkeypatch.setattr(config, "TOP_PARTNERS", 2)
    even = {"me": 1000, "a": 1000, "b": 1000, "x": 1000, "y": 1000}
    res = _results([
        (("me", "a"), ("x", "y"), "A", even),
        (("me", "a"), ("x", "y"), "A", even),   # a: 2 wins, expected 1.0 -> diff +1
        (("me", "b"), ("x", "y"), "B", even),
        (("me", "b"), ("x", "y"), "B", even),   # b: 0 wins, expected 1.0 -> diff -1
        (("me", "x"), ("a", "b"), "A", even),   # x: only 1 match -> outside the top 2
    ])
    rows = partner_table("me", res)
    assert [r["name"] for r in rows] == ["a", "b"]   # equal matches, better diff first
    assert rows[0]["diff"] == pytest.approx(1.0)
    assert rows[1]["diff"] == pytest.approx(-1.0)


def test_no_partners_when_never_played():
    assert partner_table("ghost", []) == []
