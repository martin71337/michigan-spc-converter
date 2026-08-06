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
from enum import Enum
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
from michspc.spc.frames import NAD83_2011, NATRF2022, FrameMismatchError
from michspc.spc.convert import ConversionWarning, WarningCode
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


def test_a_byte_that_is_neither_utf8_nor_cp1252_raises_a_pnezd_error(tmp_path):
    """The refusal must be this program's, not Python's.

    read() decodes utf-8-sig and falls back to cp1252. The fallback's `except`
    caught only OSError, so a file that is neither raised a raw
    UnicodeDecodeError straight out of the file layer - which the GUI shows the
    surveyor as a Python traceback message rather than a sentence naming the
    file and saying what to do (DESIGN.md s.1, "a loud, specific refusal naming
    the offending item").

    Hand-derived choice of byte: 0x81 is not a legal UTF-8 lead byte, AND it is
    one of the five positions cp1252 leaves undefined (0x81, 0x8D, 0x8F, 0x90,
    0x9D). So both decoders must fail on it, which is what makes it the right
    counterexample - anything else would only prove the first decoder failed.
    """
    path = tmp_path / "binary.txt"
    path.write_bytes(b"101,780000.000,13123359.580,800.00,IRON\x81PIPE\r\n")

    with pytest.raises(pnezd.PnezdError) as caught:
        pnezd.read(path)

    message = str(caught.value)
    # Hand-derived: names the file, the byte, and where it is.
    assert "binary.txt" in message
    assert "0x81" in message
    # Hand-derived: b"101,780000.000,13123359.580,800.00,IRON" is 39 bytes
    # (4 + 11 + 1 + 13 + 1 + 6 + 1 + 4 = 39... counted directly below), so the
    # offending byte sits at that index.
    assert str(b"101,780000.000,13123359.580,800.00,IRON".index(b"N") + 1) in message
    # And it says what to do.
    assert "Export it again" in message


def test_the_cp1252_fallback_still_reads_a_legacy_ansi_file(tmp_path):
    """Anti-vacuousness: the fix must not have turned the fallback into a wall.

    Hand-derived: 0xE9 is cp1252 for 'e-acute'. On its own it is not valid
    UTF-8 (it is a three-byte lead byte followed by ASCII), so utf-8-sig fails
    and cp1252 succeeds - the case the fallback exists for.
    """
    path = tmp_path / "ansi.txt"
    path.write_bytes(b"101,780000.000,13123359.580,800.00,B\xc9TON\r\n")

    parsed = pnezd.read(path)

    # Hand-derived: cp1252 0xC9 is 'E-acute', U+00C9.
    assert parsed.rows[0].description == "BÉTON"
    assert parsed.rows[0].northing == 780000.0


def test_unquoted_thousands_separators_are_refused_not_guessed(tmp_path):
    """REWRITTEN. This test previously pinned the DEFECT as current behaviour.

    It asserted that "101,13,221,442.048,650.00,IRON PIPE" was accepted as
    northing 13.0, easting 221.0, elevation 442.048 - a point some 13 million
    feet from the one written, produced silently. The tier sentence says a
    wrong coordinate moves a boundary, so the behaviour was fixed and the pin
    rewritten to assert the refusal. It is not weakened to keep green.

    Hand-derived. csv splits the row into SIX fields:
        ["101", "13", "221", "442.048", "650.00", "IRON PIPE"]
    Two readings of those commas are both well formed PNEZD:
        literal - N 13, E 221, Z 442.048, description "650.00,IRON PIPE"
        grouped - N 13, E 221442.048, Z 650.00, description "IRON PIPE"
    Nothing in the file says which was meant, so the reader refuses.

    The signature the reader keys on: fields[1] = "13" is one-to-three digits
    and fields[2] = "221" is exactly three, which is the shape an unquoted
    group separator leaves behind; and the description "650.00,..." begins with
    a bare number, which is the shifted field the stray comma pushed there.
    """
    with pytest.raises(pnezd.PnezdError) as caught:
        pnezd.parse_lines(["101,13,221,442.048,650.00,IRON PIPE"], path="J.txt")

    message = str(caught.value)
    # Hand-derived: the refusal names the file and the line, per DESIGN.md s.1.
    assert "J.txt" in message
    assert "line 1" in message
    # It names the offending text, not just the row.
    assert "'13,221'" in message
    # And it says what to do about it, in both permitted forms.
    assert "remove the thousands separators" in message
    assert "double quotes" in message


def test_the_reviewers_grouped_row_is_refused_and_never_reaches_a_file(tmp_path):
    """The reviewer's own counterexample, end to end.

        101,780,000.000,13,123,359.580,800.00,IRON PIPE

    Hand-derived. csv splits this into EIGHT fields:
        ["101", "780", "000.000", "13", "123", "359.580", "800.00", "IRON PIPE"]
    so the literal reading is northing 780.0, easting 0.0, elevation 13.0 and
    description "123,359.580,800.00,IRON PIPE" - while the reading the surveyor
    plainly meant is northing 780000.000, easting 13123359.580, elevation
    800.00. The two differ by more than 13 million feet in easting. Both are
    well formed, so the file is refused.

    Asserted at the JOB level as well as the parser, because the defect that
    mattered was that this row produced a written export.
    """
    path = tmp_path / "grouped.txt"
    path.write_text(
        "101,780,000.000,13,123,359.580,800.00,IRON PIPE\n",
        encoding="utf-8",
        newline="",
    )
    out = tmp_path / "out"
    out.mkdir()

    with pytest.raises(pnezd.PnezdError) as caught:
        _south_to_central(tmp_path, input_path=path, output_directory=out)

    message = str(caught.value)
    # Hand-derived: refusal names the file, the line, and the offending text.
    assert "grouped.txt" in message
    assert "line 1" in message
    assert "'780,000.000'" in message
    # Hand-derived: the literal reading is quoted back so the surveyor can see
    # what the program would otherwise have believed.
    assert "'780'" in message
    assert "'000.000'" in message
    # The property that matters: nothing was written.
    assert list(out.iterdir()) == []


def test_a_row_carrying_the_signature_with_no_second_reading_is_still_read():
    """Anti-vacuousness, and the limit of the rule.

    "A,1,2,100.0,x" carries the same textual signature - "2" is one-to-three
    digits and "100.0" is exactly three plus decimals - but joining them gives
    "A,1,2100.0,x", four fields whose elevation field is "x". "x" is not a
    number, so that reading is not well formed and there is no ambiguity to
    refuse: the literal reading is the only one.

    Without this test the refusal could be widened until it rejected ordinary
    files, and nothing would notice.
    """
    parsed = pnezd.parse_lines(["A,1,2,100.0,x"])
    row = parsed.rows[0]

    # Hand-derived from the five-way split: id A, N 1, E 2, Z 100.0, desc "x".
    assert row.point_id == "A"
    assert row.northing == 1.0
    assert row.easting == 2.0
    assert row.elevation == 100.0
    assert row.description == "x"


def test_an_ordinary_michigan_row_with_a_numeric_description_is_read():
    """The second anti-vacuousness case: a real coordinate, numeric description.

    "101,780000.000,13123359.580,800.00,500" has a bare number as its
    description (surveyors do use numeric feature codes). No grouping signature
    exists - the elevation "800.00" carries a decimal point, so it cannot be
    the leading group of a grouped number - so the row is read literally.
    """
    parsed = pnezd.parse_lines(["101,780000.000,13123359.580,800.00,500"])
    row = parsed.rows[0]

    # Hand-derived from the five-way split.
    assert row.northing == 780000.0
    assert row.easting == 13123359.58
    assert row.elevation == 800.0
    assert row.description == "500"


def test_the_reviewers_nan_elevation_row_is_refused_and_never_reaches_a_file(
    tmp_path,
):
    """The reviewer's other counterexample, end to end.

        101,780000.000,13123359.580,nan,IRON PIPE

    This row previously converted and WROTE a file, because every guard between
    the reader and the disk misses NaN specifically:

      * float("nan") parses, so the reader accepted it;
      * `value == 0.0` is False for NaN, so the absent-elevation branch that
        turns 0.00 into "not recorded" did not catch it either;
      * write_all's finiteness loop checks the northing and the easting only;
      * verify_round_trip re-parses the written "nan" happily.

    Hand-derived: math.isfinite(float("nan")) is False, so the reader now
    refuses at the elevation field, which is column 4.
    """
    path = tmp_path / "nanelev.txt"
    path.write_text(
        "101,780000.000,13123359.580,nan,IRON PIPE\n", encoding="utf-8", newline=""
    )
    out = tmp_path / "out"
    out.mkdir()

    with pytest.raises(pnezd.PnezdError) as caught:
        _south_to_central(tmp_path, input_path=path, output_directory=out)

    message = str(caught.value)
    # Hand-derived: names file, line, column and the offending text.
    assert "nanelev.txt" in message
    assert "line 1" in message
    assert "elevation" in message
    assert "'nan'" in message
    # It tells the surveyor what to do instead of a placeholder.
    assert "BLANK" in message
    # The property that matters: nothing was written.
    assert list(out.iterdir()) == []


def test_a_blank_elevation_is_still_the_way_to_say_not_recorded():
    """Anti-vacuousness for the refusal above: the sanctioned spelling works.

    The refusal message tells the surveyor to leave the field blank rather than
    filling it with a placeholder, so the blank must actually be accepted.
    """
    parsed = pnezd.parse_lines(["101,780000.000,13123359.580,,IRON PIPE"])

    # Hand-derived from the module docstring: blank means "not recorded".
    assert parsed.rows[0].elevation is None
    assert parsed.rows[0].elevation_was_zero is False


def test_a_quoted_field_of_commas_that_is_not_grouping_is_refused():
    """The comma strip is validated, not blind.

    _parse_number keeps its `.replace(",", "")` because it is NOT dead code for
    a QUOTED field - see the test below, where '"13,221,442.048"' arrives as one
    field with its commas intact. But stripping unconditionally would turn a
    quoted '"1,2"' into 12 without a word.

    Hand-derived: "1,2" fails the grouped-number pattern (a group after the
    first separator must be exactly three digits, and "2" is one), so it is
    refused rather than silently becoming twelve.
    """
    with pytest.raises(pnezd.PnezdError) as caught:
        pnezd.parse_lines(['101,"1,2",13123359.580,800.00,IP'], path="J.txt")

    message = str(caught.value)
    assert "northing" in message
    assert "'1,2'" in message
    assert "thousands separators" in message


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


def _dms_parts(text: str) -> tuple[str, int, int, float]:
    """Split "+00 14 58.30" into sign, degrees, minutes, seconds."""
    sign, rest = text[0], text[1:]
    degrees, minutes, seconds = rest.split(" ")
    return sign, int(degrees), int(minutes), float(seconds)


def test_angle_dms_needs_no_carry_guard_because_it_rounds_before_it_splits():
    """The two carry guards deleted from angle_dms could never fire.

    They were of the form "if the seconds rounded up to 60, borrow a minute".
    Hand-derived reason they are unreachable: the rounding is applied ONCE, to
    the total seconds, BEFORE either divmod. divmod's contract is that the
    remainder is strictly smaller than the divisor, so `remainder` is below 3600
    and `seconds` is below 60 by construction; and because the total was already
    rounded to `seconds_decimals` places, so is `seconds`, so rounding it again
    cannot move it. Neither boundary can be crossed after the split.

    Verified independently before deletion by a sweep of 88,612,997 angles - a
    dense pass at 1e-7 deg across the whole convergence domain, every
    0.01-arcsecond tick approached from both sides, values engineered onto the
    carry boundaries, and a random sample across all seven legal values of
    `seconds_decimals`. Neither guard was reached once.

    This test keeps a representative slice of that sweep live. It is not a test
    that the guards are gone; it is a test of the INVARIANT that made them
    pointless, and it fails if the rounding is ever moved after the split.
    """
    # -------------------------------------------------- engineered boundaries
    # The only values where a carry could arise: a hair under a whole minute
    # and a hair under a whole degree, at every whole degree across a domain
    # far wider than any convergence angle (Michigan's is under 3.4 deg).
    for whole in range(0, 91):
        for sub in (59.999, 59.99999, 59.9999999, 3599.999, 3599.9999999):
            for base in (whole * 3600.0, whole * 60.0):
                for degrees in ((base + sub) / 3600.0, -(base + sub) / 3600.0):
                    _, _, minutes, seconds = _dms_parts(fmt.angle_dms(degrees))
                    # Hand-derived: 60 minutes is one degree and 60 seconds is
                    # one minute, so neither may ever be printed.
                    assert minutes < 60, degrees
                    assert seconds < 60.0, degrees

    # ------------------------------------------------------------ tick sweep
    # Every representable 0.01-arcsecond output in [0, 0.05) deg, approached
    # from just below, exactly on, and just above.
    for ticks in range(0, 18_000):
        for nudge in (-1e-12, 0.0, 1e-12):
            degrees = (ticks / 100.0) / 3600.0 + nudge
            _, _, minutes, seconds = _dms_parts(fmt.angle_dms(degrees))
            assert minutes < 60, degrees
            assert seconds < 60.0, degrees

    # -------------------------------------------- every seconds_decimals used
    for decimals in range(0, 7):
        for sub in (59.999999, 3599.999999):
            text = fmt.angle_dms(sub / 3600.0, seconds_decimals=decimals)
            _, _, minutes, seconds = _dms_parts(text)
            assert minutes < 60, (decimals, sub)
            assert seconds < 60.0, (decimals, sub)


def test_angle_dms_still_carries_after_the_guards_were_deleted():
    """The behaviour the deleted guards appeared to provide is still provided.

    Deleting a dead check is only safe if the live mechanism is pinned, so this
    asserts the carry itself rather than the absence of the guards.

    Hand-derived: 59.999 arcsec rounds to 60.00 arcsec = exactly 1 minute, so
    divmod(60.0, 60.0) gives 1 minute and 0.00 seconds - the carry, produced by
    the rounding order and not by any guard. Likewise 3599.999 arcsec rounds to
    3600.00 = exactly 1 degree, so divmod(3600.0, 3600.0) gives 1 degree, 0
    minutes, 0.00 seconds.
    """
    assert fmt.angle_dms(59.999 / 3600.0) == "+00 01 00.00"
    assert fmt.angle_dms(3599.999 / 3600.0) == "+01 00 00.00"
    assert fmt.angle_dms(-3599.999 / 3600.0) == "-01 00 00.00"


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


def test_verify_round_trip_now_catches_the_text_nan(tmp_path):
    """REWRITTEN. This test previously pinned the gap as current behaviour.

    exports.verify_round_trip's docstring has always claimed that a value
    formatted as "nan" "would produce a file that looks written and imports
    wrongly" - implying the check stops it. It did not, because float("nan")
    succeeds and the reader it round-trips through accepted the cell as a
    perfectly good northing. The docstring described teeth the code lacked.

    Fixing the READER gives the check the teeth its docstring claims, because
    verify_round_trip re-parses through that same reader. So the old pin is
    rewritten to assert the refusal rather than the gap.

    Hand-derived: pnezd._parse_number now rejects any value for which
    math.isfinite is False, so parse_lines raises PnezdError on the "nan" cell,
    which verify_round_trip converts into a WriteError.
    """
    result = _south_to_central(tmp_path)
    rows = exports.clean_pnezd_rows(result)
    rows[0] = [rows[0][0], "nan", rows[0][2], rows[0][3], rows[0][4]]

    with pytest.raises(WriteError) as caught:
        exports.verify_round_trip(rows, result)

    message = str(caught.value)
    # Hand-derived: the WriteError wraps the reader's own refusal text.
    assert "cannot be read back by its own reader" in message
    assert "'nan'" in message


def test_the_reader_refuses_the_text_nan_as_a_coordinate():
    """REWRITTEN. This test previously pinned "nan" and "inf" as ACCEPTED.

    It asserted math.isnan(rows[0].northing) - i.e. that a non-finite value
    entered the core from a coordinate file. That is the root of the defect and
    is now refused at the one entry point (DESIGN.md s.7, "one entry point per
    data path; loaders validate as strictly as the UI").

    Hand-derived: math.isfinite(float("nan")) is False and
    math.isfinite(float("inf")) is False, so the first numeric field of the row
    fails the finiteness check and the row is refused before any of it is used.
    """
    with pytest.raises(pnezd.PnezdError) as caught:
        pnezd.parse_lines(["101,nan,inf,3,D"], path="J.txt")

    message = str(caught.value)
    # Hand-derived: northing is field 1, so it is the field named first.
    assert "northing" in message
    assert "'nan'" in message
    assert "J.txt" in message
    assert "line 1" in message


def test_every_numeric_column_refuses_every_non_finite_spelling():
    """All three numeric columns, all four spellings float() accepts.

    Anti-vacuousness for the test above, which only exercises columns 2 and 3.
    float() accepts "nan", "inf", "-inf" and "infinity" case-insensitively;
    each is placed in each numeric column in turn and each must be refused.
    """
    spellings = ["nan", "NaN", "inf", "-inf", "infinity", "-Infinity"]
    # Hand-derived: column index 1 is northing, 2 easting, 3 elevation.
    columns = {1: "northing", 2: "easting", 3: "elevation"}

    for index, field_name in columns.items():
        for spelling in spellings:
            cells = ["101", "780000.000", "13123359.580", "800.00", "IRON PIPE"]
            cells[index] = spelling
            row = ",".join(cells)

            with pytest.raises(pnezd.PnezdError) as caught:
                pnezd.parse_lines([row], path="J.txt")

            message = str(caught.value)
            assert field_name in message, (row, message)
            assert repr(spelling) in message, (row, message)

    # Anti-vacuousness: the same row with real numbers is accepted, so the
    # refusals above are about the spellings and not about the row shape.
    ok = pnezd.parse_lines(["101,780000.000,13123359.580,800.00,IRON PIPE"])
    assert ok.rows[0].northing == 780000.0


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


class _FutureWarningCode(Enum):
    """Stands in for a WarningCode added after this report section was written.

    A real one cannot be used, because Python enums cannot be extended and both
    codes that exist today have headings - which is exactly why the defect was
    latent. This reproduces the situation faithfully: a code object that
    report._WARNING_HEADINGS has never heard of, attached to a real warning on a
    real converted point.
    """

    GEOID_TILE_EDGE = "geoid-tile-edge"


def test_the_report_prints_a_warning_whose_code_has_no_heading(tmp_path):
    """A warning counted in the total must also be shown.

    build_report used to iterate _WARNING_HEADINGS rather than the warnings, so
    a warning kind with no heading was included in the "N warning(s)" count at
    the head of the section and then never printed underneath it. The surveyor
    would be told something was wrong and not told what - the worst shape a
    warning can take, because it cannot be acted on and cannot be dismissed.

    Hand-derived: one point is given one extra warning carrying a code that has
    no heading, so the section's total must read 1 more than the job's own
    warnings, and the new warning's message text must appear in the body.
    """
    result = _south_to_central(tmp_path)
    before = len(result.warnings)

    unheaded = ConversionWarning(
        code=_FutureWarningCode.GEOID_TILE_EDGE,
        message="point 101 lies within one grid cell of the geoid tile edge",
    )
    first = dataclasses.replace(
        result.points[0], warnings=result.points[0].warnings + (unheaded,)
    )
    result = dataclasses.replace(result, points=(first,) + result.points[1:])

    # Hand-derived: the code is genuinely unknown to the report's table, or the
    # test proves nothing.
    assert _FutureWarningCode.GEOID_TILE_EDGE not in report._WARNING_HEADINGS

    text = report.build_report(result)

    # Hand-derived: exactly one warning was added.
    assert f"{before + 1} warning(s)" in text
    # The point of the whole test: the message is actually printed.
    assert "within one grid cell of the geoid tile edge" in text
    # And it is introduced by a heading derived from the code itself, since the
    # table has none: "geoid-tile-edge" -> "GEOID TILE EDGE".
    assert "GEOID TILE EDGE (1 point(s))" in text


def test_the_report_still_uses_the_written_heading_when_there_is_one(tmp_path):
    """Anti-vacuousness for the test above.

    If _warning_heading fell back to the raw code for every warning, the test
    above would still pass while the report got worse. This pins that a code
    WITH a registered heading still gets it.

    Hand-derived: SAMPLE_PNEZD's CP-4 sits about 123,000 feet west of the
    others, far enough out that the easting guard fires - so this job raises the
    EASTING_UNLIKE_SELECTED_ZONE warning, whose heading is registered.
    """
    path = tmp_path / "farwest.txt"
    # Hand-derived: Michigan South's false easting is 13,123,359.58 int. ft.
    # 400 km is 1,312,335.958 int. ft, so an easting 2,000,000 ft below the
    # false easting is outside the window the guard uses.
    path.write_text(
        "101,780000.000,11123359.580,800.00,WAY WEST\n", encoding="utf-8", newline=""
    )
    result = _south_to_central(tmp_path, input_path=path)

    text = report.build_report(result)

    heading = report._WARNING_HEADINGS[WarningCode.EASTING_UNLIKE_SELECTED_ZONE]
    # Hand-derived: the registered heading, not the raw code text.
    assert heading in text
    assert "EASTING UNLIKE SELECTED ZONE" not in text


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


# ==========================================================================
# job.py - the reference frame a geodetic input file is read as.
# Interim review gate finding 1 (docs/DESIGN.md amendment #11).
# ==========================================================================


GEODETIC_INPUT = "101,42.73250000,-84.55550000,800.00,IRON PIPE\n"
"""One point, in the layout a geodetic input file uses: the second and third
columns are latitude and longitude, not northing and easting. Lansing, the
reviewer's counterexample position."""


def _geodetic_job(tmp_path: Path, **overrides) -> JobSettings:
    path = tmp_path / "geodetic.txt"
    path.write_text(GEODETIC_INPUT, encoding="utf-8", newline="")
    return JobSettings(
        input_path=path,
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        **overrides,
    )


def test_a_geodetic_job_states_the_frame_it_reads_the_file_in(tmp_path):
    """The setting exists and is visible, rather than being implied.

    NAD83(2011) is the frame every zone in the registry is in (zones.py), so it
    is the only value that can produce a conversion today - but it is recorded
    as a choice on the settings, because the job record has to be able to say
    which frame the latitudes and longitudes were interpreted as.
    """
    settings = _geodetic_job(tmp_path)

    assert settings.geodetic_frame is NAD83_2011
    assert settings.geodetic_frame.code == "NAD83(2011)"

    result = run(settings)
    # The frame travels onto the conversion record, not just the settings.
    assert result.points[0].conversion.frame is NAD83_2011


def test_a_geodetic_job_declared_natrf2022_is_refused_end_to_end(tmp_path):
    """The application layer's default cannot be used to sneak past the core.

    Setting the frame to NATRF2022 is the only way to reach a mismatch today,
    and it must fail loudly at the point of conversion rather than producing
    Michigan South coordinates computed as though the file were NAD 83. The
    reviewer measured that untransformed answer at N = 136920.027586723 m,
    E = 3984537.119005890 m, which is exactly what a NAD 83 reading gives - the
    frames differ by one to two metres and nothing in the numbers shows it.
    """
    settings = _geodetic_job(tmp_path, geodetic_frame=NATRF2022)

    with pytest.raises(FrameMismatchError, match="NATRF2022"):
        run(settings)


def test_a_geodetic_job_record_states_the_frame_it_read_the_file_as(tmp_path):
    """Closing the second half of interim-gate finding 1 (docs/DESIGN.md #11).

    The core now REFUSES a cross-frame geodetic input. That protects the
    computation, but a job record still has to say which frame it read the file
    as - a latitude and longitude carry no frame in their own columns, and
    reading NATRF2022 positions as NAD 83 is a one-to-two metre error that looks
    entirely ordinary on the page.

    Hand-derived: 42.73250000 N, -84.55550000 W in Michigan South is
    N = 136920.027586723 m, E = 3984537.119005890 m (the interim reviewer's own
    figures for this position). In International feet, 0.3048 m exactly:
        136920.027586723 / 0.3048 = 449212.6889 ift
        3984537.119005890 / 0.3048 = 13072628.3432 ift
    """
    source = tmp_path / "opus.csv"
    source.write_text(
        "101,42.73250000,-84.55550000,812.40,OPUS SOLUTION\n", encoding="utf-8"
    )

    settings = JobSettings(
        input_path=source,
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=NAD83_2011,
    )
    result = run(settings)

    # The conversion itself, against the reviewer's metre values converted above.
    point = result.points[0]
    assert point.output_northing == pytest.approx(449212.6889, abs=0.001)
    assert point.output_easting == pytest.approx(13072628.3432, abs=0.001)
    assert point.conversion.frame is NAD83_2011

    text = report.build_report(result)
    assert "Reference frame    NAD83(2011)" in text
    assert "read as positions in this frame" in text

    # And the short longitude wording the owner chose (docs/DESIGN.md #17)
    # reaches the record, not just the dropdown.
    assert "Longitude          negative west (-84.37)" in text
    assert "as used by" not in text


def test_a_zone_to_zone_record_does_not_claim_a_geodetic_frame(tmp_path):
    """The frame line belongs only where a geodetic file was actually read.

    A zone-to-zone job takes its frame from the zones themselves, which the
    COORDINATE SYSTEMS section already states per zone. Repeating it as an
    input-frame line would imply the user chose something they never chose.
    """
    result = _south_to_central(tmp_path)
    lines = report.build_report(result).splitlines()

    # The input-frame line starts at column 0; the per-zone frame lines are
    # indented two spaces inside their zone block. Checked line by line rather
    # than by substring, because "Reference frame    " is a prefix of the zone
    # block's own "Reference frame           " and a substring test passes
    # against the wrong line.
    assert not [line for line in lines if line.startswith("Reference frame")]

    # The zone blocks still carry theirs, one per zone in the conversion.
    indented = [line for line in lines if line.strip().startswith("Reference frame")]
    assert len(indented) == 2
    for line in indented:
        assert line.startswith("  ")
        assert "NAD83(2011)" in line
