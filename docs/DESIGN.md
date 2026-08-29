# DESIGN.md — Michigan SPC Zone Converter

**This document is the design authority.** `CLAUDE.md` is a working summary and
may be rewritten freely; this file is *amended*, never rewritten. Decisions are
recorded append-only in the amendment log at the bottom. A superseded decision
stays in the log with a pointer forward — history is evidence, not clutter.

---

## 1. Correctness tier

> **A wrong coordinate here lands on a sealed survey or a recorded legal
> description and moves a boundary.**

Everything below scales from that sentence. When a convenient behavior and a
correct behavior conflict, this sentence is the tiebreaker.

Direct consequences, adopted:

- Independent adversarial review at **both** the interim and closing gates.
- Every expected value in a test is hand-derived in a comment above it, from the
  equation or the published table — never read back from our own output.
- Loaders validate as strictly as the UI. Corrupt input never reaches the core.
- Fail closed. An unhandleable case produces a loud, specific refusal naming the
  offending item. No plausible default is ever fabricated.
- Two independent computation engines run on every point and must agree.

## 2. Scope

**In scope**

- Conversion of coordinate files between the three Michigan SPCS 83 zones:
  MI North 2111, MI Central 2112, MI South 2113 — all Lambert conformal conic.
- Geodetic (latitude/longitude) ⇄ State Plane, either direction.
- Grid scale factor, convergence angle, elevation factor and combined factor
  per point, with geoid separation from a registry of geoid models — GEOID18
  (default) and GEOID12B (#40).
- Vertical datum conversion of elevations, NGVD 29 ⇄ NAVD 88, via NGS
  VERTCON 3.0, with a per-point modeled shift and one-sigma uncertainty and
  the disclosure surfaces of #42 (added across #40–#44; the registry design
  is what NAPGD2022 later arrives through, #22/#32).
- Units: International feet (default and legislated), US survey feet, meters —
  selectable independently for input and output.
- Three outputs per run: a clean PNEZD file, a full-audit CSV, and a plain-text
  job record.

**Deliberately out of scope** (see §10 for the reasons)

UTM; SPCS2022 zones; NAD83 ↔ NATRF2022 transformation; other states; NAD 27;
two-point azimuth/distance computation.

## 3. Primary sources

| Source | Location | Used for |
|---|---|---|
| NOAA Manual NOS NGS 5, *State Plane Coordinate System of 1983*, Stem, Jan 1989, reprinted with minor corrections Mar 1990 | `docs/NOAA_Manual_NOS_NGS_0005.pdf` (committed) | All projection math, zone constants, factor definitions |
| NGS GEOID18 model, grid tile `g2018u3.bin` | `data/` (committed unmodified, SHA-256 pinned) | Geoid separation |
| NGS GEOID12B model, grid tile `g2012bu3.bin` | `data/` (committed unmodified, SHA-256 pinned in its `GeoidModel` record) | Second geoid model in the registry (WP-V5, #40) |
| NGS VERTCON 3.0, release 20190601, `.trn.b` and `.err.b` CONUS grids | `data/` (committed unmodified under NGS's own filenames, SHA-256 pinned) | NGVD 29 ⇄ NAVD 88 shift and its one-sigma uncertainty |
| NOAA TM NOS NGS-84 and `intg.f`; NOAA's published `Vertcon.java` | Read from `ngs.noaa.gov`; findings recorded in #36/#37, harnesses in `review/wp-v4-anchoring/` | The biquadratic scheme and its nearest-node stencil anchoring |
| NGS NCAT service | Frozen fixtures in `tests/fixtures/` | Independent verification anchors, horizontal and vertical |
| NGS geoid height API (`model=14` GEOID18, `model=13` GEOID12B — each response names its own model and the captures refuse a mismatch) | Frozen fixtures in `tests/fixtures/` | Geoid interpolation anchors, both models |
| Prior MATLAB implementation | `docs/reference/SPC_converter_AllZones_Elev.m` | Supplemental only, not authoritative |

Page citations in code comments refer to the **PDF's own page numbering**, not
the printed page numbers (the PDF leads the printed body by 10 pages).

**No uncited constants.** Every empirical coefficient, tolerance or proportion
carries its source document and page in an adjacent comment. Where the source
publishes no number and one is needed, it is declared a *disclosed convention*,
not a citation.

## 4. Data model

The pivot of every conversion is a geodetic position **tagged with its reference
frame**:

```
(zone A, N, E)  --inverse-->  Geodetic{frame, lat, lon}
                --transform-->  Geodetic{frame'}
                --forward-->   (zone B, N, E)
```

Zone-to-zone inside one frame is exact and reversible; the transform step is
currently the identity. Elevation is orthometric height, tagged with its
vertical datum when the job states one. In HORIZONTAL mode it is passed
through unchanged — it does not depend on the horizontal zone. In
HORIZONTAL_AND_VERTICAL mode it is **shifted between the stated vertical
datums before the geoid lookup and the factors** (plan §3.6, #41) — the
"passed through unchanged" sentence this section carried was repealed for
that mode at #41, and every output that carries a shifted height says so
(#42).

Result records produced by the core are frozen. UI layers never mutate them.

## 5. Core computation

**[ANNOTATED at #44: the polynomial engine described below was DELETED at
amendment #14 (owner directive), and this section went uncorrected for three
minor versions — found by the closing gate of the vertical feature. The
rigorous §3.1 equations are the only computation path; what verifies them is
external and lives in the suite: the frozen NGS NCAT anchors and the
published Appendix C constants. CLAUDE.md's conventions section has said so
all along; this body section now matches it.]**

The **rigorous** general Lambert conformal conic mapping equations, manual
§3.1 (pp. 27–29), are the only engine. Valid everywhere; Python's doubles
supply the significant digits the manual warns are needed (§3, p. 25).

~~2. **Polynomial coefficient method** — manual §3.4 (pp. 52–55) with the
Appendix C coefficients (pp. 103–104). Independent cross-check.
Disagreement beyond **0.5 mm** is a named, loud failure.~~ (Deleted, #14:
the polynomials are least-squares fits inside each zone's own latitude band,
so cross-zone conversion — this tool's core use — is extrapolation for them;
measured wrong by metres, #5.)

## 6. Extensibility

**Corrected by amendment #21 (2026-08-06); the original text is quoted there.**
Michigan's published SPCS2022 design is **19 zones on NATRF2022** — a statewide
oblique Mercator plus 18 low-distortion zones, 13 one-parallel Lambert and 5
transverse Mercator. The SPCS 83 North/Central/South zones do not carry forward.
NATRF2022 is finalized in beta but not released, and no official
NAD83(2011)→NATRF2022 transformation exists yet.

The seams below were **claimed** to let that arrive as data rather than a
rewrite. Two independent reviewers attacked that claim at the closing gate and
both returned REWORK-REQUIRED: the protocol, the second constructor and the
transformation seam do not exist in code. Amendment #21 carries the full list,
which is the opening specification of the SPCS2022 work package. They are
retained here as the intended design, not as a description of the code:

- **`Projection` protocol** — `forward(lat, lon)` and `inverse(N, E)`. Lambert
  today; the manual already supplies transverse Mercator (§3.2) and oblique
  Mercator (§3.3) for zone types other states use.
- **Two Lambert constructors** — from two standard parallels (the SPCS 83 form)
  and from a central parallel plus scale factor (the SPCS2022 1SP form).
- **Zone registry as versioned data**, not code. Adding a system means adding
  records and a citation.
- **Frame registry with an explicit transformation seam.**

**Safety rule, non-negotiable:** a conversion whose source and target frames
differ **refuses loudly** until a real transformation is implemented. It must
never pass coordinates through as though NAD 83 and NATRF2022 were the same
thing — that is a silent 1–2 m error on a sealed drawing, which is precisely the
failure the tier sentence exists to prevent.

## 7. Conventions (enforced in review)

- Units are explicit at every boundary. International feet is the default
  because Michigan legislated it (manual Table 1.5, p. 9, "Michigan(I)"), but
  the unit in force is stated in every output file.
- Longitude sign convention is **selected by the user, and the CORE has no
  default**. The manual and the prior MATLAB tool use positive-west; NCAT,
  OPUS, GPS and GIS use negative-west. A silent default here throws a Michigan
  point ~340 miles, so `JobSettings` requires it and `job.run` refuses a
  geodetic conversion that does not state one. **The GUI dropdown now opens on
  positive-west — amendment #29, on the owner's instruction. Read it before
  "fixing" this back.** The distinction that makes both true: the core assumes
  nothing, while the interface shows its answer in words before Convert is
  pressed.
- Missing elevations produce `N/A` in factor columns — never `1.0`, never the
  grid factor alone — and every affected point is named in the report.
- One authoritative representation per fact. Derived values are derived, never
  also stored.
- One entry point per data path. Every reader funnels through the same
  validation gate.
- Exports never silently clobber: atomic stage-and-rename, overwrite prompt, and
  a writer that refuses to produce a file its own reader would reject.
- No load-bearing asserts anywhere in production code; the suite runs under
  `-O`, which strips them. Use `if`/`raise`.

## 8. Verification anchors

| Anchor | What it proves |
|---|---|
| Appendix C published derived constants (B₀, sinB₀, R_b, R₀, K, N₀, k₀, M₀, r₀) recomputed from the defining constants alone, all three zones | Our §3.12 zone-constant derivation, checked against numbers NGS published |
| Frozen NCAT lattice across Michigan | Full forward/inverse chain against NGS's own implementation |
| Frozen GEOID18 API values | The grid reader and interpolator |
| Rigorous vs polynomial, every point | Independent recomputation |
| Round-trip zone A → B → A and SPC → geodetic → SPC | One-to-one mapping is preserved |
| Import/AST scans with anti-vacuousness checks | Architectural boundaries actually hold |

No test touches the network. Anchors are captured once and committed.

## 9. Repository layout

```
michspc/spc/      computation core — stdlib only, no Qt, no I/O
michspc/fileio/   readers and writers; owns csv and the binary grid format
michspc/gui/      PySide6; never computes a domain value
tests/            expected values hand-derived in comments
data/             four NGS grids, unmodified, each SHA-256 pinned: g2018u3.bin,
                  g2012bu3.bin, and the VERTCON 3.0 .trn/.err pair
review/           committed review harnesses and captured NGS truth data; each
                  claim in the design log maps to a script here (#36)
docs/             DESIGN.md (authority), method/, the NOAA manual, reference/
```

## 10. Deferred scope, with reasons

| Item | Reason deferred |
|---|---|
| SPCS2022 Michigan zones | Beta until 2027. The seam (§6) is built; the zones arrive as registry data plus a citation to NOAA SP NOS NGS 13 once NGS finalizes them. |
| NAD 83 ↔ NATRF2022 transformation | Requires NGS transformation grids that are not final. Refuses loudly meanwhile (§6). |
| UTM | Not requested. Requires the transverse Mercator engine (manual §3.2). |
| IGLD 85 (International Great Lakes Datum of 1985) | **Cannot be built the way this program builds anything.** NGS's own converter runs two steps and both need data NGS does not publish for download: NAVD 88 -> dynamic height via **NGS's NAVD 88 gravity model**, then dynamic -> IGLD 85 via a **hydraulic corrector** (per-lake grids that flatten each lake to its master gauge). `PC_PROD/IGLD85/` is a 404; the corrector grids exist only inside NGS's web tool, and queried live they returned **"out of bounds" at Detroit and Sault Ste. Marie** while neighbouring points succeeded — the model does not blanket Michigan. Measured through NGS's tool, IGLD 85 minus NAVD 88 runs about **-15 cm to +2 cm** across Michigan, crossing zero near 45.5 N; not constant, not smooth (the corrector alone accounts for up to 9 cm). Facts worth keeping: `H_dyn = C / gamma_45` with **gamma_45 = 980.6199 gals = 9.806199 m/s²** (Zilkoski, NGS; Heck & Craymer, FIG 2021 §3.1.4, two independent NGS-authored sources); IGLD 85 and NAVD 88 share their zero at Father Point/Rimouski and their geopotential numbers, differing only in height TYPE. **The Michigan statute is IGLD 1955, not 1985** — MCL 324.32502 fixes the ordinary high water mark on IGLD 1955 (Superior 601.5 ft, Michigan/Huron 579.8 ft, St. Clair 574.7 ft, Erie 571.6 ft); EGLE publishes an IGLD 85 equivalent table administratively. NGS datasheets carry a `DYNAMIC HEIGHT` field (API `geodesy.noaa.gov/api/nde/radial`) with **no corrector applied** — it must never be labelled IGLD 85. **Revisit when IGLD 2020 lands (~2027, already slipped twice)**: it is tied to NAPGD2022, keeps dynamic heights, expects much smaller correctors, and will move lake elevations by **as much as 60 cm** as it removes a ~35 cm tilt in the NAVD 88 leveling. That is the same dependency the roadmap already has (#32, #21). Researched 2026-08-11 at the owner's request. |
| Two-point azimuth/distance | Not selected by the owner. The three defects it inherits from the MATLAB tool are recorded in amendment #1 so the fixes travel with the feature if it is ever added. |
| Other states, NAD 27 | Out of scope by design. A Michigan tool is not a national one. |

Nothing here is reintroduced without revisiting the recorded decision.

---

## Amendment log

### #1 — 2026-08-05 — Project founding decisions

Supersedes nothing. Establishes the tier sentence (§1), scope (§2), two-engine
core (§5), extensibility seams (§6), and the deferred list (§10).

Owner-approved decisions recorded verbatim:

- PySide6 GUI only; no CLI. Single window with a results table below.
- Zone ↔ zone plus geodetic ⇄ SPC. Input PNEZD, no header row.
- Default International feet; US survey feet and meters selectable, input and
  output independently.
- Longitude sign convention: explicit GUI selector; no default in the core,
  and the dropdown opens on positive-west since amendment #29.
- GEOID18 bundled, automatic per-point lookup.
- Missing elevation: convert, write `N/A` in factor columns, name the points in
  the report.
- Out-of-zone points: convert, warn in the report only, keep the PNEZD export
  clean for CAD.
- Precision: N/E/Z 3 dp in feet, 4 dp in meters; factors 8 dp; convergence in
  DMS to 0.01″; latitude/longitude 8 dp.
- Codex CLI as the independent adversarial reviewer at both gates.
- Delivery as a PyInstaller/Inno `.exe` plus a run-from-source launcher.
- Remote: `martin71337/michigan-spc-converter`, private.

**Findings recorded against the prior MATLAB tool**
(`docs/reference/SPC_converter_AllZones_Elev.m`). Its zone constants match
Appendix C exactly and its output was verified against NCAT to 0.09 mm northing
and 0.18 mm easting, so it is a sound supplemental reference. Its defects:

1. Arc-to-chord in the geodetic→SPC branch computes `p1 = N1 - N0` mixing feet
   with meters, while the manual's 25.4 × 10⁻¹⁰ coefficient (p. 30) requires
   meters. The SPC→geodetic branch is correct.
2. Geoid separation sign is undefended; the manual (p. 47) defines it negative
   in the conterminous United States.
3. A single geoid separation is applied to two points that each carry their own
   elevation.
4. Grid azimuth from `atan2` is not normalized to [0, 360).
5. Line scale factor uses the mean of the endpoint factors; the manual §4.2
   (p. 50) prefers (k₁ + 4k_m + k₂)/6.
6. No zone-extent validation, and no cross-zone capability at all.

Defects 1, 4 and 5 belong to the two-point azimuth/distance feature, which is
deferred (§10). They are recorded here so the fixes travel with the feature.

### #18 — 2026-08-06 — Five file-layer defects fixed; one brief of mine was wrong

All five defects the WP5 test subagent found are fixed and pinned with their own
counterexamples, each falsified. Two entries are worth keeping for the record.

**My brief was wrong about `_parse_number`'s `.replace(",", "")`.** I told the
subagent it was dead code. It is dead for *unquoted* fields — `csv.reader` has
already eaten those commas as delimiters — but **live for quoted ones**, and
`'101,"13,221,442.048",…'` was an existing passing test. The subagent checked
rather than complied, and said so. It kept the replace and *validated* it: the
text must match a genuine grouped-number pattern first, so a quoted `"1,2"` is
now refused instead of silently becoming `12`. That is a better outcome than
either the original code or my instruction.

**The thousands-separator refusal fires only on genuine ambiguity.** A row is
refused when it has two well-formed readings — the split signature (a 1–3 digit
field followed by an exactly-3-digit field) *and* a description beginning with a
bare number, which is the structural consequence of a stray comma shifting a
numeric token past the elevation column. Independently probed by the lead
against fourteen row shapes: the counterexample, a quoted `"1,2"`, `nan` and
`inf` are refused; ordinary rows, quoted grouping, comma-bearing descriptions, a
description that *is* a number, blank elevations, negative eastings and metric
coordinates all still parse. No over-rejection.

**Dead carry guards in `angle_dms` deleted**, with the live mechanism documented
in their place: rounding happens once on the total before either `divmod`, and
`divmod`'s remainder is strictly below its divisor, so neither boundary can be
crossed after the split. The subagent proved the claim itself over 88,612,997
angles rather than accepting mine, and noted honestly that re-adding a dead
guard cannot fail a test — so it falsified against the rounding order instead.

Also fixed: `build_report` now iterates the warnings actually raised rather than
the heading table, so a future `WarningCode` without a heading is printed rather
than counted-and-hidden; and `pnezd.read`'s cp1252 fallback catches
`UnicodeDecodeError` as well as `OSError`, so an undecodable byte produces a
`PnezdError` naming the byte and its position rather than a raw traceback.

### #19 — 2026-08-06 — Interim gate finding #1 fully closed: the record states the frame

The core has refused a cross-frame geodetic input since #11's fix landed, but
the job record did not say which frame it had read the file as — so half the
finding was still open. A geodetic input file carries no frame in its own
columns, and reading NATRF2022 positions as NAD 83 is a one-to-two metre error
that looks entirely ordinary on the page.

`report.py` now prints, for geodetic-input jobs only, the frame the latitudes
and longitudes were interpreted as. Zone-to-zone jobs do not get the line: their
frame comes from the zones, which the COORDINATE SYSTEMS section already states
per zone, and an input-frame line there would imply the user chose something
they never chose.

Verified end to end, which also closed the WP6 subagent's reported gap that no
geodetic conversion was tested at all: 42.73250000 N, −84.55550000 W into
Michigan South gives 449,212.689 / 13,072,628.343 international feet, which is
the interim reviewer's own metre figures (136,920.027586723 / 3,984,537.119005890)
divided by 0.3048 exactly. The pin was falsified.

### #20 — 2026-08-06 — Closing review gate: 17 findings, all fixed and pinned

The closing gate ran three independent tracks, blind to each other: the Codex
CLI over the whole codebase, an Opus adversarial reviewer, and a **live NGS NCAT
cross-check** driving every pipeline through the real file path. Prompts and raw
output are in `review/gate2-prompt.txt`, `review/gate2-output.txt`,
`review/opus-probes/` and `review/ncat-crosscheck/`; the session lead's
adjudication is `review/gate2-adjudication.md`.

**The mathematics was found correct by all three tracks.** The live cross-check
made 666 comparisons over 13 fresh points — geodetic⇄SPC in all three zones, all
six directed zone pairs, all three unit systems — against NCAT and the NGS geoid
API, and every one passed: single-leg linear agreement to **0.5 mm**, chained
zone-to-zone to **0.9 mm**, grid scale factor and convergence matching NCAT's
printed precision **exactly**, geoid separation within the API's own 1 mm print
quantum. Both reviewers independently re-derived §3.1 from the manual — Codex at
80 digits, Opus at 60 digits writing the manual's positive-west form from
scratch — and matched production to ~1e-9 m.

**Every defect found was in the contract, the record, or the safety gates — not
in a coordinate.** At this tier that distinction is not a comfort: a deliverable
that misstates its own units is a wrong number in the reader's hands.

Two interim-gate fixes were recorded in #11 as landed and had **not** landed:

- **The `constants=` seam.** #11 says the caller-supplied constants parameters
  were "deleted rather than guarded". They were not; all four public conversion
  functions still accepted them, `LambertConstants.zone_code` existed to make
  the mismatch checkable and nothing read it, and `test_convert.py` pinned the
  seam *open* by testing only the matched pairing. Mispairing moved a point
  **4,231 km** with no warning. Now genuinely deleted, and pinned by signature.
- **The longitude convention default.** `JobSettings.longitude_convention`
  defaulted to negative-west against §7's "no default" rule, and its pin only
  counted enum members. A positive-west file converted under the silent default
  lands **11,634,618 m** away. The field is now required; `None` is sayable only
  by a zone-to-zone job, which never consults it, and `run` refuses any other
  direction that arrives with it.

Interim pins #2 (the 0-360 east longitude, 275.4445) and #3 (non-finite input)
were **never written at all** — the reviewer seeded both pre-fix behaviours and
260 tests stayed green. Both are now pinned and falsified.

Fixed in this round, each pinned with the reviewer's own counterexample and each
pin falsified by reverting the fix:

| Defect | Consequence before the fix |
|---|---|
| Zone→geodetic elevation left in the INPUT unit while the clean export, audit CSV and record all declared the OUTPUT unit | 900 ift read as 900 m: **625.680 m**; re-import as the record instructs: 98 ppm factor error |
| Job record described geodetic files as "PNEZD … northing, easting" | three false statements about a latitude/longitude file, in the program's only documentation |
| Geoid lookup failure silently merged into "no elevation" | a point whose Z *was* recorded listed under "Blank elevation field" — a falsehood in an audit record |
| `verify_round_trip` compared only point identifiers | every coordinate, elevation and description could be corrupted and still pass the writer's own safety gate |
| Input SHA-256 hashed independently of the bytes parsed | the record could certify a file that was never converted |
| Duplicate point identifiers accepted | export names a point that picks out neither row |
| `overwrite=False` committed with `os.replace` | a file created by another process mid-write was destroyed |
| ZIP never fsynced, never verified before commit | a corrupt archive could reach the deliverable name |
| Lenient CSV quoting silently repaired malformed rows | `"A"junk` became `Ajunk`; the parsed text stopped representing the file |
| Cone-apex band raised bare `ZeroDivisionError` | 20–45 m of northing per zone refused with no point named |
| Audit CSV formatted geodetic input degrees as linear coordinates | 42.73250000 recorded as 42.733 — about 55 m |
| BOM survived into `point_id` on the cp1252 path | point "101" matched nothing on the way back |
| GUI table headed degrees "Northing"/"Easting" | the screen named a latitude a northing |

The unit selectors were examined and deliberately **left enabled in every
direction**: a geodetic side's Z column still carries a linear unit and still
drives the elevation and combined factors, so greying the control would make a
wrong foot definition unselectable rather than unnecessary. The label and
tooltip now say which column the unit governs.

**A defect found by the fix round itself.** The WP-R4 verification package,
writing anchors, found that `lambert.forward` had the same bare-arithmetic
failure near the poles that `inverse` had just been hardened against: `sin()`
rounds to exactly ±1 over the last ~6.04e-7° (about 67 mm) below each pole, and
`isometric_latitude` then evaluated `log(2/0)`. North side raised
`ZeroDivisionError`, south side a `ValueError` out of `math.log` naming nothing.
No Michigan survey reaches it; the rule it broke has no latitude qualifier. The
symmetric guard is in, pinned, and falsified. The package reported it rather
than fixing it silently, which is the behaviour the method asks for.

**Verification, rebuilt.** The suite went **546 → 855**. The 27 frozen NCAT
anchors drove `lambert` directly and nothing drove the production path end to
end, which is exactly why the unit and record defects survived — one whole
direction, `ZONE_TO_GEODETIC`, had **zero** successful executions anywhere in
the suite. Now: the 13 live cross-check points are frozen as fixtures in
`tests/fixtures/ncat_crosscheck.py` (401 values, every one transcribed from the
raw NGS JSON and machine-verified against it, none recomputed by this program),
and `tests/test_ncat_crosscheck.py` drives **file → `job.run` → `write_all` →
the ZIP → the parsed audit CSV** for all three directions in all three units,
asserting against NGS figures rather than against the program's own output.
Anti-vacuousness was demonstrated by seeding seven separate production defects
and confirming which tests caught each.

Rejected nothing this round. Codex's finding 11 (no fsync, no startup cleanup of
stale `.partial` files) was accepted in part: fsync and pre-commit archive
verification are in; a startup sweep for orphaned `.partial` files is **not**,
because nothing in the program is a daemon and a sweep would race a concurrent
job. Recorded here so it is a decision rather than an omission.

One platform dependency is now load-bearing and stated: the no-clobber commit
relies on Windows `os.rename` refusing an existing target. POSIX `rename`
replaces silently. This program ships for Windows (§9); a port would need
`O_EXCL` or an equivalent.

### #24 — 2026-08-07 — 0.1.1: the icon's transparency was painted on, not real

Owner asked for a transparent background where the checkered area was, and for
the artwork to be enlarged. Investigating the first found a defect rather than a
preference.

**The checkerboard was in the artwork.** `assets/icon/coord-convert-1024.png`
had the grey-and-white squares an image editor draws to *indicate* transparency
painted into it as opaque pixels — all 1,048,576 of them alpha 255, confirmed by
reading the decoded alpha channel. The shipped icon therefore carried grey
squares behind the badge on every surface that respects alpha. It went out in
0.1.0.

Three parts of the build asserted the property and none verified it:
`make_icon.py`'s module docstring states "the artwork has a transparent
background"; its resampler premultiplies alpha and divides it out afterwards for
the sole purpose of keeping a transparent edge from fringing; and every entry is
written as a 32-bit BGRA DIB whose alpha channel is meant to carry the
transparency. All three were correct code operating on artwork that had none —
the same shape as this project's other findings, where the record and the
artefact disagreed and only the record was ever read.

**What was done.** The badge's rounded-rect geometry was measured from the
image (left 169, top 171, right 854, bottom 859, corner radius 126.7), the alpha
channel rebuilt from a 4x4-supersampled rounded-rect mask inset 3 px so no
checkerboard-blended edge pixel survives, the image cropped to the badge so it
fills the canvas instead of 67% of it, and the result rescaled to 1024 so the
master keeps its documented size. The baked drop shadow is gone: it was painted
onto the checkerboard and could not survive its removal.

Two measurement errors worth recording, both caught by looking at the output
rather than trusting the arithmetic. The corner radius read off the top
scanline gave 105 against a true 126 — up there the circle is nearly tangent to
the row, so one pixel of anti-aliasing moves the first dark sample a long way
sideways, and the too-square mask cut the corners through the checkerboard and
left grey nubs on the edge. Refitting from mid-curve samples, where
`r = (dx+dy) ± sqrt(2·dx·dy)`, then required the **larger** root; taking the
smaller one gave 63 and a visibly wrong corner. Two independent rows agree on
126.2 and 126.7.

**Pinned.** `tests/test_icon.py` now asserts the committed master's corners are
fully transparent, its centre opaque, and its edge anti-aliased rather than a
1-bit cutout. Falsified against the old artwork, which fails on the first
corner. The derivation script was a one-shot and is not committed; the original
artwork remains in history at `50ada05` for anyone who needs to redo it.

Not addressed, and still the owner's call: at 16 and 32 px the "COORD CONVERT"
lettering is below the size at which text resolves. Enlarging the badge does not
fix it; the usual remedy is a cropped, text-free compass variant for the small
sizes inside the same `.ico`.

### #61 — 2026-08-28 — The modernized NSRS build opens: scope, N0 measurement, and the vertical half's deferral

**This amendment reopens two items from §10's deferred list by revisiting
their recorded reasons (METHOD.md §7), and re-defers a third with a new,
measured reason.** The working specification is
`docs/PLAN-nsrs-modernization.md`, approved by the owner 2026-08-28 after two
rounds of his decisions (tabled there); this amendment is the design
authority's record of the decision and of what the N0 measurement gate found.
Until the work packages land, the program's behaviour is unchanged — this
amendment changes the record, not the code.

**What reopens, and why the recorded reasons no longer hold.** §10 deferred
the SPCS2022 Michigan zones and the NAD 83 ↔ NATRF2022 transformation because
NGS had published no final data ("Beta until 2027", "transformation grids that
are not final"), and #21's verdict was "PARTIALLY BUILDABLE, and deliberately
not built now" because the datum layer had no oracle. Two facts changed:
NGS declared the definitional beta products **stable for implementation
planning and integration** on 2026-05-28 (feedback periods complete), and the
owner instructed on 2026-08-28: **build and release ahead of the official
~Q1 2027 rollout** — "i want to have it ahead of time." Every beta-derived
artifact carries the literal token `NGS beta` with its capture date, a
committed re-freeze checklist (`docs/REFREEZE-NSRS.md`, arriving with the
first beta artifact) maps each one to its recapture harness and
authenticating pin, and the release gate will refuse while any `NGS beta` tag
remains unless an explicit acknowledgement flag is passed — each beta release
is a conscious act. **Sealed work may carry beta-era numbers; that is the
owner's explicit, recorded decision**, and the record's factual provenance
lines (capture dates, digests, NGS's own beta wording) are the defense.

**N0 ran before any code (2026-08-28), on the owner's machine.** Full record:
`review/nsrs-n0/FINDINGS.md`, with 177 raw captures, per-fetch manifests, and
eight re-runnable harnesses; the session lead independently reproduced one
probe of each decisive family before accepting. Verdicts:

- **SPCS2022 Michigan: GO.** All 19 zone definitions captured verbatim and
  digest-pinned (`zoneDefinitions.json`, SHA-256 `f222dac6…`): one statewide
  Hotine oblique Mercator (OMC, skew −26°, k₀ 0.999800, origin 45°N/86°W),
  five TM, thirteen LC1, all on NATRF2022, all origin scales ≥ 1, false
  origins published in metres and international feet **only** — NCAT prints
  `N/A` for usft on every 2022 zone, which is the citation basis for the
  per-zone unit restriction. None of the three SPCS 83 Lambert zones survives
  into SPCS2022. NGS states "All parameters are exact values."
- **NAD83(2011) ⇄ NATRF2022: GO, web-app oracle only.** Beta NCAT v3.0
  performs the transformation (at 43°N/−84.5°W: +0.943 m, −0.798 m, ±0.02 m
  printed σ; the reverse is the exact negation to every printed digit; the
  ellipsoid height changes by **−1.115 m**, load-bearing for factors). **No
  REST API on either host accepts any NATRF2022 token** — the probe matrix is
  frozen — so anchors are captured by driving NCAT's own form (harness
  committed) and frozen, as GEOID12B's were. NGS's NCAT engine is open source
  (`github.com/noaa-ngs/ncat-lib`, Java) — the reference-implementation path
  the transformation math will be verified against, as `Vertcon.java` was for
  VERTCON. EPP2022 captured (181 bytes, SHA-256 `63d80d64…`). One
  contradiction is recorded and MUST be resolved at H3, not assumed: the
  single-point app labels its input "NAD83(2011) epoch 2010.00" yet reports
  "Input Epoch 2020.00".
- **NAVD 88 ↔ NAPGD2022: NO-GO — the product does not exist.** No grid, no
  service, no mention on any captured beta page; both hosts' APIs refuse
  every token; the beta app has no geopotential-datum control and silently
  drops orthometric heights; NGS's own FAQ answers the modernized-datum
  question in the future tense. GEOID2022 grids themselves ARE published
  (GGXF **and** legacy `.b`/`.bin` — so the plan's build-time conversion tool
  is unnecessary), static grid at epoch 2020.0 plus a rate grid (the geoid is
  now time-dependent), with σ grids, ~475 MB for Michigan's needs,
  interpolation **bicubic** per the file's own declared attribute — with no
  NGS reference implementation located and only two NGS test points near
  Michigan. There is no geoid API for GEOID2022 on any host.

**The owner's decision on the vertical half (2026-08-28): DEFERRED.** The
program will not convert to a datum NGS has published no path to — deriving
the ~0.5 m NAVD 88 → NAPGD2022 offset from the GEOID18/SGEOID2022 difference
is exactly the fabrication this program refuses. NAPGD2022 stays
`DECLARED_NOT_USABLE`; its registry citation gains the measured reason. The
chained NGVD 29 → NAPGD2022 path (which the owner had approved, with RSS σ
composition) defers with it, both to return as data + anchors when NGS
publishes. The GEOID2022-for-GNSS-heights option (H = h − N onto NAPGD2022)
was offered and declined for now — verification would rest on two check
points and an unreferenced interpolation method, the thinnest footing of
anything MCX would ship.

**#32's ordering is thereby resolved, not violated:** #32 made SPCS2022
downstream of NAPGD2022 so no conversion mixes eras inside a factor. With the
vertical half deferred, a 2022-zone job carrying elevations computes its
factors from the height its file holds and the geoid model the user selects
(GEOID18 today), exactly as horizontal jobs have always done under the #41
asymmetry — the datum question is undeclared in horizontal mode by the
owner's standing decision, the model in force is named on every surface, and
the magnitude of the era gap inside an elevation factor is ~0.5 m of H in
R/(R+H+N) ≈ **8×10⁻⁸**, three orders below the 5.9 ppm the ellipsoid-height
feature corrected. Recorded as fact, not mitigated further.

**Operational hazard, standing rule:** `beta.ngs.noaa.gov/api/*` answers
`200 OK` with `N/A`/`{}` where `geodesy.noaa.gov` returns numbers — **beta's
REST API fails open.** Legacy-quantity truth captures come from production
only; NATRF2022-era truth comes from the beta web-app captures, frozen with
their harness. Also pinned when the anchors land: NCAT's multipoint datum
list carries a duplicate `NATRF2022 epoch 2020.00` entry with a leading
space, and NGS writes zone abbreviations both `MI_L45G` (JSON) and `MI L45G`
(NCAT) — both sanctioned, neither canonical.

**Body corrections carried by this amendment:** §2's out-of-scope line and
§10's rows for SPCS2022 and NAD 83 ↔ NATRF2022 are superseded — those items
are now in scope under the plan; §10's NAPGD2022-adjacent expectations gain
the measured NO-GO reason; and §10's SPCS2022 row's sentence "The seam (§6)
is built" was false when written (#21 proved the seams are intended design,
not code) and is corrected in place. The body text edits land with the work
packages that make them true.

**Process, the owner's instruction:** Opus subagents design and build the
work packages; the session lead verifies — independently re-deriving
load-bearing math and checking claims against the code; **Codex reviews at
every gate** (two interim, one closing — this tier runs all of them; the
0.6.x releases' gateless cadence does not apply here). The horizontal work
packages H1–H6 proceed per the plan; the first code lands only after this
amendment, which is the H0 exit condition.

### #60 — 2026-08-26 — 0.6.4: new application artwork, chosen from three

**The owner's instruction:** a new icon, presented for approval before anything
was committed. Three candidates were drawn and shown at 16, 32, 48 and 128 px —
reduced through `make_icon.resample_area`, the build's own premultiplied area
average, so the comparison was of what Explorer would actually receive and not
of a browser downscale. He chose the one titled **Converted Point**. He gave no
reason and none is recorded here; the other two are described only so the
record says what the choice was made against.

- **Converted Point (chosen).** A survey monument — ring, crosshair, amber
  centre — with two arc arrows turning around it, on the graphite tile over a
  faint square grid. The most legible of the three at 16 px, where the ring and
  centre still resolve.
- **Three Zones.** Michigan with its three State Plane zones tinted separately,
  North being the whole Upper Peninsula. Recommended by the session lead and not
  taken. Had it been, this amendment would have had to record that its outline
  was hand-traced rather than derived from boundary data, which on this
  program's tier sentence is a claim worth being careful about.
- **Grid Exchange.** Two arrows bending along a Lambert graticule drawn with
  converging meridians. Rejected in review before it reached him as the weakest:
  the convergence carrying the whole idea is gone by 32 px.

**The compass rose it replaces** had been the artwork since 0.1.0. It read as
*direction*, which is not what this program does.

**No computation changed, and the amendment claims nothing beyond artwork.**
The suite is 1,696 green in both run modes, including the cross-version digest
pin, so a change that quietly moved a number would have failed rather than
needed arguing about.

**The invariant of #15 note 1 is intact and was deliberately not renegotiated.**
`assets/icon/mcx-1024.png` is still the single authoritative representation and
the `.ico` is still derived by `tools/make_icon.py` into build output. The new
artwork was drawn by a script rather than by hand, which raises the question of
whether the script becomes the authoritative source and the PNG a derived
artifact. **It does not, and the reasoning is #24's:** that amendment's
derivation script was a one-shot and was not committed either. A drawing tool
stands in the same relation to the artwork as an image editor does — nobody
commits the editor's project file — and committing it would create the second
representation §7 exists to forbid. The previous artwork remains in history, as
#24's did.

**Verified against the pins rather than assumed.** `tests/test_icon.py` passes
unchanged, 25 tests: 1024×1024 8-bit RGBA through `decode_png_rgba8`, all four
corners alpha 0, centre alpha 255, and an anti-aliased edge. The build step
produces the same six-size 370,070-byte `.ico`.

**One caveat worth carrying, found by measuring rather than by a failure.** The
edge pin requires more than 1,000 partially transparent pixels. The old artwork
had 8,205; this one has **1,536**. The margin narrowed because the new tile's
straight sides fall on integer pixel boundaries, so only the four corner arcs
produce partial coverage, where the old artwork's baked soft edge produced it
everywhere. 1,536 passes and the property the pin exists to protect — a real
alpha channel, not a 1-bit cutout — is fully intact. But **a future master that
is more axis-aligned still, or drawn at a smaller corner radius, could cross
that floor while being perfectly correct.** Anyone replacing the artwork should
read that number rather than assume the pin is slack.

### #59 — 2026-08-11 — Field validation: the owner has run real jobs end to end

**The owner's report, at the close of the session:** *"i have ran jobs end to
end. no issues."*

This closes the longest-standing open item in this record. METHOD.md §7 makes
field validation a precondition for anything real leaning on the outputs, and
§6 makes the human proof a release requirement; every release from 0.1.0 to
0.6.3 carried it forward unmet, and the working summary named it after each
one. It is met: the program has converted real work, on the owner's own
machine, and produced nothing he had to correct.

**What it does and does not cover.** He states jobs run end to end — the
program installed, read real input, converted, and wrote outputs he accepted.
The half of METHOD §6 that remains unconfirmed in his own words is the
**clean-profile** install specifically: whether a machine without a developer's
Python and Qt already on it was among those tested. That distinction is
recorded rather than assumed either way, because it is the one an installer
defect would hide behind, and the frozen-bundle self-test is evidence but not
proof of it.

**What still has no substitute:** a real PNEZD file from an actual job
committed as a fixture. The reader is still built to a documented convention.
Jobs running clean is strong evidence the convention matches reality; a
committed file would make it a regression pin. Downgraded from an open risk to
a nice-to-have.

No code changed for this amendment. It is recorded because the absence of
field validation was recorded, repeatedly, and a record that only carries the
gap and never its closing is a record that misleads.

### #58 — 2026-08-11 — Owner: every geodetic selection names the datum

**The owner's instruction**, in his words: *"before all 'geodetic' selections
we should add NAD83. this is because NAD83 is different from WGS84, and the
new ellipsoid will be different again."*

**Why it matters more than a label usually does.** NAD 83 and WGS 84 differ by
**a metre or more** in the conterminous United States — a boundary-moving
amount by this project's own tier sentence. A dropdown reading only "Geodetic"
asks no question at all, and the obvious wrong answer is close enough to look
right: a handheld or a phone gives WGS 84, it pastes in cleanly, and it
converts to a plausible State Plane coordinate a metre from the truth. The
program has always converted against NAD 83(2011) and always said so in the
job record; it did not say so at the point of choosing.

**Derived, not typed.** `GEODETIC_LABEL` is built from `NAD83_2011.code`, the
frame record the projection actually uses, so the label cannot drift from the
mathematics — and it answers the second half of his sentence by itself: when a
job eventually runs on NATRF2022 the dropdown renames itself rather than
needing to be remembered. The pin asserts the derivation, not just the text,
and a hard-coded "NAD83 geodetic..." fails it.

One change reaches all four dropdowns — both ends of both tabs — because
`zone_combo` builds every one of them. The realization travels with the datum
("NAD83(2011)", not "NAD83") because the record's own code is the
authoritative string and the realization is the thing that changes next.

Suite **1695 → 1696**, green in `pytest` and `-O`. Two falsifications: the
datum dropped from the label, and the label hard-coded instead of derived.

### #57 — 2026-08-11 — Owner's layout round: a hint, three saved rows, and a geoid that grays

**Five instructions, all interface, no computation touched.**

1. **A hint inside the Single point elevation box** — grey italic, "optional,
   used for combined scale factor" — **in HORIZONTAL MODE ONLY**. That last
   clause is the whole care this needs: #51 removed a TOOLTIP from this very
   box for calling the elevation optional in all three modes, and a
   placeholder saying it sits inside the field, which is more prominent. It is
   cleared in both vertical modes and pinned empty there. Grey comes free from
   Qt's placeholder palette; italic does not, and Qt has no placeholder-only
   font, so **the widget is italic while empty** — an empty box shows nothing
   but its placeholder, and the italic comes off on the first keystroke so a
   typed elevation is never slanted.
2. **Three paired rows compacted onto one line each** on the Single point tab:
   the two vertical datums, the two geoids, and the elevation beside the
   height-kind control. Fourteen grid rows to eleven. Every control keeps its
   own label on the same row, so nothing is inferred from position, and the
   pairing is pinned through the layout rather than by eye.
3. **The Multi point geoid dropdown grays when no elevations are read**, in
   horizontal mode. With no height there is nothing to look a separation up
   for and every factor that would use it reads N/A, so the model choice
   changes nothing the job produces.
4. **The elevations note** now reads "used for combined scale factor", from
   "used for the elevation and combined factors" — the combined factor is the
   number that reaches a drawing; the elevation factor is an intermediate
   nobody asks for.

**The defect this round produced, caught by an existing pin.** The first
graying wrote `geoid_combo.setEnabled(vertical or elevations)`, which
**re-enabled a combo the per-datum filter had deliberately grayed** — two
methods driving one property, the later call winning, so an NGVD 29 target's
output geoid came back to life. #50's own graying pin caught it. The rule now
only ever DISABLES, and only in horizontal mode; in the vertical modes the
enablement belongs entirely to `_refresh_geoid_sides`, and a pin says so.

**Verification.** Five falsifications, each caught by its own pin: the hint
left in place in the vertical modes (#51 again), the italic never coming off a
typed value, the paired rows split apart, the geoid no longer graying, and the
note reverting. Suite **1690 → 1695**, green in `pytest` and `-O`.

### #56 — 2026-08-11 — Owner removes the glosses, and a duplicated row goes with them

**The owner's instruction**: drop the "(elevation)" and "(GNSS)" after
*Orthometric* and *Ellipsoid*. The dropdown now offers **Orthometric** and
**Ellipsoid**; the horizontal elevation column, on screen and in the audit CSV,
reads **Ellipsoid height**. Text removed, behaviour untouched — the #34/#51
ruling again.

**What the removal exposed, and the reason this is an amendment rather than a
string edit.** The panel's supplied-height row carried "(GNSS," for a stated
reason: the factors block has shown a computed `Ellipsoid height (m)` row since
0.1.0, and without the qualifier the two labels are identical on a metres job.
Removing the gloss forced the question, and the honest answer is that they were
never two facts. The computed row recomputes h = H + N from a conversion that
derived H as h − N, so on an ellipsoid-input job it is **arithmetically the
same number** as the height the user typed — `(h − N) + N` is `h`. The
qualifier had been distinguishing one value from itself.

So the computed row is **dropped on ellipsoid-input jobs only**. The value
stays on screen once, as the height supplied. On an orthometric job the row is
untouched and still shown, because there h = H + N is a genuinely separate
fact from the Z — pinned in both directions. The reconstruction it used to
demonstrate is still checked, in the audit CSV's own column and by its pin.

**Left alone, and flagged for the owner:** the audit CSV now carries both
`Ellipsoid height` (the Z column, output unit) and the long-standing
`Ellipsoid height (m)` (computed, always metres). Those are two distinct
strings a reader sees together in one header row, not the identical-label
collision the panel had, so the panel's resolution was not extended to them.
On a metres job they hold the same number.

**One vacuous pin found and fixed while falsifying this.** The control's
wording test compared `combo.currentText()` against the constant it came
from, so re-adding "(GNSS)" passed it — the LOW-3 class the 0.5.0 gate had
just flagged, recurring in a test written after it. The wording is now pinned
as literals, and the seeded gloss fails it. Suite **1690**, green in `pytest`
and `-O`.

### #55 — 2026-08-11 — The ellipsoid-height closing gate: two false headings, one weak pin

**The gate.** Codex CLI, read-only, over `v0.5.0..HEAD` (WP-E1..E5), at the
owner's instruction. **Verdict FINDINGS: one HIGH, one MEDIUM, one LOW, no
CRITICAL.** Its explicit negatives matter as much as the findings: the
`_convert_row` invariant **holds** — it traced every read of `elevation_m`,
`supplied_m`, `height_m` and `written_m` and confirmed the rebinding carries
the feature — **no accepted configuration produced a wrong converted height or
factor** across a full 3-modes x 4-operations x 4-model-placements matrix, no
refusal could be bypassed, the clean PNEZD stayed five headerless fields, and
the benchmark fixture's honesty statement about what it does not prove was
checked and upheld. It independently recomputed the 5.192 ppm factor error at
43 N / -84.5 W.

**HIGH 1 — h escaping into a field labelled H, on two surfaces.** In
HORIZONTAL mode the Z column holds the ellipsoid height, passed through by the
owner's own rule, and both the audit CSV column and the Multi point table
heading still read **"Elevation"** over it. At the gate's test point that is a
number **33.085 m** from the elevation the heading claims. The CSV's adjacent
`Input height kind` column mitigated it only for a reader who noticed that
column; the table carried no qualification at all. This was one of the three
decisions #54 recorded as taken by the session lead and open to review — the
review took it, and it was wrong. Both headings now read
`Ellipsoid height (GNSS)`, one wording on both surfaces (#17), and an
orthometric job keeps the 0.1.0 heading to the string.

**MEDIUM 2 — a record contradicting the file beside it.** The new ELEVATIONS
branch keyed on `ellipsoid_model_name` alone, not on the mode. A horizontal
job whose point falls off the geoid tile still WRITES its Z — that is what
horizontal mode does — while the record said the elevation was "deliberately
not written" and "deliberately absent from the exports". The same
WP-R2-fix-C class the design review had already caught once in this feature,
and the same section states it twice, so both copies were wrong. Both now
branch on the mode and say what actually happened: the Z carries the ellipsoid
height as supplied, and only the factors are missing.

**LOW 3 — a compatibility pin that was self-comparison.**
`test_the_default_leaves_every_existing_job_alone` compared HEAD-with-default
against HEAD-with-ORTHOMETRIC-explicit, so an unconditional regression — a
metre added to every height — left it green. The gate accepted the manual
cross-version digest evidence as establishing the current build but correctly
called it a captured artifact rather than a test. **Converted into one:**
`tests/fixtures/orthometric_output_digests.txt` holds the SHA-256 of all 18
CSV members of nine ordinary jobs, **computed by v0.5.0 itself** in a detached
worktree, and `tests/test_orthometric_regression.py` compares against them
with two anti-vacuousness tests beside it. The seeded metre now fails it.

**A defect in the evidence, found while fixing LOW 3 and recorded rather than
quietly corrected:** the original digest harness reused one output folder per
job shape across all three units, so its member names collapsed three
configurations into one. The comparison itself was still valid — each digest
was taken immediately after its own write, and both runs wrote in the same
order — but the naming was ambiguous. The frozen fixture was regenerated with
unique names, 18 distinct keys.

**Verification of the fixes.** Four falsifications, each caught by its own
pins: the audit heading left as "Elevation", the table heading left as
"Elevation", the horizontal record claiming the Z was withheld, and a metre
added to every written height. Suite **1681 → 1690**, green in `pytest` and
`-O`.

### #54 — 2026-08-11 — Owner's feature: ellipsoid (GNSS) heights as input

**The owner's instruction**: the Z column may hold ellipsoid heights from a
GNSS receiver; convert them with H = h - N. His answers to the scoping
questions: **input only** (no ellipsoid output); the selector **defaults to
Orthometric**; available in **all three modes**; and then, decisively, **"in
horizontal only mode, the elevations should be passed through unchanged,
regardless of the input"** — with the factors still computed correctly.
Placement: **beneath the "Elevations: in file" button, grayed unless that is
selected.**

**What the feature fixes, beyond convenience.** The elevation factor is
R / (R + H + N). Feed the program a height that already contains the
separation and it adds it again — |N| is about 34 m in Michigan, so every
combined factor is wrong by roughly **5 ppm**, measured at 5.9 ppm on a real
Upper Peninsula point. About a third of a foot in ten miles, systematically,
in one direction, making grid distances long. Nothing on screen looks wrong.

**The design.** One conversion, one place; the mode decides only what is
WRITTEN. `elevation_m` is rebound to the orthometric height immediately after
it reaches metres, establishing the invariant that carries the feature — *from
that line down, `elevation_m` is an orthometric height in metres, on every
path, in every mode* — which is why the eight downstream readers needed no
edit. The written Z is the supplied height in horizontal mode and the derived
one in the vertical modes, in a single expression. `Factors` needed no new
field: what reaches `factors_at` is genuinely orthometric, so
`orthometric_height` keeps its meaning and `ellipsoid_height` stops
double-counting and reconstructs the user's own h.

**THE DESIGN REVIEW CAUGHT A BUG IN THE APPROVED PLAN before a line was
written.** The plan converted into `height_m`; the identity branch a few lines
below re-reads `elevation_m` through `apply_shift` and would have overwritten
it — so on the flagship same-datum job the feature would have done nothing
while every output reported a conversion, and both VERTCON and #41's
source-era factor path would have been handed a raw ellipsoid height with
nothing downstream able to notice. Pinned by name
(`test_the_identity_branch_cannot_overwrite_the_converted_height`).

**Three refusals, all before any point converts:** no geoid model on either
side (no N, so no H); a source vertical datum that is not the model's own (an
ellipsoid height is in no vertical datum, and the H derived from it is in the
model's); and — **the owner's decision** — a geoid change combined with
ellipsoid input. That last is not an arithmetic failure: the input model
cancels out of `(h - N_in) + (N_in - N_out)`, so it changes no number, while
the record would state a conversion FROM a model the height was never on. A
false sentence in an audit document is the thing refused.

**A second false sentence, also caught by the review.** A point off the geoid
tile lands in the ELEVATIONS section's "read but not written" bucket, whose
only branches were VERTCON and geoid-swap — so an identity job, which loads no
VERTCON grid at all, would have blamed "the point lies outside the VERTCON
grids". The WP-R2-fix-C class through a **third** door. The section states the
fact twice, counted and then with the points named, so both copies gained the
branch.

**Supersessions and amendments, each recorded rather than slipped in:**

* **#52 generalises.** The geoid model is named wherever the displayed
  orthometric height DEPENDS on a model — a geoid change, **or** a height
  derived from an ellipsoid height — and still never beside a leveled height,
  which depends on none (#50's recorded geodetic fact). #52's two negative
  pins survive unchanged.
* **#48 is partially amended, with the owner.** Its reasoning covers the "in
  file" button and its note and only those; they still hide in the vertical
  modes. The Elevations label and the height-kind control stay visible in all
  three, because the question is asked in all three and matters most where the
  answer decides whether the Z is converted at all.
* **A label collision resolved:** the supplied height reads
  `Ellipsoid height (GNSS, m)`, because the factors block has carried a
  computed `Ellipsoid height (m)` row since 0.1.0 and on a metres job the two
  would have been the same string in the same section.

**Disclosure.** An ELLIPSOID HEIGHT CONVERSION block in the record — model,
tile, digest, arithmetic, and the datum of the result — placed before the
vertical block because h → H runs first, ordering pinned. Its load-bearing
paragraph is the mode one: a horizontal ellipsoid export is
byte-indistinguishable from an elevation export, so the record says outright
that the Z carries the ellipsoid height as supplied. The audit CSV gains
`Input height kind` in every mode and `Ellipsoid height in (unit)` in the
vertical ones, so `Source elevation` keeps meaning the pre-shift orthometric
height and the row's arithmetic stays closed. The clean PNEZD export is
unchanged: five headerless fields, pinned to contain no ellipsoid token.

**Verification.** WP-E1 captured **fourteen NGS published Michigan
benchmarks** (`tests/fixtures/ellipsoid_height_anchors.py`, raw capture and
harness at `review/wp-e1-ellipsoid/`), each carrying both an NAVD 88
orthometric height and a GEOID18 separation on its own datasheet; our reader
matches NGS's published separations to **0.75 mm worst** across the state. The
fixture states plainly what they do NOT prove — NGS derived those separations
from the same model, so they are not an independent derivation of the geoid.
The tolerance is derived: the published H cancels out of the comparison,
leaving only the separation disagreement. The Houghton anchor pins both
directions off #50's own frozen figure. A ninth frozen-bundle self-test check
converts one ellipsoid point end to end. **Nineteen falsifications across the
five packages**, each caught by its own pins. Suite **1609 → 1681**, green in
`pytest` and `-O`.

**Decisions taken by the session lead and open to the owner's review:** the
`Input height kind` column on a horizontal CSV (a row cut out of the file must
say what its Z is); `Source elevation` holding the derived pre-shift H rather
than the raw h; and the control's wording, "Heights are:" with "Orthometric
(elevation)" and "Ellipsoid (GNSS)".

### #53 — 2026-08-11 — The 0.5.0 closing gate: one MEDIUM, and it was a crash the per-side split introduced

**The gate.** Codex CLI, read-only, over the whole unreleased range
`v0.4.0..HEAD` (#50, #51, #52), at the owner's instruction after he reversed
his own "no review" answer. **Verdict FINDINGS: exactly one MEDIUM, no HIGH,
no CRITICAL.** Everything load-bearing was re-verified independently and came
back clean — the swap arithmetic recomputed (200.000 → 199.9676565265265 m
and the reverse → 200.0323434734735 m), the ellipsoid height provably fixed
across the swap, eighteen accepted/refused per-side configurations consistent
at Houghton, the audit CSV naming each side correctly, the record's GEOID
CHANGE arithmetic accurate, the clean PNEZD still five headerless fields, and
the GUI's filtering, emission, invalidation and new headings tracing
correctly. Its explicit negatives are worth recording: **no wrong in-coverage
elevation, no sign reversal, no double swap, no wrong-era factor, no stale
clipboard path, no false written disclosure.**

**The finding, which the session lead had found independently from the same
diff fragment and fixed before the gate returned — same defect, same
counterexample, same test point.** `_convert_row`'s GEOID_UNAVAILABLE warning
named `settings.geoid_model.name`, whose comment claimed "grid is only ever
non-None when settings.geoid_model is a record". **#50 made that false.**
`grid` is now loaded from `factors_geoid_model`, which is the INPUT side when
the output side has no model — and NGVD 29 has none, so a NAVD 88 → NGVD 29
job carries `geoid_model=None` with a real input-side grid. At a point off
the geoid tile the warning dereferenced None: `AttributeError`, killing the
whole job where one point should have converted with N/A factors.

**Reachability, which is what set the severity.** It is not an exotic call
shape — it is **exactly what both GUI tabs emit for that datum pair**, since
the output geoid selector grays itself and emits None (#50's own design). It
needs only a point off the tile. Codex's input: vertical-only, geodetic,
metres, negative west, NAVD 88 → NGVD 29, input geoid GEOID18, output None,
`1,39.5,-84.0,200.000,OFF` — 39.5 N is south of the tiles' 40.0 N edge while
VERTCON covers it, so the datum shift succeeds and the geoid lookup is the
only refusal. Expected: 200.20998242497444 m NGVD 29, combined factor N/A,
one geoid-unavailable warning. **MEDIUM rather than HIGH because it fails
closed** — the job stops, and no wrong coordinate is written.

**Why the suite missed it.** Two pins bracketed it without meeting: an
in-grid source-only model (`test_the_new_shape_writes_the_record_the_old_shape_wrote`)
and an off-grid two-model swap
(`test_a_point_outside_the_geoid_tiles_refuses_the_swap_and_stands`). The
defect lives at their intersection. The #42-finding-3 class again — a
sentence about a height going false when the thing it names moves — which
#50 itself cited and still reintroduced one line away.

**Fixed at the root**: the message names `factors_geoid_model`, the side the
grid was actually loaded from, so it cannot name a model the point did not
consult. Pinned by
`test_a_geoid_refusal_names_the_side_the_grid_was_read_from` at the
reviewer's own input and expected elevation; **falsified** by restoring the
original expression, which reproduces the AttributeError at that line. Suite
**1608 → 1609**, green in `pytest` and `-O`.

**Gate limits, recorded not hidden:** the read-only sandbox blocked eight
filesystem tests (no writable temp directory) and the fallback interpreter
lacked PySide6, so the GUI suites did not collect under Codex. Both were run
in full by the session lead in the ordinary environment, and the release
build's own gate 3 runs the whole suite in both modes.

### #52 — 2026-08-10 — Owner's instruction: a geoid-to-geoid elevation names its geoid on screen

**The owner's instruction**: on a same-datum geoid conversion the output must
say which geoid the result is displayed in, **in a parenthesis after the
units**. Answers to the two scoping questions, his: **both ends**, each naming
its own model; **screen only** — the audit CSV already carries `Source geoid
model` and `Geoid model` columns and the record already carries its GEOID
CHANGE block, so those two say it already.

**The problem it fixes.** On a swap job the two elevation rows read
`Elevation (NAVD88, m)` at both ends — identical strings over two different
heights, because the datum and the unit are the same on both sides and the
model is the entire difference between them. The panel showed the shift row's
`Geoid change GEOID12B -> GEOID18 (m)` but nothing said which of the two the
number above it was on.

**What changed.** `Elevation (NAVD88, m) (GEOID18)`, a separate parenthesis
after the unit one as instructed. INPUT names the input model, OUTPUT the
output model; the Multi point table's single elevation column names the
OUTPUT model, the model its cells are on. Named **only** where
`job.geoid_swap_models` says a swap ran — not on a modeled datum shift and
not on same-model identity — because #50's recorded geodetic fact is that a
leveled orthometric height does not depend on the hybrid model, and tagging
one beside a leveled height would assert a dependence that does not exist.
The panel reads the point's **own** `GeoidSwapReading`, so a point whose swap
was refused carries no model name even where every other point converted; the
heading reads the job's settings through the same registry lookup `job.run`
and the record perform.

**A duplicate removed on the way.** `_elevation_heading` and
`_datum_elevation_label` were two f-strings producing the same text; the
heading now delegates to the label. One fact in two places is what lets a
panel and a table drift apart, and #26 spent a whole gate establishing that
these two cannot.

**Verification.** Four pins: the swap panel's two tagged rows (each naming its
own side), the tagged table heading, and two negatives — same model both sides,
and a modeled NGVD 29 → NAVD 88 shift — asserting no geoid token appears on
any label. The heading pin also asserts the table's string is one the panel
also shows, which is the shared template pinned as a property rather than as
two literals. Three falsifications, each caught by exactly its own pins: the
heading tag suppressed, the tag leaked to every vertical job, the input row
named with the output model. Suite **1605 → 1608**, green in `pytest` and
`-O`. No computation, no written output, no clean PNEZD byte touched.

### #51 — 2026-08-10 — Owner removes the Single point elevation tooltip

**The owner's instruction, from looking at the real screen**: the Single point
tab's elevation field carries a tooltip calling the elevation *optional*; he
found it in Horizontal + Vertical and in Vertical mode, where it is false.
Remove it. **No cross-check, his instruction** — one deleted string with one
falsified pin behind it.

**Why it was wrong.** `single_point.setToolTip(ELEVATION_TOOLTIP)` ran once
when the field was built, so the sentence stood in all three modes. It was
written for the horizontal tab this program started as, where a blank Z is a
legitimate "not recorded" and the factor columns then read `N/A`. In the two
vertical modes the elevation is the value the job exists to convert: it is not
optional, and the leading word said it was. This is the same class as #48's
"passed through unchanged" on the Multi point tab — a horizontal-era sentence
left standing after the vertical modes arrived — and the third and last one on
either tab.

**What changed.** `ELEVATION_TOOLTIP` and its one call site are deleted; the
field keeps its label, its behaviour and its place in the grid. **Removed
rather than made mode-dependent**, which is the owner's choice here and #34's
standing ruling on this tab's tooltips. #48 hid the whole Multi point row
instead, and the two are not in conflict: that row was a *question* the
vertical modes never ask, where this is a *field* every mode needs.

**What the removal costs, recorded rather than mitigated.** This tab no longer
states in words that a blank or exactly-zero elevation means "not recorded".
The behaviour is unchanged and still pinned, and the result panel shows the
`N/A` itself when it happens — text removed, not behaviour, as in #34.

**Verification.** One pin, `test_the_elevation_field_carries_no_tooltip_in_any_mode`,
asserting an empty tooltip in **all three** modes and the absence of the module
constant — all three because a pin looking only at the vertical modes would
pass against a rewrite that restored the text in Horizontal. Falsified by
setting the tooltip back on the field: the pin fails on the Horizontal pass
with the seeded string in the diff. Suite **1604 → 1605**, green in `pytest`
and `-O`. No computation, no formatter, no written output touched; the version
literal does not move.

### #50 — 2026-08-09 — Owner's feature: per-side geoid selection, and geoid-to-geoid conversion

**The owner's instruction**: vertical jobs choose the geoid for the input and
the output separately, so the same datum can be transformed between geoid
realizations (NAVD 88/GEOID12B → NAVD 88/GEOID18); a datum with no
associated geoids (NGVD 29) gets its selector GRAYED (disabled, his word —
not hidden); future datums gray inapplicable models through the registry.
**No Codex gate, his instruction** — the review weight is the hand-derived
pins, six falsifications, and the session lead's independent from-scratch
verification. **A second instruction arrived mid-build: no disclaimers
visible to the user, on any surface including the written record.**

**What was built.** `JobSettings.source_geoid_model`; on a same-datum
vertical job with two different models the elevation converts by
**H_out = H_in + (N_in − N_out)** — the ellipsoid height held fixed, both
separations from the shipped grids at the pivot — carried on a
`GeoidSwapReading` whose arithmetic is enforced in its own constructor.
Each side's model must match its side's datum; the per-side rule
**supersedes #41's either-endpoint contortion by generalization** (factors
pair each height with its own side's model; every #41-era call shape
normalizes to per-side form and every existing outcome is bit-identical,
pinned). New refusals: an input-side model on a horizontal job; a per-side
datum mismatch; **a compound job** — both sides geoided across a modeled
datum shift — refused as two modeled operations in one job (reachable today
only as the same model on both sides of NGVD29↔NAVD88; the guard is for
NAPGD2022's arrival). GUI: Input geoid / Output geoid rows in the vertical
modes, each filtered by its side's datum and **disabled with items cleared**
when its datum is unanswered or has no models; both default GEOID18, so
nothing converts differently unless the user changes a dropdown; Horizontal
mode is pixel-identical to before. σ for a swap: **bare N/A** — NGS
publishes no error model for the difference of two hybrid geoids — with no
explanatory prose, per the no-disclaimers instruction. The record's GEOID
CHANGE block states facts only: both models, tile filenames, digests, the
arithmetic. **The absence of caveat prose is itself pinned** (a record may
not contain 'GNSS', 'leveled', 'benchmark', 'disagreement', 'cannot know'),
falsified by seeding the caveat back.

**The geodetic fact, recorded HERE because the outputs no longer carry it
(the owner asked the question directly and has the answer):** a leveled
NAVD 88 height does not depend on the hybrid geoid model — GEOID12B and
GEOID18 were each fitted TO the leveled network, and updating the model
moves no published benchmark. The swap arithmetic is the re-derivation of a
**GNSS-derived** orthometric height under the other model (h fixed,
H = h − N); applied to a leveled height it states the two models'
disagreement at the point rather than a new realization of the benchmark.
The program cannot know which kind of height a Z column holds.

**Verification.** Hand-derived from BOTH frozen NGS fixture sets at the
Houghton anchor (N18 = −33.796, N12B = −33.828, both printed to 0.001 m):
12B→18 moves 200.000 → 199.968, the reverse → 200.032; the shipped grids'
exact difference is −0.032343 m ("−0.106" ift under #47's input-unit rule —
the fixture-quantized figure would read "−0.105", and the pin holds the
exact grid value with the derivation recorded). Same-model both sides is
bit-identical to the pre-feature identity job; all pre-existing job shapes
byte-identical on every surface; the factors' ellipsoid height provably
fixed ((H+N_in−N_out)+N_out = H+N_in, pinned). Six falsifications, each
caught by exactly its own pins: the sign flipped (lands at 200.032 where
199.968 is pinned), one grid read twice (swap 0), the graying filter
dropped, the new combo's invalidation disconnected, the compound refusal
deleted, the caveat seeded back. **Independently re-verified by the session
lead from scratch**: own N readings from both grids, the job's Z and swap
shift to 1e-9/1e-12, exact round-trip symmetry, the audit column present.
One GUI test replaced (the NGVD29-identity refusal is no longer
constructable from the screen — both sides gray and no model is emitted, so
the job honestly converts with N/A factors; the core refusal of the old
call shape remains pinned).

**Suite: 1565 → 1604**, green in `pytest` and `-O`. Committed to `main` and
pushed. 0.4.0 shipped without this feature; it rides the next release.

### #49 — 2026-08-09 — 0.4.0 RELEASED: vertical datum conversion ships

**The owner's release instruction, executed.** Version literal 0.3.1 →
0.4.0; `py tools/build_release.py` passed **all eight gates** on this
machine: suite **1565** green in both modes, the icon build, the PyInstaller
bundle (139.8 MB), the frozen bundle's own self-test **8/8** — GEOID18,
the VERTCON pair, the vertical conversion (200.000 m NGVD 29 → 199.8598 m
against NCAT's 199.860), GEOID12B through the registry (−33.2850 against
NGS's −33.285), 23 lazy imports, Qt + icon, and the end-to-end NCAT
conversion (0.0000 ft northing, 0.0010 ft easting) — the Inno Setup
installer `mcx-0.4.0-setup.exe` (42,645,282 bytes, SHA-256
825a4587bf45dd5845e4753e0b07e526c84310e3e5afe0a9561e2fa28b118c33), and the
checksum manifest naming all four bundled NGS grids. Tagged `v0.4.0`;
installer, `SHA256SUMS.txt` and the frozen self-test transcript on the
GitHub Release; notes are `docs/RELEASE-NOTES-0.4.0.md`.

**What ships**: everything of #35–#48 — NGVD 29 ⇄ NAVD 88 via VERTCON 3.0
with per-point σ in the job's input unit, the vertical-only mode, the geoid
model registry with GEOID12B, the GEOID18 re-anchoring, the disclosure
surfaces, and the two inherited fixes (the longitude-convention stale
result live since 0.1.0, the scaled-display copy glyph).

**Still human, and now the only outstanding item of METHOD.md §6:** install
on a clean profile and run one real job end to end. The release was cut on
the owner's instruction with that proof outstanding, as every release since
0.1.0 has recorded; a real PNEZD file from an actual job also remains worth
having.

### #48 — 2026-08-09 — Owner's Multi point elevations-row fixes, cross-checked under Codex

**Owner's instruction**: the Elevations "in file" tooltip was wrong in the
two vertical modes (elevations are not passed through unchanged there — the
mode exists to change them); the button itself is unnecessary in those modes
(the elevations MUST be in the file); and where the button remains
(Horizontal), a visible note should say the elevations are used for the
factor calculations.

**What changed.** The Elevations row — label, "in file" button, and the new
note — hides in HORIZONTAL_AND_VERTICAL and VERTICAL modes and returns with
Horizontal, mirroring the datum rows' hidden-not-disabled idiom; the geoid
dropdown beside it stays in every mode. `elevation_in_file` is read by no
settings path (verified), so hiding it changes no job. The note is on-screen
text, not a tooltip (#34's ruling stands): "— used for the elevation and
combined factors". Pinned: visibility across all three modes and the
transitions, the note's text AND its membership in the row — the first
version of that pin passed with the label orphaned out of the layout, which
its own falsification exposed, and it now checks the shared parent.

**The cross-check ran under Codex** — the owner's instruction, and the
re-confirmation the #44 closing gate left as his option, in one pass. Its
quota had reset; its sandbox could not run the full suite (`py` unavailable,
no writable temp — the #35-recorded limitation) so the suite gates ran on
this machine instead: **1565 green in `pytest` and `-O`**. Codex verified
clean: the visibility wiring across every mode transition including
H+V ↔ Vertical; #45's row genuinely absent from panel and Copy all; **#46's
mirror re-proven independently** (rendered cells preserved exactly, output
floats bit-identical to parsed input, only Z changing); **#47's unit
conversion hand-derived** (−0.14019644 m ÷ 0.3048 → "−0.460") and agreeing
on every surface; horizontal jobs byte-identical against the pre-round
commit; and the #46 round-trip-verifier change shown to be a strict
IMPROVEMENT — Codex constructed a `200000.0005` case where the old
tolerance ACCEPTED the wrong adjacent value and the exact-against-rendered
form refuses it.

**Codex's findings, both fixed:** (MEDIUM) the Horizontal-mode tooltip still
said "passed through unchanged", which is imprecise even there — a differing
output unit re-expresses the value (Codex's counterexample: 900.000 ift is
written as 274.3200 m; the height is the same, the number is not) — and the
test pinned only the presence of the old words. The tooltip now says the
honest thing (not converted between datums in this mode; a differing output
unit re-expresses the value; blank/0.00 means not recorded) and the pin
asserts the new wording and REFUSES "unchanged". (LOW) code and tests cited
this amendment before it existed; it exists now.

**Suite: 1563 → 1565**, green in both modes. Committed to `main` and
pushed; no release.

### #47 — 2026-08-09 — Owner's units instruction: shift and σ in the job's input unit, units on the elevation output

**Owner's instruction**: add units to the elevation output, and present the
shift and shift sigma in the job's input units instead of defaulting to
metres.

**What changed — presentation only, the internals stay metres.**
`VerticalReading.shift_m`/`sigma_m` are untouched; conversion happens at the
display boundary through one new formatter, `formatting.vertical_quantity
(value_m, unit)`, rendering at the unit's own declared precision.
`vertical_metres` is deleted, not delegated — a unit-less shift formatter is
the door this defect class walks through. The heading authority lives in
`exports.py` (`vertical_shift_heading`/`vertical_sigma_heading`, functions
of the unit) and the table imports it, so per #17 the panel, the table and
the audit CSV move together and a heading can never claim a unit its cells
are not in — the headings and the cell conversions take the same unit
object. The record's σ summary converts likewise; its σ>|shift| comparison
stays in metres (unit-invariant). **The display unit for shift and σ is
`settings.input_unit`** — the owner's words; in vertical-only mode input and
output units are equal by construction, and in Horizontal + Vertical the
input unit governs these two quantities while the Elevation heading names
the output unit its own cells are in. Datum-tagged elevation labels gain
their unit — `Elevation (NAVD88, m)` — INPUT label with the input unit,
OUTPUT with the output unit; horizontal jobs' plain labels are untouched by
a byte.

**What the change corrected on its way in**: two pre-existing tests pinned
`(m)` shift labels over FEET jobs — the exact mislabel the instruction
removes, live on screen for any feet-unit vertical job until now.

**Verification.** Hand-derived pins at the anchors: −0.14019644 m →
`-0.460` ift and `-0.460` usft (the two foot definitions differ in the 7th
significant digit; the pin asserts the floats differ so the usft case is not
vacuously the ift one), σ 0.0006554 m → `0.002` ift, max-σ 0.3656 m →
`1.199` ift; metre jobs render exactly as before — the metre path is the
regression floor, and written outputs of metre vertical jobs are
byte-identical. Four falsifications, each caught by name: the from/to
conversion swapped (the feared defect — produces −0.043 where −0.460 is
pinned; the metre pins alone would NOT see it, which is why the feet pins
exist); σ converted but the shift left metres; CSV headings converted with
metre values beneath; the OUTPUT elevation label fed from the input unit in
a differing-units job. **Independently re-verified by the session lead**
with a from-scratch script: hand conversion, panel/table cell and audit CSV
cell agree in all three units at anchor-22, and a 200.000 ift elevation
lands at 199.540 ift through the whole job (200 ift = 60.96 m, −0.140196 m,
back out).

**Suite: 1553 → 1563**, green in `pytest` and `-O`. Committed to `main` and
pushed; no release.

### #46 — 2026-08-09 — Owner's feature: a vertical-only mode on both tabs

**The owner's instruction**: a third mode, **Vertical**, on both tabs. The
user states the INPUT horizontal system — a Michigan zone (PNEZD file) or
geodetic positions — and no output system; the only conversion performed is
the vertical datum shift; the Multi point export mirrors the import except
the elevations.

**What was built** (implemented by a work-package subagent to the session
lead's settled decisions, then gated): `Direction.VERTICAL_ONLY` and
`VerticalMode.VERTICAL`, mutually required; `target_zone` refused;
`output_unit` must equal `input_unit` (the export reproduces the input's
columns — a unit change would alter them); the longitude convention required
for geodetic input and stated-None for zone input (the ZONE_TO_ZONE rule).
Zone input inverse-projects for the pivot and reports the INPUT zone's
factors (the ZONE_TO_GEODETIC precedent); geodetic input runs **no
projection at all** — `Factors.grid_scale_factor` became optional so no zone
is ever fabricated: grid scale and combined factors read N/A while the
elevation factor, which needs no zone, is computed. **The shift is the same
code path as HORIZONTAL_AND_VERTICAL — proven bit-identical, not asserted**
— with the #41 either-endpoint guard, the coverage shape and the σ rules
unchanged. Output coordinates are the input row's own floats; the clean
export keeps the input's layout with only the Z shifted; the audit CSV's
target columns equal its source columns and the Target zone cell reads
"vertical only"; the archive stem is `_VERTICAL`. GUI: a third radio via the
shared helper — **whose addition exposed a structural trap the implementer
caught itself**: the two-button toggle wiring listened to the Horizontal
button alone, and a Vertical ↔ Horizontal+Vertical switch toggles neither
old button, so the old wiring would have missed that mode change entirely —
the #26 stale-result class, rewired to the group signal and pinned. To-zone
and output-unit controls hidden in this mode; the Single point OUTPUT
section holds exactly the target-datum elevation, the shift and σ.

**The gate (independent Opus): FIX-FIRST — no CRITICAL, no HIGH; "no
coordinate moves anywhere I could reach."** Its own verification: the mirror
claim held over **2,007 assertions across 45 written-archive configurations**
(coordinate cells character-identical to the formatted input, output floats
bit-identical to the parsed input, Z differing by exactly the re-derived
shift, five fields, both conventions — including a positive-west file
mirrored as written); the shift over 294 assertions (all 25 NCAT anchors ×
both directions × both input formats); the refusal matrix 17/17; the #26
property over 174 assertions including every mode transition; **horizontal
and H+V regression: 891 archive members across 297 configurations
byte-identical to HEAD**; 15 seeded defects, 15 caught. Findings, closed
this round:

1. **MEDIUM — the record printed "no point carried a usable elevation" on a
   geodetic-input job whose every point carried one**, contradicting its own
   ELEVATIONS section five lines below — the #42-finding-3 class recurring:
   the empty-combined-factors implication broke when `grid_scale_factor`
   became optional and the sentence was not re-guarded. It now keys on WHY
   the tuple is empty (no zone vs no elevation), both spellings pinned, the
   both-causes case resolved to the sentence true of every point.
   Falsified.
2. **MEDIUM — an ordinary metre PNEZD northing could refuse the whole
   archive, only in this mode.** `verify_round_trip` compared the re-read
   value against the PRE-ROUNDING float within half a place; a value whose
   next decimal is exactly 5 rounds a hair past that, and in this mode the
   value is the user's own literal — trip rates up to **83% of 5-decimal
   metre northings in Michigan's main bands** (the gate measured them),
   where every pre-existing direction's computed values hit the boundary
   with probability ~2⁻⁵². Fail-closed — no wrong number was ever written —
   but a whole-archive refusal naming the program's own reader. **Fixed at
   the root for every direction**: the verifier now compares the re-read
   value EXACTLY against the value the writer promised (the job's number
   rendered at the written precision) — strictly tighter than the old
   tolerance, and a NaN still refuses because NaN ≠ NaN.
   `_rounding_tolerance` is retired with a tombstone note. Pinned with the
   gate's own 166625.16645 reproduction; falsified by restoring the
   tolerance form.
3. **MEDIUM — this amendment** (the feature was unrecorded; §2's scope list
   and the release-notes draft now carry the mode).
4. **LOW, fixed**: the `vertical_mode` impostor refusal now names all three
   modes; the release notes' claim that the panel carries the caveat in a
   row of its own (stale since #45) corrected.
5. **LOW, carried with reasons**: the record's METHOD block still prints the
   Lambert apparatus on a geodetic-input job where no projection ran —
   inapplicable, not false, and the factor-provenance paragraph beside it
   says plainly that no zone is involved; `Combined factor: N/A` sits on
   the geodetic panel without an on-screen explanation (consistent with the
   owner's #45 ruling); the bare-Elevation label on refused points (#42/#44
   carry) now also appears in this mode; the archive prose's
   "moved between zones" sentence on a job that moved between none; the
   frozen self-test exercises H+V but not vertical-only. All owner-visible
   at the release review.

**Suite: 1505 → 1553**, green in `pytest` and `-O`. Committed to `main` and
pushed; still no release — **and the owner has still not seen any of the new
controls on a real screen**, now including the third radio.

### #45 — 2026-08-09 — Owner removes the Vertical method row from the results panel

**Owner's instruction.** The "Vertical method" caveat row — added at the
WP-V7 gate's HIGH 1 as the on-screen carrier of the modeled-not-measured
caveat, on the reasoning that the Single point tab writes nothing — is
removed from the OUTPUT section and, with it, from Copy all. This reverses
the #42 gate's resolution **under the owner's own standing ruling** (#33:
verification is the user's responsibility; #34 applied the same ruling to
three tooltips).

**Text was removed, not information.** The transformation record's caveat
still reaches every *written* job in full through the record's METHOD block
(pinned, unchanged); the σ-unavailable warning still reaches the panel's
warnings field; the shift and σ rows still name their datums. What no longer
exists is any caveat on the Single point screen for an unwritten conversion
— that is the owner's decision, made with #42's reasoning in front of him,
and it is recorded rather than argued with.

**The removal is pinned** (`test_the_vertical_method_row_stays_removed`): a
row that quietly returned would be a decision nobody made. The label
constant survives for that pin to name. #42 finding 1 is annotated by this
amendment; suite 1506 → 1505 (two caveat-content tests replaced by the
absence pin), green in both modes.

### #44 — 2026-08-08 — WP-V9 and the closing gate: the vertical feature is COMPLETE, unreleased

**WP-V9**: the frozen self-test now converts one vertical point end to end —
200.000 m NGVD 29 at anchor-22 → 199.8598 m against NCAT's 199.860 — inside
the bundle, with its constants pinned `==` to the fixtures and a failure test
seeded with the sign-flipped outcome; `docs/RELEASE-NOTES-0.4.0.md` is
drafted, explicitly marked DRAFT: **the version literal has not moved, no
installer is built, no tag exists — the owner reviews first**, including the
tab layouts nobody has seen on a real screen.

**The closing gate, and the reviewer substitution recorded rather than
glossed:** Codex was invoked per the standing method and refused on quota
("You've hit your usage limit… try again at 5:17 PM" — the log is in the
session record). The owner's standing fallback (2026-08-07: independent Opus
reviewers if Codex usage runs out) applied; the closing gate ran on an
independent Opus reviewer briefed as the outsider over the full
`3eda02a..HEAD` diff plus the working tree. **A Codex re-confirmation after
the quota reset is available to the owner if wanted; it was not required to
close.**

**Verdict: FIX-FIRST → all findings closed → the reviewer's sign-off
condition met. No CRITICAL, no HIGH — "no elevation is converted wrongly,
and no unconverted height escapes as converted, through any path I could
find."** What it verified with its own harnesses, never importing the
suite's expected values: **1,113 elevation configurations against the frozen
NCAT anchors — 0 failures** (all anchors × 3 directions × all 9 zone pairs ×
all 9 unit pairs × both conventions × both datum directions × identities;
round trips < 1e-6 m in every unit); the 42-combination datum × geoid ×
coverage seam sweep; disclosure honesty across 11 archive shapes with the σ
summary hand-verified character-exact; #43's "every selection discards the
result" re-proven across all 24 widgets and 25 mutations; screen-vs-archive
0 mismatches over 16 shapes; 28 seeded defects across 8 modules, 25 caught
— the 3 survivors being exactly the two pin-gap MEDIUMs below.

**The findings, all closed this round:**

1. **MEDIUM — the Multi point table's σ cell was the ONE surface of #36's
   "N/A, never a number" rule held by nothing**: a seeded `0.0000` there
   survived the whole suite while the CSV and the warning beside it read
   N/A — three surfaces of one job contradicting each other, and zero is
   the most misleading available value where σ runs to 0.3656 m. The
   shipped code was correct; the pin was missing. Now pinned at both
   σ-less readings (the negative-σ position and an identity job, shift
   `0.0000` and σ `N/A` distinguishable), falsified with the gate's own
   seed.
2. **MEDIUM — a `CHECKS` entry could be deleted silently**: both tests
   touching the self-test registry were self-referential, so removing any
   check — including the new vertical one the release notes lean on —
   stayed green. The #38-finding-2 discipline now applies: the full
   ordered name list is pinned; falsified by removing the vertical entry.
3. **MEDIUM — the draft release notes claimed "horizontal mode is unchanged
   in every byte of its output", which is false**: the gate byte-diffed
   1,136 configurations against **released v0.3.1** — the comparison no
   interim gate had made, each having proven only its own parent unchanged
   — and found the audit CSV's geoid/ellipsoid heights move at 13.6% of
   positions (WP-G1's disclosed re-anchoring, worst 4.5 mm in its sweep)
   and one record METHOD line reworded. **The clean PNEZD export is
   byte-identical in all 1,136 configurations; no coordinate, elevation
   factor or combined factor changed anywhere.** The notes now say exactly
   that. The record-keeping lesson is the finding: a chain of
   parent-relative regression proofs does not compose into a
   release-relative one.
4. **LOW, fixed**: the self-test's "280 times the tolerance" was 140 (wrong
   in the flattering direction, the #38-finding-4 class); the record's
   all-refused paragraph pointed at a WARNINGS section that can be empty;
   §2's scope now contains the feature; §4's repealed "passed through
   unchanged" sentence now says when it was repealed; **§5 still described
   the polynomial engine deleted at #14 three minor versions ago** —
   annotated and corrected (found in passing by the gate; the body now
   matches the conventions CLAUDE.md carried all along).
5. **LOW, carried with reasons**: a vertical audit row on a feet job names
   every unit but supplies no conversion factor (nothing false is
   printed); a coverage-refused point's panel shows two bare `Elevation`
   labels (re-confirming #42's carry, slightly broader).

**Suite: 1503 → 1506**, green in `pytest` and `-O`; the frozen-source
self-test passes 8/8 including the vertical conversion.

**The feature stands complete: V0–V9 plus WP-G1, every package interim-gated,
the whole closed by this gate.** Still owner's, before any release: look at
the two tabs on a real screen (#43 describes the layouts); decide the
Vertical method row's wording (#42 carried it as re-wordable); the clean-
profile install proof (METHOD.md §6); a real PNEZD file from a job; and the
release itself — version bump, `py tools/build_release.py`, tag — which
nothing in this record performs.

### #43 — 2026-08-08 — WP-V8: vertical mode reaches the screen, and the gate catches a CRITICAL that shipped in 0.1.0

**What was built** (plan §4, plus #42 finding 4): the Horizontal /
Horizontal + Vertical toggle as the Conversion box's first row on **both
tabs** (per-tab, never window-level — #26 forbids shared state; proven
independent), the two vertical datum dropdowns revealed by the toggle
(hidden, not disabled; **opening unanswered** per §7's no-default rule;
offering exactly the registry's *usable* datums — NAPGD2022 excluded by its
own `is_usable`, not by name), the geoid dropdown built from
`ALL_GEOID_MODELS` in declaration order (GEOID18 first, no "none") replacing
the Multi point tab's static label and newly added to Single point, Convert
gated on both datums, refusals surfaced verbatim (the GUI greys out no
combination — the refusals teach), and **the Multi point table's vertical
columns**: the Elevation heading names the target datum, shift and σ columns
sit directly after it with the audit CSV's own wordings, and the
table-vs-CSV pin is parametrized over BOTH directions — because the raw grid
value and the applied shift are the same number under sign +1 and negatives
of each other under −1, so only the inverse direction discriminates a shift
cell fed from the wrong source. `ResultsModel` now derives its
warnings-column and alignment indexes from its own header: the old fixed
index 6, applied to the nine-column vertical table, painted the wrong cell
amber.

**The gate (independent Opus): FIX-FIRST — the WP-V8 diff itself held** ("I
could not break it"): 13 controls × 2 result kinds driven adversarially with
copy paths checked after each, 64 two-tab configurations with 320 cell
comparisons bitwise against the panel, the table AND the written audit CSV
(zero disagreements), settings honesty under exhaustive mode sequences
(hidden combos never leak), refusals character-identical through the real
Convert click, horizontal GUI regression exact to the cell and the archive
digest, and 12 seeded defects — 11 caught by exactly their claimed pins.
What it found:

1. **CRITICAL, inherited — live in released 0.3.1 and every release since
   0.1.0: the longitude sign dropdown never invalidated a displayed result
   on the Single point tab.** Wired to Convert-gating only; every other
   control reaches `_invalidate_result`. Flip the convention after a
   geodetic conversion and the old convention's result stays on screen
   captioned "Converted", both copy paths armed — the gate measured a stale
   northing **9,756,797 m out**, the largest magnitude the #26 class has
   produced, dwarfing #26's own 100,001 ft counterexample. **#26's fix text
   — "every entry field and every selection discards the result" — was
   false for exactly this control**, and #26's own test parametrized zones
   and units and never the convention. (That the *preselect* debate of
   #29/#33 orbited this exact control for three rounds while the
   invalidation gap sat unnoticed is recorded without comment.) Fixed: the
   combo now drives gating AND invalidation; pinned
   (`test_flipping_the_longitude_convention_discards_the_result`);
   falsified by rewiring the shipped 0.3.1 connection — the pin alone
   fails. **#26 is annotated in place.**
2. **MEDIUM — the derived amber index was unpinned**: seeding the fixed
   index back survived all 1500 tests while painting every Grid scale
   factor cell amber on a vertical job, and `TextAlignmentRole` was
   asserted nowhere. Both now pinned on a vertical job with a genuinely
   warned row (the frozen negative-σ position); falsified — the seed now
   fails exactly the two new tests.
3. **LOW, carried**: `WARNINGS_COLUMN` remains as the horizontal layout's
   documented constant (one pre-existing horizontal test uses it
   correctly); `vertical_mode_for`'s neither-checked branch is unreachable
   by construction; a post-run mode flip leaving the previous job's headers
   on the Multi table is the standing describe-the-written-archive
   behaviour, confirmed intentional.

**Suite: 1474 → 1503**, green in `pytest` and `-O`; the implementer's nine
falsifications, the gate's twelve seeds, and this round's three (the
longitude rewiring, the fixed amber index, the alignment set). Committed to
`main` and pushed; no release. WP-V9 remains: end-to-end + the frozen
self-test's vertical conversion, build gates, release notes, and the closing
gate over the whole feature.

### #42 — 2026-08-08 — WP-V7: the disclosure — every surface now says what was done to the height

**What was built** (plan §5, implemented by a work-package subagent to the
session lead's settled disclosure decisions, then gated): the job record's
vertical blocks (both datums under INPUT/OUTPUT, the OUTPUT statement that the
clean export's Z is in the target datum, a METHOD block quoting — wrapped,
never reworded — the registry's `direction_statement`, model + release, both
grid filenames and digests, the uncertainty citation, NGS's supersession
caveat, **the half-cell step disclosure (#38's decision, discharged)**, and a
Factor height paragraph for the #41 source-era configuration); the audit
CSV's six vertical-only columns (source/target datum, source elevation, shift,
σ, and `Geoid model` — closing #40 LOW 5 for the mode where two models can
answer differently; horizontal CSVs deliberately keep the 0.1.0 layout and
rely on the record, #17); the Single point panel's datum-labelled elevation
rows, shift row, **σ row with its own copy button, in Copy all** (plan §6's
pin); `WarningCode.VERTICAL_SIGMA_UNAVAILABLE` so the negative-σ absence is
SAID on every surface (#41's note, discharged); `formatting.vertical_metres`
(4 dp, rationale recorded); and the clean export pinned at **exactly five
fields in every vertical mode** with the round-trip gate independently
refusing a sixth. The negative-σ decision, on every surface: **N/A, never a
number** (#36's rule, held by four independent pins).

**The gate (independent Opus): FIX-FIRST.** It verified the disclosure
complete on the written deliverable across 11 job shapes (identity both ways,
geoid-none, source-era factors, coverage-refused, negative-σ, unit mixes),
hand-derived the record's σ summary from the committed grids
(0.0007/0.3656/0.1831 — character-exact), confirmed the direction statements
against the arithmetic in both directions, byte-diffed **27 horizontal
archive members against a HEAD worktree — all identical**, parsed every CSV
(28 cells header and rows alike), and seeded 18 defects with 18 caught.
Findings, all closed this round:

1. **HIGH — the Single point panel showed the modeled shift with no caveat
   anywhere**, on the one surface that writes no file — the condition #41's
   sequencing constraint exists to prevent, live on the tab WP-V8 is about
   to wire. Resolved with the **Vertical method row**: the transformation
   record's own words (model, release, MODELED-not-measured, the
   supersession caveat; the identity's own sentence for an identity), an
   ordinary row with a copy button that rides into Copy all so numbers
   leaving by clipboard take the caveat with them. Wording is the record's,
   not re-drafted, so the panel and the job record cannot disagree. Pinned
   (layout + content + clipboard), falsified. *Owner may re-word at the
   pre-release review; the decision that SOME caveat must be on-screen was
   the gate's condition for WP-V8 proceeding.*
2. **MEDIUM — the σ warning printed the raw error-model output at 18
   significant digits with a Python attribute path**, into the record and
   the screen — publishing the figure #36 deliberately kept behind a code
   accessor, beside which NCAT prints +0.011 where the raw figure is −0.00965.
   The raw figure and the accessor now live only on the reading's
   `sigma_unavailable_reason`, off every output. Pinned on the message, the
   record and the panel; falsified.
3. **MEDIUM — two record sentences claimed work not done** on jobs whose
   every point was blank-Z or coverage-refused ("each point's shift … are in
   the _full.csv export" over all-N/A cells; "factors were computed from the
   SOURCE-datum height" when no factor existed). Both guarded on work
   actually done, with an honest all-refused paragraph. Pinned, falsified.
4. **MEDIUM — assigned, not dropped: the Multi point tab's on-screen table**
   shows a shifted Z under a bare `Elevation` heading with no datum, shift
   or σ — a surface neither plan §5.2 nor §7's V8 scope enumerated. **WP-V8's
   scope now includes it**: the Elevation column header gains the datum and
   the table gains shift and σ columns on vertical jobs, mirroring the audit
   CSV (#26's cannot-disagree property is the pin to build).
5. **MEDIUM/LOW housekeeping**: `window.py`'s geoid-dropdown comment now
   cites WP-V8 (a half-applied correction); four future-tense comments
   settled (`selftest.py`'s lazy-imports note, `ngs_grid.py` and
   `vertcon.py`'s "is WP-V7's"); the factor-era rule is now stated ONCE —
   `job.factors_use_source_era` — and called by both the computation and the
   record, so the sentence and the arithmetic cannot drift (one
   authoritative representation); `_labelled_paragraph` no longer breaks
   long tokens, so a quoted URL cannot be snapped mid-token in a sealed
   record; one double blank line removed.
6. **LOW, carried with reasons**: a coverage-refused point's INPUT elevation
   label reads plain `Elevation` rather than naming the source datum —
   nothing false is printed and the warning names both datums.

**Suite: 1441 → 1474**, green in `pytest` and `-O`; the implementer's six
seeded falsifications plus the gate's 18 plus this round's two (the caveat
row and the raw-figure leak, each failing 3 pins). Committed to `main` and
pushed; no release. **The #41 sequencing constraint is satisfied: WP-V8 may
now make vertical mode reachable.**

### #41 — 2026-08-08 — WP-V6: the vertical shift reaches the job, and the geoid guard learns which era a height is in

**What was built** (plan §3.5–3.6, implemented by a work-package subagent to
the session lead's settled judgment calls, then gated): `VerticalMode` on
`JobSettings` (default `HORIZONTAL` — today's behaviour exactly, the GUI
toggle is WP-V8), both vertical datum fields with `None` as a statement, the
§3.6 ordering — **shift before geoid lookup before factors** — pinned by
recording what `factors_at` actually receives, `VerticalReading` on
`ConvertedPoint` (transformation record, applied shift, σ or a reason it is
unavailable — identity and negative-σ **distinguishable by construction**),
the coverage-refused per-point shape (horizontal stands, Z deliberately
absent, factors N/A, a warning that teaches), the settings refusal matrix
(missing datum, datum-on-horizontal, the registry's own two classes
propagating unwrapped, impostor guards on all three new fields), and the #38
longitude-boundary refusal — where the investigation found **the feared gap
was already closed**: `lambert._require_valid_geodetic` refused out-of-range
geodetics all along, so the new row-level refusal adds the row and the
convention to the message and changes no accepted range (proven: 34 boundary
cases behave identically to HEAD).

**End to end against NCAT**: 200.000 m NGVD 29 at 43.0 N / 84.5 W → 199.8598
through a real file → `job.run` → written ZIP, against NCAT's 199.860; all
20 forward anchors in one job; the five-point inverse set round-trips within
1e-9; the max-σ anchor carries σ ≈ 0.3656 per point. Both directions, four
unit paths.

**The gate (independent Opus): FIX-FIRST — the mathematics sound, the record
not.** It re-derived the sign from the raw `.trn` cell before touching
`job.run`, byte-compared five job configurations against a HEAD worktree
(15/15 output digests identical — the horizontal regression is exact), ran
the refusal matrix at 16 cases, confirmed the #38 claim independently, and
seeded 8 defects with 8 caught (one behaviourally-inert geoid-gate seed
verified inert, not missed). Findings, every one closed this round:

1. **HIGH — the job record called a populated Z field "Blank elevation
   field"** for a coverage-refused point: WP-R2 fix C's defect through a new
   door, unpinned because nothing in the suite read a vertical job's report.
   The ELEVATIONS section now has a **fourth bucket** — "Elevation recorded,
   but not convertible between vertical datums" — keyed on `row.elevation`,
   with wording that says the Z was read and deliberately not written.
   Pinned; falsified by reverting the bucketing.
2. **HIGH — a vertical job's Z moves ~0.46 ft and no output says so.**
   Acknowledged deferral, resolved as a **hard sequencing constraint**: WP-V7
   (the disclosure package) lands before WP-V8 (the GUI), in this same
   continuous build, so no build in which vertical mode is *reachable* can
   fail to state the datum, the shift and NGS's caveat. Vertical mode today
   is reachable from no interface (verified by the gate).
3. **MEDIUM — the record's "H = orthometric height from the input file" was
   made false by the shift.** Now "as used for the factors".
4. **MEDIUM — `VerticalReading` accepted a negative or NaN σ, an empty
   reason, and a string transformation.** All refused in `__post_init__`:
   `vertcon.sigma_is_physical` applied at its third site so the record and
   the reader cannot disagree, finiteness beside it, the empty-reason rule
   `VerticalTransformation` already applies to its own citation, and the
   #11-finding-1 guard on the transformation field. Falsified.
5. **MEDIUM — the geoid-vs-datum guard's rule superseded** (this amendment's
   substantive decision, superseding plan §3.5's fourth refusal). The plan
   compared the geoid model against the *target* datum alone, which would
   have refused NAVD88 → NGVD29 outright — dead-ending WP-V8's dropdowns for
   every NGVD 29 target with advice that named a geoid model that does not
   exist and a setting no interface offers. **The rule is now
   either-endpoint**: the model's datum must match the source or the target,
   and `_convert_row` computes the factors from **the height in the model's
   own era** — the shifted height when the target matches, the source height
   when the source does. For NAVD88 → NGVD29 that is *more* correct than the
   plan's rule, which would have combined a shifted NGVD 29 height with a
   NAVD 88 separation; the era mixing #32 forbids now never happens in any
   accepted configuration. What still refuses: a pair whose endpoints both
   differ from the model's datum — today exactly the NGVD29 → NGVD29
   identity job with a geoid model, whose refusal now gives achievable
   advice (horizontal mode). `geoid.require_geoid_matches_datum` remains as
   the one-datum primitive with its docstring saying production applies the
   derived rule; its own message no longer suggests the impossible.
   **Recorded asymmetry, deliberate:** a HORIZONTAL job performs the
   identical mixed-era arithmetic silently whenever its file happens to hold
   NGVD 29 heights — that is the owner's "horizontal mode unchanged, nothing
   asked, nothing tagged" decision (plan §1), and the guard governs only
   jobs that *declare* their datums. The gate measured the stake either way
   at ~0.02 ppm in the elevation factor; the guard is about the record being
   honest, not about the magnitude.
6. **LOW, all closed**: the datum-tag check gained its mirror (vertical
   settings arriving with NO transformation record refuse, rather than
   passing an unshifted height); coverage is now decided by
   `pair.contains` — asked, not caught — so a structural `VertconError`
   propagates loudly instead of being headlined as a coverage gap; the
   VERTCON pair argument is required, not silently defaulted, holding
   "loaded once per job" as a guarantee.
7. **Recorded, not fixed here**: a shifted height that lands within 0.0005
   of exactly 0.000 formats as `0.0000`, reads back as "not recorded", and
   the round-trip gate refuses the whole export — fail-closed, pre-existing
   class, not a Michigan case (Lake Erie ≈ 571 ft). **For WP-V7**: the
   negative-σ case carries its reason on the reading but raises no warning —
   the disclosure layer must not assume a warning already flags it. **For
   WP-V9**: the frozen self-test should convert one vertical point end to
   end once the GUI can reach the mode.

**Falsified this round beyond the implementer's own eight**: the report
bucketing, the factor-era override, the either-endpoint guard, the mirror
check, the σ-physicality check, and the structural-propagation behaviour —
each seeded, each failing exactly its own pin, the tree swept for leftover
seeds afterwards.

**Suite: 1397 → 1441**, green in `pytest` and `-O`. Committed to `main` and
pushed; no release — WP-V7 next, per finding 2's sequencing constraint.

### #40 — 2026-08-08 — WP-V5: the geoid model registry, and GEOID12B becomes real

**Two commits, as the plan required.** WP-V5a renamed `geoid18.py` to
`geoid.py` — `git mv`, byte-identical content, every reference updated by
word-boundary rewrite so the symbols carrying GEOID18 as a *model* name were
structurally untouchable. WP-V5b built the registry inside it.

**The anchors preceded the code, as V0's order requires.** Before any registry
existed, the session lead captured 20 GEOID12B anchors live from NGS's geoid
service at the exact positions of the 20 GEOID18 anchors — `model=13` never
assumed: every response names its own model and the capture harness
(`review/wp-v5-geoid12b/`, raw bodies committed) refuses a mismatch — and
verified the committed tile reproduces every figure through the INTG stencil
at worst **0.543 mm**, NGS's own printing floor. **18 of the 20 anchors differ
between the models at the printed millimetre**, which matters because the two
tiles are byte-for-byte the same size on the same geometry: the digest and the
anchors are the only things that can tell them apart. Frozen as
`tests/fixtures/geoid12b_anchors.py`.

**What was built** (plan §3.4 and the `geoid_model` half of §3.5):

- **`GeoidModel`** — name, tile filename, SHA-256, geometry, vertical datum,
  citation — with `GEOID18_MODEL` and `GEOID12B_MODEL` records,
  `ALL_GEOID_MODELS`, and `geoid_model_by_name` refusing unknowns by listing
  what it knows. The records are THE authoritative representation: the old
  module constants are derived aliases, pinned by identity, and each digest
  literal appears exactly once in production code. **The GEOID12B digest now
  lives in the runtime record the loader authenticates against** — the WP-V4
  gate's standing instruction, discharged.
- **`vertical_datum` on the record is load-bearing**: `require_geoid_matches_datum`
  refuses a geoid model applied against heights in a datum it is not for —
  #32's "two eras inside one number" — latent today (both models are NAVD 88),
  wired into `job.run` at WP-V6, guarded against the #11-finding-1 impostor
  class on both arguments.
- **`JobSettings.apply_geoid: bool` → `geoid_model: GeoidModel | None`**,
  default `GEOID18_MODEL`; `None` is the statement "no geoid was applied",
  kept as a core capability no interface offers (owner's "no none").
  `job.run` refuses `geoid_model=True` — the exact habit the retired bool
  leaves behind — by name, and refuses a non-registry record *before any
  point converts* (see the gate's LOW 1 below).
- **Per-model refusal dialect**: a GEOID12B refusal names GEOID12B — "outside
  the GEOID18 tile" for a lookup that consulted `g2012bu3.bin` would be a
  false statement — via a subclass so `dialect` stays the ClassVar the
  substrate declares and the suite pins.
- **The frozen bundle reads GEOID12B**: `check_geoid12b_tile` now loads
  through the registry and checks the frozen anchor at 44.2542 N / −85.4012 W
  → −33.285 m, constants transcribed and pinned `==` to the fixture. The
  spec's `NGS_GRID_FILENAMES` and the release manifest both derive from the
  registries, so a grid cannot be added without the bundle and the manifest
  following.
- **report.py**: the geoid block resolves the record through the registry —
  character-identical for GEOID18 jobs; a GEOID12B job cites its own tile and
  digest. One latent defect found by the rename: a geoid-disabled job's
  ELEVATIONS section claimed elevation-carrying points sat "outside the grid
  tile" when no grid was consulted at all; now an honest "no geoid model was
  applied" branch, pinned.

**The review gate (independent Opus): verdict MERGE, no CRITICAL, no HIGH.**
What it verified independently rather than trusting: **GEOID18 output
byte-identical** across five job configurations run side by side against the
pre-registry commit, every geoid-touching record branch fired; the GEOID12B
tile digest, geometry and **all 20 anchors reproduced by the reviewer's own
reader written from the format spec with no `michspc` import** (worst
0.543 mm, and the 18/20 discrimination claim confirmed); rename completeness;
one-authoritative-representation held; nine seeded defects all caught, four
by exactly the single pin claimed. Findings, all closed in the same pass:

1. **MEDIUM — this amendment did not exist yet** and §3's table still said
   GEOID12B was read by nothing. Fixed: §3 now records both API model ids
   and the registry.
2. **LOW — a hand-built `GeoidModel` converted a whole job and then died at
   the record write** with a bare `KeyError` (the loaders accept hand-built
   records on purpose — the suite reads tampered tiles through them — but
   `report.py` cites only registry members). `job.run` now refuses a
   non-registry record by name before converting; membership is by equality,
   so a record rebuilt with a registry model's exact facts is accepted —
   identical facts are the same model. Pinned, falsified.
3. **LOW — the anti-swap pin's recorded falsification was under-specified**:
   pointing only the GEOID12B record's filename at GEOID18's tile trips the
   digest check in fixture setup, so the pin's own assertion never ran — the
   #31 failure mode, caught by the gate re-running it properly. Re-falsified
   with the swap that passes BOTH authentication gates (filename and digest
   together): the pin's own assertion fails, 3 misses where 10 are required.
   The docstring now records the stronger seeding and why the weaker one
   proves the wrong thing.
4. **LOW — housekeeping**: the capture harness notes it ran pre-rename; the
   release manifest derives from the registries (it manifested GEOID18
   alone); `build_release.py`'s missing-grid advice no longer tells the
   reader to add a filename literal the spec deliberately no longer holds;
   the shipped-grid cache is bounded at 8 (its "bounded by the registry"
   claim was not enforceable — `default_grid` is public) and hand-built
   models get one cached class per name instead of a fresh type per call.
5. **LOW, recorded for WP-V7 rather than fixed**: `_full.csv` carries
   `Geoid height (m)` with no model column — model-dependent since this
   amendment, 32 mm apart between the models at the Houghton anchor.
   Mitigated by the ZIP travelling with the job record that names the model
   (#17); the disclosure decision belongs with WP-V7's others.

**The selftest's honest limit, disclosed where it lives:** the bundle anchor
check cannot catch a swapped tile — the models differ by only 1.2 mm at the
Cadillac anchor against a 2 mm tolerance. The suite-level anti-swap pin is
the real line, proven to discriminate under a fully-authenticating swap, and
the digest is checked twice in the bundle path besides.

**Suite: 1358 → 1397** across WP-V5 (V5a adds none — a rename may not — V5b
adds 38, the gate's fixes 1; #39's six glyph pins landed between them), green
in `pytest` and `-O`. Pushed to `main`; still no release — the owner reviews
first.

### #39 — 2026-08-08 — The copy glyph lost its bottom on every scaled display, and the suite could not see it

**Reported by the owner** — "the copy buttons might be getting cut off on the
edges in the results" — and reproduced by grabbing the real Single point tab on
the real `windows` platform rather than the offscreen one: at this machine's
125% display scale every copy button rendered the glyph with its bottom and
right edges missing, an "n" where two sheets belong.

**The defect, one ordering.** `copy_pixmap` stamped the device pixel ratio on
the pixmap **before** opening the painter. A `QPainter` on a pixmap that
already carries a ratio works in logical coordinates — it arrives pre-scaled
by the ratio — and the function then applied its own canvas scale
(`physical / CANVAS`) on top, so the two scales compounded: at 125% the
16-unit canvas mapped onto 17.5 device pixels of a 14-pixel pixmap, cutting
~20% off the bottom and right; at 150% a third; at 200% half. At 100% both
scales are 1.0 and the glyph is perfect — and the offscreen test platform runs
at ratio 1.0, which is why the suite's 12 glyph tests (including one named
`test_a_high_dpi_screen_gets_real_pixels_not_a_scaled_up_one`, which pinned
the pixmap's *dimensions* and never its content) stayed green for three
releases while every scaled Windows laptop showed the truncated glyph. **This
is #31's lesson again from a new direction**: the test platform's honest
difference from the shipped platform (there, font metrics; here, device pixel
ratio) turned a real defect invisible.

**The fix is to stamp the ratio after painting** — the painter then works in
device pixels, the canvas scale is the only scale, and the fractional-ratio
render becomes **byte-identical** to a 100%-display render of the same
physical size. That identity is the new pin: parametrized over ratios 1.25 /
1.5 / 2.0 and sizes 11 (the panel's actual `COPY_ICON_SIZE`) and 14, the
scaled image must equal the same-physical-size unscaled one exactly — no probe
positions to drift, no antialiasing tolerance to go stale. Falsified by
seeding the old ordering: all six parametrizations fail, nothing else does.
Verified visually on the real platform before and after via `QWidget.grab()`
of the actual panel.

`result_panel.py` is untouched; no layout, size or placement changed — the
buttons were never clipped by the layout (checked: every button sits at its
`sizeHint`, no horizontal scroll), only the picture inside them was cut.
Suite 1390 → 1396, green in both modes.

### #38 — 2026-08-07 — The merge gate: two independent Opus reviews before V0–V4 and WP-G1 reach main

**Why Opus reviewers:** the owner's standing instruction (2026-08-07, recorded
at #36's close) is Codex for gates, independent Opus reviewers if Codex usage
runs out. This session ran two Opus reviewers in parallel, briefed blind to
each other on different angles — one on numerical and algorithmic correctness,
one on contracts, tests, regression risk and process integrity — both
read-only, both against the full branch. Every finding below was verified by
the session lead before being acted on; both reviewers also independently
re-ran the load-bearing measurements rather than trusting the record.

**What the gate confirmed, independently of the record:** suite 1346/1348
green in both modes with exit codes read directly; the WP-V2 extraction
behaviour-identical to `origin/main`'s `geoid18.py` (bit-identical
interpolation over 200,000 positions, 69 refusal scenarios
character-identical); the VERTCON reader bit-identical to NOAA's published
`Vertcon.java` over the *whole* CONUS grid including clamp regions and 88,968
typed-coordinate half-cell positions the original 18,000-point sweep never
sampled; all four SHA-256 pins matching the committed bytes; sign, direction
and round-trip exact at every anchor (forward + reverse = exactly 0.0 at all
five inverse points, and over 8,000 further Michigan positions); the 20-anchor
pins strongly discriminating (a sign flip misses by 792 mm, every stencil
mutation caught); 10 of the 120 frozen geoid anchors re-queried live against
NGS and identical; and the negative-σ record accurate under independent test —
at 12 NCAT queries inside the negative region no candidate rule reproduces
NCAT, and at 14 positions just *outside* it agreement returns to NCAT's
printed quantization, so the disagreement is confined to exactly where
`sigma_m` refuses.

**HIGH (found by the numerical review, verified by the lead, live-confirmed
against NCAT): the nearest-node stencil is discontinuous, and nothing had said
so.** A 3×3 stencil centred on the nearest node switches cells at half-cell
lines — odd multiples of 0.025° on the VERTCON grids, exactly the round values
surveyors type — and the interpolated field jumps there. Measured across
Michigan: under 1 mm on three quarters of the lines, `.trn` worst **75.6 mm**
at 41.975 N / −83.935 W (2.2 m of ground), `.err` worst ~94 mm, re-anchored
GEOID18 ~6 mm. The floor-anchored scheme this program shipped through 0.3.1
switches stencils *at* nodes and is exactly continuous, so WP-V4 and WP-G1
both imported this property, and the anchoring tables presented nearest-node
as strictly better with no tradeoff named. **NCAT prints the same step** —
queried live at both sides of the 41.975 N pair: 200.168 / 200.244 from
200.000 NGVD 29 — and the reader is bit-identical to NOAA's published source,
so this is NOAA's behaviour and replicating NOAA (the owner's standing
instruction) carries it in; smoothing it would diverge from the authority at
exactly the positions NCAT can check. **Resolved as disclosure, not repair:**
the property, its magnitude and NOAA's sharing of it are now in
`interpolate_biquadratic_nearest_node`'s docstring, pinned executable in
`test_the_nearest_node_stencil_is_discontinuous_and_ncat_shares_the_jump`
with NGS truth frozen on both sides of the line, and **WP-V7's disclosure
decision now owns how a job whose points straddle such a line shows the step**
— alongside the negative-σ disclosure it already owns.

**MEDIUM, all fixed at the root this session:**

1. **`geoid18.default_grid` — the loader production actually calls — had no
   pin on its authentication wiring** (contracts review). All three seeded
   rewirings (both gates gone, checksum gone, geometry gone) left the suite
   green; the identical pin already existed for `vertcon.default_grids`, built
   by this very branch. The matching pin now exists
   (`test_the_cached_grid_comes_through_the_authenticated_path`), falsified by
   seeding the both-gates-gone variant. Pre-existing at 0.3.1, not introduced
   by the branch.
2. **The vertical registry's import guard could be deleted silently**
   (contracts review). The module promises it "refuses to import" when a
   required pair is lost; removing the module-level call kept every test
   green. Two pins now: the guard fires on a doctored registry, and an
   AST-walking test holds the call site itself — a commented-out call cannot
   pass. Falsified by seeding exactly that deletion.
3. **The frozen bundle carried three grids nothing authenticated and two
   modules nothing imported** (contracts review). The suite's digest pins
   check `data/`, not the bundle, so a grid corrupted during packaging passed
   all eight release gates; and `vertcon.py`/`vertical.py` were invisible to
   PyInstaller's analysis (imported by nothing yet), so the next installer
   would have shipped 4.9 MB of VERTCON data with no code able to read it.
   The self-test now authenticates all four grids from inside the bundle —
   the VERTCON pair fully loaded and checked against NCAT's anchor-22 figure,
   GEOID12B by digest — and `LAZY_IMPORTS` (which `michspc.spec` derives
   `hiddenimports` from) now declares `ngs_grid`, `vertcon` and `vertical`.
   Selftest constants transcribed from `tests/fixtures/vertcon_anchors.py`
   and pinned to it, per the standing convention.
4. **WP-G1's stated cost was understated** (numerical review): "~4 mm" is
   ~7 mm over the Michigan window, ~8 mm over the whole tile, at 300,000
   random positions each — verified by the lead before correcting #36/#37's
   figures in place. Wrong in the direction that flattered the change, which
   is why it is called out rather than silently amended.
5. **DESIGN.md's body was factually stale** (contracts review): §3 now cites
   VERTCON 3.0, GEOID12B and the NOAA interpolation sources; §9 now lists the
   four grids and the `review/` directory.

**LOW, fixed:** `VertconGridPair.contains` — a claimed defence with no pin —
is now tested to ask both grids; `test_the_pair_offers_no_way_to_take_half_a_reading`
renamed `..._through_itself` so the name no longer overclaims what #36 records
as mitigated-not-closed; the `GEOMETRY_TOLERANCE_DEG` comment's
"six orders of magnitude" corrected to seven; plan §2.5a consequences 2 and 3
annotated as superseded/resolved by WP-G1 (the same defect class #36 fixed at
§3.3/§5.1/§7 — one location it missed).

**LOW, recorded for the next work packages rather than fixed here:**

- **For WP-V6 (file wiring):** `to_east_longitude` accepts a 0–360 east
  longitude silently — `shift_m(43.0, 275.5)` equals `shift_m(43.0, -84.5)`
  byte-identically. It fails closed for the realistic positive-west mistake
  (84.5 lands outside the grid and refuses), but a CSV carrying 0–360
  longitudes would convert without complaint. The file layer's geodetic
  validation must decide the accepted longitude range *before* these readers
  see it. Pre-existing behaviour inherited from released `geoid18`.
- **For WP-V7 (disclosure):** `reading_at`'s `sigma=None` collapses "the
  model interpolated negative" into one signal; the GUI/record layer will
  need the distinction (the raw figure is reachable via
  `modeled_error_raw_m`). And WP-V7 now owns TWO disclosure decisions: the
  negative σ (#36) and the half-cell discontinuity (this amendment).

**A verification trap recorded for whoever repeats the discontinuity
measurement:** synthesising a boundary position as `slat + (k + 0.5) * dlat`
lands ~6e-14° on the *opposite side* of the half-cell line from the typed
decimal (`43.025`), which manufactures apparent 90 mm disagreements with NCAT
that are pure float artefact. Feed typed decimals, not synthesised ones.

**Suite after the gate's fixes: 1348 → 1358**, green in both `pytest` and
`-O`. Merged to `main` after this amendment; no release cut — the owner
reviews first.

### #37 — 2026-08-07 — WP-G1 executed: GEOID18 re-anchored to INTG's stencil

**The work package #36 specified is built.** `geoid18.GeoidGrid.height_biquadratic`
and with it `geoid_height` now read `ngs_grid.interpolate_biquadratic_nearest_node`
— the 3×3 stencil centred on the nearest node, which is what NGS's own INTG
program does (`irown = nint(...)` in `intg.f`) and what NOAA TM NOS NGS-84
describes. The change site is one call, exactly as #36 predicted; the work was
the anchors. Authority: the owner's 2026-08-07 instruction to replicate NOAA,
with the tiebreak that where NOAA's published program and NOAA's web service
disagree, **the published program governs**.

**The evidence was reproduced independently before the change, not inherited.**
The session lead re-ran the comparison from the committed truth capture
(`review/wp-v4-anchoring/geoid18_120_discriminating_points.json`) through the
production interpolators: floor rms 0.715 mm / 66 of 120 rounding to NGS's
printed figure, nearest-node rms 0.454 mm / 83 of 120 — matching #36's table to
the digit, with zero divergence between the capture's stored predictions and
what the production code computes at all 240 evaluations.

**The anchors #36 required now exist:**
`tests/fixtures/geoid_discriminating_anchors.py`, 120 NGS geoid-API truths
frozen verbatim from the committed capture, of which **36 discriminate exactly**:
the nearest-node stencil rounds to NGS's printed figure there and the
floor-anchored one does not. Two new pins in `tests/test_geoid.py`: the exact
round-to-NGS pin over the 36, and an aggregate pin holding both schemes' rms and
round counts over all 120 (so satisfying the 36 while degrading elsewhere would
still show). The fixture records the honest remainder in its own docstring: 19
of 120 round under floor and not under nearest-node — printing-boundary noise
against 36 the other way. `tests/test_vertcon.py`'s
`test_geoid18_keeps_the_other_anchoring`, which pinned the pre-decision status
quo, is rewritten as `test_geoid18_shares_vertcons_anchoring_since_wp_g1`: both
NGS products now read the same anchoring, `geoid_height` is checked against the
nearest-node interpolator at every one of the 20 original anchors, and the
20-anchor measurements (floor 0.595 mm, nearest 0.830 mm — floor fractionally
better there, inside the quantization noise) stay asserted as history, because
they are why discriminating anchors had to exist.

**Falsified before acceptance:** with `geoid_height` seeded back to the floor
stencil, all three pins fail — the 36-point exact pin on its first position, the
aggregate pin on rms (0.715 measured against the 0.454 required), and the
cross-product pin in `test_vertcon.py`. Restored, suite **1346 → 1348**, green in
`pytest` and `-O`.

**What it cost, measured:** worst change to a reported geoid separation
**~7 mm over the Michigan window and ~8 mm over the whole tile** — measured at
the #38 merge gate over 300,000 random positions each; #36's "~4 mm" was this
same quantity sampled less widely and is corrected, not confirmed. At the 20
frozen anchors the largest change is 0.83 mm; at the frozen self-test anchor
(Cadillac) 0.09 mm, far inside its 0.002 m tolerance; ~1e-9 in an elevation
factor. **No coordinate moves.** All figures sit far inside GEOID18's own
stated 30–60 mm model uncertainty. One property the change trades away is
recorded in #38: the nearest-node stencil is discontinuous at half-cell lines
(~6 mm at worst on this grid) where the floor anchoring was continuous —
NOAA's own algorithm shares the jumps, which is why replicating NOAA carries
them in.

**The caveat #36 required to survive, stated again rather than implied away:**
INTG's stencil is *not* the best fit to the NGS geoid API — a bicubic 4×4 is,
rms 0.409 mm against nearest-node's 0.454. The re-anchoring follows the owner's
published-program rule and `intg.f`'s documented reading of exactly this `.bin`
format; it does not claim to reproduce NGS's web service, whose engine is
undocumented. This paragraph also lives in
`geoid18.GeoidGrid.height_biquadratic`'s docstring.

**#8's status after this:** its decision — biquadratic over bilinear — stands;
its anchoring claim was corrected by #36; as of this amendment the shipped
anchoring **is** INTG's, so the correction is now historical rather than a
standing discrepancy. `ngs_grid.interpolate_biquadratic` (the floor-anchored
variant) remains in the module deliberately: it is what the discriminating pins
are shown failing against, and it is the recorded history of what 0.1.0 through
0.3.1 computed.

### #36 — 2026-08-07 — WP-V1 and WP-V4: the grids land, and the interpolation stencil was wrong

**Status: the vertical feature is HALF BUILT.** V0–V4 are done, gated under Codex
and pushed; V5–V9 are not. `docs/PLAN-vertical-datums.md` is still a proposal and
the sections of this document above the amendment log are unchanged.

**The block recorded in #35 was the container, not the work.** #35 said WP-V1
could not be done because `geodesy.noaa.gov` is refused by the container's egress
policy. Run on the owner's Windows machine, NOAA is reachable, and every
consequence #35 drew from that block dissolved.

**WP-V1.** All three files of plan §2.1 downloaded and **every SHA-256 matched the
pin**, so the committed files are byte-identical to what the V0 gate measured —
independent confirmation that §2.1 was recorded correctly. Committed unmodified
under NGS's own filenames (§3). `michspc.spec` names every grid in
`NGS_GRID_FILENAMES` and derives `datas` from that list; `tools/build_release.py`
compares the built bundle against `data/` rather than one hard-coded name, so a
grid added and forgotten fails the build. `installer/michspc.iss` needed no change
— it copies the bundle recursively — but its comment no longer claims the geoid
tile is the only data file.

**The anchor lattice is a RECREATION and the fixture says so.** The V0 scripts and
their coordinates were lost with that session's scratchpad. The new 20-point
lattice was seeded with every position the plan does record, so the recreation
could be *checked* against V0 rather than merely replacing it, and all six
reproduce — including the five-point inverse set, matching §2.4 to the last
printed digit and summing to exactly 0.000 m. **Two figures are not reproduced and
must not be cited as though they were:** §2.5's Kalamazoo and Lansing σ are at
coordinates V0 never recorded.

#### The finding: plan §2.5 was wrong, and the pin it asked for would have enshrined a defect

§2.5 said the `.trn` grid is read biquadratically and the `.err` grid
**bilinearly**, and §6 asked for a test that fails if the two are ever unified.

`ngs_grid.interpolate_biquadratic` anchors its 3×3 stencil at `int(row) - 1`,
which puts the target in the stencil's **upper interval** — the stencil reaches a
full cell below the point and none above it. Anchoring on the nearest node centres
it. Max absolute residual against the frozen NCAT lattice:

| Grid | floor-anchored | **nearest-node** | bilinear | nearest |
|---|---|---|---|---|
| `.trn` | 8.4573 mm | **0.4707 mm** | 17.7262 mm | 32.5466 mm |
| `.err` | 3.0416 mm | **0.4716 mm** | 4.5468 mm | 14.3214 mm |

**Both grids are biquadratic.** Centred, every one of the 20 anchors reproduces
NCAT's printed figure exactly on both grids, and all 40 residuals fall below
NCAT's own 0.5 mm printing quantization. §2.5's asymmetry was a real measurement
of an off-centre stencil: bilinear only beat "biquadratic" on `.err` because it
was racing a mis-anchored one. Confirmed at 40 further points chosen where the
schemes diverge most — nearest-node 40/40 exact, bilinear wrong by up to 46 mm.

**Measured four times independently** before acceptance: a measurement agent that
never saw the production code, the session lead, the implementer, and Codex — all
agreeing to four decimal places.

**Every figure in this amendment is reproducible from `review/wp-v4-anchoring/`**,
which carries the harnesses and the captured NGS truth data, with a README
mapping each claim to the script that proves it. That directory exists because
the narrowing re-confirmation caught this amendment citing experiments whose
harnesses had never been committed — a design-log claim nobody else could check,
which is the same defect this amendment records against the *plan* below. The
discriminating samples select positions using the grids and score them against
NGS, so selection is by predictor disagreement and the outcome is external; they
are good discrimination and **not** an unbiased estimate of typical error, which
is what the 20-anchor table in the suite is for.

**Then verified against NOAA's own source rather than only against its outputs.**
`Vertcon.java`'s `getGridRow`/`getGridColumn` were transcribed literally,
including Java's truncating `(int)` cast and integer division, and compared with
this reader over 18,000 Michigan positions spanning the half-cell boundary where
the stencil switches: **max difference exactly 0.000000000000 m.** The reader is
not close to NOAA's algorithm, it *is* NOAA's algorithm. `GridManager.java` also
shows NOAA's bilinear fallback fires only on a `MISSING_DATA_INDICATOR` of −999,
which these grids do not contain, so the biquadratic path is always taken here.

#### Amendment #8 is corrected, and GEOID18's anchoring is probably wrong

#8 states that NGS does not document INTG's interpolation scheme. **It does.**
NOAA TM NOS NGS-84, *Biquadratic Interpolation*, describes "the nearest 3×3 set of
grid points", and `intg.f` anchors with `irown = nint(...)` then reads
`irown-1, irown, irown+1`. Read directly from `ngs.noaa.gov`, not via a summary.

What #8 actually decided — biquadratic over bilinear — **survives**. What does not
is the claim that this program's *anchoring* is INTG's; it was repeated in three
docstrings and the 0.1.0 release notes, all corrected.

**GEOID18 was deliberately left on the old anchoring in this build.** Its 20
anchors cannot discriminate — quantized to 0.001 m, all candidates sit inside that
noise — but 120 points sampled where the anchorings diverge most reverse the
ranking (floor rms 0.715 mm against nearest-node 0.454). The cost of not changing
it is about 4 mm in a *reported geoid separation* and ~6e-10 in an elevation
factor, inside GEOID18's own 30–60 mm model uncertainty: **no coordinate moves.**
Re-anchoring released code deserved its own package rather than being folded into
a vertical-datum build.

**The owner has since decided it, and named the tiebreak.** Instructed 2026-08-07:
replicate NOAA, they are the authority; and where NOAA's published program and
NOAA's web service disagree — as they do for the geoid, whose API matches neither
scheme and is best fitted by a bicubic — **use the published program.**

**LOGGED, NOT EXECUTED — the owner's instruction at the close of this session.**
No line of `geoid18.py` or `ngs_grid.py` was re-anchored here. What follows is the
specification for the work package that will do it, recorded now while the
measurements are fresh.

#### WP-G1 (specified, not built) — re-anchor GEOID18 to INTG's stencil

**The change.** `geoid_height` and `GeoidGrid.height_biquadratic` move from
`interpolate_biquadratic` to `interpolate_biquadratic_nearest_node`, which already
exists and is already exercised by the VERTCON reader. `ngs_grid` needs no new
code. The floor-anchored method stays, because removing it would delete the thing
the new anchors have to be shown failing against.

**The evidence, all of it already captured** in `review/wp-v4-anchoring/`:

| | max | mean | rms | rounds to NGS |
|---|---|---|---|---|
| floor-anchored (ships today) | 2.177 mm | 0.556 | **0.715** | 66/120 |
| **nearest-node (INTG)** | 1.368 mm | 0.368 | **0.454** | 83/120 |
| bicubic 4×4 | 1.136 mm | 0.328 | 0.409 | 91/120 |
| bilinear | 2.510 mm | 0.804 | 0.942 | 37/120 |

over 120 points sampled where the anchorings diverge — fractional cell position
0.9, highest-curvature Michigan cells. Against the 20 frozen anchors all four
schemes sit inside the 0.001 m quantization and nothing can be concluded.

**The honest caveat, which must survive into the amendment that supersedes #8:**
INTG's stencil is *not* the best fit to the NGS geoid API — a bicubic is, and by a
visible margin. This is done because the owner ruled that the published program
governs where NOAA's two answers differ, and because `intg.f` is the documented
reader for exactly this `.bin` format while the API's engine is undocumented.
Chasing the API would mean guessing at it. **Say so in the record rather than
implying INTG reproduces NGS's service.**

**What must NOT be reused: the existing 20 anchors cannot gate this change.**
`tests/fixtures/geoid_anchors.py` cannot tell the schemes apart — 16 of its 20
positions differ between them at all, and `tests/test_geoid.py`'s 1 mm tolerance
admits both — so the geoid suite passes with `geoid_height` re-anchored either
way. That is a #31-class pin that has stopped discriminating, and it was found by
seeding exactly that defect. **New anchors must be frozen at max-divergence
positions with an exact round-to-NGS pin**, and the 120-point capture in
`review/wp-v4-anchoring/geoid18_120_discriminating_points.json` already holds NGS
truth for such positions.

**What it costs and does not cost.** Worst measured change to a *reported geoid
separation* is about 4 mm, in the roughest cells; roughly 6e-10 in an elevation
factor, which is nothing. Both figures are far inside GEOID18's own stated 30–60 mm
model uncertainty. **No coordinate moves and no combined factor changes
meaningfully** — this is a disclosure-accuracy improvement, not a correction to a
survey result. It is nevertheless a change to released computation, so it takes
its own commit, its own falsified pins and its own gate, and it must not be
folded into a vertical-datum package.

**Ordering.** WP-V5 renames `geoid18.py` to `geoid.py` and builds the geoid model
registry inside it. Doing WP-G1 **first** means the rename lands on settled code;
doing them in parallel means two sessions editing a file one of them renames.

#### The Codex gate: verdict FIX, one HIGH, three MEDIUM, two LOW, no CRITICAL

Codex independently confirmed the sign and direction — the defect class #1 records
— and confirmed the anchoring conclusion is sound and its sampling not circular.

**HIGH — a negative value was returned as a one-sigma uncertainty.** The `.err`
grid interpolates below zero at ~0.43% of Michigan positions (956 of 223,850
sampled, worst −0.027 m). A negative one-sigma is not a quantity. `sigma_m` now
**refuses**, naming the position and the value and stating that **the shift itself
is valid and unaffected**, so a caller cannot conclude the elevation is bad;
`modeled_error_raw_m` keeps the unfiltered output under a name that cannot be
mistaken for an uncertainty; `reading_at` still reports the shift with the sigma
marked unavailable, the shape `job.py` already uses for a missing geoid height.

**Why not simply match NCAT.** NOAA's own published source produces these
negatives too — `Vertcon.java` applies no clamp, floor or `abs` to the error grid
— yet the live service returns +0.011 m at 42.475 N / 83.125 W where both NOAA's
algorithm and this reader give −0.00965 m. **NOAA's source and NOAA's service
disagree there and no rule maps one to the other.** Refusing is the only option
that neither invents a number nor hides the disagreement. All three paper-overs —
return it, clamp it, `abs()` it — are pinned as failures. **The disclosure
decision belongs to WP-V7 and is the owner's.**

**MEDIUM — the GEOID12B checksum could not fail.** `michspc.spec` claimed the file
and its digest landed together but stored only the filename; the digest lived only
in the plan. Altering one payload float passed every executable check. Now pinned
as `geoid18.GEOID12B_TILE_SHA256`, with a test that the file matches it and a
second that the two geoid pins are two pins — the tiles are byte-for-byte the same
size, so pinning GEOID18's digest twice would leave GEOID12B unauthenticated with
nothing to notice.

**MEDIUM — docstrings cited evidence the repo did not hold.** The 40-point
experiment and the 223,850-position sweep were described but their coordinates
were not committed. Added an offline scheme-separation pin at the reviewer's own
uncovered position, 42.87 N / 83.81 W, checkable from the committed grids with no
network.

**MEDIUM — the plan still instructed downstream work to use the superseded
algorithm**, at §3.3, §5.1 and the §7 table, despite the banner. A later package
following it literally would have reintroduced the defect. Corrected in place; the
superseded text stays visible where it is historically useful, as §2.6 does for
the VDatum wrong turn, but no sentence still reads as an instruction.

**LOW — the pair API** let a caller combine a shift at one position with a sigma
at another, understating uncertainty by up to 0.365 m with both numbers looking
plausible. The pair-level `shift_m` and `sigma_m` were removed and `reading_at`
is now the only value method on `VertconGridPair`. **The fix is real but partial,
and the docstrings must not claim more:** `.transformation` and `.uncertainty`
remain public, so `pair.transformation.shift_m(A)` beside
`pair.uncertainty.sigma_m(B)` still reproduces the mistake one attribute deeper.
Making that structurally impossible would mean hiding the two grids, which the
suite legitimately exercises one at a time. Recorded as mitigated, not closed.

**LOW — the bytes-consumed refusal was unreachable.** The header-derived length
check forces it. Removed along with the claim: a refusal that cannot fire is worse
than none, because it reads as a defence being kept. The property is not lost —
the suite walks both shipped files independently of this reader.

**Verification.** Suite **1223 → 1346**, green in `pytest` and `-O`. Eight seeded
defects at the fix stage, all caught, including all three ways of papering over
the negative sigma. Plan §2.7's Michigan window figures re-measured from the
committed grids and reproducing exactly, at the same two nodes.

**Two plan figures corrected.** The shift at the max-σ point is **−0.1435 m**, not
§2.8's −0.1466: that point is an exact grid node, so no interpolation is involved,
and NCAT independently returns −0.144. The ratio is **255%** of the shift, not
249%, and that sentence is quoted verbatim into the job record. And §2.7 vs §2.8
on the σ floor was **never a conflict** — 0.000004 m is the grid's own minimum,
0.001 m is NCAT's print resolution; at 43.0 N / 84.5 W the grid holds 0.00065542
where NCAT shows 0.001. **This closes the question #35 left open for the owner.**

**A trap worth remembering, and it generalises #34.** A PowerShell
`Get-Content -Raw` / `WriteAllText` round-trip used to seed a falsification
silently mangled six em-dashes in `michspc.spec`. #34 recorded `Set-Content`;
the rule is broader — **any** read-modify-write through PowerShell re-encodes.
Caught by byte-counting the file, not by a test, exactly as #34 predicts.

### #35 — 2026-08-07 — The vertical build starts: WP-V2 and WP-V3, and the two work packages that cannot be built off Windows

**Status: the vertical feature is STARTED, not finished, and `docs/PLAN-vertical-datums.md`
is still a proposal — the sections of this document above the amendment log are
unchanged.** Two of its ten work packages are built, gated and committed. The rest
are blocked, and the reason is environmental rather than technical, which is why it
is recorded here rather than left as a note in a session log.

**What landed.**

- **WP-V2 — `michspc/fileio/ngs_grid.py`.** The substrate shared by the GEOID18
  reader and the VERTCON reader WP-V4 will add: the `<4d3i` header record,
  `TileGeometry` and the canonical-geometry check, the generic header refusals, the
  0–360 east conversion, `lagrange3`, both interpolators, and the non-finite payload
  refusal. `geoid18.py` is now a thin **policy** layer over it — filename, checksum,
  geometry, model name, interpolation choice, and the wording of every refusal.
- **WP-V3 — `michspc/spc/vertical.py`.** `VerticalDatum` (NGVD29 and NAVD88 usable,
  NAPGD2022 declared-not-usable, mirroring `NATRF2022` in `frames.py`),
  `VerticalTransformation`, the registry keyed by `(source, target)` with both
  identity pairs as explicit records, `require_vertical_pair` with two distinct
  refusals, and `signed_shift` / `apply_shift`. Stdlib only; the grid value is a
  parameter, exactly as `factors.factors_at` takes the geoid height.

**The extraction problem, and its solution.** `job.py` catches `geoid18.GeoidError`
by name, so a refusal raised inside a shared substrate has to *be* that class — not a
base of it and not a sibling. The substrate therefore defines **no exception at all**;
a policy layer hands down a frozen `GridDialect` carrying its exception class and the
model-specific wording of each refusal. A shared base class was tried and rejected by
measurement: it breaks 24 geoid tests. The wording seam matters as much as the class —
a structural check shared by two readers would otherwise have to speak generically,
and this project's refusals are meant to teach.

**The extraction was proved behaviour-preserving, not asserted to be.** Its stated
safety property is that `tests/test_geoid.py` passes byte-unchanged, and it does — but
a passing suite only covers what it covers. Both the old and new modules were loaded
side by side and compared directly: **every refusal message character-identical across
37 constructed failure scenarios** plus 14 outside-the-tile positions; **check ORDER
unchanged** under 8 inputs built to violate two rules at once, since an earlier refusal
masks a later one; `GeoidError` the exact class on all 12 raise sites, which map 1:1
old to new; and **both interpolators bit-identical (max difference exactly 0.0)** over
200,000 random positions, a 2,499-point synthetic lattice including every node, edge
and corner, and 3,600 Michigan positions on the real shipped tile — the last of these
re-run independently by the session lead.

**The sign convention was re-derived independently before anything was accepted.** The
grid stores `NAVD88 − NGVD29` in metres and it is ADDED to the source height. Against
#22's live NCAT anchor — 200.000 m NGVD 29 at 43.0 N / 84.5 W → **199.860 m** NAVD 88 —
`sign = +1` gives 199.8598 with our grid's −0.1402, 0.2 mm from NCAT, which prints only
to the millimetre. `sign = −1` returns 200.0000 exactly, matching plan §2.4's 0.00 mm
round trip. `grid_quantity` reports "NAVD88 minus NGVD29" from **both** records, which
is correct because it is one grid; and it is derived from `sign` rather than stored, so
`direction_statement` — the sentence the job record will quote — cannot drift from the
arithmetic the program performs. This is the defect class of #1 / MATLAB defect 2, and
it is now pinned before the reader that will feed it exists.

**Review gate: THE REVIEWER WAS SUBSTITUTED, and that is disclosed rather than
glossed.** #1 records Codex CLI as the independent adversarial reviewer at both gates.
This session ran in a Linux container with no `codex` binary, no `~/.codex`, and no
credential to authenticate one (`@openai/codex` 0.147.0 is installable from npm; there
is nothing to log it in with). Plan §7 anticipated exactly this and required the
substitution be recorded. Two independent adversarial reviewers were used instead,
briefed blind to the implementers' reasoning and on different models — one on the sign
convention and the registry, one solely on proving the extraction changed nothing.
**This is weaker than the standing method**, because both reviewers share a model
family with the implementers, and the closing gate for this feature should be run under
Codex on the owner's machine before any of it ships.

**Findings: one MEDIUM, two LOW. All three fixed at the root, each pinned with the
reviewer's own counterexample, each pin falsified.**

1. **MEDIUM — a non-datum record duck-typed into `require_vertical_pair`.** Every
   record in this core carries `code`, `name` and `citation`, so
   `require_vertical_pair(frames.NAD83_2011, NAVD88)`, and the same with a `Zone` or a
   `LinearUnit`, passed `_canonical` unremarked and failed several lines later on
   `.is_usable` — as an `AttributeError`, which names nothing and walks straight
   through the `except VerticalDatumError` this module's own docstring tells callers
   to write. **This is #11 finding 1 recurring in a new module**: the same duck-typing,
   against the same three-field shape, whose fix in `convert.project_point` is an
   `isinstance` guard. That guard now exists here. Pinned against all three impostor
   types *and* against a forged record carrying both `code` and a truthy `is_usable`,
   so the refusal does not depend on the impostor happening to lack a field.
   Falsified: removing the guard fails 4 tests.
2. **LOW — `ngs_grid.py` claimed to carry "no wording that names a model", and its own
   prose contradicted it.** The claim worth holding is narrower: no **message a user
   reads** may name a model, because such a message is wrong for the substrate's other
   caller. Comments may and must name the file a constant was measured against, or the
   constant becomes uncited (§7). The docstring now says that, and
   `test_no_refusal_message_names_a_model` walks the AST of every `raise` in the module
   to hold it. Falsified: seeding "GEOID18" into one refusal fails it.
3. **LOW — the plan disagrees with itself about the σ floor, and the looser figure was
   heading for the job record.** Plan §2.8 says σ runs "0.001 m to 0.366 m"; §2.7's
   direct scan of the `.err` grid over the same Michigan window gives **+0.000004 m to
   +0.365599 m**. `uncertainty_citation` is quoted verbatim into the record (plan
   §5.2), so it now states §2.7's measured range — what this program's own reader can
   actually produce — and both the constant and its pin say why. **0.001 m is NCAT's
   printed resolution, not a value the grid holds.** *Open for the owner: confirm §2.7
   is authoritative, and correct §2.8 if so.* The 249% headline fact is unaffected and
   both sections agree on it (0.3656 / 0.1466 = 2.494).

One further citation was softened rather than left overstated: #22 names NCAT's
`inVertDatum` / `outVertDatum` **parameters**, not their permitted values, so the datum
codes are recorded as a convention chosen to match NCAT and to be confirmed against it
when WP-V1 freezes the anchors — not as a quoted token list.

**Suite: 1132 → 1223.** WP-V2 added 39 tests, WP-V3 added 52. Green in both `pytest`
and `-O`. Every new pin was falsified by seeding the defect it catches, and every
seed-and-restore was verified by SHA-256 afterwards rather than by eye, because #34's
trap was an encoding change no test could see.

**BLOCKED, and blocked on data rather than on effort. WP-V1 cannot be done anywhere
but the owner's machine.** This session's egress policy refuses `geodesy.noaa.gov`
outright — every NOAA host, 403 on CONNECT. Three consequences, all of which stop the
build here rather than slowing it:

- The three files WP-V1 commits — `vertcon_3.0_20190601.ngvd29.navd88.conus.oht.trn.b`,
  `…err.b`, and `g2012bu3.bin` — cannot be fetched. Plan §2.1 requires them unmodified
  under NGS's own filenames; GitHub carries neither, and a re-projected mirror would
  not satisfy the SHA-256 pin.
- **NCAT cannot be reached, so the frozen anchor lattice cannot be recreated.** Plan §2
  records the V0 scripts as living in that session's scratchpad rather than the repo,
  and that scratchpad was the owner's Windows machine. What survives in the plan is
  summary statistics plus the 43.0 N / 84.5 W anchor, the five-point inverse set and
  two σ readings — **not the 20-point lattice §6 requires as fixtures.**
- Therefore **WP-V4 was deliberately not built.** Its reader could have been written and
  structurally tested against synthesized `.b` files, but §1's tier does not permit
  shipping the module where a sign or scale error hides with no external anchor under
  it. §8 risk 3 exists to prevent precisely that, and V0 was run first precisely so the
  anchors would precede the code. Building it now would invert that order.
- **WP-V5's visible half is blocked too**: the geoid dropdown the owner asked for is
  GEOID18 **and** GEOID12B, and `g2012bu3.bin` is one of the three unreachable files. A
  one-entry dropdown is not the instruction.

Recorded also because it will recur: the three `tests/test_fileio.py::test_r3_3_*`
tests fail on any POSIX machine. That is not a defect and not new — it is the load-bearing
platform dependency **#20** already states, that the no-clobber commit relies on Windows
`os.rename` refusing an existing target while POSIX `rename` replaces silently. On
Windows the suite is 1223 green.

### #34 — 2026-08-07 — Three tooltips removed from the entry controls (0.3.1)

Owner's instruction. Removed, on both tabs where the control appears on both:

1. **The longitude sign dropdown** (`controls.longitude_combo`) — carried #28's
   worked example (`-84.37` / `84.37`) and #29's *"Files from OPUS, NCAT, GPS
   receivers and GIS software are normally negative west - CHECK THIS AGAINST
   THE FILE."* **This helper builds the control for the file tab and the Single
   point tab both**, so the removal reaches both, which is what the owner chose
   when asked. Keeping one tab's tooltip and not the other's would have put two
   different explanations of one control in one program, against #17's standing
   rule of one wording in both surfaces.
2. **The angle-format dropdown** (`single_point.ANGLE_FORMAT_TOOLTIP`, deleted)
   — said the choice governs what is TYPED only.
3. **Both hemisphere letter boxes** (`dms_entry`) — said Michigan is always N
   and W.

**What is gone is text, not information.** The longitude control still names the
convention in words before Convert is pressed; the job record still states it on
its own line and in the input and export descriptions; `job.run` still refuses a
geodetic job with no convention, in a sentence carrying the 340 miles; the
hemisphere boxes still show their letter; the format dropdown still names both
formats. Nothing about any conversion changed, and no output file changed.

**This supersedes one sentence of #33**, written the same day, which listed the
tooltip among the mitigations for the positive-west preselect. That mitigation is
withdrawn by the owner under the same ruling #33 records: verifying the
convention is the user's responsibility. The remaining mitigations there stand.
#29's account of adding the sentence is history and is left as written.

**Pinned, because deleted text grows back.** Each of these explained a control
that answers a question for the user, so the next reader who notices that will
reach for a tooltip in good faith. `test_the_longitude_dropdown_has_no_tooltip`
and `test_the_coordinate_entry_carries_no_tooltips` assert emptiness on both
tabs — deliberately overlapping on the shared longitude control, so that a future
change giving the Single point tab its own instance cannot slip past a pin that
only looks at the other tab. Both check the control still says what it is, so
they cannot be satisfied by deleting the control itself.

**Falsified**: with a tooltip seeded back on the longitude combo and on the
hemisphere box, both tests fail. Suite 1131 → 1132 (one tooltip-content test
retired, two emptiness pins added).

**A near-miss worth recording, in the suite's own tooling rather than the
program.** The seeding was done with PowerShell `Set-Content`, which on 5.1 reads
as ANSI and writes UTF-8 with a BOM — it added a BOM to `controls.py` and
`dms_entry.py` and mangled every em-dash and degree symbol in them. The suite
stayed green throughout, because Python accepts a BOM and the corruption was
confined to prose. Caught by reading the diff stat: two files showed roughly
three times the churn the edit accounted for. Both were restored from HEAD and
re-edited with a tool that preserves encoding. TOOLING.md already warns about
this exact trap; the lesson is that it applies to throwaway seeding commands too,
where the file is expected to be thrown away and the diff therefore goes unread.

### #33 — 2026-08-07 — The positive-west preselect: closed, not a concern

Owner's ruling at the close of 0.3.0, in his words: he is **not** concerned about
the positive-west preselect, and **verifying the convention is the user's
responsibility.**

This closes the standing item raised at #29 and carried through the 0.3.0
release. The facts behind the concern are unchanged and are not being disputed
away: OPUS, NCAT, GPS and GIS files are normally negative west, the two
conventions are indistinguishable from the number alone, and the wrong one moves
a Michigan point about 340 miles. What is settled is what this program does about
it — **it informs, and it does not decide.** The dropdown names the convention in
words before Convert is pressed, its tooltip carries the warning in capitals, the
job record states the convention in force, and the release notes lead with it.
The surveyor checks it against the file in front of him, as he checks a datum or
a unit.

> **Superseded in part by #34, later the same day: the tooltip is gone**, on the
> owner's instruction and under this same ruling. Strike it from the list above;
> the dropdown's wording, the job record and `job.run`'s refusal all stand.

**Recorded so it is not refiled.** This item has now been raised three times —
at #29, before the release, and after it. A reviewer who reaches for it again
should find this decision rather than open it a fourth time. Reopening needs new
evidence, not the same argument: a wrong conversion that actually reached a
drawing would be that evidence.

Nothing changed in the program. This amendment is the decision only.

### #32 — 2026-08-07 — Roadmap: vertical datums are the next build

Owner's decision at the close of the 0.3.0 release. Recorded here because it
settles an ordering that #21 and #22 left open — both were sized and neither was
chosen.

**Next: elevation conversion, NGVD 29 → NAVD 88.** The sizing stands as written
in **#22** and does not need redoing: MEDIUM, two work packages, every input
available today (VERTCON 3.0 grids in the same NGS `.b` family as the GEOID18
tile already read here, NCAT carrying the transformation for frozen anchors).
Its two risks stand too, and neither is about effort — the disclosure of a
*modeled* shift into a number that looks exact, and the sign/direction semantics
of the `trn` grid, which is the defect class this project has already been burned
by (#1, MATLAB defect 2).

**After it: NAPGD2022,** which #22 established is blocked on NGS rather than on
us. It arrives through the vertical-transformation registry as a record plus
grids plus a citation — which is the reason to build that registry rather than a
single hard-wired NGVD-to-NAVD path, even though only one pair exists today.

**And with it, backwards compatibility, stated as a requirement rather than
assumed.** NAPGD2022 support does not retire NAVD 88 or NGVD 29. A job converted
under this program in 2026 must still convert, and still reproduce, after the new
datum lands — a surveyor's older work does not stop existing because NGS
published something. Practically that means the registry keeps every published
pair it has ever carried, elevations stay datum-tagged so an old file says what
it meant, and the datum in force is named in every output. A conversion whose
datum cannot be established refuses; it does not assume the newest.

**SPCS2022 (#21) is not next — and it is not a parallel track either. It is
downstream of NAPGD2022.** Owner's correction, recorded because the first draft
of this amendment listed the two as separate items and that understates the
dependency.

The modernized NSRS has two halves and they arrive together. SPCS2022
*coordinates* are defined on **NATRF2022**, the terrestrial frame — #21's recon
says so directly, 19 Michigan zones on NATRF2022. **NAPGD2022** is the
geopotential half: GEOID2022 replacing GEOID18, replacing NAVD 88 as the height
datum.

For **this** program the coupling is concrete rather than administrative,
because this program does not merely project a point — it reports an elevation
factor and a combined factor. #22 already records that GEOID2022 replaces
GEOID18 in that factor chain when it lands. So an SPCS2022 conversion carrying a
GEOID18/NAVD 88 elevation factor would be **mixing two eras inside a single
number**, which is the same class of silent error the frame refusal exists to
prevent, one level down. Michigan's 2022 layer sharpens it: 18 of the 19 zones
are low-distortion projections designed at a topographic height — grid ≈ ground
at the design height — so the height side is load-bearing there, not incidental.

Hence the ordering in this amendment is a **dependency order, not a preference**:
the vertical work builds the registry, NAPGD2022 arrives through that registry,
and SPCS2022 needs both halves before this program could write a conversion it
would stand behind. SPCS2022's other blockers from #21 are unchanged and
independent of all this — no official NAD83(2011)→NATRF2022 transformation, and
the transverse and oblique Mercator engines this program does not have.

Nothing is built here. This is an ordering, and the two sizings it points at are
#21 and #22.

### #31 — 2026-08-07 — A pin that measured the test platform, not the program

Found by the 0.3.0 release build: gate 3 refused, one failing test, on a
release whose only change was the version literal.

`test_the_copy_button_does_not_tower_over_the_value_it_copies` (#28 note 1)
compared the copy button's height against `value.fontMetrics().height()`. The
suite runs under the **offscreen** platform plugin, which has no system font and
no text rasteriser. It answers **12 px for every family** — including `Segoe UI`
requested by name — where the Windows plugin answers **16** for that same font
at the same 9 pt and the same 96 dpi. The button's height comes from the style
rather than from the text, so it does not move with any of this: 18 px offscreen
and 19 on Windows.

Measured, per platform, glyph → button height, against the pin's allowance of
one frame:

| line height | 11 px glyph (shipped) | 14 px glyph (#28 replaced) |
|---|---|---|
| offscreen, this machine — 12 | 18, **fails** | 21, fails |
| offscreen, machine of origin — 14 | 18, fails | 21, fails |
| **Windows, as shipped — 16** | **19, passes** | 22, **fails** |

So the pin was only ever discriminating by accident, and on this machine it
rejected the fix and the defect alike. **No relative pin can work here**: to pass
the 11 px glyph and fail the 14 px one, the allowance must be at least 6 px
offscreen and under 6 on Windows. The two frames of reference do not correspond,
because one of them is not rendering text.

**Fixed in the test, and deliberately not in the program.** `SHIPPED_LINE_HEIGHT
= 16` states the line of text the panel is actually drawn in — Segoe UI 9 pt,
96 dpi, inherited, since nothing in `michspc.gui` sets a font — and the button is
measured against that. Stating a metric is against this file's usual rule, which
is why the constant carries the whole argument above. The alternative root fix,
constraining the button's height in `result_panel` so the relationship holds on
any platform by construction, was **rejected for this release**: it changes what
the owner has already approved on screen and risks clipping the glyph under a
larger system font or a scaled display, which is not a thing to do while cutting
a release. Recorded as available if the pin ever needs to be relative again.

The loop also gained a guard that the panel laid out any rows at all: it was
satisfied by an empty panel, a pass that means nothing.

**Falsified.** With `COPY_ICON_SIZE` seeded back to 14 the pin fails on 21 ≤ 20;
restored to 11 it passes on 19 ≤ 20. `result_panel.py` is byte-identical to its
committed state — no shipped pixel changed, and no coordinate was ever in reach
of this.

### #30 — 2026-08-07 — Warnings get their own field; display punctuation

Five owner directives, all interface. The third and fourth introduce the first
formatters in this program that write pixels and not files, and that separation
is the load-bearing part of this amendment.

**1. The lat/long entry selector loses its worked example.** `Decimal degrees
(43.800)` → `Decimal degrees`. The same edit #28 made to the longitude sign
entries, for the same reason: the parenthesis taught nothing the changing shape
of the boxes does not.

**2. The longitude sign list is reordered, positive west first.** Declaration
order in `LongitudeConvention` is what the dropdown offers — `longitude_combo`
iterates the enum rather than carrying a list of its own — so member order is a
user-visible fact and is pinned as one. Nothing branches on it; `to_signed` and
`from_signed` test identity.

**3. Warnings move to a full-width field beneath the results panel.**

They were the last row of the right-hand OUTPUT column, where a paragraph sat in
a column sized for coordinates. Now they have a `Warnings` box of their own,
spanning the tab, between the panel and the status line.

**No copy button, and not in Copy all** — his instruction, and it follows from
what the clipboard is for here: the numbers go into CAD or a spreadsheet, and a
two-paragraph warning dropped among them has to be deleted there. The text is
still selectable with the mouse, which is reading rather than a copy control.

`single_point_sections` no longer builds a warnings row, so
`single_point_clipboard_text` — which serialises those sections and nothing
else — drops them without a special case. The text comes from
`single_point_warnings`, a new accessor over the same `_warnings_text` the
sections used to call, so moving the display did not create a second account of
what a warning says.

**A defect found by looking at it, not by a test.** A word-wrapped `QLabel` does
not propagate height-for-width out through a `QGroupBox`'s layout: the box took
the height of one line and clipped the rest, so a three-warning conversion
showed one sentence with nothing on screen saying two more existed — in the one
field whose entire job is to say something is wrong. Fixed with a bounded scroll
area: nothing is hidden, the text is all reachable, and the field cannot grow
until it pushes the coordinates off a laptop screen. Pinned by measuring the
label's laid-out height against the height its own text needs at its own width.

**4. The decimal latitude and longitude carry a degree symbol; the convergence
angle is shown in DMS notation.** `43.80000000°` and `-16°49'17.78"`.

**These are display-only formatters, and that is not fussiness.**
`formatting.latitude` and `longitude` write the clean PNEZD export's columns two
and three, and that file is read back by `pnezd` before the archive may take its
name (`exports._verify_archive`). `float("43.80000000°")` raises — so a symbol
in the file formatter would not merely look wrong, it would make **every
geodetic job refuse to write**, and any file that did survive would be one no
CAD package could import. `angle_dms` likewise writes the audit CSV's
Convergence column and the job record.

So `latitude_display`, `longitude_display` and `convergence_display` are built
**on top of** the file formatters' own output rather than reimplementing the
number. The screen and the file therefore cannot disagree about a digit; they
differ in punctuation only, and the agreement tests normalise the punctuation
and still demand equality rather than skipping those rows. `convergence_display`
is built on `_dms_magnitude`, the single definition of symbol notation in the
program, so the three angles on the panel cannot come to punctuate themselves
differently.

The symbol appears on the INPUT block — which is what the owner named — and on
the OUTPUT block, because both are built by `_geodetic_values` and one section
showing `43.8` while the other showed `43.8°` would be two notations for one
quantity on one screen.

**Verification.** Suite **1120 → 1128**, green in both modes; the frozen-bundle
self-test passes. Five seeded defects, all caught: the degree symbol moved into
the file formatter (which fails 12 export and round-trip tests, exactly as the
argument above predicts), warnings restored to the OUTPUT section, the warnings
field not cleared when a result is discarded, the convergence returned to space
notation, and the warnings label put back in the group box unscrolled.

### #29 — 2026-08-07 — Owner sets two defaults, one of which reverses §7

Two preselections, both asked for by name after using the built version.

**1. The DMS hemisphere opens on N and W.** It was built to open unanswered, on
the house rule that nothing answers a question for the user. He judged the two
extra clicks per conversion not worth it for data that is always north and
west, and he is right about his own data.

This one costs little. The answer is a visible token in the box beside the
angle it belongs to, it reads back in the result panel afterwards, and it is
correct for every point MCX can convert — the program carries the three
Michigan zones and nothing else. `dms_entry.DEFAULT_HEMISPHERE` is the single
place that assumption is written down, so a zone outside the north-west
quadrant is one edit rather than a habit to hunt.

The placeholder entry went with it: a "not yet" option beside a preselected
default is reachable only by choosing it, and choosing "not yet" is not
something anyone does. `fileio.dms` still refuses an empty letter, which is now
unreachable from the GUI and stays anyway — it is what stops a later change up
in the interface from quietly acquiring a default down in the composition.

**2. The longitude sign dropdown opens on positive west. This reverses §7.**

§7 has said since #1 that this control has no default, and an adversarial
review once recorded a default here as a finding (#20). The reasoning was
sound and is unchanged: the two conventions are indistinguishable from the
numbers in a file, and choosing wrongly moves a Michigan point about 340 miles
onto a sealed survey.

**What changed is not the risk but who carries it.** The owner works in
positive west — the convention of NOAA Manual NOS NGS 5 and of the MATLAB tool
this replaces — he is the only user, he is a licensed surveyor, and restating
the same answer every run is friction he does not want. That is his call to
make about his own instrument.

The concern, recorded rather than argued: **files from OPUS, NCAT, GPS
receivers and GIS software are normally negative west**, and those are exactly
the files a surveyor downloads rather than writes. A preselected positive west
is wrong for every one of them, and wrong by 340 miles. The tooltip now carries
that sentence in capitals, because with no default the control asked the
question by existing and now it does not.

**Scope of the reversal, which is deliberately narrow.** The default is in the
interface and nowhere else:

* `LongitudeConvention` still has no default member;
* `JobSettings.longitude_convention` is still a required field with no default,
  so constructing one without it is a `TypeError`;
* `job.run` still refuses a geodetic conversion whose settings state no
  convention, with the 340-mile sentence intact;
* a zone-to-zone job still passes `longitude_convention=None` deliberately, so
  the record says nothing about a question never asked.

All four are pinned, in
`test_the_core_has_no_longitude_default_even_though_the_dropdown_does`. The
distinction that makes §7 and this amendment both true: **the core assumes
nothing; the interface shows its answer in words before Convert is pressed.**

§7 and CLAUDE.md's convention list have both been amended to point here, so the
next reviewer who reaches for "no default" finds the decision rather than
filing it as a regression.

**Verification.** Suite **1118 → 1120**, green in both modes. Four seeded
defects, all caught: the preselected convention no longer reaching the settings,
the dropdown opening on the other convention, the hemisphere opening on E, and
the hemisphere dropdown becoming a dead control the composition ignores. The
last two matter most — a preselected value that stops being read would satisfy
every assertion about what the box shows while the conversion used something
else.

### #28 — 2026-08-07 — Owner's second pass: DMS entry, and the worked example goes

Four more owner directives after looking at #27 on screen. Three are interface;
the fourth is a question he asked, answered here and in the suite.

**1. The copy glyph is smaller** — 14 px to 11. Pinned as a relationship rather
than as the number: the button may stand above its line of text by the frame a
flat `QToolButton` needs and no more, which the 14 px glyph failed and the 11 px
one passes. It cannot go flat without a hard-coded box, and hard-coding one
renders cramped under a native Windows theme.

**2. The worked example leaves the longitude sign entries.**

    NEGATIVE_WEST -> "negative west"
    POSITIVE_WEST -> "positive west"

This continues #16 note 2 and #17, which took the attribution tail off the same
two strings. The sign word alone names the convention completely — "negative
west" *is* the definition, not an abbreviation of one.

**The job record's `Longitude` line moves with it, and that is the owner's
standing choice, not an oversight.** #16 note 2 raised exactly this and #17
settled it: one wording in both surfaces rather than a short GUI label beside a
longer record entry, because two strings for one fact drift. The example was
doing real work for the person *choosing*, so it moved to the dropdown's
tooltip — which teaches at the moment of the decision without following the
decision into every document that reports it. The record's surrounding lines
still state the conversion direction and both zones' defining constants.

**3. Latitude and longitude can be typed as degrees, minutes and seconds.**

A `Lat/long entry` selector on the Single point tab, relevant only while the
FROM selection is geodetic — a northing has no minutes, so a zone source keeps
the decimal boxes however the selector is set. Decimal degrees is what the tab
opens on. That is a starting state rather than a silent default: the two zone
dropdowns and the longitude convention open unanswered because their options are
indistinguishable from what is on screen, and these two are not — the boxes
visibly change shape.

DMS is four boxes per angle with the symbols already between them — `43 ° 48 '
00.00000 " N` — mirroring what the results panel displays, so a reading can be
typed straight back in. **The hemisphere opens unanswered** and gates Convert,
like every other question this program refuses to answer for the user. Michigan
is always N and W; a dropdown that opened there would be right until the first
time it was not, with nothing on screen saying a choice had been made.

**The architecture point.** Composing d + m/60 + s/3600 is arithmetic on a
coordinate, so it is in `michspc/fileio/dms.py` and not in the interface (§9).
It sits beside `formatting.latitude_dms` and `longitude_dms` because those two
*define* the notation it reads; a parser living anywhere else would be a second,
drifting definition of one format. `tests/test_dms.py` pins the round trip
against the formatter in both directions.

What comes back is **the text the decimal box would have held**, which then goes
through `pnezd.parse_typed_point` — the same single gate as everything else. So
DMS adds a step in front of the gate, not a second gate, and nothing downstream
of `typed_coordinates` can tell the two entry modes apart. `repr` rather than a
fixed format, because `f"{v:.8f}"` would round the typed angle to about a
millimetre before it was ever converted.

**The convention interaction, which is the subtle part.** A DMS longitude is
convention-independent — `formatting.longitude_dms` already recorded why: the
magnitude is the same under both conventions and the letter is a fact about the
point. So the letter alone fixes the position, and `positive_west` only decides
how that one position is written as a bare number. The pin: **the same DMS entry
converts to the same coordinate under both conventions, where the same decimal
entry gives two points 340 miles apart.** Both halves are asserted; the contrast
is what makes the first half mean something.

The convention selector stays required for geodetic jobs regardless. It still
governs how the decimal longitude is displayed and recorded, and relaxing a
safety gate because one entry mode happens not to need it would be a rule with
an exception in it.

**4. The input CSV takes decimal degrees only — the owner's question, answered.**

`pnezd._parse_number` calls `float()`, so `43°47'59.8"N`, `43 47 59.8 N` and
`43-47-59.8` were all refused already, as "not a number". That is the right
behaviour and the wrong sentence: a surveyor whose data collector exported DMS
has a *format* problem and would go looking for a corrupt row.

DMS is now refused **by name**, with a message that says the reader takes
decimal degrees, says why DMS is not read from a file, and points at the Single
point tab, which does take it. The detection is a diagnostic and never a parse —
nothing branches on it.

**Reading DMS out of a file is deliberately not built**, and the reason is
recorded so it is not revisited by accident: the spellings differ between
collectors, the hemisphere is a letter in some and a sign in others, and packed
forms are indistinguishable from ordinary numbers — `434759.8` is a perfectly
good decimal degree, nowhere near Michigan. A reader that accepted DMS would
have to guess between those readings, and guessing moves a point silently. In
four separate boxes nothing is ambiguous, which is why the typed path can offer
what the file path refuses.

**Verification.** Suite **1048 → 1118**, green in both `pytest` and `-O`; the
frozen-bundle self-test passes with `fileio.dms` and `gui.dms_entry` in its lazy
import list. Every new pin was falsified by seeding its defect: minutes divided
by 100, the hemisphere ignored, a blank component read as zero, the fixed
8-place format, the convention applied to a latitude, the 14 px glyph restored,
and a DMS spelling reaching the generic refusal.

### #27 — 2026-08-07 — Owner's interface edits before the release: four changes

Four owner directives, taken after looking at the built Single point tab
(amendment #26) for the first time. All four are interface-only. **No
computation changed, no formatter changed, and no value that reaches the screen
is produced differently than it was** — the suite's agreement pins between the
panel, the multi-point table and the audit CSV are untouched and still green.

**1. The single-point result reads in two columns, INPUT on the left.**

It was one column, INPUT stacked above OUTPUT. On a laptop screen that put the
converted coordinate below the fold: reading the answer meant scrolling away
from the typed point, which are the two numbers a surveyor most wants to see at
once. Now the two sections sit side by side with a vertical rule between them.

The split in `michspc.gui.result_panel` is **positional** — first section left,
the rest right — not by matching the string `"INPUT"`. That module does not know
what INPUT means and should not learn: `results_model.single_point_sections`
already states the section layout, and a second statement of it in the panel is
a second thing to keep in step. What ties the two together is a test, in all
three directions.

Row indices are unchanged by the split. `value_labels[i]`, `copy_buttons[i]`,
`displayed_rows()[i]` and `copy_value(i)` all still mean the same row, in
flattened section order, so a button in the right-hand column cannot copy a
left-hand value. That is pinned, because it is the stale-value failure of #26
arriving by a new road.

**2. The copy control is the Windows 11 glyph, beside its own value.**

It was the word `Copy`, in a grid column of its own — so every button landed at
the right edge of the widest value in the panel, an inch of blank space from the
number it copied, in a vertical row of identical-looking buttons. Now each
button carries the two-offset-rounded-rectangles symbol the surveyor already
knows from File Explorer, and sits immediately after the end of its own value.

Drawn with `QPainter` in `michspc.gui.copy_icon`, **not** shipped as an asset.
The alternatives were each worse for a program whose release is eight gates
deep: a `.svg` or `.png` would put a new file in the path of the PyInstaller
spec, the frozen-bundle self-test and the checksum gate; `QStyle.StandardPixmap`
has no copy glyph on Windows; `QtSvg` is a Qt module the bundle does not carry.
The module *is* added to `selftest.LAZY_IMPORTS`, so the frozen bundle proves it
can import it — a missing one would show as a row of blank buttons, not as an
error.

The colour comes from the panel's own palette, so a dark Windows theme does not
get black on near-black. The tooltip still names the section and the row, which
is the disambiguation the #26 closing gate asked for and which matters *more*
now that the caption is a picture and not a word; the accessible name is still
"Copy", because a glyph with no accessible name is a button with no name at all
to anything that is not a pair of eyes.

**3. The input file box starts empty, with no placeholder.**

The greyed-out `C:\jobs\24-118\pts.csv` is gone. It was a job number that is not
this surveyor's, in a folder that does not exist, sitting in the field that
names the file about to be read — and a placeholder in a path field is not
distinguishable at a glance from a path that is really there. The format hint
below the field is untouched: it is a correctness aid (#16 note 1), not a
suggestion.

**4. The output folder starts empty. This REVERSES #16 note 3.**

The Downloads pre-fill is removed and nothing replaces it — no default, no
placeholder. Downloads is not where a survey job's exports belong, and a
pre-filled destination is answered by pressing Convert rather than by choosing.

`default_output_directory` is **deleted**, not left unused, and the
`QStandardPaths` import went with it. A dormant Downloads lookup sitting beside
a field that no longer calls it is one line away from being switched back on by
someone who reads #16 note 3 and not this. The absence is pinned by a test.

What #16 note 3 said about safety still holds and is still checked: Convert is
gated on the field being non-empty, and `exports.write_all` still refuses to
clobber, still stages and renames, and still verifies the round trip.

**One defect found by looking at it, not by a test.** With the panel halved in
width, `QLabel`'s word-wrap sizeHint heuristic took less width than the text
needed, and "Michigan Central 2112" arrived as two lines with the copy button
stranded beside the first half — in a column with two inches of unused space to
its right. The fix is a minimum width taken from the text's own advance and
capped at `WRAP_WIDTH`, so every value stays on one line and only the Warnings
paragraph wraps. It is stated as a width rule rather than as a rule about which
row is which, because this module does not know that one of its rows is called
Warnings. Pinned, and falsified.

**Verification.** Suite **1031 → 1048**, green in both `pytest` and `-O`. Every
new pin was falsified by seeding the defect it claims to catch: the stacked
single column, the two columns in the wrong order, a rule that paints nothing, a
button pushed back to the far right (**twice** — the first version of that pin
measured the label widget's right edge instead of where the text ends, and
passed against the defect; it now measures the text advance), the word in place
of the glyph, an unpainted glyph, a filled glyph, and two sheets crossing
instead of one sitting in front of the other. The frozen-bundle self-test passes
from source with the new module in its list.

### #26 — 2026-08-07 — Single point: a second tab that types one coordinate

**Written before the code, as the specification.** Closed at the end of the
work with what actually landed.

The program converts a *file*. The owner wants the everyday case that makes
clumsy: one coordinate, typed in, converted, read off the screen — no file to
prepare, no folder to choose, nothing written. The existing tool becomes the
**Multi point** tab; the new one is **Single point**.

**The constraint that shapes everything else:** the two tabs must be
*incapable* of disagreeing about the same point. A surveyor who checks a
coordinate on one tab and then runs the file through the other must get the same
numbers — a discrepancy between two views of the same conversion is the tier
sentence's failure mode arriving by a new road. So the typed values go through
the **same validation gate** (`pnezd.parse_lines`) and the **same conversion
function** (`job.run` → `_convert_row`) as a file row. Not a parallel path that
happens to agree today.

**Owner's decisions.** Two tabs, Single point at index 0 and the window opens
there. Tabs are **fully self-contained** — each carries its own zone, unit and
longitude-sign controls and shares no state, so neither can silently alter the
other. No export, no file, no output folder on the single-point tab: a results
display only. No point number and no description — coordinates only. Elevation
optional, on the file reader's own convention. The input is **either N/E/Z or
geodetic, never both**; the entry fields relabel by direction. A Convert button,
not live-as-you-type. Latitude and longitude in **both** decimal degrees and
DMS, DMS to **five decimal places of a second**. A small copy button beside each
output value and one Copy all.

**Latitude and longitude in DMS are magnitude plus a hemisphere letter, never a
sign.** The owner's format: `42°43'57.00000"N`, `84°33'19.80000"W`. His first
sketch paired a minus with the letter — `-84°33'19.80000"W` — and he corrected
it during the build: the two say the same thing, and together they read as a
double negative. The letter alone states the direction completely.

A consequence worth stating, because it is what makes the format work: a DMS
longitude is **convention-independent**. The magnitude is the same number
whichever way the file writes its signs, and the letter is geographic — always
`W` in Michigan — so one position reads `84°33'19.80000"W` under both
conventions. `longitude_dms` therefore takes no `positive_west` parameter at
all, while its decimal-degrees sibling `longitude` still must, because a bare
number has to pick a sign. The letter is read from the **signed** value the
core stores, never from the displayed number: handed a user's positive-west
`84.5555` with nothing said about the convention, the formatter could only call
it east, and a Michigan longitude labelled "east" is the quiet falsehood this
program exists to refuse.

That letter also replaces what would otherwise have been a separate "longitude
sign" row, and it answers a real problem: a zone-to-zone job never asks for a
convention (`job.run` refuses `None` only for the geodetic directions) yet its
result shows a longitude. With no sign to interpret, the interface is not
answering a question it was never asked.

**Results layout, decided by the owner.** The general rule is that computed
values independent of the target zone appear under OUTPUT; the factors that
describe the *typed* State Plane coordinate stay under INPUT.

| Direction | INPUT | OUTPUT |
|---|---|---|
| zone → zone | zone, units, N, E, Z, source grid scale factor, source convergence | target zone, units, N, E, Z, latitude and longitude (DD and DMS), grid scale factor, convergence, geoid height, ellipsoid height, elevation factor, combined factor, warnings |
| SPC → geodetic | zone, units, N, E, Z, grid scale factor, convergence, geoid height, ellipsoid height, elevation factor, combined factor | latitude and longitude (DD and DMS), elevation, units, warnings |
| geodetic → SPC | latitude and longitude as typed (DD and DMS), elevation, units | target zone, units, N, E, Z, grid scale factor, convergence, geoid height, ellipsoid height, elevation factor, combined factor, warnings |

In SPC → geodetic there is no target zone at all, so every factor describes the
typed point and none of them belong on the output side. Warnings are the last
OUTPUT row in **all three** directions, including the one the owner did not list
— a layout rule that hides a warning in one direction is not a layout rule.

**`JobSettings.input_path` and `.output_directory` become `Path | None`** —
still required, still without defaults, the idiom `longitude_convention` already
uses: `None` is a statement, not an absence. `run` never reads
`output_directory` and reads `input_path` only when no parsed source was handed
in, so a typed point can state honestly that it came from no file and produces
none. The alternative was a fabricated placeholder path, which is the plausible
default §1 forbids. Four reads are guarded, each raising its own layer's error:
`run`, `exports.output_stem`, `exports.archive_path`, `report.build_report`.

**Every typed field is quoted before it reaches the reader.** A typed field is
one field by construction — a `QLineEdit` cannot contain a delimiter — and
quoting is what makes the CSV reader agree with that fact. Unquoted, a typed
`780,000.000` northing shifts every column right: the row parses cleanly as
N=780, E=0.0, Z=13221442.048 and converts, and the ambiguous-grouping guard
cannot catch it because a typed point has no description for that guard to
inspect. Quoted, the same text lands in `_parse_number`'s existing
grouped-number branch, where genuine grouping is honoured and `1,2` is refused
with the reader's own teaching message. This is a real semantic decision — it
makes `780,000.000` *valid* rather than silently wrong — and it is pinned by a
test falsified against an unquoted builder.

**Rejected: a second job-layer entry point.** A `convert_one()` would have to
restate the direction/zone validation and the longitude refusal, and two copies
of those rules is exactly the divergence this feature is forbidden to create.
The two tabs call the same function object.

**Rejected: a validator on the entry fields.** A `QDoubleValidator` is a second
validation gate that rejects silently, which inverts both "one entry point per
data path" and "refusals teach". Non-numeric text travels to the reader and
comes back as the reader's own sentence naming the field and the line.

#### Closing gate on this feature (2026-08-07)

Two reviewers ran blind to each other over the whole feature diff. **Both found
the same CRITICAL independently**, and neither could construct an input where
the two tabs disagree — one drove both real GUIs over 378 configurations
(3×3 zone pairs, both conventions, all nine input/output unit pairs, with and
without an elevation), parsed the audit CSV back out of the ZIP the multi-point
run wrote, and compared it to the panel section by section: zero disagreements.
The other confirmed by tracing and by 29 hostile typed strings that no input can
reach the core as a different number than typed.

Fixed, each pinned and each pin falsified:

- **CRITICAL — a stale result survived every control and field change**, with
  both copy paths armed. Editing a northing after converting left the previous
  point's answer on screen, still captioned "Converted": the reviewers' shared
  counterexample was a reading **100,001.037 ft out**, one click from the
  clipboard. Worse in the second shape they found, where flipping the longitude
  convention left a longitude on screen whose sign the control now contradicted
  and which carried no qualifier to reveal it. Now every entry field and every
  selection discards the result, clears the panel, disables Copy all and says
  "Input changed. Press Convert." Clearing rather than annotating: a greyed-out
  number is still a number beside a Copy button.
  **[ANNOTATED at #43: "every selection" was FALSE.** The longitude sign
  dropdown — the very control of the "second shape" above — was wired to
  Convert-gating only and never invalidated; the fix and this record's test
  covered zones and units and missed it. It shipped that way from 0.1.0
  through 0.3.1, capable of a stale result 9,756,797 m out, and was found by
  the WP-V8 review gate. Fixed and pinned at #43.]
- **Two warnings told a typed-point user to check a file that does not exist** —
  "the ones this file is actually in" and "was read from the file". Reworded for
  both callers; the wrong-source-zone warning is the likeliest a typed point
  raises.
- **The fabricated point identifier reached the screen.** `parse_typed_point`
  must supply one because the reader refuses a blank, but this tab has no point
  numbers: the panel now strips exactly `point 1` from displayed warnings, and
  the status tooltip no longer prefixes it a second time ("1: point 1: …").
- **Copy buttons beside two identically-named rows.** Both sections carry a
  "Northing"; the tooltip now names the section. The INPUT buttons stay,
  because in a State-Plane-to-geodetic job every factor sits under INPUT.
- **The half-pathless report refusal said "neither"** when only one path was
  missing.
- **`selftest.LAZY_IMPORTS`** gained the three new GUI modules; they reached the
  bundle transitively, which satisfied the list's contract only indirectly.

Two test gaps closed, both found by seeding defects that the 1014-test suite
passed: the **INPUT block was never exercised with the two units differing**, so
four separate defects rendering an input coordinate, elevation or unit label in
the *output* unit all went unnoticed; and the **no-write test watched a
directory the tab has no relationship to**, so a seeded `Path("x").write_text()`
landing in the process working directory passed it. Also added: the panel is now
compared against the **audit CSV the other tab actually wrote**, which reaches
convergence, geoid height, ellipsoid height and the elevation factor — none of
which appear in the multi-point table the first pin compared against.

**Accepted, not fixed, with reasons.** A per-value copy of the decimal-degrees
`Longitude` puts a signed number on the clipboard with nothing travelling
alongside to say which convention it is in — and on a zone-to-zone job the user
was never asked. The mitigation is the DMS row beside it, whose hemisphere
letter is unambiguous and independently copyable. Naming the convention in the
row label would contradict the zone-to-zone case, where the program never asked;
carrying it in the copied text would break the rule that a copy is exactly the
value. Recorded so the trade is visible rather than assumed. Separately,
`latitude_dms(-0.0)` reads `N` while `latitude(-0.0)` reads `-0.00000000`; the
only disagreement found in ~1.6 million checks, and unreachable from any
Michigan position.

### #25 — 2026-08-07 — 0.2.0: renamed MCX, publisher corrected, lettering removed

Three owner directives, one release. **No computation changed**; the suite is
green in both modes and the frozen bundle passes its own self-test.

**The program is MCX, for Martin Coordinate Exchange.** `APP_NAME` is now the
three letters, with `APP_FULL_NAME` beside it for every surface that has room —
the window title, the file description, the installer — because three letters
alone do not tell a reader six months later what produced a file. The executable
is `mcx.exe`. The **Python package stays `michspc`**: renaming it would touch
every import in the project for no user-visible gain, and the package name is
not a user-facing fact. Recorded so the divergence is deliberate rather than
an oversight.

**The publisher is DMARTIN.** Windows' Installed apps and the executable's own
version resource both showed "Lapham Associates", which was wrong. It is now a
constant, `APP_PUBLISHER`, read by the installer and the version resource
rather than restated in each.

**The AppId is deliberately unchanged.** A new GUID would make the renamed
program a *second* entry in Installed apps beside the old one, with the old one
un-uninstallable from its own shortcut. Keeping it means Windows treats 0.2.0
as an upgrade — which is what it is — so an `[InstallDelete]` section removes
what the old name left behind: `michspc-spc-converter.exe` and the two old
shortcuts. Harmless on a clean machine.

**The lettering is out of the artwork at every size.** "COORD CONVERT" was also
now simply wrong. It could not be cropped away: the down arrow's tip reaches
y=956, *below* the lettering band at y=860–915, so every crop that loses the
words amputates the arrow the composition is built around. The words and their
embossed shadow were painted out instead and the badge behind them rebuilt by
interpolating each column between the clean rows above and below the band,
which reproduces the vertical gradient and the vertical grid lines exactly.

Four things had to be got right, each found by looking at the output rather
than trusting the previous step: a warm-colour mask removes the cream glyphs but
leaves their dark shadow perfectly legible; a "keep what is bright and neutral"
rule preserves the arrow but also preserves the glyphs' anti-aliased edges, so
the wording survives as an outline; interpolating across the badge's bevelled
rim smears it into vertical streaks, so the rebuild is confined to the flat
interior; and a keep-window derived per row from the arrow's own measured extent
must be clamped, or a letter edge inside the search range widens it and drags
a shadow back in. The final rule is: rebuild rows 843–934 for x in [120, 940],
except the arrow's own width per row, clamped to [462, 560] and never narrower
than the shaft.

**A test pin was corrected, not deleted.** `test_the_spec_reads_the_version_
rather_than_restating_it` asserted the spec's *entire* import line, so adding
`APP_FULL_NAME` and `APP_PUBLISHER` beside `__version__` failed it. The rule it
exists to enforce — the version is imported, never restated — is untouched; the
assertion now checks that rule instead of the line's exact shape.

### #23 — 2026-08-06 — Narrowing re-confirmation: 10 closed, 1 accepted weak, 1 new defect fixed

The closing gate's reviewer re-examined only the fixed surfaces, at commit
`386763c`, and returned **10 of 11 CLOSED with faithful pins** (full table in
`review/gate3-output.txt`). It independently re-verified the frozen anchors —
356 fixture fields compared field-by-field against the raw NGS captures, **zero
mismatches** — and confirmed the new end-to-end tests bite by seeding three
defects, including the original feet-in-a-metres-column defect, and watching the
committed assertions catch each one.

**A defect the fixes introduced, now fixed.** The apex refusal added to
`lambert.inverse` wrapped *every* `ApexLatitudeError` from the solver in the
wording "northing … within a rounding step of the apex" — a statement about the
+90° side. But `Q < 0` is the *opposite* side, which an extreme easting reaches
with a perfectly ordinary northing, so the refusal sent the surveyor to check
the wrong field and never mentioned the easting at all. Separately,
`math.hypot` of two finite doubles can overflow to infinity, making `K / R` zero
and `math.log` raise a bare `ValueError("math domain error")` naming nothing —
reachable from an ordinary finite PNEZD row through `job.run`.

Both are fixed: the mapping radius is checked for overflow before the logarithm,
and the refusal now branches on the sign of `Q`, naming the easting when the
easting is at fault and keeping the original apex wording when it is not. Four
pins, all falsified — one of which was first written too weakly (it asserted
only the absence of a phrase, and the pre-fix bare `ValueError` satisfied it),
caught during falsification and strengthened to assert the exception type.

**Finding 11 accepted as WEAK, deliberately.** The reviewer is right that the
final rename is not write-through: the archive's *contents* are fsynced and
CRC-verified before the rename, but the rename's own metadata is not forced to
stable storage, so a power loss in that window could leave the deliverable
missing. Not fixed, for three reasons. The failure mode is an **absent** archive,
never a corrupt or wrong one — the tier sentence is about wrong coordinates
reaching a drawing, and a job that has to be re-run is not that. Forcing it
means calling `MoveFileEx` with `MOVEFILE_WRITE_THROUGH` through `ctypes`, which
is new platform-specific code in the write path that had just passed
verification. And the window is bounded by the filesystem's own flush interval.
Recorded here so it is a decision with reasons rather than an oversight, and
stated plainly in the release notes rather than hidden.

The reviewer also confirmed the rejection of a startup sweep for orphaned
`.partial` files (#20) as adequately reasoned: a sweep could delete a concurrent
instance's stage, and a `.partial` file cannot masquerade as a deliverable.

### #21 — 2026-08-06 — §6 was wrong about SPCS2022, and the extensibility claim did not survive

Both reviewers were asked to attack §6's claim that SPCS2022 "arrives as data
rather than a rewrite". Both returned **REWORK-REQUIRED**, independently and
with congruent lists. The claim was aspiration recorded as fact.

What §6 promised and what exists: there is **no `Projection` protocol** —
`convert.py` imports `lambert.forward`/`inverse` by name; `Zone.definition` is
typed to `LambertTwoParallelDef` alone; **`ProjectionKind` is declared and read
nowhere**; the "two Lambert constructors" are one; there is **no datum
transformation seam as code** — `PointConversion` carries a single pivot and a
single frame, so a real transformation changes the core record type and with it
the audit schema; `report.py` hardcodes 2SP Lambert, GRS 80, NAD 83, Appendix C
and "twenty-seven positions", and raises `AttributeError` on a 1SP zone *after*
the coordinates are computed; zone lookup is keyed on the bare code, so two eras
collide; archive names and audit columns cannot distinguish eras;
`_EASTING_WINDOW_M` assumes SPCS 83 false-easting spacing. Clean: `zones.py` is
genuinely data, and the GUI zone dropdown builds entirely from `ALL_ZONES`.

**§6's factual claim about Michigan was also false.** It said Michigan "kept
Lambert conformal conic and the same three zones, redesigned as low-distortion
projections". Recon against NGS's published zone definitions
(`beta.ngs.noaa.gov/SPCS/json_data/zoneDefinitions.json`, page last updated
2026-06-01; downloaded and inspected directly by the session lead) shows
Michigan's final SPCS2022 design is **19 zones on NATRF2022**:

- `260001` **Michigan**, statewide, **oblique Mercator (OMC)**, origin 45°00′N /
  86°00′W, skew azimuth −26°, origin scale 0.999800;
- `261001`–`261018`, eighteen state-designed low-distortion zones named for
  localities (Ann Arbor, Detroit, Flint, Saginaw, Roscommon, Thunder Bay,
  Kalamazoo, Grand Rapids, Newaygo, Wexford, Leelanau, Cheboygan, Mackinac,
  Escanaba, Marquette, Houghton, Bessemer, Isle Royale) — **13 one-parallel
  Lambert (LC1) and 5 transverse Mercator (TM)**, all origin scales ≥ 1.

There is no SPCS2022 Michigan North/Central/South. Supporting Michigan therefore
needs the **transverse Mercator (§3.2) and oblique Mercator (§3.3) engines**,
not merely the 1SP Lambert constructor §10 anticipated. §6 is corrected in place
by this amendment; the superseded wording is quoted above so the record shows
what was believed and when.

**Publication status, established 2026-08-06 from primary NGS sources.** Zone
parameters: published and declared *"stable for implementation planning"* (NOAA
bulletin, 2026-05-28); beta feedback closed. NATRF2022: **finalized in beta, not
released** — FGCS approval expected mid-2026, official adoption late 2026 per the
Federal Register notice of 2024-10-09, with an unconfirmed report of slip into
2027. NAD83(2011)→NATRF2022 transformation: **does not exist as an official
product**; beta NCAT states plainly that it does not transform between reference
frames. Verification source: beta NCAT **does** emit SPCS2022 coordinates, so
projection anchors are obtainable — but they would be *beta* anchors and must be
re-frozen against official NCAT at rollout. Units: the beta tables publish
international feet only, which matches this program's default.

**Verdict recorded: PARTIALLY BUILDABLE, and deliberately not built now.** The
zone layer could be built today; the datum layer cannot. Until an official
NAD83(2011)→NATRF2022 transformation ships, this program could hold SPCS2022
zones but could not legitimately move the owner's existing NAD 83 job
coordinates into them — and moving them anyway is precisely the silent 1–2 m
error §6's safety rule exists to prevent. The frame refusal in `frames.py`
therefore stays, and it is doing real work rather than standing in reserve.

The rework list above is the opening specification of the future SPCS2022 work
package. Deliberately not attempted in this session: the core had just passed
three independent verifications, and restructuring it before release would
re-open verified surfaces for no present capability.

### #22 — 2026-08-06 — NGVD 29 → NAVD 88 sized, recorded, not built

Owner asked how large a task vertical datum conversion would be, with NAPGD2022
capability later. Researched against primary NGS sources 2026-08-06; recorded
here so the work can be scoped without repeating the recon.

**Verdict: MEDIUM — two work packages**, comparable in bulk to the GEOID18
subsystem, roughly 1,200–1,800 lines with tests. Nothing architecturally novel;
every piece has a precedent in this repo.

Available today: **VERTCON 3.0** (release 20190601) transformation and *error*
grids for CONUS, covering all of Michigan, in the NGS `.b` format — the same
family as the GEOID18 tile already read here, differing by Fortran record
markers bracketing the header and each row, which are themselves a free
structural check. Both grids are ~2.4 MB, US-government work, SHA-256 pinnable
exactly like `g2018u3.bin`. The NCAT API carries the transformation
(`orthoHt`, `inVertDatum`, `outVertDatum`), so frozen anchors come from the same
source and workflow as the existing NCAT lattice — verified live by the session
lead: 200.000 m NGVD 29 at 43.0 N, 84.5 W → **199.860 m** NAVD 88, σ 0.001,
`vertconVersion 3.0`. The shift depends on horizontal position only, so the
inverse is the same grid with the sign reversed — one data path, not two.

Shape of the work: a `VerticalDatum` and a **transformation registry keyed by
(source, target)**, mirroring `frames.py` and its refusal — any pair without a
published grid refuses loudly. That registry is the NAPGD2022 seam: it arrives
later as a record plus grids plus a citation. Elevations become datum-tagged
rather than untyped floats implicitly meaning NAVD 88. The shift must land
**before** the geoid lookup, because GEOID18's N is defined against NAVD 88.
`ConvertedPoint`'s "unchanged by the conversion" contract is repealed for the Z
column, which must then be said in every output.

**Top risk, and the reason this is not a small task: disclosure.** VERTCON is a
*modeled* shift — NGS states 2 cm (1σ) and that it "can not maintain the full
vertical control accuracy of geodetic leveling", with rare NGVD 29 network
distortions of 20 cm or more, and published NAVD 88 benchmark values superseding
it. A converted elevation looks exact. The record must carry the per-point sigma
from the error grid and the supersession caveat verbatim, or this program
launders a model into a sealed number — the tier sentence applied to heights.
Second risk: the sign/direction semantics of the `trn` grid must be pinned
against a live NCAT anchor at build time; that is the geoid-sign defect class
this project has already been burned by (#1, MATLAB defect 2).

NAPGD2022 itself is **blocked**: beta only, no final NAVD88→NAPGD2022
transformation product exists, and GEOID2022 replaces GEOID18 in the factor
chain when it lands. Make the GEOID18↔NAVD88 pairing explicit data in the
registry now so that later is a data change rather than an excavation.

### #17 — 2026-08-05 — Owner resolves the two open questions from #15 and #16

**No loose PNEZD file.** The ZIP is the only deliverable. A job writes exactly
one artefact, `<stem>.zip`, containing the clean PNEZD export, the full audit
CSV and the job record. Nothing is written beside it.

This settles the CAD-import friction raised in #15 note 2 in favour of a single
handover artefact: the three files travel together or not at all, so a PNEZD
file can never be filed or emailed without the record explaining how it was
derived. That is the stronger property for a document that ends up supporting a
sealed survey, and it is worth the unzip.

**Short longitude wording in both surfaces.** `LongitudeConvention`'s enum values
lose the "as used by …" attribution outright — no separate GUI label, no longer
text preserved for the job record. The sign and the worked example carry the
meaning:

    NEGATIVE_WEST -> "negative west (-84.37)"
    POSITIVE_WEST -> "positive west (84.37)"

The job record's "Longitude" line therefore reads shorter too. Acceptable
because the record already states the conversion direction and both zones' full
defining constants immediately around it, so the convention is not left without
context.

### #16 — 2026-08-05 — Three GUI notes

**1. The input row's label is static; its format hint follows the From zone.**

The label reads **"Input file:"** in every state — not "Input PNEZD file:".
Renaming it once, rather than swapping it between two spellings, keeps the
control's identity stable and is what the owner asked for.

The *format hint* is what changes. It currently always describes PNEZD —
*point, northing, easting, elevation, description*. When From is set to
`Geodetic (latitude / longitude)` the file is not PNEZD at all: columns two and
three hold latitude and longitude, so the hint must read *point, latitude,
longitude, elevation, description*.

This is a correctness aid, not cosmetics. The two layouts are indistinguishable
from the numbers alone in the sense that matters — a file fed under the wrong
reading produces a coordinate rather than an error, and the program's own
easting guard only fires for the zone case.

**2. Drop the "as used by …" tail from the longitude sign selector.** The two
options read *"negative west (-84.37), as used by OPUS, NCAT, GPS and GIS"* and
*"positive west (84.37), as used by NOAA Manual NOS NGS 5"*. The owner wants the
attribution removed; the sign and the worked example are the parts that
disambiguate.

**Note for whoever implements it:** those strings are the
`LongitudeConvention` enum *values*, and `report.py` prints the same value on
its "Longitude" line. Shortening the enum shortens the job record too. Either
give the enum a separate short GUI label and keep the fuller text for the record,
or accept the shorter text in both — **ask the owner which**, since the job
record is the document that has to stand on its own six months later.

**3. The output folder defaults to Downloads.** The field currently starts
empty, and Convert stays disabled until it is filled. It should pre-fill with
the user's Downloads folder.

Resolve it with
`QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)`
rather than assembling `~/Downloads` by hand — Windows lets Downloads be
relocated, and Qt reads the real shell path. If Qt returns an empty string (it
can, on an unusual profile), fall back to the home directory rather than to a
path that does not exist, and leave the field editable either way.

The pre-filled default does **not** relax anything: the overwrite refusal, the
atomic write and the round-trip verification all still apply, so a default
destination cannot silently clobber a previous job's export.

### #15 — 2026-08-05 — App icon, ZIP export, and a standing report-validity rule

Three owner notes.

**1. App icon.** `assets/icon/coord-convert-1024.png` — 1024×1024, 8-bit RGBA
with transparency, a compass rose over a grid reading "COORD CONVERT". Supplied
by the owner; committed as the master artwork.

Windows needs a multi-resolution `.ico` derived from it (16, 32, 48, 64, 128,
256 px) for three consumers: the Qt window icon, the PyInstaller bundle, and the
Inno installer and its Start-menu entry. Generate the `.ico` as a build step
from this master rather than committing a second hand-made artefact, so the two
can never diverge.

**One judgement call to put to the owner:** at 16 and 32 px the "COORD CONVERT"
lettering will be an illegible smear. The usual fix is a cropped, text-free
variant of the compass for the small sizes inside the same `.ico`. Ask before
assuming — it is his artwork.

**2. Exports ship as a single ZIP.** A job produces three files; they are to be
delivered as one `<stem>.zip` rather than three loose ones, so a job hands over
as a single artefact.

Everything the loose writers guaranteed must survive the change: stage-and-
rename atomicity on the archive itself, refusal to clobber without confirmation,
and the PNEZD round-trip verification running *before* the archive is committed
to its final name. A job still either produces a complete readable deliverable
or leaves the output folder untouched.

**Friction worth naming:** importing into CAD now requires unzipping first.
Whether the clean PNEZD file should *also* be written loose alongside the
archive is the owner's call, not an assumption to make silently.

**3. The job record must always describe the program as it actually is.**
Standing rule, not a one-off task. `report.py` currently states at length that
every coordinate is computed twice by two independent methods and reports a
worst-engine-discrepancy figure. Amendment #14 deletes the second engine, which
makes that section **false**. It also describes three separate output files,
which note 2 makes false.

Both must be rewritten in the same change that causes them — a job record that
misdescribes its own derivation is worse than no record, because it is signed,
filed, and believed. The verification wording should cite what actually carries
the weight after #14: the frozen NGS NCAT anchors and the published Appendix C
constants.

METHOD.md §5 already requires a generated manual to be rebuilt in the same
change as any user-facing behaviour. Amendment #13 dropped the manual; this
extends the same discipline to the job record, which is now the only generated
documentation the program produces.

### #14 — 2026-08-05 — SUPERSEDES #12: delete the polynomial method entirely

> "delete all traces of the polynomial method so that we dont have an
> unverified/unreviewed code pathway"

Amendment #12 demoted the §3.4 polynomial engine from runtime gate to build-time
check. **That is superseded: it is removed from the program altogether.**

The reasoning is sound and worth stating, because it reverses a decision made in
the original plan. A second engine is only a safeguard if it is itself held to
the same standard as the first. This one was not: it carries NGS's own stated
0.5 mm fitting error, it degrades to **metres** outside each zone's fitted band
(amendment #5), and it forced an in-band/out-of-band policy that the interim
review gate then found two defects in (findings #3 and #4, amendment #11). A
code path that needs its own special-case policy to stay quiet is not a check —
it is a second thing to verify.

The verification that actually carries weight is the **frozen NGS NCAT anchors**:
27 lattice points computed by NGS's own service, agreeing with the rigorous
equations to 0.497 mm, which is the limit of what NCAT publishes. Plus the
published Appendix C derived constants, reproduced from the defining constants
alone. Both are external authorities. Neither is code we wrote.

**Honest statement of what is given up.** There will be no independent
recomputation *at conversion time*. A regression in the rigorous engine would be
caught by the test suite and the release gates, not by the running program. That
is the normal state of affairs for engineering software and it is the owner's
call; it is recorded here so nobody later mistakes the absence for an oversight.

**What stays.** Amendment #5 remains in this log as history — the measurement
that the polynomial method is wrong by up to 3355 mm across zones is the
evidence that made the rigorous equations primary, and deleting the code does
not delete the reason. Section 5 of this document is superseded by this entry.

### #13 — 2026-08-05 — Release via GitHub Releases; no user manual

Two owner directives, both affecting WP7.

**1. The published `.exe` ships as a GitHub Release** on
`martin71337/michigan-spc-converter`, not as a loose file. Each release carries
the installer, its SHA-256 checksum, and release notes naming what was verified
(test counts in both run modes, the anchors, the gate verdicts). The tag is the
version literal from `michspc/__init__.py` — which the release gate already
refuses to build while it carries a `-dev` marker, so the tag and the binary
cannot disagree. The repository is private, so releases are private too.

**2. No user manual.** METHOD.md §5 calls for a generated manual rebuilt in the
same change as any user-facing behavior, and §6 for a release gate checking its
content freshness. **Both are dropped**, and this is a recorded deviation rather
than an omission.

Reason: the interface is one window with six controls, and the job record
written beside every export already explains the units, the zones, the method,
the factors and each output file in plain language — to a reader who did not run
the conversion. A separate manual would restate it and then rot. The job record
*is* the documentation, and it cannot go stale because it is generated from the
same run it describes.

Consequence for the release script: the doc-freshness gate is removed from the
gate list. Every other gate in METHOD.md §6 stands — version sanity, full suite
in both modes, bundle build, frozen-artifact self-test, installer, checksum.

### #12 — 2026-08-05 — Owner directive: do not invest further in the polynomial method

> "you dont need to develop the polynomial method as long as you cross check with NGS"

**Superseded scope, not superseded code.** The §3.4 polynomial engine is built,
correct, and anchored. What changes is its *role*.

It is currently a **runtime** gate: it runs on every point and the pipeline
enforces agreement, which is where the whole in-band/out-of-band policy
(amendments #5, #6) comes from. The frozen NGS NCAT anchors are a **build-time**
authority: 27 lattice points proving the rigorous engine matches NGS to
0.497 mm, the limit of what NCAT publishes.

**To do at resume:** demote the polynomial engine from runtime gate to
build-time verification. It keeps earning its place in the test suite — it is a
genuinely independent second derivation and it is what produced amendment #5 —
but it stops gating live conversions. This deletes `_check_engines`, the
in-band/out-of-band branch, `WarningCode.ENGINE_DISAGREEMENT_OUT_OF_BAND`, and
with them gate findings #3 and #4 below, which exist only because of that
policy. The `Zone.band_lat_*` fields stay, used by the test suite only.

Net effect: less runtime machinery, the same verification strength, and the
authority moves from a 1980s hand-calculator approximation to NGS's own service.

### #11 — 2026-08-05 — Interim review gate: findings accepted

Codex CLI, read-only, over `8127446..e2a8834`. **VERDICT: FINDINGS** — three
critical, three high, one medium. Six accepted, one rejected (#10 below).
Surfaces it examined and found clean are recorded in `review/gate1-output.txt`,
including an independent 60-digit recomputation of the Lambert equations that
differed from production by at most 1.68e-9 m, and a line-by-line check of every
Appendix A and C transcription against the committed PDF.

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | CRITICAL | Geodetic input carries no reference frame, so a NATRF2022 position is silently projected as NAD 83 | **Fixed** |
| 2 | CRITICAL | Longitude domain unvalidated: 275.4445 (the 0–360 form of −84.5555) converts silently, 2.2 M m out of place | **Fixed** |
| 3 | HIGH | A non-finite input is downgraded to a warning by the out-of-band branch and returns NaN coordinates | **Fixed** at the engine; the policy branch is deleted by #12 |
| 4 | HIGH | `to_geodetic` re-projects the *polynomial* result, so a defect isolated to the *rigorous* inverse is invisible — an injected 0.01° error reported 0.032 mm agreement | **Dissolved** by #14 |
| 5 | CRITICAL | Caller-supplied `LambertConstants` were not bound to their zone: pairing MI South's constants with MI North's identity gave a coordinate **4,231 km** wrong, warnings only | **Fixed** |
| 6 | HIGH | The production geoid path never authenticates the grid, and a header with row/column counts swapped (1081×1141 → 1141×1081) preserves the payload length and is accepted, giving a 5.16 m geoid error | **Fixed** |

Fixes landed so far:

- **#2 and #3** — `_require_valid_geodetic` and `_require_finite_grid` in
  `lambert.py`, called by *both* engines before any arithmetic. The check must
  precede both, because both are handed the same bad value and agree perfectly
  on the wrong answer — neither the cross-check nor the extent warning protects
  this path. The longitude refusal names the 0–360 confusion and prints the
  corrected value.
- **#5** — the `constants=` parameters are **deleted** rather than guarded.
  `constants_for` is now `lru_cache`d, so callers get the per-file efficiency
  for free and have no way to mismatch. `LambertConstants.zone_code` records
  provenance so any future re-introduction of the seam is checkable.
- **#1** — `project_point` takes a **required** `source_frame` with no default
  and calls `require_same_frame` against the target zone's frame, so a
  cross-frame geodetic input is refused exactly as a cross-frame zone-to-zone
  conversion already was. A `TypeError` guard rejects a non-frame argument
  before that call; the subagent found this was not decoration, because a `Zone`
  duck-types straight through `require_same_frame` (both carry `.code`) and
  produced the nonsense refusal *"Cannot convert from 2113 to NAD83(2011)"*.
  `PointConversion` now carries the frame, so the record itself is tagged as
  §4 requires. `JobSettings.geodetic_frame` defaults to NAD83(2011) at the
  **application** layer only — every registry zone is NAD83(2011) and NATRF2022
  has neither zones nor a transformation, so the only route to a mismatch today
  is a caller setting the field deliberately, and the core then refuses it.
- **#6** — `default_grid()` now routes through `load_shipped_grid()`, which
  verifies the SHA-256 **and** the tile's canonical geometry. Independently
  re-derived by the session lead rather than accepted: the row/column swap
  reproduces the reviewer's figures exactly — −27.927000063 m against a true
  −33.084999085 m, a **5.158 m** error — and the geometry check was confirmed
  load-bearing *on its own*, refusing the swap with the checksum disabled, so it
  is not merely masked by the hash. Generic header guards (non-positive
  spacings, a grid too small for the 3×3 interpolation stencil) were likewise
  confirmed to refuse independently. Hashing costs 2.1 ms and a cold
  `default_grid()` 26.4 ms, once per process — measured by the lead, not
  material.

  A geometry **tolerance** of 1e-9° is a disclosed convention, not a citation:
  the shipped header stores one arcminute as `0.016666666667`, about 3.3e-13°
  from the double nearest 1/60, so an exact comparison would reject the genuine
  NGS file. NGS publishes no tolerance for reading back its own header.

  The payload is also scanned for non-finite values. Strictly redundant with the
  SHA-256 on the shipped tile, but `load_grid` accepts any path, and a NaN cell
  is the worst kind of failure: neither an exception nor a number, it propagates
  through interpolation into `h = H + N` and out into the elevation and combined
  factors, landing in the audit file beside real values. 11 ms against the 22 ms
  unpack already being done. A plausibility *range* check was deliberately not
  added — a "no data" sentinel such as 9999 is finite anyway, and a range would
  make the reader useless for a non-CONUS tile.

### #10 — 2026-08-05 — Interim gate finding #7 REJECTED, with evidence

The reviewer reported that `python -O -m pytest` strips the numerical
assertions, making the optimized run meaningless. **This is not true of how the
suite is run.**

Its probe imported a test module directly (`import tests.test_lambert as t;
t.test_...()`), which bypasses pytest's assertion-rewriting import hook. Under
that access pattern `-O` does strip asserts — but the program never runs tests
that way.

Falsified directly against a real test module: a genuine NCAT anchor was
corrupted by 999 m and the suite run both ways with `__pycache__` cleared
between runs.

    py -m pytest tests/test_lambert.py     ->  1 failed, exit 1
    py -O -m pytest tests/test_lambert.py  ->  1 failed, exit 1

pytest's rewriting is applied at import by its own hook and survives `-O`. The
optimized run is not vacuous. Recorded here so the question is settled by
evidence rather than re-litigated.

### #9 — 2026-08-05 — Subagent work packages resumed per the owner's method

WP0–WP5 were written by the session lead alone. `docs/method/METHOD.md` §3 has
subagents write and the lead independently re-derive; the lead did both halves.
Defensible for WP1 (the load-bearing math, where re-deriving a subagent's
version costs more than writing it) but carried through WP2–WP5 without being
flagged, which was not. Corrected: WP5's test suite and WP6's GUI are subagent
packages, reviewed and re-derived before acceptance.

### #8 — 2026-08-05 — GEOID18 interpolation is biquadratic, settled by measurement

> **CORRECTED AT THE WP-V4 GATE, 2026-08-07.** The first sentence below is
> false. NGS *does* document it: NOAA Technical Memorandum **NOS NGS-84,
> "Biquadratic Interpolation"**, describes the method as relying on "the nearest
> 3×3 set of grid points to the point of interpolation", and INTG's published
> Fortran source anchors on the nearest node —
> `irown = nint((xlat-glamn(k)) / dla(k)) + 1`, then rows `irown-1, irown,
> irown+1`. Source fetched and read directly at
> `https://www.ngs.noaa.gov/GEOID/G99BM/intg.f`.
>
> **What survives:** biquadratic over bilinear, which is what this amendment
> actually decided and what the measurement actually showed. **What does not:**
> the claim that this program's *anchoring* is INTG's. It is not — this program
> anchors below the point, INTG centres on the nearest node.
>
> **Why it was not simply fixed here.** The 20 anchors below cannot tell the two
> anchorings apart: they are quantized to 0.001 m and all candidates sit inside
> that noise. A 120-point sample taken where the anchorings diverge most
> reverses the ranking (floor rms 0.715 mm, nearest-node 0.454 mm), so
> nearest-node is probably right for GEOID18 too. The cost of the present
> anchoring is about 4 mm at worst in a *reported geoid separation*, ~6e-10 in an
> elevation factor, well inside GEOID18's own 30–60 mm model uncertainty — so no
> coordinate moves and nothing on a sealed survey changes. Re-anchoring released
> code deserves its own work package, its own discriminating anchors, and the
> owner's decision. **Raised, not taken.**

NGS does not document which interpolation scheme its INTG program uses for the
geoid grids — not in the GEOID18 readme, not on the computation or technical
details pages. The plan therefore called for implementing both candidates and
pinning whichever matched NGS's own service.

Measured against 20 frozen anchors from the NGS geoid API (`model=14`), at
positions deliberately placed well inside grid cells so interpolation is what is
actually being tested:

| Scheme | Worst error vs NGS |
|---|---|
| Bilinear (2×2) | 1.3 mm |
| **Biquadratic (3×3 Lagrange)** | **0.6 mm** |

NGS publishes geoid heights to 0.001 m, so ±0.5 mm is pure quantization.
Biquadratic sits at that floor; bilinear is measurably worse.

**Decision: biquadratic.** `geoid_height()` uses it. Both implementations are
retained, and `test_biquadratic_beats_bilinear_against_ngs` keeps the comparison
live so a future change that quietly switched schemes would show.

Consequence is small either way — a millimetre of geoid error moves an elevation
factor by about 1.6e-10 — but the geoid height itself is reported in the job
record, so it should match NGS.

The grid tile is `data/g2018u3.bin`, CONUS grid #3 (40–58 °N, 96–77 °W, 1′,
1081 × 1141), committed unmodified from NGS at 4,933,728 bytes, SHA-256
`cd2080f9…be3b3`, pinned by test.

### #6 — 2026-08-05 — A zone's polynomial band is a measured property, distinct from its geographic extent

**Defect found and fixed during WP3.** The first implementation of the engine
cross-check used each zone's geographic extent as the band inside which the
0.5 mm agreement is *enforced*, widened by a tenth of a degree of slack. That
was wrong in both respects.

The manual publishes no fitted band — it says only that the Appendix C
coefficients were fit to ten data points per zone (PDF p. 54). So the band was
measured directly: the latitude range over which the two engines agree within
NGS's 0.5 mm, worst case across each zone's full longitude span.

| Zone | Measured 0.5 mm band | Geographic extent | Stored band (rounded inward) |
|---|---|---|---|
| MI North | 44.192 – 48.901 | 45.0 – 48.4 | 44.25 – 48.85 |
| MI Central | 43.236 – 46.128 | 43.5 – 46.0 | 43.30 – 46.05 |
| MI South | 41.403 – 44.312 | 41.6 – 44.3 | 41.45 – 44.25 |

Michigan South's band ends at 44.312 while its coverage reaches 44.3 — a margin
of one hundredth of a degree. Adding 0.1° of outward slack pushed the *enforced*
range past where the polynomial is valid, so a legitimate Michigan Central →
Michigan South conversion raised a hard `EngineDisagreementError` at 0.6186 mm.
The program refused a conversion it had computed correctly.

**Decision.** `Zone` now carries `band_lat_min` / `band_lat_max` as measured
data, rounded **inward** so the stored band can never claim more than the
measurement supports, and `_within_fitted_band` uses them with no slack.
`tests/test_polynomial_band.py` re-measures on every run and fails if either
stored bound has drifted outside the real one, or if the engines ever disagree
anywhere inside the stored band.

Caught by `test_zone_to_zone_round_trips[MI-C->MI-S]`.

### #7 — 2026-08-05 — No source file may carry a UTF-8 byte order mark

A PowerShell 5.1 `Set-Content -Encoding utf8` edit prepended U+FEFF to
`zones.py`. Python's importer tolerates it (source is read as utf-8-sig), so the
program kept working — but `ast.parse` on text read as plain utf-8 does not, so
the four architecture scanners crashed while the code they guard appeared fine.
Checks breaking silently while the thing they check looks healthy is the worst
available failure mode.

Now machine-enforced by `test_no_source_file_carries_a_utf8_byte_order_mark`,
with an anti-vacuousness check that reproduces the `SyntaxError`.

### #5 — 2026-08-05 — Measured: the polynomial method alone would be wrong by metres across zones

The plan asserted that the Appendix C polynomials degrade outside their fitted
band and that this matters for cross-zone work. That is now measured, not
asserted. A cross-zone conversion evaluates the **target** zone's polynomial at
the **source** point's latitude:

| Point in | Expressed as | Latitude | Polynomial error vs rigorous |
|---|---|---|---|
| MI North | MI South | 48.40 | **3355 mm** |
| MI North | MI Central | 48.40 | 408 mm |
| MI Central | MI South | 46.00 | 159 mm |
| MI South | MI Central | 41.60 | 147 mm |
| MI South | MI North | 41.60 | 110 mm |
| MI Central | MI North | 43.50 | 4 mm |

Inside its own zone the same method agrees with the rigorous equations to
0.0775 mm (MI North), 0.3382 mm (MI Central) and 0.4304 mm (MI South) — all
within the 0.5 mm NGS fitted them to.

**Consequence.** The prior MATLAB tool (`docs/reference/SPC_converter_AllZones_Elev.m`)
uses the polynomial method alone. Had this program done the same, a Michigan
North point expressed in Michigan South coordinates could have been wrong by
over three metres, with nothing in the output to reveal it. The two-engine
design (§5) is what surfaces this, and the rigorous equations are what get it
right.

Pinned by `test_cross_zone_conversion_is_where_the_polynomial_method_actually_fails`.

**This also constrains how the cross-check may be applied.** The 0.5 mm
agreement requirement can only be enforced where both engines are valid — that
is, when the point lies inside the target zone's fitted band. Outside it, the
disagreement is expected and is the polynomial's fault, not a defect. The
pipeline therefore treats an out-of-band point as a *warning carrying the
measured discrepancy*, never as grounds to refuse a conversion the rigorous
engine handles correctly.

### #4 — 2026-08-05 — The manual's printed 1/f and e² are mutually inconsistent at the last place

Manual p. 23 prints both to 14 significant digits, each correctly rounded from
the exact GRS 80 values:

    1/f = 298.25722210088      (exact: 298.257222100882711...)
    e²  = 0.0066943800229034   (exact: 0.006694380022903416...)

Deriving e² from the *printed* 1/f gives 0.006694380022903476 — about 1.5 units
in e²'s last printed place, 6.0e-17 absolute. The two published figures cannot
both be reproduced from one another at full printed precision. This is
independent rounding, not an error in the manual.

**Decision: keep fidelity to the committed source.** `ellipsoid.py` stores the
printed 1/f, because that is the number a reader checking our work against the
manual would use, and derives everything else from it. The consequence is
measured rather than assumed: `test_the_ellipsoid_rounding_choice_cannot_move_a_coordinate`
recomputes Michigan coordinates on an ellipsoid built from the unrounded
flattening and bounds the difference at **9.3e-10 m** worst case across all
three zones — six orders of magnitude below the 0.5 mm the two engines are held
to.

### #3 — 2026-08-05 — Inverse latitude iterates to convergence, not a fixed count

Manual §3.14 (p. 39) says to apply the Newton correction and "iterate two
times". We iterate to machine precision (correction < 1e-15 on sin φ) with a
ceiling of 12 iterations, and raise `ConvergenceError` if that ceiling is hit.

Reason: a fixed iteration count silently returns a half-converged latitude if
the starting approximation is ever poor. The manual's count was chosen for hand
calculators working inside a zone; this program converts points *between* zones
and must behave correctly further from the central parallel. Iterating to
convergence is strictly tighter and fails closed. Verified: round-trip error
across a 9×9 lattice over each zone's full extent is below 1e-11 degrees, about
one micrometre.

### #2 — 2026-08-05 — Package layout deviates from the plan's flat directories

The approved plan named three top-level directories `spc/`, `fileio/`, `gui/`.
Implemented instead as one distribution package `michspc/` containing those
three as subpackages. Reason: three generic top-level package names would
pollute the namespace on install and complicate the frozen bundle, while the
architecture tests and the stdlib-shadowing rule are unaffected. The `fileio`
naming decision (never `io`) is unchanged and still enforced.
