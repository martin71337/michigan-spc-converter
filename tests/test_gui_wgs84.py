"""Work package W5 of the WGS 84 build: the five frames reach the screen.

What this package made reachable, and therefore what has to be pinned
(docs/PLAN-wgs84.md section 3.7, DESIGN.md #70):

* **Five new geodetic entries** in all four zone dropdowns - WGS84(G1762),
  (G2139), (G2296), ITRF2014 and ITRF2020 - each labelled from its own record
  (#58), in a block of their own below a separator. The bare "WGS 84" label is
  never offered (plan decision D2).
* **A geodetic-to-geodetic direction**, only across one of the ten HTDP paths
  (D7). Two global frames (D4) and a global frame against NATRF2022 (D3) are
  still not a direction, and a cross-frame pair the interface can be made to
  hold still refuses at Convert in the core's own words.
* **An observation date control** that opens UNANSWERED, is enabled only when
  a selected side's frame is time-dependent, and is sent to the core only
  then. No default date: a Michigan point moves about 17 mm a year against
  NAD 83 in these frames, so a preselected date is a guessed position.
* **Both positions on the Single point panel**, each named by its frame, and
  the Multi point table's headings naming the frame its cells are in, from
  the file layer's own rules.
* **The job-level realization warning** in both tabs' warnings surfaces.
* **HTDP's refusal caught by name** on both tabs (interim gate 2, finding L4).
* **Every control invalidates a displayed Single point result** - the
  amendment #26 / #43 CRITICAL class - pinned per control.

Every expected value is derived in the comment above it (docs/method/METHOD.md
section 4). Values the core computes are compared against the core's own
records, rendered through the formatters the files use: the interface must
display what ``job.run`` returned, never a number of its own.
"""

from __future__ import annotations

import csv
import datetime
import os
import re

# MUST precede any Qt import: the platform plugin is chosen at import time and a
# later change is ignored (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import QDate, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from michspc import job as job_module  # noqa: E402
from michspc.fileio import exports, formatting as fmt, geoid  # noqa: E402
from michspc.gui import controls, results_model  # noqa: E402
from michspc.gui import single_point as single_point_module  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.single_point import INCOMPLETE_FORM  # noqa: E402
from michspc.gui.window import MainWindow  # noqa: E402
from michspc.job import (  # noqa: E402
    Direction,
    LongitudeConvention,
    VerticalMode,
    WarningCode,
)
from michspc.spc import htdp  # noqa: E402
from michspc.spc.frames import (  # noqa: E402
    ALL_FRAMES,
    ITRF2020,
    NAD83_2011,
    NATRF2022,
    WGS84,
    WGS84_G2139,
    WGS84_G2296,
    FrameTransformationUnavailableError,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS  # noqa: E402
from michspc.spc.vertical import NAVD88, HeightKind  # noqa: E402
from michspc.spc.convert import project_point  # noqa: E402
from michspc.spc.zones import MI_CENTRAL, MI_SOUTH, zone_by_code  # noqa: E402
from tests.conftest import member_text  # noqa: E402
from tests.fixtures.htdp_w3_anchors import (  # noqa: E402
    L5_RECORDS,
    L5_REVERSE_RECORDS,
)

NAD = controls.geodetic_choice(NAD83_2011)
NAT = controls.geodetic_choice(NATRF2022)
G2296 = controls.geodetic_choice(WGS84_G2296)
G2139 = controls.geodetic_choice(WGS84_G2139)
I2020 = controls.geodetic_choice(ITRF2020)
FIVE = tuple(f for f in ALL_FRAMES if f.is_usable and f.is_time_dependent)
STATEWIDE_2022 = zone_by_code("260001")

OBSERVED = datetime.date(2025, 6, 15)
"""Inside G2296's period of use (from 2024-01-07, no end yet, NGA via
frames._WGS84_IN_USE_FROM), and before the day this suite runs, so a G2296
job dated on it raises no warning and no refusal."""

OUTSIDE_PERIOD = datetime.date(2012, 6, 15)
"""Before G2296 came into use on 2024-01-07, so a G2296 job dated on it
raises exactly one job-level REALIZATION_OUTSIDE_PERIOD_OF_USE warning
(plan decision D9) - and still converts, because that is a warning."""

# Typed in positive west, the tabs' preselected convention (DESIGN.md #29):
# 42.7325 N, 84.5555 W - Lansing, inside Michigan South and the HTDP window.
LATITUDE_TEXT = "42.7325"
LONGITUDE_TEXT = "84.5555"
HEIGHT_TEXT = "200.000"


# --------------------------------------------------------------------------
# Fixtures and helpers
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    """One QApplication for the whole module (docs/method/TOOLING.md)."""
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


@pytest.fixture
def window(qapp):
    """A window whose modal dialogs and clipboard are replaced by recorders."""
    win = MainWindow()
    win.shown_failures = []
    win._show_failure = lambda error: win.shown_failures.append(
        str(error) or repr(error)
    )
    win._ask_overwrite = lambda existing, error: True

    tab = win.single_point
    tab.shown_failures = []
    tab._show_failure = lambda error: tab.shown_failures.append(
        str(error) or repr(error)
    )
    tab.clipboard = []
    tab._set_clipboard = tab.clipboard.append
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


def answer_date(page, date: datetime.date) -> None:
    page.observation_date_edit.setDate(QDate(date.year, date.month, date.day))


def typed_wgs84_to_zone(tab, date=OBSERVED, kind=HeightKind.ELLIPSOID) -> None:
    """A displayed WGS84(G2296) -> Michigan South single-point result."""
    choose(tab.from_zone, G2296)
    choose(tab.to_zone, MI_SOUTH)
    choose(tab.height_kind_combo, kind)
    tab.first_edit.setText(LATITUDE_TEXT)
    tab.second_edit.setText(LONGITUDE_TEXT)
    tab.elevation_edit.setText(HEIGHT_TEXT)
    answer_date(tab, date)
    assert tab.convert() is True, tab.shown_failures
    assert tab.result is not None
    assert tab.result.points[0].conversion.is_transformed


def file_job(window, tmp_path, rows: str) -> None:
    source = tmp_path / "in.csv"
    source.write_text(rows, encoding="utf-8")
    window.input_edit.setText(str(source))
    window.output_edit.setText(str(tmp_path))


def audit_rows(window) -> list[list[str]]:
    archive = next(iter(window.written_files.values()))
    return list(csv.reader(member_text(archive, "_full.csv").splitlines()))


def table_headings(window) -> list[str]:
    model = window.model
    return [
        model.headerData(column, Qt.Orientation.Horizontal)
        for column in range(model.columnCount())
    ]


def table_cells(window, row: int = 0) -> list[str]:
    model = window.model
    return [model.data(model.index(row, c)) for c in range(model.columnCount())]


def rows_of(section) -> dict[str, str]:
    return {value.label: value.text for value in section.values}


# ==========================================================================
# 1. The dropdown entries.
# ==========================================================================


def test_the_five_frames_are_offered_in_their_own_block_on_every_combo(window):
    """Seven geodetic entries in two blocks, split by the frame record.

    Derived: the plate-fixed block is every offered frame whose
    ``is_time_dependent`` is False (NAD83(2011), NATRF2022), the global block
    every one where it is True (the five), in ALL_FRAMES declaration order, and
    exactly one separator (data None, text "") lies between the blocks. The
    bare WGS 84 record is in neither: it is declared not usable (D2).
    """
    plate_fixed, time_dependent = controls.geodetic_choice_groups()
    assert [c.frame for c in plate_fixed] == [NAD83_2011, NATRF2022]
    assert [c.frame for c in time_dependent] == list(FIVE)
    assert WGS84 not in [c.frame for c in controls.GEODETIC_CHOICES]

    for combo in (
        window.from_zone,
        window.to_zone,
        window.single_point.from_zone,
        window.single_point.to_zone,
    ):
        data = [combo.itemData(i) for i in range(combo.count())]
        # 0 placeholder, 1-2 plate-fixed, 3 separator, 4-8 the five.
        assert data[1:3] == list(plate_fixed)
        assert data[3] is None and combo.itemText(3) == ""
        assert data[4:9] == list(time_dependent)
        assert data[9] is None  # the separator above the SPCS 83 zones
        for i in range(4, 9):
            assert combo.itemText(i) == controls.geodetic_label(data[i].frame)


def test_a_d4_or_d3_pair_is_grayed_and_is_no_direction(window):
    """Two global frames (D4) and a global frame against NATRF2022 (D3).

    The graying asks the registry (``frames_have_a_path``): G2296 has a path
    to NAD83(2011) only, so with G2296 chosen at From every other global
    entry, NATRF2022's entry and every 2022 zone gray at To, and NAD83(2011)
    geodetic and the three SPCS 83 zones stay choosable. Forced into the
    dropdowns by code, the pairs still describe no job.
    """
    tab = window.single_point
    choose(tab.from_zone, G2296)
    model = tab.to_zone.model()

    def enabled(data):
        index = tab.to_zone.findData(data)
        return bool(model.item(index).flags() & Qt.ItemFlag.ItemIsEnabled)

    assert enabled(NAD)
    assert not enabled(NAT)
    for frame in FIVE:
        assert not enabled(controls.geodetic_choice(frame))
    assert not enabled(STATEWIDE_2022)
    assert enabled(MI_SOUTH)

    assert controls.direction_for(G2296, G2139) is None  # D4
    assert controls.direction_for(G2296, I2020) is None  # D4
    assert controls.direction_for(G2296, G2296) is None  # same frame
    assert controls.direction_for(G2296, NAT) is None  # D3
    assert controls.direction_for(NAT, G2296) is None  # D3
    assert controls.direction_for(G2296, NAD) is Direction.GEODETIC_TO_GEODETIC
    assert controls.direction_for(NAD, G2296) is Direction.GEODETIC_TO_GEODETIC


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_d3_pair_forced_past_the_graying_refuses_at_convert(
    window, which, tmp_path
):
    """WGS84(G2296) geodetic into a 2022 zone: a direction, refused by the core.

    The graying stops a user choosing it; code can still select a disabled
    item (pinned in tests/test_gui_frames.py), and then the pair IS a
    direction (GEODETIC_TO_ZONE) - so the core's refusal must reach the
    refusal surface verbatim, as NATRF2022 cross-frame does today (#62).
    """
    page = pages(window)[which]
    if which == "multi":
        file_job(window, tmp_path, f"1,43.0,84.5,{HEIGHT_TEXT},A\n")
    else:
        page.first_edit.setText("43.0")
        page.second_edit.setText("84.5")
    choose(page.to_zone, STATEWIDE_2022)
    page.from_zone.blockSignals(True)
    try:
        choose(page.from_zone, G2296)
    finally:
        page.from_zone.blockSignals(False)
    page._on_direction_changed()
    answer_date(page, OBSERVED)
    choose(page.input_unit, METERS)
    choose(page.output_unit, METERS)
    assert page.direction() is Direction.GEODETIC_TO_ZONE

    assert page.convert() is False
    assert isinstance(page.last_failure, FrameTransformationUnavailableError)
    shown = page.shown_failures[-1]
    assert shown == str(page.last_failure)
    assert "WGS84(G2296)" in shown and "NATRF2022" in shown
    assert page.result is None


# ==========================================================================
# 2. Direction and settings.
# ==========================================================================


@pytest.mark.parametrize("which", ["single", "multi"])
@pytest.mark.parametrize("forward", [True, False])
def test_a_geodetic_to_geodetic_pair_builds_the_core_job(
    window, which, forward, tmp_path
):
    """Both ends geodetic across an HTDP path: GEODETIC_TO_GEODETIC.

    ``geodetic_frame`` is the INPUT frame (From), ``target_geodetic_frame``
    the OUTPUT frame (To), no zone at either end, the longitude convention is
    asked (both ends are degrees) and the date is sent, because one end is
    time-dependent.
    """
    page = pages(window)[which]
    source, target = (G2296, NAD) if forward else (NAD, G2296)
    if which == "multi":
        file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
    else:
        page.first_edit.setText(LATITUDE_TEXT)
        page.second_edit.setText(LONGITUDE_TEXT)
    choose(page.from_zone, source)
    choose(page.to_zone, target)
    assert page.longitude_combo.isEnabled()
    assert page.observation_date_edit.isEnabled()
    assert page.settings() is None  # the date is unanswered
    answer_date(page, OBSERVED)

    settings = page.settings()
    assert settings is not None
    assert settings.direction is Direction.GEODETIC_TO_GEODETIC
    assert settings.geodetic_frame is source.frame
    assert settings.target_geodetic_frame is target.frame
    assert settings.source_zone is None and settings.target_zone is None
    assert settings.observation_date == OBSERVED
    assert settings.longitude_convention is LongitudeConvention.POSITIVE_WEST

    assert page.convert() is True, page.shown_failures


@pytest.mark.parametrize("which", ["single", "multi"])
def test_no_other_direction_states_a_target_geodetic_frame(window, which, tmp_path):
    """``target_geodetic_frame`` is refused by the core on every other direction.

    So a WGS 84 geodetic-to-zone job and a zone-to-WGS 84 job leave it None.
    """
    page = pages(window)[which]
    if which == "multi":
        file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
    else:
        page.first_edit.setText(LATITUDE_TEXT)
        page.second_edit.setText(LONGITUDE_TEXT)
    answer_date(page, OBSERVED)
    choose(page.from_zone, G2296)
    choose(page.to_zone, MI_SOUTH)
    assert page.settings().target_geodetic_frame is None
    choose(page.from_zone, MI_SOUTH)
    choose(page.to_zone, G2296)
    settings = page.settings()
    assert settings.direction is Direction.ZONE_TO_GEODETIC
    assert settings.geodetic_frame is WGS84_G2296
    assert settings.target_geodetic_frame is None


# ==========================================================================
# 3. The observation date control.
# ==========================================================================


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_date_opens_unanswered_and_names_no_date(window, which):
    """No default date - not today, not any date.

    The control holds the sentinel minimum (Qt's own 1752-09-14), so Qt
    shows the special value text "— choose —" in place of a date, and the
    reader returns None. The displayed text carries no digit at all, so it
    cannot be read as a date; and it is not today's, the preselect the brief
    forbids.
    """
    edit = pages(window)[which].observation_date_edit
    assert edit.date() == controls.OBSERVATION_DATE_UNANSWERED
    assert edit.minimumDate() == controls.OBSERVATION_DATE_UNANSWERED
    assert edit.text() == controls.UNANSWERED_TEXT == "— choose —"
    assert not any(ch.isdigit() for ch in edit.text())
    assert controls.observation_date_for(edit) is None
    assert edit.is_answered() is False
    today = job_module.today()
    assert edit.date() != QDate(today.year, today.month, today.day)
    # ISO display, year first, the form the record prints.
    assert edit.displayFormat() == "yyyy-MM-dd"
    assert edit.calendarPopup() is True


@pytest.mark.parametrize("which", ["single", "multi"])
def test_an_unanswered_date_cannot_be_submitted(window, which, tmp_path):
    """Everything answered but the date: no settings, Convert disabled, and
    a direct call refuses rather than running.

    Then the date answered and nothing else touched: the form completes. So
    the date, and nothing else, was what held it.
    """
    page = pages(window)[which]
    if which == "multi":
        file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
    else:
        page.first_edit.setText(LATITUDE_TEXT)
        page.second_edit.setText(LONGITUDE_TEXT)
    choose(page.from_zone, G2296)
    choose(page.to_zone, MI_SOUTH)

    assert page.settings() is None
    assert page.convert_button.isEnabled() is False
    assert page.convert() is False
    assert page.result is None
    if which == "single":
        assert page.shown_failures[-1] == INCOMPLETE_FORM
    assert "observation date" in page.shown_failures[-1]

    answer_date(page, OBSERVED)
    assert page.settings() is not None
    assert page.convert_button.isEnabled() is True


def test_the_unanswered_state_cannot_be_stepped_typed_or_wheeled_into_a_date(tab):
    """The stock widget would answer the question three ways nobody chose.

    Measured on the stock QDateEdit: Up from the sentinel steps its YEAR to
    1753-09-14, and typed digits are appended to "— choose —" without ever
    becoming a date. On this control, in the unanswered state, stepping is
    off and keys are swallowed, so the box neither holds a date nor shows
    something resembling one; the wheel is handed on. Once a date is chosen
    the control is the stock widget again and Up steps the day section.
    """
    edit = tab.observation_date_edit
    choose(tab.from_zone, G2296)  # enables the control
    assert edit.isEnabled()
    tab.show()
    edit.setFocus()

    QTest.keyClick(edit, Qt.Key.Key_Up)
    QTest.keyClick(edit, Qt.Key.Key_PageUp)
    edit.stepBy(1)
    QTest.keyClicks(edit, "20250615")
    QApplication.sendEvent(
        edit,
        QWheelEvent(
            QPointF(5, 5),
            QPointF(5, 5),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        ),
    )
    assert edit.date() == controls.OBSERVATION_DATE_UNANSWERED
    assert edit.text() == controls.UNANSWERED_TEXT
    assert controls.observation_date_for(edit) is None

    answer_date(tab, OBSERVED)
    edit.setCurrentSection(edit.Section.DaySection)
    edit.stepBy(1)
    # 2025-06-15 plus one day.
    assert controls.observation_date_for(edit) == datetime.date(2025, 6, 16)


def test_the_calendar_opens_on_this_month_without_answering(tab, monkeypatch):
    """The page moves to today's month; the held date does not move at all.

    ``job.today`` is the clock (the core's future-date seam), set here to
    2026-10-21, so the page shown is October 2026 - and the control is still
    unanswered when the calendar is shown and after it is hidden.
    """
    monkeypatch.setattr(job_module, "today", lambda: datetime.date(2026, 10, 21))
    edit = tab.observation_date_edit
    choose(tab.from_zone, G2296)  # enables the control
    tab.show()
    calendar = edit.calendarWidget()
    # Opened the way a user opens it: a click on the drop-down arrow at the
    # control's right-hand edge (measured: QDateEdit opens its popup there).
    QTest.mouseClick(
        edit,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(edit.width() - 4, edit.height() // 2),
    )
    assert calendar.isVisible()
    assert (calendar.yearShown(), calendar.monthShown()) == (2026, 10)
    assert edit.is_answered() is False
    calendar.window().hide()
    assert edit.is_answered() is False
    assert controls.observation_date_for(edit) is None


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_date_is_enabled_only_for_a_time_dependent_selection(window, which):
    """Grayed unless a SELECTED side's frame is time-dependent.

    Zones are on NAD83(2011) or NATRF2022 (plate-fixed); geodetic entries
    carry their frame. In vertical-only mode only the From selection counts:
    the To dropdown is hidden, and a hidden selection must not ask for a date.
    """
    page = pages(window)[which]
    edit = page.observation_date_edit
    assert edit.isEnabled() is False  # nothing chosen

    choose(page.from_zone, MI_SOUTH)
    choose(page.to_zone, MI_CENTRAL)
    assert edit.isEnabled() is False
    choose(page.to_zone, NAD)
    assert edit.isEnabled() is False
    choose(page.to_zone, G2296)
    assert edit.isEnabled() is True
    assert page.observation_date_label.isEnabled() is True
    choose(page.from_zone, NAD)
    assert edit.isEnabled() is True  # G2G, the target is time-dependent

    # Vertical-only: To (still G2296) is hidden and does not count.
    page.mode_vertical_only.setChecked(True)
    choose(page.from_zone, MI_SOUTH)
    assert edit.isEnabled() is False
    choose(page.from_zone, G2296)
    assert edit.isEnabled() is True
    page.mode_horizontal.setChecked(True)


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_date_left_in_the_control_is_not_sent_to_a_job_that_reads_none(
    window, which, tmp_path
):
    """The core refuses a stray observation_date by name, so the tab sends none.

    The date was answered for a WGS 84 job; the selection then moved to
    NAD83(2011) geodetic -> Michigan South, which reads no time-dependent
    frame. The control is grayed and keeps its value, and the settings carry
    observation_date None - so the job runs rather than refusing.
    """
    page = pages(window)[which]
    if which == "multi":
        file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
    else:
        page.first_edit.setText(LATITUDE_TEXT)
        page.second_edit.setText(LONGITUDE_TEXT)
    choose(page.from_zone, G2296)
    choose(page.to_zone, MI_SOUTH)
    answer_date(page, OBSERVED)
    assert page.settings().observation_date == OBSERVED

    choose(page.from_zone, NAD)
    assert page.observation_date_edit.isEnabled() is False
    assert controls.observation_date_for(page.observation_date_edit) == OBSERVED
    settings = page.settings()
    assert settings.observation_date is None
    assert page.convert() is True, page.shown_failures

    # And in vertical-only mode with a zone input, the same.
    page.mode_vertical_only.setChecked(True)
    choose(page.from_zone, MI_SOUTH)
    choose(page.vertical_source_combo, NAVD88)
    choose(page.vertical_target_combo, NAVD88)
    assert page.settings().observation_date is None


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_future_date_is_the_cores_refusal_shown_verbatim(
    window, which, tmp_path, monkeypatch
):
    """No second rule in the interface: the core refuses, the tab shows it.

    ``job.today`` is set to 2026-10-21; the date chosen is the day after.
    The control accepts it (no maximum is set - the control's maximum is Qt's
    9999-12-31), Convert is offered, and the refusal is job.run's own
    sentence, which names both dates.
    """
    monkeypatch.setattr(job_module, "today", lambda: datetime.date(2026, 10, 21))
    page = pages(window)[which]
    assert page.observation_date_edit.maximumDate() == QDate(9999, 12, 31)
    if which == "multi":
        file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
    else:
        page.first_edit.setText(LATITUDE_TEXT)
        page.second_edit.setText(LONGITUDE_TEXT)
    choose(page.from_zone, G2296)
    choose(page.to_zone, MI_SOUTH)
    answer_date(page, datetime.date(2026, 10, 22))
    assert page.convert_button.isEnabled() is True

    assert page.convert() is False
    shown = page.shown_failures[-1]
    assert shown == str(page.last_failure)
    assert "2026-10-22" in shown and "2026-10-21" in shown
    assert "future" in shown
    assert page.result is None


# ==========================================================================
# 4. Results display.
# ==========================================================================


def test_the_single_point_panel_shows_both_positions_under_their_frames(tab):
    """WGS84(G2296) in, Michigan South out: the typed position under G2296's
    name, the NAD83(2011) pivot under NAD83's, never one under the other.

    Expected values are the core's own records rendered by the panel's
    formatters: the INPUT rows are ``external_position`` (what was typed,
    carried as given), the OUTPUT geodetic rows ``conversion.latitude`` /
    ``longitude`` (the pivot, plan decision D5), and the two differ - at
    Lansing in 2025 by about 1 m - so a swap cannot pass.
    """
    typed_wgs84_to_zone(tab)
    point = tab.result.points[0]
    conversion = point.conversion
    external = conversion.external_position
    source, target = tab.sections
    inp, out = rows_of(source), rows_of(target)

    assert inp["Latitude (WGS84(G2296))"] == fmt.latitude_display(external.latitude)
    assert inp["Latitude (WGS84(G2296), DMS)"] == fmt.latitude_dms(external.latitude)
    assert inp["Longitude (WGS84(G2296))"] == fmt.longitude_display(
        external.longitude, positive_west=True
    )
    assert inp["Longitude (WGS84(G2296), DMS)"] == fmt.longitude_dms(external.longitude)
    assert inp["Observation date"] == "2025-06-15"
    # What was typed, exactly: 42.7325 N, 84.5555 W in positive west.
    assert inp["Latitude (WGS84(G2296))"] == "42.73250000°"
    assert inp["Longitude (WGS84(G2296))"] == "84.55550000°"

    assert out["Latitude (NAD83(2011))"] == fmt.latitude_display(conversion.latitude)
    assert out["Longitude (NAD83(2011))"] == fmt.longitude_display(
        conversion.longitude, positive_west=True
    )
    assert out["Latitude (NAD83(2011), DMS)"] == fmt.latitude_dms(conversion.latitude)
    assert out["Longitude (NAD83(2011), DMS)"] == fmt.longitude_dms(
        conversion.longitude
    )
    assert inp["Latitude (WGS84(G2296))"] != out["Latitude (NAD83(2011))"]
    # No unlabelled latitude anywhere on a transformed job.
    for section in tab.sections:
        for value in section.values:
            assert value.label not in ("Latitude", "Longitude", "Latitude (DMS)")


def test_the_ellipsoid_heights_are_named_by_their_frames(tab):
    """D6: the typed h is in the source frame, the horizontal output's in the
    target frame, both in the job's unit, and they are different numbers.

    Input: 200.000 ift typed, in WGS84(G2296). Output: HTDP's NAD83(2011) h
    re-expressed in ift - ``point.output_elevation``, which the core holds
    equal to ``target_frame_ellipsoid_height`` / 0.3048.
    """
    typed_wgs84_to_zone(tab)
    point = tab.result.points[0]
    inp, out = (rows_of(s) for s in tab.sections)
    assert inp["Ellipsoid height (WGS84(G2296), ift)"] == "200.000"
    assert out["Ellipsoid height (NAD83(2011), ift)"] == fmt.coordinate(
        point.output_elevation, INTERNATIONAL_FEET
    )
    assert point.output_elevation == pytest.approx(
        point.conversion.target_frame_ellipsoid_height / 0.3048, abs=1e-9
    )
    assert out["Ellipsoid height (NAD83(2011), ift)"] != "200.000"


def test_an_orthometric_transformed_job_names_the_factor_h_by_the_pivot(tab):
    """An elevation is in no frame (D6), so its row stays "Elevation"; the
    factors' h = H + N is NAD 83's (N is published against it), named so as
    the audit CSV's column is: ``Ellipsoid height (NAD83(2011), m)``."""
    typed_wgs84_to_zone(tab, kind=HeightKind.ORTHOMETRIC)
    inp, out = (rows_of(s) for s in tab.sections)
    assert inp["Elevation"] == "200.000"
    assert "Ellipsoid height (NAD83(2011), m)" in out
    assert "Ellipsoid height (m)" not in out


@pytest.mark.parametrize("forward", [True, False])
def test_a_geodetic_to_geodetic_panel_shows_each_end_in_its_frame(tab, forward):
    """Forward: input the typed G2296 position, output the NAD83(2011) pivot.
    Reverse: input the typed NAD83(2011) position (the pivot), output HTDP's
    G2296 position. No zone row on either side; the date sits with the G2296
    position, wherever it is.
    """
    source, target = (G2296, NAD) if forward else (NAD, G2296)
    choose(tab.from_zone, source)
    choose(tab.to_zone, target)
    tab.first_edit.setText(LATITUDE_TEXT)
    tab.second_edit.setText(LONGITUDE_TEXT)
    answer_date(tab, OBSERVED)
    assert tab.convert() is True, tab.shown_failures
    conversion = tab.result.points[0].conversion
    external = conversion.external_position
    inp, out = (rows_of(s) for s in tab.sections)

    g2296_rows, nad_rows = (inp, out) if forward else (out, inp)
    assert g2296_rows["Latitude (WGS84(G2296))"] == fmt.latitude_display(
        external.latitude
    )
    assert g2296_rows["Observation date"] == "2025-06-15"
    assert nad_rows["Latitude (NAD83(2011))"] == fmt.latitude_display(
        conversion.latitude
    )
    assert "Observation date" not in nad_rows
    # The typed side reads back exactly what was typed.
    assert inp[f"Latitude ({source.frame.code})"] == "42.73250000°"
    for rows in (inp, out):
        assert "Zone" not in rows and "Grid scale factor" not in rows


def test_copy_all_and_every_copy_button_copy_what_is_shown(tab):
    """The clipboard carries the panel's own strings, on a transformed job.

    Copy all is ``single_point_clipboard_text`` of the rendered sections; each
    per-value button copies its own value label's text, in screen order.
    """
    typed_wgs84_to_zone(tab)
    assert tab.copy_all() is True
    assert tab.clipboard[-1] == results_model.single_point_clipboard_text(
        tab.sections
    )
    assert "Latitude (WGS84(G2296))\t42.73250000°" in tab.clipboard[-1]
    assert "Observation date\t2025-06-15" in tab.clipboard[-1]
    shown = [label.text() for label in tab.value_labels]
    for index, button in enumerate(tab.copy_buttons):
        button.click()
        assert tab.clipboard[-1] == shown[index]


@pytest.mark.parametrize(
    "case",
    ["g2g-forward", "g2g-reverse", "z2g-wgs84", "vertical-only-wgs84"],
)
def test_the_table_headings_name_the_frame_their_cells_hold(window, tmp_path, case):
    """Gate 2's H1 on screen: each degree heading names the frame of its cells,
    by the audit CSV's own rule (``exports.geodetic_pair_frames``).

    The table's two coordinate columns are the audit CSV's TARGET pair, cell
    for cell - checked against the written file - so their frame is the
    Target pair's: the output frame on G2G and Z2G, the INPUT frame on
    vertical-only (which mirrors its input). A G2G table must never read
    "Northing" / "Easting" (W4's note: the restated rule had no G2G branch).
    """
    if case == "z2g-wgs84":
        # A Michigan South grid point in ift near Lansing (about 42.73 N,
        # 84.56 W, inside HTDP's velocity window). Its value is not the
        # subject: the cells are checked against the written file below.
        file_job(window, tmp_path, "1,449212.689,13072640.000,200.0,A\n")
        choose(window.from_zone, MI_SOUTH)
        choose(window.to_zone, G2296)
        frame = "WGS84(G2296)"
    elif case == "vertical-only-wgs84":
        file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
        window.mode_vertical_only.setChecked(True)
        choose(window.from_zone, G2296)
        choose(window.vertical_source_combo, NAVD88)
        choose(window.vertical_target_combo, NAVD88)
        frame = "WGS84(G2296)"
    else:
        file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
        forward = case == "g2g-forward"
        choose(window.from_zone, G2296 if forward else NAD)
        choose(window.to_zone, NAD if forward else G2296)
        frame = "NAD83(2011)" if forward else "WGS84(G2296)"
    answer_date(window, OBSERVED)
    assert window.convert() is True, window.shown_failures

    headings = table_headings(window)
    assert headings[1] == f"Latitude ({frame})"
    assert headings[2] == f"Longitude ({frame})"
    assert "Northing" not in headings and "Easting" not in headings

    audit = audit_rows(window)
    header, row = audit[0], audit[1]
    target_lat = header.index(f"Target latitude ({frame})")
    target_lon = header.index(f"Target longitude ({frame}, as written)")
    cells = table_cells(window)
    assert cells[1] == row[target_lat]
    assert cells[2] == row[target_lon]


def test_a_same_frame_geodetic_table_keeps_its_headings(window, tmp_path):
    """Anti-overreach: NAD83(2011) geodetic out keeps H6's plain headings."""
    file_job(window, tmp_path, "1,449212.689,13072640.000,200.0,A\n")
    choose(window.from_zone, MI_SOUTH)
    choose(window.to_zone, NAD)
    assert window.convert() is True, window.shown_failures
    assert table_headings(window) == list(results_model.GEODETIC_COLUMNS)


def test_a_horizontal_ellipsoid_tables_height_heading_is_the_audit_csvs(
    window, tmp_path
):
    """The Z column of a horizontal ellipsoid job holds h in the TARGET frame
    (D6); the table's heading and the audit CSV's are one function's answer.
    """
    file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
    choose(window.from_zone, G2296)
    choose(window.to_zone, MI_SOUTH)
    choose(window.height_kind_combo, HeightKind.ELLIPSOID)
    answer_date(window, OBSERVED)
    assert window.convert() is True, window.shown_failures
    heading = "Ellipsoid height (NAD83(2011))"
    assert table_headings(window)[3] == heading
    assert heading in audit_rows(window)[0]


# ==========================================================================
# 5. Job-level warnings.
# ==========================================================================


def test_the_realization_warning_reaches_the_single_point_field(tab):
    """G2296 dated 2012-06-15, before G2296 came into use (2024-01-07).

    One job-level warning, not on any point; the field shows its message
    exactly as the record prints it (``warning.message``), the status counts
    it and goes amber.
    """
    typed_wgs84_to_zone(tab, date=OUTSIDE_PERIOD)
    result = tab.result
    assert result.warnings == ()
    (warning,) = result.job_warnings
    assert warning.code is WarningCode.REALIZATION_OUTSIDE_PERIOD_OF_USE
    assert tab.warnings_label.text() == warning.message
    assert tab.status_label.text() == "Converted. 1 warning."
    assert "8A5A00" in tab.status_label.styleSheet()
    assert warning.message in tab.status_label.toolTip()


def test_the_realization_warning_reaches_the_multi_point_status(window, tmp_path):
    """The Multi point tab's warnings surface is its status line and tooltip;
    the job's own warning is counted there and printed first, in its words.
    The written record carries the same sentence."""
    file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
    choose(window.from_zone, G2296)
    choose(window.to_zone, MI_SOUTH)
    answer_date(window, OUTSIDE_PERIOD)
    assert window.convert() is True, window.shown_failures
    (warning,) = window.result.job_warnings
    assert window.status_label.text() == "1 points converted. 1 warnings."
    assert window.status_label.toolTip().startswith(warning.message)
    archive = next(iter(window.written_files.values()))
    assert warning.message in member_text(archive, ".txt")


def test_no_job_warning_means_the_field_says_none(tab):
    """Anti-vacuity: inside the period, the field and status say none."""
    typed_wgs84_to_zone(tab, date=OBSERVED)
    assert tab.result.job_warnings == ()
    assert tab.warnings_label.text() == results_model.NO_WARNINGS
    assert tab.status_label.text() == "Converted. No warnings."


# ==========================================================================
# 6. Refusals.
# ==========================================================================


def test_htdp_refusal_is_neither_of_the_handlers_a_tab_might_narrow_to():
    """Why the tabs name it (interim gate 2, finding L4)."""
    from michspc.spc.frames import FrameMismatchError

    assert not issubclass(htdp.HtdpRefusal, ValueError)
    assert not issubclass(htdp.HtdpRefusal, FrameMismatchError)
    assert issubclass(htdp.HtdpVelocityGridError, htdp.HtdpRefusal)


@pytest.mark.parametrize("which", ["single", "multi"])
def test_an_htdp_refusal_is_caught_shown_and_clears_the_previous_result(
    window, which, tmp_path
):
    """A real HTDP refusal through the real Convert, on both tabs.

    41.0 N, 95.0 W (Iowa) is outside HTDP's velocity-grid window this program
    carries (lon -92.0 to -80.5, plan section 3.2), so job.run raises
    ``HtdpVelocityGridError`` naming the point and the frame. First a good
    conversion is put on screen; the refusal must leave nothing of it.
    """
    page = pages(window)[which]
    if which == "multi":
        file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
    else:
        page.first_edit.setText(LATITUDE_TEXT)
        page.second_edit.setText(LONGITUDE_TEXT)
    choose(page.from_zone, G2296)
    choose(page.to_zone, NAD)
    answer_date(page, OBSERVED)
    assert page.convert() is True, page.shown_failures
    assert page.result is not None

    if which == "multi":
        (tmp_path / "in.csv").write_text("1,41.0,95.0,200.0,A\n", encoding="utf-8")
    else:
        page.first_edit.setText("41.0")
        page.second_edit.setText("95.0")
    assert page.convert() is False
    assert isinstance(page.last_failure, htdp.HtdpVelocityGridError)
    shown = page.shown_failures[-1]
    assert shown == str(page.last_failure)
    assert "WGS84(G2296)" in shown and "velocity" in shown
    assert page.result is None
    assert page.status_label.text().startswith("Refused: ")
    if which == "multi":
        assert window.model.rowCount() == 0
        assert window.open_folder_button.isEnabled() is False
    else:
        assert page.sections is None
        assert page.copy_all_button.isEnabled() is False
        assert page.copy_value(0) is False


# ==========================================================================
# 7. Invalidation, per control - the amendment #26 / #43 CRITICAL class.
# ==========================================================================


def _move(control: str, tab) -> None:
    """Change exactly one control, to a value that still describes a job."""
    if control == "observation date":
        answer_date(tab, OBSERVED + datetime.timedelta(days=1))
    elif control == "from":
        choose(tab.from_zone, G2139)  # still reaches Michigan South
    elif control == "to":
        choose(tab.to_zone, MI_CENTRAL)  # still reachable from G2296
    elif control == "height kind":
        choose(tab.height_kind_combo, HeightKind.ORTHOMETRIC)
    elif control == "vertical mode":
        # Horizontal + Vertical -> Vertical: see the test's docstring for why
        # this move and not Horizontal -> Horizontal + Vertical.
        tab.mode_vertical_only.setChecked(True)
    elif control == "input unit":
        choose(tab.input_unit, METERS)
    elif control == "output unit":
        choose(tab.output_unit, METERS)
    elif control == "longitude convention":
        choose(tab.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    else:
        raise AssertionError(control)


@pytest.mark.parametrize(
    "control",
    [
        "observation date",
        "from",
        "to",
        "height kind",
        "vertical mode",
        "input unit",
        "output unit",
        "longitude convention",
    ],
)
def test_every_control_discards_a_displayed_wgs84_result(tab, control):
    """A WGS84(G2296) result on screen, both copy paths armed; one control
    moves; nothing of the result survives and neither copy path works.

    Each control is its own case, so removing any ONE control's invalidation
    connection fails exactly its case (falsified per control, see the W5
    report). The starting state is checked first so no case passes vacuously.

    **The mode case starts in Horizontal + Vertical and moves to Vertical,
    measured rather than chosen for convenience.** Leaving or entering
    Horizontal rebuilds the geoid dropdowns (``_refresh_geoid_sides``), and
    that rebuild invalidates through the geoid combo's own connection - so a
    Horizontal -> Horizontal + Vertical move discards the result even with the
    mode's own invalidation removed, and its case could not tell (falsification
    seed S14 survived it in the first form of this test). Between the two
    vertical modes the geoid offering does not change, so the mode's own
    connection is the only route, and removing it fails this case.
    """
    if control == "vertical mode":
        tab.mode_vertical.setChecked(True)
        choose(tab.vertical_source_combo, NAVD88)
        choose(tab.vertical_target_combo, NAVD88)
    typed_wgs84_to_zone(tab)
    assert tab.sections is not None
    assert tab.copy_all_button.isEnabled() is True
    before = len(tab.clipboard)

    _move(control, tab)

    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False
    assert tab.copy_all() is False
    assert tab.copy_value(0) is False
    assert len(tab.clipboard) == before
    assert tab.warnings_label.text() == "—"


@pytest.mark.parametrize("control", ["observation date", "from", "to"])
def test_the_multi_point_table_goes_on_describing_its_archive(
    window, tmp_path, control
):
    """The Multi point tab's standing contract, unchanged by W5.

    Its table describes the archive a run WROTE, not the controls
    (``MainWindow._clear_table``; tests/test_gui_frames.py::
    test_an_ordinary_zone_change_leaves_the_multi_point_table_alone) - the
    files on disk, whose record states the frame and the date they were
    converted at, are still correct, and there is no copy path on this tab.
    So the date, like every other control here, re-gates Convert and leaves
    the table. Recorded in the W5 report as the one place this package
    reads the brief's "on both tabs" against an owner-reviewed contract.
    """
    file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
    choose(window.from_zone, G2296)
    choose(window.to_zone, MI_SOUTH)
    answer_date(window, OBSERVED)
    assert window.convert() is True, window.shown_failures
    written = sorted(tmp_path.glob("*.zip"))

    _move(control, window)

    assert window.model.rowCount() == 1
    assert window.result is not None
    assert sorted(tmp_path.glob("*.zip")) == written
    assert window.convert_button.isEnabled() is True


def test_vertical_mode_g2g_reaches_navd88_from_a_wgs84_gnss_height(tab):
    """D8 through the screen: a WGS84(G2296) GNSS height to a NAVD 88
    elevation, geodetic to geodetic, Horizontal + Vertical.

    The output Z is H = h(NAD 83) - N at the pivot (plan D6/D8): the core's
    own ``output_elevation``, which equals the NAD 83 h HTDP produced
    (``pivot_ellipsoid_height``) minus the geoid height read at the pivot,
    shown under the datum-tagged label. 165.000 m typed shows as "165.0000"
    because metres carry four decimals (``formatting.coordinate``).
    """
    choose(tab.from_zone, G2296)
    choose(tab.to_zone, NAD)
    tab.mode_vertical.setChecked(True)
    choose(tab.vertical_source_combo, NAVD88)
    choose(tab.vertical_target_combo, NAVD88)
    choose(tab.height_kind_combo, HeightKind.ELLIPSOID)
    choose(tab.input_unit, METERS)
    choose(tab.output_unit, METERS)
    tab.first_edit.setText(LATITUDE_TEXT)
    tab.second_edit.setText(LONGITUDE_TEXT)
    tab.elevation_edit.setText("165.000")
    answer_date(tab, OBSERVED)
    assert tab.settings().vertical_mode is VerticalMode.HORIZONTAL_AND_VERTICAL
    assert tab.convert() is True, tab.shown_failures
    point = tab.result.points[0]
    conversion = point.conversion
    inp, out = (rows_of(s) for s in tab.sections)
    assert inp["Ellipsoid height (WGS84(G2296), m)"] == "165.0000"
    label = "Elevation (NAVD88, m) (GEOID18)"
    assert out[label] == fmt.coordinate(point.output_elevation, METERS)
    assert point.output_elevation == pytest.approx(
        conversion.pivot_ellipsoid_height - point.factors.geoid_height, abs=1e-9
    )


# ==========================================================================
# 8. The lead's two findings on the W5 screenshots: a G2G job has no zone.
# ==========================================================================


def test_the_zoneless_rule_is_the_cores_one_statement():
    """``job.is_zoneless``: G2G always, VERTICAL_ONLY on geodetic input only.

    Derived from what a zone is: GEODETIC_TO_GEODETIC has latitude and
    longitude at both ends; VERTICAL_ONLY has the input's system alone, which
    is a zone exactly when ``source_zone`` is set; every other direction has
    a zone at one end at least. The job record reads it (W4b's flag) and the
    interface's hints read it, so this is the rule both obey.
    """
    from michspc.fileio import report

    assert job_module.is_zoneless(Direction.GEODETIC_TO_GEODETIC, None) is True
    assert job_module.is_zoneless(Direction.VERTICAL_ONLY, None) is True
    assert job_module.is_zoneless(Direction.VERTICAL_ONLY, MI_SOUTH) is False
    for direction in (
        Direction.ZONE_TO_ZONE,
        Direction.GEODETIC_TO_ZONE,
        Direction.ZONE_TO_GEODETIC,
    ):
        assert job_module.is_zoneless(direction, MI_SOUTH) is False
    # The record asks the same function - not a restatement of it.
    assert report.is_zoneless is job_module.is_zoneless
    assert controls.is_zoneless is job_module.is_zoneless


def test_the_single_point_hint_names_no_combined_factor_on_a_zoneless_job(tab):
    """Finding 1, Single point: the #57 placeholder is false on G2G.

    Horizontal mode throughout, so only the direction moves the hint:
    * unanswered (no job yet) - the owner's sentence, as the tab opens;
    * G2296 -> Michigan South - a zone, so a combined factor: the sentence;
    * G2296 -> NAD83(2011) geodetic - G2G, no zone, no combined factor:
      ``ELEVATION_PLACEHOLDER_ZONELESS``, "optional" and nothing more;
    * back to a zone target - the sentence returns.
    The two vertical modes keep #51's empty placeholder on G2G too.
    """
    from michspc.gui.single_point import (
        ELEVATION_PLACEHOLDER,
        ELEVATION_PLACEHOLDER_ZONELESS,
    )

    assert ELEVATION_PLACEHOLDER_ZONELESS == "optional"
    assert "combined" not in ELEVATION_PLACEHOLDER_ZONELESS
    hint = tab.elevation_edit.placeholderText
    assert hint() == ELEVATION_PLACEHOLDER
    choose(tab.from_zone, G2296)
    choose(tab.to_zone, MI_SOUTH)
    assert hint() == ELEVATION_PLACEHOLDER
    choose(tab.to_zone, NAD)
    assert tab.direction() is Direction.GEODETIC_TO_GEODETIC
    assert hint() == ELEVATION_PLACEHOLDER_ZONELESS
    choose(tab.to_zone, MI_CENTRAL)
    assert hint() == ELEVATION_PLACEHOLDER

    choose(tab.to_zone, NAD)
    tab.mode_vertical.setChecked(True)
    assert hint() == ""
    tab.mode_horizontal.setChecked(True)
    assert hint() == ELEVATION_PLACEHOLDER_ZONELESS


def test_the_multi_point_note_names_no_combined_factor_on_a_zoneless_job(window):
    """Finding 1, Multi point: the #48 note beside "in file" is false on G2G.

    Same walk as the Single point pin. Only the TEXT moves; the note's
    visibility is still ``_update_vertical_rows``'s alone (#57), so it stays
    visible in Horizontal on every direction.
    """
    from michspc.gui.window import ELEVATION_NOTE, ELEVATION_NOTE_ZONELESS

    note = window.elevation_note
    assert ELEVATION_NOTE_ZONELESS == ""
    assert note.text() == ELEVATION_NOTE
    choose(window.from_zone, G2296)
    choose(window.to_zone, MI_SOUTH)
    assert note.text() == ELEVATION_NOTE
    choose(window.to_zone, NAD)
    assert window.direction() is Direction.GEODETIC_TO_GEODETIC
    assert note.text() == ELEVATION_NOTE_ZONELESS
    assert "combined" not in note.text()
    # Not explicitly hidden: the visibility owner left it alone (the page
    # itself is behind the Single point tab, so isVisible() would say False).
    assert note.isHidden() is False
    choose(window.from_zone, MI_SOUTH)  # Michigan South -> NAD83(2011) is a job
    assert window.direction() is Direction.ZONE_TO_GEODETIC
    assert note.text() == ELEVATION_NOTE


def _g2g_file_job(window, tmp_path, vertical: bool) -> None:
    """A forward G2296 -> NAD83(2011) file job, two points, one of them blank-Z."""
    file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n2,42.8,84.6,,B\n")
    choose(window.from_zone, G2296)
    choose(window.to_zone, NAD)
    if vertical:
        window.mode_vertical.setChecked(True)
        choose(window.vertical_source_combo, NAVD88)
        choose(window.vertical_target_combo, NAVD88)
    answer_date(window, OBSERVED)
    assert window.convert() is True, window.shown_failures


@pytest.mark.parametrize("vertical", [False, True])
def test_a_g2g_table_carries_no_zone_only_column(window, tmp_path, vertical):
    """Finding 2: no "Grid scale factor" or "Combined factor" column on G2G.

    Expected headings: ``GEODETIC_COLUMNS`` with the coordinate pair named by
    its frame (NAD83(2011), the forward target) and the two zone-only
    columns removed - plus, in Horizontal + Vertical, the shift and sigma
    headings directly after Elevation, as on every vertical table. Every row
    has exactly as many cells as headings, and every cell the table shows is
    the audit CSV's own under its own heading: the table drops two columns,
    it never shifts a value under the wrong heading.

    THE EXCEPTION to the table-mirrors-the-CSV rule, stated: the audit CSV is
    the record and keeps both factor columns on this direction, N/A in every
    row (checked below), because a record does not omit a field it carries
    for every other direction.
    """
    _g2g_file_job(window, tmp_path, vertical)
    headings = table_headings(window)
    for column in results_model.ZONE_ONLY_COLUMNS:
        assert column not in headings
    assert headings[:3] == [
        "Point",
        "Latitude (NAD83(2011))",
        "Longitude (NAD83(2011))",
    ]
    assert headings[-1] == "Warnings"
    assert len(headings) == (7 if vertical else 5)
    if vertical:
        assert headings[4:6] == [
            exports.vertical_shift_heading(window.result.settings.input_unit),
            exports.vertical_sigma_heading(window.result.settings.input_unit),
        ]

    audit = audit_rows(window)
    header = audit[0]
    correspondence = {
        "Point": "Point",
        "Latitude (NAD83(2011))": "Target latitude (NAD83(2011))",
        "Longitude (NAD83(2011))": "Target longitude (NAD83(2011), as written)",
        headings[3]: "Elevation",
    }
    if vertical:
        correspondence[headings[4]] = headings[4]
        correspondence[headings[5]] = headings[5]
    for row_index in range(window.model.rowCount()):
        cells = table_cells(window, row_index)
        assert len(cells) == len(headings)
        record = dict(zip(header, audit[1 + row_index]))
        for shown, recorded in correspondence.items():
            assert cells[headings.index(shown)] == record[recorded], (
                row_index,
                shown,
            )
        # The Warnings cell is the point's own codes, under the Warnings
        # heading - not a factor cell left behind and shifted under it.
        point = window.result.points[row_index]
        assert cells[headings.index("Warnings")] == "; ".join(
            warning.code.value for warning in point.warnings
        )
        # The record keeps its N/A cells: the exception is the table's alone.
        assert record["Grid scale factor"] == fmt.NOT_AVAILABLE
        assert record["Combined factor"] == fmt.NOT_AVAILABLE
    assert window.model.rowCount() == 2
    # The rendered rows themselves, not only what the model's column count
    # lets a view reach: one cell per heading, exactly.
    for rendered in results_model.row_strings(window.result):
        assert len(rendered) == len(headings)
    # The Warnings comparison discriminates although neither point warns: a
    # factor cell left behind would sit under that heading reading "N/A"
    # (both factors are None on every G2G point), never the empty string.


def test_a_zone_job_table_keeps_the_zone_columns(window, tmp_path):
    """Anti-overreach: the same G2296 file into a zone keeps both columns, and
    their cells are numbers, not N/A - the columns were dropped only where
    they could never hold a value."""
    file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
    choose(window.from_zone, G2296)
    choose(window.to_zone, MI_SOUTH)
    answer_date(window, OBSERVED)
    assert window.convert() is True, window.shown_failures
    headings = table_headings(window)
    cells = table_cells(window)
    for column in results_model.ZONE_ONLY_COLUMNS:
        assert column in headings
        assert cells[headings.index(column)] != fmt.NOT_AVAILABLE


def test_a_g2g_panel_shows_no_combined_factor_row(tab):
    """The Single point G2G layout's own rule, matching the table: no Zone,
    grid factor, convergence or combined factor row. The elevation factor
    and geoid height stay - they need only the height and the geoid - and
    carry the core's numbers through the panel's formatters."""
    choose(tab.from_zone, G2296)
    choose(tab.to_zone, NAD)
    tab.first_edit.setText(LATITUDE_TEXT)
    tab.second_edit.setText(LONGITUDE_TEXT)
    tab.elevation_edit.setText(HEIGHT_TEXT)
    answer_date(tab, OBSERVED)
    assert tab.convert() is True, tab.shown_failures
    factors = tab.result.points[0].factors
    labels = [v.label for s in tab.sections for v in s.values]
    for absent in ("Zone", "Grid scale factor", "Convergence", "Combined factor"):
        assert absent not in labels
    out = rows_of(tab.sections[1])
    assert out["Elevation factor"] == fmt.factor(factors.elevation_factor)
    assert out["Elevation factor"] != fmt.NOT_AVAILABLE
    assert out["Geoid height (m)"] == fmt.geoid_height(factors.geoid_height)


def test_a_vertical_mode_panel_shows_the_transformed_ellipsoid_height(tab):
    """D6 in a vertical mode: the typed WGS84(G2296) h is transformed with the
    position before H = h - N, and the output row is H - so the transformed h
    must be shown on its own row, or no row on the panel holds it.

    Label: the audit CSV's own heading for it,
    ``Ellipsoid height after transformation (NAD83(2011), m)``. Value: HTDP's
    output h, ``target_frame_ellipsoid_height`` (on this forward path the
    pivot's), through the CSV's formatter. Anti-swap: it is not the typed
    165.000 m, which would be the input h shown under the output frame.
    """
    choose(tab.from_zone, G2296)
    choose(tab.to_zone, NAD)
    tab.mode_vertical.setChecked(True)
    choose(tab.vertical_source_combo, NAVD88)
    choose(tab.vertical_target_combo, NAVD88)
    choose(tab.height_kind_combo, HeightKind.ELLIPSOID)
    choose(tab.input_unit, METERS)
    choose(tab.output_unit, METERS)
    tab.first_edit.setText(LATITUDE_TEXT)
    tab.second_edit.setText(LONGITUDE_TEXT)
    tab.elevation_edit.setText("165.000")
    answer_date(tab, OBSERVED)
    assert tab.convert() is True, tab.shown_failures
    conversion = tab.result.points[0].conversion
    out = rows_of(tab.sections[1])
    label = "Ellipsoid height after transformation (NAD83(2011), m)"
    assert label == exports.transformed_ellipsoid_height_heading(
        conversion.frame_transformation
    )
    assert out[label] == fmt.geoid_height(conversion.target_frame_ellipsoid_height)
    assert out[label] == fmt.geoid_height(conversion.pivot_ellipsoid_height)
    assert out[label] != fmt.geoid_height(165.0)
    # In the clipboard too: Copy all carries what is shown.
    assert tab.copy_all() is True
    assert f"{label}\t{out[label]}" in tab.clipboard[-1]


def test_a_horizontal_panel_does_not_repeat_the_transformed_height(tab):
    """Anti-overreach: in Horizontal the output Z row IS the transformed h,
    already named by its frame, so the extra row is not added."""
    typed_wgs84_to_zone(tab)
    labels = [v.label for s in tab.sections for v in s.values]
    assert not any("after transformation" in label for label in labels)


# ==========================================================================
# 9. The closing gate of the WGS 84 build (review/gate-wgs84-closing/
#    output.md): the panel rows whose value differs between the two frames,
#    pinned on the paths OUT of NAD 83 against HTDP's own print.
# ==========================================================================

L5 = {record.frame_code: record for record in L5_RECORDS}
L5R = {record.frame_code: record for record in L5_REVERSE_RECORDS}

_NAD83_SOUTH = project_point(43.0, -84.5, NAD83_2011, MI_SOUTH)
"""An INPUT, not an expected value: interim gate 1's L5 position, NAD 83
43.0 N 84.5 W, projected into Michigan South and typed with repr so the box
holds the doubles exactly. The tab inverts it back to 43.0 / -84.5 within
1e-11 degree (the projection round trip W3 measured), far inside every
tolerance below."""

HTDP_H_TOLERANCE_M = 0.0005 + 0.00005
"""A 4-place metre cell (``formatting.coordinate``) against HTDP's 3-place
print of the same h: half HTDP's printed unit plus half the cell's."""


def _out_of_nad83_job(tab, case: str, mode: str) -> None:
    """The reviewer's M1 configuration: NAD 83 in, WGS84(G2296) out.

    ``case`` "z2g": Michigan South grid in (the L5 position); "g2g-reverse":
    NAD83(2011) geodetic in, 43.0 / -84.5 typed negative west - the
    reviewer's exact input. ``mode`` "hv" is Horizontal + Vertical, NAVD88 to
    NAVD88, GEOID18; "h" is Horizontal. ELLIPSOID, metres, h 165.000 m,
    observed 2025-06-15.
    """
    choose(tab.from_zone, MI_SOUTH if case == "z2g" else NAD)
    choose(tab.to_zone, G2296)
    if mode == "hv":
        tab.mode_vertical.setChecked(True)
        choose(tab.vertical_source_combo, NAVD88)
        choose(tab.vertical_target_combo, NAVD88)
        choose(tab.geoid_combo, geoid.GEOID18_MODEL)
    choose(tab.height_kind_combo, HeightKind.ELLIPSOID)
    choose(tab.input_unit, METERS)
    choose(tab.output_unit, METERS)
    choose(tab.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    if case == "z2g":
        tab.first_edit.setText(repr(_NAD83_SOUTH.target_northing))
        tab.second_edit.setText(repr(_NAD83_SOUTH.target_easting))
    else:
        tab.first_edit.setText("43.0")
        tab.second_edit.setText("-84.5")
    tab.elevation_edit.setText("165.000")
    answer_date(tab, OBSERVED)
    expected_mode = (
        VerticalMode.HORIZONTAL_AND_VERTICAL if mode == "hv" else VerticalMode.HORIZONTAL
    )
    assert tab.settings().vertical_mode is expected_mode
    assert tab.convert() is True, tab.shown_failures
    assert tab.result.points[0].conversion.is_transformed


@pytest.mark.parametrize("case", ["z2g", "g2g-reverse"])
def test_a_vertical_mode_panel_out_of_nad83_shows_htdps_target_frame_h(tab, case):
    """Closing gate, M1: the "after transformation" row on a path OUT of NAD 83.

    The row's only earlier pin ran G2G forward, INTO NAD 83, where the
    target-frame h and the pivot h are one number - so the reviewer's seed
    (the row fed ``pivot_ellipsoid_height``) left the suite green while the
    panel showed the NAD 83 h, 165.000 m, under the WGS84(G2296) label.

    Expected: HTDP's own print, the frozen L5 reverse record for G2296
    (``htdp_w3_anchors``: NAD 83(2011) 43.0 N 84.5 W h 165.000 at 1 1 2010
    to WGS84(G2296) at 6 15 2025): h_out "163.901". The row is rendered by
    ``formatting.geoid_height`` (3 places, the audit CSV's formatter), so it
    must read HTDP's printed string exactly: the program reproduces HTDP at
    its printed digit (W1), and 163.901 is not near a rounding boundary of
    its own print. The seed's value, the NAD 83 h, is "165.000": 1.099 m out.
    """
    _out_of_nad83_job(tab, case, "hv")
    truth = L5R[WGS84_G2296.code]
    out = rows_of(tab.sections[1])
    label = "Ellipsoid height after transformation (WGS84(G2296), m)"
    assert truth.h_out == "163.901"
    assert out[label] == truth.h_out
    assert out[label] != "165.000"
    # And in the clipboard: Copy all carries the shown row.
    assert tab.copy_all() is True
    assert f"{label}\t163.901" in tab.clipboard[-1]


@pytest.mark.parametrize("case", ["z2g", "g2g-reverse"])
@pytest.mark.parametrize("mode", ["h", "hv"])
def test_the_output_position_out_of_nad83_is_htdps_target_frame_position(
    tab, case, mode
):
    """Closing gate, M1's sweep: the OUTPUT position rows on the paths out of
    NAD 83, the other panel rows whose value differs between the two frames.

    Their earlier pins compared the rows with the core's own
    ``external_position``; these compare them with HTDP's print, the L5
    reverse record for G2296: 43.0000085274 N, 84.5000107604 W.

    * DD rows, 8 places (``formatting.latitude_display``): 43.0000085274 to
      8 places is 43.00000853 (ninth digit 7, nowhere near a half); the
      longitude is shown in the job's negative-west convention,
      -84.5000107604 -> -84.50001076 (ninth digit 0).
    * DMS rows, 5 places of a second: 0.0000085274 deg x 3600 = 0.03069864"
      -> 00.03070"; 0.0000107604 deg x 3600 = 0.03873744" -> 00.03874". Each
      is more than 2e-6" from its rounding boundary, where HTDP's half-unit
      print (0.5e-10 deg) is 1.8e-7".
    * The NAD83(2011) pivot rows still read the L5 input itself, 43.0 / -84.5.

    The pivot shown under the G2296 label - the seed class - is 0.95 m away
    and fails every one of them.
    """
    _out_of_nad83_job(tab, case, mode)
    out = rows_of(tab.sections[1])
    rows = {**rows_of(tab.sections[0]), **out}
    assert out["Latitude (WGS84(G2296))"] == "43.00000853°"
    assert out["Longitude (WGS84(G2296))"] == "-84.50001076°"
    assert out["Latitude (WGS84(G2296), DMS)"] == "43°00'00.03070\"N"
    assert out["Longitude (WGS84(G2296), DMS)"] == "84°30'00.03874\"W"
    assert out["Observation date"] == "2025-06-15"
    assert rows["Latitude (NAD83(2011))"] == "43.00000000°"
    assert rows["Longitude (NAD83(2011))"] == "-84.50000000°"


@pytest.mark.parametrize("case", ["z2g", "g2g-reverse"])
def test_a_horizontal_panel_out_of_nad83_shows_htdps_target_frame_h(tab, case):
    """Closing gate, M1's sweep: in Horizontal the OUTPUT Z of an ELLIPSOID job
    IS the target-frame h (plan D6), and its only panel pin ran G2Z, into
    NAD 83.

    Expected: HTDP's printed 163.901 m (L5 reverse record, G2296), within
    HTDP_H_TOLERANCE_M of the 4-place cell; not the NAD 83 h typed, 165.000,
    which is 1.099 m from it.
    """
    _out_of_nad83_job(tab, case, "h")
    truth = L5R[WGS84_G2296.code]
    out = rows_of(tab.sections[1])
    shown = out["Ellipsoid height (WGS84(G2296), m)"]
    assert abs(float(shown) - float(truth.h_out)) <= HTDP_H_TOLERANCE_M
    assert rows_of(tab.sections[0])["Ellipsoid height (NAD83(2011), m)"] == "165.0000"


def test_the_multi_point_table_out_of_nad83_holds_htdps_target_frame_values(
    window, tmp_path
):
    """Closing gate, M1's sweep on the table: Michigan South in, WGS84(G2296)
    out, ELLIPSOID, Horizontal - the table's three coordinate cells against
    HTDP's print rather than against the written file alone.

    Input: the L5 position's MI-S grid in metres, h 165.000, negative west.
    Expected (L5 reverse record, G2296): latitude 43.0000085274 to the
    table's 8 places (``formatting.latitude``) = "43.00000853"; longitude
    -84.5000107604 -> "-84.50001076"; the Z cell is the target-frame h, within
    HTDP_H_TOLERANCE_M of HTDP's 163.901 - not the NAD 83 165.000.
    """
    file_job(
        window,
        tmp_path,
        f"1,{_NAD83_SOUTH.target_northing!r},{_NAD83_SOUTH.target_easting!r},"
        f"165.000,P\n",
    )
    choose(window.from_zone, MI_SOUTH)
    choose(window.to_zone, G2296)
    choose(window.height_kind_combo, HeightKind.ELLIPSOID)
    choose(window.input_unit, METERS)
    choose(window.output_unit, METERS)
    choose(window.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    answer_date(window, OBSERVED)
    assert window.convert() is True, window.shown_failures
    truth = L5R[WGS84_G2296.code]
    headings = table_headings(window)
    cells = dict(zip(headings, table_cells(window)))
    assert cells["Latitude (WGS84(G2296))"] == "43.00000853"
    assert cells["Longitude (WGS84(G2296))"] == "-84.50001076"
    z = cells[headings[results_model.ELEVATION_COLUMN]]
    assert abs(float(z) - float(truth.h_out)) <= HTDP_H_TOLERANCE_M


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_date_follows_a_mode_change_on_both_tabs(window, which):
    """Closing gate, L2: a MODE change re-decides whether the date is asked.

    The reviewer's sequence: From NAD83(2011) geodetic, To WGS84(G2296) -
    a G2G job reading a time-dependent target, so the date is enabled. In
    vertical-only mode only From counts, and NAD83(2011) is plate-fixed, so
    the date grays. Back to Horizontal, To counts again and the date must be
    enabled again; Horizontal + Vertical reads both ends too. The Multi point
    tab's mode handler was unpinned: without the refresh the date stayed
    grayed in Horizontal and Convert could never be enabled (a fail-closed
    dead end).
    """
    page = pages(window)[which]
    edit = page.observation_date_edit
    choose(page.from_zone, NAD)
    choose(page.to_zone, G2296)
    assert edit.isEnabled() is True
    page.mode_vertical_only.setChecked(True)
    assert edit.isEnabled() is False
    page.mode_horizontal.setChecked(True)
    assert page.to_zone.currentData() == G2296  # the pair still reaches
    assert edit.isEnabled() is True
    assert page.observation_date_label.isEnabled() is True
    page.mode_vertical_only.setChecked(True)
    assert edit.isEnabled() is False
    page.mode_vertical.setChecked(True)
    assert edit.isEnabled() is True


def test_a_vertical_only_wgs84_panel_shows_both_positions(tab):
    """Closing gate, L1: the release notes say the Single point tab shows both
    positions, each under its frame, when a transformation ran - and on a
    vertical-only job on ITRF2020 input the NAD83(2011) pivot rows were
    unpinned (the reviewer's seed C8 dropped them, suite green).

    Input: VERTICAL, From ITRF2020, NAVD88 -> NAVD88, ELLIPSOID h 165.000 m,
    43.0 / 84.5 typed positive west, observed 2025-06-15 - interim gate 1's
    L5 position, whose HTDP print is frozen (L5 record for ITRF2020: NAD 83
    42.9999914716 N, 84.4999892398 W, h 166.099).

    Expected INPUT rows, in order: the ITRF2020 position as typed
    (43.00000000, 84.50000000, DMS 43°00'00.00000"N / 84°30'00.00000"W),
    its observation date, then the NAD83(2011) pivot from HTDP's print:
    * 42.9999914716 to 8 places = 42.99999147 (ninth digit 1);
    * 84.4999892398 to 8 places = 84.49998924 (ninth digit 9, the tail
      .98 rounds the eighth up; 4.8e-9 deg from the boundary, HTDP's
      half-unit print is 5e-11);
    * DMS latitude: 1 - 0.9999914716 = 0.0000085284 deg = 0.03070224",
      so 59.96929776" -> 42°59'59.96930"N;
    * DMS longitude: 0.4999892398 deg = 29' 59.96126328" -> 84°29'59.96126"W.
    """
    tab.mode_vertical_only.setChecked(True)
    choose(tab.from_zone, I2020)
    choose(tab.vertical_source_combo, NAVD88)
    choose(tab.vertical_target_combo, NAVD88)
    choose(tab.height_kind_combo, HeightKind.ELLIPSOID)
    choose(tab.input_unit, METERS)
    tab.first_edit.setText("43.0")
    tab.second_edit.setText("84.5")
    tab.elevation_edit.setText("165.000")
    answer_date(tab, OBSERVED)
    assert tab.settings().direction is Direction.VERTICAL_ONLY
    assert tab.convert() is True, tab.shown_failures
    source = tab.sections[0]
    labels = [value.label for value in source.values]
    assert labels[:9] == [
        "Latitude (ITRF2020)",
        "Latitude (ITRF2020, DMS)",
        "Longitude (ITRF2020)",
        "Longitude (ITRF2020, DMS)",
        "Observation date",
        "Latitude (NAD83(2011))",
        "Latitude (NAD83(2011), DMS)",
        "Longitude (NAD83(2011))",
        "Longitude (NAD83(2011), DMS)",
    ]
    inp = rows_of(source)
    assert inp["Latitude (ITRF2020)"] == "43.00000000°"
    assert inp["Longitude (ITRF2020)"] == "84.50000000°"
    assert inp["Latitude (NAD83(2011))"] == "42.99999147°"
    assert inp["Longitude (NAD83(2011))"] == "84.49998924°"
    assert inp["Latitude (NAD83(2011), DMS)"] == "42°59'59.96930\"N"
    assert inp["Longitude (NAD83(2011), DMS)"] == "84°29'59.96126\"W"
    assert L5[ITRF2020.code].lat_out == "42.9999914716"
    # Copy all carries both.
    assert tab.copy_all() is True
    assert "Latitude (NAD83(2011))\t42.99999147°" in tab.clipboard[-1]
    assert "Latitude (ITRF2020)\t43.00000000°" in tab.clipboard[-1]


# --------------------------------------------------------------------------
# Closing gate, L3 and I3: the core's user-facing sentences are true on BOTH
# tabs - the Single point tab has no file, and on its DMS page the hemisphere
# letter, not the longitude convention, decides a sign.
# --------------------------------------------------------------------------

_LOOKUP = re.compile(
    r"its velocity-model lookup position in ITRF2008, latitude (-?\d+\.\d{6}), "
    r"longitude (-?\d+\.\d{6}) \(signed, negative west\), is outside the part "
    r"of HTDP's velocity grid this program carries\. "
)
"""The refused lookup position, in the program's own convention: signed
degrees with the convention named, as the refused input position before it
is (I3). Before the fix it read "-42.732484 N 84.555496 W" and, for an east
input, "275.444520 W"."""

LOOKUP_NEAR_INPUT_DEG = 1e-4
"""The ITRF2008 lookup position is the input moved by the frame difference -
about a metre in Michigan (0.95 m at the L5 position), 1e-5 degree - so
within 1e-4 degree of the refused input in each coordinate, sign included.
A 0-360 longitude (275.44 for 84.56 E) or a lost sign misses by degrees."""

_SIGN_ADVICE = (
    "Check that the point is in Michigan, and that its latitude and longitude "
    "carry the right signs: this job reads longitudes written {convention}, "
    "and a latitude or longitude whose sign is the wrong way round lands on "
    "the other side of the world."
)


def _typed_dms(tab, latitude, longitude) -> None:
    tab.angle_format.setCurrentIndex(
        tab.angle_format.findData(single_point_module.DMS_PAGE)
    )
    for entry, (degrees, minutes, seconds, letter) in (
        (tab.first_dms, latitude),
        (tab.second_dms, longitude),
    ):
        entry.degrees.setText(degrees)
        entry.minutes.setText(minutes)
        entry.seconds.setText(seconds)
        entry.hemisphere.setCurrentIndex(entry.hemisphere.findData(letter))


def _refusal_on(window, which, tmp_path, *, dms, decimal, row, convention):
    """Run one G2296 -> MI-S job dated 2025-06-15 that HTDP refuses; the
    message shown. ``dms`` (Single point) is typed on the DMS page, ``decimal``
    on the decimal page, ``row`` is the Multi point file's line."""
    page = pages(window)[which]
    if which == "multi":
        file_job(window, tmp_path, row)
    choose(page.from_zone, G2296)
    choose(page.to_zone, MI_SOUTH)
    choose(page.longitude_combo, convention)
    if which == "single":
        if dms is not None:
            _typed_dms(page, *dms)
        else:
            page.first_edit.setText(decimal[0])
            page.second_edit.setText(decimal[1])
    answer_date(page, OBSERVED)
    assert page.convert() is False
    (shown,) = page.shown_failures
    return shown


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_htdp_refusal_of_a_south_latitude_is_true_on_both_tabs(
    window, which, tmp_path
):
    """The reviewer's L3 (a): Single point, DMS 42°43'57" S, 84°33'19.8" W,
    positive west (the tab's preselect), G2296 -> MI-S, 2025-06-15. On the
    Multi point tab the same position as a file row, -42.7325, 84.5555.

    The DMS entry composes 42 + 43/60 + 57/3600 = 42.7325 S and
    84 + 33/60 + 19.8/3600 = 84.5555 W: signed, -42.7325 / -84.5555. A
    south latitude is outside HTDP's velocity window, so the refusal names
    point 1 and that signed position.

    Expected, the same words on both tabs: "the supplied position" (not
    "the position the file supplied" - the tab has no file); the lookup
    position signed with its convention named (I3), within
    LOOKUP_NEAR_INPUT_DEG of the input; and advice that asks for the SIGNS
    to be checked rather than presuming the longitude convention decided
    them - on the DMS page the S letter decided this one.
    """
    shown = _refusal_on(
        window,
        which,
        tmp_path,
        dms=(("42", "43", "57", "S"), ("84", "33", "19.8", "W")),
        decimal=None,
        row="1,-42.7325,84.5555,200.0,A\n",
        convention=LongitudeConvention.POSITIVE_WEST,
    )
    assert shown.startswith(
        "point 1: cannot transform the supplied position - latitude -42.732500, "
        "longitude -84.555500 (signed, negative west), in WGS84(G2296) - to "
        "NAD83(2011): "
    ), shown
    lookup = _LOOKUP.search(shown)
    assert lookup is not None, shown
    assert abs(float(lookup.group(1)) - -42.7325) <= LOOKUP_NEAR_INPUT_DEG
    assert abs(float(lookup.group(2)) - -84.5555) <= LOOKUP_NEAR_INPUT_DEG
    assert shown.endswith(_SIGN_ADVICE.format(convention="positive west")), shown
    assert "file" not in shown
    # Not the old "-42.732484 N 84.555496 W in ITRF2008": a negative number
    # with a hemisphere letter. (The window's own bounds, "40.5 N to 50.0 N",
    # are positive magnitudes with their letters, and true.)
    assert re.search(r"-\d+\.\d+ [NS]", shown) is None, shown
    assert " W in ITRF2008" not in shown


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_htdp_refusal_of_an_east_longitude_prints_it_signed(
    window, which, tmp_path
):
    """I3: G2296, longitude +84.5555 under NEGATIVE west - 84.5555 E, in
    China - so the refused position and its lookup are east.

    Expected: the input "latitude 42.732500, longitude 84.555500 (signed,
    negative west)", and the lookup printed the same way, POSITIVE (east),
    within LOOKUP_NEAR_INPUT_DEG of +84.5555 - where it read "275.444520 W",
    HTDP's 0-360 west longitude. The advice names the job's convention,
    negative west.
    """
    shown = _refusal_on(
        window,
        which,
        tmp_path,
        dms=None,
        decimal=("42.7325", "84.5555"),
        row="1,42.7325,84.5555,200.0,A\n",
        convention=LongitudeConvention.NEGATIVE_WEST,
    )
    assert shown.startswith(
        "point 1: cannot transform the supplied position - latitude 42.732500, "
        "longitude 84.555500 (signed, negative west), in WGS84(G2296) - to "
        "NAD83(2011): "
    ), shown
    lookup = _LOOKUP.search(shown)
    assert lookup is not None, shown
    assert abs(float(lookup.group(1)) - 42.7325) <= LOOKUP_NEAR_INPUT_DEG
    assert abs(float(lookup.group(2)) - 84.5555) <= LOOKUP_NEAR_INPUT_DEG
    assert "275." not in shown
    assert shown.endswith(_SIGN_ADVICE.format(convention="negative west")), shown


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_realization_warning_is_true_on_both_tabs(window, which, tmp_path):
    """The reviewer's L3 (b): WGS84(G2139) -> MI-S at 2019-03-01, before
    G2139 came into use (2021-01-03), on a path INTO NAD 83.

    Expected, character for character the same on both tabs and stated as
    facts true for typed and file input alike: G2139 "was not the realization
    in use on that date" (it said "a receiver on that date was not
    broadcasting it" - receivers broadcast nothing), and "positions labelled
    with the wrong realization look exactly like this" (it said "a file").
    The span is frames.realization_period_of_use's, as the core pin derives.
    """
    page = pages(window)[which]
    if which == "multi":
        file_job(window, tmp_path, "1,42.7325,84.5555,200.0,A\n")
    else:
        page.first_edit.setText(LATITUDE_TEXT)
        page.second_edit.setText(LONGITUDE_TEXT)
    choose(page.from_zone, G2139)
    choose(page.to_zone, MI_SOUTH)
    answer_date(page, datetime.date(2019, 3, 1))
    assert page.convert() is True, page.shown_failures
    (warning,) = page.result.job_warnings
    assert warning.message == (
        "The positions are stated in WGS84(G2139) and dated 2019-03-01, outside "
        "WGS84(G2139)'s period of use, which is from 2021-01-03 to 2024-01-06 "
        "(NGA replaced it with WGS84(G2296) on 2024-01-07). The date is before "
        "NGA put WGS84(G2139) into use, so WGS84(G2139) was not the realization "
        "in use on that date. Reprocessed data can legitimately carry a later "
        "realization, so the job is converted as stated - but positions "
        "labelled with the wrong realization look exactly like this. Check "
        "which realization the positions are in."
    )
    if which == "single":
        assert page.warnings_label.text() == warning.message
    else:
        assert page.status_label.toolTip().startswith(warning.message)


# --------------------------------------------------------------------------
# Closing gate, I5: the Multi point "in file" tooltip names the height kind.
# --------------------------------------------------------------------------


def test_the_in_file_tooltip_says_what_kind_of_height_is_read(window):
    """Shown in Horizontal only (#48). It said "Orthometric heights are read
    from the file's Z column" on ELLIPSOID jobs too (since 0.6.0) - false
    there. Each kind's sentence, and it follows the control both ways.

    Expected: the ORTHOMETRIC wording is the one #48 pinned, unchanged
    ("not converted between vertical datums", "re-expresses", no
    "unchanged"); the ELLIPSOID wording says ellipsoid heights are read and
    are not converted to elevations, and names neither "Orthometric" nor
    "elevation" as what is read.
    """
    tip = window.elevation_in_file.toolTip
    choose(window.height_kind_combo, HeightKind.ORTHOMETRIC)
    assert tip().startswith("Orthometric heights are read from the file's Z column.")
    assert "not converted between vertical datums" in tip()
    assert "re-expresses" in tip() and "unchanged" not in tip()

    choose(window.height_kind_combo, HeightKind.ELLIPSOID)
    assert tip().startswith("Ellipsoid heights are read from the file's Z column.")
    assert "Orthometric" not in tip()
    assert "not converted to elevations in this mode" in tip()
    assert "transformed with the position when the job changes frame" in tip()
    assert "re-expresses" in tip() and "unchanged" not in tip()

    choose(window.height_kind_combo, HeightKind.ORTHOMETRIC)
    assert tip().startswith("Orthometric heights are read")
