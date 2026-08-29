"""Transverse Mercator mapping equations - the rigorous series form.

NOAA Manual NOS NGS 5, section 3.2 (PDF pp. 42-48):

  * 3.21 notation                          (PDF pp. 42-43)
  * 3.22 computation of zone constants     (PDF pp. 43-44)
  * 3.23 direct conversion, phi/lambda -> N/E   (PDF pp. 44-45)
  * 3.24 inverse conversion, N/E -> phi/lambda  (PDF pp. 45-46)

Five of Michigan's eighteen SPCS2022 low-distortion zones are transverse
Mercator (NGS's abbreviation **TM**); no SPCS 83 Michigan zone is.

**Every series term is kept, unconditionally.** The manual calls A6, A7, C5, F4
and B6, B7, D5, G4 negligible - but it says so *inside SPCS 83 zone bounds*
(PDF pp. 45, 47), and Michigan's SPCS2022 zones are not those zones. Dropping a
term because a sentence written about different zones called it small is exactly
the kind of inherited assumption this program refuses; keeping them costs a few
multiplications per point. Section 3.24's approximate scale factor
``k = k_0 + E'^2 / 2 r_0^2`` is likewise NOT used - the full series is.

**Neither direction iterates.** The inverse uses the manual's closed footpoint
series, so there is no convergence loop here and no ceiling to tune.

Two name collisions with michspc.spc.lambert are worth stating, because both
are the manual's own and both would be silent if mixed up (section 3.21):

  * ``R`` here is the radius of curvature in the prime vertical scaled to the
    grid, ``k_0 a / W`` - not Lambert's mapping radius.
  * ``Q`` here is ``E' / R_f``, a dimensionless ratio - not the isometric
    latitude that carries the same letter in section 3.12.

Conventions, matching michspc.spc.lambert and michspc.spc.projection:
  * Latitudes and longitudes at the API boundary are decimal degrees.
  * Longitude is signed, NEGATIVE WEST. The manual uses positive-west; the TWO
    places that conversion matters are marked below.
  * Linear units are meters.
  * Convergence is decimal degrees, positive east of the central meridian.

What verifies this module is external and lives in the test suite: Table 3.22's
published S_0 values for three SPCS 83 TM zones, recomputed from their defining
constants alone, and the frozen beta NCAT anchors for Michigan's five SPCS2022
TM zones (tests/fixtures/spcs2022_engine_anchors.py).
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
from michspc.spc.zones import TransverseMercatorDef


def _require_usable_cos_latitude(cos_lat: float, latitude: float) -> None:
    """Refuse a latitude whose cosine has rounded onto a pole.

    The transverse Mercator divides by cos(phi) (in ``L``, and again when the
    inverse recovers a longitude) and takes tan(phi). At a pole neither exists:
    the whole meridian collapses to a point and no longitude corresponds. The
    domain check in ``projection`` admits any latitude strictly inside
    (-90, 90), which for a double keeps cos(phi) strictly positive - but "no
    bare arithmetic error escapes the core" is not a rule with a latitude
    qualifier, and this is where a ZeroDivisionError would otherwise appear.

    Stated as a containment test so a NaN is refused too, and it names the
    latitude the caller passed rather than its cosine, because that is the
    number in the file.
    """
    if not cos_lat > 0.0:
        raise ValueError(
            f"Latitude {latitude!r} is at or within a rounding step of a pole: "
            f"its cosine is {cos_lat!r}, and a transverse Mercator divides by "
            f"it. Every longitude meets at a pole, so no grid coordinate "
            f"corresponds. Check that the latitude column holds decimal degrees "
            f"and was not swapped with another field."
        )


@dataclass(frozen=True)
class TransverseMercatorConstants:
    """Zone constants derived once per zone, manual section 3.22 (PDF p. 43).

    Only the defining constants are stored. Everything the mapping equations
    consume - the third flattening, the rectifying-sphere radius, the two
    coefficient series and S_0 - is derived on demand and cached, so there is
    one authoritative representation of each and no stored copy can drift out of
    agreement with the definition it came from.

    Table 3.22 (PDF p. 44) publishes S_0 for all forty SPCS 83 transverse
    Mercator zones. That table plays the role Appendix C plays for the Lambert
    zones: an NGS-computed derived constant this module must reproduce from the
    defining constants alone, checked in tests/test_projection_engines.py.
    """

    ellipsoid: Ellipsoid

    lat_grid_origin: float
    """phi_0 - grid origin latitude, decimal degrees north. Manual's ``Bo``."""

    lon_origin: float
    """lambda_0 - central meridian, decimal degrees, NEGATIVE WEST."""

    k_origin: float
    """k_0 - grid scale factor on the central meridian."""

    northing_grid_origin: float
    """N_0 - northing assigned to phi_0 on the central meridian, meters."""

    easting_origin: float
    """E_0 - easting assigned to the central meridian, meters."""

    zone_code: str | None = None
    """The zone these constants belong to, when they came from a registry zone.

    Carried for the same reason ``LambertConstants`` carries it: constants can
    never be silently paired with a different zone's identity.
    """

    # ------------------------------------------------------------------
    # Section 3.22 (PDF p. 43). The printed GRS 80 values are given beside each
    # coefficient so the transcription can be checked against the page at a
    # glance; the test suite pins them.
    # ------------------------------------------------------------------

    @cached_property
    def _u(self) -> tuple[float, float, float, float]:
        """u2, u4, u6, u8 - the rectifying-latitude coefficients (PDF p. 43).

            u2 = -3n/2 + 9n^3/16       u4 = 15n^2/16 - 15n^4/32
            u6 = -35n^3/48             u8 = 315n^4/512
        """
        n = self.ellipsoid.n
        n2 = n * n
        n3 = n2 * n
        n4 = n2 * n2
        return (
            -3.0 * n / 2.0 + 9.0 * n3 / 16.0,
            15.0 * n2 / 16.0 - 15.0 * n4 / 32.0,
            -35.0 * n3 / 48.0,
            315.0 * n4 / 512.0,
        )

    @cached_property
    def _v(self) -> tuple[float, float, float, float]:
        """v2, v4, v6, v8 - the footpoint-latitude coefficients (PDF p. 43).

            v2 = 3n/2 - 27n^3/32       v4 = 21n^2/16 - 55n^4/32
            v6 = 151n^3/96             v8 = 1097n^4/512
        """
        n = self.ellipsoid.n
        n2 = n * n
        n3 = n2 * n
        n4 = n2 * n2
        return (
            3.0 * n / 2.0 - 27.0 * n3 / 32.0,
            21.0 * n2 / 16.0 - 55.0 * n4 / 32.0,
            151.0 * n3 / 96.0,
            1097.0 * n4 / 512.0,
        )

    @cached_property
    def U0(self) -> float:
        """U0 = 2(u2 - 2u4 + 3u6 - 4u8). GRS 80: -0.00504 82507 76 (PDF p. 43)."""
        u2, u4, u6, u8 = self._u
        return 2.0 * (u2 - 2.0 * u4 + 3.0 * u6 - 4.0 * u8)

    @cached_property
    def U2(self) -> float:
        """U2 = 8(u4 - 4u6 + 10u8). GRS 80: 0.00002 12592 04 (PDF p. 43)."""
        _, u4, u6, u8 = self._u
        return 8.0 * (u4 - 4.0 * u6 + 10.0 * u8)

    @cached_property
    def U4(self) -> float:
        """U4 = 32(u6 - 6u8). GRS 80: -0.00000 01114 23 (PDF p. 43)."""
        _, _, u6, u8 = self._u
        return 32.0 * (u6 - 6.0 * u8)

    @cached_property
    def U6(self) -> float:
        """U6 = 128 u8. GRS 80: 0.00000 00006 26 (PDF p. 43)."""
        return 128.0 * self._u[3]

    @cached_property
    def V0(self) -> float:
        """V0 = 2(v2 - 2v4 + 3v6 - 4v8). GRS 80: 0.00502 28939 48 (PDF p. 43)."""
        v2, v4, v6, v8 = self._v
        return 2.0 * (v2 - 2.0 * v4 + 3.0 * v6 - 4.0 * v8)

    @cached_property
    def V2(self) -> float:
        """V2 = 8(v4 - 4v6 + 10v8). GRS 80: 0.00002 93706 25 (PDF p. 43)."""
        _, v4, v6, v8 = self._v
        return 8.0 * (v4 - 4.0 * v6 + 10.0 * v8)

    @cached_property
    def V4(self) -> float:
        """V4 = 32(v6 - 6v8). GRS 80: 0.00000 02350 59 (PDF p. 43)."""
        _, _, v6, v8 = self._v
        return 32.0 * (v6 - 6.0 * v8)

    @cached_property
    def V6(self) -> float:
        """V6 = 128 v8. GRS 80: 0.00000 00021 81 (PDF p. 43)."""
        return 128.0 * self._v[3]

    @cached_property
    def r(self) -> float:
        """r - radius of the rectifying sphere, meters (PDF p. 43).

            r = a(1 - n)(1 - n^2)(1 + 9n^2/4 + 225n^4/64)

        GRS 80: 6,367,449.14577 m, printed on the same page.
        """
        n = self.ellipsoid.n
        n2 = n * n
        n4 = n2 * n2
        return (
            self.ellipsoid.a
            * (1.0 - n)
            * (1.0 - n2)
            * (1.0 + 9.0 * n2 / 4.0 + 225.0 * n4 / 64.0)
        )

    @cached_property
    def omega_grid_origin(self) -> float:
        """omega_0 - rectifying latitude at phi_0, radians (PDF p. 43)."""
        return self.rectifying_latitude(math.radians(self.lat_grid_origin))

    @cached_property
    def S0(self) -> float:
        """S_0 = k_0 omega_0 r - meridional distance to the grid origin, meters.

        Manual section 3.22 (PDF p. 43); Table 3.22 (PDF p. 44) publishes this
        value for every SPCS 83 transverse Mercator zone.
        """
        return self.k_origin * self.omega_grid_origin * self.r

    def rectifying_latitude(self, lat_radians: float) -> float:
        """omega, manual section 3.22 (PDF p. 43).

            omega = phi + sin phi cos phi (U0 + U2 cos^2 phi + U4 cos^4 phi
                                              + U6 cos^6 phi)

        Radians in, radians out.
        """
        sin_lat = math.sin(lat_radians)
        cos_lat = math.cos(lat_radians)
        c2 = cos_lat * cos_lat
        return lat_radians + sin_lat * cos_lat * (
            self.U0 + c2 * (self.U2 + c2 * (self.U4 + c2 * self.U6))
        )

    def footpoint_latitude(self, omega: float) -> float:
        """phi_f from omega, manual section 3.24 (PDF p. 45).

            phi_f = omega + sin omega cos omega (V0 + V2 cos^2 omega
                                                    + V4 cos^4 omega
                                                    + V6 cos^6 omega)

        The closed inverse of ``rectifying_latitude``; no iteration.
        Radians in, radians out.
        """
        sin_w = math.sin(omega)
        cos_w = math.cos(omega)
        c2 = cos_w * cos_w
        return omega + sin_w * cos_w * (
            self.V0 + c2 * (self.V2 + c2 * (self.V4 + c2 * self.V6))
        )

    @classmethod
    def from_definition(
        cls,
        definition: TransverseMercatorDef,
        ellipsoid: Ellipsoid = GRS80,
    ) -> TransverseMercatorConstants:
        """Build the constants from a zone's published defining parameters."""
        if not -90.0 < definition.lat_grid_origin < 90.0:
            raise ValueError(
                f"A transverse Mercator zone needs a grid origin latitude "
                f"strictly between the poles; this zone gives phi_0 = "
                f"{definition.lat_grid_origin!r} degrees. The definition "
                f"refused is {definition!r}."
            )
        if not definition.k_origin > 0.0:
            raise ValueError(
                f"A grid scale factor must be positive; this zone gives "
                f"k_0 = {definition.k_origin!r}. A zero or negative scale "
                f"factor would collapse or reflect the grid rather than scale "
                f"it. The definition refused is {definition!r}."
            )
        return cls(
            ellipsoid=ellipsoid,
            lat_grid_origin=definition.lat_grid_origin,
            lon_origin=definition.lon_origin,
            k_origin=definition.k_origin,
            northing_grid_origin=definition.northing_grid_origin,
            easting_origin=definition.easting_origin,
        )


def forward(
    latitude: float, longitude: float, constants: TransverseMercatorConstants
) -> GridPoint:
    """Geodetic to grid. Manual section 3.23 (PDF pp. 44-45).

        L  = (lambda_0 - lambda) cos phi          [see the sign note below]
        R  = k_0 a / W        t = tan phi        eta^2 = e'^2 cos^2 phi
        A2 = R t / 2
        A4 = (1/12)[5 - t^2 + eta^2(9 + 4 eta^2)]
        A6 = (1/360)[61 - 58 t^2 + t^4 + eta^2(270 - 330 t^2)]
        N  = S - S_0 + N_0 + A2 L^2 [1 + L^2 (A4 + A6 L^2)]
        A1 = -R
        A3 = (1/6)(1 - t^2 + eta^2)
        A5 = (1/120)[5 - 18 t^2 + t^4 + eta^2(14 - 58 t^2)]
        A7 = (1/5040)(61 - 479 t^2 + 179 t^4 - t^6)
        E  = E_0 + A1 L [1 + L^2 (A3 + L^2 (A5 + A7 L^2))]
        gamma = C1 L [1 + L^2 (C3 + C5 L^2)]
        k  = k_0 [1 + F2 L^2 (1 + F4 L^2)]

    ``latitude`` and ``longitude`` are decimal degrees, longitude negative west.
    """
    _require_valid_geodetic(latitude, longitude)

    lat_radians = math.radians(latitude)
    sin_lat = math.sin(lat_radians)
    cos_lat = math.cos(lat_radians)
    _require_usable_cos_latitude(cos_lat, latitude)

    # DEVIATION POINT 1 of 2 from the manual's longitude convention.
    # Section 3.23 writes L = (lambda - lambda_0) cos phi with longitude
    # POSITIVE WEST. Our longitudes are negative west, so both terms change sign
    # and the subtraction reverses. L itself is the same physical quantity under
    # either convention - negative east of the central meridian - which is why
    # nothing downstream of this line changes. Same class as lambert.py's single
    # occurrence; the transverse Mercator has two, this and the one in
    # ``inverse``.
    L = math.radians(constants.lon_origin - longitude) * cos_lat

    ellipsoid = constants.ellipsoid
    S = constants.k_origin * constants.rectifying_latitude(lat_radians) * constants.r
    R = constants.k_origin * ellipsoid.a / ellipsoid.W(sin_lat)

    t = sin_lat / cos_lat
    t2 = t * t
    t4 = t2 * t2
    t6 = t4 * t2
    eta2 = ellipsoid.e2_prime * cos_lat * cos_lat
    eta4 = eta2 * eta2

    L2 = L * L

    A2 = R * t / 2.0
    A4 = (5.0 - t2 + eta2 * (9.0 + 4.0 * eta2)) / 12.0
    A6 = (61.0 - 58.0 * t2 + t4 + eta2 * (270.0 - 330.0 * t2)) / 360.0

    northing = (
        S
        - constants.S0
        + constants.northing_grid_origin
        + A2 * L2 * (1.0 + L2 * (A4 + A6 * L2))
    )

    A1 = -R
    A3 = (1.0 - t2 + eta2) / 6.0
    A5 = (5.0 - 18.0 * t2 + t4 + eta2 * (14.0 - 58.0 * t2)) / 120.0
    A7 = (61.0 - 479.0 * t2 + 179.0 * t4 - t6) / 5040.0

    easting = constants.easting_origin + A1 * L * (
        1.0 + L2 * (A3 + L2 * (A5 + A7 * L2))
    )

    C1 = -t
    C3 = (1.0 + 3.0 * eta2 + 2.0 * eta4) / 3.0
    C5 = (2.0 - t2) / 15.0
    convergence = math.degrees(C1 * L * (1.0 + L2 * (C3 + C5 * L2)))

    F2 = (1.0 + eta2) / 2.0
    F4 = (5.0 - 4.0 * t2 + eta2 * (9.0 - 24.0 * t2)) / 12.0
    scale_factor = constants.k_origin * (1.0 + F2 * L2 * (1.0 + F4 * L2))

    return GridPoint(
        northing=northing,
        easting=easting,
        convergence=convergence,
        scale_factor=scale_factor,
    )


def inverse(
    northing: float, easting: float, constants: TransverseMercatorConstants
) -> GeodeticPoint:
    """Grid to geodetic. Manual section 3.24 (PDF pp. 45-46). No iteration.

        omega_f = (N - N_0 + S_0) / (k_0 r)
        phi_f   = footpoint series in omega_f
        R_f     = k_0 a / W(phi_f)      Q = (E - E_0) / R_f
        B2 = -(1/2) t_f (1 + eta_f^2)
        B4 = -(1/12)[5 + 3 t_f^2 + eta_f^2(1 - 9 t_f^2) - 4 eta_f^4]
        B6 =  (1/360)[61 + 90 t_f^2 + 45 t_f^4
                          + eta_f^2(46 - 252 t_f^2 - 90 t_f^4)]
        phi = phi_f + B2 Q^2 [1 + Q^2 (B4 + B6 Q^2)]
        B3 = -(1/6)(1 + 2 t_f^2 + eta_f^2)
        B5 =  (1/120)[5 + 28 t_f^2 + 24 t_f^4 + eta_f^2(6 + 8 t_f^2)]
        B7 = -(1/5040)(61 + 662 t_f^2 + 1320 t_f^4 + 720 t_f^6)
        L   = Q [1 + Q^2 (B3 + Q^2 (B5 + B7 Q^2))]
        lambda = lambda_0 + L / cos phi_f          [see the sign note below]
        gamma = D1 Q [1 + Q^2 (D3 + D5 Q^2)]
        k = k_0 [1 + G2 Q^2 (1 + G4 Q^2)]

    ``northing`` and ``easting`` are meters.
    """
    _require_finite_grid(northing, easting)

    omega_f = (northing - constants.northing_grid_origin + constants.S0) / (
        constants.k_origin * constants.r
    )
    if not -math.pi / 2.0 < omega_f < math.pi / 2.0:
        raise ValueError(
            f"Northing {northing} m is beyond the pole for this zone: the "
            f"rectifying latitude it implies is {math.degrees(omega_f):.6f} "
            f"degrees, and no geodetic position corresponds to it. Check that "
            f"the northing and easting are not transposed and that the correct "
            f"zone and unit were selected."
        )

    lat_footpoint = constants.footpoint_latitude(omega_f)
    if not -math.pi / 2.0 < lat_footpoint < math.pi / 2.0:
        raise ValueError(
            f"Northing {northing} m is beyond the pole for this zone: the "
            f"footpoint latitude it implies is "
            f"{math.degrees(lat_footpoint):.6f} degrees. Check that the "
            f"northing and easting are not transposed and that the correct zone "
            f"and unit were selected."
        )

    sin_f = math.sin(lat_footpoint)
    cos_f = math.cos(lat_footpoint)
    _require_usable_cos_latitude(cos_f, math.degrees(lat_footpoint))

    ellipsoid = constants.ellipsoid
    R_f = constants.k_origin * ellipsoid.a / ellipsoid.W(sin_f)
    Q = (easting - constants.easting_origin) / R_f
    Q2 = Q * Q

    t_f = sin_f / cos_f
    t2 = t_f * t_f
    t4 = t2 * t2
    t6 = t4 * t2
    eta2 = ellipsoid.e2_prime * cos_f * cos_f
    eta4 = eta2 * eta2

    B2 = -0.5 * t_f * (1.0 + eta2)
    B4 = -(5.0 + 3.0 * t2 + eta2 * (1.0 - 9.0 * t2) - 4.0 * eta4) / 12.0
    B6 = (
        61.0
        + 90.0 * t2
        + 45.0 * t4
        + eta2 * (46.0 - 252.0 * t2 - 90.0 * t4)
    ) / 360.0

    lat_radians = lat_footpoint + B2 * Q2 * (1.0 + Q2 * (B4 + B6 * Q2))
    if not -math.pi / 2.0 < lat_radians < math.pi / 2.0:
        raise ValueError(
            f"Northing {northing} m and easting {easting} m imply a latitude of "
            f"{math.degrees(lat_radians):.6f} degrees, which is not a geodetic "
            f"latitude. Check that the northing and easting are not transposed "
            f"and that the correct zone and unit were selected."
        )

    B3 = -(1.0 + 2.0 * t2 + eta2) / 6.0
    B5 = (5.0 + 28.0 * t2 + 24.0 * t4 + eta2 * (6.0 + 8.0 * t2)) / 120.0
    B7 = -(61.0 + 662.0 * t2 + 1320.0 * t4 + 720.0 * t6) / 5040.0

    L = Q * (1.0 + Q2 * (B3 + Q2 * (B5 + B7 * Q2)))

    # DEVIATION POINT 2 of 2 from the manual's longitude convention.
    # Section 3.24 writes lambda = lambda_0 - L / cos phi_f with longitude
    # POSITIVE WEST; negating both longitudes turns the subtraction into an
    # addition. This is the exact inverse of the sign handling in ``forward``,
    # and the two must be changed together or a round trip lands twice the
    # distance from the central meridian on the wrong side.
    longitude = constants.lon_origin + math.degrees(L / cos_f)

    D1 = t_f
    D3 = -(1.0 + t2 - eta2 - 2.0 * eta4) / 3.0
    D5 = (2.0 + 5.0 * t2 + 3.0 * t4) / 15.0
    convergence = math.degrees(D1 * Q * (1.0 + Q2 * (D3 + D5 * Q2)))

    G2 = (1.0 + eta2) / 2.0
    G4 = (1.0 + 5.0 * eta2) / 12.0
    scale_factor = constants.k_origin * (1.0 + G2 * Q2 * (1.0 + G4 * Q2))

    return GeodeticPoint(
        latitude=math.degrees(lat_radians),
        longitude=longitude,
        convergence=convergence,
        scale_factor=scale_factor,
    )
