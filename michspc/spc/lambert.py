"""Lambert conformal conic mapping equations - the rigorous form.

NOAA Manual NOS NGS 5, section 3.1 (PDF pp. 36-39):

  * 3.12 computation of zone constants   (PDF p. 37)
  * 3.13 direct conversion, phi/lambda -> N/E   (PDF p. 38)
  * 3.14 inverse conversion, N/E -> phi/lambda  (PDF pp. 38-39)

These are the only conversion equations this program uses.

The manual warns (section 3, PDF p. 35) that the general equations need more
than 10 significant digits to hold millimeter accuracy in the larger Lambert
zones. Python's floats carry about 15-17 significant decimal digits, so that
constraint does not bind here. The equations are exact at any latitude, with no
fitted term and no restricted band - which matters for this program, whose whole
purpose is converting a point from one Michigan zone into a neighbouring zone's
coordinates.

What verifies this module is external and lives in the test suite: the published
Appendix C derived constants, recomputed here from the defining constants alone,
and 27 frozen NGS NCAT positions. See docs/DESIGN.md amendment #14.

Conventions in this module:
  * Latitudes and longitudes at the API boundary are decimal degrees.
  * Longitude is signed, NEGATIVE WEST. The manual uses positive-west; the two
    places that conversion matters are marked below.
  * Linear units are meters, matching the ellipsoid and the zone constants.
  * Convergence angle is returned in decimal degrees, positive east of the
    central meridian.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import cached_property, lru_cache

from michspc.spc.ellipsoid import GRS80, Ellipsoid
from michspc.spc.zones import LambertTwoParallelDef, Zone

# The inverse conversion solves for sin(phi) by Newton's method. The manual
# (PDF p. 39) says to apply the correction and "iterate two times"; we instead
# iterate to convergence with a hard ceiling, which is strictly tighter and
# fails loudly rather than silently returning a half-converged latitude.
# Documented as a deviation in docs/DESIGN.md.
_SIN_LAT_TOLERANCE = 1e-15
_MAX_ITERATIONS = 12

# Largest |Q| for which the manual's starting approximation can still produce a
# sin(phi) strictly inside (-1, 1), hand-derived:
#
#     sin phi = (exp(2Q) - 1) / (exp(2Q) + 1) = tanh Q
#     1 - tanh Q = 2 / (exp(2Q) + 1)
#
# IEEE-754 binary64 has ulp(1.0) = 2^-53, so any value within 2^-54 of 1.0
# rounds to exactly 1.0. The seed is therefore indistinguishable from 1 once
#
#     2 / (exp(2Q) + 1) <= 2^-54   <=>   exp(2Q) >= 2^55 - 1
#     Q >= 0.5 ln(2^55 - 1) = 19.0615475...
#
# and no representable latitude corresponds. Guarding here also keeps
# math.exp(2Q) below its own overflow point (2Q < 709.78) and keeps the
# symmetric case, Q -> -inf and sin(phi) -> -1, out of math.log(0.0).
_MAX_ISOMETRIC_LATITUDE = 0.5 * math.log(2.0**55 - 1.0)


class ApexLatitudeError(ValueError):
    """The grid point lies too close to the cone apex for any latitude.

    Distinct from the ``R' <= 0`` refusal in ``inverse``, which catches points
    at or past the apex itself. This is the band just below it, a few tens of
    metres deep, where the mapping radius is still positive but the latitude it
    implies is within a rounding step of 90 degrees. Before this guard existed
    the band raised a bare ``ZeroDivisionError`` out of
    ``Ellipsoid.isometric_latitude`` - found by the closing review gate.

    A ``ValueError`` so it sits alongside the module's other refusals for a
    coordinate that cannot be converted.
    """


def _require_representable_sin_latitude_of(sin_lat: float, latitude: float) -> None:
    """Refuse a latitude whose sine has rounded onto a pole.

    The forward counterpart of ``_require_representable_sin_latitude``, which
    guards the inverse iteration. Stated as a containment test so a NaN is
    refused too, and it names the latitude the caller passed rather than its
    sine, because that is the number in the file.
    """
    if not -1.0 < sin_lat < 1.0:
        raise ApexLatitudeError(
            f"Latitude {latitude!r} is within a rounding step of a pole: its "
            f"sine is exactly {sin_lat!r}, and the isometric latitude of a pole "
            f"is infinite, so no grid coordinate corresponds to it. Check that "
            f"the latitude column holds decimal degrees and was not swapped "
            f"with another field."
        )


class ConvergenceError(Exception):
    """The inverse latitude iteration did not converge.

    Fails closed. In Michigan this cannot happen for any real coordinate; if it
    ever does, the input is far outside the projection's usable domain and no
    plausible latitude should be invented for it.
    """


def _require_valid_geodetic(latitude: float, longitude: float) -> None:
    """Refuse a latitude or longitude that is out of domain or not a number.

    Both engines call this. Neither the engine cross-check nor the zone-extent
    warning can protect against a bad input here, because both engines are
    handed the same bad value and agree perfectly on the wrong answer - so the
    check has to happen before either of them runs.

    The longitude domain matters more than it looks. This program uses signed
    longitude, negative west; the geoid grid and many datasets use the 0-360
    east convention, in which Michigan's 84.5555 W is 275.4445. That value is a
    perfectly ordinary float, it produces a coordinate with no warning worth
    noticing, and it is wrong by thousands of kilometres. Found by the interim
    review gate; see docs/DESIGN.md amendment #10.
    """
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError(
            f"Latitude {latitude!r} and longitude {longitude!r} must both be "
            f"finite numbers. A coordinate that is not a number cannot be "
            f"projected, and must never be written to a file."
        )
    if not -90.0 < latitude < 90.0:
        raise ValueError(
            f"Latitude {latitude} is not a valid geodetic latitude; it must lie "
            f"strictly between -90 and 90 degrees."
        )
    if not -180.0 <= longitude <= 180.0:
        raise ValueError(
            f"Longitude {longitude} is outside the range -180 to 180. This "
            f"program uses SIGNED longitude, negative west - Michigan runs from "
            f"about -83 to -90. A value between 180 and 360 is the 0-360 east "
            f"convention: subtract 360 from it ({longitude - 360.0:.6f} here). "
            f"Converting it as given would place the point thousands of "
            f"kilometres away."
        )


def _require_finite_grid(northing: float, easting: float) -> None:
    """Refuse a grid coordinate that is not a number, before it is inverted."""
    if not math.isfinite(northing) or not math.isfinite(easting):
        raise ValueError(
            f"Northing {northing!r} and easting {easting!r} must both be finite "
            f"numbers. Check the input file for a blank or corrupt coordinate."
        )


@dataclass(frozen=True)
class LambertConstants:
    """Zone constants derived once per zone, manual section 3.12 (PDF p. 37).

    These are the quantities the mapping equations actually consume. The manual
    publishes their values for every zone in Appendix C, which is what
    tests/test_zone_constants.py checks this derivation against.

    Constructed by ``from_two_parallels`` for the SPCS 83 form. A second
    constructor taking a central parallel and scale factor directly - the
    SPCS2022 one-standard-parallel form - drops in here without touching
    anything downstream, because the mapping equations depend only on the
    fields below.
    """

    ellipsoid: Ellipsoid

    sin_lat_origin: float
    """sin(phi_0) - the cone constant. Manual's ``SinBo``."""

    K: float
    """Mapping radius at the equator. Manual's ``K``."""

    R_grid_origin: float
    """R_b - mapping radius at the grid origin latitude phi_b."""

    R_origin: float
    """R_0 - mapping radius at the central parallel phi_0."""

    northing_grid_origin: float
    """N_b - northing assigned to the grid origin."""

    easting_origin: float
    """E_0 - easting assigned to the central meridian."""

    lon_origin: float
    """lambda_0 - central meridian, decimal degrees, NEGATIVE WEST."""

    zone_code: str | None = None
    """The zone these constants belong to, when they came from a registry zone.

    Carried so constants can never be silently paired with a different zone's
    identity. Passing Michigan South's constants while naming Michigan North
    produced a coordinate 4,231 km out of place with only a warning - found by
    the interim review gate. The public conversion API no longer accepts
    caller-supplied constants at all (docs/DESIGN.md amendment #11); this field
    makes any future re-introduction of that seam checkable.
    """

    @cached_property
    def lat_origin(self) -> float:
        """phi_0 - the central parallel, decimal degrees. Manual's ``Bo``."""
        return math.degrees(math.asin(self.sin_lat_origin))

    @cached_property
    def northing_origin(self) -> float:
        """N_0 - northing at the true projection origin. Manual's ``No``.

        From the direct equation N = R_b + N_b - R cos(gamma) evaluated on the
        central meridian at the central parallel, where gamma = 0 and R = R_0.
        """
        return self.R_grid_origin + self.northing_grid_origin - self.R_origin

    @cached_property
    def k_origin(self) -> float:
        """k_0 - grid scale factor at the central parallel. Manual's ``ko``.

        The section 3.14 scale factor equation (PDF p. 39) evaluated at phi_0.
        """
        return self._scale_factor(self.sin_lat_origin, self.R_origin)

    @cached_property
    def M_origin(self) -> float:
        """M_0 - radius of curvature in the meridian at phi_0, scaled to the grid.

        Manual section 3.15 (PDF p. 40): "M0 is the scaled radius of curvature
        in the meridian at phi_0 scaled to the grid."
        """
        return self.k_origin * self.ellipsoid.radius_meridian(self.sin_lat_origin)

    @cached_property
    def r_origin(self) -> float:
        """r_0 - geometric mean radius of curvature at phi_0, scaled to the grid.

        Manual section 3.15 (PDF p. 40).
        """
        return self.k_origin * self.ellipsoid.radius_geometric_mean(
            self.sin_lat_origin
        )

    def _scale_factor(self, sin_lat: float, R: float) -> float:
        """k = W (R sin phi_0) / (a cos phi), manual section 3.14 (PDF p. 39)."""
        cos_lat = math.sqrt(1.0 - sin_lat * sin_lat)
        return (
            self.ellipsoid.W(sin_lat)
            * R
            * self.sin_lat_origin
            / (self.ellipsoid.a * cos_lat)
        )

    @classmethod
    def from_two_parallels(
        cls,
        definition: LambertTwoParallelDef,
        ellipsoid: Ellipsoid = GRS80,
    ) -> LambertConstants:
        """Derive the zone constants from two standard parallels.

        Manual section 3.12 (PDF p. 37):

            sin(phi_0) = ln[(W_n cos phi_s) / (W_s cos phi_n)] / (Q_n - Q_s)
            K = a cos(phi_s) exp(Q_s sin phi_0) / (W_s sin phi_0)
            R_0 = K / exp(Q_0 sin phi_0)

        The equation for K is given twice in the manual, once in terms of the
        southern standard parallel and once the northern; they are equal by
        construction. We use the southern form and the test suite checks the
        northern form agrees, which is a free consistency check on this whole
        derivation.
        """
        sin_s = math.sin(math.radians(definition.lat_south))
        sin_n = math.sin(math.radians(definition.lat_north))
        cos_s = math.cos(math.radians(definition.lat_south))
        cos_n = math.cos(math.radians(definition.lat_north))

        W_s = ellipsoid.W(sin_s)
        W_n = ellipsoid.W(sin_n)
        Q_s = ellipsoid.isometric_latitude(sin_s)
        Q_n = ellipsoid.isometric_latitude(sin_n)

        sin_lat_origin = math.log((W_n * cos_s) / (W_s * cos_n)) / (Q_n - Q_s)

        K = ellipsoid.a * cos_s * math.exp(Q_s * sin_lat_origin) / (W_s * sin_lat_origin)

        sin_b = math.sin(math.radians(definition.lat_grid_origin))
        Q_b = ellipsoid.isometric_latitude(sin_b)
        Q_0 = ellipsoid.isometric_latitude(sin_lat_origin)

        return cls(
            ellipsoid=ellipsoid,
            sin_lat_origin=sin_lat_origin,
            K=K,
            R_grid_origin=K / math.exp(Q_b * sin_lat_origin),
            R_origin=K / math.exp(Q_0 * sin_lat_origin),
            northing_grid_origin=definition.northing_grid_origin,
            easting_origin=definition.easting_origin,
            lon_origin=definition.lon_origin,
        )


@dataclass(frozen=True)
class GridPoint:
    """A point on the grid, with the two quantities that describe the grid there."""

    northing: float
    """Meters."""

    easting: float
    """Meters."""

    convergence: float
    """Decimal degrees, positive east of the central meridian."""

    scale_factor: float
    """Grid scale factor at the point (dimensionless)."""


@dataclass(frozen=True)
class GeodeticPoint:
    """A geodetic position, with the grid quantities that apply at it."""

    latitude: float
    """Decimal degrees north."""

    longitude: float
    """Decimal degrees, NEGATIVE WEST."""

    convergence: float
    """Decimal degrees, positive east of the central meridian."""

    scale_factor: float
    """Grid scale factor at the point (dimensionless)."""


def forward(
    latitude: float, longitude: float, constants: LambertConstants
) -> GridPoint:
    """Geodetic to grid. Manual section 3.13 (PDF p. 38).

        Q     = isometric latitude
        R     = K / exp(Q sin phi_0)
        gamma = (lambda_0 - lambda) sin phi_0
        N     = R_b + N_b - R cos gamma
        E     = E_0 + R sin gamma

    ``latitude`` and ``longitude`` are decimal degrees, longitude negative west.
    """
    _require_valid_geodetic(latitude, longitude)

    sin_lat = math.sin(math.radians(latitude))

    # The domain check above admits any latitude strictly inside (-90, 90), but
    # sin() rounds to exactly +-1.0 for the last 6.04e-7 degrees - about 67 mm -
    # below each pole, and isometric_latitude then evaluates log((1+1)/(1-1)).
    # The inverse path was hardened against the same arithmetic at the cone
    # apex; this is its symmetric partner on the forward path, found by the
    # WP-R4 verification package. Michigan work never approaches it, but "no
    # bare arithmetic error escapes the core" is not a rule with a latitude
    # qualifier: unguarded, the north side raised ZeroDivisionError and the
    # south side a ValueError out of math.log naming nothing.
    _require_representable_sin_latitude_of(sin_lat, latitude)

    Q = constants.ellipsoid.isometric_latitude(sin_lat)
    R = constants.K / math.exp(Q * constants.sin_lat_origin)

    # The manual writes gamma = (lambda_0 - lambda) sin(phi_0) with longitude
    # POSITIVE WEST. Our longitudes are negative west, so both terms change
    # sign and the subtraction reverses. This is the only place in the program
    # where the manual's longitude convention appears.
    convergence = (longitude - constants.lon_origin) * constants.sin_lat_origin
    gamma = math.radians(convergence)

    return GridPoint(
        northing=constants.R_grid_origin
        + constants.northing_grid_origin
        - R * math.cos(gamma),
        easting=constants.easting_origin + R * math.sin(gamma),
        convergence=convergence,
        scale_factor=constants._scale_factor(sin_lat, R),
    )


def inverse(
    northing: float, easting: float, constants: LambertConstants
) -> GeodeticPoint:
    """Grid to geodetic. Manual section 3.14 (PDF pp. 38-39).

        R'    = R_b - N + N_b
        E'    = E - E_0
        gamma = atan(E' / R')
        lambda = lambda_0 - gamma / sin phi_0
        R     = (R'^2 + E'^2)^(1/2)
        Q     = ln(K / R) / sin phi_0

    then solve Q for latitude by Newton's method on sin(phi).

    ``northing`` and ``easting`` are meters.
    """
    _require_finite_grid(northing, easting)

    R_prime = constants.R_grid_origin - northing + constants.northing_grid_origin
    E_prime = easting - constants.easting_origin

    if R_prime <= 0.0:
        raise ValueError(
            f"Northing {northing} m is at or beyond the apex of the projection "
            f"cone for this zone (the mapping radius would be {R_prime:.3f} m). "
            f"No geodetic position corresponds to it. Check that the northing "
            f"and easting are not transposed and that the correct zone and unit "
            f"were selected."
        )

    gamma = math.atan(E_prime / R_prime)
    convergence = math.degrees(gamma)

    # Inverse of the sign handling in forward(): with negative-west longitudes,
    # lambda = lambda_0 + gamma / sin(phi_0).
    longitude = constants.lon_origin + convergence / constants.sin_lat_origin

    R = math.hypot(R_prime, E_prime)
    Q = math.log(constants.K / R) / constants.sin_lat_origin

    try:
        sin_lat = _solve_sin_latitude(Q, constants.ellipsoid)
    except ApexLatitudeError as exc:
        # The solver knows only Q. Re-raise naming the quantity the surveyor
        # actually typed, in the wording of the adjacent apex refusal above.
        raise ApexLatitudeError(
            f"Northing {northing} m is within a rounding step of the apex of "
            f"the projection cone for this zone (the mapping radius is only "
            f"{R:.3f} m, isometric latitude {Q:.6f}). Every latitude that close "
            f"to 90 degrees is the same double-precision number, so no geodetic "
            f"position can be reported for it. Check that the northing and "
            f"easting are not transposed and that the correct zone and unit "
            f"were selected."
        ) from exc

    return GeodeticPoint(
        latitude=math.degrees(math.asin(sin_lat)),
        longitude=longitude,
        convergence=convergence,
        scale_factor=constants._scale_factor(sin_lat, R),
    )


def _require_representable_sin_latitude(sin_lat: float, Q: float) -> None:
    """Refuse a sin(phi) that has reached or passed a pole, or is not a number.

    Written as a containment test rather than ``abs(sin_lat) >= 1.0`` so that a
    NaN - which compares false against every bound - is refused too.

    The |Q| ceiling above is the analytic boundary; this is the arithmetic one,
    and it is the tighter of the two. The manual's seed is evaluated as
    ``(exp(2Q) - 1) / (exp(2Q) + 1)``, and near the apex exp(2Q) is of order
    1e16, where ulp is 2 - so the +-1 terms snap to the same double and the
    quotient reaches exactly 1.0 while Q is still around 18.46, well short of
    19.06. Measured on the shipped zones, the refused band is the last 20 m
    (MI North), 28 m (MI Central) and 45 m (MI South) of northing below the
    apex, and its lower edge is ragged over a few metres for the same
    ulp-snapping reason - which is why the guard is a test on the value rather
    than a northing threshold anyone could tabulate.
    """
    if not -1.0 < sin_lat < 1.0:
        raise ApexLatitudeError(
            f"The latitude iteration reached sin(phi) = {sin_lat!r} for "
            f"isometric latitude Q={Q!r}. No geodetic latitude corresponds to "
            f"it; the point is at or beyond a pole of the projection."
        )


def _solve_sin_latitude(Q: float, ellipsoid: Ellipsoid) -> float:
    """Solve isometric_latitude(sin phi) = Q for sin(phi).

    Manual section 3.14 (PDF pp. 38-39) gives the starting approximation

        sin phi = (exp(2Q) - 1) / (exp(2Q) + 1)

    which is the spherical solution, then Newton's method with

        f1 = isometric_latitude(sin phi) - Q
        f2 = d(isometric_latitude)/d(sin phi)

    applying a correction of -f1/f2. The manual says to iterate twice; we
    iterate to machine precision and raise if that does not happen, rather than
    returning a value that merely looks converged.

    Refuses with ``ApexLatitudeError`` if the seed or any iterate leaves the
    open interval (-1, 1). ``isometric_latitude`` divides by ``1 - sin phi``,
    so a sin(phi) that has reached the poles produces a bare ZeroDivisionError
    (or, at -1, a math domain error out of ``log``) rather than a refusal, and
    no bare arithmetic error may escape the core.
    """
    if abs(Q) >= _MAX_ISOMETRIC_LATITUDE:
        raise ApexLatitudeError(
            f"Isometric latitude Q={Q!r} is beyond {_MAX_ISOMETRIC_LATITUDE:.6f}, "
            f"past which the starting approximation sin(phi) = tanh(Q) is "
            f"exactly +-1 in double precision and no representable geodetic "
            f"latitude corresponds."
        )

    exp_2q = math.exp(2.0 * Q)
    sin_lat = (exp_2q - 1.0) / (exp_2q + 1.0)
    _require_representable_sin_latitude(sin_lat, Q)

    for _ in range(_MAX_ITERATIONS):
        f1 = ellipsoid.isometric_latitude(sin_lat) - Q
        f2 = ellipsoid.d_isometric_latitude_d_sin(sin_lat)
        correction = -f1 / f2
        sin_lat += correction
        _require_representable_sin_latitude(sin_lat, Q)
        if abs(correction) < _SIN_LAT_TOLERANCE:
            return sin_lat

    raise ConvergenceError(
        f"Latitude iteration failed to converge for isometric latitude Q={Q!r} "
        f"after {_MAX_ITERATIONS} iterations (last correction {correction:.3e}). "
        f"The coordinate is outside the usable domain of this projection."
    )


@lru_cache(maxsize=32)
def constants_for(zone: Zone, ellipsoid: Ellipsoid = GRS80) -> LambertConstants:
    """Derive the working constants for a registry zone, once.

    Cached, so a file of several thousand points does not re-derive the same
    constants per row. The cache is what made it possible to delete the
    ``constants=`` parameters the conversion functions used to accept: callers
    now get the per-file efficiency for free and have no way to pair one zone's
    constants with another zone's identity (docs/DESIGN.md amendment #11).

    Zone and Ellipsoid are both frozen dataclasses and therefore hashable, so
    they are usable as cache keys directly.
    """
    constants = LambertConstants.from_two_parallels(zone.definition, ellipsoid)
    return replace(constants, zone_code=zone.code)
