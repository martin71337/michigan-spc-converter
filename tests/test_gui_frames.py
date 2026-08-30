"""H6: the SPCS2022 zones and the second frame reach the screen.

What this package made reachable, and therefore what has to be pinned:

**A geodetic selection now names its FRAME, and there are two of them.** The
bare ``"geodetic"`` sentinel is gone - deleted, not deprecated - and every one
of the fourteen sites that compared against it was visited. A selection carries
``GeodeticChoice(frame=...)``, and the frame it carries is threaded into
``JobSettings.geodetic_frame``, which is the field ``job.run`` refuses a
cross-frame job on. A geodetic entry that did not name its frame would be the
amendment #58 failure with NATRF2022 in the place of WGS 84: one to two metres,
nothing in the numbers to show it.

**Both eras of zone are offered in one dropdown**, so a zone label names its
frame too, and a separator marks the boundary between two blocks that cannot be
converted between (DESIGN.md #62).

**A cross-frame pair is SELECTABLE and refuses at Convert.** That is deliberate
and it is #33's stance: this interface informs, it does not decide. The refusal
must reach the user, so it is pinned end to end on both tabs.

**The units offered follow the zone.** NGS publishes every SPCS2022 zone's
false origin in metres and international feet only, so a job left on US survey
feet has its unit changed for it - by the program, not by the user - and a
result computed in the old unit must not survive that. The survey foot is 2 ppm
from the international foot, about 26 feet at a four-million-metre easting.

Every expected value is derived from the registries in the line above it, or
from a frozen anchor named in the comment (docs/method/METHOD.md section 4).
"""

from __future__ import annotations

import os

# MUST precede any Qt import: the platform plugin is chosen at import time and a
# later change is ignored (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from michspc.gui import controls  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.window import MainWindow, UNITS_SNAPPED_STATUS  # noqa: E402
from michspc.job import (  # noqa: E402
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc import convert, frames  # noqa: E402
from michspc.spc.frames import (  # noqa: E402
    ALL_FRAMES,
    NAD83_2011,
    NATRF2022,
    WGS84,
    FrameStatus,
    FrameTransformationUnavailableError,
    ReferenceFrame,
)
from michspc.spc.units import (  # noqa: E402
    ALL_UNITS,
    INTERNATIONAL_FEET,
    METERS,
    US_SURVEY_FEET,
)
from michspc.spc.vertical import NAVD88, NGVD29  # noqa: E402
from michspc.spc.zones import (  # noqa: E402
    ALL_ZONES,
    MI_CENTRAL,
    MI_SOUTH,
    SPCS2022_ZONES,
    SPCS83_ZONES,
    zone_by_code,
)
from tests.fixtures.vertcon_anchors import NGVD29_TO_NAVD88_ANCHORS  # noqa: E402

NAD = controls.geodetic_choice(NAD83_2011)
NAT = controls.geodetic_choice(NATRF2022)

STATEWIDE_2022 = zone_by_code("260001")
"""Michigan's statewide SPCS2022 zone - the only one covering the whole state,
so a Michigan position lands inside it whichever anchor is used."""

# The frozen VERTCON anchor these vertical jobs sit on: 43.0 N, 84.5 W, where
# NCAT converts 200.000 m NGVD 29 to 199.860 m NAVD 88 (DESIGN.md #22, plan
# section 2.3). The reader's measured worst residual against the printed
# figures is 0.4716 mm, and NCAT prints to 0.001 m, so 0.0005 m is the bound.
ANCHOR = next(
    a
    for a in NGVD29_TO_NAVD88_ANCHORS
    if (a.latitude, a.longitude) == (43.0, -84.5)
)
SHIFT_TOLERANCE_M = 0.0005


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    """One QApplication for the whole module (docs/method/TOOLING.md)."""
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


@pytest.fixture
def window(qapp):
    """A window whose modal dialogs are replaced by recorders."""
    win = MainWindow()
    win.shown_failures = []
    win.overwrite_prompts = []
    win.overwrite_answer = True

    def record_failure(error):
        win.shown_failures.append(str(error) or repr(error))

    def record_overwrite(existing, error):
        win.overwrite_prompts.append([Path(p) for p in existing])
        return win.overwrite_answer

    win._show_failure = record_failure
    win._ask_overwrite = record_overwrite

    tab = win.single_point
    tab.shown_failures = []

    def record_tab_failure(error):
        tab.shown_failures.append(str(error) or repr(error))

    tab._show_failure = record_tab_failure

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


def offered_units(combo) -> list:
    return [combo.itemData(i) for i in range(combo.count())]


def item_is_enabled(combo, data) -> bool:
    """Whether the entry carrying ``data`` is choosable in ``combo``."""
    from PySide6.QtCore import Qt as _Qt

    index = combo.findData(data)
    if index < 0:
        raise AssertionError(f"{combo!r} has no entry for {data!r}")
    flags = combo.model().item(index).flags()
    return bool(flags & _Qt.ItemFlag.ItemIsEnabled)


def grayed(combo) -> list:
    """Every entry the user cannot choose right now, by data."""
    from PySide6.QtCore import Qt as _Qt

    out = []
    for index in range(combo.count()):
        data = combo.itemData(index)
        if data is None:  # a separator, never a selection
            continue
        if not (combo.model().item(index).flags() & _Qt.ItemFlag.ItemIsEnabled):
            out.append(data)
    return out


# ==========================================================================
# The sentinel is a typed record, and the string is gone.
# ==========================================================================


def test_the_geodetic_string_sentinel_no_longer_exists():
    """``controls.GEODETIC`` is DELETED, and this is what keeps it deleted.

    The string could not name a frame, and a comparison against it answers
    False for anything unexpected rather than saying so. Deleting it is what
    forced every one of the fourteen ``== GEODETIC`` sites to be visited rather
    than left to keep working by accident; a module-level name reappearing
    here - even as an alias for the NAD83(2011) choice - would let a fifteenth
    be written tomorrow.

    ``GEODETIC_LABEL`` goes with it: one label cannot describe two frames.
    """
    assert not hasattr(controls, "GEODETIC")
    assert not hasattr(controls, "GEODETIC_LABEL")


def test_is_geodetic_answers_for_every_kind_of_dropdown_data():
    """The one predicate, over everything a zone dropdown can hold.

    Including the two impostors that matter: the old string, which must NOT be
    honoured (a leftover comparison against it would otherwise keep working),
    and the separator's ``None``.
    """
    for choice in controls.GEODETIC_CHOICES:
        assert controls.is_geodetic(choice) is True

    for other in (controls.UNCHOSEN, None, "geodetic", *ALL_ZONES):
        assert controls.is_geodetic(other) is False


def test_a_geodetic_choice_is_the_registry_record_not_a_lookalike():
    """``geodetic_choice`` returns the canonical instance, and refuses others.

    Identity is load-bearing rather than pedantic: ``QComboBox.findData``
    compares stored Python objects by identity, so a second equal instance is
    unfindable in a dropdown holding the first - a selection that silently does
    nothing.
    """
    assert controls.geodetic_choice(NAD83_2011) is controls.geodetic_choice(
        NAD83_2011
    )
    assert controls.geodetic_choice(NAD83_2011) in controls.GEODETIC_CHOICES

    # A frame that is declared and not usable has no entry, and says so.
    with pytest.raises(KeyError) as raised:
        controls.geodetic_choice(WGS84)
    assert "WGS84" in str(raised.value)
    assert "NAD83(2011)" in str(raised.value)


# ==========================================================================
# What is offered, and what is not.
# ==========================================================================


def test_only_usable_frames_that_carry_zones_are_offered():
    """Two conditions, each checked against a live counterexample.

    WGS 84 is the first: declared in ``ALL_FRAMES`` precisely so this program
    can refuse it by name, and a metre or more from NAD 83 in CONUS. A geodetic
    entry for it would invite exactly the handheld position #58 was written
    about.

    A usable frame carrying no zones is the second, and it does not exist in
    the registry - so it is constructed here and passed in through
    ``frames_offered``'s own seam. Without this the rule would be believed
    rather than checked.
    """
    offered = controls.frames_offered()

    assert offered == (NAD83_2011, NATRF2022)
    assert WGS84 in ALL_FRAMES
    assert WGS84.is_usable is False
    assert WGS84 not in offered
    assert all(frame.is_usable for frame in offered)

    # Declaration order, not iteration order: it is what the dropdown shows.
    assert list(offered) == [f for f in ALL_FRAMES if f in offered]

    # A usable frame with no zones on it: offered nothing to convert to or
    # from, so it is not offered at all.
    zoneless = ReferenceFrame(
        code="ZONELESS",
        name="A usable frame with no zones",
        ellipsoid_name="GRS 80",
        citation="Constructed by this test; not a registry record.",
        status=FrameStatus.USABLE,
    )
    with_it = controls.frames_offered(
        frames=(*ALL_FRAMES, zoneless), zones=ALL_ZONES
    )
    assert zoneless not in with_it
    assert with_it == offered

    # And it IS offered the moment a zone names it - so the exclusion above is
    # about the zones, not about the frame being unrecognised.
    on_it = type(MI_SOUTH)(
        code=MI_SOUTH.code,
        abbrev=MI_SOUTH.abbrev,
        name=MI_SOUTH.name,
        system=MI_SOUTH.system,
        frame=zoneless,
        definition=MI_SOUTH.definition,
        citation=MI_SOUTH.citation,
        allowed_units=MI_SOUTH.allowed_units,
        easting_range_m=MI_SOUTH.easting_range_m,
        lat_min=MI_SOUTH.lat_min,
        lat_max=MI_SOUTH.lat_max,
        lon_min=MI_SOUTH.lon_min,
        lon_max=MI_SOUTH.lon_max,
    )
    assert zoneless in controls.frames_offered(
        frames=(*ALL_FRAMES, zoneless), zones=(*ALL_ZONES, on_it)
    )


def test_a_not_usable_frame_never_reaches_a_dropdown(window):
    """The same rule seen from the screen: no dropdown mentions WGS 84.

    Checked by label as well as by record, because the label is what a surveyor
    reads: a hard-coded entry would carry the frame's code without carrying its
    record.
    """
    for combo in (
        window.from_zone,
        window.to_zone,
        window.single_point.from_zone,
        window.single_point.to_zone,
    ):
        labels = [combo.itemText(i) for i in range(combo.count())]
        assert WGS84.code not in "".join(labels)
        for index in range(combo.count()):
            data = combo.itemData(index)
            if controls.is_geodetic(data):
                assert data.frame.is_usable


def test_every_zone_label_is_derived_from_its_own_record():
    """Name, code and FRAME, from the record - a hard-coded string fails.

    The frame joined the label at H6 because two eras share one dropdown and
    the zones are one to two metres apart between them. Asserted over every
    zone in the registry, in both eras, so a label typed out for any one of
    them fails here.
    """
    for zone in ALL_ZONES:
        assert controls.zone_label(zone) == (
            f"{zone.name} {zone.code} - {zone.frame.code}"
        )
        assert zone.frame.code in controls.zone_label(zone)

    # And the two eras really do produce different frame codes, so the pin is
    # not passing on twenty-two copies of one string.
    codes = {controls.zone_label(z).rsplit(" - ", 1)[1] for z in ALL_ZONES}
    assert codes == {"NAD83(2011)", "NATRF2022"}


def test_direction_for_refuses_data_that_is_not_a_selection():
    """The separator's ``None`` is refused by name, never read as a zone.

    Unreachable through the interface - Qt gives a separator no selectable
    flags, pinned in tests/test_gui_tabs.py - so this guards the programmatic
    route: ``setCurrentIndex`` onto the separator or onto -1 would otherwise
    fall through to ZONE_TO_ZONE and hand ``job.run`` a job with no zone.
    """
    with pytest.raises(ValueError) as raised:
        controls.direction_for(None, MI_SOUTH)
    assert "separator" in str(raised.value)

    with pytest.raises(ValueError):
        controls.direction_for(MI_SOUTH, None)

    # The old string is not a selection either, now that the sentinel is gone.
    with pytest.raises(ValueError):
        controls.direction_for("geodetic", MI_SOUTH)


def test_geodetic_to_geodetic_is_not_a_conversion_in_any_frame_pair():
    """Unchanged rule, extended to the pairs H6 made selectable.

    NAD83(2011) geodetic against NATRF2022 geodetic reads like a datum
    transformation. It is not one this program has - there is no zone at either
    end to project through, and the frame bridge is unpublished (#62).
    """
    for source in controls.GEODETIC_CHOICES:
        for target in controls.GEODETIC_CHOICES:
            assert controls.direction_for(source, target) is None


# ==========================================================================
# The frame reaches JobSettings.
# ==========================================================================


@pytest.mark.parametrize("which", ["single", "multi"])
@pytest.mark.parametrize("choice", list(controls.GEODETIC_CHOICES))
def test_the_chosen_geodetic_entry_states_its_frame_in_the_settings(
    window, which, choice, tmp_path
):
    """``geodetic_frame`` comes from the selection, on both tabs, both ends.

    This is the field ``job.run`` refuses a cross-frame job on, and the field
    the job record quotes. If the interface could not state it, every 2022
    geodetic job would be silently attributed to NAD83(2011) - which is the
    default, and which is one to two metres away.
    """
    page = pages(window)[which]
    zone = MI_SOUTH if choice.frame is NAD83_2011 else STATEWIDE_2022

    if which == "multi":
        source = tmp_path / "in.csv"
        source.write_text("1,43.0,-84.5,200.0,A\n", encoding="utf-8")
        page.input_edit.setText(str(source))
        page.output_edit.setText(str(tmp_path))
    else:
        page.first_edit.setText("43.0")
        page.second_edit.setText("-84.5")

    # Geodetic in.
    choose(page.from_zone, choice)
    choose(page.to_zone, zone)
    settings = page.settings()
    assert settings is not None
    assert settings.direction is Direction.GEODETIC_TO_ZONE
    assert settings.geodetic_frame is choice.frame

    # Geodetic out - the frame of the written latitudes and longitudes.
    if which == "single":
        page.first_edit.setText("500000.0")
        page.second_edit.setText("13000000.0")
    choose(page.from_zone, zone)
    choose(page.to_zone, choice)
    settings = page.settings()
    assert settings is not None
    assert settings.direction is Direction.ZONE_TO_GEODETIC
    assert settings.geodetic_frame is choice.frame


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_zone_to_zone_job_states_nothing_about_a_geodetic_frame(
    window, which, tmp_path
):
    """No end is geodetic, so the field is left at its default and unread.

    Stated as a decision rather than an omission: ``geodetic_frame`` has a
    default precisely because a zone-to-zone job never consults it, and the
    interface does not answer a question the job does not ask.
    """
    page = pages(window)[which]
    if which == "multi":
        source = tmp_path / "in.csv"
        source.write_text("1,500000.0,13000000.0,200.0,A\n", encoding="utf-8")
        page.input_edit.setText(str(source))
        page.output_edit.setText(str(tmp_path))
    else:
        page.first_edit.setText("500000.0")
        page.second_edit.setText("13000000.0")

    choose(page.from_zone, MI_CENTRAL)
    choose(page.to_zone, MI_SOUTH)
    settings = page.settings()

    assert settings is not None
    assert settings.direction is Direction.ZONE_TO_ZONE
    assert settings.geodetic_frame is NAD83_2011  # the field's own default


# ==========================================================================
# The cross-frame refusal reaches the user.
# ==========================================================================


def test_the_convert_time_frame_gate_is_still_the_wall(tmp_path):
    """The graying did NOT replace the refusal, and this is what says so.

    The owner's graying round is a courtesy in front of the gate, not the gate:
    Qt lets a program select a disabled item (measured - see
    ``test_a_disabled_item_is_unreachable_by_keyboard_but_not_by_code``), a
    saved job or a later caller never touches this interface at all, and a
    refusal that only existed in a dropdown would be no refusal.

    Built by hand rather than through the tabs, deliberately: that is the shape
    of every caller the interface does not own.
    """
    source = tmp_path / "in.csv"
    source.write_text("1,43.0,-84.5,200.0,A\n", encoding="utf-8")

    settings = JobSettings(
        input_path=source,
        output_directory=tmp_path,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=STATEWIDE_2022,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=NAD83_2011,
    )

    with pytest.raises(FrameTransformationUnavailableError) as raised:
        run(settings)
    message = str(raised.value)
    assert "NAD83(2011)" in message and "NATRF2022" in message
    assert "no transformation" in message
    # Nothing was written, and the file was never read: the gate is at the
    # settings, not in the loop.
    assert list(tmp_path.glob("*.zip")) == []

    # The mirror direction, whose consequence is the quietest: the latitudes
    # and longitudes WRITTEN would carry a frame label the position is not in.
    with pytest.raises(FrameTransformationUnavailableError):
        run(
            JobSettings(
                input_path=source,
                output_directory=tmp_path,
                direction=Direction.ZONE_TO_GEODETIC,
                source_zone=STATEWIDE_2022,
                target_zone=None,
                input_unit=METERS,
                output_unit=METERS,
                longitude_convention=LongitudeConvention.NEGATIVE_WEST,
                geodetic_frame=NAD83_2011,
            )
        )


def test_a_disabled_item_is_unreachable_by_keyboard_but_not_by_code(window):
    """What Qt actually does, measured on the real control and pinned.

    Two facts, and the second is why the gate above has to stay:

    * arrow-key traversal SKIPS a disabled item, as it skips a separator, so a
      user cannot land on one by keyboard - and the mouse cannot click one;
    * ``setCurrentIndex`` selects it from code without complaint.

    So the graying is a user-interface courtesy and nothing downstream may be
    simplified on the strength of it. If a Qt upgrade ever made programmatic
    selection fail instead, this test fails and says the fact changed.
    """
    from PySide6.QtCore import QEvent, Qt as _Qt
    from PySide6.QtGui import QKeyEvent

    combo = window.from_zone
    choose(window.to_zone, MI_SOUTH)  # grays every NATRF2022 entry in From
    grayed = combo.findData(STATEWIDE_2022)
    assert not (combo.model().item(grayed).flags() & _Qt.ItemFlag.ItemIsEnabled)

    # Keyboard: walk down from the last enabled zone and never arrive.
    combo.setCurrentIndex(combo.findData(SPCS83_ZONES[-1]))
    for _ in range(4):
        combo.keyPressEvent(
            QKeyEvent(
                QEvent.Type.KeyPress,
                _Qt.Key.Key_Down,
                _Qt.KeyboardModifier.NoModifier,
            )
        )
        assert combo.currentIndex() != grayed

    # Code: lands on it, which is exactly why job.run keeps the wall.
    combo.blockSignals(True)
    try:
        combo.setCurrentIndex(grayed)
    finally:
        combo.blockSignals(False)
    assert combo.currentIndex() == grayed
    assert combo.currentData() is STATEWIDE_2022


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_job_inside_the_2022_frame_converts(window, which, tmp_path):
    """The other half of #62: work WITHIN a frame is complete.

    A NATRF2022 geodetic position into a 2022 zone runs end to end. Without
    this, the refusal pins above would be satisfied by an interface that
    refused everything.
    """
    page = pages(window)[which]
    if which == "multi":
        source = tmp_path / "in.csv"
        source.write_text("1,43.0,-84.5,200.0,A\n", encoding="utf-8")
        page.input_edit.setText(str(source))
        page.output_edit.setText(str(tmp_path))
    else:
        page.first_edit.setText("43.0")
        page.second_edit.setText("-84.5")
        page.elevation_edit.setText("200.0")

    choose(page.from_zone, NAT)
    choose(page.to_zone, STATEWIDE_2022)
    choose(page.input_unit, METERS)
    choose(page.output_unit, METERS)

    assert page.convert() is True
    assert page.last_failure is None
    assert page.result is not None
    assert page.result.settings.geodetic_frame is NATRF2022


# ==========================================================================
# The owner's graying round: incompatible entries are disabled in place.
#
# This SUPERSEDES the "informing, not deciding" stance H6 shipped with, on the
# owner's instruction after his screen review. The Convert-time refusals are
# untouched and are pinned above as the wall.
# ==========================================================================


@pytest.mark.parametrize("which", ["single", "multi"])
def test_nothing_is_grayed_while_the_other_end_is_unanswered(window, which):
    """A placeholder is not an answer, so it disagrees with nothing.

    Both combos open unanswered, so this is also the state the tabs are built
    in - and a program that grayed something here would be deciding before the
    user had said anything at all.
    """
    page = pages(window)[which]
    assert page.from_zone.currentData() == controls.UNCHOSEN
    assert page.to_zone.currentData() == controls.UNCHOSEN

    assert grayed(page.from_zone) == []
    assert grayed(page.to_zone) == []


@pytest.mark.parametrize("which", ["single", "multi"])
@pytest.mark.parametrize("end", ["from", "to"])
def test_choosing_one_frame_grays_every_entry_of_the_other(window, which, end):
    """Symmetric, both tabs, and derived - never an era test.

    Choosing an SPCS 83 zone at one end grays, at the other end, exactly the
    entries whose frame has no registered path with NAD83(2011): the NATRF2022
    geodetic entry and all nineteen 2022 zones. Choosing a 2022 zone grays the
    mirror set. Nothing else is grayed, which is the half that would let an
    over-broad rule through.

    The expected sets are built from the registries here, so a zone added to
    either era joins the right set with no change to this test.
    """
    page = pages(window)[which]
    chooser = page.from_zone if end == "from" else page.to_zone
    other = page.to_zone if end == "from" else page.from_zone

    # An SPCS 83 selection at one end.
    choose(chooser, MI_SOUTH)
    assert set(grayed(other)) == {NAT, *SPCS2022_ZONES}
    assert item_is_enabled(other, NAD)
    assert item_is_enabled(other, controls.UNCHOSEN)
    for zone in SPCS83_ZONES:
        assert item_is_enabled(other, zone)

    # A 2022 selection at the same end grays the mirror set.
    choose(chooser, STATEWIDE_2022)
    assert set(grayed(other)) == {NAD, *SPCS83_ZONES}
    assert item_is_enabled(other, NAT)
    assert item_is_enabled(other, controls.UNCHOSEN)
    for zone in SPCS2022_ZONES:
        assert item_is_enabled(other, zone)


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_geodetic_entry_grays_the_other_frames_entries_too(window, which):
    """One mechanism, no special case for the geodetic-to-geodetic pair.

    That pair is not a conversion at all (``direction_for`` returns None), so
    exempting it would break nothing - and would mean two rules where one does,
    while offering a NATRF2022 position against a NAD83(2011) one as though the
    pair meant something.
    """
    page = pages(window)[which]
    choose(page.from_zone, NAD)

    assert set(grayed(page.to_zone)) == {NAT, *SPCS2022_ZONES}
    assert item_is_enabled(page.to_zone, NAD)

    choose(page.from_zone, NAT)
    assert set(grayed(page.to_zone)) == {NAD, *SPCS83_ZONES}
    assert item_is_enabled(page.to_zone, NAT)


@pytest.mark.parametrize("which", ["single", "multi"])
@pytest.mark.parametrize("end", ["from", "to"])
def test_an_end_made_unreachable_is_cleared_and_said_so(window, which, end):
    """Graying cannot undo a pair that went bad under the user's hands.

    It stops a user CHOOSING an incompatible entry; it does nothing about the
    entry already chosen at the OTHER end when this one moves. Left alone, that
    selection would sit in its combo grayed out - stating two things at once -
    and would still be what ``settings()`` read.

    So the side that did not move is cleared, the displayed result goes with
    it, and the status line says why: an empty dropdown that emptied itself is
    not something a surveyor should have to reason about.
    """
    page = pages(window)[which]
    moved = page.from_zone if end == "from" else page.to_zone
    cleared = page.to_zone if end == "from" else page.from_zone

    choose(page.from_zone, MI_CENTRAL)
    choose(page.to_zone, MI_SOUTH)
    assert cleared.currentData() is not controls.UNCHOSEN

    choose(moved, STATEWIDE_2022)

    assert cleared.currentData() == controls.UNCHOSEN
    assert moved.currentData() is STATEWIDE_2022
    assert page.status_label.text() == controls.FRAME_RESET_STATUS
    assert controls.FRAME_RESET_STATUS.count(".") == 1  # one sentence
    # The pair no longer describes a job, so Convert is not offered.
    assert page.settings() is None


def test_clearing_the_other_end_discards_a_displayed_single_point_result(tab):
    """The reset is an invalidation too - amendment #26 at a new control.

    A result on screen was computed for a pair that no longer exists, and one
    half of that pair has just been emptied by the program.
    """
    converted_single_point(tab)
    assert tab.sections is not None

    choose(tab.from_zone, STATEWIDE_2022)

    assert tab.to_zone.currentData() == controls.UNCHOSEN
    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False
    assert tab.status_label.text() == controls.FRAME_RESET_STATUS


def test_clearing_the_other_end_clears_the_multi_point_table(window, tmp_path):
    """The same, on the tab whose table describes a written archive.

    The archive stays on disk and stays correct; what cannot stand is a table
    describing a pair one of whose ends the program has just emptied.
    """
    converted_multi_point(window, tmp_path)
    written = sorted(tmp_path.glob("*.zip"))
    assert written

    choose(window.from_zone, STATEWIDE_2022)

    assert window.to_zone.currentData() == controls.UNCHOSEN
    assert window.model.rowCount() == 0
    assert window.result is None
    assert window.open_folder_button.isEnabled() is False
    assert window.status_label.text() == controls.FRAME_RESET_STATUS
    assert sorted(tmp_path.glob("*.zip")) == written


@pytest.mark.parametrize("which", ["single", "multi"])
def test_the_graying_lifts_when_a_transformation_is_registered(
    window, which, monkeypatch
):
    """**The derivation itself, pinned.** This is the point of the whole rule.

    The graying asks ``frames.require_frame_path``, which reads the registry.
    So the day NGS publishes the NAD83(2011) <-> NATRF2022 transformation and
    it is registered, every one of these entries becomes choosable again with
    no change to a line of interface code - and nobody has to remember that a
    dropdown was hiding an era.

    A synthetic cross-frame entry stands in for that day. It is the NAD83(2011)
    identity record placed under the cross key: ``FrameTransformation``'s own
    ``__post_init__`` refuses to CONSTRUCT a non-identity record (deliberately,
    #62), and what is being tested here is the lookup the interface performs,
    not the record's contents.

    A rule written as an era test - "1983 zones do not mix with 2022 zones" -
    passes every other test in this file and fails this one.
    """
    page = pages(window)[which]
    choose(page.from_zone, MI_SOUTH)
    assert set(grayed(page.to_zone)) == {NAT, *SPCS2022_ZONES}

    bridged = dict(frames._TRANSFORMATIONS_BY_CODE)
    identity = bridged[("NAD83(2011)", "NAD83(2011)")]
    bridged[("NAD83(2011)", "NATRF2022")] = identity
    bridged[("NATRF2022", "NAD83(2011)")] = identity
    monkeypatch.setattr(frames, "_TRANSFORMATIONS_BY_CODE", bridged)

    # Nothing about the interface changed - it is asked again, and answers
    # differently because the registry does.
    page._update_zone_graying()

    assert grayed(page.to_zone) == []
    assert item_is_enabled(page.to_zone, NAT)
    for zone in SPCS2022_ZONES:
        assert item_is_enabled(page.to_zone, zone)


@pytest.mark.parametrize("which", ["single", "multi"])
def test_vertical_only_mode_grays_nothing_and_clears_nothing(window, which):
    """The single system dropdown has no pairing, so it has no rule.

    In this mode the To dropdown is hidden and the From selection is the whole
    job. An invisible control must not gray - or clear - a visible one, which
    is the same distinction ``_update_vertical_rows`` already draws for the
    output unit selector.
    """
    page = pages(window)[which]
    choose(page.to_zone, MI_SOUTH)
    page.mode_vertical_only.setChecked(True)

    assert grayed(page.from_zone) == []
    # Every zone in both eras is choosable, and choosing one clears nothing.
    choose(page.from_zone, STATEWIDE_2022)
    assert page.from_zone.currentData() is STATEWIDE_2022
    assert page.to_zone.currentData() is MI_SOUTH  # hidden, untouched
    assert page.status_label.text() != controls.FRAME_RESET_STATUS
    assert grayed(page.from_zone) == []

    # Coming BACK to horizontal is where the pair is reconciled: the To
    # selection is the one the user could not see while From moved under it.
    page.mode_horizontal.setChecked(True)
    assert page.to_zone.currentData() == controls.UNCHOSEN
    assert page.status_label.text() == controls.FRAME_RESET_STATUS
    assert set(grayed(page.from_zone)) == set()  # nothing to disagree with


def test_one_owner_per_property_on_both_tabs():
    """The #57 rule, checked by AST rather than by reading.

    That amendment's defect was two methods driving one property, with the
    later call winning. Item FLAGS and item LISTS are properties in exactly the
    same sense, and the graying round added a second one - so each tab is
    scanned and each helper must be called from exactly one method, named.

    A scanner that found nothing would pass silently, so the counts are
    asserted rather than the absence of duplicates.
    """
    import ast

    expected = {
        "refresh_zone_graying": "_update_zone_graying",
        "refresh_unit_combo": "_update_unit_offerings",
        "refresh_geoid_combo": "_refresh_geoid_sides",
    }

    for module in ("michspc/gui/window.py", "michspc/gui/single_point.py"):
        tree = ast.parse(Path(module).read_text(encoding="utf-8"))
        callers: dict[str, list[str]] = {name: [] for name in expected}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                func = inner.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                if name in callers:
                    callers[name].append(node.name)

        for helper, owner in expected.items():
            found = sorted(set(callers[helper]))
            assert found == [owner], (
                f"{module}: {helper} is called from {found}, not only from "
                f"{owner}"
            )


# ==========================================================================
# The units offered follow the zone.
# ==========================================================================


@pytest.mark.parametrize("which", ["single", "multi"])
def test_each_zone_offers_exactly_the_units_it_publishes(window, which):
    """Over every zone in the registry, on both tabs, both ends.

    ``Zone.allowed_units`` is the authority; the same tuple is enforced on the
    settings by ``job._require_units_the_zones_publish``, so this filter can
    never offer something the job would refuse - and never withhold something
    the job would accept.
    """
    page = pages(window)[which]
    for zone in ALL_ZONES:
        choose(page.from_zone, zone)
        assert offered_units(page.input_unit) == list(zone.allowed_units)
        assert offered_units(page.input_unit) != []

        choose(page.to_zone, zone)
        assert offered_units(page.output_unit) == list(zone.allowed_units)

    # The two eras really do publish different sets, so the sweep above is not
    # twenty-two copies of one answer.
    assert set(SPCS83_ZONES[0].allowed_units) != set(
        SPCS2022_ZONES[0].allowed_units
    )
    assert list(SPCS2022_ZONES[0].allowed_units) == [INTERNATIONAL_FEET, METERS]
    assert US_SURVEY_FEET not in SPCS2022_ZONES[0].allowed_units


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_geodetic_end_and_the_placeholder_offer_every_unit(window, which):
    """Neither is a zone, so no zone's publishing authority constrains them.

    The selector still governs the ELEVATION column at a geodetic end, which is
    what the elevation and combined factors are computed from - so narrowing it
    there would refuse a foot definition rather than make it unnecessary.
    """
    page = pages(window)[which]
    for data in (controls.UNCHOSEN, NAD, NAT):
        choose(page.from_zone, data)
        assert offered_units(page.input_unit) == list(ALL_UNITS)


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_unit_selector_is_never_disabled_whatever_the_zone(window, which):
    """The rule ``UNITS_LABEL_ELEVATION_ONLY`` states, surviving H6 literally.

    A narrowed offering is not an absent question. This is the #57 defect's
    shape one property along - two rules driving one widget - so it is checked
    over every zone rather than argued about.
    """
    page = pages(window)[which]
    for zone in (*ALL_ZONES, MI_SOUTH):
        choose(page.from_zone, zone)
        choose(page.to_zone, zone)
        assert page.input_unit.isEnabled()
        assert page.output_unit.isEnabled()


@pytest.mark.parametrize("which", ["single", "multi"])
def test_a_surviving_selection_is_preserved_across_a_refilter(window, which):
    """Metres is published by both eras, so choosing it is not undone.

    The ``refresh_geoid_combo`` property: flipping an unrelated control does
    not silently discard an answer the user gave.
    """
    page = pages(window)[which]
    choose(page.from_zone, MI_SOUTH)
    choose(page.input_unit, METERS)

    choose(page.from_zone, STATEWIDE_2022)
    assert page.input_unit.currentData() is METERS

    choose(page.from_zone, MI_SOUTH)
    assert page.input_unit.currentData() is METERS


@pytest.mark.parametrize("which", ["single", "multi"])
def test_an_unsurvivable_selection_snaps_and_says_so(window, which):
    """US survey feet against a 2022 zone: changed by the program, not the user.

    NGS publishes no US-survey-foot false origin for any 2022 zone and beta
    NCAT prints N/A for it, so the unit cannot be offered - and the selection
    has to go somewhere. It goes to the International foot, which Michigan
    legislated and which the zone does publish.
    """
    page = pages(window)[which]
    choose(page.from_zone, MI_SOUTH)
    choose(page.input_unit, US_SURVEY_FEET)
    assert page.input_unit.currentData() is US_SURVEY_FEET

    choose(page.from_zone, STATEWIDE_2022)

    assert page.input_unit.currentData() is INTERNATIONAL_FEET
    assert US_SURVEY_FEET not in offered_units(page.input_unit)
    # And the settings that reach the job carry the unit actually shown.
    assert controls.unit_for(page.input_unit) is INTERNATIONAL_FEET


def test_unit_for_refuses_a_combo_that_holds_no_unit(window):
    """The guarded reader, at the state the filter made reachable.

    ``currentData()`` raw would hand None to ``JobSettings.input_unit`` on a
    job whose Convert button was enabled, and it would fail somewhere inside
    the writer instead of naming the control.
    """
    window.input_unit.clear()
    with pytest.raises(ValueError) as raised:
        controls.unit_for(window.input_unit)
    assert "LinearUnit" in str(raised.value)


def test_refresh_unit_combo_refuses_an_empty_offering(window):
    """The same door from the other side: no zone publishes nothing."""
    with pytest.raises(ValueError) as raised:
        controls.refresh_unit_combo(window.input_unit, ())
    assert "no units" in str(raised.value)


# ==========================================================================
# Stale results: every new control path discards a displayed one.
# ==========================================================================


def converted_single_point(tab) -> None:
    """A displayed Michigan Central -> Michigan South result, in survey feet."""
    choose(tab.from_zone, MI_CENTRAL)
    choose(tab.to_zone, MI_SOUTH)
    choose(tab.input_unit, US_SURVEY_FEET)
    choose(tab.output_unit, US_SURVEY_FEET)
    tab.first_edit.setText("176200.000")
    tab.second_edit.setText("19685000.000")
    assert tab.convert() is True
    assert tab.sections is not None


def test_a_unit_snap_discards_a_displayed_single_point_result(tab):
    """The stale-result class (#26, #43) through a control nobody touched.

    The result on screen was computed in US survey feet. Choosing a 2022 zone
    takes that unit away, and the numbers under the new selector would be 2 ppm
    out - about 26 feet at a four-million-metre easting - while still captioned
    "Converted" with both copy paths armed.

    **The zone-combo signal is BLOCKED here, and that is what makes this test
    able to fail.** Written the obvious way - choose the zone and look - it
    passed against its own defect: on this tab a zone change already discards
    the result through ``_on_direction_changed``, so the assertion was
    satisfied by a mechanism it was not testing. Seeding the snap invalidation
    away (and the two combos' own invalidation connections with it) left the
    test green, which is the definition of a pin that proves nothing.

    Blocking the signal isolates the route: the zone selection moves with no
    handler running - asserted, so the isolation itself cannot rot - and then
    the refilter is called on its own. The redundancy is real and worth having;
    what is not acceptable is a pin that cannot tell whether it is there.
    """
    converted_single_point(tab)

    tab.from_zone.blockSignals(True)
    try:
        choose(tab.from_zone, STATEWIDE_2022)
    finally:
        tab.from_zone.blockSignals(False)
    # Nothing ran, so the result is still on screen: the isolation is real and
    # what follows is about the refilter alone.
    assert tab.sections is not None
    assert tab.input_unit.currentData() is US_SURVEY_FEET

    tab._update_unit_offerings()

    assert tab.input_unit.currentData() is INTERNATIONAL_FEET
    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False


def test_choosing_a_2022_zone_discards_a_displayed_result_end_to_end(tab):
    """The same thing seen from the user's side, with every handler live.

    The pin above isolates the snap; this one is the whole gesture, and it is
    what a surveyor actually does. Both routes are wired - the zone change and
    the refilter - and this asserts that the outcome is right however they
    interleave.
    """
    converted_single_point(tab)

    choose(tab.from_zone, STATEWIDE_2022)

    assert tab.result is None
    assert tab.sections is None
    assert tab.copy_all_button.isEnabled() is False
    assert tab.input_unit.currentData() is INTERNATIONAL_FEET


def test_changing_the_era_of_a_zone_discards_a_displayed_result(tab):
    """A different era is a different job, whatever the units do."""
    converted_single_point(tab)
    choose(tab.input_unit, METERS)  # survives the filter, so no snap
    choose(tab.output_unit, METERS)
    assert tab.convert() is True

    choose(tab.to_zone, STATEWIDE_2022)

    assert tab.result is None
    assert tab.sections is None


def test_changing_the_geodetic_entrys_frame_discards_a_displayed_result(tab):
    """NAD83(2011) to NATRF2022 is a metre or two, and nothing on screen shows
    it. A result computed against one frame does not describe the other."""
    choose(tab.from_zone, NAD)
    choose(tab.to_zone, MI_SOUTH)
    choose(tab.input_unit, METERS)
    choose(tab.output_unit, METERS)
    tab.first_edit.setText("43.0")
    tab.second_edit.setText("-84.5")
    assert tab.convert() is True
    assert tab.sections is not None

    choose(tab.from_zone, NAT)

    assert tab.result is None
    assert tab.sections is None


def converted_multi_point(window, tmp_path):
    """A written Michigan Central -> Michigan South archive, in survey feet."""
    source = tmp_path / "in.csv"
    source.write_text("1,176200.000,19685000.000,900.00,A\n", encoding="utf-8")
    window.input_edit.setText(str(source))
    window.output_edit.setText(str(tmp_path))
    choose(window.from_zone, MI_CENTRAL)
    choose(window.to_zone, MI_SOUTH)
    choose(window.input_unit, US_SURVEY_FEET)
    choose(window.output_unit, US_SURVEY_FEET)
    assert window.convert() is True
    assert window.model.rowCount() == 1


def test_a_unit_snap_clears_the_multi_point_table(window, tmp_path):
    """The table clears when the program swaps a unit out from under it.

    It describes an archive that was WRITTEN, so it does not follow the
    controls in general - the files on disk are unchanged and their own record
    states the units they were written in. It clears here because the program
    itself changed the unit, and the status line says all three things that
    happened, the last of them being that nothing on disk was touched.

    **In VERTICAL-ONLY mode, and that is a finding rather than a convenience.**
    After the owner's graying round a unit snap in either horizontal mode is
    always accompanied by a frame reset - the unit offering shrinks only when
    an SPCS2022 zone is chosen, which makes any answered other end unreachable,
    and the reset's own message then supersedes this one. Vertical-only mode is
    the one place a snap stands alone, because it has no second end to
    reconcile. So this message is now reachable exactly there; recorded so the
    next reader does not conclude the test was contrived.
    """
    source = tmp_path / "in.csv"
    source.write_text("1,176200.000,19685000.000,900.00,A\n", encoding="utf-8")
    window.input_edit.setText(str(source))
    window.output_edit.setText(str(tmp_path))
    window.mode_vertical_only.setChecked(True)
    choose(window.from_zone, MI_CENTRAL)
    choose(window.input_unit, US_SURVEY_FEET)
    choose(window.vertical_source_combo, NGVD29)
    choose(window.vertical_target_combo, NAVD88)
    assert window.convert() is True
    assert window.model.rowCount() == 1

    written = sorted(tmp_path.glob("*.zip"))
    assert written

    choose(window.from_zone, STATEWIDE_2022)

    assert window.input_unit.currentData() is INTERNATIONAL_FEET
    assert window.model.rowCount() == 0
    assert window.result is None
    assert window.written_files == {}
    assert window.open_folder_button.isEnabled() is False
    assert window.status_label.text() == UNITS_SNAPPED_STATUS
    # Nothing on disk was touched: the archive is still there and still right.
    assert sorted(tmp_path.glob("*.zip")) == written


def test_an_ordinary_zone_change_leaves_the_multi_point_table_alone(
    window, tmp_path
):
    """Anti-overreach for the pin above, and the tab's standing contract.

    Michigan South publishes all three units, so moving between the SPCS 83
    zones snaps nothing - and the table goes on describing the archive that
    was written, which is what it is for. A table that cleared on every control
    change would send a surveyor back to re-run a job that is already correct
    on disk.
    """
    converted_multi_point(window, tmp_path)

    choose(window.to_zone, MI_CENTRAL)

    assert window.model.rowCount() == 1
    assert window.result is not None
    assert window.status_label.text() != UNITS_SNAPPED_STATUS


# ==========================================================================
# Vertical-only, inside the 2022 frame, end to end.
# ==========================================================================


def test_a_natrf2022_vertical_only_job_converts_and_writes(window, tmp_path):
    """Vertical mode is era-indifferent, and this is what proves it.

    The vertical machinery is keyed on VERTICAL DATUMS, not on reference
    frames: NGVD 29 and NAVD 88 are surfaces, and the VERTCON grid is looked up
    by latitude and longitude. So a 2022 zone must convert elevations exactly
    as an SPCS 83 zone does - and it must also write a job record, which is the
    H5 half of this package's precondition (``report``'s zone block used to
    write the two-standard-parallel wording unconditionally and would have
    raised ``AttributeError`` on a 2022 definition, after the work and before
    the archive).

    The INPUT is derived, the EXPECTED is frozen. The northing and easting are
    the statewide 2022 zone's own coordinates for the frozen VERTCON anchor at
    43.0 N, 84.5 W, computed here through the projection engine that the 63
    frozen beta-NCAT anchors verify; the expected elevation is NCAT's own
    printed 199.860 m for 200.000 m NGVD 29 at that position.
    """
    northing, easting, _convergence, _scale, _warnings = convert.from_geodetic(
        ANCHOR.latitude, ANCHOR.longitude, STATEWIDE_2022
    )

    source = tmp_path / "in.csv"
    source.write_text(
        f"1,{northing:.3f},{easting:.3f},{ANCHOR.source_height_m:.3f},ANCHOR\n",
        encoding="utf-8",
    )
    window.input_edit.setText(str(source))
    window.output_edit.setText(str(tmp_path))

    window.mode_vertical_only.setChecked(True)
    choose(window.from_zone, STATEWIDE_2022)
    choose(window.input_unit, METERS)
    choose(window.vertical_source_combo, NGVD29)
    choose(window.vertical_target_combo, NAVD88)

    settings = window.settings()
    assert settings is not None
    assert settings.direction is Direction.VERTICAL_ONLY
    assert settings.vertical_mode is VerticalMode.VERTICAL
    assert settings.source_zone is STATEWIDE_2022
    assert settings.source_zone.frame is NATRF2022

    assert window.convert() is True
    assert window.last_failure is None

    # 200.000 m NGVD 29 -> 199.860 m NAVD 88 at the anchor (frozen NCAT). The
    # job is in metres, so the output elevation is directly comparable.
    point = window.result.points[0]
    assert point.vertical is not None
    assert abs(point.output_elevation - ANCHOR.target_height_m) < SHIFT_TOLERANCE_M
    # And the shift really happened, rather than the height passing through.
    assert abs(point.output_elevation - ANCHOR.source_height_m) > 0.1

    # And the archive - the job record included - was actually written.
    assert window.written_files
    assert sorted(tmp_path.glob("*.zip"))
