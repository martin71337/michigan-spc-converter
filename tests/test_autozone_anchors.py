"""Auto zone against NGS NCAT's own zone picks, frozen outside the boundary bands.

NGS beta: the SPCS2022 anchors are beta NCAT's answers (re-freeze:
docs/REFREEZE-NSRS.md). Each anchor's raw NCAT response is re-hashed and its
zone re-read from the response itself, so the expected value is NCAT's, not
the fixture's transcription of it. Each anchor's distance to the nearest zone
line is re-measured here and must clear the band (50 m on land, 1 km in water
and outside), because inside the bands NCAT disagrees with itself and with the
county sources (RECON.md section 5.3) and an "anchor" there would be a coin.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pytest

from michspc.fileio import counties as county_file
from michspc.spc import autozone_spcs83, autozone_spcs2022, zones
from michspc.spc.autozone import AutoZoneOutsideError, AutoZoneSystem, zone_for
from tests import autozone_geometry as geo
from tests.fixtures.autozone_anchors import ANCHORS, EXCLUDED, NCAT_SELF_DISAGREEMENT

REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = {"SPCS 83": AutoZoneSystem.SPCS83, "SPCS2022": AutoZoneSystem.SPCS2022}


@pytest.fixture(scope="module")
def shipped():
    return county_file.load_counties()


def ncat_zone_from_capture(system: str, raw: bytes) -> str | None:
    """NCAT's zone, read out of its own response.

    SPCS 83: the production REST JSON's ``spcZone``. SPCS2022: the beta web
    app's "Converted Coordinate" panel, its ``Zone`` row - the same parse as
    review/autozone-r0/probe_ncat.py.
    """
    if system == "SPCS 83":
        return json.loads(raw).get("spcZone")
    text = re.sub(r"<[^>]+>", "\n", raw.decode("utf-8", "replace"))
    text = re.sub(r"\n\s*\n+", "\n", text)
    j = text.find("Converted Coordinate")
    assert j >= 0, "no result panel in the capture"
    m = re.search(r"\nZone\n([^\n]*)", text[j : j + 3000])
    return m.group(1).replace("\xa0", " ").strip() if m else None


def code_of(ncat_zone: str | None) -> str | None:
    # 'MI S-2113' -> '2113'; 'MI L45G-261008 (Multizone complete)' -> '261008';
    # another state's zone ('OH N-3401') or 'N/A' -> None.
    if not ncat_zone or not ncat_zone.startswith("MI "):
        return None
    return ncat_zone.split("-")[-1].split(" ")[0]


@lru_cache(maxsize=None)
def other_zone_edges(system: str, zone_code: str):
    """County edges beyond which a point is NOT in ``zone_code``: every shared
    edge whose two counties are not both wholly that zone, plus Michigan's
    outline. Keweenaw counts as both 261016 and 261018 for SPCS2022 (the
    parallel is measured separately)."""
    if system == "SPCS 83":
        zone_of = {f: {z.code} for f, z in autozone_spcs83.SPCS83_ZONE_BY_FIPS.items()}
    else:
        zone_of = {f: {z.code} for f, z in autozone_spcs2022.LDP_ZONE_BY_FIPS.items()}
        zone_of[autozone_spcs2022.KEWEENAW_FIPS] = {"261016", "261018"}
    edges = []
    for a, b, owners in geo.edges_with_owners():
        if len(owners) == 1 or set().union(*(zone_of[f] for f in owners)) != {zone_code}:
            edges.append((a, b))
    return tuple(edges)


def measured_distance_m(anchor) -> float:
    if anchor.expected is None:
        outline = [(a, b) for a, b, o in geo.edges_with_owners() if len(o) == 1]
        return geo.nearest_distance_m(anchor.latitude, anchor.longitude, outline, 20000.0)
    d = geo.nearest_distance_m(
        anchor.latitude, anchor.longitude, other_zone_edges(anchor.system, anchor.expected), 20000.0
    )
    if anchor.system == "SPCS2022" and anchor.expected in ("261016", "261018"):
        my, _ = geo.metres_per_degree(anchor.latitude)
        d = min(d, abs(anchor.latitude - autozone_spcs2022.ISLE_ROYALE_SPLIT_LATITUDE) * my)
    return d


def band_for(category: str) -> float:
    return geo.LAND_BAND_M if category == "land" else geo.WATER_BAND_M


@pytest.mark.parametrize("anchor", ANCHORS, ids=lambda a: f"{a.system}|{a.tag}")
def test_auto_zone_matches_ncat(anchor, shipped):
    raw = (REPO_ROOT / anchor.capture).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == anchor.sha256, "capture altered"
    ncat = ncat_zone_from_capture(anchor.system, raw)
    assert ncat == anchor.ncat_zone
    assert code_of(ncat) == anchor.expected

    system = SYSTEMS[anchor.system]
    if anchor.expected is None:
        with pytest.raises(AutoZoneOutsideError):
            zone_for(anchor.latitude, anchor.longitude, system, shipped)
    else:
        assignment = zone_for(anchor.latitude, anchor.longitude, system, shipped)
        assert assignment.zone.code == anchor.expected
        assert assignment.zone is zones.zone_by_code(anchor.expected)


@pytest.mark.parametrize("anchor", ANCHORS, ids=lambda a: f"{a.system}|{a.tag}")
def test_every_anchor_is_outside_the_boundary_band(anchor):
    if anchor.expected is not None:
        on_land = bool(geo.ngs_land_zones(anchor.longitude, anchor.latitude))
        assert anchor.category == ("land" if on_land else "water")
    else:
        assert anchor.category == "outside"
    d = measured_distance_m(anchor)
    assert d >= band_for(anchor.category), f"{d:.1f} m"
    assert abs(d - anchor.distance_m) < 0.5


def test_coverage_every_zone_has_an_interior_land_anchor():
    for system, era in (("SPCS 83", zones.SPCS83_ZONES), ("SPCS2022", zones.SPCS2022_ZONES[1:])):
        land = {a.expected for a in ANCHORS if a.system == system and a.category == "land"}
        assert land == {z.code for z in era}, system
    # ...and every county has one, in both systems (the deepest-land points).
    for system in SYSTEMS:
        tags = {a.tag for a in ANCHORS if a.system == system and a.tag.startswith("COUNTY ")}
        assert len(tags) == 83


def test_coverage_water_keweenaw_both_sides_and_outside():
    counts = Counter((a.system, a.category) for a in ANCHORS)
    assert counts == {
        ("SPCS 83", "land"): 85,
        ("SPCS2022", "land"): 85,
        ("SPCS 83", "water"): 32,
        ("SPCS2022", "water"): 31,
        ("SPCS 83", "outside"): 7,
        ("SPCS2022", "outside"): 7,
    }
    # The 14 recon water points where "county's zone" and "nearest land's zone"
    # disagree (RECON.md section 3): NCAT follows the county; so must Auto.
    water14 = [a for a in ANCHORS if a.tag.startswith("WATER ")]
    assert {a.system for a in water14} == {"SPCS 83", "SPCS2022"}
    assert len(water14) == 26  # 13 each: one of the 14 is inside the band
    # Keweenaw water either side of 47.65 N, well clear of it.
    split = autozone_spcs2022.ISLE_ROYALE_SPLIT_LATITUDE
    keweenaw = [a for a in ANCHORS if a.system == "SPCS2022" and a.category == "water" and a.expected in ("261016", "261018")]
    south = [a for a in keweenaw if a.latitude < split]
    north = [a for a in keweenaw if a.latitude > split]
    assert all(a.expected == "261016" for a in south) and len(south) >= 4
    assert all(a.expected == "261018" for a in north) and len(north) >= 8
    # Outside: another state's zone, and Canada (N/A), both refused.
    outside = [a for a in ANCHORS if a.category == "outside"]
    assert any(a.ncat_zone == "N/A" for a in outside)
    assert any(a.ncat_zone and a.ncat_zone[:2] in ("OH", "IN", "WI") for a in outside)


def test_every_excluded_capture_is_really_inside_its_band():
    # Nothing captured is dropped silently: each exclusion is re-measured and
    # must be inside the band it was excluded for.
    assert len(EXCLUDED) == 7
    for row in EXCLUDED:
        tag, system, lat, lon, category, ncat_zone, expected, capture, sha, distance, reason = row
        anchor = type(ANCHORS[0])(tag, system, lat, lon, category, ncat_zone, expected, capture, sha, distance)
        assert measured_distance_m(anchor) < band_for(category), tag


def test_ncats_self_disagreement_points_are_listed_and_are_not_anchors():
    assert len(NCAT_SELF_DISAGREEMENT) == 12
    anchored = {(round(a.latitude, 6), round(a.longitude, 6)) for a in ANCHORS}
    for _system, _tag, lat, lon, _zone, capture in NCAT_SELF_DISAGREEMENT:
        assert (REPO_ROOT / capture).is_file()
        assert (round(lat, 6), round(lon, 6)) not in anchored
        # All within 50 m of a county line: inside the land band.
        edges = [(a, b) for a, b, o in geo.edges_with_owners() if len(o) == 2]
        assert geo.nearest_distance_m(lat, lon, edges, 50.0) < 50.0


def test_the_fixture_carries_the_beta_token():
    source = (REPO_ROOT / "tests" / "fixtures" / "autozone_anchors.py").read_text(encoding="utf-8")
    assert "NGS beta" in source
