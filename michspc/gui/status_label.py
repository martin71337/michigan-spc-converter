"""The status line's label: one line, elided, never wider than the window.

The owner's report, 2026-10-29 (DESIGN.md #73): when an Auto refusal was
raised on the Single point tab, the window grew wider than the screen. The
cause was not that message. Both tabs' status lines were plain ``QLabel``s
that do not wrap, and every refusal is shown there as "Refused: " plus the
message's first line - and refusal messages are single long lines, because
they name every offending point and say what to do about it. A non-wrapping
label's minimum width is its text's width, a layout cannot make a widget
narrower than its minimum, and so the WINDOW's minimum width became the
message's: 2,908 px for that one refusal, and more for a longer one.

So this label never asks for width. It keeps the full text - ``text()``
returns it, exactly as set, because the tabs, the tests and the tooltip all
read it - and DISPLAYS it on one line, cut with "…" where the window ends.
Nothing is lost: the tabs put the whole message in the tooltip and in the
failure dialog, as they always have.

**Why not word wrap.** A wrapping label asks for height instead of width, and
a 600-character refusal on a narrow window would push the status line down
over several lines and resize the form above it. One line is what a status
line is.

**Why the elision is done by setting the displayed text** rather than by
painting: QLabel draws its own text selection (the status line is
selectable by mouse), and a label that painted its own text would draw a
selection that no longer matched what is on screen. The stylesheet colour
(the RED and AMBER of the tabs) applies to the label as before.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


class StatusLabel(QLabel):
    """A one-line label that shows its text elided to its own width.

    ``setText`` stores the full text and ``text`` returns it; what is drawn is
    that text cut to the label's current width with a trailing ellipsis. The
    horizontal size policy is ``Ignored`` and the minimum size hint asks for no
    width, so no text, however long, can widen the window.
    """

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setWordWrap(False)
        self.setText(text)

    # The full text is the label's value; the drawn text is derived from it.

    def setText(self, text: str) -> None:  # noqa: N802 - Qt's name
        self._full_text = text
        self._refit()

    def text(self) -> str:
        return self._full_text

    def shown_text(self) -> str:
        """What is actually drawn: the full text, or its elided form."""
        return super().text()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt's name
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt's name
        return QSize(0, super().sizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt's name
        super().resizeEvent(event)
        self._refit()

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt's name
        # A font or style change (the stylesheet swaps colours, a font may
        # come with it) changes the text's width.
        super().changeEvent(event)
        self._refit()

    def _refit(self) -> None:
        # Newlines would make a second line; a status line is one. None of
        # the tabs' status texts contain one today, and the refusal path
        # already takes the message's first line.
        # changeEvent can arrive from inside QLabel's own constructor, before
        # the full text exists.
        one_line = " ".join(getattr(self, "_full_text", "").splitlines())
        width = max(self.contentsRect().width(), 0)
        shown = self.fontMetrics().elidedText(one_line, Qt.TextElideMode.ElideRight, width)
        if shown != super().text():
            super().setText(shown)
