import math

import pytest

from badminton_stats import config
from badminton_stats.elo import EloState, expected, k_factor, process_match, replay


def test_expected_equal_ratings_is_half():
    assert expected(1000, 1000) == pytest.approx(0.5)


def test_expected_symmetry_and_direction():
    assert expected(1200, 1000) + expected(1000, 1200) == pytest.approx(1.0)
    assert expected(1200, 1000) > 0.5
    assert expected(1400, 1000) == pytest.approx(1 / (1 + 10 ** (-1)))  # 400 gap -> ~0.909


def test_k_schedule_switches_after_ten_matches():
    assert k_factor(0) == config.K_NEW
    assert k_factor(config.PROVISIONAL_UNTIL - 1) == config.K_NEW
    assert k_factor(config.PROVISIONAL_UNTIL) == config.K_ESTABLISHED
    assert k_factor(500) == config.K_ESTABLISHED


def test_first_match_equal_teams_each_moves_half_k():
    state = EloState()
    r = process_match(state, 1, ("a", "b"), ("c", "d"), "A")
    assert r.p_a == pytest.approx(0.5)
    for p in ("a", "b"):
        assert r.delta[p] == pytest.approx(config.K_NEW * 0.5)
    for p in ("c", "d"):
        assert r.delta[p] == pytest.approx(-config.K_NEW * 0.5)
    assert state.rating["a"] == pytest.approx(config.START_RATING + 24)
    assert state.n_matches == {"a": 1, "b": 1, "c": 1, "d": 1}


def test_teammates_share_delta_when_same_k():
    state = EloState()
    state.rating.update({"a": 1100, "b": 900, "c": 1000, "d": 1050})
    state.n_matches.update({"a": 20, "b": 20, "c": 20, "d": 20})
    r = process_match(state, 1, ("a", "b"), ("c", "d"), "B")
    assert r.delta["a"] == pytest.approx(r.delta["b"])
    assert r.delta["c"] == pytest.approx(r.delta["d"])
    assert sum(r.delta.values()) == pytest.approx(0.0)


def test_mixed_k_deltas_are_zero_sum_when_weighted_by_k():
    state = EloState()
    state.n_matches.update({"vet": 30, "new": 2, "x": 30, "y": 1})
    for p in state.n_matches:
        state.rating[p] = 1000
    r = process_match(state, 1, ("vet", "new"), ("x", "y"), "A")
    assert r.k == {"vet": 32, "new": 48, "x": 32, "y": 48}
    assert r.delta["new"] / r.delta["vet"] == pytest.approx(48 / 32)
    assert sum(r.delta[p] / r.k[p] for p in r.players) == pytest.approx(0.0, abs=1e-12)


def test_team_rating_is_mean_of_players():
    state = EloState()
    state.rating.update({"a": 1200, "b": 800, "c": 1000, "d": 1000})
    r = process_match(state, 1, ("a", "b"), ("c", "d"), "A")
    assert r.p_a == pytest.approx(0.5)  # mean(1200, 800) == 1000


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        process_match(EloState(), 1, ("a", "b"), ("c", "d"), "X")
    with pytest.raises(ValueError):
        process_match(EloState(), 1, ("a", "b"), ("a", "d"), "A")


def test_replay_marks_provisional_and_ratings_stay_finite():
    matches = [(i, ("a", "b"), ("c", "d"), "A" if i % 3 else "B") for i in range(1, 13)]
    results, state = replay(matches)
    assert len(results) == 12
    assert not state.is_provisional("a")
    assert state.is_provisional("zzz")
    assert all(math.isfinite(v) for v in state.rating.values())
    # K drops to 32 once a player has PROVISIONAL_UNTIL matches behind them
    n = config.PROVISIONAL_UNTIL
    assert results[n - 1].k["a"] == 48 and results[n].k["a"] == 32


def test_strong_player_converges_high():
    """A player who wins 90 % of the time against a rotating cast ends up clearly above start."""
    import random
    rng = random.Random(1)
    cast = [f"p{i}" for i in range(12)]
    matches = []
    for i in range(1, 121):
        others = rng.sample(cast, 3)
        team_a, team_b = ("star", others[0]), (others[1], others[2])
        winner = "A" if rng.random() < 0.9 else "B"
        matches.append((i, team_a, team_b, winner))
    _, state = replay(matches)
    assert state.rating["star"] > 1150
    assert state.rating["star"] == max(state.rating.values())
