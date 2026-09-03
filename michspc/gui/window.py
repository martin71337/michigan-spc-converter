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

from PySide6.QtCore import QMimeData, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDragMoveEvent, QDropEvent
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
from michspc.fileio import exports
# Re-exported deliberately, not merely used: these names were defined here
# before the two-tab split (docs/DESIGN.md amendment #26) and importing them
# at module level keeps ``michspc.gui.window.UNCHOSEN`` and its neighbours
# spelled the way every existing caller and test already spells them. One
# definition, two spellings — never two definitions.
from michspc.fileio import geoid
from michspc.gui.controls import (
    HEIGHT_KIND_LABEL,
    height_kind_combo,
    height_kind_for,
    AMBER,
    FRAME_RESET_STATUS,
    GEODETIC_CHOICES,
    GEOID_MODEL_LABEL,
    INPUT_GEOID_LABEL,
    OUTPUT_GEOID_LABEL,
    RED,
    UNCHOSEN,
    UNITS_LABEL,
    UNITS_LABEL_ELEVATION_ONLY,
    VERTICAL_MODE_LABEL,
    VERTICAL_SOURCE_LABEL,
    VERTICAL_TARGET_LABEL,
    direction_for,
    geodetic_choice,
    geodetic_frame_for,
    geoid_combo,
    geoid_models_for_datum,
    is_geodetic,
    longitude_combo,
    longitude_relevance,
    refresh_geoid_combo,
    refresh_unit_combo,
    refresh_zone_graying,
    selection_is_compatible,
    show_failure_dialog,
    unit_combo,
    unit_for,
    units_for_selection,
    vertical_datum_combo,
    vertical_datum_for,
    vertical_mode_buttons,
    vertical_mode_for,
    zone_combo,
)
from michspc.gui.icon import application_icon
from michspc.gui.results_model import ResultsModel
from michspc.gui.single_point import SinglePointTab
from michspc.job import (
    Direction,
    JobResult,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc.vertical import VerticalDatum
from michspc.spc.zones import Zone

WINDOW_TITLE = f"{APP_NAME} - {APP_FULL_NAME}"

SINGLE_POINT_TAB = "Single point"
MULTI_POINT_TAB = "Multi point"
"""The two tab captions, in the order the owner chose.

Single point is index 0 and the window opens there: it is the everyday case
(docs/DESIGN.md amendment #26). The file converter is unchanged behind the
second tab.
"""

ELEVATION_NOTE = "— used for combined scale factor"
"""The visible note beside the Elevations button, HORIZONTAL mode only.

The owner's instruction (DESIGN.md #48): where the "in file" button remains,
say what the elevations are FOR - they feed the elevation and combined
factor calculations - as on-screen text, not a tooltip (#34's ruling on
tooltips stands). In the two vertical modes the whole row is hidden: there
the elevations are the thing being converted, and the record and the panel
already say so.
"""

UNITS_SNAPPED_STATUS = (
    "The chosen zone does not publish that unit, so the unit was changed and "
    "the table was cleared. Nothing already written was altered. Press Convert."
)
"""Shown when the per-zone unit filter moves a selection the user made.

Three sentences because three separate things happened and a surveyor is
entitled to all of them: his unit selection was changed by the program (the
SPCS2022 zones publish metres and international feet only), the table he was
looking at was emptied because it no longer matched the controls above it, and
- the one he will worry about - the archive on disk was not touched.

"Press Convert" rather than "Ready.", the STATUS_INPUT_CHANGED reasoning of the
Single point tab: a surveyor who thought the table was still there is exactly
the person this message is for.
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


def dropped_input_file(mime: QMimeData) -> Path | None:
    """The one local file a drag carries, or None if it carries anything else.

    This is the whole rule for what the Multi point tab accepts from a drag:
    **exactly one URL, naming a local path, that is an existing file.** Every
    other payload answers None, and the drag is refused at the border so the
    cursor says so before the user lets go:

    - two or more files — which one? The program does not guess
      (docs/DESIGN.md section 7, the longitude rule's reasoning applied to a
      file);
    - a folder — it could only be meant for the output box, and routing a
      drop to a different field than the one a file lands in would be a
      second convention to learn. Folders are chosen with their own button;
    - a path that does not exist, or a URL that is not a local file — nothing
      the reader could open.

    ``is_file`` is a filesystem check, not a domain result: it is the same
    question the Browse dialog answers by only listing files, asked of a drop.
    The file's CONTENTS are not read here — the reader is the gate for those,
    unchanged, when Convert is pressed.
    """
    if not mime.hasUrls():
        return None
    urls = mime.urls()
    if len(urls) != 1 or not urls[0].isLocalFile():
        return None
    path = Path(urls[0].toLocalFile())
    return path if path.is_file() else None


class MultiPointPage(QWidget):
    """The Multi point tab's page, which accepts a dropped input file.

    The page is the drop target rather than the Input file box, so a file
    dropped ANYWHERE on the tab — on the table, the status line, the settings
    block — reaches the same handler. Qt delivers a drag to the nearest
    ancestor of the widget under the cursor that accepts drops, which is why
    ``MainWindow`` switches drops OFF on the two path boxes: a ``QLineEdit``
    accepts them by default and handles a drop as text to insert, and the
    text of a ``file://`` URL is not a path.

    The page owns no rule. It asks ``dropped_input_file`` and hands the answer
    to the callback it was built with, which is the Input file box's own
    setter — the same one the Browse dialog uses.
    """

    def __init__(self, on_file_dropped, parent=None) -> None:
        super().__init__(parent)
        self._on_file_dropped = on_file_dropped
        self.setAcceptDrops(True)

    def _consider(self, event: QDragMoveEvent) -> None:
        if dropped_input_file(event.mimeData()) is None:
            event.ignore()
        else:
            event.acceptProposedAction()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        self._consider(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        # Qt pre-accepts moves after an accepted enter, so this is belt and
        # braces: the rule is asked again rather than trusted to have been
        # asked once.
        self._consider(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        path = dropped_input_file(event.mimeData())
        if path is None:
            event.ignore()
            return
        self._on_file_dropped(path)
        event.acceptProposedAction()


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

        self._reconciling = False
        """True while this tab is clearing one zone combo because the other
        moved. See ``_reconcile_zone_frames``: the clear fires the cleared
        combo's own handler, and the outer call has to keep the status line."""

        self._build()
        self._update_input_hint()
        self._update_zone_graying()
        self._update_unit_offerings()
        self._update_unit_labels()
        self._update_longitude_relevance()
        self._update_vertical_rows()
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
        # The page is the tab's drop target for the input file: a file
        # dropped anywhere on it lands in the Input file box (DESIGN.md #65).
        page = MultiPointPage(self._accept_dropped_file, self.tabs)
        self.multi_point_page = page
        layout = QVBoxLayout(page)

        layout.addWidget(self._build_settings())
        layout.addWidget(self._build_table(), 1)
        layout.addLayout(self._build_status_line())

        return page

    def _build_settings(self) -> QWidget:
        box = QGroupBox("Conversion", self)
        grid = QGridLayout(box)

        # --- horizontal / horizontal + vertical -------------------------
        # The first row of the Conversion box, per plan section 4.1 - and on
        # THIS tab, not the window: a window-level toggle would be state
        # shared between the tabs, which amendment #26 forbids.
        (
            self.mode_horizontal,
            self.mode_vertical,
            self.mode_vertical_only,
            self._mode_group,
        ) = vertical_mode_buttons(box, self._on_vertical_mode_changed)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_horizontal)
        mode_row.addWidget(self.mode_vertical)
        mode_row.addWidget(self.mode_vertical_only)
        mode_row.addStretch(1)
        grid.addWidget(QLabel(VERTICAL_MODE_LABEL, box), 0, 0)
        grid.addLayout(mode_row, 0, 1, 1, 3)

        # --- input file -------------------------------------------------
        self.input_edit = QLineEdit(box)
        # No placeholder path. The owner asked for the box to start empty
        # (docs/DESIGN.md amendment #27): a greyed-out C:\jobs\24-118\pts.csv is
        # a job number that is not his, in a folder that does not exist, sitting
        # in the field that names the file about to be read.
        self.input_edit.textChanged.connect(self._update_convert_enabled)
        # Drops are the PAGE's, not the box's (MultiPointPage). Left on, the
        # box would catch a file dropped on it and treat it as text.
        self.input_edit.setAcceptDrops(False)
        self.input_browse = QPushButton("...", box)
        self.input_browse.setToolTip("Choose the coordinate file to convert")
        self.input_browse.clicked.connect(self._choose_input_file)

        self.input_label = QLabel(INPUT_LABEL, box)
        grid.addWidget(self.input_label, 1, 0)
        grid.addWidget(self.input_edit, 1, 1, 1, 3)
        grid.addWidget(self.input_browse, 1, 4)

        # The format hint sits under the field rather than inside it as
        # placeholder text, because a placeholder disappears the moment a path
        # is typed — exactly when the user most needs to know which columns the
        # file is about to be read as.
        self.input_hint = QLabel(INPUT_HINT_UNCHOSEN, box)
        self.input_hint.setTextFormat(Qt.TextFormat.PlainText)
        grid.addWidget(self.input_hint, 2, 1, 1, 3)

        # --- from / to --------------------------------------------------
        # One handler per END, not one shared: the reconciliation rule has to
        # know which side the user just moved, because it is the OTHER side
        # that gets cleared when the pair becomes incompatible.
        self.from_zone = zone_combo(box, self._on_from_zone_changed)
        self.to_zone = zone_combo(box, self._on_to_zone_changed)
        self.input_unit = unit_combo(box)
        self.output_unit = unit_combo(box)

        # Held as attributes rather than dropped into the layout anonymously:
        # their text follows the From/To selections (see _update_unit_labels).
        self.input_unit_label = QLabel(UNITS_LABEL, box)
        self.output_unit_label = QLabel(UNITS_LABEL, box)

        grid.addWidget(QLabel("From zone:", box), 3, 0)
        grid.addWidget(self.from_zone, 3, 1)
        grid.addWidget(self.input_unit_label, 3, 2)
        grid.addWidget(self.input_unit, 3, 3)

        # Held as an attribute so vertical-only mode can hide the whole row:
        # no output horizontal system exists in that mode, and a visible "To
        # zone" dropdown would be a question the job never asks.
        self.to_zone_label = QLabel("To zone:", box)
        grid.addWidget(self.to_zone_label, 4, 0)
        grid.addWidget(self.to_zone, 4, 1)
        grid.addWidget(self.output_unit_label, 4, 2)
        grid.addWidget(self.output_unit, 4, 3)

        # --- vertical datums --------------------------------------------
        # Directly under the To zone row: they are the vertical job's own
        # from/to pair. Revealed by Horizontal + Vertical and hidden - not
        # disabled - by Horizontal (plan section 4.2): a disabled control that
        # never becomes relevant in this mode is clutter, where the longitude
        # selector is disabled because it becomes relevant again. Both open
        # unanswered; the datum combos gate Convert through settings().
        self.vertical_source_label = QLabel(VERTICAL_SOURCE_LABEL, box)
        self.vertical_source_combo = vertical_datum_combo(
            box, self._on_vertical_datum_changed
        )
        self.vertical_target_label = QLabel(VERTICAL_TARGET_LABEL, box)
        self.vertical_target_combo = vertical_datum_combo(
            box, self._on_vertical_datum_changed
        )

        grid.addWidget(self.vertical_source_label, 5, 0)
        grid.addWidget(self.vertical_source_combo, 5, 1, 1, 3)
        grid.addWidget(self.vertical_target_label, 6, 0)
        grid.addWidget(self.vertical_target_combo, 6, 1, 1, 3)

        # --- input-side geoid model -------------------------------------
        # Directly under the datum rows it is filtered by (the owner's
        # per-side feature, 2026-08-09): which geoid model the INPUT
        # elevations are stated against. Vertical-mode furniture, hidden in
        # Horizontal exactly as the datum rows are; DISABLED - grayed, the
        # owner's explicit word, not hidden - when its side's datum is
        # unanswered or has no published model (NGVD 29). Populated and
        # refreshed by _refresh_geoid_sides, which owns the filter for both
        # sides.
        self.input_geoid_label = QLabel(INPUT_GEOID_LABEL, box)
        self.input_geoid_combo = geoid_combo(box)

        grid.addWidget(self.input_geoid_label, 7, 0)
        grid.addWidget(self.input_geoid_combo, 7, 1, 1, 3)

        # --- longitude sign convention ----------------------------------
        self.longitude_label = QLabel("Longitude sign:", box)
        self.longitude_combo = longitude_combo(box, self._update_convert_enabled)

        grid.addWidget(self.longitude_label, 8, 0)
        grid.addWidget(self.longitude_combo, 8, 1, 1, 3)

        # --- elevations -------------------------------------------------
        # The whole row is HORIZONTAL-mode furniture, hidden by
        # _update_vertical_rows when elevations convert (the owner's
        # instruction, DESIGN.md #48): in Horizontal + Vertical and Vertical
        # modes the elevations MUST be in the file - the modes exist to
        # convert them - so a button stating the only possibility is a
        # question the job never asks, and its "passed through unchanged"
        # tooltip would be a false sentence in exactly those modes. Where the
        # button remains, a visible note says what the elevations are FOR.
        self.elevations_label = QLabel("Elevations:", box)
        self.elevation_in_file = QRadioButton("in file", box)
        self.elevation_in_file.setChecked(True)
        # "Passed through unchanged" was false twice over: false in the two
        # vertical modes (the shift is the whole point there - this button is
        # now hidden in them), and imprecise even here, because a differing
        # output unit re-expresses the value (900.000 ift is written as
        # 274.3200 m; the height is the same, the number is not). The Codex
        # cross-check's counterexample, DESIGN.md #48.
        self.elevation_in_file.setToolTip(
            "Orthometric heights are read from the file's Z column. They are "
            "not converted between vertical datums in this mode; a differing "
            "output unit re-expresses the value. A blank or 0.00 Z means "
            "'not recorded' and its factor columns read N/A."
        )
        self.elevation_note = QLabel(ELEVATION_NOTE, box)
        # The geoid model dropdown, replacing the static "Geoid: GEOID18
        # (auto)" label (WP-V8, plan section 4.3). Visible in BOTH modes: the
        # geoid governs the elevation and combined factors whether or not the
        # elevations are converted between vertical datums. No handler - this
        # tab's table describes the archive a run wrote, not the current
        # controls, and the model reaches the job through settings().
        self.geoid_label = QLabel(GEOID_MODEL_LABEL, box)
        self.geoid_combo = geoid_combo(box)

        # The height-kind control sits BENEATH the "in file" button, the
        # owner's placement (2026-08-11), so the cell became a two-row stack.
        # Stacking rather than inserting a grid row keeps every row index
        # below this one exactly where it was, which is the lower-risk change
        # for a layout the owner has already approved.
        self.height_kind_label = QLabel(HEIGHT_KIND_LABEL, box)
        self.height_kind_combo = height_kind_combo(box)
        self.height_kind_combo.currentIndexChanged.connect(
            self._update_convert_enabled
        )
        self.elevation_in_file.toggled.connect(
            self._update_elevation_dependent_enabled
        )

        elevations_cell = QWidget(box)
        stacked = QVBoxLayout(elevations_cell)
        stacked.setContentsMargins(0, 0, 0, 0)
        beside = QHBoxLayout()
        beside.setContentsMargins(0, 0, 0, 0)
        beside.addWidget(self.elevation_in_file)
        beside.addWidget(self.elevation_note)
        beside.addStretch(1)
        stacked.addLayout(beside)
        kind_row = QHBoxLayout()
        kind_row.setContentsMargins(0, 0, 0, 0)
        kind_row.addWidget(self.height_kind_label)
        kind_row.addWidget(self.height_kind_combo)
        kind_row.addStretch(1)
        stacked.addLayout(kind_row)

        grid.addWidget(self.elevations_label, 9, 0)
        grid.addWidget(elevations_cell, 9, 1)
        grid.addWidget(self.geoid_label, 9, 2)
        grid.addWidget(self.geoid_combo, 9, 3)

        # --- output folder ----------------------------------------------
        self.output_edit = QLineEdit(box)
        # Empty, with no placeholder and no default: the owner reversed
        # amendment #16 note 3 (docs/DESIGN.md amendment #27). Downloads is not
        # where a survey job's exports belong, and a pre-filled destination is
        # answered by pressing Convert rather than by choosing. Convert stays
        # disabled until this is filled, so the empty field is a question the
        # program refuses to answer for him rather than an obstacle.
        self.output_edit.textChanged.connect(self._update_convert_enabled)
        # Same as the input box: a file dropped here goes to the page, which
        # routes it to the Input file box. The output folder is chosen with
        # its own button; a dropped folder is refused (dropped_input_file).
        self.output_edit.setAcceptDrops(False)
        self.output_browse = QPushButton("...", box)
        self.output_browse.setToolTip("Choose where the output archive goes")
        self.output_browse.clicked.connect(self._choose_output_directory)

        grid.addWidget(QLabel("Output folder:", box), 10, 0)
        grid.addWidget(self.output_edit, 10, 1, 1, 3)
        grid.addWidget(self.output_browse, 10, 4)

        # --- convert ----------------------------------------------------
        self.convert_button = QPushButton("Convert", box)
        self.convert_button.setDefault(True)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.convert_button)
        self.convert_button.clicked.connect(self.convert)
        grid.addLayout(buttons, 11, 0, 1, 5)

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

    def vertical_mode(self) -> VerticalMode:
        """What the mode toggle states; ``controls.vertical_mode_for`` owns the rule."""
        return vertical_mode_for(
            self.mode_horizontal, self.mode_vertical, self.mode_vertical_only
        )

    def source_vertical_datum(self) -> VerticalDatum | None:
        return vertical_datum_for(self.vertical_source_combo.currentData())

    def target_vertical_datum(self) -> VerticalDatum | None:
        return vertical_datum_for(self.vertical_target_combo.currentData())

    def output_geoid_model(self) -> geoid.GeoidModel | None:
        """The model ``JobSettings.geoid_model`` gets from this tab.

        Horizontal mode reads the combo exactly as it always has - the full
        registry list always holds a model. In the vertical modes the combo
        is the OUTPUT side, filtered per datum, and a grayed side states
        None: its datum has no published geoid model, so no model is
        emitted rather than one the job would refuse (the per-side rule the
        graying exists to state).
        """
        if not self.vertical_mode().converts_elevations:
            return self.geoid_combo.currentData()
        data = (
            self.geoid_combo.currentData()
            if self.geoid_combo.isEnabled()
            else None
        )
        return data if isinstance(data, geoid.GeoidModel) else None

    def input_geoid_model(self) -> geoid.GeoidModel | None:
        """The model ``JobSettings.source_geoid_model`` gets from this tab.

        None in Horizontal mode - the hidden combo is never read, the
        datum-row idiom - and None from a grayed side in the vertical
        modes, for the reason ``output_geoid_model`` states.
        """
        if not self.vertical_mode().converts_elevations:
            return None
        data = (
            self.input_geoid_combo.currentData()
            if self.input_geoid_combo.isEnabled()
            else None
        )
        return data if isinstance(data, geoid.GeoidModel) else None

    def settings(self) -> JobSettings | None:
        """Assemble the job settings, or None if the form is not yet complete."""
        if self.input_path is None or self.output_directory is None:
            return None

        if self.vertical_mode() is VerticalMode.VERTICAL:
            return self._vertical_only_settings()

        direction = self.direction()
        if direction is None:
            return None

        # A vertical job needs both datums answered before it is a job at all
        # (plan section 4.4); a horizontal job states None for both, which is
        # the statement job.run requires of it - a horizontal job supplied
        # with a datum is refused there. The refusal matrix itself stays in
        # job.run: this method only decides whether the form is complete,
        # never whether a completed form's combination is convertible, so a
        # pair the registry refuses reaches the job and comes back as the
        # registry's own teaching message rather than a greyed-out control.
        mode = self.vertical_mode()
        if mode is VerticalMode.HORIZONTAL_AND_VERTICAL:
            source_datum = self.source_vertical_datum()
            target_datum = self.target_vertical_datum()
            if source_datum is None or target_datum is None:
                return None
        else:
            source_datum = None
            target_datum = None

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
            input_unit=unit_for(self.input_unit),
            output_unit=unit_for(self.output_unit),
            # From the dropdowns (WP-V8, plan section 4.3; per-side since
            # the owner's 2026-08-09 feature), exactly as the two unit
            # combos are read: the combos offer only registry records, and
            # job.run refuses an impostor by name. A grayed side emits
            # None - its datum has no published model.
            geoid_model=self.output_geoid_model(),
            input_height_kind=height_kind_for(self.height_kind_combo),
            source_geoid_model=self.input_geoid_model(),
            vertical_mode=mode,
            source_vertical_datum=source_datum,
            target_vertical_datum=target_datum,
        )

        # The frame the geodetic END is in, straight off the selection that
        # names it (H6, DESIGN.md #62). Stated only when there IS a geodetic
        # end: a zone-to-zone job never reads this field, and its two zones
        # carry their own frames, so telling the settings anything here would
        # be an answer to a question the job does not ask. A pair whose frames
        # have no published path - this frame against a zone in the other era -
        # is refused by job.run before the file is read, in the frame
        # registry's own words; the interface deliberately does not pre-filter
        # it (#33: this program informs, it does not decide).
        frame = geodetic_frame_for(source, target)
        if frame is not None:
            common["geodetic_frame"] = frame

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

    def _vertical_only_settings(self) -> JobSettings | None:
        """The vertical-only job this tab's controls describe, or None.

        The From selection is the INPUT system - a zone, or the Geodetic
        entry stated as ``source_zone=None`` - and there is no output system:
        ``target_zone`` is None and ``output_unit`` IS the input unit, because
        the exports reproduce the input's columns and ``job.run`` refuses a
        mismatch. The To dropdown and the output unit selector are hidden in
        this mode and deliberately not read. The longitude convention follows
        the same rule the core enforces: stated for a geodetic input, None
        for a zone input.
        """
        source = self.from_zone.currentData()
        if source == UNCHOSEN:
            return None
        source_zone = source if isinstance(source, Zone) else None

        source_datum = self.source_vertical_datum()
        target_datum = self.target_vertical_datum()
        if source_datum is None or target_datum is None:
            return None

        input_unit = unit_for(self.input_unit)
        common = dict(
            input_path=self.input_path,
            output_directory=self.output_directory,
            direction=Direction.VERTICAL_ONLY,
            source_zone=source_zone,
            target_zone=None,
            input_unit=input_unit,
            output_unit=input_unit,
            geoid_model=self.output_geoid_model(),
            input_height_kind=height_kind_for(self.height_kind_combo),
            source_geoid_model=self.input_geoid_model(),
            vertical_mode=VerticalMode.VERTICAL,
            source_vertical_datum=source_datum,
            target_vertical_datum=target_datum,
        )

        # Only one side exists in this mode, so only one side can be geodetic.
        frame = geodetic_frame_for(source)
        if frame is not None:
            common["geodetic_frame"] = frame

        if source_zone is not None:
            # The file carries no longitudes and none are written - the
            # zone-to-zone statement rule, which job.run enforces.
            return JobSettings(**common, longitude_convention=None)

        convention = self.longitude_convention()
        if convention is None:
            return None
        return JobSettings(**common, longitude_convention=convention)

    # ------------------------------------------------------------------
    # Enablement
    # ------------------------------------------------------------------

    def _on_from_zone_changed(self) -> None:
        """The From end moved, so the To end may no longer be reachable."""
        self._reconcile_zone_frames(clear=self.to_zone)
        self._on_direction_changed()

    def _on_to_zone_changed(self) -> None:
        """The To end moved, so the From end may no longer reach it."""
        self._reconcile_zone_frames(clear=self.from_zone)
        self._on_direction_changed()

    def _reconcile_zone_frames(self, clear) -> None:
        """Clear the side that the other end just made unreachable.

        Graying stops a user CHOOSING an incompatible entry; it cannot undo a
        pair that became incompatible because the other end moved under it. So
        the side that did not move is reset to the placeholder and the status
        line says why - the alternative is a selection sitting in a combo where
        it is now grayed out, which states two things at once.

        **Reentrancy is guarded, not avoided.** Clearing the other combo fires
        its own handler, which arrives back here; the flag lets that pass
        through so the outer call keeps ownership of the status line. Without
        it the inner ``_on_direction_changed`` would overwrite the message that
        explains what just happened.

        Vertical-only mode is exempt: there is no output system in that mode,
        the To dropdown is hidden, and a hidden control must not clear a
        visible one (``_update_zone_graying`` says the same thing about the
        graying itself).
        """
        if self._reconciling:
            return
        if self.vertical_mode() is VerticalMode.VERTICAL:
            return

        other = self.from_zone if clear is self.to_zone else self.to_zone
        if selection_is_compatible(
            clear.currentData(),
            other.currentData(),
            candidate_is_source=clear is self.from_zone,
        ):
            return

        self._reconciling = True
        try:
            clear.setCurrentIndex(clear.findData(UNCHOSEN))
        finally:
            self._reconciling = False
        self._clear_table()
        self._set_status(FRAME_RESET_STATUS)

    def _update_zone_graying(self) -> None:
        """Gray each end's incompatible entries against the other end.

        **The one owner of these two combos' item flags on this tab** - the
        #57 rule, and it is pinned by an AST scan rather than by hoping: that
        amendment's defect was two methods driving one property, with the later
        call winning, and item flags are a property in exactly the same sense.

        ``controls.refresh_zone_graying`` owns WHICH items, so this tab and the
        Single point tab cannot gray differently.

        In vertical-only mode nothing is grayed: the To dropdown is hidden and
        the From selection is the only system in the job, so an invisible
        control must not gray a visible one. Passing UNCHOSEN is how that is
        said - it is the same "the other end has answered nothing" state the
        rule already has, rather than a second branch in the rule.
        """
        vertical_only = self.vertical_mode() is VerticalMode.VERTICAL
        source = UNCHOSEN if vertical_only else self.from_zone.currentData()
        target = UNCHOSEN if vertical_only else self.to_zone.currentData()
        refresh_zone_graying(self.from_zone, target, is_source=True)
        refresh_zone_graying(self.to_zone, source, is_source=False)

    def _on_direction_changed(self) -> None:
        self._update_input_hint()
        self._update_zone_graying()
        self._update_unit_offerings()
        self._update_unit_labels()
        self._update_longitude_relevance()
        self._update_convert_enabled()

    def _update_unit_offerings(self) -> None:
        """Offer each end only the units its own selection publishes.

        The one owner of these two combos' item lists, so nothing else rebuilds
        them (the #57 defect was two methods driving one property, and this is
        the same shape one property along). ``controls`` owns the rule -
        ``units_for_selection`` reads ``Zone.allowed_units``, the authoritative
        statement - and ``job._require_units_the_zones_publish`` enforces the
        identical tuple on the settings, so this narrowing is a convenience
        over the gate and never a second rule.

        Neither combo is ever disabled here; see ``refresh_unit_combo``.

        **A forced swap discards the table.** SPCS2022 publishes metres and
        international feet only, so a job left on US survey feet has its unit
        changed for it when a 2022 zone is chosen - by the program, not by the
        user - and the table above would then be showing an archive's numbers
        under a unit selector that no longer describes them. That is the
        amendment #26 / #43 stale-display class reaching this tab through a
        control nobody touched.
        """
        snapped = refresh_unit_combo(
            self.input_unit, units_for_selection(self.from_zone.currentData())
        )
        snapped |= refresh_unit_combo(
            self.output_unit, units_for_selection(self.to_zone.currentData())
        )
        if snapped and self._clear_table():
            self._set_status(UNITS_SNAPPED_STATUS)

    def _clear_table(self) -> bool:
        """Empty the results table. True if something was on screen.

        The mechanism only; the caller says WHY, because the two reasons this
        tab clears its table are different sentences - a unit the program
        swapped, and a selection the program cleared. One clearing, two
        messages, rather than two clearings that could drift apart.

        **Narrower than the Single point tab's ``_invalidate_result``, on
        purpose.** This tab's table describes an archive that was WRITTEN, not
        the current controls, so it does not clear when a control moves - the
        files on disk are unchanged and their own record states the units they
        were written in. It clears for the two cases where leaving it would
        show numbers the controls above them contradict: a unit the program
        itself swapped, and a selection the program itself cleared.

        "Open folder" is disarmed with the table because it points at the run
        the table described. Nothing on disk is touched - the archive is still
        there and still correct - and the unit message says that outright.

        Idempotent: costs nothing when there is no result on screen, which is
        what the return value is for.
        """
        if self.result is None and self.model.rowCount() == 0:
            return False
        self.result = None
        self.written_files = {}
        self.model.set_result(None)
        self.open_folder_button.setEnabled(False)
        self.status_label.setToolTip("")
        return True

    def _update_unit_labels(self) -> None:
        """Say what each unit selector governs, given From and To.

        Reads the two dropdowns' own data, not ``direction()``: each selector
        belongs to one END of the job and must describe that end even while the
        other end is still unanswered. Nothing here computes anything - it sets
        two strings and two tooltips (see ``UNITS_LABEL_ELEVATION_ONLY`` for why
        neither selector is ever disabled).
        """
        source_is_geodetic = is_geodetic(self.from_zone.currentData())
        target_is_geodetic = is_geodetic(self.to_zone.currentData())

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
        if is_geodetic(source):
            return INPUT_HINT_GEODETIC
        if isinstance(source, Zone):
            return INPUT_HINT_ZONE
        return INPUT_HINT_UNCHOSEN

    def _update_input_hint(self) -> None:
        self.input_hint.setText(self.input_hint_text())

    def _update_longitude_relevance(self) -> None:
        """The selector matters only when geodetic coordinates are involved;
        ``controls.longitude_relevance`` owns the rule for all three modes."""
        relevant = longitude_relevance(
            self.vertical_mode(), self.from_zone.currentData(), self.direction()
        )
        self.longitude_label.setEnabled(relevant)
        self.longitude_combo.setEnabled(relevant)

    def _on_vertical_mode_changed(self) -> None:
        self._update_vertical_rows()
        # Leaving vertical-only mode brings the To dropdown back, and its
        # selection is the one thing the user could not see while the From end
        # moved - so the pair is reconciled on the way out, clearing To if the
        # two ends no longer reach each other, and the graying is reapplied
        # either way. Entering the mode is the same call and simply grays
        # nothing, which is what "no pairing in this mode" means.
        self._reconcile_zone_frames(clear=self.to_zone)
        self._update_zone_graying()
        self._update_longitude_relevance()
        self._update_convert_enabled()

    def _on_vertical_datum_changed(self) -> None:
        """What both datum combos are wired to: a datum decides which geoid
        models its side may offer (the per-side registry filter), so the
        geoid combos refresh with it - then the gate, as before."""
        self._refresh_geoid_sides()
        self._update_convert_enabled()

    def _refresh_geoid_sides(self) -> None:
        """Make both geoid combos offer what the mode and datums allow.

        The one place the per-side filter meets this tab's controls
        (``controls.geoid_models_for_datum`` owns the rule): in Horizontal
        the single combo keeps the full registry list under its standing
        label; in the vertical modes each side filters by its own datum,
        and a side with no models is DISABLED - grayed, the owner's word -
        rather than hidden or left enabled over an empty list.
        """
        mode = self.vertical_mode()
        if not mode.converts_elevations:
            self.geoid_label.setText(GEOID_MODEL_LABEL)
            refresh_geoid_combo(self.geoid_combo, geoid.ALL_GEOID_MODELS)
            refresh_geoid_combo(
                self.input_geoid_combo,
                geoid_models_for_datum(self.source_vertical_datum()),
            )
            return
        self.geoid_label.setText(OUTPUT_GEOID_LABEL)
        refresh_geoid_combo(
            self.geoid_combo,
            geoid_models_for_datum(self.target_vertical_datum()),
        )
        refresh_geoid_combo(
            self.input_geoid_combo,
            geoid_models_for_datum(self.source_vertical_datum()),
        )

    def _update_vertical_rows(self) -> None:
        """Show the datum rows when elevations convert; hide the output
        horizontal controls in vertical-only mode.

        Hidden, not disabled, in both directions of this method (plan section
        4.2). The combos keep whatever answer they held, so toggling modes
        does not silently discard a chosen datum or a chosen To zone - but a
        job that does not consult a hidden control never reads it:
        ``settings`` states None for the datums of a horizontal job, and a
        vertical-only job never reads the To zone or the output unit.
        """
        mode = self.vertical_mode()
        for widget in (
            self.vertical_source_label,
            self.vertical_source_combo,
            self.vertical_target_label,
            self.vertical_target_combo,
            # The input-side geoid row is vertical-mode furniture exactly as
            # the datum rows it filters by are: hidden in Horizontal (the
            # question does not apply), visible in both vertical modes -
            # where a side with no models is GRAYED by
            # _refresh_geoid_sides, never hidden (the owner's distinction,
            # 2026-08-09).
            self.input_geoid_label,
            self.input_geoid_combo,
        ):
            widget.setVisible(mode.converts_elevations)
        # The mode also decides each geoid combo's offering and label
        # (Horizontal's full list vs the vertical modes' per-datum filter).
        self._refresh_geoid_sides()
        # The Elevations row is the mirror image (owner's instruction,
        # DESIGN.md #48): in the two vertical modes the elevations must be in
        # the file - the mode exists to convert them - so the "in file"
        # button states the only possibility, and its "passed through
        # unchanged" tooltip would be false there. Hidden with its label and
        # its note; the geoid dropdown beside them stays in every mode.
        #
        # AMENDED for the height-kind control (the owner's instruction,
        # 2026-08-11): #48's reasoning covers the "in file" BUTTON and its
        # note, and only those. The question "what kind of height is this?"
        # is asked in every mode, and matters MOST in the vertical ones,
        # where the answer decides whether the Z column gets converted at
        # all - so the label and the kind control stay visible while the
        # button and its note still hide.
        for widget in (self.elevation_in_file, self.elevation_note):
            widget.setVisible(not mode.converts_elevations)
        for widget in (
            self.elevations_label,
            self.height_kind_label,
            self.height_kind_combo,
        ):
            widget.setVisible(True)
        self._update_elevation_dependent_enabled()
        # No output horizontal system exists in vertical-only mode (the To
        # row), and the export mirrors the input's unit (the output Units
        # selector) - visible, either control would be a question this job
        # never asks.
        vertical_only = mode is VerticalMode.VERTICAL
        for widget in (
            self.to_zone_label,
            self.to_zone,
            self.output_unit_label,
            self.output_unit,
        ):
            widget.setVisible(not vertical_only)

    def _update_elevation_dependent_enabled(self) -> None:
        """Gray the controls that only matter when elevations are read.

        The owner's instruction, 2026-08-11. In HORIZONTAL mode, with no
        elevations in the file, there is no height to look a geoid separation
        up FOR: every factor that would use it reads N/A, so the model choice
        changes nothing the job produces and the dropdown says so by graying.

        Only in horizontal mode. In the two vertical modes the geoid is
        load-bearing whatever the "in file" button says - it is what converts
        the heights - so it stays live there, and the button itself is hidden
        anyway (#48).

        Grayed rather than hidden, the owner's standing distinction (#50): a
        disabled dropdown shows that the question exists and does not apply.
        """
        elevations = self.elevation_in_file.isChecked()
        self.height_kind_combo.setEnabled(elevations)
        # ONLY EVER DISABLES, and only in horizontal mode. In the vertical
        # modes the output geoid's enablement belongs entirely to
        # _refresh_geoid_sides, which grays it when its side's datum has no
        # published model (NGVD 29). Writing `setEnabled(vertical or
        # elevations)` here instead re-enabled it in exactly that case and
        # broke that rule - two methods driving one property, the later call
        # winning. Caught by #50's own graying pin.
        if not self.vertical_mode().converts_elevations:
            self.geoid_combo.setEnabled(elevations)

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
            self._set_input_file(chosen)

    def _accept_dropped_file(self, path: Path) -> None:
        """The page's drop, routed to the box the Browse dialog fills.

        ``toLocalFile`` spells the path the way ``QFileDialog`` does (forward
        slashes on Windows), so the box reads the same whichever way the file
        arrived, and ``input_path`` and ``job.run`` see one convention.
        """
        self._set_input_file(QUrl.fromLocalFile(str(path)).toLocalFile())

    def _set_input_file(self, text: str) -> None:
        """The one setter for the Input file box.

        Browse and drop both end here, so the ``textChanged`` gate that arms
        Convert fires the same way for both, and this tab's table follows its
        own policy (``_clear_table``) for both.
        """
        self.input_edit.setText(text)

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
                    "the conversion, the longitude sign convention when "
                    "geodetic coordinates are involved, and both vertical "
                    "datums when vertical mode is on."
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
