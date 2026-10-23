"""Z0: choose and capture the NCAT zone anchors Auto zone is pinned to.

    py -I review/autozone-z0/capture_anchors.py select   # choose the points
    py -I review/autozone-z0/capture_anchors.py query    # ask NCAT, live

``select`` picks, for each of Michigan's 83 counties, the land point deepest
inside it: a 41 x 41 grid over the county's bounding box, kept only where the
point is inside the county (data/mi_counties_tiger2025.json) AND on land (inside
one of NGS's land-only SPCS2022 polygons, review/autozone-r0/raw/ngs_fs/
mi_4269.json), scored by its distance to the nearest edge of the county's own
polygon, best kept. Being deep inside its county puts it far from every zone
line. Written to work/anchor_points.json.

``query`` asks NGS NCAT which zone it picks for each chosen point, plus the
recon's 14 Great Lakes water points and 13 Keweenaw-to-Isle-Royale transect
points for SPCS 83 (the recon asked those for SPCS2022 only):

* SPCS 83: production REST, https://geodesy.noaa.gov/api/ncat/llh, NAD83(2011)
  in and out, no spcZone - NCAT picks the zone (RECON.md section 5.1);
* SPCS2022: the beta web app's JSF form, NATRF2022 epoch 2020.00 in and out,
  zone list left on "Auto Pick (default zone)" (RECON.md section 5.1; the form
  code is review/autozone-r0/probe_ncat.py's, reused unchanged).

Every response is saved raw under raw/ with its SHA-256 in
work/anchor_ncat.json. Stdlib only, plus the repository's own michspc package
(for the point-in-polygon of the selection step; NCAT decides the answers).
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "review" / "autozone-r0"))

from michspc.spc.autozone import County, PreparedCounty  # noqa: E402

RAW = HERE / "raw"
WORK = HERE / "work"
R0 = REPO / "review" / "autozone-r0"


def local_metres(lat0: float):
    """Metres per degree of latitude and of longitude at lat0 (GRS 80)."""
    a, f = 6378137.0, 1 / 298.257222101
    e2 = f * (2 - f)
    s = math.sin(math.radians(lat0))
    w = math.sqrt(1 - e2 * s * s)
    m = a * (1 - e2) / w**3  # meridian radius
    n = a / w  # prime vertical radius
    return math.radians(1) * m, math.radians(1) * n * math.cos(math.radians(lat0))


def seg_distance(px, py, ax, ay, bx, by, my, mx):
    ax, ay, bx, by = (ax - px) * mx, (ay - py) * my, (bx - px) * mx, (by - py) * my
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
    return math.hypot(ax + t * dx, ay + t * dy)


def load_counties():
    doc = json.loads((REPO / "data" / "mi_counties_tiger2025.json").read_text(encoding="utf-8"))
    return [
        County(c["fips"], c["name"], tuple(tuple((x, y) for x, y in r) for r in c["rings"]))
        for c in doc["counties"]
    ]


def load_ngs_land():
    doc = json.loads((R0 / "raw" / "ngs_fs" / "mi_4269.json").read_text(encoding="utf-8"))
    return [
        PreparedCounty.build(
            County(
                f["attributes"]["ZoneCode"],
                f["attributes"]["AbrvFull"],
                tuple(tuple((x, y) for x, y in r) for r in f["geometry"]["rings"]),
            )
        )
        for f in doc["features"]
    ]


def select():
    counties = load_counties()
    land = load_ngs_land()
    out = []
    for c in counties:
        pc = PreparedCounty.build(c)
        ring_edges = [e for r in c.rings for e in zip(r[:-1], r[1:])]
        best = None
        n = 41
        for i in range(1, n):
            for j in range(1, n):
                x = pc.min_longitude + (pc.max_longitude - pc.min_longitude) * i / n
                y = pc.min_latitude + (pc.max_latitude - pc.min_latitude) * j / n
                if not pc.contains(x, y):
                    continue
                if not any(z.contains(x, y) for z in land):
                    continue
                my, mx = local_metres(y)
                d = min(seg_distance(x, y, a[0], a[1], b[0], b[1], my, mx) for a, b in ring_edges)
                if best is None or d > best[0]:
                    best = (d, round(y, 6), round(x, 6))
        if best is None:
            raise SystemExit(f"no land grid point inside {c.name}")
        out.append({"tag": f"COUNTY {c.fips} {c.name}", "fips": c.fips, "lat": best[1],
                    "lon": best[2], "depth_m": round(best[0], 1)})
        print(c.fips, c.name, best)
    WORK.mkdir(exist_ok=True)
    (WORK / "anchor_points.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")


def recon_extra_points():
    """The recon's water and Keweenaw transect points, asked for SPCS2022 only."""
    rows = json.loads((R0 / "work" / "r2_ncat_22.json").read_text(encoding="utf-8"))
    return [
        {"tag": r["tag"], "lat": r["lat"], "lon": r["lon"]}
        for r in rows
        if r["tag"].split()[0] in ("WATER", "KEWEENAW_TRANSECT")
    ]


def query():
    import probe_ncat  # review/autozone-r0/probe_ncat.py: fetch, form code

    probe_ncat.RAW = str(RAW)
    RAW.mkdir(exist_ok=True)
    points = json.loads((WORK / "anchor_points.json").read_text(encoding="utf-8"))
    # Isle Royale's land, the one county-part the deepest-point rule cannot
    # reach (Keweenaw's deepest land point is on the mainland). Inland on the
    # island, about 10 km from 47.65 N; checked as land in the suite.
    points.append({"tag": "ISLE_ROYALE_LAND", "fips": "26083", "lat": 48.0, "lon": -88.8})
    extra = recon_extra_points()

    results = {"spcs83": [], "spcs2022": []}
    for i, pt in enumerate(points + extra):
        q = urllib.parse.urlencode({"lat": "%.8f" % pt["lat"], "lon": "%.8f" % pt["lon"],
                                    "inDatum": "NAD83(2011)", "outDatum": "NAD83(2011)"})
        body = probe_ncat.fetch(probe_ncat.PROD + "?" + q)
        name = "z0_spcs83_%03d.json" % i
        (RAW / name).write_bytes(body)
        zone = json.loads(body).get("spcZone")
        results["spcs83"].append(dict(pt, ncat_zone=zone, raw=name,
                                      sha256=hashlib.sha256(body).hexdigest()))
        print("83", i, pt["tag"], zone)
        time.sleep(0.4)

    probe_ncat.PREFIX = "z0_"
    res22 = probe_ncat.run22(points)
    results["spcs2022"] = res22
    (WORK / "anchor_ncat.json").write_text(json.dumps(results, indent=1) + "\n",
                                           encoding="utf-8", newline="\n")


if __name__ == "__main__":
    {"select": select, "query": query}[sys.argv[1]]()
