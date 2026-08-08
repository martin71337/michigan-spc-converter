"""NGS GEOID12B heights, captured once and frozen. WP-V5 verification anchors.

Every value below was computed by the National Geodetic Survey's own geoid
height service and captured verbatim from its API:

    https://geodesy.noaa.gov/api/geoid/ght?lat=<lat>&lon=<lon>&model=13

where model 13 is GEOID12B - not assumed: every captured response names itself
"GEOID12B" in its ``geoidModel`` field, and the capture harness
(review/wp-v5-geoid12b/capture_geoid12b_anchors.py, raw responses committed
beside it) refuses any response that does not. Captured 2026-08-07.
**No test touches the network.**

The positions are exactly those of ``geoid_anchors.GEOID_ANCHORS``, the
GEOID18 anchors, so the two models are anchored at identical ground:

- **18 of the 20 differ between the models at NGS's printed millimetre**, so
  these anchors discriminate the models - a GEOID18 tile served under the
  GEOID12B name (the two files are byte-for-byte the same SIZE and the same
  tile-#3 geometry, so nothing structural can tell them apart) fails here.
- The committed ``data/g2012bu3.bin`` reproduces every figure through the
  nearest-node biquadratic (the INTG stencil, DESIGN.md #37) at worst
  0.543 mm - NGS's own 0.5 mm printing quantization, measured at capture
  before any registry code existed.

NGS prints geoid heights to 0.001 m, so a published figure carries +/-0.0005 m
of quantization on its own. Every value is negative: the ellipsoid is above
the geoid throughout the conterminous United States.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Geoid12bAnchor:
    """One NGS GEOID12B height, verbatim."""

    latitude: float
    longitude: float
    """Decimal degrees, negative west. Same ground as GEOID_ANCHORS."""

    geoid_height_m: float
    """Negative throughout the conterminous United States."""

    error_m: float
    """NGS's own stated uncertainty for the model at this point."""


GEOID12B_ANCHORS: tuple[Geoid12bAnchor, ...] = (
    Geoid12bAnchor(
        latitude=41.7231,
        longitude=-83.4817,
        geoid_height_m=-35.396,
        error_m=0.043,
    ),
    Geoid12bAnchor(
        latitude=42.3314,
        longitude=-83.0458,
        geoid_height_m=-34.548,
        error_m=0.042,
    ),
    Geoid12bAnchor(
        latitude=42.7325,
        longitude=-84.5555,
        geoid_height_m=-33.641,
        error_m=0.041,
    ),
    Geoid12bAnchor(
        latitude=42.9634,
        longitude=-85.6681,
        geoid_height_m=-33.61,
        error_m=0.043,
    ),
    Geoid12bAnchor(
        latitude=43.0125,
        longitude=-83.6875,
        geoid_height_m=-34.073,
        error_m=0.041,
    ),
    Geoid12bAnchor(
        latitude=43.4195,
        longitude=-83.9508,
        geoid_height_m=-34.276,
        error_m=0.042,
    ),
    Geoid12bAnchor(
        latitude=43.6106,
        longitude=-84.2472,
        geoid_height_m=-34.281,
        error_m=0.043,
    ),
    Geoid12bAnchor(
        latitude=44.2542,
        longitude=-85.4012,
        geoid_height_m=-33.285,
        error_m=0.042,
    ),
    Geoid12bAnchor(
        latitude=44.7631,
        longitude=-85.6206,
        geoid_height_m=-34.666,
        error_m=0.043,
    ),
    Geoid12bAnchor(
        latitude=45.0217,
        longitude=-84.6753,
        geoid_height_m=-34.936,
        error_m=0.05,
    ),
    Geoid12bAnchor(
        latitude=45.3672,
        longitude=-84.9553,
        geoid_height_m=-35.191,
        error_m=0.044,
    ),
    Geoid12bAnchor(
        latitude=45.7842,
        longitude=-84.7278,
        geoid_height_m=-35.411,
        error_m=0.043,
    ),
    Geoid12bAnchor(
        latitude=46.0931,
        longitude=-85.5031,
        geoid_height_m=-34.96,
        error_m=0.044,
    ),
    Geoid12bAnchor(
        latitude=46.3406,
        longitude=-85.5089,
        geoid_height_m=-35.357,
        error_m=0.044,
    ),
    Geoid12bAnchor(
        latitude=46.4931,
        longitude=-84.3453,
        geoid_height_m=-36.637,
        error_m=0.042,
    ),
    Geoid12bAnchor(
        latitude=46.5436,
        longitude=-87.3954,
        geoid_height_m=-34.751,
        error_m=0.044,
    ),
    Geoid12bAnchor(
        latitude=47.1211,
        longitude=-88.5694,
        geoid_height_m=-33.828,
        error_m=0.044,
    ),
    Geoid12bAnchor(
        latitude=47.4703,
        longitude=-87.8842,
        geoid_height_m=-35.291,
        error_m=0.046,
    ),
    Geoid12bAnchor(
        latitude=46.4547,
        longitude=-90.1712,
        geoid_height_m=-30.666,
        error_m=0.049,
    ),
    Geoid12bAnchor(
        latitude=48.1736,
        longitude=-88.4892,
        geoid_height_m=-35.396,
        error_m=0.075,
    ),
)
