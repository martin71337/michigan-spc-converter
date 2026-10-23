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


EDGE_CLEARANCE_M = 5.0
"""Samples this close to the county's own line are skipped. NGS's lines sit on
TIGER's to centimetres almost everywhere (RECON.md section 2.2), but not
everywhere: at 43.9107 N 83.9530 W, on the Bay/Arenac line, a grid sample 0.51 m
inside TIGER's Bay is 0.41 m inside NGS's 261005 - the two lines are about
0.9 m apart there. The test is of which zone a county's land is in, not of
NGS's line to the centimetre, so a metre-scale clearance is the honest margin."""


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
