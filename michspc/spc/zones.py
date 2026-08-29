"""Zone registry.

Zones are *data*, not code. **SPCS2022 arrived exactly that way**: nineteen
records added below, each with its citation, and not one line of new
mathematics - the engines the 2022 zones dispatch to were built separately
(michspc.spc.projection, and DESIGN.md amendment #21). See docs/DESIGN.md
section 6.

Two eras live here, and they are kept apart by name:

    SPCS83_ZONES     Michigan's three 1983 zones, on NAD83(2011)
    SPCS2022_ZONES   Michigan's nineteen 2022 zones, on NATRF2022
    ALL_ZONES        both, derived by concatenation

A conversion between the eras crosses reference frames and is refused
(michspc.spc.frames) until a transformation is implemented. Nothing in this
module decides that; it is stated here because the two tuples are otherwise
easy to read as a display choice, and they are not.

Every SPCS 83 constant is transcribed from NOAA Manual NOS NGS 5, Appendix A
(PDF p. 77) and Appendix C (PDF pp. 103-104); every SPCS2022 constant from
NGS's own zoneDefinitions.json, frozen and digest-pinned (see the section
heading above SPCS2022_ZONES). Appendix C also publishes the *derived*
constants for each zone; those are deliberately NOT stored here. They are held
in tests/fixtures as verification anchors, so that the derivation in lambert.py
is checked against NGS's published values rather than merely agreeing with a
copy of them kept alongside it - and the 2022 records are cross-checked against
the frozen capture the same way.

Longitude convention: **all longitudes in this codebase are signed, negative
west.** The manual prints central meridians as positive-west (Michigan North is
"87:00" there, meaning 87 degrees WEST). The conversion happens here, once, at
transcription time. See docs/DESIGN.md section 7.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from michspc.spc.frames import NAD83_2011, NATRF2022, ReferenceFrame
from michspc.spc.units import INTERNATIONAL_FEET, METERS, US_SURVEY_FEET, LinearUnit


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

    allowed_units: tuple[LinearUnit, ...]
    """The linear units a job in this zone may be read or written in.

    Not a preference and not a display filter: a unit absent from this tuple is
    one the publishing authority does not define coordinates in for this zone,
    and offering it would mean writing a number in a unit nobody can check the
    zone's own published false origins against.

    A TUPLE, not a set or a list, for two reasons that are both load-bearing:
    ``Zone`` must stay hashable, because ``projection.constants_for`` caches on
    the zone itself; and the order is the order an interface offers, so it is a
    user-visible fact rather than an accident of iteration.

    SPCS 83 carries all three units. SPCS2022 carries metres and International
    feet only - see the citation on each 2022 record.
    """

    easting_range_m: tuple[float, float] | None
    """(lowest, highest) easting a coordinate in this zone can plausibly have,
    metres - or ``None`` for a zone with no published or derivable range.

    Read by ``michspc.spc.convert.easting_looks_wrong_for_zone``, which warns
    when a file's eastings fall outside it. Selecting the wrong source zone is
    the most likely real-world mistake with this program, and an easting is the
    cheapest thing to notice it in.

    The two eras get their range from different places, and both are recorded
    on the zone rather than computed in ``convert``:

    * **SPCS 83** derives it, +/- 400 km about the zone's false easting. The
      1983 design put Michigan's three false eastings 2,000,000 m apart
      precisely so a coordinate reveals its own zone (manual PDF p. 18), and no
      point in a zone lies more than about 200 km from its central meridian, so
      400 km flags a mismatched zone without ever flagging a legitimate point.
    * **SPCS2022** does not derive it - NGS PUBLISHES it, per zone, projected
      outward from the zone polygon (``zoneBounds.json``). That is strictly
      better than any window this program could invent, and it is why this
      field is a range rather than a half-width: the published bounds are not
      symmetric about the false easting.

    ``None`` is not "unset" - it is the recorded absence of any usable range,
    and it switches the check off rather than inventing a threshold that would
    fire on legitimate points. No zone in the registry carries it today; the
    branch is kept, contracted and pinned, because the next authority to
    publish a zone may not publish bounds for it.

    A TUPLE, so ``Zone`` stays hashable for ``projection.constants_for``'s
    cache. Never a refusal in any case (docs/DESIGN.md amendment #1).
    """

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

_SPCS83_UNITS: tuple[LinearUnit, ...] = (INTERNATIONAL_FEET, US_SURVEY_FEET, METERS)
"""What an SPCS 83 job may be read or written in, in the order offered.

Michigan legislated the International foot (NOAA Manual NOS NGS 5, Table 1.5,
PDF p. 19, "Michigan(I)"), which is why it leads; the US survey foot is here
because legacy Michigan data is in it, and metres because the defining
constants and NGS's own publication are metric (manual PDF pp. 21-22). This is
the offering the program has had since 0.1.0, written down on the record rather
than assumed from ``units.ALL_UNITS`` - the 2022 zones do NOT carry all three,
so "every unit this program knows" stopped being the same statement as "every
unit this zone may be expressed in".
"""

_SPCS83_EASTING_WINDOW_M = 400000.0
"""Half-width of the easting range for an SPCS 83 zone, metres.

Michigan's three false eastings are 2,000,000 m apart precisely so a coordinate
reveals its own zone (manual PDF p. 18: "Selecting different grid origins ... so
the coordinate user could determine the zone from the magnitude of the
coordinate"), and no point in a zone lies more than about 200 km from its
central meridian, so 400 km flags a mismatched zone without ever flagging a
legitimate point. Held here rather than in ``convert.py`` because it is a
property of the 1983 zone design; NGS publishes the 2022 zones' ranges outright
and this number has nothing to do with them.
"""


def _spcs83_easting_range(easting_origin: float) -> tuple[float, float]:
    """The +/- 400 km range about an SPCS 83 zone's false easting.

    The arithmetic lives here so it appears once rather than three times. The
    false easting is named again at the call site, which is a second copy of a
    number the definition record already holds - so the import-time check
    ``_check_every_easting_range_brackets_its_false_easting`` proves the two
    agree, and would refuse the module if a hand edit moved one and not the
    other.
    """
    return (easting_origin - _SPCS83_EASTING_WINDOW_M,
            easting_origin + _SPCS83_EASTING_WINDOW_M)

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
    allowed_units=_SPCS83_UNITS,
    easting_range_m=_spcs83_easting_range(8000000.0),  # Eo from the definition above
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
    allowed_units=_SPCS83_UNITS,
    easting_range_m=_spcs83_easting_range(6000000.0),  # Eo from the definition above
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
    allowed_units=_SPCS83_UNITS,
    easting_range_m=_spcs83_easting_range(4000000.0),  # Eo from the definition above
    lat_min=41.6,
    lat_max=44.3,
    lon_min=-87.0,
    lon_max=-82.3,
)


SPCS83_ZONES: tuple[Zone, ...] = (MI_NORTH, MI_CENTRAL, MI_SOUTH)
"""Michigan's three State Plane Coordinate System of 1983 zones, north to south.

The era tuples exist because "every zone" stopped being one statement when
SPCS2022 arrived. A property that is true of the 1983 design - two standard
parallels, NAD83(2011), false eastings two million metres apart, all three
linear units - is not true of the 2022 design, and a test parametrized over the
whole registry would either fail or have to be weakened to the intersection.
Each caller names the era it means (docs/DESIGN.md amendment #21).
"""


# --------------------------------------------------------------------------
# Michigan, SPCS2022. Nineteen zones on NATRF2022: one statewide Hotine
# oblique Mercator, and eighteen low-distortion projections - thirteen Lambert
# conformal conic with one parallel (NGS's LC1) and five transverse Mercator
# (TM).
#
# **None of the three SPCS 83 zones above survives into SPCS2022.** The 2022
# design is not a re-realization of the 1983 zones; it is a different set of
# projections with different origins, and a 1983 coordinate is not a 2022
# coordinate of the same point.
#
# Defining constants: NGS's own zoneDefinitions.json, frozen at
# review/nsrs-n0/raw/zoneDefinitions.json (632,927 bytes, SHA-256
# f222dac669503c8e25eb41d477bbb129b813b894b43e7d012effb9dc00bbc06a,
# Last-Modified 2026-06-01, captured 2026-08-28 from
# https://beta.ngs.noaa.gov/SPCS/json_data/zoneDefinitions.json). The nineteen
# Michigan rows are tabulated in review/nsrs-n0/FINDINGS.md section 6 and
# extracted verbatim to review/nsrs-n0/raw/spcs/michigan_zones.json. NGS's
# zone-definitions page states: "All parameters are exact values, except for
# the North Carolina Zone (370001) false northing and easting in international
# feet" - so every defining figure below is exact, not rounded.
#
# Bounds (the ``extent=`` and ``easting_range_m=`` arguments): NGS's own
# zoneBounds.json, frozen at review/nsrs-n0/raw/zoneBounds.json (654,390 bytes,
# SHA-256 040f9d5a6e4af2587cb8306d05829a0efefd17a482b37f55678e4ea861f48b66,
# captured 2026-08-29 from
# https://beta.ngs.noaa.gov/SPCS/json_data/zoneBounds.json). **These are NGS
# figures, not a convention of this program** - the page says they were
# "computed outward from the zone polygon to 0.01 degree precision using floor
# and ceiling functions", and the easting bounds "are based on projected
# bounding boxes to account for parallel curvature and meridian convergence and
# were computed outward to 100 m ... precision". They are ROUNDED OUTWARD by
# construction, which is the right direction for a warning aid: a point inside
# the published area never trips it.
#
# Every bound is transcribed as a literal with the file's own value in the
# comment beside it, and every one is cross-checked against the frozen file in
# tests/test_zone_registry.py.
#
# **NGS BETA.** Every constant here is pre-release and carries a re-freeze
# obligation against NGS's official SPCS2022 release: re-run the capture, and
# any changed digest means new records and a full gate cycle.
#
# tests/test_zone_registry.py parses the frozen capture and cross-checks every
# field below against it, so this transcription cannot merely agree with a copy
# kept beside it - the same rule Appendix C's derived constants follow.
# --------------------------------------------------------------------------

_SPCS2022_SYSTEM = "SPCS2022"
"""NGS's own spelling, solid - "State Plane Coordinate System of 2022",
abbreviated SPCS2022 throughout https://beta.ngs.noaa.gov/SPCS/ (captured
2026-08-28). Not "SPCS 2022": the 1983 system's spelling has the space
("SPCS 83") and the 2022 system's does not, and the two strings are what an
audit column and a job record print.
"""

_SPCS2022_UNITS: tuple[LinearUnit, ...] = (INTERNATIONAL_FEET, METERS)
"""What an SPCS2022 job may be read or written in. **No US survey foot.**

Two independent NGS facts, both captured at N0 (review/nsrs-n0/FINDINGS.md
sections 1.4 and 6):

* zoneDefinitions.json publishes each 2022 zone's false origin in metres and
  international feet ONLY - the columns are ``False northing (m)``,
  ``False easting (m)``, ``False northing (ift)``, ``False easting (ift)``, and
  there is no US-survey-foot column for any of the 953 zones; and
* beta NCAT prints ``N/A`` for usft on every SPCS2022 zone, while printing a
  usft coordinate for the SPCS 83 zone it auto-picked in the same session.

NGS's zone-information page adds the design reason: "Many grid origin metric
values (false northings and eastings) have been updated such that the
international foot values are exact whole numbers ... See section 6.f.v of the
SPCS2022 Procedures." Every Michigan 2022 false origin below is an exact whole
number of international feet; none is a whole number of US survey feet. Writing
a 2022 coordinate in survey feet would produce a number no published NGS figure
can be checked against, and the survey foot is 2 ppm from the international
foot - about 26 feet at a four-million-metre easting.
"""

_SPCS2022_CITATION = (
    "NOAA Special Publication NOS NGS 13, 'The State Plane Coordinate System: "
    "History, Policy, & Future Directions' (Dennis, 2018), and the SPCS2022 "
    "Procedures it is implemented under; defining constants from NGS's "
    "zoneDefinitions.json, "
    "https://beta.ngs.noaa.gov/SPCS/json_data/zoneDefinitions.json, captured "
    "2026-08-28, 632,927 bytes, SHA-256 f222dac669503c8e25eb41d477bbb129b813b"
    "894b43e7d012effb9dc00bbc06a, frozen at "
    "review/nsrs-n0/raw/zoneDefinitions.json; zone bounds from NGS's "
    "zoneBounds.json, "
    "https://beta.ngs.noaa.gov/SPCS/json_data/zoneBounds.json, captured "
    "2026-08-29, 654,390 bytes, SHA-256 040f9d5a6e4af2587cb8306d05829a0efefd1"
    "7a482b37f55678e4ea861f48b66, frozen at "
    "review/nsrs-n0/raw/zoneBounds.json. NGS beta"
)
"""The shared half of every 2022 zone's citation; each record names its own row.

TWO captures, because a 2022 record carries two independent kinds of NGS fact -
the defining constants a coordinate is computed from, and the published bounds
the extent and easting warnings are measured against. Both are named, both
digest-pinned, both dated, and both carry the ``NGS beta`` token the re-freeze
mechanism looks for, because both are pre-release.
"""


def _spcs2022_citation(code: str) -> str:
    """This zone's citation: the shared sources, plus the row it was read from.

    One row number covers both files: ``zoneBounds.json`` is keyed by the same
    ``Zone code``, which the cross-check test verifies rather than assumes.
    """
    return f"{_SPCS2022_CITATION}, row 'Zone code' {code}"


def _spcs2022_zone(
    code: str,
    abbrev: str,
    name: str,
    definition: ProjectionDef,
    extent: tuple[float, float, float, float],
    easting_range_m: tuple[float, float],
) -> Zone:
    """One SPCS2022 zone record, with the parts all nineteen share filled in.

    Those parts are facts about the 2022 design rather than about the zone -
    the frame, the system spelling, the unit restriction and the citation - so
    each is written once here instead of nineteen times below, where nineteen
    copies could disagree.

    **Everything that differs per zone is passed in, and nothing is derived.**
    ``extent`` is ``(lat_min, lat_max, lon_min, lon_max)`` and
    ``easting_range_m`` is ``(lowest, highest)``, both transcribed from NGS's
    published ``zoneBounds.json`` at the call site with the source values in a
    comment. Neither has a default: a zone added without bounds must fail to
    construct rather than quietly inherit somebody else's.
    """
    lat_min, lat_max, lon_min, lon_max = extent

    return Zone(
        code=code,
        abbrev=abbrev,
        name=name,
        system=_SPCS2022_SYSTEM,
        frame=NATRF2022,
        definition=definition,
        citation=_spcs2022_citation(code),
        allowed_units=_SPCS2022_UNITS,
        easting_range_m=easting_range_m,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
    )


SPCS2022_ZONES: tuple[Zone, ...] = (
    # ------------------------------------------------------------------
    # The statewide zone. NGS's ``Zone type`` is "Statewide", ``Design by``
    # is "NGS" (every other Michigan zone is designed by the State), and it
    # is the only Michigan zone in any era that is not a Lambert or a
    # transverse Mercator.
    #
    # The skew azimuth is the only signed angle in the file, and NGS
    # publishes it once: -26 degrees. It is NOT a longitude, so this
    # codebase's negative-west convention does not touch it (see
    # ObliqueMercatorCenterDef.skew_azimuth).
    # ------------------------------------------------------------------
    _spcs2022_zone(
        code="260001",
        abbrev="MI",
        name="Michigan",
        definition=ObliqueMercatorCenterDef(
            lat_center=dms(45, 0),  # 45 deg 00' N = 45.0
            lon_center=-dms(86, 0),  # 86 deg 00' W = -86.0
            skew_azimuth=-26.0,  # "Skew azimuth (deg)" = -26
            k_center=0.999800,  # "Projection origin scale"
            northing_center=762000.0,  # "False northing (m)" = 762,000
            easting_center=1524000.0,  # "False easting (m)" = 1,524,000
        ),
        # zoneBounds.json: 41.69 to 48.31 lat, -90.42 to -82.12 lon west
        extent=(41.69, 48.31, -90.42, -82.12),
        # zoneBounds.json: easting 1,155,800 to 1,847,000 m
        easting_range_m=(1155800.0, 1847000.0),
    ),
    # ------------------------------------------------------------------
    # The eighteen low-distortion zones, in NGS's own code order. Each
    # zone's own scale factor is published AT its origin and is at or above
    # 1 - that is what makes them low-distortion designs: the projection
    # surface sits above the ellipsoid at the design height rather than
    # cutting through it.
    #
    # Four of the eighteen grid origins lie outside Michigan (261002 at
    # 40 deg 12' N is in Ohio; 261014, 261015 and 261016 are over Lake
    # Michigan or Wisconsin). They are grid origins, not places.
    # ------------------------------------------------------------------
    _spcs2022_zone(
        code="261001",
        abbrev="MI_L11A",
        name="Michigan Ann Arbor",
        definition=TransverseMercatorDef(
            lat_grid_origin=dms(41, 18),  # 41 deg 18' N = 41.3
            lon_origin=-dms(84, 6),  # 84 deg 06' W = -84.1
            k_origin=1.000022,
            northing_grid_origin=0.0,  # 0
            easting_origin=381000.0,  # 381,000
        ),
        # zoneBounds.json: 41.69 to 42.79 lat, -84.83 to -83.53 lon west
        extent=(41.69, 42.79, -84.83, -83.53),
        # zoneBounds.json: easting 320,200 to 428,500 m
        easting_range_m=(320200.0, 428500.0),
    ),
    _spcs2022_zone(
        code="261002",
        abbrev="MI_L15D",
        name="Michigan Detroit",
        definition=TransverseMercatorDef(
            lat_grid_origin=dms(40, 12),  # 40 deg 12' N = 40.2
            lon_origin=-dms(83, 9),  # 83 deg 09' W = -83.15
            k_origin=1.000024,
            northing_grid_origin=0.0,  # 0
            easting_origin=495300.0,  # 495,300
        ),
        # zoneBounds.json: 41.72 to 42.90 lat, -83.78 to -82.70 lon west
        extent=(41.72, 42.90, -83.78, -82.70),
        # zoneBounds.json: easting 442,800 to 532,800 m
        easting_range_m=(442800.0, 532800.0),
    ),
    _spcs2022_zone(
        code="261003",
        abbrev="MI_L21F",
        name="Michigan Flint",
        definition=LambertOneParallelDef(
            lat_origin=dms(42, 54),  # 42 deg 54' N = 42.9
            k_origin=1.000026,
            lon_origin=-dms(83, 24),  # 83 deg 24' W = -83.4
            northing_grid_origin=76200.0,  # 76,200
            easting_origin=685800.0,  # 685,800
        ),
        # zoneBounds.json: 42.47 to 43.33 lat, -84.37 to -82.33 lon west
        extent=(42.47, 43.33, -84.37, -82.33),
        # zoneBounds.json: easting 606,000 to 773,800 m
        easting_range_m=(606000.0, 773800.0),
    ),
    _spcs2022_zone(
        code="261004",
        abbrev="MI_L25S",
        name="Michigan Saginaw",
        definition=LambertOneParallelDef(
            lat_origin=dms(43, 36),  # 43 deg 36' N = 43.6
            k_origin=1.000012,
            lon_origin=-dms(83, 39),  # 83 deg 39' W = -83.65
            northing_grid_origin=228600.0,  # 228,600
            easting_origin=723900.0,  # 723,900
        ),
        # zoneBounds.json: 43.12 to 44.18 lat, -84.61 to -82.12 lon west
        extent=(43.12, 44.18, -84.61, -82.12),
        # zoneBounds.json: easting 645,700 to 848,500 m
        easting_range_m=(645700.0, 848500.0),
    ),
    _spcs2022_zone(
        code="261005",
        abbrev="MI_L31R",
        name="Michigan Roscommon",
        definition=LambertOneParallelDef(
            lat_origin=dms(44, 15),  # 44 deg 15' N = 44.25
            k_origin=1.000029,
            lon_origin=-dms(84, 9),  # 84 deg 09' W = -84.15
            northing_grid_origin=76200.0,  # 76,200
            easting_origin=990600.0,  # 990,600
        ),
        # zoneBounds.json: 43.81 to 44.52 lat, -85.09 to -82.24 lon west
        extent=(43.81, 44.52, -85.09, -82.24),
        # zoneBounds.json: easting 914,900 to 1,144,300 m
        easting_range_m=(914900.0, 1144300.0),
    ),
    _spcs2022_zone(
        code="261006",
        abbrev="MI_L35T",
        name="Michigan Thunder Bay",
        definition=LambertOneParallelDef(
            lat_origin=dms(44, 51),  # 44 deg 51' N = 44.85
            k_origin=1.000031,
            lon_origin=-dms(84, 3),  # 84 deg 03' W = -84.05
            northing_grid_origin=190500.0,  # 190,500
            easting_origin=1028700.0,  # 1,028,700
        ),
        # zoneBounds.json: 44.50 to 45.22 lat, -84.86 to -82.32 lon west
        extent=(44.50, 45.22, -84.86, -82.32),
        # zoneBounds.json: easting 964,200 to 1,166,300 m
        easting_range_m=(964200.0, 1166300.0),
    ),
    _spcs2022_zone(
        code="261007",
        abbrev="MI_L41Z",
        name="Michigan Kalamazoo",
        definition=LambertOneParallelDef(
            lat_origin=dms(42, 6),  # 42 deg 06' N = 42.1
            k_origin=1.000024,
            lon_origin=-dms(85, 39),  # 85 deg 39' W = -85.65
            northing_grid_origin=76200.0,  # 76,200
            easting_origin=1333500.0,  # 1,333,500
        ),
        # zoneBounds.json: 41.75 to 42.43 lat, -87.21 to -84.70 lon west
        extent=(41.75, 42.43, -87.21, -84.70),
        # zoneBounds.json: easting 1,203,700 to 1,412,600 m
        easting_range_m=(1203700.0, 1412600.0),
    ),
    _spcs2022_zone(
        code="261008",
        abbrev="MI_L45G",
        name="Michigan Grand Rapids",
        definition=LambertOneParallelDef(
            lat_origin=dms(42, 48),  # 42 deg 48' N = 42.8
            k_origin=1.000018,
            lon_origin=-dms(85, 9),  # 85 deg 09' W = -85.15
            northing_grid_origin=228600.0,  # 228,600
            easting_origin=1409700.0,  # 1,409,700
        ),
        # zoneBounds.json: 42.41 to 43.30 lat, -87.11 to -84.14 lon west
        extent=(42.41, 43.30, -87.11, -84.14),
        # zoneBounds.json: easting 1,248,300 to 1,492,900 m
        easting_range_m=(1248300.0, 1492900.0),
    ),
    _spcs2022_zone(
        code="261009",
        abbrev="MI_L51N",
        name="Michigan Newaygo",
        definition=LambertOneParallelDef(
            lat_origin=dms(43, 27),  # 43 deg 27' N = 43.45
            k_origin=1.000025,
            lon_origin=-dms(85, 24),  # 85 deg 24' W = -85.4
            northing_grid_origin=76200.0,  # 76,200
            easting_origin=1638300.0,  # 1,638,300
        ),
        # zoneBounds.json: 43.11 to 43.83 lat, -87.15 to -84.36 lon west
        extent=(43.11, 43.83, -87.15, -84.36),
        # zoneBounds.json: easting 1,495,800 to 1,723,000 m
        easting_range_m=(1495800.0, 1723000.0),
    ),
    _spcs2022_zone(
        code="261010",
        abbrev="MI_L55W",
        name="Michigan Wexford",
        definition=LambertOneParallelDef(
            lat_origin=dms(44, 9),  # 44 deg 09' N = 44.15
            k_origin=1.000034,
            lon_origin=-dms(85, 33),  # 85 deg 33' W = -85.55
            northing_grid_origin=190500.0,  # 190,500
            easting_origin=1638300.0,  # 1,638,300
        ),
        # zoneBounds.json: 43.81 to 44.52 lat, -87.10 to -84.85 lon west
        extent=(43.81, 44.52, -87.10, -84.85),
        # zoneBounds.json: easting 1,513,500 to 1,694,700 m
        easting_range_m=(1513500.0, 1694700.0),
    ),
    _spcs2022_zone(
        code="261011",
        abbrev="MI_L61L",
        name="Michigan Leelanau",
        definition=LambertOneParallelDef(
            lat_origin=dms(44, 54),  # 44 deg 54' N = 44.9
            k_origin=1.000025,
            lon_origin=-dms(85, 27),  # 85 deg 27' W = -85.45
            northing_grid_origin=76200.0,  # 76,200
            easting_origin=1905000.0,  # 1,905,000
        ),
        # zoneBounds.json: 44.51 to 45.59 lat, -86.85 to -84.84 lon west
        extent=(44.51, 45.59, -86.85, -84.84),
        # zoneBounds.json: easting 1,793,600 to 1,953,600 m
        easting_range_m=(1793600.0, 1953600.0),
    ),
    _spcs2022_zone(
        code="261012",
        abbrev="MI_L65C",
        name="Michigan Cheboygan",
        definition=LambertOneParallelDef(
            lat_origin=dms(45, 27),  # 45 deg 27' N = 45.45
            k_origin=1.000025,
            lon_origin=-dms(84, 27),  # 84 deg 27' W = -84.45
            northing_grid_origin=190500.0,  # 190,500
            easting_origin=2019300.0,  # 2,019,300
        ),
        # zoneBounds.json: 45.11 to 45.89 lat, -85.88 to -82.49 lon west
        extent=(45.11, 45.89, -85.88, -82.49),
        # zoneBounds.json: easting 1,906,700 to 2,173,600 m
        easting_range_m=(1906700.0, 2173600.0),
    ),
    _spcs2022_zone(
        code="261013",
        abbrev="MI_U11M",
        name="Michigan Mackinac",
        definition=LambertOneParallelDef(
            lat_origin=dms(46, 12),  # 46 deg 12' N = 46.2
            k_origin=1.000011,
            lon_origin=-dms(84, 51),  # 84 deg 51' W = -84.85
            northing_grid_origin=76200.0,  # 76,200
            easting_origin=381000.0,  # 381,000
        ),
        # zoneBounds.json: 45.69 to 47.31 lat, -85.87 to -83.43 lon west
        extent=(45.69, 47.31, -85.87, -83.43),
        # zoneBounds.json: easting 301,500 to 491,700 m
        easting_range_m=(301500.0, 491700.0),
    ),
    _spcs2022_zone(
        code="261014",
        abbrev="MI_U21E",
        name="Michigan Escanaba",
        definition=TransverseMercatorDef(
            lat_grid_origin=dms(45, 9),  # 45 deg 09' N = 45.15
            lon_origin=-dms(86, 36),  # 86 deg 36' W = -86.6
            k_origin=1.000012,
            northing_grid_origin=0.0,  # 0
            easting_origin=685800.0,  # 685,800
        ),
        # zoneBounds.json: 45.32 to 47.82 lat, -87.37 to -85.85 lon west
        extent=(45.32, 47.82, -87.37, -85.85),
        # zoneBounds.json: easting 625,400 to 744,700 m
        easting_range_m=(625400.0, 744700.0),
    ),
    _spcs2022_zone(
        code="261015",
        abbrev="MI_U31Q",
        name="Michigan Marquette",
        definition=TransverseMercatorDef(
            lat_grid_origin=dms(44, 42),  # 44 deg 42' N = 44.7
            lon_origin=-dms(87, 36),  # 87 deg 36' W = -87.6
            k_origin=1.000038,
            northing_grid_origin=0.0,  # 0
            easting_origin=952500.0,  # 952,500
        ),
        # zoneBounds.json: 45.07 to 47.23 lat, -88.14 to -87.11 lon west
        extent=(45.07, 47.23, -88.14, -87.11),
        # zoneBounds.json: easting 909,900 to 991,100 m
        easting_range_m=(909900.0, 991100.0),
    ),
    _spcs2022_zone(
        code="261016",
        abbrev="MI_U41H",
        name="Michigan Houghton",
        definition=TransverseMercatorDef(
            lat_grid_origin=dms(45, 30),  # 45 deg 30' N = 45.5
            lon_origin=-dms(88, 24),  # 88 deg 24' W = -88.4
            k_origin=1.000042,
            northing_grid_origin=0.0,  # 0
            easting_origin=1295400.0,  # 1,295,400
        ),
        # zoneBounds.json: 45.92 to 47.65 lat, -89.48 to -87.11 lon west
        extent=(45.92, 47.65, -89.48, -87.11),
        # zoneBounds.json: easting 1,211,600 to 1,395,500 m
        easting_range_m=(1211600.0, 1395500.0),
    ),
    _spcs2022_zone(
        code="261017",
        abbrev="MI_U51B",
        name="Michigan Bessemer",
        definition=LambertOneParallelDef(
            lat_origin=dms(46, 42),  # 46 deg 42' N = 46.7
            k_origin=1.000036,
            lon_origin=-dms(89, 42),  # 89 deg 42' W = -89.7
            northing_grid_origin=114300.0,  # 114,300
            easting_origin=1600200.0,  # 1,600,200
        ),
        # zoneBounds.json: 46.09 to 47.72 lat, -90.42 to -88.86 lon west
        extent=(46.09, 47.72, -90.42, -88.86),
        # zoneBounds.json: easting 1,544,500 to 1,665,200 m
        easting_range_m=(1544500.0, 1665200.0),
    ),
    _spcs2022_zone(
        code="261018",
        abbrev="MI_U61K",
        name="Michigan Isle Royale",
        definition=LambertOneParallelDef(
            lat_origin=dms(48, 0),  # 48 deg 00' N = 48.0
            k_origin=1.000026,
            lon_origin=-dms(88, 51),  # 88 deg 51' W = -88.85
            northing_grid_origin=76200.0,  # 76,200
            easting_origin=1866900.0,  # 1,866,900
        ),
        # zoneBounds.json: 47.65 to 48.31 lat, -89.69 to -87.11 lon west
        extent=(47.65, 48.31, -89.69, -87.11),
        # zoneBounds.json: easting 1,803,700 to 1,997,700 m
        easting_range_m=(1803700.0, 1997700.0),
    ),
)
"""Michigan's nineteen SPCS2022 zones, in NGS's own order: the statewide
oblique Mercator first, then the eighteen low-distortion zones by zone code.

Order is a user-visible fact - it is the order a dropdown offers - so it is
NGS's, not this program's.
"""


ALL_ZONES: tuple[Zone, ...] = SPCS83_ZONES + SPCS2022_ZONES
"""Every zone in the registry, both eras. **Derived, never written out.**

A zone belongs to exactly one era tuple, and this is their concatenation, so a
zone cannot be added to one and forgotten in the other. Callers that mean one
era say so; ``zone_by_code`` and the uniqueness check below mean all of them.
"""


class ZoneRegistryError(ValueError):
    """The registry itself is malformed - raised at import, never at a job."""


_IDENTIFYING_FIELDS = ("code", "abbrev", "name")
"""The three strings that must identify a zone uniquely across BOTH eras.

Not just the code. ``abbrev`` names output files and audit columns and
``name`` is what the job record and every dropdown print, so a collision
between eras would produce two archives that overwrite each other, or a record
naming a zone the reader cannot resolve. The era cannot be appended as a suffix
to fix a collision after the fact either - the archive stems and audit column
headings are pinned byte-for-byte across versions - so the distinction has to
live in NGS's own strings, and this check is what proves it does.
"""


def _check_zone_identifiers_are_unique(zones: tuple[Zone, ...]) -> None:
    """Refuse to import if two zones share a code, an abbreviation or a name.

    Loud at startup beats quiet at the first job that resolved the wrong zone.
    if/raise rather than assert, because -O strips asserts. Takes the zones as
    an argument rather than reading the module global so the suite can hand it
    a deliberate collision and see it fire.
    """
    for field_name in _IDENTIFYING_FIELDS:
        seen: dict[str, Zone] = {}
        for zone in zones:
            value = getattr(zone, field_name)
            first = seen.get(value)
            if first is not None:
                raise ZoneRegistryError(
                    f"Two zones in the registry share the same {field_name} "
                    f"{value!r}: {first.name} ({first.code}, {first.system}) "
                    f"and {zone.name} ({zone.code}, {zone.system}). Every zone "
                    f"must be identifiable by its code, its abbreviation and "
                    f"its name alone, in every era at once: the abbreviation "
                    f"names output files and the name is what a job record "
                    f"prints, so a collision means two jobs that overwrite each "
                    f"other's archive or a record naming a zone that cannot be "
                    f"resolved. Use the publishing authority's own strings."
                )
            seen[value] = zone


_check_zone_identifiers_are_unique(ALL_ZONES)


def _check_every_easting_range_brackets_its_false_easting(
    zones: tuple[Zone, ...],
) -> None:
    """Refuse to import a zone whose easting range cannot contain its own origin.

    A coordinate ON the central meridian has exactly the false easting, so a
    range that excludes it would warn about every point in the middle of the
    zone - the warning firing hardest where it is least deserved. It also
    catches the two mistakes this field is actually exposed to: an SPCS 83 range
    typed about the wrong zone's false easting (the call site names the number a
    second time), and a 2022 range transcribed onto the wrong row.

    It is not a substitute for the cross-check against NGS's frozen file, which
    is what proves the published numbers were copied correctly; this is the
    cheap structural check that runs in the shipped program, at import, before
    any job. if/raise rather than assert, because -O strips asserts.

    Verified true of all nineteen published ranges at transcription time - NGS
    computes them outward from the zone polygon, which always contains the
    zone's own origin meridian.
    """
    for zone in zones:
        if zone.easting_range_m is None:
            continue
        lowest, highest = zone.easting_range_m
        origin = zone.definition.easting_origin
        if not lowest < highest:
            raise ZoneRegistryError(
                f"{zone.name} ({zone.code}) has the easting range "
                f"{zone.easting_range_m!r}, whose bounds are not in increasing "
                f"order. A transposed pair warns on every point instead of on "
                f"none."
            )
        if not lowest <= origin <= highest:
            raise ZoneRegistryError(
                f"{zone.name} ({zone.code}) has the easting range "
                f"{zone.easting_range_m!r}, which does not contain the zone's "
                f"own false easting of {origin!r} m. A point on the central "
                f"meridian has exactly that easting, so this range would warn "
                f"about the middle of the zone. Check the transcription against "
                f"the zone's row in NGS's zoneBounds.json."
            )


_check_every_easting_range_brackets_its_false_easting(ALL_ZONES)


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
