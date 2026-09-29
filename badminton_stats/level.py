"""Season-fit rating engine: a Bradley-Terry fit over every match at once.

This is what the site calls "Elo". Unlike classic Elo, which walks through the matches in order
and moves ratings by a fixed K, this finds the set of ratings that best explains all results
together, so a January win over someone who later turned out to be strong counts as much as a
win over them today.

  * Same scale and formula as classic Elo: P(A wins) = 1 / (1 + 10 ** ((R_B - R_A) / 400)).
  * A pair's rating leans towards its stronger player: LEVEL_CARRY_WEIGHT (0.7) of the stronger
    player's rating plus the rest of the weaker one's. With a plain average, a weak player who
    always partners a strong one against two medium players got half the credit for wins the
    strong player earned. On the real results 0.7 predicted held-out matches better than 0.5.
  * A mild prior pulls every rating towards START_RATING (normal prior with standard deviation
    LEVEL_PRIOR_SD points). Players with one or two matches stay close to the middle until they
    have shown more; players with many matches are barely affected.
  * The switch between "stronger" and "weaker" is smoothed over the first few points of
    difference (CARRY_SMOOTH), so teammates with equal ratings count half each and the fit has no
    kinks. Past a few points the split is 70/30 to within a point.
  * Fitted by a diagonal Newton method with a backtracking line search on the penalised
    log-likelihood. Which partner is "stronger" depends on the ratings being fitted, so the
    carry-weighted fit can have more than one optimum. The fit starts with plain averages (a single
    optimum) and raises the carry weight in small steps, following that optimum. The result
    depends only on the set of matches, not on their order or on any earlier fit.

`replay_fit` produces the same MatchResult / EloState objects as the classic engine in elo.py,
refitting the season after every match, so the rest of the pipeline (match cards, form, upsets,
histories) works unchanged. "delta" is how much a player's fitted rating moved when the match was
added; "rating_before" is the fit without it.
"""
from __future__ import annotations

import math
from collections.abc import Iterable

from . import config
from .elo import EloState, MatchResult, expected

_SCALE = math.log(10) / 400.0  # rating points -> logistic units
CARRY_SMOOTH = 5.0             # rating points over which a pair's 50/50 split turns into the carry split
_CARRY_STEP = 0.1            # carry-weight increment per stage of the fit


def team_rating(r1: float, r2: float, carry: float | None = None) -> float:
    """A pair's rating: `carry` (default LEVEL_CARRY_WEIGHT) of the stronger player, the rest of the weaker,
    blended smoothly towards the plain average when the two are within a few points of each other."""
    k = (config.LEVEL_CARRY_WEIGHT if carry is None else carry) - 0.5
    return (r1 + r2) / 2.0 + k * (math.hypot(r1 - r2, CARRY_SMOOTH) - CARRY_SMOOTH)


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
    k, eps = carry - 0.5, CARRY_SMOOTH * _SCALE
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


def replay_fit(matches, players: Iterable[str] = ()) -> tuple[list[MatchResult], EloState]:
    """matches: iterable of (match_id, team_a, team_b, winner) in chronological order.

    Refits the season after each match. Returns the per-match accounting and the final state,
    shaped exactly like elo.replay() so downstream code cannot tell the two engines apart.
    """
    state = EloState()
    for p in players:
        state.ensure(p)
    seen: list[tuple[tuple[str, str], tuple[str, str], str]] = []
    ratings = dict(state.rating)
    results: list[MatchResult] = []

    for match_id, team_a, team_b, winner in matches:
        if winner not in ("A", "B"):
            raise ValueError(f"winner must be 'A' or 'B', got {winner!r}")
        team_a, team_b = tuple(team_a), tuple(team_b)
        four = (*team_a, *team_b)
        if len(four) != 4 or len(set(four)) != 4:
            raise ValueError(f"a match needs 4 distinct players, got {four}")
        for p in four:
            state.ensure(p)
            ratings.setdefault(p, config.START_RATING)

        rating_before = {p: ratings[p] for p in four}
        matches_before = {p: state.n_matches[p] for p in four}
        k = {p: 0 for p in four}  # no K-factor in a season fit; kept for interface compatibility
        p_a = expected(team_rating(*(rating_before[p] for p in team_a)),
                       team_rating(*(rating_before[p] for p in team_b)))

        seen.append((team_a, team_b, winner))
        ratings = fit_levels(seen, state.rating.keys())
        rating_after = {p: ratings[p] for p in four}
        delta = {p: rating_after[p] - rating_before[p] for p in four}
        for p in four:
            state.n_matches[p] += 1

        results.append(MatchResult(match_id, team_a, team_b, winner, rating_before,
                                   matches_before, k, p_a, delta, rating_after))

    state.rating.update(ratings)
    return results, state
