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
* **No numeric field may be NaN or infinite.** "nan", "inf" and "-inf" are all
  legal arguments to Python's ``float()``, so without an explicit check they
  parse silently and travel the whole length of the program - through the
  screen, through the audit CSV, and into a coordinate file where "nan" imports
  into CAD as zero or as a parse error depending on the package. Refused here,
  at the one entry point, rather than at the writer: by the time a writer sees
  it the value has already been shown to the surveyor as though it were real.
* **A number written with unquoted thousands separators is refused, not
  guessed.** See ``_grouping_signature`` below.
* **No two rows may share a point identifier.** Both would convert and both
  would be written out under the same name, after which the job record names a
  point that could be either and a CAD import overwrites or fails. Refused,
  naming the identifier and both line numbers.
* **Malformed double quoting is refused, not repaired.** ``csv``'s default
  leniency turns ``"UNTERMINATED`` into ``UNTERMINATED`` and ``"A"junk`` into
  ``Ajunk``, so the parsed text stops representing the file with nothing said.
  The reader is strict and converts ``csv.Error`` into a refusal naming the
  line.
* **A byte order mark never becomes part of a point identifier.** It is
  stripped on every path into the parser, not only on the one that decodes
  utf-8-sig.

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
import hashlib
import io
import math
import re
from dataclasses import dataclass
from pathlib import Path

# Descriptions this reader treats as "no elevation recorded", in addition to a
# blank field.
_ABSENT_ELEVATION_TEXT = frozenset({"", "-", "n/a", "na", "null", "none"})

# A number written with thousands separators, in full: a leading group of one
# to three digits, then one or more groups of exactly three, then an optional
# decimal part. Only ever matched against a QUOTED field, where the separators
# survived csv splitting and the reading is unambiguous.
_GROUPED_NUMBER = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$")

# The two halves of that same pattern as they appear once csv has split an
# UNQUOTED grouped number into separate fields.
_LEADING_GROUP = re.compile(r"^[+-]?\d{1,3}$")
_FOLLOWING_GROUP = re.compile(r"^\d{3}(?:\.\d+)?$")

# U+FEFF, the byte order mark, written as an escape rather than as the character
# itself: docs/DESIGN.md amendment #7 records what an invisible mark in a source
# file costs, and a literal one here would be exactly that.
_BYTE_ORDER_MARK = "\ufeff"

# A bare number, used only to test whether the description begins with one.
# Deliberately does not admit "nan" or "inf": those are refused as coordinates,
# and a description that literally reads "nan" is text, not a shifted number.
_NUMERIC_TOKEN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


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

    sha256: str | None = None
    """SHA-256 of the bytes these rows were parsed from, or None.

    Carried by the reader rather than recomputed later, because a digest taken
    from the path afterwards certifies whatever is at that path *then* - not
    what was converted. The reader reads the file once and hashes exactly the
    bytes it decoded, so the two cannot be different bytes (WP-R3 fix 2).

    ``None`` is a statement, not an absence: "these rows did not come from bytes
    this program read". ``parse_lines`` is handed already-decoded text and so
    says None, and every surface that reports the digest must say so plainly
    rather than substituting a hash of something else.
    """

    @property
    def points_without_elevation(self) -> tuple[PnezdRow, ...]:
        return tuple(row for row in self.rows if not row.has_elevation)


def _parse_number(text: str, field: str, line_number: int, line: str, path) -> float:
    cleaned = text.strip()

    if "," in cleaned:
        # Only reachable for a QUOTED field. csv.reader has already consumed
        # every unquoted comma as a field delimiter, so a comma surviving to
        # here means the writer quoted the number - '"13,221,442.048"' - which
        # is an unambiguous reading and worth honouring.
        #
        # The separators are removed only after the text is confirmed to be
        # genuine three-digit grouping. Stripping unconditionally would turn a
        # quoted '"1,2"' into 12 without a word, which is exactly the class of
        # silent wrong number this program exists to prevent.
        if not _GROUPED_NUMBER.match(cleaned):
            raise PnezdError(
                f"{path}, line {line_number}: the {field} field reads "
                f"{cleaned!r}, which contains commas but is not a number "
                f"written with thousands separators.\n  {line.strip()!r}\n"
                f"A grouped number reads like 13,221,442.048 - one to three "
                f"digits, then groups of exactly three. Remove the commas, or "
                f"correct the grouping."
            )
        cleaned = cleaned.replace(",", "")

    try:
        value = float(cleaned)
    except ValueError:
        raise PnezdError(
            f"{path}, line {line_number}: the {field} field reads {text.strip()!r}, "
            f"which is not a number.\n  {line.strip()!r}\n"
            f"Expected: point, northing, easting, elevation, description - with "
            f"no header row."
        ) from None

    # float() accepts "nan", "inf", "-inf" and "infinity" as legal literals.
    # None of them is a position or a height, and every one of them survives
    # every downstream check that tests a value rather than its finiteness:
    # NaN is not equal to 0.0, so the absent-elevation branch misses it, and
    # re-parsing the written text succeeds, so the export's round-trip check
    # misses it too. It is refused here, where the file is first read.
    if not math.isfinite(value):
        raise PnezdError(
            f"{path}, line {line_number}: the {field} field reads "
            f"{text.strip()!r}, which is not a usable number.\n"
            f"  {line.strip()!r}\n"
            f"'nan' (not a number) and 'inf' (infinity) are refused wherever a "
            f"coordinate, an elevation or a height is expected. They normally "
            f"mean an earlier program failed to compute this point. Correct the "
            f"value in the source file, or delete the row if the point was "
            f"never observed - leave the elevation field BLANK rather than "
            f"filling it with a placeholder."
        )

    return value


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


def _grouping_signature(fields: list[str]) -> int | None:
    """Index ``i`` where ``fields[i]`` and ``fields[i+1]`` read as one number.

    ``780,000.000`` written into a CSV without quotes is not one field. csv
    splits it at the comma, so the row arrives here as ``["780", "000.000"]``
    and the reader takes 780 as the northing - a coordinate 779,220 feet from
    the one the surveyor wrote, produced without a murmur.

    This locates the textual fingerprint of that split: a field of one to three
    digits followed by a field of exactly three digits (with an optional
    decimal part), which is precisely the shape thousands grouping produces and
    is not the shape of anything else.

    The scan starts at index 1. Field 0 is the point identifier, which is text
    by design - "101" is an identifier, never the leading group of a number.
    """
    for index in range(1, len(fields) - 1):
        if _LEADING_GROUP.match(fields[index].strip()) and _FOLLOWING_GROUP.match(
            fields[index + 1].strip()
        ):
            return index
    return None


def _refuse_ambiguous_grouping(
    fields: list[str], description: str, line_number: int, line: str, path
) -> None:
    """Refuse a row that reads correctly two different ways.

    The signature alone is not enough to refuse on. ``A,1,2,100.0,x`` carries
    it - "2" then "100.0" - but there is no second valid reading: joining them
    leaves ``A,1,2100.0,x``, four fields whose elevation is "x", which is not a
    number. Only one reading is well formed, so the row is not ambiguous and is
    read literally.

    What makes a row genuinely ambiguous is a structural consequence of the
    stray comma: every unquoted separator adds a field, which pushes one more
    numeric token past the elevation column and into the description. So the
    test is the signature AND a description that begins with a bare number.
    Both counterexamples behave that way -

        101,780,000.000,13,123,359.580,800.00,IRON PIPE
            -> literally: N 780, E 0, Z 13, description "123,359.580,800.00,..."
            -> grouped:   N 780000.000, E 13123359.580, Z 800.00, "IRON PIPE"

    - and both readings are well formed PNEZD. Nothing in the file says which
    the surveyor meant, so this program does not choose. It refuses and says
    how to make the file say it (docs/DESIGN.md section 1: fail closed, never
    fabricate).
    """
    index = _grouping_signature(fields)
    if index is None:
        return

    first_token = description.split(",", 1)[0].strip()
    if not _NUMERIC_TOKEN.match(first_token):
        return

    grouped = f"{fields[index].strip()},{fields[index + 1].strip()}"
    raise PnezdError(
        f"{path}, line {line_number}: this row can be read two different ways, "
        f"so it is refused rather than guessed.\n"
        f"  {line.strip()!r}\n"
        f"Read literally it is {len(fields)} comma-separated fields, giving "
        f"northing {fields[1].strip()!r}, easting {fields[2].strip()!r} and "
        f"elevation {fields[3].strip()!r} - with a description that starts "
        f"with the number {first_token!r}, which is the giveaway.\n"
        f"But {grouped!r} also reads as a single number written with thousands "
        f"separators. Both readings are well formed and they give completely "
        f"different coordinates.\n"
        f"Correct the file either way: remove the thousands separators "
        f"(write 780000.000, not 780,000.000), or put double quotes around "
        f"each number that contains them (\"780,000.000\"). Both are then read "
        f"exactly as written."
    )


def parse_lines(lines, path="<text>") -> PnezdFile:
    """Parse PNEZD content from an iterable of lines.

    Separated from file reading so the parser can be tested exhaustively
    without touching the filesystem.
    """
    rows: list[PnezdRow] = []
    blank = 0
    first_seen: dict[str, int] = {}

    for line_number, line in enumerate(lines, start=1):
        if line_number == 1:
            # A byte order mark belongs to the file, not to the first point.
            # ``read`` decodes utf-8-sig and so never delivers one - but its
            # cp1252 fallback does, and so does any caller handing this
            # function text it decoded itself, and the mark then rides into
            # point_id, so point "101" arrives with an invisible mark glued to its front
            # and matches nothing
            # on the way back (WP-R2 fix G). Stripped here, at the one entry
            # point every route funnels through, rather than on one of them.
            line = line.lstrip(_BYTE_ORDER_MARK)

        if not line.strip():
            blank += 1
            continue

        # csv handles quoted fields containing commas; anything past the fifth
        # field is description text that contained unquoted commas, and is
        # rejoined below.
        #
        # strict=True is load-bearing, not tidiness. csv's default leniency
        # REPAIRS malformed quoting instead of reporting it: an unterminated
        # '"UNTERMINATED' becomes UNTERMINATED, and '"A"junk' becomes Ajunk.
        # The parsed text then no longer represents the file, with no refusal
        # anywhere - which for a description field is a survey note silently
        # rewritten (WP-R2 fix E). csv.Error is converted to this module's own
        # refusal so it names the line and says what is wrong, like every other
        # refusal here.
        try:
            fields = next(csv.reader(io.StringIO(line), strict=True))
        except csv.Error as error:
            raise PnezdError(
                f"{path}, line {line_number}: the double quotes on this row are "
                f"malformed, so it is refused rather than repaired.\n"
                f"  {line.strip()!r}\n"
                f"The CSV reader reported: {error}.\n"
                f"A quoted field must open and close with a double quote and "
                f"must be followed by a comma or the end of the line - "
                f'101,1,2,3,"IRON PIPE, BENT". A double quote INSIDE a quoted '
                f'field is written twice - "6"" PIPE". Repairing this row '
                f"instead would change the text the file actually holds."
            ) from error

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

        # Two rows claiming the same identifier is refused, not resolved. Both
        # would parse, both would be converted, and both would be written into
        # the export as point 101 - after which the job record names points by
        # an identifier that no longer picks out one of them, and a CAD import
        # either overwrites the first with the second or stops. Neither outcome
        # can be corrected from the export, because the export no longer says
        # which row was which.
        #
        # The owner's decision, and DESIGN.md section 7's rule that loaders
        # validate as strictly as the UI. Compared exactly, after stripping
        # surrounding whitespace: "101" and "101 " are the same point written
        # untidily, but "CP4" and "cp4" are two identifiers this program has no
        # authority to declare the same, and folding case would refuse a file
        # that is legitimate (WP-R2 fix D).
        if point_id in first_seen:
            raise PnezdError(
                f"{path}, line {line_number}: the point identifier "
                f"{point_id!r} is already used on line {first_seen[point_id]}, "
                f"so this file is refused rather than converted.\n"
                f"  {line.strip()!r}\n"
                f"Two rows sharing one identifier both convert and both are "
                f"written out as point {point_id!r}. The job record then names "
                f"a point that could be either of them, and importing the "
                f"result into CAD either overwrites the first with the second "
                f"or fails outright - and nothing in the export says which row "
                f"was which. Give the duplicate a distinct identifier, or "
                f"delete whichever row is the stale one, and convert again."
            )
        first_seen[point_id] = line_number

        description = ",".join(fields[4:]).strip() if len(fields) > 4 else ""

        # Before any field is read as a number, because the literal reading of
        # an ambiguous row parses perfectly well - that is the whole problem.
        _refuse_ambiguous_grouping(fields, description, line_number, line, path)

        northing = _parse_number(fields[1], "northing", line_number, line, path)
        easting = _parse_number(fields[2], "easting", line_number, line, path)
        elevation, was_zero = _parse_elevation(fields[3], line_number, line, path)

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

    **The bytes are read once and hashed here**, and the digest travels with the
    parsed rows. A job record's SHA-256 line exists to say what was converted;
    hashing the path again afterwards would certify whatever is at that path at
    that later moment, which is a different file if anything touched it in
    between - and no file at all if the caller supplied the rows itself
    (WP-R3 fix 2). One read, one decode, one digest.
    """
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as error:
        raise PnezdError(f"Could not read {path}: {error}") from error

    digest = hashlib.sha256(data).hexdigest()

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Legacy exports are often ANSI. Fall back rather than refusing a file
        # that is perfectly readable, and stay strict about the contents.
        #
        # The fallback can fail too: cp1252 leaves 0x81, 0x8D, 0x8F, 0x90 and
        # 0x9D undefined, so a file that is neither UTF-8 nor cp1252 raises a
        # second UnicodeDecodeError here. That must become a PnezdError like
        # every other refusal - a raw UnicodeDecodeError reaching the GUI shows
        # the surveyor a Python traceback instead of a sentence naming the file
        # and saying what to do about it.
        try:
            text = data.decode("cp1252")
        except UnicodeDecodeError as error:
            raise PnezdError(
                f"Could not read {path}: it is not a plain text file this "
                f"program can decode. Byte 0x{error.object[error.start]:02X} at "
                f"position {error.start} is not valid UTF-8 and has no meaning "
                f"in Windows ANSI (cp1252) either.\n"
                f"This usually means the file is a spreadsheet, a PDF or a "
                f"compressed archive rather than a coordinate file. Export it "
                f"again from the source program as CSV or plain text."
            ) from error

    parsed = parse_lines(text.splitlines(), path=str(path))
    return PnezdFile(
        path=path,
        rows=parsed.rows,
        skipped_blank_lines=parsed.skipped_blank_lines,
        sha256=digest,
    )
