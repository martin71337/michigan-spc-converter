"""Zone registry.

Zones are *data*, not code. A new coordinate system - SPCS2022 when NGS
finalizes it - arrives as records added here plus a citation, not as new
mathematics. See docs/DESIGN.md section 6.

Every constant in this module is transcribed from NOAA Manual NOS NGS 5,
Appendix A (PDF p. 77) and Appendix C (PDF pp. 103-104). Appendix C also
publishes the *derived* constants for each zone; those are deliberately NOT
stored here. They are held in tests/fixtures as verification anchors, so that
the derivation in lambert.py is checked against NGS's published values rather
than merely agreeing with a copy of them kept alongside it.

Longitude convention: **all longitudes in this codebase are signed, negative
west.** The manual prints central meridians as positive-west (Michigan North is
"87:00" there, meaning 87 degrees WEST). The conversion happens here, once, at
transcription time. See docs/DESIGN.md section 7.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from michspc.spc.frames import NAD83_2011, ReferenceFrame


def dms(degrees: int, minutes: int = 0, seconds: float = 0.0) -> float:
    """Degrees-minutes-seconds to decimal degrees, magnitude only.

    Appendix A gives standard parallels and central meridians in whole degrees
    and minutes. Writing them as ``dms(45, 29)`` rather than ``45.4833333``
    keeps the transcription checkable against the printed table at a glance.
    """
    return degrees + minutes / 60.0 + seconds / 3600.0


class ProjectionKind(Enum):
    """The conformal projections the State Plane systems are built from.

    SPCS 83 and SPCS2022 both draw from this set (manual chapter 3; SPCS2022
    uses the same three). Only the first is implemented; the others are listed
    so the registry's shape does not have to change when they arrive.
    """

    LAMBERT_CONIC_2SP = "Lambert conformal conic, two standard parallels"
    LAMBERT_CONIC_1SP = "Lambert conformal conic, central parallel and scale factor"
    TRANSVERSE_MERCATOR = "Transverse Mercator (Gauss-Kruger)"
    OBLIQUE_MERCATOR = "Hotine oblique Mercator"


@dataclass(frozen=True)
class LambertTwoParallelDef:
    """Lambert conformal conic defined by two standard parallels.

    This is the SPCS 83 form. The manual's symbols are given for each field so
    the transcription can be checked directly against Appendix A and C.
    """

    lat_south: float
    """phi_s / Bs - southern standard parallel, decimal degrees north."""

    lat_north: float
    """phi_n / Bn - northern standard parallel, decimal degrees north."""

    lat_grid_origin: float
    """phi_b / Bb - latitude of the grid origin, decimal degrees north."""

    lon_origin: float
    """lambda_0 / Lo - central meridian, decimal degrees, NEGATIVE WEST."""

    northing_grid_origin: float
    """N_b - northing assigned to the grid origin, meters ("false northing")."""

    easting_origin: float
    """E_0 - easting assigned to the central meridian, meters ("false easting")."""

    kind: ProjectionKind = ProjectionKind.LAMBERT_CONIC_2SP


@dataclass(frozen=True)
class Zone:
    """One State Plane zone."""

    code: str
    """NGS zone number, e.g. "2113"."""

    abbrev: str
    """Short label used in output file names, e.g. "MI-S"."""

    name: str
    system: str
    """The coordinate system this zone belongs to, e.g. "SPCS 83"."""

    frame: ReferenceFrame
    definition: LambertTwoParallelDef
    citation: str

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    """Approximate geographic extent of the zone's intended area, used only to
    warn when a point falls well outside it. Never used in computation, and
    never a reason to refuse a conversion - a project legitimately straddling a
    zone boundary must still convert (docs/DESIGN.md amendment #1)."""

    band_lat_min: float
    band_lat_max: float
    """The latitude range over which this zone's Appendix C polynomial
    coefficients agree with the rigorous equations to NGS's stated 0.5 mm.

    This is a **measured** property, not a guess and not the same thing as the
    zone's geographic extent. The manual says only that the coefficients were
    fit to ten data points per zone (PDF p. 54); it does not publish the band.
    So the band was measured directly, worst-case across each zone's full
    longitude span, and rounded inward. See docs/DESIGN.md amendment #6.

    It exists for exactly one purpose: to decide whether a disagreement between
    the two engines is a defect (inside the band) or the polynomial method's
    known degradation (outside it). Rounding is always INWARD, so the stored
    band can never claim more than the measurement supports.

    tests/test_polynomial_band.py re-measures and fails if either bound has
    drifted outside the real one."""

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


# --------------------------------------------------------------------------
# Michigan, SPCS 83. All three zones are Lambert conformal conic.
#
# Defining constants: NOAA Manual NOS NGS 5, Appendix A (PDF p. 77) and
# Appendix C (PDF pp. 103-104), which agree with each other.
#
# Michigan legislated International feet as its foot unit (manual Table 1.5,
# PDF p. 19, "Michigan(I)"); the defining constants themselves are metric.
#
# Zone extents are the counties each zone covers, rounded outward to whole
# tenths of a degree. They are a warning aid only.
# --------------------------------------------------------------------------

_APPENDIX = "NOAA Manual NOS NGS 5, Appendix A (PDF p. 77) and Appendix C (PDF pp. 103-104)"

MI_NORTH = Zone(
    code="2111",
    abbrev="MI-N",
    name="Michigan North",
    system="SPCS 83",
    frame=NAD83_2011,
    definition=LambertTwoParallelDef(
        lat_south=dms(45, 29),  # Bs = 45:29
        lat_north=dms(47, 5),  # Bn = 47:05
        lat_grid_origin=dms(44, 47),  # Bb = 44:47
        lon_origin=-dms(87, 0),  # Lo = 87:00 west
        northing_grid_origin=0.0,  # Nb
        easting_origin=8000000.0,  # Eo
    ),
    citation=_APPENDIX,
    lat_min=45.0,
    lat_max=48.4,
    lon_min=-90.5,
    lon_max=-83.4,
    # Measured 0.5 mm agreement band: 44.192 to 48.901. Rounded inward.
    band_lat_min=44.25,
    band_lat_max=48.85,
)

MI_CENTRAL = Zone(
    code="2112",
    abbrev="MI-C",
    name="Michigan Central",
    system="SPCS 83",
    frame=NAD83_2011,
    definition=LambertTwoParallelDef(
        lat_south=dms(44, 11),  # Bs = 44:11
        lat_north=dms(45, 42),  # Bn = 45:42
        lat_grid_origin=dms(43, 19),  # Bb = 43:19
        lon_origin=-dms(84, 22),  # Lo = 84:22 west
        northing_grid_origin=0.0,  # Nb
        easting_origin=6000000.0,  # Eo
    ),
    citation=_APPENDIX,
    lat_min=43.5,
    lat_max=46.0,
    lon_min=-86.7,
    lon_max=-82.9,
    # Measured 0.5 mm agreement band: 43.236 to 46.128. Rounded inward.
    band_lat_min=43.30,
    band_lat_max=46.05,
)

MI_SOUTH = Zone(
    code="2113",
    abbrev="MI-S",
    name="Michigan South",
    system="SPCS 83",
    frame=NAD83_2011,
    definition=LambertTwoParallelDef(
        lat_south=dms(42, 6),  # Bs = 42:06
        lat_north=dms(43, 40),  # Bn = 43:40
        lat_grid_origin=dms(41, 30),  # Bb = 41:30
        lon_origin=-dms(84, 22),  # Lo = 84:22 west
        northing_grid_origin=0.0,  # Nb
        easting_origin=4000000.0,  # Eo
    ),
    citation=_APPENDIX,
    lat_min=41.6,
    lat_max=44.3,
    lon_min=-87.0,
    lon_max=-82.3,
    # Measured 0.5 mm agreement band: 41.403 to 44.312. Rounded inward.
    # Note this band's top edge sits essentially AT the top of the zone's own
    # coverage, so points in the far north of Michigan South are legitimately
    # near the limit of the polynomial cross-check.
    band_lat_min=41.45,
    band_lat_max=44.25,
)


ALL_ZONES: tuple[Zone, ...] = (MI_NORTH, MI_CENTRAL, MI_SOUTH)

_BY_CODE = {zone.code: zone for zone in ALL_ZONES}


def zone_by_code(code: str) -> Zone:
    """Look up a zone by its NGS zone number.

    Refuses an unknown code rather than guessing, and names what is available.
    """
    key = str(code).strip()
    try:
        return _BY_CODE[key]
    except KeyError:
        known = ", ".join(f"{z.code} ({z.name})" for z in ALL_ZONES)
        raise KeyError(
            f"No zone with code {code!r}. This program covers Michigan only; "
            f"known zones are: {known}."
        ) from None
