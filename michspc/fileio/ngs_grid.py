"""The substrate shared by every NGS binary grid this program reads.

NGS publishes several gridded models in one family of little-endian binary
formats: the GEOID18 geoid separation tiles read by ``geoid18.py``, and the
VERTCON 3.0 vertical transformation and uncertainty grids. They share more than
a resemblance - the header is the **identical** ``<4d3i`` record, IKIND
included, the longitude convention is the identical 0-360 east one, the
structural checks that must hold before a payload can be indexed are the same
checks, and both readers need both interpolation schemes.

    offset  type      field
    0       real*8    SLAT   southernmost latitude, degrees
    8       real*8    WLON   westernmost longitude, degrees EAST (0-360)
    16      real*8    DLAT   north-south spacing, degrees
    24      real*8    DLON   east-west spacing, degrees
    32      int*4     NLAT   number of rows, extending north from SLAT
    36      int*4     NLON   number of columns, extending east from WLON
    40      int*4     IKIND  always 1: real*4 data, and the endian marker

**This module states no policy.** It carries no filename, no checksum, no
canonical geometry, no exception class of its own, and **no refusal message
that names a model** - every model-specific word in a refusal arrives from the
caller. Those are the things that differ between one grid and the next, and a
substrate that guessed at any of them would be a second place a model is
described. What a caller must supply is a ``GridDialect``: the exception class
its callers already catch by name, and the sentences its refusals say. See
``geoid18.GEOID_DIALECT`` for the worked example.

The prose and comments below *do* name GEOID18 and VERTCON, deliberately: a
constant whose value was chosen by measuring one particular file has to say
which file, or it becomes an uncited constant (docs/DESIGN.md section 7). What
must never name a model is a **message a user reads**, and the test
``test_no_refusal_message_names_a_model`` is what holds that line.

**Why the dialect carries the exception class rather than this module defining
one.** ``michspc/job.py`` catches ``geoid18.GeoidError`` by name, and the suite
matches on it. A refusal raised from here must therefore *be* that class, not a
base class of it and not a sibling - so the policy layer hands its own exception
type down and this module raises exactly what the caller already handles. The
same seam serves ``vertcon`` without either module learning about the other.

Extracted from ``geoid18.py`` unchanged (docs/PLAN-vertical-datums.md section
3.2). Every behaviour, every message and every tolerance below is the one that
module already shipped; the geoid suite passing untouched is what says so.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, NamedTuple

HEADER = struct.Struct("<4d3i")
"""SLAT, WLON, DLAT, DLON as real*8, then NLAT, NLON, IKIND as int*4."""

HEADER_BYTES = HEADER.size  # 44

# The 3x3 Lagrange neighbourhood interpolate_biquadratic anchors needs three rows
# and three columns; below that its clamping arithmetic (``row_count - 3``) goes
# negative and it would index from the wrong end of the array rather than fail.
MINIMUM_INTERPOLATION_SPAN = 3

# How far a header value may sit from a canonical geometry.
#
# Not zero: the shipped GEOID18 file stores the one-arcminute spacing as the
# decimal literals 0.016666666667 and 0.01666666666699, which differ from the
# double nearest 1/60 by about 3.3e-13 degrees. An exact comparison would reject
# the genuine, checksum-verified NGS file. 1e-9 degrees is about 0.11 mm on the
# ground - four orders of magnitude tighter than the smallest header confusion
# that could plausibly occur (1/60 against 1/30, or 40 N against 41 N), so the
# tolerance admits the real file and nothing else. Disclosed convention: NGS
# publishes no tolerance for reading back its own header.
#
# The reasoning above was measured on GEOID18's one-arcminute spacing and now
# governs every caller, so it is worth saying that it still holds for the other
# one: VERTCON 3.0 is 0.05 degrees (docs/PLAN-vertical-datums.md section 2.2),
# and 1e-9 is six orders of magnitude below that - far tighter than 0.05 against
# 0.025, the smallest confusion that grid could suffer. Any future caller on a
# spacing finer than about 1e-6 degrees must re-derive it rather than inherit it.
GEOMETRY_TOLERANCE_DEG = 1e-9


@dataclass(frozen=True)
class GridDialect:
    """What a policy layer tells the substrate so its refusals stay its own.

    Everything here is a thing that differs between one NGS grid and the next
    and that a shared refusal must nonetheless say. Splitting it out is what
    lets the structural checks be written once without the messages becoming
    generic - a refusal that said "the grid" instead of "the GEOID18 tile" would
    be a worse message than the one this project already ships.
    """

    error: type[Exception]
    """The exception class the policy layer's own callers catch by name.

    Load-bearing: ``job.py`` catches ``geoid18.GeoidError``, so a refusal raised
    from this module has to be that exact class.
    """

    model_name: str
    """How the model names itself in a message, e.g. ``"GEOID18"``."""

    grid_noun: str
    """What this kind of file is, with its article: ``"a geoid grid"``.

    Reads as "... the file is corrupt or is not a geoid grid."
    """

    value_noun: str
    """What one cell holds: ``"geoid height"``.

    Reads as "... would produce a non-finite geoid height."
    """

    outside_consequence: str
    """What being outside the grid means for the caller's output.

    Appended to "Position ... is outside the <model> tile this program ships
    (<extent>). ".
    """

    geometry_consequence: str
    """Why a misdescribing header is refused rather than read.

    Appended, on its own line, to the list of geometry mismatches.
    """

    payload_consequence: str
    """What a non-finite cell would do downstream if it were read.

    Appended to "<path> contains a non-finite <value_noun> (<value>) at cell
    index <n>. ".
    """


class GridHeader(NamedTuple):
    """The seven header fields, in the order the record stores them."""

    south_latitude: float
    west_longitude: float
    """Degrees EAST, 0-360, as the file stores it."""

    latitude_spacing: float
    longitude_spacing: float
    row_count: int
    column_count: int
    ikind: int


def unpack_header(raw: bytes, offset: int = 0) -> GridHeader:
    """The ``<4d3i`` record at ``offset``.

    ``offset`` exists because VERTCON's ``.b`` files bracket the same record
    with Fortran record markers, so the header sits at byte 4 rather than 0.
    GEOID18 has no markers and reads it at 0.
    """
    return GridHeader._make(HEADER.unpack_from(raw, offset))


@dataclass(frozen=True)
class TileGeometry:
    """The geometry a particular published tile is known to have.

    Separate from a loaded grid because this is an *expectation* stated by the
    program, checked against what a file claims - not something read out of the
    file. Kept as data so a loader stays usable for a different tile: a caller
    who has another NGS grid passes that grid's geometry, or none.
    """

    south_latitude: float
    west_longitude: float
    """Degrees EAST, 0-360, as the file stores it."""

    latitude_spacing: float
    longitude_spacing: float
    row_count: int
    column_count: int
    name: str


@dataclass(frozen=True)
class Grid:
    """A loaded NGS grid: its geometry, and its cells in row-major order.

    Subclasses supply a ``dialect`` and whatever named accessors their own
    callers read the values through. This class knows nothing about what the
    numbers mean.
    """

    dialect: ClassVar[GridDialect]

    path: Path
    south_latitude: float
    west_longitude: float
    """Degrees EAST, 0-360, as the file stores it."""

    latitude_spacing: float
    longitude_spacing: float
    row_count: int
    column_count: int
    values: tuple[float, ...]
    """Row-major, southernmost row first, each row west to east."""

    @property
    def north_latitude(self) -> float:
        return self.south_latitude + (self.row_count - 1) * self.latitude_spacing

    @property
    def east_longitude(self) -> float:
        return self.west_longitude + (self.column_count - 1) * self.longitude_spacing

    def _value(self, row: int, column: int) -> float:
        return self.values[row * self.column_count + column]

    def _cell_indices(self, latitude: float, longitude_east: float):
        """Fractional row and column of a position within the grid."""
        row = (latitude - self.south_latitude) / self.latitude_spacing
        column = (longitude_east - self.west_longitude) / self.longitude_spacing
        return row, column

    def contains(self, latitude: float, longitude: float) -> bool:
        east = to_east_longitude(longitude)
        return (
            self.south_latitude <= latitude <= self.north_latitude
            and self.west_longitude <= east <= self.east_longitude
        )

    def interpolate_bilinear(self, latitude: float, longitude: float) -> float:
        """Bilinear interpolation over the enclosing 2x2 cell."""
        row, column = self._require_inside(latitude, longitude)

        row0 = min(int(row), self.row_count - 2)
        col0 = min(int(column), self.column_count - 2)
        dr = row - row0
        dc = column - col0

        v00 = self._value(row0, col0)
        v01 = self._value(row0, col0 + 1)
        v10 = self._value(row0 + 1, col0)
        v11 = self._value(row0 + 1, col0 + 1)

        south = v00 + (v01 - v00) * dc
        north = v10 + (v11 - v10) * dc
        return south + (north - south) * dr

    def interpolate_biquadratic(self, latitude: float, longitude: float) -> float:
        """Biquadratic interpolation over a 3x3 neighbourhood.

        This is the scheme NGS's own INTG program uses for its geoid grids. The
        3x3 block is chosen so the target cell is the middle one where possible,
        then Lagrange quadratics are applied along each row and the three row
        results are combined along the column.

        Which grid wants which scheme is the *caller's* choice and is not
        obvious: GEOID18 is biquadratic by measurement (docs/DESIGN.md amendment
        #8), and the VERTCON uncertainty grid is measurably better read
        bilinearly (docs/PLAN-vertical-datums.md section 2.5). Both live here;
        neither is a default.
        """
        row, column = self._require_inside(latitude, longitude)

        # Anchor so the interpolated point sits in the middle interval of the
        # three, clamped at the grid edges.
        row0 = min(max(int(row) - 1, 0), self.row_count - 3)
        col0 = min(max(int(column) - 1, 0), self.column_count - 3)

        dr = row - row0
        dc = column - col0

        row_values = [
            lagrange3([self._value(row0 + i, col0 + j) for j in range(3)], dc)
            for i in range(3)
        ]
        return lagrange3(row_values, dr)

    def _require_inside(self, latitude: float, longitude: float):
        east = to_east_longitude(longitude)
        if not self.contains(latitude, longitude):
            raise self.dialect.error(
                f"Position {latitude:.6f}, {longitude:.6f} is outside the "
                f"{self.dialect.model_name} tile this program ships "
                f"({self.south_latitude:.1f} to {self.north_latitude:.1f} N, "
                f"{to_signed_longitude(self.west_longitude):.1f} to "
                f"{to_signed_longitude(self.east_longitude):.1f}). "
                + self.dialect.outside_consequence
            )
        return self._cell_indices(latitude, east)


def lagrange3(values: list[float], x: float) -> float:
    """Quadratic through three equally spaced points at x = 0, 1, 2.

    Hand derivation of the Lagrange basis on nodes 0, 1, 2:
        L0 = (x-1)(x-2)/2
        L1 = -x(x-2)      =  x(2-x)
        L2 = x(x-1)/2
    """
    v0, v1, v2 = values
    return (
        v0 * (x - 1.0) * (x - 2.0) / 2.0
        + v1 * x * (2.0 - x)
        + v2 * x * (x - 1.0) / 2.0
    )


def to_east_longitude(longitude: float) -> float:
    """Signed longitude (negative west) to the 0-360 east convention the file uses."""
    return longitude + 360.0 if longitude < 0.0 else longitude


def to_signed_longitude(east: float) -> float:
    return east - 360.0 if east > 180.0 else east


def require_supported_ikind(dialect: GridDialect, path: Path, ikind: int) -> None:
    """Refuse anything but the little-endian real*4 form.

    Byte order is the whole content of this check: a big-endian grid read
    little-endian produces numbers, not an error.
    """
    if ikind != 1:
        raise dialect.error(
            f"{path} declares IKIND={ikind}; this reader handles only IKIND=1, "
            f"the little-endian real*4 form NGS publishes as the PC format. A "
            f"big-endian (Unix) grid will not read correctly here."
        )


def require_readable_header(
    dialect: GridDialect,
    path: Path,
    south: float,
    west: float,
    dlat: float,
    dlon: float,
    rows: int,
    columns: int,
) -> None:
    """Refuse a header that no real NGS grid could carry.

    These are the checks that hold for *any* NGS tile, so they live here rather
    than in the canonical-geometry check. Everything here would otherwise reach
    the interpolators, which divide by the spacings and index by the counts.
    """
    for label, spacing in (("DLAT", dlat), ("DLON", dlon)):
        if not math.isfinite(spacing) or spacing <= 0.0:
            raise dialect.error(
                f"{path} declares {label}={spacing!r}. A grid spacing must be a "
                f"positive, finite number of degrees; the interpolators divide "
                f"by it, so a zero, negative or non-finite spacing would place "
                f"every lookup in the wrong cell or produce a non-finite "
                f"{dialect.value_noun}. The file is corrupt or is not "
                f"{dialect.grid_noun}."
            )

    for label, count in (("NLAT", rows), ("NLON", columns)):
        if count < MINIMUM_INTERPOLATION_SPAN:
            raise dialect.error(
                f"{path} declares {label}={count}. This reader interpolates over "
                f"a {MINIMUM_INTERPOLATION_SPAN}x{MINIMUM_INTERPOLATION_SPAN} "
                f"neighbourhood, so a grid narrower than "
                f"{MINIMUM_INTERPOLATION_SPAN} in either direction cannot be "
                f"interpolated in at all and would be read from the wrong end of "
                f"the array. No {dialect.value_noun} can be taken from it."
            )

    if not math.isfinite(south) or not (-90.0 <= south <= 90.0):
        raise dialect.error(
            f"{path} declares SLAT={south!r}, which is not a latitude. The file "
            f"is corrupt, or is stored in the big-endian (Unix) byte order this "
            f"reader does not handle."
        )

    if not math.isfinite(west) or not (0.0 <= west <= 360.0):
        raise dialect.error(
            f"{path} declares WLON={west!r}. This format stores the westernmost "
            f"longitude in degrees EAST on 0-360, so a value outside that range "
            f"means the file is corrupt or is not {dialect.grid_noun}."
        )


def require_canonical_geometry(
    dialect: GridDialect,
    path: Path,
    expected: TileGeometry,
    south: float,
    west: float,
    dlat: float,
    dlon: float,
    rows: int,
    columns: int,
) -> None:
    """Refuse a file whose header does not describe the tile it claims to be.

    The payload-length check cannot do this: it compares only ``rows * columns``
    against the byte count, and a transposed header preserves that product for a
    square-product grid such as GEOID18's 1081 x 1141.
    """
    mismatches: list[str] = []

    for label, found, want in (
        ("SLAT (southernmost latitude)", south, expected.south_latitude),
        ("WLON (westernmost longitude, east of Greenwich)", west, expected.west_longitude),
        ("DLAT (north-south spacing)", dlat, expected.latitude_spacing),
        ("DLON (east-west spacing)", dlon, expected.longitude_spacing),
    ):
        if not math.isfinite(found) or abs(found - want) > GEOMETRY_TOLERANCE_DEG:
            mismatches.append(f"  {label}: expected {want!r}, found {found!r}")

    for label, found, want in (
        ("NLAT (row count)", rows, expected.row_count),
        ("NLON (column count)", columns, expected.column_count),
    ):
        if found != want:
            mismatches.append(f"  {label}: expected {want}, found {found}")

    if not mismatches:
        return

    raise dialect.error(
        f"{path} does not have the geometry of {expected.name}, the tile this "
        f"program ships:\n" + "\n".join(mismatches) + "\n"
        + dialect.geometry_consequence
    )


def require_finite_payload(
    dialect: GridDialect, path: Path, values: tuple[float, ...]
) -> None:
    """Refuse a payload carrying NaN or an infinity.

    A non-finite cell would not stop anything by itself: the biquadratic
    interpolator would return NaN, and every quantity derived from it downstream
    would be NaN too - a value that is not a refusal and not a number, printed
    beside real ones.

    On a checksum-pinned tile this is redundant with the SHA-256, which
    authenticates every byte. It is here because the loaders accept any path,
    and because it is cheap: measured on this machine over the GEOID18 tile's
    1,233,421 cells, the scan below takes about 11 ms once per process, against
    about 22 ms to unpack the same array - work the loader already did.

    The whole array is tested first, in one C-level pass; the Python loop that
    locates the offending cell for the message runs only when there is one.
    """
    if all(map(math.isfinite, values)):
        return

    for index, value in enumerate(values):
        if not math.isfinite(value):
            raise dialect.error(
                f"{path} contains a non-finite {dialect.value_noun} ({value!r}) "
                f"at cell index {index}. " + dialect.payload_consequence
            )
