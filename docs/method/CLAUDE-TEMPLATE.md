# CLAUDE.md — <project name>

<One paragraph: what this software is, who uses it, and the CORRECTNESS
TIER sentence — what a wrong output costs. This paragraph calibrates
everything below.>

**Read `docs/DESIGN.md` before any engineering change.** It is the design
source of truth; this file is the working summary. The standing method is
`docs/method/METHOD.md` — defaults, not law; record deviations in the
DESIGN.md amendment log.

## What it is

<Scope in a few sentences: what it does, what it deliberately does NOT do.>

## Status (<date>)

<Current state: last milestone, test count and modes, version, what is next.
Keep a "Next session — where to pick up" list current at every pause.>

## Repo layout

```
<core>/     <the domain core — state its purity/dependency rule>
<io>/       <readers/writers — name which module owns each external library>
<ui>/       <interface layer — never computes domain results>
tests/      <suite; every expected value hand-derived in a comment>
docs/       DESIGN.md (authority) + method/ + generated user docs
```

## Non-negotiable conventions (enforce in review)

- <Units/precision regime, stated once.>
- Fail closed, never fabricate; refusals name the offending item.
- One authoritative representation per fact; derived values are never
  also stored.
- One entry point per data path; loaders validate as strictly as the UI.
- No uncited constants.
- Exports never silently clobber; atomic writes.
- <Project-specific additions as they are decided — with amendment refs.>

## Development process

Work packages by subagents -> session lead independently re-derives
load-bearing logic before accepting -> independent adversarial review at
the build midpoint AND at closing -> fix loop with narrowing
re-confirmation until approved. Commit per gated milestone; push after
gates. Suite green in every shipped run mode before any commit.

## Environment notes

<Interpreter/toolchain versions, machine quirks, paths, anything a fresh
session would otherwise rediscover the hard way.>
