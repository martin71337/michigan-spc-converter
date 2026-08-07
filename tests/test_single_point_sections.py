"""The single-point results layout, asserted without a widget.

``single_point_sections`` is a pure function of a ``JobResult``, so the layout
the owner approved (docs/DESIGN.md amendment #26) can be asserted label by
label and value by value with no ``QApplication`` and no widget tree anywhere in
this file. That is the point of the split: the layout is a statement about the
conversion, not a property of some form.

Two properties dominate, and they are the same two the multi-point interface is
held to.

**UI honesty.** Every value must be the string ``michspc.fileio.formatting``
produced for that quantity - not a similar string, not one that rounds the same
way, the same string. So the assertions below compare against the formatter
applied to the result's OWN numbers, never against a literal typed here. A
literal would keep passing while the screen and the audit CSV drifted apart,
which is the exact failure the rule exists to prevent (docs/method/METHOD.md
section 5).

**The two tabs cannot disagree.** Every result here is built by calling
``job.run`` on ``pnezd.parse_typed_point`` output - the same validation gate and
the same conversion function a file row goes through.
"""

from __future__ import annotations

import os

# MUST precede any Qt import. ``results_model`` imports PySide6 at module level,
# and the platform plugin is chosen at import time (docs/method/TOOLING.md).
# Nothing in this file creates a QApplication; the functions under test are
# pure.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402

from michspc.fileio import formatting as fmt, pnezd  # noqa: E402
from michspc.gui import results_model as rm  # noqa: E402
from michspc.gui.controls import zone_label  # noqa: E402
from michspc.job import (  # noqa: E402
    Direction,
    JobResult,
    JobSettings,
    LongitudeConvention,
    run,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS  # noqa: E402
from michspc.spc.zones import MI_CENTRAL, MI_SOUTH  # noqa: E402

# --------------------------------------------------------------------------
# The typed points. Chosen, not computed.
#
# The grid point sits 780,000 ift north and on Michigan South's own false
# easting of 13,123,359.580 ift (4,000,000 m), so it is on the central meridian
# at about 43.64 N - inside Michigan South's extent (41.6-44.3) and inside
# Michigan Central's (43.5-46.0), so a South -> Central conversion raises no
# extent warning.
#
# The geodetic point is Lansing-ish: 42.7325 N, 84.5555 W, well inside Michigan
# South. Its DMS values are the owner's two worked examples exactly -
# 42 deg 43' 57.00000" N and 84 deg 33' 19.80000" W.
# --------------------------------------------------------------------------

TYPED_NORTHING = "780000.000"
TYPED_EASTING = "13123359.580"
TYPED_ELEVATION = "800.00"

TYPED_LATITUDE = "42.7325"
TYPED_LONGITUDE_NEGATIVE_WEST = "-84.5555"
TYPED_LONGITUDE_POSITIVE_WEST = "84.5555"


def _zone_to_zone(**overrides) -> JobResult:
    parsed = pnezd.parse_typed_point(
        overrides.pop("northing", TYPED_NORTHING),
        overrides.pop("easting", TYPED_EASTING),
        overrides.pop("elevation", TYPED_ELEVATION),
        source=pnezd.TYPED_POINT_SOURCE_GRID,
    )
    settings = JobSettings(
        input_path=None,
        output_directory=None,
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_SOUTH,
        target_zone=MI_CENTRAL,
        input_unit=INTERNATIONAL_FEET,
        output_unit=overrides.pop("output_unit", INTERNATIONAL_FEET),
        # A zone-to-zone job never asks for a convention, and this is the
        # direction whose longitude row is therefore carried entirely by the
        # hemisphere letter.
        longitude_convention=None,
        **overrides,
    )
    return run(settings, source=parsed)


def _zone_to_geodetic(**overrides) -> JobResult:
    parsed = pnezd.parse_typed_point(
        TYPED_NORTHING,
        TYPED_EASTING,
        TYPED_ELEVATION,
        source=pnezd.TYPED_POINT_SOURCE_GRID,
    )
    settings = JobSettings(
        input_path=None,
        output_directory=None,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        input_unit=INTERNATIONAL_FEET,
        output_unit=overrides.pop("output_unit", INTERNATIONAL_FEET),
        longitude_convention=overrides.pop(
            "longitude_convention", LongitudeConvention.NEGATIVE_WEST
        ),
        **overrides,
    )
    return run(settings, source=parsed)


def _geodetic_to_zone(**overrides) -> JobResult:
    convention = overrides.pop(
        "longitude_convention", LongitudeConvention.NEGATIVE_WEST
    )
    longitude = overrides.pop(
        "longitude",
        TYPED_LONGITUDE_NEGATIVE_WEST
        if convention is LongitudeConvention.NEGATIVE_WEST
        else TYPED_LONGITUDE_POSITIVE_WEST,
    )
    parsed = pnezd.parse_typed_point(
        overrides.pop("latitude", TYPED_LATITUDE),
        longitude,
        overrides.pop("elevation", TYPED_ELEVATION),
        source=pnezd.TYPED_POINT_SOURCE_GEODETIC,
    )
    settings = JobSettings(
        input_path=None,
        output_directory=None,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=INTERNATIONAL_FEET,
        output_unit=overrides.pop("output_unit", INTERNATIONAL_FEET),
        longitude_convention=convention,
        **overrides,
    )
    return run(settings, source=parsed)


ALL_DIRECTIONS = {
    "zone to zone": _zone_to_zone,
    "State Plane to geodetic": _zone_to_geodetic,
    "geodetic to State Plane": _geodetic_to_zone,
}


def _labels(section) -> tuple[str, ...]:
    return tuple(value.label for value in section.values)


def _by_label(section) -> dict[str, str]:
    return {value.label: value.text for value in section.values}


# ==========================================================================
# The three layouts, exactly as the owner approved them.
#
# The expected tuples below are transcribed from amendment #26's table, not
# read back from the code. Order is asserted, not membership: the owner decided
# the reading order as well as the contents.
# ==========================================================================


def test_zone_to_zone_is_the_owners_layout():
    """Amendment #26, row one.

    The rule behind it: computed values independent of the target zone appear
    under OUTPUT, and the factors that describe the TYPED State Plane
    coordinate stay under INPUT. So the source grid scale factor and source
    convergence are on the input side and everything else is on the output
    side, including the geodetic pivot the conversion passed through.
    """
    source, target = rm.single_point_sections(_zone_to_zone())

    assert (source.title, target.title) == ("INPUT", "OUTPUT")
    assert _labels(source) == (
        "Zone",
        "Units",
        "Northing",
        "Easting",
        "Elevation",
        "Grid scale factor",
        "Convergence",
    )
    assert _labels(target) == (
        "Zone",
        "Units",
        "Northing",
        "Easting",
        "Elevation",
        "Latitude",
        "Latitude (DMS)",
        "Longitude",
        "Longitude (DMS)",
        "Grid scale factor",
        "Convergence",
        "Geoid height (m)",
        "Ellipsoid height (m)",
        "Elevation factor",
        "Combined factor",
        "Warnings",
    )


def test_zone_to_geodetic_is_the_owners_layout():
    """Amendment #26, row two.

    "In SPC -> geodetic there is no target zone at all, so every factor
    describes the typed point and none of them belong on the output side." The
    output side is therefore the position, its elevation, the unit that
    elevation is in, and the warnings.
    """
    source, target = rm.single_point_sections(_zone_to_geodetic())

    assert (source.title, target.title) == ("INPUT", "OUTPUT")
    assert _labels(source) == (
        "Zone",
        "Units",
        "Northing",
        "Easting",
        "Elevation",
        "Grid scale factor",
        "Convergence",
        "Geoid height (m)",
        "Ellipsoid height (m)",
        "Elevation factor",
        "Combined factor",
    )
    assert _labels(target) == (
        "Latitude",
        "Latitude (DMS)",
        "Longitude",
        "Longitude (DMS)",
        "Elevation",
        "Units",
        "Warnings",
    )


def test_geodetic_to_zone_is_the_owners_layout():
    """Amendment #26, row three.

    The input side is the position as typed, its elevation and that
    elevation's unit - the input file's columns two and three hold degrees, so
    there is no input zone and no input northing or easting.
    """
    source, target = rm.single_point_sections(_geodetic_to_zone())

    assert (source.title, target.title) == ("INPUT", "OUTPUT")
    assert _labels(source) == (
        "Latitude",
        "Latitude (DMS)",
        "Longitude",
        "Longitude (DMS)",
        "Elevation",
        "Units",
    )
    assert _labels(target) == (
        "Zone",
        "Units",
        "Northing",
        "Easting",
        "Elevation",
        "Grid scale factor",
        "Convergence",
        "Geoid height (m)",
        "Ellipsoid height (m)",
        "Elevation factor",
        "Combined factor",
        "Warnings",
    )


# ==========================================================================
# UI honesty: every value is the formatter's own output.
# ==========================================================================


def test_zone_to_zone_values_are_the_formatters_output():
    """Compared against fmt applied to the result's own numbers, field by field.

    Nothing here is a literal. If the model started rounding, scaling a unit or
    choosing its own absent-value string, every one of these would fail - which
    is what the model's docstring promises it does not do.
    """
    result = _zone_to_zone()
    point = result.points[0]
    conversion = point.conversion
    factors = point.factors
    settings = result.settings
    source, target = rm.single_point_sections(result)

    assert _by_label(source) == {
        "Zone": zone_label(MI_SOUTH),
        "Units": f"{INTERNATIONAL_FEET.name} ({INTERNATIONAL_FEET.code})",
        "Northing": fmt.coordinate(point.row.northing, settings.input_unit),
        "Easting": fmt.coordinate(point.row.easting, settings.input_unit),
        "Elevation": fmt.coordinate(point.row.elevation, settings.input_unit),
        "Grid scale factor": fmt.factor(conversion.source_scale_factor),
        "Convergence": fmt.angle_dms(conversion.source_convergence),
    }
    assert _by_label(target) == {
        "Zone": zone_label(MI_CENTRAL),
        "Units": f"{INTERNATIONAL_FEET.name} ({INTERNATIONAL_FEET.code})",
        "Northing": fmt.coordinate(point.output_northing, settings.output_unit),
        "Easting": fmt.coordinate(point.output_easting, settings.output_unit),
        "Elevation": fmt.coordinate(point.output_elevation, settings.output_unit),
        "Latitude": fmt.latitude(conversion.latitude),
        "Latitude (DMS)": fmt.latitude_dms(conversion.latitude),
        "Longitude": fmt.longitude(conversion.longitude),
        "Longitude (DMS)": fmt.longitude_dms(conversion.longitude),
        "Grid scale factor": fmt.factor(factors.grid_scale_factor),
        "Convergence": fmt.angle_dms(conversion.target_convergence),
        "Geoid height (m)": fmt.geoid_height(factors.geoid_height),
        "Ellipsoid height (m)": fmt.geoid_height(factors.ellipsoid_height),
        "Elevation factor": fmt.factor(factors.elevation_factor),
        "Combined factor": fmt.factor(factors.combined_factor),
        "Warnings": "none",
    }


def test_zone_to_geodetic_values_are_the_formatters_output():
    """The same comparison for the direction whose output is a position.

    ``job._convert_row`` has already applied the chosen convention to
    ``output_easting`` (job.py's ZONE_TO_GEODETIC branch), so the displayed
    longitude must equal ``fmt.longitude(point.output_easting)`` and must not be
    negated a second time. That equality is asserted explicitly below.
    """
    result = _zone_to_geodetic()
    point = result.points[0]
    conversion = point.conversion
    factors = point.factors
    settings = result.settings
    source, target = rm.single_point_sections(result)

    assert _by_label(source) == {
        "Zone": zone_label(MI_SOUTH),
        "Units": f"{INTERNATIONAL_FEET.name} ({INTERNATIONAL_FEET.code})",
        "Northing": fmt.coordinate(point.row.northing, settings.input_unit),
        "Easting": fmt.coordinate(point.row.easting, settings.input_unit),
        "Elevation": fmt.coordinate(point.row.elevation, settings.input_unit),
        "Grid scale factor": fmt.factor(factors.grid_scale_factor),
        "Convergence": fmt.angle_dms(conversion.target_convergence),
        "Geoid height (m)": fmt.geoid_height(factors.geoid_height),
        "Ellipsoid height (m)": fmt.geoid_height(factors.ellipsoid_height),
        "Elevation factor": fmt.factor(factors.elevation_factor),
        "Combined factor": fmt.factor(factors.combined_factor),
    }

    values = _by_label(target)
    # The position, compared against the columns job.run itself produced.
    assert values["Latitude"] == fmt.latitude(point.output_northing)
    assert values["Longitude"] == fmt.longitude(point.output_easting)
    assert values["Elevation"] == fmt.coordinate(
        point.output_elevation, settings.output_unit
    )
    assert values["Units"] == (
        f"{INTERNATIONAL_FEET.name} ({INTERNATIONAL_FEET.code})"
    )
    assert values["Warnings"] == "none"
    # And the DMS rows, against the same numbers.
    assert values["Latitude (DMS)"] == fmt.latitude_dms(conversion.latitude)
    assert values["Longitude (DMS)"] == fmt.longitude_dms(conversion.longitude)


def test_geodetic_to_zone_values_are_the_formatters_output():
    """The input side is what the user typed; the output side is the grid.

    ``point.row.northing`` and ``point.row.easting`` hold the typed latitude and
    longitude, which is the branch ``exports.audit_rows`` takes at its
    ``geodetic_source`` test, so the screen and the audit CSV's "Source
    latitude"/"Source longitude (as in file)" cells carry the same characters.
    """
    result = _geodetic_to_zone()
    point = result.points[0]
    conversion = point.conversion
    factors = point.factors
    settings = result.settings
    source, target = rm.single_point_sections(result)

    values = _by_label(source)
    assert values["Latitude"] == fmt.latitude(point.row.northing)
    assert values["Longitude"] == fmt.longitude(point.row.easting)
    assert values["Elevation"] == fmt.coordinate(
        point.row.elevation, settings.input_unit
    )
    assert values["Units"] == (
        f"{INTERNATIONAL_FEET.name} ({INTERNATIONAL_FEET.code})"
    )
    assert values["Latitude (DMS)"] == fmt.latitude_dms(conversion.latitude)
    assert values["Longitude (DMS)"] == fmt.longitude_dms(conversion.longitude)

    assert _by_label(target) == {
        "Zone": zone_label(MI_SOUTH),
        "Units": f"{INTERNATIONAL_FEET.name} ({INTERNATIONAL_FEET.code})",
        "Northing": fmt.coordinate(point.output_northing, settings.output_unit),
        "Easting": fmt.coordinate(point.output_easting, settings.output_unit),
        "Elevation": fmt.coordinate(point.output_elevation, settings.output_unit),
        "Grid scale factor": fmt.factor(factors.grid_scale_factor),
        "Convergence": fmt.angle_dms(conversion.target_convergence),
        "Geoid height (m)": fmt.geoid_height(factors.geoid_height),
        "Ellipsoid height (m)": fmt.geoid_height(factors.ellipsoid_height),
        "Elevation factor": fmt.factor(factors.elevation_factor),
        "Combined factor": fmt.factor(factors.combined_factor),
        "Warnings": "none",
    }


def test_the_units_line_carries_the_name_and_the_code():
    """"meters (m)", never one without the other.

    A code alone is ambiguous between the two foot definitions the surveyor
    actually has to distinguish, and a name alone cannot be matched against the
    audit CSV's "in <code>, out <code>" cell.
    """
    result = _zone_to_zone(output_unit=METERS)
    _, target = rm.single_point_sections(result)

    # Hand-derived from michspc/spc/units.py: METERS.name is "meters" and
    # METERS.code is "m".
    assert _by_label(target)["Units"] == "meters (m)"


# ==========================================================================
# The DMS rows and the hemisphere letter.
# ==========================================================================


@pytest.mark.parametrize("name", sorted(ALL_DIRECTIONS))
def test_the_dms_rows_carry_five_decimals_of_a_second(name):
    """Five, in every direction (docs/DESIGN.md amendment #26)."""
    sections = rm.single_point_sections(ALL_DIRECTIONS[name]())

    found = 0
    for section in sections:
        for value in section.values:
            if not value.label.endswith("(DMS)"):
                continue
            found += 1
            # The seconds field is everything between the apostrophe and the
            # double quote; its fractional part must be exactly five digits.
            seconds = value.text.split("'")[1].split('"')[0]
            assert len(seconds.split(".")[1]) == 5

    # Both a latitude and a longitude, in every direction - so this loop cannot
    # pass by finding nothing.
    assert found == 2


def test_the_typed_geodetic_point_reads_back_as_the_owners_two_examples():
    """42.7325 N and 84.5555 W, the amendment's worked examples.

        42.7325 x 3600 = 153,837.0 s; /3600 = 42 deg rem 2,637.0;
            2,637.0 / 60 = 43 min rem 57.0
        84.5555 x 3600 = 304,399.8 s; /3600 = 84 deg rem 1,999.8;
            1,999.8 / 60 = 33 min rem 19.8

    The letter is W and there is no sign: magnitude plus a letter is the whole
    format, so a DMS longitude reads the same under either convention.
    """
    source, _ = rm.single_point_sections(_geodetic_to_zone())
    values = _by_label(source)

    # Hand-derived above.
    assert values["Latitude (DMS)"] == "42°43'57.00000\"N"
    assert values["Longitude (DMS)"] == "84°33'19.80000\"W"


@pytest.mark.parametrize(
    "convention, expected_dms",
    [
        # The same position, typed both ways, and the DMS row is IDENTICAL:
        # magnitude plus a hemisphere letter carries no sign for a convention
        # to move (docs/DESIGN.md amendment #26).
        (LongitudeConvention.NEGATIVE_WEST, "84°33'19.80000\"W"),
        (LongitudeConvention.POSITIVE_WEST, "84°33'19.80000\"W"),
    ],
)
def test_the_input_longitude_is_shown_in_the_convention_the_user_typed(
    convention, expected_dms
):
    """And the decimal-degrees row equals the typed column exactly.

    ``point.row.easting`` is the longitude as the surveyor wrote it, in
    whichever convention was chosen; the displayed number must be that, not a
    re-signed version of it. The DMS row beside it states the direction with a
    letter instead, and is therefore the same string in both.
    """
    result = _geodetic_to_zone(longitude_convention=convention)
    point = result.points[0]
    source, _ = rm.single_point_sections(result)
    values = _by_label(source)

    assert values["Longitude"] == fmt.longitude(point.row.easting)
    assert values["Longitude (DMS)"] == expected_dms
    assert values["Longitude (DMS)"].endswith("W")


@pytest.mark.parametrize(
    "convention",
    [LongitudeConvention.NEGATIVE_WEST, LongitudeConvention.POSITIVE_WEST],
)
def test_the_output_longitude_is_shown_in_the_convention_that_was_chosen(
    convention,
):
    """``job._convert_row`` already applied it, so it must not be applied twice.

    The decimal-degrees row must equal ``fmt.longitude(point.output_easting)``,
    which is the number the clean export's second column carries, and the letter
    is W under both conventions.
    """
    result = _zone_to_geodetic(longitude_convention=convention)
    point = result.points[0]
    _, target = rm.single_point_sections(result)
    values = _by_label(target)

    assert values["Longitude"] == fmt.longitude(point.output_easting)
    assert values["Longitude (DMS)"].endswith("W")
    # The DMS row never carries a sign, under either convention - only the
    # decimal-degrees row above it does.
    assert not values["Longitude (DMS)"].startswith("-")


def test_a_zone_to_zone_longitude_says_west_although_no_convention_was_asked():
    """The problem the hemisphere letter was introduced to solve.

    A zone-to-zone job never asks for a convention - ``job.run`` refuses None
    only for the geodetic directions - yet its result shows a longitude.
    Displaying a signed number with nothing said about its sign would be the
    interface answering a question it was never asked, so the letter says it.
    """
    result = _zone_to_zone()
    assert result.settings.longitude_convention is None

    _, target = rm.single_point_sections(result)
    values = _by_label(target)

    assert values["Longitude (DMS)"].endswith("W")
    # And no sign to interpret, which is the whole reason this reads cleanly in
    # a direction that never chose a convention.
    assert not values["Longitude (DMS)"].startswith("-")


# ==========================================================================
# Warnings.
# ==========================================================================


@pytest.mark.parametrize("name", sorted(ALL_DIRECTIONS))
def test_warnings_are_the_last_output_row_in_every_direction(name):
    """Including the direction the owner's table did not list.

    "A layout rule that hides a warning in one direction is not a layout rule"
    (docs/DESIGN.md amendment #26).
    """
    source, target = rm.single_point_sections(ALL_DIRECTIONS[name]())

    assert target.values[-1].label == "Warnings"
    # And it is on the output side only, in every direction.
    assert "Warnings" not in _labels(source)


@pytest.mark.parametrize("name", sorted(ALL_DIRECTIONS))
def test_a_clean_conversion_reads_none_rather_than_blank(name):
    """An empty value in a labelled list reads as an oversight.

    And "N/A" is reserved for a quantity that is genuinely absent and
    unknowable, which "this point raised no warnings" is not - it is a result,
    and it is the good one.
    """
    _, target = rm.single_point_sections(ALL_DIRECTIONS[name]())

    assert target.values[-1].text == "none"
    assert target.values[-1].text != ""
    assert target.values[-1].text != fmt.NOT_AVAILABLE


def test_the_warnings_row_carries_the_messages_in_full():
    """The sentences, not the codes, joined by a blank line.

    An easting of 11,000,000 ift is about 700,000 m, more than 2,000 km from
    Michigan South's 4,000,000 m false easting, so it trips
    easting_looks_wrong_for_zone; the position it inverts to then lands outside
    Michigan Central's extent, so a second warning follows. Two messages is what
    makes the blank-line join observable.
    """
    result = _zone_to_zone(easting="11000000.000")
    point = result.points[0]
    _, target = rm.single_point_sections(result)
    text = target.values[-1].text

    assert len(point.warnings) == 2
    # Hand-derived from the join: the messages themselves, in order, separated
    # by a blank line - the same shape the multi-point table's tooltip uses.
    assert text == "\n\n".join(w.message for w in point.warnings)
    # And the sentences really are there, not the compressed codes.
    assert "does not look like Michigan South data" in text
    # The typed point's identifier reaches the screen through the warning
    # context job._convert_row builds, which is why it may not be blank.
    assert f"point {pnezd.TYPED_POINT_ID}:" in text


def test_a_point_with_no_elevation_reads_not_available_and_never_one():
    """The elevation-dependent quantities are absent, and say so.

    A blank elevation field means "not recorded" (pnezd's disclosed
    convention), so there is no orthometric height, no geoid lookup, and no
    elevation or combined factor. Writing 1.0 into either would put a factor on
    a drawing that looks entirely ordinary.
    """
    result = _zone_to_zone(elevation="")
    _, target = rm.single_point_sections(result)
    values = _by_label(target)

    for label in (
        "Elevation",
        "Geoid height (m)",
        "Ellipsoid height (m)",
        "Elevation factor",
        "Combined factor",
    ):
        assert values[label] == fmt.NOT_AVAILABLE

    # The grid scale factor does NOT depend on elevation and is still a number.
    assert values["Grid scale factor"] != fmt.NOT_AVAILABLE


# ==========================================================================
# The clipboard text.
# ==========================================================================


def _parse_clipboard(text: str) -> list[tuple[str, tuple[tuple[str, str], ...]]]:
    """Read the clipboard text back into (title, ((label, value), ...)) blocks.

    Deliberately naive - split on the blank line, then on the tab - because
    that is exactly the shape the format promises and a lenient parser would
    hide a format that had drifted.
    """
    blocks = []
    for block in text.split("\n\n"):
        lines = block.split("\n")
        pairs = tuple(tuple(line.split("\t")) for line in lines[1:])
        blocks.append((lines[0], pairs))
    return blocks


@pytest.mark.parametrize("name", sorted(ALL_DIRECTIONS))
def test_the_clipboard_text_round_trips_to_the_same_label_value_pairs(name):
    """Every label and every value survives, in order, with no loss.

    A clean result is used so no value contains a newline of its own; the
    multi-line case is asserted separately below.
    """
    sections = rm.single_point_sections(ALL_DIRECTIONS[name]())
    text = rm.single_point_clipboard_text(sections)

    recovered = _parse_clipboard(text)

    assert [title for title, _ in recovered] == [s.title for s in sections]
    for (_, pairs), section in zip(recovered, sections):
        assert list(pairs) == [(v.label, v.text) for v in section.values]


def test_the_clipboard_text_has_no_trailing_blank_line():
    """One blank line between sections and none at the end."""
    text = rm.single_point_clipboard_text(rm.single_point_sections(_zone_to_zone()))

    assert not text.endswith("\n")
    # Exactly one blank line, between INPUT and OUTPUT.
    assert text.count("\n\n") == 1
    assert text.startswith("INPUT\n")
    assert "\n\nOUTPUT\n" in text


def test_a_multi_line_warning_keeps_its_newlines_in_the_clipboard_text():
    """Flattening them would compress the sentences that explain the flag."""
    result = _zone_to_zone(easting="11000000.000")
    sections = rm.single_point_sections(result)
    text = rm.single_point_clipboard_text(sections)

    warnings_value = sections[1].values[-1].text
    # The value goes in verbatim, blank lines and all, on the tab's right side.
    assert f"Warnings\t{warnings_value}" in text
    assert warnings_value.count("\n\n") == 1


# ==========================================================================
# The one-point precondition.
# ==========================================================================


def test_single_point_sections_refuses_a_job_carrying_more_than_one_point():
    """Refused rather than showing the first point as though it were the job.

    Fail closed (docs/DESIGN.md section 1): a display that silently described
    one row of a file as "the" result would be a wrong coordinate presented as
    a right one.
    """
    two_points = pnezd.parse_lines(
        ["1,780000.000,13123359.580,800.00", "2,781000.000,13123359.580,801.00"]
    )
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
    result = run(settings, source=two_points)

    with pytest.raises(ValueError) as raised:
        rm.single_point_sections(result)

    assert "one converted point" in str(raised.value)

    # Anti-vacuousness: the same settings with one point go through.
    assert rm.single_point_sections(_zone_to_zone())
