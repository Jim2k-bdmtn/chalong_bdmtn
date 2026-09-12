"""Season-fit rating engine: a Bradley-Terry fit over every match at once.

This is what the site calls "Elo". Unlike classic Elo, which walks through the matches in order
and moves ratings by a fixed K, this finds the one set of ratings that best explains all results
together, so a January win over someone who later turned out to be strong counts as much as a
win over them today.

  * Same scale and formula as classic Elo: P(A wins) = 1 / (1 + 10 ** ((R_B - R_A) / 400)),
    with a pair's rating being the average of its two players.
  * A mild prior pulls every rating towards START_RATING (normal prior with standard deviation
    LEVEL_PRIOR_SD points). Players with one or two matches stay close to the middle until they
    have shown more; players with many matches are barely affected.
  * Fitted by a diagonal Newton method on the penalised log-likelihood. 48 players and a few
    hundred matches converge in a few milliseconds.

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


def fit_levels(matches: Iterable[tuple[tuple[str, str], tuple[str, str], str]],
               players: Iterable[str],
               prior_sd: float | None = None,
               init: dict[str, float] | None = None,
               max_iter: int = 500,
               tol: float = 1e-9) -> dict[str, float]:
    """matches: (team_a, team_b, winner) with winner in {"A", "B"}. Returns {player: rating}.

    Every name in `players` gets a rating; those without matches sit exactly at START_RATING.
    `init` (ratings from a previous fit) only speeds convergence; the result does not depend on it.
    """
    prior_sd = config.LEVEL_PRIOR_SD if prior_sd is None else prior_sd
    lam = 1.0 / (prior_sd * _SCALE) ** 2  # penalty in logistic units
    matches = [(tuple(a), tuple(b), 1.0 if w == "A" else 0.0) for a, b, w in matches]
    names = set(players)
    for a, b, _ in matches:
        names.update(a)
        names.update(b)
    init = init or {}
    x = {n: (init.get(n, config.START_RATING) - config.START_RATING) * _SCALE for n in names}

    for _ in range(max_iter):
        grad = {n: -lam * v for n, v in x.items()}
        hess = {n: lam for n in names}
        for a, b, y in matches:
            d = (x[a[0]] + x[a[1]] - x[b[0]] - x[b[1]]) / 2.0
            p = 1.0 / (1.0 + math.exp(-d))
            g, h = (y - p) / 2.0, p * (1.0 - p) / 4.0
            for n in a:
                grad[n] += g
                hess[n] += h
            for n in b:
                grad[n] -= g
                hess[n] += h
        step = 0.0
        for n in names:
            dx = grad[n] / hess[n]
            x[n] += dx
            step = max(step, abs(dx))
        if step < tol:
            break

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
        r_a = (rating_before[team_a[0]] + rating_before[team_a[1]]) / 2.0
        r_b = (rating_before[team_b[0]] + rating_before[team_b[1]]) / 2.0
        p_a = expected(r_a, r_b)

        seen.append((team_a, team_b, winner))
        ratings = fit_levels(seen, state.rating.keys(), init=ratings)
        rating_after = {p: ratings[p] for p in four}
        delta = {p: rating_after[p] - rating_before[p] for p in four}
        for p in four:
            state.n_matches[p] += 1

        results.append(MatchResult(match_id, team_a, team_b, winner, rating_before,
                                   matches_before, k, p_a, delta, rating_after))

    state.rating.update(ratings)
    return results, state
