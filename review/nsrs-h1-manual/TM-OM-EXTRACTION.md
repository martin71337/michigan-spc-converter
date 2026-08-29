# H1 recon — NGS 5 §3.2 (transverse Mercator) and §3.3 (oblique Mercator), extracted and recomputation-verified (2026-08-28)

Opus recon from `docs/NOAA_Manual_NOS_NGS_0005.pdf`, every transcription
verified by recomputation; adjudicated by the session lead. PDF page =
printed page + 10 throughout. This is the transcription source for
`michspc/spc/tm.py` and `michspc/spc/omerc.py`; the code's own comments cite
the manual directly, and this file records the verification that the
transcription was faithful.

## Verification performed

| Check | Result |
|---|---|
| GRS 80 `r`, `U0..U6`, `V0..V6` (PDF p. 43) | reproduce printed values exactly |
| `F0..F6` conformal series (PDF p. 49) | reproduce printed values exactly |
| Table 3.22 `S0` for AZ-C, ID-E, NH (PDF p. 44) | reproduce to all 4 printed decimals |
| Alaska zone 1 `B, C, D, G, I, lambda0` (PDF p. 50) | reproduce exactly |
| Alaska zone 1 `F` | printed −0.32701 29554 **38**; exact double −0.32701 29554 **4998** (Δ 1.2e−11 ≈ 0.08 mm). Printed F/G self-consistent (√(1−F²) = printed G) — the manual's own rounding. **Do not pin a bit-match on F.** |
| TM forward/inverse round trip (transcription) | closes < 1 µm; γ and k from the two independent series agree to all digits |
| OM forward/inverse round trip | closes < 1 µm |
| OM γ and k vs finite difference | agree to fd noise (2e−8°, 1e−9) |

## 1. §3.2 Transverse Mercator (PDF pp. 42–48)

**Notation (§3.21, PDF pp. 42–43).** λ **positive west** in the manual.
Zone-defining: `lambda0` (CM), `E0` (false easting at CM), `phi0` (grid-origin
latitude), `N0` (false northing at phi0), `k0` (CM scale). Working: `omega`
rectifying latitude, `S` meridional distance, `S0 = k0·omega0·r`, `E' = E−E0`,
`n = (a−b)/(a+b) = f/(2−f)`, `t = tan phi`, `eta² = e'²cos²phi`, `R = a/W`
(prime-vertical radius — **collides with Lambert's mapping-radius `R`**),
`r` rectifying-sphere radius, `r0` geometric mean radius scaled to grid.
**TM's `Q` is `E'/R_f`, NOT isometric latitude** — a second name collision.
The manual overloads `t` (tan phi in §3.23–3.24; grid azimuth in §3.25).

**Zone constants (§3.22, PDF p. 43), GRS 80 printed values:**

```
r  = a(1−n)(1−n²)(1 + 9n²/4 + 225n⁴/64)      = 6367449.14577 m
u2 = −3n/2 + 9n³/16          v2 = 3n/2 − 27n³/32
u4 = 15n²/16 − 15n⁴/32       v4 = 21n²/16 − 55n⁴/32
u6 = −35n³/48                v6 = 151n³/96
u8 = 315n⁴/512               v8 = 1097n⁴/512
U0 = 2(u2 − 2u4 + 3u6 − 4u8) = −0.00504 82507 76
U2 = 8(u4 − 4u6 + 10u8)      =  0.00002 12592 04
U4 = 32(u6 − 6u8)            = −0.00000 01114 23
U6 = 128 u8                  =  0.00000 00006 26
V0 = 2(v2 − 2v4 + 3v6 − 4v8) =  0.00502 28939 48
V2 = 8(v4 − 4v6 + 10v8)      =  0.00002 93706 25
V4 = 32(v6 − 6v8)            =  0.00000 02350 59
V6 = 128 v8                  =  0.00000 00021 81
omega0 = phi0 + sin phi0 cos phi0 (U0 + U2cos²phi0 + U4cos⁴phi0 + U6cos⁶phi0)
S0 = k0 · omega0 · r
```

Table 3.22 (PDF p. 44) prints `S0` and `1/(2r0²)×10^14` for all 40 SPCS 83 TM
zones — derived-constant anchors in the Appendix-C role. Verified:
AZ-C-0202 = 3,430,631.2260 (phi0 31°00′, k0 1:10,000);
ID-E-1101 = 4,614,370.6555 (41°40′, 1:19,000);
NH-2800 = 4,707,019.0442 (42°30′, 1:30,000).

**Direct (§3.23, PDF pp. 44–45)** — angles radians:

```
L  = (lambda − lambda0) cos phi        [positive-west manual; SPCS 27 used the reverse]
omega, S = as §3.22 at phi;  R = k0·a/(1−e²sin²phi)^0.5
A2 = R·t/2
A4 = (1/12)[5 − t² + eta²(9 + 4eta²)]
A6 = (1/360)[61 − 58t² + t⁴ + eta²(270 − 330t²)]
N  = S − S0 + N0 + A2·L²[1 + L²(A4 + A6·L²)]
A1 = −R
A3 = (1/6)(1 − t² + eta²)
A5 = (1/120)[5 − 18t² + t⁴ + eta²(14 − 58t²)]
A7 = (1/5040)(61 − 479t² + 179t⁴ − t⁶)
E  = E0 + A1·L[1 + L²(A3 + L²(A5 + A7·L²))]
C1 = −t;  C3 = (1/3)(1 + 3eta² + 2eta⁴);  C5 = (1/15)(2 − t²)
gamma = C1·L[1 + L²(C3 + C5·L²)]
F2 = (1/2)(1 + eta²);  F4 = (1/12)[5 − 4t² + eta²(9 − 24t²)]
k  = k0[1 + F2·L²(1 + F4·L²)]
```

**Inverse (§3.24, PDF pp. 45–46) — NO iteration** (closed footpoint series):

```
omega_f = (N − N0 + S0)/(k0·r)
phi_f = omega_f + sin omega_f cos omega_f (V0 + V2cos²omega_f + V4cos⁴omega_f + V6cos⁶omega_f)
R_f = k0·a/(1−e²sin²phi_f)^0.5;   Q = (E − E0)/R_f
B2 = −(1/2)·t_f·(1 + eta_f²)
B4 = −(1/12)[5 + 3t_f² + eta_f²(1 − 9t_f²) − 4eta_f⁴]
B6 =  (1/360)[61 + 90t_f² + 45t_f⁴ + eta_f²(46 − 252t_f² − 90t_f⁴)]
phi = phi_f + B2·Q²[1 + Q²(B4 + B6·Q²)]
B3 = −(1/6)(1 + 2t_f² + eta_f²)
B5 =  (1/120)[5 + 28t_f² + 24t_f⁴ + eta_f²(6 + 8t_f²)]
B7 = −(1/5040)(61 + 662t_f² + 1320t_f⁴ + 720t_f⁶)
L = Q[1 + Q²{B3 + Q²(B5 + B7·Q²)}]
lambda = lambda0 − L/cos phi_f          [positive-west manual]
D1 = t_f;  D3 = −(1/3)(1 + t_f² − eta_f² − 2eta_f⁴)   [both minus signs
D5 = (1/15)(2 + 5t_f² + 3t_f⁴)                         confirmed at 400 dpi]
gamma = D1·Q[1 + Q²(D3 + D5·Q²)]
G2 = (1/2)(1 + eta_f²);  G4 = (1/12)(1 + 5eta_f²)
k = k0[1 + G2·Q²(1 + G4·Q²)]
```

**Accuracy/domain (PDF pp. 35, 45, 47):** "millimeter accuracy on any machine
handling 10 significant digits" (the >12-digit fragility warning is
Lambert-only); the manual calls A6/A7/C5/F4 and B6/B7/D5/G4 negligible
*inside SPCS 83 zone bounds* — **keep all terms unconditionally**: SPCS2022
LDPs are not those zones. §3.24's approximate `k = k0 + E'²/2r0²` is
convenience only; do not ship it. §3.25/§3.26 (arc-to-chord, line scale) out
of scope (deferred azimuth/distance feature).

## 2. §3.3 Oblique Mercator (PDF pp. 48–52)

**🚩 VARIANT FLAG, measured not inferred: the manual presents the
NATURAL-ORIGIN Hotine** (Alaska zone 1). At (phi_c, lambda_c) its equations
give u = 6,968,872.111 m, v = 0 — the false coordinates apply at the point
where the initial line crosses the equator, NOT at the centre.
**SPCS2022's designation "OMC = Hotine Oblique Mercator, center" fixes the
false coordinates AT THE PROJECTION CENTRE** (EPSG 9815 variant B; the
third-party DB and NGS's abbreviation gloss agree). The centre-variant
offset (subtracting u_c before rotation) is a required, separately-anchored
addition — getting it wrong misplaces every point by ~6,969 km, and the
frozen statewide-centre anchor (2,500,000.000 / 5,000,000.000 ift exactly)
is the discriminator.

Two further flags: the manual takes `cos alpha0 = +sqrt(1−sin²alpha0)`,
silently assuming |alpha0| < 90° — check Michigan's −26° rather than
inherit; and `alpha_c` enters twice (defining the skew AND as the u,v→N,E
rotation angle) — Michigan's published record has azimuth = rectified-skew
angle = −26° (both), so the two roles coincide here, verified against the
zone data, not assumed generally.

**GRS 80 conformal-latitude series (§3.32, PDF p. 49):**

```
c2 = e²/2 + 5e⁴/24 + e⁶/12 + 13e⁸/360
c4 = 7e⁴/48 + 29e⁶/240 + 811e⁸/11520
c6 = 7e⁶/120 + 81e⁸/1120
c8 = 4279e⁸/161280
F0 = 2(c2 − 2c4 + 3c6 − 4c8) = 0.00668 69209 27
F2 = 8(c4 − 4c6 + 10c8)      = 0.00005 20145 84
F4 = 32(c6 − 6c8)            = 0.00000 05544 30
F6 = 128 c8                  = 0.00000 00068 20
```
(**Distinct namespace from §3.23's TM F2/F4 scale coefficients.**)

**Zone constants (§3.33, PDF pp. 49–50):**

```
B   = (1 + e'²cos⁴phi_c)^0.5
W_c = (1 − e²sin²phi_c)^0.5
A   = a·B·(1−e²)^0.5 / W_c²
Q_c = isometric latitude at phi_c        [character-identical to Lambert §3.12 Q]
C   = arcosh[ B(1−e²)^0.5 / (W_c cos phi_c) ] − B·Q_c
D   = k_c·A/B
sin alpha0 = a·sin alpha_c·cos phi_c / (A·W_c)
lambda0 = lambda_c + { arcsin[ sin alpha0·sinh(B·Q_c + C) / cos alpha0 ] } / B
F = sin alpha0;  G = cos alpha0;  I = k_c·A/a
```

Alaska zone 1 seven-value test vector (PDF p. 50) with `tan alpha_c = −0.75`:
verified reproducible (see table above; pin F loosely per the rounding note).

**Direct (§3.34, PDF pp. 50–51):**

```
L = (lambda − lambda0)·B          [positive-west manual]
Q = isometric latitude at phi
J = sinh(B·Q + C);  K = cosh(B·Q + C)
u = D·arctan[ (J·G − F·sin L)/cos L ]          [needs atan2 away from the line]
v = (D/2)·ln[ (K − F·J − G·sin L)/(K + F·J + G·sin L) ]
N = u·cos alpha_c − v·sin alpha_c + N0         [natural-origin form; the
E = u·sin alpha_c + v·cos alpha_c + E0          centre variant offsets u by u_c]
gamma = arctan[ (F − J·G·sin L)/(K·G·cos L) ] − alpha_c
k = I·(1 − e²sin²phi)^0.5·cos(u/D) / (cos phi·cos L)
```

**Inverse (§3.35, PDF pp. 51–52) — NO iteration:**

```
u = (E−E0)·sin alpha_c + (N−N0)·cos alpha_c
v = (E−E0)·cos alpha_c − (N−N0)·sin alpha_c
R = sinh(v/D);  S = cosh(v/D);  T = sin(u/D)
Q = [ (1/2)·ln((S − R·F + G·T)/(S + R·F − G·T)) − C ] / B
chi = 2·arctan[ (e^Q − 1)/(e^Q + 1) ]
phi = chi + sin chi cos chi (F0 + F2cos²chi + F4cos⁴chi + F6cos⁶chi)
lambda = lambda0 − (1/B)·arctan[ (R·G + T·F)/cos(u/D) ]   [needs atan2]
```

For γ and k after an inverse the manual says: re-run the direct equations on
the recovered (phi, lambda) — there is no separate inverse γ/k. §3.36's
line-scale/arc-to-chord out of scope.

## 3. Worked numeric examples — ABSENT

**The manual contains no worked forward/inverse computation for §3.2 or
§3.3, and Appendix C is Lambert-only.** The 83 frozen beta NCAT anchors
(`review/nsrs-h1-anchors/anchors.json`) carry the end-to-end verification
burden, with Table 3.22's S0 values and Alaska zone 1's constants as the
hand-checkable derivation anchors. Nothing was substituted from any other
source.

## 4. Shared machinery already in the repo

| Manual symbol | Lives at | Note |
|---|---|---|
| `e²`, `e` | `ellipsoid.py:49,58` | identical in §3.21/§3.32 |
| `W` | `ellipsoid.py:62` | OM's W_c = W(sin phi_c); TM's working R = k0·a/W |
| `Q` isometric | `ellipsoid.py:70` | OM reuses it verbatim; **TM's `Q` is a different quantity** |
| prime-vertical R | `ellipsoid.py:108` | already cites §3.21 |
| geometric-mean r0 | `ellipsoid.py:115` + `lambert.py:236` | §3.15 closed form ≡ k0·√(MN), verified |
| domain refusals | `lambert.py:109,146` | reusable unchanged |

Needed and not yet present: `e'² = e²/(1−e²)`; `n = f/(2−f)` + rectifying
radius `r` (TM only); conformal-latitude series F0..F6 (OM inverse only).

**Longitude-sign deviation points under the repo's negative-west convention**
(the class `lambert.py:370-374` records once — TM has TWO, OM has FOUR):
TM: `L = (lambda0 − lambda)cos phi`; `lambda = lambda0 + L/cos phi_f`.
OM: `lambda0 = lambda_c − {…}/B`; `L = (lambda0 − lambda)B`;
`lambda = lambda0 + (1/B)arctan[…]`; plus `lambda_c` at transcription.
Convergence sign convention is consistent with `lambert.py` (positive east
of the CM), confirmed against the manual's own Wisconsin example (PDF p. 66).

## 5. Elevation-factor radius

No per-projection variation: PDF p. 59 gives the one mean radius
(6,372,000 m / 20,906,000 ft) for everything — exactly what `factors.py:34-38`
already cites. Nothing in §3.2/§3.3/§4 qualifies it by projection.
