"""Download the NGS technical reports the beta NCAT page itself cites.

The page's three grid blocks cite:
    Nadcon5 grids   -> NOAA_TR_NOS_NGS_0063.pdf   ("Learn more")
    Vertcon3 grids  -> NOAA_TR_NOS_NGS_0068.pdf   ("Learn more")
    IFDM2022 grids  -> (NO "Learn more" link at all)

TR 63 is captured because the H3 brief names it as the NATRF2022 defining
document. The page itself says otherwise -- it cites 63 for NADCON 5.0 -- so
the download settles which is true from the PDF's own title page.

The neighbouring recent reports are HEAD-probed so the recon can say whether
an IFDM2022 report exists in the library under a number nobody linked.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture_lib as cl

LIB = "https://geodesy.noaa.gov/library/pdfs/"

FULL = [
    ("NOAA_TR_NOS_NGS_0063.pdf", "TR 63 -- cited by the page for Nadcon5"),
    ("NOAA_TR_NOS_NGS_0068.pdf", "TR 68 -- cited by the page for Vertcon3"),
]

# The library listing holds TR 0028..0084. Probe every report from 0069 up,
# where a NATRF2022 / IFDM2022 document would have to live if one exists.
PROBE = ["NOAA_TR_NOS_NGS_%04d.pdf" % n for n in range(69, 90)]
PROBE += ["NOAA_TR_NOS_NGS_0067.pdf", "NOAA_TR_NOS_NGS_0066.pdf",
          "NOAA_TR_NOS_NGS_0065.pdf", "NOAA_TR_NOS_NGS_0064.pdf",
          "NOAA_TR_NOS_NGS_0062.pdf", "NOAA_TR_NOS_NGS_0061.pdf"]


def main():
    records = []
    for name, why in FULL:
        rec = cl.fetch(LIB + name, timeout=900)
        rec["why"] = why
        p = cl.save(rec, name, subdir="pubs")
        print(cl.describe(rec, p))
        print()
        records.append((rec, p))
    for name in PROBE:
        rec = cl.head(LIB + name, timeout=90)
        print(cl.describe(rec))
        records.append((rec, None))
    p = cl.write_manifest(records, "pubs_manifest.json")
    print("\nmanifest:", p)


if __name__ == "__main__":
    main()
