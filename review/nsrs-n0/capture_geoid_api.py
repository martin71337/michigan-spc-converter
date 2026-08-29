"""N0 item 4 -- the NGS geoid height API: does anything serve GEOID2022?

Enumerates the numeric `model` registry on BOTH the beta and the production
hosts, plus the obvious GEOID2022 name tokens. Every refusal is saved: the
error text is what documents the registry's actual contents.

Run:  py -3 capture_geoid_api.py
"""

from __future__ import annotations

import os

import capture_lib as C

SUB = "geoid_api"
HOSTS = ["beta.ngs.noaa.gov", "geodesy.noaa.gov"]
LAT, LON = 43.0, -84.5

MODELS = [str(i) for i in range(0, 26)] + [
    "2022", "GEOID2022", "geoid2022", "G2022", "SGEOID2022", "NAPGD2022",
]


def main():
    os.makedirs(os.path.join(C.RAW, SUB), exist_ok=True)
    recs = []
    for host in HOSTS:
        r = C.fetch("https://%s/api/geoid/meta" % host, timeout=45)
        p = C.save(r, "%s__meta.json" % host.split(".")[0], subdir=SUB)
        recs.append((r, p))
        print(C.describe(r, p))
        for m in MODELS:
            url = ("https://%s/api/geoid/ght?lat=%s&lon=%s&model=%s"
                   % (host, LAT, LON, m))
            r = C.fetch(url, timeout=30)
            name = "%s__model_%s.json" % (host.split(".")[0], m)
            p = C.save(r, name, subdir=SUB)
            recs.append((r, p))
            body = " ".join(C.preview(r, 300).split())
            print("  %-18s model=%-11s %s" % (host, m, body[:130]))
        print()
    C.write_manifest(recs, "geoid_api_manifest.json")


if __name__ == "__main__":
    main()
