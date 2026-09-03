"""Per-player statistics derived from the replayed Elo results."""
from __future__ import annotations

from collections import defaultdict

from . import config
from .elo import EloState, MatchResult, expected


def streaks(results: list[str]) -> dict:
    """results: chronological list of 'W'/'L'. Returns current + longest streaks."""
    longest = {"W": 0, "L": 0}
    run_type, run_len = None, 0
    for r in results:
        if r == run_type:
            run_len += 1
        else:
            run_type, run_len = r, 1
        longest[r] = max(longest[r], run_len)
    return {
        "current": {"type": run_type, "len": run_len},
        "longest_win": longest["W"],
        "longest_loss": longest["L"],
    }


def partner_table(player: str, played: list[MatchResult]) -> list[dict]:
    """Per partner: matches, wins, expected wins (sum of pre-match win probabilities), diff.
    The TOP_PARTNERS most-played-with partners, most matches first."""
    acc: dict[str, dict] = defaultdict(lambda: {"matches": 0, "wins": 0, "expected": 0.0})
    for r in played:
        a = acc[r.partner_of(player)]
        a["matches"] += 1
        a["wins"] += int(r.won(player))
        a["expected"] += r.p_win(player)
    rows = [
        {"name": p, "matches": v["matches"], "wins": v["wins"],
         "win_rate": v["wins"] / v["matches"],
         "expected_wins": v["expected"], "diff": v["wins"] - v["expected"]}
        for p, v in acc.items()
    ]
    rows.sort(key=lambda x: (-x["matches"], -x["diff"], x["name"]))
    return rows[:config.TOP_PARTNERS]


def opponent_table(player: str, played: list[MatchResult]) -> dict:
    acc: dict[str, dict] = defaultdict(lambda: {"matches": 0, "wins": 0})
    for r in played:
        for opp in r.opponents_of(player):
            acc[opp]["matches"] += 1
            acc[opp]["wins"] += int(r.won(player))
    rows = [
        {"name": p, "matches": v["matches"], "wins": v["wins"],
         "losses": v["matches"] - v["wins"], "win_rate": v["wins"] / v["matches"]}
        for p, v in acc.items()
    ]
    rows.sort(key=lambda x: (-x["matches"], x["name"]))
    eligible = [r for r in rows if r["matches"] >= config.MIN_OPPONENT_MATCHES]
    most_faced = rows[0] if rows else None
    nemesis = min(eligible, key=lambda x: (x["win_rate"], -x["matches"], x["name"])) if eligible else None
    victim = max(eligible, key=lambda x: (x["win_rate"], x["matches"], x["name"])) if eligible else None
    # A player who is both nemesis and victim (only one eligible opponent) is not interesting.
    if nemesis is not None and victim is not None and nemesis["name"] == victim["name"]:
        nemesis = victim = None
    return {"rows": rows, "most_faced": most_faced, "nemesis": nemesis, "victim": victim}


def p_win_now(player: str, r: MatchResult, rating: dict[str, float]) -> float:
    """Win chance of `player`'s team in match `r`, judged by TODAY's ratings of the four players."""
    own = r.team_of(player)
    opp = r.opponents_of(player)

    def mean(team):
        return sum(rating.get(p, config.START_RATING) for p in team) / 2.0

    return expected(mean(own), mean(opp))


def notable_matches(player: str, played: list[MatchResult],
                    rating: dict[str, float]) -> dict[str, list[dict]]:
    """The TOP_MATCHES hardest wins (lowest win chance) and easiest losses (highest win chance),
    where the chance is recomputed from the players' current Elo ratings, not the pre-match ones."""
    scored = [(r, p_win_now(player, r, rating)) for r in played]
    wins = sorted(((r, p) for r, p in scored if r.won(player)), key=lambda x: (x[1], -x[0].match_id))
    losses = sorted(((r, p) for r, p in scored if not r.won(player)), key=lambda x: (-x[1], -x[0].match_id))

    def pack(items):
        return [{"match_id": r.match_id, "p_now": round(p, 4)} for r, p in items[:config.TOP_MATCHES]]

    return {"hardest_wins": pack(wins), "easiest_losses": pack(losses)}


def player_stats(players: list[str], results: list[MatchResult], state: EloState,
                 dates: dict[int, str]) -> dict[str, dict]:
    """dates: match_id -> 'YYYY-MM-DD'. Returns a dict keyed by player name (all league players,
    including those who never played)."""
    by_player: dict[str, list[MatchResult]] = defaultdict(list)
    for r in results:
        for p in r.players:
            by_player[p].append(r)

    out: dict[str, dict] = {}
    for p in players:
        played = by_player.get(p, [])
        wl = ["W" if r.won(p) else "L" for r in played]
        wins = wl.count("W")
        n = len(played)
        points = 0
        points_history, elo_history = [], []
        for r, res in zip(played, wl):
            points += 1 if res == "W" else -1
            points_history.append({"match_id": r.match_id, "date": dates[r.match_id], "value": points})
            elo_history.append({"match_id": r.match_id, "date": dates[r.match_id],
                                "value": round(r.rating_after[p], 1)})
        st = streaks(wl)
        opp = opponent_table(p, played)
        peak = max(elo_history, key=lambda h: h["value"]) if elo_history else None
        low = min(elo_history, key=lambda h: h["value"]) if elo_history else None
        form_delta = sum(r.delta[p] for r in played[-config.FORM_WINDOW:]) if n >= config.FORM_WINDOW else None
        avg_opp = (sum(sum(state.rating[o] for o in r.opponents_of(p)) / 2.0 for r in played) / n) if n else None
        avg_partner = (sum(state.rating[r.partner_of(p)] for r in played) / n) if n else None
        notable = notable_matches(p, played, state.rating)
        out[p] = {
            "name": p,
            "matches": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate": (wins / n) if n else None,
            "points": points,
            "elo": round(state.rating.get(p, config.START_RATING), 1),
            "provisional": n < config.PROVISIONAL_UNTIL,
            "streak_current": st["current"],
            "longest_win": st["longest_win"],
            "longest_loss": st["longest_loss"],
            "form": wl[-config.FORM_LENGTH:],
            "form_delta": None if form_delta is None else round(form_delta, 1),
            "peak_elo": peak,
            "low_elo": low,
            "avg_opponent_elo": None if avg_opp is None else round(avg_opp, 1),
            "avg_partner_elo": None if avg_partner is None else round(avg_partner, 1),
            "elo_history": elo_history,
            "points_history": points_history,
            "partners": partner_table(p, played),
            "hardest_wins": notable["hardest_wins"],
            "easiest_losses": notable["easiest_losses"],
            "most_faced": opp["most_faced"],
            "nemesis": opp["nemesis"],
            "victim": opp["victim"],
            "last_played": dates[played[-1].match_id] if played else None,
        }
    return out
