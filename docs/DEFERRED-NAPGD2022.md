# DEFERRED — NAPGD2022 / GEOID2022 vertical support MUST BE COMPLETED IN A FUTURE BUILD

**Status: DEFERRED on 2026-08-28, by the owner's decision, for the measured
reasons below. This is unfinished, scheduled work — not abandoned scope.**
Authority: DESIGN.md **#61**; measurement record: `review/nsrs-n0/FINDINGS.md`;
the deferred design of record: the vertical sections (N-packages) of
`docs/PLAN-nsrs-modernization.md`.

## What is deferred

1. **NAVD 88 ⇄ NAPGD2022 elevation conversion** — the datum bridge itself.
2. **NGVD 29 → NAPGD2022 chained conversion** (both legs in one job, per-leg
   disclosure, RSS σ) — approved by the owner during planning, fully designed
   (the `ChainedVerticalTransformation` record in the plan), waiting on leg 2.
3. **GEOID2022 as a geoid model** (including GNSS ellipsoid-height →
   NAPGD2022 orthometric, H = h − N).
4. **IGLD 2020** remains deferred from before (DESIGN.md §10) and is
   additionally downstream of all of the above (~2027, tied to NAPGD2022).

## What is NOT deferred — the factors all still work

Grid scale factor is a projection quantity and is computed for every SPCS2022
zone by this build's engines. Elevation factor and combined factor keep
working exactly as today — the file's elevation plus GEOID18's separation —
on every zone including the 2022 zones. The era gap this introduces
(an NAVD 88-era height inside a NATRF2022-era zone's factor) is ~0.5 m of H
in R/(R+H+N) ≈ **8×10⁻⁸**, recorded as fact in #61. Nothing a job computes
today stops working; nothing waits on this deferral except conversions **to
the new vertical datum**.

## Why it is deferred — every reason, all measured 2026-08-28 (N0)

1. **NGS publishes no NAVD 88 ↔ NAPGD2022 transformation product. It does
   not exist anywhere.** No grid file on any NGS site; no service; both
   hosts' REST APIs refuse every token (`{"error": "Invalid output vertical
   Datum"}` — reproduced independently by the session lead); the beta NCAT
   app has no geopotential-datum control and silently drops orthometric
   heights; NGS's own FAQ answers "will NCAT convert to the modernized
   NSRS?" with "Yes, it **will**" — future tense. Building the conversion
   would mean inventing NGS's missing product.
2. **The ~0.5 m offset is real and cannot be derived honestly from what is
   published.** GEOID18 minus SGEOID2022 at NGS's own test points (Detroit
   −0.576 m, Chicago −0.434 m) is the hybrid-vs-gravimetric datum gap, and
   using that difference as a conversion would fabricate a transformation
   NGS has not published — the exact class of silent error this program
   exists to refuse.
3. **GEOID2022 has no oracle today.** No geoid API serves it on any host
   (production's model registry stops at 14 = GEOID18; beta's API returns
   `{}` for everything). NGS publishes only 87 test points, exactly **two**
   within a Michigan-sized window.
4. **GEOID2022's interpolation method has no reference implementation.**
   The file declares bicubic (4×4, Numerical Recipes, linear edge padding;
   bilinear for σ grids), but unlike VERTCON (`Vertcon.java`) and GEOID18
   (`intg.f`), no NGS source code implementing it was located — the
   replicate-NOAA-exactly standard (DESIGN.md #36/#37) currently has nothing
   to replicate against.
5. **The geoid is now time-dependent** (static grid at epoch 2020.0 plus a
   rate grid; `GEOID = SGEOID + DGEOID·(mjdn−58849)/365.25`), and nothing in
   MCX carries a time axis — a real structural change that deserves its own
   verified build, not a rider.
6. **~475 MB of new grids** against today's 2.4 MB tile — a bundling and
   installer decision the owner should make when the data is actually
   usable.
7. **Everything is beta** (`beta_v0a`, 2026-04-27) and NGS's official
   release is ~Q1 2027; the vertical product, when it appears, may arrive
   with different geometry, format, or σ semantics than anything guessed
   today.

## What already exists, waiting

- The registry seam: `NAPGD2022` is declared in `michspc/spc/vertical.py`
  (`DECLARED_NOT_USABLE`), and `GeoidModel.vertical_datum` +
  `require_geoid_matches_datum` + the per-side era guards + the compound
  refusal were all built for exactly this arrival (DESIGN.md #32/#41/#50).
- The full vertical design (chained record, grid-key dispatch, epoch field,
  per-leg disclosure, σ composition with its citation) in
  `docs/PLAN-nsrs-modernization.md` — verified against the code at 0.6.4.
- GEOID2022's download URLs, formats (legacy `.b`/`.bin` published — no
  format conversion needed), sizes, geometry, and the embedded combination
  rule — all captured and digest-pinned in `review/nsrs-n0/`.
- Re-runnable capture harnesses (`review/nsrs-n0/capture_*.py`) that will
  re-measure everything the day NGS publishes.

## Conditions to reopen — check these, in order

1. NGS publishes a NAVD 88 ↔ NAPGD2022 transformation product (grid or
   service), OR NCAT accepts the vertical-datum tokens. (Re-run
   `review/nsrs-n0/capture_ncat_beta.py`'s REST matrix — the refusals are
   the tripwire.)
2. An oracle for GEOID2022 exists: a geoid API model id, a computation
   service, more test points, or NGS reference source for the bicubic.
3. Then: execute the plan's N-packages (N1–N5 vertical items) as written,
   with fresh captures replacing every assumption, under the same gate
   discipline — and NGVD 29 chaining and IGLD 2020 in their recorded order.

**Do not remove this file until that work ships.** The release notes for
every release in between should continue to say vertical-datum conversion to
the modernized NSRS awaits NGS publication.
