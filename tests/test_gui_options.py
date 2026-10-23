"""Work package Z4 of the Auto zone build: Options, Auto entry, the date in Options.

What this package made reachable, and therefore what is pinned here
(docs/PLAN-options-autozone.md section 1, DESIGN.md #71):

* **The Options** - one immutable value, window-level, read by both tabs
  (plan L7); a dialog that refuses an empty list (L8); remembered through a
  store seam the suite never lets reach the owner's registry (L9), and never
  holding a date (O3).
* **The lists follow the Options** - rows hidden in place, indexes stable,
  hidden rows also disabled so no key reaches them, separators never doubled;
  a selection the Options hide is cleared and said so (L8); every Options
  change discards a displayed Single point result (#26).
* **Auto** - at the top of the zone section of the TO lists only (L1), for
  the Options' frame only, grayed against a zone input or a frame with no
  path (L2), offering only the units every zone it can choose publishes.
* **Results** - the point's own zone and county on the Single point panel
  and as Multi point columns, Auto jobs only; an Auto refusal caught by name.
* **The observation date** - "Today" sends ``job.today_local()`` with the
  source TODAY and shows no date box; "Enter a date" shows the W5 box,
  unanswered, gating Convert, and sends ENTERED (O3, L10).

Every expected value is derived in the comment above it (docs/method/METHOD.md
section 4).
"""

from __future__ import annotations

import csv
import datetime
import os
import re

# MUST precede any Qt import: the platform plugin is chosen at import time and a
# later change is ignored (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402
from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from michspc import APP_PUBLISHER  # noqa: E402
from michspc import job as job_module  # noqa: E402
from michspc.gui import controls, options, settings_store  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.options_dialog import (  # noqa: E402
    DATE_SOURCE_TEXT,
    OptionsDialog,
    auto_frame_label,
)
from michspc.gui.results_model import single_point_clipboard_text  # noqa: E402
from michspc.gui.window import WINDOW_TITLE, MainWindow  # noqa: E402
from michspc.job import (  # noqa: E402
    AUTO_ZONE,
    AutoZoneUnplacedPointsError,
    Direction,
    ObservationDateSource,
)
from michspc.spc.frames import NAD83_2011, NATRF2022, WGS84_G2296  # noqa: E402
from michspc.spc.units import (  # noqa: E402
    INTERNATIONAL_FEET,
    METERS,
    US_SURVEY_FEET,
)
from michspc.spc.zones import (  # noqa: E402
    MI_CENTRAL,
    MI_SOUTH,
    SPCS83_ZONES,
    zone_by_code,
)
from tests.conftest import member_text  # noqa: E402

NAD = controls.geodetic_choice(NAD83_2011)
NAT = controls.geodetic_choice(NATRF2022)
G2296 = controls.geodetic_choice(WGS84_G2296)
AUTO_NAD = controls.auto_choice(NAD83_2011)
AUTO_NAT = controls.auto_choice(NATRF2022)
TIME_DEPENDENT = tuple(
    choice for choice in controls.GEODETIC_CHOICES if choice.frame.is_time_dependent
)

# Two points of tests/test_job_autozone.py, typed positive west (the tabs'
# preselected convention, DESIGN.md #29): Calhoun County (FIPS 26025), in
# Michigan South 2113 by MCL 54.232's county list and by NCAT; and the Alcona
# anchor (FIPS 26001), in Michigan Central 2112 likewise.
CALHOUN = ("42.250568", "84.954191")
ALCONA = ("44.682131", "83.622405")
# 40.0 N, 84.0 W is in Ohio: no Michigan county holds it, so Auto refuses it
# by name (plan L5) and the whole job converts nothing.
OHIO = ("40.0", "84.0")


# --------------------------------------------------------------------------
# Fixtures and helpers
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    """One QApplication for the whole module (docs/method/TOOLING.md)."""
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


def recorded(win: MainWindow) -> MainWindow:
    win.shown_failures = []
    win._show_failure = lambda error: win.shown_failures.append(str(error))
    win._ask_overwrite = lambda existing, error: True
    tab = win.single_point
    tab.shown_failures = []
    tab._show_failure = lambda error: tab.shown_failures.append(str(error))
    tab.clipboard = []
    tab._set_clipboard = tab.clipboard.append
    return win


@pytest.fixture
def store():
    return settings_store.MemoryStore()


@pytest.fixture
def window(qapp, store):
    win = recorded(MainWindow(store=store))
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


def is_hidden(combo, data) -> bool:
    return combo.view().isRowHidden(combo.findData(data))


def is_enabled(combo, data) -> bool:
    flags = combo.model().item(combo.findData(data)).flags()
    return bool(flags & Qt.ItemFlag.ItemIsEnabled)


def offered_units(combo) -> list:
    return [combo.itemData(i) for i in range(combo.count())]


def with_time_dependent(base=None, *, date_source=None) -> options.Options:
    base = options.DEFAULT_OPTIONS if base is None else base
    groups = [options.group_of(choice) for choice in TIME_DEPENDENT]
    chosen = base.with_groups(*groups)
    return options.Options(
        shown=chosen.shown,
        auto_frame=chosen.auto_frame,
        date_source=base.date_source if date_source is None else date_source,
    )


def replaced(base, **fields) -> options.Options:
    values = dict(
        shown=base.shown, auto_frame=base.auto_frame, date_source=base.date_source
    )
    values.update(fields)
    return options.Options(**values)


def type_point(tab, latitude: str, longitude: str, elevation: str = "") -> None:
    tab.first_edit.setText(latitude)
    tab.second_edit.setText(longitude)
    tab.elevation_edit.setText(elevation)


def file_job(window, tmp_path, rows: str) -> None:
    source = tmp_path / "in.csv"
    source.write_text(rows, encoding="utf-8")
    window.input_edit.setText(str(source))
    window.output_edit.setText(str(tmp_path))


def converted_single_point(tab) -> None:
    """A displayed NAD83(2011) -> Michigan South result (a fixed zone)."""
    choose(tab.from_zone, NAD)
    choose(tab.to_zone, MI_SOUTH)
    type_point(tab, *CALHOUN)
    assert tab.convert() is True, tab.shown_failures
    assert tab.sections is not None


# ==========================================================================
# 1. The persistence seam: the suite never touches the owner's registry.
# ==========================================================================


def test_the_suite_never_builds_the_real_store(qapp):
    """Plan L9: a test that read the owner's saved Options would be measuring
    his machine. tests/conftest.py installs the in-memory factory before any
    test module is collected; this pins that it did, FIRST - before anything
    here could build a window and so reach the registry if it had not - and
    that the production factory has never run in this process."""
    assert settings_store.store_factory() is not settings_store.production_store
    assert settings_store.PRODUCTION_STORES_BUILT == 0
    built = MainWindow()
    try:
        assert isinstance(built._store, settings_store.MemoryStore)
    finally:
        built.close()
    assert settings_store.PRODUCTION_STORES_BUILT == 0


def test_the_production_store_is_named_as_the_plan_states():
    """``HKCU\\Software\\DMARTIN\\MCX - Martin Coordinate Exchange`` (plan L9):
    the organisation is the publisher, the application the window title -
    one derivation, so the key cannot drift from the name the window shows."""
    assert settings_store.ORGANIZATION == APP_PUBLISHER == "DMARTIN"
    assert settings_store.APPLICATION == WINDOW_TITLE
    assert WINDOW_TITLE == "MCX - Martin Coordinate Exchange"


def test_the_qsettings_adapter_round_trips_through_an_ini_file(qapp, tmp_path):
    """The adapter the production store uses, exercised on a temp INI file -
    never the native registry - so what is written is what is read back."""
    path = tmp_path / "mcx.ini"
    store = settings_store.QSettingsStore(ini_path=path)
    chosen = with_time_dependent(date_source=ObservationDateSource.ENTERED)
    options.save_options(store, chosen)
    again = settings_store.QSettingsStore(ini_path=path)
    loaded, messages = options.load_options(again)
    assert messages == ()
    assert loaded == chosen
    assert path.exists()


# ==========================================================================
# 2. The Options value, its defaults, and what is remembered.
# ==========================================================================


def test_the_groups_and_their_labels_are_derived_from_the_registries():
    """The dialog's nine groups, in the brief's order, each named from its own
    record (no second copy of a name): the two zone systems by ``Zone.system``,
    then one latitude/longitude group per offered frame by ``frame.code``."""
    assert [group.label for group in options.LIST_GROUPS] == [
        "SPCS 83 zones",
        "SPCS2022 zones",
        "NAD83(2011) latitude/longitude",
        "NATRF2022 latitude/longitude",
        "WGS84(G1762) latitude/longitude",
        "WGS84(G2139) latitude/longitude",
        "WGS84(G2296) latitude/longitude",
        "ITRF2014 latitude/longitude",
        "ITRF2020 latitude/longitude",
    ]
    for group in options.LIST_GROUPS:
        if group.is_zone_group:
            assert group.label == f"{group.system} zones"
        else:
            assert group.label == f"{group.frame.code} latitude/longitude"


def test_the_defaults_are_all_on_but_the_five_time_dependent_frames():
    """Plan section 1 item 1: every group on except the five WGS 84 / ITRF,
    decided by each frame's own ``is_time_dependent`` - and Auto on
    NAD83(2011), the date "today" (O3)."""
    default = options.DEFAULT_OPTIONS
    for group in options.LIST_GROUPS:
        off = (not group.is_zone_group) and group.frame.is_time_dependent
        assert default.is_group_shown(group) is (not off), group.label
    assert sum(not default.is_group_shown(g) for g in options.LIST_GROUPS) == 5
    assert default.auto_frame is NAD83_2011
    assert default.date_source is ObservationDateSource.TODAY


def test_an_options_value_that_would_empty_a_list_cannot_exist():
    """L8 in the value itself, not only in the dialog."""
    geodetic_only = frozenset(
        g.key for g in options.LIST_GROUPS if not g.is_zone_group
    )
    zones_only = frozenset(g.key for g in options.LIST_GROUPS if g.is_zone_group)
    with pytest.raises(options.OptionsError, match="State Plane zones"):
        replaced(options.DEFAULT_OPTIONS, shown=geodetic_only)
    with pytest.raises(options.OptionsError, match="latitude/longitude group"):
        replaced(options.DEFAULT_OPTIONS, shown=zones_only)
    with pytest.raises(options.OptionsError, match="AUTO_FRAMES"):
        replaced(options.DEFAULT_OPTIONS, auto_frame=WGS84_G2296)


def test_remembered_options_are_read_back_by_the_next_window(qapp, store):
    """O3: the three choices are remembered - a second window built on the
    same store opens on them."""
    first = MainWindow(store=store)
    chosen = replaced(
        with_time_dependent(date_source=ObservationDateSource.ENTERED),
        auto_frame=NATRF2022,
    )
    assert first.apply_options(chosen) is True
    first.close()

    second = MainWindow(store=store)
    try:
        assert second.options == chosen
        assert second.single_point.options == chosen
        assert second.options_status == ""
    finally:
        second.close()


def test_a_date_is_never_remembered(qapp, store):
    """O3: "the choice is remembered; the date is not". A date answered under
    "Enter a date" is in no stored value, and the next window's box opens
    unanswered."""
    first = recorded(MainWindow(store=store))
    first.apply_options(
        with_time_dependent(date_source=ObservationDateSource.ENTERED)
    )
    for page in (first, first.single_point):
        page.observation_date_edit.setDate(QDate(2025, 6, 15))
    first.apply_options(first.options.with_groups(
        options.group_of(TIME_DEPENDENT[0]), shown=False
    ))
    first.close()

    iso = re.compile(r"\d{4}-\d{2}-\d{2}|2025")
    for key, value in store.values.items():
        assert not iso.search(str(value)), (key, value)
        assert "date" not in key or key == options.DATE_SOURCE_KEY, key
    assert set(store.values) == {
        *(group.key for group in options.LIST_GROUPS),
        options.AUTO_FRAME_KEY,
        options.DATE_SOURCE_KEY,
    }

    second = MainWindow(store=store)
    try:
        for page in (second, second.single_point):
            assert page.observation_date_edit.is_answered() is False
    finally:
        second.close()


@pytest.mark.parametrize(
    "key, raw, named",
    [
        ("lists/geodetic/WGS84(G2296)", "True", "Show WGS84(G2296) latitude/longitude"),
        ("lists/zones/SPCS 83", "1", "Show SPCS 83 zones"),
        (options.AUTO_FRAME_KEY, "NAD83", "Auto zone frame"),
        (options.DATE_SOURCE_KEY, "yesterday", "Observation date"),
        (options.DATE_SOURCE_KEY, 7, "Observation date"),
    ],
)
def test_an_unrecognised_stored_value_is_reset_and_said(qapp, key, raw, named):
    """L9: a value MCX does not write is never coerced ("True", "1", a short
    frame code, a non-string). It falls back to that key's default, the
    status line names the option, and the default is written back so it is
    said once."""
    store = settings_store.MemoryStore({key: raw})
    win = MainWindow(store=store)
    try:
        assert win.options == options.DEFAULT_OPTIONS
        assert f'"{named}"' in win.options_status
        assert "reset to its default" in win.options_status
        assert win.status_label.text() == win.options_status
        assert win.single_point.status_label.text() == win.options_status
        assert store.values[key] != raw
    finally:
        win.close()
    # Said once: the next window reads the written-back default silently.
    again = MainWindow(store=store)
    try:
        assert again.options_status == ""
    finally:
        again.close()


def test_stored_lists_that_would_be_empty_are_reset_and_said(qapp):
    """L8 at load: every zone group remembered OFF would leave no zone to
    choose, so the lists reset to their defaults and the status says so."""
    store = settings_store.MemoryStore(
        {g.key: "false" for g in options.LIST_GROUPS if g.is_zone_group}
    )
    win = MainWindow(store=store)
    try:
        assert win.options.shown == options.DEFAULT_SHOWN
        assert "nothing to choose" in win.options_status
    finally:
        win.close()


# ==========================================================================
# 3. The lists follow the Options.
# ==========================================================================


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_five_time_dependent_entries_are_hidden_by_default(window, which):
    """Off by default (plan section 1 item 1) on both combos of both tabs -
    hidden in the popup AND disabled, so neither the mouse nor a key reaches
    one - while every other geodetic entry and every zone is shown."""
    page = pages(window)[which]
    for combo in (page.from_zone, page.to_zone):
        for choice in TIME_DEPENDENT:
            assert is_hidden(combo, choice), choice
            assert not is_enabled(combo, choice), choice
        for data in (NAD, NAT, *SPCS83_ZONES, zone_by_code("260001")):
            assert not is_hidden(combo, data), data
            assert is_enabled(combo, data), data


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_key_cannot_step_onto_a_hidden_entry(window, which):
    """The measured Qt fact the disabling exists for: a closed combo's Down
    arrow steps through every ENABLED row, hidden or not. From NATRF2022
    (index 2) on the FROM list, the next row is the separator, then the five
    hidden WGS 84 / ITRF rows, the two Auto rows (never on a FROM list) and
    another separator - so Down lands on the first SPCS 83 zone."""
    page = pages(window)[which]
    choose(page.from_zone, NAT)
    page.from_zone.setFocus()
    QTest.keyClick(page.from_zone, Qt.Key.Key_Down)
    assert page.from_zone.currentData() is SPCS83_ZONES[0]


@pytest.mark.parametrize("which", ["single", "multi"])
def test_switching_the_five_on_shows_them(window, which):
    page = pages(window)[which]
    window.apply_options(with_time_dependent())
    for combo in (page.from_zone, page.to_zone):
        for choice in TIME_DEPENDENT:
            assert not is_hidden(combo, choice)
            assert is_enabled(combo, choice)


def _visible_sequence(combo) -> list:
    return [
        combo.itemData(i) for i in range(combo.count()) if not combo.view().isRowHidden(i)
    ]


@pytest.mark.parametrize(
    "shown_keys",
    [
        None,  # the defaults
        "all",
        "only-83-and-nad",
        "only-2022-and-wgs",
    ],
)
def test_no_two_rules_stand_together_and_none_ends_the_list(qapp, shown_keys):
    """A separator is shown only BETWEEN two shown entries: never first after
    the placeholder, never last, never two together - whatever is switched
    off (``options.visible_rows``)."""
    keys = {
        None: options.DEFAULT_SHOWN,
        "all": frozenset(g.key for g in options.LIST_GROUPS),
        "only-83-and-nad": frozenset(
            {"lists/zones/SPCS 83", "lists/geodetic/NAD83(2011)"}
        ),
        "only-2022-and-wgs": frozenset(
            {"lists/zones/SPCS2022", "lists/geodetic/WGS84(G2296)"}
        ),
    }[shown_keys]
    win = MainWindow(store=settings_store.MemoryStore())
    try:
        win.apply_options(replaced(options.DEFAULT_OPTIONS, shown=keys))
        for combo in (win.from_zone, win.to_zone, win.single_point.to_zone):
            sequence = _visible_sequence(combo)
            assert sequence[0] == controls.UNCHOSEN
            assert sequence[1] is not None
            assert sequence[-1] is not None
            for before, after in zip(sequence, sequence[1:]):
                assert not (before is None and after is None)
    finally:
        win.close()


def test_the_default_lists_read_as_the_owner_will_see_them(window):
    """The whole visible TO list under the defaults, written out: one rule
    between the positions and Auto, one between Auto and the 1983 zones, one
    before the 2022 zones. On a FROM list there is no Auto row and one rule
    between the positions and the zones."""
    from michspc.spc.zones import SPCS2022_ZONES

    assert _visible_sequence(window.to_zone) == [
        controls.UNCHOSEN, NAD, NAT, None, AUTO_NAD, None,
        *SPCS83_ZONES, None, *SPCS2022_ZONES,
    ]
    assert _visible_sequence(window.from_zone) == [
        controls.UNCHOSEN, NAD, NAT, None, *SPCS83_ZONES, None, *SPCS2022_ZONES,
    ]


@pytest.mark.parametrize("which", ["single", "multi"])
def test_hiding_a_selected_entry_clears_it_and_says_so(window, which, tmp_path):
    """L8: a group switched off while it holds a selection clears that
    selection to the placeholder, with one sentence on the status line - the
    #64 strand rule's form. On the Multi point tab the table goes with it."""
    page = pages(window)[which]
    window.apply_options(with_time_dependent())
    choose(page.from_zone, G2296)
    choose(page.to_zone, MI_SOUTH)
    assert page.from_zone.currentData() is G2296

    window.apply_options(options.DEFAULT_OPTIONS)

    assert page.from_zone.currentData() == controls.UNCHOSEN
    assert page.to_zone.currentData() is MI_SOUTH
    assert page.status_label.text() == controls.OPTIONS_RESET_STATUS
    assert controls.OPTIONS_RESET_STATUS.count(".") == 1
    assert page.settings() is None


def test_hiding_a_selection_clears_the_multi_point_table(window, tmp_path):
    window.apply_options(with_time_dependent())
    file_job(window, tmp_path, f"1,{CALHOUN[0]},{CALHOUN[1]},,A\n")
    choose(window.from_zone, G2296)
    choose(window.to_zone, MI_SOUTH)
    assert window.convert() is True, window.shown_failures
    assert window.model.rowCount() == 1

    window.apply_options(options.DEFAULT_OPTIONS)
    assert window.model.rowCount() == 0
    assert window.result is None
    assert window.status_label.text() == controls.OPTIONS_RESET_STATUS


def test_an_options_change_that_hides_nothing_leaves_the_multi_point_table(
    window, tmp_path
):
    """#65: the table describes the archive a run wrote, so an Options change
    that clears no selection leaves it - and re-gates Convert."""
    file_job(window, tmp_path, f"1,{CALHOUN[0]},{CALHOUN[1]},,A\n")
    choose(window.from_zone, NAD)
    choose(window.to_zone, MI_SOUTH)
    assert window.convert() is True, window.shown_failures
    window.apply_options(with_time_dependent())
    assert window.model.rowCount() == 1
    assert window.convert_button.isEnabled() is True


@pytest.mark.parametrize(
    "change",
    ["lists", "auto frame", "date source"],
)
def test_every_options_change_discards_a_displayed_single_point_result(
    window, change
):
    """L7 + #26: whatever the Options change - even one that hides nothing
    the tab holds - the displayed result goes, both copy paths with it."""
    tab = window.single_point
    converted_single_point(tab)
    new = {
        "lists": with_time_dependent(),
        "auto frame": replaced(options.DEFAULT_OPTIONS, auto_frame=NATRF2022),
        "date source": replaced(
            options.DEFAULT_OPTIONS, date_source=ObservationDateSource.ENTERED
        ),
    }[change]
    assert window.apply_options(new) is True
    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False
    # The selections themselves were not hidden, so they stand.
    assert tab.from_zone.currentData() is NAD
    assert tab.to_zone.currentData() is MI_SOUTH


def test_unchanged_options_change_nothing(window):
    converted_single_point(window.single_point)
    assert window.apply_options(options.DEFAULT_OPTIONS) is False
    assert window.single_point.sections is not None


# ==========================================================================
# 4. The Auto entry.
# ==========================================================================


@pytest.mark.parametrize("which", ["single", "multi"])
def test_auto_is_offered_on_the_to_list_only(window, which):
    """L1: a northing and easting do not say which zone they are in, so Auto
    is never an input - hidden and disabled on both FROM lists."""
    page = pages(window)[which]
    for choice in controls.AUTO_CHOICES:
        assert is_hidden(page.from_zone, choice)
        assert not is_enabled(page.from_zone, choice)
    assert not is_hidden(page.to_zone, AUTO_NAD)
    assert controls.direction_for(AUTO_NAD, MI_SOUTH) is None
    assert controls.direction_for(AUTO_NAD, NAD) is None


@pytest.mark.parametrize("which", ["single", "multi"])
def test_auto_follows_the_options_frame_and_its_zone_group(window, which):
    """Only the entry for the Options' Auto frame is shown, labelled with its
    zone system; and only while that system's zone group is on."""
    page = pages(window)[which]
    assert not is_hidden(page.to_zone, AUTO_NAD)
    assert is_hidden(page.to_zone, AUTO_NAT)
    assert page.to_zone.itemText(page.to_zone.findData(AUTO_NAD)) == (
        "Auto - zone from latitude/longitude (SPCS 83)"
    )
    assert page.to_zone.itemText(page.to_zone.findData(AUTO_NAT)) == (
        "Auto - zone from latitude/longitude (SPCS2022)"
    )

    window.apply_options(replaced(options.DEFAULT_OPTIONS, auto_frame=NATRF2022))
    assert is_hidden(page.to_zone, AUTO_NAD)
    assert not is_hidden(page.to_zone, AUTO_NAT)

    spcs2022 = next(g for g in options.LIST_GROUPS if g.system == "SPCS2022")
    window.apply_options(window.options.with_groups(spcs2022, shown=False))
    assert is_hidden(page.to_zone, AUTO_NAT)


@pytest.mark.parametrize("which", ["single", "multi"])
def test_changing_the_auto_frame_clears_a_selected_auto_entry(window, which):
    """Recon risk 10: an Options change must never silently re-target a
    selection to the other system - different zones, different coordinates.
    The NAD83(2011) entry is hidden by the change, so it is cleared and said."""
    page = pages(window)[which]
    choose(page.from_zone, NAD)
    choose(page.to_zone, AUTO_NAD)
    window.apply_options(replaced(options.DEFAULT_OPTIONS, auto_frame=NATRF2022))
    assert page.to_zone.currentData() == controls.UNCHOSEN
    assert page.status_label.text() == controls.OPTIONS_RESET_STATUS


@pytest.mark.parametrize("which", ["single", "multi"])
def test_auto_is_grayed_against_a_zone_input(window, which):
    page = pages(window)[which]
    choose(page.from_zone, MI_CENTRAL)
    assert not is_enabled(page.to_zone, AUTO_NAD)
    choose(page.from_zone, NAD)
    assert is_enabled(page.to_zone, AUTO_NAD)


@pytest.mark.parametrize("which", ["single", "multi"])
def test_auto_on_natrf2022_is_grayed_for_a_nad83_input(window, which):
    """L2, by #64's registry rule: no published path NAD83(2011) -> NATRF2022,
    so Auto on NATRF2022 is grayed for a NAD83(2011) or WGS 84 input and
    choosable for a NATRF2022 one - and the mirror for Auto on NAD83(2011)."""
    page = pages(window)[which]
    window.apply_options(
        with_time_dependent(replaced(options.DEFAULT_OPTIONS, auto_frame=NATRF2022))
    )
    choose(page.from_zone, NAD)
    assert not is_enabled(page.to_zone, AUTO_NAT)
    choose(page.from_zone, G2296)
    assert not is_enabled(page.to_zone, AUTO_NAT)
    choose(page.from_zone, NAT)
    assert is_enabled(page.to_zone, AUTO_NAT)

    window.apply_options(with_time_dependent())
    choose(page.from_zone, G2296)
    assert is_enabled(page.to_zone, AUTO_NAD)
    choose(page.from_zone, NAT)
    assert not is_enabled(page.to_zone, AUTO_NAD)


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_stranded_auto_selection_is_cleared_with_its_reason(window, which):
    """Auto held, then the FROM end moves: to a zone - cleared, "needs a
    latitude/longitude input"; to a frame with no path - cleared with the
    frame sentence (#64)."""
    page = pages(window)[which]
    choose(page.from_zone, NAD)
    choose(page.to_zone, AUTO_NAD)
    choose(page.from_zone, MI_SOUTH)
    assert page.to_zone.currentData() == controls.UNCHOSEN
    assert page.status_label.text() == controls.AUTO_RESET_STATUS

    choose(page.from_zone, NAD)
    choose(page.to_zone, AUTO_NAD)
    choose(page.from_zone, NAT)
    assert page.to_zone.currentData() == controls.UNCHOSEN
    assert page.status_label.text() == controls.FRAME_RESET_STATUS


@pytest.mark.parametrize("which", ["single", "multi"])
def test_auto_offers_only_the_units_every_zone_it_can_choose_publishes(
    window, which
):
    """The unit list for Auto is the intersection of the choosable zones'
    allowed units: SPCS 83 publishes all three; no SPCS2022 zone publishes the
    US survey foot, so Auto on NATRF2022 offers international feet and metres
    only - the core's own Auto unit gate, met before it is asked."""
    page = pages(window)[which]
    choose(page.from_zone, NAD)
    choose(page.output_unit, US_SURVEY_FEET)
    choose(page.to_zone, AUTO_NAD)
    assert offered_units(page.output_unit) == [
        INTERNATIONAL_FEET,
        US_SURVEY_FEET,
        METERS,
    ]
    assert page.output_unit.currentData() is US_SURVEY_FEET

    window.apply_options(replaced(options.DEFAULT_OPTIONS, auto_frame=NATRF2022))
    choose(page.from_zone, NAT)
    choose(page.to_zone, AUTO_NAT)
    assert offered_units(page.output_unit) == [INTERNATIONAL_FEET, METERS]
    assert page.output_unit.currentData() is INTERNATIONAL_FEET


@pytest.mark.parametrize("which", ["single", "multi"])
def test_an_auto_selection_states_auto_zone_and_its_frame(window, which, tmp_path):
    page = pages(window)[which]
    if which == "multi":
        file_job(window, tmp_path, f"1,{CALHOUN[0]},{CALHOUN[1]},,A\n")
    else:
        type_point(page, *CALHOUN)
    choose(page.from_zone, NAD)
    choose(page.to_zone, AUTO_NAD)
    settings = page.settings()
    assert settings is not None
    assert settings.direction is Direction.GEODETIC_TO_ZONE
    assert settings.target_zone is AUTO_ZONE
    assert settings.auto_frame is NAD83_2011
    assert settings.geodetic_frame is NAD83_2011


# ==========================================================================
# 5. Results.
# ==========================================================================


def test_an_auto_single_point_result_names_its_zone_and_county(tab):
    """The point's OWN zone - Calhoun County is in Michigan South 2113 - in
    the Zone row that labels the northing and easting beneath it, and the
    county that chose it, name and FIPS, beneath that; all in Copy all."""
    choose(tab.from_zone, NAD)
    choose(tab.to_zone, AUTO_NAD)
    type_point(tab, *CALHOUN)
    assert tab.convert() is True, tab.shown_failures

    point = tab.result.points[0]
    assert point.auto_zone.zone is MI_SOUTH
    rows = dict(tab.displayed_rows())
    assert rows["Zone"] == controls.zone_label(MI_SOUTH) == (
        "Michigan South 2113 - NAD83(2011)"
    )
    assert rows["County"] == "Calhoun"
    assert rows["County FIPS"] == "26025"
    labels = [label for label, _ in tab.displayed_rows()]
    at = labels.index("Zone")
    assert labels[at : at + 4] == ["Zone", "County", "County FIPS", "Units"]

    assert tab.copy_all() is True
    copied = tab.clipboard[-1]
    assert "Zone\tMichigan South 2113 - NAD83(2011)" in copied
    assert "County\tCalhoun" in copied
    assert "County FIPS\t26025" in copied
    assert copied == single_point_clipboard_text(tab.sections)


def test_a_fixed_zone_single_point_result_has_no_county_rows(tab):
    converted_single_point(tab)
    labels = [label for label, _ in tab.displayed_rows()]
    assert "County" not in labels
    assert "County FIPS" not in labels


def test_an_auto_multi_point_table_has_zone_and_county_columns(window, tmp_path):
    """#65: the table describes the written archive. Two points in two zones
    (Calhoun -> Michigan South, Alcona -> Michigan Central): each row names
    its own zone and county, exactly as the audit CSV's Target zone and County
    cells do, and the northings beside them are each zone's own."""
    file_job(
        window,
        tmp_path,
        f"1,{CALHOUN[0]},{CALHOUN[1]},,A\n2,{ALCONA[0]},{ALCONA[1]},,B\n",
    )
    choose(window.from_zone, NAD)
    choose(window.to_zone, AUTO_NAD)
    assert window.convert() is True, window.shown_failures

    model = window.model
    headings = [
        model.headerData(c, Qt.Orientation.Horizontal) for c in range(model.columnCount())
    ]
    assert headings[:4] == ["Point", "Zone", "County", "Northing"]
    cells = [
        [model.data(model.index(r, c)) for c in range(model.columnCount())]
        for r in range(model.rowCount())
    ]
    assert [row[:3] for row in cells] == [
        ["1", "Michigan South", "Calhoun"],
        ["2", "Michigan Central", "Alcona"],
    ]

    archive = next(iter(window.written_files.values()))
    audit = list(csv.reader(member_text(archive, "_full.csv").splitlines()))
    header, *rows = audit
    for table_row, audit_row in zip(cells, rows):
        assert table_row[1] == audit_row[header.index("Target zone")]
        assert table_row[2] == audit_row[header.index("County")]
        assert table_row[3] == audit_row[header.index("Target northing")]
    # Names, not numbers: the two text columns are not right-aligned.
    align = model.data(model.index(0, 1), Qt.ItemDataRole.TextAlignmentRole)
    assert align is None


def test_a_fixed_zone_table_is_unchanged(window, tmp_path):
    file_job(window, tmp_path, f"1,{CALHOUN[0]},{CALHOUN[1]},,A\n")
    choose(window.from_zone, NAD)
    choose(window.to_zone, MI_SOUTH)
    assert window.convert() is True
    model = window.model
    headings = [
        model.headerData(c, Qt.Orientation.Horizontal) for c in range(model.columnCount())
    ]
    assert "Zone" not in headings and "County" not in headings


@pytest.mark.parametrize("which", ["single", "multi"])
def test_an_auto_refusal_is_shown_on_both_tabs(window, which, tmp_path):
    """L5: a point in no Michigan county refuses the whole job, by name - the
    core's AutoZoneUnplacedPointsError, caught BY NAME on both tabs and shown
    exactly as raised; nothing is displayed or written."""
    page = pages(window)[which]
    if which == "multi":
        file_job(window, tmp_path, f"1,{OHIO[0]},{OHIO[1]},,A\n")
    else:
        type_point(page, *OHIO)
    choose(page.from_zone, NAD)
    choose(page.to_zone, AUTO_NAD)
    assert page.convert() is False
    assert isinstance(page.last_failure, AutoZoneUnplacedPointsError)
    assert page.shown_failures == [str(page.last_failure)]
    assert page.status_label.text().startswith("Refused: ")
    assert page.result is None
    if which == "multi":
        assert list(tmp_path.glob("*.zip")) == []
    else:
        assert page.sections is None


def test_auto_and_convert_handlers_name_the_auto_refusal():
    """Caught by NAME on both tabs, beside HtdpRefusal - a handler narrowed one
    day must not let it escape with the window disabled."""
    from pathlib import Path

    for module in ("michspc/gui/window.py", "michspc/gui/single_point.py"):
        text = Path(module).read_text(encoding="utf-8")
        assert "except AutoZoneUnplacedPointsError as error:" in text, module


# ==========================================================================
# 6. The observation date in Options (O3, L10).
# ==========================================================================


@pytest.mark.parametrize("which", ["single", "multi"])
def test_under_today_there_is_no_date_box(window, which):
    page = pages(window)[which]
    assert page.observation_date_edit.isHidden()
    assert page.observation_date_label.isHidden()


@pytest.mark.parametrize("which", ["single", "multi"])
def test_today_sends_the_local_date_and_its_source(window, which, monkeypatch, tmp_path):
    """L10: "today" is the LOCAL date the job runs. A Michigan evening is
    already tomorrow in UTC; the settings carry the local date, never the
    UTC one, with the source TODAY - which the core holds equal to
    ``today_local()``."""
    local = datetime.date(2026, 10, 22)
    utc = datetime.date(2026, 10, 23)
    monkeypatch.setattr(job_module, "_local_and_utc_dates", lambda: (local, utc))
    page = pages(window)[which]
    window.apply_options(with_time_dependent())
    if which == "multi":
        file_job(window, tmp_path, f"1,{CALHOUN[0]},{CALHOUN[1]},,A\n")
    else:
        type_point(page, *CALHOUN)
    choose(page.from_zone, G2296)
    choose(page.to_zone, MI_SOUTH)
    settings = page.settings()
    assert settings is not None
    assert settings.observation_date == local
    assert settings.observation_date_source is ObservationDateSource.TODAY


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_job_reading_no_time_dependent_frame_sends_neither(window, which, tmp_path):
    page = pages(window)[which]
    if which == "multi":
        file_job(window, tmp_path, f"1,{CALHOUN[0]},{CALHOUN[1]},,A\n")
    else:
        type_point(page, *CALHOUN)
    choose(page.from_zone, NAD)
    choose(page.to_zone, MI_SOUTH)
    settings = page.settings()
    assert settings.observation_date is None
    assert settings.observation_date_source is None


@pytest.mark.parametrize("which", ["single", "multi"])
def test_enter_a_date_shows_the_box_unanswered_and_gates_convert(
    window, which, tmp_path
):
    """O3: with "Enter a date" the W5 box appears, unanswered, and Convert
    waits for it; answered, the date goes with the source ENTERED."""
    page = pages(window)[which]
    window.apply_options(with_time_dependent(date_source=ObservationDateSource.ENTERED))
    assert not page.observation_date_edit.isHidden()
    assert page.observation_date_edit.is_answered() is False
    if which == "multi":
        file_job(window, tmp_path, f"1,{CALHOUN[0]},{CALHOUN[1]},,A\n")
    else:
        type_point(page, *CALHOUN)
    choose(page.from_zone, G2296)
    choose(page.to_zone, MI_SOUTH)
    assert page.settings() is None
    assert page.convert_button.isEnabled() is False

    page.observation_date_edit.setDate(QDate(2025, 6, 15))
    settings = page.settings()
    assert settings.observation_date == datetime.date(2025, 6, 15)
    assert settings.observation_date_source is ObservationDateSource.ENTERED
    assert page.convert_button.isEnabled() is True


@pytest.mark.parametrize("which", ["single", "multi"])
def test_leaving_enter_a_date_empties_the_box(window, which):
    """A date typed under "Enter a date" must never reappear later and be sent
    unseen: switching to "Today" empties the box."""
    page = pages(window)[which]
    window.apply_options(replaced(
        options.DEFAULT_OPTIONS, date_source=ObservationDateSource.ENTERED
    ))
    page.observation_date_edit.setDate(QDate(2025, 6, 15))
    window.apply_options(options.DEFAULT_OPTIONS)
    window.apply_options(replaced(
        options.DEFAULT_OPTIONS, date_source=ObservationDateSource.ENTERED
    ))
    assert page.observation_date_edit.is_answered() is False


def test_a_today_job_record_says_where_its_date_came_from(window, tmp_path):
    """End to end on the Multi point tab: a WGS 84 file under "Today" is
    written, and its record prints the date with Z3's source sentence."""
    window.apply_options(with_time_dependent())
    file_job(window, tmp_path, f"1,{CALHOUN[0]},{CALHOUN[1]},,A\n")
    choose(window.from_zone, G2296)
    choose(window.to_zone, MI_SOUTH)
    assert window.convert() is True, window.shown_failures
    record = member_text(next(iter(window.written_files.values())), "_README.txt")
    flat = " ".join(record.split())
    today = job_module.today_local().isoformat()
    assert f"{today}, the date the job ran (Options default)," in flat


def test_wgs84_input_with_auto_on_nad83_converts(window):
    """L2's positive half: a WGS 84 position reaches Auto on NAD83(2011)
    through HTDP, and the zone is chosen from the NAD 83 pivot."""
    window.apply_options(with_time_dependent())
    tab = window.single_point
    choose(tab.from_zone, G2296)
    choose(tab.to_zone, AUTO_NAD)
    type_point(tab, *CALHOUN)
    assert tab.convert() is True, tab.shown_failures
    assert tab.result.points[0].auto_zone.zone is MI_SOUTH
    assert tab.result.settings.observation_date_source is ObservationDateSource.TODAY


# ==========================================================================
# 7. The dialog and the menu.
# ==========================================================================


def test_the_dialog_opens_on_the_current_options(qapp):
    current = replaced(
        with_time_dependent(), auto_frame=NATRF2022,
        date_source=ObservationDateSource.ENTERED,
    )
    dialog = OptionsDialog(current)
    try:
        assert [box.text() for box in dialog.group_boxes.values()] == [
            group.label for group in options.LIST_GROUPS
        ]
        assert all(box.isChecked() for box in dialog.group_boxes.values())
        assert dialog.auto_buttons[NATRF2022].isChecked()
        assert dialog.date_buttons[ObservationDateSource.ENTERED].isChecked()
        assert dialog.options() == current
        assert dialog.ok_button.isEnabled()
    finally:
        dialog.close()


def test_the_dialog_labels(qapp):
    assert auto_frame_label(NAD83_2011) == "NAD83(2011) - SPCS 83 zones"
    assert auto_frame_label(NATRF2022) == "NATRF2022 - SPCS2022 local zones"
    assert DATE_SOURCE_TEXT[ObservationDateSource.TODAY] == (
        "Today (the date the job runs)"
    )
    assert DATE_SOURCE_TEXT[ObservationDateSource.ENTERED] == "Enter a date on the tab"


@pytest.mark.parametrize("kind", ["zone", "geodetic"])
def test_the_dialog_refuses_ok_with_an_empty_list_and_says_why(qapp, kind):
    """L8: every zone group off, or every latitude/longitude group off - OK is
    disabled, the reason is shown, and Enter cannot accept it either."""
    dialog = OptionsDialog(options.DEFAULT_OPTIONS)
    try:
        for group in options.LIST_GROUPS:
            if group.is_zone_group is (kind == "zone"):
                dialog.group_boxes[group.key].setChecked(False)
        assert dialog.ok_button.isEnabled() is False
        assert not dialog.problem_label.isHidden()
        assert dialog.problem_label.text() == dialog.problem()
        expected = "State Plane zones" if kind == "zone" else "latitude/longitude"
        assert expected in dialog.problem_label.text()
        dialog.accept()
        assert dialog.result() != OptionsDialog.DialogCode.Accepted
    finally:
        dialog.close()


def test_the_menu_opens_the_options_and_applies_and_remembers_them(window, store):
    assert window.options_action.text() == "Options…"
    chosen = with_time_dependent()
    asked = []

    def answer(current):
        asked.append(current)
        return chosen

    window._ask_options = answer
    window.options_action.trigger()
    assert asked == [options.DEFAULT_OPTIONS]
    assert window.options == chosen
    assert window.single_point.options == chosen
    assert store.values["lists/geodetic/WGS84(G2296)"] == "true"

    window._ask_options = lambda current: None  # Cancel changes nothing
    window.options_action.trigger()
    assert window.options == chosen
