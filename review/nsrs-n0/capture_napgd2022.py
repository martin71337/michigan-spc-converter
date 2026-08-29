"""N0 item 2 + item 5 -- NAPGD2022 / GEOID2022 downloads, and NATRF2022 / EPP2022.

Crawls the beta product pages, saves them raw, extracts every download link out
of the tables, and HEADs each one. Nothing over SIZE_LIMIT is downloaded --
headers only -- because the point of N0 is to MEASURE, not to acquire.

Small parameter files (EPP2022, test cases) ARE downloaded and hashed.

Run:  py -3 capture_napgd2022.py
"""

from __future__ import annotations

import os
import re
import urllib.parse

import capture_lib as C

SUB = "napgd2022"
SIZE_LIMIT = 50 * 1024 * 1024  # do not download anything larger

PAGES = [
    "https://beta.ngs.noaa.gov/NAPGD2022/index.html",
    "https://beta.ngs.noaa.gov/NAPGD2022/download.html",
    "https://beta.ngs.noaa.gov/NAPGD2022/developer-guide.html",
    "https://beta.ngs.noaa.gov/NAPGD2022/change-log.html",
    "https://beta.ngs.noaa.gov/NAPGD2022/map-gallery.html",
    "https://beta.ngs.noaa.gov/NATRF2022/index.html",
    "https://beta.ngs.noaa.gov/SPCS/index.html",
    "https://beta.ngs.noaa.gov/index.html",
    "https://beta.ngs.noaa.gov/sitemap.html",
]

# Extensions worth a HEAD (data / parameter payloads, not navigation).
DATA_EXT = (".ggxf", ".bin", ".b", ".csv", ".txt", ".zip", ".nc", ".pdf",
            ".xml", ".json", ".tif", ".gz")

# Small files that are downloaded outright and hashed.
SMALL_EXT = (".csv", ".txt", ".json", ".xml")


def page_name(url):
    p = urllib.parse.urlparse(url)
    n = (p.path.strip("/").replace("/", "__")) or "index"
    return n if n.endswith((".html", ".htm", ".shtml")) else n + ".html"


def main():
    d = os.path.join(C.RAW, SUB)
    os.makedirs(d, exist_ok=True)
    records = []
    data_links = {}

    for url in PAGES:
        r = C.fetch(url, timeout=90)
        p = C.save(r, page_name(url), subdir=SUB)
        records.append((r, p))
        print(C.describe(r, p))
        if r["status"] != 200 or not r["body"]:
            print()
            continue
        html = r["body"].decode("utf-8", "replace")
        for href in re.findall(r'href="([^"]+)"', html):
            full = urllib.parse.urljoin(url, href)
            low = urllib.parse.urlparse(full).path.lower()
            if low.endswith(DATA_EXT) and "ngs.noaa.gov" in full:
                data_links.setdefault(full, url)
        print()

    print("### %d data links found\n" % len(data_links))
    for link, src in sorted(data_links.items()):
        low = urllib.parse.urlparse(link).path.lower()
        h = C.head(link, timeout=90)
        size = h["headers"].get("Content-Length")
        records.append((h, None))
        print(C.describe(h))
        print("        linked from %s" % src)
        try:
            n = int(size) if size else None
        except ValueError:
            n = None
        if low.endswith(SMALL_EXT) and (n is None or n <= SIZE_LIMIT):
            g = C.fetch(link, timeout=180)
            name = os.path.basename(urllib.parse.urlparse(link).path)
            p = C.save(g, name, subdir=SUB)
            records.append((g, p))
            print("        DOWNLOADED %s bytes sha256 %s -> %s" %
                  (g["bytes"], g["sha256"], os.path.relpath(p, C.HERE)))
        print()

    C.write_manifest(records, "napgd2022_manifest.json")


if __name__ == "__main__":
    main()
