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

## Status (2026-08-05, paused mid-gate-1 fix loop)

**WP0–WP4 complete, committed, pushed.** WP5 (file I/O) written and smoke-tested
end to end. Core suite **401 passing in both `pytest` and `-O`**, exit codes
asserted directly.

**Interim Codex gate ran and returned FINDINGS** — 3 critical, 3 high, 1 medium.
Full output in `review/gate1-output.txt`; the table of findings and their status
is DESIGN.md amendment #11. Two critical findings are fixed (#2 longitude
domain, #5 zone-bound constants); three remain open.

**In flight, uncommitted, needs audit before trusting:** two subagents were
running when the session paused and left untracked files —
`michspc/gui/{app,window,results_model}.py`, `tests/test_gui.py`,
`tests/test_fileio.py`. These are NOT verified and NOT committed. The core suite
above was run with those two test files excluded.

### Next session — where to pick up, in order

1. **Audit the subagent output per deliverable.** Run `py -m pytest` including
   `tests/test_fileio.py` and `tests/test_gui.py`. Re-derive any load-bearing
   expected value before accepting. Discard anything that cannot be verified —
   partial agent work is not automatically coherent.
2. **DESIGN.md #14 — DELETE the polynomial method entirely.** Owner directive,
   superseding #12: no unverified/unreviewed code pathway is to remain. Do this
   FIRST — before fixing gate findings #3 and #4, which exist only because of it,
   and before auditing anything downstream. Fixing or reviewing code that is
   about to be deleted is waste.

   Remove, and grep for stragglers afterwards:
   - `michspc/spc/polynomial.py` and `michspc/spc/agreement.py` (the latter
     exists only to compare the two engines)
   - `tests/test_polynomial.py` and `tests/test_polynomial_band.py`
   - `convert.py`: `_check_engines`, the in-band/out-of-band branch,
     `WarningCode.ENGINE_DISAGREEMENT_OUT_OF_BAND`, and the
     `inverse_agreement` / `forward_agreement` fields on `PointConversion`
   - `zones.py`: `band_lat_min` / `band_lat_max` and their docstrings
   - `job.py`: `JobResult.worst_engine_discrepancy`
   - `exports.py`: the two "Engine check … (mm)" audit columns
   - `report.py`: the METHOD section's two-engine wording and the worst-
     discrepancy line — rewrite it to cite the frozen NGS NCAT anchors as the
     verification instead
   - `CLAUDE.md`'s own "two engines … must agree within 0.5 mm" non-negotiable
   - references in `test_convert.py`, `test_fileio.py`, `test_gui.py`

   Keep `michspc/spc/lambert.py`'s `_require_valid_geodetic` and
   `_require_finite_grid` — they currently live in lambert.py and are imported
   BY polynomial.py, not the other way round, so they survive the deletion.
   Verify that after removal.

   The suite must be green in both modes afterwards, and the NCAT and Appendix C
   anchor tests must still be present and passing — they are now the *only*
   verification of the projection mathematics.

   **In the same change, rewrite `report.py`'s METHOD section.** It currently
   states that every coordinate is computed twice by two independent methods and
   prints a worst-engine-discrepancy figure. Deleting the second engine makes
   that text FALSE, and a job record that misdescribes its own derivation is
   worse than none — it gets signed, filed and believed. Cite what actually
   carries the weight instead: the frozen NGS NCAT anchors and the published
   Appendix C constants. See DESIGN.md #15 note 3, which makes this a standing
   rule rather than a one-off.

2a. **Exports ship as a single ZIP** (DESIGN.md #15 note 2). Three files per job
   become one `<stem>.zip`. Everything the loose writers guaranteed must survive:
   stage-and-rename atomicity on the archive, refusal to clobber without
   confirmation, and the PNEZD round-trip verification running BEFORE the archive
   is committed to its final name. The GUI's "Open folder" and
   `window._existing_outputs` both need updating, and `report.py`'s "FILES
   WRITTEN" section describes three loose files and will also be wrong.

   **Decided (DESIGN.md #17): the ZIP is the ONLY deliverable.** No loose PNEZD
   beside it. A job writes exactly one artefact. The three files travel together
   or not at all, so a PNEZD export can never be filed or emailed without the
   record explaining how it was derived.

2b. **App icon** (DESIGN.md #15 note 1). Master artwork is committed at
   `assets/icon/coord-convert-1024.png` (1024×1024 RGBA). Generate a
   multi-resolution `.ico` (16/32/48/64/128/256) from it AS A BUILD STEP, not as
   a second committed artefact, so the two cannot diverge. Consumed by the Qt
   window icon, the PyInstaller bundle, and the Inno installer plus Start-menu
   entry.

   **Ask the owner:** at 16 and 32 px the "COORD CONVERT" lettering will be an
   illegible smear. The usual fix is a cropped, text-free compass variant for the
   small sizes inside the same `.ico`. It is his artwork — ask, do not assume.

2c. **Three GUI notes** (DESIGN.md #16):
   - The input row's **label is renamed to "Input file:"** in every state (not
     "Input PNEZD file:"), and its **format hint follows the selected From
     zone**. When From is `Geodetic (latitude / longitude)` the file is not
     PNEZD — columns two and three are latitude and longitude — so the hint must
     read *point, latitude, longitude, elevation, description*. A file fed under
     the wrong reading yields a coordinate rather than an error, and the easting
     guard only covers the zone case, so this is a correctness aid, not
     cosmetics.
   - **Remove the "as used by …" tail** from the longitude sign selector.
     **Decided (DESIGN.md #17): short in BOTH surfaces** — change the
     `LongitudeConvention` enum values themselves to `"negative west (-84.37)"`
     and `"positive west (84.37)"`. No separate GUI label, and the job record's
     "Longitude" line gets the shorter text too.
   - **Default the output folder to Downloads**, via
     `QStandardPaths.writableLocation(...DownloadLocation)` — not a hand-built
     `~/Downloads`, since Windows allows it to be relocated. Fall back to the
     home directory if Qt returns empty. The overwrite refusal, atomic write and
     round-trip check all still apply, so a default destination cannot silently
     clobber a previous job.
3. **Gate finding #1 (CRITICAL)** — tag geodetic input with its reference frame.
   `project_point` must take a source frame and call `require_same_frame`.
4. **Gate finding #6 (HIGH)** — authenticate the geoid grid in the production
   path (`default_grid` must verify the checksum) and validate the header
   against the shipped tile's canonical geometry, so a row/column swap that
   preserves the payload length is refused rather than silently returning a
   5.16 m error.
5. **Defects the WP5 test subagent found in my file layer.** Its suite
   (`tests/test_fileio.py`, 117 tests, green in both modes, independently
   re-run by the lead) pins these as CURRENT behaviour — so fixing them will
   turn those pins red, which is exactly what should happen:
   - **NaN reaches a coordinate file through the ELEVATION column.** Confirmed:
     `101,780000.000,13123359.580,nan,IRON PIPE` writes
     `101,117978.426,19685039.370,nan,IRON PIPE`. `write_all`'s finiteness loop
     checks only northing and easting; `float("nan")` parses; `value == 0.0` is
     False for NaN; `verify_round_trip` re-parses `"nan"` happily. Its docstring
     claims teeth it does not have. `inf`/`-inf` behave the same. **Fix the
     reader** (reject non-finite at parse) rather than only the writer.
   - **Unquoted thousands separators produce a wrong coordinate and a written
     file.** `101,780,000.000,13,123,359.580,800.00,IRON PIPE` is accepted as
     northing 780.0, easting 0.0, elevation 13.0. `_parse_number`'s
     `.replace(",", "")` is dead code — `csv.reader` already consumed those
     commas as delimiters. Warnings fire but nothing refuses.
   - `formatting.angle_dms`'s two carry guards are **unreachable** (rounding
     happens before the divmod). Probed over 2,000,000 angles: fired zero times.
     Dead code offering false assurance — delete them and say why.
   - `report.build_report` iterates `_WARNING_HEADINGS`, not the warnings, so a
     future `WarningCode` without a heading would be counted in the total and
     never printed. Latent today; all three codes are covered.
   - `pnezd.read`'s cp1252 fallback catches only `OSError`, so an undecodable
     byte raises a raw `UnicodeDecodeError` instead of a `PnezdError`.
6. **Correction to carry forward:** the US survey foot is the LONGER foot
   (1200/3937 m vs 0.3048 m exactly), so a fixed length is a SMALLER number of
   them. 800 international feet = 243.84 m exactly = **799.9984** US survey
   feet. (The lead's WP6 brief stated this backwards; `test_fileio.py` has both
   directions derived correctly.)
7. **Pin every accepted finding with the reviewer's own counterexample** as a
   regression test, then **falsify each pin** (revert the fix, watch it fail,
   restore). None of the fixes landed so far have been falsified yet — that is
   outstanding work, not a completed step.
8. **WP6 GUI landed from a subagent — audit it, then close its gaps.**
   `michspc/gui/{app,window,results_model}.py` and `tests/test_gui.py`
   (35 tests). Suite verified by the lead at 553 passing in both modes, exit 0.
   The agent falsified three of its own pins and launched the app twice on the
   real Windows platform plugin. Still to do:
   - **Record the approved GUI layout and look in DESIGN.md**, per METHOD.md §5
     ("recorded once and enforced in review"). The agent correctly refused to
     write to the design authority itself.
   - **The agent added a `Geodetic (latitude / longitude)` entry to the From and
     To dropdowns** so one pair of controls states all three directions. This is
     an addition to the owner-approved layout — confirm with the owner or record
     it as an amendment.
   - `job.JobSettings.longitude_convention` still carries a `NEGATIVE_WEST`
     default, which DESIGN.md §7 forbids. The GUI enforces the no-default rule,
     but the API-level default remains a bypass. Remove it.
   - `window._existing_outputs` duplicates the three output suffixes; add
     `exports.destination_paths(result)` and use it.
   - No end-to-end geodetic conversion test exists — only the longitude gating.
   - `QDesktopServices.openUrl` is never exercised.
9. WP7 release, then the closing Codex gate.

**WP7 scope, per DESIGN.md #13:** the `.exe` ships as a **GitHub Release** on
`martin71337/michigan-spc-converter` — installer plus SHA-256 plus release notes
naming what was verified, tagged with the version literal. **No user manual**:
the generated-manual requirement and its doc-freshness release gate are
deliberately dropped, because the job record written beside every export already
documents the run and cannot go stale. All other METHOD.md §6 gates stand.

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
- Two engines (rigorous §3.1 and polynomial §3.4) run on every point and must
  agree within 0.5 mm; disagreement is a named failure, never an average.

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
