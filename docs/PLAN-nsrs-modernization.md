# PLAN — The Modernized NSRS Build (NATRF2022 · SPCS2022 · NAPGD2022/GEOID2022)

**STATUS (2026-08-28): N0 IS DONE AND IT CHANGED THE PLAN — read
`review/nsrs-n0/FINDINGS.md` and DESIGN.md #61 before building anything.**

The owner approved this plan 2026-08-28; N0 ran the same day and returned:

- **Horizontal half: GO in full.** All 19 zone definitions captured and
  pinned; beta NCAT performs NAD83(2011)⇄NATRF2022 (web app ONLY — no REST
  API accepts any NATRF2022 token on either host; anchors are captured by
  form-driving, harness committed) and emits SPCS2022 coordinates for OMC,
  LC1 and TM zones including the pure-projection shape; EPP2022 captured;
  NGS's engine is open source (`github.com/noaa-ngs/ncat-lib`) — the
  reference-implementation path for H3. usft is `N/A` on every 2022 zone —
  the unit restriction's citation. Unresolved, owned by H3: the app's epoch
  labelling contradiction (input "epoch 2010.00", reported "Input Epoch
  2020.00").
- **Vertical half: DEFERRED by the owner (2026-08-28).** NGS publishes NO
  NAVD88↔NAPGD2022 product — no grid, no service, FAQ in the future tense.
  The N-packages (N1–N5 vertical items, the chained NGVD29 path, GEOID2022)
  do not run in this build; they return as data + anchors when NGS
  publishes. GEOID2022 IS published (in legacy `.b`/`.bin` as well as GGXF —
  **the build-time derivation tool below is unnecessary**; grids are
  time-dependent, bicubic, ~475 MB, no reference implementation, no API
  oracle, 2 Michigan-window test points) — all recorded for that future
  build.
- **Hazard, standing:** beta's REST API fails open (`200 OK` with
  `N/A`/`{}`). Legacy truth from `geodesy.noaa.gov` only; NATRF2022 truth
  from the frozen beta web-app captures.

**The build that proceeds is H0–H6** (H0 = N0 + DESIGN.md #61, done
2026-08-28) plus the packaging/release package, with the re-freeze
mechanism, the two interim Codex gates and the closing gate as planned. The
vertical sections below are retained as the deferred design of record;
DESIGN.md #61 is the authority for what was measured and decided.

## Context

NGS's modernized National Spatial Reference System goes official ~Q1 2027; its
definitional beta products were declared **stable for implementation** on
2026-05-28 (all on beta.ngs.noaa.gov, feedback periods complete). The owner's
instruction: **build and release now — "i want to have it ahead of time."**
This build makes MCX convert between everything: the 3 SPCS 83 zones, the 19
SPCS 2022 Michigan zones, and geodetic on either frame — any to any, with the
NAD83(2011)↔NATRF2022 transformation at the geodetic pivot — plus the
NAPGD2022/GEOID2022 vertical half, which DESIGN.md #32 requires before the
2022 zones become selectable. DESIGN.md **#21** is the standing opening spec.

**Design provenance:** drafted, then independently re-designed and verified by
two Opus design agents against the tree at 0.6.4 with file:line evidence; the
session lead spot-verified the load-bearing claims directly (the
three-caller `require_vertical_pair` fact, the hard-coded VERTCON constants at
report.py:288-291, the 14 `== GEODETIC` comparisons, the unguarded unit-combo
reads at window.py:618). This plan is the merged, verified result. It becomes
a DESIGN.md amendment on owner approval.

Tier sentence: a wrong coordinate lands on a sealed survey and moves a boundary.

**Model assignment (owner's instruction, 2026-08-28, clarified same day):
the session lead develops all plans and designs; Opus subagents perform
recon and build the work packages; the lead reviews every diff and
independently re-derives load-bearing math and claims before accepting;
Codex is the adversarial reviewer at every gate.**

## Settled by the owner during planning (2026-08-28)

| Question | Answer |
|---|---|
| Release timing | **Build and release now**, ahead of NGS official; every beta artifact capture-dated; recorded re-freeze obligation at official rollout |
| Vertical half | **Included** — full build in #32's order (vertical lands before 2022 zones are selectable) |
| Epochs | **NGS standard epochs only** (2010.0 → 2020.0 for the frames; GEOID2022 at its NGS standard epoch, measured at V0). No user-selectable epoch; epochs stated in outputs |
| GEOID2022 format | **Build-time conversion**: NGS's GGXF committed unmodified + SHA-256 pinned; a converted tile in GEOID18's `.bin` layout committed beside it; the byte-compare re-derivation is a **release gate that fails (never skips) without the dev tools**. If V0 finds NGS also ships a legacy binary, use it directly and the derivation package is deleted |
| NGVD29 ↔ NAPGD2022 | **Allow chained** in one job: both legs run, both models/grids/digests in the record, per-leg shifts disclosed, combined σ by root-sum-square (independence stated as fact, cited — NGS's own combination rule governs instead if V0 finds one); σ is N/A naming the leg whenever either leg publishes none |
| Zone dropdown | SPCS 83 zones first, separator, then 2022 statewide + 18 LDPs in NGS order; **every zone label names its frame, derived from `zone.frame.code`** (#58 pattern) |
| Units on 2022 zones | **Metres + international feet only**. GUI removes usft from the offering (filter idiom); `job.run` refuses authoritatively, citing NGS's usft exclusion (citation captured at V0) |
| Disclaimers | **MCX writes no caveat prose of its own on any surface** — facts only: models, digests, dates, epochs, arithmetic. **NGS's own published caveats stay, quoted with attribution** (owner's ruling 2026-08-28) — existing records stay byte-identical. The #50 absence-pin extends **per-block** to every new block |

Deliberately out of scope: user epochs / plate-motion modeling; IGLD 2020
(grids unpublished — but its datum record IS declared `DECLARED_NOT_USABLE` so
the forged-status guard stays testable once NAPGD2022 flips usable); UTM;
other states.

**The DESIGN.md amendment is itself a deliverable** (METHOD.md §2/§7): §2, §6
and §10 currently forbid this work; the amendment records the revisit of each
deferred item's reasons (lifted by NGS's 2026-05-28 stable declaration), the
recorded override of #32's ordering by the owner's scope decision (the
era-coupling *fact* stays true and is handled by per-side guards + facts in the
record), corrects §10's stale "the seam (§6) is built" sentence, and carries
the beta-artifact register + re-freeze obligation. It lands at H0/N0, before
code.

## N0/H0 — Measure before code (owner's Windows machine; geodesy.noaa.gov refused from the container)

Harnesses committed under `review/nsrs-n0/`, every capture SHA-256'd,
responses self-identifying (refuse mismatches), tolerances derived from
printed precision, "what these do NOT prove" stated — the
`vertcon_anchors.py` / `review/ncat-crosscheck/` pattern. GO/NO-GO items
first:

1. **GEOID2022 formats**: legacy binary offered? (If yes → use directly, delete N2.) Else GGXF structure: row order, longitude convention, spacing, units, sign, sentinels, `interpolationMethod` (a declared method different from biquadratic-nearest-node is a finding), epoch semantics (per-epoch grids vs static+rate, t0), per-point uncertainty product, sizes/URLs/digests.
2. **NAVD88↔NAPGD2022 product**: exists as files? form, byte layout (does the marker-validated `vertcon.load_grid` read it?), **sign re-derived from a raw cell** (never a comment), inverse = same grid sign-reversed or separate product, companion σ grid + Michigan bounds.
3. **Frame-transformation oracle hunt, in order**: beta NCAT frame transformation (DESIGN #21 recorded "no" on 2026-08-06; the 2026-08-28 research found NCAT v3.0 beta now does it — verify live) → NGS HTDP → published parameter sets alone. **Stop rule: with no oracle at level 1–2, the NAD 83 ⇄ NATRF2022 leg does not ship as usable** — the 19 zones still ship (fully verifiable against beta NCAT's SPCS2022 output within NATRF2022), and the bridge waits. Only measurement approves the arithmetic.
4. **Helmert/EPP provenance**: the exact document+table for every parameter (uncited = stop); EPP2022 CSV frozen; **the composition question settled by measurement** (whether plate propagation enters or the transformation reduces to the Helmert alone — the module docstring records the measured answer); intraplate residual for Michigan quantified; A→B→A algebraic-inverse closure (~1e-9 m); ellipsoid-height sensitivity swept h∈[0,500] m (expected ~µm; h defaults 0.0 as a disclosed convention, and a derived h′ never reaches an output — guard, not comment).
5. **`zoneDefinitions.json` frozen** (capture date, SHA-256, committed to `review/` and `tests/fixtures/` — shipped code never imports it): 19 Michigan rows transcribed; per-zone field semantics read not assumed (LC1 grid-origin vs central parallel; TM constants; OM: is −26° the initial-line or rectified-skew azimuth); `system` spelling and abbreviations from NGS's own strings.
6. **Beta NCAT anchors**: ≥3 per SPCS2022 zone both directions spanning each zone's band, **asymmetric about the OM center** (variant/sign discrimination — the project's signature defect class; same rule for TM convergence sign and LC1 k₀ location); frame lattice ≥20 points both directions; NAVD88↔NAPGD2022 20-point lattice + 5-point inverse; chained NGVD29→NAPGD2022 direct AND decomposed at the same points; GEOID2022 separations + discriminating fractional-cell set. Every fixture tagged `NGS beta` + capture date.
7. **σ combination rule**: does NGS publish one for stacked vertical legs (NOS NGS 68 / product docs / NCAT's printed σ on a chained request)? If yes it governs; else GUM (JCGM 100:2008 §5.1.2) is the cited method.
8. **usft-exclusion citation**; per-zone `easting_window_m` values hand-derived from captured extents (`None` = cannot discriminate, warning suppressed as stated fact); GEOID18/VERTCON coverage at every new zone extent, **Isle Royale first**; NGS's beta-status wording quoted verbatim for citations.

## Architecture (verified against 0.6.4; corrections from the Opus passes marked ✦)

### Core (`michspc/spc/` — stdlib-only; note the scanner also bans `json`/`struct`/`csv` there, so zone records are Python literals and only tests parse the frozen JSON)

- **`projection.py` (new)** — dispatch keyed on `type(zone.definition)`; ✦ `ProjectionKind` is **deleted as a stored field** (read nowhere today) — one dispatch table derives both the kind and the engine so they cannot disagree; `Zone.projection_kind` becomes a property. `GridPoint`/`GeodeticPoint` + input guards move here with re-export aliases (referenced nowhere outside lambert.py except test prose). ✦ Structural contract pinned over `ALL_ZONES`: every definition record carries `lon_origin`, `easting_origin`, `northing_grid_origin` with identical meaning (convert.py:228 and job.py:1558 already read `definition.easting_origin` blind). Cache `maxsize=None` (finite immutable registry; 32 has no headroom at 22 zones). `constants_for`'s two importers (convert.py:34, report.py:32) both go through the dispatcher.
- **`zones.py`** — definition union (2SP | 1SP | TM | OM, all frozen; `allowed_units` a tuple, keeping `Zone` hashable for the lru_cache — pinned); 19 records as literals, `system` per V0 spelling, `frame=NATRF2022`, per-zone citations naming the frozen capture; ✦ **`SPCS83_ZONES` + `SPCS2022_ZONES` with `ALL_ZONES` derived** — ~20 existing test sites that parametrize over `ALL_ZONES` assuming 2SP/NAD83 are repointed to the era tuple each actually pins (named list in the Opus report; no test silently narrowed); ✦ import-time uniqueness on **code, abbrev AND name** (era distinction must live in the strings — audit columns and archive stems can't gain era suffixes without breaking the byte pin; ambiguous NGS names become disclosed transcription conventions with NGS's string quoted); `Zone.allowed_units`; `Zone.easting_window_m: float|None` replacing `_EASTING_WINDOW_M` (convert.py:44), values from V0; a test cross-checks every transcribed field against the frozen capture (test-side only).
- **`lambert.py`** — `from_one_parallel`: defining k₀ lives only in the definition record; `k_origin` stays derived; the constructor's round-trip check is kept but ✦ **documented as a typo/float-pathology check, not verification** (it is algebraically an identity) — the numbers are verified externally by the beta anchors.
- **`tm.py` / `omerc.py` (new)** — NGS 5 §3.2/§3.3; every convention (OM variant, skew sign, TM convergence sign, LC1 k₀ location) **measured at V0**, never assumed; iterate-to-convergence-with-ceiling idiom; hand-derived expected values.
- **`frames.py`** — mirrors `vertical.py` line for line: `FrameStatus` (✦ **required field, no default** — mirroring `VerticalDatum`; plus `_canonical()` so a rebuilt record can't grant itself a status); `FrameTransformation` (`__post_init__` all-or-nothing identity check; `direction_statement` derived from parameters); `FRAME_TRANSFORMATIONS` MappingProxyType; `REQUIRED_FRAME_PAIRS` + import-time check; `require_frame_path` replacing `require_same_frame` at convert.py:299/367 (deleted); exceptions `FrameNotUsableError`/`FrameTransformationUnavailableError` under the `FrameMismatchError` base (what tests and the GUI catch). ✦ **The four pinned safety tests (test_convert.py:44-113, test_fileio.py:2935-2948) are replaced by successors, not deleted** — the same calls now pinned against the oracle; a new refusal pin uses a declared-not-usable **WGS 84** record (real, per #58's NAD83≠WGS84 rationale) so both refusals keep live counterexamples; each successor falsified. ✦ The reverse direction evaluates the **algebraic inverse** (not sign-flipped parameters), round-trip pinned.
- **`helmert.py` (new)** — pure stdlib geodetic↔ECEF (GRS 80, one record; the exact-1/f question is already bounded at 9.3e-10 m by DESIGN #4's existing test — a new bound covers only the ECEF round-trip), 14-parameter Helmert at epoch, Euler rotation, one public `transform_geodetic`; identity refuses parameters; composition per V0's measurement, recorded in the docstring.
- **`convert.py`** — `PointConversion` gains defaulted `target_frame/target_latitude/target_longitude/frame_transformation` (`None` on same-frame; three keyword-only construction sites verified tolerant; no test constructs one). ✦ **`latitude`/`longitude` stay the source-frame pivot** — every existing consumer (extent check, audit cells, and the geoid/VERTCON lookups, which are published against NAD 83) keeps reading them; the lookup-frame choice is bounded at V0 (~0.1 mm on N). ✦ The `ZONE_TO_GEODETIC` cross-frame direction is wired explicitly (convert then `transform_geodetic_position` at the pivot; exports take the target pivot). `JobSettings.target_frame=None` = source side's frame (today's behavior, byte-identical); GUI always states it.
- **`vertical.py`** — NAPGD2022 → USABLE (citation: beta facts + `NGS beta` + capture date); new records: NAPGD2022 identity, NAVD88↔NAPGD2022 (one-grid-two-signs **only if V0 measures that form**), and ✦ **`ChainedVerticalTransformation`** — a new frozen record under a fieldless `VerticalTransformationRecord` base (provably inert; field-tuple pinned), registered in `VERTICAL_TRANSFORMATIONS` and returned by `require_vertical_pair` — **dispositive because three callers re-derive the record** (job.py:1305, report.py:699, results_model.py:144/155, verified). Eight `__post_init__` branches (legs are registered single-leg records — checked at import so a chain cannot carry a private copy; continuity; no identity legs; no shared grid_key; depth 1; non-empty citations). Derived: composed `direction_statement` naming the unwritten intermediate; deliberately absent: `.model/.release/.grid_key/.sign` (grep-verified safe; the base protocol every consumer needs is pinned explicitly). ✦ IGLD2020 declared `DECLARED_NOT_USABLE`; ✦ the **six existing tests asserting NAPGD2022's refusal are rewritten as recorded supersessions** (named list in the Opus report), never deleted silently. `REQUIRED_VERTICAL_PAIRS` + the hand-written test mirror both extended.

### File layer

- **`geoid.py`** — `epoch: str|None = None`; one record per NGS standard epoch (uncacheable/unciteable/unbundleable otherwise — three independent reasons); GEOID2022 record with `vertical_datum=NAPGD2022` (all four latent guards verified live with no code change); derived `display_name` with epoch; ✦ **two-citation rule**: `source_citation` (the NGS GGXF) + `derivation_citation: str|None` with `citation` derived from both, and `__post_init__` refusing a record that presents a derived file's digest as NGS's; ✦ tile named `geoid2022_….bin` (**GEOID18's marker-free layout, not VERTCON's `.b`**) so it loads through `geoid.load_shipped_grid` unchanged.
- **`tools/derive_geoid2022_tile.py` (new, dev-only)** — h5py/netCDF4 confined to `tools/` + one test module; writes IKIND=1 little-endian real*4, south-first rows, 0–360 longitudes (all three substrate demands verified at ngs_grid.py:235/248/456/524); refuses an unexpected `interpolationMethod` or time model; **deterministic, pinned by double-run byte-compare**. ✦ Three falsification seeds: row flip omitted; row/column transposed **with the geometry record corrupted to agree** (#11-finding-6's 5.16 m class); longitude off by half a cell (center-vs-edge). ✦ The re-derivation byte-compare is a **release gate in `build_release.py` that fails without h5py** (a skipped test is not a gate); two new architecture pins (no h5py/netCDF4/numpy anywhere in `michspc/**`) with anti-vacuousness checks.
- **`vertical_grids.py` (new)** — `VERTICAL_GRID_PRODUCTS[grid_key]` dispatch; ✦ protocol is **`contains` + `reading_at`** (coverage decided by asking, not catching — WP-V6 LOW 7); ✦ rewires **four hard-coded sites, not one**: job.py:1137, report.py:288-291 (the record currently names VERTCON's files for ANY modeled transformation — a live defect for NAPGD2022), selftest.py:230-270, build_release.py:395-427 — plus michspc.spec. Completeness pins: every leg's key resolves; no orphan products; every file exists + hashes; ✦ **every ordered pair of usable datums resolves through `require_vertical_pair`** (9 of 9 — the dropdowns offer all usable datums with no pair filtering, so no selectable pair may refuse).
- **`job.py`** — chained execution entirely inside the modeled branch (job.py:1850's `else`): per-leg loop, each `apply_shift` in its leg's own source datum, **all-or-nothing coverage** (any leg uncovered → whole Z refused naming the leg — a partially-chained height is in the intermediate datum, the falsehood the existing rule refuses); `VerticalReading` gains `legs` (totals stay on the outer reading so every existing consumer works unchanged; constructor enforces sum/RSS/leg-matching arithmetic in `GeoidSwapReading`'s idiom); all legs' products resolved once per job before the row loop; ✦ **the era-guard refusal message is corrected for chains** (job.py:1026-1030 would state "no stage … is in that datum" while the intermediate stage is exactly that datum — a false sentence; pinned, falsified). Unit + `target_frame` refusals slot immediately after job.py:804 (after zone-presence establishes non-None, before the file read at :862; per-side rule). Pinned refusal ordering extended, never reordered.
- **`exports.py` / `report.py`** — conditional additions only (18-digest v0.5.0 cross-version pin green throughout): `Geoid epoch` column when the model has one; per-leg shift/σ columns on chained jobs (existing columns keep totals; row arithmetic stays closed); `Source frame`/`Target frame` + target pivots only when frames differ. Record: the VERTICAL DATUM TRANSFORMATION block becomes **three-way** (identity / single modeled — byte-identical / chained — per-leg, resolved through `VERTICAL_GRID_PRODUCTS`); CHAINED block naming both legs, the unwritten intermediate, and the σ method with citation; GEOID2022 METHOD block (GGXF source facts + derivation stated as fact); FRAME TRANSFORMATION block (direction statement, epochs, parameter citations, capture dates); per-kind zone blocks (defining constants labelled defining); era-correct verification prose (the "Appendix C … twenty-seven positions" paragraph is FALSE for a 2022 job — branch on system; ✦ the anchor-count literal stays in report.py and a **test** asserts it equals the fixture length — shipped code may not import tests). Clean PNEZD: five headerless fields, pinned. ✦ Absence-pin per-block on new blocks; NGS-quoted caveats exempt (owner's ruling).

### GUI

- ✦ `GEODETIC` string sentinel replaced by a frozen `GeodeticChoice(frame)` record + one `is_geodetic()` predicate; **the old name is deleted so all 14 comparison sites fail loudly at import until visited** (a tuple would have failed them silently). Per-frame geodetic entries ordered by `ALL_FRAMES` filtered to frames in use (registry order, not a set); `geodetic_label(frame)`; the #58 derivation pin generalizes, never deleted; test_gui.py:201's count becomes derived.
- Zone combos: placeholder, geodetic entries, SPCS83 zones, `insertSeparator` (carries no data — `direction_for` unaffected), 2022 zones; labels derive the frame code. Broken label pins are recorded supersessions (labels, not written outputs).
- Units: ✦ new guarded `unit_for(combo)` reader (filtering makes `None` reachable for the first time; today's raw `currentData()` would crash with Convert still enabled); offering never empty (pinned per zone); one owner method per combo's item list, pinned by AST scan (#57 rule); the filter-forced usft→ift swap invalidates any displayed result (pinned, falsified) and the new value is visible before Convert (#29/#33 class — verification is the user's responsibility; recorded).
- Datums/geoids: NAPGD2022 appears via `is_usable` (verified: exactly one production read site); NGVD29↔NAPGD2022 selectable and converts with **no GUI edit** once the chain is registered; ✦ the GEOID2022 default on a NAPGD2022 side is **pinned by name, not list position**.

### Packaging / self-test

Spec datas derive from `ALL_GEOID_MODELS` (auto-bundles GEOID2022) + `VERTICAL_GRID_PRODUCTS` (replacing hand-listed VERTCON names; the spec comment's "NGS's own filename" claim gains the derived case); **the GGXF is explicitly not bundled** (stated + pinned); `LAZY_IMPORTS` + `michspc.fileio.vertical_grids`; frozen-bundle **no-numpy/h5py pin** (sys.modules after a full conversion, anti-vacuousness by injection); three new self-test checks in the absent→altered→misread pattern (GEOID2022 via registry vs frozen beta anchor; NAVD88→NAPGD2022 end-to-end; chained job asserting both legs present and total = sum) plus a cross-frame and an SPCS2022 case; the suite/gate-vs-bundle division of labor stated in selftest.py's docstring. ✦ **The release gate refuses while any `NGS beta` tag remains unless an explicit acknowledgement flag is passed** — each beta release is a conscious act (the `-dev` idiom).

## Work packages (each: Opus-built, lead-verified, suite green in `pytest` AND `-O`, commit + push after gates, resume checklist at boundaries; `-dev` until release)

| WP | Contents |
|---|---|
| **N0/H0** | The measurement gate + the DESIGN.md amendment (deferred-scope revisit, #32 override, oracle fork decided). Nothing built before it closes |
| **N1** | Data landing: files + pins, two-citation records, beta fixtures frozen, `docs/REFREEZE-NSRS.md` + its two-way inventory test |
| **N2** | Derivation tool + byte-compare release gate + three seeds (deleted if V0 found a legacy binary) |
| **N3** | `vertical_grids.py` + the four sites rewired — **no behavior change, byte-identical against frozen digests** |
| **N4** | Vertical registry: NAPGD2022 usable, NAVD88 pair, IGLD2020 declared, six supersessions rewritten |
| — | **Interim Codex gate #1** over N0–N4 (readers + registry; the sign determination is the most dangerous fact in the feature) |
| **N4b** | `ChainedVerticalTransformation` + base + eight branches + leg-registration check + protocol pin (core only) |
| **N5** | Job wiring: `VerticalReading.legs`, per-leg loop, all-or-nothing coverage, era-guard message fix, once-per-job resolution |
| **H1** | `projection.py`, engines, `from_one_parallel`, `ProjectionKind` deletion — anchors reproduced within NCAT's printed precision |
| **H2** | Zone registry, era tuples, ~20 test repoints, uniqueness, easting windows, capture cross-check, coverage at Isle Royale |
| **H3** | `helmert.py` + `frames.py` (gated on H0's oracle fork): pinned-test successors each falsified, algebraic-inverse round-trip |
| **H4** | `convert.py` two-pivot + `job.py` gates + `ZONE_TO_GEODETIC` cross-frame — **exit: the 18-digest pin green untouched** |
| — | **Interim Codex gate #2** over H1–H4 + the N/H integration surface (the cross-frame + cross-datum job crosses both halves) |
| **N6/H5** | Outputs: three-way vertical block, chained/GEOID2022/FRAME blocks, per-kind zone blocks, era prose, conditional columns, per-block absence pins, anchor-count test |
| **N7/H6** | GUI: `GeodeticChoice`, zone list, `unit_for` + filtering, invalidation pins falsified |
| **N8** | Packaging/self-test/gates, digest fixture extended from this release's own worktree (#55 mechanism), release notes |
| — | **Closing Codex gate** over the full diff; narrowing re-confirmation until APPROVED. This tier runs every gate |

Release: 0.7.0 via `py tools/build_release.py` on the owner's machine (all
eight gates + the new derivation and beta-acknowledgement gates), tag, GitHub
Release.

## The re-freeze obligation (mechanism, not memory)

`NGS beta` token + capture date on every beta artifact; `docs/REFREEZE-NSRS.md`
mapping each artifact → recapture harness → authenticating pin; a suite test
that fails on an unlisted tagged artifact AND a listed untagged one; the
release-gate acknowledgement flag. At official rollout: re-run every harness,
any changed digest ⇒ new tiles + a **full** gate cycle; a DESIGN.md amendment
records the event.

## Verification

Hand-derived expected values; every new pin falsified by seeding its defect
(file-snapshot restore); external truth = the frozen beta lattices at ±0.5 of
printed precision + variant discrimination + round-trip closures; the
18-digest cross-version pin green untouched until extended at release;
end-to-end file→job.run→ZIP→parsed-CSV for cross-frame and chained shapes;
frozen-bundle self-test; the build gates. New `spc/` modules are inside the
AST scanners with anti-vacuousness checks.

## Risks

1. **Beta drift** — capture dates, re-freeze mechanism, NCAT re-check at each gate.
2. **Convention defects** (OM variant, Helmert composition, NAPGD2022 sign) — neutralized only by N0-before-code with discriminating anchors.
3. **No independent oracle for the frame leg** — the stop rule: zones ship, the bridge waits.
4. **Sealed work carrying beta-era numbers** — the owner's recorded decision; factual provenance lines are the defense; top adversarial-gate target.
5. **Chained-σ honesty** — RSS with independence stated as fact and cited; NGS's rule governs if published; N/A never partial.
6. **Silent GUI breakage** — the sentinel deletion forces loud failure; invalidation pins per #26, each falsified.
7. **Repo/installer growth** — V0 sizes the GGXF; digest-only fallback is the owner's call if large.

## Still human, still outstanding

Clean-profile install proof (METHOD.md §6); a real PNEZD file committed as a
fixture; the owner's screen review of every new control before 0.7.0; field
validation of the new paths (real jobs end to end on 2022 surfaces, the #59
pattern) before any sealed deliverable leans on a 2022-era output.
