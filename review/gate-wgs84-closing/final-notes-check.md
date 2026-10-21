# Closing gate, WGS 84 build: final narrow check of the release notes

**Reviewer:** an independent Opus reviewer. I did not write the notes or the fixes.

**Scope:** `docs/RELEASE-NOTES-0.8.0.md` at `b3dbeb3`, read whole, with the N1 and N3 rewrites checked in detail. N2 (the "Precision written" lines) is excluded, by DESIGN.md #70's recorded decision.

**What I touched:** only this file in the repository. My harnesses are in the session scratchpad (`pairs.py`, `control.py`, `suite.out`).

## The rewritten pair bullets (N1), on both tabs

I drove the real `MainWindow` and its Single point tab headless (`QT_QPA_PLATFORM=offscreen`), with a fresh window for every scenario. There were eight pairs, each tried in both orders:

- G2296 against SPCS2022 260001;
- ITRF2020 and G1762 against two of the other SPCS2022 zones;
- G2296 and ITRF2014 against NATRF2022 geodetic;
- G2296 against G2139, ITRF2014 against ITRF2020, and G1762 against ITRF2020.

| Claim | Result |
|---|---|
| "Such a pair is grayed in the dropdowns, so it cannot be chosen" | **True.** With either end chosen, the other end's item lacks `ItemIsEnabled`. Both tabs, both ends, every pair. |
| "If changing one end would leave the other end's existing selection in such a pair, the other end is cleared and the status line reads 'Cleared: no published transformation between those reference frames.', so Convert is not offered" | **True on both tabs, by both routes.** (a) A user route: choose To, switch to Vertical only, choose an incompatible From, then switch back to Horizontal. To is reset to the placeholder. (b) An incompatible item forced with `setCurrentIndex` at either end: the opposite end is reset. Every time, the status text equals `controls.FRAME_RESET_STATUS` exactly and `convert_button.isEnabled()` is False. |
| "A job that states such a pair is refused by name" (both bullets) | **True.** I ran 70 `job.run` configurations with a date, each with every frame in each listed role: each of the five frames as G2Z into two SPCS2022 zones, as Z2G out of them, and as G2G against NATRF2022 and against every other global frame, both ways. All 70 raise `FrameTransformationUnavailableError`, and every message names the frame. Samples: "Cannot convert from WGS84(G2296) to NATRF2022 ... HTDP ... does not carry NATRF2022 at all"; "Cannot convert from ITRF2014 to ITRF2020 ... Convert via NAD83(2011) instead". |
| "grayed and cleared exactly as above" (realization to realization, ITRF to ITRF) | **True.** These are the same checks as the rows above. |

**Totals:** 416 GUI checks with 0 problems, and 70 jobs with 0 problems.

**Harness validity:** I added a compatible control pair, G2296 against MI-S. That pair raised 42 problems from its 52 checks: every check of graying, clearing, status and Convert flagged it. The harness therefore discriminates.

## The other claims

| Claim | Result | Evidence |
|---|---|---|
| No em dashes | **True** | There are 0 U+2014 and 0 U+2013 characters. The only non-ASCII character is U+21C4 (⇄) on line 131. There is no BOM and no CRLF. |
| 4,793 tests pass in both modes, with six container failures | **True** | Re-run here at HEAD. `pytest`: 4793 passed, 5 failed, 1 error. `pytest -O`: the same. The six are the known #65/#69 set. |
| Gate counts | **True** | Interim gate 1: seven LOW. Interim gate 2: 2 HIGH, 1 MEDIUM, 5 LOW. Closing gate: 1 MEDIUM, 7 LOW. No gate found a wrong number. Sources: DESIGN.md #70, `review/gate-wgs84-closing/output.md` and `reconfirm-output.md`. |
| "each gate's fixes passed a narrowing re-confirmation" | **True** | Every gate's fixes were confirmed at the root. (The closing gate's re-confirmation returned new LOWs, which are what this check covers.) |
| 382 near-tie records: 374 reproduced, 8 refused | **True** | `NEAR_TIE_RUNS` holds 382 records, of which `_near_tie_inside` accepts 374 and 8 have the role `outside`. |
| 1,846 anchors; 480 grid nodes | **True** | `HTDP_RUNS` holds 1,846 records. `test_htdp.py:589` asserts 480. |
| 2,050 Single point configurations and 540 Multi point jobs | **True** | `output.md`, section 1 and section 2. |
| 617,164 records; 1,500 jobs and about 6,700 points | **True** | DESIGN.md #70. |
| Thirteen self-test checks | **True** | `launch.py --selftest` prints "SELF-TEST PASSED - 13 checks." |
| Nine build gates | **True** | `tools/build_release.py` defines nine `gate_*` functions. |
| Realization start dates | **True** | `frames._WGS84_IN_USE_FROM`. |
| Round-trip bound 9.2e-6 / 6.4e-5 / 4.3e-6 m, for 1990 to 2035 and -250 m to 610 m | **True** | DESIGN.md #70, interim gate 2, L3 and N1. |
| x87 stand-in: 6 of 1,846 and 128 near-tie records differ | **True** | `check_ngs_windows_binary.py` docstring. |
| Height figures: 1.2e-5 m per 40 m; 0.18 mm north, 0.13 mm east | **True** | DESIGN.md #70 (W0) and PLAN-wgs84.md:81. |
| The bare "WGS 84" is never offered and is refused by name; the date is gated; a future date is refused; a stray date is refused | **True** | Checked by the re-confirmation's L6 section. GUI tests pass. |

## False or overstated sentences

| # | Sev | Line | Text | Problem | Correction |
|---|---|---|---|---|---|
| F1 | LOW | 259-260 | Under "Not verified yet: still to do before this ships": "**The closing review gate** over the whole build, then the release build" | **Stale. N3's class, missed by the N3 fix.** Lines 5-6 and 226-233 say the closing gate ran and its findings are fixed. This bullet still lists it as outstanding, so the file contradicts itself. | Drop the closing gate from that bullet. For example: "**The release build**: `py tools/build_release.py --acknowledge-ngs-beta` on the owner's machine." If wanted, mention the optional Codex re-confirmation there. |
| F2 | LOW | 156-158 | "No number was ever wrong **in either case**; **both** are sentences in the job record" | **Stale since item 3 was added.** The section now has three items, and its heading was changed from "two false sentences" for that reason. | "No number was ever wrong in any of them; all are sentences in the job record". |

**INFO (not a finding):** item 3 quotes two of L7's three corrected phrases. The third is the geoid-swap branch's "the factors are stated against" in FILES WRITTEN. It is present in released records, and the re-confirmation's matrix shows it changing. Nothing written is false: such jobs are vertical-only on geodetic input, so they fall under items 1 and 3 and are excluded from the "byte for byte" sentence. Item 3 simply under-itemizes.

No wrong number was found, and no claim about the interface or a refusal is false.

VERDICT: FINDINGS
