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
