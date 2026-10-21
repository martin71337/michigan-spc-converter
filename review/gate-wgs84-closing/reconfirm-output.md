# Closing gate, WGS 84 build: narrowing re-confirmation

**Reviewer:** an independent Opus reviewer. I did not write the fixes.

**Scope:** the fix commit `a31444f` (diff `c14a22d..HEAD`), findings M1, L1, L2, L3 with I3, L4, L5, L6, L7 and I5 only.

**What I touched:** only this file in the repository. Seeds ran in a scratch clone at `/tmp/claude-0/reconf3/repo`, each restore proved by sha256. Scratch work is in `/tmp/claude-0/reconf3/`.

## Suite and self-test at HEAD (a31444f)

- `QT_QPA_PLATFORM=offscreen python3 -m pytest -q -p no:cacheprovider --continue-on-collection-errors`: **4793 passed, 5 failed, 1 error**, exit 1. The six are exactly the known environmental ones: the `test_zone_registry` collection error, the three `test_fileio::test_r3_3_*`, `test_geodetic_dms_export::...half_way_point_writes`, `test_projection_engines::...page_ngs_served`.
- The same under `python3 -O`: **4793 passed**, the same six, exit 1.
- `python3 launch.py --selftest`: **SELF-TEST PASSED - 13 checks**, exit 0.

## M1: the "after transformation" row out of NAD 83

- Gate counterexample at HEAD (Single point, NAD83(2011) geodetic to WGS84(G2296), H+V, NAVD88 to NAVD88, GEOID18, ELLIPSOID, m, negative west, 43.0 / -84.5, h 165.000, 2025-06-15): the row reads **163.901**; my HTDP v3.6.0 build prints 163.901 (lat 43.0000085274, lon -84.5000107604; the panel shows 43.00000853 / -84.50001076). Production is correct, as the gate found.
- The new pins compare against the frozen HTDP print (`L5_REVERSE_RECORDS`, h_out "163.901"), not against the core's own fields, on Z2G and G2G-reverse, in H and H+V, on the panel, Copy all and the Multi point table.

## L3 with I3: the refusal and warning wording, both tabs

Harness `/tmp/claude-0/reconf3/h/l3.py`, output `/tmp/claude-0/reconf3/l3.out`. Cases run at HEAD, every one through the real widgets:

- Single point, G2296 to MI-S: DMS with S latitude under negative west and under positive west; DMS with E longitude under positive west; decimal +84.5555 under negative west; decimal -84.5555 under positive west; decimal south latitude.
- Single point, grid input: MI-S and MI-N grid far north, to G2296, both conventions.
- Single point, G2G reverse (NAD83 to G2296): decimal and DMS south latitude.
- Realization warnings: G2139 dated 2019-03-01 (before), G1762 dated 2023-03-01 (after), and MI-S to G2139 dated 2019-03-01 (out of NAD 83).
- Multi point: a south-latitude file, an east-longitude file under positive west, a far-north grid file, and both realization warnings.

Every message is now true on both tabs. None names a file. The refused position and the ITRF2008 lookup position both print as signed degrees with "(signed, negative west)" stated, so the gate's I3 forms "-42.732484 N" and "275.444520 W" are gone: the east input prints `longitude 84.555480 (signed, negative west)`. The printed lookup position is within 1e-4 degree of the input in every case. The advice asks for the signs of the latitude and the longitude to be checked and states the job's convention as a fact. That holds on DMS entry as well, where the S latitude is the visible fault. Grid input names the zone and unit, with no file. The warnings now say "was not the realization in use on that date" and "positions labelled with the wrong realization". Both are true for the before and after cases, and the out-of-NAD-83 branch was already file-free.

## L4: gate 6 provenance

- **The real check against a synthetic correct bundle does not refuse.** I built `/tmp/claude-0/reconf3/bundle/mcx/` from `data/`, `assets/`, `michspc/` (no `__pycache__`), `installer/` and `launch.py` under `_internal/`, plus the icon at the root. `tools/build_release.foreign_bundle_files` against the real `review/` (708 files, 146 MB, `REVIEW_DIR` present) returns **`[]`**.
- A wider proxy for a real PyInstaller bundle also comes back clean. I ran the provenance rule over the whole installed `dist-packages` (PySide6, shiboken6 and more) and over `/usr/lib/python3.13`: **0 provenance hits**. The only hits were the pre-existing Fortran-suffix rule on numpy's f2py test sources, which no MCX bundle carries.
- The gate's counterexample is now refused, naming its source. `htdp_truth.json` copied to `_internal/data/`, the HTDP README copied to `_internal/htdp/README.md`, and the same README renamed `_internal/notes.txt` all return `... (a copy of review/wgs84-w0/...)`.
- A missing `review/` now refuses the gate rather than passing every bundle unread.
- The release-notes sentence, "refuses ... anything from the repository's `review/` folder", is now a content check. The one exemption is a zero-byte file, whose digest carries no provenance.

## L5: tripwire probes 1 to 3

Harness `/tmp/claude-0/reconf3/h/l5.py`, driving `nsrs_tripwire.main` with a fake fetch. The other probes answered their frozen values.

| Body on probe 1, 2 or 3 | Outcome |
|---|---|
| The frozen refusal, pretty-printed as captured or compact | quiet, exit 0 |
| Captive-portal HTML | PROBE FAILED, exit 2, no notice |
| HTML that contains the frozen text | PROBE FAILED, exit 2, no notice |
| Empty body, `{}`, `[]`, a bare JSON string | PROBE FAILED, exit 2, no notice |
| An NCAT-like success object | TRIPPED, exit 1, notice shown |
| A geoid-like success object | TRIPPED, exit 1, notice shown |
| A different `error` | TRIPPED, exit 1, notice shown |
| `error: null` with data | TRIPPED, exit 1, notice shown |
| A JSON object with no `error` | TRIPPED, exit 1, notice shown |

- **Every well-formed differing answer still trips.** The probe is quiet only when an `error` string carries the frozen text. The frozen captures in `review/nsrs-n0/raw` are exactly that shape, served 200 `application/json`.
- The docstring is now true. It scopes "a proxy's error object" as could-not-check to GitHub's probes, and says probes 1 to 3 trip on any non-empty object that is not the refusal.
- An `error` string that contains the frozen text plus more is quiet. That is the pre-existing "carries" semantics, needed because probe 3's captured refusal appends the model number.

## L7: zone-less records, against c14a22d

I ran two matrices in a `git worktree` at `c14a22d` and at HEAD, comparing every member with the `Generated` and `Software` lines normalised. The worktree was removed afterwards.

**The gate's own 400-job same-frame matrix** (`/tmp/claude-0/closing/h/jobs.json`):
- 274 wrote and 126 refused, with identical refusal texts.
- All 598 CSV and clean-export members are byte-identical, and so are all 228 zone-job records.
- **Every difference is in the 46 VO-geodetic records**, and it is exactly three line forms:
  - `H = orthometric height as used for the factors` becomes `... the elevation factor`;
  - `the factors were computed from.` becomes `the elevation factor was computed from.`;
  - `the factors are stated against.` becomes `the elevation factor are stated against.` The subject is "the Z column and the elevation factor", so the plural verb is right.

**My 600-job matrix** (`/tmp/claude-0/reconf3/h/regress2.py`, seed 3), which adds the five frames, G2G both ways, VO on every frame, H and H+V, swaps and shifts, and dates from 2010 to 2026:
- 460 wrote and 140 refused, identical in both trees.
- All 1,132 CSV members and 273 records are identical.
- The zone-less differences (71 VO-geodetic, 101 G2G) are the same three line forms.
- **15 zone records differ, and only in the realization warning.** That is L3's rewording, on WGS 84 zone jobs that are new in 0.8.0. No zone record changes any "factors" wording: zone jobs keep their sentences to the character.

The wording now matches the record's own "No combined factors exist for this job". A residue of the same class is reported below as N2.

## L6: the release notes, read whole

- **No em dash** (0 U+2014) and no en dash.
- The three gate items are fixed:
  - (a) 374 reproduced and 8 refused at the grid's edge, which matches `tests/test_htdp.py`;
  - (b) the bare "WGS 84" is "not offered in any dropdown, and a job that states it is refused by name";
  - (c) "apart from ... `Generated` ... and `Software`" agrees with both matrices above.
- **Checked true, at the job level and through both tabs:**
  - the bare WGS 84 is `FrameNotUsableError`, naming the realizations;
  - a forced G2296 to SPCS2022 job, G2296 to NATRF2022 G2G, G2296 to G2139, and ITRF2014 to ITRF2020 are each `FrameTransformationUnavailableError` by name;
  - a NAD 83 job given a date is refused as stray;
  - a future date is enterable (the control's maximum is 9999-12-31) and refused at Convert with the "after the day this job runs" message;
  - the HTDP-window refusal names the point.
- **Not true as written:** N1 and N3 below.

## No wrong number introduced

I re-ran the gate's own sweeps at HEAD against my HTDP v3.6.0 build:
- `sp_sweep.py`, seed 5: 250 Single point configurations, 4,806 rows and 4,806 copy paths, 68 transformed-h rows, **0 problems**.
- `mp_sweep.py`, seed 9: 120 Multi point jobs, 369 points, 1,107 cells, **0 problems**.

The fix commit touches no arithmetic. Its production changes are message strings in `job.py` and `htdp.py`, record sentences in `report.py`, a tooltip in `window.py`, and `tools/`. Both regression matrices above show every CSV member byte-identical to `c14a22d` and no refusal status changed.

## Seeds: 21 into a scratch clone, 21 caught, 21 restored

Each seed ran against the **full suite**, with the six environmental failures excluded from "caught". Harness: `/tmp/claude-0/reconf3/h/seed.py`, raw results in `seeds.out`.
- Every seed was restored with `git checkout`, and the sha256 recorded after the restore equals the one recorded before.
- After all 21 seeds, all seven seeded files in the scratch clone hash identically to HEAD's, and `git status` there is clean.

The table gives the first 16 hex digits of each sha256.

| Seed | Before | Seeded | After | First named test that fails |
|---|---|---|---|---|
| M1/G14 transformed-h row shows pivot h | `942ec96dbd62bc3c` | `cfbe8cad3afb419c` | `942ec96dbd62bc3c` | `test_a_vertical_mode_panel_out_of_nad83_shows_htdps_target_frame_h[z2g]` |
| L1/C8 VO panel drops pivot | `942ec96dbd62bc3c` | `2ea5b5107d052386` | `942ec96dbd62bc3c` | `test_a_vertical_only_wgs84_panel_shows_both_positions` |
| L2/C10 Multi mode change skips date relevance | `7e33cffb1f6603a3` | `d32432bdbd2f7f43` | `7e33cffb1f6603a3` | `test_the_date_follows_a_mode_change_on_both_tabs[multi]` |
| L3a origin says file | `248c728cb639ed3c` | `163b6f78920e954b` | `248c728cb639ed3c` | `test_the_htdp_refusal_of_a_south_latitude_is_true_on_both_tabs[single]` |
| L3b advice back to file-longitude wording | `248c728cb639ed3c` | `a1362ed4a6e0fafc` | `248c728cb639ed3c` | `test_the_htdp_refusal_of_a_south_latitude_is_true_on_both_tabs[single]` |
| L3c grid origin says file | `248c728cb639ed3c` | `08de9099fd1675f0` | `248c728cb639ed3c` | `test_the_reviewers_grid_row_outside_the_velocity_window_names_the_point` |
| L3d grid advice says file | `248c728cb639ed3c` | `9ac7083f968866b9` | `248c728cb639ed3c` | `test_the_reviewers_grid_row_outside_the_velocity_window_names_the_point` |
| L3e warning says receiver broadcasting | `248c728cb639ed3c` | `2b1463ec6203e032` | `248c728cb639ed3c` | `test_the_realization_warning_is_true_on_both_tabs[single]` |
| L3f warning says file labelled | `248c728cb639ed3c` | `1aef527ad73a0d71` | `248c728cb639ed3c` | `test_the_realization_warning_is_true_on_both_tabs[single]` |
| I3 lookup longitude back to 0-360 W | `0eb564b218601b78` | `24a86fb5b5748e1b` | `0eb564b218601b78` | `test_the_htdp_refusal_of_a_south_latitude_is_true_on_both_tabs[single]` |
| L4a provenance rule removed | `c1dd309a8a874cbd` | `b60f226039f0b655` | `c1dd309a8a874cbd` | `test_the_bundle_gate_finds_a_review_file_copied_under_another_name` |
| L4b provenance compares size only | `c1dd309a8a874cbd` | `6d3268858317801d` | `c1dd309a8a874cbd` | `test_the_provenance_rule_matches_content_not_size` |
| L4c missing review/ not refused | `c1dd309a8a874cbd` | `9f22ef707bd1eb79` | `c1dd309a8a874cbd` | `test_the_bundle_gate_refuses_to_check_without_review` |
| L5a probes 1-3 back to substring | `d7a65860540eae47` | `7a05fdac9596a8f3` | `d7a65860540eae47` | `test_a_captive_portal_on_an_ngs_probe_is_could_not_check[0]` |
| L5b empty object accepted as answer | `d7a65860540eae47` | `8d40dedb4f5526d2` | `d7a65860540eae47` | `test_an_ngs_answer_that_is_not_an_object_is_could_not_check[empty-object]` |
| L5c quiet on fragment anywhere in object | `d7a65860540eae47` | `63accaeded4b47e3` | `d7a65860540eae47` | `test_the_ngs_probes_quiet_only_on_the_frozen_refusal_field` |
| L5d differing object treated as quiet | `d7a65860540eae47` | `5054cb6bcd47106c` | `d7a65860540eae47` | `test_an_ngs_refusal_that_changed_trips_and_a_dead_host_does_not` |
| L7a FILES WRITTEN zoneless plural | `2f07e79977808da9` | `b30b07223173ae18` | `2f07e79977808da9` | `test_a_zoneless_vertical_record_names_its_one_factor[g2g_hv]` |
| L7b swap zoneless plural | `2f07e79977808da9` | `e60b6676b5e30bdd` | `2f07e79977808da9` | `test_a_geoid_swap_record_names_the_factor_it_has[True]` |
| L7c H line zoneless plural | `2f07e79977808da9` | `99a8e5b65c61192f` | `2f07e79977808da9` | `test_a_zoneless_vertical_record_names_its_one_factor[g2g_hv]` |
| I5 ellipsoid tooltip says orthometric | `7e33cffb1f6603a3` | `bc54bd8bdc238dfd` | `7e33cffb1f6603a3` | `test_the_in_file_tooltip_says_what_kind_of_height_is_read` |

## Per finding

| # | Fixed at root | Pin real | Evidence |
|---|---|---|---|
| M1 | Yes. Production was already correct: 163.901 = HTDP. | Yes. The pin is HTDP's frozen print, not a core field. | Seed G14 is caught by 2 tests. The output-position, horizontal-h and table pins cover the other rows that differ between frames. |
| L1 | Yes | Yes | Seed C8 is caught by `test_a_vertical_only_wgs84_panel_shows_both_positions`, with HTDP-derived pivot rows. |
| L2 | Yes | Yes | Seed C10 is caught by `test_the_date_follows_a_mode_change_on_both_tabs[multi]`. |
| L3 | Yes, true on both tabs, both conventions, DMS, decimal and grid input. | Yes | Six seeds, one per sentence, are each caught. See the L3 section for the cases. |
| I3 | Yes | Yes | The east and south inputs print signed. The seed is caught. |
| L4 | Yes: content provenance, plus a refusal when `review/` is missing. | Yes | Three seeds caught. A synthetic correct bundle is **not refused**, and installed Python trees show 0 provenance hits. |
| L5 | Yes | Yes | Four seeds caught. Every well-formed differing answer still trips; quiet only on the frozen `error`. |
| L6 | (a), (b) bare WGS 84, and (c) yes. **(b) for the SPCS2022 pair, no: N1.** | n/a (prose) | Release notes read whole: no em dash. N1 and N3 below. |
| L7 | Yes. Zone records unchanged to the character. | Yes | Three seeds caught. 400 + 600 job matrices against `c14a22d`. Residue: N2. |
| I5 | Yes | Yes | Seed caught by `test_the_in_file_tooltip_says_what_kind_of_height_is_read`. The wording is true for a Horizontal ELLIPSOID job. |

## New findings

| # | Sev | Finding | Counterexample | Suggested fix |
|---|---|---|---|---|
| N1 | LOW | **Introduced by the L6 fix.** `RELEASE-NOTES-0.8.0.md:133-135` says "If one is selected anyway, a pair with an SPCS2022 zone is refused at Convert by name". From the interface the pair never reaches Convert, on either tab. | On both tabs, the grayed item forced with `setCurrentIndex`, From WGS84(G2296) then To MI_L45G (or To first, then From). The OTHER end resets to the placeholder and the status reads "Cleared: no published transformation between those reference frames." Convert stays disabled, because `settings()` is None. The same holds for G2296 to NATRF2022. The by-name refusal exists only for a job that STATES the pair: `job.run` with G2296 to an SPCS2022 zone raises `FrameTransformationUnavailableError`. | Say what happens: the other selection is cleared, and a job that states the pair is refused by name, as bullet 3 phrases it. |
| N2 | LOW | **L7's class, residue.** The record's "Precision written" block is unconditional (`report.py:2110-2111`). Every zone-less record (VO geodetic, and G2G) carries "Scale and combined factors  8 decimal places" and "Convergence angles  degrees-minutes-seconds to 0.01 second", while the same record says "No combined factors exist for this job: no zone is involved". It is pre-existing for VO geodetic since 0.4.0, and was not changed by the fix. | Any VO-geodetic job, for example `/tmp/claude-0/reconf3/reg_new/j0__in_VERTICAL_README.txt:48-49`. It appears in all 218 zone-less records of the two matrices. | On zone-less records, print an elevation-factor precision line and drop the convergence line. Or record that the block is a fixed legend. |
| N3 | LOW | **Stale status claims in the DRAFT notes.** | Line 4: "the closing review gate over the whole build has not run". It ran (`c14a22d`, FINDINGS) and is now in re-confirmation. Line 210: "4,757 automated tests pass in both run modes". The suite is now **4,793** in both modes. Lines 217-223 list only the two interim gates. | Update at the next edit of the notes: the closing gate's outcome and the current count. |

**INFO:**
- The L7 correction also changes released-0.7.1 VO-geodetic record sentences ("the factors" becomes "the elevation factor", and the `H =` line). It is not itemised under "Corrected". Nothing written is false, because those jobs fall under item 1 and are excluded from the "byte for byte" sentence, but the heading "two false sentences" now undercounts.
- Probes 1 to 3 are quiet on an `error` string that contains the frozen text plus more. That is the pre-existing "carries" semantics, needed for probe 3's model-numbered refusal.

No CRITICAL, no HIGH, no MEDIUM, and no wrong number on any surface.

VERDICT: FINDINGS
