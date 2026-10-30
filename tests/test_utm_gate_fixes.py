"""The interim gate over the UTM build (U1-U4 + R1): each finding pinned.

review/gate-utm-interim/output.txt; DESIGN.md #72. Each test is the
reviewer's own counterexample, or the lead's measurement it rests on.

MEDIUM 1  far from its central meridian the manual's transverse Mercator
          series drifts (centimetres at 10 degrees) - the engine now refuses
          beyond tm.DOMAIN_LIMIT_DEGREES, both directions.
MEDIUM 2  a file in one UTM zone declared as another converted silently -
          UTM extents are their band over Michigan, and a UTM job warns on a
          point in no Michigan county.
LOW 3     a UTM job's units line cited the SPCS 83 manual.
LOW 4     the extent warning called Michigan's latitudes the zone's area.
(LOW 1, LOW 2 and LOW 5 are pinned where their text lives:
tests/test_utm_jobs.py, tests/test_utm.py, tests/test_refusal_headline.py.)
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from michspc.fileio import exports, pnezd
from michspc.job import Direction, JobSettings, LongitudeConvention, run
from michspc.spc import projection, tm
from michspc.spc.convert import WarningCode
from michspc.spc.frames import NAD83_2011
from michspc.spc.tm import DOMAIN_LIMIT_DEGREES, TransverseMercatorDomainError
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.zones import (
    MI_CENTRAL,
    MI_SOUTH,
    SPCS2022_ZONES,
    UTM_ZONES,
    TransverseMercatorDef,
    zone_by_code,
)
from tests.conftest import member_text

UTM15 = zone_by_code("15N")
UTM16 = zone_by_code("16N")
UTM17 = zone_by_code("17N")
OUTSIDE = WarningCode.POINT_OUTSIDE_MICHIGAN


def _job(tmp_path: Path, rows: str, **fields):
    """Run and write one job; (result, archive)."""
    base = dict(
        input_path=tmp_path / "in.csv",
        output_directory=tmp_path,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    base.update(fields)
    settings = JobSettings(**base)
    settings.input_path.write_text(rows, encoding="utf-8")
    result = run(settings)
    return result, exports.write_all(result)["archive"]


def _geodetic_to(zone, **extra):
    return dict(
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=zone,
        geodetic_frame=NAD83_2011,
        **extra,
    )


def _zone_to_geodetic(zone):
    return dict(
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=zone,
        target_zone=None,
        geodetic_frame=NAD83_2011,
    )


def _codes(result):
    return [w.code for p in result.points for w in p.warnings]


# ==========================================================================
# MEDIUM 1 - the engine's domain.
# ==========================================================================


def test_the_domain_limit_is_five_degrees():
    """The lead's ruling, on the measurement in tm.DOMAIN_LIMIT_DEGREES's
    docstring: 0.073 mm forward and 0.364 mm inverse at 5.0 degrees, both
    inside the half millimetre NCAT prints."""
    assert DOMAIN_LIMIT_DEGREES == 5.0


def test_the_reviewers_15n_case_refuses_through_the_job(tmp_path):
    """Geodetic 42.0, -82.5 into 15N: 10.5 degrees off. Was written 14.1 mm /
    7.1 mm wrong with a record saying "computed correctly"; now refused,
    naming the point, the distance, the limit, the measured drift and the
    zone that covers it."""
    with pytest.raises(TransverseMercatorDomainError) as refused:
        _job(tmp_path, "2,42.0,-82.5,200,Q\n", **_geodetic_to(UTM15))
    message = str(refused.value)
    assert message.startswith("point 2 (NAD83(2011) / UTM zone 15N): ")
    assert "longitude -82.500000, 10.5000 degrees from the central meridian of zone 15N" in message
    assert "within 5.0 degrees of its central meridian" in message
    assert "19 mm and 177 mm at 10.7 degrees" in message
    assert message.endswith("lies in UTM zone 17N (central meridian -81 degrees); choose that zone.")
    assert not list(tmp_path.glob("*.zip"))


def test_17n_used_at_the_far_west_of_the_upper_peninsula_refuses_inverse():
    """The inverse, from 17N at 90.4 W (9.4 degrees): the position the series
    recovers is past the limit, so no position is returned. The grid
    coordinate is the series' own forward value there."""
    constants = projection.constants_for(UTM17)
    grid = tm._forward_series(46.5, -90.4, constants)
    with pytest.raises(TransverseMercatorDomainError) as refused:
        projection.inverse(grid.northing, grid.easting, UTM17)
    assert "lies in UTM zone 15N" in str(refused.value)


@pytest.mark.parametrize("zone", UTM_ZONES[:3], ids=lambda z: z.code)
def test_the_boundary_is_the_limit_in_both_directions(zone):
    """4.999 degrees converts both ways; 5.001 refuses both ways, east and west."""
    meridian = zone.definition.lon_origin
    constants = projection.constants_for(zone)
    for side in (-1.0, 1.0):
        inside = meridian + side * 4.999
        point = projection.forward(45.0, inside, zone)
        back = projection.inverse(point.northing, point.easting, zone)
        assert back.longitude == pytest.approx(inside, abs=1e-8)

        outside = meridian + side * 5.001
        with pytest.raises(TransverseMercatorDomainError):
            projection.forward(45.0, outside, zone)
        grid = tm._forward_series(45.0, outside, constants)
        with pytest.raises(TransverseMercatorDomainError):
            projection.inverse(grid.northing, grid.easting, zone)


PROJ_16N_EAST_EDGE = (
    # (latitude, longitude, northing, easting): PROJ 9.8.1 with EPSG v12.029,
    # EPSG:6318 -> EPSG:6345 ("NAD83(2011) / UTM zone 16N"), computed
    # 2026-10-29. 82.41 W is Michigan's eastern edge, 4.59 degrees from 16N's
    # meridian - 16N stretched over the whole Lower Peninsula.
    (41.7, -82.41, 4626657.7708, 881960.5773),
    (45.0, -82.41, 4993207.7722, 861762.4846),
)


@pytest.mark.parametrize("latitude, longitude, northing, easting", PROJ_16N_EAST_EDGE)
def test_16n_at_michigans_east_edge_converts_within_half_a_millimetre(
    latitude, longitude, northing, easting
):
    """Inside the domain, both directions, against PROJ (a third opinion; the
    NCAT anchors are tests/test_utm.py's). Measured 0.04 mm forward, 0.18 mm
    inverse."""
    point = projection.forward(latitude, longitude, UTM16)
    assert math.hypot(point.northing - northing, point.easting - easting) < 0.0005
    back = projection.inverse(northing, easting, UTM16)
    north_m = (back.latitude - latitude) * 111_000.0
    east_m = (back.longitude - longitude) * 111_000.0 * math.cos(math.radians(latitude))
    assert math.hypot(north_m, east_m) < 0.0005


def test_no_spcs2022_transverse_mercator_zone_comes_near_the_limit():
    """The limit is the engine's, and it applies to the five SPCS2022 TM zones
    too; none of them reaches it inside NGS's published bounds. Widest:
    261016 (Houghton), 1.29 degrees from its meridian."""
    reaches = {
        zone.code: max(
            abs(zone.lon_min - zone.definition.lon_origin),
            abs(zone.lon_max - zone.definition.lon_origin),
        )
        for zone in SPCS2022_ZONES
        if isinstance(zone.definition, TransverseMercatorDef)
    }
    assert len(reaches) == 5
    assert max(reaches.values()) == pytest.approx(1.29, abs=1e-9)
    assert max(reaches.values()) < DOMAIN_LIMIT_DEGREES


# ==========================================================================
# MEDIUM 2 - the wrong UTM zone.
# ==========================================================================

BLUNDERS = (
    # (name, northing, easting, declared zone, landing longitude). The grid
    # coordinates are the TRUE zone's for a real Michigan point, computed
    # 2026-10-30 by this engine and by PROJ 9.8.1 (EPSG 6345/6346), which
    # agree to every digit shown; the reviewer's three cases.
    #   16N 43.8 N 85.5 W declared 17N -> 79.5 W (Ontario)
    #   17N 42.5 N 83.5 W declared 16N -> 89.5 W (Wisconsin)
    #   16N 46.0 N 87.0 W declared 15N -> 93.0 W (Minnesota)
    ("16N as 17N", "4850753.0408", "620665.0072", UTM17, -79.5),
    ("17N as 16N", "4708321.8101", "294578.8764", UTM16, -89.5),
    ("16N as 15N", "5094047.4920", "500000.0000", UTM15, -93.0),
)


def test_the_blunder_coordinates_are_what_they_claim():
    """The literals above are the true-zone grid coordinates of those three
    Michigan points, to 0.1 mm, by this program's own engine (PROJ agreed
    when they were frozen)."""
    for lat, lon, zone, (_name, northing, easting, _declared, _lands) in zip(
        (43.8, 42.5, 46.0), (-85.5, -83.5, -87.0), (UTM16, UTM17, UTM16), BLUNDERS
    ):
        point = projection.forward(lat, lon, zone)
        assert point.northing == pytest.approx(float(northing), abs=1e-4)
        assert point.easting == pytest.approx(float(easting), abs=1e-4)


@pytest.mark.parametrize(
    "name, northing, easting, declared, lands", BLUNDERS, ids=[b[0] for b in BLUNDERS]
)
def test_a_utm_file_declared_in_the_wrong_zone_warns(
    tmp_path, name, northing, easting, declared, lands
):
    result, archive = _job(
        tmp_path, f"1,{northing},{easting},,P\n", **_zone_to_geodetic(declared)
    )
    point = result.points[0]
    assert point.conversion.longitude == pytest.approx(lands, abs=1e-6)
    outside = [w for w in point.warnings if w.code is OUTSIDE]
    assert len(outside) == 1
    message = outside[0].message
    assert message.startswith("point 1: ")
    assert "lies in no Michigan county" in message
    assert "Great Lakes waters included) - it is outside Michigan." in message
    assert "same 500,000 m false easting" in message
    assert f"Check that {declared.name} is the zone these coordinates are in." in message
    record = member_text(archive, "_README.txt")
    assert "POINTS OUTSIDE MICHIGAN" in record
    assert "None. Every point converted cleanly" not in record


def test_the_right_zone_does_not_warn(tmp_path):
    """The same 16N coordinate declared as 16N: no warning of any kind."""
    _name, northing, easting, _declared, _lands = BLUNDERS[0]
    result, _archive = _job(
        tmp_path, f"1,{northing},{easting},,P\n", **_zone_to_geodetic(UTM16)
    )
    assert _codes(result) == []


def test_a_geodetic_point_outside_michigan_into_utm_warns_on_its_position(tmp_path):
    """Into UTM, the input position itself is what is outside Michigan, so the
    advice is about the latitude and longitude, not the zone."""
    result, _archive = _job(tmp_path, "1,43.5,-87.6,,P\n", **_geodetic_to(UTM16))
    outside = [w for p in result.points for w in p.warnings if w.code is OUTSIDE]
    assert len(outside) == 1
    assert outside[0].message.endswith("it is outside Michigan. Check the latitude and longitude.")


def test_a_state_plane_job_outside_michigan_never_gets_the_utm_warning(tmp_path):
    """UTM jobs only: the same Wisconsin position into Michigan South warns
    on the zone's extent, as it always has, and nothing else."""
    result, _archive = _job(tmp_path, "1,43.5,-87.6,,P\n", **_geodetic_to(MI_SOUTH))
    assert OUTSIDE not in _codes(result)


def test_the_warning_reaches_the_single_point_path():
    """The Single point tab calls job.run with an already-parsed row and no
    file; the county set is loaded for a UTM job there too."""
    _name, northing, easting, declared, _lands = BLUNDERS[0]
    settings = JobSettings(
        input_path=None,
        output_directory=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        **_zone_to_geodetic(declared),
    )
    result = run(settings, source=pnezd.parse_lines([f"1,{northing},{easting},,P\n"]))
    assert OUTSIDE in _codes(result)


def test_utm_extents_are_the_band_over_michigan():
    """15N -90.5 to -90.0, 16N -90.0 to -84.0, 17N -84.0 to -82.3, both frames:
    17N used at 79.5 W and 15N at 93.0 W are outside them."""
    expected = {15: (-90.5, -90.0), 16: (-90.0, -84.0), 17: (-84.0, -82.3)}
    for zone in UTM_ZONES:
        number = int(zone.code[:2])
        assert (zone.lon_min, zone.lon_max) == expected[number]


# ==========================================================================
# LOW 3 - the units line.
# ==========================================================================

UTM_CITATION = "UTM is defined in meters (DMA Technical Manual 8358.2, 1989)"
SPCS83_CITATION = "NOAA Manual NOS NGS 5 publishes SPCS 83 in meters (PDF p. 21)"


def _units_lines(archive) -> tuple[str, str]:
    """The citation under "Units in" and under "Units out"."""
    lines = member_text(archive, "_README.txt").splitlines()
    cited = []
    for heading in ("Units in", "Units out"):
        index = next(i for i, line in enumerate(lines) if line.startswith(heading))
        # The citation is the last indented line of the block.
        block = [lines[index]]
        for line in lines[index + 1 :]:
            if not line.startswith(" " * 19):
                break
            block.append(line)
        cited.append(block[-1].strip())
    return tuple(cited)


def test_a_utm_job_cites_utms_definition_for_its_meters(tmp_path):
    _result, archive = _job(tmp_path, "1,45.0,-86.0,200,P\n", **_geodetic_to(UTM16))
    assert _units_lines(archive) == (UTM_CITATION, UTM_CITATION)


def test_a_mixed_job_cites_each_side_by_its_own_grid(tmp_path):
    """Michigan Central in, UTM out: each side's authority."""
    _result, archive = _job(
        tmp_path, "1,61379.810,6016088.527,200,P\n",
        direction=Direction.ZONE_TO_ZONE, source_zone=MI_CENTRAL, target_zone=UTM16,
    )
    assert _units_lines(archive) == (SPCS83_CITATION, UTM_CITATION)


def test_a_foot_elevation_on_the_geodetic_side_keeps_its_own_citation(tmp_path):
    """Geodetic in with elevations in international feet: the input's unit is
    a foot, which UTM's definition says nothing about."""
    _result, archive = _job(
        tmp_path, "1,45.0,-86.0,656.168,P\n",
        **_geodetic_to(UTM16, input_unit=INTERNATIONAL_FEET),
    )
    cited_in, cited_out = _units_lines(archive)
    assert cited_in == INTERNATIONAL_FEET.citation
    assert cited_out == UTM_CITATION


def test_a_state_plane_meters_job_still_cites_the_spcs83_manual(tmp_path):
    _result, archive = _job(tmp_path, "1,42.5,-84.4,200,P\n", **_geodetic_to(MI_SOUTH))
    assert _units_lines(archive) == (SPCS83_CITATION, SPCS83_CITATION)


# ==========================================================================
# LOW 4 - the extent sentence.
# ==========================================================================


def test_the_utm_extent_warning_names_the_part_over_michigan(tmp_path):
    """16N at 82.5 W, 43.0 N (St. Clair County): outside the part of 16N over
    Michigan, and the sentence says so - not "the area 16N covers"."""
    result, _archive = _job(tmp_path, "1,43.0,-82.5,,P\n", **_geodetic_to(UTM16))
    (warning,) = [w for p in result.points for w in p.warnings]
    assert warning.code is WarningCode.OUTSIDE_ZONE_EXTENT
    assert (
        "lies outside the part of NAD83(2011) / UTM zone 16N over Michigan "
        "(41.6 to 48.4 N, -90.0 to -84.0 E)" in warning.message
    )


def test_the_state_plane_extent_sentence_is_unchanged(tmp_path):
    result, _archive = _job(tmp_path, "1,43.5,-87.6,,P\n", **_geodetic_to(MI_SOUTH))
    (warning,) = [w for p in result.points for w in p.warnings]
    assert "lies outside the area Michigan South covers (41.6 to 44.3 N" in warning.message
