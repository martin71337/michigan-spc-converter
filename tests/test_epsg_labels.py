"""EPSG codes in the system labels (DESIGN.md #72, docs/PLAN-utm-epsg.md D1-D3).

The owner's instruction, 2026-10-29: every system names its EPSG code in
parentheses. His decision D1: a zone's code FOLLOWS ITS SIDE'S UNITS BOX, with
the unit named; D2: where EPSG has no code, none is shown; D3 (lead's): the
geodetic entries carry the frame's geographic 2D code.

Every expected code below is hand-written, with the EPSG CRS name it belongs
to in a comment. They were read from the EPSG dataset v12.029 (2025-10-02) and
checked against MCX's own records by review/utm-u0/measure.py; they are typed
here, not derived from michspc.spc.epsg, so a wrong code in the table fails.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from michspc.gui import controls, settings_store  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.window import MainWindow  # noqa: E402
from michspc.spc import epsg  # noqa: E402
from michspc.spc.frames import (  # noqa: E402
    ALL_FRAMES,
    ITRF2014,
    ITRF2020,
    NAD83_2011,
    NATRF2022,
    WGS84,
    WGS84_G1762,
    WGS84_G2139,
    WGS84_G2296,
)
from michspc.spc.units import (  # noqa: E402
    ALL_UNITS,
    INTERNATIONAL_FEET,
    METERS,
    US_SURVEY_FEET,
)
from michspc.spc.zones import (  # noqa: E402
    ALL_ZONES,
    MI_CENTRAL,
    MI_NORTH,
    MI_SOUTH,
    SPCS2022_ZONES,
    UTM_ZONES,
    zone_by_code,
)

IFT, USFT, M = INTERNATIONAL_FEET, US_SURVEY_FEET, METERS


# --------------------------------------------------------------------------
# The labels, literally.
# --------------------------------------------------------------------------

SPCS83_LABELS = {
    # zone: {unit: label}
    MI_NORTH: {
        # "NAD83(2011) / Michigan North (ft)" is EPSG 6496, international foot.
        IFT: "Michigan North 2111 - NAD83(2011) (EPSG 6496 ift)",
        # No US survey foot CRS exists for any NAD83(2011) Michigan zone.
        USFT: "Michigan North 2111 - NAD83(2011)",
        # "NAD83(2011) / Michigan North" is EPSG 6495, metres.
        M: "Michigan North 2111 - NAD83(2011) (EPSG 6495 m)",
    },
    MI_CENTRAL: {
        # "NAD83(2011) / Michigan Central (ft)", EPSG 6494.
        IFT: "Michigan Central 2112 - NAD83(2011) (EPSG 6494 ift)",
        USFT: "Michigan Central 2112 - NAD83(2011)",
        # "NAD83(2011) / Michigan Central", EPSG 6493 - numbered BEFORE North.
        M: "Michigan Central 2112 - NAD83(2011) (EPSG 6493 m)",
    },
    MI_SOUTH: {
        # "NAD83(2011) / Michigan South (ft)", EPSG 6499.
        IFT: "Michigan South 2113 - NAD83(2011) (EPSG 6499 ift)",
        USFT: "Michigan South 2113 - NAD83(2011)",
        # "NAD83(2011) / Michigan South", EPSG 6498 (6497 is the oblique Mercator).
        M: "Michigan South 2113 - NAD83(2011) (EPSG 6498 m)",
    },
}


@pytest.mark.parametrize("zone", list(SPCS83_LABELS), ids=lambda z: z.code)
@pytest.mark.parametrize("unit", ALL_UNITS, ids=lambda u: u.code)
def test_every_spcs83_label_names_the_code_of_its_unit(zone, unit):
    assert controls.zone_label(zone, unit) == SPCS83_LABELS[zone][unit]


UTM_LABELS = {
    # "NAD83(2011) / UTM zone 15N" EPSG 6344, 16N 6345, 17N 6346; metres only,
    # so whichever unit the side holds, choosing UTM puts it on metres and
    # the metre code is the one shown.
    "15N": "NAD83(2011) / UTM zone 15N (EPSG 6344 m)",
    "16N": "NAD83(2011) / UTM zone 16N (EPSG 6345 m)",
    "17N": "NAD83(2011) / UTM zone 17N (EPSG 6346 m)",
    # No NATRF2022 UTM CRS exists in EPSG v12.029 (D2).
    "15N-2022": "NATRF2022 / UTM zone 15N",
    "16N-2022": "NATRF2022 / UTM zone 16N",
    "17N-2022": "NATRF2022 / UTM zone 17N",
}


@pytest.mark.parametrize("code", list(UTM_LABELS))
@pytest.mark.parametrize("unit", ALL_UNITS, ids=lambda u: u.code)
def test_every_utm_label(code, unit):
    """Through ``zone_label`` directly: no dropdown offers UTM until U5."""
    assert controls.zone_label(zone_by_code(code), unit) == UTM_LABELS[code]


@pytest.mark.parametrize("unit", ALL_UNITS, ids=lambda u: u.code)
def test_no_spcs2022_zone_shows_a_code(unit):
    """EPSG v12.029 has no Michigan SPCS2022 CRS (D2): never a guessed code."""
    for zone in SPCS2022_ZONES:
        assert "EPSG" not in controls.zone_label(zone, unit)
        assert controls.zone_label(zone, unit) == (
            f"{zone.name} {zone.code} - NATRF2022"
        )


GEODETIC_LABELS = {
    # Each frame's geographic 2D CRS.
    NAD83_2011: "NAD83(2011) geodetic (latitude / longitude) (EPSG 6318)",
    NATRF2022: "NATRF2022 geodetic (latitude / longitude) (EPSG 10968)",
    WGS84_G1762: "WGS84(G1762) geodetic (latitude / longitude) (EPSG 9057)",
    WGS84_G2139: "WGS84(G2139) geodetic (latitude / longitude) (EPSG 9755)",
    WGS84_G2296: "WGS84(G2296) geodetic (latitude / longitude) (EPSG 10606)",
    ITRF2014: "ITRF2014 geodetic (latitude / longitude) (EPSG 9000)",
    ITRF2020: "ITRF2020 geodetic (latitude / longitude) (EPSG 9990)",
}


def test_every_offered_frame_names_its_geographic_2d_code():
    assert [choice.frame for choice in controls.GEODETIC_CHOICES] == list(
        GEODETIC_LABELS
    )
    for choice in controls.GEODETIC_CHOICES:
        assert choice.label == GEODETIC_LABELS[choice.frame]
    # The bare WGS 84 record is refused by name and has no code; 4326 is the
    # ensemble of every realization, the ambiguity the refusal is for.
    assert epsg.frame_code(WGS84) is None
    # Not the 3D code: NAD83(2011) geographic 3D is 6319.
    assert "6319" not in controls.geodetic_label(NAD83_2011)


def test_the_auto_entries_carry_no_code():
    for choice in controls.AUTO_CHOICES:
        assert "EPSG" not in choice.label


# --------------------------------------------------------------------------
# One rule: the label predicts the unit the Units box will hold.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.code)
@pytest.mark.parametrize("unit", ALL_UNITS, ids=lambda u: u.code)
def test_the_label_and_the_units_box_follow_one_rule(qapp, zone, unit):
    """For every zone and every unit a side might hold before it is chosen.

    The Units box is rebuilt for the zone exactly as the tabs rebuild it, and
    the unit it then holds is the unit whose code the label showed.
    """
    combo = controls.unit_combo(None)
    combo.setCurrentIndex(combo.findData(unit))
    controls.refresh_unit_combo(combo, controls.units_for_selection(zone))
    held = combo.currentData()
    assert held is controls.unit_if_chosen(zone, unit)
    assert controls.zone_label(zone, unit) == controls.zone_label(zone, held)
    code = epsg.zone_code(zone, held)
    if code is None:
        assert "EPSG" not in controls.zone_label(zone, unit)
    else:
        assert controls.zone_label(zone, unit).endswith(f" (EPSG {code} {held.code})")


# --------------------------------------------------------------------------
# Both tabs, both sides: the rows re-render when the side's unit changes.
# --------------------------------------------------------------------------


@pytest.fixture
def window(qapp):
    win = MainWindow(store=settings_store.MemoryStore())
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def tabs(window):
    return (window, window.single_point)


def row_text(combo, zone) -> str:
    return combo.itemText(combo.findData(zone))


def choose(combo, data) -> None:
    index = combo.findData(data)
    assert index >= 0, data
    combo.setCurrentIndex(index)


@pytest.mark.parametrize("which", ["multi", "single"])
def test_each_side_follows_its_own_units_box(window, which):
    page = window if which == "multi" else window.single_point
    # Both open on international feet.
    assert row_text(page.from_zone, MI_SOUTH) == SPCS83_LABELS[MI_SOUTH][IFT]
    assert row_text(page.to_zone, MI_SOUTH) == SPCS83_LABELS[MI_SOUTH][IFT]

    choose(page.input_unit, M)
    assert row_text(page.from_zone, MI_SOUTH) == SPCS83_LABELS[MI_SOUTH][M]
    assert row_text(page.from_zone, MI_NORTH) == SPCS83_LABELS[MI_NORTH][M]
    # The TO side did not move.
    assert row_text(page.to_zone, MI_SOUTH) == SPCS83_LABELS[MI_SOUTH][IFT]

    choose(page.output_unit, USFT)
    assert row_text(page.to_zone, MI_CENTRAL) == SPCS83_LABELS[MI_CENTRAL][USFT]
    assert row_text(page.from_zone, MI_CENTRAL) == SPCS83_LABELS[MI_CENTRAL][M]

    # The geodetic rows never change with a unit.
    nad = controls.geodetic_choice(NAD83_2011)
    assert row_text(page.from_zone, nad) == GEODETIC_LABELS[NAD83_2011]
    assert row_text(page.to_zone, nad) == GEODETIC_LABELS[NAD83_2011]


@pytest.mark.parametrize("which", ["multi", "single"])
def test_the_snap_case_relabels_the_rows(window, which):
    """US survey feet, then an SPCS2022 zone: the Units box snaps to
    international feet, and the SPCS 83 rows follow it."""
    page = window if which == "multi" else window.single_point
    choose(page.input_unit, USFT)
    assert row_text(page.from_zone, MI_SOUTH) == SPCS83_LABELS[MI_SOUTH][USFT]
    choose(page.from_zone, SPCS2022_ZONES[1])
    assert page.input_unit.currentData() is IFT
    assert row_text(page.from_zone, MI_SOUTH) == SPCS83_LABELS[MI_SOUTH][IFT]


@pytest.mark.parametrize("which", ["multi", "single"])
def test_relabelling_fires_no_selection_signal(window, which):
    page = window if which == "multi" else window.single_point
    choose(page.from_zone, MI_SOUTH)
    fired = []
    page.from_zone.currentIndexChanged.connect(fired.append)
    choose(page.input_unit, M)
    choose(page.input_unit, IFT)
    assert fired == []
    assert page.from_zone.currentData() is MI_SOUTH
    assert page.from_zone.currentText() == SPCS83_LABELS[MI_SOUTH][IFT]


# --------------------------------------------------------------------------
# The table refuses what the registries do not hold.
# --------------------------------------------------------------------------


def test_the_table_refuses_a_zone_the_registry_does_not_hold():
    with pytest.raises(epsg.EpsgTableError, match="2114"):
        epsg.check_table({"2114": ((M, 6500),)}, {})


def test_the_table_refuses_a_unit_the_zone_does_not_publish():
    with pytest.raises(epsg.EpsgTableError, match="US survey feet|does not publish"):
        epsg.check_table({"16N": ((USFT, 6345),)}, {})
    with pytest.raises(epsg.EpsgTableError, match="does not publish"):
        epsg.check_table({SPCS2022_ZONES[0].code: ((USFT, 1),)}, {})


def test_the_table_refuses_a_frame_that_is_not_usable():
    with pytest.raises(epsg.EpsgTableError, match="WGS84"):
        epsg.check_table({}, {WGS84.code: 4326})
    with pytest.raises(epsg.EpsgTableError, match="NAD27"):
        epsg.check_table({}, {"NAD27": 4267})


def test_the_shipped_table_passes_its_own_check_and_holds_exactly_these_entries():
    epsg.check_table(epsg.ZONE_CODES, epsg.FRAME_CODES)
    assert set(epsg.ZONE_CODES) == {"2111", "2112", "2113", "15N", "16N", "17N"}
    assert set(epsg.FRAME_CODES) == {
        frame.code for frame in ALL_FRAMES if frame.is_usable
    }
    # No NATRF2022 UTM record is keyed (D2).
    assert all(zone.code not in epsg.ZONE_CODES for zone in UTM_ZONES[3:])
