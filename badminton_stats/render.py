"""Inline the site sources and the JSON payload into a single self-contained index.html."""
from __future__ import annotations

import json
import os
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent.parent / "site"


def render(payload: dict, out_path: str | Path, site_dir: Path = SITE_DIR) -> Path:
    template = (site_dir / "template.html").read_text(encoding="utf-8")
    css = (site_dir / "style.css").read_text(encoding="utf-8")
    js = "\n".join((site_dir / f).read_text(encoding="utf-8") for f in ("i18n.js", "app.js"))
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # A literal "</script>" inside the JSON would end the data block early.
    data = data.replace("</", "<\\/")

    html = (template
            .replace("{{CSS}}", css)
            .replace("{{JS}}", js)
            .replace("{{DATA}}", data))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(html, encoding="utf-8")
    os.replace(tmp, out_path)
    return out_path
