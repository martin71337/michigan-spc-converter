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
    GEODETIC,
    MULTI_POINT_TAB,
    SINGLE_POINT_TAB,
    UNCHOSEN,
    MainWindow,
)
from michspc.spc.zones import SPCS2022_ZONES, SPCS83_ZONES  # noqa: E402


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

    The combinations, hand-enumerated from the two dropdowns' contents
    (michspc/gui/controls.py zone_combo): each side is UNCHOSEN, GEODETIC, or
    one of the three Michigan zones, so 5 x 5 = 25 pairs, which is small enough
    to check exhaustively rather than sample. That sweep includes every case the
    rule names by hand - both unanswered states, geodetic-to-geodetic (not a
    conversion), the two geodetic directions, and a zone to ITSELF, which IS a
    conversion and must not be guarded away.
    """
    choices = [UNCHOSEN, GEODETIC, *SPCS83_ZONES]
    # 3 zones ship today; the sweep below is 25 pairs.
    assert len(choices) == 5

    checked = 0
    for source in choices:
        for target in choices:
            source_index = window.from_zone.findData(source)
            target_index = window.to_zone.findData(target)
            # Every choice must actually be in both dropdowns; findData returns
            # -1 when it is not, and a -1 here would silently test nothing.
            assert source_index >= 0, f"from_zone has no entry for {source!r}"
            assert target_index >= 0, f"to_zone has no entry for {target!r}"

            window.from_zone.setCurrentIndex(source_index)
            window.to_zone.setCurrentIndex(target_index)

            assert window.direction() == controls.direction_for(source, target), (
                f"window and controls disagree for {source!r} -> {target!r}"
            )
            checked += 1

    assert checked == 25

    # The two cases the rule singles out, stated outright rather than left
    # implicit in the sweep. A zone to itself is a real job (the units are
    # chosen independently of the zones); geodetic to geodetic is not one.
    zone = SPCS83_ZONES[0]
    assert controls.direction_for(zone, zone) is not None
    assert controls.direction_for(GEODETIC, GEODETIC) is None


# --------------------------------------------------------------------------
# The H2 gate: the 2022 zones are in the registry and out of the interface.
# --------------------------------------------------------------------------


def test_no_spcs2022_zone_is_offered_in_any_of_the_four_zone_dropdowns(window):
    """Michigan's nineteen SPCS2022 zones convert, and are not selectable yet.

    **This is a gate, not an omission**, and the reason is downstream of the
    conversion rather than in it: ``michspc.fileio.report``'s zone block writes
    the two-standard-parallel wording unconditionally and reads
    ``definition.lat_south``, which no 2022 definition record has. A 2022 job
    would convert every point correctly and then raise ``AttributeError`` while
    writing its record — after the work and before the archive. H5 rewrites
    that block per projection kind; H6 then opens the dropdowns.

    All four dropdowns are checked — both tabs, both directions — because they
    are four separate ``QComboBox`` instances and a change to one is not a
    change to the others.
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
        labels = [combo.itemText(index) for index in range(combo.count())]
        for zone in SPCS2022_ZONES:
            assert combo.findData(zone) == -1, f"{zone.name} is selectable"
            assert zone not in offered
            assert zone.name not in labels
            assert zone.code not in "".join(labels)
        # And every SPCS 83 zone still is.
        for zone in SPCS83_ZONES:
            assert combo.findData(zone) >= 0, f"{zone.name} is not selectable"


def test_the_dropdown_gate_has_something_to_exclude():
    """Anti-vacuousness for the pin above.

    If ``SPCS2022_ZONES`` were empty the test above would pass by iterating
    nothing, and would keep passing on the day the registry lost every 2022
    record. Nineteen zones, all absent from the interface, all present in the
    registry.
    """
    assert len(SPCS2022_ZONES) == 19
    assert len(SPCS83_ZONES) == 3

    from michspc.spc.zones import ALL_ZONES

    assert len(ALL_ZONES) == 22
