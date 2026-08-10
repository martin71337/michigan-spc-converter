# MCX 0.4.0

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

## A Vertical-only mode

A third mode, **Vertical**, on both tabs, converts elevations and nothing
else. You state the INPUT horizontal system — a zone, or geodetic positions
— and no output system: the To zone and output unit controls are hidden,
because no output horizontal system exists in this mode.

- **The exports mirror the import.** The clean export keeps the input's own
  layout and its coordinate columns hold the input values unchanged
  (re-rendered through the standard formatters, so they are
  formatting-normalized, not byte-copied); only the Z column differs, by
  exactly the modeled shift, in the target datum. The output unit is the
  input unit by construction — a mismatch is refused rather than
  re-expressed.
- The audit CSV states it plainly: the target coordinate columns equal the
  source columns, and the "Target zone" cell reads **vertical only**.
- Factors follow the input system: with a zone input they are the input
  zone's at each point (as a State Plane → geodetic job reports them); with
  geodetic input no zone exists anywhere, so the grid scale and combined
  factors read N/A — never a fabricated 1.0 — while the elevation factor,
  which needs no zone, is still computed.
- On the Single point tab the OUTPUT panel shows only the target-datum
  elevation, the shift and its one-sigma — the unchanged coordinates are
  not repeated under an OUTPUT heading, because nothing was converted
  horizontally.
- The vertical arithmetic is the same code path as Horizontal + Vertical —
  not a second implementation — held to the same frozen NCAT anchors in
  both input formats and both datum directions.

## What the shift is, honestly

- **Modeled, not measured.** A published NAVD 88 benchmark value supersedes
  a modeled shift, and NGVD 29 network distortions of 20 cm or more exist.
  The job record carries NGS's caveat in full on every written job.
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
- **The Multi point tab's Elevations tooltip** claimed heights were "passed
  through unchanged"; a differing output unit re-expresses the value, and
  the tooltip now says so. The Elevations controls appear only in
  Horizontal mode — in the vertical modes the elevations are the thing
  being converted — and a visible note beside them says what they are for:
  the elevation and combined factors.

## Verification (summary; the full record is DESIGN.md #35–#49)

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
