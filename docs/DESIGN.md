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
  per point, with geoid separation from GEOID18.
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
| NGS NCAT service | Frozen fixtures in `tests/fixtures/` | Independent verification anchors |
| NGS geoid height API (`model=14`) | Frozen fixtures in `tests/fixtures/` | Geoid interpolation anchors |
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
currently the identity. Elevation is orthometric height and is **passed through
unchanged** — it does not depend on the horizontal zone.

Result records produced by the core are frozen. UI layers never mutate them.

## 5. Core computation

Two independent engines, both from the manual, both run on every point:

1. **Rigorous** — the general Lambert conformal conic mapping equations,
   manual §3.1 (pp. 27–29). Primary. Valid everywhere. Python's doubles supply
   the significant digits the manual warns are needed (§3, p. 25).
2. **Polynomial coefficient method** — manual §3.4 (pp. 52–55) with the
   Appendix C coefficients (pp. 103–104). Independent cross-check.

Disagreement beyond **0.5 mm** is a named, loud failure. The two are never
averaged, and the polynomial result is never silently substituted.

Why rigorous is primary: the Appendix C polynomials were least-squares fit to
ten data points inside each zone's own latitude band (manual p. 54). Converting
a point deep in one zone into a neighbouring zone's coordinates — the core use
case of this tool — is extrapolation for the polynomials but exact for the
rigorous equations.

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
data/             g2018u3.bin, unmodified from NGS, SHA-256 pinned
docs/             DESIGN.md (authority), method/, the NOAA manual, reference/
```

## 10. Deferred scope, with reasons

| Item | Reason deferred |
|---|---|
| SPCS2022 Michigan zones | Beta until 2027. The seam (§6) is built; the zones arrive as registry data plus a citation to NOAA SP NOS NGS 13 once NGS finalizes them. |
| NAD 83 ↔ NATRF2022 transformation | Requires NGS transformation grids that are not final. Refuses loudly meanwhile (§6). |
| UTM | Not requested. Requires the transverse Mercator engine (manual §3.2). |
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

**What it cost, measured:** worst change to a reported geoid separation ~4 mm in
the roughest cells (#36's figure, confirmed); at the 20 frozen anchors the
largest change is 0.83 mm; at the frozen self-test anchor (Cadillac) 0.09 mm,
far inside its 0.002 m tolerance; ~6e-10 in an elevation factor. **No coordinate
moves.** All figures sit far inside GEOID18's own stated 30–60 mm model
uncertainty.

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
