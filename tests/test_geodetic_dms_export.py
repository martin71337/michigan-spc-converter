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
    for dd_row, dms_row, point in zip(dd, dms_rows, result.points):
        assert dms_row[0] == dd_row[0]
        assert dms_row[3] == dd_row[3]
        assert dms_row[4] == dd_row[4]
        # Both files are the job's pivot, each in its own notation, compared
        # as text and never within a tolerance (the gate's MEDIUM 1); and the
        # DMS cell, read by the Single point tab's own parser, renders back
        # to itself. Not compared to each other through a float: the DD cell
        # holds 8 decimals of a degree (3.6e-5 s), COARSER than the DMS
        # cell's 1e-5 s, so the DMS file is the more precise of the two.
        conversion = point.conversion
        for index, axis, render, decimal, pivot in (
            (1, dms.LATITUDE, fmt.latitude_dms_fields, fmt.latitude, conversion.latitude),
            (2, dms.LONGITUDE, fmt.longitude_dms_fields, fmt.longitude, conversion.longitude),
        ):
            assert dd_row[index] == decimal(pivot)
            assert dms_row[index] == render(pivot)
            angle, letter = dms_row[index].split(" ")
            parts = angle.split("-") + [letter]
            assert len(parts) == 4
            assert parts[3] in ("N", "W")
            parsed = dms.decimal_degrees(*parts, axis=axis)
            assert render(parsed) == dms_row[index]
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


HALF_WAY_ROWS = (
    "101,381151.542,12817687.128,900.000,LAT TRIPS\n"
    "102,436327.645,13471551.953,900.000,LON TRIPS\n"
)
"""Two MI-S ift points whose converted position falls on the rounding
half-way point of the DMS cell's last place: the 0.7.1 closing gate's
counterexample (MEDIUM 1). Parsing the correctly rounded cell back lands a
few parts in 1e15 PAST half a place from the pivot, so the first cut's
tolerance refused the whole archive; the comparison is now text."""


def test_a_position_on_the_rounding_half_way_point_writes(tmp_path):
    """The gate's counterexample, end to end: the archive is written and the
    DMS cells are the correctly rounded ones. The anti-vacuity half proves
    the anchor still discriminates: the parsed cell really does sit past
    half a place from the pivot, which is what the tolerance form refused -
    and inside the one-full-place bound the verifier now keeps."""
    result = _half_way_job(tmp_path)
    half_place = 0.5e-5 / 3600.0
    dms_rows = exports.clean_pnezd_dms_rows(result)
    for row_index, index, axis, expected in (
        (0, 1, dms.LATITUDE, "42-32-24.87132 N"),
        (1, 2, dms.LONGITUDE, "83-04-17.22885 W"),
    ):
        cell = dms_rows[row_index][index]
        assert cell == expected
        angle, letter = cell.split(" ")
        parsed = dms.decimal_degrees(*(angle.split("-") + [letter]), axis=axis)
        conversion = result.points[row_index].conversion
        pivot = conversion.latitude if axis is dms.LATITUDE else conversion.longitude
        assert abs(parsed - pivot) > half_place, "the anchor no longer discriminates"
    written = exports.write_all(result)
    rows = _rows(_members(written["archive"])["job_GEODETIC_DMS.csv"])
    assert rows[0][1] == "42-32-24.87132 N"
    assert rows[1][2] == "83-04-17.22885 W"


def _half_way_job(tmp_path):
    source = tmp_path / "job.csv"
    source.write_text(HALF_WAY_ROWS, encoding="utf-8")
    return run(JobSettings(
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        input_path=source,
        output_directory=tmp_path,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    ))


REAL_LATITUDE_DMS_FIELDS = fmt.latitude_dms_fields


@pytest.mark.parametrize(
    "defect, wrong_cell",
    [
        ("a constant", lambda value, seconds_decimals=5: "42-00-00.00000 N"),
        ("four places", lambda value, seconds_decimals=5: REAL_LATITUDE_DMS_FIELDS(value, 4)),
    ],
)
def test_the_dms_verifier_catches_a_formatter_that_is_its_own_fixed_point(
    tmp_path, monkeypatch, defect, wrong_cell
):
    """The re-confirmation's LOW 7: the cell and the expectation come from
    one formatter call, so a formatter returning a constant, or four places
    instead of five, passed the text check AND the parse-and-render fixed
    point. The one-full-place bound against the pivot is what refuses them.
    On the half-way rows: the constant is 0.7 degrees out, and four places
    leave the latitude 2e-5 s from the pivot, twice the bound."""
    result = _half_way_job(tmp_path)
    monkeypatch.setattr(fmt, "latitude_dms_fields", wrong_cell)
    rows = exports.clean_pnezd_dms_rows(result)
    assert rows[0][1] == wrong_cell(result.points[0].conversion.latitude)
    with pytest.raises(WriteError, match="reads back as"):
        exports.verify_dms_round_trip(rows, result)
    with pytest.raises(WriteError, match="Nothing was written"):
        exports.write_all(result)
    assert list(tmp_path.glob("*.zip")) == [], defect


def test_the_dms_verifier_joins_the_dd_file_to_the_same_position(tmp_path, monkeypatch):
    """A DD file whose latitude is 1.7 degrees wrong, with the DMS rows
    untouched, passed the first cut (the gate's LOW 1): each file was checked
    against the job and neither against the other. Now the DD cells must be
    the pivot's own rendering, and a wrong one refuses with nothing written."""
    result = _job(tmp_path)
    rows = exports.clean_pnezd_dms_rows(result)
    original = exports.clean_pnezd_rows

    def wrong_dd(result):
        dd = original(result)
        dd[0][1] = "41.00000000"
        return dd

    monkeypatch.setattr(exports, "clean_pnezd_rows", wrong_dd)
    with pytest.raises(WriteError, match="decimal export's latitude reads '41.00000000'"):
        exports.verify_dms_round_trip(rows, result)
    with pytest.raises(WriteError, match="Nothing was written"):
        exports.write_all(result)
    assert list(tmp_path.glob("*.zip")) == []


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
