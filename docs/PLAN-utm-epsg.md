# PLAN: EPSG codes in every system label, and the three Michigan UTM zones

**Status: PROPOSAL, written by the session lead 2026-10-29. Nothing built is
accepted; no code is committed.** DESIGN.md #72 will open it when the owner
settles §1.2. Two owner instructions of 2026-10-29: (1) "add the epsg code for
the system in parenthesis for each system"; (2) "add capability to convert to
the utm zones that cover michigan".

**Revisits a recorded deferral.** DESIGN.md §10 lists UTM as deferred ("Not
requested. Requires the transverse Mercator engine (manual §3.2)") and says
nothing there returns without revisiting the decision. Both reasons are now
gone: the owner has requested it, and the TM engine exists (`tm.py`, built for
the five SPCS2022 TM zones, H1). #72 revisits it; §10's row is struck there.

**Process, unchanged** (DESIGN.md #61's instruction): the lead plans; Opus
subagents build the work packages to the lead's brief; the lead reviews every
diff and re-derives the load-bearing figures; gates are independent (Codex is
not available in this container, so an independent Opus reviewer, the owner's
standing fallback): one interim, one closing, narrowing re-confirmation until
approved. Every pin is falsified by seeding; suite green in `pytest` and `-O`.

## 1. Scope

### 1.1 What is asked

- **E. EPSG codes.** Every system entry in the four zone/geodetic dropdowns
  names its EPSG code in parentheses.
- **U. UTM.** Convert to and from the UTM zones covering Michigan: **15N**
  (west of 90 W, the western tip of Gogebic County), **16N** (90 W to 84 W),
  **17N** (east of 84 W).

### 1.2 Decisions for the owner (the lead's recommendation first)

- **D1. An SPCS 83 zone shows two codes, one per unit.** An EPSG projected
  CRS is a zone *and* a unit: Michigan South is 6498 in metres and 6499 in
  international feet. Recommended label:
  `Michigan South 2113 - NAD83(2011) (EPSG 6498 m / 6499 ift)`.
  Alternative: one code that follows the Units selector (more moving parts,
  and the label would change under the user's hand).
- **D2. Where no EPSG code exists, the label shows none.** Two real
  absences: (a) **no US survey foot code exists for any NAD83(2011) Michigan
  zone**; (b) **none of the 19 Michigan SPCS2022 zones has an EPSG code** in
  the newest dataset reachable here (v12.029, 2025-10-02). Newer EPSG
  versions could not be checked: epsg.io and apps.epsg.org are blocked from
  this container. A code is never guessed from the numbering around it.
- **D3. Geodetic entries take the geographic 2D code** (NAD83(2011) 6318,
  not 3D 6319), because the height beside the latitude may be an elevation.
- **D4. UTM is metres only.** NCAT prints UTM in metres only, and EPSG
  defines NAD83(2011) UTM 15N/16N/17N in metres only (6344/6345/6346). A UTM
  job in feet is refused by the existing per-zone unit gate, naming the
  reason.
- **D5. UTM is on NAD83(2011) only.** Any-to-any with the SPCS 83 zones,
  NAD83(2011) geodetic, and the WGS 84 / ITRF frames through the existing
  HTDP path. **Not on NATRF2022**: no EPSG code exists for it, and NCAT
  publishes no NATRF2022 UTM anchor this project has captured. NATRF2022 UTM
  is the same records on the other frame, and can follow later as data.
- **D6. UTM gets its own block, last in each dropdown, and its own Options
  group ("UTM zones"), on by default.**
- **D7. Auto zone stays State Plane only.** Auto picks SPC zones by county
  (MCL 54.231). UTM zone choice is by longitude, a different rule, and is
  not asked for.
- **D8. The release is 0.9.0** (a new coordinate system is a minor bump);
  the literal becomes `0.9.0-dev` in U1.

## 2. Recon already measured (U0, by the lead, 2026-10-29)

Reproducible from `review/utm-u0/` (to be committed with U1).

- **EPSG codes, read from the EPSG dataset v12.029** (PROJ 9.8.1's
  `proj.db`, via pyproj 3.8.0), and checked for substance, not only by name.
  Each projected CRS was run against MCX's own zone records:

  | System | EPSG | Check |
  |---|---|---|
  | NAD83(2011) / Michigan North, m / ft | 6495 / 6496 | 0.000 mm / 0.032 mm |
  | NAD83(2011) / Michigan Central, m / ft | 6493 / 6494 | 0.000 mm / 0.024 mm |
  | NAD83(2011) / Michigan South, m / ft | 6498 / 6499 | 0.000 mm / 0.016 mm |
  | NAD83(2011) / UTM zone 15N, 16N, 17N | 6344, 6345, 6346 | conversions 16015-16017 |
  | NAD83(2011), NATRF2022 geographic 2D | 6318, 10968 | |
  | WGS 84 (G1762), (G2139), (G2296) 2D | 9057, 9755, 10606 | |
  | ITRF2014, ITRF2020 2D | 9000, 9990 | |

  The "(ft)" CRSs are the international foot (0.3048 exactly); their
  sub-0.04 mm residual is EPSG rounding its false origins in feet. **EPSG
  numbers Central before North**, which is why this was read and not recalled.

- **The UTM oracle already exists in the repository.** The 212 production
  NCAT responses frozen at `review/autozone-r0/raw/ncat_probe/*.json`
  (captured 2026-10-22, SHA-256 pinned in `tests/fixtures/autozone_anchors.py`)
  each carry NGS's UTM northing, easting, convergence and scale factor. **The
  existing `tm.py`, given UTM's constants, reproduces all 212 at NCAT's
  printed precision**: worst 0.0005 m northing and easting (NCAT prints
  0.001 m), 5.0e-9 in scale (prints 1e-8), 0.005" in convergence (prints
  0.01"). 181 points are in zone 16 and 31 in zone 17. **None is in zone 15.**

- **Zone 15 and the far-from-meridian case, against PROJ** (EPSG 6344-6346,
  a third opinion only): worst 0.003 mm within 3.0 degrees of the central
  meridian, 0.04 mm within 4.6 (16N stretched over the whole Lower
  Peninsula), **2.9 mm at 8.5 degrees** (17N used at 90 W). The manual's
  series is ample inside any sane use; far outside the band the existing
  extent warning fires.

- **Where a UTM zone would otherwise inherit State Plane wording.** Each is
  a false sentence in a sealed record if left alone:
  - the record's `Conversion` line prints `Direction.value`, which reads
    "geodetic to State Plane" / "State Plane to geodetic";
  - `report._method_and_verification` sends any non-SPCS2022 zone to the
    frozen SPCS 83 METHOD arm, which says "Lambert conformal conic ...
    section 3.1" and "Twenty-seven positions spanning the three zones";
  - `job`'s unit-gate refusal has authority prose only for SPCS2022.

## 3. Architecture

- **Zones are data** (`zones.py`): `UTM_ZONES`, three records built from the
  zone number (central meridian derived as 6z - 183, never typed),
  `TransverseMercatorDef(lat 0, k 0.9996, FN 0, FE 500,000 m)`, system `"UTM"`,
  frame NAD83(2011), units (metres,), easting range FE +/- 400 km (the SPCS 83
  reasoning), extent = the zone's six-degree band over Michigan's latitudes.
  `ALL_ZONES` appends them, so every existing index is unchanged.
- **One EPSG table** (`spc/epsg.py`), keyed by zone code + unit and by frame,
  checked against the registries at import, read only by labels. No
  computation reads an EPSG code.
- **Labels** (`gui/controls.py`): `zone_label` and `geodetic_label` append
  the suffix; a UTM zone's code is not repeated after its name.
- **Record** (`fileio/report.py`): a third METHOD arm for any job with a UTM
  zone (equations listed per projection present, UTM's defining authority,
  verification naming the 212 anchors and, when an SPCS 83 zone is also
  present, the Appendix C and 27-anchor paragraphs). The `Conversion` line
  names UTM rather than State Plane on a UTM job. **Every SPCS 83 and
  SPCS2022 record stays byte-identical** (the cross-version digest pins).
- **No change to** the projection engines, frames, HTDP, Auto zone, the
  vertical and geoid machinery.

## 4. Work packages

- **U0** recon (done, §2) plus the committed harness `review/utm-u0/`.
- **U1** EPSG table and labels (E), every dropdown pin updated to the new
  labels, the version literal to `0.9.0-dev`.
- **U2** UTM zone records; the NCAT anchor fixture built from the 212 frozen
  responses (each re-hashed against its pin); forward and inverse pinned at
  NCAT's printed digit; a zone 15 pin by the meridian-shift identity; the
  PROJ third opinion as an optional, skipping test.
- **U3** the job path: unit gate and refusal prose; end-to-end jobs
  UTM <-> SPCS 83, UTM <-> NAD83(2011) geodetic, WGS 84 -> UTM; the audit CSV
  and clean export. **Interim gate over U1-U3.**
- **U4** the record: the UTM METHOD arm, the `Conversion` line, every
  non-UTM digest unchanged.
- **U5** GUI: the UTM block, Options group, unit filtering on both tabs;
  offscreen previews for the owner.
- **U6** self-test check (one UTM point against a frozen NCAT anchor),
  release notes `docs/RELEASE-NOTES-0.9.0.md` DRAFT, DESIGN.md §2/§10 body
  edits. **Closing gate over U0-U6**, fixes, re-confirmation.

**Known test churn.** Adding the three records breaks 20 existing pins that
count or enumerate zones, labels and Options groups (e.g. "all twenty-two",
"114 cross-era pairs", "the two eras concatenated"). Each is updated in the
package that causes it, to the new true count, never weakened to a range.

## 5. Still human

- The owner's screen review of the dropdowns and the Options dialog.
- One real UTM job checked against a known UTM coordinate.
- The release build on the owner's machine.

## 6. The lead's draft (not accepted)

Before this plan existed the lead drafted, inline and outside the method,
`michspc/spc/epsg.py`, the UTM records in `zones.py`, and the label change in
`gui/controls.py`. They are **uncommitted and ungated**, and are evidence for
U1/U2's briefs, not accepted work: the builder may start from them or
replace them, and the diff is reviewed as any other.
