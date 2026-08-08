"""The single window.

The whole interface, in the layout the owner approved: a settings block, a
results table, and a status line. Native widgets, standard Qt dialogs, system
fonts, no stylesheet beyond the one severity colour each in
``results_model`` and the status line (docs/method/METHOD.md section 5,
"UI look").

**This module never computes a domain value.** It collects what the user chose,
hands it to ``michspc.job.run``, and renders what comes back through
``michspc.fileio.formatting``. There is no arithmetic here — no rounding, no
unit conversion, no defaulting of an absent value. That is not a stylistic
preference: a number computed here would be a second authoritative
representation of a fact the core already owns, and the two could drift apart on
a sealed drawing.

Two behaviours are worth reading the code for:

*Longitude sign convention has no default.* When a job involves geodetic
coordinates the user must actively pick negative-west or positive-west before
Convert becomes available. The two are indistinguishable from the numbers and
choosing wrongly throws a Michigan point about 340 miles
(docs/DESIGN.md section 7).

*Failures are shown in full.* Every message this program's layers raise was
written to teach and names the offending point. They are displayed verbatim,
never summarised, never replaced with "conversion failed".
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from michspc import APP_FULL_NAME, APP_NAME
from michspc.fileio import exports, geoid
# Re-exported deliberately, not merely used: these names were defined here
# before the two-tab split (docs/DESIGN.md amendment #26) and importing them
# at module level keeps ``michspc.gui.window.UNCHOSEN`` and its neighbours
# spelled the way every existing caller and test already spells them. One
# definition, two spellings — never two definitions.
from michspc.gui.controls import (
    AMBER,
    GEODETIC,
    RED,
    UNCHOSEN,
    UNITS_LABEL,
    UNITS_LABEL_ELEVATION_ONLY,
    direction_for,
    longitude_combo,
    longitude_is_relevant,
    show_failure_dialog,
    unit_combo,
    zone_combo,
)
from michspc.gui.icon import application_icon
from michspc.gui.results_model import ResultsModel
from michspc.gui.single_point import SinglePointTab
from michspc.job import Direction, JobResult, JobSettings, LongitudeConvention, run
from michspc.spc.zones import Zone

WINDOW_TITLE = f"{APP_NAME} - {APP_FULL_NAME}"

SINGLE_POINT_TAB = "Single point"
MULTI_POINT_TAB = "Multi point"
"""The two tab captions, in the order the owner chose.

Single point is index 0 and the window opens there: it is the everyday case
(docs/DESIGN.md amendment #26). The file converter is unchanged behind the
second tab.
"""

INPUT_LABEL = "Input file:"
"""The input row's label, in every state (docs/DESIGN.md amendment #16 note 1).

Never "Input PNEZD file:". The file is only PNEZD when the conversion starts
from a State Plane zone; when it starts from geodetic positions, columns two and
three are latitude and longitude. Rather than swap the label between two
spellings, the label names the control and the hint below it names the layout,
so the control's identity stays stable.
"""

INPUT_HINT_ZONE = "No header row: point, northing, easting, elevation, description"
INPUT_HINT_GEODETIC = (
    "No header row: point, latitude, longitude, elevation, description"
)
INPUT_HINT_UNCHOSEN = (
    "No header row. The column layout follows the From selection below."
)
"""The three states of the format hint, which follows the From selection.

**This is a correctness aid, not decoration.** The two layouts are not
distinguishable from the numbers in the sense that matters: a geodetic file read
as PNEZD yields a plausible coordinate rather than an error, and the program's
easting guard (``michspc.spc.convert.easting_looks_wrong_for_zone``) only fires
on the zone branch. The hint is what tells the user, before they run anything,
which reading their file is about to be given.

The unchosen state names the dependency rather than showing the PNEZD wording.
Showing PNEZD there would be a silent default for the very question this hint
exists to ask — and defaulting a question the user was never asked is the
failure the longitude rule exists to prevent (docs/DESIGN.md section 7).
"""

UNITS_TOOLTIP_ZONE_IN = (
    "The unit the input file's northing, easting and elevation columns are "
    "written in."
)
UNITS_TOOLTIP_GEODETIC_IN = (
    "The input file's columns two and three are latitude and longitude in "
    "decimal degrees, which carry no linear unit. This selects the unit of its "
    "ELEVATION column only - and that still matters: the elevation factor and "
    "the combined factor are computed from it."
)
UNITS_TOOLTIP_ZONE_OUT = (
    "The unit the converted northing, easting and elevation are written in."
)
UNITS_TOOLTIP_GEODETIC_OUT = (
    "The export's columns two and three are latitude and longitude in decimal "
    "degrees, which carry no linear unit. This selects the unit of its "
    "ELEVATION column only - the elevation is re-expressed into it, and the "
    "job record says so."
)


# Neither the input file box nor the output folder box suggests anything: both
# start empty, with no text and no placeholder (docs/DESIGN.md amendment #27,
# which reverses #16 note 3). The Downloads lookup that used to live here —
# default_output_directory, through QStandardPaths — is deleted rather than
# left unused, so there is no dormant default for a later change to switch
# back on. Convert is gated on both fields being non-empty
# (_update_convert_enabled), so an empty output folder cannot reach
# exports.write_all; and if one ever did, that function still refuses to
# clobber, still stages and renames, and still verifies the round trip.


class MainWindow(QMainWindow):
    """The application window."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        # Cosmetic, and the only thing in this window allowed to be absent: the
        # .ico is a build product, and a source checkout that has not run
        # tools/make_icon.py must still open (michspc.gui.icon).
        self.setWindowIcon(application_icon())

        self.result: JobResult | None = None
        self.written_files: dict[str, Path] = {}
        self.last_failure: BaseException | None = None
        """The most recent exception surfaced to the user. Kept so the failure
        path is observable to a test without driving a modal dialog."""

        self._build()
        self._update_input_hint()
        self._update_unit_labels()
        self._update_longitude_relevance()
        self._update_convert_enabled()
        self.resize(1000, 640)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)

        # Index 0 is Single point and the window opens there, which is Qt's own
        # default for a fresh QTabWidget — deliberately not set explicitly, so
        # there is one statement of the order (the insertion order below) rather
        # than two that could disagree.
        self.tabs = QTabWidget(central)
        # Fully self-contained: it owns its own zone, unit and longitude-sign
        # controls and shares no state with this window, so neither tab can
        # silently alter the other (docs/DESIGN.md amendment #26).
        self.single_point = SinglePointTab(self.tabs)
        self.tabs.addTab(self.single_point, SINGLE_POINT_TAB)
        self.tabs.addTab(self._build_multi_point_tab(), MULTI_POINT_TAB)

        layout.addWidget(self.tabs)

        self.setCentralWidget(central)

    def _build_multi_point_tab(self) -> QWidget:
        """The file converter, unchanged, in the shape it always had.

        The three blocks below and their order are exactly what ``_build`` used
        to place directly in the window. Nothing about the multi-point job moved
        with it — every attribute and method is still where it was, so its tests
        describe the same object they always did.
        """
        page = QWidget(self.tabs)
        layout = QVBoxLayout(page)

        layout.addWidget(self._build_settings())
        layout.addWidget(self._build_table(), 1)
        layout.addLayout(self._build_status_line())

        return page

    def _build_settings(self) -> QWidget:
        box = QGroupBox("Conversion", self)
        grid = QGridLayout(box)

        # --- input file -------------------------------------------------
        self.input_edit = QLineEdit(box)
        # No placeholder path. The owner asked for the box to start empty
        # (docs/DESIGN.md amendment #27): a greyed-out C:\jobs\24-118\pts.csv is
        # a job number that is not his, in a folder that does not exist, sitting
        # in the field that names the file about to be read.
        self.input_edit.textChanged.connect(self._update_convert_enabled)
        self.input_browse = QPushButton("...", box)
        self.input_browse.setToolTip("Choose the coordinate file to convert")
        self.input_browse.clicked.connect(self._choose_input_file)

        self.input_label = QLabel(INPUT_LABEL, box)
        grid.addWidget(self.input_label, 0, 0)
        grid.addWidget(self.input_edit, 0, 1, 1, 3)
        grid.addWidget(self.input_browse, 0, 4)

        # The format hint sits under the field rather than inside it as
        # placeholder text, because a placeholder disappears the moment a path
        # is typed — exactly when the user most needs to know which columns the
        # file is about to be read as.
        self.input_hint = QLabel(INPUT_HINT_UNCHOSEN, box)
        self.input_hint.setTextFormat(Qt.TextFormat.PlainText)
        grid.addWidget(self.input_hint, 1, 1, 1, 3)

        # --- from / to --------------------------------------------------
        self.from_zone = zone_combo(box, self._on_direction_changed)
        self.to_zone = zone_combo(box, self._on_direction_changed)
        self.input_unit = unit_combo(box)
        self.output_unit = unit_combo(box)

        # Held as attributes rather than dropped into the layout anonymously:
        # their text follows the From/To selections (see _update_unit_labels).
        self.input_unit_label = QLabel(UNITS_LABEL, box)
        self.output_unit_label = QLabel(UNITS_LABEL, box)

        grid.addWidget(QLabel("From zone:", box), 2, 0)
        grid.addWidget(self.from_zone, 2, 1)
        grid.addWidget(self.input_unit_label, 2, 2)
        grid.addWidget(self.input_unit, 2, 3)

        grid.addWidget(QLabel("To zone:", box), 3, 0)
        grid.addWidget(self.to_zone, 3, 1)
        grid.addWidget(self.output_unit_label, 3, 2)
        grid.addWidget(self.output_unit, 3, 3)

        # --- longitude sign convention ----------------------------------
        self.longitude_label = QLabel("Longitude sign:", box)
        self.longitude_combo = longitude_combo(box, self._update_convert_enabled)

        grid.addWidget(self.longitude_label, 4, 0)
        grid.addWidget(self.longitude_combo, 4, 1, 1, 3)

        # --- elevations -------------------------------------------------
        self.elevation_in_file = QRadioButton("in file", box)
        self.elevation_in_file.setChecked(True)
        self.elevation_in_file.setToolTip(
            "Orthometric heights are read from the file's Z column and passed "
            "through unchanged; a blank or 0.00 Z means 'not recorded' and its "
            "factor columns read N/A."
        )
        geoid_label = QLabel(f"Geoid: {geoid.GEOID_MODEL_NAME} (auto)", box)
        geoid_label.setToolTip(
            "Geoid separation is looked up per point from the bundled "
            f"{geoid.GEOID_MODEL_NAME} grid."
        )

        grid.addWidget(QLabel("Elevations:", box), 5, 0)
        grid.addWidget(self.elevation_in_file, 5, 1)
        grid.addWidget(geoid_label, 5, 2, 1, 2)

        # --- output folder ----------------------------------------------
        self.output_edit = QLineEdit(box)
        # Empty, with no placeholder and no default: the owner reversed
        # amendment #16 note 3 (docs/DESIGN.md amendment #27). Downloads is not
        # where a survey job's exports belong, and a pre-filled destination is
        # answered by pressing Convert rather than by choosing. Convert stays
        # disabled until this is filled, so the empty field is a question the
        # program refuses to answer for him rather than an obstacle.
        self.output_edit.textChanged.connect(self._update_convert_enabled)
        self.output_browse = QPushButton("...", box)
        self.output_browse.setToolTip("Choose where the output archive goes")
        self.output_browse.clicked.connect(self._choose_output_directory)

        grid.addWidget(QLabel("Output folder:", box), 6, 0)
        grid.addWidget(self.output_edit, 6, 1, 1, 3)
        grid.addWidget(self.output_browse, 6, 4)

        # --- convert ----------------------------------------------------
        self.convert_button = QPushButton("Convert", box)
        self.convert_button.setDefault(True)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.convert_button)
        self.convert_button.clicked.connect(self.convert)
        grid.addLayout(buttons, 7, 0, 1, 5)

        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(3, 2)
        return box

    def _build_table(self) -> QTableView:
        self.model = ResultsModel(self)
        self.table = QTableView(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        return self.table

    def _build_status_line(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.status_label = QLabel("Ready.", self)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        # Plain text, explicitly. QLabel's default is AutoText, which guesses
        # whether a string is HTML (Qt::mightBeRichText). This label carries
        # refusal messages, and those quote arbitrary file content back - a
        # PNEZD description field is whatever the surveyor typed. A description
        # containing something the heuristic reads as a tag would be rendered
        # as markup and vanish from the message. Pinning the format takes the
        # guess out of the path entirely.
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.open_folder_button = QPushButton("Open folder", self)
        self.open_folder_button.setEnabled(False)
        self.open_folder_button.clicked.connect(self.open_output_folder)

        row.addWidget(self.status_label, 1)
        row.addWidget(self.open_folder_button)
        return row

    # ------------------------------------------------------------------
    # What the user chose
    # ------------------------------------------------------------------

    @property
    def input_path(self) -> Path | None:
        text = self.input_edit.text().strip()
        return Path(text) if text else None

    @property
    def output_directory(self) -> Path | None:
        text = self.output_edit.text().strip()
        return Path(text) if text else None

    def direction(self) -> Direction | None:
        """This tab's job, per ``controls.direction_for``, which owns the rule."""
        return direction_for(self.from_zone.currentData(), self.to_zone.currentData())

    def longitude_convention(self) -> LongitudeConvention | None:
        data = self.longitude_combo.currentData()
        return data if isinstance(data, LongitudeConvention) else None

    def settings(self) -> JobSettings | None:
        """Assemble the job settings, or None if the form is not yet complete."""
        direction = self.direction()
        if direction is None:
            return None
        if self.input_path is None or self.output_directory is None:
            return None

        source = self.from_zone.currentData()
        target = self.to_zone.currentData()
        source_zone = source if isinstance(source, Zone) else None
        target_zone = target if isinstance(target, Zone) else None

        common = dict(
            input_path=self.input_path,
            output_directory=self.output_directory,
            direction=direction,
            source_zone=source_zone,
            target_zone=target_zone,
            input_unit=self.input_unit.currentData(),
            output_unit=self.output_unit.currentData(),
            # Stated, not defaulted: the tab's static label names GEOID18, so
            # the settings say the same thing explicitly. The model dropdown
            # that makes this a choice is WP-V8 (plan section 4.3).
            geoid_model=geoid.GEOID18_MODEL,
        )

        if direction is Direction.ZONE_TO_ZONE:
            # A pure zone-to-zone job never consults the longitude convention
            # (michspc.job._convert_row), so the interface does not pretend the
            # user answered a question it never asked. The field carries no
            # default, so the absence has to be stated rather than omitted.
            return JobSettings(**common, longitude_convention=None)

        convention = self.longitude_convention()
        if convention is None:
            return None
        return JobSettings(**common, longitude_convention=convention)

    # ------------------------------------------------------------------
    # Enablement
    # ------------------------------------------------------------------

    def _on_direction_changed(self) -> None:
        self._update_input_hint()
        self._update_unit_labels()
        self._update_longitude_relevance()
        self._update_convert_enabled()

    def _update_unit_labels(self) -> None:
        """Say what each unit selector governs, given From and To.

        Reads the two dropdowns' own data, not ``direction()``: each selector
        belongs to one END of the job and must describe that end even while the
        other end is still unanswered. Nothing here computes anything - it sets
        two strings and two tooltips (see ``UNITS_LABEL_ELEVATION_ONLY`` for why
        neither selector is ever disabled).
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

    def input_hint_text(self) -> str:
        """The column layout the input file will be read as, given From.

        Reads the From selection only. The To selection cannot change how the
        input is parsed, and a hint that moved with it would be describing the
        wrong end of the job.
        """
        source = self.from_zone.currentData()
        if source == GEODETIC:
            return INPUT_HINT_GEODETIC
        if isinstance(source, Zone):
            return INPUT_HINT_ZONE
        return INPUT_HINT_UNCHOSEN

    def _update_input_hint(self) -> None:
        self.input_hint.setText(self.input_hint_text())

    def _update_longitude_relevance(self) -> None:
        """The selector matters only when geodetic coordinates are involved."""
        relevant = longitude_is_relevant(self.direction())
        self.longitude_label.setEnabled(relevant)
        self.longitude_combo.setEnabled(relevant)

    def _update_convert_enabled(self) -> None:
        self.convert_button.setEnabled(self.settings() is not None)

    # ------------------------------------------------------------------
    # Browsing
    # ------------------------------------------------------------------

    def _choose_input_file(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Choose the coordinate file",
            self.input_edit.text(),
            "Coordinate files (*.csv *.txt *.pts);;All files (*)",
        )
        if chosen:
            self.input_edit.setText(chosen)

    def _choose_output_directory(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose the output folder", self.output_edit.text()
        )
        if chosen:
            self.output_edit.setText(chosen)

    # ------------------------------------------------------------------
    # Running a job
    # ------------------------------------------------------------------

    def convert(self) -> bool:
        """Run the job and write its archive. True if everything landed.

        Responsiveness: the window shows a wait cursor and a "Converting…"
        status line, repainted synchronously, and the controls are disabled for
        the duration. There is deliberately **no worker thread**. Qt's threading
        rules are unforgiving — a widget touched from a worker thread is
        undefined behaviour that usually looks like it works — and a wrong
        threading model here is far worse than a few seconds of a frozen window
        on a file of a few thousand points. If long jobs ever justify it, the
        seam is already in the right place: ``michspc.job.run`` is pure and
        writes nothing.
        """
        settings = self.settings()
        if settings is None:
            # Convert is disabled in this state; reaching here would mean the
            # enablement logic and this method disagree, so say so rather than
            # running a half-specified job.
            self._report_failure(
                ValueError(
                    "The conversion settings are incomplete, so nothing was "
                    "run. Choose an input file, an output folder, both ends of "
                    "the conversion, and — when geodetic coordinates are "
                    "involved — the longitude sign convention."
                )
            )
            return False

        self.result = None
        self.written_files = {}
        self.last_failure = None
        self.model.set_result(None)
        self.open_folder_button.setEnabled(False)
        self._set_status("Converting…")

        # The computation is the long part; the writing is not, and the
        # overwrite prompt must not appear behind a wait cursor on a disabled
        # window. So only the run is wrapped.
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = run(settings)
        except Exception as error:  # noqa: BLE001 - shown in full, then stopped
            failure = error
        else:
            failure = None
        finally:
            QApplication.restoreOverrideCursor()
            self.setEnabled(True)

        if failure is not None:
            self._report_failure(failure)
            return False

        try:
            written = self._write(result)
        except Exception as error:  # noqa: BLE001 - shown in full, then stopped
            self._report_failure(error)
            return False

        if written is None:
            return False

        self.result = result
        self.written_files = written
        self.model.set_result(result)
        self.table.resizeColumnsToContents()
        self._report_success(result)
        return True

    def _write(self, result: JobResult) -> dict[str, Path] | None:
        """Write the job's archive, asking before clobbering anything.

        ``exports.write_all`` refuses to overwrite unless told to. That refusal
        is answered by asking the user, never by passing ``overwrite=True``
        unconditionally — the whole point of the refusal is that a job written
        into the wrong folder must not quietly destroy the previous one.
        """
        try:
            return exports.write_all(result, overwrite=False)
        except exports.WriteError as error:
            existing = self._existing_outputs(result)
            if not existing:
                raise
            if not self._ask_overwrite(existing, error):
                self._set_status("Nothing was written. The existing files were kept.")
                return None
        return exports.write_all(result, overwrite=True)

    @staticmethod
    def _existing_outputs(result: JobResult) -> list[Path]:
        """Which of this job's destinations already hold a file.

        Asks ``exports`` rather than rebuilding the naming rule here, so this
        cannot drift out of step with what write_all actually produces. The
        paths are listed to the user by name, so the overwrite prompt says
        exactly what is at risk rather than "some files exist".
        """
        return [path for path in exports.destination_paths(result) if path.exists()]

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def status_text(self, result: JobResult) -> str:
        """"<n> points converted. <m> warnings." — the owner's wording."""
        return (
            f"{len(result.points)} points converted. "
            f"{len(result.warnings)} warnings."
        )

    def _report_success(self, result: JobResult) -> None:
        warned = len(result.warnings)
        self._set_status(
            self.status_text(result),
            style=AMBER if warned else "",
        )
        if warned:
            self.status_label.setToolTip(
                "\n\n".join(
                    f"{point_id}: {warning.message}"
                    for point_id, warning in result.warnings
                )
            )
        else:
            self.status_label.setToolTip("")
        self.open_folder_button.setEnabled(True)

    def _report_failure(self, error: BaseException) -> None:
        """Surface a refusal, in full, and record it.

        Every message the layers below raise names the offending point and says
        what to do about it. It is shown exactly as raised.
        """
        self.last_failure = error
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
        show_failure_dialog(self, error, WINDOW_TITLE)

    def _ask_overwrite(self, existing: list[Path], error: BaseException) -> bool:
        """Ask before replacing files. Overridden in tests."""
        listed = "\n".join(f"  {path.name}" for path in existing)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(f"{WINDOW_TITLE} — replace existing files?")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(
            f"{len(existing)} file(s) in {existing[0].parent} would be replaced:\n\n"
            f"{listed}"
        )
        box.setInformativeText("Replace them?")
        box.setDetailedText(str(error))
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------------
    # Output folder
    # ------------------------------------------------------------------

    def output_folder_url(self) -> QUrl | None:
        """The folder the "Open folder" button would open, as a local file URL."""
        directory = self.output_directory
        if directory is None:
            return None
        return QUrl.fromLocalFile(str(directory))

    def open_output_folder(self) -> bool:
        """Hand the output folder to the shell — Explorer, on this platform."""
        url = self.output_folder_url()
        if url is None:
            return False
        return QDesktopServices.openUrl(url)
