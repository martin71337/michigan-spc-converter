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

from michspc.fileio import exports, formatting as fmt, pnezd  # noqa: E402
from michspc.gui import single_point as single_point_module  # noqa: E402
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


def test_the_longitude_convention_has_no_default(tab):
    """It opens unanswered. The two are indistinguishable from the numbers."""
    assert tab.longitude_combo.currentData() == UNCHOSEN
    assert tab.longitude_convention() is None


@pytest.mark.parametrize(
    "case", [case_named("zone_to_geodetic"), case_named("geodetic_to_zone")], ids=lambda c: c.name
)
def test_a_geodetic_direction_is_gated_on_the_convention(tab, case):
    """Both geodetic directions refuse to enable Convert without it."""
    tab.from_zone.setCurrentIndex(tab.from_zone.findData(case.source))
    tab.to_zone.setCurrentIndex(tab.to_zone.findData(case.target))
    tab.first_edit.setText(case.first)
    tab.second_edit.setText(case.second)
    tab.elevation_edit.setText(case.elevation)

    assert tab.longitude_combo.isEnabled() is True
    assert tab.settings() is None
    assert tab.convert_button.isEnabled() is False

    tab.longitude_combo.setCurrentIndex(
        tab.longitude_combo.findData(case.convention)
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
        assert value_of(tab.sections, title, label) == cell(window, 0, column)
        # ... and the panel is really showing it, not merely able to produce it.
        assert shown[label] == cell(window, 0, column)

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

    # The panel's Warnings row drops the fabricated identifier entirely - this
    # tab has no point numbers - so it carries the message's SUBSTANCE rather
    # than the message verbatim.
    shown = value_of(tab.sections, OUTPUT_TITLE, "Warnings")
    assert f"point {pnezd.TYPED_POINT_ID}" not in shown
    assert first_message.split(": ", 1)[1] in shown


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
        assert shown[label] == audit[column], (
            f"{label}: panel {shown[label]!r} != audit CSV {audit[column]!r}"
        )

    # Convergence: the audit names the target one "Convergence" and the source
    # one "Source convergence"; the panel shows whichever describes the end the
    # layout puts it under.
    assert shown["Convergence"] in (audit["Convergence"], audit["Source convergence"])
