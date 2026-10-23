"""autozone-r0 round 2 probes -> work/probe2_points.json

(a) metre-scale straddles of TIGER-derived boundaries on LAND (+-0.3, 1, 3 m)
    for both SPCS 83 (C/S line) and SPCS2022 (LDP internal lines);
(b) Great Lakes water points where 'zone of the county whose water it is'
    and 'zone of the nearest land' DISAGREE -- discriminates NCAT's rule;
(c) a transect Keweenaw Point -> Isle Royale (where does U41H become U61K?).
Run:  <venv>/python -I probe2_points.py
"""
from __future__ import annotations

import json
import os
import random
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings("ignore", category=DeprecationWarning)

from shapely.geometry import Point
from shapely.ops import unary_union, linemerge, nearest_points

import load_sources as L
from probe_points import straddle, longest

WORK = os.path.join(L.HERE, "work")


def main():
    tig, _ = L.counties_tiger()
    zt, _, _ = L.zones_from_counties(tig)
    ldp = {c: g for c, (_, g) in L.ngs_ldp().items()}
    lu = unary_union(list(ldp.values()))
    c2l = json.load(open(os.path.join(WORK, "ldp_detail.json"),
                         encoding="utf-8"))["county_to_ldp"]
    p83, p22 = [], []
    cs = zt["2112"].boundary.intersection(zt["2113"].boundary.buffer(0.5))
    cs_land = cs.intersection(lu.buffer(-50))  # well inland
    for i, ln in enumerate(longest(cs_land)[:3]):
        p83 += straddle(ln, [0.3, 0.7], [0.3, 1, 3], "T83CS%d" % i)
    internal = unary_union([g.boundary for g in ldp.values()]).difference(
        lu.boundary.buffer(50.0))
    for i, ln in enumerate(longest(internal)[10:16]):
        p22 += straddle(ln, [0.5], [0.3, 1, 3], "T22L%d" % (i + 10))

    # (b) water points
    water = unary_union(list(tig.values())).difference(lu.buffer(200))
    minx, miny, maxx, maxy = water.bounds
    rnd = random.Random(20261022)
    cand = []
    tries = 0
    while len(cand) < 14 and tries < 200000:
        tries += 1
        x, y = rnd.uniform(minx, maxx), rnd.uniform(miny, maxy)
        p = Point(x, y)
        if not water.contains(p):
            continue
        cn = [n for n, g in tig.items() if g.contains(p)]
        if len(cn) != 1:
            continue
        zc = c2l[cn[0]]
        dists = sorted((g.distance(p), c) for c, g in ldp.items())
        zn = dists[0][1]
        if zn != zc and dists[1][0] - dists[0][0] > 2000:
            lon, lat = L.M_TO_LL.transform(x, y)
            cand.append(dict(tag="WATER county=%s(%s) nearest=%s %.0fm" % (
                cn[0], zc, zn, dists[0][0]), lat=round(lat, 6),
                lon=round(lon, 6)))
    p22 += cand
    # (c) transect
    a = (47.47, -87.85)
    b = (48.00, -88.70)
    for k in range(13):
        t = k / 12.0
        p22.append(dict(tag="KEWEENAW_TRANSECT t=%.3f" % t,
                        lat=round(a[0] + t * (b[0] - a[0]), 6),
                        lon=round(a[1] + t * (b[1] - a[1]), 6)))
    with open(os.path.join(WORK, "probe2_points.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(dict(spcs83=p83, spcs2022=p22), fh, indent=1)
    print(len(p83), len(p22), "water candidates", len(cand), "tries", tries)


if __name__ == "__main__":
    main()
