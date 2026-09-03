"""Tunable constants. Everything the stats depend on lives here."""

START_RATING = 1000.0
K_NEW = 48          # K-factor while a player has fewer than PROVISIONAL_UNTIL matches
K_ESTABLISHED = 32  # K-factor afterwards
PROVISIONAL_UNTIL = 5   # players with fewer matches than this are "provisional"

MIN_OPPONENT_MATCHES = 5  # for nemesis / victim
FORM_LENGTH = 10          # results shown in "form"
HOME_UPSETS = 5           # upsets shown on the home page
TOP_STREAKS = 3           # longest win / loss streaks shown on the home page
TOP_PARTNERS = 5          # most-played-with partners shown per player
TOP_MATCHES = 3           # hardest wins / easiest losses shown per player
FORM_WINDOW = 3           # per-player: matches summed for the "Form (last 3)" card
FORM_GLOBAL_MATCHES = 10  # home page hot/cold form: Elo change within the league's last N matches
TOP_FORM = 3              # players shown in each form list
TOP_RANK_GAP = 3          # players shown in each Elo-vs-points list
MIN_RANK_GAP_MATCHES = 5  # matches needed to appear in the Elo-vs-points lists
TOP_POINTS_CHART = 5      # players drawn in the points-race chart on the home page

REQUIRED_COLUMNS = [
    "date", "player_a1", "player_a2", "player_b1", "player_b2",
    "winner", "score_a", "score_b",
]
PLAYER_COLUMNS = ["player_a1", "player_a2", "player_b1", "player_b2"]
