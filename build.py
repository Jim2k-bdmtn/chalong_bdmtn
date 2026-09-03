"""Build the static site.

    python build.py                          # data/matches.csv -> docs/index.html
    python build.py --csv "https://docs.google.com/.../pub?output=csv"
    python build.py --check                  # also print the sanity checks

The CSV source is picked in this order: --csv, the SHEET_CSV_URL environment variable,
data/matches.csv (real matches typed in with enter_matches.py).
Any validation problem aborts with a non-zero exit and a list of offending sheet rows.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from badminton_stats import config
from badminton_stats.load import ValidationError, load_matches, load_players
from badminton_stats.payload import build_payload, replay_frame
from badminton_stats.render import render

ROOT = Path(__file__).resolve().parent


def sanity_checks(df, payload) -> list[tuple[str, bool, str]]:
    """The three checks from the spec. Returns (name, passed, detail)."""
    results, state, _ = replay_frame(df)
    checks = []

    worst = max((abs(sum(r.delta[p] / r.k[p] for p in r.players)) for r in results), default=0.0)
    checks.append(("Per-match deltas sum to zero (weighted by 1/K)", worst < 1e-9,
                   f"max |sum(delta/K)| = {worst:.2e} over {len(results)} matches"))

    ranked = payload["leaderboard_elo"]
    bad = [p for p in ranked if payload["players"][p]["matches"] < config.PROVISIONAL_UNTIL]
    checks.append(("Provisional players excluded from Elo ranking", not bad,
                   f"{len(ranked)} ranked, {len(payload['provisional'])} provisional, "
                   f"offenders: {bad or 'none'}"))

    top = ranked[:5]
    detail = (", ".join(f"{p} {payload['players'][p]['elo']:.0f}" for p in top)
              or f"nobody has {config.PROVISIONAL_UNTIL} matches yet")
    checks.append(("Top 5 by Elo", True, detail))
    return checks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=os.environ.get("SHEET_CSV_URL") or str(ROOT / "data" / "matches.csv"),
                    help="match CSV: local path or published-sheet URL")
    ap.add_argument("--players", default=str(ROOT / "data" / "players.csv"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "index.html"))
    ap.add_argument("--check", action="store_true", help="print sanity checks after building")
    args = ap.parse_args(argv)

    if not args.csv.startswith(("http://", "https://")) and not Path(args.csv).exists():
        print(f"ERROR: {args.csv} does not exist. Enter matches with enter_matches.py first.", file=sys.stderr)
        return 1
    try:
        players = load_players(args.players)
        df = load_matches(args.csv, players)
    except ValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    payload = build_payload(df, players)
    out = render(payload, args.out)
    print(f"Built {out} from {len(df)} matches, {len(players)} players "
          f"({len(payload['leaderboard_elo'])} ranked, {len(payload['provisional'])} provisional).")

    if args.check:
        ok_all = True
        for name, ok, detail in sanity_checks(df, payload):
            ok_all &= ok
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        return 0 if ok_all else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
