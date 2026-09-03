"""Fetch the match CSV, validate it strictly, and return a clean chronological DataFrame.

Philosophy: never guess. Any unknown name, contradictory score, or malformed row aborts the
build with ONE error message that lists every problem and the sheet row it is on.
"""
from __future__ import annotations

import difflib
import io
from pathlib import Path

import pandas as pd
import requests

from . import config


class ValidationError(Exception):
    """Raised with a multi-line message listing every problem found."""


def _read_text(source: str) -> str:
    if source.startswith(("http://", "https://")):
        resp = requests.get(source, timeout=30)
        if resp.status_code != 200:
            raise ValidationError(f"Fetching {source} returned HTTP {resp.status_code}")
        resp.encoding = "utf-8"
        return resp.text.lstrip("﻿")
    return Path(source).read_text(encoding="utf-8-sig")


def load_players(path: str) -> list[str]:
    """players.csv: a header row `name` then one canonical name per line."""
    df = pd.read_csv(io.StringIO(_read_text(path)), dtype=str, keep_default_na=False)
    cols = [c.strip().lower() for c in df.columns]
    if "name" not in cols:
        raise ValidationError(f"players file {path} needs a 'name' column, has {list(df.columns)}")
    names = [str(n).strip() for n in df.iloc[:, cols.index("name")].tolist()]
    names = [n for n in names if n]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValidationError(f"players file has duplicate names: {dupes}")
    if not names:
        raise ValidationError(f"players file {path} lists no players")
    return names


def _norm_header(c: str) -> str:
    return str(c).strip().lower().replace(" ", "_")


def load_matches(source: str, players: list[str]) -> pd.DataFrame:
    """Return a DataFrame with columns
    match_id, date (datetime64), player_a1..player_b2, winner ('A'/'B'),
    score_a, score_b (Int64, NA allowed), sorted by date with a stable sort so
    same-day matches keep the order they have in the sheet."""
    raw = pd.read_csv(io.StringIO(_read_text(source)), dtype=str, keep_default_na=False)
    raw.columns = [_norm_header(c) for c in raw.columns]

    missing = [c for c in config.REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValidationError(
            f"CSV is missing required column(s) {missing}. Found columns: {list(raw.columns)}")

    df = raw[config.REQUIRED_COLUMNS].copy()
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()

    # Drop rows that are entirely blank (Sheets sometimes exports trailing empties).
    df = df[(df != "").any(axis=1)].copy()

    known = set(players)
    errors: list[str] = []

    def err(idx: int, msg: str) -> None:
        errors.append(f"row {idx + 2}: {msg}")   # +2 = header row + 1-based index

    for idx, row in df.iterrows():
        names = [row[c] for c in config.PLAYER_COLUMNS]
        for col, name in zip(config.PLAYER_COLUMNS, names):
            if not name:
                err(idx, f"{col} is blank")
            elif name not in known:
                hint = difflib.get_close_matches(name, players, n=1, cutoff=0.6)
                suffix = f" (did you mean {hint[0]!r}?)" if hint else ""
                err(idx, f"unknown player {name!r} in {col}{suffix}. "
                         "Fix the sheet or add them to players.csv")
        filled = [n for n in names if n]
        if len(set(filled)) != len(filled):
            err(idx, f"same player appears twice in one match: {names}")

        if row["winner"] not in ("A", "B"):
            err(idx, f"winner must be exactly 'A' or 'B', got {row['winner']!r}")

        if not row["date"]:
            err(idx, "date is blank")

        sa, sb = row["score_a"], row["score_b"]
        if (sa == "") != (sb == ""):
            err(idx, f"only one score filled in (score_a={sa!r}, score_b={sb!r}); fill both or neither")
        elif sa != "":
            try:
                ia, ib = int(sa), int(sb)
            except ValueError:
                err(idx, f"scores must be whole numbers, got {sa!r} and {sb!r}")
            else:
                if ia == ib:
                    err(idx, f"scores are equal ({ia}-{ib}); a match cannot be a draw")
                elif row["winner"] in ("A", "B"):
                    implied = "A" if ia > ib else "B"
                    if implied != row["winner"]:
                        err(idx, f"score {ia}-{ib} says team {implied} won "
                                 f"but winner column says {row['winner']}")

    parsed = pd.to_datetime(df["date"].replace("", None), errors="coerce")
    for idx, orig, val in zip(df.index, df["date"], parsed):
        if orig and pd.isna(val):
            err(idx, f"cannot parse date {orig!r}")

    if errors:
        raise ValidationError(
            f"{len(errors)} problem(s) in the match sheet, nothing was built:\n  "
            + "\n  ".join(errors))

    df["date"] = parsed.dt.normalize()
    df["score_a"] = pd.to_numeric(df["score_a"].replace("", None)).astype("Int64")
    df["score_b"] = pd.to_numeric(df["score_b"].replace("", None)).astype("Int64")
    df = df.sort_values("date", kind="stable").reset_index(drop=True)
    df.insert(0, "match_id", range(1, len(df) + 1))
    return df
