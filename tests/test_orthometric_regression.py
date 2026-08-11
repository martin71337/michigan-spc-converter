"""Every CSV a default job writes, digested against v0.5.0. Frozen.

Closing gate, LOW 3. The ellipsoid-height feature rests on one promise: a job
that does not opt in produces exactly what the released program produced. That
promise was checked by hand at the gate — nine archives written twice, once in
a worktree at tag v0.5.0 and once at HEAD, all members digested — and the
evidence is committed at ``review/wp-e-byte-identity/``. But a captured
artifact does not fail when someone breaks it later, and the unit test that
carried the promise compared HEAD against HEAD: an unconditional regression, a
metre added to every height, left it green.

**These digests were computed by v0.5.0 itself**, not by the current code, so
they are a genuine cross-version pin. If a later change moves any byte of any
clean export or audit CSV on any of these nine ordinary jobs, this fails and
names the member.

Only the CSVs are pinned, and deliberately so: the job record embeds a
generation timestamp and the input and output paths, so its digest differs
between any two runs of identical code. What the record says is pinned by
content elsewhere, in the disclosure suites.
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from michspc.fileio import exports, geoid
from michspc.job import (
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS, US_SURVEY_FEET
from michspc.spc.vertical import NAVD88, NGVD29
from michspc.spc.zones import MI_CENTRAL, MI_NORTH, MI_SOUTH

DIGESTS = Path(__file__).parent / "fixtures" / "orthometric_output_digests.txt"

ROWS = (
    "1,500000.000,8000000.000,900.000,PIN\n"
    "2,510000.000,8010000.000,0.00,ZEROED\n"
    "3,520000.000,8020000.000,,BLANK\n"
)
"""One populated Z, one exactly-zero Z and one blank Z — the three the
elevation paths treat differently, in every job below."""


def _configurations():
    """The nine jobs, exactly as the gate's harness built them."""
    configurations = []
    for unit in (INTERNATIONAL_FEET, US_SURVEY_FEET, METERS):
        configurations.append(
            (
                f"z2z_{unit.code}",
                dict(
                    direction=Direction.ZONE_TO_ZONE,
                    source_zone=MI_NORTH,
                    target_zone=MI_CENTRAL,
                    input_unit=unit,
                    output_unit=unit,
                ),
            )
        )
        configurations.append(
            (
                f"z2g_{unit.code}",
                dict(
                    direction=Direction.ZONE_TO_GEODETIC,
                    source_zone=MI_SOUTH,
                    target_zone=None,
                    input_unit=unit,
                    output_unit=unit,
                ),
            )
        )
    configurations.append(
        (
            "z2z_vert",
            dict(
                direction=Direction.ZONE_TO_ZONE,
                source_zone=MI_NORTH,
                target_zone=MI_CENTRAL,
                input_unit=INTERNATIONAL_FEET,
                output_unit=INTERNATIONAL_FEET,
                vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
                source_vertical_datum=NGVD29,
                target_vertical_datum=NAVD88,
            ),
        )
    )
    configurations.append(
        (
            "vert_only",
            dict(
                direction=Direction.VERTICAL_ONLY,
                source_zone=MI_NORTH,
                target_zone=None,
                input_unit=METERS,
                output_unit=METERS,
                vertical_mode=VerticalMode.VERTICAL,
                source_vertical_datum=NGVD29,
                target_vertical_datum=NAVD88,
            ),
        )
    )
    configurations.append(
        (
            "swap",
            dict(
                direction=Direction.VERTICAL_ONLY,
                source_zone=MI_NORTH,
                target_zone=None,
                input_unit=METERS,
                output_unit=METERS,
                vertical_mode=VerticalMode.VERTICAL,
                source_vertical_datum=NAVD88,
                target_vertical_datum=NAVD88,
                source_geoid_model=geoid.GEOID12B_MODEL,
                geoid_model=geoid.GEOID18_MODEL,
            ),
        )
    )
    return configurations


def _written_digests(root: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for name, configuration in _configurations():
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / "in.csv"
        source.write_text(ROWS, encoding="utf-8")

        settings = dict(
            input_path=source,
            output_directory=folder,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        )
        settings.update(configuration)
        # A vertical-only job reading State Plane states no convention: the
        # file carries no longitude column, and the program refuses one.
        if configuration.get("direction") is Direction.VERTICAL_ONLY:
            settings["longitude_convention"] = None

        written = exports.write_all(run(JobSettings(**settings)), overwrite=True)
        with zipfile.ZipFile(written["archive"]) as archive:
            for member in sorted(archive.namelist()):
                if member.endswith("_README.txt"):
                    continue  # timestamped and path-bearing; pinned by content
                body = archive.read(member)
                digests[f"{name}/{member}"] = hashlib.sha256(body).hexdigest()
    return digests


def _frozen() -> dict[str, str]:
    frozen: dict[str, str] = {}
    for line in DIGESTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        member, digest = line.split()
        frozen[member] = digest
    return frozen


def test_the_frozen_list_covers_every_member_of_every_configuration():
    """Anti-vacuousness: a fixture that lost half its lines would let half the
    outputs drift while the comparison below still passed."""
    frozen = _frozen()
    assert len(frozen) == 18
    for name, _configuration in _configurations():
        assert any(member.startswith(f"{name}/") for member in frozen)


def test_no_default_job_writes_a_different_byte_than_v0_5_0(tmp_path):
    """The regression floor, against digests v0.5.0 itself computed."""
    written = _written_digests(tmp_path)
    frozen = _frozen()

    assert sorted(written) == sorted(frozen)
    differing = {
        member: (frozen[member], written[member])
        for member in frozen
        if frozen[member] != written[member]
    }
    assert not differing, (
        "these members differ from what v0.5.0 wrote for the same job: "
        + ", ".join(sorted(differing))
    )


@pytest.mark.parametrize("name", ["z2z_ift", "z2g_m", "swap"])
def test_the_comparison_would_notice_a_changed_byte(tmp_path, name):
    """Anti-vacuousness for the comparison itself: a digest is only a pin if a
    changed file produces a different one."""
    written = _written_digests(tmp_path)
    member = next(key for key in written if key.startswith(f"{name}/"))

    path = tmp_path / name
    archive = next(path.glob("*.zip"))
    with zipfile.ZipFile(archive) as opened:
        body = opened.read(member.split("/", 1)[1])

    altered = hashlib.sha256(body + b"\n").hexdigest()
    assert altered != written[member]
