"""Reference ellipsoids.

Only the two defining geometric constants are stored. Everything else is
derived, so there is exactly one authoritative representation of the ellipsoid's
shape and no possibility of a stored derived value drifting out of agreement
with it.

Reference: NOAA Manual NOS NGS 5, section 1.7 (PDF p. 23).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property


@dataclass(frozen=True)
class Ellipsoid:
    """An ellipsoid of revolution, defined by semimajor axis and flattening.

    Two geometric constants define an ellipsoid (PDF p. 36: "only two geometric
    constants are required to define an ellipsoid ... All other geometric
    ellipsoid constants are then derived from the two defining constants").
    Every other quantity below is derived on demand.
    """

    name: str
    a: float
    """Semimajor axis, meters."""

    inv_f: float
    """Reciprocal of flattening, 1/f."""

    citation: str
    """Document and page the defining constants were taken from."""

    @cached_property
    def f(self) -> float:
        """Flattening, (a - b) / a."""
        return 1.0 / self.inv_f

    @cached_property
    def b(self) -> float:
        """Semiminor axis, meters."""
        return self.a * (1.0 - self.f)

    @cached_property
    def e2(self) -> float:
        """First eccentricity squared, e^2 = 2f - f^2.

        Manual section 3.11 notation list (PDF p. 37): "First eccentricity of
        the ellipsoid = (2f - f^2)^(1/2)".
        """
        return 2.0 * self.f - self.f * self.f

    @cached_property
    def e(self) -> float:
        """First eccentricity."""
        return math.sqrt(self.e2)

    def W(self, sin_lat: float) -> float:
        """W = (1 - e^2 sin^2(phi))^(1/2), manual section 3.12 (PDF p. 37).

        Appears throughout the Lambert equations as the scaling between the
        ellipsoid and the sphere of curvature at a latitude.
        """
        return math.sqrt(1.0 - self.e2 * sin_lat * sin_lat)

    def isometric_latitude(self, sin_lat: float) -> float:
        """Isometric latitude Q, manual section 3.12 (PDF p. 37).

            Q = 1/2 [ ln((1 + sin phi) / (1 - sin phi))
                      - e ln((1 + e sin phi) / (1 - e sin phi)) ]

        Takes the sine of the latitude rather than the latitude itself because
        the inverse conversion iterates on sin(phi) directly (section 3.14,
        PDF p. 39) and would otherwise round-trip through asin on every step.
        """
        e_sin = self.e * sin_lat
        return 0.5 * (
            math.log((1.0 + sin_lat) / (1.0 - sin_lat))
            - self.e * math.log((1.0 + e_sin) / (1.0 - e_sin))
        )

    def d_isometric_latitude_d_sin(self, sin_lat: float) -> float:
        """dQ/d(sin phi), used by the inverse conversion's Newton iteration.

        The manual gives this as ``f2`` in section 3.14 (PDF p. 39):

            f2 = 1 / (1 - sin^2 phi) - e^2 / (1 - e^2 sin^2 phi)

        which is the analytic derivative of ``isometric_latitude`` with respect
        to sin(phi).
        """
        s2 = sin_lat * sin_lat
        return 1.0 / (1.0 - s2) - self.e2 / (1.0 - self.e2 * s2)

    def radius_meridian(self, sin_lat: float) -> float:
        """Radius of curvature in the meridian, M = a(1 - e^2) / W^3.

        Manual section 3.15 (PDF p. 40), where M0 is this quantity at the
        central parallel, scaled to the grid.
        """
        w = self.W(sin_lat)
        return self.a * (1.0 - self.e2) / (w * w * w)

    def radius_prime_vertical(self, sin_lat: float) -> float:
        """Radius of curvature in the prime vertical, N = a / W.

        Manual section 3.21 (PDF p. 43).
        """
        return self.a / self.W(sin_lat)

    def radius_geometric_mean(self, sin_lat: float) -> float:
        """Geometric mean radius of curvature, sqrt(M * N).

        The manual's ``r0`` is this quantity at the central parallel, scaled to
        the grid (manual section 3.15, PDF p. 40).
        """
        return math.sqrt(
            self.radius_meridian(sin_lat) * self.radius_prime_vertical(sin_lat)
        )


GRS80 = Ellipsoid(
    name="GRS 80",
    # a = 6,378,137 m exact by definition; 1/f = 298.25722210088 to 14
    # significant digits by computation. NOAA Manual NOS NGS 5 section 1.7,
    # PDF p. 23. The same page publishes the derived b = 6,356,752.3141403 and
    # e^2 = 0.0066943800229034, which tests/test_ellipsoid.py checks this
    # module reproduces rather than storing them as independent facts.
    a=6378137.0,
    inv_f=298.25722210088,
    citation="NOAA Manual NOS NGS 5, section 1.7, PDF p. 23",
)
