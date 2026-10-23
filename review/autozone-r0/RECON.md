# autozone-r0 — recon for an "Auto" zone entry (SPCS 83 and SPCS2022, Michigan)

Recon only, 2026-10-22. Nothing in `michspc/` or `tests/` was touched. Every
download is under `raw/` (one folder per source). The scripts are beside this
file. Derived results are in `work/`. Downloads were read with `py -I`, or
with a scratch venv (shapely 2.2.0, pyproj 3.8.0, pyshp 3.1.6) run with `-I`.
That venv lives in the session scratchpad and is not part of the repo.

## Bottom line

1. **SPCS 83 zones are legally county unions.** The authority is MCL 54.231(3)–(5)
   (Act 9 of 1964, as amended by 1988 PA 154). The legal object is "the area
   included in" the named counties, and Michigan counties extend into the
   Great Lakes. No polygon is legally authoritative: every polygon of these
   zones is a GIS picture of county lines.
2. **SPCS2022 Michigan LDP zones are also county unions** (with one exception,
   below). NGS's beta polygons have internal lines that sit on Census TIGER
   county edges to **0.026 m worst** (23,957 samples). The one non-county split
   is Keweenaw County: Isle Royale goes to U61K and the rest to U41H. In the
   water, NCAT splits Keweenaw at about **47.65° N**.
3. **NGS's published SPCS2022 polygons are LAND-ONLY.** They are clipped at
   the shoreline and have 232 holes. NGS's own NCAT is not land-only: it
   assigns Great Lakes points by the county whose water they are in. Bundling
   the NGS feature-service polygons as they are would refuse every water point
   NCAT accepts.
4. **NCAT returns the zone for a lat/long, for both systems.** Production REST
   does this for SPCS 83. The beta web app does it for SPCS2022. It is the
   truth source to freeze anchors from. However, **NCAT uses two different
   county-line datasets internally**, and they disagree by up to about 17 m on
   land (§5.3).
5. **Recommended bundled form:** a county table and county polygons, not zone
   polygons. Use 83 water-extended county polygons, plus a county → zone table
   for each system, plus the Keweenaw rule at 47.65° N. Data source details and
   open choices are in §6.

---

## 1. SPCS 83 Michigan: the legal definition and the polygon sources

### 1.1 Statute (captured `raw/statute/mcl-54-231.html` … `-239.html`, legislature.mi.gov, 2026-10-22)

MCL 54.231(2) divides the state into north, central and south zones.
Subsections (3)–(5) define each zone as "the area included in the following
counties". History line: "1964, Act 9, Eff. Aug. 28, 1964; Am. 1988, Act 154,
Imd. Eff. June 14, 1988".

| Zone | Code | Counties (MCL 54.231) | Count |
|---|---|---|---|
| North | 2111 | Gogebic, Ontonagon, Houghton, Keweenaw, Baraga, Iron, Marquette, Dickinson, Menominee, Alger, Delta, Schoolcraft, Luce, Chippewa, Mackinac | 15 |
| Central | 2112 | Emmet, Cheboygan, Presque Isle, Charlevoix, Leelanau, Antrim, Otsego, Montmorency, Alpena, Benzie, Grand Traverse, Kalkaska, Crawford, Oscoda, Alcona, Manistee, Wexford, Missaukee, Roscommon, Ogemaw, Iosco, Mason, Lake, Osceola, Clare, Gladwin, Arenac | 27 |
| South | 2113 | Oceana, Newaygo, Mecosta, Isabella, Midland, Bay, Huron, Muskegon, Montcalm, Gratiot, Saginaw, Tuscola, Sanilac, Ottawa, Kent, Ionia, Clinton, Shiawassee, Genesee, Lapeer, St. Clair, Allegan, Barry, Eaton, Ingham, Livingston, Oakland, Macomb, Van Buren, Kalamazoo, Calhoun, Jackson, Washtenaw, Wayne, Berrien, Cass, St. Joseph, Branch, Hillsdale, Lenawee, Monroe | 41 |

The counts sum to 83, which is every Michigan county. The names were checked
by script against both polygon sources: no county is missing and none is extra.

- **MCL 54.234** covers a tract that crosses a zone line. The tract "may be
  referred to either of the 2 zones", and the zone used "shall be specifically
  named in the description". This is the only statutory rule on boundary cases.
  It permits either zone; it does not resolve a point that sits exactly on the line.
- **Every boundary is a county line, but the county lines run through water.**
  The North/Central line is all water: the Straits, Lake Michigan and Lake
  Huron. The Central/South line runs 233 km on land. It continues into Lake
  Michigan (Mason/Oceana) and into Saginaw Bay and Lake Huron (Arenac,
  Iosco/Huron, Bay). North and South never touch. In MGF, the N/C shared line
  is 296 km and the C/S line is 435 km.
- **The legislation is pending: HB 5577 of 2026** (`raw/statute/2026-HEBH-5577.htm`,
  as passed by the House 106–0 on 2026-04-15; referred to the Senate Committee
  on Regulatory Affairs 2026-04-16; no later action as of 2026-10-22). The
  `FormattedStrike` spans in that document **strike subsections (2)–(5)**, which
  are the three zones and their county lists. A `FormattedNew` span adds:
  *"Zone" means the geographic areas encompassed by closed contiguous county
  boundaries or submerged lands, or both.* If enacted, the statute stops
  listing counties per zone and defers to NGS/NSRS. Zones stay county-and-water
  based.
- **NOS NGS 5** (the SPCS 83 manual in `docs/`) was not checked for a county
  table in this round.

### 1.2 Polygon sources found

| Source | What it is | Water? | Datum / CRS | Size, SHA-256 | Licence |
|---|---|---|---|---|---|
| **State of Michigan "County Boundaries-Extended"** (item `dcbf3b3eb47941cf9fb764b5f5308b15`, owner `michigan_admin`, service `services3.arcgis.com/dxRQUfTDNtfqZ301/.../CountyNoClip/FeatureServer/0`, data last edited 2026-01-13, `MGFVersion` V25) | The state's own Michigan Geographic Framework. The item says "extended to Michigan's legal boundary in the Great Lakes and international boundary" | yes | EPSG:3078, NAD83 Michigan Oblique Mercator | `raw/mi_counties_extended/counties_native.json`, 2,435,776 B, `5a854712…cf42`; 83 counties, 93,326 vertices | "public record … no restrictions on use, reproduction, or distribution", provided AS IS (DTMB Center for Shared Solutions) |
| **Census TIGER/Line 2025 counties** (`www2.census.gov/geo/tiger/TIGER2025/COUNTY/tl_2025_us_county.zip`, Last-Modified 2025-09-23) | Federal county polygons. The Michigan counties extend into the Great Lakes (ALAND 146,626 km², AWATER 103,860 km²) | yes | NAD83 geographic (EPSG:4269) | 83,989,800 B, `9c6e9d90…f763`; Michigan: 83 counties, 72,545 vertices | US Government work, public domain |
| **NGS 2019 design data** `geodesy.noaa.gov/pub/SPCS/MapData/Michigan_data_2019-05-26.zip` | `DataCommon/MI_S_SPCS83.shp`: NGS's own South-zone polygon, land-only. Its metadata lineage shows it was built from Esri `dtl_cnty` (detailed counties), not from an independent source | no | GCS NAD 1983 (2011) | 16,951,308 B, `8617889e…8288` | NGS (public) |
| **Esri "USA State Plane Zones NAD83"** (`services.arcgis.com/P3ePLMYs2RVChkJx/.../USA_State_Plane_Zones_NAD83`). NGS's own web map lists this as an "Additional Data Set" | Generalized: 211 / 72 / 69 vertices for N / C / S. The metadata says it is an "approximation … for visual reference" | no | WGS 84 | `raw/esri_spcs83/mi.json`, 11,209 B | Esri; not suitable |

No NGS-published SPCS 83 zone polygon file exists for download. The NGS ArcGIS
organisation (`NGS.GIS_noaa`, 78 items, `raw/ngs_pages/arcgis_search_ngs.json`)
has SPCS2022 layers only. NGS's own map shows SPCS 83 zones using Esri's
generalized layer. The public NCAT library's zone lookup
(`noaa-ngs/ncat-lib`, `SpcUtil.getZone`, `raw/ncatlib/SpcUtil.java`) is a stub
that returns `"0000"`. The polygons NCAT actually uses are server-side and
unpublished.

### 1.3 How much the sources disagree (`analyze.py`, `work/analysis.json`)

The SPCS 83 zones were dissolved from each county source per the statute. The
C/S and N/C shared lines were sampled every 50 m along the MGF line, and the
distance to the TIGER line measured. Land and water were classified with the
NGS 2019 `Michigan.shp` land polygon.

| Line | Samples | Median | p95 | Max | Where the max is |
|---|---|---|---|---|---|
| Central/South, **land** | 4,657 | 0.04 m | 11.8 m | **40.1 m** | — |
| Central/South, **water** | 4,044 | 116 m | 363 m | **444 m** | 44.167 N, 83.000 W (Lake Huron) |
| North/Central (all water) | 5,921 | 9.5 m | 767 m | **11,807 m** | 45.772 N, 83.485 W (Lake Huron, where the line meets the international boundary) |

- **Zone area that changes hands between MGF and TIGER:** N 158 km², C 102 km², S 55 km².
- **State outline, MGF vs TIGER:** symmetric difference 215 km². The Hausdorff
  distance is 6.1 km; the worst place is in the lakes or at the international line.
- **NGS 2019 South polygon vs the MGF South zone:** the C/S line is offset by a
  median of 25.8 m. It is land-clipped, so its Hausdorff distance is 70 km.
- **Esri generalized:** the C/S line is offset by a median of 599 m. Esri
  answers None for every Great Lakes probe. Not usable.
- Neither county source has overlaps or interior holes (0.0 m² for each).

**Which source is most authoritative?** None is legally authoritative; the
legal line is the surveyed county line. As a GIS picture, the MGF is the
State of Michigan's own framework and explicitly carries the legal Great Lakes
boundary. TIGER is the federal picture. On land, NCAT's SPCS 83 answer follows
MGF and not TIGER (§5.3). In water near the MGF line, NCAT's SPCS 83 answer
follows TIGER and not MGF (§5.2). So NCAT matches neither source everywhere.

---

## 2. SPCS2022 Michigan LDP zones

### 2.1 Where the polygons are

- **NGS "Beta SPCS2022 Multizone Complete Zones Feature Layer View"**: item
  `3e6a8ce23a814b62ae38993394669d8e`, owner `NGS.GIS_noaa`, item modified
  2026-09-21, data last edited around 2026-09-20. Service URL:
  `https://services2.arcgis.com/C8EMgrsFcRFL6LrL/arcgis/rest/services/Alpha_SPCS2022_Multizone_Complete_Zones_Feature_Layer_View/FeatureServer/0`.
  Query used: `where=StateAbrv='MI'` (18 features, 261001–261018, attributes
  match `zoneDefinitions.json`). Captures:
  - `raw/ngs_fs/mi_native.json`: 7,382,157 B, `0b400984…c7f7`, native Web Mercator.
  - `raw/ngs_fs/mi_4269.json`: 6,179,489 B, outSR 4269.
  - Statewide 260001 (separate layer): `raw/ngs_fs/mi_statewide_native.json`,
    6,509,520 B, `12962f33…bcfae`.
  - Licence (item `licenseInfo`): *"This is a beta product and zones should not
    be considered final … not subject to copyright … CC0 1.0"*.
  - Linked from the "Beta SPCS2022 Experience" (`dddb7bc0…`), which is linked
    from `geodesy.noaa.gov/SPCS/download.shtml`.
- NGS publishes **no downloadable file** (shapefile or GeoJSON) of the final
  zone polygons. `pub/SPCS/MapData/Michigan_data_2019-05-26.zip` contains 2019
  design-study rasters and the SPCS 83 South polygon, not the LDP zones.
  `pub/SPCS/ZoneDesignData/` lists only national design inputs: DataCommon
  308 MB, ElpsdHtRaster 898 MB, and others; not downloaded.
- `zoneBounds.json` (N0 capture) holds only lat/long rectangles. U41H and U61K
  meet at exactly 47.65° there, which matches NCAT's Keweenaw water split (§2.3).

### 2.2 What they are (`analyze.py`, `ldp_detail.py`)

- **County unions.** Internal LDP lines lie on TIGER county edges: median
  0.000 m, p95 0.000 m, **max 0.026 m** over 23,957 samples at 100 m. Against
  MGF county edges: median 0.03 m, p95 2.4 m, max 167 m. **NGS built these
  from TIGER-family county lines.**
- **Composition** (each county's land assigned 100% to one zone):

| Zone | Abbr | Counties |
|---|---|---|
| 261001 | L11A Ann Arbor | Hillsdale, Jackson, Lenawee, Livingston, Washtenaw |
| 261002 | L15D Detroit | Macomb, Monroe, Oakland, Wayne |
| 261003 | L21F Flint | Genesee, Lapeer, Shiawassee, St. Clair |
| 261004 | L25S Saginaw | Bay, Huron, Midland, Saginaw, Sanilac, Tuscola |
| 261005 | L31R Roscommon | Arenac, Clare, Gladwin, Iosco, Ogemaw, Roscommon |
| 261006 | L35T Thunder Bay | Alcona, Alpena, Crawford, Montmorency, Oscoda, Otsego |
| 261007 | L41Z Kalamazoo | Berrien, Branch, Calhoun, Cass, Kalamazoo, St. Joseph, Van Buren |
| 261008 | L45G Grand Rapids | Allegan, Barry, Clinton, Eaton, Ingham, Ionia, Kent, Ottawa |
| 261009 | L51N Newaygo | Gratiot, Isabella, Mecosta, Montcalm, Muskegon, Newaygo, Oceana |
| 261010 | L55W Wexford | Lake, Manistee, Mason, Missaukee, Osceola, Wexford |
| 261011 | L61L Leelanau | Antrim, Benzie, Grand Traverse, Kalkaska, Leelanau |
| 261012 | L65C Cheboygan | Charlevoix, Cheboygan, Emmet, Presque Isle |
| 261013 | U11M Mackinac | Chippewa, Luce, Mackinac |
| 261014 | U21E Escanaba | Alger, Delta, Schoolcraft |
| 261015 | U31Q Marquette | Dickinson, Marquette, Menominee |
| 261016 | U41H Houghton | Baraga, Houghton, Iron, **Keweenaw (mainland, 60.8% of its land)** |
| 261017 | U51B Bessemer | Gogebic, Ontonagon |
| 261018 | U61K Isle Royale | **Keweenaw (Isle Royale, 39.2% of its land)** |

- **No overlaps:** no pair of zones intersects by more than 1 m².
- **No gaps on land between zones.** The union is identical to the statewide
  260001 polygon (difference 0.0000 km²).
- **The polygons are land-only.** The union is 150,565 km², against 250,363 km²
  for the TIGER counties with their water. It contains **232 interior holes,
  25.3 km² in total**. The largest is 2.63 km² at 45.748 N, 84.460 W. Several
  are inland lakes, for example on Beaver Island. Zones are also split into many
  parts by islands; U11M alone has 189 parts.
- The holes conflict with NGS's own policy: SPCS2022 Policy §III.B.2.c says *"A
  zone polygon can include holes only if it is based on a political boundary
  that includes the same holes."* That suggests the feature service is a
  display product, not the definitional extent. This is my inference; NGS
  does not say so.
- **The polygons' datum is unknown.** The service stores Web Mercator
  (wkid 102100). The fields record `Ref_frame = NATRF2022`, which is the zone's
  frame, not the geometry's. Because the internal lines equal TIGER (NAD83)
  coordinates to 2.6 cm, the numbers are NAD83 county-line numbers, whatever
  label is attached.

### 2.3 Keweenaw / Isle Royale in the water (from NCAT, §5)

Three bisections along transects from the Keweenaw Peninsula to Isle Royale
found NCAT switching from U41H to U61K between:

- 47.6491 and 47.6501 N (88.14 W)
- 47.6492 and 47.6504 N (88.95 W)
- 47.6492 and 47.6504 N (87.66 W)

That is consistent with the **parallel 47.65° N** across Keweenaw County
waters. No published NGS text states this rule; it is measured from NCAT only.
Ontonagon and Alger waters north of 47.65° stay in their own counties' zones,
U51B and U21E (confirmed by NCAT).

---

## 3. Edge cases

- **Tolerance of the sources.** None of them publishes positional accuracy for
  the county lines. Measured instead:
  - MGF vs TIGER on land: 0.04 m median, 11.8 m p95, 40 m max.
  - In water: hundreds of metres, and up to 11.8 km at the international line.
  - NGS LDP vs TIGER: 2.6 cm.
  - NCAT's SPCS 83 boundary: within 0.3 m of MGF at all 9 land places tested.
  - NCAT's SPCS2022 boundary: within 0.3 m of TIGER/NGS at all 16 lines tested.
- **Great Lakes water.** By statute (SPCS 83) and HB 5577 ("submerged lands"),
  zones cover the water. **NCAT assigns water points by county** in both
  systems: 10/10 water probes for SPCS 83 and 9/9 for SPCS2022 in round 1.
  14 random water points were chosen so that "county's zone" and "nearest
  land's zone" disagree; NCAT followed the county rule 14/14. Lake Michigan off
  Oceana gives L51N / South; off Mason it gives L55W / Central. Saginaw Bay
  (Huron waters) gives L25S / South.
- **Outside Michigan.** The checks were Lake Michigan off Wisconsin, Lake Erie
  at 41.80 N 83.30 W (Ohio waters), Toledo, South Bend, Marinette, Windsor and
  Ontario waters of Lake Huron. In every case NCAT returns the other state's
  zone, or `N/A` for Canada. Every county-polygon source returns no county.
  "Outside the union of Michigan's 83 counties → refuse" therefore matches
  NCAT's MI/non-MI answer at all 8 outside points tested. One of them, the
  intended "Detroit River" point at 42.30 N 83.08 W, turned out to be on the
  Canadian side.
- **A point exactly on a boundary.** No published NGS rule was found.
  - SPCS2022 Policy rev. 3 (2023-07-01, `raw/ngs_policy/SPCS2022-Policy.pdf`)
    *removed* its "default zones" section as "no longer relevant".
  - Policy §III.B.2.c requires non-overlapping zone polygons, which makes "on
    the line" a measure-zero case that it leaves undefined.
  - The only rule found is MCL 54.234, which allows either zone if it is named.
  - A design choice is needed: break the tie deterministically, or flag points
    within X m of a line.
- **NAD 83 vs NATRF2022 (about 1.2 m).** Measured at the Jackson/Ingham line,
  42.4221 N 84.3688 W:
  - With input and output both NATRF2022, NCAT's pick flips between −0.3 m and
    +0.3 m of the TIGER line, using the same numbers.
  - With NAD83(2011) input and NATRF2022 output, the pick flips between −1.5 m
    and −0.7 m.
  - So NCAT picks the zone from the **output NATRF2022 position**, tested
    against a polygon whose numbers are TIGER/NAD83 county lines. The NAD83 →
    NATRF shift there is +0.937 m N (N0 FINDINGS §1.4).
  - The datum matters only for points within about 1.2 m of a line. That is
    well under the MGF–TIGER disagreement on land, so it is not the binding
    uncertainty.

---

## 4. Size and format

All counts are measured in `work/bundle_sizes.json` and `work/analysis.json`.

| Representation | Vertices | Approx. size as float64 pairs |
|---|---|---|
| 83 water-extended counties, TIGER | 72,545 | ~1.16 MB |
| 83 water-extended counties, MGF | 93,326 | ~1.49 MB |
| SPCS 83 zones dissolved from TIGER (3 polygons) | 14,309 | ~0.23 MB |
| LDP zones dissolved from TIGER counties (17 + Keweenaw rule) | 35,855 | ~0.57 MB |
| NGS LDP feature-service polygons as published (land-only) | 200,568 | ~3.2 MB |
| Michigan state outline alone (TIGER) | 10,721 | ~0.17 MB |

**Simplification cost.** Each zone was simplified independently with
Douglas–Peucker in EPSG:3078 metres. By construction, the maximum deviation is
at most the tolerance.

| Tolerance | SPCS 83 zones (MGF): vertices / overlap / new gaps | NGS LDP: vertices / overlap |
|---|---|---|
| 0.5 m | 9,911 / 149 m² / 72 m² | 175,207 / 1,521 m² |
| 1 m | 8,751 / 1,496 m² / 478 m² | 150,092 / 3,754 m² |
| 5 m | 4,476 / 13,613 m² / 33,964 m² | 79,535 / 74,705 m² |
| 25 m | 1,713 / 364,969 m² / 158,803 m² | 28,559 / 1,417,498 m² |

Simplifying zones independently **creates overlaps and gaps** along shared
lines. Simplification would have to be done on shared arcs (topology), or not
at all. At these sizes it is not needed: about 1 MB is smaller than the
GEOID18 tile MCX already ships.

**Point-in-polygon on geodetic coordinates.**

- TIGER is NAD83 lat/long.
- MGF is EPSG:3078; converting it to NAD83 lat/long is a pure projection with
  no datum shift.
- The NGS LDP polygons hold TIGER's NAD83 numbers (§2.2).
- Over sub-kilometre segments, planar point-in-polygon on lat/long is adequate.
  Lines in these sources are straight segments between dense vertices.

---

## 5. NCAT as the truth source (`probe_ncat.py`, `probe3_ncat.py`; raw responses in `raw/ncat_probe/`, 394 files; results in `work/*ncat*.json`, `work/classify*.`)

### 5.1 Working queries

- **SPCS 83 (production REST)**: omit `spcZone`, and NCAT picks the zone itself.
  ```
  https://geodesy.noaa.gov/api/ncat/llh?lat=44.0&lon=-85.0&inDatum=NAD83(2011)&outDatum=NAD83(2011)
  → "spcZone": "MI C-2112"
  ```
  Outside Michigan the answer is another state's zone, e.g. `WI C-4802` or
  `OH N-3401`; Canada gives `N/A`.
- **SPCS2022 (beta web app only; no REST accepts NATRF2022, N0 FINDINGS §1.1)**:
  POST the JSF form at `https://beta.ngs.noaa.gov/NCAT/`. Set `indatum` and
  `outdatum` to `NATRF2022 epoch 2020.00`. Leave `zonelist_input` at the page's
  default `Auto Pick (default zone)`. Set **both** `lat_input`/`lat_hinput` and
  `lon_input`/`lon_hinput`. The result row is `Zone | MI L45G-261008 (Multizone complete)`.
  - Verified: 43.0 N, 84.5 W reproduces the frozen N0 anchor exactly,
    N 251,022.875 m and E 1,462,702.380 m.
  - **The beta app changed since the 2026-08-29 capture.** The result panel is
    now labelled "Converted Coordinate" (was "Transformed Coordinate").
  - The zone list default is now `Auto Pick (default zone)`.
  - `review/nsrs-n0/capture_ncat_beta.py` **no longer gets a result as
    written**. It needs `lat_hinput` set and the new label.
  - Auto-pick chooses the multizone (LDP) layer, never 260001.

### 5.2 Round 1: straddles of the MGF lines, plus fixed water and outside points

SPCS 83 (88 probes):

- NCAT equals the TIGER-derived zone 88/88.
- NCAT equals the MGF-derived zone 78/88. The 10 differences are all in Great
  Lakes water, within 15–200 m of the MGF water line:
  - Huron waters off Saginaw Bay
  - Oceana waters in Lake Michigan
  - Chippewa and Charlevoix waters

SPCS2022 (76 probes):

- 60 straddle probes at ±15, 50 and 500 m on 10 internal lines: NCAT equals the
  NGS polygon 60/60.
- Water points: NCAT gives an LDP zone where the land-only NGS polygon gives none.

### 5.3 Rounds 2–4: metre-scale probes

| Test | Result |
|---|---|
| SPCS2022, ±0.3 / 1 / 3 m straddles of 6 more TIGER/LDP lines (36 probes) | NCAT equals TIGER/NGS polygon **36/36**. The boundary is resolved below 0.3 m. |
| SPCS 83, ±0.3 … 20 m across the C/S land line at 8 places (112 probes), plus Gladwin/Midland and the corner at 43.8155 N 85.5629 W (12 probes) | NCAT equals **MGF at every probe**. NCAT **differs from TIGER at 3 places**: Mecosta/Osceola at 43.8154 N 85.5337 W (to at least 10 m), Mason/Oceana at 43.8174 N 86.2564 W (5–10 m), and the 85.5629 W corner (at least 3 m). |
| Same points as the row above, SPCS2022 auto-pick (beta) | NCAT follows **TIGER** (L55W Osceola/Mason side). At 43.8154 N 85.5337 W, 3–10 m inside Osceola County, **NCAT says SPCS 83 South (2113) and SPCS2022 L55W (Wexford)**. Its two answers disagree about which county the point is in. Beta NCAT's SPCS 83 auto-pick agrees with production NCAT. |
| Water: 14 random points where county rule ≠ nearest-land rule | NCAT follows the **county rule 14/14** (Keweenaw split per §2.3). |
| Datum (Jackson/Ingham line) | See §3. The pick is made on the output NATRF2022 coordinate. |

**What this means for anchors.** NCAT can be frozen as truth for points more
than about 20 m from any land line and more than about 500 m from any
Great Lakes water line. Inside those bands NCAT's SPCS 83 answer comes from an
unpublished, MGF-like polygon. Its SPCS2022 answer comes from TIGER. A bundled
dataset will match one of them and not the other near some land lines.

---

## 6. Recommendation (for the lead to decide; not built)

1. **Bundle counties, not zones:** 83 water-extended county polygons, plus a
   county → SPCS 83 zone table transcribed from MCL 54.231, plus a county →
   LDP table from §2.2, plus the Keweenaw rule (Isle Royale at 47.65° N).
   - This represents the legal object directly.
   - It covers Great Lakes water the way NCAT does.
   - It gives "outside Michigan → refuse" for free.
   - It is about 1.2–1.5 MB unsimplified. Do not simplify.
   - The county → zone tables are the single authority for which counties form
     which zone. The polygons are only the county picture.
2. **Which county picture is an owner decision; both have a cost.**
   - **TIGER 2025:** federal and public domain. It is what NGS built the
     SPCS2022 zones from (2.6 cm), and what NCAT uses for SPCS2022. It matches
     NCAT's SPCS 83 water answers. It **disagrees with NCAT's SPCS 83 land line
     by 3–17 m in places**.
   - **MGF V25:** the State of Michigan's framework with the legal lake
     boundary. It matches NCAT's SPCS 83 land line to 0.3 m, but differs from
     NCAT by 100–444 m (C/S) and up to km (N/C) in the water. Its SPCS2022
     lines would differ from NGS's by up to 167 m.
   - A single TIGER picture keeps both systems consistent with each other and
     with NGS's own SPCS2022 design. On the evidence it is the better default.
     The 3–17 m SPCS 83 land discrepancy against NCAT needs disclosure.
3. **Treat the boundary band as a refusal or warning, not a silent pick.** A
   point within a stated distance of any zone line should be flagged. For
   example, 50 m on land and 1 km in water would cover every measured source
   disagreement except the 11.8 km N/C international-line corner. MCL 54.234
   lets the surveyor choose either zone if it is named. An "Auto" that silently
   picks inside the band would put a GIS-picture choice onto a sealed document.
4. **Freeze anchors from NCAT outside the bands** (production for SPCS 83,
   beta form for SPCS2022), with raw captures, the way `ncat_crosscheck.py` was
   built. Keep the band points as documented disagreements, not as anchors.
5. **SPCS2022 data is beta (CC0, "not final")** and belongs on the
   `docs/REFREEZE-NSRS.md` inventory. If HB 5577 is enacted, the SPCS 83 county
   lists leave the statute. Pin the 1988 text as captured here.

## 7. Not verified, stated plainly

- **Whether NGS considers its feature-service polygons definitional.** I found
  no definitional zone-extent file from NGS. The holes suggest it is a display
  product; that is inference.
- **The source of NCAT's SPCS 83 polygon.** It is MGF-like on land and
  TIGER-like in water near the tested lines. The server code is unpublished
  (`SpcUtil` is a stub). Whether the water agreement holds at metre scale was
  not tested; the water probes were 15–200 m from the MGF line.
- **The Keweenaw 47.65° N rule** comes from 3 bisections at about 100 m
  resolution. No NGS text was found. Whether it is exactly 47.65° was not proven.
- **Where the true (legal) county line lies** where MGF and TIGER differ. That
  is a survey question; no GIS source settles it.
- **The datum of NGS's LDP polygons** (NAD83 vs NATRF2022 label). Only their
  numerical identity with TIGER was measured.
- **NOS NGS 5's county tables** were not read in this round.
- **The 6.1 km MGF/TIGER outline Hausdorff** was not localized beyond "lakes or
  international line". The worst N/C water point is 45.772 N, 83.485 W.
- **Large raw files.** `raw/` is about 137 MB: the TIGER zip is 84 MB, the NGS
  2019 zip 17 MB with its extracted `x/` folder, and the NGS polygon JSONs
  6–7 MB each. Decide what to commit; the SHA-256 values are listed above and
  in the hash table printed during recon.

## Files

- Scripts: `load_sources.py`, `analyze.py`, `ldp_detail.py`, `probe_points.py`,
  `probe2_points.py`, `probe3_points.py`, `probe_ncat.py` (stdlib only),
  `probe3_ncat.py` (stdlib only), `classify.py`.
- Results: `work/analysis.json`, `work/ldp_detail.json`, `work/bundle_sizes.json`,
  `work/classify.json`, `work/ncat_83.json`, `work/ncat_22.json`,
  `work/r2_ncat_*.json`, `work/r3_ncat.json`, `work/r3_spcs83_fine_summary.json`,
  `work/r4_ncat.json`.
