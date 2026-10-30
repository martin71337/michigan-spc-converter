# MCX 0.9.0

**DRAFT. Not released. The closing gate has run (seven LOW, no wrong number;
all fixed); the numbers below are re-checked against the code and DESIGN.md
#72 and #73 before the release build.**

---

**MCX now converts to and from UTM, and every coordinate system in its lists
names its EPSG code.** It moves survey coordinates between Michigan's three
State Plane zones, the 19 SPCS2022 zones and now the three UTM zones that cover
Michigan, between those grids and geodetic positions, converts elevations
between vertical datums and geoid models, accepts GNSS ellipsoid heights,
carries WGS 84 and ITRF positions through NGS's HTDP, and documents every job
well enough to defend it. It is in production use by a licensed professional
surveyor.

**Nothing about an existing job's numbers changed.** Every State Plane,
SPCS2022, geodetic and vertical job writes the same files it wrote in 0.8.0,
byte for byte, with one deliberate exception named under "Changed" below.

## UTM zones 15N, 16N and 17N

Six new entries at the bottom of every zone dropdown, on both tabs, below their
own separator:

- **NAD83(2011) / UTM zone 15N**, **16N** and **17N**, and
- **NATRF2022 / UTM zone 15N**, **16N** and **17N**.

Zone 15N covers Michigan west of 90 W (the western tip of Gogebic County), 16N
from 90 W to 84 W, and 17N east of 84 W. Each zone is on one frame, so a UTM
job works the way an SPCS 83 or SPCS2022 job does:

- **NAD83(2011) UTM** converts to and from the SPCS 83 zones and NAD83(2011)
  latitude and longitude, and takes WGS 84 and ITRF positions through HTDP.
- **NATRF2022 UTM** converts to and from the SPCS2022 zones and NATRF2022
  latitude and longitude.
- Between the two frames it refuses, as SPCS 83 to SPCS2022 does: NGS has not
  published the NAD83(2011) to NATRF2022 transformation.

**Metres only.** UTM is defined in metres, NCAT prints UTM coordinates in
metres, and EPSG defines these zones in metres. Choosing a UTM zone leaves only
metres in that side's Units box; a job asked for UTM in feet refuses and says
why.

The Options dialog has a new group, **UTM zones**, switched on by default.

The job record for a UTM job says "geodetic to UTM" or "UTM to geodetic", has
its own METHOD section citing UTM's definition (DMA Technical Manual 8358.2,
1989, with the constants as the EPSG dataset states them), and states how UTM
was verified. It cites UTM's definition for its units rather than the State
Plane manual.

### Where each zone converts, and where it refuses

MCX computes UTM with the transverse Mercator equations of NOAA Manual NOS
NGS 5, section 3.2, the same equations the SPCS2022 transverse Mercator zones
use. Close to a zone's central meridian they agree with an independent
implementation (PROJ) to a few thousandths of a millimetre. Far from it they
drift: by 19 mm forward and 177 mm in reverse at 10.7 degrees. **So MCX
converts only within 4.8 degrees of a zone's central meridian, and refuses
beyond it.** At 4.8 degrees positions agree with PROJ within 0.26 mm and the
printed scale factor within half a unit of its 8th decimal. In Michigan:

- **16N converts every point on Michigan's land**, including the east edge of
  the Lower Peninsula at Port Huron (82.41 W, 4.59 degrees from its meridian).
  It refuses only Michigan's Lake Huron waters east of 82.2 W.
- **17N refuses west of 85.8 W.** That includes the Lake Michigan shore towns:
  Muskegon, Ludington, Manistee, South Haven and St. Joseph.
- **15N refuses east of 88.2 W.**

The refusal names the point's distance from the meridian and the UTM zone that
does cover it. When a typed or filed longitude is east of Greenwich, it also
names the longitude sign convention, worded for where the longitude came from:
a file, a decimal longitude typed on the Single point tab, or a degrees,
minutes and seconds entry with an E.

### A UTM point outside Michigan warns

Every UTM zone has the same false easting, 500,000 m, so a file in one UTM zone
declared as another converts to a plausible coordinate: 16N data read as 17N
lands in Ontario. **A UTM job now warns on every point that lies in no
Michigan county** (Great Lakes waters included, from the county file the Auto
zone already ships). The job record lists those points under POINTS OUTSIDE
MICHIGAN. Each UTM zone's own extent warning covers the part of the zone over
Michigan.

## EPSG codes in the dropdowns

Every coordinate system in the zone dropdowns now names its EPSG code in
parentheses, so the same system can be set in Civil 3D, a GIS or a data
collector without translating names.

- **A State Plane zone's code follows that side's Units box, with the unit
  named**, because EPSG defines each zone once per unit:
  `Michigan South 2113 - NAD83(2011) (EPSG 6499 ift)` in international feet,
  `(EPSG 6498 m)` in metres. Michigan North is 6496 ift / 6495 m and Michigan
  Central 6494 ift / 6493 m.
- **UTM on NAD83(2011)**: `(EPSG 6344 m)`, `(EPSG 6345 m)` and
  `(EPSG 6346 m)` for 15N, 16N and 17N.
- **Latitude and longitude entries** carry the frame's geographic 2D code:
  NAD83(2011) 6318, NATRF2022 10968, WGS 84 (G1762) 9057, (G2139) 9755,
  (G2296) 10606, ITRF2014 9000, ITRF2020 9990.
- **No code is shown where EPSG has none**: any zone in US survey feet, the 19
  SPCS2022 zones, and the NATRF2022 UTM zones. A code is never guessed.
- The Single point result panel's Zone row carries the code of the unit the
  job used, and Copy all copies it. No output file carries an EPSG code.

Every code was read from the EPSG Geodetic Parameter Dataset itself, version
v12.029 of 2 October 2025, and checked for substance, not only by name: each
projected code's definition was run against MCX's own zone and agreed.

## The Auto refusal reads as one line

When Auto cannot place a point in a Michigan county, the dialog now says it in
one line: **"Coordinates out of range: 1 point is outside Michigan."** ("3
points are outside Michigan" for several). The full refusal, naming each point
and the position tested, is behind **Show Details**. A point that two county
polygons claim is not out of range, and reads "Auto could not choose a zone:
1 point lies where county boundaries overlap." Every other refusal's dialog is
unchanged.

## A refusal no longer widens the window

A long refusal used to stretch the window wider than the screen: the status
line at the bottom of each tab did not wrap, so the message's width became the
window's. The status line now shows one line, cut with "..." where the window
ends, with the full message in its tooltip and in the dialog. The window keeps
its width.

## Changed

- **A transverse Mercator point more than 4.8 degrees from its zone's central
  meridian now refuses on the SPCS2022 transverse Mercator zones too.** In
  0.8.0 such a point converted, and the error grew without bound past the
  limit: 69 mm at 12.6 degrees, 113 mm at 13.4, measured against PROJ. Two
  real mistakes converted to coordinates nowhere near the point: a longitude
  with the wrong sign (tens of thousands of kilometres off, where the
  equations no longer mean anything), and a file in international feet read
  as metres (a zone 261001 file read that way landed at 43.708 N, 72.985 W,
  in Vermont, with an easting warning and an extent warning that called the
  coordinate correct). 0.9.0 refuses all of them. No point
  inside a zone's published bounds is affected: the widest SPCS2022
  transverse Mercator zone reaches 1.29 degrees from its meridian.
- The Options error that asked for "at least one group of State Plane zones"
  now asks for "at least one group of zones", because the UTM group alone
  satisfies it.

## Verified

- **UTM against NGS NCAT, both frames.** 212 production NCAT positions in
  NAD83(2011), zones 16 and 17, and 34 beta NCAT positions in NATRF2022, zone
  16, all captured 2026-10-22, reproduced in northing, easting, convergence
  and scale factor within the precision NCAT prints, both to and from the
  grid. NCAT's own State Plane coordinate converted to UTM returns NCAT's own
  UTM coordinate for the same point, through a written file, across all six
  Michigan zone pairings and 204 positions.
- **Zone 15** has no NCAT position in Michigan. It is the same equations with
  the central meridian six degrees west of zone 16's, and the tests hold it to
  zone 16 at points the same distance from their meridians, and to PROJ.
- **PROJ as a third opinion** over Michigan's latitudes on all six zones: within
  0.26 mm of position and 4.6e-9 of scale factor everywhere MCX converts.
- **EPSG codes** read from the EPSG dataset v12.029 and checked by name, unit
  and type.
- **A self-test run inside the frozen application**, now sixteen checks: it
  converts one point in UTM zone 16N on each frame against NCAT's own figures,
  and proves the 4.8-degree refusal is alive in the shipped binary.
- **Gates**, under an independent Opus reviewer (the Codex reviewer the method
  names is not available in the cloud container this was built in; the
  owner's standing fallback). The interim gate over the UTM, EPSG and refusal
  work returned two MEDIUM and five LOW findings, none a wrong number inside a
  zone's band. Four narrowing re-confirmations followed, each closing the round
  before it. Every finding is fixed and pinned at the reviewer's own input,
  except three edge cases recorded below and one wording question left to
  the owner: whether the one-line Auto refusal dialog should also say
  "Nothing was written." **The closing gate** then returned seven LOW
  findings, every one a sentence or a missing test and none a wrong number,
  and all are fixed.

## Recorded, not fixed

Three cases at the very edge of the 4.8-degree limit refuse where they could
in principle convert. **Each is a refusal, never a wrong number**:

- A coordinate within a few billionths of a degree of the limit can refuse
  after a further round trip through another zone.
- A latitude and longitude file MCX wrote from a UTM coordinate just past the
  limit refuses when converted back into the same zone.
- Repeating a job from a UTM zone into the same zone at the limit moves the
  coordinate by up to 0.23 mm each time, and it eventually refuses.

## Not included

- **UTM beyond 4.8 degrees of a zone's central meridian**, so one UTM zone
  cannot be used across all of Michigan: 17N refuses at Muskegon, 15N east of
  88.2 W (16N is the exception and covers all of Michigan's land). The limit
  comes from the manual's equations; a different series (Krueger's) would
  remove it. It is not built.
- **EPSG codes for the SPCS2022 and NATRF2022 UTM zones**, until EPSG
  publishes them, and for zones in US survey feet, which EPSG does not define.
- **The NAD83(2011) to NATRF2022 transformation**, unchanged: NGS has not
  published it, and a job across the two frames refuses.

## Still to do, by the owner

- Before the release build: look at the UTM entries, the EPSG labels, the
  Options group and the one-line refusal on a real screen (previews in
  `review/utm-u2/`, `review/utm-u5/` and `review/refusal-r1/`).
- Run one real UTM job end to end against a known UTM coordinate.
- The clean-profile install proof (METHOD.md section 6).
