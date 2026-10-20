# Interim gate 1, WGS 84 build: independent adversarial review of W1 and W2

**Reviewer:** an independent Opus reviewer, working blind to the lead's review. **Scope:** the committed diff
`fbcbf4a..acf31a7` on `claude/brave-noether-88m7x1` (W1 = `4de081b`, W2 = `acf31a7`). Nothing uncommitted was in
scope. I wrote no file in the repository except this one. All scratch work is in `/tmp/claude-0/gate1/`.

**Oracle:** NGS HTDP v3.6.0, compiled from `review/wgs84-w0/htdp-v3.6.0/*.f` with
`gfortran -O0 -std=legacy -w` (GNU Fortran 13.3.0, x86_64). I drove it non-interactively with calendar dates, and
the NAD 83 side was always 1 1 2010. I compared every record as three separate printed strings (latitude,
longitude, height), never through a `max()`.

## Verdict in one paragraph

**The arithmetic is clean and the safety property holds.**
- **Numbers:** `michspc.spc.htdp` reproduced the binary at its printed digit on every accepted record of 617,164
  fresh comparisons. They span all ten frame and direction pairs, dates from 1907-01-01 to 5941-12-10 (every
  calendar day from 2008 to 2031), heights from -6,000 km to +100 km, the window edges, the 45.00002 N switch and
  the grid-cell boundaries.
- **Fixture:** all 1,846 frozen anchors re-derive identically from my own build of the oracle.
- **Safety:** no path through `job.run`, `convert.project_point`, `convert.convert_point` or the GUI's
  `frames_have_a_path` carries a WGS 84 or ITRF position into a NAD 83 output. I tried 960 job configurations.
- **Seeds:** all 23 W2 seeds were caught.

I found **no CRITICAL, HIGH or MEDIUM** finding. There are **seven LOW** findings: wrong citations, three pin gaps
that only matter at the last place or outside Michigan, a code-versus-`htdp_frame` consistency hole that W3 must
not build on, a defence-in-depth single gate, and message wording. There are also four INFO notes.

---

## Findings

| # | Sev | Finding | Counterexample (input) | Observed | Expected | Root cause |
|---|---|---|---|---|---|---|
| L1 | LOW | Wrong `htdp.f` line citations | Read the cited lines | (a) `_toit94`, htdp.py 675-685, cites 4604-4615. Every comment is one line late: `dtime` is at 4603, and the `ds` comment cites 4611, a blank line. (b) `_newcor`, htdp.py 959-964, cites 7378, 7380-7381, 7383-7384 and 7386-7388; 7378 is blank. (c) NAD 83's MENU1 entry is cited "htdp.f:4676-4677" at htdp.py:239 and frames.py:327, and 4676 is blank. | (a) 4603-4614. (b) 7379, 7381-7382, 7384-7385, 7387-7389. (c) 4677-4678. | Only SETTP's citations are pinned (`test_the_helmert_sets_are_settp_number_for_number`). Per-line citations in `htdp.py` are checked by nothing. I paired all 127 single-line citations with the Fortran line they name; the rest are correct. |
| L2 | LOW | The anchors cannot see a change in the order of operations at the last place | Seed S15: in `_newcor`, `ylat + ylat2 - ylat1` becomes `ylat + (ylat2 - ylat1)`. Seed S26: `ylat = math.radians(xlat)` replaces `(xlat*3600)/RHOSEC`. | The suite stays green. Against the oracle, S15 changes 1 of 120,000 fresh records and S26 changes 5, each by one unit in the 10th decimal of latitude. Example for S26: input 44.16073757508377, 84.2231097333896, 0.0 gives 44.1607289388 where HTDP prints 44.1607289389. | A pin that fails. The plan says the anchors "at the printed digit" are what hold fidelity (§4, §6). | 1,846 anchors chosen by position are almost never within about 1e-3 of a print unit of a rounding tie, so a change of one ulp is invisible. 1e-10° is about 11 µm, so this is not a geodetic matter. A small set of near-tie anchors from a fuzz like mine would close it. |
| L3 | LOW | No pin at the transcribed window's own edges | Seed S16b, in `_window_cell`: `i + 1 <= i_high` becomes `i <= i_high`. Then `htdp.to_nad83(44.0, -80.4, 0.0, WGS84_G2296, 2020-01-01)`. | Suite green. The call raises `KeyError (61, 40)`, which is not an `HtdpRefusal` and so passes through every `except HtdpRefusal` or `except FrameMismatchError`. Separately, seeds S16 (north row, `j + 1 <= j_high` becomes `j <= j_high`) and S17 (`north_of_edge = False`) each mask the other, so neither check is individually pinned. | `HtdpVelocityGridError`, and a test that fails. | `test_outside_the_transcribed_window_is_refused` uses 80.0 W, 93.0 W and 40.0 N. Those are cells I = 61, I = 35 and J = 33, a whole cell or more outside the window. Nothing probes the last accepted cell, or the first refused one, on any edge. The unseeded code is right: 19,965 accepted records within ±0.0005° of each edge all match HTDP. The edges are at least 1.2° outside Michigan. |
| L4 | LOW | `ReferenceFrame.__post_init__` does not tie `code` to `htdp_frame`, `epoch_kind` or `name`. These are a second typed copy that can disagree with the code. | `fake = dataclasses.replace(frames.WGS84_G2296, code="NAD83(2011)")` constructs: TIME_DEPENDENT, `htdp_frame=htdp.WGS84_G2296`, WGS 84 ellipsoid. Run a GEODETIC_TO_ZONE job with `geodetic_frame=fake`. Also `dataclasses.replace(ITRF2020, code="WGS84(G2296)")` constructs. | The job runs as a NAD 83 identity because `_canonical` resolves by code. `PointConversion.frame` carries the fake record, and the README says `Reference frame NAD83(2011) - World Geodetic System 1984, realization G2296`. | Refused at construction, or canonicalized before use. | `__post_init__` checks `htdp_frame` against the ellipsoid and the epoch kind, but never against the record that `code` names. Today `_canonical` makes this harmless: nothing in the pipeline reads `htdp_frame`, and the GUI only passes registry records. **The W3 hazard:** if W3 reads `settings.geodetic_frame.htdp_frame` or `.is_time_dependent` from the caller's record rather than the canonical one, the code and the arithmetic can disagree. The registry's own five mappings are pinned (`frame.htdp_frame is carried`). |
| L5 | LOW | Defence in depth: VERTICAL_ONLY geodetic jobs have one gate, not two | Seed F13 removes the VERTICAL_ONLY branch of `_require_a_registered_frame_path`. Then run a VERTICAL_ONLY job with `geodetic_frame=WGS84_G2296`, ELLIPSOID, NAVD 88 to NAVD 88, and the row `1,43.0,-84.5,165.000`. | The job runs and writes NAVD 88 198.085. h in WGS 84 was taken as h in NAD 83, about 1.07 m off by HTDP. The bare `WGS84` record does the same. | Refused. | `convert.geodetic_position` has no frame gate; this predates the diff. `_require_a_convertible_ellipsoid_height_frame` names only NATRF2022. Every other direction is guarded both at the settings and at each point; this one only at the settings. **The suite does catch F13**, so this is not a pin gap. W3 should guard `geodetic_position` and extend the height gate. |
| L6 | LOW | Refusal wording | (a) `require_frame_path(WGS84, NAD83_2011)`. (b) `(NATRF2022, WGS84_G2296)`. (c) `(WGS84_G1762, WGS84_G2296)`. | (a) "The reference frames this program can carry are: …, WGS84(G1762), … ITRF2020" and "Choose the realization…". (b) "This program's path for a position in WGS84(G2296) is to NAD83(2011)". (c) "Convert via NAD83(2011) instead". In this build, every one of those instructions ends at the W2 guard's refusal. The bare-label citation also says the modern realizations "differ … by up to about 8 cm". My HTDP run at 43.82 N, 84.77 W, h = 200 m (NAD83@2010.0 to menus 6-12 @2010.0) gives a largest pairwise 3-D difference of **8.73 cm**: 5.42 cm horizontal, with component spreads of 2.95, 5.20 and 7.50 cm. That reproduces the lead's figures. | (a) to (c) are true from W3 onward. "About 9 cm", or the components. | The text was written for W3's behaviour, and the 3-D figure was rounded down. Transit 1.11 m ✓. Mislabelled NAD 83: 1.32 m horizontal at 2026.8 ✓ (1.15 m at 2010.0). The GUI cannot reach any of these messages yet. |
| L7 | LOW | The name of one test overstates what it checks | `test_htdps_round_trip_does_not_close_and_neither_does_this_one` | It counts fixture records only, never calls `htdp`, and passes against any module. | Either compute the non-closure through the module, or rename the test. | The claim in the name is actually held by `test_the_round_trip_chains_to_htdps_own_round_trip`. |
| I1 | INFO | Stray `geodetic_frame` | ZONE_TO_ZONE, or VERTICAL_ONLY with `source_zone=MI_SOUTH`, with `geodetic_frame` set to WGS84_G2296 or the bare WGS84 | The job runs, the field is ignored, and the README states only the zone's frame, `NAD83(2011)`. I checked the written archive. | (W3) Refuse by name. | Plan §3.5 lists ZONE_TO_ZONE. **VERTICAL_ONLY with a zone input has the same stray field and is not in that list.** |
| I2 | INFO | Arguments of the wrong type fail closed, but not as a frame refusal | `project_point(43, -84.5, NAD83_2011, WGS84_G2296)`; `JobSettings(target_zone=WGS84_G2296)` | `AttributeError` | Arguably `TypeError` | Predates the diff; the zone parameter is not type-checked. |
| I3 | INFO | Mutants with no effect | S09b, S12, S13, S14, S14b, S20, S29, S32 | The suite was green, and each gives **0** printed differences against the oracle over 120,000 records (S32 changes no MJD at all) | — | These are not gaps. For example, IGS and IERS have the same rate differences (S09b), radii differ by about 1e-9 (S12), and the two FRMXYZ height formulas agree to sub-µm (S13, S14). |
| I4 | INFO | Height overflow in HTDP's own print | \|h\| ≥ 1e6 m | HTDP prints `**********` (F10.3); the module returns the number. Latitude and longitude match. | — | Out of reach for a surveyor. |

---

## Clean surfaces, and how each was checked

### 1. Numerical fidelity: 617,164 records compared, 0 differ at the printed digit

Harness: `scripts/harness.py`. Every record is checked component by component.

| Campaign | Records compared | Refused | Coverage |
|---|---|---|---|
| Broad (`fuzz_a.py`) | 125,581 | 6,419 | 10 pairs × 22 dates: 1907-01-01, 1950, 1999-12-31, 2000-02-29, 2009-12-31, **2010-01-01 (same day)**, 2010-01-02, the leap days 2012/2020/2024, year ends, 2100-02-28 and 2100-03-01, 2400-02-29, 3000, 5000, 5900. Positions from 40.3 to 50.2 N and 80.3 to 92.2 W. Heights from -500 m to +100 km. |
| Window edges (`fuzz_edges.py`) | 19,965 | 16,035 | Within ±0.0005° of 50.0 N, 40.5 N, 92.0 W and 80.5 W. 10 pairs × 3 dates. |
| 45° switch and cell boundaries (`fuzz_special.py`) | 210,000 | 0 | Input latitude stepped from 44.99995° in steps of 1e-7°. Lattice longitudes and latitudes ±3e-5°. 7 dates, including 2013-10-16 and 2015-12-31. |
| Dates (`fuzz_dates.py`) | 61,602 | 0 | 10,267 dates: every calendar day from 2008 to 2031, plus 1,500 random dates from 1907 to 5940 near month and year ends. |
| Full-precision doubles (`fuzz_repr.py`) | 200,000 | 0 | `repr()` inputs and random days from 2000 to 2032. |
| Integer-clock boundary | 16 | — | 5941-12-10 is the last day accepted (minutes = 2,147,483,520) and 5941-12-11 is refused, and HTDP agrees. |

Notes on the counts:
- **Every refusal was a lookup outside the window.** None fell inside 40.6 to 49.98 N and 80.6 to 91.9 W.
- **STOP 666 lines up exactly.** At h = -6.0e6 m the module and HTDP both compute; at h = -6.1e6 m both stop.
- **The fixture is genuine.** All 76 runs and 1,846 records of `tests/fixtures/htdp_anchors.py` were driven through
  my build with calendar entry, and every record is identical. The Jan-1 decimal entries in the fixture are
  therefore equivalent to calendar entry.

### 2. The safety property: holds

**Matrix** (`safety_matrix.py`, `safety_matrix2.py`). 960 `job.run` and `exports.write_all` runs:
- every Direction;
- every VerticalMode, with NGVD29 to NAVD88 and with NAVD88 to NAVD88;
- both HeightKinds;
- both zone and geodetic input for VERTICAL_ONLY;
- every registry frame;
- eight hand-built records: a G2296 marked not-usable; the bare WGS84 marked usable, and marked plate-fixed; code NAD83 carrying htdp G2296; code G2296 carrying htdp ITRF2020; code G2296 plate-fixed with no HTDP frame; a code with a trailing space; a new code.

**Results:**
- Every registered time-dependent frame and the bare WGS84 **refused on every direction that reads
  `geodetic_frame`.**
- The only runs that completed were zone-input jobs where `geodetic_frame` is unread (I1), and the hand-built
  record whose code is `NAD83(2011)` (L4).
- `project_point` refuses all five frames into SPCS 83 zones (the guard) and into SPCS2022 zones (D3).
- `convert_point` refuses a zone whose frame was replaced by any of the five, in both orders.
- `geodetic_position` tags its result with the input's own frame; it never relabels it. See L5.
- The GUI offers none of the five frames (`frames_offered`), and `frames_have_a_path` applies the guard.

**W2 seeds: 23 tried, 23 caught.** Each guard was removed in turn: `require_a_connected_path`, the guard in
`project_point`, in `convert_point`, in the job gate and in the GUI. The other seeds:
- the job's ZONE_TO_GEODETIC branch, and its VERTICAL_ONLY-geodetic branch;
- the usability check moved after the pair lookup;
- `_canonical` removed;
- an identity added for G2296;
- the ellipsoid check, the epoch-kind check, the method check, the NAD 83 reference-epoch check and the HTDP-pair check, each removed;
- the HTDP-pair check loosened to admit two global frames;
- `is_identity` decided by ellipsoid;
- the D3 and D4 messages collapsed together;
- a required pair dropped;
- the reverse direction statement given the wrong Helmert epoch;
- the bare WGS84 made usable;
- a time-dependent frame allowed a reference epoch;
- the guard's `TypeError` removed.

### 3. Registry contracts

- `REQUIRED_FRAME_PAIRS` is enforced at import, and its append-only rule is pinned. The 12 entries and each of
  the ten pairs are parametrized, so dropping one is caught (F17).
- The bare WGS84 is refused **before** the lookup, as `FrameNotUsableError`, against every frame in both orders.
- Every refusal message is true for its pair, apart from the W3-tense wording in L6. I read every message
  `_no_path_message` can produce.
- `FrameTransformation` stores no Helmert parameter: the fields are exactly source, target, citation and method.
  `direction_statement` is derived from the fields, and both directions match HTDP's composition.

### 4. Transcription, checked independently of the suite's parser

- **Velocity grid:** my own regex over `initvl.f` and IEEE single-precision rounding through `struct`: 480 nodes,
  1,440 values, 0 mismatches. I also checked all 480 `initvl.f:line B(index)` citations, 0 wrong.
- **Single-precision rounding:** `fortran_real` against `struct` on 200,000 random two-decimal literals,
  0 differences.
- **Helmert sets:** my own SETTP parser checked all 120 fields (IGS and IERS × frames 1, 15, 16, 17 × 15
  parameters), including `/ rhosec` appearing exactly on the rotations: 0 mismatches.
- **Single precision is applied to the right things:** the grid literals are REAL and the header bounds are exact.
- **Ellipsoid and inline constants match**, and the MENU1 names and indices match (lines 4704-4753 verified).

### 5. Tests

**Suite:** 4,084 passed in both `pytest` and `python -O`. The six known environmental failures are unchanged.

**htdp seeds: 41 tried, 28 caught.** The 13 the suite missed:
- 8 have no effect on output (I3);
- S15 and S26 change only the last place (L2);
- S16, S16b and S17 are the window-edge gap (L3);
- S32 changes no MJD at all.

The ones caught, among others: the Helmert at the output epoch; the velocity left in the input frame; the
velocity's sign in each component; GRS 80 on the WGS 84 frames; a one-day error on either clock; VTRANF omitted in
PREDV; the IERS set used for positions; a grid node transposed; the IGS set in XTO08; no leap year; true π on
output; VTRANF at the output XYZ; PREDV with the target's iopt; datetime and 1906 accepted; the INT4 check removed;
the scale sign in `toit94`; velocity applied on the same day; the sign of a rate rotation; a 365-day velocity year;
the single-precision rounding removed; one node altered; the height zeroed.

**No expected value is read back from the module's own output.** The fixture comes from the binary, and the
hand-derived values are derived in comments.

### 6. Epoch handling

- `ObservationEpoch` refuses a `datetime`, a string, a float and None.
- It refuses year 1906 and earlier, as HTDP does.
- It refuses dates past the INT4 minute clock; the boundary matches HTDP, as above.
- DATE and MINS reproduce GETMDY option 1 on every day from 2008 to 2031 and on the random far dates, through the
  oracle.
- Same-day handling, 2010-01-01 on a time-dependent frame, gives the Helmert alone, as HTDP does.

---

VERDICT: FINDINGS

(No CRITICAL, HIGH or MEDIUM. Seven LOW: L1 to L7. Four INFO: I1 to I4. The arithmetic of W1 and the safety guard
of W2 are clean. The LOWs are citations, pin gaps at the last place and at the window edges, a code-consistency
hole that W3 must not rely on, defence in depth, and wording.)
