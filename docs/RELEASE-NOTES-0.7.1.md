# MCX 0.7.1

**A finished, verified tool.** MCX moves survey coordinates between Michigan's
three State Plane zones and the 19 SPCS2022 zones, between State Plane and
geodetic positions on either reference frame, converts elevations between
vertical datums and between geoid models, accepts GNSS ellipsoid heights, and
documents every job well enough to defend it. It is in production use by a
licensed professional surveyor.

This is an interface release. **No calculation changed, and no coordinate,
elevation or factor this program produces differs from 0.7.0 by any amount.**

## Drag a file onto the Multi point tab

A coordinate file dragged from Explorer and dropped anywhere on the Multi
point tab lands in the Input file box, exactly as if Browse had chosen it.
Convert arms the same way, and the path is written the way the file dialog
writes it.

The drop is accepted for exactly one thing: a single file that exists on this
machine. Anything else is refused at the border, with the no-drop cursor,
before it can land anywhere:

- **two or more files** — the program will not pick one for you;
- **a folder** — folders have their own button;
- **a path that does not exist**, or **a web address**.

Dropping onto the Input file or Output folder boxes themselves does nothing:
those boxes take a typed path or a chosen one, never a dropped one, so a drop
cannot write a stray string into either.

Nothing else on screen changed, and nothing about the way a job is converted,
written or recorded changed. The Single point tab is untouched.

## Built against NGS's beta products

As in 0.7.0: NGS's SPCS2022 zone definitions and its NCAT v3 service are
pre-release, and this release is built against them deliberately, at the
owner's instruction. Every beta-derived number carries its capture date and
the SHA-256 of the NGS file it came from (`docs/REFREEZE-NSRS.md`), and the
release build refuses to run unless that is acknowledged on the command line.

## Verified

- **3,764 automated tests**, green in both run modes, including the
  cross-version pin that digests what nine ordinary jobs write against what
  the previous release produced — so an interface release that quietly moved
  a number would fail a test. It did not.
- **Ten tests guard the drop itself.** Every one drives a real drag-enter and
  drop through Qt's own event dispatch, so what is pinned is what the tab does
  when Explorer hands it a file: the one-file rule, each refusal, the box
  filled, Convert armed, and a written result kept. Eight defects were seeded
  against them and every one was caught.
- **Nine build gates**, including a **self-test run inside the frozen
  application** against NGS's own figures.

Verify the download against `SHA256SUMS.txt` on this page.
