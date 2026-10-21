"""Work package W4 of the WGS 84 build: a transformed job writes, and says so.

docs/PLAN-wgs84.md section 3.6, decisions D1, D5, D6, D7, D9 and D10;
docs/DESIGN.md #70. W3 connected HTDP v3.6.0 to the conversion and held every
transformed job back from the disk until its outputs could state what was
done. This package builds that statement and removes the hold. Pinned here:

1. **End to end, through the archive**: ``job.run`` -> ``write_all`` ->
   unzip -> parse, for every direction with a transformed end
   (GEODETIC_TO_ZONE, ZONE_TO_GEODETIC, GEODETIC_TO_GEODETIC both ways,
   VERTICAL_ONLY on a WGS 84 / ITRF input), under each height convention of
   D6, and the flagship HORIZONTAL_AND_VERTICAL job (a WGS 84 GNSS position
   and h in, a NAD 83 position and a NAVD 88 elevation out). Every cell is
   compared with NGS's own printed output (``tests/fixtures/htdp_anchors.py``,
   ``htdp_w3_anchors.py``) through an independent leg derived in a comment -
   HTDP's print itself, or HTDP's print carried through the program's
   NCAT-verified projection or GEOID18 reader - latitude, longitude and height
   separately, never through a ``max()``.
2. **The job record's FRAME TRANSFORMATION block**, as exact text for one
   representative job per direction, and each of its facts separately: the
   decimal year is HTDP's, the commit is the one constant, the frames and
   ellipsoids are the registry's, the Helmert sets are ``htdp_data``'s, the
   height-convention counts are the points', the measured figures are
   DESIGN.md #70's, and the block is absent on every same-frame job.
3. **GEODETIC_TO_GEODETIC's own record**: FROM and TO frame blocks, its own
   METHOD and verification, and the ABSENCE of every sentence that is true
   only of a job with a zone (the #42 finding-3 class).
4. **The audit CSV's frame columns**: present only on a transformed job,
   appended after Description, every position and ellipsoid height named by
   its frame - and no same-frame header moved.
5. **The verifiers check each file against the position THAT FILE STATES**:
   the target frame's on a geodetic target - not the NAD 83 pivot, which is a
   metre away (plan section 3.6's hazard; 0.7.1's MEDIUM 1 class) - and the
   grid on a zone target. A file built from the pivot is refused.
6. **The DMS sibling** exists on both geodetic-target directions (#67).

The same-frame byte pins are ``tests/test_orthometric_regression.py`` (the 18
v0.5.0 digests, untouched) and ``tests/test_same_frame_outputs_unchanged.py``
(one job of each direction, record included, digested before W4 existed).
"""

from __future__ import annotations

import csv
import dataclasses
import datetime
import io
import re
import zipfile
from pathlib import Path

import pytest

from michspc.fileio import exports, geoid, pnezd
from michspc.fileio import formatting as fmt
from michspc.fileio import report
from michspc.fileio.writers import WriteError
from michspc.job import (
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    applied_frame_transformation,
    run,
)
from michspc.spc import htdp, htdp_data
from michspc.spc.convert import HeightConvention, project_point
from michspc.spc.frames import (
    ITRF2014,
    ITRF2020,
    NAD83_2011,
    WGS84_G1762,
    WGS84_G2139,
    WGS84_G2296,
)
from michspc.spc.units import METERS
from michspc.spc.vertical import NAVD88, NGVD29, HeightKind
from michspc.spc.zones import MI_CENTRAL, MI_SOUTH
from tests import test_orthometric_regression as regression
from tests.conftest import member_text
from tests.fixtures.htdp_anchors import HTDP_RUNS
from tests.fixtures.htdp_w3_anchors import L5_RECORDS, L5_REVERSE_RECORDS

REPO = Path(__file__).resolve().parents[1]

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
EPOCH_2020 = datetime.date(2020, 1, 1)


def _michigan(records):
    """The Michigan lattice of a W0 run: P064 onward (the fixture's docstring)."""
    return [r for r in records if r.name.startswith("P0") and int(r.name[1:4]) >= 64]


def _forward(frame):
    return _michigan(RUNS[f"fwd_f{MENU[frame.code]}_2020.0"].records)


def _reverse(frame):
    return _michigan(RUNS[f"rev_f{MENU[frame.code]}_2020.0"].records)


def _not_recorded(record) -> bool:
    # The reader's rule (pnezd): an exactly-zero Z means "not recorded".
    return float(record.h_in) == 0.0


# --------------------------------------------------------------------------
# Tolerances, each derived once. The HTDP-side figures are W3's
# (tests/test_job_wgs84.py), re-derived here because each is relied on here.
# --------------------------------------------------------------------------

HTDP_PRINT_DEG = 0.5e-10
"""Half of HTDP's printed unit of a degree, 1e-10: the program reproduces
HTDP's print, so its unrounded value lies within this of the printed one."""

DD_CELL_DEG = 0.5e-8 + HTDP_PRINT_DEG
"""A written decimal-degree cell (8 places, ``formatting.latitude``) against
HTDP's print: half the written unit plus HTDP_PRINT_DEG."""

DMS_CELL_DEG = 0.5e-5 / 3600.0 + HTDP_PRINT_DEG + 1e-12
"""A DMS cell (five places of a second) against HTDP's print: half a place of
the cell, 1.39e-9 deg, plus HTDP_PRINT_DEG, plus 1e-12 deg for the float sum
of d + m/60 + s/3600 in the test's own reader."""

GRID_TOLERANCE_M = 1.2e-5
"""W3's derivation: two HTDP print steps of 0.5e-10 deg x (pi/180) x 6.39e6 m
(the largest radius of curvature in Michigan), x 1.0001 for k, = 1.12e-5 m per
component, rounded up."""

GRID_CELL_M = 0.5e-4 + GRID_TOLERANCE_M
"""A metre grid cell (4 places) against HTDP's pivot projected."""

ROUND_TRIP_DEG = 1e-11
"""A grid input inverted back to its NAD 83 anchor: the projection round trip,
measured by W3 at 1e-11 deg and asserted where relied on."""

HEIGHT_M = 0.0005 + 1e-6
"""A height against HTDP's 1 mm print: half its unit, plus 1e-6 m for a geoid
separation read at the program's pivot rather than HTDP's printed one."""


def _dms_degrees(cell: str) -> float:
    """The test's OWN reading of a ``42-43-57.00000 N`` cell, signed.

    Written here rather than taken from ``michspc.fileio.dms`` so the DMS cells
    are read back by arithmetic the program did not supply.
    """
    angle, letter = cell.split(" ")
    degrees, minutes, seconds = angle.split("-")
    value = int(degrees) + int(minutes) / 60.0 + float(seconds) / 3600.0
    return -value if letter in ("S", "W") else value


def _members(archive: Path) -> dict[str, str]:
    with zipfile.ZipFile(archive) as opened:
        return {name: opened.read(name).decode("utf-8") for name in opened.namelist()}


def _csv_rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text, newline="")))


def _audit(archive: Path) -> list[dict[str, str]]:
    """The audit CSV, keyed by heading - every heading unique (asserted)."""
    rows = _csv_rows(member_text(archive, "_full.csv"))
    header = rows[0]
    assert len(set(header)) == len(header), "duplicate audit headings"
    assert all(len(row) == len(header) for row in rows[1:])
    return [dict(zip(header, row)) for row in rows[1:]]


def _settings(folder: Path, **fields) -> JobSettings:
    base = dict(
        input_path=folder / "in.csv",
        output_directory=folder,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.POSITIVE_WEST,
        geodetic_frame=WGS84_G2296,
        observation_date=L5_DATE,
    )
    base.update(fields)
    return JobSettings(**base)


def _write_job(folder: Path, rows: str, **fields):
    """Run and write one job; ``(result, archive)``."""
    folder.mkdir(parents=True, exist_ok=True)
    settings = _settings(folder, **fields)
    settings.input_path.write_text(rows, encoding="utf-8")
    result = run(settings)
    written = exports.write_all(result)
    return result, written["archive"]


# ==========================================================================
# The representative jobs: one per direction, all at the L5 position and
# date (interim gate 1's L5 input, 43.0 N 84.5 W, 165.000 m, 2025-06-15),
# whose HTDP truth is frozen in htdp_w3_anchors. Each has a second point with
# a blank Z, so two height conventions appear in every record.
# ==========================================================================

_NAD83_SOUTH = project_point(43.0, -84.5, NAD83_2011, MI_SOUTH)
"""An INPUT, not an expected value: the NAD 83 position 43.0 N 84.5 W (the L5
reverse records' input) projected into MI-S, written with repr so the file
holds the doubles exactly. The job inverts it back to within ROUND_TRIP_DEG."""

REPRESENTATIVE = {
    "g2z": (
        "1,43.0,84.5,165.000,P\n2,43.0,84.5,,BLANK\n",
        dict(),
    ),
    "z2g": (
        f"1,{_NAD83_SOUTH.target_northing!r},{_NAD83_SOUTH.target_easting!r},165.000,P\n"
        f"2,{_NAD83_SOUTH.target_northing!r},{_NAD83_SOUTH.target_easting!r},,BLANK\n",
        dict(
            direction=Direction.ZONE_TO_GEODETIC,
            source_zone=MI_SOUTH,
            target_zone=None,
            input_height_kind=HeightKind.ELLIPSOID,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        ),
    ),
    "g2g_forward": (
        # The flagship: a WGS 84 GNSS position and h in, NAD 83 and NAVD 88 out.
        "1,43.0,-84.5,165.000,P\n2,43.0,-84.5,,BLANK\n",
        dict(
            direction=Direction.GEODETIC_TO_GEODETIC,
            target_zone=None,
            target_geodetic_frame=NAD83_2011,
            input_height_kind=HeightKind.ELLIPSOID,
            vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
            source_vertical_datum=NAVD88,
            target_vertical_datum=NAVD88,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        ),
    ),
    "g2g_reverse": (
        # NAD 83 to G1762 on a date after G1762's period of use: the job-level
        # realization warning of D9 (2025-06-15 is after 2021-01-02).
        "1,43.0,84.5,165.000,P\n2,43.0,84.5,,BLANK\n",
        dict(
            direction=Direction.GEODETIC_TO_GEODETIC,
            target_zone=None,
            geodetic_frame=NAD83_2011,
            target_geodetic_frame=WGS84_G1762,
        ),
    ),
    "vertical_only": (
        "1,43.0,84.5,165.000,P\n2,43.0,84.5,,BLANK\n",
        dict(
            direction=Direction.VERTICAL_ONLY,
            target_zone=None,
            geodetic_frame=ITRF2020,
            input_height_kind=HeightKind.ELLIPSOID,
            vertical_mode=VerticalMode.VERTICAL,
            source_vertical_datum=NAVD88,
            target_vertical_datum=NAVD88,
        ),
    ),
}


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    """Every representative job, run and written once: name -> (result, archive)."""
    root = tmp_path_factory.mktemp("w4_representative")
    return {
        name: _write_job(root / name, rows, **fields)
        for name, (rows, fields) in REPRESENTATIVE.items()
    }


def _record(archive: Path) -> str:
    return member_text(archive, "_README.txt")


def _block(record: str) -> str:
    """The FRAME TRANSFORMATION block: its heading to the blank line before the
    next METHOD block (every transformed job carries a geoid model here)."""
    start = record.index("\nFRAME TRANSFORMATION\n") + 1
    end = record.index("\nGeoid model        ", start)
    return record[start:end]


# ==========================================================================
# 1. End to end through the archive, against HTDP's print.
# ==========================================================================


def test_g2z_writes_htdps_pivot_projected(written):
    """WGS84(G2296) in, MI-S out, orthometric Z.

    Expected northing and easting: the L5 record's PRINTED NAD 83 output
    (42.9999914726 N, 84.4999892398 W for G2296) projected by the program's
    NCAT-verified projection, within GRID_CELL_M - two independent legs. The
    audit's pivot cells are that print within DD_CELL_DEG; its external
    position is the input as given, 43.0 / -84.5, exactly; the Z is the
    orthometric input, unchanged (an elevation is in no frame).
    """
    truth = L5[WGS84_G2296.code]
    _result, archive = written["g2z"]
    expected = project_point(float(truth.lat_out), -float(truth.lonw_out), NAD83_2011, MI_SOUTH)
    rows = pnezd.parse_lines(member_text(archive, "_MI-S.csv").splitlines(), path="<g2z>").rows
    assert abs(rows[0].northing - expected.target_northing) <= GRID_CELL_M
    assert abs(rows[0].easting - expected.target_easting) <= GRID_CELL_M
    assert rows[0].elevation == 165.0
    assert rows[1].elevation is None
    audit = _audit(archive)
    assert abs(float(audit[0]["Latitude (NAD83(2011))"]) - float(truth.lat_out)) <= DD_CELL_DEG
    assert abs(float(audit[0]["Longitude (NAD83(2011), neg west)"]) + float(truth.lonw_out)) <= DD_CELL_DEG
    assert audit[0]["Latitude (WGS84(G2296))"] == "43.00000000"
    assert audit[0]["Longitude (WGS84(G2296), neg west)"] == "-84.50000000"
    assert audit[0]["Latitude (WGS84(G2296), DMS)"] == "43-00-00.00000 N"
    assert audit[0]["Longitude (WGS84(G2296), DMS)"] == "84-30-00.00000 W"
    assert abs(_dms_degrees(audit[0]["Latitude (NAD83(2011), DMS)"]) - float(truth.lat_out)) <= DMS_CELL_DEG
    assert abs(_dms_degrees(audit[0]["Longitude (NAD83(2011), DMS)"]) + float(truth.lonw_out)) <= DMS_CELL_DEG
    assert [row["Height convention"] for row in audit] == [
        HeightConvention.ORTHOMETRIC.value,
        HeightConvention.NOT_RECORDED.value,
    ]


def test_z2g_writes_htdps_global_position_not_the_pivot(written):
    """MI-S in, WGS84(G2296) out, ELLIPSOID Z: the files state HTDP's output.

    Expected: the L5 reverse record for G2296 (NAD 83 43.0 / 84.5 W, 165.000
    m, carried to 2025-06-15): 43.0000085430 N, 84.5000107720 W, h 163.901 -
    within DD_CELL_DEG + ROUND_TRIP_DEG in the DD file (negative west), within
    DMS_CELL_DEG + ROUND_TRIP_DEG in the DMS file, and the Z column (h in the
    TARGET frame, plan D6) within HEIGHT_M + half its 4-place unit. The NAD 83
    pivot - 43.0 / -84.5 itself - is about 0.95 m north-west of that, so a
    file built from it fails each comparison by 30,000 tolerances.
    """
    truth = L5R[WGS84_G2296.code]
    _result, archive = written["z2g"]
    dd = pnezd.parse_lines(member_text(archive, "_DD.csv").splitlines(), path="<dd>").rows
    assert abs(dd[0].northing - float(truth.lat_out)) <= DD_CELL_DEG + ROUND_TRIP_DEG
    assert abs(dd[0].easting + float(truth.lonw_out)) <= DD_CELL_DEG + ROUND_TRIP_DEG
    assert abs(dd[0].elevation - float(truth.h_out)) <= HEIGHT_M + 0.5e-4
    assert abs(dd[0].northing - 43.0) > 5e-6  # not the pivot
    dms_rows = _csv_rows(member_text(archive, "_DMS.csv"))
    assert abs(_dms_degrees(dms_rows[0][1]) - float(truth.lat_out)) <= DMS_CELL_DEG + ROUND_TRIP_DEG
    assert abs(_dms_degrees(dms_rows[0][2]) + float(truth.lonw_out)) <= DMS_CELL_DEG + ROUND_TRIP_DEG
    audit = _audit(archive)
    assert abs(float(audit[0]["Ellipsoid height (WGS84(G2296))"]) - float(truth.h_out)) <= HEIGHT_M + 0.5e-4
    assert audit[0]["Ellipsoid height before transformation (NAD83(2011), m)"] == "165.000"
    assert abs(
        float(audit[0]["Ellipsoid height after transformation (WGS84(G2296), m)"]) - float(truth.h_out)
    ) <= HEIGHT_M + 0.5e-3
    assert abs(float(audit[0]["Latitude (NAD83(2011))"]) - 43.0) <= 0.5e-8 + ROUND_TRIP_DEG
    assert abs(float(audit[0]["Latitude (WGS84(G2296))"]) - float(truth.lat_out)) <= DD_CELL_DEG + ROUND_TRIP_DEG
    assert audit[1]["Ellipsoid height before transformation (NAD83(2011), m)"] == "N/A"
    assert audit[1]["Ellipsoid height after transformation (WGS84(G2296), m)"] == "N/A"


def test_the_flagship_g2g_with_vertical_writes_nad83_and_navd88(written):
    """WGS84(G2296) GNSS position and h in; NAD83(2011) position and NAVD 88 out.

    Expected, all from the L5 record for G2296 (HTDP's print) and the
    program's GEOID18 reader at that printed pivot: the DD file's position is
    HTDP's 42.9999914726 N, 84.4999892398 W within DD_CELL_DEG; the DMS file
    within DMS_CELL_DEG; the elevation is h(NAD 83) - N = 166.099 - (-33.085)
    = 199.184 m within HEIGHT_M plus half the 4-place unit. The reviewer's
    unguarded seed (gate 1, L5) wrote 198.085 m.
    """
    truth = L5[WGS84_G2296.code]
    _result, archive = written["g2g_forward"]
    dd = pnezd.parse_lines(member_text(archive, "_DD.csv").splitlines(), path="<dd>").rows
    assert abs(dd[0].northing - float(truth.lat_out)) <= DD_CELL_DEG
    assert abs(dd[0].easting + float(truth.lonw_out)) <= DD_CELL_DEG
    separation = geoid.geoid_height(
        float(truth.lat_out), -float(truth.lonw_out), geoid.default_grid(geoid.GEOID18_MODEL)
    )
    assert f"{separation:.3f}" == "-33.085"
    assert abs(dd[0].elevation - (float(truth.h_out) - separation)) <= HEIGHT_M + 0.5e-4
    assert abs(dd[0].elevation - 199.184) <= 0.0006
    assert dd[1].elevation is None
    dms_rows = _csv_rows(member_text(archive, "_DMS.csv"))
    assert abs(_dms_degrees(dms_rows[0][1]) - float(truth.lat_out)) <= DMS_CELL_DEG
    assert abs(_dms_degrees(dms_rows[0][2]) + float(truth.lonw_out)) <= DMS_CELL_DEG
    audit = _audit(archive)
    # The NAD 83 h HTDP printed is the h of H = h - N.
    assert audit[0]["Ellipsoid height after transformation (NAD83(2011), m)"] == truth.h_out
    assert audit[0]["Ellipsoid height before transformation (WGS84(G2296), m)"] == "165.000"
    assert audit[0]["Ellipsoid height in (WGS84(G2296), m)"] == "165.0000"
    assert audit[0]["Ellipsoid height (NAD83(2011), m)"] == truth.h_out
    assert audit[0]["Target vertical datum"] == "NAVD88"


def test_g2g_reverse_writes_htdps_g1762_position(written):
    """NAD83(2011) in, WGS84(G1762) out, positive west, orthometric Z.

    Expected: the L5 reverse record for G1762, at HTDP's printed digit - the
    orthometric Z 165.000 is handed to HTDP as h, which is the record's own
    input height - within DD_CELL_DEG in the DD file (positive west, so +W).
    The Z passes unchanged.
    """
    truth = L5R[WGS84_G1762.code]
    result, archive = written["g2g_reverse"]
    assert f"{result.points[0].conversion.external_position.latitude:.10f}" == truth.lat_out
    dd = pnezd.parse_lines(member_text(archive, "_DD.csv").splitlines(), path="<dd>").rows
    assert abs(dd[0].northing - float(truth.lat_out)) <= DD_CELL_DEG
    assert abs(dd[0].easting - float(truth.lonw_out)) <= DD_CELL_DEG
    assert dd[0].elevation == 165.0
    dms_rows = _csv_rows(member_text(archive, "_DMS.csv"))
    assert abs(_dms_degrees(dms_rows[0][1]) - float(truth.lat_out)) <= DMS_CELL_DEG
    assert abs(_dms_degrees(dms_rows[0][2]) + float(truth.lonw_out)) <= DMS_CELL_DEG


def test_vertical_only_on_itrf2020_mirrors_and_converts_the_height(written):
    """ITRF2020 position and h in, the same position out and H in NAVD 88.

    Expected: the clean export mirrors the input's position text exactly
    (43.00000000, 84.50000000 as the file wrote it); the elevation is the L5
    ITRF2020 record's printed NAD 83 h minus GEOID18's N at its printed pivot,
    within HEIGHT_M plus half the 4-place unit. No DMS sibling: a
    vertical-only job is not a conversion to geodetic (#67).
    """
    truth = L5[ITRF2020.code]
    _result, archive = written["vertical_only"]
    members = _members(archive)
    assert not any(name.endswith("_DMS.csv") for name in members)
    clean = _csv_rows(member_text(archive, "_VERTICAL.csv"))
    assert clean[0][1:3] == ["43.00000000", "84.50000000"]
    separation = geoid.geoid_height(
        float(truth.lat_out), -float(truth.lonw_out), geoid.default_grid(geoid.GEOID18_MODEL)
    )
    assert abs(float(clean[0][3]) - (float(truth.h_out) - separation)) <= HEIGHT_M + 0.5e-4
    audit = _audit(archive)
    assert abs(float(audit[0]["Latitude (NAD83(2011))"]) - float(truth.lat_out)) <= DD_CELL_DEG
    assert audit[0]["Ellipsoid height after transformation (NAD83(2011), m)"] == truth.h_out
    assert audit[0]["Latitude (ITRF2020)"] == "43.00000000"


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
@pytest.mark.parametrize("kind", [HeightKind.ORTHOMETRIC, HeightKind.ELLIPSOID], ids=["orth", "ellip"])
def test_every_frame_writes_g2g_forward_at_htdps_print(tmp_path, frame, kind):
    """The W0 Michigan lattice, every frame, both height kinds, through the archive.

    WGS 84/ITRF in, NAD83(2011) out at 2020-01-01. HTDP is handed each record's
    own input height under both kinds (ORTHOMETRIC hands H in place of h, and
    the file's Z IS the record's input), and 0.000 is NOT_RECORDED, handed as
    h = 0 - the record's input there too. So every DD cell is HTDP's print
    within DD_CELL_DEG; the Z is h out (ELLIPSOID) or the Z in (ORTHOMETRIC).
    """
    records = _forward(frame)
    rows = "".join(f"{r.name},{r.lat_in},{r.lonw_in},{r.h_in},A\n" for r in records)
    _result, archive = _write_job(
        tmp_path,
        rows,
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        geodetic_frame=frame,
        target_geodetic_frame=NAD83_2011,
        input_height_kind=kind,
        observation_date=EPOCH_2020,
    )
    dd = {row.point_id: row for row in pnezd.parse_lines(
        member_text(archive, "_DD.csv").splitlines(), path="<dd>").rows}
    audit = {row["Point"]: row for row in _audit(archive)}
    for r in records:
        assert abs(dd[r.name].northing - float(r.lat_out)) <= DD_CELL_DEG, r.name
        assert abs(dd[r.name].easting - float(r.lonw_out)) <= DD_CELL_DEG, r.name
        convention = audit[r.name]["Height convention"]
        if _not_recorded(r):
            assert dd[r.name].elevation is None
            assert convention == HeightConvention.NOT_RECORDED.value
        elif kind is HeightKind.ELLIPSOID:
            assert abs(dd[r.name].elevation - float(r.h_out)) <= HEIGHT_M + 0.5e-4, r.name
            assert convention == HeightConvention.ELLIPSOID.value
        else:
            assert dd[r.name].elevation == float(r.h_in)
            assert convention == HeightConvention.ORTHOMETRIC.value
        # The external position is the input, exactly as given.
        assert audit[r.name][f"Latitude ({frame.code})"] == f"{float(r.lat_in):.8f}"
        assert audit[r.name][f"Longitude ({frame.code}, neg west)"] == f"{-float(r.lonw_in):.8f}"


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_every_frame_writes_z2g_at_htdps_print(tmp_path, frame):
    """MI-C grid in, every frame out, ELLIPSOID, through DD, DMS and audit.

    Input: each reverse record's NAD 83 position projected into MI-C (an
    input, as ``_NAD83_SOUTH`` is). Expected: HTDP's printed output within
    DD_CELL_DEG + ROUND_TRIP_DEG (DD, negative west), DMS_CELL_DEG +
    ROUND_TRIP_DEG (DMS), and the Z, h in ``frame``, within HEIGHT_M + half
    its unit.
    """
    records = _reverse(frame)
    rows = []
    for r in records:
        point = project_point(float(r.lat_in), -float(r.lonw_in), NAD83_2011, MI_CENTRAL)
        rows.append(f"{r.name},{point.target_northing!r},{point.target_easting!r},{r.h_in},A\n")
    _result, archive = _write_job(
        tmp_path,
        "".join(rows),
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_CENTRAL,
        target_zone=None,
        geodetic_frame=frame,
        input_height_kind=HeightKind.ELLIPSOID,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        observation_date=EPOCH_2020,
    )
    dd = {row.point_id: row for row in pnezd.parse_lines(
        member_text(archive, "_DD.csv").splitlines(), path="<dd>").rows}
    dms_rows = {row[0]: row for row in _csv_rows(member_text(archive, "_DMS.csv"))}
    for r in records:
        tolerance = DD_CELL_DEG + ROUND_TRIP_DEG
        assert abs(dd[r.name].northing - float(r.lat_out)) <= tolerance, r.name
        assert abs(dd[r.name].easting + float(r.lonw_out)) <= tolerance, r.name
        dms_tolerance = DMS_CELL_DEG + ROUND_TRIP_DEG
        assert abs(_dms_degrees(dms_rows[r.name][1]) - float(r.lat_out)) <= dms_tolerance
        assert abs(_dms_degrees(dms_rows[r.name][2]) + float(r.lonw_out)) <= dms_tolerance
        if _not_recorded(r):
            assert dd[r.name].elevation is None
        else:
            assert abs(dd[r.name].elevation - float(r.h_out)) <= HEIGHT_M + 0.5e-4, r.name


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_every_frame_writes_g2z_and_g2g_reverse(tmp_path, frame):
    """The other two directions on every frame, through the archive.

    G2Z: the forward lattice into MI-C; expected grid = HTDP's printed pivot
    projected, within GRID_CELL_M. G2G reverse: NAD 83 in (negative west),
    the frame out; expected = HTDP's print within DD_CELL_DEG.
    """
    forward = _forward(frame)
    _result, archive = _write_job(
        tmp_path / "g2z",
        "".join(f"{r.name},{r.lat_in},{r.lonw_in},{r.h_in},A\n" for r in forward),
        target_zone=MI_CENTRAL,
        geodetic_frame=frame,
        observation_date=EPOCH_2020,
    )
    grid = {row.point_id: row for row in pnezd.parse_lines(
        member_text(archive, "_MI-C.csv").splitlines(), path="<g2z>").rows}
    for r in forward:
        expected = project_point(float(r.lat_out), -float(r.lonw_out), NAD83_2011, MI_CENTRAL)
        assert abs(grid[r.name].northing - expected.target_northing) <= GRID_CELL_M, r.name
        assert abs(grid[r.name].easting - expected.target_easting) <= GRID_CELL_M, r.name

    reverse = _reverse(frame)
    _result, archive = _write_job(
        tmp_path / "g2g",
        "".join(f"{r.name},{r.lat_in},-{r.lonw_in},{r.h_in},A\n" for r in reverse),
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        geodetic_frame=NAD83_2011,
        target_geodetic_frame=frame,
        input_height_kind=HeightKind.ELLIPSOID,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        observation_date=EPOCH_2020,
    )
    dd = {row.point_id: row for row in pnezd.parse_lines(
        member_text(archive, "_DD.csv").splitlines(), path="<dd>").rows}
    for r in reverse:
        assert abs(dd[r.name].northing - float(r.lat_out)) <= DD_CELL_DEG, r.name
        assert abs(dd[r.name].easting + float(r.lonw_out)) <= DD_CELL_DEG, r.name


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_vertical_only_on_every_frame_is_l5s_h_minus_n(tmp_path, frame):
    """VERTICAL_ONLY, ELLIPSOID, on each frame, through the archive (plan D8).

    Expected: L5's printed NAD 83 h for the frame minus GEOID18's N at its
    printed pivot (166.096 to 166.099 + 33.085), within HEIGHT_M + half the
    written unit; the position columns mirror the input.
    """
    truth = L5[frame.code]
    _result, archive = _write_job(
        tmp_path,
        "1,43.0,84.5,165.000,P\n",
        **dict(REPRESENTATIVE["vertical_only"][1], geodetic_frame=frame),
    )
    clean = _csv_rows(member_text(archive, "_VERTICAL.csv"))
    separation = geoid.geoid_height(
        float(truth.lat_out), -float(truth.lonw_out), geoid.default_grid(geoid.GEOID18_MODEL)
    )
    assert clean[0][1:3] == ["43.00000000", "84.50000000"]
    assert abs(float(clean[0][3]) - (float(truth.h_out) - separation)) <= HEIGHT_M + 0.5e-4


def test_the_velocity_cells_are_the_grid_node_at_a_node(tmp_path):
    """An independent leg for the velocity: initvl.f's own node.

    NAD 83 44.0 N 85.0 W to WGS84(G1762) at 2020-01-01. That position is grid
    node I = (275 - 250)/0.5 + 1 = 51, J = (44 - 24)/0.5 + 1 = 41, initvl.f
    ``DATA B(139639), ... / 0.30, -16.18, 0.00 /``; G1762 is ITRF2008, the
    grid's own frame, so HTDP applies the node's velocity to within 1e-4
    mm/yr (``tests/test_htdp.py``, the node test). The cells, to 0.01 mm/yr,
    are therefore 0.30, -16.18 and 0.00.
    """
    _result, archive = _write_job(
        tmp_path,
        "1,44.0,-85.0,0.000,NODE\n",
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        geodetic_frame=NAD83_2011,
        target_geodetic_frame=WGS84_G1762,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        observation_date=EPOCH_2020,
    )
    (row,) = _audit(archive)
    assert row["Velocity north (WGS84(G1762), mm/yr)"] == "0.30"
    assert row["Velocity east (WGS84(G1762), mm/yr)"] == "-16.18"
    assert row["Velocity up (WGS84(G1762), mm/yr)"] == "0.00"


def test_every_velocity_cell_is_the_points_own_and_in_w0s_measured_range(written):
    """Every velocity cell is HTDP's for that point, and inside W0's range.

    The ranges are W0's measurement over the in-box lattice (plan section
    2.1, RECON.md section 1.4): into NAD 83 N -1.87..-0.12, E +1.76..+2.51,
    U -1.25..-1.01 mm/yr; out of NAD 83 into WGS84(G2296) - the row W0
    measured, RECON.md Supplement C - N -2.18..+1.70, E -16.94..-15.34,
    U -0.33. Widened by the 0.005 of the cell's rounding. Out of NAD 83 into
    WGS84(G1762), which IS ITRF2008, the grid's own frame: the up velocity is
    the grid's, 0.00 at every node (htdp_data.GRID6_WINDOW), carried 15 -> 1
    -> 15 - an identity to below 1e-4 mm/yr - so the cell is 0.00.
    """
    into = ((-1.87, -0.12), (1.76, 2.51), (-1.25, -1.01))
    out_of_g2296 = ((-2.18, 1.70), (-16.94, -15.34), (-0.33, -0.33))
    for name, (result, archive) in written.items():
        path = applied_frame_transformation(result.settings)
        if path.target is WGS84_G1762:
            for row in _audit(archive):
                assert row["Velocity up (WGS84(G1762), mm/yr)"] == "0.00"
            continue
        assert path.target in (NAD83_2011, WGS84_G2296), name
        ranges = out_of_g2296 if path.target.is_time_dependent else into
        for point, row in zip(result.points, _audit(archive)):
            velocity = point.conversion.htdp_result.velocity
            for axis, value, (low, high) in zip(
                ("north", "east", "up"),
                (velocity.north_mm_per_yr, velocity.east_mm_per_yr, velocity.up_mm_per_yr),
                ranges,
            ):
                cell = row[f"Velocity {axis} ({path.target.code}, mm/yr)"]
                assert cell == f"{value:.2f}", (name, axis)
                assert low - 0.005 <= float(cell) <= high + 0.005, (name, axis, cell)


def test_the_same_day_writes_no_velocity_and_says_so(tmp_path):
    """Observed on 2010-01-01, the NAD 83 reference epoch's day: HTDP applies
    the Helmert alone (htdp.f:3245), so every velocity cell is N/A - never
    0.00 - and the record says why."""
    result, archive = _write_job(
        tmp_path, "1,43.0,84.5,165.000,P\n", observation_date=datetime.date(2010, 1, 1)
    )
    assert result.points[0].conversion.htdp_result.velocity is None
    (row,) = _audit(archive)
    for axis in ("north", "east", "up"):
        assert row[f"Velocity {axis} (NAD83(2011), mm/yr)"] == "N/A"
    flat = " ".join(_block(_record(archive)).split())
    assert (
        "The observation date is 2010-01-01, the day of the NAD83(2011) "
        "reference epoch, so the propagation span is zero and HTDP applied no "
        "velocity: the _full.csv export's velocity cells read N/A."
    ) in flat
    assert "Each point's velocity" not in flat


# ==========================================================================
# 2. The FRAME TRANSFORMATION block: exact text per direction, then each fact.
#
# Derivations used in the literals below:
# * 2025-06-15 is day 165 of a 365-day year (31+28+31+30+31+14), so HTDP's
#   DATE is 2025 + 165/365 = 2025.4520547945206 as the shortest repr of the
#   double (htdp.f:7913-7919; ObservationEpoch.decimal_year).
# * The Helmert rows are htdp_data.IGS_CONVENTION's, printed by repr: iopt 17
#   (ITRF2020, used for G2296 and ITRF2020), 15 (ITRF2008, used for G1762)
#   and 1 (NAD 83), each with the htdp.f lines its HelmertParameters.source
#   names and the name HELMERT_SET_NAMES copies from SETTP's comment.
# * Each job has two points: point 1 carries 165.000 (ORTHOMETRIC, or
#   ELLIPSOID where the job says so), point 2 a blank Z (NOT_RECORDED).
# * The Helmert epoch is the INPUT epoch: the observation date's DATE when the
#   source is time-dependent, 2010.0 when it is NAD83(2011) (htdp.f:3230).
# * Velocity "0.5-degree": (50 - 24) / 52 cells (htdp_data.GRID6_*).
# ==========================================================================

_HELMERT_ITRF2020 = """\
  From ITRF94 to ITRF2020 (also IGS20 and IGb20) - used for {frame}
    htdp.f:3970-3984, reference epoch 2010.0
    tx ty tz         -0.0129  0.00241  0.02827  m
    dtx dty dtz      -0.00079  0.0007  0.00124  m/yr
    rx ry rz         -0.00029978  0.00042037  0.00031714  arcsec
    drx dry drz      -1.347e-05  1.514e-05  1.973e-05  arcsec/yr
    scale dscale     5.109e-11  7.201e-11  /yr
"""

_HELMERT_ITRF2008 = """\
  From ITRF94 to ITRF2008 (also IGS08 and IGb08) - used for {frame}
    htdp.f:3923-3937, reference epoch 1997.0
    tx ty tz         -0.00243  -0.00389  0.01365  m
    dtx dty dtz      -0.00079  0.0006  0.00134  m/yr
    rx ry rz         -0.00012467  0.00022355  6.065e-05  arcsec
    drx dry drz      -1.347e-05  1.514e-05  1.973e-05  arcsec/yr
    scale dscale     -1.71504e-09  1.0201e-10  /yr
"""

_HELMERT_NAD83 = """\
  From ITRF94 to NAD 83 - used for NAD83(2011)
    htdp.f:3652-3666, reference epoch 1997.0
    tx ty tz         0.991  -1.9072  -0.5129  m
    dtx dty dtz      0.0  0.0  0.0  m/yr
    rx ry rz         0.02579  0.00965  0.01166  arcsec
    drx dry drz      5.32e-05  -0.0007423  -3.16e-05  arcsec/yr
    scale dscale     0.0  0.0  /yr
"""

_FROM_G2296 = """\
From               WGS84(G2296) - World Geodetic System 1984, realization
                   G2296, on the WGS 84 ellipsoid, at the observation date
"""
_TO_G2296 = """\
To                 WGS84(G2296) - World Geodetic System 1984, realization
                   G2296, on the WGS 84 ellipsoid, at the observation date
"""
_FROM_NAD83 = """\
From               NAD83(2011) - North American Datum of 1983, 2011
                   realization, on the GRS 80 ellipsoid, at its reference
                   epoch 2010.0
"""
_TO_NAD83 = """\
To                 NAD83(2011) - North American Datum of 1983, 2011
                   realization, on the GRS 80 ellipsoid, at its reference
                   epoch 2010.0
"""

_OBSERVED = """\
Observation date   2025-06-15, decimal year 2025.4520547945206 - HTDP's own
                   conversion of the calendar date (htdp.f:7913-7919). One
                   date for the whole job: each of its 2 point(s) is taken as
                   observed on it, because the input file carries no date of
                   its own.
Software           NGS HTDP v3.6.0 (April 7, 2025), github.com/noaa-ngs/HTDP
                   commit 59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c, as
                   transcribed by this program (michspc.spc.htdp).

"""

# RECORDED SUPERSESSION - DESIGN.md #70, interim gate 2 finding L3: the
# frozen W4 text stated W0's bound as though it held at every date. It was
# measured to hold over observation dates 1990-01-01 to 2035-12-31 (the
# lead's re-measurement, review/wgs84-gate2/, extending W0's 1997.0 to 2026.8),
# and now says so;
# the representative jobs are dated 2025-06-15, inside that range, so no
# further sentence follows. W4's text is kept as _ROUND_TRIP_AT_W4 for the
# respelling of G2G_NO_GEOID_AT_W4 below.
_ROUND_TRIP = """\
Round trip         HTDP's forward and reverse transformations are not exact
                   inverses. Measured on HTDP's own arithmetic, unrounded, for
                   observation dates from 1990-01-01 to 2035-12-31 and heights
                   handed to HTDP from -250 m to 610 m, a Michigan position
                   carried out and back fails to return by up to 9.2e-6 m
                   north, 6.4e-5 m east and 4.3e-6 m up
                   (review/wgs84-w0/RECON.md section 5, review/wgs84-gate2/,
                   DESIGN.md #70). This program reproduces HTDP's arithmetic,
                   and so its round trip too.
"""

_ROUND_TRIP_AT_W4 = """\
Round trip         HTDP's forward and reverse transformations are not exact
                   inverses. Measured on HTDP's own arithmetic, unrounded, a
                   Michigan position carried out and back fails to return by
                   up to 9.2e-6 m north, 6.4e-5 m east and 4.3e-6 m up
                   (review/wgs84-w0/RECON.md section 5, DESIGN.md #70). This
                   program reproduces HTDP's arithmetic, and so its round trip
                   too.
"""

_VERIFIED = """\

Verified           This program's transcription of HTDP is held by its test
                   suite to NGS's own Fortran source, committed unmodified at
                   review/wgs84-w0/htdp-v3.6.0/: every constant transcribed
                   must equal the one NGS wrote, number for number. The
                   transformation itself is checked against HTDP. NGS's source
                   was compiled and run, and 1,846 of its printed records -
                   every frame offered, both directions and the round trip,
                   across Michigan and its lakes - are held in the test suite
                   as fixed reference values. This software reproduces them to
                   the digit HTDP prints, 1e-10 degree and 1 mm.
"""

_NOT_RECORDED_LINES = """\
  no height recorded, transformed at an ellipsoid height of 0 m:
    1 of 2 points. HTDP was handed an ellipsoid height of 0 m, and the Z stays
    blank. Measured: at 600 m of real height, Michigan's highest ground, the
    horizontal result moves at most 0.18 mm north and 0.13 mm east (DESIGN.md
    #70).

"""

_ORTHOMETRIC_LINES = """\
  orthometric height, used in place of the ellipsoid height:
    1 of 2 points. An elevation belongs to no frame, so the transformation
    leaves the Z unchanged; HTDP was handed the elevation in place of the
    ellipsoid height. Measured: the horizontal result moves 1.2e-5 m per 40 m
    of height difference, so at most 0.012 mm where the geoid separation is
    about 35 m, as in Michigan (DESIGN.md #70).
"""

_HEIGHTS_HEAD = """\
Heights            The height HTDP was handed, and its convention, is stated
                   per point in the _full.csv export. This job:
"""


def _velocity(target: str, intraplate: bool) -> str:
    """The Velocity paragraph for a job into ``target`` (wrapping derived below)."""
    if target == "NAD83(2011)":
        return """\
Velocity           HTDP's model for its velocity region 6: a 0.5-degree grid
                   of ITRF2008 velocities (initvl.f), interpolated bilinearly
                   at the point's position mapped to ITRF2008, then carried
                   into NAD83(2011), the output frame. The grid's up velocity
                   is 0.00 at every node this program carries, so the up rate
                   is the two frames' own translation and scale rates. Each
                   point's velocity - north, east and up, mm/yr, in
                   NAD83(2011) - is in the _full.csv export.

"""
    return f"""\
Velocity           HTDP's model for its velocity region 6: a 0.5-degree grid
                   of ITRF2008 velocities (initvl.f), interpolated bilinearly
                   at the point's position mapped to ITRF2008, then carried
                   into {target}, the output frame. The grid's up velocity
                   is 0.00 at every node this program carries, so the up rate
                   is the two frames' own translation and scale rates. Each
                   point's velocity - north, east and up, mm/yr, in
                   {target} - is in the _full.csv export.

"""


def _direction(path) -> str:
    """The Direction paragraph: frames.FrameTransformation.direction_statement,
    QUOTED - wrapped at the record's label column, never reworded (the
    registry's sentence is pinned by its own suite, test_frames_wgs84)."""
    import textwrap

    body = textwrap.wrap(
        path.direction_statement, width=78 - 19, break_long_words=False, break_on_hyphens=False
    )
    return "\n".join([f"{'Direction':<19}{body[0]}"] + [f"{'':<19}{line}" for line in body[1:]]) + "\n\n"


def _helmert_head(source: str, target: str, epoch: str) -> str:
    import textwrap

    text = (
        f"HTDP's IGS-convention sets (SETTP's /tranpa/, htdp.f:3229), each from ITRF94 "
        f"to a frame, linearized, and evaluated at the input epoch, {epoch}. The "
        f"position goes from {source} to ITRF94 by the first set below with all "
        f"fourteen parameters negated, then from ITRF94 to {target} by the second. "
        f"Rotations in arcseconds, as HTDP stores them:"
    )
    body = textwrap.wrap(text, width=59, break_long_words=False, break_on_hyphens=False)
    return "\n".join([f"{'Helmert':<19}{body[0]}"] + [f"{'':<19}{line}" for line in body[1:]]) + "\n"


def _expected_block(name: str) -> str:
    """The exact block each representative job must print.

    Assembled from the literal pieces above, each derived in the section
    comment; only the quoted registry sentence (``_direction``) and the
    Helmert lead-in's wrapping are re-wrapped here, because the record must
    QUOTE the first and the second's words are the literal above.
    """
    g2296_to_nad83 = frames_path(WGS84_G2296, NAD83_2011)
    nad83_to_g2296 = frames_path(NAD83_2011, WGS84_G2296)
    nad83_to_g1762 = frames_path(NAD83_2011, WGS84_G1762)
    itrf2020_to_nad83 = frames_path(ITRF2020, NAD83_2011)
    decimal = "2025.4520547945206"
    if name == "g2z":
        return (
            "FRAME TRANSFORMATION\n\n" + _FROM_G2296 + _TO_NAD83 + _OBSERVED
            + _direction(g2296_to_nad83)
            + _helmert_head("WGS84(G2296)", "NAD83(2011)", decimal)
            + _HELMERT_ITRF2020.format(frame="WGS84(G2296)") + _HELMERT_NAD83 + "\n"
            + _velocity("NAD83(2011)", True)
            + _HEIGHTS_HEAD + _ORTHOMETRIC_LINES + _NOT_RECORDED_LINES
            + _ROUND_TRIP + _VERIFIED
        )
    if name == "z2g":
        ellipsoid = """\
  ellipsoid height, transformed with the position:
    1 of 2 points. The supplied height is part of the 3-D position HTDP
    transforms, and the ellipsoid height out is the WGS84(G2296) one, above
    the WGS 84 ellipsoid.
"""
        return (
            "FRAME TRANSFORMATION\n\n" + _FROM_NAD83 + _TO_G2296 + _OBSERVED
            + _direction(nad83_to_g2296)
            + _helmert_head("NAD83(2011)", "WGS84(G2296)", "2010.0")
            + _HELMERT_NAD83 + _HELMERT_ITRF2020.format(frame="WGS84(G2296)") + "\n"
            + _velocity("WGS84(G2296)", False)
            + _HEIGHTS_HEAD + ellipsoid + _NOT_RECORDED_LINES
            + _ROUND_TRIP + _VERIFIED
        )
    if name == "g2g_forward":
        ellipsoid = """\
  ellipsoid height, transformed with the position:
    1 of 2 points. The supplied height is part of the 3-D position HTDP
    transforms, and the ellipsoid height out is the NAD83(2011) one, above the
    GRS 80 ellipsoid.
"""
        return (
            "FRAME TRANSFORMATION\n\n" + _FROM_G2296 + _TO_NAD83 + _OBSERVED
            + _direction(g2296_to_nad83)
            + _helmert_head("WGS84(G2296)", "NAD83(2011)", decimal)
            + _HELMERT_ITRF2020.format(frame="WGS84(G2296)") + _HELMERT_NAD83 + "\n"
            + _velocity("NAD83(2011)", True)
            + _HEIGHTS_HEAD + ellipsoid + _NOT_RECORDED_LINES
            # No Verified paragraph: a geodetic-to-geodetic job carries the
            # HTDP verification in its METHOD section instead.
            + _ROUND_TRIP
        )
    if name == "g2g_reverse":
        to_g1762 = """\
To                 WGS84(G1762) - World Geodetic System 1984, realization
                   G1762, on the WGS 84 ellipsoid, at the observation date
"""
        return (
            "FRAME TRANSFORMATION\n\n" + _FROM_NAD83 + to_g1762 + _OBSERVED
            + _direction(nad83_to_g1762)
            + _helmert_head("NAD83(2011)", "WGS84(G1762)", "2010.0")
            + _HELMERT_NAD83 + _HELMERT_ITRF2008.format(frame="WGS84(G1762)") + "\n"
            + _velocity("WGS84(G1762)", False)
            + _HEIGHTS_HEAD + _ORTHOMETRIC_LINES + _NOT_RECORDED_LINES
            + _ROUND_TRIP
        )
    if name == "vertical_only":
        ellipsoid = """\
  ellipsoid height, transformed with the position:
    1 of 2 points. The supplied height is part of the 3-D position HTDP
    transforms, and the ellipsoid height out is the NAD83(2011) one, above the
    GRS 80 ellipsoid.
"""
        from_itrf2020 = """\
From               ITRF2020 - International Terrestrial Reference Frame 2020,
                   on the GRS 80 ellipsoid, at the observation date
"""
        return (
            "FRAME TRANSFORMATION\n\n" + from_itrf2020 + _TO_NAD83 + _OBSERVED
            + _direction(itrf2020_to_nad83)
            + _helmert_head("ITRF2020", "NAD83(2011)", decimal)
            + _HELMERT_ITRF2020.format(frame="ITRF2020") + _HELMERT_NAD83 + "\n"
            + _velocity("NAD83(2011)", True)
            + _HEIGHTS_HEAD + ellipsoid + _NOT_RECORDED_LINES
            # RECORDED SUPERSESSION - DESIGN.md #70, plan W4b: the frozen
            # text stated a zone the job does not have. At W4 this block
            # ended with _VERIFIED, the Verified line a ZONE job carries
            # because its own HOW THIS SOFTWARE IS VERIFIED is about the
            # projection; a vertical-only geodetic job has no projection, and
            # since W4b carries the HTDP checks in its own zone-less METHOD
            # section (as geodetic to geodetic does), not here.
            + _ROUND_TRIP
        )
    raise AssertionError(name)


def frames_path(source, target):
    from michspc.spc.frames import require_frame_path

    return require_frame_path(source, target)


@pytest.mark.parametrize("name", list(REPRESENTATIVE))
def test_the_block_is_exactly_this_text(written, name):
    _result, archive = written[name]
    assert _block(_record(archive)) == _expected_block(name)


def test_the_block_appears_once_on_every_transformed_job(written):
    for name, (_result, archive) in written.items():
        assert _record(archive).count("\nFRAME TRANSFORMATION\n") == 1, name


def test_the_decimal_year_printed_is_htdps_derived_from_the_date(written):
    """The figure printed equals ObservationEpoch.decimal_year EXACTLY, and both
    equal the hand derivation 2025 + 165/365."""
    for name, (result, archive) in written.items():
        match = re.search(r"decimal year (\S+) - HTDP's own", _record(archive))
        printed = float(match.group(1))
        assert printed == htdp.ObservationEpoch(result.settings.observation_date).decimal_year
        assert printed == result.points[0].conversion.observation_epoch.decimal_year
        assert printed == 2025.0 + 165.0 / 365.0, name


def test_the_decimal_year_follows_the_date_and_is_not_typed(tmp_path):
    """A second date: 2024-02-29 is day 59 of a 366-day year, 2024 + 59/366."""
    _result, archive = _write_job(
        tmp_path, "1,43.0,84.5,165.000,P\n", observation_date=datetime.date(2024, 2, 29)
    )
    match = re.search(r"decimal year (\S+) - HTDP's own", _record(archive))
    assert float(match.group(1)) == 2024.0 + 59.0 / 366.0
    assert "2024-02-29, decimal year" in _record(archive)
    (row,) = _audit(archive)
    assert row["Observation date"] == "2024-02-29"
    assert float(row["Observation epoch (decimal year)"]) == 2024.0 + 59.0 / 366.0


def test_the_commit_and_version_come_from_the_one_constant(written):
    """The Software line is htdp_data's three constants, and the commit is the
    one the frozen anchors were captured from (their provenance header)."""
    assert htdp_data.HTDP_COMMIT == "59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c"
    fixture = (REPO / "tests" / "fixtures" / "htdp_anchors.py").read_text(encoding="utf-8")
    assert f"commit     {htdp_data.HTDP_COMMIT}" in fixture
    for _name, (_result, archive) in written.items():
        block = _block(_record(archive))
        software = block[block.index("Software"):block.index("\n\n", block.index("Software"))]
        flat = " ".join(software.split())
        assert (
            f"NGS HTDP v{htdp_data.HTDP_VERSION} ({htdp_data.HTDP_VERSION_DATE}), "
            f"github.com/noaa-ngs/HTDP commit {htdp_data.HTDP_COMMIT}"
        ) in flat


def test_the_frames_named_are_the_registrys_records(written):
    for name, (result, archive) in written.items():
        path = applied_frame_transformation(result.settings)
        flat = " ".join(_block(_record(archive)).split())
        for label, frame in (("From", path.source), ("To", path.target)):
            assert (
                f"{label} {frame.code} - {frame.name}, on the {frame.ellipsoid_name} ellipsoid"
            ) in flat, name
        # The WGS 84 realizations are on the WGS 84 ellipsoid, never GRS 80.
        if "WGS84(" in path.source.code:
            assert "on the WGS 84 ellipsoid" in flat


def test_the_height_convention_counts_are_the_points(tmp_path):
    """Three points, three conventions are impossible in one job (the kind is
    the job's), so: five points, three orthometric and two blank - counts
    derived from the rows written."""
    rows = (
        "1,43.0,84.5,165.000,A\n2,43.1,84.5,170.000,B\n3,43.2,84.5,175.000,C\n"
        "4,43.0,84.6,,D\n5,43.1,84.6,0.000,E\n"
    )
    _result, archive = _write_job(tmp_path, rows)
    block = _block(_record(archive))
    assert "  orthometric height, used in place of the ellipsoid height:\n    3 of 5 points." in block
    assert "  no height recorded, transformed at an ellipsoid height of 0 m:\n    2 of 5 points." in block
    assert "ellipsoid height, transformed with the position:" not in block
    conventions = [row["Height convention"] for row in _audit(archive)]
    assert conventions.count(HeightConvention.ORTHOMETRIC.value) == 3
    assert conventions.count(HeightConvention.NOT_RECORDED.value) == 2


def test_the_helmert_figures_read_back_as_htdp_datas_exactly(written):
    """Every printed parameter parses back to the transcribed float, bit for bit."""
    _result, archive = written["g2z"]
    block = _block(_record(archive))
    for iopt in (17, 1):
        row = htdp_data.IGS_CONVENTION[iopt]
        name, _line = htdp_data.HELMERT_SET_NAMES[iopt]
        section = block[block.index(f"From ITRF94 to {name} -"):]
        lines = section.splitlines()[1:7]
        assert lines[0] == f"    {row.source}, reference epoch {row.reference_epoch!r}"
        values = [float(v) for line in lines[1:] for v in line[21:].split()[:-1]]
        expected = [
            row.tx_m, row.ty_m, row.tz_m,
            row.dtx_m_per_yr, row.dty_m_per_yr, row.dtz_m_per_yr,
            row.rx_arcsec, row.ry_arcsec, row.rz_arcsec,
            row.drx_arcsec_per_yr, row.dry_arcsec_per_yr, row.drz_arcsec_per_yr,
            row.scale, row.dscale_per_yr,
        ]
        assert values == expected


def test_the_helmert_set_names_are_settps_own_comments():
    """HELMERT_SET_NAMES is a transcription: the cited htdp.f line reads
    exactly ``*** From ITRF94 to <name>``."""
    source = (REPO / "review" / "wgs84-w0" / "htdp-v3.6.0" / "htdp.f").read_text(
        encoding="latin-1"
    ).splitlines()
    assert set(htdp_data.HELMERT_SET_NAMES) == set(htdp_data.IGS_CONVENTION)
    for iopt, (name, line) in htdp_data.HELMERT_SET_NAMES.items():
        assert source[line - 1].rstrip() == f"*** From ITRF94 to {name}", iopt


def test_the_velocity_facts_are_derived_from_the_transcription():
    """0.5 degree and the all-zero up velocity are true of htdp_data's grid."""
    spacing = (htdp_data.GRID6_UPPER_LATITUDE - htdp_data.GRID6_LOWER_LATITUDE) / htdp_data.GRID6_CELLS_NORTH
    assert spacing == 0.5
    assert (htdp_data.GRID6_UPPER_EAST_LONGITUDE - htdp_data.GRID6_LOWER_EAST_LONGITUDE) / htdp_data.GRID6_CELLS_EAST == 0.5
    assert all(node[2] == 0.0 for node in htdp_data.GRID6_WINDOW.values())


def test_the_measured_figures_are_design_70s_and_recons():
    """Every measured figure the block states appears in its cited source."""
    design = (REPO / "docs" / "DESIGN.md").read_text(encoding="utf-8")
    entry = design[design.index("### #70"):design.index("### #69")]
    flat = " ".join(entry.split())
    for figure in ("1.2e-5 m per 40 m", "0.012 mm", "0.18 mm", "1.8e-4 m per 600 m"):
        assert figure in flat, figure
    plan = " ".join((REPO / "docs" / "PLAN-wgs84.md").read_text(encoding="utf-8").split())
    assert "at most 0.18 mm north and 0.13 mm east" in plan
    recon = (REPO / "review" / "wgs84-w0" / "RECON.md").read_text(encoding="utf-8")
    section5 = recon[recon.index("## 5. Round trip"):recon.index("## 6.")]
    assert "N 9.2e-6 m, E 6.4e-5 m, U 4.3e-6 m" in section5
    for fact in report._HEIGHT_CONVENTION_FACTS.values():
        assert "DESIGN.md #70" in fact or "{target}" in fact
    assert "9.2e-6 m north, 6.4e-5 m east and 4.3e-6 m up" in report.ROUND_TRIP_NON_CLOSURE


def test_the_anchor_count_is_the_fixtures():
    assert report.HTDP_ANCHOR_RECORD_COUNT == f"{sum(len(r.records) for r in HTDP_RUNS):,}"


def test_every_height_convention_has_a_sentence():
    assert set(report._HEIGHT_CONVENTION_FACTS) == set(HeightConvention)


def test_the_block_states_facts_not_caveats(written):
    """The owner's no-disclaimer rule (DESIGN.md #50), on the new block."""
    for name, (_result, archive) in written.items():
        lowered = _block(_record(archive)).lower()
        for banned in ("caution", "should ", "recommend", "responsib", "be aware", "note that", "beware"):
            assert banned not in lowered, (name, banned)


def test_the_job_warning_is_in_the_record(written):
    """JobResult.job_warnings is not JobResult.warnings (W3's note), and the
    record's WARNINGS section reads it: heading, count line, message."""
    result, archive = written["g2g_reverse"]
    assert len(result.job_warnings) == 1 and result.warnings == ()
    record = _record(archive)
    warnings = record[record.index("\nWARNINGS\n"):record.index("\nFILES WRITTEN\n")]
    assert "0 warning(s) across 2 points, and 1 about the job as a whole." in warnings
    assert "POSITIONS DATED OUTSIDE THEIR REALIZATION'S PERIOD OF USE (the whole job)" in warnings
    assert result.job_warnings[0].message in warnings
    assert "None. Every point converted cleanly" not in warnings


def test_a_point_warning_beside_a_job_warning_counts_both(tmp_path):
    """G2Z on G1762 at L5's date into MI-C: 43.0 N is south of MI-C's extent,
    so each point warns too - the count line names both kinds."""
    result, archive = _write_job(
        tmp_path, "1,43.0,84.5,165.000,P\n", target_zone=MI_CENTRAL, geodetic_frame=WGS84_G1762
    )
    assert len(result.warnings) == 1 and len(result.job_warnings) == 1
    assert "1 warning(s) across 1 points, and 1 about the job as a whole." in _record(archive)


@pytest.mark.parametrize("name", [n for n, _c in regression._configurations()])
def test_no_same_frame_job_carries_any_of_it(tmp_path, name):
    """The regression floor's nine jobs, plus the frame-disclosure surfaces:
    no block, no frame-named heading, no appended column."""
    configuration = dict(regression._configurations())[name]
    source = tmp_path / "in.csv"
    source.write_text(regression.ROWS, encoding="utf-8")
    fields = dict(input_path=source, output_directory=tmp_path,
                  longitude_convention=LongitudeConvention.NEGATIVE_WEST)
    fields.update(configuration)
    if configuration["direction"] is Direction.VERTICAL_ONLY:
        fields["longitude_convention"] = None
    result = run(JobSettings(**fields))
    assert applied_frame_transformation(result.settings) is None
    archive = exports.write_all(result)["archive"]
    record = _record(archive)
    assert "FRAME TRANSFORMATION" not in record
    assert "Written in" not in record
    header = _csv_rows(member_text(archive, "_full.csv"))[0]
    assert header[-1] == "Description"
    assert not any("NAD83(2011)" in column or "Frame" in column for column in header)


# ==========================================================================
# 3. GEODETIC_TO_GEODETIC's own record.
# ==========================================================================

ZONE_ONLY_SENTENCES = (
    # Each true only of a job with a State Plane zone; each printed on a
    # vertical-only or zone job's record. Pinned ABSENT on geodetic to
    # geodetic (the #42 finding-3 class).
    "inside its zone",
    "moved between zones",
    "both\n    zones' coordinates",
    "both convergence angles",
    "Combined factor    grid scale factor x elevation factor",
    "), manual section 4.1",
    "Lambert conformal conic",
    "Appendix C",
    "NCAT",
    "Both zones are on the same reference frame",
    "Projection",
    "Central meridian",
    "False northing",
    "Twenty-seven",
    "the horizontal conversion is\nunaffected - it does not depend on elevation at all",
    "does not depend on elevation at all",
    "EXACTLY AS SUPPLIED",
    "vertical-only conversion of geodetic positions",
)


@pytest.mark.parametrize("name", ["g2g_forward", "g2g_reverse"])
def test_g2g_prints_no_zone_only_sentence(written, name):
    _result, archive = written[name]
    record = _record(archive)
    for sentence in ZONE_ONLY_SENTENCES:
        assert sentence not in record, sentence


def test_the_zone_only_sentences_do_print_on_a_zone_job(written):
    """Anti-vacuity: the list holds sentences this program really prints - on
    the zone jobs - so their absence above means something."""
    printed = _record(written["g2z"][1]) + _record(written["z2g"][1])
    present = [s for s in ZONE_ONLY_SENTENCES if s in printed]
    assert len(present) >= 12, sorted(set(ZONE_ONLY_SENTENCES) - set(present))


_G2G_COORDINATE_SYSTEMS = """\
COORDINATE SYSTEMS
------------------------------------------------------------------------------
FROM: geodetic positions (latitude / longitude)
  Reference frame           NAD83(2011) - North American Datum of 1983, 2011 realization
  Ellipsoid                 GRS 80
  Epoch                     2010.0, the frame's reference epoch
  Source: NOAA Manual NOS NGS 5, section 1.7, PDF p. 23

TO: geodetic positions (latitude / longitude)
  Reference frame           WGS84(G1762) - World Geodetic System 1984, realization G1762
  Ellipsoid                 WGS 84
  Epoch                     the observation date (see FRAME TRANSFORMATION)
  Source: NGS HTDP v3.6.0 (April 7, 2025), github.com/noaa-ngs/HTDP commit
          59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c, committed unmodified at
          review/wgs84-w0/htdp-v3.6.0/: MENU1 frame 10, 'WGS84(G1762)'
          (htdp.f:4704-4705), carried with ITRF2008's parameters
          ('WGS84(G1762)  ITRF2008=IGS08=IGb08 used', htdp.f:4767), on the WGS
          84 ellipsoid by its name (htdp.f:3221-3224). Implemented by NGA on
          2013-10-16 (NGA, ICG-17 Working Group D presentation, 2023; EPSG
          9756 and 10607; IGSMAIL-8444 (docs/PLAN-wgs84.md decision D9))

No State Plane coordinate system is involved in this job.

"""

_G2G_METHOD = """\
METHOD
------------------------------------------------------------------------------
Authority          NGS HTDP v3.6.0 (April 7, 2025), github.com/noaa-ngs/HTDP
                   commit 59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c - the frame
                   transformation, which is the whole of this job's
                   conversion. No State Plane coordinate system and no map
                   projection is involved.

Ellipsoids         NAD83(2011) on the GRS 80 ellipsoid, WGS84(G1762) on the
                   WGS 84 ellipsoid: HTDP takes the ellipsoid from the frame's
                   name (htdp.f:3221-3224).

HOW THIS SOFTWARE IS VERIFIED

This program's transcription of HTDP is held by its test suite to NGS's own
Fortran source, committed unmodified at review/wgs84-w0/htdp-v3.6.0/: every
constant transcribed must equal the one NGS wrote, number for number.

The transformation itself is checked against HTDP. NGS's source was compiled
and run, and 1,846 of its printed records - every frame offered, both
directions and the round trip, across Michigan and its lakes - are held in the
test suite as fixed reference values. This software reproduces them to the
digit HTDP prints, 1e-10 degree and 1 mm.

Both checks compare this software against NGS. Neither compares it
against itself.

"""
"""The W4 METHOD section, kept as W4 froze it: since W4b it is exactly what a
geodetic-to-geodetic job that read NO geoid prints - HTDP's two checks alone
(``test_g2g_reading_no_geoid_is_byte_identical_to_w4``)."""

_G2G_GEOID_CHECK = """\
The geoid heights are checked against NGS's own geoid height service. Twenty
Michigan positions were computed by NGS for each model this job read
(GEOID18), and those results are held in the test suite as fixed reference
values. This software reproduces them to within 1 mm, the precision NGS
publishes geoid heights to.

"""

_G2G_BENCHMARK_CHECK = """\
The ellipsoid-height arithmetic is checked at fourteen published NGS
benchmarks whose datasheets carry both an NAVD 88 height and a GEOID18 geoid
height: given h = H + N from those figures, this software returns the
published H to within 1.5 mm.

"""

_BOTH_CHECKS = """\
Both checks compare this software against NGS. Neither compares it
against itself.
"""
_EACH_CHECK = """\
Each check compares this software against NGS. None compares it
against itself.
"""

_G2G_METHOD_WITH_GEOID = _G2G_METHOD.replace(
    _BOTH_CHECKS, _G2G_GEOID_CHECK + _EACH_CHECK
)
"""RECORDED SUPERSESSION - DESIGN.md #70, plan W4b: the record named fewer
checks than the job ran. The representative g2g_reverse job is horizontal but
reads GEOID18 for its elevation factor (the default model), and at W4 its
verification named HTDP's two checks only. It now names the geoid check too,
and closes "Each check" for three: _G2G_METHOD with exactly that
replacement, nothing else moved."""


def test_g2g_coordinate_systems_and_method_are_exactly_this(written):
    """The FROM and TO frame blocks (the zone block's shape: frame, ellipsoid,
    epoch, the registry record's citation) and the METHOD/verification section
    in this direction's own words - which name the geoid check, because this
    job read GEOID18 (superseded at W4b, see _G2G_METHOD_WITH_GEOID)."""
    record = _record(written["g2g_reverse"][1])
    start = record.index("COORDINATE SYSTEMS\n")
    assert record[start:record.index("-" * 78 + "\nMETHOD", start)] == _G2G_COORDINATE_SYSTEMS
    method = record.index("METHOD\n", start)
    assert record[method:record.index("FRAME TRANSFORMATION", method)] == _G2G_METHOD_WITH_GEOID


def test_the_flagship_g2g_names_every_check_its_work_ran_on(written):
    """Plan W4b, extended to geodetic to geodetic: the H+V ellipsoid flagship
    ran HTDP, read GEOID18, and derived H from a GEOID18 h - so HTDP's two
    checks, the geoid check and the benchmark check, in that order, and no
    VERTCON check (NAVD 88 to NAVD 88 is an identity)."""
    record = _record(written["g2g_forward"][1])
    start = record.index("HOW THIS SOFTWARE IS VERIFIED\n")
    verified = record[start:record.index("\nFRAME TRANSFORMATION\n", start)]
    assert _G2G_GEOID_CHECK + _G2G_BENCHMARK_CHECK + _EACH_CHECK in verified
    assert verified.index("This program's transcription of HTDP") < verified.index(_G2G_GEOID_CHECK)
    assert "NCAT" not in verified


def test_a_g2g_job_with_vertcon_names_the_vertcon_check(tmp_path):
    """G2G H+V NGVD 29 -> NAVD 88: VERTCON ran, so its NCAT check prints."""
    _result, archive = _write_job(
        tmp_path,
        "1,43.0,84.5,200.000,P\n",
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        target_geodetic_frame=NAD83_2011,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    flat = " ".join(_record(archive).split())
    assert "converted from NGVD 29 to NAVD 88 by NCAT" in flat
    assert "for each model this job read (GEOID18)" in flat
    assert "benchmarks" not in flat


# Computed at commit 1210d34 (W4's code; the commit after it changed no code)
# by tests/test_frame_disclosure.py::_g2g_no_geoid_digests's construction run
# from a worktree of that commit, before this W4b change existed. Not to be
# regenerated from later code.
G2G_NO_GEOID_AT_W4 = {
    "g2g_no_geoid_reverse/in_GEODETIC_DD.csv": "e40a2cbbf4c87f1e303d9e800cf36fa7512700e52eb985a8d6a94c0f63bd6555",
    "g2g_no_geoid_reverse/in_GEODETIC_DMS.csv": "6a3c00e49a4f958253fb8e38c0d5db0191b3b1be3e521bcea92a0a76138c016a",
    "g2g_no_geoid_reverse/in_GEODETIC_README.txt": "390fc4b59467c39e0ca5888622a4cd0c11ba275fe0659ecb423c94cfdd287e05",
    "g2g_no_geoid_reverse/in_GEODETIC_full.csv": "c040e2da77dd068773e7c09ff290030e1ead37ab2b1851ed8902773a043fb752",
    "g2g_no_geoid_forward/in_GEODETIC_DD.csv": "bfdd3d435ab214337a0bc4f2cee0b4056fa3a1a69a54f9eedd2e466a68993239",
    "g2g_no_geoid_forward/in_GEODETIC_DMS.csv": "e06ea1829d94ba5ed3942798c7ed9c7725340922a8c58452da88a97841d59a75",
    "g2g_no_geoid_forward/in_GEODETIC_README.txt": "411fc85b68aac7695a12299147142869d051f4e34f8161e42ebf3a207d3cc093",
    "g2g_no_geoid_forward/in_GEODETIC_full.csv": "0f35d1f4052aeddae763870a0a4977b48e27d86c50520046c58dd6f65835bce1",
}


# --------------------------------------------------------------------------
# RECORDED SUPERSESSION - DESIGN.md #70, interim gate 2 (findings H1, L2, L3).
#
# Three of the gate's fixes reach these two jobs, and nothing else does:
#
# * H1 - the four Source / Target degree headings of the audit CSV now name
#   their frame, and the record's FILES WRITTEN sentence says exactly what
#   is pinned true ("Every latitude, longitude and ellipsoid height column
#   names its frame", where it said "Every position and ...");
# * L3 - the Round trip paragraph names the epochs W0 measured over;
# * L2 - on the REVERSE job (NAD83(2011) to G1762, dated outside G1762's
#   period) the realization warning speaks of the OUTPUT realization.
#
# The digests are NOT re-frozen - that would discard the cross-version
# property for every other byte - but, on #66/#68's and W4b's precedent, each
# gate-2 passage, which must occur exactly once where it is expected, is
# respelled back to its W4 text before the digest
# (test_the_gate_2_respelling_is_exact pins the counts).
# --------------------------------------------------------------------------

_FILES_WRITTEN_SENTENCE = (
    "    DMS, and the velocity HTDP applied. Every latitude, longitude and\n"
    "    ellipsoid height column names its frame.\n",
    "    DMS, and the velocity HTDP applied. Every position and ellipsoid height\n"
    "    column names its frame.\n",
)

GATE2_RESPELLING = {
    "g2g_no_geoid_reverse/in_GEODETIC_README.txt": (
        (_ROUND_TRIP, _ROUND_TRIP_AT_W4),
        _FILES_WRITTEN_SENTENCE,
        (
            "    This job writes its positions in WGS84(G1762), the realization "
            "requested as its output, at the observation date 2025-06-15 - outside "
            "WGS84(G1762)'s period of use, which is from 2013-10-16 to 2021-01-02 "
            "(NGA replaced it with WGS84(G2139) on 2021-01-03). The date is after "
            "NGA had replaced WGS84(G1762) with WGS84(G2139), so WGS84(G1762) was "
            "not the realization in use on that date. The job is converted as "
            "requested. Check that WGS84(G1762) is the realization wanted for "
            "positions observed on that date.\n",
            "    The positions are stated in WGS84(G1762) and dated 2025-06-15, "
            "outside WGS84(G1762)'s period of use, which is from 2013-10-16 to "
            "2021-01-02 (NGA replaced it with WGS84(G2139) on 2021-01-03). The "
            "date is after NGA had replaced WGS84(G1762) with WGS84(G2139), so a "
            "receiver on that date was not broadcasting it. Software can "
            "legitimately keep labelling output with an older realization, so the "
            "job is converted as stated - but a file labelled with the wrong "
            "realization looks exactly like this. Check which realization the "
            "positions are in.\n",
        ),
    ),
    "g2g_no_geoid_forward/in_GEODETIC_README.txt": (
        (_ROUND_TRIP, _ROUND_TRIP_AT_W4),
        _FILES_WRITTEN_SENTENCE,
    ),
    "g2g_no_geoid_reverse/in_GEODETIC_full.csv": (
        (
            'Source latitude (NAD83(2011)),"Source longitude (NAD83(2011), as in file)"',
            "Source latitude,Source longitude (as in file)",
        ),
        (
            'Target latitude (WGS84(G1762)),"Target longitude (WGS84(G1762), as written)"',
            "Target latitude,Target longitude (as written)",
        ),
    ),
    "g2g_no_geoid_forward/in_GEODETIC_full.csv": (
        (
            'Source latitude (WGS84(G2296)),"Source longitude (WGS84(G2296), as in file)"',
            "Source latitude,Source longitude (as in file)",
        ),
        (
            'Target latitude (NAD83(2011)),"Target longitude (NAD83(2011), as written)"',
            "Target latitude,Target longitude (as written)",
        ),
    ),
}
"""``{member: ((gate-2 text, W4 text), ...)}`` for the two G2G jobs."""


def _respelled_as_w4(key: str, body: bytes) -> tuple[bytes, int]:
    """``body`` with every gate-2 passage for ``key`` put back to its W4
    spelling, and how many were found; a passage occurring twice is refused."""
    text = body.decode("utf-8")
    found = 0
    for new, old in GATE2_RESPELLING.get(key, ()):
        count = text.count(new)
        if count > 1:
            raise AssertionError(f"gate-2 passage occurs {count} times in {key}: {new[:60]!r}")
        if count == 1:
            text = text.replace(new, old)
            found += 1
    return text.encode("utf-8"), found


def _g2g_no_geoid_digests(root: Path, *, respell: bool = True) -> dict[str, str]:
    """Two HORIZONTAL geodetic-to-geodetic jobs with geoid_model=None - no
    geoid read anywhere - every member digested, the record's timestamp and
    temporary root normalised, and (unless ``respell`` is False) the gate-2
    passages respelled as W4 wrote them (GATE2_RESPELLING)."""
    import hashlib

    jobs = {
        "g2g_no_geoid_reverse": dict(geodetic_frame=NAD83_2011, target_geodetic_frame=WGS84_G1762),
        "g2g_no_geoid_forward": dict(geodetic_frame=WGS84_G2296, target_geodetic_frame=NAD83_2011),
    }
    digests = {}
    for name, frames_ in jobs.items():
        folder = root / name
        folder.mkdir()
        (folder / "in.csv").write_text("1,43.0,84.5,165.000,P\n2,43.0,84.5,,BLANK\n")
        settings = JobSettings(
            input_path=folder / "in.csv", output_directory=folder,
            direction=Direction.GEODETIC_TO_GEODETIC, source_zone=None, target_zone=None,
            input_unit=METERS, output_unit=METERS,
            longitude_convention=LongitudeConvention.POSITIVE_WEST,
            geoid_model=None, observation_date=L5_DATE, **frames_,
        )
        with zipfile.ZipFile(exports.write_all(run(settings))["archive"]) as opened:
            for member in sorted(opened.namelist()):
                body = opened.read(member)
                if member.endswith("README.txt"):
                    text = re.sub(r"^Generated          .*$", "Generated          <normalised>",
                                  body.decode(), flags=re.M)
                    body = text.replace(str(root), "<ROOT>").encode()
                key = f"{name}/{member}"
                if respell:
                    body, _found = _respelled_as_w4(key, body)
                digests[key] = hashlib.sha256(body).hexdigest()
    return digests


def test_g2g_reading_no_geoid_is_byte_identical_to_w4(tmp_path):
    """A horizontal G2G job that reads no geoid ran no vertical work, so W4b
    adds no check to it: all four members of both jobs are W4's bytes - but
    for interim gate 2's passages, respelled (GATE2_RESPELLING) - and its
    METHOD is W4's _G2G_METHOD exactly."""
    assert _g2g_no_geoid_digests(tmp_path) == G2G_NO_GEOID_AT_W4
    archive = next((tmp_path / "g2g_no_geoid_reverse").glob("*.zip"))
    text = _record(archive)
    method = text.index("METHOD\n")
    assert text[method:text.index("FRAME TRANSFORMATION", method)] == _G2G_METHOD
    assert "geoid height service" not in text


def test_the_gate_2_respelling_is_exact(tmp_path):
    """Anti-vacuity and confinement, as test_the_w4b_respelling_is_exact is:
    every gate-2 passage is found exactly where GATE2_RESPELLING expects it
    (3 + 2 in the records, 2 + 2 in the audit CSVs), so the raw members no
    longer match W4's digests while the respelled ones do; the DD and DMS
    members have no passage and are compared exactly as written."""
    (tmp_path / "raw").mkdir()
    (tmp_path / "respelled").mkdir()
    raw = _g2g_no_geoid_digests(tmp_path / "raw", respell=False)
    respelled = _g2g_no_geoid_digests(tmp_path / "respelled")
    assert respelled == G2G_NO_GEOID_AT_W4
    for key in G2G_NO_GEOID_AT_W4:
        if key in GATE2_RESPELLING:
            assert raw[key] != G2G_NO_GEOID_AT_W4[key], key
        else:
            assert raw[key] == G2G_NO_GEOID_AT_W4[key], key
    for key, passages in GATE2_RESPELLING.items():
        name, member = key.split("/", 1)
        archive = next((tmp_path / "raw" / name).glob("*.zip"))
        with zipfile.ZipFile(archive) as opened:
            body = opened.read(member)
        if member.endswith("README.txt"):
            text = re.sub(r"^Generated          .*$", "Generated          <normalised>",
                          body.decode(), flags=re.M)
            body = text.replace(str(tmp_path / "raw"), "<ROOT>").encode()
        respelled_body, found = _respelled_as_w4(key, body)
        assert found == len(passages), key
        assert _respelled_as_w4(key, respelled_body) == (respelled_body, 0), key


def test_g2g_record_describes_its_own_files_and_factors(written):
    record = _record(written["g2g_forward"][1])
    assert "Conversion         geodetic to geodetic" in record
    assert "Reference frame    WGS84(G2296) - World Geodetic System 1984, realization G2296" in record
    assert "Written in         NAD83(2011) - North American Datum of 1983, 2011 realization" in record
    assert "Format             Comma separated, no header row - NOT PNEZD" in record
    assert "positions in NAD83(2011)." in record
    assert "None. Every point converted cleanly.\n" in record
    assert "R / (R + H + N), NOAA Manual NOS NGS 5 section 4.1" in record
    assert "in a geodetic-to-geodetic conversion, so there is no grid" in record
    assert "moved between reference\nframes" in record
    names = exports.member_names(written["g2g_forward"][0])
    assert names["pnezd"].endswith("_GEODETIC_DD.csv")
    assert names["pnezd_dms"].endswith("_GEODETIC_DMS.csv")


def test_the_ellipsoid_block_names_the_frames_on_a_transformed_job(written):
    """D6, in the record: the supplied heights are above THEIR frame's
    ellipsoid; the h of H = h - N is the NAD 83 one; a horizontal job's Z is h
    in the target frame - never "EXACTLY AS SUPPLIED"."""
    z2g = " ".join(_record(written["z2g"][1]).split())
    assert "stated as ELLIPSOID heights in NAD83(2011) (above the GRS 80 ellipsoid)" in z2g
    assert "carries the ELLIPSOID HEIGHT in WGS84(G2296): the height the file supplied in NAD83(2011), transformed with the position" in z2g
    assert "EXACTLY AS SUPPLIED" not in z2g
    assert "h is the NAD83(2011) ellipsoid height the Z column supplied" in z2g
    g2g = " ".join(_record(written["g2g_forward"][1]).split())
    assert "stated as ELLIPSOID heights in WGS84(G2296) (above the WGS 84 ellipsoid)" in g2g
    assert (
        "h is the NAD83(2011) ellipsoid height (the height the Z column supplied in "
        "WGS84(G2296), transformed with the position to NAD83(2011): GEOID18 publishes "
        "N against NAD83(2011))"
    ) in g2g
    assert "(above the GRS 80 ellipsoid)" not in g2g


def test_the_elevations_paragraph_no_longer_claims_independence(written):
    """A blank Z is transformed at h = 0 (D6), so "does not depend on
    elevation at all" would be false: the transformed record says what holds."""
    for name, (_result, archive) in written.items():
        flat = " ".join(_record(archive).split())
        assert "does not depend on elevation at all" not in flat, name
        assert (
            "The height each point's frame transformation was handed is stated "
            "under FRAME TRANSFORMATION, and per point in the _full.csv export."
        ) in flat, name


# ==========================================================================
# 4. The audit CSV's headers.
# ==========================================================================

_PIVOT = [
    "Latitude (NAD83(2011))",
    "Longitude (NAD83(2011), neg west)",
    "Latitude (NAD83(2011), DMS)",
    "Longitude (NAD83(2011), DMS)",
]


def _appended(external, target, ellipsoid_source=None):
    columns = [
        "Frame transformation",
        "Observation date",
        "Observation epoch (decimal year)",
        "Height convention",
        f"Latitude ({external})",
        f"Longitude ({external}, neg west)",
        f"Latitude ({external}, DMS)",
        f"Longitude ({external}, DMS)",
    ]
    if ellipsoid_source is not None:
        columns += [
            f"Ellipsoid height before transformation ({ellipsoid_source}, m)",
            f"Ellipsoid height after transformation ({target}, m)",
        ]
    return columns + [
        f"Velocity north ({target}, mm/yr)",
        f"Velocity east ({target}, mm/yr)",
        f"Velocity up ({target}, mm/yr)",
    ]


EXPECTED_HEADERS_AT_W4 = {
    # The headers W4 froze. RECORDED SUPERSESSION below
    # (test_the_audit_header_is_exactly_this): interim gate 2 renamed four of
    # them, and nothing else.
    "g2z": [
        "Point", "Source zone", "Source latitude", "Source longitude (as in file)",
        "Target zone", "Target northing", "Target easting", "Elevation", "Units",
        *_PIVOT, "Geoid height (m)", "Ellipsoid height (NAD83(2011), m)",
        "Source grid scale factor", "Source convergence", "Grid scale factor",
        "Convergence", "Elevation factor", "Combined factor", "Combined factor (ppm)",
        "Warnings", "Description",
        *_appended("WGS84(G2296)", "NAD83(2011)"),
    ],
    "z2g": [
        "Point", "Source zone", "Source northing", "Source easting",
        "Target zone", "Target latitude", "Target longitude (as written)",
        "Ellipsoid height (WGS84(G2296))", "Input height kind", "Units",
        *_PIVOT, "Geoid height (m)", "Ellipsoid height (NAD83(2011), m)",
        "Source grid scale factor", "Source convergence", "Grid scale factor",
        "Convergence", "Elevation factor", "Combined factor", "Combined factor (ppm)",
        "Warnings", "Description",
        *_appended("WGS84(G2296)", "WGS84(G2296)", "NAD83(2011)"),
    ],
    "g2g_forward": [
        "Point", "Source zone", "Source latitude", "Source longitude (as in file)",
        "Target zone", "Target latitude", "Target longitude (as written)",
        "Elevation", "Input height kind", "Source vertical datum", "Target vertical datum",
        "Ellipsoid height in (WGS84(G2296), m)", "Source elevation (m)",
        "Vertical shift (m)", "Shift sigma (m)", "Units",
        *_PIVOT, "Geoid model", "Geoid height (m)", "Ellipsoid height (NAD83(2011), m)",
        "Source grid scale factor", "Source convergence", "Grid scale factor",
        "Convergence", "Elevation factor", "Combined factor", "Combined factor (ppm)",
        "Warnings", "Description",
        *_appended("WGS84(G2296)", "NAD83(2011)", "WGS84(G2296)"),
    ],
}


GATE2_H1_RENAMES = {
    # The frame each degree pair HOLDS, per direction (exports.
    # geodetic_pair_frames): the Source pair is the input, at the path's
    # source end; the Target pair is the written position, at its target end.
    # g2z: WGS84(G2296) input, MI-S grid out - only the Source pair is degrees.
    "g2z": {
        "Source latitude": "Source latitude (WGS84(G2296))",
        "Source longitude (as in file)": "Source longitude (WGS84(G2296), as in file)",
    },
    # z2g: MI-S grid in, WGS84(G2296) written - only the Target pair.
    "z2g": {
        "Target latitude": "Target latitude (WGS84(G2296))",
        "Target longitude (as written)": "Target longitude (WGS84(G2296), as written)",
    },
    # g2g_forward: WGS84(G2296) in, NAD83(2011) written - both pairs.
    "g2g_forward": {
        "Source latitude": "Source latitude (WGS84(G2296))",
        "Source longitude (as in file)": "Source longitude (WGS84(G2296), as in file)",
        "Target latitude": "Target latitude (NAD83(2011))",
        "Target longitude (as written)": "Target longitude (NAD83(2011), as written)",
    },
}


@pytest.mark.parametrize("name", list(EXPECTED_HEADERS_AT_W4))
def test_the_audit_header_is_exactly_this(written, name):
    """RECORDED SUPERSESSION - DESIGN.md #70, interim gate 2 finding H1.

    W4 froze these headers with the four Source / Target degree headings
    naming no frame, beside a record sentence saying every position column
    named its frame; the pin enshrined the false half. They now name the
    frame their cells are in. Pinned as W4's header with EXACTLY those
    renames and no other change, so the supersession is confined: every other
    heading is W4's, in W4's position.
    """
    _result, archive = written[name]
    header = _csv_rows(member_text(archive, "_full.csv"))[0]
    renames = GATE2_H1_RENAMES[name]
    assert header == [renames.get(c, c) for c in EXPECTED_HEADERS_AT_W4[name]]
    assert sum(1 for c in EXPECTED_HEADERS_AT_W4[name] if c in renames) == len(renames)


_PIVOT_RENAMES = {
    # What a transformed job calls the five same-frame headings that hold a
    # NAD 83 quantity (exports._frame_named), and nothing else.
    "Latitude": "Latitude (NAD83(2011))",
    "Longitude (neg west)": "Longitude (NAD83(2011), neg west)",
    "Latitude (DMS)": "Latitude (NAD83(2011), DMS)",
    "Longitude (DMS)": "Longitude (NAD83(2011), DMS)",
    "Ellipsoid height (m)": "Ellipsoid height (NAD83(2011), m)",
}


_SUPPLIED_HEIGHT_RENAMES = {
    # The one further heading each ellipsoid job renames: a horizontal job's
    # Z column (h in the path's TARGET frame) and a vertical job's supplied
    # height (h in its SOURCE frame).
    "g2z": {},
    "z2g": {"Ellipsoid height": "Ellipsoid height (WGS84(G2296))"},
    "vertical_only": {"Ellipsoid height in (m)": "Ellipsoid height in (ITRF2020, m)"},
}


_PAIR_RENAMES = {
    # Interim gate 2, H1: the degree pairs, each by the frame its cells hold.
    "g2z": GATE2_H1_RENAMES["g2z"],
    "z2g": GATE2_H1_RENAMES["z2g"],
    # vertical_only: ITRF2020 input, and the Target pair MIRRORS it, so both
    # pairs are ITRF2020 - not the NAD83(2011) the path ends in.
    "vertical_only": {
        "Source latitude": "Source latitude (ITRF2020)",
        "Source longitude (as in file)": "Source longitude (ITRF2020, as in file)",
        "Target latitude": "Target latitude (ITRF2020)",
        "Target longitude (as written)": "Target longitude (ITRF2020, as written)",
    },
}


@pytest.mark.parametrize("name", list(_SUPPLIED_HEIGHT_RENAMES))
def test_the_shared_columns_keep_their_positions(written, name):
    """Against the SAME job on NAD83(2011) with no date - the same-frame job
    of the same shape - every column keeps its index: the five NAD 83
    headings, the supplied height's and (since interim gate 2, H1) the degree
    pairs' are renamed in place, and every new column follows Description.
    (Geodetic to geodetic has no same-frame shape: D7 refuses one.)"""
    result, archive = written[name]
    header = _csv_rows(member_text(archive, "_full.csv"))[0]
    same_settings = dataclasses.replace(
        result.settings, geodetic_frame=NAD83_2011, observation_date=None
    )
    same = exports.audit_columns(dataclasses.replace(result, settings=same_settings))
    renames = {**_PIVOT_RENAMES, **_SUPPLIED_HEIGHT_RENAMES[name], **_PAIR_RENAMES[name]}
    assert header[: len(same)] == [renames.get(c, c) for c in same]
    assert sum(1 for c in same if c in renames) == len(_PIVOT_RENAMES) + len(
        _SUPPLIED_HEIGHT_RENAMES[name]
    ) + len(_PAIR_RENAMES[name])
    assert same[-1] == "Description"
    assert header[len(same)] == "Frame transformation"


def test_a_point_without_the_jobs_transformation_is_refused(written):
    """Fail closed: an audit row may not state a transformation its point did
    not undergo. A point stripped of its evidence is refused by name."""
    result, _archive = written["g2z"]
    point = result.points[0]
    bare = dataclasses.replace(
        point.conversion,
        external_position=None,
        frame_transformation=None,
        htdp_result=None,
        observation_epoch=None,
        transform_height=None,
    )
    forged = dataclasses.replace(
        result, points=(dataclasses.replace(point, conversion=bare),) + result.points[1:]
    )
    with pytest.raises(WriteError, match="carries no frame transformation"):
        exports.audit_rows(forged)


def test_the_record_refuses_a_point_the_transformation_did_not_move(written):
    """The block states HTDP moved every point; a hand-assembled result with
    one point stripped of its evidence is refused by the record too, naming
    the point, rather than described."""
    result, _archive = written["g2g_reverse"]
    point = result.points[1]
    bare = dataclasses.replace(
        point.conversion,
        external_position=None,
        frame_transformation=None,
        htdp_result=None,
        observation_epoch=None,
        transform_height=None,
    )
    forged = dataclasses.replace(
        result, points=(result.points[0], dataclasses.replace(point, conversion=bare))
    )
    with pytest.raises(ValueError, match=r"point\(s\) 2 of the job carry no such"):
        report.build_report(forged)


# ==========================================================================
# 5. The verifiers check the position each file states.
# ==========================================================================


def _rows_from_pivot(result, dms: bool):
    """A clean export (or its DMS sibling) built from the NAD 83 PIVOT: what a
    writer or verifier still pointed at the pivot would produce."""
    convention = result.settings.longitude_convention
    rows = []
    for point in result.points:
        latitude, longitude = point.conversion.latitude, point.conversion.longitude
        if dms:
            cells = [fmt.latitude_dms_fields(latitude), fmt.longitude_dms_fields(longitude)]
        else:
            cells = [fmt.latitude(latitude), fmt.longitude(convention.from_signed(longitude))]
        rows.append(
            [point.point_id, *cells,
             fmt.coordinate(point.output_elevation, result.settings.output_unit),
             point.row.description]
        )
    return rows


@pytest.mark.parametrize("name", ["z2g", "g2g_reverse", "g2g_forward"])
def test_the_verifiers_accept_the_stated_position(written, name):
    """Each geodetic-target archive was written (the fixture), and its two
    files pass the verifiers again here, against the target frame's position."""
    result, _archive = written[name]
    exports.verify_round_trip(exports.clean_pnezd_rows(result), result)
    exports.verify_dms_round_trip(exports.clean_pnezd_dms_rows(result), result)


@pytest.mark.parametrize("name", ["z2g", "g2g_reverse"])
def test_files_built_from_the_pivot_are_refused(written, name):
    """On a WGS 84 target the pivot is not what the files state: a DD or DMS
    file built from it is refused by both verifiers, naming the cell."""
    result, _archive = written[name]
    with pytest.raises(WriteError, match="Round-trip check failed"):
        exports.verify_round_trip(_rows_from_pivot(result, dms=False), result)
    with pytest.raises(WriteError, match="DMS round-trip check failed"):
        exports.verify_dms_round_trip(_rows_from_pivot(result, dms=True), result)


def test_on_a_nad83_target_the_pivot_is_the_stated_position(written):
    """The control: into NAD83(2011) the stated position IS the pivot, so the
    pivot-built files are the files and pass."""
    result, _archive = written["g2g_forward"]
    exports.verify_round_trip(_rows_from_pivot(result, dms=False), result)
    exports.verify_dms_round_trip(_rows_from_pivot(result, dms=True), result)


def test_g2z_is_verified_against_the_grid(written):
    """GEODETIC_TO_ZONE: the file states grid coordinates and is checked
    against them, as always - a northing 1 mm off is refused."""
    result, _archive = written["g2z"]
    rows = exports.clean_pnezd_rows(result)
    exports.verify_round_trip(rows, result)
    rows[0][1] = f"{float(rows[0][1]) + 0.001:.4f}"
    with pytest.raises(WriteError, match="northing"):
        exports.verify_round_trip(rows, result)


def test_the_dms_sibling_is_written_on_both_geodetic_targets(written):
    for name, (result, archive) in written.items():
        members = _members(archive)
        has_dms = any(m.endswith("_DMS.csv") for m in members)
        geodetic_target = result.settings.direction in (
            Direction.ZONE_TO_GEODETIC, Direction.GEODETIC_TO_GEODETIC
        )
        assert has_dms is geodetic_target, name
        assert exports.writes_dms_export(result) is geodetic_target
        assert len(members) == (4 if geodetic_target else 3)



# ==========================================================================
# 7. Plan W4b: a vertical-only job on GEODETIC positions has no zone, and its
#    record says so (DESIGN.md #70; the #42 finding-3 class). Until W4b it
#    printed the SPCS 83 projection prose and "inside its zone" - in
#    released output since 0.4.0, and on WGS 84 input since W4.
# ==========================================================================

VO_ZONE_ONLY_SENTENCES = tuple(
    sentence
    for sentence in ZONE_ONLY_SENTENCES
    # True of this job, and VO-specific: its factor summary's own sentence.
    if sentence != "vertical-only conversion of geodetic positions"
) + (
    "Authority          NOAA Manual NOS NGS 5, State Plane Coordinate System",
    "The zone constants used above are not taken on trust.",
    "the grid\nscale factor is not substituted for the combined factor",
    "The horizontal conversion is\nunaffected",
)


def _vo_geodetic(folder, rows="1,43.0,84.5,200.000,P\n2,43.1,84.6,,BLANK\n", **fields):
    """A vertical-only job on NAD83(2011) positions - the same-frame variant."""
    base = dict(
        direction=Direction.VERTICAL_ONLY,
        target_zone=None,
        geodetic_frame=NAD83_2011,
        observation_date=None,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
    )
    base.update(fields)
    return _write_job(folder, rows, **base)


@pytest.fixture(scope="module")
def vo_records(tmp_path_factory, written):
    """Both variants of the defect the lead reproduced: same-frame NAD83(2011)
    and WGS84(G2296), plus the transformed ITRF2020 representative."""
    root = tmp_path_factory.mktemp("w4b")
    same = _record(_vo_geodetic(root / "same")[1])
    g2296 = _record(_vo_geodetic(
        root / "g2296", geodetic_frame=WGS84_G2296, observation_date=L5_DATE
    )[1])
    return {"same_frame": same, "wgs84_g2296": g2296, "itrf2020": _record(written["vertical_only"][1])}


@pytest.mark.parametrize("variant", ["same_frame", "wgs84_g2296", "itrf2020"])
def test_vo_geodetic_prints_no_zone_only_sentence(vo_records, variant):
    record = vo_records[variant]
    for sentence in VO_ZONE_ONLY_SENTENCES:
        assert sentence not in record, (variant, sentence)


def test_the_vo_zone_only_sentences_still_print_on_a_vo_zone_job(tmp_path):
    """Anti-vacuity and plan W4b item 4: VERTICAL_ONLY with a ZONE input keeps
    its zone prose, which is true of it - it inverts through the input zone.
    (Its whole record is byte-pinned against W3 in
    tests/test_same_frame_outputs_unchanged.py.)"""
    _result, archive = _write_job(
        tmp_path,
        f"1,{_NAD83_SOUTH.target_northing!r},{_NAD83_SOUTH.target_easting!r},200.000,P\n",
        direction=Direction.VERTICAL_ONLY,
        source_zone=MI_SOUTH,
        target_zone=None,
        geodetic_frame=NAD83_2011,
        observation_date=None,
        longitude_convention=None,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
    )
    record = _record(archive)
    for sentence in (
        "Authority          NOAA Manual NOS NGS 5, State Plane Coordinate System",
        "Lambert conformal conic",
        "The zone constants used above are not taken on trust.",
        "Twenty-seven",
        "Combined factor    grid scale factor x elevation factor",
        "), manual section 4.1",
        "inside its zone",
        "moved between zones",
        "both\n    zones' coordinates",
    ):
        assert sentence in record, sentence
    assert "No map projection runs in this job" not in record


_VO_METHOD_SAME_FRAME = """\
METHOD
------------------------------------------------------------------------------
Method             No map projection runs in this job: its positions are
                   geodetic, no State Plane zone is involved, and the
                   horizontal coordinates are reproduced unconverted. Each
                   point's elevation is converted at its NAD83(2011) position,
                   which is the input position itself: the GEOID18 geoid
                   height is read there, and the vertical datum transformation
                   stated below is applied.

HOW THIS SOFTWARE IS VERIFIED

The geoid heights are checked against NGS's own geoid height service. Twenty
Michigan positions were computed by NGS for each model this job read
(GEOID18), and those results are held in the test suite as fixed reference
values. This software reproduces them to within 1 mm, the precision NGS
publishes geoid heights to.

The check compares this software against NGS, not against itself.

"""
"""Orthometric Z, NAVD 88 to NAVD 88 (an identity, so no VERTCON check), the
default GEOID18, no transformation: the one check this job's arithmetic
rests on is the geoid one."""

_VO_METHOD_ITRF2020 = """\
METHOD
------------------------------------------------------------------------------
Method             No map projection runs in this job: its positions are
                   geodetic, no State Plane zone is involved, and the
                   horizontal coordinates are reproduced unconverted. Each
                   point's elevation is converted at its NAD83(2011) position,
                   which is the input position carried from ITRF2020 by the
                   frame transformation stated below: the GEOID18 geoid height
                   is read there, and the vertical datum transformation stated
                   below is applied.

HOW THIS SOFTWARE IS VERIFIED

This program's transcription of HTDP is held by its test suite to NGS's own
Fortran source, committed unmodified at review/wgs84-w0/htdp-v3.6.0/: every
constant transcribed must equal the one NGS wrote, number for number.

The transformation itself is checked against HTDP. NGS's source was compiled
and run, and 1,846 of its printed records - every frame offered, both
directions and the round trip, across Michigan and its lakes - are held in the
test suite as fixed reference values. This software reproduces them to the
digit HTDP prints, 1e-10 degree and 1 mm.

The geoid heights are checked against NGS's own geoid height service. Twenty
Michigan positions were computed by NGS for each model this job read
(GEOID18), and those results are held in the test suite as fixed reference
values. This software reproduces them to within 1 mm, the precision NGS
publishes geoid heights to.

The ellipsoid-height arithmetic is checked at fourteen published NGS
benchmarks whose datasheets carry both an NAVD 88 height and a GEOID18 geoid
height: given h = H + N from those figures, this software returns the
published H to within 1.5 mm.

Each check compares this software against NGS. None compares it
against itself.

"""
"""The ITRF2020 representative: ELLIPSOID Z, so the HTDP step (two checks),
the geoid read (one), and the GEOID18 h -> H arithmetic (the benchmarks) all
ran; the datum pair is an identity, so no VERTCON check."""


def _method_section(record: str) -> str:
    start = record.index("METHOD\n")
    for end_marker in ("FRAME TRANSFORMATION\n", "Geoid model        "):
        if end_marker in record[start:]:
            return record[start:record.index(end_marker, start)]
    raise AssertionError("no end to METHOD")


def test_vo_geodetic_method_is_exactly_this(vo_records):
    assert _method_section(vo_records["same_frame"]) == _VO_METHOD_SAME_FRAME
    assert _method_section(vo_records["itrf2020"]) == _VO_METHOD_ITRF2020


def test_vo_geodetic_states_what_ran_and_its_true_replacements(vo_records):
    """Plan W4b item 2: no projection; the geoid lookup at the NAD 83 pivot;
    the HTDP step on a transformed job; and each zone-free replacement."""
    for variant, record in vo_records.items():
        flat = " ".join(record.split())
        assert "No map projection runs in this job" in flat
        assert "is converted at its NAD83(2011) position" in flat
        assert "the GEOID18 geoid height is read there" in flat
        assert "R / (R + H + N), NOAA Manual NOS NGS 5 section 4.1" in record
        assert "None. Every point converted cleanly.\n" in record
        assert "A coordinate file produced by a conversion should not" in record
        assert "scale-factor and convergence columns read N/A" in flat
        assert (
            "For those points the elevation factor is written as 'N/A' in the "
            "exports. It is NOT set to 1.0. The positions do not use it." in flat
        )
        transformed = variant != "same_frame"
        assert ("carried from" in flat) is transformed, variant
        assert ("This program's transcription of HTDP" in flat) is transformed
        assert ("position in both frames" in flat) is transformed
        assert ("position the file supplied" in flat) is not transformed
    g2296 = " ".join(vo_records["wgs84_g2296"].split())
    assert "the input position carried from WGS84(G2296) by the frame transformation" in g2296
    # The transformed variants carry the HTDP checks in METHOD, not a second
    # time as the block's Verified line.
    for variant in ("wgs84_g2296", "itrf2020"):
        assert "\nVerified           " not in vo_records[variant]


def test_vo_geodetic_names_the_vertcon_check_only_when_vertcon_ran(tmp_path):
    """NGVD 29 -> NAVD 88 with GEOID12B: the VERTCON NCAT check and the
    GEOID12B geoid check, and no benchmark check (orthometric input)."""
    _result, archive = _vo_geodetic(
        tmp_path, source_vertical_datum=NGVD29, geoid_model=geoid.GEOID12B_MODEL
    )
    flat = " ".join(_method_section(_record(archive)).split())
    assert "converted from NGVD 29 to NAVD 88 by NCAT" in flat
    assert "to within 0.5 mm - which is the precision NCAT publishes" in flat
    assert "for each model this job read (GEOID12B)" in flat
    assert "benchmarks" not in flat
    assert "Both checks compare this software against NGS." in flat


def test_vo_geodetic_names_both_models_on_a_geoid_change(tmp_path):
    _result, archive = _vo_geodetic(tmp_path, source_geoid_model=geoid.GEOID12B_MODEL)
    flat = " ".join(_method_section(_record(archive)).split())
    assert "the GEOID12B and GEOID18 geoid heights are read there" in flat
    assert "for each model this job read (GEOID12B and GEOID18)" in flat
    assert "NCAT" not in flat


def test_the_vertical_check_counts_are_the_fixtures():
    from tests.fixtures.ellipsoid_height_anchors import BENCHMARK_ANCHORS
    from tests.fixtures.geoid12b_anchors import GEOID12B_ANCHORS
    from tests.fixtures.geoid_anchors import GEOID_ANCHORS
    from tests.fixtures.vertcon_anchors import (
        NAVD88_TO_NGVD29_ANCHORS,
        NGVD29_TO_NAVD88_ANCHORS,
    )

    words = {5: "five", 14: "fourteen", 20: "twenty"}
    assert words[len(NGVD29_TO_NAVD88_ANCHORS)] == report.VERTCON_FORWARD_ANCHOR_COUNT.lower()
    assert words[len(NAVD88_TO_NGVD29_ANCHORS)] == report.VERTCON_INVERSE_ANCHOR_COUNT
    assert words[len(GEOID_ANCHORS)] == report.GEOID_ANCHOR_COUNT.lower()
    assert words[len(GEOID12B_ANCHORS)] == report.GEOID_ANCHOR_COUNT.lower()
    assert words[len(BENCHMARK_ANCHORS)] == report.BENCHMARK_ANCHOR_COUNT


# ==========================================================================
# 8. Interim gate 2 of the WGS 84 build (review/gate-wgs84-2/output.md):
#    H1, H2 and L3 - three record sentences made true and pinned.
# ==========================================================================

# --------------------------------------------------------------------------
# H1: "Every latitude, longitude and ellipsoid height column names its
# frame." The root pin: on every transformed direction, under both height
# kinds and every mode the direction takes, each such heading names exactly
# one frame, and that frame is the one its CELLS hold - found by matching
# each cell against the point's NAD83(2011) and WGS 84 / ITRF values, which
# are about a metre apart (~9e-6 deg, ~1.1 m in h), far beyond every written
# precision (5e-9 deg DD, 1.4e-9 deg DMS, 0.5 mm h).
# --------------------------------------------------------------------------

_FRAME_CODES = [NAD83_2011.code] + FIVE_IDS
"""Every frame a transformed job's heading can name; no code contains another."""

_H1_GEODETIC_POINTS = ((43.0, 84.5, "165.000"), (42.4, 83.2, "250.000"))
"""Two NAD 83 / input positions in MI-S's area, longitude positive west, with
ellipsoid-or-orthometric Z values far from zero (a 0 Z is "not recorded")."""

_NAD83_SOUTH_2 = project_point(42.4, -83.2, NAD83_2011, MI_SOUTH)


def _h1_rows(direction, convention) -> str:
    if direction is Direction.ZONE_TO_GEODETIC:
        grid = (_NAD83_SOUTH, _NAD83_SOUTH_2)
        return "".join(
            f"{n},{g.target_northing!r},{g.target_easting!r},{z},P{n}\n"
            for n, (g, (_lat, _lon, z)) in enumerate(zip(grid, _H1_GEODETIC_POINTS), 1)
        )
    sign = -1.0 if convention is LongitudeConvention.NEGATIVE_WEST else 1.0
    return "".join(
        f"{n},{lat},{sign * lon},{z},P{n}\n"
        for n, (lat, lon, z) in enumerate(_H1_GEODETIC_POINTS, 1)
    )


def _h1_jobs():
    """(id, direction, frame, kind, mode, convention) over every transformed
    direction x both height kinds x every mode it takes, the frame rotating
    through all five and the longitude convention alternating."""
    jobs = []
    shapes = [
        (Direction.GEODETIC_TO_ZONE, "g2z"),
        (Direction.ZONE_TO_GEODETIC, "z2g"),
        (Direction.GEODETIC_TO_GEODETIC, "g2g_forward"),
        (Direction.GEODETIC_TO_GEODETIC, "g2g_reverse"),
        (Direction.VERTICAL_ONLY, "vo"),
    ]
    counter = 0
    for direction, label in shapes:
        modes = (
            (VerticalMode.VERTICAL,)
            if direction is Direction.VERTICAL_ONLY
            else (VerticalMode.HORIZONTAL, VerticalMode.HORIZONTAL_AND_VERTICAL)
        )
        for kind in (HeightKind.ORTHOMETRIC, HeightKind.ELLIPSOID):
            for mode in modes:
                frame = FIVE[counter % len(FIVE)]
                convention = (
                    LongitudeConvention.POSITIVE_WEST
                    if counter % 2
                    else LongitudeConvention.NEGATIVE_WEST
                )
                counter += 1
                jobs.append(
                    (f"{label}-{kind.name}-{mode.name}-{frame.code}", direction,
                     label, frame, kind, mode, convention)
                )
    return jobs


_H1_JOBS = _h1_jobs()


def _h1_write(folder: Path, direction, label, frame, kind, mode, convention):
    fields = dict(
        direction=direction,
        geodetic_frame=frame,
        input_height_kind=kind,
        vertical_mode=mode,
        longitude_convention=convention,
        target_zone=MI_SOUTH if direction is Direction.GEODETIC_TO_ZONE else None,
    )
    if direction is Direction.ZONE_TO_GEODETIC:
        fields.update(source_zone=MI_SOUTH)
    if label == "g2g_forward":
        fields.update(target_geodetic_frame=NAD83_2011)
    if label == "g2g_reverse":
        fields.update(geodetic_frame=NAD83_2011, target_geodetic_frame=frame)
    if mode is not VerticalMode.HORIZONTAL:
        fields.update(source_vertical_datum=NAVD88, target_vertical_datum=NAVD88)
    return _write_job(folder, _h1_rows(direction, convention), **fields)


def _cell_degrees(cell: str, heading: str, settings) -> float:
    """A latitude or longitude cell, signed negative west, read by the test."""
    if "DMS" in heading:
        return _dms_degrees(cell)
    value = float(cell)
    if "longitude" not in heading.lower() or "neg west" in heading:
        return value
    # "as in file" / "as written": the job's own convention, which the
    # record's Longitude line names.
    assert "as in file" in heading or "as written" in heading, heading
    return settings.longitude_convention.to_signed(value)


def _frames_holding(kind: str, heading: str, value: float, point, path, settings) -> list[str]:
    """Which frames' value for this point the cell equals, at its precision.

    The candidates are the point's NAD83(2011) and WGS 84 / ITRF values from
    its conversion record (each pinned against HTDP's print in sections 1-2),
    except one: the NAD 83 h of an ORTHOMETRIC job, which no transformation
    produced, is derived here as H + N - the Z (an elevation, unshifted on
    these NAVD 88 to NAVD 88 jobs) plus GEOID18 read at the pivot by the
    program's NGS-anchored reader - because N is published against NAD 83.
    """
    conversion = point.conversion
    external = conversion.external_position
    pivot_code = exports.pivot_frame(path).code
    external_code = exports.external_frame(path).code
    if kind == "lat":
        candidates = {pivot_code: conversion.latitude, external_code: external.latitude}
        tolerance = DMS_CELL_DEG if "DMS" in heading else 0.5e-8 + 1e-12
    elif kind == "lon":
        candidates = {pivot_code: conversion.longitude, external_code: external.longitude}
        tolerance = DMS_CELL_DEG if "DMS" in heading else 0.5e-8 + 1e-12
    else:
        nad83_h = conversion.pivot_ellipsoid_height
        if nad83_h is None:
            nad83_h = point.row.elevation + geoid.geoid_height(
                conversion.latitude, conversion.longitude, geoid.default_grid(geoid.GEOID18_MODEL)
            )
        candidates = {pivot_code: nad83_h, external_code: external.ellipsoid_height}
        # The coarsest written height is 3 places (formatting.geoid_height):
        # half its unit, plus 1e-6 m for the separation's float sum.
        tolerance = 0.5e-3 + 1e-6
    return sorted(
        code for code, held in candidates.items()
        if held is not None and abs(value - held) <= tolerance
    )


def _check_every_position_heading(result, archive) -> list[str]:
    """The record sentence, checked heading by heading against the cells.
    Returns the headings checked."""
    settings = result.settings
    path = applied_frame_transformation(settings)
    rows = _csv_rows(member_text(archive, "_full.csv"))
    header, body = rows[0], rows[1:]
    assert len(body) == len(result.points)
    checked = []
    for index, heading in enumerate(header):
        lowered = heading.lower()
        kind = (
            "lat" if "latitude" in lowered
            else "lon" if "longitude" in lowered
            else "h" if "ellipsoid height" in lowered
            else None
        )
        if kind is None:
            continue
        named = [code for code in _FRAME_CODES if code in heading]
        assert len(named) == 1, f"{heading!r} names {named or 'no frame'}"
        for point, row in zip(result.points, body):
            cell = row[index]
            if cell in ("", fmt.NOT_AVAILABLE):
                continue
            value = (
                float(cell) if kind == "h" else _cell_degrees(cell, heading, settings)
            )
            held = _frames_holding(kind, heading, value, point, path, settings)
            assert held == named, (heading, point.point_id, cell, held)
        checked.append(heading)
    return checked


@pytest.mark.parametrize(
    "job_id,direction,label,frame,kind,mode,convention",
    _H1_JOBS,
    ids=[job[0] for job in _H1_JOBS],
)
def test_every_position_and_height_heading_names_the_frame_its_cells_hold(
    tmp_path, job_id, direction, label, frame, kind, mode, convention
):
    """Interim gate 2, H1: the record's sentence, made true and pinned at the root."""
    result, archive = _h1_write(tmp_path, direction, label, frame, kind, mode, convention)
    record = " ".join(_record(archive).split())
    assert "Every latitude, longitude and ellipsoid height column names its frame." in record
    assert "Every position and ellipsoid height column" not in record
    checked = _check_every_position_heading(result, archive)
    # Anti-vacuity: the pivot's four, the external position's four and the
    # factors' h always; the degree pairs wherever they hold degrees - which
    # are exactly the four headings the gate found unnamed.
    assert len(checked) >= 9, checked
    geodetic_source = direction is not Direction.ZONE_TO_GEODETIC
    geodetic_target = direction is not Direction.GEODETIC_TO_ZONE
    assert any(h.startswith("Source latitude (") for h in checked) is geodetic_source
    assert any(h.startswith("Source longitude (") for h in checked) is geodetic_source
    assert any(h.startswith("Target latitude (") for h in checked) is geodetic_target
    assert any(h.startswith("Target longitude (") for h in checked) is geodetic_target
    if kind is HeightKind.ELLIPSOID:
        assert any("before transformation" in h for h in checked)
        assert any("after transformation" in h for h in checked)


def test_the_vertical_only_target_pair_carries_the_input_frame(written):
    """The reviewer's VERTICAL_ONLY case, ITRF2020 with ``1,43.0,84.5,165.000``:
    the Target pair mirrors the input, so it is ITRF2020's - the frame of the
    path's FIRST end - not the NAD83(2011) the path ends in; the cells are the
    input exactly (43.0, 84.5 positive west, the file's own convention)."""
    _result, archive = written["vertical_only"]
    audit = _audit(archive)
    assert audit[0]["Target latitude (ITRF2020)"] == "43.00000000"
    assert audit[0]["Target longitude (ITRF2020, as written)"] == "84.50000000"
    assert audit[0]["Source latitude (ITRF2020)"] == "43.00000000"
    assert "Target latitude (NAD83(2011))" not in audit[0]


def test_the_reviewers_z2g_g2139_job_names_every_position_heading(tmp_path):
    """The reviewer's own H1 input: ZONE_TO_GEODETIC from MI-S to WGS84(G2139),
    2019-03-01, ELLIPSOID heights - the Target pair is WGS84(G2139)'s."""
    result, archive = _write_job(
        tmp_path,
        f"1,{_NAD83_SOUTH.target_northing!r},{_NAD83_SOUTH.target_easting!r},165.000,P\n",
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        geodetic_frame=WGS84_G2139,
        observation_date=datetime.date(2019, 3, 1),
        input_height_kind=HeightKind.ELLIPSOID,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    header = _csv_rows(member_text(archive, "_full.csv"))[0]
    assert header[5:7] == [
        "Target latitude (WGS84(G2139))",
        "Target longitude (WGS84(G2139), as written)",
    ]
    _check_every_position_heading(result, archive)


# --------------------------------------------------------------------------
# H2: the Factor height paragraph names only the factors that exist.
# --------------------------------------------------------------------------

def _flat(archive: Path) -> str:
    return " ".join(_record(archive).split())


_ZONELESS_FACTOR_HEIGHT = (
    # job.factors_use_source_era's configuration (a NAVD 88 to NGVD 29 job
    # whose only model, GEOID18, is NAVD 88's) on a job with no zone: no grid
    # scale factor, so no combined factor - the summary's own words below.
    "Factor height The elevation factor was computed from the SOURCE-datum "
    "(NAVD88) height, not from the shifted height the Z column carries."
)
_ZONE_FACTOR_HEIGHT = (
    "Factor height The elevation and combined factors were computed from the "
    "SOURCE-datum (NAVD88) height, not from the shifted height the Z column "
    "carries."
)


def test_the_reviewers_vertical_only_nad83_job_states_no_combined_factor(tmp_path):
    """Gate 2, H2 job (a) - reachable from the released 0.7.1 GUI: VERTICAL_ONLY,
    NAD83(2011) geodetic, NAVD88 to NGVD29, GEOID18, ``1,43.0,84.5,165.000``,
    positive west."""
    result, archive = _vo_geodetic(
        tmp_path, rows="1,43.0,84.5,165.000\n", target_vertical_datum=NGVD29
    )
    flat = _flat(archive)
    assert result.combined_factors == () and result.points[0].factors.elevation_factor is not None
    assert _ZONELESS_FACTOR_HEIGHT in flat
    assert "combined factors were computed" not in flat
    assert "No combined factors exist for this job" in flat


def test_the_reviewers_g2g_job_states_no_combined_factor(tmp_path):
    """Gate 2, H2 job (b): GEODETIC_TO_GEODETIC from WGS84(G2296) to
    NAD83(2011), 2025-06-15, HORIZONTAL_AND_VERTICAL, NAVD88 to NGVD29."""
    result, archive = _write_job(
        tmp_path,
        "1,43.0,84.5,165.000,P\n",
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        target_geodetic_frame=NAD83_2011,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NGVD29,
    )
    flat = _flat(archive)
    assert result.combined_factors == () and result.points[0].factors.elevation_factor is not None
    assert _ZONELESS_FACTOR_HEIGHT in flat
    assert "combined factors were computed" not in flat
    assert "No combined factors exist for this job" in flat


@pytest.mark.parametrize("shape", ["g2z", "vo_zone"])
def test_the_zone_jobs_factor_height_wording_is_unchanged(tmp_path, shape):
    """The control: a job WITH a zone has a combined factor, and keeps the
    paragraph's wording since #41 - a NAD 83 geodetic job into MI-S, and a
    vertical-only job on MI-S grid input (factors under the input zone)."""
    fields = dict(
        geodetic_frame=NAD83_2011,
        observation_date=None,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NGVD29,
    )
    rows = "1,43.0,84.5,165.000,P\n"
    if shape == "vo_zone":
        fields.update(
            direction=Direction.VERTICAL_ONLY, source_zone=MI_SOUTH, target_zone=None,
            vertical_mode=VerticalMode.VERTICAL, longitude_convention=None,
        )
        rows = f"1,{_NAD83_SOUTH.target_northing!r},{_NAD83_SOUTH.target_easting!r},165.000,P\n"
    result, archive = _write_job(tmp_path, rows, **fields)
    assert result.combined_factors
    assert _ZONE_FACTOR_HEIGHT in _flat(archive)


# --------------------------------------------------------------------------
# L3: the round-trip bound states the epochs it was measured over, and says
# when a job's date is outside them.
# --------------------------------------------------------------------------

def test_the_round_trip_range_is_the_committed_measurement():
    """1990-01-01 to 2035-12-31, and the stated bound covers what was measured.

    Interim gate 2, L3, superseding the W0-range pin: the range and the bound
    are held to ``review/wgs84-gate2/roundtrip_range_output.txt``, the lead's
    measurement through ``michspc.spc.htdp`` (which reproduces HTDP at every
    printed digit). The stated figures, 9.2e-6 / 6.4e-5 / 4.3e-6 m, are W0's
    (RECON.md section 5); the measurement must not exceed any of them.
    """
    output = (
        REPO / "review" / "wgs84-gate2" / "roundtrip_range_output.txt"
    ).read_text(encoding="utf-8").splitlines()
    fields = {line.split()[0]: line.split()[1] for line in output}
    assert fields["first"] == report.ROUND_TRIP_MEASURED_FROM.isoformat() == "1990-01-01"
    assert fields["last"] == report.ROUND_TRIP_MEASURED_TO.isoformat() == "2035-12-31"
    assert int(fields["positions"]) == 83
    # N1: the measured heights bound the stated range. The non-closure is
    # linear in the height handed to HTDP, so the measured ends bound every
    # height between them.
    measured = [float(h) for h in fields["heights_m"].split(",")]
    assert min(measured) <= report.ROUND_TRIP_HEIGHT_FROM_M == -250.0
    assert max(measured) >= report.ROUND_TRIP_HEIGHT_TO_M == 610.0
    assert "heights handed to HTDP from -250 m to 610 m" in " ".join(
        report.ROUND_TRIP_NON_CLOSURE.split()
    )
    for key, stated in (("worst_north_m", 9.2e-6), ("worst_east_m", 6.4e-5), ("worst_up_m", 4.3e-6)):
        assert float(fields[key]) <= stated, key
    assert (
        "for observation dates from 1990-01-01 to 2035-12-31"
        in " ".join(report.ROUND_TRIP_NON_CLOSURE.split())
    )
    assert "up to 9.2e-6 m north, 6.4e-5 m east and 4.3e-6 m up" in report.ROUND_TRIP_NON_CLOSURE


_OUTSIDE = (
    "This job's observation date, {date}, is outside that range: the bound "
    "stated was measured for observation dates 1990-01-01 to 2035-12-31 and "
    "does not cover this date."
)


@pytest.mark.parametrize(
    "date,decimal",
    [
        # The reviewer's "before about 1985" case.
        (datetime.date(1950, 6, 15), None),
        # One day before the range starts.
        (datetime.date(1989, 12, 31), None),
    ],
)
def test_a_date_outside_the_measured_range_says_the_bound_does_not_cover_it(
    tmp_path, monkeypatch, date, decimal
):
    from michspc import job as job_module

    monkeypatch.setattr(job_module, "today", lambda: datetime.date(2026, 10, 21))
    _result, archive = _write_job(
        tmp_path, "1,43.0,84.5,165.000,P\n", geodetic_frame=ITRF2020, observation_date=date
    )
    flat = _flat(archive)
    assert " ".join(_ROUND_TRIP.split()) in flat
    assert _OUTSIDE.format(date=date.isoformat()) in flat


@pytest.mark.parametrize(
    "date",
    [
        datetime.date(1990, 1, 1),  # the range's first day
        datetime.date(2026, 10, 20),
        datetime.date(2026, 10, 21),  # W0's range ended the day before
        L5_DATE,
    ],
)
def test_a_date_inside_the_measured_range_adds_nothing(tmp_path, monkeypatch, date):
    from michspc import job as job_module

    monkeypatch.setattr(job_module, "today", lambda: datetime.date(2026, 10, 21))
    _result, archive = _write_job(
        tmp_path, "1,43.0,84.5,165.000,P\n", geodetic_frame=ITRF2020, observation_date=date
    )
    flat = _flat(archive)
    assert " ".join(_ROUND_TRIP.split()) in flat
    assert "does not cover this date" not in flat


def test_the_day_after_the_measured_range_says_the_bound_does_not_cover_it(
    tmp_path, monkeypatch
):
    """2036-01-01, the first day past ROUND_TRIP_MEASURED_TO (2035-12-31).

    The job's clock is set to 2036-06-01 so the date is not refused as in the
    future; the sentence must then name the date and the measured range.
    """
    from michspc import job as job_module

    monkeypatch.setattr(job_module, "today", lambda: datetime.date(2036, 6, 1))
    _result, archive = _write_job(
        tmp_path,
        "1,43.0,84.5,165.000,P\n",
        geodetic_frame=ITRF2020,
        observation_date=datetime.date(2036, 1, 1),
    )
    assert _OUTSIDE.format(date="2036-01-01") in _flat(archive)


# --------------------------------------------------------------------------
# Interim gate 2 re-confirmation, N1: the bound states the heights it was
# measured over, and the record counts the points handed HTDP a height
# outside them.
# --------------------------------------------------------------------------


def test_a_point_handed_a_height_outside_the_range_is_counted(tmp_path, monkeypatch):
    """Two ELLIPSOID points: h = 700 m (above the 610 m end, where the reviewer
    measured the east non-closure past 6.4e-5 m) and h = 165 m (inside). An
    ellipsoid Z is the height HTDP is handed (plan D6), so exactly 1 of 2 is
    outside."""
    from michspc import job as job_module

    monkeypatch.setattr(job_module, "today", lambda: datetime.date(2026, 10, 21))
    _result, archive = _write_job(
        tmp_path,
        "1,43.0,84.5,700.000,HIGH\n2,43.0,84.5,165.000,P\n",
        geodetic_frame=ITRF2020,
        observation_date=L5_DATE,
        input_height_kind=HeightKind.ELLIPSOID,
    )
    flat = _flat(archive)
    assert (
        "1 of this job's 2 points were handed HTDP a height outside -250 m to "
        "610 m, so the bound stated does not cover them." in flat
    )


def test_heights_inside_the_range_add_nothing(tmp_path, monkeypatch):
    """h = 165 m and a blank Z (handed h = 0, plan D6): both inside."""
    from michspc import job as job_module

    monkeypatch.setattr(job_module, "today", lambda: datetime.date(2026, 10, 21))
    _result, archive = _write_job(
        tmp_path,
        "1,43.0,84.5,165.000,P\n2,43.0,84.5,,BLANK\n",
        geodetic_frame=ITRF2020,
        observation_date=L5_DATE,
        input_height_kind=HeightKind.ELLIPSOID,
    )
    assert "does not cover them" not in _flat(archive)


# --------------------------------------------------------------------------
# Interim gate 2 re-confirmation, N3: on a vertical-mode geodetic-to-geodetic
# job HTDP is the whole of the HORIZONTAL conversion only - VERTCON (or
# H = h - N) converts the elevation.
# --------------------------------------------------------------------------


def test_a_vertical_mode_g2g_job_says_htdp_is_the_horizontal_conversion(tmp_path):
    """The reviewer's job: G2296 -> NAD83(2011), H+V, NAVD 88 -> NGVD 29."""
    _result, archive = _write_job(
        tmp_path,
        "1,43.0,84.5,200.000,P\n",
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        target_geodetic_frame=NAD83_2011,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NGVD29,
    )
    flat = " ".join(_record(archive).split())
    assert (
        "the frame transformation, which is the whole of this job's "
        "horizontal conversion; the elevation conversion is stated below."
        in flat
    )
    assert "whole of this job's conversion." not in flat


def test_a_horizontal_g2g_job_keeps_the_whole_conversion_wording(tmp_path):
    """HORIZONTAL mode: no elevation is converted, so HTDP is the whole of it."""
    _result, archive = _write_job(
        tmp_path,
        "1,43.0,84.5,200.000,P\n",
        direction=Direction.GEODETIC_TO_GEODETIC,
        target_zone=None,
        target_geodetic_frame=NAD83_2011,
    )
    flat = " ".join(_record(archive).split())
    assert "the frame transformation, which is the whole of this job's conversion." in flat
