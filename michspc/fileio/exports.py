"""The job's output: one ZIP archive containing three files.

1. ``<name>_<zone>.csv``       - clean PNEZD, for import straight into CAD
2. ``<name>_<zone>_full.csv``  - every computed quantity, for the record
3. ``<name>_<zone>_README.txt``- the job record explaining both (report.py)

**The archive is the only deliverable.** Nothing is written loose beside it
(docs/DESIGN.md amendment #17). The three files travel together or not at all,
so a PNEZD export cannot be filed or emailed without the record explaining how
it was derived - which matters for a file that ends up supporting a sealed
survey. The cost is that importing into CAD means unzipping first; that was the
owner's explicit trade.

The clean export carries nothing but the five PNEZD fields. Warning flags
and scale factors live in the other two, because a CAD import
that meets an unexpected sixth column either fails or silently shifts
everything one field left.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

from michspc.fileio import formatting as fmt
from michspc.fileio.writers import WriteError, staged_write
from michspc.job import Direction, JobResult
from michspc.spc.vertical import HeightKind

_PNEZD_HEADERLESS = True
"""The clean export has no header row, matching the input format exactly.

A header would make the output un-round-trippable through this program's own
reader, which is the property `verify_round_trip` below exists to guarantee.
"""


def _geodetic_coordinate_columns(settings) -> bool:
    """Whether this job's OUTPUT coordinate columns hold degrees.

    True for a State-Plane-to-geodetic job, and for a vertical-only job whose
    input is geodetic - that job's exports mirror the input's own layout, so
    a geodetic input keeps geodetic columns. Stated once, here, because the
    clean export, the audit CSV and the round-trip verifier must all take
    the same branch or the verifier would check a file that was not written.
    """
    return settings.direction is Direction.ZONE_TO_GEODETIC or (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is None
    )


def _geodetic_source_columns(settings) -> bool:
    """Whether this job's INPUT file's columns two and three hold degrees."""
    return settings.direction is Direction.GEODETIC_TO_ZONE or (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is None
    )


def output_stem(result: JobResult) -> str:
    """``<input stem>_<zone abbreviation>``, e.g. ``24-118-topo_MI-C``."""
    settings = result.settings
    if settings.input_path is None:
        # The stem of every member of the archive is built from the input file's
        # name, so a job that came from no file cannot be named. Refused rather
        # than substituting something like "typed" or "untitled": the members
        # would then claim to describe a file that does not exist, in the one
        # deliverable a sealed survey is supported by (amendment #26).
        raise WriteError(
            "This job states it came from no input file "
            "(JobSettings.input_path is None), so its export cannot be named - "
            "every file inside the archive is named after the input file. A "
            "job with no file, such as a single typed point, is displayed "
            "rather than written."
        )
    if settings.direction is Direction.ZONE_TO_GEODETIC:
        suffix = "GEODETIC"
    elif settings.direction is Direction.VERTICAL_ONLY:
        # No target zone exists in this mode, so no abbreviation could name
        # the export; what happened to the file is the vertical conversion.
        suffix = "VERTICAL"
    else:
        suffix = settings.target_zone.abbrev
    return f"{settings.input_path.stem}_{suffix}"


def clean_pnezd_rows(result: JobResult) -> list[list[str]]:
    """The CAD-bound export: point, northing, easting, elevation, description."""
    settings = result.settings
    rows: list[list[str]] = []

    for point in result.points:
        if _geodetic_coordinate_columns(settings):
            # For a vertical-only geodetic job these are the INPUT positions
            # re-rendered through the standard formatters - the longitude
            # exactly as the file wrote it, in its own convention - so the
            # export mirrors the import, formatting-normalized.
            northing = fmt.latitude(point.output_northing)
            easting = fmt.longitude(point.output_easting)
            # The OUTPUT unit, exactly as in every other direction. The columns
            # either side of it are degrees, but the Z column is still linear
            # and the job record's "Units out" and "Precision written" lines
            # both describe it in the output unit (WP-R2 fix A).
            elevation = fmt.coordinate(point.output_elevation, settings.output_unit)
        else:
            northing = fmt.coordinate(point.output_northing, settings.output_unit)
            easting = fmt.coordinate(point.output_easting, settings.output_unit)
            elevation = fmt.coordinate(point.output_elevation, settings.output_unit)

        rows.append(
            [point.point_id, northing, easting, elevation, point.row.description]
        )

    return rows


SOURCE_COLUMNS_LINEAR = ("Source northing", "Source easting")
SOURCE_COLUMNS_GEODETIC = ("Source latitude", "Source longitude (as in file)")
"""What columns 3 and 4 of the audit CSV are called, per direction.

The linear pair is the header for every direction whose input file holds grid
coordinates, and it is deliberately unchanged. The geodetic pair replaces it
only when the input file's columns two and three hold degrees, because
"Source northing: 42.733" is not a shortened number, it is a wrong statement
about what the file contained (WP-R2 fix F).

"as in file" rather than a sign convention in the header: the column reproduces
the longitude exactly as the surveyor wrote it, in whichever convention the job
record's Longitude line names. The signed pivot has its own column further
along, already labelled "Longitude (neg west)".
"""

TARGET_COLUMNS_LINEAR = ("Target northing", "Target easting")
TARGET_COLUMNS_GEODETIC = ("Target latitude", "Target longitude (as written)")
"""The same two spellings for columns 6 and 7, the converted position.

A State-Plane-to-geodetic job has always written degrees into these two - the
values were never wrong - under headings that named them a northing and an
easting. Renamed for that direction only, for the same reason as the source
pair and so the audit CSV and the results table now agree on what the columns
are called.
"""

def vertical_shift_and_sigma_m(point) -> tuple[float | None, float | None]:
    """``(shift, sigma)`` in metres for a point's shift and sigma cells, or
    None where no number exists.

    THE one statement of which numbers those two columns carry, shared by
    the audit CSV (``audit_rows``) and the on-screen Multi point table
    (``results_model.row_strings``), so the two surfaces cannot disagree:

    * a geoid-to-geoid point carries the SWAP shift - the value that moved
      the height, ``GeoidSwapReading.shift_m`` - and no sigma: NGS
      publishes no error model for the difference between two of its geoid
      models, so N/A is the only honest cell (docs/DESIGN.md #36's rule,
      arriving at a new absence);
    * every other point with a ``VerticalReading`` carries the datum shift
      and its sigma, exactly as before;
    * a point with neither reading - no elevation, or a coverage refusal -
      carries neither number.
    """
    if point.geoid_swap is not None:
        return point.geoid_swap.shift_m, None
    if point.vertical is not None:
        return point.vertical.shift_m, point.vertical.sigma_m
    return None, None


def vertical_shift_heading(unit) -> str:
    """``Vertical shift (ift)`` - the audit CSV's shift column heading.

    THE authoritative wording: the Multi point table and the Single point
    panel's shift-row suffix carry this unit code too, per #17's standing
    choice of one wording on every surface (the table imports this function
    rather than restating it). The unit passed is the JOB'S INPUT UNIT - the
    owner's instruction (2026-08-09): the shift is read against the elevation
    the surveyor supplied, so it is stated in the unit that elevation was
    typed in. The value under this heading converts with it, in
    ``audit_rows`` - a heading claiming feet over a metre value would be the
    worst outcome of this change, so the two are built from the same unit
    object and pinned together.
    """
    return f"Vertical shift ({unit.code})"


def vertical_sigma_heading(unit) -> str:
    """``Shift sigma (ift)`` - the sigma column heading, same rule as the
    shift's: the job's input unit, one wording on every surface (#17), the
    cell converted by the same unit object."""
    return f"Shift sigma ({unit.code})"


AUDIT_COLUMNS = [
    "Point",
    "Source zone",
    *SOURCE_COLUMNS_LINEAR,
    "Target zone",
    *TARGET_COLUMNS_LINEAR,
    "Elevation",
    "Units",
    "Latitude",
    "Longitude (neg west)",
    "Geoid height (m)",
    "Ellipsoid height (m)",
    "Source grid scale factor",
    "Source convergence",
    "Grid scale factor",
    "Convergence",
    "Elevation factor",
    "Combined factor",
    "Combined factor (ppm)",
    "Warnings",
    "Description",
]


ELLIPSOID_ELEVATION_HEADING = "Ellipsoid height"
"""What the audit CSV's Elevation column is called on a HORIZONTAL job whose
Z holds GNSS heights.

The cell carries the height exactly as supplied - horizontal mode does not
convert it - so "Elevation" over it is a false heading on a number about 33 m
from the elevation it claims to be. Matches the panel's own wording for the
same value (``results_model.ELLIPSOID_INPUT_LABEL``), per #17's one-wording
rule.
"""


def audit_columns(result: JobResult) -> list[str]:
    """The audit CSV's header row for this job's direction.

    Identical to ``AUDIT_COLUMNS`` except where one end of the job is geodetic,
    in which case that end's pair of columns is renamed to say what it actually
    holds. The other end's headings never move.

    A job that converts elevations (``VerticalMode.converts_elevations`` -
    HORIZONTAL_AND_VERTICAL, and vertical-only) additionally carries six
    columns a horizontal CSV must never grow (WP-V7,
    docs/PLAN-vertical-datums.md section 5.2):

    * ``Source vertical datum`` / ``Target vertical datum`` - which surface
      each end's heights are expressed in, per row, so a row cut out of this
      file still says what its two heights mean.
    * ``Source elevation (<input unit>)`` - the PRE-shift height as the file
      supplied it, so this file answers "how was this Z derived" without
      re-running anything. The existing ``Elevation`` column keeps the TARGET
      height, which is what the clean export carries.
    * ``Vertical shift (<input unit>)`` - the modeled shift applied,
      converted into the job's input unit (the owner's instruction,
      2026-08-09 - the unit the elevations were supplied in; in vertical-only
      mode input and output units are equal by construction, and in
      Horizontal + Vertical the input unit still governs these two columns
      while the Elevation column stays in the output unit as always). 0.0000
      for an identity, which really is a zero shift, not an absence.
    * ``Shift sigma (<input unit>)`` - its one-sigma uncertainty, same unit
      as the shift it qualifies, and ``formatting.NOT_AVAILABLE`` where none
      can be stated (an identity ran no model; where the error model
      interpolates below zero there is no physical sigma) - NEVER a number in
      either case (docs/DESIGN.md #36).
    * ``Geoid model`` - which model's separations the factor columns were
      computed from. Two shipped models now differ by up to 32 mm at one
      Michigan anchor (DESIGN.md #40 LOW 5), so a vertical CSV names its own.
      A HORIZONTAL CSV deliberately does NOT gain this column: its layout is
      the status quo since 0.1.0, relied on by downstream spreadsheets, and
      the job record inside the same ZIP names the model (#17) - that
      standing mitigation stays the horizontal answer.
    """
    columns = list(AUDIT_COLUMNS)
    settings = result.settings
    if _geodetic_source_columns(settings):
        columns[2], columns[3] = SOURCE_COLUMNS_GEODETIC
    if _geodetic_coordinate_columns(settings):
        columns[5], columns[6] = TARGET_COLUMNS_GEODETIC
    if settings.input_height_kind is HeightKind.ELLIPSOID:
        # One column, present exactly when the job stated ellipsoid input, so
        # no pre-existing job's layout moves by a byte. It earns its place on
        # a HORIZONTAL job especially: there the Elevation column holds the
        # ellipsoid height itself, passed through, and a row cut out of this
        # file and pasted elsewhere would otherwise carry no statement at all
        # of what kind of height it is - the same reasoning that put "Source
        # vertical datum" on every row of a vertical job.
        columns.insert(columns.index("Elevation") + 1, "Input height kind")
        if not settings.vertical_mode.converts_elevations:
            # HORIZONTAL: the Elevation cell holds the ellipsoid height itself,
            # passed through, so the heading must say so. Leaving it as
            # "Elevation" put h in a column labelled H - wrong by about 33 m,
            # and the adjacent kind column mitigates it only for a reader who
            # notices the column (closing gate, HIGH 1). In the vertical modes
            # the heading is rewritten with the datum and model further down,
            # which is already correct.
            columns[columns.index("Elevation")] = ELLIPSOID_ELEVATION_HEADING

    if settings.vertical_mode.converts_elevations:
        # The vertical block sits directly after Elevation, so the target
        # height and the ingredients it was derived from read side by side;
        # Geoid model sits directly before the geoid height it governs.
        anchor = (
            columns.index("Input height kind") + 1
            if settings.input_height_kind is HeightKind.ELLIPSOID
            else columns.index("Elevation") + 1
        )
        vertical_block = [
            "Source vertical datum",
            "Target vertical datum",
            f"Source elevation ({settings.input_unit.code})",
            vertical_shift_heading(settings.input_unit),
            vertical_sigma_heading(settings.input_unit),
        ]
        if settings.input_height_kind is HeightKind.ELLIPSOID:
            # The height the file actually supplied, in its own column, so
            # "Source elevation" can go on meaning what it has always meant -
            # the PRE-SHIFT orthometric height - and the row's arithmetic
            # stays closed: Source elevation + Vertical shift = Elevation.
            # Without it one of those two facts has to give.
            vertical_block.insert(
                2, f"Ellipsoid height in ({settings.input_unit.code})"
            )
        columns[anchor:anchor] = vertical_block
        if settings.source_geoid_model is not None:
            # The per-side feature's one new column, present exactly when
            # the job STATED an input-side model: which geoid model the
            # source elevations were stated against, beside the existing
            # "Geoid model" (which keeps naming the factors/output side).
            # Every job shape that predates the field - horizontal, and
            # every #41-era vertical shape - states None here and its CSV
            # layout does not change by a byte.
            columns.insert(columns.index("Geoid height (m)"), "Source geoid model")
        columns.insert(columns.index("Geoid height (m)"), "Geoid model")
    return columns


def audit_rows(result: JobResult) -> list[list[str]]:
    """Every computed quantity for every point, with a header row.

    This is the file that answers "how was this coordinate derived" without
    anyone having to re-run the program.
    """
    settings = result.settings
    out_unit = settings.output_unit
    in_unit = settings.input_unit
    geodetic_source = _geodetic_source_columns(settings)
    geodetic_target = _geodetic_coordinate_columns(settings)
    vertical = settings.vertical_mode.converts_elevations

    header = audit_columns(result)
    rows: list[list[str]] = [header]

    for point in result.points:
        conversion = point.conversion
        factors = point.factors

        # The source columns hold whatever the file's columns two and three
        # held. For a geodetic input that is a latitude and a longitude in
        # decimal degrees, and formatting them as linear coordinates rounded
        # them to the unit's 3 places: 42.73250000 was recorded as 42.733,
        # about 55 m of latitude, and -84.55550000 as -84.555, about 37 m of
        # longitude - in the one file that exists to say how the number was
        # derived (WP-R2 fix F). The longitude is printed as the file wrote it,
        # in the job's own convention; the signed pivot has its own column.
        if geodetic_source:
            source_northing = fmt.latitude(point.row.northing)
            source_easting = fmt.longitude(point.row.easting)
        else:
            source_northing = fmt.coordinate(point.row.northing, in_unit)
            source_easting = fmt.coordinate(point.row.easting, in_unit)

        # What the "Target zone" cell says the output system is. A
        # vertical-only job HAS no output horizontal system - the coordinate
        # columns beside this cell reproduce the input's - so the honest
        # statement is the direction itself: "vertical only".
        if settings.direction is Direction.VERTICAL_ONLY:
            target_system = settings.direction.value
        elif settings.target_zone:
            target_system = settings.target_zone.name
        else:
            target_system = "geodetic"

        row = (
            [
                point.point_id,
                settings.source_zone.name if settings.source_zone else "",
                source_northing,
                source_easting,
                target_system,
                fmt.coordinate(point.output_northing, out_unit)
                if not geodetic_target
                else fmt.latitude(point.output_northing),
                fmt.coordinate(point.output_easting, out_unit)
                if not geodetic_target
                else fmt.longitude(point.output_easting),
                fmt.coordinate(point.output_elevation, out_unit),
                f"in {in_unit.code}, out {out_unit.code}",
                fmt.latitude(conversion.latitude),
                fmt.longitude(conversion.longitude),
                fmt.geoid_height(factors.geoid_height),
                fmt.geoid_height(factors.ellipsoid_height),
                fmt.factor(conversion.source_scale_factor),
                fmt.angle_dms(conversion.source_convergence),
                fmt.factor(factors.grid_scale_factor),
                fmt.angle_dms(conversion.target_convergence),
                fmt.factor(factors.elevation_factor),
                fmt.factor(factors.combined_factor),
                fmt.signed_parts_per_million(factors.combined_factor),
                "; ".join(w.code.value for w in point.warnings),
                point.row.description,
            ]
        )

        if settings.input_height_kind is HeightKind.ELLIPSOID:
            row.insert(
                header.index("Input height kind"), settings.input_height_kind.value
            )

        if vertical:
            # Inserted at the vertical header's own indexes, computed from the
            # header this function just built, so the cells cannot land under
            # the wrong headings if either insertion point moves. The vertical
            # block first (it sits earlier), then Geoid model.
            # Which numbers the shift and sigma cells carry is stated once,
            # in vertical_shift_and_sigma_m, and shared with the on-screen
            # table: the datum reading's pair ordinarily, the SWAP shift
            # with no sigma on a geoid-to-geoid point, neither where no
            # reading exists (no elevation, or a coverage refusal - the
            # warnings cell says which). An identity reading carries
            # shift_m=0.0 - a real zero, printed as one; sigma_m is None on
            # an identity (no model ran) and where the error model
            # interpolates below zero (DESIGN.md #36) - both render N/A
            # through the formatter, never the raw figure.
            shift_m, sigma_m = vertical_shift_and_sigma_m(point)
            insert_at = header.index("Source vertical datum")
            # The PRE-shift ORTHOMETRIC height. For an orthometric-input job
            # that is exactly what the file supplied; for an ellipsoid-input
            # job it is the height DERIVED from it, because this column means
            # "what the vertical shift was applied to" and the shift was
            # applied to H, never to h. N/A where no height was derived - a
            # blank Z, or a point off the geoid tile.
            source_elevation = point.row.elevation
            if settings.input_height_kind is HeightKind.ELLIPSOID:
                source_elevation = (
                    in_unit.from_meters(point.ellipsoid_height.orthometric_height_m)
                    if point.ellipsoid_height is not None
                    else None
                )
            vertical_cells = [
                settings.source_vertical_datum.code,
                settings.target_vertical_datum.code,
                fmt.coordinate(source_elevation, in_unit),
                # Both cells are converted into IN_UNIT - the same unit
                # object the two headings above were built from, so heading
                # and value cannot claim different units.
                fmt.vertical_quantity(shift_m, in_unit),
                fmt.vertical_quantity(sigma_m, in_unit),
            ]
            if settings.input_height_kind is HeightKind.ELLIPSOID:
                vertical_cells.insert(
                    2, fmt.coordinate(point.row.elevation, in_unit)
                )
            row[insert_at:insert_at] = vertical_cells
            if settings.source_geoid_model is not None:
                row.insert(
                    header.index("Source geoid model"),
                    settings.source_geoid_model.name,
                )
            row.insert(
                header.index("Geoid model"),
                # result.geoid_model is the name of the model the factors
                # were computed from, or None for a job that stated no geoid
                # is applied - in which case there is no model to name and
                # the factor columns beside it are N/A too.
                result.geoid_model
                if result.geoid_model is not None
                else fmt.NOT_AVAILABLE,
            )

        rows.append(row)

    return rows


def _expected_coordinates(result: JobResult, point) -> tuple[str, float, str, float]:
    """What the export's columns two and three must carry for this point.

    Returns ``(name, value, name, value)`` - the label the round-trip refusal
    uses for each column, and the number the job computed for it. Reads the
    same branch ``clean_pnezd_rows`` writes, so the two cannot describe
    different columns.
    """
    if _geodetic_coordinate_columns(result.settings):
        return ("latitude", point.output_northing, "longitude", point.output_easting)
    return ("northing", point.output_northing, "easting", point.output_easting)


def _written_decimals(result: JobResult, geodetic: bool) -> int:
    """The number of decimal places the column in question was written to.

    Degrees are written to 8 places by ``formatting.latitude`` and
    ``formatting.longitude``; a linear column is written to its unit's own
    declared precision. The round-trip tolerance below is derived from this and
    from nothing else.
    """
    return 8 if geodetic else result.settings.output_unit.decimals


# _rounding_tolerance stood here until the vertical-only gate (DESIGN.md #46,
# MEDIUM 2): verify_round_trip now compares the re-read value EXACTLY against
# the value the writer promised - the job's number rendered at the written
# precision - rather than the pre-rounding float within half a place. The
# tolerance form carried a trap: a value whose next decimal is exactly 5
# rounds a hair past half a place, and in vertical-only mode the value is the
# user's own literal, so ordinary metre northings refused the whole archive.
# The exact form is strictly tighter and keeps every real failure.


def verify_round_trip(rows: list[list[str]], result: JobResult) -> None:
    """Refuse to write a PNEZD file this program's own reader would reject.

    METHOD.md section 5: "a writer that refuses to produce a file its own
    reader would reject". The rows are rendered, re-parsed, and checked field
    for field against what the job computed, before anything reaches its final
    name.

    This has real teeth: a description containing a comma, an identifier
    containing a quote, or a value formatted as "nan" would all produce a file
    that looks written and imports wrongly.

    **Every field the reader returns is compared, not only the identifier.**
    It used to check ``point_id`` alone, and the reviewer demonstrated the
    consequence by replacing the whole expected row
    ``101,449212.689,13072628.343,N/A,IP`` with
    ``101,999999.999,888888.888,777.777,WRONG DESCRIPTION``: every coordinate,
    the elevation and the description were corrupted and the program's own
    safety gate passed the file (WP-R3 fix 1).

    **Compared against the reader's semantics, not against raw text.** The
    reader trims surrounding whitespace and treats a blank field, "N/A" and an
    exact 0.00 alike as "no elevation recorded", so the comparison is made
    against what it returns - a float, or None - rather than against the
    characters in the cell. The numeric comparison is EXACT against the value
    the writer promised - the job's number rendered at the written precision -
    see the note where ``_rounding_tolerance`` used to stand (DESIGN.md #46).
    """
    from michspc.fileio import pnezd

    rendered = []
    for row in rows:
        cells = []
        for cell in row:
            text = str(cell)
            if "," in text or '"' in text:
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        rendered.append(",".join(cells))

    try:
        reparsed = pnezd.parse_lines(rendered, path="<export being verified>")
    except pnezd.PnezdError as error:
        raise WriteError(
            f"The export this program built cannot be read back by its own "
            f"reader, so it was not written: {error}"
        ) from error

    if len(reparsed.rows) != len(result.points):
        raise WriteError(
            f"The export contains {len(reparsed.rows)} rows but the job "
            f"converted {len(result.points)} points. Nothing was written."
        )

    geodetic = _geodetic_coordinate_columns(result.settings)
    horizontal_decimals = _written_decimals(result, geodetic)
    elevation_decimals = _written_decimals(result, False)

    # The expectation is the value the writer PROMISED - the job's number
    # rendered at the written precision - compared exactly, not the
    # pre-rounding float compared within a tolerance. The tolerance form
    # carried a trap the vertical-only mode made probable: there
    # output_northing is the user's own literal, and a metre value whose 5th
    # decimal is exactly 5 rounds a hair past half a place, so the whole
    # archive refused to write over its own correct rendering - fail-closed,
    # but a refusal 83% of Michigan metre northings in the worst band could
    # trip, naming this program's reader instead of anything the user could
    # act on (vertical-only gate, MEDIUM 2). In every pre-existing direction
    # the value is a computed projection result, where landing on an exact
    # rounding half-way point has probability ~2^-52 - which is why three
    # releases never saw it. Rendering the expectation makes the comparison
    # EXACT (strictly tighter than the old tolerance) and keeps every real
    # failure: a wrong value, a shifted column, or a "nan" cell still
    # mismatches - float("nan") != float("nan"), so a NaN still refuses.

    def promised(value: float, decimals: int) -> float:
        return float(f"{value:.{decimals}f}")

    for parsed_row, point in zip(reparsed.rows, result.points):
        if parsed_row.point_id != point.point_id:
            raise WriteError(
                f"Round-trip check failed: the export's row reads point "
                f"{parsed_row.point_id!r} where the job converted "
                f"{point.point_id!r}. Nothing was written."
            )

        first, first_value, second, second_value = _expected_coordinates(result, point)
        for label, expected, actual in (
            (first, first_value, parsed_row.northing),
            (second, second_value, parsed_row.easting),
        ):
            if actual != promised(expected, horizontal_decimals):
                raise WriteError(
                    f"Round-trip check failed on point {point.point_id!r}: the "
                    f"export's {label} reads back as {actual!r} where the job "
                    f"computed {expected!r}. Nothing was written."
                )

        # The elevation is the one field with an absence. The reader maps a
        # blank field, "N/A" and an exact 0.00 all to None, so the two states
        # are compared before the two numbers are - and a job value that the
        # formatter would round to 0.000, which the reader would then hand back
        # as "not recorded", is a real round-trip failure and refused as one.
        if (point.output_elevation is None) != (parsed_row.elevation is None):
            raise WriteError(
                f"Round-trip check failed on point {point.point_id!r}: the "
                f"export's elevation reads back as {parsed_row.elevation!r} "
                f"where the job computed {point.output_elevation!r}. Nothing "
                f"was written."
            )
        if point.output_elevation is not None and parsed_row.elevation != promised(
            point.output_elevation, elevation_decimals
        ):
            raise WriteError(
                f"Round-trip check failed on point {point.point_id!r}: the "
                f"export's elevation reads back as {parsed_row.elevation!r} "
                f"where the job computed {point.output_elevation!r}. Nothing "
                f"was written."
            )

        # The description survives as text. Compared against the reader's own
        # form of it - the input row's description was itself produced by this
        # reader, and so is already trimmed and already rejoined at any commas.
        if parsed_row.description != point.row.description:
            raise WriteError(
                f"Round-trip check failed on point {point.point_id!r}: the "
                f"export's description reads back as "
                f"{parsed_row.description!r} where the job converted "
                f"{point.row.description!r}. Nothing was written."
            )


def member_names(result: JobResult) -> dict[str, str]:
    """The three file names inside the archive, keyed by role."""
    stem = output_stem(result)
    return {
        "pnezd": f"{stem}.csv",
        "audit": f"{stem}_full.csv",
        "report": f"{stem}_README.txt",
    }


def destination_paths(result: JobResult) -> tuple[Path, ...]:
    """Every path this job would write. Exactly one: the archive.

    Exists so callers - the GUI's overwrite check in particular - do not have to
    reconstruct the naming rule and drift out of step with it.
    """
    return (archive_path(result),)


def archive_path(result: JobResult) -> Path:
    """``<output folder>/<stem>.zip`` - the job's single deliverable."""
    if result.settings.output_directory is None:
        # Refused rather than falling back on the working directory, which is
        # wherever the program happened to be started from and is the one place
        # a surveyor would never look for a deliverable (amendment #26).
        raise WriteError(
            "This job states it produces no file "
            "(JobSettings.output_directory is None), so there is nowhere to "
            "write its archive. A job with no output folder, such as a single "
            "typed point, is displayed rather than written."
        )
    return result.settings.output_directory / f"{output_stem(result)}.zip"


def _render_csv(rows: list[list[str]]) -> str:
    """Format rows as CSV text, quoting exactly as write_csv_rows does."""
    lines = []
    for row in rows:
        cells = []
        for cell in row:
            text = "" if cell is None else str(cell)
            if "," in text or '"' in text or "\n" in text:
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        lines.append(",".join(cells))
    return "\r\n".join(lines) + "\r\n"


def _flush_to_disk(path: Path) -> None:
    """Force the staged archive out of the operating system's buffers.

    ``atomic_write_text`` in michspc.fileio.writers has always done this and the
    ZIP path never did, so the one deliverable this program produces was the one
    file it renamed onto its final name without knowing the bytes had landed. A
    rename is atomic with respect to the directory entry, not with respect to
    the data behind it: after a power loss or a crash the name can exist over a
    partly-written file (WP-R3 fix 4).

    Reopened rather than fsynced through the ``ZipFile``'s own handle because
    ``ZipFile`` closes that handle when its context exits, and the central
    directory is written on the way out.
    """
    with open(path, "rb+") as stream:
        stream.flush()
        os.fsync(stream.fileno())


def _verify_archive(staged: Path, expected_members: tuple[str, ...]) -> None:
    """Read the staged archive back before it is allowed to take its final name.

    Three questions, all cheap on files of this size: does every member's CRC
    match what the archive claims (``testzip``), is every expected member
    present, and is any of them empty. A corrupt or truncated archive that
    reached the deliverable name would be discovered by the surveyor, at the
    point of unzipping it, with the previous export already replaced.

    The three members are all non-empty by construction - the clean export has
    one line per point, the audit CSV has a header row at minimum, and the job
    record is several pages - so a zero-length member means the writing failed
    silently rather than meaning the job had nothing to say.
    """
    try:
        with zipfile.ZipFile(staged) as archive:
            damaged = archive.testzip()
            if damaged is not None:
                raise WriteError(
                    f"The archive this program built is corrupt: the stored "
                    f"member {damaged!r} does not match its own checksum. "
                    f"Nothing was written."
                )

            present = set(archive.namelist())
            missing = [name for name in expected_members if name not in present]
            if missing:
                raise WriteError(
                    f"The archive this program built is missing "
                    f"{', '.join(repr(name) for name in missing)}. The three "
                    f"files travel together or not at all, so nothing was "
                    f"written."
                )

            for name in expected_members:
                if archive.getinfo(name).file_size == 0:
                    raise WriteError(
                        f"The archive this program built holds {name!r} as an "
                        f"empty file. Nothing was written."
                    )
    except zipfile.BadZipFile as error:
        raise WriteError(
            f"The archive this program built cannot be opened as a ZIP file, "
            f"so it was not written: {error}"
        ) from error


def write_all(result: JobResult, overwrite: bool = False) -> dict[str, Path]:
    """Write the job's single ZIP deliverable, or nothing at all.

    The three files travel together or not at all (docs/DESIGN.md amendment
    #17), so a PNEZD export can never be filed or emailed without the record
    explaining how it was derived.

    Order matters here. Every coordinate is checked finite and the PNEZD export
    is round-tripped through this program's own reader BEFORE the archive is
    staged; the staged archive is then flushed to the disk and read back in full
    BEFORE it is renamed onto its final name. A job therefore either produces a
    complete, readable deliverable or leaves the output folder exactly as it
    found it.

    Returns a mapping of role to path. Both entries point at the same archive;
    the roles are kept so callers can say which member they mean.
    """
    from michspc.fileio.report import build_report

    for point in result.points:
        for label, value in (
            ("northing", point.output_northing),
            ("easting", point.output_easting),
        ):
            if not fmt.is_finite(value):
                raise WriteError(
                    f"Point {point.point_id} produced a non-finite {label} "
                    f"({value!r}). Nothing was written - a coordinate that is "
                    f"not a number must never reach a file."
                )

    clean = clean_pnezd_rows(result)
    verify_round_trip(clean, result)

    names = member_names(result)
    contents = {
        names["pnezd"]: _render_csv(clean),
        names["audit"]: _render_csv(audit_rows(result)),
        names["report"]: build_report(result),
    }

    destination = archive_path(result)
    with staged_write(destination, overwrite=overwrite) as staged:
        with zipfile.ZipFile(
            staged, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for name, text in contents.items():
                # Written as UTF-8 with CRLF already embedded by _render_csv and
                # by the report builder, so the extracted files open correctly
                # in Notepad and import correctly into CAD on Windows.
                archive.writestr(name, text.encode("utf-8"))

        # Still inside staged_write's body, so a refusal here unlinks the
        # staged file and leaves the destination exactly as it was.
        _flush_to_disk(staged)
        _verify_archive(staged, tuple(contents))

    return {"archive": destination, **{role: destination for role in names}}
