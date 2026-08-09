"""The vertical-only mode: ``Direction.VERTICAL_ONLY`` with
``VerticalMode.VERTICAL`` (the owner's feature, 2026-08-09).

The user states an INPUT horizontal system - a zone, or geodetic positions -
and NO output system; the only conversion performed is the vertical datum
shift, and the exports reproduce the input's coordinate columns unchanged.
What is tested here, and against what truth:

* End-to-end elevations against the frozen NGS NCAT anchors of
  ``tests/fixtures/vertcon_anchors.py``, in both input formats and both
  datum directions, at anchor-22. The vertical path is the SAME code the
  HORIZONTAL_AND_VERTICAL mode runs - not a fork - so these anchors hold the
  shared path under the new direction.
* The mirror property: the export's coordinate cells are the formatted INPUT
  values exactly, the floats underneath are the parsed input values
  bit-identically, and only the Z column differs - by exactly the shift.
  The bitwise half is the discriminating pin: a zone -> same-zone round trip
  reproduces the input to ~1e-9, so a cell quietly fed from the conversion
  instead of the input row would survive a string comparison and fails only
  here.
* The refusal matrix additions: mode and direction requiring each other, a
  supplied target zone, a unit mismatch, a longitude convention on zone
  input, a missing convention on geodetic input, a missing datum - each
  named, each teaching.
* The factors split: input zone's factors where a zone exists (the
  ZONE_TO_GEODETIC precedent, compared bitwise against that direction at the
  same point), and grid scale factor None - never a fabricated 1.0 - where
  no zone exists anywhere.
* The audit CSV and the job record disclosing all of it.

Tolerances are derived, not chosen to pass: 0.0005 m is the bound
tests/test_job_vertical.py derives from NCAT's printed precision and the
reader's measured 0.4716 mm worst residual. The zone-input rows sit on State
Plane coordinates computed by this program's own forward projection at
anchor-22's position; the inverse recovers 43.0 N, 84.5 W to 2.6e-10 degrees
(about 0.03 micrometres of ground), far inside anything the 0.05-degree
VERTCON grid can resolve, so the anchor's figure applies unchanged.
"""

from __future__ import annotations

import csv

import pytest

from michspc.fileio import exports, formatting as fmt, geoid, pnezd, vertcon
from michspc.fileio.report import build_report
from michspc.job import (
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc.convert import WarningCode
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.vertical import NAVD88, NGVD29
from michspc.spc.zones import MI_SOUTH
from tests.fixtures.vertcon_anchors import (
    NAVD88_TO_NGVD29_ANCHORS,
    NGVD29_TO_NAVD88_ANCHORS,
)

# The bound test_job_vertical.py derives; see its module docstring.
SHIFT_TOLERANCE_M = 0.0005

ANCHOR_22 = next(a for a in NGVD29_TO_NAVD88_ANCHORS if a.name == "anchor-22")
ANCHOR_22_INVERSE = next(
    a for a in NAVD88_TO_NGVD29_ANCHORS if a.name == "anchor-22"
)

# Anchor-22's position in Michigan South, metres, from this program's own
# forward projection (from_geodetic(43.0, -84.5, MI_SOUTH) = N 166625.1663719,
# E 3989128.8661130), written to the metre unit's own 4 decimals. The inverse
# of these rounded values is 43.00000000025 N, -84.50000000016 E - the anchor
# to 2.6e-10 degrees - so a vertical-only job reading them looks the VERTCON
# grid up at the anchor's own position.
ZONE_NORTHING = "166625.1664"
ZONE_EASTING = "3989128.8661"


def _geodetic_source(
    latitude,
    longitude,
    elevation: str = "200.000",
    point_id: str = "101",
    description: str = "VERT ONLY",
) -> pnezd.PnezdFile:
    return pnezd.parse_lines(
        [f"{point_id},{latitude},{longitude},{elevation},{description}"]
    )


def _zone_source(
    elevation: str = "200.000", point_id: str = "101"
) -> pnezd.PnezdFile:
    return pnezd.parse_lines(
        [f"{point_id},{ZONE_NORTHING},{ZONE_EASTING},{elevation},VERT ONLY"]
    )


def _geodetic_settings(**overrides) -> JobSettings:
    """A geodetic-input vertical-only job, NGVD 29 -> NAVD 88, metres."""
    base = dict(
        input_path=None,
        output_directory=None,
        direction=Direction.VERTICAL_ONLY,
        source_zone=None,
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    base.update(overrides)
    return JobSettings(**base)


def _zone_settings(**overrides) -> JobSettings:
    """A zone-input (PNEZD) vertical-only job: the input system is a zone,
    the file carries no longitudes, and the convention is stated None -
    exactly the zone-to-zone statement rule."""
    base = dict(
        source_zone=MI_SOUTH,
        longitude_convention=None,
    )
    base.update(overrides)
    return _geodetic_settings(**base)


# ==========================================================================
# End-to-end anchors: both input formats x both datum directions.
# ==========================================================================


@pytest.mark.parametrize(
    "settings, source, anchor",
    [
        pytest.param(
            _geodetic_settings(),
            _geodetic_source(43.0, -84.5),
            ANCHOR_22,
            id="geodetic_ngvd29_to_navd88",
        ),
        pytest.param(
            _geodetic_settings(
                source_vertical_datum=NAVD88, target_vertical_datum=NGVD29
            ),
            _geodetic_source(43.0, -84.5),
            ANCHOR_22_INVERSE,
            id="geodetic_navd88_to_ngvd29",
        ),
        pytest.param(
            _zone_settings(),
            _zone_source(),
            ANCHOR_22,
            id="zone_ngvd29_to_navd88",
        ),
        pytest.param(
            _zone_settings(
                source_vertical_datum=NAVD88, target_vertical_datum=NGVD29
            ),
            _zone_source(),
            ANCHOR_22_INVERSE,
            id="zone_navd88_to_ngvd29",
        ),
    ],
)
def test_anchor_22_shifts_the_elevation_and_nothing_else(
    settings, source, anchor
):
    """NCAT's own figure through the whole vertical-only job: 200.000 m moves
    by the anchor's shift, and the coordinate columns do not move at all -
    the outputs ARE the parsed input values, bit-identically, which is the
    pin a sign flip or a conversion-fed output cell cannot survive."""
    result = run(settings, source=source)
    point = result.points[0]
    row = source.rows[0]

    assert point.output_elevation == pytest.approx(
        anchor.target_height_m, abs=SHIFT_TOLERANCE_M
    )
    assert point.vertical is not None
    assert point.vertical.shift_m == pytest.approx(
        anchor.shift_m, abs=SHIFT_TOLERANCE_M
    )

    # Bit-identical, not merely close: the output coordinates are the input
    # row's own floats, untouched by any projection. A zone -> same-zone
    # round trip reproduces them to ~1e-9, so an approx comparison could not
    # tell a mirrored value from a re-projected one - this can.
    assert point.output_northing == row.northing
    assert point.output_easting == row.easting


def test_the_navd88_to_ngvd29_direction_keeps_geoid18_and_its_factors():
    """The #41 either-endpoint rule applies unchanged in this mode: the
    NAVD 88 leg is the SOURCE, GEOID18's own era, so the job converts and
    the factors exist - built from the source-era height, exactly as the
    HORIZONTAL_AND_VERTICAL suite pins for the shared code path."""
    result = run(
        _geodetic_settings(
            source_vertical_datum=NAVD88, target_vertical_datum=NGVD29
        ),
        source=_geodetic_source(43.0, -84.5),
    )
    point = result.points[0]
    assert point.output_elevation == pytest.approx(
        ANCHOR_22_INVERSE.target_height_m, abs=SHIFT_TOLERANCE_M
    )
    assert point.factors.elevation_factor is not None


def test_an_identity_vertical_only_job_reads_no_grid(monkeypatch):
    """NAVD 88 -> NAVD 88 vertical-only: a legitimate job that states the
    datum, applies exactly 0.0, and must succeed with the VERTCON files
    unreadable - the identity contract of the shared path, held under the
    new direction."""

    def _must_not_load():
        raise AssertionError(
            "an identity vertical-only job read the VERTCON grids"
        )

    monkeypatch.setattr(vertcon, "default_grids", _must_not_load)

    result = run(
        _geodetic_settings(
            source_vertical_datum=NAVD88, target_vertical_datum=NAVD88
        ),
        source=_geodetic_source(43.0, -84.5),
    )
    point = result.points[0]

    assert point.output_elevation == 200.0
    assert point.vertical is not None
    assert point.vertical.shift_m == 0.0
    assert point.vertical.transformation.is_identity
    assert point.vertical.sigma_m is None
    assert point.vertical.sigma_unavailable_reason is not None


def test_a_coverage_refused_point_still_passes_its_coordinates_through():
    """52.0 N is north of the CONUS grid's edge, so no shift exists there.
    The elevation is refused - never written unconverted into a Z column
    that claims the target datum - and the coordinate columns still mirror
    the input, because they never depended on the shift at all."""
    source = _geodetic_source(52.0, -84.5)
    result = run(_geodetic_settings(), source=source)
    point = result.points[0]
    row = source.rows[0]

    assert point.output_elevation is None
    assert point.vertical is None
    assert point.output_northing == row.northing
    assert point.output_easting == row.easting

    raised = [
        w
        for w in point.warnings
        if w.code is WarningCode.VERTICAL_SHIFT_UNAVAILABLE
    ]
    assert len(raised) == 1


def test_an_elevation_less_point_passes_through_with_nothing_invented():
    source = pnezd.parse_lines(["CP-4,43.0,-84.5,,NO ELEVATION"])
    point = run(_geodetic_settings(), source=source).points[0]

    assert point.output_elevation is None
    assert point.vertical is None
    assert point.output_northing == source.rows[0].northing
    assert point.output_easting == source.rows[0].easting


# ==========================================================================
# The factors: input zone's where a zone exists, honestly absent where not.
# ==========================================================================


def test_zone_input_factors_are_the_input_zones_bitwise():
    """The ZONE_TO_GEODETIC precedent, held bitwise: a vertical-only job
    reading Michigan South coordinates carries exactly the grid scale factor
    a State-Plane-to-geodetic job computes at the same point, because both
    inverse-project through the input zone with no target zone anywhere."""
    vertical_only = run(_zone_settings(), source=_zone_source()).points[0]

    to_geodetic = run(
        _geodetic_settings(
            direction=Direction.ZONE_TO_GEODETIC,
            source_zone=MI_SOUTH,
            vertical_mode=VerticalMode.HORIZONTAL,
            source_vertical_datum=None,
            target_vertical_datum=None,
        ),
        source=_zone_source(),
    ).points[0]

    assert (
        vertical_only.factors.grid_scale_factor
        == to_geodetic.factors.grid_scale_factor
    )
    assert vertical_only.conversion.target_convergence == (
        to_geodetic.conversion.target_convergence
    )
    assert vertical_only.factors.combined_factor is not None


def test_geodetic_input_has_no_grid_scale_factor_and_no_combined_factor():
    """No zone anywhere, so no grid scale factor and no combined factor -
    None, never a fabricated 1.0 - while the elevation factor, which needs
    no zone, is still computed from the geoid model at the position."""
    result = run(_geodetic_settings(), source=_geodetic_source(43.0, -84.5))
    point = result.points[0]

    assert point.factors.grid_scale_factor is None
    assert point.factors.combined_factor is None
    assert point.factors.elevation_factor is not None
    assert point.factors.geoid_height is not None
    assert point.conversion.source_zone is None
    assert point.conversion.target_zone is None
    # The JobResult summaries honour the absence rather than crashing on it.
    assert result.grid_scale_factors == ()
    assert result.combined_factors == ()


# ==========================================================================
# The refusal matrix additions - every one named, every one teaching.
# ==========================================================================


def test_a_vertical_only_direction_without_the_vertical_mode_is_refused():
    for mode, datums in [
        (VerticalMode.HORIZONTAL, dict(
            source_vertical_datum=None, target_vertical_datum=None
        )),
        (VerticalMode.HORIZONTAL_AND_VERTICAL, {}),
    ]:
        settings = _geodetic_settings(vertical_mode=mode, **datums)
        with pytest.raises(ValueError) as caught:
            run(settings, source=_geodetic_source(43.0, -84.5))
        message = str(caught.value)
        assert "vertical only" in message
        assert "VerticalMode.VERTICAL" in message


def test_the_vertical_mode_without_the_vertical_only_direction_is_refused():
    """The other half of the mutual requirement: VerticalMode.VERTICAL on a
    job that also converts coordinates must refuse and name the mode that
    does both, not silently decide whether the coordinates move."""
    settings = _geodetic_settings(
        direction=Direction.GEODETIC_TO_ZONE, target_zone=MI_SOUTH
    )
    with pytest.raises(ValueError) as caught:
        run(settings, source=_geodetic_source(43.0, -84.5))
    message = str(caught.value)
    assert "vertical" in message
    assert "HORIZONTAL_AND_VERTICAL" in message


def test_a_supplied_target_zone_is_refused_naming_the_mode():
    settings = _zone_settings(target_zone=MI_SOUTH)
    with pytest.raises(ValueError) as caught:
        run(settings, source=_zone_source())
    message = str(caught.value)
    assert "no output horizontal" in message
    assert MI_SOUTH.name in message
    assert "target_zone=None" in message


def test_a_unit_mismatch_is_refused_teaching_the_mirror():
    """The export reproduces the input's columns; a different output unit
    would alter every value the export promises to mirror. Falsified at the
    build by deleting the refusal: this test fails (the job runs, its
    coordinate columns silently re-expressed) while the suite stays green."""
    settings = _zone_settings(output_unit=INTERNATIONAL_FEET)
    with pytest.raises(ValueError) as caught:
        run(settings, source=_zone_source())
    message = str(caught.value)
    assert "reproduce" in message
    assert "m" in message and "ift" in message
    assert "mirror" in message


def test_a_longitude_convention_on_zone_input_is_refused():
    """The zone-to-zone statement rule arriving at this direction: the file
    carries no longitudes and none are written, so a stated convention is an
    answer to a question the job never asks."""
    settings = _zone_settings(
        longitude_convention=LongitudeConvention.POSITIVE_WEST
    )
    with pytest.raises(ValueError) as caught:
        run(settings, source=_zone_source())
    message = str(caught.value)
    assert "longitude_convention=None" in message
    assert "positive west" in message


def test_a_missing_convention_on_geodetic_input_is_refused():
    settings = _geodetic_settings(longitude_convention=None)
    with pytest.raises(ValueError) as caught:
        run(settings, source=_geodetic_source(43.0, -84.5))
    assert "340 miles" in str(caught.value)


@pytest.mark.parametrize(
    "missing", ["source_vertical_datum", "target_vertical_datum"]
)
def test_a_missing_datum_is_refused_through_the_shared_path(missing):
    """The SAME raise the horizontal-and-vertical mode uses - one code path,
    so the two vertical modes cannot come to refuse differently. The message
    names this mode's own job ("A vertical job ...")."""
    settings = _geodetic_settings(**{missing: None})
    with pytest.raises(ValueError) as caught:
        run(settings, source=_geodetic_source(43.0, -84.5))
    message = str(caught.value)
    assert missing in message
    assert "A vertical job" in message
    assert "0.41 m" in message


# ==========================================================================
# The mirror pin: the export's cells are the formatted input, exactly.
# ==========================================================================


def _clean_rows(result):
    return exports.clean_pnezd_rows(result)


def test_the_zone_export_mirrors_the_import_except_the_elevation():
    """The clean export's N and E cells are the formatted INPUT values
    character for character - the writer formats through the standard
    formatters, so values are formatting-normalized, never re-computed - and
    the Z cell is the input plus exactly the shift the reading states."""
    source = _zone_source()
    result = run(_zone_settings(), source=source)
    row = source.rows[0]
    point = result.points[0]

    cells = _clean_rows(result)[0]
    assert cells[1] == fmt.coordinate(row.northing, METERS)
    assert cells[2] == fmt.coordinate(row.easting, METERS)
    # And those ARE the characters the input file carried, because the input
    # was already written at the unit's own 4 decimals.
    assert cells[1] == ZONE_NORTHING
    assert cells[2] == ZONE_EASTING

    # Z differs by exactly the shift: the cell is the formatter's rendering
    # of input + shift_m (metres in, metres out, so no unit conversion can
    # hide in the sum).
    assert cells[3] == fmt.coordinate(
        row.elevation + point.vertical.shift_m, METERS
    )
    assert cells[3] != fmt.coordinate(row.elevation, METERS)


def test_the_geodetic_export_mirrors_a_positive_west_import_as_written():
    """The discriminating case for a conversion-fed output cell: a positive
    west input file. The export's longitude cell must be the value AS THE
    FILE WROTE IT (84.5), not the signed pivot (-84.5) - the mirror keeps
    the input's own convention, and the job record names it."""
    source = _geodetic_source(43.0, 84.5)  # positive west, as the file wrote it
    result = run(
        _geodetic_settings(
            longitude_convention=LongitudeConvention.POSITIVE_WEST
        ),
        source=source,
    )
    point = result.points[0]

    # The pivot is signed internally - the grids were looked up at -84.5 -
    # while the output column mirrors the file.
    assert point.conversion.longitude == -84.5
    assert point.output_easting == 84.5

    cells = _clean_rows(result)[0]
    assert cells[1] == fmt.latitude(43.0)
    assert cells[2] == fmt.longitude(84.5)
    assert point.output_elevation == pytest.approx(
        ANCHOR_22.target_height_m, abs=SHIFT_TOLERANCE_M
    )


def test_a_refused_elevation_leaves_the_mirrored_row_with_a_blank_z():
    source = _geodetic_source(52.0, -84.5)
    result = run(_geodetic_settings(), source=source)
    cells = _clean_rows(result)[0]

    assert cells[1] == fmt.latitude(52.0)
    assert cells[2] == fmt.longitude(-84.5)
    assert cells[3] == fmt.NOT_AVAILABLE


# ==========================================================================
# The written archive: audit CSV and job record, end to end through files.
# ==========================================================================


def _written_job(tmp_path, settings_builder, line):
    input_path = tmp_path / "job.csv"
    input_path.write_text(line + "\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    settings = settings_builder(
        input_path=input_path, output_directory=out_dir
    )
    result = run(settings)
    written = exports.write_all(result)
    return result, written["archive"]


def _audit_rows(archive, result):
    from tests.conftest import member_text

    text = member_text(archive, "_full.csv")
    rows = list(csv.reader(text.splitlines()))
    return rows[0], rows[1:]


def test_the_geodetic_audit_csv_says_nothing_moved(tmp_path):
    """Target coordinate columns equal to source - the honest statement that
    nothing moved - under geodetic headings at both ends, with the Target
    zone cell reading the direction itself: 'vertical only'."""
    result, archive = _written_job(
        tmp_path,
        _geodetic_settings,
        "101,43.0,-84.5,200.000,VERT ONLY",
    )
    header, rows = _audit_rows(archive, result)
    audit = dict(zip(header, rows[0]))

    assert "Source latitude" in header
    assert "Target latitude" in header
    assert audit["Target zone"] == "vertical only"
    assert audit["Target latitude"] == audit["Source latitude"]
    assert (
        audit["Target longitude (as written)"]
        == audit["Source longitude (as in file)"]
    )
    # The vertical block is present, with real numbers on the anchor row.
    assert audit["Source vertical datum"] == "NGVD29"
    assert audit["Target vertical datum"] == "NAVD88"
    assert audit["Vertical shift (m)"] == fmt.vertical_quantity(
        result.points[0].vertical.shift_m, METERS
    )
    assert audit["Vertical shift (m)"] != fmt.NOT_AVAILABLE
    # No zone anywhere: the factor cells are honest absences.
    assert audit["Grid scale factor"] == fmt.NOT_AVAILABLE
    assert audit["Combined factor"] == fmt.NOT_AVAILABLE
    assert audit["Elevation factor"] != fmt.NOT_AVAILABLE


def test_the_zone_audit_csv_says_nothing_moved(tmp_path):
    result, archive = _written_job(
        tmp_path,
        _zone_settings,
        f"101,{ZONE_NORTHING},{ZONE_EASTING},200.000,VERT ONLY",
    )
    header, rows = _audit_rows(archive, result)
    audit = dict(zip(header, rows[0]))

    # Linear headings at both ends - the input was PNEZD and the export
    # mirrors it - and the cells identical across.
    assert "Source northing" in header
    assert "Target northing" in header
    assert audit["Target zone"] == "vertical only"
    assert audit["Target northing"] == audit["Source northing"]
    assert audit["Target easting"] == audit["Source easting"]
    assert audit["Source zone"] == MI_SOUTH.name
    # The input zone's factors, present and real.
    assert audit["Grid scale factor"] != fmt.NOT_AVAILABLE
    assert audit["Combined factor"] != fmt.NOT_AVAILABLE


def test_the_archive_is_named_for_the_vertical_conversion(tmp_path):
    result, archive = _written_job(
        tmp_path,
        _zone_settings,
        f"101,{ZONE_NORTHING},{ZONE_EASTING},200.000,VERT ONLY",
    )
    assert archive.name == "job_VERTICAL.zip"


def test_the_zone_job_record_discloses_the_mode(tmp_path):
    result, archive = _written_job(
        tmp_path,
        _zone_settings,
        f"101,{ZONE_NORTHING},{ZONE_EASTING},200.000,VERT ONLY",
    )
    text = build_report(result)

    assert "Conversion         vertical only" in text
    assert "The horizontal coordinates are NOT converted" in text
    # The V7 METHOD vertical block, untouched: the registry's own direction
    # statement, quoted - the record and the arithmetic cannot disagree.
    assert "VERTICAL DATUM TRANSFORMATION" in text
    assert "NAVD88 = NGVD29 + g" in text
    # The factors' provenance, per the input-zone split.
    assert "the INPUT zone's at" in text
    # A zone-input job carries no longitudes: no Longitude line at all.
    assert "\nLongitude " not in text
    # The clean export description states the mirror.
    assert "ONLY the elevation converted" in text


def test_the_geodetic_job_record_discloses_the_no_zone_split(tmp_path):
    result, archive = _written_job(
        tmp_path,
        _geodetic_settings,
        "101,43.0,-84.5,200.000,VERT ONLY",
    )
    text = build_report(result)

    assert "Conversion         vertical only" in text
    # The record wraps by hand at 78 columns, so each sentence is matched on
    # the line the record actually carries it on.
    assert "The input is geodetic positions (latitude / longitude). No State" in text
    assert "Plane coordinate system is involved in this job." in text
    assert "No State Plane zone is involved in this job" in text
    # A geodetic input reads longitudes, so the convention IS stated.
    assert "Longitude          negative west" in text
    # And the input block describes the geodetic layout, not PNEZD.
    assert "NOT PNEZD" in text


# ==========================================================================
# The vertical-only review gate's findings, pinned (DESIGN.md #46).
# ==========================================================================


def test_the_record_states_the_true_reason_no_combined_factor_exists(tmp_path):
    """The gate's MEDIUM 1: a geodetic-input vertical-only job whose every
    point carried a usable elevation printed "no point carried a usable
    elevation" under the combined-factor summary - a false statement in a
    sealed record, contradicted by the ELEVATIONS section beside it (the
    #42-finding-3 class recurring; the implication broke when
    grid_scale_factor became optional). The sentence now keys on WHY the
    tuple is empty. Falsified by reverting the guard: the first two
    assertions fail."""
    result, _archive = _written_job(
        tmp_path, _geodetic_settings, "601,43.0,-84.5,200.000,HAS ELEV"
    )
    text = build_report(result)

    assert "no zone is involved" in text
    assert "no point carried a usable elevation" not in text

    # The old spelling is still the truth where the elevation IS the cause: a
    # ZONE-input vertical-only job has a real zone and real scale factors, so
    # an empty combined tuple there means what it always meant. (A geodetic
    # no-elevation job carries BOTH causes, and the no-zone sentence wins -
    # it is the one that is true of every point.) The guard distinguishes,
    # it does not replace.
    second_dir = tmp_path / "b"
    second_dir.mkdir()
    no_elev_result, _ = _written_job(
        second_dir, _zone_settings, "701,166625.1664,3989128.8661,,BLANK"
    )
    assert "no point carried a usable elevation" in build_report(no_elev_result)


def test_a_metre_northing_on_a_rounding_boundary_writes_and_mirrors(tmp_path):
    """The gate's MEDIUM 2: a metre PNEZD northing whose 5th decimal is
    exactly 5 (166625.16645 - the gate's own reproduction) tripped the
    round-trip verifier past its half-place tolerance and refused the WHOLE
    archive, in this mode only, at an 83% rate in Michigan's worst
    metre-northing band. The verifier now compares the re-read value exactly
    against the writer's own rendering, which is strictly tighter for every
    computed path and correct for the mirrored one. Falsified by restoring
    the tolerance-against-raw comparison: this test fails with the gate's
    own WriteError."""
    from tests.conftest import member_text

    result, archive = _written_job(
        tmp_path,
        _zone_settings,
        "801,166625.16645,3989128.8661,200.000,BOUNDARY",
    )
    text = member_text(archive, "job_VERTICAL.csv")
    row = text.strip().splitlines()[0].split(",")
    # The rendered mirror: the writer's 4-decimal rendering of the input
    # (round-half-even of ...16645 at 4 places).
    assert row[1] in ("166625.1664", "166625.1665")
    # And the Z is the shifted height, so the job genuinely ran.
    assert row[3] != "200.0000"
