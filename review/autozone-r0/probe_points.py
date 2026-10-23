"""autozone-r0: generate probe points near zone boundaries -> work/probe_points.json

For SPCS 83: points straddling the MGF-derived Central/South (land) and
North/Central (water) lines at +-15, 50, 200 m along the line normal.
For SPCS2022: points straddling NGS's LDP internal boundaries at +-15, 50, 500 m.
Plus fixed water / out-of-state points.
Run:  <venv>/python -I probe_points.py
"""
from __future__ import annotations

import json
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings("ignore", category=DeprecationWarning)

from shapely.geometry import Point
from shapely.ops import unary_union, linemerge

import load_sources as L

WORK = os.path.join(L.HERE, "work")
os.makedirs(WORK, exist_ok=True)


def straddle(line, fractions, dists, tag):
    out = []
    for f in fractions:
        s = f * line.length
        p = line.interpolate(s)
        q = line.interpolate(min(line.length, s + 5.0))
        r = line.interpolate(max(0.0, s - 5.0))
        dx, dy = q.x - r.x, q.y - r.y
        n = (dx * dx + dy * dy) ** 0.5
        nx, ny = -dy / n, dx / n
        for d in dists:
            for sgn in (-1, 1):
                x, y = p.x + sgn * d * nx, p.y + sgn * d * ny
                lon, lat = L.M_TO_LL.transform(x, y)
                out.append(dict(tag="%s f=%.3f d=%+d" % (tag, f, sgn * d),
                                lat=round(lat, 8), lon=round(lon, 8)))
    return out


def longest(g):
    g = linemerge(g) if g.geom_type == "MultiLineString" else g
    parts = sorted(getattr(g, "geoms", [g]), key=lambda x: -x.length)
    return parts


def main():
    mgf, _ = L.counties_mgf()
    zm, _, _ = L.zones_from_counties(mgf)
    pts = []
    cs = zm["2112"].boundary.intersection(zm["2113"].boundary.buffer(0.5))
    nc = zm["2111"].boundary.intersection(zm["2112"].boundary.buffer(0.5))
    for i, ln in enumerate(longest(cs)[:2]):
        pts += straddle(ln, [0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95],
                        [15, 50, 200], "83CS%d" % i)
    for i, ln in enumerate(longest(nc)[:1]):
        pts += straddle(ln, [0.1, 0.3, 0.5, 0.7, 0.9], [15, 50, 200],
                        "83NC%d" % i)
    fixed = [
        ("lake_michigan_mi_side_near_state_line", 43.50, -87.10),
        ("lake_michigan_mid", 44.00, -86.90),
        ("lake_michigan_wi_side", 43.50, -87.60),
        ("saginaw_bay", 43.90, -83.60),
        ("lake_huron_mi_waters", 44.50, -82.70),
        ("lake_huron_ontario_waters", 44.50, -82.20),
        ("lake_superior_mi_waters", 47.30, -87.00),
        ("lake_superior_far_north", 47.95, -88.40),
        ("lake_erie_mi_waters", 41.80, -83.30),
        ("detroit_river", 42.30, -83.08),
        ("straits_mackinac", 45.82, -84.73),
        ("toledo_oh", 41.65, -83.55),
        ("indiana_south_bend", 41.60, -86.30),
        ("wisconsin_marinette", 45.05, -87.70),
        ("windsor_on", 42.28, -83.00),
        ("lansing", 42.73, -84.55),
    ]
    pts += [dict(tag=t, lat=a, lon=b) for t, a, b in fixed]

    ldp = L.ngs_ldp()
    lz = {c: g for c, (_, g) in ldp.items()}
    lu = unary_union(list(lz.values()))
    internal = unary_union([g.boundary for g in lz.values()]).difference(
        lu.boundary.buffer(1.0))
    p22 = []
    parts = longest(internal)
    for i, ln in enumerate(parts[:10]):
        p22 += straddle(ln, [0.5], [15, 50, 500], "22L%d" % i)
    p22 += [dict(tag=t, lat=a, lon=b) for t, a, b in fixed]
    with open(os.path.join(WORK, "probe_points.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(dict(spcs83=pts, spcs2022=p22), fh, indent=1)
    print(len(pts), "SPCS83 probes,", len(p22), "SPCS2022 probes")


if __name__ == "__main__":
    main()
