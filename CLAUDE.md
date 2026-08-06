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
2. **DESIGN.md #12 — demote the polynomial engine from runtime gate to
   build-time check**, per the owner's directive. This deletes `_check_engines`,
   the in-band/out-of-band branch, and `ENGINE_DISAGREEMENT_OUT_OF_BAND`, and
   dissolves gate findings #3 and #4. Do this BEFORE fixing those two findings —
   fixing code that is about to be deleted is waste.
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
8. WP6 GUI review, WP7 release, then the closing Codex gate.

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
