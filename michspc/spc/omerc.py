"""Hotine oblique Mercator, with the false coordinates AT THE CENTRE.

NOAA Manual NOS NGS 5, section 3.3 (PDF pp. 48-52):

  * 3.32 conformal-latitude series          (PDF p. 49)
  * 3.33 computation of zone constants      (PDF pp. 49-50)
  * 3.34 direct conversion, phi/lambda -> N/E    (PDF pp. 50-51)
  * 3.35 inverse conversion, N/E -> phi/lambda   (PDF pp. 51-52)

Michigan's statewide SPCS2022 zone 260001 is this projection: centre
45 N / 86 W, skew azimuth -26 degrees, scale 0.999800 at the centre.

**THE VARIANT IS THE DANGEROUS PART, and it is not the manual's.** Section 3.3
presents the NATURAL-ORIGIN Hotine: its false coordinates apply where the
initial line crosses the equator, so at Alaska zone 1's own projection centre
the manual's equations return u = 6,968,872.111 m, not the false northing.
NGS's SPCS2022 designation is **OMC**, glossed on the zone-definitions page as
"Hotine Oblique Mercator, center" (EPSG 9815 variant B), which fixes the false
coordinates AT THE PROJECTION CENTRE. Building the manual's form and calling it
OMC misplaces every point in Michigan by about 6,969 km - a number so large it
would be caught, but the reason it is stated here is that nothing in section 3.3
says any of this. The frozen centre anchor (762,000.000 m / 1,524,000.000 m,
exactly 2,500,000 / 5,000,000 international feet) is the discriminator, and
tests/test_projection_engines.py pins it.

The centre offset is applied as a subtraction of ``u_c``, the u-coordinate of
the projection centre, before the rotation into (N, E). **``u_c`` is obtained by
running this module's own forward u at the centre**, rather than transcribing a
second closed formula for it. That is exact - the centre's u is what the direct
equations say it is - and it is self-consistent by construction: whatever the
forward equations compute at the centre is exactly what is subtracted, so
"the centre lands on the false coordinates" cannot come apart from "the forward
equations are these". A separately transcribed formula could disagree with them,
and the disagreement would be a smooth offset in every coordinate.

Two further flags carried from the extraction of section 3.3
(review/nsrs-h1-manual/TM-OM-EXTRACTION.md section 2):

  * The manual takes ``cos alpha_0 = +sqrt(1 - sin^2 alpha_0)``, silently
    assuming |alpha_0| < 90 degrees. That assumption is CHECKED here against the
    zone's own parameters rather than inherited.
  * ``alpha_c`` enters twice - defining the skew, and as the rotation angle from
    the (u, v) skew axes to (N, E). NGS publishes Michigan's azimuth and its
    rectified-skew angle as the same -26 degrees, so one field legitimately
    supplies both roles here; the rotation says so at the line where it happens.

Conventions, matching michspc.spc.lambert and michspc.spc.projection:
  * Latitudes and longitudes at the API boundary are decimal degrees.
  * Longitude is signed, NEGATIVE WEST. The manual uses positive-west; the FOUR
    places that conversion matters are marked below (one of them is the
    transcription of lambda_c itself, which happens in the zone registry).
  * ``alpha_c`` is an AZIMUTH, not a longitude, and is unaffected by that
    convention.
  * Linear units are meters.
  * Convergence is decimal degrees, positive east of the central meridian.
  * Neither direction iterates.

What verifies this module is external and lives in the test suite: Alaska zone
1's seven published zone constants (PDF p. 50) recomputed from its defining
parameters, and the nine frozen beta NCAT anchors for zone 260001, deliberately
asymmetric about the centre so the skew sign and the variant cannot both be
wrong and still pass (tests/fixtures/spcs2022_engine_anchors.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property

from michspc.spc.ellipsoid import GRS80, Ellipsoid
from michspc.spc.projection import (
    GeodeticPoint,
    GridPoint,
    _require_finite_grid,
    _require_valid_geodetic,
)
from michspc.spc.zones import ObliqueMercatorCenterDef


@dataclass(frozen=True)
class ObliqueMercatorConstants:
    """Zone constants derived once per zone, manual section 3.33 (PDF pp. 49-50).

    Only the defining constants are stored; B, A, C, D, F, G, I, lambda_0 and
    u_c are derived on demand and cached, so each has one authoritative
    representation and none can drift out of agreement with the definition.

    Alaska zone 1 (PDF p. 50) publishes B, C, D, F, G, I and lambda_0 as a test
    vector for this derivation; tests/test_projection_engines.py reproduces it.
    """

    ellipsoid: Ellipsoid

    lat_center: float
    """phi_c - latitude of the projection centre, decimal degrees north."""

    lon_center: float
    """lambda_c - longitude of the centre, decimal degrees, NEGATIVE WEST."""

    skew_azimuth: float
    """alpha_c - azimuth of the initial line at the centre, decimal degrees."""

    k_center: float
    """k_c - grid scale factor at the projection centre."""

    northing_center: float
    """N_c - northing assigned to the projection centre, meters."""

    easting_center: float
    """E_c - easting assigned to the projection centre, meters."""

    zone_code: str | None = None
    """The zone these constants belong to, when they came from a registry zone.

    Carried for the same reason ``LambertConstants`` carries it: constants can
    never be silently paired with a different zone's identity.
    """

    # ------------------------------------------------------------------
    # Section 3.32, PDF p. 49 - the conformal-latitude series used by the
    # inverse only. A DISTINCT NAMESPACE from section 3.23's TM scale
    # coefficients, which also print as F2 and F4; these are named
    # ``conformal_F*`` so the two can never be read as the same quantity.
    # GRS 80 printed values are given beside each.
    # ------------------------------------------------------------------

    @cached_property
    def _c(self) -> tuple[float, float, float, float]:
        """c2, c4, c6, c8 (PDF p. 49).

            c2 = e^2/2 + 5e^4/24 + e^6/12 + 13e^8/360
            c4 = 7e^4/48 + 29e^6/240 + 811e^8/11520
            c6 = 7e^6/120 + 81e^8/1120
            c8 = 4279e^8/161280
        """
        e2 = self.ellipsoid.e2
        e4 = e2 * e2
        e6 = e4 * e2
        e8 = e4 * e4
        return (
            e2 / 2.0 + 5.0 * e4 / 24.0 + e6 / 12.0 + 13.0 * e8 / 360.0,
            7.0 * e4 / 48.0 + 29.0 * e6 / 240.0 + 811.0 * e8 / 11520.0,
            7.0 * e6 / 120.0 + 81.0 * e8 / 1120.0,
            4279.0 * e8 / 161280.0,
        )

    @cached_property
    def conformal_F0(self) -> float:
        """F0 = 2(c2 - 2c4 + 3c6 - 4c8). GRS 80: 0.00668 69209 27 (PDF p. 49)."""
        c2, c4, c6, c8 = self._c
        return 2.0 * (c2 - 2.0 * c4 + 3.0 * c6 - 4.0 * c8)

    @cached_property
    def conformal_F2(self) -> float:
        """F2 = 8(c4 - 4c6 + 10c8). GRS 80: 0.00005 20145 84 (PDF p. 49)."""
        _, c4, c6, c8 = self._c
        return 8.0 * (c4 - 4.0 * c6 + 10.0 * c8)

    @cached_property
    def conformal_F4(self) -> float:
        """F4 = 32(c6 - 6c8). GRS 80: 0.00000 05544 30 (PDF p. 49)."""
        _, _, c6, c8 = self._c
        return 32.0 * (c6 - 6.0 * c8)

    @cached_property
    def conformal_F6(self) -> float:
        """F6 = 128 c8. GRS 80: 0.00000 00068 20 (PDF p. 49)."""
        return 128.0 * self._c[3]

    # ------------------------------------------------------------------
    # Section 3.33, PDF pp. 49-50 - the zone constants.
    # ------------------------------------------------------------------

    @cached_property
    def _sin_lat_center(self) -> float:
        return math.sin(math.radians(self.lat_center))

    @cached_property
    def _cos_lat_center(self) -> float:
        return math.cos(math.radians(self.lat_center))

    @cached_property
    def B(self) -> float:
        """B = (1 + e'^2 cos^4 phi_c)^(1/2) (PDF p. 49)."""
        cos_c = self._cos_lat_center
        return math.sqrt(1.0 + self.ellipsoid.e2_prime * cos_c**4)

    @cached_property
    def W_center(self) -> float:
        """W_c = (1 - e^2 sin^2 phi_c)^(1/2) (PDF p. 49)."""
        return self.ellipsoid.W(self._sin_lat_center)

    @cached_property
    def A(self) -> float:
        """A = a B (1 - e^2)^(1/2) / W_c^2 (PDF p. 49)."""
        return (
            self.ellipsoid.a
            * self.B
            * math.sqrt(1.0 - self.ellipsoid.e2)
            / (self.W_center * self.W_center)
        )

    @cached_property
    def Q_center(self) -> float:
        """Q_c - isometric latitude at phi_c (PDF p. 49).

        Character-identical to the Lambert section 3.12 quantity, so it comes
        from the same ``Ellipsoid.isometric_latitude`` rather than a second
        transcription of the same formula.
        """
        return self.ellipsoid.isometric_latitude(self._sin_lat_center)

    @cached_property
    def C(self) -> float:
        """C = arcosh[B(1 - e^2)^(1/2) / (W_c cos phi_c)] - B Q_c (PDF p. 49)."""
        argument = (
            self.B
            * math.sqrt(1.0 - self.ellipsoid.e2)
            / (self.W_center * self._cos_lat_center)
        )
        return math.acosh(argument) - self.B * self.Q_center

    @cached_property
    def D(self) -> float:
        """D = k_c A / B (PDF p. 50)."""
        return self.k_center * self.A / self.B

    @cached_property
    def F(self) -> float:
        """F = sin alpha_0, where

            sin alpha_0 = a sin(alpha_c) cos(phi_c) / (A W_c)      (PDF p. 50)

        alpha_0 is the azimuth of the initial line where it crosses the equator.
        """
        return (
            self.ellipsoid.a
            * math.sin(math.radians(self.skew_azimuth))
            * self._cos_lat_center
            / (self.A * self.W_center)
        )

    @cached_property
    def G(self) -> float:
        """G = cos alpha_0 (PDF p. 50).

        The manual takes the POSITIVE root, which silently assumes
        |alpha_0| < 90 degrees. ``from_definition`` refuses a zone for which
        that assumption does not hold, so the sign is a checked property here
        rather than an inherited one.
        """
        return math.sqrt(1.0 - self.F * self.F)

    @cached_property
    def I(self) -> float:  # noqa: E743 - the manual's own symbol
        """I = k_c A / a (PDF p. 50). Used only by the scale factor."""
        return self.k_center * self.A / self.ellipsoid.a

    @cached_property
    def lon_origin(self) -> float:
        """lambda_0 - longitude where the initial line crosses the equator.

        Manual (PDF p. 50), POSITIVE WEST:

            lambda_0 = lambda_c + arcsin[sin alpha_0 sinh(B Q_c + C) / cos alpha_0] / B

        DEVIATION POINT 1 of 4 from the manual's longitude convention: with
        longitudes negative west, lambda_c and lambda_0 both change sign, so the
        addition becomes a subtraction. Decimal degrees, NEGATIVE WEST.
        """
        offset = math.asin(
            self.F * math.sinh(self.B * self.Q_center + self.C) / self.G
        )
        return self.lon_center - math.degrees(offset) / self.B

    @cached_property
    def u_center(self) -> float:
        """u_c - the u-coordinate of the projection centre, meters.

        This is what makes the projection the CENTRE variant. It is computed by
        running this module's own ``_skew_coordinates`` at (phi_c, lambda_c),
        not by a second transcribed formula, so the value subtracted is by
        construction the value the forward equations produce there. See the
        module docstring.
        """
        return _skew_coordinates(self.lat_center, self.lon_center, self).u

    @classmethod
    def from_definition(
        cls,
        definition: ObliqueMercatorCenterDef,
        ellipsoid: Ellipsoid = GRS80,
    ) -> ObliqueMercatorConstants:
        """Build the constants from a zone's published defining parameters.

        Refuses, rather than inheriting, the two assumptions section 3.3 makes
        silently and the two the arithmetic makes.
        """
        if not -90.0 < definition.lat_center < 90.0:
            raise ValueError(
                f"An oblique Mercator zone needs a centre latitude strictly "
                f"between the poles; this zone gives phi_c = "
                f"{definition.lat_center!r} degrees. The definition refused is "
                f"{definition!r}."
            )
        if not definition.k_center > 0.0:
            raise ValueError(
                f"A grid scale factor must be positive; this zone gives "
                f"k_c = {definition.k_center!r}. A zero or negative scale "
                f"factor would collapse or reflect the grid rather than scale "
                f"it. The definition refused is {definition!r}."
            )
        # The manual's own silent assumption, made explicit. |alpha_c| = 90
        # degrees is an initial line running due east-west through the centre;
        # the equations take cos(alpha_0) as the POSITIVE root, which is only
        # the right branch while the line trends more north than east.
        if not -90.0 < definition.skew_azimuth < 90.0:
            raise ValueError(
                f"This zone's skew azimuth is alpha_c = "
                f"{definition.skew_azimuth!r} degrees. Section 3.3 of NOAA "
                f"Manual NOS NGS 5 takes cos(alpha_0) as the positive square "
                f"root, which assumes |alpha_0| < 90 degrees, and that holds "
                f"only while the initial line trends more north than east "
                f"(|alpha_c| < 90). At or past 90 degrees the equations return "
                f"the wrong branch and produce an ordinary-looking coordinate "
                f"reflected about the initial line. The definition refused is "
                f"{definition!r}."
            )

        constants = cls(
            ellipsoid=ellipsoid,
            lat_center=definition.lat_center,
            lon_center=definition.lon_center,
            skew_azimuth=definition.skew_azimuth,
            k_center=definition.k_center,
            northing_center=definition.northing_center,
            easting_center=definition.easting_center,
        )

        # And the arithmetic assumption: sin(alpha_0) must be a real sine, or
        # G = sqrt(1 - F^2) is the square root of a negative number and
        # lambda_0's arcsin has no value. Evaluated here so a zone refuses when
        # its constants are built rather than at the first point converted.
        if not -1.0 < constants.F < 1.0:
            raise ValueError(
                f"This zone's defining parameters give sin(alpha_0) = "
                f"{constants.F!r}, which is not the sine of any angle. No "
                f"oblique Mercator initial line corresponds to them. The "
                f"definition refused is {definition!r}."
            )

        return constants


@dataclass(frozen=True)
class _SkewPoint:
    """The section 3.34 working quantities at one position, computed once.

    ``forward`` needs all five: u and v become the grid coordinates, and L, J
    and K are what the convergence and scale factor are built from. Computing
    them in one place rather than twice is not tidiness - two evaluations of
    ``sinh(BQ + C)`` in one function are two representations of one fact, and a
    later edit to one of them would move the coordinate without moving the
    convergence that describes it.
    """

    u: float
    v: float
    L: float
    """(lambda_0 - lambda) B, radians."""

    J: float
    """sinh(B Q + C)."""

    K: float
    """cosh(B Q + C)."""


def _skew_coordinates(
    latitude: float, longitude: float, constants: ObliqueMercatorConstants
) -> _SkewPoint:
    """(u, v) on the skew axes, manual section 3.34 (PDF pp. 50-51).

        L = (lambda_0 - lambda) B                 [see the sign note below]
        Q = isometric latitude at phi
        J = sinh(B Q + C)      K = cosh(B Q + C)
        u = D arctan[(J G - F sin L) / cos L]
        v = (D/2) ln[(K - F J - G sin L) / (K + F J + G sin L)]

    Separated from ``forward`` because the centre's own u is needed to build the
    constants, and computing it any other way would let the offset and the
    equations disagree. Radians are used internally; the arguments are decimal
    degrees, longitude negative west.
    """
    # DEVIATION POINT 2 of 4. Section 3.34 writes L = (lambda - lambda_0) B with
    # longitude POSITIVE WEST; negating both longitudes reverses the
    # subtraction. L is the same physical quantity either way.
    L = math.radians(constants.lon_origin - longitude) * constants.B

    sin_lat = math.sin(math.radians(latitude))
    Q = constants.ellipsoid.isometric_latitude(sin_lat)
    argument = constants.B * Q + constants.C
    J = math.sinh(argument)
    K = math.cosh(argument)

    sin_L = math.sin(L)
    cos_L = math.cos(L)

    # atan2, not atan: the manual's arctan of a quotient loses the quadrant, and
    # cos L passes through zero a quarter turn along the initial line. Michigan
    # never reaches it, but a bare atan would fold the far side of the
    # projection back onto the near side silently rather than refusing.
    u = constants.D * math.atan2(J * constants.G - constants.F * sin_L, cos_L)

    numerator = K - constants.F * J - constants.G * sin_L
    denominator = K + constants.F * J + constants.G * sin_L
    if not numerator > 0.0 or not denominator > 0.0:
        raise ValueError(
            f"Latitude {latitude!r}, longitude {longitude!r} lies on or beyond "
            f"the oblique Mercator's own pole for this zone: the logarithm in "
            f"the v-coordinate would take {numerator!r} / {denominator!r}. The "
            f"projection maps that point to infinity, so no grid coordinate "
            f"corresponds to it."
        )
    v = 0.5 * constants.D * math.log(numerator / denominator)

    return _SkewPoint(u=u, v=v, L=L, J=J, K=K)


def forward(
    latitude: float, longitude: float, constants: ObliqueMercatorConstants
) -> GridPoint:
    """Geodetic to grid. Manual section 3.34 (PDF pp. 50-51), CENTRE variant.

        N = (u - u_c) cos alpha_c - v sin alpha_c + N_c
        E = (u - u_c) sin alpha_c + v cos alpha_c + E_c
        gamma = arctan[(F - J G sin L) / (K G cos L)] - alpha_c
        k = I (1 - e^2 sin^2 phi)^(1/2) cos(u/D) / (cos phi cos L)

    The manual's own rotation has no ``u_c`` term and offsets by the natural
    origin's false coordinates; the subtraction of ``u_c`` and the use of the
    centre's own false coordinates are what make this the OMC variant. See the
    module docstring.

    ``latitude`` and ``longitude`` are decimal degrees, longitude negative west.
    """
    _require_valid_geodetic(latitude, longitude)

    skew = _skew_coordinates(latitude, longitude, constants)

    # alpha_c in BOTH of its roles: it defined the skew (through sin alpha_0 in
    # the constants above) and it is the rectified-skew angle that rotates the
    # (u, v) axes onto (N, E). NGS publishes Michigan's statewide zone with
    # azimuth and rectified-skew angle equal, both -26 degrees, so one stored
    # field supplies both roles for this zone. They are not equal in general;
    # a zone that published them separately would need a second field, and this
    # comment is the place that would be noticed.
    alpha_c = math.radians(constants.skew_azimuth)
    sin_alpha = math.sin(alpha_c)
    cos_alpha = math.cos(alpha_c)

    u_offset = skew.u - constants.u_center
    northing = u_offset * cos_alpha - skew.v * sin_alpha + constants.northing_center
    easting = u_offset * sin_alpha + skew.v * cos_alpha + constants.easting_center

    # Convergence and scale are properties of the point, not of the false
    # origin, so they are computed from the UN-OFFSET u and from L exactly as
    # section 3.34 gives them. Moving the false origin moves the coordinates and
    # changes neither of these.
    sin_lat = math.sin(math.radians(latitude))
    cos_lat = math.cos(math.radians(latitude))

    convergence = math.degrees(
        math.atan2(
            constants.F - skew.J * constants.G * math.sin(skew.L),
            skew.K * constants.G * math.cos(skew.L),
        )
        - alpha_c
    )

    scale_factor = (
        constants.I
        * math.sqrt(1.0 - constants.ellipsoid.e2 * sin_lat * sin_lat)
        * math.cos(skew.u / constants.D)
        / (cos_lat * math.cos(skew.L))
    )

    return GridPoint(
        northing=northing,
        easting=easting,
        convergence=convergence,
        scale_factor=scale_factor,
    )


def inverse(
    northing: float, easting: float, constants: ObliqueMercatorConstants
) -> GeodeticPoint:
    """Grid to geodetic. Manual section 3.35 (PDF pp. 51-52), CENTRE variant.

        u = (E - E_c) sin alpha_c + (N - N_c) cos alpha_c + u_c
        v = (E - E_c) cos alpha_c - (N - N_c) sin alpha_c
        R = sinh(v/D)   S = cosh(v/D)   T = sin(u/D)
        Q = [ (1/2) ln((S - R F + G T) / (S + R F - G T)) - C ] / B
        chi = 2 arctan[(e^Q - 1) / (e^Q + 1)]
        phi = chi + sin chi cos chi (F0 + F2 cos^2 chi + F4 cos^4 chi
                                        + F6 cos^6 chi)
        lambda = lambda_0 + (1/B) arctan[(R G + T F) / cos(u/D)]

    The manual's own inverse rotation subtracts the natural origin's false
    coordinates and has no ``+ u_c``; both changes are the exact inverse of what
    ``forward`` does, and the two must move together.

    Convergence and scale factor have no separate inverse series in section 3.3
    - the manual says to re-run the direct equations on the recovered position,
    which is what happens here.

    ``northing`` and ``easting`` are meters.
    """
    _require_finite_grid(northing, easting)

    alpha_c = math.radians(constants.skew_azimuth)
    sin_alpha = math.sin(alpha_c)
    cos_alpha = math.cos(alpha_c)

    delta_n = northing - constants.northing_center
    delta_e = easting - constants.easting_center

    u = delta_e * sin_alpha + delta_n * cos_alpha + constants.u_center
    v = delta_e * cos_alpha - delta_n * sin_alpha

    R = math.sinh(v / constants.D)
    S = math.cosh(v / constants.D)
    T = math.sin(u / constants.D)

    numerator = S - R * constants.F + constants.G * T
    denominator = S + R * constants.F - constants.G * T
    if not numerator > 0.0 or not denominator > 0.0:
        raise ValueError(
            f"Northing {northing} m and easting {easting} m are at or beyond "
            f"the oblique Mercator's own pole for this zone: the logarithm "
            f"recovering the isometric latitude would take {numerator!r} / "
            f"{denominator!r}. No geodetic position corresponds. Check that the "
            f"northing and easting are not transposed and that the correct zone "
            f"and unit were selected."
        )

    Q = (0.5 * math.log(numerator / denominator) - constants.C) / constants.B

    # chi, the conformal latitude: 2 arctan[(e^Q - 1)/(e^Q + 1)]. Written with
    # the exponential clamped only by Q's own finiteness; a Q large enough to
    # overflow exp is refused above, because it needs a v beyond the pole.
    exp_q = math.exp(Q)
    chi = 2.0 * math.atan((exp_q - 1.0) / (exp_q + 1.0))

    sin_chi = math.sin(chi)
    cos_chi = math.cos(chi)
    c2 = cos_chi * cos_chi
    lat_radians = chi + sin_chi * cos_chi * (
        constants.conformal_F0
        + c2
        * (
            constants.conformal_F2
            + c2 * (constants.conformal_F4 + c2 * constants.conformal_F6)
        )
    )

    # DEVIATION POINT 3 of 4. Section 3.35 writes
    # lambda = lambda_0 - (1/B) arctan[...] with longitude POSITIVE WEST;
    # negating both longitudes turns the subtraction into an addition. This is
    # the exact inverse of ``_skew_coordinates``'s L, and the two must change
    # together. atan2 again, for the quadrant.
    #
    # (DEVIATION POINT 4 of 4 is the transcription of lambda_c itself, which
    # happens once in the zone registry - michspc.spc.zones - where every
    # longitude in this codebase is converted to negative west.)
    longitude = constants.lon_origin + math.degrees(
        math.atan2(R * constants.G + T * constants.F, math.cos(u / constants.D))
        / constants.B
    )

    latitude = math.degrees(lat_radians)

    # Section 3.3 gives no inverse series for gamma and k; the manual's own
    # instruction is to evaluate the direct equations at the recovered position.
    recovered = forward(latitude, longitude, constants)

    return GeodeticPoint(
        latitude=latitude,
        longitude=longitude,
        convergence=recovered.convergence,
        scale_factor=recovered.scale_factor,
    )
