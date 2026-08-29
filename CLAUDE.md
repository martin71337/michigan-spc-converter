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

Since the 0.7.0 build it also converts on the **19 Michigan SPCS2022 zones**,
with NATRF2022 geodetic in and out — any-to-any **within** each datum.

It deliberately does **not** do UTM, the **NAD 83 ↔ NATRF2022 transformation**
(held on measured evidence, `docs/DEFERRED-NATRF2022-BRIDGE.md`), **NAPGD2022 /
GEOID2022 elevations** (`docs/DEFERRED-NAPGD2022.md`), other states, NAD 27, or
two-point azimuth/distance. See DESIGN.md §10, #61 and #62 for why each was
deferred; the two standing markers are the live ones.

## Status (2026-08-07, 0.3.1 RELEASED)

**0.3.1 removes three tooltips and nothing else** (DESIGN.md **#34**): the
longitude sign dropdown on **both** tabs (one shared control), the angle-format
selector, and both hemisphere letter boxes. Owner's instruction. Text was
removed, not information — the longitude control still names the convention, the
job record still states it, and `job.run` still refuses a geodetic job without
one. Suite **1132** green in both modes; all eight gates.

**This withdraws the tooltip mitigation #33 listed** for the positive-west
preselect, under #33's own ruling that verification is the user's
responsibility. #33 is annotated in place so the record does not cite a tooltip
that no longer exists.

**Trap worth remembering, recorded in #34:** the falsification seeding used
PowerShell `Set-Content`, which on 5.1 reads ANSI and writes UTF-8 **with a
BOM** — it silently added a BOM and mangled every em-dash in two source files,
and the suite stayed green because Python accepts a BOM. Caught by reading the
diff stat, not by a test. TOOLING.md's warning applies to throwaway seeding
commands too, where the diff usually goes unread.

## Current state: 0.7.0-dev — H1–H6 and N8 are DONE, ON MAIN, UNRELEASED (2026-08-29)

**Read `docs/PLAN-nsrs-modernization.md` (status block first) and DESIGN.md
#61 and #62 before touching this work.** The whole horizontal half of the
modernized-NSRS build is on `main`: the 19 SPCS2022 Michigan zones, three new
projection engines behind one dispatcher, per-frame geodetic entries, the
era-correct job record, and the packaging/self-test/release gates. Suite
**3,733**, green in `pytest` and `-O`, exit codes read unpiped. **NOT
RELEASED — the version literal is `0.7.0-dev` and nothing is tagged.**

**What a surveyor gets:** all 19 SPCS2022 zones (statewide Hotine oblique
Mercator, 13 LC1 and 5 TM low-distortion zones), native NATRF2022 geodetic in
and out, any-to-any **within** each datum, metres and international feet on
the 2022 zones (no US survey foot — NGS publishes none), and every factor on
every zone. SPCS 83 jobs are unchanged, held by the 18-digest cross-version
pin.

**Two halves are DEFERRED FUTURE WORK with standing markers, not dropped:**
`docs/DEFERRED-NAPGD2022.md` (elevations onto the modernized vertical datum —
NGS publishes no NAVD 88 ↔ NAPGD2022 product at all) and
`docs/DEFERRED-NATRF2022-BRIDGE.md` (**the frame bridge, held by the owner's
decision on measured evidence, DESIGN.md #62** — NGS publishes no
transformation parameters, and the best public candidate misses NCAT by 17 cm
at a re-probed, verified-real Michigan point). A cross-frame selection stays
selectable and **refuses loudly at Convert**, naming that fact; it never
passes coordinates through unchanged.

**The work packages, in the order they landed** (each built by an Opus
subagent to the lead's brief, diff reviewed and both modes re-run by the lead
before acceptance):

- **H1** — `projection.py` dispatcher (one table yields kind + engine +
  forward + inverse), `tm.py` (§3.2), `omerc.py` (§3.3, CENTRE variant — the
  natural-origin form is the ~6,969 km trap), `from_one_parallel`.
- **H2** — the 19 zone records on NGS's own polygon bounds, per-zone
  `allowed_units` and NGS-cited `easting_range_m`. **Interim Codex gate over
  H1–H2: FINDINGS, 2 MEDIUM 1 LOW, all test-layer, fixed at the root**; Codex
  died on quota during the narrowing re-confirmation and an independent Opus
  reviewer completed it (25/25 coefficient mutations caught, detection floor
  1.8 µm) — `review/gate-nsrs-h1h2/`, DESIGN.md #62.
- **H3′** — the frames registry mirrored from `vertical.py`: `FrameStatus`
  required, NATRF2022 USABLE, WGS 84 declared-not-usable,
  `FRAME_TRANSFORMATIONS` identity-only with a `__post_init__` that refuses a
  non-identity record, `require_frame_path` replacing `require_same_frame` at
  both call sites.
- **H5** — `report._zone_block` dispatches per projection kind (the 2SP block
  byte-identical to 0.1.0's, pinned as frozen literal text); the METHOD and
  verification prose has an era branch; **`docs/REFREEZE-NSRS.md` and its
  two-way inventory test** close #61's obligation.
- **H6** — the modernized system reaches the screen: the `GEODETIC` string
  sentinel is gone, a frozen `GeodeticChoice` per offered frame, four combos
  offering 26 items, per-zone unit filtering, the cross-frame refusal pinned
  end to end on both tabs.
- **N8 (this session)** — packaging, self-test and the release gate:
  - **Self-test checks 10 and 11.** The frozen bundle now converts one
    SPCS2022 point through the public path (`convert.project_point`, zone
    261008) against a frozen beta-NCAT anchor, and proves the **cross-frame
    refusal is alive in the bundle** in both directions. Eleven checks; the
    printed count derives from `len(CHECKS)`.
  - **The LAZY_IMPORTS audit is now a mechanism, not a reading**: a test walks
    every `michspc` module with `ast` and requires each module imported inside
    a function body to be declared. It found two undeclared —
    `michspc.fileio.exports` and `michspc.spc.projection`.
  - **The beta-acknowledgement release gate exists** (the promise
    REFREEZE-NSRS.md recorded): gate 2 of **nine**, scanning `michspc/**` and
    `tests/fixtures/**` for the literal `NGS beta` and refusing unless
    `--acknowledge-ngs-beta` is passed; the flag prints every artifact it
    acknowledges and `SHA256SUMS.txt` records the acknowledgement. The build
    tool reimplements the inventory test's scan (a tool must not import
    `tests/`) and the two scanners are pinned against each other.
  - **`michspc/selftest.py` now carries the `NGS beta` token and a
    REFREEZE-NSRS.md row of its own** — it transcribes a beta anchor into
    shipped code, so re-freezing the fixture without it would leave the bundle
    checking itself against a superseded number. Five tagged artifacts, not
    four.
  - `docs/RELEASE-NOTES-0.7.0.md` is a marked **DRAFT**.
- **The closing Codex gate RAN over the whole build: FINDINGS — one HIGH, two
  MEDIUM, one LOW, no CRITICAL** (`review/gate-nsrs-closing/output.txt`). All
  four are fixed at the root, each pinned at the reviewer's own input and
  falsified by seeding (11 seeds, all caught). Three were production defects
  the 2022 zones made reachable, and all three are now REFUSALS:
  - **HIGH — an ELLIPSOID (GNSS) height on a NATRF2022-frame job mixed
    realizations inside `H = h - N`.** The hybrid geoid models publish N
    against NAD 83; the two ellipsoids are **1.115 m** apart at the frozen
    anchor, and the reviewer's vertical-only job at zone 261008 escaped
    231.970 m NAVD 88 where the answer is 233.085 m. New settings gate,
    `_require_a_convertible_ellipsoid_height_frame`, fires before the file is
    read. **ORTHOMETRIC jobs on 2022 zones are untouched and still convert** —
    that path's ~0.175 ppm is the owner-accepted fact of #61, pinned as a
    control so the gate cannot widen into it.
  - **MEDIUM — `VERTICAL_ONLY` geodetic jobs skipped the frame gate**, so a
    WGS 84 job certified 199.85980355739594 m and a record naming WGS 84. The
    gate now asks the frame against ITSELF for that direction (the identity
    lookup: usable, and registered — and there is deliberately no WGS 84
    identity).
  - **MEDIUM — a zone field the direction never reads created a false record**:
    `GEODETIC_TO_ZONE` ignored a stale `source_zone` while the record printed
    it as a FROM block and called the job an exact re-projection. Both
    directions now refuse the stray field by name. Both GUI tabs already
    assembled settings cleanly (`isinstance(..., Zone)`), and no test was
    passing a stray field.
  - **LOW — self-test checks 10+11 did not jointly cover the PUBLIC gate**: a
    no-op `convert.require_frame_path` passed both. Check 11 now refuses
    through `convert.project_point` and keeps the registry call as its second
    assertion.

### What remains, in order

1. **A narrowing re-confirmation of the closing gate** (Codex, or an Opus
   reviewer under the owner's standing quota fallback) over these four fixes.
2. **The owner's screen review of both tabs.** He has seen none of H6's
   controls on a real screen; layout decisions are flagged in H6's work
   record and nothing there is final until he has.
3. **The release build, on his machine**: drop the `-dev` marker, then
   `py tools/build_release.py --acknowledge-ngs-beta` (gates 5 and 7 are
   PyInstaller and Inno Setup, Windows-only), then tag and the GitHub
   Release. **The flag is required and is the point** — a beta-era release is
   a conscious act.
4. **Still human, still outstanding:** the clean-profile install proof
   (METHOD.md §6) and a real PNEZD file from an actual job.

**Process (owner's instruction, clarified 2026-08-28): the session lead
develops all plans and designs; Opus subagents do recon and build; the lead
reviews every diff and re-derives the load-bearing math; Codex gates — two
interim, one closing, none skipped.**

## Superseded status: the modernized-NSRS build in flight — H0-H2 (2026-08-28/29)

**Read `docs/PLAN-nsrs-modernization.md` (status block first) and DESIGN.md
#61 before touching this work.** The owner approved the build 2026-08-28:
the 19 SPCS2022 Michigan zones, NAD83(2011)⇄NATRF2022 at fixed NGS epochs
(2010.0→2020.0), any-to-any across all 22 zones + geodetic on either frame,
2022 zones restricted to metres + international feet — released ahead of
NGS's official ~Q1 2027 rollout, every beta artifact capture-dated with a
committed re-freeze obligation (`docs/REFREEZE-NSRS.md`, arrives with the
first beta artifact in code).

**The vertical half is DEFERRED FUTURE WORK, not dropped —
`docs/DEFERRED-NAPGD2022.md` is the standing marker**: every reason measured
and documented, the reopen conditions listed, the designs waiting. Scale
factors (grid, elevation, combined) all still work on every zone including
the 2022 zones — only conversion TO the new vertical datum waits on NGS.

**H0/N0 is DONE and committed** (`review/nsrs-n0/`, DESIGN.md #61): all 19
zone definitions captured and digest-pinned; beta NCAT performs the frame
transformation (web app only — NO REST API accepts NATRF2022 tokens; the
form-driving harness is committed) and emits SPCS2022 coordinates for all
three projection kinds; EPP2022 frozen. **The v3 NCAT engine is NOT
published** (ncat-lib is the 2021 legacy engine; HTDP has no NATRF2022) —
H3's oracles are the frozen beta NCAT anchors + NOAA TR NOS NGS 63, with
HTDP's NAD83↔ITRF Helmert constants as the citable candidate set, and a
**rotation-sign-convention conflict (~0.4–0.9 m) that a discriminating
anchor must settle before any H3 code is accepted** (#61 annotation). **The vertical half (NAPGD2022 /
GEOID2022 / chained NGVD29) is DEFERRED by the owner** — N0 proved NGS
publishes no NAVD88↔NAPGD2022 product at all; the reasons and the future
path are in #61. **Hazard: beta's REST API fails open** (`200 OK` with
`N/A`/`{}`) — legacy truth from geodesy.noaa.gov only.

**Process (owner's instruction, clarified 2026-08-28): the session lead
develops all plans and designs; Opus subagents do recon and build; the lead
reviews every diff and re-derives the load-bearing math; Codex gates — two
interim, one closing, none skipped.** Work packages H1–H6 per the plan. **H1 IS DONE**
(2026-08-29): `projection.py` dispatcher (ProjectionKind finally read, table
derives kind and engine together), `tm.py` (§3.2), `omerc.py` (§3.3 + the
CENTRE-variant u_c offset — the manual's natural-origin form is the ~6,969 km
trap, discriminated by the frozen centre anchor), `from_one_parallel`,
convert/report routed through the dispatcher bit-identically. Suite
**1696 → 2593**, both modes, lead-verified unpiped; all 63 anchors inside
NCAT's printed quantization (worst N/E 4.994e-4 m), 19 origins bit-exact,
round-trips 2.7e-11°; five falsification seeds all caught, snapshot-restored.
**Two facts for the next packages:** (1) the frozen lattice alone cannot see
a high-order TM series defect (A4/A6 swap = 1e-4 m at the anchors) — the
finite-difference γ/k test is the pin that catches it; raise at the interim
gate. (2) `report._zone_block` still hard-codes the 2SP wording and fields —
**H2 must not let 2022 zones reach the dropdowns before H5 rewrites it**
(build the combos from SPCS83_ZONES until H6 flips them, pinned).
**H2 IS DONE** (2026-08-29, suite → 3478, version 0.7.0-dev): the 19 zone
records on NGS's own polygon bounds (`zoneBounds.json`, an N0 supplement),
per-zone `allowed_units` and NGS-cited `easting_range_m`, era tuples with
derived `ALL_ZONES`, uniqueness + bracket import checks, the GUI gated to
SPCS83_ZONES until H5/H6. **The interim Codex gate over H1–H2 ran:
FINDINGS (2 MEDIUM, 1 LOW, all test-layer), fixed at the root** — the real
disease was a `max()` collapsing two series' residuals; component-wise
pins + an inverse-Jacobian test per engine now catch the reviewer's seeds
(suite → 3490). Codex died on quota during the narrowing re-confirmation;
the owner's standing fallback (Opus reviewer) completed it — verdict in
`review/gate-nsrs-h1h2/`.

**THE FRAME BRIDGE IS HELD (owner's decision 2026-08-29, DESIGN.md #62,
`docs/DEFERRED-NATRF2022-BRIDGE.md`):** NGS publishes no transformation
parameters; the best candidate misses NCAT by 17 cm at a verified-real
point. Cross-frame refuses naming that fact. H3 reduces to the
frames-registry restructure (identities only, NATRF2022 usable for
same-frame work); helmert.py and the two-pivot PointConversion defer with
the bridge.

Next: **H3′ frames registry**, **H5 disclosure rewrite** (report per-kind
zone blocks + era-correct prose — the gate before any 2022 zone reaches a
dropdown), **H6 GUI** (per-frame geodetic entries, unit filtering, zone
list opens), **N8 packaging/self-test/release-gates**, closing Codex gate,
then 0.7.0 on the owner's machine after his screen review.

## Superseded status: 0.6.4 — new application artwork (2026-08-26)

**0.6.4 carries #60 only, and it is artwork.** The compass rose that had been
the icon since 0.1.0 is replaced by a survey monument — ring, crosshair, amber
centre — with two arc arrows turning around it. The owner picked it from three
candidates shown at 16/32/48/128 px, reduced through the build's own
`resample_area` so the comparison was of what Explorer receives. **No
computation changed**; suite **1696** green in both modes, and the
cross-version digest pin is what establishes that no number moved.

**The #15-note-1 invariant was deliberately not renegotiated.** The new artwork
was drawn by a script, but `assets/icon/mcx-1024.png` remains the single
authoritative representation and the `.ico` stays derived. The drawing script
is NOT committed, on #24's precedent — its derivation script was a one-shot
too, and committing a tool that regenerates the master would create the second
representation §7 forbids.

**One caveat worth reading before the next artwork change (#60):** the edge pin
in `tests/test_icon.py` wants >1,000 partially transparent pixels. The old
master had 8,205; this one has **1,536**, because the tile's straight sides
land on integer pixel boundaries and only the corner arcs are anti-aliased. It
passes and the property is intact, but the margin is no longer generous —
measure it, do not assume it.

**Still human, still outstanding:** the clean-profile install proof
(METHOD.md §6) and a real PNEZD file from an actual job.

## Superseded status: 0.6.3 — every geodetic selection names the datum (2026-08-11)

**0.6.3 carries #58 only.** The geodetic entry in all four zone dropdowns now
reads **NAD83(2011) geodetic (latitude / longitude)**. The owner's reasoning:
NAD 83 is not WGS 84 — a metre or more apart in CONUS, boundary-moving by this
project's own tier sentence — and a handheld's WGS 84 position pastes in
cleanly and converts to something plausible and wrong. The label is DERIVED
from `NAD83_2011.code`, so it follows the mathematics and renames itself when
NATRF2022 arrives, which is the second half of what he asked for.

**FIELD VALIDATION IS DONE (DESIGN.md #59).** The owner reports running real
jobs end to end with no issues (2026-08-11) — the longest-standing open item
in this record, carried unmet from 0.1.0 through 0.6.3, is closed. Two
qualifications recorded rather than assumed: he did not say whether a
CLEAN-PROFILE machine was among those tested (the half of METHOD §6 an
installer defect would hide behind), and a real PNEZD file from an actual job
is still not committed as a fixture — now a nice-to-have rather than an open
risk, since jobs running clean is strong evidence the reader's convention
matches reality.

## Superseded status: 0.6.2 — the owner's layout round ships (2026-08-11)

**0.6.2 carries #57 only: interface, no computation.** A grey italic hint in
the Single point elevation box, HORIZONTAL ONLY (#51's rule applied to a
placeholder, which is more prominent than the tooltip #51 removed); three
paired rows compacted onto single lines, fourteen grid rows to eleven; the
Multi point geoid grayed when no elevations are read; and the elevations note
reworded to "used for combined scale factor".

**One defect produced and caught in the same round:** the first graying wrote
`setEnabled(vertical or elevations)` and re-enabled a combo the per-datum
filter had deliberately grayed — two methods driving one property. #50's own
pin caught it; the rule now only ever disables, and only in horizontal mode.

**Still human, still outstanding:** the clean-profile install proof
(METHOD.md §6) and a real PNEZD file from an actual job.

## Superseded status: 0.6.1 — the owner's wording edit ships (2026-08-11)

**0.6.1 carries #56 only: text removed, no calculation touched.** The
"(elevation)" and "(GNSS)" glosses are gone from the height selector and the
horizontal elevation heading. The removal exposed that the panel's computed
`Ellipsoid height (m)` row holds the SAME NUMBER as the supplied height on a
GNSS job — `(h − N) + N` is `h` — so the qualifier had been distinguishing a
value from itself; the row is dropped on those jobs and untouched on ordinary
ones. A vacuous wording pin was found and fixed in the same round (the LOW-3
class, recurring in a test written after the gate that named it).

**Flagged and left for the owner:** the audit CSV carries both
`Ellipsoid height` (the Z, output unit) and `Ellipsoid height (m)` (computed,
metres) — two distinct strings, same number on a metres job.

**Still human, still outstanding:** the clean-profile install proof
(METHOD.md §6) and a real PNEZD file from an actual job.

## Superseded status: 0.6.0 — ellipsoid (GNSS) height input ships (2026-08-11)

**0.6.0 carries #54 (the feature) and #55 (its closing gate).** The gate ran
under Codex over `v0.5.0..HEAD`: **one HIGH, one MEDIUM, one LOW, no
CRITICAL**, all fixed and pinned before the tag. The HIGH was h escaping into
a field labelled H on two horizontal surfaces — one of the three decisions #54
had recorded as the session lead's and open to review; the review took it and
it was wrong. The gate's negatives are worth keeping: the `_convert_row`
invariant holds, no accepted configuration produced a wrong height or factor
across the full matrix, and no refusal could be bypassed.

**The owner asked that the release read as a finished product**, not a work in
progress — the release notes say so, and say that future releases are
additions as NGS publishes data rather than further construction.

**Still human, still outstanding:** the clean-profile install proof
(METHOD.md §6) and a real PNEZD file from an actual job.

## Superseded status: ellipsoid-height input ON MAIN, unreleased (2026-08-11)

**The owner's feature: the Z column may hold GNSS ellipsoid heights
(DESIGN.md #54).** H = h - N, with the mode deciding only what is WRITTEN:
horizontal passes the Z through unchanged (his instruction) and only fixes
the factors; the two vertical modes write the derived elevation. The factor
fix is the part that matters beyond convenience — R/(R+H+N) was adding the
separation to a height that already contained it, **~5 ppm, measured at 5.9
ppm**, a third of a foot in ten miles, always long. Selector defaults to
Orthometric so every existing job is unchanged. Three refusals, including
ellipsoid-plus-geoid-change (the input model cancels out, so the record would
state a conversion FROM a model the height was never on).

**The design review earned its keep twice, both before any code shipped:** the
approved plan wrote to the wrong variable and would have been overwritten by
the identity branch — the feature silently doing nothing on its flagship job —
and the ELEVATIONS section would have blamed a missing VERTCON grid on an
identity job that loads none.

**Anchors:** 14 NGS published Michigan benchmarks carrying both heights,
frozen with their raw capture; our reader matches NGS's separations to 0.75 mm
worst. 19 falsifications across five work packages. Suite **1681**, both
modes. **WP-E1..E5 done; the Codex gate is next, then the owner's screen
review and a release.**

**IGLD 85 is DEFERRED with its reasons recorded (DESIGN.md §10):** the
hydraulic corrector grids are not published, NGS's tool returns out-of-bounds
inside Michigan, and the Michigan statute is IGLD **1955** anyway. Revisit
when IGLD 2020 lands with NAPGD2022.

## Superseded status: 0.5.0 — per-side geoid selection and geoid-to-geoid conversion ship (2026-08-11)

**0.5.0 carries #50, #51, #52 and the gate's fix #53.** The closing gate ran
under **Codex** over the whole `v0.4.0..HEAD` range, at the owner's
instruction after he reversed his own "no review" answer mid-session:
**verdict FINDINGS, one MEDIUM, no HIGH, no CRITICAL**, and the MEDIUM was a
crash the session lead had already found from the same diff and fixed —
`GEOID_UNAVAILABLE` naming `settings.geoid_model.name` when #50 made the
factors grid come from the INPUT side, so a NAVD 88 → NGVD 29 job (the GUI's
own default for that pair, output selector grayed to None) died on
`AttributeError` at any point off the geoid tile. Fails closed, so no wrong
coordinate — but the whole job, not the one point. Fixed at the root, pinned
at the reviewer's input and expected elevation, falsified. Codex's
independent negatives are worth keeping: no wrong in-coverage elevation, no
sign reversal, no double swap, no wrong-era factor, no stale clipboard path,
no false written disclosure. Suite **1609**, both modes.

**Still human, still outstanding:** the clean-profile install proof
(METHOD.md §6) and a real PNEZD file from an actual job.

**A geoid-to-geoid elevation now names its geoid on screen (DESIGN.md #52),
the owner's instruction:** `Elevation (NAVD88, m) (GEOID18)` — the model in a
parenthesis after the units, both ends naming their own model, screen only
(the audit CSV and the record already said it). Only where a swap actually
ran: not on a modeled datum shift, not on same-model identity, because a
leveled height does not depend on the hybrid model (#50). The heading and the
panel label are now ONE template, where they were two f-strings producing the
same text. Suite **1608**, both modes.

**Before that, the owner found a false tooltip on the real screen (DESIGN.md
#51), removed with no cross-check on his instruction:** the Single point
elevation field called the elevation *optional* in all three modes, because
the tooltip was set once when the field was built — false in Horizontal +
Vertical and in Vertical, where the elevation is the value the job exists to
convert. Deleted outright rather than made mode-dependent (#34's ruling; #48
hid the analogous Multi point row instead, and #51 says why the two differ).
That was the third and last horizontal-era sentence on either tab. **What it
costs, recorded not mitigated:** the Single point tab no longer says in words
that a blank or exactly-zero elevation means "not recorded" — behaviour
unchanged, still pinned, and the panel shows the N/A itself. Suite **1605**,
both modes.

**Before that, the owner's geoid round landed (DESIGN.md #50), gated
without Codex on his instruction:** vertical jobs choose the input and
output geoid separately; a same-datum job with two different models converts
by H_out = H_in + (N_in − N_out) with the ellipsoid height held fixed
(pinned at the Houghton anchor from BOTH frozen fixture sets: 200.000 under
GEOID12B → 199.968 under GEOID18); each side's selector grays when its
datum has no matching models (NGVD 29 today, crosswise models when
NAPGD2022 arrives); the per-side factors rule supersedes #41's
either-endpoint by generalization, every old shape bit-identical. **No
disclaimers on any user surface (owner's instruction): the record's GEOID
CHANGE block is facts only — models, digests, arithmetic — σ is bare N/A,
and the ABSENCE of caveat prose is pinned.** The leveled-vs-GNSS geodetic
fact lives in #50's record, not in outputs. Suite **1604**, both modes.
The Input/Output geoid controls have not been seen on a real screen.

## Superseded status: 0.4.0 RELEASED (2026-08-09) — vertical datum conversion ships

**0.4.0 is built, gated and tagged (DESIGN.md #49):** all eight gates, suite
**1565** both modes, frozen self-test **8/8** including the vertical NCAT
conversion and GEOID12B through the registry, installer + SHA256SUMS on the
GitHub Release. Ships everything of #35–#48: NGVD 29 ⇄ NAVD 88 with
per-point σ in the input unit, the vertical-only mode, the geoid registry
(GEOID18 + GEOID12B), the GEOID18 re-anchoring, the disclosure surfaces,
and the two inherited fixes (#39 copy glyph, #43 longitude-convention stale
result). **Still human and outstanding: the clean-profile install proof
(METHOD.md §6) and a real PNEZD file from an actual job.** Next builds:
NAPGD2022 as registry data when NGS publishes (#32); SPCS2022 downstream of
it (#21). Caveats worth re-reading first: #38 half-cell steps, #36
negative-σ, #44/#46 carried LOWs.

## Superseded status: vertical feature + owner's round on main, pre-release (2026-08-09)

**Two owner instructions landed after the closing gate, both gated (#45,
#46):** the Vertical method caveat row is REMOVED from the results panel
(the removal itself is pinned; the record still carries the caveat on every
written job), and a THIRD MODE — **Vertical** — exists on both tabs: input
horizontal system only (zone or geodetic), no output system, only the datum
shift runs, and the export mirrors the import except the elevations (pinned
bit-for-bit at the gate over 45 written-archive configurations). The gate's
two substantive finds, both fixed at the root: a false record sentence (the
#42-finding-3 class recurring when `Factors.grid_scale_factor` became
optional), and `verify_round_trip`'s half-place tolerance refusing whole
archives on ordinary metre northings in this mode — the verifier now
compares EXACTLY against the writer's own rendering, strictly tighter for
every direction. **A third owner instruction followed (#47): shift and σ
display in the job's INPUT unit (internals stay metres; one formatter, one
heading authority shared by panel/table/CSV), and datum-tagged elevation
labels carry their units. A fourth (#48): the Multi point Elevations row
hides in both vertical modes, a visible factors note joins it in
Horizontal, and its tooltip claims only what is true — cross-checked under
CODEX (quota restored), which also re-confirmed the #45–#47 owner round
independently and proved the #46 round-trip-verifier change strictly
stronger.** Suite **1565**, green in both modes. NOT RELEASED; the owner
has seen none of the new controls on a real screen.

**Every work package is built, interim-gated, and the whole feature passed
its closing gate (DESIGN.md #44) — run on an independent Opus reviewer
because Codex refused on quota, per the owner's standing fallback; a Codex
re-confirmation after the reset is the owner's option.** The closing
reviewer's own 1,113-configuration elevation sweep against the frozen NCAT
anchors found zero wrong elevations and zero unconverted heights escaping as
converted; its three pin-gap/wording MEDIUMs are closed and falsified. Suite
**1506**, green in both modes; the frozen self-test passes 8/8 including a
vertical conversion against NCAT.

**NOT RELEASED — 0.3.1 remains the released version; the version literal has
not moved.** `docs/RELEASE-NOTES-0.4.0.md` is a marked DRAFT. **Before any
release, the owner:** (1) looks at both tabs on a real screen (#43 has the
layouts; the Vertical method caveat row's wording is his to adjust, #42);
(2) the clean-profile install proof (METHOD.md §6); (3) optionally a Codex
re-confirmation; (4) the release itself — bump, `py tools/build_release.py`,
tag. A real PNEZD file from an actual job is still worth having.

**After this feature:** NAPGD2022 arrives as registry records when NGS
publishes (backwards compatibility is a requirement, #32); SPCS2022 stays
downstream of it (#21). The known caveats worth re-reading before then:
#38's half-cell steps, #36's negative-σ refusal, #44's carried LOWs.

**WP-V8 is DONE (DESIGN.md #43): vertical mode is reachable from both tabs**
— mode toggle (opens Horizontal), datum dropdowns (open unanswered, usable
registry only), geoid dropdown (ALL_GEOID_MODELS, no "none") on both tabs,
Multi point table with datum-named Elevation heading plus shift/σ columns
pinned cell-for-cell against the audit CSV in both directions. **The gate
found a CRITICAL that shipped in 0.1.0 and survived #26's own fix: the
longitude sign dropdown never invalidated a displayed result** — stale
northing 9,756,797 m out, one click from the clipboard; fixed, pinned,
falsified, #26 annotated in place. Suite **1503**. Remaining: **WP-V9**
(frozen self-test converts one vertical point; build gates; release notes;
closing gate over the whole vertical feature), then the owner's release
review. The tab layouts are described in #43 — THE OWNER HAS NOT SEEN THEM
on a real screen.

**WP-V7 is DONE (DESIGN.md #42): every surface discloses the vertical
conversion.** Job record (datums, quoted direction statement, both digests,
NGS's supersession caveat, the half-cell step, σ summary with σ>|shift|
points named), audit CSV (six vertical-only columns incl. Geoid model),
Single point panel (datum-labelled elevations, shift, σ with copy button in
Copy all, and the **Vertical method caveat row** — the gate's HIGH: the tab
writes nothing, so the caveat must be on screen). Negative σ: N/A on every
surface, never a number, warned via `VERTICAL_SIGMA_UNAVAILABLE`; the raw
figure lives only on the reading's reason field, off every output.
Horizontal outputs byte-identical (27/27 members vs HEAD at the gate).
Suite **1474**. **The #41 sequencing constraint is satisfied — WP-V8 may
make vertical mode reachable.** V8's scope now ALSO includes the Multi point
on-screen table (datum in the Elevation header, shift and σ columns,
mirroring the audit CSV — #42 finding 4).

**WP-V6 is DONE (DESIGN.md #41): the vertical shift is wired into `job.run`**
— `VerticalMode` (default HORIZONTAL, byte-identical to before, proven 15/15
output digests against a HEAD worktree), shift before geoid lookup before
factors (pinned), `VerticalReading` on every shifted point, coverage-refused
points keep their horizontal result and refuse the elevation, the full
refusal matrix, and NCAT anchors green through real files end to end. The
gate's substantive decision: **the geoid guard is either-endpoint (#41,
superseding plan §3.5)** — factors come from the height in the geoid model's
own era, so NAVD88 → NGVD29 works and no accepted configuration mixes eras.
**Sequencing constraint from the gate: WP-V7 (disclosure) MUST land before
WP-V8 (GUI)** — vertical mode is currently reachable from no interface, and
must not become reachable before the outputs state the datum, the shift and
NGS's caveat. Suite **1441**.

**`main` carries the vertical work through WP-V5 plus WP-G1, all gated. Suite
1397, green in both `pytest` and `-O`. NOT RELEASED — 0.3.1 is still the
released version, the version literal has not moved, and the owner reviews
before any release is cut.** Read DESIGN.md **#36–#40** before touching this
work; the plan (`docs/PLAN-vertical-datums.md`) remains a proposal whose
§2.5a/§7/§8 carry supersession annotations.

**WP-V5 is DONE (DESIGN.md #40), two commits as the plan required:** the
`geoid18.py` → `geoid.py` rename (pure, byte-identical content), then the
`GeoidModel` registry — GEOID18 and GEOID12B records carrying name, tile,
digest, geometry, vertical datum and citation as THE authoritative
representation; `apply_geoid: bool` → `geoid_model: GeoidModel | None` (None
= "no geoid applied", a core capability no interface offers); GEOID12B
genuinely read and gated by 20 NGS anchors captured live before the code
existed (`tests/fixtures/geoid12b_anchors.py`, provenance in
`review/wp-v5-geoid12b/`, 18 of 20 discriminate the models at NGS's printed
mm — the anti-swap pin, falsified with a swap that passes both authentication
gates); the latent `require_geoid_matches_datum` guard (#32's two-eras rule,
wired at V6); the bundle self-test reads GEOID12B through the registry; the
spec and release manifest derive from the registries. Gate verdict MERGE:
GEOID18 output proven byte-identical across five job configurations, all
findings closed in #40.

**Also fixed on main (DESIGN.md #39): the copy glyph was cut off on every
scaled display** — the device pixel ratio was stamped on the pixmap before
painting, so the scales compounded; invisible at 100% and on the offscreen
test platform (the #31 class). Fixed, pinned by byte-identity across ratios,
falsified.

**This session (the merge session) did, in order:**

1. **Two independent Opus reviewers ran blind over the whole branch** (the
   owner's fallback rule when Codex is unavailable), one on numerical
   correctness, one on contracts/tests/regression. No CRITICAL. Everything
   load-bearing re-verified independently — the reader is bit-identical to
   NOAA's published `Vertcon.java` over the whole CONUS grid, the WP-V2
   extraction is behaviour-identical to `origin/main`, sign/round-trip exact,
   anchors non-circular (10 of 120 re-queried live against NGS, identical).
   Full record: DESIGN.md **#38**.
2. **WP-G1 executed** (DESIGN.md **#37**): `geoid_height` now reads the
   nearest-node (INTG) stencil. The work was the anchors —
   `tests/fixtures/geoid_discriminating_anchors.py`, 120 NGS truths, 36
   discriminating exactly; all pins falsified by seeding the floor stencil
   back. Worst change to a reported separation ~7 mm (Michigan window);
   no coordinate moves.
3. **The gate's findings fixed at the root** (#38): the released
   `default_grid`'s authentication wiring is now pinned; the vertical
   registry's import guard is pinned by AST so it cannot be deleted silently;
   **the frozen bundle self-test now authenticates all four NGS grids** and
   `LAZY_IMPORTS` declares `ngs_grid`/`vertcon`/`vertical` (they were
   invisible to PyInstaller — the installer would have shipped VERTCON data
   with no reader in the bundle); DESIGN.md's body §3/§9 updated to the
   four-grid reality; `shipped_data_directory` extracted to the substrate.
4. **One HIGH, resolved as disclosure, not repair** (#38): the nearest-node
   stencil is **discontinuous at half-cell lines** — up to 75.6 mm in the
   `.trn` shift at 41.975 N / −83.935 W, ~6 mm in the re-anchored geoid —
   and **NCAT prints the same step** (queried live, both sides). It is NOAA's
   own behaviour, replicated on the owner's instruction; smoothing it would
   diverge from the authority. Pinned executable with NGS truth frozen on
   both sides. **WP-V7 now owns TWO disclosure decisions: the negative σ and
   this.**

### Resume here, in order

1. **WP-V6** — `job.py` wiring: vertical shift before geoid lookup (plan
   §3.6), datum-tagged elevations, the four refusals, and wiring
   `geoid.require_geoid_matches_datum` in. Notes from the gates: `to_east_longitude`
   accepts 0–360 east longitudes silently — the file layer must settle the
   accepted range before these readers see a CSV's longitude (#38); a
   non-registry `geoid_model` now refuses in `job.run` before converting
   (#40).
2. **WP-V7** — the disclosure package, owner's decisions: negative σ
   presentation, the half-cell discontinuity (#38), AND whether `_full.csv`
   names the geoid model beside `Geoid height (m)` — model-dependent since
   V5, 32 mm between the models at the Houghton anchor (#40). `reading_at`'s
   `sigma=None` needs a distinguishable signal by then (#38).
3. **WP-V8** — GUI: mode toggle, geoid dropdown (GEOID18 + GEOID12B, no
   "none"), both tabs. The registry's `ALL_GEOID_MODELS` is the dropdown's
   source, in declaration order.
4. Then V9; closing gate under Codex, or independent Opus reviewers if
   Codex usage runs out (owner's instruction, 2026-08-07).

**Still human, still outstanding:** install on a clean profile and run one
real job end to end (METHOD.md §6); a real PNEZD file from an actual job.

## Superseded status: vertical datums — V0–V4 DONE, V5+ NOT BUILT (2026-08-07)

**Branch `claude/vertical-transformation-plan-dtxh6j`. Read
`docs/PLAN-vertical-datums.md` and DESIGN.md **#35** before touching this work.**
The plan is still a proposal; DESIGN.md's body is unchanged and #35 records what
was built against it.

**Built, gated, committed, pushed — a clean boundary, nothing half-done:**

- **WP-V2** `michspc/fileio/ngs_grid.py` — the substrate `geoid18` and the coming
  `vertcon` share. `geoid18.py` is now policy over it: filename, checksum,
  geometry, interpolation choice, and the wording of every refusal, handed down
  in a `GridDialect` that also carries the exception class (`job.py` catches
  `GeoidError` by name, so a refusal from the substrate must *be* that class).
  **Proved behaviour-identical**, not assumed: 37 refusal scenarios
  character-identical, check order unchanged under 8 double-violating inputs,
  both interpolators bit-identical (max diff exactly **0.0**) over 200k random
  positions and 3,600 Michigan positions on the real tile.
- **WP-V3** `michspc/spc/vertical.py` — datums, the `(source, target)` registry
  with both identities as explicit records, two distinct refusals, `apply_shift`.
  Stdlib only; the grid value is a parameter, as `factors.factors_at` takes N.
  The sign was re-derived against #22's live NCAT anchor before acceptance:
  200.000 m NGVD 29 at 43.0 N/84.5 W → 199.860 m NAVD 88, so `sign = +1` and the
  inverse is the same grid at −1, round-tripping exactly.

**Suite 1132 → 1223**, green in `pytest` and `-O`. Review gate found 1 MEDIUM
(a `Zone`/`ReferenceFrame`/`LinearUnit` duck-typed into `require_vertical_pair` —
**#11 finding 1 recurring**) and 2 LOW; all fixed at the root, pinned with the
reviewer's own counterexample, every pin falsified.

### WP-V1 AND WP-V4 ARE NOW BUILT TOO — the block was the container, not the work

The previous session recorded V1 as impossible because `geodesy.noaa.gov` is
refused by the container's egress policy. **Run on the owner's Windows machine,
NOAA is reachable**, and everything that block implied dissolved.

- **WP-V1 DONE.** All three files of plan §2.1 downloaded; **every SHA-256 matched
  the pin**, so the committed files are byte-identical to what V0 measured.
  `michspc.spec` names every grid and derives `datas` from that list;
  `build_release.py` compares the built bundle against `data/` rather than one
  hard-coded name. `installer/michspc.iss` needed no change (it copies the bundle
  recursively) but its comment no longer claims the geoid tile is the only data
  file. **GEOID12B is checksum-pinned in `geoid18.py` and checked**, though
  nothing reads it until V5 — it had *no* executable check until the V4 gate.
- **The 20-point lattice is a RECREATION, not the original**, and
  `tests/fixtures/vertcon_anchors.py` says so. The V0 scripts and coordinates
  were lost with that scratchpad. It was seeded with every position the plan does
  record so the recreation could be *checked* against V0, and all six reproduce —
  including the five-point inverse set, matching §2.4 to the last printed digit
  and summing to exactly 0.000 m. **Two figures are NOT reproduced**: §2.5's
  Kalamazoo and Lansing σ are at coordinates V0 never recorded.
- **WP-V4 DONE** — `michspc/fileio/vertcon.py`, reviewed under Codex, all findings
  fixed and every pin falsified. See **#36**.

### The finding that changed the plan, and the one still open

**Plan §2.5 is superseded (§2.5a).** It said `.trn` is biquadratic and `.err`
bilinear, and asked for a pin that fails if the two are unified. **That pin would
have enshrined a defect.** `ngs_grid.interpolate_biquadratic` anchors its 3×3
stencil at `int(row) - 1`, off-centre; both VERTCON grids want it centred on the
nearest node. Then both are biquadratic and both land at **0.47 mm** against NCAT,
20/20 exact, where the old scheme reaches 8.46 mm. **Verified bit-identical to
NOAA's own published algorithm** — `Vertcon.java`'s `getGridRow` transcribed
literally, max difference exactly 0.0 over 18,000 positions.

**DESIGN.md #8 is corrected.** It said NGS does not document INTG's scheme. NGS
does: NOAA TM NOS NGS-84, and `intg.f` anchors with `nint()` — nearest node. So
**GEOID18's anchoring is not INTG's**, a claim three docstrings and the 0.1.0
release notes carried.

**OWNER'S INSTRUCTION, 2026-08-07: replicate NOAA as closely as possible, they
are the authority.** That decides the open question — **GEOID18 is to be
re-anchored to nearest-node**, as its own work package, because it touches
released code and needs its own discriminating anchors (the existing 20 cannot
tell the schemes apart; 120 points sampled where they diverge give floor rms
0.715 mm against nearest-node 0.454). Cost of the current anchoring is ~4 mm in a
*reported geoid separation* and ~6e-10 in an elevation factor — **no coordinate
moves** — which is why it was not folded into a vertical-datum build.

**STILL OPEN, and it is a disclosure decision for WP-V7:** the `.err` grid
interpolates **negative** at ~0.43% of Michigan positions (956 of 223,850 sampled,
worst −0.027 m). A negative one-sigma is not a quantity. **NOAA's own published
code produces the same negatives; NOAA's live NCAT service returns a positive
value there** (+0.011 m where we compute −0.00965 m), and no rule maps one to the
other — not `abs()`, not clamping. So `sigma_m` **refuses**, `modeled_error_raw_m`
keeps the raw value readable under a name that cannot be mistaken for an
uncertainty, and **the shift is unaffected and still reported**. All three
paper-overs are pinned as failures.

### Resume checklist, in order — SUPERSEDED by "Resume here" above; item 1 is DONE (#37)

1. ~~**WP-G1 — re-anchor GEOID18 to INTG's stencil. SPECIFIED, NOT BUILT.**~~ **EXECUTED — DESIGN.md #37.** The
   owner instructed it and then instructed that this session log it rather than
   execute it, so **no line of `geoid18.py` or `ngs_grid.py` was re-anchored.**
   The full specification, the measured evidence and the caveats are DESIGN.md
   **#36**, section "WP-G1 (specified, not built)". The change itself is one call
   site; **the work is the anchors**, because the existing 20 cannot tell the
   schemes apart and the geoid suite passes re-anchored either way. **Do this
   BEFORE WP-V5**, which renames the same file.
2. **WP-V5** — geoid model registry, `apply_geoid` → `geoid_model`, GEOID12B (the
   tile and its pin are already committed), and the `geoid18.py` → `geoid.py`
   rename as its own commit. Note the re-confirmation's instruction: **WP-V5 must
   put the GEOID12B digest into its runtime model record** — today's pin is
   suite-only, which is adequate only while nothing loads the tile.
3. Then V6–V9 as the plan has them. **WP-V7 owns the negative-σ disclosure
   decision, and it is the owner's** — see #36.
4. **Closing gate under Codex** — installed and authenticated on this machine, so
   the "reviewer SUBSTITUTED" weakness recorded at the V2/V3 gate is closed.
   **If Codex usage runs out, use independent Opus reviewers instead** (owner's
   instruction, 2026-08-07).

**Branch is NOT merged, on the owner's instruction.** `claude/vertical-transformation-plan-dtxh6j`
carries V0–V4 and is pushed; `main` is untouched.

Two notes left for V4/V6 by the reviewer, neither a defect: `signed_shift` accepts
`grid_value_m=0.0` legitimately (the `.trn` grid genuinely crosses zero in
Michigan), so **the V4 reader must raise on an unreadable cell and never fall back
to 0.0**; and `apply_shift` takes a bare float, so plan §3.6's datum tag on
`ConvertedPoint` must be *checked*, not merely carried.

**The V0 verification gate is DONE and its measurements are in the plan (§2).**
That is the load-bearing part, because it settles four things that would
otherwise be assumed wrong:

- **Amendment #22 was right in every particular** — NGS `.b`, little-endian
  `<4d3i` *including IKIND, the identical struct `geoid18.py` already uses*,
  ~2.4 MB, Fortran record markers that are a real structural check, a companion
  error grid, and the inverse being one grid sign-reversed (verified to 0.00 mm).
- **The grids are in the VERTCON 3.0 Digital Archive**, not `/PC_PROD/VERTCON/`
  and **not VDatum**. Both of those lead to **VERTCON 2.0** (`released=02/24/2011`),
  which is off by up to 43.85 mm across Michigan where 3.0 is off by 2.657 mm.
  URLs, byte counts and SHA-256s are in plan §2.1. ~~**The grids are NOT
  committed yet** — that is WP-V1.~~ **They are committed now (WP-V1), every
  SHA-256 matching.**
- ~~**The two grids need DIFFERENT interpolators**, measured against NCAT:
  `.trn` biquadratic, `.err` **bilinear**.~~ **WRONG, AND SUPERSEDED — do not
  build this.** Both grids are biquadratic with the stencil anchored on the
  NEAREST NODE; the apparent asymmetry was measuring an off-centre stencil, not
  the grids. Plan §2.5a, DESIGN.md **#36**. Verified bit-identical to NOAA's own
  published algorithm.
- **One CONUS grid covers all of Michigan**, so there is no 84 W seam, and the
  `-88.8888` null sentinel is a VDatum convention absent from the NGS files. Two
  risks that dissolved rather than needing mitigation.

**Owner's decisions, all recorded in plan §1 and §5:** Horizontal mode unchanged
(no vertical datum asked, nothing tagged); geoid dropdown is GEOID18 + GEOID12B
with **no "none"**; **per-point σ on the Single point panel and in
`<stem>_full.csv`, and NOT in the clean PNEZD export** — five fields there,
unchanged, because a sixth column breaks the CAD import.

**The disclosure fact that shaped §5:** at 43.05 N, 86.20 W the modeled shift is
**−0.1435 m** and its uncertainty is **±0.3656 m — 255% of the shift** (corrected
from −0.1466 and 249% at the WP-V4 gate; that point is an exact grid node, so the
stored value settles it and NCAT independently returns −0.144 m). Across Michigan
σ runs **0.000004 to 0.3656 m** in the grid — NCAT *prints* to 0.001 m, which is
what §2.8's "0.001" was. A job-level constant would have hidden all of it.

**Superseded by the resume checklist above.** V0–V4 are done and pushed; pick up
at WP-V5, whose dropdown half is no longer blocked — `g2012bu3.bin` is committed
and checksum-pinned.

## Superseded status (2026-08-07, 0.3.0 RELEASED)

**0.3.0 is built, gated and tagged.** The Single point tab reaches users for the
first time, which is why the minor number moved rather than the patch one. All
eight gates passed: suite **1131** green in both `pytest` and `-O`, the frozen
bundle self-test passed, and the bundled end-to-end conversion matched NGS NCAT
to 0.0000 ft northing and 0.0010 ft easting. Notes in
`docs/RELEASE-NOTES-0.3.0.md`.

**The build found one defect, and it was in the suite, not the program**
(DESIGN.md **#31**). A pin from #28 measured the copy button against
`value.fontMetrics().height()`, which under the offscreen test platform is 12 px
for every font family — including Segoe UI asked for by name — where the real
Windows plugin answers 16 for that same font. At 12 the pin rejected the 11 px
glyph the owner asked for and the 14 px one it replaced alike, so it had stopped
telling them apart. Fixed by measuring against the line height the program is
actually drawn in; `result_panel.py` is untouched and no shipped pixel changed.

**Still outstanding, and human:** install on a clean profile and run one real job
end to end (METHOD.md §6). A self-test is not a substitute.

**Next build is NGVD 29 → NAVD 88** — the owner's decision at the close of this
release (DESIGN.md **#32**), with NAPGD2022 after it and backwards compatibility
required rather than assumed. The positive-west question is **closed** and is not
to be refiled (**#33**).

### Superseded status — all owner edits DONE, merged to main

Four rounds: DESIGN.md **#27**, **#28**,
**#29**, **#30**.

### Round four (DESIGN.md #30) — warnings move out; display punctuation

1. **Warnings are a full-width field beneath the results panel**, with no copy
   button and out of Copy all. `single_point_sections` no longer builds the
   row, so the clipboard drops it without a special case; the text comes from
   the new `single_point_warnings` over the same `_warnings_text`.
2. **A defect found by looking, not by a test:** a wrapping `QLabel` does not
   propagate height-for-width out of a `QGroupBox`, so the field showed ONE
   line of a three-warning run and clipped the rest. Fixed with a bounded
   scroll area; pinned by measuring the label against its own content.
3. **Decimal lat/long carry `°`; convergence reads `-16°49'17.78"`.** These are
   **display-only** formatters built on top of the file ones. The symbol cannot
   go in `formatting.latitude`/`longitude`: they write the clean PNEZD export,
   which is read back before the archive is committed, so a symbol there would
   make every geodetic job refuse to write.
4. `Decimal degrees (43.800)` → `Decimal degrees`.
5. The longitude sign list is **positive west first** — enum declaration order
   is what the dropdown offers, so it is pinned as a user-visible fact.

### Round three (DESIGN.md #29) — two defaults, one of which reverses §7

1. **The DMS hemisphere opens on N and W.** Cheap: the letter is a visible
   token beside its angle, and it is correct for every point MCX can convert.
   `dms_entry.DEFAULT_HEMISPHERE` is the one place that assumption lives.
2. **The longitude sign dropdown opens on positive west** — the owner's own
   convention, and a **reversal of §7's no-default rule**, on his instruction.
   The reversal is narrow and pinned: the enum, `JobSettings` and `job.run` all
   still refuse to assume, so only the interface opens on a value.
   **Recorded concern:** OPUS, NCAT, GPS and GIS files are normally *negative*
   west, so the preselect is wrong for every downloaded file — by 340 miles.
   The tooltip carries that warning in capitals.

### Round two (DESIGN.md #28)

DMS entry, a smaller copy glyph, and the worked example out of the longitude
sign entries.

1. **Copy glyph 14 px → 11 px.** Pinned as a relationship — the button may
   stand above its line of text by the frame a flat QToolButton needs and no
   more — rather than as the number.
2. **`LongitudeConvention` values are now `negative west` / `positive west`.**
   The `(84.37)` example moved to the dropdown's tooltip. **This shortens the
   job record's `Longitude` line too**, which is #17's standing choice (one
   wording in both surfaces), not an oversight.
3. **Lat/long can be typed as degrees / minutes / seconds** on the Single point
   tab — four boxes per angle with the symbols already in place and a
   hemisphere letter instead of a sign. Decimal degrees is still what the tab
   opens on. The composition lives in `michspc/fileio/dms.py`, beside
   the formatters that define the notation, because the GUI may not compute an
   angle. The load-bearing pin: **the same DMS entry converts identically under
   both longitude conventions, where the same decimal entry gives two points
   340 miles apart.**
4. **The input CSV takes decimal degrees only** — the owner's question,
   answered. It always did; DMS is now refused *by name*, with a message
   pointing at the Single point tab. Reading DMS from a file is deliberately
   not built: packed `434759.8` is indistinguishable from an ordinary decimal
   degree, so a file reader would have to guess.

Suite **1031 → 1128** across all four rounds, green in both `pytest` and `-O`;
frozen-bundle self-test passes. Sixteen seeded defects, all caught.

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

### Shipped in 0.3.0 with these still open — raise with the owner

- ~~The positive-west preselect~~ — **CLOSED by the owner (DESIGN.md #33). Not
  a concern; verifying the convention is the user's responsibility.** The facts
  are unchanged — OPUS, NCAT, GPS and GIS write negative west, and the wrong one
  moves a point 340 miles — and the program informs rather than decides: the
  dropdown names the convention, the tooltip warns in capitals, the job record
  states it, and the release notes lead with it. **Do not refile this.** It has
  been raised three times; reopening needs new evidence, not the same argument.
- **The job record's `Longitude` line is now shorter too** — `Longitude
  negative west`, with no `(-84.37)`. That follows #17's standing choice of one
  wording in both surfaces. If he wants the example kept in the record and out
  of the dropdown only, that is a separate GUI label and #17 has to be reopened.
- **The layout question was asked and not answered.** "Two columns, one for
  input and one for output" was read as the **results panel**: the Conversion
  box keeps its owner-approved full-width shape on top, and the INPUT/OUTPUT
  result blocks are what split. The other reading — the whole tab splitting,
  entry form left and results right — was not built. Cheap to change.
- ~~The version number is not bumped~~ — **closed. 0.3.0 is the literal, built
  and tagged.**
- **The release cannot be cut from a Linux session.** Gates 5 and 7 of
  `tools/build_release.py` are PyInstaller and Inno Setup, Windows-only. The
  build has to be `py tools/build_release.py` on his machine — which is where
  0.3.0 was in fact built.

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

- **NGVD 29 → NAVD 88 — THIS IS THE NEXT BUILD, and it is now PLANNED: see
  `docs/PLAN-vertical-datums.md` and the status section at the top of this file.**
  Owner's decision at the close of 0.3.0 (DESIGN.md **#32**); sizing is #22 and
  stands as written — the V0 gate confirmed #22's data claims in every
  particular. MEDIUM, every input available today. Build the **vertical-transformation
  registry keyed by (source, target)** rather than one hard-wired path, because
  that registry is how NAPGD2022 later arrives as data. Two risks, neither about
  effort: disclosing a *modeled* shift inside a number that looks exact, and the
  `trn` grid's sign/direction semantics — the defect class this project has
  already been burned by.
- **NAPGD2022, after it** — blocked on NGS, not on us (#22). **Backwards
  compatibility is a requirement, not an assumption:** it does not retire
  NAVD 88 or NGVD 29. A job converted in 2026 must still convert and still
  reproduce afterwards, so the registry keeps every pair it has carried,
  elevations stay datum-tagged, the datum in force is named in every output, and
  an unestablished datum refuses rather than assuming the newest.
- **SPCS2022 — not next, and DOWNSTREAM OF NAPGD2022, not parallel to it.** The
  modernized NSRS has two halves that arrive together: SPCS2022 coordinates are
  defined on **NATRF2022**, and **NAPGD2022** is the geopotential half
  (GEOID2022 replacing GEOID18 and NAVD 88). This program reports elevation and
  combined factors, so an SPCS2022 point carrying a GEOID18/NAVD 88 factor mixes
  two eras inside one number — and 18 of Michigan's 19 zones are LDPs designed
  at a topographic height, where the height side is load-bearing. So the order
  above is a dependency order. Spec is #21; its own blockers are unchanged — no
  official NAD83(2011)→NATRF2022 transformation, and the transverse and oblique
  Mercator engines this program does not have.
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
                  NGS binary grids. Named fileio, never io (shadows stdlib).
michspc/gui/      PySide6; never computes a domain result
tests/            suite; every expected value hand-derived in a comment
data/             four NGS grids, unmodified, each SHA-256 pinned: g2018u3.bin,
                  g2012bu3.bin, and the VERTCON 3.0 .trn/.err pair
review/           committed review harnesses and captured NGS truth (#36)
docs/             DESIGN.md (authority), method/, the NOAA manual, reference/
```

## Non-negotiable conventions (enforce in review)

- Units explicit at every boundary; International feet is the default because
  Michigan legislated it, and the unit in force is stated in every output file.
- Longitude sign convention: **no default in the core** — `JobSettings`
  requires it and `job.run` refuses a geodetic job without it. The GUI dropdown
  opens on positive-west (DESIGN.md #29, owner's instruction); that is a
  decision, not a regression, and #29 says why.
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
