# N0 — measure before code: what NGS actually publishes for the modernized NSRS

**Capture date:** 2026-08-28, owner's Windows machine. Every claim carries URL,
bytes, SHA-256. Failed probes are recorded because a refusal documents the
contract. Captured by the N0 discovery agent; the session lead independently
re-ran one probe of each decisive family on 2026-08-28 and reproduced the
results (production `NAVD88→NAPGD2022` refusal verbatim; beta geoid `{}` vs
production −33.085 m; `github.com/noaa-ngs/ncat-lib` present, Java, updated
2026-04-09).

## Verdict summary

| Item | Verdict | Reason |
|---|---|---|
| 1. Beta NCAT frame transformation | **GO (web app only)** | NAD83(2011) ⇄ NATRF2022 converts and round-trips exactly; SPCS2022 output works for OMC, LC1 and TM Michigan zones. No REST API accepts any NATRF2022 token, on either host. |
| 2. GEOID2022 / NAPGD2022 downloads | **GO** | GGXF + `.b` + `.bin`, all published. Static grid at epoch **2020.0** plus a global rate grid; uncertainty and GQS grids included. ~475 MB for Michigan. Interpolation is **bicubic**, not MCX's biquadratic; no NGS reference implementation located. |
| 3. NAVD 88 ↔ NAPGD2022 | **NO-GO** | No grid, no service, no mention anywhere on beta; NCAT's own FAQ puts it in the future tense. The ~0.5 m gap is real and unconverted. |
| 4. Geoid API on beta | **NO-GO** | No GEOID2022 model id on either host; beta's geoid service returns `{}` for every model it accepts. |
| 5. EPP2022 | **GO** | 181-byte CSV downloaded and hashed; frame definition captured. Developer test dataset not yet released. |
| 6. Michigan zone parameters | **GO** | All 19 rows verbatim, digest-verified, with exact `Zone type` / `Proj type` / `Reference frame` spellings. |

**The single most important operational finding:**
`beta.ngs.noaa.gov/api/*` answers `200 OK` with `N/A` and `{}` where
`geodesy.noaa.gov` returns real numbers. **It fails open, not closed.**
Truth-source captures must keep coming from `geodesy.noaa.gov`; anything
capturing anchors from beta's REST API would freeze absences as data.

## Reproduction map

| Script | Covers | Raw output |
|---|---|---|
| `capture_lib.py` | shared fetch/hash/manifest helper | — |
| `capture_ncat_beta.py` | items 1, 3 — REST probe matrix + beta NCAT app driven through its own form | `raw/ncat/`, `raw/ncat_rest_probes_manifest.json` |
| `capture_napgd2022.py` | items 2, 5 — crawls NAPGD2022/NATRF2022/SPCS pages, HEADs 86 downloads, fetches small parameter files | `raw/napgd2022/`, `raw/napgd2022_manifest.json` |
| `capture_ggxf_header.py` | item 2 — HTTP Range read of GEOID2022 GGXF header (256 KiB of a 757 MB file) | `raw/napgd2022/GEOID2022.beta_v0a.ggxf.head256k` |
| `capture_geoid_api.py` | item 4 — enumerates geoid model registry on both hosts | `raw/geoid_api/` |
| `capture_beta_data_check.py` | cross-cutting — is the beta API host carrying grids? | `raw/beta_data_check/` |
| `capture_geoid_delta.py` | sizing — GEOID18 vs SGEOID2022 at NGS's Michigan-window test points | `raw/geoid_delta/` |
| `capture_spcs.py` | item 6 — re-fetches `zoneDefinitions.json` + SPCS pages | `raw/spcs/` |

**Digest caveat for item 1.** Beta NCAT is a JSF/PrimeFaces app; every page
embeds a fresh `jsessionid` and `ViewState`, so **NCAT HTML digests are not
reproducible across fetches** — three fetches of the same URL gave
`4b986cfa…`, `2eb38ae4…`, `129b0562…` at 405,952 / 405,949 / 405,952 bytes.
NCAT digests attest to the saved file only. Every other capture is
digest-stable and was verified by re-fetch where applicable.

---

## 1. Beta NCAT frame transformation — GO, but only through the web app

- **NAD83(2011) → NATRF2022 was successfully performed** for the Michigan
  point; raw response saved.
- **No REST API offers it.** Neither host accepts any NATRF2022 token on
  `/api/ncat/llh`. The beta REST endpoint is the *same legacy service* as
  production (`"nadconVersion": "5.0", "vertconVersion": "3.0"`).
- **SPCS2022 output works**, including the statewide OMC zone and both an LC1
  and a TM Michigan LDP.
- **There is no machine-callable NATRF2022 interface** for MCX to depend on —
  only a server-rendered form. `capture_ncat_beta.py` drives that form as a
  measurement harness, confined to `review/`.

### 1.1 The REST surface refuses every modernized token

Probed at `lat=43.0&lon=-84.5&inDatum=NAD83(2011)`
(`raw/ncat/rest_00.json`…`rest_55.json`), both hosts: `NATRF2022`,
`NATRF2022(2020.00)`, `NATRF2022 epoch 2020.00`, `NATRF2022 2020.00`,
`NATRF2022(2020.0)`, `NA2022`, `natrf2022`, `NATRF`, `MATRF2022`, `CATRF2022`,
`PATRF2022`, `ITRF2020`, `IGS20`, `WGS84` → all
`{"error": "Invalid outputDatum"}`. Controls `NAD83(2011)`, `NAD27`,
`NAD83(NSRS2007)` → 200 OK, converts. `inDatum=NAD83(2011) epoch 2010.00` →
`{"error": "Invalid inputDatum"}` while bare `NAD83(2011)` succeeds — **the
REST vocabulary and the app's dropdown vocabulary are different vocabularies**.

Dead endpoints: `/api/ncat/datums` (404), `/api/ncat/openapi.json` (404),
`/api/ncat/v3/llh` (404), `/api/ncat/spc` and `/api/ncat/xyz` (403), `/api/`
(404), `https://beta.ngs.noaa.gov/web_services/ncat/` (404). `/api/ncat/meta`
is byte-identical on both hosts (3,867 bytes, SHA-256
`2fb8bf2dada9da620cbcdb7c41ca81f9499ef60b951fca3c56696b3ffaf099c5`) and
documents no frame or epoch field. The app's "Web services" tab links to the
**production** reference (23,064 bytes, SHA-256 `342f670b2394744a8ee463da1e30
e2f0992ccc82e7f89d776d7c616da54f9f2f`), whose CONUS frame table reads exactly
`USSD, NAD27, NAD83(1986), NAD83(HARN), NAD83(FBN), NAD83(NSRS2007),
NAD83(2011)`. NATRF2022 is absent.

### 1.2 The app's datum vocabulary

`https://beta.ngs.noaa.gov/NCAT/` reports **Version 3.0**. Single-point tab,
labelled *"Datums (no user-specified epoch)"* — 8 entries in order:
`NATRF2022 epoch 2020.00`, `NAD83(2011) epoch 2010.00`, `NAD83(NSRS2007)`,
`NAD83(FBN)`, `NAD83(HARN)`, `NAD83(1986)`, `NAD27`, `USSD`.

Multipoint tab — 72 entries with user-specifiable epoch (`epochx` default
`2020.00`, `epochy`), including the full ITRF/IGS/IGB series and all four
plate frames. **Data defect worth pinning:** the multipoint list contains
`NATRF2022`, `NATRF2022 epoch 2020.00`, **and** a third entry
`' NATRF2022 epoch 2020.00'` with a **leading space** in its value. Any code
matching these must not assume they are trimmed.

### 1.3 The successful transformation — 43.0000000000 N, −84.5000000000 W

`NAD83(2011) epoch 2010.00` → `NATRF2022 epoch 2020.00`
(`raw/ncat/nad83_2011_to_natrf2022_llh.html`, 450,089 bytes, SHA-256
`0d67839c396de0f10f361f3d4261dbe4dc313841c4f591b3670bf941d64aa739`):

| | Input | Output | Change ± uncertainty |
|---|---|---|---|
| Latitude | 43.0000000000 | **43.0000084850** | +0.03055″ ±0.000657″ → **+0.943 m ±0.0203 m** |
| Longitude | −84.5000000000 | **−84.5000097815** | −0.03521″ ±0.000658″ → **−0.798 m ±0.0149 m** |
| Input Epoch / Output Epoch | **2020.00** | **2020.00** | |

**Epoch contradiction, unresolved — do not guess:** the input datum is
labelled "NAD83(2011) **epoch 2010.00**" yet the result reports **Input Epoch
2020.00**; the single-point tab offers no epoch control. Resolve at H3 from
the multipoint surface (`epochx`/`epochy`) and/or the `noaa-ngs/ncat-lib`
source, never by assumption.

**Reverse direction** (`raw/ncat/natrf2022_to_nad83_2011_llh.html`, SHA-256
`2f9e5e17da5581da533b96be3350ce0138787ba8e41ca92633a6c1ffbb81d705`) returns
**exactly the negation, to every printed digit**, with identical σ.

**Ellipsoid height changes by over a metre across the frames**: 200.000 →
**198.885** m, change −1.115 m ±0.020 m
(`raw/ncat/nad83_2011_to_natrf2022_eht200.html`, SHA-256
`0f1feacb3e6a108c6c53fa9b866df28f54f88933e178108eb96c4429c5c85a70`). That is
load-bearing for a combined factor.

### 1.4 SPCS2022 output — three Michigan zones plus auto-pick

All from the NATRF2022 output coordinate. **NCAT reports metres and
international feet only — `usft` is `N/A` for every SPCS2022 zone.** (The
NAD83(2011) run auto-picked legacy `MI S-2113` and did print usft.)

| Zone | Proj | Northing (m) | Easting (m) | Scale factor | Convergence | Raw (SHA-256 prefix) |
|---|---|---|---|---|---|---|
| auto-pick → `MI L45G-261008` | LC1 | 251,023.812 | 1,462,701.575 | 1.000024078 | +00° 26′ 29.87″ | `0d67839c` |
| `260001-MI (Statewide)` | OMC | 540,938.022 | 1,646,301.296 | 0.999802177 | +01° 02′ 23.50″ | `dd0f17d0` |
| `261007-MI L41Z` (Kalamazoo) | LC1 | 176,814.019 | 1,427,282.306 | 1.000147529 | +00° 46′ 15.54″ | `1c7dc26a` |
| `261002-MI L15D` (Detroit) | TM | 311,876.526 | 385,215.540 | 1.000173019 | −00° 55′ 14.87″ | `03dc1e85` |

**Pure-projection anchor** (input AND output `NATRF2022 epoch 2020.00`, zone
261008, no transformation in the way —
`raw/ncat/natrf2022_to_natrf2022_spc_261008.html`, SHA-256
`6bddfa31ff32a3643d0f48624b87e1573e9a59799d406f987e16a3e988cd5930`):
N **251,022.875 m**, E **1,462,702.380 m**, scale **1.000024077**, convergence
+00° 26′ 29.89″. This is the shape of anchor an MCX projection engine
reproduces directly. It differs from the transformed run by +0.937 m N /
−0.805 m E, consistent with the frame shift.

---

## 2. GEOID2022 / NAPGD2022 downloads — GO, fully published

Beta model is **`beta_v0a`**, dated 4/27/2026 (change log SHA-256
`881362425a184fbf06f529ed651d8bd4a0b16520e45c82cbc7ab6a4f29534be6`).

### Formats
From `https://beta.ngs.noaa.gov/NAPGD2022/download.html` (SHA-256
`e870bd57993860a78db7ef3c39ab6405e11cd9376f5a907bc0dfa4e6f5bee86a`):
**GGXF** (one NetCDF-4 file per model, all regional grids inside), **`.bin`**
(GEOID18's marker-free layout) and **`.b`** (VERTCON's Fortran-record layout)
— the `.b`/`.bin` difference is constant: 4 × 2 × rows + 8 bytes of markers —
plus `.gfc` spherical harmonics. **NGS publishes the legacy binary formats,
so no GGXF-to-binary derivation tool is needed** (the plan's N2 fallback is
moot; the plan said "if V0 finds NGS also ships a legacy binary, use it
directly and the derivation package is deleted" — it does).

### Files Michigan needs (HEAD, 2026-08-28)
`SGEOID2022.NA.N.beta_v0a.bin` (233,344,848 B) + `DGEOID2022.GL.Ndot.beta_v0a
.bin` (4,155,888 B), plus σ companions `SGEOID2022.NA.Nsigma` (233 MB) and
`DGEOID2022.GL.Ndotsigma` (4 MB) if uncertainty is reported — **≈ 475 MB**
against today's 2.4 MB GEOID18 tile. The full GGXF is 757,778,288 B. NA grid
is 1′, **5,401 × 10,801** nodes, lat 0–90, lon 170–350 E — one grid covers
all of Michigan, no seam.

### Time dependence — the geoid is now epoch-bearing
Developer guide (SHA-256
`6ab8aceac75b109c89d2cb27c4f4fbac05793979878c3005c76c2b485d3358d4`): "The
static grids … represent the geopotential field at the **2020.0 (January 1st,
2020) epoch**." The combination rule is embedded verbatim in the GGXF:

```
GEOID  = SGEOID + DGEOID*(mjdn-58849)/365.25
sigmaN = sqrt(geoidHeightUncertainty**2 + (delta_t*geoidVelocityUncertainty)**2)
```

MJD 58849 = 2020-01-01; Julian years of exactly 365.25 days. **No per-epoch
static grids exist** — one static grid + one rate grid, user computes the
epoch. Michigan-window rates: +0.21 to +0.27 mm/yr.

### Interpolation — the documentation contradicts itself; the file wins
Guide prose says **bicubic 4×4** (Numerical Recipes, Press et al. 2007; linear
edge extrapolation; **bilinear for σ grids and DEMs**); the guide's stale
example prints `interpolationMethod: biquadratic`; the change log (4/27/2026)
says the recommendation CHANGED from biquadratic to bicubic; and the shipped
GGXF header declares `bicubic` (Range read, slice SHA-256
`890d599f515189a87053b0fc795ced5a00c8fbac616e4aef081db04d62af7133`).
**Neither is MCX's biquadratic nearest-node INTG stencil**, and — unlike
`Vertcon.java` and `intg.f` — **no NGS source implementing the bicubic was
located**, so the replicate-NOAA-exactly standard (DESIGN.md #36) currently
has no reference implementation for GEOID2022.

The GGXF header also declares the grid's horizontal reference:
`sourceCrsWkt: GEOGCRS["ITRF2020" …]` — **ITRF2020, not NATRF2022** — and
`VERTCRS["NAPGD2022"]`.

### Anchors are thin
`NAPGD2022TestCases.beta_v0a.csv`, 10,393 bytes, SHA-256
`d475435f9223fc5c336326c50f80f73dca8cc6d0aff826379a881e51438e68b3` — 87
points, input coordinates ITRF2020, only **Detroit** (42.33687333,
−83.04910534) and **Chicago** in a Michigan-sized window. There is no geoid
API for GEOID2022 anywhere (item 4), so no service can generate more anchors.

### Sizing (recorded, NOT a conversion)
GEOID18 vs SGEOID2022@2020.0: Detroit −34.5370 vs −35.1126 (**−0.5756 m**),
Chicago −33.6000 vs −34.0343 (**−0.4343 m**). GEOID18 is hybrid (fitted to
NAVD 88); SGEOID2022 is gravimetric (defines NAPGD2022): the gap is
essentially the NAVD 88 → NAPGD2022 datum offset, roughly half a metre in
Michigan. It **must not be used as a conversion** — item 3 finds no published
transformation.

---

## 3. NAVD 88 ↔ NAPGD2022 — NO-GO. No grid and no service exists.

Checked four ways; every one negative. Re-verified first-hand by the session
lead on production: `{"error": "Invalid output vertical Datum"}`.

1. **REST refuses every token** on both hosts (`NAPGD2022`, `NAPGD2022(2022)`,
   `GEOID2022`, `NAPGD`, `napgd2022`, and `NGVD29→NAPGD2022`); controls
   `NGVD29↔NAVD88` accepted. The production API reference's CONUS
   geopotential-datum table reads exactly `NGVD29, NAVD88`.
2. **The beta web app has no geopotential-datum control at all**; driving its
   orthometric height path drops the height **silently** ("Orthometric Height
   (): Not given") while the ellipsoid path carries it through. The app FAQ
   redirects users to production for vertical datums and answers the
   modernized-datum question in the **future tense**: "Yes, it will. Please
   keep an eye out…"
3. **Zero mentions** of NAVD 88/NGVD 29/VERTCON on any captured beta page;
   the sitemap's 30 URLs contain no vertical transformation product; the
   "Interactive Computation" link is commented out and `alpha.ngs.noaa.gov`
   does not resolve.
4. **Baseline check + hazard**: production NGVD29→NAVD88 at 43.0/−84.5
   returns 199.860 ± 0.001 (MCX's own #22 anchor, reproduced); beta returns
   `N/A` for the same query, and beta's geoid endpoint returns `{}` where
   production returns −33.085 ± 0.031. **Beta's REST API fails open.**

---

## 4. Geoid API — NO-GO for GEOID2022 on either host

Model ids 0–25 plus name tokens enumerated on both hosts (62 responses,
`raw/geoid_api/`). Production's registry stops at **14 = GEOID18** (13 =
GEOID12B, matching MCX's captures). No GEOID2022 id exists. Beta accepts and
refuses the same ids with the same strings but returns `{}` for every
accepted id.

---

## 5. EPP2022 — downloaded

`https://beta.ngs.noaa.gov/NATRF2022/epp2022-beta-values.csv`, **181 bytes**,
SHA-256 `63d80d642caf2bce1512587e444e3837b2451e7052222f68dfe8a7736c143d52`.
Verbatim:

```
Plate,Omega X (mas/yr),Omega Y (mas/yr),Omega Z (mas/yr)
NATRF2022,0.046,-0.704,-0.047
CATRF2022,-0.056,-0.957,0.589
PATRF2022,-0.409,1.063,-2.188
MATRF2022,-8.089,5.937,2.159
```

Frame definition (page SHA-256
`1904cdda9bf7520f7b57d5bc887caca3ebee256e034aeafcbbc712c7529764b4`): "All of
the frames are identical to ITRF2020 at epoch 2020.0 … each reference frame
rotates with the stable part of their tectonic plate"; rotation positive
counterclockwise, right-hand rule, `K = π/(648 × 10⁶)`, `Δt = t − 2020.0`;
authority NOAA TR NOS NGS 63 (17,338,722 bytes, HEAD only, not read). The
EPP algebra on the page is rendered as images and was not captured as text.
"A test dataset for software developers will be released publically on GitHub
after completing internal review" — **not yet released**. The NCAT engine is
open source at `https://github.com/noaa-ngs/ncat-lib` (verified present,
Java, updated 2026-04-09) with a runnable offline jar — the reference-
implementation path for the transformation math.

---

## 6. Michigan SPCS2022 zone parameters — all 19 rows, verbatim

Source `zoneDefinitions.json`, 632,927 bytes, SHA-256
`f222dac669503c8e25eb41d477bbb129b813b894b43e7d012effb9dc00bbc06a`,
`Last-Modified: Mon, 01 Jun 2026 20:55:42 GMT`, re-fetched digest-identical.
953 zones nationally; the 19 Michigan rows are extracted verbatim to
`raw/spcs/michigan_zones.json` (SHA-256
`8db63d1fe83ebc74700f0d2040da12a18c08a55c0dbafbec8aafe738e6142edb`).

Column names exactly: `Zone code`, `Zone abrv`, `Zone name`, `Zone type`,
`Proj type`, `Origin latitude`, `Origin longitude east`, `Origin longitude
west`, `Projection origin scale`, `Skew azimuth (deg)`, `False northing (m)`,
`False easting (m)`, `False northing (ift)`, `False easting (ift)`,
`Design by`, `Reference frame`. **Every value is a string**, thousands
separators and degree symbols included.

| Code | Abrv | Name | Proj | Origin lat | Origin lon W | Scale | Skew | FN (m) | FE (m) |
|---|---|---|---|---|---|---|---|---|---|
| 260001 | MI | Michigan | OMC | 45°00'N | 86°00'W | 0.999800 | -26 | 762,000 | 1,524,000 |
| 261001 | MI_L11A | Michigan Ann Arbor | TM | 41°18'N | 84°06'W | 1.000022 | | 0 | 381,000 |
| 261002 | MI_L15D | Michigan Detroit | TM | 40°12'N | 83°09'W | 1.000024 | | 0 | 495,300 |
| 261003 | MI_L21F | Michigan Flint | LC1 | 42°54'N | 83°24'W | 1.000026 | | 76,200 | 685,800 |
| 261004 | MI_L25S | Michigan Saginaw | LC1 | 43°36'N | 83°39'W | 1.000012 | | 228,600 | 723,900 |
| 261005 | MI_L31R | Michigan Roscommon | LC1 | 44°15'N | 84°09'W | 1.000029 | | 76,200 | 990,600 |
| 261006 | MI_L35T | Michigan Thunder Bay | LC1 | 44°51'N | 84°03'W | 1.000031 | | 190,500 | 1,028,700 |
| 261007 | MI_L41Z | Michigan Kalamazoo | LC1 | 42°06'N | 85°39'W | 1.000024 | | 76,200 | 1,333,500 |
| 261008 | MI_L45G | Michigan Grand Rapids | LC1 | 42°48'N | 85°09'W | 1.000018 | | 228,600 | 1,409,700 |
| 261009 | MI_L51N | Michigan Newaygo | LC1 | 43°27'N | 85°24'W | 1.000025 | | 76,200 | 1,638,300 |
| 261010 | MI_L55W | Michigan Wexford | LC1 | 44°09'N | 85°33'W | 1.000034 | | 190,500 | 1,638,300 |
| 261011 | MI_L61L | Michigan Leelanau | LC1 | 44°54'N | 85°27'W | 1.000025 | | 76,200 | 1,905,000 |
| 261012 | MI_L65C | Michigan Cheboygan | LC1 | 45°27'N | 84°27'W | 1.000025 | | 190,500 | 2,019,300 |
| 261013 | MI_U11M | Michigan Mackinac | LC1 | 46°12'N | 84°51'W | 1.000011 | | 76,200 | 381,000 |
| 261014 | MI_U21E | Michigan Escanaba | TM | 45°09'N | 86°36'W | 1.000012 | | 0 | 685,800 |
| 261015 | MI_U31Q | Michigan Marquette | TM | 44°42'N | 87°36'W | 1.000038 | | 0 | 952,500 |
| 261016 | MI_U41H | Michigan Houghton | TM | 45°30'N | 88°24'W | 1.000042 | | 0 | 1,295,400 |
| 261017 | MI_U51B | Michigan Bessemer | LC1 | 46°42'N | 89°42'W | 1.000036 | | 114,300 | 1,600,200 |
| 261018 | MI_U61K | Michigan Isle Royale | LC1 | 48°00'N | 88°51'W | 1.000026 | | 76,200 | 1,866,900 |

(ift false origins are in `michigan_zones.json`; the statewide zone is
2,500,000 / 5,000,000 ift.)

Exact spellings: `Zone type` ∈ {`Statewide`, `Multizone complete`};
`Proj type` ∈ {`OMC`, `LC1`, `TM`}; `Reference frame` = `NATRF2022` bare, all
nineteen; `Design by` = `NGS` for 260001, `State` for the LDPs. The zone-
definitions page (SHA-256 `842524f9803025c7242360ff0253a9c8367f8d22fb9e356c5f
3de9102b83aeca`) states: "Projection type abbreviations: LC1 (Lambert
Conformal Conic, one parallel); TM (Transverse Mercator); OMC (Hotine Oblique
Mercator, center)" and "**All parameters are exact values**" (except NC's ift
false origins). **Abbreviation discrepancy to handle:** the JSON writes
`MI_L45G` (underscore); NCAT writes `MI L45G` (space); NGS sanctions both.
Origin longitudes are given twice (E and W) and are consistent. False origins
are metres and international feet only — no usft column, matching NCAT's
`N/A` usft for every SPCS2022 zone.

**None of the three Lambert zones MCX implements today survives into
SPCS2022.**

---

## What could not be determined

1. Whether the modernized NSRS will ever expose a REST API for NATRF2022.
2. How epochs are meant to be supplied for a single point (the app's own
   labels contradict its results; resolve from the multipoint surface or
   `ncat-lib` source at H3).
3. The algebraic form of the EPP2022 rotation (page renders it as images;
   NOAA TR NOS NGS 63 not yet read).
4. Any σ behaviour of the NAPGD2022 uncertainty grids (233 MB σ grid not
   downloaded).
5. Whether NGS's bicubic is bit-reproducible — no reference implementation
   located.
6. When any of this leaves beta.
