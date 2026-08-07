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

## Status (2026-08-07, owner's second round of edits DONE, awaiting approval to release)

**Both rounds of the owner's interface edits are in and the release is still
paused on his approval.** Round two: DMS entry, a smaller copy glyph, and the
worked example out of the longitude sign entries. Full account: DESIGN.md
**#28**.

1. **Copy glyph 14 px → 11 px.** Pinned as a relationship — the button may
   stand above its line of text by the frame a flat QToolButton needs and no
   more — rather than as the number.
2. **`LongitudeConvention` values are now `negative west` / `positive west`.**
   The `(84.37)` example moved to the dropdown's tooltip. **This shortens the
   job record's `Longitude` line too**, which is #17's standing choice (one
   wording in both surfaces), not an oversight.
3. **Lat/long can be typed as degrees / minutes / seconds** on the Single point
   tab — four boxes per angle with the symbols already in place, hemisphere
   letter instead of a sign, opening unanswered. Decimal degrees is still what
   the tab opens on. The composition lives in `michspc/fileio/dms.py`, beside
   the formatters that define the notation, because the GUI may not compute an
   angle. The load-bearing pin: **the same DMS entry converts identically under
   both longitude conventions, where the same decimal entry gives two points
   340 miles apart.**
4. **The input CSV takes decimal degrees only** — the owner's question,
   answered. It always did; DMS is now refused *by name*, with a message
   pointing at the Single point tab. Reading DMS from a file is deliberately
   not built: packed `434759.8` is indistinguishable from an ordinary decimal
   degree, so a file reader would have to guess.

Suite **1048 → 1118**, green in both modes; frozen-bundle self-test passes.
Seven seeded defects, all caught.

### Round one (DESIGN.md #27), also in

All four are interface-only: no computation, no formatter, and no value on
screen is produced differently.

1. The single-point result reads in **two columns, INPUT left, OUTPUT right**,
   with a vertical rule between. Row indices are unchanged by the split, so a
   right-column button cannot copy a left-column value — pinned.
2. The copy control is the **Windows 11 two-sheet glyph**, drawn with QPainter
   in `michspc/gui/copy_icon.py` (no new asset in the build's path), sitting
   **beside its own value** instead of pinned to the far right.
3. The **input file box** starts empty; the `C:\jobs\24-118\pts.csv`
   placeholder is gone. The format hint below it is untouched.
4. The **output folder** starts empty. This reverses #16 note 3;
   `default_output_directory` is deleted, not left dormant.

Every new pin was falsified by seeding the defect it catches — including one
that had to be rewritten because the first version passed against its own
defect (DESIGN.md #27, Verification).

### Before releasing this — open with the owner

- **The job record's `Longitude` line is now shorter too** — `Longitude
  negative west`, with no `(-84.37)`. That follows #17's standing choice of one
  wording in both surfaces. If he wants the example kept in the record and out
  of the dropdown only, that is a separate GUI label and #17 has to be reopened.
- **The DMS hemisphere opens unanswered** and Convert waits for it. Michigan is
  always N and W, so that is two clicks per conversion he may not want. Made
  this way because the house rule is that nothing answers a question for the
  user; preselecting N and W is a two-line change if he would rather have it.
- **The layout question was asked and not answered.** "Two columns, one for
  input and one for output" was read as the **results panel**: the Conversion
  box keeps its owner-approved full-width shape on top, and the INPUT/OUTPUT
  result blocks are what split. The other reading — the whole tab splitting,
  entry form left and results right — was not built. Cheap to change.
- **The version number is not bumped.** 0.2.0 is still the literal.
  Recommendation is **0.3.0**: the Single point tab reaches users for the first
  time in this release, which is a feature, not a patch.
- **The release cannot be cut from a Linux session.** Gates 5 and 7 of
  `tools/build_release.py` are PyInstaller and Inno Setup, Windows-only. The
  build has to be `py tools/build_release.py` on his machine.

## Superseded status (2026-08-07, single point tab BUILT AND GATED, unreleased)

**The Single point tab is built, reviewed and committed — not released.** The
owner asked to pause before cutting a release; `main` carries it, 0.2.0 is still
the released version, and the version literal has not moved.

A second tab beside the file tool: one typed coordinate, converted, displayed.
No file, no output folder, nothing written. Elevation optional. Input is either
N/E/Z or geodetic. Lat/lon in decimal degrees and DMS (magnitude plus hemisphere
letter, five decimals of a second). A copy button per value plus Copy all.

**The property that shaped it:** the two tabs are incapable of disagreeing about
the same point — same validation gate, same conversion function. Two reviewers
running blind could not construct a disagreement; one drove both real GUIs over
378 configurations and compared the panel against the audit CSV the other tab
wrote, section by section.

**The closing gate found a CRITICAL both reviewers hit independently:** a stale
result survived every control change with both copy paths armed — a reading
100,001 ft out, one click from the clipboard. Fixed, seven pins, all falsified.
Five more findings fixed and two test gaps closed, each found by seeding a
defect the suite passed. Full account: DESIGN.md **#26**.

Suite **1031**, green in both modes; the frozen-bundle self-test still passes.

### Before releasing this

1. Look at the tab — the layout, the copy buttons, the wording — it has not been
   seen on a real screen by its owner.
2. Then the usual: bump the version, `py tools/build_release.py`, tag, GitHub
   Release.

## Superseded status (2026-08-07, 0.2.0 RELEASED)

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
