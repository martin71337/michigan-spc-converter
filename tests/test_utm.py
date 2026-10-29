"""The six UTM zone records and their NCAT anchors (work package U1, DESIGN.md #72).

UTM is three zones over Michigan (15N, 16N, 17N) on each of NAD83(2011) and
NATRF2022, computed by the existing transverse Mercator engine
(``michspc.spc.tm``, manual section 3.2) from UTM's defining constants. What
verifies it is external:

* 212 production NCAT responses on NAD83(2011) and 34 beta NCAT pages on
  NATRF2022 (``tests/fixtures/utm_anchors.py``), held at NCAT's printed digit,
  forward and inverse, through the PUBLIC conversion path;
* for zone 15, which no anchor falls in, the meridian-shift identity (zone 15
  is zone 16 moved six degrees west, nothing else) and three PROJ values
  frozen as literals, a third opinion only.

Every tolerance is NCAT's printed half-unit plus float slack, stated where it
is used: NCAT prints northing and easting to 0.001 m, convergence to 0.01",
and the scale factor to 8 decimals (production) or 9 (beta).
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
from pathlib import Path

import pytest

from michspc.spc import convert, zones as zones_module
from michspc.spc.ellipsoid import GRS80
from michspc.spc.frames import NAD83_2011, NATRF2022
from michspc.spc.units import METERS
from michspc.spc.zones import (
    ALL_ZONES,
    SPCS83_ZONES,
    SPCS2022_ZONES,
    UTM_SYSTEM,
    UTM_ZONES,
    TransverseMercatorDef,
    ZoneRegistryError,
    zone_by_code,
)
from tests.fixtures.utm_anchors import NAD83_2011_ANCHORS, NATRF2022_ANCHORS

REPO_ROOT = Path(__file__).resolve().parent.parent
ALL_ANCHORS = NAD83_2011_ANCHORS + NATRF2022_ANCHORS

NE_TOLERANCE_M = 0.0005 + 1e-9
"""Half of NCAT's printed 0.001 m, plus float slack."""

CONVERGENCE_TOLERANCE_ARCSEC = 0.005 + 1e-9
"""Half of NCAT's printed 0.01", plus float slack."""


def _scale_tolerance(printed: str) -> float:
    """Half a unit in the last place NCAT printed, plus float slack: 5e-9 for
    production's 8 decimals, 5e-10 for beta's 9."""
    decimals = len(printed.split(".")[1])
    return 0.5 * 10.0**-decimals + 1e-12


def _dms_to_degrees(text: str) -> float:
    """NCAT's signed 'DD MM SS.ss' (e.g. '-00 12 34.56', '+01 01 19.08')."""
    parts = text.split()
    sign = -1.0 if parts[0].startswith("-") else 1.0
    return sign * (abs(float(parts[0])) + float(parts[1]) / 60.0 + float(parts[2]) / 3600.0)


def _zone_for(anchor):
    """The registry zone an anchor is in: NCAT's zone number on the anchor's frame."""
    suffix = "" if anchor.frame == NAD83_2011.code else "-2022"
    zone = zone_by_code(f"{anchor.zone}N{suffix}")
    assert zone.frame.code == anchor.frame
    return zone


def _anchor_id(anchor) -> str:
    return Path(anchor.capture).name


# ==========================================================================
# The records.
# ==========================================================================


def test_six_utm_records_three_zones_on_each_frame_in_offer_order():
    """NAD83(2011) 15N, 16N, 17N, then NATRF2022 15N, 16N, 17N (plan D5, D6)."""
    assert [(z.code, z.frame) for z in UTM_ZONES] == [
        ("15N", NAD83_2011),
        ("16N", NAD83_2011),
        ("17N", NAD83_2011),
        ("15N-2022", NATRF2022),
        ("16N-2022", NATRF2022),
        ("17N-2022", NATRF2022),
    ]
    assert [z.abbrev for z in UTM_ZONES] == [
        "UTM15N", "UTM16N", "UTM17N", "UTM15N-2022", "UTM16N-2022", "UTM17N-2022",
    ]
    # EPSG's own name form, frame first, so a cell printing the name alone
    # names the frame.
    assert [z.name for z in UTM_ZONES] == [
        "NAD83(2011) / UTM zone 15N",
        "NAD83(2011) / UTM zone 16N",
        "NAD83(2011) / UTM zone 17N",
        "NATRF2022 / UTM zone 15N",
        "NATRF2022 / UTM zone 16N",
        "NATRF2022 / UTM zone 17N",
    ]
    assert all(z.system == UTM_SYSTEM == "UTM" for z in UTM_ZONES)


@pytest.mark.parametrize("zone", UTM_ZONES, ids=lambda z: z.code)
def test_every_utm_record_carries_utms_defining_constants(zone):
    """UTM's definition, read from EPSG v12.029 conversions 16015-16017: central
    meridian 6z - 183 (-93, -87, -81 for 15, 16, 17), scale 0.9996, false easting
    500,000 m, false northing 0 m at the equator."""
    number = int(zone.code[:2])
    expected_meridian = {15: -93.0, 16: -87.0, 17: -81.0}[number]
    assert zone.definition == TransverseMercatorDef(
        lat_grid_origin=0.0,
        lon_origin=expected_meridian,
        k_origin=0.9996,
        northing_grid_origin=0.0,
        easting_origin=500000.0,
    )
    assert zone.allowed_units == (METERS,)
    assert zone.easting_range_m == (100000.0, 900000.0)
    assert (zone.lon_min, zone.lon_max) == (expected_meridian - 3.0, expected_meridian + 3.0)
    assert (zone.lat_min, zone.lat_max) == (41.6, 48.4)
    conversion = {15: "16015", 16: "16016", 17: "16017"}[number]
    assert f"EPSG {conversion} ('UTM zone {number}N')" in zone.citation
    assert "DMA Technical Manual 8358.2" in zone.citation
    assert "v12.029" in zone.citation


def test_all_zones_is_the_three_tuples_in_order():
    assert ALL_ZONES == SPCS83_ZONES + SPCS2022_ZONES + UTM_ZONES
    assert len(ALL_ZONES) == 3 + 19 + 6 == 28


def test_the_band_check_refuses_a_band_off_its_meridian():
    """The import-time check, fed a zone whose band belongs to the next zone."""
    import dataclasses

    bad = dataclasses.replace(UTM_ZONES[1], lon_min=-84.0, lon_max=-78.0)
    with pytest.raises(ZoneRegistryError, match="not the six degrees centred"):
        zones_module._check_utm_bands_match_their_meridians((bad,))
    zones_module._check_utm_bands_match_their_meridians(UTM_ZONES)


# ==========================================================================
# The fixture is its source.
# ==========================================================================


def _generator():
    spec = importlib.util.spec_from_file_location(
        "build_anchor_fixture", REPO_ROOT / "review/utm-u0/build_anchor_fixture.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_anchor_counts_and_zones():
    """212 production, 34 beta; zones 16 and 17 on NAD83, 16 on NATRF2022; none in 15."""
    assert len(NAD83_2011_ANCHORS) == 212
    assert len(NATRF2022_ANCHORS) == 34
    assert {a.zone for a in NAD83_2011_ANCHORS} == {16, 17}
    assert {a.zone for a in NATRF2022_ANCHORS} == {16}
    assert sum(a.zone == 17 for a in NAD83_2011_ANCHORS) == 31
    assert all(a.frame == "NAD83(2011)" for a in NAD83_2011_ANCHORS)
    assert all(a.frame == "NATRF2022" for a in NATRF2022_ANCHORS)


@pytest.mark.parametrize("anchor", ALL_ANCHORS, ids=_anchor_id)
def test_every_anchor_is_its_raw_capture_reread(anchor):
    """Re-hash the committed bytes, re-parse them with the generator's own rule."""
    raw = (REPO_ROOT / anchor.capture).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == anchor.sha256, "capture altered"
    assert _generator().parse_capture(anchor.capture, raw) == tuple(anchor[2:])


def test_the_generator_finds_exactly_the_fixtures_anchors():
    """No capture with a UTM result is left out of the fixture, and none added."""
    gen = _generator()
    found = set()
    for path in sorted((REPO_ROOT / gen.PROBE).iterdir()):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if not (rel.endswith(".json") or (rel.endswith(".html") and "spcs2022" in rel)):
            continue
        if gen.parse_capture(rel, path.read_bytes()) is not None:
            found.add(rel)
    assert found == {a.capture for a in ALL_ANCHORS}


def test_shared_captures_agree_with_the_autozone_fixtures_digests():
    """Where the Auto zone fixture pins the same raw file, the digests agree."""
    from tests.fixtures.autozone_anchors import ANCHORS

    pinned = {a.capture: a.sha256 for a in ANCHORS}
    shared = [a for a in ALL_ANCHORS if a.capture in pinned]
    assert shared, "expected some overlap with the Auto zone fixture"
    for anchor in shared:
        assert pinned[anchor.capture] == anchor.sha256


# ==========================================================================
# Forward and inverse against NCAT, through the public path.
# ==========================================================================


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", ALL_ANCHORS, ids=_anchor_id)
def test_forward_matches_ncat(anchor):
    zone = _zone_for(anchor)
    frame = NAD83_2011 if anchor.frame == NAD83_2011.code else NATRF2022
    result = convert.project_point(
        float(anchor.latitude), float(anchor.longitude), frame, zone
    )
    assert result.target_northing == pytest.approx(float(anchor.northing), abs=NE_TOLERANCE_M)
    assert result.target_easting == pytest.approx(float(anchor.easting), abs=NE_TOLERANCE_M)
    assert result.target_scale_factor == pytest.approx(
        float(anchor.scale_factor), abs=_scale_tolerance(anchor.scale_factor)
    )
    assert result.target_convergence * 3600.0 == pytest.approx(
        _dms_to_degrees(anchor.convergence) * 3600.0, abs=CONVERGENCE_TOLERANCE_ARCSEC
    )


def _ground_offset_m(lat1, lon1, lat2, lon2) -> float:
    """Distance between two nearby positions on GRS 80, metres (local radii)."""
    phi = math.radians(lat1)
    w = math.sqrt(1.0 - GRS80.e2 * math.sin(phi) ** 2)
    meridian = GRS80.a * (1.0 - GRS80.e2) / w**3
    prime_vertical = GRS80.a / w
    dn = math.radians(lat2 - lat1) * meridian
    de = math.radians(lon2 - lon1) * prime_vertical * math.cos(phi)
    return math.hypot(dn, de)


INVERSE_TOLERANCE_M = 0.0005 * math.sqrt(2.0) / 0.9996 + 2e-5
"""Derived: NCAT's printed northing and easting are each within 0.0005 m of the
true grid position, so the printed pair is within 0.0005*sqrt(2) m of it on the
grid, which is at most that over the smallest UTM scale (0.9996) on the ground.
The 2e-5 m covers NCAT printing the latitude and longitude to 1e-10 degree
(about 1.1e-5 m)."""


INVERSE_SCALE_SERIES_SLACK = 3e-10
"""MEASURED, not assumed (work package U1): at the same position, the manual's
inverse scale series (section 3.24, k from Q to Q^4) and its forward series
(3.23, k from L to L^4) differ by up to 2.42e-10 across all 246 anchors, because
a UTM zone is far wider than the SPCS zones those series were written for. That
is 0.0002 ppm - nothing to a surveyor - but it is half of beta NCAT's printed
9th decimal, so the inverse's scale check carries it on top of the printed
half-unit. The forward check carries no such slack."""


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", ALL_ANCHORS, ids=_anchor_id)
def test_inverse_matches_ncat(anchor):
    """NCAT's printed grid coordinate converted back lands on NCAT's position,
    and the convergence and scale there are NCAT's printed values."""
    zone = _zone_for(anchor)
    result = convert.zone_to_geodetic(
        float(anchor.northing), float(anchor.easting), zone, zone.frame
    )
    offset = _ground_offset_m(
        float(anchor.latitude), float(anchor.longitude), result.latitude, result.longitude
    )
    assert offset <= INVERSE_TOLERANCE_M
    assert result.source_scale_factor == pytest.approx(
        float(anchor.scale_factor),
        abs=_scale_tolerance(anchor.scale_factor) + INVERSE_SCALE_SERIES_SLACK,
    )
    assert result.source_convergence * 3600.0 == pytest.approx(
        _dms_to_degrees(anchor.convergence) * 3600.0, abs=CONVERGENCE_TOLERANCE_ARCSEC
    )


# ==========================================================================
# Zone 15: no NCAT anchor falls in it.
# ==========================================================================

ZONE_15_POINTS = ((46.45, -90.40), (46.55, -90.20), (46.40, -90.05))
"""Western Gogebic County, west of 90 W: Michigan's part of zone 15."""


@pytest.mark.parametrize("frame", (NAD83_2011, NATRF2022), ids=lambda f: f.code)
@pytest.mark.parametrize("latitude, longitude", ZONE_15_POINTS)
def test_zone_15_is_zone_16_moved_six_degrees_west(frame, latitude, longitude):
    """The identity that carries zone 16's 215 anchors to zone 15: every defining
    constant is the same but the central meridian, so a point lambda east of
    -93 in zone 15 has exactly the coordinates of a point lambda east of -87 in
    zone 16. To 1e-9 m - float rounding of lambda + 6 only."""
    suffix = "" if frame is NAD83_2011 else "-2022"
    z15, z16 = zone_by_code(f"15N{suffix}"), zone_by_code(f"16N{suffix}")
    a = convert.project_point(latitude, longitude, frame, z15)
    b = convert.project_point(latitude, longitude + 6.0, frame, z16)
    assert abs(a.target_northing - b.target_northing) <= 1e-9
    assert abs(a.target_easting - b.target_easting) <= 1e-9
    assert abs(a.target_scale_factor - b.target_scale_factor) <= 1e-15
    assert abs(a.target_convergence - b.target_convergence) <= 1e-12


PROJ_ZONE_15 = (
    # (latitude, longitude, northing, easting): PROJ 9.8.1 with EPSG dataset
    # v12.029, EPSG:6318 -> EPSG:6344 ("NAD83(2011) / UTM zone 15N"), computed
    # 2026-10-29 for work package U1. A THIRD OPINION, not NGS truth.
    (46.45, -90.40, 5147332.353092, 699682.325595),
    (46.55, -90.20, 5158968.317052, 714647.735109),
    (46.40, -90.05, 5142721.236982, 726768.932175),
)

PROJ_TOLERANCE_M = 1e-4
"""0.1 mm. U0 measured this engine against PROJ at 0.003 mm within three
degrees of a meridian (review/utm-u0/measure.py); the bound is loose on
purpose, because PROJ is a different series and only a third opinion."""


@pytest.mark.parametrize("latitude, longitude, northing, easting", PROJ_ZONE_15)
def test_zone_15_agrees_with_proj(latitude, longitude, northing, easting):
    result = convert.project_point(latitude, longitude, NAD83_2011, zone_by_code("15N"))
    assert result.target_northing == pytest.approx(northing, abs=PROJ_TOLERANCE_M)
    assert result.target_easting == pytest.approx(easting, abs=PROJ_TOLERANCE_M)


def test_every_zone_agrees_with_proj_over_michigan():
    """Optional: a lattice over Michigan in each NAD83(2011) zone, within four
    degrees of its meridian, against PROJ. Skips when pyproj is absent."""
    pyproj = pytest.importorskip("pyproj")
    for zone, code in zip(UTM_ZONES[:3], (6344, 6345, 6346)):
        transformer = pyproj.Transformer.from_crs("EPSG:6318", f"EPSG:{code}", always_xy=True)
        meridian = zone.definition.lon_origin
        for i in range(9):
            latitude = 41.6 + i * 0.85
            for j in range(9):
                longitude = meridian - 4.0 + j
                if not -90.5 <= longitude <= -82.3:
                    continue
                easting, northing = transformer.transform(longitude, latitude)
                result = convert.project_point(latitude, longitude, NAD83_2011, zone)
                assert abs(result.target_northing - northing) <= PROJ_TOLERANCE_M
                assert abs(result.target_easting - easting) <= PROJ_TOLERANCE_M


def test_the_inverse_scale_series_slack_is_what_was_measured():
    """The slack above is a measurement, so it is held as one: the inverse and
    forward scale series agree at every anchor's own inverse position to within
    it, and the disagreement is real (above 2e-10), so the slack is not padding."""
    worst = 0.0
    for anchor in ALL_ANCHORS:
        zone = _zone_for(anchor)
        back = convert.zone_to_geodetic(
            float(anchor.northing), float(anchor.easting), zone, zone.frame
        )
        forward = convert.project_point(back.latitude, back.longitude, zone.frame, zone)
        worst = max(worst, abs(back.source_scale_factor - forward.target_scale_factor))
    assert 2e-10 < worst <= INVERSE_SCALE_SERIES_SLACK
