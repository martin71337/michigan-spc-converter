"""The Options dialog (DESIGN.md #71, plan section 1 items 1, 3 and 5).

Modal, opened from the window's menu bar, and the only place the Options are
changed. Three boxes, top to bottom - the system lists, the Auto zone frame,
the observation date - then the refusal line and OK / Cancel.

Every label is derived from a registry record (``options.ListGroup.label``,
the Auto frames' own codes and zone systems), so no name of a frame or a
zone system is typed here.

**OK is refused while the lists would be empty** (plan L8): with every zone
group, or every latitude/longitude group, switched off, the button is
disabled and the reason is shown in words beneath the boxes - never a
dropdown with nothing to choose.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from michspc.gui.controls import RED
from michspc.gui.options import (
    LIST_GROUPS,
    Options,
    options_problem,
)
from michspc.job import AUTO_FRAMES, ObservationDateSource
from michspc.spc.autozone import zones_choosable
from michspc.spc.zones import ALL_ZONES

OPTIONS_TITLE = "Options"
OPTIONS_ACTION_TEXT = "Options…"
LISTS_TITLE = "Show in the system lists"
AUTO_FRAME_TITLE = "Auto zone frame"
DATE_TITLE = "Observation date"

DATE_SOURCE_TEXT = {
    ObservationDateSource.TODAY: "Today (the date the job runs)",
    ObservationDateSource.ENTERED: "Enter a date on the tab",
}
"""The two observation-date choices, in the owner's words (plan O3)."""


def auto_frame_label(frame) -> str:
    """"NAD83(2011) - SPCS 83 zones" / "NATRF2022 - SPCS2022 local zones".

    The frame's code and the zone system it chooses among, from
    ``job.AUTO_FRAMES``. "local" is said exactly when the system has zones
    Auto never chooses - the SPCS2022 statewide zone (``zones_choosable``
    excludes it) - so the label does not claim all of a system's zones.
    """
    system = next(system for candidate, system in AUTO_FRAMES if candidate is frame)
    choosable = zones_choosable(system)
    total = sum(1 for zone in ALL_ZONES if zone.system == system.value)
    family = f"{system.value} local zones" if len(choosable) < total else (
        f"{system.value} zones"
    )
    return f"{frame.code} - {family}"


class OptionsDialog(QDialog):
    """Edits a copy of the window's ``Options``; ``options()`` reads the answer."""

    def __init__(self, current: Options, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(OPTIONS_TITLE)
        self.setModal(True)
        layout = QVBoxLayout(self)

        lists = QGroupBox(LISTS_TITLE, self)
        lists_layout = QVBoxLayout(lists)
        self.group_boxes: dict[str, QCheckBox] = {}
        for group in LIST_GROUPS:
            box = QCheckBox(group.label, lists)
            box.setChecked(current.is_group_shown(group))
            box.toggled.connect(self._update_ok)
            lists_layout.addWidget(box)
            self.group_boxes[group.key] = box
        layout.addWidget(lists)

        auto = QGroupBox(AUTO_FRAME_TITLE, self)
        auto_layout = QVBoxLayout(auto)
        self._auto_group = QButtonGroup(auto)
        self.auto_buttons = {}
        for frame, _system in AUTO_FRAMES:
            button = QRadioButton(auto_frame_label(frame), auto)
            button.setChecked(frame is current.auto_frame)
            self._auto_group.addButton(button)
            auto_layout.addWidget(button)
            self.auto_buttons[frame] = button
        layout.addWidget(auto)

        date = QGroupBox(DATE_TITLE, self)
        date_layout = QVBoxLayout(date)
        self._date_group = QButtonGroup(date)
        self.date_buttons = {}
        for source in ObservationDateSource:
            button = QRadioButton(DATE_SOURCE_TEXT[source], date)
            button.setChecked(source is current.date_source)
            self._date_group.addButton(button)
            date_layout.addWidget(button)
            self.date_buttons[source] = button
        layout.addWidget(date)

        self.problem_label = QLabel("", self)
        self.problem_label.setTextFormat(Qt.TextFormat.PlainText)
        self.problem_label.setWordWrap(True)
        self.problem_label.setStyleSheet(RED)
        layout.addWidget(self.problem_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_ok()

    @property
    def ok_button(self):
        return self.buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _shown(self) -> frozenset[str]:
        return frozenset(key for key, box in self.group_boxes.items() if box.isChecked())

    def problem(self) -> str | None:
        """Why OK is refused right now, or None (plan L8)."""
        return options_problem(self._shown())

    def _update_ok(self) -> None:
        problem = self.problem()
        self.ok_button.setEnabled(problem is None)
        self.problem_label.setText(problem or "")
        self.problem_label.setVisible(problem is not None)

    def accept(self) -> None:  # noqa: D102 - Qt's name
        # The button is disabled while a problem stands; Enter on the dialog
        # still reaches here, so the rule is asked again rather than trusted.
        if self.problem() is not None:
            self._update_ok()
            return
        super().accept()

    def options(self) -> Options:
        """The Options the dialog's controls state. Refuses while OK is refused."""
        auto_frame = next(
            frame for frame, button in self.auto_buttons.items() if button.isChecked()
        )
        date_source = next(
            source for source, button in self.date_buttons.items() if button.isChecked()
        )
        return Options(
            shown=self._shown(), auto_frame=auto_frame, date_source=date_source
        )
