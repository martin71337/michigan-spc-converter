"""Work package W4 of the WGS 84 build: no same-frame job moves by a byte.

W4 (docs/PLAN-wgs84.md section 3.6) adds the FRAME TRANSFORMATION block to
the job record, conditional columns to the audit CSV, a geodetic-to-geodetic
branch to every output, and frame-aware wording to the sentences a
transformation would otherwise make false. Every one of those is conditional
on a frame transformation having run. This file is the proof that the
condition holds the other way: a job with no transformation writes what it
wrote before W4, every member, every byte.

**The digests below were computed by the code BEFORE W4** - commit 8201968
(the W3 commit), with ``_written`` exactly as it stands here - so this is a
cross-version pin of the kind ``tests/test_orthometric_regression.py`` is
(whose eighteen v0.5.0 digests remain the floor, untouched). That file
covers nine zone-input jobs and no record; this one adds one job of every
direction that has a geodetic end or a record branch W4 touched, and digests
the RECORD too, with its two run-dependent parts normalised: the
``Generated`` timestamp, and the temporary folder every path sits under.

Jobs, and the W4 branch each one holds closed:

* ``z2z`` - zone to zone, with an outside-zone warning: the WARNINGS section
  (job-level warnings are W4's).
* ``g2z`` - NAD83(2011) geodetic to MI-C, positive west, a blank Z: the
  ELEVATIONS "does not depend on elevation" paragraph, and the OUTPUT
  section's Reference frame line.
* ``z2g_ellipsoid`` - MI-S to NAD83(2011) geodetic, ELLIPSOID heights,
  horizontal: the ELLIPSOID HEIGHT CONVERSION block's "exactly as supplied"
  sentence, the DD/DMS members and the audit CSV's ellipsoid headings.
* ``g2z_hv`` - geodetic in, horizontal and vertical NGVD 29 to NAVD 88: the
  vertical blocks beside the geodetic input block.
* ``vo_zone`` and ``vo_geodetic`` - vertical only, on a zone and on
  NAD83(2011) positions with ellipsoid heights: the two vertical-only
  records, which W4 does not alter.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

import pytest

from michspc.fileio import exports
from michspc.job import (
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.vertical import NAVD88, NGVD29, HeightKind
from michspc.spc.zones import MI_CENTRAL, MI_NORTH, MI_SOUTH

GEODETIC_ROWS = (
    "1,42.7325,84.5555,250.000,PIN\n"
    "2,43.8000,84.3670,,BLANK\n"
    "3,45.1000,85.1000,190.500,ROD\n"
)
"""Three NAD 83 positions, positive west, one with a blank Z."""

GRID_ROWS = (
    "1,500000.000,8000000.000,900.000,PIN\n"
    "2,510000.000,8010000.000,,BLANK\n"
    "3,90000.000,2000000.000,800.000,FAR\n"
)
"""MI-N grid coordinates; the third lies far outside MI-C's extent, so the
zone-to-zone job raises a warning."""

SOUTH_ROWS = (
    "101,449212.689,13072628.343,165.250,IRON PIPE\n"
    "102,449300.000,13072700.000,,BLANK Z\n"
)
"""MI-S grid coordinates in international feet, one blank Z."""


def _jobs():
    yield "z2z", GRID_ROWS, dict(
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_NORTH,
        target_zone=MI_CENTRAL,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=None,
    )
    yield "g2z", GEODETIC_ROWS, dict(
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_CENTRAL,
        input_unit=METERS,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=LongitudeConvention.POSITIVE_WEST,
    )
    yield "z2g_ellipsoid", SOUTH_ROWS, dict(
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        input_unit=INTERNATIONAL_FEET,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        input_height_kind=HeightKind.ELLIPSOID,
    )
    yield "g2z_hv", GEODETIC_ROWS, dict(
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_NORTH,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.POSITIVE_WEST,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    yield "vo_zone", GRID_ROWS, dict(
        direction=Direction.VERTICAL_ONLY,
        source_zone=MI_NORTH,
        target_zone=None,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=None,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    yield "vo_geodetic", GEODETIC_ROWS, dict(
        direction=Direction.VERTICAL_ONLY,
        source_zone=None,
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.POSITIVE_WEST,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
        input_height_kind=HeightKind.ELLIPSOID,
    )


_GENERATED = re.compile(r"^Generated          .*$", re.MULTILINE)


# --------------------------------------------------------------------------
# RECORDED SUPERSESSION - DESIGN.md #70, plan W4b: the frozen text stated a
# zone the job does not have.
#
# The vo_geodetic record (vertical only, geodetic input, no zone anywhere)
# was frozen at 8201968 with eight passages that describe a State Plane job:
# the SPCS 83 Lambert METHOD, its Appendix C and 27-position NCAT
# verification, the "manual section 4.1" and "Combined factor" lines, the
# grid-scale-factor ELEVATIONS paragraph, "inside its zone", "moved between
# zones", and "both zones' coordinates". W4b replaced each with zone-less text
# that is true of this job. The digest is NOT re-frozen - that would discard
# the cross-version property for every other byte of the record - but, on
# #66/#68's precedent, the record is RESPELLED back: each W4b passage, which
# must occur exactly once, is put back to its frozen W3 text before the
# digest, so the frozen digest still holds every other byte of it. The
# respelling is pinned to touch only vo_geodetic's record and only these
# eight passages (``test_the_w4b_respelling_is_exact``), and the new text is
# pinned present in tests/test_frame_disclosure.py.
# --------------------------------------------------------------------------

W4B_RESPELLING = (
    (
        "Method             No map projection runs in this job: its positions are\n"
        "                   geodetic, no State Plane zone is involved, and the\n"
        "                   horizontal coordinates are reproduced unconverted. Each\n"
        "                   point's elevation is converted at its NAD83(2011) position,\n"
        "                   which is the input position itself: the GEOID18 geoid\n"
        "                   height is read there, and the vertical datum transformation\n"
        "                   stated below is applied.\n",
        "Authority          NOAA Manual NOS NGS 5, State Plane Coordinate System\n"
        "                   of 1983 (Stem, January 1989; reprinted with minor\n"
        "                   corrections March 1990)\n"
        "\n"
        "Equations          The rigorous Lambert conformal conic mapping\n"
        "                   equations of section 3.1 - zone constants (3.12),\n"
        "                   direct conversion (3.13), inverse conversion (3.14).\n"
        "                   Exact at any latitude, with no approximation term.\n"
        "\n"
        "Ellipsoid          GRS 80, the ellipsoid of NAD 83 (manual section 1.7).\n"
        "                   Only the semimajor axis and the flattening are stored;\n"
        "                   every other constant is derived from those two.\n",
    ),
    (
        "The geoid heights are checked against NGS's own geoid height service. Twenty\n"
        "Michigan positions were computed by NGS for each model this job read\n"
        "(GEOID18), and those results are held in the test suite as fixed reference\n"
        "values. This software reproduces them to within 1 mm, the precision NGS\n"
        "publishes geoid heights to.\n"
        "\n"
        "The ellipsoid-height arithmetic is checked at fourteen published NGS\n"
        "benchmarks whose datasheets carry both an NAVD 88 height and a GEOID18 geoid\n"
        "height: given h = H + N from those figures, this software returns the\n"
        "published H to within 1.5 mm.\n",
        "The zone constants used above are not taken on trust. The manual\n"
        "publishes, in Appendix C, the constants NGS computed for every Lambert\n"
        "zone. This software stores only the DEFINING constants - the standard\n"
        "parallels, the grid origin, the central meridian - and derives the rest.\n"
        "Its test suite recomputes all of them and requires a match with NGS's\n"
        "published figures to the last decimal place NGS printed, for all three\n"
        "Michigan zones.\n"
        "\n"
        "The conversion itself is checked against the National Geodetic Survey's\n"
        "own Coordinate Conversion and Transformation Tool (NCAT). Twenty-seven\n"
        "positions spanning the three zones were converted by NCAT, and those\n"
        "results are held in the test suite as fixed reference values. This\n"
        "software reproduces them to within 0.5 mm - which is the precision NCAT\n"
        "publishes, so the agreement is as close as the reference permits.\n",
    ),
    (
        "Elevation factor   R / (R + H + N), NOAA Manual NOS NGS 5 section 4.1\n",
        "Elevation factor   R / (R + H + N), manual section 4.1\n",
    ),
    (
        "                   N = geoid height, interpolated from the grid above\n\n",
        "                   N = geoid height, interpolated from the grid above\n"
        "Combined factor    grid scale factor x elevation factor\n\n",
    ),
    (
        "For those points the elevation factor is written as 'N/A' in the exports. It\n"
        "is NOT set to 1.0. The positions do not use it.\n",
        "For those points the elevation factor and combined factor are written\n"
        "as 'N/A' in the exports. They are NOT set to 1.0, and the grid\n"
        "scale factor is not substituted for the combined factor: there is no\n"
        "honest combined factor without an elevation, and a plausible-looking\n"
        "number here would travel onto a drawing. The horizontal conversion is\n"
        "unaffected - it does not depend on elevation at all.\n",
    ),
    (
        "None. Every point converted cleanly.\n",
        "None. Every point converted cleanly, inside its zone.\n",
    ),
    (
        "purpose. A coordinate file produced by a conversion should not\n",
        "purpose. A coordinate file that has been moved between zones should not\n",
    ),
    (
        "    Every computed quantity for every point, with a header row: the\n"
        "    position the file supplied, geoid and ellipsoid height, the\n"
        "    elevation factor, and any warnings. No zone is involved, so the\n"
        "    scale-factor and convergence columns read N/A. This is the file\n"
        "    that answers 'how was this number derived' without re-running\n",
        "    Every computed quantity for every point, with a header row: both\n"
        "    zones' coordinates, the geodetic position the conversion pivoted\n"
        "    through, geoid and ellipsoid height, both convergence angles, the\n"
        "    grid, elevation and combined factors, and any warnings. This is the\n"
        "    file that answers 'how was this number derived' without re-running\n",
    ),
)
"""(W4b text, frozen W3 text) for each passage W4b rewrote on vo_geodetic."""


# --------------------------------------------------------------------------
# RECORDED SUPERSESSION - the closing gate of the WGS 84 build, finding L7.
#
# The FILES WRITTEN branch for a vertical job said "the geoid model the
# factors were computed from" on a zone-less job, which has one factor (the
# same record says "No combined factors exist for this job"): the H2 sweep of
# interim gate 2 matched the zone-only words and missed "the factors". It is
# also in released 0.7.1. It now names the elevation factor, as does the
# METHOD block's "H = orthometric height as used for the factors" line, which
# the sweep of report.py for the plural found on the same jobs. Exactly as W4b
# and gate 2 did, the digest is NOT re-frozen: these two passages, each of
# which must occur exactly once and only on vo_geodetic, are respelled back
# to their W3 text before the digest
# (``test_the_closing_gate_respelling_is_exact``).
# --------------------------------------------------------------------------

CLOSING_RESPELLING = (
    (
        "                   H = orthometric height as used for the elevation factor\n",
        "                   H = orthometric height as used for the factors\n",
    ),
    (
        "    the elevation factor was computed from.\n",
        "    the factors were computed from.\n",
    ),
)
"""(closing-gate text, frozen W3 text) for the two passages L7 rewrote: the
FILES WRITTEN clause the reviewer found, and the METHOD block's ``H =`` line
the sweep of report.py for "factors" found beside it."""


def _respelled_before_the_closing_gate(text: str) -> tuple[str, int]:
    """``text`` with the L7 passage put back to its W3 spelling, and how many
    passages were found; refused if one occurs more than once."""
    found = 0
    for new, old in CLOSING_RESPELLING:
        count = text.count(new)
        if count > 1:
            raise AssertionError(f"L7 passage occurs {count} times: {new[:60]!r}")
        if count == 1:
            text = text.replace(new, old)
            found += 1
    return text, found


def _respelled_as_w3(text: str) -> tuple[str, int]:
    """``text`` with every W4b passage put back to its W3 spelling, and how
    many passages were found. Each passage is replaced only when it occurs
    exactly once; a passage occurring twice is a test defect, refused."""
    found = 0
    for new, old in W4B_RESPELLING:
        count = text.count(new)
        if count > 1:
            raise AssertionError(f"W4b passage occurs {count} times: {new[:60]!r}")
        if count == 1:
            text = text.replace(new, old)
            found += 1
    return text, found


def _normalised(member: str, body: bytes, root: Path) -> bytes:
    """The record without its timestamp and with the temporary root replaced
    (and, on the one zone-less record, respelled as W3 wrote it - see
    W4B_RESPELLING); every other member exactly as written."""
    if not member.endswith("_README.txt"):
        return body
    text = body.decode("utf-8")
    text = _GENERATED.sub("Generated          <normalised>", text)
    text = text.replace(str(root), "<ROOT>")
    if "\nConversion         vertical only\n" in text and (
        "No State\nPlane coordinate system is involved in this job." in text
    ):
        text, _found = _respelled_as_w3(text)
        text, _found = _respelled_before_the_closing_gate(text)
    return text.encode("utf-8")


def _written(root: Path) -> dict[str, str]:
    """``{"<job>/<member>": sha256}`` for every member of every job above."""
    digests: dict[str, str] = {}
    for name, rows, fields in _jobs():
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / "in.csv"
        source.write_text(rows, encoding="utf-8")
        settings = JobSettings(input_path=source, output_directory=folder, **fields)
        written = exports.write_all(run(settings), overwrite=True)
        with zipfile.ZipFile(written["archive"]) as archive:
            for member in sorted(archive.namelist()):
                body = _normalised(member, archive.read(member), root)
                digests[f"{name}/{member}"] = hashlib.sha256(body).hexdigest()
    return digests


FROZEN_AT_W3 = {
    # Computed at commit 8201968 by _written above (see the module docstring),
    # before any line of W4 existed. Not to be regenerated from later code:
    # a digest recomputed by the code it pins compares HEAD against HEAD.
    "g2z/in_MI-C.csv": "e1c69b00841d9c2d936eabedc52db2559102a472bd8d15d1895e77583c9fefb3",
    "g2z/in_MI-C_README.txt": "4e9f15c37f3ef77d4e9182cdabc166e2fca9d1dde53531f01233ea34817e51f0",
    "g2z/in_MI-C_full.csv": "4e5fed0cbdc802127c71d866bb42aabc0e4d7e427de4d5f47ed4742c53a6a634",
    "g2z_hv/in_MI-N.csv": "dc79e0da1c5e33314d46e7f2f35189a671f4eb3a2b45f9aa6e8d578bd5f5a38c",
    "g2z_hv/in_MI-N_README.txt": "6c7fe2fe8ae45dd46144188b7ad1370e51b7e7bab2cb285ea4600844f92d70b8",
    "g2z_hv/in_MI-N_full.csv": "800e7fcde6011eec14bee30f40125bdb72ac6332ab211d391d663b248d8e2828",
    "vo_geodetic/in_VERTICAL.csv": "a251d2c75c493d1f33aead90e69b686105e1a5dff4965b892585dd072cc68a9b",
    "vo_geodetic/in_VERTICAL_README.txt": "409cc2a1a952bb2f391916c6176cadd1460241d4a8f66a4c1ce5f34c9e45719a",
    "vo_geodetic/in_VERTICAL_full.csv": "b07b7cae6f6415c4f801f35a34200b8030d3bbfbf40c68a659bfe810b16ba4f6",
    "vo_zone/in_VERTICAL.csv": "af7530bf55cf43bba4bc19be1a3e79d634d32628a9a8022f809442032e7d13ca",
    "vo_zone/in_VERTICAL_README.txt": "4ab84c3d4ba6e292b07eafcb25ba7f18283faa6a73440ebbb09c438017674c73",
    "vo_zone/in_VERTICAL_full.csv": "644214a1cd3d597aa7bac1252cef189f1635d2ec5864dd880a22a79c12c59577",
    "z2g_ellipsoid/in_GEODETIC_DD.csv": "49273ba91dfb00d73f723ff885c11c9175944ed73f6e8e896aedb7a4fd1293ea",
    "z2g_ellipsoid/in_GEODETIC_DMS.csv": "b185f6934fa6ef8d0713adb2c401b30e6c6bcddcaf36909d979856606d35b04b",
    "z2g_ellipsoid/in_GEODETIC_README.txt": "6ab87f2104ad662b27788ba8c3c65c80f3bdcc9f5c72ecbbbb7f47090b634a54",
    "z2g_ellipsoid/in_GEODETIC_full.csv": "97a19e939b741eeb074376672d487c745ee0275fa037599a90302ffc5ae842ab",
    "z2z/in_MI-C.csv": "8c354f008647b275d4d52589e5722ae91343e7afe8df30fb02fcb36a2c6731ee",
    "z2z/in_MI-C_README.txt": "d53c6d0df37b6cfd78b66a9fb58f9fce446341604d35ea4863dbaacec2735bb7",
    "z2z/in_MI-C_full.csv": "65fcd1fd360559676620ed8b35a4b1808b05fe21a61fb661e061752f41c9cae0",
}


def test_the_frozen_list_covers_every_member_of_every_job():
    """Anti-vacuity: 3 members per job, 4 for the one job converting to geodetic."""
    jobs = [name for name, _rows, _fields in _jobs()]
    assert len(FROZEN_AT_W3) == 3 * len(jobs) + 1
    for name in jobs:
        assert any(member.startswith(f"{name}/") for member in FROZEN_AT_W3)


def test_no_same_frame_job_writes_a_different_byte_than_before_w4(tmp_path):
    written = _written(tmp_path)
    assert sorted(written) == sorted(FROZEN_AT_W3)
    differing = sorted(
        member for member in FROZEN_AT_W3 if FROZEN_AT_W3[member] != written[member]
    )
    assert not differing, f"these members moved: {', '.join(differing)}"


@pytest.mark.parametrize("member_suffix", ["_README.txt", "_full.csv"])
def test_the_comparison_would_notice_a_changed_byte(tmp_path, member_suffix):
    """A digest is only a pin if a changed member produces a different one."""
    written = _written(tmp_path)
    key = next(k for k in written if k.endswith(member_suffix))
    name, member = key.split("/", 1)
    archive = next((tmp_path / name).glob("*.zip"))
    with zipfile.ZipFile(archive) as opened:
        body = _normalised(member, opened.read(member), tmp_path)
    assert hashlib.sha256(body + b"\n").hexdigest() != written[key]


def _records(root: Path) -> dict[str, str]:
    """``{job: record text}``, timestamp and root normalised, NOT respelled."""
    _written(root)
    records = {}
    for name, _rows, _fields in _jobs():
        archive = next((root / name).glob("*.zip"))
        with zipfile.ZipFile(archive) as opened:
            member = next(m for m in opened.namelist() if m.endswith("_README.txt"))
            text = opened.read(member).decode("utf-8")
        text = _GENERATED.sub("Generated          <normalised>", text)
        records[name] = text.replace(str(root), "<ROOT>")
    return records


def test_the_w4b_respelling_is_exact(tmp_path):
    """Anti-vacuity and confinement, as #66's and #68's respelling pins are:

    * on vo_geodetic every one of the eight W4b passages is present, so the
      raw record no longer matches its frozen digest - and respelling exactly
      those eight passages restores it, byte for byte;
    * on every other job NOT ONE passage occurs, so the respelling cannot
      reach any other record: those are compared exactly as written;
    * respelling the W3 text again changes nothing (no W4b passage survives
      it), so the comparison is a fixed point, not a loop.
    """
    records = _records(tmp_path)
    vo = records["vo_geodetic"]
    respelled, found = _respelled_as_w3(vo)
    assert found == len(W4B_RESPELLING) == 8
    # The closing gate's one passage (L7) on top, pinned on its own below.
    respelled, _closing = _respelled_before_the_closing_gate(respelled)
    assert hashlib.sha256(vo.encode("utf-8")).hexdigest() != FROZEN_AT_W3[
        "vo_geodetic/in_VERTICAL_README.txt"
    ]
    assert hashlib.sha256(respelled.encode("utf-8")).hexdigest() == FROZEN_AT_W3[
        "vo_geodetic/in_VERTICAL_README.txt"
    ]
    assert _respelled_as_w3(respelled) == (respelled, 0)
    for name, text in records.items():
        if name == "vo_geodetic":
            continue
        assert _respelled_as_w3(text) == (text, 0), name


def test_the_closing_gate_respelling_is_exact(tmp_path):
    """L7's respelling, held to the same three rules as W4b's:

    * on vo_geodetic each new passage is present exactly once, and the old
      "the factors were computed from." and "as used for the factors" are
      gone - a zone-less job has one
      factor - so the raw record differs from its frozen digest;
    * W4b's respelling ALONE no longer restores the digest; W4b's plus this
      one does, byte for byte (asserted in test_the_w4b_respelling_is_exact);
    * on every other job neither the new passage occurs nor does the
      respelling touch anything - the zone jobs keep "the factors" (the
      vertical zone jobs here, g2z_hv and vo_zone, carry it unchanged).
    """
    records = _records(tmp_path)
    vo = records["vo_geodetic"]
    assert vo.count("the elevation factor was computed from.") == 1
    assert vo.count("as used for the elevation factor\n") == 1
    assert "the factors were computed from." not in vo
    assert "as used for the factors\n" not in vo
    w3_only, _found = _respelled_as_w3(vo)
    assert hashlib.sha256(w3_only.encode("utf-8")).hexdigest() != FROZEN_AT_W3[
        "vo_geodetic/in_VERTICAL_README.txt"
    ]
    respelled, found = _respelled_before_the_closing_gate(w3_only)
    assert found == len(CLOSING_RESPELLING) == 2
    assert _respelled_before_the_closing_gate(respelled) == (respelled, 0)
    for name, text in records.items():
        if name == "vo_geodetic":
            continue
        assert _respelled_before_the_closing_gate(text) == (text, 0), name
    for name in ("g2z_hv", "vo_zone"):
        assert "    the factors were computed from.\n" in records[name], name
        assert "as used for the factors\n" in records[name], name
