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

**The audit CSV is compared with its two DMS columns removed** (docs/DESIGN.md
amendment #66, the owner's instruction, 2026-09-03). ``Latitude (DMS)`` and
``Longitude (DMS)`` did not exist when v0.5.0 computed these digests, so the
raw member can no longer match them - and re-freezing the digests at HEAD
would have thrown away the cross-version property this file exists for.
Instead ``_without_columns`` parses the member and re-renders it through the
writer's own ``_render_csv`` with exactly those two headings dropped, and THAT
text is digested: every byte v0.5.0 wrote is still pinned to v0.5.0's own
digest, and the two new columns are pinned separately in
``tests/test_audit_dms.py``. ``test_the_stripping_is_exact`` establishes the
parse-and-render round trip reproduces an unmodified member byte for byte, so
the comparison is not passing through a lossy channel; and
``test_the_raw_member_no_longer_matches_but_the_stripped_one_does``
establishes the columns are really there - the stripped comparison would be
vacuous if nothing were stripped.
"""

from __future__ import annotations

import csv
import hashlib
import io
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


DMS_COLUMNS = ("Latitude (DMS)", "Longitude (DMS)")
"""The two audit columns added after v0.5.0 froze these digests (#66)."""


CONVERGENCE_COLUMNS = ("Source convergence", "Convergence")
"""The two audit columns whose spelling changed after v0.5.0 (#68): the
fields are dash-separated where v0.5.0 wrote spaces."""


def _v0_5_0_convergence(cell: str) -> str:
    """``-16-49-17.76`` -> ``-16 49 17.76``: the cell as v0.5.0 spelled it.

    The sign character is kept and every remaining dash becomes the space it
    replaced. A cell that is not of that shape (``N/A``) is returned as is,
    exactly as v0.5.0 wrote it too."""
    if not cell or cell[0] not in "+-":
        return cell
    return cell[0] + cell[1:].replace("-", " ")


def _without_columns(body: bytes, names: tuple[str, ...]) -> bytes:
    """The member with the named columns dropped and the convergence cells
    respelled as v0.5.0 spelled them, re-rendered by the writer's own
    ``_render_csv`` so the remaining bytes are exactly what the writer would
    have produced without those columns and with the old separator."""
    text = body.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    header = rows[0]
    keep = [index for index, column in enumerate(header) if column not in names]
    respell = [index for index, column in enumerate(header) if column in CONVERGENCE_COLUMNS]
    stripped = []
    for line, row in enumerate(rows):
        cells = list(row)
        if line > 0:
            for index in respell:
                cells[index] = _v0_5_0_convergence(cells[index])
        stripped.append([cells[index] for index in keep])
    return exports._render_csv(stripped).encode("utf-8")


DMS_EXPORT_SUFFIX = "_GEODETIC_DMS.csv"
DD_EXPORT_SUFFIX = "_GEODETIC_DD.csv"


def _frozen_name(member: str) -> str | None:
    """The name v0.5.0 gave this member, or None for a member v0.5.0 never
    wrote. Converting TO geodetic now names its clean export ``_GEODETIC_DD``
    and adds ``_GEODETIC_DMS`` (#67): the DD member is compared under its
    old name, byte for byte, and the DMS member is pinned in
    ``tests/test_geodetic_dms_export.py`` instead."""
    if member.endswith(DMS_EXPORT_SUFFIX):
        return None
    if member.endswith(DD_EXPORT_SUFFIX):
        return member[: -len(DD_EXPORT_SUFFIX)] + "_GEODETIC.csv"
    return member


def _pinned_bytes(member: str, body: bytes) -> bytes:
    """What is digested for a member: the audit CSV without its post-v0.5.0
    columns, every other member as written."""
    if member.endswith("_full.csv"):
        return _without_columns(body, DMS_COLUMNS)
    return body


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
                frozen_name = _frozen_name(member)
                if frozen_name is None:
                    continue  # the DMS export, pinned in its own suite (#67)
                body = _pinned_bytes(member, archive.read(member))
                digests[f"{name}/{frozen_name}"] = hashlib.sha256(body).hexdigest()
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
    frozen_name = member.split("/", 1)[1]
    with zipfile.ZipFile(archive) as opened:
        # The written name may differ from the frozen one (#67): find the
        # member that is compared under this frozen name.
        written_name = next(
            name for name in opened.namelist() if _frozen_name(name) == frozen_name
        )
        body = opened.read(written_name)

    altered = hashlib.sha256(_pinned_bytes(written_name, body) + b"\n").hexdigest()
    assert altered != written[member]


def _audit_members(tmp_path) -> list[tuple[str, bytes]]:
    _written_digests(tmp_path)
    members = []
    for name, _configuration in _configurations():
        archive = next((tmp_path / name).glob("*.zip"))
        with zipfile.ZipFile(archive) as opened:
            for member in opened.namelist():
                if member.endswith("_full.csv"):
                    members.append((f"{name}/{member}", opened.read(member)))
    assert len(members) == 9
    return members


def test_the_stripping_is_exact(tmp_path):
    """Dropping nothing reproduces every audit member byte for byte apart
    from the convergence respelling, so the parse-and-render channel the
    comparison passes through is lossless: re-rendering the respelled text
    with the respelling applied again is a fixed point, and re-rendering the
    ORIGINAL rows through ``_render_csv`` alone reproduces the member."""
    for _member, body in _audit_members(tmp_path):
        rows = list(csv.reader(io.StringIO(body.decode("utf-8"), newline="")))
        assert exports._render_csv(rows).encode("utf-8") == body
        once = _without_columns(body, ())
        assert _without_columns(once, ()) == once
        # The respelling touched only the two convergence columns, and only
        # by turning dashes into spaces: the digits are untouched.
        header = rows[0]
        for original, respelled in zip(rows[1:], list(csv.reader(io.StringIO(once.decode("utf-8"), newline="")))[1:]):
            for index, column in enumerate(header):
                if column in CONVERGENCE_COLUMNS:
                    assert respelled[index] == _v0_5_0_convergence(original[index])
                    assert respelled[index].replace(" ", "") == original[index].replace("-", "").replace(" ", "") or original[index][0] in "+-"
                else:
                    assert respelled[index] == original[index]


def test_the_v0_5_0_respelling_is_what_it_claims():
    assert _v0_5_0_convergence("-16-49-17.76") == "-16 49 17.76"
    assert _v0_5_0_convergence("+00-14-58.30") == "+00 14 58.30"
    assert _v0_5_0_convergence("N/A") == "N/A"
    assert _v0_5_0_convergence("") == ""


def test_the_raw_member_no_longer_matches_but_the_stripped_one_does(tmp_path):
    """The DMS columns are really in the file (the raw digest differs from
    v0.5.0's), and removing exactly those two is what restores v0.5.0's
    bytes - so the comparison above is neither vacuous nor lenient."""
    frozen = _frozen()
    for member, body in _audit_members(tmp_path):
        assert hashlib.sha256(body).hexdigest() != frozen[member]
        assert (
            hashlib.sha256(_without_columns(body, DMS_COLUMNS)).hexdigest()
            == frozen[member]
        )
        header = body.decode("utf-8").splitlines()[0].split(",")
        for column in DMS_COLUMNS:
            assert column in header
