"""autozone-r0 round 3: NCAT fine scans, datum test, Keweenaw water split.

Stdlib only.  Run:  py -I probe3_ncat.py
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops it
import probe_ncat as P

WORK = P.WORK


def zone22(r):
    m = re.search(r"-(\d{6})", r["ncat_zone"] or "")
    return m.group(1) if m else r["ncat_zone"]


def main():
    pts = json.load(open(os.path.join(WORK, "probe3_points.json"), encoding="utf-8"))
    out = {}
    P.PREFIX = "r3_"
    out["spcs83_fine"] = P.run83(pts["spcs83"])
    P.PREFIX = "r3dA_"
    out["datum_in_nad83_out_natrf"] = P.run22(
        pts["spcs2022_datum"], indatum="NAD83(2011) epoch 2010.00",
        outdatum="NATRF2022 epoch 2020.00")
    P.PREFIX = "r3dB_"
    out["datum_in_natrf_out_natrf"] = P.run22(pts["spcs2022_datum"])
    # Keweenaw water split: bisect three transects Keweenaw -> Isle Royale
    trans = [((47.47, -87.85), (48.00, -88.70)),
             ((47.30, -88.60), (47.90, -89.20)),
             ((47.60, -87.60), (48.20, -88.30))]
    bis = []
    for k, (a, b) in enumerate(trans):
        P.PREFIX = "r3k%d_" % k
        lo, hi = 0.0, 1.0
        za = zone22(P.run22([dict(tag="k%d lo" % k, lat=a[0], lon=a[1])])[0])
        zb = zone22(P.run22([dict(tag="k%d hi" % k, lat=b[0], lon=b[1])])[0])
        steps = []
        if za != zb:
            for it in range(9):
                t = (lo + hi) / 2
                lat = a[0] + t * (b[0] - a[0]); lon = a[1] + t * (b[1] - a[1])
                P.PREFIX = "r3k%d_%d_" % (k, it)
                z = zone22(P.run22([dict(tag="k%d t=%.5f" % (k, t), lat=lat, lon=lon)])[0])
                steps.append((round(t, 5), round(lat, 6), round(lon, 6), z))
                if z == za:
                    lo = t
                else:
                    hi = t
        bis.append(dict(a=a, b=b, za=za, zb=zb, steps=steps,
                        switch_t=[lo, hi]))
    out["keweenaw_bisection"] = bis
    with open(os.path.join(WORK, "r3_ncat.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
