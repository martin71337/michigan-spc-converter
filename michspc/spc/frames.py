"""Reference frames, and the seam where a datum transformation will go.

A geodetic position is meaningless without the frame it is expressed in. Every
position carried through this program is therefore tagged, and a conversion
whose source and target frames differ is refused rather than performed.

That refusal is the single most important safety property in the program. NAD 83
is being replaced by NATRF2022; the two differ by one to two meters. Passing
coordinates between them as though they were the same thing would produce
numbers that look entirely ordinary and are wrong by more than the width of a
road. See docs/DESIGN.md section 6.
"""

from __future__ import annotations

from dataclasses import dataclass


class FrameMismatchError(Exception):
    """Raised when a conversion would cross reference frames.

    Not a warning and not a silent pass-through: crossing frames requires a
    real datum transformation, and none is implemented yet.
    """


@dataclass(frozen=True)
class ReferenceFrame:
    """A geodetic reference frame."""

    code: str
    name: str
    ellipsoid_name: str
    citation: str


NAD83_2011 = ReferenceFrame(
    code="NAD83(2011)",
    name="North American Datum of 1983, 2011 realization",
    ellipsoid_name="GRS 80",
    citation="NOAA Manual NOS NGS 5, section 1.7, PDF p. 23",
)
"""The frame SPCS 83 coordinates are expressed in.

The mapping equations themselves are realization-independent - NAD83(1986),
NAD83(HARN) and NAD83(2011) all use the same projection - so this program's
projection math is unaffected by the realization. The realization matters only
when a datum transformation is eventually implemented.
"""


NATRF2022 = ReferenceFrame(
    code="NATRF2022",
    name="North American Terrestrial Reference Frame of 2022",
    ellipsoid_name="GRS 80",
    citation="NGS NSRS modernization; SPCS2022 official release 2027",
)
"""Declared but not yet usable.

No zone in this program's registry references it yet, and no transformation to
or from NAD 83 exists. It is present so that the refusal below has something
concrete to refuse, and so the shape of the eventual addition is visible.
"""


ALL_FRAMES: tuple[ReferenceFrame, ...] = (NAD83_2011, NATRF2022)


def require_same_frame(source: ReferenceFrame, target: ReferenceFrame) -> None:
    """Refuse loudly if a conversion would cross reference frames.

    Called on every conversion. Within one frame the zone-to-zone conversion is
    an exact, reversible re-projection of the same physical position and this
    function does nothing.
    """
    if source is target or source.code == target.code:
        return
    raise FrameMismatchError(
        f"Cannot convert from {source.code} to {target.code}: these are "
        f"different reference frames, and no datum transformation between them "
        f"is implemented. Coordinates differ between these frames by one to two "
        f"meters, so passing them through unchanged would silently corrupt "
        f"them. Convert within a single frame, or wait for transformation "
        f"support."
    )
