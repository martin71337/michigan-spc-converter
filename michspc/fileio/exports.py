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

from pathlib import Path

from michspc.fileio import formatting as fmt
from michspc.fileio.writers import WriteError, staged_write
from michspc.job import Direction, JobResult

_PNEZD_HEADERLESS = True
"""The clean export has no header row, matching the input format exactly.

A header would make the output un-round-trippable through this program's own
reader, which is the property `verify_round_trip` below exists to guarantee.
"""


def output_stem(result: JobResult) -> str:
    """``<input stem>_<zone abbreviation>``, e.g. ``24-118-topo_MI-C``."""
    settings = result.settings
    if settings.direction is Direction.ZONE_TO_GEODETIC:
        suffix = "GEODETIC"
    else:
        suffix = settings.target_zone.abbrev
    return f"{settings.input_path.stem}_{suffix}"


def clean_pnezd_rows(result: JobResult) -> list[list[str]]:
    """The CAD-bound export: point, northing, easting, elevation, description."""
    settings = result.settings
    rows: list[list[str]] = []

    for point in result.points:
        if settings.direction is Direction.ZONE_TO_GEODETIC:
            northing = fmt.latitude(point.output_northing)
            easting = fmt.longitude(point.output_easting)
            elevation = fmt.coordinate(point.output_elevation, settings.input_unit)
        else:
            northing = fmt.coordinate(point.output_northing, settings.output_unit)
            easting = fmt.coordinate(point.output_easting, settings.output_unit)
            elevation = fmt.coordinate(point.output_elevation, settings.output_unit)

        rows.append(
            [point.point_id, northing, easting, elevation, point.row.description]
        )

    return rows


AUDIT_COLUMNS = [
    "Point",
    "Source zone",
    "Source northing",
    "Source easting",
    "Target zone",
    "Target northing",
    "Target easting",
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


def audit_rows(result: JobResult) -> list[list[str]]:
    """Every computed quantity for every point, with a header row.

    This is the file that answers "how was this coordinate derived" without
    anyone having to re-run the program.
    """
    settings = result.settings
    out_unit = settings.output_unit
    in_unit = settings.input_unit

    rows: list[list[str]] = [list(AUDIT_COLUMNS)]

    for point in result.points:
        conversion = point.conversion
        factors = point.factors

        rows.append(
            [
                point.point_id,
                settings.source_zone.name if settings.source_zone else "",
                fmt.coordinate(point.row.northing, in_unit),
                fmt.coordinate(point.row.easting, in_unit),
                settings.target_zone.name if settings.target_zone else "geodetic",
                fmt.coordinate(point.output_northing, out_unit)
                if settings.direction is not Direction.ZONE_TO_GEODETIC
                else fmt.latitude(point.output_northing),
                fmt.coordinate(point.output_easting, out_unit)
                if settings.direction is not Direction.ZONE_TO_GEODETIC
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

    return rows


def verify_round_trip(rows: list[list[str]], result: JobResult) -> None:
    """Refuse to write a PNEZD file this program's own reader would reject.

    METHOD.md section 5: "a writer that refuses to produce a file its own
    reader would reject". The rows are rendered, re-parsed, and checked point
    for point before anything reaches its final name.

    This has real teeth: a description containing a comma, an identifier
    containing a quote, or a value formatted as "nan" would all produce a file
    that looks written and imports wrongly.
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

    for parsed_row, point in zip(reparsed.rows, result.points):
        if parsed_row.point_id != point.point_id:
            raise WriteError(
                f"Round-trip check failed: the export's row reads point "
                f"{parsed_row.point_id!r} where the job converted "
                f"{point.point_id!r}. Nothing was written."
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


def write_all(result: JobResult, overwrite: bool = False) -> dict[str, Path]:
    """Write the job's single ZIP deliverable, or nothing at all.

    The three files travel together or not at all (docs/DESIGN.md amendment
    #17), so a PNEZD export can never be filed or emailed without the record
    explaining how it was derived.

    Order matters here. Every coordinate is checked finite and the PNEZD export
    is round-tripped through this program's own reader BEFORE the archive is
    staged, and the archive is only renamed onto its final name once it has been
    written in full. A job therefore either produces a complete, readable
    deliverable or leaves the output folder exactly as it found it.

    Returns a mapping of role to path. Both entries point at the same archive;
    the roles are kept so callers can say which member they mean.
    """
    import zipfile

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

    return {"archive": destination, **{role: destination for role in names}}
