"""Second publication pass: find out what the recent NGS reports actually are.

The first pass proved which report numbers EXIST. This pass downloads the
recent ones and reads their title pages, because a number is not a title: the
brief assumed TR NOS NGS 63 is the NATRF2022 defining document, and the beta
NCAT page cites 63 for NADCON 5.0 instead. Only the title page settles it.

Also probes the Technical Memorandum series, which the first pass did not
cover and which a web lead showed runs at least to TM 0090.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture_lib as cl

LIB = "https://geodesy.noaa.gov/library/pdfs/"

# Every Technical Report that answered 200 in pass 1, from 61 up.
TR = [61, 62, 64, 66, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 82, 83, 84]
# Technical Memoranda -- range unknown, probe wide.
TM = list(range(60, 101))


def main():
    records = []
    for n in TR:
        name = "NOAA_TR_NOS_NGS_%04d.pdf" % n
        rec = cl.fetch(LIB + name, timeout=600)
        p = cl.save(rec, name, subdir="pubs") if rec.get("body") else None
        print(cl.describe(rec, p))
        records.append((rec, p))
    for n in TM:
        name = "NOAA_TM_NOS_NGS_%04d.pdf" % n
        rec = cl.head(LIB + name, timeout=60)
        print("%s -> %s (%s bytes)" % (
            name, rec["status"], rec["headers"].get("Content-Length")))
        records.append((rec, None))
    p = cl.write_manifest(records, "pubs2_manifest.json")
    print("\nmanifest:", p)


if __name__ == "__main__":
    main()
