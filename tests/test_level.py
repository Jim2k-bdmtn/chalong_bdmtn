"""Season-fit Level: sanity checks on hand-built fixtures."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from badminton_stats import config  # noqa: E402
from badminton_stats.level import fit_levels, replay_fit  # noqa: E402

A, B, C, D = "a", "b", "c", "d"


def test_no_matches_is_start_rating():
    lv = fit_levels([], [A, B])
    assert lv == {A: config.START_RATING, B: config.START_RATING}


def test_symmetric_results_give_equal_levels():
    m = [((A, B), (C, D), "A"), ((A, B), (C, D), "B")]
    lv = fit_levels(m, [A, B, C, D])
    assert abs(lv[A] - lv[C]) < 1e-6
    assert abs(lv[A] - config.START_RATING) < 1e-6


def test_winning_side_rated_higher_and_zero_mean():
    m = [((A, B), (C, D), "A")] * 6
    lv = fit_levels(m, [A, B, C, D])
    assert lv[A] > config.START_RATING > lv[C]
    assert abs(lv[A] - lv[B]) < 1e-6 and abs(lv[C] - lv[D]) < 1e-6
    assert abs(sum(lv.values()) - 4 * config.START_RATING) < 1e-6


def test_prior_shrinks_thin_records():
    one = fit_levels([((A, B), (C, D), "A")], [A, B, C, D])
    many = fit_levels([((A, B), (C, D), "A")] * 10, [A, B, C, D])
    assert config.START_RATING < one[A] < many[A]
    assert one[A] - config.START_RATING < 60  # a single win is worth little


def test_order_does_not_matter():
    m = [((A, B), (C, D), "A"), ((A, C), (B, D), "B"), ((A, D), (B, C), "A"), ((A, B), (C, D), "A")]
    lv1 = fit_levels(m, [A, B, C, D])
    lv2 = fit_levels(list(reversed(m)), [A, B, C, D])
    for n in (A, B, C, D):
        assert abs(lv1[n] - lv2[n]) < 1e-6


def test_transitive_credit():
    """A only ever beats X; X beats everyone else a lot. A should be rated above the others."""
    others = ["p1", "p2", "p3", "p4"]
    m = [(("x", others[0]), (others[1], others[2]), "A")] * 8
    m += [(("x", others[3]), (others[1], others[2]), "A")] * 8
    m += [(("a", others[0]), ("x", others[1]), "A")] * 3
    lv = fit_levels(m, ["a", "x"] + others)
    assert lv["a"] > lv[others[1]] and lv["x"] > lv[others[1]]


def test_replay_fit_bookkeeping():
    m = [(1, (A, B), (C, D), "A"), (2, (A, C), (B, D), "B"), (3, (A, D), (B, C), "A")]
    results, state = replay_fit(m, [A, B, C, D, "idle"])
    assert [r.match_id for r in results] == [1, 2, 3]
    assert results[0].rating_before == {A: 1000.0, B: 1000.0, C: 1000.0, D: 1000.0}
    assert results[0].p_a == 0.5
    assert results[0].matches_before[A] == 0 and results[2].matches_before[A] == 2
    assert state.n_matches == {A: 3, B: 3, C: 3, D: 3, "idle": 0}
    assert state.rating["idle"] == 1000.0
    for r in results:
        for p in r.players:
            assert r.rating_after[p] == r.rating_before[p] + r.delta[p]
    fresh = fit_levels([(ta, tb, w) for _, ta, tb, w in m], [A, B, C, D])
    for p in (A, B, C, D):
        assert abs(state.rating[p] - fresh[p]) < 1e-6
