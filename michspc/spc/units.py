"""Linear units.

The zone constants and all internal computation are in meters, matching the
ellipsoid and the manual's Appendix A/C values. Units exist only at the
boundaries: what a file arrives in, and what a file leaves in.

Michigan legislated the **International foot** for SPCS 83 (NOAA Manual NOS
NGS 5, Table 1.5, PDF p. 19, where Michigan is flagged "(I)"). That is this
program's default. The US survey foot is supported because legacy data uses it,
and the two differ by 2 parts per million - which at Michigan South's
4,000,000 m false easting is about 26 feet. A file converted under the wrong
foot definition looks entirely ordinary and is badly wrong, so the unit in force
is stated in every output file this program writes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LinearUnit:
    """A linear unit, defined by its exact size in meters."""

    code: str
    name: str
    meters_per_unit: float
    decimals: int
    """Decimal places this program writes coordinates to in this unit.

    Three for feet (0.001 ft, about 0.3 mm) and four for meters (0.0001 m),
    which is the survey convention and roughly matches the two resolutions.
    """

    citation: str

    def to_meters(self, value: float) -> float:
        return value * self.meters_per_unit

    def from_meters(self, meters: float) -> float:
        return meters / self.meters_per_unit


METERS = LinearUnit(
    code="m",
    name="meters",
    meters_per_unit=1.0,
    decimals=4,
    citation="NOAA Manual NOS NGS 5 publishes SPCS 83 in meters (PDF p. 21)",
)

INTERNATIONAL_FEET = LinearUnit(
    code="ift",
    name="International feet",
    # 0.3048 m exactly. NOAA Manual NOS NGS 5, PDF p. 22.
    meters_per_unit=0.3048,
    decimals=3,
    citation="NOAA Manual NOS NGS 5, PDF p. 22 (0.3048 m exactly); Michigan "
    "legislated this unit, Table 1.5, PDF p. 19",
)

US_SURVEY_FEET = LinearUnit(
    code="usft",
    name="US survey feet",
    # 1200/3937 m exactly. NOAA Manual NOS NGS 5, PDF p. 22.
    meters_per_unit=1200.0 / 3937.0,
    decimals=3,
    citation="NOAA Manual NOS NGS 5, PDF p. 22 (1200/3937 m exactly). Legacy "
    "unit; superseded by the International foot for Michigan SPCS 83",
)

ALL_UNITS: tuple[LinearUnit, ...] = (INTERNATIONAL_FEET, US_SURVEY_FEET, METERS)

DEFAULT_UNIT = INTERNATIONAL_FEET

_BY_CODE = {unit.code: unit for unit in ALL_UNITS}


def unit_by_code(code: str) -> LinearUnit:
    """Look up a unit, refusing anything unrecognised rather than guessing."""
    key = str(code).strip().lower()
    try:
        return _BY_CODE[key]
    except KeyError:
        known = ", ".join(f"{u.code} ({u.name})" for u in ALL_UNITS)
        raise KeyError(
            f"Unknown linear unit {code!r}. Known units are: {known}."
        ) from None
