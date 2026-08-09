"""WP-V7: the disclosure of docs/PLAN-vertical-datums.md section 5.

A vertical job moves the Z column by about 0.46 ft across Michigan (DESIGN.md
#41), and before this package NO output said so. The #41 gate made that a hard
sequencing constraint: no build in which vertical mode is reachable may fail to
state the datum, the shift and NGS's caveat. What is tested here is that every
surface now states them - and, just as load-bearing, that a HORIZONTAL job's
three outputs are untouched to the byte's worth of content.

Truth sources for the hand-derived values below:

* 43.0 N / -84.5 W and 43.05 N / -86.2 W are EXACT nodes of the 0.05-degree
  VERTCON grids, so interpolation is not involved: the cells' stored values
  settle every figure (DESIGN.md #36 used the same fact to correct plan
  section 2.8). Transcribed from the committed grids via
  ``vertcon.default_grids().reading_at``:

      43.0, -84.5    shift -0.14019644260406494  sigma 0.0006554240244440734
      43.05, -86.2   shift -0.14352931082248527  sigma 0.36559906601907743

  Both agree with the frozen NCAT lattice (tests/fixtures/vertcon_anchors.py:
  -0.140 and -0.144/0.366 at NCAT's 0.001 m print) and with plan section 2.7's
  direct grid scan (max sigma 0.365599 m; anchor-22's sigma 0.00065542 m).

* 42.475 N / -83.125 W is the frozen negative-sigma position of DESIGN.md #36:
  the .err grid interpolates to -0.009651645734265912 m there, which cannot be
  a one-sigma, so ``sigma_m`` is None and only N/A may be printed. The .trn
  shift there is -0.13599119428545237 m and is valid and unaffected.

Formatted through ``formatting.vertical_metres`` (4 decimal places):

      anchor-22   shift "-0.1402"   sigma "0.0007"
      max-sigma   shift "-0.1435"   sigma "0.3656"
      neg-sigma   shift "-0.1360"   sigma  N/A
      mean sigma over {anchor-22, max-sigma}:
          (0.0006554240244440734 + 0.36559906601907743) / 2
          = 0.18312724502176075 -> "0.1831"

      anchor-22 target height: 200.000 - 0.14019644260406494
          = 199.85980355739594 -> "199.8598" (METERS, 4 dp)
"""

from __future__ import annotations

import csv
import io
import os
import zipfile

# MUST precede any Qt import (docs/method/TOOLING.md): results_model imports
# PySide6 at module level and the platform plugin is chosen at import time.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402

from michspc.fileio import exports, formatting as fmt, pnezd, report, vertcon  # noqa: E402
from michspc.gui import results_model as rm  # noqa: E402
from michspc.job import (  # noqa: E402
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc.convert import WarningCode  # noqa: E402
from michspc.spc.units import INTERNATIONAL_FEET, METERS  # noqa: E402
from michspc.spc.vertical import NAVD88, NGVD29, require_vertical_pair  # noqa: E402
from michspc.spc.zones import MI_CENTRAL, MI_SOUTH  # noqa: E402

# The three disclosure positions, hand-derived in the module docstring.
ANCHOR_22 = (43.0, -84.5)
MAX_SIGMA = (43.05, -86.2)
NEG_SIGMA = (42.475, -83.125)

# The formatted figures those positions must produce, derived above.
ANCHOR_22_SHIFT = "-0.1402"
ANCHOR_22_SIGMA = "0.0007"
ANCHOR_22_TARGET_HEIGHT = "199.8598"
MAX_SIGMA_SHIFT = "-0.1435"
MAX_SIGMA_SIGMA = "0.3656"
NEG_SIGMA_SHIFT = "-0.1360"
MEAN_SIGMA = "0.1831"


def _normalized(text: str) -> str:
    """Whitespace collapsed, so a registry sentence wrapped by the record can
    be checked as a QUOTE - same words, same order - rather than re-drafted."""
    return " ".join(text.split())


def _vertical_file_job(tmp_path, lines=None, **overrides):
    """A written geodetic file through ``run``, vertical NGVD29 -> NAVD88.

    A real file and a real output folder, because the job record refuses a
    pathless job - and because the disclosure this module tests is exactly
    what the WRITTEN deliverable says.
    """
    if lines is None:
        lines = [
            f"101,{ANCHOR_22[0]},{ANCHOR_22[1]},200.000,ANCHOR22",
            f"102,{MAX_SIGMA[0]},{MAX_SIGMA[1]},200.000,MAXSIGMA",
            f"103,{NEG_SIGMA[0]},{NEG_SIGMA[1]},200.000,NEGSIGMA",
            "104,42.9634,-85.6681,,NOELEV",
        ]
    source = tmp_path / "vjob.csv"
    source.write_text("\n".join(lines) + "\n", encoding="ascii")
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    base = dict(
        input_path=source,
        output_directory=out,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    base.update(overrides)
    return run(JobSettings(**base))


def _horizontal_file_job(tmp_path, **overrides):
    base = dict(
        vertical_mode=VerticalMode.HORIZONTAL,
        source_vertical_datum=None,
        target_vertical_datum=None,
    )
    base.update(overrides)
    return _vertical_file_job(tmp_path, **base)


def _typed_vertical_job(latitude=ANCHOR_22[0], longitude=ANCHOR_22[1], **overrides):
    """A single typed geodetic point through the same gate the tab uses."""
    parsed = pnezd.parse_typed_point(
        str(latitude),
        str(longitude),
        overrides.pop("elevation", "200.000"),
        source=pnezd.TYPED_POINT_SOURCE_GEODETIC,
    )
    base = dict(
        input_path=None,
        output_directory=None,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    base.update(overrides)
    return run(JobSettings(**base), source=parsed)


def _member_text(archive_path, suffix):
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            if name.endswith(suffix):
                return archive.read(name).decode("utf-8")
    raise AssertionError(f"no member ending {suffix!r} in {archive_path}")


def _labels(section):
    return tuple(value.label for value in section.values)


def _by_label(section):
    return {value.label: value.text for value in section.values}


MODELED = require_vertical_pair(NGVD29, NAVD88)


# ==========================================================================
# The warning: a sigma-less modeled reading is SAID, not merely recorded.
# ==========================================================================


def test_a_negative_sigma_point_raises_the_sigma_unavailable_warning(tmp_path):
    """DESIGN.md #41's note to WP-V7: the disclosure layer must not assume a
    warning exists, so this one makes it exist. Position, non-physicality, the
    #36 rule that the shift is valid and unaffected, and the raw figure's
    accessor - all in the one message every surface inherits."""
    result = _vertical_file_job(tmp_path)
    point = next(p for p in result.points if p.point_id == "103")

    codes = [w.code for w in point.warnings]
    assert WarningCode.VERTICAL_SIGMA_UNAVAILABLE in codes

    message = next(
        w.message
        for w in point.warnings
        if w.code is WarningCode.VERTICAL_SIGMA_UNAVAILABLE
    )
    # The position, to the same precision every other warning names one at.
    assert "42.475000" in message and "-83.125000" in message
    # Not physical as an uncertainty - the reason, not just the absence.
    assert "not physical" in message
    # The #36 rule, in capitals, so a caller cannot conclude the elevation is
    # bad: the shift comes from the other grid.
    assert "THE SHIFT ITSELF IS VALID AND UNAFFECTED" in message
    # The raw figure and its accessor stay OFF every output surface: they
    # live on the reading's reason field for a caller who asks the code
    # (WP-V7 review gate, MEDIUM 1 - the dedicated pin is
    # test_the_sigma_warning_prints_no_raw_figure_and_no_api_path).
    assert "modeled_error_raw_m" not in message

    # And the point's elevation really was converted: sigma None, shift valid.
    assert point.vertical.sigma_m is None
    assert point.output_elevation is not None


def test_an_identity_reading_raises_no_sigma_warning(tmp_path):
    """An identity's missing sigma is a statement the record's METHOD text
    makes ("no shift is applied"), not a warning: no model ran, so there is
    nothing unusual to flag. Warning about it would teach the user to ignore
    the warning field."""
    result = _vertical_file_job(
        tmp_path,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
    )
    point = next(p for p in result.points if p.point_id == "103")

    assert point.vertical is not None
    assert point.vertical.sigma_m is None  # no model ran
    assert point.vertical.transformation.is_identity
    codes = [w.code for w in point.warnings]
    assert WarningCode.VERTICAL_SIGMA_UNAVAILABLE not in codes


def test_a_point_with_a_physical_sigma_raises_no_sigma_warning(tmp_path):
    """Anti-vacuousness for the two above: the warning is about the negative
    region, not about vertical mode."""
    result = _vertical_file_job(tmp_path)
    point = next(p for p in result.points if p.point_id == "101")

    assert point.vertical.sigma_m is not None
    assert point.warnings == ()


# ==========================================================================
# The job record.
# ==========================================================================


def test_a_vertical_record_names_both_datums_in_input_and_output(tmp_path):
    """Plan section 5.2: INPUT names the source datum, OUTPUT names the target
    datum and says the clean export's Z column is expressed in it. Full names,
    not just codes - the code is a token a reader six months later may not
    place."""
    text = report.build_report(_vertical_file_job(tmp_path))

    assert (
        "Vertical datum     National Geodetic Vertical Datum of 1929 (NGVD29)"
        in text
    )
    assert (
        "Vertical datum     North American Vertical Datum of 1988 (NAVD88)"
        in text
    )
    normalized = _normalized(text)
    assert (
        "Every elevation this job writes - including the clean export's "
        "Z column - is expressed in this datum." in normalized
    )


def test_a_vertical_record_quotes_the_direction_statement(tmp_path):
    """The record quotes ``direction_statement`` - the sentence derived from
    the same ``sign`` the computation multiplies by - so the record and the
    arithmetic cannot disagree about which way the shift went. Checked as a
    QUOTE with whitespace normalized (the record wraps it), never re-drafted."""
    text = report.build_report(_vertical_file_job(tmp_path))

    assert _normalized(MODELED.direction_statement) in _normalized(text)
    # Anti-vacuousness: the statement really does state the arithmetic.
    assert "NAVD88 = NGVD29 + g" in MODELED.direction_statement


def test_a_vertical_record_carries_both_grid_files_and_both_digests(tmp_path):
    """Both filenames and both SHA-256s: the shift and its uncertainty come
    from two different files, and a record naming one would certify half of
    what was read (plan section 5.2)."""
    text = report.build_report(_vertical_file_job(tmp_path))

    assert vertcon.VERTCON3_TRN_FILENAME in text
    assert vertcon.VERTCON3_TRN_SHA256 in text
    assert vertcon.VERTCON3_ERR_FILENAME in text
    assert vertcon.VERTCON3_ERR_SHA256 in text
    # And the model with its release, exactly as the registry names them.
    assert "VERTCON 3.0 release 20190601" in text


def test_a_vertical_record_quotes_the_uncertainty_citation_and_caveat(tmp_path):
    """The registry's own sentences, quoted: the citation that carries the
    0.3656 m / 255% disclosure, and NGS's supersession caveat with the NGVD 29
    distortion figure. Plan section 2.8 is the proof the caveat is not
    boilerplate - one such place is in Michigan."""
    text = _normalized(report.build_report(_vertical_file_job(tmp_path)))

    assert _normalized(MODELED.uncertainty_citation) in text
    assert _normalized(MODELED.caveat) in text
    # Anti-vacuousness: the quoted sentences carry the load-bearing facts.
    assert "255% of the shift" in _normalized(MODELED.uncertainty_citation)
    assert "MODELED, not measured" in MODELED.caveat
    assert "20 cm" in MODELED.caveat


def test_a_vertical_record_discloses_the_half_cell_steps(tmp_path):
    """DESIGN.md #38's disclosure decision, owned by WP-V7: the model is
    interpolated the way NOAA's own software interpolates it, which steps at
    half-cell lines - worst about 76 mm in Michigan in the shift - and NCAT
    reproduces the same steps. A job whose points straddle such a line shows
    the step with nothing else to explain it, so the record explains it."""
    text = _normalized(report.build_report(_vertical_file_job(tmp_path)))

    assert "NOAA's own published VERTCON software" in text
    assert "half-cell lines" in text
    assert "76 mm" in text
    assert "NGS NCAT reproduces the same steps" in text


def test_the_sigma_summary_is_min_max_mean_over_points_with_a_sigma(tmp_path):
    """The record keeps a summary in the ``_factor_summary`` shape; the CSV
    keeps the per-point column (plan section 5.1). Hand-derived in the module
    docstring: min 0.0007 (anchor-22), max 0.3656 (max-sigma), mean 0.1831 -
    over the two points whose sigma EXISTS, because the negative-region point
    has none to average and averaging a stand-in would fabricate one."""
    result = _vertical_file_job(tmp_path)
    text = report.build_report(result)

    expected = (
        "  Shift one-sigma uncertainty (m)\n"
        f"    minimum  {ANCHOR_22_SIGMA}\n"
        f"    maximum  {MAX_SIGMA_SIGMA}\n"
        f"    mean     {MEAN_SIGMA}"
    )
    assert expected in text

    # UI honesty: the same strings the formatter produces from the result's
    # own readings - the literal above is the hand-derivation, this is the
    # no-second-account check.
    sigmas = [
        p.vertical.sigma_m
        for p in result.points
        if p.vertical is not None and p.vertical.sigma_m is not None
    ]
    assert len(sigmas) == 2
    assert fmt.vertical_metres(min(sigmas)) == ANCHOR_22_SIGMA
    assert fmt.vertical_metres(max(sigmas)) == MAX_SIGMA_SIGMA
    assert fmt.vertical_metres(sum(sigmas) / 2) == MEAN_SIGMA


def test_the_record_names_the_point_whose_sigma_exceeds_its_shift(tmp_path):
    """Plan section 5.2, proved a real Michigan case by section 2.8: at the
    max-sigma anchor the uncertainty (0.3656 m) is 255% of the shift
    (-0.1435 m). The point is NAMED, not buried in the summary."""
    text = report.build_report(_vertical_file_job(tmp_path))

    heading = "  Points whose shift uncertainty EXCEEDS the shift itself (1):"
    assert heading in text
    block = text.split(heading, 1)[1]
    # The max-sigma point is named in the block...
    assert "102" in block.split("\n\n")[0]
    # ...and the well-behaved anchor is not (0.0007 < 0.1402).
    assert "101" not in block.split("\n\n")[0]


def test_the_record_names_the_negative_sigma_point_never_a_number(tmp_path):
    """The #36 disclosure: no uncertainty could be stated - never a number -
    and the shift beside it is valid and unaffected. The point is counted and
    named, and the WARNINGS section carries the new heading."""
    text = report.build_report(_vertical_file_job(tmp_path))

    heading = "  Points where no uncertainty could be stated (1):"
    assert heading in text
    block = text.split(heading, 1)[1]
    assert "103" in block.split("\n\n")[0]

    normalized = _normalized(text)
    assert (
        "no uncertainty could be stated - the Shift sigma cell reads "
        "'N/A', never a number" in normalized
    )
    assert "THE SHIFT ITSELF IS VALID AND UNAFFECTED" in normalized
    # The warning heading in the WARNINGS section - the record does not rely
    # on the raw code text fallback for a warning this build introduces.
    assert "SHIFT APPLIED, BUT NO UNCERTAINTY COULD BE STATED FOR IT" in text


def test_the_record_states_how_many_points_were_shifted_and_that_its_modeled(
    tmp_path,
):
    """The count, the direction, and MODELED-not-measured, in the ELEVATIONS
    section where a reader looking for the Z column's provenance will look."""
    text = _normalized(report.build_report(_vertical_file_job(tmp_path)))

    assert (
        "3 of 4 points had their elevation shifted from NGVD29 to NAVD88. "
        "The shift is MODELED, not measured (see METHOD)" in text
    )


def test_an_identity_record_says_no_shift_is_applied_and_names_no_grid(tmp_path):
    """An identity is an explicit record whose direction_statement reads "no
    shift is applied" - stated, not fallen out of an untested branch
    (spc/vertical's own contract). No grid was read, so no grid may be named:
    a digest in an identity record would certify files the job never opened."""
    identity = require_vertical_pair(NAVD88, NAVD88)
    text = report.build_report(
        _vertical_file_job(
            tmp_path,
            source_vertical_datum=NAVD88,
            target_vertical_datum=NAVD88,
        )
    )

    assert _normalized(identity.direction_statement) in _normalized(text)
    assert "no shift is applied" in identity.direction_statement
    assert vertcon.VERTCON3_TRN_FILENAME not in text
    assert vertcon.VERTCON3_ERR_SHA256 not in text
    # No model ran: the sigma summary would be a summary of nothing.
    assert "Shift one-sigma uncertainty (m)" not in text
    assert _normalized(
        "both vertical datums are NAVD88, so no shift was applied"
    ) in _normalized(text)


def test_the_record_states_the_factor_height_for_a_navd88_source_job(tmp_path):
    """DESIGN.md #41's either-endpoint rule: in a NAVD88 -> NGVD29 job with a
    NAVD 88 geoid model the factors are computed from the SOURCE height, and
    the record must SAY so - it is the one configuration where the factors do
    not use the height the Z column carries."""
    text = report.build_report(
        _vertical_file_job(
            tmp_path,
            source_vertical_datum=NAVD88,
            target_vertical_datum=NGVD29,
        )
    )

    normalized = _normalized(text)
    assert "Factor height" in text
    assert (
        "The elevation and combined factors were computed from the "
        "SOURCE-datum (NAVD88) height, not from the shifted height the "
        "Z column carries." in normalized
    )
    # Anti-vacuousness: the forward job, whose factors DO use the shifted
    # height, must not carry the paragraph.
    forward = report.build_report(_vertical_file_job(tmp_path))
    assert "Factor height" not in forward


def test_a_horizontal_record_carries_none_of_the_vertical_disclosure(tmp_path):
    """The hard constraint: a horizontal job's record is what it always was.
    Every vertical marker this package adds is absent - this is the regression
    floor beneath the byte-identity check the gate will run."""
    text = report.build_report(_horizontal_file_job(tmp_path))

    assert "Vertical datum" not in text
    assert "VERTICAL DATUM TRANSFORMATION" not in text
    assert vertcon.VERTCON3_TRN_SHA256 not in text
    assert vertcon.VERTCON3_ERR_FILENAME not in text
    assert "half-cell" not in text
    assert "Factor height" not in text
    assert "Shift one-sigma uncertainty" not in text
    assert "shifted from" not in text


# ==========================================================================
# The audit CSV.
# ==========================================================================

# The vertical header for a geodetic-to-zone job, transcribed from plan
# section 5.2 plus the WP-V7 decisions: the vertical block directly after
# Elevation (the target height beside what derived it), Geoid model directly
# before the geoid height it governs (DESIGN.md #40 LOW 5).
VERTICAL_GEODETIC_HEADER = [
    "Point",
    "Source zone",
    "Source latitude",
    "Source longitude (as in file)",
    "Target zone",
    "Target northing",
    "Target easting",
    "Elevation",
    "Source vertical datum",
    "Target vertical datum",
    "Source elevation (m)",
    "Vertical shift (m)",
    "Shift sigma (m)",
    "Units",
    "Latitude",
    "Longitude (neg west)",
    "Geoid model",
    "Geoid height (m)",
    "Ellipsoid height (m)",
    "Source grid scale factor",
    "Source convergence",
    "Grid scale factor",
    "Convergence",
    "Elevation factor",
    "Combined factor",
    "Combined factor (ppm)",
    "Warnings",
    "Description",
]


def test_the_vertical_audit_header_is_exact_and_reaches_the_written_file(
    tmp_path,
):
    result = _vertical_file_job(tmp_path)

    assert exports.audit_columns(result) == VERTICAL_GEODETIC_HEADER
    # Every data row is as wide as the header.
    rows = exports.audit_rows(result)
    assert rows[0] == VERTICAL_GEODETIC_HEADER
    for row in rows[1:]:
        assert len(row) == len(VERTICAL_GEODETIC_HEADER)

    # And the header the WRITTEN file carries is the same one.
    written = exports.write_all(result)
    text = _member_text(written["archive"], "_full.csv")
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == VERTICAL_GEODETIC_HEADER


def test_the_vertical_audit_row_at_anchor_22_is_hand_derived(tmp_path):
    """Every new cell at the exact-node anchor, against the figures derived in
    the module docstring. The Elevation column keeps the TARGET height - it is
    what the clean export carries - and the Source elevation column holds the
    pre-shift height, so the file answers 'how was this Z derived'."""
    result = _vertical_file_job(tmp_path)
    header, *rows = exports.audit_rows(result)
    row = next(r for r in rows if r[0] == "101")

    def cell(name):
        return row[header.index(name)]

    assert cell("Source vertical datum") == "NGVD29"
    assert cell("Target vertical datum") == "NAVD88"
    # 200.000 m as supplied, in the input unit (METERS, 4 dp).
    assert cell("Source elevation (m)") == "200.0000"
    # Hand-derived: -0.14019644260406494 -> "-0.1402".
    assert cell("Vertical shift (m)") == ANCHOR_22_SHIFT
    # Hand-derived: 0.0006554240244440734 -> "0.0007".
    assert cell("Shift sigma (m)") == ANCHOR_22_SIGMA
    # Hand-derived: 200.000 - 0.14019644260406494 = 199.85980... -> "199.8598".
    assert cell("Elevation") == ANCHOR_22_TARGET_HEIGHT
    assert cell("Geoid model") == "GEOID18"


def test_the_sigma_cell_at_the_negative_region_reads_na_never_a_number(
    tmp_path,
):
    """DESIGN.md #36's standing convention at the CSV: where no uncertainty
    can be stated the cell reads N/A - NEVER the raw model output, which is
    negative and is not an uncertainty. The shift cell beside it is a real
    number, because the shift is valid and unaffected."""
    result = _vertical_file_job(tmp_path)
    header, *rows = exports.audit_rows(result)
    row = next(r for r in rows if r[0] == "103")

    assert row[header.index("Shift sigma (m)")] == fmt.NOT_AVAILABLE
    # The shift is a number - hand-derived -0.13599119428545237 -> "-0.1360" -
    # and parses as one.
    shift_cell = row[header.index("Vertical shift (m)")]
    assert shift_cell == NEG_SIGMA_SHIFT
    assert float(shift_cell) < 0.0
    # The warnings cell carries the new code, so the CSV inherits the reason.
    assert "vertical-sigma-unavailable" in row[header.index("Warnings")]


def test_an_identity_audit_row_reads_zero_shift_and_na_sigma(tmp_path):
    """An identity's shift is a REAL zero - printed as one - and its sigma is
    N/A because no model ran, not 0.0: a fabricated zero uncertainty is the
    same class of invented number as a fabricated zero shift."""
    result = _vertical_file_job(
        tmp_path,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
    )
    header, *rows = exports.audit_rows(result)
    row = next(r for r in rows if r[0] == "101")

    assert row[header.index("Vertical shift (m)")] == "0.0000"
    assert row[header.index("Shift sigma (m)")] == fmt.NOT_AVAILABLE
    assert row[header.index("Source vertical datum")] == "NAVD88"
    assert row[header.index("Target vertical datum")] == "NAVD88"


def test_a_point_with_no_elevation_reads_na_in_every_vertical_cell(tmp_path):
    """No height, no shift, no sigma - and the source elevation cell says N/A
    exactly as the Elevation cell always has for a blank Z field."""
    result = _vertical_file_job(tmp_path)
    header, *rows = exports.audit_rows(result)
    row = next(r for r in rows if r[0] == "104")

    for name in ("Source elevation (m)", "Vertical shift (m)", "Shift sigma (m)"):
        assert row[header.index(name)] == fmt.NOT_AVAILABLE
    # The datums are the JOB's statement and stand even on this point.
    assert row[header.index("Source vertical datum")] == "NGVD29"


def test_a_horizontal_audit_csv_gains_no_columns(tmp_path):
    """DESIGN.md #40 LOW 5 is closed for the mode where two answers differ;
    the horizontal CSV keeps its 0.1.0 layout and relies on the record inside
    the same ZIP to name the geoid model (#17) - the standing status quo,
    kept deliberately."""
    result = _horizontal_file_job(tmp_path)

    columns = exports.audit_columns(result)
    for name in VERTICAL_GEODETIC_HEADER[8:13] + ["Geoid model"]:
        assert name not in columns

    # And the zone-to-zone horizontal header is still AUDIT_COLUMNS itself -
    # the exact regression floor the existing suite pins.
    source = tmp_path / "grid.csv"
    source.write_text("1,780000.000,13123359.580,800.00,IP\n", encoding="ascii")
    z2z = run(
        JobSettings(
            input_path=source,
            output_directory=tmp_path / "out",
            direction=Direction.ZONE_TO_ZONE,
            source_zone=MI_SOUTH,
            target_zone=MI_CENTRAL,
            input_unit=INTERNATIONAL_FEET,
            output_unit=INTERNATIONAL_FEET,
            longitude_convention=None,
        )
    )
    assert exports.audit_columns(z2z) == exports.AUDIT_COLUMNS


# ==========================================================================
# The clean PNEZD export: five fields in every vertical mode (plan section 6).
# ==========================================================================


def test_the_clean_export_has_exactly_five_fields_in_a_vertical_job(tmp_path):
    """Plan section 6's named pin. Sigma, shift and datum never reach the
    CAD-bound file: a sixth column either fails the import or silently shifts
    every field left (section 5.1), and the ZIP travels with the record that
    names the datum. The Z is the TARGET-datum height."""
    result = _vertical_file_job(tmp_path)

    # At the row level - so a seeded sixth field fails THIS assertion, before
    # the round-trip gate refuses the write.
    for row in exports.clean_pnezd_rows(result):
        assert len(row) == 5

    written = exports.write_all(result)
    text = _member_text(written["archive"], "S.csv")
    parsed = list(csv.reader(io.StringIO(text)))
    # Four points, no header row.
    assert len(parsed) == 4
    assert parsed[0][0] == "101"
    for row in parsed:
        assert len(row) == 5

    # The Z column is the shifted, target-datum height - hand-derived
    # 199.8598 at anchor-22 - and nothing vertical leaks in anywhere.
    assert parsed[0][3] == ANCHOR_22_TARGET_HEIGHT
    assert "NGVD29" not in text and "NAVD88" not in text
    assert ANCHOR_22_SIGMA not in [cell for row in parsed for cell in row]


# ==========================================================================
# The single point panel.
# ==========================================================================


def test_the_vertical_rows_join_the_owners_layout():
    """The geodetic-to-zone layout of amendment #26, with WP-V7's additions in
    place: the INPUT elevation labelled with the source datum, the OUTPUT one
    with the target datum, and the shift and sigma rows directly under the
    elevation they explain, before the factors."""
    source, target = rm.single_point_sections(_typed_vertical_job())

    assert _labels(source) == (
        "Latitude",
        "Latitude (DMS)",
        "Longitude",
        "Longitude (DMS)",
        "Elevation (NGVD29)",
        "Units",
    )
    assert _labels(target) == (
        "Zone",
        "Units",
        "Northing",
        "Easting",
        "Elevation (NAVD88)",
        "Vertical shift NGVD29 -> NAVD88 (m)",
        "Shift sigma (m)",
        # No "Vertical method" caveat row: it stood here between the WP-V7
        # gate and the owner's removal instruction (DESIGN.md #45).
        "Grid scale factor",
        "Convergence",
        "Geoid height (m)",
        "Ellipsoid height (m)",
        "Elevation factor",
        "Combined factor",
    )


@pytest.mark.parametrize(
    "direction",
    [Direction.ZONE_TO_ZONE, Direction.ZONE_TO_GEODETIC],
)
def test_the_vertical_rows_appear_in_the_grid_input_directions_too(direction):
    """The shift row follows the OUTPUT elevation in every direction - a
    layout rule that behaved differently in one direction would not be a
    layout rule (#26's own reasoning). Vertical mode has no GUI today
    (WP-V8), so these layouts are pinned before any control can reach them."""
    parsed = pnezd.parse_typed_point(
        "780000.000",
        "13123359.580",
        "200.000",
        source=pnezd.TYPED_POINT_SOURCE_GRID,
    )
    settings = JobSettings(
        input_path=None,
        output_directory=None,
        direction=direction,
        source_zone=MI_SOUTH,
        target_zone=MI_CENTRAL if direction is Direction.ZONE_TO_ZONE else None,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=(
            None
            if direction is Direction.ZONE_TO_ZONE
            else LongitudeConvention.NEGATIVE_WEST
        ),
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    result = run(settings, source=parsed)
    source, target = rm.single_point_sections(result)

    input_labels = _labels(source)
    output_labels = _labels(target)
    assert "Elevation (NGVD29)" in input_labels
    assert "Elevation (NAVD88)" in output_labels
    # Directly under the elevation they explain.
    at = output_labels.index("Elevation (NAVD88)")
    assert output_labels[at + 1] == "Vertical shift NGVD29 -> NAVD88 (m)"
    assert output_labels[at + 2] == "Shift sigma (m)"


def test_the_vertical_row_values_are_the_formatters_output():
    """UI honesty: the panel's strings are ``fmt.vertical_metres`` applied to
    the reading's own numbers - the same function the audit CSV calls - plus
    the hand-derived figures at the exact-node anchor."""
    result = _typed_vertical_job()
    reading = result.points[0].vertical
    _, target = rm.single_point_sections(result)
    values = _by_label(target)

    assert values["Vertical shift NGVD29 -> NAVD88 (m)"] == fmt.vertical_metres(
        reading.shift_m
    )
    assert values["Shift sigma (m)"] == fmt.vertical_metres(reading.sigma_m)
    # Hand-derived at the node (module docstring).
    assert values["Vertical shift NGVD29 -> NAVD88 (m)"] == ANCHOR_22_SHIFT
    assert values["Shift sigma (m)"] == ANCHOR_22_SIGMA
    # And the two elevations are two different heights on two surfaces.
    source_values = _by_label(rm.single_point_sections(result)[0])
    assert source_values["Elevation (NGVD29)"] == "200.0000"
    assert values["Elevation (NAVD88)"] == ANCHOR_22_TARGET_HEIGHT


def test_the_sigma_row_reads_na_where_no_uncertainty_can_be_stated():
    """The row's value is N/A - never the raw negative figure - and the REASON
    reaches the warnings field through the new warning, so the panel's N/A is
    explained on the same screen."""
    result = _typed_vertical_job(*NEG_SIGMA)
    _, target = rm.single_point_sections(result)
    values = _by_label(target)

    assert values["Shift sigma (m)"] == fmt.NOT_AVAILABLE
    # The shift row is a real number beside it.
    assert values["Vertical shift NGVD29 -> NAVD88 (m)"] == NEG_SIGMA_SHIFT

    warnings_text = rm.single_point_warnings(result)
    assert "THE SHIFT ITSELF IS VALID AND UNAFFECTED" in warnings_text
    # No raw figure and no API path on screen (WP-V7 review gate, MEDIUM 1).
    assert "modeled_error_raw_m" not in warnings_text


def test_the_sigma_row_is_in_the_clipboard_text():
    """Plan section 6's pin: sigma is a NUMBER, so unlike warnings (#30) it
    belongs in Copy all. The clipboard serialises the sections, so the row's
    label and value both survive."""
    sections = rm.single_point_sections(_typed_vertical_job())
    text = rm.single_point_clipboard_text(sections)

    assert f"Shift sigma (m)\t{ANCHOR_22_SIGMA}" in text
    assert f"Vertical shift NGVD29 -> NAVD88 (m)\t{ANCHOR_22_SHIFT}" in text
    assert f"Elevation (NAVD88)\t{ANCHOR_22_TARGET_HEIGHT}" in text


def test_a_horizontal_single_point_carries_no_vertical_rows():
    """The other half of the gate: a horizontal job's panel is unchanged to
    the label. The existing layout tests pin the exact tuples; this is the
    explicit absence, so a leak fails a test that NAMES the leak."""
    result = _typed_vertical_job(
        vertical_mode=VerticalMode.HORIZONTAL,
        source_vertical_datum=None,
        target_vertical_datum=None,
    )
    source, target = rm.single_point_sections(result)

    for labels in (_labels(source), _labels(target)):
        assert "Shift sigma (m)" not in labels
        for label in labels:
            assert "Vertical shift" not in label
            assert "(NGVD29)" not in label and "(NAVD88)" not in label
    # The plain labels are still there.
    assert "Elevation" in _labels(source)
    assert "Elevation" in _labels(target)


# ==========================================================================
# The WP-V7 review gate's findings, each pinned (DESIGN.md #42).
# ==========================================================================


def test_the_vertical_method_row_stays_removed():
    """The owner removed the caveat row (DESIGN.md #45), reversing the WP-V7
    gate's on-screen-caveat resolution under his #33 ruling. This pins the
    REMOVAL: a row that quietly returned would be a decision nobody made.
    The caveat itself still reaches every written job through the record's
    METHOD block, which test_a_vertical_record_quotes... continue to hold."""
    sections = rm.single_point_sections(_typed_vertical_job())
    for section in sections:
        assert rm.VERTICAL_METHOD_LABEL not in [v.label for v in section.values]
    assert rm.VERTICAL_METHOD_LABEL not in rm.single_point_clipboard_text(sections)


def test_the_sigma_warning_prints_no_raw_figure_and_no_api_path(tmp_path):
    """The gate's MEDIUM 1: the warning reached the record and the screen
    carrying the raw error-model output at 18 significant digits and a Python
    attribute path - publishing the figure #36 deliberately kept behind a
    code accessor, in a document a surveyor compares against NCAT's +0.011.
    The raw figure and the accessor stay on the reading's reason field, out
    of every output. Falsified by restoring the old message: this fails."""
    result = _vertical_file_job(
        tmp_path,
        lines=[f"301,{NEG_SIGMA[0]},{NEG_SIGMA[1]},200.000,NEGSIGMA"],
    )
    point = result.points[0]
    warning = next(
        w
        for w in point.warnings
        if w.code is WarningCode.VERTICAL_SIGMA_UNAVAILABLE
    )

    assert "modeled_error_raw_m" not in warning.message
    assert "-0.009" not in warning.message
    assert "THE SHIFT ITSELF IS VALID" in warning.message
    # The reason field keeps both, for a caller who asks the code.
    assert "modeled_error_raw_m" in point.vertical.sigma_unavailable_reason
    assert "-0.009" in point.vertical.sigma_unavailable_reason
    # And the record therefore carries neither.
    text = report.build_report(result)
    assert "modeled_error_raw_m" not in text
    assert "-0.009651645734265912" not in text


def test_an_all_refused_vertical_record_claims_no_work_was_done(tmp_path):
    """The gate's MEDIUM 3: a modeled job whose every point was blank-Z or
    coverage-refused asserted "each point's shift ... are in the _full.csv
    export" over cells that all read N/A, and (NAVD88 source) that factors
    "were computed from" a height no factor was computed from. Both
    sentences are now guarded on work actually done. Falsified by removing
    either guard: this fails."""
    result = _vertical_file_job(
        tmp_path,
        lines=[
            "401,43.0,-84.5,,BLANKZ",
            "402,52.0,-84.5,300.000,OUTOFCOVERAGE",
        ],
        source_vertical_datum=NAVD88,
        target_vertical_datum=NGVD29,
    )
    text = _normalized(report.build_report(result))

    assert "no point carried a convertible elevation" in text
    assert "each point's shift and its one-sigma" not in text
    assert "Factor height" not in text
    # The Factor height paragraph's own distinctive claim - narrower than
    # "were computed from", which a permanent audit-description sentence
    # also contains, truthfully.
    assert "computed from the SOURCE-datum" not in text
