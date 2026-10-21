# Interim gate 2, WGS 84 build: independent adversarial review of W3, W4 and W4b

**Reviewer:** an independent Opus reviewer. I worked blind to the lead's review of this code.

**Scope:** the committed diff `bd2b325..HEAD` on `claude/brave-noether-88m7x1`:
- W3 = `8201968`
- W4 = `4454a54`
- W4b = `4b7833a`
- `1210d34`, the brief, was read and not reviewed

Nothing uncommitted was in scope. In the repository I wrote only this file. The `git worktree` at `bd2b325` that I used for the regression comparison has been removed, and `git status` is clean. All scratch work is in `/tmp/claude-0/gate2/`.

**Oracle:** NGS HTDP v3.6.0, compiled from `review/wgs84-w0/htdp-v3.6.0/*.f` with `gfortran -O0 -std=legacy -w`. Its SHA-256 is `3738c50c…f77f8f`, the same as W0's build. I drove it with calendar dates, with NAD 83 always at 1 1 2010. The program's NCAT-verified projection, GEOID18/GEOID12B readers and VERTCON reader serve as the second leg wherever a number goes beyond HTDP's print.

## Verdict in one paragraph

**No coordinate or height is wrong anywhere I looked.**
- I sent 1,500 random transformed jobs (about 6,700 points) through `job.run`, `write_all`, unzip and parse. They cover every direction, frame, height kind, vertical mode, unit and longitude convention, with dates from 2010-01-01 to 2026-10-20, and blank and 0.00 Z values. I compared every member against the HTDP binary plus the projection, geoid and VERTCON legs, and nothing differed.
- The verifiers refused none of 37,620 correctly converted archives' points.
- No same-frame job changes by a byte, except the vertical-only geodetic record that W4b supersedes on purpose.
- No interface path reaches the five frames, GEODETIC_TO_GEODETIC or the observation date.

**The records are where the findings are:**
- Two sentences are false in configurations the core reaches. One of them is also in released, GUI-reachable output, and W4b set out to remove exactly that kind of sentence.
- One pin gap: a seeded 1.1 m error in NAVD 88 elevations on reverse-direction ellipsoid jobs leaves the whole suite green.

**Counts:** 2 HIGH, 1 MEDIUM, 5 LOW, 5 INFO. No CRITICAL.

---

## Findings

| # | Sev | Finding | Concrete input | Observed | Expected | Root cause |
|---|---|---|---|---|---|---|
| H1 | HIGH | The job record says **"Every position and ellipsoid height column names its frame."** That is false on every transformed job. | Any transformed job. For example, ZONE_TO_GEODETIC from MI-S to WGS84(G2139), dated 2019-03-01, with ELLIPSOID heights. Or VERTICAL_ONLY on ITRF2020 with the row `1,43.0,84.5,165.000`. | The audit CSV's `Source latitude`, `Source longitude (as in file)`, `Target latitude` and `Target longitude (as written)` name no frame. On G2Z, G2G and VO the Source pair holds WGS 84/ITRF positions. On Z2G and G2G the Target pair holds the target frame's. **On VERTICAL_ONLY the Target pair holds the ITRF2020 input mirrored**, which contradicts the convention in the `frame_transformation_columns` docstring ("the source columns are in its first frame and the target columns in its second"). The pin `test_the_audit_header_is_exactly_this` enshrines these unnamed headings, while the record sentence it sits beside is never checked. | Either the four headings name their frame (for example `Target latitude (WGS84(G2139))`), or the record states which columns do. | `exports._frame_named` renames only the pivot's four cells, the factors' ellipsoid height and the supplied-height columns. `report.build_report` (FILES WRITTEN, audit paragraph) states the sentence as universal. **Reach:** every transformed job through `job.run`/`write_all`. No interface reaches it until W5, and the GUI will after W5. No number is wrong, but the sentence is false in the document a surveyor keeps. |
| H2 | HIGH | **"The elevation and combined factors were computed from the SOURCE-datum (NAVD88) height"** is printed on jobs with no zone and therefore no combined factor. The same record then says "No combined factors exist for this job". | (a) VERTICAL_ONLY, geodetic NAD83(2011), NAVD88 to NGVD29, GEOID18, row `1,43.0,84.5,165.000`, positive west. (b) GEODETIC_TO_GEODETIC from WGS84(G2296) to NAD83(2011), 2025-06-15, HORIZONTAL_AND_VERTICAL, NAVD88 to NGVD29. | Both records print the "Factor height" paragraph quoted in the finding title. The SCALE FACTOR SUMMARY then says "no grid scale factor and no combined factor exists for any point" and "No combined factors exist for this job". The audit's Combined factor cells read N/A. | "The elevation factor was computed…", which is the zone-less wording W4b gave the ELLIPSOID block (`_ellipsoid_height_method_block`) and ELEVATIONS. | `report._vertical_method_block`, the `factors_use_source_era` paragraph (report.py:650-664), has no zone-less branch, and W4b's sweep missed it. **Reach:** (a) is reachable from the released 0.7.1 GUI (vertical mode, NAD 83 geodetic input) and has been present since #41. (b) is new with W4's direction. This is the #42 finding-3 class, which #42 itself graded MEDIUM. Under this brief's definitions a false record statement in a reachable configuration is HIGH. |
| M1 | MEDIUM | Pin gap: the suite never runs an ELLIPSOID job in a vertical mode on a path **out of** NAD 83 (Z2G, or G2G reverse). That is the only case where the pivot h and the target-frame h differ, so `H = h - N` using the wrong one goes undetected. | Seed S07, in `job._convert_row`: `elevation_m = conversion.pivot_ellipsoid_height` becomes `elevation_m = conversion.target_frame_ellipsoid_height`. Then ZONE_TO_GEODETIC from MI-S (the NAD 83 point 43.0 N, 84.5 W at h = 165.000 m) to WGS84(G2296), 2025-06-15, ELLIPSOID, HORIZONTAL_AND_VERTICAL, NAVD88 to NAVD88. | **The suite is fully green (0 new failures)**, and the archive writes NAVD 88 **196.986 m**. | 198.085 m: HTDP leaves the NAD 83 h at 165.000 and N = -33.085. The seed is 1.099 m low, and my end-to-end harness flags 26 of 150 random jobs under it. | Every vertical-mode ellipsoid pin runs a path into NAD 83 (G2Z, G2G forward, VO), where `target_frame_ellipsoid_height == pivot_ellipsoid_height` by construction. Seed S17 (`pivot_ellipsoid_height` always returning the handed-in value) is caught, but only because it breaks the forward cases. The production code is correct today; this is a gap that would let a wrong elevation through. |
| L1 | LOW | The `today()` seam's UTC half has no working pin. | Seed S14: `return max(local, utc)` becomes `min(local, utc)`. | Suite green. `test_today_is_never_earlier_than_the_local_date` asserts `today() >= date.today()`, and `min` also satisfies that anywhere west of UTC, including Michigan, where UTC is the later clock. It is trivially true in this UTC container. | A pin that monkeypatches the two clocks, for example local 2026-10-20 with UTC 2026-10-21, and requires that a 2026-10-21 observation is accepted. | The property #70 records ("an evening session is never refused as future-dated") is not tested. If it regressed, legitimate evening jobs would be refused. |
| L2 | LOW | The realization-period warning reads as though the input were WGS 84 even on jobs that write WGS 84. | ZONE_TO_GEODETIC from MI-S to WGS84(G2139), dated 2019-03-01. | "The positions are stated in WGS84(G2139) … a file labelled with the wrong realization looks exactly like this. Check which realization the positions are in." The input is NAD 83 grid, and G2139 is the output the user asked for. | On a path out of NAD 83, the warning should say that the requested output realization was not in use on that date. | `job._require_the_observation_date` has one message for both directions. |
| L3 | LOW | The round-trip sentence states W0's bound, measured over 1997–2026.8, as if it held always. The program accepts dates back to 1907. | An ITRF2020 or WGS 84 job dated before about 1985. | My measurement through `michspc.spc.htdp`, which is identical to the binary: east non-closure 1.13e-4 m at 1950 and 2.06e-4 m at 1908. | The record says "up to … 6.4e-5 m east". | `report.ROUND_TRIP_NON_CLOSURE` is a constant. The bound holds for 2010–2026 (I measured 3.8e-5 m east over 30,000 records). Either qualify it with its epoch range, or derive it. |
| L4 | LOW | An HTDP velocity-window refusal through `job.run` names no point, and on paths out of NAD 83 it labels the NAD 83 position with the target frame. | ZONE_TO_GEODETIC from MI-S to WGS84(G2296), row `1,0,0,,a`. | "Cannot transform the position at latitude 32.026364, longitude -127.914179 (WGS84(G2296))". That position is the NAD83(2011) pivot. The message also advises checking "that its longitude is negative west", which is irrelevant to a grid input. One such row refuses the whole file without a point id. | The message should name the point and name the position's own frame. | `htdp._window_cell` receives the non-NAD 83 frame "for messages", and `job._convert_row` does not wrap the error with its `context`. Note for W5: `HtdpRefusal` subclasses neither `ValueError` nor `FrameMismatchError`, so the GUI must catch it explicitly. |
| L5 | LOW | Stale numbers in two test docstrings. | `tests/test_frame_disclosure.py:313` and `:380` | Both cite "42.9999914437 N, 84.4999892421 W for G2296". | The fixture (`htdp_w3_anchors.py:100-101`) and my build of HTDP both give 42.9999914726 and 84.4999892398. | The docstrings were not updated when the fixture was. The assertions read the fixture, so only the prose is wrong. |
| I1 | INFO | The writers and the three verifiers share one rule, `job.written_geodetic_position`. | Seed S02: that function returns the pivot. | Every archive writes, and the pivot appears under a WGS 84 label. No verifier objects, because they check against the same rule. The suite catches it with 32 failures in the end-to-end HTDP pins. | — | This is by design (one statement per fact). The verifiers prove that the files agree with each other and with the conversion record, not with HTDP. The end-to-end pins are what hold the number. |
| I2 | INFO | Some seeds make no measurable difference. | S19 (geoid read at the external position instead of the pivot) and S22 (the DD join reads `output_northing` instead of the stated position). | Suite green and my harness green. | — | The geoid slope over about 1.3 m is below 1e-5 m, under every print. `output_northing` *is* the stated position by construction. Neither is a defect; neither can be pinned at the printed precision. |
| I3 | INFO | An ITRF job with an implausible date gets no warning. | ITRF2020 dated 1925-06-15, where 2025 was meant. | The job converts silently and moves about 1.7 m. | — | Plan D9 deliberately gives ITRF no period warning. Whether a sanity window is wanted is the owner's call. |
| I4 | INFO | Two pre-existing ellipsoid refusals fire after the file is read. | ELLIPSOID with `geoid_model=None`; ELLIPSOID with a geoid swap. | Both refuse, but after `pnezd.read`. | — | Both date from 0.6.0, not from this diff. Every W3 gate (stray frame fields, frame path, observation date, the NATRF2022 ellipsoid gate) fires before the read, as I checked with a missing input path. |
| I5 | INFO | The realization warning is job-level only. | Any job carrying that warning. | It appears in the record's WARNINGS section but not in the audit CSV's per-row Warnings column. | — | This is by design (`JobResult.job_warnings`). A row cut out of the CSV does not carry it. The W5 GUI warnings field must read it as well. |

---

## Clean surfaces, and how each was checked

### 1. Numbers through the real file path: 1,500 jobs, 0 mismatches

**Harness:** `/tmp/claude-0/gate2/e2e.py`, seed 7, 1,500 jobs. The jobs were spread over:
- G2Z: 304
- Z2G: 293
- G2G forward: 327
- G2G reverse: 292
- VO: 286

**Each job used random draws of:**
- the frame, out of all five;
- the height kind, ORTHOMETRIC or ELLIPSOID;
- the mode, HORIZONTAL or HORIZONTAL_AND_VERTICAL (VERTICAL for VO);
- the vertical pair: NAVD88 to NAVD88 under GEOID18 or GEOID12B, NGVD29 to NAVD88, NAVD88 to NGVD29, and the GEOID12B-to-GEOID18 swap;
- the input and output units, m, ift or usft;
- the longitude convention, either;
- the date, 2010-01-01 to 2026-10-20, with about 8% exactly 2010-01-01;
- 1 to 8 points across both peninsulas, with about 15% blank Z and 7% `0.00` Z.

**Every point was checked against:**
- HTDP's print for the pivot and the external position;
- the program's projection of HTDP's pivot (grid within 1.2e-5 m plus half a written unit);
- GEOID18/GEOID12B and VERTCON read at HTDP's pivot.

**Cells checked:**
- the clean export's N, E, lat, lon and Z;
- the DD and DMS siblings, including identical id, Z and description;
- the audit's pivot and external positions in DD and in DMS;
- the observation date and the height-convention text;
- the before and after ellipsoid heights, and N/A on a blank Z;
- the elevation factor recomputed as R/(R+H+N) from the correct h;
- the `Ellipsoid height (NAD83(2011), m)` cell;
- the VO mirror.

**Specific hunts, all clean:**
- A WGS 84 value written where NAD 83 is labelled, or the reverse.
- An ellipsoid height in the wrong frame.
- An orthometric Z altered.
- A factor computed from the wrong h.
- Unit conversion applied to degrees: usft and ift outputs on every geodetic target.

**Harness validity:** my harness flags each of seeds S01–S09, S17, S21 and S26 on 10 to 150 of 150 jobs, including S07, which the suite misses (M1).

### 2. Velocities, decimal year and HTDP facts

- **Velocities:** 400 points × 2 directions × 5 frames. The audit-cell velocity matches HTDP's own finite difference (output at t against output at 2010.0) within 0.0015 mm/yr north and east. Up agrees within HTDP's 1 mm print over dt (≤ 0.17 mm/yr).
- **Decimal year:** `exact_number(ObservationEpoch.decimal_year)` equals y + elapsed days / days in the year, for example 2025.4520547945206 = 2025 + 165/365.
- **D6 measured figures:** re-measured over 20,000 random records in both directions. At 603 m the worst is 0.179 mm north and 0.125 mm east, against the stated ≤ 0.18 and ≤ 0.13. An elevation in place of h with |N| = 37 m costs 0.011 mm, against the stated ≤ 0.012.
- **Round-trip figures:** confirmed for 2010–2026 (3.8e-5 m east, under 6.4e-5). See L3 for earlier dates.

### 3. Records read in full: 8 configurations, plus the 24 superseded VO records diffed line by line

The eight configurations:
- G2Z WGS84(G2296), orthometric, horizontal.
- G2Z ITRF2020, ellipsoid, H+V NAVD88 to NGVD29, on the same day as the NAD 83 epoch.
- Z2G to G2139, ellipsoid, horizontal, out of period, with a 0.00 Z.
- G2G G2296 to NAD 83, ellipsoid, H+V.
- G2G NAD 83 to G1762.
- G2G ITRF2014, ellipsoid, horizontal.
- VO ITRF2020, ellipsoid.
- VO NAD 83, NGVD29 to NAVD88.

What I found true in every one of them:
- Frames and ellipsoids.
- Date and decimal year.
- Helmert epoch: the observation date on paths into NAD 83, 2010.0 on paths out of it.
- Sets and parameters, which read back as `htdp_data` exactly.
- The velocity frame, and the same-day "applied no velocity … read N/A" sentence.
- Height-convention counts.
- The "Written in" and "Reference frame" lines.
- The clean-export frame sentences.
- The ELLIPSOID HEIGHT block's three re-statements.
- ELEVATIONS, WARNINGS and FILES WRITTEN, apart from H1, H2 and L2.

The #50 rule holds: the new block carries no caveat prose.

### 4. Refusals and gates: 44 probes, every one before the file was read

Method: `input_path` pointed at a nonexistent file, so a probe that passed every gate would end in a file-read error. All behaved as designed.

**Observation date:**
- Required on WGS/ITRF jobs, and refused as stray on NAD 83, Z2Z and VO-zone jobs.
- `datetime` refused, and a string refused.
- A date of today is accepted; tomorrow is refused.
- 1906 is refused; 1907 is accepted.

**Realization warning edges:** five frames × 8 dates × both directions. The edges are exactly D9's: G1762 runs 2013-10-16 to 2021-01-02, G2139 runs 2021-01-03 to 2024-01-06, G2296 starts 2024-01-07, and ITRF never warns.

**Stray fields:** a stray `geodetic_frame` on Z2Z and on VO-zone, and a stray `target_geodetic_frame` on Z2G.

**G2G pair rules:**
- NAD83→NAD83 and NATRF2022→NATRF2022 refused, including with a date.
- WGS→WGS, WGS→ITRF and WGS→NATRF2022 refused.
- NAD83→NATRF2022 refused, and the bare WGS84 frame refused.
- A missing target, a stray zone and VERTICAL mode refused.
- Both legitimate directions accepted.

**Ellipsoid gate:** NATRF2022 still refuses on VO, G2Z, Z2G and Z2Z.

**TypeError:** raised for a frame where a zone belongs, and for a string zone.

**Cross-frame refusals:** WGS→SPCS2022 and SPCS2022→WGS refuse.

**HTDP window:** a position outside it is refused, fail-closed; see L4 for the message.

### 5. Same-frame regression: 138 jobs, 444 members, against `bd2b325`

The matrix (`sameframe.py`) covered:
- both eras (SPCS 83 / NAD 83 and SPCS2022 / NATRF2022);
- Z2Z, G2Z, Z2G, VO-zone and VO-geodetic;
- both height kinds where legal;
- every vertical pair, including the swap and NGVD29 with no model;
- random units and conventions;
- blank and zero Z.

**Result:** 420 members are byte-identical. The **24 that differ are exactly the VO-geodetic `_README.txt`**, which is W4b's recorded supersession. I read the diff and every changed line is the zone-less replacement (H2 is a sentence W4b missed, not one it introduced). No CSV, clean export or DMS member moved.

### 6. Verifiers: no false refusal, and seeds

- **No false refusal:** 120 archives × 300 points with `repr()` full-precision inputs, 2 to 5 Z decimals, all five directions and three units, gave 0 refusals. The 1,500-job sweep also gave 0 refusals. Total 37,620 points.
- **Seeds:** 28 seeds into a scratch copy, each run against the full suite (baseline: the 6 known environmental failures).
  - Caught by the suite: 24.
  - Not caught: S07 (M1), S14 (L1), S19 and S22 (I2, no behavioural effect).
  - Every verifier-side seed was caught: S01 DMS from the pivot was refused at write; S04, S10, S11, S18 and S26 were caught by the audit pins; the record seeds S12, S20, S23, S27 and S28 by the exact-text pins; and the gate seeds S13, S15, S16, S24 and S25 by name.

### 7. Interface: clean

- `frames_offered()` returns NAD83(2011) and NATRF2022 only.
- `direction_for` returns None for geodetic-to-geodetic.
- Neither tab constructs `observation_date` or `target_geodetic_frame`; I searched `michspc/gui/` for both.
- `frames_have_a_path` now answers True for the HTDP pairs, but no offered entry reaches one.

### 8. Tests

The pins compare against the frozen HTDP print through independent legs, component by component. I found no expected value read back from the module under test. The gaps are M1 and L1, plus the docstrings in L5.

VERDICT: FINDINGS
