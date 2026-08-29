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
import zipfile
from enum import Enum
from pathlib import Path

import pytest

from tests.conftest import archive_members, extract_member, member_text

from michspc import job as jobmod
from michspc.fileio import exports, pnezd, report
from michspc.fileio import formatting as fmt
from michspc.fileio.writers import (
    WriteError,
    atomic_write_text,
    staged_write,
    write_csv_rows,
)
from michspc.job import (
    Direction,
    JobSettings,
    LongitudeConvention,
    file_sha256,
    run,
)
from michspc.spc.frames import (
    NAD83_2011,
    NATRF2022,
    FrameMismatchError,
    FrameTransformationUnavailableError,
)
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
# pnezd.parse_typed_point - the single-point seam (docs/DESIGN.md #26)
#
# The constraint the whole feature is built on: a typed point and a file row
# must be incapable of disagreeing, so the typed values go through this same
# reader. These tests therefore assert that the seam ADDS nothing - no parsing,
# no validation, no convention of its own - and that the one thing it does add,
# unconditional quoting, is load-bearing.
# ==========================================================================


def _typed(first, second, elevation, source=pnezd.TYPED_POINT_SOURCE_GRID):
    """Shorthand for the seam under test, at its grid-entry source."""
    return pnezd.parse_typed_point(first, second, elevation, source=source)


def _unquoted_typed_line(first, second, elevation):
    """What the seam would build if it did NOT quote. The falsification target.

    Identical to ``parse_typed_point``'s own construction except for the
    quoting, so a test that passes against this one is not testing the quoting.
    """
    return ",".join([pnezd.TYPED_POINT_ID, first, second, elevation])


def test_parse_typed_point_yields_one_row_through_the_reader():
    """Four quoted fields, one line, one row - and no digest.

    Hand-derived from the construction: the line is
    '"1","780000.000","13123359.580","800.00"', which csv reads as exactly four
    fields, so parse_lines takes the fourth as the elevation and leaves the
    description empty (fields[4:] is the empty list).

    sha256 is None because parse_lines was handed already-decoded text: no bytes
    passed through this program, so there is nothing it can honestly certify
    (PnezdFile.sha256's own docstring).
    """
    parsed = _typed("780000.000", "13123359.580", "800.00")

    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    # Hand-derived: the four fields, verbatim, read as float() reads them.
    assert row.northing == 780000.0
    assert row.easting == 13123359.58
    assert row.elevation == 800.0
    assert row.description == ""
    assert parsed.sha256 is None


def test_parse_typed_point_gives_the_point_the_identifier_the_reader_needs():
    """TYPED_POINT_ID is "1", and parse_lines refuses a blank identifier.

    It also reaches the screen: job._convert_row builds every warning's context
    as f"point {row.point_id}", so an empty identifier would surface as
    "point : an easting of ...".
    """
    parsed = _typed("780000.000", "13123359.580", "800.00")

    # Hand-derived from the module constant.
    assert pnezd.TYPED_POINT_ID == "1"
    assert parsed.rows[0].point_id == "1"


@pytest.mark.parametrize(
    "text, expected_elevation, expected_was_zero",
    [
        # The reader's own convention, unchanged: blank is absent and was not a
        # zero; an explicit "0.00" is absent and WAS a zero; anything else is
        # the number itself.
        ("", None, False),
        ("0.00", None, True),
        ("812.40", 812.4, False),
    ],
)
def test_parse_typed_point_uses_the_readers_elevation_convention(
    text, expected_elevation, expected_was_zero
):
    """No special case in the seam: _parse_elevation already decides all three.

    Hand-derived from pnezd._parse_elevation: "" is in _ABSENT_ELEVATION_TEXT so
    it returns (None, False); "0.00" parses to 0.0 and hits the `value == 0.0`
    branch, returning (None, True); "812.40" parses to 812.4 and is returned as
    itself with the flag False.
    """
    row = _typed("780000.000", "13123359.580", text).rows[0]

    assert row.elevation == expected_elevation
    assert row.elevation_was_zero is expected_was_zero


@pytest.mark.parametrize(
    "source",
    [pnezd.TYPED_POINT_SOURCE_GRID, pnezd.TYPED_POINT_SOURCE_GEODETIC],
)
def test_parse_typed_point_refusals_name_the_typed_source(source):
    """A refusal must not say "<text>", and must name the right columns.

    parse_lines writes `path` at the head of every refusal, so passing the
    typed source is what makes the sentence describe the entry layout the
    surveyor is actually looking at.
    """
    with pytest.raises(pnezd.PnezdError) as raised:
        pnezd.parse_typed_point("not a number", "13123359.580", "800.00", source=source)

    message = str(raised.value)
    # Hand-derived: parse_lines interpolates `path` first, then ", line 1: ".
    assert message.startswith(f"{source}, line 1:")
    assert "<text>" not in message


def test_parse_typed_point_names_the_geodetic_columns_when_that_is_the_layout():
    """The two source constants differ in exactly the columns they name.

    A surveyor who typed a longitude must not be told his "easting" is wrong -
    which is the whole reason `source` is keyword-only with no default.
    """
    # Hand-derived from the constants themselves.
    assert pnezd.TYPED_POINT_SOURCE_GRID == (
        "The typed point (northing, easting, elevation)"
    )
    assert pnezd.TYPED_POINT_SOURCE_GEODETIC == (
        "The typed point (latitude, longitude, elevation)"
    )


def test_parse_typed_point_has_no_default_source():
    """Keyword-only AND required: omitting it is a TypeError, not a guess."""
    with pytest.raises(TypeError):
        pnezd.parse_typed_point("780000.000", "13123359.580", "800.00")

    # And it cannot be passed positionally either, so no call site can supply
    # it by accident in the wrong slot.
    with pytest.raises(TypeError):
        pnezd.parse_typed_point(
            "780000.000", "13123359.580", "800.00", pnezd.TYPED_POINT_SOURCE_GRID
        )


@pytest.mark.parametrize(
    "first, second, elevation, expected_n, expected_e, expected_z",
    [
        # A grouped northing. 780,000.000 with the separators removed is
        # 780000.000, and the other two fields are untouched.
        ("780,000.000", "13123359.580", "800.00", 780000.0, 13123359.58, 800.0),
        # A grouped easting. 13,123,359.580 -> 13123359.580.
        ("780000.000", "13,123,359.580", "800.00", 780000.0, 13123359.58, 800.0),
        # A grouped elevation. 1,800.00 -> 1800.00.
        ("780000.000", "13123359.580", "1,800.00", 780000.0, 13123359.58, 1800.0),
    ],
)
def test_a_comma_in_a_typed_field_never_shifts_a_column(
    first, second, elevation, expected_n, expected_e, expected_z
):
    """The quoting, stated as the property it buys.

    A typed field is one field by construction - a text box cannot hold a
    delimiter - so a comma inside one is a thousands separator and nothing else.
    Quoted, csv keeps the field whole and the comma survives into
    _parse_number's grouped-number branch, which honours it. Every value below
    is hand-derived by deleting the separators, which is exactly what
    _GROUPED_NUMBER licenses.
    """
    row = _typed(first, second, elevation).rows[0]

    assert row.northing == expected_n
    assert row.easting == expected_e
    assert row.elevation == expected_z


def test_without_the_quoting_a_typed_grouped_northing_shifts_every_column():
    """The falsification: the same three fields, built unquoted.

    Run against ``_unquoted_typed_line`` on 2026-08-07, this is what came back
    for a typed northing of "780,000.000", easting "13221442.048" and a blank
    elevation - the amendment's own counterexample:

        line     '1,780,000.000,13221442.048,'
        parsed   N=780.0  E=0.0  Z=13221442.048  desc=''

    A northing 779,220 feet from the one the surveyor typed, an easting of
    zero, and the easting sitting in the elevation column - accepted without a
    murmur. _refuse_ambiguous_grouping cannot catch it: its second condition is
    a description beginning with a bare number, and a typed point's description
    is empty.

    The other unquoted combinations were refused rather than mis-read, with the
    ambiguous-grouping message - which is still wrong, because the quoted
    builder ACCEPTS all three and reads them exactly as typed (the test above).
    So the quoting is not defence-in-depth; it is what makes a grouped typed
    number mean what it says.
    """
    shifted = pnezd.parse_lines(
        [_unquoted_typed_line("780,000.000", "13221442.048", "")],
        path="<unquoted builder>",
    ).rows[0]

    # Hand-derived from the csv split of '1,780,000.000,13221442.048,':
    # fields are ['1', '780', '000.000', '13221442.048', ''].
    assert shifted.northing == 780.0
    assert shifted.easting == 0.0
    assert shifted.elevation == 13221442.048

    # And the seam itself, on the same three fields, is not fooled.
    correct = _typed("780,000.000", "13221442.048", "").rows[0]
    assert correct.northing == 780000.0
    assert correct.easting == 13221442.048
    assert correct.elevation is None


def test_parse_typed_point_refuses_a_comma_that_is_not_thousands_grouping():
    """"1,2" is quoted, survives csv whole, and fails _GROUPED_NUMBER.

    The reader's own teaching message is what must appear - the seam adds no
    wording of its own, and stripping the comma to make 12 is exactly the
    silent wrong number this program exists to prevent.
    """
    with pytest.raises(pnezd.PnezdError) as raised:
        _typed("1,2", "13123359.580", "800.00")

    message = str(raised.value)
    # Hand-derived from _parse_number's grouped-number refusal.
    assert "thousands separators" in message
    assert "13,221,442.048" in message
    assert "northing" in message


@pytest.mark.parametrize("text", ["nan", "inf", "-inf", "infinity", "INF", "NaN"])
def test_parse_typed_point_refuses_nan_and_infinity(text):
    """float() accepts all of these; none of them is a position.

    Refused by _parse_number's math.isfinite check, at the one entry point, for
    a typed point exactly as for a file row.
    """
    with pytest.raises(pnezd.PnezdError) as raised:
        _typed(text, "13123359.580", "800.00")

    # Hand-derived from _parse_number's non-finite refusal wording.
    assert "not a usable number" in str(raised.value)


def test_parse_typed_point_doubles_an_embedded_double_quote():
    """CSV's own escape, so a quote inside a typed field cannot open a field.

    Not reachable from a numeric entry box, but the quoting rule is
    unconditional and must be correct for whatever text arrives. The field
    below carries both a quote and a comma, which is what makes the test bite:
    written raw it would be '1"2,3', which csv splits at the comma into '1"2'
    and '3' and the row shifts one column right. Doubled and quoted it is
    '"1""2,3"', which csv reads back as the single field 1"2,3.

    So the assertion is that the refusal names the WHOLE typed text. It can
    only do that if the field survived as one field.
    """
    with pytest.raises(pnezd.PnezdError) as raised:
        _typed('1"2,3', "13123359.580", "800.00")

    message = str(raised.value)
    # Hand-derived from _parse_number's grouped-number refusal, which is what a
    # field containing a comma reaches: it quotes `cleaned` back verbatim.
    assert repr('1"2,3') in message
    # Not a quoting complaint - that is what a broken escape would produce.
    assert "malformed" not in message


# ==========================================================================
# The pathless job: input_path and output_directory as Path | None
#
# Four reads are guarded, each raising its own layer's error and saying why.
# Every test below has an anti-vacuousness half: the SAME result with real
# paths must go through, or the guard would be indistinguishable from the
# function being broken.
# ==========================================================================


def _typed_zone_to_zone(**overrides) -> jobmod.JobResult:
    """A one-point South -> Central job from a typed point and no files."""
    source = overrides.pop(
        "source",
        _typed("780000.000", "13123359.580", "800.00"),
    )
    settings = JobSettings(
        input_path=overrides.pop("input_path", None),
        output_directory=overrides.pop("output_directory", None),
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_SOUTH,
        target_zone=MI_CENTRAL,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=None,
        **overrides,
    )
    return run(settings, source=source)


def test_a_typed_point_converts_with_no_paths_at_all():
    """The property the whole change exists for: None is a usable statement."""
    result = _typed_zone_to_zone()

    assert result.settings.input_path is None
    assert result.settings.output_directory is None
    assert len(result.points) == 1
    # No bytes were read, so nothing is certified - see JobResult.input_sha256.
    assert result.input_sha256 is None


def test_run_with_no_source_and_no_input_path_names_parse_typed_point():
    """Refused rather than defaulted: there is nothing to read and nothing to
    convert, and a placeholder path would send pnezd.read at a file nobody
    named."""
    settings = JobSettings(
        input_path=None,
        output_directory=None,
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_SOUTH,
        target_zone=MI_CENTRAL,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=None,
    )

    with pytest.raises(ValueError) as raised:
        run(settings, source=None)

    message = str(raised.value)
    assert "parse_typed_point" in message
    assert "nothing to convert" in message


def test_run_with_no_input_path_but_a_source_is_fine(tmp_path):
    """Anti-vacuousness for the guard above: the same settings, with rows."""
    result = run(
        JobSettings(
            input_path=None,
            output_directory=None,
            direction=Direction.ZONE_TO_ZONE,
            source_zone=MI_SOUTH,
            target_zone=MI_CENTRAL,
            input_unit=INTERNATIONAL_FEET,
            output_unit=INTERNATIONAL_FEET,
            longitude_convention=None,
        ),
        source=_typed("780000.000", "13123359.580", "800.00"),
    )

    assert len(result.points) == 1


def test_output_stem_refuses_a_job_that_came_from_no_file(tmp_path):
    """Every member of the archive is named after the input file."""
    with pytest.raises(WriteError) as raised:
        exports.output_stem(_typed_zone_to_zone())

    assert "input_path is None" in str(raised.value)

    # Anti-vacuousness: the same job, given a real path, is named as usual.
    named = _typed_zone_to_zone(
        input_path=tmp_path / "24-118-topo.txt",
        output_directory=tmp_path / "out",
    )
    # Hand-derived from output_stem: "<input stem>_<target zone abbrev>", and
    # MI_CENTRAL's abbreviation is what the registry carries.
    assert exports.output_stem(named) == f"24-118-topo_{MI_CENTRAL.abbrev}"


def test_archive_path_refuses_a_job_with_no_output_folder(tmp_path):
    """Refused rather than falling back on the working directory."""
    with pytest.raises(WriteError) as raised:
        exports.archive_path(_typed_zone_to_zone(input_path=tmp_path / "job.txt"))

    assert "output_directory is None" in str(raised.value)

    # Anti-vacuousness: with a folder, the deliverable is named.
    named = _typed_zone_to_zone(
        input_path=tmp_path / "job.txt", output_directory=tmp_path / "out"
    )
    assert exports.archive_path(named) == tmp_path / "out" / (
        f"job_{MI_CENTRAL.abbrev}.zip"
    )


def test_destination_paths_refuses_a_pathless_job(tmp_path):
    """destination_paths reaches both guards through archive_path/output_stem.

    Checked rather than assumed: this is the function the GUI's overwrite check
    calls, so a None slipping through here would reach a path comparison.
    """
    with pytest.raises(WriteError):
        exports.destination_paths(_typed_zone_to_zone())

    # Anti-vacuousness: exactly one destination, the archive, when paths exist.
    named = _typed_zone_to_zone(
        input_path=tmp_path / "job.txt", output_directory=tmp_path / "out"
    )
    assert exports.destination_paths(named) == (exports.archive_path(named),)


def test_write_all_refuses_a_pathless_job_and_writes_nothing(tmp_path):
    """The deliverable path, end to end, on a job that has no deliverable."""
    with pytest.raises(WriteError):
        exports.write_all(_typed_zone_to_zone())

    # Nothing was created anywhere the test can see.
    assert list(tmp_path.iterdir()) == []

    # Anti-vacuousness: the same one-point job, given paths, writes its archive.
    named = _typed_zone_to_zone(
        input_path=tmp_path / "job.txt", output_directory=tmp_path / "out"
    )
    written = exports.write_all(named)
    assert written["archive"].exists()


def test_build_report_refuses_a_pathless_job(tmp_path):
    """The record names the file it read and the folder it wrote to.

    Neither line can be written from None, and neither may be substituted: this
    document is what a sealed survey is defended with.
    """
    with pytest.raises(ValueError) as raised:
        report.build_report(_typed_zone_to_zone())

    message = str(raised.value)
    assert "input_path=None" in message
    assert "output_directory=None" in message

    # Anti-vacuousness: with both paths the record is built and names them.
    named = _typed_zone_to_zone(
        input_path=tmp_path / "job.txt", output_directory=tmp_path / "out"
    )
    text = report.build_report(named)
    assert str(tmp_path / "job.txt") in text
    assert str(tmp_path / "out") in text


@pytest.mark.parametrize(
    "input_path, output_directory",
    [
        # Half-pathless is refused too, from whichever end is missing.
        (None, Path("out")),
        (Path("job.txt"), None),
    ],
)
def test_build_report_refuses_when_either_path_alone_is_missing(
    input_path, output_directory
):
    with pytest.raises(ValueError):
        report.build_report(
            _typed_zone_to_zone(
                input_path=input_path, output_directory=output_directory
            )
        )


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


# --------------------------------------------------------------------------
# latitude_dms / longitude_dms - the owner's format (docs/DESIGN.md #26)
#
# 42 deg 43' 57.00000" N and -84 deg 33' 19.80000" W, with the degree, minute
# and second symbols and a trailing HEMISPHERE LETTER. The letter is geographic
# and the numeric sign is the convention in force, which is what lets a
# zone-to-zone job - which never asks for a convention - show a longitude at
# all.
# --------------------------------------------------------------------------


def test_latitude_dms_is_the_owners_format():
    """42.7325 degrees north.

        42.7325 x 3600 = 153,837.0 seconds exactly
            42 x 3600 = 151,200; 0.7325 x 3600 = 2,637.0
        153,837.0 / 3600 = 42 degrees remainder 2,637.0
            42 x 3600 = 151,200; 153,837.0 - 151,200 = 2,637.0
        2,637.0 / 60 = 43 minutes remainder 57.0
            43 x 60 = 2,580; 2,637.0 - 2,580 = 57.0

    so 42 deg, 43 min, 57.00000 s, north of the equator and positive, giving no
    sign character - the owner's example verbatim.
    """
    # Hand-derived above.
    assert fmt.latitude_dms(42.7325) == "42°43'57.00000\"N"


def test_longitude_dms_is_the_owners_format():
    """-84.5555 degrees, i.e. 84.5555 west.

        84.5555 x 3600 = 304,399.8 seconds
            84 x 3600 = 302,400; 0.5555 x 3600 = 1,999.8
        304,399.8 / 3600 = 84 degrees remainder 1,999.8
        1,999.8 / 60 = 33 minutes remainder 19.8
            33 x 60 = 1,980; 1,999.8 - 1,980 = 19.8

    so 84 deg, 33 min, 19.80000 s, and the letter is W because the signed value
    is negative under the program's own negative-west storage.

    No minus sign: the letter already says west, and the owner corrected his
    own first sketch on exactly this point - a sign beside the letter reads as
    a double negative (docs/DESIGN.md amendment #26).
    """
    # Hand-derived above.
    assert fmt.longitude_dms(-84.5555) == "84°33'19.80000\"W"


def test_longitude_dms_is_convention_independent():
    """A DMS longitude is magnitude plus a letter, so no convention can move it.

    That is why ``longitude_dms`` takes no ``positive_west`` flag while its
    decimal-degrees sibling still must: a bare number has to pick a sign, and a
    magnitude-with-a-letter does not.
    """
    # Hand-derived from the derivation above.
    assert fmt.longitude_dms(-84.5555) == "84°33'19.80000\"W"

    # The flag does not exist, so the two conventions cannot disagree here.
    with pytest.raises(TypeError):
        fmt.longitude_dms(-84.5555, positive_west=True)

    # The decimal-degrees sibling still carries the convention, and still shows
    # a sign, which is the asymmetry this test exists to record.
    assert fmt.longitude(-84.5555) == "-84.55550000"
    assert fmt.longitude(-84.5555, positive_west=True) == "84.55550000"


def test_latitude_dms_south_of_the_equator_reads_s():
    """-20.5 degrees.

        20.5 x 3600 = 73,800 seconds exactly
        73,800 / 3600 = 20 degrees remainder 0
        0 / 60 = 0 minutes remainder 0
    """
    # Hand-derived above; negative, so the letter is S - and no sign, because
    # the letter already says south.
    assert fmt.latitude_dms(-20.5) == "20°30'00.00000\"S"


def test_longitude_dms_east_of_greenwich_reads_e():
    """+2.25 degrees, which under negative-west storage is genuinely east.

        2.25 x 3600 = 8,100 seconds exactly
        8,100 / 3600 = 2 degrees remainder 900
        900 / 60 = 15 minutes remainder 0

    The degrees field is two characters wide, so 2 prints as "02".
    """
    # Hand-derived above.
    assert fmt.longitude_dms(2.25) == "02°15'00.00000\"E"


def test_the_dms_formatters_of_none_are_not_available():
    """An absent value is "N/A" here as everywhere else - never a blank, never
    a plausible zero on the equator."""
    assert fmt.latitude_dms(None) == "N/A"
    assert fmt.longitude_dms(None) == "N/A"
    assert fmt.latitude_dms(None) == fmt.NOT_AVAILABLE
    assert fmt.longitude_dms(None) == fmt.NOT_AVAILABLE


def test_the_dms_formatters_default_to_five_decimals_of_a_second():
    """The owner asked for five (docs/DESIGN.md amendment #26).

    One second of latitude is about 30.9 m, so the fifth decimal is about
    0.3 mm - finer than any coordinate this program writes.
    """
    latitude = fmt.latitude_dms(42.7325)
    longitude = fmt.longitude_dms(-84.5555)

    # Hand-derived: the seconds field is everything between the apostrophe and
    # the double quote, and its fractional part must be exactly five digits.
    for text in (latitude, longitude):
        seconds = text.split("'")[1].split('"')[0]
        assert len(seconds.split(".")[1]) == 5


def test_dms_seconds_rounding_carries_into_the_next_minute():
    """The same mechanism angle_dms uses: round once, on the total, before both
    divmods.

    degrees = 59.9999999 / 3600, i.e. 59.9999999 seconds.
    round(59.9999999, 5) = 60.00000, which is a whole minute.
        60.00000 / 3600 = 0 degrees remainder 60.00000
        60.00000 / 60   = 1 minute remainder 0.00000
    so 0 degrees, 1 minute, 00.00000 seconds - never "00 deg 00' 60.00000"".
    """
    # Hand-derived above.
    assert fmt.latitude_dms(59.9999999 / 3600.0) == "00°01'00.00000\"N"
    assert "60.00000" not in fmt.latitude_dms(59.9999999 / 3600.0)


def test_dms_minute_rounding_carries_into_the_next_degree():
    """degrees = 3599.999999 / 3600, i.e. 3599.999999 seconds.

    round(3599.999999, 5) = 3600.00000 seconds.
        3600.00000 / 3600 = 1 degree remainder 0.00000
        0.00000 / 60      = 0 minutes remainder 0.00000
    """
    # Hand-derived above.
    result = fmt.longitude_dms(-3599.999999 / 3600.0)
    assert result == "01°00'00.00000\"W"
    assert "60" not in result


def test_the_dms_formatters_take_a_seconds_precision_like_angle_dms():
    """43.8 degrees at zero decimals.

        43.8 x 3600 = 157,680 seconds exactly
        157,680 / 3600 = 43 degrees remainder 0
        0 / 60 = 0 minutes remainder 0

    At seconds_decimals=0 the seconds field is two characters wide, matching
    angle_dms's own width rule.
    """
    # Hand-derived above.
    assert fmt.latitude_dms(43.8, seconds_decimals=0) == "43°48'00\"N"


def test_angle_dms_still_defaults_to_two_decimals_of_a_second():
    """Anti-regression for the DMS work above: angle_dms was not touched.

    exports.audit_rows reads it for the two convergence columns (the "Source
    convergence" and "Convergence" cells) and the job record reads it too, so a
    changed default here would silently reformat both of those files.
    """
    import inspect

    signature = inspect.signature(fmt.angle_dms)
    # Hand-derived from formatting.py's declaration: seconds_decimals = 2.
    assert signature.parameters["seconds_decimals"].default == 2
    # And the string it produces, which is what the two files actually carry.
    assert fmt.angle_dms(0.25) == "+00 15 00.00"


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
        longitude_convention=None,
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
        longitude_convention=None,
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
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
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
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
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


def test_longitude_convention_has_no_default_value(tmp_path):
    """DESIGN.md section 7: "selected by the user with no default".

    The enforcement is on ``JobSettings``, which is what a caller actually
    constructs; the enum having no designated default member proves nothing on
    its own, which is what the predecessor of this test asserted. Until this
    was fixed ``JobSettings`` silently supplied NEGATIVE_WEST, and the closing
    gate measured the consequence: a geodetic input file holding a positive-west
    84.5555 converted as though it read -84.5555 landed 11,634,618.748 m from
    the true position, carrying nothing louder than an outside-zone-extent
    warning.

    Omitting a field with no default is a TypeError from the generated
    ``__init__`` - the dataclass machinery is the enforcement, so this asserts
    on the omitted field's name rather than on any message we wrote.
    """
    with pytest.raises(TypeError) as caught:
        JobSettings(
            input_path=tmp_path / "in.txt",
            output_directory=tmp_path / "out",
            direction=Direction.GEODETIC_TO_ZONE,
            source_zone=None,
            target_zone=MI_SOUTH,
            input_unit=INTERNATIONAL_FEET,
            output_unit=INTERNATIONAL_FEET,
        )

    assert "longitude_convention" in str(caught.value)

    # Hand-derived: exactly the two conventions in the enum's docstring, and
    # neither of them is reachable without being named.
    assert len(list(LongitudeConvention)) == 2
    assert LongitudeConvention.POSITIVE_WEST is not LongitudeConvention.NEGATIVE_WEST


def test_a_geodetic_job_refuses_a_settings_object_that_never_stated_the_convention(
    tmp_path,
):
    """``None`` is only sayable by a job that never consults the convention.

    A pure zone-to-zone job has grid coordinates on both ends and no longitude
    anywhere, so it states None (michspc.gui.window builds it that way). Any
    direction with geodetic coordinates on either end that arrives with None is
    refused rather than defaulted - the same rule as the field itself, at the
    only layer that can tell the directions apart.
    """
    settings = JobSettings(
        input_path=_write_sample(tmp_path),
        output_directory=tmp_path / "out",
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=None,
    )

    with pytest.raises(ValueError) as caught:
        run(settings)

    message = str(caught.value)
    assert "longitude sign convention" in message
    assert "no default" in message
    assert "340 miles" in message


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


def test_a_job_with_no_geoid_model_reports_no_model_and_no_factors(tmp_path):
    """``geoid_model=None`` is the statement ``apply_geoid=False`` used to make.

    WP-V5 replaced the bool with the registry record
    (docs/PLAN-vertical-datums.md section 3.5); ``None`` must behave exactly as
    the disabled bool did - no model named, no grid loaded, no elevation or
    combined factors - while the horizontal conversion is untouched. No
    interface offers None (the owner's "no none"); it is a capability of the
    core, and this test plus the report test below are what keep it honest.
    """
    result = _south_to_central(tmp_path, geoid_model=None)

    # Hand-derived from run(): grid is None, so geoid_height stays None for
    # every point and factors_at short-circuits to None factors.
    assert result.geoid_model is None
    assert result.combined_factors == ()
    for point in result.points:
        assert point.factors.elevation_factor is None
        # ...but the horizontal conversion is untouched.
        assert math.isfinite(point.output_northing)
        assert math.isfinite(point.output_easting)

    # And the job record says so, in the words report.py has always used for
    # a geoid-less job - the branch WP-V5 must not orphan. What it must NOT
    # say is that any grid failed to "reach" these points: no grid was
    # consulted, and the old wording made exactly that false claim.
    text = report.build_report(result)
    assert "Geoid model        not applied" in text
    assert "no geoid model was applied to this job" in text
    assert "grid does not reach" not in text


def test_a_bool_in_the_geoid_model_field_is_refused_by_name(tmp_path):
    """``geoid_model=True`` is the exact habit apply_geoid leaves behind.

    Truthiness would accept it and the loader would then fail attribute by
    attribute somewhere inside the cache - an AttributeError nobody catches -
    so ``job.run`` refuses it by name before any grid is touched
    (the #11-finding-1 duck-typing class, at this field's likeliest call site).
    """
    with pytest.raises(TypeError) as raised:
        _south_to_central(tmp_path, geoid_model=True)

    message = str(raised.value)
    assert "GeoidModel" in message
    assert "True" in message
    assert "apply_geoid" in message


def test_a_job_refuses_a_geoid_model_the_registry_does_not_hold(tmp_path):
    """A hand-built record converts nowhere, and it refuses BEFORE converting.

    The loaders accept a hand-built ``GeoidModel`` on purpose - the suite
    reads tampered tiles through one - but ``report.py`` resolves the model
    back from the registry by name to cite its tile and digest. Without this
    gate a job carrying a non-registry record converted every point and then
    died at the record write with a bare ``KeyError``, the whole conversion
    discarded at the last step (WP-V5 review gate, LOW 1). Falsified by
    removing the membership check: this test fails and the reviewer's
    reproduction returns.

    A record equal to a registry one is NOT refused - membership is by
    equality, because identical facts are the same model. That branch is
    asserted too, so the gate cannot quietly tighten into identity.
    """
    import dataclasses

    from michspc.fileio import geoid

    imposter = dataclasses.replace(geoid.GEOID18_MODEL, name="GEOID18-LOCAL")
    with pytest.raises(ValueError) as raised:
        _south_to_central(tmp_path, geoid_model=imposter)

    message = str(raised.value)
    assert "GEOID18-LOCAL" in message
    assert "not a registered geoid model" in message
    assert "GEOID18" in message and "GEOID12B" in message

    # The equal-record branch: same facts, same model, accepted.
    rebuilt = dataclasses.replace(geoid.GEOID18_MODEL)
    assert rebuilt == geoid.GEOID18_MODEL
    result = _south_to_central(tmp_path, geoid_model=rebuilt)
    assert result.geoid_model == "GEOID18"


def test_a_geoid12b_job_reports_geoid12b_separations_not_geoid18s(tmp_path):
    """The registry choice reaches the audit CSV - the point of WP-V5.

    Position 47.1211 N, 88.5694 W (Houghton, Michigan North) is one of the 20
    frozen anchor positions where the two models differ at NGS's printed
    millimetre: NGS's own geoid service returns -33.828 m for GEOID12B and
    -33.796 m for GEOID18 (tests/fixtures/geoid12b_anchors.py and
    geoid_anchors.py, both captured from the live service). A job run with the
    GEOID12B record must put GEOID12B's figure in the audit file; the same job
    under the default must put GEOID18's. 32 mm apart, so the assertion cannot
    be satisfied by interpolation noise.
    """
    from michspc.fileio.geoid import GEOID12B_MODEL, GEOID18_MODEL
    from michspc.spc.zones import MI_NORTH

    def run_with(model, workspace):
        workspace.mkdir()
        path = workspace / "houghton.csv"
        path.write_text("1,47.1211,-88.5694,300.00,ANCHOR\n", encoding="utf-8")
        settings = JobSettings(
            input_path=path,
            output_directory=workspace / "out",
            direction=Direction.GEODETIC_TO_ZONE,
            source_zone=None,
            target_zone=MI_NORTH,
            input_unit=METERS,
            output_unit=METERS,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
            geoid_model=model,
        )
        return run(settings)

    result_12b = run_with(GEOID12B_MODEL, tmp_path / "g12b")
    result_18 = run_with(GEOID18_MODEL, tmp_path / "g18")

    assert result_12b.geoid_model == "GEOID12B"
    assert result_18.geoid_model == "GEOID18"

    def audit_geoid_cell(result, workspace):
        written = exports.write_all(result)
        audit = extract_member(written["archive"], "_full.csv", workspace / "unzipped")
        with open(audit, newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        header, data = rows[0], rows[1]
        return data[header.index("Geoid height (m)")]

    cell_12b = audit_geoid_cell(result_12b, tmp_path / "g12b")
    cell_18 = audit_geoid_cell(result_18, tmp_path / "g18")

    # Each audit value is its own model's NGS figure to the printed millimetre...
    assert float(cell_12b) == pytest.approx(-33.828, abs=0.001)
    assert float(cell_18) == pytest.approx(-33.796, abs=0.001)
    # ...and could not be the other model's: they are 32 mm apart here.
    assert abs(float(cell_12b) - float(cell_18)) > 0.02

    # The job record names the model AND its own tile and digest - a GEOID12B
    # job documented with GEOID18's file would cite the wrong evidence.
    text = report.build_report(result_12b)
    assert "GEOID12B, NGS grid tile g2012bu3.bin" in text
    assert "7ce1755c1e6ef8a1cc2909bd221e4a94fa46b2fbc33ebe4489a4973edd39b844" in text
    assert "g2018u3.bin" not in text


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

    Declaring the file's positions NATRF2022 while targeting an SPCS 83 zone
    must fail loudly rather than producing Michigan South coordinates computed
    as though the file were NAD 83. The interim reviewer measured that
    untransformed answer at N = 136920.027586723 m, E = 3984537.119005890 m,
    which is exactly what a NAD 83 reading gives - the frames differ by one to
    two metres and nothing in the numbers shows it.

    SUPERSEDED, not deleted (docs/DESIGN.md #62). Same job, same call; three
    things are now pinned that were not:

    * the narrower ``FrameTransformationUnavailableError``, which is a
      ``FrameMismatchError`` - so the class this test used to name still
      catches it;
    * the message facts a user acts on: the metre-scale stake, and that the
      gap is NGS's unpublished transformation rather than this program's
      schedule;
    * that the refusal happens BEFORE the file is read. It is a fact about the
      settings, so it must not depend on the file existing, let alone on which
      row the loop reaches.
    """
    settings = _geodetic_job(tmp_path, geodetic_frame=NATRF2022)

    with pytest.raises(FrameTransformationUnavailableError) as caught:
        run(settings)

    message = str(caught.value)
    assert "NATRF2022" in message
    assert "NAD83(2011)" in message
    assert "one to two metres" in message
    assert "NGS has not published" in message

    # Before the file is read: delete it and the same refusal arrives. A
    # per-row check would raise FileNotFoundError here instead.
    settings.input_path.unlink()
    with pytest.raises(FrameTransformationUnavailableError):
        run(settings)


def test_a_2022_zone_geodetic_job_on_the_default_frame_is_refused(tmp_path):
    """The default's new failure mode, pinned rather than discovered (#62).

    ``geodetic_frame`` defaults to NAD83(2011), which is right for every
    SPCS 83 job and wrong for every 2022-zone one. Wrong here must mean
    REFUSED: projecting NAD 83 latitudes and longitudes with a NATRF2022 zone's
    constants is amendment #11 finding 1 with a new zone list, one to two
    metres, invisible in the numbers.
    """
    from michspc.spc.zones import zone_by_code

    path = tmp_path / "geo.csv"
    path.write_text("101,42.80000000,-85.15000000,300.00,P\n", encoding="utf-8")
    settings = JobSettings(
        input_path=path,
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=zone_by_code("261008"),
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    assert settings.geodetic_frame is NAD83_2011

    with pytest.raises(FrameTransformationUnavailableError) as caught:
        run(settings)
    assert "NATRF2022" in str(caught.value)


def test_a_2022_zone_geodetic_job_on_its_own_frame_runs(tmp_path):
    """And the same job, stated honestly, converts (#62).

    The half that proves the refusal above is about the PAIR and not about the
    2022 zones: NATRF2022 is usable, so a job entirely within it runs end to
    end through ``job.run``, file and all. Without this, making the frames
    gate stricter could quietly make nineteen zones unreachable from a
    latitude and longitude and every test would still pass.
    """
    from michspc.spc.zones import zone_by_code

    zone = zone_by_code("261008")
    path = tmp_path / "natrf.csv"
    # Zone 261008's captured origin (tests/fixtures/spcs2022_engine_anchors.py,
    # raw/z261008_p1.html): 42.8 N, -85.15 W, which beta NCAT put at exactly
    # the zone's published false origin, N 228,600.000 m E 1,409,700.000 m.
    path.write_text("101,42.80000000,-85.15000000,300.00,ORIGIN\n", encoding="utf-8")

    settings = JobSettings(
        input_path=path,
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=zone,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=NATRF2022,
    )

    result = run(settings)

    assert result.points[0].conversion.frame is NATRF2022
    assert result.points[0].output_northing == pytest.approx(228600.0, abs=0.0005)
    assert result.points[0].output_easting == pytest.approx(1409700.0, abs=0.0005)


def test_a_zone_to_geodetic_job_must_name_the_frame_its_output_is_in(tmp_path):
    """The other direction of the settings gate (#62).

    ``ZONE_TO_GEODETIC`` writes latitudes and longitudes in the SOURCE ZONE's
    frame - there is no choice about it - so ``geodetic_frame`` must name that
    frame. A 2022-zone job left on the NAD83(2011) default would write
    NATRF2022 positions under a job record that says NAD83(2011): one to two
    metres, and the numbers look ordinary.

    Both halves pinned: the mismatch refuses, and the honest statement runs.
    """
    from michspc.spc.zones import zone_by_code

    zone = zone_by_code("261008")
    path = tmp_path / "grid.csv"
    path.write_text("101,228600.000,1409700.000,300.00,ORIGIN\n", encoding="utf-8")

    def settings_with(frame):
        return JobSettings(
            input_path=path,
            output_directory=tmp_path / "out",
            direction=Direction.ZONE_TO_GEODETIC,
            source_zone=zone,
            target_zone=None,
            input_unit=METERS,
            output_unit=METERS,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
            geodetic_frame=frame,
        )

    with pytest.raises(FrameTransformationUnavailableError) as caught:
        run(settings_with(NAD83_2011))
    assert "NATRF2022" in str(caught.value)

    result = run(settings_with(NATRF2022))
    assert result.points[0].output_northing == pytest.approx(42.8, abs=5e-8)
    # Negative west, the convention the job states, so the longitude is
    # written with its sign exactly as it was read.
    assert result.points[0].output_easting == pytest.approx(-85.15, abs=5e-8)


def test_a_job_may_not_use_a_unit_the_zone_does_not_publish(tmp_path):
    """The per-zone unit gate, the authoritative half of the owner's decision.

    ``Zone.allowed_units`` says what a coordinate in that zone may be written
    in. NGS publishes every SPCS2022 false origin in metres and international
    feet ONLY, and beta NCAT prints ``N/A`` for the US survey foot on every
    2022 zone; the survey foot is 2 ppm from the international foot, about 26
    feet at a four-million-metre easting, so a survey-foot 2022 coordinate
    could be checked against no published figure. The GUI will filter the
    selector (H6), but a filter a caller can bypass is not a rule, so the rule
    lives here, before the file is read.

    Each direction is pinned at the end the unit actually governs:

    * ``GEODETIC_TO_ZONE`` - the OUTPUT unit governs the target zone;
    * ``ZONE_TO_GEODETIC`` - the INPUT unit governs the source zone;
    * ``ZONE_TO_ZONE`` - both ends.
    """
    from michspc.spc.zones import zone_by_code

    zone = zone_by_code("261008")
    assert US_SURVEY_FEET not in zone.allowed_units

    geodetic = tmp_path / "geo.csv"
    geodetic.write_text("101,42.80000000,-85.15000000,300.00,P\n", encoding="utf-8")
    grid = tmp_path / "grid.csv"
    grid.write_text("101,228600.000,1409700.000,300.00,P\n", encoding="utf-8")

    into_the_zone = JobSettings(
        input_path=geodetic,
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=zone,
        input_unit=METERS,
        output_unit=US_SURVEY_FEET,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=NATRF2022,
    )
    with pytest.raises(ValueError) as caught:
        run(into_the_zone)
    message = str(caught.value)
    assert zone.name in message
    assert US_SURVEY_FEET.code in message
    # It names what the zone DOES publish, in the zone's own declared order,
    # and why - the citation basis rather than a bare "not allowed".
    assert "ift (International feet), m (meters)" in message
    assert "NCAT prints N/A for the" in message
    assert "2 ppm" in message

    out_of_the_zone = JobSettings(
        input_path=grid,
        output_directory=tmp_path / "out",
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=zone,
        target_zone=None,
        input_unit=US_SURVEY_FEET,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=NATRF2022,
    )
    with pytest.raises(ValueError, match=US_SURVEY_FEET.code):
        run(out_of_the_zone)

    zone_to_zone = JobSettings(
        input_path=grid,
        output_directory=tmp_path / "out",
        direction=Direction.ZONE_TO_ZONE,
        source_zone=zone,
        target_zone=zone_by_code("261009"),
        input_unit=METERS,
        output_unit=US_SURVEY_FEET,
        longitude_convention=None,
    )
    with pytest.raises(ValueError, match=US_SURVEY_FEET.code):
        run(zone_to_zone)


def test_the_unit_gate_leaves_every_unit_an_spcs83_zone_publishes_alone(tmp_path):
    """The gate must refuse only what the authority does not publish.

    All three units are legitimate on an SPCS 83 zone, including the US survey
    foot that a 2022 zone refuses, and every one of them must still run. A gate
    that refused a legitimate unit would break jobs that have been running
    since 0.1.0.
    """
    for unit in (INTERNATIONAL_FEET, US_SURVEY_FEET, METERS):
        assert unit in MI_SOUTH.allowed_units

    for index, unit in enumerate((INTERNATIONAL_FEET, US_SURVEY_FEET, METERS)):
        workspace = tmp_path / f"unit{index}"
        workspace.mkdir()
        path = workspace / "pts.csv"
        path.write_text("101,42.73250000,-84.55550000,812.40,P\n", encoding="utf-8")
        settings = JobSettings(
            input_path=path,
            output_directory=workspace / "out",
            direction=Direction.GEODETIC_TO_ZONE,
            source_zone=None,
            target_zone=MI_SOUTH,
            input_unit=unit,
            output_unit=unit,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        )
        assert run(settings).points[0].output_northing is not None


def test_the_unit_gate_does_not_read_a_unit_the_direction_never_applies(tmp_path):
    """The per-side rule, at the end it deliberately does NOT check.

    On ``GEODETIC_TO_ZONE`` the input unit governs only the Z column - there is
    no input zone whose grid it could be in - so a unit the TARGET zone does
    not publish must not be refused on the input side. Refusing it would block
    a legitimate job: a 2022-zone job whose elevations arrived in survey feet.
    The mirror holds on ``ZONE_TO_GEODETIC``, where the output unit governs
    only the Z column.
    """
    from michspc.spc.zones import zone_by_code

    zone = zone_by_code("261008")

    geodetic = tmp_path / "geo.csv"
    geodetic.write_text("101,42.80000000,-85.15000000,984.25,P\n", encoding="utf-8")
    into_the_zone = JobSettings(
        input_path=geodetic,
        output_directory=tmp_path / "out_in",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=zone,
        input_unit=US_SURVEY_FEET,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=NATRF2022,
    )
    assert run(into_the_zone).points[0].output_northing == pytest.approx(
        228600.0, abs=0.0005
    )

    grid = tmp_path / "grid.csv"
    grid.write_text("101,228600.000,1409700.000,300.00,P\n", encoding="utf-8")
    out_of_the_zone = JobSettings(
        input_path=grid,
        output_directory=tmp_path / "out_out",
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=zone,
        target_zone=None,
        input_unit=METERS,
        output_unit=US_SURVEY_FEET,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=NATRF2022,
    )
    assert run(out_of_the_zone).points[0].output_northing == pytest.approx(
        42.8, abs=5e-8
    )


# --------------------------------------------------------------------------
# The 0.7.0 closing gate's three job-level findings, each pinned at the
# reviewer's own input (review/gate-nsrs-closing/output.txt).
# --------------------------------------------------------------------------


def test_an_ellipsoid_height_in_the_2022_frame_is_refused(tmp_path):
    """The closing gate's HIGH, at the reviewer's exact job.

    ``H = h - N`` needs both heights measured from the SAME ellipsoid. The
    geoid models this program carries are NGS hybrid models published against
    NAD 83(2011); an NATRF2022 ellipsoid height is measured from a different
    realization, and the frozen NGS capture puts the two 1.115 m apart at
    43.0 N / 84.5 W (review/nsrs-n0/FINDINGS.md).

    The reviewer's input, verbatim: vertical-only, zone 261008 Grand Rapids,
    N = 251023.811677263118 m, E = 1462701.575467889430 m, h = 198.885 m,
    output datum NAVD 88 - the NATRF2022 counterpart of the frozen NAD 83
    anchor at h = 200.000 m. Before this gate the job succeeded and wrote
    **231.969990331655 m NAVD 88**, where the answer is 233.084999084570 m:
    an elevation 1.115 m low, wearing the right label, with nothing in the
    number to show it.
    """
    from michspc.fileio import geoid as geoid_module
    from michspc.spc.vertical import NAVD88, HeightKind
    from michspc.spc.zones import zone_by_code

    source = tmp_path / "gnss.csv"
    source.write_text(
        "1,251023.811677263118,1462701.575467889430,198.885,GNSS\n",
        encoding="utf-8",
    )
    settings = JobSettings(
        input_path=source,
        output_directory=tmp_path / "out",
        direction=Direction.VERTICAL_ONLY,
        source_zone=zone_by_code("261008"),
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=None,
        vertical_mode=jobmod.VerticalMode.VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
        geoid_model=geoid_module.GEOID18_MODEL,
        input_height_kind=HeightKind.ELLIPSOID,
    )

    with pytest.raises(FrameTransformationUnavailableError) as caught:
        run(settings)

    message = str(caught.value)
    assert "NATRF2022" in message
    assert "NAD83(2011)" in message
    # The measured fact, not an adjective: the two ellipsoid heights of one
    # point, and the distance between them.
    assert "1.115" in message
    assert "198.885" in message
    assert "200.000" in message
    assert "ORTHOMETRIC" in message
    assert "DEFERRED-NATRF2022-BRIDGE.md" in message

    # A settings fact, so it fires before the file is read: delete the file and
    # the same refusal arrives. A per-row check would raise FileNotFoundError.
    source.unlink()
    with pytest.raises(FrameTransformationUnavailableError):
        run(settings)


def test_the_ellipsoid_height_frame_gate_leaves_nad83_jobs_alone(tmp_path):
    """The half that proves the gate is about the FRAME, not about the feature.

    The same shape of job in NAD83(2011) still converts h -> H: the GEOID18
    anchor at 44.252 N / -85.4012 W, separation -33.280 m, so an ellipsoid
    height of 200.000 - 33.280 = 166.720 m must come back as 200.000 m NAVD 88
    (the frozen figures michspc/selftest.py's own ellipsoid check uses).
    Without this, refusing every ellipsoid job would pass the test above.
    """
    from michspc.fileio import geoid as geoid_module
    from michspc.spc.vertical import NAVD88, HeightKind

    source = tmp_path / "gnss83.csv"
    source.write_text("1,44.2520,-85.4012,166.720,GNSS\n", encoding="utf-8")
    settings = JobSettings(
        input_path=source,
        output_directory=tmp_path / "out",
        direction=Direction.VERTICAL_ONLY,
        source_zone=None,
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=jobmod.VerticalMode.VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
        geoid_model=geoid_module.GEOID18_MODEL,
        input_height_kind=HeightKind.ELLIPSOID,
        geodetic_frame=NAD83_2011,
    )

    assert run(settings).points[0].output_elevation == pytest.approx(
        200.000, abs=0.0015
    )


def test_an_orthometric_job_on_a_2022_zone_still_converts(tmp_path):
    """The other half, and it is the owner's recorded decision (#61).

    An elevation is a height above the GEOID, not above any frame's ellipsoid,
    so an ORTHOMETRIC job on a 2022 zone is honest and must keep working - the
    gate above must not widen into it. The residual it carries is recorded
    rather than hidden: the factors rebuild h as H + N in the NAD 83
    realization, ~0.175 ppm in the combined factor, three orders below the
    5.9 ppm the ellipsoid-height feature was built to correct.

    Zone 261008's captured origin, 42.8 N / -85.15 W, which beta NCAT put at
    the zone's published false origin N 228,600.000 m / E 1,409,700.000 m.
    """
    from michspc.spc.vertical import HeightKind
    from michspc.spc.zones import zone_by_code

    source = tmp_path / "ortho.csv"
    source.write_text("101,42.80000000,-85.15000000,300.00,P\n", encoding="utf-8")
    settings = JobSettings(
        input_path=source,
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=zone_by_code("261008"),
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=NATRF2022,
    )
    assert settings.input_height_kind is HeightKind.ORTHOMETRIC

    point = run(settings).points[0]

    assert point.output_northing == pytest.approx(228600.0, abs=0.0005)
    assert point.output_easting == pytest.approx(1409700.0, abs=0.0005)
    # And the factors are computed, not withheld: an elevation was supplied.
    assert point.factors.combined_factor is not None


def test_a_vertical_only_geodetic_job_refuses_an_unusable_frame(tmp_path):
    """The closing gate's first MEDIUM, at the reviewer's exact job.

    ``VERTICAL_ONLY`` was skipped by the settings frame gate on the ground that
    it has no second frame to disagree with the first. True, and it left the
    other question unasked: whether this program may carry a coordinate in that
    frame AT ALL. ``geodetic_position`` accepts any ``ReferenceFrame``, so the
    reviewer's job - VERTICAL_ONLY, no zone, WGS84, 43.0 N / -84.5 W,
    200.000 m, NGVD 29 -> NAVD 88 - ran to completion, returned
    199.85980355739594 m and a shift of -0.14019644260406494 m, and produced a
    record reading "Reference frame WGS84 - World Geodetic System 1984". The
    registry says nothing in this program accepts or produces a coordinate in
    that frame; the job record said otherwise.
    """
    from michspc.spc.frames import FrameNotUsableError, WGS84
    from michspc.spc.vertical import NAVD88, NGVD29

    source = tmp_path / "wgs.csv"
    source.write_text("1,43.0,-84.5,200.000,P\n", encoding="utf-8")
    settings = JobSettings(
        input_path=source,
        output_directory=tmp_path / "out",
        direction=Direction.VERTICAL_ONLY,
        source_zone=None,
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=jobmod.VerticalMode.VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
        geodetic_frame=WGS84,
    )

    with pytest.raises(FrameNotUsableError) as caught:
        run(settings)
    assert "WGS84" in str(caught.value)

    # Before the file is read, like every other settings refusal.
    source.unlink()
    with pytest.raises(FrameNotUsableError):
        run(settings)


def test_a_vertical_only_geodetic_job_in_a_usable_frame_still_runs(tmp_path):
    """And the same job in a usable frame converts, to the reviewer's digit.

    199.85980355739594 m is what the reviewer's WGS 84 job returned; it is the
    RIGHT answer for this position, and the frame was the only thing wrong
    with that job. Pinning it here is what stops the fix above from being
    "refuse vertical-only geodetic jobs".
    """
    from michspc.spc.vertical import NAVD88, NGVD29

    source = tmp_path / "nad.csv"
    source.write_text("1,43.0,-84.5,200.000,P\n", encoding="utf-8")
    settings = JobSettings(
        input_path=source,
        output_directory=tmp_path / "out",
        direction=Direction.VERTICAL_ONLY,
        source_zone=None,
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=jobmod.VerticalMode.VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
        geodetic_frame=NAD83_2011,
    )

    assert run(settings).points[0].output_elevation == pytest.approx(
        199.85980355739594, abs=1e-9
    )

    # NATRF2022 is usable too, and a vertical-only job may run in it: the gate
    # asks usability, not era.
    in_2022 = dataclasses.replace(settings, geodetic_frame=NATRF2022)
    assert run(in_2022).points[0].output_elevation == pytest.approx(
        199.85980355739594, abs=1e-9
    )


def test_a_zone_field_the_direction_never_reads_is_refused(tmp_path):
    """The closing gate's second MEDIUM: a false work history in the record.

    The reviewer's input: GEODETIC_TO_ZONE, NATRF2022, 43.0 N / -84.5 W, a
    stale ``source_zone`` of statewide 260001 and a real ``target_zone`` of
    Grand Rapids 261008. The conversion ignored 260001 and computed
    N = 251022.87520860415, E = 1462702.380322114 through 261008 alone - and
    the record, which derives its zone blocks from the SETTINGS, then printed
    a FROM block for 260001, a TO block for 261008, and the sentence that this
    conversion is an exact re-projection between them. No projection from
    260001 occurred. The archive round-tripped, so that false history escaped
    as the authoritative document.

    Both directions of the same shape are pinned: ZONE_TO_GEODETIC with a
    stray ``target_zone`` is the mirror.
    """
    from michspc.spc.zones import zone_by_code

    statewide = zone_by_code("260001")
    grand_rapids = zone_by_code("261008")

    geodetic = tmp_path / "geo.csv"
    geodetic.write_text("101,43.0,-84.5,300.00,P\n", encoding="utf-8")
    stray_source = JobSettings(
        input_path=geodetic,
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=statewide,
        target_zone=grand_rapids,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=NATRF2022,
    )

    with pytest.raises(ValueError) as caught:
        run(stray_source)
    message = str(caught.value)
    assert "source_zone" in message
    assert "GEODETIC_TO_ZONE" in message
    assert statewide.name in message and "260001" in message
    # Why it is refused rather than ignored: the record would print it.
    assert "job record" in message
    assert "source_zone=None" in message

    grid = tmp_path / "grid.csv"
    grid.write_text("101,228600.000,1409700.000,300.00,P\n", encoding="utf-8")
    stray_target = JobSettings(
        input_path=grid,
        output_directory=tmp_path / "out2",
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=grand_rapids,
        target_zone=statewide,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=NATRF2022,
    )

    with pytest.raises(ValueError) as caught:
        run(stray_target)
    message = str(caught.value)
    assert "target_zone" in message
    assert "ZONE_TO_GEODETIC" in message
    assert "target_zone=None" in message

    # The same two jobs stated honestly still convert - the refusal is about
    # the stray field, not about the direction.
    assert run(
        dataclasses.replace(stray_source, source_zone=None)
    ).points[0].output_northing == pytest.approx(251022.875, abs=0.0005)
    assert run(
        dataclasses.replace(stray_target, target_zone=None)
    ).points[0].output_northing == pytest.approx(42.8, abs=5e-8)


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
    assert "Longitude          negative west" in text
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


# ==========================================================================
# WP-R2 regression pins.
#
# Each test below is the reviewer's own counterexample, held against the fix
# that closed it. The counterexample position is Lansing, 42.73250000 N,
# -84.55550000 W - the same one the interim gate used - which in Michigan South
# is N = 136920.027586723 m, E = 3984537.119005890 m, i.e.
#     136920.027586723 / 0.3048 = 449212.6889 ift
#     3984537.119005890 / 0.3048 = 13072628.3432 ift
# ==========================================================================


ZONE_TO_GEODETIC_INPUT = "101,449212.689,13072628.343,900.000,IRON PIPE\n"
"""The reviewer's row for fix A: Michigan South in International feet, with a
900.000 ift elevation, converted back to the geodetic position above."""


def _zone_to_geodetic_job(tmp_path: Path, **overrides) -> JobSettings:
    """MI South 2113 -> geodetic, feet in, metres out, negative west."""
    path = overrides.pop("input_path", None)
    if path is None:
        path = tmp_path / "spc.txt"
        path.write_text(ZONE_TO_GEODETIC_INPUT, encoding="utf-8", newline="")
    return JobSettings(
        input_path=path,
        output_directory=overrides.pop("output_directory", tmp_path / "out"),
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        input_unit=overrides.pop("input_unit", INTERNATIONAL_FEET),
        output_unit=overrides.pop("output_unit", METERS),
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        **overrides,
    )


# --------------------------------------------------------------------------
# Fix A - the elevation of a geodetic export is in the OUTPUT unit
# --------------------------------------------------------------------------


def test_fix_a_the_clean_geodetic_export_writes_the_elevation_in_metres(tmp_path):
    """The reviewer's counterexample, whole.

    Hand-derived. units.py fixes the International foot at 0.3048 m exactly, so

        900.000 ift x 0.3048 m/ift = 274.32 m exactly

    (900 x 0.3048: 900 x 0.3 = 270, 900 x 0.0048 = 4.32, sum 274.32.) The
    output unit is metres, whose declared precision is 4 decimal places
    (michspc/spc/units.py), so the cell reads "274.3200".

    Columns two and three are the geodetic position the input row projects back
    to, formatted to 8 places by fmt.latitude / fmt.longitude: the interim
    gate's own figures for this point are 42.73250000 N, -84.55550000 W.

    Before the fix this cell read "900.000" - the input number, at the input
    unit's precision - under a job record whose "Units out" line said metres. A
    reader who did as the record instructs was 625.680 m out on Z.
    """
    result = run(_zone_to_geodetic_job(tmp_path))

    assert exports.clean_pnezd_rows(result) == [
        ["101", "42.73250000", "-84.55550000", "274.3200", "IRON PIPE"]
    ]


def test_fix_a_the_audit_csv_elevation_cell_agrees_with_the_clean_export(tmp_path):
    """The same 274.3200, in the file that exists to say how it was derived.

    The Elevation column is index 7 of AUDIT_COLUMNS, counted from the list in
    exports.py: Point(0), Source zone(1), Source northing(2), Source easting(3),
    Target zone(4), Target northing(5), Target easting(6), Elevation(7).
    """
    result = run(_zone_to_geodetic_job(tmp_path))

    header, row = exports.audit_rows(result)
    assert header[7] == "Elevation"
    # Hand-derived above: 900 ift x 0.3048 = 274.32 m exactly, 4 dp in metres.
    assert row[7] == "274.3200"
    # And the two files say the same thing about the same point.
    assert row[7] == exports.clean_pnezd_rows(result)[0][3]
    # The unit label states the pair, so the cell is not ambiguous.
    assert row[8] == "in ift, out m"


def test_fix_a_the_written_archive_carries_the_metre_elevation(tmp_path):
    """Not just the row builders - the bytes that reach the disk.

    Reads the clean export out of the ZIP that was actually written, because
    that is the file the surveyor unzips and imports.
    """
    result = run(_zone_to_geodetic_job(tmp_path))
    written = exports.write_all(result)

    text = member_text(written["archive"], "GEODETIC.csv")
    # Hand-derived above. The clean export has no header row, so the single
    # data line is the whole file.
    assert text.strip() == "101,42.73250000,-84.55550000,274.3200,IRON PIPE"


def test_fix_a_the_elevation_is_untouched_when_the_units_are_the_same(tmp_path):
    """The fix re-expresses; it must not shift.

    Feet in, feet out: 900.000 ift -> 274.32 m -> 900.000 ift, and the
    International foot's declared precision is 3 places, so "900.000".
    """
    result = run(_zone_to_geodetic_job(tmp_path, output_unit=INTERNATIONAL_FEET))

    assert exports.clean_pnezd_rows(result)[0][3] == "900.000"


# --------------------------------------------------------------------------
# Fix B - the job record describes the file that was actually read, and the
# file that was actually written, per direction
# --------------------------------------------------------------------------


def _section(text: str, start: str, end: str) -> str:
    """The slice of the record between two headings, for line-level asserts."""
    return text[text.index(start) : text.index(end)]


def test_fix_b_a_geodetic_input_is_not_described_as_pnezd(tmp_path):
    """Converting FROM geodetic: the INPUT block must say what the file held.

    The columns are a latitude and a longitude in decimal degrees, and the two
    layouts are indistinguishable from the numbers - a geodetic file read as
    PNEZD yields a plausible coordinate rather than an error - so the record
    describing it as "PNEZD, no header row / point, northing, easting" was a
    wrong statement in a document that is filed and believed.
    """
    text = report.build_report(run(_geodetic_job(tmp_path)))
    block = _section(text, "INPUT", "OUTPUT")

    # What the columns are.
    assert "Format             Comma separated, no header row - NOT PNEZD" in block
    assert "point, latitude, longitude, elevation, description" in block
    assert "Columns two and three are DECIMAL DEGREES, read" in block
    # ... and which way west is signed, without which the description of the
    # file cannot be read at all (docs/DESIGN.md section 7).
    assert "as negative west." in block

    # What it must NOT say.
    assert "PNEZD, no header row" not in block
    assert "point, northing, easting, elevation, description" not in block


def test_fix_b_a_geodetic_inputs_linear_unit_governs_only_the_elevation(tmp_path):
    """"Units in <foot>" must not be claimed over columns two and three.

    Degrees carry no linear unit. The elevation column does, and it is the one
    the elevation factor and the combined factor are computed from, so the unit
    is still stated - qualified to the column it actually governs.
    """
    text = report.build_report(run(_geodetic_job(tmp_path)))
    block = _section(text, "INPUT", "OUTPUT")

    assert (
        "Units in           International feet (ift) - the ELEVATION column only"
        in block
    )
    assert "Columns two and three are degrees and carry no" in block
    assert "linear unit." in block
    # The unqualified claim is gone.
    assert "- northing, easting and elevation" not in block


def test_fix_b_a_geodetic_export_is_not_described_as_pnezd(tmp_path):
    """Converting TO geodetic: the CLEAN EXPORT block, in FILES WRITTEN.

    "in the same PNEZD layout as the input" is true only of a zone-to-zone job.
    This export's columns two and three are degrees, and its one linear column
    is the elevation - which fix A now writes in the output unit, so the record
    naming that unit is the same statement the file makes.
    """
    result = run(_zone_to_geodetic_job(tmp_path))
    block = _section(report.build_report(result), "FILES WRITTEN", "END OF JOB RECORD")

    assert "The converted positions - NOT PNEZD, and NOT the same layout as" in block
    assert "the input: point, latitude, longitude, elevation, description," in block
    assert "Columns two and three are DECIMAL DEGREES to 8 places, written" in block
    assert "negative west." in block
    # The elevation, named as the one linear column and in the OUTPUT unit.
    assert "The elevation column is meters (m)." in block

    # The linear sentence belongs to the other directions only.
    assert "Northing, easting and elevation are" not in block
    assert "in the same PNEZD layout as the input" not in block


def test_fix_b_a_pnezd_export_out_of_a_geodetic_input_says_so(tmp_path):
    """The other geodetic direction writes PNEZD out of a file that was not.

    Saying "the same layout as the input" here would be exactly backwards.
    """
    block = _section(
        report.build_report(run(_geodetic_job(tmp_path))),
        "FILES WRITTEN",
        "END OF JOB RECORD",
    )

    assert "The converted coordinates in PNEZD layout - which the INPUT file" in block
    assert "was not: point, northing, easting, elevation, description, no" in block
    assert "Northing, easting and elevation are International feet (ift)." in block
    assert "in the same PNEZD layout as the input" not in block


def test_fix_b_a_zone_to_zone_record_still_reads_the_way_it_always_did(tmp_path):
    """The direction-aware wording must not have disturbed the ordinary job.

    A zone-to-zone job reads PNEZD and writes PNEZD, and both blocks say so.
    """
    text = report.build_report(_south_to_central(tmp_path))
    input_block = _section(text, "INPUT", "OUTPUT")
    files_block = _section(text, "FILES WRITTEN", "END OF JOB RECORD")

    assert "Format             PNEZD, no header row" in input_block
    assert "point, northing, easting, elevation, description" in input_block
    assert (
        "Units in           International feet (ift) - northing, easting and elevation"
        in input_block
    )
    assert "NOT PNEZD" not in input_block

    assert (
        "The converted coordinates, in the same PNEZD layout as the input:"
        in files_block
    )
    assert "Northing, easting and elevation are International feet (ift)." in files_block
    assert "NOT PNEZD" not in files_block


# --------------------------------------------------------------------------
# Fix C - a geoid miss is a warning, not a blank elevation field
# --------------------------------------------------------------------------


GEOID_MISS_INPUT = "OUT1,39.0,-84.0,800.0,OBS\n"
"""The reviewer's counterexample: a point with a perfectly good Z column at a
position the shipped GEOID18 tile does not cover.

Hand-derived from the tile's own header: g2018u3.bin spans 40.0 to 58.0 N and
-96.0 to -77.0 E. Latitude 39.0 is one degree south of its southern edge, so
the lookup must miss - while the horizontal conversion, which does not consult
the geoid at all, still succeeds."""


def _geoid_miss_job(tmp_path: Path) -> JobSettings:
    path = tmp_path / "outside.txt"
    path.write_text(GEOID_MISS_INPUT, encoding="utf-8", newline="")
    return JobSettings(
        input_path=path,
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )


def test_fix_c_a_geoid_miss_raises_its_own_warning_naming_the_point(tmp_path):
    """Silence here is indistinguishable from a blank Z column.

    The point converts, the elevation is present, and only the two
    elevation-dependent factors are absent. Without a warning the audit CSV,
    the report and the screen all show exactly what they show for a point that
    carried no elevation at all.
    """
    result = run(_geoid_miss_job(tmp_path))
    point = result.points[0]

    raised = result.warnings_of(WarningCode.GEOID_UNAVAILABLE)
    assert len(raised) == 1
    point_id, warning = raised[0]
    assert point_id == "OUT1"
    assert "point OUT1" in warning.message
    # It says the elevation WAS supplied, which is the whole distinction from a
    # blank Z field. The wording avoids "read from the file" because the same
    # message now reaches the single-point tab, which has no file to read
    # (closing review gate, docs/DESIGN.md amendment #26).
    assert "was supplied" in warning.message
    assert "file" not in warning.message
    assert "GEOID18" in warning.message

    # The elevation survives: 800.0 ift in, 800.0 ift out (units unchanged).
    assert point.row.elevation == 800.0
    assert abs(point.output_elevation - 800.0) < 1e-9
    # The factors that need a geoid height are absent, never 1.0.
    assert point.factors.elevation_factor is None
    assert point.factors.combined_factor is None
    # ... and the one that does not need it survives.
    assert point.factors.grid_scale_factor is not None
    # The height itself was read and is on the record, which is what separates
    # this point from one whose Z field was blank.
    assert point.factors.orthometric_height is not None


def test_fix_c_the_warning_reaches_the_audit_csv_warnings_cell(tmp_path):
    """The machine-readable code, in the column that carries codes.

    AUDIT_COLUMNS ends Warnings(-2), Description(-1).
    """
    result = run(_geoid_miss_job(tmp_path))

    header, row = exports.audit_rows(result)
    assert header[-2] == "Warnings"
    codes = row[-2].split("; ")
    assert "geoid-unavailable" in codes


def test_fix_c_the_report_names_the_point_and_never_calls_its_z_blank(tmp_path):
    """The false statement this fix removed, pinned by its own words.

    The ELEVATIONS section used to file this point under "Blank elevation
    field" - a claim about a Z column that was read perfectly well.
    """
    text = report.build_report(run(_geoid_miss_job(tmp_path)))
    elevations = _section(text, "ELEVATIONS", "WARNINGS")

    # The third category, in its own words.
    assert "carried an elevation the GEOID18 grid does not reach" in elevations
    assert (
        "Elevation recorded, but no GEOID18 geoid height at this position (1):"
        in elevations
    )
    assert "OUT1" in elevations
    assert "NOT blank and they are NOT zero" in elevations

    # And the two statements it must not make.
    assert "Blank elevation field" not in elevations
    assert "had NO usable elevation" not in elevations

    # The WARNINGS section carries it too, under its own heading.
    warnings_section = text[text.index("WARNINGS") :]
    assert (
        "ELEVATION RECORDED, BUT NO GEOID HEIGHT AT THIS POSITION" in warnings_section
    )
    assert "point OUT1: the elevation" in warnings_section


def test_fix_c_a_genuinely_blank_z_field_is_still_called_blank(tmp_path):
    """The new category must not have swallowed the old one.

    SAMPLE_PNEZD's CP-4 has an empty Z field and 007 holds exactly 0.00, and
    both sit inside the GEOID18 tile, so this job exercises the two original
    causes with the third absent.
    """
    elevations = _section(
        report.build_report(_south_to_central(tmp_path)), "ELEVATIONS", "WARNINGS"
    )

    # Two of the four sample points have no usable elevation: CP-4 (blank) and
    # 007 (exactly 0.00), counted from SAMPLE_PNEZD by eye.
    assert "2 of 4 points had NO usable elevation." in elevations
    assert "Blank elevation field (1):" in elevations
    assert "CP-4" in elevations
    assert "Elevation field held exactly 0.00 (1):" in elevations
    assert "007" in elevations
    # The third category does not appear when nothing triggered it.
    assert "does not reach" not in elevations


# --------------------------------------------------------------------------
# Fix D - duplicate point identifiers are refused
# --------------------------------------------------------------------------


def test_fix_d_two_rows_sharing_an_identifier_are_refused():
    """The reviewer's counterexample, verbatim.

    Both rows parse, both would convert, and both would be written out as point
    101 - after which the job record names a point that could be either and a
    CAD import overwrites or fails, with nothing in the export saying which row
    was which.
    """
    with pytest.raises(pnezd.PnezdError) as raised:
        pnezd.parse_lines(["101,1,2,3,FIRST", "101,4,5,6,SECOND"])

    message = str(raised.value)
    # The refusal names the identifier ...
    assert "'101'" in message
    # ... and BOTH line numbers, so the file can be corrected without a search.
    assert "line 2" in message
    assert "already used on line 1" in message


def test_fix_d_the_refusal_names_whichever_lines_actually_collided():
    """Not a fixed pair of numbers: the line numbers are the file's own.

    Rows 1 and 4 here, with two other identifiers in between.
    """
    with pytest.raises(pnezd.PnezdError) as raised:
        pnezd.parse_lines(
            [
                "CP-4,1,2,3,FIRST",
                "102,1,2,3,B",
                "103,1,2,3,C",
                "CP-4,9,9,9,SECOND",
            ]
        )

    message = str(raised.value)
    assert "'CP-4'" in message
    assert "line 4" in message
    assert "already used on line 1" in message


def test_fix_d_surrounding_whitespace_does_not_make_a_new_point():
    """"101" and "101 " are one point written untidily.

    The identifier is compared after stripping, because that is how it is
    stored - a file whose second row merely has a trailing space would
    otherwise pass the check and then collide inside the export.
    """
    with pytest.raises(pnezd.PnezdError, match="already used on line 1"):
        pnezd.parse_lines(["101,1,2,3,FIRST", " 101 ,4,5,6,SECOND"])


def test_fix_d_case_is_not_folded_because_this_program_has_no_authority_to():
    """"CP4" and "cp4" are two identifiers, not one.

    Folding case would refuse a legitimate file. The reader states what it
    compares and compares only that (pnezd.py module docstring).
    """
    parsed = pnezd.parse_lines(["CP4,1,2,3,FIRST", "cp4,4,5,6,SECOND"])

    assert [row.point_id for row in parsed.rows] == ["CP4", "cp4"]


def test_fix_d_distinct_identifiers_are_still_read(tmp_path):
    """The ordinary file must be unaffected.

    SAMPLE_PNEZD's four identifiers are all distinct, counted by eye:
    101, CP-4, 007, TBM1.
    """
    parsed = pnezd.read(_write_sample(tmp_path))

    assert [row.point_id for row in parsed.rows] == ["101", "CP-4", "007", "TBM1"]


# --------------------------------------------------------------------------
# Fix E - malformed quoting is refused, not repaired
# --------------------------------------------------------------------------


def test_fix_e_an_unterminated_quote_is_refused_not_repaired():
    """csv's default leniency turned '"UNTERMINATED' into UNTERMINATED.

    The parsed text then no longer represents the file, with no refusal
    anywhere - for a description field, a survey note silently rewritten.
    """
    with pytest.raises(pnezd.PnezdError) as raised:
        pnezd.parse_lines(['101,1,2,3,"UNTERMINATED'])

    message = str(raised.value)
    assert "line 1" in message
    assert "malformed" in message
    assert "refused rather than repaired" in message
    # The reader's own refusal, not a bare csv.Error reaching the surveyor.
    assert "The CSV reader reported:" in message


def test_fix_e_data_after_a_closing_quote_is_refused_not_repaired():
    """The second counterexample: '"A"junk' silently became Ajunk."""
    with pytest.raises(pnezd.PnezdError) as raised:
        pnezd.parse_lines(['101,1,2,3,"A"junk'])

    message = str(raised.value)
    assert "line 1" in message
    assert "refused rather than repaired" in message


def test_fix_e_a_legitimate_quoted_description_still_parses():
    """Strictness must not cost the format its documented convention.

    A quoted field containing a comma is exactly what the module docstring
    promises to honour: "IRON PIPE, BENT" is one description, not two fields.
    """
    parsed = pnezd.parse_lines(['101,1,2,3,"IRON PIPE, BENT"'])

    assert parsed.rows[0].description == "IRON PIPE, BENT"


def test_fix_e_an_escaped_inner_quote_still_parses():
    """A double quote inside a quoted field is written twice.

    '"6"" PIPE"' is the CSV spelling of the description 6" PIPE - a six-inch
    pipe, which is a monument description a surveyor really writes.
    """
    parsed = pnezd.parse_lines(['101,1,2,3,"6"" PIPE"'])

    assert parsed.rows[0].description == '6" PIPE'


def test_fix_e_the_written_export_still_round_trips_through_the_strict_reader(
    tmp_path,
):
    """The writer quotes; the strict reader must accept what the writer quotes.

    SAMPLE_PNEZD carries both awkward descriptions - "IRON PIPE, BENT" written
    with a bare comma and "BENCH, MARK" written quoted - so a quoting rule the
    strict reader rejects would surface here rather than on a surveyor's disk.
    """
    result = _south_to_central(tmp_path)
    written = exports.write_all(result)
    exported = extract_member(written["archive"], "MI-C.csv", tmp_path / "unzipped")

    reparsed = pnezd.read(exported)

    assert [row.description for row in reparsed.rows] == [
        point.row.description for point in result.points
    ]


# --------------------------------------------------------------------------
# Fix F - a geodetic input's source columns keep their precision and their name
# --------------------------------------------------------------------------


def test_fix_f_the_audit_csv_records_a_geodetic_source_at_full_precision(tmp_path):
    """The reviewer's counterexample: 42.73250000 recorded as 42.733.

    Hand-derived cost of the rounding that was there. One degree of latitude is
    about 111,132 m, so

        42.73250000 - 42.733 = -0.00050000 deg
        0.0005 x 111,132 = 55.6 m

    and one degree of longitude at 42.73 N is about 111,320 x cos(42.73 deg) =
    111,320 x 0.7345 = 81,764 m, so

        -84.55550000 - (-84.555) = -0.00050000 deg
        0.0005 x 81,764 = 40.9 m

    - roughly 55 m of latitude and 40 m of longitude, invented by a formatter,
    in the one file that exists to say how the number was derived.

    Columns 2 and 3 are the source pair in AUDIT_COLUMNS, counted from the list
    in exports.py.
    """
    result = run(_geodetic_job(tmp_path))
    header, row = exports.audit_rows(result)

    # The values, at the 8 places fmt.latitude and fmt.longitude write.
    assert row[2] == "42.73250000"
    assert row[3] == "-84.55550000"
    # The rounded strings are gone from the row entirely, not merely moved.
    assert "42.733" not in row
    assert "-84.555" not in row
    # Header sanity for the indices asserted above.
    assert header[2].startswith("Source ")
    assert header[3].startswith("Source ")


def test_fix_f_a_geodetic_source_column_is_named_for_what_it_holds(tmp_path):
    """"Source northing: 42.733" is not a shortened number, it is a wrong name."""
    columns = exports.audit_columns(run(_geodetic_job(tmp_path)))

    assert columns[2] == "Source latitude"
    assert columns[3] == "Source longitude (as in file)"
    # The converted end of this job is grid, and keeps its linear headings.
    assert columns[5] == "Target northing"
    assert columns[6] == "Target easting"


def test_fix_f_a_geodetic_target_column_is_named_for_what_it_holds(tmp_path):
    """The other direction, and the reviewer's verified headers.

    A State-Plane-to-geodetic job has always written degrees into columns 5 and
    6 - the values were never wrong - under headings that called them a
    northing and an easting.
    """
    result = run(_zone_to_geodetic_job(tmp_path))
    columns = exports.audit_columns(result)

    assert columns[5] == "Target latitude"
    assert columns[6] == "Target longitude (as written)"
    # The source end of this job is grid, and keeps its linear headings.
    assert columns[2] == "Source northing"
    assert columns[3] == "Source easting"

    # ... and the header row the file actually carries is that same list.
    assert exports.audit_rows(result)[0] == columns


def test_fix_f_a_zone_to_zone_audit_header_is_unchanged(tmp_path):
    """Neither end is geodetic, so nothing moves.

    Pinned because renaming per direction is exactly the kind of change that
    leaks into the direction it was not meant for.
    """
    result = _south_to_central(tmp_path)

    assert exports.audit_columns(result) == exports.AUDIT_COLUMNS
    assert exports.audit_columns(result)[2:4] == ["Source northing", "Source easting"]
    assert exports.audit_columns(result)[5:7] == ["Target northing", "Target easting"]


def test_fix_f_the_written_audit_csv_carries_the_direction_specific_header(tmp_path):
    """Read out of the archive, not out of the row builder."""
    result = run(_geodetic_job(tmp_path))
    written = exports.write_all(result)

    text = member_text(written["archive"], "_full.csv")
    header = next(csv.reader(io.StringIO(text)))

    assert header[2] == "Source latitude"
    assert header[3] == "Source longitude (as in file)"


# --------------------------------------------------------------------------
# Fix G - a byte order mark never becomes part of a point identifier
# --------------------------------------------------------------------------

# U+FEFF written as an escape rather than as the character itself, for the
# reason pnezd.py gives: an invisible mark in a source file is what this fix is
# about, and a literal one here would be exactly that.
_BOM = "﻿"


def test_fix_g_a_byte_order_mark_is_stripped_in_parse_lines():
    """Not only on the utf-8-sig path through ``read``.

    ``read``'s cp1252 fallback delivers the mark, and so does any caller
    handing this function text it decoded itself. Point "101" would then arrive
    as "\\ufeff101" and match nothing on the way back.
    """
    parsed = pnezd.parse_lines([_BOM + "101,1,2,3,A"])

    assert parsed.rows[0].point_id == "101"
    # Stated as an inequality too, because the two render identically.
    assert parsed.rows[0].point_id != _BOM + "101"
    assert _BOM not in parsed.rows[0].point_id


def test_fix_g_only_the_first_line_can_carry_one():
    """A mark is a file-level prefix, so a later line's is data, not a prefix.

    Stripping every line would quietly alter text on line 40 of a real file.
    This row's identifier is therefore left exactly as the file wrote it.
    """
    parsed = pnezd.parse_lines(["101,1,2,3,A", _BOM + "102,4,5,6,B"])

    assert parsed.rows[0].point_id == "101"
    assert parsed.rows[1].point_id == _BOM + "102"


def test_fix_g_a_marked_line_still_parses_all_five_fields():
    """The strip happens before the split, so nothing downstream sees it."""
    row = pnezd.parse_lines(
        [_BOM + "101,780000.000,13123359.580,800.00,IRON PIPE"]
    ).rows[0]

    assert row.point_id == "101"
    # Hand-derived: the fields are the literal numbers in the line above.
    assert row.northing == 780000.0
    assert row.easting == 13123359.58
    assert row.elevation == 800.0
    assert row.description == "IRON PIPE"


# ==========================================================================
# WP-R3 - the write path.
# ==========================================================================

# The reviewer's probe row for fix R3-1, in Michigan South International feet
# with no elevation recorded. Same Lansing position as above:
#     136920.027586723 / 0.3048 = 449212.6889 ift
#     3984537.119005890 / 0.3048 = 13072628.3432 ift
PROBE_INPUT = "101,449212.689,13072628.343,,IP\n"

CORRUPT_ROW = ["101", "999999.999", "888888.888", "777.777", "WRONG DESCRIPTION"]
"""The row the reviewer substituted wholesale for the expected one.

Every field but the identifier is wrong - the northing by about 550,000 ft, the
easting by more than 4,000,000 ft, an elevation invented for a point that never
had one, and a description that is not the surveyor's - and the program's own
round-trip gate passed it, because the gate compared the identifier and nothing
else."""


def _probe_job(tmp_path: Path, **overrides) -> jobmod.JobResult:
    """A one-point Michigan South -> Michigan South job over PROBE_INPUT.

    The identity re-projection is deliberate: the export's coordinates are then
    the input's own numbers, so a corrupted cell is visibly a different place
    rather than a plausible one.
    """
    path = tmp_path / "probe.txt"
    path.write_text(PROBE_INPUT, encoding="utf-8", newline="")
    settings = JobSettings(
        input_path=path,
        output_directory=tmp_path / "out",
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_SOUTH,
        target_zone=MI_SOUTH,
        input_unit=INTERNATIONAL_FEET,
        output_unit=overrides.pop("output_unit", INTERNATIONAL_FEET),
        longitude_convention=None,
        **overrides,
    )
    return run(settings)


# --------------------------------------------------------------------------
# R3-1 - the round-trip check compares every field, not just the identifier
# --------------------------------------------------------------------------


def test_r3_1_the_round_trip_check_passes_on_the_export_the_program_builds(tmp_path):
    """Anti-vacuousness for every refusal below.

    A gate that refuses everything proves as little as one that refuses
    nothing, so the honest export must go through untouched.
    """
    result = _probe_job(tmp_path)

    # Must not raise.
    exports.verify_round_trip(exports.clean_pnezd_rows(result), result)


def test_r3_1_the_reviewers_wholesale_corruption_is_refused(tmp_path):
    """The probe, exactly as the reviewer ran it.

    The expected row 101,449212.689,13072628.343,N/A,IP replaced by
    101,999999.999,888888.888,777.777,WRONG DESCRIPTION - a writer regression
    corrupting every coordinate, the elevation and the description - used to
    sail through this gate untouched.
    """
    result = _probe_job(tmp_path)

    # The row the program really builds, so the substitution below is the only
    # difference between passing and failing.
    built = exports.clean_pnezd_rows(result)
    assert built[0][0] == "101"
    assert built[0][3] == fmt.NOT_AVAILABLE
    assert built[0][4] == "IP"

    with pytest.raises(WriteError) as raised:
        exports.verify_round_trip([list(CORRUPT_ROW)], result)

    message = str(raised.value)
    assert "101" in message
    assert "Nothing was written" in message


@pytest.mark.parametrize(
    "index, replacement, field",
    [
        # Hand-derived from clean_pnezd_rows: point(0), northing(1), easting(2),
        # elevation(3), description(4). Each value is the reviewer's own from
        # CORRUPT_ROW, substituted one at a time so each field is shown to be
        # checked on its own rather than shielded by a neighbour.
        (1, "999999.999", "northing"),
        (2, "888888.888", "easting"),
        (3, "777.777", "elevation"),
        (4, "WRONG DESCRIPTION", "description"),
    ],
)
def test_r3_1_each_corrupted_field_is_caught_on_its_own(
    tmp_path, index, replacement, field
):
    """One field at a time, and the refusal names which one."""
    result = _probe_job(tmp_path)
    rows = exports.clean_pnezd_rows(result)
    rows[0][index] = replacement

    with pytest.raises(WriteError) as raised:
        exports.verify_round_trip(rows, result)

    message = str(raised.value)
    assert field in message
    # It names the point, so a 3,000-point file can be corrected.
    assert "'101'" in message


def test_r3_1_a_dropped_elevation_is_caught_as_well_as_an_invented_one(tmp_path):
    """The absence is a value, and it is compared in both directions.

    The reader maps a blank field, "N/A" and an exact 0.00 alike to None, so
    the check compares the two states before it compares two numbers. Here the
    job HAS an elevation and the export claims it has none - the mirror image
    of the reviewer's 777.777, and equally a file that does not carry what was
    converted.
    """
    path = tmp_path / "withz.txt"
    path.write_text("101,449212.689,13072628.343,900.000,IP\n", encoding="utf-8")
    result = run(
        JobSettings(
            input_path=path,
            output_directory=tmp_path / "out",
            direction=Direction.ZONE_TO_ZONE,
            source_zone=MI_SOUTH,
            target_zone=MI_SOUTH,
            input_unit=INTERNATIONAL_FEET,
            output_unit=INTERNATIONAL_FEET,
            longitude_convention=None,
        )
    )

    rows = exports.clean_pnezd_rows(result)
    # Hand-derived: 900.000 ift in, feet out, so the cell reads "900.000".
    assert rows[0][3] == "900.000"

    rows[0][3] = fmt.NOT_AVAILABLE
    with pytest.raises(WriteError, match="elevation"):
        exports.verify_round_trip(rows, result)

    # An exact zero is the same absence to the reader, and equally refused.
    rows[0][3] = "0.000"
    with pytest.raises(WriteError, match="elevation"):
        exports.verify_round_trip(rows, result)


def test_r3_1_a_shift_of_two_thousandths_of_a_foot_is_caught(tmp_path):
    """The tolerance is the formatter's rounding and not one bit more.

    Hand-derived. A northing is written to 3 decimal places in feet, so the
    written cell sits within 0.0005 ft of the value the job computed. Adding
    0.002 ft to the cell therefore puts it at least 0.0015 ft away - three
    times the whole budget - so it must be refused, while an honest export
    (above) passes.
    """
    result = _probe_job(tmp_path)
    rows = exports.clean_pnezd_rows(result)

    written = float(rows[0][1])
    rows[0][1] = f"{written + 0.002:.3f}"

    with pytest.raises(WriteError, match="northing"):
        exports.verify_round_trip(rows, result)


def test_r3_1_re_rendering_the_same_number_more_widely_is_accepted(tmp_path):
    """Not a text comparison: the same value written differently still passes.

    "449212.689" and "449212.68900" are the same number, and the reader returns
    the same float for both. A check that compared characters would refuse a
    correct file here.
    """
    result = _probe_job(tmp_path)
    rows = exports.clean_pnezd_rows(result)
    rows[0][1] = f"{float(rows[0][1]):.5f}"
    rows[0][2] = f" {rows[0][2]} "

    # Must not raise: the reader trims, and the numbers are unchanged.
    exports.verify_round_trip(rows, result)


def test_r3_1_a_geodetic_export_is_checked_in_degrees(tmp_path):
    """The columns are latitude and longitude on this branch, at 8 places.

    Hand-derived tolerance: 8 decimal places of a degree is 0.5e-8 deg, about
    half a millimetre. A shift of 0.00001 deg is roughly 1.1 m of latitude -
    a thousand times the budget - so it must be refused.
    """
    result = run(_zone_to_geodetic_job(tmp_path))
    rows = exports.clean_pnezd_rows(result)

    # Must not raise on the honest rows.
    exports.verify_round_trip(rows, result)

    rows[0][1] = f"{float(rows[0][1]) + 0.00001:.8f}"
    with pytest.raises(WriteError, match="latitude"):
        exports.verify_round_trip(rows, result)


def test_r3_1_a_geodetic_longitude_is_named_as_a_longitude(tmp_path):
    """The refusal must say which column, in the words of that direction."""
    result = run(_zone_to_geodetic_job(tmp_path))
    rows = exports.clean_pnezd_rows(result)
    rows[0][2] = f"{float(rows[0][2]) + 0.00001:.8f}"

    with pytest.raises(WriteError) as raised:
        exports.verify_round_trip(rows, result)

    assert "longitude" in str(raised.value)
    assert "easting" not in str(raised.value)


def test_r3_1_write_all_refuses_and_writes_nothing_when_the_check_fails(
    tmp_path, monkeypatch
):
    """The gate is upstream of the archive, so a failure leaves no file.

    ``clean_pnezd_rows`` is replaced with the reviewer's corrupted row, which is
    what a writer regression would amount to.
    """
    result = _probe_job(tmp_path)
    monkeypatch.setattr(exports, "clean_pnezd_rows", lambda _r: [list(CORRUPT_ROW)])

    with pytest.raises(WriteError):
        exports.write_all(result)

    destination = exports.archive_path(result)
    assert not destination.exists()
    assert not destination.parent.exists() or list(destination.parent.iterdir()) == []


# --------------------------------------------------------------------------
# R3-2 - the record can only certify the bytes that were converted
# --------------------------------------------------------------------------


def test_r3_2_the_digest_travels_with_the_rows_the_reader_parsed(tmp_path):
    """One read, one decode, one digest.

    Independently recomputed here from the bytes on disk; the reader is
    required to have hashed those same bytes rather than to have been asked
    again afterwards.
    """
    path = _write_sample(tmp_path)
    parsed = pnezd.read(path)

    assert parsed.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_r3_2_a_parsed_source_carries_no_digest_because_it_read_no_bytes():
    """``parse_lines`` is handed text, so it has nothing to certify.

    None is a statement - "these rows did not come from bytes this program
    read" - and it must not be filled in downstream.
    """
    parsed = pnezd.parse_lines(["101,780000.000,13123359.580,800.00,IRON PIPE"])

    assert parsed.sha256 is None


def test_r3_2_an_in_memory_source_never_borrows_the_named_files_hash(tmp_path):
    """The reviewer's counterexample, whole.

    An in-memory Lansing coordinate is converted while ``input_path`` points at
    a README. The record used to state "File README.md", the SHA-256 of the
    actual README, and "Format PNEZD, no header row" - certifying bytes that
    were never converted, and never even read as coordinates.
    """
    readme = tmp_path / "README.md"
    readme.write_text("# not a coordinate file\n", encoding="utf-8")
    readme_digest = hashlib.sha256(readme.read_bytes()).hexdigest()

    source = pnezd.parse_lines(["101,780000.000,13123359.580,800.00,IRON PIPE"])
    settings = JobSettings(
        input_path=readme,
        output_directory=tmp_path / "out",
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_SOUTH,
        target_zone=MI_CENTRAL,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=None,
    )
    result = run(settings, source=source)

    # The job ran on the supplied rows ...
    assert result.input_row_count == 1
    # ... and certifies nothing, rather than certifying the README.
    assert result.input_sha256 is None

    text = report.build_report(result)
    assert readme_digest not in text
    assert "SHA-256            not available" in text
    assert "already parsed, so it never read the file named" in text


def test_r3_2_editing_the_file_after_the_parse_cannot_change_the_record(tmp_path):
    """The same shape on the ordinary path, and the reason the digest moved.

    The hash used to be taken from the path at the end of the run, so anything
    that touched the file between the parse and the hash produced a record
    certifying bytes the job never saw. Here the file is rewritten wholesale
    after it was read, which is the largest version of that race.
    """
    path = _write_sample(tmp_path)
    original_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    parsed = pnezd.read(path)

    replacement = "999,1.000,2.000,3.000,SOMETHING ELSE ENTIRELY\n"
    path.write_text(replacement, encoding="utf-8", newline="")
    replaced_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert replaced_digest != original_digest

    settings = JobSettings(
        input_path=path,
        output_directory=tmp_path / "out",
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_SOUTH,
        target_zone=MI_CENTRAL,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=None,
    )
    result = run(settings, source=parsed)

    # The four points of SAMPLE_PNEZD were converted, not the one-line file
    # that is on the disk now.
    assert result.input_row_count == 4
    assert result.input_sha256 == original_digest
    assert result.input_sha256 != replaced_digest
    assert replaced_digest not in report.build_report(result)


def test_r3_2_the_ordinary_path_still_certifies_the_file_it_read(tmp_path):
    """Anti-vacuousness: the honest case must still print a real digest."""
    result = _south_to_central(tmp_path)

    expected = hashlib.sha256(result.settings.input_path.read_bytes()).hexdigest()
    assert result.input_sha256 == expected
    text = report.build_report(result)
    assert f"SHA-256            {expected}" in text
    assert "not available" not in text


# --------------------------------------------------------------------------
# R3-3 - the commit refuses a destination that appeared during the write
# --------------------------------------------------------------------------


PRIOR_EXPORT = b"101,1.000,2.000,3.000,THE FILE THAT WAS ALREADY THERE\r\n"
"""Stand-in for a previous job's export, compared byte for byte afterwards."""


def test_r3_3_a_destination_created_during_the_write_is_not_clobbered(tmp_path):
    """The race the existence check cannot close, closed at the commit.

    ``staged_write`` checks ``path.exists()`` before the body runs and then
    committed with an unconditional ``os.replace``. Building an archive takes
    time; another process - or the surveyor working in a second window - can
    create the destination in that gap, and the commit destroyed it silently.
    """
    destination = tmp_path / "job_MI-C.zip"

    with pytest.raises(WriteError) as raised:
        with staged_write(destination, overwrite=False) as staged:
            staged.write_bytes(b"the export this job built")
            # Someone else wins the race, after the existence check.
            destination.write_bytes(PRIOR_EXPORT)

    assert str(destination) in str(raised.value)
    assert "Nothing was written" in str(raised.value)
    # The other file survives, byte for byte.
    assert destination.read_bytes() == PRIOR_EXPORT


def test_r3_3_the_staged_file_is_removed_when_the_commit_is_refused(tmp_path):
    """A refusal must not leave a .partial beside the surveyor's export."""
    destination = tmp_path / "job_MI-C.zip"

    with pytest.raises(WriteError):
        with staged_write(destination, overwrite=False) as staged:
            staged.write_bytes(b"the export this job built")
            destination.write_bytes(PRIOR_EXPORT)

    assert [p.name for p in tmp_path.iterdir()] == [destination.name]


def test_r3_3_an_overwrite_that_was_granted_still_replaces(tmp_path):
    """The other half of the rule: when the user confirmed, the write lands.

    Including the same race - a destination appearing mid-write is exactly what
    the user agreed could be replaced.
    """
    destination = tmp_path / "job_MI-C.zip"

    with staged_write(destination, overwrite=True) as staged:
        staged.write_bytes(b"the new export")
        destination.write_bytes(PRIOR_EXPORT)

    assert destination.read_bytes() == b"the new export"
    assert [p.name for p in tmp_path.iterdir()] == [destination.name]


def test_r3_3_write_all_leaves_a_file_that_appeared_mid_write_alone(
    tmp_path, monkeypatch
):
    """End to end, through the function the GUI calls.

    The destination is created from inside ``_verify_archive`` - the last thing
    that happens before the commit - which is as close to the rename as this
    race can be staged.
    """
    result = _south_to_central(tmp_path)
    destination = exports.archive_path(result)
    destination.parent.mkdir(parents=True, exist_ok=True)

    real_verify = exports._verify_archive

    def verify_then_lose_the_race(staged, expected_members):
        real_verify(staged, expected_members)
        destination.write_bytes(PRIOR_EXPORT)

    monkeypatch.setattr(exports, "_verify_archive", verify_then_lose_the_race)

    with pytest.raises(WriteError):
        exports.write_all(result)

    assert destination.read_bytes() == PRIOR_EXPORT
    assert [p.name for p in destination.parent.iterdir()] == [destination.name]


# --------------------------------------------------------------------------
# R3-4 - the archive is flushed and read back before it takes its final name
# --------------------------------------------------------------------------


def test_r3_4_the_staged_archive_is_fsynced_before_the_rename(tmp_path, monkeypatch):
    """A rename is atomic for the name, not for the bytes behind it.

    ``atomic_write_text`` in the same package has always fsynced; the ZIP path -
    the only deliverable this program produces - never did.
    """
    calls = []
    real_fsync = exports.os.fsync

    def recording_fsync(descriptor):
        calls.append(descriptor)
        return real_fsync(descriptor)

    monkeypatch.setattr(exports.os, "fsync", recording_fsync)

    result = _south_to_central(tmp_path)
    exports.write_all(result)

    assert calls, "the staged archive was never flushed to the disk"


def test_r3_4_the_real_archive_passes_its_own_verification(tmp_path):
    """Anti-vacuousness: the honest archive must go through.

    All three members present, all three non-empty, every checksum matching.
    """
    result = _south_to_central(tmp_path)
    written = exports.write_all(result)

    names = tuple(exports.member_names(result).values())
    # Must not raise on the archive that was actually committed.
    exports._verify_archive(written["archive"], names)


def test_r3_4_a_member_whose_checksum_does_not_match_is_refused(tmp_path):
    """``testzip``'s branch, on an archive built to fail it deterministically.

    Stored rather than deflated so the member's bytes sit verbatim in the file
    and one of them can be flipped, leaving the recorded CRC describing text
    that is no longer there - which is what a bad sector or a half-written
    buffer looks like from the outside.
    """
    archive_file = tmp_path / "staged.zip"
    payload = b"AAAAAAAAAAAAAAAAAAAA"
    with zipfile.ZipFile(archive_file, "w", compression=zipfile.ZIP_STORED) as handle:
        handle.writestr("job.csv", payload)

    raw = bytearray(archive_file.read_bytes())
    start = raw.index(payload)
    raw[start] = ord("B")
    archive_file.write_bytes(bytes(raw))

    with pytest.raises(WriteError) as raised:
        exports._verify_archive(archive_file, ("job.csv",))

    assert "job.csv" in str(raised.value)
    assert "checksum" in str(raised.value)


def test_r3_4_a_missing_member_is_refused(tmp_path):
    """The three files travel together or not at all."""
    archive_file = tmp_path / "staged.zip"
    with zipfile.ZipFile(archive_file, "w") as handle:
        handle.writestr("job.csv", "101,1,2,3,IP\r\n")

    with pytest.raises(WriteError) as raised:
        exports._verify_archive(archive_file, ("job.csv", "job_README.txt"))

    assert "job_README.txt" in str(raised.value)
    assert "travel together" in str(raised.value)


def test_r3_4_an_empty_member_is_refused(tmp_path):
    """Every member is non-empty by construction, so zero length is a failure.

    The clean export has one line per point, the audit CSV has a header row at
    minimum, and the job record runs to several pages.
    """
    archive_file = tmp_path / "staged.zip"
    with zipfile.ZipFile(archive_file, "w") as handle:
        handle.writestr("job.csv", "")

    with pytest.raises(WriteError, match="empty file"):
        exports._verify_archive(archive_file, ("job.csv",))


def test_r3_4_a_corrupt_staged_archive_never_reaches_the_deliverable_name(
    tmp_path, monkeypatch
):
    """The whole point: the destination is left exactly as it was.

    The staged archive is truncated in the hook that runs immediately before the
    verification, standing in for an interrupted write or a bad sector. There is
    a previous export already at the destination, and the user granted the
    overwrite - so nothing but the verification stands between the corrupt bytes
    and the file a surveyor would open.
    """
    result = _south_to_central(tmp_path)
    destination = exports.archive_path(result)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(PRIOR_EXPORT)

    def truncate_instead_of_flushing(path):
        path.write_bytes(path.read_bytes()[:40])

    monkeypatch.setattr(exports, "_flush_to_disk", truncate_instead_of_flushing)

    with pytest.raises(WriteError) as raised:
        exports.write_all(result, overwrite=True)

    assert "not written" in str(raised.value)
    # The previous export is untouched, byte for byte ...
    assert destination.read_bytes() == PRIOR_EXPORT
    # ... and no .partial was left beside it.
    assert [p.name for p in destination.parent.iterdir()] == [destination.name]


def test_r3_4_a_corrupt_staged_archive_creates_no_file_at_all(tmp_path, monkeypatch):
    """The same, with nothing at the destination to begin with.

    A half-written archive under the deliverable name would be worse than no
    archive: the job reports failure and the folder holds a file named as
    though it succeeded.
    """
    result = _south_to_central(tmp_path)
    destination = exports.archive_path(result)

    def truncate_instead_of_flushing(path):
        path.write_bytes(path.read_bytes()[:40])

    monkeypatch.setattr(exports, "_flush_to_disk", truncate_instead_of_flushing)

    with pytest.raises(WriteError):
        exports.write_all(result)

    assert not destination.exists()
    assert list(destination.parent.iterdir()) == []


# --------------------------------------------------------------------------
# The input file takes decimal degrees only
# --------------------------------------------------------------------------
#
# The owner asked the direct question: do both DD and DMS work in the input
# CSV? They do not, deliberately, and docs/DESIGN.md amendment #28 records why.
# These tests are the answer in executable form - both halves of it, because
# "DMS is not supported" is only half an answer if the refusal does not say so.


DECIMAL_DEGREE_ROWS = (
    "101,43.80000000,-84.36700000,812.40,IRON PIPE\n"
    "102,43.80100000,-84.36800000,814.10,HUB\n"
)


def test_decimal_degrees_are_what_a_geodetic_input_file_holds():
    """The supported half. Columns two and three are plain decimal degrees.

    Anti-vacuousness for every refusal below: the format that IS accepted has
    to actually be accepted, or the tests that follow would pass against a
    reader that refused everything.
    """
    parsed = pnezd.parse_lines(DECIMAL_DEGREE_ROWS.splitlines())

    assert len(parsed.rows) == 2
    assert parsed.rows[0].northing == pytest.approx(43.8, abs=1e-12)
    assert parsed.rows[0].easting == pytest.approx(-84.367, abs=1e-12)


@pytest.mark.parametrize(
    "written",
    [
        "43°47'59.8\"N",
        "43 47 59.8 N",
        "43-47-59.8",
        "43:47:59.8N",
        "43d47m59.8s",
        "43°47'59.8\"",
        "43 47 59.8",
    ],
)
def test_a_dms_angle_in_the_file_is_refused_and_told_why(written):
    """Refused, and the refusal names the format rather than the value.

    "which is not a number" is true and useless: a surveyor whose data
    collector exported DMS has a FORMAT problem, and the message has to say
    that or he will go looking for a corrupt row. It also points him at the
    Single point tab, which does take DMS (amendment #28).

    Every spelling here is one a data collector or a spreadsheet actually
    produces, and none of them is guessed at.
    """
    # Quoted, with any inner double quote doubled - the CSV spelling of a
    # seconds symbol. Written out here rather than left to chance: an
    # improperly quoted line is refused by the QUOTING guard instead, and the
    # test would then be checking the wrong refusal.
    line = '101,"' + written.replace('"', '""') + '",-84.36700000,812.40,IRON PIPE'

    with pytest.raises(pnezd.PnezdError) as raised:
        pnezd.parse_lines([line])

    message = str(raised.value)
    assert "degrees, minutes and seconds" in message
    assert "DECIMAL DEGREES only" in message
    assert "Single point tab" in message
    # It still names the field and the line, like every other refusal here.
    assert "northing" in message
    assert "line 1" in message


def test_a_packed_dms_angle_is_the_reason_dms_is_not_read_from_a_file():
    """434759.8 is a perfectly good decimal degree, and it is not near Michigan.

    This is the case that cannot be caught and is why the format is refused
    outright rather than sniffed: packed DMS is indistinguishable from an
    ordinary number, so a reader that tried to accept DMS would have to guess,
    and guessing moves a point silently. Here it parses as what it literally
    is - which is exactly right, and exactly why the OTHER spellings are
    refused with a message instead.
    """
    parsed = pnezd.parse_lines(['101,"434759.8",-84.36700000,812.40,PIPE'])

    assert parsed.rows[0].northing == pytest.approx(434759.8, abs=1e-9)


def test_the_dms_hint_does_not_fire_on_an_ordinary_bad_number():
    """A false positive here would send someone hunting a format problem that
    is not there. Plain rubbish gets the plain message."""
    with pytest.raises(pnezd.PnezdError) as raised:
        pnezd.parse_lines(["101,IRON PIPE,-84.367,812.40,DESC"])

    message = str(raised.value)
    assert "which is not a number" in message
    assert "degrees, minutes and seconds" not in message
