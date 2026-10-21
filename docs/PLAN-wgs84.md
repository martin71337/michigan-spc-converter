# PLAN: WGS 84 and ITRF positions, to and from NAD 83(2011)

**Status (2026-10-20): W0 to W4 and interim gate 1 DONE.** Transformed jobs now write, and every output states the transformation. W4b is done too. Next: interim gate 2. W2 registers the five frames and ten HTDP paths, and every one of them REFUSES at `convert.require_a_connected_path` and at the job's settings gate until W3 connects the arithmetic. W1 (`htdp.py`, `htdp_data.py`, 1,846 anchors) reproduces HTDP on all 19,236 applicable frozen records, and on 720 fresh random records the lead drove through NGS's binary, at every printed digit. Written by the session
lead at the owner's instruction ("get going on it. follow the established
development method"). DESIGN.md amendment **#70** records the opening of this
build, the owner's three scope decisions and what W0 measured. This plan is the
design of record for the build; DESIGN.md's body is amended by the work
packages that make each change true, never ahead of them.

**Headline of W0: NGS publishes everything this needs, and its own program
reproduces bit for bit in a Python transcription.** Unlike the deferred
NATRF2022 bridge (`docs/DEFERRED-NATRF2022-BRIDGE.md`, #62), where NGS's
parameters are server-side and unpublished, the WGS 84 and ITRF paths to and
from NAD 83(2011) are NGS's open-source HTDP v3.6.0 (`github.com/noaa-ngs/HTDP`,
commit `59fdbe6b`, 2025-04-07). Compiled from that source in the container, it
is the oracle. A stdlib-Python transcription matched it on **45,408 of 45,408**
printed records (8 frames, 6 epochs, 3 heights, 86 positions across Michigan,
both directions, round trips, calendar and decimal dates), and the lead
re-derived the composition independently from the repo's earlier Helmert code
plus HTDP's own printed velocities, to 0.2 mm in both directions. The full
record is `review/wgs84-w0/RECON.md`.

---

## 1. Scope

### Settled by the owner (2026-10-20)

1. **Realizations offered: WGS 84 (G1762), (G2139) and (G2296)**, the three in
   force since 16 October 2013.
2. **ITRF2014 and ITRF2020 are offered by name** beside them, for PPP results
   (CSRS-PPP, OPUS's ITRF output). HTDP equates them with G2139 and G2296
   numerically, but a PPP report says "ITRF2020", and asking the user to
   translate that into a G-number is a chance to pick wrong.
3. **The observation epoch is entered as a calendar date**, converted the way
   HTDP converts it; the job record states both the date and the decimal year.

### Settled by the session lead, open to the owner's review

Each of these is recorded in #70 with its reason, and each is the kind of
decision #54 recorded as the lead's and open to review.

- **D1. The NAD 83(2011) end is always epoch 2010.0.** It is the epoch NGS,
  OPUS, NCAT and the CORS networks publish NAD 83(2011) coordinates at, and
  every NAD 83 coordinate this program has ever read was implicitly at it. The
  record states it.
- **D2. A bare "WGS 84" stays refused.** The existing `WGS84` record remains
  `DECLARED_NOT_USABLE`, and its refusal now says to name the realization. A
  position labelled only "WGS 84" may be any realization, or NAD 83 output
  mislabelled by a data collector, and the two cases differ by more than a
  metre.
- **D3. WGS 84 or ITRF against NATRF2022 refuses**, for the reasons #62 holds
  the NAD 83 bridge: HTDP does not carry NATRF2022, and composing through
  NAD 83 would use the unpublished bridge. Same `FrameTransformationUnavailableError`.
- **D4. Realization-to-realization and ITRF-to-ITRF are not offered.** No
  zone lives on any of these frames, so the only conversion a surveyor needs
  is to or from NAD 83(2011). HTDP could do it; refusing a neighbouring
  problem is a recordable decision (METHOD.md §7).
- **D5. The pivot is always the NAD 83(2011) position.**
  `PointConversion.latitude/longitude` keep meaning the position in the zone's
  frame, so every existing consumer (projection, extent check, GEOID18,
  GEOID12B and VERTCON lookups, all published against NAD 83) stays correct
  with no change. The WGS 84/ITRF position travels beside it as a second,
  frame-tagged position.
- **D6. Heights.**
  - An **ELLIPSOID** Z is part of the 3-D position and is transformed with it:
    the output ellipsoid height is the target frame's. Passing a WGS 84 h
    through into a NAD 83 job would be about a metre wrong under the right
    label. This interprets #54's "horizontal passes the Z through unchanged":
    #54 meant that horizontal mode does not turn an ellipsoid height into an
    elevation, and that still holds. The height stays an ellipsoid height;
    only its frame changes, because the frame of the job changed. Flagged for
    the owner.
  - An **ORTHOMETRIC** Z is not frame-dependent and passes unchanged. The
    horizontal transform needs an ellipsoid height, and uses H in its place.
    **Measured cost:** the horizontal result moves 1.2e-5 m per 40 m of
    height error, so H for h (|N| about 35 m in Michigan) costs at most
    0.012 mm.
  - A **blank** Z transforms horizontally at h = 0. **Measured cost:** at
    600 m of real height (Michigan's highest ground is about 603 m) the
    horizontal result moves at most 0.18 mm north and 0.13 mm east. The
    record states which convention each job used. These are disclosed facts,
    not caveats: the owner's no-disclaimer rule (#50) holds.
- **D7. A new direction: geodetic to geodetic, only across a registered
  non-identity path.** WGS 84 or ITRF positions in, NAD 83(2011) positions
  out, and the reverse: HTDP's own core use, and the conversion most people
  asking for "WGS 84" need. Same-frame geodetic to geodetic is still not a
  conversion and stays unavailable (`direction_for`).
- **D8. Vertical modes work with the new frames.** Lookups use the NAD 83
  pivot (D5). A VERTICAL_ONLY job on WGS 84 geodetic input mirrors its input
  horizontally, as it does today, and an ellipsoid Z goes
  h(WGS 84) → h(NAD 83) → H = h − N. That gives GNSS WGS 84 heights to NAVD 88
  elevations.
- **D9. The observation date is validated by MCX, not by HTDP.** HTDP accepts
  30 February and computes it as 2 March (W0 §1.5, driven). MCX takes a real
  calendar date only (Python `datetime.date`). It refuses a date after the day
  the job runs, because an observation cannot be in the future. It **warns**,
  without refusing, when a WGS 84 realization's date falls outside that
  realization's period of use: G1762 from 2013-10-16, G2139 from 2021-01-03,
  G2296 from 2024-01-07 (NGA, ICG-17 WG-D presentation, 2023; EPSG 9756 and
  10607; IGSMAIL-8444). Reprocessed data can legitimately carry a later
  realization, so this is a warning, not a refusal. No period warning for
  ITRF.
- **D10. One epoch per job.** A PNEZD file has no column for it; the job's
  settings carry it, and every point in the file is taken as observed on that
  date. Stated in the record.

### Deliberately out of scope

Older realizations (G730 to G1674; G1150 and G1674 are HTDP's "biased"
sets), other ITRFs, per-point epochs, velocity output, HTDP's observation
transforms, NAD 83 at an epoch other than 2010.0, and anything NATRF2022.

---

## 2. W0: what was measured (`review/wgs84-w0/`)

All claims below cite `htdp.f` lines in RECON.md.

### 2.1 The path is not symmetric, and that is HTDP's behaviour to replicate

HTDP always evaluates the Helmert at the **input** epoch, then propagates in
the **output** frame with that frame's velocity:

| Direction | Helmert evaluated at | Velocity | Size in Michigan |
|---|---|---|---|
| WGS 84 or ITRF @ t → NAD 83 @ 2010.0 | t | NAD 83 intraplate residual | N −1.87 to −0.12, E +1.76 to +2.51, U −1.25 to −1.01 mm/yr |
| NAD 83 @ 2010.0 → WGS 84 or ITRF @ t | 2010.0 | full plate motion, output frame | N −2.18 to +1.70, E −16.94 to −15.34, U −0.33 mm/yr |

A Helmert-only implementation misses HTDP at 2026.8 by up to 3.1 / 4.2 /
2.1 cm forward and 3.7 / 28.5 / 0.6 cm in reverse. **The velocity model is
part of the transformation and is built.**

The forward and reverse are therefore not exact inverses. A round trip
through HTDP's own arithmetic fails to close by up to 9.2e-6 m north and
6.4e-5 m east (unrounded), fully decomposed in RECON.md §5: two clocks (the
Helmert runs on the calendar-year fraction, the velocity on whole days in
Julian years), the height omitted from HTDP's velocity-to-angle radii, and a
1e-7 m floor from the negated linearized Helmert. **This is replicated, not
smoothed**, on the owner's standing rule (replicate NOAA, #36/#38 precedent),
and the record states the non-closure as a fact.

### 2.2 Frames, parameters, ellipsoids

- G1762, G2139 and G2296 use exactly the Helmert sets of ITRF2008, 2014 and
  2020 (MENU1 `4677-4753`).
- Every hop is frame → ITRF94 → frame, with linearized rotations in
  arcseconds. The code comment calls them "mas"; it is wrong, and the code's
  own earlier-value comment proves it (`3658`).
- The IGS-convention set (`/tranpa/`) is used whenever NAD 83 is an endpoint.
- **The ellipsoid follows the frame name.** WGS84(…) frames use the WGS 84
  ellipsoid; ITRF and NAD 83 use GRS 80. So ITRF2020 and WGS84(G2296) outputs
  differ by about 0.1 mm north and 0.05 mm up from identical inputs, and the
  records keep them apart.

### 2.3 Velocity model

All of the Michigan box (lat 41.5 to 48.5, lon −90.6 to −82.0, including
Isle Royale and the lakes) lies in HTDP region 6, "eastern CONUS"
(`initbd.f:37-40`). Region 6 is a 0.5° grid of ITRF2008 velocities,
`initvl.f:42981-47704`, interpolated bilinearly in degrees. The region and
grid lookups use the point's ITRF2008 position. The grid values are
single-precision literals. The vertical grid velocity is 0.00 at every node;
the "up" velocity comes from frame rates. No earthquake or postseismic term
reaches Michigan (closest approach 1,291 km outside the nearest radius). The
nearest discontinuity is the 50°N region edge, 1.5° north of the box.

### 2.4 Dates

Calendar entry gives the decimal year as y + (day − Jan 1)/(days in the
year), and the velocity clock is midnight UTC at the start of the date
(GETMDY `7886-7922`). Decimal-year entry often truncates the velocity clock a
day early; calendar entry avoids that, which confirms the owner's choice.

### 2.5 Build sensitivity, and what remains unverified

- -O2 is byte-identical to -O0.
- x87 arithmetic flips the last printed digit on 11 of 176 runs.
- **NGS's own 32-bit Windows `htdp.exe` was not run.**
- The owner can run it, and it ships in NGS's repository: frozen anchors are
  re-checked on his machine before release (§8, still human).

### 2.6 Heights fed to the horizontal transform

See D6: 1.2e-5 m per 40 m, 1.8e-4 m per 600 m.

---

## 3. Architecture

### 3.1 `michspc/spc/htdp.py` (new, core, stdlib only)

A faithful transcription of HTDP's arithmetic for exactly the paths offered,
nothing wider:

- TOXYZ/FRMXYZ on the frame's own ellipsoid, iteration cap and tolerance as
  HTDP;
- toit94/frit94 linearized;
- IGS-convention set for positions;
- PREDV's ITRF2008 lookup position (IERS set);
- bilinear grid interpolation;
- VTRANF into the output frame;
- NEWCOR/COMPSN with HTDP's RADII (no height term);
- HTDP's date arithmetic.

One public entry, `transform(position, path, epoch)`, returning a frozen
record of the transformed position and the facts the record states (Helmert
epoch, velocity in the output frame, dt on each clock).

**Refusals:**
- a lookup position outside the transcribed grid window, never extrapolated;
- an FRMXYZ non-convergence (HTDP's `STOP 666`);
- any frame not in the table.

If/raise only; the suite runs under `-O`.

### 3.2 `michspc/spc/htdp_data.py` (new, core, constants)

- The Helmert sets (both conventions, as used).
- The region-6 grid **window** W0 transcribed: grid columns I 37 to 60 and
  rows J 34 to 53, that is lon −92.0 to −80.5 and lat 40.5 to 50.0, 480
  nodes. Each block is cited to its `initvl.f` lines.
- The window is read-only. A lookup position must fall inside a fully
  transcribed cell and south of the 50.0°N region edge, or it refuses. The
  Michigan box has at least 1.0° of margin on every side.

**The authority is NGS's source, committed unmodified** at
`review/wgs84-w0/htdp-v3.6.0/` (`htdp.f`, `initbd.f`, `initvl.f`, `initeq.f`,
SHA-256 pinned). A suite test re-parses it and requires the transcription to
match number for number; this is W0's `--verify-transcription` as a pin.
Production never reads the Fortran (the core does no file I/O), so the
constants module is a transcription the suite verifies, the way
`zones.py` is checked against NGS's captured definitions.

### 3.3 `frames.py`

- Five new `ReferenceFrame` records, all USABLE: `WGS84(G1762)`,
  `WGS84(G2139)`, `WGS84(G2296)`, `ITRF2014`, `ITRF2020`.
  - Each states its ellipsoid as HTDP uses it.
  - Each carries a new **required** field saying whether the frame is
    plate-fixed with a published reference epoch (NAD83(2011): 2010.0;
    NATRF2022: 2020.0, TR NOS NGS 62) or time-dependent, needing an
    observation epoch (the five new ones). The `FrameStatus` precedent applies
    (#62): required, no default, so a frame cannot be added without the
    question being answered.
- **`FrameTransformation` gains parameters:**
  - Identity records stay parameter-free.
  - A non-identity record must carry its HTDP path (input set, output set,
    velocity frame) and its citation.
  - `__post_init__` refuses a half-specified record either way.
  - `direction_statement` is written from the fields.
- **Registry:** ten new records, each new frame to NAD83(2011) and back.
- **`REQUIRED_FRAME_PAIRS`:** the ten pairs are appended (append-only, #32).
- **`require_frame_path`:**
  - returns the record it finds;
  - WGS 84/ITRF against NATRF2022 still refuses, naming the reason (D3);
  - D4's pairs refuse as unregistered;
  - the bare `WGS84` record still refuses first, by name (D2).

### 3.4 `convert.py`

- `PointConversion` gains defaulted fields: `external_position` (frame,
  latitude, longitude, ellipsoid height when one was transformed),
  `frame_transformation`, `epoch`, and the height convention used (D6).
- `latitude/longitude` stay the NAD 83 pivot (D5).
- **`project_point`, ZONE_TO_GEODETIC and the new geodetic-to-geodetic** call
  `htdp.transform` exactly once, on the side the path requires.
- The NON-identity branch the existing comments promise is written here, and
  the comments that call every path an identity are corrected in the same
  change.

### 3.5 `job.py`

- **Carried from interim gate 1** (`review/gate-wgs84-1/output.md`):
  - **L5:** `convert.geodetic_position` gets its own frame gate, so a
    VERTICAL_ONLY geodetic job has two gates like every other direction.
    `_require_a_convertible_ellipsoid_height_frame` becomes the path-to-geoid
    rule of D6. The reviewer's seed is the pin: with the settings branch
    removed, a WGS84(G2296) ellipsoid job wrote NAVD 88 198.085, about
    1.07 m low.
  - **I1:** the stray `geodetic_frame` refusal covers VERTICAL_ONLY with a
    zone input as well as ZONE_TO_ZONE.
  - **I2:** `project_point`, `convert_point` and `JobSettings` refuse a
    non-`Zone` where a zone is expected with a `TypeError` naming it (today
    an `AttributeError`, pre-existing).
  - **L6, disposition:** three refusals advise conversions that, in the W2
    build, reach the W2 guard. They become true when W3 connects the paths,
    no interface can reach them before then, and interim gate 2 re-checks
    that every refusal is true for its pair.
  - **The L4 hazard:** W3 reads `htdp_frame` and the epoch kind only from
    the CANONICAL registry record, never from a caller's record.
- **From the lead's W2 probe:** a ZONE_TO_ZONE job given a non-default
  `geodetic_frame` it never reads runs and ignores it. That is correct
  arithmetic, and the record does not print the frame for that direction,
  but it is the stray-field class: refuse it by name, as stray zones are.

- **`JobSettings.observation_date: datetime.date | None = None`.**
  - Required when either end's frame is time-dependent.
  - Refused by name when neither is: a stray field creates a false record, the
    0.7.0 closing-gate MEDIUM class.
  - D9's checks.
- `Direction.GEODETIC_TO_GEODETIC`, accepted only across a registered
  non-identity path.
- Gates run in the existing pre-read order, extended, never reordered.
- **D6:**
  - an ELLIPSOID Z transforms with the position;
  - `_require_a_convertible_ellipsoid_height_frame` becomes "the height's
    frame must have a path to the geoid's frame": WGS 84/ITRF now pass,
    NATRF2022 still refuses.

### 3.6 Outputs (`report.py`, `exports.py`)

- **Job record:** a FRAME TRANSFORMATION block, stating
  - both frames and their ellipsoids;
  - the observation date and decimal year;
  - HTDP v3.6.0 and its commit;
  - the direction-specific composition in words;
  - the Helmert set's parameters;
  - the velocity model (region 6 grid, ITRF2008, bilinear);
  - the height convention used;
  - the measured round-trip non-closure, as fact.
- **Audit CSV:** conditional columns only on transformed jobs: the external
  position and the NAD 83 pivot, both named by frame, plus the input and
  output ellipsoid heights where D6 transformed one.
- **Clean PNEZD export:** five headerless fields, unchanged in shape,
  carrying the TARGET frame's values.
- **The three verifiers** (`verify_round_trip`, `verify_dms_round_trip` and
  the DD check) compare each file against the position that file states. On
  a ZONE_TO_GEODETIC WGS 84 job that is the external position, not the pivot.
  This is the integration hazard to watch, because a verifier left pointing
  at the pivot would refuse every such archive. Pinned per direction.
- **The 18-digest cross-version pin stays green and untouched**: no existing
  job's output moves by a byte.

### 3.7 GUI (both tabs)

- **Five new geodetic entries.** `frames_offered` becomes: usable, and either
  carrying zones or holding a registered non-identity path to a frame that
  does.
- **An observation date control**, enabled only when a time-dependent frame
  is selected.
  - No default date: Convert refuses until it is answered, as the longitude
    convention does in the core.
  - The widget choice goes to the owner's screen review.
- **Every change to the date, the frames or the height kind invalidates a
  displayed result.** This is #26's and #43's CRITICAL class, pinned and
  falsified per control.
- The Single point panel shows both positions when a transformation ran.
- **An HTDP refusal must be caught and shown** (interim gate 2, finding L4).
  `job.run` raises `htdp.HtdpRefusal` subclasses (a position outside the
  velocity window is `HtdpVelocityGridError`), restated per row with the
  point and the refused position's own frame. `HtdpRefusal` subclasses
  neither `ValueError` nor `FrameMismatchError`, so a handler written for
  those does not catch it. Both tabs catch `Exception` around `job.run`
  today; W5 must keep that, or catch `htdp.HtdpRefusal` by name, and pin it.

### 3.8 Packaging, self-test, tripwire

- **Self-test check 12:** one WGS84(G2296) point through
  `convert.project_point` against a frozen HTDP anchor.
- **Self-test check 13:** the bare-WGS 84 and WGS 84-to-SPCS2022 refusals,
  alive in the bundle.
- **`LAZY_IMPORTS` audit** extended.
- **Tripwire:** a fifth probe on the `noaa-ngs/HTDP` default-branch commit,
  so a new HTDP release reopens the anchors.
- Release notes; version **0.8.0** (a new capability), `0.8.0-dev` from W1.

---

## 4. Verification anchors

- `tests/fixtures/htdp_anchors.py`: a discriminating subset of the 45,408
  frozen records. It covers every frame × direction × epoch, Isle Royale,
  the corners, the 45°N FRMXYZ switch, all three heights, and the calendar
  dates of §2.4. Provenance: the stdin, the HTDP commit, the source digests,
  the compiler.
- **Acceptance:** every anchor reproduced to HTDP's printed digit (1e-10° and
  1 mm), compared component-wise, never through a `max()` (#62's lesson).
- **Falsification seeds**, each to be caught by a named pin:
  - Helmert at the output epoch;
  - velocity in the input frame;
  - velocity sign;
  - GRS 80 on a WGS84(…) frame;
  - the one-day clock;
  - VTRANF omitted;
  - IERS set used for positions;
  - a grid node transposed;
  - the IGS/IERS lookup-position set swapped.
- **End to end:** file → `job.run` → ZIP → parsed CSV for each direction,
  pinned against the same anchors.

## 5. Work packages

Each WP is built by an Opus subagent to the lead's brief. The lead reviews
every diff and re-derives the load-bearing arithmetic. The suite must pass in
`pytest` and `-O` with exit codes read unpiped. Commit and push follow each
gate.

| WP | Contents |
|---|---|
| **W0** | Recon, oracle, transcription experiment, this plan, #70. **DONE.** |
| **W1** | `htdp.py` + `htdp_data.py` + anchors fixture + transcription pin + falsification seeds. Version → `0.8.0-dev`. **DONE.** |
| **W2** | `frames.py` records and parameterized paths; refusal successors (the old "WGS 84 is unusable" pins become pins on the bare record, never deleted silently). **DONE.** |
| | **Interim gate 1** over W1–W2: the arithmetic. **APPROVED** (`review/gate-wgs84-1/`). |
| **W3** | `convert.py` + `job.py`: D5–D10, `GEODETIC_TO_GEODETIC`, gates, end-to-end pins. **DONE.** |
| **W4** | Outputs: record block, conditional columns, verifiers, the digest pin untouched. **DONE.** |
| **W4b** | **Found at W4's review, inherited from 0.4.0:** a VERTICAL_ONLY job on GEODETIC input prints the SPCS 83 Lambert METHOD prose and "Every point converted cleanly, inside its zone", with no zone in the job. That is a false record sentence (the #42 finding-3 class) in released output, and W4 now writes it for WGS 84 input too. Give zone-less jobs zone-less prose, as GEODETIC_TO_GEODETIC already has. The pinned same-frame records change, as a recorded supersession. **DONE.** |
| | **Interim gate 2** over W3–W4: the integration and the records. |
| **W5** | GUI, both tabs. |
| **W6** | Self-test 12–13, LAZY_IMPORTS, tripwire probe, release notes DRAFT. |
| | **Closing gate** over the full diff; narrowing re-confirmation until APPROVED. |

**Reviewer.** Codex CLI is not installed in this cloud container. Every gate
here runs under an independent Opus reviewer, blind to the lead's reading,
per the owner's standing fallback (2026-08-07). A Codex re-confirmation on
his machine is his option.

## 6. Risks

- **Mislabelled NAD 83 data.** A user who selects a WGS 84 realization for
  data that is really NAD 83 (RTN rover output, many data collectors) adds a
  1.3 m error. The program cannot detect this from the numbers. D2 forces the
  realization to be named, and the record states the frames. As with the
  longitude sign (#33), verification is the user's responsibility; the
  program informs.
- **Fidelity drift.** A "cleaner" reimplementation (exact rotations, exact
  inverse, one clock) would disagree with NGS at the 0.01 to 0.1 mm level.
  The anchors at the printed digit are what hold it.
- **Window edges.** The grid window must refuse rather than extrapolate, and
  the ITRF2008 lookup position (about 1.5 m from the input) must be the one
  tested against it.
- **The verifier hazard** of §3.6.

## 7. Still human

- Run NGS's own Windows `htdp.exe` on a sample of the frozen anchors and
  confirm the digits match the container build.
- The owner's screen review of both tabs.
- One real WGS 84 or PPP dataset, end to end.
- The release build on his machine.
