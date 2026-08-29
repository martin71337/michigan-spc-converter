# H1 — a frozen SPCS2022 anchor lattice for Michigan, from beta NCAT

**Capture date: 2026-08-28**, owner's Windows machine, where NOAA is reachable.
Source: `https://beta.ngs.noaa.gov/NCAT/` (beta NCAT **Version 3.0**), driven
through its own JSF/PrimeFaces form, the approach inherited from
`review/nsrs-n0/capture_ncat_beta.py`. There is still no REST surface that
accepts any NATRF2022 token (N0 §1.1); the form is the only interface.

Nothing here is production code and nothing in `michspc/` may import it.

## Counts

| Family | Captured | Refused/failed |
|---|---|---|
| A. Statewide OMC zone 260001, pure projection | **9** | 0 |
| B. The 18 LDP zones × 3 points, pure projection | **54** | 0 |
| C. Frame transformation, NAD83(2011)→NATRF2022, no zone forced | **12** | 0 |
| C. Reverse, NATRF2022→NAD83(2011) | **3** | 0 |
| D. Inverse — SPC northing/easting/zone as INPUT | **5** | 0 |
| **Total anchors** | **83** | **0** |

HTTP requests: **84** in the lattice session, **21** in the inverse session,
plus the discovery and probe requests listed under "Probes" below. Throttled to
one request per second throughout.

*Pure projection* means input datum **and** output datum are both
`NATRF2022 epoch 2020.00`, so no frame transformation stands between the
geodetic position and the grid coordinate. That is the shape an MCX projection
engine reproduces directly; the N0 run `natrf2022_to_natrf2022_spc_261008.html`
proved it works.

## Files

| Path | What |
|---|---|
| `anchors.json` | the machine-readable summary — every printed value, verbatim |
| `raw/manifest.json` | the lattice session: URL, POST fields (session tokens redacted), bytes, SHA-256, timestamp, per request |
| `raw/inverse_manifest.json` | the inverse session, same shape |
| `raw/inv_probe_manifest.json`, `raw/probe_field_precedence_manifest.json` | the two discovery families |
| `raw/z260001_p1..9.html` | family A |
| `raw/z2610NN_p1..3.html` | family B, `p1` = the zone origin |
| `raw/frame_p01..12.html`, `raw/framerev_p01..03.html` | family C |
| `raw/inv3_pN.html` + `inv3_pN_{1north,2east,3zone}.xml` | family D, four requests per point |
| `h1_lib.py` | the session driver, extraction and verification |
| `capture_h1_anchors.py` | families A, B, C |
| `capture_h1_inverse.py` | family D |
| `probe_inverse.py` | the inverse capability probe |
| `check_anchors.py` | the four cross-checks below |

Digests, 2026-08-28:

```
anchors.json                          76d2b61e57d2b9ddeb5466bcc3add92907f687efe8221cd0914c595707390a2d
raw/manifest.json                     2d62ad404188e267975e76ca94ca734d2dfd98b9c6fc70b37f047e1a957f5e37
raw/inverse_manifest.json             27cbf0213afb3974b77e34dea14f3fb8b7f0075571ff56daece3d768978b232f
```

`check_anchors.py` re-reads every anchor's raw file and confirms its SHA-256
still matches what the manifest recorded. **The N0 digest caveat still holds:**
beta NCAT embeds a fresh `jsessionid` and `ViewState` in every page, so these
digests attest to the saved files and are **not** reproducible by re-fetching.

`raw/` is about **53 MB** — beta NCAT returns the whole re-rendered document
(434–718 KB) for every submit. Whether that belongs in the repository as-is is
the session lead's call.

## Values: exactly as printed

Every value in `anchors.json` is the string beta NCAT printed, with two
documented exceptions:

1. the unit token (`m`, `ift`, `usft`) is split off into the field name, so
   `"251022.875 m"` becomes `northing_m: "251022.875"`; and
2. a thousands separator would be stripped, and each point records
   `thousands_stripped`. **No separator was observed in any captured value** —
   `thousands_stripped` is `false` on all 63 projection anchors.

`usft` is `N/A` for every SPCS2022 zone, on all 63 anchors, confirming N0 §1.4
and matching `zoneDefinitions.json`, which publishes false origins in metres and
international feet only. `Combined factor` is `N/A` and `Distortion` is
`+N/A  ppm` on every anchor — no height was supplied.

## Self-identification

A response was parsed for numbers only if it named what was asked for. Every
run checks:

- a result block is present;
- `Reference Frame` in **and** out equal the datum tokens requested;
- NCAT's echo of the input latitude and longitude equals what was sent;
- for a zone-forced run, the zone panel names the forced zone code.

A response failing any of these is recorded as a failure and never parsed.
**No response failed.** The inverse runs add a fourth check — the response must
echo back the northing and easting that were sent — which is what caught the
discarded first attempt described below.

## Cross-checks (`check_anchors.py`, all clean)

0. **All 83 anchors' raw response files are present and still hash to the
   SHA-256 the manifest recorded.**
1. **19 origin points reproduce the published zone parameters exactly.** Each
   LDP origin, and the statewide projection center, returns *exactly* the
   published false northing, false easting and origin scale factor, with zero
   convergence. The published values come from `zoneDefinitions.json` by way of
   N0 §6 — a different source from the NCAT app — so this is NCAT's projection
   agreeing with NGS's own parameter file, not with itself. The statewide center
   also returns the published international-foot false origin exactly:
   2,500,000.000 / 5,000,000.000 ift.
2. **Inverse round-trip: worst 5.0e-09 degrees (~0.56 mm) over 5 points**,
   which is the rounding of the 3-decimal metre northing fed back in.
3. **The reverse frame runs are the exact negation of the forward runs**, to
   every printed digit, at all 3 paired points. N0 observed this at one point;
   it now holds at three.

An independent consistency check falls out for free: `frame_p04` is the N0 point
(43.0, −84.5) and reproduces N0 §1.3 to every digit — output
43.0000084850 / −84.5000097815, +0.943 m ±0.0203 m and −0.798 m ±0.0149 m.

## A. Statewide OMC zone 260001 — `260001-MI (Statewide)`

Deliberately asymmetric about the 45°00′N / 86°00′W center: these points are
chosen to discriminate the Hotine variant and the sign of the −26° skew, which
a symmetric lattice cannot do.

| Lat | Lon | Northing (m) | Easting (m) | Northing (ift) | Scale factor | Convergence |
|---|---|---|---|---|---|---|
| 42.100000 | -83.200000 | 443768.217 | 1755596.782 | 1455932.472 | 0.999858230 | +01° 54′ 40.49″ |
| 41.900000 | -86.600000 | 417769.740 | 1474269.524 | 1370635.628 | 1.000270716 | -00° 22′ 23.36″ |
| 43.600000 | -84.200000 | 608056.647 | 1669305.544 | 1994936.507 | 0.999849004 | +01° 14′ 53.92″ |
| 44.800000 | -87.400000 | 740734.526 | 1413252.847 | 2430231.383 | 0.999945690 | -00° 59′ 25.81″ |
| 45.900000 | -84.700000 | 862829.994 | 1624868.041 | 2830807.068 | 1.000023585 | +00° 55′ 51.20″ |
| 46.500000 | -87.600000 | 929914.111 | 1401203.127 | 3050899.316 | 0.999816572 | -01° 09′ 05.48″ |
| 47.100000 | -88.600000 | 998601.613 | 1326671.208 | 3276252.012 | 0.999866553 | -01° 53′ 16.29″ |
| 48.100000 | -88.550000 | 1109582.833 | 1334062.199 | 3640363.625 | 0.999803779 | -01° 51′ 25.87″ |
| 45.000000 | -86.000000 | 762000.000 | 1524000.000 | 2500000.000 | 0.999800000 | -00° 00′ 00.00″ |

Eastings in international feet are in `anchors.json`; the table shows the
northing in both units to keep it readable.

## B. The 18 LDP zones

Three points per zone — the zone origin (`p1`), origin +(0.15°, 0.25°) (`p2`)
and origin −(0.15°, 0.25°) (`p3`), zone forced each time. Origin latitudes and
longitudes were converted from the DMS strings in N0 §6 and are listed in
`capture_h1_anchors.py` with the DMS beside each one.

All 54 are in `anchors.json`. Two things worth stating here:

- **Four zone origins lie outside Michigan** — 261002 Detroit at 40°12′N is in
  Ohio, and 261014 / 261015 / 261016 are over Lake Michigan or in Wisconsin.
  They are grid origins, not places. NCAT projected all of them without
  complaint, which is the correct behaviour for a projection but means the
  anchors at those points are not field-checkable.
- **A symmetric pair of geodetic offsets is not symmetric in the projected
  plane, and the anchors capture that.** ±0.15° of latitude about the 261003
  origin gives +16,694.540 m and −16,633.454 m of northing — the two do not sum
  to zero but to **+61.086 m**. The same asymmetry appears in every zone
  (261002 +60.383 m, 261007 +60.935 m, 261014 +61.257 m). The scale factors of
  the two offset points also differ, in the ninth decimal (261003:
  1.000029418 against 1.000029412). Any engine reproducing these must reproduce
  the asymmetry, not average it away.

## C. Frame transformation

`NAD83(2011) epoch 2010.00` → `NATRF2022 epoch 2020.00`, no zone forced. NCAT
auto-picks an SPCS2022 zone for the output; that auto-pick is recorded in
`anchors.json` as `auto_spc_*` and is not part of the frame anchor.

| In lat | In lon | Out lat | Out lon | Δlat ± σ | Δlon ± σ |
|---|---|---|---|---|---|
| 41.800000 | -83.500000 | 41.8000083785 | -83.5000091465 | 0.03016″ ±0.000650″ (0.931 m ±0.0200 m) | -0.03293″ ±0.000651″ (-0.760 m ±0.0150 m) |
| 42.300000 | -83.100000 | 42.3000086001 | -83.1000091723 | 0.03096″ ±0.000670″ (0.955 m ±0.0207 m) | -0.03302″ ±0.000667″ (-0.756 m ±0.0153 m) |
| 42.300000 | -86.200000 | 42.3000081805 | -86.2000100882 | 0.02945″ ±0.000671″ (0.909 m ±0.0207 m) | -0.03632″ ±0.000665″ (-0.832 m ±0.0152 m) |
| 43.000000 | -84.500000 | 43.0000084850 | -84.5000097815 | 0.03055″ ±0.000657″ (0.943 m ±0.0203 m) | -0.03521″ ±0.000658″ (-0.798 m ±0.0149 m) |
| 43.800000 | -86.400000 | 43.8000088707 | -86.4000119439 | 0.03193″ ±0.000700″ (0.986 m ±0.0216 m) | -0.04300″ ±0.000826″ (-0.961 m ±0.0185 m) |
| 44.300000 | -84.700000 | 44.3000086056 | -84.7000102166 | 0.03098″ ±0.000648″ (0.956 m ±0.0200 m) | -0.03678″ ±0.000650″ (-0.815 m ±0.0144 m) |
| 45.100000 | -83.500000 | 45.1000089100 | -83.5000100071 | 0.03208″ ±0.000652″ (0.990 m ±0.0201 m) | -0.03603″ ±0.000660″ (-0.788 m ±0.0144 m) |
| 45.800000 | -84.700000 | 45.8000088046 | -84.7000105885 | 0.03170″ ±0.000656″ (0.979 m ±0.0203 m) | -0.03812″ ±0.000679″ (-0.823 m ±0.0147 m) |
| 46.300000 | -85.500000 | 46.3000087631 | -85.5000109414 | 0.03155″ ±0.000649″ (0.974 m ±0.0200 m) | -0.03939″ ±0.000648″ (-0.843 m ±0.0139 m) |
| 46.600000 | -87.400000 | 46.6000085741 | -87.4000116056 | 0.03087″ ±0.000648″ (0.953 m ±0.0200 m) | -0.04178″ ±0.000656″ (-0.889 m ±0.0140 m) |
| 47.200000 | -88.500000 | 47.2000084744 | -88.5000122141 | 0.03051″ ±0.000648″ (0.942 m ±0.0200 m) | -0.04397″ ±0.000651″ (-0.925 m ±0.0137 m) |
| 48.100000 | -88.600000 | 48.1000086310 | -88.6000124563 | 0.03107″ ±0.000649″ (0.960 m ±0.0200 m) | -0.04484″ ±0.000651″ (-0.928 m ±0.0135 m) |

The metre figures in parentheses are NCAT's own, and NCAT marks them on screen
as "Approximate value to aid interpretation and not an actual distance."

Reverse, `NATRF2022 epoch 2020.00` → `NAD83(2011) epoch 2010.00`:

| In lat | In lon | Out lat | Out lon |
|---|---|---|---|
| 43.000000 | -84.500000 | 42.9999915150 | -84.4999902185 |
| 42.300000 | -83.100000 | 42.2999913999 | -83.0999908277 |
| 47.200000 | -88.500000 | 47.1999915256 | -88.4999877859 |

**The epoch contradiction recorded at N0 §1.3 is unchanged and still
unresolved.** The input datum is labelled "epoch 2010.00" and every result
reports Input Epoch **2020.00** and Output Epoch **2020.00**. Do not guess what
that means; it is still an H3 question for the multipoint surface or the
`noaa-ngs/ncat-lib` source.

## D. Inverse — the answer is YES, with two traps

**Beta NCAT does accept SPC (northing / easting / zone) as INPUT.** The
`tv1:f1:proj1` control offers `llh | spc | utm | usng`; choosing `spc` builds an
input panel with `northing_input`, `easting_input`, `units_input` (`m | ift |
usft`), `spcsy` (`spcs2022 | spc83 | spc27`, default `spcs2022`),
`zonelist3_input` (the input zone, 955 options) and `zonelistx2_input` (the
output zone, labelled optional).

Five inverse anchors, input and output datum both `NATRF2022 epoch 2020.00`,
units metres, taken from five different zones across all three projection types:

| Raw | Zone | N (m) | E (m) | Returned lat | Returned lon | Forward input was |
|---|---|---|---|---|---|---|
| `inv3_p1.html` | 260001 OMC | 762000.000 | 1524000.000 | 45.0000000000 | -86.0000000000 | 45.000000 / -86.000000 |
| `inv3_p2.html` | 261007 LC1 | 76200.000 | 1333500.000 | 42.1000000000 | -85.6500000000 | 42.100000 / -85.650000 |
| `inv3_p3.html` | 261002 TM | 16686.390 | 516539.589 | 40.3500000030 | -82.9000000050 | 40.350000 / -82.900000 |
| `inv3_p4.html` | 261013 LC1 | 76200.000 | 381000.000 | 46.2000000000 | -84.8500000000 | 46.200000 / -84.850000 |
| `inv3_p5.html` | 261018 LC1 | 59551.554 | 1848189.127 | 47.8500000031 | -89.1000000004 | 47.850000 / -89.100000 |

So the inverse is carried by NCAT's own anchors, not only by our round-trip
closure. Two traps, both found by probe, both recorded because either one
silently produces a plausible number that is not the answer to the question
asked:

1. **`zonelistx2_input` is not optional as a FIELD.** The control is labelled
   "Output SPC zone (optional)". Submitting from SPC-input mode without the
   field present makes the app return its "The page that you are attempting to
   access has expired or an error occurred" page — and the session's view is
   then reset, so the *next* submit succeeds against default values.
   `raw/probe7_x2blank.html` (throws) beside `raw/probe7_x2same.html` and
   `raw/probe7_x2sel.html` (do not).
2. **The northing and easting only reach the model through their own blur
   AJAX**, and that must fire *before* the zone `valueChange`. Posting them on
   the submit alone leaves the app converting whatever latitude and longitude
   the bean already holds and projecting *that* into the chosen zone.
   `raw/probe7_x2same.html` is the worst case on record: HTTP 200, the correct
   zone named, `Northing 19,261,562.580 m`, `Scale factor 1.276527136`, and
   `Convergence -18° 35′ 553.55″` — from a latitude of 0.

The working sequence, five requests per point, is
`proj1=spc` (once per session) → `blur northing` → `blur easting` →
`valueChange zonelist3` → `submit` with `zonelistx2_input` supplied. It is in
`capture_h1_inverse.py` and recorded in `anchors.json` under
`inverse_probe.required_request_sequence`.

## Failures and things thrown away

**Zero failures in the delivered anchor set.** Two things were produced and
discarded, and both are recorded rather than quietly dropped:

- **A first inverse attempt, five points, all wrong.** It ran at the tail of the
  84-request lattice session using the naive single-submit shape. Three points
  got the expired/error page; two returned HTTP 200 from a reset form and
  converted northing 0.0 / easting 0.0 into latitude 0.0000000000. **The
  original verification did not catch this** — it checked the datum pair, which
  was correct, and not the coordinate echo. That is exactly the class of defect
  this project cares about, so the echo check was added and those five bodies
  were deleted. The five entries remain in `raw/manifest.json` with their bytes
  and digests, annotated `saved_body_deleted`, and both behaviours survive
  reproducibly in `raw/probe7_x2blank.html` and `raw/probe7_x2same.html`.
- **One transient network failure**, `getaddrinfo failed`, on a single request
  during that discarded attempt. Recorded, not retried in a loop.

## Probes

Two discovery families are reproducible from committed scripts:

- `probe_inverse.py` → `raw/inv_probe_proj1_spc.xml` — the inverse capability
  answer and the SPC panel's field names.
- `raw/probe_field_precedence_*.html` — **which field actually drives the input
  position.** The form carries a decimal-degree box (`lat_input`), a hidden
  PrimeFaces companion (`lat_hinput`) and a DMS box (`latd`). Sending a
  deliberately mismatched DMS value changes nothing; sending a mismatched
  `lat_hinput` moves the result. **`_hinput` wins and `latd` is ignored on
  submit.** The harness sets `_input` and `_hinput` identically for every
  anchor, so the captured positions are the ones intended either way.

`raw/probe2_*` through `raw/probe8_*` are the interactive discovery captures
that isolated the two inverse traps. They are retained as evidence but were
made by ad-hoc commands, not by a committed script, and are not reproducible
the way the rest of this directory is.

## Surprises in NCAT's output format

- The statewide projection center prints its convergence as **`-00° 00′ 00.00″`**
  — a signed zero. Any parser comparing convergence strings must not assume the
  sign character is meaningful at zero.
- Convergence seconds can exceed 60. `raw/probe7_x2same.html` prints
  `-18° 35′ 553.55″`. That was an out-of-domain input, but it shows the
  formatter does not normalise.
- Longitude is echoed three ways in one cell — `E275° 30′ 0.00000″`, then
  `W0843000.00000`, then `-84.5000000000`: **east-longitude DMS, west-longitude
  packed, and negative-west decimal, all at once.** The extractor takes the
  decimal line. This is worth remembering given DESIGN.md #29's standing
  longitude-convention hazard.
- The result page ships a "Customize Export" column list naming 59 export
  fields (`SPCNorth(m)`, `SPCSF`, `SPCConvergence`, `Lat_Sigma(m)` …). Nothing
  was captured through it; the anchors come from the rendered panels.

## What these anchors do NOT prove

Read this before any of the numbers above are used to accept or reject a
computation.

1. **They are beta NCAT's implementation on 2026-08-28, not ground truth.**
   SPCS2022, NATRF2022 and this tool are all pre-release. A beta service is
   entitled to be wrong, and N0 §"the single most important operational
   finding" already recorded that `beta.ngs.noaa.gov` **fails open** — its REST
   API answers `200 OK` with `N/A` and `{}` where production returns real
   numbers. **These anchors must be re-frozen against NGS's official release
   before anything ships on them**, and the difference must be measured, not
   assumed to be zero.
2. **The projection anchors and the frame anchors are different kinds of
   claim.** The 63 pure-projection anchors are a projection reproducing
   published, exact zone parameters — 19 of them land on the published false
   origins to the millimetre, which is real evidence. The 15 frame anchors
   depend on an unpublished NAD83(2011)→NATRF2022 transformation with **no
   official specification released** (N0 §5: the developer test dataset is not
   out). They are a black box's output, and nothing here checks them against
   anything.
3. **The epoch semantics are unresolved** (§C above). Every frame anchor
   carries `Input Epoch 2020.00` under a datum labelled "epoch 2010.00". If
   that labelling is a beta defect, the frame anchors are anchors to the wrong
   question.
4. **Nothing vertical was captured.** No height, no geoid, no geopotential
   datum. Every combined factor is `N/A` by construction. N0 §3 found NAVD 88 ↔
   NAPGD2022 has no grid and no service.
5. **Four LDP zone origins are outside Michigan** and are not field-checkable.
6. **The digests are not reproducible** — see "Files" above. They pin the saved
   bytes, nothing more.
7. **No anchor here was compared against a second independent source.** N0's
   Michigan captures went through NGS's production NCAT; there is no production
   service that speaks SPCS2022, so there is no second opinion to be had today.
