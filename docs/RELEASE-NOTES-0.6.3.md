# MCX 0.6.3

**A finished, verified tool.** In production use by a licensed professional
surveyor.

An interface release. **No calculation changed, and no coordinate, elevation or
factor differs from 0.6.2 by any amount.**

## Every geodetic selection now names the datum

The geodetic entry in all four zone dropdowns — From and To, on both tabs —
reads:

> **NAD83(2011) geodetic (latitude / longitude)**

### Why this is not cosmetic

**NAD 83 is not WGS 84.** In the conterminous United States they differ by a
metre or more. A dropdown reading only "Geodetic" asks no question, and the
obvious wrong answer looks right: a handheld GPS or a phone gives WGS 84, it
pastes in cleanly, and it converts to a plausible State Plane coordinate about
a metre from the truth.

MCX has always converted against NAD 83(2011), and the job record has always
said so. What it did not do was say so at the moment you choose.

The realization is named too, not just the datum, and the label is **built from
the reference frame the projection actually uses** rather than typed in. So it
cannot drift from the mathematics — and when the modernized frame arrives, the
dropdown will rename itself rather than needing to be remembered.

## Verified

- **1,696 automated tests**, green in both run modes, including the
  cross-version pin that digests every CSV nine ordinary jobs write against
  what an earlier release produced. Nothing moved.
- The new test was **falsified** two ways: with the datum dropped from the
  label, and with the label hard-coded instead of derived from the frame. Both
  fail it.
- All eight build gates, including a **self-test run inside the frozen
  application** against live NGS values.

Verify the download against `SHA256SUMS.txt` on this page.
