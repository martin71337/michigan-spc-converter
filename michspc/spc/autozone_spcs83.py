"""County -> SPCS 83 zone, transcribed from Michigan statute.

**Authority: MCL 54.231(3)-(5)** (Michigan Coordinate Systems, Act 9 of 1964,
as amended by 1988 PA 154, Imd. Eff. June 14, 1988): "The area included in the
following counties constitutes the north zone: ..." and likewise for the
central and south zones. Captured from legislature.mi.gov on 2026-10-22 as
``review/autozone-r0/raw/statute/mcl-54-231.html`` (21,044 bytes, SHA-256
``3ed4adaa63a83eb9edd92d9a3efeba873c04c68c2857f16ad3d53833ecf592b8``, see
``tests/test_autozone_tables.py``, which re-reads that capture and requires
every county below to be listed in exactly the zone this table gives it).

The statute's 15 + 27 + 41 counties are all 83 of Michigan's counties, each in
exactly one zone. A zone is the union of its counties, Great Lakes waters
included, because the counties extend into the lakes (RECON.md section 1.1).

**Pending legislation:** HB 5577 of 2026 would strike subsections (2)-(5) and
define a zone as "the geographic areas encompassed by closed contiguous county
boundaries or submerged lands, or both", deferring to NGS (RECON.md section
1.1; passed the House 2026-04-15, in Senate committee 2026-10-22). This table
is the 1988 text as captured; if that bill is enacted, the capture and this
table are re-read against the new law.

FIPS codes and the county names are the Census TIGER/Line 2025 county file's
own GEOID and NAME (the shipped ``data/mi_counties_tiger2025.json``);
``michspc.spc.autozone.require_tables_cover`` refuses at load if the file and
this table disagree about either. The statute spells every county the way
TIGER does.

**Zones by identity.** The values are the records of ``michspc.spc.zones``
themselves (MI_NORTH, MI_CENTRAL, MI_SOUTH), never copies, so no fact about a
zone is stated here.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from michspc.spc.zones import MI_CENTRAL, MI_NORTH, MI_SOUTH, Zone

STATUTE_CITATION = (
    "MCL 54.231(3)-(5), Act 9 of 1964 as amended by 1988 PA 154 (Imd. Eff. "
    "June 14, 1988), captured from legislature.mi.gov 2026-10-22"
)

# (FIPS, county name, zone). Sorted by FIPS. The zone column is MCL 54.231:
# N = subsection (3), C = subsection (4), S = subsection (5).
_ROWS: tuple[tuple[str, str, Zone], ...] = (
    ("26001", "Alcona", MI_CENTRAL),
    ("26003", "Alger", MI_NORTH),
    ("26005", "Allegan", MI_SOUTH),
    ("26007", "Alpena", MI_CENTRAL),
    ("26009", "Antrim", MI_CENTRAL),
    ("26011", "Arenac", MI_CENTRAL),
    ("26013", "Baraga", MI_NORTH),
    ("26015", "Barry", MI_SOUTH),
    ("26017", "Bay", MI_SOUTH),
    ("26019", "Benzie", MI_CENTRAL),
    ("26021", "Berrien", MI_SOUTH),
    ("26023", "Branch", MI_SOUTH),
    ("26025", "Calhoun", MI_SOUTH),
    ("26027", "Cass", MI_SOUTH),
    ("26029", "Charlevoix", MI_CENTRAL),
    ("26031", "Cheboygan", MI_CENTRAL),
    ("26033", "Chippewa", MI_NORTH),
    ("26035", "Clare", MI_CENTRAL),
    ("26037", "Clinton", MI_SOUTH),
    ("26039", "Crawford", MI_CENTRAL),
    ("26041", "Delta", MI_NORTH),
    ("26043", "Dickinson", MI_NORTH),
    ("26045", "Eaton", MI_SOUTH),
    ("26047", "Emmet", MI_CENTRAL),
    ("26049", "Genesee", MI_SOUTH),
    ("26051", "Gladwin", MI_CENTRAL),
    ("26053", "Gogebic", MI_NORTH),
    ("26055", "Grand Traverse", MI_CENTRAL),
    ("26057", "Gratiot", MI_SOUTH),
    ("26059", "Hillsdale", MI_SOUTH),
    ("26061", "Houghton", MI_NORTH),
    ("26063", "Huron", MI_SOUTH),
    ("26065", "Ingham", MI_SOUTH),
    ("26067", "Ionia", MI_SOUTH),
    ("26069", "Iosco", MI_CENTRAL),
    ("26071", "Iron", MI_NORTH),
    ("26073", "Isabella", MI_SOUTH),
    ("26075", "Jackson", MI_SOUTH),
    ("26077", "Kalamazoo", MI_SOUTH),
    ("26079", "Kalkaska", MI_CENTRAL),
    ("26081", "Kent", MI_SOUTH),
    ("26083", "Keweenaw", MI_NORTH),
    ("26085", "Lake", MI_CENTRAL),
    ("26087", "Lapeer", MI_SOUTH),
    ("26089", "Leelanau", MI_CENTRAL),
    ("26091", "Lenawee", MI_SOUTH),
    ("26093", "Livingston", MI_SOUTH),
    ("26095", "Luce", MI_NORTH),
    ("26097", "Mackinac", MI_NORTH),
    ("26099", "Macomb", MI_SOUTH),
    ("26101", "Manistee", MI_CENTRAL),
    ("26103", "Marquette", MI_NORTH),
    ("26105", "Mason", MI_CENTRAL),
    ("26107", "Mecosta", MI_SOUTH),
    ("26109", "Menominee", MI_NORTH),
    ("26111", "Midland", MI_SOUTH),
    ("26113", "Missaukee", MI_CENTRAL),
    ("26115", "Monroe", MI_SOUTH),
    ("26117", "Montcalm", MI_SOUTH),
    ("26119", "Montmorency", MI_CENTRAL),
    ("26121", "Muskegon", MI_SOUTH),
    ("26123", "Newaygo", MI_SOUTH),
    ("26125", "Oakland", MI_SOUTH),
    ("26127", "Oceana", MI_SOUTH),
    ("26129", "Ogemaw", MI_CENTRAL),
    ("26131", "Ontonagon", MI_NORTH),
    ("26133", "Osceola", MI_CENTRAL),
    ("26135", "Oscoda", MI_CENTRAL),
    ("26137", "Otsego", MI_CENTRAL),
    ("26139", "Ottawa", MI_SOUTH),
    ("26141", "Presque Isle", MI_CENTRAL),
    ("26143", "Roscommon", MI_CENTRAL),
    ("26145", "Saginaw", MI_SOUTH),
    ("26147", "St. Clair", MI_SOUTH),
    ("26149", "St. Joseph", MI_SOUTH),
    ("26151", "Sanilac", MI_SOUTH),
    ("26153", "Schoolcraft", MI_NORTH),
    ("26155", "Shiawassee", MI_SOUTH),
    ("26157", "Tuscola", MI_SOUTH),
    ("26159", "Van Buren", MI_SOUTH),
    ("26161", "Washtenaw", MI_SOUTH),
    ("26163", "Wayne", MI_SOUTH),
    ("26165", "Wexford", MI_CENTRAL),
)

SPCS83_ZONE_BY_FIPS: Mapping[str, Zone] = MappingProxyType(
    {fips: zone for fips, _name, zone in _ROWS}
)
"""County FIPS -> the SPCS 83 zone record MCL 54.231 puts it in."""

COUNTY_NAME_BY_FIPS: Mapping[str, str] = MappingProxyType(
    {fips: name for fips, name, _zone in _ROWS}
)
"""County FIPS -> the county's name as the statute (and TIGER) spells it."""


def _check_table(rows) -> None:
    """Refuse to import a malformed table. if/raise: the suite runs under -O."""
    fips = [r[0] for r in rows]
    names = [r[1] for r in rows]
    if len(set(fips)) != len(fips) or len(set(names)) != len(names):
        raise ValueError("The SPCS 83 county table repeats a FIPS code or a name.")
    for code, name, zone in rows:
        if zone not in (MI_NORTH, MI_CENTRAL, MI_SOUTH):
            raise ValueError(f"{name} ({code}) is mapped to {zone}, not an SPCS 83 zone.")


_check_table(_ROWS)
