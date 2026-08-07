# Closing gate — session lead's adjudication (Phase B)

2026-08-06. Inputs: Codex closing gate (review/gate2-output.txt, VERDICT:
FINDINGS), Opus adversarial review (VERDICT: FINDINGS, probes in
review/opus-probes/), NCAT live cross-check (review/ncat-crosscheck/, all
PASS), and the session lead's own core read. Every finding below was
independently reproduced or code-verified by the lead before acceptance;
none is accepted on a reviewer's say-so.

## The headline

**The mathematics is right.** Three independent verifications agree: the live
NCAT cross-check matched all 666 comparisons across every pipeline, direction,
zone pair and unit system to <= 0.9 mm (scale factors and convergence exact to
NCAT's printed precision); Codex re-derived the Lambert equations at 80-digit
precision (max diff 1.7e-9 m over the 27 anchors); Opus re-derived them
independently at 60-digit precision (max diff 9.3e-10 m), writing the manual's
own positive-west form from scratch. The suite is 546/546 in both `pytest`
and `-O`, exit codes verified (Opus, unpiped).

**Every defect found lives in the contract/record/robustness layer** — what
the deliverable *says about itself*, what the API promises, what the tests
actually pin — not in the numbers. At this correctness tier those layers
matter almost as much as the numbers, and two interim-gate fixes turn out to
be recorded as landed when they did not land.

## Confirmed findings (merged, deduplicated)

| # | Adjudicated severity | Reachable via GUI? | Found by | Defect |
|---|---|---|---|---|
| F1 | CRITICAL (latent) | No — API only | Codex #2, Opus H2, lead | `constants=` seam recorded DELETED in amendment #11 is still on all four public conversion functions, unguarded; mispairing moves a point 4,231 km with zero warnings; `zone_code` field exists and nothing reads it; test_convert.py:391 locks the seam in |
| F2 | HIGH (latent) | No — GUI forces choice | Codex #1, lead | `JobSettings.longitude_convention` defaults to NEGATIVE_WEST against the program's own "no default" contract; the claimed pin (test_fileio.py:1707) never inspects JobSettings — vacuous |
| F3 | HIGH | **Yes** | Opus H1, Codex #3 | Zone→geodetic elevation stays in the INPUT unit while the clean export, audit CSV and job record all declare the OUTPUT unit. 900 ift read as 900 m = 625.68 m error for a trusting reader; feeding the file back as instructed = 98 ppm factor error. Split-brain: exports.py:55 knows the truth, job.py:126 docstring and report claim the opposite |
| F4 | HIGH | **Yes** | Opus M4, Codex #3 | Job record unconditionally describes both geodetic directions' files as "PNEZD... northing, easting" in linear units — three false statements about a lat/lon file, in the program's only documentation |
| F5 | HIGH | Yes (silent) | Codex #4 | `verify_round_trip` compares only point IDs after re-parsing; a writer regression corrupting every coordinate passes the gate. Also the third divergent CSV-quoting implementation (Opus L8) lives inside it |
| F6 | HIGH | Yes (narrow) | Codex #5 | Job record hashes `settings.input_path` independently of the bytes parsed; a caller-supplied `source` (or an edit in the parse-to-hash window) makes the record certify bytes that were never converted |
| F7 | HIGH | **Yes** | Codex #6, lead | Point WITH elevation but outside the GEOID18 tile: `GeoidError` swallowed, no warning, and the record lists the point under "Blank elevation field" — a falsehood in the audit record |
| F8 | MEDIUM | **Yes** | Codex #7, Opus L7 | Duplicate point IDs accepted silently; report references by ID become ambiguous; CAD import overwrites. Lead recommends refusal (loader-as-strict-as-UI) |
| F9 | MEDIUM | Yes (race) | Codex #8 | `overwrite=False` checks existence early but commits with unconditional `os.replace` — a concurrently created file is silently clobbered. Windows `os.rename` refuses existing targets; one-line root fix |
| F10 | HIGH (test integrity) | — | Codex #9, Opus M5 + caveat | Interim pins #2 (275.4445 longitude) and #3 (non-finite) were never written — Codex seeded both pre-fix behaviors and 260 tests stayed green. No NCAT anchor drives `job.run`/export; ZONE_TO_GEODETIC has ZERO successful executions in all 546 tests (why F3/F4 survived) |
| F11 | MEDIUM | **Yes** | Codex #10 | csv.reader leniency silently repairs malformed quoting (`"A"junk` → `Ajunk`); output no longer represents the input text, no refusal |
| F12 | MEDIUM | Yes (edge) | Opus M3 | 16–45 m band of northings below each zone's cone apex raises bare `ZeroDivisionError` instead of the adjacent informative refusal; fails closed but GUI shows "Refused: division by zero" with no point id |
| F13 | MEDIUM | Yes (crash) | Codex #11 | ZIP path never fsyncs (the plain-text writer does); `.partial` files can linger after kill; no CRC self-check before commit |
| F14 | LOW | Yes | Opus M6, Codex #3 | Audit CSV formats geodetic input lat/lon with the linear formatter — 3 decimals ≈ 55 m; full precision recoverable in later columns |
| F15 | LOW | Edge | Opus L10 | BOM survives into `point_id` via the cp1252 fallback path only |
| F16 | LOW | — | Opus L9, lead | `MainWindow.direction()` docstring describes a zone-to-itself guard that does not exist (behavior is a legitimate identity/unit conversion — fix the docstring); ellipsoid.py cites §3.12/3.14/3.15 at printed page numbers mislabeled as PDF pages, contradicting lambert.py |

GUI notes (owner's call, not defects in computation): results table headers
read "Northing/Easting" even when showing latitude/longitude; both unit
selectors stay active in every direction.

Interim pin audit (Codex): #1 faithful, #4 dissolved, #6 faithful, #7 resolved
meaningfully (Opus confirmed -O is meaningful for this suite's shape); #2, #3
missing; #5 REVERSED (= F1).

## Extensibility: REWORK-REQUIRED (both reviewers, independently congruent)

DESIGN.md §6's claim that SPCS2022 "arrives as data" does not hold. Merged
rework list: no Projection protocol (convert.py imports lambert by name);
`Zone.definition` typed to the 2SP form only; `ProjectionKind` declared and
never read; the claimed 1SP constructor does not exist; `constants_for`
hardwires 2SP; no datum-transformation seam as code (PointConversion carries
one pivot, one frame); report hardcodes 2SP/GRS80/NAD83/Appendix-C/NCAT-27
authority text; zone lookup keyed by bare code (era collision); archive names
and audit columns cannot distinguish eras; `_EASTING_WINDOW_M` assumes SPCS 83
false-easting spacing; no GUI frame selector; GEOID18 hardwired rather than a
model registry keyed by frame/epoch. Clean: the GUI zone dropdown builds
entirely from ALL_ZONES; zones.py itself is genuinely data.

Lead's recommendation: do NOT rework now. The core just passed three
independent verifications; restructuring it before release re-opens verified
surfaces for zero current functionality. Instead amend DESIGN.md to state the
truth and carry this list as the SPCS2022 work package's opening spec.

## Proposed fix plan (Phase D, on owner approval)

- **WP-R1 core/API contract:** F1 (delete the `constants=` parameters, fix
  test_convert.py:391), F2 (make `longitude_convention` a required field, real
  pin), F12 (widen apex guard to the informative refusal), F16 citations.
- **WP-R2 deliverable honesty:** F3 (elevation to output unit end to end —
  owner to confirm shape), F4 (direction-aware record wording), F7 (new
  warning code + report category "elevation present, geoid unavailable"),
  F8 (refuse duplicates — owner to confirm), F11 (strict CSV lexing),
  F14 (degree formatter for geodetic source columns), F15 (strip/refuse BOM),
  F16 docstring. GUI notes if owner wants them.
- **WP-R3 write-path integrity:** F5 (full-field round-trip comparison, one
  quoting implementation), F6 (hash the bytes the parser consumed), F9
  (`os.rename` commit when overwrite=False), F13 (fsync + testzip before
  commit; stale-.partial policy).
- **WP-R4 verification:** F10 — write the missing interim pins and falsify
  them; freeze the 12 fresh NCAT points + geoid values as anchors; end-to-end
  anchor tests driving file → job.run → ZIP → parsed audit CSV for all three
  directions in all three units; positive ZONE_TO_GEODETIC coverage.
- **Records:** DESIGN.md amendments (gate findings table + fixes; extensibility
  truth + SPCS2022 spec), CLAUDE.md refresh, delete stray root dev-method.zip.
- Then the narrowing Codex re-confirmation over fixed surfaces, then WP7.

## Decisions the owner must make (Phase C gate)

1. Approve the fix list and packaging? Anything to drop, add, or re-rank?
2. F3 fix shape: convert the zone→geodetic elevation into the output unit
   (recommended — matches the docstring, record, and audit claims) or keep it
   in the input unit and relabel every surface?
3. F8: refuse duplicate point IDs (recommended) or accept with a warning?
4. Extensibility: record-now, rework-at-SPCS2022 (recommended) or rework now?
5. GUI notes (table headers per direction; unit-selector states): fix now or
   leave for a later session?
