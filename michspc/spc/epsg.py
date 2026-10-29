"""EPSG codes for the coordinate systems this program offers.

The owner's instruction, 2026-10-29: every system in the dropdowns names its
EPSG code in parentheses (docs/DESIGN.md amendment #72, docs/PLAN-utm-epsg.md
decisions D1-D3). **A label, never an input.** Nothing in this program
converts BY an EPSG code and no computation reads this module; the codes are
here so a surveyor can set the same system in Civil 3D, a GIS or a data
collector without translating names.

**Every code was read from the EPSG Geodetic Parameter Dataset itself**,
version v12.029 of 2025-10-02 (the ``proj.db`` PROJ 9.8.1 ships, through
pyproj 3.8.0), and checked there for substance, not only by name
(``review/utm-u0/measure.py``): each NAD83(2011) Michigan projected CRS was
run against this program's own zone record and agreed to 0.000 mm in metres
and to 0.032 mm or better on the foot variants (EPSG rounding its false
origins in feet); the UTM CRSs are conversions 16015-16017 on NAD83(2011);
each geographic code is the 2D CRS of exactly the realization its frame
record names. **EPSG numbers Michigan Central (6493) before North (6495)** -
the reason these are read and never recalled.

**An EPSG projected CRS is a zone AND a unit.** "NAD83(2011) / Michigan South"
(6498) is metres and "NAD83(2011) / Michigan South (ft)" (6499) is the
international foot. So a zone carries one code per unit EPSG defines it in,
and the dropdown shows the code for the unit that side of the job would use
(plan D1). Two absences are facts, recorded rather than filled in (plan D2):

* **No US survey foot code exists for any NAD83(2011) Michigan zone.** EPSG
  defines them in metres and the international foot, the unit Michigan
  legislated. A survey-foot side shows no code.
* **No Michigan SPCS2022 zone and no NATRF2022 UTM zone has an EPSG code** in
  v12.029. EPSG had added the NATRF2022 geographic CRSs (10967 3D, 10968 2D)
  and NATRF2022's Gulf zones, but none of Michigan's; NGS states it is
  "providing SPCS2022 definitions to ... the European Petroleum Survey Group
  (EPSG) Geodetic Parameter Dataset" (review/nsrs-n0/raw/spcs/learn-more.html).
  Those entries carry no code until EPSG publishes one, and the code that
  arrives then is added here from the dataset, never guessed from the
  numbering around it.

The geographic codes are the **2D** CRSs, latitude and longitude only (plan
D3): the height beside them may be an elevation or an ellipsoid height (the
job's height setting says which), and the 3D code would assert an ellipsoid
height.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from michspc.spc.frames import (
    ALL_FRAMES,
    ITRF2014,
    ITRF2020,
    NAD83_2011,
    NATRF2022,
    WGS84_G1762,
    WGS84_G2139,
    WGS84_G2296,
    ReferenceFrame,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS, LinearUnit
from michspc.spc.zones import ALL_ZONES, Zone

EPSG_DATASET_VERSION = "v12.029"
EPSG_DATASET_DATE = "2025-10-02"
"""The EPSG dataset every code below was read from."""


ZONE_CODES: Mapping[str, tuple[tuple[LinearUnit, int], ...]] = MappingProxyType(
    {
        # "NAD83(2011) / Michigan North" (6495) and "... (ft)" (6496), and so
        # on. Not north to south: EPSG assigned Central before North.
        "2111": ((METERS, 6495), (INTERNATIONAL_FEET, 6496)),
        "2112": ((METERS, 6493), (INTERNATIONAL_FEET, 6494)),
        "2113": ((METERS, 6498), (INTERNATIONAL_FEET, 6499)),
        # "NAD83(2011) / UTM zone 15N" (6344), 16N (6345), 17N (6346); metres
        # only. The NATRF2022 UTM records ("15N-2022" ...) have no code.
        "15N": ((METERS, 6344),),
        "16N": ((METERS, 6345),),
        "17N": ((METERS, 6346),),
    }
)
"""Zone code -> ((unit, EPSG code), ...). A zone absent here has no code."""

FRAME_CODES: Mapping[str, int] = MappingProxyType(
    {
        NAD83_2011.code: 6318,  # "NAD83(2011)", geographic 2D
        NATRF2022.code: 10968,  # "NATRF2022", geographic 2D
        WGS84_G1762.code: 9057,  # "WGS 84 (G1762)", geographic 2D
        WGS84_G2139.code: 9755,  # "WGS 84 (G2139)", geographic 2D
        WGS84_G2296.code: 10606,  # "WGS 84 (G2296)", geographic 2D
        ITRF2014.code: 9000,  # "ITRF2014", geographic 2D
        ITRF2020.code: 9990,  # "ITRF2020", geographic 2D
    }
)
"""Frame code -> the EPSG code of its geographic 2D CRS.

The bare "WGS84" record is deliberately absent: it is refused by name and
offered nowhere, and EPSG 4326 is the ENSEMBLE of every WGS 84 realization -
exactly the ambiguity that refusal exists for."""


class EpsgTableError(ValueError):
    """The table names a zone, frame or unit the registries do not hold.

    Raised at import, never at a job: a code keyed to a misspelt zone would
    silently label nothing, and a code for a unit the zone does not publish
    would label a side the unit gate refuses.
    """


def check_table(
    zone_codes: Mapping[str, tuple[tuple[LinearUnit, int], ...]],
    frame_codes: Mapping[str, int],
) -> None:
    """Refuse a table that names anything the registries do not hold.

    Takes the tables as arguments so the suite can hand it a bad one and see
    it fire. if/raise rather than assert, because -O strips asserts.
    """
    zones = {zone.code: zone for zone in ALL_ZONES}
    for code, entries in zone_codes.items():
        zone = zones.get(code)
        if zone is None:
            raise EpsgTableError(
                f"The EPSG table names zone {code!r}, which is not in the zone "
                f"registry."
            )
        for unit, epsg in entries:
            if unit not in zone.allowed_units:
                raise EpsgTableError(
                    f"The EPSG table gives {zone.name} ({zone.code}) the code "
                    f"{epsg} in {unit.name}, a unit the zone does not publish "
                    f"({', '.join(u.code for u in zone.allowed_units)})."
                )
    registered = {frame.code for frame in ALL_FRAMES if frame.is_usable}
    for code in frame_codes:
        if code not in registered:
            raise EpsgTableError(
                f"The EPSG table names frame {code!r}, which is not a usable "
                f"registered frame."
            )


check_table(ZONE_CODES, FRAME_CODES)


def zone_code(zone: Zone, unit: LinearUnit) -> int | None:
    """The EPSG code of this zone in this unit, or None where EPSG has none."""
    for entry_unit, code in ZONE_CODES.get(zone.code, ()):
        if entry_unit == unit:
            return code
    return None


def frame_code(frame: ReferenceFrame) -> int | None:
    """The EPSG code of this frame's geographic 2D CRS, or None."""
    return FRAME_CODES.get(frame.code)


def zone_label_suffix(zone: Zone, unit: LinearUnit) -> str:
    """" (EPSG 6499 ift)", " (EPSG 6345 m)", or "" - the unit always named."""
    code = zone_code(zone, unit)
    return "" if code is None else f" (EPSG {code} {unit.code})"


def frame_label_suffix(frame: ReferenceFrame) -> str:
    """" (EPSG 6318)", or "" for a frame with no code. No unit: degrees."""
    code = frame_code(frame)
    return "" if code is None else f" (EPSG {code})"
