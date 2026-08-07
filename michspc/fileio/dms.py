"""Degrees, minutes and seconds typed in — composed into decimal degrees.

The exact inverse of ``formatting.latitude_dms`` and
``formatting.longitude_dms``, and it lives beside them on purpose: those two
functions define what a DMS angle looks like in this program, and a parser that
did not read back what they write would be a second, disagreeing definition of
the same format. ``tests/test_dms.py`` pins the round trip in both directions.

**Why this is in ``fileio`` and not in ``michspc.gui``.** Composing d + m/60 +
s/3600 is arithmetic on a coordinate, and the interface layer is forbidden to
produce a domain value (docs/DESIGN.md §9). The GUI collects four strings from
four boxes and hands them here; what comes back is the text the decimal-degrees
box would have held, which then goes through ``pnezd.parse_typed_point`` — the
same single validation gate as every other route into the program. So this adds
a step in front of the gate; it does not add a second gate.

**The hemisphere letter, not a sign.** Direction is stated by ``N``/``S`` and
``E``/``W``, exactly as the panel displays it. A minus sign in the degrees box is
refused rather than combined with the letter: ``-84`` with ``W`` says west twice
and could as easily have been meant as east, and this program does not guess
(docs/DESIGN.md §1).

**On the longitude sign convention.** A DMS longitude is convention-independent
— ``formatting.longitude_dms`` records why: the magnitude is the same number
under both conventions and the letter is a fact about the point rather than
about how a file writes its signs. So the letter alone fixes the position. The
``positive_west`` argument does not change *which point* this is; it only decides
how that one position is written as a bare number, so that what comes back is
what the user would have typed into the decimal box under the convention they
selected. The pin for that: the same DMS entry converts to the same coordinate
under both conventions, where the same DECIMAL entry converts to two points 340
miles apart. That difference is the whole reason the convention selector exists.
"""

from __future__ import annotations

import math

LATITUDE = "latitude"
LONGITUDE = "longitude"

HEMISPHERES = {
    LATITUDE: ("N", "S"),
    LONGITUDE: ("E", "W"),
}
"""Which letters each axis accepts, in the order the dropdown offers them."""

NEGATIVE_HEMISPHERES = frozenset({"S", "W"})
"""The two that mean a negative signed angle, in the program's own
negative-west, negative-south convention."""

MAX_DEGREES = {
    LATITUDE: 90.0,
    LONGITUDE: 180.0,
}


class DmsError(Exception):
    """A typed DMS angle could not be read.

    Names the component and says what is wrong with it, like every other
    refusal in this program. Raised before anything is converted, so nothing
    partial reaches the screen.
    """


def _component(text: str, name: str, axis: str, *, whole: bool) -> float:
    """One box's contents as a number, or a refusal naming that box."""
    cleaned = text.strip()
    if not cleaned:
        raise DmsError(
            f"The {axis} {name} box is empty. All four boxes - degrees, "
            f"minutes, seconds and the hemisphere - have to be filled in. A "
            f"blank box is not read as zero: a minutes field left empty by "
            f"accident would move the point up to a mile with nothing said."
        )

    if cleaned.startswith(("+", "-")):
        raise DmsError(
            f"The {axis} {name} box reads {cleaned!r}. Degrees, minutes and "
            f"seconds are written as magnitudes here, without a sign - the "
            f"hemisphere letter states the direction. '-84' with 'W' says west "
            f"twice, and it could equally have been meant as east, so it is "
            f"refused rather than guessed."
        )

    try:
        value = float(cleaned)
    except ValueError:
        raise DmsError(
            f"The {axis} {name} box reads {cleaned!r}, which is not a number."
        ) from None

    if not math.isfinite(value):
        raise DmsError(
            f"The {axis} {name} box reads {cleaned!r}, which is not a usable "
            f"number. 'nan' and 'inf' are refused wherever an angle is expected."
        )

    if whole and value != int(value):
        raise DmsError(
            f"The {axis} {name} box reads {cleaned!r}. Only the seconds box "
            f"takes a fraction; write the remainder in the boxes to its right."
        )

    return value


def decimal_degrees(
    degrees: str,
    minutes: str,
    seconds: str,
    hemisphere: str,
    *,
    axis: str,
) -> float:
    """The four boxes as one signed angle, negative south and negative west.

    This is the program's own signed convention — the one
    ``formatting.latitude_dms`` and ``formatting.longitude_dms`` read.
    """
    if axis not in HEMISPHERES:
        raise DmsError(f"{axis!r} is neither {LATITUDE!r} nor {LONGITUDE!r}.")

    letter = hemisphere.strip().upper()
    if letter not in HEMISPHERES[axis]:
        allowed = " or ".join(HEMISPHERES[axis])
        raise DmsError(
            f"The {axis} hemisphere is {hemisphere.strip()!r}; it has to be "
            f"{allowed}. The letter is what states which side of the equator "
            f"or the meridian this point is on, and nothing is assumed here "
            f"when it is missing: the interface opens its dropdown on a real "
            f"letter, and this function will not invent one for a caller that "
            f"passes none."
        )

    whole_degrees = _component(degrees, "degrees", axis, whole=True)
    whole_minutes = _component(minutes, "minutes", axis, whole=True)
    real_seconds = _component(seconds, "seconds", axis, whole=False)

    if whole_minutes >= 60.0:
        raise DmsError(
            f"The {axis} minutes box reads {minutes.strip()!r}. There are 60 "
            f"minutes in a degree, so minutes run from 0 to 59."
        )
    if real_seconds >= 60.0:
        raise DmsError(
            f"The {axis} seconds box reads {seconds.strip()!r}. There are 60 "
            f"seconds in a minute, so seconds run from 0 up to but not "
            f"including 60."
        )

    magnitude = whole_degrees + whole_minutes / 60.0 + real_seconds / 3600.0

    limit = MAX_DEGREES[axis]
    if magnitude > limit:
        raise DmsError(
            f"That is {magnitude:.6f} degrees of {axis}, and {axis} runs to "
            f"{limit:g}. Check the degrees box - {degrees.strip()!r} - against "
            f"the value you meant."
        )

    return -magnitude if letter in NEGATIVE_HEMISPHERES else magnitude


def decimal_degrees_text(
    degrees: str,
    minutes: str,
    seconds: str,
    hemisphere: str,
    *,
    axis: str,
    positive_west: bool,
) -> str:
    """The four boxes as the text the decimal-degrees box would have held.

    ``repr`` rather than a fixed number of places: it is the shortest string
    that reads back as the identical float, so nothing is lost between here and
    ``pnezd._parse_number``. A ``f"{value:.8f}"`` would silently round the
    typed angle to about a millimetre before it was ever converted.

    ``positive_west`` re-signs a LONGITUDE into the convention the user
    selected, so that what goes down the pipeline is indistinguishable from a
    typed decimal. Latitude ignores it — the sign of a latitude is not a
    convention, and there is no positive-south anything.
    """
    value = decimal_degrees(degrees, minutes, seconds, hemisphere, axis=axis)

    if axis == LONGITUDE and positive_west:
        value = -value

    return repr(value)
