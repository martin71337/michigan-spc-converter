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
    (42.9999914437 N, 84.4999892421 W for G2296) projected by the program's
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
    HTDP's 42.9999914437 N, 84.4999892421 W within DD_CELL_DEG; the DMS file
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

_ROUND_TRIP = """\
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
            + _ROUND_TRIP + _VERIFIED
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


def test_g2g_coordinate_systems_and_method_are_exactly_this(written):
    """The FROM and TO frame blocks (the zone block's shape: frame, ellipsoid,
    epoch, the registry record's citation) and the METHOD/verification section
    in this direction's own words."""
    record = _record(written["g2g_reverse"][1])
    start = record.index("COORDINATE SYSTEMS\n")
    assert record[start:record.index("-" * 78 + "\nMETHOD", start)] == _G2G_COORDINATE_SYSTEMS
    method = record.index("METHOD\n", start)
    assert record[method:record.index("FRAME TRANSFORMATION", method)] == _G2G_METHOD


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


EXPECTED_HEADERS = {
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


@pytest.mark.parametrize("name", list(EXPECTED_HEADERS))
def test_the_audit_header_is_exactly_this(written, name):
    _result, archive = written[name]
    assert _csv_rows(member_text(archive, "_full.csv"))[0] == EXPECTED_HEADERS[name]


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


@pytest.mark.parametrize("name", list(_SUPPLIED_HEIGHT_RENAMES))
def test_the_shared_columns_keep_their_positions(written, name):
    """Against the SAME job on NAD83(2011) with no date - the same-frame job
    of the same shape - every column keeps its index: the five NAD 83
    headings and the supplied height's are renamed in place, and every new
    column follows Description. (Geodetic to geodetic has no same-frame
    shape: D7 refuses one.)"""
    result, archive = written[name]
    header = _csv_rows(member_text(archive, "_full.csv"))[0]
    same_settings = dataclasses.replace(
        result.settings, geodetic_frame=NAD83_2011, observation_date=None
    )
    same = exports.audit_columns(dataclasses.replace(result, settings=same_settings))
    renames = {**_PIVOT_RENAMES, **_SUPPLIED_HEIGHT_RENAMES[name]}
    assert header[: len(same)] == [renames.get(c, c) for c in same]
    assert sum(1 for c in same if c in renames) == len(_PIVOT_RENAMES) + len(
        _SUPPLIED_HEIGHT_RENAMES[name]
    )
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
