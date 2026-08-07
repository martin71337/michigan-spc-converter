"""The single-point results panel: two columns, INPUT on the left.

Split out of ``michspc.gui.single_point`` because that module had grown past the
size at which one file still reads as one idea. The boundary is a real one: this
module knows how to *show* a ``ResultSection`` tuple and nothing else. It does
not know what a direction is, it never calls ``job.run``, and it never touches
the clipboard — the copy request is handed back to its owner through a callback,
so there is exactly one route to the clipboard and it lives with the tab that
owns the result.

**Nothing here computes a domain value, and nothing here builds a display
string.** Every string it renders arrived already formatted, from
``results_model.single_point_sections`` — which is built from
``michspc.fileio.formatting``, the same functions the audit CSV and the job
record use. A string assembled here would be a second authoritative
representation of a fact the core already owns.

**Two columns, separated by a vertical rule** (docs/DESIGN.md amendment #27).
The first section goes left and the rest go right; ``single_point_sections``
returns exactly ``(source, target)``, so in practice that is INPUT on the left
and OUTPUT on the right, which is the order the owner asked for and the order a
surveyor reads. The split is positional rather than by title on purpose: this
module does not know what "INPUT" means, and giving it that knowledge would put
a second statement of the section layout here beside the one in
``results_model``.

The stacked single column it replaces put the converted coordinate below the
fold on a laptop screen, so reading a result meant scrolling away from the
typed one — the two numbers a surveyor most wants to see at once.

**The copy control is the Windows 11 glyph, beside its own value.** It was the
word "Copy" pinned to the far right of the panel, which put a button an inch of
empty space away from the number it copied, in a column where every row's button
looked identical. Now each button sits immediately after the value it copies
(``michspc.gui.copy_icon``). The tooltip still names the section and the row,
which is the disambiguation the closing review gate asked for.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QWidget,
)

from michspc.gui.copy_icon import copy_icon
from michspc.gui.results_model import ResultSection, ResultValue

COPY_ACCESSIBLE_NAME = "Copy"
"""What the button calls itself to a screen reader and to a test.

The caption is a glyph now, so this is the only place the control still says
the word. A button with an icon and no accessible name is a button with no name
at all to anything that is not a pair of eyes.
"""

COPY_ICON_SIZE = 11
"""The glyph's size in logical pixels.

Reduced from 14 at the owner's request. The floor is legibility, not taste: the
glyph has to stay recognisable as two sheets, and below about 10 px its two
outlines merge into a smudge at the stroke width Fluent uses. 11 keeps the
button smaller than the line of text it sits beside, which is what he asked
for, and `tests/test_copy_icon.py` still resolves the two sheets at this size.
"""

NAME_COLUMN = 0
VALUE_COLUMN = 1

WRAP_WIDTH = 320
"""How wide a value is allowed to get before it is asked to wrap.

Every value but one is a coordinate, a factor or a zone name, and none of those
should ever wrap: "Michigan Central 2112" broken across two lines with the copy
button stranded beside the first half is worse than a slightly wider column.
Only the Warnings value is a paragraph, and it is the one this cap is for.

Applied as a minimum width taken from the text's own advance and capped here,
rather than as a rule about which row is which — this module does not know that
one of its rows is called Warnings, and should not learn.
"""

SEPARATOR_WIDTH = 1
"""A hairline, drawn in the palette's own mid tone. ``QFrame.Sunken`` — Qt's
default — draws the etched two-tone groove of a 1990s dialog; the owner asked
for a clean bar."""


class ResultPanel(QScrollArea):
    """A scrolling two-column view of one result, rebuilt wholesale each time."""

    def __init__(self, parent=None, on_copy=None) -> None:
        """``on_copy`` is called with a value's index when its button is clicked.

        Passed in rather than wired to a clipboard here: the panel shows values,
        the tab owns them, and one route to the clipboard is what keeps the
        per-value copy and Copy all from drifting apart.
        """
        super().__init__(parent)
        self.setWidgetResizable(True)

        self._on_copy = on_copy
        self.sections: tuple[ResultSection, ...] | None = None
        self.values: tuple[ResultValue, ...] = ()
        self.value_labels: list[QLabel] = []
        self.copy_buttons: list[QToolButton] = []
        self.separator: QFrame | None = None

        self.render_sections(None)

    def render_sections(self, sections: tuple[ResultSection, ...] | None) -> None:
        """Rebuild the panel from scratch. ``None`` empties it.

        A fresh container replaces the old one wholesale — ``QScrollArea`` takes
        ownership and deletes what it held — rather than editing rows in place.
        The three directions do not share a row layout, so a partial update
        would leave a row from the previous conversion standing beside this
        one's, which is exactly the divergence this feature must not create
        (docs/DESIGN.md amendment #26).

        ``value_labels`` and ``copy_buttons`` stay in the flattened order of
        ``values`` — every left-hand row, then every right-hand row — so an
        index means the same thing to the panel, to ``copy_value`` and to a
        test, regardless of which column the row was drawn in.
        """
        self.sections = sections
        self.values = tuple(
            value for section in (sections or ()) for value in section.values
        )
        self.value_labels = []
        self.copy_buttons = []
        self.separator = None

        container = QWidget(self)
        columns = QHBoxLayout(container)

        if sections:
            left = self._build_column(container, sections[:1])
            right = self._build_column(container, sections[1:])

            columns.addWidget(left, 1)
            self.separator = self._separator(container)
            columns.addWidget(self.separator)
            columns.addWidget(right, 1)

            self.left_column = left
            self.right_column = right
        else:
            # Nothing converted: no columns and no rule. An empty panel with a
            # bar down the middle of it would be furniture describing a result
            # that does not exist.
            self.left_column = None
            self.right_column = None

        self.container = container
        self.setWidget(container)

    def displayed_rows(self) -> tuple[tuple[str, str], ...]:
        """What the panel is showing, as (label, value) pairs in screen order.

        Read off the widgets, not off ``self.values``: a test asking what the
        surveyor can see must be answered by the labels he is looking at.
        """
        return tuple(
            (value.label, label.text())
            for value, label in zip(self.values, self.value_labels)
        )

    # ------------------------------------------------------------------
    # One column at a time
    # ------------------------------------------------------------------

    def _build_column(
        self, parent: QWidget, sections: tuple[ResultSection, ...]
    ) -> QWidget:
        """One side of the panel: its sections, stacked, top-aligned."""
        column = QWidget(parent)
        grid = QGridLayout(column)
        grid.setContentsMargins(0, 0, 0, 0)
        row = 0

        for section in sections:
            grid.addWidget(self._title_label(section.title, column), row, 0, 1, 2)
            row += 1
            for value in section.values:
                self._add_value_row(grid, column, value, row, section.title)
                row += 1

        grid.setColumnStretch(VALUE_COLUMN, 1)
        # Absorbs the height the shorter column does not use, so both columns'
        # rows start at the top and line up with each other rather than being
        # spread down their own side.
        grid.setRowStretch(row, 1)
        return column

    def _separator(self, parent: QWidget) -> QFrame:
        """The vertical rule between the two columns."""
        line = QFrame(parent)
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setLineWidth(SEPARATOR_WIDTH)
        line.setFixedWidth(SEPARATOR_WIDTH)
        return line

    # ------------------------------------------------------------------
    # One row at a time
    # ------------------------------------------------------------------

    @staticmethod
    def _title_label(title: str, container: QWidget) -> QLabel:
        """A section heading — INPUT or OUTPUT — in bold."""
        label = QLabel(title, container)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        return label

    def _add_value_row(
        self,
        grid: QGridLayout,
        container: QWidget,
        value: ResultValue,
        row: int,
        section_title: str,
    ) -> None:
        """One label / value / copy-button row.

        The value and its button share a cell, in that order, with the slack
        after them: the button follows the end of the number rather than the
        end of the panel. In a grid cell of its own it would have landed at the
        right edge of the widest value in the column — which is the Warnings
        line, several times the width of a coordinate.

        ``section_title`` is carried in solely for the tooltip. Both sections
        can hold a row called "Northing" - the typed one and the converted one -
        and the closing review gate found that two identical-looking Copy
        buttons beside two identically-named rows is a direct route to pasting
        an unconverted number as the converted coordinate. Naming the section is
        the cheapest honest disambiguation, and it matters more now that the
        buttons carry a glyph instead of a word.

        The INPUT rows keep their copy buttons rather than losing them: in a
        State-Plane-to-geodetic job EVERY factor sits under INPUT, because there
        is no target zone, and those are exactly the computed values a surveyor
        needs to lift off the screen.
        """
        index = len(self.value_labels)

        name = QLabel(value.label, container)
        shown = QLabel(value.text, container)
        # The same treatment MainWindow.status_label gets, for the same
        # load-bearing reason: the Warnings value quotes typed input back, and
        # QLabel's AutoText guess (Qt::mightBeRichText) would render a token
        # that looks like a tag away — deleting part of a refusal-grade
        # sentence from the screen with nothing said.
        shown.setTextFormat(Qt.TextFormat.PlainText)
        shown.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        shown.setWordWrap(True)
        # Wide enough for its own text, up to the cap. Without this a wrapped
        # QLabel takes the width its own sizeHint heuristic picks, which is
        # narrower than the text: a zone name broke across two lines with the
        # copy button beside the first half of it.
        # The two extra pixels are not cosmetic slack: horizontalAdvance
        # returns whole pixels while the label lays its text out in fractions,
        # so a value given exactly its advance can still wrap by a hair's
        # breadth. "International feet (ift)" did, at 129 px of 129.
        shown.setMinimumWidth(
            min(shown.fontMetrics().horizontalAdvance(value.text) + 2, WRAP_WIDTH)
        )

        button = QToolButton(container)
        button.setIcon(
            copy_icon(
                COPY_ICON_SIZE,
                self.palette().color(QPalette.ColorRole.WindowText),
                self.devicePixelRatioF(),
            )
        )
        button.setIconSize(QSize(COPY_ICON_SIZE, COPY_ICON_SIZE))
        button.setAutoRaise(True)
        button.setAccessibleName(COPY_ACCESSIBLE_NAME)
        button.setToolTip(f"Copy the {section_title} {value.label} value to the clipboard")
        # The default argument freezes this row's index; ``clicked`` also passes
        # a checked flag, which is swallowed.
        button.clicked.connect(lambda *_ignored, at=index: self._copy(at))

        cell = QWidget(container)
        beside = QHBoxLayout(cell)
        beside.setContentsMargins(0, 0, 0, 0)
        beside.addWidget(shown)
        # Top-aligned, and so is the row's name. Every row but one is a single
        # line, where this changes nothing; the Warnings row wraps to a
        # paragraph, and there the default centring would leave the label and
        # the button floating halfway down a block of text.
        beside.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        beside.addStretch(1)

        grid.addWidget(name, row, NAME_COLUMN, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(cell, row, VALUE_COLUMN)

        self.value_labels.append(shown)
        self.copy_buttons.append(button)

    def _copy(self, index: int) -> None:
        if self._on_copy is not None:
            self._on_copy(index)
