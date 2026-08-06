"""The file layer: PNEZD reading, formatting, atomic writing, exports, report.

Everything asserted here is hand-derived in the comment immediately above the
assertion - from the format specification in the module docstrings, from the
unit definitions in michspc/spc/units.py, or from arithmetic shown in full.
Nothing was read back from the program's own output.

The three end-to-end tests at the bottom assert *properties* (identity of a
round trip, survival of text through an export) rather than coordinate values,
because a coordinate value that this program computed is not evidence about
this program. The coordinate anchors live in test_lambert.py and
test_convert.py against NGS's own published numbers.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import hashlib
import math
from pathlib import Path

import pytest

from tests.conftest import archive_members, extract_member, member_text

from michspc import job as jobmod
from michspc.fileio import exports, pnezd, report
from michspc.fileio import formatting as fmt
from michspc.fileio.writers import WriteError, atomic_write_text, write_csv_rows
from michspc.job import (
    Direction,
    JobSettings,
    LongitudeConvention,
    file_sha256,
    run,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS, US_SURVEY_FEET
from michspc.spc.zones import MI_CENTRAL, MI_SOUTH

# --------------------------------------------------------------------------
# Shared fixtures. Coordinates are chosen, not computed: every northing sits
# about 237,700-240,100 m north of Michigan South's grid origin at 41 deg 30',
# which is roughly 2.14 degrees of latitude, so every point lands near 43.65 N.
# That is inside Michigan South's extent (41.6-44.3) and fitted band
# (41.45-44.25) AND inside Michigan Central's extent (43.5-46.0) and fitted
# band (43.30-46.05), so a South->Central conversion of these points exercises
# both engines fully rather than tripping the out-of-band warning path.
#
# Eastings sit within 40 km of Michigan South's 4,000,000 m false easting
# (13,123,359.58 international feet), well inside the 400 km window
# easting_looks_wrong_for_zone uses.
# --------------------------------------------------------------------------

SAMPLE_PNEZD = (
    "101,780000.000,13123359.580,800.00,IRON PIPE, BENT\n"
    "\n"
    "CP-4,782500.500,13000000.000,,CONTROL POINT\n"
    "007,785000.000,13200000.000,0.00,ZERO ELEVATION\n"
    'TBM1,787777.770,13123359.580,912.340,"BENCH, MARK"\n'
)


def _write_sample(tmp_path: Path, name: str = "job.txt") -> Path:
    path = tmp_path / name
    path.write_text(SAMPLE_PNEZD, encoding="utf-8", newline="")
    return path


def _south_to_central(tmp_path: Path, **overrides) -> jobmod.JobResult:
    """A real South -> Central job over SAMPLE_PNEZD, in International feet."""
    input_path = overrides.pop("input_path", None) or _write_sample(tmp_path)
    settings = JobSettings(
        input_path=input_path,
        output_directory=overrides.pop("output_directory", tmp_path / "out"),
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_SOUTH,
        target_zone=MI_CENTRAL,
        input_unit=overrides.pop("input_unit", INTERNATIONAL_FEET),
        output_unit=overrides.pop("output_unit", INTERNATIONAL_FEET),
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        **overrides,
    )
    return run(settings)


# ==========================================================================
# pnezd.py - the reader
# ==========================================================================


def test_description_is_everything_after_the_fourth_comma():
    """Module docstring: "the description is everything after the fourth comma".

    "101,1,2,3,IRON PIPE, BENT" splits on commas into six fields; fields[4:] is
    ["IRON PIPE", " BENT"], rejoined with "," gives "IRON PIPE, BENT".
    """
    parsed = pnezd.parse_lines(["101,1,2,3,IRON PIPE, BENT"])

    # Hand-derived: the whole remainder, not the first fragment.
    assert parsed.rows[0].description == "IRON PIPE, BENT"
    # And specifically NOT the truncation a naive 5-way split would produce.
    assert parsed.rows[0].description != "IRON PIPE"


def test_quoted_description_containing_commas_also_works():
    """csv quoting is honoured, so a proper export reads correctly too.

    '101,1,2,3,"IRON PIPE, BENT"' is four unquoted fields plus one quoted
    field, so csv yields exactly five fields and fields[4] is the description
    with its comma intact and the quotes consumed.
    """
    parsed = pnezd.parse_lines(['101,1,2,3,"IRON PIPE, BENT"'])

    # Hand-derived from the csv quoting rule: quotes are removed, comma kept.
    assert parsed.rows[0].description == "IRON PIPE, BENT"


def test_a_description_may_be_empty():
    """Four fields exactly: len(fields) == 4, so ",".join(fields[4:]) is ""."""
    parsed = pnezd.parse_lines(["101,1,2,3"])

    # Hand-derived: fields[4:] is the empty list, joined is the empty string.
    assert parsed.rows[0].description == ""


def test_point_identifiers_are_text_and_keep_their_exact_form():
    """Module docstring: "Point identifiers are text, not numbers."

    In particular "007" must survive as "007". Read as a number it would become
    7 and stop matching the point in the surveyor's field book.
    """
    parsed = pnezd.parse_lines(
        [
            "CP-4,1,2,3,A",
            "TBM1,1,2,3,B",
            "007,1,2,3,C",
        ]
    )

    ids = [row.point_id for row in parsed.rows]
    # Hand-derived: fields[0].strip(), verbatim, no numeric coercion anywhere.
    assert ids == ["CP-4", "TBM1", "007"]
    # The trap spelled out: 007 is not 7.
    assert ids[2] != "7"


def test_a_blank_elevation_is_absent_and_not_a_zero():
    """"" is in _ABSENT_ELEVATION_TEXT, so (None, False) - blank, not zeroed."""
    parsed = pnezd.parse_lines(["101,1,2,,DESC"])
    row = parsed.rows[0]

    # Hand-derived from _parse_elevation: cleaned == "" hits the absent set,
    # which returns (None, False) - the flag says "was NOT an explicit zero".
    assert row.elevation is None
    assert row.elevation_was_zero is False
    assert row.has_elevation is False


def test_an_explicit_zero_elevation_is_absent_but_flagged_as_zero():
    """The disclosed convention: 0.00 means "never levelled", and says so.

    _parse_elevation parses "0.00" to 0.0, which is not in the absent-text set,
    so it reaches the `value == 0.0` branch and returns (None, True). The two
    cases must stay distinguishable or the job record cannot report which it
    saw (docs/DESIGN.md section 7).
    """
    parsed = pnezd.parse_lines(["101,1,2,0.00,DESC"])
    row = parsed.rows[0]

    # Hand-derived: elevation absent, but flagged as an explicit zero.
    assert row.elevation is None
    assert row.elevation_was_zero is True


def test_blank_and_explicit_zero_elevations_are_told_apart():
    """The whole point of elevation_was_zero: the two are not flattened."""
    parsed = pnezd.parse_lines(["A,1,2,,x", "B,1,2,0.00,y"])

    # Hand-derived: both have elevation None, but the flags differ.
    assert parsed.rows[0].elevation is None
    assert parsed.rows[1].elevation is None
    assert parsed.rows[0].elevation_was_zero != parsed.rows[1].elevation_was_zero


@pytest.mark.parametrize("text", ["-", "n/a", "N/A", "na", "NULL", "None", "  "])
def test_the_other_absent_elevation_spellings(text):
    """_ABSENT_ELEVATION_TEXT, compared after strip() and lower()."""
    parsed = pnezd.parse_lines([f"101,1,2,{text},DESC"])

    # Hand-derived from the frozenset in the module: all of these are absent,
    # and none of them is an explicit zero.
    assert parsed.rows[0].elevation is None
    assert parsed.rows[0].elevation_was_zero is False


def test_nonzero_elevations_parse_normally_including_negative_ones():
    """Only exactly 0.0 is special. 912.34 and -12.5 are ordinary numbers."""
    parsed = pnezd.parse_lines(
        [
            "A,1,2,912.34,x",
            "B,1,2,-12.5,y",
            "C,1,2,0.001,z",
        ]
    )

    # Hand-derived: float() of the field text, unchanged.
    assert parsed.rows[0].elevation == 912.34
    assert parsed.rows[1].elevation == -12.5
    # 0.001 is not 0.0, so it is a real elevation, not the zero convention.
    assert parsed.rows[2].elevation == 0.001
    assert parsed.rows[2].elevation_was_zero is False


def test_blank_lines_are_skipped_and_counted():
    """Three blank lines around two coordinate rows.

    Lines 1 ("") , 3 ("   ") and 5 ("") are blank by `not line.strip()`;
    lines 2 and 4 are coordinate rows. So 2 rows and 3 skipped blanks, and the
    stored line numbers are the file's own: 2 and 4.
    """
    parsed = pnezd.parse_lines(["", "101,1,2,3,A", "   ", "102,4,5,6,B", ""])

    # Hand-derived by counting the five input lines above.
    assert len(parsed.rows) == 2
    assert parsed.skipped_blank_lines == 3
    assert [row.line_number for row in parsed.rows] == [2, 4]


def test_a_row_with_fewer_than_four_fields_is_refused_by_line_and_content():
    """Fail closed, and name the offending item (docs/DESIGN.md section 1).

    "101,1,2" is three fields; the reader needs at least four. The refusal must
    carry the line number (3 here) and quote the line, or it is useless against
    a file of several thousand points.
    """
    with pytest.raises(pnezd.PnezdError) as caught:
        pnezd.parse_lines(["1,2,3,4,ok", "5,6,7,8,ok", "101,1,2"], path="F.txt")

    message = str(caught.value)
    # Hand-derived: the bad row is the third line of the three supplied.
    assert "line 3" in message
    # The offending line is quoted verbatim (repr of the stripped line).
    assert "'101,1,2'" in message
    # And it says how many it found against how many it needs.
    assert "3 field(s)" in message
    assert "F.txt" in message


def test_a_blank_point_identifier_is_refused():
    """An unidentifiable point cannot be matched back to the input file."""
    with pytest.raises(pnezd.PnezdError) as caught:
        pnezd.parse_lines(["101,1,2,3,ok", ",4,5,6,nameless"], path="F.txt")

    message = str(caught.value)
    # Hand-derived: the offending row is line 2.
    assert "line 2" in message
    assert "point identifier is blank" in message


def test_a_non_numeric_northing_is_refused_by_name():
    """The refusal names WHICH field is wrong, not just that the row is."""
    with pytest.raises(pnezd.PnezdError) as caught:
        pnezd.parse_lines(["101,ABC,2,3,D"], path="F.txt")

    message = str(caught.value)
    # Hand-derived from _parse_number's message template: field name, the
    # offending text in repr form, and the line number.
    assert "northing" in message
    assert "'ABC'" in message
    assert "line 1" in message
    assert "not a number" in message


def test_a_non_numeric_easting_is_refused_by_name():
    with pytest.raises(pnezd.PnezdError) as caught:
        pnezd.parse_lines(["101,1,EAST,3,D"], path="F.txt")

    # Hand-derived: fields[2] is the easting, so the message says "easting".
    message = str(caught.value)
    assert "easting" in message
    assert "'EAST'" in message


def test_a_non_numeric_elevation_is_refused_by_name():
    with pytest.raises(pnezd.PnezdError) as caught:
        pnezd.parse_lines(["101,1,2,HIGH,D"], path="F.txt")

    # Hand-derived: _parse_elevation passes the field name "elevation" through.
    message = str(caught.value)
    assert "elevation" in message
    assert "'HIGH'" in message


def test_an_empty_file_is_refused_rather_than_succeeding_emptily():
    """An empty export that looks like a successful conversion is the failure
    this refusal exists to prevent."""
    with pytest.raises(pnezd.PnezdError) as caught:
        pnezd.parse_lines(["", "   ", ""], path="F.txt")

    # Hand-derived: no rows accumulated, so the "no coordinate rows" branch.
    assert "no coordinate rows" in str(caught.value)


def test_a_utf8_byte_order_mark_does_not_end_up_inside_the_first_point_id(tmp_path):
    """The real trap: EF BB BF before "101" must not make the id "\\ufeff101".

    read() decodes as utf-8-sig, which consumes exactly one leading BOM.
    """
    path = tmp_path / "bom.txt"
    # Bytes written by hand: BOM, then the ASCII of a normal PNEZD row.
    path.write_bytes(b"\xef\xbb\xbf101,780000.000,13123359.580,800.00,IP\r\n")

    parsed = pnezd.read(path)

    # Hand-derived: after utf-8-sig decoding the first character is "1".
    assert parsed.rows[0].point_id == "101"
    assert parsed.rows[0].point_id != "\ufeff101"
    # Belt and braces: no U+FEFF anywhere in the row at all.
    assert "\ufeff" not in parsed.rows[0].point_id
    assert "\ufeff" not in parsed.rows[0].description


def test_read_without_a_bom_is_unaffected(tmp_path):
    """utf-8-sig only strips a BOM when there is one; plain utf-8 is untouched.

    Anti-vacuousness for the test above: the assertion there would also pass on
    a reader that stripped the first character unconditionally, so pin that a
    file with no BOM keeps its first character.
    """
    path = tmp_path / "plain.txt"
    path.write_bytes(b"101,780000.000,13123359.580,800.00,IP\r\n")

    parsed = pnezd.read(path)

    # Hand-derived: the identifier is the three characters written.
    assert parsed.rows[0].point_id == "101"


def test_unquoted_thousands_separators_are_read_as_field_separators(tmp_path):
    """CURRENT BEHAVIOUR, pinned deliberately - see the report accompanying
    this suite.

    "101,13,221,442.048,650.00,IRON PIPE" is split by csv into SIX fields:
        fields[0] = "101"        -> point id
        fields[1] = "13"         -> northing  13.0
        fields[2] = "221"        -> easting   221.0
        fields[3] = "442.048"    -> elevation 442.048
        fields[4:] = ["650.00", "IRON PIPE"] -> description "650.00,IRON PIPE"

    The `.replace(",", "")` inside _parse_number never sees the grouped number,
    because csv has already taken the commas away as delimiters. This test
    asserts what the code does, not what one might wish it did.
    """
    parsed = pnezd.parse_lines(["101,13,221,442.048,650.00,IRON PIPE"])
    row = parsed.rows[0]

    # Hand-derived from the six-way split above.
    assert row.point_id == "101"
    assert row.northing == 13.0
    assert row.easting == 221.0
    assert row.elevation == 442.048
    assert row.description == "650.00,IRON PIPE"


def test_quoted_thousands_separators_are_stripped_from_the_number():
    """The other half of the same story: quoting makes grouping work.

    '"13,221,442.048"' is one csv field whose text is "13,221,442.048";
    _parse_number strips the commas giving "13221442.048" -> 13221442.048.
    '"4,000,000.00"' likewise gives 4000000.0.
    """
    parsed = pnezd.parse_lines(['101,"13,221,442.048","4,000,000.00",650.00,IP'])
    row = parsed.rows[0]

    # Hand-derived: 13,221,442.048 with the group separators removed.
    assert row.northing == 13221442.048
    # Hand-derived: 4,000,000.00 with the group separators removed.
    assert row.easting == 4000000.0
    assert row.description == "IP"


def test_points_without_elevation_lists_both_blank_and_zero_rows():
    parsed = pnezd.parse_lines(
        ["A,1,2,100.0,x", "B,1,2,,y", "C,1,2,0.00,z"]
    )

    # Hand-derived: B (blank) and C (explicit zero) both have elevation None;
    # A has 100.0 and is therefore excluded.
    assert [r.point_id for r in parsed.points_without_elevation] == ["B", "C"]


def test_read_records_the_path_and_the_blank_line_count(tmp_path):
    path = _write_sample(tmp_path)

    parsed = pnezd.read(path)

    # Hand-derived from SAMPLE_PNEZD: four coordinate rows and one blank line.
    assert len(parsed.rows) == 4
    assert parsed.skipped_blank_lines == 1
    assert parsed.path == path


# ==========================================================================
# formatting.py
# ==========================================================================


def test_angle_dms_of_zero():
    """0 degrees is 0 seconds: 0 deg, 0 min, 0.00 s, sign "+" (0 is not < 0).

    Field widths from the code: degrees and minutes %02d, seconds %05.2f.
    """
    # Hand-derived: "+" + "00" + " " + "00" + " " + "00.00".
    assert fmt.angle_dms(0.0) == "+00 00 00.00"


def test_angle_dms_of_a_typical_convergence():
    """0.24952739530106213 degrees.

        0.24952739530106213 x 3600 = 898.29862308... seconds
        rounded to 0.01                898.30 seconds
        898.30 / 60 = 14 remainder 58.30
            14 x 60 = 840; 898.30 - 840 = 58.30
        so 0 degrees, 14 minutes, 58.30 seconds, positive.
    """
    # Hand-derived above.
    assert fmt.angle_dms(0.24952739530106213) == "+00 14 58.30"


def test_angle_dms_carries_the_sign_on_the_whole_quantity():
    """-0.25 degrees.

        0.25 x 3600 = 900 seconds exactly
        900 / 60    = 15 minutes remainder 0
        so 0 degrees, 15 minutes, 00.00 seconds, negative.

    The sign belongs to the whole angle, so the degrees field itself is the
    unsigned "00" and the leading "-" covers all three fields. Anything like
    "-0 15 00.00" or "00 -15 00.00" would be wrong.
    """
    # Hand-derived above.
    assert fmt.angle_dms(-0.25) == "-00 15 00.00"


def test_angle_dms_negative_and_positive_differ_only_in_the_sign_character():
    """Same magnitude, opposite signs: the digits must be identical."""
    positive = fmt.angle_dms(0.25)
    negative = fmt.angle_dms(-0.25)

    # Hand-derived: "+00 15 00.00" and "-00 15 00.00".
    assert positive == "+00 15 00.00"
    assert negative == "-00 15 00.00"
    assert positive[1:] == negative[1:]


def test_angle_dms_pads_single_digit_seconds():
    """0.0025 degrees x 3600 = 9.0 seconds exactly -> 0 deg 0 min 09.00 s.

    The seconds field is %05.2f, so 9.0 prints as "09.00", not "9.00".
    """
    # Hand-derived above.
    assert fmt.angle_dms(0.0025) == "+00 00 09.00"


def test_angle_dms_seconds_rounding_carries_into_the_next_minute():
    """The carry the docstring promises: 59.999 s must never print "60.00".

    degrees = 59.999 / 3600, so |degrees| x 3600 = 59.999 seconds.
    round(59.999, 2) = 60.00, which is a whole minute.
        60.00 / 3600 = 0 degrees remainder 60.00
        60.00 / 60   = 1 minute remainder 0.00
    so 0 degrees, 1 minute, 00.00 seconds.
    """
    # Hand-derived above.
    assert fmt.angle_dms(59.999 / 3600.0) == "+00 01 00.00"
    # The failure being guarded against, stated directly.
    assert "60.00" not in fmt.angle_dms(59.999 / 3600.0)


def test_angle_dms_minute_rounding_carries_into_the_next_degree():
    """degrees = 3599.999 / 3600, i.e. 3599.999 seconds.

    round(3599.999, 2) = 3600.00 seconds.
        3600.00 / 3600 = 1 degree remainder 0.00
        0.00 / 60      = 0 minutes remainder 0.00
    so 1 degree, 0 minutes, 00.00 seconds - never "00 59 60.00" or "00 60 00.00".
    """
    result = fmt.angle_dms(3599.999 / 3600.0)

    # Hand-derived above.
    assert result == "+01 00 00.00"
    assert "60" not in result


def test_angle_dms_of_a_whole_degree_and_a_half():
    """1.5 degrees x 3600 = 5400 seconds.

        5400 / 3600 = 1 degree remainder 1800
        1800 / 60   = 30 minutes remainder 0
    """
    # Hand-derived above.
    assert fmt.angle_dms(1.5) == "+01 30 00.00"
    assert fmt.angle_dms(-1.5) == "-01 30 00.00"


def test_angle_dms_of_none_is_not_available():
    assert fmt.angle_dms(None) == "N/A"
    assert fmt.angle_dms(None) == fmt.NOT_AVAILABLE


def test_angle_dms_with_whole_seconds_uses_a_two_character_field():
    """seconds_decimals=0 sets width=2, so 9 seconds prints "09" not "09.".

    0.0025 degrees = 9.0 seconds exactly, as above.
    """
    # Hand-derived: "+00 00 09".
    assert fmt.angle_dms(0.0025, seconds_decimals=0) == "+00 00 09"


def test_factor_of_none_is_not_available():
    assert fmt.factor(None) == "N/A"


def test_factor_is_exactly_eight_decimal_places():
    """0.99990889 to 8 dp is "0.99990889" - the digits given, no more, no less.

    docs/DESIGN.md amendment #1: "factors 8 dp".
    """
    text = fmt.factor(0.99990889)

    # Hand-derived: the literal, unchanged.
    assert text == "0.99990889"
    # And the field really is 8 places after the point: len("99990889") == 8.
    assert len(text.split(".")[1]) == 8


def test_factor_pads_short_values_to_eight_places():
    """1.0 to 8 dp is "1.00000000": one digit, a point, then eight zeros."""
    # Hand-derived above.
    assert fmt.factor(1.0) == "1.00000000"


def test_coordinate_of_none_is_not_available():
    assert fmt.coordinate(None, INTERNATIONAL_FEET) == "N/A"
    assert fmt.coordinate(None, METERS) == "N/A"


def test_coordinate_uses_three_decimals_in_feet():
    """units.py: INTERNATIONAL_FEET.decimals == 3, US_SURVEY_FEET.decimals == 3.

    1234.56789 to 3 dp: the fourth decimal is 8, so the third rounds up from
    7 to 8 -> "1234.568".
    """
    # Hand-derived above.
    assert fmt.coordinate(1234.56789, INTERNATIONAL_FEET) == "1234.568"
    assert fmt.coordinate(1234.56789, US_SURVEY_FEET) == "1234.568"


def test_coordinate_uses_four_decimals_in_meters():
    """units.py: METERS.decimals == 4.

    1234.56789 to 4 dp: the fifth decimal is 9, so the fourth rounds up from
    8 to 9 -> "1234.5679".
    """
    # Hand-derived above.
    assert fmt.coordinate(1234.56789, METERS) == "1234.5679"


def test_coordinate_keeps_the_sign():
    """-12.5 in feet, 3 dp: "-12.500"."""
    # Hand-derived above.
    assert fmt.coordinate(-12.5, INTERNATIONAL_FEET) == "-12.500"


def test_signed_parts_per_million_of_a_short_factor():
    """0.99993 is 70 parts per million short of unity.

        (0.99993 - 1.0) x 1_000_000
      = (-0.00007) x 1_000_000
      = -70.0

    Formatted "+.1f", which forces the sign and one decimal: "-70.0".
    """
    # Hand-derived above.
    assert fmt.signed_parts_per_million(0.99993) == "-70.0"


def test_signed_parts_per_million_forces_a_plus_on_a_long_factor():
    """1.00005 is 50 ppm long:

        (1.00005 - 1.0) x 1_000_000 = 50.0  ->  "+50.0"
    """
    # Hand-derived above.
    assert fmt.signed_parts_per_million(1.00005) == "+50.0"


def test_signed_parts_per_million_of_unity_is_plus_zero():
    """(1.0 - 1.0) x 1e6 = 0.0, and "+.1f" of 0.0 is "+0.0"."""
    # Hand-derived above.
    assert fmt.signed_parts_per_million(1.0) == "+0.0"


def test_signed_parts_per_million_of_none_is_not_available():
    assert fmt.signed_parts_per_million(None) == "N/A"


def test_millimetres_converts_metres_to_four_places():
    """0.0005 m is half a millimetre: 0.0005 x 1000 = 0.5 -> "0.5000"."""
    # Hand-derived above.
    assert fmt.millimetres(0.0005) == "0.5000"
    assert fmt.millimetres(None) == "N/A"


def test_latitude_and_longitude_are_eight_decimal_places():
    """docs/DESIGN.md amendment #1: "latitude/longitude 8 dp".

    43.65 to 8 dp is "43.65000000" (two given digits then six padding zeros).
    """
    # Hand-derived above.
    assert fmt.latitude(43.65) == "43.65000000"
    assert fmt.longitude(-84.36666667) == "-84.36666667"
    assert fmt.latitude(None) == "N/A"
    assert fmt.longitude(None) == "N/A"


def test_longitude_positive_west_flips_the_sign():
    """The manual's convention: -84.36666667 signed is 84.36666667 positive-west."""
    # Hand-derived: negation, then 8 dp.
    assert fmt.longitude(-84.36666667, positive_west=True) == "84.36666667"
    # And the default is untouched, since a silent flip here is 340 miles.
    assert fmt.longitude(-84.36666667) == "-84.36666667"


def test_geoid_height_is_three_decimal_places():
    """NGS publishes geoid heights to 0.001 m. -34.1234 to 3 dp is "-34.123"
    (the fourth decimal, 4, rounds down)."""
    # Hand-derived above.
    assert fmt.geoid_height(-34.1234) == "-34.123"
    assert fmt.geoid_height(None) == "N/A"


def test_describe_convergence_spells_out_the_direction():
    """formatting.py: positive convergence means grid north lies WEST of true
    north, negative means EAST, zero means the point is on the central meridian.
    """
    # Hand-derived: 0.25 deg = 900 s = 15 minutes, positive -> west.
    assert fmt.describe_convergence(0.25).startswith("+00 15 00.00")
    assert "west" in fmt.describe_convergence(0.25)
    assert "east" in fmt.describe_convergence(-0.25)
    assert "central meridian" in fmt.describe_convergence(0.0)
    assert fmt.describe_convergence(None) == "N/A"


def test_is_finite_rejects_nan_and_both_infinities():
    """A NaN or an infinity written to a CSV imports into CAD as zero or as a
    parse error. Neither may reach a file."""
    # Hand-derived from math.isfinite's definition.
    assert fmt.is_finite(0.0) is True
    assert fmt.is_finite(-1234.5) is True
    assert fmt.is_finite(float("nan")) is False
    assert fmt.is_finite(float("inf")) is False
    assert fmt.is_finite(float("-inf")) is False


def test_is_finite_rejects_non_numbers():
    """isinstance guard: a string that looks numeric is still not a number."""
    assert fmt.is_finite("1234.5") is False
    assert fmt.is_finite(None) is False


# ==========================================================================
# writers.py
# ==========================================================================


def test_atomic_write_text_creates_the_file(tmp_path):
    path = atomic_write_text(tmp_path / "a.txt", "hello")

    # Hand-derived: the content written, with no newline translation to apply
    # because the string contains no "\n".
    assert path.read_text(encoding="utf-8") == "hello"


def test_atomic_write_text_uses_windows_line_endings_by_default(tmp_path):
    """newline="\\r\\n": every "\\n" in the content becomes CR LF on disk.

    "a\\nb" is 3 characters in, so on disk it is b"a\\r\\nb" - 4 bytes.
    """
    path = atomic_write_text(tmp_path / "a.txt", "a\nb")

    # Hand-derived above.
    assert path.read_bytes() == b"a\r\nb"


def test_atomic_write_text_refuses_an_existing_file(tmp_path):
    path = tmp_path / "a.txt"
    atomic_write_text(path, "original")

    with pytest.raises(WriteError) as caught:
        atomic_write_text(path, "replacement")

    # The refusal names the file and says nothing was written.
    assert str(path) in str(caught.value)
    assert "Nothing was written" in str(caught.value)


def test_a_refused_overwrite_leaves_the_original_file_untouched(tmp_path):
    """The property that actually matters: the previous file survives intact.

    "Exports never silently clobber" is worth nothing if the refusal happens
    after the old bytes are gone.
    """
    path = tmp_path / "a.txt"
    atomic_write_text(path, "original")

    with pytest.raises(WriteError):
        atomic_write_text(path, "replacement")

    # Hand-derived: the file still holds exactly the first write's content.
    assert path.read_text(encoding="utf-8") == "original"


def test_overwrite_true_replaces_the_content(tmp_path):
    path = tmp_path / "a.txt"
    atomic_write_text(path, "original")
    atomic_write_text(path, "replacement", overwrite=True)

    # Hand-derived: the second write's content, and only it.
    assert path.read_text(encoding="utf-8") == "replacement"


def test_no_partial_files_are_left_behind_after_a_successful_write(tmp_path):
    """The staging file is named ".<name>.*.partial" and must not survive."""
    atomic_write_text(tmp_path / "a.txt", "hello")

    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".partial")]
    # Hand-derived: os.replace renamed the staged file into place, so none.
    assert leftovers == []
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"]


def test_no_partial_files_are_left_behind_after_a_failed_write(tmp_path):
    """Force a failure AFTER staging, and check the cleanup in `finally`.

    A directory is created at the destination path. The existence check passes
    because overwrite=True, the temporary file is staged successfully, and then
    os.replace onto a directory raises OSError - which is exactly the "write
    failed late" case the staging file's cleanup exists for.
    """
    destination = tmp_path / "blocked.csv"
    destination.mkdir()

    with pytest.raises(WriteError):
        atomic_write_text(destination, "content", overwrite=True)

    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".partial")]
    # Hand-derived from the `finally` block: the staged file is unlinked.
    assert leftovers == []


def test_write_csv_rows_quotes_cells_with_commas_quotes_and_newlines(tmp_path):
    """The quoting rule in write_csv_rows, applied cell by cell.

    Row: [a,b] [say "hi"] [line1 LF line2] [plain] [None], where the brackets
    are not part of the data. Cell by cell, per the rule in writers.py -- wrap
    in quotes if the cell holds the delimiter, a quote, or a newline, and
    double every embedded quote:

        a,b              holds the delimiter -> wrapped:  QUOTE a,b QUOTE
        say "hi"         holds a quote       -> wrapped and doubled:
                                                QUOTE say QUOTE QUOTE hi
                                                QUOTE QUOTE QUOTE
        line1 LF line2   holds a newline     -> wrapped
        plain            holds none of them  -> bare
        None                                 -> the empty string, bare

    The five rendered cells are joined with commas, atomic_write_text appends
    one LF, and the newline="\\r\\n" argument turns every LF into CR LF -
    including the one inside the third cell.
    """
    path = write_csv_rows(
        tmp_path / "q.csv", [["a,b", 'say "hi"', "line1\nline2", "plain", None]]
    )

    # Hand-derived byte-for-byte from the rendering above.
    assert path.read_bytes() == (
        b'"a,b","say ""hi""","line1\r\nline2",plain,\r\n'
    )


def test_write_csv_rows_writes_one_line_per_row(tmp_path):
    """Two rows of three plain cells: two lines, each "x,y,z"."""
    path = write_csv_rows(tmp_path / "r.csv", [["1", "2", "3"], ["4", "5", "6"]])

    # Hand-derived: joined with ",", separated by "\n", trailing "\n",
    # every "\n" written as CR LF.
    assert path.read_bytes() == b"1,2,3\r\n4,5,6\r\n"


def test_write_csv_rows_refuses_an_existing_file_and_leaves_it_alone(tmp_path):
    path = tmp_path / "r.csv"
    write_csv_rows(path, [["1", "2"]])

    with pytest.raises(WriteError):
        write_csv_rows(path, [["9", "9"]])

    # Hand-derived: the first write's bytes, unchanged.
    assert path.read_bytes() == b"1,2\r\n"


def test_write_csv_rows_round_trips_through_the_csv_module(tmp_path):
    """The quoting must be readable by a standard csv reader, not just by us."""
    row = ["a,b", 'say "hi"', "plain"]
    path = write_csv_rows(tmp_path / "q.csv", [row])

    with open(path, newline="", encoding="utf-8") as stream:
        parsed = next(csv.reader(stream))

    # Hand-derived: the cells go in and come back identical.
    assert parsed == row


# ==========================================================================
# exports.py
# ==========================================================================


def test_output_stem_is_input_stem_plus_zone_abbreviation(tmp_path):
    result = _south_to_central(tmp_path)

    # Hand-derived: input file "job.txt" has stem "job"; MI_CENTRAL.abbrev is
    # "MI-C" (michspc/spc/zones.py); joined with "_".
    assert exports.output_stem(result) == "job_MI-C"


def test_write_all_writes_one_archive_holding_exactly_three_members(tmp_path):
    """A job writes ONE file (docs/DESIGN.md amendment #17), not three.

    Nothing is written loose beside the archive, so the output folder holds
    exactly one entry.
    """
    result = _south_to_central(tmp_path)
    out = result.settings.output_directory

    written = exports.write_all(result)

    # Hand-derived: the stem "job_MI-C" derived above, plus ".zip".
    assert [p.name for p in out.iterdir()] == ["job_MI-C.zip"]
    assert written["archive"].name == "job_MI-C.zip"

    # Every role points at the same archive; the roles name members inside it.
    assert set(written) == {"archive", "pnezd", "audit", "report"}
    assert {p for p in written.values()} == {written["archive"]}

    members = archive_members(written["archive"])
    assert sorted(members) == [
        "job_MI-C.csv",
        "job_MI-C_README.txt",
        "job_MI-C_full.csv",
    ]


def test_the_clean_export_has_no_header_row_and_exactly_five_fields(tmp_path):
    """A sixth column, or a header, either fails a CAD import or shifts every
    field one place left."""
    result = _south_to_central(tmp_path)
    written = exports.write_all(result)

    text = member_text(written["archive"], "MI-C.csv")
    rows = list(csv.reader(io.StringIO(text)))

    # Hand-derived from SAMPLE_PNEZD: four coordinate rows, no header.
    assert len(rows) == 4
    # Hand-derived: the first cell is the first point identifier, not "Point".
    assert rows[0][0] == "101"
    for row in rows:
        # Hand-derived: point, northing, easting, elevation, description.
        assert len(row) == 5


def test_the_audit_export_has_a_header_row_matching_audit_columns(tmp_path):
    result = _south_to_central(tmp_path)
    written = exports.write_all(result)

    text = member_text(written["archive"], "_full.csv")
    rows = list(csv.reader(io.StringIO(text)))

    # Hand-derived: audit_rows() seeds the list with list(AUDIT_COLUMNS).
    assert rows[0] == exports.AUDIT_COLUMNS
    # Hand-derived: one header plus four points.
    assert len(rows) == 5
    # Every data row is as wide as the header.
    for row in rows[1:]:
        assert len(row) == len(exports.AUDIT_COLUMNS)


def test_verify_round_trip_accepts_the_export_this_program_actually_builds(tmp_path):
    """Anti-vacuousness for the two refusal tests below: the check must PASS on
    good input, or its failures prove nothing."""
    result = _south_to_central(tmp_path)
    rows = exports.clean_pnezd_rows(result)

    # Must not raise.
    exports.verify_round_trip(rows, result)


def test_verify_round_trip_refuses_a_row_with_too_few_fields(tmp_path):
    """Rows this program's own PNEZD reader would reject must never be written.

    A three-field row trips parse_lines' "need at least 4" refusal, which
    verify_round_trip must re-raise as a WriteError.
    """
    result = _south_to_central(tmp_path)
    bad = [["101", "1", "2"] for _ in result.points]

    with pytest.raises(WriteError) as caught:
        exports.verify_round_trip(bad, result)

    # Hand-derived: the wrapper text, carrying the reader's own message.
    assert "cannot be read back by its own reader" in str(caught.value)
    assert "need at least 4" in str(caught.value)


def test_verify_round_trip_refuses_a_blank_point_identifier(tmp_path):
    result = _south_to_central(tmp_path)
    bad = [["", "1", "2", "3", "D"] for _ in result.points]

    with pytest.raises(WriteError) as caught:
        exports.verify_round_trip(bad, result)

    # Hand-derived: the reader's blank-identifier refusal, wrapped.
    assert "point identifier is blank" in str(caught.value)


def test_verify_round_trip_refuses_a_row_count_mismatch(tmp_path):
    """Four points converted, one row rendered: the export is short."""
    result = _south_to_central(tmp_path)
    short = exports.clean_pnezd_rows(result)[:1]

    with pytest.raises(WriteError) as caught:
        exports.verify_round_trip(short, result)

    message = str(caught.value)
    # Hand-derived: 1 row against 4 converted points (SAMPLE_PNEZD has four).
    assert "1 rows" in message
    assert "4 points" in message


def test_verify_round_trip_refuses_a_point_identifier_mismatch(tmp_path):
    """A row whose identifier does not match the point it claims to be."""
    result = _south_to_central(tmp_path)
    rows = exports.clean_pnezd_rows(result)
    rows[0] = ["WRONG"] + rows[0][1:]

    with pytest.raises(WriteError) as caught:
        exports.verify_round_trip(rows, result)

    message = str(caught.value)
    # Hand-derived: it names both the row's id and the job's id.
    assert "'WRONG'" in message
    assert "'101'" in message


def test_verify_round_trip_does_not_catch_the_text_nan(tmp_path):
    """CURRENT BEHAVIOUR, pinned deliberately, and it is not what the docstring
    of verify_round_trip claims.

    exports.verify_round_trip says a value formatted as "nan" "would produce a
    file that looks written and imports wrongly", implying the check stops it.
    It does not: Python's float("nan") succeeds, so pnezd.parse_lines accepts
    the cell as a perfectly good northing and the round trip passes.

    Hand-derived: float("nan") is a legal float literal, therefore
    _parse_number's try/except never fires, therefore no PnezdError, therefore
    no WriteError.

    What actually stops a NaN reaching the clean export is the fmt.is_finite
    loop at the top of write_all - a different mechanism, over a narrower set
    of values. See the accompanying report.
    """
    result = _south_to_central(tmp_path)
    rows = exports.clean_pnezd_rows(result)
    rows[0] = [rows[0][0], "nan", rows[0][2], rows[0][3], rows[0][4]]

    # Must not raise - pinning the gap, not endorsing it.
    exports.verify_round_trip(rows, result)


def test_the_reader_accepts_the_text_nan_as_a_coordinate():
    """The root of the gap above, isolated.

    CURRENT BEHAVIOUR. "nan", "inf" and "-inf" are all accepted by float(), so
    _parse_number returns them and a non-finite value enters the core from a
    coordinate file. Reported, not fixed.
    """
    parsed = pnezd.parse_lines(["101,nan,inf,3,D"])

    # Hand-derived from float()'s accepted literals.
    assert math.isnan(parsed.rows[0].northing)
    assert math.isinf(parsed.rows[0].easting)


def test_write_all_writes_nothing_when_a_coordinate_is_not_a_number(tmp_path):
    """A NaN northing must abort the whole job, leaving the folder untouched.

    dataclasses.replace on a real converted point is used rather than a
    hand-built stub, so the rest of the record is genuine and only the one
    value is poisoned.
    """
    result = _south_to_central(tmp_path)
    out = result.settings.output_directory
    out.mkdir(parents=True, exist_ok=True)

    poisoned = dataclasses.replace(result.points[2], output_northing=float("nan"))
    result = dataclasses.replace(
        result, points=result.points[:2] + (poisoned,) + result.points[3:]
    )

    with pytest.raises(WriteError) as caught:
        exports.write_all(result)

    message = str(caught.value)
    # Hand-derived: SAMPLE_PNEZD's third coordinate row is point "007".
    assert "Point 007" in message
    assert "northing" in message
    assert "Nothing was written" in message
    # The property that matters: not one of the three files appeared.
    assert list(out.iterdir()) == []


def test_write_all_writes_nothing_when_an_easting_is_infinite(tmp_path):
    """Same guard, the other coordinate, the other non-finite value."""
    result = _south_to_central(tmp_path)
    out = result.settings.output_directory
    out.mkdir(parents=True, exist_ok=True)

    poisoned = dataclasses.replace(result.points[0], output_easting=float("inf"))
    result = dataclasses.replace(result, points=(poisoned,) + result.points[1:])

    with pytest.raises(WriteError) as caught:
        exports.write_all(result)

    # Hand-derived: the first coordinate row of SAMPLE_PNEZD is point "101".
    assert "Point 101" in str(caught.value)
    assert "easting" in str(caught.value)
    assert list(out.iterdir()) == []


def test_write_all_refuses_to_clobber_and_leaves_the_first_file_alone(tmp_path):
    """Running the same job twice into the same folder must not overwrite."""
    result = _south_to_central(tmp_path)
    written = exports.write_all(result)
    original = written["pnezd"].read_bytes()

    with pytest.raises(WriteError):
        exports.write_all(result)

    # Hand-derived: the clean export still holds the first run's bytes.
    assert written["pnezd"].read_bytes() == original


def test_a_missing_elevation_is_written_as_not_available_in_the_clean_export(
    tmp_path,
):
    """"N/A", never 0.000 - a fabricated zero would travel onto a drawing."""
    result = _south_to_central(tmp_path)
    rows = exports.clean_pnezd_rows(result)

    by_id = {row[0]: row for row in rows}
    # Hand-derived: CP-4's Z field is blank and 007's is 0.00, so both are
    # absent, and fmt.coordinate(None, unit) is fmt.NOT_AVAILABLE == "N/A".
    assert by_id["CP-4"][3] == "N/A"
    assert by_id["007"][3] == "N/A"
    # And a point that DID carry an elevation is a number, not "N/A".
    assert by_id["101"][3] != "N/A"


# ==========================================================================
# report.py
# ==========================================================================


def test_the_report_records_the_input_file_and_its_hash(tmp_path):
    """A job record that names a file but not its contents proves nothing."""
    result = _south_to_central(tmp_path)

    text = report.build_report(result)

    # Independently recomputed from the bytes on disk, not read back from the
    # program: sha256 of the file the job was pointed at.
    expected = hashlib.sha256(
        result.settings.input_path.read_bytes()
    ).hexdigest()
    assert expected in text
    assert str(result.settings.input_path) in text
    # Hand-derived: SAMPLE_PNEZD has 4 coordinate rows and 1 blank line.
    assert "Coordinate rows    4" in text
    assert "Blank lines        1 (skipped)" in text


def test_the_report_names_every_point_with_no_usable_elevation(tmp_path):
    """docs/DESIGN.md section 7: every affected point is named in the report,
    and the blank case is listed separately from the explicit-zero case."""
    result = _south_to_central(tmp_path)

    text = report.build_report(result)

    # Hand-derived from SAMPLE_PNEZD: CP-4 blank, 007 exactly 0.00, so two of
    # the four points have no usable elevation.
    assert "2 of 4 points had NO usable elevation" in text
    assert "Blank elevation field (1):" in text
    assert "Elevation field held exactly 0.00 (1):" in text
    assert "CP-4" in text
    assert "007" in text
    # And it states the refusal to fabricate.
    assert "They are NOT set to 1.0" in text


def test_the_report_states_the_units_in_force_on_both_sides(tmp_path):
    """"the unit in force is stated in every output file" (DESIGN.md section 7).

    A file converted under the wrong foot definition looks entirely ordinary.
    """
    result = _south_to_central(
        tmp_path, input_unit=INTERNATIONAL_FEET, output_unit=US_SURVEY_FEET
    )

    text = report.build_report(result)

    # Hand-derived from units.py's name/code fields.
    assert "Units in           International feet (ift)" in text
    assert "Units out          US survey feet (usft)" in text


def test_the_report_names_all_three_files_it_describes(tmp_path):
    result = _south_to_central(tmp_path)

    text = report.build_report(result)

    # Hand-derived: stem "job_MI-C" plus the three suffixes from exports.py.
    assert "job_MI-C.csv" in text
    assert "job_MI-C_full.csv" in text
    assert "job_MI-C_README.txt" in text


def test_the_report_names_both_zones_and_their_defining_constants(tmp_path):
    result = _south_to_central(tmp_path)

    text = report.build_report(result)

    # Hand-derived from zones.py: Michigan South is 2113, Central is 2112, and
    # both share the central meridian 84 deg 22' west = -84.3666666667 deg.
    assert "FROM: Michigan South, zone 2113" in text
    assert "TO: Michigan Central, zone 2112" in text
    assert "-84.3666666667" in text


def test_the_report_says_when_every_point_had_an_elevation(tmp_path):
    """The other branch of the elevation section - so the test above is not
    passing merely because the section always says the same thing."""
    path = tmp_path / "allz.txt"
    path.write_text(
        "101,780000.000,13123359.580,800.00,A\n"
        "102,782500.500,13000000.000,810.00,B\n",
        encoding="utf-8",
        newline="",
    )
    result = _south_to_central(tmp_path, input_path=path)

    text = report.build_report(result)

    # Hand-derived: both points carry an elevation, so the "all" branch.
    assert "All 2 points carried a usable elevation." in text
    assert "had NO usable elevation" not in text


# ==========================================================================
# job.py
# ==========================================================================


def test_a_zone_to_zone_job_with_no_zones_is_refused_with_a_useful_message(
    tmp_path,
):
    settings = JobSettings(
        input_path=_write_sample(tmp_path),
        output_directory=tmp_path / "out",
        direction=Direction.ZONE_TO_ZONE,
        source_zone=None,
        target_zone=None,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
    )

    with pytest.raises(ValueError) as caught:
        run(settings)

    message = str(caught.value)
    # The refusal must teach: say what is missing and that nothing is guessed.
    assert "source" in message
    assert "target" in message
    assert "Neither is inferred from the coordinates" in message


def test_a_zone_to_zone_job_missing_only_the_target_is_still_refused(tmp_path):
    settings = JobSettings(
        input_path=_write_sample(tmp_path),
        output_directory=tmp_path / "out",
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_SOUTH,
        target_zone=None,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
    )

    with pytest.raises(ValueError):
        run(settings)


def test_a_geodetic_to_zone_job_needs_a_target_zone(tmp_path):
    settings = JobSettings(
        input_path=_write_sample(tmp_path),
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=None,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
    )

    with pytest.raises(ValueError) as caught:
        run(settings)

    assert "target zone" in str(caught.value)


def test_a_zone_to_geodetic_job_needs_the_source_zone(tmp_path):
    settings = JobSettings(
        input_path=_write_sample(tmp_path),
        output_directory=tmp_path / "out",
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=None,
        target_zone=None,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
    )

    with pytest.raises(ValueError) as caught:
        run(settings)

    assert "the zone the file is in" in str(caught.value)


@pytest.mark.parametrize("convention", list(LongitudeConvention))
@pytest.mark.parametrize("value", [-84.36666667, 0.0, 84.36666667, -90.5])
def test_longitude_convention_round_trips(convention, value):
    """from_signed(to_signed(x)) == x for both conventions.

    NEGATIVE_WEST is the identity, so the composition is trivially x.
    POSITIVE_WEST negates, so the composition is -(-x) == x - exact in IEEE
    754, because negation only flips the sign bit.
    """
    # Hand-derived above: exact equality is the right assertion here.
    assert convention.from_signed(convention.to_signed(value)) == value
    assert convention.to_signed(convention.from_signed(value)) == value


def test_positive_west_flips_the_sign_and_negative_west_does_not():
    """The distinction that throws a Michigan point 340 miles if got wrong.

    Michigan Central's central meridian is 84 deg 22' WEST. Signed (the
    program's internal convention) that is -84.3666...; in the manual's
    positive-west convention it is +84.3666...
    """
    signed = -84.36666667

    # Hand-derived: POSITIVE_WEST means "the file's 84.37 is really -84.37".
    assert LongitudeConvention.POSITIVE_WEST.to_signed(84.36666667) == signed
    assert LongitudeConvention.POSITIVE_WEST.from_signed(signed) == 84.36666667
    # Hand-derived: NEGATIVE_WEST is already the program's convention.
    assert LongitudeConvention.NEGATIVE_WEST.to_signed(signed) == signed
    assert LongitudeConvention.NEGATIVE_WEST.from_signed(signed) == signed


def test_longitude_convention_has_no_default_value():
    """DESIGN.md section 7: "selected by the user with no default".

    An Enum with no member designated as default is the enforcement; this pins
    that nobody has added one, and that both members remain distinguishable.
    """
    members = list(LongitudeConvention)

    # Hand-derived: exactly the two conventions in the docstring.
    assert len(members) == 2
    assert LongitudeConvention.POSITIVE_WEST is not LongitudeConvention.NEGATIVE_WEST


def test_elevation_passes_through_unchanged_when_the_units_match(tmp_path):
    """Orthometric height does not depend on the horizontal zone.

    In feet in, feet out, 800.00 must come out 800.00. Internally it becomes
    800 x 0.3048 = 243.84 m and then 243.84 / 0.3048 = 800, so the only error
    possible is IEEE rounding in the two operations - bounded here at 1e-9 ft,
    which is a nanometre-scale quantity and far below the 0.001 ft written.
    """
    result = _south_to_central(
        tmp_path, input_unit=INTERNATIONAL_FEET, output_unit=INTERNATIONAL_FEET
    )
    point = next(p for p in result.points if p.point_id == "101")

    # Hand-derived above.
    assert abs(point.output_elevation - 800.0) < 1e-9


def test_elevation_is_re_expressed_when_the_units_differ(tmp_path):
    """800 International feet, expressed in US survey feet.

    units.py gives the two feet exactly:
        International foot = 0.3048 m exactly
        US survey foot     = 1200/3937 m exactly

        800 ift  = 800 x 0.3048 = 243.84 m exactly

        243.84 m in US survey feet
            = 243.84 x 3937 / 1200
            = 959,998.08 / 1200          (243.84 x 3937: 243.84 x 3900 = 950,976
                                          plus 243.84 x 37 = 9,022.08)
            = 799.9984 US survey feet exactly

    Cross-check by the ratio of the two feet:
        0.3048 / (1200/3937) = 0.3048 x 3937 / 1200 = 1199.9976 / 1200
                             = 0.999998
        800 x 0.999998 = 799.9984.  Agrees.

    Note the direction: the US survey foot is the LONGER foot (by 2 ppm), so a
    fixed length is a SMALLER number of them. 800 ift is 799.9984 usft, not
    800.0016 - that figure is the other direction, 800 usft in ift.
    """
    result = _south_to_central(
        tmp_path, input_unit=INTERNATIONAL_FEET, output_unit=US_SURVEY_FEET
    )
    point = next(p for p in result.points if p.point_id == "101")

    # Hand-derived above. Tolerance is IEEE noise on three exact operations.
    assert abs(point.output_elevation - 799.9984) < 1e-9
    # And it really moved: 800 usft would be wrong by 0.0016 ft.
    assert point.output_elevation != 800.0


def test_elevation_re_expressed_the_other_way_round(tmp_path):
    """800 US survey feet, expressed in International feet.

        800 usft = 800 x 1200/3937 = 960,000/3937 m
        in ift   = 960,000 / (3937 x 0.3048)
                 = 960,000 / 1199.9976

    Equivalently, one US survey foot is 1200/1199.9976 International feet:

        0.0024 / 1199.9976 = 2.0000040000...e-6
        so the ratio is 1.0000020000040...
        and 800 x 1.000002000004 = 800 + 800 x 2.000004e-6
                                 = 800 + 0.0016000032
                                 = 800.0016000032

    Verify by multiplying back:
        1199.9976 x 800.0016 = 1199.9976 x 800  +  1199.9976 x 0.0016
                             = 959,998.08       +  1.91999616
                             = 959,999.99999616
        short of 960,000 by 0.00000384, and 0.00000384 / 1199.9976 = 3.2e-9,
        so the true quotient is 800.0016 + 0.0000000032 = 800.0016000032.
        Agrees with the ratio derivation.

    Note the direction: 800 usft is 800.0016 ift, whereas 800 ift is 799.9984
    usft (the test above). Those are different numbers and the 2 ppm between
    them is about 26 feet at Michigan South's false easting.
    """
    result = _south_to_central(
        tmp_path, input_unit=US_SURVEY_FEET, output_unit=INTERNATIONAL_FEET
    )
    point = next(p for p in result.points if p.point_id == "101")

    # Hand-derived above. Tolerance is IEEE noise on three exact operations.
    assert abs(point.output_elevation - 800.0016000032) < 1e-9


def test_a_point_with_no_elevation_gets_no_elevation_or_combined_factor(tmp_path):
    """Never 1.0, never the grid factor alone (DESIGN.md section 7).

    The grid scale factor does NOT depend on elevation, so it must still be
    present - reporting it as absent would be its own fabrication.
    """
    result = _south_to_central(tmp_path)
    point = next(p for p in result.points if p.point_id == "CP-4")

    # Hand-derived from factors_at: orthometric_height None short-circuits to
    # elevation_factor None and combined_factor None.
    assert point.row.elevation is None
    assert point.factors.elevation_factor is None
    assert point.factors.combined_factor is None
    assert point.factors.has_elevation is False
    # The grid scale factor survives, and is a real Lambert factor near unity.
    assert point.factors.grid_scale_factor is not None
    assert math.isfinite(point.factors.grid_scale_factor)
    # Michigan's zones are designed for about 1 part in 10,000 (manual ch. 1),
    # so any grid factor must sit within 0.001 of unity.
    assert abs(point.factors.grid_scale_factor - 1.0) < 1e-3


def test_an_explicit_zero_elevation_also_gets_no_factors(tmp_path):
    """Point 007's Z field is 0.00, which the disclosed convention treats as
    "not recorded" - so it takes the same path as a blank field."""
    result = _south_to_central(tmp_path)
    point = next(p for p in result.points if p.point_id == "007")

    # Hand-derived: the reader returned elevation None, so no factors.
    assert point.factors.elevation_factor is None
    assert point.factors.combined_factor is None
    assert point.row.elevation_was_zero is True


def test_a_point_with_an_elevation_gets_both_factors(tmp_path):
    """Anti-vacuousness for the two tests above: the factors are not always
    None, so their absence above is caused by the missing elevation."""
    result = _south_to_central(tmp_path)
    point = next(p for p in result.points if p.point_id == "101")

    assert point.factors.elevation_factor is not None
    assert point.factors.combined_factor is not None
    # Hand-derived from factors.py: combined = grid x elevation, exactly.
    assert point.factors.combined_factor == (
        point.factors.grid_scale_factor * point.factors.elevation_factor
    )
    # Hand-derived: the elevation factor is R/(R+h) with h = H + N. In
    # Michigan N is about -35 m and H here is 800 ift = 243.84 m, so
    # h is about 209 m and the factor is 6372000/6372209 - a shade under 1.
    assert 0.9999 < point.factors.elevation_factor < 1.0


def test_points_without_elevation_lists_exactly_the_two_affected_points(tmp_path):
    result = _south_to_central(tmp_path)

    # Hand-derived from SAMPLE_PNEZD: CP-4 (blank) and 007 (0.00).
    assert [p.point_id for p in result.points_without_elevation] == ["CP-4", "007"]
    # Hand-derived: combined factors exist only for the other two points.
    assert len(result.combined_factors) == 2
    # Hand-derived: the grid scale factor exists for all four.
    assert len(result.grid_scale_factors) == 4


def test_file_sha256_matches_hashlib_on_the_same_bytes(tmp_path):
    path = tmp_path / "hash.bin"
    payload = b"101,780000.000,13123359.580,800.00,IRON PIPE, BENT\r\n"
    path.write_bytes(payload)

    # Independently recomputed with hashlib over the same bytes.
    assert file_sha256(path) == hashlib.sha256(payload).hexdigest()


def test_file_sha256_spans_more_than_one_read_block(tmp_path):
    """file_sha256 reads in 1 MiB blocks; a file larger than one block proves
    the loop accumulates rather than hashing only the first chunk."""
    path = tmp_path / "big.bin"
    # 1 MiB + 1 byte, so exactly two iterations of the read loop.
    payload = b"A" * (1024 * 1024 + 1)
    path.write_bytes(payload)

    assert file_sha256(path) == hashlib.sha256(payload).hexdigest()


def test_the_job_result_records_the_input_hash_and_row_counts(tmp_path):
    result = _south_to_central(tmp_path)

    # Independently recomputed from the file on disk.
    assert result.input_sha256 == hashlib.sha256(
        result.settings.input_path.read_bytes()
    ).hexdigest()
    # Hand-derived from SAMPLE_PNEZD.
    assert result.input_row_count == 4
    assert result.skipped_blank_lines == 1
    assert result.geoid_model == "GEOID18"


def test_a_job_with_the_geoid_disabled_reports_no_model_and_no_factors(tmp_path):
    result = _south_to_central(tmp_path, apply_geoid=False)

    # Hand-derived from run(): grid is None, so geoid_height stays None for
    # every point and factors_at short-circuits to None factors.
    assert result.geoid_model is None
    assert result.combined_factors == ()
    for point in result.points:
        assert point.factors.elevation_factor is None
        # ...but the horizontal conversion is untouched.
        assert math.isfinite(point.output_northing)
        assert math.isfinite(point.output_easting)


# ==========================================================================
# End to end
# ==========================================================================


def test_identifiers_and_descriptions_survive_a_full_export_and_re_read(tmp_path):
    """Write the three files, then read the clean export back with this
    program's own reader and compare every identifier and description.

    The traps this catches: "007" turning into "7", "IRON PIPE, BENT" losing
    its tail at the comma, and a quoted "BENCH, MARK" gaining or losing quotes.
    """
    result = _south_to_central(tmp_path)
    written = exports.write_all(result)
    extracted = extract_member(written["archive"], "MI-C.csv", tmp_path / "unzipped")

    reread = pnezd.read(extracted)

    # Hand-derived from SAMPLE_PNEZD, in file order.
    assert [row.point_id for row in reread.rows] == ["101", "CP-4", "007", "TBM1"]
    assert [row.description for row in reread.rows] == [
        "IRON PIPE, BENT",
        "CONTROL POINT",
        "ZERO ELEVATION",
        "BENCH, MARK",
    ]
    # And the re-read identifiers match the converted points one for one.
    assert [row.point_id for row in reread.rows] == [
        p.point_id for p in result.points
    ]


def test_the_re_read_export_preserves_the_absence_of_an_elevation(tmp_path):
    """"N/A" is in _ABSENT_ELEVATION_TEXT, so a missing elevation stays missing
    through the export - it does not come back as 0.00.

    Note what is NOT preserved: the blank-versus-explicit-zero distinction.
    Both are written "N/A", so both re-read as blank. That is by design - the
    job record is where the original distinction is recorded - and this test
    pins it so a future change to the export has to face the question.
    """
    result = _south_to_central(tmp_path)
    written = exports.write_all(result)
    extracted = extract_member(written["archive"], "MI-C.csv", tmp_path / "unzipped")

    reread = pnezd.read(extracted)
    by_id = {row.point_id: row for row in reread.rows}

    # Hand-derived: CP-4 was blank, 007 was 0.00; both export as "N/A", which
    # the reader maps back to (None, False).
    assert by_id["CP-4"].elevation is None
    assert by_id["007"].elevation is None
    assert by_id["007"].elevation_was_zero is False
    # Hand-derived: 101 carried 800.00 ift, written to 3 dp as "800.000".
    assert by_id["101"].elevation == 800.0
    # Hand-derived: TBM1 carried 912.340 ift.
    assert by_id["TBM1"].elevation == 912.34


def test_south_to_central_and_back_returns_the_original_coordinates(tmp_path):
    """South -> Central -> South, through the real exports, must land within
    0.001 international feet of where it started.

    WHY 0.001 FEET IS THE RIGHT TOLERANCE, derived rather than tuned:

    The projection itself contributes essentially nothing. Zone-to-zone inside
    one reference frame is an exact re-projection of the same geodetic position
    (DESIGN.md section 4), and the inverse latitude iterates to machine
    precision, with the measured round-trip error below 1e-11 degrees, about
    one micrometre (DESIGN.md amendment #3). One micrometre is 3.3e-6 feet.

    What actually limits the round trip is the FILE. The owner specified 3
    decimal places of feet (DESIGN.md amendment #1), so:

      * writing the Central coordinate rounds it to the nearest 0.001 ft,
        an error of at most 0.0005 ft;
      * reading that back and re-projecting to South carries that error
        across essentially unchanged - the two zones' scale factors are both
        within 1e-4 of unity, so the transfer alters the 0.0005 ft by at most
        5e-8 ft;
      * writing the South coordinate rounds again, at most another 0.0005 ft.

        0.0005 + 0.0005 + 3.3e-6 + 5e-8  =  0.0010033 ft worst case,
        and the two rounding errors only reach their maxima together in the
        worst case; 0.001 ft is the bound the format itself imposes.

    Any tolerance looser than this would hide a real error; any tighter would
    fail on quantisation alone. So: 0.001 ft, with the 3.4e-6 ft of non-format
    error allowed for explicitly.
    """
    TOLERANCE_FT = 0.001 + 3.4e-6  # two roundings, plus the projection residual

    forward = _south_to_central(tmp_path)
    written = exports.write_all(forward)
    extracted = extract_member(written["archive"], "MI-C.csv", tmp_path / "unzipped3")

    back_settings = JobSettings(
        input_path=extracted,
        output_directory=tmp_path / "back",
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_CENTRAL,
        target_zone=MI_SOUTH,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    backward = run(back_settings)

    assert len(backward.points) == len(forward.points)

    for original, returned in zip(forward.points, backward.points):
        # The identifier must not have drifted either.
        assert returned.point_id == original.point_id

        # original.row.northing / .easting are the literal values from
        # SAMPLE_PNEZD, in international feet.
        assert abs(returned.output_northing - original.row.northing) <= TOLERANCE_FT
        assert abs(returned.output_easting - original.row.easting) <= TOLERANCE_FT


def test_the_round_trip_test_would_notice_a_shifted_coordinate(tmp_path):
    """Anti-vacuousness for the tolerance above.

    A tolerance of 0.001 ft proves nothing unless it is tight enough to catch
    a real error. Michigan South and Michigan Central have false eastings
    2,000,000 m apart, so a converted coordinate is nowhere near its input:
    the test above only passes because the conversion genuinely came back.
    """
    forward = _south_to_central(tmp_path)

    for point in forward.points:
        # Hand-derived: the false eastings differ by 6,000,000 - 4,000,000 =
        # 2,000,000 m = 2,000,000 / 0.3048 = 6,561,679.79 international feet.
        # The central meridians are identical (both 84 deg 22' W), so the
        # Central easting of these points must exceed the South easting by
        # roughly that amount - certainly by more than a million feet.
        assert point.output_easting - point.row.easting > 1_000_000.0
        # If the "round trip" above were comparing a value to itself, this
        # separation would be zero.
        assert abs(point.output_easting - point.row.easting) > 0.001
