"""The owner's units instruction (2026-08-09): shift and sigma read in the
JOB'S INPUT UNIT, and every datum-labelled elevation names its unit.

Before this change every shift and sigma surface rendered metres through
``formatting.vertical_metres`` while the panel and table labels said "(m)"
even over a feet job - a wrong statement about a number one click from the
clipboard. Now ``formatting.vertical_quantity(value_m, unit)`` converts at
the presentation boundary (``VerticalReading.shift_m``/``sigma_m`` stay
metres, the one authoritative representation), and every label carries the
unit its value is rendered in. This module pins the conversion with
hand-derived figures and pins that all four surfaces - the Single point
panel, the Multi point table strings, the audit CSV, and the job record's
sigma summary - agree in feet exactly as they already agreed in metres.

Truth sources, as in tests/test_vertical_disclosure.py: 43.0 N / -84.5 W and
43.05 N / -86.2 W are EXACT nodes of the 0.05-degree VERTCON grids, so the
stored cell values settle every figure (DESIGN.md #36), and both agree with
the frozen NCAT lattice (tests/fixtures/vertcon_anchors.py):

    43.0,  -84.5    shift -0.14019644260406494 m  sigma 0.0006554240244440734 m
    43.05, -86.2    shift -0.14352931082248527 m  sigma 0.36559906601907743 m
    42.475,-83.125  shift -0.13599119428545237 m  sigma None (DESIGN.md #36)

Hand-derived conversions (unit sizes are exact by definition: the
International foot is 0.3048 m, NOAA Manual NOS NGS 5 PDF p. 22; the US
survey foot is 1200/3937 m, same page):

  anchor-22 shift, International feet: -0.14019644260406494 / 0.3048
      = -0.45996208203433375        -> "-0.460" at ift's 3 dp
  anchor-22 shift, US survey feet:    -0.14019644260406494 * 3937 / 1200
      = -0.45996116211016974        -> "-0.460" at 3 dp
      (the two floats differ in the 7th significant digit - the 2 ppm
      between the foot definitions - and render identically at 3 dp; the
      derivation is exact and the strings agreeing is a checked fact, not
      an assumption)
  anchor-22 sigma, ift:  0.0006554240244440734 / 0.3048
      = 0.0021503412875461727       -> "0.002"
  max-sigma sigma, ift:  0.36559906601907743 / 0.3048
      = 1.1994720013749258          -> "1.199"
  mean sigma over {anchor-22, max-sigma}, converted from the metre mean
      0.18312724502176075:  / 0.3048 = 0.6008111713312361 -> "0.601"
  neg-sigma shift, ift: -0.13599119428545237 / 0.3048
      = -0.4461653355821928         -> "-0.446"

  A 200.000 ift source elevation is 200.000 * 0.3048 = 60.96 m exactly;
  shifted, 60.96 - 0.14019644260406494 = 60.819803557395936 m, which is
      "60.8198" in metres (4 dp) and
      / 0.3048 = 199.54003791796566 -> "199.540" in ift (3 dp).

  The metre job is the regression floor: the same readings must render
  exactly as they always have - shift "-0.1402", sigma "0.0007", max sigma
  "0.3656" - because vertical_quantity(value, METERS) divides by 1.0 and
  formats at the metre unit's own 4 places, byte for byte what the retired
  ``vertical_metres`` printed.

The load-bearing falsification (recorded in the work report): swapping the
formatter's ``from_meters`` for ``to_meters`` multiplies instead of divides,
so the ift shift would render -0.14019644260406494 * 0.3048
= -0.042731876185718994 -> "-0.043" - an order of magnitude from "-0.460" -
and every ift pin below fails while the metre pins (conversion by 1.0,
identical both ways) stay green. That is why the feet pins exist.
"""

from __future__ import annotations

import csv
import io
import os
import zipfile

# MUST precede any Qt import (docs/method/TOOLING.md): results_model imports
# PySide6 at module level.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402

from michspc.fileio import exports, formatting as fmt, pnezd, report  # noqa: E402
from michspc.gui import results_model as rm  # noqa: E402
from michspc.job import (  # noqa: E402
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc.units import (  # noqa: E402
    INTERNATIONAL_FEET,
    METERS,
    US_SURVEY_FEET,
)
from michspc.spc.vertical import NAVD88, NGVD29  # noqa: E402
from michspc.spc.zones import MI_SOUTH  # noqa: E402

# The exact-node positions and their stored grid values (module docstring).
ANCHOR_22 = (43.0, -84.5)
MAX_SIGMA = (43.05, -86.2)
NEG_SIGMA = (42.475, -83.125)

ANCHOR_22_SHIFT_M = -0.14019644260406494
ANCHOR_22_SIGMA_M = 0.0006554240244440734
MAX_SIGMA_SIGMA_M = 0.36559906601907743
NEG_SIGMA_SHIFT_M = -0.13599119428545237


def _feet_job(tmp_path, lines, **overrides):
    """A written geodetic NGVD29 -> NAVD88 job, elevations in ift both ends."""
    source = tmp_path / "vfeet.csv"
    source.write_text("\n".join(lines) + "\n", encoding="ascii")
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    base = dict(
        input_path=source,
        output_directory=out,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    base.update(overrides)
    return run(JobSettings(**base))


def _typed_job(**overrides):
    """A single typed geodetic point at the anchor, for the panel."""
    parsed = pnezd.parse_typed_point(
        str(overrides.pop("latitude", ANCHOR_22[0])),
        str(overrides.pop("longitude", ANCHOR_22[1])),
        overrides.pop("elevation", "200.000"),
        source=pnezd.TYPED_POINT_SOURCE_GEODETIC,
    )
    base = dict(
        input_path=None,
        output_directory=None,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    base.update(overrides)
    return run(JobSettings(**base), source=parsed)


def _by_label(section):
    return {value.label: value.text for value in section.values}


def _member_text(archive_path, suffix):
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            if name.endswith(suffix):
                return archive.read(name).decode("utf-8")
    raise AssertionError(f"no member ending {suffix!r} in {archive_path}")


# ==========================================================================
# The formatter itself, hand-derived in every unit.
# ==========================================================================


def test_the_formatter_converts_then_rounds_hand_derived():
    """Divide by the unit's size in metres, THEN round at the unit's own
    declared precision - each figure derived by hand in the module
    docstring. The swapped-conversion seed (to_meters: multiply by 0.3048)
    would print "-0.043" here, not "-0.460"."""
    assert fmt.vertical_quantity(ANCHOR_22_SHIFT_M, INTERNATIONAL_FEET) == "-0.460"
    assert fmt.vertical_quantity(ANCHOR_22_SHIFT_M, US_SURVEY_FEET) == "-0.460"
    assert fmt.vertical_quantity(ANCHOR_22_SHIFT_M, METERS) == "-0.1402"

    assert fmt.vertical_quantity(ANCHOR_22_SIGMA_M, INTERNATIONAL_FEET) == "0.002"
    assert fmt.vertical_quantity(MAX_SIGMA_SIGMA_M, INTERNATIONAL_FEET) == "1.199"
    assert fmt.vertical_quantity(MAX_SIGMA_SIGMA_M, US_SURVEY_FEET) == "1.199"
    assert fmt.vertical_quantity(ANCHOR_22_SIGMA_M, METERS) == "0.0007"
    assert fmt.vertical_quantity(MAX_SIGMA_SIGMA_M, METERS) == "0.3656"

    # The two foot definitions really do produce different floats - the 2 ppm
    # between 0.3048 and 1200/3937 - that happen to agree at 3 dp here. This
    # keeps the usft pin above from being vacuously the ift one.
    assert (
        INTERNATIONAL_FEET.from_meters(ANCHOR_22_SHIFT_M)
        == -0.45996208203433375
    )
    assert US_SURVEY_FEET.from_meters(ANCHOR_22_SHIFT_M) == -0.45996116211016974


def test_the_formatter_prints_na_for_none_in_every_unit():
    """The #36 rule survives the unit parameter: an absent value is N/A in
    every unit, never a number and never a unit-dependent string."""
    for unit in (INTERNATIONAL_FEET, US_SURVEY_FEET, METERS):
        assert fmt.vertical_quantity(None, unit) == fmt.NOT_AVAILABLE


def test_an_identity_zero_renders_at_the_units_own_precision():
    """A real zero shift prints as one, at the unit's declared decimals:
    "0.000" in either foot, "0.0000" in metres."""
    assert fmt.vertical_quantity(0.0, INTERNATIONAL_FEET) == "0.000"
    assert fmt.vertical_quantity(0.0, US_SURVEY_FEET) == "0.000"
    assert fmt.vertical_quantity(0.0, METERS) == "0.0000"


# ==========================================================================
# Every surface, one feet job: panel, table strings, audit CSV, record.
# ==========================================================================


def test_every_surface_agrees_for_a_feet_job(tmp_path):
    """The cross-surface pin in International feet: the audit CSV's shift and
    sigma cells, the table's cells under the ift headings, and the record's
    sigma summary all carry the hand-derived feet figures - and the CSV's
    heading and value move TOGETHER (a heading claiming ift over a metre
    value would be the worst outcome of this change)."""
    result = _feet_job(
        tmp_path,
        [
            f"101,{ANCHOR_22[0]},{ANCHOR_22[1]},200.000,ANCHOR22",
            f"102,{MAX_SIGMA[0]},{MAX_SIGMA[1]},200.000,MAXSIGMA",
        ],
    )

    # --- The audit CSV: ift headings over ift values.
    header, *rows = exports.audit_rows(result)
    assert "Vertical shift (ift)" in header
    assert "Shift sigma (ift)" in header
    assert "Vertical shift (m)" not in header
    assert "Shift sigma (m)" not in header
    anchor = dict(zip(header, rows[0]))
    assert anchor["Source elevation (ift)"] == "200.000"
    assert anchor["Vertical shift (ift)"] == "-0.460"
    assert anchor["Shift sigma (ift)"] == "0.002"
    # The Elevation column stays in the OUTPUT unit (ift here):
    # 60.96 - 0.14019644... m = 60.819803557395936 m -> "199.540" ift.
    assert anchor["Elevation"] == "199.540"
    maxsig = dict(zip(header, rows[1]))
    assert maxsig["Shift sigma (ift)"] == "1.199"

    # And the WRITTEN file carries the same header and cells.
    written = exports.write_all(result)
    text = _member_text(written["archive"], "_full.csv")
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == header
    assert parsed[1] == rows[0]

    # --- The table strings: the shared ift headings, the same cells.
    columns = rm.columns_for(result)
    assert "Vertical shift (ift)" in columns
    assert "Shift sigma (ift)" in columns
    assert "Elevation (NAVD88, ift)" in columns
    table_rows = rm.row_strings(result)
    shift_at = columns.index("Vertical shift (ift)")
    sigma_at = columns.index("Shift sigma (ift)")
    elevation_at = columns.index("Elevation (NAVD88, ift)")
    assert table_rows[0][shift_at] == "-0.460"
    assert table_rows[0][sigma_at] == "0.002"
    assert table_rows[0][elevation_at] == "199.540"
    assert table_rows[1][sigma_at] == "1.199"

    # --- The record's sigma summary, in the input unit, min/max/mean
    # hand-derived: min 0.002 (anchor-22), max 1.199 (max-sigma), mean
    # (0.0006554240244440734 + 0.36559906601907743) / 2 = 0.18312724502176075 m
    # / 0.3048 = 0.6008111713312361 -> "0.601".
    record = report.build_report(result)
    expected = (
        "  Shift one-sigma uncertainty (ift)\n"
        "    minimum  0.002\n"
        "    maximum  1.199\n"
        "    mean     0.601"
    )
    assert expected in record
    assert "Shift one-sigma uncertainty (m)" not in record
    # The sigma-exceeds-shift rule still names the max-sigma point: compared
    # in metres on the reading (0.3656 > 0.1435), unit-invariantly.
    assert "Points whose shift uncertainty EXCEEDS the shift itself (1):" in record


def test_the_panel_agrees_for_a_feet_job():
    """The Single point panel's rows for the same configuration: ift in every
    label, the hand-derived feet values, and the elevations labelled with
    each end's own datum AND unit."""
    result = _typed_job()
    source, target = rm.single_point_sections(result)
    source_values = _by_label(source)
    target_values = _by_label(target)

    assert source_values["Elevation (NGVD29, ift)"] == "200.000"
    assert target_values["Elevation (NAVD88, ift)"] == "199.540"
    assert target_values["Vertical shift NGVD29 -> NAVD88 (ift)"] == "-0.460"
    assert target_values["Shift sigma (ift)"] == "0.002"
    # No metre spelling survives anywhere on this panel.
    for labels in (source_values, target_values):
        assert "Shift sigma (m)" not in labels
        assert "Vertical shift NGVD29 -> NAVD88 (m)" not in labels

    # And the clipboard serialises the same ift rows.
    text = rm.single_point_clipboard_text((source, target))
    assert "Vertical shift NGVD29 -> NAVD88 (ift)\t-0.460" in text
    assert "Shift sigma (ift)\t0.002" in text
    assert "Elevation (NAVD88, ift)\t199.540" in text


def test_the_metre_job_is_the_regression_floor(tmp_path):
    """The same two points in metres render exactly as they always have -
    the strings 0.4.0's whole vertical suite already pins, restated here
    beside the feet case so a unit regression fails a test that names both."""
    result = _feet_job(
        tmp_path,
        [
            f"101,{ANCHOR_22[0]},{ANCHOR_22[1]},200.000,ANCHOR22",
            f"102,{MAX_SIGMA[0]},{MAX_SIGMA[1]},200.000,MAXSIGMA",
        ],
        input_unit=METERS,
        output_unit=METERS,
    )

    header, *rows = exports.audit_rows(result)
    anchor = dict(zip(header, rows[0]))
    assert anchor["Vertical shift (m)"] == "-0.1402"
    assert anchor["Shift sigma (m)"] == "0.0007"
    assert dict(zip(header, rows[1]))["Shift sigma (m)"] == "0.3656"

    columns = rm.columns_for(result)
    assert "Vertical shift (m)" in columns
    assert "Elevation (NAVD88, m)" in columns

    record = report.build_report(result)
    assert (
        "  Shift one-sigma uncertainty (m)\n"
        "    minimum  0.0007\n"
        "    maximum  0.3656" in record
    )


def test_the_sigma_na_path_is_unchanged_in_feet(tmp_path):
    """DESIGN.md #36 in the new unit: where no uncertainty can be stated the
    cell reads N/A in feet exactly as in metres - never a number, converted
    or otherwise - while the shift beside it is the hand-derived feet value
    (-0.13599119428545237 m / 0.3048 = -0.4461653355821928 -> "-0.446")."""
    result = _feet_job(
        tmp_path,
        [f"301,{NEG_SIGMA[0]},{NEG_SIGMA[1]},200.000,NEGSIGMA"],
    )

    header, *rows = exports.audit_rows(result)
    row = dict(zip(header, rows[0]))
    assert row["Shift sigma (ift)"] == fmt.NOT_AVAILABLE
    assert row["Vertical shift (ift)"] == "-0.446"

    columns = rm.columns_for(result)
    cells = rm.row_strings(result)[0]
    assert cells[columns.index("Shift sigma (ift)")] == fmt.NOT_AVAILABLE

    panel = _typed_job(latitude=NEG_SIGMA[0], longitude=NEG_SIGMA[1])
    _, target = rm.single_point_sections(panel)
    values = _by_label(target)
    assert values["Shift sigma (ift)"] == fmt.NOT_AVAILABLE
    assert values["Vertical shift NGVD29 -> NAVD88 (ift)"] == "-0.446"

    # The record still counts and names the point, and its summary line is
    # the honest absence in the input unit.
    record = report.build_report(result)
    assert "Points where no uncertainty could be stated (1):" in record
    assert "Shift one-sigma uncertainty (ift)" in record


def test_an_identity_feet_job_prints_a_three_place_zero(tmp_path):
    """The identity pin at the surfaces: shift "0.000" at ift's 3 places
    (never the metre "0.0000"), sigma N/A because no model ran."""
    result = _feet_job(
        tmp_path,
        [f"101,{ANCHOR_22[0]},{ANCHOR_22[1]},200.000,IDENTITY"],
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
    )

    header, *rows = exports.audit_rows(result)
    row = dict(zip(header, rows[0]))
    assert row["Vertical shift (ift)"] == "0.000"
    assert row["Shift sigma (ift)"] == fmt.NOT_AVAILABLE

    columns = rm.columns_for(result)
    cells = rm.row_strings(result)[0]
    assert cells[columns.index("Vertical shift (ift)")] == "0.000"


# ==========================================================================
# Horizontal + Vertical with DIFFERING units: each label names its own end.
# ==========================================================================


def test_differing_units_label_each_end_with_its_own_unit():
    """Input ift, output metres - legal in Horizontal + Vertical. The INPUT
    elevation label carries the input unit and the OUTPUT one the output
    unit (the falsification: feeding the OUTPUT label from the input unit
    prints "Elevation (NAVD88, ift)" over a metre value, and this test
    alone names it). The shift and sigma stay in the INPUT unit - the
    owner's words, "whatever the input units are" - even though the
    elevation beside them is metres."""
    result = _typed_job(output_unit=METERS)
    source, target = rm.single_point_sections(result)
    source_values = _by_label(source)
    target_values = _by_label(target)

    # 200.000 ift in, 60.96 m exactly; shifted 60.819803557395936 m out.
    assert source_values["Elevation (NGVD29, ift)"] == "200.000"
    assert target_values["Elevation (NAVD88, m)"] == "60.8198"
    assert "Elevation (NAVD88, ift)" not in target_values
    # The shift and sigma read in the INPUT unit beside the metre elevation.
    assert target_values["Vertical shift NGVD29 -> NAVD88 (ift)"] == "-0.460"
    assert target_values["Shift sigma (ift)"] == "0.002"

    # The table for the same settings: Elevation heading in the output unit,
    # shift and sigma headings in the input unit, cells to match.
    columns = rm.columns_for(result)
    assert "Elevation (NAVD88, m)" in columns
    assert "Vertical shift (ift)" in columns
    assert "Shift sigma (ift)" in columns
    cells = rm.row_strings(result)[0]
    assert cells[columns.index("Elevation (NAVD88, m)")] == "60.8198"
    assert cells[columns.index("Vertical shift (ift)")] == "-0.460"

    # And the audit CSV takes the same split: Source elevation and the two
    # vertical columns in ift, the target Elevation column in metres.
    header, *rows = exports.audit_rows(result)
    row = dict(zip(header, rows[0]))
    assert row["Source elevation (ift)"] == "200.000"
    assert row["Vertical shift (ift)"] == "-0.460"
    assert row["Elevation"] == "60.8198"


def test_a_horizontal_job_gains_no_unit_suffix_anywhere():
    """Nothing about horizontal output changes by a byte: the plain
    "Elevation" labels stay plain (the Units row serves them), and no
    shift or sigma wording appears in any unit's spelling."""
    result = _typed_job(
        vertical_mode=VerticalMode.HORIZONTAL,
        source_vertical_datum=None,
        target_vertical_datum=None,
    )
    source, target = rm.single_point_sections(result)
    for section in (source, target):
        labels = [value.label for value in section.values]
        assert "Elevation" in labels
        for label in labels:
            assert "Vertical shift" not in label
            assert "Shift sigma" not in label
            assert ", ift)" not in label and ", m)" not in label
    # The table header is the unchanged horizontal one (GEODETIC_TO_ZONE
    # renders grid coordinates, so the plain COLUMNS).
    assert rm.columns_for(result) == rm.COLUMNS
