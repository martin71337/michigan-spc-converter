# MCX 0.4.0 — DRAFT, NOT RELEASED

> **This is a draft.** The version literal has not moved, no installer has
> been built, and no tag exists. The owner reviews the whole vertical feature
> — including the new tab layouts, which have not been seen on a real screen
> — before any release is cut. This file exists so the release, when it
> comes, ships with notes written while the verification was fresh.

## Elevations can now be converted between vertical datums

A new **Horizontal + Vertical** mode on both tabs converts elevations between
**NGVD 29** and **NAVD 88** using NGS **VERTCON 3.0** (release 20190601),
alongside the horizontal conversion. In Horizontal mode nothing is asked,
nothing is tagged, and the Z column is never shifted. **Horizontal
coordinates are unchanged to the last written digit** — the clean PNEZD
export is byte-identical to 0.3.1's across every configuration measured, and
no elevation or combined factor changed. Two things in a horizontal job's
*audit trail* do change, both disclosed below: the reported geoid height
moves by up to ~7 mm at some positions (the GEOID18 re-anchoring — no
coordinate and no factor moves), and one METHOD line in the job record now
reads "as used for the factors".

- The shift is applied at each point's own position — it varies from
  −0.41 m to +0.35 m across Michigan and changes sign, so it is not a
  constant that could be added by hand.
- Every shifted elevation carries a **per-point one-sigma uncertainty** from
  NGS's companion error grid, on the Single point panel and in the audit
  CSV. Across Michigan it runs from a fraction of a millimetre to
  **0.366 m — at one Michigan position, 255% of the shift itself** — which
  is why it is per-point and not a job-level constant.
- The clean PNEZD export keeps **exactly five fields**: the Z column holds
  the target-datum elevation and the job record says which datum that is. No
  sixth column reaches a CAD import.

## What the shift is, honestly

- **Modeled, not measured.** A published NAVD 88 benchmark value supersedes
  a modeled shift, and NGVD 29 network distortions of 20 cm or more exist.
  The job record carries NGS's caveat in full; the Single point panel
  carries it in a row of its own, because that tab writes no file.
- Where the error model's output cannot be a one-sigma uncertainty (a small
  fraction of Michigan positions), the sigma reads **N/A — never a number**
  — and a warning explains. The shift at such a point is valid and
  unaffected.
- The model is interpolated the way NOAA's own published software
  interpolates it, verified bit-identical; that method steps at half-cell
  lines (worst ≈76 mm in Michigan), NCAT reproduces the same steps, and the
  job record says so.

## A second geoid model

The geoid dropdown offers **GEOID18** (the default) and **GEOID12B**, both
NGS tiles committed unmodified and checksum-pinned, both anchored against
NGS's own geoid service. The audit CSV of a vertical job names the model
beside every geoid height. GEOID18's interpolation was also re-anchored to
the stencil NGS's own INTG program uses (worst change ~7 mm in a reported
separation, inside the model's stated 30–60 mm uncertainty; no coordinate
moved).

## Fixed

- **A stale result could survive a longitude-convention flip on the Single
  point tab** — present since 0.1.0, capable of leaving a coordinate
  9,756,797 m out on screen captioned "Converted" with the copy buttons
  armed. Every selection now genuinely discards the result.
- **The copy buttons' glyph was cut off on scaled displays** (125/150/200%
  Windows scaling). It now renders identically at every scale.

## Verification (summary; the full record is DESIGN.md #35–#44)

- The VERTCON reader is **bit-identical to NOAA's published Vertcon.java**
  over the whole CONUS grid; 20 frozen NCAT anchors reproduce to 0.47 mm;
  forward and inverse round-trip to exactly zero; the sign is pinned by
  NCAT's own 200.000 → 199.860 figure.
- 20 frozen NGS anchors gate GEOID12B (worst 0.543 mm); 120 discriminating
  anchors gate GEOID18's re-anchoring.
- The frozen bundle self-test authenticates all four NGS grids and converts
  one vertical point end to end against NCAT before any release is cut.
- Every work package passed an independent adversarial review gate; every
  fix is pinned with the reviewer's own counterexample and every pin was
  falsified by seeding the defect it catches.
