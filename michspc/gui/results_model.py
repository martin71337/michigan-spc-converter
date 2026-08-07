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

from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor

from michspc.fileio import formatting as fmt
from michspc.gui.controls import zone_label
from michspc.job import Direction, JobResult, LongitudeConvention

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


# --------------------------------------------------------------------------
# The single-point results display (docs/DESIGN.md amendment #26).
#
# Pure functions of a JobResult, and widgets are built from what they return.
# Nothing below touches Qt, which is what lets the layout the owner approved be
# asserted label by label without a QApplication - and what keeps the layout a
# statement about the conversion rather than a property of some widget tree.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultValue:
    """One labelled line of a results section. Both fields are display text."""

    label: str
    text: str


@dataclass(frozen=True)
class ResultSection:
    """One titled block of a single-point result: INPUT or OUTPUT."""

    title: str
    values: tuple[ResultValue, ...]


INPUT_TITLE = "INPUT"
OUTPUT_TITLE = "OUTPUT"

WARNINGS_LABEL = "Warnings"

NO_WARNINGS = "none"
"""What the warnings line says when the conversion raised none.

Not a blank, which in a list of labelled values reads as an oversight, and not
``formatting.NOT_AVAILABLE``: "N/A" is reserved for a quantity that is genuinely
absent and unknowable, and "this point raised no warnings" is neither - it is a
result, and it is the good one.
"""

# The labels below are section-relative on purpose. exports.AUDIT_COLUMNS spells
# the same quantities "Source northing", "Target northing", "Source grid scale
# factor" and so on because the audit CSV is one flat row per point and has to
# say which end it means. Here the INPUT and OUTPUT titles say it, so the
# prefixes would be repeating the heading. Every other word is the audit CSV's
# own, including the "(m)" on the two heights, so that the screen and
# <stem>_full.csv name the same thing the same way.
#
# The one qualifier deliberately NOT carried over is the audit CSV's
# "Longitude (neg west)". The DMS line beside it ends in a hemisphere letter,
# and that letter is what states the convention (docs/DESIGN.md amendment #26):
# -84 deg 33' 19.80000" W says both where the point is and how the number was
# written, which is what the parenthesis existed to say.
ZONE_LABEL = "Zone"
UNITS_LABEL = "Units"
NORTHING_LABEL = "Northing"
EASTING_LABEL = "Easting"
ELEVATION_LABEL = "Elevation"
LATITUDE_LABEL = "Latitude"
LATITUDE_DMS_LABEL = "Latitude (DMS)"
LONGITUDE_LABEL = "Longitude"
LONGITUDE_DMS_LABEL = "Longitude (DMS)"
GRID_FACTOR_LABEL = "Grid scale factor"
CONVERGENCE_LABEL = "Convergence"
GEOID_HEIGHT_LABEL = "Geoid height (m)"
ELLIPSOID_HEIGHT_LABEL = "Ellipsoid height (m)"
ELEVATION_FACTOR_LABEL = "Elevation factor"
COMBINED_FACTOR_LABEL = "Combined factor"


def _units_text(unit) -> str:
    """"International feet (ift)" - the name and the code, never one alone."""
    return f"{unit.name} ({unit.code})"


def _warnings_text(point) -> str:
    """Every warning this point raised, in full, or ``NO_WARNINGS``.

    The messages themselves, joined by a blank line, exactly as the multi-point
    table's tooltip does. The refusal-grade wording in this program was written
    to teach; a single-point display has the room, so it shows the sentences
    rather than the warning codes the table has to compress into a cell.
    """
    if not point.warnings:
        return NO_WARNINGS
    return "\n\n".join(warning.message for warning in point.warnings)


def _positive_west(settings) -> bool:
    """Whether this job's longitudes are written positive west.

    ``None`` - a zone-to-zone job, which never asks - is negative west, which is
    what the program stores internally and what the hemisphere letter then
    declares on screen.
    """
    return settings.longitude_convention is LongitudeConvention.POSITIVE_WEST


def _geodetic_values(conversion, positive_west: bool) -> tuple[ResultValue, ...]:
    """Latitude and longitude, each in decimal degrees and then in DMS.

    Built from ``conversion.latitude`` and ``conversion.longitude`` - the signed
    pivot the core stores - in every direction, rather than from the row's own
    columns, and that choice is load-bearing rather than convenient.

    The displayed NUMBER is identical either way: ``LongitudeConvention``'s
    ``to_signed`` and ``from_signed`` are the same exact IEEE negation, so
    ``fmt.longitude(conversion.longitude, positive_west=...)`` and
    ``fmt.longitude(point.row.easting)`` produce the same characters for a
    geodetic input, and the same holds for ``point.output_easting`` on the way
    out. What differs is the hemisphere LETTER. It is geographic - a fact about
    where the point is, not about how the number was written - so it must be
    read from the signed value. Handed the user's own positive-west 84.5555 with
    nothing said about the convention, ``longitude_dms`` could only call it E,
    and a Michigan longitude labelled "east" on screen is the kind of quiet
    falsehood this program exists to refuse (docs/DESIGN.md amendment #26: the
    letter is "always W in Michigan").
    """
    return (
        ResultValue(LATITUDE_LABEL, fmt.latitude(conversion.latitude)),
        ResultValue(LATITUDE_DMS_LABEL, fmt.latitude_dms(conversion.latitude)),
        ResultValue(
            LONGITUDE_LABEL,
            fmt.longitude(conversion.longitude, positive_west=positive_west),
        ),
        # No convention flag: a DMS longitude is magnitude plus a hemisphere
        # letter, and the magnitude is the same number either way.
        ResultValue(LONGITUDE_DMS_LABEL, fmt.longitude_dms(conversion.longitude)),
    )


def _grid_values(zone, unit, northing, easting, elevation) -> tuple[ResultValue, ...]:
    """Zone, units and the three linear columns, in that order."""
    return (
        ResultValue(ZONE_LABEL, zone_label(zone)),
        ResultValue(UNITS_LABEL, _units_text(unit)),
        ResultValue(NORTHING_LABEL, fmt.coordinate(northing, unit)),
        ResultValue(EASTING_LABEL, fmt.coordinate(easting, unit)),
        ResultValue(ELEVATION_LABEL, fmt.coordinate(elevation, unit)),
    )


def _elevation_dependent_values(factors) -> tuple[ResultValue, ...]:
    """The four quantities that exist only because the point had an elevation.

    Every one of them is None for a point with no usable elevation, and
    ``fmt`` renders that as "N/A" - never as a plausible 1.0, which is the
    convention this program is built on (docs/DESIGN.md section 7).
    """
    return (
        ResultValue(GEOID_HEIGHT_LABEL, fmt.geoid_height(factors.geoid_height)),
        ResultValue(
            ELLIPSOID_HEIGHT_LABEL, fmt.geoid_height(factors.ellipsoid_height)
        ),
        ResultValue(ELEVATION_FACTOR_LABEL, fmt.factor(factors.elevation_factor)),
        ResultValue(COMBINED_FACTOR_LABEL, fmt.factor(factors.combined_factor)),
    )


def single_point_sections(result: JobResult) -> tuple[ResultSection, ResultSection]:
    """The INPUT and OUTPUT blocks for a job carrying exactly one point.

    The three layouts are the owner's, decided before the code and tabulated in
    docs/DESIGN.md amendment #26. The rule behind them: computed values that do
    not depend on the target zone appear under OUTPUT, and the factors that
    describe the TYPED State Plane coordinate stay under INPUT. A State Plane to
    geodetic job has no target zone at all, so all of its factors are on the
    input side.

    Warnings are the last OUTPUT line in all three directions, including the one
    the owner's table did not list - a layout rule that hides a warning in one
    direction is not a layout rule.
    """
    if len(result.points) != 1:
        raise ValueError(
            f"The single-point display describes one converted point and this "
            f"job carries {len(result.points)}. Refused rather than showing the "
            f"first of them, which would name one point's coordinates as though "
            f"they were the whole job's."
        )

    settings = result.settings
    point = result.points[0]
    conversion = point.conversion
    factors = point.factors
    positive_west = _positive_west(settings)
    warnings = ResultValue(WARNINGS_LABEL, _warnings_text(point))

    if settings.direction is Direction.GEODETIC_TO_ZONE:
        # The file's northing and easting columns hold a latitude and a
        # longitude here, which is the branch exports.audit_rows takes at its
        # `geodetic_source` test. The elevation column is still linear and is
        # still in the input unit, so the units line stays.
        source = ResultSection(
            INPUT_TITLE,
            (
                *_geodetic_values(conversion, positive_west),
                ResultValue(
                    ELEVATION_LABEL,
                    fmt.coordinate(point.row.elevation, settings.input_unit),
                ),
                ResultValue(UNITS_LABEL, _units_text(settings.input_unit)),
            ),
        )
        target = ResultSection(
            OUTPUT_TITLE,
            (
                *_grid_values(
                    settings.target_zone,
                    settings.output_unit,
                    point.output_northing,
                    point.output_easting,
                    point.output_elevation,
                ),
                ResultValue(
                    GRID_FACTOR_LABEL, fmt.factor(factors.grid_scale_factor)
                ),
                ResultValue(
                    CONVERGENCE_LABEL, fmt.angle_dms(conversion.target_convergence)
                ),
                *_elevation_dependent_values(factors),
                warnings,
            ),
        )
        return source, target

    if settings.direction is Direction.ZONE_TO_GEODETIC:
        # There is no target zone, so every factor describes the typed State
        # Plane point and all of them sit under INPUT. The source and target
        # zones are the same zone on this path (job._convert_row passes
        # source_zone twice), so the target-side factor and convergence are the
        # typed point's own - and they are the ones the audit CSV's "Grid scale
        # factor" and "Convergence" columns carry.
        source = ResultSection(
            INPUT_TITLE,
            (
                *_grid_values(
                    settings.source_zone,
                    settings.input_unit,
                    point.row.northing,
                    point.row.easting,
                    point.row.elevation,
                ),
                ResultValue(
                    GRID_FACTOR_LABEL, fmt.factor(factors.grid_scale_factor)
                ),
                ResultValue(
                    CONVERGENCE_LABEL, fmt.angle_dms(conversion.target_convergence)
                ),
                *_elevation_dependent_values(factors),
            ),
        )
        target = ResultSection(
            OUTPUT_TITLE,
            (
                *_geodetic_values(conversion, positive_west),
                ResultValue(
                    ELEVATION_LABEL,
                    fmt.coordinate(point.output_elevation, settings.output_unit),
                ),
                ResultValue(UNITS_LABEL, _units_text(settings.output_unit)),
                warnings,
            ),
        )
        return source, target

    # Zone to zone. The geodetic pivot the conversion passed through is a real
    # computed result and independent of neither end, so it is shown - under
    # OUTPUT, with the target zone's factors.
    source = ResultSection(
        INPUT_TITLE,
        (
            *_grid_values(
                settings.source_zone,
                settings.input_unit,
                point.row.northing,
                point.row.easting,
                point.row.elevation,
            ),
            ResultValue(
                GRID_FACTOR_LABEL, fmt.factor(conversion.source_scale_factor)
            ),
            ResultValue(
                CONVERGENCE_LABEL, fmt.angle_dms(conversion.source_convergence)
            ),
        ),
    )
    target = ResultSection(
        OUTPUT_TITLE,
        (
            *_grid_values(
                settings.target_zone,
                settings.output_unit,
                point.output_northing,
                point.output_easting,
                point.output_elevation,
            ),
            *_geodetic_values(conversion, positive_west),
            ResultValue(GRID_FACTOR_LABEL, fmt.factor(factors.grid_scale_factor)),
            ResultValue(
                CONVERGENCE_LABEL, fmt.angle_dms(conversion.target_convergence)
            ),
            *_elevation_dependent_values(factors),
            warnings,
        ),
    )
    return source, target


def single_point_clipboard_text(sections: tuple[ResultSection, ...]) -> str:
    """The sections as tab-separated text, for the Copy all button.

    Section title on its own line, then one ``label<TAB>value`` line per value,
    with a blank line between sections and none at the end. Tabs because the
    result is pasted into a spreadsheet or an email as often as into a text
    file, and a tab is the one separator that survives all three - and because
    a comma would collide with the very thousands separators this program
    argues about elsewhere.

    A multi-line warning keeps its own newlines. Flattening them would compress
    exactly the sentences that explain why the point was flagged.
    """
    blocks = []
    for section in sections:
        lines = [section.title]
        lines.extend(f"{value.label}\t{value.text}" for value in section.values)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


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
