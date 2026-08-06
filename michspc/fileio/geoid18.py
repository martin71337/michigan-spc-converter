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


class GeoidError(Exception):
    """The geoid grid could not be read, or does not cover the point asked for."""


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


def load_grid(path: Path | None = None, verify_checksum: bool = False) -> GeoidGrid:
    """Read a GEOID18 binary tile.

    ``verify_checksum`` re-hashes the whole 4.7 MB file; it is off by default so
    ordinary use does not pay for it on every load, and the pin is checked by
    the test suite and by the frozen bundle's self-test instead.
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

    expected = rows * columns * 4
    payload = raw[_HEADER_BYTES:]
    if len(payload) != expected:
        raise GeoidError(
            f"{path} header declares {rows} x {columns} cells "
            f"({expected} bytes of data) but carries {len(payload)}. The file "
            f"is truncated or corrupt."
        )

    values = struct.unpack(f"<{rows * columns}f", payload)

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


@lru_cache(maxsize=1)
def default_grid() -> GeoidGrid:
    """The shipped tile, loaded once per process.

    A file of several thousand points would otherwise re-read and re-unpack
    4.7 MB per row.
    """
    return load_grid()


def geoid_height(latitude: float, longitude: float, grid: GeoidGrid | None = None) -> float:
    """Geoid height at a position, meters, negative in Michigan.

    Uses biquadratic interpolation, matching NGS's own INTG program. See
    docs/DESIGN.md amendment #8 for the evidence behind that choice.
    """
    grid = grid or default_grid()
    return grid.height_biquadratic(latitude, longitude)
