"""The 2026-08-06 NGS cross-check, frozen as permanent anchors.

Two layers, and the second is the one that was missing.

1. **Core anchors.** The thirteen fresh cross-check points against
   ``lambert.forward`` / ``lambert.inverse`` and ``geoid18.geoid_height``,
   exactly as ``test_lambert.py`` does for the 2026-08-05 lattice.

2. **End-to-end anchors.** The same NGS numbers driven through the production
   entry points a surveyor actually runs - ``job.run`` ->
   ``exports.write_all`` -> the ZIP on disk -> the clean PNEZD export and the
   audit CSV, parsed back out. Every existing coordinate anchor in this suite
   stops at ``lambert.forward``, which is why unit-labelling and record
   defects in the file layer were invisible to it (WP-R2 fixes A and F,
   WP-R3 fix 1). An anchor that stops at the engine cannot see them.

Nothing here is compared against a number this program produced. Every
expected value is an NGS figure transcribed from a raw JSON capture into
``tests/fixtures/ncat_crosscheck.py``; the elevations, which NGS has no
opinion about, are the cross-check's own chosen inputs and are only ever
asserted to survive a unit round trip.

**No test in this module touches the network.**
"""

from __future__ import annotations

import csv
import io
import math
from pathlib import Path

import pytest

from tests.conftest import extract_member, member_text
from tests.fixtures.ncat_anchors import NCAT_ANCHORS
from tests.fixtures.ncat_crosscheck import (
    CROSSCHECK_FORWARD,
    CROSSCHECK_GEOID,
    CROSSCHECK_INVERSE,
    CROSSCHECK_POINTS,
    CROSSCHECK_TOLERANCES,
)

from michspc.fileio import exports, geoid18, pnezd
from michspc.job import Direction, JobSettings, LongitudeConvention, run
from michspc.spc.lambert import constants_for, forward, inverse
from michspc.spc.units import INTERNATIONAL_FEET, METERS, US_SURVEY_FEET, LinearUnit
from michspc.spc.zones import zone_by_code

# --------------------------------------------------------------------------
# Tolerances. Each is the figure the live run established and passed at, and
# each is derived from what NGS prints rather than chosen for convenience.
# --------------------------------------------------------------------------

LINEAR_TOLERANCE_M = CROSSCHECK_TOLERANCES["linear_m"]
"""0.002 m. NCAT publishes to 0.001 m, so one figure carries +-0.0005 m."""

# A zone-to-zone conversion is anchored at BOTH ends by an NCAT figure, so it
# gets two legs of that quantization rather than one.
ZONE_TO_ZONE_TOLERANCE_M = 2.0 * LINEAR_TOLERANCE_M

GEOID_TOLERANCE_M = CROSSCHECK_TOLERANCES["geoid_m"]
SCALE_FACTOR_TOLERANCE = CROSSCHECK_TOLERANCES["scale_factor"]
CONVERGENCE_TOLERANCE_DEG = CROSSCHECK_TOLERANCES["convergence_arcsec"] / 3600.0

# Metres per degree, used only to express a linear tolerance in degrees.
#
# A degree of latitude on GRS 80 is shortest at the equator, 110,574 m
# (Michigan's is about 111,100 m), so dividing by 110,574 never understates the
# degree equivalent of a linear tolerance. A degree of longitude is longest at
# the equator, 111,320 m, shrinking as cos(phi), so dividing by
# 111,320 cos(phi) never overstates it. Both figures are the standard GRS 80
# quantities; neither is load-bearing beyond setting a tolerance about 0.5%
# either side of the truth at Michigan's latitudes.
_METRES_PER_DEGREE_LATITUDE = 110574.0
_METRES_PER_DEGREE_LONGITUDE_AT_EQUATOR = 111320.0

# formatting.latitude / formatting.longitude write 8 decimal places, so a
# written degree carries half of the eighth place on top of everything else.
_DEGREE_ROUNDING = 0.5e-8


def _latitude_tolerance(metres: float = LINEAR_TOLERANCE_M) -> float:
    return metres / _METRES_PER_DEGREE_LATITUDE + _DEGREE_ROUNDING


def _longitude_tolerance(
    latitude: float, metres: float = LINEAR_TOLERANCE_M
) -> float:
    parallel = _METRES_PER_DEGREE_LONGITUDE_AT_EQUATOR * math.cos(
        math.radians(latitude)
    )
    return metres / parallel + _DEGREE_ROUNDING


def _linear_tolerance(unit: LinearUnit, metres: float = LINEAR_TOLERANCE_M) -> float:
    """A metre tolerance expressed in ``unit``, plus that unit's own rounding.

    ``f"{v:.Nf}"`` moves a value by at most half of the last place it keeps, and
    the export is written at the unit's declared precision - 3 places in feet,
    4 in metres - so that half-place is part of the budget for any value read
    back out of a written file.
    """
    return unit.from_meters(metres) + 0.5 * 10.0 ** -unit.decimals


def _dms_to_degrees(text: str) -> float:
    """``"-00 26 14.24"`` -> decimal degrees, sign on the whole quantity.

    Accepts the leading ``+`` that ``formatting.angle_dms`` writes and NCAT
    does not, so the same parser reads both the frozen NGS string and the cell
    this program produced.
    """
    body = text.strip()
    sign = -1.0 if body.startswith("-") else 1.0
    degrees, minutes, seconds = body.lstrip("+-").split()
    return sign * (float(degrees) + float(minutes) / 60.0 + float(seconds) / 3600.0)


# --------------------------------------------------------------------------
# Indexes over the frozen data.
# --------------------------------------------------------------------------

POINT_BY_ID = {p.point_id: p for p in CROSSCHECK_POINTS}
FORWARD_BY_KEY = {(f.point_id, f.zone_code): f for f in CROSSCHECK_FORWARD}
INVERSE_BY_KEY = {(i.point_id, i.zone_code, i.unit_code): i for i in CROSSCHECK_INVERSE}
GEOID_BY_ID = {g.point_id: g for g in CROSSCHECK_GEOID}

FORWARD_IDS = [f"{f.point_id}@{f.zone_code}" for f in CROSSCHECK_FORWARD]
INVERSE_IDS = [f"{i.point_id}@{i.zone_code}/{i.unit_code}" for i in CROSSCHECK_INVERSE]
GEOID_IDS = [g.point_id for g in CROSSCHECK_GEOID]

UNITS: tuple[LinearUnit, ...] = (METERS, INTERNATIONAL_FEET, US_SURVEY_FEET)

# The four points that sit in each zone, in the order they appear in the file
# the end-to-end jobs write.
ZONE_POINT_IDS = {
    "2111": ("N1", "N2", "N3", "N4"),
    "2112": ("C1", "C2", "C3", "C4"),
    "2113": ("S1", "S2", "S3", "S4"),
}

# The three points NCAT computed in two zones each, giving a directed
# zone-to-zone pair whose BOTH ends are NGS figures rather than ours.
ZONE_PAIRS = (
    ("2112", "2111", "C2"),
    ("2111", "2112", "C2"),
    ("2113", "2112", "S2"),
    ("2112", "2113", "S2"),
    ("2111", "2113", "NS"),
    ("2113", "2111", "NS"),
)


def _ncat_linear(record, unit: LinearUnit, axis: str) -> float:
    """The NCAT northing or easting in ``unit``, from a frozen forward record.

    ``LinearUnit.code`` is ``m``/``ift``/``usft`` and the fixture's fields are
    named to match, so the unit under test selects NGS's own figure for that
    unit rather than one this program converted.
    """
    return getattr(record, f"{axis}_{unit.code}")


# ==========================================================================
# Task 2 - the cross-check frozen as core anchors.
# ==========================================================================


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", CROSSCHECK_FORWARD, ids=FORWARD_IDS)
def test_crosscheck_forward_matches_ncat_in_metres(anchor):
    """Expected values computed by NGS NCAT, not by this codebase."""
    point = forward(
        anchor.latitude, anchor.longitude, constants_for(zone_by_code(anchor.zone_code))
    )

    assert point.northing == pytest.approx(
        anchor.northing_m, abs=LINEAR_TOLERANCE_M
    )
    assert point.easting == pytest.approx(anchor.easting_m, abs=LINEAR_TOLERANCE_M)


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", CROSSCHECK_FORWARD, ids=FORWARD_IDS)
def test_crosscheck_forward_matches_ncat_in_both_foot_units(anchor):
    """NCAT publishes each point in metres, International feet and US survey feet.

    The International foot is 0.3048 m exactly and the US survey foot
    1200/3937 m exactly (michspc/spc/units.py), so these are the same physical
    position under three definitions. The two feet differ by 2 ppm, which at
    Michigan North's 8,000,000 m false easting is about 52 feet - the error
    this anchor exists to catch.
    """
    point = forward(
        anchor.latitude, anchor.longitude, constants_for(zone_by_code(anchor.zone_code))
    )

    for unit in (INTERNATIONAL_FEET, US_SURVEY_FEET):
        # 0.002 m expressed in the unit; NCAT prints feet to 0.001 as well, so
        # the same physical budget applies.
        tolerance = unit.from_meters(LINEAR_TOLERANCE_M)
        assert unit.from_meters(point.northing) == pytest.approx(
            _ncat_linear(anchor, unit, "northing"), abs=tolerance
        )
        assert unit.from_meters(point.easting) == pytest.approx(
            _ncat_linear(anchor, unit, "easting"), abs=tolerance
        )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", CROSSCHECK_FORWARD, ids=FORWARD_IDS)
def test_crosscheck_forward_matches_ncat_convergence(anchor):
    """Convergence angle, to the 0.01 arc second NCAT prints."""
    point = forward(
        anchor.latitude, anchor.longitude, constants_for(zone_by_code(anchor.zone_code))
    )

    assert point.convergence == pytest.approx(
        anchor.convergence_deg, abs=CONVERGENCE_TOLERANCE_DEG
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", CROSSCHECK_FORWARD, ids=FORWARD_IDS)
def test_crosscheck_forward_matches_ncat_scale_factor(anchor):
    """Grid scale factor, to the 8 decimal places NCAT prints."""
    point = forward(
        anchor.latitude, anchor.longitude, constants_for(zone_by_code(anchor.zone_code))
    )

    assert point.scale_factor == pytest.approx(
        anchor.scale_factor, abs=SCALE_FACTOR_TOLERANCE
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", CROSSCHECK_FORWARD, ids=FORWARD_IDS)
def test_the_frozen_convergence_in_degrees_agrees_with_the_dms_string(anchor):
    """The one derived field in the fixture, checked against its own source.

    ``convergence_dms`` is NCAT's string verbatim; ``convergence_deg`` is that
    string in decimal degrees, and it is the only value in the fixture that is
    not a straight transcription. Re-deriving it here means a slip in the
    generator - a dropped sign in particular, which is what a convergence
    transcription gets wrong - cannot pass unnoticed.

    Hand-derived: a DMS reading of d m s carries its sign on the whole
    quantity, so the decimal form is sign x (d + m/60 + s/3600). For N1's
    "-00 26 14.24" that is -(0 + 26/60 + 14.24/3600) = -0.4372888... degrees.
    """
    assert _dms_to_degrees(anchor.convergence_dms) == pytest.approx(
        anchor.convergence_deg, abs=1e-15
    )
    # The sign specifically: a positive convergence must not carry "-".
    assert (anchor.convergence_deg < 0.0) == anchor.convergence_dms.strip().startswith(
        "-"
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", CROSSCHECK_INVERSE, ids=INVERSE_IDS)
def test_crosscheck_inverse_matches_ncat_geodetic(anchor):
    """NCAT's own State-Plane-to-geodetic result, in all three units.

    Both ends of this anchor are NGS's numbers: the northing and easting are
    the ones NCAT printed for the point, and the latitude and longitude are
    what NCAT returned when they were handed back to it. This is the direction
    ``ZONE_TO_GEODETIC`` runs, and it had no coordinate anchor of any kind
    before this package.

    The query coordinates are in ``unit_code``, so they are converted to metres
    here by the exact unit definitions before reaching the engine - which is
    what ``michspc.job`` does at the same boundary.
    """
    unit = {"m": METERS, "ift": INTERNATIONAL_FEET, "usft": US_SURVEY_FEET}[
        anchor.unit_code
    ]
    position = inverse(
        unit.to_meters(anchor.northing),
        unit.to_meters(anchor.easting),
        constants_for(zone_by_code(anchor.zone_code)),
    )

    assert position.latitude == pytest.approx(
        anchor.latitude, abs=_latitude_tolerance()
    )
    assert position.longitude == pytest.approx(
        anchor.longitude, abs=_longitude_tolerance(anchor.latitude)
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", CROSSCHECK_GEOID, ids=GEOID_IDS)
def test_crosscheck_geoid_heights_match_the_ngs_geoid_api(anchor):
    """Our GEOID18 reader and interpolator against NGS's own service.

    The shipped tile and the API are the same model, so agreement here is a
    statement about the reader and the biquadratic interpolation
    (docs/DESIGN.md amendment #8), not about the model.

    The sign is checked as well: in the conterminous United States the
    ellipsoid lies above the geoid, so every Michigan separation is negative
    (manual PDF p. 57). A positive one is always an error.
    """
    height = geoid18.geoid_height(anchor.latitude, anchor.longitude)

    assert height == pytest.approx(anchor.geoid_height_m, abs=GEOID_TOLERANCE_M)
    assert height < 0.0


def test_the_crosscheck_points_share_no_position_with_the_frozen_lattice():
    """These anchors are independent of the 2026-08-05 ones, not a re-run.

    A second set of anchors at the same positions would double the count and
    prove nothing new. The cross-check chose its thirteen points to avoid every
    latitude and every longitude in ``ncat_anchors.py`` - different values, not
    just different pairings - and that is a property worth holding, because a
    future top-up of either fixture could quietly break it.
    """
    lattice_latitudes = {a.latitude for a in NCAT_ANCHORS}
    lattice_longitudes = {a.longitude for a in NCAT_ANCHORS}

    for point in CROSSCHECK_POINTS:
        assert point.latitude not in lattice_latitudes
        assert point.longitude not in lattice_longitudes

    # And the thirteen are thirteen distinct places.
    assert len({(p.latitude, p.longitude) for p in CROSSCHECK_POINTS}) == 13


# ==========================================================================
# Task 3 - the same NGS numbers through the production path.
#
#   PNEZD file on disk -> job.run -> exports.write_all -> <stem>.zip
#                      -> the clean PNEZD export and the audit CSV, re-parsed
#
# This is the gap the closing review found: 27 anchors drove lambert.forward
# and lambert.inverse directly, and nothing drove a coordinate the whole way
# out to a written file. Every assertion below compares a value read back out
# of the archive against an NGS figure.
# ==========================================================================


class WrittenJob:
    """One job run to completion, with its archive opened and parsed.

    Holds what the surveyor ends up with: the clean PNEZD export as this
    program's own reader returns it, and the audit CSV as rows of text.
    """

    def __init__(self, result, archive: Path, workspace: Path):
        self.result = result
        self.archive = archive
        self.clean = pnezd.read(
            extract_member(archive, _clean_suffix(result), workspace)
        )
        audit_text = member_text(archive, "_full.csv")
        rows = list(csv.reader(io.StringIO(audit_text)))
        self.audit_header = rows[0]
        self.audit = {row[0]: row for row in rows[1:]}


def _clean_suffix(result) -> str:
    """The clean export's own file name inside the archive.

    Taken from ``exports.member_names`` rather than reconstructed, so a test
    can never read the audit CSV while believing it read the clean export -
    both end in ``.csv``.
    """
    return exports.member_names(result)["pnezd"]


def _write_input(path: Path, rows: list[str]) -> Path:
    path.write_text("".join(line + "\n" for line in rows), encoding="utf-8", newline="")
    return path


def _run_and_write(workspace: Path, settings: JobSettings) -> WrittenJob:
    result = run(settings)
    written = exports.write_all(result)
    return WrittenJob(result, written["archive"], workspace / "unzipped")


def _geodetic_to_zone(workspace: Path, zone_code: str, unit: LinearUnit) -> WrittenJob:
    """A geodetic input file for one zone's four points, converted into it.

    The file's columns two and three are decimal degrees written to 10 places -
    the precision NCAT itself publishes a position to - and the Z column is the
    cross-check's chosen orthometric height in metres, so ``input_unit`` is
    metres and ``output_unit`` is the unit under test.
    """
    rows = []
    for point_id in ZONE_POINT_IDS[zone_code]:
        point = POINT_BY_ID[point_id]
        rows.append(
            f"{point_id},{point.latitude:.10f},{point.longitude:.10f},"
            f"{point.elevation_m:.4f},NCAT {point_id}"
        )
    path = _write_input(workspace / f"g2z_{zone_code}_{unit.code}.txt", rows)
    return _run_and_write(
        workspace,
        JobSettings(
            input_path=path,
            output_directory=workspace / f"out_g2z_{zone_code}_{unit.code}",
            direction=Direction.GEODETIC_TO_ZONE,
            source_zone=None,
            target_zone=zone_by_code(zone_code),
            input_unit=METERS,
            output_unit=unit,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        ),
    )


def _zone_to_geodetic(workspace: Path, zone_code: str, unit: LinearUnit) -> WrittenJob:
    """One zone's four points as State Plane in ``unit``, converted to geodetic.

    The northings and eastings are the ones NCAT printed for these points in
    this unit. The Z column is the chosen height re-expressed in the same unit,
    because ``input_unit`` governs the whole file; the output unit is metres, so
    the elevation must come back out as the height it went in as.
    """
    rows = []
    for point_id in ZONE_POINT_IDS[zone_code]:
        anchor = INVERSE_BY_KEY[(point_id, zone_code, unit.code)]
        elevation = unit.from_meters(POINT_BY_ID[point_id].elevation_m)
        rows.append(
            f"{point_id},{anchor.northing:.3f},{anchor.easting:.3f},"
            f"{elevation:.{unit.decimals}f},NCAT {point_id}"
        )
    path = _write_input(workspace / f"z2g_{zone_code}_{unit.code}.txt", rows)
    return _run_and_write(
        workspace,
        JobSettings(
            input_path=path,
            output_directory=workspace / f"out_z2g_{zone_code}_{unit.code}",
            direction=Direction.ZONE_TO_GEODETIC,
            source_zone=zone_by_code(zone_code),
            target_zone=None,
            input_unit=unit,
            output_unit=METERS,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        ),
    )


def _zone_to_zone(
    workspace: Path, source_code: str, target_code: str, point_id: str, unit: LinearUnit
) -> WrittenJob:
    """One pair point, converted from one zone into another, in ``unit``.

    Both ends are NGS figures: the input is what NCAT computed for this
    position in the source zone, and the expected output is what NCAT computed
    for the same position in the target zone. Nothing this program produced
    appears on either side.
    """
    source = FORWARD_BY_KEY[(point_id, source_code)]
    elevation = unit.from_meters(POINT_BY_ID[point_id].elevation_m)
    rows = [
        f"{point_id},{_ncat_linear(source, unit, 'northing'):.3f},"
        f"{_ncat_linear(source, unit, 'easting'):.3f},"
        f"{elevation:.{unit.decimals}f},NCAT {point_id}"
    ]
    tag = f"{source_code}_{target_code}_{unit.code}"
    path = _write_input(workspace / f"z2z_{tag}.txt", rows)
    return _run_and_write(
        workspace,
        JobSettings(
            input_path=path,
            output_directory=workspace / f"out_z2z_{tag}",
            direction=Direction.ZONE_TO_ZONE,
            source_zone=zone_by_code(source_code),
            target_zone=zone_by_code(target_code),
            input_unit=unit,
            output_unit=unit,
            longitude_convention=None,
        ),
    )


@pytest.fixture(scope="module")
def written_jobs(tmp_path_factory):
    """Every end-to-end configuration, run once and written to a real archive.

    Module scoped because each entry is a full job: a file read from disk, a
    conversion, a ZIP staged, flushed, verified and renamed. The tests below
    only read what came back out, so one run per configuration is enough and
    the suite does not pay for it 36 times.
    """
    workspace = tmp_path_factory.mktemp("ncat_crosscheck")
    jobs: dict[tuple, WrittenJob] = {}

    for zone_code in ZONE_POINT_IDS:
        for unit in UNITS:
            jobs[("g2z", zone_code, unit.code)] = _geodetic_to_zone(
                workspace, zone_code, unit
            )
            jobs[("z2g", zone_code, unit.code)] = _zone_to_geodetic(
                workspace, zone_code, unit
            )

    for source_code, target_code, point_id in ZONE_PAIRS:
        for unit in UNITS:
            jobs[("z2z", source_code, target_code, unit.code)] = _zone_to_zone(
                workspace, source_code, target_code, point_id, unit
            )

    return jobs


# Audit CSV column positions, counted from AUDIT_COLUMNS in exports.py:
# Point(0) Source zone(1) Source N(2) Source E(3) Target zone(4) Target N(5)
# Target E(6) Elevation(7) Units(8) Latitude(9) Longitude(10) Geoid(11)
# Ellipsoid height(12) Source k(13) Source convergence(14) k(15)
# Convergence(16) Elevation factor(17) Combined factor(18) ppm(19)
# Warnings(20) Description(21).
AUDIT_TARGET_NORTHING = 5
AUDIT_TARGET_EASTING = 6
AUDIT_ELEVATION = 7
AUDIT_LATITUDE = 9
AUDIT_LONGITUDE = 10
AUDIT_GEOID = 11
AUDIT_SCALE_FACTOR = 15
AUDIT_CONVERGENCE = 16

ZONE_UNIT_CASES = [
    (zone_code, unit)
    for zone_code in ZONE_POINT_IDS
    for unit in UNITS
]
ZONE_UNIT_IDS = [f"{z}-{u.code}" for z, u in ZONE_UNIT_CASES]

PAIR_UNIT_CASES = [
    (source, target, point_id, unit)
    for source, target, point_id in ZONE_PAIRS
    for unit in UNITS
]
PAIR_UNIT_IDS = [
    f"{s}->{t}-{u.code}" for s, t, _p, u in PAIR_UNIT_CASES
]


# --------------------------------------------------------------------------
# GEODETIC_TO_ZONE, end to end.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("zone_code, unit", ZONE_UNIT_CASES, ids=ZONE_UNIT_IDS)
def test_e2e_geodetic_to_zone_clean_export_matches_ncat(written_jobs, zone_code, unit):
    """The file CAD imports, read back with this program's own reader.

    The expected northing and easting are NCAT's own figures **for this unit** -
    not metres converted here - so a defect in the output-unit boundary shows
    as a coordinate error rather than cancelling out.
    """
    job = written_jobs[("g2z", zone_code, unit.code)]
    tolerance = _linear_tolerance(unit)

    assert [row.point_id for row in job.clean.rows] == list(ZONE_POINT_IDS[zone_code])

    for row in job.clean.rows:
        anchor = FORWARD_BY_KEY[(row.point_id, zone_code)]
        assert row.northing == pytest.approx(
            _ncat_linear(anchor, unit, "northing"), abs=tolerance
        ), f"{row.point_id} northing in {unit.code}"
        assert row.easting == pytest.approx(
            _ncat_linear(anchor, unit, "easting"), abs=tolerance
        ), f"{row.point_id} easting in {unit.code}"


@pytest.mark.anchor
@pytest.mark.parametrize("zone_code, unit", ZONE_UNIT_CASES, ids=ZONE_UNIT_IDS)
def test_e2e_geodetic_to_zone_audit_csv_matches_ncat(written_jobs, zone_code, unit):
    """The record that says how each coordinate was derived, against NGS.

    Also pins the two column headings that name what columns two and three of
    the *input* file held: a geodetic input under "Source northing" was a wrong
    statement about the file's contents, and the number under it was rounded to
    a linear unit's 3 places - 55 m of latitude (WP-R2 fix F).
    """
    job = written_jobs[("g2z", zone_code, unit.code)]
    tolerance = _linear_tolerance(unit)

    assert job.audit_header[2] == "Source latitude"
    assert job.audit_header[3] == "Source longitude (as in file)"
    assert job.audit_header[AUDIT_TARGET_NORTHING] == "Target northing"
    assert job.audit_header[AUDIT_TARGET_EASTING] == "Target easting"

    for point_id in ZONE_POINT_IDS[zone_code]:
        row = job.audit[point_id]
        anchor = FORWARD_BY_KEY[(point_id, zone_code)]
        geoid = GEOID_BY_ID[point_id]

        assert float(row[AUDIT_TARGET_NORTHING]) == pytest.approx(
            _ncat_linear(anchor, unit, "northing"), abs=tolerance
        )
        assert float(row[AUDIT_TARGET_EASTING]) == pytest.approx(
            _ncat_linear(anchor, unit, "easting"), abs=tolerance
        )
        # The geodetic pivot is the position the file was written with, so it
        # must come back out unchanged to the 8 places the column carries.
        assert float(row[AUDIT_LATITUDE]) == pytest.approx(
            anchor.latitude, abs=_DEGREE_ROUNDING
        )
        assert float(row[AUDIT_LONGITUDE]) == pytest.approx(
            anchor.longitude, abs=_DEGREE_ROUNDING
        )
        assert float(row[AUDIT_SCALE_FACTOR]) == pytest.approx(
            anchor.scale_factor, abs=SCALE_FACTOR_TOLERANCE
        )
        assert _dms_to_degrees(row[AUDIT_CONVERGENCE]) == pytest.approx(
            anchor.convergence_deg, abs=CONVERGENCE_TOLERANCE_DEG
        )
        assert float(row[AUDIT_GEOID]) == pytest.approx(
            geoid.geoid_height_m, abs=GEOID_TOLERANCE_M
        )


# --------------------------------------------------------------------------
# ZONE_TO_GEODETIC, end to end. The direction the closing review found had no
# anchored coverage of its outputs at all.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("zone_code, unit", ZONE_UNIT_CASES, ids=ZONE_UNIT_IDS)
def test_e2e_zone_to_geodetic_clean_export_matches_ncat(written_jobs, zone_code, unit):
    """State Plane in ``unit`` out to degrees, against NCAT's own inversion.

    The expected latitude and longitude are what NCAT returned when it was
    handed these very northings and eastings, so both ends of this check are
    NGS's numbers.

    The elevation is the one linear column left in a geodetic export, and the
    output unit is metres, so it must read back as the height that went in. It
    travels input unit -> metres -> output unit, and in feet the input file
    itself carries only 3 places, so the budget is that quantization
    (0.0005 ft = 0.15 mm) plus the metre column's own 0.05 mm.
    """
    job = written_jobs[("z2g", zone_code, unit.code)]

    assert [row.point_id for row in job.clean.rows] == list(ZONE_POINT_IDS[zone_code])

    for row in job.clean.rows:
        anchor = INVERSE_BY_KEY[(row.point_id, zone_code, unit.code)]
        assert row.northing == pytest.approx(
            anchor.latitude, abs=_latitude_tolerance()
        ), f"{row.point_id} latitude from {unit.code}"
        assert row.easting == pytest.approx(
            anchor.longitude, abs=_longitude_tolerance(anchor.latitude)
        ), f"{row.point_id} longitude from {unit.code}"

        expected_elevation = POINT_BY_ID[row.point_id].elevation_m
        assert row.elevation == pytest.approx(expected_elevation, abs=0.0005)


@pytest.mark.anchor
@pytest.mark.parametrize("zone_code, unit", ZONE_UNIT_CASES, ids=ZONE_UNIT_IDS)
def test_e2e_zone_to_geodetic_audit_csv_matches_ncat(written_jobs, zone_code, unit):
    """The audit CSV for the direction that had no positive coverage.

    The target columns hold degrees here, and they are named for it: a State
    Plane to geodetic job always wrote degrees into columns six and seven, but
    under headings that called them a northing and an easting (WP-R2 fix F).

    The grid quantities belong to the source zone, because there is no target
    zone - ``job._convert_row`` converts the point into its own zone - so they
    are checked against NCAT's figures for that zone.
    """
    job = written_jobs[("z2g", zone_code, unit.code)]

    assert job.audit_header[AUDIT_TARGET_NORTHING] == "Target latitude"
    assert job.audit_header[AUDIT_TARGET_EASTING] == "Target longitude (as written)"
    assert job.audit_header[2] == "Source northing"
    assert job.audit_header[3] == "Source easting"

    for point_id in ZONE_POINT_IDS[zone_code]:
        row = job.audit[point_id]
        inverse_anchor = INVERSE_BY_KEY[(point_id, zone_code, unit.code)]
        forward_anchor = FORWARD_BY_KEY[(point_id, zone_code)]
        geoid = GEOID_BY_ID[point_id]

        assert float(row[AUDIT_TARGET_NORTHING]) == pytest.approx(
            inverse_anchor.latitude, abs=_latitude_tolerance()
        )
        assert float(row[AUDIT_TARGET_EASTING]) == pytest.approx(
            inverse_anchor.longitude,
            abs=_longitude_tolerance(inverse_anchor.latitude),
        )
        # The signed pivot columns must agree with the written pair, since the
        # job's convention is negative west and no re-signing applies.
        assert float(row[AUDIT_LATITUDE]) == pytest.approx(
            inverse_anchor.latitude, abs=_latitude_tolerance()
        )
        assert float(row[AUDIT_LONGITUDE]) == pytest.approx(
            inverse_anchor.longitude,
            abs=_longitude_tolerance(inverse_anchor.latitude),
        )
        assert float(row[AUDIT_SCALE_FACTOR]) == pytest.approx(
            forward_anchor.scale_factor, abs=SCALE_FACTOR_TOLERANCE
        )
        assert _dms_to_degrees(row[AUDIT_CONVERGENCE]) == pytest.approx(
            forward_anchor.convergence_deg, abs=CONVERGENCE_TOLERANCE_DEG
        )
        assert float(row[AUDIT_GEOID]) == pytest.approx(
            geoid.geoid_height_m, abs=GEOID_TOLERANCE_M
        )
        # The elevation column is in the OUTPUT unit, metres (WP-R2 fix A).
        assert float(row[AUDIT_ELEVATION]) == pytest.approx(
            POINT_BY_ID[point_id].elevation_m, abs=0.0005
        )


# --------------------------------------------------------------------------
# ZONE_TO_ZONE, end to end - an NGS figure at both ends.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize(
    "source_code, target_code, point_id, unit", PAIR_UNIT_CASES, ids=PAIR_UNIT_IDS
)
def test_e2e_zone_to_zone_clean_export_matches_ncat(
    written_jobs, source_code, target_code, point_id, unit
):
    """NCAT's source-zone coordinate in, NCAT's target-zone coordinate out.

    This is the program's core use case and the one the polynomial method could
    not do (docs/DESIGN.md amendment #5): the target zone's coordinate for a
    point that sits deep in another zone's band. The budget is two legs of
    NCAT's 0.001 m printing rather than one, because a published figure stands
    at both ends.
    """
    job = written_jobs[("z2z", source_code, target_code, unit.code)]
    target = FORWARD_BY_KEY[(point_id, target_code)]
    tolerance = _linear_tolerance(unit, ZONE_TO_ZONE_TOLERANCE_M)

    (row,) = job.clean.rows
    assert row.point_id == point_id
    assert row.northing == pytest.approx(
        _ncat_linear(target, unit, "northing"), abs=tolerance
    )
    assert row.easting == pytest.approx(
        _ncat_linear(target, unit, "easting"), abs=tolerance
    )


@pytest.mark.anchor
@pytest.mark.parametrize(
    "source_code, target_code, point_id, unit", PAIR_UNIT_CASES, ids=PAIR_UNIT_IDS
)
def test_e2e_zone_to_zone_audit_csv_matches_ncat(
    written_jobs, source_code, target_code, point_id, unit
):
    """Both zones' grid quantities, and the geodetic pivot between them.

    The pivot is the position NCAT was queried at, so it is an NGS figure too -
    which makes this a check on the inverse leg and the forward leg separately
    rather than only on their composition.
    """
    job = written_jobs[("z2z", source_code, target_code, unit.code)]
    source = FORWARD_BY_KEY[(point_id, source_code)]
    target = FORWARD_BY_KEY[(point_id, target_code)]
    geoid = GEOID_BY_ID[point_id]
    tolerance = _linear_tolerance(unit, ZONE_TO_ZONE_TOLERANCE_M)

    assert job.audit_header[2] == "Source northing"
    assert job.audit_header[AUDIT_TARGET_NORTHING] == "Target northing"

    row = job.audit[point_id]
    assert float(row[AUDIT_TARGET_NORTHING]) == pytest.approx(
        _ncat_linear(target, unit, "northing"), abs=tolerance
    )
    assert float(row[AUDIT_TARGET_EASTING]) == pytest.approx(
        _ncat_linear(target, unit, "easting"), abs=tolerance
    )
    assert float(row[AUDIT_LATITUDE]) == pytest.approx(
        source.latitude, abs=_latitude_tolerance()
    )
    assert float(row[AUDIT_LONGITUDE]) == pytest.approx(
        source.longitude, abs=_longitude_tolerance(source.latitude)
    )
    assert float(row[AUDIT_SCALE_FACTOR]) == pytest.approx(
        target.scale_factor, abs=SCALE_FACTOR_TOLERANCE
    )
    assert _dms_to_degrees(row[AUDIT_CONVERGENCE]) == pytest.approx(
        target.convergence_deg, abs=CONVERGENCE_TOLERANCE_DEG
    )
    assert float(row[AUDIT_GEOID]) == pytest.approx(
        geoid.geoid_height_m, abs=GEOID_TOLERANCE_M
    )
