"""The two-tab shell, and the promise that nothing moved out from under it.

WP1 reparents every existing multi-point widget into a tab. That is the only
change in this package, and the only way it can go wrong is silently: a control
that ends up on the wrong page, or off both pages, still constructs and still
answers ``isEnabled()``. So these tests do not ask whether the window opens —
they ask **where each control actually is**, and they ask it of the widget tree
rather than of the code that built it.

The pairing that matters is tests 2 and 3. Test 2 asserts every multi-point
control is a descendant of tab 1; test 3 asserts the same controls are NOT
descendants of tab 0. Without test 3, test 2 would still pass if
``isAncestorOf`` were the wrong question — an assertion that cannot fail proves
nothing (tests/test_architecture.py says the same thing about its scanners).

Test 4 is the anti-divergence check that ``controls`` exists for: the rule that
decides a job's direction now lives in one function, and the window must be
asking that function rather than carrying a copy that agrees today.

Every expected value below is derived in the comment above it
(docs/method/METHOD.md section 4).
"""

from __future__ import annotations

import os

# MUST precede any Qt import: the platform plugin is chosen at import time and a
# later change is ignored, leaving the run needing a display it does not have
# (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from michspc.gui import controls  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.window import (  # noqa: E402
    GEODETIC_CHOICES,
    MULTI_POINT_TAB,
    SINGLE_POINT_TAB,
    UNCHOSEN,
    MainWindow,
)
from michspc.spc.frames import ALL_FRAMES, NAD83_2011  # noqa: E402
from michspc.spc.zones import (  # noqa: E402
    ALL_ZONES,
    SPCS2022_ZONES,
    SPCS83_ZONES,
)

GEODETIC = controls.geodetic_choice(NAD83_2011)
"""The NAD83(2011) geodetic entry - one of two since H6 (DESIGN.md #62)."""


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
    """A window whose failure dialog is replaced by a recorder.

    A headless run cannot answer a modal box. The seam is a plain method for
    exactly this reason, and it stays a plain method after WP1 even though the
    dialog itself moved into ``controls``.
    """
    win = MainWindow()
    win.shown_failures = []

    def record_failure(error):
        win.shown_failures.append(str(error) or repr(error))

    win._show_failure = record_failure
    yield win
    win.close()


# The ten controls that make up the multi-point job. This is the whole visible
# surface of the tab: the two file fields, the four selectors that describe the
# conversion, the longitude convention, the button that runs it, the results
# table and the status line. If any one of them were left behind on the window
# instead of moving into the tab, the tab would look complete and be missing a
# control the surveyor needs.
MULTI_POINT_CONTROL_NAMES = (
    "input_edit",
    "output_edit",
    "from_zone",
    "to_zone",
    "input_unit",
    "output_unit",
    "longitude_combo",
    "convert_button",
    "table",
    "status_label",
)


def multi_point_controls(window) -> list[tuple[str, QWidget]]:
    return [(name, getattr(window, name)) for name in MULTI_POINT_CONTROL_NAMES]


# --------------------------------------------------------------------------
# The shell
# --------------------------------------------------------------------------


def test_the_window_has_exactly_two_tabs_in_the_owners_order(window):
    """Two tabs, Single point first, and the window opens on it.

    The order is an owner decision (docs/DESIGN.md amendment #26): the everyday
    case is one typed coordinate, so it is index 0 and the window opens there.
    Asserting the count as well as the texts is what catches a third tab added
    later without a decision behind it.
    """
    assert window.tabs.count() == 2
    assert window.tabs.tabText(0) == SINGLE_POINT_TAB
    assert window.tabs.tabText(1) == MULTI_POINT_TAB

    # The captions are the module's constants, not strings retyped here, so a
    # renamed tab cannot pass this test by having been renamed in two places.
    assert SINGLE_POINT_TAB == "Single point"
    assert MULTI_POINT_TAB == "Multi point"

    assert window.tabs.currentIndex() == 0


def test_every_multi_point_control_lives_on_the_multi_point_tab(window):
    """The reparenting actually happened, control by control.

    ``isAncestorOf`` walks the real parent chain, so this is a statement about
    the constructed widget tree rather than about the builder methods' return
    values. A control that was created but never added to a layout would fail
    here, which is the failure mode a screenshot would not catch either.
    """
    page = window.tabs.widget(1)
    misplaced = [
        name for name, widget in multi_point_controls(window)
        if not page.isAncestorOf(widget)
    ]
    assert not misplaced, (
        "not on the multi-point tab: " + ", ".join(misplaced)
    )


def test_no_multi_point_control_lives_on_the_single_point_tab(window):
    """Anti-vacuousness for the test above.

    If ``isAncestorOf`` were the wrong question - if it returned True for every
    widget in the application, say - the previous test would pass while proving
    nothing. The same ten widgets asked about the OTHER page must all answer no.
    """
    page = window.tabs.widget(0)
    stowaways = [
        name for name, widget in multi_point_controls(window)
        if page.isAncestorOf(widget)
    ]
    assert not stowaways, (
        "found on the single-point tab: " + ", ".join(stowaways)
    )

    # And the placeholder really is a page of its own, not the same object as
    # the multi-point page under two indices.
    assert page is not window.tabs.widget(1)


# --------------------------------------------------------------------------
# One rule, one place
# --------------------------------------------------------------------------


def test_the_window_asks_controls_for_the_direction_in_every_combination(window):
    """``MainWindow.direction()`` is a delegation, checked over the whole sweep.

    The combinations are read off the dropdown itself rather than listed here,
    so the sweep cannot fall behind what the control offers: every SELECTABLE
    entry (the separator between the eras is not one) against every other.
    Since H6 that is the placeholder, two geodetic entries and twenty-two
    zones - 25 x 25 = 625 pairs, still small enough to check exhaustively.

    The sweep includes every case the rule names by hand: both unanswered
    states, geodetic-to-geodetic (not a conversion, in either frame and across
    the two), the two geodetic directions, a zone to ITSELF - which IS a
    conversion and must not be guarded away - and the cross-frame pairs, which
    ARE directions by this rule and which the interface now grays and the job
    refuses.

    **The two combos' signals are blocked for the sweep, deliberately.** Since
    the owner's graying round an incompatible pair does not survive being
    selected - the tab clears the other end and says so - so a sweep with the
    handlers live would be testing the reconciliation rather than the direction
    rule, and its cross-frame pairs would silently become placeholder pairs.
    ``direction()`` reads the combos' data, which the block does not affect;
    the reconciliation has its own pins in tests/test_gui_frames.py.
    """
    combo = window.from_zone
    choices = [
        combo.itemData(index)
        for index in range(combo.count())
        if combo.itemData(index) is not None
    ]
    # 1 placeholder + one geodetic entry per offered frame + every zone in the
    # registry. Derived from the registries, so a lost era fails here.
    # SUPERSEDED COUNT (DESIGN.md #70, plan W5): the five WGS 84 and ITRF
    # frames are offered since W5, so 1 + 7 + 22 = 30 selectable entries,
    # where H6 had 1 + 2 + 22 = 25. The rule is unchanged.
    # SUPERSEDED AGAIN (DESIGN.md #71, the Options build): every combo also
    # carries the two Auto entries (controls.AUTO_CHOICES, one per Auto
    # frame), so 1 + 7 + 2 + 22 = 32. The sweep covers them on BOTH ends -
    # an Auto FROM, hidden in the interface, must still answer no job.
    # INTERIM (DESIGN.md #72, plan section 4): the six UTM records are in the
    # registry from U1 but reach no dropdown until U5, so the zones counted are
    # the ones the dropdowns offer (controls.OFFERED_ZONES), still 22.
    assert len(choices) == (
        1 + len(GEODETIC_CHOICES) + len(controls.AUTO_CHOICES) + len(controls.OFFERED_ZONES)
    )
    assert len(choices) == 32

    checked = 0
    window.from_zone.blockSignals(True)
    window.to_zone.blockSignals(True)
    try:
        for source in choices:
            for target in choices:
                source_index = window.from_zone.findData(source)
                target_index = window.to_zone.findData(target)
                # Every choice must actually be in both dropdowns; findData
                # returns -1 when it is not, and a -1 here would silently test
                # nothing.
                assert source_index >= 0, f"from_zone has no entry for {source!r}"
                assert target_index >= 0, f"to_zone has no entry for {target!r}"

                window.from_zone.setCurrentIndex(source_index)
                window.to_zone.setCurrentIndex(target_index)

                assert window.direction() == controls.direction_for(
                    source, target
                ), f"window and controls disagree for {source!r} -> {target!r}"
                checked += 1
    finally:
        window.from_zone.blockSignals(False)
        window.to_zone.blockSignals(False)

    assert checked == 1024  # 32 x 32, superseding W5's 30 x 30 = 900

    # The two cases the rule singles out, stated outright rather than left
    # implicit in the sweep. A zone to itself is a real job (the units are
    # chosen independently of the zones); geodetic to geodetic is not one.
    zone = SPCS83_ZONES[0]
    assert controls.direction_for(zone, zone) is not None
    assert controls.direction_for(GEODETIC, GEODETIC) is None


# --------------------------------------------------------------------------
# The H2 gate is DISCHARGED: every registered zone is now offered.
#
# ``test_no_spcs2022_zone_is_offered_in_any_of_the_four_zone_dropdowns`` and
# ``test_the_dropdown_gate_has_something_to_exclude`` stood here and are
# SUPERSEDED BY NAME by the two below, which is what that gate's own flip
# condition asked for: H5 taught michspc.fileio.report to describe each
# projection kind, H6 taught this interface to state a zone's frame, and the
# gate said in writing that the dropdowns open when both have landed.
#
# The replacement is not "the pin was deleted". A pin that says "nothing is
# excluded" is vacuous, so what stands in its place says how MANY entries each
# dropdown has and where they come from - counts derived from the registries,
# so an era silently vanishing from the interface still fails, which is the
# property the old gate was really protecting.
# --------------------------------------------------------------------------


def test_every_registered_zone_is_offered_in_all_four_zone_dropdowns(window):
    """Both eras reach the interface, in registry order, with a separator.

    All four dropdowns are checked — both tabs, both directions — because they
    are four separate ``QComboBox`` instances and a change to one is not a
    change to the others.

    The expected content is derived from the registries and from
    ``controls.frames_offered``, never listed here: the interface's promise is
    that a zone added to an era tuple appears with no interface change
    (docs/DESIGN.md section 6), and a hand-written list would quietly stop
    checking that.
    """
    combos = (
        window.from_zone,
        window.to_zone,
        window.single_point.from_zone,
        window.single_point.to_zone,
    )
    assert len({id(combo) for combo in combos}) == 4

    for combo in combos:
        offered = [combo.itemData(index) for index in range(combo.count())]

        # 1 placeholder + the plate-fixed geodetic entries + a separator + the
        # time-dependent geodetic entries + a separator + the SPCS 83 block +
        # a separator + the SPCS2022 block. Written as the sum, with the three
        # separators counted rather than assumed, so a missing piece names
        # itself.
        #
        # SUPERSEDED LAYOUT (DESIGN.md #70, plan W5): H6 and #64 had one
        # geodetic block and two separators, 27 items. W5 offers the five WGS
        # 84 and ITRF frames in a block of their own below a third separator
        # (controls.zone_combo says why; the owner reviews it on screen):
        # 1 + 2 + 1 + 5 + 1 + 3 + 1 + 19 = 33.
        #
        # SUPERSEDED LAYOUT AGAIN (DESIGN.md #71, the Options build): the two
        # Auto entries sit at the top of the zone section in a block of their
        # own, below a fourth separator: 1 + 2 + 1 + 5 + 1 + 2 + 1 + 3 + 1 +
        # 19 = 36. Every item is always present - the Options HIDE rows
        # (tests/test_gui_options.py) - so these positions hold whatever is
        # switched on.
        plate_fixed, time_dependent = controls.geodetic_choice_groups()
        assert combo.count() == (
            1
            + len(plate_fixed)
            + 1
            + len(time_dependent)
            + 1
            + len(controls.AUTO_CHOICES)
            + 1
            + len(SPCS83_ZONES)
            + 1
            + len(SPCS2022_ZONES)
        )
        assert combo.count() == 36

        assert offered[0] == UNCHOSEN
        first_separator = 1 + len(plate_fixed)
        assert offered[1:first_separator] == list(plate_fixed)
        assert offered[first_separator] is None
        assert combo.itemText(first_separator) == ""
        global_block = first_separator + 1
        geodetic_separator = global_block + len(time_dependent)
        assert offered[global_block:geodetic_separator] == list(time_dependent)
        # The owner's second separator, added at his screen review: the
        # geodetic entries are positions and what follows them are zones, which
        # are not the same kind of answer.
        assert offered[geodetic_separator] is None
        assert combo.itemText(geodetic_separator) == ""

        # The Auto block, then its separator (DESIGN.md #71).
        first_auto = geodetic_separator + 1
        auto_separator = first_auto + len(controls.AUTO_CHOICES)
        assert offered[first_auto:auto_separator] == list(controls.AUTO_CHOICES)
        assert offered[auto_separator] is None
        assert combo.itemText(auto_separator) == ""

        first_zone = auto_separator + 1
        second_separator = first_zone + len(SPCS83_ZONES)
        assert offered[first_zone:second_separator] == list(SPCS83_ZONES)
        # A separator carries no data at all, which is what makes it a
        # separator and not a selection.
        assert offered[second_separator] is None
        assert combo.itemText(second_separator) == ""
        assert offered[second_separator + 1:] == list(SPCS2022_ZONES)

        # And every zone is findable by its own record, in both eras.
        for zone in (*SPCS83_ZONES, *SPCS2022_ZONES):
            position = combo.findData(zone)
            assert position >= 0, f"{zone.name} is not selectable"
            assert combo.itemText(position) == (
                f"{zone.name} {zone.code} - {zone.frame.code}"
            )


def test_neither_separator_can_be_chosen(window):
    """They are rules in the list, not items — a user cannot land on either.

    Qt gives a separator no ItemIsEnabled and no ItemIsSelectable flag, so it
    is unreachable by mouse or keyboard. That matters because its data is None,
    and None is not a zone: if a selection could land there, the pair would
    describe no job at all. ``controls.direction_for`` refuses it by name for
    the case that a later change reaches it programmatically, and that refusal
    is pinned in tests/test_gui_frames.py.

    **Both separators, on all four combos.** The graying round rewrites these
    items' flags every time a selection changes, and a rule that re-enabled
    every item it did not gray would turn a separator into a selectable blank
    line - which is exactly the shape of mistake that makes flags a property
    with one owner.
    """
    from PySide6.QtCore import Qt as _Qt

    # SUPERSEDED POSITIONS (DESIGN.md #70, plan W5): three separators now -
    # after the plate-fixed geodetic entries, after the time-dependent ones,
    # and after the SPCS 83 zones - where H6/#64 had two.
    # SUPERSEDED AGAIN (DESIGN.md #71): four, the Auto block having its own
    # separator after it, before the SPCS 83 zones.
    plate_fixed, time_dependent = controls.geodetic_choice_groups()
    autos = len(controls.AUTO_CHOICES)
    positions = (
        1 + len(plate_fixed),
        1 + len(plate_fixed) + 1 + len(time_dependent),
        1 + len(GEODETIC_CHOICES) + 2 + autos,
        1 + len(GEODETIC_CHOICES) + 2 + autos + 1 + len(SPCS83_ZONES),
    )
    for combo in (
        window.from_zone,
        window.to_zone,
        window.single_point.from_zone,
        window.single_point.to_zone,
    ):
        for separator in positions:
            flags = combo.model().item(separator).flags()
            assert not (flags & _Qt.ItemFlag.ItemIsEnabled), separator
            assert not (flags & _Qt.ItemFlag.ItemIsSelectable), separator

    # And they stay flagless after a selection has driven the graying.
    window.from_zone.setCurrentIndex(window.from_zone.findData(SPCS83_ZONES[0]))
    for separator in positions:
        flags = window.to_zone.model().item(separator).flags()
        assert not (flags & _Qt.ItemFlag.ItemIsEnabled), separator


def test_the_dropdown_pin_has_something_to_find():
    """Anti-vacuousness for the pin above, in its new direction.

    The old gate could pass by having nothing to exclude; this one could pass
    by having nothing to find. Twenty-two zones in two eras, two frames
    offered, and the geodetic entries derived from the frames that actually
    carry zones - so a registry that lost an era, or a frame that quietly
    became unusable, fails here rather than silently shrinking a dropdown.
    """
    assert len(SPCS2022_ZONES) == 19
    assert len(SPCS83_ZONES) == 3
    # The registry holds 28 since U1 (DESIGN.md #72); the dropdowns offer the
    # 22 State Plane zones until U5 (the pin below).
    assert len(ALL_ZONES) == 28
    assert controls.OFFERED_ZONES == SPCS83_ZONES + SPCS2022_ZONES

    # Seven of the declared frames are offered. The bare WGS 84 label is
    # declared and NOT usable, and its absence from the dropdown is the whole
    # point of #58 and of plan decision D2.
    # SUPERSEDED (DESIGN.md #70, plan W2): eight frames are declared now, not
    # three. SUPERSEDED AGAIN (plan W5): the five WGS 84 / ITRF frames carry no
    # zone but each holds an HTDP path to NAD83(2011), so frames_offered's W5
    # rule offers them, and the count is seven where W2 left it at two.
    assert len(ALL_FRAMES) == 8
    assert len(GEODETIC_CHOICES) == 7
    assert [choice.frame.code for choice in GEODETIC_CHOICES] == [
        "NAD83(2011)",
        "NATRF2022",
        "WGS84(G1762)",
        "WGS84(G2139)",
        "WGS84(G2296)",
        "ITRF2014",
        "ITRF2020",
    ]


def test_no_utm_zone_reaches_a_dropdown_or_an_options_group_before_u5(window):
    """INTERIM PIN, retired by work package U5 (docs/PLAN-utm-epsg.md section 4).

    The six UTM records are in the registry from U1, but no UTM zone may be
    selectable before the job record can describe a UTM job (U4): the #41
    rule, disclosure before reachability, and the H2 precedent, which gated
    the 2022 zones out of the dropdowns the same way until H5/H6. Checked on
    all four combos and on the Options groups, which derive from the same
    ``controls.OFFERED_ZONES`` - so a "UTM zones" toggle that switches nothing
    cannot appear either.
    """
    from michspc.gui import options
    from michspc.spc.zones import UTM_SYSTEM, UTM_ZONES

    assert len(UTM_ZONES) == 6
    assert not set(UTM_ZONES) & set(controls.OFFERED_ZONES)
    for combo in (
        window.from_zone,
        window.to_zone,
        window.single_point.from_zone,
        window.single_point.to_zone,
    ):
        for zone in UTM_ZONES:
            assert combo.findData(zone) == -1, zone.name
    assert UTM_SYSTEM not in {group.system for group in options.LIST_GROUPS}
