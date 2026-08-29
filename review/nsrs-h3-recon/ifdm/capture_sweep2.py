"""Sweep 2: prove presence or absence of IFDM2022 DOCUMENTATION.

The grids are found (they download from the beta NCAT app). What is not yet
found is any NGS document that describes them: the format, the interpolation,
the sign, the epoch convention, or how NCAT applies them. This sweep covers
the places such a document would live.

Downloads the recent Technical Memoranda (the TR series was covered in
capture_pubs2.py) and fetches the NGS pages that discuss the modernized NSRS.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture_lib as cl

LIB = "https://geodesy.noaa.gov/library/pdfs/"

# Technical Memoranda that answered 200 in the pubs2 probe, recent half.
TM = [78, 79, 81, 83, 90, 91, 92, 94, 95, 97, 98]

PAGES = [
    ("ngs_newdatums_index",
     "https://geodesy.noaa.gov/datums/newdatums/index.shtml"),
    ("ngs_newdatums_naming",
     "https://www.ngs.noaa.gov/datums/newdatums/naming-convention.shtml"),
    ("ngs_newdatums_reference_frames",
     "https://geodesy.noaa.gov/datums/newdatums/reference-frames.shtml"),
    ("ngs_newdatums_qa",
     "https://geodesy.noaa.gov/datums/newdatums/QandA.shtml"),
    ("ngs_presentations_library",
     "https://geodesy.noaa.gov/web/science_edu/presentations_library/"),
    ("ngs_tools_index", "https://geodesy.noaa.gov/TOOLS/"),
    ("ngs_htdp", "https://geodesy.noaa.gov/TOOLS/Htdp/Htdp.shtml"),
    ("beta_index", "https://beta.ngs.noaa.gov/"),
    ("beta_napgd2022", "https://beta.ngs.noaa.gov/NAPGD2022/index.html"),
    ("beta_spcs", "https://beta.ngs.noaa.gov/SPCS/index.html"),
    ("beta_ncat_dotb_format",
     "https://beta.ngs.noaa.gov/NCAT/dot-b_format.pdf"),
    ("beta_ncat_coverage",
     "https://beta.ngs.noaa.gov/NCAT/Nadcon-Vertcon_Coverage.pdf"),
    # Search endpoints -- what NGS's own site search knows about IFDM2022.
    ("search_gov_ifdm",
     "https://search.usa.gov/search?affiliate=noaa.gov&query=IFDM2022"),
]


def main():
    records = []
    for n in TM:
        name = "NOAA_TM_NOS_NGS_%04d.pdf" % n
        rec = cl.fetch(LIB + name, timeout=600)
        p = cl.save(rec, name, subdir="pubs") if rec.get("body") else None
        print(cl.describe(rec, p))
        records.append((rec, p))
    for name, url in PAGES:
        rec = cl.fetch(url, timeout=120)
        ext = ".pdf" if url.endswith(".pdf") else ".html"
        p = cl.save(rec, name + ext, subdir="sweep2") if rec.get("body") else None
        print(cl.describe(rec, p))
        records.append((rec, p))
    p = cl.write_manifest(records, "sweep2_manifest.json")
    print("\nmanifest:", p)


if __name__ == "__main__":
    main()
