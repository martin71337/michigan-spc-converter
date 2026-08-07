"""The Single point tab: one coordinate, typed in, converted, read off screen.

The everyday case the file converter makes clumsy (docs/DESIGN.md amendment
#26). No file, no output folder, nothing written — a results display only.

**The constraint that shapes this whole module:** this tab and the Multi point
tab must be *incapable* of disagreeing about the same point. A surveyor who
checks a coordinate here and then runs the file through the other tab must get
the same numbers, because a discrepancy between two views of one conversion is
the tier sentence's failure mode arriving by a new road. So:

* the typed values go through the same validation gate — ``pnezd.parse_lines``,
  reached via ``pnezd.parse_typed_point`` — as a file row;
* they go through the same conversion function, ``job.run``, called with the
  parsed rows as its ``source``;
* every string on screen comes from ``results_model.single_point_sections``,
  which is built from ``michspc.fileio.formatting`` — the same formatters the
  audit CSV and the job record use.

**This module never computes a domain value**, for the same reason ``window``
does not. There is no arithmetic here: no rounding, no unit conversion, no
defaulting of an absent value. A number produced here would be a second
authoritative representation of a fact the core already owns.

**There is no ``QValidator`` on any entry field**, and that is deliberate. A
validator is a second validation gate that rejects silently, which inverts both
"one entry point per data path" and "refusals teach". Non-numeric text travels
to the reader and comes back as the reader's own sentence, naming the field and
the column layout it was read as.

The tab shares no state with ``MainWindow``: it owns its own zone, unit and
longitude-sign controls, built by ``michspc.gui.controls`` so they are the same
controls rather than a lookalike set. It imports nothing from
``michspc.gui.window`` — the dependency runs one way, so neither tab can reach
the other.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFrame,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from michspc import APP_NAME
from michspc.fileio import dms, pnezd
from michspc.gui.controls import (
    AMBER,
    GEODETIC,
    RED,
    UNITS_LABEL,
    UNITS_LABEL_ELEVATION_ONLY,
    direction_for,
    longitude_combo,
    longitude_is_relevant,
    show_failure_dialog,
    unit_combo,
    zone_combo,
)
from michspc.gui.dms_entry import DmsEntry
from michspc.gui.result_panel import ResultPanel
from michspc.gui.results_model import (
    ResultSection,
    single_point_clipboard_text,
    single_point_sections,
    single_point_warnings,
)
from michspc.job import Direction, JobResult, JobSettings, LongitudeConvention, run
from michspc.spc.zones import Zone

TAB_TITLE = f"{APP_NAME} — single point"
"""What the failure dialog calls itself. Names the tab, not just the program:
a refusal raised here must not look like one raised by the file converter."""

FIRST_LABEL_ZONE = "Northing:"
SECOND_LABEL_ZONE = "Easting:"
FIRST_LABEL_GEODETIC = "Latitude:"
SECOND_LABEL_GEODETIC = "Longitude:"
FIRST_LABEL_UNCHOSEN = "Northing / Latitude:"
SECOND_LABEL_UNCHOSEN = "Easting / Longitude:"
"""The three states of the two coordinate labels.

They follow the **From** selection alone, exactly as
``MainWindow.input_hint_text`` does and for the same reason: the To selection
cannot change what the typed values *are*, and a label that moved with it would
be describing the wrong end of the job.

The unchosen spelling names both readings rather than showing the northing/
easting one. Showing that would be a silent default for the very question the
labels exist to ask (docs/DESIGN.md section 7).
"""

ELEVATION_LABEL = "Elevation:"
"""One spelling, in every direction. An elevation is an elevation whichever way
the coordinates are going, so this label never moves and the field is never
disabled."""

ELEVATION_TOOLTIP = (
    "Optional. A blank or exactly-zero elevation means 'not recorded': the "
    "elevation and combined factors then read N/A rather than a plausible 1.0."
)

STATUS_READY = "Ready."

STATUS_INPUT_CHANGED = "Input changed. Press Convert."
"""Shown when a displayed result is discarded because a control moved.

It says what happened and what to do. "Ready." would be true but would not
explain why the numbers vanished, and a surveyor who thought the result was
still there is exactly the person this message is for.
"""

UNITS_TOOLTIP_ZONE_IN = "The unit the typed northing, easting and elevation are in."
UNITS_TOOLTIP_GEODETIC_IN = (
    "The typed latitude and longitude are decimal degrees, which carry no "
    "linear unit. This selects the unit of the typed ELEVATION only - and that "
    "still matters: the elevation factor and the combined factor are computed "
    "from it."
)
UNITS_TOOLTIP_ZONE_OUT = (
    "The unit the converted northing, easting and elevation are shown in."
)
UNITS_TOOLTIP_GEODETIC_OUT = (
    "The converted latitude and longitude are decimal degrees, which carry no "
    "linear unit. This selects the unit of the converted ELEVATION only - the "
    "elevation is re-expressed into it."
)
"""This tab's own unit tooltips, not ``window``'s.

The multi-point wording says "the input file's columns two and three", which is
simply false of a typed point: there is no file and there are no columns. The
load-bearing sentence is carried over unchanged — that the elevation unit still
drives the elevation and combined factors — because that is the part a surveyor
would otherwise get wrong.
"""

INCOMPLETE_FORM = (
    "The conversion settings are incomplete, so nothing was run. Choose both "
    "ends of the conversion, type both coordinate values, and — when geodetic "
    "coordinates are involved — choose the longitude sign convention."
)

WARNINGS_TITLE = "Warnings"

WARNINGS_MIN_HEIGHT = 34
WARNINGS_MAX_HEIGHT = 76
"""How tall the warnings field may be, in logical pixels — about two lines at
the minimum and four at the maximum, scrolling past that.

Bounded on BOTH sides deliberately. Below the minimum a single warning would
arrive in a slot too small to read; above the maximum the field would push the
converted coordinates off a laptop screen at exactly the moment a warning says
to look at them.
"""

NO_RESULT_WARNINGS = "—"
"""What the warnings field shows when there is no result on screen.

Not "none", which is a statement ABOUT a conversion - that this point raised no
warnings - and would be a lie before one has been run. A dash says the field
has nothing to report yet, which is the truth.
"""

ANGLE_FORMAT_LABEL = "Lat/long entry:"
ANGLE_FORMAT_DECIMAL = "Decimal degrees"
ANGLE_FORMAT_DMS = "Degrees / minutes / seconds"
DECIMAL_PAGE = 0
DMS_PAGE = 1
"""The two ways of typing a geodetic coordinate (docs/DESIGN.md amendment #28).

**Decimal degrees is the default, and defaulting here is safe** — which is
worth saying, because almost nothing else in this program has a default. The
two zone dropdowns and the longitude convention open unanswered because their
options are indistinguishable from the numbers on screen. These two are not: the
boxes visibly change shape, and a decimal box holding "43.800" cannot be
mistaken for a degrees box holding "43". Nothing is silently assumed about a
value, so this is a starting state rather than an answer.

The selector is relevant only while the FROM selection is geodetic. When the
job starts from a zone the two boxes hold a northing and an easting, which have
no minutes or seconds, so the selector is disabled and the decimal page stays
up (see ``_update_angle_format_relevance``).
"""

# The angle-format dropdown had a tooltip here explaining that the choice
# governs what is TYPED only. Deleted at the owner's instruction (docs/DESIGN.md
# amendment #34) along with the other two on the coordinate entry. The behaviour
# it described is unchanged and is still pinned by the tests that switch pages
# mid-entry; only the text is gone.


class SinglePointTab(QWidget):
    """One typed coordinate, converted and displayed. Writes nothing."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.result: JobResult | None = None
        self.last_failure: BaseException | None = None
        """The most recent exception surfaced to the user. Kept so the failure
        path is observable to a test without driving a modal dialog."""

        self._build()
        self._update_entry_labels()
        self._update_unit_labels()
        self._update_longitude_relevance()
        self._update_angle_format_relevance()
        self._update_convert_enabled()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        # Built out of visual order on purpose: the results panel starts empty
        # by calling _render_sections(None), and that sets the Copy all button's
        # enablement, so the button has to exist first. The three widgets go
        # into the layout in the order the owner approved regardless.
        settings_box = self._build_settings()
        status_row = self._build_status_line()
        results_panel = self._build_results_panel()
        warnings_box = self._build_warnings_field()

        layout.addWidget(settings_box)
        layout.addWidget(results_panel, 1)
        layout.addWidget(warnings_box)
        layout.addLayout(status_row)

    def _build_settings(self) -> QWidget:
        box = QGroupBox("Conversion", self)
        grid = QGridLayout(box)

        # --- from / to --------------------------------------------------
        self.from_zone = zone_combo(box, self._on_direction_changed)
        self.to_zone = zone_combo(box, self._on_direction_changed)
        self.input_unit = unit_combo(box)
        self.output_unit = unit_combo(box)

        # Every control that can change the answer invalidates a displayed one.
        # The unit combos have no other handler at all, so without this a
        # feet-to-metres change would leave the previous unit's numbers on
        # screen under the new unit's label.
        self.input_unit.currentIndexChanged.connect(self._invalidate_result)
        self.output_unit.currentIndexChanged.connect(self._invalidate_result)

        self.input_unit_label = QLabel(UNITS_LABEL, box)
        self.output_unit_label = QLabel(UNITS_LABEL, box)

        grid.addWidget(QLabel("From zone:", box), 0, 0)
        grid.addWidget(self.from_zone, 0, 1)
        grid.addWidget(self.input_unit_label, 0, 2)
        grid.addWidget(self.input_unit, 0, 3)

        grid.addWidget(QLabel("To zone:", box), 1, 0)
        grid.addWidget(self.to_zone, 1, 1)
        grid.addWidget(self.output_unit_label, 1, 2)
        grid.addWidget(self.output_unit, 1, 3)

        # --- longitude sign convention ----------------------------------
        self.longitude_label = QLabel("Longitude sign:", box)
        self.longitude_combo = longitude_combo(box, self._update_convert_enabled)

        grid.addWidget(self.longitude_label, 2, 0)
        grid.addWidget(self.longitude_combo, 2, 1, 1, 3)

        # --- how a latitude and longitude are typed ----------------------
        self.angle_format_label = QLabel(ANGLE_FORMAT_LABEL, box)
        self.angle_format = QComboBox(box)
        self.angle_format.addItem(ANGLE_FORMAT_DECIMAL, DECIMAL_PAGE)
        self.angle_format.addItem(ANGLE_FORMAT_DMS, DMS_PAGE)
        self.angle_format.currentIndexChanged.connect(self._on_angle_format_changed)

        grid.addWidget(self.angle_format_label, 3, 0)
        grid.addWidget(self.angle_format, 3, 1, 1, 3)

        # --- the typed coordinate ---------------------------------------
        # Each coordinate row is a two-page stack: one decimal box, or four DMS
        # boxes. Both pages exist at all times and neither is rebuilt when the
        # format changes, so a switch cannot lose what is in the other one - and
        # `first_edit` means the same widget it always did, which is what lets
        # every existing test go on describing this tab unchanged.
        self.first_label = QLabel(FIRST_LABEL_UNCHOSEN, box)
        self.first_edit = QLineEdit(box)
        self.first_dms = DmsEntry(dms.LATITUDE, box, on_change=self._on_entry_changed)
        self.first_stack = self._entry_stack(box, self.first_edit, self.first_dms)

        self.second_label = QLabel(SECOND_LABEL_UNCHOSEN, box)
        self.second_edit = QLineEdit(box)
        self.second_dms = DmsEntry(dms.LONGITUDE, box, on_change=self._on_entry_changed)
        self.second_stack = self._entry_stack(box, self.second_edit, self.second_dms)

        self.elevation_label = QLabel(ELEVATION_LABEL, box)
        self.elevation_edit = QLineEdit(box)
        self.elevation_edit.setToolTip(ELEVATION_TOOLTIP)

        # Only the two coordinate fields gate Convert. The elevation is optional
        # by the file reader's own convention, so it does not participate in
        # enablement - but every field, including the elevation, invalidates a
        # displayed result, which is a separate concern (see _invalidate_result).
        # The DMS boxes reach the same two methods through _on_entry_changed.
        self.first_edit.textChanged.connect(self._update_convert_enabled)
        self.second_edit.textChanged.connect(self._update_convert_enabled)
        self.first_edit.textChanged.connect(self._invalidate_result)
        self.second_edit.textChanged.connect(self._invalidate_result)
        self.elevation_edit.textChanged.connect(self._invalidate_result)

        grid.addWidget(self.first_label, 4, 0)
        grid.addWidget(self.first_stack, 4, 1, 1, 3)
        grid.addWidget(self.second_label, 5, 0)
        grid.addWidget(self.second_stack, 5, 1, 1, 3)
        grid.addWidget(self.elevation_label, 6, 0)
        grid.addWidget(self.elevation_edit, 6, 1, 1, 3)

        # --- convert ----------------------------------------------------
        self.convert_button = QPushButton("Convert", box)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.convert_button)
        self.convert_button.clicked.connect(self.convert)
        grid.addLayout(buttons, 7, 0, 1, 4)

        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(3, 2)
        return box

    @staticmethod
    def _entry_stack(box: QWidget, decimal: QWidget, degrees: QWidget) -> QStackedWidget:
        """One coordinate row's two pages, decimal first.

        ``QStackedWidget`` sizes itself to its tallest page, so the row does not
        change height when the format switches - a form that jumps about as a
        dropdown moves reads as a glitch.
        """
        stack = QStackedWidget(box)
        stack.addWidget(decimal)
        stack.addWidget(degrees)
        stack.setCurrentIndex(DECIMAL_PAGE)
        return stack

    def _build_results_panel(self) -> ResultPanel:
        """An empty scrolling panel, rebuilt wholesale on each conversion.

        The panel calls back into ``copy_value`` rather than reaching a
        clipboard itself, so both copy routes go through this tab's one
        ``_set_clipboard`` seam.
        """
        self.panel = ResultPanel(self, on_copy=self.copy_value)
        self.copy_all_button.setEnabled(self.panel.sections is not None)
        return self.panel

    def _build_warnings_field(self) -> QGroupBox:
        """Warnings, full width, in a box of their own beneath the results.

        The owner's shape (docs/DESIGN.md amendment #30). They were the last
        OUTPUT line of the right-hand column, where a paragraph of prose sat in
        a column sized for coordinates and pushed every number above it around.
        Full width is what a sentence needs.

        **No copy button, and not in Copy all.** Also his instruction, and it
        follows from what the clipboard is for here: the numbers go into CAD or
        a spreadsheet, and a warning is something to read on the screen and act
        on. The text is still selectable with the mouse, which is how every
        other label in this program behaves - that is reading, not a copy
        control.

        The box is always present rather than appearing with a warning. A field
        that materialises only sometimes is one a surveyor learns not to look
        for, and "none" is a result worth stating - it is the good one.
        """
        box = QGroupBox(WARNINGS_TITLE, self)
        layout = QVBoxLayout(box)

        self.warnings_label = QLabel(NO_RESULT_WARNINGS, box)
        # Plain text and word-wrapped, for the reasons the panel's value labels
        # are: these messages quote typed input back, and QLabel's AutoText
        # guess would render a token that looks like a tag away - deleting part
        # of a warning-grade sentence with nothing said.
        self.warnings_label.setTextFormat(Qt.TextFormat.PlainText)
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        # Top-aligned so one short line sits at the top of the box rather than
        # floating in the middle of it.
        self.warnings_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        # **The label goes in a scroll area, and that is a correctness fix.**
        # A word-wrapped QLabel does not propagate its height-for-width out
        # through a QGroupBox's layout: the box took the height of ONE line and
        # clipped the rest, so a three-warning conversion showed its first
        # sentence and silently dropped the other two. Found by looking at a
        # warned run rather than by a test, which is why the test that now
        # covers it measures the rendered label against its own content.
        #
        # Scrolling rather than growing without limit: the box sits between the
        # results and the status line, and a field that expanded to six lines
        # would push the numbers off a laptop screen exactly when a warning
        # says to look at them. Nothing is hidden - the text is all there and
        # reachable, and the status line states the count.
        self.warnings_scroll = QScrollArea(box)
        self.warnings_scroll.setWidgetResizable(True)
        self.warnings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.warnings_scroll.setWidget(self.warnings_label)
        self.warnings_scroll.setMinimumHeight(WARNINGS_MIN_HEIGHT)
        self.warnings_scroll.setMaximumHeight(WARNINGS_MAX_HEIGHT)

        layout.addWidget(self.warnings_scroll)
        return box

    def _build_status_line(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.status_label = QLabel(STATUS_READY, self)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        # Plain text, explicitly, for the reason MainWindow.status_label is:
        # refusal messages quote back whatever was typed, and QLabel's AutoText
        # guess would render something that looks like a tag away.
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)

        self.copy_all_button = QPushButton("Copy all", self)
        self.copy_all_button.setEnabled(False)
        self.copy_all_button.setToolTip(
            "Copy every line of the result, label and value, to the clipboard"
        )
        self.copy_all_button.clicked.connect(self.copy_all)

        row.addWidget(self.status_label, 1)
        row.addWidget(self.copy_all_button)
        return row

    # ------------------------------------------------------------------
    # What the user chose
    # ------------------------------------------------------------------

    def direction(self) -> Direction | None:
        """This tab's job, per ``controls.direction_for``, which owns the rule."""
        return direction_for(self.from_zone.currentData(), self.to_zone.currentData())

    def longitude_convention(self) -> LongitudeConvention | None:
        data = self.longitude_combo.currentData()
        return data if isinstance(data, LongitudeConvention) else None

    def settings(self) -> JobSettings | None:
        """Assemble the job settings, or None if the form is not yet complete.

        Mirrors ``MainWindow.settings`` exactly, including the zone-to-zone
        branch that states ``longitude_convention=None``, and differs in one
        respect only: ``input_path`` and ``output_directory`` are ``None`` and
        are not gated on. That is a statement, not an absence — this job came
        from no file and produces none (docs/DESIGN.md amendment #26).
        """
        direction = self.direction()
        if direction is None:
            return None

        source = self.from_zone.currentData()
        target = self.to_zone.currentData()
        source_zone = source if isinstance(source, Zone) else None
        target_zone = target if isinstance(target, Zone) else None

        common = dict(
            input_path=None,
            output_directory=None,
            direction=direction,
            source_zone=source_zone,
            target_zone=target_zone,
            input_unit=self.input_unit.currentData(),
            output_unit=self.output_unit.currentData(),
            apply_geoid=True,
        )

        if direction is Direction.ZONE_TO_ZONE:
            # A pure zone-to-zone job never consults the longitude convention
            # (michspc.job._convert_row), so the interface does not pretend the
            # user answered a question it never asked.
            return JobSettings(**common, longitude_convention=None)

        convention = self.longitude_convention()
        if convention is None:
            return None
        return JobSettings(**common, longitude_convention=convention)

    def typed_point_source(self) -> str:
        """What the reader's refusals will call this row.

        Read from the From selection, because that is what decides whether the
        two typed values are a northing and an easting or a latitude and a
        longitude. A surveyor who typed a longitude must not be told his
        "easting" is unreadable.
        """
        if self.from_zone.currentData() == GEODETIC:
            return pnezd.TYPED_POINT_SOURCE_GEODETIC
        return pnezd.TYPED_POINT_SOURCE_GRID

    def typed_coordinates(self, settings: JobSettings) -> tuple[str, str]:
        """The two coordinate values as text, whichever way they were typed.

        On the decimal page this is what is in the two boxes, verbatim. On the
        DMS page it is what ``fileio.dms`` composes from the four boxes: the
        text the decimal box WOULD have held, so everything downstream of this
        line — the reader, the conversion, the panel, the warnings — cannot
        tell the two entry modes apart. That is the point. A DMS-specific path
        through the conversion would be a second way of converting a latitude,
        and two ways of doing one thing is how the two tabs would come to
        disagree (docs/DESIGN.md amendment #26).

        ``settings`` is passed in rather than re-derived so this uses the very
        object the job will run with, and its convention rather than a second
        reading of the dropdown.

        Raises ``dms.DmsError`` if any box is unreadable. ``convert`` shows it
        exactly as raised, like every other refusal.
        """
        if not self.entering_dms():
            return self.first_edit.text(), self.second_edit.text()

        # A geodetic SOURCE always has a convention by this point: settings()
        # returns None without one for both geodetic directions, and convert()
        # has already refused on that. Latitude ignores it either way.
        positive_west = (
            settings.longitude_convention is LongitudeConvention.POSITIVE_WEST
        )
        return (
            self.first_dms.decimal_degrees_text(positive_west=positive_west),
            self.second_dms.decimal_degrees_text(positive_west=positive_west),
        )

    # ------------------------------------------------------------------
    # Enablement and labelling
    # ------------------------------------------------------------------

    def _on_direction_changed(self) -> None:
        self._update_entry_labels()
        self._update_unit_labels()
        self._update_longitude_relevance()
        self._update_angle_format_relevance()
        self._update_convert_enabled()
        self._invalidate_result()

    def _on_angle_format_changed(self) -> None:
        """The typed point is discarded when the format changes, deliberately.

        The two pages hold different text, and carrying a decimal 43.800 over
        into a degrees box would read as 43 degrees flat - the same number
        meaning a different point, 48 minutes away, with nothing said. Nothing
        is translated between the pages: the abandoned page keeps whatever was
        in it and stops gating Convert, and ``_update_convert_enabled`` reads
        only the page now showing.
        """
        self._update_entry_pages()
        self._update_convert_enabled()
        self._invalidate_result()

    def _on_entry_changed(self) -> None:
        """What every DMS box is wired to: the same pair the decimal box uses."""
        self._update_convert_enabled()
        self._invalidate_result()

    def entering_dms(self) -> bool:
        """True when the two coordinate rows are showing their four-box page.

        Both conditions, not just the dropdown: a northing has no minutes, so
        the DMS page is never shown while the job starts from a zone however
        the selector happens to be set.
        """
        return (
            self.from_zone.currentData() == GEODETIC
            and self.angle_format.currentData() == DMS_PAGE
        )

    def _update_entry_pages(self) -> None:
        page = DMS_PAGE if self.entering_dms() else DECIMAL_PAGE
        self.first_stack.setCurrentIndex(page)
        self.second_stack.setCurrentIndex(page)

    def _update_angle_format_relevance(self) -> None:
        """The selector matters only when the typed values are angles."""
        relevant = self.from_zone.currentData() == GEODETIC
        self.angle_format_label.setEnabled(relevant)
        self.angle_format.setEnabled(relevant)
        self._update_entry_pages()

    def _invalidate_result(self) -> None:
        """Discard a displayed result the controls no longer describe.

        Found by the closing review gate, as a CRITICAL. Editing any field or
        selection after a conversion left the previous point's answer on the
        screen, still captioned "Converted", with both copy paths still live -
        so a surveyor who changed a northing and did not press Convert could
        copy the PREVIOUS point's coordinate straight into CAD. The reviewer's
        counterexample: Michigan Central to Michigan South, N=176,200.000
        converts to N=838,214.295; editing the entry to 276,200.000 without
        converting left 838,214.295 on screen, while the point now in the
        controls is 938,215.332 - a stale reading 100,001.037 ft out.

        Clearing rather than marking stale: a greyed-out or annotated result is
        still a number on the screen next to a Copy button, and this program's
        rule is that a value it cannot stand behind is not displayed at all.

        Idempotent, so the many signals that reach it cost nothing when there is
        no result to discard.
        """
        if self.result is None and self.panel.sections is None:
            return
        self.result = None
        self._render_sections(None)
        self._set_status(STATUS_INPUT_CHANGED)

    def entry_labels(self) -> tuple[str, str]:
        """The two coordinate labels for the current From selection."""
        source = self.from_zone.currentData()
        if source == GEODETIC:
            return FIRST_LABEL_GEODETIC, SECOND_LABEL_GEODETIC
        if isinstance(source, Zone):
            return FIRST_LABEL_ZONE, SECOND_LABEL_ZONE
        return FIRST_LABEL_UNCHOSEN, SECOND_LABEL_UNCHOSEN

    def _update_entry_labels(self) -> None:
        first, second = self.entry_labels()
        self.first_label.setText(first)
        self.second_label.setText(second)

        # Disabled only while the From selection is unanswered: until it is,
        # the program cannot say what a number typed here would mean, and an
        # enabled field would be inviting an answer to an unasked question.
        # The elevation field is never disabled - an elevation is an elevation
        # in every direction.
        known = self.from_zone.currentData() == GEODETIC or isinstance(
            self.from_zone.currentData(), Zone
        )
        self.first_label.setEnabled(known)
        self.first_stack.setEnabled(known)
        self.second_label.setEnabled(known)
        self.second_stack.setEnabled(known)

    def _update_unit_labels(self) -> None:
        """Say what each unit selector governs, given From and To.

        Reads the two dropdowns' own data, not ``direction()``: each selector
        belongs to one END of the job and must describe that end even while the
        other end is still unanswered. Neither selector is ever disabled - see
        ``controls.UNITS_LABEL_ELEVATION_ONLY`` for why.
        """
        source_is_geodetic = self.from_zone.currentData() == GEODETIC
        target_is_geodetic = self.to_zone.currentData() == GEODETIC

        self.input_unit_label.setText(
            UNITS_LABEL_ELEVATION_ONLY if source_is_geodetic else UNITS_LABEL
        )
        self.input_unit.setToolTip(
            UNITS_TOOLTIP_GEODETIC_IN if source_is_geodetic else UNITS_TOOLTIP_ZONE_IN
        )
        self.output_unit_label.setText(
            UNITS_LABEL_ELEVATION_ONLY if target_is_geodetic else UNITS_LABEL
        )
        self.output_unit.setToolTip(
            UNITS_TOOLTIP_GEODETIC_OUT if target_is_geodetic else UNITS_TOOLTIP_ZONE_OUT
        )

    def _update_longitude_relevance(self) -> None:
        """The selector matters only when geodetic coordinates are involved."""
        relevant = longitude_is_relevant(self.direction())
        self.longitude_label.setEnabled(relevant)
        self.longitude_combo.setEnabled(relevant)

    def coordinates_are_typed(self) -> bool:
        """Both coordinate rows answered, on whichever page is showing.

        "Answered" means every box has something in it — not that what is in
        them is readable. Whether 61 minutes is an angle is ``fileio.dms``'s
        question and it answers it with a sentence; deciding it here as well
        would put a second rule about angles in the interface, and the two
        would eventually disagree.
        """
        if self.entering_dms():
            return self.first_dms.is_complete() and self.second_dms.is_complete()
        return bool(self.first_edit.text().strip()) and bool(
            self.second_edit.text().strip()
        )

    def form_is_complete(self) -> bool:
        """Everything ``convert`` needs, and nothing it does not.

        The elevation is deliberately absent from this test: a blank elevation
        is the file reader's own "not recorded", and refusing to convert
        without one would invent a requirement the format does not have.
        """
        if self.settings() is None:
            return False
        return self.coordinates_are_typed()

    def _update_convert_enabled(self) -> None:
        self.convert_button.setEnabled(self.form_is_complete())

    # ------------------------------------------------------------------
    # Running the conversion
    # ------------------------------------------------------------------

    def convert(self) -> bool:
        """Convert the typed point and display it. True if it landed.

        **No wait cursor and no ``setEnabled(False)``.** That ceremony exists in
        ``MainWindow.convert`` because a file of several thousand points takes
        long enough for a frozen window to look like a crash. One point is
        instantaneous - a single ``_convert_row`` and one geoid lookup - so the
        same ceremony here would be a flicker that says "this is slow" about
        something that is not. Recorded as a decision rather than an omission.

        Nothing is written on this path at all, so there is no overwrite prompt
        and no output folder to open.
        """
        settings = self.settings()
        if settings is None or not self.form_is_complete():
            # Convert is disabled in this state; reaching here would mean the
            # enablement logic and this method disagree, so say so rather than
            # converting a half-specified point.
            self._report_failure(ValueError(INCOMPLETE_FORM))
            return False

        self.result = None
        self.last_failure = None
        self._render_sections(None)

        try:
            first, second = self.typed_coordinates(settings)
            parsed = pnezd.parse_typed_point(
                first,
                second,
                self.elevation_edit.text(),
                source=self.typed_point_source(),
            )
            result = run(settings, source=parsed)
            sections = single_point_sections(result)
            warnings = single_point_warnings(result)
        except Exception as error:  # noqa: BLE001 - shown in full, then stopped
            self._report_failure(error)
            return False

        self.result = result
        self._render_sections(sections, warnings)
        self._report_success(result)
        return True

    # ------------------------------------------------------------------
    # The results panel
    # ------------------------------------------------------------------

    def _render_sections(
        self,
        sections: tuple[ResultSection, ...] | None,
        warnings: str = NO_RESULT_WARNINGS,
    ) -> None:
        """Show a result, or ``None`` to empty the panel.

        Copy all follows the panel exactly: it is enabled when, and only when,
        there is something on screen to copy.

        The warnings field is driven from here rather than from ``convert``, so
        that it is emptied by the SAME call that empties the panel. Every route
        that discards a result - a control changing, a refusal, a fresh run
        starting - goes through this method, and a warnings field that outlived
        the numbers it described would be the stale-result failure of amendment
        #26 in a new place: the surveyor would read "none" beside a blank panel
        and take it as this point's answer.
        """
        self.panel.render_sections(sections)
        self.copy_all_button.setEnabled(sections is not None)
        self.warnings_label.setText(warnings)

    @property
    def sections(self) -> tuple[ResultSection, ...] | None:
        """The exact sections the panel last rendered, or None if it is empty.

        Read from the panel rather than kept beside it, so Copy all serialises
        what is on screen rather than a second copy of it that could go stale.
        """
        return self.panel.sections

    @property
    def value_labels(self) -> list[QLabel]:
        """The panel's value widgets, in screen order."""
        return self.panel.value_labels

    @property
    def copy_buttons(self) -> list[QToolButton]:
        """The panel's per-value copy buttons, in screen order."""
        return self.panel.copy_buttons

    def displayed_rows(self) -> tuple[tuple[str, str], ...]:
        """What the panel is showing, as (label, value) pairs in screen order."""
        return self.panel.displayed_rows()

    # ------------------------------------------------------------------
    # Copying
    # ------------------------------------------------------------------

    def _set_clipboard(self, text: str) -> None:
        """The one route to the clipboard. Overridden in tests, which run
        headless and must not depend on a platform clipboard."""
        QGuiApplication.clipboard().setText(text)

    def copy_value(self, index: int) -> bool:
        """Put exactly one displayed value on the clipboard.

        The value string alone: no label, no unit, no trailing newline. It is
        pasted straight into a CAD prompt or a spreadsheet cell, and anything
        else in the buffer has to be deleted there.
        """
        if self.sections is None:
            # Nothing has been converted, so there is nothing to copy. Refused
            # rather than copying an empty string, which would silently destroy
            # whatever the user already had on the clipboard.
            return False
        self._set_clipboard(self.panel.values[index].text)
        return True

    def copy_all(self) -> bool:
        """Put the whole result on the clipboard, labels included.

        Serialises the *same* sections tuple the panel rendered, through
        ``results_model.single_point_clipboard_text``, so the screen and the
        clipboard cannot disagree about what the result contains.
        """
        if self.sections is None:
            return False
        self._set_clipboard(single_point_clipboard_text(self.sections))
        return True

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def status_text(self, result: JobResult) -> str:
        """"Converted. 1 warning." — one point, so the count is of warnings."""
        count = len(result.warnings)
        if count == 0:
            return "Converted. No warnings."
        if count == 1:
            return "Converted. 1 warning."
        return f"Converted. {count} warnings."

    def _report_success(self, result: JobResult) -> None:
        warned = len(result.warnings)
        self._set_status(self.status_text(result), style=AMBER if warned else "")
        if warned:
            # The message already opens "point 1: ...", because job._convert_row
            # builds its context from the row identifier. Prefixing the same
            # identifier again produced "1: point 1: ..." - found by the closing
            # review gate. The panel's own Warnings row strips the fabricated
            # identifier entirely; this tooltip shows the message as the core
            # wrote it, minus the duplicate.
            self.status_label.setToolTip(
                "\n\n".join(warning.message for _point_id, warning in result.warnings)
            )
        else:
            self.status_label.setToolTip("")

    def _report_failure(self, error: BaseException) -> None:
        """Surface a refusal, in full, and record it.

        Every message the layers below raise names the offending field and says
        what to do about it. It is shown exactly as raised. The previous
        result - if there was one - is already gone by the time this runs, so
        the panel can never show one conversion beside another's refusal.
        """
        self.result = None
        self.last_failure = error
        self._render_sections(None)
        message = str(error) or repr(error)
        self._set_status(f"Refused: {message.splitlines()[0]}", style=RED)
        self.status_label.setToolTip(message)
        self._show_failure(error)

    def _set_status(self, text: str, style: str = "") -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(style)
        self.status_label.repaint()

    def _show_failure(self, error: BaseException) -> None:
        """The failure dialog. Overridden in tests, which cannot answer a modal.

        Stays a method because that override is an attribute assignment on the
        instance; the dialog itself lives in ``controls`` so both tabs raise the
        identical box.
        """
        show_failure_dialog(self, error, TAB_TITLE)
