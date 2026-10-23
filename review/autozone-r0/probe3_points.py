"""autozone-r0 round 3 probes -> work/probe3_points.json

(a) SPCS 83: fine scan across the TIGER Central/South LAND line at 8 places,
    -20..+20 m, to measure where NCAT's own boundary sits.
(b) SPCS2022 datum test: straddles of the Jackson/Ingham (L11A/L45G) line at
    +-0.3, 0.7, 1.5 m, to be submitted as NAD83(2011) input with NATRF2022
    output -- does NCAT pick the zone from the input or the output position?
Run:  <venv>/python -I probe3_points.py
"""
from __future__ import annotations

import json
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings("ignore", category=DeprecationWarning)

from shapely.ops import unary_union

import load_sources as L
from probe_points import longest

WORK = os.path.join(L.HERE, "work")


def straddle_signed(line, fractions, dists, tag):
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
            lon, lat = L.M_TO_LL.transform(p.x + d * nx, p.y + d * ny)
            out.append(dict(tag="%s f=%.3f d=%+.1f" % (tag, f, d),
                            lat=round(lat, 9), lon=round(lon, 9)))
    return out


def main():
    tig, _ = L.counties_tiger()
    zt, _, _ = L.zones_from_counties(tig)
    cs = zt["2112"].boundary.intersection(zt["2113"].boundary.buffer(0.5))
    land = unary_union([g for _, g in L.ngs_ldp().values()]).buffer(-100)
    cs_land = cs.intersection(land)
    parts = longest(cs_land)
    dists = [-20, -10, -5, -3, -2, -1, -0.3, 0.3, 1, 2, 3, 5, 10, 20]
    p83 = []
    for i, ln in enumerate(parts[:4]):
        p83 += straddle_signed(ln, [0.06, 0.19, 0.31, 0.44, 0.56, 0.69, 0.81, 0.94], dists, "F83CS%d" % i)
    jk = tig["Jackson"].boundary.intersection(tig["Ingham"].boundary.buffer(0.5))
    jl = longest(jk)[0]
    p22 = straddle_signed(jl, [0.5], [-1.5, -0.7, -0.3, 0.3, 0.7, 1.5],
                          "DATUM JacksonIngham")
    with open(os.path.join(WORK, "probe3_points.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(dict(spcs83=p83, spcs2022_datum=p22), fh, indent=1)
    print(len(p83), len(p22), [round(x.length) for x in parts[:4]])


if __name__ == "__main__":
    main()
