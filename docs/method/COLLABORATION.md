# Working with the owner

How the owner operates, and the defaults that have worked. For the agent
reading this at a new project's start.

## The owner's style

- **Bulk dumps, autonomous execution.** Requirements and feedback arrive as
  large unstructured dumps (often dictated — expect homophones and loose
  punctuation; read for intent). The agent's job: itemize the dump
  faithfully, plan, ask its questions in ONE batch, then work through
  everything without hand-holding. Do not dribble questions.
- **Always ask before building the plan.** The dump may not be complete on
  the first pass. After recon and clarifying questions — and BEFORE
  finalizing any plan — ask: *"Do you have any more questions or anything
  to add? Am I good to build the plan?"* and wait for the go. Building the
  plan before the owner has emptied his notes wastes a review cycle.
- **Latest supersedes.** Mid-stream feedback bursts are normal; when a later
  instruction contradicts an earlier one, the later one governs — no need
  to reconcile ceremonially, but record the change where decisions live.
- **Plan annotation is the steering surface.** The owner reviews plans by
  annotating selected text with short corrections. Make plans annotatable:
  concrete, decision-dense, with the agent's interpretation calls stated
  explicitly so they can be vetoed cheaply.
- **"Do what you think is best" is real delegation.** When granted, decide,
  and state the decision and its reason in the plan/commit — the owner
  vetoes at review rather than pre-approving.
- **Status + ETA.** At milestones and on request: what happened, what is
  running, what remains, roughly how long. Lead with outcomes.
- **Thoroughness is funded.** The owner prefers paying for verification
  depth (independent reviews, falsified regressions, live inspection)
  over shipping fast and wrong. Do not economize on correctness to look
  efficient.
- **The owner's live inspection is the highest-value test.** Rounds of
  polish come from the owner actually using the installed build. Make
  those hours count: before handing over, run the app yourself and sweep
  for visual problems, stale text, and mess; give the owner a short list
  of what changed and where to look.

## Session hygiene that has mattered

- Usage limits end sessions mid-flight. Keep clean committed boundaries;
  maintain a "where to pick up" block; on resume, assess the tree before
  building (partial agent work may be coherent — audit per deliverable).
- Verify subagent claims independently (test counts, exit codes, anchors).
- Batch heavy multi-agent phases early in the owner's usage window.

## A pattern worth continuing

Owner keeps a running feedback file while using the software, then dumps it
wholesale; agent turns it into an itemized round plan with per-item
interpretation calls; owner annotates; agent executes package by package
with gates. This loop has produced the best defect-yield per owner-hour.
