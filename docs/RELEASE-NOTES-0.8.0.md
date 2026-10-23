# MCX 0.8.0 (DRAFT)

**DRAFT. Not released.** The version literal still carries its `-dev` marker
(`0.8.0-dev`), nothing is tagged, and the owner has not seen the new
controls on a real screen. The release has two parts. The WGS 84 and ITRF
part has had its closing review gate, and its findings are fixed (below,
under Verified). The Options, Auto zone and observation date part has had
its interim gate, and its findings are fixed; **its closing gate has not run
yet.** The release build is made on the owner's machine. This file is
written so that what the release claims can be checked against what was
actually verified.

---

**MCX now converts WGS 84 and ITRF positions, and can pick the State Plane
zone for you.** It moves survey coordinates between Michigan's three State
Plane zones and the 19 SPCS2022 zones, between State Plane and geodetic
positions, converts elevations between vertical datums and between geoid
models, accepts GNSS ellipsoid heights, and documents every job well enough
to defend it. It is in production use by a licensed professional surveyor.

This release adds **five global reference frames**, carried to and from
NAD 83(2011) by NGS's own HTDP; an **Options menu**; an **Auto zone** entry
that chooses each point's zone from its county; and moves the **observation
date** into Options. **Nothing about an existing job's numbers changed**:
every coordinate, elevation and factor an SPCS 83, SPCS2022 or vertical job
produces is what 0.7.1 produced, and a job with a fixed zone writes the same
files it wrote before the Auto zone work.

## WGS 84 and ITRF, to and from NAD 83(2011)

Five frames, each a separate entry in every system dropdown, grouped below
the two NAD 83 and NATRF2022 geodetic entries:

- **WGS 84 (G1762)**, **WGS 84 (G2139)** and **WGS 84 (G2296)**: the three
  realizations in force since 16 October 2013;
- **ITRF2014** and **ITRF2020** by name, for precise point positioning
  results (CSRS-PPP, OPUS's ITRF output), so a PPP report's frame is selected
  as it is printed rather than translated into a G-number.

The five are **switched off in the dropdowns by default** (see Options
below): turn them on in Options to use them.

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

## The Options menu

A new **Options...** menu opens one dialog with three parts. The choices
apply to both tabs at once.

- **Show in the system lists.** One check box per group of entries in every
  FROM and TO dropdown: SPCS 83 zones, SPCS2022 zones, NAD83(2011)
  latitude/longitude, NATRF2022 latitude/longitude, and each of the five
  WGS 84 and ITRF frames. All are on by default except the five WGS 84 and
  ITRF frames, which are off. At least one group of zones and one group of
  latitude/longitude must stay on; the dialog will not accept a choice that
  leaves a dropdown with nothing to pick.
- **Auto zone frame**: NAD83(2011) (SPCS 83 zones, the default) or
  NATRF2022 (SPCS2022 local zones). See Auto zone below.
- **Observation date**: "Today (the date the job runs)", the default, or
  "Enter a date on the tab". See below.

If a change in Options hides an entry that is selected on a tab, that
selection is cleared and the status line says so. Any change in Options
clears a result shown on the Single point tab, so a result on screen always
matches the choices in force.

**What is remembered, and where.** MCX remembers three things between runs:
which groups are shown, the Auto zone frame, and which observation date
choice is in force. They are stored per Windows user, in the registry at
`HKCU\Software\DMARTIN\MCX - Martin Coordinate Exchange`. **No date is ever
stored**, and nothing else is: zones, units, files and folders are chosen
for each job. If a stored value is one MCX does not recognise, that setting
goes back to its default and the status line says so.

## Auto zone

**Auto** is a new entry at the top of the State Plane zone section of the TO
dropdown on both tabs. It chooses the zone **for each point**, from the
point's latitude and longitude, **by the county the point is in**, which is
how the law defines the zones.

- It is offered only as the TO system, and only when the FROM system is a
  latitude/longitude. A northing and easting do not say which zone they are
  in, because the zones overlap in grid coordinates.
- **On NAD83(2011)** it chooses among the three SPCS 83 zones. Each zone's
  counties are the ones MCL 54.231 names: subsection (3) the north zone, (4)
  the central zone, (5) the south zone.
- **On NATRF2022** it chooses among the **18 SPCS2022 low-distortion zones**,
  never the statewide zone 260001. NGS publishes no county list for these
  zones, so MCX measured one from NGS's beta zone polygons: each zone is a
  union of whole counties. The one exception is Keweenaw County, which is two
  zones. **The Isle Royale rule:** a Keweenaw County position at or north of
  47.65 degrees N is placed in Michigan Isle Royale (261018, MI_U61K); south
  of it, in Michigan Houghton (261016, MI_U41H). NGS publishes no text stating
  this rule; NGS's zone bounds give the two zones a shared bound at 47.65 N,
  and NGS's beta NCAT switches between them there to within about 100 m.
- **County lines are the US Census TIGER/Line 2025 counties**, all 83 of
  Michigan's, unsimplified, with their lines extended into the Great Lakes,
  so a point on the water is in a county just as a point on land is. This is
  the county data NGS built SPCS2022 from. MCX ships it as
  `mi_counties_tiger2025.json` and checks its SHA-256 every time it is read.
- **A point exactly on a county line** is placed in the county east of it,
  or, where the line runs exactly east-west, in the county north of it.
- **A point near a zone line** is placed by its county like every other
  point, with no warning.
- **WGS 84 and ITRF input works with Auto on NAD83(2011).** The zone is
  chosen from the point's NAD 83(2011) position after the HTDP
  transformation.
- **Each point's coordinates are exactly what a job with that zone fixed
  would produce**, to the last digit. Auto chooses a zone and changes nothing
  else.

**What an Auto job writes.** The archive is named `<input>_AUTO-SPCS83.zip`
or `<input>_AUTO-SPCS2022.zip`. It holds **one CAD (clean PNEZD) file per
zone the job used**, named `<input>_AUTO-SPCS83_<zone>.csv`, for example
`pts_AUTO-SPCS83_MI-C.csv` or `pts_AUTO-SPCS2022_MI_L45G.csv`, holding that
zone's points in file order. A zone no point fell in gets no file. Each file
is checked on its own points before the archive is kept. The audit CSV names
each point's zone, county and county FIPS code. The job record lists each
zone used with its point count and file, the county rule and where it comes
from, the county data and its SHA-256, the on-line rule, and, for SPCS 83,
MCL 54.234. On screen, the Single point result and the Multi point table show
each point's zone and county.

**What Auto refuses.** None of these ever passes coordinates through
unchanged.

- **A point in no Michigan county**, outside the state or in Canadian water,
  or a point two county polygons both claim: the **whole job** is refused,
  and the message names every such point with the position tested. A point
  is never given the nearest zone.
- **An Auto frame the input cannot reach**: NAD83(2011) or WGS 84 or ITRF
  input with Auto on NATRF2022, and NATRF2022 input with Auto on
  NAD83(2011). There is no published NAD 83 to NATRF2022 transformation
  (`docs/DEFERRED-NATRF2022-BRIDGE.md`). The Auto entry is grayed for such a
  pair, cleared with the same status line as any other frame mismatch, and a
  job that states one is refused by name.
- **A unit one of the possible zones does not define.** Auto offers only the
  units every zone it can choose publishes, so Auto on NATRF2022 offers no US
  survey foot, which NGS publishes for no SPCS2022 zone.

## The observation date

A WGS 84 or ITRF position means nothing until the date it was observed is
stated: Michigan moves about 17 mm a year in those frames against NAD 83. So
every job on one of the five frames carries an **observation date**, a
calendar date. **Where it comes from is now an Options choice:**

- **Today (the default).** The job uses **the local calendar date on the
  computer running MCX, read when Convert is clicked**, and no date box is
  shown on the tabs. **This reverses the earlier rule that the observation
  date has no default, at the owner's instruction**, for this choice only.
- **Enter a date on the tab.** The date box appears on both tabs. It opens
  unanswered every time MCX starts, because a typed date is never
  remembered, and Convert stays unavailable until it is answered. The box is
  enabled only when one of the five frames is selected.

Either way:

- the job record states the date and where it came from: "the date the job
  ran (Options default)" or "entered by the user";
- an entered date must be a real date (there is no 30 February) and not
  after the day the job runs;
- it is converted to a decimal year exactly the way HTDP converts a calendar
  date, and the job record states both;
- one date covers the whole job: a PNEZD file has no column for it, so every
  point in the file is taken as observed on that date, and the record says
  so;
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
does (Auto zone's own refusals are listed under Auto zone above):

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
- **A WGS 84 or ITRF job with no observation date, or a future one.** Under
  "Enter a date on the tab", Convert stays unavailable until a date is
  entered, and a future date is refused at Convert.
- **An observation date on a job with no WGS 84 or ITRF frame**, where it
  would answer a question the job never asks. No date is sent for such a
  job, and the date box is grayed; a job that states one anyway is refused
  by name.

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
deliberately, at the owner's instruction (`docs/REFREEZE-NSRS.md`). Auto
zone on NATRF2022 adds two more beta-derived artifacts: the county to
SPCS2022 zone table, measured from NGS's beta zone polygons, and the beta
NCAT zone picks it is tested against. The release build acknowledges
**seven** beta-derived artifacts, where 0.7.0 and 0.7.1 acknowledged five.
HTDP is not beta: it is NGS's released program. **When NGS changes HTDP,
every HTDP-derived number in MCX is recaptured** (`docs/REFREEZE-HTDP.md`),
and the monthly tripwire now watches NGS's HTDP repository for that change.

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
- **NGS's own Windows `htdp.exe`**, the binary at the pinned commit with its
  git blob verified, was run on the owner's machine over every anchor input
  (`review/wgs84-w0/ngs-windows-check-2026-10-22.txt`). Verdict: **last digit
  only.** 2,093 of 2,228 records are identical. 6 of the 1,846 ordinary
  anchors and 128 of the records tuned to sit at a rounding tie differ by
  one unit in the last printed place, exactly as predicted from a 32-bit
  stand-in built beforehand. The one other record is one MCX refuses, just
  outside its velocity grid, so it is listed and does not decide anything.
- **The transcription is checked against the Fortran itself**: the suite
  re-reads NGS's committed source and requires every transcribed constant,
  and all 480 velocity-grid nodes, to equal the number NGS wrote.
- **Independent checks.** The first interim reviewer compared 617,164 fresh
  records against its own HTDP build and found no difference at the printed
  digit. The second ran 1,500 random transformed jobs, about 6,700 points,
  through the real file path against its own HTDP build plus the projection,
  geoid and VERTCON steps, and nothing differed.
- **Auto zone against NGS NCAT.** 247 frozen NCAT zone picks, every one
  outside the bands near a zone line where NCAT disagrees with itself: 124
  from production NCAT for SPCS 83 and 123 from beta NCAT for SPCS2022, on
  land, on the Great Lakes, and outside Michigan. Auto agrees with every
  one, and refuses every point NCAT puts outside Michigan. The SPCS 83
  county table was checked against MCL 54.231 as captured, and the SPCS2022
  table re-derived from NGS's native polygon capture, whose lines lie on
  TIGER's county lines to 0.025 m at worst over 11,875 shared edges. The
  on-line rule was proven on all 30,871 shared TIGER county edges. 223
  fixed-zone job configurations, 667 files, were compared byte for byte
  against the build before the Auto zone output work: all identical.
- **A self-test run inside the frozen application**, now fourteen checks: it
  converts one WGS 84 (G2296) position into Michigan Central against HTDP's
  own printed output projected, proves the bare-WGS 84 and
  WGS 84-to-SPCS2022 refusals are alive in the shipped binary, and runs an
  Auto zone job on the shipped county file: two points land in the zones
  NGS NCAT chose for them (Michigan South for Kent County, Michigan North for
  Marquette County), at exactly the fixed-zone coordinates and within 0.3 mm
  of NCAT's printed coordinates (the check allows 2 mm), and a point in
  Toledo, Ohio refuses the whole job.
- **The automated tests on the owner's Windows 11 machine.** The WGS 84 part
  was built in a cloud container, where 4,793 tests passed in both run
  modes. On the owner's machine 30 tests then failed, none for a program
  defect: Windows paths and a Windows line ending in two tests that compare
  job records to frozen digests; three NGS HTDP captures rewritten with
  Windows line endings by git; 19 HTDP records (18 of the records tuned to
  sit at a rounding tie, and one at the velocity grid's edge) that MCX
  prints one unit differently on Windows, because Windows' C library
  computes trigonometry differently from Linux's in the last bit; and one
  list in a test whose order depends on the platform. All were fixed in the
  tests, the 19 records by an exception limited to exactly those records
  (4,968 passing in both modes). With
  the Options and Auto zone work, **5,754 tests pass in both run modes** on
  the owner's machine; the release build runs them again as gate 4.
- **Nine build gates**, unchanged in number. The bundle gate also refuses a
  bundle carrying NGS's HTDP Fortran or anything from the repository's
  `review/` folder, and requires every file in `data/`, now including the
  county file, to be in the bundle.
- **The WGS 84 part's gates ran under an independent Opus reviewer**, blind
  to the build's own reading, because the Codex reviewer the method names
  was not available in the cloud container it was built in (the owner's
  standing fallback). Two interim gates and a closing gate ran. The first
  interim gate returned seven LOW findings; the second two HIGH, one MEDIUM
  and five LOW; the closing gate one MEDIUM and seven LOW. None was a wrong
  number. All are fixed, each pinned at the reviewer's own input, and each
  gate's fixes passed a narrowing re-confirmation. The closing gate's
  reviewer drove the real interface on both tabs, 2,050 Single point
  configurations and 540 Multi point jobs, against its own HTDP build with
  no mismatch.
- **The Options and Auto zone part's interim gate ran under Codex** over the
  county data, the zone lookup and Auto in the conversion
  (`review/gate-autozone-1/`). It found no wrong zone and returned one HIGH
  and one MEDIUM. The HIGH: two public routines that turn a result into file
  text could still produce an Auto job's CAD file, with points from
  different zones in one unlabelled file, getting around the guard that held
  Auto jobs back until their job record existed. The guard was replaced by
  the real Auto output, and the CAD file routine now requires each point's
  zone on an Auto job and refuses a zone the job did not use, so points from
  two zones cannot reach one file. The MEDIUM: the SPCS2022 table's test read a
  copy of NGS's polygons that NGS's server had shifted about 0.9 m, while the
  agreement it cited was measured on the unshifted capture; the test now
  reads the unshifted capture. Both are fixed and pinned at the reviewer's
  own inputs.

## Not verified yet: still to do before this ships

- **The closing review gate over the Options and Auto zone work**, and a
  narrowing re-confirmation of its fixes.
- **The owner's screen review of both tabs and the Options dialog**,
  including:
  - the Options dialog itself, and the Auto entry at the top of the zone
    section of the TO dropdown;
  - the zone and county shown for each point on both tabs;
  - the separate group for the five frames in the dropdowns;
  - the observation date box under "Enter a date on the tab", and **whether
    a keyboard-only first answer works** (F4 or Alt+Down could not be
    confirmed offscreen);
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
