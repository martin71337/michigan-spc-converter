"""The audit CSV's ``Latitude (DMS)`` and ``Longitude (DMS)`` columns
(docs/DESIGN.md amendment #66, the owner's instruction).

Three properties, each pinned against something other than the code that
produces it:

* the cell text is the owner's DMS - degrees, minutes, seconds to five places,
  a hemisphere letter - in the file notation, at hand-derived values;
* the Multi point audit CSV and the Single point panel state the SAME
  degrees, minutes, seconds and letter for the same point, differing only in
  punctuation - the two tabs cannot disagree about a position;
* the pair sits directly after ``Longitude (neg west)`` in every direction and
  mode, and is N/A exactly where the decimal pivot beside it is N/A.
"""

from __future__ import annotations

import csv
import io
import zipfile

import pytest

from michspc.fileio import exports
from michspc.fileio import formatting as fmt
from michspc.job import JobSettings, run
from tests import test_orthometric_regression as regression


# ---------------------------------------------------------------------------
# The formatters, at hand-derived values
# ---------------------------------------------------------------------------


def test_latitude_dms_fields_is_the_owners_dms_in_file_notation():
    # 42.7325: 0.7325 deg * 60 = 43.95 min -> 43', 0.95 * 60 = 57.00000".
    # The panel pins the same value as 42°43'57.00000"N (test_fileio).
    assert fmt.latitude_dms_fields(42.7325) == "42-43-57.00000 N"
    # 0.5555 deg * 60 = 33.33 min -> 33', 0.33*60 = 19.8 s.
    assert fmt.longitude_dms_fields(-84.5555) == "84-33-19.80000 W"


def test_dms_fields_carry_a_letter_and_never_a_sign():
    assert fmt.latitude_dms_fields(-42.7325) == "42-43-57.00000 S"
    assert fmt.longitude_dms_fields(84.5555) == "84-33-19.80000 E"
    assert fmt.latitude_dms_fields(0.0) == "00-00-00.00000 N"
    for text in (
        fmt.latitude_dms_fields(-42.7325),
        fmt.longitude_dms_fields(-84.5555),
    ):
        # No leading sign: the dashes are the field separators (#67), two of
        # them, and the letter is the only other field.
        assert not text.startswith("-")
        assert "°" not in text and "'" not in text and '"' not in text
        assert text.count("-") == 2 and text.count(" ") == 1
        assert text[-1] in "SW"


def test_dms_fields_are_not_available_without_a_value():
    assert fmt.latitude_dms_fields(None) == fmt.NOT_AVAILABLE
    assert fmt.longitude_dms_fields(None) == fmt.NOT_AVAILABLE


def test_dms_fields_carry_the_seconds_once_rounded_like_the_panel():
    # 59.999996 s rounds to 60.00000 at five places, and must carry: the
    # panel's ``latitude_dms`` prints 42°44'00.00000"N for this value.
    value = 42.0 + 43.0 / 60.0 + 59.999996 / 3600.0
    assert fmt.latitude_dms(value) == "42°44'00.00000\"N"
    assert fmt.latitude_dms_fields(value) == "42-44-00.00000 N"


# ---------------------------------------------------------------------------
# One job, both surfaces
# ---------------------------------------------------------------------------


def _punctuation_free(text: str) -> str:
    """``42°43'57.00000"N`` -> ``42-43-57.00000 N``: the panel's string with
    its symbols read as separators, so a comparison against the file's cell
    tests the digits and the letter and nothing else."""
    degrees, minutes, seconds, letter = (
        text.replace("°", " ").replace("'", " ").replace('"', " ").split()
    )
    return f"{degrees}-{minutes}-{seconds} {letter}"


def _audit_table(tmp_path, name: str):
    """``(rows, result)``: the audit CSV a regression configuration writes,
    parsed by heading, beside the result it was written from."""
    configuration = dict(regression._configurations())[name]
    folder = tmp_path / name
    folder.mkdir()
    source = folder / "in.csv"
    source.write_text(regression.ROWS, encoding="utf-8")
    settings = dict(
        input_path=source,
        output_directory=folder,
        longitude_convention=regression.LongitudeConvention.NEGATIVE_WEST,
    )
    settings.update(configuration)
    if configuration.get("direction") is regression.Direction.VERTICAL_ONLY:
        settings["longitude_convention"] = None
    result = run(JobSettings(**settings))
    written = exports.write_all(result, overwrite=True)
    with zipfile.ZipFile(written["archive"]) as archive:
        member = next(n for n in archive.namelist() if n.endswith("_full.csv"))
        text = archive.read(member).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text, newline="")))
    assert len(rows) == 3
    return rows, result


@pytest.mark.parametrize("name", [n for n, _ in regression._configurations()])
def test_the_audit_csv_and_the_single_point_panel_state_the_same_dms(tmp_path, name):
    rows, result = _audit_table(tmp_path, name)
    for row, point in zip(rows, result.points):
        conversion = point.conversion
        assert row["Latitude (DMS)"] == _punctuation_free(
            fmt.latitude_dms(conversion.latitude)
        )
        assert row["Longitude (DMS)"] == _punctuation_free(
            fmt.longitude_dms(conversion.longitude)
        )
        # The decimal pivot beside it is the same number, to the precision the
        # decimal column prints (1e-8 deg is 3.6e-5 arcsecond, below the
        # DMS cell's last place, so the two agree to within one unit there).
        assert (row["Latitude"] == "N/A") == (row["Latitude (DMS)"] == "N/A")
        if row["Latitude"] != "N/A":
            assert row["Latitude (DMS)"].endswith(" N")
            assert row["Longitude (DMS)"].endswith(" W")
            assert int(row["Latitude (DMS)"].split("-")[0]) == int(
                float(row["Latitude"])
            )
            assert int(row["Longitude (DMS)"].split("-")[0]) == int(
                abs(float(row["Longitude (neg west)"]))
            )


@pytest.mark.parametrize("name", [n for n, _ in regression._configurations()])
def test_the_dms_pair_sits_directly_after_the_decimal_longitude(tmp_path, name):
    rows, result = _audit_table(tmp_path, name)
    header = exports.audit_columns(result)
    at = header.index("Longitude (neg west)")
    assert header[at + 1 : at + 3] == ["Latitude (DMS)", "Longitude (DMS)"]
    assert header[at - 1] == "Latitude"
    # ...and the cells land under those headings: the DictReader above keyed
    # every cell by its heading, and the parametrised test before this one
    # found the DMS text there. Here, the row's width is the header's.
    for line in exports.audit_rows(result):
        assert len(line) == len(header)


def test_the_dms_columns_are_in_the_base_header_once_each():
    assert exports.AUDIT_COLUMNS.count("Latitude (DMS)") == 1
    assert exports.AUDIT_COLUMNS.count("Longitude (DMS)") == 1
