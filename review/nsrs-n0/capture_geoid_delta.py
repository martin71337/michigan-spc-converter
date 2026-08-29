"""N0 -- how far apart are GEOID18 and SGEOID2022 in Michigan's neighbourhood?

There is no GEOID2022 service to query (item 4 is NO-GO), so the only published
GEOID2022 values available today are the ones in NGS's own test-case CSV. Two
of its 87 points fall in or beside the Michigan window. This script queries the
production GEOID18 API at exactly those coordinates and prints the difference.

WHAT THE DIFFERENCE IS, AND IS NOT. GEOID18 is a HYBRID model, fitted to
NAVD 88 bench marks; SGEOID2022 is a GRAVIMETRIC geoid defining NAPGD2022. The
gap between them is therefore mostly the NAVD 88 -> NAPGD2022 DATUM offset, not
model disagreement about the same surface. It is recorded here to size the
change, not to be used as a conversion.

The test-case coordinates are stated by NGS as ITRF2020; the GEOID18 API takes
NAD83(2011). The frame difference is under a metre horizontally, where the
geoid gradient is of order 1e-5 m/m, so it does not affect the figures below at
the millimetre they are printed to.

Run:  py -3 capture_geoid_delta.py
"""

from __future__ import annotations

import csv
import json
import os

import capture_lib as C

SUB = "geoid_delta"
TESTCASES = os.path.join(C.RAW, "napgd2022", "NAPGD2022TestCases.beta_v0a.csv")

# Michigan window: the three MCX zones plus a margin.
LAT_MIN, LAT_MAX = 41.0, 48.5
LON_MIN, LON_MAX = -91.0, -82.0


def main():
    os.makedirs(os.path.join(C.RAW, SUB), exist_ok=True)
    if not os.path.exists(TESTCASES):
        raise SystemExit("run capture_napgd2022.py first -- %s missing"
                         % TESTCASES)
    rows = [r for r in open(TESTCASES, encoding="utf-8")
            if not r.startswith("#")]
    recs = []
    print("test cases file sha256 %s" % C.sha256_file(TESTCASES))
    print("%-34s %10s %10s %9s %10s" %
          ("point", "GEOID18", "SGEOID2022", "diff(m)", "Ndot mm/yr"))
    for r in csv.DictReader(rows):
        lat = float(r["Latitude_decdeg"])
        lon = float(r["Longitude_decdeg"])
        lon = lon - 360.0 if lon > 180.0 else lon
        if not (LAT_MIN < lat < LAT_MAX and LON_MIN < lon < LON_MAX):
            continue
        url = ("https://geodesy.noaa.gov/api/geoid/ght?lat=%.8f&lon=%.8f"
               "&model=14" % (lat, lon))
        resp = C.fetch(url, timeout=45)
        p = C.save(resp, "geoid18_%s.json" % r["Name"].lower().replace(" ", "_"),
                   subdir=SUB)
        recs.append((resp, p))
        g18 = json.loads(resp["body"])["geoidHeight"]
        sg = float(r["SGEOID2022_m"])
        print("%-34s %10.4f %10.4f %+9.4f %10s" %
              (r["Name"], g18, sg, sg - g18, r["DGEOID2022_mmperyear"]))
    C.write_manifest(recs, "geoid_delta_manifest.json")


if __name__ == "__main__":
    main()
