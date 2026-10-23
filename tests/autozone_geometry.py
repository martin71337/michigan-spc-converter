"""Geometry the Auto zone suite measures with - never the program's own code.

Distances from a position to county lines, in metres, used to prove each frozen
NCAT anchor lies OUTSIDE the boundary bands where NCAT disagrees with itself
and with the county sources (RECON.md section 5.3): at least 50 m from any
zone line on land, 1 km in water and outside Michigan.

The distance is planar in a local frame at the anchor's latitude - metres per
degree from the GRS 80 meridian and prime-vertical radii - which over the
kilometre windows used here is accurate to far better than a metre, and a
metre is all a 50 m band needs.

Also: the land/water classifier (NGS's own land-only SPCS2022 polygons) and a
plain even-odd point-in-polygon written separately from ``michspc``'s, so the
suite's independent recomputations do not lean on the code under test.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COUNTY_FILE = REPO_ROOT / "data" / "mi_counties_tiger2025.json"
NGS_POLYGONS = REPO_ROOT / "review" / "autozone-r0" / "raw" / "ngs_fs" / "mi_4269.json"
NGS_POLYGONS_SHA256 = "658c4ead203c9ed2a727a29aee8d88ecc834a750cb1c135a83ef710c7d3f2099"

LAND_BAND_M = 50.0
WATER_BAND_M = 1000.0


def metres_per_degree(latitude: float) -> tuple[float, float]:
    """(metres per degree of latitude, per degree of longitude), GRS 80."""
    a, f = 6378137.0, 1 / 298.257222101
    e2 = f * (2 - f)
    s = math.sin(math.radians(latitude))
    w = math.sqrt(1 - e2 * s * s)
    meridian = a * (1 - e2) / w**3
    prime_vertical = a / w
    return (
        math.radians(1) * meridian,
        math.radians(1) * prime_vertical * math.cos(math.radians(latitude)),
    )


def segment_distance_m(lat, lon, a, b) -> float:
    """Metres from (lat, lon) to the segment a-b; a, b are (lon, lat)."""
    my, mx = metres_per_degree(lat)
    ax, ay = (a[0] - lon) * mx, (a[1] - lat) * my
    bx, by = (b[0] - lon) * mx, (b[1] - lat) * my
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0.0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
    return math.hypot(ax + t * dx, ay + t * dy)


@lru_cache(maxsize=1)
def county_document() -> dict:
    return json.loads(COUNTY_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def edges_with_owners() -> tuple[tuple[tuple, tuple, frozenset], ...]:
    """Every distinct county edge: (a, b, the FIPS codes that use it).

    An edge used by one county is on Michigan's outline (the state, Great
    Lakes water and international boundary); by two, a shared county line.
    """
    owners: dict[frozenset, set] = {}
    ends: dict[frozenset, tuple] = {}
    for county in county_document()["counties"]:
        for ring in county["rings"]:
            for a, b in zip(ring[:-1], ring[1:]):
                key = frozenset((tuple(a), tuple(b)))
                owners.setdefault(key, set()).add(county["fips"])
                ends[key] = (tuple(a), tuple(b))
    return tuple((ends[k][0], ends[k][1], frozenset(v)) for k, v in owners.items())


def edge_use_counts() -> Counter:
    uses: Counter = Counter()
    for county in county_document()["counties"]:
        for ring in county["rings"]:
            for a, b in zip(ring[:-1], ring[1:]):
                uses[frozenset((tuple(a), tuple(b)))] += 1
    return uses


def nearest_distance_m(lat, lon, edges, window_m: float) -> float:
    """Distance to the nearest of ``edges`` (a, b) - or ``window_m`` if none is
    within that window (only "at least this far" matters to a band test)."""
    my, mx = metres_per_degree(lat)
    dlat, dlon = window_m / my, window_m / mx
    best = window_m
    for a, b in edges:
        if max(a[1], b[1]) < lat - dlat or min(a[1], b[1]) > lat + dlat:
            continue
        if max(a[0], b[0]) < lon - dlon or min(a[0], b[0]) > lon + dlon:
            continue
        best = min(best, segment_distance_m(lat, lon, a, b))
    return best


def plain_even_odd(rings, lon, lat) -> bool:
    """Even-odd point-in-polygon, written independently of michspc.spc.autozone
    (standard crossing test, not the program's canonical-edge form)."""
    inside = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring[:-1], ring[1:]):
            if (y1 > lat) != (y2 > lat):
                x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
                if lon < x:
                    inside = not inside
    return inside


@lru_cache(maxsize=1)
def ngs_zone_polygons() -> tuple[tuple[str, tuple, tuple], ...]:
    """NGS's 18 land-only LDP polygons: (zone code, bbox, rings)."""
    document = json.loads(NGS_POLYGONS.read_text(encoding="utf-8"))
    out = []
    for feature in document["features"]:
        rings = tuple(tuple(tuple(p) for p in r) for r in feature["geometry"]["rings"])
        xs = [p[0] for r in rings for p in r]
        ys = [p[1] for r in rings for p in r]
        out.append(
            (feature["attributes"]["ZoneCode"], (min(xs), min(ys), max(xs), max(ys)), rings)
        )
    return tuple(out)


def ngs_land_zones(lon, lat) -> list[str]:
    """The NGS LDP polygons (land only) that contain the point."""
    hits = []
    for code, (x0, y0, x1, y1), rings in ngs_zone_polygons():
        if x0 <= lon <= x1 and y0 <= lat <= y1 and plain_even_odd(rings, lon, lat):
            hits.append(code)
    return hits
