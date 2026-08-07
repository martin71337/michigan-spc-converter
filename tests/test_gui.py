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
from PySide6.QtCore import QStandardPaths, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tests.conftest import archive_members, member_text

from michspc.fileio import exports, formatting as fmt, pnezd  # noqa: E402
from michspc.gui import icon, results_model, window as window_module  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.window import (  # noqa: E402
    GEODETIC,
    INPUT_HINT_GEODETIC,
    INPUT_HINT_UNCHOSEN,
    INPUT_HINT_ZONE,
    INPUT_LABEL,
    UNCHOSEN,
    WINDOW_TITLE,
    MainWindow,
)
from michspc.job import Direction, LongitudeConvention  # noqa: E402
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
    assert window.windowTitle() == "MCX - Martin Coordinate Exchange"
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
    """Each of the four answers is necessary; together they are sufficient.

    The output folder is cleared first. It now opens pre-filled with Downloads
    (docs/DESIGN.md amendment #16 note 3), so leaving it alone would make this
    test pass while proving nothing about the folder being required.
    """
    window.output_edit.setText("")
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
    assert window.convert_button.isEnabled() is True

    # And the selector's value does not leak into the job. The dropdown now
    # opens on a real convention (#29), so the ONLY thing keeping a zone-to-zone
    # job from carrying one is settings() stating None deliberately - which is
    # what makes the job record say nothing about a question never asked.
    assert window.settings().longitude_convention is None


def test_the_longitude_selector_opens_on_positive_west(window):
    """docs/DESIGN.md amendment #29 - which REVERSES section 7 on this control.

    The owner asked for it: he works in positive west, the NOAA Manual NOS NGS
    5 convention, and answering the same question every run is friction he does
    not want. What section 7's reasoning still buys is everywhere else - the
    enum has no default, JobSettings has no default, and job.run refuses a
    geodetic conversion that does not state one. Only the dropdown opens on a
    value, where it is visible in words before Convert is pressed.
    """
    assert window.longitude_combo.currentData() == LongitudeConvention.POSITIVE_WEST
    assert window.longitude_convention() is LongitudeConvention.POSITIVE_WEST

    # No "not yet" entry to fall back into: one item per convention, no more.
    assert window.longitude_combo.count() == len(LongitudeConvention)


@pytest.mark.parametrize(
    "source,target",
    [
        # geodetic in, State Plane out
        (GEODETIC, MI_SOUTH),
        # State Plane in, geodetic out
        (MI_SOUTH, GEODETIC),
    ],
)
def test_a_geodetic_job_runs_on_the_preselected_sign_and_follows_a_change(
    window, job_file, out_dir, source, target
):
    """The default does not hold the job up, and it is not a dead control.

    Anti-vacuousness for #29: a preselected value that stopped reaching the
    conversion would pass every "it opens on positive west" assertion while
    doing nothing. Here the run is available immediately AND the other
    convention is still selectable and still changes the settings the job runs
    with.
    """
    fill_in(
        window,
        input_path=job_file,
        output_directory=out_dir,
        source=source,
        target=target,
    )
    assert window.longitude_combo.isEnabled() is True
    assert window.convert_button.isEnabled() is True
    assert (
        window.settings().longitude_convention is LongitudeConvention.POSITIVE_WEST
    )

    window.longitude_combo.setCurrentIndex(
        window.longitude_combo.findData(LongitudeConvention.NEGATIVE_WEST)
    )
    assert window.convert_button.isEnabled() is True
    assert (
        window.settings().longitude_convention is LongitudeConvention.NEGATIVE_WEST
    )


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


def test_one_archive_was_written_holding_the_three_files(converted, out_dir):
    """A job writes ONE file (docs/DESIGN.md amendment #17).

    The clean PNEZD export, the audit CSV and the job record all live inside it;
    nothing is written loose beside it, so the output folder holds exactly one
    entry.
    """
    assert set(converted.written_files) == {"archive", "pnezd", "audit", "report"}

    archive = converted.written_files["archive"]
    assert archive.exists()
    assert archive.parent == out_dir
    assert archive.suffix == ".zip"
    assert [p.name for p in out_dir.iterdir()] == [archive.name]

    # Every role points at that same archive; the roles name members inside it.
    assert set(converted.written_files.values()) == {archive}

    members = archive_members(archive)
    assert len(members) == 3
    assert sum(name.endswith("_full.csv") for name in members) == 1
    assert sum(name.endswith("_README.txt") for name in members) == 1


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
    clean_name = exports.member_names(converted.result)["pnezd"]
    written = archive_members(converted.written_files["archive"])[clean_name]
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
    archive = converted.written_files["archive"]
    original = archive.read_bytes()
    stem = exports.output_stem(converted.result)

    converted.overwrite_answer = False
    converted.overwrite_prompts.clear()

    assert converted.convert() is False

    # A job writes ONE file (docs/DESIGN.md amendment #17), so the user is asked
    # by name about exactly that one.
    assert len(converted.overwrite_prompts) == 1
    prompted = {path.name for path in converted.overwrite_prompts[0]}
    assert prompted == {f"{stem}.zip"}

    # Declining left the previous run's archive byte-for-byte as it was.
    assert archive.read_bytes() == original
    # And no refusal dialog was raised: declining is a choice, not a failure.
    assert converted.shown_failures == []


def test_confirming_the_overwrite_replaces_the_files(converted):
    archive = converted.written_files["archive"]
    clean_name = exports.member_names(converted.result)["pnezd"]
    original = archive_members(archive)[clean_name]
    # Vandalise the previous output so a genuine rewrite is visible. A file that
    # is not a valid archive at all makes the replacement unambiguous.
    archive.write_bytes(b"stale, not a zip at all")

    converted.overwrite_answer = True
    converted.overwrite_prompts.clear()

    assert converted.convert() is True
    assert len(converted.overwrite_prompts) == 1
    # It is a real archive again, carrying the same coordinates.
    assert archive_members(archive)[clean_name] == original
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


# --------------------------------------------------------------------------
# The input row: a static label, a hint that follows the From selection
# --------------------------------------------------------------------------


def test_the_input_label_is_static_and_never_says_pnezd(window):
    """"Input file:" in every state (docs/DESIGN.md amendment #16 note 1).

    The label names the control; the hint names the layout. Checked across every
    From selection the program offers, because the whole point of the amendment
    is that the label does NOT move between two spellings.
    """
    selections = [UNCHOSEN, GEODETIC] + list(ALL_ZONES)
    for selection in selections:
        window.from_zone.setCurrentIndex(window.from_zone.findData(selection))
        assert window.input_label.text() == INPUT_LABEL
        assert window.input_label.text() == "Input file:"
        assert "PNEZD" not in window.input_label.text()


@pytest.mark.parametrize(
    "selection,expected",
    [
        # A State Plane source: the file is PNEZD, columns two and three are
        # northing and easting.
        (MI_NORTH, INPUT_HINT_ZONE),
        (MI_CENTRAL, INPUT_HINT_ZONE),
        (MI_SOUTH, INPUT_HINT_ZONE),
        # A geodetic source: columns two and three are latitude and longitude,
        # so the file is not PNEZD at all.
        (GEODETIC, INPUT_HINT_GEODETIC),
        # Nothing chosen: the hint names the dependency rather than defaulting
        # to either reading.
        (UNCHOSEN, INPUT_HINT_UNCHOSEN),
    ],
)
def test_the_format_hint_follows_the_from_selection(window, selection, expected):
    """A geodetic file read as PNEZD produces a coordinate, not an error.

    michspc.spc.convert.easting_looks_wrong_for_zone only fires on the zone
    branch, so nothing downstream catches a file fed under the wrong reading.
    The hint is the correctness aid that has to (docs/DESIGN.md amendment #16
    note 1).
    """
    window.from_zone.setCurrentIndex(window.from_zone.findData(selection))
    assert window.input_hint.text() == expected


def test_the_geodetic_hint_names_latitude_and_longitude(window):
    """Stated against the words themselves, not against the constant.

    A change that kept the constant's name but emptied its meaning would pass
    the parametrised test above and fail here.
    """
    window.from_zone.setCurrentIndex(window.from_zone.findData(GEODETIC))
    hint = window.input_hint.text()

    assert "latitude" in hint
    assert "longitude" in hint
    assert "northing" not in hint
    assert "easting" not in hint
    assert "no header row" in hint.lower()


def test_the_zone_hint_names_northing_and_easting(window):
    window.from_zone.setCurrentIndex(window.from_zone.findData(MI_CENTRAL))
    hint = window.input_hint.text()

    assert "northing" in hint
    assert "easting" in hint
    assert "latitude" not in hint
    assert "longitude" not in hint


def test_the_hint_ignores_the_to_selection(window):
    """The To zone cannot change how the INPUT file is parsed.

    A State Plane to geodetic job still reads a PNEZD file. A hint that moved
    with the target would be describing the wrong end of the conversion, and
    would tell a surveyor his northings were latitudes.
    """
    window.from_zone.setCurrentIndex(window.from_zone.findData(MI_CENTRAL))
    window.to_zone.setCurrentIndex(window.to_zone.findData(GEODETIC))
    assert window.input_hint.text() == INPUT_HINT_ZONE

    window.from_zone.setCurrentIndex(window.from_zone.findData(GEODETIC))
    window.to_zone.setCurrentIndex(window.to_zone.findData(MI_CENTRAL))
    assert window.input_hint.text() == INPUT_HINT_GEODETIC


# --------------------------------------------------------------------------
# The longitude wording
# --------------------------------------------------------------------------


def test_the_longitude_convention_reads_the_wording_the_owner_chose():
    """Exactly these two strings (docs/DESIGN.md amendments #16 note 2, #17, #28).

    Two things have been stripped at the owner's direction: the attribution
    tails ("as used by OPUS, NCAT, GPS and GIS" / "as used by NOAA Manual NOS
    NGS 5") at #17, and the worked example ("(-84.37)" / "(84.37)") at #28. The
    sign word alone names the convention completely.

    He chose one wording for BOTH surfaces each time, so there is no separate
    GUI label to drift from this - which is why the job record's line moves with
    the dropdown's, and why that is checked below rather than assumed.
    """
    assert LongitudeConvention.NEGATIVE_WEST.value == "negative west"
    assert LongitudeConvention.POSITIVE_WEST.value == "positive west"
    assert [c.value for c in LongitudeConvention] == [
        "negative west",
        "positive west",
    ]

    # The worked example is gone from the values themselves, not merely
    # shortened - it moved to the dropdown's tooltip, which is checked in
    # test_the_longitude_tooltip_carries_the_worked_example.
    for convention in LongitudeConvention:
        assert "84.37" not in convention.value


def test_the_longitude_tooltip_carries_the_worked_example(window):
    """The example moved out of the entries and into the tooltip (#28).

    It was doing real work where it was - a surveyor choosing between two
    conventions needs to see which sign each one puts on a Michigan longitude -
    but it rode the enum value into the job record's Longitude line as well.
    The tooltip teaches the person making the choice without following the
    choice into every document that reports it.
    """
    tip = window.longitude_combo.toolTip()

    assert "-84.37" in tip
    assert "84.37" in tip
    # And the part that says why the question is being asked at all - which
    # matters more now that the control opens on an answer (#29), because the
    # tooltip is where the question still gets asked.
    assert "340 miles" in tip
    assert "opens on positive west" in tip
    assert "CHECK THIS AGAINST THE FILE" in tip

    # Anti-vacuousness: the example really is absent from the place it used to
    # be, so the tooltip is now the only surface carrying it.
    for position in range(window.longitude_combo.count()):
        assert "84.37" not in window.longitude_combo.itemText(position)


def test_the_longitude_dropdown_shows_the_enum_values_and_nothing_else(window):
    """One authoritative representation of this wording.

    The GUI does not carry its own labels for these; it shows the enum's own
    values, which is what makes the job record and the screen unable to
    disagree (docs/DESIGN.md amendment #17).
    """
    combo = window.longitude_combo
    # One entry per convention and no more. The "— choose —" placeholder went
    # with the no-default rule (#29): beside a preselected value it would be a
    # third option meaning "not yet".
    assert combo.count() == len(LongitudeConvention)

    for position in range(combo.count()):
        convention = combo.itemData(position)
        assert isinstance(convention, LongitudeConvention)
        assert combo.itemText(position) == convention.value
        assert "as used by" not in combo.itemText(position)


def test_the_core_has_no_longitude_default_even_though_the_dropdown_does(
    window, job_file, out_dir, tmp_path
):
    """The half of section 7 that #29 did NOT reverse, pinned where it lives.

    The owner moved the default into the interface, and only into the
    interface. Everything below it still refuses to assume: a JobSettings that
    states no convention on a geodetic direction is refused by job.run, in the
    core, with the 340-mile sentence intact. That is what stops the preselect
    from becoming a program-wide assumption if the GUI is ever bypassed - by a
    test, by a script, or by a later feature.
    """
    from michspc.job import Direction, JobSettings, run

    settings = JobSettings(
        input_path=job_file,
        output_directory=out_dir,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_CENTRAL,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=None,
        apply_geoid=True,
    )

    with pytest.raises(ValueError) as raised:
        run(settings)

    message = str(raised.value)
    assert "has no default" in message
    assert "340 miles" in message

    # And the dataclass itself does not supply one to a caller who omits it.
    with pytest.raises(TypeError):
        JobSettings(
            input_path=job_file,
            output_directory=out_dir,
            direction=Direction.GEODETIC_TO_ZONE,
            source_zone=None,
            target_zone=MI_CENTRAL,
            input_unit=INTERNATIONAL_FEET,
            output_unit=INTERNATIONAL_FEET,
            apply_geoid=True,
        )


# A one-point geodetic file, sited by the same hand derivation as CENTRAL_POINTS
# read backwards: latitude 43.800 N, longitude 84.367 W. Michigan Central's grid
# origin is 43 deg 19 min N with a false easting of 6,000,000 m and a central
# meridian at 84 deg 22 min W (NOAA Manual NOS NGS 5 Appendix A).
#
#   43.800 - 43.31667 = 0.48333 deg x 111,132 m/deg = 53,706 m of northing,
#   which is 53,706 / 0.3048 = 176,200 international feet.
#
#   84.367 - 84.36667 = 0.00033 deg of longitude west of the central meridian,
#   x cos(43.8) x 111,320 m/deg = about 27 m, so the easting sits about 88 ift
#   west of the false easting 6,000,000 m = 19,685,039.370 ift.
GEODETIC_POINT = "101,43.800,-84.367,812.40,IRON PIPE\n"


@pytest.fixture
def geodetic_file(tmp_path) -> Path:
    path = tmp_path / "24-118-gps.csv"
    path.write_text(GEODETIC_POINT, encoding="utf-8")
    return path


def test_a_geodetic_job_runs_end_to_end_and_lands_where_it_should(
    window, geodetic_file, out_dir
):
    """The geodetic branch, driven through the interface for the first time.

    The bounds are deliberately loose - the siting above is a flat-earth
    approximation, good to a few hundred feet, and the projection itself is
    anchored to the frozen NCAT lattice elsewhere. What they establish is that
    the file's columns two and three were read as latitude and longitude and
    actually projected: a pass-through, a wrong zone, or a sign error would each
    be wrong by hundreds of thousands of feet, not by hundreds.
    """
    fill_in(
        window,
        input_path=geodetic_file,
        output_directory=out_dir,
        source=GEODETIC,
        target=MI_CENTRAL,
        unit=INTERNATIONAL_FEET,
    )
    window.longitude_combo.setCurrentIndex(
        window.longitude_combo.findData(LongitudeConvention.NEGATIVE_WEST)
    )
    if not window.convert():
        raise AssertionError(f"the run failed: {window.shown_failures}")

    point = window.result.points[0]
    assert abs(point.output_northing - 176_200) < 1000
    assert abs(point.output_easting - 19_685_039) < 1000
    # And the table shows the formatter's own strings, as everywhere else.
    assert cell(window, 0, 1) == fmt.coordinate(
        point.output_northing, INTERNATIONAL_FEET
    )


def test_the_job_record_prints_the_short_longitude_wording(
    window, geodetic_file, out_dir
):
    """The record and the dropdown say the same thing, and it is the short one.

    docs/DESIGN.md amendment #17 accepted the shorter text in the job record
    too. This reads the record out of the archive that was actually written, so
    it is the document a surveyor would file six months later, not a string
    assembled here.
    """
    fill_in(
        window,
        input_path=geodetic_file,
        output_directory=out_dir,
        source=GEODETIC,
        target=MI_CENTRAL,
        unit=INTERNATIONAL_FEET,
    )
    window.longitude_combo.setCurrentIndex(
        window.longitude_combo.findData(LongitudeConvention.POSITIVE_WEST)
    )
    if not window.convert():
        raise AssertionError(f"the run failed: {window.shown_failures}")

    record = member_text(window.written_files["archive"], "_README.txt")
    longitude_lines = [
        line for line in record.splitlines() if line.startswith("Longitude")
    ]

    assert len(longitude_lines) == 1
    # The line is a fixed-width label followed by the convention's own value.
    assert longitude_lines[0].split(maxsplit=1)[1].strip() == "positive west"
    assert longitude_lines[0].strip() == "Longitude          positive west"
    # The dropped attribution is gone from the whole record, not just this line.
    assert "as used by" not in record


# --------------------------------------------------------------------------
# Neither file box suggests anything
# --------------------------------------------------------------------------


def test_the_input_file_box_opens_empty_with_no_placeholder(window):
    """docs/DESIGN.md amendment #27.

    The greyed-out ``C:\\jobs\\24-118\\pts.csv`` is gone. It was a job number
    that is not this surveyor's, in a folder that does not exist, sitting in
    the field that names the file about to be read - and a placeholder in a
    path field is indistinguishable at a glance from a path that is there.
    """
    assert window.input_edit.text() == ""
    assert window.input_edit.placeholderText() == ""
    assert window.input_path is None


def test_the_output_folder_box_opens_empty_with_no_placeholder(window):
    """docs/DESIGN.md amendment #27, which REVERSES amendment #16 note 3.

    The Downloads pre-fill is gone and nothing replaced it. Downloads is not
    where a survey job's exports belong, and a pre-filled destination is
    answered by pressing Convert rather than by choosing.
    """
    assert window.output_edit.text() == ""
    assert window.output_edit.placeholderText() == ""
    assert window.output_directory is None


def test_the_downloads_default_is_gone_from_the_module_entirely(window):
    """Deleted, not merely unused.

    A dormant ``default_output_directory`` sitting beside a field that no
    longer calls it is one line away from being switched back on by someone who
    reads #16 note 3 and not #27. The absence is the pin.
    """
    assert not hasattr(window_module, "default_output_directory")

    # And nothing else reaches for the Downloads location either: the whole
    # QStandardPaths import went with it.
    source = Path(window_module.__file__).read_text(encoding="utf-8")
    assert "QStandardPaths" not in source.replace(
        "# default_output_directory, through QStandardPaths", ""
    )


def test_an_empty_output_folder_keeps_convert_disabled(window, job_file, out_dir):
    """The empty box is a question, not an obstacle - but it is a real question.

    With no default there is nothing to fall back on, so the gate that was
    always there is now the only thing standing between an unanswered
    destination and a write. Filling every OTHER field must not enable Convert.
    """
    fill_in(
        window,
        input_path=job_file,
        output_directory=out_dir,
        source=MI_CENTRAL,
        target=MI_SOUTH,
    )
    # Anti-vacuousness: with the folder answered, Convert really is available,
    # so what the next line proves is the folder and not some other blank.
    assert window.convert_button.isEnabled() is True

    window.output_edit.setText("")
    assert window.convert_button.isEnabled() is False


def test_the_output_folder_box_is_still_editable(window, out_dir):
    """Empty, and typed into - not read-only and not a dialog-only field."""
    assert window.output_edit.isReadOnly() is False

    window.output_edit.setText(str(out_dir))
    assert window.output_directory == out_dir


def test_a_typed_destination_does_not_relax_the_overwrite_refusal(
    window, job_file, out_dir
):
    """The property that mattered under the old default still holds.

    Amendment #16 note 3 checked this of the pre-filled folder; removing the
    default does not remove the reason to check it, because it is the one
    property of this field that could cost someone their work.
    """
    fill_in(
        window,
        input_path=job_file,
        output_directory=out_dir,
        source=MI_CENTRAL,
        target=MI_SOUTH,
    )
    if not window.convert():
        raise AssertionError(f"the run failed: {window.shown_failures}")

    window.overwrite_answer = False
    window.overwrite_prompts.clear()
    assert window.convert() is False
    assert len(window.overwrite_prompts) == 1


# --------------------------------------------------------------------------
# The application icon
# --------------------------------------------------------------------------


def test_the_window_wears_the_application_icon(window):
    """The master artwork is committed, so a fresh clone has one even before
    tools/make_icon.py has ever run (docs/DESIGN.md amendment #15 note 1)."""
    assert icon.icon_path() is not None
    assert window.windowIcon().isNull() is False


def test_the_window_still_opens_when_no_icon_has_been_built(
    qapp, tmp_path, monkeypatch
):
    """The generated .ico is build output and may simply not be there.

    A missing icon is cosmetic. Refusing to open the window over it would apply
    the tier sentence backwards - nothing about a coordinate depends on the
    picture - so the loader returns a null QIcon and construction carries on.
    """
    monkeypatch.setattr(icon, "GENERATED_ICO", tmp_path / "not-built.ico")
    monkeypatch.setattr(icon, "MASTER_PNG", tmp_path / "no-master.png")

    # Anti-vacuousness: there really is nothing to find in this state.
    assert icon.icon_path() is None

    built = MainWindow()
    try:
        assert built.windowIcon().isNull() is True
        assert built.windowTitle() == WINDOW_TITLE
        # And the window is fully usable, not a stub that happened to construct.
        assert built.convert_button.isEnabled() is False
        assert built.input_label.text() == INPUT_LABEL
    finally:
        built.close()


def test_launch_imports_main_with_the_signature_it_expects():
    """launch.py does `from michspc.gui.app import main` and calls main()."""
    from michspc.gui.app import main

    assert callable(main)
    launch_source = (
        Path(__file__).resolve().parent.parent / "launch.py"
    ).read_text(encoding="utf-8")
    assert "from michspc.gui.app import main" in launch_source


# --------------------------------------------------------------------------
# WP-R2 fixes A and H, at the interface.
#
# A State-Plane-to-geodetic run driven through the window, because these two
# fixes are about what the SCREEN says and about the screen agreeing with the
# file. The position is the interim gate's own: Lansing, 42.73250000 N,
# -84.55550000 W, which in Michigan South is N = 136920.027586723 m,
# E = 3984537.119005890 m, and 0.3048 m to the International foot exactly gives
#     136920.027586723 / 0.3048 = 449212.6889 ift
#     3984537.119005890 / 0.3048 = 13072628.3432 ift
# --------------------------------------------------------------------------

SPC_POINT = "101,449212.689,13072628.343,900.000,IRON PIPE\n"
"""The reviewer's counterexample row for fix A, in Michigan South feet."""


@pytest.fixture
def spc_file(tmp_path) -> Path:
    path = tmp_path / "24-118-spc.csv"
    path.write_text(SPC_POINT, encoding="utf-8")
    return path


@pytest.fixture
def to_geodetic(window, spc_file, out_dir):
    """A completed Michigan South -> geodetic run, feet in, metres out."""
    fill_in(
        window,
        input_path=spc_file,
        output_directory=out_dir,
        source=MI_SOUTH,
        target=GEODETIC,
    )
    window.input_unit.setCurrentIndex(window.input_unit.findData(INTERNATIONAL_FEET))
    window.output_unit.setCurrentIndex(window.output_unit.findData(METERS))
    window.longitude_combo.setCurrentIndex(
        window.longitude_combo.findData(LongitudeConvention.NEGATIVE_WEST)
    )
    if not window.convert():
        raise AssertionError(f"the run failed: {window.shown_failures}")
    return window


def test_fix_a_the_table_shows_the_elevation_in_the_output_unit(to_geodetic):
    """900 International feet in, metres out, on screen.

    Hand-derived. The International foot is 0.3048 m exactly (units.py), so

        900.000 ift x 0.3048 m/ift = 274.32 m exactly

    (900 x 0.3 = 270, 900 x 0.0048 = 4.32, sum 274.32.) Metres are written to
    4 decimal places, so the cell reads "274.3200".

    The elevation column is index 3 (results_model.ELEVATION_COLUMN). Before
    the fix it read "900.0000" - the input number relabelled as metres, which
    is 625.680 m from the truth - while the "Units out" line of the record in
    the same archive said metres.
    """
    assert cell(to_geodetic, 0, results_model.ELEVATION_COLUMN) == "274.3200"


def test_fix_a_the_screen_and_the_written_export_agree_on_the_elevation(
    to_geodetic,
):
    """UI honesty: the same string, not a string that rounds the same way.

    Read out of the archive that was actually written, so a divergence between
    the two surfaces would fail here rather than on a surveyor's disk.
    """
    exported = member_text(to_geodetic.written_files["archive"], "GEODETIC.csv")
    fields = exported.strip().split(",")

    # The clean export has no header row: field 3 of the single data line is
    # the elevation.
    assert fields[3] == cell(to_geodetic, 0, results_model.ELEVATION_COLUMN)
    # ... and it is the formatter's own string for the value the job produced.
    assert fields[3] == fmt.coordinate(
        to_geodetic.result.points[0].output_elevation, METERS
    )


# --------------------------------------------------------------------------
# Fix H - the table's headings name what the columns hold
# --------------------------------------------------------------------------


def headings(window) -> list[str]:
    """The horizontal header, as the table itself reports it."""
    return [
        window.model.headerData(
            section, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
        )
        for section in range(window.model.columnCount())
    ]


def test_fix_h_a_geodetic_result_renames_the_two_degree_columns(to_geodetic):
    """The values were always degrees; the headings called them a northing.

    ``row_strings`` has always rendered columns 1 and 2 as a latitude and a
    longitude on this branch, so the table labelled 42.73250000 "Northing".
    Only the two names move - the columns, their order and their alignment are
    unchanged.
    """
    assert headings(to_geodetic) == [
        "Point",
        "Latitude",
        "Longitude",
        "Elevation",
        "Grid scale factor",
        "Combined factor",
        "Warnings",
    ]
    assert headings(to_geodetic) == list(results_model.GEODETIC_COLUMNS)

    # The cells under those two headings really are the degrees, at 8 places.
    point = to_geodetic.result.points[0]
    assert cell(to_geodetic, 0, results_model.NORTHING_COLUMN) == fmt.latitude(
        point.output_northing
    )
    assert cell(to_geodetic, 0, results_model.EASTING_COLUMN) == fmt.longitude(
        point.output_easting
    )


def test_fix_h_a_zone_to_zone_result_keeps_the_linear_headings(converted):
    """The rename is for the one direction whose values are degrees.

    A Michigan Central -> Michigan South job puts grid coordinates in those two
    columns, so they keep the names the owner approved.
    """
    assert headings(converted) == list(results_model.COLUMNS)
    assert headings(converted)[1:3] == ["Northing", "Easting"]


def test_fix_h_an_empty_table_shows_the_ordinary_headings(window):
    """Nothing has been converted, so no direction has been run.

    Naming the columns after a direction the user has not run would be the
    interface answering a question it was not asked.
    """
    assert window.result is None
    assert window.model.rowCount() == 0
    assert headings(window) == list(results_model.COLUMNS)
    assert results_model.columns_for(None) == results_model.COLUMNS


def test_fix_h_the_headings_change_back_when_the_result_is_cleared(to_geodetic):
    """The model settles headings with rows, in one reset.

    A stale "Latitude" over an empty table, or over the next zone-to-zone job,
    would be the same wrong label the fix removed.
    """
    assert headings(to_geodetic)[1:3] == ["Latitude", "Longitude"]

    to_geodetic.model.set_result(None)

    assert to_geodetic.model.rowCount() == 0
    assert headings(to_geodetic) == list(results_model.COLUMNS)


def test_fix_h_both_unit_selectors_stay_enabled_in_every_direction(window):
    """A selector is disabled only if it governs nothing, and neither ever does.

    On a geodetic side, columns two and three are degrees and carry no linear
    unit - but the ELEVATION column still does, and that column is what the
    elevation factor and the combined factor are computed from. Greying the
    control out would make a wrong foot definition unselectable rather than
    unnecessary, which is a worse lie than the unqualified label was.
    """
    for source, target in (
        (UNCHOSEN, UNCHOSEN),
        (MI_SOUTH, MI_CENTRAL),
        (MI_SOUTH, GEODETIC),
        (GEODETIC, MI_SOUTH),
        (GEODETIC, GEODETIC),
    ):
        window.from_zone.setCurrentIndex(window.from_zone.findData(source))
        window.to_zone.setCurrentIndex(window.to_zone.findData(target))
        assert window.input_unit.isEnabled() is True
        assert window.output_unit.isEnabled() is True


def test_fix_h_the_unit_label_says_elevation_only_on_the_geodetic_side(window):
    """What changes is the LABEL, and it follows the end it belongs to.

    Each selector describes one END of the job, so the labels are driven by the
    two dropdowns separately rather than by ``direction()`` - the input side
    must describe itself while the output side is still unanswered.
    """
    # Nothing chosen: both sides are still ordinary linear columns.
    assert window.input_unit_label.text() == window_module.UNITS_LABEL
    assert window.output_unit_label.text() == window_module.UNITS_LABEL

    # Reading a geodetic file: only the INPUT label is qualified.
    window.from_zone.setCurrentIndex(window.from_zone.findData(GEODETIC))
    window.to_zone.setCurrentIndex(window.to_zone.findData(MI_SOUTH))
    assert (
        window.input_unit_label.text() == window_module.UNITS_LABEL_ELEVATION_ONLY
    )
    assert window.output_unit_label.text() == window_module.UNITS_LABEL

    # Writing a geodetic file: only the OUTPUT label is.
    window.from_zone.setCurrentIndex(window.from_zone.findData(MI_SOUTH))
    window.to_zone.setCurrentIndex(window.to_zone.findData(GEODETIC))
    assert window.input_unit_label.text() == window_module.UNITS_LABEL
    assert (
        window.output_unit_label.text() == window_module.UNITS_LABEL_ELEVATION_ONLY
    )


def test_fix_h_the_unit_tooltip_says_which_column_the_unit_governs(window):
    """The label is short, so the tooltip carries the reason.

    It names the elevation column and says why it still matters - the factors
    are computed from it - which is what makes an enabled control honest rather
    than merely un-greyed.
    """
    window.from_zone.setCurrentIndex(window.from_zone.findData(GEODETIC))
    window.to_zone.setCurrentIndex(window.to_zone.findData(MI_SOUTH))
    assert window.input_unit.toolTip() == window_module.UNITS_TOOLTIP_GEODETIC_IN
    assert window.output_unit.toolTip() == window_module.UNITS_TOOLTIP_ZONE_OUT
    assert "ELEVATION column only" in window.input_unit.toolTip()

    window.from_zone.setCurrentIndex(window.from_zone.findData(MI_SOUTH))
    window.to_zone.setCurrentIndex(window.to_zone.findData(GEODETIC))
    assert window.input_unit.toolTip() == window_module.UNITS_TOOLTIP_ZONE_IN
    assert window.output_unit.toolTip() == window_module.UNITS_TOOLTIP_GEODETIC_OUT
    assert "ELEVATION column only" in window.output_unit.toolTip()


def test_fix_h_a_zone_to_itself_is_a_real_job_and_the_docstring_says_so(window):
    """The docstring used to claim a guard that does not exist in the code.

    Michigan South in feet to Michigan South in metres is a conversion the
    surveyor asked for - the units are chosen independently of the zones - and
    even the identity case produces the per-point factors the audit CSV exists
    to report. The behaviour is unchanged by fix H; only the description of it
    was wrong, and a docstring that describes a guard nobody wrote is how the
    guard gets removed by someone "restoring" it.
    """
    window.from_zone.setCurrentIndex(window.from_zone.findData(MI_SOUTH))
    window.to_zone.setCurrentIndex(window.to_zone.findData(MI_SOUTH))

    # The behaviour: it is a job.
    assert window.direction() is Direction.ZONE_TO_ZONE

    # The description of it.
    text = window_module.direction_for.__doc__
    assert "A zone to ITSELF is deliberately not in that list" in text
    assert "not a conversion: geodetic to geodetic" in text
    assert "and a zone to itself" not in text
