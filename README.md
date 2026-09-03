# Chalong Badminton Court League — stats site

Static stats site for our doubles league. Every statistic is computed in Python at build time and
written into one file, `docs/index.html`, which GitHub Pages serves. The site is a dumb viewer: plain
HTML/CSS/JS with the numbers embedded as JSON, Plotly loaded from a CDN, no framework, no server,
no database.

Matches can come from either of two places:

- **`data/matches.csv` in the repo**, typed in with `enter_matches.py` (the way we start).
- **A Google Sheet published as CSV**, filled by a Google Form (optional, later). When the repository
  variable `SHEET_CSV_URL` is set the hourly rebuild reads the sheet instead of the file.

---

## 1. Getting the old matches in (from photos)

`enter_matches.py` opens a window. The photo is on the left, the form on the right.

```powershell
.venv\Scripts\activate
python enter_matches.py --photos "C:\Users\Storm\Pictures\badminton"
```

(or run it without `--photos` and click *Choose photo folder*.)

- **Date** is prefilled from the photo (EXIF date, otherwise the file date). Change it if needed.
- **Winner 1, Winner 2, Loser 1, Loser 2**: type a few letters, the dropdown narrows down to the
  matching names from `data/players.csv`. `som` is enough for Somchai. Names not in the file are
  refused with a message under the form.
- **Enter** or *Save & next* writes the match to `data/matches.csv` right away and shows the next photo.
- *Skip photo* for a photo that is not a match. *Undo last* removes the last saved match and brings
  its photo back. *Open photo full size* opens it in your normal viewer.
- Close the window whenever you like. Photos already recorded are skipped next time.

Before you start, put the real names in `data/players.csv` (header `name`, one name per line, spelled
the way you want them shown on the site). Then build and look:

```powershell
python build.py --check              # rebuilds docs/index.html from data/matches.csv
python -m http.server -d docs 8000   # open http://localhost:8000
```

`data/reference_2026-08-23.csv` holds the totals from the photo of the results table, handy for
checking the transcription later. There is also a terminal version: `python enter_matches.py --cli`.

---

## 2. Publishing online (GitHub Pages), step by step

You need a free GitHub account and Git on your machine (you already have Git Bash).

1. **Create the account** at https://github.com/signup.
2. **Create an empty repository**: top-right **+** → *New repository*. Name it e.g.
   `badminton-stats`, keep it **Public** (Pages is free on public repos), do **not** tick
   "Add a README". Click *Create repository*.
3. **Push this folder** to it. In PowerShell inside the project folder:

   ```powershell
   git init
   git branch -M main
   git add .
   git commit -m "Badminton stats site"
   git remote add origin https://github.com/<your-username>/badminton-stats.git
   git push -u origin main
   ```

   Git opens a browser window to log in the first time.
4. **Turn on Pages**: in the repo, *Settings* → *Pages* → under *Build and deployment* set
   Source = **Deploy from a branch**, Branch = **main**, Folder = **/docs**, click *Save*.
5. **Allow the Action to push**: *Settings* → *Actions* → *General* → scroll to *Workflow
   permissions* → choose **Read and write permissions** → *Save*.
6. Wait a minute. The site is at `https://<your-username>.github.io/badminton-stats/`.
   Check *Actions* in the repo: the "Rebuild site" run should be green.

From now on the workflow in `.github/workflows/build.yml` runs on every push that touches the code
or the data, every hour, and on demand (*Actions* → *Rebuild site* → *Run workflow*). It runs the
tests, rebuilds `docs/index.html`, and commits it only if the page changed.

---

## 3. Adding new matches and new players, step by step

### New matches

1. `python enter_matches.py` (with or without `--photos`), enter the matches, close the window.
2. `python build.py --check` to make sure it builds (an unknown name stops it with the row number).
3. Push:

   ```powershell
   git add data/matches.csv docs/index.html
   git commit -m "Matches 2026-09-05"
   git push
   ```

4. The site updates within a couple of minutes. Pushing `docs/index.html` is optional: the Action
   rebuilds it anyway.

### New player

1. In the entry window click **Add player**, type the name, OK. It is appended to `data/players.csv`
   and is available in the name boxes right away. (Editing the file by hand works too.) The spelling
   here is the spelling on the site.
2. Enter their matches as usual.
3. Commit both files: `git add data/players.csv data/matches.csv`, commit, push.

If a match uses a name that is not in `players.csv`, the build fails on purpose and prints the row
number and a "did you mean" hint. Fix the name, do not add a second spelling.

### Switching to the Google Form later (optional)

1. Make a Google Form with fields: date, player A1, A2, B1, B2 (dropdowns from `players.csv`),
   winner (A/B), score A, score B. Responses go to a Sheet.
2. In the Sheet: *File → Share → Publish to web*, pick the responses tab, choose **CSV**, copy the URL.
3. In GitHub: *Settings → Secrets and variables → Actions → Variables → New repository variable*,
   name `SHEET_CSV_URL`, value = that URL.
4. From then on the hourly rebuild reads the sheet. To keep the old photo matches, paste the rows
   of `data/matches.csv` into the sheet (same columns; the `Timestamp` and `photo` columns are ignored).

---

## 4. Translations

All UI strings are in `site/i18n.js`. The ⓘ popups show the English explanation with the Thai
version underneath. The Thai texts are the `tip_*` entries under `I18N.th`, currently English
placeholders prefixed `TODO:`. Replace each string with the Thai text (keep the `{n}` / `{start}`
placeholders, they are filled with numbers). Rebuild and push.

---

## Running locally (Windows, Python 3.12+)

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

pytest -q                             # unit + end-to-end tests
python build.py --check               # -> docs/index.html, plus sanity checks
python -m http.server -d docs 8000
```

`build.py` reads `--csv <path or url>`, else the `SHEET_CSV_URL` environment variable, else
`data/matches.csv`. To try the site with made-up data: `python tests/fake_season.py --out tmp` then
`python build.py --csv tmp/sample.csv --players tmp/sample_players.csv`.

## How the numbers are computed

Everything lives in `badminton_stats/`; constants are in `config.py`.

- **League points**: +1 per win, −1 per loss, per player. The official ranking.
- **Elo (doubles)**: everyone starts at 1000. Team rating = mean of the two players.
  `expected(A) = 1 / (1 + 10^((R_B − R_A) / 400))`. Each player gets
  `delta = K × (result − expected)` with K = 48 for their first 5 matches, 32 afterwards.
  Teammates share `(result − expected)`, so their deltas are equal whenever their K is equal, and
  `Σ delta / K` over the four players is always zero.
- **Provisional**: fewer than 5 matches. Elo still updates, but the player has no Elo rank yet.
- **Partners**: the 5 most-played-with partners, with matches, wins, *expected wins* (sum of the
  pre-match win probability of the pair) and the difference.
- **Opponents**: most faced, nemesis (lowest win %, min 5 meetings), favourite victim (highest win %, min 5).
- **Hardest wins / easiest losses**: per player, the 3 wins with the lowest win chance and the 3
  losses with the highest, where the chance is recomputed from the four players' *current* Elo.
- **Upsets**: matches ordered by the winners' pre-match win probability, lowest first.
- **Longest streaks**: the 3 longest win streaks and 3 longest loss streaks ever recorded.
- **Hot / cold form** (home): within the league's last 10 matches, the 3 players who gained and the 3 who
  lost the most Elo. The player page card "Form (last 3)" is that player's own last 3 matches.
- **Elo vs points**: players whose Elo rank is better than their points rank and the reverse (min 5 matches).
- **Points race**: home ends with cumulative points over time for the top 5 players.
- **Per player extras**: peak and lowest Elo with dates, average opponent and partner strength
  (today's Elo, averaged per match).
- **Ordering**: matches are sorted by date; same-day matches keep the order they have in the file/sheet.

Sanity checks (`python build.py --check`): per-match deltas are zero-sum (weighted by 1/K),
provisional players are absent from the Elo ranking, and the top five by Elo is printed.

## Layout

```
build.py                 CLI entry point (CSV -> docs/index.html)
enter_matches.py         GUI (or --cli) to type matches in photo by photo -> data/matches.csv
badminton_stats/         load (fetch + validate), elo, stats, global_stats, payload, render
site/                    template.html, style.css, i18n.js, app.js  (inlined into docs/index.html)
data/                    players.csv (names), matches.csv (matches), reference_2026-08-23.csv (photo totals)
docs/index.html          generated output, served by GitHub Pages
tests/                   pytest suite (+ fake_season.py, a fake data generator used by the tests)
```
