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

_PNEZD_HEADERLESS = True
"""The clean export has no header row, matching the input format exactly.

A header would make the output un-round-trippable through this program's own
reader, which is the property `verify_round_trip` below exists to guarantee.
"""


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


def audit_columns(result: JobResult) -> list[str]:
    """The audit CSV's header row for this job's direction.

    Identical to ``AUDIT_COLUMNS`` except where one end of the job is geodetic,
    in which case that end's pair of columns is renamed to say what it actually
    holds. The other end's headings never move.
    """
    columns = list(AUDIT_COLUMNS)
    direction = result.settings.direction
    if direction is Direction.GEODETIC_TO_ZONE:
        columns[2], columns[3] = SOURCE_COLUMNS_GEODETIC
    elif direction is Direction.ZONE_TO_GEODETIC:
        columns[5], columns[6] = TARGET_COLUMNS_GEODETIC
    return columns


def audit_rows(result: JobResult) -> list[list[str]]:
    """Every computed quantity for every point, with a header row.

    This is the file that answers "how was this coordinate derived" without
    anyone having to re-run the program.
    """
    settings = result.settings
    out_unit = settings.output_unit
    in_unit = settings.input_unit
    geodetic_source = settings.direction is Direction.GEODETIC_TO_ZONE

    rows: list[list[str]] = [audit_columns(result)]

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

        rows.append(
            [
                point.point_id,
                settings.source_zone.name if settings.source_zone else "",
                source_northing,
                source_easting,
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


def _expected_coordinates(result: JobResult, point) -> tuple[str, float, str, float]:
    """What the export's columns two and three must carry for this point.

    Returns ``(name, value, name, value)`` - the label the round-trip refusal
    uses for each column, and the number the job computed for it. Reads the
    same branch ``clean_pnezd_rows`` writes, so the two cannot describe
    different columns.
    """
    if result.settings.direction is Direction.ZONE_TO_GEODETIC:
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


def _rounding_tolerance(decimals: int) -> float:
    """How far a re-read value may sit from the value the job computed.

    ``f"{v:.Nf}"`` moves a value by at most half of the last place it keeps, so
    that is the whole budget: 0.0005 ft at 3 places, 0.00005 m at 4, and
    0.000000005 deg - about half a millimetre - at 8. The 1e-12 is IEEE slack
    on the power itself, not a licence to disagree.

    Anything larger than this is not rounding. It is a different number.
    """
    return 0.5 * 10.0**-decimals + 1e-12


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
    characters in the cell. The numeric comparison carries the tolerance the
    formatter's own rounding earns and nothing more (``_rounding_tolerance``).
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

    geodetic = result.settings.direction is Direction.ZONE_TO_GEODETIC
    horizontal_tolerance = _rounding_tolerance(_written_decimals(result, geodetic))
    elevation_tolerance = _rounding_tolerance(_written_decimals(result, False))

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
            if abs(actual - expected) > horizontal_tolerance:
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
        if (
            point.output_elevation is not None
            and abs(parsed_row.elevation - point.output_elevation)
            > elevation_tolerance
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
