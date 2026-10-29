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

import datetime
import traceback
from dataclasses import dataclass

from PySide6.QtCore import QDate, QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QMessageBox,
    QRadioButton,
)

from michspc import job as job_module
from michspc.fileio import geoid
from michspc.job import (
    AUTO_FRAMES,
    AutoZoneUnplacedPointsError,
    Direction,
    LongitudeConvention,
    ObservationDateSource,
    VerticalMode,
    auto_zone_system,
    is_zoneless,
)
from michspc.spc.autozone import AutoZoneSystem, zones_choosable
from michspc.spc.units import ALL_UNITS, INTERNATIONAL_FEET, LinearUnit
from michspc.spc.convert import require_an_applicable_path
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
from michspc.spc.epsg import frame_label_suffix, zone_label_suffix
from michspc.spc.zones import ALL_ZONES, SPCS2022_ZONES, SPCS83_ZONES, UTM_SYSTEM, Zone

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


@dataclass(frozen=True)
class AutoChoice:
    """"Choose each point's zone from its latitude/longitude, in THIS frame".

    The Auto entry of a TO dropdown (docs/PLAN-options-autozone.md L1, L2;
    DESIGN.md #71). ``settings()`` on both tabs turns it into
    ``JobSettings.target_zone=job.AUTO_ZONE`` with ``auto_frame=choice.frame``,
    so the frame travels WITH the selection, exactly as ``GeodeticChoice``
    carries its own - and that is why the dropdown item holds this record
    rather than the bare ``AUTO_ZONE`` sentinel. ``AUTO_ZONE`` says nothing
    about which system Auto chooses in; the frame decides that
    (``job.AUTO_FRAMES``: NAD83(2011) chooses among the SPCS 83 zones,
    NATRF2022 among the SPCS2022 local zones), and with the frame on the item
    the registry-derived graying (#64) answers whether an input frame can
    reach it, with no rule of its own.

    **One entry per Auto frame, and only the one the Options name is shown.**
    An Options change of the Auto frame therefore HIDES the selected entry and
    the strand rule clears it, where a single entry whose data was swapped
    would silently re-target a selection the user made in the other system -
    a different zone, different coordinates, nothing said (recon risk 10).

    Singletons, for the reason ``GeodeticChoice`` gives: ``findData``
    compares by identity. Use ``auto_choice``; never construct one.
    """

    frame: ReferenceFrame

    @property
    def system(self) -> AutoZoneSystem:
        """The zone system this entry chooses among - the core's own pairing."""
        return auto_zone_system(self.frame)

    @property
    def label(self) -> str:
        """What the dropdown calls this choice. Derived, never typed."""
        return auto_label(self.frame)

    def __str__(self) -> str:
        return self.label


def auto_label(frame: ReferenceFrame) -> str:
    """"Auto - zone from latitude/longitude (SPCS 83)" - from the core's records.

    The system's own registry string (``AutoZoneSystem.value``, which is the
    zones' ``Zone.system``), so the label cannot name a system the entry does
    not choose among. The frame is not repeated: only the entry for the
    Options' Auto frame is ever shown, and the Options dialog names the frame.
    """
    return f"Auto - zone from latitude/longitude ({auto_zone_system(frame).value})"


AUTO_CHOICES: tuple[AutoChoice, ...] = tuple(
    AutoChoice(frame=frame) for frame, _system in AUTO_FRAMES
)
"""The canonical Auto selection records, one per ``job.AUTO_FRAMES`` frame,
in that tuple's order (NAD83(2011) first). Singletons."""


def auto_choice(frame: ReferenceFrame) -> AutoChoice:
    """The canonical Auto entry for an Auto frame (by identity), or a refusal."""
    for choice in AUTO_CHOICES:
        if choice.frame is frame:
            return choice
    raise KeyError(
        f"No Auto entry exists for {frame!r}. Auto chooses zones in: "
        + ", ".join(choice.frame.code for choice in AUTO_CHOICES)
        + " (job.AUTO_FRAMES)."
    )


def is_auto(data) -> bool:
    """Whether a zone dropdown's data is an Auto entry. The one predicate."""
    return isinstance(data, AutoChoice)


def auto_units(choice: AutoChoice) -> tuple[LinearUnit, ...]:
    """The units EVERY zone this Auto entry can choose publishes, in the zones' order.

    The intersection, because the unit is chosen before the file is read and
    the job may put a point in any of the zones: an SPCS2022 Auto job offers
    metres and international feet only, never the US survey foot, which no
    SPCS2022 zone publishes. The same intersection ``job``'s Auto unit gate
    states in its refusal (``_require_a_unit_every_auto_zone_publishes``),
    read from ``autozone.zones_choosable`` - the rule's own list.
    """
    zones = zones_choosable(choice.system)
    return tuple(
        unit
        for unit in zones[0].allowed_units
        if all(unit in zone.allowed_units for zone in zones)
    )


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

OFFERED_ZONE_BLOCKS: tuple[tuple[Zone, ...], ...] = (SPCS83_ZONES, SPCS2022_ZONES)
"""The zone blocks every zone dropdown offers, in order, a separator before each.

**THE one statement of which zones reach the interface.** ``zone_combo``
builds its zone rows from it, and the Options groups (``options.LIST_GROUPS``)
are derived from it, so a group can never switch rows that no dropdown holds.

**``UTM_ZONES`` is deliberately absent until work package U5**
(docs/PLAN-utm-epsg.md section 4, DESIGN.md #72): the six UTM records are in
the registry from U1, but no UTM zone may reach a dropdown before the job
record can describe a UTM job (U4) - the #41 rule, disclosure before
reachability, and the H2 precedent of gating the 2022 zones out of the
dropdowns until H5/H6. A pin in tests/test_gui_tabs.py holds the absence.
"""

OFFERED_ZONES: tuple[Zone, ...] = tuple(zone for block in OFFERED_ZONE_BLOCKS for zone in block)
"""Every zone a dropdown offers, in dropdown order. Derived, never written out."""


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


def zone_label(zone: Zone, unit: LinearUnit | None = None) -> str:
    """"Michigan South 2113 - NAD83(2011) (EPSG 6499 ift)" — built from the registry.

    **The frame joins the label at H6**, and it is not decoration: two eras of
    Michigan zone are offered in one dropdown from this release on, the two
    frames are one to two metres apart, and "Michigan South" names a zone in
    each of them (2113 in SPCS 83, and the 2022 design has its own southern
    zones). The number alone distinguishes them only to somebody who knows both
    numbering schemes.

    Derived from the record's own fields — name, code, and the frame's code —
    so a label cannot drift from the mathematics the zone converts through,
    which is the #58 rule applied to the zone entries for the same reason it
    was applied to the geodetic ones. A UTM zone's name is EPSG's own form,
    "NAD83(2011) / UTM zone 16N", which already carries its frame and its
    zone number, so its label is the name (DESIGN.md #72).

    **The EPSG code follows the side's Units box** (the owner's decision D1,
    DESIGN.md #72): given that side's current ``unit``, the code shown is the
    one for the unit the Units box WOULD hold if this zone were chosen -
    ``unit_if_chosen``, the very rule ``refresh_unit_combo`` applies - with
    the unit named, "(EPSG 6499 ift)". No code where EPSG has none (D2): any
    SPCS2022 zone, any NATRF2022 UTM zone, any zone in US survey feet. With
    ``unit`` None the label carries no code at all.
    """
    if zone.system == UTM_SYSTEM:
        title = zone.name
    else:
        title = f"{zone.name} {zone.code} - {zone.frame.code}"
    if unit is None:
        return title
    return f"{title}{zone_label_suffix(zone, unit_if_chosen(zone, unit))}"


def relabel_zone_rows(combo, unit_combo_widget) -> None:
    """Re-render every zone row of a zone dropdown for its side's current unit.

    ``setItemText`` only: no row is added, removed or selected, so no
    ``currentIndexChanged`` fires and no handler runs (DESIGN.md #72, D1).
    Called whenever the side's Units box changes, and once at construction.
    A Units box caught mid-rebuild (``refresh_unit_combo`` clears it, so it
    briefly holds nothing) is skipped; the rebuild's own final selection
    signals again and the rows are re-rendered then.
    """
    unit = unit_combo_widget.currentData()
    if not isinstance(unit, LinearUnit):
        return
    for index in range(combo.count()):
        data = combo.itemData(index)
        if isinstance(data, Zone):
            text = zone_label(data, unit)
            if combo.itemText(index) != text:
                combo.setItemText(index, text)


def connect_zone_labels_to_unit(combo, unit_combo_widget) -> None:
    """Make a zone dropdown's EPSG codes follow its side's Units box, now and on change."""
    unit_combo_widget.currentIndexChanged.connect(
        lambda _index: relabel_zone_rows(combo, unit_combo_widget)
    )
    relabel_zone_rows(combo, unit_combo_widget)


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
    # D3 (DESIGN.md #72): the frame's geographic 2D EPSG code, no unit.
    return f"{frame.code} geodetic (latitude / longitude){frame_label_suffix(frame)}"


def _has_a_transformation(source: ReferenceFrame, target: ReferenceFrame) -> bool:
    """Whether a registered NON-identity path carries ``source`` to ``target``.

    Asked of the frame registry (``frames.require_frame_path``), the same
    function ``job.run`` refuses on, and through
    ``convert.require_an_applicable_path``, the same point ``job.run`` applies
    or refuses a path at - so the interface cannot offer a transformation the
    pipeline would not run. An identity record is not a transformation: the
    same frame at both ends converts nothing.
    """
    try:
        path = require_an_applicable_path(require_frame_path(source, target))
    except FrameMismatchError:
        return False
    return not path.is_identity


def frames_offered(frames=ALL_FRAMES, zones=ALL_ZONES) -> tuple[ReferenceFrame, ...]:
    """Every frame a geodetic entry is offered for, in declaration order.

    Two conditions, both necessary, and each one keeps out a different wrong
    entry:

    * **usable** - ``ALL_FRAMES`` carries the bare WGS 84 label precisely so
      this program can refuse it by name (``frames.FrameNotUsableError``,
      docs/PLAN-wgs84.md decision D2). Offering it would put a label naming no
      realization and no epoch into the dropdown that decides the frame, which
      is the exact mistake #58 was written about;
    * **connected to a zone** - either referenced by at least one registered
      zone, or holding a registered NON-identity path to a frame that is
      (``_has_a_transformation``, which asks the frame registry). A usable
      frame with neither is a frame nothing can be converted INTO or out of,
      so its geodetic entry could only ever pair with the placeholder or with
      itself, and the same frame at both ends is not a conversion
      (``direction_for``). The entry would be a question with no answer.

    **The second branch is work package W5 of the WGS 84 build**
    (docs/PLAN-wgs84.md section 3.7, DESIGN.md #70). The five WGS 84 and ITRF
    frames carry no zone - no State Plane zone is defined on a global frame -
    but each holds an NGS HTDP v3.6.0 path to NAD83(2011), which carries the
    three SPCS 83 zones, so a WGS 84 position can be converted into one of
    them, out of one, or to NAD83(2011) geodetic. Until W5 this rule was
    "carries a zone" alone and kept all five out of every dropdown, which was
    the #41 rule (disclosure before reachability) doing its job while W3 and
    W4 built the arithmetic and the records. Both have landed.

    Derived, so a frame arriving in the registry with zones on it, or with a
    path to one, appears here with no interface change - the ``zone_combo``
    property - and a frame whose status changes to not-usable disappears the
    same way. NATRF2022 against the five is not a path (plan decision D3), and
    neither is one global frame against another (D4); neither is needed for
    the five to be offered, because each reaches NAD83(2011).

    The two registries are parameters defaulting to themselves. Nothing in the
    program passes them: it is a seam for the pin, which has to be able to ask
    this rule about a frame that does not exist - "a usable frame carrying no
    zones is not offered" is a claim about a case the registry does not contain
    today and would otherwise be untestable, which is how a rule ends up being
    believed rather than checked.
    """
    with_zones = {zone.frame.code for zone in zones}
    zoned = [frame for frame in frames if frame.code in with_zones]
    return tuple(
        frame
        for frame in frames
        if frame.is_usable
        and (
            frame.code in with_zones
            or any(_has_a_transformation(frame, other) for other in zoned)
        )
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
            f"must be usable and must carry at least one registered zone, or "
            f"hold a registered transformation to a frame that does)."
        ) from None


def geodetic_choice_groups() -> tuple[
    tuple[GeodeticChoice, ...], tuple[GeodeticChoice, ...]
]:
    """``(plate-fixed choices, time-dependent choices)``, each in declaration order.

    The two blocks ``zone_combo`` separates. Split on the frame record's own
    ``is_time_dependent`` - the question every frame must answer
    (``frames.FrameEpochKind``) - so a frame cannot land in the wrong block by
    being typed into the wrong list.
    """
    return (
        tuple(c for c in GEODETIC_CHOICES if not c.frame.is_time_dependent),
        tuple(c for c in GEODETIC_CHOICES if c.frame.is_time_dependent),
    )


UNANSWERED_TEXT = "— choose —"
"""What every control that opens unanswered shows: the zone dropdowns' and
the vertical datum dropdowns' placeholder, and the observation date's special
value text. One spelling, so a surveyor learns one sign for "not yet
answered" (docs/DESIGN.md amendment #17's one-wording rule)."""


def zone_combo(parent, on_change) -> QComboBox:
    """A zone dropdown, built from the registry. Both eras, since H6.

    Zone names are never typed out here — a zone added to either era tuple
    appears in the list with no interface change (docs/DESIGN.md section 6).

    The order, and why it is this order:

    1. the unanswered placeholder;
    2. one geodetic entry per offered PLATE-FIXED frame - NAD83(2011) and
       NATRF2022 - in ``ALL_FRAMES`` declaration order (``frames_offered``),
       each naming its own datum (#58);
    3. a separator;
    4. one geodetic entry per offered TIME-DEPENDENT frame - the three WGS 84
       realizations and the two ITRFs - in the same declaration order
       (``geodetic_choice_groups``);
    5. a separator;
    6. the two Auto entries (``AUTO_CHOICES``, DESIGN.md #71), one per Auto
       frame - never shown on a FROM combo, and on a TO combo only the one
       for the Options' Auto frame (``options.visible_rows``);
    7. a separator;
    8. ``SPCS83_ZONES``, the three zones every Michigan job has used since
       0.1.0 — first, because they are today's work;
    9. a separator;
    10. ``SPCS2022_ZONES``, the nineteen zones of the modernized design.

    **Every item is always present; the Options HIDE rows** (plan L7/L8,
    ``apply_row_visibility``) rather than rebuilding the list, so every index
    is the same in all four combos whatever is switched on, and a separator
    left between two hidden groups is hidden with them.

    **Items 3 and 4 are work package W5 of the WGS 84 build, and the separator
    between the two geodetic groups is a layout decision for the owner's
    screen review** (docs/PLAN-wgs84.md section 3.7). Its reasons: the five
    global entries are a different KIND of answer from the two above them - a
    position in them means nothing until the date it was observed is stated,
    which is why choosing one asks a further question (the observation date);
    and the commonest wrong pick this build can invite is one row off - the
    NAD83(2011) entry every existing job uses against a WGS 84 realization
    1.3 m away (plan section 6). A rule between the two groups puts a visible
    boundary at exactly that slip. The groups are split by the frame record's
    own ``is_time_dependent``, never by a typed list, and the separator is
    emitted only when the group below it has members, so the list never
    carries an empty block.

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
    combo.addItem(UNANSWERED_TEXT, UNCHOSEN)
    plate_fixed, time_dependent = geodetic_choice_groups()
    for choice in plate_fixed:
        combo.addItem(choice.label, choice)
    if time_dependent:
        combo.insertSeparator(combo.count())
        for choice in time_dependent:
            combo.addItem(choice.label, choice)
    combo.insertSeparator(combo.count())
    # The Auto entries (DESIGN.md #71): "the top option at the top of the SPC
    # zones", the owner's words - in a block of their own, so an Auto entry
    # is never read as one of the SPCS 83 zones beneath it. Present in all
    # four combos so the indexes are the same in every one; HIDDEN on both
    # FROM combos (plan L1, ``options.is_shown``), and on a TO combo only the
    # entry for the Options' Auto frame is shown.
    for choice in AUTO_CHOICES:
        combo.addItem(choice.label, choice)
    for block in OFFERED_ZONE_BLOCKS:
        combo.insertSeparator(combo.count())
        for zone in block:
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
    if is_auto(data):
        return auto_units(data)
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
    preferred = preferred_unit(previous, units)
    combo.setCurrentIndex(combo.findData(preferred))
    return preferred is not previous


def preferred_unit(previous, units) -> LinearUnit:
    """The unit a Units box holds once it offers ``units``: THE one rule.

    The previous selection when it survives, else Michigan's legislated
    international foot when offered, else the first unit offered.
    ``refresh_unit_combo`` applies it, and the zone labels predict with it
    (``unit_if_chosen``), so the EPSG code a dropdown row shows is the code of
    the unit the job will actually use if that row is chosen (DESIGN.md #72).
    """
    units = tuple(units)
    if previous in units:
        return previous
    if INTERNATIONAL_FEET in units:
        return INTERNATIONAL_FEET
    return units[0]


def unit_if_chosen(zone: Zone, current: LinearUnit) -> LinearUnit:
    """The unit a side's Units box would hold if ``zone`` were chosen there."""
    return preferred_unit(current, zone.allowed_units)


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
    combo.addItem(UNANSWERED_TEXT, UNCHOSEN)
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

    Returns None while either side is unanswered, and for the geodetic pairs
    that are not a conversion: geodetic to geodetic with no registered
    transformation between the two frames, which has no zone at either end and
    nothing to project through.

    A zone to ITSELF is deliberately not in that list. It returns
    ``ZONE_TO_ZONE`` and runs, because it is a real job: the units are
    selected independently of the zones, so Michigan South in feet to
    Michigan South in metres is a conversion the surveyor asked for, and
    even the identity case produces the per-point scale, convergence and
    combined factors that the audit CSV and the job record exist to report.

    **Geodetic to geodetic is ``GEODETIC_TO_GEODETIC`` exactly when the frame
    registry holds a NON-identity transformation between the two frames**
    (docs/PLAN-wgs84.md decision D7, work package W5) - the ten NGS HTDP paths
    between NAD83(2011) and the five WGS 84 and ITRF frames, which is HTDP's
    own core use and the conversion most people asking for "WGS 84" need. Asked
    of the registry (``_has_a_transformation``), never of a list here.

    SUPERSEDES H6's "geodetic to geodetic returns None whatever the two frames
    are", which was true while no transformation existed. It still returns
    None for every other geodetic pair, and each for the reason it always had:

    * the same frame at both ends - an identity converts nothing;
    * NAD83(2011) against NATRF2022 - reads like a datum transformation and is
      not one this program has; the frame bridge is unpublished (DESIGN.md
      #62);
    * a WGS 84 or ITRF frame against NATRF2022 (plan decision D3) - HTDP does
      not carry NATRF2022;
    * one global frame against another (plan decision D4) - no zone lives on
      either, and refusing that neighbouring problem is a recorded decision.

    None there means the pair describes no job and Convert is not offered; the
    graying (``selection_is_compatible``) already keeps the user from choosing
    it, from the same registry.

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
    if is_auto(source_data):
        # Plan L1: a northing and easting do not say which zone they are in,
        # so Auto is never an input. Hidden on the FROM combos; reachable only
        # programmatically, and then it describes no job.
        return None
    if is_auto(target_data):
        # Auto chooses a zone from a latitude and longitude, so only a
        # geodetic FROM makes it a job (the entry is grayed otherwise).
        return Direction.GEODETIC_TO_ZONE if is_geodetic(source_data) else None
    if is_geodetic(source_data) and is_geodetic(target_data):
        if _has_a_transformation(source_data.frame, target_data.frame):
            return Direction.GEODETIC_TO_GEODETIC
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
        f"geodetic entry, nor an Auto entry, nor a zone. Every item zone_combo "
        f"offers is one of those four; the separators are not selectable and "
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

AUTO_RESET_STATUS = "Cleared: Auto zone needs a latitude/longitude input."
"""Shown when an Auto TO selection is cleared because the FROM end moved to
something that is not a latitude/longitude (plan L1). One sentence, in
``FRAME_RESET_STATUS``'s form: that the program cleared it, and why."""

OPTIONS_RESET_STATUS = "Cleared: that entry is switched off in Options."
"""Shown when an Options change hides the entry a dropdown held (plan L8) -
including an Auto entry whose frame the Options no longer choose. The
``FRAME_RESET_STATUS`` form again: cleared by the program, and why."""


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
    if is_auto(data):
        # Every zone an Auto entry can choose is defined on its frame
        # (job._check_auto_frames refuses to import otherwise), so the frame
        # IS what that TO end is expressed in.
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

    **And through the same point ``job.run`` applies or refuses a path**
    (``convert.require_an_applicable_path``, docs/PLAN-wgs84.md work package
    W3): the registry returns NGS HTDP records for NAD83(2011) against the
    WGS 84 and ITRF frames, and since W3 the conversion pipeline applies them,
    so this answers True for those pairs exactly as ``job.run`` accepts them
    (a WGS 84 position into an SPCS 83 zone, an SPCS 83 zone out to WGS 84) -
    and False for a registered path whose method the pipeline could not run.
    Under W2 it answered False for all ten, because the guard then refused
    them. Since work package W5 the five frames are offered in the dropdowns
    (``frames_offered``), so this answer is now what grays - or leaves
    choosable - every pairing of a WGS 84 or ITRF entry.
    """
    try:
        require_an_applicable_path(require_frame_path(source, target))
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
    return (
        incompatibility(candidate, other, candidate_is_source=candidate_is_source)
        is None
    )


def incompatibility(candidate, other, *, candidate_is_source: bool) -> str | None:
    """Why ``candidate`` cannot be paired with ``other``, as its status line, or None.

    ``selection_is_compatible``'s rule with its reason, so a cleared selection
    says the true one of two (DESIGN.md #71):

    * ``AUTO_RESET_STATUS`` - an Auto entry at the TO end with a FROM end that
      is not a latitude/longitude, or an Auto entry at the FROM end at all
      (plan L1: Auto chooses a zone from a latitude/longitude, and a
      northing/easting does not say which zone it is in);
    * ``FRAME_RESET_STATUS`` - the frame registry has no path between the two
      frames (#64). An Auto entry's frame is its Auto frame, so NAD83(2011)
      input against Auto on NATRF2022 grays and clears exactly as it does
      against an SPCS2022 zone (plan L2) - and dissolves by itself the same
      way when a bridge is registered.

    Nothing is incompatible with the unanswered placeholder or a separator,
    and the placeholder is incompatible with nothing.
    """
    if other == UNCHOSEN or candidate == UNCHOSEN:
        return None
    if candidate is None or other is None:
        return None
    source, target = (candidate, other) if candidate_is_source else (other, candidate)
    if is_auto(source):
        return AUTO_RESET_STATUS
    if is_auto(target) and not is_geodetic(source):
        return AUTO_RESET_STATUS
    candidate_frame = frame_of(candidate)
    other_frame = frame_of(other)
    if candidate_frame is None or other_frame is None:
        return None
    if candidate_is_source:
        allowed = frames_have_a_path(candidate_frame, other_frame)
    else:
        allowed = frames_have_a_path(other_frame, candidate_frame)
    return None if allowed else FRAME_RESET_STATUS


def refresh_zone_graying(combo, other, *, is_source: bool, visible=None) -> None:
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

    **``visible`` - the Options' row visibility (``options.visible_rows``),
    one flag per index; None means every row is shown.** A hidden row is
    DISABLED here as well as hidden by ``apply_row_visibility``, and that is
    measured Qt behaviour, not belt and braces: ``QListView.setRowHidden``
    hides a row from the popup only, while the closed combo's arrow keys and
    mouse wheel step through every ENABLED item, hidden or not - so a
    switched-off WGS 84 entry would be one Down-arrow away without this
    (pinned in tests/test_gui_options.py). Folded into this one owner of the
    flags (the #57 rule) rather than set by a second method.
    """
    model = combo.model()
    for index in range(combo.count()):
        data = combo.itemData(index)
        if data is None:
            # A separator. It carries no data, no flags and no meaning.
            continue
        item = model.item(index)
        allowed = (visible is None or visible[index]) and selection_is_compatible(
            data, other, candidate_is_source=is_source
        )
        flags = item.flags()
        if allowed:
            item.setFlags(flags | Qt.ItemFlag.ItemIsEnabled)
        else:
            item.setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled)


def combo_items(combo) -> tuple:
    """Every item's data in a combo, in index order - separators as None."""
    return tuple(combo.itemData(index) for index in range(combo.count()))


def apply_row_visibility(combo, visible) -> None:
    """Hide the popup rows the Options switch off; one flag per index.

    ``setRowHidden`` on the combo's own list view, never a rebuild: the items
    and their indexes stay exactly where ``zone_combo`` put them, so every
    ``findData`` and every index a method holds stays valid, and a hidden
    selection cannot silently turn into a different item. The flags that keep
    a hidden row out of keyboard and wheel stepping are
    ``refresh_zone_graying``'s (its ``visible``). Each tab calls this from one
    method only (the #57 rule, AST-pinned).
    """
    visible = tuple(visible)
    if len(visible) != combo.count():
        raise ValueError(
            f"Row visibility for {len(visible)} rows was applied to a dropdown "
            f"holding {combo.count()}; the flags must come from this combo's "
            f"own items (combo_items)."
        )
    view = combo.view()
    for index, shown in enumerate(visible):
        view.setRowHidden(index, not shown)


def geodetic_frame_for(*sides) -> ReferenceFrame | None:
    """The frame this job's geodetic END is in, or None if it has none.

    What ``JobSettings.geodetic_frame`` is threaded from, on both tabs. The
    sides are passed in the order the tab reads them - source then target,
    or source alone in vertical-only mode - and the first geodetic one
    answers.

    First-wins is the rule, and since work package W5 it is load-bearing
    rather than incidental: the only pair with two geodetic sides is
    ``GEODETIC_TO_GEODETIC``, whose ``geodetic_frame`` is the INPUT frame - the
    source, which is read first - and whose output frame both tabs state
    separately as ``target_geodetic_frame`` (``target_geodetic_frame_for``).

    None means "no end of this job is geodetic", which is a zone-to-zone job:
    ``geodetic_frame`` is unread there, and the settings keep their default
    rather than being told something the job never consults.
    """
    for data in sides:
        if is_geodetic(data):
            return data.frame
    return None


def target_geodetic_frame_for(direction, target_data) -> ReferenceFrame | None:
    """The OUTPUT frame of a geodetic-to-geodetic job, and None for every other.

    What ``JobSettings.target_geodetic_frame`` is threaded from, on both tabs.
    The core requires it on ``GEODETIC_TO_GEODETIC`` and refuses it by name on
    every other direction - a second geodetic frame stated beside a job with
    one geodetic end is a frame the record could print and the conversion
    never used - so this answers None unless the direction is that one.
    """
    if direction is Direction.GEODETIC_TO_GEODETIC and is_geodetic(target_data):
        return target_data.frame
    return None


def combined_factor_is_reported(direction, source_data) -> bool:
    """Whether the job this form describes reports a combined scale factor.

    What the two horizontal elevation hints ask before naming it - the Single
    point placeholder (#57) and the Multi point note (#48), both "used for
    combined scale factor". A job with no State Plane zone has no grid scale
    factor and so no combined factor, and a hint promising one there is a
    false sentence on screen: the W4b class on the record, and interim gate 2's
    H2, reaching the interface through the GEODETIC_TO_GEODETIC direction W5
    makes reachable (the lead's finding on the W5 screenshots).

    Asked of ``job.is_zoneless``, the rule the job record withholds its
    zone-only sentences on, so the screen and the record cannot disagree about
    which jobs have a zone. ``direction`` None - a form not yet describing a
    job - answers True: the hint keeps the owner's wording until the
    selections say otherwise, exactly as it opens.
    """
    if direction is None:
        return True
    source_zone = source_data if isinstance(source_data, Zone) else None
    return not is_zoneless(direction, source_zone)


def longitude_is_relevant(direction) -> bool:
    """The selector matters only when geodetic coordinates are involved."""
    return direction in (
        Direction.GEODETIC_TO_ZONE,
        Direction.ZONE_TO_GEODETIC,
        Direction.GEODETIC_TO_GEODETIC,
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


OBSERVATION_DATE_LABEL = "Observation date:"

OBSERVATION_DATE_FORMAT = "yyyy-MM-dd"
"""How the date control shows a date: ISO 8601, year first.

Not the platform's short date. ``03/04/2025`` is the 4th of March to one
reader and the 3rd of April to another, and a date read the wrong way round
is a position moved by a month of plate motion with nothing on screen to
show it. ``2025-03-04`` reads one way only, and it is the form the job
record and the audit CSV print the date in (``datetime.date.isoformat``), so
the screen and the files spell it identically (#17)."""

OBSERVATION_DATE_UNANSWERED = QDate(1752, 9, 14)
"""The sentinel the date control holds while it is unanswered.

Qt's own default minimum date for a ``QDateTimeEdit``. It is set as the
control's MINIMUM, which is what makes Qt show ``UNANSWERED_TEXT`` in place
of a date (``QAbstractSpinBox.specialValueText`` is shown exactly when the
value equals the minimum) - so the unanswered state is not a date that might
be mistaken for one: no date is displayed at all. ``observation_date_for``
reads this value as None, and no real date can equal it, because every date
the control can hold is at or after the minimum and only the minimum itself is
the sentinel.

Every date after it can be chosen. The core refuses what HTDP cannot compute
(a year before 1907, in HTDP's own words) and what has not happened yet (a
date after the day the job runs), and the interface shows those refusals
rather than pre-empting them with a second rule (docs/PLAN-wgs84.md decision
D9)."""


class _CalendarOpensOnToday(QObject):
    """Opens an unanswered date control's calendar on this month's page.

    Left alone, Qt opens the calendar on the page of the control's current
    value - September 1752, the sentinel - and a surveyor would page forward
    nearly three centuries to reach his job. This moves the PAGE shown and
    nothing else: no date is selected, the control stays unanswered, and
    closing the calendar without clicking a day leaves it unanswered. Today is
    where the page opens, never what the control holds (the brief's rule, and
    the longitude convention's core rule: no default answer).

    "Today" is ``job.today`` - the later of the local and UTC dates, the same
    clock the core's future-date refusal reads - so the page shown and the
    refusal cannot disagree about which month is current.
    """

    def __init__(self, edit) -> None:
        super().__init__(edit)
        self._edit = edit

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt's name
        if event.type() == QEvent.Type.Show and not self._edit.is_answered():
            today = job_module.today()
            watched.setCurrentPage(today.year, today.month)
        return False


class ObservationDateEdit(QDateEdit):
    """The observation date control: a calendar date, opening unanswered.

    A native ``QDateEdit`` with its calendar popup (the owner's decision 3:
    the epoch is entered as a calendar date), shown in ISO form
    (``OBSERVATION_DATE_FORMAT``), and opening on ``OBSERVATION_DATE_UNANSWERED``
    so that it displays ``UNANSWERED_TEXT`` and holds no date at all.

    **No default date, and that is the whole care this control needs**
    (docs/PLAN-wgs84.md section 3.7). A Michigan point moves about 17 mm a
    year against NAD 83 in a WGS 84 or ITRF frame, so a date is a fact about
    the data, and a preselected one - today's, say - would be an answer to a
    question the surveyor was never asked, wrong by a year's motion for a
    year-old file and looking exactly like a right one. The longitude
    convention's core rule (docs/DESIGN.md section 7), applied here without
    #29's exception.

    **Three things are changed from the stock widget, and only in the
    unanswered state**, each because the stock behaviour there would answer
    the question or appear to:

    * stepping is off - the Up and Down keys, Page Up and Down, the wheel and
      the context menu's Step items would otherwise step the sentinel's YEAR
      section to 1753-09-14, a plausible-looking date nobody chose;
    * typed keys are swallowed - Qt appends them to the placeholder text
      ("— choose —2025") without ever reading them as a date, so the box
      would show something resembling an answer while holding none;
    * the calendar opens on this month's page (``_CalendarOpensOnToday``).

    **Shown only when the Options say "Enter a date on the tab"** (plan O3,
    DESIGN.md #71). With the default, "Today", there is no date box on either
    tab and the job is dated ``job.today_local()`` with the source stated as
    TODAY, which the record prints - the reversal of D10's no-default rule,
    on the owner's instruction, for that choice only. Under "Enter a date"
    everything below holds unchanged, and the box opens unanswered at every
    start: the date is never remembered.

    So the first answer comes from the calendar. Once answered, the control is
    the stock widget: each section can be typed over or stepped, and the
    calendar opens on the date chosen. Measured on the offscreen platform and
    pinned (tests/test_gui_wgs84.py).
    """

    def is_answered(self) -> bool:
        """Whether a date has been chosen (anything but the sentinel)."""
        return self.date() != self.minimumDate()

    def stepEnabled(self):  # noqa: N802 - Qt's name
        if not self.is_answered():
            return QAbstractSpinBox.StepEnabledFlag.StepNone
        return super().stepEnabled()

    def stepBy(self, steps: int) -> None:  # noqa: N802 - Qt's name
        if not self.is_answered():
            return
        super().stepBy(steps)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt's name
        if not self.is_answered():
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt's name
        if not self.is_answered():
            # Handed on, so a wheel over the unanswered box scrolls whatever
            # contains it rather than stepping a date into existence.
            event.ignore()
            return
        super().wheelEvent(event)


def observation_date_edit(parent, on_change) -> ObservationDateEdit:
    """The observation date control, one per tab, opening unanswered.

    Built here so both tabs get the *same* control - the ``longitude_combo``
    rule - and the handler is passed in because the tabs share no state
    (docs/DESIGN.md amendment #26). It rides ``dateChanged``, which fires
    exactly once per change of the held date, from the calendar, a typed
    section or a step alike.
    """
    edit = ObservationDateEdit(parent)
    edit.setDisplayFormat(OBSERVATION_DATE_FORMAT)
    edit.setCalendarPopup(True)
    edit.setMinimumDate(OBSERVATION_DATE_UNANSWERED)
    edit.setSpecialValueText(UNANSWERED_TEXT)
    # Set BEFORE the connection, so building the control does not fire the
    # handler on a tab that is still constructing itself.
    edit.setDate(OBSERVATION_DATE_UNANSWERED)
    calendar = edit.calendarWidget()
    calendar.installEventFilter(_CalendarOpensOnToday(edit))
    # NO TOOLTIP (#34, #51): the label and the unanswered text are the whole
    # control.
    edit.dateChanged.connect(on_change)
    return edit


def observation_date_for(edit) -> datetime.date | None:
    """The date the control holds, or None while it is unanswered.

    The sentinel is None, never a date: ``OBSERVATION_DATE_UNANSWERED`` is how
    the control says "not yet", and a reader that returned it as 1752-09-14
    would hand the core a date nobody chose. Refuses a control that is not the
    one ``observation_date_edit`` builds rather than guessing how its
    "unanswered" is spelled - the ``height_kind_for`` contract.
    """
    if not isinstance(edit, ObservationDateEdit):
        raise TypeError(
            f"observation_date_for needs the control observation_date_edit "
            f"builds; got {type(edit).__name__}. Another date widget has no "
            f"unanswered state this function knows how to read, and a "
            f"guessed one would send the core a date nobody chose."
        )
    if not edit.is_answered():
        return None
    value = edit.date().toPython()
    if isinstance(value, datetime.datetime) or not isinstance(value, datetime.date):
        raise TypeError(
            f"The date control returned {type(value).__name__} ({value!r}) "
            f"where a datetime.date was expected."
        )
    return value


def observation_date_relevance(mode, source_data, target_data) -> bool:
    """Whether the observation date governs anything right now.

    True exactly when a SELECTED side's frame is time-dependent - a WGS 84
    realization or an ITRF, asked of the frame record (``frame_of`` and
    ``ReferenceFrame.is_time_dependent``), never of a list of names. Zones are
    never time-dependent: no zone is defined on a global frame.

    In vertical-only mode the To dropdown is hidden and no output system
    exists, so only the From selection counts - the ``longitude_relevance``
    rule for the same mode. A hidden To selection must not ask for a date.

    The core is the authority and asks the same question of the PATH
    (``job._time_dependent_frames_read``): it requires a date when the path
    reads a time-dependent frame and refuses one by name when it does not. So
    this decides two things only - whether the control is enabled, and whether
    the tab sends its value - and the tab sends nothing when this is False,
    which is what keeps a stray date out of a job that reads none.
    """
    sides = (
        (source_data,) if mode is VerticalMode.VERTICAL else (source_data, target_data)
    )
    for data in sides:
        frame = frame_of(data)
        if frame is not None and frame.is_time_dependent:
            return True
    return False


def frame_settings_fields(
    mode, direction, source_data, target_data, date_edit, date_source
):
    """The WGS 84 build's two settings fields this form states, or None if incomplete.

    One rule for both tabs (work package W5), so they cannot thread the fields
    differently:

    * ``target_geodetic_frame`` - stated only on ``GEODETIC_TO_GEODETIC``
      (``target_geodetic_frame_for``), the one direction with two geodetic
      ends. Every other direction leaves it at None, its default, which the
      core requires there.
    * ``observation_date`` and ``observation_date_source`` - stated only when
      a selected side's frame is time-dependent (``observation_date_relevance``),
      and then always together. Otherwise both are left at None, because the
      core refuses a date, or a source, stated for a job that reads none (a
      stray field would print an epoch into a record of a conversion that
      used none).

    **Where the date comes from is the Options' choice** (plan O3 and L10,
    DESIGN.md #71), passed in as ``date_source``:

    * ``ObservationDateSource.TODAY`` (the default) - ``job.today_local()``,
      the LOCAL calendar date the job runs, never ``job.today``'s
      later-of-local-and-UTC, which exists only so that a date that is today
      in either clock is not refused as future: a Michigan evening is already
      tomorrow in UTC, and the record would print that as "the date the job
      ran". Read when ``settings()`` is assembled, which is when Convert runs
      it. The date box is hidden and not read.
    * ``ObservationDateSource.ENTERED`` - the date box, REQUIRED: unanswered
      returns None, so ``settings()`` returns None and Convert is not offered
      (the WGS 84 build's gating, W5, kept).

    Returns a dict to merge into the ``JobSettings`` keyword arguments.
    """
    if not isinstance(date_source, ObservationDateSource):
        raise TypeError(
            f"frame_settings_fields needs the Options' ObservationDateSource "
            f"(TODAY or ENTERED); got {type(date_source).__name__} "
            f"({date_source!r}). Guessing one would decide where every "
            f"time-dependent position's date comes from."
        )
    fields: dict = {}
    target_frame = target_geodetic_frame_for(direction, target_data)
    if target_frame is not None:
        fields["target_geodetic_frame"] = target_frame
    if observation_date_relevance(mode, source_data, target_data):
        if date_source is ObservationDateSource.TODAY:
            date = job_module.today_local()
        else:
            date = observation_date_for(date_edit)
            if date is None:
                return None
        fields["observation_date"] = date
        fields["observation_date_source"] = date_source
    return fields


def _points(count: int) -> str:
    """"1 point" or "3 points"."""
    return f"{count} point" if count == 1 else f"{count} points"


def refusal_headline(error: BaseException) -> str | None:
    """A one-line headline for a refusal, or None to show the refusal as raised.

    The owner's instruction, 2026-10-29 (DESIGN.md #73): the Auto refusal is
    to read as "a simple one line 'coordinates out of range' or something
    like that". Only that refusal has a headline. Every other refusal is
    shown exactly as raised, as it always was.

    The headline is chosen from the error's DATA, never from its message
    text, and it says only what is true of every point it counts: "outside
    Michigan" when every unplaced point is in no Michigan county
    (``outside_count``), otherwise a wording that also covers a point two
    county polygons claim. The full refusal, naming each point, stays one
    click away in the dialog's details and in the status line's tooltip.
    """
    if not isinstance(error, AutoZoneUnplacedPointsError):
        return None
    total = len(error.points)
    if error.outside_count == total:
        verb = "is" if total == 1 else "are"
        return f"Coordinates out of range: {_points(total)} {verb} outside Michigan."
    if error.outside_count == 0:
        verb = "lies" if total == 1 else "lie"
        return (
            f"Auto could not choose a zone: {_points(total)} {verb} where two "
            f"counties overlap."
        )
    return (
        f"Auto could not choose a zone: {_points(total)} could not be placed in "
        f"one Michigan county."
    )


def refusal_status(error: BaseException) -> str:
    """The status line's text for a refusal, on both tabs.

    "Refused: " and the headline when the refusal has one, else the first
    line of the message as raised - one rule, so the two tabs cannot word
    the same refusal differently.
    """
    headline = refusal_headline(error)
    if headline is not None:
        return f"Refused: {headline}"
    message = str(error) or repr(error)
    return f"Refused: {message.splitlines()[0]}"


def show_failure_dialog(parent, error: BaseException, title: str) -> None:
    """The failure dialog. Overridden in tests, which cannot answer a modal."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(f"{title} — conversion refused")
    # Plain text for the same reason the status line is: these messages
    # quote file content back, and no part of a refusal may be rendered
    # away as markup.
    box.setTextFormat(Qt.TextFormat.PlainText)
    fill_failure_dialog(box, error)
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    box.exec()


FAILURE_INFORMATIVE_TEXT = (
    "Nothing was written. This message names the problem exactly; it is "
    "not a summary."
)


def fill_failure_dialog(box: QMessageBox, error: BaseException) -> None:
    """Put a refusal into the failure dialog. Separate so the suite can read it.

    A refusal with a headline (``refusal_headline``) shows the headline
    alone, and its full message - every point it names - under Show
    Details. There is no informative line on that box: "it is not a summary"
    would be false of a headline. Every other refusal is unchanged: the full
    message, the informative line, and the traceback under Show Details.
    """
    headline = refusal_headline(error)
    if headline is not None:
        box.setText(headline)
        box.setInformativeText("")
        box.setDetailedText(str(error))
        return
    box.setText(str(error) or repr(error))
    box.setInformativeText(FAILURE_INFORMATIVE_TEXT)
    box.setDetailedText(
        "".join(traceback.format_exception(type(error), error, error.__traceback__))
    )
