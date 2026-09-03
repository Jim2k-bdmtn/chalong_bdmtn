"""Generate a realistic fake season. Used by the test suite; can also be run by hand to try the site
without real data:

    python tests/fake_season.py --out some_folder     # writes sample_players.csv and sample.csv there
    python build.py --csv some_folder/sample.csv --players some_folder/sample_players.csv

50 players with a hidden "true skill", a strong outlier ("Ace") who should end up near the top of
the Elo table, and a long tail of casual players with only 1-3 matches. About 400 matches spread over
Jan-Aug 2026 on Tue/Thu/Sat nights. The CSV mimics a Google Form export: a Timestamp column first
(ignored by the loader), ISO dates, and ~10 % of matches without scores.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import random
from pathlib import Path

SEED = 20260101
N_MATCHES = 400
START = dt.date(2026, 1, 1)
END = dt.date(2026, 8, 31)
PLAY_DAYS = {1, 3, 5}  # Tue, Thu, Sat

NAMES = [
    "Ace", "Somchai", "Nok", "Ploy", "Beam", "Tom", "Mike", "Fon", "Golf", "Bank",
    "Aom", "Pim", "Kwan", "Nat", "Oat", "Boss", "Jib", "Mint", "Tar", "Ice",
    "Nan", "Pae", "Gift", "Bell", "First", "Earth", "Prae", "Film", "Toey", "Nut",
    "Mook", "Por", "Best", "Kai", "Fah", "Pui", "Chai", "Dew", "Muk", "Yok",
    "Anna", "Ben", "Chris", "Dan", "Eve", "Frank", "Grace", "Hugo", "Ivy", "Jack",
]
CASUALS = {"Ivy": 1, "Jack": 2, "Hugo": 3, "Grace": 2}  # forced tiny match counts


def main(out_dir: Path) -> None:
    rng = random.Random(SEED)
    skill = {n: rng.gauss(1000, 160) for n in NAMES}
    skill["Ace"] = 1550  # the clear outlier the Elo sanity check looks for
    activity = {n: rng.lognormvariate(0, 0.6) for n in NAMES}
    activity["Ace"] = 2.5
    for n in CASUALS:
        activity[n] = 0.0  # scheduled explicitly below

    nights = [START + dt.timedelta(days=i) for i in range((END - START).days + 1)]
    nights = [d for d in nights if d.weekday() in PLAY_DAYS]
    per_night = N_MATCHES / len(nights)

    regulars = [n for n in NAMES if n not in CASUALS]
    weights = [activity[n] for n in regulars]

    matches: list[dict] = []

    def play(date: dt.date, present: list[str]) -> None:
        pool = present[:]
        rng.shuffle(pool)
        a1, a2, b1, b2 = pool[:4]
        team_a, team_b = (a1, a2), (b1, b2)
        ra = (skill[a1] + skill[a2]) / 2
        rb = (skill[b1] + skill[b2]) / 2
        p_a = 1 / (1 + 10 ** ((rb - ra) / 400))
        winner = "A" if rng.random() < p_a else "B"
        if rng.random() < 0.10:
            sa = sb = ""
        else:
            if rng.random() < 0.12:               # deuce game
                lose = rng.randint(20, 28)
                win = lose + 2 if lose < 29 else 30
            else:
                win, lose = 21, rng.randint(5, 19)
            sa, sb = (win, lose) if winner == "A" else (lose, win)
        ts = dt.datetime.combine(date, dt.time(19, 0)) + dt.timedelta(minutes=len(matches) % 7 * 17)
        matches.append({
            "Timestamp": ts.strftime("%m/%d/%Y %H:%M:%S"),
            "date": date.isoformat(),
            "player_a1": team_a[0], "player_a2": team_a[1],
            "player_b1": team_b[0], "player_b2": team_b[1],
            "winner": winner, "score_a": sa, "score_b": sb,
        })

    casual_nights = {n: set(rng.sample(nights, k)) for n, k in CASUALS.items()}

    for night in nights:
        n_matches = max(1, round(rng.gauss(per_night, 1.2)))
        n_present = rng.randint(8, 14)
        present = set()
        while len(present) < n_present:
            present.add(rng.choices(regulars, weights)[0])
        present = list(present)
        for n, days in casual_nights.items():
            if night in days:   # casual plays exactly one match and is not in the regular pool
                play(night, [n] + rng.sample(present, 3))
        for _ in range(n_matches):
            play(night, present)

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "sample_players.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name"])
        for n in sorted(NAMES):
            w.writerow([n])
    with (out_dir / "sample.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(matches[0].keys()))
        w.writeheader()
        w.writerows(matches)

    counts = {n: 0 for n in NAMES}
    for m in matches:
        for c in ("player_a1", "player_a2", "player_b1", "player_b2"):
            counts[m[c]] += 1
    print(f"wrote {len(matches)} matches for {len(NAMES)} players to {out_dir}")
    print("fewest matches:", sorted(counts.items(), key=lambda kv: kv[1])[:6])
    print("most matches:  ", sorted(counts.items(), key=lambda kv: -kv[1])[:4])
    print(f"Ace true skill {skill['Ace']:.0f}, group mean {sum(skill.values())/len(skill):.0f}, "
          f"stdev {math.sqrt(sum((s-1000)**2 for s in skill.values())/len(skill)):.0f}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="folder to write sample_players.csv and sample.csv into")
    main(Path(ap.parse_args().out))
