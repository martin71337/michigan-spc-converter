"""The shipped Michigan county polygons: the only reader of the county file.

``data/mi_counties_tiger2025.json`` holds Michigan's 83 counties as the US
Census Bureau's TIGER/Line 2025 county shapefile draws them - water-extended
into the Great Lakes, unsimplified, every ring and vertex in TIGER's own order,
every coordinate the shapefile's own double (owner's decision O1,
docs/PLAN-options-autozone.md). It is a DERIVED serialization, written by
``review/autozone-z0/derive_counties.py`` from the zip that script
authenticates, and it is what Auto zone tests a position against
(``michspc.spc.autozone``).

**Authenticated on every load, as the NGS grids are** (``geoid.py``): the
whole file is hashed against the digest pinned here before a byte of it is
parsed, then its structure is checked - the format tag, 83 counties, unique
FIPS codes and names, every ring closed and made of finite coordinates inside
Michigan's neighbourhood - and finally its counties are joined against both
zone tables, which must name exactly the same FIPS codes with exactly the same
county names. Each check refuses by name. A county file that fails any of them
is never used: a wrong county polygon assigns a wrong zone with nothing
downstream to notice.

File layout (one JSON object; LF line endings, one county per line, marked
``-text`` in ``.gitattributes`` so a Windows checkout cannot move its digest):

    "format":       "mcx-county-polygons/1"
    "source", "selection", "coordinates", "rings", "derived_by":  provenance text
    "counties":     [{"fips": "26001", "name": "Alcona",
                      "namelsad": "Alcona County",
                      "rings": [[[lon, lat], ...], ...]}, ...]   sorted by FIPS

Longitude negative west, NAD83 geographic, as TIGER stores it.

Packaging (work package Z5): this file must ship under ``data/`` beside the
NGS grids, and this module must be importable in the frozen bundle.
"""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

from michspc.fileio import ngs_grid
from michspc.spc.autozone import (
    AutoZoneDataError,
    County,
    CountySet,
    require_tables_cover,
)

DATA_DIR = ngs_grid.shipped_data_directory()

COUNTIES_FILENAME = "mi_counties_tiger2025.json"
COUNTIES_BYTES = 1_659_316
COUNTIES_SHA256 = "53664dd816375b407c5269cabde565fc89d76e0a3f3ed320fb264240b49f33c3"
"""SHA-256 of the file ``derive_counties.py`` wrote from
tl_2025_us_county.zip (SHA-256
9c6e9d9076abce2670d1de255de3710c35ecca00a7005d88e012dec52d95f763), 2026-10-22."""

COUNTIES_FORMAT = "mcx-county-polygons/1"
COUNTY_COUNT = 83
"""Michigan's counties: MCL 54.231's 15 + 27 + 41."""

COUNTIES_SOURCE = "US Census TIGER/Line 2025 counties"
"""How a refusal and the job record name the county data."""

# Michigan's neighbourhood, generously: TIGER's Michigan counties span about
# 41.70-48.31 N and 90.42-82.12 W (measured from the file). A vertex outside
# this box is not a Michigan county line, whatever else it is.
_LAT_RANGE = (41.0, 49.0)
_LON_RANGE = (-91.0, -82.0)


class CountyDataError(Exception):
    """The shipped county file could not be read, or is not the file pinned."""


def _refuse(path: Path, problem: str) -> CountyDataError:
    return CountyDataError(
        f"The county file {path} cannot be used: {problem}. Auto zone picks a "
        f"zone from these polygons, so a wrong one would assign a wrong zone "
        f"with nothing downstream to notice; it is refused instead. The file "
        f"ships with the program - reinstall if it has been altered."
    )


def _coordinate(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _parse_county(path: Path, index: int, record: object) -> County:
    if not isinstance(record, dict):
        raise _refuse(path, f"county entry {index} is not an object")
    fips, name, rings = record.get("fips"), record.get("name"), record.get("rings")
    if not (isinstance(fips, str) and len(fips) == 5 and fips.isdigit() and fips.startswith("26")):
        raise _refuse(path, f"county entry {index} has FIPS {fips!r}, not a Michigan (26xxx) code")
    if not (isinstance(name, str) and name.strip() == name and name):
        raise _refuse(path, f"county {fips} has the name {name!r}")
    if not (isinstance(rings, list) and rings):
        raise _refuse(path, f"{name} County ({fips}) has no rings")
    parsed = []
    for r, ring in enumerate(rings):
        if not (isinstance(ring, list) and len(ring) >= 4):
            raise _refuse(
                path, f"{name} County ({fips}) ring {r} has fewer than 4 vertices"
            )
        vertices = []
        for v, vertex in enumerate(ring):
            if not (isinstance(vertex, list) and len(vertex) == 2):
                raise _refuse(path, f"{name} County ({fips}) ring {r} vertex {v} is not a [lon, lat] pair")
            lon, lat = _coordinate(vertex[0]), _coordinate(vertex[1])
            if lon is None or lat is None:
                raise _refuse(path, f"{name} County ({fips}) ring {r} vertex {v} is not two finite numbers: {vertex!r}")
            if not (_LON_RANGE[0] <= lon <= _LON_RANGE[1] and _LAT_RANGE[0] <= lat <= _LAT_RANGE[1]):
                raise _refuse(
                    path,
                    f"{name} County ({fips}) ring {r} vertex {v} at longitude "
                    f"{lon!r}, latitude {lat!r} is outside Michigan's neighbourhood",
                )
            vertices.append((lon, lat))
        if vertices[0] != vertices[-1]:
            raise _refuse(
                path,
                f"{name} County ({fips}) ring {r} is not closed: it starts at "
                f"{vertices[0]!r} and ends at {vertices[-1]!r}",
            )
        parsed.append(tuple(vertices))
    return County(fips=fips, name=name, rings=tuple(parsed))


def load_counties(path: Path | None = None, verify_checksum: bool = True) -> CountySet:
    """Read, authenticate and check the county file; return the prepared set.

    ``verify_checksum=False`` exists only so the structural checks can be
    exercised against a deliberately altered copy in the suite. The program
    never passes it.
    """
    path = path or DATA_DIR / COUNTIES_FILENAME
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise CountyDataError(
            f"Could not read the county file at {path}: {error}. This file "
            f"ships with the program; if it is missing the installation is "
            f"incomplete."
        ) from error

    if verify_checksum:
        digest = hashlib.sha256(raw).hexdigest()
        if digest != COUNTIES_SHA256:
            raise CountyDataError(
                f"{path} does not match the county file this program was "
                f"built against.\n  expected SHA-256 {COUNTIES_SHA256} "
                f"({COUNTIES_BYTES} bytes)\n  found    SHA-256 {digest} "
                f"({len(raw)} bytes)\nZones chosen from unverified county "
                f"lines could be wrong in ways nothing downstream would "
                f"notice, so it is refused."
            )

    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise _refuse(path, f"it is not valid UTF-8 JSON ({error})") from error
    if not isinstance(document, dict) or document.get("format") != COUNTIES_FORMAT:
        raise _refuse(path, f"its format tag is not {COUNTIES_FORMAT!r}")
    records = document.get("counties")
    if not isinstance(records, list):
        raise _refuse(path, "it has no county list")
    if len(records) != COUNTY_COUNT:
        raise _refuse(path, f"it holds {len(records)} counties, not Michigan's {COUNTY_COUNT}")

    counties = [_parse_county(path, i, record) for i, record in enumerate(records)]
    for field_name in ("fips", "name"):
        values = [getattr(c, field_name) for c in counties]
        repeated = sorted({v for v in values if values.count(v) > 1})
        if repeated:
            raise _refuse(path, f"more than one county has the {field_name} {repeated}")

    try:
        county_set = CountySet(counties, source=COUNTIES_SOURCE)
        require_tables_cover(county_set)
    except AutoZoneDataError as error:
        raise _refuse(path, str(error)) from error
    return county_set


@lru_cache(maxsize=1)
def default_counties() -> CountySet:
    """The shipped county set, read and authenticated once per process."""
    return load_counties()
