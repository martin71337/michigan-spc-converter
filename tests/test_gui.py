"""The interface, tested headless.

Two properties dominate this file.

**UI honesty.** Every string the results table shows must be the string
``michspc.fileio.formatting`` produced for the same value — not a similar
string, not a string that rounds the same way, the same string. So the
assertions compare against the formatter and against the file that was actually
written, never against a literal typed here. A literal would pass while the
screen and the report drifted apart, which is the exact failure the rule exists
to prevent (docs/method/METHOD.md section 5).

**Refusals arrive intact.** The messages this program's layers raise name the
offending point and say what to do. The interface must show them verbatim, so
the test compares the surfaced text with the text the reader itself raises for
the same file.

Every expected value below is derived in the comment above it
(docs/method/METHOD.md section 4).
"""

from __future__ import annotations

import os

# MUST precede any Qt import: the platform plugin is chosen at import time and a
# later change is ignored, leaving the run needing a display it does not have
# (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from michspc.fileio import exports, formatting as fmt, pnezd  # noqa: E402
from michspc.gui import results_model  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.window import GEODETIC, UNCHOSEN, MainWindow  # noqa: E402
from michspc.spc.units import (  # noqa: E402
    ALL_UNITS,
    INTERNATIONAL_FEET,
    METERS,
)
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
    """A window whose two modal dialogs are replaced by recorders.

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
    yield win
    win.close()


# A three-point job in Michigan Central, International feet.
#
# Hand-derived siting. Michigan Central's grid origin is 43 deg 19 min N with a
# false northing of 0 and a false easting of 6,000,000 m (NOAA Manual NOS NGS 5
# Appendix A; michspc/spc/zones.py MI_CENTRAL).
#
#   northing 176,200 ift x 0.3048 = 53,705.76 m above the grid origin
#   53,705.76 m / 111,132 m per degree = 0.4833 deg
#   latitude = 43.3167 + 0.4833 = 43.800 N
#
#   easting 19,685,000 ift x 0.3048 = 5,999,988 m, i.e. 12 m west of the central
#   meridian at 84 deg 22 min W, so longitude = -84.367 give or take a second
#
# That latitude was chosen because it is the only band that is safe in BOTH
# zones of the conversion below: it lies inside Michigan Central's extent
# (43.5-46.0) and fitted band (43.30-46.05) and inside Michigan South's extent
# (41.6-44.3) and fitted band (41.45-44.25). So a Central-to-South job on this
# file raises no warning of any kind, which is what makes the "0 warnings"
# assertion meaningful.
CENTRAL_POINTS = (
    "101,176200.000,19685000.000,812.40,IRON PIPE\n"
    "102,176900.000,19686500.000,814.10,HUB\n"
    "103,175500.000,19684000.000,810.90,MAG NAIL\n"
)

CENTRAL_POINT_COUNT = 3
"""Three data lines in CENTRAL_POINTS, counted by eye."""


@pytest.fixture
def job_file(tmp_path) -> Path:
    path = tmp_path / "24-118-topo.csv"
    path.write_text(CENTRAL_POINTS, encoding="utf-8")
    return path


@pytest.fixture
def out_dir(tmp_path) -> Path:
    return tmp_path / "out"


def fill_in(window, *, input_path, output_directory, source, target, unit=None):
    """Answer the form the way a user would, by driving the widgets."""
    window.input_edit.setText(str(input_path))
    window.output_edit.setText(str(output_directory))
    window.from_zone.setCurrentIndex(window.from_zone.findData(source))
    window.to_zone.setCurrentIndex(window.to_zone.findData(target))
    if unit is not None:
        window.input_unit.setCurrentIndex(window.input_unit.findData(unit))
        window.output_unit.setCurrentIndex(window.output_unit.findData(unit))


def cell(window, row, column) -> str:
    index = window.model.index(row, column)
    return index.data(Qt.ItemDataRole.DisplayRole)


# --------------------------------------------------------------------------
# The window exists and is built from the registries
# --------------------------------------------------------------------------


def test_the_window_builds(window):
    """It constructs, names itself, and starts with an empty table."""
    assert window.windowTitle() == "Michigan SPC Zone Converter"
    # Nothing has been converted, so there is nothing to show.
    assert window.model.rowCount() == 0
    assert window.result is None


def test_the_table_has_the_seven_approved_columns(window):
    """Point, Northing, Easting, Elevation, grid factor, combined factor,
    warnings - the columns the owner approved, in that order."""
    assert results_model.COLUMNS == (
        "Point",
        "Northing",
        "Easting",
        "Elevation",
        "Grid scale factor",
        "Combined factor",
        "Warnings",
    )
    assert window.model.columnCount() == 7


def test_zone_dropdowns_are_built_from_the_registry(window):
    """Every registered zone appears, and no zone name is typed into the GUI.

    Derived from the registry, not from a list here: adding a zone to
    michspc.spc.zones.ALL_ZONES must make it selectable with no interface
    change (docs/DESIGN.md section 6).
    """
    for combo in (window.from_zone, window.to_zone):
        offered = [combo.itemData(i) for i in range(combo.count())]
        # Two non-zone entries (the unanswered placeholder and the geodetic
        # option) plus one per registered zone.
        assert len(offered) == 2 + len(ALL_ZONES)
        assert offered[0] == UNCHOSEN
        assert offered[1] == GEODETIC
        for zone in ALL_ZONES:
            position = combo.findData(zone)
            assert position >= 0, f"{zone.name} is not selectable"
            # The label is assembled from the registry record itself.
            assert combo.itemText(position) == f"{zone.name} {zone.code}"


def test_unit_dropdowns_offer_every_unit_and_default_to_international_feet(window):
    """Michigan legislated the International foot, so that is the default.

    docs/DESIGN.md section 7. Unlike the longitude convention, a default is
    defensible here: the unit in force is stated in every output file and a
    wrong choice shows up in the magnitudes.
    """
    for combo in (window.input_unit, window.output_unit):
        offered = [combo.itemData(i) for i in range(combo.count())]
        assert offered == list(ALL_UNITS)
        assert combo.currentData() is INTERNATIONAL_FEET


# --------------------------------------------------------------------------
# Convert is gated
# --------------------------------------------------------------------------


def test_convert_starts_disabled(window):
    """Nothing has been chosen, so there is nothing to run."""
    assert window.convert_button.isEnabled() is False


def test_convert_enables_only_once_every_question_is_answered(
    window, job_file, out_dir
):
    """Each of the four answers is necessary; together they are sufficient."""
    window.input_edit.setText(str(job_file))
    assert window.convert_button.isEnabled() is False  # no output folder

    window.output_edit.setText(str(out_dir))
    assert window.convert_button.isEnabled() is False  # no zones

    window.from_zone.setCurrentIndex(window.from_zone.findData(MI_CENTRAL))
    assert window.convert_button.isEnabled() is False  # no target zone

    window.to_zone.setCurrentIndex(window.to_zone.findData(MI_SOUTH))
    assert window.convert_button.isEnabled() is True


def test_clearing_the_input_file_disables_convert_again(window, job_file, out_dir):
    """The gate is a live condition, not a one-time check."""
    fill_in(
        window,
        input_path=job_file,
        output_directory=out_dir,
        source=MI_CENTRAL,
        target=MI_SOUTH,
    )
    assert window.convert_button.isEnabled() is True

    window.input_edit.setText("")
    assert window.convert_button.isEnabled() is False


# --------------------------------------------------------------------------
# The longitude sign convention has no default
# --------------------------------------------------------------------------


def test_the_longitude_selector_is_irrelevant_to_a_zone_to_zone_job(
    window, job_file, out_dir
):
    """A grid-to-grid conversion never looks at a longitude sign.

    michspc.job._convert_row consults the convention only on the geodetic
    branches, so for zone-to-zone the selector is disabled and its being
    unanswered does not block the run.
    """
    fill_in(
        window,
        input_path=job_file,
        output_directory=out_dir,
        source=MI_CENTRAL,
        target=MI_SOUTH,
    )
    assert window.longitude_combo.isEnabled() is False
    assert window.longitude_combo.currentData() == UNCHOSEN
    assert window.convert_button.isEnabled() is True


def test_the_longitude_selector_opens_unanswered(window):
    """No default, ever. The two conventions are indistinguishable from the
    numbers and choosing wrongly moves a Michigan point about 340 miles
    (docs/DESIGN.md section 7)."""
    assert window.longitude_combo.currentData() == UNCHOSEN


@pytest.mark.parametrize(
    "source,target",
    [
        # geodetic in, State Plane out
        (GEODETIC, MI_SOUTH),
        # State Plane in, geodetic out
        (MI_SOUTH, GEODETIC),
    ],
)
def test_a_geodetic_job_will_not_run_until_the_longitude_sign_is_chosen(
    window, job_file, out_dir, source, target
):
    from michspc.job import LongitudeConvention

    fill_in(
        window,
        input_path=job_file,
        output_directory=out_dir,
        source=source,
        target=target,
    )
    # Everything else is answered, so only the convention is holding it back.
    assert window.longitude_combo.isEnabled() is True
    assert window.convert_button.isEnabled() is False

    window.longitude_combo.setCurrentIndex(
        window.longitude_combo.findData(LongitudeConvention.NEGATIVE_WEST)
    )
    assert window.convert_button.isEnabled() is True


def test_geodetic_to_geodetic_is_not_a_conversion(window, job_file, out_dir):
    """Both ends geodetic is not a job this program performs, so Convert stays
    disabled rather than producing a pass-through file."""
    fill_in(
        window,
        input_path=job_file,
        output_directory=out_dir,
        source=GEODETIC,
        target=GEODETIC,
    )
    assert window.direction() is None
    assert window.convert_button.isEnabled() is False


# --------------------------------------------------------------------------
# A real conversion, end to end
# --------------------------------------------------------------------------


@pytest.fixture
def converted(window, job_file, out_dir):
    """A completed Michigan Central to Michigan South run."""
    fill_in(
        window,
        input_path=job_file,
        output_directory=out_dir,
        source=MI_CENTRAL,
        target=MI_SOUTH,
        unit=INTERNATIONAL_FEET,
    )
    ok = window.convert()
    if not ok:
        raise AssertionError(f"the run failed: {window.shown_failures}")
    return window


def test_a_conversion_fills_the_table(converted):
    """One row per point in the file, seven columns."""
    assert converted.model.rowCount() == CENTRAL_POINT_COUNT
    assert converted.model.columnCount() == 7
    # The identifiers are the file's own, in file order.
    assert [cell(converted, r, 0) for r in range(3)] == ["101", "102", "103"]


def test_the_status_line_reads_the_owners_wording(converted):
    """"<n> points converted. <m> warnings."

    n = 3, the three data lines in the fixture file.

    m = 0, hand-derived: the only warnings this pipeline raises are
    outside-zone-extent and easting-unlike-selected-zone
    (michspc.spc.convert.WarningCode). At latitude 43.800 the points sit inside
    Michigan South's extent (41.6-44.3), and their eastings are within 12 m of
    Michigan Central's false easting - far inside the 400 km window - so
    neither can fire.
    """
    assert converted.status_label.text() == "3 points converted. 0 warnings."
    # A clean run is not coloured. Colour means something in this program.
    assert converted.status_label.styleSheet() == ""


def test_a_successful_run_offers_the_output_folder(converted, out_dir):
    assert converted.open_folder_button.isEnabled() is True
    # The button opens exactly the folder the user named, as a local file URL.
    # QUrl renders a Windows path with forward slashes, so the comparison is
    # made as paths rather than as text.
    assert Path(converted.output_folder_url().toLocalFile()) == out_dir


def test_the_three_output_files_were_written(converted, out_dir):
    """The clean PNEZD export, the audit CSV and the job record."""
    assert set(converted.written_files) == {"pnezd", "audit", "report"}
    for path in converted.written_files.values():
        assert path.exists()
        assert path.parent == out_dir


# --------------------------------------------------------------------------
# UI honesty: the screen and the report are the same strings
# --------------------------------------------------------------------------


def test_every_displayed_value_is_the_formatters_own_string(converted):
    """String equality against michspc.fileio.formatting, value by value.

    Not "close to", not "rounds the same" - the identical string. The formatter
    is the single authority for what a number looks like, and the report calls
    the same functions, so this is what guarantees the screen and the file
    cannot disagree.
    """
    result = converted.result
    unit = result.settings.output_unit

    for row, point in enumerate(result.points):
        assert cell(converted, row, 0) == point.point_id
        assert cell(converted, row, 1) == fmt.coordinate(point.output_northing, unit)
        assert cell(converted, row, 2) == fmt.coordinate(point.output_easting, unit)
        assert cell(converted, row, 3) == fmt.coordinate(point.output_elevation, unit)
        assert cell(converted, row, 4) == fmt.factor(point.factors.grid_scale_factor)
        assert cell(converted, row, 5) == fmt.factor(point.factors.combined_factor)
        assert cell(converted, row, 6) == "; ".join(
            w.code.value for w in point.warnings
        )


def test_the_screen_matches_the_file_that_was_written(converted):
    """The stronger form of the same claim, read back off the disk.

    exports.clean_pnezd_rows is what lands in CAD. If the table and that file
    ever disagreed about a coordinate, one of them would be lying to a surveyor.
    """
    written = converted.written_files["pnezd"].read_text(encoding="utf-8")
    lines = [line for line in written.splitlines() if line.strip()]
    assert len(lines) == CENTRAL_POINT_COUNT

    for row, line in enumerate(lines):
        point_id, northing, easting, elevation = line.split(",")[:4]
        assert cell(converted, row, 0) == point_id
        assert cell(converted, row, 1) == northing
        assert cell(converted, row, 2) == easting
        assert cell(converted, row, 3) == elevation


def test_the_displayed_precision_is_the_precision_the_owner_specified(converted):
    """3 dp for coordinates in feet, 8 dp for factors.

    docs/DESIGN.md amendment #1: "Precision: N/E/Z 3 dp in feet, 4 dp in meters;
    factors 8 dp". Checked here against the specification rather than against
    the formatter, so a change to the formatter that silently altered the
    precision would still be caught.
    """
    for row in range(converted.model.rowCount()):
        for column in (1, 2, 3):
            assert len(cell(converted, row, column).split(".")[1]) == 3
        for column in (4, 5):
            assert len(cell(converted, row, column).split(".")[1]) == 8


def test_metres_are_shown_to_four_places(window, job_file, out_dir):
    """The other half of the same rule: 4 dp in meters."""
    fill_in(
        window,
        input_path=job_file,
        output_directory=out_dir,
        source=MI_CENTRAL,
        target=MI_SOUTH,
    )
    window.output_unit.setCurrentIndex(window.output_unit.findData(METERS))
    if not window.convert():
        raise AssertionError(f"the run failed: {window.shown_failures}")

    assert len(cell(window, 0, 1).split(".")[1]) == 4
    # And still the formatter's own string.
    assert cell(window, 0, 1) == fmt.coordinate(
        window.result.points[0].output_northing, METERS
    )


# --------------------------------------------------------------------------
# Severity colour
# --------------------------------------------------------------------------


def test_warnings_are_counted_and_shown_in_amber(window, job_file, out_dir):
    """Michigan Central to Michigan North on this file: exactly 3 warnings.

    Hand-derived, one per point over three points:

    outside-zone-extent - latitude 43.800 is south of Michigan North's extent,
    which starts at 45.0 (michspc/spc/zones.py MI_NORTH.lat_min).

    That is now the only warning these points can raise. Two per point was
    correct while the polynomial cross-check existed, which also fired here
    because 43.800 fell below Michigan North's fitted band; that engine and its
    warning were removed in docs/DESIGN.md amendment #14.

    The easting warning cannot fire: the eastings are within 12 m of Michigan
    Central's false easting, and Michigan Central is the source zone here.
    """
    fill_in(
        window,
        input_path=job_file,
        output_directory=out_dir,
        source=MI_CENTRAL,
        target=MI_NORTH,
    )
    if not window.convert():
        raise AssertionError(f"the run failed: {window.shown_failures}")

    assert window.status_label.text() == "3 points converted. 3 warnings."

    # Amber = "look at this" (docs/method/METHOD.md section 5). It is the only
    # colour a completed run may wear.
    assert "color:" in window.status_label.styleSheet()
    assert window.status_label.styleSheet() != ""

    # And the warning cell of every affected row carries the amber background.
    for row in range(window.model.rowCount()):
        brush = window.model.index(row, 6).data(Qt.ItemDataRole.BackgroundRole)
        assert brush is not None
        assert brush.color() == results_model.AMBER
        # ... while an untroubled cell is left in the system's own palette.
        assert window.model.index(row, 1).data(Qt.ItemDataRole.BackgroundRole) is None


def test_a_clean_run_paints_nothing(converted):
    """No warnings means no colour anywhere in the table."""
    for row in range(converted.model.rowCount()):
        for column in range(7):
            index = converted.model.index(row, column)
            assert index.data(Qt.ItemDataRole.BackgroundRole) is None


# --------------------------------------------------------------------------
# Failures arrive intact
# --------------------------------------------------------------------------


def test_a_malformed_file_surfaces_the_readers_own_message(
    window, tmp_path, out_dir
):
    """The reader's message, verbatim - not a generic "conversion failed".

    The expected text is obtained by asking the reader itself to refuse the same
    file, so this compares the interface against the authority rather than
    against a copy of the wording that could rot.
    """
    bad = tmp_path / "broken.csv"
    # Line 2's northing field is not a number, so pnezd refuses by line number
    # and names the offending text.
    bad.write_text(
        "101,176200.000,19685000.000,812.40,IRON PIPE\n"
        "102,NORTHING?,19686500.000,814.10,HUB\n",
        encoding="utf-8",
    )

    with pytest.raises(pnezd.PnezdError) as raised:
        pnezd.read(bad)
    expected = str(raised.value)

    fill_in(
        window,
        input_path=bad,
        output_directory=out_dir,
        source=MI_CENTRAL,
        target=MI_SOUTH,
    )
    assert window.convert() is False

    assert window.shown_failures == [expected]
    assert str(window.last_failure) == expected
    # The message names the offending row, which is the whole point of it.
    assert "line 2" in expected
    assert "NORTHING?" in expected


def test_a_refusal_leaves_no_results_and_writes_nothing(window, tmp_path, out_dir):
    bad = tmp_path / "empty.csv"
    # A file with no coordinate rows: pnezd refuses rather than producing an
    # empty export that would look like a successful conversion.
    bad.write_text("\n\n", encoding="utf-8")

    fill_in(
        window,
        input_path=bad,
        output_directory=out_dir,
        source=MI_CENTRAL,
        target=MI_SOUTH,
    )
    assert window.convert() is False

    assert window.model.rowCount() == 0
    assert window.result is None
    assert window.written_files == {}
    assert window.open_folder_button.isEnabled() is False
    assert out_dir.exists() is False


def test_a_refusal_is_shown_in_red_and_carries_the_message(window, tmp_path, out_dir):
    """Red = actually wrong (docs/method/METHOD.md section 5).

    The status line is one line and the dialog is authoritative, so the line
    carries the message's first line and the whole text sits in its tooltip.
    Nothing is paraphrased.
    """
    bad = tmp_path / "broken.csv"
    bad.write_text("101,NOPE,19685000.000,812.40,IRON PIPE\n", encoding="utf-8")

    fill_in(
        window,
        input_path=bad,
        output_directory=out_dir,
        source=MI_CENTRAL,
        target=MI_SOUTH,
    )
    window.convert()

    message = str(window.last_failure)
    assert window.status_label.styleSheet() != ""
    assert message.splitlines()[0] in window.status_label.text()
    assert window.status_label.toolTip() == message


def test_a_refusal_that_looks_like_markup_is_still_shown_as_text(window):
    """QLabel guesses whether a string is HTML. The status line must not guess.

    Refusal messages quote file content back verbatim, and a PNEZD description
    field is whatever the surveyor typed. If Qt's heuristic decides such a
    message is rich text, the offending token is rendered as a tag and
    disappears from a message whose entire job is to name the offending point.
    """
    from PySide6.QtGui import Qt as GuiQt

    from michspc.fileio.writers import WriteError

    message = (
        "Point 104: the description reads 'MON <br> BOX', which the export "
        "could not round-trip. Nothing was written."
    )
    # Anti-vacuousness: Qt really would treat this string as rich text if the
    # label were left on its default AutoText setting.
    assert GuiQt.mightBeRichText(message) is True

    window._report_failure(WriteError(message))

    assert window.status_label.textFormat() == Qt.TextFormat.PlainText
    assert window.status_label.toolTip() == message
    assert "<br>" in window.status_label.text()


def test_converting_with_an_incomplete_form_refuses_rather_than_guessing(window):
    """The button is disabled in this state; if it is ever reached anyway, the
    program says so instead of running a half-specified job."""
    assert window.convert() is False
    assert isinstance(window.last_failure, ValueError)
    assert len(window.shown_failures) == 1


# --------------------------------------------------------------------------
# Overwrite
# --------------------------------------------------------------------------


def test_a_second_run_asks_before_replacing_and_keeps_the_files_when_declined(
    converted, out_dir
):
    """exports.write_all refuses to clobber; the answer is to ask, not to force."""
    pnezd_path = converted.written_files["pnezd"]
    original = pnezd_path.read_text(encoding="utf-8")
    stem = exports.output_stem(converted.result)

    converted.overwrite_answer = False
    converted.overwrite_prompts.clear()

    assert converted.convert() is False

    # The user was asked, by name, about the three files at risk.
    assert len(converted.overwrite_prompts) == 1
    prompted = {path.name for path in converted.overwrite_prompts[0]}
    assert prompted == {
        f"{stem}.csv",
        f"{stem}_full.csv",
        f"{stem}_README.txt",
    }

    # Declining left the previous run's file exactly as it was.
    assert pnezd_path.read_text(encoding="utf-8") == original
    # And no refusal dialog was raised: declining is a choice, not a failure.
    assert converted.shown_failures == []


def test_confirming_the_overwrite_replaces_the_files(converted):
    pnezd_path = converted.written_files["pnezd"]
    original = pnezd_path.read_text(encoding="utf-8")
    # Vandalise the previous output so a genuine rewrite is visible.
    pnezd_path.write_text("stale\n", encoding="utf-8")

    converted.overwrite_answer = True
    converted.overwrite_prompts.clear()

    assert converted.convert() is True
    assert len(converted.overwrite_prompts) == 1
    assert pnezd_path.read_text(encoding="utf-8") == original
    assert converted.shown_failures == []


def test_the_first_run_never_asks(converted):
    """Nothing existed, so nothing was at risk, so no prompt."""
    assert converted.overwrite_prompts == []


def test_a_write_failure_that_is_not_a_clobber_is_surfaced_not_prompted(
    window, job_file, tmp_path
):
    """An output "folder" that is really a file.

    exports.write_all raises WriteError because the directory cannot be
    created, but none of the three destinations exists, so there is nothing to
    overwrite. That must reach the user as a refusal, not as an overwrite
    question - the prompt is answered only to a genuine clobber refusal.
    """
    occupied = tmp_path / "not-a-folder.txt"
    occupied.write_text("this is a file, not a directory\n", encoding="utf-8")

    fill_in(
        window,
        input_path=job_file,
        output_directory=occupied,
        source=MI_CENTRAL,
        target=MI_SOUTH,
    )

    assert window.convert() is False
    assert window.overwrite_prompts == []
    assert len(window.shown_failures) == 1
    # The writer's own words, naming the path it could not create.
    assert str(occupied) in window.shown_failures[0]


# --------------------------------------------------------------------------
# The interface computes nothing
# --------------------------------------------------------------------------


def test_the_model_holds_strings_and_nothing_else(converted):
    """Every displayed value is text produced downstream.

    A float reaching the table would mean the interface had taken a view on how
    a number should look, which is the core's job and the formatter's job.
    """
    for row in range(converted.model.rowCount()):
        for column in range(7):
            value = converted.model.index(row, column).data(
                Qt.ItemDataRole.DisplayRole
            )
            assert isinstance(value, str)


def test_an_absent_elevation_reads_n_a_and_never_a_number(window, tmp_path, out_dir):
    """A blank Z column produces N/A in the factor columns, never 1.0.

    docs/DESIGN.md section 7. The elevation and combined factors have no honest
    value for a point that was never levelled, and a fabricated 1.0 would ride
    onto a drawing looking ordinary.
    """
    path = tmp_path / "no-elev.csv"
    # Same siting as CENTRAL_POINTS, with the elevation field left blank.
    path.write_text("101,176200.000,19685000.000,,IRON PIPE\n", encoding="utf-8")

    fill_in(
        window,
        input_path=path,
        output_directory=out_dir,
        source=MI_CENTRAL,
        target=MI_SOUTH,
    )
    if not window.convert():
        raise AssertionError(f"the run failed: {window.shown_failures}")

    assert cell(window, 0, 3) == fmt.NOT_AVAILABLE
    # The grid scale factor does not depend on elevation, so it is still real.
    assert cell(window, 0, 4) != fmt.NOT_AVAILABLE
    # The combined factor does, so it is absent rather than invented.
    assert cell(window, 0, 5) == fmt.NOT_AVAILABLE


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def test_build_application_never_makes_a_second_qapplication(qapp):
    """Two QApplications in one process crash the interpreter
    (docs/method/TOOLING.md), so the entry point reuses the existing one."""
    assert build_application([]) is qapp
    assert QApplication.instance() is qapp


def test_launch_imports_main_with_the_signature_it_expects():
    """launch.py does `from michspc.gui.app import main` and calls main()."""
    from michspc.gui.app import main

    assert callable(main)
    launch_source = (
        Path(__file__).resolve().parent.parent / "launch.py"
    ).read_text(encoding="utf-8")
    assert "from michspc.gui.app import main" in launch_source
