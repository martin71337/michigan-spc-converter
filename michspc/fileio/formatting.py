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
    latitude / longitude in DMS      5 dp of a second, with a hemisphere letter
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

    **That ordering is the whole carry mechanism, and it is why there is no
    carry guard below.** Rounding happens once, on the total, before either
    divmod. Each divmod then returns a remainder strictly smaller than its
    divisor - that is what divmod means - so ``remainder`` is below 3600 and
    ``seconds`` is below 60 by construction. And because ``total_seconds`` was
    already rounded to ``seconds_decimals`` places, ``seconds`` is too, so
    rounding it a second time cannot move it up to 60 either. Neither boundary
    can be crossed after the split, so nothing after the split needs to catch
    one.

    This is recorded because the function used to carry two guards here, of the
    form "if the seconds rounded up to 60, borrow a minute". They could not
    fire. An independent sweep of 88,612,997 angles - a dense pass at 1e-7 deg
    through the whole convergence domain, every 0.01-arcsecond tick nudged from
    both sides, values engineered to sit exactly on the carry boundaries, and a
    random sample across all seven values of ``seconds_decimals`` - reached
    neither guard once. They were deleted rather than left in place: a check
    that cannot run still tells every later reader that the case is handled,
    which is worse than saying nothing, because the reader stops looking for
    the thing that actually handles it. The rounding order handles it.
    """
    if degrees is None:
        return NOT_AVAILABLE

    sign = "-" if degrees < 0 else "+"
    total_seconds = round(abs(degrees) * 3600.0, seconds_decimals)

    whole_degrees, remainder = divmod(total_seconds, 3600.0)
    whole_minutes, seconds = divmod(remainder, 60.0)

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


def _dms_magnitude(magnitude: float, seconds_decimals: int) -> str:
    """``DD°MM'SS.sssss"`` for an unsigned quantity in decimal degrees.

    ``angle_dms`` is deliberately NOT reused here, and not because reuse would
    be wrong to want. Its output is a different shape - a leading sign, three
    space-separated fields, no symbols - and it is read as text by the audit CSV
    and the job record. Building this string by taking that one apart would make
    one display format depend on another display format's characters, and
    changing either would silently move the other. ``angle_dms`` is left exactly
    as it is, at its settled default of 2 decimals (docs/DESIGN.md amendment #26).

    What IS reused is its arithmetic, verbatim and in the same order: the total
    seconds are rounded ONCE, before both divmods. That ordering is the entire
    carry mechanism and is why there is no carry guard here either - each divmod
    returns a remainder strictly smaller than its divisor, and the seconds were
    already rounded to ``seconds_decimals`` places before the split, so neither
    boundary can be crossed afterwards. ``angle_dms``'s own docstring records the
    88,612,997-angle sweep that established this.
    """
    total_seconds = round(magnitude * 3600.0, seconds_decimals)

    whole_degrees, remainder = divmod(total_seconds, 3600.0)
    whole_minutes, seconds = divmod(remainder, 60.0)

    width = 2 if seconds_decimals == 0 else seconds_decimals + 3
    return (
        f"{int(whole_degrees):02d}°{int(whole_minutes):02d}'"
        f"{seconds:0{width}.{seconds_decimals}f}\""
    )


def latitude_dms(value: float | None, seconds_decimals: int = 5) -> str:
    """``42°43'57.00000"N`` - the owner's format, exactly.

    **Magnitude and a letter, never a sign.** The trailing letter is geographic:
    N above the equator, S below it. It states the direction completely, so a
    minus sign beside it would say the same thing twice - and ``-20°...S`` reads
    like a double negative rather than like a latitude. The owner corrected this
    during the build (docs/DESIGN.md amendment #26).

    Exactly 0.0 is called N. It is a boundary that does not occur in Michigan,
    and calling it S would be no more true.
    """
    if value is None:
        return NOT_AVAILABLE

    hemisphere = "S" if value < 0 else "N"
    return f"{_dms_magnitude(abs(value), seconds_decimals)}{hemisphere}"


def longitude_dms(value: float | None, seconds_decimals: int = 5) -> str:
    """``84°33'19.80000"W`` - the owner's format, exactly.

    ``value`` is the program's own signed, negative-west longitude.

    **Magnitude and a letter, never a sign** - and therefore no convention
    parameter either. W means the position is in the western hemisphere, which
    is a fact about the point rather than about how it was written, so it is
    read from the signed value. The magnitude is the same number under either
    convention, so a DMS longitude is convention-INDEPENDENT: one Michigan
    position reads ``84°33'19.80000"W`` whichever way the file writes its signs.

    That is what lets a longitude be shown at all in a zone-to-zone job, which
    never asks for a convention: there is no sign to interpret, so the interface
    is not answering a question it was never asked. Its decimal-degrees sibling
    ``longitude`` still takes ``positive_west``, because a bare number does have
    to pick one (docs/DESIGN.md amendment #26).

    The owner's first sketch paired a minus with the letter, and he corrected it
    during the build: the two say the same thing, and together they read as a
    double negative.
    """
    if value is None:
        return NOT_AVAILABLE

    hemisphere = "W" if value < 0 else "E"
    return f"{_dms_magnitude(abs(value), seconds_decimals)}{hemisphere}"


DEGREE_SYMBOL = "°"

# --------------------------------------------------------------------------
# Display-only variants
# --------------------------------------------------------------------------
#
# The three below are for the SCREEN and nothing else (docs/DESIGN.md amendment
# #30). Every other function in this module writes files as well as pixels, and
# these deliberately do not.
#
# The distinction is load-bearing, not stylistic. ``latitude`` and ``longitude``
# write the clean PNEZD export's columns two and three, and that file is read
# back by ``pnezd`` before the archive is allowed to take its name
# (``exports._verify_archive``). A degree symbol in it is not a cosmetic change:
# ``float("43.80000000°")`` raises, so the round-trip check would fail and every
# geodetic job would refuse to write. It would also reach the surveyor's CAD
# package, which is the one file in this program that has to be machine-plain.
# ``angle_dms`` likewise writes the audit CSV's Convergence column and the job
# record.
#
# So the symbol is added HERE, once, on top of the file formatter's own output -
# not by a second implementation of the number. The screen and the file
# therefore cannot disagree about a digit; they differ only in punctuation, and
# `tests/test_gui_single_point.py` compares them with the punctuation normalised
# rather than ignoring the comparison.


def latitude_display(value: float | None) -> str:
    """``43.80000000°`` — the file's own string, plus the symbol."""
    text = latitude(value)
    return text if text == NOT_AVAILABLE else f"{text}{DEGREE_SYMBOL}"


def longitude_display(value: float | None, positive_west: bool = False) -> str:
    """``-84.36700000°`` — the file's own string, plus the symbol."""
    text = longitude(value, positive_west=positive_west)
    return text if text == NOT_AVAILABLE else f"{text}{DEGREE_SYMBOL}"


def convergence_display(degrees: float | None, seconds_decimals: int = 2) -> str:
    """``-16°49'17.78"`` — the convergence angle in symbol notation.

    The same angle the audit CSV carries as ``-16 49 17.78``, written the way a
    surveyor reads it off an instrument. Built on ``_dms_magnitude``, which is
    the single definition of this symbol notation in the program — the same one
    ``latitude_dms`` and ``longitude_dms`` use — so the convergence and the two
    geodetic angles cannot come to punctuate themselves differently.

    The sign is carried on the whole quantity and there is no hemisphere letter,
    exactly as ``angle_dms`` does it: a convergence is a rotation, not a
    position, so N/S/E/W would be meaningless. ``angle_dms``'s docstring records
    why the sign sits on the front rather than on the degrees field.
    """
    if degrees is None:
        return NOT_AVAILABLE

    sign = "-" if degrees < 0 else "+"
    return f"{sign}{_dms_magnitude(abs(degrees), seconds_decimals)}"


def geoid_height(value: float | None) -> str:
    """Metres to 3 places, the precision NGS publishes."""
    if value is None:
        return NOT_AVAILABLE
    return f"{value:.3f}"


def millimetres(metres: float | None) -> str:
    """A small linear quantity in millimetres, to 4 places."""
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
