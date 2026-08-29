"""N0 item 6 -- SPCS2022 zone definitions: provenance and re-capture.

Re-fetches zoneDefinitions.json from its published URL so the copy under raw/
carries a verified digest, and saves the SPCS2022 pages that describe it.

Run:  py -3 capture_spcs.py
"""

from __future__ import annotations

import json
import os

import capture_lib as C

SUB = "spcs"

JSON_URL = "https://beta.ngs.noaa.gov/SPCS/json_data/zoneDefinitions.json"
PAGES = [
    "https://beta.ngs.noaa.gov/SPCS/zone-definitions.shtml",
    "https://beta.ngs.noaa.gov/SPCS/zone-information.html",
    "https://beta.ngs.noaa.gov/SPCS/coordinates.shtml",
    "https://beta.ngs.noaa.gov/SPCS/zone-bounds.shtml",
    "https://beta.ngs.noaa.gov/SPCS/learn-more.html",
]


def main():
    d = os.path.join(C.RAW, SUB)
    os.makedirs(d, exist_ok=True)
    recs = []

    r = C.fetch(JSON_URL, timeout=120)
    p = C.save(r, "zoneDefinitions.json", subdir=SUB)
    recs.append((r, p))
    print(C.describe(r, p))

    existing = os.path.join(C.RAW, "zoneDefinitions.json")
    if os.path.exists(existing):
        print("  prior capture raw/zoneDefinitions.json sha256 %s  %s"
              % (C.sha256_file(existing),
                 "MATCHES" if C.sha256_file(existing) == r["sha256"]
                 else "DIFFERS -- the published file changed"))

    for u in PAGES:
        rr = C.fetch(u, timeout=60)
        name = u.rsplit("/", 1)[-1]
        pp = C.save(rr, name, subdir=SUB)
        recs.append((rr, pp))
        print(C.describe(rr, pp))

    C.write_manifest(recs, "spcs_manifest.json")

    # Michigan rows, verbatim, as a committed extract.
    rows = json.loads(r["body"].decode("utf-8"))
    mi = [x for x in rows if x["Zone code"].startswith("26")]
    out = os.path.join(d, "michigan_zones.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(mi, fh, indent=2, ensure_ascii=False)
    print("\n%d Michigan rows extracted -> %s (sha256 %s)"
          % (len(mi), os.path.relpath(out, C.HERE), C.sha256_file(out)))
    print("total rows in file: %d" % len(rows))


if __name__ == "__main__":
    main()
