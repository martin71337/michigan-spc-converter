"""Vertical-only mode reaches the interface: the third radio, on both tabs.

The standing rules of tests/test_gui_vertical.py, arriving at a third mode
(the owner's feature, 2026-08-09):

**No silent defaults**: the toggle still opens on Horizontal, and choosing
Vertical answers nothing about a datum - the datum dropdowns still open
unanswered and still gate Convert.

**Hidden, not disabled**: in Vertical mode the To zone row and the output
Units selector are hidden - no output horizontal system exists, and the
export mirrors the input's unit - while From, the input Units, the geoid
dropdown and the datum rows stay.

**Every control that can change the answer invalidates a displayed one**
(amendment #26): the third radio is a new way to reproduce the one CRITICAL
this GUI has ever had, so it carries its own pin - falsified by making the
shared toggle wiring skip exactly that button.

**Two surfaces cannot disagree**: the same vertical-only point through both
tabs compares bitwise, and the Multi point table compares cell against cell
with the audit CSV inside the archive the same run wrote.

Expected values are the frozen NCAT anchors of
``tests/fixtures/vertcon_anchors.py``: at 43.0 N, 84.5 W the VERTCON 3.0
grid shifts an NGVD 29 height by about -0.140 m (NCAT prints
200.000 -> 199.860), within the 0.0005 m bound test_job_vertical.py derives.
"""

from __future__ import annotations

import os

# MUST precede any Qt import (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import csv  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

from michspc.fileio import exports, formatting as fmt, pnezd  # noqa: E402
from michspc.gui import controls  # noqa: E402
from michspc.gui import single_point as single_point_module  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.results_model import (  # noqa: E402
    INPUT_TITLE,
    OUTPUT_TITLE,
    VERTICAL_SHIFT_COLUMN_HEADING,
    VERTICAL_SIGMA_LABEL,
)
from michspc.gui.window import UNCHOSEN, MainWindow  # noqa: E402
from michspc.job import (  # noqa: E402
    Direction,
    LongitudeConvention,
    VerticalMode,
)
from michspc.spc.units import METERS  # noqa: E402
from michspc.spc.vertical import NAVD88, NGVD29  # noqa: E402
from michspc.spc.zones import MI_SOUTH  # noqa: E402
from tests.fixtures.vertcon_anchors import (  # noqa: E402
    NGVD29_TO_NAVD88_ANCHORS,
)

ANCHOR_22 = next(a for a in NGVD29_TO_NAVD88_ANCHORS if a.name == "anchor-22")
SHIFT_TOLERANCE_M = 0.0005

# Anchor-22's Michigan South position, metres - the derivation is in
# tests/test_vertical_only.py, whose constants these deliberately repeat so a
# GUI test failure names its own numbers.
ZONE_NORTHING = "166625.1664"
ZONE_EASTING = "3989128.8661"


@pytest.fixture(scope="module")
def qapp():
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


@pytest.fixture
def window(qapp):
    """A window whose modal dialogs - on both tabs - are replaced by recorders."""
    win = MainWindow()
    win.shown_failures = []
    win.overwrite_prompts = []
    win.overwrite_answer = False

    def record_failure(error):
        win.shown_failures.append(str(error) or repr(error))

    def record_overwrite(existing, error):
        win.overwrite_prompts.append([Path(p) for p in existing])
        return win.overwrite_answer

    win._show_failure = record_failure
    win._ask_overwrite = record_overwrite

    tab = win.single_point
    tab.shown_failures = []
    tab.copied = []

    def record_tab_failure(error):
        tab.shown_failures.append(str(error) or repr(error))

    def record_clipboard(text):
        tab.copied.append(text)

    tab._show_failure = record_tab_failure
    tab._set_clipboard = record_clipboard

    yield win
    win.close()


@pytest.fixture
def tab(window):
    return window.single_point


def pages(window):
    return {"single": window.single_point, "multi": window}


def choose(combo, data) -> None:
    index = combo.findData(data)
    if index < 0:
        raise AssertionError(f"{combo!r} has no entry for {data!r}")
    combo.setCurrentIndex(index)


def make_vertical_only(page, source_datum=NGVD29, target_datum=NAVD88) -> None:
    """Turn vertical-only mode on and answer both datum dropdowns."""
    page.mode_vertical_only.setChecked(True)
    choose(page.vertical_source_combo, source_datum)
    choose(page.vertical_target_combo, target_datum)


def fill_single_geodetic(tab) -> None:
    """The anchor as a geodetic vertical-only point, metres."""
    choose(tab.from_zone, controls.GEODETIC)
    choose(tab.input_unit, METERS)
    choose(tab.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    tab.first_edit.setText(str(ANCHOR_22.latitude))
    tab.second_edit.setText(str(ANCHOR_22.longitude))
    tab.elevation_edit.setText("200.000")
    make_vertical_only(tab)


def value_of(sections, title, label) -> str:
    for section in sections:
        if section.title != title:
            continue
        for value in section.values:
            if value.label == label:
                return value.text
    raise AssertionError(f"no {label!r} value in the {title} section")


def section_labels(sections, title) -> list[str]:
    for section in sections:
        if section.title == title:
            return [value.label for value in section.values]
    raise AssertionError(f"no {title} section")


def cell(window, row, column) -> str:
    return window.model.index(row, column).data(Qt.ItemDataRole.DisplayRole)


def headings(window) -> list[str]:
    return [
        window.model.headerData(i, Qt.Orientation.Horizontal)
        for i in range(window.model.columnCount())
    ]


# --------------------------------------------------------------------------
# The third radio: both tabs, shared with nobody, opens unchecked
# --------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_third_radio_exists_and_states_the_vertical_mode(window, which):
    page = pages(window)[which]

    assert page.mode_vertical_only.text() == controls.VERTICAL_ONLY_MODE_TEXT
    assert controls.VERTICAL_ONLY_MODE_TEXT == "Vertical"
    assert page.mode_vertical_only.isChecked() is False
    assert page.vertical_mode() is VerticalMode.HORIZONTAL

    page.mode_vertical_only.setChecked(True)
    assert page.vertical_mode() is VerticalMode.VERTICAL
    # The other two really are off - the group is exclusive.
    assert page.mode_horizontal.isChecked() is False
    assert page.mode_vertical.isChecked() is False


def test_the_two_tabs_share_no_third_radio(window, tab):
    assert tab.mode_vertical_only is not window.mode_vertical_only
    tab.mode_vertical_only.setChecked(True)
    assert tab.vertical_mode() is VerticalMode.VERTICAL
    assert window.vertical_mode() is VerticalMode.HORIZONTAL


# --------------------------------------------------------------------------
# What hides: the output horizontal controls (hidden, not disabled)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["single", "multi"])
def test_vertical_only_hides_the_output_controls_and_restores_them(
    window, which
):
    """No output horizontal system exists in this mode, so the To zone row
    and the output Units selector hide; From, the input Units and the geoid
    dropdown stay, and the datum rows reveal. Hidden, NOT disabled - the
    datum rows' own idiom - and everything returns when the mode does.
    ``isHidden`` is the right probe on an unshown window."""
    page = pages(window)[which]
    hidden_in_vertical_only = (
        page.to_zone_label,
        page.to_zone,
        page.output_unit_label,
        page.output_unit,
    )
    always_shown = (
        page.from_zone,
        page.input_unit_label,
        page.input_unit,
        page.geoid_combo,
    )
    datum_rows = (
        page.vertical_source_label,
        page.vertical_source_combo,
        page.vertical_target_label,
        page.vertical_target_combo,
    )

    for widget in hidden_in_vertical_only:
        assert widget.isHidden() is False, "visible before the mode is chosen"

    page.mode_vertical_only.setChecked(True)
    for widget in hidden_in_vertical_only:
        assert widget.isHidden() is True, "vertical-only mode must hide it"
        assert widget.isEnabled() is True, "hidden, not disabled"
    for widget in always_shown:
        assert widget.isHidden() is False
    for widget in datum_rows:
        assert widget.isHidden() is False, "the datum rows must reveal"

    page.mode_horizontal.setChecked(True)
    for widget in hidden_in_vertical_only:
        assert widget.isHidden() is False, "horizontal mode must restore it"
    for widget in datum_rows:
        assert widget.isHidden() is True


@pytest.mark.parametrize("which", ["single", "multi"])
def test_horizontal_and_vertical_mode_keeps_the_output_controls(window, which):
    """The middle mode still converts coordinates, so its output controls
    must not be caught by the new hiding."""
    page = pages(window)[which]
    page.mode_vertical.setChecked(True)
    for widget in (
        page.to_zone_label,
        page.to_zone,
        page.output_unit_label,
        page.output_unit,
    ):
        assert widget.isHidden() is False


# --------------------------------------------------------------------------
# Gating: the To-zone requirement drops; the datums still gate
# --------------------------------------------------------------------------


def test_convert_gates_without_a_to_zone_on_the_single_point_tab(tab):
    """In vertical-only mode a complete form needs the input system, both
    coordinates, both datums, and the convention when the input is geodetic
    - and NOT a To zone, which does not exist in this mode."""
    choose(tab.from_zone, controls.GEODETIC)
    choose(tab.input_unit, METERS)
    choose(tab.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    tab.first_edit.setText(str(ANCHOR_22.latitude))
    tab.second_edit.setText(str(ANCHOR_22.longitude))

    tab.mode_vertical_only.setChecked(True)
    assert tab.to_zone.currentData() == UNCHOSEN, (
        "anti-vacuousness: the To zone really is unanswered"
    )
    assert tab.settings() is None, "the datums still gate"
    assert tab.convert_button.isEnabled() is False

    choose(tab.vertical_source_combo, NGVD29)
    assert tab.convert_button.isEnabled() is False, "one datum is not both"

    choose(tab.vertical_target_combo, NAVD88)
    assert tab.settings() is not None
    assert tab.convert_button.isEnabled() is True


def test_convert_gates_without_a_to_zone_on_the_multi_point_tab(
    window, tmp_path
):
    window.input_edit.setText(str(tmp_path / "pts.csv"))
    window.output_edit.setText(str(tmp_path / "out"))
    choose(window.from_zone, MI_SOUTH)

    window.mode_vertical_only.setChecked(True)
    assert window.to_zone.currentData() == UNCHOSEN
    assert window.convert_button.isEnabled() is False

    choose(window.vertical_source_combo, NGVD29)
    choose(window.vertical_target_combo, NAVD88)
    assert window.settings() is not None
    assert window.convert_button.isEnabled() is True


# --------------------------------------------------------------------------
# Settings honesty
# --------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_settings_state_the_vertical_only_job_honestly(
    window, tmp_path, which
):
    """direction VERTICAL_ONLY, target_zone None, output_unit the SAME unit
    record as the input - the mirror job.run enforces - and, for a zone
    input, longitude_convention None even though the combo opens holding a
    value."""
    page = pages(window)[which]
    if which == "multi":
        window.input_edit.setText(str(tmp_path / "pts.csv"))
        window.output_edit.setText(str(tmp_path / "out"))
    else:
        page.first_edit.setText(ZONE_NORTHING)
        page.second_edit.setText(ZONE_EASTING)
    choose(page.from_zone, MI_SOUTH)
    choose(page.input_unit, METERS)
    make_vertical_only(page)

    settings = page.settings()
    assert settings is not None
    assert settings.direction is Direction.VERTICAL_ONLY
    assert settings.vertical_mode is VerticalMode.VERTICAL
    assert settings.source_zone is MI_SOUTH
    assert settings.target_zone is None
    assert settings.input_unit is METERS
    assert settings.output_unit is settings.input_unit
    # The combo holds the positive-west preselect, and the settings still
    # state None: a zone-input file carries no longitudes.
    assert page.longitude_combo.currentData() is not None
    assert settings.longitude_convention is None
    assert settings.source_vertical_datum is NGVD29
    assert settings.target_vertical_datum is NAVD88

    # Geodetic input: the convention IS read.
    choose(page.from_zone, controls.GEODETIC)
    if which == "single":
        page.first_edit.setText(str(ANCHOR_22.latitude))
        page.second_edit.setText(str(ANCHOR_22.longitude))
    choose(page.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    settings = page.settings()
    assert settings is not None
    assert settings.source_zone is None
    assert settings.longitude_convention is LongitudeConvention.NEGATIVE_WEST


def test_the_longitude_selector_follows_the_from_selection_in_this_mode(tab):
    """The To dropdown is hidden, so relevance reads From alone: enabled for
    a geodetic input (the file carries longitudes), disabled for a zone
    input (it carries none)."""
    tab.mode_vertical_only.setChecked(True)

    choose(tab.from_zone, MI_SOUTH)
    assert tab.longitude_combo.isEnabled() is False

    choose(tab.from_zone, controls.GEODETIC)
    assert tab.longitude_combo.isEnabled() is True


# --------------------------------------------------------------------------
# Invalidation: the third radio's own pin (amendment #26)
# --------------------------------------------------------------------------


def converted_horizontal(tab):
    """A displayed horizontal result to go stale."""
    choose(tab.from_zone, MI_SOUTH)
    choose(tab.to_zone, MI_SOUTH)
    tab.first_edit.setText(ZONE_NORTHING)
    tab.second_edit.setText(ZONE_EASTING)
    tab.elevation_edit.setText("200.000")
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")
    assert tab.result is not None
    assert tab.sections is not None
    assert tab.copy_all_button.isEnabled() is True


def assert_discarded(tab):
    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False
    assert tab.copy_value(0) is False
    assert tab.copy_all() is False
    assert tab.status_label.text() == single_point_module.STATUS_INPUT_CHANGED


def test_checking_the_third_radio_discards_a_displayed_result(tab):
    """The same numbers under vertical-only mode describe a different job: a
    horizontal result surviving the switch would sit one Convert away from
    claiming an unshifted elevation is a converted one. Falsified by making
    the shared toggle wiring skip the third button: this pin alone fails
    while every other invalidation pin stays green."""
    converted_horizontal(tab)
    tab.mode_vertical_only.setChecked(True)
    assert_discarded(tab)


def test_leaving_vertical_only_for_the_middle_mode_discards_too(tab):
    """The switch the old one-button wiring could never see: Vertical ->
    Horizontal + Vertical toggles neither button the old handler rode, which
    is why the wiring moved to the group's own signal."""
    converted_horizontal(tab)
    make_vertical_only(tab)
    tab.elevation_edit.setText("200.000")
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")
    assert tab.result is not None

    tab.mode_vertical.setChecked(True)
    assert_discarded(tab)


# --------------------------------------------------------------------------
# The panel: OUTPUT holds the elevation, the shift and the sigma - only
# --------------------------------------------------------------------------


def test_the_output_section_holds_exactly_the_vertical_rows(tab):
    """THE row-list pin. Nothing was converted horizontally, so the OUTPUT
    section must not show Zone, Northing or Easting rows - unchanged numbers
    under an OUTPUT heading would imply a conversion that never ran.
    Falsified by seeding the coordinate rows back into the vertical-only
    OUTPUT section: this test alone fails."""
    fill_single_geodetic(tab)
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")

    assert section_labels(tab.sections, OUTPUT_TITLE) == [
        "Elevation (NAVD88)",
        "Vertical shift NGVD29 -> NAVD88 (m)",
        VERTICAL_SIGMA_LABEL,
    ]

    # And the values are the anchor's: the elevation is the shifted height,
    # the shift is NCAT's own figure, both through the standard formatters.
    shown = value_of(tab.sections, OUTPUT_TITLE, "Elevation (NAVD88)")
    assert shown == fmt.coordinate(
        tab.result.points[0].output_elevation, METERS
    )
    assert abs(
        tab.result.points[0].output_elevation - ANCHOR_22.target_height_m
    ) < SHIFT_TOLERANCE_M


def test_the_geodetic_input_section_carries_the_point_and_its_factors(tab):
    """INPUT as normal: the typed position, its elevation in the source
    datum, and the factors - with no Zone row and no grid-factor row,
    because no zone exists anywhere in this job to own one."""
    fill_single_geodetic(tab)
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")

    labels = section_labels(tab.sections, INPUT_TITLE)
    assert labels == [
        "Latitude",
        "Latitude (DMS)",
        "Longitude",
        "Longitude (DMS)",
        "Elevation (NGVD29)",
        "Units",
        "Geoid height (m)",
        "Ellipsoid height (m)",
        "Elevation factor",
        "Combined factor",
    ]
    # The combined factor is an honest absence - no zone, no grid factor to
    # multiply - while the elevation factor is a real number.
    assert value_of(tab.sections, INPUT_TITLE, "Combined factor") == fmt.NOT_AVAILABLE
    assert value_of(tab.sections, INPUT_TITLE, "Elevation factor") != fmt.NOT_AVAILABLE


def test_the_zone_input_section_carries_the_input_zones_factors(tab):
    """Zone input: the INPUT section is the typed State Plane point with the
    INPUT zone's factors - the ZONE_TO_GEODETIC precedent - and the OUTPUT
    section is still only the vertical rows."""
    choose(tab.from_zone, MI_SOUTH)
    choose(tab.input_unit, METERS)
    tab.first_edit.setText(ZONE_NORTHING)
    tab.second_edit.setText(ZONE_EASTING)
    tab.elevation_edit.setText("200.000")
    make_vertical_only(tab)
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")

    labels = section_labels(tab.sections, INPUT_TITLE)
    assert labels == [
        "Zone",
        "Units",
        "Northing",
        "Easting",
        "Elevation (NGVD29)",
        "Grid scale factor",
        "Convergence",
        "Geoid height (m)",
        "Ellipsoid height (m)",
        "Elevation factor",
        "Combined factor",
    ]
    assert value_of(tab.sections, INPUT_TITLE, "Grid scale factor") != fmt.NOT_AVAILABLE
    assert value_of(tab.sections, INPUT_TITLE, "Combined factor") != fmt.NOT_AVAILABLE
    assert section_labels(tab.sections, OUTPUT_TITLE) == [
        "Elevation (NAVD88)",
        "Vertical shift NGVD29 -> NAVD88 (m)",
        VERTICAL_SIGMA_LABEL,
    ]
    # The typed coordinates are shown exactly as the formatters render the
    # parsed input - the mirror, on screen.
    assert value_of(tab.sections, INPUT_TITLE, "Northing") == ZONE_NORTHING
    assert value_of(tab.sections, INPUT_TITLE, "Easting") == ZONE_EASTING


# --------------------------------------------------------------------------
# The two tabs cannot disagree about a vertical-only point (amendment #26)
# --------------------------------------------------------------------------


def test_the_two_tabs_cannot_disagree_about_a_vertical_only_point(
    window, tab, tmp_path
):
    job_file = tmp_path / "one-point.csv"
    job_file.write_text(
        f"{pnezd.TYPED_POINT_ID},{ANCHOR_22.latitude},{ANCHOR_22.longitude},"
        f"200.000\n",
        encoding="utf-8",
    )
    window.input_edit.setText(str(job_file))
    window.output_edit.setText(str(tmp_path / "out"))
    choose(window.from_zone, controls.GEODETIC)
    choose(window.input_unit, METERS)
    choose(window.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    make_vertical_only(window)
    if window.convert() is not True:
        raise AssertionError(f"the multi-point run failed: {window.shown_failures}")

    fill_single_geodetic(tab)
    if tab.convert() is not True:
        raise AssertionError(f"the single-point run failed: {tab.shown_failures}")

    from_file = window.result.points[0]
    typed = tab.result.points[0]

    assert typed.output_northing == from_file.output_northing
    assert typed.output_easting == from_file.output_easting
    assert typed.output_elevation == from_file.output_elevation
    assert typed.vertical is not None and from_file.vertical is not None
    assert typed.vertical.shift_m == from_file.vertical.shift_m
    assert typed.vertical.sigma_m == from_file.vertical.sigma_m
    assert [w.message for w in typed.warnings] == [
        w.message for w in from_file.warnings
    ]

    # Not two matching zeroes: the shift really is the anchor's.
    assert abs(typed.vertical.shift_m - ANCHOR_22.shift_m) < SHIFT_TOLERANCE_M


# --------------------------------------------------------------------------
# The Multi point table against the audit CSV (the #26 property, new mode)
# --------------------------------------------------------------------------


def vertical_only_multi_job(window, tmp_path):
    """Three geodetic rows: the anchor, a blank-Z row, the max-sigma point."""
    job_file = tmp_path / "three-point.csv"
    job_file.write_text(
        f"101,{ANCHOR_22.latitude},{ANCHOR_22.longitude},200.000,ANCHOR\n"
        f"102,43.1,-84.6,,NO ELEVATION\n"
        f"103,43.05,-86.20,200.000,MAX SIGMA\n",
        encoding="utf-8",
    )
    window.input_edit.setText(str(job_file))
    window.output_edit.setText(str(tmp_path / "out"))
    choose(window.from_zone, controls.GEODETIC)
    choose(window.input_unit, METERS)
    choose(window.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    make_vertical_only(window)
    if window.convert() is not True:
        raise AssertionError(f"the multi-point run failed: {window.shown_failures}")


def test_the_vertical_only_table_and_the_audit_csv_cannot_disagree(
    window, tmp_path, read_member
):
    """Cell against cell, screen against the file the same run wrote. The
    coordinate columns carry the pass-through positions under geodetic
    headings, the Elevation heading names the target datum, and the shift
    and sigma columns are the audit CSV's own."""
    vertical_only_multi_job(window, tmp_path)

    audit_name = exports.member_names(window.result)["audit"]
    text = read_member(window.written_files["archive"], audit_name)
    rows = list(csv.reader(text.splitlines()))
    header = rows[0]

    table_columns = headings(window)
    assert "Elevation (NAVD88)" in table_columns
    assert "Latitude" in table_columns and "Longitude" in table_columns

    correspondence = {
        "Point": "Point",
        "Latitude": "Target latitude",
        "Longitude": "Target longitude (as written)",
        "Elevation (NAVD88)": "Elevation",
        VERTICAL_SHIFT_COLUMN_HEADING: VERTICAL_SHIFT_COLUMN_HEADING,
        VERTICAL_SIGMA_LABEL: VERTICAL_SIGMA_LABEL,
        "Grid scale factor": "Grid scale factor",
        "Combined factor": "Combined factor",
    }

    compared = 0
    for row_index in range(window.model.rowCount()):
        audit = dict(zip(header, rows[1 + row_index]))
        for table_heading, audit_heading in correspondence.items():
            assert table_heading in table_columns
            assert audit_heading in audit
            shown = cell(window, row_index, table_columns.index(table_heading))
            assert shown == audit[audit_heading], (
                f"row {row_index}, {table_heading!r}: table {shown!r} != "
                f"audit CSV {audit[audit_heading]!r}"
            )
            compared += 1
        # The pass-through statement itself, against the file: the target
        # coordinate cells equal the source cells.
        assert audit["Target latitude"] == audit["Source latitude"]
        assert (
            audit["Target longitude (as written)"]
            == audit["Source longitude (as in file)"]
        )

    assert compared == 3 * len(correspondence)
    # Anti-vacuousness: the anchor row's shift is a real number, and the
    # no-zone factor cells really are absences.
    assert cell(
        window, 0, table_columns.index(VERTICAL_SHIFT_COLUMN_HEADING)
    ) != fmt.NOT_AVAILABLE
    assert cell(
        window, 0, table_columns.index("Grid scale factor")
    ) == fmt.NOT_AVAILABLE


def test_the_vertical_only_tables_coordinates_are_the_inputs_own(
    window, tmp_path
):
    vertical_only_multi_job(window, tmp_path)
    table_columns = headings(window)

    assert cell(window, 0, table_columns.index("Latitude")) == fmt.latitude(
        ANCHOR_22.latitude
    )
    assert cell(window, 0, table_columns.index("Longitude")) == fmt.longitude(
        ANCHOR_22.longitude
    )
    # The blank-Z row passes its coordinates through too, with N/A verticals.
    at = table_columns.index("Elevation (NAVD88)")
    assert cell(window, 1, at) == fmt.NOT_AVAILABLE
    assert cell(window, 1, at + 1) == fmt.NOT_AVAILABLE
    assert cell(window, 1, at + 2) == fmt.NOT_AVAILABLE
