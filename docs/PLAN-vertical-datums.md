# PLAN — Vertical datum transformation, and a geoid model registry

**Status: V0, V1, V2, V3 and V4 are BUILT. V5–V9 are not.** See the work-package
table in §7 and DESIGN.md amendments **#35** and **#36**, which record what
landed, the review-gate findings, and why the rest stopped. Written 2026-08-07 at
the owner's direction. It remains a proposal against DESIGN.md amendments **#22**
(sizing) and **#32** (ordering), and it becomes a DESIGN.md amendment when the
owner approves it. Until then DESIGN.md's body is unchanged.

**WP-V1 IS DONE — the block was the container, not the work.** It was recorded
here as impossible off the owner's machine because `geodesy.noaa.gov` is refused
by the container's egress policy. Run *on* that machine, NOAA is reachable: all
three files of §2.1 downloaded and **every SHA-256 matched the pin**, so the
committed files are byte-identical to what V0 measured. The 20-point lattice was
re-captured (the V0 scripts were lost with that session's scratchpad) and is
frozen at `tests/fixtures/vertcon_anchors.py`; it is a **recreation, not the
original**, seeded with every position this plan records so it could be checked
against V0, and all six of those reproduce. See the fixture's own docstring for
what is and is not reproduced.

**RESOLVED, and no longer a question for the owner:** §2.8's "0.001 m to
0.366 m" and §2.7's "+0.000004 m to +0.365599 m" are not in conflict — they
describe the grid's own value and NCAT's *printed resolution* respectively. At
43.0 N / 84.5 W the grid holds 0.00065542 m where NCAT returns 0.001. The code
quotes §2.7, which is right. See the note in §2.8.

**§2.5 IS SUPERSEDED — read §2.5a before building the reader.** Both VERTCON
grids are biquadratic; the "`.err` is bilinear" asymmetry was an artifact of an
off-centre interpolation stencil, and the pin §2.5 and §6 ask for would enshrine
a defect. Measured by two independent readers agreeing to four decimals.

**The V0 verification gate has been run.** Every load-bearing unknown named in
the first draft of this plan is now measured rather than assumed, against the
real files and against NGS's own service. §2 records what was measured. There is
**no blocking question left** — the earlier draft's §3 is resolved and its
answer changed the plan.

**Headline: amendment #22 was right in every particular, and the first pass of
this reconnaissance was wrong.** #22 said the grids are NGS `.b`, little-endian,
~2.4 MB, with Fortran record markers that are themselves a free structural
check, with a companion error grid, and with the inverse being the same grid
sign-reversed. All six claims are confirmed by measurement. A detour through
VDatum found a *different and superseded* product and briefly contradicted four
of them; that detour and its correction are recorded in §2.6 because the wrong
turn is instructive.

---

## 1. Scope

Five instructions from the owner:

1. Add the vertical transformation recorded in the plan — NGVD 29 → NAVD 88.
2. Elevations convert **simultaneously alongside** the horizontal conversion.
   Not a separate mode, not a second pass.
3. There must be a way to **opt out**, so the user is not made to answer input
   settings the job does not need.
4. The input options **expand or change** when the user picks their method of
   conversion. At the top of the form, button selections for **"Horizontal"** or
   **"Horizontal + Vertical"**.
5. A **geoid option on both tabs** — today it appears only on Multi point, as a
   static label. It becomes a **dropdown** so further models can be added.
   **GEOID18 and GEOID12B**, and **no "none" entry**.

### Settled by the owner during planning

| Question | Answer |
|---|---|
| What does "Horizontal" mode say about the vertical datum? | **Nothing. Unchanged from today** — Z passes through untagged, no vertical datum is asked, and the record states none was established. |
| Geoid dropdown contents | **GEOID18 and GEOID12B. No "none."** |
| Uncertainty disclosure | **Per-point σ from the error grid.** On the Single point panel and in the full-audit CSV. **Not in the clean PNEZD export.** Settled after the §2.8 measurement; see §5. |
| Grid acquisition | Authorized. Done; see §2.1. |

### Deliberately out of scope

- **NAPGD2022 / GEOID2022.** Blocked on NGS (#22), and confirmed so in V0: NCAT
  returns an empty response for a NAVD88 → NAPGD2022 request. It is *declared*
  here so the refusal has something to refuse — the role `NATRF2022` plays in
  `frames.py` today — and nothing more.
- **Tidal datums, IGLD 85, LWD.** VDatum carries them; this is not VDatum.
  IGLD 85 is genuinely tempting for Great Lakes work and is genuinely a different
  problem (dynamic heights, not orthometric). Recorded as refused, not forgotten.
- **Alaska, Guam, PR/VI, CNMI, American Samoa.** The VERTCON 3.0 archive carries
  all of them. A Michigan tool is not a national one (§10).
- **NAD 27 / NADCON.** Horizontal, and already out of scope.
- **Vertical-only conversion as a distinct mode.** Already expressible: a
  zone-to-the-same-zone job with the vertical pair selected.

---

## 2. V0 verification — what was measured

All figures below are from files downloaded 2026-08-07 and from NCAT queried live
the same day. The scripts are in the session scratchpad, not the repo; they get
rewritten as suite fixtures in WP-V7.

### 2.1 The data, located and pinned

Source: **`geodesy.noaa.gov/pub/vertcon3/20190601release/Builds/ngvd29.navd88.conus/`**
— the VERTCON 3.0 Digital Archive, referenced from `geodesy.noaa.gov/VERTCON3/`
and documented in NOAA Technical Report NOS NGS 68.

| File | Bytes | SHA-256 |
|---|---|---|
| `vertcon_3.0_20190601.ngvd29.navd88.conus.oht.trn.b` | 2,465,424 | `2bd703f760e8fbb96b48173f762a1e4bc2e4bd0357e1a26201a96bb7a96b1cbe` |
| `vertcon_3.0_20190601.ngvd29.navd88.conus.oht.err.b` | 2,465,424 | `496355e8617b0f0cdfb0fad9f0f96c8215aabe44ccf7039514e124d22af492cc` |
| `g2012bu3.bin` (GEOID12B, NGS PC format) | 4,933,728 | `7ce1755c1e6ef8a1cc2909bd221e4a94fa46b2fbc33ebe4489a4973edd39b844` |

Committed **unmodified** and under NGS's own filenames, so each stays
byte-comparable against its source (DESIGN.md §3). Repo and installer grow
**9.8 MB**.

The GEOID12B tile is **byte-for-byte the same size as the `g2018u3.bin` already
committed**, on the same tile #3 geometry — 1081 × 1141, 40–58 N, 96–77 W, one
arcminute. It needs a new SHA-256 pin and its own `TileGeometry` record and
nothing else. The geoid seam works as designed.

> **Do not take the geoid from VDatum.** `vdatum_GEOID12B.zip` is 94.7 MB and
> `vdatum_GEOID18.zip` is 141.6 MB, because they carry every region as GTX.

### 2.2 Format — confirmed as #22 described it

```
offset 0   int32   Fortran record marker = 44          <- NOT in GEOID18
offset 4   4d3i    SLAT WLON DLAT DLON NLAT NLON IKIND <- IDENTICAL to GEOID18
offset 48  int32   Fortran record marker = 44
then, per row:  int32 marker=NLON*4 | float32[NLON] | int32 marker=NLON*4
```

Little-endian, `IKIND = 1`, values in **metres**. Every marker was validated
during the parse — header 44/44, all 521 row markers 4724/4724, and the byte
count consumed exactly equals the file length:
`52 + 521 × (8 + 4724) = 2,465,424`. #22's "free structural check" is real and it
is stronger than GEOID18's, which has no markers at all.

**Geometry: 24–50 N, 235–294 E (125 W – 66 W), 521 × 1181 at 0.05°.** The `.err`
grid shares that geometry exactly.

**One CONUS grid covers all of Michigan.** The 84 W seam that the first draft of
this plan devoted a whole section to **does not exist** — it was an artifact of
VDatum's three-region split (§2.6). That risk is dissolved, not mitigated.

Michigan sits well inside: the grid reaches 50 N and 125 W, against Michigan's
48.3 N and 90.5 W.

### 2.3 Sign and units — pinned, with #22's own anchor

The grid stores `NAVD88 − NGVD29` in **metres**, and it is **added** to the
source height. At #22's anchor, 43.0 N / 84.5 W:

| | value |
|---|---|
| grid, biquadratic | **−0.1402 m** |
| NCAT `destOrthoht` − 200.000 | **−0.1400 m** |

This is the sign/direction defect class the project was burned by (#1, MATLAB
defect 2), and it is now pinned against an external source before a line of
production code exists.

### 2.4 The inverse is the same grid, sign reversed — verified exactly

#22 claimed it; NCAT confirms it at every point tested, to the last printed
figure:

| Point | NGVD29→NAVD88 | NAVD88→NGVD29 | sum |
|---|---|---|---|
| 43.00 N 84.50 W | −0.1400 | +0.1400 | **0.00 mm** |
| 42.33 N 83.05 W | −0.1710 | +0.1710 | **0.00 mm** |
| 45.87 N 84.73 W | −0.0770 | +0.0770 | **0.00 mm** |
| 46.54 N 87.40 W | +0.0340 | −0.0340 | **0.00 mm** |
| 44.76 N 85.62 W | −0.1160 | +0.1160 | **0.00 mm** |

One grid, one data path, two directions.

### 2.5 THE INTERPOLATION FINDING — SUPERSEDED AT THE WP-V1/V4 GATE

> **This section's conclusion was wrong, and the way it was wrong is the useful
> part.** It is left standing rather than rewritten, with the correction below
> it, because "the plan was right and the recon was wrong" is recorded in §2.6
> and the reverse deserves the same treatment. **Read §2.5a before building
> anything.**

**Measured, not assumed, and not what anyone would have guessed.** 20 points
across Michigan, our reader against NCAT:

| Grid | Bilinear | **Biquadratic** | Nearest |
|---|---|---|---|
| `.trn` (transformation) | max 7.430 mm, mean 1.637 | **max 2.657 mm, mean 0.697** | — |
| `.err` (uncertainty) | **max 1.526 mm, mean 0.589** | max 12.406 mm, mean 1.339 | max 14.321 mm, mean 2.184 |

~~**The transformation is biquadratic. The error grid is bilinear.**~~
**WRONG — see §2.5a. Both grids are biquadratic, nearest-node anchored. Do not
build this.**

This matters, and it would have been got wrong. GEOID18 is biquadratic —
established by measurement in amendment #8 — so biquadratic on both is the
obvious choice, and on the error grid it is wrong by up to 12 mm. Two concrete
consequences at real Michigan towns:

- **Kalamazoo**: NCAT reports σ = 0.0040 m. Biquadratic gives **0.0080** — double
  the true uncertainty.
- **Lansing**: NCAT reports σ = 0.0070 m. Biquadratic gives **0.0042** — *less*
  uncertainty than there is, which is the dangerous direction.

There is a principled reason as well as a measured one: an uncertainty is a
non-negative, variance-like quantity, and the Lagrange biquadratic can overshoot
and undershoot, while bilinear is monotone within its cell. The measurement is
the authority; the reason is why the measurement is believable.

~~**This gets pinned by a test that fails if the two are ever unified**, because
"use the same interpolator for both grids" is exactly the tidy-looking
simplification a future reader would make.~~
**DO NOT WRITE THAT TEST — it would pin the defect. §2.5a, point 1, says what to
pin instead: both grids through the nearest-node-anchored biquadratic, with the
floor-anchored and bilinear variants shown failing the anchor lattice.**

### 2.5a THE CORRECTION — both grids are biquadratic; the asymmetry was a stencil artifact

**Measured 2026-08-07 by two independent readers** — one written by a
measurement agent forbidden to look at the production code, one written by the
session lead from the format spec — **agreeing to four decimal places**, against
the re-captured NCAT lattice in `tests/fixtures/vertcon_anchors.py`.

`ngs_grid.interpolate_biquadratic` anchors its 3×3 stencil with
`row0 = int(row) - 1`. That puts the interpolation coordinate in **[1, 2]**: the
point sits in the *upper* interval of the stencil, which therefore reaches a
full cell below the point and none above it. Anchoring on the **nearest node**
(`int(row + 0.5) - 1`) puts it in [0.5, 1.5], centred.

Max absolute residual against NCAT, 20 forward anchors:

| Grid | biquad, **floor**-anchored | biquad, **nearest-node** | Bilinear | Nearest |
|---|---|---|---|---|
| `.trn` | 8.4573 mm | **0.4707 mm** | 17.7262 mm | 32.5466 mm |
| `.err` | 3.0416 mm | **0.4716 mm** | 4.5468 mm | 14.3214 mm |

**Both grids are biquadratic with nearest-node anchoring**, and under it all 40
residuals fall below NCAT's own 0.5 mm printing quantization — every one of the
20 points in both grids rounds to NCAT's printed figure exactly.

§2.5's asymmetry was a real measurement of an off-centre stencil, not a property
of the two grids: bilinear only beat "biquadratic" on `.err` because it was
racing a mis-anchored biquadratic. Note that *both* of §2.5's biquadratic
figures (2.657 and 12.406 mm) are worse than the 0.47 mm a centred stencil gets
on the same grids.

**Three consequences, all load-bearing:**

1. **The pin §2.5 and §6 ask for — "fails if the two are ever unified" — must
   NOT be written.** It would pin the defect. The pin to write is the opposite:
   both grids read through the nearest-node-anchored biquadratic, with the
   floor-anchored and bilinear variants failing the anchor lattice.
2. ~~**`ngs_grid.interpolate_biquadratic` must NOT be changed, and neither must
   `geoid18.py`.**~~ **SUPERSEDED for `geoid18.py` by WP-G1 (DESIGN.md #37):
   GEOID18 now reads nearest-node too, on the owner's replicate-NOAA
   instruction, gated by its own discriminating anchors.** What stands from
   this point: `ngs_grid.interpolate_biquadratic` itself is unchanged and kept,
   and no re-anchoring was folded into the vertical build — WP-G1 was its own
   package with its own gate, exactly as required. The measurement that
   motivated the caution stands too: against GEOID18's 20 frozen anchors, floor
   gives max 0.595 mm against nearest-node's 0.830 — inside ±0.5 mm truth
   noise, which is why those 20 could not decide anything.
3. ~~**The two NGS products genuinely differ in stencil convention.**~~
   **RESOLVED — they do not.** The open question this point raised ("whether
   GEOID18 would also prefer nearest-node anchoring if the truth set could
   resolve it") was answered at the WP-V4 gate by a 120-point sample where the
   anchorings diverge (floor rms 0.715 mm, nearest-node 0.454, DESIGN.md #36),
   corroborated by INTG's own source, and closed by WP-G1 (DESIGN.md #37).
   Both NGS products are nearest-node.

**Tolerance, derived rather than chosen:** the primary pin is exact —
`round(grid_value, 3)` equals NCAT's printed figure, 20/20 on both grids, and it
discriminates (floor anchoring fails it 8/20 on `.trn`, 6/20 on `.err`). The
secondary numeric pin is **0.0005 m**: NCAT prints to 0.001 m so a printed figure
carries ±0.5 mm, and the shift is `target − 200.000` where the 200.000 is the
request input echoed back rather than a rounded print, so only one term is
quantized. Measured max is 0.4707 and 0.4716 mm. **Do not loosen it to 2 mm or
5 mm**: 2 mm admits bilinear on `.err` and 5 mm admits the floor-anchored
biquadratic, and the tolerance would stop telling the schemes apart — the exact
failure mode DESIGN.md #31 already recorded once.

### 2.6 The wrong turn, recorded

The first pass looked for the grids at `geodesy.noaa.gov/PC_PROD/VERTCON/` (which
holds only the **1994** set) and then at **VDatum**, whose download page still
links back to that 1994 directory. `vdatum_VERTCON.zip` was obtained and
analyzed, and it contradicted #22 on four points — GTX not `.b`, big-endian not
little, millimetres not metres, three regional grids not one, and no error grid
at all. From its own manifest:

```
vdatum/core/vcn.inf   ->  released=02/24/2011
```

**It is VERTCON 2.0.** The 2025-06-23 `Last-Modified` on the zip is a
repackaging date, not a data date. Measured against NCAT it disagrees by **up to
43.85 mm across Michigan (mean 6.76 mm)** — against VERTCON 3.0's **2.657 mm max
(mean 0.697 mm)**. The correct product is **16× closer** to NGS's own service.

Two things follow. First, **#22's claims were about the right file all along**,
and the apparent corrections were an artifact of analyzing the wrong one — worth
recording because the discipline of "the source falsifies the plan, say so
plainly" (METHOD.md §2) cuts both ways: the plan was right and the recon was
wrong. Second, **the owner's `vdatum_VERTCON.zip` in the repo root is this same
superseded file** — byte-identical, SHA-256 `2e207e36…`. It is not used by this
plan and can be deleted; it is left in place because it is his file to remove.

### 2.7 Sentinels and non-finite values

Over the Michigan window (41.6–48.4 N, 90.6–82.2 W, 23,120 cells per grid):

| Grid | min | max | non-finite or sentinel |
|---|---|---|---|
| `.trn` | −0.411640 m | +0.348303 m | **0** |
| `.err` | +0.000004 m | +0.365599 m | **0** |

No `NaN`, no infinity, no `-88.8888`, no `9999.0`. The `-88.8888` GTX null
sentinel is a **VDatum** convention and is not present in the NGS `.b` files, so
that hazard belongs to the abandoned path. The reader still refuses non-finite
payloads, as `geoid18` does, because `load_grid` accepts any path.

### 2.8 The disclosure fact that changes §7

**The largest NGVD 29 uncertainty inside Michigan is 0.3656 m — 36.6 cm — at
43.05 N, 86.20 W** (the Lake Michigan shore near Muskegon). The modeled shift
there is **−0.1435 m**. The uncertainty is **255% of the shift itself**.

> **Two corrections made at the WP-V1/V4 gate, recorded rather than quietly
> applied.**
>
> **The shift was stated here as −0.1466 m, and it is −0.143529 m.** 43.05 N /
> 86.20 W is an *exact grid node* — row 381, column 776 — so no interpolation is
> involved and every scheme returns the stored value; NGS NCAT independently
> returns −0.144 m there, printing to 0.001 m. The ratio is 255%, not 249%. The
> σ figure, 0.365599 m, was re-measured from the committed grid and is exact.
>
> **The "0.001 m" floor below is not a competing measurement of §2.7's
> 0.000004 m — the two describe different things**, and neither should be
> "corrected" to the other. 0.000004 m is what the grid holds at its Michigan
> minimum (43.85 N / 84.95 W, reproduced exactly). 0.001 m is the resolution
> **NCAT prints to**, so it is the smallest value NCAT can ever display.
> Evidence, not inference: at 43.0 N / 84.5 W the grid holds 0.00065542 m where
> NCAT returns 0.001. **This resolves the question flagged for the owner at the
> WP-V3 gate.** The sentence below should read: across Michigan σ runs
> 0.000004 m to 0.365599 m in the grid; NCAT prints to 0.001 m.

Across Michigan, σ ranges from **0.001 m to 0.366 m** — a factor of 366. Any
single job-level constant hides that completely, and at that location it would
understate the uncertainty by two orders of magnitude while printing a shift to
the millimetre. This is the "modeled shift laundered into an exact-looking
number" risk of #22, located and quantified.

---

## 3. Architecture

Two registries, both mirroring `spc/frames.py` — which already demonstrates the
pattern: typed records, an explicit registry, and a `require_*` that refuses
loudly rather than passing through.

### 3.1 `michspc/spc/vertical.py` — new, core, stdlib only

```
VerticalDatum(code, name, citation, status)
    NGVD29, NAVD88            usable
    NAPGD2022                 declared, NOT usable  (mirrors NATRF2022)

VerticalTransformation(source, target, model, release, grid_key, sign,
                       uncertainty_citation, caveat)

VERTICAL_TRANSFORMATIONS: dict[(VerticalDatum, VerticalDatum), VerticalTransformation]
    (NAVD88,  NAVD88)   identity, explicit
    (NGVD29,  NGVD29)   identity, explicit
    (NGVD29,  NAVD88)   VERTCON 3.0 release 20190601, sign +1
    (NAVD88,  NGVD29)   VERTCON 3.0 release 20190601, sign -1   (§2.4)

require_vertical_pair(source, target) -> VerticalTransformation
```

Three properties this file must have:

- **No file I/O and no Qt.** The architecture tests enforce it. The grid value is
  passed *in*, exactly as `factors.factors_at` takes the geoid height as a
  parameter rather than reading the tile.
- **Identity pairs are explicit records, not a `source is target` shortcut.** A
  NAVD 88 → NAVD 88 job is legitimate, and the record must be able to say "both
  datums NAVD 88, no shift applied" rather than having that fall out of a branch.
- **The registry keeps every pair it has ever carried** — #32's backwards
  compatibility requirement, stated as a requirement, not an assumption.

### 3.2 `michspc/fileio/ngs_grid.py` — extracted, shared

The VERTCON `.b` header struct is **identical** to GEOID18's (`<4d3i`, IKIND
included), the longitude convention is identical (0–360 east), the geometry
validation is identical in kind, and both interpolators are needed by both
callers. Duplicating that into a sibling module would be two views of one
question, which is what this project forbids.

So: extract the shared substrate — header struct, `TileGeometry` checking, the
0–360 east conversion, `_lagrange3`, `bilinear`, `biquadratic`, the
non-finite payload refusal — and leave `geoid18` and `vertcon` as thin **policy**
layers over it.

**The extraction's own safety property:** every existing geoid test exercises
`geoid18`'s public API, so the whole geoid suite must pass **unchanged**. If it
does not, the refactor is wrong. Done in its own commit with no behavior change
in it.

### 3.3 `michspc/fileio/vertcon.py` — new, policy over the substrate

What is genuinely VERTCON's own, and not shared:

- **Fortran record markers** — absent in GEOID18. Validated on the header and on
  every row. This is a real integrity gate, not ceremony. **Corrected at the V4
  review gate:** the "total consumed byte count == file length" check this line
  originally also asked for was built and then removed as dead code — the
  header-derived length check runs before the walk and forces it, so the second
  refusal could not fire. A dead check advertised as an independent gate is worse
  than no check. The property is held by the length check, and by a test that
  walks both shipped files with its own arithmetic.
- **Two grids, loaded as a pair**, with a check that they share geometry (§2.2)
  — a mismatched pair would report one position's shift with another's sigma.
  **The pair exposes `reading_at` only**: separate `shift_m`/`sigma_m` accessors
  on the pair let a caller combine one position's shift with another position's
  sigma, and were removed at the V4 review gate.
- **Both grids are read by the nearest-node-anchored biquadratic** (§2.5a — NOT
  §2.5, whose `.trn` biquadratic / `.err` bilinear asymmetry is superseded).
  Pinned with the floor-anchored and bilinear variants shown failing the anchor
  lattice. **Do not write the "fails if the two are ever unified" test §2.5 asks
  for**: it would pin a defect.
- **A negative interpolated uncertainty is refused, not returned and not
  clamped** (§2.5a, V4 review). The raw interpolation stays available under a
  name that cannot be read as a sigma; `reading_at` reports the shift with the
  sigma marked unavailable, since the shift comes from the other grid and is
  unaffected.
- SHA-256 pins and a `VERTCON3_CONUS_GEOMETRY` expectation record, for the same
  reason `GEOID18_U3_GEOMETRY` exists.

Note `521 × 1181` and `1181 × 521` do **not** share a product, so a transposed
header is caught by length alone here — unlike GEOID18, where the geometry check
was the only thing that could catch it (amendment #11, finding 6). The geometry
check still earns its place for SLAT/WLON/spacing.

### 3.4 The geoid model registry

```
GeoidModel(name, tile_filename, sha256, geometry, vertical_datum, citation)
    GEOID18   g2018u3.bin    -> NAVD88
    GEOID12B  g2012bu3.bin   -> NAVD88
    (GEOID2022 arrives as a record -> NAPGD2022)
```

`vertical_datum` on the record is load-bearing, not documentation: it is what
lets the program refuse a GEOID2022 lookup against NAVD 88 heights, which is
#32's "two eras inside a single number." Both models available today are
NAVD 88, so the guard is **latent** — and it is exactly the kind of guard that
must exist before the case arrives.

**Module naming.** `geoid18.py` holding a two-model registry is a name that lies.
Rename to `geoid.py`; it touches `job.py`, `report.py`, `selftest.py`,
`single_point.py`, `window.py` and four test modules — wide, purely mechanical.
**Recommend doing it**, in its own commit, with no behavior change in it.

### 3.5 `JobSettings` changes

```
vertical_mode:          VerticalMode          HORIZONTAL | HORIZONTAL_AND_VERTICAL
source_vertical_datum:  VerticalDatum | None  required when vertical; None is a statement
target_vertical_datum:  VerticalDatum | None
geoid_model:            GeoidModel  | None    replaces apply_geoid: bool
```

`apply_geoid: bool` becomes `geoid_model: GeoidModel | None`, where `None` is a
statement — *"no geoid was applied to this job"* — the idiom `input_path` and
`output_directory` already use. This keeps `report.py`'s existing "Geoid model
not applied" branch honest and tested while **no interface offers it**, per the
owner's "no none." It is a capability of the core, not an option on the screen.

`job.run` refuses, in the style of the existing longitude refusal:

- vertical mode on, either datum absent;
- a `(source, target)` pair with no published transformation;
- ~~a geoid model whose `vertical_datum` is not the job's target vertical
  datum;~~ **SUPERSEDED (DESIGN.md #41): the rule is either-endpoint — the
  model's datum must match the source or the target, and the factors are
  computed from the height in the model's own era. The target-only rule would
  have refused NAVD88 → NGVD29 outright with advice nothing offers;**
- a point outside the VERTCON grid, where the horizontal result still stands and
  only the elevation is refused — the shape `GEOID_UNAVAILABLE` already has.

### 3.6 The order of operations in `_convert_row`

```
1. horizontal conversion                      (unchanged)
2. elevation: input unit -> metres            (unchanged)
3. VERTICAL SHIFT, source datum -> target     <-- NEW
4. geoid height lookup at the pivot           (unchanged position, shifted H)
5. factors_at(scale, H_target, N)             (unchanged)
6. elevation: metres -> output unit           (unchanged)
```

**Step 3 must precede step 4** because GEOID18's N is defined against NAVD 88.
Worth writing down: skipping the shift perturbs the *elevation factor* by only
`0.14 / 6,372,000 ≈ 0.02 ppm`, which is negligible — so nobody should mistake the
factor for the reason. **The reason is the Z value itself**, out by about 0.46 ft
in Michigan.

`ConvertedPoint` gains the shift, its sigma, and both datums. Its
`output_elevation` docstring — *"Unchanged by the conversion"* — is **repealed
for the Z column**, which #22 requires and which must then be said in every
output.

---

## 4. GUI

### 4.1 The mode toggle

Two `QRadioButton`s in a `QButtonGroup`, on the first row of the existing
**Conversion** group box, on **both tabs**, built by one shared helper in
`controls.py` — the way `longitude_combo` already serves both. Native widgets,
per METHOD.md §5.

> ( ) Horizontal   ( ) Horizontal + Vertical

Opens on **Horizontal**, which is today's behavior and asserts nothing about a
vertical datum. `QRadioButton` is the repo's existing idiom
(`elevation_in_file`); if the owner pictured a segmented pair of checkable
`QPushButton`s, that is a one-line change to the helper.

**Not above the tab bar.** A window-level toggle would be state shared between
the tabs, which amendment #26 forbids — the tabs own their own controls precisely
so neither can silently alter the other.

### 4.2 What expands

Selecting **Horizontal + Vertical** reveals two rows; selecting **Horizontal**
hides them. Hidden, not disabled — a disabled control that never becomes
relevant is clutter, whereas the longitude and angle-format selectors are
*disabled* because they become relevant again.

```
Vertical datum from:  [ — choose — ]
Vertical datum to:    [ — choose — ]
```

Both open **unanswered**, per §7's rule. Amendment #29's positive-west preselect
is a narrow, recorded exception for a control whose options are
indistinguishable from the numbers; these are not that.

### 4.3 The geoid dropdown

Replaces the Multi point tab's static `Geoid: GEOID18 (auto)` label, and is
**added to Single point, which has none today**. Built from the registry, so a
model added to it appears with no interface change — the property
`controls.zone_combo` already has. Opens on **GEOID18**. No "none" entry.

### 4.4 Enablement and invalidation

- Convert is gated on both vertical datums once vertical mode is on; the existing
  `settings() is None` gate extends naturally.
- **Every new control must reach `_invalidate_result` on the Single point tab.**
  This is the amendment #26 CRITICAL — a stale result surviving a control change
  with both copy paths armed, one click from the clipboard. Three new controls
  are three new ways to reproduce it. Each gets its own pin, and each pin gets
  falsified against the missing connection.

---

## 5. Disclosure

### 5.1 SETTLED — per-point sigma, on two surfaces of three

**Owner's decision, 2026-08-07:** per-point σ from the `.err` grid. It appears
on the **Single point panel** and in the **full-audit CSV**, and **not in the
clean PNEZD export**.

> **Corrected at the V4 gate.** This line originally said "read bilinearly
> (§2.5)". It is not: both grids are read by the nearest-node-anchored
> biquadratic (§2.5a), and bilinear on `.err` is wrong by 4.547 mm at the frozen
> Kalamazoo anchor where the shipped scheme is inside NCAT's 0.5 mm printing
> quantization. The owner's decision — per-point, on two surfaces of three — is
> unaffected; only the sentence about how the number is read was wrong.
>
> **WP-V7 also inherits a case this section did not anticipate:** at a small
> fraction of Michigan positions the error model interpolates below zero, which
> is not an uncertainty, and the reader refuses it rather than clamping. The
> shift at such a point is valid and is still reported. What the panel and the
> CSV say in that cell is WP-V7's to decide; what they must not say is a number.

He had earlier chosen a job-level cited constant, on my advice, when I believed
there was no error grid. There is one (§2.1), and §2.8 is what reopened it:
across Michigan σ runs **0.001 m to 0.366 m** — a factor of 366 — and at
43.05 N / 86.20 W the uncertainty is **255% of the shift** (corrected from 249%
at the WP-V4 gate — see the note in §2.8). A single constant
would understate that point by two orders of magnitude while the shift beside it
was printed to the millimetre. The earlier reasoning against a per-point number
was that NCAT's `sigOrthoht` looked like a constant 0.001 interpolation figure;
the lattice shows it is a real, strongly varying field, and our reader reproduces
it to **max 1.526 mm, mean 0.589 mm**.

**Keeping σ out of the clean export is not a reduction in disclosure — it is the
export's existing rule, and it predates this feature.** `exports.py` states it
directly: the clean file carries nothing but the five PNEZD fields, because "a
CAD import that meets an unexpected sixth column either fails or silently shifts
everything one field left." A σ column there would be the more dangerous
disclosure: it would either break the import or silently push the description
into the elevation field. The archive is a single ZIP precisely so the export
cannot circulate without the audit CSV and the record that carry the caveat
(#17), so nothing is lost by keeping the CAD-bound file clean.

**The job record keeps a summary, not a per-point column** — min, max and mean σ
across the job, in the shape `_factor_summary` already uses for the scale
factors, plus the caveat in METHOD. That follows the record's own standing design
("full record, but factors summarized," per-point detail left to the audit CSV,
#17) rather than being a new decision. Flagged here so the division of labour is
explicit: **the record says how uncertain this job was; the CSV says how
uncertain each point was.**

### 5.2 What gets said, and where

**Job record** — new and amended blocks:

- INPUT: the source vertical datum, named.
- OUTPUT: the target vertical datum, named, and that the clean export's Z column
  is in it.
- METHOD: the model and release (`VERTCON 3.0 release 20190601`), both grid
  filenames and both SHA-256s, the uncertainty **with its citation**, and NGS's
  supersession caveat — that published NAVD 88 benchmark values supersede a
  modeled shift, and that NGVD 29 network distortions of 20 cm or more exist.
  **§2.8 is the proof that caveat is not boilerplate: one such place is in
  Michigan.**
- ELEVATIONS: how many points were shifted, **min / max / mean σ across the
  job**, and that the shift is **modeled, not measured**. Any point whose σ
  exceeds its own shift is named — §2.8 proves that is a real Michigan case, not
  a hypothetical.

**Audit CSV** (`<stem>_full.csv`) — four new columns: source vertical datum,
target vertical datum, the shift applied, and **its σ**. The source-datum
elevation is carried too, so the file answers "how was this number derived"
without re-running anything, which is what that file is for.

**Single point panel**: source-datum elevation under INPUT; target-datum
elevation under OUTPUT; the shift with both datums named; and **σ**, as its own
labelled row with its own copy button like every other value. The tab writes
nothing, so a caveat not on screen does not exist for that user.

**Clean PNEZD export** (`<stem>.csv`) — **no σ, no shift, no datum column. Five
fields, unchanged.** The Z column holds the target-datum elevation and the record
says which datum that is. §5.1 says why this is the safer choice rather than a
weaker one.

**What the anchors actually prove, in the record in these words:** that MCX reads
NGS's grid the way NGS reads it. NCAT is an implementation of the same model, not
an independent measurement of the ground. Every other quantity in this program is
checked against an external truth; this one cannot be, and the record says so
rather than borrowing the credibility of the sentences around it.

---

## 6. Verification anchors

For DESIGN.md §8. Every expected value hand-derived in a comment; every new pin
falsified by seeding the defect it catches; suite green in `pytest` and `-O`.

| Anchor | What it proves | Measured bound |
|---|---|---|
| Frozen NCAT vertical conversions, 20 Michigan points | `.trn` reader and sign against NGS's own service | max 2.657 mm, mean 0.697 |
| The 43.0 N / 84.5 W anchor: −0.1402 m vs NCAT −0.1400 | sign, direction, metres — the #1/MATLAB-defect-2 class | 0.2 mm |
| Frozen NCAT `sigOrthoht`, same 20 points | `.err` reader | max 1.526 mm, mean 0.589 |
| ~~**`.trn` biquadratic beats bilinear; `.err` bilinear beats biquadratic**~~ **SUPERSEDED, see §2.5a — do not build this pin** | ~~the §2.5 asymmetry~~ it would pin a defect | ~~2.657 vs 7.430; 1.526 vs 12.406~~ |
| **Both grids read nearest-node-anchored biquadratic; floor-anchored and bilinear FAIL the lattice** | §2.5a. Every anchor rounds to NCAT's printed figure, 20/20 on both grids | 0.4707 mm `.trn`, 0.4716 mm `.err`, against 8.4573 / 3.0416 floor-anchored |
| ~~**GEOID18 still reads floor-anchored, and its suite still passes**~~ **SUPERSEDED by WP-G1 (DESIGN.md #37): GEOID18 reads nearest-node now, gated by its own 120-point discriminating anchor set** | at WP-V4 time the new interpolator was added alongside, never a replacement — re-anchoring released code was correctly left to its own package | 0.595 mm vs 0.830 on the 20 anchors (cannot discriminate); 0.715 vs 0.454 rms where the anchorings diverge |
| Fortran markers on header and all 521 rows; the file's length equals what its header implies | the structural check #22 predicted. **A separate "bytes consumed" refusal after the row walk is NOT to be added back** — it is forced by the length check and cannot fire (V4 review) | exact |
| A negative interpolated σ refuses through `sigma_m`, and `reading_at` still returns the shift | a negative is not an uncertainty; the shift is a different grid and is unaffected (V4 review) | exact, at 42.87 N / 83.81 W and 42.475 N / 83.125 W |
| The pair has no per-quantity accessor | a shift at one position must not be pairable with a σ at another (V4 review) | exact |
| `g2012bu3.bin` matches its pinned SHA-256 | the tile is bundled and not yet read; without a pin in code, one altered float passes every check (V4 review) | exact |
| `.trn` and `.err` share geometry | a mismatched pair cannot report one point's σ for another's shift | exact |
| Header geometry + SHA-256, both grids | refuses a substituted or transposed grid | exact |
| NGVD29 → NAVD88 → NGVD29 round trip | the inverse is one grid sign-reversed (§2.4) | 0.00 mm at 5 points |
| GEOID12B reproduces frozen NGS geoid API values | the second geoid model is read, not merely loaded | to be measured in V3 |
| A non-finite payload cell refuses | `load_grid` accepts any path | exact |
| **The clean PNEZD export has exactly five fields in every vertical mode** | σ, shift and datum never reach the CAD-bound file (§5.1) | exact |
| σ appears as a panel row with a copy button, and in `single_point_clipboard_text` | it is a number, so unlike warnings (#30) it belongs in Copy all | exact |
| End to end: file → `job.run` → ZIP → parsed audit CSV, vertical on and off | the path whose absence let the #20 record defects survive | — |
| Existing geoid suite passes unchanged after the §3.2 extraction | the refactor changed no behavior | exact |

No test touches the network. All anchors captured once and committed.

---

## 7. Work packages

Each ends with the suite green and a commit.

| WP | Contents |
|---|---|
| **V0** | **DONE** — §2. Data located, downloaded, format/sign/units/interpolation/inverse verified against NCAT, sentinels scanned, σ field characterized. |
| **V1** | **DONE** — the three files committed under NGS's own filenames, every SHA-256 matching §2.1's pin; `michspc.spec` names them all and derives `datas` from that list; `tools/build_release.py` compares the built bundle against `data/`. The 20-point NCAT lattice and the 5-point inverse set are frozen as `tests/fixtures/vertcon_anchors.py`. GEOID12B is pinned in `geoid18.py` and checked, though nothing reads it until V5. |
| **V2** | **DONE** — `fileio/ngs_grid.py` extraction (§3.2), geoid suite passing byte-unchanged, behaviour proved identical (DESIGN.md #35). |
| **V3** | **DONE** — `spc/vertical.py`: datums, registry, refusals, `apply_shift`. Stdlib only. Sign re-derived against #22's NCAT anchor (DESIGN.md #35). |
| **V4** | **DONE** — `fileio/vertcon.py`: marker-validated reader, the grid pair, geometry and checksum pins, and the **§2.5a** interpolation (nearest-node-anchored biquadratic on both grids — *not* §2.5's asymmetry, which would pin a defect). A negative interpolated σ refuses rather than being returned or clamped. |
| **V5** | Geoid model registry; `apply_geoid` → `geoid_model`; GEOID12B; `geoid18.py` → `geoid.py` rename as its own commit. |
| **V6** | `job.py` wiring; step 3 before step 4; datum-tagged elevations; the four refusals. |
| **V7** | Outputs: audit CSV, clean export, job record, results model — the disclosure of §5. |
| **V8** | GUI: mode toggle, expanding rows, geoid dropdown, both tabs, invalidation pins. |
| **V9** | End-to-end tests, `selftest.py` checks, build gates, release notes. |

**Interim adversarial gate after V4** — the reader is where a sign or scale error
hides and it is what V6–V8 build on. **Closing gate over the full diff.** Then
narrowing re-confirmation until approved (METHOD.md §3).

**Reviewer status: SUBSTITUTED at the V2/V3 gate, and it must not stay that way.**
Codex was unreachable again — no binary, no credential in the container — so that
gate ran with two independent adversarial reviewers on a different briefing but the
same model family as the implementers. That is weaker than the method asks for, and
it is recorded rather than glossed, per this section's own instruction. **Run the
interim and closing gates under Codex on the owner's machine.**

**V5 and V8's geoid dropdown do not depend on the vertical work at all.** If the
owner wants instruction 5 first and on its own, V2 + V5 + the dropdown half of V8
deliver it.

---

## 8. Risks

1. **Disclosure of a modeled shift** — #22's top risk, unchanged, and sharpened
   by §2.8: there is a place in Michigan where the uncertainty is 2.5× the shift.
   §5 is the whole answer to it, and it is the part most worth an adversarial
   reviewer's attention.
2. ~~**The §2.5 interpolation asymmetry being "simplified" later.** Pinned, with a
   test whose failure message says why the two differ.~~ **DISSOLVED — there is no
   asymmetry to protect (§2.5a).** Both grids are biquadratic; the risk that
   replaces this one is the *opposite*, that someone re-anchors a stencil to
   the floor-anchored variant, and that is what is pinned — on VERTCON by the
   NCAT lattice, and since WP-G1 on GEOID18 by its discriminating anchors too
   (GEOID18 no longer reads floor-anchored; DESIGN.md #37).
3. **Sign, byte order, units, marker layout.** Four ways to produce plausible
   garbage. All four are now pinned by measurement *before* code exists — which
   is the point of running V0 first.
4. **The `ngs_grid` extraction touching proven code.** Mitigated by requiring the
   existing geoid suite to pass unchanged, and by keeping it a separate commit
   with no behavior change in it.
5. **Backwards compatibility** (#32). The registry keeps every published pair;
   elevations stay datum-tagged; the datum in force is named in every output; an
   unestablished datum refuses rather than assuming the newest.
6. **Repo and installer growth** of 9.8 MB.
7. **`geoid18.py`'s name** becomes false the moment there are two models.
8. **Residual 2.657 mm against NCAT on the `.trn` grid.** NCAT prints to 1 mm, so
   one figure carries ±0.5 mm and the mean (0.697 mm) is at the quantization
   floor — but the max is not, and the suite tolerance must be the measured
   figure with the measurement recorded, not a round number chosen to pass.

---

## 9. Still human, still outstanding

Unchanged from CLAUDE.md, and this feature does not touch either: install on a
clean profile and run one real job end to end (METHOD.md §6), and get a real
PNEZD file from an actual job.

**And one this feature adds, which §2.8 makes concrete:** a vertical conversion
should be checked against a **published NAVD 88 benchmark** near a real job, not
only against NCAT. NGS's own caveat is that published benchmark values supersede
the model. NCAT cannot tell us whether the model is right about the ground — only
a datasheet can, and that lookup is the owner's to make.
