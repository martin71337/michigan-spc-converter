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
from michspc.job import Direction, JobSettings, LongitudeConvention, VerticalMode, run
from michspc.spc import convert, projection, tm
from michspc.spc.projection import GridPoint
from michspc.spc.convert import WarningCode
from michspc.spc.frames import NAD83_2011, NATRF2022
from michspc.spc.tm import DOMAIN_LIMIT_DEGREES, TransverseMercatorDomainError
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.vertical import NAVD88, NGVD29
from michspc.spc.zones import (
    MI_CENTRAL,
    MI_NORTH,
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


PROJ_SCALE_AT_45_7_N = (
    # (degrees east of 16N's meridian, PROJ's grid scale factor): PROJ 9.8.1,
    # EPSG v12.029, Proj("EPSG:6345").get_factors(lon, 45.7).meridional_scale,
    # computed 2026-10-30. 45.7 N is where the manual's forward scale series
    # drifts most over Michigan's latitudes at these distances.
    (4.8, 1.0013170289249773),
    (4.9, 1.0013893326681462),
)


def test_the_domain_limit_is_four_point_eight_degrees():
    """The lead's ruling (the re-confirmation's scale measurement, in
    tm.DOMAIN_LIMIT_DEGREES's docstring): the record prints scale factors to 8
    decimals, so the forward scale series must be within half a unit, 5e-9,
    everywhere the engine accepts a point. At 4.8 degrees it is (4.6e-9); at
    4.9 it is not (5.2e-9). Measured here against frozen PROJ values, so the
    limit's reason is executable, not only stated."""
    assert DOMAIN_LIMIT_DEGREES == 4.8
    constants = projection.constants_for(UTM16)
    (at_limit, proj_at_limit), (beyond, proj_beyond) = PROJ_SCALE_AT_45_7_N
    inside = tm._forward_series(45.7, -87.0 + at_limit, constants).scale_factor
    outside = tm._forward_series(45.7, -87.0 + beyond, constants).scale_factor
    assert abs(inside - proj_at_limit) < 5e-9
    assert abs(outside - proj_beyond) > 5e-9


def test_the_reviewers_15n_case_refuses_through_the_job(tmp_path):
    """Geodetic 42.0, -82.5 into 15N: 10.5 degrees off. Was written 14.1 mm /
    7.1 mm wrong with a record saying "computed correctly"; now refused,
    naming the point, the distance, the limit, the measured drift and the
    zone that covers it."""
    with pytest.raises(TransverseMercatorDomainError) as refused:
        _job(tmp_path, "2,42.0,-82.5,200,Q\n", **_geodetic_to(UTM15))
    message = str(refused.value)
    assert message.startswith("point 2 (NAD83(2011) / UTM zone 15N): ")
    assert "longitude -82.500000, 10.500000 degrees from the central meridian of zone 15N" in message
    assert "within 4.8 degrees of its central meridian" in message
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
    """4.799 degrees converts both ways; 4.801 refuses both ways, east and west."""
    meridian = zone.definition.lon_origin
    constants = projection.constants_for(zone)
    for side in (-1.0, 1.0):
        inside = meridian + side * 4.799
        point = projection.forward(45.0, inside, zone)
        back = projection.inverse(point.northing, point.easting, zone)
        assert back.longitude == pytest.approx(inside, abs=1e-8)

        outside = meridian + side * 4.801
        with pytest.raises(TransverseMercatorDomainError):
            projection.forward(45.0, outside, zone)
        grid = tm._forward_series(45.0, outside, constants)
        with pytest.raises(TransverseMercatorDomainError):
            projection.inverse(grid.northing, grid.easting, zone)


@pytest.mark.parametrize("zone", UTM_ZONES[:3], ids=lambda z: z.code)
def test_a_point_exactly_at_the_limit_reads_back(zone):
    """The re-confirmation's N5: whatever the forward accepts must read back.
    A point exactly 4.8 degrees from the meridian, east and west, at Michigan's
    southern and northern latitudes: projected, rounded to the 0.1 mm the
    program writes, and converted back - it converts, and comes back to the
    point. Without INVERSE_DOMAIN_ALLOWANCE_DEGREES the recovered longitude
    lands up to 9.1e-10 degrees past the limit and refuses."""
    meridian = zone.definition.lon_origin
    for latitude in (41.6, 45.0, 48.4):
        for side in (-1.0, 1.0):
            longitude = meridian + side * DOMAIN_LIMIT_DEGREES
            point = projection.forward(latitude, longitude, zone)
            back = projection.inverse(
                round(point.northing, 4), round(point.easting, 4), zone
            )
            assert back.longitude == pytest.approx(longitude, abs=1e-8)
            assert back.latitude == pytest.approx(latitude, abs=1e-8)


# The second re-confirmation's R2-1: N5 was closed in tm.inverse but not on
# the program's main read-back path. convert_point re-projects the position
# its inverse recovered - into the SAME zone on a zone-to-geodetic or
# vertical-only job - and that forward had no allowance, so a file the program
# wrote at the limit refused on read-back ("4.800000 degrees ... converts only
# within 4.8"). The reviewer's case, and its proof that the old pin (latitude
# 45.0 only) passed with the allowance seeded to 0.
REVIEWER_LIMIT_ROW = "1,4627612.7742,100559.4963,200.0000,P"
"""GEODETIC_TO_ZONE 17N "1,41.7,-85.8,200,P" writes exactly this row
(reconfirm2-output.txt, R2-1); its longitude reads back 9.1e-10 degrees past
the limit."""


def _vertical_only(zone):
    return dict(
        direction=Direction.VERTICAL_ONLY,
        source_zone=zone,
        target_zone=None,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
        longitude_convention=None,
    )


def test_the_reviewers_row_at_the_limit_is_what_the_program_writes(tmp_path):
    _result, archive = _job(tmp_path, "1,41.7,-85.8,200,P\n", **_geodetic_to(UTM17))
    clean = member_text(archive, f"{archive.stem}.csv").strip()
    assert clean == REVIEWER_LIMIT_ROW


def test_a_file_written_at_the_limit_reads_back_zone_to_geodetic(tmp_path):
    """Fails with INVERSE_DOMAIN_ALLOWANCE_DEGREES seeded to 0 (R2-1's pin)."""
    result, _archive = _job(tmp_path, REVIEWER_LIMIT_ROW + "\n", **_zone_to_geodetic(UTM17))
    (point,) = result.points
    assert point.conversion.latitude == pytest.approx(41.7, abs=1e-8)
    assert point.conversion.longitude == pytest.approx(-85.8, abs=1e-8)


def test_a_file_written_at_the_limit_reads_back_vertical_only(tmp_path):
    result, _archive = _job(tmp_path, REVIEWER_LIMIT_ROW + "\n", **_vertical_only(UTM17))
    (point,) = result.points
    assert point.conversion.longitude == pytest.approx(-85.8, abs=1e-8)


# 44.5 N, 82.2 W into 16N at full precision: exactly 4.8 degrees east of 16N's
# meridian - the position test_utm_16n_to_17n_lands_on_ncats_17n builds from a
# frozen NCAT anchor, which the reviewer found refused under ZONE_TO_GEODETIC.
ANCHOR_AT_THE_LIMIT = (44.5, -82.2)
HALF_MM_IN_DEGREES = 5e-9
"""Half a millimetre of latitude (1 degree is about 111 km): the bound the
read-back is held to, the inverse series' own error at the limit being
0.26 mm (tm.DOMAIN_LIMIT_DEGREES's table)."""


@pytest.mark.parametrize(
    "target",
    [UTM16, UTM17, MI_SOUTH, MI_CENTRAL],
    ids=lambda z: z.code,
)
def test_the_ncat_anchor_at_the_limit_reads_back_on_every_path(target):
    position = projection.forward(*ANCHOR_AT_THE_LIMIT, UTM16)
    result = convert.convert_point(position.northing, position.easting, UTM16, target)
    assert result.latitude == pytest.approx(ANCHOR_AT_THE_LIMIT[0], abs=HALF_MM_IN_DEGREES)
    assert result.longitude == pytest.approx(ANCHOR_AT_THE_LIMIT[1], abs=HALF_MM_IN_DEGREES)


def test_the_ncat_anchor_at_the_limit_reads_back_through_both_jobs(tmp_path):
    position = projection.forward(*ANCHOR_AT_THE_LIMIT, UTM16)
    row = f"1,{position.northing!r},{position.easting!r},200.0,P\n"
    to_geodetic, _ = _job(tmp_path, row, **_zone_to_geodetic(UTM16))
    assert to_geodetic.points[0].conversion.longitude == pytest.approx(-82.2, abs=HALF_MM_IN_DEGREES)
    vertical_dir = tmp_path / "vertical"
    vertical_dir.mkdir()
    vertical, _ = _job(vertical_dir, row, **_vertical_only(UTM16))
    assert vertical.points[0].conversion.longitude == pytest.approx(-82.2, abs=HALF_MM_IN_DEGREES)


# A lattice at exactly the limit, both sides of the meridian, on all six UTM
# zones: forward as the user supplies it, rounded to the 4 decimals the
# program writes, then read back on every path that re-projects - zone to
# geodetic (convert_point into the same zone), and zone to zone into a State
# Plane zone of the same frame and back again.
LIMIT_LATITUDES = tuple(41.6 + 0.4 * k for k in range(18))


def _limit_points(zone):
    meridian = zone.definition.lon_origin
    for latitude in LIMIT_LATITUDES:
        for side in (-1.0, 1.0):
            yield latitude, meridian + side * DOMAIN_LIMIT_DEGREES


def _state_plane_twin(zone):
    return MI_SOUTH if zone.frame is NAD83_2011 else SPCS2022_ZONES[0]


@pytest.mark.parametrize("zone", UTM_ZONES, ids=lambda z: z.code)
def test_every_point_at_the_limit_reads_back_on_every_path(zone):
    assert zone.frame in (NAD83_2011, NATRF2022)
    count = 0
    for latitude, longitude in _limit_points(zone):
        written = projection.forward(latitude, longitude, zone)
        northing, easting = round(written.northing, 4), round(written.easting, 4)
        same = convert.convert_point(northing, easting, zone, zone)
        assert same.longitude == pytest.approx(longitude, abs=1e-8)
        twin = _state_plane_twin(zone)
        out = convert.convert_point(northing, easting, zone, twin)
        back = convert.convert_point(out.target_northing, out.target_easting, twin, zone)
        assert back.target_northing == pytest.approx(northing, abs=1e-3)
        assert back.target_easting == pytest.approx(easting, abs=1e-3)
        count += 1
    assert count == 2 * len(LIMIT_LATITUDES)


def test_a_supplied_position_is_not_widened_by_the_allowance():
    """The allowance is for a position an inverse produced, never a supplied
    one: a geodetic position just past the limit (by half the allowance)
    still refuses on the forward, and is accepted on the recovered forward."""
    meridian = UTM16.definition.lon_origin
    longitude = meridian + DOMAIN_LIMIT_DEGREES + tm.INVERSE_DOMAIN_ALLOWANCE_DEGREES / 2
    with pytest.raises(TransverseMercatorDomainError):
        projection.forward(45.0, longitude, UTM16)
    with pytest.raises(TransverseMercatorDomainError):
        convert.project_point(45.0, longitude, NAD83_2011, UTM16)
    projection.forward(45.0, longitude, UTM16, recovered=True)


# --------------------------------------------------------------------------
# The re-confirmation's N1: a grid coordinate the inverse does not close on.
# --------------------------------------------------------------------------

FOLD_BACKS = (
    # The reviewer's two inputs, ZONE_TO_GEODETIC NAD83(2011) metres, 16N:
    # before the closure check each was written as a plausible position -
    # the first inside a Monroe County polygon (41.871079, -83.479228), where
    # PROJ (EPSG 6345) puts that grid coordinate at 29.825 S, 48.869 E.
    ("7175000.0", "4475000.0"),
    # A real Michigan South coordinate in international feet, read as 16N
    # metres: written as -33.561297, -87.911882; PROJ: 12.029 S, 2.209 E.
    ("982054.0253", "13477274.7744"),
    # Further far-off grid inputs, east and west of the false easting.
    ("5000000.0", "2500000.0"),
    ("5000000.0", "-2500000.0"),
    ("1000000.0", "8000000.0"),
)


@pytest.mark.parametrize("northing, easting", FOLD_BACKS)
def test_a_grid_coordinate_the_inverse_cannot_close_on_refuses(tmp_path, northing, easting):
    with pytest.raises(TransverseMercatorDomainError) as refused:
        _job(tmp_path, f"1,{northing},{easting},200,P\n", **_zone_to_geodetic(UTM16))
    message = str(refused.value)
    assert message.startswith("point 1 (NAD83(2011) / UTM zone 16N): ")
    assert "check the zone and the units" in message
    assert not list(tmp_path.glob("*.zip"))


def test_the_closure_message_names_the_coordinate_and_the_miss():
    with pytest.raises(TransverseMercatorDomainError) as refused:
        projection.inverse(7175000.0, 4475000.0, UTM16)
    message = str(refused.value)
    assert message.startswith(
        "Northing 7175000.0 m and easting 4475000.0 m are not a coordinate in zone 16N: "
    )
    assert "within 1 mm" in message
    assert "3,975,000 m from the zone's false easting of 500,000 m" in message


def test_the_closure_tolerance_is_measured_with_margin():
    """INVERSE_CLOSURE_TOLERANCE_M is 1 mm, and inside the domain the worst
    closure measured is 0.232 mm (the 0.1 mm-rounded coordinate of a point at
    the limit). Re-measured here on all three zones at the limit, so the
    margin is held, not just stated."""
    assert tm.INVERSE_CLOSURE_TOLERANCE_M == 0.001
    worst = 0.0
    for zone in UTM_ZONES[:3]:
        constants = projection.constants_for(zone)
        for k in range(35):
            latitude = 41.6 + k * 0.2
            for side in (-1.0, 1.0):
                longitude = zone.definition.lon_origin + side * DOMAIN_LIMIT_DEGREES
                grid = tm._forward_series(latitude, longitude, constants)
                n, e = round(grid.northing, 4), round(grid.easting, 4)
                position = tm._inverse_series(n, e, constants)
                again = tm._forward_series(position.latitude, position.longitude, constants)
                worst = max(worst, math.hypot(again.northing - n, again.easting - e))
    assert 0.0002 < worst < tm.INVERSE_CLOSURE_TOLERANCE_M / 4


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
    """15N -90.42 to -90.0, 16N -90.0 to -84.0, 17N -84.0 to -82.12, both frames:
    17N used at 79.5 W and 15N at 93.0 W are outside them."""
    expected = {15: (-90.42, -90.0), 16: (-90.0, -84.0), 17: (-84.0, -82.12)}
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
        "(41.6 to 48.4 N, -90.00 to -84.00 E)" in warning.message
    )


def test_the_state_plane_extent_sentence_is_unchanged(tmp_path):
    result, _archive = _job(tmp_path, "1,43.5,-87.6,,P\n", **_geodetic_to(MI_SOUTH))
    (warning,) = [w for p in result.points for w in p.warnings]
    assert "lies outside the area Michigan South covers (41.6 to 44.3 N" in warning.message


# ==========================================================================
# The narrowing re-confirmation's N2-N4, and the Great Lakes negative.
# ==========================================================================


def test_michigans_longitudes_are_the_county_sets_rounded_outward():
    """N2: zones.MICHIGAN_LONGITUDES is a literal (the core reads no files),
    so it is held here against the bundled county set it was taken from:
    every county vertex inside it, and each edge within 0.01 degree of the
    set's own bound - rounded outward, never inward. The latitudes contain
    every county too."""
    from michspc.fileio.counties import default_counties
    from michspc.spc.zones import MICHIGAN_LATITUDES, MICHIGAN_LONGITUDES

    longitudes: list[float] = []
    latitudes: list[float] = []

    def walk(item):
        if (
            isinstance(item, tuple)
            and len(item) == 2
            and all(isinstance(v, float) for v in item)
        ):
            longitudes.append(item[0])
            latitudes.append(item[1])
            return
        for child in item:
            walk(child)

    for county in default_counties().counties:
        walk(county.rings)
    west, east = MICHIGAN_LONGITUDES
    assert west <= min(longitudes) < west + 0.01
    assert east - 0.01 < max(longitudes) <= east
    assert MICHIGAN_LATITUDES[0] <= min(latitudes)
    assert max(latitudes) <= MICHIGAN_LATITUDES[1]


def test_a_17n_point_in_michigans_lake_huron_east_of_82_3_w_does_not_warn(tmp_path):
    """N2, the reviewer's input: 43.8 N, 82.2 W into 17N is in Lake Huron
    inside the Huron County polygon. With the old -82.3 east edge it was told
    it lay outside the part of 17N over Michigan; it is in Michigan."""
    result, _archive = _job(tmp_path, "1,43.8,-82.2,180,P\n", **_geodetic_to(UTM17))
    assert _codes(result) == []


@pytest.mark.parametrize(
    "zone, latitude, longitude, county",
    [
        # Lake Superior off Gogebic County, west of 90 W: 15N.
        (UTM15, 46.8, -90.1, "Gogebic"),
        # Lake Michigan, mid-lake, Michigan's side (an autozone anchor): 16N.
        (UTM16, 44.0, -86.9, "Mason"),
        # Lake Huron, Michigan's waters (an autozone anchor): 17N.
        (UTM17, 44.5, -82.7, "Iosco"),
    ],
    ids=["15N-superior", "16N-michigan", "17N-huron"],
)
def test_a_great_lakes_water_point_in_michigan_does_not_warn(
    tmp_path, zone, latitude, longitude, county
):
    """The reviewer's missing negative: Michigan's Great Lakes waters are
    Michigan, so a UTM job's water point gets neither the outside-Michigan nor
    the extent warning. The county named is the water-extended polygon the
    point lies in (checked here, so the case cannot silently become land)."""
    from michspc.fileio.counties import default_counties

    assert [c.name for c in default_counties().containing(longitude, latitude)] == [county]
    result, _archive = _job(
        tmp_path, f"1,{latitude},{longitude},180,P\n", **_geodetic_to(zone)
    )
    assert _codes(result) == []


def test_a_state_plane_to_utm_point_outside_michigan_names_its_northing_and_easting(tmp_path):
    """N3, the reviewer's input: ZONE_TO_ZONE 2113 (international feet) -> 16N,
    the 2113 coordinate of 41.55 N, 86.0 W (Indiana). The input holds a
    northing and easting, so the advice names those and the zone and unit
    they were declared in - not a latitude and longitude the file does not
    have. The coordinate is the engine's own, 2113 forward at that position."""
    result, _archive = _job(
        tmp_path,
        "1,22559.89445232862,12676222.158558782,200,P\n",
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_SOUTH,
        target_zone=UTM16,
        input_unit=INTERNATIONAL_FEET,
    )
    outside = [w for p in result.points for w in p.warnings if w.code is OUTSIDE]
    assert len(outside) == 1
    assert outside[0].message.endswith(
        "it is outside Michigan. Check the northing and easting, and that "
        "Michigan South is the zone, and the unit, these coordinates were "
        "declared in."
    )
    assert "latitude and longitude" not in outside[0].message


def _run_positive_west(tmp_path, rows, zone):
    settings = dict(_geodetic_to(zone))
    base = dict(
        input_path=tmp_path / "in.csv",
        output_directory=tmp_path,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.POSITIVE_WEST,
    )
    base.update(settings)
    job_settings = JobSettings(**base)
    job_settings.input_path.write_text(rows, encoding="utf-8")
    return run(job_settings)


SIGN_SENTENCE = (
    "A file written in the other longitude sign convention lands every point "
    "on the other side of Greenwich: check that the convention chosen for this "
    "job is the one this file uses."
)


def test_a_positive_west_file_read_as_negative_west_names_the_sign_convention(tmp_path):
    """N4, the reviewer's input: "1,43.0,84.5,200,P" into 16N under negative
    west - a positive-west file. The refusal states the file's value, the
    convention in force and where that put the point, and presumes nothing."""
    with pytest.raises(TransverseMercatorDomainError) as refused:
        _job(tmp_path, "1,43.0,84.5,200,P\n", **_geodetic_to(UTM16))
    assert str(refused.value).endswith(
        "The file gives longitude 84.500000, and this job reads longitudes as "
        "negative west, which puts the point at 84.500000 - east of Greenwich, "
        "where no Michigan point is. " + SIGN_SENTENCE
    )


def test_a_negative_west_file_read_as_positive_west_names_the_sign_convention(tmp_path):
    """R2-2, the mirror and the commoner blunder (the GUI opens on positive
    west; OPUS, NCAT and GPS files are negative west): "1,43.0,-84.5,200,P"
    under positive west. The file's own -84.5 is named, not 84.5."""
    with pytest.raises(TransverseMercatorDomainError) as refused:
        _run_positive_west(tmp_path, "1,43.0,-84.5,200,P\n", UTM16)
    message = str(refused.value)
    assert message.endswith(
        "The file gives longitude -84.500000, and this job reads longitudes as "
        "positive west, which puts the point at 84.500000 - east of Greenwich, "
        "where no Michigan point is. " + SIGN_SENTENCE
    )
    assert "if this file's longitudes are positive west" not in message


def test_the_sign_sentence_is_equally_true_on_an_spcs2022_transverse_mercator_job(tmp_path):
    """The reviewer's third case: zone 261001 (a transverse Mercator
    low-distortion zone) at 42.3, -83.7 under positive west, on NATRF2022."""
    zone = zone_by_code("261001")
    settings = dict(
        input_path=tmp_path / "in.csv",
        output_directory=tmp_path,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.POSITIVE_WEST,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=zone,
        geodetic_frame=NATRF2022,
    )
    job_settings = JobSettings(**settings)
    job_settings.input_path.write_text("1,42.3,-83.7,200,P\n", encoding="utf-8")
    with pytest.raises(TransverseMercatorDomainError) as refused:
        run(job_settings)
    assert str(refused.value).endswith(
        "The file gives longitude -83.700000, and this job reads longitudes as "
        "positive west, which puts the point at 83.700000 - east of Greenwich, "
        "where no Michigan point is. " + SIGN_SENTENCE
    )


def test_a_west_longitude_refusal_does_not_blame_the_sign_convention(tmp_path):
    """The N4 sentence is for a longitude east of Greenwich only: 15N used at
    82.5 W is a wrong zone, not a wrong sign."""
    with pytest.raises(TransverseMercatorDomainError) as refused:
        _job(tmp_path, "1,42.0,-82.5,200,P\n", **_geodetic_to(UTM15))
    assert "sign convention" not in str(refused.value)


# --------------------------------------------------------------------------
# The second re-confirmation's uncaught seed: the closure test rewritten so a
# NaN miss passes ("not miss > tolerance") went uncaught, because a NaN
# recovered longitude fails the domain test first. Pinned directly: a NaN
# re-projection must refuse on the closure test's own containment.
# --------------------------------------------------------------------------


def test_a_nan_closure_refuses_on_its_own(monkeypatch):
    nan = float("nan")
    monkeypatch.setattr(
        tm,
        "_forward_series",
        lambda latitude, longitude, constants: GridPoint(
            northing=nan, easting=nan, convergence=nan, scale_factor=nan
        ),
    )
    with pytest.raises(TransverseMercatorDomainError, match="miss themselves by nan m"):
        projection.inverse(4980000.0, 500000.0, UTM16)
