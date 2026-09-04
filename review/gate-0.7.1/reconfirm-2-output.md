# Second narrowing re-confirmation — MCX 0.7.1, LOW 7 only

Same reviewer. Read-only: nothing in the repository was edited, staged, created
or deleted; the tree was examined as an uncommitted `git diff`, with targeted
test runs and probe scripts under the scratchpad. Scope as instructed: **LOW 7
and the surfaces its fix touched.** Everything else stands as reported in
`gate-0.7.1-opus.md` and `gate-0.7.1-opus-reconfirm.md`.

Targeted run, green: `test_geodetic_dms_export.py test_audit_dms.py
test_fileio.py test_gui_drop.py test_orthometric_regression.py
test_ncat_crosscheck.py test_selftest.py test_gui_single_point.py
test_vertical_disclosure.py test_gui.py test_dms.py` → **823 passed, 1 skipped**
(the release-number skip). Full suite left to the coordinator.

**Result: LOW 7 is closed. The bound cannot false-refuse, the pin is
non-vacuous, and nothing else moved. No new findings.**

---

## (a) The bound cannot false-refuse a correctly rounded cell

`michspc/fileio/exports.py:796` — `one_place_deg = 10.0 ** -fmt.DMS_SECONDS_DECIMALS / 3600.0`
= **2.777777777777778e-09 degrees**, applied at `:862`.

The arithmetic that has to hold: a correctly rounded cell can sit at most **half**
a place from the pivot — 1.388888888888889e-09 — so the bound is exactly 2x the
worst possible correct residual. I re-ran both populations from the first pass
against the current code:

| population | angles | exceeding the bound | worst residual |
|---|---|---|---|
| real inverse-projected Michigan positions, all three 1983 zones | **3,000,000** | **0** | 1.3888978855902678e-09 |
| adversarial constructions placed on and around the half-way point | **227,201** | **0** | 1.3888978855902678e-09 |

**bound / worst observed = 1.999987x**; headroom **1.388880e-09 degrees**. That
headroom is five to six orders of magnitude above the float excess that broke
the first cut (1.9e-15 to 9.0e-15 degrees), so the failure mode that started
this thread cannot recur through this bound.

**End to end, through the real verifier:** one job of **2,002 points** — both of
my counterexample rows plus 2,000 random MI-South ift coordinates — writes
`big_GEODETIC.zip` with no refusal. The two half-way rows individually:

```
101: |parsed-pivot| lat 1.388891e-09  lon 6.994014e-10   bound 2.777778e-09
102: |parsed-pivot| lat 4.992984e-10  lon 1.388898e-09   bound 2.777778e-09
```

Both sit at half the bound with the full second half unused. Confirmed.

## (b) The pin is non-vacuous, and the bound is what does the work

`tests/test_geodetic_dms_export.py:288`
(`test_the_dms_verifier_catches_a_formatter_that_is_its_own_fixed_point`) runs my
two seeds through the real `verify_dms_round_trip` on `HALF_WAY_ROWS` and
requires a refusal with no ZIP on disk.

I falsified it surgically. `DMS_SECONDS_DECIMALS` is read at **call time** by
`exports` but captured at **def time** by the formatters
(`fmt.latitude_dms_fields.__defaults__` is `(5,)`), so reassigning the module
attribute disables the bound and touches nothing else — a clean isolation of the
one new line:

| seeded formatter defect | bound ON | bound OFF |
|---|---|---|
| returns a constant `42-00-00.00000 N` | **refuses** | PASSES |
| four places instead of five | **refuses** | PASSES |

Both of my reported escapes are closed, and both closures depend on the bound
alone — the text equality and the fixed point still pass them, exactly as I
reported. The pin cannot be satisfied without the line it exists for.

## (c) Nothing else moved

* **Code delta since my previous pass, by diff-of-diffs:** the `one_place_deg`
  line (`exports.py:796`), the third clause of the refusal condition
  (`:862`), the rewritten docstring items 3 and 4 (`:775-793`),
  `formatting.DMS_SECONDS_DECIMALS = 5` (`formatting.py:177`) and the four
  formatter defaults now naming it. Nothing else in `michspc/`.
* **LOW 3 does not return.** No `1e-5` or `0.5 * 1e-5` literal survives anywhere
  in the DMS path; the only remaining `seconds_decimals` literals are
  `angle_dms`'s and `convergence_display`'s `= 2`, which is the convergence's own
  settled default (#26) and correctly outside `DMS_SECONDS_DECIMALS`' stated
  scope ("every DMS latitude or longitude").
* **No digit moved.** `formatting.py`'s only behavioural change is that four
  defaults now spell `5` by name instead of by literal; the formatters produce
  identical text.
* **The release notes are accurate.** The rewritten "DMS export is checked
  before it is written" bullet describes all three conditions correctly, the
  test count matches (3,807), and the new closing-review bullet states the
  refusal rate and my measurement without overstating either.
* **DESIGN.md #69 is an accurate record of the gate.** I checked every figure
  attributed to me — 42.54024203472222, `42-32-24.87132 N`, 6 of 3,000,000, the
  232 near-misses, 1.3888908e-9 against 1.3888889e-9, 0 over 3,000,000 + 227,201,
  the 72% DD-precision figure, 108 configurations, the 41.0 latitude pin, the
  21.05 s / 2.70 s network measurements, the 54 signed convergence cells — all
  correct. Both "records, not defects" (the equatorial corner, the VERTICAL_ONLY
  product question) and my agreement with deferring LOW 2 are recorded as I
  stated them.

---

## Observations, none of them findings

* **One number is out by an order of magnitude, in two places.**
  `exports.py:788` and `DESIGN.md:679` both read "1.4e-9 degrees, five orders of
  magnitude above the noise" after describing the noise as "~1e-15 degrees".
  1.4e-9 / 1e-15 is six orders, not five. Five is right against the *measured*
  excess I reported (1.9e-15 to 9.0e-15, so ~1e-14). Either raise "five" to
  "six" or describe the noise as ~1e-14; the argument is unaffected. Flagging it
  only because this project treats a stated number as load-bearing.
* **The bound is a floor, not a fence: a formatter writing MORE decimals than
  the standard still escapes the production gate.** Seeded `REAL(value, 6)` —
  cells at six decimals of a second — passes with the bound on, because the
  parsed angle is *closer* to the pivot than a correct cell would be. The
  consequence is a correct angle carrying an extra digit, not a wrong one, and
  the suite's hand-derived literals (`"42-43-57.00000 N"`) catch the shape
  change. Item 4's wording ("a sanity bound on the formatter") is fair; I note
  it so nobody later reads the bound as guarding the cell's *format*.
* **The "hemisphere always N" seed still passes, and that is correct
  behaviour, not a hole.** `abs()` is the identity on every Michigan latitude,
  so the seed changes no cell there. Wherever it would change one — any southern
  latitude — the parse returns `+42` against a pivot of `-42` and the bound
  refuses by 85 degrees. The longitude equivalent (building from the re-signed
  value so the cell prints `E`) was already refused before this change.
* **`DMS_SECONDS_DECIMALS` couples the check to the cell at source-edit time,
  not at runtime.** The formatters bind it as a default at import; `exports`
  reads it per call. For the only realistic change — editing the constant — the
  docstring's claim that "the check and the cell cannot come to describe
  different last places" holds exactly. A runtime reassignment would decouple
  them, which is what made my falsification above possible. Worth one sentence
  in the constant's docstring if anyone later relies on runtime coupling.

---

# VERDICT: APPROVED

LOW 7 is closed at the root. The strengthening does what it was proposed to do
and costs nothing: **0 refusals over 3,227,201 angles including the entire
population that broke the first cut**, a 2,002-point job written end to end, and
a 2x margin between the bound and the worst residual a correct cell can produce.
The pin is non-vacuous — disabling the bound alone makes both of its cases pass.
LOW 3 stays closed and the single-authority constant is the right shape for it.
Nothing outside the LOW 7 fix moved, and the design record and release notes
state my findings and measurements accurately.

Three observations above are for the record, not for repair; the only one I
would act on before tagging is the "five orders" wording, which is a
one-character edit in two files.

## Re-examined surfaces, as negatives, with the measured numbers

* **No correctly rounded DMS cell can trip the new bound** — 3,000,000 real
  angles across MI-South, MI-Central and MI-North and 227,201 half-way
  constructions: **0 exceedances**, worst residual 1.3888978855902678e-09
  against a bound of 2.777777777777778e-09 (**1.999987x**).
* **No archive is refused that the previous cut accepted** — a single job of
  2,002 points containing both counterexample rows writes; each half-way row's
  residual sits at half the bound.
* **No case of the new pin passes without the bound** — seeding
  `DMS_SECONDS_DECIMALS` to disable only the bound makes both the constant and
  the four-place cases pass; with it on, both refuse and no ZIP reaches the disk.
* **No duplicated precision constant survives** — one authority,
  `formatting.DMS_SECONDS_DECIMALS`, read by four formatters and by the
  verifier; no `1e-5` literal remains in the DMS path.
* **No digit moved and no other module changed** — the delta since the previous
  pass is confined to one expression, one condition clause, one docstring and
  one constant with its four references; 823 passed / 1 skipped across eleven
  targeted suites.
* **No claim in the design record or the release notes about this review is
  inaccurate** — every figure attributed to the reviewer was re-checked against
  the measurement that produced it, with one order-of-magnitude wording slip
  noted above.

---

*Probes:* `rc2.py` (this pass), plus `rc_fixedpoint.py`, `rc_join.py`,
`rc_power.py`, `rc_seeds.py`, `fix-src.diff`, `fix2-src.diff` from the earlier
passes, in the reviewer scratchpad.
