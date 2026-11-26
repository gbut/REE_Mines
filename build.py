#!/usr/bin/env python3
"""Build index.html from src/template.html and the saved data copies.

Usage:  python3 build.py           # writes index.html
        python3 build.py --check   # exits 1 if index.html is out of date

Inputs (all relative to the repository root):
  src/template.html               page markup, styles and script, with placeholders
  src/data/sites_snapshot.json    saved copy of the Stimson + Myanmar Witness sites and the Myanmar outline
  src/data/admin1.json            Kachin, Shan, Yunnan and Tibet boundaries (Natural Earth 10m admin-1)
  src/data/archive_snapshot.json  saved copy of the BVC Archive (Articles and Reports section)
  src/data/snapshot.json          the date the saved copies were taken
  reports.json                    the Reports list (also fetched live by the page)

The saved copies are only fallbacks: the page loads every source live when it opens.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"

def read(p): return (ROOT / p).read_text(encoding="utf-8")

def embed(text):
    # Validate the JSON, then make it safe to place inside a <script> element.
    json.loads(text)
    return text.strip().replace("</", "<\\/")

def build():
    t = read("src/template.html")
    snap = json.loads(read("src/data/snapshot.json"))
    parts = {
        "/*DATA*/null": embed(read("src/data/sites_snapshot.json")),
        "/*ADMIN*/null": embed(read("src/data/admin1.json")),
        "/*ARCHIVE*/null": embed(read("src/data/archive_snapshot.json")),
        "/*REPORTS*/null": embed(read("reports.json")),
        "{{SNAPSHOT_DATE}}": snap["short"],
        "{{SNAPSHOT_DATE_LONG}}": snap["long"],
    }
    for k, v in parts.items():
        if t.count(k) != 1:
            sys.exit(f"build.py: expected exactly one {k!r} in src/template.html, found {t.count(k)}")
        t = t.replace(k, v)
    return t

if __name__ == "__main__":
    out = build()
    target = ROOT / "index.html"
    if "--check" in sys.argv:
        same = target.exists() and target.read_text(encoding="utf-8") == out
        print("index.html is up to date" if same else "index.html is OUT OF DATE: run python3 build.py")
        sys.exit(0 if same else 1)
    target.write_text(out, encoding="utf-8")
    print(f"wrote index.html ({len(out):,} bytes)")
