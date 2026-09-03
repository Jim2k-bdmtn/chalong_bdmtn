import pytest

from badminton_stats import config
from badminton_stats.elo import replay
from badminton_stats.stats import notable_matches, opponent_table, p_win_now, player_stats, streaks


def test_streaks_empty():
    assert streaks([]) == {"current": {"type": None, "len": 0}, "longest_win": 0, "longest_loss": 0}


def test_streaks_basic():
    s = streaks(list("WWLLLWW"))
    assert s["current"] == {"type": "W", "len": 2}
    assert s["longest_win"] == 2
    assert s["longest_loss"] == 3


def test_streaks_all_wins():
    s = streaks(list("WWWW"))
    assert s["current"] == {"type": "W", "len": 4}
    assert s["longest_loss"] == 0


def _season():
    # "me" plays 12 matches: wins the first 8 with pal, loses the last 4 with other partners.
    matches = []
    for i in range(1, 9):
        matches.append((i, ("me", "pal"), ("foe", f"o{i % 3}"), "A"))
    for i in range(9, 13):
        matches.append((i, ("foe", f"o{i % 3}"), ("me", "pal2"), "A"))
    return matches


def test_player_stats_points_form_and_histories():
    matches = _season()
    results, state = replay(matches)
    dates = {i: f"2026-01-{i:02d}" for i in range(1, 13)}
    players = ["me", "pal", "pal2", "foe", "o0", "o1", "o2", "ghost"]
    ps = player_stats(players, results, state, dates)

    me = ps["me"]
    assert me["matches"] == 12 and me["wins"] == 8 and me["losses"] == 4
    assert me["points"] == 4
    assert me["win_rate"] == pytest.approx(8 / 12)
    assert not me["provisional"]
    assert me["form"] == list("WWWWWWLLLL")            # last 10 of 12
    assert me["streak_current"] == {"type": "L", "len": 4}
    assert me["longest_win"] == 8 and me["longest_loss"] == 4
    assert [h["value"] for h in me["points_history"]] == [1, 2, 3, 4, 5, 6, 7, 8, 7, 6, 5, 4]
    assert len(me["elo_history"]) == 12
    assert me["elo_history"][-1]["value"] == pytest.approx(state.rating["me"], abs=0.05)
    assert me["last_played"] == "2026-01-12"
    assert me["peak_elo"]["value"] == max(h["value"] for h in me["elo_history"])
    assert me["low_elo"]["value"] == min(h["value"] for h in me["elo_history"])
    assert me["peak_elo"]["date"] == "2026-01-08"          # rating peaked after the 8th straight win
    assert me["form_delta"] == pytest.approx(sum(r.delta["me"] for r in results[-3:]), abs=0.05)
    assert me["form_delta"] < 0                              # lost the last three
    assert me["avg_partner_elo"] == pytest.approx((8 * state.rating["pal"] + 4 * state.rating["pal2"]) / 12, abs=0.05)
    assert me["avg_opponent_elo"] is not None

    ghost = ps["ghost"]
    assert ghost["matches"] == 0 and ghost["win_rate"] is None and ghost["provisional"]
    assert ghost["form"] == [] and ghost["partners"] == [] and ghost["nemesis"] is None
    assert ghost["hardest_wins"] == [] and ghost["easiest_losses"] == []
    assert ghost["peak_elo"] is None and ghost["form_delta"] is None and ghost["avg_partner_elo"] is None


def test_partners_most_played_first():
    results, state = replay(_season())
    dates = {i: "2026-01-01" for i in range(1, 13)}
    ps = player_stats(["me", "pal", "pal2", "foe", "o0", "o1", "o2"], results, state, dates)
    names = [p["name"] for p in ps["me"]["partners"]]
    assert names == ["pal", "pal2"]              # 8 matches, then 4
    pal = ps["me"]["partners"][0]
    assert pal["matches"] == 8 and pal["wins"] == 8
    assert pal["diff"] == pytest.approx(8 - pal["expected_wins"])
    assert pal["expected_wins"] < 8


def test_nemesis_victim_and_most_faced(monkeypatch):
    monkeypatch.setattr(config, "MIN_OPPONENT_MATCHES", 2)
    matches = [
        (1, ("me", "p"), ("nem", "x"), "B"),
        (2, ("me", "p"), ("nem", "y"), "B"),
        (3, ("me", "p"), ("vic", "x"), "A"),
        (4, ("me", "p"), ("vic", "y"), "A"),
        (5, ("me", "p"), ("vic", "z"), "A"),
        (6, ("me", "p"), ("nem", "vic"), "B"),
    ]
    results, _ = replay(matches)
    played = [r for r in results if "me" in r.players]
    opp = opponent_table("me", played)
    assert opp["most_faced"]["name"] == "vic"      # 4 meetings vs nem 3
    assert opp["nemesis"]["name"] == "nem" and opp["nemesis"]["wins"] == 0
    assert opp["victim"]["name"] == "vic" and opp["victim"]["win_rate"] == pytest.approx(0.75)
    # x and y: only 2 meetings each, x has 50 % -> neither extreme
    by_name = {r["name"]: r for r in opp["rows"]}
    assert by_name["x"]["matches"] == 2


def test_notable_matches_use_todays_ratings(monkeypatch):
    monkeypatch.setattr(config, "TOP_MATCHES", 2)
    results, state = replay(_season())
    played = [r for r in results if "me" in r.players]
    # Judge with made-up "today" ratings: o2 is now a monster, o0 is weak.
    today = {p: 1000.0 for p in state.rating}
    today.update({"me": 1100, "pal": 1000, "foe": 1000, "o2": 1600, "o0": 700, "o1": 1000, "pal2": 1000})
    nb = notable_matches("me", played, today)
    assert len(nb["hardest_wins"]) == 2 and len(nb["easiest_losses"]) == 2
    by_id = {r.match_id: r for r in played}
    hard = nb["hardest_wins"]
    assert "o2" in by_id[hard[0]["match_id"]].opponents_of("me")      # win vs the now-strong o2
    assert hard[0]["p_now"] <= hard[1]["p_now"]
    assert hard[0]["p_now"] == pytest.approx(p_win_now("me", by_id[hard[0]["match_id"]], today), abs=1e-4)
    easy = nb["easiest_losses"]
    assert "o0" in by_id[easy[0]["match_id"]].opponents_of("me")      # loss vs the now-weak o0
    assert easy[0]["p_now"] >= easy[1]["p_now"]
    assert all(not by_id[e["match_id"]].won("me") for e in easy)
    assert all(by_id[h["match_id"]].won("me") for h in hard)


def test_p_win_now_is_team_mean_expected():
    from badminton_stats.elo import EloState, process_match, expected
    r = process_match(EloState(), 1, ("me", "pal"), ("x", "y"), "A")
    today = {"me": 1200, "pal": 1000, "x": 1100, "y": 1100}   # 1100 vs 1100 -> 0.5
    assert p_win_now("me", r, today) == pytest.approx(0.5)
    assert p_win_now("x", r, today) == pytest.approx(0.5)
    today["me"] = 1400                                          # 1200 vs 1100
    assert p_win_now("me", r, today) == pytest.approx(expected(1200, 1100))
