# MCX 0.6.0

**This is a finished, verified tool, not a work in progress.** MCX does what it
was built to do: move survey coordinates between Michigan's three State Plane
zones and between State Plane and geodetic positions, convert elevations
between vertical datums and between geoid models, and document every job well
enough to defend it. It is in production use by a licensed professional
surveyor.

Future releases will be additions and corrections as the National Geodetic
Survey publishes new data — NAPGD2022 and SPCS2022 when they are final — not
further construction of the core. The mathematics, the file formats, the
verification anchors and the documentation are complete.

## New in this release: GNSS heights can go in directly

Survey data arrives from GNSS as **ellipsoid heights**. Plats and legal
descriptions need **elevations**. Until now that conversion happened outside
MCX, or — worse — an ellipsoid height went in as if it were an elevation and
nothing said otherwise.

Tell MCX what the Z column holds and it handles the rest. A new
**Heights are:** control on both tabs, offering *Orthometric (elevation)* and
*Ellipsoid (GNSS)*. It opens on Orthometric, so **nothing about an existing job
changes unless you change it.**

- In **Horizontal + Vertical** and **Vertical** mode, MCX converts the height
  with `H = h − N` and writes the elevation, tagged with its datum and the
  geoid model it came from.
- In **Horizontal** mode the Z column is written back **exactly as you supplied
  it** — an ellipsoid height stays an ellipsoid height — and the job record
  says so plainly.

### The correction that comes with it

This also fixes a real error that was easy to hit and impossible to see.

The elevation factor is `R / (R + H + N)`. Feed MCX an ellipsoid height as
though it were an elevation and the geoid separation gets added to a height
that already contains it. In Michigan the separation is about **34 metres**,
which makes every combined factor wrong by roughly **5 parts per million** —
measured at 5.9 ppm on an Upper Peninsula point. That is about **a third of a
foot in ten miles**, in the same direction every time, making grid distances
long. No warning, no odd-looking number, nothing on screen to catch it.

Declaring the height type fixes it in every mode, including Horizontal, where
the Z is untouched but the factors are now right.

### What it refuses, and why

- **No geoid model selected.** There is no separation, so there is no
  elevation to derive.
- **An input vertical datum that is not the model's.** An ellipsoid height is
  in no vertical datum at all; the elevation derived from it is in the datum
  the geoid model publishes for. Any other input datum would mislabel it before
  a single shift ran.
- **An ellipsoid input combined with a geoid change.** The input model cancels
  out of the arithmetic, so it changes no number — but the job record would
  state a conversion *from* a model the height was never on. MCX does not write
  sentences that are not true.

A point outside the bundled geoid grid gets no elevation at all in the vertical
modes, rather than an unconverted ellipsoid height sitting in a column labelled
with a datum. In Horizontal mode the Z still goes out, unconverted as always,
and the factors read N/A.

## Also in this release

- The job record gains an **ELLIPSOID HEIGHT CONVERSION** section: the model,
  its grid file, its SHA-256, the arithmetic, and the datum of the result.
- The audit CSV names the input height kind on every row, and vertical jobs
  carry the supplied ellipsoid height in its own column so the row's arithmetic
  still closes: source elevation + shift = elevation.
- In Horizontal mode the elevation column — on screen and in the audit CSV — is
  renamed **Ellipsoid height (GNSS)**, because that is what it holds. Nothing
  labelled "Elevation" ever contains an unconverted GNSS height.
- The clean PNEZD export is unchanged — **five fields, no header**, exactly as
  every CAD import expects.

## Not included, and why

**IGLD 85** was investigated at length for this release and deliberately left
out. NGS converts NAVD 88 to IGLD 85 in two steps, and both need data NGS does
not publish for download: a gravity model, and per-lake *hydraulic corrector*
grids. Queried live, NGS's own tool returns "out of bounds" at Detroit and
Sault Ste. Marie. The difference across Michigan runs about −15 cm to +2 cm and
is neither constant nor smooth, so it cannot be approximated honestly.

Worth knowing regardless: **Michigan's ordinary high water mark statute (MCL
324.32502) is written on IGLD 1955, not 1985**, and **IGLD 2020 arrives around
2027** and will move Great Lakes elevations by as much as 60 cm. The full
findings, with sources, are in the design record.

## How this release was verified

- **14 NGS published Michigan benchmarks**, from Monroe to Houghton and every
  zone, each carrying both an NAVD 88 elevation and a GEOID18 geoid height on
  its own datasheet. MCX matches NGS's published separations to **0.75 mm at
  worst**. The captures are frozen in the repository with the harness that took
  them.
- Every new test was **falsified** — the defect it claims to catch was put back
  and the test watched to fail. Nineteen of them across this feature.
- An **independent adversarial reviewer** examined the entire change and
  found three issues, all fixed before release: two places where a GNSS height
  sat under a heading that said "Elevation", and one weak test. It separately
  confirmed the conversion logic, the refusals and the factor correction were
  sound across every accepted configuration.
- **1,690 automated tests**, green in both run modes, including a
  cross-version pin: the digests of every CSV that nine ordinary jobs write,
  computed by the previous release and frozen, so a future change that moves
  any byte of an existing job's output fails a test.
- The installer is built only through a gated script: version check, clean
  tree, full test suite twice, icon, bundle, a **self-test run inside the
  frozen application** against live NGS values, installer, checksums. Any
  failure aborts the build.

Verify the download against `SHA256SUMS.txt` on this page.
