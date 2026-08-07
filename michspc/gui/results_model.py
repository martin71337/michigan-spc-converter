"""The results table's model.

Holds nothing but strings. Every one of them was produced by
``michspc.fileio.formatting`` — the same functions the written report and the
audit CSV call — so the screen and the files on disk cannot disagree about what
a number is (docs/method/METHOD.md section 5, "UI honesty").

The model therefore performs no arithmetic at all. It does not round, it does
not scale a unit, it does not decide what an absent value looks like. Those are
domain decisions and they live one layer down.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor

from michspc.fileio import formatting as fmt
from michspc.job import Direction, JobResult

COLUMNS: tuple[str, ...] = (
    "Point",
    "Northing",
    "Easting",
    "Elevation",
    "Grid scale factor",
    "Combined factor",
    "Warnings",
)

GEODETIC_COLUMNS: tuple[str, ...] = (
    "Point",
    "Latitude",
    "Longitude",
    "Elevation",
    "Grid scale factor",
    "Combined factor",
    "Warnings",
)
"""The same seven columns, named for what a State-Plane-to-geodetic job puts
in them.

``row_strings`` has always rendered columns 1 and 2 as a latitude and a
longitude on that branch while the header still read "Northing" and "Easting",
so the table labelled 42.73250000 as a northing (WP-R2 fix H). The columns
themselves, their order, their alignment and their meaning are unchanged - only
the two names move, and only for the one direction whose values are degrees.
"""


def columns_for(result: JobResult | None) -> tuple[str, ...]:
    """The header row for a job's direction. ``COLUMNS`` until a job says else.

    An empty table shows the ordinary headings: nothing has been converted, so
    naming the columns after a direction the user has not run would be the
    interface answering a question it was not asked.
    """
    if result is not None and result.settings.direction is Direction.ZONE_TO_GEODETIC:
        return GEODETIC_COLUMNS
    return COLUMNS

POINT_COLUMN = 0
NORTHING_COLUMN = 1
EASTING_COLUMN = 2
ELEVATION_COLUMN = 3
GRID_FACTOR_COLUMN = 4
COMBINED_FACTOR_COLUMN = 5
WARNINGS_COLUMN = 6

_RIGHT_ALIGNED = frozenset(
    {
        NORTHING_COLUMN,
        EASTING_COLUMN,
        ELEVATION_COLUMN,
        GRID_FACTOR_COLUMN,
        COMBINED_FACTOR_COLUMN,
    }
)

AMBER = QColor(255, 233, 178)
"""The one colour this table paints, and it means exactly one thing.

Amber = "look at this" (docs/method/METHOD.md section 5). It marks a cell that
carries a warning. Red is reserved for a refusal — something that is actually
wrong — and a refusal never produces a table row, because the job did not
finish. Nothing else in this program is coloured.

Chosen light enough that the system's ordinary black text stays readable on it,
because the palette is otherwise the native one.
"""


def row_strings(result: JobResult) -> tuple[tuple[str, ...], ...]:
    """Render one job's points as display strings.

    The northing/easting/elevation branch below is deliberately identical to
    ``michspc.fileio.exports.clean_pnezd_rows``: when a job converts to geodetic
    the first two columns hold a latitude and a longitude, not a grid
    coordinate. The elevation is in the OUTPUT unit in every direction,
    including that one - it is the only linear column left on a geodetic
    export and the job record describes it in the output unit (WP-R2 fix A).
    If those two ever diverge, the screen would be describing a different file
    from the one written.
    """
    settings = result.settings
    to_geodetic = settings.direction is Direction.ZONE_TO_GEODETIC

    rows: list[tuple[str, ...]] = []

    for point in result.points:
        if to_geodetic:
            northing = fmt.latitude(point.output_northing)
            easting = fmt.longitude(point.output_easting)
        else:
            northing = fmt.coordinate(point.output_northing, settings.output_unit)
            easting = fmt.coordinate(point.output_easting, settings.output_unit)

        rows.append(
            (
                point.point_id,
                northing,
                easting,
                fmt.coordinate(point.output_elevation, settings.output_unit),
                fmt.factor(point.factors.grid_scale_factor),
                # combined_factor is None for a point with no usable elevation;
                # fmt.factor renders that as "N/A", never as 1.0.
                fmt.factor(point.factors.combined_factor),
                "; ".join(warning.code.value for warning in point.warnings),
            )
        )

    return tuple(rows)


class ResultsModel(QAbstractTableModel):
    """A read-only table of already-formatted strings.

    Read-only on purpose: core result records are frozen and the interface never
    mutates a computed value (docs/DESIGN.md section 4).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: tuple[tuple[str, ...], ...] = ()
        self._warning_messages: tuple[str, ...] = ()
        self._columns: tuple[str, ...] = COLUMNS

    def set_result(self, result: JobResult | None) -> None:
        self.beginResetModel()
        # The headings are settled here, with the rows, so the two can never
        # describe different jobs: a model reset repaints both together.
        self._columns = columns_for(result)
        if result is None:
            self._rows = ()
            self._warning_messages = ()
        else:
            self._rows = row_strings(result)
            self._warning_messages = tuple(
                "\n\n".join(w.message for w in point.warnings) for point in result.points
            )
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        column = index.column()
        if row < 0 or row >= len(self._rows):
            return None
        if column < 0 or column >= len(self._columns):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return self._rows[row][column]

        if role == Qt.ItemDataRole.TextAlignmentRole and column in _RIGHT_ALIGNED:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.BackgroundRole:
            if column == WARNINGS_COLUMN and self._rows[row][WARNINGS_COLUMN]:
                return QBrush(AMBER)
            return None

        if role == Qt.ItemDataRole.ToolTipRole:
            # The warning text itself, in full. The refusal-grade messages in
            # this program were written to teach; truncating them here would
            # throw that away.
            if self._warning_messages[row]:
                return self._warning_messages[row]
            return None

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._columns):
                return self._columns[section]
            return None
        return str(section + 1)
