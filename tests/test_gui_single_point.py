"""The Single point tab, tested headless.

One property dominates this file, and it is the reason the tab exists in the
shape it does.

**The two tabs must be incapable of disagreeing.** A surveyor who checks one
coordinate on the Single point tab and then runs the same point through a file
on the Multi point tab must get the same numbers — a discrepancy between two
views of one conversion is the tier sentence's failure mode arriving by a new
road (docs/DESIGN.md amendment #26). The pin for that is
``test_the_two_tabs_cannot_disagree_about_the_same_point``: it converts the same
three numbers both ways and compares the floats **bitwise**, the warning
messages byte for byte, and the displayed strings against the multi-point
table's own cells.

The remaining tests are the ordinary interface properties: no silent defaults,
refusals arriving intact, nothing written, and every displayed string coming
from the formatters rather than from a literal typed here. A literal would pass
while the screen and the report drifted apart, which is the exact failure the
rule exists to prevent (docs/method/METHOD.md section 5).
"""

from __future__ import annotations

import os

# MUST precede any Qt import: the platform plugin is chosen at import time and a
# later change is ignored, leaving the run needing a display it does not have
# (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import csv  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QFrame, QLabel, QToolButton  # noqa: E402

from michspc.fileio import exports, formatting as fmt, pnezd  # noqa: E402
from michspc.gui import results_model, single_point as single_point_module  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.results_model import (  # noqa: E402
    COMBINED_FACTOR_LABEL,
    ELEVATION_FACTOR_LABEL,
    ELEVATION_LABEL,
    EASTING_LABEL,
    GRID_FACTOR_LABEL,
    INPUT_TITLE,
    LATITUDE_LABEL,
    LONGITUDE_LABEL,
    NORTHING_LABEL,
    OUTPUT_TITLE,
    single_point_clipboard_text,
)
from michspc.gui.window import GEODETIC, UNCHOSEN, MainWindow  # noqa: E402
from michspc.job import Direction, LongitudeConvention  # noqa: E402
from michspc.spc.units import INTERNATIONAL_FEET, METERS  # noqa: E402
from michspc.spc.zones import ALL_ZONES, MI_CENTRAL, MI_NORTH, MI_SOUTH  # noqa: E402


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    """One QApplication for the whole module.

    A second QApplication in the same process crashes the interpreter
    (docs/method/TOOLING.md), so this is module-scoped and goes through the same
    constructor the shipped entry point uses.
    """
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


@pytest.fixture
def window(qapp):
    """A window whose modal dialogs — on both tabs — are replaced by recorders.

    A headless run cannot answer a modal box, and a test that could not observe
    what the box said would not be testing the thing that matters. Both seams
    are plain methods for exactly this reason.
    """
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
    """The Single point tab of that window."""
    return window.single_point


# The same point, several ways. Hand-derived siting, reused from
# tests/test_gui.py:
#
# Michigan Central's grid origin is 43 deg 19 min N with a false northing of 0
# and a false easting of 6,000,000 m (NOAA Manual NOS NGS 5 Appendix A;
# michspc/spc/zones.py MI_CENTRAL).
#
#   northing 176,200 ift x 0.3048 = 53,705.76 m above the grid origin
#   53,705.76 m / 111,132 m per degree = 0.4833 deg
#   latitude = 43.3167 + 0.4833 = 43.800 N
#
#   easting 19,685,000 ift x 0.3048 = 5,999,988 m, i.e. 12 m west of the
#   central meridian at 84 deg 22 min W, so longitude = -84.367 to within a
#   second or so.
#
# 43.800 N is inside Michigan Central's extent (43.5-46.0) and inside Michigan
# South's (41.6-44.3), so every case below except the last raises no warning at
# all - and the last one warns on purpose.
CENTRAL_NORTHING = "176200.000"
CENTRAL_EASTING = "19685000.000"
CENTRAL_ELEVATION = "812.40"
CENTRAL_LATITUDE = "43.800"
CENTRAL_LONGITUDE = "-84.367"


class Case:
    """One direction, with a typed point that suits it."""

    def __init__(self, name, source, target, first, second, elevation, convention):
        self.name = name
        self.source = source
        self.target = target
        self.first = first
        self.second = second
        self.elevation = elevation
        self.convention = convention

    def __repr__(self) -> str:  # pragma: no cover - pytest ids only
        return self.name


DIRECTION_CASES = (
    Case(
        "zone_to_zone",
        MI_CENTRAL,
        MI_SOUTH,
        CENTRAL_NORTHING,
        CENTRAL_EASTING,
        CENTRAL_ELEVATION,
        None,
    ),
    Case(
        "zone_to_geodetic",
        MI_CENTRAL,
        GEODETIC,
        CENTRAL_NORTHING,
        CENTRAL_EASTING,
        CENTRAL_ELEVATION,
        LongitudeConvention.NEGATIVE_WEST,
    ),
    Case(
        "geodetic_to_zone",
        GEODETIC,
        MI_CENTRAL,
        CENTRAL_LATITUDE,
        CENTRAL_LONGITUDE,
        CENTRAL_ELEVATION,
        LongitudeConvention.NEGATIVE_WEST,
    ),
    # The same two geodetic directions again in the OTHER convention. The
    # multi-point table renders a longitude from the row's own column while the
    # single-point panel renders it from the signed pivot the core stores
    # (results_model._geodetic_values); the two are the same IEEE negation, and
    # this is what holds them to it.
    Case(
        "zone_to_geodetic_positive_west",
        MI_CENTRAL,
        GEODETIC,
        CENTRAL_NORTHING,
        CENTRAL_EASTING,
        CENTRAL_ELEVATION,
        LongitudeConvention.POSITIVE_WEST,
    ),
    Case(
        "geodetic_to_zone_positive_west",
        GEODETIC,
        MI_CENTRAL,
        CENTRAL_LATITUDE,
        "84.367",
        CENTRAL_ELEVATION,
        LongitudeConvention.POSITIVE_WEST,
    ),
    # A case that deliberately warns, so the byte-identical warning
    # comparison below has something to compare. A Michigan Central easting
    # declared as Michigan South data is about 2,000,000 m away from where
    # South's eastings sit, which is what easting_looks_wrong_for_zone exists
    # to catch - and the warning text names "point 1", which is exactly why
    # pnezd.TYPED_POINT_ID is "1" rather than nothing.
    Case(
        "zone_to_zone_warned",
        MI_SOUTH,
        MI_NORTH,
        CENTRAL_NORTHING,
        CENTRAL_EASTING,
        CENTRAL_ELEVATION,
        None,
    ),
)


def case_named(name: str) -> Case:
    """One of the cases above, by name.

    By name and not by index: the tuple is a parametrisation list that grows,
    and a positional reference would quietly start naming a different direction
    the next time a case is inserted.
    """
    for case in DIRECTION_CASES:
        if case.name == name:
            return case
    raise AssertionError(f"no case named {name!r}")


def as_the_file_writes_it(text: str) -> str:
    """A panel string with its display-only punctuation taken back off.

    The panel shows ``43.80000000°`` and ``-16°49\'17.78"`` where the audit CSV
    and the multi-point table show ``43.80000000`` and ``-16 49 17.78``
    (docs/DESIGN.md amendment #30). That difference is punctuation and nothing
    else: ``formatting.latitude_display`` and ``convergence_display`` are built
    on the file formatters rather than reimplementing the number.

    So the agreement tests below normalise rather than skip. Stripping the
    symbols and then demanding equality still catches a digit that differs,
    which is the property those tests exist for; ignoring the rows would not.
    """
    return (
        text.replace(fmt.DEGREE_SYMBOL, " ")
        .replace("'", " ")
        .replace('"', "")
        .strip()
    )


def fill_single(tab, case):
    """Answer the Single point form the way a user would, widget by widget."""
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(case.source))
    tab.to_zone.setCurrentIndex(tab.to_zone.findData(case.target))
    tab.first_edit.setText(case.first)
    tab.second_edit.setText(case.second)
    tab.elevation_edit.setText(case.elevation)
    if case.convention is not None:
        tab.longitude_combo.setCurrentIndex(
            tab.longitude_combo.findData(case.convention)
        )


def fill_multi(window, case, *, input_path, output_directory):
    """The same answers on the Multi point tab, plus the file and the folder."""
    window.input_edit.setText(str(input_path))
    window.output_edit.setText(str(output_directory))
    window.from_zone.setCurrentIndex(window.from_zone.findData(case.source))
    window.to_zone.setCurrentIndex(window.to_zone.findData(case.target))
    if case.convention is not None:
        window.longitude_combo.setCurrentIndex(
            window.longitude_combo.findData(case.convention)
        )


def value_of(sections, title, label) -> str:
    """The displayed text of one labelled value in one named section.

    Section-qualified on purpose: "Northing", "Units" and "Grid scale factor"
    each appear in BOTH sections of a zone-to-zone result, and an unqualified
    lookup would silently compare the wrong end of the job.
    """
    for section in sections:
        if section.title != title:
            continue
        for value in section.values:
            if value.label == label:
                return value.text
    raise AssertionError(f"no {label!r} value in the {title} section")


def cell(window, row, column) -> str:
    return window.model.index(row, column).data(Qt.ItemDataRole.DisplayRole)


# --------------------------------------------------------------------------
# The two tabs share nothing
# --------------------------------------------------------------------------


def test_the_two_tabs_share_no_control(window, tab):
    """Six dropdowns and a button, and not one of them is the same object.

    A shared control would let a choice made on one tab silently change what
    the other converts, which is the state amendment #26 forbids.
    """
    assert tab is not window
    assert tab.from_zone is not window.from_zone
    assert tab.to_zone is not window.to_zone
    assert tab.input_unit is not window.input_unit
    assert tab.output_unit is not window.output_unit
    assert tab.longitude_combo is not window.longitude_combo
    assert tab.convert_button is not window.convert_button
    assert tab.status_label is not window.status_label


def test_choosing_on_one_tab_does_not_answer_the_other(window, tab):
    """The multi-point form is still unanswered afterwards."""
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(MI_CENTRAL))
    tab.to_zone.setCurrentIndex(tab.to_zone.findData(MI_SOUTH))

    assert window.from_zone.currentData() == UNCHOSEN
    assert window.to_zone.currentData() == UNCHOSEN
    assert window.convert_button.isEnabled() is False


def test_the_single_point_tab_is_index_zero(window, tab):
    """The window opens on the everyday case, which is the owner's order."""
    assert window.tabs.widget(0) is tab
    assert window.tabs.currentIndex() == 0


# --------------------------------------------------------------------------
# Convert is enabled by exactly the right answers
# --------------------------------------------------------------------------


def test_convert_starts_disabled(tab):
    """Nothing has been answered, so there is nothing to convert."""
    assert tab.convert_button.isEnabled() is False
    assert tab.settings() is None
    assert tab.result is None


def test_every_answer_is_necessary_and_together_they_are_sufficient(tab):
    """Remove any one of the four and Convert goes away again."""
    case = case_named("zone_to_zone")
    fill_single(tab, case)
    assert tab.convert_button.isEnabled() is True

    # From zone.
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(UNCHOSEN))
    assert tab.convert_button.isEnabled() is False
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(case.source))
    assert tab.convert_button.isEnabled() is True

    # To zone.
    tab.to_zone.setCurrentIndex(tab.to_zone.findData(UNCHOSEN))
    assert tab.convert_button.isEnabled() is False
    tab.to_zone.setCurrentIndex(tab.to_zone.findData(case.target))
    assert tab.convert_button.isEnabled() is True

    # The first coordinate. Whitespace alone is not an answer.
    tab.first_edit.setText("   ")
    assert tab.convert_button.isEnabled() is False
    tab.first_edit.setText(case.first)
    assert tab.convert_button.isEnabled() is True

    # The second coordinate.
    tab.second_edit.setText("")
    assert tab.convert_button.isEnabled() is False
    tab.second_edit.setText(case.second)
    assert tab.convert_button.isEnabled() is True


def test_convert_is_enabled_with_the_elevation_blank(tab):
    """A blank elevation is the file reader's own "not recorded".

    Refusing to convert without one would invent a requirement the format does
    not have (michspc/fileio/pnezd.py, _ABSENT_ELEVATION_TEXT).
    """
    fill_single(tab, case_named("zone_to_zone"))
    tab.elevation_edit.setText("")
    assert tab.convert_button.isEnabled() is True
    assert tab.convert() is True


# --------------------------------------------------------------------------
# Longitude sign convention
# --------------------------------------------------------------------------


def test_the_longitude_convention_opens_on_positive_west(tab):
    """The owner's convention, preselected (docs/DESIGN.md amendment #29).

    Both tabs get it from the same ``controls.longitude_combo``, so this is the
    same control the Multi point tab carries rather than a lookalike that could
    open on something else.
    """
    assert tab.longitude_combo.currentData() is LongitudeConvention.POSITIVE_WEST
    assert tab.longitude_convention() is LongitudeConvention.POSITIVE_WEST
    assert tab.longitude_combo.count() == len(LongitudeConvention)


@pytest.mark.parametrize(
    "case", [case_named("zone_to_geodetic"), case_named("geodetic_to_zone")], ids=lambda c: c.name
)
def test_a_geodetic_direction_runs_on_the_preselected_convention(tab, case):
    """Neither geodetic direction waits for the convention any more - and both
    still follow it when it is changed.

    The second half is the anti-vacuousness: a preselected value that stopped
    reaching the settings would satisfy every assertion about what the dropdown
    shows while the conversion quietly used something else.
    """
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(case.source))
    tab.to_zone.setCurrentIndex(tab.to_zone.findData(case.target))
    tab.first_edit.setText(case.first)
    tab.second_edit.setText(case.second)
    tab.elevation_edit.setText(case.elevation)

    assert tab.longitude_combo.isEnabled() is True
    assert tab.convert_button.isEnabled() is True
    assert (
        tab.settings().longitude_convention is LongitudeConvention.POSITIVE_WEST
    )

    tab.longitude_combo.setCurrentIndex(
        tab.longitude_combo.findData(LongitudeConvention.NEGATIVE_WEST)
    )
    assert (
        tab.settings().longitude_convention is LongitudeConvention.NEGATIVE_WEST
    )
    assert tab.convert_button.isEnabled() is True


def test_the_convention_is_irrelevant_for_a_zone_to_zone_job(tab):
    """No longitude is consulted, so the control is disabled and the settings
    state the absence rather than omitting it."""
    fill_single(tab, case_named("zone_to_zone"))

    assert tab.longitude_combo.isEnabled() is False
    assert tab.longitude_label.isEnabled() is False
    settings = tab.settings()
    assert settings is not None
    assert settings.direction is Direction.ZONE_TO_ZONE
    assert settings.longitude_convention is None


# --------------------------------------------------------------------------
# The entry labels follow the From selection
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, expected, fields_enabled",
    [
        (
            UNCHOSEN,
            (
                single_point_module.FIRST_LABEL_UNCHOSEN,
                single_point_module.SECOND_LABEL_UNCHOSEN,
            ),
            False,
        ),
        (
            GEODETIC,
            (
                single_point_module.FIRST_LABEL_GEODETIC,
                single_point_module.SECOND_LABEL_GEODETIC,
            ),
            True,
        ),
        *[
            (
                zone,
                (
                    single_point_module.FIRST_LABEL_ZONE,
                    single_point_module.SECOND_LABEL_ZONE,
                ),
                True,
            )
            for zone in ALL_ZONES
        ],
    ],
    ids=["unchosen", "geodetic", *[zone.abbrev for zone in ALL_ZONES]],
)
def test_the_entry_labels_follow_the_from_selection(
    tab, source, expected, fields_enabled
):
    """What the two typed values ARE is decided by the From selection alone.

    The coordinate fields are disabled only while it is unanswered: until then
    the program cannot say what a number typed there would mean. The elevation
    field is enabled in every state, because an elevation is an elevation in
    every direction.
    """
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(source))

    assert (tab.first_label.text(), tab.second_label.text()) == expected
    assert tab.first_edit.isEnabled() is fields_enabled
    assert tab.second_edit.isEnabled() is fields_enabled

    assert tab.elevation_label.text() == single_point_module.ELEVATION_LABEL
    assert tab.elevation_edit.isEnabled() is True


@pytest.mark.parametrize("target", [UNCHOSEN, GEODETIC, MI_SOUTH, MI_NORTH])
def test_the_entry_labels_ignore_the_to_selection(tab, target):
    """The To selection cannot change what the typed values are.

    A label that moved with it would be describing the wrong end of the job -
    the same rule MainWindow.input_hint_text follows.
    """
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(MI_CENTRAL))
    before = (tab.first_label.text(), tab.second_label.text())

    tab.to_zone.setCurrentIndex(tab.to_zone.findData(target))

    assert (tab.first_label.text(), tab.second_label.text()) == before
    assert before == (
        single_point_module.FIRST_LABEL_ZONE,
        single_point_module.SECOND_LABEL_ZONE,
    )


def test_the_unit_labels_say_what_each_selector_governs(tab):
    """"Units (elevation only):" on the side whose coordinates are degrees, and
    neither selector is ever disabled - it still governs the elevation."""
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(GEODETIC))
    tab.to_zone.setCurrentIndex(tab.to_zone.findData(MI_CENTRAL))

    assert tab.input_unit_label.text() == single_point_module.UNITS_LABEL_ELEVATION_ONLY
    assert tab.output_unit_label.text() == single_point_module.UNITS_LABEL
    assert tab.input_unit.isEnabled() is True
    assert tab.output_unit.isEnabled() is True

    # This tab writes its own tooltips: the multi-point wording names "the
    # input file's columns two and three", and a typed point has no file and no
    # columns.
    assert "file" not in tab.input_unit.toolTip()
    assert "file" not in tab.output_unit.toolTip()
    # The load-bearing sentence is carried over unchanged.
    assert "combined factor are computed from it" in tab.input_unit.toolTip()


# --------------------------------------------------------------------------
# THE ANTI-DIVERGENCE PIN
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", DIRECTION_CASES, ids=lambda c: c.name)
def test_the_two_tabs_cannot_disagree_about_the_same_point(
    window, tab, tmp_path, case
):
    """The same three numbers, typed and in a file, produce the same result.

    Bitwise, not approximately: it is the same function object applied to the
    same parsed row, so anything other than an exact match means the two tabs
    took different paths - which is the one thing this feature may not do
    (docs/DESIGN.md amendment #26).

    The file's single row carries pnezd.TYPED_POINT_ID as its point identifier
    and no description, which is exactly the line parse_typed_point builds, so
    the two rows are the same row.
    """
    job_file = tmp_path / "one-point.csv"
    job_file.write_text(
        f"{pnezd.TYPED_POINT_ID},{case.first},{case.second},{case.elevation}\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    fill_multi(window, case, input_path=job_file, output_directory=out_dir)
    if window.convert() is not True:
        raise AssertionError(f"the multi-point run failed: {window.shown_failures}")

    fill_single(tab, case)
    if tab.convert() is not True:
        raise AssertionError(f"the single-point run failed: {tab.shown_failures}")

    from_file = window.result.points[0]
    typed = tab.result.points[0]

    # The numbers, bitwise.
    assert typed.output_northing == from_file.output_northing
    assert typed.output_easting == from_file.output_easting
    assert typed.output_elevation == from_file.output_elevation
    assert typed.factors.grid_scale_factor == from_file.factors.grid_scale_factor
    assert typed.factors.combined_factor == from_file.factors.combined_factor

    # The warnings, byte for byte - including the "point 1" each message names.
    assert [w.message for w in typed.warnings] == [
        w.message for w in from_file.warnings
    ]
    assert [w.code for w in typed.warnings] == [w.code for w in from_file.warnings]

    # And the strings on screen: the single point's panel against the
    # multi-point table's own cells.
    if case.target == GEODETIC:
        # There is no target zone, so every factor describes the typed State
        # Plane point and sits under INPUT (results_model.single_point_sections).
        mapping = (
            (1, OUTPUT_TITLE, LATITUDE_LABEL),
            (2, OUTPUT_TITLE, LONGITUDE_LABEL),
            (3, OUTPUT_TITLE, ELEVATION_LABEL),
            (4, INPUT_TITLE, GRID_FACTOR_LABEL),
            (5, INPUT_TITLE, COMBINED_FACTOR_LABEL),
        )
    else:
        mapping = (
            (1, OUTPUT_TITLE, NORTHING_LABEL),
            (2, OUTPUT_TITLE, EASTING_LABEL),
            (3, OUTPUT_TITLE, ELEVATION_LABEL),
            (4, OUTPUT_TITLE, GRID_FACTOR_LABEL),
            (5, OUTPUT_TITLE, COMBINED_FACTOR_LABEL),
        )

    shown = dict(tab.displayed_rows())
    for column, title, label in mapping:
        in_table = cell(window, 0, column)
        assert as_the_file_writes_it(
            value_of(tab.sections, title, label)
        ) == as_the_file_writes_it(in_table)
        # ... and the panel is really showing it, not merely able to produce it.
        assert as_the_file_writes_it(shown[label]) == as_the_file_writes_it(in_table)

    # The point identifier the file row carried is the one the typed point was
    # given, which is what makes the two warning texts identical.
    assert cell(window, 0, 0) == pnezd.TYPED_POINT_ID


# --------------------------------------------------------------------------
# The optional elevation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("typed", ["", "0.00"], ids=["blank", "explicit_zero"])
def test_an_absent_elevation_reads_na_and_never_one_point_zero(tab, typed):
    """Blank and exactly-zero both mean "not recorded".

    The grid scale factor is still a real number - it depends only on position -
    while the elevation, elevation factor and combined factor all read N/A.
    Never 1.0, which would be a plausible wrong number on a sealed drawing
    (docs/DESIGN.md section 7).
    """
    fill_single(tab, case_named("zone_to_zone"))
    tab.elevation_edit.setText(typed)

    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")

    assert value_of(tab.sections, OUTPUT_TITLE, ELEVATION_LABEL) == fmt.NOT_AVAILABLE
    assert (
        value_of(tab.sections, OUTPUT_TITLE, ELEVATION_FACTOR_LABEL)
        == fmt.NOT_AVAILABLE
    )
    assert (
        value_of(tab.sections, OUTPUT_TITLE, COMBINED_FACTOR_LABEL)
        == fmt.NOT_AVAILABLE
    )

    grid_factor = value_of(tab.sections, OUTPUT_TITLE, GRID_FACTOR_LABEL)
    assert grid_factor != fmt.NOT_AVAILABLE
    assert grid_factor == fmt.factor(tab.result.points[0].factors.grid_scale_factor)


# --------------------------------------------------------------------------
# Refusals arrive intact
# --------------------------------------------------------------------------


def test_a_non_numeric_entry_surfaces_the_readers_own_message(tab):
    """The reader's sentence, verbatim, naming the typed source.

    The expected text is obtained by asking the reader itself to refuse the same
    three strings, so this compares the interface against the authority rather
    than against a copy of the wording that could rot.
    """
    case = case_named("zone_to_zone")
    with pytest.raises(pnezd.PnezdError) as raised:
        pnezd.parse_typed_point(
            "NORTHING?",
            case.second,
            case.elevation,
            source=pnezd.TYPED_POINT_SOURCE_GRID,
        )
    expected = str(raised.value)

    fill_single(tab, case)
    tab.first_edit.setText("NORTHING?")

    assert tab.convert() is False
    assert tab.shown_failures == [expected]
    assert str(tab.last_failure) == expected

    # It names the column layout the row was read as, so a surveyor who typed a
    # longitude is never told his "easting" is wrong ...
    assert pnezd.TYPED_POINT_SOURCE_GRID in expected
    assert "northing" in expected
    # ... and it names the offending text, which is the whole point of it.
    assert "NORTHING?" in expected
    # The placeholder is not a message. Nothing may reach the user reading
    # "<text>".
    assert "<text>" not in expected


def test_a_geodetic_refusal_names_the_geodetic_layout(tab):
    """The same row typed as latitude/longitude is refused as such."""
    case = case_named("geodetic_to_zone")
    fill_single(tab, case)
    tab.second_edit.setText("WEST?")

    assert tab.convert() is False
    message = str(tab.last_failure)
    assert pnezd.TYPED_POINT_SOURCE_GEODETIC in message
    assert pnezd.TYPED_POINT_SOURCE_GRID not in message


def test_a_refusal_clears_the_previous_result(tab):
    """A refusal after a good run leaves nothing of the good run behind.

    A stale panel beside a red status line would invite a surveyor to read the
    previous point's coordinates as though they were this one's.
    """
    fill_single(tab, case_named("zone_to_zone"))
    assert tab.convert() is True
    assert tab.sections is not None
    assert tab.value_labels != []
    assert tab.copy_all_button.isEnabled() is True

    tab.first_edit.setText("NOPE")
    assert tab.convert() is False

    assert tab.result is None
    assert tab.sections is None
    assert tab.value_labels == []
    assert tab.copy_buttons == []
    assert tab.displayed_rows() == ()
    assert tab.copy_all_button.isEnabled() is False

    # Red = actually wrong (docs/method/METHOD.md section 5), and the whole
    # message is in the tooltip because the status line is one line.
    message = str(tab.last_failure)
    assert tab.status_label.styleSheet() == single_point_module.RED
    assert message.splitlines()[0] in tab.status_label.text()
    assert tab.status_label.toolTip() == message


def test_a_refusal_is_shown_as_plain_text(tab):
    """QLabel guesses whether a string is HTML. This panel must not guess.

    Refusal messages quote back whatever was typed, and a typed value that the
    heuristic reads as a tag would be rendered as markup and vanish.
    """
    assert tab.status_label.textFormat() == Qt.TextFormat.PlainText

    fill_single(tab, case_named("zone_to_zone"))
    assert tab.convert() is True
    for label in tab.value_labels:
        assert label.textFormat() == Qt.TextFormat.PlainText
        assert label.wordWrap() is True
        assert (
            label.textInteractionFlags()
            & Qt.TextInteractionFlag.TextSelectableByMouse
        )


# --------------------------------------------------------------------------
# The tab writes nothing
# --------------------------------------------------------------------------


def test_the_single_point_tab_writes_nothing(tab, tmp_path, monkeypatch):
    """No file, no folder, no archive - a results display only.

    Watching a scratch directory the tab has no relationship to proves nothing:
    the closing review gate showed that seeding ``convert`` with
    ``Path("single-point.txt").write_text(...)`` left that test passing, because
    a bare relative path lands in the PROCESS WORKING DIRECTORY, which the test
    never looked at. So the working directory is moved into ``tmp_path`` for the
    duration and the whole tree is compared before and after - a relative write
    anywhere now lands inside the snapshot.
    """
    monkeypatch.chdir(tmp_path)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    fill_single(tab, case_named("zone_to_zone"))
    assert tab.convert() is True

    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before
    # Anti-vacuousness: the snapshot really would notice a file. Without this a
    # comparison of two empty lists would pass for the wrong reason.
    (tmp_path / "sentinel.txt").write_text("x", encoding="ascii")
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) != before

    settings = tab.result.settings
    assert settings.input_path is None
    assert settings.output_directory is None

    # And the export layer refuses to name a destination for it rather than
    # inventing one (michspc/fileio/exports.py, archive_path).
    with pytest.raises(exports.WriteError):
        exports.destination_paths(tab.result)


# --------------------------------------------------------------------------
# Copying
# --------------------------------------------------------------------------


def test_copy_all_is_disabled_until_a_conversion_succeeds(tab):
    assert tab.copy_all_button.isEnabled() is False
    assert tab.copy_all() is False
    assert tab.copied == []

    fill_single(tab, case_named("zone_to_zone"))
    assert tab.convert() is True
    assert tab.copy_all_button.isEnabled() is True


def test_copy_value_puts_exactly_that_value_on_the_clipboard(tab):
    """The value string alone: no label, no unit, no trailing newline.

    It is pasted straight into a CAD prompt, and anything else in the buffer
    has to be deleted there.
    """
    fill_single(tab, case_named("zone_to_zone"))
    assert tab.convert() is True

    rows = tab.displayed_rows()
    for index, (label, text) in enumerate(rows):
        tab.copied.clear()
        assert tab.copy_value(index) is True
        assert tab.copied == [text]
        # No label, and no trailing newline.
        if label not in text:
            assert label not in tab.copied[0]
        assert not tab.copied[0].endswith("\n")

    # One button per value, and each one copies its own row.
    assert len(tab.copy_buttons) == len(rows)


def test_copy_all_serialises_the_sections_the_panel_rendered(tab):
    """The same tuple, through results_model - so the screen and the clipboard
    cannot diverge structurally."""
    fill_single(tab, case_named("zone_to_zone"))
    assert tab.convert() is True

    tab.copied.clear()
    assert tab.copy_all() is True
    assert tab.copied == [single_point_clipboard_text(tab.sections)]

    # Every displayed value is in it, spelled the same way.
    text = tab.copied[0]
    for label, value in tab.displayed_rows():
        assert f"{label}\t{value}" in text


def test_the_clipboard_seam_really_reaches_the_clipboard(window, tab):
    """The recorder used above stands in for a real QClipboard, so prove once
    that the un-overridden method reaches one."""
    del tab._set_clipboard  # restore the class's own implementation

    fill_single(tab, case_named("zone_to_zone"))
    assert tab.convert() is True

    assert tab.copy_all() is True
    assert QGuiApplication.clipboard().text() == single_point_clipboard_text(
        tab.sections
    )

    assert tab.copy_value(0) is True
    assert QGuiApplication.clipboard().text() == tab.displayed_rows()[0][1]


# --------------------------------------------------------------------------
# Success reporting
# --------------------------------------------------------------------------


def test_a_clean_run_is_reported_without_colour(tab):
    fill_single(tab, case_named("zone_to_zone"))
    assert tab.convert() is True

    assert tab.result is not None
    assert tab.result.warnings == ()
    assert tab.status_label.text() == tab.status_text(tab.result)
    assert tab.status_label.styleSheet() == ""
    assert tab.status_label.toolTip() == ""


def test_a_warned_run_is_amber_and_carries_the_message(tab):
    """Amber = "look at this", and the warning's own sentence is in the tooltip
    as well as in the panel's Warnings row."""
    fill_single(tab, case_named("zone_to_zone_warned"))
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")

    assert tab.result.warnings != ()
    assert tab.status_label.styleSheet() == single_point_module.AMBER

    first_message = tab.result.warnings[0][1].message
    assert first_message in tab.status_label.toolTip()

    # The tooltip must NOT prefix the identifier a second time. The core's
    # message already opens "point 1: ...", and the closing review gate found
    # the tooltip rendering it as "1: point 1: ..." (docs/DESIGN.md #26).
    assert not tab.status_label.toolTip().startswith(pnezd.TYPED_POINT_ID + ":")

    # The warnings FIELD - beneath the results, full width (#30) - drops the
    # fabricated identifier entirely, this tab having no point numbers, so it
    # carries the message's SUBSTANCE rather than the message verbatim.
    shown = tab.warnings_label.text()
    assert f"point {pnezd.TYPED_POINT_ID}" not in shown
    assert first_message.split(": ", 1)[1] in shown

    # And it is not in the panel or on the clipboard.
    assert "Warnings" not in dict(tab.displayed_rows())
    tab.copied.clear()
    assert tab.copy_all() is True
    assert first_message.split(": ", 1)[1] not in tab.copied[0]


def test_the_unit_selection_reaches_the_settings(tab):
    """The dropdowns are what the job is built from, with no default injected
    between them and JobSettings."""
    fill_single(tab, case_named("zone_to_zone"))
    settings = tab.settings()
    assert settings.input_unit is tab.input_unit.currentData()
    assert settings.output_unit is tab.output_unit.currentData()
    assert settings.input_unit is INTERNATIONAL_FEET


# ==========================================================================
# Result invalidation.
#
# The closing review gate's CRITICAL finding. Editing any control after a
# conversion left the previous point's answer on the screen, still captioned
# "Converted", with both copy paths live - so a surveyor who changed a northing
# and did not press Convert could copy the PREVIOUS point's coordinate into
# CAD. The reviewer's counterexample is reproduced verbatim below.
# ==========================================================================


def test_editing_a_coordinate_discards_the_result_it_no_longer_describes(tab):
    """The reviewer's own counterexample, reproduced.

    Michigan Central to Michigan South, international feet both ends:
    N=176,200.000 E=19,685,000.000 Z=812.40 converts to N=838,214.295. Editing
    the northing to 276,200.000 without pressing Convert left 838,214.295 on
    screen, while the point now in the controls converts to 938,215.332 - a
    stale reading 100,001.037 ft out, and directly copyable.
    """
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(MI_CENTRAL))
    tab.to_zone.setCurrentIndex(tab.to_zone.findData(MI_SOUTH))
    tab.first_edit.setText("176200.000")
    tab.second_edit.setText("19685000.000")
    tab.elevation_edit.setText("812.40")
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")

    # Anti-vacuousness: the stale value really was on screen to begin with.
    before = value_of(tab.sections, OUTPUT_TITLE, "Northing")
    assert before == "838214.295"

    tab.first_edit.setText("276200.000")

    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False
    assert tab.status_label.text() == single_point_module.STATUS_INPUT_CHANGED

    # And converting again gives the point the controls now describe.
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")
    assert value_of(tab.sections, OUTPUT_TITLE, "Northing") == "938215.332"


@pytest.mark.parametrize(
    "control",
    ["first_edit", "second_edit", "elevation_edit"],
)
def test_every_entry_field_discards_the_result(tab, control):
    """Including the elevation, which does not gate Convert but does change the
    answer: it drives the elevation and combined factors."""
    fill_single(tab, case_named("zone_to_zone"))
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")
    assert tab.result is not None

    edit = getattr(tab, control)
    edit.setText(edit.text() + "1")

    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False


@pytest.mark.parametrize(
    "control, data",
    [
        ("to_zone", MI_NORTH),
        ("input_unit", METERS),
        ("output_unit", METERS),
    ],
)
def test_every_selection_discards_the_result(tab, control, data):
    """A zone or unit change makes the displayed numbers describe a job nobody
    asked for. The unit combos had no handler at all before this fix, so a
    feet-to-metres change left the previous unit's numbers under the new
    unit's label."""
    fill_single(tab, case_named("zone_to_zone"))
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")
    assert tab.result is not None

    combo = getattr(tab, control)
    index = combo.findData(data)
    assert index >= 0, f"{control} has no entry for {data!r}"
    combo.setCurrentIndex(index)

    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False


def test_the_copy_tooltip_says_which_section_the_value_came_from(tab):
    """Both sections carry a row called "Northing" in a zone-to-zone job.

    Two identical-looking Copy buttons beside two identically-named rows is a
    direct route to pasting an unconverted number as the converted coordinate
    (closing review gate). The tooltip names the section.
    """
    fill_single(tab, case_named("zone_to_zone"))
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")

    rows = tab.panel.displayed_rows()
    tooltips = [button.toolTip() for button in tab.panel.copy_buttons]

    northings = [i for i, (label, _text) in enumerate(rows) if label == "Northing"]
    # Anti-vacuousness: there really are two of them, which is the problem.
    assert len(northings) == 2

    assert INPUT_TITLE in tooltips[northings[0]]
    assert OUTPUT_TITLE in tooltips[northings[1]]


@pytest.mark.parametrize("case", DIRECTION_CASES, ids=lambda c: c.name)
def test_the_panel_agrees_with_the_audit_csv_the_other_tab_wrote(
    window, tab, tmp_path, case, read_member
):
    """The strongest form of the anti-divergence claim.

    The pin above compares the panel against the multi-point TABLE, which holds
    only seven columns. The quantities a surveyor is most likely to transcribe
    by hand - convergence, geoid height, ellipsoid height, the elevation factor
    - appear in neither the table nor that comparison, and the closing review
    gate noted the gap: a single-point-only defect in any of them would pass.

    The audit CSV inside the archive the multi-point run actually wrote is the
    file of record for those values, so this compares against it. Screen against
    file, not screen against screen.
    """
    job_file = tmp_path / "one-point.csv"
    job_file.write_text(
        f"{pnezd.TYPED_POINT_ID},{case.first},{case.second},{case.elevation}\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    fill_multi(window, case, input_path=job_file, output_directory=out_dir)
    if window.convert() is not True:
        raise AssertionError(f"the multi-point run failed: {window.shown_failures}")

    fill_single(tab, case)
    if tab.convert() is not True:
        raise AssertionError(f"the single-point run failed: {tab.shown_failures}")

    audit_name = exports.member_names(window.result)["audit"]
    text = read_member(window.written_files["archive"], audit_name)
    # splitlines(): csv.reader over a bare string iterates CHARACTERS, which
    # yields a header of single letters and a KeyError that looks like a
    # missing column rather than a mis-read file.
    rows = list(csv.reader(text.splitlines()))
    header, values = rows[0], rows[1]
    audit = dict(zip(header, values))

    # Every quantity the audit CSV and the panel both carry, by the audit's own
    # column name. The panel's section differs by direction, so each is looked
    # up in whichever section holds it.
    shown = {
        label: text for section in tab.sections for label, text in [(v.label, v.text) for v in section.values]
    }
    for column, label in (
        ("Geoid height (m)", "Geoid height (m)"),
        ("Ellipsoid height (m)", "Ellipsoid height (m)"),
        ("Elevation factor", "Elevation factor"),
        ("Combined factor", "Combined factor"),
        ("Latitude", "Latitude"),
    ):
        assert label in shown, f"the panel has no {label!r} row"
        assert as_the_file_writes_it(shown[label]) == as_the_file_writes_it(
            audit[column]
        ), f"{label}: panel {shown[label]!r} != audit CSV {audit[column]!r}"

    # Convergence: the audit names the target one "Convergence" and the source
    # one "Source convergence"; the panel shows whichever describes the end the
    # layout puts it under - and shows it in symbol notation, which normalises
    # to the audit's space-separated form.
    assert as_the_file_writes_it(shown["Convergence"]) in (
        as_the_file_writes_it(audit["Convergence"]),
        as_the_file_writes_it(audit["Source convergence"]),
    )

    # The warnings are no longer a panel row at all (#30); the field beneath the
    # panel is where they are. Compared against the multi-point run's own
    # warning objects rather than the audit CSV's Warnings column, which
    # carries the compressed CODES ("easting-unlike-selected-zone") because a
    # spreadsheet cell has no room for the sentences. The single-point field
    # has the room and shows the sentences, which is the whole reason it
    # exists - so the messages are what the two surfaces must agree about.
    assert "Warnings" not in shown

    field = tab.warnings_label.text()
    for _point_id, warning in window.result.warnings:
        # Each message opens "point <id>: "; the field drops that prefix
        # because this tab has no point numbers.
        assert warning.message.split(": ", 1)[1] in field

    if not window.result.warnings:
        assert field == results_model.NO_WARNINGS


# --------------------------------------------------------------------------
# The panel reads in two columns, INPUT on the left
# --------------------------------------------------------------------------
#
# docs/DESIGN.md amendment #27. These tests measure REAL widget geometry, which
# means the window has to be shown and the event loop has to have laid it out -
# an unshown widget reports zeroes and every comparison below would pass
# vacuously. `laid_out` does that, and `test_the_measurements_are_real` proves
# it worked before the others rely on it.


def laid_out(window, tab, case, width=1100, height=780):
    """Convert `case` on a shown, laid-out window and return the panel."""
    window.resize(width, height)
    window.show()
    fill_single(tab, case)
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")
    QGuiApplication.processEvents()
    return tab.panel


def left_edge(widget, panel) -> int:
    """A widget's x, in the panel container's own coordinates."""
    return widget.mapTo(panel.container, widget.rect().topLeft()).x()


def test_the_measurements_are_real(window, tab):
    """Anti-vacuousness for every geometry test below.

    An unshown Qt widget reports a zero-sized rectangle at the origin, so every
    "left of" comparison in this section would hold for two widgets that were
    never laid out at all.
    """
    panel = laid_out(window, tab, case_named("zone_to_zone"))

    assert panel.width() > 100
    assert panel.left_column.width() > 100
    assert panel.right_column.width() > 100
    assert {left_edge(label, panel) for label in panel.value_labels} != {0}


@pytest.mark.parametrize("case", DIRECTION_CASES, ids=lambda c: c.name)
def test_the_result_reads_in_two_columns_with_input_on_the_left(window, tab, case):
    """INPUT left, OUTPUT right, in every direction.

    The single stacked column this replaced put the converted coordinate below
    the fold on a laptop screen: reading the answer meant scrolling away from
    the typed point, which are the two numbers a surveyor most wants to compare.

    Checked in all three directions because the sections differ by direction -
    a State-Plane-to-geodetic job carries every factor under INPUT - and a
    layout rule that holds in one direction only is not a layout rule.
    """
    panel = laid_out(window, tab, case)

    assert [section.title for section in panel.sections] == [INPUT_TITLE, OUTPUT_TITLE]

    input_count = len(panel.sections[0].values)
    input_rows = panel.value_labels[:input_count]
    output_rows = panel.value_labels[input_count:]

    # Anti-vacuousness: both sides really have rows in them.
    assert input_rows and output_rows

    rightmost_input = max(left_edge(label, panel) for label in input_rows)
    leftmost_output = min(left_edge(label, panel) for label in output_rows)
    assert rightmost_input < leftmost_output

    # And the split is the columns' doing, not an accident of row widths.
    assert panel.left_column.geometry().right() <= panel.right_column.geometry().left()


def test_a_vertical_rule_separates_the_two_columns(window, tab):
    """A clean bar, actually drawn, actually between them.

    ``QFrame.VLine`` with Qt's default Sunken shadow draws the etched two-tone
    groove of a 1990s dialog. This one is Plain, and it is checked by grabbing
    it: a frame with no line width would sit in the layout, pass every geometry
    assertion here, and paint nothing.
    """
    panel = laid_out(window, tab, case_named("zone_to_zone"))
    rule = panel.separator

    assert rule is not None
    assert rule.frameShape() == QFrame.Shape.VLine
    assert rule.frameShadow() == QFrame.Shadow.Plain

    # Between the columns, horizontally.
    assert panel.left_column.geometry().right() <= left_edge(rule, panel)
    assert left_edge(rule, panel) <= panel.right_column.geometry().left()

    # Tall enough to read as a divider rather than a tick.
    assert rule.height() > 100

    # And it paints: every pixel of the grab is opaque.
    shot = rule.grab().toImage()
    painted = sum(
        1
        for y in range(shot.height())
        for x in range(shot.width())
        if shot.pixelColor(x, y).alpha() > 0
    )
    assert painted == shot.width() * shot.height()


def test_an_empty_panel_has_no_columns_and_no_rule(window, tab):
    """Nothing converted, nothing drawn.

    An empty panel with a bar down the middle of it is furniture describing a
    result that does not exist - and this panel is emptied by every control
    change, not only at startup (``_invalidate_result``).
    """
    panel = tab.panel
    assert panel.sections is None
    assert panel.separator is None
    assert panel.left_column is None
    assert panel.right_column is None

    laid_out(window, tab, case_named("zone_to_zone"))
    assert tab.panel.separator is not None

    tab.first_edit.setText("176201.000")
    assert tab.panel.sections is None
    assert tab.panel.separator is None
    assert tab.panel.left_column is None


def test_each_copy_button_sits_beside_its_own_value(window, tab):
    """Not pinned to the far right of the panel, an inch of blank away.

    It was in a grid column of its own, so every button landed at the right
    edge of the widest value in the panel and a row of identical buttons stood
    in a line with nothing to say which number each belonged to.
    """
    panel = laid_out(window, tab, case_named("zone_to_zone"))
    rows = panel.displayed_rows()

    for index, (label, text) in enumerate(rows):
        value = panel.value_labels[index]
        button = panel.copy_buttons[index]

        # Measured from where the TEXT ends, not from where the label widget
        # ends. Those are the same thing only when the label is not stretched -
        # and a label given stretch inside its cell puts the button back at the
        # far right with the gap between widget and button still reading zero,
        # which is the defect this test failed to see the first time it was
        # written. The Warnings row wraps to a paragraph, so its text width is
        # not a single advance and it is measured the widget way.
        wrapped = value.height() > value.fontMetrics().height() * 1.5
        if wrapped:
            text_ends = left_edge(value, panel) + value.width()
        else:
            text_ends = left_edge(value, panel) + value.fontMetrics().horizontalAdvance(
                text
            )

        gap = left_edge(button, panel) - text_ends
        assert 0 <= gap <= 24, (
            f"row {index} ({label} = {text!r}): the copy button is {gap} px from "
            f"the end of its value"
        )

    # And the coordinate rows' buttons are nowhere near the panel's right edge,
    # which is where they used to be. The Warnings row is excluded on purpose:
    # its value is a paragraph, so its own right end IS near the edge.
    coordinates = [
        index for index, (label, _text) in enumerate(rows)
        if label in (NORTHING_LABEL, EASTING_LABEL, ELEVATION_LABEL)
    ]
    assert coordinates  # anti-vacuousness
    for index in coordinates:
        button = panel.copy_buttons[index]
        assert left_edge(button, panel) < panel.width() - 100


def test_the_copy_button_wears_the_glyph_and_still_names_itself(window, tab):
    """The Windows 11 two-sheet symbol, in place of the word "Copy".

    A glyph with no accessible name is a button with no name at all to anything
    that is not a pair of eyes, and the tooltip is what the closing review gate
    asked for when it found two identical buttons beside two rows both called
    "Northing" - which matters more now that the caption is a picture.
    """
    panel = laid_out(window, tab, case_named("zone_to_zone"))

    for button in panel.copy_buttons:
        assert button.icon().isNull() is False
        assert button.text() == ""
        assert button.accessibleName() == "Copy"
        assert button.toolTip().startswith("Copy the ")

    rows = panel.displayed_rows()
    northings = [i for i, (label, _t) in enumerate(rows) if label == NORTHING_LABEL]
    assert len(northings) == 2
    assert INPUT_TITLE in panel.copy_buttons[northings[0]].toolTip()
    assert OUTPUT_TITLE in panel.copy_buttons[northings[1]].toolTip()


def test_the_columns_did_not_reorder_what_an_index_means(window, tab):
    """The split is visual only.

    ``copy_value(index)``, ``value_labels[index]`` and ``displayed_rows()[index]``
    all have to keep meaning the same row, or a copy button in the right-hand
    column copies a left-hand column value - which is precisely the stale-value
    failure the closing gate found by another road (amendment #26).
    """
    panel = laid_out(window, tab, case_named("zone_to_zone"))
    rows = panel.displayed_rows()

    flattened = [
        (value.label, value.text)
        for section in panel.sections
        for value in section.values
    ]
    assert list(rows) == flattened

    for index, (_label, text) in enumerate(rows):
        tab.copied.clear()
        panel.copy_buttons[index].click()
        assert tab.copied == [text], f"row {index} copied the wrong value"


def test_no_panel_value_wraps_at_all(window, tab):
    """A zone name broken across two lines is a defect, not a cosmetic quibble.

    ``QLabel`` with word wrap takes the width its own sizeHint heuristic picks,
    which is narrower than the text - so "Michigan Central 2112" arrived as
    "Michigan Central" over "2112" with the copy button beside the first half,
    in a column with two inches of unused space to its right.

    Since #30 there is no exception. Every panel value is a coordinate, a
    factor or a zone name; the one that was a paragraph - Warnings - now has a
    full-width field of its own, which is where a paragraph belongs and is
    why the owner moved it.
    """
    panel = laid_out(window, tab, case_named("zone_to_zone_warned"))
    rows = panel.displayed_rows()

    one_line = panel.value_labels[0].fontMetrics().height() * 1.5
    wrapped = [
        label
        for (label, _text), value in zip(rows, panel.value_labels)
        if value.height() > one_line
    ]
    assert wrapped == [], f"these values wrapped: {wrapped}"

    # Anti-vacuousness: this case really does carry a warning, so the paragraph
    # that used to wrap in here exists - it is just somewhere else now.
    assert "Warnings" not in [label for label, _text in rows]
    assert tab.warnings_label.text() != single_point_module.NO_RESULT_WARNINGS
    assert len(tab.warnings_label.text()) > 80


# --------------------------------------------------------------------------
# Degrees / minutes / seconds entry
# --------------------------------------------------------------------------
#
# docs/DESIGN.md amendment #28. The property that matters is that this is an
# ENTRY mode and nothing else: the same point typed either way must convert to
# the same coordinate, because a second way of reading a latitude is a second
# thing that can be wrong about one.

# 43.800 N and -84.367 W as degrees, minutes and seconds. Hand-derived from the
# decimal values the cases above already use:
#
#   0.800 deg x 60 = 48.000 min exactly            -> 43 deg 48 min 00.00000 sec
#   0.367 deg x 60 = 22.02 min; 0.02 x 60 = 1.2 s  -> 84 deg 22 min 01.20000 sec
#
# So the two spellings name one point, and every comparison below rests on that
# arithmetic rather than on the program agreeing with itself.
LATITUDE_DMS = ("43", "48", "00.00000", "N")
LONGITUDE_DMS = ("84", "22", "01.20000", "W")


def fill_dms(entry, components):
    degrees, minutes, seconds, hemisphere = components
    entry.degrees.setText(degrees)
    entry.minutes.setText(minutes)
    entry.seconds.setText(seconds)
    entry.hemisphere.setCurrentIndex(entry.hemisphere.findData(hemisphere))


def set_up_dms_job(tab, target=MI_CENTRAL, convention=LongitudeConvention.NEGATIVE_WEST):
    """A geodetic-to-zone job with the two angles typed in DMS."""
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(GEODETIC))
    tab.to_zone.setCurrentIndex(tab.to_zone.findData(target))
    tab.longitude_combo.setCurrentIndex(tab.longitude_combo.findData(convention))
    tab.angle_format.setCurrentIndex(
        tab.angle_format.findData(single_point_module.DMS_PAGE)
    )
    fill_dms(tab.first_dms, LATITUDE_DMS)
    fill_dms(tab.second_dms, LONGITUDE_DMS)
    tab.elevation_edit.setText(CENTRAL_ELEVATION)


def output_rows(tab):
    """Just the OUTPUT section, as (label, value) pairs."""
    count = len(tab.sections[0].values)
    return tab.displayed_rows()[count:]


def test_decimal_degrees_is_what_the_tab_opens_on(tab):
    """A starting state, not a silent default.

    Almost nothing in this program has a default, so this is worth saying: the
    two zone dropdowns and the longitude convention open unanswered because
    their options are indistinguishable from what is on screen. These two are
    not - the boxes visibly change shape - so nothing is being assumed about a
    value the user did not state.
    """
    assert tab.angle_format.currentData() == single_point_module.DECIMAL_PAGE
    assert tab.entering_dms() is False
    assert tab.first_stack.currentIndex() == single_point_module.DECIMAL_PAGE
    assert tab.second_stack.currentIndex() == single_point_module.DECIMAL_PAGE


def test_the_format_selector_is_dead_while_the_job_starts_from_a_zone(tab):
    """A northing has no minutes.

    The selector follows the FROM selection alone, exactly as the entry labels
    do and for the same reason: the To selection cannot change what the typed
    values ARE.
    """
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(MI_CENTRAL))
    assert tab.angle_format.isEnabled() is False
    assert tab.angle_format_label.isEnabled() is False

    # Even set to DMS, a zone source keeps the decimal boxes: entering_dms()
    # requires both, so the dropdown cannot strand a northing in a degrees box.
    tab.angle_format.setCurrentIndex(
        tab.angle_format.findData(single_point_module.DMS_PAGE)
    )
    assert tab.entering_dms() is False
    assert tab.first_stack.currentIndex() == single_point_module.DECIMAL_PAGE

    tab.from_zone.setCurrentIndex(tab.from_zone.findData(GEODETIC))
    assert tab.angle_format.isEnabled() is True
    assert tab.entering_dms() is True
    assert tab.first_stack.currentIndex() == single_point_module.DMS_PAGE


def test_the_dms_row_has_four_boxes_with_the_symbols_already_in_place(tab):
    """The owner's shape: type the numbers, not the punctuation."""
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(GEODETIC))
    tab.angle_format.setCurrentIndex(
        tab.angle_format.findData(single_point_module.DMS_PAGE)
    )

    for entry, letters in (
        (tab.first_dms, ("N", "S")),
        (tab.second_dms, ("E", "W")),
    ):
        symbols = [
            child.text()
            for child in entry.findChildren(QLabel)
        ]
        assert symbols == ["°", "'", '"']

        # Both letters, and no third "not yet" entry.
        offered = [
            entry.hemisphere.itemData(i) for i in range(entry.hemisphere.count())
        ]
        assert tuple(offered) == letters


def test_convert_waits_for_every_typed_box(tab):
    """Any of the six typed boxes left empty holds Convert.

    The hemisphere is not among them and does not need to be: it opens on a
    real letter and has no empty state, so there is nothing to wait for.
    """
    set_up_dms_job(tab)
    assert tab.convert_button.isEnabled() is True

    for clear, restore in (
        (lambda: tab.first_dms.degrees.setText(""),
         lambda: tab.first_dms.degrees.setText(LATITUDE_DMS[0])),
        (lambda: tab.first_dms.minutes.setText(""),
         lambda: tab.first_dms.minutes.setText(LATITUDE_DMS[1])),
        (lambda: tab.first_dms.seconds.setText(""),
         lambda: tab.first_dms.seconds.setText(LATITUDE_DMS[2])),
        (lambda: tab.second_dms.degrees.setText(""),
         lambda: tab.second_dms.degrees.setText(LONGITUDE_DMS[0])),
        (lambda: tab.second_dms.minutes.setText(""),
         lambda: tab.second_dms.minutes.setText(LONGITUDE_DMS[1])),
        (lambda: tab.second_dms.seconds.setText(""),
         lambda: tab.second_dms.seconds.setText(LONGITUDE_DMS[2])),
    ):
        clear()
        assert tab.convert_button.isEnabled() is False
        restore()
        assert tab.convert_button.isEnabled() is True


def test_the_same_point_converts_the_same_typed_either_way(window, tab):
    """The load-bearing pin of this feature.

    43 deg 48 min 00 sec N is 43.800 and 84 deg 22 min 01.2 sec W is -84.367 -
    derived above from the arithmetic, not from this program. Typing the point
    each way must therefore produce the same converted coordinate, to the last
    displayed digit. A DMS-specific route through the conversion would be a
    second way of converting a latitude, and two ways of doing one thing is
    exactly how the two TABS would come to disagree (amendment #26).
    """
    set_up_dms_job(tab)
    if tab.convert() is not True:
        raise AssertionError(f"the DMS run failed: {tab.shown_failures}")
    from_dms = output_rows(tab)

    # The identical job, typed as decimal degrees.
    tab.angle_format.setCurrentIndex(
        tab.angle_format.findData(single_point_module.DECIMAL_PAGE)
    )
    tab.first_edit.setText(CENTRAL_LATITUDE)
    tab.second_edit.setText(CENTRAL_LONGITUDE)
    if tab.convert() is not True:
        raise AssertionError(f"the decimal run failed: {tab.shown_failures}")
    from_decimal = output_rows(tab)

    assert from_dms == from_decimal
    # Anti-vacuousness: there is a real converted coordinate in there.
    labels = [label for label, _text in from_dms]
    assert NORTHING_LABEL in labels and EASTING_LABEL in labels


def test_a_dms_entry_means_the_same_point_under_both_conventions(window, tab):
    """The hemisphere letter fixes the position; the convention only spells it.

    ``formatting.longitude_dms`` records why a DMS longitude is
    convention-independent: the magnitude is the same number under both, and
    the letter is a fact about the point rather than about how a file writes
    its signs. So the two conventions must give ONE converted coordinate here -
    where the same DECIMAL longitude gives two, 340 miles apart. That contrast
    is the whole reason the convention selector exists, and both halves of it
    are checked.
    """
    set_up_dms_job(tab, convention=LongitudeConvention.NEGATIVE_WEST)
    assert tab.convert() is True
    negative_west = output_rows(tab)

    set_up_dms_job(tab, convention=LongitudeConvention.POSITIVE_WEST)
    assert tab.convert() is True
    positive_west = output_rows(tab)

    assert negative_west == positive_west

    # And the contrast, on the decimal page: the SAME typed text is two
    # different points, which is what the selector is there to disambiguate.
    tab.angle_format.setCurrentIndex(
        tab.angle_format.findData(single_point_module.DECIMAL_PAGE)
    )
    tab.first_edit.setText(CENTRAL_LATITUDE)
    tab.second_edit.setText(CENTRAL_LONGITUDE)

    tab.longitude_combo.setCurrentIndex(
        tab.longitude_combo.findData(LongitudeConvention.NEGATIVE_WEST)
    )
    assert tab.convert() is True
    decimal_negative = output_rows(tab)

    tab.longitude_combo.setCurrentIndex(
        tab.longitude_combo.findData(LongitudeConvention.POSITIVE_WEST)
    )
    assert tab.convert() is True
    decimal_positive = output_rows(tab)

    assert decimal_negative != decimal_positive


def test_a_panel_reading_can_be_typed_straight_back_in(window, tab):
    """Screen and entry form are two views of one notation, not two notations.

    Converts a zone point to geodetic, reads the two DMS strings off the panel
    exactly as a surveyor would, types them back into the four-box entry, and
    converts back. The northing and easting must return to where they started.
    """
    fill_single(tab, case_named("zone_to_geodetic"))
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")

    shown = dict(tab.displayed_rows())
    latitude_text = shown["Latitude (DMS)"]
    longitude_text = shown["Longitude (DMS)"]

    def components(text):
        degrees, rest = text.split("°")
        minutes, rest = rest.split("'")
        return degrees, minutes, rest[:-2], rest[-1]

    set_up_dms_job(tab, target=MI_CENTRAL)
    fill_dms(tab.first_dms, components(latitude_text))
    fill_dms(tab.second_dms, components(longitude_text))
    tab.elevation_edit.setText(CENTRAL_ELEVATION)
    if tab.convert() is not True:
        raise AssertionError(f"the round trip failed: {tab.shown_failures}")

    returned = dict(output_rows(tab))
    # Five decimals of a second is about 0.3 mm, so the returned coordinate
    # agrees with the original to well under a millimetre. Compared as numbers
    # at that tolerance rather than as strings: the last displayed digit of a
    # foot is 0.001, and a 0.3 mm difference can still move it.
    assert float(returned[NORTHING_LABEL].replace(",", "")) == pytest.approx(
        float(CENTRAL_NORTHING), abs=0.005
    )
    assert float(returned[EASTING_LABEL].replace(",", "")) == pytest.approx(
        float(CENTRAL_EASTING), abs=0.005
    )


def test_an_unreadable_dms_box_refuses_by_name_and_clears_the_result(window, tab):
    """The refusal is fileio.dms's own sentence, shown exactly as raised."""
    set_up_dms_job(tab)
    assert tab.convert() is True
    assert tab.sections is not None

    tab.second_dms.minutes.setText("61")
    assert tab.convert() is False

    message = str(tab.last_failure)
    assert "60 minutes in a degree" in message
    assert "longitude" in message
    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False
    assert tab.status_label.styleSheet() == single_point_module.RED


def test_editing_any_dms_box_discards_a_displayed_result(window, tab):
    """The stale-value failure of amendment #26, on the new boxes.

    Every one of the eight new controls has to reach _invalidate_result, or a
    surveyor who corrected a seconds box and did not press Convert could copy
    the previous point's coordinate straight into CAD.
    """
    boxes = [
        tab.first_dms.degrees,
        tab.first_dms.minutes,
        tab.first_dms.seconds,
        tab.second_dms.degrees,
        tab.second_dms.minutes,
        tab.second_dms.seconds,
    ]
    for box in boxes:
        set_up_dms_job(tab)
        assert tab.convert() is True
        assert tab.sections is not None

        box.setText(box.text() + "0")
        assert tab.sections is None, f"{box} left a result on screen"
        assert tab.result is None

    # And the two hemisphere dropdowns, moved to their OTHER letter - which is
    # the only change either one can make, and the one that matters most: it
    # reflects the point across the equator or the meridian.
    for entry in (tab.first_dms, tab.second_dms):
        set_up_dms_job(tab)
        assert tab.convert() is True
        other = 1 - entry.hemisphere.currentIndex()
        entry.hemisphere.setCurrentIndex(other)
        assert tab.sections is None


def test_switching_the_entry_format_discards_a_displayed_result(window, tab):
    """The two pages hold different text, and nothing is translated between
    them - so what is on screen no longer describes what is in the boxes."""
    set_up_dms_job(tab)
    assert tab.convert() is True
    assert tab.sections is not None

    tab.angle_format.setCurrentIndex(
        tab.angle_format.findData(single_point_module.DECIMAL_PAGE)
    )
    assert tab.sections is None
    assert tab.result is None
    assert tab.status_label.text() == single_point_module.STATUS_INPUT_CHANGED


def test_the_two_pages_do_not_leak_into_each_other(tab):
    """Nothing is translated when the format switches, and nothing is cleared.

    Carrying a decimal 43.800 into a degrees box would read as 43 degrees flat
    - 48 minutes away - and clearing the abandoned page would lose work on a
    mis-click. The abandoned page simply stops gating Convert.
    """
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(GEODETIC))
    tab.to_zone.setCurrentIndex(tab.to_zone.findData(MI_CENTRAL))
    tab.longitude_combo.setCurrentIndex(
        tab.longitude_combo.findData(LongitudeConvention.NEGATIVE_WEST)
    )

    tab.first_edit.setText(CENTRAL_LATITUDE)
    tab.second_edit.setText(CENTRAL_LONGITUDE)
    assert tab.convert_button.isEnabled() is True

    tab.angle_format.setCurrentIndex(
        tab.angle_format.findData(single_point_module.DMS_PAGE)
    )
    # The decimal text survives untouched, and no digit of it appeared in a
    # degrees box.
    assert tab.first_edit.text() == CENTRAL_LATITUDE
    assert tab.first_dms.degrees.text() == ""
    # Convert now reads the DMS page, which is empty.
    assert tab.convert_button.isEnabled() is False


BUTTON_FRAME_ALLOWANCE = 4
"""How far a flat QToolButton may stand above the line of text beside it.

The button cannot shrink to the text height: Qt adds its own frame around the
icon, and pinning it flat would mean overriding that with a hard-coded box,
which renders cramped under a native Windows theme. So the pin below allows the
frame and nothing more - which is a real discriminator rather than a formality:
against the line of text the program is actually drawn in, the 14 px glyph this
replaced measures 22 px and fails it, and the 11 px one measures 19 and passes.
"""

SHIPPED_LINE_HEIGHT = 16
"""One line of the panel's text in the program as it ships: Segoe UI at 9 pt on
a 96 dpi Windows desktop. Nothing in michspc.gui sets a font, so every value
label is drawn in the system UI font.

**Stated here rather than measured from the label, and that is the opposite of
this file's usual rule.** The suite runs on the offscreen platform plugin, which
has no system font and no text rasteriser: it answers 12 px for EVERY family,
including Segoe UI asked for by name, where the Windows plugin answers 16 for
that same font. The button is unmoved by any of it - its height comes from the
style, 18 px offscreen and 19 on Windows.

Measured against offscreen's 12, the comparison below rejects the 11 px glyph
the owner asked for AND the 14 px one it replaced, so it stops telling them
apart. That is how it came to fail on a machine whose offscreen fallback (12)
differed from the one this pin was written on (14) - a red suite saying nothing
about the program (docs/DESIGN.md amendment #31). What the owner sees is decided
by the line height he sees, so that is what the button is measured against.
"""


def test_the_copy_button_does_not_tower_over_the_value_it_copies(window, tab):
    """The owner asked for a smaller glyph (docs/DESIGN.md amendment #28).

    Pinned as a relationship rather than as the number 11, which would only
    restate the constant. What he was after is a control that sits beside a
    coordinate without dominating it, and that is a comparison against the text.
    """
    panel = laid_out(window, tab, case_named("zone_to_zone"))

    # Without this the loop below is satisfied by a panel that drew no rows at
    # all, which is a pass that means nothing.
    assert panel.copy_buttons, "the panel laid out no copy buttons to measure"

    for value, button in zip(panel.value_labels, panel.copy_buttons):
        assert button.height() <= SHIPPED_LINE_HEIGHT + BUTTON_FRAME_ALLOWANCE, (
            f"the copy button is {button.height()} px against a "
            f"{SHIPPED_LINE_HEIGHT} px line of text"
        )
        # The glyph itself is smaller than a character, which is the part the
        # eye actually reads as the button's size.
        assert button.iconSize().height() < SHIPPED_LINE_HEIGHT
        # And it is beside a value, not beside nothing.
        assert value.text()


def test_the_coordinate_entry_carries_no_tooltips(tab):
    """The owner had all three removed (docs/DESIGN.md amendment #34).

    The longitude sign dropdown, the angle-format dropdown and both hemisphere
    letter boxes. Pinned rather than merely deleted for the reason #34 gives:
    every one of these explained a control that answers a question for the user,
    so the pressure to write the explanation back is real and will come from
    someone acting in good faith.

    The longitude assertion overlaps ``test_the_longitude_dropdown_has_no_tooltip``
    in the file-tab suite ON PURPOSE. One shared helper builds that control for
    both tabs, and a future change that gave the Single point tab its own
    control would slip past a pin that only ever looked at the other tab.
    """
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(GEODETIC))
    tab.angle_format.setCurrentIndex(
        tab.angle_format.findData(single_point_module.DMS_PAGE)
    )

    assert tab.longitude_combo.toolTip() == ""
    assert tab.angle_format.toolTip() == ""
    assert tab.first_dms.hemisphere.toolTip() == ""
    assert tab.second_dms.hemisphere.toolTip() == ""

    # The boxes still say what they are: this removed text, not meaning. The
    # letters are in the control, and the format dropdown still names both
    # formats - which is what the tooltips were explaining.
    assert tab.first_dms.hemisphere_letter() == "N"
    assert [
        tab.angle_format.itemText(position)
        for position in range(tab.angle_format.count())
    ] == [single_point_module.ANGLE_FORMAT_DECIMAL, single_point_module.ANGLE_FORMAT_DMS]


def test_the_hemisphere_opens_on_north_and_west(tab):
    """The owner's decision (docs/DESIGN.md amendment #28 note 3).

    It was built to open unanswered, on the house rule that nothing answers a
    question for the user. He judged the two extra clicks per conversion not
    worth it for data that is always N and W, and this is his tool.

    What makes it defensible where a longitude-convention default would not be:
    the answer is a visible token in the box before Convert is pressed, and it
    reads back in the result panel afterwards. It is a starting value, not a
    hidden assumption.
    """
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(GEODETIC))
    tab.angle_format.setCurrentIndex(
        tab.angle_format.findData(single_point_module.DMS_PAGE)
    )

    assert tab.first_dms.hemisphere_letter() == "N"
    assert tab.second_dms.hemisphere_letter() == "W"

    # There is no third "not yet" entry to fall back into.
    assert tab.first_dms.hemisphere.count() == 2
    assert tab.second_dms.hemisphere.count() == 2

    # A freshly cleared row is in the same state a freshly built one is.
    tab.first_dms.degrees.setText("43")
    tab.first_dms.hemisphere.setCurrentIndex(
        tab.first_dms.hemisphere.findData("S")
    )
    tab.first_dms.clear()
    assert tab.first_dms.degrees.text() == ""
    assert tab.first_dms.hemisphere_letter() == "N"


def test_the_preselected_hemisphere_is_still_a_live_control(window, tab):
    """Anti-vacuousness for the default: a preselect must not become a control
    that is set once and then ignored.

    43 deg 48 min N and 43 deg 48 min S are 6,000 miles apart, so if the letter
    still reaches the conversion the two runs cannot agree - and if it stopped
    reaching it, they would.
    """
    set_up_dms_job(tab)
    assert tab.first_dms.hemisphere_letter() == "N"
    assert tab.convert() is True
    northern = as_the_file_writes_it(dict(tab.displayed_rows())["Latitude"])

    tab.first_dms.hemisphere.setCurrentIndex(
        tab.first_dms.hemisphere.findData("S")
    )
    assert tab.convert() is True
    southern = as_the_file_writes_it(dict(tab.displayed_rows())["Latitude"])

    assert northern != southern
    assert float(southern) == pytest.approx(-float(northern), abs=1e-8)


# --------------------------------------------------------------------------
# Warnings in a field of their own; display punctuation
# --------------------------------------------------------------------------
#
# docs/DESIGN.md amendment #30.


def test_the_warnings_field_spans_the_full_width_beneath_the_panel(window, tab):
    """The owner's shape, measured rather than assumed.

    It was the last row of the right-hand column, where a paragraph sat in a
    column sized for coordinates. Full width is what a sentence needs, and
    "beneath the panel" is where it has to be for the numbers to stay together.
    """
    panel = laid_out(window, tab, case_named("zone_to_zone_warned"))
    field = tab.warnings_label

    # Beneath: the field's top is below the panel's bottom, in the tab's own
    # coordinates.
    panel_bottom = panel.mapTo(tab, panel.rect().bottomLeft()).y()
    field_top = field.mapTo(tab, field.rect().topLeft()).y()
    assert field_top > panel_bottom

    # Full width: wider than either results column, which is what it was
    # confined to before.
    assert field.width() > panel.left_column.width()
    assert field.width() > panel.right_column.width()


def test_the_warnings_field_has_no_copy_button_and_is_not_in_copy_all(window, tab):
    """Both halves of the owner's instruction.

    The clipboard carries the numbers that go into CAD or a spreadsheet. A
    two-paragraph warning dropped among them has to be deleted there, and it is
    not what a copy button is for on this tab.
    """
    laid_out(window, tab, case_named("zone_to_zone_warned"))
    text = tab.warnings_label.text()

    # Anti-vacuousness: there really is a warning to have been copied.
    assert text != results_model.NO_WARNINGS
    assert len(text) > 80

    # No copy button anywhere in the field's box.
    box = tab.warnings_label.parentWidget()
    assert box.findChildren(QToolButton) == []

    # One copy button per panel value and not one more - the field did not
    # bring one with it.
    assert len(tab.copy_buttons) == len(tab.displayed_rows())

    tab.copied.clear()
    assert tab.copy_all() is True
    assert text not in tab.copied[0]
    assert "Warnings" not in tab.copied[0]


def test_the_warnings_field_is_emptied_with_the_result(window, tab):
    """A field that outlived the numbers it described would be the stale-result
    failure of amendment #26 in a new place: "none" beside a blank panel reads
    as this point's answer.
    """
    assert tab.warnings_label.text() == single_point_module.NO_RESULT_WARNINGS

    set_up_dms_job(tab)
    assert tab.convert() is True
    assert tab.warnings_label.text() == results_model.NO_WARNINGS

    # A control change discards the result - and the warnings with it.
    tab.first_dms.degrees.setText("44")
    assert tab.sections is None
    assert tab.warnings_label.text() == single_point_module.NO_RESULT_WARNINGS

    # So does a refusal.
    fill_single(tab, case_named("zone_to_zone_warned"))
    assert tab.convert() is True
    assert tab.warnings_label.text() != single_point_module.NO_RESULT_WARNINGS
    tab.first_edit.setText("NOPE")
    assert tab.convert() is False
    assert tab.warnings_label.text() == single_point_module.NO_RESULT_WARNINGS


def test_the_decimal_latitude_and_longitude_carry_a_degree_symbol(window, tab):
    """The owner asked for it on the results (docs/DESIGN.md amendment #30).

    On the INPUT block, which is what he named, and on the OUTPUT block too:
    both are built by ``_geodetic_values``, and one section showing 43.8 while
    the other showed 43.8° would be two notations for one quantity on one
    screen.
    """
    fill_single(tab, case_named("geodetic_to_zone"))
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")

    # This direction puts the typed position under INPUT.
    shown = dict(tab.displayed_rows())
    assert shown["Latitude"].endswith(fmt.DEGREE_SYMBOL)
    assert shown["Longitude"].endswith(fmt.DEGREE_SYMBOL)

    # And the other direction, where the position is the OUTPUT.
    fill_single(tab, case_named("zone_to_geodetic"))
    assert tab.convert() is True
    shown = dict(tab.displayed_rows())
    assert shown["Latitude"].endswith(fmt.DEGREE_SYMBOL)
    assert shown["Longitude"].endswith(fmt.DEGREE_SYMBOL)

    # The symbol is punctuation on the file's own string, not a second way of
    # writing the number: strip it and the digits are the file's exactly.
    assert as_the_file_writes_it(shown["Latitude"]) == fmt.latitude(
        tab.result.points[0].conversion.latitude
    )


def test_the_degree_symbol_never_reaches_the_exported_file(
    window, tab, tmp_path, read_member
):
    """The reason the display formatter is separate, pinned as a property.

    ``formatting.latitude`` and ``longitude`` write the clean PNEZD export, and
    that file is read back by ``pnezd`` before the archive may take its name.
    ``float("43.80000000°")`` raises, so a symbol in the file formatter would
    not merely look wrong - every geodetic job would refuse to write, and the
    file that did survive would be one no CAD package could import.
    """
    job_file = tmp_path / "one-point.csv"
    job_file.write_text("1,176200.000,19685000.000,812.40,PT\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    window.input_edit.setText(str(job_file))
    window.output_edit.setText(str(out_dir))
    window.from_zone.setCurrentIndex(window.from_zone.findData(MI_CENTRAL))
    window.to_zone.setCurrentIndex(window.to_zone.findData(GEODETIC))
    window.longitude_combo.setCurrentIndex(
        window.longitude_combo.findData(LongitudeConvention.NEGATIVE_WEST)
    )
    if not window.convert():
        raise AssertionError(f"the run failed: {window.shown_failures}")

    archive = window.written_files["archive"]
    names = exports.member_names(window.result)
    for member in (names["pnezd"], names["audit"], names["report"]):
        text = read_member(archive, member)
        assert fmt.DEGREE_SYMBOL not in text, f"{member} carries a degree symbol"


def test_the_convergence_is_shown_in_symbol_notation(window, tab):
    """``-16°49'17.78"`` where the audit CSV writes ``-16 49 17.78``.

    The owner asked for DMS notation on screen. It is built on the same
    ``_dms_magnitude`` the latitude and longitude DMS rows use, so the three
    angles on this panel cannot come to punctuate themselves differently.
    """
    fill_single(tab, case_named("zone_to_zone"))
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")

    # The INPUT one specifically: a zone-to-zone job shows a Convergence row in
    # both sections, and dict() would silently keep only the second.
    shown = value_of(tab.sections, INPUT_TITLE, "Convergence")

    assert fmt.DEGREE_SYMBOL in shown
    assert "'" in shown
    assert shown.endswith('"')
    assert shown[0] in "+-"

    # The same angle the file formatter writes, in different punctuation - not
    # a differently computed one.
    convergence = tab.result.points[0].conversion.source_convergence
    assert as_the_file_writes_it(shown) == fmt.angle_dms(convergence)


def test_a_long_warning_is_not_clipped(window, tab):
    """The defect this field arrived with, found by looking at a warned run.

    A word-wrapped ``QLabel`` does not propagate its height-for-width out
    through a ``QGroupBox``'s layout: the box took the height of ONE line and
    the rest of the text was simply not drawn. Three warnings showed one
    sentence, with nothing on screen saying two more existed - which is the
    failure this program exists to refuse, in the one field whose whole job is
    to tell a surveyor something is wrong.

    The pin is the label's laid-out height against the height its own text
    needs at its own width. That is the question "is any of it cut off", asked
    of the widget rather than of the layout that was supposed to size it.
    """
    panel = laid_out(window, tab, case_named("zone_to_zone_warned"))
    label = tab.warnings_label

    # Anti-vacuousness: this really is a multi-warning run whose text is long
    # enough to need more than one line at this width.
    assert len(tab.result.warnings) >= 2
    assert label.heightForWidth(label.width()) > label.fontMetrics().height() * 2

    assert label.height() >= label.heightForWidth(label.width()), (
        f"the warnings label is {label.height()} px tall and its text needs "
        f"{label.heightForWidth(label.width())} px - the rest is cut off"
    )

    # The box itself stays bounded, so a wordy warning cannot push the
    # converted coordinates off the screen. What does not fit scrolls.
    assert tab.warnings_scroll.height() <= single_point_module.WARNINGS_MAX_HEIGHT
    assert panel.height() > tab.warnings_scroll.height()
