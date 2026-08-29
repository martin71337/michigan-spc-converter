"""Sweep 1: does an IFDM2022 page or grid directory exist anywhere on NGS?

Every candidate URL is recorded whether it answers or refuses. A 404 is a
measurement: it is how the absence gets proved, the way N0 proved the
NAVD88-NAPGD2022 absence.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture_lib as cl

CANDIDATES = [
    # Beta site -- the tool that names IFDM2022
    ("beta_ncat_index", "https://beta.ngs.noaa.gov/NCAT/"),
    ("beta_ifdm2022_dir", "https://beta.ngs.noaa.gov/IFDM2022/"),
    ("beta_ifdm2022_index", "https://beta.ngs.noaa.gov/IFDM2022/index.html"),
    ("beta_ifdm_dir", "https://beta.ngs.noaa.gov/IFDM/"),
    ("beta_natrf2022_index", "https://beta.ngs.noaa.gov/NATRF2022/index.html"),
    ("beta_natrf2022_dir", "https://beta.ngs.noaa.gov/NATRF2022/"),
    ("beta_sitemap_xml", "https://beta.ngs.noaa.gov/sitemap.xml"),
    ("beta_sitemap_html", "https://beta.ngs.noaa.gov/sitemap.html"),
    ("beta_robots", "https://beta.ngs.noaa.gov/robots.txt"),
    ("beta_datasheet_products", "https://beta.ngs.noaa.gov/PC_PROD/"),
    # Production geodesy.noaa.gov
    ("geo_ifdm2022_dir", "https://geodesy.noaa.gov/IFDM2022/"),
    ("geo_ifdm2022_index", "https://geodesy.noaa.gov/IFDM2022/index.shtml"),
    ("geo_ifdm_dir", "https://geodesy.noaa.gov/IFDM/"),
    ("geo_natrf2022", "https://geodesy.noaa.gov/NATRF2022/index.shtml"),
    ("geo_natrf2022_html", "https://geodesy.noaa.gov/NATRF2022/index.html"),
    ("geo_sitemap", "https://geodesy.noaa.gov/sitemap.xml"),
    ("geo_robots", "https://geodesy.noaa.gov/robots.txt"),
    ("geo_datums_new", "https://geodesy.noaa.gov/datums/newdatums/index.shtml"),
    # www.ngs.noaa.gov mirror
    ("www_ifdm2022_dir", "https://www.ngs.noaa.gov/IFDM2022/"),
    ("www_natrf2022", "https://www.ngs.noaa.gov/NATRF2022/index.shtml"),
    # Plausible grid homes
    ("geo_pc_prod_ifdm", "https://geodesy.noaa.gov/PC_PROD/IFDM2022/"),
    ("geo_pub_ifdm", "https://geodesy.noaa.gov/pub/IFDM2022/"),
    ("beta_web_tools_ncat", "https://beta.ngs.noaa.gov/web/tools/NCAT/"),
    # Library landing (the technical-report index)
    ("geo_library_index", "https://geodesy.noaa.gov/library/"),
    ("geo_library_pdfs", "https://geodesy.noaa.gov/library/pdfs/"),
]


def main():
    records = []
    for name, url in CANDIDATES:
        rec = cl.fetch(url, timeout=60)
        path = None
        if rec.get("body"):
            ext = ".html"
            ct = (rec["headers"].get("Content-Type") or "").lower()
            if "xml" in ct:
                ext = ".xml"
            elif "plain" in ct:
                ext = ".txt"
            elif "json" in ct:
                ext = ".json"
            path = cl.save(rec, name + ext, subdir="sweep")
        print(cl.describe(rec, path))
        print()
        records.append((rec, path))
    p = cl.write_manifest(records, "sweep_manifest.json")
    print("manifest:", p)


if __name__ == "__main__":
    main()
