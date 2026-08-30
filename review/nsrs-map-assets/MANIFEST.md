# SPCS2022 Michigan zone-map assets — recon capture

**Captured 2026-08-30. Recon only: no production code was touched.**
Everything here is raw source material plus two throwaway analysis scripts.
Per-file bytes and SHA-256 are in `SHA256SUMS.tsv`; the URL and HTTP metadata
for every file I fetched myself are in `fetchlog.tsv`.

Purpose: gather what a *map of the Michigan SPCS2022 zones showing counties*
would need, and find out whether NGS or Michigan publishes an authoritative
county-to-zone assignment.

---

## 1. Tooling trap, recorded first because it fails open

`geodesy.noaa.gov/pub/...` answers **HTTP 200 with a "404 Error: Page Not
Found" HTML body** when the request carries a non-default `User-Agent`. A
Python `urllib` fetch with a custom UA returned three different files all
15,905 bytes and all identical — the error page, under the requested
filenames, with a 200 status. `curl -sI` on the same URLs returned the
correct `Content-Length`, so a HEAD-based size check does **not** catch it.

This is the same failure class as the beta REST API hazard already recorded in
DESIGN.md #61 ("beta's REST API fails open"). **Send no UA override to
geodesy.noaa.gov, and check the magic bytes of every download** (`%PDF`,
`PK\x03\x04`, `\x89PNG`). `fetch.sh` does the download and logging; it warns
on a soft-404 body.

---

## 2. Official NGS maps (raster)

### The Michigan map — `maps/MI_SPCS2022_18_zones_10ppm_slide_2022-10-30.png`

3000 x 2250 px, 2,364,480 bytes,
`f0bd4c524475436b087d1c4994c487e1bd293a7f8cbc5c0ea2e57c0a4f01c4a2`.
From `https://geodesy.noaa.gov/pub/SPCS/DistortionMaps/Michigan_2022-10-30.zip`
(8,136,688 bytes, `e76f3e5d…`), which holds three slides:

| file | what it is |
|---|---|
| `MI_SPCS2022_18_zones_10ppm_slide_2022-10-30.png` | **the 18 LDP zones**, numbered 1–18 with codes L11A…U61K, drawn over county boundaries |
| `MI_SPCS2022_om09999_4500_27400_n26_slide.png` | the statewide oblique-Mercator zone (260001) |
| `MI_existing_GeoRef83_slde.png` | existing SPCS 83 georeference, for comparison |

**Caveat, and it is on the map's own face: the title block reads
"Preliminary SPCS2022 design".** Created 10/30/2022 by Michael Dennis. This is
the newest Michigan-specific map NGS publishes — `pub/SPCS/DistortionMaps/`
carries exactly one Michigan file and this is it. Its zone codes and names
match the final NGS GIS layer exactly (§3), so the geometry is current even
though the word "Preliminary" is not.

The map shows counties, but only as unlabelled boundary lines — **no county
names**. A surveyor who does not already know Michigan's county shapes cannot
read his own county off it.

### National maps showing Michigan

Newer than the Michigan slide, all 4000 x 2250 px, from `beta.ngs.noaa.gov/SPCS/maps/`:

| file | bytes | note |
|---|---|---|
| `05_CONUS_MultizonePartial_20ppm_2026-05-13_wide.png` | 4,880,404 | dated 2026-05-13 |
| `08_CONUS_all_842_zones_20ppm_2026-05-13_wide.png` | 5,638,007 | all CONUS zone layers |
| `04_CONUS_Multizone_20ppm_2025-06-02_wide.png` | 5,859,024 | multizone complete — Michigan's layer |
| `03_CONUS_Multizone_50ppm_2025-06-02_wide.png` | 5,353,025 | |
| `02_CONUS_Statewide_50ppm_2025-06-02_wide.png` | 5,743,986 | |

At CONUS scale Michigan is roughly a tenth of the frame. Useful for context,
not usable as a Michigan working map.

Also captured: `SPCS2022_ZoneLayers_slide_2025-06-09.png`,
`SPCS2022_state_designs_slide_2025-06-09.png`,
`SPCS2022_number_zones_slide_2025-06-09.png` (explainer slides, 3000 x 2250).

---

## 3. Machine-readable zone geography — **found, and it is the good stuff**

NGS publishes the SPCS2022 zones as **public ArcGIS feature services** under
the NOAA org (`owner: NGS.GIS_noaa`), linked from the beta SPCS site as
"Online Interactive Maps" / the Beta SPCS2022 Experience
(`https://noaa.maps.arcgis.com/home/item.html?id=dddb7bc0be6f4e56a1c370c8d529d1a0`).
No key, no login.

Service (multizone complete — Michigan's 18-zone layer):
```
https://services2.arcgis.com/C8EMgrsFcRFL6LrL/arcgis/rest/services/
  Alpha_SPCS2022_Multizone_Complete_Zones_Feature_Layer_View/FeatureServer/0
```
The statewide layer is `Alpha_SPCS2022_Statewide_Zones_Feature_Layer_View`.
Sibling services exist for multizone-partial, special-use and Gulf zones, each
with a matching tiled image service of the distortion raster.

Captured as GeoJSON (WGS 84, `outSR=4326`):

| file | features | vertices | bytes |
|---|---|---|---|
| `raw/MI_SPCS2022_multizone_complete_18zones.geojson` | 18 | 200,622 | 5,688,758 |
| `raw/MI_SPCS2022_statewide_zone.geojson` | 1 (260001) | 176,829 | 5,006,926 |

Every feature carries the full defining parameter set: `ZoneCode`, `AbrvFull`,
`NameFull`, `ProjAbrv`, `Lat0_deg`, `Lon0_W_deg`, `ProjScale`, `SkewAz_deg`,
`FalseN_m`, `FalseE_m`, `FalseN_ift`, `FalseE_ift`, `DesignBy`, `Ref_frame`.

**There is no county field on the layer.**

### Independent confirmation of the build's own zone data

I compared all 19 Michigan zones in `michspc/spc/zones.py` against this layer:
central meridian, origin latitude, projection scale, false easting, false
northing, skew azimuth, projection kind, abbreviation and name.

**153 field comparisons across 19 zones. Zero mismatches.**

This is an independent authority from the one H2 used (`zoneBounds.json` /
the zone-definitions spreadsheet), reached through a different NGS service, and
it agrees exactly. The only cosmetic difference: the build writes `MI_L45G`
where NGS writes `MI L45G` (underscore for space).

### The 18 LDP zones

| # | code | abbrev | name | proj |
|---|---|---|---|---|
| 1 | 261001 | L11A | Ann Arbor | TM |
| 2 | 261002 | L15D | Detroit | TM |
| 3 | 261003 | L21F | Flint | LC1 |
| 4 | 261004 | L25S | Saginaw | LC1 |
| 5 | 261005 | L31R | Roscommon | LC1 |
| 6 | 261006 | L35T | Thunder Bay | LC1 |
| 7 | 261007 | L41Z | Kalamazoo | LC1 |
| 8 | 261008 | L45G | Grand Rapids | LC1 |
| 9 | 261009 | L51N | Newaygo | LC1 |
| 10 | 261010 | L55W | Wexford | LC1 |
| 11 | 261011 | L61L | Leelanau | LC1 |
| 12 | 261012 | L65C | Cheboygan | LC1 |
| 13 | 261013 | U11M | Mackinac | LC1 |
| 14 | 261014 | U21E | Escanaba | TM |
| 15 | 261015 | U31Q | Marquette | TM |
| 16 | 261016 | U41H | Houghton | TM |
| 17 | 261017 | U51B | Bessemer | LC1 |
| 18 | 261018 | U61K | Isle Royale | LC1 |

Plus statewide `260001` MI Michigan (OMC).

### The 2019 MapData package is stale — do not use it for zones

`raw/Michigan_data_2019-05-26.zip` (16,951,308 bytes, `8617889e…`) is the only
Michigan entry in `pub/SPCS/MapData/`. It is dated **2019-05-26**, three years
before the 18-zone design, and contains only the statewide OM design, the old
`MI_S_SPCS83` zone, and distortion rasters — **no LDP zone polygons**. Its
`DataCommon/Michigan.shp` is a state-level outline, not counties. Keep it for
provenance; the feature service above supersedes it.

---

## 4. County boundaries

`raw/MI_counties_tigerweb.geojson` — **83 features, 72,545 vertices,
2,978,517 bytes**, `bcf77b30ba55def250e34168fd9c2b772b78b8f8389fa1db4ce6bd27615fccc7`.

From Census TIGERweb, layer 1 (Counties), `where=STATE='26'`, `outSR=4326`:
```
https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query
```
Fields kept: `GEOID, STATE, COUNTY, BASENAME, NAME, INTPTLAT, INTPTLON, AREALAND`.

Also captured as fallback (national cartographic boundary files, 2024):
`raw/cb_2024_us_county_500k.zip` (11,626,066 B) and
`raw/cb_2024_us_county_5m.zip` (2,982,952 B). Filter to state FIPS 26.
**Note: no `geopandas` or `pyshp` is installed on this machine**, so the
shapefiles cannot be read without adding a dependency — the TIGERweb GeoJSON
needs nothing.

**Important for cartography: Census county polygons extend into the Great
Lakes** (Michigan counties hold submerged land). NGS zone polygons do not.
Drawing Census counties over NGS zones will show county area outside every
zone. That is correct, not a defect.

---

## 5. County-to-zone assignment — **NOT published; derived here instead**

### The honest answer

**No public source names the final 18 zones and their counties.** Confirmed
negative on every avenue:

- NGS `zoneDefinitions.json` — **no county field**. All 18 MI LDP zones are
  `Design by = State`; only 260001 is `NGS`.
- NGS beta "Zone Information" (updated 5/14/2026) — definitions, example
  coordinates, bounding boxes, overlap differences. No county table.
- `geodesy.noaa.gov/SPCS/zones.shtml` ("Final SPCS2022 Zones") — still reads
  **"Table coming soon."**
- NOAA SP NOS NGS 13 (`raw/SP_NOS_NGS_13.pdf`, 6,788,415 B) is the SPCS
  **27/83** compendium; its 20 Michigan mentions are all historical.
- `SPCS2022-Procedures.pdf` (`raw/`, 604,859 B) sets the *rule* but names no
  counties. §5.e.ii: "Well-defined geographic regions (such as counties,
  townships, urbanized areas, etc.) that do not meet the minimum size
  requirement should be aggregated with other areas to create zones that are
  larger than the minimum size."
- `pub/SPCS/ExampleForms/` publishes eight states' design submittals —
  **Michigan's is not among them**. `ExampleLegislation/` has 14 states, no
  Michigan.
- `ZoneDesignSpreadsheets.zip` (84,678,116 B) — generic calculators plus
  Florida and Minnesota worked examples only.
- EPSG has not published SPCS2022 at all (0 results for `SPCS2022`).
- MDOT still documents only the three-zone 1964 system.

**The legislature is a definitive dead end, not a gap.** Michigan HB 5577
(2026; passed House 106-0 on 2026-04-15, now in Senate Regulatory Affairs)
*deletes* the county enumeration rather than updating it — it repeals
MCL 54.232, 54.235 and 54.235a, defers wholly to NGS, and defines only:

> `(f) "Zone" means the geographic areas encompassed by closed contiguous
> county boundaries or submerged lands, or both.`

So no Michigan statute will ever carry the SPCS2022 county table.

### Closest published source: MSPS, April 2020 — historical, superseded

`raw/msps_2020_update_april_newsletter.pdf` (1,025,796 B,
`c850fa9c05a79cb4bb920cfd9d2df4846c7172a567994a663d421b62b82a04ed`),
MSPS 2022 Datum Committee, pp. 4–5, `https://cdn.ymaws.com/www.misps.org/resource/resmgr/committee_reports/2020_datum/2020_update_-_april_newslett.pdf`:

> The zones will encompass the following counties:

with 17 zones — Ann Arbor, Baraga, Cheboygan, Delta, Grand Rapids, Iron,
Kalamazoo, Keweenaw, Marquette, Mio, Newaygo, Oakland, Pickford, Roscommon,
Saginaw, Traverse, Wexford. The committee "retained the Lambert Conic
Conformal projection and applied this to all zones."

**This is the 2020 proposal, not the final design**: 17 zones all Lambert,
where the final is 18 zones with 5 Transverse Mercator. Eight of its zone
names are gone and nine final names are new. Use it as context only.

### What I derived, and how far it can be trusted

`derived_county_zone.csv` — all 83 counties, each with its zone.

Method (`analyze_county_zone.py`, `verify_derivation.py`, both review-only):
sample a 14x14 grid across each county's bounding box, keep the points inside
the county polygon, and ask which NGS zone polygon each falls in. **14,165
sample points.** Points landing in no zone are Great Lakes water (§4) and are
excluded; the test is whether a county's *land* points agree on one zone.

**Result: 82 of 83 counties resolve unanimously to exactly one zone.**

**The one exception is real and worth knowing: Keweenaw County is split
between two zones.** The mainland (Keweenaw Peninsula tip) is in **U41H
Houghton**; **Isle Royale**, which is legally part of Keweenaw County, is its
own zone **U61K Isle Royale (261018)**. Zone 18 contains no whole county. So a
"county → zone" lookup is exact for 82 counties and ambiguous for Keweenaw
unless Isle Royale is called out separately.

Derived zone → counties (17 zones; 261018 Isle Royale is sub-county):

| zone | name | n | counties |
|---|---|---|---|
| 261001 L11A | Ann Arbor | 5 | Hillsdale, Jackson, Lenawee, Livingston, Washtenaw |
| 261002 L15D | Detroit | 4 | Macomb, Monroe, Oakland, Wayne |
| 261003 L21F | Flint | 4 | Genesee, Lapeer, Shiawassee, St. Clair |
| 261004 L25S | Saginaw | 6 | Bay, Huron, Midland, Saginaw, Sanilac, Tuscola |
| 261005 L31R | Roscommon | 6 | Arenac, Clare, Gladwin, Iosco, Ogemaw, Roscommon |
| 261006 L35T | Thunder Bay | 6 | Alcona, Alpena, Crawford, Montmorency, Oscoda, Otsego |
| 261007 L41Z | Kalamazoo | 7 | Berrien, Branch, Calhoun, Cass, Kalamazoo, St. Joseph, Van Buren |
| 261008 L45G | Grand Rapids | 8 | Allegan, Barry, Clinton, Eaton, Ingham, Ionia, Kent, Ottawa |
| 261009 L51N | Newaygo | 7 | Gratiot, Isabella, Mecosta, Montcalm, Muskegon, Newaygo, Oceana |
| 261010 L55W | Wexford | 6 | Lake, Manistee, Mason, Missaukee, Osceola, Wexford |
| 261011 L61L | Leelanau | 5 | Antrim, Benzie, Grand Traverse, Kalkaska, Leelanau |
| 261012 L65C | Cheboygan | 4 | Charlevoix, Cheboygan, Emmet, Presque Isle |
| 261013 U11M | Mackinac | 3 | Chippewa, Luce, Mackinac |
| 261014 U21E | Escanaba | 3 | Alger, Delta, Schoolcraft |
| 261015 U31Q | Marquette | 3 | Dickinson, Marquette, Menominee |
| 261016 U41H | Houghton | 4 | Baraga, Houghton, Iron, Keweenaw *(mainland)* |
| 261017 U51B | Bessemer | 2 | Gogebic, Ontonagon |
| 261018 U61K | Isle Royale | — | *Isle Royale only — part of Keweenaw County* |

Independent corroboration against the MSPS 2020 table: of the nine zone names
common to both, **five have byte-identical county sets** — Cheboygan (4),
Grand Rapids (8), Kalamazoo (7), Newaygo (7), Saginaw (6). Both tables cover
the same 83 counties exactly once. Two independent constructions agreeing on
five whole zones is meaningful evidence the derivation method is sound.

**What this derivation is and is not.** It is a spatial join of two
authorities' own vector geometry — NGS's zone polygons and Census's county
polygons — not a reading of a raster and not a reconstruction from a map
image. It is still **derived, not cited**. If it is ever to drive a
conversion, it needs the same treatment as any other load-bearing table:
a published source, or the owner's explicit acceptance of the derivation with
the Keweenaw exception recorded.

### Where the real table might still be

1. **MSPS post-2020 committee reports.** `misps.org` is Cloudflare-blocked
   from this machine (403) and `web.archive.org` is unreachable. The CDN path
   `cdn.ymaws.com/www.misps.org/resource/resmgr/committee_reports/<year>_datum/`
   is open and worth probing from an ordinary browser.
2. **Michigan's design submittal to NGS**, unpublished. NGS publishes eight
   other states'. Contact: `NGS.SPCS@noaa.gov`.

---

## 6. Files

- `fetchlog.tsv` — timestamp, name, effective URL, bytes, SHA-256, HTTP code,
  content-type for every file fetched by `fetch.sh`.
- `SHA256SUMS.tsv` — bytes and SHA-256 for **every** file in `raw/` and
  `maps/`, including those fetched by the research subagent.
- `fetch.sh` — the download helper (no UA override; warns on soft-404).
- `analyze_county_zone.py`, `verify_derivation.py` — review-only analysis.
- `derived_county_zone.csv` — the derived table, with per-county land sample
  counts and a `unanimous` column (82 `yes`, 1 `NO` = Keweenaw).

Total capture ~190 MB. The two large items —
`raw/ZoneDesignSpreadsheets.zip` (81 MB) and `raw/SP_NOS_NGS_13.pdf` (6.5 MB)
— were checked and hold nothing Michigan-specific; they can be deleted if the
directory is committed.
