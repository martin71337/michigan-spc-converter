# MCX 0.2.0 - Martin Coordinate Exchange

**The program is renamed.** What shipped as the "Michigan SPC Zone Converter"
is now **MCX**, for *Martin Coordinate Exchange*.

**No computation changed.** Every coordinate this version produces is
bit-for-bit what 0.1.0 and 0.1.1 produced. The full suite is green in both
modes and the frozen bundle passes its own self-test, including an end-to-end
conversion checked against NGS NCAT.

## What changed

**The name.** The window title, the Start Menu and desktop shortcuts, the
installer, the job record's header and the executable itself are now MCX. The
executable is `mcx.exe`; it was `michspc-spc-converter.exe`.

**The publisher.** Windows' *Installed apps* and the file's own properties now
show **DMARTIN**. They previously showed "Lapham Associates", which was wrong.

**The icon carries no lettering at any size.** "COORD CONVERT" is gone from the
artwork. It could not simply be cropped away: the down arrow's tip sits *below*
the lettering, so any crop that removed the words also amputated the arrow. The
lettering and its embossed shadow were painted out instead and the badge behind
them reconstructed, which keeps all four arrows and both arcs intact. At 16 and
32 px - the sizes Windows actually draws on the taskbar - the compass is now the
whole icon rather than competing with text that was never legible at that size.

## Upgrading

The installer keeps the same application identity, so this upgrades an existing
install in place rather than appearing as a second entry in *Installed apps*.
The old executable and the old Start Menu and desktop shortcuts are removed
during the upgrade.

If the icon still looks like the old one after upgrading, that is Windows'
icon cache rather than the installed file - it caches by path and does not
always notice that the file changed.

## Verification

- Suite **898 tests, green in both `pytest` and `python -O`**, exit codes read
  from the runner itself.
- All eight release gates passed, including the frozen bundle's `--selftest`:
  the bundled GEOID18 tile authenticates against its pinned SHA-256, every
  lazily imported dependency resolves inside the bundle, all six icon sizes
  load, and one end-to-end conversion matches NGS NCAT.
- The coordinate mathematics carries 0.1.0's verification unchanged: 666 live
  comparisons against NGS NCAT and the NGS geoid API, all passing, single-leg
  agreement 0.5 mm and chained zone-to-zone 0.9 mm.

Scope is unchanged: Michigan SPCS 83 only - no UTM, no SPCS2022, no
NAD 83 <-> NATRF2022 transformation, no NAD 27, no two-point azimuth and
distance. `docs/DESIGN.md` section 10 records why each was deferred.
