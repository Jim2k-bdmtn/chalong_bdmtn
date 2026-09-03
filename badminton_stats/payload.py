"""Turn a validated match DataFrame into the JSON blob the site reads."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from . import config, global_stats
from .elo import EloState, MatchResult, replay
from .stats import player_stats


def replay_frame(df: pd.DataFrame) -> tuple[list[MatchResult], EloState, dict[int, str]]:
    """Run the Elo engine over the frame. Returns (results, final state, match_id -> ISO date)."""
    matches = [
        (int(row.match_id), (row.player_a1, row.player_a2), (row.player_b1, row.player_b2), row.winner)
        for row in df.itertuples(index=False)
    ]
    results, state = replay(matches)
    dates = {int(r.match_id): r.date.strftime("%Y-%m-%d") for r in df.itertuples(index=False)}
    return results, state, dates


def _form(results, dates):
    out = global_stats.form_lists(results)
    recent = results[-config.FORM_GLOBAL_MATCHES:]
    if recent:
        out["form_span"] = {"matches": len(recent), "from": dates[recent[0].match_id], "to": dates[recent[-1].match_id]}
    return out


def _score(v) -> int | None:
    return None if pd.isna(v) else int(v)


def build_payload(df: pd.DataFrame, players: list[str]) -> dict:
    results, state, dates = replay_frame(df)
    pstats = player_stats(players, results, state, dates)
    boards = global_stats.leaderboards(pstats)

    match_rows = []
    for row, r in zip(df.itertuples(index=False), results):
        match_rows.append({
            "id": r.match_id,
            "date": dates[r.match_id],
            "month": dates[r.match_id][:7],
            "a": list(r.team_a),
            "b": list(r.team_b),
            "winner": r.winner,
            "score_a": _score(row.score_a),
            "score_b": _score(row.score_b),
            "p_a": round(r.p_a, 4),
            "winner_prob": round(r.p_winner, 4),
            "deltas": {p: round(d, 1) for p, d in r.delta.items()},
            "elo_before": {p: round(v, 1) for p, v in r.rating_before.items()},
        })

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "config": {
            "start_rating": config.START_RATING,
            "k_new": config.K_NEW,
            "k_established": config.K_ESTABLISHED,
            "provisional_until": config.PROVISIONAL_UNTIL,
            "min_opponent_matches": config.MIN_OPPONENT_MATCHES,
            "form_length": config.FORM_LENGTH,
            "home_upsets": config.HOME_UPSETS,
            "top_streaks": config.TOP_STREAKS,
            "top_partners": config.TOP_PARTNERS,
            "top_matches": config.TOP_MATCHES,
            "form_window": config.FORM_WINDOW,
            "form_global_matches": config.FORM_GLOBAL_MATCHES,
            "min_rank_gap_matches": config.MIN_RANK_GAP_MATCHES,
            "top_points_chart": config.TOP_POINTS_CHART,
        },
        "players": pstats,
        **boards,
        "upsets": global_stats.upsets(results, dates),
        **global_stats.longest_streaks(pstats),
        **_form(results, dates),
        **global_stats.rank_gap_lists(pstats),
        "scatter": global_stats.scatter(pstats),
        "matches": match_rows,
    }
