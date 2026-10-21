"""NGS HTDP v3.6.0's frame transformation, transcribed: WGS 84 and ITRF to and from NAD 83(2011).

A WGS 84 or ITRF position is not a NAD 83 position. In Michigan the two differ
by about a metre north, a metre west and a metre down (review/wgs84-w0/RECON.md
section 3), and they drift apart by a further 17 mm a year because NAD 83 is
fixed to the North American plate and the global frames are not. This module
moves a position between them the way the National Geodetic Survey's own
program does - HTDP v3.6.0, ``github.com/noaa-ngs/HTDP`` commit
``59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c`` - and for no other paths.

**A transcription, not a reimplementation.** The owner's standing rule is to
replicate NOAA, because NOAA is the authority (DESIGN.md #36, #38). So every
routine below follows HTDP's Fortran operation for operation, in its own
order, with its own constants, and cites the lines it follows. Where HTDP makes
a choice a geodesist might make differently, the choice is HTDP's and it is
copied, never improved:

* the Helmert is evaluated at the INPUT epoch, whichever direction is run
  (``htdp.f:3229-3235``), so the path is not symmetric: WGS 84 at t to
  NAD 83 at 2010.0 is Helmert(t) plus NAD 83's small intraplate velocity,
  while the reverse is Helmert(2010.0) plus the full plate motion of the
  global frame;
* the rotations are linearized and ``toit94`` NEGATES the parameters rather
  than inverting the transformation (``htdp.f:4572-4617``);
* the velocity comes from a 0.5 degree grid of ITRF2008 velocities,
  interpolated bilinearly in degrees (``GRDWEI``, ``htdp.f:1542-1631``), at a
  lookup position ``PREDV`` computes by treating the output-frame position as
  if it were in the INPUT frame and mapping that to ITRF2008 - with the IERS
  Helmert convention when the input frame is neither NAD 83 nor ITRF2008
  (``htdp.f:7426-7439``, ``2733-2743``);
* the velocity is carried into the output frame with ``VTRANF``, using the
  input frame's Cartesian position (``htdp.f:3255-3271``);
* it is turned into an angular rate with radii of curvature that carry NO
  height term, on GRS 80 even for a WGS 84 frame, because ``PREDV`` resets the
  ellipsoid before ``NEWCOR`` runs (``htdp.f:7465-7466``, ``976-988``);
* the velocity runs on a clock of whole minutes in Julian years, while the
  Helmert runs on the calendar-year fraction (``htdp.f:7322``, ``7913-7920``);
* the output radians are turned into degrees with a TRUNCATED pi
  (``htdp.f:2766``);
* the ellipsoid follows the frame's NAME: WGS84(...) frames use the WGS 84
  ellipsoid, everything else GRS 80 (``htdp.f:3221-3224``, ``3240-3243``) - so
  WGS84(G2296) and ITRF2020 share every Helmert parameter and still differ by
  about 0.1 mm from identical input numbers;
* when the two dates fall on the same day, HTDP applies the Helmert and no
  velocity at all (``htdp.f:3245``, ``3276-3283``).

The consequence worth knowing: the forward and reverse transformations are not
exact inverses. HTDP's own round trip fails to close by up to about 6e-5 m
east (RECON.md section 5). That is replicated, and pinned against HTDP's own
round-trip records, not smoothed.

**What is verified, and against what.** ``tests/test_htdp.py`` reproduces HTDP's
printed output - 1e-10 degree, 1 mm - on every frozen anchor in
``tests/fixtures/htdp_anchors.py``, taken from NGS's source compiled in the
container (review/wgs84-w0/), and on the records of
``tests/fixtures/htdp_near_tie_anchors.py``: inputs tuned, with W0's
independent transcription, to put one component's result beside a rounding
tie of HTDP's print - where an ulp's change in the order of operations moves
the printed digit - and to put the velocity lookup either side of each edge
of the window below (interim gate 1 of the WGS 84 build, findings L2 and L3).
The W0 transcription this module descends from matched that binary on 45,408
of 45,408 printed records. NGS's own 32-bit Windows build was not run (plan
section 7, still human).

**Exactly these paths and nothing wider.** NAD 83(2011) at its reference epoch
2010.0 (plan D1) to or from one of five time-dependent frames - WGS84(G1762),
WGS84(G2139), WGS84(G2296), ITRF2014 and ITRF2020 - in Michigan. Every refusal
below is a boundary of that scope, stated by name:

* a lookup position outside the transcribed window of the velocity grid
  (``htdp_data.WINDOW_I_RANGE``, ``WINDOW_J_RANGE``), or at or north of the
  50.0 N edge of HTDP's region 6 - never extrapolated;
* an ``FRMXYZ`` that does not converge, where HTDP would ``STOP 666``;
* a frame not in the table, a pair that is not NAD 83 against one of the five,
  and an epoch that is not an ``ObservationEpoch`` built from a calendar date.

**Longitude is NEGATIVE WEST here**, as everywhere in this program (DESIGN.md
section 7). HTDP is positive west internally and in its files; the sign is
changed once on the way in and once on the way out, and nowhere else.

Stdlib only, no file I/O: the constants are ``htdp_data``'s transcription,
which the suite holds to the committed Fortran number for number. If/raise
throughout, never assert: the suite and the shipped program run under ``-O``.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Mapping

from michspc.spc import htdp_data
from michspc.spc.htdp_data import (
    GRID6_WINDOW,
    IERS_CONVENTION,
    IGS_CONVENTION,
    PI,
    RHOSEC,
    TWOPI,
    HelmertParameters,
)


# --------------------------------------------------------------------------
# Refusals.
# --------------------------------------------------------------------------


class HtdpRefusal(Exception):
    """Base class for every refusal in this module.

    A caller that only needs "the frame transformation was refused, say why"
    catches this. The subclasses separate the cases a surveyor is told
    differently: a position this program has no velocity model for, an input
    that is not a frame or a date, and the arithmetic itself failing.
    """


class HtdpFrameError(HtdpRefusal):
    """A frame or a pair of frames this module does not carry."""


class HtdpEpochError(HtdpRefusal):
    """An observation epoch that is not a calendar date HTDP accepts."""


class HtdpInputError(HtdpRefusal):
    """A latitude, longitude or height that is not a usable number."""


class HtdpVelocityGridError(HtdpRefusal):
    """A position outside the transcribed window of HTDP's velocity grid.

    Never extrapolated: a velocity read off the edge of the transcription
    would be a number this program made up, presented as NGS's.

    Carries the refused position as data - ``latitude`` and ``longitude``
    (decimal degrees, negative west, as ``transform`` took them),
    ``position_frame`` (the name of the frame THAT position is in: the
    transform's source) and ``reason`` (why it was refused, without advice) -
    so a caller that knows where the position came from can say so in its
    own words (interim gate 2 of the WGS 84 build, finding L4: ``job.run``
    names the point, and gives advice only where it applies). All four are
    None on the defect-only refusal of ``_window_node``.
    """

    def __init__(
        self,
        message: str,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
        position_frame: str | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.latitude = latitude
        self.longitude = longitude
        self.position_frame = position_frame
        self.reason = reason


class HtdpConvergenceError(HtdpRefusal):
    """``FRMXYZ`` failed to converge - where HTDP itself would ``STOP 666``."""


# --------------------------------------------------------------------------
# Ellipsoids: MODEL (htdp.f:140-176).
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HtdpEllipsoid:
    """One of the two ellipsoids HTDP's ``MODEL`` can load for these frames.

    ``elpsd`` is HTDP's own five-character token. The derived constants are
    written exactly as ``MODEL`` writes them (``htdp.f:161-163``), as
    properties, so nothing derived is stored beside the definition.
    """

    elpsd: str
    inverse_flattening: float

    @property
    def a(self) -> float:
        # htdp.f:151, A = 6378137.D0 for both GRS 80 and WGS 84.
        return htdp_data.SEMI_MAJOR_AXIS_M

    @property
    def f(self) -> float:
        # htdp.f:152 and 154, F = 1.D0 / 298.257...D0.
        return 1.0 / self.inverse_flattening

    @property
    def e2(self) -> float:
        # htdp.f:161, E2 = F*(2.D0 - F).
        f = self.f
        return f * (2.0 - f)

    @property
    def af(self) -> float:
        # htdp.f:162, AF = A / (1.D0 - F).
        return self.a / (1.0 - self.f)

    @property
    def eps(self) -> float:
        # htdp.f:163, EPS = F*(2.D0 - F) / ((1.D0 -F)**2). gfortran expands a
        # constant integer power of two into one multiplication.
        f = self.f
        return f * (2.0 - f) / ((1.0 - f) * (1.0 - f))


GRS80 = HtdpEllipsoid(
    elpsd="GRS80",
    inverse_flattening=htdp_data.GRS80_INVERSE_FLATTENING,
)
"""HTDP's default ellipsoid (``htdp.f:60``, ``152``), used for NAD 83 and ITRF."""

WGS84_ELLIPSOID = HtdpEllipsoid(
    elpsd="WGS84",
    inverse_flattening=htdp_data.WGS84_INVERSE_FLATTENING,
)
"""Loaded when the frame's name begins ``WGS84`` (``htdp.f:154``, ``3224``)."""


# --------------------------------------------------------------------------
# Frames: MENU1 (htdp.f:4667-4797).
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HtdpFrame:
    """A reference frame as HTDP's ``MENU1`` defines it.

    Three facts, all HTDP's own: the number a user types at the menu, the
    internal index every parameter array is subscripted by, and the
    24-character name. The ellipsoid is NOT a fourth field: HTDP chooses it
    from the first five characters of the name (``htdp.f:3221-3224`` for the
    input frame, ``3240-3243`` for the output), so it is derived from the name
    here too, and the record cannot state an ellipsoid HTDP would not use.
    """

    menu: int
    iopt: int
    htdp_name: str
    """Exactly as ``MENU1`` stores it, trailing blanks and all."""

    @property
    def ellipsoid(self) -> HtdpEllipsoid:
        # htdp.f:3221-3224 (and 3240-3243 for frame2): GRS80 unless the name
        # begins 'WGS72' or 'WGS84'. No offered frame is WGS72.
        if self.htdp_name[:5] == "WGS84":
            return WGS84_ELLIPSOID
        return GRS80

    @property
    def name(self) -> str:
        """The name without MENU1's padding, for messages and records."""
        return self.htdp_name.rstrip()

    def __str__(self) -> str:
        return self.name


NAD83_2011 = HtdpFrame(
    menu=1,
    iopt=1,
    htdp_name="NAD_83(2011/CORS96/2007)",  # htdp.f:4677-4678
)
"""NAD 83(2011), plate-fixed: always at epoch 2010.0 here (plan D1)."""

WGS84_G1762 = HtdpFrame(
    menu=10,
    iopt=15,
    htdp_name="WGS84(G1762)            ",  # htdp.f:4704-4705
)
"""In force from 2013-10-16; HTDP uses ITRF2008's parameters for it
(``htdp.f:4767``: "ITRF2008=IGS08=IGb08 used")."""

WGS84_G2139 = HtdpFrame(
    menu=11,
    iopt=16,
    htdp_name="WGS84(G2139)            ",  # htdp.f:4707-4708
)
"""In force from 2021-01-03; ITRF2014's parameters (``htdp.f:4768``)."""

WGS84_G2296 = HtdpFrame(
    menu=12,
    iopt=17,
    htdp_name="WGS84(G2296)            ",  # htdp.f:4710-4711
)
"""In force from 2024-01-07; ITRF2020's parameters (``htdp.f:4769``)."""

ITRF2014 = HtdpFrame(
    menu=25,
    iopt=16,
    htdp_name="ITRF2014 or IGS14/IGb14 ",  # htdp.f:4749-4750
)
"""Offered by name for PPP output (plan section 1, owner's decision 2)."""

ITRF2020 = HtdpFrame(
    menu=26,
    iopt=17,
    htdp_name="ITRF2020 or IGS20/IGb20 ",  # htdp.f:4752-4753
)
"""Offered by name for PPP output (plan section 1, owner's decision 2)."""


TIME_DEPENDENT_FRAMES: tuple[HtdpFrame, ...] = (
    WGS84_G1762,
    WGS84_G2139,
    WGS84_G2296,
    ITRF2014,
    ITRF2020,
)
"""The five frames this module moves to and from NAD 83(2011), in the order the
owner's scope names them (plan section 1)."""

ALL_HTDP_FRAMES: tuple[HtdpFrame, ...] = (NAD83_2011,) + TIME_DEPENDENT_FRAMES

_FRAMES_BY_MENU: Mapping[int, HtdpFrame] = {
    frame.menu: frame for frame in ALL_HTDP_FRAMES
}


def frame_by_menu(menu: int) -> HtdpFrame:
    """The offered frame HTDP numbers ``menu`` in ``MENU1``, or a refusal."""
    try:
        return _FRAMES_BY_MENU[menu]
    except (KeyError, TypeError):
        offered = ", ".join(f"{f.menu} {f.name}" for f in ALL_HTDP_FRAMES)
        raise HtdpFrameError(
            f"HTDP menu number {menu!r} is not a frame this program carries. "
            f"The offered frames are: {offered}."
        ) from None


# --------------------------------------------------------------------------
# Dates: GETMDY option 1 (htdp.f:7886-7922) and IYMDMJ (htdp.f:7997-8084).
# --------------------------------------------------------------------------


def _iymdmj(iyr: int, imon: int, iday: int) -> int:
    """HTDP's modified Julian date of a calendar date. ``htdp.f:7997-8084``.

    Duffett-Smith's algorithm as HTDP writes it, including its truncations:
    ``IDINT`` truncates toward zero, as Python's ``int`` of a float does.
    """
    iyrp = iyr  # htdp.f:8056
    if imon < 3:  # htdp.f:8060-8065
        iyrp = iyrp - 1
        imop = imon + 12
    else:
        imop = imon
    a = int(float(iyrp) * 0.01)  # htdp.f:8077
    b = 2 - a + int(float(a) * 0.25)  # htdp.f:8078
    c = int(365.25 * float(iyrp))  # htdp.f:8079
    d = int(30.6001 * float(imop + 1))  # htdp.f:8080
    return b + c + d + iday - 679006  # htdp.f:8081


_INTEGER4_MAX = 2**31 - 1
"""HTDP holds minutes in a default INTEGER (``IMPLICIT INTEGER*4 (I-N)``,
``htdp.f:7854``), so ``MINS = MJD * 24 * 60`` (``htdp.f:7920``) cannot exceed
this. A date past it would wrap inside HTDP; it is refused here instead."""


ITREF = _iymdmj(*htdp_data.VELOCITY_REFERENCE_DATE) * 24 * 60
"""HTDP's velocity-clock origin, 00:00 UTC on 2010-01-01, in minutes of MJD
(``htdp.f:169-173``: ``ITREF = MJD * 24 * 60``)."""


@dataclass(frozen=True)
class ObservationEpoch:
    """The day a position was observed, as a calendar date. Nothing else.

    The owner's decision (plan section 1, decision 3): the epoch is ENTERED as
    a calendar date and converted the way HTDP converts one. There is
    deliberately no decimal-year constructor. HTDP's decimal entry derives its
    velocity clock by truncating a floating-point day count, and that
    truncation often lands a day early - 2026.8 runs the clock from
    2026-10-19 although 2026 + 292/365 is 2026-10-20 (RECON.md section 1.5).

    ``date`` is the one authoritative fact. HTDP's two derived quantities are
    properties computed from it by HTDP's own arithmetic, never stored beside
    it:

    * ``decimal_year`` - HTDP's ``DATE``, the Helmert's clock: the year plus
      the day-of-year fraction over a 365- or 366-day year
      (``htdp.f:7913-7919``);
    * ``minutes`` - HTDP's ``MINS``, the velocity's clock: the MJD of 00:00
      UTC on that date, in minutes (``htdp.f:7920``).

    Validation is this program's, not HTDP's. HTDP checks only year > 1906,
    month 1-12 and day 1-31, and accepts 30 February as 2 March (RECON.md
    section 1.5, driven). A ``datetime.date`` cannot hold an impossible day,
    so building from one closes that; HTDP's own year rule is applied on top.
    """

    date: datetime.date

    def __post_init__(self) -> None:
        value = self.date
        # datetime.datetime IS a datetime.date, and would carry a time of day
        # this record would silently drop. HTDP's calendar entry has no time
        # of day: the date means 00:00 UTC (htdp.f:7879-7880).
        if isinstance(value, datetime.datetime) or not isinstance(
            value, datetime.date
        ):
            raise HtdpEpochError(
                f"An observation epoch is a calendar date - a datetime.date - "
                f"and nothing else; got {type(value).__name__} ({value!r}). "
                f"HTDP's calendar entry means 00:00 UTC at the start of the "
                f"date, so a time of day would be dropped without a word, and "
                f"a decimal year is not accepted at all: HTDP's decimal entry "
                f"often runs its velocity clock a day early. Enter the date "
                f"the position was observed."
            )
        if value.year <= htdp_data.EARLIEST_YEAR_EXCLUSIVE:
            raise HtdpEpochError(
                f"Observation date {value.isoformat()} is in "
                f"{value.year}; HTDP's model is not valid for dates before "
                f"1907 (htdp.f:7891-7896, 'The model is not valid for dates "
                f"prior to 1906', refusing 1906 itself). Check the year."
            )
        if self.minutes > _INTEGER4_MAX:
            raise HtdpEpochError(
                f"Observation date {value.isoformat()} is beyond the last "
                f"date HTDP's integer minute clock can hold (htdp.f:7920). "
                f"Check the year."
            )

    @property
    def mjd(self) -> int:
        """HTDP's ``MJD`` for this date (``htdp.f:7913``)."""
        return _iymdmj(self.date.year, self.date.month, self.date.day)

    @property
    def decimal_year(self) -> float:
        """HTDP's ``DATE`` (``htdp.f:7913-7919``) - the Helmert's clock."""
        iyear = self.date.year
        mjd0 = _iymdmj(iyear, 1, 1)  # htdp.f:7914
        mjd1 = _iymdmj(iyear + 1, 1, 1)  # htdp.f:7915-7916
        day = float(self.mjd - mjd0)  # htdp.f:7917
        denom = float(mjd1 - mjd0)  # htdp.f:7918
        return float(iyear) + (day / denom)  # htdp.f:7919

    @property
    def minutes(self) -> int:
        """HTDP's ``MINS`` (``htdp.f:7920``) - the velocity's clock."""
        return self.mjd * 24 * 60

    def __str__(self) -> str:
        return self.date.isoformat()


NAD83_2011_EPOCH = ObservationEpoch(datetime.date(2010, 1, 1))
"""The epoch of every NAD 83(2011) position here: 2010.0 (plan D1).

2010-01-01 through HTDP's calendar arithmetic gives ``DATE`` = 2010.0 exactly
and ``MINS`` = ``ITREF`` - the same two numbers HTDP's decimal entry ``2010.0``
gives (``htdp.f:7941-7963``: a zero fraction truncates to day 1 of January),
which is how W0's frozen runs entered it. Pinned in the suite."""


# --------------------------------------------------------------------------
# The result.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HtdpVelocity:
    """The velocity HTDP applied, in mm/yr, in the OUTPUT frame.

    What ``TRFPOS`` hands ``NEWCOR`` after ``VTRANF`` and ``TOVNEU``
    (``htdp.f:3264-3273``). Up is not a vertical-motion model: grid 6's up
    velocity is 0.00 at every node, and what remains is the frames'
    translation-rate and scale-rate terms (RECON.md section 3).
    """

    north_mm_per_yr: float
    east_mm_per_yr: float
    up_mm_per_yr: float


@dataclass(frozen=True)
class HtdpResult:
    """One position, transformed as HTDP transforms it, and what was done.

    The stored fields are the output and the facts a job record states. The
    rest - the Helmert's epoch, the velocity clock's span - are derived from
    those by HTDP's rules, so the record cannot state one and have computed
    another.
    """

    latitude: float
    """Decimal degrees, in ``target_frame`` at ``target_epoch``."""

    longitude: float
    """Decimal degrees, NEGATIVE WEST."""

    ellipsoid_height: float
    """Metres above ``target_frame``'s ellipsoid as HTDP uses it."""

    source_frame: HtdpFrame
    source_epoch: ObservationEpoch
    target_frame: HtdpFrame
    target_epoch: ObservationEpoch

    velocity: HtdpVelocity | None
    """``None`` when the two dates are the same day: HTDP then applies the
    Helmert and no velocity at all (``htdp.f:3245``, ``3276-3283``)."""

    @property
    def helmert_epoch(self) -> ObservationEpoch:
        """The epoch the Helmert was evaluated at: ALWAYS the input's.

        ``TOIT94`` and ``FRIT94`` both take ``date1`` (``htdp.f:3230-3231``),
        whichever direction is run.
        """
        return self.source_epoch

    @property
    def velocity_clock_minutes(self) -> int:
        """``MIN2 - MIN1``: the span ``NEWCOR`` propagates over, in minutes."""
        return self.target_epoch.minutes - self.source_epoch.minutes

    @property
    def velocity_clock_years(self) -> float:
        """The same span in HTDP's Julian years (``htdp.f:7322``).

        Negative when the target epoch is earlier: a 2026 WGS 84 position
        carried to NAD 83 at 2010.0 runs the velocity backwards.
        """
        return float(self.velocity_clock_minutes) / htdp_data.MINUTES_PER_JULIAN_YEAR


# --------------------------------------------------------------------------
# Geometry: TOXYZ, FRMXYZ, RADII, TOVNEU, TOVXYZ.
# --------------------------------------------------------------------------


def _toxyz(
    glat: float, glon: float, eht: float, ellipsoid: HtdpEllipsoid
) -> tuple[float, float, float]:
    """Geodetic to Cartesian, closed form. ``htdp.f:895-916``.

    ``glon`` is EAST longitude in radians, as HTDP passes it (``-ylon``).
    """
    e2 = ellipsoid.e2
    slat = math.sin(glat)  # htdp.f:906
    clat = math.cos(glat)  # htdp.f:907
    w = math.sqrt(1.0 - e2 * slat * slat)  # htdp.f:908
    en = ellipsoid.a / w  # htdp.f:909
    x = (en + eht) * clat * math.cos(glon)  # htdp.f:911
    y = (en + eht) * clat * math.sin(glon)  # htdp.f:912
    z = (en * (1.0 - e2) + eht) * slat  # htdp.f:913
    return x, y, z


def _frmxyz(
    x: float, y: float, z: float, ellipsoid: HtdpEllipsoid
) -> tuple[float, float, float]:
    """Cartesian to geodetic by HTDP's iteration. ``htdp.f:919-974``.

    Returns (latitude rad, EAST longitude rad, ellipsoid height m). Iterates on
    the tangent of the latitude to HTDP's tolerance and cap, and switches its
    height formula at |latitude| = 0.7854 rad, 45.00002 degrees - inside
    Michigan (``htdp.f:957-961``). Where HTDP's function returns ``.false.``
    and every caller then ``STOP 666`` (``htdp.f:2746``, ``3246``, ``3280``),
    this raises.
    """
    a = ellipsoid.a
    e2 = ellipsoid.e2
    ae2 = a * e2  # htdp.f:932
    p = math.sqrt(x * x + y * y)  # htdp.f:936
    if p == 0.0:
        # Not reachable from a position inside the velocity window; HTDP would
        # divide by zero here. Refused rather than computed.
        raise HtdpConvergenceError(
            f"Cannot convert the Cartesian position ({x!r}, {y!r}, {z!r}) to "
            f"latitude and longitude: it lies on the polar axis, where HTDP's "
            f"FRMXYZ divides by zero (htdp.f:938). Check the position."
        )
    icount = 0  # htdp.f:937
    tgla = z / p / (1.0 - e2)  # htdp.f:938
    while icount <= htdp_data.FRMXYZ_MAX_ITERATIONS:  # htdp.f:942
        tglax = tgla  # htdp.f:943
        tgla = z / (p - (ae2 / math.sqrt(1.0 + (1.0 - e2) * tgla * tgla)))  # :944
        icount = icount + 1  # htdp.f:945
        if abs(tgla - tglax) > htdp_data.FRMXYZ_TOLERANCE:  # htdp.f:946
            continue
        glat = math.atan(tgla)  # htdp.f:951
        slat = math.sin(glat)  # htdp.f:952
        clat = math.cos(glat)  # htdp.f:953
        w = math.sqrt(1.0 - e2 * slat * slat)  # htdp.f:955
        en = a / w  # htdp.f:956
        if abs(glat) <= htdp_data.FRMXYZ_HEIGHT_SWITCH_RAD:  # htdp.f:957
            eht = p / clat - en  # htdp.f:958
        else:
            eht = z / slat - en + e2 * en  # htdp.f:960
        glon = math.atan2(y, x)  # htdp.f:962
        return glat, glon, eht
    raise HtdpConvergenceError(
        f"HTDP's Cartesian-to-geodetic iteration did not converge for "
        f"({x!r}, {y!r}, {z!r}) m on {ellipsoid.elpsd} within "
        f"{htdp_data.FRMXYZ_MAX_ITERATIONS + 1} passes to "
        f"{htdp_data.FRMXYZ_TOLERANCE:g} (htdp.f:919-974). HTDP itself stops "
        f"here (STOP 666, htdp.f:3246). No position is reported; check the "
        f"input coordinates."
    )


def _radii(ylat: float, ellipsoid: HtdpEllipsoid) -> tuple[float, float]:
    """Meridian and parallel radii, WITHOUT a height term. ``htdp.f:976-988``.

    HTDP uses these to turn a velocity in mm/yr into radians per year
    (``RADR8T``, ``htdp.f:405-419``), so the velocity is applied as though the
    point sat on the ellipsoid. At 600 m that is a relative error of about 1e-4
    in the velocity term - part of HTDP's round-trip non-closure (RECON.md
    section 5), and HTDP's choice, copied.
    """
    coslat = math.cos(ylat)  # htdp.f:983
    denom = math.sqrt(1.0 + ellipsoid.eps * coslat * coslat)  # htdp.f:984
    # htdp.f:985, RADMER = AF/(DENOM**3): gfortran expands **3 to (d*d)*d.
    radmer = ellipsoid.af / (denom * denom * denom)
    radpar = ellipsoid.af * coslat / denom  # htdp.f:986
    return radmer, radpar


def _tovneu(
    glat: float, glon: float, vx: float, vy: float, vz: float
) -> tuple[float, float, float]:
    """Velocity, Cartesian to north/east/up. ``htdp.f:1747-1764``."""
    slat = math.sin(glat)
    clat = math.cos(glat)
    slon = math.sin(glon)
    clon = math.cos(glon)
    vn = -slat * clon * vx - slat * slon * vy + clat * vz  # htdp.f:1759
    ve = -slon * vx + clon * vy  # htdp.f:1760
    vu = clat * clon * vx + clat * slon * vy + slat * vz  # htdp.f:1761
    return vn, ve, vu


def _tovxyz(
    glat: float, glon: float, vn: float, ve: float, vu: float
) -> tuple[float, float, float]:
    """Velocity, north/east/up to Cartesian. ``htdp.f:1767-1782``."""
    slat = math.sin(glat)
    clat = math.cos(glat)
    slon = math.sin(glon)
    clon = math.cos(glon)
    vx = -slat * clon * vn - slon * ve + clat * clon * vu  # htdp.f:1777
    vy = -slat * slon * vn + clon * ve + clat * slon * vu  # htdp.f:1778
    vz = clat * vn + slat * vu  # htdp.f:1779
    return vx, vy, vz


# --------------------------------------------------------------------------
# Helmert: frit94 / toit94 (htdp.f:4475-4665) and VTRANF (htdp.f:7666-7791).
# The IGS and IERS routines are textually identical apart from the common
# block they read, so each is one function here taking the block.
# --------------------------------------------------------------------------


def _frit94(
    table: Mapping[int, HelmertParameters],
    xyz: tuple[float, float, float],
    date: float,
    iopt: int,
) -> tuple[float, float, float]:
    """ITRF94 to frame ``iopt`` at ``date``. ``htdp.f:4475-4521`` (and _IERS)."""
    p = table[iopt]
    x1, y1, z1 = xyz
    dtime = date - p.reference_epoch  # htdp.f:4507
    tranx = p.tx_m + p.dtx_m_per_yr * dtime  # htdp.f:4508
    trany = p.ty_m + p.dty_m_per_yr * dtime  # htdp.f:4509
    tranz = p.tz_m + p.dtz_m_per_yr * dtime  # htdp.f:4510
    rotnx = p.rx_rad + p.drx_rad_per_yr * dtime  # htdp.f:4511
    rotny = p.ry_rad + p.dry_rad_per_yr * dtime  # htdp.f:4512
    rotnz = p.rz_rad + p.drz_rad_per_yr * dtime  # htdp.f:4513
    ds = 1.0 + p.scale + p.dscale_per_yr * dtime  # htdp.f:4514
    x2 = tranx + ds * x1 + rotnz * y1 - rotny * z1  # htdp.f:4516
    y2 = trany - rotnz * x1 + ds * y1 + rotnx * z1  # htdp.f:4517
    z2 = tranz + rotny * x1 - rotnx * y1 + ds * z1  # htdp.f:4518
    return x2, y2, z2


def _toit94(
    table: Mapping[int, HelmertParameters],
    xyz: tuple[float, float, float],
    date: float,
    iopt: int,
) -> tuple[float, float, float]:
    """Frame ``iopt`` to ITRF94 at ``date``. ``htdp.f:4572-4617`` (and _IERS).

    By NEGATING all fourteen parameters, not by inverting the transformation:
    the linearized negation is not an exact inverse, and its second-order
    residue, about 1e-7 m, is the height-independent floor of HTDP's round-trip
    non-closure (RECON.md section 5). Copied, not corrected.
    """
    p = table[iopt]
    x1, y1, z1 = xyz
    dtime = date - p.reference_epoch  # htdp.f:4603
    tranx = -(p.tx_m + p.dtx_m_per_yr * dtime)  # htdp.f:4604
    trany = -(p.ty_m + p.dty_m_per_yr * dtime)  # htdp.f:4605
    tranz = -(p.tz_m + p.dtz_m_per_yr * dtime)  # htdp.f:4606
    rotnx = -(p.rx_rad + p.drx_rad_per_yr * dtime)  # htdp.f:4607
    rotny = -(p.ry_rad + p.dry_rad_per_yr * dtime)  # htdp.f:4608
    rotnz = -(p.rz_rad + p.drz_rad_per_yr * dtime)  # htdp.f:4609
    ds = 1.0 - (p.scale + p.dscale_per_yr * dtime)  # htdp.f:4610
    x2 = tranx + ds * x1 + rotnz * y1 - rotny * z1  # htdp.f:4612
    y2 = trany - rotnz * x1 + ds * y1 + rotnx * z1  # htdp.f:4613
    z2 = tranz + rotny * x1 - rotnx * y1 + ds * z1  # htdp.f:4614
    return x2, y2, z2


def _vtranf(
    table: Mapping[int, HelmertParameters],
    xyz: tuple[float, float, float],
    vxyz: tuple[float, float, float],
    iopt1: int,
    iopt2: int,
) -> tuple[float, float, float]:
    """Velocity from frame ``iopt1`` to ``iopt2``, in mm/yr. ``htdp.f:7666-7728``.

    Rates only, through ITRF94, at the Cartesian position ``xyz`` the caller
    supplies - which in TRFPOS is the INPUT frame's (``htdp.f:3265``).
    """
    x, y, z = xyz
    vx, vy, vz = vxyz
    vx = vx / 1000.0  # htdp.f:7690
    vy = vy / 1000.0  # htdp.f:7691
    vz = vz / 1000.0  # htdp.f:7692
    p = table[iopt1]
    wx = -p.drx_rad_per_yr  # htdp.f:7697
    wy = -p.dry_rad_per_yr  # htdp.f:7698
    wz = -p.drz_rad_per_yr  # htdp.f:7699
    ds = -p.dscale_per_yr  # htdp.f:7700
    vx = vx - p.dtx_m_per_yr + ds * x + wz * y - wy * z  # htdp.f:7701
    vy = vy - p.dty_m_per_yr - wz * x + ds * y + wx * z  # htdp.f:7702
    vz = vz - p.dtz_m_per_yr + wy * x - wx * y + ds * z  # htdp.f:7703
    p = table[iopt2]
    wx = p.drx_rad_per_yr  # htdp.f:7708
    wy = p.dry_rad_per_yr  # htdp.f:7709
    wz = p.drz_rad_per_yr  # htdp.f:7710
    ds = p.dscale_per_yr  # htdp.f:7711
    vx = vx + p.dtx_m_per_yr + ds * x + wz * y - wy * z  # htdp.f:7712
    vy = vy + p.dty_m_per_yr - wz * x + ds * y + wx * z  # htdp.f:7713
    vz = vz + p.dtz_m_per_yr + wy * x - wx * y + ds * z  # htdp.f:7714
    return vx * 1000.0, vy * 1000.0, vz * 1000.0  # htdp.f:7717-7719


# --------------------------------------------------------------------------
# The velocity model: XTO08, the window check standing in for GETREG, GRDWEI
# and COMVEL's grid branch, PREDV.
# --------------------------------------------------------------------------


def _xto08(
    xyz: tuple[float, float, float],
    date: float,
    iopt: int,
    ellipsoid: HtdpEllipsoid,
) -> tuple[float, float]:
    """A position read as frame ``iopt``, mapped to ITRF2008. ``htdp.f:2721-2755``.

    Returns (latitude rad, WEST longitude rad in [0, 2 pi)). ``ellipsoid`` is
    whatever HTDP's /CONST/ holds when ``PREDV`` calls this - the OUTPUT
    frame's (``htdp.f:3240-3243``) - because ``FRMXYZ`` calls ``MODEL`` on the
    current ``ELPSD`` (``htdp.f:930``).
    """
    if iopt == 15:  # htdp.f:2733-2736: already ITRF2008
        x2 = xyz
    elif iopt == 1:  # htdp.f:2737-2739: NAD 83, the IGS convention
        x2 = _frit94(IGS_CONVENTION, _toit94(IGS_CONVENTION, xyz, date, iopt), date, 15)
    else:  # htdp.f:2740-2742: every other frame, the IERS convention
        x2 = _frit94(
            IERS_CONVENTION, _toit94(IERS_CONVENTION, xyz, date, iopt), date, 15
        )
    rlat, elon, _ = _frmxyz(*x2, ellipsoid)  # htdp.f:2746
    wlon = -elon  # htdp.f:2748
    while wlon < 0.0:  # htdp.f:2749-2752
        wlon = wlon + TWOPI
    return rlat, wlon


_REGION6_NORTH_EDGE_RAD = (htdp_data.GRID6_UPPER_LATITUDE * 3600.0) / RHOSEC
"""Region 6's north edge, 50.0 N, as ``GETBDY`` converts the polygon vertex
(``htdp.f:271``, ``initbd.f:39-40``: ``50.00000``, exact in single
precision). ``GETREG`` compares a lookup latitude against THIS number, not
against the 50.0 of ``GRDWEI``'s degrees, so the edge test is made on it."""


def _cell_is_in_window(i: int, j: int) -> bool:
    """True when all four nodes of GRDWEI's cell (i, j) are transcribed.

    Cell (i, j) is read from nodes (i, j), (i + 1, j), (i, j + 1) and
    (i + 1, j + 1) (``GRDVEC``, ``htdp.f:1685-1692``), so with nodes
    I ``i_low``-``i_high`` and J ``j_low``-``j_high`` transcribed the accepted
    cells are I ``i_low`` to ``i_high - 1`` and J ``j_low`` to ``j_high - 1``.
    Its own function so that the window's rows and columns can be held to that
    by the suite separately from region 6's 50.0 N edge, which coincides with
    the window's north row at the double and would otherwise mask it (interim
    gate 1 of the WGS 84 build, finding L3).
    """
    i_low, i_high = htdp_data.WINDOW_I_RANGE
    j_low, j_high = htdp_data.WINDOW_J_RANGE
    return (i_low <= i and i + 1 <= i_high and j_low <= j and j + 1 <= j_high)


def _window_cell(
    rlat: float, rlon: float, frame: HtdpFrame, latitude: float, longitude: float
) -> tuple[int, int, float, float]:
    """GRDWEI's cell for a lookup position, or a refusal. ``htdp.f:1542-1631``.

    ``frame``, ``latitude`` and ``longitude`` are for the refusal only: the
    position ``transform`` was handed, in ITS OWN frame - the transform's
    source. Until interim gate 2 (finding L4) the frame passed was whichever
    end was not NAD 83, which on a path out of NAD 83 labelled a NAD83(2011)
    position with the target frame.

    This stands in for ``GETREG`` (``htdp.f:277-303``) as well, and it may: a
    position strictly south of region 6's 50.0 N edge and inside the
    transcribed window lies strictly inside region 6 and in none of regions 1
    to 5, which ``GETREG`` tests first and which all lie west of 253 E
    (``initbd.f:17-40``; proved in the suite from the committed source). So for
    every position this function accepts, ``GETREG`` returns 6, and ``COMVEL``
    takes its grid branch (``htdp.f:458-480``).

    Refuses - never extrapolates - when the lookup position is at or north of
    the 50.0 N edge, or when its cell's four nodes are not all transcribed.
    HTDP counts a point exactly ON the edge as inside region 6 and then reads
    the row past the end of grid 6 with weight zero (RECON.md section 2); that
    is unreachable from Michigan, and refused rather than copied.
    """
    # GRDWEI, htdp.f:1603-1611.
    posx = (TWOPI - rlon) * 180.0 / PI  # htdp.f:1603, east longitude degrees
    posy = rlat * 180.0 / PI  # htdp.f:1604
    stepx = (
        htdp_data.GRID6_UPPER_EAST_LONGITUDE - htdp_data.GRID6_LOWER_EAST_LONGITUDE
    ) / htdp_data.GRID6_CELLS_EAST  # htdp.f:1608
    stepy = (
        htdp_data.GRID6_UPPER_LATITUDE - htdp_data.GRID6_LOWER_LATITUDE
    ) / htdp_data.GRID6_CELLS_NORTH  # htdp.f:1609
    i = int((posx - htdp_data.GRID6_LOWER_EAST_LONGITUDE) / stepx) + 1  # :1610
    j = int((posy - htdp_data.GRID6_LOWER_LATITUDE) / stepy) + 1  # htdp.f:1611

    i_low, i_high = htdp_data.WINDOW_I_RANGE
    j_low, j_high = htdp_data.WINDOW_J_RANGE
    north_of_edge = rlat >= _REGION6_NORTH_EDGE_RAD
    outside_window = not _cell_is_in_window(i, j)
    if north_of_edge or outside_window:
        where = (
            "at or north of 50.0 N, the northern edge of HTDP's velocity "
            "region 6 (initbd.f:39-40), where HTDP leaves this grid for a "
            "plate model this program does not carry"
            if north_of_edge
            else "outside the part of HTDP's velocity grid this program carries"
        )
        lon_w_low = 360.0 - (htdp_data.GRID6_LOWER_EAST_LONGITUDE + (i_low - 1) * stepx)
        lon_w_high = 360.0 - (htdp_data.GRID6_LOWER_EAST_LONGITUDE + (i_high - 1) * stepx)
        lat_low = htdp_data.GRID6_LOWER_LATITUDE + (j_low - 1) * stepy
        lat_high = htdp_data.GRID6_LOWER_LATITUDE + (j_high - 1) * stepy
        # The lookup position in the program's own convention, signed
        # degrees with the convention named, as every other refusal states a
        # position (closing gate of the WGS 84 build, I3): HTDP's 0-360
        # longitude printed as "275.444520 W" for an east input, and a south
        # latitude as "-42.732484 N". ``posx`` is east longitude in degrees;
        # folded to [-180, 180) it is the signed negative-west longitude.
        lookup_longitude = (posx + 180.0) % 360.0 - 180.0
        reason = (
            f"its velocity-model lookup position in ITRF2008, latitude "
            f"{posy:.6f}, longitude {lookup_longitude:.6f} (signed, negative "
            f"west), is {where}. This program "
            f"carries HTDP's velocity grid only from {lat_low:.1f} N to "
            f"{lat_high:.1f} N (north edge excluded) and {lon_w_low:.1f} W to "
            f"{lon_w_high:.1f} W - Michigan with at least a degree of margin "
            f"- and it never extrapolates."
        )
        raise HtdpVelocityGridError(
            f"Cannot transform the position at latitude {latitude:.6f}, "
            f"longitude {longitude:.6f} ({frame.name}): {reason} Check "
            f"that the position is in Michigan and that its longitude is "
            f"negative west, as this function takes it: a positive-west "
            f"longitude passed as negative west lands on the other side of "
            f"the world.",
            latitude=latitude,
            longitude=longitude,
            position_frame=frame.name,
            reason=reason,
        )

    # GRDWEI's weights would be computed from posx/posy here; returned to the
    # caller so COMVEL's arithmetic stays in one place.
    return i, j, posx, posy


def _window_node(i: int, j: int) -> tuple[float, float, float]:
    """One transcribed node of grid 6, or a refusal - never a ``KeyError``.

    ``_window_cell`` accepts only cells whose four nodes are transcribed, so
    this refusal is unreachable while that check is right. It exists so that
    if the check is ever wrong - an off-by-one at an edge (interim gate 1 of
    the WGS 84 build, finding L3) - the lookup still fails CLOSED and in this
    module's own family: a ``KeyError`` would walk straight through every
    ``except HtdpRefusal`` and ``except FrameMismatchError`` a caller writes.
    """
    try:
        return GRID6_WINDOW[(i, j)]
    except KeyError:
        i_low, i_high = htdp_data.WINDOW_I_RANGE
        j_low, j_high = htdp_data.WINDOW_J_RANGE
        raise HtdpVelocityGridError(
            f"HTDP's velocity grid node I = {i}, J = {j} is not part of the "
            f"transcription this program carries (nodes I {i_low} to {i_high}, "
            f"J {j_low} to {j_high}; htdp_data.GRID6_WINDOW). The window check "
            f"should have refused this position before any node was read, so "
            f"this is a defect in this program, not a fact about the position; "
            f"nothing is computed from a node that is not NGS's."
        ) from None


def _grid_velocity(
    i: int, j: int, posx: float, posy: float
) -> tuple[float, float, float]:
    """COMVEL's grid branch, ITRF2008 mm/yr. ``htdp.f:458-474``, ``1613-1631``."""
    stepx = (
        htdp_data.GRID6_UPPER_EAST_LONGITUDE - htdp_data.GRID6_LOWER_EAST_LONGITUDE
    ) / htdp_data.GRID6_CELLS_EAST  # htdp.f:1608
    stepy = (
        htdp_data.GRID6_UPPER_LATITUDE - htdp_data.GRID6_LOWER_LATITUDE
    ) / htdp_data.GRID6_CELLS_NORTH  # htdp.f:1609
    grlx = htdp_data.GRID6_LOWER_EAST_LONGITUDE + (i - 1) * stepx  # htdp.f:1618
    grux = grlx + stepx  # htdp.f:1619
    grly = htdp_data.GRID6_LOWER_LATITUDE + (j - 1) * stepy  # htdp.f:1620
    gruy = grly + stepy  # htdp.f:1621
    denom = (grux - grlx) * (gruy - grly)  # htdp.f:1624
    w11 = (grux - posx) * (gruy - posy) / denom  # htdp.f:1625
    w21 = (posx - grlx) * (gruy - posy) / denom  # htdp.f:1626
    w12 = (grux - posx) * (posy - grly) / denom  # htdp.f:1627
    w22 = (posx - grlx) * (posy - grly) / denom  # htdp.f:1628

    # GRDVEC, htdp.f:1685-1692: VEL(II+1, IJ+1, IVEC) <- node (I+II, J+IJ).
    v11 = _window_node(i, j)
    v12 = _window_node(i, j + 1)
    v21 = _window_node(i + 1, j)
    v22 = _window_node(i + 1, j + 1)
    # COMVEL, htdp.f:467-474, in its own summation order.
    vn = w11 * v11[0] + w12 * v12[0] + w21 * v21[0] + w22 * v22[0]
    ve = w11 * v11[1] + w12 * v12[1] + w21 * v21[1] + w22 * v22[1]
    vu = w11 * v11[2] + w12 * v12[2] + w21 * v21[2] + w22 * v22[2]
    return vn, ve, vu


def _lookup_position(
    ylat: float,
    ylon: float,
    eht: float,
    date: float,
    iopt: int,
    ellipsoid: HtdpEllipsoid,
) -> tuple[tuple[float, float, float], float, float]:
    """PREDV's Cartesian position and ITRF2008 lookup position. ``htdp.f:7426-7439``.

    Returns ((x, y, z), rlat, rlon west). The position (``ylat``, ``ylon``) is
    the OUTPUT frame's, and ``iopt`` the INPUT frame's: HTDP reads the one as
    though it were in the other (``htdp.f:3249``). Copied.
    """
    elon = -ylon  # htdp.f:7425
    xyz = _toxyz(ylat, elon, eht, ellipsoid)  # htdp.f:7426
    if iopt == 15:  # htdp.f:7428-7436: velocity grids are in ITRF2008
        rlat = ylat
        rlon = ylon if ylon >= 0.0 else ylon + TWOPI
    else:  # htdp.f:7438
        rlat, rlon = _xto08(xyz, date, iopt, ellipsoid)
    return xyz, rlat, rlon


def _predv(
    ylat: float,
    ylon: float,
    eht: float,
    date: float,
    iopt: int,
    ellipsoid: HtdpEllipsoid,
    frame: HtdpFrame,
    latitude: float,
    longitude: float,
) -> tuple[float, float, float]:
    """The velocity at a position, in frame ``iopt``, mm/yr. ``htdp.f:7400-7469``."""
    xyz, rlat, rlon = _lookup_position(ylat, ylon, eht, date, iopt, ellipsoid)
    # GETREG (htdp.f:7443) is answered by the window check: see _window_cell.
    i, j, posx, posy = _window_cell(rlat, rlon, frame, latitude, longitude)
    vn, ve, vu = _grid_velocity(i, j, posx, posy)  # COMVEL, htdp.f:7450
    if iopt != 15:  # htdp.f:7455-7463
        elon = -ylon
        vx, vy, vz = _tovxyz(ylat, elon, vn, ve, vu)  # htdp.f:7456
        table = IGS_CONVENTION if iopt == 1 else IERS_CONVENTION  # :7454, 7457-7461
        vx, vy, vz = _vtranf(table, xyz, (vx, vy, vz), 15, iopt)
        vn, ve, vu = _tovneu(ylat, elon, vx, vy, vz)  # htdp.f:7462
    # htdp.f:7465-7466: ELPSD = 'GRS80'; CALL MODEL. The caller's NEWCOR runs
    # on GRS80 from here on, whatever the frames' ellipsoids are.
    return vn, ve, vu


# --------------------------------------------------------------------------
# NEWCOR / COMPSN (htdp.f:7303-7398).
# --------------------------------------------------------------------------


def _compsn(
    ylat: float, ylon: float, ht: float, mins: int, vn: float, ve: float, vu: float
) -> tuple[float, float, float]:
    """The position at time ``mins`` under constant velocity. ``htdp.f:7303-7368``.

    Runs on GRS 80, because ``PREDV`` has just reset the ellipsoid
    (``htdp.f:7465-7466``). The earthquake loop (``htdp.f:7333-7359``) and the
    postseismic term (``htdp.f:7362-7366``) are not transcribed: neither can
    contribute anywhere a position can reach this function - every co-seismic
    radius of influence lies more than a thousand kilometres from the velocity
    window, and the one postseismic grid is in Alaska. The suite proves both
    from the committed ``initeq.f`` and ``initps.f``. (PSDISP's zeros would add
    0/RMER, 0/RPAR and 0 at ``htdp.f:7364-7366``: identities.)
    """
    dtime = float(mins - ITREF) / htdp_data.MINUTES_PER_JULIAN_YEAR  # :7322
    radmer, radpar = _radii(ylat, GRS80)  # RADR8T, htdp.f:7323 and 412
    vnr = vn / (1000.0 * radmer)  # htdp.f:414
    ver = ve / (1000.0 * radpar)  # htdp.f:415
    ylatt = ylat + vnr * dtime  # htdp.f:7324
    ylont = ylon - ver * dtime  # htdp.f:7325
    htt = ht + ((vu * dtime) / 1000.0)  # htdp.f:7326
    return ylatt, ylont, htt


def _newcor(
    ylat: float,
    ylon: float,
    htold: float,
    min1: int,
    min2: int,
    vn: float,
    ve: float,
    vu: float,
) -> tuple[float, float, float]:
    """Carry a position from ``min1`` to ``min2``. ``htdp.f:7370-7398``.

    HTDP evaluates the position at BOTH times from the same starting point and
    adds the difference, rather than multiplying the velocity by the span;
    the floating-point result is not the same, so the form is copied.
    """
    ht = htold  # htdp.f:7379
    ylat1, ylon1, ht1 = _compsn(ylat, ylon, ht, min1, vn, ve, vu)  # :7381-7382
    ylat2, ylon2, ht2 = _compsn(ylat, ylon, ht, min2, vn, ve, vu)  # :7384-7385
    ylat3 = ylat + ylat2 - ylat1  # htdp.f:7387
    ylon3 = ylon + ylon2 - ylon1  # htdp.f:7388
    htnew = ht + ht2 - ht1  # htdp.f:7389
    return ylat3, ylon3, htnew


# --------------------------------------------------------------------------
# TRFPOS, file option 3 (htdp.f:3175-3294): one record.
# --------------------------------------------------------------------------


def _require_number(value: object, label: str) -> float:
    # bool is an int; a True latitude is a mistake, not 1.0 degree.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HtdpInputError(
            f"The {label} must be a number of degrees or metres; got "
            f"{type(value).__name__} ({value!r})."
        )
    number = float(value)
    if not math.isfinite(number):
        raise HtdpInputError(
            f"The {label} is {number!r}, which is not a coordinate. Nothing "
            f"is transformed."
        )
    return number


def _require_frame(value: object, label: str) -> HtdpFrame:
    if not isinstance(value, HtdpFrame) or value not in ALL_HTDP_FRAMES:
        offered = ", ".join(f.name for f in ALL_HTDP_FRAMES)
        raise HtdpFrameError(
            f"The {label} frame must be one of the frames this program "
            f"transforms with HTDP: {offered}. Got {type(value).__name__} "
            f"({value!r}). Other HTDP frames - older WGS 84 realizations, "
            f"other ITRFs, NAD 83 at other epochs - are deliberately not "
            f"carried (docs/PLAN-wgs84.md section 1)."
        )
    return value


def _require_epoch(value: object, label: str) -> ObservationEpoch:
    if not isinstance(value, ObservationEpoch):
        raise HtdpEpochError(
            f"The {label} epoch must be an ObservationEpoch built from the "
            f"calendar date the position was observed; got "
            f"{type(value).__name__} ({value!r}). A bare date, a decimal year "
            f"or a string is refused so that every epoch goes through the "
            f"same validation and HTDP's calendar arithmetic."
        )
    return value


def transform(
    latitude: float,
    longitude: float,
    ellipsoid_height: float,
    source_frame: HtdpFrame,
    target_frame: HtdpFrame,
    epoch: ObservationEpoch,
) -> HtdpResult:
    """Transform one position between NAD 83(2011) and a time-dependent frame.

    Exactly one of ``source_frame`` and ``target_frame`` must be NAD 83(2011),
    which is always at its reference epoch 2010.0 (plan D1); ``epoch`` is the
    observation date of the OTHER frame's position. ``to_nad83`` and
    ``from_nad83`` are the two directions spelled out.

    ``latitude`` and ``longitude`` are decimal degrees, longitude NEGATIVE
    WEST; ``ellipsoid_height`` is metres above the source frame's ellipsoid as
    HTDP uses it.
    """
    source = _require_frame(source_frame, "source")
    target = _require_frame(target_frame, "target")
    observed = _require_epoch(epoch, "observation")
    if source == target:
        raise HtdpFrameError(
            f"Source and target frame are both {source.name}: that is not a "
            f"frame transformation, and this module does not pretend one ran. "
            f"Choose the frame the position is in and the frame it is wanted "
            f"in."
        )
    if NAD83_2011 not in (source, target):
        raise HtdpFrameError(
            f"Cannot transform from {source.name} to {target.name}: one side "
            f"must be NAD 83(2011). Realization-to-realization and "
            f"ITRF-to-ITRF transformations are not offered - no Michigan zone "
            f"lives on either frame (docs/PLAN-wgs84.md, decision D4). "
            f"Transform each to NAD 83(2011) instead."
        )
    lat = _require_number(latitude, "latitude")
    lon = _require_number(longitude, "longitude")
    eht = _require_number(ellipsoid_height, "ellipsoid height")
    # htdp.f:3204: HTDP refuses |lat| > 90 or |lon| > 360 in its input file.
    if abs(lat) > 90.0 or abs(lon) > 360.0:
        raise HtdpInputError(
            f"Latitude {lat!r} and longitude {lon!r} are not a position on "
            f"the earth (HTDP refuses |latitude| > 90 or |longitude| > 360, "
            f"htdp.f:3204). Check the input."
        )

    if source == NAD83_2011:
        epoch1, epoch2 = NAD83_2011_EPOCH, observed
    else:
        epoch1, epoch2 = observed, NAD83_2011_EPOCH

    try:
        return _trfpos(lat, lon, eht, source, epoch1, target, epoch2)
    except HtdpConvergenceError as failure:
        raise HtdpConvergenceError(
            f"Cannot transform the position at latitude {lat!r}, longitude "
            f"{lon!r}, ellipsoid height {eht!r} m from {source.name} to "
            f"{target.name}: {failure}"
        ) from None


def _trfpos(
    lat: float,
    lon: float,
    eht: float,
    source: HtdpFrame,
    epoch1: ObservationEpoch,
    target: HtdpFrame,
    epoch2: ObservationEpoch,
) -> HtdpResult:
    """One record of TRFPOS file option 3. ``htdp.f:3175-3294``.

    Arguments already validated by ``transform``. A refusal names the input
    position by ``source``, the frame it is in (interim gate 2, finding L4).
    """
    date1 = epoch1.decimal_year
    min1 = epoch1.minutes
    min2 = epoch2.minutes
    iopt1 = source.iopt
    iopt2 = target.iopt

    # htdp.f:3229 and 3264: the IGS block whenever NAD 83 is an endpoint -
    # which, by the refusal above, is every call.
    is_nad83 = source.iopt == 1 or target.iopt == 1
    position_table = IGS_CONVENTION if is_nad83 else IERS_CONVENTION

    xlat = lat
    xlon = -lon  # HTDP's input longitude is positive west (htdp.f:2860)
    ylat = (xlat * 3600.0) / RHOSEC  # htdp.f:3216
    ylon = (xlon * 3600.0) / RHOSEC  # htdp.f:3217
    elon = -ylon  # htdp.f:3218

    ellipsoid1 = source.ellipsoid  # htdp.f:3221-3224
    xyz = _toxyz(ylat, elon, eht, ellipsoid1)  # htdp.f:3226
    # htdp.f:3230-3231: the Helmert at DATE1, the INPUT epoch, both ways.
    x1 = _toit94(position_table, xyz, date1, iopt1)
    x2 = _frit94(position_table, x1, date1, iopt2)
    ellipsoid2 = target.ellipsoid  # htdp.f:3240-3243

    ylat1, elon1, eht1 = _frmxyz(*x2, ellipsoid2)  # htdp.f:3246 / 3280
    ylon1 = -elon1  # htdp.f:3247 / 3281
    if ylon1 < 0.0:  # htdp.f:3248 / 3282
        ylon1 = ylon1 + TWOPI

    velocity: HtdpVelocity | None
    if min1 != min2:  # htdp.f:3245
        vn, ve, vu = _predv(
            ylat1, ylon1, eht1, date1, iopt1, ellipsoid2, source, lat, lon
        )  # htdp.f:3249-3250
        vx, vy, vz = _tovxyz(ylat1, elon1, vn, ve, vu)  # htdp.f:3255
        vx, vy, vz = _vtranf(position_table, xyz, (vx, vy, vz), iopt1, iopt2)  # :3265
        vn, ve, vu = _tovneu(ylat1, elon1, vx, vy, vz)  # htdp.f:3271
        ylatt, ylont, ehtnew = _newcor(
            ylat1, ylon1, eht1, min1, min2, vn, ve, vu
        )  # htdp.f:3272-3273
        # htdp.f:3274 converts the result back to XYZ and never uses it.
        velocity = HtdpVelocity(north_mm_per_yr=vn, east_mm_per_yr=ve, up_mm_per_yr=vu)
    else:
        # htdp.f:3276-3283: the same day - the Helmert, and no velocity.
        # HTDP does no velocity lookup here and so has no window to leave;
        # this program refuses the same positions either way, so that a
        # point's acceptance never depends on the date. The lookup is computed
        # exactly as PREDV would and discarded: no number below depends on it.
        _, rlat, rlon = _lookup_position(ylat1, ylon1, eht1, date1, iopt1, ellipsoid2)
        _window_cell(rlat, rlon, source, lat, lon)
        ylatt, ylont, ehtnew = ylat1, ylon1, eht1
        velocity = None

    rad2deg = 180.0 / htdp_data.TRUNCATED_PI  # htdp.f:2766
    outlat = ylatt * rad2deg  # htdp.f:3286
    outlon = ylont * rad2deg  # htdp.f:3287, positive west
    return HtdpResult(
        latitude=outlat,
        longitude=-outlon,
        ellipsoid_height=ehtnew,
        source_frame=source,
        source_epoch=epoch1,
        target_frame=target,
        target_epoch=epoch2,
        velocity=velocity,
    )


def to_nad83(
    latitude: float,
    longitude: float,
    ellipsoid_height: float,
    source_frame: HtdpFrame,
    epoch: ObservationEpoch,
) -> HtdpResult:
    """A position in a time-dependent frame at ``epoch``, to NAD 83(2011) at 2010.0.

    HTDP's arithmetic: the Helmert at ``epoch``, then NAD 83's own small
    intraplate velocity from ``epoch`` back to 2010.0 (RECON.md section 1.4).
    """
    return transform(
        latitude, longitude, ellipsoid_height, source_frame, NAD83_2011, epoch
    )


def from_nad83(
    latitude: float,
    longitude: float,
    ellipsoid_height: float,
    target_frame: HtdpFrame,
    epoch: ObservationEpoch,
) -> HtdpResult:
    """A NAD 83(2011) position at 2010.0, to a time-dependent frame at ``epoch``.

    HTDP's arithmetic: the Helmert at 2010.0, then the global frame's full
    plate motion from 2010.0 to ``epoch`` - about 17 mm a year in Michigan.
    """
    return transform(
        latitude, longitude, ellipsoid_height, NAD83_2011, target_frame, epoch
    )
