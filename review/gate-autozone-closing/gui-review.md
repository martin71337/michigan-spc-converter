# Closing gate, Options / Auto zone build: the real-GUI half

Independent adversarial reviewer (Claude Opus), 2026-10-23, HEAD `207645f`,
branch `claude/brave-noether-88m7x1`. This completes the part of the closing
gate that Codex could not run. Its sandbox had no Python 3.14 or PySide6
(`review/gate-autozone-closing/output.txt`, finding 1, a verification
blocker). Read-only on the repository except for this file. Nothing was
committed.

**Environment:** Python 3.14 (`py`) with PySide6, and `QT_QPA_PLATFORM=offscreen`
set before every Qt import. Every window was a real `MainWindow` built on
`settings_store.MemoryStore`, with the store factory replaced the way
`tests/conftest.py` does it. Each harness ends by asserting
`settings_store.PRODUCTION_STORES_BUILT == 0`. That assertion passed in every
run, so neither the registry nor the production store was touched. The
harnesses are in the session scratchpad (`gui-gate/probe_*.py`), not in the
repository.

**How the widgets were driven:** the Options dialog was opened through the
window's own menu action (`options_action.trigger()`, which runs the real
modal `exec()`). Its check boxes and radio buttons were clicked with
`QTest.mouseClick`, and the dialog was closed with a click on OK, the Return
key, Escape or Cancel. The zone combos were driven with `QTest` key events on
the closed combo, real `QWheelEvent`s, and key events on the open popup's
view followed by Return.

## Suite

| Mode | Command | Result | Exit code |
|---|---|---|---|
| normal | `py -m pytest -q -p no:cacheprovider` | **5754 passed** | 0 |
| optimized | `py -O -m pytest -q -p no:cacheprovider` | **5754 passed**, 1 warning (pytest's standard "assertions not executed under -O" notice) | 0 |

Both commands were run unpiped to files, and the exit codes were captured
directly.

## Findings

None at CRITICAL, HIGH, MEDIUM or LOW.

- **INFO 1 (harness pitfall, not a defect).** `isVisibleTo(window)` reports
  False for every widget on the tab that is not current, because
  `QTabWidget` hides that page. My first date probe therefore reported "date
  box hidden under Enter a date" on Multi point 15 times. Once the probe made
  the tab current, all of those checks passed. Any future pin of
  `observation_date_edit` visibility on the Multi point tab has to select
  that tab first, or the Today half of the pin passes vacuously.
- **INFO 2 (behaviour confirmed, recorded for the owner).** In Vertical mode
  a hidden TO selection of Auto survives a FROM change to a zone, because
  reconciliation is exempt in that mode by #43/#71 design. On return to
  Horizontal it is cleared, with `AUTO_RESET_STATUS`, on both tabs. Nothing
  stale escapes: the Vertical-only settings never read the TO combo.

## What was checked, all clean

1. **Stale results: 50 scenarios, 0 mismatches** (`probe_stale.py`).
   - **Setup:** each scenario started from a fresh Single point conversion.
     Most used NAD83(2011) to Auto (SPCS 83) at Calhoun. Others used
     NATRF2022 to Auto (SPCS2022), and WGS84(G1762) to Auto under Today.
   - **Options changes that must clear:** each of the 9 group check boxes,
     clicked once from both the default Options and the all-on Options; the
     Auto frame in both directions; Today to Enter a date. Every one cleared
     the result. Afterwards `sections` was None, Copy all was disabled,
     `copy_all()` and `copy_value(0)` returned False, and the warnings field
     was reset.
   - **Dialog actions that must keep the result:** OK with no change, Return
     with no change, Cancel after toggles, Escape after toggles, a check box
     clicked twice, and the Auto frame switched there and back. All of them
     kept the result. `MainWindow.apply_options` returns early on equal
     Options, so OK with no change does not wrongly clear.
   - **Status lines:** when a selection was cleared, the status line read
     "Cleared: that entry is switched off in Options."
   - **Controls on the tab, with Auto selected:** output unit, longitude
     sign, angle format, TO set to a fixed zone, FROM set to a zone (Auto
     stranded, `AUTO_RESET_STATUS`), FROM set to NATRF2022 lat/long
     (cross-frame, `FRAME_RESET_STATUS`), elevation, latitude, height kind,
     the Down key on TO, the wheel on TO, and the vertical mode radio. All
     cleared the result.
   - **Multi point table** (`probe_multi.py`, 7 dialog cases after a written
     two-zone Auto job): the table was cleared exactly when the dialog hid
     the selection (Auto frame changed, SPCS 83 group off, NAD83(2011)
     group off), each time with the Options status. It was kept otherwise
     (SPCS2022 group off, the five frames on, Enter a date, OK with no
     change), which is #65's design.
2. **Hidden and disabled rows: 529,656 closed-combo events plus 9,856
   open-popup navigations, 0 reached a hidden or disabled row**
   (`probe_hidden.py`, `probe_popup.py`).
   - **Configurations:** 90 Options, being every valid mix of zone groups,
     the two plate-fixed groups and four patterns of the time-dependent
     groups, under both Auto frames.
   - **Combos and starting rows:** all four combos, starting from every shown
     and enabled row, with the other end set to each of 8 representative
     entries (both Auto entries among them).
   - **Closed combo:** Down, Up, Home, End, PageUp and PageDown; typed letters
     A N M W I G C S E U, digits and "-" (accumulating within Qt's keyboard
     interval); the wheel in both directions.
   - **What was checked after every event:** the current row of each combo
     on that tab was never a hidden row.
   - **Open popup:** five Options configurations; 0 to 31 presses of Down,
     Up, End or a letter, then Return.
   - **Not reachable by any of these:** a switched-off group, the hidden
     Auto entry for the other frame, an Auto entry on a FROM combo, and a
     grayed (cross-frame) row.
3. **Selections when the Options or the FROM end change: 406 FROM moves plus
   120 matrix cells, 0 issues** (`probe_auto.py`).
   - **Setup:** both Auto frames, all groups on, both tabs, with Auto
     selected and FROM moved to every entry (8 geodetic and 22 zones).
   - **Expected and found:** Auto was kept exactly for a compatible
     lat/long; it was cleared with `AUTO_RESET_STATUS` for any zone and with
     `FRAME_RESET_STATUS` for a frame with no path.
   - **Never silently retargeted:** when the Auto frame changed, the selected
     Auto entry was cleared with the Options status (item 1).
4. **Auto offered, grayed and units, and the anchors.**
   - **Offering and graying:** for each FROM (the placeholder, 7 geodetic
     entries, 22 zones), each Auto frame and each tab, the Auto entry was
     hidden and disabled on every FROM combo, and the other frame's Auto was
     hidden on TO. The Options' Auto was enabled exactly per L2 and #64:
     - Auto on NAD83(2011): NAD83(2011) and all five WGS 84 / ITRF inputs
       are enabled; NATRF2022 is grayed.
     - Auto on NATRF2022: only NATRF2022 is enabled.
     - Any zone FROM grays Auto.
   - **Units:** Auto SPCS 83 offered international feet, US survey feet and
     metres. Auto SPCS2022 offered international feet and metres, with no US
     survey foot, in all 14 Auto selections.
   - **Anchors** (all 247 in `tests/fixtures/autozone_anchors.py`, through
     both tabs):
     - Single point Auto was run on every anchor. The 233 Michigan anchors
       converted; the 14 outside anchors were refused, with the panel
       unarmed.
     - For each of the 233 placed anchors, the Zone row equalled the NCAT
       zone's label and the County matched. Copy all contained the Zone,
       County and County FIPS lines.
     - The Auto Northing, Easting, grid scale factor and convergence were
       character-identical to the same point converted with the fixed zone.
     - One Multi point file per system (117 SPCS 83 and 116 SPCS2022 points)
       was written and parsed. Each audit CSV's Target northing, Target
       easting, Target zone and County equalled the Single point display, and
       the table's Zone, County and Northing cells equalled the audit CSV.
     - The archives held one CAD file per zone used: 3 for SPCS 83 and 18
       for SPCS2022, plus the README and the `_full.csv`.
5. **The observation date: 645 checks, 0 issues** (`probe_date.py`).
   - **Coverage:** each of the five time-dependent frames, against TO set to
     Auto (SPCS 83), Michigan South and NAD83(2011) geodetic, on both tabs.
     The five frames were switched on through the dialog.
   - **Under Today:** there was no date box on either tab (checked with each
     tab current). The clocks were monkeypatched
     (`job._local_and_utc_dates`) to local 2026-10-22 and UTC 2026-10-23,
     and the job was sent the LOCAL date with source TODAY.
   - **Read at Convert:** the clock was then moved to local 2026-10-23 and
     UTC 2026-10-24 between selection and Convert. The job, the panel's
     "Observation date" row and the Multi point job record all carried
     2026-10-23, never the UTC 2026-10-24, so the date is read when Convert
     is clicked.
   - **Under Enter a date:** the box appeared unanswered, Convert was
     disabled and `settings()` returned None until the date was answered;
     then ENTERED was sent with that date.
   - **Switching modes:** Enter, then Today, then Enter again left the box
     unanswered; the old date did not come back. OK with no change, and an
     unrelated Options change, both kept an entered date.
   - **Persistence:** the store held only the 9 group keys,
     `auto_zone/frame` and `observation_date/source`, and no date. A new
     `MainWindow` on the same store remembered ENTERED and opened the box
     unanswered.
6. **Persistence across windows: 1,014 checks, 0 issues**
   (`probe_persist.py`).
   - **Remembered choices:** 60 random dialog sessions, each followed by a
     new `MainWindow` on the same store. Each time the Options were equal,
     there was no spurious reset message, and both tabs' row visibility
     equalled `visible_rows`.
   - **Refusing an empty list:** with every zone group, or every lat/long
     group, switched off, OK was disabled, Return was refused, the reason was
     shown, and nothing was written to the store.
   - **Invalid stored values:** 154 cases, 14 bad raw values (including
     non-str values) for each of the 11 keys. Each was reset with an AMBER
     message on BOTH tabs' status lines, written back, and not repeated by
     the next window.
   - **Stored empty lists** (zones, geodetic, both) were reset to the
     defaults with the "nothing to choose" message on both tabs, and no list
     was displayed empty.
   - **`Options()` itself** refused all three empty shapes.
7. **W5 with the five frames on: 164 checks, 0 issues** (`probe_w5.py`).
   - **Setup:** each WGS 84 / ITRF frame to Auto (SPCS 83) at Lansing, under
     both Today and Enter a date.
   - **Date gating:** under Enter a date, the box was live and Convert was
     gated until the date was answered, on both tabs.
   - **Both positions:** the panel showed both positions under their frames
     (`Latitude (<frame>)` in INPUT, `Latitude (NAD83(2011))` in OUTPUT, the
     two differing) and the Observation date row.
   - **Zone and county:** Michigan South 2113, Ingham.
   - **Auto against fixed zone:** Auto and the fixed zone gave identical
     Northing, Easting, convergence, grid scale factor and NAD 83 pivot
     latitude.
   - **Multi point:** the audit CSV northing and County agreed.
   - **Vertical mode:** the hidden-Auto case passed (INFO 2).

**Release notes, GUI claims** (`docs/RELEASE-NOTES-0.8.0.md`, the Options,
Auto zone and observation date sections):

- **Claims found true:**
  - selections hidden by an Options change are cleared, with a status line;
  - any change in Options clears the Single point result;
  - three things are remembered, and no date;
  - an unrecognised stored value is reset and the status line says so;
  - Auto is offered on TO only, from a lat/long only, at the top of the
    zone section;
  - Auto is grayed and cleared on a frame mismatch;
  - Auto on NATRF2022 offers no US survey foot;
  - Today uses the local date read when Convert is clicked, with no date
    box;
  - Enter a date opens unanswered and gates Convert;
  - the screens show each point's zone and county.
- **Not verified here:** the registry path. It was deliberately not
  touched; the suite pins it by name.

VERDICT: APPROVED
