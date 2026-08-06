"""NGS GEOID18 binary grid reader.

Geoid separation converts an orthometric height (height above the geoid, what a
level loop measures and what appears in a PNEZD file's Z column) into an
ellipsoid height, which is what the elevation factor needs.

    h = H + N

where H is orthometric and N is the geoid height. **In the conterminous United
States N is negative** - the ellipsoid is above the geoid - and it runs about
-30 to -37 m across Michigan. The manual is explicit (PDF p. 57): "the geoid
height of a station is defined as the height above the ellipsoid minus the
height above the geoid, except in Alaska it is a negative value." Getting this
sign backwards is a ~10 ppm error in every reduced distance, and it is one of
the defects recorded against the prior MATLAB tool (docs/DESIGN.md amendment #1).

**File format.** From the GEOID18 readme: a one-line header followed by the data
in row-major order.

    offset  type      field
    0       real*8    SLAT   southernmost latitude, degrees
    8       real*8    WLON   westernmost longitude, degrees EAST (0-360)
    16      real*8    DLAT   north-south spacing, degrees
    24      real*8    DLON   east-west spacing, degrees
    32      int*4     NLAT   number of rows, extending north from SLAT
    36      int*4     NLON   number of columns, extending east from WLON
    40      int*4     IKIND  always 1: real*4 data, and the endian marker
    44      real*4[]  the grid, southernmost row first, each row west to east

No Fortran record-length markers. This program ships the little-endian ("PC")
variant.

**The tile.** ``data/g2018u3.bin`` is CONUS grid #3, 40-58 N by 96-77 W at one
arcminute, 1081 rows by 1141 columns. It covers all of Michigan with room to
spare. It is committed **unmodified** from NGS rather than trimmed to a Michigan
subgrid, so it stays byte-comparable against the source and its SHA-256 can be
pinned (docs/DESIGN.md section 3).
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_HEADER = struct.Struct("<4d3i")
_HEADER_BYTES = _HEADER.size  # 44

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
GEOID18_TILE = DATA_DIR / "g2018u3.bin"

GEOID18_TILE_SHA256 = "cd2080f904d168e3356effffc535d5d0c9cd8c2a0019ddb4f40a0e2454ebe3b3"
"""SHA-256 of the unmodified NGS file, pinned so a corrupted or substituted
grid is caught rather than silently producing plausible wrong geoid heights.

Source: https://geodesy.noaa.gov/PC_PROD/GEOID18/Format_pc/g2018u3.bin
Downloaded 2026-08-05, 4,933,728 bytes.
"""

GEOID_MODEL_NAME = "GEOID18"

# The 3x3 Lagrange neighbourhood height_biquadratic anchors needs three rows and
# three columns; below that its clamping arithmetic (``row_count - 3``) goes
# negative and it would index from the wrong end of the array rather than fail.
_MINIMUM_INTERPOLATION_SPAN = 3


class GeoidError(Exception):
    """The geoid grid could not be read, or does not cover the point asked for."""


@dataclass(frozen=True)
class TileGeometry:
    """The geometry a particular published tile is known to have.

    Separate from ``GeoidGrid`` because this is an *expectation* stated by the
    program, checked against what a file claims - not something read out of the
    file. Kept as data so ``load_grid`` stays usable for a different tile: a
    caller who has another NGS grid passes that grid's geometry, or none.
    """

    south_latitude: float
    west_longitude: float
    """Degrees EAST, 0-360, as the file stores it."""

    latitude_spacing: float
    longitude_spacing: float
    row_count: int
    column_count: int
    name: str


GEOID18_U3_GEOMETRY = TileGeometry(
    south_latitude=40.0,
    west_longitude=264.0,  # 96 W in the file's 0-360 east convention
    latitude_spacing=1.0 / 60.0,  # one arcminute
    longitude_spacing=1.0 / 60.0,
    row_count=1081,
    column_count=1141,
    name="GEOID18 CONUS grid #3 (g2018u3)",
)
"""The geometry of the tile this program ships.

Source: the GEOID18 readme's grid table, and the file's own name - u3 is the
third CONUS grid, 40-58 N by 96-77 W at one arcminute. Recorded independently in
docs/DESIGN.md amendment #8. Checkable by hand from the counts alone:

    north = 40.0 + (1081 - 1) / 60 = 40 + 18 = 58 N
    east  = 264.0 + (1141 - 1) / 60 = 264 + 19 = 283 E = 77 W

**Why this exists.** Row and column counts appear in the header only as two
integers whose product must match the payload length, and 1081 x 1141 has the
same product as 1141 x 1081. Swapping them therefore passes every structural
check while re-shaping the grid: the interim review gate measured the result at
43.0 N, 84.5 W as -27.927 m against a true -33.085 m, a 5.16 m error that looks
like a perfectly ordinary Michigan geoid height (docs/DESIGN.md amendment #11,
finding 6). Only knowing what the shipped tile's geometry actually *is* catches
that.
"""

# How far a header value may sit from the canonical geometry above.
#
# Not zero: the shipped file stores the one-arcminute spacing as the decimal
# literals 0.016666666667 and 0.01666666666699, which differ from the double
# nearest 1/60 by about 3.3e-13 degrees. An exact comparison would reject the
# genuine, checksum-verified NGS file. 1e-9 degrees is about 0.11 mm on the
# ground - four orders of magnitude tighter than the smallest header confusion
# that could plausibly occur (1/60 against 1/30, or 40 N against 41 N), so the
# tolerance admits the real file and nothing else. Disclosed convention: NGS
# publishes no tolerance for reading back its own header.
_GEOMETRY_TOLERANCE_DEG = 1e-9


@dataclass(frozen=True)
class GeoidGrid:
    """A loaded GEOID18 tile."""

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
        east = _to_east_longitude(longitude)
        return (
            self.south_latitude <= latitude <= self.north_latitude
            and self.west_longitude <= east <= self.east_longitude
        )

    def height_bilinear(self, latitude: float, longitude: float) -> float:
        """Geoid height by bilinear interpolation over the enclosing 2x2 cell."""
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

    def height_biquadratic(self, latitude: float, longitude: float) -> float:
        """Geoid height by biquadratic interpolation over a 3x3 neighbourhood.

        This is the scheme NGS's own INTG program uses for its geoid grids. The
        3x3 block is chosen so the target cell is the middle one where possible,
        then Lagrange quadratics are applied along each row and the three row
        results are combined along the column.
        """
        row, column = self._require_inside(latitude, longitude)

        # Anchor so the interpolated point sits in the middle interval of the
        # three, clamped at the grid edges.
        row0 = min(max(int(row) - 1, 0), self.row_count - 3)
        col0 = min(max(int(column) - 1, 0), self.column_count - 3)

        dr = row - row0
        dc = column - col0

        row_values = [
            _lagrange3([self._value(row0 + i, col0 + j) for j in range(3)], dc)
            for i in range(3)
        ]
        return _lagrange3(row_values, dr)

    def _require_inside(self, latitude: float, longitude: float):
        east = _to_east_longitude(longitude)
        if not self.contains(latitude, longitude):
            raise GeoidError(
                f"Position {latitude:.6f}, {longitude:.6f} is outside the "
                f"{GEOID_MODEL_NAME} tile this program ships "
                f"({self.south_latitude:.1f} to {self.north_latitude:.1f} N, "
                f"{_to_signed_longitude(self.west_longitude):.1f} to "
                f"{_to_signed_longitude(self.east_longitude):.1f}). No geoid "
                f"height can be looked up, so no elevation or combined factor "
                f"can be computed for it. Check the coordinate, the zone and "
                f"the units."
            )
        return self._cell_indices(latitude, east)


def _lagrange3(values: list[float], x: float) -> float:
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


def _to_east_longitude(longitude: float) -> float:
    """Signed longitude (negative west) to the 0-360 east convention the file uses."""
    return longitude + 360.0 if longitude < 0.0 else longitude


def _to_signed_longitude(east: float) -> float:
    return east - 360.0 if east > 180.0 else east


def _require_readable_header(
    path: Path,
    south: float,
    west: float,
    dlat: float,
    dlon: float,
    rows: int,
    columns: int,
) -> None:
    """Refuse a header that no real geoid grid could carry.

    These are the checks that hold for *any* NGS tile, so they live here rather
    than in the canonical-geometry check. Everything here would otherwise reach
    the interpolators, which divide by the spacings and index by the counts.
    """
    for label, spacing in (("DLAT", dlat), ("DLON", dlon)):
        if not math.isfinite(spacing) or spacing <= 0.0:
            raise GeoidError(
                f"{path} declares {label}={spacing!r}. A grid spacing must be a "
                f"positive, finite number of degrees; the interpolators divide "
                f"by it, so a zero, negative or non-finite spacing would place "
                f"every lookup in the wrong cell or produce a non-finite geoid "
                f"height. The file is corrupt or is not a geoid grid."
            )

    for label, count in (("NLAT", rows), ("NLON", columns)):
        if count < _MINIMUM_INTERPOLATION_SPAN:
            raise GeoidError(
                f"{path} declares {label}={count}. This reader interpolates over "
                f"a {_MINIMUM_INTERPOLATION_SPAN}x{_MINIMUM_INTERPOLATION_SPAN} "
                f"neighbourhood, so a grid narrower than "
                f"{_MINIMUM_INTERPOLATION_SPAN} in either direction cannot be "
                f"interpolated in at all and would be read from the wrong end of "
                f"the array. No geoid height can be taken from it."
            )

    if not math.isfinite(south) or not (-90.0 <= south <= 90.0):
        raise GeoidError(
            f"{path} declares SLAT={south!r}, which is not a latitude. The file "
            f"is corrupt, or is stored in the big-endian (Unix) byte order this "
            f"reader does not handle."
        )

    if not math.isfinite(west) or not (0.0 <= west <= 360.0):
        raise GeoidError(
            f"{path} declares WLON={west!r}. This format stores the westernmost "
            f"longitude in degrees EAST on 0-360, so a value outside that range "
            f"means the file is corrupt or is not a geoid grid."
        )


def _require_canonical_geometry(
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
    against the byte count, and a transposed header preserves that product.
    """
    mismatches: list[str] = []

    for label, found, want in (
        ("SLAT (southernmost latitude)", south, expected.south_latitude),
        ("WLON (westernmost longitude, east of Greenwich)", west, expected.west_longitude),
        ("DLAT (north-south spacing)", dlat, expected.latitude_spacing),
        ("DLON (east-west spacing)", dlon, expected.longitude_spacing),
    ):
        if not math.isfinite(found) or abs(found - want) > _GEOMETRY_TOLERANCE_DEG:
            mismatches.append(f"  {label}: expected {want!r}, found {found!r}")

    for label, found, want in (
        ("NLAT (row count)", rows, expected.row_count),
        ("NLON (column count)", columns, expected.column_count),
    ):
        if found != want:
            mismatches.append(f"  {label}: expected {want}, found {found}")

    if not mismatches:
        return

    raise GeoidError(
        f"{path} does not have the geometry of {expected.name}, the tile this "
        f"program ships:\n" + "\n".join(mismatches) + "\n"
        f"A header that misdescribes the grid does not fail: it re-shapes it, "
        f"and every geoid height then comes from the wrong cell. Transposing "
        f"the row and column counts alone moves a Michigan geoid height by over "
        f"five metres while leaving the file the right length, which is why the "
        f"geometry is checked and not just the size. Refused rather than "
        f"returning heights that would look ordinary and be wrong."
    )


def _require_finite_payload(path: Path, values: tuple[float, ...]) -> None:
    """Refuse a payload carrying NaN or an infinity.

    A non-finite cell would not stop anything by itself: the biquadratic
    interpolator would return NaN, ``h = H + N`` would be NaN, and the elevation
    and combined factors would be NaN in the audit file - a value that is not a
    refusal and not a number, printed beside real ones.

    On the shipped tile this is redundant with the SHA-256, which authenticates
    every byte. It is here because ``load_grid`` accepts any path, and because
    it is cheap: measured on this machine over the 1,233,421-cell tile, the scan
    below takes about 11 ms once per process, against about 22 ms to unpack the
    same array - work this loader already did.

    The whole array is tested first, in one C-level pass; the Python loop that
    locates the offending cell for the message runs only when there is one.
    """
    if all(map(math.isfinite, values)):
        return

    for index, value in enumerate(values):
        if not math.isfinite(value):
            raise GeoidError(
                f"{path} contains a non-finite geoid height ({value!r}) at cell "
                f"index {index}. Every cell of a geoid grid is a real height in "
                f"metres; a NaN or infinity would propagate silently into the "
                f"ellipsoid height and out into the elevation and combined "
                f"factors, so the file is refused rather than read."
            )


def load_grid(
    path: Path | None = None,
    verify_checksum: bool = False,
    expect_geometry: TileGeometry | None = None,
) -> GeoidGrid:
    """Read a GEOID18 binary tile.

    ``verify_checksum`` re-hashes the whole 4.7 MB file against the pinned
    SHA-256 of the shipped tile. ``expect_geometry`` additionally requires the
    header to describe a named, known tile; without it only the format-level
    checks that hold for any NGS grid are applied, so this function stays usable
    for a different tile.

    The production path passes both. See ``load_shipped_grid``.
    """
    path = path or GEOID18_TILE

    try:
        raw = path.read_bytes()
    except OSError as error:
        raise GeoidError(
            f"Could not read the {GEOID_MODEL_NAME} grid at {path}: {error}. "
            f"This file ships with the program; if it is missing the "
            f"installation is incomplete."
        ) from error

    if len(raw) < _HEADER_BYTES:
        raise GeoidError(
            f"{path} is only {len(raw)} bytes, too short to contain the "
            f"{_HEADER_BYTES}-byte {GEOID_MODEL_NAME} header. The file is "
            f"truncated or is not a geoid grid."
        )

    if verify_checksum:
        digest = hashlib.sha256(raw).hexdigest()
        if digest != GEOID18_TILE_SHA256:
            raise GeoidError(
                f"{path} does not match the {GEOID_MODEL_NAME} grid this "
                f"program was built against.\n  expected SHA-256 "
                f"{GEOID18_TILE_SHA256}\n  found    SHA-256 {digest}\n"
                f"Geoid heights from an unverified grid could be wrong in ways "
                f"nothing downstream would notice, so it is refused."
            )

    south, west, dlat, dlon, rows, columns, ikind = _HEADER.unpack_from(raw, 0)

    if ikind != 1:
        raise GeoidError(
            f"{path} declares IKIND={ikind}; this reader handles only IKIND=1, "
            f"the little-endian real*4 form NGS publishes as the PC format. A "
            f"big-endian (Unix) grid will not read correctly here."
        )

    _require_readable_header(path, south, west, dlat, dlon, rows, columns)

    if expect_geometry is not None:
        _require_canonical_geometry(
            path, expect_geometry, south, west, dlat, dlon, rows, columns
        )

    expected = rows * columns * 4
    payload = raw[_HEADER_BYTES:]
    if len(payload) != expected:
        raise GeoidError(
            f"{path} header declares {rows} x {columns} cells "
            f"({expected} bytes of data) but carries {len(payload)}. The file "
            f"is truncated or corrupt."
        )

    values = struct.unpack(f"<{rows * columns}f", payload)
    _require_finite_payload(path, values)

    return GeoidGrid(
        path=path,
        south_latitude=south,
        west_longitude=west,
        latitude_spacing=dlat,
        longitude_spacing=dlon,
        row_count=rows,
        column_count=columns,
        values=values,
    )


def load_shipped_grid(path: Path | None = None) -> GeoidGrid:
    """Load the tile this program ships, fully authenticated.

    This is the production policy in one place: the SHA-256 must match the
    pinned digest of the unmodified NGS file, **and** the header must describe
    the geometry that tile is known to have. Two independent gates, because they
    fail differently - the checksum catches any altered byte, the geometry check
    catches a file that is internally consistent and still describes the wrong
    grid.

    Takes a path only so the checks themselves can be exercised against a
    deliberately tampered copy in a test. Nothing in the program passes one.
    """
    return load_grid(
        path or GEOID18_TILE,
        verify_checksum=True,
        expect_geometry=GEOID18_U3_GEOMETRY,
    )


@lru_cache(maxsize=1)
def default_grid() -> GeoidGrid:
    """The shipped tile, loaded once per process.

    A file of several thousand points would otherwise re-read and re-unpack
    4.7 MB per row.

    **Authenticated.** This is the path production actually takes, so it takes
    the checked one: it hashes the file and validates the header geometry
    (``load_shipped_grid``). The gate previously ran only in the test suite and
    the frozen bundle's self-test, which left the running program trusting
    whatever bytes were on disk - the interim review gate's finding 6
    (docs/DESIGN.md amendment #11).

    The cost is paid once per process and measured, not assumed: reading and
    hashing the 4,933,728-byte file takes about 3.5 ms, against about 22 ms to
    unpack the same payload into floats - work this loader already did - and
    about 32 ms for the whole cold load. The check is roughly a tenth of the
    load it protects, and the load happens once no matter how many points a
    file holds.
    """
    return load_shipped_grid()


def geoid_height(latitude: float, longitude: float, grid: GeoidGrid | None = None) -> float:
    """Geoid height at a position, meters, negative in Michigan.

    Uses biquadratic interpolation, matching NGS's own INTG program. See
    docs/DESIGN.md amendment #8 for the evidence behind that choice.
    """
    grid = grid or default_grid()
    return grid.height_biquadratic(latitude, longitude)
