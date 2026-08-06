"""Number formatting, shared by every surface that displays a value.

The screen and the written report read the same data through these functions,
so they cannot disagree about what a number is (docs/method/METHOD.md section 5,
"UI honesty"). If a factor reads 0.99990889 in the results table it reads
0.99990889 in the job record, because the same function produced both strings.

Precision, as specified by the owner:

    northing / easting / elevation   3 dp in feet, 4 dp in meters
    grid, elevation, combined factor 8 dp
    convergence angle                degrees-minutes-seconds to 0.01 second
    latitude / longitude             8 dp
    geoid height                     3 dp (metres), matching what NGS publishes
"""

from __future__ import annotations

import math

from michspc.spc.units import LinearUnit

NOT_AVAILABLE = "N/A"
"""What a genuinely absent value looks like in every output.

Never a blank cell, which reads as an oversight, and never a plausible number.
The owner asked for this string specifically.
"""


def coordinate(value: float | None, unit: LinearUnit) -> str:
    """A northing, easting or elevation, at the unit's own precision."""
    if value is None:
        return NOT_AVAILABLE
    return f"{value:.{unit.decimals}f}"


def factor(value: float | None) -> str:
    """A grid, elevation or combined factor to 8 decimal places.

    Returns "N/A" for an absent factor - which happens whenever a point had no
    usable elevation. That is a real absence, not a formatting fallback.
    """
    if value is None:
        return NOT_AVAILABLE
    return f"{value:.8f}"


def angle_dms(degrees: float | None, seconds_decimals: int = 2) -> str:
    """Decimal degrees to signed degrees-minutes-seconds.

    Used for the convergence angle, which surveyors read in DMS and which NGS
    publishes the same way. The sign is carried on the whole quantity, not on
    the degrees field alone, so a convergence of -0.25 degrees formats as
    "-00 15 00.00" rather than "-0 15 00.00" or "00 -15 00.00".

    Rounding is done on the total seconds before splitting, so 59.999 seconds
    carries into the next minute instead of printing "60.00".
    """
    if degrees is None:
        return NOT_AVAILABLE

    sign = "-" if degrees < 0 else "+"
    total_seconds = round(abs(degrees) * 3600.0, seconds_decimals)

    whole_degrees, remainder = divmod(total_seconds, 3600.0)
    whole_minutes, seconds = divmod(remainder, 60.0)

    # Guard the carry that rounding can create at each boundary.
    if round(seconds, seconds_decimals) >= 60.0:
        seconds -= 60.0
        whole_minutes += 1
    if whole_minutes >= 60.0:
        whole_minutes -= 60
        whole_degrees += 1

    width = 2 if seconds_decimals == 0 else seconds_decimals + 3
    return (
        f"{sign}{int(whole_degrees):02d} {int(whole_minutes):02d} "
        f"{seconds:0{width}.{seconds_decimals}f}"
    )


def latitude(value: float | None) -> str:
    """Decimal degrees to 8 places, about one millimetre."""
    if value is None:
        return NOT_AVAILABLE
    return f"{value:.8f}"


def longitude(value: float | None, positive_west: bool = False) -> str:
    """Decimal degrees to 8 places.

    ``positive_west`` emits the manual's convention instead of the signed one.
    The program stores signed, negative-west longitudes everywhere; this is the
    only place the other convention may appear, and only because the user
    explicitly asked for it.
    """
    if value is None:
        return NOT_AVAILABLE
    return f"{-value if positive_west else value:.8f}"


def geoid_height(value: float | None) -> str:
    """Metres to 3 places, the precision NGS publishes."""
    if value is None:
        return NOT_AVAILABLE
    return f"{value:.3f}"


def millimetres(metres: float | None) -> str:
    """An engine-agreement discrepancy, in millimetres to 4 places."""
    if metres is None:
        return NOT_AVAILABLE
    return f"{metres * 1000.0:.4f}"


def signed_parts_per_million(value: float | None) -> str:
    """A factor expressed as parts per million from unity.

    Surveyors reason about scale in ppm far more readily than in the eighth
    decimal place: a combined factor of 0.99993 is "70 ppm short".
    """
    if value is None:
        return NOT_AVAILABLE
    return f"{(value - 1.0) * 1e6:+.1f}"


def describe_convergence(degrees: float | None) -> str:
    """Convergence with its meaning spelled out, for the job record.

    Grid north lies east of true north when convergence is negative and west of
    it when positive, so the report says which rather than leaving the reader to
    remember the convention.
    """
    if degrees is None:
        return NOT_AVAILABLE
    if degrees == 0.0:
        return f"{angle_dms(degrees)} (on the central meridian; grid north is true north)"
    direction = "west" if degrees > 0 else "east"
    return f"{angle_dms(degrees)} (grid north lies {direction} of true north)"


def is_finite(value) -> bool:
    """Reject NaN and infinity before they reach a file.

    A NaN written to a CSV becomes the text "nan", which imports into CAD as
    zero or as a parse error depending on the package. Neither is acceptable on
    a coordinate, so writers check this rather than trusting the arithmetic.
    """
    return isinstance(value, (int, float)) and math.isfinite(value)
