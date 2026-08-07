# CLAUDE.md — MCX (Martin Coordinate Exchange)

A Windows desktop tool that converts survey coordinate files between the three
Michigan State Plane Coordinate System of 1983 zones, and between State Plane
and geodetic positions. It is used by a licensed professional surveyor to move
job coordinates across zone boundaries. **A wrong coordinate here lands on a
sealed survey or a recorded legal description and moves a boundary.** That
sentence calibrates everything below.

**Read `docs/DESIGN.md` before any engineering change.** It is the design source
of truth; this file is the working summary. The standing method is
`docs/method/METHOD.md` — defaults, not law; record deviations in the DESIGN.md
amendment log.

## What it is

Reads a PNEZD coordinate file (point, northing, easting, elevation,
description — no header row), converts it from one Michigan zone to another, and
writes three files: a clean PNEZD export for CAD, a full-audit CSV, and a
plain-text job record. Also converts geodetic ⇄ State Plane in either direction.
Reports grid scale factor, convergence angle, elevation factor and combined
factor per point, with geoid separation from a bundled GEOID18 grid.

It deliberately does **not** do UTM, SPCS2022, NAD 83 ↔ NATRF2022
transformation, other states, NAD 27, or two-point azimuth/distance. See
DESIGN.md §10 for why each was deferred.

## Status (2026-08-07, 0.2.0 RELEASED)

**Closing adversarial gate is done and every finding is fixed.** Three
independent tracks ran blind to each other — Codex CLI, an Opus reviewer, and a
**live NGS NCAT cross-check** of every pipeline through the real file path. The
mathematics was confirmed correct by all three: 666 live comparisons, all pass,
single-leg agreement 0.5 mm, chained zone-to-zone 0.9 mm, scale factor and
convergence exact to NCAT's printed precision. Both reviewers re-derived §3.1
from the manual independently (80 and 60 digits) and matched to ~1e-9 m.

Seventeen defects were found, **all in the contract/record/safety-gate layer,
none in a coordinate**, and all are now fixed, pinned with the reviewer's own
counterexample, and each pin falsified. Two interim-gate fixes recorded in #11
as landed had not landed (the `constants=` seam, the longitude-convention
default) and two interim pins had never been written at all. Full account:
DESIGN.md amendment **#20**.

**Suite: 546 → 855**, green in both `pytest` and `-O`, exit codes asserted
directly, run unpiped. The 13 live cross-check points are frozen as fixtures and
now drive **file → job.run → ZIP → parsed audit CSV** for all three directions
in all three units — the end-to-end path that had no anchors before, and whose
absence is why the record defects survived.

**Extensibility: REWORK-REQUIRED, recorded not built** (amendment #21). §6's
claim that SPCS2022 arrives as data did not survive review. Michigan's published
SPCS2022 design is 19 zones on NATRF2022 (statewide oblique Mercator + 18 LDPs,
13 LC1 and 5 TM) — *not* the three Lambert zones §6 assumed. Zone parameters are
published and stable; NATRF2022 and its transformation are not released, so the
frame refusal stays and the zone layer is deliberately not built yet.

**Vertical datums sized, recorded not built** (amendment #22): NGVD 29 → NAVD 88
is MEDIUM, two work packages, everything needed available today; NAPGD2022 is
blocked but seam-able via a transformation registry.

**0.2.0 IS RELEASED — the program is now MCX, Martin Coordinate Exchange.**
Renamed throughout (window title, shortcuts, installer, job record, executable
`mcx.exe`); publisher corrected to **DMARTIN** in Installed apps and the version
resource; the "COORD CONVERT" lettering removed from the artwork at every size.
The Python package stays `michspc` on purpose. The AppId is unchanged so this
upgrades in place, with an `[InstallDelete]` clearing the old name's leftovers.
No computation changed. DESIGN.md **#25**.

**0.1.1** fixed the icon's fake transparency: the master had a checkerboard
*painted into it* — all 1,048,576 pixels opaque — so the transparent background
three parts of the build assumed never existed (DESIGN.md **#24**).

**0.1.0** remains the release the verification record describes. Suite 898,
green in both modes; all eight build gates pass for each release.

The narrowing re-confirmation closed 10 of 11 findings, found one defect the
fixes had introduced (fixed and pinned, amendment #23), and one item is accepted
weak with reasons recorded: the final rename is not write-through, so the
failure mode is an absent archive, never a corrupt one.

### Open for the owner

1. **The install proof is human and still outstanding** (METHOD.md §6): install
   on a clean profile and run one real job end to end. A self-test is not a
   substitute.
2. **A real PNEZD file from an actual job** is still worth having. The reader is
   built to a documented convention, not to a real export.
3. ~~The icon's small-size lettering~~ — **closed at 0.2.0.** The lettering is
   out of the artwork at every size, so nothing smears at 16 and 32 px and no
   size-specific variant was needed.
4. **The `Geodetic (latitude / longitude)` dropdown entry** was a subagent
   addition to the owner-approved layout. It works, it is tested end to end, and
   he has not looked at it.

### Next build, when it comes

- **SPCS2022** — spec is DESIGN.md #21. Blocked on NATRF2022 and its
  transformation, not on effort. Michigan is 19 zones, needing transverse and
  oblique Mercator engines this program does not have.
- **NGVD 29 → NAVD 88** — sizing is DESIGN.md #22. MEDIUM, two work packages,
  buildable today; design the vertical-transformation registry so NAPGD2022 is
  later a data change.
- **Rename durability** (#23) — if it is ever worth it, `MoveFileEx` with
  `MOVEFILE_WRITE_THROUGH` via `ctypes`.

## Superseded status (2026-08-06, interim gate CLOSED)

**WP0–WP6 complete, committed, pushed.** Suite **546 passing in both `pytest`
and `-O`**, exit codes asserted directly, run unpiped. Working tree clean,
`main` level with `origin/main`. Nothing is half-finished: this is a clean
boundary, not a pause mid-package.

Owner stopped the session before WP7 deliberately — the release work had not
started, so nothing is in flight.

**Every interim-gate finding is resolved.** Codex returned 3 critical, 3 high,
1 medium. Findings #1, #2, #3, #5, #6 fixed and pinned; #4 dissolved with the
polynomial method (#14); #7 rejected with evidence (#10). The findings table and
each fix are in DESIGN.md amendment #11, extended by #18 and #19.

**Owner directives all landed:** the polynomial method is gone (#14), exports
ship as a single ZIP and it is the only deliverable (#15/#17), the app icon is
derived from the committed master by a build step (#15), and the three GUI notes
are in (#16/#17).

The prior MATLAB tool's six recorded defects are all either fixed or belong to
the deferred azimuth/distance feature. The five defects the WP5 test subagent
found in this program's own file layer are fixed, pinned and falsified (#18).

### Next session — where to pick up, in order

1. **WP7 release.** `launch.py` and `run.bat` exist and the icon build step is
   at `tools/make_icon.py`. Still needed: PyInstaller spec, the frozen-bundle
   `--selftest` as a build gate, Inno Setup with a once-generated frozen AppId,
   checksum, and the GitHub Release. Scope is DESIGN.md #13 — installer plus
   SHA-256 plus release notes naming what was verified, **no user manual**.
   Drop the `-dev` marker from `michspc.__version__` only at the release gate.

2. **The closing Codex gate over the full diff**, per TOOLING.md: background
   shell, `< /dev/null`, hard timeout, read the tail for the verdict. The
   polynomial deletion and the ZIP change are large and belong inside its scope.

3. **Open items for the owner**, neither blocking:
   - At 16 and 32 px the icon's "COORD CONVERT" lettering will be an illegible
     smear. A cropped, text-free compass variant for the small sizes inside the
     same `.ico` is the usual fix. His artwork, his call.
   - The GUI's `Geodetic (latitude / longitude)` entry in the From/To dropdowns
     is a subagent addition to the owner-approved layout. It works and is
     tested, but he has not looked at it.

4. **A real PNEZD file from an actual job** would still be worth having. The
   reader is built to a documented convention, not to a real export.

## Repo layout

```
michspc/spc/      computation core — stdlib only; no Qt, no file I/O, no network
michspc/fileio/   readers and writers; the ONLY layer that touches csv or the
                  GEOID18 binary grid. Named fileio, never io (shadows stdlib).
michspc/gui/      PySide6; never computes a domain result
tests/            suite; every expected value hand-derived in a comment
data/             g2018u3.bin — NGS GEOID18 tile, unmodified, SHA-256 pinned
docs/             DESIGN.md (authority), method/, the NOAA manual, reference/
```

## Non-negotiable conventions (enforce in review)

- Units explicit at every boundary; International feet is the default because
  Michigan legislated it, and the unit in force is stated in every output file.
- Longitude sign convention is user-selected with **no default**.
- Fail closed, never fabricate; refusals name the offending item.
- Missing elevation writes `N/A` in factor columns — never `1.0`.
- One authoritative representation per fact; derived values are never stored.
- One entry point per data path; loaders validate as strictly as the UI.
- No uncited constants — document and page, in an adjacent comment.
- Exports never silently clobber; atomic stage-and-rename.
- No load-bearing asserts in production code; the suite runs under `-O`.
- Cross-frame conversion refuses loudly. Never a silent pass-through.
- The rigorous §3.1 Lambert equations are the only computation path. What
  verifies them is external and lives in the suite: the frozen NGS NCAT anchors
  and the published Appendix C constants (DESIGN.md #14).

## Development process

Work packages by subagents → session lead independently re-derives load-bearing
math before accepting → independent adversarial review (Codex CLI) at the build
midpoint AND at closing → fix at the root, pin each finding with the reviewer's
own counterexample, falsify the pin, then narrowing re-confirmation until
approved. Commit per gated milestone; push after gates. Suite green in both
`pytest` and `-O` modes before any commit.

## Environment notes

Verified 2026-08-05 on this machine (Windows 11 Pro 26200, PowerShell 5.1):

- Python 3.14.5 via `py`
- PySide6 6.11.1 — imports cleanly on 3.14
- pytest 9.1.0
- git 2.54.0, gh 2.96.0 authenticated as `martin71337` (repo scope)
- codex-cli 0.144.1 — the independent reviewer

Repo lives at `C:\claude-projects\coord-convert`, outside OneDrive, per
`docs/method/TOOLING.md`.

Traps that apply here, from TOOLING.md: run the suite unpiped or assert the
runner's own exit code; PowerShell 5.1 has no `&&` and `Set-Content` defaults to
ANSI; set `QT_QPA_PLATFORM=offscreen` before any Qt import in tests; PyInstaller
freezes a script, not `-m`.
