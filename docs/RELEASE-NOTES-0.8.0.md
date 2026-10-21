# MCX 0.8.0 (DRAFT)

**DRAFT. Not released.** The version literal still carries its `-dev` marker
(`0.8.0-dev`), nothing is tagged, and the owner has not seen the new
controls on a real screen. The closing review gate over the whole build has
run, and its findings are fixed (below, under Verified).
The release build is made on the owner's machine. This file is written so that
what the release claims can be checked against what was actually verified.

---

**MCX now converts WGS 84 and ITRF positions.** It moves survey coordinates
between Michigan's three State Plane zones and the 19 SPCS2022 zones, between
State Plane and geodetic positions, converts elevations between vertical
datums and between geoid models, accepts GNSS ellipsoid heights, and
documents every job well enough to defend it. It is in production use by a
licensed professional surveyor.

This release adds **five global reference frames**, carried to and from
NAD 83(2011) by NGS's own HTDP. **Nothing about an existing job's numbers
changed**: every coordinate, elevation and factor an SPCS 83, SPCS2022 or
vertical job produces is what 0.7.1 produced.

## WGS 84 and ITRF, to and from NAD 83(2011)

Five frames, each a separate entry in every system dropdown, grouped below
the two NAD 83 and NATRF2022 geodetic entries:

- **WGS 84 (G1762)**, **WGS 84 (G2139)** and **WGS 84 (G2296)**: the three
  realizations in force since 16 October 2013;
- **ITRF2014** and **ITRF2020** by name, for precise point positioning
  results (CSRS-PPP, OPUS's ITRF output), so a PPP report's frame is selected
  as it is printed rather than translated into a G-number.

Each converts to and from **NAD 83(2011) at epoch 2010.0** (the epoch NGS,
OPUS, NCAT and the CORS networks publish NAD 83(2011) at), and through it to
and from **every SPCS 83 zone**, in every unit those zones offer.

- **Geodetic to geodetic** is a new direction: WGS 84 or ITRF latitude and
  longitude in, NAD 83(2011) latitude and longitude out, and the reverse. It
  exists only across one of these paths; NAD 83(2011) to NAD 83(2011) is still
  not a conversion.
- **Vertical modes work with the new frames.** A GNSS ellipsoid height in
  WGS 84 or ITRF goes to its NAD 83(2011) ellipsoid height and then to a
  NAVD 88 elevation through the selected geoid model, so a WGS 84 GNSS height
  becomes an elevation in one job.
- **Both tabs.** The Single point tab shows both positions, each labelled
  with its frame, when a transformation ran.

## The observation date

A WGS 84 or ITRF position means nothing until the date it was observed is
stated: Michigan moves about 17 mm a year in those frames against NAD 83. So
every job on one of the five frames carries an **observation date, entered as
a calendar date**:

- it has no default (Convert stays unavailable until it is answered), and
  the control is enabled only when one of the five frames is selected;
- it must be a real date (there is no 30 February) and not after the day the
  job runs;
- it is converted to a decimal year exactly the way HTDP converts a calendar
  date, and the job record states both;
- one date covers the whole job: a PNEZD file has no column for it, so every
  point in the file is taken as observed on that date, and the record says so;
- a date outside the selected WGS 84 realization's period of use (G1762 from
  2013-10-16, G2139 from 2021-01-03, G2296 from 2024-01-07, each ending the
  day before its successor) raises a warning naming the period. It does not
  refuse: reprocessed data can carry a later realization. The ITRF frames
  have no such period.

## NGS HTDP v3.6.0 is the authority

The transformation is **NGS's Horizontal Time-Dependent Positioning program,
HTDP v3.6.0** (`github.com/noaa-ngs/HTDP`, commit
`59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c`, 7 April 2025), transcribed into
MCX and held to HTDP's own output. It is not a reimplementation of the
geodesy: it is HTDP's arithmetic, including the parts a cleaner design would
change.

- **The Helmert transformation and the velocity model, as HTDP applies
  them.** HTDP evaluates the Helmert at the input epoch and then moves the
  position in the output frame with that frame's velocity, from its region-6
  velocity grid for the eastern United States (ITRF2008 velocities on a
  0.5-degree grid, interpolated bilinearly). All of Michigan, Isle Royale and
  the lakes lie in that region.
- **The ellipsoid follows the frame's name, as in HTDP**: WGS 84 (...)
  positions are on the WGS 84 ellipsoid, ITRF and NAD 83 on GRS 80.
- **Forward and reverse are not exact inverses, in HTDP.** Measured on HTDP's
  own arithmetic, for observation dates from 1990-01-01 to 2035-12-31 and
  heights handed to HTDP from -250 m to 610 m, a Michigan position carried out
  and back returns within 9.2e-6 m north, 6.4e-5 m east and 4.3e-6 m up. MCX
  reproduces that, and every job record states it.
- **The job record** gains a FRAME TRANSFORMATION block on transformed jobs:
  both frames and their ellipsoids, the observation date and decimal year,
  HTDP's version and commit, the composition in words, both Helmert sets'
  parameters, the velocity model, the height rule used and the round-trip
  figure above. The audit CSV gains the external position and the NAD 83
  position, each in columns named by frame, on transformed jobs only. The
  clean PNEZD export keeps its five fields and carries the target frame's
  values; a geodetic target writes its decimal and DMS pair as 0.7.1 does.

## Heights

- **An ellipsoid (GNSS) height is part of the 3-D position and is transformed
  with it.** The ellipsoid height out is the target frame's, above the target
  frame's ellipsoid. A WGS 84 height kept unchanged in a NAD 83 job would be
  about a metre wrong under the right label.
- **An elevation is in no frame, so it passes unchanged.** HTDP needs an
  ellipsoid height for the horizontal transformation and is handed the
  elevation in its place. Measured: the horizontal result moves 1.2e-5 m per
  40 m of height difference, so at most 0.012 mm in Michigan.
- **A blank height is transformed at an ellipsoid height of 0 m** and the Z
  stays blank. Measured: at 600 m of real height, Michigan's highest ground,
  the horizontal result moves at most 0.18 mm north and 0.13 mm east.

The job record states which of the three each job used and how many points
used it.

## What is refused

None of these ever passes coordinates through unchanged. What each one
does:

- **A bare "WGS 84".** A position labelled only "WGS 84" may be in any
  realization (about 9 cm apart across the modern ones, about 1.1 m from the
  original 1987 one), or may be NAD 83 output mislabelled by a data
  collector, 1.3 m away. It is not offered in any dropdown, and a job that
  states it is refused by name, the refusal naming the realizations to
  choose from.
- **WGS 84 or ITRF against NATRF2022 or an SPCS2022 zone.** HTDP does not
  carry NATRF2022, and going through NAD 83 would need the NAD 83 ⇄
  NATRF2022 transformation NGS has not published
  (`docs/DEFERRED-NATRF2022-BRIDGE.md`). Such a pair is grayed in the
  dropdowns, so it cannot be chosen. If changing one end would leave the
  other end's existing selection in such a pair, the other end is cleared
  and the status line reads "Cleared: no published transformation between
  those reference frames.", so Convert is not offered. A job that states
  such a pair is refused by name.
- **Realization to realization, and ITRF to ITRF.** No zone is defined on any
  of these frames, so the only conversion offered for a position in one is to
  or from NAD 83(2011). Such a pair is grayed and cleared exactly as above,
  and a job that states one is refused by name.
- **A position outside HTDP's velocity grid as MCX carries it** (Michigan
  with at least a degree of margin on every side): refused at Convert, never
  extrapolated, naming the point.
- **A WGS 84 or ITRF job with no observation date, or a future one.** Convert
  stays unavailable until a date is entered, and a future date is refused at
  Convert.
- **An observation date on a job with no WGS 84 or ITRF frame**, where it
  would answer a question the job never asks. The date control is grayed for
  such a job and its date is not sent; a job that states one anyway is
  refused by name.

## Corrected: false sentences in earlier job records

**Present in 0.4.0 through 0.7.1, and corrected here. No number was ever
wrong in any of them**; all are sentences in the job record
(`<job>_README.txt`) that described work the job did not do.

1. **A vertical-only job on geodetic input** (latitude and longitude in, the
   elevations converted, no State Plane zone anywhere in the job) had a job
   record that described a zone conversion. Its METHOD section carried the
   SPCS 83 Lambert projection prose, and its verification section the
   Appendix C and 27-position NCAT paragraphs; it said "Every point converted
   cleanly, inside its zone" and spoke of points "moved between zones". None
   of that ran. These records now name only the work that ran: the VERTCON,
   geoid and benchmark checks that hold the vertical conversion.
2. **A vertical-only job on geodetic input converting NAVD 88 to NGVD 29**
   (the configuration whose factors are computed from the source-datum
   height) said "The elevation and combined factors were computed from the
   SOURCE-datum height". A job with no zone has no combined factor, and the
   same record said so in its scale factor summary. It now says "The
   elevation factor was computed ...".
3. **The same vertical-only geodetic jobs** named "the geoid model the
   factors were computed from" and "H ... as used for the factors" in their
   FILES WRITTEN and METHOD sections, and "the geoid model the Z column and
   the factors are stated against" when the job changed geoid models. They
   now name the elevation factor, the one factor such a job has.

Every other existing job's files are unchanged byte for byte, apart from
two lines at the top of the job record: `Generated`, the time the job ran,
which differs on every run, and `Software`, which names this release.

## Built against NGS's beta products

As in 0.7.0 and 0.7.1: NGS's SPCS2022 zone definitions and its NCAT v3
service are pre-release, and this release is built against them
deliberately, at the owner's instruction (`docs/REFREEZE-NSRS.md`). HTDP is
not: it is NGS's released program. **When NGS changes HTDP, every
HTDP-derived number in MCX is recaptured** (`docs/REFREEZE-HTDP.md`), and the
monthly tripwire now watches NGS's HTDP repository for that change.

## Verified

- **HTDP's own output, at its printed digit.** NGS's source was compiled and
  run (gfortran, x86_64). MCX reproduces 1,846 of HTDP's printed records,
  every offered frame in both directions and the round trip at every
  calendar-equivalent epoch, to 1e-10 degree and 1 mm, compared component
  by component. A further 382 records were chosen to sit within an ulp or
  so of HTDP's rounding or at the velocity grid's edge: MCX reproduces the
  374 it transforms to the same tolerance, and refuses the other 8, which
  lie just outside the grid's edge, as it must. W0's transcription
  matched 45,408 of 45,408 records, and 720 fresh random records were matched
  when the transcription was built.
- **The transcription is checked against the Fortran itself**: the suite
  re-reads NGS's committed source and requires every transcribed constant,
  and all 480 velocity-grid nodes, to equal the number NGS wrote.
- **Independent checks.** The first interim reviewer compared 617,164 fresh
  records against its own HTDP build and found no difference at the printed
  digit. The second ran 1,500 random transformed jobs, about 6,700 points,
  through the real file path against its own HTDP build plus the projection,
  geoid and VERTCON steps, and nothing differed.
- **A self-test run inside the frozen application**, now thirteen checks: it
  converts one WGS 84 (G2296) position into Michigan Central against HTDP's
  own printed output projected, and proves the bare-WGS 84 and
  WGS 84-to-SPCS2022 refusals are alive in the shipped binary.
- **4,793 automated tests pass in both run modes** in the cloud container
  this was built in, where six tests fail for the container's own reasons
  and fail identically without this build's work (DESIGN.md #65 and #69);
  the owner's machine runs the suite again as gate 4 of the release build.
- **Nine build gates**, unchanged in number. The bundle gate also refuses a
  bundle carrying NGS's HTDP Fortran or anything from the repository's
  `review/` folder.
- **The gates ran under an independent Opus reviewer**, blind to the build's
  own reading, because the Codex reviewer the method names was not available
  in the cloud container this release was built in (the owner's standing
  fallback). Two interim gates and a closing gate ran. The first interim
  gate returned seven LOW findings; the second two HIGH, one MEDIUM and five
  LOW; the closing gate one MEDIUM and seven LOW. None was a wrong number.
  All are fixed, each pinned at the reviewer's own input, and each gate's
  fixes passed a narrowing re-confirmation. The closing gate's reviewer
  drove the real interface on both tabs, 2,050 Single point configurations
  and 540 Multi point jobs, against its own HTDP build with no mismatch. A
  Codex re-confirmation on the owner's machine is his option.

## Not verified yet: still to do before this ships

- **NGS's own Windows `htdp.exe`.** The oracle above is HTDP compiled in a
  Linux container. NGS's Windows build is 32-bit, and an x87 stand-in built
  here flips the last printed digit on some records (RECON section 4). Run
  `review/wgs84-w0/check_ngs_windows_binary.py` on the owner's machine with
  NGS's shipped `htdp.exe`; it compares every anchor input and states its
  verdict. Measured here against the x87 stand-in: at every record MCX
  converts, differences of one unit in the last printed place only (6 of
  the 1,846 ordinary anchors, 128 of the 382 records tuned to sit at a
  rounding tie).
- **The owner's screen review of both tabs**, including:
  - the separate group for the five frames in the dropdowns;
  - the observation date control, and **whether a keyboard-only first
    answer works** (F4 or Alt+Down could not be confirmed offscreen);
  - the zone-less hints: "optional" on the Single point tab, blank on the
    Multi point tab;
  - whether the vertical-only geodetic table and panel should also drop
    their N/A grid and combined factor cells, as geodetic to geodetic now
    does.
- **One real WGS 84 or PPP dataset, end to end**, against the tool it came
  from.
- **The clean-profile install proof**: install on a clean profile and run
  one real job end to end.
- **The release build**: `py tools/build_release.py --acknowledge-ngs-beta`
  on the owner's machine.

Verify the download against `SHA256SUMS.txt` on this page.
