# MCX 0.3.1 - Martin Coordinate Exchange

**Three tooltips removed from the entry controls.** That is the whole release.

**No computation changed.** Every coordinate this version produces is
bit-for-bit what 0.1.0 through 0.3.0 produced. No output file changed - not the
PNEZD export, not the audit CSV, not the job record.

## What changed

The hover explanations are gone from:

- the **longitude sign** dropdown, on **both** tabs - it is one shared control;
- the **Decimal degrees / DMS** selector on the Single point tab;
- both **hemisphere letter** boxes (N/S, E/W) in DMS entry.

**Text was removed, not information.** The longitude control still names the
convention in words before Convert is pressed. The job record still states the
convention on its own line and in the input and export descriptions, so every
file this program writes says which reading produced it. A geodetic job with no
convention stated is still refused outright, in a sentence naming the 340 miles
at stake. The hemisphere boxes still show their letter, and the format selector
still names both formats.

## Still true, and now the surveyor's to check

The longitude sign box opens on **positive west**. Files from OPUS, NCAT, GPS
receivers and GIS software are normally **negative west**. The two conventions
are indistinguishable from the number alone, and the wrong one puts a Michigan
point about **340 miles** from where it belongs.

That warning used to be in the tooltip. It is now here, in the release notes,
and in the job record's statement of the convention actually used - **check the
dropdown against the file in front of you before every conversion.**

## Upgrading

The installer keeps the same application identity, so this upgrades an existing
install in place rather than appearing as a second entry in *Installed apps*.

## Verification

- Suite **1132 tests, green in both `pytest` and `python -O`**, exit codes read
  from the runner itself.
- All eight release gates passed, including the frozen bundle's `--selftest`:
  the bundled GEOID18 tile authenticates against its pinned SHA-256, every
  lazily imported dependency resolves inside the bundle, all six icon sizes
  load, and one end-to-end conversion matches NGS NCAT.
- The removals are pinned by two tests that assert the controls carry no
  tooltip and still say what they are, on both tabs. Falsified by seeding a
  tooltip back on each control and confirming both tests fail.
- The coordinate mathematics carries 0.1.0's verification unchanged: 666 live
  comparisons against NGS NCAT and the NGS geoid API, all passing, single-leg
  agreement 0.5 mm and chained zone-to-zone 0.9 mm.

Scope is unchanged: Michigan SPCS 83 only - no UTM, no SPCS2022, no
NAD 83 <-> NATRF2022 transformation, no NAD 27, no two-point azimuth and
distance. `docs/DESIGN.md` section 10 records why each was deferred.
