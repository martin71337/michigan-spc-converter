# H3 lead experiment — the frame composition, discriminated against the frozen anchors (2026-08-29)

Run by the session lead (`frame_experiment.py`, output committed beside it)
against the 12 forward frame anchors frozen from beta NCAT
(`review/nsrs-h1-anchors/anchors.json`). Five candidate compositions of
NAD83(2011)@2010.0 → NATRF2022@2020.00, all using HTDP v3.6.0's IGS-block
Helmert constants (verbatim in NCAT-ENGINE-RECON.md) and the frozen EPP2022
rates.

## Result

| Candidate | Composition | Mean error vs NCAT |
|---|---|---|
| P1 | Helmert legs @2010.0, EPP +10 yr, **coordinate-frame sign** | 11.024 mas ≈ **341 mm** |
| **P2** | Helmert legs @2010.0, EPP +10 yr, **position-vector sign** | **0.644 mas ≈ 20 mm** |
| P3 | Helmert alone @2010.0, no EPP | 5.769 mas ≈ 178 mm |
| P4 | Helmert legs @2020.0, EPP +10 yr CF | 5.127 mas ≈ 158 mm |
| P5 | Helmert alone @2020.0 | 0.915 mas ≈ 28 mm |

**The sign-convention conflict recorded in #61's annotation is SETTLED by
measurement: the EPP2022 rotation is applied in the position-vector sense —
NGS's own "positive counterclockwise, right-hand rule" prose was right, and
the third-party database's EPSG-1056 (coordinate-frame) tag was wrong.**
Getting it backwards costs 341 mm at Michigan's latitude, the boundary-moving
figure the annotation predicted.

## The residual, and what it points at

Per-anchor P2 residuals: eleven of twelve anchors agree at 0.06–0.47 mas
(≈ 2–12 mm); one — `frame_p05` (43.8 N, −86.4 W, near the Lake Michigan
shore) — is (−1.85, +5.28) mas ≈ 170 mm. Small spatially-varying residuals
with a localized outlier are the signature of a **grid-based displacement
term**, and N0's capture of the beta NCAT app already named one: the app
describes epoch transformation "via IFDM2022" (the intra-frame deformation
model). The working hypothesis for H3, to be confirmed before code:

    NCAT's path = Helmert(NAD83(2011) ↔ ITRF2020, HTDP-class values)
                + EPP2022 rotation (position-vector sign) over 2010.0→2020.0
                + IFDM2022 gridded intra-frame displacement over the same span

## What H3 must do with this

1. **Recon: find IFDM2022** on beta.ngs.noaa.gov — grids, format, coverage,
   sign, and whether a Michigan tile exists; freeze whatever is found. If
   the residuals (mean ~9 mm excluding the outlier, worst 170 mm) are
   entirely IFDM, the composition above plus the grid reproduces NCAT
   within print precision. If IFDM is not published, the honest options are
   (a) carry the composition with the measured residual bound stated as a
   fact in the record, or (b) hold the frame leg per the plan's stop rule —
   **the owner's call, with the measured numbers in front of him**.
2. The exact Helmert values remain a candidate set (HTDP's), not NCAT's
   confirmed internals; the anchor suite is the arbiter either way.
3. The experiment used HTDP's own GRS 80 (1/f = 298.257222101) and
   linearized rotations, matching frit94's arithmetic; production code
   revisits both choices against the house citations.

Nothing here is production code; the experiment exists so the H3 design and
its build brief rest on measurement rather than on either conflicting
document.
