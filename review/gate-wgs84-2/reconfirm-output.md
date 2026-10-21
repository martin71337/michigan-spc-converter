# Interim gate 2, WGS 84 build: narrowing re-confirmation of the fixes in fcd8168

**Reviewer:** an independent Opus reviewer. I did not write the fixes.

**Scope:** the diff `4fb2798..fcd8168`, and only the surfaces of H1, H2, M1 and L1-L5. I did not re-raise the INFO items or the lead's decision on the "Precision written" lines.

**What I touched:** in the repository I wrote only this file. The `git worktree` at `4fb2798` has been removed and `git status` is clean. Scratch work, harnesses and outputs are in `/tmp/claude-0/reconf2/`.

**Oracle:** NGS HTDP v3.6.0, built from `review/wgs84-w0/htdp-v3.6.0/*.f` in `/tmp/claude-0/reconf2/htdp/` with `gfortran -O0 -std=legacy -w`. Its SHA-256 is `3738c50c…f77f8f`, the same binary as W0 and the gate. Before relying on `michspc.spc.htdp` for unrounded figures, I checked it against this binary:
- 2,400 records: 60 random frame/date runs × 20 random Michigan positions × both directions;
- dates across 1990-2035, 30% of them on 30 or 31 December;
- heights from -50 to 700 m;
- result: identical to HTDP's printed digit on all 2,400 (`spot.py`).

## Suite

Both modes ran: `QT_QPA_PLATFORM=offscreen python3 [-O] -m pytest -q -p no:cacheprovider --continue-on-collection-errors`.

Both gave **4600 passed, 5 failed, 1 error**, exit 1. The six are exactly the known environmental ones:
- `test_zone_registry` (collection error);
- `test_fileio::test_r3_3_*` ×3;
- `test_geodetic_dms_export::test_a_position_on_the_rounding_half_way_point_writes`;
- `test_projection_engines::test_every_captured_value_is_in_the_page_ngs_served`.

A file-for-file scratch copy of the repository gives the same baseline, and all seeding below ran against that copy.

## Per-finding table

| # | Fixed at root | Pin real | Evidence |
|---|---|---|---|
| H1 | **Yes** | **Yes** | **Cells:** 90 transformed jobs: 5 frames × 2 height kinds × {G2Z, Z2G, G2G forward, G2G reverse} × {HORIZONTAL, H+V}, plus VO in VERTICAL. Through `run`, `write_all` and unzip. I read every latitude, longitude and ellipsoid height heading, 3,450 cells in all. I recomputed each cell's value in every candidate frame independently (HTDP, the NAD 83 inverse projection, GEOID18). **Every cell matched exactly one frame, and that frame is the one its heading names. No such heading is unnamed** (`h1cells.py`). VO's Target pair is in the input frame, as its heading says. The same harness on `4fb2798` flags the four unnamed headings on every job, so the check is not vacuous. **Same-frame:** 72 configurations in both trees, covering both eras, Z2Z/G2Z/Z2G/VO-zone/VO-geodetic, both height kinds and all three modes. 49 wrote; 23 are designed refusals, identical in both trees. **49 of 49 audit headers are byte-identical to `4fb2798`**, and 155 of 158 members are byte-identical. The 3 that differ are VO-geodetic records whose only change is H2's sentence. **Seeds:** VO pair named by the target frame: 4 failures. Every Target pair named by the source frame: 18. Source pair named by the pivot: 17. Record sentence reverted to "Every position…": 19. All were caught by the root pin `test_every_position_and_height_heading_names_the_frame_its_cells_hold` and its neighbours. |
| H2 | **Yes** | **Yes** | **Records:** 104 zone-less configurations. They cover VO geodetic on NAD 83, NATRF2022, G2296 and ITRF2014, and G2G both ways. Each ran at both height kinds, in every applicable mode, over six vertical pairs: NAVD88↔NGVD29 each way, NAVD88→NAVD88, the GEOID12B→18 swap, and GEOID12B with NGVD29. 77 wrote; 27 are pre-existing designed refusals. **The phrase "elevation and combined factors" appears 0 times in the new records and 30 times in the same configurations on `4fb2798`.** **The sweep's claim:** I extracted every sentence containing combined / convergence / grid scale / zone / Lambert / projection. Apart from the lead's recorded "Precision written" lines, every one is true for a zone-less job, for example "No zone is involved, so the scale-factor and convergence columns read N/A" and "No combined factors exist for this job…". Zone jobs keep the old wording, byte-identical in the same-frame comparison. **Seeds:** flag ignored: 2 failures. Zone jobs given the zone-less wording: 3. |
| M1 | **Yes** | **Yes** | **The gate's counterexample now gives 198.085.** The job is Z2G from MI-S (the NAD 83 point 43.0 N, 84.5 W, h = 165.000) to G2296, dated 2025-06-15, ELLIPSOID, H+V, NAVD88→NAVD88. Its clean export is `43.00000853,84.50001076,198.0850`. The G2G reverse job gives the same. 165 − (−33.085) = 198.085. My HTDP gives 43.0000085274 / 84.5000107604. **Seed S07** (`elevation_m = conversion.target_frame_ellipsoid_height`) gives 7 failures, among them `test_z2g_ellipsoid_in_a_vertical_mode_uses_the_nad83_h` and `test_g2g_reverse_…_uses_the_nad83_h`. |
| L1 | **Yes** | **Yes** | **Counterexample:** with `_local_and_utc_dates` patched to (2026-10-20, 2026-10-21), `today()` returns 2026-10-21. A job dated 2026-10-21 is accepted and one dated 2026-10-22 is refused. No other clock read in `michspc/` feeds the date gate. **Seed S14** (`min`) gives 3 failures, among them `test_an_evening_session_dated_in_utc_is_not_refused_as_future`. |
| L2 | **Yes** | **Yes** | **Wording read in 8 cases:** Z2G to G2139 dated 2019-03-01, the gate's case; G2Z from G2139 on the same date; G2G reverse to G1762 and forward from it, both dated 2025-06-15; Z2G to G2296 dated 2023-12-31; Z2G to G1762 dated 2013-10-15; Z2G to G1762 dated 2013-10-16, which correctly gives no warning; VO from G2139 dated 2021-01-02. Paths out of NAD 83 now say "This job writes its positions in X, the realization requested as its output … X was not the realization in use on that date". Paths into NAD 83 keep the old input-label text, byte-identical in wording. Every message is true for its direction. **Seeds:** always the input message: 3 failures. Always the output message: 9. |
| L3 | **Yes for dates; see N1 for heights** | **Yes** | **The date range holds** for Michigan ground heights. I measured independently through `michspc.spc.htdp`, confirmed against the binary as above.<br>**Daily sweep:** every day from 1990-01-01 to 2035-12-31, 12 positions (the lattice extremes and the box corners), h 0 and 600, all five frames, both ways: 4,032,240 round trips. Worst: **8.517e-6 m N** (1992-01-01, 42.5, −82.0, G2139); **5.923e-5 m E** (1992-01-01, 48.5, −86.914, G1762); **1.886e-6 m U** (2035-12-31, 48.5, −90.6, G1762). This reproduces the lead's output.<br>**Random sweep:** 960,000 round trips at random Michigan positions (41.69–48.31 N, 90.42–82.41 W). Dates are 70% within a week of a year's end and the rest anywhere in the year. Height is 610 m, above Michigan's highest ground. Worst: 8.04e-6 N, 5.96e-5 E, 1.87e-6 U. All are inside the stated 9.2e-6 / 6.4e-5 / 4.3e-6 m.<br>**Record text:** dates outside the range (1950-06-01, 1989-12-31) get a true qualifier, and 1990-01-01 gets none.<br>**Seeds:** range end set back to 2026-10-19: 6 failures. Qualifier never printed: 3. Range start moved to 1907: 4. |
| L4 | **Yes** | **Yes, for the window refusal** (see N2) | **Grid input:** the gate's row `1,0,0,,a` (Z2G to G2296) now reads "point 1: cannot transform the position the file's Michigan South northing and easting give - latitude 32.026364, longitude -127.914179 (signed, negative west), in NAD83(2011) - to WGS84(G2296): … Check that the point is in Michigan, and that the file holds Michigan South coordinates in m." The program's own inverse of (0,0) in MI-S is 32.02636419614145, −127.91417920888318, so the position and its frame are true.<br>**Geodetic input:** G2Z from G2139 at 30 N; G2G forward with the sign flipped; G2G reverse from NAD 83 at 52 N and with the sign flipped; VO on G2296 at 39 N; and a same-day 2010-01-01 Z2G job. Every message names the point id from the file, the position actually handed to HTDP, and the frame that position is in. Only the geodetic cases give the convention advice, and they name the job's convention.<br>**Every refusal type reaches the caller:** I monkeypatched `htdp.to_nad83` and `from_nad83` to raise each of HtdpConvergenceError, HtdpInputError, HtdpFrameError, HtdpEpochError, HtdpVelocityGridError and bare HtdpRefusal. On grid, geodetic and VO jobs, each one leaves `job.run` as its own class, an `HtdpRefusal`, prefixed "point N:", with `__cause__` set. None is swallowed or turned into another type.<br>**Seeds:** refusal labelled with the target frame: 3 failures. `htdp._window_cell` given the pre-fix "other" frame: 4. The `job` wrapper removed: 3. |
| L5 | **Yes** | n/a (prose) | `tests/test_frame_disclosure.py:313` and `:380` now cite 42.9999914726 / 84.4999892398. That matches the fixture and my HTDP's print for G2296 dated 2025-06-15. No stale copy remains in any `.py` file. |

**Restores:** every seed was applied to the scratch copy and restored from the repository. After each restore the file's SHA-256 matched the repository's, for example:
- `job.py` 0732a910…
- `report.py` cdd18fdc…
- `exports.py` c69d0477…
- `htdp.py` 61f4f7aa…

At the end, every file under `michspc/` and `tests/` in the scratch copy compared byte-equal to the repository.

**Did the fixes introduce anything?**
- No wrong number: the position cells, the M1 heights, the same-frame bytes and the HTDP spot-check are all as stated.
- No refusal of legitimate work: the L1 evening date is accepted, and the same-frame refusal sets are identical in both trees.
- No false sentence, other than the two items below.
- The `htdp.py` change passes `source` where it passed `other`. `_predv` and `_window_cell` use that frame only for messages, and the 2,400 records still reproduce the binary.

## New findings

| # | Sev | Finding | Counterexample | Note |
|---|---|---|---|---|
| N1 | LOW | The round-trip bound was qualified by date but not by height. The non-closure is linear in the height handed to HTDP: east is about 5.4e-8 m per metre at the worst point and date. The stated 6.4e-5 m east is passed at about 690 m. The record says "a Michigan position carried out and back fails to return by up to 9.2e-6 m north, 6.4e-5 m east", and `job.run` accepts any height. | (48.29327 N, −85.59821) at h 700 m, dated 1992-01-01, in G2296: **6.448e-5 m east**. At 800 m: 6.99e-5 m east and 9.41e-6 m north, both outside the bound. A random Michigan sweep at 0–1000 m (4,000,000 round trips) reached **1.092e-5 m N** (2032-12-31, 44.824, −82.215, h 978, ITRF2014) and **8.194e-5 m E** (2033-01-02, 48.131, −89.638, h 994.5, G1762). Up stays at about 1.9e-6, inside 4.3e-6. | This is the same class as the gate's L3, which was graded LOW. It needs an airborne or tower-top GNSS height over about 690 m to arise. The harness's own heights were 0 and 600 m, and its docstring says so, but the record sentence does not. **Fix: add the height range to the sentence** ("for … heights up to 600 m" or similar), or measure further. |
| N2 | INFO | Pin gap: the fallback branch of `_point_named_htdp_refusal` is unpinned. The docstring promises "every other HtdpRefusal as its own class, with this row's context prefixed". | Seed: `type(error)(f"{context}: {error}")` becomes `type(error)(f"{error}")`. Suite green, 0 new failures. | The behaviour is correct today: my synthetic-raise probe above shows all five non-window types arrive with "point N:". The only production path is the convergence failure (STOP 666) or the defect-only node refusal, neither reachable in Michigan, so INFO. The probe would make a pin. |
| N3 | LOW (out of the narrowed scope; recorded for the lead) | On a GEODETIC_TO_GEODETIC job in a vertical mode, the METHOD Authority line says HTDP is "the frame transformation, which is the whole of this job's conversion". The same record's VERTICAL DATUM TRANSFORMATION block shows VERTCON (or H = h − N) converting the elevation as well. | G2G forward from WGS84(G2296) to NAD83(2011), dated 2025-06-15, HORIZONTAL_AND_VERTICAL, NAVD88→NGVD29, GEOID18, row `1,43.0,84.5,165.000,P`. The record's Authority line is as quoted, and its VERTICAL DATUM TRANSFORMATION block reads "NGVD29 = NAVD88 - g …". This holds for every G2G job in H+V, including ellipsoid jobs. | It comes from W4 (`4454a54`, `report.py:1277`) and was neither introduced nor touched by `fcd8168`. It is not a zone sentence, so H2's sweep claim stands. It sits on the G2G surface W4b and H2 cleaned up. Read narrowly ("conversion" meaning the horizontal one) it is defensible; read plainly it is false on those jobs. **Fix: on a vertical-mode job, say "the horizontal conversion".** |

**Measured, not a finding:** inside the accepted velocity window but outside Michigan, at 610 m, the north figure reaches 1.03e-5 m (40.71 N, 80.61 W). The record sentence says "a Michigan position", so it is not false there.

VERDICT: FINDINGS
