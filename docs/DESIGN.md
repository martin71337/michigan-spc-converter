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
