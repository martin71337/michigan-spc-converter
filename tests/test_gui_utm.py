"""Work package U5: the six UTM zones reach both tabs (DESIGN.md #72).

docs/PLAN-utm-epsg.md section 4, U5, and decisions D1 (labels follow the
Units box), D4 (metres only), D5 (both frames) and D6 (a block of its own,
last, and one Options group on by default). Every behaviour below is the
INTERFACE half; the conversions themselves are pinned through the core in
tests/test_utm.py and tests/test_utm_jobs.py, and are only held here to the
same NCAT anchors so the tabs cannot drift from them.

Expected values: the frozen NCAT captures in tests/fixtures/utm_anchors.py
(production NCAT, NAD83(2011), and beta NCAT, NATRF2022), and for the State
Plane leg NCAT's own SPCS 83 coordinate in the same frozen production
response. NCAT prints metres to 0.001 m, so a coordinate is held within
0.0005 m plus float slack; the tabs show 4 decimals, read back as floats.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

from michspc.gui import controls, options, settings_store  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.window import UNITS_SNAPPED_STATUS, MainWindow  # noqa: E402
from michspc.spc.frames import (  # noqa: E402
    ALL_FRAMES,
    NAD83_2011,
    NATRF2022,
    WGS84_G2296,
)
from michspc.spc.convert import WarningCode  # noqa: E402
from michspc.spc.tm import TransverseMercatorDomainError  # noqa: E402
from michspc.spc.units import (  # noqa: E402
    INTERNATIONAL_FEET,
    METERS,
    US_SURVEY_FEET,
)
from michspc.spc.zones import (  # noqa: E402
    ALL_ZONES,
    UTM_SYSTEM,
    UTM_ZONES,
    zone_by_code,
)
from tests.fixtures.utm_anchors import (  # noqa: E402
    NAD83_2011_ANCHORS,
    NATRF2022_ANCHORS,
)

REPO = Path(__file__).resolve().parent.parent

NAD = controls.geodetic_choice(NAD83_2011)
NAT = controls.geodetic_choice(NATRF2022)
G2296 = controls.geodetic_choice(WGS84_G2296)
AUTO_NAD = controls.auto_choice(NAD83_2011)
GLOBAL = tuple(
    controls.geodetic_choice(frame)
    for frame in ALL_FRAMES
    if frame.is_usable and frame.is_time_dependent
)

UTM16_NAD = zone_by_code("16N")
UTM16_NAT = zone_by_code("16N-2022")
NAD_ZONES = tuple(zone for zone in ALL_ZONES if zone.frame is NAD83_2011)
NAT_ZONES = tuple(zone for zone in ALL_ZONES if zone.frame is NATRF2022)
UTM_NAD = tuple(zone for zone in UTM_ZONES if zone.frame is NAD83_2011)
UTM_NAT = tuple(zone for zone in UTM_ZONES if zone.frame is NATRF2022)

NCAT_COORDINATE_TOLERANCE_M = 0.0005 + 1e-9
"""NCAT prints metres to 0.001 m; half a unit, plus float slack."""

NAD_ANCHOR = NAD83_2011_ANCHORS[0]
"""43.8138851900 N, 84.4055193200 W, UTM zone 16: production NCAT,
review/autozone-r0/raw/ncat_probe/r2_spcs83_000.json, N 4,854,473.717 m,
E 708,662.368 m."""

NAT_ANCHOR = next(a for a in NATRF2022_ANCHORS if a.zone == 16)
"""The first beta NCAT NATRF2022 anchor (every one of the 34 is zone 16)."""


@pytest.fixture(scope="module")
def qapp():
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


@pytest.fixture
def window(qapp):
    win = MainWindow(store=settings_store.MemoryStore())
    win.shown_failures = []
    win._show_failure = win.shown_failures.append
    win._ask_overwrite = lambda existing, error: True
    tab = win.single_point
    tab.shown_failures = []
    tab._show_failure = tab.shown_failures.append
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def pages(window):
    return {"single": window.single_point, "multi": window}


def choose(combo, data) -> None:
    index = combo.findData(data)
    if index < 0:
        raise AssertionError(f"{combo!r} has no entry for {data!r}")
    combo.setCurrentIndex(index)


def offered_units(combo) -> list:
    return [combo.itemData(i) for i in range(combo.count())]


def grayed(combo) -> list:
    """Every SHOWN entry the user cannot choose (tests/test_gui_frames.py's
    definition: a row the Options hide is disabled too, but not grayed)."""
    out = []
    for index in range(combo.count()):
        data = combo.itemData(index)
        if data is None or combo.view().isRowHidden(index):
            continue
        if not combo.model().item(index).flags() & Qt.ItemFlag.ItemIsEnabled:
            out.append(data)
    return out


def visible(combo) -> list:
    return [
        combo.itemData(i) for i in range(combo.count()) if not combo.view().isRowHidden(i)
    ]


def ncat_spc(anchor) -> tuple[str, float, float]:
    """NCAT's own SPCS 83 zone code and metric coordinate for the anchor's position."""
    raw = json.loads((REPO / anchor.capture).read_text(encoding="utf-8"))
    code = raw["spcZone"].rsplit("-", 1)[1]
    northing = float(raw["spcNorthing_m"].replace(",", ""))
    easting = float(raw["spcEasting_m"].replace(",", ""))
    return code, northing, easting


def row(tab, label: str, nth: int = 0) -> str:
    values = [text for name, text in tab.displayed_rows() if name == label]
    return values[nth]


# ==========================================================================
# 1. Units: a UTM zone is metres only (D4), on both tabs and both sides.
# ==========================================================================


@pytest.mark.parametrize("which", ["single", "multi"])
def test_choosing_a_utm_zone_leaves_only_meters_on_that_side(window, which):
    page = pages(window)[which]
    for zone in UTM_ZONES:
        choose(page.from_zone, zone)
        assert offered_units(page.input_unit) == [METERS]
        choose(page.to_zone, zone)
        assert offered_units(page.output_unit) == [METERS]
        assert page.output_unit.currentData() is METERS


def test_the_multi_point_snap_from_international_feet_clears_the_table(
    window, tmp_path
):
    """A written result in international feet, then a UTM TO zone: the unit
    snaps to metres, and the table that described the feet run goes with it,
    saying so (UNITS_SNAPPED_STATUS, the #26 stale-result rule)."""
    source = tmp_path / "in.csv"
    source.write_text(
        f"1,{NAD_ANCHOR.latitude},{NAD_ANCHOR.longitude.lstrip('-')},,A\n",
        encoding="utf-8",
    )
    window.tabs.setCurrentIndex(1)
    window.input_edit.setText(str(source))
    window.output_edit.setText(str(tmp_path))
    choose(window.from_zone, NAD)
    choose(window.to_zone, zone_by_code("2112"))
    assert window.output_unit.currentData() is INTERNATIONAL_FEET
    assert window.convert() is True, window.shown_failures
    assert window.model.rowCount() == 1

    choose(window.to_zone, UTM16_NAD)
    assert window.output_unit.currentData() is METERS
    assert window.model.rowCount() == 0
    assert window.status_label.text() == UNITS_SNAPPED_STATUS


def test_the_single_point_result_does_not_survive_a_snap_to_meters(window):
    tab = window.single_point
    choose(tab.from_zone, NAD)
    choose(tab.to_zone, zone_by_code("2112"))
    tab.first_edit.setText(NAD_ANCHOR.latitude)
    tab.second_edit.setText(NAD_ANCHOR.longitude.lstrip("-"))
    assert tab.convert() is True, tab.shown_failures
    assert tab.result is not None

    choose(tab.to_zone, UTM16_NAD)
    assert tab.output_unit.currentData() is METERS
    assert tab.result is None
    assert tab.sections is None


# ==========================================================================
# 2. EPSG labels (D1, D2): NAD83(2011) UTM rows name their metre code
#    whatever the side's unit; NATRF2022 UTM rows name none.
# ==========================================================================


EPSG_BY_CODE = {"15N": 6344, "16N": 6345, "17N": 6346}
"""EPSG v12.029: "NAD83(2011) / UTM zone 15N/16N/17N", metres only."""


@pytest.mark.parametrize("which", ["single", "multi"])
@pytest.mark.parametrize("unit", [INTERNATIONAL_FEET, US_SURVEY_FEET, METERS])
def test_utm_rows_carry_their_metre_code_whatever_the_unit(window, which, unit):
    page = pages(window)[which]
    choose(page.from_zone, NAD)  # a geodetic FROM offers every unit
    choose(page.input_unit, unit)
    for zone in UTM_NAD:
        text = page.from_zone.itemText(page.from_zone.findData(zone))
        assert text == f"{zone.name} (EPSG {EPSG_BY_CODE[zone.code]} m)"
    for zone in UTM_NAT:
        text = page.from_zone.itemText(page.from_zone.findData(zone))
        assert text == zone.name
        assert "EPSG" not in text


# ==========================================================================
# 3. Frame graying (#64) reaches the UTM rows by FRAME.
# ==========================================================================


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_nad83_utm_zone_grays_every_natrf2022_entry_and_nothing_else(window, which):
    page = pages(window)[which]
    choose(page.from_zone, UTM16_NAD)
    # A zone FROM grays the Auto entry (plan L1), as every zone FROM does.
    assert set(grayed(page.to_zone)) == {NAT, *NAT_ZONES, AUTO_NAD}
    for zone in UTM_NAD:
        assert zone not in grayed(page.to_zone)


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_natrf2022_utm_zone_grays_every_nad83_and_global_entry(window, which):
    # The five WGS 84 / ITRF rows are hidden by default (DESIGN.md #71), and a
    # hidden row is not grayed; show them so their graying is visible.
    window.apply_options(
        options.DEFAULT_OPTIONS.with_groups(
            *(options.group_of(choice) for choice in GLOBAL)
        )
    )
    page = pages(window)[which]
    choose(page.from_zone, UTM16_NAT)
    assert set(grayed(page.to_zone)) == {NAD, *NAD_ZONES, *GLOBAL, AUTO_NAD}
    for zone in UTM_NAT:
        assert zone not in grayed(page.to_zone)


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_wgs84_entry_grays_the_natrf2022_utm_rows_not_the_nad83_ones(window, which):
    window.apply_options(
        options.DEFAULT_OPTIONS.with_groups(
            *(options.group_of(choice) for choice in GLOBAL)
        )
    )
    page = pages(window)[which]
    choose(page.from_zone, G2296)
    gray = grayed(page.to_zone)
    for zone in UTM_NAT:
        assert zone in gray
    for zone in UTM_NAD:
        assert zone not in gray
    # Auto on NAD83(2011) stays available from a WGS 84 position (plan L2).
    assert AUTO_NAD not in gray


# ==========================================================================
# 4. Options (D6): one group, on by default; hiding it hides the block.
# ==========================================================================


UTM_GROUP = next(group for group in options.LIST_GROUPS if group.system == UTM_SYSTEM)


@pytest.mark.parametrize("which", ["single", "multi"])
def test_switching_the_utm_group_off_hides_all_six_rows_and_their_separator(
    window, which
):
    page = pages(window)[which]
    shown_before = visible(page.from_zone)
    assert shown_before[-7:] == [None, *UTM_ZONES]

    window.apply_options(options.DEFAULT_OPTIONS.with_groups(UTM_GROUP, shown=False))
    shown_after = visible(page.from_zone)
    assert not set(UTM_ZONES) & set(shown_after)
    assert shown_after == shown_before[:-7]
    assert shown_after[-1] is not None  # no rule left ending the list


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_selected_utm_row_hidden_by_options_is_cleared_and_said_so(window, which):
    page = pages(window)[which]
    choose(page.from_zone, NAD)
    choose(page.to_zone, UTM16_NAD)
    window.apply_options(options.DEFAULT_OPTIONS.with_groups(UTM_GROUP, shown=False))
    assert page.to_zone.currentData() == controls.UNCHOSEN
    assert page.from_zone.currentData() is NAD
    assert page.status_label.text() == controls.OPTIONS_RESET_STATUS


def test_the_utm_group_alone_satisfies_the_one_zone_group_rule():
    """"At least one zone group stays on" counts UTM too, and the refusal
    names zones without naming State Plane (DESIGN.md #72, U5)."""
    zone_groups = [group for group in options.LIST_GROUPS if group.is_zone_group]
    only_utm = options.DEFAULT_OPTIONS
    for group in zone_groups:
        if group is not UTM_GROUP:
            only_utm = only_utm.with_groups(group, shown=False)
    assert options.options_problem(only_utm.shown) is None

    none = only_utm.shown - {UTM_GROUP.key}
    problem = options.options_problem(none)
    assert problem == (
        "Switch on at least one group of zones: with none, the system lists "
        "would hold no zone to choose."
    )
    assert "State Plane" not in problem


# ==========================================================================
# 5. Convert on both tabs reproduces NCAT, both frames.
# ==========================================================================


@pytest.mark.parametrize(
    "anchor, frame_choice, zone",
    [(NAD_ANCHOR, NAD, UTM16_NAD), (NAT_ANCHOR, NAT, UTM16_NAT)],
    ids=["NAD83(2011)", "NATRF2022"],
)
def test_single_point_geodetic_to_utm_reproduces_ncat(window, anchor, frame_choice, zone):
    tab = window.single_point
    choose(tab.from_zone, frame_choice)
    choose(tab.to_zone, zone)
    tab.first_edit.setText(anchor.latitude)
    tab.second_edit.setText(anchor.longitude.lstrip("-"))  # positive west
    assert tab.convert() is True, tab.shown_failures
    assert row(tab, "Zone") == controls.zone_label(zone, METERS)
    assert float(row(tab, "Northing")) == pytest.approx(
        float(anchor.northing), abs=NCAT_COORDINATE_TOLERANCE_M
    )
    assert float(row(tab, "Easting")) == pytest.approx(
        float(anchor.easting), abs=NCAT_COORDINATE_TOLERANCE_M
    )


def test_single_point_utm_to_geodetic_reproduces_ncat(window):
    tab = window.single_point
    choose(tab.from_zone, UTM16_NAD)
    choose(tab.to_zone, NAD)
    tab.first_edit.setText(NAD_ANCHOR.northing)
    tab.second_edit.setText(NAD_ANCHOR.easting)
    assert tab.convert() is True, tab.shown_failures
    # 0.0005 m at NCAT's printed grid digit is under 1e-8 degree here;
    # the panel shows 8 decimals of a degree.
    assert float(row(tab, "Latitude").rstrip("°")) == pytest.approx(
        float(NAD_ANCHOR.latitude), abs=1e-8 + 1e-12
    )
    assert float(row(tab, "Longitude").rstrip("°")) == pytest.approx(
        abs(float(NAD_ANCHOR.longitude)), abs=1e-8 + 1e-12
    )


def test_multi_point_utm_to_spcs83_reproduces_ncat_s_own_state_plane_value(
    window, tmp_path
):
    """NCAT's UTM coordinate in, NCAT's own SPCS 83 coordinate for the same
    position out, through the real tab and the written archive's table."""
    code, ncat_n, ncat_e = ncat_spc(NAD_ANCHOR)
    source = tmp_path / "in.csv"
    source.write_text(f"1,{NAD_ANCHOR.northing},{NAD_ANCHOR.easting},,A\n", encoding="utf-8")
    window.tabs.setCurrentIndex(1)
    window.input_edit.setText(str(source))
    window.output_edit.setText(str(tmp_path))
    choose(window.from_zone, UTM16_NAD)
    choose(window.to_zone, zone_by_code(code))
    choose(window.output_unit, METERS)
    assert window.convert() is True, window.shown_failures
    northing = float(window.model.index(0, 1).data())
    easting = float(window.model.index(0, 2).data())
    # Two NCAT roundings (the UTM input and the SPC truth), each 0.0005 m.
    assert northing == pytest.approx(ncat_n, abs=2 * NCAT_COORDINATE_TOLERANCE_M)
    assert easting == pytest.approx(ncat_e, abs=2 * NCAT_COORDINATE_TOLERANCE_M)


# ==========================================================================
# 6. Nothing on screen calls a UTM job State Plane.
# ==========================================================================


def test_no_state_plane_wording_on_a_utm_single_point_result(window):
    tab = window.single_point
    choose(tab.from_zone, NAD)
    choose(tab.to_zone, UTM16_NAD)
    tab.first_edit.setText(NAD_ANCHOR.latitude)
    tab.second_edit.setText(NAD_ANCHOR.longitude.lstrip("-"))
    assert tab.convert() is True, tab.shown_failures
    shown = " ".join(
        [f"{name} {text}" for name, text in tab.displayed_rows()]
        + [tab.status_label.text(), tab.warnings_label.text()]
    )
    assert "State Plane" not in shown
    assert "SPCS" not in shown


def test_no_state_plane_wording_on_a_utm_multi_point_table(window, tmp_path):
    source = tmp_path / "in.csv"
    source.write_text(
        f"1,{NAD_ANCHOR.latitude},{NAD_ANCHOR.longitude.lstrip('-')},,A\n",
        encoding="utf-8",
    )
    window.tabs.setCurrentIndex(1)
    window.input_edit.setText(str(source))
    window.output_edit.setText(str(tmp_path))
    choose(window.from_zone, NAD)
    choose(window.to_zone, UTM16_NAD)
    assert window.convert() is True, window.shown_failures
    model = window.model
    headers = [
        model.headerData(c, Qt.Orientation.Horizontal) for c in range(model.columnCount())
    ]
    cells = [model.index(0, c).data() for c in range(model.columnCount())]
    shown = " ".join(str(x) for x in (*headers, *cells, window.status_label.text()))
    assert "State Plane" not in shown
    assert "SPCS" not in shown


# ==========================================================================
# 7. The outside-Michigan warning and the 4.8-degree refusal reach the screen.
# ==========================================================================


def test_a_16n_coordinate_declared_17n_warns_on_the_single_point_tab(window):
    tab = window.single_point
    choose(tab.from_zone, zone_by_code("17N"))
    choose(tab.to_zone, NAD)
    tab.first_edit.setText(NAD_ANCHOR.northing)
    tab.second_edit.setText(NAD_ANCHOR.easting)
    assert tab.convert() is True, tab.shown_failures
    warnings = tab.warnings_label.text()
    assert "outside Michigan" in warnings
    assert "500,000 m false easting" in warnings


def test_a_16n_file_declared_17n_warns_on_the_multi_point_tab(window, tmp_path):
    source = tmp_path / "in.csv"
    source.write_text(f"1,{NAD_ANCHOR.northing},{NAD_ANCHOR.easting},,A\n", encoding="utf-8")
    window.tabs.setCurrentIndex(1)
    window.input_edit.setText(str(source))
    window.output_edit.setText(str(tmp_path))
    choose(window.from_zone, zone_by_code("17N"))
    choose(window.to_zone, NAD)
    assert window.convert() is True, window.shown_failures
    assert "warning" in window.status_label.text()
    assert not window.status_label.text().endswith("0 warnings.")
    cells = " ".join(
        str(window.model.index(0, c).data()) for c in range(window.model.columnCount())
    )
    # The table's Warnings column carries the warning codes; the sentence is
    # the job record's and the audit CSV's.
    assert WarningCode.POINT_OUTSIDE_MICHIGAN.value in cells


def test_the_domain_refusal_reaches_the_dialog_and_status_line_intact(window):
    """42.0 N, 82.5 W into 15N: 10.5 degrees from its meridian, refused
    (the interim gate's MEDIUM 1 input). The dialog receives the engine's
    refusal itself, and the status line its first line, in full."""
    tab = window.single_point
    choose(tab.from_zone, NAD)
    choose(tab.to_zone, zone_by_code("15N"))
    tab.first_edit.setText("42.0")
    tab.second_edit.setText("82.5")
    assert tab.convert() is False
    (error,) = tab.shown_failures
    assert isinstance(error, TransverseMercatorDomainError)
    message = str(error)
    assert "4.8 degrees" in message
    assert "UTM zone 17N" in message
    assert tab.status_label.text() == f"Refused: {message.splitlines()[0]}"
    assert tab.status_label.toolTip() == message
