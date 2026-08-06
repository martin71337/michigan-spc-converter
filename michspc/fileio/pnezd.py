"""PNEZD coordinate file reader.

The format: one point per line, no header row,

    point, northing, easting, elevation, description

as exported by essentially every data collector and CAD package. It is not a
specified format, so this reader states its conventions explicitly and refuses
anything it cannot read rather than guessing.

**Conventions, all deliberate:**

* **The description is everything after the fourth comma.** Descriptions
  routinely contain commas ("IRON PIPE, BENT"), and a strict five-field split
  would either lose the remainder or reject the row. Quoted fields are also
  honoured, so a properly quoted export reads correctly too.
* **Point identifiers are text, not numbers.** "101", "CP-4" and "TBM1" are all
  valid, and a numeric identifier keeps its leading zeros.
* **A blank or exactly-zero elevation means "not recorded".** See below.
* **Blank lines are skipped**; anything else that cannot be parsed is refused
  by line number and content.

**On zero elevations.** Data collectors write 0.00 into the Z column for points
that were never levelled. Treating that as a real elevation would compute an
elevation factor at sea level and carry it onto a drawing looking entirely
ordinary. Michigan's lowest natural point is Lake Erie at about 571 feet, so a
genuine survey elevation of exactly zero does not occur here; treating it as
absent is safe as well as usually right. This is a **disclosed convention**, not
something the sources specify: every point affected is named in the job record
so the surveyor sees exactly what was assumed (docs/DESIGN.md section 7).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

# Descriptions this reader treats as "no elevation recorded", in addition to a
# blank field.
_ABSENT_ELEVATION_TEXT = frozenset({"", "-", "n/a", "na", "null", "none"})


class PnezdError(Exception):
    """A coordinate file could not be read.

    Always names the file, the line number and the offending text, because a
    refusal that does not say which row is wrong is not much use against a file
    of several thousand points.
    """


@dataclass(frozen=True)
class PnezdRow:
    """One point as it appeared in the file. Values are in the FILE's units."""

    line_number: int
    point_id: str
    northing: float
    easting: float
    elevation: float | None
    """None when the field was blank or exactly zero - see the module docstring."""

    description: str
    elevation_was_zero: bool
    """True when the field held an explicit zero rather than being blank.

    Kept distinct so the job record can say which of the two it saw, rather
    than flattening both into "missing".
    """

    @property
    def has_elevation(self) -> bool:
        return self.elevation is not None


@dataclass(frozen=True)
class PnezdFile:
    """A parsed coordinate file."""

    path: Path
    rows: tuple[PnezdRow, ...]
    skipped_blank_lines: int

    @property
    def points_without_elevation(self) -> tuple[PnezdRow, ...]:
        return tuple(row for row in self.rows if not row.has_elevation)


def _parse_number(text: str, field: str, line_number: int, line: str, path) -> float:
    cleaned = text.strip().replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        raise PnezdError(
            f"{path}, line {line_number}: the {field} field reads {text.strip()!r}, "
            f"which is not a number.\n  {line.strip()!r}\n"
            f"Expected: point, northing, easting, elevation, description - with "
            f"no header row."
        ) from None


def _parse_elevation(
    text: str, line_number: int, line: str, path
) -> tuple[float | None, bool]:
    """Returns (elevation, was_explicit_zero)."""
    cleaned = text.strip()
    if cleaned.lower() in _ABSENT_ELEVATION_TEXT:
        return None, False

    value = _parse_number(cleaned, "elevation", line_number, line, path)
    if value == 0.0:
        return None, True
    return value, False


def parse_lines(lines, path="<text>") -> PnezdFile:
    """Parse PNEZD content from an iterable of lines.

    Separated from file reading so the parser can be tested exhaustively
    without touching the filesystem.
    """
    rows: list[PnezdRow] = []
    blank = 0

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            blank += 1
            continue

        # csv handles quoted fields containing commas; anything past the fifth
        # field is description text that contained unquoted commas, and is
        # rejoined below.
        fields = next(csv.reader(io.StringIO(line)))

        if len(fields) < 4:
            raise PnezdError(
                f"{path}, line {line_number}: found {len(fields)} field(s), "
                f"need at least 4.\n  {line.strip()!r}\n"
                f"Expected: point, northing, easting, elevation, description - "
                f"with no header row. If this file has a header, remove it."
            )

        point_id = fields[0].strip()
        if not point_id:
            raise PnezdError(
                f"{path}, line {line_number}: the point identifier is blank.\n"
                f"  {line.strip()!r}\n"
                f"Every point must be identifiable, or the converted file "
                f"cannot be matched back to this one."
            )

        northing = _parse_number(fields[1], "northing", line_number, line, path)
        easting = _parse_number(fields[2], "easting", line_number, line, path)
        elevation, was_zero = _parse_elevation(fields[3], line_number, line, path)
        description = ",".join(fields[4:]).strip() if len(fields) > 4 else ""

        rows.append(
            PnezdRow(
                line_number=line_number,
                point_id=point_id,
                northing=northing,
                easting=easting,
                elevation=elevation,
                description=description,
                elevation_was_zero=was_zero,
            )
        )

    if not rows:
        raise PnezdError(
            f"{path} contains no coordinate rows. An empty file is refused "
            f"rather than producing an empty export that would look like a "
            f"successful conversion."
        )

    return PnezdFile(path=Path(path), rows=tuple(rows), skipped_blank_lines=blank)


def read(path: Path) -> PnezdFile:
    """Read and parse a PNEZD file.

    Decoded as utf-8-sig so a byte order mark written by Excel or PowerShell is
    consumed rather than becoming part of the first point's identifier - which
    would otherwise turn point "101" into "\\ufeff101" and match nothing.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        # Legacy exports are often ANSI. Fall back rather than refusing a file
        # that is perfectly readable, and stay strict about the contents.
        try:
            text = path.read_text(encoding="cp1252")
        except OSError as error:
            raise PnezdError(f"Could not read {path}: {error}") from error
    except OSError as error:
        raise PnezdError(f"Could not read {path}: {error}") from error

    parsed = parse_lines(text.splitlines(), path=str(path))
    return PnezdFile(
        path=path,
        rows=parsed.rows,
        skipped_blank_lines=parsed.skipped_blank_lines,
    )
