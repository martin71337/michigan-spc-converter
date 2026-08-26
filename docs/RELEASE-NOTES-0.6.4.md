# MCX 0.6.4

**A finished, verified tool.** MCX moves survey coordinates between Michigan's
three State Plane zones and between State Plane and geodetic positions,
converts elevations between vertical datums and between geoid models, accepts
GNSS ellipsoid heights, and documents every job well enough to defend it. It is
in production use by a licensed professional surveyor.

This is an artwork release. **No calculation changed, and no coordinate,
elevation or factor this program produces differs from 0.6.3 by any amount.**

## A new application icon

The compass rose is gone. It had been the icon since 0.1.0, and it said
*direction* — which is not what this program does.

In its place: a survey monument, drawn as a ring with a crosshair through it
and an amber centre, with two arrows turning around it on a faint grid. A point
being converted, rather than a bearing being taken.

It was chosen from three candidates, each compared at the four sizes Windows
actually asks for — 16, 32, 48 and 128 px — using the same reducer the build
itself uses, so the comparison was of the icon Explorer receives rather than of
a preview. This one holds together the furthest down: at 16 px the ring and its
centre still read.

Nothing else on screen changed, and nothing about the way a job is converted,
written or recorded changed.

## Where you will see it

The window, the taskbar, the Start menu and desktop shortcuts, the entry in
Installed apps, and the executable itself in Explorer.

**Windows caches icons.** If the old compass persists on a shortcut after
upgrading, that is the shell's icon cache rather than the installer; signing
out and back in clears it.

## Verified

- **1,696 automated tests**, green in both run modes, including the
  cross-version pin that digests every CSV nine ordinary jobs write against
  what the previous release produced — so an artwork release that quietly moved
  a number would fail a test. It did not.
- The **25 tests that guard the icon** pass unchanged. They are the ones that
  matter here: the master artwork is read back through the build's own strict
  decoder and must be 1024×1024 8-bit RGBA, its corners fully transparent, its
  centre opaque, and its edge genuinely anti-aliased rather than a hard cutout.
  That last check exists because the 0.1.0 artwork failed it — the transparency
  was a checkerboard painted into the image — and it was run against this
  artwork before the icon was accepted, not after.
- All eight build gates, including a **self-test run inside the frozen
  application** against live NGS values.

Verify the download against `SHA256SUMS.txt` on this page.
