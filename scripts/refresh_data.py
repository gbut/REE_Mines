#!/usr/bin/env python3
"""Refresh the saved data copies and record what changed in the Stimson sheet.

Run by .github/workflows/refresh-data.yml every week (and on demand). It:
  1. fetches the Stimson sheet, the Myanmar Witness ArcGIS layer and the BVC Archive sheet;
  2. rewrites src/data/sites_snapshot.json, src/data/archive_snapshot.json and src/data/snapshot.json;
  3. compares the new Stimson rows with the previous saved copy and appends any differences to changes.json;
  4. leaves build.py to the workflow, which rebuilds index.html.

Stimson site IDs are the sheet row number: S0634 is row 634 of the sheet (the header is row 1).
They stay put when a row is edited or re-tagged, and only move if Stimson deletes or inserts rows above.

Usage:
  python3 scripts/refresh_data.py                  # live fetch
  python3 scripts/refresh_data.py --from DIR       # read stimson.csv, mw.json, bvc.csv from DIR (testing)
  python3 scripts/refresh_data.py --date 2026-12-01
"""
import csv, datetime, io, json, math, pathlib, re, sys, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"

STIMSON_SHEET, STIMSON_GID = "1bfGeMKv3piuMtmnJJq_XW3cBwVwtYISSjX1o4jqRLZE", "1355866538"
BVC_SHEET, BVC_GID = "1QNfqAaXdOlTA9PiWYg-fo8wqJ8dhZYWQytxXUMHMNPg", "0"
MW_URL = ("https://services-eu1.arcgis.com/06WOSMGHsCnaFyMp/arcgis/rest/services/rare_earth_arcgis_data_view/"
          "FeatureServer/0/query?where=1%3D1&outFields=*&outSR=4326&resultRecordCount=5000&f=json")
STIMSON_EXPORT = f"https://docs.google.com/spreadsheets/d/{STIMSON_SHEET}/export?format=csv&gid={STIMSON_GID}"
STIMSON_GVIZ = (f"https://docs.google.com/spreadsheets/d/{STIMSON_SHEET}/gviz/tq?tqx=out:csv&headers=1&gid={STIMSON_GID}&tq="
                + urllib.parse.quote("select *"))
BVC_EXPORT = f"https://docs.google.com/spreadsheets/d/{BVC_SHEET}/export?format=csv&gid={BVC_GID}&range=A1:F5000"

SOURCES = ["Shan Human Rights Foundation/Stimson Center/Planet Labs", "Myanmar Witness/Stimson Center/Planet Labs",
           "Stimson Center/Planet Labs", "USGS/Stimson Center/Planet Labs", "(not given)"]
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "REE_Mines data refresh (github.com/gbut/REE_Mines)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8-sig")


def norm_date(v):
    """Dates as typed in the sheets -> YYYY-MM-DD, YYYY-MM or YYYY where possible."""
    v = (v or "").strip()
    if not v:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", v):
        return v[:10]
    if re.match(r"^\d{4}(-\d{2})?$", v):
        return v
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
    if m:
        return f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}"
    m = re.match(r"^(\d{1,2}) ([A-Za-z]{3})[a-z]* (\d{4})$", v)
    if m and m[2].lower() in MONTHS:
        return f"{m[3]}-{MONTHS[m[2].lower()]:02d}-{int(m[1]):02d}"
    return v


# ---------- geometry (same formulas as the page) ----------
def rings_of(mm):
    polys = [mm["coordinates"]] if mm["type"] == "Polygon" else mm["coordinates"]
    return polys, [r for p in polys for r in p]


def _in_ring(r, lo, la):
    c = False
    j = len(r) - 1
    for i in range(len(r)):
        xi, yi = r[i]; xj, yj = r[j]
        if (yi > la) != (yj > la) and lo < (xj - xi) * (la - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def js_round(x):
    return math.floor(x + 0.5)  # JavaScript Math.round, so saved and live values agree


def km_outside(polys, rings, la, lo):
    for poly in polys:
        if _in_ring(poly[0], lo, la) and not any(_in_ring(h, lo, la) for h in poly[1:]):
            return 0
    kx, ky = 111.32 * math.cos(la * math.pi / 180), 110.57
    best = 1e9
    for r in rings:
        for i in range(1, len(r)):
            ax, ay = (r[i - 1][0] - lo) * kx, (r[i - 1][1] - la) * ky
            bx, by = (r[i][0] - lo) * kx, (r[i][1] - la) * ky
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = max(0, min(1, -(ax * dx + ay * dy) / L2 if L2 else 0))
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    v = js_round(best * 10) / 10
    return int(v) if v == int(v) else v


def hav(a, b, c, d):
    r = math.pi / 180
    x = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return int(js_round(2 * 6371e3 * math.asin(math.sqrt(x))))


def nearest(p, others):
    best = (None, 10 ** 12)
    for q in others:
        d = hav(p["la"], p["lo"], q["la"], q["lo"])
        if d < best[1]:
            best = (q["id"], d)
    return best


# ---------- sources ----------
def parse_stimson(text, from_gviz=False):
    rows = list(csv.reader(io.StringIO(text)))
    head = [h.strip().lower() for h in rows[0]]
    col = lambda name: next((i for i, h in enumerate(head) if h.startswith(name)), None)
    ix = {k: col(k) for k in ["method", "metal", "year", "country", "province", "basin", "sub-basin", "latitude", "longitude", "source", "last updated"]}
    ix["basin"] = next((i for i, h in enumerate(head) if h == "basin"), ix["basin"])
    missing = [k for k in ["metal", "country", "latitude", "longitude"] if ix[k] is None]
    if missing:
        raise SystemExit(f"Stimson sheet: missing columns {missing}; header was {rows[0]}")
    g = lambda r, k: (r[ix[k]].strip() if ix[k] is not None and ix[k] < len(r) else "")
    total, out = 0, []
    for n, r in enumerate(rows[1:], start=2):  # n = sheet row number
        if not any(x.strip() for x in r):
            continue
        total += 1
        if g(r, "country") != "Myanmar" or g(r, "metal") != "Rare Earth":
            continue
        try:
            la, lo = float(g(r, "latitude")), float(g(r, "longitude"))
        except ValueError:
            continue
        y = g(r, "year")
        out.append({"id": f"S{n:04d}", "y": round(float(y)) if re.match(r"^\d+(\.\d+)?$", y) else None,
                    "st": g(r, "province"), "ba": g(r, "basin"), "sb": g(r, "sub-basin").replace(" (Myanmar)", "").strip(),
                    "la": round(la, 5), "lo": round(lo, 5), "srcName": g(r, "source") or "(not given)",
                    "lu": norm_date(g(r, "last updated"))})
    if len(out) < 100:
        raise SystemExit(f"Stimson sheet: only {len(out)} Myanmar rare earth rows")
    return out, total


def parse_mw(text):
    d = json.loads(text)
    if not d.get("features"):
        raise SystemExit("Myanmar Witness layer: no features")
    out = []
    for f in d["features"]:
        a = f["attributes"]
        m = re.search(r"located in ([^,]+), ([^,]+?)(?: State)?,", a.get("Description") or "")
        img = re.search(r"items/([0-9a-f]{32})", a.get("Site_Image") or "")
        out.append({"id": a["Site_ID"], "la": round(f["geometry"]["y"], 5), "lo": round(f["geometry"]["x"], 5), "y": a.get("Year"),
                    "pits": a.get("Number_of_Pits") or 0, "tw": m[1] if m else "Unknown", "st": m[2] if m else "Kachin",
                    "img": img[1] if img else ""})
    return out


def parse_bvc(text, prev):
    rows = list(csv.reader(io.StringIO(text)))
    head = [h.strip().lower() for h in rows[0]]
    if not (len(head) >= 6 and head[1] == "title" and head[5] == "link"):
        raise SystemExit(f"BVC Archive: unexpected columns {rows[0]}")
    snap_date = {r[5]: r[0] for r in prev if r[0]}
    sec, kept = None, []
    for r in rows[1:]:
        r = (r + [""] * 6)[:6]
        if r[0].strip() and not any(x.strip() for x in r[1:]):
            sec = r[0].strip()
            continue
        if sec and re.match(r"^articles and reports$", sec, re.I) and r[1].strip() and r[5].strip():
            c = lambda x: re.sub(r"\s+", " ", x).strip()
            link = c(r[5])
            kept.append([norm_date(r[0]) or snap_date.get(link, ""), c(r[1]), c(r[2]), c(r[3]), c(r[4]), link])
    if sec is None or len(kept) < 10:
        raise SystemExit(f"BVC Archive: found {len(kept)} rows (section headers seen: {sec is not None})")
    return sorted(kept, key=lambda r: r[0] or "0", reverse=True)


# ---------- change detection ----------
FIELDS = [("y", "year"), ("st", "state"), ("ba", "basin"), ("sb", "sub-basin"), ("la", "latitude"), ("lo", "longitude"),
          ("srcName", "source"), ("lu", "last updated")]


def diff(old, new, date):
    """Compare two lists of Stimson sites. Rows are matched by ID and position first, then by identical coordinates
    (so a row that only moved because of an inserted or deleted row is reported as renumbered, not as edited)."""
    o_by, n_by = {p["id"]: p for p in old}, {p["id"]: p for p in new}
    out, o_left, n_left = [], set(o_by), set(n_by)
    pos = lambda p: (p["la"], p["lo"])
    # 1. same ID, same coordinates
    for i in list(n_left):
        if i in o_left and pos(o_by[i]) == pos(n_by[i]):
            o_left.discard(i); n_left.discard(i)
            ch = changed(o_by[i], n_by[i])
            if ch:
                out.append({"date": date, "id": i, "kind": "edited", "fields": ch})
    # 2. different ID, same coordinates -> renumbered
    o_pos = {}
    for i in o_left:
        o_pos.setdefault(pos(o_by[i]), []).append(i)
    moved = []
    for i in sorted(n_left):
        cands = o_pos.get(pos(n_by[i]))
        if cands:
            j = cands.pop(0)
            o_left.discard(j); n_left.discard(i)
            moved.append([j, i])
            ch = changed(o_by[j], n_by[i])
            if ch:
                out.append({"date": date, "id": i, "prev_id": j, "kind": "edited", "fields": ch})
    # 3. same ID, coordinates moved -> edited
    for i in sorted(n_left & o_left):
        o_left.discard(i); n_left.discard(i)
        out.append({"date": date, "id": i, "kind": "edited", "fields": changed(o_by[i], n_by[i])})
    # 4. the rest
    out += [{"date": date, "id": i, "kind": "added", "fields": {lab: [None, n_by[i][k]] for k, lab in FIELDS if n_by[i].get(k) not in (None, "")}}
            for i in sorted(n_left)]
    out += [{"date": date, "id": i, "kind": "removed", "fields": {lab: [o_by[i][k], None] for k, lab in FIELDS if o_by[i].get(k) not in (None, "")}}
            for i in sorted(o_left)]
    out.sort(key=lambda e: e["id"])
    if moved:  # one entry for all rows whose ID changed because rows above them were inserted or deleted
        out.append({"date": date, "kind": "renumbered", "ids": moved})
    return out


def changed(a, b):
    return {lab: [a.get(k), b.get(k)] for k, lab in FIELDS if a.get(k) != b.get(k)}


# ---------- snapshot format ----------
def load_prev_stimson(snap):
    """Previous Stimson rows in the same shape parse_stimson returns, or None if the saved copy predates row-number IDs."""
    if snap.get("v", 1) < 2:
        return None
    out = []
    for r in snap["s"]:
        out.append({"id": r[0], "y": r[1], "st": snap["P"][r[2]], "ba": snap["F"][r[3]], "sb": snap["B"][r[4]], "la": r[5], "lo": r[6],
                    "srcName": r[12] or snap["S"][r[7]], "lu": r[11]})
    return out


def idx(lst, v):
    if v not in lst:
        lst.append(v)
    return lst.index(v)


def write_json(path, obj, indent=None):
    text = json.dumps(obj, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"))
    path.write_text(text + "\n", encoding="utf-8")


def main():
    args = sys.argv[1:]
    date = args[args.index("--date") + 1] if "--date" in args else datetime.date.today().isoformat()
    src_dir = pathlib.Path(args[args.index("--from") + 1]) if "--from" in args else None

    prev = json.loads((DATA / "sites_snapshot.json").read_text(encoding="utf-8"))
    prev_arc = json.loads((DATA / "archive_snapshot.json").read_text(encoding="utf-8"))

    if src_dir:
        st_text, mw_text, bvc_text, how = (src_dir / "stimson.csv").read_text(), (src_dir / "mw.json").read_text(), (src_dir / "bvc.csv").read_text(), "file"
    else:
        try:
            st_text, how = get(STIMSON_EXPORT), "export"
        except Exception as e:  # export blocked: gviz "select *" keeps every row in sheet order
            print(f"Stimson CSV export failed ({e}); using gviz select *", file=sys.stderr)
            st_text, how = get(STIMSON_GVIZ), "gviz"
        mw_text, bvc_text = get(MW_URL), get(BVC_EXPORT)

    S, total = parse_stimson(st_text)
    M = parse_mw(mw_text)
    A = parse_bvc(bvc_text, prev_arc)
    if len(M) < 50:
        raise SystemExit(f"Myanmar Witness layer: only {len(M)} sites")

    polys, rings = rings_of(prev["mm"])
    for p in S + M:
        p["nb"] = km_outside(polys, rings, p["la"], p["lo"])
    for p in S:
        p["nn"], p["nd"] = nearest(p, M)
    for p in M:
        p["nn"], p["nd"] = nearest(p, S)

    # change log
    old = load_prev_stimson(prev)
    changes_path = ROOT / "changes.json"
    log = json.loads(changes_path.read_text(encoding="utf-8")) if changes_path.exists() else {"baseline": None, "changes": []}
    if old is None:
        log["baseline"] = date
        print(f"Baseline: {len(S)} Stimson rows saved with row-number IDs; no changes recorded this time.")
    else:
        new_changes = diff(old, S, date)
        log["changes"] = new_changes + [c for c in log["changes"] if c["date"] != date]
        print(f"{len(new_changes)} Stimson changes since the last saved copy.")

    # Lookup lists keep their previous order; values no longer used are dropped and new ones are added at the end.
    keep = lambda lst, used: [v for v in lst if v in used] + sorted(used - set(lst))
    P = keep(prev["P"], {p["st"] for p in S})
    F = keep(prev["F"], {p["ba"] for p in S})
    B = keep(prev["B"], {p["sb"] for p in S})
    T = [list(t) for t in prev["T"] if [t[0], t[1]] in [[p["tw"], p["st"]] for p in M]]
    snap = {
        "v": 2,
        "meta": {"date": date, "stimson_sheet_rows": total, "stimson_read_via": how},
        "P": P, "F": F, "B": B, "S": SOURCES, "T": T, "mm": prev["mm"],
        # [id, year|null, P, F, B, lat, lon, S, km_outside_border, nearest_MW_id, nearest_MW_m, last_updated, source_if_not_in_S]
        "s": [[p["id"], p["y"], idx(P, p["st"]), idx(F, p["ba"]), idx(B, p["sb"]), p["la"], p["lo"],
               SOURCES.index(p["srcName"]) if p["srcName"] in SOURCES else 4, p["nb"], p["nn"], p["nd"], p["lu"],
               "" if p["srcName"] in SOURCES else p["srcName"]] for p in S],
        "m": [[p["id"], p["la"], p["lo"], p["y"], p["pits"], idx_pair(T, [p["tw"], p["st"]]), p["img"], p["nb"], p["nn"], p["nd"]] for p in M],
    }
    write_json(DATA / "sites_snapshot.json", snap)
    write_json(DATA / "archive_snapshot.json", A)
    d = datetime.date.fromisoformat(date)
    write_json(DATA / "snapshot.json", {"date": date, "short": f"{d.day} {d.strftime('%b %Y')}", "long": f"{d.day} {d.strftime('%B %Y')}",
                                        "note": "Date the saved copies in sites_snapshot.json and archive_snapshot.json were taken."}, indent=1)
    write_json(changes_path, log, indent=1)
    print(f"Saved {len(S)} Stimson sites (of {total} sheet rows, via {how}), {len(M)} Myanmar Witness sites, {len(A)} BVC Archive items.")


def idx_pair(T, pair):
    if pair not in T:
        T.append(pair)
    return T.index(pair)


if __name__ == "__main__":
    main()
