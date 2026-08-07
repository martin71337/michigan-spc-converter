"""The single-point results panel: a scrolling grid of labelled values.

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

No ``.qrc``, no ``QStyle.StandardPixmap``, no new asset. The copy control is a
flat ``QToolButton`` with the word "Copy" on it: the repo has no icon
infrastructure beyond the application ``.ico``, and adding one would put a new
file in the release gate's path for a purely cosmetic gain.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QToolButton, QWidget

from michspc.gui.results_model import ResultSection, ResultValue

COPY_BUTTON_TEXT = "Copy"
"""The per-value copy button's caption, in words rather than a glyph."""

NAME_COLUMN = 0
VALUE_COLUMN = 1
BUTTON_COLUMN = 2


class ResultPanel(QScrollArea):
    """A scrolling grid of one result's sections, rebuilt wholesale each time."""

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

        self.render_sections(None)

    def render_sections(self, sections: tuple[ResultSection, ...] | None) -> None:
        """Rebuild the panel from scratch. ``None`` empties it.

        A fresh container replaces the old one wholesale — ``QScrollArea`` takes
        ownership and deletes what it held — rather than editing rows in place.
        The three directions do not share a row layout, so a partial update
        would leave a row from the previous conversion standing beside this
        one's, which is exactly the divergence this feature must not create
        (docs/DESIGN.md amendment #26).
        """
        self.sections = sections
        self.values = tuple(
            value for section in (sections or ()) for value in section.values
        )
        self.value_labels = []
        self.copy_buttons = []

        container = QWidget(self)
        grid = QGridLayout(container)
        row = 0

        for section in sections or ():
            grid.addWidget(self._title_label(section.title, container), row, 0, 1, 3)
            row += 1
            for value in section.values:
                self._add_value_row(grid, container, value, row)
                row += 1

        grid.setColumnStretch(VALUE_COLUMN, 1)
        grid.setRowStretch(row, 1)

        self.container = container
        self.grid = grid
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
        self, grid: QGridLayout, container: QWidget, value: ResultValue, row: int
    ) -> None:
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

        button = QToolButton(container)
        button.setText(COPY_BUTTON_TEXT)
        button.setAutoRaise(True)
        button.setToolTip(f"Copy the {value.label} value to the clipboard")
        # The default argument freezes this row's index; ``clicked`` also passes
        # a checked flag, which is swallowed.
        button.clicked.connect(lambda *_ignored, at=index: self._copy(at))

        grid.addWidget(name, row, NAME_COLUMN)
        grid.addWidget(shown, row, VALUE_COLUMN)
        grid.addWidget(button, row, BUTTON_COLUMN)

        self.value_labels.append(shown)
        self.copy_buttons.append(button)

    def _copy(self, index: int) -> None:
        if self._on_copy is not None:
            self._on_copy(index)
