"""Type matches in by hand, photo by photo, straight into data/matches.csv.

    python enter_matches.py                                   # GUI, pick the photo folder with a button
    python enter_matches.py --photos "C:\\path\\to\\pics"    # GUI, folder preselected
    python enter_matches.py --cli [--photos DIR]              # terminal version of the same thing

GUI: the photo is shown on the left. On the right: date (prefilled from the photo), two winners,
two losers. Type a few letters in a name box and the list narrows down; a name that
is not in data/players.csv is refused. Enter or "Save & next" writes the row and moves to the next
photo. Photos already recorded are skipped, so you can close the window and continue later.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLAYERS_FILE = ROOT / "data" / "players.csv"
MATCHES_FILE = ROOT / "data" / "matches.csv"
COLUMNS = ["date", "player_a1", "player_a2", "player_b1", "player_b2", "winner", "score_a", "score_b", "photo"]
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


# ============================================================== shared logic
def load_players() -> list[str]:
    with PLAYERS_FILE.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    names = [r["name"].strip() for r in rows if r.get("name", "").strip()]
    if not names:
        sys.exit(f"No players in {PLAYERS_FILE}. Fill it first (header 'name', one name per line).")
    return names


def match_name(text: str, players: list[str]) -> list[str]:
    """Candidates for what the user typed, best first. One candidate = unambiguous."""
    q = text.strip().lower()
    if not q:
        return []
    exact = [p for p in players if p.lower() == q]
    if exact:
        return exact
    prefix = [p for p in players if p.lower().startswith(q)]
    if prefix:
        return prefix
    inside = [p for p in players if q in p.lower()]
    if inside:
        return inside
    lowered = {p.lower(): p for p in players}
    return [lowered[m] for m in difflib.get_close_matches(q, list(lowered), n=5, cutoff=0.5)]


def photo_date(path: Path) -> str:
    try:
        from PIL import Image
        with Image.open(path) as im:
            exif = im.getexif()
            raw = exif.get(36867) or exif.get(306)   # DateTimeOriginal, DateTime
            if raw:
                return dt.datetime.strptime(str(raw)[:10], "%Y:%m:%d").date().isoformat()
    except Exception:
        pass
    return dt.date.fromtimestamp(path.stat().st_mtime).isoformat()


def read_rows() -> list[dict]:
    if not MATCHES_FILE.exists():
        return []
    with MATCHES_FILE.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(rows: list[dict]) -> None:
    MATCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MATCHES_FILE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})


def list_photos(folder: Path, done: set[str]) -> list[Path]:
    photos = sorted(p for p in folder.iterdir() if p.suffix.lower() in PHOTO_EXT)
    return [p for p in photos if p.name not in done]


def describe(row: dict) -> str:
    score = f" {row['score_a']}-{row['score_b']}" if row.get("score_a") else ""
    return (f"{row['date']}  {row['player_a1']} & {row['player_a2']}  beat  "
            f"{row['player_b1']} & {row['player_b2']}{score}")


def validate(players: list[str], date: str, names: list[str], score: str = "") -> tuple[dict | None, str]:
    """Turn raw field values into a row. Returns (row, error message)."""
    try:
        date = dt.date.fromisoformat(date.strip()).isoformat()
    except ValueError:
        return None, "Date must look like 2026-03-14"
    resolved = []
    for label, raw in zip(("Winner 1", "Winner 2", "Loser 1", "Loser 2"), names):
        cands = match_name(raw, players)
        if len(cands) == 1:
            resolved.append(cands[0])
        elif not cands:
            return None, f"{label}: no player matches {raw.strip()!r}"
        else:
            return None, f"{label}: {raw.strip()!r} could be {', '.join(cands[:5])}"
    if len(set(resolved)) != 4:
        return None, "The same player appears twice"
    sw = sl = ""
    if score.strip():
        parts = score.replace(":", "-").replace(" ", "-").split("-")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            return None, "Score must look like 21-15 (winners first), or be empty"
        if int(parts[0]) <= int(parts[1]):
            return None, "The winners' score must be the higher one"
        sw, sl = parts
    return {"date": date, "player_a1": resolved[0], "player_a2": resolved[1],
            "player_b1": resolved[2], "player_b2": resolved[3], "winner": "A",
            "score_a": sw, "score_b": sl, "photo": ""}, ""


# ============================================================== GUI
def run_gui(photos_dir: str | None, smoke: bool = False) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    players = load_players()
    rows = read_rows()
    state = {"photos": [], "i": 0, "folder": None, "img": None}

    root = tk.Tk()
    root.title("Badminton match entry")
    root.geometry("1100x680")
    root.minsize(900, 560)

    # ---- left: photo
    left = ttk.Frame(root, padding=8)
    left.pack(side="left", fill="both", expand=True)
    photo_label = ttk.Label(left, text="No photo folder chosen.\nUse 'Choose photo folder' or just type matches.",
                            anchor="center", justify="center", relief="groove")
    photo_label.pack(fill="both", expand=True)
    progress = ttk.Label(left, text="", font=("Segoe UI", 10))
    progress.pack(fill="x", pady=(6, 0))

    # ---- right: form
    right = ttk.Frame(root, padding=12)
    right.pack(side="right", fill="y")
    ttk.Label(right, text="Match", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")

    ttk.Label(right, text="Date").grid(row=1, column=0, sticky="w", pady=(10, 2))
    date_var = tk.StringVar(value=rows[-1]["date"] if rows else dt.date.today().isoformat())
    date_entry = ttk.Entry(right, textvariable=date_var, width=16, font=("Segoe UI", 11))
    date_entry.grid(row=1, column=1, sticky="w", pady=(10, 2))

    name_vars: list[tk.StringVar] = []
    name_boxes: list[ttk.Combobox] = []
    labels = [("Winners", "Winner 1"), ("", "Winner 2"), ("Losers", "Loser 1"), ("", "Loser 2")]
    r = 2
    for section, label in labels:
        if section:
            ttk.Label(right, text=section, font=("Segoe UI", 11, "bold"),
                      foreground="#1a8f4c" if section == "Winners" else "#d1373b").grid(
                row=r, column=0, columnspan=2, sticky="w", pady=(12, 2))
            r += 1
        ttk.Label(right, text=label).grid(row=r, column=0, sticky="w", pady=2)
        var = tk.StringVar()
        box = ttk.Combobox(right, textvariable=var, values=players, width=22, font=("Segoe UI", 11))
        box.grid(row=r, column=1, sticky="w", pady=2)
        name_vars.append(var)
        name_boxes.append(box)
        r += 1


    error = ttk.Label(right, text="", foreground="#d1373b", wraplength=280)
    error.grid(row=r, column=0, columnspan=2, sticky="w", pady=(10, 2))
    r += 1

    btns = ttk.Frame(right)
    btns.grid(row=r, column=0, columnspan=2, sticky="we", pady=(8, 4))
    r += 1

    saved = ttk.Label(right, text=f"{len(rows)} matches in matches.csv", foreground="#5f6b7a")
    saved.grid(row=r, column=0, columnspan=2, sticky="w", pady=(6, 2))
    r += 1
    last = tk.Text(right, height=6, width=40, font=("Segoe UI", 9), state="disabled", relief="flat",
                   background=root.cget("background"))
    last.grid(row=r, column=0, columnspan=2, sticky="we")

    # ---- behaviour
    def narrow(box: ttk.Combobox, var: tk.StringVar):
        def on_key(event):
            if event.keysym in ("Up", "Down", "Return", "Tab", "Escape"):
                return
            typed = var.get()
            cands = match_name(typed, players) if typed.strip() else players
            box["values"] = cands or players
        box.bind("<KeyRelease>", on_key)

    for box, var in zip(name_boxes, name_vars):
        narrow(box, var)

    def log(text: str):
        last.configure(state="normal")
        last.insert("1.0", text + "\n")
        last.configure(state="disabled")

    def show_photo():
        photos = state["photos"]
        i = state["i"]
        if state["folder"] is None:
            return
        if i >= len(photos):
            photo_label.configure(image="", text="All photos done.\nYou can still type matches by hand.")
            progress.configure(text=f"{len(photos)} photos done")
            return
        path = photos[i]
        progress.configure(text=f"Photo {i + 1} of {len(photos)}   {path.name}")
        date_var.set(photo_date(path))
        try:
            from PIL import Image, ImageOps, ImageTk
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)
                w = max(300, photo_label.winfo_width() - 8)
                h = max(300, photo_label.winfo_height() - 8)
                im.thumbnail((w, h))
                state["img"] = ImageTk.PhotoImage(im)
            photo_label.configure(image=state["img"], text="")
        except Exception as e:  # no Pillow or unreadable file: open externally
            photo_label.configure(image="", text=f"{path.name}\n(cannot preview: {e})\nOpened in your image viewer.")
            try:
                os.startfile(str(path))
            except Exception:
                pass

    def clear_form():
        for v in name_vars:
            v.set("")
        for b in name_boxes:
            b["values"] = players
        error.configure(text="")
        name_boxes[0].focus_set()

    def choose_folder(path: str | None = None):
        path = path or filedialog.askdirectory(title="Folder with match photos")
        if not path:
            return
        state["folder"] = Path(path)
        done = {r_.get("photo", "") for r_ in rows}
        state["photos"] = list_photos(state["folder"], done)
        state["i"] = 0
        skipped = len([p for p in state["folder"].iterdir() if p.suffix.lower() in PHOTO_EXT]) - len(state["photos"])
        log(f"Folder: {path}  ({len(state['photos'])} photos to do, {skipped} already recorded)")
        root.after(50, show_photo)

    def save(event=None):
        row, err = validate(players, date_var.get(), [v.get() for v in name_vars])
        if row is None:
            error.configure(text=err)
            return "break"
        if state["folder"] is not None and state["i"] < len(state["photos"]):
            row["photo"] = state["photos"][state["i"]].name
            state["i"] += 1
        rows.append(row)
        write_rows(rows)
        saved.configure(text=f"{len(rows)} matches in matches.csv")
        log(f"#{len(rows)}  {describe(row)}")
        clear_form()
        show_photo()
        return "break"

    def skip():
        if state["folder"] is not None and state["i"] < len(state["photos"]):
            log(f"skipped {state['photos'][state['i']].name}")
            state["i"] += 1
            clear_form()
            show_photo()

    def undo():
        if not rows:
            error.configure(text="Nothing to undo")
            return
        gone = rows.pop()
        write_rows(rows)
        saved.configure(text=f"{len(rows)} matches in matches.csv")
        log(f"removed  {describe(gone)}")
        if gone.get("photo") and state["folder"] is not None:
            # put that photo back in front so it can be redone
            path = state["folder"] / gone["photo"]
            if path.exists() and path not in state["photos"]:
                state["photos"].insert(state["i"], path)
            elif path in state["photos"]:
                state["i"] = state["photos"].index(path)
        clear_form()
        show_photo()

    def open_external():
        if state["folder"] is not None and state["i"] < len(state["photos"]):
            os.startfile(str(state["photos"][state["i"]]))

    ttk.Button(btns, text="Save & next  (Enter)", command=save).pack(side="left")
    ttk.Button(btns, text="Skip photo", command=skip).pack(side="left", padx=4)
    ttk.Button(btns, text="Undo last", command=undo).pack(side="left")
    tools = ttk.Frame(right)
    tools.grid(row=r + 1, column=0, columnspan=2, sticky="we", pady=(10, 0))
    def add_player():
        from tkinter import simpledialog
        name = simpledialog.askstring("Add player", "New player's name (as it should appear on the site):", parent=root)
        if name is None:
            return
        name = name.strip()
        if not name:
            return
        if "," in name or '"' in name:
            messagebox.showerror("Add player", "Names cannot contain commas or quotes.", parent=root)
            return
        clash = [p for p in players if p.lower() == name.lower()]
        if clash:
            messagebox.showinfo("Add player", f"{clash[0]} is already in the list.", parent=root)
            return
        players.append(name)
        with PLAYERS_FILE.open("a", encoding="utf-8", newline="") as f:
            f.write(name + "\n")
        for b in name_boxes:
            b["values"] = players
        log(f"added player {name} to players.csv ({len(players)} players)")

    ttk.Button(tools, text="Choose photo folder", command=choose_folder).pack(side="left")
    ttk.Button(tools, text="Open photo full size", command=open_external).pack(side="left", padx=4)
    ttk.Button(tools, text="Add player", command=add_player).pack(side="left")

    for w in (date_entry, *name_boxes):
        w.bind("<Return>", save)
    photo_label.bind("<Configure>", lambda e: root.after_idle(show_photo) if state["folder"] else None)

    if photos_dir:
        choose_folder(photos_dir)
    clear_form()

    if smoke:  # used by the test suite: fill the form, save once, close
        date_var.set("2026-09-01")
        for v, n in zip(name_vars, ("ace", "nok", "tom", "pim")):
            v.set(n)
        def grab():
            try:
                from PIL import ImageGrab
                root.update_idletasks()
                x, y = root.winfo_rootx(), root.winfo_rooty()
                ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(
                    os.environ.get("SMOKE_PNG", "gui_smoke.png"))
            except Exception as e:
                print("no screenshot:", e)
        root.after(400, save)
        root.after(900, grab)
        root.after(1200, root.destroy)
    root.mainloop()
    return 0


# ============================================================== CLI
class Quit(Exception):
    pass


def run_cli(photos_dir: str | None) -> int:
    players = load_players()
    rows = read_rows()
    print(f"{len(players)} players, {len(rows)} matches already in {MATCHES_FILE.name}")
    print("q = quit, u = undo last saved match, s = skip photo. A few letters of a name is enough.\n")

    def ask(prompt: str, default: str = "") -> str:
        try:
            raw = input(f"{prompt} [{default}]: " if default else f"{prompt}: ").strip()
        except EOFError:
            raise Quit
        if raw.lower() == "q":
            raise Quit
        return raw or default

    queue: list[tuple[str, str, Path | None]]
    if photos_dir:
        folder = Path(photos_dir)
        todo = list_photos(folder, {r.get("photo", "") for r in rows})
        print(f"{len(todo)} photos to do\n")
        queue = [(p.name, photo_date(p), p) for p in todo]
    else:
        queue = [("", "", None)] * 100000

    last_date = rows[-1]["date"] if rows else dt.date.today().isoformat()
    i = 0
    try:
        while i < len(queue):
            name, pdate, path = queue[i]
            if path is not None:
                print(f"--- photo {i + 1}/{len(queue)}: {name}")
                try:
                    os.startfile(str(path))
                except Exception:
                    pass
            while True:
                date = ask("date", pdate or last_date)
                if date.lower() == "s" and path is not None:
                    break
                if date.lower() == "u":
                    if rows:
                        gone = rows.pop()
                        write_rows(rows)
                        print(f"  removed {describe(gone)}")
                    continue
                w = ask("winners (two names)")
                l = ask("losers (two names)")
                names = (w.split() + ["", ""])[:2] + (l.split() + ["", ""])[:2]
                row, err = validate(players, date, names)
                if row is None:
                    print(f"  {err}")
                    continue
                row["photo"] = name
                rows.append(row)
                write_rows(rows)
                last_date = row["date"]
                print(f"  saved #{len(rows)}: {describe(row)}\n")
                break
            i += 1
    except Quit:
        pass
    print(f"\n{len(rows)} matches in {MATCHES_FILE}. Build the site with: python build.py --check")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--photos", help="folder of match photos to walk through")
    ap.add_argument("--cli", action="store_true", help="terminal mode instead of the window")
    ap.add_argument("--smoke", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.cli:
        return run_cli(args.photos)
    return run_gui(args.photos, smoke=args.smoke)


if __name__ == "__main__":
    sys.exit(main())
