# WP-V4 interpolation evidence

Every numeric claim in DESIGN.md amendment **#36** is reproduced by something in
this directory, from the grids committed under `data/`. They are here because the
WP-V4 narrowing re-confirmation found #36 citing experiments whose harnesses had
never been committed — a design-log claim nobody else could check.

Run any of them from this directory with `py <script>`. They resolve the repo
from their own location. **Two need the network** and are marked; the rest are
offline and read only committed files.

## What proves what

| Claim in #36 | Script | Offline? |
|---|---|---|
| `.trn` / `.err` residual table: floor 8.4573 / 3.0416 mm against nearest-node 0.4707 / 0.4716 mm, and bilinear 17.7262 / 4.5468 | `lead_check_vertcon.py` | yes |
| **Bit-identical to NOAA's published algorithm over 18,000 positions, max difference exactly 0.0 m** | `replicate_noaa_exactly.py` | yes |
| 40 further points where the schemes diverge most: nearest-node 40/40 exact, bilinear wrong by up to 46 mm | `decide_err_scheme.py` (capture), `err_40_discriminating_points.json` (the NCAT truth) | script needs NCAT; the capture does not |
| 956 negatives among 223,850 Michigan positions, worst −0.027 m | `scan_negative_sigma.py` | yes |
| GEOID18 120-point comparison: floor rms 0.715 mm against nearest-node 0.454, bicubic 0.409 | `analyse_geoid_schemes.py` over `geoid18_120_discriminating_points.json` | yes |
| GEOID18 20 frozen anchors cannot discriminate — all schemes inside the 0.001 m quantization | `analyse_geoid_schemes.py`, second table | yes |
| Plan §2.7 Michigan window figures, and the `.trn` zero crossing | `lead_check_window.py` | yes |
| The max-σ point is an exact grid node; shift −0.1435 m, σ 0.3656 m, ratio 255% | `lead_check_maxsigma.py` | yes |
| INTG and `Vertcon.java` both anchor on the nearest node | `ncat_source_verification.md` | transcribed, with URLs |

`capture_vertcon_anchors.py` (needs NCAT) is the script that produced
`tests/fixtures/vertcon_anchors.py`; `vertcon_anchor_capture_index.json` is its
index. `decide_geoid_anchoring.py` (needs the NGS geoid API) produced the
120-point capture. `check_err_cell_centres.py` and the transect capture record
the investigation of the negative-σ disagreement with NCAT.

## The sampling, and why it is not circular

The discriminating points were chosen using the **grids** — positions where the
candidate schemes disagree most with each other — and then scored against
**NCAT and the NGS geoid API**, which are external. Selection uses predictor
disagreement; the outcome comes from NGS. That is deliberate and it is what makes
20 randomly-placed anchors unable to settle the question: the two anchorings are
algebraically identical wherever both fractional cell coordinates are below 0.5,
so most randomly placed points carry no information at all.

It is good discrimination, **not** an unbiased estimate of typical error. The
typical-error figure is the 20-anchor table in the suite.

## The one thing not reproduced here

`err_cell_centres_vs_ncat.json` records that NGS NCAT returns **+0.011 m** at
42.475 N / 83.125 W where both this reader and a literal transcription of NOAA's
own `Vertcon.java` return **−0.009652 m**. NOAA's published source contains no
clamp, floor or `abs` on the error grid, so their source and their service
disagree there and nothing in this directory explains why. That is the open
question behind `sigma_m`'s refusal, and it belongs to WP-V7.
