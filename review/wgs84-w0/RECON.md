# W0 recon: how NGS HTDP v3.6.0 moves WGS 84 / ITRF at epoch t to and from NAD 83(2011) epoch 2010.0, in Michigan

Opus recon subagent, 2026-10-20. Nothing under `michspc/` or `tests/` was touched,
and nothing is committed. **The lead has not reviewed this yet.**

**Source.** `github.com/noaa-ngs/HTDP` at commit
`59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c` (v3.6.0, `htdp.f:27-28` "April 7, 2025").
I treated it as untrusted data: I only hashed, read and compiled it, and ran no
script from the clone. The SHA-256 of every `.f` file is in `htdp_truth.json`
under `provenance.source_sha256`.

**Binary.** The lead's `htdp_linux` (`gfortran -O0 -std=legacy -w *.f`, GNU
Fortran 13.3.0, x86_64) has sha256 `3738c50c…f77f8f`. My own -O0 rebuild of
the same sources is byte-identical to it.

All line numbers below are `htdp.f` unless another file is named.

## 0. Headline

- **An independent stdlib-Python transcription (`experiment.py`) reproduces the
  binary to the printed digit on every record.**
  - 45,408 of 45,408 output records are identical in all three printed fields.
  - Coverage: 8 frames × 6 epochs × 3 heights × 86 positions, forward,
    reverse and round-trip, plus 32 calendar/decimal date runs.
  - It also matches HTDP's velocity listing (option 2) on all 172 site-frames.
  - The worst residual of the unrounded experiment against the printed HTDP
    output is exactly half a print unit in every group:
    - N 5.56e-6 m (half of 1e-10°)
    - E 4.17e-6 m
    - U 5.00e-4 m (half of 1 mm)
- **HTDP's path is not symmetric.** It always evaluates the Helmert at the
  INPUT epoch. It then propagates in the OUTPUT frame with that frame's velocity
  (§1.3). So:
  - WGS84@t → NAD83@2010 = Helmert(t) + NAD83 intraplate velocity × (2010 − t).
  - NAD83@2010 → WGS84@t = Helmert(2010) + full ITRF plate velocity × (t − 2010).
- **The velocity term is real and not negligible.** A Helmert-only
  implementation misses HTDP by these amounts (worst, in the box):

  | Direction | Epoch | N | E | U |
  |---|---|---|---|---|
  | Forward | 2026.8 | 3.1 cm | 4.2 cm | 2.1 cm |
  | Reverse | 2026.8 | 3.7 cm | 28.5 cm | 0.6 cm |
- **All of Michigan lies in one velocity region: HTDP region 6, "eastern CONUS"**,
  a 0.5° grid with bilinear interpolation. There is no region boundary, refusal,
  earthquake term or postseismic term anywhere in lat 41.5–48.5, lon −90.6 to
  −82.0. The nearest boundary is 50.0°N, 1.5° north of the box (§2).
- **The grid's vertical velocity is 0.00 at all 4,717 nodes.** The −1.0 to
  −1.25 mm/yr "up" velocity HTDP reports in NAD 83 comes entirely from the
  frame translation-rate and scale-rate terms. It is not a GIA model (§3).
- **Build flags:**
  - -O2 is byte-identical to -O0 on every run.
  - An x87-arithmetic -O0 build flips the last printed digit (1e-10°) on one
    record in each of 11 of the 176 runs.
  - An -O2 + x87 build is **broken** in HTDP's ITRF2008 velocity listing (§4).

## 1. The transformation path (TRFPOS, menu option 4, file option 3)

### 1.1 Frames, menu → internal index, ellipsoid

`MENU1` (`4667-4797`) maps the menu number to an internal index (`kopt`) and a
24-character name (`mframe`):

| menu | name | iopt | Helmert set | ellipsoid used for φλh ↔ XYZ |
|---|---|---|---|---|
| 1 | NAD_83(2011/CORS96/2007) | 1 | own | GRS80 |
| 8 | WGS84(G1150) | 18 | own (`3986-4009`, `4399-4422`) | **WGS84** |
| 9 | WGS84(G1674) | 19 | own (`4011-4034`, `4424-4447`) | **WGS84** |
| 10 | WGS84(G1762) | 15 | **= ITRF2008** | **WGS84** |
| 11 | WGS84(G2139) | 16 | **= ITRF2014** | **WGS84** |
| 12 | WGS84(G2296) | 17 | **= ITRF2020** | **WGS84** |
| 24 | ITRF2008 or IGS08/IGb08 | 15 | `3917-3937` | GRS80 |
| 25 | ITRF2014 or IGS14/IGb14 | 16 | `3939-3960` | GRS80 |
| 26 | ITRF2020 or IGS20/IGb20 | 17 | `3962-3984` | GRS80 |

**The ellipsoid is chosen from the first five characters of the frame NAME,
not from the index** (`3221-3224` for the input frame, `3240-3243` for the
output frame).
- `'WGS84'` gives f = 1/298.257223563 (`154`); everything else gives GRS80,
  f = 1/298.257222101 (`152`).
- `MODEL` (`140-176`) is called inside every `TOXYZ` (`904`) and `FRMXYZ` (`930`).

**So WGS84(G2296) and ITRF2020 share a Helmert but are NOT the same
transformation in HTDP.** The same input numbers are converted to XYZ on
different ellipsoids. Measured, for menu 12 minus menu 26, in the box:

- Unrounded (experiment Supplement A):
  - Forward: dN +0.104 to +0.105 mm, dE 0, dU +0.046 to +0.059 mm.
  - Reverse: the same with opposite sign.
- In HTDP's printed output: dN = 1 unit in the 10th decimal, and dU flips a
  mm digit on some records (0 or 1 mm).
- Pairs 11/25 and 10/24 are identical in size.
- The experiment with the frame-12 ellipsoid forced to GRS80 reproduces HTDP's
  frame-26 output on 258 of 258 records.
- **Not citable as negligible in principle:** about 0.1 mm north is 10× HTDP's
  print precision.

### 1.2 Helmert parameters (SETTP `3618-4060`), verbatim

**Units.** Rotations are arcseconds divided by `rhosec` (arcsec per radian,
`165`).
- The in-code comment "changed rotations from radians to **mas**" at `3650`
  (repeated at `4063`) is wrong; the values are arcseconds.
- Proof by the code's own previous-value comment: `rx(1) = 0.02579d0 / rhosec
  !Previous 1.25033d-7 rad` (`3658`), and 0.02579″ = 1.25033e-7 rad.

Every set is **ITRF94 → frame**, evaluated at `date − refepc` (`4507-4514`).

Fields: tx ty tz (m), dtx dty dtz (m/yr), rx ry rz (″), drx dry drz (″/yr),
scale, dscale (/yr), refepc.

`/tranpa/`, the IGS convention (ITRF96 ≠ ITRF97):

| iopt | lines | T (m) | Ṫ (m/yr) | R (″) | Ṙ (″/yr) | s, ṡ | ref |
|---|---|---|---|---|---|---|---|
| 1 NAD83 | 3652-3666 | 0.9910, −1.9072, −0.5129 | 0,0,0 | 0.02579, 0.00965, 0.01166 | 0.0000532, −0.0007423, −0.0000316 | 0, 0 | 1997.0 |
| 15 ITRF2008 | 3923-3937 | −0.00243, −0.00389, 0.01365 | −0.00079, 0.00060, 0.00134 | −0.00012467, 0.00022355, 0.00006065 | −0.00001347, 0.00001514, 0.00001973 | −1.71504e−9, 0.10201e−9 | 1997.0 |
| 16 ITRF2014 | 3946-3960 | −0.01430, 0.00201, 0.02867 | −0.00079, 0.00060, 0.00144 | −0.00029978, 0.00042037, 0.00031714 | same as 15 | −0.36891e−9, 0.07201e−9 | 2010.0 |
| 17 ITRF2020 | 3970-3984 | −0.01290, 0.00241, 0.02827 | −0.00079, 0.00070, 0.00124 | same as 16 | same as 15 | 0.05109e−9, 0.07201e−9 | 2010.0 |
| 18 G1150 | 3995-4009 | −0.00580, −0.00019, −0.00513 | −0.00069, 0.00070, −0.00046 | same as 16 | same as 15 | 4.83109e−9, 0.18201e−9 | 2010.0 |
| 19 G1674 | 4020-4034 | −0.00870, 0.00091, 0.02707 | −0.00079, 0.00060, 0.00134 | −0.00056978, 0.00069037, −0.00006286 | same as 15 | 6.51109e−9, 0.10201e−9 | 2010.0 |

`/tranpa1/`, the IERS convention (ITRF96 = ITRF97):
- Row 1 is identical (`4065-4079`).
- Rows 15–19 are at `4336-4350`, `4359-4373`, `4383-4397`, `4408-4422` and
  `4433-4447`; they are transcribed in `experiment.py`.
- The rate DIFFERENCES between any two of frames 15–19 are identical in the
  two conventions. Only the static offsets differ, by up to cm.

**Which set is used.**
- If either endpoint is NAD 83, TRFPOS uses `/tranpa/` for the position
  (`2808, 2818, 3229-3235`). This holds for both of our directions.
- **Exception, inside `PREDV` (velocity only):** when the input frame is not
  NAD 83, `XTO08` (`2737-2743`) and `VTRANF_IERS` (`7457-7461`) use
  `/tranpa1/`. This only shifts the position used for the velocity-grid lookup
  by mm–cm, which is immaterial on a 0.5° grid, and the experiment reproduces
  it exactly.
- There is no direct NAD83↔ITRF20xx set: every hop is frame → ITRF94 → frame.

**Application.**
- `toit94` (`4572-4617`) applies frame → ITRF94 by **negating** all seven
  parameters and their rates.
- `frit94` (`4475-4521`) applies ITRF94 → frame.
- Both use **small-angle linearized** rotations and scale:
  `x2 = T + ds·x + rz·y − ry·z` and so on (`4516-4518`), with
  `ds = 1 + s + ṡ·dt`.
- The negation is not an exact inverse. The second-order error is about 1e-7 m,
  measured as the h-independent round-trip floor in §5.

### 1.3 Epoch handling and order of operations, per record (`3175-3294`)

1. **Input to XYZ.** ELPSD is set from the input frame name. The record is
   converted with `ylat = lat·3600/rhosec` (`3216-3218`) and then
   `TOXYZ(ylat, −ylon, eht)` (`3226`). Longitude is positive west in HTDP's
   files.
2. **Helmert at the INPUT date.** `TOIT94(…, date1, iopt1)` then
   `FRIT94(…, date1, iopt2)` (`3229-3235`). **This is always DATE1, the input
   epoch, whichever direction is run.**
3. ELPSD is set from the output frame name (`3240-3243`).
4. **If `min1 == min2`** (the two dates fall on the same day; see §1.5):
   `FRMXYZ` and output. Helmert only, no velocity (`3276-3283`).
5. **Otherwise:**
   - `FRMXYZ` converts to the output frame's φλh at date1 (`3246`).
   - **PREDV** (`7400-7469`):
     - `TOXYZ` on the output ellipsoid.
     - `XTO08` maps that position to ITRF2008 as if it were in frame
       **iopt1** at date1 (`7438`). If iopt1 = 15, the position is used
       unchanged (`7428-7436`).
     - `GETREG` finds the region (`7443`). Region 0 is "outside the modeled
       region" (`3251-3253`), and the record is written as a refusal line.
     - `COMVEL` returns the ITRF2008 velocity in mm/yr (`7450`).
     - `TOVXYZ` / `VTRANF` (15 → iopt1) / `TOVNEU` convert the velocity into
       frame iopt1 (`7455-7463`).
     - **It then resets ELPSD to GRS80** (`7465-7466`).
   - Back in TRFPOS: `TOVXYZ`, then `VTRANF(x, y, z, …, iopt1, iopt2)`, which
     uses the **input-frame XYZ** of step 1 (`3255, 3264-3268`), then `TOVNEU`
     (`3271`). The velocity is now in the output frame.
   - **NEWCOR** (`7370-7398`) calls `COMPSN` (`7303-7368`) for min1 and for
     min2 and differences them:
     - `dtime = (MIN − ITREF)/525960` (Julian years from 2010-01-01 00:00,
       `7322`; `ITREF` is set at `168-173`).
     - `RADR8T`/`RADII` turn mm/yr into rad/yr (`405-419`, `976-988`).
     - φ += vN·dt/M, λW −= vE·dt/(N cos φ), h += vU·dt/1000 (`7324-7326`).
     - `RADII` has **no height term** (see §5), and runs on **GRS80** even for
       WGS84 frames, because of the reset in PREDV.
   - Then the earthquake loop (`7333-7359`) and `PSDISP` (`7362-7366`); both
     contribute zero in Michigan (§2).
6. Output: `ylatt·rad2deg` with `rad2deg = 180/3.14159265358979` (a
   truncated π, `2766`), written as `2f16.10,f10.3` (`3293`), longitude
   positive west.

**XYZ ↔ geodetic.**
- `TOXYZ` (`895-916`) is closed form.
- `FRMXYZ` (`919-974`) iterates on the tangent of latitude:
  - at most 10 iterations, tolerance 1e-13 (`926`);
  - on failure, the callers `STOP 666`;
  - the height formula switches at |φ| = 0.7854 rad = 45.00002° (`957-961`),
    which lies inside Michigan.
- Probes at 44.9999°, 45.0° and 45.0001° all reproduce exactly.

### 1.4 What that means for the two directions

| | Helmert evaluated at | velocity frame | velocity magnitude (Michigan) |
|---|---|---|---|
| WGS84@t → NAD83@2010.0 | **t** | NAD 83 (intraplate residual) | N −1.87…−0.12, E +1.76…+2.51, U −1.25…−1.01 mm/yr |
| NAD83@2010.0 → WGS84@t | **2010.0** | WGS84 = ITRF (full plate motion) | N −2.18…+1.70, E −16.94…−15.34, U −0.33 mm/yr |

These ranges are from the experiment over the in-box lattice; the reverse
WGS84(G2296) row is Supplement C. Velocity is constant in time; there is no
acceleration term.

### 1.5 Dates: GETMDY (`7842-7995`) and IYMDMJ (`7997-8084`)

**Calendar entry (option 1, `7886-7922`).** This is the owner's choice.
- `MJD = IYMDMJ(y, m, d)`, an integer.
- `DATE = y + (MJD − MJD(y,1,1)) / (MJD(y+1,1,1) − MJD(y,1,1))`: a
  day-of-year fraction over a 365- or 366-day year (`7917-7919`).
- `MINS = MJD·1440` (`7920`).
- Both refer to **00:00 UTC at the start of the date** (the prompt text at
  `7879-7880` says so).
- Leap years come from the MJD difference (366); there is no separate rule.
- The checks are only: year > 1906, month 1–12, day 1–31 (`7891-7911`).
  **No day-in-month check. Driven and confirmed:** `2 30 2025` is accepted,
  printed as "02-30-2025", and gives output identical to `3 2 2025`. The same
  holds for `2 31` and `4 31`. **MCX must validate calendar dates itself.**

**Decimal entry (option 2, `7924-7970`).**
- DATE is used as typed, for the Helmert.
- MINS is derived as `MJD(y,1,1) + IDINT((DATE − y)·ndays)` days, i.e.
  truncated to 00:00 of a day (`7941-7963`).
- **The floating-point truncation often lands one day early:**
  - `2026.8` → velocity clock 10-19-2026, though 2026 + 292/365 is 10-20.
  - `2024.1612021857923` (HTDP's own DATE for 2/29/2024) → 02-28.
  - `2025.1616438356164` (3/1/2025) → 02-28.
  - `2026.7972602739726` (10/19/2026) → 10-18.
  - 12/31/2024, 7/2/2015 and Jan 1 dates survive.
- The header HTDP prints shows the truncated date, and the experiment
  reproduces every header.
- Effect of one lost day on output: up to 0.011 mm N and 0.053 mm E (reverse
  direction, plate motion), and a 1 mm height digit flip on some records.
- **Calendar entry avoids this. It is the cleaner input path.**

**The two clocks.** The Helmert runs on DATE (calendar-year fraction). The
velocity runs on MINS in Julian years of 365.25 days. They disagree by
`dT = (DATE − 2010) − (MINS − ITREF)/525960`:
- 1997.0: −0.000684 yr
- 2015.5: +0.002396 yr
- 2026.8: +0.003285 yr
- calendar 10/20/2026: +0.000548 yr

dT multiplied by the ~17 mm/yr plate rate is the round-trip non-closure (§5).

## 2. The velocity model in Michigan

**Region lookup.**
- `GETREG` (`277-303`) tests regions 1…65 in order and takes the first
  polygon that contains the point.
- The test is `POLYIN` (`306-402`), a crossing count in which **a point on
  the border counts as inside** (return 2, `396`).
- Polygons are in `initbd.f`, in degrees (positive east), converted to
  radians by `GETBDY` (`269-273`).
- The lookup position is the point's **ITRF2008** φλ (`XTO08`), not the
  input position.

**Region 6, "eastern CONUS"** (`initbd.f:37-40`), is the rectangle
lat 24–50, lon 250–294 E (−110 to −66).
- Regions 1–5 (`initbd.f:17-36`) are California, the Pacific Northwest and
  western CONUS rectangles, all west of 253 E.
- **The whole box lat 41.5–48.5, lon −90.6…−82.0 is inside region 6 and in
  none of 1–5.** That covers the Lower and Upper Peninsula, Isle Royale
  (48.0, −88.9), all the Great Lakes water probed, and margins into WI, IN,
  OH and Ontario.
- Margins: 1.5° to the north edge (50°N), 17.5° to the south edge, 19.4° to
  the west edge and 16° to the east edge.
- **No region boundary crosses the box, so there are no straddling points to
  test inside it.**

**The model.**
- `COMVEL` (`422-488`) uses the grid for regions 1–10 (`458-480`) and a plate
  rotation for regions 14–65 (`441-456`, `PLATVL` `490-662`).
- Grid 6 is in `initvl.f:42981-47704`: GRDLX/UX 250/294, GRDLY/UY 24/50,
  88 × 52 cells of 0.5°, 4,717 nodes (89 × 53), NBASE 128808.
  - Each node is (VN, VE, VU) in mm/yr, **relative to ITRF2008**
    (`424`, `7450`).
  - Node (I, J) is at `initvl.f` line 42988 + (I−1)·53 + (J−1).
  - The values are Fortran REAL literals stored into DOUBLE, so they are
    **single-precision values**. I confirmed this with my own gfortran test
    program, and the experiment uses `f32()`.
- Interpolation: `GRDWEI` (`1542-1631`) computes cell indices
  `I = IDINT((x − 250)/0.5) + 1` (and the same for J) and plain bilinear
  weights on degrees. `GRDVEC`/`IUNGRD` (`1635-1744`) fetch the four corners.
- The interpolation is continuous everywhere inside region 6: **no
  discontinuity in the box.**
- Range in the box, ITRF2008 frame: N −2.19…+1.71, E −16.94…−15.34,
  **U 0.00** mm/yr.

**Earthquakes.**
- `initeq.f` holds NUMEQ = 33 models (`initeq.f:24896`).
- All 33 epicentres are in California or Alaska, with radii of influence of
  100–2,000 km.
- The test (`7341-7345`) is HTDP's own flat-earth distance. Evaluated over
  every point, every epoch and both directions, the closest approach is
  **1,291 km outside** the nearest radius.

**Postseismic.**
- `PSDISP` (`8086-8180`) has a single grid, Denali 2002, covering 210–225 E
  and 60–66 N (`initps.f:10-16`).
- Michigan fails `GRDCHK`, so the displacement is identically zero.
- The experiment raises an error if either the earthquake or the postseismic
  term would ever apply. Neither fired.

**The nearest discontinuity is the 50°N edge of region 6**, beyond the box.
North of it is region 14, the NA plate model (ITRF2008 rotation
0.17/−3.209/−0.485 e−9 rad/yr plus translation 0.41/0.22/0.41 mm/yr, `577`,
`591`, `605`, `656-658`). HTDP's velocity listing at 88°W:

| | 49.9°N | 50.0°N | 50.1°N |
|---|---|---|---|
| ITRF2008 frame | N −1.35, E −16.81, U 0.00 (grid) | N −1.35, E −16.79, U 0.00 (grid, on border) | N +0.05, E −17.22, U +0.18 (plate) |

That is a step of 1.4 mm/yr north and 0.4 mm/yr east. In the NAD 83 frame the
50.0 probe already falls on the plate side, because its ITRF2008 position is
about 1 m north of its NAD 83 position.

- The NA polygon (`initbd.f:86ff`) is **not** transcribed. The experiment
  assumes region 14 north of 50°N. That assumption is used only for the three
  beyond-box probes, where it reproduces HTDP exactly.
- **An edge case worth knowing:**
  - A point exactly on lat 50.0 in ITRF2008 is "inside" region 6 (border
    rule). It gets J = 53, and GRDVEC reads row J = 54, which is past the end
    of grid 6.
  - The `/VGRID/ B(210000)` array is flat, so those entries come from grid 7's
    Alaska data (`initvl.f:47794`, `47821`).
  - The weight on them is exactly 0.0, so the result is unaffected. The
    experiment transcribes the two out-of-bounds nodes literally.
  - This is not reachable from Michigan.

## 3. Vertical

- Ellipsoid height goes through the full 3-D Helmert in XYZ, and then
  through `HTT = HT + VU·dt/1000` (`7326`). **The up velocity IS applied.**
- But grid 6's VU is **0.00 at all 4,717 nodes**: "Horizontal" Time-Dependent
  Positioning; I tallied every node.
- The vertical velocity in a target frame is therefore purely the
  translation-rate and scale-rate frame terms from `VTRANF`
  (`7666-7728`): −1.01…−1.25 mm/yr in NAD 83 and −0.33 mm/yr in
  WGS84(G2296). It is not a physical uplift model.
- Size of the vertical term:
  - over 16.8 years, NAD 83 direction: 1.7–2.1 cm;
  - Helmert-only misses: forward 2.1 cm; reverse 0.05 cm (frame 10) to 0.6 cm
    (frame 12).
- The total WGS84(G2296)@2026.8 minus NAD83(2011)@2010.0 offset in the box
  (HTDP truth):
  - **N +0.819…+1.076 m, E −1.087…−0.820 m, U −1.170…−0.861 m.**

## 4. Build flags

The same 176 TRFPOS runs and 2 VELOC runs were re-executed with each build
(`htdp_truth.json` → `provenance.comparison_builds`):

| build | TRFPOS output files byte-identical | VELOC |
|---|---|---|
| -O2 (x86_64 SSE2) | **176 / 176** | identical |
| -O0 `-mfpmath=387` (x87 80-bit) | 165 / 176; 11 runs differ in exactly 1 record, by 1 unit of the 10th decimal | identical |
| -O2 `-mfpmath=387` | 164 / 176; 12 runs, 1 record each, 1 last-digit unit | **WRONG**, see below |

**The x87 builds stand in for NGS's own Windows build**, which is
`gfortran -DNGS_PC_ENV -static -m32 -Wall -Wtabs *.f`
(`pc_build_readme.txt`): 32-bit, x87 by default, no `-O`, so -O0.
- A true `-m32` link is impossible here: there is no i386 libc.
- `htdp.exe` (PE32) cannot be run here.
- **So whether NGS's shipped `htdp.exe` matches this Linux binary digit for
  digit is UNVERIFIED.** The proxy says: last-digit ties only, at about 1e-5 m.

**The -O2 + x87 build is broken in VELOC's ITRF2008-frame path.** It returns
velocities such as 0.00 and −32.28 mm/yr where every other build returns
about −16. I did not root-cause this. It is not NGS's configuration, but it
shows the code is not robust to every optimizer/FPU combination. Do not use
an optimized 32-bit build as an oracle.

## 5. Round trip (forward, then the printed output reversed)

- HTDP, with its printed output fed back: worst N 1.1e-5 m, E 6.9e-5 m,
  U 1.0e-3 m. The height figure is print quantization.
- The unrounded experiment chain: N 9.2e-6 m, E 6.4e-5 m, U 4.3e-6 m.
- **So the non-closure is algorithmic, not print noise.** It is fully
  decomposed (experiment Supplements B and E):
  1. **The two clocks** (§1.5): about dT × 17 mm/yr. 0.012 mm at 1997.0 and
     0.056 mm at 2026.8. Calendar entry reduces it (0.009 mm for 10/20/2026)
     but cannot remove it: calendar years and Julian years differ.
  2. **`RADII` omits the height** (`976-988`, used by `RADR8T` `405-419`).
     The velocity is turned into an angular rate on the ellipsoid surface, a
     relative error of h/R. The plate motion travels through this path in the
     reverse direction but through the rigid Helmert in the forward one.
     - Predicted: (h/R)(V_W − V_N)·dt.
     - At 2030.0, where dT = 0 exactly (7,305 days = 20 Julian years), the
       prediction matches the residual to ≤ 2.3e-7 m at h = 0, 600 and
       1,200 m.
     - Size: 3.3e-5 m at 600 m over 20 years.
  3. **An h-independent floor of 1–2.3e-7 m.** This is consistent with the
     second-order terms of the linearized and negated Helmert (§1.2). I did
     not decompose it term by term.

## 6. What I could not verify, and what was assumed

- Whether NGS's distributed 32-bit `htdp.exe`, or the NGS web HTDP, matches
  this x86_64 build to the last digit. Only the x87 proxy above was tested.
- The NA-plate polygon (region 14) was not transcribed. It is used only for
  the beyond-box probes.
- The cause of the -O2 + x87 VELOC failure.
- **The truth is HTDP itself.** No external authority (NCAT, OPUS) was
  queried in this package, so "HTDP is right" is the owner's rule, not a
  measurement.
- The experiment re-derives HTDP's arithmetic. It does not independently
  establish that HTDP's geodesy is correct. For example, the h/R omission in
  §5 is HTDP's behaviour, replicated, not endorsed.

## 7. Files (all in `review/wgs84-w0/`)

| file | what |
|---|---|
| `RECON.md` | this record |
| `drive_htdp.py` | harness. Builds the lattice (86 positions: an 8 × 8 grid over the box, the four corners, Isle Royale ×2, six lake-water points, Clare/Houghton/Detroit/Soo, grid-node and cell-centre probes, three 45° probes, and three beyond-box 50°N probes) × heights 0/200/600. Runs every combination in a fresh temp dir and freezes the result with provenance. Reads `.git/HEAD` as data and never runs git in the clone. |
| `htdp_truth.json` | frozen binary output, 5.95 MB. 176 TRFPOS runs (forward, reverse, round-trip, calendar, decimal-equivalent) and 2 VELOC runs; every run's exact stdin, input lines and parsed output; the build-comparison results; provenance (commit, `.f` sha256s, compiler, flags, binary sha256, UTC capture time) |
| `experiment.py` | independent stdlib Python, every constant cited. `--verify-transcription DIR` re-parses `initvl.f`/`initeq.f` as data and proves the embedded tables are exact: 480 nodes, 0 mismatches; 33 earthquakes, 0 mismatches. Exits non-zero unless every printed record matches. |
| `experiment_output.txt` | the run whose numbers this record quotes |

**Transcribed data volume.**
- Velocity grid 6, nodes I 37–60 × J 34–53: 480 nodes, **1,440 numbers**
  (`initvl.f:44929-46167`, 24 runs of 20 lines). Plus 2 out-of-bounds nodes
  (6 numbers). 305 nodes are actually touched by the lattice.
- Region 1–6 vertices: 24 pairs.
- Earthquake epicentre, radius and date: 33 × 4 = 132 numbers (used for the
  exclusion proof only).
- Helmert sets: 6 frames × 15 parameters × 2 conventions.
- NA plate: 6 numbers.
