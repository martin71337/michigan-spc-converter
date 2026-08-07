"""One latitude or longitude, typed as degrees, minutes, seconds and a letter.

Four boxes with the symbols already between them, so the surveyor types only
the numbers he is reading off — the owner's shape (docs/DESIGN.md amendment
#28). It mirrors what the results panel displays: ``84°22'00.53675"W`` typed
back in is 84, 22, 00.53675, W, which makes the screen and the entry form two
views of one notation rather than two notations.

**This widget never computes an angle.** It hands its four strings to
``michspc.fileio.dms``, which owns the arithmetic and every refusal, for the
same reason the rest of ``michspc.gui`` never produces a domain value. Nothing
here rounds, defaults or combines anything.

**No validator on any box**, for the reason ``single_point`` states at length:
a ``QValidator`` is a second validation gate that rejects silently, and this
program's refusals are meant to arrive as sentences that name the offending box.
Non-numeric text travels to ``fileio.dms`` and comes back as its own message.

**The hemisphere opens unanswered.** It is the one component that is not a
number, and it decides which side of the meridian the point is on. A dropdown
that opened on "W" would answer that for the user — right for Michigan, and
wrong the first time this is used on anything else, with nothing on screen
saying a choice had been made. Convert stays disabled until it is set, exactly
as it does for the zones and the longitude convention.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QWidget

from michspc.fileio import dms
from michspc.gui.controls import UNCHOSEN

DEGREE_SYMBOL = "°"
MINUTE_SYMBOL = "'"
SECOND_SYMBOL = '"'

DEGREES_WIDTH = 52
MINUTES_WIDTH = 46
SECONDS_WIDTH = 92
"""Box widths in logical pixels, sized to their contents rather than stretched.

Seconds is the widest because it is the only one that carries a fraction, and
the panel shows five decimal places. Fixed widths are what make the row read as
one angle instead of three unrelated fields.
"""

HEMISPHERE_PLACEHOLDER = "—"
"""What the hemisphere dropdown shows before it is answered. Shorter than the
"— choose —" the zone combos use because it sits in a narrow box at the end of
a row, and the row's own label already says which angle it belongs to."""


class DmsEntry(QWidget):
    """Degrees / minutes / seconds / hemisphere for one axis."""

    def __init__(self, axis: str, parent=None, on_change=None) -> None:
        """``axis`` is ``dms.LATITUDE`` or ``dms.LONGITUDE``.

        It decides which two letters the dropdown offers, and it is passed
        straight through to ``fileio.dms`` so every refusal names the right
        angle. ``on_change`` is called whenever any box changes — the tab wires
        it to the same invalidation the decimal boxes use, so a half-edited
        angle cannot leave a converted result standing on screen.
        """
        super().__init__(parent)
        self.axis = axis

        self.degrees = QLineEdit(self)
        self.minutes = QLineEdit(self)
        self.seconds = QLineEdit(self)
        self.degrees.setFixedWidth(DEGREES_WIDTH)
        self.minutes.setFixedWidth(MINUTES_WIDTH)
        self.seconds.setFixedWidth(SECONDS_WIDTH)

        self.hemisphere = QComboBox(self)
        self.hemisphere.addItem(HEMISPHERE_PLACEHOLDER, UNCHOSEN)
        for letter in dms.HEMISPHERES[axis]:
            self.hemisphere.addItem(letter, letter)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        for box, symbol in (
            (self.degrees, DEGREE_SYMBOL),
            (self.minutes, MINUTE_SYMBOL),
            (self.seconds, SECOND_SYMBOL),
        ):
            row.addWidget(box)
            row.addWidget(QLabel(symbol, self))
        row.addWidget(self.hemisphere)
        row.addStretch(1)

        if on_change is not None:
            for box in (self.degrees, self.minutes, self.seconds):
                box.textChanged.connect(on_change)
            self.hemisphere.currentIndexChanged.connect(on_change)

    # ------------------------------------------------------------------
    # What was typed
    # ------------------------------------------------------------------

    def hemisphere_letter(self) -> str:
        """The chosen letter, or "" while the dropdown is unanswered.

        Empty rather than None so it can be handed to ``fileio.dms`` unchanged
        — which refuses it, by name, exactly as it refuses a wrong letter. The
        interface does not need a second opinion about what a valid letter is.
        """
        data = self.hemisphere.currentData()
        return data if isinstance(data, str) and data != UNCHOSEN else ""

    def is_complete(self) -> bool:
        """Every box answered. Says nothing about whether they are READABLE.

        This gates the Convert button, and gating is all it does: whether 61
        minutes is a legal angle is ``fileio.dms``'s question, and asking it
        here as well would put a second rule about angles in the interface.
        """
        return bool(
            self.degrees.text().strip()
            and self.minutes.text().strip()
            and self.seconds.text().strip()
            and self.hemisphere_letter()
        )

    def decimal_degrees_text(self, *, positive_west: bool) -> str:
        """The four boxes as decimal-degree text, or raise ``dms.DmsError``."""
        return dms.decimal_degrees_text(
            self.degrees.text(),
            self.minutes.text(),
            self.seconds.text(),
            self.hemisphere_letter(),
            axis=self.axis,
            positive_west=positive_west,
        )

    def clear(self) -> None:
        """Empty every box and unanswer the hemisphere."""
        for box in (self.degrees, self.minutes, self.seconds):
            box.clear()
        self.hemisphere.setCurrentIndex(0)
