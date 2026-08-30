# MCX 0.7.0

**MCX now converts on the modernized State Plane system.** It moves survey
coordinates between Michigan's three State Plane zones and between State Plane
and geodetic positions, converts elevations between vertical datums and between
geoid models, accepts GNSS ellipsoid heights, and documents every job well
enough to defend it. It is in production use by a licensed professional
surveyor.

This release adds the **19 Michigan SPCS2022 zones** and native **NATRF2022**
geodetic input and output. **Nothing about an SPCS 83 job changed** — the three
1983 zones, their mathematics, their outputs and their factors are exactly as
they were in 0.6.4.

## The 19 SPCS2022 Michigan zones

One statewide zone and eighteen local low-distortion zones, on NGS's own
published parameters:

- **260001 · MI — Michigan (statewide)**, a Hotine oblique Mercator skewed to
  the state's diagonal.
- **Thirteen Lambert conformal conic zones:** 261003 Flint, 261004 Saginaw,
  261005 Roscommon, 261006 Thunder Bay, 261007 Kalamazoo, 261008 Grand Rapids,
  261009 Newaygo, 261010 Wexford, 261011 Leelanau, 261012 Cheboygan, 261013
  Mackinac, 261017 Bessemer, 261018 Isle Royale.
- **Five transverse Mercator zones:** 261001 Ann Arbor, 261002 Detroit, 261014
  Escanaba, 261015 Marquette, 261016 Houghton.

The low-distortion zones are designed to keep grid distances close to ground
distances, which is what they are for and why there are eighteen of them.

## What you can do with them

- **Any zone to any other zone within the same datum.** Every 2022 zone to
  every other 2022 zone; the three 1983 zones to each other, as always.
- **Native NATRF2022 geodetic input and output.** Both zone dropdowns carry
  `NAD83(2011) geodetic (latitude / longitude)` and `NATRF2022 geodetic
  (latitude / longitude)` as separate entries — the frame is named, never
  assumed — and either can be an input or an output.
- **Metres and international feet on the 2022 zones. No US survey foot** —
  NGS publishes no US-survey-foot false origins for them, printing `N/A` for
  that unit on every 2022 zone, so MCX offers what NGS publishes and refuses
  the rest rather than converting one for you.
- **Grid scale factor, convergence angle, elevation factor and combined
  factor on every zone**, 1983 and 2022 alike, computed per point exactly as
  before.
- All three projections are new mathematics in this program — the one-parallel
  Lambert, the transverse Mercator and the Hotine oblique Mercator — from the
  same NOAA manual the 1983 Lambert equations came from.

## Two things this release deliberately does not do

**Elevations onto the modernized vertical datum (NAPGD2022) wait on NGS.**
NGS has published no product that converts a height between NAVD 88 and
NAPGD2022 — no grid, no service; its own FAQ answers the question in the
future tense. The offset is real, about half a metre, and it cannot be
honestly derived from anything published today, so MCX does not derive it.
Elevations, elevation factors and combined factors on a 2022 zone work exactly
as they always have, from the file's height and the geoid model selected.
Details: `docs/DEFERRED-NAPGD2022.md`.

**Converting between NAD 83 and NATRF2022 waits on NGS too.** The two frames
are one to two metres apart, and NGS has not published the transformation
between them: its own NCAT computes one from parameters that appear in no
published document, and the best public candidate misses NCAT by 17 cm at one
of twelve Michigan test positions. Selecting an NAD 83 end and a NATRF2022 end
in the same job **refuses, and says why** — it never passes the coordinates
through unchanged. Work entirely in one datum or the other. Details:
`docs/DEFERRED-NATRF2022-BRIDGE.md`.

## Built against NGS's beta products

NGS's SPCS2022 zone definitions and its NCAT v3 service are **pre-release**.
NGS declared the definitional products **stable for implementation planning
and integration on 2026-05-28**, with the official rollout expected around
Q1 2027. This release is built against them deliberately, ahead of that
rollout, at the owner's instruction.

Every beta-derived number in this program carries its capture date and the
SHA-256 of the NGS file it came from, `docs/REFREEZE-NSRS.md` lists each one
beside the harness that recaptures it, and the release build itself refuses to
run while any of them remains unless the acknowledgement is given on the
command line. When NGS publishes, every one of those numbers is recaptured and
the difference is **measured and recorded**, not assumed to be zero.

## Verified

- **63 frozen positions computed by NGS's beta NCAT, across all 19 zones**,
  reproduced within NCAT's own printed precision — to half a unit in the last
  digit NGS prints, on northing, easting, grid scale factor and convergence
  alike. The 19 zone origins additionally reproduce NGS's separately published
  false origins and origin scale factors exactly, so two independent NGS
  artifacts agree there.
- **Every zone's defining constants cross-checked field by field** against
  NGS's own published `zoneDefinitions.json` and `zoneBounds.json`, both held
  in this repository under their SHA-256, with each zone's extent and easting
  range taken from NGS's published bounds rather than invented.
- **3,733 automated tests**, green in both run modes, including the
  cross-version pin that digests what nine ordinary jobs write against what the
  previous release produced — so an SPCS 83 job that quietly moved would fail a
  test. It did not.
- **Nine build gates**, including a **self-test run inside the frozen
  application**: it authenticates all four bundled NGS grids, converts one
  point end to end against NGS's own figures, converts one SPCS2022 point
  against beta NCAT's, and proves the cross-datum refusal is still there in the
  shipped binary.
- Every work package passed an independent adversarial review gate; every fix
  is pinned with the reviewer's own counterexample, and every pin was falsified
  by seeding the defect it catches.
- The **closing gate over the whole build** returned four findings and all four
  are fixed and pinned. Three are refusals this release now makes that it did
  not: a **GNSS ellipsoid height entered on a 2022-zone job is refused** rather
  than converted (the two datums' ellipsoids are 1.115 m apart in Michigan, so
  the elevation would have been a metre low with the right label on it); a
  vertical-only job in an unusable reference frame is refused; and a job that
  names a zone its own direction never uses is refused rather than printing
  that zone in the record as though it had taken part. **Orthometric
  elevations on 2022 zones are unaffected and keep converting.**

Verify the download against `SHA256SUMS.txt` on this page.
