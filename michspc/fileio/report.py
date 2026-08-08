"""The job record - the plain-text file that explains the exports.

The owner chose "full record, but factors summarized": everything about how the
conversion was performed, with per-point scale factors left to the audit CSV
rather than duplicated here. So this document carries what the CSV cannot -
provenance, settings, citations, summary statistics, and every warning - and
points at the CSV for the per-point detail.

It is written to be readable in Notepad by a surveyor who did not run the
conversion, six months later.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

from michspc import APP_NAME, __version__
from michspc.fileio import formatting as fmt
from michspc.fileio.geoid import geoid_model_by_name
from michspc.job import Direction, JobResult
from michspc.spc.convert import WarningCode
from michspc.spc.factors import MEAN_EARTH_RADIUS_M
from michspc.spc.lambert import constants_for

_RULE = "=" * 78
_THIN = "-" * 78

_WARNING_HEADINGS = {
    WarningCode.EASTING_UNLIKE_SELECTED_ZONE: (
        "COORDINATES MAY NOT BE IN THE SELECTED SOURCE ZONE"
    ),
    WarningCode.OUTSIDE_ZONE_EXTENT: "POINTS OUTSIDE THE TARGET ZONE'S AREA",
    WarningCode.GEOID_UNAVAILABLE: (
        "ELEVATION RECORDED, BUT NO GEOID HEIGHT AT THIS POSITION"
    ),
}
"""Readable headings for the warning kinds this program currently raises.

Presentation only. It does NOT decide which warnings are printed - see
``_warning_codes_present``. A heading missing from this table changes how a
warning is introduced, never whether the surveyor is shown it.
"""


def _warning_codes_present(result: JobResult) -> list:
    """Every warning code this job actually raised, in the order to print.

    Driven by the warnings, not by ``_WARNING_HEADINGS``. Iterating the heading
    table instead would mean a warning kind added later, before anyone wrote it
    a heading, was counted in the "N warning(s)" total at the top of the section
    and then never printed underneath it - the report telling the surveyor that
    something is wrong and declining to say what. Latent rather than live today,
    because both current codes have headings; structural, because the next code
    added would activate it silently.

    Known kinds keep their declared order so the section reads the same way from
    job to job; anything unheaded follows, in the order it first appeared.
    """
    raised = []
    for _point_id, warning in result.warnings:
        if warning.code not in raised:
            raised.append(warning.code)

    known = [code for code in _WARNING_HEADINGS if code in raised]
    return known + [code for code in raised if code not in _WARNING_HEADINGS]


def _warning_heading(code) -> str:
    """A heading for a code, falling back to the code itself.

    The fallback is deliberately the raw code text rather than something
    generic like "OTHER": a surveyor reading an unfamiliar heading can search
    for it, and it is honest about being unpolished.
    """
    registered = _WARNING_HEADINGS.get(code)
    if registered is not None:
        return registered
    return str(getattr(code, "value", code)).replace("-", " ").replace("_", " ").upper()


def _input_format_block(settings) -> list[str]:
    """What the input file's five columns actually held, and in what units.

    Direction-aware, because the input is not always PNEZD. When a job starts
    from geodetic positions, columns two and three are a latitude and a
    longitude in decimal degrees - not a northing and an easting in the linear
    unit - and this block used to say otherwise in a document that is signed,
    filed and believed.

    That is the same confusion docs/DESIGN.md amendment #16 note 1 called "a
    correctness aid, not cosmetics" for the input hint on screen: the two
    layouts are indistinguishable from the numbers, because a geodetic file
    read as PNEZD yields a plausible coordinate rather than an error. The
    record has to describe the file that was actually read.

    The longitude sign convention is stated here as well as on the OUTPUT
    section's "Longitude" line. It is not a duplicate for its own sake: a
    reader who takes columns two and three as latitude and longitude has still
    not been told which way west is signed, and the two readings are 340 miles
    apart (docs/DESIGN.md section 7). The description of the file cannot be
    read without it.
    """
    unit = settings.input_unit
    if settings.direction is Direction.GEODETIC_TO_ZONE:
        return [
            "Format             Comma separated, no header row - NOT PNEZD",
            "                   point, latitude, longitude, elevation, description",
            "                   description is everything after the fourth comma",
            "                   Columns two and three are DECIMAL DEGREES, read",
            f"                   as {settings.longitude_convention.value}.",
            f"Units in           {unit.name} ({unit.code}) - the ELEVATION column only",
            "                   Columns two and three are degrees and carry no",
            "                   linear unit.",
            f"                   {unit.citation}",
        ]
    return [
        "Format             PNEZD, no header row",
        "                   point, northing, easting, elevation, description",
        "                   description is everything after the fourth comma",
        f"Units in           {unit.name} ({unit.code}) - northing, easting and elevation",
        f"                   {unit.citation}",
    ]


def _clean_export_block(settings) -> list[str]:
    """What the clean export's five columns hold. Direction-aware.

    "in the same PNEZD layout as the input" is true only of a zone-to-zone job.
    Converting TO geodetic writes a latitude and a longitude in columns two and
    three; converting FROM geodetic writes PNEZD out of a file that was never
    PNEZD going in. In both cases the old sentence described a file that is not
    on the disk, and this record is the only documentation the program produces
    (docs/DESIGN.md amendment #13).
    """
    unit = settings.output_unit
    if settings.direction is Direction.ZONE_TO_GEODETIC:
        return [
            "    The converted positions - NOT PNEZD, and NOT the same layout as",
            "    the input: point, latitude, longitude, elevation, description,",
            "    no header row.",
            "    Columns two and three are DECIMAL DEGREES to 8 places, written",
            f"    {settings.longitude_convention.value}.",
            f"    The elevation column is {unit.name} ({unit.code}).",
            "    Nothing else.",
        ]
    if settings.direction is Direction.GEODETIC_TO_ZONE:
        opening = [
            "    The converted coordinates in PNEZD layout - which the INPUT file",
            "    was not: point, northing, easting, elevation, description, no",
            "    header row.",
        ]
    else:
        opening = [
            "    The converted coordinates, in the same PNEZD layout as the input:",
            "    point, northing, easting, elevation, description - no header row.",
        ]
    return opening + [
        f"    Northing, easting and elevation are {unit.name} ({unit.code}).",
        "    Nothing else. Extract this one and import it into CAD.",
    ]


def _zone_block(zone, label: str) -> list[str]:
    """A zone's full defining and derived constants, with citations."""
    definition = zone.definition
    constants = constants_for(zone)
    return [
        f"{label}: {zone.name}, zone {zone.code} ({zone.system})",
        f"  Reference frame           {zone.frame.code}",
        f"  Projection                Lambert conformal conic, two standard parallels",
        f"  Southern standard parallel  {definition.lat_south:.10f} deg N",
        f"  Northern standard parallel  {definition.lat_north:.10f} deg N",
        f"  Latitude of grid origin     {definition.lat_grid_origin:.10f} deg N",
        f"  Central meridian            {definition.lon_origin:.10f} deg "
        f"({-definition.lon_origin:.10f} deg west)",
        f"  False northing              {definition.northing_grid_origin:,.4f} m",
        f"  False easting               {definition.easting_origin:,.4f} m",
        f"  Central parallel (derived)  {constants.lat_origin:.10f} deg N",
        f"  Scale at central parallel   {constants.k_origin:.12f}",
        f"  Source: {zone.citation}",
    ]


def build_report(result: JobResult) -> str:
    """Render the job record."""
    settings = result.settings
    if settings.input_path is None or settings.output_directory is None:
        # The record's INPUT block opens with "File" and its OUTPUT block opens
        # with "Folder". Neither line can be written from None, and neither may
        # be filled in with a plausible substitute: this record is what a sealed
        # survey is defended with, so a file name it never read or a folder it
        # never wrote to would be a falsehood in the one document that exists to
        # say what happened (docs/DESIGN.md section 1, amendment #26).
        # Name which one is actually missing. Saying "neither" when only one is
        # absent is a false diagnostic about the half-pathless state, which is
        # a state this program explicitly supports (closing review gate).
        missing = []
        if settings.input_path is None:
            missing.append("no input file")
        if settings.output_directory is None:
            missing.append("no output folder")
        raise ValueError(
            f"A job record names the input file it read and the folder it "
            f"wrote to, and this job states it had {' and '.join(missing)} "
            f"(input_path={settings.input_path!r}, "
            f"output_directory={settings.output_directory!r}). A job with no "
            f"file, such as a single typed point, is displayed rather than "
            f"recorded."
        )
    generated = datetime.now(timezone.utc).astimezone()

    lines: list[str] = []
    add = lines.append

    add(_RULE)
    add(f"  {APP_NAME.upper()}")
    add("  COORDINATE CONVERSION JOB RECORD")
    add(_RULE)
    add("")
    add(f"Generated          {generated.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    add(f"Software           {APP_NAME} version {__version__}")
    add("")

    # ---------------------------------------------------------------- input
    add(_THIN)
    add("INPUT")
    add(_THIN)
    add(f"File               {settings.input_path}")
    if result.input_sha256:
        add(f"SHA-256            {result.input_sha256}")
    else:
        # No digest means no bytes passed through this program: the rows were
        # handed to the job already parsed. Saying so is the only honest line
        # available, and it is a great deal more honest than the hash of
        # whatever happens to sit at the path above - which is what this line
        # used to print, certifying a file that was never converted
        # (WP-R3 fix 2). The file name is left in place because it is what the
        # caller stated; the sentence below says what it is worth.
        add("SHA-256            not available")
        add("                   These coordinates were supplied to this program")
        add("                   already parsed, so it never read the file named")
        add("                   above and nothing here certifies its contents.")
    add(f"Coordinate rows    {result.input_row_count}")
    if result.skipped_blank_lines:
        add(f"Blank lines        {result.skipped_blank_lines} (skipped)")
    lines.extend(_input_format_block(settings))
    add("")

    # --------------------------------------------------------------- output
    add(_THIN)
    add("OUTPUT")
    add(_THIN)
    add(f"Folder             {settings.output_directory}")
    add(f"Conversion         {settings.direction.value}")
    add(f"Units out          {settings.output_unit.name} ({settings.output_unit.code})")
    add(f"                   {settings.output_unit.citation}")
    if settings.direction is not Direction.ZONE_TO_ZONE:
        add(f"Longitude          {settings.longitude_convention.value}")
    if settings.direction is Direction.GEODETIC_TO_ZONE:
        # The one thing a geodetic input file cannot carry in its own columns.
        # A latitude and longitude mean nothing without the frame they are
        # expressed in, and reading NATRF2022 positions as NAD 83 is a one-to-
        # two metre error that looks entirely ordinary (docs/DESIGN.md section
        # 6). The core refuses a mismatch; this states what was assumed, so the
        # record answers the question rather than leaving a reader to guess.
        add(
            f"Reference frame    {settings.geodetic_frame.code} - "
            f"{settings.geodetic_frame.name}"
        )
        add("                   The latitudes and longitudes in the input file")
        add("                   were read as positions in this frame.")
    add("")
    add("Precision written:")
    add(f"  Coordinates and elevations  {settings.output_unit.decimals} decimal places")
    add("  Scale and combined factors  8 decimal places")
    add("  Convergence angles          degrees-minutes-seconds to 0.01 second")
    add("  Latitude and longitude      8 decimal places (about 1 mm)")
    add("")

    # ---------------------------------------------------------------- zones
    add(_THIN)
    add("COORDINATE SYSTEMS")
    add(_THIN)
    if settings.source_zone is not None:
        lines.extend(_zone_block(settings.source_zone, "FROM"))
        add("")
    if settings.target_zone is not None and settings.direction is not Direction.ZONE_TO_GEODETIC:
        lines.extend(_zone_block(settings.target_zone, "TO"))
        add("")

    if (
        settings.source_zone is not None
        and settings.target_zone is not None
        and settings.source_zone is not settings.target_zone
    ):
        add("Both zones are on the same reference frame, so this conversion is an")
        add("exact re-projection of the same physical positions: no datum shift is")
        add("applied and none is needed. Converting back returns the original")
        add("coordinates to well under a millimetre.")
        add("")

    # -------------------------------------------------------------- method
    add(_THIN)
    add("METHOD")
    add(_THIN)
    add("Authority          NOAA Manual NOS NGS 5, State Plane Coordinate System")
    add("                   of 1983 (Stem, January 1989; reprinted with minor")
    add("                   corrections March 1990)")
    add("")
    add("Equations          The rigorous Lambert conformal conic mapping")
    add("                   equations of section 3.1 - zone constants (3.12),")
    add("                   direct conversion (3.13), inverse conversion (3.14).")
    add("                   Exact at any latitude, with no approximation term.")
    add("")
    add("Ellipsoid          GRS 80, the ellipsoid of NAD 83 (manual section 1.7).")
    add("                   Only the semimajor axis and the flattening are stored;")
    add("                   every other constant is derived from those two.")
    add("")
    add("HOW THIS SOFTWARE IS VERIFIED")
    add("")
    add("The zone constants used above are not taken on trust. The manual")
    add("publishes, in Appendix C, the constants NGS computed for every Lambert")
    add("zone. This software stores only the DEFINING constants - the standard")
    add("parallels, the grid origin, the central meridian - and derives the rest.")
    add("Its test suite recomputes all of them and requires a match with NGS's")
    add("published figures to the last decimal place NGS printed, for all three")
    add("Michigan zones.")
    add("")
    add("The conversion itself is checked against the National Geodetic Survey's")
    add("own Coordinate Conversion and Transformation Tool (NCAT). Twenty-seven")
    add("positions spanning the three zones were converted by NCAT, and those")
    add("results are held in the test suite as fixed reference values. This")
    add("software reproduces them to within 0.5 mm - which is the precision NCAT")
    add("publishes, so the agreement is as close as the reference permits.")
    add("")
    add("Both checks compare this software against NGS. Neither compares it")
    add("against itself.")
    add("")

    if result.geoid_model:
        # Resolved through the registry so the tile name and digest printed
        # here are the record's own - a GEOID12B job must not be documented
        # with GEOID18's file and checksum (WP-V5). For a GEOID18 job every
        # character below is what this record printed before the registry.
        geoid_record = geoid_model_by_name(result.geoid_model)
        add(
            f"Geoid model        {geoid_record.name}, NGS grid tile "
            f"{geoid_record.tile_filename}"
        )
        add(f"                   SHA-256 {geoid_record.sha256}")
        add("                   Geoid heights are NEGATIVE throughout Michigan:")
        add("                   the ellipsoid lies above the geoid here.")
        add("")
        add("Elevation factor   R / (R + H + N), manual section 4.1")
        add(f"                   R = {MEAN_EARTH_RADIUS_M:,.0f} m mean earth radius")
        # "from the input file" was true until WP-V6: a vertical job shifts
        # the height between datums BEFORE the factors are computed, so the H
        # here is the height the factors actually used, which the audit CSV
        # carries per point.
        add("                   H = orthometric height as used for the factors")
        add("                   N = geoid height, interpolated from the grid above")
        add("Combined factor    grid scale factor x elevation factor")
        add("")
    else:
        add("Geoid model        not applied; no elevation or combined factors")
        add("                   were computed for this job.")
        add("")

    # ------------------------------------------------------------- summary
    add(_THIN)
    add("SCALE FACTOR SUMMARY")
    add(_THIN)
    add("Per-point values are in the _full.csv export. Summary across this job:")
    add("")
    lines.extend(_factor_summary(result))
    add("")

    # ------------------------------------------------------------ elevation
    missing = result.points_without_elevation
    add(_THIN)
    add("ELEVATIONS")
    add(_THIN)
    # Three causes, and this section must not flatten them into one. The first
    # two are genuinely absent elevations. The THIRD is a point whose Z column
    # was read perfectly well, and whose factors are absent only because the
    # shipped GEOID18 tile does not reach its position. Describing that point
    # as having a blank Z field is a false statement in an audit document, and
    # it is the statement this section used to make (WP-R2 fix C).
    #
    # ``Factors.orthometric_height`` is what separates them: it is the height
    # the job read, present whether or not a geoid height was found, so a
    # factor-less point that still carries one is a geoid miss - OR, on a job
    # that applied no geoid model at all, simply a point nothing was looked up
    # for. Those are different statements and the record must make the right
    # one: "the grid does not reach this point" is false when no grid was ever
    # consulted, and the old wording made exactly that claim on a
    # geoid-disabled job (found at WP-V5, when the model name became the
    # result's own and the sentence would otherwise have read "the None grid").
    no_geoid = [p for p in missing if p.factors.orthometric_height is not None]
    absent = [p for p in missing if p.factors.orthometric_height is None]
    # The FOURTH cause, WP-V6's: the Z field was read perfectly well, but the
    # vertical shift could not be computed (the point sits outside the VERTCON
    # grids), so no target-datum height exists and the elevation was REFUSED
    # rather than passed through unshifted. Calling that a "blank elevation
    # field" would be a false statement about a populated field in an audit
    # document - the exact defect WP-R2 fix C removed for the geoid, arriving
    # through a new door (WP-V6 review gate, HIGH 1). ``row.elevation`` is what
    # separates it: None for a genuinely blank or zeroed field, present here.
    unshifted = [p for p in absent if p.row.elevation is not None]
    absent = [p for p in absent if p.row.elevation is None]

    if not missing:
        add(f"All {len(result.points)} points carried a usable elevation.")
    else:
        if absent:
            add(
                f"{len(absent)} of {len(result.points)} points had NO usable "
                f"elevation."
            )
        if unshifted:
            add(
                f"{len(unshifted)} of {len(result.points)} points carried an "
                f"elevation that could NOT be converted between vertical "
                f"datums: the point lies outside the VERTCON grids. The Z "
                f"field was read; the elevation is deliberately not written, "
                f"because the height in hand is in the source vertical datum "
                f"and every elevation this job writes claims the target one."
            )
        if no_geoid and result.geoid_model:
            add(
                f"{len(no_geoid)} of {len(result.points)} points carried an "
                # A geoid miss with a model applied: result.geoid_model names
                # the grid that was actually consulted.
                f"elevation the {result.geoid_model} grid does not reach."
            )
        elif no_geoid:
            add(
                f"{len(no_geoid)} of {len(result.points)} points carried an "
                f"elevation, but no geoid model was applied to this job, so "
                f"no geoid height was looked up for any of them."
            )
        add("")
        add("For those points the elevation factor and combined factor are written")
        add(f"as {fmt.NOT_AVAILABLE!r} in the exports. They are NOT set to 1.0, and the grid")
        add("scale factor is not substituted for the combined factor: there is no")
        add("honest combined factor without an elevation, and a plausible-looking")
        add("number here would travel onto a drawing. The horizontal conversion is")
        add("unaffected - it does not depend on elevation at all.")
        add("")
        if absent:
            add("A Z field that is blank, or that holds exactly 0.00, is treated as")
            add("'not recorded'. Michigan's lowest natural point is Lake Erie at about")
            add("571 feet, so a genuine survey elevation of exactly zero does not")
            add("occur here. This is a stated convention of this program, not")
            add("something the source documents specify.")
            add("")
            blank = [p for p in absent if not p.row.elevation_was_zero]
            zeroed = [p for p in absent if p.row.elevation_was_zero]
            if blank:
                add(f"  Blank elevation field ({len(blank)}):")
                lines.extend(_point_id_block(blank))
            if zeroed:
                add(f"  Elevation field held exactly 0.00 ({len(zeroed)}):")
                lines.extend(_point_id_block(zeroed))
            if no_geoid and result.geoid_model:
                add("")
        if no_geoid and result.geoid_model:
            # Only when a model was applied: on a no-geoid-model job the count
            # line above already says why the factors are absent, and this
            # block's "position lies outside the grid tile" would be a false
            # statement about a lookup that never happened.
            add(
                f"  Elevation recorded, but no {result.geoid_model} geoid height at "
                f"this position ({len(no_geoid)}):"
            )
            lines.extend(_point_id_block(no_geoid))
            add("")
            add("  These Z fields were read and are written to the exports. They are")
            add("  NOT blank and they are NOT zero. What is missing is the geoid")
            add("  height, because the position lies outside the grid tile this")
            add("  program ships, and without it there is no elevation factor. The")
            add("  HORIZONTAL coordinate of each point is unaffected and stands: it")
            add("  does not depend on elevation at all. Each point is named again,")
            add("  with its position, under WARNINGS below.")
        if unshifted:
            add("")
            add(
                f"  Elevation recorded, but not convertible between vertical "
                f"datums ({len(unshifted)}):"
            )
            lines.extend(_point_id_block(unshifted))
            add("")
            add("  These Z fields were read. They are NOT blank and they are NOT")
            add("  zero. The position lies outside the VERTCON grids, so no shift")
            add("  to the target vertical datum exists, and the elevation is")
            add("  deliberately absent from the exports rather than written")
            add("  unconverted: an unconverted height in a column that claims the")
            add("  target datum would look ordinary and be wrong. The HORIZONTAL")
            add("  coordinate of each point is unaffected and stands. Each point is")
            add("  named again, with its position, under WARNINGS below.")
    add("")

    # ------------------------------------------------------------- warnings
    add(_THIN)
    add("WARNINGS")
    add(_THIN)
    all_warnings = result.warnings
    if not all_warnings:
        add("None. Every point converted cleanly, inside its zone.")
    else:
        add(f"{len(all_warnings)} warning(s) across {len(result.points)} points.")
        add("")
        add("A warning is not an error. Every point below was converted, and the")
        add("coordinate written for it is correct. A warning means something about")
        add("the job is worth a second look.")
        for code in _warning_codes_present(result):
            group = result.warnings_of(code)
            if not group:
                continue
            add("")
            add(f"  {_warning_heading(code)} ({len(group)} point(s))")
            add("")
            for point_id, warning in group[:20]:
                add(f"    {warning.message}")
            if len(group) > 20:
                add(f"    ... and {len(group) - 20} more; see the _full.csv export.")
    add("")

    # -------------------------------------------------------------- files
    add(_THIN)
    add("FILES WRITTEN")
    add(_THIN)
    from michspc.fileio.exports import member_names, output_stem

    stem = output_stem(result)
    names = member_names(result)

    add(f"This job wrote ONE file: {stem}.zip")
    add("")
    add("It contains the three files below, and they are kept together on")
    add("purpose. A coordinate file that has been moved between zones should not")
    add("circulate without the record explaining how it was derived, so the")
    add("export is a single archive rather than three loose files.")
    add("")
    add(f"  {names['pnezd']}")
    lines.extend(_clean_export_block(settings))
    add("")
    add(f"  {names['audit']}")
    add("    Every computed quantity for every point, with a header row: both")
    add("    zones' coordinates, the geodetic position the conversion pivoted")
    add("    through, geoid and ellipsoid height, both convergence angles, the")
    add("    grid, elevation and combined factors, and any warnings. This is the")
    add("    file that answers 'how was this number derived' without re-running")
    add("    anything.")
    add("")
    add(f"  {names['report']}")
    add("    This file.")
    add("")
    add(_RULE)
    add("  END OF JOB RECORD")
    add(_RULE)

    return "\n".join(lines) + "\n"


def _point_id_block(points, per_line: int = 8) -> list[str]:
    """Point identifiers wrapped to a readable width."""
    ids = [p.point_id for p in points]
    lines = []
    for start in range(0, len(ids), per_line):
        lines.append("    " + ", ".join(ids[start : start + per_line]))
    return lines


def _factor_summary(result: JobResult) -> list[str]:
    """Minimum, maximum and mean of each factor, in value and parts per million."""
    lines = []

    def block(label: str, values) -> None:
        if not values:
            lines.append(f"  {label:<26} {fmt.NOT_AVAILABLE}")
            return
        low, high = min(values), max(values)
        mean = statistics.fmean(values)
        lines.append(f"  {label}")
        lines.append(
            f"    minimum  {fmt.factor(low):<14} "
            f"({fmt.signed_parts_per_million(low)} ppm)"
        )
        lines.append(
            f"    maximum  {fmt.factor(high):<14} "
            f"({fmt.signed_parts_per_million(high)} ppm)"
        )
        lines.append(
            f"    mean     {fmt.factor(mean):<14} "
            f"({fmt.signed_parts_per_million(mean)} ppm)"
        )

    block("Grid scale factor", result.grid_scale_factors)
    lines.append("")
    combined = result.combined_factors
    block("Combined factor", combined)
    if combined:
        lines.append("")
        lines.append(
            "  Multiply a ground distance by the combined factor to get the grid"
        )
        lines.append(
            "  distance; divide a grid distance by it to get ground. Divide a grid"
        )
        lines.append("  area by its square to get ground area (manual section 4.1).")
    else:
        lines.append("")
        lines.append(
            "  No combined factors were computed: no point carried a usable elevation."
        )
    return lines
