# The Method

Defaults for engineering-grade software development. Everything here earned
its place by catching a real defect or preventing a real loss on prior
projects. Adapt freely; record what you adapt and why.

## 1. Name the correctness tier first

Before any code: state, in one sentence in the project docs, what a wrong
answer costs. ("A plausible-looking wrong number goes on a stamped drawing"
vs "a glitch annoys a user for a minute.") Every other decision — how much
verification, how strict the loaders, whether a convenience default is
allowed — scales from that sentence. When in doubt between a convenient
behavior and a correct one, the tier sentence is the tiebreaker.

## 2. One design authority with an amendment log

- Keep ONE design document (`DESIGN.md`) as the source of truth: data model,
  core algorithms, external references, verification anchors.
- Decisions get RECORDED, append-only, in a numbered amendment log inside
  it: what changed, why, what it supersedes. A superseded decision stays in
  the log with a pointer forward — history is evidence, not clutter.
- `CLAUDE.md` (or equivalent) is the working summary: current status, where
  to pick up, repo layout, the non-negotiables. It defers to DESIGN.md and
  is rewritten freely; DESIGN.md is amended, never rewritten.
- When a primary source falsifies a plan assumption, SAY SO PLAINLY in the
  log and choose fidelity to the source. Do not quietly blend the two.

## 3. Build process

- **Work packages.** Implementation proceeds in scoped work packages (WPs),
  each small enough to review as one diff, each ending with the full test
  suite green and a commit. Subagents write code; the session lead reviews
  every diff and INDEPENDENTLY RE-DERIVES all load-bearing math/logic before
  accepting tests that pin it. Never accept a subagent's numbers on its own
  say-so — subagent reports overstate; verify counts, exit codes, and claims
  directly.
- **Review gates.** An independent adversarial reviewer (a different model/
  tool than the one that wrote the code) reviews at TWO points minimum: an
  interim gate at the build's midpoint — this has repeatedly caught blockers
  in code the next package was about to build on — and a closing gate over
  the full diff. **Cadence scales with the consequence tier**: work whose
  outputs carry real-world consequence always gets both gates; low-stakes
  tooling may run closing-only. The tier sentence (§1) decides, and the
  choice is recorded. Findings get fixed at the root, each pinned by the
  reviewer's own counterexample as a regression test, then a NARROWING
  re-confirmation pass (only the fixed surfaces) until APPROVED.
- **Commit discipline.** Commit at each gated milestone with a message that
  records what was verified (test counts, both modes, anchors). Push after
  gates. Before any pause or risky stretch, leave a clean committed boundary
  and a written resume checklist — sessions die mid-flight; the boundary is
  the recovery point.
- **Interruptions.** If work is interrupted mid-package, first assess the
  tree (does the suite pass? which deliverables landed?), salvage coherent
  work, and disclose in the commit message when histories had to interleave.

## 4. Verification doctrine

- **Hand-derived anchors.** Every expected value in a test is derived in a
  comment immediately above it — from the equation, the geometry, the spec —
  never read back from the code's own output. High-precision anchors are
  pinned exactly (`==`, not approx) when the claim is "nothing moved".
- **Falsify your regressions.** A regression test that has never failed
  proves nothing. When pinning a fix, demonstrate the test fails against the
  unfixed code (revert, run, restore) at least once.
- **Independent recomputation.** Any change to domain math or geometry is
  verified against a separate calculation (hand calc or an independent
  script) before it ships. Eyeballing is not verification.
- **All shipped run modes.** The suite passes in every mode the software
  actually runs in (e.g. Python normal AND `-O`, which strips asserts —
  hence: no load-bearing asserts in production code, ever; use if/raise).
- **Check real exit codes.** Piping test output can swallow failures
  (`cmd | tail` reports the pipe's status). Always assert the test runner's
  own exit code.
- **Machine-enforce boundaries.** Architectural rules (layer X never imports
  Y; only module Z touches library Q; no third-party types leak past a
  boundary) are tests — AST/import scans — not comments. Include
  anti-vacuousness checks proving the scanner actually sees violations.

## 5. Engineering conventions (the non-negotiables, tier permitting)

- **Fail closed, never fabricate.** An unhandleable case produces a loud,
  specific refusal naming the offending item — never a plausible default.
  Refusal messages teach: say what the thing is and what to do.
- **Disclose, don't silently normalize.** When the program must change
  stored user data (migration, derivation superseding an entry), it says
  exactly what changed, and the project opens dirty — a file on disk that no
  longer matches the screen must be a conscious save away, never automatic.
  Prefer disclosure over refusal when refusing would lock the user away
  from their own work over a secondary inconsistency.
- **One authoritative representation per fact.** Anything derivable is
  derived, never stored as an independent second fact (slope from inverts,
  lengths from geometry). Where a derived and a stored value could coexist,
  the derivation governs and supersession is disclosed.
- **One entry point per data path.** Manual entry, imports, and file loads
  all funnel through the same validation gate. Loaders validate as strictly
  as interactive input — corrupt files never reach the core.
- **No uncited constants.** Every empirical coefficient, tolerance, or
  proportion carries its source (document, edition, page/table) in an
  adjacent comment. If the source publishes no number and one is needed,
  declare it a disclosed convention, not a citation.
- **Immutable core outputs.** Result records are frozen; UI layers never
  mutate computed results; undo/redo works by snapshotting immutable state
  (structural sharing keeps it cheap).
- **Exports never silently clobber.** Atomic writes (stage + rename), an
  overwrite prompt, and a writer that refuses to produce a file its own
  reader would reject.
- **Round-trip properties.** Save→load→save is byte-stable. Migration
  chains validate each step against its own version's schema, touch no
  filesystem, and return user-facing disclosure notes.
- **UI honesty.** Screen and report read the same data through the same
  formatters. Severity colors mean one thing each (red = actually wrong;
  amber = look at this).
- **UI look: present options, don't assume.** At a GUI project's start,
  offer the owner concrete look-and-feel options rather than defaulting
  silently — knowing that his lean is toward DURABLE, PROVEN presentation
  (native OS widgets, standard dialogs, system fonts, restraint over
  fashion). Whatever is chosen gets recorded once and enforced in review. A generated manual is rebuilt in the same change
  as any user-facing behavior — a stale manual is worse than none. Version
  is a single literal with every consumer reading it.

## 6. Release (when the project ships installables)

- ONE sanctioned, fully gated build script; first failure aborts. Typical
  gates: version sanity (refuse pre-release markers, refuse reusing a
  shipped number), full suite in all modes, doc-freshness gates that check
  CONTENT (not mtimes — checkouts and copies fake mtimes), bundle build, a
  frozen-artifact SELF-TEST (the shipped bundle is the one thing the suite
  can't reach), installer, checksum, immutable archive.
- Partial builds (skipped tests, missing installer) never count as released.
- The install proof is human: install on a clean profile and run one real
  workflow end to end. A self-test is not a substitute.
- Between releases, the version literal carries a `-dev` marker the release
  gate refuses — so the shipped number space stays unambiguous.

## 7. Scope discipline

- A deferred-scope list lives in DESIGN.md with the REASON each item was
  deferred. Nothing deferred gets reintroduced without revisiting the
  recorded decision.
- Resist adjacent scope: a checker is not a designer, a parser is not a
  validator-of-the-world. Refusing to solve a neighboring problem is a
  recordable decision, not a failure.
- Field validation against the tools of record comes before any real
  deliverable leans on the outputs. Schedule it; don't let it drift.
