"""League-wide tables: leaderboards, upsets, longest streaks, scatter data."""
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
    """Every match, most surprising first (lowest pre-match probability for the eventual winner)."""
    rows = [
        {
            "match_id": r.match_id,
            "date": dates[r.match_id],
            "winners": list(r.winners),
            "losers": list(r.losers),
            "winner_prob": round(r.p_winner, 4),
            "provisional": any(r.matches_before[p] < config.PROVISIONAL_UNTIL for p in r.players),
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
    """Biggest Elo gain and biggest Elo loss within the league's last FORM_GLOBAL_MATCHES matches."""
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
    gap = points_rank - elo_rank (positive: Elo says they are better than the points table does)."""
    rows = [
        {"name": s["name"], "rank_points": s["rank_points"], "rank_elo": s["rank_elo"],
         "gap": s["rank_points"] - s["rank_elo"]}
        for s in pstats.values()
        if s["matches"] >= config.MIN_RANK_GAP_MATCHES and s.get("rank_elo") is not None
        and s.get("rank_points") is not None
    ]
    elo_better = sorted((r for r in rows if r["gap"] > 0), key=lambda r: (-r["gap"], r["rank_elo"], r["name"]))
    points_better = sorted((r for r in rows if r["gap"] < 0), key=lambda r: (r["gap"], r["rank_points"], r["name"]))
    return {"elo_over_points": elo_better[:config.TOP_RANK_GAP],
            "points_over_elo": points_better[:config.TOP_RANK_GAP]}


def scatter(pstats: dict[str, dict]) -> list[dict]:
    return [
        {"name": s["name"], "matches": s["matches"], "win_rate": round(s["win_rate"], 4),
         "elo": s["elo"], "provisional": s["provisional"]}
        for s in pstats.values() if s["matches"] > 0
    ]
