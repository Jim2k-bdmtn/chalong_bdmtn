"""Season-fit Level: sanity checks on hand-built fixtures."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from badminton_stats import config  # noqa: E402
import random  # noqa: E402

from badminton_stats.level import fit_levels, season_points, shares, team_rating  # noqa: E402

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
    assert one[A] - config.START_RATING < 100  # a single win is worth little


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


def test_season_points_bookkeeping():
    m = [(1, (A, B), (C, D), "A"), (2, (A, C), (B, D), "B"), (3, (A, D), (B, C), "A")]
    results, state = season_points(m, [A, B, C, D, "idle"])
    assert [r.match_id for r in results] == [1, 2, 3]
    assert results[0].rating_before == {A: 1000.0, B: 1000.0, C: 1000.0, D: 1000.0}
    assert results[0].matches_before[A] == 0 and results[2].matches_before[A] == 2
    assert state.n_matches == {A: 3, B: 3, C: 3, D: 3, "idle": 0}
    assert state.rating["idle"] == 1000.0
    for r in results:
        for p in r.players:
            assert abs(r.rating_after[p] - (r.rating_before[p] + r.delta[p])) < 1e-9
    fresh = fit_levels([(ta, tb, w) for _, ta, tb, w in m], [A, B, C, D])
    for p in (A, B, C, D):
        assert abs(state.rating[p] - fresh[p]) < 1e-6


def _random_season(n_players=8, n_matches=60, seed=1):
    rng = random.Random(seed)
    names = [f"p{i}" for i in range(n_players)]
    out = []
    for i in range(1, n_matches + 1):
        four = rng.sample(names, 4)
        out.append((i, (four[0], four[1]), (four[2], four[3]), rng.choice("AB")))
    return names, out


def test_match_points_are_zero_sum_and_add_up_to_ratings():
    names, m = _random_season()
    results, state = season_points(m, names)
    total = dict.fromkeys(names, config.START_RATING)
    for r in results:
        assert abs(sum(r.delta.values())) < 1e-9
        assert all(r.delta[p] > 0 for p in r.winners) and all(r.delta[p] < 0 for p in r.losers)
        for p, d in r.delta.items():
            total[p] += d
    for p in names:
        assert abs(total[p] - state.rating[p]) < 1e-4
        last = [r for r in results if p in r.players][-1]
        assert abs(last.rating_after[p] - state.rating[p]) < 1e-4


def test_match_points_do_not_depend_on_order():
    names, m = _random_season()
    fwd, _ = season_points(m, names)
    back, _ = season_points(list(reversed(m)), names)
    back = {r.match_id: r for r in back}
    for r in fwd:
        for p in r.players:
            assert abs(r.delta[p] - back[r.match_id].delta[p]) < 1e-5


def test_stronger_partner_loses_more():
    """s wins all their matches, w loses all theirs; when s and w lose together, s loses more."""
    m = [(i, ("s", f"m{i % 4}"), (f"m{(i + 1) % 4}", f"m{(i + 2) % 4}"), "A") for i in range(1, 9)]
    m += [(i, ("w", f"m{i % 4}"), (f"m{(i + 1) % 4}", f"m{(i + 2) % 4}"), "B") for i in range(9, 17)]
    m += [(17, ("s", "w"), ("m0", "m1"), "B")]
    results, state = season_points(m)
    r = results[-1]
    assert state.rating["s"] > state.rating["w"]
    assert r.delta["s"] < r.delta["w"] < 0


def test_shares_grow_with_the_gap():
    assert shares(1000, 1000) == (0.5, 0.5)
    small, _ = shares(1050, 1000)
    big, rest = shares(1300, 1000)
    assert 0.5 < small < big < config.LEVEL_CARRY_WEIGHT
    assert abs(big + rest - 1.0) < 1e-12
    assert shares(1000, 1300) == (rest, big)


def test_team_rating_leans_towards_stronger_player():
    assert team_rating(1100, 1100) == 1100
    assert team_rating(1200, 1000) == team_rating(1000, 1200)
    w = config.LEVEL_CARRY_WEIGHT
    assert 1100 < team_rating(1300, 900) < w * 1300 + (1 - w) * 900   # leans, but gradually
    assert team_rating(1010, 1000) - 1005 < 0.2                        # near-equal partners: about the average
    assert team_rating(1200, 1000, carry=0.5) == 1100


def test_carried_partner_gets_less_credit():
    """The complaint that motivated LEVEL_CARRY_WEIGHT: w always partners the strong s and beats two
    medium players. Under a plain average w looks as good as the medium players; with carry he does not."""
    m = [(("s", f"m{i}"), (f"m{i + 1}", f"m{i + 2}"), "A") for i in range(6)] * 2   # s is strong
    m += [(("m0", "m1"), ("m2", "m3"), "A"), (("m2", "m3"), ("m0", "m1"), "A")]
    m += [(("s", "w"), ("m1", "m2"), "A"), (("s", "w"), ("m3", "m4"), "A"), (("s", "w"), ("m1", "m4"), "A")]
    names = ["s", "w"] + [f"m{i}" for i in range(8)]
    avg = fit_levels(m, names, carry=0.5)
    carry = fit_levels(m, names, carry=0.7)
    assert carry["w"] < avg["w"]
    assert carry["s"] > carry["w"]

