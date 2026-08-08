"""NGS geoid grid reader, and the geoid model registry.

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

**The tiles.** ``data/g2018u3.bin`` (GEOID18) and ``data/g2012bu3.bin``
(GEOID12B) are both CONUS grid #3, 40-58 N by 96-77 W at one arcminute, 1081
rows by 1141 columns - the same geometry and the same byte count, which is why
each is pinned by its own SHA-256: the digest is the only structural fact that
tells them apart. Each covers all of Michigan with room to spare, and each is
committed **unmodified** from NGS rather than trimmed to a Michigan subgrid, so
it stays byte-comparable against the source (docs/DESIGN.md section 3).

**This module is the geoid policy over ``ngs_grid``, and the geoid model
registry.** The header record, the geometry checking, the longitude convention,
both interpolators and the structural refusals are shared with the VERTCON
reader and live in ``michspc/fileio/ngs_grid.py`` (docs/PLAN-vertical-datums.md
section 3.2). What stays here is everything that is *about a geoid model*:
which file, which checksum, which geometry, which vertical datum its heights
are defined against, which interpolation scheme, and what every refusal says.
Since WP-V5 those facts live in one place - the ``GeoidModel`` records below -
and everything else, the module-level tile constants included, is derived from
them.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from michspc.fileio import ngs_grid
from michspc.fileio.ngs_grid import TileGeometry

# fileio may import the computation core; the reverse is forbidden
# (tests/test_architecture.py). The vertical datum on a GeoidModel record is
# load-bearing, not documentation: it is what lets require_geoid_matches_datum
# refuse a geoid applied against heights from another era (DESIGN.md #32).
from michspc.spc.vertical import NAVD88, VerticalDatum

# The substrate's names, kept under this module's historical private ones. They
# are re-exported rather than moved out of reach because they are part of what
# the geoid suite tests through this module, and because a reader who comes
# looking for _lagrange3 in the file that used to hold it should find it.
from michspc.fileio.ngs_grid import lagrange3 as _lagrange3  # noqa: F401
from michspc.fileio.ngs_grid import to_east_longitude as _to_east_longitude  # noqa: F401
from michspc.fileio.ngs_grid import to_signed_longitude as _to_signed_longitude  # noqa: F401


DATA_DIR = ngs_grid.shipped_data_directory()


class GeoidError(Exception):
    """The geoid grid could not be read, or does not cover the point asked for."""


def _dialect_for(model_name: str) -> ngs_grid.GridDialect:
    """What the shared substrate's refusals say when reading a geoid grid.

    The wording is the whole point of this record. A structural check written
    once and shared between two readers would otherwise have to speak
    generically, and this project's refusals are meant to teach: they name the
    file, say what the value would have been used for, and say what to do.
    ``error=GeoidError`` is load-bearing rather than cosmetic -
    ``michspc/job.py`` catches that class by name, so a refusal raised inside
    ``ngs_grid`` has to be exactly it.

    A function of the model name rather than one constant, because since WP-V5
    two geoid models load through this module and a refusal about the GEOID12B
    tile must not call it GEOID18 - "outside the GEOID18 tile" would be a false
    statement about which grid was consulted. Every other word is identical for
    every geoid model.
    """
    return ngs_grid.GridDialect(
        error=GeoidError,
        model_name=model_name,
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


@dataclass(frozen=True)
class GeoidModel:
    """One published NGS geoid model this program can look heights up in.

    THE authoritative representation of a geoid model's facts
    (docs/PLAN-vertical-datums.md section 3.4): the module-level tile constants
    below are derived aliases of these fields, never a second statement of
    them. Frozen and hashable on purpose - the per-model grid cache is keyed on
    the record itself - and every field it carries is itself immutable
    (``TileGeometry`` and ``VerticalDatum`` are frozen dataclasses).
    """

    name: str
    """How the model names itself everywhere a user reads it, e.g. "GEOID18".

    Spelled the way NGS spells it. This is also what ``JobResult.geoid_model``
    carries and what the job record prints, so it can be handed back to NGS's
    geoid service for checking.
    """

    tile_filename: str
    """NGS's own filename for the CONUS #3 tile, unmodified, under ``data/``."""

    sha256: str
    """SHA-256 of the unmodified NGS file, pinned so a corrupted or substituted
    grid is caught rather than silently producing plausible wrong geoid
    heights. The two shipped tiles are byte-for-byte the same SIZE on the same
    geometry, so the digest is the only structural fact that tells them apart."""

    geometry: TileGeometry
    """The geometry the tile is known to have - an expectation stated by the
    program and checked against what the file claims, because a transposed
    header preserves the payload length while re-shaping the grid
    (docs/DESIGN.md amendment #11, finding 6)."""

    vertical_datum: VerticalDatum
    """The vertical datum the model's orthometric heights are defined against.

    Load-bearing, not documentation (plan section 3.4): it is what lets
    ``require_geoid_matches_datum`` refuse a geoid separation applied to
    heights from another era - DESIGN.md #32's "two eras inside one number".
    Both models shipped today are NAVD 88; the guard exists before the case
    that needs it (GEOID2022 against NAPGD2022) arrives.
    """

    citation: str
    """Source URL and download date - no uncited constants (docs/DESIGN.md
    section 7)."""


GEOID18_MODEL = GeoidModel(
    name="GEOID18",
    tile_filename="g2018u3.bin",
    sha256="cd2080f904d168e3356effffc535d5d0c9cd8c2a0019ddb4f40a0e2454ebe3b3",
    geometry=TileGeometry(
        south_latitude=40.0,
        west_longitude=264.0,  # 96 W in the file's 0-360 east convention
        latitude_spacing=1.0 / 60.0,  # one arcminute
        longitude_spacing=1.0 / 60.0,
        row_count=1081,
        column_count=1141,
        name="GEOID18 CONUS grid #3 (g2018u3)",
    ),
    vertical_datum=NAVD88,
    citation=(
        "https://geodesy.noaa.gov/PC_PROD/GEOID18/Format_pc/g2018u3.bin, "
        "downloaded 2026-08-05, 4,933,728 bytes, committed unmodified "
        "(docs/DESIGN.md section 3)"
    ),
)
"""The model this program has shipped since 0.1.0, and the default.

Geometry source: the GEOID18 readme's grid table, and the file's own name - u3
is the third CONUS grid, 40-58 N by 96-77 W at one arcminute. Recorded
independently in docs/DESIGN.md amendment #8. Checkable by hand from the counts
alone:

    north = 40.0 + (1081 - 1) / 60 = 40 + 18 = 58 N
    east  = 264.0 + (1141 - 1) / 60 = 264 + 19 = 283 E = 77 W

**Why the geometry is recorded at all.** Row and column counts appear in the
header only as two integers whose product must match the payload length, and
1081 x 1141 has the same product as 1141 x 1081. Swapping them therefore passes
every structural check while re-shaping the grid: the interim review gate
measured the result at 43.0 N, 84.5 W as -27.927 m against a true -33.085 m, a
5.16 m error that looks like a perfectly ordinary Michigan geoid height
(docs/DESIGN.md amendment #11, finding 6). Only knowing what the shipped tile's
geometry actually *is* catches that.
"""

GEOID12B_MODEL = GeoidModel(
    name="GEOID12B",
    tile_filename="g2012bu3.bin",
    sha256="7ce1755c1e6ef8a1cc2909bd221e4a94fa46b2fbc33ebe4489a4973edd39b844",
    geometry=TileGeometry(
        south_latitude=40.0,
        west_longitude=264.0,  # 96 W in the file's 0-360 east convention
        latitude_spacing=1.0 / 60.0,  # one arcminute
        longitude_spacing=1.0 / 60.0,
        row_count=1081,
        column_count=1141,
        name="GEOID12B CONUS grid #3 (g2012bu3)",
    ),
    vertical_datum=NAVD88,
    citation=(
        "https://geodesy.noaa.gov/PC_PROD/GEOID12B/Format_pc/g2012bu3.bin, "
        "downloaded 2026-08-07, 4,933,728 bytes, committed unmodified "
        "(docs/PLAN-vertical-datums.md section 2.1)"
    ),
)
"""GEOID18's predecessor, kept because older jobs were reduced against it.

The tile was committed and checksum-pinned by WP-V1; this record (WP-V5) is
what first READS it. Until the WP-V4 review gate the digest lived only in the
plan document - ``michspc.spec`` bundled the file, ``tests/test_selftest.py``
checked its NAME and ``tools/build_release.py`` checked its presence, so
altering one payload float passed every executable check in the repo (WP-V4
review, MEDIUM 1). The digest now lives here, in the runtime record the loader
authenticates against - the WP-V4 gate's instruction - with the frozen NGS
anchors of ``tests/fixtures/geoid12b_anchors.py`` gating what the tile
answers, exactly as GEOID18 is gated.

The geometry is numerically identical to GEOID18's - the same CONUS tile #3
shape, stated as its own record so a refusal about this file names this file.
Same size, same geometry: the SHA-256 and the anchors are the only things that
can tell the two tiles apart, which is why both exist.
"""


ALL_GEOID_MODELS: tuple[GeoidModel, ...] = (GEOID18_MODEL, GEOID12B_MODEL)
"""Every geoid model this program carries, in the order an interface offers
them. GEOID2022 arrives later as a third record here - plus its tile, its pin
and its anchors - not as an excavation (docs/PLAN-vertical-datums.md section
3.4)."""

_MODELS_BY_NAME: Mapping[str, GeoidModel] = MappingProxyType(
    {model.name: model for model in ALL_GEOID_MODELS}
)

_DIALECTS_BY_NAME: Mapping[str, ngs_grid.GridDialect] = MappingProxyType(
    {model.name: _dialect_for(model.name) for model in ALL_GEOID_MODELS}
)


def geoid_model_by_name(name: str) -> GeoidModel:
    """Look up a geoid model by its name.

    Refuses an unknown name rather than guessing, and names what is available -
    the same contract as ``vertical.vertical_datum_by_code`` and
    ``zones.zone_by_code``.
    """
    key = str(name).strip()
    try:
        return _MODELS_BY_NAME[key]
    except KeyError:
        known = ", ".join(
            f"{model.name} ({model.tile_filename})" for model in ALL_GEOID_MODELS
        )
        raise KeyError(
            f"No geoid model named {name!r}. Known geoid models are: {known}."
        ) from None


# ---------------------------------------------------------------------------
# Derived aliases. The records above are the one authoritative representation
# of each model's facts; these names exist because three releases of code and
# tests read them here, and each is DERIVED from its record - never a second
# statement of the fact (docs/DESIGN.md section 7).
# ---------------------------------------------------------------------------

GEOID_MODEL_NAME = GEOID18_MODEL.name
"""Derived: the default model's name. Kept for the callers that predate the
registry; anything model-aware should read the record it was given instead."""

GEOID18_TILE = DATA_DIR / GEOID18_MODEL.tile_filename
GEOID18_TILE_SHA256 = GEOID18_MODEL.sha256
GEOID18_U3_GEOMETRY = GEOID18_MODEL.geometry

GEOID12B_TILE = DATA_DIR / GEOID12B_MODEL.tile_filename
GEOID12B_TILE_SHA256 = GEOID12B_MODEL.sha256

GEOID_DIALECT = _DIALECTS_BY_NAME[GEOID18_MODEL.name]
"""Derived: the default model's dialect. See ``_dialect_for`` for what a
dialect is and why the model name is the only word that varies."""


@dataclass(frozen=True)
class GeoidGrid(ngs_grid.Grid):
    """A loaded GEOID18 tile.

    The geometry, the cell lookup and both interpolators are ``ngs_grid.Grid``'s;
    what this class adds is that the numbers are geoid heights in metres, and
    that a refusal about them speaks ``GEOID_DIALECT``. The dialect stays a
    ClassVar - a property of the KIND of grid, not of one loaded file
    (tests/test_ngs_grid.py pins the constructor to the eight data fields a
    reader parses) - so each registry model gets its own kind: see
    ``_grid_class_for``.
    """

    dialect = GEOID_DIALECT

    def height_bilinear(self, latitude: float, longitude: float) -> float:
        """Geoid height by bilinear interpolation over the enclosing 2x2 cell."""
        return self.interpolate_bilinear(latitude, longitude)

    def height_biquadratic(self, latitude: float, longitude: float) -> float:
        """Geoid height by biquadratic interpolation over a 3x3 neighbourhood.

        Anchored on the NEAREST node, which is what NGS's own INTG program does
        (``irown = nint(...)`` in intg.f) and what NOAA TM NOS NGS-84 describes:
        "the nearest 3x3 set of grid points". Re-anchored at WP-G1 on the
        owner's instruction to replicate NOAA (DESIGN.md #37); for three
        releases this read the floor-anchored stencil while claiming to be
        INTG's, a claim corrected at the WP-V4 gate (DESIGN.md #36). Measured
        against NGS's own geoid API at 120 positions chosen where the two
        anchorings diverge most, nearest-node is the better fit - rms 0.454 mm
        against 0.715, 83 against 66 of 120 reproducing NGS's printed figure -
        and the worst change to a reported separation is about 7 mm (Michigan
        window, measured at the merge gate; ~8 mm over the whole tile), far
        inside GEOID18's own 30-60 mm model uncertainty. No coordinate moves.
        The nearest-node stencil is discontinuous at half-cell lines - about
        6 mm at worst here, where the old anchoring was continuous; that
        property, NOAA's sharing of it, and its pin are recorded in
        ``ngs_grid.interpolate_biquadratic_nearest_node``.

        The honest caveat, from #36 and kept here on purpose: INTG's stencil is
        NOT the best fit to the NGS geoid API - a bicubic is, by a visible
        margin (rms 0.409 mm). This anchoring is used because the owner ruled
        that NOAA's published program governs where NOAA's program and NOAA's
        service disagree, and ``intg.f`` is the documented reader for exactly
        this ``.bin`` format while the API's engine is undocumented.
        """
        return self.interpolate_biquadratic_nearest_node(latitude, longitude)


@dataclass(frozen=True)
class Geoid12bGrid(GeoidGrid):
    """A loaded GEOID12B tile: the same reader, refusals that name GEOID12B.

    Nothing here but the dialect. The two tiles share every structural
    property - same format, same geometry, same interpolation - and differ
    only in which model a refusal must name, which is exactly what a dialect
    is. A subclass rather than an instance field keeps ``dialect`` the
    ClassVar the substrate declares and the suite pins.
    """

    dialect = _DIALECTS_BY_NAME[GEOID12B_MODEL.name]


_GRID_CLASS_BY_MODEL_NAME: Mapping[str, type[GeoidGrid]] = MappingProxyType(
    {
        GEOID18_MODEL.name: GeoidGrid,
        GEOID12B_MODEL.name: Geoid12bGrid,
    }
)


@lru_cache(maxsize=16)
def _grid_class_for_name(model_name: str) -> type[GeoidGrid]:
    """One subclass per model NAME, cached, so two loads of the same
    hand-built model yield instances of one class rather than two classes
    that compare unequal by type (WP-V5 review gate, LOW 7). Bounded because
    the name is caller-supplied; 16 is far above the registry and any test.
    """
    return type(
        f"GeoidGrid_{model_name}", (GeoidGrid,), {"dialect": _dialect_for(model_name)}
    )


def _grid_class_for(model: GeoidModel) -> type[GeoidGrid]:
    """The grid kind whose refusals name this model.

    A registry model gets its declared class. A hand-built record - a test
    exercising the loader against some other tile - gets a cached per-name
    subclass carrying its own name, so even then no refusal misnames the grid
    it is refusing.
    """
    known = _GRID_CLASS_BY_MODEL_NAME.get(model.name)
    if known is not None:
        return known
    return _grid_class_for_name(model.name)


def _require_geoid_model_record(model: object, where: str) -> None:
    """Refuse a non-``GeoidModel`` by name - the #11-finding-1 guard.

    This program's core records all carry ``name`` and ``citation``, so a
    ``Zone``, a ``ReferenceFrame`` or a ``VerticalDatum`` duck-types a long way
    into a loader before failing on some attribute several calls deep - and the
    likeliest impostor here is ``True``, because this argument replaced
    ``apply_geoid: bool`` (WP-V5). if/raise, never assert: the suite and the
    shipped program run under ``-O``.
    """
    if not isinstance(model, GeoidModel):
        raise TypeError(
            f"{where} needs a michspc.fileio.geoid.GeoidModel record; got "
            f"{type(model).__name__} ({model!r}). In particular True is not "
            f"'the default model' - that was apply_geoid's contract, retired "
            f"by WP-V5. Pass GEOID18_MODEL, GEOID12B_MODEL, or a record from "
            f"geoid_model_by_name()."
        )


def load_grid(
    path: Path | None = None,
    verify_checksum: bool = False,
    expect_geometry: TileGeometry | None = None,
    model: GeoidModel | None = None,
) -> GeoidGrid:
    """Read an NGS geoid binary tile.

    ``model`` names the geoid model the file is being read as; it decides what
    the refusals call the grid, which digest ``verify_checksum`` compares
    against, and which default path is read. Omitted, it is GEOID18 - the
    signature every pre-registry caller already uses.

    ``verify_checksum`` re-hashes the whole 4.7 MB file against the model's
    pinned SHA-256. ``expect_geometry`` additionally requires the header to
    describe a named, known tile; without it only the format-level checks that
    hold for any NGS grid are applied, so this function stays usable for a
    different tile.

    The production path passes both. See ``load_shipped_grid``.
    """
    if model is not None:
        _require_geoid_model_record(model, "load_grid")
    model = model or GEOID18_MODEL
    path = path or DATA_DIR / model.tile_filename
    grid_class = _grid_class_for(model)
    dialect = grid_class.dialect

    try:
        raw = path.read_bytes()
    except OSError as error:
        raise GeoidError(
            f"Could not read the {model.name} grid at {path}: {error}. "
            f"This file ships with the program; if it is missing the "
            f"installation is incomplete."
        ) from error

    if len(raw) < ngs_grid.HEADER_BYTES:
        raise GeoidError(
            f"{path} is only {len(raw)} bytes, too short to contain the "
            f"{ngs_grid.HEADER_BYTES}-byte {model.name} header. The file is "
            f"truncated or is not a geoid grid."
        )

    if verify_checksum:
        digest = hashlib.sha256(raw).hexdigest()
        if digest != model.sha256:
            raise GeoidError(
                f"{path} does not match the {model.name} grid this "
                f"program was built against.\n  expected SHA-256 "
                f"{model.sha256}\n  found    SHA-256 {digest}\n"
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

    ngs_grid.require_supported_ikind(dialect, path, header.ikind)

    ngs_grid.require_readable_header(
        dialect, path, south, west, dlat, dlon, rows, columns
    )

    if expect_geometry is not None:
        ngs_grid.require_canonical_geometry(
            dialect, path, expect_geometry, south, west, dlat, dlon, rows, columns
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
    ngs_grid.require_finite_payload(dialect, path, values)

    return grid_class(
        path=path,
        south_latitude=south,
        west_longitude=west,
        latitude_spacing=dlat,
        longitude_spacing=dlon,
        row_count=rows,
        column_count=columns,
        values=values,
    )


def load_shipped_grid(
    path: Path | None = None, model: GeoidModel = GEOID18_MODEL
) -> GeoidGrid:
    """Load a tile this program ships, fully authenticated.

    This is the production policy in one place: the SHA-256 must match the
    model record's pinned digest of the unmodified NGS file, **and** the header
    must describe the geometry that record says the tile has. Two independent
    gates, because they fail differently - the checksum catches any altered
    byte, the geometry check catches a file that is internally consistent and
    still describes the wrong grid.

    Takes a path only so the checks themselves can be exercised against a
    deliberately tampered copy in a test. Nothing in the program passes one.
    """
    _require_geoid_model_record(model, "load_shipped_grid")
    return load_grid(
        path or DATA_DIR / model.tile_filename,
        verify_checksum=True,
        expect_geometry=model.geometry,
        model=model,
    )


@lru_cache(maxsize=8)
def _cached_shipped_grid(model: GeoidModel) -> GeoidGrid:
    """One authenticated load per model per process. See ``default_grid``.

    Bounded at 8, not ``None``: ``default_grid`` is public and accepts any
    ``GeoidModel``, so "bounded in practice by the registry" was a claim the
    registry could not enforce - a caller looping over hand-built records
    would have grown it without limit (WP-V5 review gate, LOW 7). Eight is
    four times the registry; evicting beyond that trades a 32 ms reload for
    a bound.
    """
    return load_shipped_grid(model=model)


def default_grid(model: GeoidModel = GEOID18_MODEL) -> GeoidGrid:
    """A shipped tile, loaded once per model per process.

    A file of several thousand points would otherwise re-read and re-unpack
    4.7 MB per row. The cache is keyed on the model RECORD (hashable because
    ``GeoidModel`` and everything it carries are frozen), and it lives on the
    inner ``_cached_shipped_grid`` rather than on this function so that
    ``default_grid()`` and ``default_grid(GEOID18_MODEL)`` are one cache entry,
    not two separate loads of the same 4.7 MB - ``lru_cache`` keys on the
    arguments actually passed, and a defaulted argument is not passed.

    **Authenticated.** This is the path production actually takes, so it takes
    the checked one: it hashes the file and validates the header geometry
    (``load_shipped_grid``). The gate previously ran only in the test suite and
    the frozen bundle's self-test, which left the running program trusting
    whatever bytes were on disk - the interim review gate's finding 6
    (docs/DESIGN.md amendment #11).

    The cost is paid once per model per process and measured, not assumed:
    reading and hashing the 4,933,728-byte file takes about 3.5 ms, against
    about 22 ms to unpack the same payload into floats - work this loader
    already did - and about 32 ms for the whole cold load. The check is roughly
    a tenth of the load it protects, and the load happens once no matter how
    many points a file holds.
    """
    return _cached_shipped_grid(model)


# The suite clears the cache around monkeypatched loads; keep that surface on
# the public name it has always been cleared through.
default_grid.cache_clear = _cached_shipped_grid.cache_clear
default_grid.cache_info = _cached_shipped_grid.cache_info


def require_geoid_matches_datum(
    model: GeoidModel, target_datum: VerticalDatum
) -> None:
    """Refuse a geoid model applied against heights in a datum it is not for.

    DESIGN.md #32's rule: an elevation factor built from a height in one
    vertical datum and a geoid separation defined against another mixes two
    eras inside one number - the number looks exact and cites nothing.

    **This is the one-datum primitive; production applies a rule DERIVED from
    it, not this function.** The WP-V6 review gate showed that comparing the
    model against the job's *target* datum alone (plan section 3.5's rule)
    would refuse NAVD88 -> NGVD29 outright with advice nothing offers, so
    ``job.run`` widened it: the model's datum must match EITHER endpoint of
    the vertical conversion, and the factors are computed from the height in
    the model's own era (DESIGN.md #41). This primitive remains for callers
    that genuinely have one height in one datum - the shape the GEOID2022 /
    NAPGD2022 era will need - and its refusal teaches the same rule.

    Compared by ``code`` rather than object identity, the rule the vertical
    registry already follows, so a datum record rebuilt from a saved job still
    matches. The isinstance guards are the #11-finding-1 refusal: every core
    record carries ``name`` and ``citation``, so a ``Zone`` or a
    ``ReferenceFrame`` would otherwise duck-type deep into the comparison and
    fail as an ``AttributeError`` nobody catches.
    """
    _require_geoid_model_record(model, "require_geoid_matches_datum")
    if not isinstance(target_datum, VerticalDatum):
        raise TypeError(
            f"require_geoid_matches_datum needs a michspc.spc.vertical."
            f"VerticalDatum as its target_datum; got "
            f"{type(target_datum).__name__} ({target_datum!r}). Every record "
            f"in this program carries name and citation, so a zone, a "
            f"reference frame or a geoid model reaches this function without "
            f"complaint and would be asked which vertical datum it is. Pass "
            f"michspc.spc.vertical.NAVD88 or NGVD29."
        )

    if model.vertical_datum.code != target_datum.code:
        raise GeoidError(
            f"The {model.name} geoid model publishes separations for "
            f"{model.vertical_datum.name} ({model.vertical_datum.code}) "
            f"heights, and this job's elevations are "
            f"{target_datum.name} ({target_datum.code}). Applying it would put "
            f"two eras inside one number: an elevation factor whose H is "
            f"{target_datum.code} and whose N is {model.vertical_datum.code} "
            f"looks exact and is neither (docs/DESIGN.md amendment #32). "
            f"Use a height in {model.vertical_datum.code}, or apply no geoid "
            f"model, in which case the elevation-dependent factors read N/A "
            f"rather than mixing eras. "
            + (
                f"Models published for {target_datum.code} heights: "
                f"{', '.join(alternatives)}."
                if (
                    alternatives := [
                        m.name
                        for m in ALL_GEOID_MODELS
                        if m.vertical_datum.code == target_datum.code
                    ]
                )
                else f"No geoid model in this program's registry is "
                f"published for {target_datum.code} heights - the advice "
                f"above is the whole of the way forward."
            )
        )


def geoid_height(latitude: float, longitude: float, grid: GeoidGrid | None = None) -> float:
    """Geoid height at a position, meters, negative in Michigan.

    Uses biquadratic interpolation on a 3x3 stencil anchored at the nearest
    node - the scheme AND the anchoring of NGS's own INTG program. See
    docs/DESIGN.md amendment #8 for the evidence behind the scheme, #36 for
    the discovery that the anchoring shipped wrong for three releases, and #37
    for the re-anchoring (WP-G1) and the anchors that gate it.
    """
    grid = grid or default_grid()
    return grid.height_biquadratic(latitude, longitude)
