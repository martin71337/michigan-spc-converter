# PLAN: EPSG codes in every system label, and the three Michigan UTM zones

**Status: APPROVED by the owner 2026-10-29, building. Written by the session
lead.** DESIGN.md #72 opens it and records the owner's decisions; §1.2 below
is updated to them. Two owner instructions of 2026-10-29: (1) "add the epsg code for
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

### 1.2 Decisions (owner's, 2026-10-29, unless marked lead's)

- **D1 (owner). The zone label's code follows that side's Units box, unit
  named.** `Michigan South 2113 - NAD83(2011) (EPSG 6499 ift)` with
  international feet, `(EPSG 6498 m)` with metres, no code with US survey
  feet. The code shown is for the unit the Units box WOULD hold if that zone
  were chosen: the current unit if the zone publishes it, else the fallback
  `refresh_unit_combo` already applies (international feet if offered, else
  the zone's first unit). **One function states that rule and both the Units
  rebuild and the label call it.** Every zone label on a side is re-rendered
  (`setItemText`, which changes no selection and fires no index signal)
  whenever that side's Units box changes. FROM follows the input unit, TO the
  output unit.
- **D2 (owner). No EPSG code, no code shown**: every SPCS2022 zone, the
  NATRF2022 UTM zones, any zone in US survey feet. Never a guessed code.
- **D3 (lead's). Geodetic entries take the geographic 2D code** (6318, not
  6319): the height beside the latitude may be an elevation. No unit is named
  on a geodetic entry; its code does not depend on one.
- **D4 (owner). UTM is metres only.** The existing per-zone unit gate refuses
  feet, with UTM's own reason.
- **D5 (owner). UTM on both frames**: NAD83(2011) and NATRF2022, 15N/16N/17N,
  six records. Identifiers (lead's): codes `15N`/`16N`/`17N` on NAD83(2011)
  and `15N-2022`/`16N-2022`/`17N-2022` on NATRF2022; abbreviations
  `UTM15N` ... and `UTM15N-2022` ...; names in EPSG's own form,
  `NAD83(2011) / UTM zone 16N` and `NATRF2022 / UTM zone 16N`, so the audit
  CSV's zone cell, which prints the name alone, names the frame. A UTM label
  is the name, since it already carries the frame.
- **D6 (lead's). UTM is its own block, last in each dropdown, and one Options
  group, "UTM zones", on by default.** NAD83(2011) entries first, then
  NATRF2022. The frame graying of #64 applies unchanged.
- **D7 (lead's). Auto zone stays State Plane only.**
- **D8 (owner). Release 0.9.0**; the literal is `0.9.0-dev` from U1.

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

- **Zones are data** (`zones.py`): `UTM_ZONES`, six records (three zones on
  each frame) built from the zone number (central meridian derived as
  6z - 183, never typed),
  `TransverseMercatorDef(lat 0, k 0.9996, FN 0, FE 500,000 m)`, system `"UTM"`,
  frame NAD83(2011) or NATRF2022, units (metres,), easting range FE +/- 400 km (the SPCS 83
  reasoning), extent = the zone's six-degree band over Michigan's latitudes.
  `ALL_ZONES` appends them, so every existing index is unchanged.
- **One EPSG table** (`spc/epsg.py`), keyed by zone code + unit and by frame,
  checked against the registries at import, read only by labels. No
  computation reads an EPSG code.
- **Labels** (`gui/controls.py`): `zone_label` and `geodetic_label` append
  the suffix; a UTM zone's code is not repeated after its name.
- **Record** (`fileio/report.py`): a third METHOD arm for any job with a UTM
  zone (equations listed per projection present, UTM's defining authority,
  verification naming the NCAT anchors of the job's frame and, when a State
  Plane zone of either era is also present, that era's own verification
  paragraphs). **The era check moves from zone codes to frames**: UTM on
  NATRF2022 with an SPCS2022 zone is one frame and must convert; today's
  check sorts any non-SPCS2022 code into the 1983 era and would refuse it. The `Conversion` line
  names UTM rather than State Plane on a UTM job. **Every SPCS 83 and
  SPCS2022 record stays byte-identical** (the cross-version digest pins).
- **No change to** the projection engines, frames, HTDP, Auto zone, the
  vertical and geoid machinery.

## 4. Work packages

Reordered from the proposal: the zone records come first because the EPSG
table is checked against them, and **no UTM zone reaches a dropdown before
the record can describe it** (U5 after U4, the #41 rule). Until U5 the GUI
builds its zone lists from the era tuples it names today, and a pin says so,
the H2 precedent.

- **U0** recon (done, §2): `review/utm-u0/`.
- **U1** the six UTM records; the NCAT anchor fixtures built from the frozen
  responses (each file re-hashed against its pin, both frames); forward and
  inverse, convergence and scale pinned at NCAT's printed digit; zone 15 by
  the meridian-shift identity; PROJ as an optional, skipping third opinion;
  registry churn updated to true counts; the interim "not yet offered" GUI
  pin; version `0.9.0-dev`.
- **U2** the EPSG table (`spc/epsg.py`), checked against the registries at
  import; the unit-following labels (D1) on both tabs, one rule shared with
  `refresh_unit_combo`; every dropdown label pin updated.
- **U3** the job path: the unit gate's UTM reason; the frame gates for UTM on
  both frames (WGS 84 / ITRF -> NAD83 UTM works; NATRF2022 UTM against
  NAD83(2011) refuses, as SPCS2022 does; the NATRF2022 ellipsoid-height gate
  covers NATRF2022 UTM); end-to-end jobs through real files on both frames;
  audit CSV and clean export. **Interim gate over U1-U3.**
- **U4** the record: the UTM METHOD arm, the era check by frame, the
  `Conversion` line; every SPCS 83 and SPCS2022 record byte-identical.
- **U5** GUI: the UTM block, Options group, unit filtering on both tabs, the
  "not yet offered" pin retired; offscreen previews for the owner.
- **U6** self-test check (one UTM point per frame against a frozen anchor),
  `docs/RELEASE-NOTES-0.9.0.md` DRAFT, DESIGN.md §2/§10 body edits, REFREEZE
  row for the beta UTM anchors. **Closing gate over U0-U6**, fixes,
  re-confirmation.

**Known test churn.** Adding the three records breaks 20 existing pins that
count or enumerate zones, labels and Options groups (e.g. "all twenty-two",
"114 cross-era pairs", "the two eras concatenated"). Each is updated in the
package that causes it, to the new true count, never weakened to a range.

## 5. Still human

- The owner's screen review of the dropdowns and the Options dialog.
- One real UTM job checked against a known UTM coordinate.
- The release build on the owner's machine.

## 6. The lead's draft (not accepted)

Before this plan existed the lead drafted, inline and outside the method, an
EPSG table, three UTM records and a label change. They were removed from the
working tree before U1 (kept outside the repository as a patch) and are not
accepted work; the builders work from this plan.
