"""NGS GEOID18 heights, captured once and frozen. Verification anchors.

Every value below was computed by the National Geodetic Survey's own geoid
height service and captured verbatim from its API:

    https://geodesy.noaa.gov/api/geoid/ght?lat=<lat>&lon=<lon>&model=14

where model 14 is GEOID18. Captured 2026-08-05. **No test touches the network.**

The positions are deliberately off-node: the grid's nodes lie on exact multiples
of one arcminute, and every point here falls well inside a cell, so what these
anchors actually test is the interpolation scheme rather than a raw table
lookup. They are spread across the Upper Peninsula, the Lower Peninsula and the
Detroit/Lansing corridor.

NGS prints geoid heights to 0.001 m, so a published figure carries +/-0.0005 m
of quantization on its own.

Note the sign: every value is negative, between about -30 and -37 m. In the
conterminous United States the ellipsoid lies above the geoid (manual PDF
p. 57). A positive geoid height for a Michigan point is always an error.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeoidAnchor:
    """One NGS geoid height, verbatim."""

    latitude: float
    longitude: float
    """Decimal degrees, negative west."""

    geoid_height_m: float
    """Negative throughout the conterminous United States."""

    error_m: float
    """NGS's own stated uncertainty for the model at this point."""


GEOID_ANCHORS: tuple[GeoidAnchor, ...] = (

    GeoidAnchor(
        latitude=41.7231,
        longitude=-83.4817,
        geoid_height_m=-35.382,
        error_m=0.032,
    ),
    GeoidAnchor(
        latitude=42.3314,
        longitude=-83.0458,
        geoid_height_m=-34.547,
        error_m=0.031,
    ),
    GeoidAnchor(
        latitude=42.7325,
        longitude=-84.5555,
        geoid_height_m=-33.637,
        error_m=0.03,
    ),
    GeoidAnchor(
        latitude=42.9634,
        longitude=-85.6681,
        geoid_height_m=-33.605,
        error_m=0.032,
    ),
    GeoidAnchor(
        latitude=43.0125,
        longitude=-83.6875,
        geoid_height_m=-34.092,
        error_m=0.031,
    ),
    GeoidAnchor(
        latitude=43.4195,
        longitude=-83.9508,
        geoid_height_m=-34.276,
        error_m=0.031,
    ),
    GeoidAnchor(
        latitude=43.6106,
        longitude=-84.2472,
        geoid_height_m=-34.282,
        error_m=0.033,
    ),
    GeoidAnchor(
        latitude=44.2542,
        longitude=-85.4012,
        geoid_height_m=-33.284,
        error_m=0.032,
    ),
    GeoidAnchor(
        latitude=44.7631,
        longitude=-85.6206,
        geoid_height_m=-34.67,
        error_m=0.033,
    ),
    GeoidAnchor(
        latitude=45.0217,
        longitude=-84.6753,
        geoid_height_m=-34.933,
        error_m=0.039,
    ),
    GeoidAnchor(
        latitude=45.3672,
        longitude=-84.9553,
        geoid_height_m=-35.185,
        error_m=0.033,
    ),
    GeoidAnchor(
        latitude=45.7842,
        longitude=-84.7278,
        geoid_height_m=-35.406,
        error_m=0.033,
    ),
    GeoidAnchor(
        latitude=46.0931,
        longitude=-85.5031,
        geoid_height_m=-34.975,
        error_m=0.037,
    ),
    GeoidAnchor(
        latitude=46.3406,
        longitude=-85.5089,
        geoid_height_m=-35.349,
        error_m=0.034,
    ),
    GeoidAnchor(
        latitude=46.4931,
        longitude=-84.3453,
        geoid_height_m=-36.634,
        error_m=0.032,
    ),
    GeoidAnchor(
        latitude=46.5436,
        longitude=-87.3954,
        geoid_height_m=-34.741,
        error_m=0.034,
    ),
    GeoidAnchor(
        latitude=47.1211,
        longitude=-88.5694,
        geoid_height_m=-33.796,
        error_m=0.034,
    ),
    GeoidAnchor(
        latitude=47.4703,
        longitude=-87.8842,
        geoid_height_m=-35.291,
        error_m=0.035,
    ),
    GeoidAnchor(
        latitude=46.4547,
        longitude=-90.1712,
        geoid_height_m=-30.678,
        error_m=0.03,
    ),
    GeoidAnchor(
        latitude=48.1736,
        longitude=-88.4892,
        geoid_height_m=-35.385,
        error_m=0.061,
    ),
)
