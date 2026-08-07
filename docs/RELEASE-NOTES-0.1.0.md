# Michigan SPC Zone Converter 0.1.0 — release notes

First release. These notes say **what was verified and how**, because the number
this program writes can end up on a sealed survey or in a recorded legal
description. Nothing below is a claim about how easy or how fast the program is.

---

## What it does

Converts a PNEZD coordinate file (point, northing, easting, elevation,
description — no header row) between the three Michigan State Plane Coordinate
System of 1983 zones, and between State Plane and geodetic positions in either
direction:

- **MI North 2111**, **MI Central 2112**, **MI South 2113** — all Lambert
  conformal conic, all NAD 83 (2011).
- Grid scale factor, convergence angle, elevation factor and combined factor for
  every point, with geoid separation from a bundled NGS **GEOID18** grid.
- Units: International feet (the default, because Michigan legislated it), US
  survey feet, and meters — selectable independently for input and output.
- One job produces one deliverable: a `.zip` containing the clean PNEZD export
  for CAD, a full-audit CSV, and a plain-text job record that explains the run
  to a reader who did not perform it.

The job record is the documentation. There is no separate user manual, and that
is deliberate: a manual would restate the record and then go stale, while the
record is generated from the run it describes and cannot.

---

## What this program deliberately does **not** do

Each of these is a recorded decision with a reason, not an oversight. The
reasons are in `docs/DESIGN.md` §10.

| Not supported | Why |
|---|---|
| **UTM** | Not requested; needs the transverse Mercator engine. |
| **SPCS2022 zones** | Michigan's published SPCS2022 design is 19 zones on NATRF2022 — a statewide oblique Mercator plus 18 low-distortion zones. The SPCS 83 North/Central/South zones do not carry forward. Parameters are stable for planning; NATRF2022 itself is not released. |
| **NAD 83 ⇄ NATRF2022 transformation** | No official NGS transformation product exists. A conversion whose source and target reference frames differ **refuses loudly** rather than passing coordinates through — that silent pass-through would be a 1–2 m error on a drawing that looks entirely ordinary. |
| **NAD 27, other states** | Out of scope by design. A Michigan tool is not a national one. |
| **Two-point azimuth and distance** | Not selected by the owner. Three defects the prior MATLAB tool has in this feature are recorded so the fixes travel with it if it is ever added. |

Also: elevations are treated as **NAVD 88 orthometric heights** and are passed
through unchanged (re-expressed in the output unit). There is no vertical datum
conversion — an NGVD 29 elevation is not converted to NAVD 88.

---

## Verification

### Live NGS NCAT cross-check, 2026-08-06

Thirteen fresh Michigan points — chosen to share no latitude and no longitude
with the earlier anchor lattice — were driven through the program's **real file
path** (a PNEZD file on disk → conversion → the written ZIP → the exports parsed
back out) and compared against the National Geodetic Survey's own NCAT service
and geoid API. Every pipeline, every direction, all six directed zone pairs, all
three unit systems:

**666 comparisons, 666 pass, 0 fail.**

| Quantity | Worst disagreement with NGS | Tolerance |
|---|---|---|
| Northing / easting, single leg | **0.5 mm** | 2 mm |
| Northing / easting, chained zone to zone | **0.9 mm** | 4 mm |
| Latitude / longitude out (as a distance) | **0.47 mm** | 2 mm |
| Grid scale factor | **exact** at the 8 decimal places NCAT prints, every point | 2e-8 |
| Convergence angle | **exact** at the 0.01″ NCAT prints, every point | 0.02″ |
| Geoid separation | **1 mm**, which is NGS's own print quantum | 2 mm |
| Elevation factor / combined factor | 4.4e-9 / 5.7e-9 | 2e-8 |

Half a millimetre is the resolution of what NCAT publishes, not a measurement of
error: NCAT prints coordinates to 0.001 m, so a single printed figure already
carries ±0.5 mm. The program agrees with NGS to the limit of what NGS states.

Raw JSON captures, the comparison table and the run log are in
`review/ncat-crosscheck/`.

### Independent adversarial review — three tracks, blind to each other

The closing gate ran the **Codex CLI** over the whole codebase, an **Opus
adversarial reviewer**, and the **live NCAT cross-check** above, none of them
seeing the others' work.

All three found the mathematics correct. Both reviewers re-derived the manual's
§3.1 Lambert equations from scratch at extended precision — Codex at 80 digits,
Opus at 60 digits, writing the manual's positive-west form itself — and matched
production to **1.7e-9 m** and **9.3e-10 m** respectively over the frozen
anchors.

Seventeen defects were found, **every one of them in what the program says about
itself rather than in a coordinate**: units misstated in an export, a job record
describing a latitude file as a northing, a round-trip safety gate that compared
only point identifiers, an input digest that could certify bytes that were never
converted. At this correctness tier that is not a comfort — a deliverable that
misstates its own units is a wrong number in the reader's hands — so all
seventeen were fixed at the root, each pinned as a regression test using the
reviewer's own counterexample, and each pin then **falsified** by reverting the
fix to confirm the test actually fails.

A narrowing re-confirmation pass then re-examined only the fixed surfaces and
confirmed ten of the eleven it was given as closed with faithful pins. It found
one defect that the fixes had **introduced**: the new refusal for an
out-of-range grid coordinate named the northing and the cone apex even when the
real cause was an extreme easting running off the opposite side of the
projection, and one overflow case still escaped as a bare arithmetic error
naming nothing. That is fixed, pinned and falsified in this release — the
refusal now names the field actually at fault.

One item is recorded rather than closed: the export's final rename is not
write-through, so a power loss in the window between the rename and the
filesystem's own metadata flush could leave the archive missing. The archive's
contents are flushed to disk and CRC-verified before that rename, so the failure
mode is an absent deliverable, never a corrupt one, and re-running the job
produces it again. Fixing it properly means calling the Windows move API
directly; that was judged not worth opening a freshly verified write path for
immediately before a release. It is recorded in `docs/DESIGN.md` amendment #23.


The full record is `docs/DESIGN.md` amendment #20, with the adjudication in
`review/gate2-adjudication.md` and the reviewers' raw output beside it.

An earlier interim gate, at the build's midpoint, found seven more defects; six
were fixed and one was rejected with evidence (amendments #11 and #10).

### Test suite

The suite runs in **both** modes this program can execute in — ordinary and
`python -O`, which strips `assert` statements — because production code here
contains no load-bearing asserts and that rule has to be enforced rather than
remembered. Exit codes are read from the test runner itself, never from a
pipeline.

- At the closing review gate: **855 tests, green in both modes.**
- At this release, including the release-package tests and the re-confirmation
  gate's pins: **898 tests, green in both modes.**

Every expected value in the suite is hand-derived in a comment above it — from
the equation, the published table, or an external authority — and never read
back from this program's own output.

### Frozen anchors, and where they come from

No test touches the network. Every external value was captured once, verbatim,
and committed:

| Anchor set | Source | What it proves |
|---|---|---|
| 27-point NCAT lattice across Michigan (2026-08-05) | NGS NCAT service | The forward and inverse Lambert chain against NGS's own implementation |
| 13-point cross-check, 401 frozen values (2026-08-06) | NGS NCAT service and geoid API | The whole production path, file to file |
| 20 geoid heights | NGS geoid API, model GEOID18 | The grid reader and the biquadratic interpolation |
| Appendix C published derived constants, all three zones | NOAA Manual NOS NGS 5, pp. 103–104 | The zone-constant derivation, against numbers NGS published |

Every value in the 13-point fixture was transcribed from a raw JSON capture and
then **machine-verified against that capture** — 356 fields compared, zero
mismatches. None was recomputed by this program. The one derived quantity, the
convergence angle in decimal degrees, carries NCAT's original DMS string beside
it so the conversion is checkable.

### The frozen bundle checks itself

The test suite runs against the source tree, so it can say nothing about whether
the shipped bundle is complete. The installed executable therefore verifies
itself, and the release build refuses to package a bundle that fails:

```
michspc-spc-converter.exe --selftest
```

It confirms that the bundled GEOID18 tile is present and authenticates against
its pinned SHA-256 and its canonical geometry; that it returns a geoid height
NGS agrees with; that every lazily imported dependency resolves inside the
bundle; that Qt starts and the bundled icon loads; and that one real
Michigan South → Michigan Central conversion, driven all the way to a written
ZIP and parsed back out, lands on the coordinate **NCAT computed** for that
position.

---

## The bundled geoid model

`GEOID18`, NGS CONUS grid #3 (`g2018u3.bin`) — 40–58 °N by 96–77 °W at one
arcminute, 1081 × 1141 cells — committed and shipped **unmodified** from NGS,
4,933,728 bytes:

```
SHA-256  cd2080f904d168e3356effffc535d5d0c9cd8c2a0019ddb4f40a0e2454ebe3b3
```

Source: `https://geodesy.noaa.gov/PC_PROD/GEOID18/Format_pc/g2018u3.bin`,
downloaded 2026-08-05. The digest is checked by the program every time it loads
the grid, and again by the frozen bundle's self-test, so a corrupted or
substituted grid is refused rather than quietly producing plausible wrong
separations. After installation the file can be checked by hand at
`_internal\data\g2018u3.bin` inside the installation folder.

Interpolation is biquadratic (3×3 Lagrange), which is what NGS's own INTG
program uses; it was chosen by measurement against 20 frozen NGS values, where
it sits at the 0.5 mm quantization floor and bilinear does not.

---

## Installation

Run `michspc-spc-converter-0.1.0-setup.exe`. It installs per-user by default and
offers an administrative install; it creates a Start Menu entry and an
uninstaller, and optionally a desktop shortcut. Windows 10 or 11, 64-bit. No
Python installation is required — the interpreter, Qt and the geoid grid are all
inside the bundle.

**Verify the download before installing.** The SHA-256 of every published
artifact is in `SHA256SUMS.txt` beside it in this release. In PowerShell:

```powershell
Get-FileHash .\michspc-spc-converter-0.1.0-setup.exe -Algorithm SHA256
```

---

## Known limitations, stated plainly

- **There is no independent recomputation at conversion time.** An earlier
  design ran a second engine (the manual's §3.4 polynomial method) on every
  point. It was removed, deliberately, because it carries NGS's own 0.5 mm
  fitting error, degrades to *metres* outside each zone's fitted band, and
  needed a special-case policy of its own to stay quiet — a code path that needs
  a policy to stay quiet is a second thing to verify, not a check. What carries
  the verification now is external: the frozen NGS NCAT anchors and the
  published Appendix C constants. A regression in the rigorous engine would be
  caught by the test suite and the release gates, not by the running program.
  (`docs/DESIGN.md` amendment #14.)
- **This program has not yet been run against a PNEZD file exported by the
  owner's own CAD package.** The reader is built to a documented convention and
  is exercised against files this project wrote. The first real job file is
  worth checking carefully.
- **Windows only.** The no-clobber export commit relies on Windows `os.rename`
  refusing an existing target; POSIX replaces silently. A port would need an
  equivalent.
- Points outside the shipped GEOID18 tile convert horizontally and report `N/A`
  for the elevation and combined factors, naming the point. Points with no
  elevation do the same. Neither ever gets a fabricated `1.0`.

---

## Primary reference

NOAA Manual NOS NGS 5, *State Plane Coordinate System of 1983*, James E. Stem,
January 1989, reprinted with minor corrections March 1990 — committed in this
repository at `docs/NOAA_Manual_NOS_NGS_0005.pdf`. Every projection equation,
zone constant and factor definition traces to it by page. The rigorous §3.1
Lambert conformal conic equations are the only computation path.
