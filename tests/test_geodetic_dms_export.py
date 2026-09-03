"""The DMS sibling of the clean export on a job converting TO geodetic
(docs/DESIGN.md amendment #67, the owner's instruction).

* ``<stem>_GEODETIC_DD.csv`` is the clean export, byte-identical to what it
  was under its old name; ``<stem>_GEODETIC_DMS.csv`` is the same rows with
  the position in degrees, minutes, seconds and a letter.
* Only that direction writes it; every other direction's archive is unchanged.
* The DMS file reads the same under both longitude conventions.
* It cannot be fed back in as an input file: the reader refuses it by name.
* The job record names it and says what it is not for.
"""

from __future__ import annotations

import csv
import io
import zipfile

import pytest

from michspc.fileio import dms, exports, pnezd
from michspc.fileio import formatting as fmt
from michspc.fileio.writers import WriteError
from michspc.job import Direction, JobSettings, LongitudeConvention, run
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.zones import MI_CENTRAL, MI_SOUTH
from tests import test_orthometric_regression as regression
from tests.conftest import member_text

ROWS = (
    "101,449212.689,13072628.343,900.000,IRON PIPE\n"
    "102,449300.000,13072700.000,,BLANK Z\n"
)


def _job(tmp_path, convention=LongitudeConvention.NEGATIVE_WEST, **overrides):
    source = tmp_path / "job.csv"
    source.write_text(ROWS, encoding="utf-8")
    settings = dict(
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        input_path=source,
        output_directory=tmp_path,
        longitude_convention=convention,
    )
    settings.update(overrides)
    return run(JobSettings(**settings))


def _members(archive) -> dict[str, str]:
    with zipfile.ZipFile(archive) as opened:
        return {name: opened.read(name).decode("utf-8") for name in opened.namelist()}


def _rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text, newline="")))


# ---------------------------------------------------------------------------
# Names and membership
# ---------------------------------------------------------------------------


def test_converting_to_geodetic_writes_dd_and_dms_and_names_them(tmp_path):
    result = _job(tmp_path)
    written = exports.write_all(result)
    names = exports.member_names(result)
    assert names["pnezd"] == "job_GEODETIC_DD.csv"
    assert names["pnezd_dms"] == "job_GEODETIC_DMS.csv"
    assert names["audit"] == "job_GEODETIC_full.csv"
    assert names["report"] == "job_GEODETIC_README.txt"
    assert written["archive"].name == "job_GEODETIC.zip"
    assert set(written) == {"archive", "pnezd", "pnezd_dms", "audit", "report"}
    members = _members(written["archive"])
    assert list(members) == [
        "job_GEODETIC_DD.csv",
        "job_GEODETIC_DMS.csv",
        "job_GEODETIC_full.csv",
        "job_GEODETIC_README.txt",
    ]


def test_every_other_direction_is_unchanged_by_name_and_count(tmp_path):
    for name, configuration in regression._configurations():
        if configuration["direction"] is Direction.ZONE_TO_GEODETIC:
            continue
        folder = tmp_path / name
        folder.mkdir()
        source = folder / "in.csv"
        source.write_text(regression.ROWS, encoding="utf-8")
        settings = dict(
            input_path=source,
            output_directory=folder,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        )
        settings.update(configuration)
        if configuration["direction"] is Direction.VERTICAL_ONLY:
            settings["longitude_convention"] = None
        result = run(JobSettings(**settings))
        names = exports.member_names(result)
        assert "pnezd_dms" not in names
        assert not names["pnezd"].endswith("_DD.csv")
        assert not exports.writes_dms_export(result)
        written = exports.write_all(result)
        assert len(_members(written["archive"])) == 3
        with pytest.raises(WriteError, match="only when the job converts TO geodetic"):
            exports.clean_pnezd_dms_rows(result)


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("output_unit", [INTERNATIONAL_FEET, METERS])
def test_the_dms_file_is_the_dd_file_with_the_position_restated(tmp_path, output_unit):
    result = _job(tmp_path, output_unit=output_unit)
    written = exports.write_all(result)
    members = _members(written["archive"])
    dd = _rows(members["job_GEODETIC_DD.csv"])
    dms_rows = _rows(members["job_GEODETIC_DMS.csv"])
    assert len(dd) == len(dms_rows) == 2
    for dd_row, dms_row in zip(dd, dms_rows):
        assert dms_row[0] == dd_row[0]
        assert dms_row[3] == dd_row[3]
        assert dms_row[4] == dd_row[4]
        # The DMS cell, read by the Single point tab's own parser, is the
        # DD cell's angle to within half of the DMS cell's last place.
        for index, axis in ((1, dms.LATITUDE), (2, dms.LONGITUDE)):
            angle, letter = dms_row[index].split(" ")
            parts = angle.split("-") + [letter]
            assert len(parts) == 4
            assert parts[3] in ("N", "W")
            assert abs(
                dms.decimal_degrees(*parts, axis=axis) - float(dd_row[index])
            ) <= 0.5e-5 / 3600.0 + 0.5e-8
    # And the first row at the hand-derived anchor this suite has used since
    # 0.1.0: 449212.689 / 13072628.343 ift in MI-S is 42.7325, -84.5555.
    assert dd[0][1:3] == ["42.73250000", "-84.55550000"]
    assert dms_rows[0][1:3] == ["42-43-57.00000 N", "84-33-19.80000 W"]
    # 900.000 ift out as ift; 900 x 0.3048 = 274.32 m exactly, 4 dp in metres:
    # the DMS file carries the OUTPUT elevation, like the DD file.
    elevation = "900.000" if output_unit is INTERNATIONAL_FEET else "274.3200"
    assert dms_rows[0] == ["101", "42-43-57.00000 N", "84-33-19.80000 W", elevation, "IRON PIPE"]
    assert dms_rows[1][3] == "N/A"


def test_the_dms_file_reads_the_same_under_both_longitude_conventions(tmp_path):
    for folder in ("neg", "pos"):
        (tmp_path / folder).mkdir()
    negative = _job(tmp_path / "neg", convention=LongitudeConvention.NEGATIVE_WEST)
    positive = _job(tmp_path / "pos", convention=LongitudeConvention.POSITIVE_WEST)
    dd_negative = exports.clean_pnezd_rows(negative)
    dd_positive = exports.clean_pnezd_rows(positive)
    # The decimal files differ - the sign is the convention - ...
    assert dd_negative[0][2] == "-84.55550000"
    assert dd_positive[0][2] == "84.55550000"
    # ... and the DMS files are identical: W is a fact about the point.
    assert exports.clean_pnezd_dms_rows(negative) == exports.clean_pnezd_dms_rows(positive)
    assert exports.clean_pnezd_dms_rows(positive)[0][2] == "84-33-19.80000 W"


def test_the_dms_file_matches_the_audit_csv_and_the_panel_for_the_same_point(tmp_path):
    result = _job(tmp_path)
    audit = exports.audit_rows(result)
    header = audit[0]
    for dms_row, audit_row, point in zip(
        exports.clean_pnezd_dms_rows(result), audit[1:], result.points
    ):
        assert dms_row[1] == audit_row[header.index("Latitude (DMS)")]
        assert dms_row[2] == audit_row[header.index("Longitude (DMS)")]
        degrees, minutes, seconds, letter = (
            fmt.latitude_dms(point.conversion.latitude)
            .replace("°", " ").replace("'", " ").replace('"', " ").split()
        )
        assert dms_row[1] == f"{degrees}-{minutes}-{seconds} {letter}"


# ---------------------------------------------------------------------------
# The reader refuses it; the verifier refuses a wrong one
# ---------------------------------------------------------------------------


def test_the_dms_file_cannot_be_read_back_as_an_input_file(tmp_path):
    result = _job(tmp_path)
    written = exports.write_all(result)
    text = member_text(written["archive"], "GEODETIC_DMS.csv")
    with pytest.raises(pnezd.PnezdError, match="DMS"):
        pnezd.parse_lines(text.splitlines(), path="job_GEODETIC_DMS.csv")


def test_the_dms_round_trip_refuses_a_wrong_cell(tmp_path):
    result = _job(tmp_path)
    rows = exports.clean_pnezd_dms_rows(result)
    for index, bad, reason in (
        (1, "42-43-57.00000 S", "reads back as"),
        (2, "84-33-19.80000 E", "reads back as"),
        (1, "42-44-57.00000 N", "reads back as"),
        (1, "42-43-57.0001 N", "reads back as"),
        (1, "42°43'57.00000\"N", "does not read back as an angle"),
        (1, "42 43 57.00000 N", "does not read back as an angle"),
        (3, "900.001", "elevation"),
        (0, "999", "point"),
    ):
        seeded = [list(row) for row in rows]
        seeded[0][index] = bad
        with pytest.raises(WriteError, match=reason):
            exports.verify_dms_round_trip(seeded, result)
    with pytest.raises(WriteError, match="rows for"):
        exports.verify_dms_round_trip(rows[:1], result)
    exports.verify_dms_round_trip(rows, result)  # the real rows pass


def test_a_dms_verification_failure_writes_nothing(tmp_path, monkeypatch):
    result = _job(tmp_path)

    original = exports.clean_pnezd_dms_rows

    def corrupted(result):
        rows = original(result)
        rows[0][1] = "42-43-57.00000 S"
        return rows

    monkeypatch.setattr(exports, "clean_pnezd_dms_rows", corrupted)
    with pytest.raises(WriteError, match="Nothing was written"):
        exports.write_all(result)
    assert list(tmp_path.glob("*.zip")) == []


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def test_the_record_names_four_files_and_says_what_the_dms_file_is_not_for(tmp_path):
    result = _job(tmp_path)
    written = exports.write_all(result)
    text = member_text(written["archive"], "_README.txt")
    block = text[text.index("FILES WRITTEN") : text.index("END OF JOB RECORD")]
    assert "It contains the four files below" in block
    assert "rather than four loose files" in block
    assert "  job_GEODETIC_DD.csv" in block
    assert "  job_GEODETIC_DMS.csv" in block
    assert block.index("job_GEODETIC_DD.csv") < block.index("job_GEODETIC_DMS.csv") < block.index("job_GEODETIC_full.csv")
    assert "DEGREES MINUTES SECONDS" in block
    assert "NOT for CAD import" in block
    assert "42-43-57.00000 N   84-33-19.80000 W" in block


def test_a_zone_to_zone_record_still_says_three(tmp_path):
    source = tmp_path / "job.csv"
    source.write_text(ROWS, encoding="utf-8")
    result = run(JobSettings(
        direction=Direction.ZONE_TO_ZONE, source_zone=MI_SOUTH, target_zone=MI_CENTRAL,
        input_unit=METERS, output_unit=METERS, input_path=source,
        output_directory=tmp_path, longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    ))
    written = exports.write_all(result)
    text = member_text(written["archive"], "_README.txt")
    assert "It contains the three files below" in text
    assert "rather than three loose files" in text
    assert "DMS" not in text[text.index("FILES WRITTEN"):]
