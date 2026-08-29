# DEFERRED — the NAD 83(2011) ⇄ NATRF2022 transformation MUST BE COMPLETED IN A FUTURE BUILD

**Status: DEFERRED on 2026-08-29, by the owner's decision, on measured
evidence. This is unfinished, scheduled work — not abandoned scope.**
Authority: DESIGN.md **#62**; the measurements:
`review/nsrs-h3-recon/EXPERIMENT-FRAME-COMPOSITION.md` (as corrected),
`review/nsrs-h3-recon/ifdm/`, `review/nsrs-h1-anchors/P05-PROBE.md`.

## What is deferred

Converting coordinates BETWEEN the two frames — NAD 83(2011) jobs onto
SPCS2022 zones and back, and NAD 83 ⇄ NATRF2022 geodetic. A cross-frame
selection refuses, naming the reason: NGS has not published the
transformation.

## What is NOT deferred

Everything within each frame: the three SPCS 83 zones exactly as always,
the 19 SPCS2022 zones with NATRF2022 geodetic input/output (any-to-any
among the 2022 zones, verified against beta NCAT to print precision), and
every factor on every zone.

## Why — measured 2026-08-28/29

1. **NGS publishes no transformation parameters.** NCAT's values are
   server-side (proven to the level of parsing the offline tool's compiled
   classes — the Helmert beans deserialize server data; no parameter
   resource ships; the offline readme says "This version does not support
   datum transformations"). The NATRF2022 page says a developer test
   dataset "will be released publically on GitHub after completing
   internal review" — future tense.
2. **The best public candidate set misses NCAT by more than the tier
   tolerates.** HTDP-derived Helmert values reproduce beta NCAT to 2–3 cm
   at 11 of 12 frozen Michigan anchors — and **17 cm at one** (43.8 N,
   −86.4 W), re-probed and reproduced digit-for-digit, so it is NCAT's
   real behaviour, explained by neither EPP2022 nor IFDM2022 (the
   IFDM-vs-EPP deviation there is exactly zero, measured against the
   captured grid).
3. **NCAT's own printed sigmas vary spatially** (0.000681″ to 0.001540″
   within 0.1°) — the signature of an unpublished grid component inside
   NCAT's path that no public document describes.
4. The program's standing rule (the plan's acceptance bar): a systematic
   residual means wrong parameters — stop. Shipping a boundary-moving
   transformation that disagrees with the national tool by up to 17 cm is
   exactly what MCX exists to refuse.

## What already exists, waiting

The frozen 12+3-point frame anchor lattice with reverse pairs; the p05
probe; the EPP2022 capture; the IFDM2022 grids (digest-pinned, harness
committed); TR NOS NGS 62 / TM 90 / TM 95 captured with the definitional
equations extracted verbatim; the composition experiment with candidate
rankings; and the H3/H4 design in `docs/PLAN-nsrs-modernization.md`
(helmert.py, the frames-transformation registry, the two-pivot
PointConversion) — all verified against the code at 0.6.4/H2.

## Conditions to reopen — check these, in order

1. NGS publishes the transformation: the developer test dataset on
   github.com/noaa-ngs, or published parameter sets, or an NCAT REST API
   accepting NATRF2022 tokens (re-run the frozen probe matrix in
   review/nsrs-n0/capture_ncat_beta.py — the refusals are the tripwire).
2. Then: freeze new anchors, discriminate the composition against them
   (the experiment script is the template), and execute the plan's H3/H4
   packages as designed, under the standing gate discipline.

**Do not remove this file until that work ships.** Release notes in the
interim state that cross-datum conversion awaits NGS's publication of the
transformation.
