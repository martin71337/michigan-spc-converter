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
from michspc.fileio import pnezd
from michspc.fileio.exports import vertical_shift_heading, vertical_sigma_heading
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


# The table's shift and sigma column headings on a vertical job are the audit
# CSV's own - ``exports.vertical_shift_heading`` and ``vertical_sigma_heading``
# imported above, per the #17 standing choice of one wording on every surface.
# They are functions of the unit, not constants: since the owner's units
# instruction (2026-08-09) both headings carry the JOB'S INPUT UNIT, so the
# table cannot restate the CSV's wording and drift from it.


def _geodetic_display_columns(settings) -> bool:
    """Whether the table's coordinate columns hold degrees for this job.

    True for a State-Plane-to-geodetic job, and for a vertical-only job whose
    input is geodetic: that job's cells reproduce the input positions, so a
    geodetic input keeps geodetic headings. The same branch
    ``exports._geodetic_coordinate_columns`` takes for the files, restated
    here only because this module may not import the file layer's private
    names; ``row_strings`` renders through the identical formatters either
    way, so the two cannot show different digits.
    """
    return settings.direction is Direction.ZONE_TO_GEODETIC or (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is None
    )


def _elevation_heading(base: str, settings) -> str:
    """``Elevation (NAVD88, m)`` - the ordinary heading with the TARGET datum
    and the OUTPUT unit.

    Vertical jobs only. The table's elevation cells hold the SHIFTED height
    (``row_strings`` renders ``point.output_elevation``, which _convert_row
    moved into the target datum), so a bare "Elevation" over them names the
    number without saying which surface it is on - the WP-V7 review gate's
    finding 4, assigned to WP-V8. The unit is the OUTPUT unit - the unit the
    cells beneath are actually rendered in (``row_strings`` formats them with
    ``settings.output_unit``), NOT the input unit that governs the shift and
    sigma columns beside it. The datum and unit come from the settings the
    job actually ran with, never from a dropdown's current state.
    """
    return (
        f"{base} ({settings.target_vertical_datum.code}, "
        f"{settings.output_unit.code})"
    )


def columns_for(result: JobResult | None) -> tuple[str, ...]:
    """The header row for a job's direction. ``COLUMNS`` until a job says else.

    An empty table shows the ordinary headings: nothing has been converted, so
    naming the columns after a direction the user has not run would be the
    interface answering a question it was not asked.

    A HORIZONTAL_AND_VERTICAL job renames the Elevation heading with the
    target datum and gains the shift and sigma columns directly after it -
    mirroring ``exports.audit_columns``, whose vertical block also sits
    directly after Elevation, so the table and the audit CSV read in the same
    order. A horizontal job's header is ``COLUMNS`` (or ``GEODETIC_COLUMNS``)
    unchanged, to the string: horizontal mode asked no vertical question and
    its table must not claim a datum nobody stated (plan section 1).
    """
    if result is None:
        return COLUMNS
    settings = result.settings
    columns = list(
        GEODETIC_COLUMNS if _geodetic_display_columns(settings) else COLUMNS
    )
    if settings.vertical_mode.converts_elevations:
        at = columns.index("Elevation")
        columns[at] = _elevation_heading(columns[at], settings)
        # The shift and sigma headings carry the INPUT unit - the unit the
        # elevations were supplied in, the owner's instruction (2026-08-09).
        # In vertical-only mode input and output units are equal by
        # construction; in Horizontal + Vertical they can differ, and the
        # input unit still governs these two columns while the Elevation
        # heading beside them names the output unit its own cells are in.
        # ``row_strings`` converts the cells with the same unit object.
        columns[at + 1 : at + 1] = [
            vertical_shift_heading(settings.input_unit),
            vertical_sigma_heading(settings.input_unit),
        ]
    return tuple(columns)

POINT_COLUMN = 0
NORTHING_COLUMN = 1
EASTING_COLUMN = 2
ELEVATION_COLUMN = 3
GRID_FACTOR_COLUMN = 4
COMBINED_FACTOR_COLUMN = 5
WARNINGS_COLUMN = 6
"""The HORIZONTAL layout's column indexes - the table every release since
0.1.0 has shown, unchanged by WP-V8. A vertical job's table carries two more
columns after Elevation, so the model derives that job's warnings and
alignment positions from its own header in ``set_result`` rather than from
these constants; a fixed index applied to the wider table would paint the
wrong cell amber."""


def _warnings_index(columns: tuple[str, ...]) -> int:
    """Where the Warnings column sits in this header."""
    return columns.index("Warnings")


def _right_aligned(columns: tuple[str, ...]) -> frozenset[int]:
    """Which columns hold numbers, derived from the header itself.

    Every column except Point and Warnings - exactly the set the old
    module-level constant froze for the seven-column layout (indexes 1-5),
    restated as a rule so the vertical layout's shift and sigma columns
    right-align without a second hand-kept index list to drift.
    """
    return frozenset(range(len(columns))) - {POINT_COLUMN, _warnings_index(columns)}

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
    to_geodetic = _geodetic_display_columns(settings)
    vertical = settings.vertical_mode.converts_elevations

    rows: list[tuple[str, ...]] = []

    for point in result.points:
        if to_geodetic:
            northing = fmt.latitude(point.output_northing)
            easting = fmt.longitude(point.output_easting)
        else:
            northing = fmt.coordinate(point.output_northing, settings.output_unit)
            easting = fmt.coordinate(point.output_easting, settings.output_unit)

        cells = [
            point.point_id,
            northing,
            easting,
            fmt.coordinate(point.output_elevation, settings.output_unit),
            fmt.factor(point.factors.grid_scale_factor),
            # combined_factor is None for a point with no usable elevation;
            # fmt.factor renders that as "N/A", never as 1.0.
            fmt.factor(point.factors.combined_factor),
            "; ".join(warning.code.value for warning in point.warnings),
        ]

        if vertical:
            # Directly after the Elevation cell, under the two headings
            # columns_for inserts at the same position. The None handling is
            # deliberately identical to exports.audit_rows' vertical block: a
            # reading is None on a point that carried no elevation and on a
            # coverage-refused point (the warnings cell says which), so
            # neither number exists and both render N/A; sigma_m is None on
            # an identity and where the error model interpolates below zero
            # (DESIGN.md #36) - never the raw figure, which is not an
            # uncertainty. The values come from the READING - the shift the
            # job actually applied - not from any grid value, so this cell
            # and the audit CSV's cannot disagree (#26's property). Both are
            # converted into the INPUT unit - the same unit object
            # ``columns_for`` built the two headings from (and the same one
            # ``exports.audit_rows`` converts its cells with), so heading
            # and value cannot claim different units.
            reading = point.vertical
            cells[ELEVATION_COLUMN + 1 : ELEVATION_COLUMN + 1] = [
                fmt.vertical_quantity(
                    reading.shift_m if reading is not None else None,
                    settings.input_unit,
                ),
                fmt.vertical_quantity(
                    reading.sigma_m if reading is not None else None,
                    settings.input_unit,
                ),
            ]

        rows.append(tuple(cells))

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

# The sigma row's label is ``exports.vertical_sigma_heading(settings.input_unit)``
# - the audit CSV's own column heading, per the #17 standing choice of one
# wording on every surface, now a function of the job's input unit rather than
# a constant (owner's units instruction, 2026-08-09). It is a labelled row with
# its own copy button, exactly like every other value, because a sigma is a
# NUMBER a surveyor carries into a report - unlike the warnings, which are
# prose and live in their own field (#30). That is also why it belongs in
# ``single_point_clipboard_text`` (plan section 6's pin) while warnings do not.

VERTICAL_METHOD_LABEL = "Vertical method"
"""The label of a caveat row that no longer exists.

The row stood between the WP-V7 gate (its HIGH 1: the tab writes nothing, so
a caveat not on screen does not exist for that user) and the owner's
instruction of 2026-08-09 removing it (DESIGN.md #45) — the same ruling as
#33/#34: verification is the user's responsibility, and the record carries
the caveat for every written job. The constant remains so the suite can pin
the ABSENCE by name — a row that quietly returned would be a decision nobody
made."""


def vertical_shift_label(transformation, unit) -> str:
    """``Vertical shift NGVD29 -> NAVD88 (ift)`` - both datums in the label,
    and the unit the value is rendered in.

    The datums are IN the label, not implied by the section, because the shift
    is the one value on this panel that belongs to neither section alone: it is
    what moved the INPUT elevation to the OUTPUT one, and a bare "Shift" copied
    into a spreadsheet says nothing about which way. ``unit`` is the job's
    input unit (the owner's instruction, 2026-08-09), the same one the value
    beside this label is converted with.
    """
    return (
        f"Vertical shift {transformation.source.code} -> "
        f"{transformation.target.code} ({unit.code})"
    )


def _datum_elevation_label(datum, unit) -> str:
    """``Elevation (NAVD88, m)`` - the ordinary label, with its datum and its
    unit named.

    Only a vertical conversion uses this: a horizontal job asked no vertical
    question and its rows must not claim a datum nobody stated (plan section
    1, the owner's decision that horizontal mode is unchanged) - which is
    also why a horizontal row's plain "Elevation" gains no unit here: the
    Units row already serves it, and nothing about horizontal output may
    change. ``unit`` is the unit the row's VALUE is rendered in - the input
    unit for the INPUT section's elevation, the output unit for the OUTPUT
    section's - passed by the caller that formats the value, so label and
    value cannot name different units.
    """
    return f"{ELEVATION_LABEL} ({datum.code}, {unit.code})"


def _vertical_rows(reading, unit) -> tuple[ResultValue, ...]:
    """The shift row and the sigma row, or nothing at all.

    Empty when the point carries no ``VerticalReading`` - a horizontal job, a
    vertical point with no elevation, or a coverage-refused point whose
    warning says why. ``unit`` is the job's INPUT unit - the unit both labels
    name and both values are converted into (the owner's instruction,
    2026-08-09). The sigma renders through ``fmt.vertical_quantity``, which
    prints N/A for a None - the ONLY thing an unavailable sigma may print
    (docs/DESIGN.md #36); the reason it is unavailable reaches the warnings
    field through ``WarningCode.VERTICAL_SIGMA_UNAVAILABLE``, raised beside
    the reading by ``job._convert_row``.
    """
    if reading is None:
        return ()
    return (
        ResultValue(
            vertical_shift_label(reading.transformation, unit),
            fmt.vertical_quantity(reading.shift_m, unit),
        ),
        ResultValue(
            vertical_sigma_heading(unit),
            fmt.vertical_quantity(reading.sigma_m, unit),
        ),
        # The "Vertical method" caveat row that stood here was REMOVED at the
        # owner's instruction (DESIGN.md #45, 2026-08-09), reversing the #42
        # gate's on-screen-caveat resolution under the owner's #33 ruling
        # that verification is the user's responsibility. The caveat itself
        # is not deleted from the program: the job record's METHOD block
        # still quotes it in full for every written job, and the
        # sigma-unavailable warning still reaches the panel's warnings
        # field. What is gone is the caveat as a panel row and from Copy
        # all.
    )


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
    return "\n\n".join(_without_point_prefix(w.message) for w in point.warnings)


def _without_point_prefix(message: str) -> str:
    """Drop the leading "point 1" that a typed point cannot meaningfully carry.

    ``job._convert_row`` opens every warning with the row's identifier, and
    ``parse_typed_point`` supplies the fabricated ``TYPED_POINT_ID`` because the
    reader requires a non-blank one. On a tab whose specification says "no point
    number" (docs/DESIGN.md amendment #26), naming point 1 of 1 is noise the
    surveyor never asked for - found by the closing review gate.

    Only the exact fabricated identifier is stripped, and only at the start, so
    a real identifier can never be silently removed. Written against the
    constant rather than a literal so the two cannot drift apart.
    """
    prefix = f"point {pnezd.TYPED_POINT_ID}"
    if not message.startswith(prefix):
        return message

    rest = message[len(prefix) :]
    if rest.startswith(":"):
        return rest[1:].lstrip()
    # "point 1 (into MI-C): ..." - the qualifier is kept, the identifier is not.
    if rest.startswith(" ("):
        return rest.lstrip()
    return message


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
    #
    # The two decimal lines use the DISPLAY formatters, which are the file
    # formatters plus a degree symbol (docs/DESIGN.md amendment #30). The symbol
    # cannot go in the file ones: they also write the clean PNEZD export, which
    # is read back before the archive is committed and lands in the surveyor's
    # CAD package. The DMS lines already carry their own symbols.
    return (
        ResultValue(LATITUDE_LABEL, fmt.latitude_display(conversion.latitude)),
        ResultValue(LATITUDE_DMS_LABEL, fmt.latitude_dms(conversion.latitude)),
        ResultValue(
            LONGITUDE_LABEL,
            fmt.longitude_display(conversion.longitude, positive_west=positive_west),
        ),
        # No convention flag: a DMS longitude is magnitude plus a hemisphere
        # letter, and the magnitude is the same number either way.
        ResultValue(LONGITUDE_DMS_LABEL, fmt.longitude_dms(conversion.longitude)),
    )


def _grid_values(
    zone, unit, northing, easting, elevation, elevation_label: str = ELEVATION_LABEL
) -> tuple[ResultValue, ...]:
    """Zone, units and the three linear columns, in that order.

    ``elevation_label`` names the vertical datum on a vertical conversion
    (``Elevation (NAVD88)``) and is the plain ``ELEVATION_LABEL`` everywhere
    else - the label moves, the value's formatter never does.
    """
    return (
        ResultValue(ZONE_LABEL, zone_label(zone)),
        ResultValue(UNITS_LABEL, _units_text(unit)),
        ResultValue(NORTHING_LABEL, fmt.coordinate(northing, unit)),
        ResultValue(EASTING_LABEL, fmt.coordinate(easting, unit)),
        ResultValue(elevation_label, fmt.coordinate(elevation, unit)),
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

    **Warnings are NOT in here.** They were the last OUTPUT line in all three
    directions until the owner moved them out to a full-width field of their own
    beneath the panel (docs/DESIGN.md amendment #30). They are still built from
    the same point, by ``single_point_warnings`` below, so there is one
    statement of what a warning says - it is only shown somewhere else.

    That also takes warnings out of ``single_point_clipboard_text``, which
    serialises these sections and nothing else. Deliberate, and his
    instruction: the clipboard carries the numbers a surveyor pastes into CAD,
    and a paragraph of prose in the middle of them is what he is removing.
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

    # The vertical rows (WP-V7, plan section 5.2). Gated on the point CARRYING
    # a VerticalReading, not on the settings: a horizontal job's layout is
    # unchanged to the label, and a vertical point whose shift was refused
    # (coverage) or that had no elevation shows no shift row - its warning, in
    # the warnings field, is what explains the absence. When a reading exists,
    # the INPUT elevation is labelled with the source datum and the OUTPUT one
    # with the target datum, because the two rows now hold heights on two
    # different surfaces and unlabelled they would read as the same quantity
    # re-expressed. Each label carries the unit its own VALUE is rendered in
    # - the input unit for the INPUT row, the output unit for the OUTPUT row
    # (they can differ in a Horizontal + Vertical job): symmetric on purpose,
    # because a unit on the output row alone would invite "in what?" of the
    # input one. The shift and sigma rows carry the INPUT unit (the owner's
    # instruction, 2026-08-09).
    reading = point.vertical
    if reading is not None:
        input_elevation_label = _datum_elevation_label(
            reading.transformation.source, settings.input_unit
        )
        output_elevation_label = _datum_elevation_label(
            reading.transformation.target, settings.output_unit
        )
    else:
        input_elevation_label = ELEVATION_LABEL
        output_elevation_label = ELEVATION_LABEL
    vertical_rows = _vertical_rows(reading, settings.input_unit)

    if settings.direction is Direction.VERTICAL_ONLY:
        # The vertical-only layouts (the owner's feature, 2026-08-09). The
        # INPUT section describes the typed point in its own system, with the
        # factors - the input zone's where one exists, honestly absent where
        # none does. The OUTPUT section holds ONLY the target-datum elevation,
        # the shift and the sigma: nothing was converted horizontally, and
        # the unchanged coordinates repeated under an OUTPUT heading would
        # read as a conversion that never ran.
        if settings.source_zone is not None:
            source = ResultSection(
                INPUT_TITLE,
                (
                    *_grid_values(
                        settings.source_zone,
                        settings.input_unit,
                        point.row.northing,
                        point.row.easting,
                        point.row.elevation,
                        elevation_label=input_elevation_label,
                    ),
                    # The INPUT zone's factors, the ZONE_TO_GEODETIC
                    # precedent: no output zone exists, so every factor
                    # describes the typed State Plane point.
                    ResultValue(
                        GRID_FACTOR_LABEL, fmt.factor(factors.grid_scale_factor)
                    ),
                    ResultValue(
                        CONVERGENCE_LABEL,
                        fmt.convergence_display(conversion.target_convergence),
                    ),
                    *_elevation_dependent_values(factors),
                ),
            )
        else:
            # Geodetic input: no zone anywhere, so no Zone row, no grid
            # factor row and no convergence row - a row of N/A would imply a
            # zone could exist. The elevation-dependent values stay: the
            # geoid height and elevation factor need no zone, and the
            # combined factor honestly reads N/A through the formatter.
            source = ResultSection(
                INPUT_TITLE,
                (
                    *_geodetic_values(conversion, positive_west),
                    ResultValue(
                        input_elevation_label,
                        fmt.coordinate(point.row.elevation, settings.input_unit),
                    ),
                    ResultValue(UNITS_LABEL, _units_text(settings.input_unit)),
                    *_elevation_dependent_values(factors),
                ),
            )
        target = ResultSection(
            OUTPUT_TITLE,
            (
                ResultValue(
                    output_elevation_label,
                    fmt.coordinate(point.output_elevation, settings.output_unit),
                ),
                *vertical_rows,
            ),
        )
        return source, target

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
                    input_elevation_label,
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
                    elevation_label=output_elevation_label,
                ),
                # The shift and its sigma read directly under the elevation
                # they explain, before the factors.
                *vertical_rows,
                ResultValue(
                    GRID_FACTOR_LABEL, fmt.factor(factors.grid_scale_factor)
                ),
                ResultValue(
                    CONVERGENCE_LABEL,
                    fmt.convergence_display(conversion.target_convergence),
                ),
                *_elevation_dependent_values(factors),
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
                    elevation_label=input_elevation_label,
                ),
                ResultValue(
                    GRID_FACTOR_LABEL, fmt.factor(factors.grid_scale_factor)
                ),
                ResultValue(
                    CONVERGENCE_LABEL,
                    fmt.convergence_display(conversion.target_convergence),
                ),
                *_elevation_dependent_values(factors),
            ),
        )
        target = ResultSection(
            OUTPUT_TITLE,
            (
                *_geodetic_values(conversion, positive_west),
                ResultValue(
                    output_elevation_label,
                    fmt.coordinate(point.output_elevation, settings.output_unit),
                ),
                *vertical_rows,
                ResultValue(UNITS_LABEL, _units_text(settings.output_unit)),
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
                elevation_label=input_elevation_label,
            ),
            ResultValue(
                GRID_FACTOR_LABEL, fmt.factor(conversion.source_scale_factor)
            ),
            ResultValue(
                CONVERGENCE_LABEL,
                fmt.convergence_display(conversion.source_convergence),
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
                elevation_label=output_elevation_label,
            ),
            *vertical_rows,
            *_geodetic_values(conversion, positive_west),
            ResultValue(GRID_FACTOR_LABEL, fmt.factor(factors.grid_scale_factor)),
            ResultValue(
                CONVERGENCE_LABEL,
                fmt.convergence_display(conversion.target_convergence),
            ),
            *_elevation_dependent_values(factors),
        ),
    )
    return source, target


def single_point_warnings(result: JobResult) -> str:
    """Every warning the single converted point raised, or ``NO_WARNINGS``.

    Separate from ``single_point_sections`` because the owner put warnings in a
    field of their own (docs/DESIGN.md amendment #30) - but built from the same
    ``_warnings_text`` the sections used to call, so moving the display did not
    create a second account of what a warning says.

    Refuses a multi-point job for the same reason ``single_point_sections``
    does: naming one point's warnings as though they were the whole job's is
    exactly the kind of quiet mis-statement this program refuses.
    """
    if len(result.points) != 1:
        raise ValueError(
            f"The single-point warnings field describes one converted point "
            f"and this job carries {len(result.points)}. Refused rather than "
            f"showing the first of them."
        )
    return _warnings_text(result.points[0])


def single_point_clipboard_text(sections: tuple[ResultSection, ...]) -> str:
    """The sections as tab-separated text, for the Copy all button.

    Section title on its own line, then one ``label<TAB>value`` line per value,
    with a blank line between sections and none at the end. Tabs because the
    result is pasted into a spreadsheet or an email as often as into a text
    file, and a tab is the one separator that survives all three - and because
    a comma would collide with the very thousands separators this program
    argues about elsewhere.

    Warnings are not in these sections and so are not in this text, which is
    the owner's instruction (amendment #30): the clipboard carries the numbers
    a surveyor pastes into CAD or a spreadsheet, and a paragraph of prose
    dropped among them has to be deleted there. The warnings field on screen is
    where they are read.
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
        self._warnings_column: int = _warnings_index(COLUMNS)
        self._aligned_right: frozenset[int] = _right_aligned(COLUMNS)

    def set_result(self, result: JobResult | None) -> None:
        self.beginResetModel()
        # The headings are settled here, with the rows, so the two can never
        # describe different jobs: a model reset repaints both together. The
        # warnings and alignment positions are derived from the header at the
        # same moment, because a vertical job's table is two columns wider
        # and a fixed index would paint the wrong cell amber.
        self._columns = columns_for(result)
        self._warnings_column = _warnings_index(self._columns)
        self._aligned_right = _right_aligned(self._columns)
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

        if role == Qt.ItemDataRole.TextAlignmentRole and column in self._aligned_right:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.BackgroundRole:
            if (
                column == self._warnings_column
                and self._rows[row][self._warnings_column]
            ):
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
