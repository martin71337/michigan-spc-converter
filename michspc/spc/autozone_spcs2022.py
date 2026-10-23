"""County -> SPCS2022 low-distortion zone, measured from NGS's beta zone polygons.

**NGS beta.** NGS publishes no county list for its SPCS2022 zones and no
definitional zone-extent file. What it publishes is a beta ArcGIS feature
layer, "Beta SPCS2022 Multizone Complete Zones Feature Layer View" (item
``3e6a8ce23a814b62ae38993394669d8e``, owner NGS.GIS_noaa, item modified
2026-09-21; licence "This is a beta product and zones should not be considered
final", CC0 1.0). The autozone-r0 recon captured Michigan's 18 features from it
on 2026-10-22 in the service's native Web Mercator (wkid 102100 / EPSG 3857) as
``review/autozone-r0/raw/ngs_fs/mi_native.json`` (7,382,157 bytes, SHA-256
``0b40098476f55a04d8bd9f5b4b162b2f573cddf00e7054c39693b7441e3c7cf7``;
re-fetched byte-identical 2026-10-23 by ``review/autozone-z0/capture_ngs_polygons.py``).
Inverse-projected on the EPSG 3857 sphere with no datum shift, it was measured
(RECON.md section 2.2, re-measured 2026-10-23 on the geometry the test reads):

* every internal line of those polygons lies on a Census TIGER county line -
  0.025 m worst over 42,896 samples (every vertex of 11,875 shared edges, and
  at most 100 m apart), and every land stretch of a TIGER county line between
  two zones lies on an NGS line, 0.029 m worst over 42,854 samples - the zones
  are unions of whole counties;
* each county's land falls 100% in one zone, EXCEPT Keweenaw, whose Isle
  Royale is zone 261018 (U61K) and whose mainland is 261016 (U41H).

The service's ``outSR=4269`` capture, ``mi_4269.json`` (SHA-256 ``658c4ead...``),
is not used: the server re-projected it through a WGS 84 -> NAD 83
transformation, moving every line about 0.9 m (1.08 m worst) off TIGER's, so a
point 0.06 m inside Livingston at 42.7787768 N 84.0242281 W lands in Genesee's
zone on it (gate-autozone-1 finding 2).

This table is that measurement. ``tests/test_autozone_tables.py`` re-derives
it from the native capture: it re-measures the line agreement above, samples
each county's interior, tests every sample against all 18 NGS polygons, and
requires every land sample to fall in exactly the zone this table gives the
county (Keweenaw: on the side of the split this module states). Re-freeze
obligation: docs/REFREEZE-NSRS.md.

**The polygons are evidence, not the shipped data** (plan L3). They are
clipped at the shoreline, so a Great Lakes point is in none of them, while
NGS's own NCAT assigns water points by the county whose water they are in
(RECON.md section 3; 14/14 water probes). The shipped county polygons are
water-extended, and this table gives each county its zone.

**Only the eighteen local zones.** The statewide zone 260001 is never a value
here (owner's decision, plan section 1 item 2: Auto on NATRF2022 picks the
local low-distortion zone); an import-time check refuses it.

The Isle Royale rule
--------------------

**A Keweenaw County position at or north of 47.65 degrees N is zone 261018
(U61K, Isle Royale); south of it, 261016 (U41H, Houghton).** No NGS text states
this rule. Two things support it, and neither is a definition:

* NGS's own ``zoneBounds.json`` (frozen, review/nsrs-n0/raw, SHA-256 in
  ``michspc.spc.zones``) gives U41H a north bound of 47.65 and U61K a south
  bound of 47.65 - transcribed into those zones' ``lat_max`` / ``lat_min``;
* beta NCAT switches between them at that parallel in Keweenaw's water:
  three bisections (88.95 W, 88.14 W, 87.66 W) bracketed the switch between
  47.6491 and 47.6504 N, a resolution of about 100 m (RECON.md section 2.3).
  Whether NCAT's line is EXACTLY 47.65 was not proven.

The parallel lies wholly in Lake Superior: Isle Royale's land is north of it
and the Keweenaw Peninsula's south of it (the test holds both against NGS's
polygons). The tie - a latitude of exactly 47.65 - goes north, to U61K; that is
this program's choice, stated, since nothing published decides it.
Ontonagon and Alger waters north of 47.65 stay in their own counties' zones
(U51B, U21E), as NCAT does (RECON.md section 2.3) - the rule is Keweenaw's only.

FIPS codes and county names are TIGER 2025's (see ``autozone_spcs83``).
Zones are the ``michspc.spc.zones`` records themselves, by identity.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from michspc.spc.zones import SPCS2022_ZONES, Zone, zone_by_code

NGS_POLYGONS_CITATION = (
    "NGS beta, 'Beta SPCS2022 Multizone Complete Zones Feature Layer View' "
    "(ArcGIS item 3e6a8ce23a814b62ae38993394669d8e, NGS.GIS_noaa), Michigan "
    "features captured 2026-10-22 in native Web Mercator, "
    "review/autozone-r0/raw/ngs_fs/mi_native.json, "
    "SHA-256 0b40098476f55a04d8bd9f5b4b162b2f573cddf00e7054c39693b7441e3c7cf7; "
    "zones measured as unions of TIGER county lines (RECON.md section 2.2)"
)

KEWEENAW_FIPS = "26083"
ISLE_ROYALE_SPLIT_LATITUDE = 47.65
"""Degrees N. See "The Isle Royale rule" above: zoneBounds.json's shared
U41H/U61K bound, and beta NCAT's measured switch (~100 m resolution)."""

ISLE_ROYALE_ZONE: Zone = zone_by_code("261018")  # U61K Isle Royale
KEWEENAW_MAINLAND_ZONE: Zone = zone_by_code("261016")  # U41H Houghton

# (FIPS, county name, zone code). Sorted by FIPS. Keweenaw's code is the
# mainland zone; ``ldp_zone`` applies the Isle Royale rule on top of it.
_ROWS: tuple[tuple[str, str, str], ...] = (
    ("26001", "Alcona", "261006"),  # L35T Thunder Bay
    ("26003", "Alger", "261014"),  # U21E Escanaba
    ("26005", "Allegan", "261008"),  # L45G Grand Rapids
    ("26007", "Alpena", "261006"),  # L35T Thunder Bay
    ("26009", "Antrim", "261011"),  # L61L Leelanau
    ("26011", "Arenac", "261005"),  # L31R Roscommon
    ("26013", "Baraga", "261016"),  # U41H Houghton
    ("26015", "Barry", "261008"),  # L45G Grand Rapids
    ("26017", "Bay", "261004"),  # L25S Saginaw
    ("26019", "Benzie", "261011"),  # L61L Leelanau
    ("26021", "Berrien", "261007"),  # L41Z Kalamazoo
    ("26023", "Branch", "261007"),  # L41Z Kalamazoo
    ("26025", "Calhoun", "261007"),  # L41Z Kalamazoo
    ("26027", "Cass", "261007"),  # L41Z Kalamazoo
    ("26029", "Charlevoix", "261012"),  # L65C Cheboygan
    ("26031", "Cheboygan", "261012"),  # L65C Cheboygan
    ("26033", "Chippewa", "261013"),  # U11M Mackinac
    ("26035", "Clare", "261005"),  # L31R Roscommon
    ("26037", "Clinton", "261008"),  # L45G Grand Rapids
    ("26039", "Crawford", "261006"),  # L35T Thunder Bay
    ("26041", "Delta", "261014"),  # U21E Escanaba
    ("26043", "Dickinson", "261015"),  # U31Q Marquette
    ("26045", "Eaton", "261008"),  # L45G Grand Rapids
    ("26047", "Emmet", "261012"),  # L65C Cheboygan
    ("26049", "Genesee", "261003"),  # L21F Flint
    ("26051", "Gladwin", "261005"),  # L31R Roscommon
    ("26053", "Gogebic", "261017"),  # U51B Bessemer
    ("26055", "Grand Traverse", "261011"),  # L61L Leelanau
    ("26057", "Gratiot", "261009"),  # L51N Newaygo
    ("26059", "Hillsdale", "261001"),  # L11A Ann Arbor
    ("26061", "Houghton", "261016"),  # U41H Houghton
    ("26063", "Huron", "261004"),  # L25S Saginaw
    ("26065", "Ingham", "261008"),  # L45G Grand Rapids
    ("26067", "Ionia", "261008"),  # L45G Grand Rapids
    ("26069", "Iosco", "261005"),  # L31R Roscommon
    ("26071", "Iron", "261016"),  # U41H Houghton
    ("26073", "Isabella", "261009"),  # L51N Newaygo
    ("26075", "Jackson", "261001"),  # L11A Ann Arbor
    ("26077", "Kalamazoo", "261007"),  # L41Z Kalamazoo
    ("26079", "Kalkaska", "261011"),  # L61L Leelanau
    ("26081", "Kent", "261008"),  # L45G Grand Rapids
    ("26083", "Keweenaw", "261016"),  # U41H Houghton; Isle Royale -> U61K by rule
    ("26085", "Lake", "261010"),  # L55W Wexford
    ("26087", "Lapeer", "261003"),  # L21F Flint
    ("26089", "Leelanau", "261011"),  # L61L Leelanau
    ("26091", "Lenawee", "261001"),  # L11A Ann Arbor
    ("26093", "Livingston", "261001"),  # L11A Ann Arbor
    ("26095", "Luce", "261013"),  # U11M Mackinac
    ("26097", "Mackinac", "261013"),  # U11M Mackinac
    ("26099", "Macomb", "261002"),  # L15D Detroit
    ("26101", "Manistee", "261010"),  # L55W Wexford
    ("26103", "Marquette", "261015"),  # U31Q Marquette
    ("26105", "Mason", "261010"),  # L55W Wexford
    ("26107", "Mecosta", "261009"),  # L51N Newaygo
    ("26109", "Menominee", "261015"),  # U31Q Marquette
    ("26111", "Midland", "261004"),  # L25S Saginaw
    ("26113", "Missaukee", "261010"),  # L55W Wexford
    ("26115", "Monroe", "261002"),  # L15D Detroit
    ("26117", "Montcalm", "261009"),  # L51N Newaygo
    ("26119", "Montmorency", "261006"),  # L35T Thunder Bay
    ("26121", "Muskegon", "261009"),  # L51N Newaygo
    ("26123", "Newaygo", "261009"),  # L51N Newaygo
    ("26125", "Oakland", "261002"),  # L15D Detroit
    ("26127", "Oceana", "261009"),  # L51N Newaygo
    ("26129", "Ogemaw", "261005"),  # L31R Roscommon
    ("26131", "Ontonagon", "261017"),  # U51B Bessemer
    ("26133", "Osceola", "261010"),  # L55W Wexford
    ("26135", "Oscoda", "261006"),  # L35T Thunder Bay
    ("26137", "Otsego", "261006"),  # L35T Thunder Bay
    ("26139", "Ottawa", "261008"),  # L45G Grand Rapids
    ("26141", "Presque Isle", "261012"),  # L65C Cheboygan
    ("26143", "Roscommon", "261005"),  # L31R Roscommon
    ("26145", "Saginaw", "261004"),  # L25S Saginaw
    ("26147", "St. Clair", "261003"),  # L21F Flint
    ("26149", "St. Joseph", "261007"),  # L41Z Kalamazoo
    ("26151", "Sanilac", "261004"),  # L25S Saginaw
    ("26153", "Schoolcraft", "261014"),  # U21E Escanaba
    ("26155", "Shiawassee", "261003"),  # L21F Flint
    ("26157", "Tuscola", "261004"),  # L25S Saginaw
    ("26159", "Van Buren", "261007"),  # L41Z Kalamazoo
    ("26161", "Washtenaw", "261001"),  # L11A Ann Arbor
    ("26163", "Wayne", "261002"),  # L15D Detroit
    ("26165", "Wexford", "261010"),  # L55W Wexford
)

LDP_ZONE_BY_FIPS: Mapping[str, Zone] = MappingProxyType(
    {fips: zone_by_code(code) for fips, _name, code in _ROWS}
)
"""County FIPS -> its SPCS2022 low-distortion zone record (Keweenaw: mainland;
use ``ldp_zone`` for a position, which applies the Isle Royale rule)."""

COUNTY_NAME_BY_FIPS: Mapping[str, str] = MappingProxyType(
    {fips: name for fips, name, _code in _ROWS}
)


def ldp_zone(fips: str, latitude: float) -> Zone | None:
    """The low-distortion zone of a position in county ``fips`` at ``latitude``.

    None for a FIPS the table does not carry (the caller refuses by name).
    """
    if fips == KEWEENAW_FIPS and latitude >= ISLE_ROYALE_SPLIT_LATITUDE:
        return ISLE_ROYALE_ZONE
    return LDP_ZONE_BY_FIPS.get(fips)


_STATEWIDE = zone_by_code("260001")


def _check_table() -> None:
    """Refuse to import a malformed table. if/raise: the suite runs under -O."""
    fips = [r[0] for r in _ROWS]
    names = [r[1] for r in _ROWS]
    if len(set(fips)) != len(fips) or len(set(names)) != len(names):
        raise ValueError("The SPCS2022 county table repeats a FIPS code or a name.")
    local = set(SPCS2022_ZONES) - {_STATEWIDE}
    used = set(LDP_ZONE_BY_FIPS.values()) | {ISLE_ROYALE_ZONE}
    if _STATEWIDE in used:
        raise ValueError(
            "The SPCS2022 county table maps a county to the statewide zone "
            "260001; Auto chooses the local low-distortion zone only."
        )
    if used != local:
        raise ValueError(
            "The SPCS2022 county table does not use each of the 18 local zones: "
            f"unused {sorted(z.code for z in local - used)}."
        )


_check_table()
