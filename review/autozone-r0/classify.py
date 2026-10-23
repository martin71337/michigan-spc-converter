"""autozone-r0: compare NCAT's zone picks with point-in-polygon on each source.

Reads work/ncat_83.json and work/ncat_22.json, writes work/classify.json.
Run:  <venv>/python -I classify.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings("ignore", category=DeprecationWarning)

from shapely.geometry import Point
from shapely.ops import unary_union

import load_sources as L

WORK = os.path.join(L.HERE, "work")
NCAT83 = {"MI N-2111": "2111", "MI C-2112": "2112", "MI S-2113": "2113"}


def pip(zones, x, y):
    p = Point(x, y)
    hit = [c for c, g in zones.items() if g.covers(p)]
    if not hit:
        return None
    return hit[0] if len(hit) == 1 else "+".join(sorted(hit))


def county_of(cs, x, y):
    p = Point(x, y)
    return [n for n, g in cs.items() if g.covers(p)]


def main():
    mgf, _ = L.counties_mgf()
    tig, _ = L.counties_tiger()
    zm, _, _ = L.zones_from_counties(mgf)
    zt, _, _ = L.zones_from_counties(tig)
    esri = L.esri_spcs83()
    ldp = {c: g for c, (_, g) in L.ngs_ldp().items()}
    # LDP per county from the land-clipped NGS layer (work/ldp_detail.json)
    c2l = json.load(open(os.path.join(WORK, "ldp_detail.json"),
                         encoding="utf-8"))["county_to_ldp"]
    out = {"spcs83": [], "spcs2022": []}
    for r in json.load(open(os.path.join(WORK, "ncat_83.json"), encoding="utf-8")):
        x, y = L.LL_TO_M.transform(r["lon"], r["lat"])
        row = dict(tag=r["tag"], lat=r["lat"], lon=r["lon"],
                   ncat=NCAT83.get(r["ncat_zone"], r["ncat_zone"]),
                   mgf=pip(zm, x, y), tiger=pip(zt, x, y), esri=pip(esri, x, y),
                   county_tiger=county_of(tig, x, y))
        row["ncat_eq_tiger"] = row["ncat"] == row["tiger"] or (
            row["tiger"] is None and row["ncat"] not in NCAT83.values())
        row["ncat_eq_mgf"] = row["ncat"] == row["mgf"] or (
            row["mgf"] is None and row["ncat"] not in NCAT83.values())
        out["spcs83"].append(row)
    for r in json.load(open(os.path.join(WORK, "ncat_22.json"), encoding="utf-8")):
        x, y = L.LL_TO_M.transform(r["lon"], r["lat"])
        m = re.search(r"-(26\d{4})", r["ncat_zone"] or "")
        cn = county_of(tig, x, y)
        row = dict(tag=r["tag"], lat=r["lat"], lon=r["lon"],
                   ncat=m.group(1) if m else r["ncat_zone"],
                   ngs_polygon=pip(ldp, x, y), county_tiger=cn,
                   via_county=c2l.get(cn[0]) if len(cn) == 1 else None)
        out["spcs2022"].append(row)
    with open(os.path.join(WORK, "classify.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(out, fh, indent=1)
    print("SPCS83: n=%d" % len(out["spcs83"]))
    for r in out["spcs83"]:
        flag = "" if (r["ncat_eq_tiger"] and r["ncat_eq_mgf"]) else "  <-- DIFF"
        print("%-40s ncat=%-10s mgf=%-6s tiger=%-6s esri=%-6s %s%s" % (
            r["tag"], r["ncat"], r["mgf"], r["tiger"], r["esri"],
            r["county_tiger"], flag))
    print("\nSPCS2022: n=%d" % len(out["spcs2022"]))
    for r in out["spcs2022"]:
        flag = "" if r["ncat"] == r["ngs_polygon"] else "  <-- polygon differs"
        flag2 = "" if r["ncat"] == r["via_county"] else "  <-- county rule differs"
        print("%-40s ncat=%-8s poly=%-8s county=%s->%s%s%s" % (
            r["tag"], r["ncat"], r["ngs_polygon"], r["county_tiger"],
            r["via_county"], flag, flag2))


if __name__ == "__main__":
    main()
