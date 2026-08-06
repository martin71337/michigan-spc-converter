"""Lambert conversion by the polynomial coefficient method - the second engine.

NOAA Manual NOS NGS 5, section 3.4 (PDF pp. 52-55), with the per-zone
coefficients from Appendix C (PDF pp. 103-104).

NGS developed this method as an alternative to the rigorous mapping equations
of section 3.1, for machines carrying only 10 significant digits. It replaces
the isometric-latitude logarithm and exponential with a fitted polynomial in
``u``, the distance along the mapping radius between the central parallel and
the point. That makes it a genuinely *different* route to the same answer, not
a rearrangement of the same one - which is precisely why it is useful here.

**This engine is not the primary.** It runs alongside the rigorous engine on
every point, and the two must agree. See michspc/spc/agreement.py.

Why not primary: the manual states (PDF p. 54) that the coefficients were fit
by least squares to **ten data points per zone**, solving for the fewest
coefficients that held 0.5 mm accuracy *within that zone*. Converting a point
from one Michigan zone into a neighbouring zone's coordinates - this program's
whole purpose - evaluates the target zone's polynomial outside the band it was
fit to. The rigorous equations have no such limitation.

Note on the coefficient counts: Michigan North is a large enough zone to need
five L and five G coefficients; Central and South need four. The manual is
explicit that "the only required terms are those for which polynomial
coefficients are provided in appendix C" (PDF pp. 54-55), so the tables below
carry exactly what Appendix C prints and no zero padding.

Note on units: Delta-phi is in decimal degrees and ``u`` is in meters. The
manual's section 3.4 text describes the inverse polynomial as producing
Delta-phi "in radians"; that is inconsistent with its own printed coefficients
(G1 is about 9.0e-06, and 9.0e-06 x 111000 m is about 1.0, a degree, not a
radian) and with L1 being about 111,100 m per degree. Degrees is correct, and
the anchor tests confirm it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from michspc.spc.lambert import GeodeticPoint, GridPoint, LambertConstants


@dataclass(frozen=True)
class PolynomialCoefficients:
    """Appendix C coefficients for one zone.

    These are irreducible data: they are least-squares fits published by NGS
    and cannot be derived from anything else in the program. The *derived*
    zone constants this method also needs (B_0, sin B_0, R_0, N_0, E_0,
    lambda_0) are deliberately NOT duplicated here - they come from the
    rigorous engine's LambertConstants, whose agreement with Appendix C's
    published values is proven independently in tests/test_zone_constants.py.
    """

    zone_code: str
    citation: str

    L: tuple[float, ...]
    """Forward coefficients, geodetic position to plane coordinates."""

    G: tuple[float, ...]
    """Inverse coefficients, plane coordinates to geodetic position."""

    F: tuple[float, ...]
    """Grid scale factor coefficients."""


_APPENDIX_C = "NOAA Manual NOS NGS 5, Appendix C"

# --------------------------------------------------------------------------
# Michigan coefficients, transcribed from Appendix C.
#
# F(1) is printed as identical to the zone's ko in every case, which
# tests/test_polynomial.py checks against our independently derived k_origin -
# a free cross-check between the two engines at the central parallel.
# --------------------------------------------------------------------------

MI_NORTH_COEFFICIENTS = PolynomialCoefficients(
    zone_code="2111",
    citation=f"{_APPENDIX_C}, PDF p. 103 (MI N, zone 2111)",
    L=(111146.0908, 9.76397, 5.62053, 0.025777, 0.0007325),
    G=(8.997167538e-06, -7.11123e-15, -3.68190e-20, -1.3725e-27, 8.019e-35),
    F=(0.999902834466, 1.22919e-14, 6.70e-22),
)

MI_CENTRAL_COEFFICIENTS = PolynomialCoefficients(
    zone_code="2112",
    citation=f"{_APPENDIX_C}, PDF p. 103 (MI C, zone 2112)",
    L=(111120.9691, 9.77091, 5.62494, 0.023788),
    G=(8.999201531e-06, -7.12032e-15, -3.68711e-20, -1.3161e-27),
    F=(0.999912706253, 1.22939e-14, 6.25e-22),
)

MI_SOUTH_COEFFICIENTS = PolynomialCoefficients(
    zone_code="2113",
    citation=f"{_APPENDIX_C}, PDF p. 104 (MI S, zone 2113)",
    L=(111080.1507, 9.73761, 5.63002, 0.022802),
    G=(9.002508421e-06, -7.10459e-15, -3.69552e-20, -1.2067e-27),
    F=(0.999906878420, 1.23000e-14, 5.87e-22),
)

ALL_COEFFICIENTS: tuple[PolynomialCoefficients, ...] = (
    MI_NORTH_COEFFICIENTS,
    MI_CENTRAL_COEFFICIENTS,
    MI_SOUTH_COEFFICIENTS,
)

_BY_ZONE = {c.zone_code: c for c in ALL_COEFFICIENTS}


def coefficients_for(zone_code: str) -> PolynomialCoefficients:
    """Look up a zone's Appendix C coefficients, refusing an unknown zone."""
    key = str(zone_code).strip()
    try:
        return _BY_ZONE[key]
    except KeyError:
        known = ", ".join(sorted(_BY_ZONE))
        raise KeyError(
            f"No Appendix C polynomial coefficients for zone {zone_code!r}. "
            f"Coefficients are published for: {known}."
        ) from None


def _horner(coefficients: tuple[float, ...], x: float) -> float:
    """Evaluate c1*x + c2*x^2 + ... + cn*x^n.

    The manual suggests nested (Horner) form (PDF p. 54), which is both faster
    and better conditioned than summing the powers separately.
    """
    total = 0.0
    for coefficient in reversed(coefficients):
        total = (total + coefficient) * x
    return total


def forward(
    latitude: float,
    longitude: float,
    constants: LambertConstants,
    coefficients: PolynomialCoefficients,
) -> GridPoint:
    """Geodetic to grid, manual section 3.41 (PDF pp. 54-55).

        delta_phi = phi - B_0            (decimal degrees)
        u         = L1 d + L2 d^2 + ...  (meters)
        R         = R_0 - u
        gamma     = (L_0 - lambda) sin B_0
        E'        = R sin gamma
        N'        = u + E' tan(gamma / 2)
        E         = E' + E_0
        N         = N' + N_0
        k         = F1 + F2 u^2 + F3 u^3
    """
    if not -90.0 < latitude < 90.0:
        raise ValueError(
            f"Latitude {latitude} is not a valid geodetic latitude; it must lie "
            f"strictly between -90 and 90 degrees."
        )

    delta_phi = latitude - constants.lat_origin
    u = _horner(coefficients.L, delta_phi)
    R = constants.R_origin - u

    # Same longitude sign handling as the rigorous engine: the manual writes
    # (L_0 - lambda) with longitude positive west; ours is negative west.
    convergence = (longitude - constants.lon_origin) * constants.sin_lat_origin
    gamma = math.radians(convergence)

    easting_prime = R * math.sin(gamma)
    northing_prime = u + easting_prime * math.tan(gamma / 2.0)

    return GridPoint(
        northing=northing_prime + constants.northing_origin,
        easting=easting_prime + constants.easting_origin,
        convergence=convergence,
        scale_factor=_scale_factor(u, coefficients),
    )


def inverse(
    northing: float,
    easting: float,
    constants: LambertConstants,
    coefficients: PolynomialCoefficients,
) -> GeodeticPoint:
    """Grid to geodetic, manual section 3.42 (PDF p. 55).

        N'        = N - N_0
        E'        = E - E_0
        R'        = R_0 - N'
        gamma     = atan(E' / R')
        lambda    = L_0 - gamma / sin B_0
        u         = N' - E' tan(gamma / 2)
        delta_phi = G1 u + G2 u^2 + ...  (decimal degrees)
        phi       = B_0 + delta_phi
        k         = F1 + F2 u^2 + F3 u^3
    """
    northing_prime = northing - constants.northing_origin
    easting_prime = easting - constants.easting_origin
    R_prime = constants.R_origin - northing_prime

    if R_prime <= 0.0:
        raise ValueError(
            f"Northing {northing} m is at or beyond the apex of the projection "
            f"cone for this zone. No geodetic position corresponds to it."
        )

    gamma = math.atan(easting_prime / R_prime)
    convergence = math.degrees(gamma)
    longitude = constants.lon_origin + convergence / constants.sin_lat_origin

    u = northing_prime - easting_prime * math.tan(gamma / 2.0)
    delta_phi = _horner(coefficients.G, u)

    return GeodeticPoint(
        latitude=constants.lat_origin + delta_phi,
        longitude=longitude,
        convergence=convergence,
        scale_factor=_scale_factor(u, coefficients),
    )


def _scale_factor(u: float, coefficients: PolynomialCoefficients) -> float:
    """k = F1 + F2 u^2 + F3 u^3, manual sections 3.41 and 3.42.

    Note the series starts at F1 as a constant term and skips the linear term
    entirely - it is not the same shape as the L and G series, so it is written
    out rather than passed through _horner.
    """
    F1, F2, F3 = coefficients.F
    return F1 + u * u * (F2 + F3 * u)
