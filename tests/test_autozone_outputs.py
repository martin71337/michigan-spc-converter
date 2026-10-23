"""Work package Z3: what an Auto zone job WRITES (docs/PLAN-options-autozone.md).

Every expectation here comes from outside the code under test:

* **Which zone, which county**: the frozen NCAT anchors
  (``tests/fixtures/autozone_anchors.py``) - NGS's own zone answer for each
  position, and the county named in the anchor's tag. The files are built
  from those positions and the expected file of every point is NCAT's zone.
* **What a zone's clean file holds**: the fixed-zone job of that zone over
  the SAME input, which this program has written since 0.1.0 and the digest
  pins hold - each Auto clean file must be exactly that job's lines for the
  points NCAT put in the zone, byte for byte, in file order.
* **The record's Auto TO block**: written out below by hand, line for line,
  for one mixed-zone job of each system.

Pinned:

1. **Members.** One clean PNEZD file per zone used, ``<stem>_<abbrev>.csv``,
   stem ``<input>_AUTO-SPCS83`` / ``<input>_AUTO-SPCS2022``, zones in
   registry order; no file for an unused zone; audit and record after them.
2. **No cross-zone clean rows** (interim gate over Z0-Z2, HIGH 1):
   ``clean_pnezd_rows`` and ``verify_round_trip`` refuse an Auto result
   without a zone, or with a zone it did not use, at the reviewer's input -
   so mixed rows can never reach a writer as one file.
3. **Verifiers** run per file on exactly that file's points; the partition
   check refuses a point missing, doubled, out of order or in the wrong
   zone's file.
4. **Audit CSV**: Target zone is the point's own zone, County and County
   FIPS follow it; every other cell is the fixed-zone job's.
5. **Record**: the TO block, the era, FILES WRITTEN, and a sweep of every
   sentence that names a zone, a target or the files, on Auto jobs of both
   systems, single- and mixed-zone, NAD83 and WGS 84 input.
6. **Observation date source** wording (TODAY / ENTERED / None).
"""

from __future__ import annotations

import csv
import dataclasses
import datetime
import io
import zipfile

import pytest

from michspc import job
from michspc.fileio import exports, pnezd, report
from michspc.fileio.writers import WriteError
from michspc.job import (
    AUTO_ZONE,
    Direction,
    JobSettings,
    LongitudeConvention,
    ObservationDateSource,
    VerticalMode,
    run,
)
from michspc.spc.frames import ITRF2020, NAD83_2011, NATRF2022, WGS84_G2296
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.vertical import NAVD88, NGVD29, HeightKind
from michspc.spc.zones import MI_CENTRAL, MI_NORTH, MI_SOUTH, zone_by_code
from michspc.spc.autozone_spcs2022 import NGS_POLYGONS_CITATION
from tests.fixtures.autozone_anchors import ANCHORS

NEG = LongitudeConvention.NEGATIVE_WEST


def anchor(tag: str, system: str):
    (found,) = [a for a in ANCHORS if a.tag == tag and a.system == system]
    return found


def county_of(tag: str) -> tuple[str, str]:
    """'COUNTY 26001 Alcona' -> ('Alcona', '26001'): the county the anchor's
    capture was taken in, from the fixture, not from the program."""
    _, fips, name = tag.split(" ", 2)
    return name, fips


# The mixed-zone files. File order deliberately interleaves the zones.
TAGS_83 = (
    "COUNTY 26001 Alcona",  # NCAT 2112
    "COUNTY 26025 Calhoun",  # NCAT 2113
    "COUNTY 26003 Alger",  # NCAT 2111
    "COUNTY 26019 Benzie",  # NCAT 2112
    "COUNTY 26005 Allegan",  # NCAT 2113
)
TAGS_2022 = (
    "COUNTY 26001 Alcona",  # NCAT 261006
    "ISLE_ROYALE_LAND",  # NCAT 261018
    "COUNTY 26025 Calhoun",  # NCAT 261007
    "COUNTY 26083 Keweenaw",  # NCAT 261016 (mainland)
    "COUNTY 26003 Alger",  # NCAT 261014
    "COUNTY 26019 Benzie",  # NCAT 261011
    "COUNTY 26005 Allegan",  # NCAT 261008
)
ELEVATIONS = (250.0, None, 190.5, 300.25, None, 210.0, 275.5)


def write_input(tmp_path, tags, system, name="pts"):
    path = tmp_path / f"{name}.csv"
    lines = []
    for index, tag in enumerate(tags):
        a = anchor(tag, system)
        z = ELEVATIONS[index]
        lines.append(f"{index + 1},{a.latitude},{a.longitude},{'' if z is None else z},P{index + 1}\r\n")
    path.write_bytes("".join(lines).encode("ascii"))
    return path


def auto_settings(path, frame, **fields):
    base = dict(
        input_path=path,
        output_directory=path.parent,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=AUTO_ZONE,
        input_unit=METERS,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=NEG,
        geodetic_frame=frame,
        auto_frame=frame,
    )
    base.update(fields)
    return JobSettings(**base)


def members_of(archive) -> dict[str, str]:
    with zipfile.ZipFile(archive) as opened:
        return {name: opened.read(name).decode("utf-8") for name in opened.namelist()}


def expected_zones(tags, system) -> list[str]:
    return [anchor(tag, system).expected for tag in tags]


def auto_job(tmp_path, tags, system, frame, **fields):
    path = write_input(tmp_path, tags, system)
    result = run(auto_settings(path, frame, **fields))
    return result, exports.write_all(result)["archive"]


SYSTEMS = [
    pytest.param(TAGS_83, "SPCS 83", NAD83_2011, "AUTO-SPCS83", id="spcs83"),
    pytest.param(TAGS_2022, "SPCS2022", NATRF2022, "AUTO-SPCS2022", id="spcs2022"),
]


# --------------------------------------------------------------------------
# 1. Members.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tags, system, frame, suffix", SYSTEMS)
def test_one_clean_file_per_zone_used_named_for_the_zone(tmp_path, tags, system, frame, suffix):
    result, archive = auto_job(tmp_path, tags, system, frame)
    assert archive.name == f"pts_{suffix}.zip"
    # NCAT's zones, in the registry's order (the code numbers ascend in both
    # registries), one file each and no other.
    used = sorted(set(expected_zones(tags, system)), key=int)
    expected = [f"pts_{suffix}_{zone_by_code(code).abbrev}.csv" for code in used]
    expected += [f"pts_{suffix}_full.csv", f"pts_{suffix}_README.txt"]
    assert list(members_of(archive)) == expected


def test_the_member_names_are_spelled_as_the_owner_will_see_them(tmp_path):
    """Literal, so a change to the naming scheme is a conscious one."""
    _, archive = auto_job(tmp_path, TAGS_83, "SPCS 83", NAD83_2011)
    assert list(members_of(archive)) == [
        "pts_AUTO-SPCS83_MI-N.csv",
        "pts_AUTO-SPCS83_MI-C.csv",
        "pts_AUTO-SPCS83_MI-S.csv",
        "pts_AUTO-SPCS83_full.csv",
        "pts_AUTO-SPCS83_README.txt",
    ]


@pytest.mark.parametrize("tags, system, frame, suffix", SYSTEMS)
def test_each_clean_file_is_the_fixed_zone_jobs_lines_for_ncats_points(
    tmp_path, tags, system, frame, suffix
):
    """Each zone's file is byte for byte the fixed-zone job's clean file of
    that zone over the same input, restricted to the points NCAT puts in the
    zone, in file order. A point in the wrong file, a point missing, a file
    for an unused zone, or a coordinate from another zone all fail here."""
    result, archive = auto_job(tmp_path, tags, system, frame)
    files = members_of(archive)
    zones = expected_zones(tags, system)
    for code in sorted(set(zones), key=int):
        zone = zone_by_code(code)
        fixed_dir = tmp_path / f"fixed_{code}"
        fixed_dir.mkdir()
        fixed = run(
            dataclasses.replace(
                result.settings, target_zone=zone, auto_frame=None, output_directory=fixed_dir
            )
        )
        fixed_files = members_of(exports.write_all(fixed)["archive"])
        fixed_lines = fixed_files[f"pts_{zone.abbrev}.csv"].split("\r\n")
        wanted_ids = {str(i + 1) for i, z in enumerate(zones) if z == code}
        expected = [line for line in fixed_lines if line.split(",")[0] in wanted_ids]
        assert len(expected) == len(wanted_ids)
        auto_text = files[f"pts_{suffix}_{zone.abbrev}.csv"]
        assert auto_text == "\r\n".join(expected) + "\r\n"


@pytest.mark.parametrize("tags, system, frame, suffix", SYSTEMS)
def test_a_single_zone_auto_job_writes_one_clean_file(tmp_path, tags, system, frame, suffix):
    one = (tags[0], tags[3]) if system == "SPCS 83" else (tags[0],)
    zones = set(expected_zones(one, system))
    assert len(zones) == 1
    result, archive = auto_job(tmp_path, one, system, frame)
    (code,) = zones
    abbrev = zone_by_code(code).abbrev
    assert list(members_of(archive)) == [
        f"pts_{suffix}_{abbrev}.csv",
        f"pts_{suffix}_full.csv",
        f"pts_{suffix}_README.txt",
    ]
    record = members_of(archive)[f"pts_{suffix}_README.txt"]
    assert "It contains the three files below, and they are kept together on\n" in record
    assert f"  Zones used                1 of the " in record


@pytest.mark.parametrize("tags, system, frame, suffix", SYSTEMS)
def test_every_member_reads_back(tmp_path, tags, system, frame, suffix):
    result, archive = auto_job(tmp_path, tags, system, frame)
    files = members_of(archive)
    seen = []
    for name, text in files.items():
        if name.endswith(("_full.csv", "_README.txt")):
            continue
        parsed = pnezd.parse_lines(text.splitlines(), path=name)
        seen.extend(row.point_id for row in parsed.rows)
    assert sorted(seen, key=int) == [str(i + 1) for i in range(len(tags))]
    audit = list(csv.reader(io.StringIO(files[f"pts_{suffix}_full.csv"])))
    assert len(audit) == len(tags) + 1
    assert all(len(row) == len(audit[0]) for row in audit)
    record = files[f"pts_{suffix}_README.txt"]
    assert record.rstrip("\n").endswith("  END OF JOB RECORD\n" + "=" * 78)


# --------------------------------------------------------------------------
# 2. No public function renders an Auto job's clean rows across zones
#    (interim gate over Z0-Z2, HIGH 1, at the reviewer's own input).
# --------------------------------------------------------------------------

REVIEWER_INPUT = "1,42.250568,-84.954191,,CALHOUN\r\n2,44.682131,-83.622405,,ALCONA\r\n"


@pytest.fixture
def reviewers_result(tmp_path):
    path = tmp_path / "pts.csv"
    path.write_bytes(REVIEWER_INPUT.encode("ascii"))
    return run(auto_settings(path, NAD83_2011, output_unit=METERS))


def test_clean_rows_of_an_auto_job_need_a_zone(reviewers_result):
    with pytest.raises(WriteError) as caught:
        exports.clean_pnezd_rows(reviewers_result)
    assert str(caught.value) == (
        "This is an Auto zone job: its points are in 2 zone(s) (Michigan "
        "Central (2112), Michigan South (2113)), and each zone's points go in a "
        "clean export of their own. Clean PNEZD rows of an Auto job are "
        "rendered one zone at a time - name the zone - and never across zones, "
        "because one file of northings and eastings from different zones reads "
        "as one zone's file. Nothing was rendered."
    )
    with pytest.raises(WriteError, match="name the zone"):
        exports.clean_points(reviewers_result)


def test_clean_rows_of_an_auto_job_refuse_a_zone_it_did_not_use(reviewers_result):
    with pytest.raises(WriteError) as caught:
        exports.clean_pnezd_rows(reviewers_result, MI_NORTH)
    assert str(caught.value) == (
        "This Auto zone job put no point in Michigan North (2111), so it has no "
        "clean export for that zone. Nothing was rendered."
    )


def test_clean_rows_of_an_auto_job_are_one_zones_points(reviewers_result):
    south = exports.clean_pnezd_rows(reviewers_result, MI_SOUTH)
    central = exports.clean_pnezd_rows(reviewers_result, MI_CENTRAL)
    assert [row[0] for row in south] == ["1"]
    assert [row[0] for row in central] == ["2"]
    assert south[0][4] == "CALHOUN" and central[0][4] == "ALCONA"


def test_a_fixed_zone_job_refuses_a_zone_argument(tmp_path):
    path = tmp_path / "pts.csv"
    path.write_bytes(REVIEWER_INPUT.encode("ascii"))
    result = run(auto_settings(path, NAD83_2011, target_zone=MI_SOUTH, auto_frame=None))
    assert len(exports.clean_pnezd_rows(result)) == 2
    with pytest.raises(WriteError, match="not an Auto zone job"):
        exports.clean_pnezd_rows(result, MI_SOUTH)


def test_the_mixed_rows_never_reach_a_writer(reviewers_result, tmp_path, monkeypatch):
    """Every route from the result to writers.write_csv_rows goes through
    clean_pnezd_rows, and it refuses before returning anything; write_all
    writes one file per zone and never one holding both points."""
    from michspc.fileio import writers

    calls = []
    monkeypatch.setattr(writers, "write_csv_rows", lambda *a, **k: calls.append(a))
    with pytest.raises(WriteError):
        writers.write_csv_rows(tmp_path / "x.csv", exports.clean_pnezd_rows(reviewers_result))
    assert calls == []
    files = members_of(exports.write_all(reviewers_result)["archive"])
    clean = [text for name, text in files.items() if not name.endswith(("_full.csv", "_README.txt"))]
    assert len(clean) == 2
    assert all(len(text.strip().split("\r\n")) == 1 for text in clean)


def test_the_audit_names_each_reviewer_point_by_its_own_zone_and_county(reviewers_result):
    rows = exports.audit_rows(reviewers_result)
    header = rows[0]
    at = header.index("Target zone")
    assert header[at : at + 3] == ["Target zone", "County", "County FIPS"]
    assert [row[at : at + 3] for row in rows[1:]] == [
        ["Michigan South", "Calhoun", "26025"],
        ["Michigan Central", "Alcona", "26001"],
    ]
    assert not any("AUTO" in cell for row in rows for cell in row)


def test_the_round_trip_verifier_needs_the_zone_too(reviewers_result):
    rows = exports.clean_pnezd_rows(reviewers_result, MI_SOUTH)
    exports.verify_round_trip(rows, reviewers_result, MI_SOUTH)
    with pytest.raises(WriteError, match="name the zone"):
        exports.verify_round_trip(rows, reviewers_result)
    with pytest.raises(WriteError) as caught:
        exports.verify_round_trip(rows, reviewers_result, MI_CENTRAL)
    assert "point '2'" in str(caught.value) or "reads point '1'" in str(caught.value)


# --------------------------------------------------------------------------
# 3. The partition: every point in exactly the file of its own zone.
# --------------------------------------------------------------------------


def _members(result):
    return exports.clean_members(result)


def test_the_members_partition_the_job(reviewers_result):
    members = _members(reviewers_result)
    assert [(m.zone, [p.point_id for p in m.points]) for m in members] == [
        (MI_CENTRAL, ["2"]),
        (MI_SOUTH, ["1"]),
    ]
    exports._require_members_partition_the_job(reviewers_result, members)


def test_a_point_in_the_wrong_zones_file_is_refused(reviewers_result):
    central, south = _members(reviewers_result)
    swapped = (
        dataclasses.replace(central, points=south.points),
        dataclasses.replace(south, points=central.points),
    )
    with pytest.raises(WriteError, match="but it is not in that zone"):
        exports._require_members_partition_the_job(reviewers_result, swapped)


def test_a_point_missing_or_doubled_is_refused(reviewers_result):
    central, south = _members(reviewers_result)
    with pytest.raises(WriteError, match="would be written to\nno clean|written to no clean"):
        exports._require_members_partition_the_job(reviewers_result, (central,))
    with pytest.raises(WriteError, match="would be written to both"):
        exports._require_members_partition_the_job(
            reviewers_result, (central, south, dataclasses.replace(south, name="again.csv"))
        )


def test_points_out_of_order_are_refused(tmp_path):
    path = write_input(tmp_path, TAGS_83, "SPCS 83")
    result = run(auto_settings(path, NAD83_2011))
    members = list(_members(result))
    central = [m for m in members if m.zone is MI_CENTRAL][0]
    members[members.index(central)] = dataclasses.replace(
        central, points=tuple(reversed(central.points))
    )
    with pytest.raises(WriteError, match="out of\nthe input file's order|out of the input file's order"):
        exports._require_members_partition_the_job(result, tuple(members))


def test_a_result_whose_assignment_disagrees_with_its_projection_is_refused(reviewers_result):
    first = reviewers_result.points[0]
    wrong = dataclasses.replace(
        first, auto_zone=dataclasses.replace(first.auto_zone, zone=MI_NORTH)
    )
    bad = dataclasses.replace(reviewers_result, points=(wrong, *reviewers_result.points[1:]))
    with pytest.raises(WriteError) as caught:
        exports.clean_members(bad)
    assert str(caught.value) == (
        "Point 1 of this Auto zone job was assigned Michigan North (2111) but "
        "projected into Michigan South (2113). Nothing was written: its "
        "coordinates would be filed under a zone they are not in."
    )


def test_a_point_without_an_assignment_is_refused(reviewers_result):
    first = dataclasses.replace(reviewers_result.points[0], auto_zone=None)
    bad = dataclasses.replace(reviewers_result, points=(first, *reviewers_result.points[1:]))
    with pytest.raises(WriteError, match="carries no zone assignment"):
        exports.write_all(bad)


# --------------------------------------------------------------------------
# 4. The audit CSV.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tags, system, frame, suffix", SYSTEMS)
def test_the_audit_names_ncats_zone_and_the_anchors_county(tmp_path, tags, system, frame, suffix):
    result, archive = auto_job(tmp_path, tags, system, frame)
    audit = list(csv.reader(io.StringIO(members_of(archive)[f"pts_{suffix}_full.csv"])))
    header = audit[0]
    at = header.index("Target zone")
    assert header[at + 1 : at + 3] == ["County", "County FIPS"]
    for row, tag in zip(audit[1:], tags):
        a = anchor(tag, system)
        if tag == "ISLE_ROYALE_LAND":
            county = ("Keweenaw", "26083")  # Isle Royale is Keweenaw County
        else:
            county = county_of(tag)
        assert row[at : at + 3] == [zone_by_code(a.expected).name, *county]


@pytest.mark.parametrize("tags, system, frame, suffix", SYSTEMS)
def test_every_other_audit_cell_is_the_fixed_zone_jobs(tmp_path, tags, system, frame, suffix):
    """Strip the two county cells from an Auto row and it is the fixed-zone
    job's row of the point's zone, cell for cell - except the Warnings cell
    where the fixed job warned OUTSIDE_ZONE_EXTENT, which Auto never does."""
    result, archive = auto_job(tmp_path, tags, system, frame)
    audit = list(csv.reader(io.StringIO(members_of(archive)[f"pts_{suffix}_full.csv"])))
    at = audit[0].index("County")
    stripped = [row[:at] + row[at + 2 :] for row in audit]
    for index, code in enumerate(expected_zones(tags, system)):
        zone = zone_by_code(code)
        fixed = run(dataclasses.replace(result.settings, target_zone=zone, auto_frame=None))
        fixed_rows = exports.audit_rows(fixed)
        assert stripped[0] == fixed_rows[0]
        warnings = fixed_rows[0].index("Warnings")
        fixed_row = list(fixed_rows[index + 1])
        if fixed_row[warnings] == "outside-zone-extent":
            fixed_row[warnings] = ""
        assert stripped[index + 1] == fixed_row


def test_a_fixed_zone_audit_has_no_county_columns(reviewers_result):
    fixed = run(dataclasses.replace(reviewers_result.settings, target_zone=MI_SOUTH, auto_frame=None))
    assert "County" not in exports.audit_rows(fixed)[0]
    assert "County FIPS" not in exports.audit_rows(fixed)[0]


# --------------------------------------------------------------------------
# 5. The record.
# --------------------------------------------------------------------------


def _block(record: str, first: str, stop: str) -> str:
    start = record.index(first)
    return record[start : record.index(stop, start)]


TO_BLOCK_83 = """\
TO: Auto zone - each point in the zone of its county (SPCS 83)
  Reference frame           NAD83(2011)
  Zones used                3 of the 3 SPCS 83 zones Auto chooses among
    Michigan North, zone 2111 (MI-N): 1 point
      in pts_AUTO-SPCS83_MI-N.csv
    Michigan Central, zone 2112 (MI-C): 2 points
      in pts_AUTO-SPCS83_MI-C.csv
    Michigan South, zone 2113 (MI-S): 2 points
      in pts_AUTO-SPCS83_MI-S.csv

Zone rule          Each point is placed in the zone of the Michigan county its
                   NAD83(2011) position lies in. The counties of each zone are
                   those named by MCL 54.231(3)-(5), Act 9 of 1964 as amended
                   by 1988 PA 154 (Imd. Eff. June 14, 1988), captured from
                   legislature.mi.gov 2026-10-22: subsection (3) the north
                   zone, (4) the central zone, (5) the south zone.
County data        US Census TIGER/Line 2025 counties, all 83 of Michigan's,
                   whose lines extend into the Great Lakes, so a position on
                   the water is in a county as a position on land is. Bundled
                   as mi_counties_tiger2025.json, checked against SHA-256
                   53664dd816375b407c5269cabde565fc89d76e0a3f3ed320fb264240b49f33c3
                   when read.
On a line          A position exactly on a county line is placed in the county
                   east of it, or, where the line runs exactly east-west, in
                   the county north of it.
Near a line        A point near a zone line is placed by its county like every
                   other point, with no warning. MCL 54.234 provides that a
                   tract of land defined by a single description and extending
                   from one zone into another may have the positions of all
                   points on its boundaries referred to either zone, and that
                   the zone used shall be named in the description. Each
                   point's zone and county are in the _full.csv export.

"""

TO_BLOCK_2022 = """\
TO: Auto zone - each point in the zone of its county (SPCS2022)
  Reference frame           NATRF2022
  Zones used                7 of the 18 SPCS2022 zones Auto chooses among
    Michigan Thunder Bay, zone 261006 (MI_L35T): 1 point
      in pts_AUTO-SPCS2022_MI_L35T.csv
    Michigan Kalamazoo, zone 261007 (MI_L41Z): 1 point
      in pts_AUTO-SPCS2022_MI_L41Z.csv
    Michigan Grand Rapids, zone 261008 (MI_L45G): 1 point
      in pts_AUTO-SPCS2022_MI_L45G.csv
    Michigan Leelanau, zone 261011 (MI_L61L): 1 point
      in pts_AUTO-SPCS2022_MI_L61L.csv
    Michigan Escanaba, zone 261014 (MI_U21E): 1 point
      in pts_AUTO-SPCS2022_MI_U21E.csv
    Michigan Houghton, zone 261016 (MI_U41H): 1 point
      in pts_AUTO-SPCS2022_MI_U41H.csv
    Michigan Isle Royale, zone 261018 (MI_U61K): 1 point
      in pts_AUTO-SPCS2022_MI_U61K.csv

<ZONE RULE>
Isle Royale        A Keweenaw County position at or north of 47.65 degrees N
                   is placed in Michigan Isle Royale, zone 261018 (MI_U61K);
                   south of it, in Michigan Houghton, zone 261016 (MI_U41H).
                   This is this program's rule. NGS publishes no text stating
                   it; NGS's zone bounds file (zoneBounds.json) gives the two
                   zones a shared bound at 47.65 degrees N.
County data        US Census TIGER/Line 2025 counties, all 83 of Michigan's,
                   whose lines extend into the Great Lakes, so a position on
                   the water is in a county as a position on land is. Bundled
                   as mi_counties_tiger2025.json, checked against SHA-256
                   53664dd816375b407c5269cabde565fc89d76e0a3f3ed320fb264240b49f33c3
                   when read.
On a line          A position exactly on a county line is placed in the county
                   east of it, or, where the line runs exactly east-west, in
                   the county north of it.
Near a line        A point near a zone line is placed by its county like every
                   other point, with no warning. Each point's zone and county
                   are in the _full.csv export.

"""


def test_the_spcs83_to_block_reads_exactly(tmp_path):
    """Hand-written. The zones and counts are NCAT's for the five anchors:
    Alger -> 2111 (1); Alcona, Benzie -> 2112 (2); Calhoun, Allegan -> 2113 (2)."""
    _, archive = auto_job(tmp_path, TAGS_83, "SPCS 83", NAD83_2011)
    record = members_of(archive)["pts_AUTO-SPCS83_README.txt"]
    assert _block(record, "TO: Auto zone", "TO (Auto): ") == TO_BLOCK_83


def test_the_spcs2022_to_block_reads_exactly(tmp_path):
    """Hand-written. Seven anchors, seven zones (NCAT's), one point each."""
    _, archive = auto_job(tmp_path, TAGS_2022, "SPCS2022", NATRF2022)
    record = members_of(archive)["pts_AUTO-SPCS2022_README.txt"]
    block = _block(record, "TO: Auto zone", "TO (Auto): ")
    before, rule, after = TO_BLOCK_2022.partition("<ZONE RULE>\n")
    assert rule
    assert block.startswith(before) and block.endswith(after)
    # The Zone rule paragraph, read as words: hand-written up to the source,
    # which is the table module's own citation of the NGS capture it was
    # measured from (that module's provenance text is pinned with it, in
    # tests/test_autozone_tables.py), quoted whole.
    paragraph = block[len(before) : len(block) - len(after)]
    assert paragraph.startswith("Zone rule          Each point is placed")
    assert " ".join(paragraph.split()) == (
        "Zone rule Each point is placed in the low-distortion zone of the "
        "Michigan county its NATRF2022 position lies in; the statewide zone "
        "260001 is never chosen. NGS publishes no county list for its SPCS2022 "
        "zones. This program measured one from NGS's zone polygons: each zone "
        "is a union of whole Census TIGER counties, except Keweenaw County, "
        "whose Isle Royale is its own zone. Source: "
        + " ".join(NGS_POLYGONS_CITATION.split())
        + "."
    )


@pytest.mark.parametrize("tags, system, frame, suffix", SYSTEMS)
def test_each_used_zone_is_described_and_no_other(tmp_path, tags, system, frame, suffix):
    _, archive = auto_job(tmp_path, tags, system, frame)
    record = members_of(archive)[f"pts_{suffix}_README.txt"]
    described = [line for line in record.split("\n") if line.startswith("TO (Auto): ")]
    used = sorted(set(expected_zones(tags, system)), key=int)
    assert described == [
        f"TO (Auto): {zone_by_code(c).name}, zone {c} ({zone_by_code(c).system})" for c in used
    ]
    # The fixed-zone TO heading never appears.
    assert not [line for line in record.split("\n") if line.startswith("TO: Michigan")]


def test_the_spcs2022_record_is_in_the_spcs2022_era(tmp_path):
    _, archive = auto_job(tmp_path, TAGS_2022, "SPCS2022", NATRF2022)
    record = members_of(archive)["pts_AUTO-SPCS2022_README.txt"]
    assert "Sixty-three positions spanning all nineteen Michigan" in " ".join(record.split())
    # The projections the seven zones use: the L zones are one-parallel
    # Lambert, U41H, U21E and U61K transverse Mercator (NGS's own kinds).
    kinds = {zone_by_code(c).projection_kind for c in expected_zones(TAGS_2022, "SPCS2022")}
    for kind, section in ((k, report._MANUAL_SECTIONS[k]) for k in kinds):
        assert f"section {section}  " in record
    for spcs83_sentence in (
        "Twenty-seven",
        "Appendix C, the constants NGS computed",
        "MCL 54.231",
        "MCL 54.234",
        "GRS 80, the ellipsoid of NAD 83 (manual section 1.7).",
    ):
        assert spcs83_sentence not in record


def test_the_spcs83_record_is_in_the_spcs83_era(tmp_path):
    _, archive = auto_job(tmp_path, TAGS_83, "SPCS 83", NAD83_2011)
    record = members_of(archive)["pts_AUTO-SPCS83_README.txt"]
    assert "Twenty-seven" in record
    for spcs2022_sentence in ("Sixty-three", "NGS publishes no county list", "Isle Royale        "):
        assert spcs2022_sentence not in record


@pytest.mark.parametrize(
    "tags, system, frame, suffix, count",
    [
        pytest.param(TAGS_83, "SPCS 83", NAD83_2011, "AUTO-SPCS83", "five", id="spcs83"),
        pytest.param(TAGS_2022, "SPCS2022", NATRF2022, "AUTO-SPCS2022", "nine", id="spcs2022"),
    ],
)
def test_files_written_lists_every_member(tmp_path, tags, system, frame, suffix, count):
    _, archive = auto_job(tmp_path, tags, system, frame)
    files = members_of(archive)
    record = files[f"pts_{suffix}_README.txt"]
    section = record[record.index("FILES WRITTEN") :]
    assert f"This job wrote ONE file: pts_{suffix}.zip\n" in section
    assert f"It contains the {count} files below, and they are kept together on\n" in section
    listed = [line[2:] for line in section.split("\n") if line.startswith(f"  pts_{suffix}_")]
    assert listed == list(files)
    clean = len(files) - 2
    assert f"One clean export for each zone this job used ({clean})," in section


def test_each_clean_file_is_described_with_its_own_zone_and_count(tmp_path):
    _, archive = auto_job(tmp_path, TAGS_83, "SPCS 83", NAD83_2011)
    record = members_of(archive)["pts_AUTO-SPCS83_README.txt"]
    flat = " ".join(record.split())
    assert (
        "pts_AUTO-SPCS83_MI-N.csv The 1 point placed in Michigan North, zone 2111 "
        "(MI-N): its converted coordinates in that zone"
    ) in flat
    assert (
        "pts_AUTO-SPCS83_MI-C.csv The 2 points placed in Michigan Central, zone "
        "2112 (MI-C), in input file order: their converted coordinates"
    ) in flat
    assert "Import it into CAD as Michigan South (2113) coordinates." in flat


FALSE_ON_AUTO = (
    # Each sentence below names one zone, one target, a zone-to-zone move or
    # the fixed-zone file count; each is false on an Auto job.
    "Both zones are on the same reference frame",
    "moved between zones",
    "both zones' coordinates",
    "both convergence angles",
    "It contains the three files below" + "\n" + "purpose. A coordinate file",
    "Extract this one and import it into CAD",
    "AUTO_ZONE",
    "AutoZone",
    "TO: Michigan",
    "OUTSIDE THE TARGET ZONE",
)


def _sweep_jobs():
    for tags, system, frame in (
        (TAGS_83, "SPCS 83", NAD83_2011),
        (TAGS_2022, "SPCS2022", NATRF2022),
    ):
        yield f"{system}-mixed", tags, system, frame, {}
        yield f"{system}-single", tags[:1], system, frame, {}
    for tags in (TAGS_83, TAGS_83[:1]):
        yield (
            f"wgs84-{len(tags)}",
            tags,
            "SPCS 83",
            NAD83_2011,
            dict(geodetic_frame=WGS84_G2296, observation_date=datetime.date(2025, 6, 15)),
        )
    yield "hv", TAGS_83, "SPCS 83", NAD83_2011, dict(
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    yield "ellipsoid", TAGS_83, "SPCS 83", NAD83_2011, dict(
        input_height_kind=HeightKind.ELLIPSOID
    )
    yield "no-geoid", TAGS_2022, "SPCS2022", NATRF2022, dict(geoid_model=None)
    yield "itrf-hv-ellipsoid", TAGS_83, "SPCS 83", NAD83_2011, dict(
        geodetic_frame=ITRF2020,
        observation_date=datetime.date(2024, 1, 1),
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
        input_height_kind=HeightKind.ELLIPSOID,
    )


@pytest.mark.parametrize("label, tags, system, frame, fields", list(_sweep_jobs()), ids=lambda v: v if isinstance(v, str) and "-" in v or v in ("hv", "ellipsoid") else "")
def test_no_one_zone_sentence_survives_on_an_auto_job(tmp_path, label, tags, system, frame, fields):
    fields = dict(fields)
    geodetic = fields.pop("geodetic_frame", frame)
    path = write_input(tmp_path, tags, system)
    result = run(auto_settings(path, frame, geodetic_frame=geodetic, **fields))
    files = members_of(exports.write_all(result)["archive"])
    (record,) = [text for name, text in files.items() if name.endswith("_README.txt")]
    flat = " ".join(record.split())
    for sentence in FALSE_ON_AUTO:
        assert " ".join(sentence.split()) not in flat, (label, sentence)
    assert "TO: Auto zone - each point in the zone of its county" in record
    if geodetic is not frame:
        assert f"Position tested    Each point's {frame.code} position, as the frame" in record
        assert "FRAME TRANSFORMATION" in record
    else:
        assert "Position tested" not in record
    # Every clean file's points are the job's points, each once.
    seen = []
    for name, text in files.items():
        if not name.endswith(("_full.csv", "_README.txt")):
            seen.extend(line.split(",")[0] for line in text.strip().split("\r\n"))
    assert sorted(seen, key=int) == [str(i + 1) for i in range(len(tags))]


def test_the_auto_scale_factor_sentence(tmp_path):
    _, archive = auto_job(tmp_path, TAGS_83, "SPCS 83", NAD83_2011)
    record = members_of(archive)["pts_AUTO-SPCS83_README.txt"]
    assert (
        "Each point's grid scale factor and convergence are those of its own "
        "zone, named in its row's Target zone cell of the _full.csv export. The "
        "summary below is across all 5 point(s), in the 3 zones this job used."
    ) in " ".join(record.split())


def test_a_wgs84_auto_job_writes_the_fixed_zone_jobs_lines(tmp_path):
    """WGS 84 in, Auto on NAD83(2011): the zone is chosen at the pivot, and
    each clean file is the fixed-zone WGS 84 job's lines for its points."""
    path = write_input(tmp_path, TAGS_83, "SPCS 83")
    settings = auto_settings(
        path, NAD83_2011, geodetic_frame=WGS84_G2296, observation_date=datetime.date(2025, 6, 15)
    )
    result = run(settings)
    files = members_of(exports.write_all(result)["archive"])
    for zone in (MI_NORTH, MI_CENTRAL, MI_SOUTH):
        out = tmp_path / zone.abbrev
        out.mkdir()
        fixed = run(dataclasses.replace(settings, target_zone=zone, auto_frame=None, output_directory=out))
        fixed_lines = members_of(exports.write_all(fixed)["archive"])[f"pts_{zone.abbrev}.csv"].split("\r\n")
        ids = {p.point_id for p in result.points if p.auto_zone.zone is zone}
        expected = [line for line in fixed_lines if line.split(",")[0] in ids]
        assert files[f"pts_AUTO-SPCS83_{zone.abbrev}.csv"] == "\r\n".join(expected) + "\r\n"
    audit = list(csv.reader(io.StringIO(files["pts_AUTO-SPCS83_full.csv"])))
    assert audit[0][-1].startswith("Velocity up")
    assert audit[0].index("County") == audit[0].index("Target zone") + 1


# --------------------------------------------------------------------------
# 6. The observation date source (L10, O3).
# --------------------------------------------------------------------------

LOCAL = datetime.date(2026, 10, 21)


@pytest.fixture
def local_day(monkeypatch):
    monkeypatch.setattr(job, "_local_and_utc_dates", lambda: (LOCAL, LOCAL))


def _dated_record(tmp_path, source, auto=False):
    out = tmp_path / f"{source}-{auto}"
    out.mkdir()
    path = write_input(out, TAGS_83[:2], "SPCS 83")
    fields = dict(
        geodetic_frame=WGS84_G2296,
        observation_date=LOCAL,
        observation_date_source=source,
    )
    if not auto:
        fields.update(target_zone=MI_SOUTH, auto_frame=None)
    result = run(auto_settings(path, NAD83_2011, **fields))
    files = members_of(exports.write_all(result)["archive"])
    (record,) = [t for n, t in files.items() if n.endswith("_README.txt")]
    (audit,) = [t for n, t in files.items() if n.endswith("_full.csv")]
    return record.split("\n", 6)[6].replace(str(out), "<ROOT>"), audit


@pytest.mark.parametrize("auto", [False, True], ids=["fixed", "auto"])
def test_the_observation_date_says_where_it_came_from(tmp_path, local_day, auto):
    none, none_audit = _dated_record(tmp_path, None, auto)
    today, today_audit = _dated_record(tmp_path, ObservationDateSource.TODAY, auto)
    entered, entered_audit = _dated_record(tmp_path, ObservationDateSource.ENTERED, auto)
    assert "Observation date   2026-10-21, decimal year" in none
    assert (
        "Observation date   2026-10-21, the date the job ran (Options default), decimal"
        in today
    )
    assert "Observation date   2026-10-21, entered by the user, decimal year" in entered
    assert "the date the job ran" not in entered
    assert "entered by the user" not in today
    # Nothing else moves: the words are the only difference.
    flat = lambda text: " ".join(text.split())
    assert flat(today).replace(" the date the job ran (Options default),", "") == flat(none)
    assert flat(entered).replace(" entered by the user,", "") == flat(none)
    assert none_audit == today_audit == entered_audit
