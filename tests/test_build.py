"""End-to-end: fake season -> payload -> index.html, plus the three sanity checks from the spec."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests import fake_season  # noqa: E402
from badminton_stats import config  # noqa: E402
from badminton_stats.load import load_matches, load_players  # noqa: E402
from badminton_stats.payload import build_payload, replay_frame  # noqa: E402
from badminton_stats.render import render  # noqa: E402


@pytest.fixture(scope="module")
def season(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    fake_season.main(d)
    players = load_players(str(d / "sample_players.csv"))
    df = load_matches(str(d / "sample.csv"), players)
    return players, df, build_payload(df, players)


def test_fake_data_shape(season):
    players, df, payload = season
    assert len(players) == 50
    assert 350 <= len(df) <= 450
    counts = {p: payload["players"][p]["matches"] for p in players}
    assert counts["Ivy"] == 1 and counts["Jack"] == 2 and counts["Hugo"] == 3
    assert min(counts.values()) >= 1
    assert df["score_a"].isna().sum() > 10          # some blank scores survive


def test_elo_deltas_zero_sum_every_match(season):
    _, df, _ = season
    results, _, _ = replay_frame(df)
    for r in results:
        assert sum(r.delta[p] / r.k[p] for p in r.players) == pytest.approx(0.0, abs=1e-9)
        same_k = len({r.k[p] for p in r.players}) == 1
        if same_k:
            assert sum(r.delta.values()) == pytest.approx(0.0, abs=1e-9)


def test_provisional_players_excluded_from_elo_ranking(season):
    _, _, payload = season
    for name in payload["leaderboard_elo"]:
        assert payload["players"][name]["matches"] >= config.PROVISIONAL_UNTIL
        assert payload["players"][name]["rank_elo"] is not None
    for name in payload["provisional"]:
        assert payload["players"][name]["matches"] < config.PROVISIONAL_UNTIL
        assert payload["players"][name]["rank_elo"] is None
    ranked = set(payload["leaderboard_elo"])
    assert ranked.isdisjoint(payload["provisional"])
    assert ranked | set(payload["provisional"]) == set(payload["players"])


def test_strong_fake_player_converges_high(season):
    _, _, payload = season
    ace = payload["players"]["Ace"]
    assert ace["elo"] >= 1100
    assert ace["rank_elo"] is not None and ace["rank_elo"] <= 5


def test_points_and_leaderboards_consistent(season):
    _, _, payload = season
    for name, s in payload["players"].items():
        assert s["points"] == s["wins"] - s["losses"]
        assert len(s["form"]) <= config.FORM_LENGTH
    ranks = [payload["players"][n]["rank_points"] for n in payload["leaderboard_points"]]
    assert ranks == list(range(1, len(ranks) + 1))
    assert payload["upsets"][0]["winner_prob"] <= payload["upsets"][-1]["winner_prob"]
    sw, sl = payload["streaks_win"], payload["streaks_loss"]
    assert len(sw) == config.TOP_STREAKS and len(sl) == config.TOP_STREAKS
    assert sw[0]["len"] == max(s["longest_win"] for s in payload["players"].values())
    assert sl[0]["len"] == max(s["longest_loss"] for s in payload["players"].values())
    for name, s in payload["players"].items():
        assert len(s["partners"]) <= config.TOP_PARTNERS
        assert len(s["hardest_wins"]) <= config.TOP_MATCHES
    fu, fd = payload["form_up"], payload["form_down"]
    assert 0 < len(fu) <= config.TOP_FORM and 0 < len(fd) <= config.TOP_FORM
    recent = payload["matches"][-config.FORM_GLOBAL_MATCHES:]
    gain = {}
    for m_ in recent:
        for p, d in m_["deltas"].items():
            gain[p] = gain.get(p, 0) + d
    assert fu[0]["delta"] == pytest.approx(max(gain.values()), abs=0.11)
    assert fd[0]["delta"] == pytest.approx(min(gain.values()), abs=0.11)
    assert payload["form_span"]["matches"] == config.FORM_GLOBAL_MATCHES
    assert payload["form_span"]["from"] <= payload["form_span"]["to"]
    for r in payload["elo_over_points"]:
        assert r["rank_elo"] < r["rank_points"] and payload["players"][r["name"]]["matches"] >= config.MIN_RANK_GAP_MATCHES
    for r in payload["points_over_elo"]:
        assert r["rank_points"] < r["rank_elo"]


def test_render_embeds_valid_json(season, tmp_path):
    _, _, payload = season
    out = render(payload, tmp_path / "index.html")
    html = out.read_text(encoding="utf-8")
    assert "cdn.plot.ly" in html
    assert "{{" not in html
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    assert m, "data block not found"
    embedded = json.loads(m.group(1).replace("<\\/", "</"))
    assert set(embedded) >= {"players", "leaderboard_points", "leaderboard_elo", "provisional",
                             "upsets", "streaks_win", "streaks_loss", "scatter", "matches", "config"}
    assert embedded["players"]["Ace"]["elo"] == payload["players"]["Ace"]["elo"]
