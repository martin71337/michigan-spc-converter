"""Degrees / minutes / seconds composed into decimal degrees.

The load-bearing property is the **round trip against the display formatter**.
``formatting.latitude_dms`` and ``formatting.longitude_dms`` define what a DMS
angle looks like in this program; ``fileio.dms`` reads that notation back. If
the two ever disagreed, a surveyor could copy a reading off the results panel,
type it into the entry boxes, and get a different point - two notations
pretending to be one, which is the divergence failure of amendment #26 arriving
in a new place.

Every expected value below is hand-derived in the comment above it
(docs/method/METHOD.md section 4).
"""

from __future__ import annotations


import pytest

from michspc.fileio import dms, formatting as fmt

# 43 deg 48 min 00 sec N is 43 + 48/60 = 43.8 exactly - chosen because it is
# exact in binary-free arithmetic and because it is the latitude the GUI tests
# already use for a Michigan Central point.
LATITUDE_DEGREES = "43"
LATITUDE_MINUTES = "48"
LATITUDE_SECONDS = "00.00000"
LATITUDE_DECIMAL = 43.8

# 84 deg 22 min 01.2 sec W:
#   22/60      = 0.3666666...
#   1.2/3600   = 0.0003333...
#   84 + 0.36666666... + 0.00033333... = 84.367 exactly to 3 places
LONGITUDE_DEGREES = "84"
LONGITUDE_MINUTES = "22"
LONGITUDE_SECONDS = "01.20000"
LONGITUDE_MAGNITUDE = 84.367


# --------------------------------------------------------------------------
# The angle itself
# --------------------------------------------------------------------------


def test_a_northern_latitude_is_positive():
    """43 + 48/60 = 43.8."""
    value = dms.decimal_degrees(
        LATITUDE_DEGREES, LATITUDE_MINUTES, LATITUDE_SECONDS, "N", axis=dms.LATITUDE
    )
    assert value == pytest.approx(LATITUDE_DECIMAL, abs=1e-12)


def test_a_southern_latitude_is_the_same_magnitude_negated():
    """The letter is the only thing that differs, and it flips the sign."""
    north = dms.decimal_degrees("12", "30", "00", "N", axis=dms.LATITUDE)
    south = dms.decimal_degrees("12", "30", "00", "S", axis=dms.LATITUDE)

    assert north == pytest.approx(12.5, abs=1e-12)
    assert south == -north


def test_a_western_longitude_is_negative_in_the_programs_own_convention():
    """84 + 22/60 + 1.2/3600 = 84.367, west, so -84.367.

    Negative-west is the signed convention the core stores and the one
    ``formatting.longitude_dms`` reads (docs/DESIGN.md section 7).
    """
    value = dms.decimal_degrees(
        LONGITUDE_DEGREES,
        LONGITUDE_MINUTES,
        LONGITUDE_SECONDS,
        "W",
        axis=dms.LONGITUDE,
    )
    assert value == pytest.approx(-LONGITUDE_MAGNITUDE, abs=1e-9)


def test_seconds_carry_their_fraction_all_the_way_through():
    """0.00001 of a second is about 0.3 mm on the ground, and it survives.

    1 second of latitude is about 30.9 m, so 1e-5 sec is 3.1e-4 m. The pin is
    that the composed angle differs from the whole-second one by exactly
    1e-5/3600 degrees - i.e. nothing was rounded away on the way through.
    """
    whole = dms.decimal_degrees("43", "48", "00", "N", axis=dms.LATITUDE)
    fractional = dms.decimal_degrees("43", "48", "00.00001", "N", axis=dms.LATITUDE)

    assert fractional - whole == pytest.approx(1e-5 / 3600.0, rel=1e-9)


# --------------------------------------------------------------------------
# The round trip against the display formatter
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        43.8,
        -84.367,
        41.75,
        -90.0,
        45.123456789,
        -83.000001,
        0.0,
        12.5,
    ],
)
def test_every_displayed_latitude_reads_back_as_itself(value):
    """Type back what the panel showed and get the same angle.

    The formatter rounds to five decimals of a second - about 0.3 mm - so the
    comparison is to that tolerance and not to the bit. Anything looser would
    pass while the two notations disagreed by a measurable distance.

    5e-6 seconds / 3600 = 1.4e-9 degrees, and half a rounding step is half of
    that; 1e-8 degrees is the tolerance used, comfortably above the rounding
    and far below anything a surveyor could measure.
    """
    shown = fmt.latitude_dms(value)

    # "43°48'00.00000\"N" -> the four components, by the symbols the formatter
    # itself writes. Split here rather than with a regex so a change to the
    # displayed format breaks this loudly instead of silently not matching.
    degrees, rest = shown.split("°")
    minutes, rest = rest.split("'")
    seconds, hemisphere = rest[:-2], rest[-1]

    read_back = dms.decimal_degrees(
        degrees, minutes, seconds, hemisphere, axis=dms.LATITUDE
    )
    assert read_back == pytest.approx(value, abs=1e-8)


@pytest.mark.parametrize(
    "value",
    [-84.367, -83.0, -90.5, -86.123456, -84.0000001, 0.0, 12.75],
)
def test_every_displayed_longitude_reads_back_as_itself(value):
    """The same round trip on the other axis, in the program's signed
    convention. ``longitude_dms`` takes negative-west and returns a magnitude
    plus a letter, so this is the inverse of exactly that."""
    shown = fmt.longitude_dms(value)

    degrees, rest = shown.split("°")
    minutes, rest = rest.split("'")
    seconds, hemisphere = rest[:-2], rest[-1]

    read_back = dms.decimal_degrees(
        degrees, minutes, seconds, hemisphere, axis=dms.LONGITUDE
    )
    assert read_back == pytest.approx(value, abs=1e-8)


def test_the_round_trip_would_notice_a_disagreement():
    """Anti-vacuousness for the two tests above.

    They must be capable of failing, and the way they would fail in practice is
    one notation drifting from the other - a minute read as a degree, or a
    hemisphere ignored. Both are constructed here and both are caught.
    """
    correct = dms.decimal_degrees("43", "48", "00", "N", axis=dms.LATITUDE)

    minutes_as_degrees = dms.decimal_degrees("43", "00", "48", "N", axis=dms.LATITUDE)
    assert minutes_as_degrees != pytest.approx(correct, abs=1e-8)

    hemisphere_ignored = dms.decimal_degrees("43", "48", "00", "S", axis=dms.LATITUDE)
    assert hemisphere_ignored != pytest.approx(correct, abs=1e-8)


# --------------------------------------------------------------------------
# The text handed to the reader
# --------------------------------------------------------------------------


def test_the_text_is_what_the_decimal_box_would_have_held():
    """It goes into a CSV line and through pnezd, so it has to be a plain
    number: no degree symbol, no letter, no thousands separator."""
    text = dms.decimal_degrees_text(
        LATITUDE_DEGREES,
        LATITUDE_MINUTES,
        LATITUDE_SECONDS,
        "N",
        axis=dms.LATITUDE,
        positive_west=False,
    )

    assert float(text) == pytest.approx(LATITUDE_DECIMAL, abs=1e-12)
    assert "," not in text
    assert "°" not in text
    assert not text.strip().endswith(("N", "S", "E", "W"))


def test_the_text_loses_nothing_the_float_carried():
    """``repr`` round-trips a float exactly; ``f"{v:.8f}"`` would not.

    8 decimal places of a degree is about 1.1 mm, so a fixed format would round
    the typed angle before it was ever converted. The pin is exactness, not
    closeness.
    """
    text = dms.decimal_degrees_text(
        "43", "48", "00.123456789", "N", axis=dms.LATITUDE, positive_west=False
    )
    composed = dms.decimal_degrees(
        "43", "48", "00.123456789", "N", axis=dms.LATITUDE
    )

    assert float(text) == composed  # bitwise, not approximately


def test_a_west_longitude_is_written_in_whichever_convention_was_chosen():
    """The same point, the two ways a decimal box would have spelled it.

    This is what lets everything downstream be identical between the two entry
    modes: what comes back is indistinguishable from what the user would have
    typed himself.
    """
    negative = dms.decimal_degrees_text(
        LONGITUDE_DEGREES,
        LONGITUDE_MINUTES,
        LONGITUDE_SECONDS,
        "W",
        axis=dms.LONGITUDE,
        positive_west=False,
    )
    positive = dms.decimal_degrees_text(
        LONGITUDE_DEGREES,
        LONGITUDE_MINUTES,
        LONGITUDE_SECONDS,
        "W",
        axis=dms.LONGITUDE,
        positive_west=True,
    )

    assert float(negative) == pytest.approx(-LONGITUDE_MAGNITUDE, abs=1e-9)
    assert float(positive) == pytest.approx(LONGITUDE_MAGNITUDE, abs=1e-9)
    assert float(negative) == -float(positive)


def test_a_latitude_ignores_the_longitude_convention():
    """There is no positive-south anything. The sign of a latitude is a fact
    about the point, not a choice about how a file writes it."""
    under_negative_west = dms.decimal_degrees_text(
        LATITUDE_DEGREES,
        LATITUDE_MINUTES,
        LATITUDE_SECONDS,
        "N",
        axis=dms.LATITUDE,
        positive_west=False,
    )
    under_positive_west = dms.decimal_degrees_text(
        LATITUDE_DEGREES,
        LATITUDE_MINUTES,
        LATITUDE_SECONDS,
        "N",
        axis=dms.LATITUDE,
        positive_west=True,
    )

    assert under_negative_west == under_positive_west


# --------------------------------------------------------------------------
# Refusals - each one names the box
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "degrees,minutes,seconds,expected_word",
    [
        ("", "48", "00", "degrees"),
        ("43", "", "00", "minutes"),
        ("43", "48", "", "seconds"),
        ("   ", "48", "00", "degrees"),
    ],
)
def test_an_empty_box_is_refused_and_named(degrees, minutes, seconds, expected_word):
    """Never read as zero. A minutes box left empty by accident is a mile."""
    with pytest.raises(dms.DmsError) as raised:
        dms.decimal_degrees(degrees, minutes, seconds, "N", axis=dms.LATITUDE)

    message = str(raised.value)
    assert expected_word in message
    assert "latitude" in message
    # It says WHY a blank is not zero, rather than only that it is missing.
    assert "not read as zero" in message


def test_a_signed_component_is_refused_rather_than_combined():
    """"-84" with "W" says west twice, and might have meant east."""
    with pytest.raises(dms.DmsError) as raised:
        dms.decimal_degrees("-84", "22", "01.2", "W", axis=dms.LONGITUDE)

    assert "without a sign" in str(raised.value)
    assert "hemisphere letter" in str(raised.value)


def test_a_missing_hemisphere_is_refused_rather_than_assumed():
    """The dropdown opens on a real letter and cannot be emptied (#28 note 3),
    so this guard is unreachable from the GUI today - and it stays.

    It is what stops a later change up in the interface from quietly acquiring
    a default down here: an empty letter reaching this function is a caller
    that did not answer, and inventing "N" for it would put an assumption in
    the one module that is supposed to hold none.
    """
    with pytest.raises(dms.DmsError) as raised:
        dms.decimal_degrees("43", "48", "00", "", axis=dms.LATITUDE)

    message = str(raised.value)
    assert "N or S" in message
    assert "will not invent one" in message


def test_the_wrong_axis_letter_is_refused():
    """"W" is not a latitude and "N" is not a longitude."""
    with pytest.raises(dms.DmsError) as raised:
        dms.decimal_degrees("43", "48", "00", "W", axis=dms.LATITUDE)
    assert "N or S" in str(raised.value)

    with pytest.raises(dms.DmsError) as raised:
        dms.decimal_degrees("84", "22", "01", "N", axis=dms.LONGITUDE)
    assert "E or W" in str(raised.value)


def test_the_hemisphere_letter_is_read_case_insensitively():
    """"n" is the same answer as "N" - it is a letter, not an identifier."""
    upper = dms.decimal_degrees("43", "48", "00", "N", axis=dms.LATITUDE)
    lower = dms.decimal_degrees("43", "48", "00", "n", axis=dms.LATITUDE)

    assert lower == upper


@pytest.mark.parametrize("minutes", ["60", "61", "99"])
def test_sixty_minutes_is_refused(minutes):
    """There are 60 minutes in a degree, so they run 0 to 59. 60 is either a
    typo or a different unit, and neither is guessable."""
    with pytest.raises(dms.DmsError) as raised:
        dms.decimal_degrees("43", minutes, "00", "N", axis=dms.LATITUDE)

    assert "60 minutes in a degree" in str(raised.value)


@pytest.mark.parametrize("seconds", ["60", "60.0", "75.5"])
def test_sixty_seconds_is_refused(seconds):
    with pytest.raises(dms.DmsError) as raised:
        dms.decimal_degrees("43", "48", seconds, "N", axis=dms.LATITUDE)

    assert "60 seconds in a minute" in str(raised.value)


def test_fifty_nine_point_nine_nine_seconds_is_accepted():
    """Anti-vacuousness for the two tests above: the boundary is exclusive, so
    everything below it must still go through."""
    value = dms.decimal_degrees("43", "59", "59.99999", "N", axis=dms.LATITUDE)

    # 43 + 59/60 + 59.99999/3600, just under 44.
    assert 43.99 < value < 44.0


def test_a_fractional_degree_or_minute_is_refused():
    """"43.8" in the DEGREES box beside "48" in the minutes box is 43.8 degrees
    plus 48 minutes, which is not what anybody meant. Only seconds carry a
    fraction."""
    with pytest.raises(dms.DmsError) as raised:
        dms.decimal_degrees("43.8", "48", "00", "N", axis=dms.LATITUDE)
    assert "Only the seconds box takes a fraction" in str(raised.value)

    with pytest.raises(dms.DmsError):
        dms.decimal_degrees("43", "48.5", "00", "N", axis=dms.LATITUDE)


@pytest.mark.parametrize("text", ["nan", "inf", "-inf", "Infinity"])
def test_nan_and_infinity_are_refused(text):
    """float() accepts all of these. None of them is an angle, and every one
    survives downstream checks that test a value rather than its finiteness -
    the same reason pnezd refuses them at the file boundary."""
    with pytest.raises(dms.DmsError):
        dms.decimal_degrees(text, "48", "00", "N", axis=dms.LATITUDE)


def test_an_angle_past_the_pole_or_the_antimeridian_is_refused():
    """90 degrees of latitude and 180 of longitude are the ends of the scale."""
    with pytest.raises(dms.DmsError) as raised:
        dms.decimal_degrees("90", "00", "00.1", "N", axis=dms.LATITUDE)
    assert "latitude runs to 90" in str(raised.value)

    with pytest.raises(dms.DmsError) as raised:
        dms.decimal_degrees("180", "00", "01", "W", axis=dms.LONGITUDE)
    assert "longitude runs to 180" in str(raised.value)

    # Anti-vacuousness: the boundary itself is fine.
    assert dms.decimal_degrees("90", "00", "00", "N", axis=dms.LATITUDE) == 90.0
    assert dms.decimal_degrees("180", "00", "00", "W", axis=dms.LONGITUDE) == -180.0


def test_a_nonsense_axis_is_refused_rather_than_defaulted():
    """Callers pass dms.LATITUDE or dms.LONGITUDE. Anything else is a
    programming error, and guessing one would silently apply the wrong range
    limit and the wrong pair of letters."""
    with pytest.raises(dms.DmsError):
        dms.decimal_degrees("43", "48", "00", "N", axis="northing")


def test_every_refusal_is_a_finished_sentence():
    """A refusal that does not say what to do is not much use in the field.

    Sampled across the failure modes rather than asserted on each one
    individually: every message ends in a full stop and names the axis.
    """
    cases = [
        ("", "48", "00", "N", dms.LATITUDE),
        ("-43", "48", "00", "N", dms.LATITUDE),
        ("43", "61", "00", "N", dms.LATITUDE),
        ("43", "48", "61", "N", dms.LATITUDE),
        ("43", "48", "00", "", dms.LATITUDE),
        ("200", "00", "00", "W", dms.LONGITUDE),
        ("abc", "48", "00", "N", dms.LATITUDE),
    ]
    for degrees, minutes, seconds, letter, axis in cases:
        with pytest.raises(dms.DmsError) as raised:
            dms.decimal_degrees(degrees, minutes, seconds, letter, axis=axis)
        message = str(raised.value)
        assert message.rstrip().endswith("."), message
        assert axis in message, message
