"""The conversion pipeline.

One point in, one immutable record out, carrying not just the answer but the
evidence for it: the geodetic pivot, both zones' convergence and scale factor,
and every warning raised along the way.

The pipeline shape (docs/DESIGN.md section 4):

    (source zone, N, E) --inverse--> geodetic --forward--> (target zone, N, E)

Both steps use the rigorous Lambert conformal conic equations of NOAA Manual
NOS NGS 5 section 3.1, which are exact at any latitude.

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
from michspc.spc.lambert import LambertConstants, constants_for
from michspc.spc.lambert import forward as lambert_forward
from michspc.spc.lambert import inverse as lambert_inverse
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


@dataclass(frozen=True)
class ConversionWarning:
    """Something the surveyor should look at, which is not a reason to refuse."""

    code: WarningCode
    message: str


@dataclass(frozen=True)
class PointConversion:
    """The full record of one point's conversion. Immutable."""

    source_zone: Zone
    target_zone: Zone

    frame: ReferenceFrame
    """The reference frame this position is expressed in.

    A geodetic position is meaningless without it (docs/DESIGN.md section 4:
    the pivot of every conversion is "a geodetic position tagged with its
    reference frame"). Carried on the record so the job record can state which
    frame the numbers were interpreted as, rather than leaving a reader to
    assume NAD 83 - the assumption that is a one-to-two metre error when it is
    wrong.
    """

    source_northing: float
    source_easting: float
    """Meters, in the source zone."""

    latitude: float
    longitude: float
    """The geodetic pivot. Decimal degrees, longitude negative west."""

    target_northing: float
    target_easting: float
    """Meters, in the target zone."""

    source_convergence: float
    source_scale_factor: float
    target_convergence: float
    target_scale_factor: float

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
    constants: LambertConstants | None = None,
) -> tuple[float, float, float, float, tuple[ConversionWarning, ...]]:
    """Grid to geodetic.

    Returns (latitude, longitude, convergence, scale_factor, warnings).
    """
    constants = constants or constants_for(zone)
    position = lambert_inverse(northing, easting, constants)

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
    constants: LambertConstants | None = None,
) -> tuple[float, float, float, float, tuple[ConversionWarning, ...]]:
    """Geodetic to grid.

    Returns (northing, easting, convergence, scale_factor, warnings).
    """
    constants = constants or constants_for(zone)
    point = lambert_forward(latitude, longitude, constants)

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
    source_constants: LambertConstants | None = None,
    target_constants: LambertConstants | None = None,
) -> PointConversion:
    """Convert one point from one zone to another.

    Both zones must be in the same reference frame; crossing frames is refused
    (michspc.spc.frames). Linear values are meters.
    """
    require_same_frame(source_zone.frame, target_zone.frame)

    latitude, longitude, source_convergence, source_scale, warnings_in = to_geodetic(
        northing, easting, source_zone, context, source_constants
    )

    (
        target_northing,
        target_easting,
        target_convergence,
        target_scale,
        warnings_out,
    ) = from_geodetic(latitude, longitude, target_zone, context, target_constants)

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
    target_constants: LambertConstants | None = None,
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
    ) = from_geodetic(latitude, longitude, target_zone, context, target_constants)

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
