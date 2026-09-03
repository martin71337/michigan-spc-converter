"""Drag-and-drop of the input file onto the Multi point tab, tested headless.

Every event below is a real ``QDragEnterEvent`` / ``QDropEvent`` sent through
``QApplication.sendEvent``, carrying a real ``QMimeData`` with a ``file://``
URL — the same object Explorer's drop hands the widget — rather than a call to
the handler with a path. Measured on the unchanged code before this feature
was built (offscreen platform): the tab's page did not accept drops at all,
and a file dropped on the Input file box left it empty — there was no drop
path. The box's own drop handling is text insertion (a ``QLineEdit``'s
default), so the design keeps drops OFF the boxes and ON the page.

**One entry point.** The drop and the Browse dialog have to land the same
string in the same box, so the tests compare the two routes against each other
rather than against a literal spelled here (docs/DESIGN.md section 7, "one
entry point per data path").
"""

from __future__ import annotations

import os

# MUST precede any Qt import (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import QMimeData, QPoint, QPointF, QUrl, Qt  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from michspc.gui import window as window_module  # noqa: E402
from michspc.gui.window import (  # noqa: E402
    MainWindow,
    MultiPointPage,
    dropped_input_file,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp):
    win = MainWindow()
    yield win
    win.close()


@pytest.fixture
def points_file(tmp_path) -> Path:
    path = tmp_path / "pts.csv"
    path.write_text("1,100.0,200.0,300.0,IP\n", encoding="utf-8")
    return path


def mime_for(*urls: QUrl) -> QMimeData:
    mime = QMimeData()
    mime.setUrls(list(urls))
    return mime


def local(path: Path) -> QUrl:
    return QUrl.fromLocalFile(str(path))


def drag_enter(target, mime: QMimeData) -> QDragEnterEvent:
    event = QDragEnterEvent(
        QPoint(5, 5),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(target, event)
    return event


def drop(target, mime: QMimeData) -> QDropEvent:
    """A drop the way the platform delivers one: an enter, then the drop.

    Measured fact, not a convenience: ``QApplication.notify`` delivers a
    ``Drop`` only to the widget whose ``DragEnter`` it last saw accepted, so
    a drop sent cold is discarded before any handler runs. A real drag always
    enters first, so this helper does too.
    """
    drag_enter(target, mime)
    event = QDropEvent(
        QPointF(5, 5),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(target, event)
    return event


def browse_result(window, chosen: Path) -> str:
    """What the Browse button would leave in the box for ``chosen``.

    Drives the real ``_choose_input_file`` with the dialog's static function
    replaced, so the string compared against is the one the dialog route
    produces — not a guess at it.
    """
    real = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = staticmethod(
        lambda *args, **kwargs: (local(chosen).toLocalFile(), "")
    )
    try:
        window._choose_input_file()
    finally:
        QFileDialog.getOpenFileName = real
    return window.input_edit.text()


# --------------------------------------------------------------------------
# The rule: exactly one local file
# --------------------------------------------------------------------------


def test_one_local_file_is_the_only_drop_the_rule_accepts(points_file, tmp_path):
    """``dropped_input_file`` answers the file, and nothing else.

    Every refusal is a case where the program would otherwise have to guess:
    which of two files, whether a folder was meant for the output box, what
    a web address is doing on a coordinate tool. Guessing is the failure
    mode the longitude rule exists to prevent (docs/DESIGN.md section 7), so
    the rule answers None and the drag is refused before it lands.
    """
    other = tmp_path / "other.csv"
    other.write_text("2,1.0,2.0,3.0,X\n", encoding="utf-8")
    folder = tmp_path / "out"
    folder.mkdir()

    assert dropped_input_file(mime_for(local(points_file))) == points_file

    assert dropped_input_file(mime_for(local(points_file), local(other))) is None
    assert dropped_input_file(mime_for(local(folder))) is None
    assert dropped_input_file(mime_for(local(tmp_path / "missing.csv"))) is None
    assert dropped_input_file(mime_for(QUrl("https://geodesy.noaa.gov/pts.csv"))) is None
    assert dropped_input_file(mime_for()) is None

    text_only = QMimeData()
    text_only.setText(str(points_file))
    assert dropped_input_file(text_only) is None


# --------------------------------------------------------------------------
# The page is the drop target; the boxes are not
# --------------------------------------------------------------------------


def test_the_multi_point_page_is_the_drop_target_and_its_children_are_not(window):
    """A file dropped ANYWHERE on the tab reaches the page's handler.

    Qt delivers a drag to the nearest ancestor of the widget under the cursor
    that accepts drops, so this is two facts: the page accepts, and the
    widgets a cursor would naturally hover — the two path boxes, the table
    and the status line — do not. A ``QLineEdit`` that still accepted would
    catch the drop itself and handle it as text to insert, and the text of a
    ``file://`` URL is not a path.
    """
    page = window.multi_point_page
    assert isinstance(page, MultiPointPage)
    assert page.acceptDrops()
    assert window.tabs.widget(1) is page

    for name in ("input_edit", "output_edit", "table", "status_label"):
        assert not getattr(window, name).acceptDrops(), name
    assert not window.table.viewport().acceptDrops()
    assert not window.single_point.acceptDrops()


def test_dropping_a_file_on_the_page_lands_its_path_in_the_input_box(
    window, points_file
):
    """The drop fills the Input file box with the dropped file's path.

    Compared against the Browse route for the same file, not a literal: the
    two must agree to the character, because the box is what ``input_path``
    reads and what ``job.run`` opens.
    """
    enter = drag_enter(window.multi_point_page, mime_for(local(points_file)))
    assert enter.isAccepted()

    dropped = drop(window.multi_point_page, mime_for(local(points_file)))
    assert dropped.isAccepted()

    by_drop = window.input_edit.text()
    assert window.input_path == points_file
    assert Path(by_drop).is_file()

    window.input_edit.setText("")
    assert browse_result(window, points_file) == by_drop


def test_a_drop_replaces_the_path_already_in_the_box(window, points_file, tmp_path):
    """Replace, never insert.

    A ``QLineEdit``'s own drop inserts at the cursor, which would leave two
    paths concatenated into one string. The box names ONE file.
    """
    stale = tmp_path / "stale.csv"
    stale.write_text("9,1.0,2.0,3.0,X\n", encoding="utf-8")
    window.input_edit.setText(str(stale))

    drop(window.multi_point_page, mime_for(local(points_file)))

    assert window.input_path == points_file
    assert str(stale) not in window.input_edit.text()


def test_a_drop_enables_convert_exactly_as_the_dialog_would(
    window, points_file, tmp_path
):
    """The drop goes through the same ``textChanged`` gate as typing.

    With every other field answered, Convert is disabled while the input box
    is empty and enabled the moment the drop lands - the same signal the
    Browse dialog fires, because the drop calls the same setter.
    """
    from michspc.gui.window import geodetic_choice  # noqa: F401 - documents the tab
    from michspc.spc.zones import zone_by_code

    window.output_edit.setText(str(tmp_path))
    window.from_zone.setCurrentIndex(
        window.from_zone.findData(zone_by_code(2112))
    )
    window.to_zone.setCurrentIndex(window.to_zone.findData(zone_by_code(2113)))
    assert not window.convert_button.isEnabled()

    drop(window.multi_point_page, mime_for(local(points_file)))

    assert window.convert_button.isEnabled()


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["two files", "folder", "missing", "web"])
def test_a_drop_the_rule_refuses_is_refused_at_the_border_and_changes_nothing(
    window, points_file, tmp_path, case
):
    """The drag is refused on entry, and a drop after it changes nothing.

    Refusing at ``dragEnterEvent`` is what makes Explorer show the no-drop
    cursor, so the user learns before letting go. The drop that follows is
    refused twice over: Qt does not deliver it to a widget whose enter was
    refused, and ``dropEvent`` asks the rule again if it ever arrived.
    """
    other = tmp_path / "other.csv"
    other.write_text("2,1.0,2.0,3.0,X\n", encoding="utf-8")
    folder = tmp_path / "out"
    folder.mkdir()
    mime = {
        "two files": mime_for(local(points_file), local(other)),
        "folder": mime_for(local(folder)),
        "missing": mime_for(local(tmp_path / "missing.csv")),
        "web": mime_for(QUrl("https://geodesy.noaa.gov/pts.csv")),
    }[case]

    before = "C:/jobs/24-118/typed.csv"
    window.input_edit.setText(before)

    enter = drag_enter(window.multi_point_page, mime)
    assert not enter.isAccepted()

    dropped = drop(window.multi_point_page, mime)
    assert not dropped.isAccepted()
    assert window.input_edit.text() == before
    assert window.output_edit.text() == ""


# --------------------------------------------------------------------------
# The result on screen follows the box's own policy
# --------------------------------------------------------------------------


def test_a_drop_after_a_conversion_leaves_the_written_result_on_screen(
    window, points_file, tmp_path
):
    """This tab's table describes an archive that was WRITTEN.

    It does not clear when the input box changes by typing or browsing
    (``_clear_table``'s docstring), so it does not clear for a drop either:
    the drop is the same setter. Pinned so a later change cannot make the
    three routes disagree.
    """
    from michspc.spc.zones import zone_by_code

    job = tmp_path / "job.csv"
    # Michigan Central, a point near Lansing in International feet
    # (the same shape tests/test_gui.py converts end to end).
    job.write_text("1,410000.000,12750000.000,850.000,IP\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()

    window.input_edit.setText(str(job))
    window.output_edit.setText(str(out))
    window.from_zone.setCurrentIndex(
        window.from_zone.findData(zone_by_code(2112))
    )
    window.to_zone.setCurrentIndex(window.to_zone.findData(zone_by_code(2113)))
    assert window.convert()
    assert window.result is not None
    rows = window.model.rowCount()
    assert rows == 1

    drop(window.multi_point_page, mime_for(local(points_file)))

    assert window.input_path == points_file
    assert window.result is not None
    assert window.model.rowCount() == rows
