"""The conversion pipeline.

One point in, one immutable record out, carrying not just the answer but the
evidence for it: the geodetic pivot, both zones' convergence and scale factor,
how closely the two independent engines agreed, and every warning raised along
the way.

The pipeline shape (docs/DESIGN.md section 4):

    (source zone, N, E) --inverse--> geodetic --forward--> (target zone, N, E)

Both steps are computed twice, once by each engine. Within a zone's fitted band
the two must agree to 0.5 mm or the conversion is refused. Outside it, the
polynomial method is known to degrade (design log #5) and the disagreement is
reported as a warning rather than treated as a defect - refusing there would
block a conversion the rigorous engine handles correctly, which is the opposite
of the intended behavior.

All linear values in this module are meters. Unit conversion happens at the
file boundary, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from michspc.spc import agreement as ag
from michspc.spc import polynomial as poly
from michspc.spc.frames import require_same_frame
from michspc.spc.lambert import LambertConstants, constants_for
from michspc.spc.lambert import forward as rigorous_forward
from michspc.spc.lambert import inverse as rigorous_inverse
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
    ENGINE_DISAGREEMENT_OUT_OF_BAND = "engine-disagreement-out-of-band"
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

    inverse_agreement: ag.Agreement | None
    """How closely the engines agreed on the source zone's inverse conversion.

    None when the conversion started from a geodetic position, since no inverse
    step was performed.
    """

    forward_agreement: ag.Agreement
    """How closely the engines agreed on the target zone's forward conversion."""

    warnings: tuple[ConversionWarning, ...] = field(default_factory=tuple)


def _within_fitted_band(zone: Zone, latitude: float) -> bool:
    """Is this latitude inside the band the zone's polynomials were fit across?

    Uses the zone's **measured** band, not its geographic extent. Those are
    different things and conflating them is a real defect: Michigan Central's
    coverage reaches 46.0 N while its polynomials hold only to 46.128 N, and
    Michigan South's coverage reaches 44.3 N while its polynomials hold only to
    44.312 N. Widening the enforcement band past the measured one turns the
    polynomial method's known degradation into a spurious hard failure.
    See docs/DESIGN.md amendment #6.
    """
    return zone.band_lat_min <= latitude <= zone.band_lat_max


def _check_engines(
    zone: Zone,
    latitude: float,
    agreement: ag.Agreement,
    context: str,
) -> ConversionWarning | None:
    """Enforce the cross-check where both engines are valid; warn where not.

    Returns a warning, or None. Raises EngineDisagreementError when the point is
    inside the zone's fitted band and the engines still disagree - there, a
    disagreement means one of them is genuinely wrong.
    """
    if agreement.within_tolerance:
        return None

    if _within_fitted_band(zone, latitude):
        ag.require_agreement(agreement, context)
        return None  # unreachable; require_agreement raises

    return ConversionWarning(
        code=WarningCode.ENGINE_DISAGREEMENT_OUT_OF_BAND,
        message=(
            f"{context}: latitude {latitude:.6f} is outside {zone.name}'s "
            f"fitted latitude band ({zone.band_lat_min:.2f} to "
            f"{zone.band_lat_max:.2f}), "
            f"where the manual's Appendix C polynomial coefficients are known "
            f"to degrade. The two engines differ by {agreement.describe()}. The "
            f"rigorous Lambert equations are exact here and were used; the "
            f"polynomial figure is the unreliable one."
        ),
    )


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
) -> tuple[float, float, float, float, ag.Agreement, tuple[ConversionWarning, ...]]:
    """Grid to geodetic, both engines, with warnings.

    Returns (latitude, longitude, convergence, scale_factor, agreement, warnings).
    """
    constants = constants or constants_for(zone)
    coefficients = poly.coefficients_for(zone.code)

    rigorous = rigorous_inverse(northing, easting, constants)
    polynomial = poly.inverse(northing, easting, constants, coefficients)

    # Compare the two inverse results by re-projecting the polynomial engine's
    # geodetic answer through the rigorous forward equations. Comparing the two
    # latitudes directly would need an ad-hoc degrees-to-meters factor; this
    # keeps the whole comparison in meters on the grid, which is the unit the
    # 0.5 mm tolerance is actually stated in.
    reprojected = rigorous_forward(polynomial.latitude, polynomial.longitude, constants)
    agreement = ag.Agreement(
        northing_difference=northing - reprojected.northing,
        easting_difference=easting - reprojected.easting,
    )

    warnings: list[ConversionWarning] = []
    engine_warning = _check_engines(
        zone, rigorous.latitude, agreement, f"{context} (from {zone.abbrev})"
    )
    if engine_warning:
        warnings.append(engine_warning)

    return (
        rigorous.latitude,
        rigorous.longitude,
        rigorous.convergence,
        rigorous.scale_factor,
        agreement,
        tuple(warnings),
    )


def from_geodetic(
    latitude: float,
    longitude: float,
    zone: Zone,
    context: str = "point",
    constants: LambertConstants | None = None,
) -> tuple[float, float, float, float, ag.Agreement, tuple[ConversionWarning, ...]]:
    """Geodetic to grid, both engines, with warnings.

    Returns (northing, easting, convergence, scale_factor, agreement, warnings).
    """
    constants = constants or constants_for(zone)
    coefficients = poly.coefficients_for(zone.code)

    rigorous = rigorous_forward(latitude, longitude, constants)
    polynomial = poly.forward(latitude, longitude, constants, coefficients)
    agreement = ag.compare(rigorous, polynomial)

    warnings: list[ConversionWarning] = []
    engine_warning = _check_engines(
        zone, latitude, agreement, f"{context} (into {zone.abbrev})"
    )
    if engine_warning:
        warnings.append(engine_warning)

    extent_warning = _check_extent(zone, latitude, longitude, f"{context} (into {zone.abbrev})")
    if extent_warning:
        warnings.append(extent_warning)

    return (
        rigorous.northing,
        rigorous.easting,
        rigorous.convergence,
        rigorous.scale_factor,
        agreement,
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

    ``source_constants`` and ``target_constants`` may be passed in so a whole
    file's worth of points does not re-derive the zone constants per row; they
    are otherwise derived here.
    """
    require_same_frame(source_zone.frame, target_zone.frame)

    latitude, longitude, source_convergence, source_scale, inverse_agreement, warnings_in = (
        to_geodetic(northing, easting, source_zone, context, source_constants)
    )

    (
        target_northing,
        target_easting,
        target_convergence,
        target_scale,
        forward_agreement,
        warnings_out,
    ) = from_geodetic(latitude, longitude, target_zone, context, target_constants)

    return PointConversion(
        source_zone=source_zone,
        target_zone=target_zone,
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
        inverse_agreement=inverse_agreement,
        forward_agreement=forward_agreement,
        warnings=warnings_in + warnings_out,
    )


def project_point(
    latitude: float,
    longitude: float,
    target_zone: Zone,
    context: str = "point",
    target_constants: LambertConstants | None = None,
) -> PointConversion:
    """Convert a geodetic position into a zone's grid coordinates.

    The geodetic-input case. No inverse step is performed, so
    ``inverse_agreement`` is None and the source zone is the target zone.
    """
    (
        northing,
        easting,
        convergence,
        scale,
        forward_agreement,
        warnings,
    ) = from_geodetic(latitude, longitude, target_zone, context, target_constants)

    return PointConversion(
        source_zone=target_zone,
        target_zone=target_zone,
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
        inverse_agreement=None,
        forward_agreement=forward_agreement,
        warnings=warnings,
    )
