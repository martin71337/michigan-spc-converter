"""N0 -- is the beta API host actually carrying its grids?

Beta and production expose the same REST endpoints with byte-identical metadata,
so it is tempting to treat beta as production-plus-NATRF2022. This script tests
that assumption on the two paths MCX already depends on -- the VERTCON
orthometric shift and the geoid height -- by asking both hosts the same
question and printing the two answers side by side.

Run:  py -3 capture_beta_data_check.py
"""

from __future__ import annotations

import json
import os
import urllib.parse

import capture_lib as C

SUB = "beta_data_check"
LAT, LON = 43.0, -84.5
HOSTS = ["beta.ngs.noaa.gov", "geodesy.noaa.gov"]


def main():
    os.makedirs(os.path.join(C.RAW, SUB), exist_ok=True)
    recs = []

    print("### VERTCON 3.0 orthometric shift, NGVD29 -> NAVD88, 200.000 m")
    for host in HOSTS:
        for ind, outd in [("NAD83(2011)", "NAD83(2011)"),
                          ("NAD83(2011)", "NAD83(NSRS2007)")]:
            q = urllib.parse.urlencode({
                "lat": LAT, "lon": LON, "inDatum": ind, "outDatum": outd,
                "orthoHt": 200.0,
                "inVertDatum": "NGVD29", "outVertDatum": "NAVD88",
            })
            url = "https://%s/api/ncat/llh?%s" % (host, q)
            r = C.fetch(url, timeout=45)
            name = "%s__ngvd29_navd88__%s.json" % (
                host.split(".")[0], outd.replace("(", "").replace(")", ""))
            p = C.save(r, name, subdir=SUB)
            recs.append((r, p))
            try:
                d = json.loads(r["body"])
            except Exception:
                d = {}
            print("  %-18s %s -> %-18s srcOrthoht=%s destOrthoht=%s "
                  "sigOrthoht=%s vertconVersion=%s"
                  % (host, ind, outd, d.get("srcOrthoht"),
                     d.get("destOrthoht"), d.get("sigOrthoht"),
                     d.get("vertconVersion")))

    print("\n### geoid height, model 14 (GEOID18)")
    for host in HOSTS:
        url = ("https://%s/api/geoid/ght?lat=%s&lon=%s&model=14"
               % (host, LAT, LON))
        r = C.fetch(url, timeout=45)
        p = C.save(r, "%s__geoid_model14.json" % host.split(".")[0],
                   subdir=SUB)
        recs.append((r, p))
        print("  %-18s %s" % (host, " ".join(C.preview(r, 400).split())))

    print("\n### the meta endpoints, for the digest comparison")
    metas = {}
    for host in HOSTS:
        for path in ("/api/ncat/meta", "/api/geoid/meta"):
            r = C.fetch("https://%s%s" % (host, path), timeout=45)
            name = "%s__%s.json" % (host.split(".")[0],
                                    path.strip("/").replace("/", "_"))
            p = C.save(r, name, subdir=SUB)
            recs.append((r, p))
            metas.setdefault(path, []).append((host, r["sha256"]))
    for path, rows in metas.items():
        digs = {s for _, s in rows}
        print("  %-18s %s   (%s)" %
              (path, " ".join("%s=%s" % (h, s[:16]) for h, s in rows),
               "IDENTICAL" if len(digs) == 1 else "DIFFERENT"))

    C.write_manifest(recs, "beta_data_check_manifest.json")


if __name__ == "__main__":
    main()
