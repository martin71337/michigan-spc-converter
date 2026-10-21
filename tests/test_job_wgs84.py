"""Work package W3 of the WGS 84 build: the frame transformation, connected.

docs/PLAN-wgs84.md sections 3.4 and 3.5, decisions D1 and D5 to D10;
docs/DESIGN.md #70. W1 transcribed NGS HTDP v3.6.0 (``htdp.py``) and W2
registered its ten paths (``frames.py``); this package runs them inside the
conversion and ``job.run``. What is pinned here:

1. **End to end against HTDP's own printed output**, through real files and
   ``job.run``, in every direction a time-dependent frame reaches -
   GEODETIC_TO_ZONE, ZONE_TO_GEODETIC, GEODETIC_TO_GEODETIC both ways, and
   VERTICAL_ONLY - on each of the five frames, under every height convention
   (plan D6). The truth is frozen from NGS's binary
   (``tests/fixtures/htdp_anchors.py``, W0; ``htdp_w3_anchors.py``, this
   package's generator for interim gate 1's L5 position). Every expected value
   is an independent leg derived in a comment: HTDP's print, or HTDP's print
   carried through the program's own NCAT-verified projection or GEOID18
   reader. Latitude, longitude and height are compared separately, never
   through a ``max()`` (#62's lesson).
2. **The settings**: ``observation_date`` (required, refused when stray, a
   real date, not in the future, the realization-period warning of D9),
   ``target_geodetic_frame`` and ``Direction.GEODETIC_TO_GEODETIC`` (D7), and
   the stray ``geodetic_frame`` of interim gate 1's I1.
3. **The record**: ``PointConversion``'s transformation evidence, held to
   itself; the canonical-record rule of gate 1's L4; the zone type checks of
   gate 1's I2.
4. **The write guard's successors.** W3 held every transformed job back from
   the disk (plan W3 item 9) until W4 could disclose it. W4 removed the guard;
   its three pins are kept here as successors - the inputs that refused now
   WRITE, and what they write is pinned against HTDP's print. The full
   disclosure suite is ``tests/test_frame_disclosure.py``.

The interface's reachability pins are in ``tests/test_gui_frames.py``.
"""

from __future__ import annotations

import dataclasses
import datetime
import importlib.util
from pathlib import Path

import pytest

from michspc import job
from michspc.fileio import exports, geoid
from michspc.fileio.report import build_report
from tests.conftest import member_text
from michspc.job import (
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc import convert, frames, htdp
from michspc.spc.convert import (
    HeightConvention,
    TransformHeight,
    WarningCode,
    geodetic_to_geodetic,
    pivot_path,
    project_point,
    zone_to_geodetic,
)
from michspc.spc.frames import (
    FRAME_TRANSFORMATIONS,
    ITRF2014,
    ITRF2020,
    NAD83_2011,
    NATRF2022,
    WGS84,
    WGS84_G1762,
    WGS84_G2139,
    WGS84_G2296,
    FrameNotUsableError,
    FrameTransformationUnavailableError,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.vertical import NAVD88, NGVD29, HeightKind
from michspc.spc.zones import MI_CENTRAL, MI_SOUTH, zone_by_code
from tests.fixtures.htdp_anchors import HTDP_RUNS
from tests.fixtures.htdp_w3_anchors import L5_RECORDS, L5_REVERSE_RECORDS

REPO = Path(__file__).resolve().parents[1]
STATEWIDE_2022 = zone_by_code("260001")  # the SPCS2022 statewide zone, NATRF2022

FIVE = (WGS84_G1762, WGS84_G2139, WGS84_G2296, ITRF2014, ITRF2020)
FIVE_IDS = [frame.code for frame in FIVE]
MENU = {
    # HTDP's MENU1 numbers (htdp.f:4704-4711, 4749-4753), as the fixture
    # records them.
    WGS84_G1762.code: 10,
    WGS84_G2139.code: 11,
    WGS84_G2296.code: 12,
    ITRF2014.code: 25,
    ITRF2020.code: 26,
}
RUNS = {run_.run_id: run_ for run_ in HTDP_RUNS}
L5 = {record.frame_code: record for record in L5_RECORDS}
L5R = {record.frame_code: record for record in L5_REVERSE_RECORDS}
L5_DATE = datetime.date(2025, 6, 15)

# The W0 anchors used end to end: the Michigan lattice of every run (P064 to
# P082 - the box's interior, Isle Royale, the lakes, Clare, Houghton,
# Detroit, the Soo, the grid probes and the 45 N FRMXYZ switch), at the
# 2020.0 epoch, whose decimal entry IS the calendar date 2020-01-01 (the
# fixture's own docstring, and RECON.md section 1.5). Heights rotate through
# 0, 200 and 600 m across the records.
EPOCH_2020 = datetime.date(2020, 1, 1)


def _michigan(records):
    return [r for r in records if r.name.startswith("P0") and int(r.name[1:4]) >= 64]


def _forward(frame):
    return _michigan(RUNS[f"fwd_f{MENU[frame.code]}_2020.0"].records)


def _reverse(frame):
    return _michigan(RUNS[f"rev_f{MENU[frame.code]}_2020.0"].records)


# --------------------------------------------------------------------------
# Tolerances, each derived once.
# --------------------------------------------------------------------------

# Projected grid coordinates of HTDP's printed NAD 83 pivot against the
# program's unrounded one. HTDP prints 1e-10 deg, so the two pivots differ by
# at most half of that in each of latitude and longitude. 0.5e-10 deg x
# (pi/180) x 6.39e6 m (the largest radius of curvature in Michigan, the
# prime vertical's at 48.5 N, rounded up) = 5.58e-6 m; a longitude step is
# smaller by cos(latitude). The grid northing and easting each take at most
# both steps, rotated by the convergence and scaled by k < 1.0001 in these
# zones, so each component differs by at most 2 x 5.58e-6 x 1.0001 =
# 1.12e-5 m. Rounded up.
GRID_TOLERANCE_M = 1.2e-5

# A written latitude or longitude after the program's own inverse projection
# and HTDP: half of HTDP's print unit (0.5e-10 deg) plus the projection round
# trip's bound, 1e-11 deg, asserted in the test where it is relied on. HTDP's
# map is a near-identity shift (its Jacobian differs from 1 by about 1e-6),
# so the round trip moves its output by the same amount to within rounding.
GEODETIC_TOLERANCE_DEG = 0.5e-10 + 1e-11

# A height compared with HTDP's print: half of its 1 mm unit, plus 1e-6 m
# for any geoid separation read at the program's unrounded pivot rather than
# HTDP's printed one (5e-11 deg is about 6 um, and N changes by far less than
# 1e-6 m over that).
HEIGHT_TOLERANCE_M = 0.0005 + 1e-6


def _settings(tmp_path: Path, **overrides) -> JobSettings:
    fields = dict(
        input_path=tmp_path / "points.csv",
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_CENTRAL,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.POSITIVE_WEST,
        geodetic_frame=WGS84_G2296,
        observation_date=EPOCH_2020,
    )
    fields.update(overrides)
    return JobSettings(**fields)


def _write(settings: JobSettings, lines: list[str]) -> None:
    settings.input_path.write_text("".join(lines), encoding="utf-8")


def _geodetic_rows(records) -> list[str]:
    """HTDP's own input strings, longitude positive west as HTDP reads it."""
    return [f"{r.name},{r.lat_in},{r.lonw_in},{r.h_in},A\n" for r in records]


def _grid_rows(records, zone) -> list[str]:
    """A reverse record's NAD 83 INPUT projected into ``zone`` by the program.

    An input, not an expected value - the brief's construction: the job
    inverts it back to (nearly) the anchor's own input, which HTDP then
    carries out. Written with repr, so the file holds the doubles exactly.
    """
    rows = []
    for r in records:
        point = project_point(float(r.lat_in), -float(r.lonw_in), NAD83_2011, zone)
        rows.append(
            f"{r.name},{point.target_northing!r},{point.target_easting!r},{r.h_in},A\n"
        )
    return rows


def _by_id(result):
    return {point.point_id: point for point in result.points}


def _not_recorded(record) -> bool:
    # The reader's rule (pnezd): an exactly-zero Z means "not recorded".
    return float(record.h_in) == 0.0


# ==========================================================================
# 0. The W3 truth file reproduces from its generator.
# ==========================================================================


def test_the_w3_generator_reproduces_its_fixture_byte_for_byte():
    spec = importlib.util.spec_from_file_location(
        "make_w3_anchors", REPO / "review" / "wgs84-w3" / "make_w3_anchors.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = (REPO / "tests" / "fixtures" / "htdp_w3_anchors.py").read_text(
        encoding="utf-8"
    )
    assert module.render() == fixture
    # The L5 input is the reviewer's, verbatim (review/gate-wgs84-1/output.md).
    for record in (*L5_RECORDS, *L5_REVERSE_RECORDS):
        assert (record.lat_in, record.lonw_in, record.h_in) == ("43.0", "84.5", "165.000")
        assert record.observation_date == L5_DATE
    assert [r.frame_code for r in L5_RECORDS] == FIVE_IDS
    assert [r.frame_code for r in L5_REVERSE_RECORDS] == FIVE_IDS


# ==========================================================================
# 1. End to end, every direction, every frame, every height convention.
# ==========================================================================


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_geodetic_to_zone_projects_htdps_nad83_output(tmp_path, frame):
    """WGS 84/ITRF lat/lon in, MI-C grid out, orthometric or blank Z.

    Expected northing and easting: HTDP's PRINTED NAD 83 output for the
    anchor, projected by the program's own NCAT-verified projection - two
    independent legs - within GRID_TOLERANCE_M per component. The pivot itself
    must equal HTDP's print at its printed digit. The Z is orthometric (the
    default), so HTDP is handed H in place of h - the anchor's own input
    height - and the Z passes unchanged; a 0.000 Z is "not recorded", handed
    as h = 0 (the anchor's input there too) and stays blank.
    """
    records = _forward(frame)
    settings = _settings(tmp_path, geodetic_frame=frame)
    _write(settings, _geodetic_rows(records))
    points = _by_id(run(settings))
    for r in records:
        point = points[r.name]
        assert f"{point.conversion.latitude:.10f}" == r.lat_out, r.name
        assert f"{-point.conversion.longitude:.10f}" == r.lonw_out, r.name
        expected = project_point(float(r.lat_out), -float(r.lonw_out), NAD83_2011, MI_CENTRAL)
        assert abs(point.output_northing - expected.target_northing) <= GRID_TOLERANCE_M, r.name
        assert abs(point.output_easting - expected.target_easting) <= GRID_TOLERANCE_M, r.name
        height = point.conversion.transform_height
        if _not_recorded(r):
            assert height == TransformHeight(HeightConvention.NOT_RECORDED, None)
            assert point.output_elevation is None
        else:
            assert height == TransformHeight(HeightConvention.ORTHOMETRIC, float(r.h_in))
            assert point.output_elevation == float(r.h_in)
        assert point.conversion.external_position.frame is frame
        assert point.conversion.observation_epoch == htdp.ObservationEpoch(EPOCH_2020)


def test_geodetic_to_zone_in_feet_projects_the_same_pivot(tmp_path):
    """The unit boundary is untouched: the same job in international feet.

    Expected: the metre result of the program's projection of HTDP's printed
    pivot, divided by 0.3048 (the international foot, exact), within
    GRID_TOLERANCE_M / 0.3048. The orthometric Z in feet is handed to HTDP in
    METRES (it is a height), so the transform is the anchor's: a 200 m height
    is written 656.168 ft in and stays 656.168 ft out.
    """
    (r,) = [r for r in _forward(WGS84_G2296) if r.name == "P078H200"]
    settings = _settings(tmp_path, input_unit=INTERNATIONAL_FEET, output_unit=INTERNATIONAL_FEET)
    _write(settings, [f"1,{r.lat_in},{r.lonw_in},{200.0 / 0.3048!r},A\n"])
    (point,) = run(settings).points
    assert f"{point.conversion.latitude:.10f}" == r.lat_out
    assert f"{-point.conversion.longitude:.10f}" == r.lonw_out
    expected = project_point(float(r.lat_out), -float(r.lonw_out), NAD83_2011, MI_CENTRAL)
    tolerance = GRID_TOLERANCE_M / 0.3048
    assert abs(point.output_northing - expected.target_northing / 0.3048) <= tolerance
    assert abs(point.output_easting - expected.target_easting / 0.3048) <= tolerance
    assert abs(point.conversion.transform_height.value_m - 200.0) < 1e-9


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_geodetic_to_zone_with_ellipsoid_heights_writes_the_nad83_h(tmp_path, frame):
    """ELLIPSOID Z, horizontal mode: the Z written is h in the OUTPUT frame (D6).

    Expected: HTDP's printed NAD 83 height for each anchor, within
    HEIGHT_TOLERANCE_M - not the WGS 84/ITRF h as supplied, which is about a
    metre away (h_out - h_in is 0.8 to 1.2 m on every record). A 0.000 Z is
    still "not recorded" and stays blank.
    """
    records = _forward(frame)
    settings = _settings(tmp_path, geodetic_frame=frame, input_height_kind=HeightKind.ELLIPSOID)
    _write(settings, _geodetic_rows(records))
    points = _by_id(run(settings))
    for r in records:
        point = points[r.name]
        if _not_recorded(r):
            assert point.output_elevation is None
            continue
        assert abs(point.output_elevation - float(r.h_out)) <= HEIGHT_TOLERANCE_M, r.name
        assert abs(point.output_elevation - float(r.h_in)) > 0.5, r.name
        assert point.conversion.external_position.ellipsoid_height == float(r.h_in)
        # H = h - N used the NAD 83 h: the reading carries it.
        assert point.ellipsoid_height.ellipsoid_height_m == point.conversion.pivot_ellipsoid_height


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_zone_to_geodetic_writes_htdps_output_in_the_global_frame(tmp_path, frame):
    """MI-C grid in, WGS 84/ITRF lat/lon out, ellipsoid Z.

    The input is each reverse anchor's NAD 83 input projected by the program;
    the job inverts it - the round trip, measured here at 1e-11 deg - and HTDP
    carries the pivot to ``frame`` at 2020-01-01. Expected: HTDP's printed
    output, within GEODETIC_TOLERANCE_DEG in latitude and in longitude
    separately; the ELLIPSOID Z written is HTDP's printed output height in
    ``frame``, within HEIGHT_TOLERANCE_M (the input Z is a NAD 83 h, the
    zone's frame). The written longitude is in the file's convention,
    positive west.
    """
    records = _reverse(frame)
    settings = _settings(
        tmp_path,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_CENTRAL,
        target_zone=None,
        geodetic_frame=frame,
        input_height_kind=HeightKind.ELLIPSOID,
    )
    _write(settings, _grid_rows(records, MI_CENTRAL))
    points = _by_id(run(settings))
    for r in records:
        point = points[r.name]
        assert abs(point.conversion.latitude - float(r.lat_in)) <= 1e-11, r.name
        assert abs(point.conversion.longitude + float(r.lonw_in)) <= 1e-11, r.name
        assert abs(point.output_northing - float(r.lat_out)) <= GEODETIC_TOLERANCE_DEG, r.name
        assert abs(point.output_easting - float(r.lonw_out)) <= GEODETIC_TOLERANCE_DEG, r.name
        if _not_recorded(r):
            assert point.output_elevation is None
        else:
            assert abs(point.output_elevation - float(r.h_out)) <= HEIGHT_TOLERANCE_M, r.name
        assert point.conversion.frame is NAD83_2011
        assert point.conversion.external_position.frame is frame


def test_zone_to_geodetic_with_an_orthometric_z_passes_it_unchanged(tmp_path):
    """ORTHOMETRIC Z on a reverse job: handed to HTDP as h, written unchanged.

    The anchors' input height IS the Z here, so the horizontal output is the
    anchor's (within GEODETIC_TOLERANCE_DEG), and the Z out equals the Z in to
    the bit: an elevation belongs to no frame.
    """
    records = [r for r in _reverse(ITRF2020) if not _not_recorded(r)]
    settings = _settings(
        tmp_path,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_CENTRAL,
        target_zone=None,
        geodetic_frame=ITRF2020,
    )
    _write(settings, _grid_rows(records, MI_CENTRAL))
    points = _by_id(run(settings))
    for r in records:
        point = points[r.name]
        assert abs(point.output_northing - float(r.lat_out)) <= GEODETIC_TOLERANCE_DEG
        assert abs(point.output_easting - float(r.lonw_out)) <= GEODETIC_TOLERANCE_DEG
        assert point.output_elevation == float(r.h_in)
        assert point.conversion.transform_height.convention is HeightConvention.ORTHOMETRIC
        assert point.conversion.external_position.ellipsoid_height is None


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_geodetic_to_geodetic_forward_is_htdps_print(tmp_path, frame):
    """WGS 84/ITRF in, NAD83(2011) out: the written values ARE HTDP's output.

    No projection is involved, so the expected values are HTDP's printed
    strings themselves, compared at HTDP's printed digit (1e-10 deg, 1 mm),
    latitude, longitude and height separately. Ellipsoid Z, horizontal mode.
    """
    records = _forward(frame)
    settings = _settings(
        tmp_path,
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        geodetic_frame=frame,
        target_geodetic_frame=NAD83_2011,
        input_height_kind=HeightKind.ELLIPSOID,
    )
    _write(settings, _geodetic_rows(records))
    points = _by_id(run(settings))
    for r in records:
        point = points[r.name]
        assert f"{point.output_northing:.10f}" == r.lat_out, r.name
        assert f"{point.output_easting:.10f}" == r.lonw_out, r.name
        if not _not_recorded(r):
            assert f"{point.output_elevation:.3f}" == r.h_out, r.name
        conversion = point.conversion
        assert (conversion.source_zone, conversion.target_zone) == (None, None)
        assert conversion.target_scale_factor is None
        assert point.factors.grid_scale_factor is None


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_geodetic_to_geodetic_reverse_is_htdps_print(tmp_path, frame):
    """NAD83(2011) in, WGS 84/ITRF out, negative-west file: HTDP's print again."""
    records = _reverse(frame)
    settings = _settings(
        tmp_path,
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        geodetic_frame=NAD83_2011,
        target_geodetic_frame=frame,
        input_height_kind=HeightKind.ELLIPSOID,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    _write(settings, [f"{r.name},{r.lat_in},-{r.lonw_in},{r.h_in},A\n" for r in records])
    points = _by_id(run(settings))
    for r in records:
        point = points[r.name]
        assert f"{point.output_northing:.10f}" == r.lat_out, r.name
        assert f"{-point.output_easting:.10f}" == r.lonw_out, r.name
        if not _not_recorded(r):
            assert f"{point.output_elevation:.3f}" == r.h_out, r.name
        assert point.conversion.frame is NAD83_2011
        assert point.conversion.latitude == float(r.lat_in)


def _geoid18_at(record) -> float:
    return geoid.geoid_height(
        float(record.lat_out),
        -float(record.lonw_out),
        geoid.default_grid(geoid.GEOID18_MODEL),
    )


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_vertical_only_ellipsoid_height_is_htdps_nad83_h_minus_geoid18(tmp_path, frame):
    """Interim gate 1's L5 job, on every frame: the elevation is H = h(NAD 83) - N.

    Row ``1,43.0,-84.5,165.000``, ELLIPSOID, NAVD 88 to NAVD 88, observed
    2025-06-15. Expected: HTDP's printed NAD 83 h for the position
    (htdp_w3_anchors.L5_RECORDS - 166.096 to 166.099 m across the frames)
    minus N from the program's GEOID18 reader at HTDP's printed pivot
    (-33.085 m there), within HEIGHT_TOLERANCE_M. For WGS84(G2296):
    166.099 - (-33.085) = 199.184 m. The reviewer's unguarded seed wrote
    198.085 m - 165.000 + 33.085, the WGS 84 h taken as NAD 83's.
    """
    truth = L5[frame.code]
    settings = _settings(
        tmp_path,
        direction=Direction.VERTICAL_ONLY,
        target_zone=None,
        geodetic_frame=frame,
        input_height_kind=HeightKind.ELLIPSOID,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
        observation_date=L5_DATE,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    _write(settings, ["1,43.0,-84.5,165.000,P\n"])
    (point,) = run(settings).points
    expected = float(truth.h_out) - _geoid18_at(truth)
    assert abs(point.output_elevation - expected) <= HEIGHT_TOLERANCE_M
    assert abs(point.output_elevation - 198.085) > 1.0
    # The pivot the grids were read at is HTDP's, and the columns mirror.
    assert f"{point.conversion.latitude:.10f}" == truth.lat_out
    assert f"{-point.conversion.longitude:.10f}" == truth.lonw_out
    assert (point.output_northing, point.output_easting) == (43.0, -84.5)
    assert f"{point.ellipsoid_height.ellipsoid_height_m:.3f}" == truth.h_out


def test_the_l5_figure_itself(tmp_path):
    """The headline number, stated: 199.184 m for G2296 (166.099 + 33.085)."""
    truth = L5[WGS84_G2296.code]
    assert truth.h_out == "166.099"
    assert f"{_geoid18_at(truth):.3f}" == "-33.085"


def test_geodetic_to_geodetic_with_vertical_gives_a_navd88_elevation(tmp_path):
    """D7 with HORIZONTAL_AND_VERTICAL: a GNSS WGS 84 position and h in, NAD 83 and NAVD 88 out.

    The flagship use, and the reason this direction pairs with the vertical
    mode rather than refusing it: every piece is one already pinned - the
    NAD 83 pivot (D5) for the lookups, H = h(NAD 83) - N (D6), the NAVD 88
    identity. Expected: HTDP's printed NAD 83 position at its printed digit,
    and the elevation 166.099 - N(GEOID18) = 199.184 m within
    HEIGHT_TOLERANCE_M; the grid scale factor is absent (no zone) while the
    elevation factor exists.
    """
    truth = L5[WGS84_G2296.code]
    settings = _settings(
        tmp_path,
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        geodetic_frame=WGS84_G2296,
        target_geodetic_frame=NAD83_2011,
        input_height_kind=HeightKind.ELLIPSOID,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
        observation_date=L5_DATE,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    _write(settings, ["1,43.0,-84.5,165.000,P\n"])
    (point,) = run(settings).points
    assert f"{point.output_northing:.10f}" == truth.lat_out
    assert f"{-point.output_easting:.10f}" == truth.lonw_out
    expected = float(truth.h_out) - _geoid18_at(truth)
    assert abs(point.output_elevation - expected) <= HEIGHT_TOLERANCE_M
    assert point.factors.grid_scale_factor is None
    assert point.factors.elevation_factor is not None


def test_a_blank_z_is_not_recorded_and_is_transformed_at_zero(tmp_path):
    """Blank and 0.000 are both "not recorded" (pnezd), and HTDP gets h = 0.

    Expected: the anchors whose input height is 0.000 (h = 0 into HTDP), so
    HTDP's print is the pivot for the blank row and the zero row alike; both
    stay blank, under ELLIPSOID and ORTHOMETRIC alike.
    """
    (r,) = [r for r in _forward(WGS84_G2139) if r.name == "P074H000"]
    for kind in (HeightKind.ORTHOMETRIC, HeightKind.ELLIPSOID):
        settings = _settings(tmp_path, geodetic_frame=WGS84_G2139, input_height_kind=kind)
        _write(settings, [f"B,{r.lat_in},{r.lonw_in},,A\n", f"Z,{r.lat_in},{r.lonw_in},0.000,A\n"])
        for point in run(settings).points:
            assert f"{point.conversion.latitude:.10f}" == r.lat_out
            assert f"{-point.conversion.longitude:.10f}" == r.lonw_out
            assert point.output_elevation is None
            assert point.conversion.transform_height == TransformHeight(
                HeightConvention.NOT_RECORDED, None
            )


def test_an_orthometric_z_is_used_as_h_and_moves_the_horizontal_by_micrometres(tmp_path):
    """D6's measured cost, as a fact: H for h moves the horizontal by < 0.012 mm.

    The same anchor position with h = 200 m (its truth) and with an
    orthometric Z 34 m higher - roughly H against h in Michigan (|N| ~ 34 m).
    Expected from #70's measurement, 1.2e-5 m per 40 m: under 1.2e-5 m in
    each of north and east, in degrees 1.2e-5 / 111,000 ~ 1.1e-10.
    """
    (r,) = [r for r in _forward(WGS84_G2296) if r.name == "P078H200"]
    settings = _settings(tmp_path)
    _write(settings, [f"1,{r.lat_in},{r.lonw_in},{float(r.h_in) + 34.0},A\n"])
    (point,) = run(settings).points
    assert abs(point.conversion.latitude - float(r.lat_out)) < 1.1e-10 + 0.5e-10
    assert abs(-point.conversion.longitude - float(r.lonw_out)) < 1.1e-10 + 0.5e-10
    assert point.output_elevation == float(r.h_in) + 34.0


# ==========================================================================
# 2. The observation date (plan D9, D10).
# ==========================================================================


def test_a_time_dependent_job_without_a_date_is_refused_naming_the_frame(tmp_path):
    for frame in FIVE:
        settings = _settings(tmp_path, geodetic_frame=frame, observation_date=None)
        with pytest.raises(ValueError) as caught:
            run(settings)  # the file does not exist: refused before reading
        message = str(caught.value)
        assert f"has positions in {frame.code}" in message
        assert "no observation_date" in message
        assert "17 mm a year" in message


@pytest.mark.parametrize(
    "overrides",
    [
        dict(geodetic_frame=NAD83_2011),
        dict(direction=Direction.ZONE_TO_GEODETIC, source_zone=MI_SOUTH, target_zone=None, geodetic_frame=NAD83_2011),
        dict(direction=Direction.ZONE_TO_ZONE, source_zone=MI_SOUTH, target_zone=MI_CENTRAL, geodetic_frame=NAD83_2011, longitude_convention=None),
        dict(target_zone=STATEWIDE_2022, geodetic_frame=NATRF2022),
    ],
    ids=["g2z-nad83", "z2g-nad83", "zone-to-zone", "g2z-natrf2022"],
)
def test_a_stray_observation_date_is_refused_by_name(tmp_path, overrides):
    settings = _settings(tmp_path, **overrides)
    with pytest.raises(ValueError) as caught:
        run(settings)
    message = str(caught.value)
    assert "observation_date=2020-01-01" in message
    assert "no frame this job reads is time-dependent" in message
    assert "Pass observation_date=None" in message


def test_a_datetime_is_refused_because_its_time_would_be_dropped(tmp_path):
    settings = _settings(
        tmp_path, observation_date=datetime.datetime(2020, 1, 1, 18, 30)
    )
    with pytest.raises(TypeError) as caught:
        run(settings)
    assert "time of day" in str(caught.value)
    for wrong in ("2020-01-01", 2020.0, (2020, 1, 1)):
        with pytest.raises(TypeError, match="must be a datetime.date"):
            run(_settings(tmp_path, observation_date=wrong))


def test_a_future_date_is_refused_against_the_seam(tmp_path, monkeypatch):
    """The day the job runs comes from ``job.today``, the one seam.

    Today 2025-06-14: 2025-06-15 is in the future and refused. Today
    2025-06-15: the same date is today, and converts.
    """
    settings = _settings(tmp_path, observation_date=L5_DATE, longitude_convention=LongitudeConvention.NEGATIVE_WEST)
    _write(settings, ["1,43.0,-84.5,165.000,P\n"])
    monkeypatch.setattr(job, "today", lambda: datetime.date(2025, 6, 14))
    with pytest.raises(ValueError) as caught:
        run(settings)
    assert "after the day this job runs (2025-06-14)" in str(caught.value)
    monkeypatch.setattr(job, "today", lambda: datetime.date(2025, 6, 15))
    assert len(run(settings).points) == 1


def test_today_is_never_earlier_than_the_local_date():
    assert job.today() >= datetime.date.today()


def test_htdps_own_year_rule_still_refuses_1906(tmp_path):
    with pytest.raises(htdp.HtdpEpochError, match="before\\s+1907"):
        run(_settings(tmp_path, observation_date=datetime.date(1906, 12, 31)))


def test_the_epoch_is_the_date_through_htdps_calendar(tmp_path):
    """D10: one epoch per job, every point on it, from the date by HTDP's arithmetic."""
    settings = _settings(tmp_path, observation_date=datetime.date(2024, 2, 29))
    _write(settings, _geodetic_rows(_forward(WGS84_G2296)[:3]))
    for point in run(settings).points:
        assert point.conversion.observation_epoch.date == datetime.date(2024, 2, 29)
        assert point.conversion.htdp_result.source_epoch.date == datetime.date(2024, 2, 29)


# The periods of use, plan D9 (NGA, ICG-17 WG-D 2023; EPSG 9756, 10607;
# IGSMAIL-8444), each ending the day before the next realization began:
#   G1762  2013-10-16 to 2021-01-02  (G2139 began 2021-01-03)
#   G2139  2021-01-03 to 2024-01-06  (G2296 began 2024-01-07)
#   G2296  2024-01-07, no end yet
# A date outside its realization's period warns; inside, nothing. Each case
# below states its expected outcome from those three lines.
PERIOD_CASES = [
    # One day before the start: outside, warns.
    (WGS84_G1762, datetime.date(2013, 10, 15), True),
    (WGS84_G2139, datetime.date(2021, 1, 2), True),
    (WGS84_G2296, datetime.date(2024, 1, 6), True),
    # The start day: inside, silent.
    (WGS84_G1762, datetime.date(2013, 10, 16), False),
    (WGS84_G2139, datetime.date(2021, 1, 3), False),
    (WGS84_G2296, datetime.date(2024, 1, 7), False),
    # The last day of the period (the day before the next start): inside.
    (WGS84_G1762, datetime.date(2021, 1, 2), False),
    (WGS84_G2139, datetime.date(2024, 1, 6), False),
    # The first day of the next realization's period: outside, warns.
    (WGS84_G1762, datetime.date(2021, 1, 3), True),
    (WGS84_G2139, datetime.date(2024, 1, 7), True),
    # Well before, and well after (G1762 on the L5 date, 2025-06-15).
    (WGS84_G1762, datetime.date(1997, 1, 1), True),
    (WGS84_G1762, L5_DATE, True),
    (WGS84_G2139, L5_DATE, True),
    # Inside, mid-period.
    (WGS84_G2296, L5_DATE, False),
    (WGS84_G1762, datetime.date(2020, 1, 1), False),
    # ITRF has no NGA period of use: never warns, at any date.
    (ITRF2014, datetime.date(1997, 1, 1), False),
    (ITRF2020, datetime.date(2020, 1, 1), False),
]


@pytest.mark.parametrize(
    ("frame", "date", "warns"),
    PERIOD_CASES,
    ids=[f"{frame.code}-{date.isoformat()}" for frame, date, _ in PERIOD_CASES],
)
def test_the_realization_period_warning_fires_outside_the_period_once_for_the_job(
    tmp_path, frame, date, warns
):
    settings = _settings(tmp_path, geodetic_frame=frame, observation_date=date)
    _write(settings, _geodetic_rows(_forward(frame)[:4]))
    result = run(settings)
    assert len(result.points) == 4
    # A job-level fact, never repeated on the points.
    assert not result.warnings_of(WarningCode.REALIZATION_OUTSIDE_PERIOD_OF_USE)
    if not warns:
        assert result.job_warnings == ()
        return
    (warning,) = result.job_warnings
    assert warning.code is WarningCode.REALIZATION_OUTSIDE_PERIOD_OF_USE
    assert f"stated in {frame.code} and dated {date.isoformat()}" in warning.message
    period = frames.realization_period_of_use(frame)
    assert f"from {period.first_day.isoformat()}" in warning.message
    if period.last_day is not None:
        assert f"to {period.last_day.isoformat()}" in warning.message
    assert ("before NGA put" in warning.message) is (date < period.first_day)


def test_g2296_far_beyond_its_start_does_not_warn(tmp_path, monkeypatch):
    """G2296 has no end yet (no later realization in the table): 2039 is inside.

    The job's future-date refusal is moved out of the way through the one
    seam, ``job.today``, so the date can be far ahead of the real one.
    """
    monkeypatch.setattr(job, "today", lambda: datetime.date(2040, 1, 1))
    settings = _settings(tmp_path, observation_date=datetime.date(2039, 6, 1))
    _write(settings, _geodetic_rows(_forward(WGS84_G2296)[:2]))
    assert run(settings).job_warnings == ()


def test_the_period_ends_are_derived_from_the_one_table():
    """Each end is the next start minus one day; the newest has none.

    Expected from the three start dates alone (2013-10-16, 2021-01-03,
    2024-01-07): G1762 ends 2021-01-03 - 1 day = 2021-01-02, G2139 ends
    2024-01-07 - 1 day = 2024-01-06, G2296 has no end.
    """
    g1762 = frames.realization_period_of_use(WGS84_G1762)
    g2139 = frames.realization_period_of_use(WGS84_G2139)
    g2296 = frames.realization_period_of_use(WGS84_G2296)
    assert (g1762.first_day, g1762.last_day, g1762.succeeded_by) == (
        datetime.date(2013, 10, 16), datetime.date(2021, 1, 2), "WGS84(G2139)"
    )
    assert (g2139.first_day, g2139.last_day, g2139.succeeded_by) == (
        datetime.date(2021, 1, 3), datetime.date(2024, 1, 6), "WGS84(G2296)"
    )
    assert (g2296.first_day, g2296.last_day, g2296.succeeded_by) == (
        datetime.date(2024, 1, 7), None, None
    )
    for frame in (ITRF2014, ITRF2020, NAD83_2011, NATRF2022):
        assert frames.realization_period_of_use(frame) is None


def test_the_period_dates_are_one_table_the_citations_print():
    """One authority: the warning's date and the frame's citation are one value."""
    for frame, first_day in (
        (WGS84_G1762, datetime.date(2013, 10, 16)),
        (WGS84_G2139, datetime.date(2021, 1, 3)),
        (WGS84_G2296, datetime.date(2024, 1, 7)),
    ):
        assert frames.realization_in_use_from(frame) == first_day
        assert f"Implemented by NGA on {first_day.isoformat()}" in frame.citation
    for frame in (ITRF2014, ITRF2020, NAD83_2011, NATRF2022):
        assert frames.realization_in_use_from(frame) is None


def test_a_same_frame_job_has_no_job_warnings_and_no_evidence(tmp_path):
    settings = _settings(tmp_path, geodetic_frame=NAD83_2011, observation_date=None)
    _write(settings, ["1,43.0,84.5,200.0,A\n"])
    result = run(settings)
    assert result.job_warnings == ()
    conversion = result.points[0].conversion
    for name in ("external_position", "frame_transformation", "htdp_result", "observation_epoch", "transform_height"):
        assert getattr(conversion, name) is None


# ==========================================================================
# 3. Stray frame fields and the new direction's refusals.
# ==========================================================================


@pytest.mark.parametrize(
    "overrides",
    [
        dict(direction=Direction.ZONE_TO_ZONE, source_zone=MI_SOUTH, target_zone=MI_CENTRAL, longitude_convention=None),
        dict(
            direction=Direction.VERTICAL_ONLY,
            source_zone=MI_SOUTH,
            target_zone=None,
            longitude_convention=None,
            vertical_mode=VerticalMode.VERTICAL,
            source_vertical_datum=NGVD29,
            target_vertical_datum=NAVD88,
        ),
    ],
    ids=["zone-to-zone", "vertical-only-zone"],
)
@pytest.mark.parametrize("frame", (WGS84_G2296, WGS84, NATRF2022), ids=["G2296", "WGS84", "NATRF2022"])
def test_a_stray_geodetic_frame_is_refused_by_name(tmp_path, overrides, frame):
    """Interim gate 1, I1, and the lead's W2 probe: a frame the job never reads."""
    settings = _settings(tmp_path, geodetic_frame=frame, observation_date=None, **overrides)
    with pytest.raises(ValueError) as caught:
        run(settings)
    message = str(caught.value)
    assert f"geodetic_frame={frame.code}" in message
    assert "never" in message and "reads" in message
    assert "Leave geodetic_frame at its default, NAD83(2011)" in message


def test_the_default_frame_rebuilt_in_value_is_not_stray(tmp_path):
    settings = _settings(
        tmp_path,
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_SOUTH,
        target_zone=MI_CENTRAL,
        longitude_convention=None,
        geodetic_frame=dataclasses.replace(NAD83_2011),
        observation_date=None,
    )
    _write(settings, ["1,200000.0,4000000.0,200.0,A\n"])
    assert len(run(settings).points) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        dict(),
        dict(direction=Direction.ZONE_TO_GEODETIC, source_zone=MI_SOUTH, target_zone=None),
        dict(direction=Direction.ZONE_TO_ZONE, source_zone=MI_SOUTH, longitude_convention=None),
    ],
    ids=["g2z", "z2g", "z2z"],
)
def test_a_stray_target_geodetic_frame_is_refused_by_name(tmp_path, overrides):
    settings = _settings(tmp_path, target_geodetic_frame=NAD83_2011, **overrides)
    with pytest.raises(ValueError) as caught:
        run(settings)
    message = str(caught.value)
    assert "target_geodetic_frame=NAD83(2011)" in message
    assert "Pass target_geodetic_frame=None" in message


def _g2g(tmp_path, **overrides):
    fields = dict(direction=Direction.GEODETIC_TO_GEODETIC, target_zone=None, target_geodetic_frame=NAD83_2011)
    fields.update(overrides)
    return _settings(tmp_path, **fields)


def test_geodetic_to_geodetic_within_one_frame_is_not_a_conversion(tmp_path):
    for frame in (NAD83_2011, NATRF2022):
        with pytest.raises(FrameTransformationUnavailableError) as caught:
            run(_g2g(tmp_path, geodetic_frame=frame, target_geodetic_frame=frame, observation_date=None))
        assert f"was given {frame.code} at both ends" in str(caught.value)
    # The registry's own refusal for a global frame against itself.
    with pytest.raises(FrameTransformationUnavailableError, match="no identity is registered"):
        run(_g2g(tmp_path, geodetic_frame=WGS84_G2296, target_geodetic_frame=WGS84_G2296))


@pytest.mark.parametrize(
    ("source", "target", "expected", "text"),
    [
        (WGS84_G2296, ITRF2020, FrameTransformationUnavailableError, "decision D4"),
        (ITRF2014, WGS84_G1762, FrameTransformationUnavailableError, "decision D4"),
        (WGS84_G2296, NATRF2022, FrameTransformationUnavailableError, "does not carry NATRF2022"),
        (NATRF2022, ITRF2020, FrameTransformationUnavailableError, "does not carry NATRF2022"),
        (NAD83_2011, NATRF2022, FrameTransformationUnavailableError, "17 cm"),
        (WGS84, NAD83_2011, FrameNotUsableError, "Choose the realization"),
        (NAD83_2011, WGS84, FrameNotUsableError, "Choose the realization"),
    ],
)
def test_geodetic_to_geodetic_refuses_every_unregistered_pair_in_the_registrys_words(
    tmp_path, source, target, expected, text
):
    settings = _g2g(tmp_path, geodetic_frame=source, target_geodetic_frame=target)
    with pytest.raises(expected) as caught:
        run(settings)
    assert text in str(caught.value)


def test_geodetic_to_geodetic_refuses_a_stray_zone_and_a_missing_target(tmp_path):
    with pytest.raises(ValueError) as caught:
        run(_g2g(tmp_path, source_zone=MI_SOUTH, target_zone=MI_CENTRAL))
    message = str(caught.value)
    assert "source_zone=Michigan South" in message and "target_zone=Michigan Central" in message
    assert "Pass source_zone=None and target_zone=None" in message
    with pytest.raises(ValueError, match="needs the frame its output positions"):
        run(_g2g(tmp_path, target_geodetic_frame=None))


def test_geodetic_to_geodetic_refuses_the_vertical_only_mode(tmp_path):
    settings = _g2g(
        tmp_path,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
    )
    with pytest.raises(ValueError, match="pairs only with Direction.VERTICAL_ONLY"):
        run(settings)


def test_the_ellipsoid_gate_still_refuses_natrf2022_with_its_message(tmp_path):
    """D6's rule, and NATRF2022's message unchanged (the 0.7.0 closing gate's HIGH)."""
    settings = _settings(
        tmp_path,
        target_zone=STATEWIDE_2022,
        geodetic_frame=NATRF2022,
        input_height_kind=HeightKind.ELLIPSOID,
        observation_date=None,
    )
    with pytest.raises(FrameTransformationUnavailableError) as caught:
        run(settings)
    message = str(caught.value)
    assert "198.885 m above the NATRF2022 one - 1.115 m apart" in message
    assert "works in NATRF2022" in message


def test_the_ellipsoid_gate_refuses_any_frame_with_no_path_to_nad83():
    """The rule itself, asked directly of a frame the frame gate would refuse first."""
    nad27 = frames.ReferenceFrame(
        code="NAD27",
        name="hand-built by this test",
        ellipsoid_name="Clarke 1866",
        citation="synthetic",
        status=frames.FrameStatus.USABLE,
        epoch_kind=frames.FrameEpochKind.PLATE_FIXED,
        reference_epoch=1927.0,
        htdp_frame=None,
    )
    settings = JobSettings(
        input_path=None,
        output_directory=None,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=nad27,
        input_height_kind=HeightKind.ELLIPSOID,
    )
    with pytest.raises(FrameTransformationUnavailableError) as caught:
        job._require_a_convertible_ellipsoid_height_frame(settings)
    assert "no registered path from NAD27 to NAD83(2011)" in str(caught.value)
    for frame in (NAD83_2011, *FIVE):
        job._require_a_convertible_ellipsoid_height_frame(
            dataclasses.replace(settings, geodetic_frame=frame)
        )


def test_a_frame_where_a_zone_belongs_is_a_type_error(tmp_path):
    """Interim gate 1, I2: TypeError naming it, not AttributeError."""
    with pytest.raises(TypeError, match="JobSettings.target_zone must be a michspc.spc.zones.Zone"):
        run(_settings(tmp_path, target_zone=WGS84_G2296))
    with pytest.raises(TypeError, match="needs a michspc.spc.zones.Zone as its target zone"):
        project_point(43.0, -84.5, NAD83_2011, WGS84_G2296)
    with pytest.raises(TypeError, match="as its source zone"):
        convert.convert_point(1.0, 1.0, NAD83_2011, MI_SOUTH)
    with pytest.raises(TypeError, match="as its target zone"):
        convert.convert_point(1.0, 1.0, MI_SOUTH, NAD83_2011)
    with pytest.raises(TypeError, match="as its source zone"):
        zone_to_geodetic(1.0, 1.0, WGS84_G2296, NAD83_2011)


# ==========================================================================
# 4. The convert-level contract.
# ==========================================================================

EPOCH = htdp.ObservationEpoch(L5_DATE)
H165 = TransformHeight(HeightConvention.ELLIPSOID, 165.0)


def test_an_epoch_or_height_on_a_same_frame_conversion_is_refused():
    with pytest.raises(ValueError, match="was given epoch for a conversion within NAD83\\(2011\\)"):
        project_point(43.0, -84.5, NAD83_2011, MI_SOUTH, epoch=EPOCH)
    with pytest.raises(ValueError, match="was given height"):
        project_point(43.0, -84.5, NAD83_2011, MI_SOUTH, height=H165)
    with pytest.raises(ValueError, match="epoch and height"):
        convert.geodetic_position(43.0, -84.5, NAD83_2011, epoch=EPOCH, height=H165)
    with pytest.raises(ValueError, match="zone_to_geodetic was given epoch"):
        zone_to_geodetic(1.0e5, 4.0e6, MI_SOUTH, NAD83_2011, epoch=EPOCH)


def test_an_htdp_path_requires_both_and_types_them():
    with pytest.raises(ValueError, match="observation epoch of the WGS84\\(G2296\\) position"):
        convert.geodetic_position(43.0, -84.5, WGS84_G2296, height=H165)
    with pytest.raises(ValueError, match="needs the height handed to HTDP"):
        geodetic_to_geodetic(43.0, -84.5, WGS84_G2296, NAD83_2011, epoch=EPOCH)
    with pytest.raises(TypeError, match="ObservationEpoch"):
        project_point(43.0, -84.5, WGS84_G2296, MI_SOUTH, epoch=L5_DATE, height=H165)
    with pytest.raises(TypeError, match="TransformHeight"):
        project_point(43.0, -84.5, WGS84_G2296, MI_SOUTH, epoch=EPOCH, height=165.0)


def test_transform_height_holds_its_value_to_its_convention():
    assert TransformHeight(HeightConvention.NOT_RECORDED, None).height_for_transform_m == 0.0
    assert H165.height_for_transform_m == 165.0
    with pytest.raises(ValueError, match="pass value_m=None"):
        TransformHeight(HeightConvention.NOT_RECORDED, 0.0)
    for bad in (None, float("nan"), True, "165"):
        with pytest.raises(ValueError, match="finite height"):
            TransformHeight(HeightConvention.ORTHOMETRIC, bad)
    with pytest.raises(TypeError):
        TransformHeight(HeightKind.ELLIPSOID, 165.0)


def test_pivot_path_is_the_identity_or_the_htdp_path_and_never_a_new_identity():
    assert pivot_path(NAD83_2011) is FRAME_TRANSFORMATIONS[(NAD83_2011, NAD83_2011)]
    assert pivot_path(NATRF2022) is FRAME_TRANSFORMATIONS[(NATRF2022, NATRF2022)]
    for frame in FIVE:
        assert pivot_path(frame) is FRAME_TRANSFORMATIONS[(frame, NAD83_2011)]
    with pytest.raises(FrameNotUsableError):
        pivot_path(WGS84)


def test_geodetic_position_has_its_own_frame_gate():
    """Interim gate 1, L5: the per-point gate exists, independent of the job's."""
    with pytest.raises(FrameNotUsableError):
        convert.geodetic_position(43.0, -84.5, WGS84)
    with pytest.raises(ValueError, match="observation epoch"):
        convert.geodetic_position(43.0, -84.5, WGS84_G2296)
    truth = L5[WGS84_G2296.code]
    conversion = convert.geodetic_position(43.0, -84.5, WGS84_G2296, epoch=EPOCH, height=H165)
    assert f"{conversion.latitude:.10f}" == truth.lat_out
    assert f"{-conversion.longitude:.10f}" == truth.lonw_out
    assert f"{conversion.pivot_ellipsoid_height:.3f}" == truth.h_out
    assert conversion.external_position == convert.ExternalPosition(
        frame=WGS84_G2296, latitude=43.0, longitude=-84.5, ellipsoid_height=165.0
    )


def test_zone_to_geodetic_within_a_frame_is_convert_point_exactly():
    """The same-frame direction is bit-identical to the call job.run always made."""
    for zone in (MI_SOUTH, STATEWIDE_2022):
        assert zone_to_geodetic(200_000.0, 4_000_000.0, zone, zone.frame) == convert.convert_point(
            200_000.0, 4_000_000.0, zone, zone
        )


def test_the_canonical_records_are_carried_never_the_callers():
    """Interim gate 1, L4: the HTDP frame is read from the registry's record.

    A caller's copy of WGS84(G2296), equal in value - whose htdp_frame is an
    equal-valued COPY of HTDP's record - resolves (it states the registry's
    facts), but the conversion must run on, and carry, the registry's own
    objects: ``htdp_result.source_frame is htdp.WGS84_G2296`` and the
    external position's frame ``is`` the registry's.
    """
    htdp_copy = dataclasses.replace(htdp.WGS84_G2296)
    assert htdp_copy == htdp.WGS84_G2296 and htdp_copy is not htdp.WGS84_G2296
    caller = dataclasses.replace(WGS84_G2296, htdp_frame=htdp_copy)
    assert caller == WGS84_G2296 and caller is not WGS84_G2296
    for conversion in (
        project_point(43.0, -84.5, caller, MI_SOUTH, epoch=EPOCH, height=H165),
        convert.geodetic_position(43.0, -84.5, caller, epoch=EPOCH, height=H165),
        geodetic_to_geodetic(43.0, -84.5, caller, NAD83_2011, epoch=EPOCH, height=H165),
    ):
        assert conversion.htdp_result.source_frame is htdp.WGS84_G2296
        assert conversion.external_position.frame is WGS84_G2296
        assert conversion.frame is NAD83_2011
    reverse = zone_to_geodetic(
        200_000.0, 4_000_000.0, MI_SOUTH, caller, epoch=EPOCH, height=H165
    )
    assert reverse.htdp_result.target_frame is htdp.WGS84_G2296
    assert reverse.external_position.frame is WGS84_G2296


def test_a_point_conversion_cannot_carry_half_its_evidence_or_contradict_it():
    whole = project_point(43.0, -84.5, WGS84_G2296, MI_SOUTH, epoch=EPOCH, height=H165)
    for name in ("external_position", "frame_transformation", "htdp_result", "observation_epoch", "transform_height"):
        with pytest.raises(ValueError, match="present together or not at all"):
            dataclasses.replace(whole, **{name: None})
    with pytest.raises(ValueError, match="is not HTDP's output position"):
        dataclasses.replace(whole, latitude=43.0)
    with pytest.raises(ValueError, match="HTDP ran at 2025-06-15"):
        dataclasses.replace(whole, observation_epoch=htdp.ObservationEpoch(EPOCH_2020))
    with pytest.raises(ValueError, match="the pivot is tagged WGS84"):
        dataclasses.replace(whole, frame=WGS84_G2296)
    with pytest.raises(ValueError, match="is not the height handed to HTDP"):
        dataclasses.replace(
            whole,
            external_position=dataclasses.replace(whole.external_position, ellipsoid_height=166.0),
        )


# ==========================================================================
# 5. The write guard's successors (W4).
#
# W3 pinned three things: a transformed job converts and is NOT written
# (``test_a_transformed_job_converts_and_is_not_written``), the guard names
# each of its three conditions (``test_the_guard_names_every_reason_it_holds``),
# and a same-frame job still writes (kept below, unchanged). W4 built the
# disclosure the guard waited for and removed it
# (``exports.require_a_disclosable_job``, ``UndisclosedTransformationError``).
# The first two are SUPERSEDED by the successors here - the same five inputs
# now write, each pinned against HTDP's print, and each of the guard's three
# conditions now leads to a disclosed archive - not deleted.
# ==========================================================================


def _transformed_jobs(tmp_path):
    rows_geo = ["1,43.0,84.5,165.000,P\n"]
    yield "g2z", _settings(tmp_path / "a"), rows_geo
    yield "z2g", _settings(
        tmp_path / "b",
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
    ), [f"1,{project_point(43.0, -84.5, NAD83_2011, MI_SOUTH).target_northing!r},"
        f"{project_point(43.0, -84.5, NAD83_2011, MI_SOUTH).target_easting!r},165.000,P\n"]
    yield "g2g", _g2g(tmp_path / "c"), rows_geo
    yield "g2g-into-nad83-of-nad83", _g2g(
        tmp_path / "d", geodetic_frame=NAD83_2011, target_geodetic_frame=WGS84_G2296
    ), rows_geo
    yield "vertical-only", _settings(
        tmp_path / "e",
        direction=Direction.VERTICAL_ONLY,
        target_zone=None,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    ), rows_geo


def test_the_jobs_the_guard_refused_now_write_and_disclose(tmp_path):
    """SUCCESSOR of ``test_a_transformed_job_converts_and_is_not_written``.

    The guard's five inputs, exactly as W3 built them, at the L5 date so
    HTDP's truth is frozen for them (htdp_w3_anchors; the position is L5's,
    43.0 N 84.5 W, an orthometric Z of 165.000 handed to HTDP as h - the
    record's own input height). Each now writes an archive whose record
    carries the FRAME TRANSFORMATION block, and whose positions are HTDP's:

    * g2z: the projected pivot, which is HTDP's printed G2296 -> NAD 83
      output (checked at the printed digit) projected into MI-C;
    * z2g and the reverse g2g: the files' position is HTDP's printed
      NAD 83 -> G2296 output, within half the written 8-place unit plus half
      HTDP's 1e-10 print (plus the 1e-11 inverse round trip on z2g);
    * g2g: HTDP's printed G2296 -> NAD 83 output, same tolerance;
    * vertical-only: the pivot the grids were read at is HTDP's print, and
      the columns mirror the input.
    """
    forward = L5[WGS84_G2296.code]
    reverse = L5R[WGS84_G2296.code]
    dd_tolerance = 0.5e-8 + 0.5e-10
    for label, settings, rows in _transformed_jobs(tmp_path):
        settings = dataclasses.replace(settings, observation_date=L5_DATE)
        settings.input_path.parent.mkdir(parents=True, exist_ok=True)
        _write(settings, rows)
        result = run(settings)
        written = exports.write_all(result)
        archive = written["archive"]
        assert archive.exists(), label
        record = member_text(archive, "_README.txt")
        assert record.count("\nFRAME TRANSFORMATION\n") == 1, label
        assert build_report(result).count("\nFRAME TRANSFORMATION\n") == 1
        (point,) = result.points
        if label in ("g2z", "g2g", "vertical-only"):
            assert f"{point.conversion.latitude:.10f}" == forward.lat_out, label
            assert f"{-point.conversion.longitude:.10f}" == forward.lonw_out, label
        if label == "g2z":
            expected = project_point(
                float(forward.lat_out), -float(forward.lonw_out), NAD83_2011, MI_CENTRAL
            )
            clean = member_text(archive, "_MI-C.csv").split(",")
            assert abs(float(clean[1]) - expected.target_northing) <= 0.5e-4 + GRID_TOLERANCE_M
            assert abs(float(clean[2]) - expected.target_easting) <= 0.5e-4 + GRID_TOLERANCE_M
        elif label == "vertical-only":
            clean = member_text(archive, "_VERTICAL.csv").split(",")
            assert clean[1:3] == ["43.00000000", "84.50000000"]
        else:
            dd = member_text(archive, "_DD.csv").split(",")
            truth = forward if label == "g2g" else reverse
            extra = 1e-11 if label == "z2g" else 0.0
            assert abs(float(dd[1]) - float(truth.lat_out)) <= dd_tolerance + extra, label
            assert abs(float(dd[2]) - float(truth.lonw_out)) <= dd_tolerance + extra, label


def test_each_condition_the_guard_held_now_leads_to_a_disclosed_archive(tmp_path):
    """SUCCESSOR of ``test_the_guard_names_every_reason_it_holds``.

    The guard refused on any of three conditions: a point carrying a frame
    transformation, the GEODETIC_TO_GEODETIC direction, a stated observation
    date. The guard is gone - both names are absent from ``exports`` - and a
    job meeting each condition writes, its record naming the observation
    date the guard used to quote.
    """
    assert not hasattr(exports, "require_a_disclosable_job")
    assert not hasattr(exports, "UndisclosedTransformationError")
    for label, settings, rows in _transformed_jobs(tmp_path):
        settings.input_path.parent.mkdir(parents=True, exist_ok=True)
        _write(settings, rows)
        result = run(settings)
        assert all(point.conversion.is_transformed for point in result.points), label
        assert result.settings.observation_date == EPOCH_2020
        archive = exports.write_all(result)["archive"]
        record = member_text(archive, "_README.txt")
        assert "Observation date   2020-01-01, decimal year 2020.0" in record, label
        if result.settings.direction is Direction.GEODETIC_TO_GEODETIC:
            assert "Conversion         geodetic to geodetic" in record


def test_a_same_frame_job_still_writes(tmp_path):
    """The control: the guard refuses transformed jobs, not jobs."""
    settings = _settings(tmp_path, geodetic_frame=NAD83_2011, observation_date=None)
    _write(settings, ["1,43.0,84.5,200.0,A\n"])
    written = exports.write_all(run(settings))
    assert all(path.exists() for path in written.values())


# ==========================================================================
# Interim gate 2 of the WGS 84 build (review/gate-wgs84-2/output.md):
# M1, L1, L2 and L4.
# ==========================================================================

# --------------------------------------------------------------------------
# M1: an ELLIPSOID job in a vertical mode on a path OUT of NAD 83 - the one
# case where the pivot h and the target-frame h differ, so H = h - N with the
# wrong one would go unseen. The reviewer's job: NAD 83 43.0 N 84.5 W at
# h = 165.000 m into WGS84(G2296), 2025-06-15, NAVD88 to NAVD88.
#
# Expected, derived: on a path out of NAD 83 the NAD 83 h IS the supplied one
# (HTDP is handed it; convert.PointConversion.pivot_ellipsoid_height), so
# H = 165.000 - N, with N read through the program's NGS-anchored GEOID18
# reader at the NAD 83 position, 43.0 / -84.5: N = -33.085 (asserted, 3
# places), so H = 165.000 + 33.085 = 198.085 m. The reviewer's seed S07
# (the target-frame h, HTDP's 163.901 for G2296, L5_REVERSE_RECORDS) wrote
# 163.901 + 33.085 = 196.986 m, 1.099 m low.
# --------------------------------------------------------------------------

def _m1_separation() -> float:
    separation = geoid.geoid_height(43.0, -84.5, geoid.default_grid(geoid.GEOID18_MODEL))
    assert f"{separation:.3f}" == "-33.085"
    return separation


def _m1_check(tmp_path, settings, lines):
    _write(settings, lines)
    result = run(settings)
    (point,) = result.points
    separation = _m1_separation()
    # The pivot the separation is read at is 43.0 / -84.5 itself (to the
    # projection round trip, 1e-11 deg, on the grid input) - a 1e-11 deg move
    # changes N by far less than 1e-9 m.
    assert abs(point.output_elevation - (165.0 - separation)) <= 1e-6
    assert abs(point.output_elevation - 198.085) <= 0.0006
    assert abs(point.output_elevation - 196.986) > 1.0  # not seed S07's
    # The written file carries it too, at its 4 places.
    archive = exports.write_all(result)["archive"]
    (row,) = [
        line for line in member_text(archive, "_DD.csv").splitlines() if line
    ]
    assert abs(float(row.split(",")[3]) - (165.0 - separation)) <= 0.5e-4 + 1e-6
    return point


def test_z2g_ellipsoid_in_a_vertical_mode_uses_the_nad83_h(tmp_path):
    """M1, the reviewer's own job: ZONE_TO_GEODETIC MI-S -> WGS84(G2296)."""
    grid = project_point(43.0, -84.5, NAD83_2011, MI_SOUTH)
    settings = _settings(
        tmp_path,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        geodetic_frame=WGS84_G2296,
        input_height_kind=HeightKind.ELLIPSOID,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
        observation_date=L5_DATE,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    point = _m1_check(
        tmp_path, settings,
        [f"1,{grid.target_northing!r},{grid.target_easting!r},165.000,P\n"],
    )
    # And the target-frame h really is the other number (HTDP's print).
    assert f"{point.conversion.target_frame_ellipsoid_height:.3f}" == L5R[WGS84_G2296.code].h_out


def test_g2g_reverse_ellipsoid_in_a_vertical_mode_uses_the_nad83_h(tmp_path):
    """M1: GEODETIC_TO_GEODETIC NAD83(2011) -> WGS84(G2296), the same position."""
    settings = _settings(
        tmp_path,
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        geodetic_frame=NAD83_2011,
        target_geodetic_frame=WGS84_G2296,
        input_height_kind=HeightKind.ELLIPSOID,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
        observation_date=L5_DATE,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    point = _m1_check(tmp_path, settings, ["1,43.0,-84.5,165.000,P\n"])
    assert f"{point.conversion.target_frame_ellipsoid_height:.3f}" == L5R[WGS84_G2296.code].h_out


# --------------------------------------------------------------------------
# L1: the "today" seam's UTC half. In a UTC container the two clocks are one,
# and west of UTC (Michigan) the later is UTC, so a test against the local
# date alone cannot tell max from min. The clocks are set apart here.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "local,utc",
    [
        # A Michigan evening: local is still the 20th, UTC already the 21st.
        (datetime.date(2026, 10, 20), datetime.date(2026, 10, 21)),
        # East of UTC after midnight local: the local clock is the later.
        (datetime.date(2026, 10, 21), datetime.date(2026, 10, 20)),
    ],
)
def test_today_is_the_later_of_the_local_and_utc_dates(monkeypatch, local, utc):
    monkeypatch.setattr(job, "_local_and_utc_dates", lambda: (local, utc))
    assert job.today() == datetime.date(2026, 10, 21)


def test_an_evening_session_dated_in_utc_is_not_refused_as_future(tmp_path, monkeypatch):
    """The property #70 records: local 2026-10-20, UTC 2026-10-21 - a GNSS
    processor dates the session 2026-10-21, and the job accepts it; the 22nd,
    after both clocks, is still refused, naming the 21st."""
    monkeypatch.setattr(
        job,
        "_local_and_utc_dates",
        lambda: (datetime.date(2026, 10, 20), datetime.date(2026, 10, 21)),
    )
    settings = _settings(
        tmp_path,
        observation_date=datetime.date(2026, 10, 21),
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    _write(settings, ["1,43.0,-84.5,165.000,P\n"])
    assert len(run(settings).points) == 1
    later = dataclasses.replace(settings, observation_date=datetime.date(2026, 10, 22))
    with pytest.raises(ValueError, match=r"after the day this job runs \(2026-10-21\)"):
        run(later)


# --------------------------------------------------------------------------
# L2: the realization-period warning, true in each direction. The reviewer's
# input: MI-S to WGS84(G2139) on 2019-03-01 - before G2139's period began
# (2021-01-03, the PERIOD_CASES table above; it ended 2024-01-06, the day
# before G2296 began).
# --------------------------------------------------------------------------

_G2139_SPAN = (
    "from 2021-01-03 to 2024-01-06 (NGA replaced it with WGS84(G2296) on 2024-01-07)"
)


def test_the_period_warning_on_a_path_out_of_nad83_names_the_output(tmp_path):
    grid = project_point(43.0, -84.5, NAD83_2011, MI_SOUTH)
    settings = _settings(
        tmp_path,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        geodetic_frame=WGS84_G2139,
        observation_date=datetime.date(2019, 3, 1),
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    _write(settings, [f"1,{grid.target_northing!r},{grid.target_easting!r},165.000,P\n"])
    (warning,) = run(settings).job_warnings
    assert warning.code is WarningCode.REALIZATION_OUTSIDE_PERIOD_OF_USE
    assert warning.message == (
        "This job writes its positions in WGS84(G2139), the realization "
        "requested as its output, at the observation date 2019-03-01 - outside "
        f"WGS84(G2139)'s period of use, which is {_G2139_SPAN}. The date is "
        "before NGA put WGS84(G2139) into use, so WGS84(G2139) was not the "
        "realization in use on that date. The job is converted as requested. "
        "Check that WGS84(G2139) is the realization wanted for positions "
        "observed on that date."
    )
    assert "stated in" not in warning.message


def test_the_period_warning_on_a_path_into_nad83_names_the_input(tmp_path):
    """The same frame and date the other way: WGS84(G2139) geodetic into MI-S.
    The positions ARE stated in G2139 here, so the label is the question."""
    settings = _settings(
        tmp_path,
        target_zone=MI_SOUTH,
        geodetic_frame=WGS84_G2139,
        observation_date=datetime.date(2019, 3, 1),
    )
    _write(settings, ["1,43.0,84.5,165.000,P\n"])
    (warning,) = run(settings).job_warnings
    assert warning.message == (
        "The positions are stated in WGS84(G2139) and dated 2019-03-01, outside "
        f"WGS84(G2139)'s period of use, which is {_G2139_SPAN}. The date is "
        "before NGA put WGS84(G2139) into use, so a receiver on that date was "
        "not broadcasting it. Reprocessed data can legitimately carry a later "
        "realization, so the job is converted as stated - but a file labelled "
        "with the wrong realization looks exactly like this. Check which "
        "realization the positions are in."
    )


def test_the_period_warning_on_g2g_reverse_names_the_output(tmp_path):
    settings = _settings(
        tmp_path,
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        geodetic_frame=NAD83_2011,
        target_geodetic_frame=WGS84_G2139,
        observation_date=datetime.date(2019, 3, 1),
    )
    _write(settings, ["1,43.0,84.5,165.000,P\n"])
    (warning,) = run(settings).job_warnings
    assert warning.message.startswith("This job writes its positions in WGS84(G2139)")


# --------------------------------------------------------------------------
# L4: an HTDP refusal through job.run names the point and the refused
# position's OWN frame, with advice that fits where the position came from.
# --------------------------------------------------------------------------

def test_the_reviewers_grid_row_outside_the_velocity_window_names_the_point(tmp_path):
    """The reviewer's row ``1,0,0,,a``, ZONE_TO_GEODETIC MI-S -> WGS84(G2296).

    MI-S's grid origin inverts to a NAD 83 position far west of Michigan -
    derived here by the program's NCAT-verified inverse, 32.026364 N
    127.914179 W - whose velocity lookup is outside the window. That position
    is the NAD83(2011) pivot, handed to HTDP on the way OUT of NAD 83, so the
    refusal names NAD83(2011), the point, and the zone and unit - and gives
    no longitude-sign advice, the file having held no longitude.
    """
    pivot = convert.to_geodetic(0.0, 0.0, MI_SOUTH)
    latitude, longitude = pivot[0], pivot[1]
    assert (f"{latitude:.6f}", f"{longitude:.6f}") == ("32.026364", "-127.914179")
    settings = _settings(
        tmp_path,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        geodetic_frame=WGS84_G2296,
        observation_date=L5_DATE,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    _write(settings, ["1,0,0,,a\n"])
    with pytest.raises(htdp.HtdpVelocityGridError) as raised:
        run(settings)
    message = str(raised.value)
    assert isinstance(raised.value, htdp.HtdpRefusal)
    assert message.startswith(
        "point 1: cannot transform the position the file's Michigan South "
        "northing and easting give - latitude 32.026364, longitude -127.914179 "
        "(signed, negative west), in NAD83(2011) - to WGS84(G2296): its "
        "velocity-model lookup position"
    ), message
    assert message.endswith(
        "Check that the point is in Michigan, and that the file holds Michigan "
        "South coordinates in m."
    ), message
    assert "(WGS84(G2296))" not in message
    assert "longitude is negative west" not in message
    assert "longitudes are written" not in message
    # The refused position, as data, is the pivot.
    assert (raised.value.latitude, raised.value.longitude) == (latitude, longitude)


@pytest.mark.parametrize(
    "overrides,frame_code",
    [
        # WGS84(G2296) geodetic into MI-S, 84.5 read as EAST under the
        # negative-west convention: the input itself is refused, in its frame.
        (dict(longitude_convention=LongitudeConvention.NEGATIVE_WEST), "WGS84(G2296)"),
        # NAD83(2011) geodetic out to G2296: the input is the NAD 83 position.
        (
            dict(
                direction=Direction.GEODETIC_TO_GEODETIC,
                target_zone=None,
                geodetic_frame=NAD83_2011,
                target_geodetic_frame=WGS84_G2296,
                longitude_convention=LongitudeConvention.NEGATIVE_WEST,
            ),
            "NAD83(2011)",
        ),
    ],
    ids=["g2z-into-nad83", "g2g-out-of-nad83"],
)
def test_a_geodetic_row_outside_the_window_names_the_point_and_the_convention(
    tmp_path, overrides, frame_code
):
    settings = _settings(tmp_path, observation_date=L5_DATE, **overrides)
    _write(settings, ["7,43.0,84.5,165.000,P\n"])
    with pytest.raises(htdp.HtdpVelocityGridError) as raised:
        run(settings)
    message = str(raised.value)
    assert message.startswith(
        "point 7: cannot transform the position the file supplied - latitude "
        f"43.000000, longitude 84.500000 (signed, negative west), in {frame_code} - "
    ), message
    assert message.endswith(
        "Check that the point is in Michigan, and that the file's longitudes are "
        "written negative west, as this job states: a longitude written in the "
        "other convention lands on the other side of the world."
    ), message


# --------------------------------------------------------------------------
# Interim gate 2 re-confirmation, N2: the fallback branch of
# _point_named_htdp_refusal - every HTDP refusal other than the velocity-
# window one keeps its own class and is prefixed with its point.
# --------------------------------------------------------------------------


def test_any_other_htdp_refusal_keeps_its_class_and_names_the_point(
    tmp_path, monkeypatch
):
    """An FRMXYZ non-convergence (HTDP's STOP 666) cannot be reached from a
    Michigan position, so it is forced: htdp.to_nad83, which convert.py calls
    by attribute, raises HtdpConvergenceError("forced"). The job's restatement
    must be the same class, read "point 2: forced", and leave HTDP's own words
    untouched; the first row converts before the second is refused."""
    real = htdp.to_nad83
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise htdp.HtdpConvergenceError("forced")
        return real(*args, **kwargs)

    monkeypatch.setattr(htdp, "to_nad83", flaky)
    settings = _settings(tmp_path)
    _write(settings, ["1,43.0,84.5,165.000,P\n", "2,43.1,84.6,165.000,Q\n"])
    with pytest.raises(htdp.HtdpConvergenceError) as raised:
        run(settings)
    assert type(raised.value) is htdp.HtdpConvergenceError
    assert str(raised.value) == "point 2: forced"
