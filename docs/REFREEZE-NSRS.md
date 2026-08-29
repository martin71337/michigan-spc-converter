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

**The release gate will refuse to build while any `NGS beta` tag remains,
unless an explicit acknowledgement flag is passed**, so that every beta-era
release is a conscious act rather than a default (DESIGN.md #61; the `-dev`
marker idiom). **That flag arrives with work package N8** (packaging,
self-test and build gates) and is not in `tools/build_release.py` yet. Until it
is, this document and its inventory test are the whole mechanism.

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
| `michspc/fileio/report.py` | The job record's SPCS2022 METHOD and verification prose — the capture dates, both digests, and the beta-NCAT anchor count it states to the surveyor. | `review/nsrs-h1-anchors/capture_h1_anchors.py` | `tests/test_spcs2022_disclosure.py` |
| `tests/fixtures/spcs2022_engine_anchors.py` | The 63 beta-NCAT projection anchors and the 19 published zone-parameter rows they are checked beside. | `review/nsrs-h1-anchors/capture_h1_anchors.py` | `tests/test_projection_engines.py` |

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
