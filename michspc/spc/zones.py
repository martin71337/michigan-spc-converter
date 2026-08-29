"""Zone registry.

Zones are *data*, not code. A new coordinate system - SPCS2022 when NGS
finalizes it - arrives as records added here plus a citation, not as new
mathematics. See docs/DESIGN.md section 6.

Every constant in this module is transcribed from NOAA Manual NOS NGS 5,
Appendix A (PDF p. 77) and Appendix C (PDF pp. 103-104). Appendix C also
publishes the *derived* constants for each zone; those are deliberately NOT
stored here. They are held in tests/fixtures as verification anchors, so that
the derivation in lambert.py is checked against NGS's published values rather
than merely agreeing with a copy of them kept alongside it.

Longitude convention: **all longitudes in this codebase are signed, negative
west.** The manual prints central meridians as positive-west (Michigan North is
"87:00" there, meaning 87 degrees WEST). The conversion happens here, once, at
transcription time. See docs/DESIGN.md section 7.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from michspc.spc.frames import NAD83_2011, ReferenceFrame


def dms(degrees: int, minutes: int = 0, seconds: float = 0.0) -> float:
    """Degrees-minutes-seconds to decimal degrees, magnitude only.

    Appendix A gives standard parallels and central meridians in whole degrees
    and minutes. Writing them as ``dms(45, 29)`` rather than ``45.4833333``
    keeps the transcription checkable against the printed table at a glance.
    """
    return degrees + minutes / 60.0 + seconds / 3600.0


class ProjectionKind(Enum):
    """The conformal projections the State Plane systems are built from.

    SPCS 83 and SPCS2022 both draw from this set (manual chapter 3; SPCS2022
    uses the same three, in NGS's own abbreviations LC1, TM and OMC).

    **This enum is not stored on any record.** A definition record's Python type
    already says which projection it is, and a stored ``kind`` field beside it
    would be a second representation of the same fact, free to disagree with the
    engine actually dispatched to. The one type-to-kind mapping lives in
    ``michspc.spc.projection``'s dispatch table, which derives both the kind and
    the engine from the same entry; ``Zone.projection_kind`` reads it.
    """

    LAMBERT_CONIC_2SP = "Lambert conformal conic, two standard parallels"
    LAMBERT_CONIC_1SP = "Lambert conformal conic, central parallel and scale factor"
    TRANSVERSE_MERCATOR = "Transverse Mercator (Gauss-Kruger)"
    OBLIQUE_MERCATOR = "Hotine oblique Mercator"


@dataclass(frozen=True)
class LambertTwoParallelDef:
    """Lambert conformal conic defined by two standard parallels.

    This is the SPCS 83 form. The manual's symbols are given for each field so
    the transcription can be checked directly against Appendix A and C.
    """

    lat_south: float
    """phi_s / Bs - southern standard parallel, decimal degrees north."""

    lat_north: float
    """phi_n / Bn - northern standard parallel, decimal degrees north."""

    lat_grid_origin: float
    """phi_b / Bb - latitude of the grid origin, decimal degrees north."""

    lon_origin: float
    """lambda_0 / Lo - central meridian, decimal degrees, NEGATIVE WEST."""

    northing_grid_origin: float
    """N_b - northing assigned to the grid origin, meters ("false northing")."""

    easting_origin: float
    """E_0 - easting assigned to the central meridian, meters ("false easting")."""


@dataclass(frozen=True)
class LambertOneParallelDef:
    """Lambert conformal conic defined by a central parallel and its scale.

    NGS's SPCS2022 abbreviation is **LC1**. The manual's section 3.1 equations
    are the same ones the two-parallel form uses; only the derivation of the
    zone constants differs (michspc.spc.lambert.LambertConstants.from_one_parallel),
    because here phi_0 and k_0 are *given* rather than solved for from a pair of
    standard parallels.

    The grid origin is the central parallel itself, which is why there is no
    separate ``lat_grid_origin`` field: the false northing is assigned at
    phi_0, so phi_b = phi_0 and R_b = R_0. Storing a second latitude that must
    always equal the first would be a fact with two representations.
    """

    lat_origin: float
    """phi_0 / Bo - the central (single standard) parallel, decimal degrees north.

    The DEFINING latitude of the projection. On the two-parallel form the same
    quantity is derived from phi_s and phi_n; here it is published.
    """

    k_origin: float
    """k_0 / ko - grid scale factor ON the central parallel, dimensionless.

    The DEFINING scale. On the two-parallel form it is derived and comes out
    just below 1; SPCS2022's low-distortion zones publish it, at or above 1.
    """

    lon_origin: float
    """lambda_0 / Lo - central meridian, decimal degrees, NEGATIVE WEST."""

    northing_grid_origin: float
    """N_b - northing assigned to the grid origin (= phi_0), meters."""

    easting_origin: float
    """E_0 - easting assigned to the central meridian, meters."""


@dataclass(frozen=True)
class TransverseMercatorDef:
    """Transverse Mercator (Gauss-Kruger), NGS's SPCS2022 abbreviation **TM**.

    Manual section 3.2 (PDF pp. 42-48); the symbols below are section 3.21's
    (PDF pp. 42-43). Computed by michspc.spc.tm.
    """

    lat_grid_origin: float
    """phi_0 / Bo - latitude of the grid origin, decimal degrees north.

    The manual's phi_0 for a transverse Mercator is the GRID ORIGIN latitude,
    not a standard parallel: it is the latitude at which the false northing is
    assigned, and it enters the equations only through S_0 = k_0 omega_0 r.
    """

    lon_origin: float
    """lambda_0 / CM - central meridian, decimal degrees, NEGATIVE WEST."""

    k_origin: float
    """k_0 - grid scale factor ON the central meridian, dimensionless."""

    northing_grid_origin: float
    """N_0 - northing assigned to the grid origin latitude, meters."""

    easting_origin: float
    """E_0 - easting assigned to the central meridian, meters."""


@dataclass(frozen=True)
class ObliqueMercatorCenterDef:
    """Hotine oblique Mercator, **false coordinates at the projection CENTRE**.

    NGS's SPCS2022 abbreviation is **OMC**, glossed on the zone-definitions page
    as "Hotine Oblique Mercator, center" - and the word *center* is the whole
    reason this record is named ``...CenterDef`` rather than ``...Def``. Manual
    section 3.3 (PDF pp. 48-52) presents the NATURAL-ORIGIN Hotine, whose false
    coordinates apply where the initial line crosses the equator; for Alaska
    zone 1 the manual's own equations put the projection centre at
    u = 6,968,872.111 m rather than at the false northing. Applying the natural-
    origin form to an OMC zone misplaces every point by thousands of kilometres,
    so the variant is part of the record's identity, not a footnote
    (review/nsrs-h1-manual/TM-OM-EXTRACTION.md section 2, and DESIGN.md #61's
    OMC gloss).

    Computed by michspc.spc.omerc.
    """

    lat_center: float
    """phi_c / Bc - latitude of the projection centre, decimal degrees north."""

    lon_center: float
    """lambda_c - longitude of the projection centre, decimal degrees,
    NEGATIVE WEST. The manual prints it positive-west; the conversion happens
    at transcription time, as it does for every other longitude here."""

    skew_azimuth: float
    """alpha_c - azimuth of the initial line at the centre, decimal degrees,
    clockwise from north, signed.

    An azimuth, not a longitude: it is unaffected by this codebase's
    negative-west longitude convention. It enters the mathematics twice - once
    defining the skew (section 3.33's sin alpha_0) and once as the rotation
    angle from the (u, v) skew axes to (N, E) (section 3.34). For Michigan's
    statewide zone NGS publishes the azimuth and the rectified-skew angle as the
    same -26 degrees, so this one field legitimately supplies both roles; see
    michspc.spc.omerc, which says so at the rotation."""

    k_center: float
    """k_c - grid scale factor AT the projection centre, dimensionless."""

    northing_center: float
    """N_c - northing assigned to the projection centre, meters."""

    easting_center: float
    """E_c - easting assigned to the projection centre, meters."""

    # ------------------------------------------------------------------
    # The structural contract every definition record satisfies: a central
    # longitude, a false easting and a false northing, under one set of names,
    # with one meaning. Three of the four records carry those names as fields;
    # this one names the same three quantities after the centre, because that
    # is what they are anchored to and calling them "origin" would misdescribe
    # the variant. The aliases below satisfy the contract without inventing a
    # second stored copy - each reads its own field.
    #
    # convert.py's easting-window check reads ``definition.easting_origin``
    # blind across the union, so this is load-bearing, not tidiness.
    # ------------------------------------------------------------------

    @property
    def lon_origin(self) -> float:
        """The zone's central longitude - here the centre's. NEGATIVE WEST."""
        return self.lon_center

    @property
    def easting_origin(self) -> float:
        """The zone's false easting - here assigned at the centre. Meters."""
        return self.easting_center

    @property
    def northing_grid_origin(self) -> float:
        """The zone's false northing - here assigned at the centre. Meters."""
        return self.northing_center


ProjectionDef = (
    LambertTwoParallelDef
    | LambertOneParallelDef
    | TransverseMercatorDef
    | ObliqueMercatorCenterDef
)
"""Every projection definition a Zone may carry.

The union is what ``michspc.spc.projection`` dispatches on. Adding a member
here without adding it to that module's table makes ``constants_for`` refuse by
name rather than compute something wrong.
"""


@dataclass(frozen=True)
class Zone:
    """One State Plane zone."""

    code: str
    """NGS zone number, e.g. "2113"."""

    abbrev: str
    """Short label used in output file names, e.g. "MI-S"."""

    name: str
    system: str
    """The coordinate system this zone belongs to, e.g. "SPCS 83"."""

    frame: ReferenceFrame
    definition: ProjectionDef
    citation: str

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    """Approximate geographic extent of the zone's intended area, used only to
    warn when a point falls well outside it. Never used in computation, and
    never a reason to refuse a conversion - a project legitimately straddling a
    zone boundary must still convert (docs/DESIGN.md amendment #1)."""

    @property
    def projection_kind(self) -> ProjectionKind:
        """Which projection this zone is, read from the one dispatch table.

        Derived, never stored. The table in ``michspc.spc.projection`` maps a
        definition record's type to its kind AND to the engine that computes it,
        in one entry, so the label a job record prints and the mathematics it
        describes cannot come apart. A zone whose definition type is not in the
        table refuses here with the same message ``constants_for`` gives, rather
        than reporting a plausible kind for a projection nothing can compute.

        Imported inside the property because ``projection`` imports this module
        for the definition types: the dependency runs one way at import time and
        the other way at call time, which is what keeps both modules importable
        on their own.
        """
        from michspc.spc.projection import projection_kind_for_definition

        return projection_kind_for_definition(self.definition)

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


# --------------------------------------------------------------------------
# Michigan, SPCS 83. All three zones are Lambert conformal conic.
#
# Defining constants: NOAA Manual NOS NGS 5, Appendix A (PDF p. 77) and
# Appendix C (PDF pp. 103-104), which agree with each other.
#
# Michigan legislated International feet as its foot unit (manual Table 1.5,
# PDF p. 19, "Michigan(I)"); the defining constants themselves are metric.
#
# Zone extents are the counties each zone covers, rounded outward to whole
# tenths of a degree. They are a warning aid only.
# --------------------------------------------------------------------------

_APPENDIX = "NOAA Manual NOS NGS 5, Appendix A (PDF p. 77) and Appendix C (PDF pp. 103-104)"

MI_NORTH = Zone(
    code="2111",
    abbrev="MI-N",
    name="Michigan North",
    system="SPCS 83",
    frame=NAD83_2011,
    definition=LambertTwoParallelDef(
        lat_south=dms(45, 29),  # Bs = 45:29
        lat_north=dms(47, 5),  # Bn = 47:05
        lat_grid_origin=dms(44, 47),  # Bb = 44:47
        lon_origin=-dms(87, 0),  # Lo = 87:00 west
        northing_grid_origin=0.0,  # Nb
        easting_origin=8000000.0,  # Eo
    ),
    citation=_APPENDIX,
    lat_min=45.0,
    lat_max=48.4,
    lon_min=-90.5,
    lon_max=-83.4,
)

MI_CENTRAL = Zone(
    code="2112",
    abbrev="MI-C",
    name="Michigan Central",
    system="SPCS 83",
    frame=NAD83_2011,
    definition=LambertTwoParallelDef(
        lat_south=dms(44, 11),  # Bs = 44:11
        lat_north=dms(45, 42),  # Bn = 45:42
        lat_grid_origin=dms(43, 19),  # Bb = 43:19
        lon_origin=-dms(84, 22),  # Lo = 84:22 west
        northing_grid_origin=0.0,  # Nb
        easting_origin=6000000.0,  # Eo
    ),
    citation=_APPENDIX,
    lat_min=43.5,
    lat_max=46.0,
    lon_min=-86.7,
    lon_max=-82.9,
)

MI_SOUTH = Zone(
    code="2113",
    abbrev="MI-S",
    name="Michigan South",
    system="SPCS 83",
    frame=NAD83_2011,
    definition=LambertTwoParallelDef(
        lat_south=dms(42, 6),  # Bs = 42:06
        lat_north=dms(43, 40),  # Bn = 43:40
        lat_grid_origin=dms(41, 30),  # Bb = 41:30
        lon_origin=-dms(84, 22),  # Lo = 84:22 west
        northing_grid_origin=0.0,  # Nb
        easting_origin=4000000.0,  # Eo
    ),
    citation=_APPENDIX,
    lat_min=41.6,
    lat_max=44.3,
    lon_min=-87.0,
    lon_max=-82.3,
)


ALL_ZONES: tuple[Zone, ...] = (MI_NORTH, MI_CENTRAL, MI_SOUTH)

_BY_CODE = {zone.code: zone for zone in ALL_ZONES}


def zone_by_code(code: str) -> Zone:
    """Look up a zone by its NGS zone number.

    Refuses an unknown code rather than guessing, and names what is available.
    """
    key = str(code).strip()
    try:
        return _BY_CODE[key]
    except KeyError:
        known = ", ".join(f"{z.code} ({z.name})" for z in ALL_ZONES)
        raise KeyError(
            f"No zone with code {code!r}. This program covers Michigan only; "
            f"known zones are: {known}."
        ) from None
