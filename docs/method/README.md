# Martin's Development Method — portable seed

This folder is the distilled working method from real projects (surveying/
civil engineering software built with Claude Code as session lead and Codex
as independent reviewer). Its purpose: start a NEW technical software project
without relitigating preferences and practices — and without handcuffing the
new project's agent.

## How to use on a new project

1. Copy this folder into the new repo as `docs/method/` (or keep it beside
   the repo and reference it).
2. In the first session, tell the agent: *"Read docs/method/METHOD.md before
   planning. It carries my standing preferences; adapt anything that doesn't
   fit this project and tell me what you adapted."*
3. Have the agent draft the project's own `CLAUDE.md` from
   `CLAUDE-TEMPLATE.md` and its own `DESIGN.md` skeleton per METHOD.md §2.
4. Walk `KICKOFF-CHECKLIST.md` together in the first session.

## The one rule about these rules

METHOD.md states **defaults, not law**. The new project's agent is expected
to exercise judgment: follow the defaults where they fit, propose deviations
where they don't, and RECORD the deviation and its reason in the project's
design log. A method document that must be obeyed verbatim is exactly the
"overpowering instruction" this package exists to avoid.

## Contents

- `METHOD.md` — the method: correctness tier, design authority, build
  process, verification doctrine, review gates, conventions, release.
- `CLAUDE-TEMPLATE.md` — skeleton for the new project's CLAUDE.md.
- `KICKOFF-CHECKLIST.md` — first-session checklist.
- `COLLABORATION.md` — how the owner works and how to work with him.
- `TOOLING.md` — machine-specific appendix (this Windows box, current
  stack): reviewer invocation, Word COM, shell traps, Qt traps,
  packaging. Ignore on other machines.
