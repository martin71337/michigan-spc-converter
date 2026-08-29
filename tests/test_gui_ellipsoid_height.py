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
    geodetic_choice,
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
from michspc.spc.frames import NAD83_2011  # noqa: E402
from michspc.spc.units import METERS  # noqa: E402
from michspc.spc.vertical import NAVD88, HeightKind  # noqa: E402
from michspc.spc.zones import MI_NORTH  # noqa: E402
from tests.fixtures.geoid_anchors import GEOID_ANCHORS  # noqa: E402

NAD83_2011_GEODETIC = geodetic_choice(NAD83_2011)
"""The NAD83(2011) geodetic entry - one of two since H6 (DESIGN.md #62)."""


def choose(combo, data) -> None:
    """Select by record, never by index. A dropdown's indices move."""
    index = combo.findData(data)
    if index < 0:
        raise AssertionError(f"{combo!r} has no entry for {data!r}")
    combo.setCurrentIndex(index)

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
    # The wording is pinned as LITERALS, not against the constants. Comparing
    # a constant to itself passes whatever the constant says, which is the
    # vacuous-pin class the 0.6.0 gate flagged; the owner removed the "(GNSS)"
    # and "(elevation)" glosses by instruction (2026-08-11) and that decision
    # needs a test that would notice them coming back.
    assert HEIGHT_KIND_ORTHOMETRIC == "Orthometric"
    assert HEIGHT_KIND_ELLIPSOID == "Ellipsoid"

    for combo in (window.height_kind_combo, tab.height_kind_combo):
        assert combo.currentData() is HeightKind.ORTHOMETRIC
        assert combo.currentText() == "Orthometric"
        assert [
            combo.itemText(i) for i in range(combo.count())
        ] == ["Orthometric", "Ellipsoid"]


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
    # By record, not by index. These two lines read setCurrentIndex(1) and (2)
    # until H6, which was the geodetic entry and Michigan North while there was
    # exactly one geodetic entry; the second frame's entry now sits at index 2,
    # so the pair silently became geodetic-to-geodetic - not a conversion, and
    # a settings() of None. Naming the records cannot drift with the list.
    choose(window.from_zone, NAD83_2011_GEODETIC)
    choose(window.to_zone, MI_NORTH)

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
    choose(tab.from_zone, NAD83_2011_GEODETIC)
    choose(tab.to_zone, MI_NORTH)
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

    assert "Ellipsoid height (m)" in input_labels
    # Exactly ONE row carries that label: the computed factors row would hold
    # the same number under the same name, so it is dropped on these jobs.
    assert [v.label for v in source.values].count("Ellipsoid height (m)") == 1
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

    assert "Ellipsoid height (m)" in labels
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
    # And the computed ellipsoid-height row is STILL THERE on an orthometric
    # job: its suppression is opt-in with the feature, not a deletion. On a
    # leveled height h = H + N is a genuinely separate fact from the Z.
    assert "Ellipsoid height (m)" in labels


# ==========================================================================
# The owner's layout and hint round, 2026-08-11.
# ==========================================================================


def test_the_elevation_box_hints_only_where_the_elevation_is_optional(tab):
    """The #51 rule, applied to a placeholder instead of a tooltip.

    #51 removed a tooltip from this box for calling the elevation "optional"
    in all three modes. A placeholder saying the same thing sits INSIDE the
    field, which is more prominent, so the mode rule matters more, not less.
    """
    from michspc.gui.single_point import ELEVATION_PLACEHOLDER

    assert ELEVATION_PLACEHOLDER == "optional, used for combined scale factor"

    tab.mode_horizontal.setChecked(True)
    assert tab.elevation_edit.placeholderText() == ELEVATION_PLACEHOLDER

    for mode_button in (tab.mode_vertical, tab.mode_vertical_only):
        mode_button.setChecked(True)
        assert tab.elevation_edit.placeholderText() == ""

    # And back, so the hint is restored rather than lost on the first switch.
    tab.mode_horizontal.setChecked(True)
    assert tab.elevation_edit.placeholderText() == ELEVATION_PLACEHOLDER


def test_the_elevation_box_is_italic_only_while_it_is_empty(tab):
    """Qt cannot italicise placeholder text alone, so the widget is italic
    while empty — which renders exactly the placeholder in italic — and
    upright the moment a value is typed."""
    tab.mode_horizontal.setChecked(True)
    tab.elevation_edit.setText("")
    assert tab.elevation_edit.font().italic()

    tab.elevation_edit.setText("900.00")
    assert not tab.elevation_edit.font().italic()

    tab.elevation_edit.setText("")
    assert tab.elevation_edit.font().italic()


def test_the_paired_controls_share_their_rows(tab):
    """The owner's compaction, 2026-08-11: three rows saved.

    Asserted through the layout rather than by eye — each pair must be on ONE
    grid row, with each control still carrying its own label so nothing is
    inferred from position.
    """
    grid = tab.elevation_edit.parentWidget().layout()

    def row_of(widget):
        return grid.getItemPosition(grid.indexOf(widget))[0]

    assert row_of(tab.vertical_source_combo) == row_of(tab.vertical_target_combo)
    assert row_of(tab.input_geoid_combo) == row_of(tab.geoid_combo)
    assert row_of(tab.elevation_edit) == row_of(tab.height_kind_combo)

    # Distinct rows from each other, so the compaction did not collapse
    # everything into one line.
    rows = {
        row_of(tab.vertical_source_combo),
        row_of(tab.input_geoid_combo),
        row_of(tab.elevation_edit),
    }
    assert len(rows) == 3

    # Every control still has its own label on the same row.
    for label, control in (
        (tab.vertical_source_label, tab.vertical_source_combo),
        (tab.vertical_target_label, tab.vertical_target_combo),
        (tab.input_geoid_label, tab.input_geoid_combo),
        (tab.geoid_label, tab.geoid_combo),
        (tab.elevation_label, tab.elevation_edit),
        (tab.height_kind_label, tab.height_kind_combo),
    ):
        assert row_of(label) == row_of(control)


def test_the_geoid_grays_when_no_elevations_are_read(window):
    """The owner's instruction, 2026-08-11. With no elevations there is no
    height to look a separation up for, so the model changes nothing."""
    window.mode_horizontal.setChecked(True)
    assert window.elevation_in_file.isChecked()
    assert window.geoid_combo.isEnabled()

    window.elevation_in_file.setChecked(False)
    assert not window.geoid_combo.isEnabled()
    assert not window.geoid_combo.isHidden()

    window.elevation_in_file.setChecked(True)
    assert window.geoid_combo.isEnabled()


def test_the_geoid_stays_live_in_the_vertical_modes(window):
    """The graying is horizontal-only: in the vertical modes the geoid is what
    converts the heights, and its enablement belongs to the per-datum rule.

    This is the pin that caught the first version of the graying, which wrote
    ``setEnabled(vertical or elevations)`` and re-enabled a combo the datum
    filter had deliberately grayed.
    """
    window.mode_vertical.setChecked(True)
    window.elevation_in_file.setChecked(False)

    # NAVD 88 by data, not by index: index 1 is NGVD 29, which genuinely has
    # no published model and is grayed on purpose.
    for combo in (window.vertical_source_combo, window.vertical_target_combo):
        combo.setCurrentIndex(combo.findData(NAVD88))
    assert window.geoid_combo.isEnabled()


def test_every_geodetic_selection_names_the_datum(window, tab):
    """The owner's instruction, 2026-08-11: NAD 83 is not WGS 84.

    They differ by a metre or more in the conterminous United States, which is
    a boundary-moving amount, and a dropdown reading only "Geodetic" invites a
    handheld's WGS 84 position to be pasted in for a plausible wrong answer.
    Asserted on EVERY zone dropdown - both ends of both tabs - because the
    From selection and the To selection are equally able to be misread.

    **GENERALIZED at H6, not replaced.** #58's promise was that the label is
    DERIVED, so that "the day a job runs on NATRF2022 the dropdown renames
    itself rather than needing to be remembered". That day arrived, and the
    single entry became one per offered frame - so the pin now runs over EVERY
    offered frame and asserts the derivation for each. A hard-coded string for
    any one of them fails it, which is what #58 asked for; so does a second
    frame's entry that quietly reuses the first frame's label.
    """
    from michspc.gui.controls import (
        GEODETIC_CHOICES,
        frames_offered,
        geodetic_label,
    )

    # The offering is not empty and is not one thing pretending to be many.
    assert len(GEODETIC_CHOICES) == len(frames_offered()) >= 2
    labels = {choice.label for choice in GEODETIC_CHOICES}
    assert len(labels) == len(GEODETIC_CHOICES)

    for combo in (window.from_zone, window.to_zone, tab.from_zone, tab.to_zone):
        for choice in GEODETIC_CHOICES:
            at = combo.findData(choice)
            assert at != -1, f"no entry for {choice.frame.code}"
            # Derived from the frame record, not typed: the label follows the
            # mathematics by itself, which is the reason the owner gave.
            assert combo.itemText(at) == geodetic_label(choice.frame)
            assert combo.itemText(at) == (
                f"{choice.frame.code} geodetic (latitude / longitude)"
            )
            assert choice.frame.code in combo.itemText(at)

    # And the frame this program has always converted against is still one of
    # them, spelled with its realization.
    assert any(choice.frame is NAD83_2011 for choice in GEODETIC_CHOICES)
    assert geodetic_label(NAD83_2011).startswith("NAD83(2011)")
