"""Doubles Elo engine. Pure Python, no pandas, so it is trivial to unit test.

Rules (numbers live in config.py):
  * team rating = mean of the two players' ratings
  * expected(A) = 1 / (1 + 10 ** ((R_B - R_A) / 400))
  * each player i gets delta_i = K_i * (S - E_team) where S is 1 for a win, 0 for a loss.
    K_i depends on how many matches player i has played BEFORE this match.
    Teammates therefore share (S - E); their deltas are equal when their K is equal,
    and sum(delta_i / K_i) over the four players is always exactly zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config


def expected(r_a: float, r_b: float) -> float:
    """Probability that a side rated r_a beats a side rated r_b."""
    return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400.0))


def k_factor(n_matches_before: int) -> int:
    return config.K_NEW if n_matches_before < config.PROVISIONAL_UNTIL else config.K_ESTABLISHED


@dataclass
class MatchResult:
    match_id: int
    team_a: tuple[str, str]
    team_b: tuple[str, str]
    winner: str                       # "A" or "B"
    rating_before: dict[str, float]   # per player
    matches_before: dict[str, int]    # per player
    k: dict[str, int]                 # per player
    p_a: float                        # pre-match probability that team A wins
    delta: dict[str, float]           # per player
    rating_after: dict[str, float]

    @property
    def players(self) -> tuple[str, str, str, str]:
        return (*self.team_a, *self.team_b)

    @property
    def winners(self) -> tuple[str, str]:
        return self.team_a if self.winner == "A" else self.team_b

    @property
    def losers(self) -> tuple[str, str]:
        return self.team_b if self.winner == "A" else self.team_a

    @property
    def p_winner(self) -> float:
        return self.p_a if self.winner == "A" else 1.0 - self.p_a

    def won(self, player: str) -> bool:
        return player in self.winners

    def team_of(self, player: str) -> tuple[str, str]:
        return self.team_a if player in self.team_a else self.team_b

    def partner_of(self, player: str) -> str:
        t = self.team_of(player)
        return t[1] if t[0] == player else t[0]

    def opponents_of(self, player: str) -> tuple[str, str]:
        return self.team_b if player in self.team_a else self.team_a

    def p_win(self, player: str) -> float:
        """Pre-match probability that `player`'s team wins."""
        return self.p_a if player in self.team_a else 1.0 - self.p_a


@dataclass
class EloState:
    rating: dict[str, float] = field(default_factory=dict)
    n_matches: dict[str, int] = field(default_factory=dict)

    def ensure(self, player: str) -> None:
        self.rating.setdefault(player, config.START_RATING)
        self.n_matches.setdefault(player, 0)

    def is_provisional(self, player: str) -> bool:
        return self.n_matches.get(player, 0) < config.PROVISIONAL_UNTIL


def process_match(state: EloState, match_id: int, team_a: tuple[str, str],
                  team_b: tuple[str, str], winner: str) -> MatchResult:
    """Apply one match to `state` (mutating it) and return the full accounting."""
    if winner not in ("A", "B"):
        raise ValueError(f"winner must be 'A' or 'B', got {winner!r}")
    team_a, team_b = tuple(team_a), tuple(team_b)
    players = (*team_a, *team_b)
    if len(players) != 4 or len(set(players)) != 4:
        raise ValueError(f"a match needs 4 distinct players, got {players}")
    for p in players:
        state.ensure(p)

    rating_before = {p: state.rating[p] for p in players}
    matches_before = {p: state.n_matches[p] for p in players}
    k = {p: k_factor(matches_before[p]) for p in players}

    r_a = (rating_before[team_a[0]] + rating_before[team_a[1]]) / 2.0
    r_b = (rating_before[team_b[0]] + rating_before[team_b[1]]) / 2.0
    p_a = expected(r_a, r_b)

    s_a = 1.0 if winner == "A" else 0.0
    surprise_a = s_a - p_a          # positive when A wins
    surprise_b = -surprise_a        # (1 - s_a) - (1 - p_a)

    delta: dict[str, float] = {}
    for p in team_a:
        delta[p] = k[p] * surprise_a
    for p in team_b:
        delta[p] = k[p] * surprise_b

    for p in players:
        state.rating[p] += delta[p]
        state.n_matches[p] += 1
    rating_after = {p: state.rating[p] for p in players}

    return MatchResult(match_id, team_a, team_b, winner, rating_before,
                       matches_before, k, p_a, delta, rating_after)


def replay(matches, state: EloState | None = None) -> tuple[list[MatchResult], EloState]:
    """matches: iterable of (match_id, team_a, team_b, winner) in chronological order."""
    state = state if state is not None else EloState()
    results = [process_match(state, mid, ta, tb, w) for mid, ta, tb, w in matches]
    return results, state
