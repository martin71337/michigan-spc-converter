# MCX 0.6.1

**A finished, verified tool.** MCX moves survey coordinates between Michigan's
three State Plane zones and between State Plane and geodetic positions,
converts elevations between vertical datums and between geoid models, accepts
GNSS ellipsoid heights, and documents every job well enough to defend it. It is
in production use by a licensed professional surveyor.

This is a wording release. **No calculation changed, and no coordinate,
elevation or factor this program produces differs from 0.6.0 by any amount.**

## What changed on screen

- The height selector reads **Orthometric** and **Ellipsoid**. The
  parenthetical glosses after each — "(elevation)" and "(GNSS)" — are gone.
- In Horizontal mode, the elevation column on screen and in the audit CSV reads
  **Ellipsoid height** when the Z holds GNSS heights.

## One duplicate row removed

Taking the qualifier off surfaced something behind it.

The single-point panel has shown a computed **Ellipsoid height (m)** row since
0.1.0, alongside the geoid height and the factors. On a GNSS job that row
recomputes `h = H + N` from a conversion that had just derived `H = h − N` — so
it is **the same number you typed**, displayed a second time. The qualifier had
been distinguishing a value from itself.

On GNSS jobs that row is now gone; the height appears once, as the height you
supplied. **On an ordinary elevation job the row is unchanged and still shown**,
because there `h = H + N` is a genuinely separate figure from the Z column. The
audit CSV still carries the computed value, so nothing that was written before
is missing.

## Verified

- **1,690 automated tests**, green in both run modes, including the
  cross-version pin that digests every CSV nine ordinary jobs write against
  what the previous release produced — so a wording change that quietly moved a
  number would fail a test. It did not.
- Each new test was **falsified**: the change it guards was put back and the
  test watched to fail. That caught a weak test in this very release — the
  wording check had been comparing a value against itself and would not have
  noticed the glosses returning. It is pinned against the literal text now.
- All eight build gates, including a **self-test run inside the frozen
  application** against live NGS values.

Verify the download against `SHA256SUMS.txt` on this page.
