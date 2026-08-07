# Closing adversarial review — plan (gate 2)

2026-08-06. Owner-approved sequence: full adversarial review now → fix cycle →
WP7 release → narrow Codex pass over the release diff → GitHub Release → close.
This file plans the review and fix cycle. Session lead coordinates; work goes
to subagents per METHOD.md §3; the lead independently re-derives load-bearing
findings before accepting them.

Review charter (all reviewers): the software must be **sound and trustworthy**
at the recorded correctness tier — a wrong coordinate lands on a sealed survey.
Added owner surface: attack DESIGN.md §6's extensibility claim — could SPCS2022
(new zone definitions, a second projection era, NAD 83 ↔ NATRF2022 as a frame
boundary) be added without rework of the core?

## Phase A — independent evidence, three tracks in parallel, blind to each other

### A1. Codex CLI closing gate (independent reviewer of record)

- Scope: the full codebase at HEAD (`4dba756..HEAD` covers the post-interim
  work, but the charter is the whole program — the interim gate predates the
  polynomial deletion and the ZIP export rework, both large).
- Invocation per TOOLING.md: `codex exec --sandbox read-only -C .` from a
  background shell, `< /dev/null`, hard timeout, stdout to
  `review/gate2-output.txt`, read the tail for the verdict.
- Prompt (saved to `review/gate2-prompt.txt`): design doc pointer, priority
  surfaces ranked by risk — (1) `michspc/spc/` Lambert core and the
  convert/round-trip chain, (2) `michspc/fileio/` readers/writers/geoid grid,
  (3) factor chain incl. missing-elevation handling, (4) `job.py`
  orchestration and refusal paths, (5) GUI honesty (same formatters as
  exports), (6) the SPCS2022 extensibility attack — plus "construct concrete
  counterexamples" and a demanded APPROVED/FINDINGS verdict with clean
  surfaces stated.

### A2. Opus subagent adversarial review

- Agent tool, model opus, full repo, same charter and ranked surfaces, run
  blind to Codex (launched in parallel; no shared state).
- Required output: structured findings — severity, file:line, the concrete
  counterexample (inputs → wrong output), and an explicit verdict per surface.
  Findings without a counterexample are labeled as suspicions, not findings.

### A3. NCAT/geoid live cross-check (subagent work package)

Both endpoints verified reachable from this machine 2026-08-06:
`geodesy.noaa.gov/api/ncat/llh` (conversion) and
`geodesy.noaa.gov/api/geoid/ght` (GEOID18 separation, mm precision).

- **Points:** 4 fresh points per zone, none coinciding with the 27 frozen
  anchors — spread to near the zone's latitude-band extremes and off-center
  longitudes, plus one realistic Michigan location per zone (a place a real
  job could sit). All carry plausible orthometric elevations.
- **Pipelines under test, through the real file path** (input file → job run →
  ZIP export → parse the audit CSV), never by calling core functions directly:
  - geodetic → SPC, each of the 3 zones;
  - SPC → geodetic, each of the 3 zones;
  - zone-to-zone, all 6 directed pairs;
  - each in all three units (m, international ft, US survey ft).
- **Truth values:** NCAT single calls for the one-leg pipelines; chained NCAT
  (source SPC → lat/lon → target SPC) for zone-to-zone; the geoid API for
  GEOID18 separation at every point; combined factor re-derived by hand from
  NCAT's scale factor and the point's ellipsoid height.
- **Tolerances** (lead's judgment; every actual delta recorded in a table
  regardless of pass/fail):
  - northing/easting, single-leg: ≤ 0.002 m (NCAT prints 0.001 m);
  - northing/easting, chained zone-to-zone: ≤ 0.004 m (two printed roundings);
  - geoid separation: ≤ 0.002 m (API prints 0.001 m; both interpolations are
    biquadratic per DESIGN.md #8);
  - grid scale factor: ≤ 2e-8 (NCAT prints 8 dp);
  - convergence: ≤ 0.02 arcsec (NCAT prints 0.01″).
- **Artifacts:** raw NCAT/geoid JSON captured verbatim under
  `review/ncat-crosscheck/`, plus the comparison table. These become the new
  frozen anchors in the fix phase (owner-approved).

### Lead's independent re-derivation (before accepting any track)

- Re-query a sample of A3's NCAT points directly and diff against the
  subagent's captures; verify its comparison arithmetic on that sample.
- Re-derive at least one conversion per pipeline class end to end.
- Verify all claimed counts and exit codes directly, unpiped.

## Phase B — adjudication (lead, solo by design)

Merge and dedupe findings from all three tracks. For each: independently
re-derive the claim, then classify **Confirmed** (with the counterexample
reproduced locally), **Refuted** (with evidence, recorded like DESIGN.md #10),
or **Deferred** (out of scope with reason). Draft the proposed fix list —
root-cause shape, severity order. No code changes in this phase.

## Phase C — present to owner (hard gate)

Findings, verdicts, actual NCAT deltas, proposed fixes, and anything refuted
with the evidence. Owner decides what proceeds. Nothing is fixed before this.

## Phase D — fix cycle (after owner approval)

- Subagent work packages per finding cluster; every fix pinned with the
  reviewer's own counterexample as a regression test; every pin falsified
  (revert → red → restore); suite green in `pytest` AND `-O`, unpiped.
- The A3 points land as new frozen anchors (`ncat_anchors.py` extension plus
  geoid anchors) with hand-derivation comments per METHOD.md §4.
- Housekeeping: delete the stray root `dev-method.zip` (byte-identical to
  `docs/reference/dev-method.zip`).
- DESIGN.md amendments for the gate results and every accepted/refuted
  finding; commit per milestone; push after the gate closes.
- Narrowing Codex re-confirmation over only the fixed surfaces, until
  APPROVED.

## Phase E — WP7 release (scope: DESIGN.md #13)

PyInstaller spec (freezes `launch.py`, not `-m`), frozen-bundle `--selftest`
as a build gate, Inno Setup with a once-generated frozen AppId, SHA-256
checksum, release notes naming what was verified, no user manual. Drop the
`-dev` marker from `michspc.__version__` only at the release gate.

## Phase F — close

Narrow Codex pass over the release diff → GitHub Release on
`martin71337/michigan-spc-converter` → clean boundary commit → session close.

## Contingencies

- Codex quota death mid-gate: record gate state and a boundary commit;
  schedule the confirm pass after reset (TOOLING.md).
- NCAT/geoid outage or throttling: retry with backoff; every accepted truth
  value must come from a captured raw JSON response, never from memory.
