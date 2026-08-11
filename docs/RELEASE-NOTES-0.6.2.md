# MCX 0.6.2

**A finished, verified tool.** MCX moves survey coordinates between Michigan's
three State Plane zones and between State Plane and geodetic positions,
converts elevations between vertical datums and between geoid models, accepts
GNSS ellipsoid heights, and documents every job well enough to defend it. It is
in production use by a licensed professional surveyor.

An interface release. **No calculation changed, and no coordinate, elevation or
factor differs from 0.6.1 by any amount.**

## Single point tab

- **The elevation box now tells you what it is for.** Empty, it reads
  *optional, used for combined scale factor* in grey italic. The hint clears as
  soon as you type, and the value itself is never italic.
- **It appears in Horizontal mode only.** In Horizontal + Vertical and in
  Vertical the elevation is the value being converted, so calling it optional
  there would be false — the same mistake a tooltip made in 0.3.1, in a more
  prominent place.
- **Three rows saved.** The two vertical datums share a line, the two geoid
  selectors share the next, and the elevation sits beside the height type.
  Fourteen rows down to eleven, with every control keeping its own label.

## Multi point tab

- **The geoid selector grays out when no elevations are read.** With no
  heights there is nothing to look a geoid separation up for and every factor
  that would use it reads N/A, so the choice changes nothing. It stays live in
  the two vertical modes, where the geoid is what converts the heights.
- **The elevations note** now reads *used for combined scale factor*. The
  combined factor is the number that reaches a drawing; naming the elevation
  factor beside it named an intermediate nobody asks for.

## Verified

- **1,695 automated tests**, green in both run modes, including the
  cross-version pin that digests every CSV nine ordinary jobs write against
  what an earlier release produced — so an interface change that quietly moved
  a number would fail a test. It did not.
- Each new test was **falsified**: the change it guards was put back and the
  test watched to fail. Five of them this release.
- That process caught a defect introduced by this very round — the first
  version of the geoid graying re-enabled a selector that the datum filter had
  deliberately grayed out. An existing test caught it before it left the
  machine.
- All eight build gates, including a **self-test run inside the frozen
  application** against live NGS values.

Verify the download against `SHA256SUMS.txt` on this page.
