"""Season-fit skill "Level": a Bradley-Terry rating fitted on every match at once.

Unlike Elo, which walks through the matches in order, this finds the one set of ratings that
best explains all results together, so a January win over someone who later turned out to be
strong counts as much as a win over them today.

  * Same scale and formula as Elo: P(A wins) = 1 / (1 + 10 ** ((R_B - R_A) / 400)),
    with a pair's rating being the average of its two players.
  * A mild prior pulls every rating towards START_RATING (a normal prior with standard deviation
    LEVEL_PRIOR_SD points). Players with one or two matches therefore stay close to the middle
    until they have shown more; players with many matches are barely affected.
  * Fitted by a diagonal Newton method on the penalised log-likelihood. 48 players and a few
    hundred matches converge in a few milliseconds.
"""
from __future__ import annotations

import math
from collections.abc import Iterable

from . import config

_SCALE = math.log(10) / 400.0  # rating points -> logistic units


def fit_levels(matches: Iterable[tuple[tuple[str, str], tuple[str, str], str]],
               players: Iterable[str],
               prior_sd: float | None = None,
               max_iter: int = 500,
               tol: float = 1e-9) -> dict[str, float]:
    """matches: (team_a, team_b, winner) with winner in {"A", "B"}. Returns {player: level}.

    Every name in `players` gets a level; those without matches sit exactly at START_RATING.
    """
    prior_sd = config.LEVEL_PRIOR_SD if prior_sd is None else prior_sd
    lam = 1.0 / (prior_sd * _SCALE) ** 2  # penalty in logistic units
    matches = [(tuple(a), tuple(b), 1.0 if w == "A" else 0.0) for a, b, w in matches]
    names = set(players)
    for a, b, _ in matches:
        names.update(a)
        names.update(b)
    x = {n: 0.0 for n in names}  # logistic-unit offsets from START_RATING

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
