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

SPCS2022 is in beta with official release in 2027; NAD 83 is being replaced by
NATRF2022. Michigan's committee kept Lambert conformal conic and the same three
zones, redesigned as low-distortion projections. The seams that let that arrive
as data rather than a rewrite:

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
- Longitude sign convention is **selected by the user with no default**. The
  manual and the prior MATLAB tool use positive-west; NCAT, OPUS, GPS and GIS
  use negative-west. A silent default here throws a Michigan point ~340 miles.
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
- Longitude sign convention: explicit GUI selector, no default.
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
| 1 | CRITICAL | Geodetic input carries no reference frame, so a NATRF2022 position is silently projected as NAD 83 | **Open** |
| 2 | CRITICAL | Longitude domain unvalidated: 275.4445 (the 0–360 form of −84.5555) converts silently, 2.2 M m out of place | **Fixed** |
| 3 | HIGH | A non-finite input is downgraded to a warning by the out-of-band branch and returns NaN coordinates | **Fixed** at the engine; the policy branch is deleted by #12 |
| 4 | HIGH | `to_geodetic` re-projects the *polynomial* result, so a defect isolated to the *rigorous* inverse is invisible — an injected 0.01° error reported 0.032 mm agreement | **Open**; dissolved by #12 |
| 5 | CRITICAL | Caller-supplied `LambertConstants` were not bound to their zone: pairing MI South's constants with MI North's identity gave a coordinate **4,231 km** wrong, warnings only | **Fixed** |
| 6 | HIGH | The production geoid path never authenticates the grid, and a header with row/column counts swapped (1081×1141 → 1141×1081) preserves the payload length and is accepted, giving a 5.16 m geoid error | **Open** |

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
