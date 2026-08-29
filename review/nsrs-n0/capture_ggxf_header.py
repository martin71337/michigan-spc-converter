"""N0 item 2 -- read the GEOID2022 GGXF header without downloading 757 MB.

The GGXF (NetCDF-4/HDF5) header sits at the front of the file, so an HTTP Range
request for the first 256 KiB is enough to read every declared attribute:
the source CRS, the vertical CRS, the grid dimensions, the interpolation
method, and the static-plus-rate arithmetic NGS embeds as documentation.

This exists because the developer-guide HTML and the file itself disagree about
the interpolation method, and the file is the authority.

Run:  py -3 capture_ggxf_header.py
"""

from __future__ import annotations

import os
import re
import urllib.request

import capture_lib as C

SUB = "napgd2022"
NBYTES = 256 * 1024

TARGETS = [
    "https://beta.ngs.noaa.gov/NAPGD2022/data/geoid2022/GEOID2022.beta_v0a.ggxf",
]


def head_slice(url, n=NBYTES):
    req = urllib.request.Request(url)
    req.add_header("Range", "bytes=0-%d" % (n - 1))
    req.add_header("User-Agent", C.USER_AGENT)
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.status, r.headers.get("Content-Range"), r.read()


def main():
    d = os.path.join(C.RAW, SUB)
    os.makedirs(d, exist_ok=True)
    for url in TARGETS:
        status, crange, body = head_slice(url)
        name = os.path.basename(url) + ".head256k"
        p = os.path.join(d, name)
        with open(p, "wb") as fh:
            fh.write(body)
        print("GET(Range) %s" % url)
        print("  status=%s Content-Range=%s" % (status, crange))
        print("  slice bytes=%d sha256=%s" % (len(body), C.sha256_bytes(body)))
        print("  saved=%s" % os.path.relpath(p, C.HERE))
        text = body.decode("latin-1")
        print("\n  --- printable attribute strings in the header ---")
        for s in sorted(set(m.group(0) for m in
                            re.finditer(r"[\x20-\x7e]{8,}", text[:20000]))):
            print("   ", s[:200])
        m = re.search(r"interpolationMethod\x00.{0,24}?([a-z]{6,12})", text,
                      re.S)
        print("\n  interpolationMethod declared IN THE FILE: %s"
              % (m.group(1) if m else "NOT FOUND"))


if __name__ == "__main__":
    main()
