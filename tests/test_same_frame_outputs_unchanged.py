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


def _normalised(member: str, body: bytes, root: Path) -> bytes:
    """The record without its timestamp and with the temporary root replaced;
    every other member exactly as written."""
    if not member.endswith("_README.txt"):
        return body
    text = body.decode("utf-8")
    text = _GENERATED.sub("Generated          <normalised>", text)
    text = text.replace(str(root), "<ROOT>")
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
