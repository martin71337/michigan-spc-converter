"""autozone-r0: LDP polygons -- holes, land clipping, county membership.

Run:  <venv>/python -I ldp_detail.py
"""
from __future__ import annotations

import json
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings("ignore", category=DeprecationWarning)

import shapely
from shapely.ops import unary_union

import load_sources as L


def ll(x, y):
    lon, lat = L.M_TO_LL.transform(x, y)
    return round(lat, 5), round(lon, 5)


def main():
    out = {}
    ldp = L.ngs_ldp()
    lz = {c: g for c, (_, g) in ldp.items()}
    lu = unary_union(list(lz.values()))
    tig, tattr = L.counties_tiger()
    # holes in the union (interior rings), largest first
    holes = []
    for g in getattr(lu, "geoms", [lu]):
        for r in g.interiors:
            p = shapely.Polygon(r)
            c = p.representative_point()
            holes.append((round(p.area / 1e6, 3), ll(c.x, c.y)))
    holes.sort(reverse=True)
    out["union_hole_count"] = len(holes)
    out["union_holes_top15_km2_latlon"] = holes[:15]
    # do individual zones have holes?
    out["zone_hole_counts"] = {c: sum(len(p.interiors) for p in
                                      getattr(g, "geoms", [g]))
                               for c, g in lz.items()}
    out["zone_part_counts"] = {c: len(getattr(g, "geoms", [g]))
                               for c, g in lz.items()}
    # membership on the land-clipped county: fraction of (county ∩ union)
    memb = {}
    for n, cg in sorted(tig.items()):
        land = cg.intersection(lu)
        if land.area == 0:
            memb[n] = "no land in LDP union"
            continue
        fr = {c: round(g.intersection(cg).area / land.area, 6)
              for c, g in lz.items() if g.intersection(cg).area > 0}
        memb[n] = fr
    split = {n: v for n, v in memb.items()
             if isinstance(v, dict) and (len(v) > 1 or
                                         max(v.values()) < 0.99999)}
    out["counties_split_across_ldp_after_land_clip"] = split
    out["county_to_ldp"] = {n: (max(v, key=v.get) if isinstance(v, dict)
                                else v) for n, v in memb.items()}
    # LDP union vs TIGER 'land' notion: ALAND+inland water?
    out["ldp_union_km2"] = round(lu.area / 1e6, 1)
    out["tiger_ALAND_km2"] = round(sum(r["ALAND"] for r in tattr.values()) / 1e6, 1)
    with open(os.path.join(L.HERE, "work", "ldp_detail.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "county_to_ldp"},
                     indent=1))
    by = {}
    for n, c in out["county_to_ldp"].items():
        by.setdefault(c, []).append(n)
    for c in sorted(by):
        print(c, ldp[c][0] if c in ldp else "", sorted(by[c]))


if __name__ == "__main__":
    main()
