"""WP-V8: vertical mode reaches the interface, tested headless.

Three properties dominate this file, and every one of them is a standing rule
arriving at three new controls rather than a new idea:

**No silent defaults** (docs/DESIGN.md section 7). The mode toggle opens on
Horizontal - today's job, asserting nothing about a vertical datum - and both
datum dropdowns open unanswered, because NGVD 29 and NAVD 88 heights differ by
up to 0.41 m across Michigan while looking identical. Amendment #29's
positive-west preselect is a narrow recorded exception; these controls are not
it (docs/PLAN-vertical-datums.md section 4.2).

**Every control that can change the answer invalidates a displayed one**
(docs/DESIGN.md amendment #26, the one CRITICAL this GUI has ever had). The
toggle, both datum dropdowns and the geoid dropdown are four new ways to
reproduce that defect on the Single point tab, so each has its own pin here,
and each pin was falsified by disconnecting exactly its own connection.

**Two surfaces cannot disagree** (amendment #26 again). The Multi point
table's new vertical columns are compared cell against cell with the audit CSV
inside the archive the same run wrote, and the two tabs are driven through the
same vertical configuration with the floats compared bitwise.

Expected values are the frozen NCAT anchors of
``tests/fixtures/vertcon_anchors.py`` where a number is asserted absolutely:
at 43.0 N, 84.5 W the VERTCON 3.0 grid shifts an NGVD 29 height by about
-0.140 m (NCAT prints 200.000 -> 199.860; plan section 2.3), within the
0.0005 m bound tests/test_job_vertical.py derives.
"""

from __future__ import annotations

import os

# MUST precede any Qt import: the platform plugin is chosen at import time and a
# later change is ignored, leaving the run needing a display it does not have
# (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import csv  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

from michspc.fileio import exports, formatting as fmt, geoid, pnezd  # noqa: E402
from michspc.fileio.exports import (  # noqa: E402
    vertical_shift_heading,
    vertical_sigma_heading,
)
from michspc.gui import controls, results_model  # noqa: E402
from michspc.gui import single_point as single_point_module  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.results_model import (  # noqa: E402
    COLUMNS,
    INPUT_TITLE,
    OUTPUT_TITLE,
    columns_for,
)
from michspc.gui.window import UNCHOSEN, MainWindow  # noqa: E402
from michspc.job import (  # noqa: E402
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS  # noqa: E402
from michspc.spc.vertical import (  # noqa: E402
    ALL_VERTICAL_DATUMS,
    NAPGD2022,
    NAVD88,
    NGVD29,
)
from michspc.spc.zones import MI_CENTRAL, MI_SOUTH  # noqa: E402
from tests.fixtures.vertcon_anchors import NGVD29_TO_NAVD88_ANCHORS  # noqa: E402

# The frozen anchor the vertical conversions below sit on: 43.0 N, 84.5 W,
# where NCAT converts 200.000 m NGVD 29 to 199.860 m NAVD 88 (plan section
# 2.3; DESIGN.md #22). The shift is a difference of two figures NCAT prints to
# 0.001 m, and the reader's measured worst residual is 0.4716 mm, so 0.0005 m
# is the derived bound (tests/test_job_vertical.py's own derivation).
ANCHOR_22 = next(a for a in NGVD29_TO_NAVD88_ANCHORS if a.name == "anchor-22")
SHIFT_TOLERANCE_M = 0.0005

USABLE_DATUMS = tuple(d for d in ALL_VERTICAL_DATUMS if d.is_usable)

# Every vertical job in this module runs metres to metres, so the table's
# shift and sigma headings - the audit CSV's own, via the shared functions,
# in the job's INPUT unit (the owner's units instruction, 2026-08-09) - are
# the metre spellings throughout. Derived, not retyped, so the table-vs-CSV
# correspondence below holds BECAUSE the wording is shared.
VERTICAL_SHIFT_COLUMN_HEADING = vertical_shift_heading(METERS)
VERTICAL_SIGMA_LABEL = vertical_sigma_heading(METERS)


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
    """A window whose modal dialogs - on both tabs - are replaced by recorders."""
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

    tab = win.single_point
    tab.shown_failures = []
    tab.copied = []

    def record_tab_failure(error):
        tab.shown_failures.append(str(error) or repr(error))

    def record_clipboard(text):
        tab.copied.append(text)

    tab._show_failure = record_tab_failure
    tab._set_clipboard = record_clipboard

    yield win
    win.close()


@pytest.fixture
def tab(window):
    """The Single point tab of that window."""
    return window.single_point


def pages(window):
    """Both tabs, keyed for parametrised tests that must cover each."""
    return {"single": window.single_point, "multi": window}


def choose(combo, data) -> None:
    """Select an entry by its data, failing loudly if it is not offered."""
    index = combo.findData(data)
    if index < 0:
        raise AssertionError(f"{combo!r} has no entry for {data!r}")
    combo.setCurrentIndex(index)


def make_vertical(page, source_datum=NGVD29, target_datum=NAVD88) -> None:
    """Turn vertical mode on and answer both datum dropdowns."""
    page.mode_vertical.setChecked(True)
    choose(page.vertical_source_combo, source_datum)
    choose(page.vertical_target_combo, target_datum)


def fill_single_vertical(tab) -> None:
    """A geodetic NGVD 29 -> NAVD 88 job on the anchor, metres both ends."""
    choose(tab.from_zone, controls.GEODETIC)
    choose(tab.to_zone, MI_SOUTH)
    choose(tab.input_unit, METERS)
    choose(tab.output_unit, METERS)
    choose(tab.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    tab.first_edit.setText(str(ANCHOR_22.latitude))
    tab.second_edit.setText(str(ANCHOR_22.longitude))
    tab.elevation_edit.setText("200.000")
    make_vertical(tab)


def fill_multi_vertical(window, *, input_path, output_directory) -> None:
    """The same job on the Multi point tab, plus the file and the folder."""
    window.input_edit.setText(str(input_path))
    window.output_edit.setText(str(output_directory))
    choose(window.from_zone, controls.GEODETIC)
    choose(window.to_zone, MI_SOUTH)
    choose(window.input_unit, METERS)
    choose(window.output_unit, METERS)
    choose(window.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
    make_vertical(window)


def value_of(sections, title, label) -> str:
    """The displayed text of one labelled value in one named section."""
    for section in sections:
        if section.title != title:
            continue
        for value in section.values:
            if value.label == label:
                return value.text
    raise AssertionError(f"no {label!r} value in the {title} section")


def cell(window, row, column) -> str:
    return window.model.index(row, column).data(Qt.ItemDataRole.DisplayRole)


def headings(window) -> list[str]:
    return [
        window.model.headerData(i, Qt.Orientation.Horizontal)
        for i in range(window.model.columnCount())
    ]


# --------------------------------------------------------------------------
# The toggle: both tabs, opens on Horizontal, shared with nobody
# --------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_mode_toggle_opens_on_horizontal(window, which):
    """Two radio buttons, Horizontal checked, on each tab (plan section 4.1).

    Horizontal is today's behaviour and asserts nothing about a vertical
    datum, so it is a starting state rather than an answer - the datum
    question itself still opens unanswered below.
    """
    page = pages(window)[which]
    assert page.mode_horizontal.isChecked() is True
    assert page.mode_vertical.isChecked() is False
    assert page.vertical_mode() is VerticalMode.HORIZONTAL

    # The captions are the module's constants, not strings retyped here.
    assert page.mode_horizontal.text() == controls.HORIZONTAL_MODE_TEXT
    assert page.mode_vertical.text() == controls.VERTICAL_MODE_TEXT
    assert controls.HORIZONTAL_MODE_TEXT == "Horizontal"
    assert controls.VERTICAL_MODE_TEXT == "Horizontal + Vertical"


def test_the_two_tabs_share_no_vertical_control(window, tab):
    """Per-tab controls, never window state (amendment #26).

    A window-level toggle would let a choice made for one tab silently change
    what the other converts - the exact state the two-tab split exists to
    forbid, which is why plan section 4.1 says "not above the tab bar".
    """
    assert tab.mode_horizontal is not window.mode_horizontal
    assert tab.mode_vertical is not window.mode_vertical
    assert tab.vertical_source_combo is not window.vertical_source_combo
    assert tab.vertical_target_combo is not window.vertical_target_combo
    assert tab.geoid_combo is not window.geoid_combo

    # And they really are independent: answering one tab leaves the other
    # exactly as it was.
    tab.mode_vertical.setChecked(True)
    assert tab.vertical_mode() is VerticalMode.HORIZONTAL_AND_VERTICAL
    assert window.vertical_mode() is VerticalMode.HORIZONTAL
    assert window.mode_horizontal.isChecked() is True


# --------------------------------------------------------------------------
# What expands: hidden, not disabled (plan section 4.2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_datum_rows_are_hidden_until_vertical_and_hide_again(window, which):
    """Selecting Horizontal + Vertical reveals the two rows; Horizontal hides
    them. Hidden, NOT disabled: a disabled control that never becomes relevant
    in this mode is clutter, where the longitude selector is disabled because
    it becomes relevant again (plan section 4.2). ``isHidden`` is the right
    probe on an unshown window - it reports the explicit hide, where
    ``isVisible`` is False for every widget of an unshown window and would
    make the assertion vacuous.
    """
    page = pages(window)[which]
    rows = (
        page.vertical_source_label,
        page.vertical_source_combo,
        page.vertical_target_label,
        page.vertical_target_combo,
    )

    for widget in rows:
        assert widget.isHidden() is True, "the row must start hidden"
        assert widget.isEnabled() is True, "hidden, not disabled"

    page.mode_vertical.setChecked(True)
    for widget in rows:
        assert widget.isHidden() is False, "vertical mode must reveal the row"

    page.mode_horizontal.setChecked(True)
    for widget in rows:
        assert widget.isHidden() is True, "horizontal mode must hide it again"


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_geoid_dropdown_is_visible_in_both_modes(window, which):
    """The geoid governs the elevation and combined factors whether or not the
    elevations are converted between datums, so it never hides (plan 4.3)."""
    page = pages(window)[which]
    assert page.geoid_combo.isHidden() is False
    page.mode_vertical.setChecked(True)
    assert page.geoid_combo.isHidden() is False
    page.mode_horizontal.setChecked(True)
    assert page.geoid_combo.isHidden() is False


# --------------------------------------------------------------------------
# The dropdowns are built from the registries
# --------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_datum_dropdowns_open_unanswered_and_offer_the_usable_registry(
    window, which
):
    """Both datum dropdowns: a placeholder, then every USABLE datum, nothing
    else, and no preselection.

    Derived from the registry, not from a list here: the entries are exactly
    ``[d for d in ALL_VERTICAL_DATUMS if d.is_usable]``, in declaration
    order, so a datum whose status changes in ``spc.vertical`` appears or
    disappears with no interface change. NAPGD2022 is declared-not-usable
    and must not appear: no transformation product to or from it exists, so
    any height offered in it would be invented rather than converted.
    """
    page = pages(window)[which]

    # Anti-vacuousness for the exclusion below: the registry really does
    # declare NAPGD2022, and really does declare it not usable.
    assert NAPGD2022 in ALL_VERTICAL_DATUMS
    assert NAPGD2022.is_usable is False
    assert len(USABLE_DATUMS) >= 2

    for combo in (page.vertical_source_combo, page.vertical_target_combo):
        # Opens unanswered (docs/DESIGN.md section 7): the entries are
        # indistinguishable from the numbers on screen, so a preselected one
        # would answer a question the user was never asked.
        assert combo.currentData() == UNCHOSEN
        assert page.vertical_mode() is not None  # the mode, by contrast, is stated

        offered = [combo.itemData(i) for i in range(combo.count())]
        assert offered == [UNCHOSEN, *USABLE_DATUMS]
        assert combo.findData(NAPGD2022) == -1, "NAPGD2022 must not be offered"

        # The entry text is the record's own name and code, never typed out.
        for datum in USABLE_DATUMS:
            assert combo.itemText(combo.findData(datum)) == str(datum)

    # Identity pairs are legitimate - NAVD88 -> NAVD88 states the datum - so
    # both ends offer BOTH usable datums rather than disjoint halves.
    assert page.vertical_source_combo.findData(NAVD88) >= 0
    assert page.vertical_target_combo.findData(NAVD88) >= 0
    assert page.vertical_source_combo.findData(NGVD29) >= 0
    assert page.vertical_target_combo.findData(NGVD29) >= 0


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_geoid_dropdown_lists_the_registry_in_order_and_opens_on_geoid18(
    window, which
):
    """Exactly ``geoid.ALL_GEOID_MODELS``, in declaration order, opening on
    GEOID18, with NO "none" entry (plan section 4.3, the owner's decisions).

    Built from the registry so a model added there appears with no interface
    change - the property the zone dropdown already has. "No none" is why
    every entry must be a real model record: ``geoid_model=None`` remains a
    capability of the core that no interface offers (plan section 5).
    """
    page = pages(window)[which]
    combo = page.geoid_combo

    offered = [combo.itemData(i) for i in range(combo.count())]
    assert offered == list(geoid.ALL_GEOID_MODELS)
    assert combo.currentData() is geoid.GEOID18_MODEL

    texts = [combo.itemText(i) for i in range(combo.count())]
    assert texts == [model.name for model in geoid.ALL_GEOID_MODELS]

    # No "none", and nothing that is not a registry record.
    for entry in offered:
        assert isinstance(entry, geoid.GeoidModel)


# --------------------------------------------------------------------------
# Convert gating and settings assembly (plan section 4.4)
# --------------------------------------------------------------------------


def test_convert_gates_on_both_datums_on_the_single_point_tab(tab):
    """Vertical mode on with either datum unanswered is not a job yet.

    The existing ``settings() is None`` idiom, extended: nothing new decides
    enablement, so the gate and the button cannot disagree.
    """
    choose(tab.from_zone, MI_CENTRAL)
    choose(tab.to_zone, MI_SOUTH)
    tab.first_edit.setText("176200.000")
    tab.second_edit.setText("19685000.000")
    assert tab.convert_button.isEnabled() is True, "the horizontal form is complete"

    tab.mode_vertical.setChecked(True)
    assert tab.settings() is None
    assert tab.convert_button.isEnabled() is False

    choose(tab.vertical_source_combo, NGVD29)
    assert tab.settings() is None, "one datum is not both"
    assert tab.convert_button.isEnabled() is False

    choose(tab.vertical_target_combo, NAVD88)
    assert tab.settings() is not None
    assert tab.convert_button.isEnabled() is True

    # Back to horizontal: the answered dropdowns are hidden and NOT read -
    # settings states None for both, which is what job.run requires of a
    # horizontal job.
    tab.mode_horizontal.setChecked(True)
    settings = tab.settings()
    assert settings is not None
    assert tab.convert_button.isEnabled() is True
    assert settings.vertical_mode is VerticalMode.HORIZONTAL
    assert settings.source_vertical_datum is None
    assert settings.target_vertical_datum is None


def test_convert_gates_on_both_datums_on_the_multi_point_tab(window, tmp_path):
    """The same gate on the file tab, through its own settings()."""
    window.input_edit.setText(str(tmp_path / "pts.csv"))
    window.output_edit.setText(str(tmp_path / "out"))
    choose(window.from_zone, MI_CENTRAL)
    choose(window.to_zone, MI_SOUTH)
    assert window.convert_button.isEnabled() is True

    window.mode_vertical.setChecked(True)
    assert window.settings() is None
    assert window.convert_button.isEnabled() is False

    choose(window.vertical_source_combo, NAVD88)
    assert window.convert_button.isEnabled() is False

    choose(window.vertical_target_combo, NGVD29)
    assert window.settings() is not None
    assert window.convert_button.isEnabled() is True


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_settings_carry_the_vertical_answers(window, tmp_path, which):
    """What the dropdowns say is what the job gets - the registry's own
    records, by identity, and the geoid model from the dropdown."""
    page = pages(window)[which]
    if which == "multi":
        window.input_edit.setText(str(tmp_path / "pts.csv"))
        window.output_edit.setText(str(tmp_path / "out"))
    else:
        page.first_edit.setText("176200.000")
        page.second_edit.setText("19685000.000")
    choose(page.from_zone, MI_CENTRAL)
    choose(page.to_zone, MI_SOUTH)

    # Horizontal first: mode stated, datums None, geoid from the dropdown.
    settings = page.settings()
    assert isinstance(settings, JobSettings)
    assert settings.vertical_mode is VerticalMode.HORIZONTAL
    assert settings.source_vertical_datum is None
    assert settings.target_vertical_datum is None
    assert settings.geoid_model is geoid.GEOID18_MODEL

    # The dropdown is live: GEOID12B chosen is GEOID12B in the settings.
    choose(page.geoid_combo, geoid.GEOID12B_MODEL)
    assert page.settings().geoid_model is geoid.GEOID12B_MODEL

    # And vertical: the records themselves, not copies.
    make_vertical(page, NAVD88, NGVD29)
    settings = page.settings()
    assert settings.vertical_mode is VerticalMode.HORIZONTAL_AND_VERTICAL
    assert settings.source_vertical_datum is NAVD88
    assert settings.target_vertical_datum is NGVD29


def test_a_refused_pair_reaches_the_screen_as_the_jobs_own_sentence(tab):
    """The GUI never pre-empts a refusal it can simply surface.

    NGVD29 -> NGVD29 with a geoid model is a complete form - Convert is
    enabled - and job.run refuses it (both endpoints differ from the model's
    datum, DESIGN.md #41). The dropdowns do not grey the pair out: the
    refusal names the problem and the achievable alternative, which a
    disabled entry never could. The expected text is obtained by running the
    same settings through the authority itself.
    """
    choose(tab.from_zone, MI_CENTRAL)
    choose(tab.to_zone, MI_SOUTH)
    tab.first_edit.setText("176200.000")
    tab.second_edit.setText("19685000.000")
    tab.elevation_edit.setText("812.40")
    make_vertical(tab, NGVD29, NGVD29)

    settings = tab.settings()
    assert settings is not None
    assert tab.convert_button.isEnabled() is True, (
        "a complete form is enabled; convertibility is job.run's question"
    )

    parsed = pnezd.parse_typed_point(
        "176200.000",
        "19685000.000",
        "812.40",
        source=pnezd.TYPED_POINT_SOURCE_GRID,
    )
    with pytest.raises(Exception) as raised:
        run(settings, source=parsed)
    expected = str(raised.value)
    assert expected, "the refusal must say something"

    assert tab.convert() is False
    assert tab.shown_failures == [expected]
    assert str(tab.last_failure) == expected


# --------------------------------------------------------------------------
# Invalidation: the amendment #26 CRITICAL class, one pin per new control
# --------------------------------------------------------------------------
#
# Each of the four tests below was falsified by disconnecting exactly the
# connection it pins (the toggle's handler, each datum combo's handler, the
# geoid combo's connect) and watching the stale result survive with both copy
# paths armed - then restoring the connection.


def converted_horizontal(tab):
    """A displayed horizontal result to go stale."""
    choose(tab.from_zone, MI_CENTRAL)
    choose(tab.to_zone, MI_SOUTH)
    tab.first_edit.setText("176200.000")
    tab.second_edit.setText("19685000.000")
    tab.elevation_edit.setText("812.40")
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")
    assert tab.result is not None
    assert tab.sections is not None
    assert tab.copy_all_button.isEnabled() is True


def assert_discarded(tab):
    """Nothing left on screen, nothing left to copy, and the status says why."""
    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False
    assert tab.copy_value(0) is False, "the per-value copy path is disarmed too"
    assert tab.copy_all() is False
    assert tab.status_label.text() == single_point_module.STATUS_INPUT_CHANGED


def test_toggling_the_mode_discards_a_displayed_result(tab):
    """The same numbers under a different mode describe a different job: a
    horizontal result left on screen after switching to Horizontal + Vertical
    would show an unshifted elevation under a caption one Convert away from
    claiming a datum (amendment #26's failure mode by the newest door)."""
    converted_horizontal(tab)
    tab.mode_vertical.setChecked(True)
    assert_discarded(tab)

    # And the way back is a change too: convert a vertical job, then toggle
    # to Horizontal, and its shifted elevation must not survive either.
    make_vertical(tab)
    tab.elevation_edit.setText("812.40")
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")
    assert tab.result is not None
    tab.mode_horizontal.setChecked(True)
    assert_discarded(tab)


def test_changing_the_source_datum_discards_a_displayed_result(tab):
    """An NGVD 29 -> NAVD 88 result under controls now reading NAVD 88 ->
    NAVD 88 is a stale shift one click from the clipboard."""
    converted_horizontal(tab)
    make_vertical(tab, NGVD29, NAVD88)
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")
    assert tab.result is not None

    choose(tab.vertical_source_combo, NAVD88)
    assert_discarded(tab)


def test_changing_the_target_datum_discards_a_displayed_result(tab):
    converted_horizontal(tab)
    make_vertical(tab, NGVD29, NAVD88)
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")
    assert tab.result is not None

    choose(tab.vertical_target_combo, NGVD29)
    assert_discarded(tab)


def test_changing_the_geoid_model_discards_a_displayed_result(tab):
    """The two shipped models differ by up to 32 mm at one Michigan anchor
    (DESIGN.md #40), so a GEOID18 factor under a dropdown now reading
    GEOID12B is a wrong number wearing a right label."""
    converted_horizontal(tab)
    choose(tab.geoid_combo, geoid.GEOID12B_MODEL)
    assert_discarded(tab)


# --------------------------------------------------------------------------
# The identity pair is a real job that states its datum
# --------------------------------------------------------------------------


def test_an_identity_pair_converts_and_states_the_datum(tab):
    """NAVD 88 -> NAVD 88 is legitimate: no shift, a stated datum, and the
    elevation labels carry it on both sides. The shift is a real zero -
    printed as one, never as N/A - and the sigma is N/A, never a number,
    because no model ran (DESIGN.md #36).

    This job runs in the tab's default unit - International feet - so it is
    also the identity-in-feet pin: the labels say ift and the zero shift
    renders "0.000" at the foot unit's 3 places, never the metre "0.0000"
    (before the units instruction the label here claimed "(m)" over a
    feet job, which is exactly the mislabelling the change removes)."""
    converted_horizontal(tab)
    make_vertical(tab, NAVD88, NAVD88)
    if tab.convert() is not True:
        raise AssertionError(f"the run failed: {tab.shown_failures}")

    assert tab.result.settings.input_unit is INTERNATIONAL_FEET
    assert value_of(tab.sections, INPUT_TITLE, "Elevation (NAVD88, ift)")
    assert value_of(tab.sections, OUTPUT_TITLE, "Elevation (NAVD88, ift)")
    shift = value_of(
        tab.sections, OUTPUT_TITLE, "Vertical shift NAVD88 -> NAVD88 (ift)"
    )
    assert shift == fmt.vertical_quantity(0.0, INTERNATIONAL_FEET)
    assert shift == "0.000"
    assert (
        value_of(tab.sections, OUTPUT_TITLE, vertical_sigma_heading(INTERNATIONAL_FEET))
        == fmt.NOT_AVAILABLE
    )


# --------------------------------------------------------------------------
# The two tabs cannot disagree about a vertical point (amendment #26)
# --------------------------------------------------------------------------


def test_the_two_tabs_cannot_disagree_about_a_vertical_point(window, tab, tmp_path):
    """The same typed point, the same datums, the same geoid model, through
    both tabs: floats bitwise, warnings byte for byte, and the shifted
    elevation on screen against the multi-point table's own cell.

    Bitwise because it is the same function object applied to the same parsed
    row; anything else means the two tabs took different paths, which is the
    one thing this feature may not do.
    """
    job_file = tmp_path / "one-point.csv"
    job_file.write_text(
        f"{pnezd.TYPED_POINT_ID},{ANCHOR_22.latitude},{ANCHOR_22.longitude},"
        f"200.000\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    fill_multi_vertical(window, input_path=job_file, output_directory=out_dir)
    if window.convert() is not True:
        raise AssertionError(f"the multi-point run failed: {window.shown_failures}")

    fill_single_vertical(tab)
    if tab.convert() is not True:
        raise AssertionError(f"the single-point run failed: {tab.shown_failures}")

    from_file = window.result.points[0]
    typed = tab.result.points[0]

    # The numbers, bitwise - including the vertical reading itself.
    assert typed.output_northing == from_file.output_northing
    assert typed.output_easting == from_file.output_easting
    assert typed.output_elevation == from_file.output_elevation
    assert typed.vertical is not None
    assert from_file.vertical is not None
    assert typed.vertical.shift_m == from_file.vertical.shift_m
    assert typed.vertical.sigma_m == from_file.vertical.sigma_m
    assert typed.factors.combined_factor == from_file.factors.combined_factor

    # The shift really is the anchor's, so the comparison above is not two
    # matching zeroes: NCAT prints 200.000 -> 199.860 here (plan section 2.3).
    expected_shift = ANCHOR_22.target_height_m - ANCHOR_22.source_height_m
    assert abs(typed.vertical.shift_m - expected_shift) < SHIFT_TOLERANCE_M

    # The warnings, byte for byte.
    assert [w.message for w in typed.warnings] == [
        w.message for w in from_file.warnings
    ]
    assert [w.code for w in typed.warnings] == [w.code for w in from_file.warnings]

    # And the strings on the two screens. The table's vertical columns sit
    # directly after its Elevation column (columns_for), and the panel's
    # rows carry the same formatter output.
    table_columns = headings(window)
    elevation_column = table_columns.index("Elevation (NAVD88, m)")
    shift_column = table_columns.index(VERTICAL_SHIFT_COLUMN_HEADING)
    sigma_column = table_columns.index(VERTICAL_SIGMA_LABEL)

    assert value_of(tab.sections, OUTPUT_TITLE, "Elevation (NAVD88, m)") == cell(
        window, 0, elevation_column
    )
    assert value_of(
        tab.sections, OUTPUT_TITLE, "Vertical shift NGVD29 -> NAVD88 (m)"
    ) == cell(window, 0, shift_column)
    assert value_of(tab.sections, OUTPUT_TITLE, VERTICAL_SIGMA_LABEL) == cell(
        window, 0, sigma_column
    )


# --------------------------------------------------------------------------
# The Multi point table on a vertical job (WP-V7 review gate finding 4)
# --------------------------------------------------------------------------


def vertical_multi_job(window, tmp_path, source_datum=NGVD29, target_datum=NAVD88):
    """Three rows: the anchor, a blank-Z row, and the max-sigma point."""
    job_file = tmp_path / "three-point.csv"
    job_file.write_text(
        f"101,{ANCHOR_22.latitude},{ANCHOR_22.longitude},200.000,ANCHOR\n"
        f"102,43.1,-84.6,,NO ELEVATION\n"
        f"103,43.05,-86.20,200.000,MAX SIGMA\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    fill_multi_vertical(window, input_path=job_file, output_directory=out_dir)
    make_vertical(window, source_datum, target_datum)
    if window.convert() is not True:
        raise AssertionError(f"the multi-point run failed: {window.shown_failures}")


def test_a_vertical_jobs_table_names_the_datum_and_carries_shift_and_sigma(
    window, tmp_path
):
    """The header: Elevation gains the TARGET datum, and the shift and sigma
    columns sit directly after it - the audit CSV's own order and its own
    wordings, per the #17 standing choice of one wording on every surface.
    """
    vertical_multi_job(window, tmp_path)

    table_columns = headings(window)
    at = table_columns.index("Elevation (NAVD88, m)")
    assert table_columns[at + 1] == VERTICAL_SHIFT_COLUMN_HEADING
    assert table_columns[at + 2] == VERTICAL_SIGMA_LABEL
    # Pinned in both units: the heading carries the job's input unit code
    # (owner's units instruction, 2026-08-09) - this job's is metres, and the
    # feet spellings are pinned here too so the wording cannot quietly become
    # unit-blind again.
    assert VERTICAL_SHIFT_COLUMN_HEADING == "Vertical shift (m)"
    assert VERTICAL_SIGMA_LABEL == "Shift sigma (m)"
    assert vertical_shift_heading(INTERNATIONAL_FEET) == "Vertical shift (ift)"
    assert vertical_sigma_heading(INTERNATIONAL_FEET) == "Shift sigma (ift)"
    assert "Elevation" not in table_columns, (
        "the bare heading must not survive on a vertical job"
    )

    # A row with no elevation has no reading, so neither number exists and
    # both cells read N/A - never 0.0, which would claim a shift was applied.
    assert cell(window, 1, at) == fmt.NOT_AVAILABLE
    assert cell(window, 1, at + 1) == fmt.NOT_AVAILABLE
    assert cell(window, 1, at + 2) == fmt.NOT_AVAILABLE

    # The anchor row's cells are the formatter's rendering of the reading the
    # job actually applied - the same objects, not a re-computation.
    reading = window.result.points[0].vertical
    assert cell(window, 0, at + 1) == fmt.vertical_quantity(
        reading.shift_m, METERS
    )
    assert cell(window, 0, at + 2) == fmt.vertical_quantity(
        reading.sigma_m, METERS
    )
    assert abs(
        reading.shift_m - (ANCHOR_22.target_height_m - ANCHOR_22.source_height_m)
    ) < SHIFT_TOLERANCE_M


@pytest.mark.parametrize(
    "source_datum, target_datum",
    [(NGVD29, NAVD88), (NAVD88, NGVD29)],
    ids=["ngvd29_to_navd88", "navd88_to_ngvd29"],
)
def test_the_vertical_table_and_the_audit_csv_cannot_disagree(
    window, tmp_path, read_member, source_datum, target_datum
):
    """The pin the WP-V7 gate asked WP-V8 to build: cell against cell, the
    on-screen table against the audit CSV inside the archive the same run
    wrote. Screen against file, not screen against screen - a table cell fed
    from anywhere but the reading would break here, because the CSV's cells
    come from the reading.

    Both directions, deliberately: the transformation's sign is +1 one way
    and -1 the other, so the raw grid value and the applied shift are the
    SAME number for NGVD29 -> NAVD88 and negatives of each other for
    NAVD88 -> NGVD29. A shift cell quietly fed from the grid value instead
    of the reading would pass the forward case and fail only here - which is
    exactly the discrimination this parametrisation exists to buy.
    """
    vertical_multi_job(window, tmp_path, source_datum, target_datum)

    audit_name = exports.member_names(window.result)["audit"]
    text = read_member(window.written_files["archive"], audit_name)
    rows = list(csv.reader(text.splitlines()))
    header = rows[0]

    # Which table column corresponds to which audit column. The two surfaces
    # deliberately share the shift and sigma wordings; the table's Elevation
    # heading carries the datum where the audit says it in its own datum
    # columns, and the values beneath the two must be identical.
    table_columns = headings(window)
    correspondence = {
        "Point": "Point",
        "Northing": "Target northing",
        "Easting": "Target easting",
        f"Elevation ({target_datum.code}, m)": "Elevation",
        VERTICAL_SHIFT_COLUMN_HEADING: VERTICAL_SHIFT_COLUMN_HEADING,
        VERTICAL_SIGMA_LABEL: VERTICAL_SIGMA_LABEL,
        "Grid scale factor": "Grid scale factor",
        "Combined factor": "Combined factor",
    }

    compared = 0
    for row_index in range(window.model.rowCount()):
        audit = dict(zip(header, rows[1 + row_index]))
        for table_heading, audit_heading in correspondence.items():
            assert table_heading in table_columns, (
                f"the table has no {table_heading!r} column"
            )
            assert audit_heading in audit, (
                f"the audit CSV has no {audit_heading!r} column"
            )
            shown = cell(window, row_index, table_columns.index(table_heading))
            assert shown == audit[audit_heading], (
                f"row {row_index}, {table_heading!r}: table {shown!r} != "
                f"audit CSV {audit[audit_heading]!r}"
            )
            compared += 1

    # Anti-vacuousness: three rows by eight columns were really compared,
    # and the cells were not all N/A - the anchor row carries real numbers.
    assert compared == 3 * len(correspondence)
    assert cell(
        window, 0, table_columns.index(VERTICAL_SHIFT_COLUMN_HEADING)
    ) != fmt.NOT_AVAILABLE


def test_a_horizontal_jobs_table_is_unchanged(window, tmp_path):
    """Horizontal mode asked no vertical question, so the table must not
    answer one: the same seven headings 0.1.0 shipped, no datum, no shift
    column, no sigma column - unchanged to the string."""
    job_file = tmp_path / "one-point.csv"
    job_file.write_text("101,176200.000,19685000.000,812.40,PIPE\n", encoding="utf-8")
    window.input_edit.setText(str(job_file))
    window.output_edit.setText(str(tmp_path / "out"))
    choose(window.from_zone, MI_CENTRAL)
    choose(window.to_zone, MI_SOUTH)
    if window.convert() is not True:
        raise AssertionError(f"the run failed: {window.shown_failures}")

    assert headings(window) == list(COLUMNS)
    assert window.model.columnCount() == 7
    assert columns_for(window.result) == COLUMNS
    for absent in (VERTICAL_SHIFT_COLUMN_HEADING, VERTICAL_SIGMA_LABEL):
        assert absent not in headings(window)


# ==========================================================================
# The WP-V8 review gate's findings, pinned (DESIGN.md #43).
# ==========================================================================


def test_the_vertical_tables_amber_lands_on_the_warnings_column(window, tmp_path):
    """The gate's MEDIUM: results_model derives the warnings-column index from
    the header because the vertical table is two columns wider - and nothing
    pinned that. Seeding the old fixed index 6 back survived all 1500 tests
    while painting every Grid scale factor cell amber and leaving the warned
    row's Warnings cell plain. This drives a vertical job with one genuinely
    warned point (the frozen negative-sigma position, which raises
    VERTICAL_SIGMA_UNAVAILABLE) and asserts amber sits exactly where the
    header says Warnings is - and NOT at the horizontal layout's index 6.
    Falsified by seeding that fixed index: this test alone fails.
    """
    job_file = tmp_path / "warned.csv"
    job_file.write_text(
        f"201,{ANCHOR_22.latitude},{ANCHOR_22.longitude},200.000,CLEAN\n"
        "202,42.475,-83.125,200.000,NEG SIGMA\n",
        encoding="utf-8",
    )
    fill_multi_vertical(
        window, input_path=job_file, output_directory=tmp_path / "out"
    )
    if window.convert() is not True:
        raise AssertionError(f"the run failed: {window.shown_failures}")

    table_columns = headings(window)
    warnings_at = table_columns.index("Warnings")
    # The vertical header is nine columns, so Warnings is NOT at 6 - the
    # horizontal constant. Anti-vacuousness for everything below.
    assert warnings_at == 8
    assert table_columns[6] != "Warnings"

    def background(row, column):
        return window.model.index(row, column).data(
            Qt.ItemDataRole.BackgroundRole
        )

    # Row 1 (point 202) is the warned one: amber exactly on its Warnings
    # cell, nowhere on the horizontal layout's old index, and the clean row
    # (point 201) carries no amber at all.
    assert background(1, warnings_at) is not None
    assert background(1, 6) is None
    assert background(0, warnings_at) is None
    assert background(0, 6) is None
    # The cell the amber marks really is the warning text.
    assert "vertical-sigma-unavailable" in cell(window, 1, warnings_at)

    # THE TABLE'S OWN N/A PIN (closing gate, MEDIUM 1): the same row's sigma
    # cell must read N/A, never a number - this exact cell was the one
    # surface of the #36 rule held by nothing, and a seeded 0.0000 there
    # survived the whole suite while the CSV and the warning beside it read
    # N/A. Falsified with that seed: this assertion alone fails.
    sigma_at = table_columns.index("Shift sigma (m)")
    assert cell(window, 1, sigma_at) == "N/A"
    # And the clean row's sigma is a real number, so the pin is not matching
    # two absences.
    assert cell(window, 0, sigma_at) == "0.0007"


def test_an_identity_jobs_table_sigma_cells_read_na(window, tmp_path):
    """The other reading whose sigma is None - every identity job. A 0.0000
    there would claim a perfectly known modeled shift where no model ran
    (closing gate, MEDIUM 1). The shift cell IS 0.0000 - a true statement of
    the arithmetic - and the sigma is N/A, the two distinguishable exactly as
    DESIGN.md #41 requires of the reading itself."""
    job_file = tmp_path / "identity.csv"
    job_file.write_text(
        f"301,{ANCHOR_22.latitude},{ANCHOR_22.longitude},200.000,IDENTITY\n",
        encoding="utf-8",
    )
    fill_multi_vertical(
        window, input_path=job_file, output_directory=tmp_path / "out"
    )
    make_vertical(window, NAVD88, NAVD88)
    if window.convert() is not True:
        raise AssertionError(f"the run failed: {window.shown_failures}")

    table_columns = headings(window)
    assert cell(window, 0, table_columns.index("Shift sigma (m)")) == "N/A"
    assert (
        cell(window, 0, table_columns.index("Vertical shift (m)")) == "0.0000"
    )


def test_the_vertical_tables_numbers_are_right_aligned(window, tmp_path):
    """The cosmetic half of the same gate finding: TextAlignmentRole was
    asserted nowhere in the suite, so the alignment rule could regress to the
    seven-column index set silently. Numbers right-align - including the two
    new vertical columns - and Point and Warnings do not.
    """
    vertical_multi_job(window, tmp_path)
    table_columns = headings(window)

    def alignment(column):
        value = window.model.index(0, column).data(
            Qt.ItemDataRole.TextAlignmentRole
        )
        return Qt.AlignmentFlag(value) if value is not None else None

    for column, heading in enumerate(table_columns):
        flags = alignment(column)
        if heading in ("Point", "Warnings"):
            assert flags is None or not (flags & Qt.AlignmentFlag.AlignRight), (
                f"{heading} must not right-align"
            )
        else:
            assert flags is not None and (flags & Qt.AlignmentFlag.AlignRight), (
                f"{heading} must right-align"
            )
