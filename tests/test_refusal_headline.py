"""Work package R1 (DESIGN.md #73): the one-line Auto refusal, and a status
line that can never widen the window.

The owner's two instructions of 2026-10-29, about the Single point tab's
dialog for a point Auto could place in no Michigan county:

1. "change this warning to be a simple one line 'coordinates out of range' or
   something like that" - so the Auto refusal is shown as a one-line
   headline, chosen from the error's DATA (``outside_count``), and its full
   message, naming every point, moves under Show Details and into the status
   line's tooltip. Every other refusal is shown exactly as it was.
2. "when that error triggers the window expands larger than the screen" - the
   cause was every refusal, not that one: the status line was a non-wrapping
   QLabel given a refusal's first line, and refusal messages are single long
   lines, so the label's minimum width became the window's (2,908 px for the
   owner's case, measured before the fix). ``StatusLabel`` keeps the full
   text and shows it elided.

Every expected value is derived in the comment above it (docs/method/METHOD.md
section 4).
"""

from __future__ import annotations

import os
import types

# MUST precede any Qt import: the platform plugin is chosen at import time.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from michspc import job as job_module  # noqa: E402
from michspc.gui import controls, settings_store  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.status_label import StatusLabel  # noqa: E402
from michspc.gui.window import MainWindow  # noqa: E402
from michspc.job import AutoZoneUnplacedPointsError  # noqa: E402
from michspc.spc.frames import NAD83_2011, FrameMismatchError  # noqa: E402

NAD = controls.geodetic_choice(NAD83_2011)
AUTO_NAD = controls.auto_choice(NAD83_2011)

# The owner's case from the screenshot: 49.0 N, 86.0 W - in Ontario, north of
# Lake Superior and of every Michigan county polygon, so Auto finds no county. Typed positive west, the tabs' preselected
# convention (DESIGN.md #29).
OWNER_CASE = ("49.0", "86.0")
# 40.0 N, 84.0 W is in Ohio (test_gui_options.py's OHIO); 40.5 N, 84.5 W and
# 41.0 N, 85.5 W are in Ohio and Indiana. None is in a Michigan county.
OUTSIDE_ROWS = "1,40.0,84.0,,A\n2,40.5,84.5,,B\n3,41.0,85.5,,C\n"


def unplaced(total: int, outside: int) -> AutoZoneUnplacedPointsError:
    """An Auto refusal of ``total`` points, ``outside`` of them in no county."""
    return AutoZoneUnplacedPointsError(
        "the core's full message",
        points=tuple((str(i + 1), 40.0, -84.0) for i in range(total)),
        frame=NAD83_2011,
        outside_count=outside,
    )


# --------------------------------------------------------------------------
# The headline: one line, true of every point it counts.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "outside", "expected"),
    [
        # Every point outside: the owner's own words, singular and plural.
        (1, 1, "Coordinates out of range: 1 point is outside Michigan."),
        (3, 3, "Coordinates out of range: 3 points are outside Michigan."),
        # Every point claimed by two county polygons: "outside" would be false.
        (1, 0, "Auto could not choose a zone: 1 point lies where two counties overlap."),
        (2, 0, "Auto could not choose a zone: 2 points lie where two counties overlap."),
        # Mixed: a wording true of both kinds of point.
        (
            3,
            1,
            "Auto could not choose a zone: 3 points could not be placed in one "
            "Michigan county.",
        ),
    ],
)
def test_the_auto_refusal_headline(total, outside, expected):
    headline = controls.refusal_headline(unplaced(total, outside))
    assert headline == expected
    assert "\n" not in headline


@pytest.mark.parametrize(
    "error",
    [
        ValueError("Latitude 95 is out of range."),
        FrameMismatchError("No published transformation joins these frames."),
        TypeError("not a zone"),
    ],
)
def test_every_other_refusal_has_no_headline(error):
    """Only the Auto refusal is summarised; every other one is shown as raised."""
    assert controls.refusal_headline(error) is None
    message = str(error) or repr(error)
    assert controls.refusal_status(error) == f"Refused: {message.splitlines()[0]}"


def test_outside_count_cannot_exceed_the_points_it_counts():
    with pytest.raises(ValueError, match="cannot exceed"):
        unplaced(2, 3)


def test_the_core_counts_outside_points_from_each_points_own_reason():
    """``outside_count`` is built from each unplaced point's flag, which the
    row loop sets from WHICH zone_for refusal it caught - never read back out
    of the message. Two outside, one claimed twice: outside_count 2."""
    points = [
        job_module._UnplacedPoint(
            point_id=str(i),
            latitude=40.0,
            longitude=-84.0,
            frame=NAD83_2011,
            reason="in no Michigan county" if outside else "inside more than one",
            transformed_from=None,
            outside=outside,
        )
        for i, outside in enumerate((True, False, True))
    ]
    error = job_module._unplaced_points_refusal(points, types.SimpleNamespace(source="S"))
    assert error.outside_count == 2
    assert len(error.points) == 3


# --------------------------------------------------------------------------
# The dialog.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


def test_the_auto_dialog_is_the_headline_with_the_full_message_in_details(qapp):
    error = unplaced(1, 1)
    box = QMessageBox()
    controls.fill_failure_dialog(box, error)
    assert box.text() == "Coordinates out of range: 1 point is outside Michigan."
    # "it is not a summary" would be false of a headline, so there is none.
    assert box.informativeText() == ""
    # Every point stays one click away.
    assert box.detailedText() == str(error)


def test_every_other_dialog_is_unchanged(qapp):
    error = ValueError("Latitude 95 is out of range.")
    box = QMessageBox()
    controls.fill_failure_dialog(box, error)
    assert box.text() == "Latitude 95 is out of range."
    assert box.informativeText() == controls.FAILURE_INFORMATIVE_TEXT
    assert box.informativeText() == (
        "Nothing was written. This message names the problem exactly; it is "
        "not a summary."
    )
    assert box.detailedText().rstrip().endswith("ValueError: Latitude 95 is out of range.")


# --------------------------------------------------------------------------
# Both tabs, end to end.
# --------------------------------------------------------------------------


def recorded(win: MainWindow) -> MainWindow:
    win.shown_failures = []
    win._show_failure = lambda error: win.shown_failures.append(error)
    win._ask_overwrite = lambda existing, error: True
    tab = win.single_point
    tab.shown_failures = []
    tab._show_failure = lambda error: tab.shown_failures.append(error)
    return win


@pytest.fixture
def window(qapp):
    win = recorded(MainWindow(store=settings_store.MemoryStore()))
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def choose(combo, data) -> None:
    index = combo.findData(data)
    assert index >= 0, data
    combo.setCurrentIndex(index)


def minimum_widths(window) -> tuple[int, int, int]:
    """The window's, the current page's and the Single point tab's minimum widths."""
    return (
        window.minimumSizeHint().width(),
        window.tabs.currentWidget().minimumSizeHint().width(),
        window.single_point.minimumSizeHint().width(),
    )


def test_the_owners_case_on_the_single_point_tab(window, qapp):
    tab = window.single_point
    window.tabs.setCurrentWidget(tab)
    choose(tab.from_zone, NAD)
    choose(tab.to_zone, AUTO_NAD)
    tab.first_edit.setText(OWNER_CASE[0])
    tab.second_edit.setText(OWNER_CASE[1])
    # Measured after the selections, which change the form's own widths, so
    # only the refusal is compared.
    qapp.processEvents()
    before = minimum_widths(window)
    assert tab.convert() is False
    qapp.processEvents()
    error = tab.last_failure
    assert isinstance(error, AutoZoneUnplacedPointsError)
    assert error.outside_count == len(error.points) == 1
    assert tab.shown_failures == [error]
    assert tab.status_label.text() == (
        "Refused: Coordinates out of range: 1 point is outside Michigan."
    )
    assert tab.status_label.toolTip() == str(error)
    # The window did not grow (the label alone asked for 2,908 px before the
    # fix, measured in this package).
    after = minimum_widths(window)
    assert all(a <= b for a, b in zip(after, before)), (before, after)


def test_three_outside_points_on_the_multi_point_tab(window, qapp, tmp_path):
    source = tmp_path / "in.csv"
    source.write_text(OUTSIDE_ROWS, encoding="utf-8")
    window.tabs.setCurrentIndex(1)
    window.input_edit.setText(str(source))
    window.output_edit.setText(str(tmp_path))
    choose(window.from_zone, NAD)
    choose(window.to_zone, AUTO_NAD)
    assert window.convert() is False
    error = window.last_failure
    assert isinstance(error, AutoZoneUnplacedPointsError)
    assert error.outside_count == 3
    assert window.status_label.text() == (
        "Refused: Coordinates out of range: 3 points are outside Michigan."
    )
    assert window.status_label.toolTip() == str(error)
    assert list(tmp_path.glob("*.zip")) == []


# --------------------------------------------------------------------------
# The window never grows for a long refusal, on either tab.
# --------------------------------------------------------------------------

LONG = "x" * 600


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_600_character_refusal_does_not_widen_the_window(window, qapp, which):
    page = window.single_point if which == "single" else window
    window.tabs.setCurrentIndex(0 if which == "single" else 1)
    qapp.processEvents()
    before = minimum_widths(window)
    page._report_failure(ValueError(LONG))
    qapp.processEvents()
    after = minimum_widths(window)
    assert all(a <= b for a, b in zip(after, before)), (before, after)
    # The full text is the label's value; what is drawn is cut to fit.
    assert page.status_label.text() == f"Refused: {LONG}"
    shown = page.status_label.shown_text()
    assert shown.endswith("…")
    assert page.status_label.fontMetrics().horizontalAdvance(shown) <= max(
        page.status_label.width(), 0
    )


def test_the_status_label_keeps_short_text_whole(qapp):
    label = StatusLabel("Ready.")
    label.resize(400, 20)
    assert label.text() == "Ready."
    assert label.shown_text() == "Ready."
    assert label.minimumSizeHint().width() == 0


def test_both_tabs_build_their_status_line_from_status_label(window):
    assert type(window.status_label) is StatusLabel
    assert type(window.single_point.status_label) is StatusLabel
