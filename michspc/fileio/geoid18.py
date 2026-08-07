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

**This module is the GEOID18 policy over ``ngs_grid``.** The header record, the
geometry checking, the longitude convention, both interpolators and the
structural refusals are shared with the VERTCON reader and live in
``michspc/fileio/ngs_grid.py`` (docs/PLAN-vertical-datums.md section 3.2). What
stays here is everything that is *about GEOID18*: which file, which checksum,
which geometry, which interpolation scheme, and what every refusal says.
"""

from __future__ import annotations

import hashlib
import struct
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from michspc.fileio import ngs_grid
from michspc.fileio.ngs_grid import TileGeometry

# The substrate's names, kept under this module's historical private ones. They
# are re-exported rather than moved out of reach because they are part of what
# the geoid suite tests through this module, and because a reader who comes
# looking for _lagrange3 in the file that used to hold it should find it.
from michspc.fileio.ngs_grid import lagrange3 as _lagrange3  # noqa: F401
from michspc.fileio.ngs_grid import to_east_longitude as _to_east_longitude  # noqa: F401
from michspc.fileio.ngs_grid import to_signed_longitude as _to_signed_longitude  # noqa: F401


def _data_directory() -> Path:
    """Where the shipped tile lives, frozen or from source.

    PyInstaller sets ``sys._MEIPASS`` to the directory it unpacked the bundle's
    data files into, and nothing else sets it (docs/method/TOOLING.md). A source
    run walks up from this module instead: fileio -> michspc -> the repository
    root, then ``data/``.

    Stated explicitly rather than left to the source-tree walk happening to land
    in the right place inside a bundle. It very nearly does — a frozen module's
    ``__file__`` sits under ``sys._MEIPASS`` — but "the frozen program finds its
    geoid grid" is not a property to hold by coincidence, and
    ``tests/test_selftest.py`` pins both branches.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "data"
    return Path(__file__).resolve().parent.parent.parent / "data"


DATA_DIR = _data_directory()
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


GEOID_DIALECT = ngs_grid.GridDialect(
    error=GeoidError,
    model_name=GEOID_MODEL_NAME,
    grid_noun="a geoid grid",
    value_noun="geoid height",
    outside_consequence=(
        "No geoid height can be looked up, so no elevation or combined factor "
        "can be computed for it. Check the coordinate, the zone and the units."
    ),
    geometry_consequence=(
        "A header that misdescribes the grid does not fail: it re-shapes it, "
        "and every geoid height then comes from the wrong cell. Transposing "
        "the row and column counts alone moves a Michigan geoid height by over "
        "five metres while leaving the file the right length, which is why the "
        "geometry is checked and not just the size. Refused rather than "
        "returning heights that would look ordinary and be wrong."
    ),
    payload_consequence=(
        "Every cell of a geoid grid is a real height in metres; a NaN or "
        "infinity would propagate silently into the ellipsoid height and out "
        "into the elevation and combined factors, so the file is refused rather "
        "than read."
    ),
)
"""What the shared substrate's refusals say when it is reading a geoid grid.

The wording is the whole point of this record. A structural check written once
and shared between two readers would otherwise have to speak generically, and
this project's refusals are meant to teach: they name the file, say what the
value would have been used for, and say what to do. ``error=GeoidError`` is
load-bearing rather than cosmetic - ``michspc/job.py`` catches that class by
name, so a refusal raised inside ``ngs_grid`` has to be exactly it.
"""


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


@dataclass(frozen=True)
class GeoidGrid(ngs_grid.Grid):
    """A loaded GEOID18 tile.

    The geometry, the cell lookup and both interpolators are ``ngs_grid.Grid``'s;
    what this class adds is that the numbers are geoid heights in metres, and
    that a refusal about them speaks ``GEOID_DIALECT``.
    """

    dialect = GEOID_DIALECT

    def height_bilinear(self, latitude: float, longitude: float) -> float:
        """Geoid height by bilinear interpolation over the enclosing 2x2 cell."""
        return self.interpolate_bilinear(latitude, longitude)

    def height_biquadratic(self, latitude: float, longitude: float) -> float:
        """Geoid height by biquadratic interpolation over a 3x3 neighbourhood.

        Biquadratic IS the scheme NGS's INTG program uses. The **anchoring**
        this inherits is not INTG's - INTG centres its stencil on the nearest
        node and this anchors below the point. Corrected at the WP-V4 gate from
        a claim that stood for three releases; the evidence, the measured cost
        (about 4 mm at worst in a reported separation) and the reason it is left
        alone for now are in ``ngs_grid.interpolate_biquadratic``.
        """
        return self.interpolate_biquadratic(latitude, longitude)


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

    if len(raw) < ngs_grid.HEADER_BYTES:
        raise GeoidError(
            f"{path} is only {len(raw)} bytes, too short to contain the "
            f"{ngs_grid.HEADER_BYTES}-byte {GEOID_MODEL_NAME} header. The file is "
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

    header = ngs_grid.unpack_header(raw, 0)
    south = header.south_latitude
    west = header.west_longitude
    dlat = header.latitude_spacing
    dlon = header.longitude_spacing
    rows = header.row_count
    columns = header.column_count

    ngs_grid.require_supported_ikind(GEOID_DIALECT, path, header.ikind)

    ngs_grid.require_readable_header(
        GEOID_DIALECT, path, south, west, dlat, dlon, rows, columns
    )

    if expect_geometry is not None:
        ngs_grid.require_canonical_geometry(
            GEOID_DIALECT, path, expect_geometry, south, west, dlat, dlon, rows, columns
        )

    expected = rows * columns * 4
    payload = raw[ngs_grid.HEADER_BYTES:]
    if len(payload) != expected:
        raise GeoidError(
            f"{path} header declares {rows} x {columns} cells "
            f"({expected} bytes of data) but carries {len(payload)}. The file "
            f"is truncated or corrupt."
        )

    values = struct.unpack(f"<{rows * columns}f", payload)
    ngs_grid.require_finite_payload(GEOID_DIALECT, path, values)

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

    Uses biquadratic interpolation, which is the scheme NGS's own INTG program
    uses. See docs/DESIGN.md amendment #8 for the evidence behind that choice,
    and its correction: the stencil ANCHORING here is not INTG's, and
    ``ngs_grid.interpolate_biquadratic`` records what that costs and why it has
    not been changed inside a vertical-datum build.
    """
    grid = grid or default_grid()
    return grid.height_biquadratic(latitude, longitude)
