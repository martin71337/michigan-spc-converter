"""Widget builders and form rules shared by the two tabs.

Everything here was factored out of ``michspc.gui.window`` unchanged, so that a
second tab can build the *same* controls rather than a lookalike set of its own.
A duplicated zone dropdown that drifted by one item, or a second copy of the
direction rule that disagreed on one combination, would be two views of the same
question giving two answers — which is the failure this feature is forbidden to
create (docs/DESIGN.md amendment #26).

**This module never computes a domain value**, for the same reason
``window`` does not: a number produced here would be a second authoritative
representation of a fact the core already owns.

It deliberately imports nothing from ``michspc.gui.window``. The dependency runs
one way — window imports controls — so that neither tab can reach the other
through this module.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QComboBox, QMessageBox, QRadioButton

from michspc.fileio import geoid
from michspc.job import Direction, LongitudeConvention, VerticalMode
from michspc.spc.units import ALL_UNITS, INTERNATIONAL_FEET, LinearUnit
from michspc.spc.frames import (
    ALL_FRAMES,
    FrameMismatchError,
    ReferenceFrame,
    require_frame_path,
)
from michspc.spc.vertical import (
    ALL_VERTICAL_DATUMS,
    HeightKind,
    VerticalDatum,
)
from michspc.spc.zones import ALL_ZONES, SPCS2022_ZONES, SPCS83_ZONES, Zone

UNCHOSEN = "unchosen"
"""Sentinel for a dropdown the user has not answered yet.

Not the same thing as a default. A combo box that opens on a real value has
answered a question the user was never asked, which is precisely the failure the
longitude convention rule exists to prevent, so the zone and convention combos
open on a placeholder and Convert stays disabled until they are answered.
"""

@dataclass(frozen=True)
class GeodeticChoice:
    """"This side of the conversion is latitude/longitude, in THIS frame".

    Carried in the same dropdown as the zones because the direction of a job is
    exactly the question "what is it coming from, and what is it going to" — the
    program converts zone to zone, geodetic to zone, and zone to geodetic
    (docs/DESIGN.md section 2), and one pair of dropdowns states all three.

    **It replaces a bare ``"geodetic"`` string, and the frame is the whole
    reason** (docs/DESIGN.md amendment #62, and #58 before it). Until the
    SPCS2022 zones landed there was exactly one frame a geodetic position could
    be in, so a sentinel that carried nothing was carrying everything there was
    to carry. There are two now. NAD83(2011) and NATRF2022 differ by one to two
    metres in Michigan and nothing in a latitude shows which one it is, so a
    geodetic selection that does not name its frame is the #58 failure with a
    second frame instead of WGS 84: the number pastes in cleanly and converts to
    something plausible and wrong.

    A frozen dataclass rather than an enum member so the frame record itself
    travels with the selection — ``settings()`` on both tabs reads
    ``choice.frame`` straight into ``JobSettings.geodetic_frame``, and no
    interface anywhere maps a label back to a frame.

    **The records below are the only ones that exist**, for the reason the zone
    records are singletons: ``QComboBox.findData`` compares stored Python
    objects by identity, not by ``==``, so a second equal instance is not
    findable in a dropdown that holds the first. Build one through
    ``geodetic_choice``; never construct one at a call site.
    """

    frame: ReferenceFrame

    @property
    def label(self) -> str:
        """What the dropdown calls this choice. Derived, never typed."""
        return geodetic_label(self.frame)

    def __str__(self) -> str:
        return self.label


def is_geodetic(data) -> bool:
    """Whether a zone dropdown's current data names a geodetic end.

    **The one predicate**, and the reason it is a function rather than an
    ``isinstance`` at fourteen call sites: those fourteen sites were fourteen
    ``== GEODETIC`` comparisons against a string, and a string comparison
    answers False for anything unexpected instead of saying so. Every one of
    them decides something that shows on screen or reaches ``JobSettings`` —
    which unit label is shown, which column layout the file is read as, whether
    a longitude convention is asked for — so they must be incapable of
    disagreeing about what "geodetic" means.
    """
    return isinstance(data, GeodeticChoice)

UNITS_LABEL = "Units:"
UNITS_LABEL_ELEVATION_ONLY = "Units (elevation only):"
"""The two spellings of a unit selector's label.

**Both selectors stay enabled in every direction, and that is the honest
state.** A unit selector is disabled only if it governs nothing, and neither
one ever governs nothing:

* The INPUT unit reads the input file. When the file is geodetic its columns
  two and three are degrees and carry no linear unit - but its ELEVATION column
  still does, and that column is what the elevation factor and the combined
  factor are computed from. Disabling the selector there would make a wrong
  foot definition unselectable rather than unnecessary.
* The OUTPUT unit writes the export. When the export is geodetic the same is
  true of its elevation column, which is re-expressed into the output unit end
  to end (WP-R2 fix A) and which the job record's "Units out" and "Precision
  written" lines both describe.

So what changes is the label, not the enablement: it says "elevation only" on
the side whose coordinate columns are degrees, and the tooltip says which
column that is and why it still matters. Greying out a control that is still
load-bearing would be a worse lie than the unqualified label was.
"""

RED = "color: #B00020;"
AMBER = "color: #8A5A00;"
"""The status line's two severity colours, and the only stylesheet in the
program. Red = actually wrong (a refusal). Amber = look at this (warnings were
raised). A clean run is the system's ordinary text colour. Nothing else is
coloured (docs/method/METHOD.md section 5).

Both are darkened against a light background rather than pure red/orange so the
text stays legible; the hue is what carries the meaning.
"""


def zone_label(zone: Zone) -> str:
    """"Michigan South 2113 - NAD83(2011)" — built from the registry.

    **The frame joins the label at H6**, and it is not decoration: two eras of
    Michigan zone are offered in one dropdown from this release on, the two
    frames are one to two metres apart, and "Michigan South" names a zone in
    each of them (2113 in SPCS 83, and the 2022 design has its own southern
    zones). The number alone distinguishes them only to somebody who knows both
    numbering schemes.

    Derived from the record's own fields — name, code, and the frame's code —
    so a label cannot drift from the mathematics the zone converts through,
    which is the #58 rule applied to the zone entries for the same reason it
    was applied to the geodetic ones.
    """
    return f"{zone.name} {zone.code} - {zone.frame.code}"


def geodetic_label(frame: ReferenceFrame) -> str:
    """What a frame's geodetic entry in every zone dropdown is called.

    The owner's instruction, 2026-08-11: name the datum, because **NAD 83 is not
    WGS 84** — they differ by a metre or more in the conterminous United States,
    which is a boundary-moving amount — and the modernized frame coming after it
    will differ again. A dropdown reading only "Geodetic" invites a surveyor to
    paste in a handheld's WGS 84 position and get a plausible, wrong answer.

    **Derived from the frame record, never typed.** The frame's own ``code`` is
    what this program converts against, so the label cannot drift from the
    mathematics. That was #58's promise in its own words - "the day a job runs
    on NATRF2022 the dropdown renames itself rather than needing to be
    remembered" - and H6 is the day: the constant became this function, the one
    entry became one per frame, and the promise was kept by the derivation
    rather than by anybody remembering.

    It carries the realization as well as the datum - "NAD83(2011)", not
    "NAD83" - because the frame record's own code is the authoritative string.
    """
    return f"{frame.code} geodetic (latitude / longitude)"


def frames_offered(frames=ALL_FRAMES, zones=ALL_ZONES) -> tuple[ReferenceFrame, ...]:
    """Every frame a geodetic entry is offered for, in declaration order.

    Two conditions, both necessary, and each one keeps out a different wrong
    entry:

    * **usable** - ``ALL_FRAMES`` carries WGS 84 precisely so this program can
      refuse it by name (``frames.FrameNotUsableError``). Offering it would put
      the one frame the registry has no path for into the dropdown that decides
      the frame, which is the exact mistake #58 was written about;
    * **referenced by at least one registered zone** - a usable frame with no
      zones is a frame nothing can be converted INTO or out of, so its geodetic
      entry could only ever pair with the placeholder or with itself, and
      geodetic-to-geodetic is not a conversion (``direction_for``). The entry
      would be a question with no answer.

    Derived, so a frame arriving in the registry with zones on it appears here
    with no interface change - the ``zone_combo`` property - and a frame whose
    status changes to not-usable disappears the same way.

    The two registries are parameters defaulting to themselves. Nothing in the
    program passes them: it is a seam for the pin, which has to be able to ask
    this rule about a frame that does not exist - "a usable frame carrying no
    zones is not offered" is a claim about a case the registry does not contain
    today and would otherwise be untestable, which is how a rule ends up being
    believed rather than checked.
    """
    with_zones = {zone.frame.code for zone in zones}
    return tuple(
        frame
        for frame in frames
        if frame.is_usable and frame.code in with_zones
    )


GEODETIC_CHOICES: tuple[GeodeticChoice, ...] = tuple(
    GeodeticChoice(frame=frame) for frame in frames_offered()
)
"""The canonical geodetic selection records, one per offered frame.

Singletons, in ``ALL_FRAMES`` declaration order, for the reason
``GeodeticChoice`` states: a dropdown finds stored Python objects by identity.
"""

_CHOICES_BY_FRAME_CODE = {choice.frame.code: choice for choice in GEODETIC_CHOICES}


def geodetic_choice(frame: ReferenceFrame) -> GeodeticChoice:
    """The canonical geodetic selection for a frame, or a loud refusal.

    The same contract as ``zones.zone_by_code`` and ``frames.frame_by_code``:
    an unoffered frame is named, together with what is offered, rather than
    silently answered with a fresh record that no dropdown could find.
    """
    try:
        return _CHOICES_BY_FRAME_CODE[frame.code]
    except (AttributeError, KeyError, TypeError):
        offered = ", ".join(choice.frame.code for choice in GEODETIC_CHOICES)
        raise KeyError(
            f"No geodetic dropdown entry exists for {frame!r}. The frames "
            f"offered are: {offered} (see controls.frames_offered - a frame "
            f"must be usable and must carry at least one registered zone)."
        ) from None


def zone_combo(parent, on_change) -> QComboBox:
    """A zone dropdown, built from the registry. Both eras, since H6.

    Zone names are never typed out here — a zone added to either era tuple
    appears in the list with no interface change (docs/DESIGN.md section 6).

    The order, and why it is this order:

    1. the unanswered placeholder;
    2. one geodetic entry per offered frame, in ``ALL_FRAMES`` declaration
       order (``frames_offered``), each naming its own datum (#58);
    3. a separator;
    4. ``SPCS83_ZONES``, the three zones every Michigan job has used since
       0.1.0 — first, because they are today's work;
    5. a separator;
    6. ``SPCS2022_ZONES``, the nineteen zones of the modernized design.

    **The separators are the only things in this dropdown that carry no
    meaning**, and they are here because the three blocks they divide are three
    different kinds of answer: a position, a 1983 zone, a 2022 zone. The second
    boundary in particular is not decorative — a job cannot cross it (the
    NAD83(2011) <-> NATRF2022 bridge is unpublished, DESIGN.md #62) — and the
    first is the owner's, on his screen review: a flat run of twenty-five
    entries reads as one list, and the geodetic entries are not zones.

    They hold no data; ``direction_for`` refuses one by name if it is ever
    reached, which no user action can do — Qt gives a separator neither the
    enabled nor the selectable flag, and arrow-key traversal skips it.

    **The H2 gate that kept the 2022 zones out of here is gone, and this
    package is what its flip condition named.** It required the record to be
    able to describe a 2022 job (H5: ``report``'s zone block per projection
    kind) and this dropdown to be able to state a zone's frame (H6: the
    frame-derived labels and the per-frame geodetic entries above). Both have
    landed. What replaced the gate is a count pinned against the registries
    themselves, so an era silently dropping out of this list still fails.

    A pair the frame registry has no path for — a NAD83(2011) geodetic entry
    against a 2022 zone — is GRAYED, on the owner's instruction after his
    screen review; ``refresh_zone_graying`` owns that rule.

    **That SUPERSEDES the stance this package shipped with**, and the
    supersession is recorded here rather than left to be inferred: the pair was
    selectable and refused at Convert, on #33's "this interface informs, it
    does not decide". The owner looked at the screens and decided the other way
    for this surface. The Convert-time refusals are untouched and remain the
    authoritative gate — the graying is what a user meets before reaching them,
    and Qt lets a program select a disabled item anyway.

    The change handler is passed in rather than hard-wired, so each tab connects
    its own — the tabs share no state (docs/DESIGN.md amendment #26) — and each
    tab passes a DIFFERENT handler per end, because the reconciliation rule has
    to know which side the user just moved to know which side to clear.
    """
    combo = QComboBox(parent)
    combo.addItem("— choose —", UNCHOSEN)
    for choice in GEODETIC_CHOICES:
        combo.addItem(choice.label, choice)
    combo.insertSeparator(combo.count())
    for zone in SPCS83_ZONES:
        combo.addItem(zone_label(zone), zone)
    combo.insertSeparator(combo.count())
    for zone in SPCS2022_ZONES:
        combo.addItem(zone_label(zone), zone)
    combo.currentIndexChanged.connect(on_change)
    return combo


def unit_combo(parent) -> QComboBox:
    """A unit dropdown, defaulting to Michigan's legislated unit.

    A default is defensible here and not for longitude: the units are stated
    in every output file, a wrong choice is visible in the magnitudes, and
    Michigan legislated the International foot (docs/DESIGN.md section 7).
    """
    combo = QComboBox(parent)
    for unit in ALL_UNITS:
        combo.addItem(unit.name, unit)
    combo.setCurrentIndex(ALL_UNITS.index(INTERNATIONAL_FEET))
    return combo


def unit_for(combo) -> LinearUnit:
    """The unit a dropdown names, refusing rather than guessing.

    Both tabs used to read ``unit_combo.currentData()`` raw, and that was
    honest while every unit dropdown held all three units for the whole life of
    the window: the data could not be anything else. **H6's per-zone filtering
    makes it possible for the combo to hold nothing** - it is cleared and
    rebuilt when the offering changes, and a rebuild that produced an empty
    list would leave ``currentData()`` returning None. None would then travel
    into ``JobSettings.input_unit`` and fail somewhere inside the writer, on a
    job whose Convert button was enabled.

    So this is the ``height_kind_for`` contract at the unit combos: name the
    impostor here, where the sentence can say which control is wrong, rather
    than several layers down. ``refresh_unit_combo`` refuses an empty offering
    for the same reason from the other side.
    """
    data = combo.currentData()
    if not isinstance(data, LinearUnit):
        raise ValueError(
            f"A unit dropdown holds {data!r}, which is not a "
            f"michspc.spc.units.LinearUnit. Every item these controls offer "
            f"carries one, and the per-zone filter only ever rebuilds them "
            f"from a zone's own allowed_units; a selection that carries "
            f"anything else is a wiring defect. Guessing a unit here would "
            f"silently decide what every northing, easting and elevation in "
            f"the job is read and written in."
        )
    return data


def units_for_selection(data) -> tuple[LinearUnit, ...]:
    """The units a zone dropdown's current selection may be read or written in.

    ``Zone.allowed_units`` is the authority and this is a convenience over it,
    never a second rule: ``job._require_units_the_zones_publish`` enforces the
    same tuple on the settings, so a caller that bypasses the interface is
    refused exactly where the interface would have filtered. A filter a caller
    can bypass is not a rule; this one does not have to be.

    A geodetic end and the unanswered placeholder both offer all three units.
    That is not a fallback: a geodetic end's coordinate columns are degrees,
    and the unit selector governs its ELEVATION column, which no zone's
    publishing authority constrains (``UNITS_LABEL_ELEVATION_ONLY``). The
    placeholder offers all three because the question of which zone applies is
    unanswered, and narrowing the units first would answer part of it.
    """
    if isinstance(data, Zone):
        return data.allowed_units
    return ALL_UNITS


def refresh_unit_combo(combo, units) -> bool:
    """Make a unit combo offer exactly ``units``. True if the selection moved.

    The ``refresh_geoid_combo`` idiom - items cleared and rebuilt, the user's
    own selection preserved when it survives, a no-op when the offering is
    already right so the many paths that call it fire no signals - with one
    deliberate difference:

    **THIS CONTROL IS NEVER DISABLED**, in any state, and the reasoning of
    ``UNITS_LABEL_ELEVATION_ONLY`` survives H6 literally: a unit selector is
    disabled only if it governs nothing, and neither one ever governs nothing,
    because even a geodetic end's Z column carries a linear unit that the
    elevation and combined factors are computed from. What narrows here is the
    OFFERING - the SPCS2022 zones publish metres and international feet only -
    and a narrowed offering is not an absent question. Where
    ``refresh_geoid_combo`` grays a side whose datum has no published model,
    this one has no such state to reach: every zone publishes at least one
    unit, and an offering that came up empty is refused below rather than
    grayed.

    **The return value is load-bearing.** When the previous selection does not
    survive the new offering - US survey feet selected, then an SPCS2022 zone
    chosen - the selection SNAPS to another unit, and a displayed result
    computed in the old one no longer describes what the controls say. That is
    the amendment #26 / #43 stale-result class arriving through a control the
    user did not touch, so the caller is told and invalidates.
    """
    units = tuple(units)
    if not units:
        raise ValueError(
            "A unit dropdown was asked to offer no units at all. Every zone "
            "publishes at least one (Zone.allowed_units), and an empty "
            "dropdown would leave the control holding nothing while still "
            "looking answerable. Pass the zone's own allowed_units."
        )

    offered = tuple(combo.itemData(i) for i in range(combo.count()))
    if offered == units:
        return False

    previous = combo.currentData()
    combo.clear()
    for unit in units:
        combo.addItem(unit.name, unit)
    preferred = (
        previous
        if previous in units
        else INTERNATIONAL_FEET
        if INTERNATIONAL_FEET in units
        else units[0]
    )
    combo.setCurrentIndex(combo.findData(preferred))
    return preferred is not previous


DEFAULT_LONGITUDE_CONVENTION = LongitudeConvention.POSITIVE_WEST
"""What the longitude sign dropdown opens on (docs/DESIGN.md amendment #29).

**This reverses a standing rule, on the owner's explicit instruction, and the
reversal is written down here so nobody quietly undoes it.** §7 said this
control has no default, and an adversarial review once recorded a default here
as a finding. The reason was real: the two conventions are indistinguishable
from the numbers in a file, and choosing wrongly moves a Michigan point about
340 miles.

What changed is not the risk but who carries it. The owner works in
positive-west — the convention of NOAA Manual NOS NGS 5 and of the MATLAB tool
this replaces — and answering the same question every run is friction he does
not want. He is the only user, he is a licensed surveyor, and it is his data.

The mitigations that remain, and they are what make this survivable:

* the answer is **on the screen, in the control, in words**, before Convert is
  pressed — this is a preselected value, not a hidden assumption;
* the job record states the convention on its own line and in the input and
  export descriptions, so any file this program produces says which reading it
  used;
* the enum itself still has no default, and neither does ``JobSettings``: the
  core will not assume a convention for a caller that does not state one. Only
  the interface opens on a value.

Anyone reviewing this and reaching for §7: read #29 first. This is a decision,
not a regression.
"""


def longitude_combo(parent, on_change) -> QComboBox:
    """The longitude sign convention dropdown, opening on the owner's own.

    No placeholder. A "— choose —" entry beside a preselected default would be
    a third option meaning "not yet", reachable only by choosing it — and
    choosing "not yet" is not something anyone does.
    """
    combo = QComboBox(parent)
    for convention in LongitudeConvention:
        combo.addItem(convention.value, convention)
    combo.setCurrentIndex(combo.findData(DEFAULT_LONGITUDE_CONVENTION))
    # NO TOOLTIP, at the owner's instruction (docs/DESIGN.md amendment #34).
    # This carried #28's worked example and #29's "CHECK THIS AGAINST THE FILE"
    # sentence; both are gone, from BOTH tabs, because this helper builds the
    # control for each of them. Verifying the convention is the user's
    # responsibility (#33), and the control still names it in words. Pinned in
    # tests/test_gui.py and tests/test_gui_single_point.py so it does not come
    # back by accident.
    combo.currentIndexChanged.connect(on_change)
    return combo


VERTICAL_MODE_LABEL = "Mode:"
HORIZONTAL_MODE_TEXT = "Horizontal"
VERTICAL_MODE_TEXT = "Horizontal + Vertical"
VERTICAL_ONLY_MODE_TEXT = "Vertical"
"""The mode toggle's three captions (docs/PLAN-vertical-datums.md section
4.1; the third is the owner's feature of 2026-08-09).

"Horizontal" is today's job, exactly - no vertical datum is asked for and
nothing is tagged. "Horizontal + Vertical" additionally converts every
elevation between the two vertical datums the revealed dropdowns name.
"Vertical" converts ONLY the elevations: the From selection names the input
system, no output system exists, and the exports reproduce the input's
coordinate columns unchanged - so the To zone row and the output unit
selector are hidden in that mode. The toggle opens on Horizontal because
that asserts nothing about a vertical datum; it is a starting state, not an
answer to the datum question, which the two dropdowns still refuse to
assume.
"""

VERTICAL_SOURCE_LABEL = "Vertical datum from:"
VERTICAL_TARGET_LABEL = "Vertical datum to:"

GEOID_MODEL_LABEL = "Geoid model:"
INPUT_GEOID_LABEL = "Input geoid:"
OUTPUT_GEOID_LABEL = "Output geoid:"
"""The geoid selectors' labels (the owner's per-side feature, 2026-08-09).

In the two vertical modes the input and output geoid models are chosen
separately: the tab's existing combo becomes the OUTPUT side under
``OUTPUT_GEOID_LABEL``, and a second combo appears under
``INPUT_GEOID_LABEL``. In Horizontal mode the single combo keeps
``GEOID_MODEL_LABEL`` and the full registry list, exactly as before, and the
input-side row hides - a horizontal job asks no per-side question.
"""


def vertical_mode_buttons(
    parent, on_change
) -> tuple[QRadioButton, QRadioButton, QRadioButton, QButtonGroup]:
    """The Horizontal / Horizontal + Vertical / Vertical toggle, one per tab.

    Three ``QRadioButton``s in an exclusive ``QButtonGroup`` - the repo's
    existing idiom (``elevation_in_file``), native per METHOD.md section 5.
    Built here so both tabs get the *same* control rather than a lookalike
    set, exactly as ``longitude_combo`` serves them both; the handler is
    passed in because the tabs share no state (docs/DESIGN.md amendment #26)
    and each connects its own.

    Opens on Horizontal (plan section 4.1): today's behaviour, asserting
    nothing about a vertical datum.

    The handler rides ``QButtonGroup.buttonToggled``, filtered to the button
    being CHECKED. With two buttons the old wiring - one button's ``toggled``
    - fired exactly once per mode change, because every change toggled both.
    Three exclusive buttons break that arithmetic: a change toggles only the
    button leaving and the button entering, so any single button's signal
    misses the switches it is not part of (Horizontal's ``toggled`` never
    fires on a Horizontal + Vertical <-> Vertical switch - a mode change
    that would silently keep a stale result on screen, the amendment #26
    CRITICAL class). The group's signal sees every change; the checked
    filter keeps the count at exactly one call per change.
    """
    horizontal = QRadioButton(HORIZONTAL_MODE_TEXT, parent)
    vertical = QRadioButton(VERTICAL_MODE_TEXT, parent)
    vertical_only = QRadioButton(VERTICAL_ONLY_MODE_TEXT, parent)
    group = QButtonGroup(parent)
    group.addButton(horizontal)
    group.addButton(vertical)
    group.addButton(vertical_only)
    # Checked BEFORE the connection, so building the control does not fire
    # the handler on a tab that is still constructing itself.
    horizontal.setChecked(True)

    def _on_button_toggled(_button, checked: bool) -> None:
        if checked:
            on_change()

    group.buttonToggled.connect(_on_button_toggled)
    return horizontal, vertical, vertical_only, group


def vertical_mode_for(
    horizontal: QRadioButton,
    vertical: QRadioButton,
    vertical_only: QRadioButton,
) -> VerticalMode:
    """The mode a tab's toggle currently states.

    The rule lives here, beside the builder, so the two tabs cannot read the
    same set of buttons two different ways. Exactly one button is checked at
    all times - the group is exclusive and the builder checks Horizontal - so
    the none-checked branch below is unreachable through the interface; it
    refuses rather than guessing because a mode guessed here would silently
    decide whether elevations, coordinates, or both are converted.
    """
    if horizontal.isChecked():
        return VerticalMode.HORIZONTAL
    if vertical.isChecked():
        return VerticalMode.HORIZONTAL_AND_VERTICAL
    if vertical_only.isChecked():
        return VerticalMode.VERTICAL
    raise ValueError(
        "No mode button is checked, so the vertical mode is unknown. "
        "The toggle is built with Horizontal checked and the group is "
        "exclusive, so this state should be unreachable; refusing rather "
        "than assuming a mode."
    )


def vertical_datum_combo(parent, on_change) -> QComboBox:
    """A vertical datum dropdown, built from the registry.

    Opens **unanswered**, per docs/DESIGN.md section 7: NGVD 29 and NAVD 88
    heights differ by up to 0.41 m across Michigan while looking identical,
    so the two entries are indistinguishable from the numbers on screen and a
    preselected one would be an answer to a question the user was never
    asked. Amendment #29's positive-west preselect is a narrow, recorded
    exception; this control is not it (plan section 4.2).

    Only USABLE datums are offered, by asking each record rather than naming
    names: NAPGD2022 is declared-not-usable in ``spc.vertical`` and must not
    appear until its status changes there - at which point it appears with no
    interface change, the property ``zone_combo`` already has. Both usable
    datums are offered on both ends: an identity pair (NAVD88 to NAVD88) is a
    legitimate job that *states* the datum, and the registry, not this
    dropdown, owns which pairs convert.
    """
    combo = QComboBox(parent)
    combo.addItem("— choose —", UNCHOSEN)
    for datum in ALL_VERTICAL_DATUMS:
        if datum.is_usable:
            # "National Geodetic Vertical Datum of 1929 (NGVD29)" - the
            # record's own name and code, via its __str__, never typed here.
            combo.addItem(str(datum), datum)
    combo.currentIndexChanged.connect(on_change)
    return combo


def vertical_datum_for(data) -> VerticalDatum | None:
    """The datum a dropdown's current data names, or None while unanswered."""
    return data if isinstance(data, VerticalDatum) else None


HEIGHT_KIND_LABEL = "Heights are:"
HEIGHT_KIND_ORTHOMETRIC = "Orthometric"
HEIGHT_KIND_ELLIPSOID = "Ellipsoid"
"""The wording of the height-kind control, one spelling on both tabs (#17).

"Heights are", not "Elevations are", because the whole premise of the control
is that the Z column may not hold elevations at all - and it dodges the
singular/plural mismatch between a tab that reads a file of them and a tab
that takes one, which would otherwise need two constants free to drift apart.

The parenthetical glosses each item carried - "(elevation)" and "(GNSS)" -
were removed at the owner's instruction (2026-08-11). The two words name the
two kinds of height a surveyor works with, and he judged the explanations
noise. Same ruling as #34 and #51: text removed, behaviour untouched.
"""


def height_kind_combo(parent) -> QComboBox:
    """What the Z column holds: an elevation, or a GNSS height.

    Opens on ORTHOMETRIC, the owner's instruction and the status quo - it is
    what every file this program has read contained, so the default assumes
    nothing that was not already assumed, and every existing job is unchanged.
    That is the same ground ``VerticalMode``'s default stands on, and it is
    why a default is defensible here where it is not for the vertical datums.

    NO TOOLTIP (#34, #51). The two item strings are the whole control.
    """
    combo = QComboBox(parent)
    combo.addItem(HEIGHT_KIND_ORTHOMETRIC, HeightKind.ORTHOMETRIC)
    combo.addItem(HEIGHT_KIND_ELLIPSOID, HeightKind.ELLIPSOID)
    combo.setCurrentIndex(combo.findData(HeightKind.ORTHOMETRIC))
    return combo


def height_kind_for(combo) -> HeightKind:
    """The kind a dropdown names, refusing rather than guessing.

    A disabled combo still reports its selection: unlike the geoid selectors,
    this control has no "unanswered" state to fall back to - the Z column
    holds one kind of height or the other, and ORTHOMETRIC is a real answer
    rather than an absence.
    """
    data = combo.currentData()
    if not isinstance(data, HeightKind):
        raise ValueError(
            f"The height-kind dropdown holds {data!r}, which is not a "
            f"HeightKind. Every item this control offers carries one; a "
            f"selection that does not is a wiring defect, and guessing "
            f"orthometric here would silently answer the question the "
            f"control exists to ask."
        )
    return data


def geoid_combo(parent) -> QComboBox:
    """A geoid model dropdown, built from the registry.

    Every model in ``geoid.ALL_GEOID_MODELS``, in declaration order, and
    nothing else - a model added to the registry appears with no interface
    change (plan section 4.3). **No "none" entry**, the owner's decision
    (plan section 5): the core can state ``geoid_model=None``, but no
    interface offers it.

    Opens on GEOID18, the model this program has shipped since 0.1.0. A
    default is defensible here as it is for the units and not for the
    vertical datums: the model in force is named in the job record and the
    audit CSV, so the answer is stated in every output rather than silently
    assumed. No handler parameter, matching ``unit_combo``: the Single point
    tab connects its own invalidation, and the Multi point tab - whose table
    describes a written archive, not the current controls - connects nothing.
    """
    combo = QComboBox(parent)
    for model in geoid.ALL_GEOID_MODELS:
        combo.addItem(model.name, model)
    combo.setCurrentIndex(combo.findData(geoid.GEOID18_MODEL))
    combo.setToolTip(
        "Geoid separation is looked up per point from the selected model's "
        "bundled grid."
    )
    return combo


def geoid_models_for_datum(datum) -> tuple:
    """Every registry model publishing separations for this datum's heights.

    The registry's own ``vertical_datum`` field is what filters - the same
    fact ``job.run``'s per-side era guard refuses on - so a side's dropdown
    can never offer a model the job would refuse for that side. ``None``
    (an unanswered datum dropdown) filters to nothing: a side whose datum
    is unknown cannot say which models apply. A future datum's models
    appear here the day their registry records do, with no interface
    change - the ``zone_combo`` property.
    """
    if datum is None:
        return ()
    return tuple(
        model
        for model in geoid.ALL_GEOID_MODELS
        if model.vertical_datum.code == datum.code
    )


def refresh_geoid_combo(combo, models) -> None:
    """Make a side's geoid combo offer exactly ``models``.

    **Disabled - grayed - with its items cleared when ``models`` is empty**,
    the owner's explicit word (2026-08-09): a side whose datum has no
    published geoid model (NGVD 29 today) is a question that APPLIES and is
    unanswerable, so the control stays visible and gray rather than hidden -
    the hidden idiom is for controls that do not apply at all. Enabled-but-
    empty would be worse than either: an enabled control promises a choice
    it cannot offer.

    A side with models enables and opens on GEOID18 where the filter keeps
    it, preserving the user's own selection when it survives a refresh so
    flipping a mode or an unrelated datum does not silently discard an
    answer. No-ops when the offering and enablement are already right, so
    the many paths that refresh cost nothing - and fire no signals - when
    nothing changed.
    """
    models = tuple(models)
    offered = tuple(combo.itemData(i) for i in range(combo.count()))
    if offered == models and combo.isEnabled() == bool(models):
        return

    previous = combo.currentData()
    combo.clear()
    for model in models:
        combo.addItem(model.name, model)
    if not models:
        combo.setEnabled(False)
        return
    combo.setEnabled(True)
    preferred = (
        previous
        if previous in models
        else geoid.GEOID18_MODEL
        if geoid.GEOID18_MODEL in models
        else models[0]
    )
    combo.setCurrentIndex(combo.findData(preferred))


def direction_for(source_data, target_data) -> Direction | None:
    """The job this pair of dropdowns describes, or None if it is not one.

    Returns None while either side is unanswered, and for the one
    combination that is not a conversion: geodetic to geodetic, which has
    no zone at either end and nothing to project through.

    A zone to ITSELF is deliberately not in that list. It returns
    ``ZONE_TO_ZONE`` and runs, because it is a real job: the units are
    selected independently of the zones, so Michigan South in feet to
    Michigan South in metres is a conversion the surveyor asked for, and
    even the identity case produces the per-point scale, convergence and
    combined factors that the audit CSV and the job record exist to report.

    **Geodetic to geodetic returns None whatever the two frames are**, and H6
    changes nothing about that: with two frames offered it is now possible to
    select NAD83(2011) geodetic against NATRF2022 geodetic, which reads like a
    datum transformation and is not one this program has - there is no zone at
    either end to project through, and the frame bridge is unpublished
    (DESIGN.md #62). It is not a conversion, so it is not a direction.

    **A cross-frame pair that IS a direction - a NAD83(2011) geodetic entry
    against an SPCS2022 zone - is answered here rather than refused.** The rule
    this function owns is what SHAPE of job the two dropdowns describe; whether
    that job's frames have a published path between them is the frame
    registry's question, and ``job.run`` asks it before a file is read. Two
    layers answering it would eventually disagree, and the one that would be
    wrong is this one, which has no registry.

    Anything else in a dropdown is refused by name. Since H6 the list contains
    one item that is not a selection at all - the separator between the two
    eras - and Qt gives it no selectable flags, so no user action reaches this
    with it. A programmatic ``setCurrentIndex`` onto it, or onto -1, would
    otherwise fall through to ``ZONE_TO_ZONE`` and hand ``job.run`` a job with
    no source zone.
    """
    if source_data == UNCHOSEN or target_data == UNCHOSEN:
        return None
    if is_geodetic(source_data) and is_geodetic(target_data):
        return None
    if is_geodetic(source_data):
        return Direction.GEODETIC_TO_ZONE
    if is_geodetic(target_data):
        return Direction.ZONE_TO_GEODETIC
    if isinstance(source_data, Zone) and isinstance(target_data, Zone):
        return Direction.ZONE_TO_ZONE
    raise ValueError(
        f"A zone dropdown holds {source_data!r} / {target_data!r}, and at "
        f"least one of those is neither the unanswered placeholder, nor a "
        f"geodetic entry, nor a zone. Every item zone_combo offers is one of "
        f"those three; the separator between the eras is not selectable and "
        f"carries no data. Refusing rather than reading it as a zone-to-zone "
        f"job, which would reach job.run with no zone."
    )


FRAME_RESET_STATUS = (
    "Cleared: no published transformation between those reference frames."
)
"""Shown when a selection is cleared because the other end moved.

One sentence, the owner's instruction after reading ``UNITS_SNAPPED_STATUS`` on
screen and finding three too many. It says the two things that cannot be
guessed from a suddenly-empty dropdown: that the program cleared it, and why.

It lives here rather than on either tab because both tabs say it, and one
wording in both surfaces is the standing rule (docs/DESIGN.md amendment #17).
"""


def frame_of(data) -> ReferenceFrame | None:
    """The reference frame a zone dropdown's item is expressed in.

    A zone carries its own; a geodetic entry carries the frame it names. The
    placeholder and the separators carry none, and ``None`` means exactly that -
    "this item states no frame" - which is what makes the compatibility rule
    below able to leave them alone rather than needing to know what they are.
    """
    if isinstance(data, Zone):
        return data.frame
    if is_geodetic(data):
        return data.frame
    return None


def frames_have_a_path(source: ReferenceFrame, target: ReferenceFrame) -> bool:
    """Whether this program can carry a position from one frame to the other.

    **Derived from the frame registry, by asking it.** Not an era test, and
    that is the whole point of writing it this way: ``require_frame_path`` is
    the same function ``job.run`` refuses on, so the interface and the gate
    cannot disagree about which pairs are convertible - and the day NGS
    publishes the NAD83(2011) <-> NATRF2022 transformation and it is registered
    in ``FRAME_TRANSFORMATIONS``, this answers True with no change to any line
    of interface code and the graying dissolves by itself. A hard-coded
    "1983 zones do not mix with 2022 zones" would still be graying them out
    that day, and somebody would have to remember it was there.

    Directional, because the registry is keyed by (source, target) and a future
    transformation need not be registered both ways.
    """
    try:
        require_frame_path(source, target)
    except FrameMismatchError:
        return False
    return True


def selection_is_compatible(candidate, other, *, candidate_is_source: bool) -> bool:
    """Whether ``candidate`` can be chosen while the other end holds ``other``.

    True whenever the question does not arise:

    * the other end is unanswered - nothing is grayed against a placeholder,
      because the user has not said anything for the candidate to disagree
      with;
    * either item states no frame at all (the placeholder itself, a separator).

    The first of those is covered by the second - ``frame_of(UNCHOSEN)`` is
    already ``None`` - and is written out anyway, measured rather than assumed:
    a falsification that deleted it changed no behaviour at all. It stays
    because the rule it states is the one a reader needs first, and because the
    day ``UNCHOSEN`` stops being frameless by accident is the day the silent
    version would start graying against a placeholder.

    Otherwise it is the registry's answer for the pair, in the direction the
    job would run: ``candidate_is_source`` says which end the candidate is, so
    a one-way transformation would gray the right list.

    **Geodetic-to-geodetic is judged by the same rule**, deliberately. It is
    not a conversion at all (``direction_for`` returns None), so nothing would
    break by exempting it - but exempting it would mean two rules where one
    does, and it would offer a NATRF2022 position against a NAD83(2011) one as
    though the pair meant something. One mechanism, no special case.
    """
    if other == UNCHOSEN:
        return True
    candidate_frame = frame_of(candidate)
    other_frame = frame_of(other)
    if candidate_frame is None or other_frame is None:
        return True
    if candidate_is_source:
        return frames_have_a_path(candidate_frame, other_frame)
    return frames_have_a_path(other_frame, candidate_frame)


def refresh_zone_graying(combo, other, *, is_source: bool) -> None:
    """Gray every item in ``combo`` that cannot be paired with ``other``.

    **Grayed - disabled in place - never removed**, the owner's word and the
    #50 vocabulary: a question that applies and cannot be answered stays
    visible and gray, where a question that does not apply at all is hidden.
    A surveyor who cannot find Michigan Grand Rapids in the list learns
    nothing; one who sees it grayed learns that his other selection is why.

    Both tabs call this through their own one owner method, so all four combos
    are grayed by one rule. The separators are never touched - they are already
    flagless, and re-enabling one would make it selectable.

    **What Qt actually does with a disabled item, measured rather than
    assumed:** the arrow keys skip it and the mouse cannot land on it, but
    ``setCurrentIndex`` selects it perfectly happily from code. So this is a
    user-interface courtesy and NOT a safety barrier, and nothing downstream
    may be simplified on the strength of it: ``job.run``'s frame gate stays the
    wall, and it is pinned as the wall.
    """
    model = combo.model()
    for index in range(combo.count()):
        data = combo.itemData(index)
        if data is None:
            # A separator. It carries no data, no flags and no meaning.
            continue
        item = model.item(index)
        allowed = selection_is_compatible(
            data, other, candidate_is_source=is_source
        )
        flags = item.flags()
        if allowed:
            item.setFlags(flags | Qt.ItemFlag.ItemIsEnabled)
        else:
            item.setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled)


def geodetic_frame_for(*sides) -> ReferenceFrame | None:
    """The frame this job's geodetic END is in, or None if it has none.

    What ``JobSettings.geodetic_frame`` is threaded from, on both tabs. The
    sides are passed in the order the tab reads them - source then target,
    or source alone in vertical-only mode - and the first geodetic one
    answers.

    First-wins is safe rather than lucky: the only pair with two geodetic
    sides is geodetic-to-geodetic, and ``direction_for`` has already made that
    not a job, so no caller reaches this with two frames in play.

    None means "no end of this job is geodetic", which is a zone-to-zone job:
    ``geodetic_frame`` is unread there, and the settings keep their default
    rather than being told something the job never consults.
    """
    for data in sides:
        if is_geodetic(data):
            return data.frame
    return None


def longitude_is_relevant(direction) -> bool:
    """The selector matters only when geodetic coordinates are involved."""
    return direction in (
        Direction.GEODETIC_TO_ZONE,
        Direction.ZONE_TO_GEODETIC,
    )


def longitude_relevance(mode, source_data, direction) -> bool:
    """Whether the longitude sign selector governs anything right now.

    The one rule for both tabs, extended for vertical-only mode: in that mode
    the To dropdown is hidden and ``direction_for`` cannot answer, so
    relevance follows the FROM selection alone - the file carries longitudes
    exactly when its input is geodetic. Every other mode keeps the standing
    ``longitude_is_relevant`` rule over the pair of dropdowns.
    """
    if mode is VerticalMode.VERTICAL:
        return is_geodetic(source_data)
    return longitude_is_relevant(direction)


def show_failure_dialog(parent, error: BaseException, title: str) -> None:
    """The failure dialog. Overridden in tests, which cannot answer a modal."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(f"{title} — conversion refused")
    # Plain text for the same reason the status line is: these messages
    # quote file content back, and no part of a refusal may be rendered
    # away as markup.
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(str(error) or repr(error))
    box.setInformativeText(
        "Nothing was written. This message names the problem exactly; it is "
        "not a summary."
    )
    box.setDetailedText(
        "".join(traceback.format_exception(type(error), error, error.__traceback__))
    )
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    box.exec()
