# Closing gate, WGS 84 build: independent adversarial review

**Reviewer:** an independent Opus reviewer, blind to the lead's reading of the code.

**Scope:** the committed diff `fbcbf4a..HEAD` (`c7df88a`) on `claude/brave-noether-88m7x1`. That covers W1 to W6, both interim gates and their fixes, and the docs. Nothing uncommitted was reviewed.

**What I touched:** in the repository I wrote only this file. The `git worktree` at `fbcbf4a` used for the regression has been removed, and `git status` shows only this file. Scratch work, harnesses and outputs are in `/tmp/claude-0/closing/`. Seeds ran in two scratch copies, `repo/` and `repo2/`, each restored with `git checkout` after every seed.

**Oracle:** NGS HTDP v3.6.0, built from `review/wgs84-w0/htdp-v3.6.0/*.f` with `gfortran -O0 -std=legacy -w`. I drove it by calendar date, with NAD 83 at 1 1 2010. For anything beyond HTDP's print, the second leg is the program's NCAT-verified projection, geoid and VERTCON readers.

## Verdict in one paragraph

**No wrong number reaches any user surface I could build.**
- I drove the real widgets of both tabs, headless, through 2,050 random Single point configurations and 540 Multi point jobs.
- The configurations cover every direction, all five frames, both height kinds, all three modes, the vertical pairs and geoid swaps, every unit, both longitude conventions, DMS entry, and dates from 2010 to 2026, including year ends and the realization edges.
- I checked every panel row, every copy button, Copy all, every table cell and every written clean export against HTDP plus the projection. Nothing differed.
- No control leaves a stale result on the Single point tab.
- Same-frame output is byte-identical to `fbcbf4a`, except the recorded W4b/H2 supersession.
- No path carries a WGS 84 or ITRF position across without HTDP, and none reaches NATRF2022.

**The findings are a pin gap, wording and packaging claims:**
- **One MEDIUM.** A seeded 1.1 m error on a Single point panel row leaves the suite green. It is gate 2's M1 class again, this time on the screen.
- **Seven LOW.** Pin gaps, false or misleading wording on refusals and warnings, and release-note or docstring claims broader than the code.
- **Five INFO.**
- No CRITICAL and no HIGH.

---

## Findings

| # | Sev | Finding | Concrete input | Observed | Expected | Root cause |
|---|---|---|---|---|---|---|
| M1 | MEDIUM | Pin gap: the Single point row **"Ellipsoid height after transformation (F, m)"**, shown in the two vertical modes, is never pinned on a path OUT of NAD 83. A 1.1 m wrong ellipsoid height under the WGS 84 label would pass the suite. | Seed G14, in `results_model.single_point_sections`: `fmt.geoid_height(conversion.target_frame_ellipsoid_height)` becomes `...pivot_ellipsoid_height`. Then on the Single point tab: From NAD83(2011) geodetic, To WGS84(G2296), Horizontal + Vertical, NAVD88 to NAVD88, GEOID18, ELLIPSOID, m, negative west, 43.0 / -84.5, h 165.000, dated 2025-06-15. | **Suite fully green (4,757 passed).** The panel and Copy all show `Ellipsoid height after transformation (WGS84(G2296), m)` = **165.000**. My harness flags 29 of 250 random configurations under the seed, for example Z2G MI-C to G2139 showing 166.619 where HTDP gives 165.552. | **163.901**, which is HTDP's print (NAD 83 to G2296, h 165.0, 2025-06-15) and what the unseeded build shows today. | `test_a_vertical_mode_panel_shows_the_transformed_ellipsoid_height` runs only G2G forward, INTO NAD 83, where `target_frame_ellipsoid_height == pivot_ellipsoid_height` by construction. It even asserts that the two are equal. Both of its expected values are the core's own fields, not HTDP's. This is interim gate 2's M1 class (the audit CSV, fixed there), reappearing on the W5 panel. **Production is correct:** 77 such rows in my sweep matched HTDP. **Fix:** a Z2G or G2G-reverse vertical-mode pin against a frozen HTDP h. |
| L1 | LOW | Pin gap: the NAD83(2011) pivot rows on the Single point panel of a vertical-only job on WGS 84/ITRF input are unpinned. The release notes say "The Single point tab shows both positions, each labelled with its frame, when a transformation ran." | Seed C8, in the VO geodetic layout: `*positions.input, *positions.pivot,` becomes `*positions.input,`. | Suite green. The VO panel then shows only the WGS position. | A pin that the VO-on-WGS panel carries both positions. | The panel tests cover G2Z and G2G only. No number goes wrong; a stated disclosure would silently disappear. |
| L2 | LOW | Pin gap: a mode change on the Multi point tab does not have to refresh the observation date's enabled state. | Seed C10: `_update_observation_date_relevance()` removed from `MainWindow._on_vertical_mode_changed`. Then: Vertical mode, From NAD83(2011) geodetic (To still holding G2296 from earlier), then switch to Horizontal. | Suite green. Under the seed the date control stays grayed while the job now needs a date, so Convert can never be enabled until another control moves. That is a fail-closed dead end. | A per-mode-change pin on the Multi point tab, as the Single point tab's controls have. | Only the direction-change path is pinned. Production is correct today. |
| L3 | LOW | **Single point refusals and warnings speak of a file, and one gives wrong advice for DMS entry.** These messages are reachable on that tab since W5. | (a) Single point, G2296 to MI-S, DMS entry `42°43'57"` with hemisphere **S**, `84°33'19.8"W`, dated 2025-06-15. (b) Single point, G2139 to MI-S at 2019-03-01. | (a) "point 1: cannot transform **the position the file supplied** - latitude -42.732500 … lookup position, -42.732484 N … Check that the point is in Michigan, and that **the file's longitudes are written positive west**, as this job states: a longitude written in the other convention lands on the other side of the world." (b) The warnings field: "…but **a file labelled with the wrong realization** looks exactly like this", and "**a receiver on that date was not broadcasting it**". | (a) The typed point, as the tab's other refusals already say (`pnezd.TYPED_POINT_SOURCE_*`). On DMS entry the hemisphere letter decides the sign, so the convention advice does not apply; here the fault is the latitude's S. (b) No file on this tab. Satellites broadcast; receivers do not. | `job._point_named_htdp_refusal` (gate 2's L4 fix) and `_require_the_observation_date` were written for the file path. W5 passes them to the Single point tab verbatim. Gate 2 graded the same class LOW (L2, L4). |
| L4 | LOW | **Gate 6 checks bundle path names, not provenance.** DESIGN #70 and the release notes say it refuses "anything from the repository's `review/` folder". | `tools/build_release.foreign_bundle_files` on a tree holding `_internal/data/htdp_truth.json` and `_internal/htdp/README.md`, both copied from `review/wgs84-w0/`. | `[]`: neither is found. Only a `.f/.for/.f77/.f90` suffix, or a path component named `review`, is caught. | Either the claim narrows ("Fortran source, or a `review/` directory"), or the gate compares bundle digests against the files under `review/`. | The rule is a name heuristic. The sentence describes a provenance check. |
| L5 | LOW | **The tripwire docstring says a captive portal is "could not check"; for probes 1 to 3 it TRIPS.** | `nsrs_tripwire.main(fetch=lambda u: "<html>…hotel wifi…</html>")` | Exit **1**. Probes 1 to 3 report "*** TRIPPED … NGS no longer answers the frozen refusal", the REVIEW-NEEDED notice is written, and the message box says "NGS has published something". Probes 4 and 5 correctly report PROBE FAILED. | The module docstring: "a body that is not the JSON shape the API documents (a captive portal's HTML …) … is 'could not check' - PROBE FAILED, exit 2". | Probes 1 to 3 test only `expected_fragment in body` (pre-existing), and the W6 docstring generalises probe 5's strictness to all five. **Fail-safe:** never quiet, so no missed trip, but the sentence is false and gives a false alarm. |
| L6 | LOW | **Release notes, three claims broader than the code.** | `docs/RELEASE-NOTES-0.8.0.md` | (a) "plus 382 records … **every one** to 1e-10 degree and 1 mm": 8 of the 382 (role `edge … outside`) are REFUSED by design, not reproduced (`tests/test_htdp.py:285`). (b) "Each of these refuses **at Convert**": the bare "WGS 84" is never offered in any dropdown, and the D3 pairs are grayed, so from the interface they do not reach Convert. The notes say "grayed" only for D4. (c) "Every other existing job's files are unchanged, **byte for byte**": every record's `Software MCX version` line changes (my regression: 228 records differ by that line alone). | (a) "374 reproduced, and the 8 outside the window refused". (b) "is not offered" or "grayed", plus "refused by name if forced". (c) "apart from the version and timestamp lines". | Drafting. |
| L7 | LOW | **"the factors"** on zone-less vertical jobs, which have one factor. This is the H2 sweep's residue. | VO on ITRF2014 geodetic, NGVD29 to NAVD88, GEOID18; and any G2G job in Horizontal + Vertical. | FILES WRITTEN: "…its one-sigma uncertainty, and the geoid model **the factors were computed from**" (`report.py:2716-2719`; the swap branch at 2713-2714 says "the factors are stated against"). The same record says "No combined factors exist for this job". | "the elevation factor", as H2 fixed elsewhere. | `report.py` FILES WRITTEN branch. It is also in released 0.7.1 on VO-geodetic jobs. H2's sweep matched "combined/convergence/grid scale/zone…", not "the factors". |
| I1 | INFO | Graying is inconsistent between same-frame geodetic pairs. | From NAD83(2011) geodetic; and From WGS84(G1762). | To = NAD83(2011) geodetic is **enabled** (no direction, so Convert stays off with no message). To = the same WGS 84 entry is **grayed**. | — | Pre-existing for NAD83/NATRF2022, harmless. For the owner's screen review. |
| I2 | INFO | The date control keeps its last answer when it becomes relevant again. | Convert a G2296 file dated 2019-06-01. Switch to NAD83 work, then back to ITRF2020 for a different dataset. | The control re-enables showing 2019-06-01, already answered. | — | Visible on screen and stated in the record, so not a default. A second dataset from another day inherits the first date if not looked at. For the owner's review. |
| I3 | INFO | The HTDP refusal prints an east or south input as "275.444520 W" or "-42.732484 N". | G2296, longitude typed +84.5555 under negative west. | "lookup position, 42.732499 N 275.444520 W in ITRF2008". | — | `htdp` prints HTDP's 0-360 west longitude and a signed latitude with a hemisphere letter. The values are equivalent, but the form is awkward. |
| I4 | INFO | Interim gate 2's I3 (an ITRF job with a mistyped year, 1925 for 2025, moves about 1.7 m with no warning) is still the owner's open question. The GUI date control now makes it a two-click slip. | — | — | — | D9 by design. |
| I5 | INFO | The Multi point "in file" tooltip says "Orthometric heights are read from the file's Z column" on ELLIPSOID jobs too. | Any ELLIPSOID job. | — | — | Pre-existing (0.6.0), not W5. Recorded only because W5 reworded the note beside it. |

---

## Clean surfaces, and how each was checked

### 1. Numbers on the Single point tab: 2,050 configurations, 0 mismatches

**Harness:** `/tmp/claude-0/closing/h/sp_sweep.py`, seeds 1, 3, 7, 11 and 31, plus `sp_sweep_x.py`. It uses real widgets, `setCurrentIndex`, typed text and DMS boxes.
- **Directions:** G2Z, Z2G, G2G both ways, VO.
- **Draws:** all five frames, all three SPCS 83 zones, ORTHO/ELLIPSOID, H/H+V/VO, NAVD88↔NGVD29 and same-datum geoid swaps, every enabled unit, both conventions, 30% DMS entry, 12% blank Z.
- **Dates:** 2010-2026, with 2010-01-01 and year ends over-sampled.
- **Extreme run:** 300 configurations at Isle Royale, the Keweenaw, Ironwood, Port Huron and Lake Erie.

**What each row was compared with:**
- Every `Latitude/Longitude (F[, DMS])` row against HTDP's print for frame F, within half a display place plus HTDP's own print.
- Northing and easting against `projection.forward` at HTDP's pivot.
- Every `Ellipsoid height (F, u)` and `…after transformation (F, m)` row against HTDP's h in F.
- Output elevations against h(NAD 83) − N plus VERTCON, or H plus the geoid swap, at the pivot.
- Geoid height; grid scale factor, convergence, elevation and combined factor against `from_geodetic` and `factors.elevation_factor` at the pivot (2,429 factor rows).
- The observation-date row.
- The realization warning's presence against D9's periods, and the status-line count.

**Other checks:**
- An unframed position row on a transformed job counts as a failure.
- **Clipboard:** every value label equals its section value, every `copy_value(i)` gives the shown text, and Copy all equals the serialised sections. 39,591 rows checked in total.
- **Harness validity:** seeding the pivot rows with the external frame's label gives 60 flags in 20 configurations, and G14 gives 29 flags.

### 2. Numbers on the Multi point tab: 540 jobs, 1,657 points, 0 mismatches

**Harness:** `mp_sweep.py`, the same draw space, 1 to 5 points per file, through `MainWindow.convert`.

**Checks per point:**
- The table's N, E and Z cells equal the clean export's.
- The clean export's grid or degrees equal HTDP plus the projection.
- The Z follows the same oracle as above.
- The geodetic headings name the frame their cells hold.
- VO mirrors its input exactly.

**Harness validity:** seeding `written_geodetic_position` to return the pivot gives 49 flags in 30 jobs.

**HTDP refusal on this tab:** a two-point file with one point at 30 N shows the refusal naming point 2. Nothing is written, the table is empty, and the window is re-enabled.

### 3. Stale results on the Single point tab: clean

I made 16 mutations after Convert, in 7 configurations (H G2Z, G2G both ways, H+V G2Z and G2G-reverse, VO WGS, Z2G):
- date +1 day and −1 year, and a date step;
- From to G2139 and to ITRF2020, To to MI-C;
- height kind, both units, longitude convention;
- elevation, latitude, mode, both geoid combos, angle format.

I also tested the DMS hemisphere letters and seconds box, and the calendar's `clicked` and `activated`, each in a fresh window.

Every effective mutation cleared the panel, disabled Copy all and refused `copy_value`. The only results left on screen were from no-op mutations: a mode already selected, and a geoid combo that is disabled in that mode.

### 4. Refusals and safety

**The dropdowns, on both tabs, for all seven geodetic From entries:**
- The five global frames reach only the three SPCS 83 zones and NAD83(2011) geodetic.
- NAD83(2011) reaches the five, the SPCS 83 zones and itself (I1).
- NATRF2022 reaches only itself and the 19 SPCS2022 zones.

**Refusals:**
- A forced WGS84(G2296)-to-SPCS2022 pair refuses with the D3 message before any date gate.
- A NATRF2022 job given a date refuses it as stray.
- Both tabs catch and show HtdpRefusal (seeds C14 and C15 are caught).

**Settings construction:**
- The date is sent only when a selected side is time-dependent.
- VO reads From only.
- G2G states `target_geodetic_frame`; no other direction does.

### 5. Packaging, self-test and tripwire

- **Self-test:** passes 13 of 13 from the source tree.
- **Checks 12 and 13 directly, under five seeded gates in `project_point`:**
  - identity gate: both fail;
  - identity gate without the argument check: both fail ("without a frame transformation" and "PROJECTED a bare WGS 84");
  - a no-op mapping (bare WGS84 to G2296): check 13 fails;
  - a permissive catch-all: check 13 fails;
  - a dropped height: check 12 fails, 0.17 mm against a 0.014 mm budget.
- **GRS 80 on WGS84 frames:** refused at import by the frames registry.
- **LAZY_IMPORTS:** the new GUI and selftest imports are module-level or declared; the AST audit passes.
- **`check_ngs_windows_binary.py`:**
  - against my Linux build: 144 runs, **2,228 / 2,228 identical, AGREES, exit 0**;
  - against a wrapper adding 2 units to one record per run: **DISAGREES, exit 1**, naming the records and the 76/1,846 > 1% pattern.
- **Tripwire probe 5:**
  - live here: proxy 403, so "PROBE FAILED", never quiet;
  - `git ls-remote` shows the HTDP HEAD at `59fdbe6b`, the frozen commit, also tagged `v.3.6.0`;
  - seeds S1 (7-hex compare), S2 (HTTPException uncaught) and S3 (any sha) are all caught.

### 6. Seeds: 25 into the suite, 22 caught

**Caught:**
- GUI: G1 date not invalidating; G3 date relevance source-only; G4 external longitude convention flipped; G5 table heading from the pivot frame; G6 job warnings uncounted; G7 identity as a transformation; G11 date row shows today; G12 calendar answers the date; G15 horizontal output h labelled with the source frame; G18 G2G zone columns; C4 factor-h row with the external frame; C5 combined-factor hint everywhere; C14 and C15 HtdpRefusal swallowed.
- W6: S1 to S4, S6, C11 (budget ×1000), C12 (checker threshold 50%), C13 (checker accepts 2 units).

**Missed:** G14 (M1), C8 (L1) and C10 (L2).

### 7. Regression against `fbcbf4a`

**Core:** 400 random same-frame jobs in a worktree and at HEAD:
- both eras; Z2Z, G2Z, Z2G, VO-zone and VO-geodetic;
- both height kinds; all modes, vertical pairs and geoid choices; random units and conventions.

Results:
- 274 wrote and 126 refused, identically in both trees.
- **All 598 CSV and clean-export members are byte-identical.**
- 228 records differ only by the version line.
- The 46 that differ further are all VO-geodetic (33 NAD 83, 13 NATRF2022).
- Every removed or added block is a W4b zone-less passage or H2's "elevation factor" sentence, as pinned in `W4B_RESPELLING`. I read each of the 15 removed and 28 added distinct blocks; each added one is true for its job.

**GUI:** 250 same-frame configurations through both tabs in both trees:
- 3,562 panel rows, table headings and cells, status lines, warnings and the elevation note;
- identical, 0 differences.

### 8. HTDP outside the 2010-2026 range the GUI reaches

1,800 records through `michspc.spc.htdp` against the binary:
- dates 1907 to 2009, 30% on 31 December;
- heights from -50 to 650 m, all five frames, both directions;
- result: 0 differences at HTDP's printed digit.

### 9. Records and documents read

**Full records:**
- G2Z G2296, ELLIPSOID, H+V NAVD88 to NGVD29 with a blank Z;
- G2G reverse NAD 83 to ITRF2014, ortho;
- VO ITRF2014 NGVD29 to NAVD88;
- Z2G to G1762, ELLIPSOID, blank Z.

Frames, ellipsoids, date and decimal year, Helmert sets and epochs, velocity frame, height buckets, round-trip bound, verification prose and FILES WRITTEN are all true for each. The exception is L7.

**Documents:** `RELEASE-NOTES-0.8.0.md` claim by claim (exceptions L4 and L6); `REFREEZE-HTDP.md` (true; the tag and commit match the live repository); DESIGN #70's W5/W6 entries and the CLAUDE.md status (true).

**Suite:** 4,757 passed, plus the 6 known environmental failures, in both `pytest` and `pytest -O`.

VERDICT: FINDINGS
