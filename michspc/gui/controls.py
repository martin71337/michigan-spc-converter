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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QComboBox, QMessageBox, QRadioButton

from michspc.fileio import geoid
from michspc.job import Direction, LongitudeConvention, VerticalMode
from michspc.spc.units import ALL_UNITS, INTERNATIONAL_FEET
from michspc.spc.vertical import ALL_VERTICAL_DATUMS, VerticalDatum
from michspc.spc.zones import ALL_ZONES, Zone

UNCHOSEN = "unchosen"
"""Sentinel for a dropdown the user has not answered yet.

Not the same thing as a default. A combo box that opens on a real value has
answered a question the user was never asked, which is precisely the failure the
longitude convention rule exists to prevent, so the zone and convention combos
open on a placeholder and Convert stays disabled until they are answered.
"""

GEODETIC = "geodetic"
"""Sentinel for "this side of the conversion is latitude/longitude, not a zone".

Carried in the same dropdown as the zones because the direction of a job is
exactly the question "what is it coming from, and what is it going to" — the
program converts zone to zone, geodetic to zone, and zone to geodetic
(docs/DESIGN.md section 2), and one pair of dropdowns states all three.
"""

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
    """"Michigan South 2113" — built from the registry, never typed out."""
    return f"{zone.name} {zone.code}"


def zone_combo(parent, on_change) -> QComboBox:
    """A zone dropdown, built from the registry.

    Zone names are never typed out here — a zone added to
    ``michspc.spc.zones.ALL_ZONES`` appears in this list with no interface
    change (docs/DESIGN.md section 6).

    The change handler is passed in rather than hard-wired, so each tab connects
    its own — the tabs share no state (docs/DESIGN.md amendment #26).
    """
    combo = QComboBox(parent)
    combo.addItem("— choose —", UNCHOSEN)
    combo.addItem("Geodetic (latitude / longitude)", GEODETIC)
    for zone in ALL_ZONES:
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
"""The mode toggle's two captions (docs/PLAN-vertical-datums.md section 4.1).

"Horizontal" is today's job, exactly - no vertical datum is asked for and
nothing is tagged. "Horizontal + Vertical" additionally converts every
elevation between the two vertical datums the revealed dropdowns name. The
toggle opens on Horizontal because that asserts nothing about a vertical
datum; it is a starting state, not an answer to the datum question, which the
two dropdowns still refuse to assume.
"""

VERTICAL_SOURCE_LABEL = "Vertical datum from:"
VERTICAL_TARGET_LABEL = "Vertical datum to:"

GEOID_MODEL_LABEL = "Geoid model:"


def vertical_mode_buttons(
    parent, on_change
) -> tuple[QRadioButton, QRadioButton, QButtonGroup]:
    """The Horizontal / Horizontal + Vertical toggle, one per tab.

    Two ``QRadioButton``s in an exclusive ``QButtonGroup`` - the repo's
    existing idiom (``elevation_in_file``), native per METHOD.md section 5.
    Built here so both tabs get the *same* control rather than a lookalike
    pair, exactly as ``longitude_combo`` serves them both; the handler is
    passed in because the tabs share no state (docs/DESIGN.md amendment #26)
    and each connects its own.

    Opens on Horizontal (plan section 4.1): today's behaviour, asserting
    nothing about a vertical datum.

    Only the Horizontal button's ``toggled`` signal carries the handler. The
    two buttons are exclusive, so every mode change toggles BOTH - connecting
    both would fire the handler twice per click, and connecting one is exactly
    once. The handlers this reaches are idempotent either way; once is simply
    the honest count.
    """
    horizontal = QRadioButton(HORIZONTAL_MODE_TEXT, parent)
    vertical = QRadioButton(VERTICAL_MODE_TEXT, parent)
    group = QButtonGroup(parent)
    group.addButton(horizontal)
    group.addButton(vertical)
    horizontal.setChecked(True)
    horizontal.toggled.connect(on_change)
    return horizontal, vertical, group


def vertical_mode_for(
    horizontal: QRadioButton, vertical: QRadioButton
) -> VerticalMode:
    """The mode a tab's toggle currently states.

    The rule lives here, beside the builder, so the two tabs cannot read the
    same pair of buttons two different ways. Exactly one button is checked at
    all times - the group is exclusive and the builder checks Horizontal - so
    the neither-checked branch below is unreachable through the interface; it
    refuses rather than guessing because a mode guessed here would silently
    decide whether elevations are converted.
    """
    if horizontal.isChecked():
        return VerticalMode.HORIZONTAL
    if vertical.isChecked():
        return VerticalMode.HORIZONTAL_AND_VERTICAL
    raise ValueError(
        "Neither mode button is checked, so the vertical mode is unknown. "
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
    """
    if source_data == UNCHOSEN or target_data == UNCHOSEN:
        return None
    if source_data == GEODETIC and target_data == GEODETIC:
        return None
    if source_data == GEODETIC:
        return Direction.GEODETIC_TO_ZONE
    if target_data == GEODETIC:
        return Direction.ZONE_TO_GEODETIC
    return Direction.ZONE_TO_ZONE


def longitude_is_relevant(direction) -> bool:
    """The selector matters only when geodetic coordinates are involved."""
    return direction in (
        Direction.GEODETIC_TO_ZONE,
        Direction.ZONE_TO_GEODETIC,
    )


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
