# Michigan SPC Zone Converter 0.1.1

An icon-only release. **No computation, file-format or interface behaviour
changed** — every coordinate this version produces is bit-for-bit what 0.1.0
produced, and the full suite is green in both modes.

If 0.1.0 is installed and the icon looks right to you, there is no reason to
update.

## What changed

**The application icon now has a real transparent background, and the artwork
fills the frame.**

The committed master artwork had a checkerboard *painted into it* — the grey and
white squares an image editor draws behind a picture to **indicate**
transparency, mistaken at some point for the transparency itself. Every one of
the master's 1,048,576 pixels was fully opaque, so the icon Windows displayed
carried grey squares behind the badge wherever a surface respects alpha, instead
of letting the background through.

Two things were done to it:

- **The background is transparent.** The badge is cut out on a real alpha
  channel, anti-aliased along its rounded edge, so the icon sits cleanly on any
  background. The drop shadow that was painted onto the checkerboard is gone with
  it — it was part of the fake background, not part of the badge.
- **The badge is enlarged.** It occupied about 67% of the canvas and now fills
  it. At the small sizes Windows actually draws — 16 and 32 px on the taskbar —
  the compass is correspondingly larger and easier to read.

The `.ico` is still derived from that one master by `tools/make_icon.py` as a
build step, at all six Windows sizes, so there remains exactly one authoritative
copy of the artwork.

## Why it was not caught before

Three separate parts of the build asserted this property and none of them
verified it: the icon tool's own documentation stated "the artwork has a
transparent background", its resampler premultiplies and divides out alpha for
the sole purpose of keeping a transparent edge clean, and every icon entry is
written as a 32-bit BGRA image whose alpha channel is supposed to carry the
transparency. All three were correct code operating on artwork that had none.

A regression test now reads the committed master and asserts that its corners
are fully transparent, that the badge is opaque, and that the edge is
anti-aliased rather than a hard cutout. It was falsified against the old
artwork, which fails it.

## Known, unchanged

At 16 and 32 px the "COORD CONVERT" lettering across the bottom of the badge is
below the size at which text resolves, and enlarging the badge does not fix
that. The usual remedy is a cropped, text-free compass variant carried inside
the same `.ico` for the small sizes. That is an artwork decision and has not been
made.

## Verification

- Suite **898 tests, green in both `pytest` and `python -O`**, exit codes read
  from the runner itself.
- All eight release gates passed, including the frozen bundle's own
  `--selftest`, which checks the bundled GEOID18 tile against its pinned
  SHA-256, resolves every lazily imported dependency, reads all six icon sizes
  out of the bundle, and runs one end-to-end conversion checked against NGS
  NCAT rather than against the program's own output.
- The coordinate mathematics is unchanged from 0.1.0 and carries that release's
  verification: 666 live comparisons against NGS NCAT and the NGS geoid API,
  all passing, with single-leg agreement of 0.5 mm and chained zone-to-zone
  agreement of 0.9 mm.

Scope limits are unchanged and are listed in the 0.1.0 notes: Michigan SPCS 83
only — no UTM, no SPCS2022, no NAD 83 ↔ NATRF2022 transformation, no NAD 27, no
two-point azimuth and distance. `docs/DESIGN.md` §10 records why each was
deferred.
