# Closing adversarial gate — MCX 0.7.1

Independent reviewer standing in for Codex CLI (out of quota), under the owner's
standing fallback rule. Read-only: nothing in the repository was edited, staged,
created or deleted. Range `v0.7.0..HEAD` (`7375c31`), working tree clean apart
from the untracked tripwire log that predates this review.

Suite as found: **3,802 passed, 1 skipped** (the release-number skip),
`QT_QPA_PLATFORM=offscreen py -m pytest -q -p no:cacheprovider`, exit code 0,
run unpiped to a file.

Scope read in full: `michspc/fileio/exports.py`, `michspc/fileio/formatting.py`,
`michspc/fileio/report.py` (FILES WRITTEN), `michspc/gui/window.py`,
`michspc/fileio/dms.py`, `michspc/gui/results_model.py`, the five test files
touched, `docs/DESIGN.md` #65–#68, `docs/RELEASE-NOTES-0.7.1.md`.

**Verdict summary: no CRITICAL, no HIGH. Two MEDIUM, six LOW.** No wrong
coordinate, elevation, factor or angle escapes anywhere. One of the two MEDIUMs
is a production refusal reachable from ordinary Michigan data, reproduced end to
end; it is a recurrence of the exact defect class amendment #46 found and fixed.

---

## MEDIUM 1 — the DMS round-trip verifier refuses whole archives on correctly-rounded Michigan positions. This is #46's defect class, reintroduced.

**File and line:** `michspc/fileio/exports.py:751` (`_DMS_HALF_PLACE_DEG =
0.5 * 1e-5 / 3600.0`) and `michspc/fileio/exports.py:801`
(`if expected is None or abs(actual - expected) > _DMS_HALF_PLACE_DEG:`).

**What is wrong.** The tolerance is *exactly* half of the cell's last place,
with no float slack, compared against a value the formatter reached by a
different arithmetic path. A position whose seconds land on the rounding
half-way point produces a residual of exactly half a place — a correct cell —
and the float comparison lands a few parts in 10^15 above the threshold. The
whole archive then refuses: no DD export, no DMS export, no audit CSV, no job
record.

The project already knows this shape. `verify_round_trip` carried a half-place
tolerance until the vertical-only gate found it "refusing whole archives on
ordinary metre northings", and the fix was to stop comparing with a tolerance
at all — `promised()` renders the expectation at the written precision and
compares EXACTLY (`exports.py:619`, and the comment above it is the whole
argument). `verify_dms_round_trip` reintroduces the tolerance form beside it.

**Concrete counterexample, executed end to end.** A one-row PNEZD file, Michigan
South, international feet:

```
101,381151.542,12817687.128,900.000,LAT TRIPS
```

Direction ZONE_TO_GEODETIC, in ift, out ift, negative-west. The job computes
`latitude = 42.54024203472222`, and the DMS cell is
`42-32-24.87132 N` — the correctly rounded value; its residual is
0.000005 arcsecond, about **0.15 mm**. `exports.write_all` raises:

```
WriteError: DMS round-trip check failed on point '101': the DMS export's
latitude '42-32-24.87132 N' reads back as 42.54024203333333 where the job
computed 42.54024203472222. Nothing was written.
```

Files left in the output folder afterwards: none. A second, independent
counterexample on the longitude side:
`102,436327.645,13471551.953,900.000,LON TRIPS` → `83-04-17.22885 W`, same
refusal. Control (`449212.689,13072628.343`, the suite's own anchor) writes
normally.

**Measured rate.** 1,500,000 random Michigan-South grid coordinates snapped to
0.001 ft and inverse-projected → 3,000,000 real angles: **6 exceed the
tolerance**, i.e. ~1 in 500,000 angles, ~1 in 250,000 points, plus 232 within
1e-13 deg of the boundary. Excess over the threshold in every case is
1.9e-15 to 9.0e-15 degrees — pure float noise, never a real disagreement. A
separate 800,000-angle random sweep produced zero trips, with a worst-case
margin of 1.2e-14 degrees; the margin, not the miss rate, is the finding.

**Why it matters more than 1-in-250,000 suggests.** The failure is total (the
deliverable does not exist), the message names this program's own reader and is
not something a surveyor can act on, and it is *sticky*: the same file refuses
every time until the point is moved.

**Fails closed.** No wrong number ever reaches a file. That is why this is
MEDIUM and not HIGH.

**The test that should have caught it.** `tests/test_geodetic_dms_export.py:119`
(`test_the_dms_file_is_the_dd_file_with_the_position_restated`) asserts the
same round trip with a *looser* tolerance than production —
`0.5e-5/3600.0 + 0.5e-8` — so the test can never fail where production does.
`test_the_dms_round_trip_refuses_a_wrong_cell` seeds only gross errors
(hemisphere flipped, a whole minute, the symbol form). #67's own falsification
list widened the tolerance "to a degree" and never narrowed it. The missing pin
is a position whose residual sits on the half-place boundary, driven through
`verify_dms_round_trip` and required to pass.

**The fix that matches the file's own precedent:** compare the STRING, not the
angle — re-render `point.conversion.latitude` through
`fmt.latitude_dms_fields` and require character equality, exactly as
`verify_round_trip`'s `promised()` does. That is strictly tighter than the
tolerance for every real defect and cannot refuse a cell the writer itself
produced.

---

## MEDIUM 2 — the release notes state, falsely, that a drop on the Input file and Output folder boxes does nothing; a drop on the OUTPUT box silently replaces the INPUT file.

**File and line:** `docs/RELEASE-NOTES-0.7.1.md:28–30`:

> Dropping onto the Input file or Output folder boxes themselves does nothing:
> those boxes take a typed path or a chosen one, never a dropped one, so a drop
> cannot write a stray string into either.

**What actually happens.** Both boxes have `setAcceptDrops(False)`
(`window.py:402`, `window.py:572`), and Qt's `QWidgetWindow::findDnDTarget`
walks from the widget under the cursor **up** to the first ancestor that accepts
drops. Measured on the real window: for `input_edit`, `output_edit`, `table`,
`status_label` and `convert_button`, the nearest drop-accepting ancestor is
`MultiPointPage` in every case. So a file dropped on the Input file box lands in
the Input file box (it works), and **a file dropped on the Output folder box
also lands in the Input file box** — silently replacing whatever input file was
named there.

The implementation's own comments say so (`window.py:569-572`: "a file dropped
here goes to the page, which routes it to the Input file box"), and the drop
suite's docstring says "A file dropped ANYWHERE on the tab reaches the page's
handler". The release notes contradict both, and contradict their own opening
sentence four paragraphs earlier.

**Operational counterexample.** The surveyor has `C:/jobs/24-118/pts.csv` in the
Input file box and drags `C:/jobs/24-118/out/` onto the Output folder box — a
folder, correctly refused. He then drags the wrong thing, a *file*, onto the
same box; the Input file box silently becomes that file, Convert stays armed,
and the job that runs is not the job he set up. The new path is visible in the
box, which is the only thing that keeps this out of HIGH.

Only the second half of the sentence is true (no stray string reaches either
box).

**The test that should have caught it.** `tests/test_gui_drop.py:157`
(`test_the_multi_point_page_is_the_drop_target_and_its_children_are_not`) pins
the mechanism — `acceptDrops()` is False on the boxes — but no test pins the
*outcome* the notes describe. A test asserting that a drop over the Output
folder box fills the Input file box (or that it does not) would have forced the
sentence to be written correctly.

---

## LOW 1 — the DMS position is never compared against the DD file's position; a divergence between the two files would pass both verifiers.

**File and line:** `michspc/fileio/exports.py:779-809`.

`verify_dms_round_trip` compares fields 0, 3 and 4 character-for-character
against `clean_pnezd_rows(result)`, but fields 1 and 2 against
`point.conversion.latitude/longitude` — never against the DD file's own cells.
`verify_round_trip` in turn compares the DD file only against
`point.output_northing/output_easting`. Nothing joins the two.

**Demonstrated:** with `clean_pnezd_rows` monkeypatched to write
`41.00000000` as the DD latitude (1.7 degrees wrong) and the DMS rows untouched,
`verify_dms_round_trip` **passes**.

Not live today: `job.py:1908` sets `output_northing = conversion.latitude` for
this direction, the same object, and the longitude differs only by the
convention sign the DMS cell deliberately discards. It is a detection gap, not a
defect — but the release's headline claim is that the two files hold the same
positions, and no production check enforces it. The test does
(`test_geodetic_dms_export.py:126-133`); production does not.

The function's docstring is accurate about what it compares against what; it is
the archive-level property that is unguarded.

## LOW 2 — the drop rule stats the filesystem on the GUI thread inside dragEnter/dragMove; a network path can freeze the window for ~21 seconds.

**File and line:** `michspc/gui/window.py:247` (`return path if path.is_file()
else None`), reached from `MultiPointPage._consider` at `window.py:271`, which
is called from both `dragEnterEvent` and `dragMoveEvent` — and Qt fires
`dragMoveEvent` on every mouse movement during the drag.

**Measured on this machine:** `Path('//192.0.2.1/share/pts.csv').is_file()`
returns `False` after **21.05 s**; `//nosuchhost-xyz9/share/pts.csv` after
2.70 s. Local `is_file()` is microseconds, so ordinary use is unaffected; a
share that has gone unreachable (VPN dropped, server down) or a slow WAN mount
stalls the whole window, repeatedly, mid-drag.

No wrong data, and the refusal is still correct when it finally returns.

## LOW 3 — `_DMS_HALF_PLACE_DEG` hardcodes the last place with nothing tying it to the formatters' default.

**File and line:** `michspc/fileio/exports.py:751`. The constant encodes
`1e-5` seconds; `latitude_dms_fields`/`longitude_dms_fields`
(`formatting.py:245`, `:261`) default to `seconds_decimals=5` independently.
Two authoritative statements of one fact, in a codebase whose §7 forbids exactly
that. Changing the default to 4 places would silently make the check 10x
stricter and refuse every job. (Moot if MEDIUM 1 is fixed by string comparison,
which removes the constant.)

## LOW 4 — two vacuous assertions in the pin that establishes the digest channel is lossless.

**File and line:** `tests/test_orthometric_regression.py:318`
(`test_the_stripping_is_exact`), the two assertions inside the
`if column in CONVERGENCE_COLUMNS:` branch:

* `assert respelled[index] == _v0_5_0_convergence(original[index])` re-applies
  the same function that produced `respelled`, so it cannot fail;
* `assert respelled[index].replace(" ", "") == original[index].replace("-",
  "").replace(" ", "") or original[index][0] in "+-"` — measured on the real
  members, every convergence cell begins with `+` or `-`, so the right-hand
  clause short-circuits true for every cell and the left-hand comparison is
  never evaluated for its truth. (`N/A` would satisfy the left clause anyway.)

The `else` branch — every non-convergence column unchanged — is real and is what
carries the test. This is the LOW-3 class #56 recorded: a pin written after the
claim it is meant to hold.

## LOW 5 — the `AUDIT_COLUMNS` explanation is a detached string expression, not the constant's docstring.

**File and line:** `michspc/fileio/exports.py:223-226`: the closing `]` is
followed by two blank lines before the `"""..."""`, so Python evaluates and
discards it and no documentation tool associates it with `AUDIT_COLUMNS`. Every
other constant in the file (`SOURCE_COLUMNS_LINEAR:124`,
`ELLIPSOID_ELEVATION_HEADING:245`, `DMS_FIELD_SEPARATOR` in `formatting.py:171`)
puts its docstring immediately after the assignment. The text is the record of
the layout decision #66 warns about, so it is worth attaching properly.

## LOW 6 — stale "three files" wording now that a direction writes four.

* `michspc/fileio/exports.py:1` — module docstring, "one ZIP archive containing
  three files";
* `michspc/fileio/exports.py:13` and `:917` — "The three files travel together";
* `michspc/selftest.py:764` — **user-visible**: a `SelfTestError` message
  reading "A job's three files travel together or not at all". The self-test's
  own job is zone-to-zone, so the message is true where it fires, but the
  sentence is now a general claim that is not general;
* `michspc/fileio/formatting.py:318` — `convergence_display`'s docstring still
  says "the same angle the audit CSV carries as `-16 49 17.78`", which #68
  changed to `-16-49-17.76`.

`_verify_archive`'s own refusal message was correctly reworded (`:895`).

---

## Observations, not findings

* **The dash serves as both sign and separator in the convergence:**
  `-16-49-17.76`. A naive `split("-")` yields an empty first field. The release
  notes warn about this explicitly ("split on dashes after the sign"), the DMS
  latitude/longitude cells carry no sign at all, and the NCAT cross-check's own
  reader was updated. Recorded as the cost of the owner's instruction, not as a
  defect.
* **A VERTICAL_ONLY job on a geodetic file gets DMS columns in the audit CSV but
  no DMS clean export.** Deliberate per #67 and verified correct in the record
  (three files, no DMS block). Worth putting in front of the owner as a product
  question, not a code question.
* `test_the_comparison_would_notice_a_changed_byte`
  (`test_orthometric_regression.py:284`) appends `b"\n"` *after* stripping, so
  it tests SHA-256 rather than the stripping. It was equally weak before this
  release, and `test_the_raw_member_no_longer_matches_but_the_stripped_one_does`
  is the real anti-vacuity pin, which is genuinely strong.

---

# VERDICT: FINDINGS

Two MEDIUM, six LOW. No CRITICAL, no HIGH. Nothing blocks a release on
correctness of a number; MEDIUM 1 is a fail-closed refusal that will eventually
be met by a real job, and MEDIUM 2 is a false sentence in the only user-facing
document the release ships.

## Surfaces examined and found clean, stated as negatives

**The DMS arithmetic**

* **No DMS cell disagrees with its decimal sibling by more than half its last
  place.** 800,000 random Michigan angles through
  `latitude_dms_fields`/`longitude_dms_fields` and back through
  `dms.decimal_degrees`: worst latitude residual **1.388877e-09 deg**
  (44.56211486527776 → `44-33-43.61351 N`), worst longitude residual
  **1.388884e-09 deg** (-88.08056041527777 → `88-04-50.01749 W`). Both are
  below half the cell's last place (1.3888889e-09 deg = 0.000005 arcsecond ≈
  0.15 mm) — see MEDIUM 1 for the margin.
* **No carry escapes.** 59.9999995 s carries to `42-44-00.00000 N`; 3599.9999995 s
  carries to `43-00-00.00000 N`; both agree digit for digit with the panel's
  `latitude_dms`. No `60.00000` field is produced anywhere in the sweeps.
* **No sign reaches a DMS cell and no hemisphere letter contradicts the sign.**
  Exact 0.0 and −0.0 longitude both print `00-00-00.00000 E`; −1e-5 prints
  `00-00-00.03600 W`; −42.7325 latitude prints `...S`, never a leading minus.
* **No digit moved anywhere in the numeric formatters.** `angle_dms` was
  compared against a transcription of the v0.7.0 implementation over
  **1,500,000** angles at 0, 2 and 5 decimals plus a 200,000-point sweep of the
  convergence range: **0 mismatches** once the separator is normalised.
  `_dms_magnitude` compared against its v0.7.0 form over **400,000** magnitudes:
  **0 mismatches**. Only separators changed.
* **No file in `michspc/spc/` is touched by the diff.** The changed files are
  `michspc/__init__.py` (version literal), `fileio/exports.py`,
  `fileio/formatting.py`, `fileio/report.py`, `gui/window.py`. The claim "no
  computation changed" holds.

**Staging and verification**

* **No DMS member reaches the archive unverified.** `clean_pnezd_dms_rows` →
  `verify_dms_round_trip` → `contents[...]` all execute before `staged_write`
  opens anything (`exports.py:947-966`), and `_verify_archive` is handed
  `tuple(contents)`, so the DMS member is CRC-checked, presence-checked and
  non-empty-checked with the other three. A monkeypatched corrupt row leaves no
  ZIP on disk (pinned, and re-executed here).
* **The verifier is not vacuous.** Executed here: swapping the latitude and
  longitude cells refuses; the docstring-claimed comparisons all fire; a row
  dropped refuses on the count; an `N/A` position (a `None` latitude) refuses
  through the four-field check rather than passing.
* **Under a positive-west job the DMS export still prints W.** The two
  conventions' DD rows differ in sign (`-84.55550000` vs `84.55550000`) and
  their DMS rows are byte-identical (`84-33-19.80000 W`), because the cell is
  built from the negative-west pivot.

**The cross-version digest pin** (`tests/test_orthometric_regression.py`)

Mutated a real audit member fifteen ways and re-digested through
`_without_columns`. **Seen** (digest changes): the last digit of Target
northing, of the decimal Latitude, of Elevation, of Combined factor, of Geoid
height, of Convergence; the sign of Convergence; the convergence separator
changed to anything other than a space; the Warnings cell; the Description; a
renamed heading; an appended row. **Invisible** (digest unchanged): only two
things — the convergence separator reverted to spaces (a #68 regression), and
anything at all done to the two DMS columns, including swapping them. Precisely:
**no change to any NUMBER in any column, and no change to any heading or row
count, can hide from the pin**; the pin is blind exactly and only to the
convergence separator and to the two stripped columns, both of which #68
declares and both of which are pinned elsewhere (23 literal pins, plus the NCAT
cross-check's independent `_lettered_dms_to_degrees` reading).

**The audit CSV layout**

* **No reader in `michspc/` or `tests/` indexes the audit CSV by a position that
  moved and was not updated.** `audit_columns` and `audit_rows` insert every
  conditional column by `header.index(name)`, so the vertical block and the
  ellipsoid-height column follow the new layout automatically.
  `test_ncat_crosscheck.py`'s positional constants were moved and are now pinned
  to their headings by a new test. `test_fileio.py`'s surviving positional
  references (index 7 Elevation, −2/−1 Warnings/Description, 2/3 the source
  pair) all sit before the insertion point or at the end and remain correct.
  `tools/build_release.py` and `michspc.spec` reference no member names or
  column positions.
* **No surface that was not supposed to change did.** The Multi point on-screen
  table has no convergence column at all (`results_model.COLUMNS`), the Single
  point panel uses `convergence_display` and `latitude_dms`/`longitude_dms` —
  the symbol forms, untouched — and the clean PNEZD export is byte-identical
  under its new `_DD` name (established by the cross-version digest under the
  frozen name). `michspc/gui/` gained no DMS-field call.

**The job record**

* **No record states a false file count.** Generated across six configurations —
  ZONE_TO_ZONE, ZONE_TO_GEODETIC, GEODETIC_TO_ZONE, VERTICAL_ONLY on a grid
  file, **VERTICAL_ONLY on a geodetic file**, and ZONE_TO_GEODETIC with
  HORIZONTAL_AND_VERTICAL. Four files and a DMS block in the two
  ZONE_TO_GEODETIC cases only; "three files" / "three loose files" and no
  mention of DMS in the other four; the archive holds exactly the number the
  record claims in all six; the DMS block is listed between the DD member and
  `_full.csv` in both four-file cases.

**The drop**

* **No drop can write a string into either path box that is not an existing
  local file's path.** `dropped_input_file` refuses two files, a folder, a
  missing path, a non-local URL, a URL-less payload and a text-only payload;
  `file:`, `file:///`, `file:///C:/` and a NUL-bearing path all answer None
  without raising. Only `input_edit` is ever written, and only via
  `_set_input_file`, which Browse also uses — so Convert arms through the same
  `textChanged` gate for both routes.
* **No dropped file is read before Convert.** `_set_input_file` calls
  `setText`; `_update_convert_enabled` calls `settings()`, which only reads the
  two boxes' text and the combos. The status line still reads `Ready.` after a
  binary file is dropped.
* **No Windows path shape survives the drop mangled.** 31 filenames round-tripped
  through `QUrl.fromLocalFile(...).toLocalFile()` and re-checked on disk — spaces,
  `#`, `%`, `+`, `&`, `;`, `=`, `,`, `@`, `$`, `!`, `~`, `^`, backtick, quote,
  brackets, braces, parentheses, Latin-1 accents, CJK, a trailing space — **0
  failures**. A UNC URL keeps its `//server/share/...` spelling through the same
  round trip.
* **No drop reaches the Single point tab.** Its nearest drop-accepting ancestor
  is `MainWindow` (a `QMainWindow` accepts drops by default) whose handlers are
  Qt's defaults, so the drag is refused and the Input file box is unchanged —
  measured.

---

*Probe scripts and captured output:*
`…/scratchpad/reviewer/probe_dms.py`, `probe_rate.py`, `probe_e2e.py`,
`probe_gui.py`, `probe_pin.py`, `probe_record.py`, `pytest.txt`.
