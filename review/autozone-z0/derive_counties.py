"""Z0: derive data/mi_counties_tiger2025.json from the Census TIGER/Line 2025
county shapefile, stdlib only.

    py -I review/autozone-z0/derive_counties.py [path/to/tl_2025_us_county.zip [output]]

Reads the zip in place (default: review/autozone-r0/raw/tiger/, where the
autozone-r0 recon left it; it is 84 MB and git-ignored, see RECON.md section
1.2), refuses unless its SHA-256 is the one RECON.md recorded, and writes the
83 Michigan counties (STATEFP 26) to data/mi_counties_tiger2025.json.

What is kept, and what is not touched:

* every county record whose STATEFP is "26" - TIGER's own polygons, which
  extend into the Great Lakes to the state's water boundary;
* every part ("ring") of each polygon, in the shapefile's own order, and every
  vertex of each ring in its own order, the closing vertex included. No ring is
  dropped, merged, re-oriented, simplified or de-duplicated;
* every coordinate exactly as the shapefile stores it: an IEEE-754 double,
  written with Python's repr, which is the shortest decimal string that reads
  back to the identical double. So no rounding is introduced here at all. The
  shapefile's own values are TIGER's published decimals (at most 6 decimal
  places of a degree, about 0.1 m; measured and printed by this script).

The output is a DERIVED serialization (JSON, not the shapefile's binary), so it
is byte-identical to nothing under review/ (build gate 6). Its SHA-256 is
printed and is the digest michspc/fileio/counties.py pins.

Shapefile layout: ESRI Shapefile Technical Description (ESRI white paper,
July 1998): 100-byte main header; each record an 8-byte big-endian header
(record number, content length in 16-bit words) then little-endian content;
shape type 5 = Polygon: box (4 doubles), NumParts, NumPoints, Parts[NumParts],
Points[NumPoints] as (X, Y) doubles. The .shx index holds one big-endian
(offset, length) pair per record, in 16-bit words. dBASE III .dbf: 32-byte
header (record count at 4, header length at 8, record length at 10), 32-byte
field descriptors terminated by 0x0D, each record prefixed by a deletion flag.
"""

from __future__ import annotations

import hashlib
import io
import json
import struct
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ZIP = REPO / "review" / "autozone-r0" / "raw" / "tiger" / "tl_2025_us_county.zip"
OUTPUT = REPO / "data" / "mi_counties_tiger2025.json"

ZIP_SHA256 = "9c6e9d9076abce2670d1de255de3710c35ecca00a7005d88e012dec52d95f763"
"""RECON.md section 1.2 records `9c6e9d90...f763`, 83,989,800 bytes, fetched
from www2.census.gov/geo/tiger/TIGER2025/COUNTY/tl_2025_us_county.zip
(Last-Modified 2025-09-23). The full digest is the one this file hashed to on
the recon machine, matching that prefix and suffix."""

ZIP_BYTES = 83_989_800
STEM = "tl_2025_us_county"
MICHIGAN = "26"


def read_dbf(data: bytes, encoding: str) -> list[dict[str, str]]:
    count, header_len, record_len = struct.unpack("<IHH", data[4:12])
    fields = []
    pos = 32
    while data[pos] != 0x0D:
        name = data[pos : pos + 11].split(b"\0", 1)[0].decode("ascii")
        ftype = chr(data[pos + 11])
        flen = data[pos + 16]
        fields.append((name, ftype, flen))
        pos += 32
    records = []
    for i in range(count):
        start = header_len + i * record_len
        rec = data[start : start + record_len]
        if rec[0:1] == b"*":
            raise SystemExit(f"dbf record {i} is flagged deleted; refusing to guess")
        off = 1
        row = {}
        for name, _ftype, flen in fields:
            row[name] = rec[off : off + flen].decode(encoding).strip()
            off += flen
        records.append(row)
    return records


def read_polygon(shp: bytes, offset_bytes: int, expect_number: int):
    number, length_words = struct.unpack(">ii", shp[offset_bytes : offset_bytes + 8])
    if number != expect_number:
        raise SystemExit(f"shp record number {number}, expected {expect_number}")
    content = shp[offset_bytes + 8 : offset_bytes + 8 + 2 * length_words]
    (shape_type,) = struct.unpack("<i", content[0:4])
    if shape_type != 5:
        raise SystemExit(f"record {number}: shape type {shape_type}, expected 5 (Polygon)")
    num_parts, num_points = struct.unpack("<ii", content[36:44])
    parts = struct.unpack(f"<{num_parts}i", content[44 : 44 + 4 * num_parts])
    pts_off = 44 + 4 * num_parts
    flat = struct.unpack(f"<{2 * num_points}d", content[pts_off : pts_off + 16 * num_points])
    if len(content) != pts_off + 16 * num_points:
        raise SystemExit(f"record {number}: content length does not match its point count")
    bounds = list(parts) + [num_points]
    rings = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        rings.append([[flat[2 * k], flat[2 * k + 1]] for k in range(a, b)])
    return rings


def decimals(value: float) -> int:
    text = repr(value)
    return len(text.split(".", 1)[1]) if "." in text else 0


def signed_area(ring) -> float:
    s = 0.0
    for (x0, y0), (x1, y1) in zip(ring[:-1], ring[1:]):
        s += x0 * y1 - x1 * y0
    return s / 2.0


def main() -> None:
    zip_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ZIP
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else OUTPUT
    raw = zip_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != ZIP_SHA256 or len(raw) != ZIP_BYTES:
        raise SystemExit(
            f"{zip_path}: SHA-256 {digest}, {len(raw)} bytes; RECON.md recorded "
            f"{ZIP_SHA256}, {ZIP_BYTES}. Refusing to derive from a different file."
        )
    archive = zipfile.ZipFile(io.BytesIO(raw))
    encoding = archive.read(f"{STEM}.cpg").decode("ascii").strip()
    if encoding.upper().replace("-", "") != "UTF8":
        raise SystemExit(f"unexpected .cpg encoding {encoding!r}")
    records = read_dbf(archive.read(f"{STEM}.dbf"), "utf-8")
    shx = archive.read(f"{STEM}.shx")
    shp = archive.read(f"{STEM}.shp")
    if len(shx) != 100 + 8 * len(records):
        raise SystemExit(".shx does not index one entry per .dbf record")

    counties = []
    for i, row in enumerate(records):
        if row["STATEFP"] != MICHIGAN:
            continue
        offset_words, _ = struct.unpack(">ii", shx[100 + 8 * i : 108 + 8 * i])
        rings = read_polygon(shp, 2 * offset_words, i + 1)
        if row["GEOID"] != row["STATEFP"] + row["COUNTYFP"]:
            raise SystemExit(f"record {i}: GEOID {row['GEOID']} is not STATEFP+COUNTYFP")
        counties.append(
            {
                "fips": row["GEOID"],
                "name": row["NAME"],
                "namelsad": row["NAMELSAD"],
                "rings": rings,
            }
        )
    counties.sort(key=lambda c: c["fips"])

    # Measurements, printed for the work record; nothing is changed by them.
    vertices = sum(len(r) for c in counties for r in c["rings"])
    ring_count = sum(len(c["rings"]) for c in counties)
    max_dec = max(decimals(v) for c in counties for r in c["rings"] for p in r for v in p)
    holes = sum(1 for c in counties for r in c["rings"] if signed_area(r) > 0)
    open_rings = sum(1 for c in counties for r in c["rings"] if r[0] != r[-1])

    header = {
        "format": "mcx-county-polygons/1",
        "source": (
            "US Census Bureau TIGER/Line Shapefiles 2025, counties: "
            "www2.census.gov/geo/tiger/TIGER2025/COUNTY/tl_2025_us_county.zip "
            f"(Last-Modified 2025-09-23, {ZIP_BYTES} bytes, SHA-256 {ZIP_SHA256}); "
            "public domain (US Government work)"
        ),
        "selection": "STATEFP 26 (Michigan), all 83 counties, water-extended as TIGER publishes them",
        "coordinates": (
            "[longitude, latitude] in decimal degrees, east-positive longitude (Michigan "
            "longitudes are negative), NAD83 geographic (the shapefile's .prj: "
            "GCS_North_American_1983), every value the shapefile's own IEEE double "
            "written with Python repr (exact round trip)"
        ),
        "rings": (
            "every shapefile part in its own order and vertex order, closing vertex "
            "included; shapefile convention: outer rings clockwise, holes "
            "counter-clockwise; unsimplified"
        ),
        "derived_by": "review/autozone-z0/derive_counties.py",
    }
    # One county per line, so a diff of a re-derivation is readable; LF only,
    # and the file is marked -text in .gitattributes so its digest survives a
    # Windows checkout with core.autocrlf=true.
    lines = ["{"]
    for key, value in header.items():
        lines.append(f"{json.dumps(key)}: {json.dumps(value)},")
    lines.append('"counties": [')
    for k, county in enumerate(counties):
        sep = "," if k < len(counties) - 1 else ""
        lines.append(json.dumps(county, separators=(",", ":"), ensure_ascii=True) + sep)
    lines.append("]")
    lines.append("}")
    text = "\n".join(lines) + "\n"
    body = text.encode("ascii")
    json.loads(body)  # the file must parse as written
    output.write_bytes(body)

    print(f"source zip     {zip_path} sha256 {digest} OK")
    print(f"counties       {len(counties)}")
    print(f"rings          {ring_count} (counter-clockwise, i.e. holes: {holes}; open: {open_rings})")
    print(f"vertices       {vertices}")
    print(f"max decimals   {max_dec} (repr of the stored doubles)")
    print(f"output         {output}")
    print(f"output bytes   {len(body)}")
    print(f"output sha256  {hashlib.sha256(body).hexdigest()}")


if __name__ == "__main__":
    main()
