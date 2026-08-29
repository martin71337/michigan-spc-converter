"""Per-side geoid selection reaches both tabs (the owner's feature,
2026-08-09), tested headless.

Three standing rules arrive at the new controls rather than any new idea:

**Graying, the owner's explicit word.** In the vertical modes each side's
geoid combo offers only the registry models published for that side's chosen
datum. A side whose datum is unanswered, or has no published model (NGVD 29
today), is DISABLED - grayed, visible - never hidden: the hidden idiom is
for controls that do not apply, and this one applies and is unanswerable.
Enabled-but-empty is pinned out too.

**Every control that can change the answer invalidates a displayed one**
(amendment #26, the one CRITICAL this GUI has ever had). The input-side
combo is a new way to reproduce that defect on the Single point tab, so it
has its own pin, falsified by disconnecting exactly its own connection.

**Two surfaces cannot disagree** (amendment #26 again). The swap conversion
is driven through both tabs on the Houghton anchor and compared bitwise; the
Multi point table's shift and sigma cells are compared against the audit CSV
inside the archive the same run wrote.

The number pinned absolutely is the Houghton fixture arithmetic of
tests/test_geoid_swap.py: N12B - N18 = -33.828 - (-33.796) = -0.032 m, so
200.000 m stated against GEOID12B reads 199.968 against GEOID18, within the
0.0015 m bound that file derives.
"""

from __future__ import annotations

import os

# MUST precede any Qt import (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import csv  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from michspc.fileio import exports, formatting as fmt, geoid  # noqa: E402
from michspc.gui import controls  # noqa: E402
from michspc.gui import single_point as single_point_module  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.controls import (  # noqa: E402
    GEOID_MODEL_LABEL,
    INPUT_GEOID_LABEL,
    OUTPUT_GEOID_LABEL,
    geoid_models_for_datum,
)
from michspc.gui.results_model import OUTPUT_TITLE  # noqa: E402
from michspc.gui.window import MainWindow  # noqa: E402
from michspc.job import VerticalMode, run  # noqa: E402
from michspc.spc.frames import NAD83_2011  # noqa: E402
from michspc.spc.units import METERS  # noqa: E402
from michspc.spc.vertical import NAVD88, NGVD29  # noqa: E402
from tests.test_geoid_swap import (  # noqa: E402
    FIXTURE_SWAP_SHIFT_M,
    HOUGHTON_LATITUDE,
    HOUGHTON_LONGITUDE,
    SWAP_TOLERANCE_M,
    _swap_settings,
    _swap_source,
)


@pytest.fixture(scope="module")
def qapp():
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


@pytest.fixture
def window(qapp):
    win = MainWindow()
    win.shown_failures = []
    win.overwrite_prompts = []
    win.overwrite_answer = False
    win._show_failure = lambda error: win.shown_failures.append(
        str(error) or repr(error)
    )
    win._ask_overwrite = lambda existing, error: win.overwrite_answer

    tab = win.single_point
    tab.shown_failures = []
    tab.copied = []
    tab._show_failure = lambda error: tab.shown_failures.append(
        str(error) or repr(error)
    )
    tab._set_clipboard = lambda text: tab.copied.append(text)

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


def offered(combo) -> list:
    return [combo.itemData(i) for i in range(combo.count())]


def fill_single_swap(tab) -> None:
    """The Houghton GEOID12B -> GEOID18 swap on the Single point tab:
    geodetic input, vertical-only mode, identity NAVD 88 pair, metres."""
    choose(tab.from_zone, NAD83_2011_GEODETIC)
    choose(tab.input_unit, METERS)
    choose(
        tab.longitude_combo,
        __import__("michspc.job", fromlist=["LongitudeConvention"])
        .LongitudeConvention.NEGATIVE_WEST,
    )
    tab.first_edit.setText(str(HOUGHTON_LATITUDE))
    tab.second_edit.setText(str(HOUGHTON_LONGITUDE))
    tab.elevation_edit.setText("200.000")
    tab.mode_vertical_only.setChecked(True)
    choose(tab.vertical_source_combo, NAVD88)
    choose(tab.vertical_target_combo, NAVD88)
    choose(tab.input_geoid_combo, geoid.GEOID12B_MODEL)

NAD83_2011_GEODETIC = controls.geodetic_choice(NAD83_2011)
"""The NAD83(2011) geodetic entry.

Since H6 the zone dropdowns carry one geodetic entry PER FRAME (DESIGN.md
#62, extending #58), so "geodetic" alone no longer names a selection. Every
case in this module is an SPCS 83 / NAD83(2011) case, which is the frame
that keeps them describing the same jobs they always did.
"""


# --------------------------------------------------------------------------
# The filter itself, asserted where it lives
# --------------------------------------------------------------------------


def test_the_registry_filter_answers_per_datum():
    """``geoid_models_for_datum`` owns the rule both tabs read: NAVD 88 has
    both shipped models, NGVD 29 has none, an unanswered datum has none -
    and a future datum's models appear the day their registry records do,
    with no interface change."""
    assert geoid_models_for_datum(NAVD88) == tuple(geoid.ALL_GEOID_MODELS)
    assert geoid_models_for_datum(NGVD29) == ()
    assert geoid_models_for_datum(None) == ()
    # Anti-vacuousness for everything below: the registry really does hold
    # NAVD 88 models only, today.
    assert all(
        model.vertical_datum.code == "NAVD88"
        for model in geoid.ALL_GEOID_MODELS
    )


# --------------------------------------------------------------------------
# Graying: the owner's word, on both tabs, both sides, flipping with datums
# --------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_side_with_no_models_grays_and_flips_with_the_datums(window, which):
    """NGVD 29's side is DISABLED with its items cleared - visible, gray,
    never hidden and never enabled-but-empty - and the graying follows the
    datums when they flip. Falsified by dropping the filter (populating the
    NGVD 29 side with the full list): the disabled assertions fail."""
    page = pages(window)[which]
    page.mode_vertical.setChecked(True)

    # Both datums unanswered: both sides gray - the question is stated and
    # unanswerable either way.
    assert page.input_geoid_combo.isEnabled() is False
    assert page.input_geoid_combo.count() == 0
    assert page.geoid_combo.isEnabled() is False
    assert page.geoid_combo.count() == 0
    # Visible, not hidden: the graying is the owner's distinction.
    assert page.input_geoid_combo.isHidden() is False
    assert page.geoid_combo.isHidden() is False

    choose(page.vertical_source_combo, NGVD29)
    choose(page.vertical_target_combo, NAVD88)
    # NGVD 29 side gray; NAVD 88 side enabled, offering exactly the NAVD 88
    # models, opening on GEOID18.
    assert page.input_geoid_combo.isEnabled() is False
    assert page.input_geoid_combo.count() == 0
    assert page.geoid_combo.isEnabled() is True
    assert offered(page.geoid_combo) == list(geoid_models_for_datum(NAVD88))
    assert page.geoid_combo.currentData() is geoid.GEOID18_MODEL

    # Flip the datums: the graying flips with them.
    choose(page.vertical_source_combo, NAVD88)
    choose(page.vertical_target_combo, NGVD29)
    assert page.input_geoid_combo.isEnabled() is True
    assert page.input_geoid_combo.currentData() is geoid.GEOID18_MODEL
    assert page.geoid_combo.isEnabled() is False
    assert page.geoid_combo.count() == 0


@pytest.mark.parametrize("which", ["single", "multi"])
def test_horizontal_mode_keeps_the_single_full_list_combo(window, which):
    """Horizontal is exactly today's surface: one combo, the full registry
    list under the standing label, the input-side row hidden (the question
    does not apply - the datum-row idiom), and the settings emit
    geoid_model from it with source None."""
    page = pages(window)[which]

    page.mode_horizontal.setChecked(True)
    assert page.geoid_label.text() == GEOID_MODEL_LABEL
    assert offered(page.geoid_combo) == list(geoid.ALL_GEOID_MODELS)
    assert page.geoid_combo.isEnabled() is True
    assert page.input_geoid_combo.isHidden() is True
    assert page.input_geoid_label.isHidden() is True

    assert page.output_geoid_model() is geoid.GEOID18_MODEL
    assert page.input_geoid_model() is None

    # And the vertical modes relabel the existing combo as the OUTPUT side
    # and reveal the input row.
    page.mode_vertical.setChecked(True)
    assert page.geoid_label.text() == OUTPUT_GEOID_LABEL
    assert page.input_geoid_combo.isHidden() is False
    assert page.input_geoid_label.text() == INPUT_GEOID_LABEL

    page.mode_horizontal.setChecked(True)
    assert page.geoid_label.text() == GEOID_MODEL_LABEL
    assert offered(page.geoid_combo) == list(geoid.ALL_GEOID_MODELS)
    assert page.input_geoid_combo.isHidden() is True


def test_a_selection_survives_a_refresh_that_keeps_it(tab):
    """The refresh preserves an answer its new list still holds: GEOID12B
    chosen in Horizontal survives a flip into a vertical mode whose target
    datum is ALREADY NAVD 88 (the filtered list holds both models), and
    survives the flip back to the full list. A refresh that passes through
    a GRAYED state clears the combo, and the re-enabled side then opens on
    GEOID18 - the stated default, not a preserved answer - which the last
    third of this test documents so the behaviour is a decision, not an
    accident."""
    # Answer the target datum first (it keeps its answer while hidden - the
    # datum-row idiom), so the later mode flips refresh straight between
    # populated lists with no grayed interlude.
    tab.mode_vertical.setChecked(True)
    choose(tab.vertical_target_combo, NAVD88)
    tab.mode_horizontal.setChecked(True)

    choose(tab.geoid_combo, geoid.GEOID12B_MODEL)
    tab.mode_vertical.setChecked(True)
    assert tab.geoid_combo.currentData() is geoid.GEOID12B_MODEL
    tab.mode_horizontal.setChecked(True)
    assert tab.geoid_combo.currentData() is geoid.GEOID12B_MODEL
    assert offered(tab.geoid_combo) == list(geoid.ALL_GEOID_MODELS)

    # Through a grayed interlude the answer is gone and the default is
    # GEOID18: gray means cleared, and a cleared side re-opens on the
    # model this program has shipped since 0.1.0.
    tab.mode_vertical.setChecked(True)
    choose(tab.geoid_combo, geoid.GEOID12B_MODEL)
    choose(tab.vertical_target_combo, NGVD29)
    assert tab.geoid_combo.isEnabled() is False
    choose(tab.vertical_target_combo, NAVD88)
    assert tab.geoid_combo.isEnabled() is True
    assert tab.geoid_combo.currentData() is geoid.GEOID18_MODEL


# --------------------------------------------------------------------------
# Settings emission: a grayed side states None, an answered side its record
# --------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_settings_carry_each_side_and_a_grayed_side_states_none(
    window, tmp_path, which
):
    page = pages(window)[which]
    if which == "multi":
        window.input_edit.setText(str(tmp_path / "pts.csv"))
        window.output_edit.setText(str(tmp_path / "out"))
    else:
        page.first_edit.setText(str(HOUGHTON_LATITUDE))
        page.second_edit.setText(str(HOUGHTON_LONGITUDE))
    choose(page.from_zone, NAD83_2011_GEODETIC)
    from michspc.spc.zones import MI_NORTH

    choose(page.to_zone, MI_NORTH)
    page.mode_vertical.setChecked(True)
    choose(page.vertical_source_combo, NAVD88)
    choose(page.vertical_target_combo, NAVD88)

    # Identity pair: both sides enabled, both defaulting to GEOID18 - so a
    # user who changes nothing gets exactly the pre-feature identity job.
    settings = page.settings()
    assert settings is not None
    assert settings.geoid_model is geoid.GEOID18_MODEL
    assert settings.source_geoid_model is geoid.GEOID18_MODEL

    # Choosing GEOID12B on the input side is the swap job.
    choose(page.input_geoid_combo, geoid.GEOID12B_MODEL)
    settings = page.settings()
    assert settings.source_geoid_model is geoid.GEOID12B_MODEL
    assert settings.geoid_model is geoid.GEOID18_MODEL

    # An NGVD 29 target grays the output side, which then states None -
    # geoid_model=None now REACHES jobs from the GUI (the normalization and
    # per-side factors make the outcomes identical to the #41-era shape;
    # test_gui_navd88_to_ngvd29_matches_the_41_era_shape holds that).
    choose(page.vertical_target_combo, NGVD29)
    settings = page.settings()
    assert settings is not None
    assert settings.geoid_model is None
    # The input side kept its own answer: only the target datum moved.
    assert settings.source_geoid_model is geoid.GEOID12B_MODEL
    # No new gating: the form is complete with a grayed side.
    assert page.convert_button.isEnabled() is True


def test_gui_navd88_to_ngvd29_matches_the_41_era_shape(tab):
    """The GUI's new NAVD88 -> NGVD29 emission (geoid_model=None,
    source_geoid_model=GEOID18) runs to the same outputs bitwise as the
    #41-era shape that carried GEOID18 in geoid_model - the equivalence the
    normalization promises, held through the tab's own settings object."""
    choose(tab.from_zone, NAD83_2011_GEODETIC)
    choose(tab.input_unit, METERS)
    from michspc.job import LongitudeConvention

    choose(tab.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    tab.first_edit.setText(str(HOUGHTON_LATITUDE))
    tab.second_edit.setText(str(HOUGHTON_LONGITUDE))
    tab.elevation_edit.setText("200.000")
    tab.mode_vertical_only.setChecked(True)
    choose(tab.vertical_source_combo, NAVD88)
    choose(tab.vertical_target_combo, NGVD29)

    settings = tab.settings()
    assert settings.geoid_model is None
    assert settings.source_geoid_model is geoid.GEOID18_MODEL

    gui_result = run(settings, source=_swap_source())
    legacy_result = run(
        _swap_settings(
            source_vertical_datum=NAVD88,
            target_vertical_datum=NGVD29,
            geoid_model=geoid.GEOID18_MODEL,
            source_geoid_model=None,
        ),
        source=_swap_source(),
    )
    gui_point, legacy_point = gui_result.points[0], legacy_result.points[0]
    assert gui_point.output_elevation == legacy_point.output_elevation
    assert gui_point.factors == legacy_point.factors
    assert gui_point.vertical.shift_m == legacy_point.vertical.shift_m
    assert gui_result.geoid_model == legacy_result.geoid_model == "GEOID18"


# --------------------------------------------------------------------------
# The swap end to end through the Single point tab
# --------------------------------------------------------------------------


def test_the_single_point_tab_converts_and_displays_the_swap(tab):
    fill_single_swap(tab)
    assert tab.convert() is True, tab.shown_failures

    point = tab.result.points[0]
    assert point.geoid_swap is not None
    assert point.geoid_swap.shift_m == pytest.approx(
        FIXTURE_SWAP_SHIFT_M, abs=SWAP_TOLERANCE_M
    )
    assert point.output_elevation == pytest.approx(
        200.0 + FIXTURE_SWAP_SHIFT_M, abs=SWAP_TOLERANCE_M
    )

    # The panel: the shift row names the MODELS, the sigma row reads N/A.
    labels = {
        value.label: value.text
        for section in tab.sections
        if section.title == OUTPUT_TITLE
        for value in section.values
    }
    assert labels["Geoid change GEOID12B -> GEOID18 (m)"] == (
        fmt.vertical_quantity(point.geoid_swap.shift_m, METERS)
    )
    assert labels[exports.vertical_sigma_heading(METERS)] == fmt.NOT_AVAILABLE


def test_the_two_tabs_cannot_disagree_about_a_swap(window, tab, tmp_path):
    """The same Houghton point through both tabs, floats bitwise - the same
    property the vertical feature is held to, at the swap."""
    from michspc.job import LongitudeConvention
    from michspc.fileio import pnezd

    job_file = tmp_path / "swap.csv"
    job_file.write_text(
        f"{pnezd.TYPED_POINT_ID},{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},"
        f"200.000\n",
        encoding="utf-8",
    )
    window.input_edit.setText(str(job_file))
    window.output_edit.setText(str(tmp_path / "out"))
    choose(window.from_zone, NAD83_2011_GEODETIC)
    choose(window.input_unit, METERS)
    choose(window.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    window.mode_vertical_only.setChecked(True)
    choose(window.vertical_source_combo, NAVD88)
    choose(window.vertical_target_combo, NAVD88)
    choose(window.input_geoid_combo, geoid.GEOID12B_MODEL)
    assert window.convert() is True, window.shown_failures

    fill_single_swap(tab)
    assert tab.convert() is True, tab.shown_failures

    from_file = window.result.points[0]
    typed = tab.result.points[0]
    assert typed.output_elevation == from_file.output_elevation
    assert typed.geoid_swap == from_file.geoid_swap
    assert typed.factors == from_file.factors


def test_the_multi_table_mirrors_the_audit_csv_for_a_swap(window, tmp_path):
    """Cell against cell, screen against the file the same run wrote - the
    #26 property at the swap's two cells: the shift cell carries the geoid
    change, the sigma cell N/A, both equal to the CSV's."""
    from michspc.job import LongitudeConvention
    from PySide6.QtCore import Qt

    job_file = tmp_path / "swap.csv"
    job_file.write_text(
        f"101,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},200.000,SWAP\n",
        encoding="utf-8",
    )
    window.input_edit.setText(str(job_file))
    window.output_edit.setText(str(tmp_path / "out"))
    choose(window.from_zone, NAD83_2011_GEODETIC)
    choose(window.input_unit, METERS)
    choose(window.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    window.mode_vertical_only.setChecked(True)
    choose(window.vertical_source_combo, NAVD88)
    choose(window.vertical_target_combo, NAVD88)
    choose(window.input_geoid_combo, geoid.GEOID12B_MODEL)
    assert window.convert() is True, window.shown_failures

    from tests.conftest import member_text

    audit_name = exports.member_names(window.result)["audit"]
    text = member_text(window.written_files["archive"], "_full.csv")
    assert audit_name.endswith("_full.csv")
    rows = list(csv.reader(text.splitlines()))
    audit = dict(zip(rows[0], rows[1]))

    headings = [
        window.model.headerData(i, Qt.Orientation.Horizontal)
        for i in range(window.model.columnCount())
    ]
    shift_at = headings.index(exports.vertical_shift_heading(METERS))
    sigma_at = headings.index(exports.vertical_sigma_heading(METERS))

    def cell(row, column):
        return window.model.index(row, column).data(Qt.ItemDataRole.DisplayRole)

    assert cell(0, shift_at) == audit["Vertical shift (m)"]
    assert cell(0, sigma_at) == audit["Shift sigma (m)"]
    assert cell(0, shift_at) == "-0.0323"
    assert cell(0, sigma_at) == fmt.NOT_AVAILABLE
    # And the CSV names both models.
    assert audit["Source geoid model"] == "GEOID12B"
    assert audit["Geoid model"] == "GEOID18"


# --------------------------------------------------------------------------
# Invalidation: the amendment #26 CRITICAL class at the new combo
# --------------------------------------------------------------------------


def test_changing_the_input_geoid_discards_a_displayed_result(tab):
    """A GEOID18-both-sides result under controls now reading GEOID12B ->
    GEOID18 is a stale identity one click from the clipboard: the swap the
    controls describe moves the elevation by ~0.032 m at Houghton and the
    displayed one did not. Falsified by disconnecting exactly the input
    combo's currentIndexChanged connection: this test alone fails."""
    fill_single_swap(tab)
    # Start from the identity: both sides GEOID18.
    choose(tab.input_geoid_combo, geoid.GEOID18_MODEL)
    assert tab.convert() is True, tab.shown_failures
    assert tab.result is not None
    assert tab.sections is not None
    assert tab.copy_all_button.isEnabled() is True

    choose(tab.input_geoid_combo, geoid.GEOID12B_MODEL)

    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False
    assert tab.copy_value(0) is False
    assert tab.copy_all() is False
    assert (
        tab.status_label.text() == single_point_module.STATUS_INPUT_CHANGED
    )
