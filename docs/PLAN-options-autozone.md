# PLAN: Options menu, Auto zone, and the observation date in Options

**Status: PROPOSAL, written by the session lead 2026-10-22.** Ships in 0.8.0
together with the WGS 84 build (`docs/PLAN-wgs84.md`). DESIGN.md #71 opens it.
Recon: `review/autozone-r0/RECON.md` (zone boundaries, NCAT as truth) and the
lead's GUI/job map (summarised in §2).

## 1. Scope

### Settled by the owner (2026-10-22)

1. **An Options menu** that switches groups on and off in every system
   dropdown: SPCS 83 zones, SPCS2022 zones, NAD83(2011) geodetic, NATRF2022
   geodetic, and each of the five WGS 84 / ITRF frames. All on by default
   except the five, which are off. **Remembered between runs.**
2. **Auto zone.** An "Auto" entry at the top of the State Plane zone section
   of the list, on both tabs. It picks the zone from each point's
   latitude/longitude, **per point**. On NATRF2022 it picks the **local
   low-distortion zone**, never the statewide one.
3. **The Auto frame is an Options setting** (NAD83(2011) or NATRF2022). A
   lat/long in the other frame is refused for now (no published NAD 83 ⇄
   NATRF2022 transformation, #62); when that bridge exists it converts.
4. **A Multi point file that spans zones writes one CAD (clean PNEZD) file
   per zone.** The audit CSV and the job record name each point's zone.
5. **The observation date leaves both tabs** and moves into Options: "today"
   by default, or a date the user enters. The job record says which.
6. ITRF early-date warning: not added (as built).

### Settled by the session lead, open to the owner's review

- **L1. Auto is an output-side entry only.** A northing/easting does not say
  which zone it is in (the zones overlap in grid space), so Auto is offered
  only as the TO system when the FROM system is geodetic. On the FROM combo it
  is hidden.
- **L2. Auto follows the existing cross-frame rule (#64).** When the Auto
  frame and the input lat/long's frame have no published path, the Auto entry
  is grayed and, if selected, cleared with `FRAME_RESET_STATUS`; `job.run`
  refuses the same pair by name. WGS 84 / ITRF input works with Auto on
  NAD83 (the zone is chosen from the NAD 83 pivot position after HTDP); with
  Auto on NATRF2022 it is refused, as WGS 84 → SPCS2022 already is.
- **L3. The zone is chosen by county, as the law defines it.** Both systems
  are county unions, Great Lakes waters included (MCL 54.231(3)–(5) for
  SPCS 83; NGS's SPCS2022 zones measured as county unions to 0.026 m, with
  Isle Royale split from Keweenaw). MCX bundles **83 water-extended county
  polygons, unsimplified**, plus two tables: county → SPCS 83 zone
  (transcribed from the statute, cited) and county → SPCS2022 LDP zone
  (measured from NGS's beta polygons, `NGS beta` token, REFREEZE-NSRS row),
  and the Isle Royale rule. NGS's own SPCS2022 polygons are land-only and
  would refuse Great Lakes points NCAT accepts, so they are evidence, not
  the bundled data.
- **L4. Point-in-polygon on the job's own geodetic position** (NAD 83(2011)
  for Auto-NAD83, including the HTDP pivot; NATRF2022 for Auto-NATRF). The
  ~1.2 m between the two is inside every boundary band below.
- **L5. A point in no county is refused by name**, never given the nearest
  zone. Outside Michigan, and in Canadian water, is refused.
- **L6.** Superseded by O2.
- **L7. Options are window-level, shared by both tabs.** This reverses
  #26/#43's "tabs share no state" for the Options only; every other control
  stays per tab. Changing any Option clears every displayed Single point
  result (the #26 stale-result rule) and reapplies the dropdown filter.
- **L8. Hiding a group that holds a current selection clears that
  selection** with a status line, exactly as #64's strand rule does. At
  least one geodetic group and one zone group must stay on; the dialog
  refuses an all-off state rather than leaving an empty dropdown.
- **L9. Persistence through `QSettings`** (per user,
  `HKCU\Software\DMARTIN\MCX - Martin Coordinate Exchange`), behind a seam so
  the suite never reads or writes the owner's real registry. A stored value
  MCX does not recognise falls back to the default **and says so** on the
  status line; it never crashes and never guesses.
- **L10. The observation date in Options.** "Today" is the **local** date the
  job runs (Michigan), not the later-of-local-and-UTC used to avoid false
  future refusals. The core keeps refusing a missing date: the GUI now always
  sends one, plus a required `ObservationDateSource` (TODAY or ENTERED) which
  the record prints ("2026-10-22, the date the job ran (Options default)" or
  "…, entered in Options"). A stray source on a job with no WGS 84/ITRF frame
  is refused, as a stray date is. **This reverses PLAN-wgs84 D10's no-default
  rule, on the owner's instruction**, for the "today" choice only; O3.
- **L11. Non-Auto jobs are byte-identical** to the WGS 84 build's output, held
  by the existing digest pins (v0.5.0, pre-W4, W4 disclosure). Every change
  in the outputs is gated on Auto.

### Owner decisions on the lead's questions (2026-10-22)

- **O1. County lines: US Census TIGER 2025** (what NGS built SPCS2022 from,
  and what NCAT uses for it). Measured against the State of Michigan
  Geographic Framework: on land 0.04 m median, 40 m worst; in the lakes
  116 m median, 444 m worst; the North/Central water line up to 11.8 km
  where it meets the international line. NCAT's SPCS 83 land line is 3-17 m
  off TIGER in places; the record names TIGER as the source.
- **O2. Near a zone line: assign only.** A point takes the zone of the
  county it falls in, with no warning and no refusal (MCL 54.234 permits
  either zone where named; the record names each point's zone and county as
  facts). L6 is superseded by this.
- **O3. The observation date.** Options holds a choice: **today** (default)
  or **enter a date**. The choice is remembered; the date is not. With
  "enter a date", the existing date box appears on the main tab, opening
  unanswered ("— choose —") every time MCX starts, and Convert waits for it
  (the WGS 84 build's widget and gating, kept). With "today", no date box is
  shown and the job uses the local date it runs.

## 2. What the recon found that shapes the build

- One function builds all four combos (`controls.zone_combo`); rows can be
  hidden (`setRowHidden`) without rebuilding, so every `findData` and index
  pin stays valid. `direction_for` fails closed on an unknown item type, so
  the Auto item is refused until each consumer handles it.
- The core already converts per point (`project_point(..., target_zone)`,
  `PointConversion.target_zone`), but every output reads
  `settings.target_zone`: `exports.output_stem`, the audit "Target zone"
  cell, `report._job_zones`, the TO block, the "Both zones … exact
  re-projection" sentence, the panel's Zone row, the unit and frame gates.
  With Auto, `target_zone` is None, and each of these crashes, prints a false
  sentence, or **skips a gate silently** (US survey feet on SPCS2022). Every
  one is a work item and a pin.
- `verify_round_trip` checks one clean file against all points; with one file
  per zone it runs per file on that file's points. `_verify_archive` refuses
  an empty member, so a zone with no points gets no file.
- Gate 6 refuses any bundled file byte-identical to one under `review/`, so
  the county file is derived (re-serialised, digest-pinned), never copied.
- NCAT returns the zone for a lat/long in both systems (production REST for
  SPCS 83; the beta web form for SPCS2022). It disagrees with itself near
  the Osceola/Mecosta line because its two systems use different county
  data, so anchors are frozen **outside** the boundary bands only.

## 3. Architecture

- **`michspc/spc/autozone.py`** (core, stdlib): `zone_for(lat, lon, frame)`
  → `ZoneAssignment(zone, county, distance_to_line_m | None)` or
  `AutoZoneRefusal` naming the point. Pure point-in-polygon (even-odd, with a
  documented on-edge rule) over polygons handed in; the county tables are
  core constants with their citations.
- **`michspc/fileio/counties.py`**: the only reader of
  `data/mi_counties_<source>.json` (derived, SHA-256 pinned, geometry
  checks on load as the NGS grids have).
- **`job.py`**: `JobSettings.target_zone` may be `AUTO` (a sentinel object,
  not None) with `auto_frame`; per point the zone is chosen after any HTDP
  pivot, then projected. Unit gate checks the unit against EVERY zone the
  Auto frame can choose; frame gate against the Auto frame.
- **Outputs**: one clean member per zone used, `<stem>_<zone>.csv`; the audit
  CSV's Target zone cell names the point's zone; the record's TO block lists
  each zone used with its point count, the county rule, the data source and
  digest; the audit CSV names each point's county (O2).
- **GUI**: `Options` menu → dialog (toggles, Auto frame, observation date);
  window-level `Options` object read by both tabs; Auto row at the top of
  the zone section; date widgets removed from both tabs.

## 4. Work packages (Opus builders to the lead's brief; lead reviews every diff)

- **Z0** derive the county file and both tables from the recon captures;
  freeze NCAT zone anchors (both systems, outside the bands, including
  Great Lakes, Isle Royale, out-of-state refusals).
- **Z1** `autozone.py` + `counties.py`, pinned to the anchors.
- **Z2** `job.run` Auto: per-point zone, refusals, both gates. **Interim
  Codex gate 1 over Z0–Z2.**
- **Z3** outputs: per-zone clean files, verifiers, audit, record (Auto only;
  every non-Auto digest unchanged).
- **Z4** Options dialog, persistence seam, toggles, Auto entry, the date
  box shown only under "enter a date", both tabs; offscreen previews for the owner.
- **Z5** packaging (spec datas, data pin, LAZY_IMPORTS, gate 6), self-test
  check for Auto, REFREEZE rows, release notes 0.8.0 updated. **Closing
  Codex gate over Z0–Z5**, fixes, narrowing re-confirmation.

Each package: hand-derived expected values, every pin falsified by seeding
(snapshot restore, never `git checkout --`), suite green in `pytest` and
`-O` before commit.

## 5. Still human

- The owner's screen review of both tabs and the Options dialog.
- One real WGS 84 / PPP dataset end to end.
- The clean-profile install proof (METHOD.md §6).
