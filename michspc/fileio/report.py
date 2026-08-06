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
from michspc.fileio.geoid18 import GEOID18_TILE_SHA256, GEOID_MODEL_NAME
from michspc.job import Direction, JobResult
from michspc.spc.agreement import AGREEMENT_TOLERANCE_M
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
    WarningCode.ENGINE_DISAGREEMENT_OUT_OF_BAND: (
        "CROSS-CHECK LIMITED OUTSIDE THE POLYNOMIAL BAND"
    ),
}


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
    add(f"SHA-256            {result.input_sha256 or 'not available'}")
    add(f"Coordinate rows    {result.input_row_count}")
    if result.skipped_blank_lines:
        add(f"Blank lines        {result.skipped_blank_lines} (skipped)")
    add(f"Format             PNEZD, no header row")
    add(f"                   point, northing, easting, elevation, description")
    add(f"                   description is everything after the fourth comma")
    add(f"Units in           {settings.input_unit.name} ({settings.input_unit.code})")
    add(f"                   {settings.input_unit.citation}")
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
    add("Every coordinate below was computed TWICE, by two independent methods")
    add("from that manual, and the two results compared:")
    add("")
    add("  1. The rigorous Lambert conformal conic mapping equations, section 3.1.")
    add("     Used for every value reported. Exact at any latitude.")
    add("  2. The polynomial coefficient method, section 3.4, with the Appendix C")
    add("     coefficients for each zone. Used only as an independent check.")
    add("")
    add(f"The two must agree to {AGREEMENT_TOLERANCE_M * 1000:.1f} mm, which is the accuracy NGS states it")
    add("fitted the Appendix C coefficients to. Where they do not agree and the")
    add("point lies inside the zone's fitted latitude band, no coordinate is")
    add("produced at all. Where the point lies outside that band the polynomial")
    add("method is known to degrade and the rigorous result is used, with the")
    add("discrepancy reported per point in the _full.csv export.")
    add("")
    add(f"Worst engine discrepancy across this job: "
        f"{fmt.millimetres(result.worst_engine_discrepancy)} mm")
    add("")

    if result.geoid_model:
        add(f"Geoid model        {GEOID_MODEL_NAME}, NGS grid tile g2018u3.bin")
        add(f"                   SHA-256 {GEOID18_TILE_SHA256}")
        add("                   Geoid heights are NEGATIVE throughout Michigan:")
        add("                   the ellipsoid lies above the geoid here.")
        add("")
        add("Elevation factor   R / (R + H + N), manual section 4.1")
        add(f"                   R = {MEAN_EARTH_RADIUS_M:,.0f} m mean earth radius")
        add("                   H = orthometric height from the input file")
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
    if not missing:
        add(f"All {len(result.points)} points carried a usable elevation.")
    else:
        add(f"{len(missing)} of {len(result.points)} points had NO usable elevation.")
        add("")
        add("For those points the elevation factor and combined factor are written")
        add(f"as {fmt.NOT_AVAILABLE!r} in the exports. They are NOT set to 1.0, and the grid")
        add("scale factor is not substituted for the combined factor: there is no")
        add("honest combined factor without an elevation, and a plausible-looking")
        add("number here would travel onto a drawing. The horizontal conversion is")
        add("unaffected - it does not depend on elevation at all.")
        add("")
        add("A Z field that is blank, or that holds exactly 0.00, is treated as")
        add("'not recorded'. Michigan's lowest natural point is Lake Erie at about")
        add("571 feet, so a genuine survey elevation of exactly zero does not")
        add("occur here. This is a stated convention of this program, not")
        add("something the source documents specify.")
        add("")
        blank = [p for p in missing if not p.row.elevation_was_zero]
        zeroed = [p for p in missing if p.row.elevation_was_zero]
        if blank:
            add(f"  Blank elevation field ({len(blank)}):")
            lines.extend(_point_id_block(blank))
        if zeroed:
            add(f"  Elevation field held exactly 0.00 ({len(zeroed)}):")
            lines.extend(_point_id_block(zeroed))
    add("")

    # ------------------------------------------------------------- warnings
    add(_THIN)
    add("WARNINGS")
    add(_THIN)
    all_warnings = result.warnings
    if not all_warnings:
        add("None. Every point converted cleanly, inside its zone, with both")
        add("computation methods in agreement.")
    else:
        add(f"{len(all_warnings)} warning(s) across {len(result.points)} points.")
        add("")
        add("A warning is not an error. Every point below was converted, and the")
        add("coordinate written for it is correct. A warning means something about")
        add("the job is worth a second look.")
        for code, heading in _WARNING_HEADINGS.items():
            group = result.warnings_of(code)
            if not group:
                continue
            add("")
            add(f"  {heading} ({len(group)} point(s))")
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
    from michspc.fileio.exports import output_stem

    stem = output_stem(result)
    add(f"{stem}.csv")
    add("    The converted coordinates, in the same PNEZD layout as the input:")
    add("    point, northing, easting, elevation, description - no header row.")
    add("    Nothing else. Import this one into CAD.")
    add("")
    add(f"{stem}_full.csv")
    add("    Every computed quantity for every point, with a header row: both")
    add("    zones' coordinates, the geodetic position the conversion pivoted")
    add("    through, geoid and ellipsoid height, both convergence angles, the")
    add("    grid, elevation and combined factors, the agreement between the two")
    add("    computation methods in millimetres, and any warnings. This is the")
    add("    file that answers 'how was this number derived' without re-running")
    add("    anything.")
    add("")
    add(f"{stem}_README.txt")
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
