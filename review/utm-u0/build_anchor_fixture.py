"""Write tests/fixtures/utm_anchors.py from the frozen NCAT captures (work package U1).

Run from the repository root:  py review/utm-u0/build_anchor_fixture.py

Two sources, both already committed byte-for-byte (``review/autozone-r0/raw/**
-text`` in .gitattributes, so a Windows checkout keeps the bytes as fetched):

* PRODUCTION NCAT, NAD83(2011): every ``review/autozone-r0/raw/ncat_probe/*.json``
  whose ``srcDatum`` is NAD83(2011) and which carries ``utmNorthing`` - the
  REST API's own JSON, captured 2026-10-22 (review/autozone-r0/RECON.md
  section 5.1).
* BETA NCAT, NATRF2022: every ``*spcs2022*.html`` result page of the same
  capture whose export table's first row is NATRF2022 epoch 2020.00 in and out
  and carries a UTM block. The other beta pages show only the on-screen panel,
  which prints no UTM northing or easting, and are skipped (DESIGN.md #72).

Every value is written AS NCAT PRINTED IT, as a string, so the suite parses
NCAT's own text rather than a number this script produced; the suite then
re-hashes each raw file and re-runs ``parse_capture`` on it, so the fixture
cannot drift from its source. Nothing here computes a coordinate.
"""

from __future__ import annotations

import glob
import hashlib
import html
import json
import os
import re
import sys

PROBE = "review/autozone-r0/raw/ncat_probe"
OUT = "tests/fixtures/utm_anchors.py"

BETA_ROW = re.compile(
    r"\| 1 \| \| NATRF2022 epoch 2020\.00 \| \| NATRF2022 epoch 2020\.00 \|"
    r"(?:[^|]*\|){4}.*? \| \| (-?\d+\.\d+) \| \| N\d+\.\d+ \| \| (-?\d+\.\d+) \| \| W\d+\.\d+ \|"
    r" \| N/A \| \| N/A \|.*?\| UTM Zone (\d+) \| \| ([\d.]+) \| \| ([\d.]+) \|"
    r" \| ([+-]\d\d \d\d [\d.]+) \| \| ([\d.]+) \|"
)
"""The export table's first row: the OUTPUT latitude and longitude (the second
pair, after the input pair and its three N/A heights), then the UTM block -
zone, northing, easting, convergence, scale factor."""


def parse_capture(path: str, raw: bytes):
    """(frame, latitude, longitude, zone, northing, easting, convergence, scale), as printed.

    Returns None for a capture that carries no usable UTM result. The suite
    imports this function, so the rule that read the fixture is the rule that
    re-reads it.
    """
    if path.endswith(".json"):
        r = json.loads(raw.decode("utf-8"))
        if r.get("srcDatum") != "NAD83(2011)" or "utmNorthing" not in r:
            return None
        if r.get("destDatum") != "NAD83(2011)":
            return None
        return (
            "NAD83(2011)",
            r["destLat"],
            r["destLon"],
            int(r["utmZone"].split()[-1]),
            r["utmNorthing"].replace(",", ""),
            r["utmEasting"].replace(",", ""),
            r["utmConvergence"],
            r["utmScaleFactor"],
        )
    text = raw.decode("utf-8", errors="replace")
    flat = html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]+>", " | ", text)))
    m = BETA_ROW.search(flat)
    if not m:
        return None
    return ("NATRF2022", m.group(1), m.group(2), int(m.group(3)),
            m.group(4), m.group(5), m.group(6), m.group(7))


HEADER = '''"""UTM anchors - frozen NCAT truth, NOT derived here (work package U1, DESIGN.md #72).

Written by review/utm-u0/build_anchor_fixture.py from captures already in the
repository; tests/test_utm.py re-hashes every raw file and re-parses it with
the generator's own ``parse_capture``, so these rows cannot drift from their
source.

* ``NAD83_2011_ANCHORS``: production NCAT (https://geodesy.noaa.gov/api/ncat/llh,
  NAD83(2011) in and out), captured 2026-10-22, review/autozone-r0/raw/ncat_probe/*.json.
* ``NATRF2022_ANCHORS``: NGS beta - beta NCAT's web app
  (https://beta.ngs.noaa.gov/NCAT/, NATRF2022 epoch 2020.00 in and out),
  captured 2026-10-22, review/autozone-r0/raw/ncat_probe/*spcs2022*.html;
  re-freeze obligation in docs/REFREEZE-NSRS.md.

Every value is NCAT's printed text. NCAT prints northing and easting to 0.001 m,
convergence to 0.01" (DD MM SS.ss) and the scale factor to 8 decimals
(production) or 9 (beta). No anchor falls in UTM zone 15: it covers only the
western tip of Gogebic County.
"""

from __future__ import annotations

from typing import NamedTuple


class UtmAnchor(NamedTuple):
    capture: str  # repository path of the raw NCAT response
    sha256: str  # of the committed bytes
    frame: str  # 'NAD83(2011)' or 'NATRF2022'
    latitude: str  # as printed, decimal degrees
    longitude: str  # as printed, decimal degrees, negative west
    zone: int  # NCAT's UTM zone number (northern hemisphere)
    northing: str  # metres, as printed
    easting: str  # metres, as printed
    convergence: str  # 'DD MM SS.ss', signed, as printed
    scale_factor: str  # as printed

'''


def main() -> None:
    rows = {"NAD83(2011)": [], "NATRF2022": []}
    for path in sorted(glob.glob(f"{PROBE}/*.json") + glob.glob(f"{PROBE}/*spcs2022*.html")):
        path = path.replace(os.sep, "/")
        raw = open(path, "rb").read()
        parsed = parse_capture(path, raw)
        if parsed is None:
            continue
        rows[parsed[0]].append((path, hashlib.sha256(raw).hexdigest(), *parsed))
    out = [HEADER]
    for name, frame in (("NAD83_2011_ANCHORS", "NAD83(2011)"), ("NATRF2022_ANCHORS", "NATRF2022")):
        out.append(f"{name}: tuple[UtmAnchor, ...] = (\n")
        for row in rows[frame]:
            out.append(f"    UtmAnchor{row!r},\n")
        out.append(")\n\n")
    with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("".join(out).rstrip("\n") + "\n")
    print({frame: len(v) for frame, v in rows.items()}, "->", OUT)


if __name__ == "__main__":
    sys.exit(main())
