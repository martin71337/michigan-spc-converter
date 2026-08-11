"""The height-kind control on both tabs, and the labels it changes (WP-E4).

The control is the owner's: it sits beneath the "in file" button on the Multi
point tab, grayed unless that button is selected, and it opens on Orthometric
so every existing job is unchanged. It is present in all three modes, because
the question "what kind of height is this?" is asked in all three - a partial
amendment to #48, which hid the whole Elevations row in the vertical modes.

The labels are the other half. A row reading "Elevation" over an unconverted
ellipsoid height is the ordinary-looking wrong number this program is built
against, and in horizontal mode the Z column holds exactly that.
"""

from __future__ import annotations

import os

# MUST precede any Qt import (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402

from michspc.fileio import geoid, pnezd  # noqa: E402
from michspc.gui import results_model  # noqa: E402
from michspc.gui.controls import (  # noqa: E402
    HEIGHT_KIND_ELLIPSOID,
    HEIGHT_KIND_LABEL,
    HEIGHT_KIND_ORTHOMETRIC,
    height_kind_combo,
    height_kind_for,
)
from michspc.gui.single_point import SinglePointTab  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.window import MainWindow  # noqa: E402
from michspc.job import (  # noqa: E402
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc.units import METERS  # noqa: E402
from michspc.spc.vertical import NAVD88, HeightKind  # noqa: E402
from tests.fixtures.geoid_anchors import GEOID_ANCHORS  # noqa: E402

HOUGHTON_LATITUDE = 47.1211
HOUGHTON_LONGITUDE = -88.5694
N18_FIXTURE = next(
    a.geoid_height_m
    for a in GEOID_ANCHORS
    if a.latitude == HOUGHTON_LATITUDE and a.longitude == HOUGHTON_LONGITUDE
)
HOUGHTON_ELLIPSOID_M = 200.000 + N18_FIXTURE


@pytest.fixture(scope="module")
def qapp():
    """One QApplication for the whole module — a second one in the same
    process crashes the interpreter (docs/method/TOOLING.md)."""
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


@pytest.fixture
def window(qapp):
    return MainWindow()


@pytest.fixture
def tab(window):
    return window.single_point


# ==========================================================================
# The control itself.
# ==========================================================================


def test_the_control_opens_on_orthometric_on_both_tabs(window, tab):
    """The owner's instruction, and the reason every existing job is
    unchanged: the default IS the status quo."""
    for combo in (window.height_kind_combo, tab.height_kind_combo):
        assert combo.currentData() is HeightKind.ORTHOMETRIC
        assert combo.currentText() == HEIGHT_KIND_ORTHOMETRIC
        assert [
            combo.itemText(i) for i in range(combo.count())
        ] == [HEIGHT_KIND_ORTHOMETRIC, HEIGHT_KIND_ELLIPSOID]


def test_the_control_carries_no_tooltip_on_either_tab(window, tab):
    """#34 and #51: the item strings carry the meaning."""
    assert window.height_kind_combo.toolTip() == ""
    assert tab.height_kind_combo.toolTip() == ""


def test_the_control_is_grayed_unless_elevations_come_from_the_file(window):
    """The owner's placement rule, 2026-08-11. Grayed, not hidden — #50's own
    distinction: a disabled control shows the question exists."""
    window.mode_horizontal.setChecked(True)
    assert window.elevation_in_file.isChecked()
    assert window.height_kind_combo.isEnabled()

    window.elevation_in_file.setChecked(False)
    assert not window.height_kind_combo.isEnabled()
    assert not window.height_kind_combo.isHidden()


def test_the_control_survives_into_the_vertical_modes(window):
    """The partial amendment to #48. The "in file" button hides there; this
    control does not, because it is where the answer decides whether the Z
    column gets converted at all."""
    for mode_button in (
        window.mode_horizontal,
        window.mode_vertical,
        window.mode_vertical_only,
    ):
        mode_button.setChecked(True)
        assert not window.height_kind_combo.isHidden()
        assert not window.height_kind_label.isHidden()
        assert not window.elevations_label.isHidden()


def test_height_kind_for_refuses_a_selection_that_is_not_a_kind(qapp):
    """Guessing orthometric would silently answer the question the control
    exists to ask."""
    combo = height_kind_combo(None)
    combo.addItem("nonsense", None)
    combo.setCurrentIndex(combo.count() - 1)

    with pytest.raises(ValueError) as caught:
        height_kind_for(combo)
    assert "HeightKind" in str(caught.value)


# ==========================================================================
# What the control reaches.
# ==========================================================================


def test_the_multi_point_tab_emits_the_chosen_kind(window, tmp_path):
    source = tmp_path / "gnss.csv"
    source.write_text("1,500000.0,300000.0,166.204,GNSS\n", encoding="utf-8")
    window.input_edit.setText(str(source))
    window.output_edit.setText(str(tmp_path))
    window.from_zone.setCurrentIndex(1)
    window.to_zone.setCurrentIndex(2)

    window.height_kind_combo.setCurrentIndex(
        window.height_kind_combo.findData(HeightKind.ELLIPSOID)
    )
    settings = window.settings()
    assert settings is not None
    assert settings.input_height_kind is HeightKind.ELLIPSOID

    window.height_kind_combo.setCurrentIndex(
        window.height_kind_combo.findData(HeightKind.ORTHOMETRIC)
    )
    assert window.settings().input_height_kind is HeightKind.ORTHOMETRIC


def test_the_single_point_tab_emits_the_chosen_kind_and_invalidates(tab):
    tab.from_zone.setCurrentIndex(1)
    tab.to_zone.setCurrentIndex(2)
    tab.first_edit.setText("500000.0")
    tab.second_edit.setText("300000.0")
    tab.elevation_edit.setText("166.204")

    tab.height_kind_combo.setCurrentIndex(
        tab.height_kind_combo.findData(HeightKind.ELLIPSOID)
    )
    settings = tab.settings()
    assert settings is not None
    assert settings.input_height_kind is HeightKind.ELLIPSOID

    tab.height_kind_combo.setCurrentIndex(
        tab.height_kind_combo.findData(HeightKind.ORTHOMETRIC)
    )
    assert tab.settings().input_height_kind is HeightKind.ORTHOMETRIC

    # And the control is WIRED to the invalidation, so moving it discards a
    # displayed result like every other control on this tab. Asserted as the
    # connection rather than by running a conversion: the defect this guards
    # against is a handler never connected (#50's own falsification seed,
    # "the new combo's invalidation disconnected"), and a receiver count of
    # zero is exactly that defect with nothing else in the way.
    assert tab.height_kind_combo.receivers("2currentIndexChanged(int)") >= 1


# ==========================================================================
# The labels.
# ==========================================================================


def _vertical_settings(**overrides) -> JobSettings:
    base = dict(
        input_path=None,
        output_directory=None,
        direction=Direction.VERTICAL_ONLY,
        source_zone=None,
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
        geoid_model=geoid.GEOID18_MODEL,
        input_height_kind=HeightKind.ELLIPSOID,
    )
    base.update(overrides)
    return JobSettings(**base)


def _houghton_source():
    return pnezd.parse_lines(
        [
            f"1,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},"
            f"{HOUGHTON_ELLIPSOID_M:.3f},GNSS"
        ]
    )


def test_a_vertical_panel_names_the_input_ellipsoid_and_the_output_model():
    result = run(_vertical_settings(), source=_houghton_source())
    sections = results_model.single_point_sections(result)

    source = next(s for s in sections if s.title == results_model.INPUT_TITLE)
    target = next(s for s in sections if s.title == results_model.OUTPUT_TITLE)
    input_labels = {v.label for v in source.values}
    output_labels = {v.label for v in target.values}

    assert "Ellipsoid height (GNSS, m)" in input_labels
    # The derived elevation names its datum AND its model: here, unlike a
    # leveled height, the number genuinely depends on the model.
    assert "Elevation (NAVD88, m) (GEOID18)" in output_labels


def test_a_horizontal_panel_keeps_calling_the_output_an_ellipsoid_height():
    """The Z was written back untouched, so promoting it to "Elevation" would
    be the falsehood this feature removes."""
    from michspc.spc.zones import MI_NORTH

    result = run(
        JobSettings(
            input_path=None,
            output_directory=None,
            direction=Direction.ZONE_TO_GEODETIC,
            source_zone=MI_NORTH,
            target_zone=None,
            input_unit=METERS,
            output_unit=METERS,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
            geoid_model=geoid.GEOID18_MODEL,
            input_height_kind=HeightKind.ELLIPSOID,
        ),
        source=pnezd.parse_lines(
            [f"1,500000.0,8000000.0,{HOUGHTON_ELLIPSOID_M:.3f},GNSS"]
        ),
    )
    labels = {
        value.label
        for section in results_model.single_point_sections(result)
        for value in section.values
    }

    assert "Ellipsoid height (GNSS, m)" in labels
    assert not any(label.startswith("Elevation (") for label in labels)


def test_the_table_heading_names_the_model_on_an_ellipsoid_job():
    result = run(_vertical_settings(), source=_houghton_source())

    assert "Elevation (NAVD88, m) (GEOID18)" in results_model.columns_for(result)
    assert results_model.table_geoid_model_name(result) == "GEOID18"


def test_an_orthometric_job_names_no_model_and_no_ellipsoid_row():
    """#52's two negatives survive the generalisation: a leveled height still
    depends on no model, and still says so by saying nothing."""
    result = run(
        _vertical_settings(input_height_kind=HeightKind.ORTHOMETRIC),
        source=pnezd.parse_lines(
            [f"1,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},200.000,LEVEL"]
        ),
    )

    assert results_model.table_geoid_model_name(result) is None
    assert "Elevation (NAVD88, m)" in results_model.columns_for(result)

    labels = {
        value.label
        for section in results_model.single_point_sections(result)
        for value in section.values
    }
    assert not any("GEOID18" in label for label in labels)
    assert not any(label.startswith("Ellipsoid height (GNSS") for label in labels)
