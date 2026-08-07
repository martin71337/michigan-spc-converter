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
from PySide6.QtWidgets import QComboBox, QMessageBox

from michspc.job import Direction, LongitudeConvention
from michspc.spc.units import ALL_UNITS, INTERNATIONAL_FEET
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


def longitude_combo(parent, on_change) -> QComboBox:
    """The longitude sign convention dropdown, which opens unanswered.

    The placeholder is the point: the two conventions are indistinguishable from
    the numbers alone, so this control must not open on either of them
    (docs/DESIGN.md section 7).
    """
    combo = QComboBox(parent)
    combo.addItem("— choose —", UNCHOSEN)
    for convention in LongitudeConvention:
        combo.addItem(convention.value, convention)
    combo.setToolTip(
        "A Michigan longitude of 84 deg 22 min W is written -84.37 under the "
        "negative-west convention and 84.37 under the positive-west one. The "
        "two are indistinguishable from the numbers alone, and choosing "
        "wrongly moves the point about 340 miles. There is deliberately no "
        "default.\n\n"
        "Degrees-minutes-seconds entry does not depend on this: a hemisphere "
        "letter states the direction outright."
    )
    """The worked example moved here from the entries themselves at the owner's
    request (docs/DESIGN.md amendment #28). It taught the person choosing, but
    it rode the enum value into the job record's Longitude line as well, and
    "positive west" alone names the convention completely."""
    combo.currentIndexChanged.connect(on_change)
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
