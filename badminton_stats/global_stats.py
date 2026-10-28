"""League-wide tables: leaderboards, upsets, longest streaks."""
from __future__ import annotations

from . import config
from .elo import MatchResult


def leaderboards(pstats: dict[str, dict]) -> dict:
    active = [s for s in pstats.values() if s["matches"] > 0]

    by_points = sorted(active, key=lambda s: (-s["points"], -s["elo"], s["name"]))
    for rank, s in enumerate(by_points, 1):
        s["rank_points"] = rank

    ranked = [s for s in active if not s["provisional"]]
    by_elo = sorted(ranked, key=lambda s: (-s["elo"], s["name"]))
    for s in pstats.values():
        s["rank_elo"] = None
    for rank, s in enumerate(by_elo, 1):
        s["rank_elo"] = rank

    provisional = sorted((s for s in pstats.values() if s["provisional"]),
                         key=lambda s: (-s["matches"], -s["elo"], s["name"]))
    return {
        "leaderboard_points": [s["name"] for s in by_points],
        "leaderboard_elo": [s["name"] for s in by_elo],
        "provisional": [s["name"] for s in provisional],
    }


def upsets(results: list[MatchResult], dates: dict[int, str]) -> list[dict]:
    """Every match, most surprising first (lowest win chance for the eventual winner, by today's ratings).
    "provisional": at least one of the four players is provisional today."""
    played: dict[str, int] = {}
    for r in results:
        for p in r.players:
            played[p] = played.get(p, 0) + 1
    rows = [
        {
            "match_id": r.match_id,
            "date": dates[r.match_id],
            "winners": list(r.winners),
            "losers": list(r.losers),
            "winner_prob": round(r.p_winner, 4),
            "provisional": any(played[p] < config.PROVISIONAL_UNTIL for p in r.players),
        }
        for r in results
    ]
    rows.sort(key=lambda x: (x["winner_prob"], -x["match_id"]))
    return rows


def longest_streaks(pstats: dict[str, dict]) -> dict[str, list[dict]]:
    """The TOP_STREAKS longest win streaks and loss streaks across all players (all-time)."""
    def top(key):
        rows = [{"name": s["name"], "len": s[key]} for s in pstats.values() if s[key] > 0]
        rows.sort(key=lambda x: (-x["len"], x["name"]))
        return rows[:config.TOP_STREAKS]
    return {"streaks_win": top("longest_win"), "streaks_loss": top("longest_loss")}


def form_lists(results: list[MatchResult]) -> dict:
    """Most Elo points won and lost within the league's last FORM_GLOBAL_MATCHES matches."""
    recent = results[-config.FORM_GLOBAL_MATCHES:]
    gain: dict[str, float] = {}
    played: dict[str, int] = {}
    for r in recent:
        for p in r.players:
            gain[p] = gain.get(p, 0.0) + r.delta[p]
            played[p] = played.get(p, 0) + 1
    rows = [{"name": p, "delta": round(g, 1), "matches": played[p]} for p, g in gain.items()]
    up = sorted((r for r in rows if r["delta"] > 0), key=lambda r: (-r["delta"], r["name"]))
    down = sorted((r for r in rows if r["delta"] < 0), key=lambda r: (r["delta"], r["name"]))
    return {"form_up": up[:config.TOP_FORM], "form_down": down[:config.TOP_FORM],
            "form_span": {"matches": len(recent),
                          "from": None, "to": None}}


def rank_gap_lists(pstats: dict[str, dict]) -> dict[str, list[dict]]:
    """Players whose Elo rank is better than their points rank, and the reverse.
    Both ranks count only Elo-ranked players, so rank_points here is the points-table order among
    them (not the league-wide rank_points). gap = points_rank - elo_rank (positive: Elo says they
    are better than the points table does)."""
    ranked = sorted((s for s in pstats.values() if s.get("rank_elo") is not None), key=lambda s: s["rank_points"])
    rows = [
        {"name": s["name"], "rank_points": rank, "rank_elo": s["rank_elo"], "gap": rank - s["rank_elo"]}
        for rank, s in enumerate(ranked, 1)
        if s["matches"] >= config.MIN_RANK_GAP_MATCHES
    ]
    elo_better = sorted((r for r in rows if r["gap"] > 0), key=lambda r: (-r["gap"], r["rank_elo"], r["name"]))
    points_better = sorted((r for r in rows if r["gap"] < 0), key=lambda r: (r["gap"], r["rank_points"], r["name"]))
    return {"elo_over_points": elo_better[:config.TOP_RANK_GAP],
            "points_over_elo": points_better[:config.TOP_RANK_GAP]}


def win_rate_lists(pstats: dict[str, dict]) -> dict[str, list[dict]]:
    """The TOP_WIN_RATE highest win rates among players with MIN_WIN_RATE_MATCHES+ matches.
    Ties on win rate go to the player with more matches, then by name."""
    rows = [
        {"name": s["name"], "matches": s["matches"], "wins": s["wins"], "losses": s["losses"],
         "win_rate": round(s["win_rate"], 4)}
        for s in pstats.values() if s["matches"] >= config.MIN_WIN_RATE_MATCHES
    ]
    best = sorted(rows, key=lambda r: (-r["win_rate"], -r["matches"], r["name"]))
    return {"win_rate_best": best[:config.TOP_WIN_RATE]}


def most_played_list(pstats: dict[str, dict]) -> dict[str, list[dict]]:
    """The TOP_MOST_PLAYED players with the most matches. Ties go to more wins, then by name."""
    rows = [
        {"name": s["name"], "matches": s["matches"], "wins": s["wins"], "losses": s["losses"]}
        for s in pstats.values() if s["matches"] > 0
    ]
    rows.sort(key=lambda r: (-r["matches"], -r["wins"], r["name"]))
    return {"most_played": rows[:config.TOP_MOST_PLAYED]}


def variety_lists(pstats: dict[str, dict]) -> dict[str, list[dict]]:
    """Who mixes the most / least (see stats.variety), among players with MIN_VARIETY_MATCHES+ matches."""
    rows = [
        {"name": s["name"], "matches": s["matches"], **s["variety"]}
        for s in pstats.values() if s["matches"] >= config.MIN_VARIETY_MATCHES
    ]
    varied = sorted(rows, key=lambda r: (r["top_share"], -r["distinct"], r["name"]))
    repeated = sorted(rows, key=lambda r: (-r["top_share"], r["distinct"], r["name"]))
    return {"variety_most": varied[:config.TOP_VARIETY], "variety_least": repeated[:config.TOP_VARIETY]}

