"""The two county -> zone tables, each re-read from the authority it came from.

* SPCS 83: the suite re-reads the captured statute, MCL 54.231(3)-(5), and
  requires every county to be listed in exactly the zone the table gives it
  (the #70 precedent: the suite re-reads the source, so a transcription cannot
  merely agree with a copy of itself).
* SPCS2022: NGS publishes no county list, so the suite re-measures one from
  NGS's own beta zone polygons (captured, digest-pinned): every county's land,
  sampled on a grid, must fall in exactly the zone the table gives it, and
  Keweenaw on the side of 47.65 N that the Isle Royale rule says. NGS beta.

Both tables must hold the ``michspc.spc.zones`` records themselves, by
identity: no zone fact is restated.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
from functools import lru_cache
from pathlib import Path

import pytest

from michspc.spc import autozone_spcs83 as t83
from michspc.spc import autozone_spcs2022 as t22
from michspc.spc import zones
from michspc.spc.autozone import County, PreparedCounty
from tests import autozone_geometry as geo

REPO_ROOT = Path(__file__).resolve().parents[1]
STATUTE = REPO_ROOT / "review" / "autozone-r0" / "raw" / "statute" / "mcl-54-231.html"
STATUTE_SHA256 = "3ed4adaa63a83eb9edd92d9a3efeba873c04c68c2857f16ad3d53833ecf592b8"


# ==========================================================================
# SPCS 83: the statute.
# ==========================================================================


@lru_cache(maxsize=1)
def statute_zones() -> dict[str, list[str]]:
    """{'north': [...], 'central': [...], 'south': [...]} read from the capture."""
    raw = STATUTE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == STATUTE_SHA256, "statute capture changed"
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw.decode("utf-8")))
    text = re.sub(r"\s+", " ", text)
    found = {}
    for match in re.finditer(
        r"The area included in the following counties constitutes the "
        r"(north|central|south) zone: (.*?)\.\s*(?=\(\d\)|History:)",
        text,
    ):
        names = [n.strip() for n in re.split(r",\s*", match.group(2))]
        names = [n[4:] if n.startswith("and ") else n for n in names]
        found[match.group(1)] = names
    return found


def test_the_statute_capture_is_the_pinned_file_and_parses_into_three_zones():
    # The capture is the 1988 text, legislature.mi.gov, 2026-10-22. MCL
    # 54.231(3) lists 15 counties, (4) 27, (5) 41: 83 in all.
    listed = statute_zones()
    assert {k: len(v) for k, v in listed.items()} == {"north": 15, "central": 27, "south": 41}
    every = [n for names in listed.values() for n in names]
    assert len(every) == len(set(every)) == 83
    # Spot values typed from the statute text by hand, first and last of each.
    assert listed["north"][0] == "Gogebic" and listed["north"][-1] == "Mackinac"
    assert listed["central"][0] == "Emmet" and listed["central"][-1] == "Arenac"
    assert listed["south"][0] == "Oceana" and listed["south"][-1] == "Monroe"


def test_every_county_is_in_exactly_the_zone_the_statute_lists_it_in():
    by_zone = {"north": zones.MI_NORTH, "central": zones.MI_CENTRAL, "south": zones.MI_SOUTH}
    statute = {name: by_zone[z] for z, names in statute_zones().items() for name in names}
    table = {
        t83.COUNTY_NAME_BY_FIPS[fips]: zone for fips, zone in t83.SPCS83_ZONE_BY_FIPS.items()
    }
    assert set(table) == set(statute), (sorted(set(table) ^ set(statute)))
    wrong = {name: (table[name].name, statute[name].name) for name in statute if table[name] is not statute[name]}
    assert not wrong, f"table vs statute: {wrong}"


def test_the_spcs83_table_holds_the_registry_records_themselves():
    for zone in t83.SPCS83_ZONE_BY_FIPS.values():
        assert any(zone is z for z in zones.SPCS83_ZONES)
    counts = {z.code: 0 for z in zones.SPCS83_ZONES}
    for zone in t83.SPCS83_ZONE_BY_FIPS.values():
        counts[zone.code] += 1
    assert counts == {"2111": 15, "2112": 27, "2113": 41}


def test_both_tables_and_the_county_file_name_the_same_83_counties():
    document = geo.county_document()
    data = {c["fips"]: c["name"] for c in document["counties"]}
    assert dict(t83.COUNTY_NAME_BY_FIPS) == data
    assert dict(t22.COUNTY_NAME_BY_FIPS) == data


# ==========================================================================
# SPCS2022: NGS's beta polygons.
# ==========================================================================


@lru_cache(maxsize=1)
def ngs_prepared() -> tuple[tuple[str, PreparedCounty], ...]:
    raw = geo.NGS_POLYGONS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == geo.NGS_POLYGONS_SHA256, "NGS capture changed"
    return tuple(
        (code, PreparedCounty.build(County(code, code, rings)))
        for code, _bbox, rings in geo.ngs_zone_polygons()
    )


def ngs_zones_at(lon, lat) -> list[str]:
    return [code for code, polygon in ngs_prepared() if polygon.contains(lon, lat)]


def test_the_ngs_capture_is_the_eighteen_local_zones():
    codes = sorted(code for code, _ in ngs_prepared())
    assert codes == [f"2610{n:02d}" for n in range(1, 19)]


def test_the_ngs_geometry_is_the_native_web_mercator_capture():
    # The recon's measurement was made on the native capture; the outSR=4269
    # one is server-shifted (gate-autozone-1 finding 2) and must not be it.
    assert geo.NGS_POLYGONS.name == "mi_native.json"
    assert geo.NGS_POLYGONS != geo.SHIFTED_4269_POLYGONS
    document = json.loads(geo.NGS_POLYGONS.read_text(encoding="utf-8"))
    assert document["spatialReference"] == {"wkid": 102100, "latestWkid": 3857}


def test_the_inverse_web_mercator_is_the_spherical_formula_with_no_shift():
    # Origin maps to origin; the sphere's quarter-circumference of easting is
    # 90 degrees of longitude; and northing atanh(sin 45 deg) * R is 45 N -
    # the forward formula N = R ln tan(pi/4 + lat/2) evaluated at 45 degrees.
    r = geo.WEB_MERCATOR_RADIUS_M
    assert geo.web_mercator_to_lonlat(0.0, 0.0) == (0.0, 0.0)
    lon, lat = geo.web_mercator_to_lonlat(math.pi * r / 2, r * math.log(math.tan(math.pi * 3 / 8)))
    assert lon == pytest.approx(90.0, abs=1e-12)
    assert lat == pytest.approx(45.0, abs=1e-12)
    # The reviewer's native vertex on the Livingston/Genesee line: it lands on
    # TIGER's six-decimal vertex (-84.021879, 42.778817) to 1e-12 degree. The
    # outSR=4269 counterpart is (-84.021874246, 42.7788087964), ~0.9 m away.
    native = [
        p for _c, _b, rings in geo.ngs_zone_polygons() for r in rings for p in r
        if abs(p[0] + 84.021879) < 1e-9 and abs(p[1] - 42.778817) < 1e-9
    ]
    assert native
    tiger = [
        p for c in geo.county_document()["counties"] for r in c["rings"] for p in r
        if p == [-84.021879, 42.778817]
    ]
    assert tiger


def test_every_internal_ngs_line_lies_on_a_tiger_county_line():
    """The module docstring's figure, re-measured on the geometry tested.

    Every edge two NGS zones share is sampled at its vertices and at most
    100 m apart; each sample must be within LINE_AGREEMENT_M of a TIGER line
    two counties share. Measured 2026-10-23: 11,875 edges, 42,896 samples,
    worst 0.025 m (on the outSR=4269 capture the same measurement gives a
    0.90 m median and 1.08 m worst).
    """
    owners: dict[frozenset, set] = {}
    for code, _bbox, rings in geo.ngs_zone_polygons():
        for r in rings:
            for a, b in zip(r[:-1], r[1:]):
                owners.setdefault(frozenset((a, b)), set()).add(code)
    internal = [tuple(k) for k, v in owners.items() if len(v) == 2 and len(k) == 2]
    assert len(internal) > 10_000

    cell = 0.01
    index: dict[tuple, list] = {}
    for a, b, own in geo.edges_with_owners():
        if len(own) != 2:
            continue
        for i in range(math.floor(min(a[0], b[0]) / cell), math.floor(max(a[0], b[0]) / cell) + 1):
            for j in range(math.floor(min(a[1], b[1]) / cell), math.floor(max(a[1], b[1]) / cell) + 1):
                index.setdefault((i, j), []).append((a, b))

    worst, where, samples = 0.0, None, 0
    for a, b in internal:
        my, mx = geo.metres_per_degree(a[1])
        n = max(1, math.ceil(math.hypot((b[0] - a[0]) * mx, (b[1] - a[1]) * my) / 100.0))
        for k in range(n + 1):
            lon = a[0] + (b[0] - a[0]) * k / n
            lat = a[1] + (b[1] - a[1]) * k / n
            i, j = math.floor(lon / cell), math.floor(lat / cell)
            d = min(
                (
                    geo.segment_distance_m(lat, lon, p, q)
                    for di in (-1, 0, 1)
                    for dj in (-1, 0, 1)
                    for p, q in index.get((i + di, j + dj), ())
                ),
                default=math.inf,
            )
            samples += 1
            if d > worst:
                worst, where = d, (lat, lon)
    assert samples > 40_000
    assert worst <= LINE_AGREEMENT_M, (worst, where)


# The reviewer's counterexample (gate-autozone-1 finding 2): 0.058 m inside
# TIGER's Livingston, on the Livingston (261001) / Genesee (261003) line.
COUNTEREXAMPLE = (42.7787768086129, -84.02422810074192)


def test_the_gate_counterexample_is_livingstons_zone_on_the_native_geometry():
    lat, lon = COUNTEREXAMPLE
    counties = [
        c for c in geo.county_document()["counties"] if geo.plain_even_odd(c["rings"], lon, lat)
    ]
    assert [c["name"] for c in counties] == ["Livingston"]
    shipped = t22.ldp_zone(counties[0]["fips"], lat).code
    assert shipped == "261001"
    assert ngs_zones_at(lon, lat) == [shipped]
    assert geo.ngs_land_zones(lon, lat) == [shipped]


def test_the_shifted_4269_capture_would_fail_the_counterexample():
    # Negative control: the server-shifted capture puts the same point in
    # Genesee's zone. If the helper ever read it, the test above would fail.
    lat, lon = COUNTEREXAMPLE
    hits = [
        code
        for code, (x0, y0, x1, y1), rings in geo.shifted_4269_zone_polygons()
        if x0 <= lon <= x1 and y0 <= lat <= y1 and geo.plain_even_odd(rings, lon, lat)
    ]
    assert hits == ["261003"]


LINE_AGREEMENT_M = 0.03
"""The worst distance from NGS's native internal zone lines to a TIGER county
line, measured 2026-10-23 at 0.025 m (``test_every_internal_ngs_line_lies_on_a_tiger_county_line``
re-measures it); the module docstring states the figure."""

EDGE_CLEARANCE_M = 0.1
"""Samples this close to the county's own line are skipped: over three times
the measured worst NGS-to-TIGER line distance (0.025 m one way, 0.029 m the
other, on the native geometry), so a sample past it is on the same side of
both lines. (An earlier 5 m margin here was sized to a ~0.9 m disagreement
that was the server's WGS 84 -> NAD 83 shift in the ``outSR=4269`` capture,
not NGS's lines - gate-autozone-1 finding 2.)"""


def _land_samples(county: dict, n: int):
    rings = tuple(tuple(tuple(p) for p in r) for r in county["rings"])
    edges = [(a, b) for r in rings for a, b in zip(r[:-1], r[1:])]
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    for i in range(1, n):
        for j in range(1, n):
            lon = min(xs) + (max(xs) - min(xs)) * i / n
            lat = min(ys) + (max(ys) - min(ys)) * j / n
            if not geo.plain_even_odd(rings, lon, lat):
                continue
            if geo.nearest_distance_m(lat, lon, edges, EDGE_CLEARANCE_M) < EDGE_CLEARANCE_M:
                continue
            hits = ngs_zones_at(lon, lat)
            if hits:
                yield lon, lat, hits


def test_each_countys_land_lies_wholly_in_the_zone_the_table_gives_it():
    """RECON.md section 2.2's measurement, re-made from the capture.

    Each county's bounding box is sampled on a grid; every sample inside the
    county AND on land (inside some NGS polygon) must be in exactly one NGS
    zone, and that zone must be the table's (Keweenaw: the Isle Royale rule's
    side of 47.65 N). The grid is finer for Keweenaw so that Isle Royale gets
    land samples of its own.
    """
    wrong = []
    for county in geo.county_document()["counties"]:
        fips = county["fips"]
        n = 60 if fips == t22.KEWEENAW_FIPS else 24
        samples = list(_land_samples(county, n))
        assert len(samples) >= 25, f"{county['name']}: only {len(samples)} land samples"
        sides = set()
        for lon, lat, hits in samples:
            expected = t22.ldp_zone(fips, lat)
            sides.add(expected.code)
            if hits != [expected.code]:
                wrong.append((county["name"], lat, lon, hits, expected.code))
        if fips == t22.KEWEENAW_FIPS:
            assert sides == {"261016", "261018"}, sides
    assert not wrong, wrong[:10]


def test_the_isle_royale_parallel_lies_wholly_in_water():
    # NGS's land polygons: U61K (Isle Royale) entirely north of 47.65 N, U41H
    # (Houghton, which holds the Keweenaw Peninsula) entirely south of it. So
    # the split never cuts land, and no land point depends on the tie rule.
    bbox = {code: box for code, box, _rings in geo.ngs_zone_polygons()}
    split = t22.ISLE_ROYALE_SPLIT_LATITUDE
    assert bbox["261018"][1] > split  # min latitude of Isle Royale's land
    assert bbox["261016"][3] < split  # max latitude of the Houghton zone's land


def test_the_isle_royale_rule_is_the_zone_records_shared_bound():
    # zoneBounds.json (transcribed into zones.py): U41H's north bound and
    # U61K's south bound are both 47.65.
    assert t22.ISLE_ROYALE_ZONE is zones.zone_by_code("261018")
    assert t22.KEWEENAW_MAINLAND_ZONE is zones.zone_by_code("261016")
    assert t22.ISLE_ROYALE_ZONE.lat_min == t22.ISLE_ROYALE_SPLIT_LATITUDE == 47.65
    assert t22.KEWEENAW_MAINLAND_ZONE.lat_max == 47.65


@pytest.mark.parametrize(
    "latitude, code",
    [
        (47.64999999, "261016"),  # just south: mainland zone
        (47.65, "261018"),  # the tie goes north (this program's stated choice)
        (47.65000001, "261018"),
        (48.0, "261018"),  # Isle Royale's land
        (47.47, "261016"),  # the Keweenaw Peninsula
    ],
)
def test_the_isle_royale_rule_at_and_around_the_parallel(latitude, code):
    assert t22.ldp_zone(t22.KEWEENAW_FIPS, latitude).code == code


def test_the_rule_is_keweenaws_alone():
    # Ontonagon (U51B) and Alger (U21E) waters north of 47.65 keep their
    # counties' zones (RECON.md section 2.3, confirmed by NCAT).
    assert t22.ldp_zone("26131", 47.9).code == "261017"
    assert t22.ldp_zone("26003", 47.9).code == "261014"


def test_the_spcs2022_table_never_names_the_statewide_zone():
    statewide = zones.zone_by_code("260001")
    values = set(t22.LDP_ZONE_BY_FIPS.values()) | {t22.ISLE_ROYALE_ZONE}
    assert statewide not in values
    # ...and uses every one of the eighteen local zones, by identity.
    local = [z for z in zones.SPCS2022_ZONES if z is not statewide]
    assert len(local) == 18
    assert all(any(v is z for v in values) for z in local)
    assert all(any(v is z for z in local) for v in values)


def test_the_spcs2022_module_carries_the_beta_token():
    source = (REPO_ROOT / "michspc" / "spc" / "autozone_spcs2022.py").read_text(encoding="utf-8")
    assert "NGS beta" in source
    assert geo.NGS_POLYGONS_SHA256 in source
