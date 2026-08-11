# MCX 0.5.0

## The input and output geoid are now chosen separately

A vertical job picks its geoid model **per side**: an **Input geoid** and an
**Output geoid**, each offering only the models that belong to that side's
vertical datum. Both open on **GEOID18**, so nothing converts differently
than it did in 0.4.0 unless you change a dropdown. Horizontal mode is
untouched — same controls, same outputs, to the byte.

- Where a datum has no geoid models of its own (NGVD 29 today), that side's
  selector is **grayed out** rather than hidden, so it is visible that the
  question exists and does not apply.
- The audit CSV of a job that states both sides gains a **Source geoid
  model** column beside the existing **Geoid model** column.

## Converting an elevation from one geoid model to another

With the same vertical datum on both sides and two *different* models, MCX
now converts the elevation between them:

**H_out = H_in + (N_in − N_out)** — the ellipsoid height is held fixed and
the orthometric height is re-derived under the other model. At the Houghton
test point, 200.000 m stated against GEOID12B becomes **199.968 m** against
GEOID18; the reverse returns 200.032 m.

- **Both elevation labels now name their geoid** — `Elevation (NAVD88, m)
  (GEOID18)`, with the input row naming its own model. On these jobs the
  datum and the unit are the same at both ends, so the model is the only
  thing telling the two heights apart.
- The Single point panel replaces the datum shift row with **Geoid change
  GEOID12B -> GEOID18**, because on these jobs the datum did not move.
- The job record gains a **GEOID CHANGE** block naming both models, both
  bundled tile filenames, both SHA-256 digests, and the arithmetic.
- **The uncertainty reads N/A.** NGS publishes no error model for the
  difference between two hybrid geoid models, so no number exists to print
  and none is invented.

### What this conversion is, and what it is not

Read this before using it on a job.

The hybrid geoid models are each fitted **to** the leveled network, so
updating the model does not move a published benchmark: a **leveled** NAVD 88
elevation does not depend on which geoid model you name. The arithmetic above
is the re-derivation of a **GNSS-derived** orthometric height under the other
model. Applied to a leveled height it states the two models' disagreement at
that point rather than a new realization of the benchmark — and **the program
cannot tell which kind of height your Z column holds.** Deciding that is
yours.

- A job with the **same model on both sides** is unchanged from 0.4.0: no
  swap step, no record block, no relabeled rows.
- A job that changes the **datum** (NGVD 29 ⇄ NAVD 88) is the 0.4.0 vertical
  conversion, unchanged, and its elevation rows name no geoid model — that
  height does not depend on one.
- Changing both the datum and the geoid in one job is **refused** rather than
  performed as two modeled operations at once.

## Fixed

- **A NAVD 88 → NGVD 29 vertical job failed outright at any point outside the
  bundled geoid grid**, instead of converting that point and reporting its
  factors as N/A. It affected the whole job, not the one point, and that datum
  pair reaches it from the program's default state. No wrong coordinate was
  ever produced — the job stopped rather than writing one — and it was never
  in a released build. Found in the release gate, by two reviewers
  independently, with the same test point.
- **The Single point tab's elevation box called the elevation "Optional"** in
  all three modes. In Horizontal + Vertical and in Vertical the elevation is
  the value being converted. The tooltip is removed.

## Verification (the full record is DESIGN.md #50–#52)

- The swap figures are hand-derived from **both** frozen NGS anchor sets at
  the Houghton point and pinned against the shipped grids' own exact
  difference; sign, round-trip symmetry and the fixed ellipsoid height are
  each pinned separately.
- Every pre-existing job shape is proven **byte-identical** on every written
  surface, and a horizontal job's outputs do not change at all.
- Each new pin was **falsified** by seeding the defect it claims to catch —
  the sign flipped, one grid read twice, the graying filter dropped, the
  compound refusal deleted, the geoid tag leaked onto ordinary vertical jobs,
  and more.
- An independent adversarial reviewer ran a closing gate over the whole
  release diff.
- Suite **1608**, green in both run modes; the frozen bundle self-test passes
  8/8 before the installer is built.
