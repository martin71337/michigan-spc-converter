# Interim gate 1, WGS 84 build: narrowing re-confirmation of the fixes

**Reviewer:** an independent Opus reviewer. I did not write the fixes.
**Scope:** commit `315c7cb` (the diff `99a209d..315c7cb`) on `claude/brave-noether-88m7x1`. The surfaces checked
are L1, L2, L3, L4, L6's figure and L7. L5, I1 and I2 are deferred to W3 (plan section 3.5) and are not
re-raised. L6's three advice sentences are a recorded disposition.
**Repository:** read-only. This file is the only one I wrote there. Every seed was planted in a scratch export
of HEAD (`git archive HEAD` into `/tmp/claude-0/reconf1/repo`). After each run the file was restored byte for
byte and its SHA-256 checked. `git status` in the real repository shows only this file.
**Oracle:** NGS HTDP v3.6.0, compiled from `review/wgs84-w0/htdp-v3.6.0/*.f` with
`gfortran -O0 -std=legacy -w`. My binary's SHA-256 is `3738c50c…7f8f`, which is identical to W0's build as
recorded in `near_tie_truth.json`. I drove it with calendar entry, and the NAD 83 side was always `1 1 2010`.

## Suite

| Mode | Result |
|---|---|
| `QT_QPA_PLATFORM=offscreen python3 -m pytest -q -p no:cacheprovider --continue-on-collection-errors` | **4345 passed**, 5 failed, 1 error. Exit 1. |
| The same with `python3 -O` | **4345 passed**, 5 failed, 1 error. Exit 1. |

The failures are exactly the 6 known environmental ones, in both modes:
- the `test_zone_registry` collection error;
- `test_fileio::test_r3_3_*`, three tests;
- `test_geodetic_dms_export::…half_way_point_writes`;
- `test_projection_engines::…page_ngs_served`.

## Per-finding table

| # | Fixed at root? | Pin real? | Evidence |
|---|---|---|---|
| **L1** citations | **Yes** | **Yes, for the citations; see N2 for the checker itself** | Every line L1 named now cites the right line. I read them in `htdp.f`: `dtime` is at 4603; the assignments run 4604-4610 and 4612-4614; 7379 `HT = HTOLD`; 7381-7382 and 7384-7385 are the two `COMPSN` calls; 7387-7389 are the three sums; 4677-4678 is `iframe(1)`/`nframe(1)`. The two extra corrections (458-474, 467-474) are also right. The parser finds 268, 664 and 24 citations (floors 150, 480 and 10). Eight seeds each failed `test_every_fortran_line_citation_names_a_real_non_blank_line[<module>]`: frames.py back to `4676-4677`; `7379`→`7378`; short form `:7384-7385`→`:7383-7384`; `4610`→`4611`; a reversed range; `47704`→`947704` (out of range); a continuation `152 and 154`→`and 155`; and a comma continuation `, 4768`→`, 99999`. |
| **L2** near ties | **Yes** | **Yes** | **Oracle:** I re-derived **all 382 records of all 68 runs** with my own binary and my own stdin. That is the 360 near-tie records, the 16 window-edge records (outside ones included) and the 6 gate-1 counterexamples: **0 mismatches**, and every stored `stdin` is byte-identical to mine. **Generator:** I re-ran it end to end with `--capture` on my binary in the scratch copy. It reproduced `near_tie_truth.json` with every run identical; only `capture_utc` differs. **Arithmetic:** 2,400 fresh random records across all 10 directions match my binary, 0 mismatches. **Seeds:** S15 (`ylat + (ylat2 - ylat1)`) fails 8 tests, including `test_the_gate1_counterexamples_print_as_htdp_prints_them[GATE1S15N4]` and five from-NAD 83 latitude near ties. S26 (`math.radians(xlat)`) fails 39. My two variants were caught too: S15 on the longitude fails 11, and S26 on the longitude fails 24. The gate's S26 example prints `44.1607289389`, as HTDP does. |
| **L3** window edges | **Yes** | **Yes** | `_cell_is_in_window` is the old expression, unchanged. `_window_node` turns a missing node into `HtdpVelocityGridError`, a subclass of `HtdpRefusal`. **Seeds, each caught:** S16b fails 5, including `…[60-40-False-east…]`, `test_east_edge_last_accepted_and_first_refused_lookup` and both `EDGEEOUT` records. S16 (north row) fails `…[40-53-False-north row…]`, so it is now pinned independently of S17. S17 (`north_of_edge = False`) fails 5, including both `test_north_of_region_6_is_refused_by_the_region_edge_by_name`. My own west and south off-by-ones fail 4 each. S17b (`>=`→`>`) fails `test_north_edge_last_accepted_lookup_and_the_region_edge_refusal`. Making `_window_node` raise `KeyError` again fails `test_an_untranscribed_node_is_a_refusal_never_a_key_error` and `…off_by_one_window_still_fails_closed…`. **The gate's input:** 44.0 N, 80.4 W in G2296 on 2020-01-01 is refused with `HtdpVelocityGridError` before and after the fix, and under S16b it is now that class, not `KeyError`. |
| **L4** record vs code | **Yes** | **Yes** | **The gate's job now refuses.** It was GEODETIC_TO_ZONE with `replace(WGS84_G2296, code="NAD83(2011)")`. It wrote an archive at `99a209d`. It now refuses with `FrameRecordMismatchError` before the file is read and writes nothing, and the message names all six differing fields. `replace(ITRF2020, code="WGS84(G2296)")` passed `require_frame_path` before and is refused now. **Seeds, each caught:** the old silent substitution (6 tests); equality by code only (6); ignoring `htdp_frame`, `name` and `citation` in the comparison (5); `geodetic_position` keeping the caller's record (2, including `test_project_point_and_geodetic_position_refuse_the_disagreeing_record`); `project_point` returning `frame=source_frame` (1, `test_a_record_equal_in_value_resolves_and_the_conversion_carries_the_registrys`); `resolve_frame`'s `TypeError` removed (1). |
| **L6** figure | **Yes** | **Yes** | I re-measured with my binary at 43.82 N, 84.77 W, h 200 m, NAD83@2010.0 to menus 6-12 @2010.0. The largest pairwise 3-D difference is **8.727 cm**, between G730 and G1674, so "up to about 9 cm" is right. Transit to G730 is 1.113 m (1.096 m north), so "about 1.1 m" stands. The test asserts both `"up to about 9 cm"` and `"8 cm" not in message`. No "about 8 cm" remains in code or docs; the gate report and a test comment quote it as history. |
| **L7** rename | **Yes** | n/a | `test_the_frozen_round_trips_include_records_that_do_not_close` says what the body does, and its docstring names the test that holds the module to HTDP's non-closure. The old name appears only in that docstring and in the gate report. |

## L4: does strict equality refuse anything the program legitimately builds or passes?

**No.** Probed exhaustively:
- **Zones:** every zone in `zones.ALL_ZONES` carries the registry's own frame object (`is`, not just `==`).
- **Copies:** every frame in `frames.ALL_FRAMES` resolves to the registry object through `resolve_frame`, as
  itself and as `copy.copy`, `copy.deepcopy`, a `pickle` round trip and `dataclasses.replace(f)`.
- **Pairs:** `require_frame_path` over all 64 ordered pairs gives the same outcome and the same path object for
  the registry records and for their deep copies. `FrameRecordMismatchError` was raised 0 times.
- **Single points:** `project_point`, for all 8 frames × all 22 zones as registry records and as deep copies,
  never raised `FrameRecordMismatchError`. Every accepted result carries the registry object. Every refusal is
  the pre-existing `FrameTransformationUnavailableError` or `FrameNotUsableError`. `geodetic_position` accepts
  all 8 frames and their copies and returns the registry object.
- **GUI:** `GEODETIC_CHOICES` holds the registry objects for NAD83(2011) and NATRF2022, and `frames_offered()`
  offers exactly those two. Over all 64 pairs, `frames_have_a_path` is True only for the two identities, as
  before.
- **Self-test:** `michspc.selftest.run_selftest` passes **11 of 11** from source, including check 11, the
  cross-frame refusal.
- **Jobs:** 54 legitimate `job.run` → `exports.write_all` configurations, built from the registry records and
  from deep copies. They cover:
  - NAD83(2011) on the three SPCS 83 zones: G2Z, Z2G, Z2Z, VERTICAL_ONLY geodetic, and H+V G2Z;
  - NATRF2022 on four SPCS2022 zones: G2Z, Z2G, Z2Z.

  All 54 completed. All 176 archive members are byte-identical to the same jobs run at `99a209d` (timestamps
  and temporary paths normalized), and identical between the registry and copy variants. **No number moved.**

## New findings

| # | Sev | Finding | Counterexample | Fix |
|---|---|---|---|---|
| **N1** | LOW | **Two scratch files were committed at the repository root by `315c7cb`.** `in.txt` holds 12 Michigan points, and `out.txt` is an HTDP run from NAD 83 to **WGS84(G2139) at 2025-08-12**. Nothing references them. The commit message does not mention them, and `.gitignore` covers only `review/*.txt`. They are not shipped (`michspc.spec` and the installer do not pick them up). Still, an HTDP output file of Michigan coordinates in a WGS 84 realization, sitting unexplained beside the program's sources, is a document someone may later take for a reference. | `git show --stat 315c7cb -- in.txt out.txt` shows 12 and 21 lines added. `git log -- in.txt` shows only `315c7cb`. | `git rm in.txt out.txt`. Optionally ignore `/in.txt` and `/out.txt`, since HTDP's file-mode stdin writes them in its working directory. |
| **N2** | LOW | **The citation check's verdict half has no self-test, so it can pass vacuously.** `test_the_citation_check_sees_each_form_it_claims_to` feeds L1's forms to the regexes, and the floors stop a parser that finds nothing. Neither ever passes a known-bad citation through `_bad_citations`. A regression there leaves the whole suite green while no citation is checked. | In the scratch copy, `bad.append(f"{module}:{number} cites {cited}:{span}")` → `pass` gives `tests/test_htdp.py` all green. So does `blank_or_missing` reduced to a range check, dropping `or not lines[k - 1].strip()`, which is exactly the L1 class. | Add one assertion that `_bad_citations` flags a synthetic `htdp.f:4676-4677` and `htdp.f:7378`, for example by factoring the per-line check so it can be called on a probe line. |
| N3 | INFO | One continuation form is not parsed. At htdp.py:216, in "``htdp.f:3221-3224`` for the input frame, ``3240-3243`` for the output", the second range is not seen because words separate it from the first. It is correct (3240-3243 is the target-frame ellipsoid block, which I checked). The test's "every citation" claim slightly overstates its reach. | — | None needed, or reword. |
| N4 | INFO | S15 on the height, `htnew = ht + (ht2 - ht1)`, is not caught. The two groupings differ by at most one ulp of h, about 3e-14 m at 200 m. The near-tie HT records sit about 1e-9 m from their tie, bounded by HTDP's Cartesian round trip, so no record can see this change. In practice it is an equivalent mutant, the I3 class, not a pin gap. | — | None. |
| N5 | INFO | The commit message says 955 citations; the parser finds 956 (268 + 664 + 24). | — | None. |

Nothing the fixes introduced produces a wrong number, refuses legitimate work or writes a false message. I read
the `FrameRecordMismatchError` text on both of the gate's counterexamples. Each field it names really differs,
"differ"/"differs" agrees in number, and the `frame_by_code` it recommends exists and returns the registry
record. Its "for NAD 83 and WGS 84 a metre or more apart" is offered as an example and is true. The text is
developer-facing, but only a hand-built record reaches it; the GUI and the job settings cannot.

VERDICT: FINDINGS
