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
from michspc.fileio.exports import (
    AUTO_COUNTY_COLUMNS,
    ellipsoid_elevation_heading,
    is_auto_zone_job,
    external_frame,
    geodetic_pair_frames,
    pivot_frame,
    transformed_ellipsoid_height_heading,
    vertical_shift_and_sigma_m,
    vertical_shift_heading,
    vertical_sigma_heading,
    writes_geodetic_coordinates,
)
from michspc.gui.controls import zone_label
from michspc.job import (
    Direction,
    JobResult,
    LongitudeConvention,
    applied_frame_transformation,
    factors_geoid_model,
    geoid_swap_models,
    written_geodetic_position,
)
from michspc.spc.vertical import HeightKind, require_vertical_pair

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

    True for a State-Plane-to-geodetic job, a geodetic-to-geodetic job, and a
    vertical-only job whose input is geodetic: that job's cells reproduce the
    input positions, so a geodetic input keeps geodetic headings.

    **The file layer's own rule, asked rather than restated** - work package
    W5 of the WGS 84 build. This used to be a copy of
    ``exports._geodetic_coordinate_columns``, made because this module may not
    import the file layer's private names, and the copy did not grow the
    GEODETIC_TO_GEODETIC branch W3 added there: that direction's table would
    have shown latitudes under "Northing" (W4's note). The copy is gone;
    ``exports.writes_geodetic_coordinates`` is the public name of the one rule.
    """
    return writes_geodetic_coordinates(settings)


ZONE_ONLY_COLUMNS: tuple[str, ...] = ("Grid scale factor", "Combined factor")
"""The two table columns that describe a State Plane zone.

A grid scale factor is a property of a projection, and the combined factor is
the grid factor times the elevation factor; a job with no zone has neither,
and its cells could only ever read N/A."""


def _shows_zone_columns(settings) -> bool:
    """Whether the table carries ``ZONE_ONLY_COLUMNS`` for this job.

    False on ``GEODETIC_TO_GEODETIC`` only (work package W5 of the WGS 84
    build, the lead's finding on the W5 screenshots): latitude and longitude
    in and out, no zone at either end, so two columns of N/A would read as
    though a zone could have existed - the single-point panel's rule for the
    same direction, which shows no grid factor row either.

    **The table's one departure from mirroring the audit CSV's columns.** The
    CSV is the record and keeps its N/A cells on this direction; the table is
    a view of it and drops two columns that can never hold a value. Every
    cell the table does show is still the CSV's own (pinned).

    **Deliberately NOT ``job.is_zoneless``**, which also covers a vertical-only
    job on geodetic positions. That job's table has shown these two columns,
    pinned as honest absences (tests/test_gui_vertical_only.py), since 0.4.0;
    narrowing a released layout is the owner's call, and is flagged for it
    rather than made here.
    """
    return settings.direction is not Direction.GEODETIC_TO_GEODETIC


def _elevation_heading(settings, geoid_model_name: str | None) -> str:
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

    Delegates to ``_datum_elevation_label`` rather than repeating its
    template. The two were separate f-strings producing the same text until
    the geoid tag arrived (DESIGN.md #52), which is one fact in two places -
    exactly the arrangement that lets a panel and a table drift apart, and
    the property amendment #26 spent a whole gate establishing is that they
    cannot.
    """
    return _datum_elevation_label(
        settings.target_vertical_datum, settings.output_unit, geoid_model_name
    )


def table_geoid_model_name(result: JobResult | None) -> str | None:
    """The geoid model the table's elevation cells are ON, or None.

    Named only for a geoid-to-geoid job, where the output elevation's identity
    is the model and nothing else: both ends carry the same datum and the same
    unit, so without it the heading describes the input column equally well
    (the owner's instruction, 2026-08-10). Every other job leaves it None -
    a leveled NAVD 88 height does not belong to a geoid model (DESIGN.md #50),
    and a horizontal job asked no vertical question at all.

    The transformation is resolved through the same registry lookup ``job.run``
    and the record perform, and the swap decision through ``job.geoid_swap_models``,
    so the heading cannot claim a swap the computation did not make.
    """
    if result is None:
        return None
    settings = result.settings
    # GENERALISED from #52 (DESIGN.md #54): the model is named wherever the
    # displayed orthometric height DEPENDS on a model - where a geoid change
    # ran, or where the height was derived from an ellipsoid height. It is
    # still not named beside a leveled height, which depends on no model
    # (#50's recorded geodetic fact), so #52's two negative pins stand.
    if settings.input_height_kind is HeightKind.ELLIPSOID:
        model = factors_geoid_model(
            settings,
            require_vertical_pair(
                settings.source_vertical_datum, settings.target_vertical_datum
            )
            if settings.vertical_mode.converts_elevations
            else None,
        )
        return None if model is None else model.name
    if not settings.vertical_mode.converts_elevations:
        return None
    swap = geoid_swap_models(
        settings,
        require_vertical_pair(
            settings.source_vertical_datum, settings.target_vertical_datum
        ),
    )
    return None if swap is None else swap[1].name


AUTO_ZONE_COLUMNS: tuple[str, ...] = ("Zone", "County")
"""The two columns an AUTO job's table carries, directly after Point (DESIGN.md
#71): the zone each point was projected into and the county that chose it.

An Auto file can span zones, and northings from two zones in one unlabelled
column would read as one grid. Each cell is the written archive's own fact -
the zone's registry name, as the audit CSV's ``Target zone`` cell prints it,
and TIGER's county name, as its ``County`` cell prints it - read from the
POINT (``ConvertedPoint.auto_zone``), never from ``settings.target_zone``,
which on an Auto job is the sentinel. Present on Auto jobs only, so every
fixed-zone table is unchanged to the string (#65: the table describes the
archive a run wrote)."""


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
    path = applied_frame_transformation(settings)
    if path is not None and _geodetic_display_columns(settings):
        # A TRANSFORMED job's degrees name their frame, as every latitude and
        # longitude heading of the audit CSV does (interim gate 2, finding
        # H1): the table's coordinate cells are the audit CSV's TARGET pair -
        # ``row_strings`` renders ``output_northing`` / ``output_easting``,
        # the values the clean export writes - so they are named by the frame
        # ``exports.geodetic_pair_frames`` states for that pair, the file
        # layer's one statement of it. On a same-frame job the headings are
        # untouched to the string.
        frame = geodetic_pair_frames(path, settings)[1].code
        columns[NORTHING_COLUMN] = f"{GEODETIC_COLUMNS[NORTHING_COLUMN]} ({frame})"
        columns[EASTING_COLUMN] = f"{GEODETIC_COLUMNS[EASTING_COLUMN]} ({frame})"
    if not _shows_zone_columns(settings):
        columns = [c for c in columns if c not in ZONE_ONLY_COLUMNS]
    if settings.input_height_kind is HeightKind.ELLIPSOID and not (
        settings.vertical_mode.converts_elevations
    ):
        # HORIZONTAL: the cells hold the ellipsoid height, passed through, so
        # the heading says so. "Elevation" over them was h in a column
        # labelled H - about 33 m out (closing gate, HIGH 1). One wording with
        # the audit CSV's own heading for the same cells (#17) - and, on a
        # transformed job, the same frame: ``exports.ellipsoid_elevation_heading``
        # is the heading the audit CSV's own column carries.
        columns[columns.index("Elevation")] = ellipsoid_elevation_heading(settings)
    if settings.vertical_mode.converts_elevations:
        at = columns.index("Elevation")
        columns[at] = _elevation_heading(settings, table_geoid_model_name(result))
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
    if is_auto_zone_job(settings):
        # LAST of the edits, at a fixed place after Point, so every index the
        # edits above took is unaffected; row_strings inserts its two cells
        # at the same moment of its own construction.
        columns[POINT_COLUMN + 1 : POINT_COLUMN + 1] = list(AUTO_ZONE_COLUMNS)
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
    right-align without a second hand-kept index list to drift - and except
    an Auto job's Zone and County, which are names, not numbers.
    """
    text = {POINT_COLUMN, _warnings_index(columns)} | {
        index for index, name in enumerate(columns) if name in AUTO_ZONE_COLUMNS
    }
    return frozenset(range(len(columns))) - text

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
    zone_columns = _shows_zone_columns(settings)
    auto = is_auto_zone_job(settings)

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
        if not zone_columns:
            # The two cells under ``ZONE_ONLY_COLUMNS``, dropped exactly where
            # ``columns_for`` drops their headings, BEFORE the vertical
            # insertion below so its index is the same on every layout.
            del cells[GRID_FACTOR_COLUMN : COMBINED_FACTOR_COLUMN + 1]

        if vertical:
            # Directly after the Elevation cell, under the two headings
            # columns_for inserts at the same position. WHICH numbers these
            # two cells carry is exports.vertical_shift_and_sigma_m's one
            # statement, shared with the audit CSV, so this cell and the
            # CSV's cannot disagree (#26's property): the datum reading's
            # shift and sigma ordinarily, the SWAP shift with no sigma on a
            # geoid-to-geoid point, neither where no reading exists (no
            # elevation, or a coverage refusal - the warnings cell says
            # which). A None renders N/A - never the raw figure, which is
            # not an uncertainty (DESIGN.md #36). Both are converted into
            # the INPUT unit - the same unit object ``columns_for`` built
            # the two headings from (and the same one ``exports.audit_rows``
            # converts its cells with), so heading and value cannot claim
            # different units.
            shift_m, sigma_m = vertical_shift_and_sigma_m(point)
            cells[ELEVATION_COLUMN + 1 : ELEVATION_COLUMN + 1] = [
                fmt.vertical_quantity(shift_m, settings.input_unit),
                fmt.vertical_quantity(sigma_m, settings.input_unit),
            ]

        if auto:
            # Under AUTO_ZONE_COLUMNS, inserted where columns_for inserts
            # them: the point's OWN zone and county.
            assignment = _auto_assignment(point)
            cells[POINT_COLUMN + 1 : POINT_COLUMN + 1] = [
                assignment.zone.name,
                assignment.county_name,
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
COUNTY_LABEL, COUNTY_FIPS_LABEL = AUTO_COUNTY_COLUMNS
"""An Auto point's county rows, under the audit CSV's own two headings (#17's
one wording): ``County`` and ``County FIPS``. Directly under the Zone row they
explain, on Auto jobs only (DESIGN.md #71)."""
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


def geoid_swap_label(swap, unit) -> str:
    """``Geoid change GEOID12B -> GEOID18 (ift)`` - a geoid-to-geoid point's
    shift row label: the MODELS, not the datums.

    On a swap job the datum did not move - the transformation is an identity
    - so a label naming the datums would describe the one thing that did not
    happen. What moved the elevation is the change of geoid model, and the
    label says so in the shape ``vertical_shift_label`` established: what
    changed, which way, and the unit the value beside it is rendered in
    (the job's input unit, the owner's 2026-08-09 instruction). The audit
    CSV's generic ``Vertical shift (unit)`` / ``Shift sigma (unit)``
    headings stay - they are true of both kinds of shift - so #17's
    one-wording rule is not in play where the surfaces differ on purpose.
    """
    return (
        f"Geoid change {swap.source_model_name} -> "
        f"{swap.target_model_name} ({unit.code})"
    )


ELLIPSOID_INPUT_LABEL = "Ellipsoid height"
"""What the INPUT row is called when the Z column held a GNSS height.

Not "Elevation". The two differ by about 34 m in Michigan, and a row labelled
"Elevation" over an ellipsoid height is the ordinary-looking wrong number this
program is built against. It is also what the OUTPUT row is called in
HORIZONTAL mode, where the Z is written back unconverted - there the output
genuinely still is an ellipsoid height, and saying "Elevation" over it would
be the same falsehood one column to the right.

This row carried a "(GNSS," qualifier until the owner had it removed
(2026-08-11). It existed because ``ELLIPSOID_HEIGHT_LABEL`` below is the
FACTORS row - h = H + N recomputed from the conversion - and on a metres job
the two labels collided. They also hold the SAME NUMBER, because the
recomputation inverts the conversion exactly: (h - N) + N is h. So the
qualifier was distinguishing two rows that were never two facts, and the
resolution is to show the value once - here, as the height the user supplied -
rather than to keep a word explaining why it appears twice
(``_elevation_dependent_values``).
"""


def _datum_elevation_label(datum, unit, geoid_model_name: str | None = None) -> str:
    """``Elevation (NAVD88, m)``, or ``Elevation (NAVD88, m) (GEOID18)`` on a
    geoid-to-geoid job - the datum, the unit, and the geoid where one applies.

    THE one elevation-label template. The Multi point table heading builds on
    it too (``_elevation_heading``), so the two surfaces cannot word the same
    fact differently.

    Only a vertical conversion uses this: a horizontal job asked no vertical
    question and its rows must not claim a datum nobody stated (plan section
    1, the owner's decision that horizontal mode is unchanged) - which is
    also why a horizontal row's plain "Elevation" gains no unit here: the
    Units row already serves it, and nothing about horizontal output may
    change. ``unit`` is the unit the row's VALUE is rendered in - the input
    unit for the INPUT section's elevation, the output unit for the OUTPUT
    section's - passed by the caller that formats the value, so label and
    value cannot name different units.

    ``geoid_model_name`` is the owner's instruction of 2026-08-10, and it is
    a SEPARATE parenthesis after the unit one, in his words. Supplied only on
    a geoid-to-geoid job, where the two elevations sit on the same datum in
    the same unit and the model is the whole difference between them: without
    it the INPUT and OUTPUT labels are the same string over two different
    heights. Left None everywhere else, because an ordinary orthometric
    height is not "in" a geoid model - the hybrid models were fitted to the
    leveled network, and naming one beside a leveled height would state a
    dependence that does not exist (DESIGN.md #50's recorded geodetic fact).
    """
    label = f"{ELEVATION_LABEL} ({datum.code}, {unit.code})"
    if geoid_model_name is None:
        return label
    return f"{label} ({geoid_model_name})"


def _vertical_rows(reading, swap, unit) -> tuple[ResultValue, ...]:
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

    On a geoid-to-geoid point (``swap`` is the point's ``GeoidSwapReading``)
    the shift row is the GEOID CHANGE - the value that actually moved the
    elevation, labelled with the two models - and the sigma row is N/A with
    nothing attached: NGS publishes no error model for the difference
    between two of its geoid models, so no number exists to print.
    """
    if reading is None:
        return ()
    if swap is not None:
        return (
            ResultValue(
                geoid_swap_label(swap, unit),
                fmt.vertical_quantity(swap.shift_m, unit),
            ),
            ResultValue(
                vertical_sigma_heading(unit),
                fmt.vertical_quantity(None, unit),
            ),
        )
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


def _warnings_text(point, job_warnings=()) -> str:
    """Every warning this point raised, in full, or ``NO_WARNINGS``.

    The messages themselves, joined by a blank line, exactly as the multi-point
    table's tooltip does. The refusal-grade wording in this program was written
    to teach; a single-point display has the room, so it shows the sentences
    rather than the warning codes the table has to compress into a cell.

    ``job_warnings`` - ``JobResult.job_warnings``, the warnings about the JOB
    rather than about any one point (today only the WGS 84 realization period,
    docs/PLAN-wgs84.md decision D9) - come FIRST, as the job record prints
    them first, and in the record's own words: ``job_warning_messages``, which
    is ``warning.message`` exactly as ``report`` writes it. Not in
    ``JobResult.warnings``, which pairs each entry with the point that raised
    it, so a display reading only that would never show them (work package
    W5).
    """
    messages = [
        *job_warning_messages(job_warnings),
        *(_without_point_prefix(w.message) for w in point.warnings),
    ]
    if not messages:
        return NO_WARNINGS
    return "\n\n".join(messages)


def job_warning_messages(job_warnings) -> tuple[str, ...]:
    """The job-level warnings' text: ``warning.message``, as the job record prints it.

    The job-level twin of ``_warnings_text``, and the one place either tab
    reads that text from, so the Single point warnings field, the Multi point
    status tooltip and the record's WARNINGS section all carry the same
    sentence (``report``'s WARNINGS block writes ``warning.message`` under
    "(the whole job)"). No point prefix to strip: a job-level warning names no
    point.
    """
    return tuple(warning.message for warning in job_warnings)


def warning_count(result: JobResult) -> int:
    """How many warnings a result carries: every point's, and the job's own.

    What both tabs' status lines count and colour by. Counting
    ``JobResult.warnings`` alone - which excludes ``job_warnings`` by design -
    would print "No warnings." in the ordinary colour beside a warnings field
    stating that the positions are dated outside their realization's period of
    use.
    """
    return len(result.warnings) + len(result.job_warnings)


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

    **The pivot, on a same-frame job only.** On a job with a frame
    transformation the pivot is the NAD83(2011) position and the WGS 84 or
    ITRF position is a second one (plan decision D5), so the panel shows both,
    each labelled with its frame, through ``_position_values`` - which this
    delegates to with no frame, so the same-frame rows are unchanged to the
    character.

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
    return _position_values(conversion.latitude, conversion.longitude, positive_west)


def _framed(label: str, frame_code: str | None, qualifier: str | None = None) -> str:
    """``Latitude``, or ``Latitude (WGS84(G2296))`` / ``Latitude (WGS84(G2296), DMS)``.

    The audit CSV's own spelling for a frame-named position heading
    (``exports._frame_named`` and ``frame_transformation_columns``: the frame
    code first inside the parenthesis, then any qualifier), so the screen and
    ``<stem>_full.csv`` name the same position the same way (#17) - less the
    CSV's "neg west", which the panel has never carried (its DMS line's
    hemisphere letter states the convention). With no frame, the plain label
    and qualifier exactly as the panel has always spelled them.
    """
    if frame_code is None:
        return label if qualifier is None else f"{label} ({qualifier})"
    if qualifier is None:
        return f"{label} ({frame_code})"
    return f"{label} ({frame_code}, {qualifier})"


def _position_values(
    latitude: float,
    longitude: float,
    positive_west: bool,
    frame_code: str | None = None,
) -> tuple[ResultValue, ...]:
    """One signed position's four rows, labelled with its frame when two exist.

    ``frame_code`` is None on every same-frame job - the labels are then the
    ones this panel has always shown, to the character - and the frame's code
    on a transformed job, where the panel carries two positions about a metre
    apart and an unlabelled one would leave the surveyor to guess which frame
    a copied number is in.
    """
    return (
        ResultValue(
            _framed(LATITUDE_LABEL, frame_code), fmt.latitude_display(latitude)
        ),
        ResultValue(
            _framed(LATITUDE_LABEL, frame_code, "DMS"), fmt.latitude_dms(latitude)
        ),
        ResultValue(
            _framed(LONGITUDE_LABEL, frame_code),
            fmt.longitude_display(longitude, positive_west=positive_west),
        ),
        # No convention flag: a DMS longitude is magnitude plus a hemisphere
        # letter, and the magnitude is the same number either way.
        ResultValue(
            _framed(LONGITUDE_LABEL, frame_code, "DMS"), fmt.longitude_dms(longitude)
        ),
    )


OBSERVATION_DATE_LABEL = "Observation date"
"""The audit CSV's own heading for the job's one date (``exports.
frame_transformation_columns``), shown directly under the WGS 84 or ITRF
position it dates. A position in a time-dependent frame means nothing until
the date it was observed is stated (``frames.FrameEpochKind``), so a Copy all
that carried the position without it would paste half a fact."""


@dataclass(frozen=True)
class _Positions:
    """The geodetic rows of one point: what the panel shows at each end.

    ``input`` and ``output`` are the rows for the position the job READ and
    the one it WROTE, where those are geodetic; ``pivot`` is the NAD83(2011)
    position on a transformed job and empty otherwise.
    """

    input: tuple[ResultValue, ...]
    output: tuple[ResultValue, ...]
    pivot: tuple[ResultValue, ...]


def _positions(point, positive_west: bool) -> _Positions:
    """The panel's geodetic rows for this point, each block from its own record.

    Same-frame job: the pivot is the only position, at either end, under the
    labels the panel has always used, and ``pivot`` is empty (the zone-to-zone
    layout shows it as its own block, unchanged).

    Transformed job (plan decision D5): the NAD83(2011) pivot -
    ``conversion.latitude`` / ``longitude`` - and the WGS 84 or ITRF
    position - ``conversion.external_position`` - are different positions in
    different frames, and each is shown under its own frame's name, never one
    under the other's. Which end each one is comes from the path's own records
    (``exports.external_frame`` / ``pivot_frame``): the external position is
    the INPUT when the path starts in the time-dependent frame, and the OUTPUT
    otherwise - the position ``job.written_geodetic_position`` says a geodetic
    target writes. The observation date follows the external position.
    """
    conversion = point.conversion
    if not conversion.is_transformed:
        same = _geodetic_values(conversion, positive_west)
        return _Positions(input=same, output=same, pivot=())

    path = conversion.frame_transformation
    external = conversion.external_position
    pivot_rows = _position_values(
        conversion.latitude,
        conversion.longitude,
        positive_west,
        pivot_frame(path).code,
    )
    external_rows = (
        *_position_values(
            external.latitude,
            external.longitude,
            positive_west,
            external_frame(path).code,
        ),
        ResultValue(
            OBSERVATION_DATE_LABEL, conversion.observation_epoch.date.isoformat()
        ),
    )
    reads_external = external_frame(path).code == path.source.code
    # The written end, asked of the core's own rule rather than inferred: a
    # mismatch here would be the pivot labelled with the WGS 84 frame.
    writes_external = written_geodetic_position(conversion) == (
        external.latitude,
        external.longitude,
    )
    if reads_external == writes_external:
        raise ValueError(
            f"Point {point.point_id} carries the transformation {path}, but "
            f"its external position is neither the input nor the output "
            f"alone. Refused rather than labelling one frame's position with "
            f"the other's name."
        )
    if reads_external:
        return _Positions(input=external_rows, output=pivot_rows, pivot=pivot_rows)
    return _Positions(input=pivot_rows, output=external_rows, pivot=pivot_rows)


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


def _auto_assignment(point):
    """An Auto point's zone assignment, or a refusal - never a guess.

    Every point of an Auto job carries one (``job._convert_row``), and its
    zone IS the zone the point was projected into; a point that says
    otherwise was assembled by hand, and showing either zone would label one
    zone's northing with the other's name.
    """
    assignment = point.auto_zone
    if assignment is None or assignment.zone is not point.conversion.target_zone:
        raise ValueError(
            f"Point {point.point_id} is on an Auto job but its zone assignment "
            f"({assignment!r}) is not the zone it was projected into "
            f"({point.conversion.target_zone!r}). Refused rather than naming "
            f"either zone beside the other's coordinates."
        )
    return assignment


def _auto_rows(point) -> tuple[ResultValue, ...]:
    """The Zone row's companions on an Auto point: its county, name and FIPS."""
    assignment = _auto_assignment(point)
    return (
        ResultValue(COUNTY_LABEL, assignment.county_name),
        ResultValue(COUNTY_FIPS_LABEL, assignment.county_fips),
    )


def _elevation_dependent_values(
    factors,
    ellipsoid_input=False,
    pivot_frame_code: str | None = None,
    has_a_zone: bool = True,
) -> tuple[ResultValue, ...]:
    """The quantities that exist only because the point had an elevation.

    Every one of them is None for a point with no usable elevation, and
    ``fmt`` renders that as "N/A" - never as a plausible 1.0, which is the
    convention this program is built on (docs/DESIGN.md section 7).

    On an ELLIPSOID-input job the computed ellipsoid-height row is dropped.
    It is not hidden for tidiness: it recomputes h = H + N from a conversion
    that derived H as h - N, so it is arithmetically the SAME NUMBER as the
    height the user supplied, already on screen one section above. Two rows
    holding one value under one label is worse than one row - and this is the
    row whose label collided when the owner had the "(GNSS," qualifier removed
    (2026-08-11). The reconstruction is still checked, in the audit CSV's own
    "Ellipsoid height (m)" column and by its pin.

    ``pivot_frame_code`` names the frame of that row's h on a transformed job:
    every geoid model publishes N against NAD83(2011), so H + N is a height in
    the pivot's frame, and the audit CSV's own column says
    ``Ellipsoid height (NAD83(2011), m)`` there (``exports._frame_named``).
    None on a same-frame job, whose label is unchanged.

    ``has_a_zone`` False drops the Combined factor row - the GEODETIC_TO_
    GEODETIC layout's rule (work package W5): with no zone there is no grid
    factor, so the combined factor does not exist, and a row of N/A would
    imply a zone could have produced one. The elevation factor stays: it
    needs only the height and the geoid. Every other layout passes True and
    is unchanged to the character - including the vertical-only geodetic
    layout, released in 0.4.0, whose N/A combined row is its own pinned
    decision.
    """
    values = [
        ResultValue(GEOID_HEIGHT_LABEL, fmt.geoid_height(factors.geoid_height)),
    ]
    if not ellipsoid_input:
        values.append(
            ResultValue(
                ELLIPSOID_HEIGHT_LABEL
                if pivot_frame_code is None
                else _framed("Ellipsoid height", pivot_frame_code, "m"),
                fmt.geoid_height(factors.ellipsoid_height),
            )
        )
    values.append(
        ResultValue(ELEVATION_FACTOR_LABEL, fmt.factor(factors.elevation_factor))
    )
    if has_a_zone:
        values.append(
            ResultValue(COMBINED_FACTOR_LABEL, fmt.factor(factors.combined_factor))
        )
    return tuple(values)


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
    #
    # On a geoid-to-geoid point each label also names ITS OWN side's model -
    # input GEOID12B, output GEOID18 (the owner's instruction, 2026-08-10) -
    # because there the datum and the unit are identical at both ends and the
    # model is the only thing telling the two heights apart. The names come
    # from the point's own ``GeoidSwapReading``, not from the settings: a
    # point whose swap was refused (its grids would not read - the
    # GEOID_SWAP_UNAVAILABLE warning) carries no reading and gets no model
    # name, which is the truth about that point even in a job where every
    # other point converted.
    #
    # An ELLIPSOID input relabels both rows, in every mode. The input row
    # says what the user actually supplied; the output row says what is in
    # the Z column, which in horizontal mode is still the ellipsoid height
    # (the owner's pass-through rule) and in the vertical modes is the
    # derived elevation, model-tagged. A row reading "Elevation" over an
    # unconverted h is the falsehood this feature exists to remove, and it
    # would be one column away from a row that reads correctly.
    reading = point.vertical
    swap = point.geoid_swap
    ellipsoid_input = settings.input_height_kind is HeightKind.ELLIPSOID
    # The frame transformation this point underwent, or None (every
    # same-frame job, whose every label below is unchanged). On a transformed
    # job an ellipsoid height is IN a frame (plan decision D6): the input's
    # in the path's source frame, a horizontal job's output - transformed
    # with the position - in its target frame, and the factors' H + N in the
    # pivot's. Each label names its own, as the audit CSV's headings do.
    path = conversion.frame_transformation
    positions = _positions(point, positive_west)
    pivot_code = None if path is None else pivot_frame(path).code
    if reading is not None:
        input_elevation_label = _datum_elevation_label(
            reading.transformation.source,
            settings.input_unit,
            None if swap is None else swap.source_model_name,
        )
        output_elevation_label = _datum_elevation_label(
            reading.transformation.target,
            settings.output_unit,
            None if swap is None else swap.target_model_name,
        )
    else:
        input_elevation_label = ELEVATION_LABEL
        output_elevation_label = ELEVATION_LABEL

    if ellipsoid_input:
        input_elevation_label = _framed(
            ELLIPSOID_INPUT_LABEL,
            None if path is None else path.source.code,
            settings.input_unit.code,
        )
        if not settings.vertical_mode.converts_elevations:
            # Horizontal: the Z was written back untouched, so it is still an
            # ellipsoid height and the label must not promote it. On a
            # transformed job it was transformed WITH the position, so it is
            # the target frame's h (plan decision D6).
            output_elevation_label = _framed(
                ELLIPSOID_INPUT_LABEL,
                None if path is None else path.target.code,
                settings.output_unit.code,
            )
        elif point.ellipsoid_height is not None:
            # A vertical mode DID derive an elevation. Name the datum the
            # model publishes for and the model itself - here, unlike a
            # leveled height, the number genuinely depends on the model.
            output_elevation_label = _datum_elevation_label(
                reading.transformation.target
                if reading is not None
                else settings.target_vertical_datum,
                settings.output_unit,
                point.ellipsoid_height.geoid_model_name,
            )
    vertical_rows = _vertical_rows(reading, swap, settings.input_unit)
    if (
        path is not None
        and ellipsoid_input
        and settings.vertical_mode.converts_elevations
    ):
        # Plan decision D6 in a vertical mode: the typed h was transformed
        # with the position before H = h - N was taken, and the Z written is
        # now the elevation - so the transformed h appears nowhere else on
        # the panel. Shown first among the rows that explain the output
        # elevation, under the audit CSV's own heading and formatter for the
        # same number (``exports.transformed_ellipsoid_height_heading``,
        # ``formatting.geoid_height``); N/A where no height was typed. In
        # Horizontal the output elevation row IS this height, already
        # labelled with its frame, so it is not repeated.
        vertical_rows = (
            ResultValue(
                transformed_ellipsoid_height_heading(path),
                fmt.geoid_height(conversion.target_frame_ellipsoid_height),
            ),
            *vertical_rows,
        )

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
                    *_elevation_dependent_values(factors, ellipsoid_input, pivot_code),
                ),
            )
        else:
            # Geodetic input: no zone anywhere, so no Zone row, no grid
            # factor row and no convergence row - a row of N/A would imply a
            # zone could exist. The elevation-dependent values stay: the
            # geoid height and elevation factor need no zone, and the
            # combined factor honestly reads N/A through the formatter.
            #
            # A WGS 84 or ITRF input (plan decision D8) shows the typed
            # position under its own frame and then the NAD83(2011) pivot
            # every grid was read at - the same point in the frame the geoid
            # and VERTCON models are published against. Same-frame input shows
            # its one position, unchanged.
            source = ResultSection(
                INPUT_TITLE,
                (
                    *positions.input,
                    *positions.pivot,
                    ResultValue(
                        input_elevation_label,
                        fmt.coordinate(point.row.elevation, settings.input_unit),
                    ),
                    ResultValue(UNITS_LABEL, _units_text(settings.input_unit)),
                    *_elevation_dependent_values(factors, ellipsoid_input, pivot_code),
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
        #
        # On an AUTO job the zone is the POINT's own (DESIGN.md #71):
        # settings.target_zone is the AUTO_ZONE sentinel there, which names no
        # zone, and the Zone row is what labels the northing and easting
        # beneath it. Its county follows it.
        auto = is_auto_zone_job(settings)
        target_zone = (
            _auto_assignment(point).zone if auto else settings.target_zone
        )
        grid = _grid_values(
            target_zone,
            settings.output_unit,
            point.output_northing,
            point.output_easting,
            point.output_elevation,
            elevation_label=output_elevation_label,
        )
        if auto:
            grid = (grid[0], *_auto_rows(point), *grid[1:])
        source = ResultSection(
            INPUT_TITLE,
            (
                *positions.input,
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
                *grid,
                # The shift and its sigma read directly under the elevation
                # they explain, before the factors.
                *vertical_rows,
                # On a WGS 84 or ITRF input, the NAD83(2011) position the
                # zone was projected from - where the zone-to-zone layout
                # shows its own geodetic pivot. Empty on a same-frame job.
                *positions.pivot,
                ResultValue(
                    GRID_FACTOR_LABEL, fmt.factor(factors.grid_scale_factor)
                ),
                ResultValue(
                    CONVERGENCE_LABEL,
                    fmt.convergence_display(conversion.target_convergence),
                ),
                *_elevation_dependent_values(factors, ellipsoid_input, pivot_code),
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
                *_elevation_dependent_values(factors, ellipsoid_input, pivot_code),
            ),
        )
        target = ResultSection(
            OUTPUT_TITLE,
            (
                *positions.output,
                ResultValue(
                    output_elevation_label,
                    fmt.coordinate(point.output_elevation, settings.output_unit),
                ),
                *vertical_rows,
                ResultValue(UNITS_LABEL, _units_text(settings.output_unit)),
                # On a WGS 84 or ITRF target, the NAD83(2011) position the
                # zone's inverse produced and HTDP carried out - last, as the
                # intermediate it is. Empty on a same-frame job.
                *positions.pivot,
            ),
        )
        return source, target

    if settings.direction is Direction.GEODETIC_TO_GEODETIC:
        # Plan decision D7: latitude and longitude in, latitude and longitude
        # out, across one HTDP path. No zone anywhere, so no Zone, grid
        # factor, convergence or combined factor row - a row of N/A would
        # imply a zone could exist (the Multi point table drops the same two
        # factor columns on this direction, ``_shows_zone_columns``). Each end shows its own
        # position under its own frame; the NAD83(2011) pivot IS one of the
        # two ends, so it is not repeated. The elevation-dependent values
        # describe the point at the pivot, where the geoid is read, and sit
        # under OUTPUT with the converted height.
        source = ResultSection(
            INPUT_TITLE,
            (
                *positions.input,
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
                *positions.output,
                ResultValue(
                    output_elevation_label,
                    fmt.coordinate(point.output_elevation, settings.output_unit),
                ),
                *vertical_rows,
                ResultValue(UNITS_LABEL, _units_text(settings.output_unit)),
                *_elevation_dependent_values(
                    factors, ellipsoid_input, pivot_code, has_a_zone=False
                ),
            ),
        )
        return source, target

    if settings.direction is not Direction.ZONE_TO_ZONE:
        raise ValueError(
            f"The single-point display has no layout for a "
            f"{settings.direction.name} job. Refused rather than drawing it as "
            f"zone to zone, which would show coordinates from zones the job "
            f"never had."
        )

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
            *_elevation_dependent_values(factors, ellipsoid_input, pivot_code),
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
    return _warnings_text(result.points[0], result.job_warnings)


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
