"""Tunable constants. Everything the stats depend on lives here."""

START_RATING = 1000.0
# Classic sequential Elo (elo.py) is kept for reference and tests; the site uses the season fit in level.py.
K_NEW = 48          # K-factor while a player has fewer than K_NEW_UNTIL matches
K_ESTABLISHED = 32  # K-factor afterwards
K_NEW_UNTIL = 5     # matches played with the higher K-factor (changing this changes every rating)
PROVISIONAL_UNTIL = 10  # players with fewer matches than this are "provisional": no Elo rank
LEVEL_PRIOR_SD = 200.0  # season-fit rating: prior pull towards START_RATING (points); smaller = stronger pull

MIN_OPPONENT_MATCHES = 5  # for nemesis / victim
FORM_LENGTH = 10          # results shown in "form"
HOME_UPSETS = 5           # upsets shown on the home page
HOME_LAST_MATCHES = 3     # most recent matches shown on the home page
TOP_STREAKS = 3           # longest win / loss streaks shown on the home page
TOP_PARTNERS = 5          # most-played-with partners shown per player
TOP_MATCHES = 3           # hardest wins / easiest losses shown per player
FORM_WINDOW = 3           # per-player: matches summed for the "Form (last 3)" card
FORM_GLOBAL_MATCHES = 10  # home page hot/cold form: Elo change within the league's last N matches
TOP_FORM = 3              # players shown in each form list
TOP_RANK_GAP = 3          # players shown in each Elo-vs-points list
MIN_RANK_GAP_MATCHES = 5  # matches needed to appear in the Elo-vs-points lists
TOP_WIN_RATE = 5          # players shown in the best win-rate list
MIN_WIN_RATE_MATCHES = 5  # matches needed to appear in the best win-rate list
TOP_POINTS_CHART = 5      # players drawn in the points-race chart on the home page

REQUIRED_COLUMNS = [
    "date", "player_a1", "player_a2", "player_b1", "player_b2",
    "winner", "score_a", "score_b",
]
PLAYER_COLUMNS = ["player_a1", "player_a2", "player_b1", "player_b2"]
