# RE-FREEZE — every `NGS beta` artifact MUST be re-frozen at NGS's official release

**Status: OPEN, and it stays open while any file in this repository carries the
literal token `NGS beta`.** Authority: DESIGN.md **#61** (the decision to build
and release ahead of NGS's official rollout, and the mechanism this document
is half of) and **#62**. The plan is
`docs/PLAN-nsrs-modernization.md`, "The re-freeze obligation (mechanism, not
memory)".

This is a mechanism, not a memory. The token, this checklist and the
two-way inventory test (`tests/test_refreeze_inventory.py`) exist so that the
obligation cannot be lost by anyone forgetting it: an artifact that carries the
token and is not listed here fails the suite, and a row here that names a file
which no longer carries the token fails it too.

## What re-freezing means

MCX ships coordinates computed from NGS products that NGS has published as
**beta** — declared stable for implementation planning and integration on
2026-05-28, with the official SPCS2022 / NATRF2022 rollout expected around
Q1 2027. The owner's recorded decision (DESIGN.md #61) is to build and release
against them now, with every beta-derived number carrying its capture date and
its digest so that a sealed job can be re-checked later.

Re-freezing is doing that re-check, and it is four steps:

1. **Re-run the recapture harness** named in the row, against NGS's official
   endpoints, on a machine that can reach `geodesy.noaa.gov` /
   `beta.ngs.noaa.gov` (the container cannot; DESIGN.md #35).
2. **Compare the new capture's SHA-256 against the digest the row's artifact
   states.** A digest that matches means nothing moved and the artifact is
   re-dated, not rebuilt.
3. **Any changed digest means new records and a full gate cycle** — the
   transcription re-done from the new capture, every anchor re-frozen, the
   difference against the beta values MEASURED and recorded, never assumed to
   be zero. Beta NCAT is entitled to have been wrong.
4. **Record the event as a DESIGN.md amendment**, and remove the `NGS beta`
   token from every artifact whose facts are no longer pre-release — which is
   what closes this document.

**Nothing here is a substitute for the measurement.** The difference between a
beta value and an official one is a number that must be printed, not a risk to
be described.

## The trigger

NGS's official publication of the SPCS2022 zone definitions and of NATRF2022 —
whichever lands first, for the artifacts that depend on it. Watch:

* `https://beta.ngs.noaa.gov/SPCS/` and its `json_data/` files, and their
  successors on `geodesy.noaa.gov`;
* NGS's NATRF2022 page and the Federal Register adoption notice;
* NCAT v3 leaving beta — the anchors in this repository are that service's
  own output.

## The release gate

**The release gate refuses to build while any `NGS beta` tag remains, unless an
explicit acknowledgement flag is passed**, so that every beta-era release is a
conscious act rather than a default (DESIGN.md #61; the `-dev` marker idiom).

**It exists.** Work package **N8** built it: `gate_beta_acknowledgement` in
`tools/build_release.py` is gate 2 of nine, immediately after the version gate,
and it scans the same roots for the same token this document's inventory test
scans (the two scanners are separate implementations — the build tool must not
import `tests/` — pinned against each other in
`tests/test_selftest.py::test_the_build_gates_beta_scan_is_the_inventory_tests_scan`).

    py tools/build_release.py                        refuses, naming every tag
    py tools/build_release.py --acknowledge-ngs-beta builds, printing each one

The flag suppresses nothing: the gate prints every artifact it acknowledges,
and the run's `SHA256SUMS.txt` carries a trailing comment naming the
acknowledgement and listing those artifacts, so the release's own evidence
records what era it was built from. When this document's table is empty — the
re-freeze done — the gate passes silently and the flag is no longer needed.

The count it prints is the table's row count: five artifacts for 0.7.0 and
0.7.1, seven since the Auto zone build (the county-to-SPCS2022 table and the
zone-pick anchors, work package Z0).

## Tagged artifacts

**This is the table `tests/test_refreeze_inventory.py` parses, and its format
is load-bearing.** One row per file in `michspc/**` or `tests/fixtures/**` that
carries the literal token `NGS beta` (or `NGS BETA`); the row's **first cell is
that file's repository path, in backticks, and nothing else**. The harness and
pin cells name existing paths in backticks; a pin may name a test function
after `::`.

The test enforces the table BOTH ways: every tagged file must appear here, and
every row must name a file that exists and still carries the token. So the
checklist can neither miss an artifact nor outlive one.

| Artifact | What it carries that is pre-release | Recapture harness | Authenticating pin |
| --- | --- | --- | --- |
| `michspc/spc/zones.py` | The nineteen SPCS2022 zone records — every defining constant transcribed from `zoneDefinitions.json`, every extent and easting range from `zoneBounds.json` — and the shared citation carrying both files' capture dates and digests. | `review/nsrs-n0/capture_spcs.py` | `tests/test_zone_registry.py` |
| `michspc/spc/frames.py` | NATRF2022's record and citation: the frame is defined by NOAA TR NOS NGS 62, and everything this program carries for it (zones, anchors) is beta. | `review/nsrs-h3-recon/ifdm/capture_pubs.py` | `tests/test_convert.py::test_natrf2022s_citation_carries_its_authority_and_its_beta_provenance` |
| `michspc/fileio/report.py` | The job record's SPCS2022 METHOD and verification prose — the capture dates, both digests, and the beta-NCAT anchor count it states to the surveyor. Since the Auto zone build, also the Auto zone SPCS2022 TO block (`_auto_zone_block`): its Zone rule paragraph cites NGS's beta "Multizone Complete Zones" polygons by quoting `autozone_spcs2022.NGS_POLYGONS_CITATION` whole (captured 2026-10-22, `mi_native.json`, SHA-256 `0b400984…7cf7`), and its Isle Royale paragraph states the 47.65 N rule those polygons and beta NCAT support. Re-freezing the table row below without re-reading this block would leave every Auto SPCS2022 record citing a superseded capture. Since 0.9.0, also the NATRF2022 UTM verification paragraph (`_utm_verification_paragraphs`): `UTM_NATRF2022_ANCHOR_COUNT` (34 beta NCAT positions, captured 2026-10-22) and the inverse-scale bound `UTM_NATRF2022_INVERSE_SCALE_BOUND` (0.0008 ppm), both measured against beta NCAT, are to be re-measured against the official release's NCAT and restated (DESIGN.md #72). | `review/nsrs-h1-anchors/capture_h1_anchors.py`; for the Auto TO block, `review/autozone-z0/capture_ngs_polygons.py` | `tests/test_spcs2022_disclosure.py`; for the Auto TO block, `tests/test_autozone_outputs.py::test_the_spcs2022_to_block_reads_exactly` |
| `michspc/selftest.py` | The frozen bundle's own SPCS2022 anchor: zone 261008's `origin -0.15/-0.25` position, northing, easting and scale factor, transcribed from the fixture below because `tests/` is not in the bundle. Since 0.9.0 also check 15's NATRF2022 UTM zone 16N anchor (beta NCAT, `r3k0_2_spcs2022_000.html`, captured 2026-10-22; DESIGN.md #72), transcribed from `tests/fixtures/utm_anchors.py`. | `review/nsrs-h1-anchors/capture_h1_anchors.py`; for the UTM anchor, `review/autozone-r0/probe3_ncat.py` | `tests/test_selftest.py::test_the_selftests_spcs2022_anchor_is_the_frozen_beta_ncat_value`; for the UTM anchor, `tests/test_selftest.py::test_the_selftests_utm_anchors_are_the_frozen_ncat_captures` |
| `tests/fixtures/spcs2022_engine_anchors.py` | The 63 beta-NCAT projection anchors and the 19 published zone-parameter rows they are checked beside. | `review/nsrs-h1-anchors/capture_h1_anchors.py` | `tests/test_projection_engines.py` |
| `michspc/spc/autozone_spcs2022.py` | Auto zone's county -> SPCS2022 low-distortion zone table and the Isle Royale rule (Keweenaw at or north of 47.65 N is U61K), measured from NGS's beta "Multizone Complete Zones" feature layer in its native Web Mercator, captured 2026-10-22. | `review/autozone-z0/capture_ngs_polygons.py` | `tests/test_autozone_tables.py` |
| `tests/fixtures/autozone_anchors.py` | The 123 beta-NCAT SPCS2022 zone-pick anchors Auto zone is pinned to (Z0's live captures and the autozone-r0 recon's), beside 124 production-NCAT SPCS 83 picks; all captured 2026-10-22. | `review/autozone-z0/capture_anchors.py` | `tests/test_autozone_anchors.py` |
| `tests/fixtures/utm_anchors.py` | The 34 beta-NCAT NATRF2022 UTM anchors (zone 16N, northing, easting, convergence and scale as beta NCAT printed them) the NATRF2022 UTM zones are pinned to, beside 212 production-NCAT NAD83(2011) UTM anchors; all captured 2026-10-22 (DESIGN.md #72). | `review/autozone-r0/probe_ncat.py`, `review/autozone-r0/probe3_ncat.py` (recapture); `review/utm-u0/build_anchor_fixture.py` (rewrites the fixture) | `tests/test_utm.py` |
| `tests/fixtures/utm_records.py` | The whole UTM job records and the two mixed METHOD sections, pinned as literal text: the NATRF2022 UTM paragraph's beta-NCAT anchor count and capture date, and the mixed SPCS2022 + UTM-2022 section's quotation of the SPCS2022 METHOD prose with both beta captures' dates and digests (DESIGN.md #72). They change whenever `michspc/fileio/report.py`'s beta-derived text does. | `review/utm-u4/preview_records.py` (regenerates the whole records) | `tests/test_utm_jobs.py` |

## The frozen captures those artifacts were read from

Not scanned by the inventory test — they are NGS's own bytes, held unmodified,
and they carry NGS's wording rather than this program's token. They are what
the harnesses above re-fetch and what the digests authenticate.

| Capture | Bytes | SHA-256 | Captured |
| --- | --- | --- | --- |
| `review/nsrs-n0/raw/zoneDefinitions.json` | 632,927 | `f222dac669503c8e25eb41d477bbb129b813b894b43e7d012effb9dc00bbc06a` | 2026-08-28 |
| `review/nsrs-n0/raw/zoneBounds.json` | 654,390 | `040f9d5a6e4af2587cb8306d05829a0efefd17a482b37f55678e4ea861f48b66` | 2026-08-29 |
| `review/nsrs-h1-anchors/anchors.json` | 98,787 | `76d2b61e57d2b9ddeb5466bcc3add92907f687efe8221cd0914c595707390a2d` | 2026-08-28 |
| `review/nsrs-h3-recon/ifdm/raw/pubs/NOAA_TR_NOS_NGS_0062.pdf` | 4,505,404 | `b0d25a26d827daf6ff01c8ba8d96ee66b12ca200be335f72732f10794d2ae72a` | 2026-08-29 |
| `review/autozone-r0/raw/ngs_fs/mi_native.json` | 7,382,157 | `0b40098476f55a04d8bd9f5b4b162b2f573cddf00e7054c39693b7441e3c7cf7` | 2026-10-22, native Web Mercator (re-fetched byte-identical by the harness 2026-10-23); the geometry `tests/test_autozone_tables.py` reads. The `outSR=4269` capture beside it, `mi_4269.json` (`658c4ead…2099`), is server-shifted about 0.9 m (WGS 84 -> NAD 83) and is kept only as the recon's record and the suite's negative control |

The per-request manifests beside each capture (`review/nsrs-n0/raw/*_manifest.json`,
`review/nsrs-h1-anchors/raw/manifest.json`) record one digest per fetched
response, and `review/nsrs-h1-anchors/CAPTURE.md` is the capture record for the
anchors, including what they do NOT prove.

## Operational hazard to re-read before recapturing

`beta.ngs.noaa.gov/api/*` answers `200 OK` carrying `N/A` or `{}` where
`geodesy.noaa.gov` returns numbers — **beta's REST API fails open** (DESIGN.md
#61). A recapture that silently collects `N/A` and re-freezes it would replace
real anchors with nothing, and every digest would still be internally
consistent. Check the values, not only the status code.
