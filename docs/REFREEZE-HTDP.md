# RE-FREEZE: every HTDP-derived artifact MUST be recaptured when NGS changes HTDP

**Status: STANDING, from 2026-10-21. This is an obligation that waits on NGS,
not unfinished work.** MCX's WGS 84 and ITRF conversions are a transcription
of NGS's **HTDP v3.6.0**, `github.com/noaa-ngs/HTDP` commit
`59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c` (tag `v.3.6.0`, "April 7, 2025",
`htdp.f:27-28`). Every constant, every anchor, every measured figure the job
record states and the frozen bundle's own check were taken from THAT commit.
Authority: DESIGN.md **#70**; the plan is `docs/PLAN-wgs84.md` (section 3.8,
"so a new HTDP release reopens the anchors"); W0's measurement is
`review/wgs84-w0/RECON.md`.

This is a mechanism, not a memory, on the pattern of `docs/REFREEZE-NSRS.md`.
Every artifact below carries the literal commit id above; the two-way
inventory test (`tests/test_refreeze_htdp_inventory.py`) requires the table
here and the tree to agree, so an artifact that carries the commit and is not
listed fails the suite, and a row that names a file which no longer carries it
fails the suite too. The commit id is the token on purpose: when
`michspc/spc/htdp_data.py`'s `HTDP_COMMIT` moves to a new release, every
artifact still carrying the old id stops matching, and the test names each one
that has not been recaptured.

## What is NOT affected

HTDP is NGS's official, released program, not a beta product: nothing here is
pre-release, and the `NGS beta` release gate does not apply to it. A new HTDP
release does not make MCX's v3.6.0 numbers wrong - they remain exactly what
v3.6.0 computes, and the job record says v3.6.0 and the commit. What it ends
is the claim that MCX reproduces **NGS's current** HTDP, which is the claim
the owner's rule (replicate NOAA, the authority; DESIGN.md #36 and #38) asks
this program to keep true.

## The trigger

The monthly tripwire, `tools/nsrs_tripwire.py`, probe 5: the head of the
`noaa-ngs/HTDP` default branch, read from GitHub's API, against the frozen
commit above. A different head fires it (exit 1, `review/tripwire/REVIEW-NEEDED.txt`,
a message box), the same way the NSRS probes fire. A fetch that fails or an
answer that is not a commit is "could not check" (exit 2), never quiet.
Also watch NGS's HTDP page, `https://geodesy.noaa.gov/TOOLS/Htdp/Htdp.shtml`,
for a release announced there before it reaches GitHub.

A fired tripwire means: do the steps below. Never believe the tripwire's own
summary without the recapture - a new commit may change only the README, and
the recapture is what says so.

## When HTDP changes, in order

1. **Recapture W0 with `review/wgs84-w0/drive_htdp.py`.** Commit NGS's new
   source unmodified beside the old (`review/wgs84-w0/htdp-v<new>/`, `-text`
   in `.gitattributes`, every file SHA-256 pinned), compile it the way W0 did
   (`gfortran -O0 -std=legacy -w *.f`), and run the harness over the same
   lattice, frames, epochs and dates. Diff the new `htdp_truth.json` against
   the old one record by record. **An identical capture means no number
   moved**: the artifacts are re-dated to the new commit, not rebuilt. Any
   difference is measured and recorded, never assumed to be zero.
2. **Regenerate the fixtures with their generators.**
   `review/wgs84-w0/make_anchor_fixture.py` (from the new truth),
   `review/wgs84-w0/make_near_tie_anchors.py --capture BINARY` and
   `review/wgs84-w3/make_w3_anchors.py --capture BINARY`. Each refuses a
   binary that is not the pinned build; the pin moves with the new source,
   deliberately. Re-transcribe `michspc/spc/htdp_data.py` (and
   `michspc/spc/htdp.py` if the arithmetic moved) from the new Fortran, and
   update the frozen bundle's anchor in `michspc/selftest.py` from the new
   fixture.
3. **Re-run the transcription pins and every gate.** `tests/test_htdp.py`
   re-parses the committed Fortran and requires every transcribed constant to
   equal it; the anchor suites require every frozen record at HTDP's printed
   digit; `review/wgs84-gate2/roundtrip_range.py` re-measures the round-trip
   bound the job record states; the inventory test below requires every row
   to carry the new commit. Then the full suite in both run modes, an
   independent gate over the change, and NGS's own Windows `htdp.exe` of the
   new release run through `review/wgs84-w0/check_ngs_windows_binary.py`.
4. **Re-release consciously.** A new MCX version whose release notes state
   the HTDP version and commit it now reproduces, what moved and by how much,
   recorded as a DESIGN.md amendment. Update `FROZEN_HTDP_COMMIT` in the
   tripwire last, so the tripwire keeps firing until the release is done.

**Nothing here is a substitute for the measurement.** The difference between
v3.6.0 and its successor at Michigan's positions is a number that must be
printed, not a risk to be described.

## Tagged artifacts

**This is the table `tests/test_refreeze_htdp_inventory.py` parses, and its
format is load-bearing**, exactly as in `docs/REFREEZE-NSRS.md`: one row per
file in `michspc/**`, `tests/fixtures/**` or `tools/**` that carries the
literal commit id `59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c`; the row's
**first cell is that file's repository path, in backticks, and nothing
else**. The recapture and pin cells name existing paths in backticks; a pin
may name a test function after `::`.

| Artifact | What it carries from HTDP | Recapture or source | Authenticating pin |
| --- | --- | --- | --- |
| `michspc/spc/htdp_data.py` | Every constant transcribed from the Fortran: the Helmert sets of both conventions, the 480-node region-6 velocity window, the ellipsoid and inline constants, the version, date and commit. | `review/wgs84-w0/htdp-v3.6.0/initvl.f` | `tests/test_htdp.py::test_the_velocity_window_is_initvl_number_for_number` |
| `michspc/spc/htdp.py` | HTDP's arithmetic transcribed routine by routine (TOXYZ, FRMXYZ, the Helmert, PREDV, VTRANF, NEWCOR, the date clocks), each cited to its `htdp.f` lines. | `review/wgs84-w0/htdp-v3.6.0/htdp.f` | `tests/test_htdp.py` |
| `michspc/spc/frames.py` | The five frame records and ten HTDP path records: menu numbers, ellipsoid by name, and citations quoting `htdp.f` lines and the commit. | `review/wgs84-w0/htdp-v3.6.0/htdp.f` | `tests/test_frames_wgs84.py` |
| `michspc/fileio/report.py` | The job record's measured figures: the 1,846-record anchor count, plan D6's height costs, and the round-trip non-closure with the dates and heights it is measured over. | `review/wgs84-gate2/roundtrip_range.py` | `tests/test_frame_disclosure.py::test_the_round_trip_range_is_the_committed_measurement` |
| `michspc/selftest.py` | The frozen bundle's own HTDP anchor (check 12): record `P073H600` of run `calfwd_2026-10-20`, its input, HTDP's printed output, and the grid coordinate that output projects to. | `review/wgs84-w0/make_anchor_fixture.py` | `tests/test_selftest.py::test_the_selftests_htdp_anchor_is_the_frozen_htdp_record` |
| `tests/fixtures/htdp_anchors.py` | 1,846 frozen TRFPOS records in 76 runs: every offered frame, both directions and the round trip, every calendar-equivalent epoch. | `review/wgs84-w0/make_anchor_fixture.py` | `tests/test_htdp.py::test_the_generator_reproduces_the_fixture_byte_for_byte` |
| `tests/fixtures/htdp_near_tie_anchors.py` | 382 near-tie, window-edge and gate-1 records, each within an ulp or so of HTDP's rounding or of the window's edge. | `review/wgs84-w0/make_near_tie_anchors.py` | `tests/test_htdp.py::test_the_near_tie_generator_reproduces_its_fixture_byte_for_byte` |
| `tests/fixtures/htdp_w3_anchors.py` | Interim gate 1's L5 position in all five frames, both ways, at 2025-06-15. | `review/wgs84-w3/make_w3_anchors.py` | `tests/test_job_wgs84.py` |
| `tools/nsrs_tripwire.py` | The frozen commit the HTDP probe compares the default-branch head against. Updated LAST, at the re-release. | `michspc/spc/htdp_data.py` | `tests/test_nsrs_tripwire.py::test_the_frozen_htdp_commit_is_the_commit_the_program_transcribes` |

## The frozen captures those artifacts were read from

Not scanned by the inventory test: they are NGS's own bytes and the captures
of its binary's output, held unmodified, and the harnesses above re-create
them. Their digests are pinned where they are used (`tests/test_htdp.py`,
`tests/test_job_wgs84.py`, and the provenance block of each fixture).

| Capture | What it is |
| --- | --- |
| `review/wgs84-w0/htdp-v3.6.0/` | NGS's source at the frozen commit: `htdp.f`, `initbd.f`, `initeq.f`, `initps.f`, `initvl.f`, each SHA-256 pinned. |
| `review/wgs84-w0/htdp_truth.json` | W0's capture: 45,408 printed records from 176 TRFPOS runs. |
| `review/wgs84-w0/near_tie_truth.json` | Interim gate 1's near-tie and window-edge capture. |
| `review/wgs84-w3/w3_truth.json` | W3's L5 capture. |
| `review/wgs84-gate2/roundtrip_range_output.txt` | The round-trip bound's measurement through `michspc.spc.htdp`. |

## Not verified, and how to verify it

The oracle is HTDP compiled here with gfortran on x86_64 (SSE2). **NGS's own
32-bit Windows `htdp.exe` has not been run against these anchors**; an x87
build here flips the last printed digit on 11 of 176 runs (RECON.md section
4). `review/wgs84-w0/check_ngs_windows_binary.py` runs NGS's shipped
`htdp.exe` over every anchor input of the two main fixtures on the owner's
Windows machine and reports each difference with its size; its docstring says
how to read the result.

**Do not remove this file while MCX carries an HTDP transcription.** Unlike
`docs/REFREEZE-NSRS.md`, it does not close: it is the standing statement of
which HTDP MCX reproduces and what must happen when NGS publishes another.
