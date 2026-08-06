"""Derived zone constants as published by NGS, for verification only.

Transcribed from NOAA Manual NOS NGS 5, Appendix C, "Constants for the Lambert
projection by the polynomial coefficient method", PDF pp. 103-104.

These are the values NGS computed from the same defining constants our registry
holds. They exist here, in the test tree, rather than in the production
registry, deliberately: their entire purpose is to be an *independent* check on
michspc.spc.lambert's derivation. Storing them beside the code that derives them
would make the check circular and would create a second authoritative
representation of the same fact (docs/DESIGN.md section 7).

Nothing in michspc/ may import this module.

Each value is recorded with the number of decimal places NGS printed, because
the assertion tolerance is half a unit in the last published place - that is the
most the published figure can be held to.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PublishedConstants:
    """One zone's derived constants exactly as Appendix C prints them."""

    zone_code: str
    page: str

    Bo: float
    """Central parallel, decimal degrees. Printed to 10 dp."""

    SinBo: float
    """Sine of the central parallel. Printed to 12 dp."""

    Rb: float
    """Mapping radius at the grid origin, meters. Printed to 4 dp."""

    Ro: float
    """Mapping radius at the central parallel, meters. Printed to 4 dp."""

    No: float
    """Northing at the true projection origin, meters. Printed to 4 dp."""

    K: float
    """Mapping radius at the equator, meters. Printed to 4 dp."""

    ko: float
    """Grid scale factor at the central parallel. Printed to 12 dp."""

    Mo: float
    """Scaled radius of curvature in the meridian at Bo, meters. Printed to 4 dp."""

    ro: float
    """Scaled geometric mean radius of curvature at Bo, meters. Printed whole."""


# Decimal places NGS printed for each quantity, used to set tolerances.
PRINTED_DECIMALS = {
    "Bo": 10,
    "SinBo": 12,
    "Rb": 4,
    "Ro": 4,
    "No": 4,
    "K": 4,
    "ko": 12,
    "Mo": 4,
    "ro": 0,
}


MI_NORTH_PUBLISHED = PublishedConstants(
    zone_code="2111",
    page="NOAA Manual NOS NGS 5, Appendix C, PDF p. 103 (MI N, zone 2111)",
    Bo=46.2853056176,
    SinBo=0.722789934733,
    Rb=6275243.8434,
    Ro=6108308.6036,
    No=166935.2398,
    K=11779843.7720,
    ko=0.999902834466,
    Mo=6368201.9117,
    ro=6378442.0,
)

MI_CENTRAL_PUBLISHED = PublishedConstants(
    zone_code="2112",
    page="NOAA Manual NOS NGS 5, Appendix C, PDF p. 103 (MI C, zone 2112)",
    Bo=44.9433587575,
    SinBo=0.706407406862,
    Rb=6581660.2321,
    Ro=6400902.4399,
    No=180757.7922,
    K=11878338.0174,
    ko=0.999912706253,
    Mo=6366762.5687,
    ro=6377502.0,
)

MI_SOUTH_PUBLISHED = PublishedConstants(
    zone_code="2113",
    page="NOAA Manual NOS NGS 5, Appendix C, PDF p. 104 (MI S, zone 2113)",
    Bo=42.8850151357,
    SinBo=0.680529259912,
    Rb=7031167.2907,
    Ro=6877323.4058,
    No=153843.8848,
    K=12061671.8385,
    ko=0.999906878420,
    Mo=6364423.8607,
    ro=6375928.0,
)


ALL_PUBLISHED: tuple[PublishedConstants, ...] = (
    MI_NORTH_PUBLISHED,
    MI_CENTRAL_PUBLISHED,
    MI_SOUTH_PUBLISHED,
)
