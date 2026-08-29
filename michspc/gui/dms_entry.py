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

**The hemisphere opens on N and W** — the owner's decision, taken after using
the unanswered version (docs/DESIGN.md amendment #28 note 3). It was built to
open on a placeholder, on the house rule that nothing answers a question for the
user; he judged the two extra clicks per conversion not worth it, and he is
right about his own data.

What makes this defensible where a longitude-convention default would not be:
**the answer is on the screen, in the box, before Convert is pressed.** The
convention has no default because its two options are indistinguishable from the
numbers — nothing on screen tells you which one is in force. A hemisphere letter
is a visible token beside the angle it belongs to, and it reads back in the
result panel as well. It is a starting value, not a hidden assumption.

It is also right for every point this program can convert: MCX carries Michigan
zones and nothing else — three on SPCS 83 and nineteen on SPCS2022
(``michspc.spc.zones.ALL_ZONES``) — and Michigan lies wholly north of the
equator and west of Greenwich. That stayed true when the 2022 zones arrived,
which is the case this paragraph was written against. ``DEFAULT_HEMISPHERE``
below is the one place that assumption is written down, so a program that ever
grew a zone outside that quadrant has one line to revisit rather than a habit to
find.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QWidget

from michspc.fileio import dms

DEFAULT_HEMISPHERE = {
    dms.LATITUDE: "N",
    dms.LONGITUDE: "W",
}
"""Which letter each dropdown opens on (docs/DESIGN.md amendment #28 note 3).

The one place the "every point MCX converts is north and west" assumption is
written down. It holds because the program carries the three Michigan zones and
nothing else; a zone outside that quadrant makes this line wrong, and it is
here rather than spread through the widget so that is one edit.

There is no unanswered state. A placeholder beside a preselected default would
be a third option meaning "not yet", which the user can only reach by choosing
it — and choosing "not yet" is not something anyone does.
"""

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
        for letter in dms.HEMISPHERES[axis]:
            self.hemisphere.addItem(letter, letter)
        self.hemisphere.setCurrentIndex(
            self.hemisphere.findData(DEFAULT_HEMISPHERE[axis])
        )
        # NO TOOLTIP, at the owner's instruction (docs/DESIGN.md amendment #34).
        # The letter is its own label: the box offers N and S, or E and W, and
        # shows which of them is selected.

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
        """The chosen letter. Always one of the two — there is no empty state.

        Whatever it returns goes to ``fileio.dms`` unchanged, including the ""
        this cannot currently produce: that function refuses an empty letter by
        name, and leaving the guard there is what keeps a future change here
        from silently defaulting one deeper down.
        """
        data = self.hemisphere.currentData()
        return data if isinstance(data, str) else ""

    def is_complete(self) -> bool:
        """The three typed boxes answered. Says nothing about whether they are
        READABLE.

        The hemisphere is deliberately not tested: it opens on a real letter
        and cannot be emptied, so a check on it would be a condition that is
        always true — which reads to the next person as though the dropdown had
        an unanswered state to guard against.

        This gates the Convert button, and gating is all it does: whether 61
        minutes is a legal angle is ``fileio.dms``'s question, and asking it
        here as well would put a second rule about angles in the interface.
        """
        return bool(
            self.degrees.text().strip()
            and self.minutes.text().strip()
            and self.seconds.text().strip()
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
        """Empty the three typed boxes and put the hemisphere back to its
        opening letter — the state a freshly built row is in."""
        for box in (self.degrees, self.minutes, self.seconds):
            box.clear()
        self.hemisphere.setCurrentIndex(
            self.hemisphere.findData(DEFAULT_HEMISPHERE[self.axis])
        )
