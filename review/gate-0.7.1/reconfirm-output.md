# Narrowing re-confirmation — MCX 0.7.1 closing gate

Same reviewer, standing in for Codex CLI. Read-only throughout: nothing in the
repository was edited, staged, created or deleted; the fixes were examined as an
uncommitted working-tree diff (`git diff`, 7 files, +208/−40) plus targeted test
runs and probe scripts under the scratchpad.

Scope: **only the surfaces the fixes touched.** Everything else stands as
reported in `gate-0.7.1-opus.md`.

Targeted runs, all green:
`test_geodetic_dms_export.py test_gui_drop.py test_orthometric_regression.py
test_audit_dms.py test_fileio.py` → **316 passed**;
`test_ncat_crosscheck.py test_selftest.py test_gui_single_point.py
test_vertical_disclosure.py test_gui.py` → **458 passed, 1 skipped** (the
release-number skip). Full suite left to the coordinator as instructed.

**Result: all eight findings closed. One new defect introduced, LOW and bounded
— the replacement gate has lost detection power against a narrow class of
formatter defect, and its docstring overclaims that it has not.** No new
CRITICAL, HIGH or MEDIUM.

---

## Finding-by-finding

### MEDIUM 1 — CLOSED. The false refusal is gone and the replacement introduces none.

`michspc/fileio/exports.py:750-849`. `_DMS_HALF_PLACE_DEG` is deleted; the check
is now `row[index] != render(pivot) or render(parse(row[index])) != row[index]` —
text equality against the writer's own rendering, plus a parse-and-re-render
fixed point. No float comparison survives.

**The counterexample no longer refuses.** `101,381151.542,12817687.128,900.000`
and `102,436327.645,13471551.953,900.000` (MI-S, ift, negative-west) now write a
complete archive; the cells are the correctly rounded `42-32-24.87132 N` and
`83-04-17.22885 W`.

**The replacement introduces no false refusal of its own** — this is the
question that matters, because the first cut was itself a fix-shaped change:

* **3,000,000 real inverse-projected angles** (500,000 grid coordinates snapped
  to 0.001 ft in each of MI-South, MI-Central, MI-North): **0 fixed-point
  failures**.
* **227,201 adversarial constructions** placed deliberately on and around the
  rounding half-way point (`k ± 5e-6` total seconds across the Michigan latitude
  and longitude ranges): **0 failures**. This is the exact population that broke
  the tolerance form; it is now inert.
* Carry to the next minute, carry to the next degree, exact zero, negative zero,
  the 90° and 180° boundaries: all fixed points.

**The pin is non-vacuous.** `HALF_WAY_ROWS`
(`tests/test_geodetic_dms_export.py:226`) is my counterexample verbatim, and
`test_a_position_on_the_rounding_half_way_point_writes:237` carries the
anti-vacuity assertion `abs(parsed - pivot) > half_place` — independently
re-measured here as 1.3888907801629102e-09 against a half place of
1.388888888888889e-09, so the anchor genuinely still sits past the old
threshold and would still trip the tolerance form. Restoring that form makes
`write_all` raise and the test fail.

**LOW 3 is closed by construction** — the duplicated `1e-5` constant no longer
exists.

### LOW 1 — CLOSED. The join is real, correct, and refuses nothing legitimate.

`exports.py:807-826`. The DD row's own position must equal
`fmt.latitude(pivot)` and `fmt.longitude(convention.from_signed(pivot_longitude))`.

**It cannot refuse a legitimate job.** Driven over **108 ZONE_TO_GEODETIC
configurations** — 3 zones × 3 input units × 3 output units (international feet,
metres, US survey feet) × both longitude conventions × horizontal and
horizontal-plus-vertical, four points each including a blank Z and both
half-way rows: **108 written, 0 refused.** Separately, the join's expected
strings were compared against `clean_pnezd_rows`' own output across all six
zone × convention combinations: **0 mismatches**. That is the property that
matters — the join recomputes exactly what `job.py:1908-1909` handed the writer
(`output_northing = conversion.latitude`,
`output_easting = convention.from_signed(conversion.longitude)`), through the
same two formatters at the same defaults, so it is a re-derivation rather than a
second convention.

**`settings.longitude_convention` cannot be `None` here**, which would have made
`.from_signed` an `AttributeError` rather than a refusal: `job.run` refuses a
geodetic job without one, verified by running it (`ValueError: A conversion with
geodetic coordinates on either end needs the longitude sign convention…`), so
the job never reaches `write_all`.

**The pin is non-vacuous.** `test_the_dms_verifier_joins_the_dd_file_to_the_same_position:273`
uses my own monkeypatched 41.0 latitude, and its `match=` string
(`"decimal export's latitude reads '41.00000000'"`) occurs in exactly one branch
of the file — line 819, the join. The other "decimal export" message (line 796)
reads "decimal export reads" and its label is only ever point/elevation/
description, so it cannot satisfy the match. I demonstrated in the first pass
that this exact input passed before the join existed.

A structural bonus: the `pivot_latitude is None` guard (`exports.py:801`) now
refuses by name instead of falling through the old `expected is None` clause.

### MEDIUM 2 — CLOSED. The release notes now describe the behaviour, including the surprising half.

`docs/RELEASE-NOTES-0.7.1.md:28-34` now states that a drop on either box lands
in the Input file box and, in bold, that **"a file dropped on the Output folder
box replaces the input file, not the output folder."** It also keeps the true
half of the old sentence (no stray string can be written into either box) and
adds that a dropped folder is refused wherever it lands. Checked against
behaviour: accurate on all three counts, and no longer contradicts the section's
own opening sentence.

**Is `platform_target` honest evidence? Yes, and the test says so in its own
docstring.** My assessment:

* What is real in the test: the widget tree, the `acceptDrops()` values on it,
  the parent chain, the `QDropEvent` delivery, and the resulting state of both
  boxes. The assertion `target is window.multi_point_page` is derived from the
  live window, not asserted as a literal.
* What is modelled: Qt's `QWidgetWindow::findDnDTarget` ancestor walk, which the
  offscreen platform does not run for a hand-sent event. The transcription
  ("nearest ancestor, itself included, that accepts drops") matches Qt's rule.
* The residual gap, which the test cannot close and does not claim to: a wrong
  *transcription* of Qt's rule would go unnoticed. That is unavoidable headless
  and is the strongest evidence available; the docstring names the substitution
  explicitly rather than passing the walk off as the platform's. I consider it
  honest.
* It is also non-vacuous: seeding `output_edit.setAcceptDrops(True)` moves the
  target to the box and the test fails (`AssertionError`), verified by running
  it both ways. Re-measured independently: `platform_target` returns the page
  for both `input_edit` and `output_edit`.

One note, not a defect: the test asserts the outcome for a cursor over each box
but skips `childAt`, i.e. it assumes the cursor is over the box rather than over
one of its children. Both boxes are leaf `QLineEdit`s, so there is nothing
below them.

### LOW 4 — CLOSED, and the new assertions bite.

`tests/test_orthometric_regression.py:335-343`. The convergence branch now
asserts invertibility (`respelled.replace(" ", "-") == original`), that no dash
survives after the sign, that the cell actually changed, and that it is signed.

**Seeded `_v0_5_0_convergence` to the identity and ran the test: it fails**
(two of the four assertions fire). Unseeded it passes. Non-vacuous.

Forward-looking note, measured not assumed: across the nine frozen audit members
there are **54 convergence cells, 0 of them `N/A`**, every one beginning with
`+` or `-`. The two new assertions (`!= original` and `[0] in "+-"`) therefore
hold today, but they would fail on a legitimate `N/A` convergence — a shape
`_v0_5_0_convergence` still handles deliberately and `angle_dms(None)` still
produces. If a tenth configuration is ever added whose convergence is absent,
this branch needs an `N/A` guard. Not a defect now; worth a line in the
amendment.

### LOW 5 — CLOSED. `exports.py:224` — the explanation now sits immediately after the `]`, matching every other constant in the file.

### LOW 6 — CLOSED. All four wordings updated and checked in place:
`exports.py:1` ("three files - four when the target is geodetic"), `exports.py:14`
and `:961` ("The files travel together"), `selftest.py:764` ("A job's files
travel together"), `formatting.py:318` (`-16-49-17.78`). No "three files" claim
survives as a general statement.

### LOW 2 — accepted as recorded, and I agree.

`is_file()` on the drag thread stays. I do not disagree with deferring it: the
refusal is correct whenever it returns, no data is at risk, and moving a
filesystem stat off the drag thread means an async or cached rule — a real
design change with its own failure modes, which is not a thing to introduce at a
release gate. My only ask is that the amendment records the measured number
(**21.05 s** for an unreachable UNC host, **2.70 s** for an unresolvable one) so
that if the owner ever reports "the window froze while I was dragging", the
cause is already written down rather than rediscovered.

### The rejected `render(float(dd_cell)) == dms_cell` form — reasoning confirmed, and it was not marginal.

The DD cell holds 8 decimals of a degree = 3.6e-5 arcsecond; the DMS cell holds
1e-5 arcsecond. The DD cell is the **coarser** of the two, so re-rendering it
cannot reproduce the DMS cell in general. Measured over 400,000 real Michigan
angles: `render(float(dd_cell)) != render(pivot)` for **288,826 of them —
72.21%**. Example: pivot `42.514977823797736` → DD cell `42.51497782` →
re-rendered `42-30-53.92015 N` where the true cell is `42-30-53.92017 N`, two
units of the DMS last place apart. Had that form shipped it would have refused
roughly three geodetic jobs in four. Checking each file against the pivot in its
own notation is the correct resolution, and the comment recording why
(`test_geodetic_dms_export.py:129-134`) is accurate.

---

## New defect introduced by the fix

### LOW 7 (new) — the text comparison is NOT "strictly tighter for every real defect"; three seeded formatter defects now escape the production gate.

**File and line:** `michspc/fileio/exports.py:777` — the docstring sentence "The
text comparison is strictly tighter for every real defect" — and the check it
describes at `:845`.

**Why the claim fails.** Condition 1 (`row[index] != expected_cell`) compares the
cell against `render(pivot)`, and `clean_pnezd_dms_rows` builds the cell with the
same `render(pivot)` call — so on the production path condition 1 is a tautology
with respect to the DMS builder. Condition 2 (the fixed point) is the only part
that can see a formatter defect, and it is blind to any defect that is an exact
fixed point of itself. The retired tolerance form was not, because it compared
the parsed angle against the pivot, a value the formatter does not produce.

**Seeded through the real `verify_dms_round_trip` on a real job (MI-S, ift,
two points). ESCAPED — the verifier passes and the archive would be written:**

| seeded defect | resulting cell | old form |
|---|---|---|
| `latitude_dms_fields` returns a constant | every latitude `42-00-00.00000 N` — up to 44 minutes (about 80 km) wrong | caught (42.0 vs 42.7325) |
| hemisphere taken from `abs(value)`, always `N` | correct digits, sign-to-letter unguarded | caught |
| seconds written to 4 places, not 5 | `42-43-57.0000 N` — silent precision loss | caught (6.94e-9 deg apart) |

**Caught, so the check is far from useless:** truncation instead of rounding,
minutes and seconds swapped, and the longitude built from the re-signed output
(prints `E`) all refuse.

**Severity LOW, and it should not block the release.** None of the three is live;
all three are caught by the suite — the constant and the 4-places forms by the
hand-derived literals in `test_geodetic_dms_export.py:150` and
`test_audit_dms.py:44`, and the always-`N` form by
`test_dms_fields_carry_a_letter_and_never_a_sign:49`. The trade made was the
right one: a reachable false refusal removed in exchange for detection power
against defects only a code change could introduce.

**But the sentence should not stand as written**, and there is a cheap way to
have both. Keep the text equality and add a **loose** tolerance of one full last
place (2.7778e-9 deg) beside it. Measured margin: the largest residual a
correctly rounded cell can have is 1.3889e-9 deg, so a one-full-place threshold
has 2x headroom and cannot false-refuse — the failure mode that started this
thread. It re-catches two of the three escapes above (the constant, by 0.73
degrees; the 4-places form, by 6.94e-9 deg). Alternatively, weaken the claim in
the docstring to what is true: strictly tighter for every defect in the *written
cell*, and blind to a formatter that is its own fixed point.

---

## Anything else the fixes disturbed

* **A new fail-closed corner, effectively unreachable, worth one line in the
  amendment.** The fixed-point condition refuses a latitude in the ~1.4e-9-degree
  band immediately *south* of the equator (and a longitude just west of the
  prime meridian): `-1e-12` renders as `00-00-00.00000 S`, parses back to `-0.0`,
  and re-renders as `00-00-00.00000 N`, so `render(actual) != row[index]` and the
  archive refuses. The old tolerance form passed it (|-0.0 - -1e-12| = 1e-12).
  Root cause: `_latitude_hemisphere(-0.0)` is `"N"` while
  `_latitude_hemisphere(-1e-12)` is `"S"` — the parse loses the sign of a zero.
  Reachability: `convert.to_geodetic` does not refuse a wild northing (a MI-South
  northing of -4,700,000 m returns latitude 2.354 degrees), so the equator is not
  gated — but landing inside a 1.4e-9-degree window, on the negative side, from a
  Michigan job is not a thing that happens, and the outcome is a refusal, never a
  wrong file. Recording it, not fixing it.
* **The audit CSV, the record, the clean exports and the drop rule are
  untouched by these fixes** — `git diff` shows no change to `audit_rows`,
  `audit_columns`, `report.py`, `window.py`, or any formatter's digits
  (`formatting.py`'s only change is one docstring character sequence). The
  0.7.1 claim "no calculation changed" is unaffected.
* **No new stale wording.** The four corrected sentences were re-read in place;
  `verify_dms_round_trip`'s expanded docstring is accurate about what it compares
  against what, apart from the overclaim recorded as LOW 7.

---

# VERDICT: FINDINGS

Every finding from the closing gate is closed at the root, each with a pin I
was able to falsify by seeding the fix back out. The two MEDIUMs are gone: the
false refusal is measurably absent over 3.2 million angles including the
population that produced it, and the release notes now say what the program
does. One new LOW is introduced by the fix itself — a docstring overclaim over a
narrow, suite-covered loss of detection power in the production gate.

**Nothing here blocks 0.7.1.** LOW 7 is a one-line docstring correction or a
five-line strengthening, at the owner's discretion; LOW 2 and the equatorial
corner are records, not repairs.

## Re-examined surfaces, stated as negatives, with the measured numbers

* **No correctly rounded DMS cell can refuse an archive.** 3,000,000 real
  inverse-projected Michigan angles across all three zones and 227,201
  adversarial half-way constructions: **0 fixed-point failures**. The two
  counterexample rows from the closing gate now write.
* **No legitimate ZONE_TO_GEODETIC job is refused by the new join.** 108
  configurations across 3 zones × 3 input units × 3 output units × 2 longitude
  conventions × 2 vertical modes: **108 written, 0 refused**; the join's expected
  strings are identical to `clean_pnezd_rows`' own output in all 6 zone ×
  convention combinations (0 mismatches).
* **No `AttributeError` can reach the join from a missing longitude
  convention** — `job.run` refuses that job first, verified by running it.
* **No new pin is vacuous.** Seeding `_v0_5_0_convergence` to the identity fails
  the stripping pin; seeding `output_edit.setAcceptDrops(True)` fails the drop
  outcome pin; the join pin's `match=` string occurs in exactly one branch of
  `exports.py` and I demonstrated in the first pass that its input passed before
  the join existed; the half-way pin carries an anti-vacuity assertion I
  re-measured (1.3888907801629102e-09 > 1.388888888888889e-09).
* **No `N/A` convergence cell exists in the population the tightened stripping
  pin now constrains** — 54 cells across the nine frozen audit members, 0 `N/A`,
  all signed.
* **No digit moved and no other surface changed.** Targeted suites: 316 passed
  (DMS export, drop, regression, audit DMS, fileio) and 458 passed / 1 skipped
  (NCAT cross-check, self-test, single point, vertical disclosure, GUI).
* **No release-note sentence about the drop is now false** — all three claims in
  the rewritten paragraph check out against behaviour.

---

*Probes:* `rc_fixedpoint.py`, `rc_join.py`, `rc_power.py`, `rc_seeds.py`,
`fix-src.diff`, `fix-tests.diff` in the reviewer scratchpad.
