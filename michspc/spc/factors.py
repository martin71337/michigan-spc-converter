"""Elevation factor and combined factor.

NOAA Manual NOS NGS 5, section 4.1 "Reduction of Observed Distances to the
Ellipsoid" (PDF pp. 56-59; section 4.2 begins partway down PDF p. 59).

A measured horizontal distance on the ground is reduced to the ellipsoid by the
**elevation factor**, and from the ellipsoid to the grid by the **grid scale
factor**. Their product is the **combined factor**, which takes a ground
distance straight to a grid distance:

    elevation factor  =  R / (R + H + N)
    combined factor   =  k * elevation factor

with H the orthometric height, N the geoid height (negative in Michigan), and
R a mean radius of the earth. h = H + N is the ellipsoid height (PDF p. 57).

This module takes the geoid height as a **parameter** rather than looking it up.
The computation core does no file I/O, and the GEOID18 grid is a file; the
caller reads it (michspc.fileio.geoid) and passes the value in. That keeps the
core pure and testable without the 4.7 MB grid present.

**Missing elevations produce None, never a number.** A PNEZD file with a blank
or 0.00 Z column is ordinary, and there is no honest elevation factor for such a
point. Returning 1.0 would claim the point is on the ellipsoid; returning the
grid factor alone would claim the combined factor equals it. Both are
fabrications the file would carry silently onto a drawing. The report names
every affected point instead (docs/DESIGN.md section 7).
"""

from __future__ import annotations

from dataclasses import dataclass

# Mean radius of the earth used for distance reduction. The manual gives it on
# PDF p. 59 as "20,906,000 ft, or 6,372,000 m", and says this approximate radius
# "serves equally well for NAD 83". The metric figure is used here because the
# core computes in meters.
#
# The two printed figures are not exactly equal - 20,906,000 ift is 6,372,148.8 m
# - but the difference is 2.3e-5 relative and moves an elevation factor by about
# 1e-9, which tests/test_factors.py bounds explicitly rather than assuming.
MEAN_EARTH_RADIUS_M = 6_372_000.0

# The same radius as the manual's foot figure, kept for that bounding test and
# for the report, which cites the manual's own wording.
MEAN_EARTH_RADIUS_IFT = 20_906_000.0


@dataclass(frozen=True)
class Factors:
    """Every scale quantity that applies at one point.

    The elevation and combined factors are None when the point has no usable
    elevation. That is a deliberate absence, not a missing value to be filled
    in later.
    """

    grid_scale_factor: float
    orthometric_height: float | None
    """Meters. None when the source file carried no elevation."""

    geoid_height: float | None
    """Meters, negative in Michigan. None when no elevation was available, since
    the geoid height is only ever looked up in service of the elevation factor."""

    elevation_factor: float | None
    combined_factor: float | None

    @property
    def has_elevation(self) -> bool:
        return self.elevation_factor is not None

    @property
    def ellipsoid_height(self) -> float | None:
        """h = H + N, meters. None when there is no orthometric height."""
        if self.orthometric_height is None or self.geoid_height is None:
            return None
        return self.orthometric_height + self.geoid_height


def elevation_factor(
    orthometric_height: float, geoid_height: float, radius: float = MEAN_EARTH_RADIUS_M
) -> float:
    """R / (R + H + N), manual section 4.1 (PDF p. 58).

    All arguments in meters. The geoid height is negative in Michigan; passing
    it positive is a ~10 ppm error, which is why callers must obtain it from the
    GEOID18 grid rather than from a user-typed field.
    """
    ellipsoid_height = orthometric_height + geoid_height
    denominator = radius + ellipsoid_height
    if denominator <= 0.0:
        raise ValueError(
            f"An ellipsoid height of {ellipsoid_height} m places the point at "
            f"or below the centre of the earth, which cannot be right. Check "
            f"the elevation and its units."
        )
    return radius / denominator


def combined_factor(grid_scale_factor: float, elevation_factor_value: float) -> float:
    """The product of the two, manual section 4.1 (PDF p. 59).

    The manual notes the product "is approximated by subtracting 1 from the sum
    of the two factors". That approximation existed for hand calculation; the
    exact product costs nothing here, so it is used.
    """
    return grid_scale_factor * elevation_factor_value


def factors_at(
    grid_scale_factor: float,
    orthometric_height: float | None,
    geoid_height: float | None,
    radius: float = MEAN_EARTH_RADIUS_M,
) -> Factors:
    """Assemble the factors for one point, honouring a missing elevation.

    Both the height and the geoid height must be present to produce an
    elevation factor. If either is absent the elevation and combined factors are
    None, and the grid scale factor - which does not depend on elevation - is
    still reported.
    """
    if orthometric_height is None or geoid_height is None:
        return Factors(
            grid_scale_factor=grid_scale_factor,
            orthometric_height=orthometric_height,
            geoid_height=geoid_height if orthometric_height is not None else None,
            elevation_factor=None,
            combined_factor=None,
        )

    factor = elevation_factor(orthometric_height, geoid_height, radius)
    return Factors(
        grid_scale_factor=grid_scale_factor,
        orthometric_height=orthometric_height,
        geoid_height=geoid_height,
        elevation_factor=factor,
        combined_factor=combined_factor(grid_scale_factor, factor),
    )
