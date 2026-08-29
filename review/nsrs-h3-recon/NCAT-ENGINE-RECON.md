# H3 recon — the search for the modernized NCAT engine (2026-08-28)

Opus recon, adjudicated by the session lead; the zone-table agreement with our
own pinned NGS capture was spot-checked by the lead (Kalamazoo, Detroit,
Houghton — exact). Clones were made read-only into the session scratchpad;
nothing third-party is vendored into this repository. This record preserves
what H3 needs: the verdicts, the citable constants, and the risks.

## Verdict

**The beta NCAT v3.0 engine is not published.** `noaa-ngs/ncat-lib` (cloned
at `77bcff1ce4a78fe06d0312102ada008aefcc2c62`, last push 2021-05-06) is the
legacy NADCON5 + VERTCON3 engine: zero occurrences of NATRF/2022-frame
content; its README's frame list ends at NAD83(2011). `noaa-ngs/HTDP` (cloned
at `59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c`, v3.6.0 of 2025-04-07) has zero
NATRF2022/NAPGD2022/GEOID2022 content, and its README warns "HTDP should NOT
be used to transform between NAD 83 realizations." The `noaa-ngs` org has 9
repos total; GitHub-wide code search for SPCS2022 returns nothing of NOAA's.
**DESIGN.md #61's reference-implementation sentence is annotated accordingly:
H3's oracles are the frozen beta NCAT web-app anchors and NOAA TR NOS NGS 63
(17,338,722 bytes, HEAD-captured at N0, not yet read).**

Licenses (ncat-lib and HTDP carry identical text): US Government work, not
subject to US copyright (17 U.S.C. §105); derivative works permitted.

## The transformation shape, from the best available sources

**ITRF2020 → NATRF2022 is a 3-parameter time-dependent rotation — all seven
static Helmert parameters are zero.** Confirmed twice: NGS's beta NATRF2022
page prose ("identical to ITRF2020 at epoch 2020.0… rotates with the stable
part of their tectonic plate") and a third-party PROJ database
(`jjimenezshaw/NSRS-2022-PROJ` at `db96341…`, data captured from
beta.ngs.noaa.gov 2026-04-24 — a LEAD, not an authority) whose record reads:
tx=ty=tz=0, rx=ry=rz=0, ds=0, all translation/scale rates 0, rate_rx=0.046,
rate_ry=−0.704, rate_rz=−0.047 mas/yr, epoch 2020.0 — matching our frozen
EPP2022 CSV exactly.

**⚠ SIGN-CONVENTION CONFLICT, unresolved — the top H3 risk.** The third-party
DB tags the record EPSG method 1056 (time-dependent **Coordinate Frame**
rotation); NGS's page prose ("rotation is positive counterclockwise following
the right-hand rule") reads as **Position Vector**. The two differ by the
sign of all three rotations — roughly **0.4–0.9 m at Michigan's latitude over
the 2010→2020 span**. A discriminating anchor from the frozen beta-NCAT
lattice settles it numerically; no transformation code is accepted before it
does.

**The NAD83(2011) ↔ ITRF leg — real NGS code, citable.** HTDP composes two
ITRF94-relative Helmerts; there is no direct NAD83↔ITRF2020 set. Selection of
the IGS-convention block hinges on either endpoint being NAD83
(`htdp.f:2900,2941`). Verbatim, `htdp.f`:

NAD83(2011/CORS96/2007), index 1 (`htdp.f:3652-3666`), refepc 1997.0:
```
tx=0.9910 m  ty=-1.9072  tz=-0.5129   (rates 0)
rx=0.02579" ry=0.00965" rz=0.01166"   (arcseconds, /rhosec to radians —
drx=0.0000532" dry=-0.0007423" drz=-0.0000316" per yr;  the in-code "mas"
scale=0  dscale=0                      comment is WRONG: these are arcsec)
```

ITRF2020, index 17 (`htdp.f:3970-3984`), refepc 2010.0:
```
tx=-0.01290 m ty=0.00241 tz=0.02827   dtx=-0.00079 dty=0.00070 dtz=0.00124
rx=-0.00029978" ry=0.00042037" rz=0.00031714"
drx=-0.00001347" dry=0.00001514" drz=0.00001973" per yr
scale=0.05109e-9  dscale=0.07201e-9
```

Application (`frit94`, `htdp.f:4507-4518`): parameters evaluated at
`date − refepc`, rotations applied **small-angle linearized** (never exact
trig); the inverse (`toit94`) negates parameters rather than inverting the
matrix. Epoch propagation (`TRFPOS`, `htdp.f:2914-2961`): equal epochs → the
Helmert output stands, no velocity model touched; differing epochs → Helmert
first, then velocity propagation as a difference of two `COMPSN` evaluations
(`NEWCOR`, `htdp.f:7370-7398`) with point-in-polygon region lookup that
refuses outside modeled regions.

**Whether beta NCAT composes exactly these HTDP values is unverified — the
frozen anchor lattice is the test.** The plan's H3 acceptance bar applies.

## The epoch question (#61)

Not resolvable from source (none exists). The data strongly implies "Input
Epoch 2020.00" reports the OUTPUT frame's reference epoch and that a
2010.0→2020.0 propagation is implied — recorded as **inference, not a source
reading**. H3 resolves it against the multipoint NCAT surface
(epochx/epochy) and the frozen anchors.

## The printed ±0.02 m sigma

**Source not found.** HTDP computes no uncertainties (its JVN/JVE/JVU
300/300/500 literals are fixed-format Bluebook filler — never surface them);
the third-party DB says accuracy 0.01 m for the ITRF2020→NATRF2022 record.
Legacy ncat-lib RSSes NADCON5 grid sigmas across chained steps
(`Transformer.java:339-341,405-407`) but sums the VERTICAL sigma linearly
(`Transformer.java:361`) — an asymmetry worth knowing. How beta NCAT gets
±0.02 m for the frame leg is an open H3 question; until answered, MCX's
record can quote NCAT's printed figure per frozen anchor as a fact, never
derive one.

## SPCS2022 / projection engines

No public SPCS2022 computation code exists. ncat-lib's legacy engines are
shape references only:

- **Oblique Mercator** (`OMTransformation.java`): Hotine, closed-form, no
  iteration; forward at :51-65, inverse a 4-term even cosine series at
  :82-95; **13 precomputed constants per zone arrive in a properties file —
  the derivation from defining parameters is absent from every source.**
  The statewide Michigan zone is **EPSG 9815 Hotine variant B** (third-party
  DB, consistent with NGS's own "OMC … center" abbreviation): false
  coordinates at the projection CENTRE (E 1,524,000 m / N 762,000 m = exactly
  5,000,000 / 2,500,000 ift), azimuth = rectified-skew angle = −26.0°,
  k₀ 0.9998 at the centre, centre 45°N/86°W.
- **Lambert** (`LambertTransformation.java:196-212`): same §3.1 shape as
  MCX's; its inverse is a fixed 3-iteration Newton with no convergence test —
  MCX's converge-with-ceiling idiom is strictly stronger.
- **ECEF↔geodetic**: HTDP iterates (`FRMXYZ`, tol 1e-13 on tan reduced
  latitude, 10-iteration cap, `STOP 666` on failure); ncat-lib solves a
  closed-form quartic (`XyzTransformation.java:57-95`). Either is citable;
  MCX picks at H3 with the house iteration idiom if iterative.
- **Elevation factor**: ncat-lib uses the Gaussian mean radius per point
  (`CoordinateTransformation.java:316-323`), where MCX uses the manual's
  constant mean radius — a recorded difference of method authority (manual
  p. 59), not a defect.
- **No-height behaviour**: ncat-lib writes N/A for the combined factor when
  no height is given — same doctrine as MCX's `factors_at`.

## Corroborating negative worth keeping

ncat-lib's NADCON5 stencil (`Nadcon.java:190-193`, `Interpolator.biquadratic`
Newton-Gregory 3×3) is logic-identical to `Vertcon.java`'s — the nearest-node
half-cell anchoring MCX replicated at #36/#37 matched NOAA across two grid
families, not one. NADCON5 never calls its own `bilinear()`.

## Print quantization (legacy, for tolerance context only)

ncat-lib formats: lat/lon %.10f, N/E %.6f (JSON layer re-quantizes to
%,.3f), scale/convergence %.8f, DMS seconds %.5f with explicit 60-carry;
sigmas %.6f arcsec / %.3f m. **The beta app's 0.03055″-style printing is its
own unpublished layer — derive H3 tolerances from the frozen anchors' own
printed precision, not from ncat-lib's.**
