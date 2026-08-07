# MCX 0.3.0 - Martin Coordinate Exchange

**One typed coordinate, converted, without a file.** That is the whole of this
release: a second tab beside the file tool, and the interface work that came out
of looking at it.

**No computation changed.** Every coordinate this version produces is
bit-for-bit what 0.1.0, 0.1.1 and 0.2.0 produced. Nothing in the conversion
core, and no formatter that writes a file, was touched.

## Read this before the first conversion

**The longitude sign box now opens on *positive west*.** That is the
convention in use here, which is why it was asked for. It is the wrong one for
almost anything downloaded: **OPUS, NCAT, GPS receivers and GIS exports all
write negative west.** The two conventions are indistinguishable from the
number alone, and choosing the wrong one puts a Michigan point about **340 miles**
from where it belongs. The box says which it is before Convert is pressed, and
its tooltip carries the warning; nothing blocks it. Check it against the file
in front of you, every time.

## The Single point tab

Type a coordinate, press Convert, read the answer. No input file, no output
folder, nothing written to disk.

- Input is **either** northing / easting / elevation **or** latitude / longitude.
- **Elevation is optional.** Without one, the factors that need it read `N/A`
  rather than a fabricated `1.0` - the same rule the file tool has always kept.
- **Latitude and longitude can be typed as decimal degrees or as degrees,
  minutes and seconds** - four boxes per angle, with a hemisphere letter (N/S,
  E/W) instead of a sign. The hemisphere opens on **N** and **W**, correct for
  every point inside the three Michigan zones.
- The result reads in **two columns: INPUT on the left, OUTPUT on the right.**
- **A copy button beside every value**, plus *Copy all* for the whole panel.
- Warnings appear in their own full-width field beneath the result, where a
  paragraph has room to be read.

**The two tabs cannot disagree about the same point.** They are not two
implementations of a conversion that happen to match - they pass through the
same validation gate and call the same conversion function. One reviewer drove
both real interfaces over 378 configurations and compared the panel against the
audit CSV the file tab wrote, section by section.

**DMS is for the tab, not for a file.** The input CSV takes decimal degrees
only, and now says so by name when it meets a DMS value instead of failing
obscurely. Reading DMS from a file is deliberately not built: packed `434759.8`
cannot be told apart from an ordinary decimal degree without guessing, and this
program does not guess about a coordinate.

## Elsewhere in the interface

- Latitude and longitude on screen now carry a degree symbol, and the
  convergence angle reads `-16°49'17.78"`. **On screen only** - the exported
  PNEZD file is unchanged, because it is read back before an archive may be
  written and a symbol in it would refuse every geodetic job.
- The copy control is the Windows 11 two-sheet glyph, sitting beside its own
  value rather than pinned to the far right of the panel.
- The input file box and the output folder both start **empty**. They previously
  offered an example path and a default folder.

## Upgrading

The installer keeps the same application identity, so this upgrades an existing
install in place rather than appearing as a second entry in *Installed apps*.

## Verification

- Suite **1131 tests, green in both `pytest` and `python -O`**, exit codes read
  from the runner itself.
- All eight release gates passed, including the frozen bundle's `--selftest`:
  the bundled GEOID18 tile authenticates against its pinned SHA-256, every
  lazily imported dependency resolves inside the bundle, all six icon sizes
  load, and one end-to-end conversion matches NGS NCAT.
- The Single point tab was gated by two reviewers working blind to each other.
  The closing gate found a stale result that survived a control change with
  both copy paths armed - a reading 100,001 ft out, one click from the
  clipboard. Fixed and pinned before this release; `docs/DESIGN.md` #26.
- The coordinate mathematics carries 0.1.0's verification unchanged: 666 live
  comparisons against NGS NCAT and the NGS geoid API, all passing, single-leg
  agreement 0.5 mm and chained zone-to-zone 0.9 mm.

Scope is unchanged: Michigan SPCS 83 only - no UTM, no SPCS2022, no
NAD 83 <-> NATRF2022 transformation, no NAD 27, no two-point azimuth and
distance. `docs/DESIGN.md` section 10 records why each was deferred.
