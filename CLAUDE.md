# CLAUDE.md — Michigan SPC Zone Converter

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

## Status (2026-08-06, interim gate CLOSED)

**WP0–WP6 complete, committed, pushed.** Suite **546 passing in both `pytest`
and `-O`**, exit codes asserted directly, run unpiped.

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
