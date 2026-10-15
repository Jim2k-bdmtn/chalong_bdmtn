"""Season-fit rating engine: a Bradley-Terry fit over every match at once.

This is what the site calls "Elo". Unlike classic Elo, which walks through the matches in order
and moves ratings by a fixed K, this finds the set of ratings that best explains all results
together, so a January win over someone who later turned out to be strong counts as much as a
win over them today.

  * Same scale and formula as classic Elo: P(A wins) = 1 / (1 + 10 ** ((R_B - R_A) / 400)).
  * A pair's rating leans towards its stronger player, gradually: partners with equal ratings count
    half each, and the stronger one's weight grows with the gap towards LEVEL_CARRY_WEIGHT (0.7),
    about 0.64 at a gap of LEVEL_CARRY_SMOOTH (100) points. With a plain average, a weak player who
    always partners a strong one against two medium players got half the credit for wins the
    strong player earned. A split that jumped to 70/30 a few points past equal made ratings leap
    whenever one match lifted a player just past an old partner (every old match with that partner
    flipped to the other split); the gradual split also predicts each match from the earlier ones better.
  * A mild prior pulls every rating towards START_RATING (normal prior with standard deviation
    LEVEL_PRIOR_SD points). Players with one or two matches stay close to the middle until they
    have shown more; players with many matches are barely affected.
  * Fitted by a diagonal Newton method with a backtracking line search on the penalised
    log-likelihood. Which partner is "stronger" depends on the ratings being fitted, so the
    carry-weighted fit can have more than one optimum. The fit starts with plain averages (a single
    optimum) and raises the carry weight in small steps, following that optimum. The result
    depends only on the set of matches, not on their order or on any earlier fit.

Match points. At the fitted ratings the prior's pull exactly balances the results, which gives

    rating = START_RATING + sum over the player's matches of points_scale() * share * (S - E)

with S = 1 for a win and 0 for a loss, E the pair's win chance and share the player's part of the
pair (`shares`; the two add up to 1), all judged by today's ratings. So every match hands out
points that add up to zero: the winners gain what the losers lose, more for a bigger upset, and the
stronger partner takes the larger share. A rating is exactly the sum of its match points.
`season_points` scores every match this way; adding a match re-scores all of them.
"""
from __future__ import annotations

import math
from collections.abc import Iterable

from . import config
from .elo import EloState, MatchResult, expected

_SCALE = math.log(10) / 400.0  # rating points -> logistic units
_CARRY_STEP = 0.1            # carry-weight increment per stage of the fit


def team_rating(r1: float, r2: float, carry: float | None = None) -> float:
    """A pair's rating: the plain average for equal partners, leaning towards the stronger player as the
    gap grows, up to `carry` (default LEVEL_CARRY_WEIGHT) of the stronger plus the rest of the weaker."""
    k = (config.LEVEL_CARRY_WEIGHT if carry is None else carry) - 0.5
    smooth = config.LEVEL_CARRY_SMOOTH
    return (r1 + r2) / 2.0 + k * (math.hypot(r1 - r2, smooth) - smooth)


def shares(r1: float, r2: float, carry: float | None = None) -> tuple[float, float]:
    """Each partner's part of the pair's result: the derivatives of team_rating. They add up to 1."""
    k = (config.LEVEL_CARRY_WEIGHT if carry is None else carry) - 0.5
    lean = k * (r1 - r2) / math.hypot(r1 - r2, config.LEVEL_CARRY_SMOOTH)
    return 0.5 + lean, 0.5 - lean


def points_scale() -> float:
    """Match points per unit of share x (S - E), set by the prior: about 130 for LEVEL_PRIOR_SD = 150."""
    return config.LEVEL_PRIOR_SD ** 2 * _SCALE


def _pair(xa: float, xb: float, k: float, eps: float) -> tuple[float, float, float]:
    """team_rating in logistic units, plus its derivatives with respect to each player."""
    diff = xa - xb
    root = math.hypot(diff, eps)
    lean = k * diff / root
    return (xa + xb) / 2.0 + k * (root - eps), 0.5 + lean, 0.5 - lean


def _objective(matches, x: dict[str, float], lam: float, k: float, eps: float) -> float:
    """Penalised log-likelihood."""
    total = -lam / 2.0 * sum(v * v for v in x.values())
    for a, b, y in matches:
        d = _pair(x[a[0]], x[a[1]], k, eps)[0] - _pair(x[b[0]], x[b[1]], k, eps)[0]
        total -= math.log1p(math.exp(-d if y else d))
    return total


def _newton(matches, x: dict[str, float], lam: float, carry: float, max_iter: int, tol: float) -> None:
    """Diagonal Newton with backtracking on the penalised log-likelihood, updating `x` (logistic units) in place."""
    k, eps = carry - 0.5, config.LEVEL_CARRY_SMOOTH * _SCALE
    f = _objective(matches, x, lam, k, eps)
    for _ in range(max_iter):
        grad = {n: -lam * v for n, v in x.items()}
        hess = {n: lam for n in x}
        for a, b, y in matches:
            ta, ca0, ca1 = _pair(x[a[0]], x[a[1]], k, eps)
            tb, cb0, cb1 = _pair(x[b[0]], x[b[1]], k, eps)
            p = 1.0 / (1.0 + math.exp(tb - ta))
            g, h = y - p, p * (1.0 - p)
            for n, c in ((a[0], ca0), (a[1], ca1)):
                grad[n] += c * g
                hess[n] += c * c * h
            for n, c in ((b[0], cb0), (b[1], cb1)):
                grad[n] -= c * g
                hess[n] += c * c * h
        dx = {n: grad[n] / hess[n] for n in x}
        t = 1.0
        while True:
            trial = {n: v + t * dx[n] for n, v in x.items()}
            f_trial = _objective(matches, trial, lam, k, eps)
            if f_trial >= f or t < 1e-6:
                break
            t /= 2.0
        x.update(trial)
        f = f_trial
        if t * max(map(abs, dx.values()), default=0.0) < tol:
            break


def fit_levels(matches: Iterable[tuple[tuple[str, str], tuple[str, str], str]],
               players: Iterable[str],
               prior_sd: float | None = None,
               carry: float | None = None,
               max_iter: int = 1000,
               tol: float = 1e-9) -> dict[str, float]:
    """matches: (team_a, team_b, winner) with winner in {"A", "B"}. Returns {player: rating}.

    Every name in `players` gets a rating; those without matches sit exactly at START_RATING.
    Always starts from scratch: with the carry weight a warm start could land on a different optimum.
    """
    prior_sd = config.LEVEL_PRIOR_SD if prior_sd is None else prior_sd
    carry = config.LEVEL_CARRY_WEIGHT if carry is None else carry
    lam = 1.0 / (prior_sd * _SCALE) ** 2  # penalty in logistic units
    matches = [(tuple(a), tuple(b), 1.0 if w == "A" else 0.0) for a, b, w in matches]
    names = set(players)
    for a, b, _ in matches:
        names.update(a)
        names.update(b)
    x = dict.fromkeys(sorted(names), 0.0)  # fixed order: float sums must not depend on set hashing

    # Walk the carry weight up from 0.5 in small steps so the fit follows one optimum smoothly
    # instead of jumping to whichever one a single big step happens to land in.
    steps = max(1, math.ceil(abs(carry - 0.5) / _CARRY_STEP))
    for i in range(steps + 1):
        _newton(matches, x, lam, 0.5 + (carry - 0.5) * i / steps, max_iter, tol)

    return {n: config.START_RATING + v / _SCALE for n, v in x.items()}


def season_points(matches, players: Iterable[str] = ()) -> tuple[list[MatchResult], EloState]:
    """matches: iterable of (match_id, team_a, team_b, winner) in chronological order.

    Fits the season once and scores every match with those ratings. Returns the per-match accounting
    and the final state, shaped like elo.replay() so downstream code cannot tell the two engines apart:
      p_a            team A's win chance by today's ratings
      delta          each player's points from the match; the four add up to zero
      rating_before  START_RATING plus the player's points from their earlier matches
      rating_after   the same including this match; after a player's last match it is their rating
    """
    state = EloState()
    for p in players:
        state.ensure(p)
    played = []
    for match_id, team_a, team_b, winner in matches:
        if winner not in ("A", "B"):
            raise ValueError(f"winner must be 'A' or 'B', got {winner!r}")
        team_a, team_b = tuple(team_a), tuple(team_b)
        four = (*team_a, *team_b)
        if len(four) != 4 or len(set(four)) != 4:
            raise ValueError(f"a match needs 4 distinct players, got {four}")
        for p in four:
            state.ensure(p)
        played.append((match_id, team_a, team_b, winner))

    ratings = fit_levels([(ta, tb, w) for _, ta, tb, w in played], state.rating.keys())
    state.rating.update(ratings)
    scale = points_scale()
    running = dict.fromkeys(ratings, config.START_RATING)
    results: list[MatchResult] = []

    for match_id, team_a, team_b, winner in played:
        four = (*team_a, *team_b)
        p_a = expected(team_rating(*(ratings[p] for p in team_a)),
                       team_rating(*(ratings[p] for p in team_b)))
        surprise_a = (1.0 if winner == "A" else 0.0) - p_a
        delta: dict[str, float] = {}
        for team, surprise in ((team_a, surprise_a), (team_b, -surprise_a)):
            for p, share in zip(team, shares(*(ratings[q] for q in team))):
                delta[p] = scale * share * surprise

        rating_before = {p: running[p] for p in four}
        matches_before = {p: state.n_matches[p] for p in four}
        for p in four:
            running[p] += delta[p]
            state.n_matches[p] += 1
        k = {p: 0 for p in four}  # no K-factor in a season fit; kept for interface compatibility
        results.append(MatchResult(match_id, team_a, team_b, winner, rating_before,
                                   matches_before, k, p_a, delta, {p: running[p] for p in four}))

    return results, state
