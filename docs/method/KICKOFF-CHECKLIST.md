# New-project kickoff checklist

Walk this in the first session, owner + agent together.

1. **The tier sentence.** Write the one-sentence cost of a wrong answer
   into CLAUDE.md. Everything scales from it.
2. **Scope + anti-scope.** What it does; what it deliberately does not do
   (start the deferred list in DESIGN.md with reasons).
3. **DESIGN.md skeleton**: data model, core computation, primary sources
   (commit the authoritative PDFs/specs to the repo — page-addressable and
   immune to link rot), verification anchors plan, amendment log started
   at #1.
4. **Reference data.** Acquire at least one REAL input fixture from the
   actual workflow (a real drawing, a real dataset) before designing
   importers around guesses.
5. **Verification plan per phase**: which anchors, which independent
   recomputation, which boundaries get machine-enforced tests.
6. **Reviewer arrangement.** Confirm the independent adversarial reviewer
   (a different model/tool than the implementer) is available and
   scriptable; decide interim + closing gate points for the first build.
7. **Environment pins**: interpreter/toolchain versions verified against
   every planned dependency BEFORE the phase that needs them; record on
   CLAUDE.md. Repo located outside sync services that churn on build
   outputs.
8. **Process wiring**: test runner in all shipped modes; version literal
   single-sourced; generated-docs pipeline (if user-facing docs) with a
   drift-fails-the-build check; .gitignore for build outputs from day one.
9. **First milestone defined** as a walking skeleton of the riskiest
   computation with its anchors — not scaffolding, not UI.
10. **Working agreement**: the owner dumps context in bulk; the agent
    plans, asks its questions in ONE batch, then executes autonomously
    with status+ETA at milestones (see COLLABORATION.md).
