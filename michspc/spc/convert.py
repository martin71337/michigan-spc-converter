"""The conversion pipeline.

One point in, one immutable record out, carrying not just the answer but the
evidence for it: the geodetic pivot, both zones' convergence and scale factor,
and every warning raised along the way.

The pipeline shape (docs/DESIGN.md section 4):

    (source zone, N, E) --inverse--> geodetic --forward--> (target zone, N, E)

Both steps go through michspc.spc.projection, which dispatches on the zone's
own definition record to the engine for that projection - the rigorous Lambert
conformal conic equations of NOAA Manual NOS NGS 5 section 3.1 for every SPCS 83
zone, and sections 3.2 and 3.3 for the transverse and oblique Mercator zones.
Nothing here names an engine: a zone in a projection this program does not
implement refuses by name in the dispatcher rather than being computed by
whichever engine happened to be imported.

**On verification.** An earlier design computed every coordinate a second time
by the manual's section 3.4 polynomial coefficient method and cross-checked the
two at runtime. That engine was removed (docs/DESIGN.md amendment #14): it
carried NGS's own stated 0.5 mm fitting error, degraded to metres outside each
zone's fitted band, and required a special-case policy to stay quiet - which
made it a second thing to verify rather than a check. What verifies this code is
external and lives in the test suite: 27 frozen NGS NCAT anchors, and every
published Appendix C derived constant reproduced from the defining constants
alone.

All linear values in this module are meters. Unit conversion happens at the file
boundary, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from michspc.spc.frames import ReferenceFrame, require_same_frame
from michspc.spc.projection import forward as project_forward
from michspc.spc.projection import inverse as project_inverse
from michspc.spc.zones import Zone

# Half-width of the easting window used to notice that a file's coordinates do
# not belong to the zone the user selected. Michigan's three false eastings are
# 2,000,000 m apart, and no point in a zone lies more than about 200 km from its
# central meridian, so 400 km flags a mismatched zone without ever flagging a
# legitimate point.
_EASTING_WINDOW_M = 400000.0


class WarningCode(Enum):
    """Machine-readable warning kinds, so the report can group them."""

    OUTSIDE_ZONE_EXTENT = "outside-zone-extent"
    EASTING_UNLIKE_SELECTED_ZONE = "easting-unlike-selected-zone"
    GEOID_UNAVAILABLE = "geoid-unavailable"
    """A point carried a usable elevation but the geoid grid does not cover it.

    Raised by michspc.job, not by this module - nothing here reads a file - but
    the code lives with the others because a job's warnings are one list and
    the audit CSV and the job record group them by this one enum.

    Without it a geoid miss is silent: the elevation and combined factors read
    N/A exactly as they do for a blank Z column, and the job record then lists
    the point under "blank elevation field", which is a false statement about a
    point whose elevation was recorded perfectly well.
    """

    VERTICAL_SHIFT_UNAVAILABLE = "vertical-shift-unavailable"
    """A vertical job's point carried a usable elevation, but the VERTCON grid
    pair does not cover its position, so the elevation was NOT converted.

    Raised by michspc.job, like GEOID_UNAVAILABLE above. The horizontal
    coordinates are unaffected and stand; the point's output elevation is
    left blank rather than filled with the unshifted source-datum height,
    because an unconverted height printed in a Z column labelled with the
    target datum is exactly the ordinary-looking wrong number this program
    exists to refuse. VERTCON 3.0's CONUS grid covers all of Michigan
    (docs/PLAN-vertical-datums.md section 2.2), so this is only reachable for
    a point already far outside the zone extents - but "unreachable in
    practice" is not a reason to pass a height through silently when it is
    reached.
    """

    VERTICAL_SIGMA_UNAVAILABLE = "vertical-sigma-unavailable"
    """A vertical job's point was shifted, but no one-sigma uncertainty can be
    stated for the shift: the VERTCON error model interpolates below zero at
    the point's position, and a negative number is not an uncertainty
    (docs/DESIGN.md #36).

    Raised by michspc.job, like the two codes above. THE SHIFT ITSELF IS VALID
    AND UNAFFECTED - it comes from the separate transformation grid - so the
    point's elevation IS converted and written; only the sigma cell reads N/A.

    This code exists because DESIGN.md #41 recorded that the disclosure layer
    (WP-V7) must not assume a warning already flags the missing sigma: the
    reading carries its reason, but a reason on a frozen record reaches no
    surface on its own. Raising it here makes every surface - the job record's
    WARNINGS section, the audit CSV's warnings column, and the GUI warnings
    field - inherit the disclosure through the one warning pipeline they all
    already read, rather than each growing its own special case.

    NOT raised for an identity transformation: an identity carries no sigma
    because no model ran, which is a statement the job record's METHOD text
    makes ("no shift is applied"), not a condition worth warning about.
    """

    GEOID_SWAP_UNAVAILABLE = "geoid-swap-unavailable"
    """A geoid-to-geoid job's point carried a usable elevation, but one of the
    two geoid tiles does not cover its position, so the elevation was NOT
    re-derived under the output geoid model.

    Raised by michspc.job, like the three codes above, and shaped exactly as
    VERTICAL_SHIFT_UNAVAILABLE is: the horizontal coordinates are unaffected
    and stand, and the point's output elevation is left blank rather than
    filled with the input-model height, because a height stated against one
    geoid model printed in a Z column whose job names another is the same
    ordinary-looking wrong number. Both shipped tiles cover all of Michigan
    with room to spare (docs/DESIGN.md section 3), so this is only reachable
    for a point already far outside the state - but "unreachable in practice"
    is not a reason to pass a height through silently when it is reached.
    """

    ELLIPSOID_HEIGHT_UNCONVERTIBLE = "ellipsoid-height-unconvertible"
    """A point's height was supplied as an ELLIPSOID height in one of the
    vertical modes, but the geoid tile does not cover its position, so
    H = h - N could not be computed and no orthometric height exists for it.

    Distinct from GEOID_UNAVAILABLE on purpose, and the distinction is the
    whole point of a separate code: GEOID_UNAVAILABLE costs a point its
    FACTORS and its Z still goes out, while this costs it the Z ITSELF. The
    vertical modes exist to produce a datum-tagged elevation; there is none
    here, and writing the unconverted ellipsoid height into a Z column those
    modes label with a vertical datum would be a height roughly 34 m wrong in
    Michigan wearing the right label - the ordinary-looking wrong number this
    project is built against.

    Horizontal mode raises GEOID_UNAVAILABLE for the same failure instead,
    because there the Z is the supplied height passed through unchanged (the
    owner's instruction) and only the factors are lost - which is exactly what
    that older code has always meant.
    """


@dataclass(frozen=True)
class ConversionWarning:
    """Something the surveyor should look at, which is not a reason to refuse."""

    code: WarningCode
    message: str


@dataclass(frozen=True)
class PointConversion:
    """The full record of one point's conversion. Immutable.

    Every zone-derived field - the two zones, the four convergence and scale
    quantities, and the grid coordinates - is None on a record built by
    ``geodetic_position``: a vertical-only job whose input is geodetic
    involves no zone anywhere, and this program does not fabricate one. The
    geodetic pivot is the one thing such a record always carries.
    """

    source_zone: Zone | None
    target_zone: Zone | None

    frame: ReferenceFrame
    """The reference frame this position is expressed in.

    A geodetic position is meaningless without it (docs/DESIGN.md section 4:
    the pivot of every conversion is "a geodetic position tagged with its
    reference frame"). Carried on the record so the job record can state which
    frame the numbers were interpreted as, rather than leaving a reader to
    assume NAD 83 - the assumption that is a one-to-two metre error when it is
    wrong.
    """

    source_northing: float | None
    source_easting: float | None
    """Meters, in the source zone. None on a no-zone record."""

    latitude: float
    longitude: float
    """The geodetic pivot. Decimal degrees, longitude negative west."""

    target_northing: float | None
    target_easting: float | None
    """Meters, in the target zone. None on a no-zone record."""

    source_convergence: float | None
    source_scale_factor: float | None
    target_convergence: float | None
    target_scale_factor: float | None

    warnings: tuple[ConversionWarning, ...] = field(default_factory=tuple)


def _check_extent(zone: Zone, latitude: float, longitude: float, context: str):
    """Warn when a point falls outside the zone's intended area.

    Never a refusal. A project legitimately straddling a zone boundary must
    still convert (docs/DESIGN.md amendment #1).
    """
    outside_latitude = not (zone.lat_min <= latitude <= zone.lat_max)
    outside_longitude = not (zone.lon_min <= longitude <= zone.lon_max)
    if not (outside_latitude or outside_longitude):
        return None

    return ConversionWarning(
        code=WarningCode.OUTSIDE_ZONE_EXTENT,
        message=(
            f"{context}: {latitude:.6f}, {longitude:.6f} lies outside the area "
            f"{zone.name} covers ({zone.lat_min:.1f} to {zone.lat_max:.1f} N, "
            f"{zone.lon_min:.1f} to {zone.lon_max:.1f} E). The coordinate is "
            f"computed correctly, but distortion grows with distance from the "
            f"zone and another zone may suit this point better."
        ),
    )


def easting_looks_wrong_for_zone(easting: float, zone: Zone) -> bool:
    """Does this easting plausibly belong to this zone at all?

    Michigan's three zones have false eastings 2,000,000 m apart precisely so a
    coordinate reveals its own zone (manual PDF p. 18: "Selecting different grid
    origins ... so the coordinate user could determine the zone from the
    magnitude of the coordinate"). Selecting the wrong source zone is the most
    likely real-world mistake with this program, and it is cheap to notice.

    Takes meters.
    """
    return abs(easting - zone.definition.easting_origin) > _EASTING_WINDOW_M


def to_geodetic(
    northing: float,
    easting: float,
    zone: Zone,
    context: str = "point",
) -> tuple[float, float, float, float, tuple[ConversionWarning, ...]]:
    """Grid to geodetic.

    Returns (latitude, longitude, convergence, scale_factor, warnings).
    """
    position = project_inverse(northing, easting, zone)

    return (
        position.latitude,
        position.longitude,
        position.convergence,
        position.scale_factor,
        (),
    )


def from_geodetic(
    latitude: float,
    longitude: float,
    zone: Zone,
    context: str = "point",
) -> tuple[float, float, float, float, tuple[ConversionWarning, ...]]:
    """Geodetic to grid.

    Returns (northing, easting, convergence, scale_factor, warnings).
    """
    point = project_forward(latitude, longitude, zone)

    warnings: list[ConversionWarning] = []
    extent_warning = _check_extent(
        zone, latitude, longitude, f"{context} (into {zone.abbrev})"
    )
    if extent_warning:
        warnings.append(extent_warning)

    return (
        point.northing,
        point.easting,
        point.convergence,
        point.scale_factor,
        tuple(warnings),
    )


def convert_point(
    northing: float,
    easting: float,
    source_zone: Zone,
    target_zone: Zone,
    context: str = "point",
) -> PointConversion:
    """Convert one point from one zone to another.

    Both zones must be in the same reference frame; crossing frames is refused
    (michspc.spc.frames). Linear values are meters.

    A zone is the only thing this function accepts; its constants are derived
    from it here. Callers used to be able to hand in precomputed
    ``LambertConstants`` for speed, which made it possible to name one zone and
    supply another's constants - a 4,231 km error with no refusal and no warning
    (docs/DESIGN.md amendment #11 finding 5). ``constants_for`` is cached, so
    the speed that seam bought is now free.
    """
    require_same_frame(source_zone.frame, target_zone.frame)

    latitude, longitude, source_convergence, source_scale, warnings_in = to_geodetic(
        northing, easting, source_zone, context
    )

    (
        target_northing,
        target_easting,
        target_convergence,
        target_scale,
        warnings_out,
    ) = from_geodetic(latitude, longitude, target_zone, context)

    return PointConversion(
        source_zone=source_zone,
        target_zone=target_zone,
        frame=source_zone.frame,
        source_northing=northing,
        source_easting=easting,
        latitude=latitude,
        longitude=longitude,
        target_northing=target_northing,
        target_easting=target_easting,
        source_convergence=source_convergence,
        source_scale_factor=source_scale,
        target_convergence=target_convergence,
        target_scale_factor=target_scale,
        warnings=warnings_in + warnings_out,
    )


def project_point(
    latitude: float,
    longitude: float,
    source_frame: ReferenceFrame,
    target_zone: Zone,
    context: str = "point",
) -> PointConversion:
    """Convert a geodetic position into a zone's grid coordinates.

    The geodetic-input case. No inverse step is performed, so the source zone is
    the target zone.

    ``source_frame`` is the reference frame the latitude and longitude are
    expressed in, and it is **required with no default**. A latitude and
    longitude alone do not say which frame they belong to, and NAD 83 and
    NATRF2022 differ by one to two metres over North America; projecting a
    NATRF2022 position with the SPCS 83 constants yields a coordinate that looks
    entirely ordinary and is wrong by more than the width of a road. The
    equivalent zone-to-zone refusal has existed since the beginning
    (``convert_point``); this closes the geodetic-input door on the same rule.
    See docs/DESIGN.md sections 4 and 6, and amendment #11 finding 1.

    Refuses with ``FrameMismatchError`` if the position's frame is not the
    target zone's frame.
    """
    if not isinstance(source_frame, ReferenceFrame):
        raise TypeError(
            f"project_point needs the reference frame the geodetic position is "
            f"expressed in, as its third argument; got "
            f"{type(source_frame).__name__} ({source_frame!r}). A latitude and "
            f"longitude do not carry their own frame, and the frame decides "
            f"whether the resulting State Plane coordinate is right or is one "
            f"to two metres out. Pass michspc.spc.frames.NAD83_2011 for an "
            f"NAD 83 position."
        )

    require_same_frame(source_frame, target_zone.frame)

    (
        northing,
        easting,
        convergence,
        scale,
        warnings,
    ) = from_geodetic(latitude, longitude, target_zone, context)

    return PointConversion(
        source_zone=target_zone,
        target_zone=target_zone,
        frame=source_frame,
        source_northing=northing,
        source_easting=easting,
        latitude=latitude,
        longitude=longitude,
        target_northing=northing,
        target_easting=easting,
        source_convergence=convergence,
        source_scale_factor=scale,
        target_convergence=convergence,
        target_scale_factor=scale,
        warnings=warnings,
    )


def geodetic_position(
    latitude: float,
    longitude: float,
    source_frame: ReferenceFrame,
    context: str = "point",
) -> PointConversion:
    """A geodetic position with no zone on either end.

    Exists for the vertical-only job whose input is geodetic
    (``michspc.job``, ``Direction.VERTICAL_ONLY`` with ``source_zone=None``):
    the vertical shift and the geoid lookup need the pivot latitude and
    longitude, and nothing in that job involves a State Plane zone. Every
    zone-derived field is None - never a fabricated zone, whose scale factor
    and convergence would be plausible numbers describing a projection nobody
    chose. ``factors_at`` accepts the None scale factor and reports the grid
    scale and combined factors as absent while still computing the elevation
    factor, which needs no zone.

    ``source_frame`` is required with no default, exactly as
    ``project_point`` requires it and for the same reason: a latitude and
    longitude alone do not say which frame they belong to, and the NGS grids
    this position is looked up in are published against NAD 83. No projection
    runs here, so no extent warning can be raised - there is no zone to have
    an extent.
    """
    if not isinstance(source_frame, ReferenceFrame):
        raise TypeError(
            f"geodetic_position needs the reference frame the position is "
            f"expressed in, as its third argument; got "
            f"{type(source_frame).__name__} ({source_frame!r}). A latitude "
            f"and longitude do not carry their own frame. Pass "
            f"michspc.spc.frames.NAD83_2011 for an NAD 83 position."
        )

    return PointConversion(
        source_zone=None,
        target_zone=None,
        frame=source_frame,
        source_northing=None,
        source_easting=None,
        latitude=latitude,
        longitude=longitude,
        target_northing=None,
        target_easting=None,
        source_convergence=None,
        source_scale_factor=None,
        target_convergence=None,
        target_scale_factor=None,
        warnings=(),
    )
