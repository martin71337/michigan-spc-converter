"""NGS HTDP v3.6.0's constants, transcribed: the data behind ``htdp.py``.

This module is a TRANSCRIPTION and nothing else. Every number below is copied
from NGS's own Fortran - ``htdp.f``, ``initvl.f`` and ``initbd.f`` of HTDP
v3.6.0, ``github.com/noaa-ngs/HTDP`` commit
``59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c`` (``htdp.f:27-28``, "April 7,
2025") - with the line it was copied from in an adjacent comment. The source is
committed unmodified at ``review/wgs84-w0/htdp-v3.6.0/`` and its SHA-256s are
pinned by the suite.

**Why a transcription and not a reader.** The core does no file I/O
(``tests/test_architecture.py``), and the Fortran is not shipped. So the
constants live here as literals, and ``tests/test_htdp.py`` re-parses the
committed Fortran *as data* and requires every value in this module to equal
the one NGS wrote, number for number - the way ``zones.py`` is held to NGS's
captured zone definitions. A transcription that merely agreed with a copy of
itself kept beside it would prove nothing.

**Only what the offered paths reach is transcribed** (docs/PLAN-wgs84.md
section 3.2). That is:

* the two Helmert conventions, IGS (``/tranpa/``) and IERS (``/tranpa1/``),
  for HTDP's internal frame indices 1 (NAD 83), 15 (ITRF2008, which
  WGS84(G1762) uses), 16 (ITRF2014, and WGS84(G2139)) and 17 (ITRF2020, and
  WGS84(G2296)) - the IERS set is needed only because ``PREDV`` uses it for
  the velocity-grid lookup position (``htdp.f:2740-2742``, ``7457-7461``);
* a WINDOW of HTDP's velocity grid 6, "eastern CONUS": nodes I 37 to 60 and
  J 34 to 53, which is east longitude 268.0 to 279.5 (92.0 W to 80.5 W) and
  latitude 40.5 to 50.0 N - 480 nodes, every Michigan cell with at least a
  degree of margin on every side. ``htdp.py`` refuses any lookup position that
  does not fall in a fully transcribed cell, and never extrapolates;
* the ellipsoid constants of HTDP's ``MODEL`` (``htdp.f:140-176``), and the
  handful of numerical constants its routines carry inline.

Nothing for the frames this program does not offer (WGS84 G730 to G1674, the
other ITRFs, the Pacific and Mariana frames), nothing of HTDP's other velocity
grids or its plate models, and nothing of its earthquake or postseismic models.
``tests/test_htdp.py`` proves the window needs none of those: it lies strictly
inside region 6 and in none of regions 1 to 5 (``initbd.f:17-40``), farther
than every co-seismic radius of influence from its epicentre (``initeq.f``),
and outside the one postseismic grid (``initps.f``).

**Units are HTDP's own.** Rotations and their rates are stored in ARCSECONDS
and arcseconds per year, exactly as ``SETTP`` writes them, and are divided by
HTDP's ``RHOSEC`` at use - the same one division ``SETTP`` performs
(``htdp.f:3658``: ``rx(1) = 0.02579d0 / rhosec``). HTDP's own comment calls
them milliarcseconds (``htdp.f:3650``, repeated at ``4063``); it is wrong, and
the comment on the very next assignment proves it - ``!Previous 1.25033d-7
rad``, which is 0.02579 arcseconds (review/wgs84-w0/RECON.md section 1.2).

**The velocity grid values are SINGLE precision.** ``initvl.f`` writes them as
Fortran REAL literals (``-15.08``, not ``-15.08D0``) into the DOUBLE PRECISION
array ``B``, so each value is rounded to a 24-bit significand at compile time
and then widened. ``fortran_real`` below reproduces that rounding; the suite
checks it against an exact rational rounding of the literal text, so the
decimal-to-double-to-single route cannot hide a double-rounding case.

**Stdlib only, and no ``struct``**: the core may not import a binary-format
module (``tests/test_architecture.py``), so the rounding to single precision is
done arithmetically, with ``math.frexp``, rather than by packing a C float.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


HTDP_VERSION = "3.6.0"
"""``htdp.f:27``: ``HTDP_version = '3.6.0'``."""

HTDP_VERSION_DATE = "April 7, 2025"
"""``htdp.f:28``: ``Version_date = 'April 7, 2025'``."""

HTDP_COMMIT = "59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c"
"""The ``noaa-ngs/HTDP`` commit transcribed (review/wgs84-w0/RECON.md, header).
Read from the clone's ``.git/HEAD`` as data when the source was captured; the
committed copy of the source is what the suite re-parses."""


# --------------------------------------------------------------------------
# MODEL (htdp.f:140-176): the ellipsoid constants.
#
# HTDP holds ONE ellipsoid at a time in /CONST/, selected by ELPSD, and MODEL
# recomputes the derived constants from A and F every time TOXYZ or FRMXYZ is
# called (htdp.f:904, 930). htdp.py passes the ellipsoid explicitly instead of
# keeping that state, and derives E2, AF and EPS with MODEL's own expressions.
# --------------------------------------------------------------------------

SEMI_MAJOR_AXIS_M = 6378137.0
"""``htdp.f:151``: ``A = 6378137.D0`` - the same for GRS 80 and WGS 84."""

GRS80_INVERSE_FLATTENING = 298.257222101
"""``htdp.f:152``: ``F = 1.D0 / 298.257222101D0``, the default ellipsoid."""

WGS84_INVERSE_FLATTENING = 298.257223563
"""``htdp.f:154``: ``IF (ELPSD .EQ. 'WGS84') F = 1.D0 / 298.257223563D0``."""

TRUNCATED_PI = 3.14159265358979
"""``htdp.f:2766``: ``parameter (rad2deg = 180.d0/3.14159265358979d0)``.

TRFPOS converts its OUTPUT radians to degrees with this truncated pi, while
every other conversion in HTDP uses ``PI = 4.D0 * DATAN(1.D0)``
(``htdp.f:164``). The two differ by about 3.2e-15 relative to pi. It is
HTDP's choice, so it is copied rather than corrected."""


# --------------------------------------------------------------------------
# Numerical constants HTDP's routines carry inline.
# --------------------------------------------------------------------------

FRMXYZ_MAX_ITERATIONS = 10
"""``htdp.f:926``: ``parameter(maxint=10, ...)``. The loop at ``htdp.f:942``
tests ``icount.le.maxint`` BEFORE incrementing, so up to eleven passes run."""

FRMXYZ_TOLERANCE = 1.0e-13
"""``htdp.f:926``: ``parameter(..., tol=1.d-13)``, on the tangent of the
latitude between successive passes (``htdp.f:946``)."""

FRMXYZ_HEIGHT_SWITCH_RAD = 0.7854
"""``htdp.f:957``: ``if(dabs(glat).le.0.7854d0)`` - the latitude, in radians,
above which FRMXYZ computes the ellipsoid height from Z rather than from the
equatorial distance. 0.7854 rad is 45.000020 degrees, so the switch lies
INSIDE Michigan, and the suite probes it from both sides."""

MINUTES_PER_JULIAN_YEAR = 525960.0
"""``htdp.f:7322``: ``DTIME = DBLE(MIN - ITREF) / 525960.D0`` - 365.25 days of
1,440 minutes. HTDP's velocity clock runs in Julian years of whole minutes,
while its Helmert runs on the calendar-year fraction ``DATE``; the two clocks
disagree slightly, and that disagreement is part of what this program
replicates (review/wgs84-w0/RECON.md sections 1.5 and 5)."""

VELOCITY_REFERENCE_DATE = (2010, 1, 1)
"""``htdp.f:169-173``: ``IYRREF = 2010``, ``IMOREF = 1``, ``IDYREF = 1``, then
``ITREF = MJD * 24 * 60`` - the origin of HTDP's velocity clock, as (year,
month, day). ``htdp.py`` derives ``ITREF`` from it through its transcription of
``IYMDMJ``."""

EARLIEST_YEAR_EXCLUSIVE = 1906
"""``htdp.f:7891``: ``IF(IYEAR .le. 1906)`` - "The model is not valid for
dates prior to 1906." HTDP refuses the year 1906 itself."""


# --------------------------------------------------------------------------
# SETTP (htdp.f:3618-4060 for /tranpa/, 4062-4473 for /tranpa1/): the
# parameters from ITRF94 TO each frame. Every hop in HTDP is
# frame -> ITRF94 -> frame; there is no direct NAD 83 <-> ITRF20xx set
# (review/wgs84-w0/RECON.md section 1.2).
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HelmertParameters:
    """One row of a SETTP common block: ITRF94 to frame ``iopt``.

    Field for field what ``SETTP`` assigns, in its own units. Rotations stay in
    arcseconds here; the ``*_rad`` properties divide by ``RHOSEC`` at use,
    which is the single operation ``SETTP`` performs before storing, so the
    radian value is bit-identical to HTDP's.
    """

    iopt: int
    """HTDP's internal frame index (the subscript of every array in SETTP)."""

    tx_m: float
    ty_m: float
    tz_m: float
    dtx_m_per_yr: float
    dty_m_per_yr: float
    dtz_m_per_yr: float
    rx_arcsec: float
    ry_arcsec: float
    rz_arcsec: float
    drx_arcsec_per_yr: float
    dry_arcsec_per_yr: float
    drz_arcsec_per_yr: float
    scale: float
    """Unitless, as SETTP stores it (``scale(15) = -1.71504d-9``)."""

    dscale_per_yr: float
    reference_epoch: float
    """``refepc``, in decimal years: the Helmert is evaluated at
    ``date - refepc`` (``htdp.f:4507``)."""

    source: str
    """The ``htdp.f`` lines this row was copied from."""

    @property
    def rx_rad(self) -> float:
        return self.rx_arcsec / RHOSEC

    @property
    def ry_rad(self) -> float:
        return self.ry_arcsec / RHOSEC

    @property
    def rz_rad(self) -> float:
        return self.rz_arcsec / RHOSEC

    @property
    def drx_rad_per_yr(self) -> float:
        return self.drx_arcsec_per_yr / RHOSEC

    @property
    def dry_rad_per_yr(self) -> float:
        return self.dry_arcsec_per_yr / RHOSEC

    @property
    def drz_rad_per_yr(self) -> float:
        return self.drz_arcsec_per_yr / RHOSEC


PI = 4.0 * math.atan(1.0)
"""``htdp.f:164``: ``PI = 4.D0 * DATAN(1.D0)``."""

RHOSEC = (180.0 * 3600.0) / PI
"""``htdp.f:165``: ``RHOSEC = (180.D0 * 3600.D0) / PI`` - arcseconds per
radian. SETTP divides by it (``htdp.f:3658``); TRFPOS uses it to turn input
degrees into radians (``htdp.f:3216-3217``)."""

TWOPI = PI + PI
"""``htdp.f:166``: ``TWOPI = PI + PI``."""


IGS_CONVENTION: Mapping[int, HelmertParameters] = MappingProxyType(
    {
        # From ITRF94 to NAD 83. htdp.f:3649-3666.
        1: HelmertParameters(
            iopt=1,
            tx_m=0.9910,  # htdp.f:3652
            ty_m=-1.9072,  # htdp.f:3653
            tz_m=-0.5129,  # htdp.f:3654
            dtx_m_per_yr=0.0,  # htdp.f:3655
            dty_m_per_yr=0.0,  # htdp.f:3656
            dtz_m_per_yr=0.0,  # htdp.f:3657
            rx_arcsec=0.02579,  # htdp.f:3658  "/ rhosec"
            ry_arcsec=0.00965,  # htdp.f:3659  "/ rhosec"
            rz_arcsec=0.01166,  # htdp.f:3660  "/ rhosec"
            drx_arcsec_per_yr=0.0000532,  # htdp.f:3661  "/ rhosec"
            dry_arcsec_per_yr=-0.0007423,  # htdp.f:3662  "/ rhosec"
            drz_arcsec_per_yr=-0.0000316,  # htdp.f:3663  "/ rhosec"
            scale=0.0,  # htdp.f:3664
            dscale_per_yr=0.0,  # htdp.f:3665
            reference_epoch=1997.0,  # htdp.f:3666
            source="htdp.f:3652-3666",
        ),
        # From ITRF94 to ITRF2008 (also IGS08 and IGb08); WGS84(G1762) uses
        # it (MENU1, htdp.f:4704-4705 and the menu text at 4767).
        15: HelmertParameters(
            iopt=15,
            tx_m=-0.00243,  # htdp.f:3923
            ty_m=-0.00389,  # htdp.f:3924
            tz_m=0.01365,  # htdp.f:3925
            dtx_m_per_yr=-0.00079,  # htdp.f:3926
            dty_m_per_yr=0.00060,  # htdp.f:3927
            dtz_m_per_yr=0.00134,  # htdp.f:3928
            rx_arcsec=-0.00012467,  # htdp.f:3929  "/ rhosec"
            ry_arcsec=0.00022355,  # htdp.f:3930  "/ rhosec"
            rz_arcsec=0.00006065,  # htdp.f:3931  "/ rhosec"
            drx_arcsec_per_yr=-0.00001347,  # htdp.f:3932  "/ rhosec"
            dry_arcsec_per_yr=0.00001514,  # htdp.f:3933  "/ rhosec"
            drz_arcsec_per_yr=0.00001973,  # htdp.f:3934  "/ rhosec"
            scale=-1.71504e-9,  # htdp.f:3935
            dscale_per_yr=0.10201e-9,  # htdp.f:3936
            reference_epoch=1997.0,  # htdp.f:3937
            source="htdp.f:3923-3937",
        ),
        # From ITRF94 to ITRF2014 (also IGS14 and IGb14); WGS84(G2139) uses
        # it (htdp.f:4707-4708, 4768).
        16: HelmertParameters(
            iopt=16,
            tx_m=-0.01430,  # htdp.f:3946
            ty_m=0.00201,  # htdp.f:3947
            tz_m=0.02867,  # htdp.f:3948
            dtx_m_per_yr=-0.00079,  # htdp.f:3949
            dty_m_per_yr=0.00060,  # htdp.f:3950
            dtz_m_per_yr=0.00144,  # htdp.f:3951
            rx_arcsec=-0.00029978,  # htdp.f:3952  "/ rhosec"
            ry_arcsec=0.00042037,  # htdp.f:3953  "/ rhosec"
            rz_arcsec=0.00031714,  # htdp.f:3954  "/ rhosec"
            drx_arcsec_per_yr=-0.00001347,  # htdp.f:3955  "/ rhosec"
            dry_arcsec_per_yr=0.00001514,  # htdp.f:3956  "/ rhosec"
            drz_arcsec_per_yr=0.00001973,  # htdp.f:3957  "/ rhosec"
            scale=-0.36891e-9,  # htdp.f:3958
            dscale_per_yr=0.07201e-9,  # htdp.f:3959
            reference_epoch=2010.0,  # htdp.f:3960
            source="htdp.f:3946-3960",
        ),
        # From ITRF94 to ITRF2020 (also IGS20 and IGb20); WGS84(G2296) uses
        # it (htdp.f:4710-4711, 4769).
        17: HelmertParameters(
            iopt=17,
            tx_m=-0.01290,  # htdp.f:3970
            ty_m=0.00241,  # htdp.f:3971
            tz_m=0.02827,  # htdp.f:3972
            dtx_m_per_yr=-0.00079,  # htdp.f:3973
            dty_m_per_yr=0.00070,  # htdp.f:3974
            dtz_m_per_yr=0.00124,  # htdp.f:3975
            rx_arcsec=-0.00029978,  # htdp.f:3976  "/ rhosec"
            ry_arcsec=0.00042037,  # htdp.f:3977  "/ rhosec"
            rz_arcsec=0.00031714,  # htdp.f:3978  "/ rhosec"
            drx_arcsec_per_yr=-0.00001347,  # htdp.f:3979  "/ rhosec"
            dry_arcsec_per_yr=0.00001514,  # htdp.f:3980  "/ rhosec"
            drz_arcsec_per_yr=0.00001973,  # htdp.f:3981  "/ rhosec"
            scale=0.05109e-9,  # htdp.f:3982
            dscale_per_yr=0.07201e-9,  # htdp.f:3983
            reference_epoch=2010.0,  # htdp.f:3984
            source="htdp.f:3970-3984",
        ),
    }
)
"""``/tranpa/``: ITRF94 to frame, the IGS convention (ITRF96 <> ITRF97).

TRFPOS uses this block for the position whenever either endpoint is NAD 83
(``htdp.f:3229-3231``) - which is every path this program offers - and for
the velocity transformation into the output frame (``htdp.f:3264-3265``)."""


IERS_CONVENTION: Mapping[int, HelmertParameters] = MappingProxyType(
    {
        # From ITRF94 to NAD 83, identical to the IGS row. htdp.f:4065-4079.
        1: HelmertParameters(
            iopt=1,
            tx_m=0.9910,  # htdp.f:4065
            ty_m=-1.9072,  # htdp.f:4066
            tz_m=-0.5129,  # htdp.f:4067
            dtx_m_per_yr=0.0,  # htdp.f:4068
            dty_m_per_yr=0.0,  # htdp.f:4069
            dtz_m_per_yr=0.0,  # htdp.f:4070
            rx_arcsec=0.02579,  # htdp.f:4071  "/ rhosec"
            ry_arcsec=0.00965,  # htdp.f:4072  "/ rhosec"
            rz_arcsec=0.01166,  # htdp.f:4073  "/ rhosec"
            drx_arcsec_per_yr=0.0000532,  # htdp.f:4074  "/ rhosec"
            dry_arcsec_per_yr=-0.0007423,  # htdp.f:4075  "/ rhosec"
            drz_arcsec_per_yr=-0.0000316,  # htdp.f:4076  "/ rhosec"
            scale=0.0,  # htdp.f:4077
            dscale_per_yr=0.0,  # htdp.f:4078
            reference_epoch=1997.0,  # htdp.f:4079
            source="htdp.f:4065-4079",
        ),
        15: HelmertParameters(
            iopt=15,
            tx_m=-0.0045,  # htdp.f:4336
            ty_m=-0.0041,  # htdp.f:4337
            tz_m=0.0236,  # htdp.f:4338
            dtx_m_per_yr=-0.0001,  # htdp.f:4339
            dty_m_per_yr=0.0005,  # htdp.f:4340
            dtz_m_per_yr=0.0032,  # htdp.f:4341
            rx_arcsec=0.0,  # htdp.f:4342  "/ rhosec"
            ry_arcsec=0.0,  # htdp.f:4343  "/ rhosec"
            rz_arcsec=0.0,  # htdp.f:4344  "/ rhosec"
            drx_arcsec_per_yr=0.0,  # htdp.f:4345  "/ rhosec"
            dry_arcsec_per_yr=0.0,  # htdp.f:4346  "/ rhosec"
            drz_arcsec_per_yr=0.00002,  # htdp.f:4347  "/ rhosec"
            scale=-2.65e-9,  # htdp.f:4348
            dscale_per_yr=-0.09e-9,  # htdp.f:4349
            reference_epoch=1997.0,  # htdp.f:4350
            source="htdp.f:4336-4350",
        ),
        16: HelmertParameters(
            iopt=16,
            tx_m=-0.0074,  # htdp.f:4359
            ty_m=0.0005,  # htdp.f:4360
            tz_m=0.0628,  # htdp.f:4361
            dtx_m_per_yr=-0.0001,  # htdp.f:4362
            dty_m_per_yr=0.0005,  # htdp.f:4363
            dtz_m_per_yr=0.0033,  # htdp.f:4364
            rx_arcsec=0.0,  # htdp.f:4365  "/ rhosec"
            ry_arcsec=0.0,  # htdp.f:4366  "/ rhosec"
            rz_arcsec=0.00026,  # htdp.f:4367  "/ rhosec"
            drx_arcsec_per_yr=0.0,  # htdp.f:4368  "/ rhosec"
            dry_arcsec_per_yr=0.0,  # htdp.f:4369  "/ rhosec"
            drz_arcsec_per_yr=0.00002,  # htdp.f:4370  "/ rhosec"
            scale=-3.80e-9,  # htdp.f:4371
            dscale_per_yr=-0.12e-9,  # htdp.f:4372
            reference_epoch=2010.0,  # htdp.f:4373
            source="htdp.f:4359-4373",
        ),
        17: HelmertParameters(
            iopt=17,
            tx_m=-0.0060,  # htdp.f:4383
            ty_m=0.0009,  # htdp.f:4384
            tz_m=0.0624,  # htdp.f:4385
            dtx_m_per_yr=-0.0001,  # htdp.f:4386
            dty_m_per_yr=0.0006,  # htdp.f:4387
            dtz_m_per_yr=0.0031,  # htdp.f:4388
            rx_arcsec=0.0,  # htdp.f:4389  "/ rhosec"
            ry_arcsec=0.0,  # htdp.f:4390  "/ rhosec"
            rz_arcsec=0.00026,  # htdp.f:4391  "/ rhosec"
            drx_arcsec_per_yr=0.0,  # htdp.f:4392  "/ rhosec"
            dry_arcsec_per_yr=0.0,  # htdp.f:4393  "/ rhosec"
            drz_arcsec_per_yr=0.00002,  # htdp.f:4394  "/ rhosec"
            scale=-3.38e-9,  # htdp.f:4395
            dscale_per_yr=-0.12e-9,  # htdp.f:4396
            reference_epoch=2010.0,  # htdp.f:4397
            source="htdp.f:4383-4397",
        ),
    }
)
"""``/tranpa1/``: ITRF94 to frame, the IERS convention (ITRF96 = ITRF97).

Not used for any POSITION this program reports - TRFPOS selects ``/tranpa/``
whenever NAD 83 is an endpoint (``htdp.f:3229``). It is used in exactly two
places on the offered paths, both inside ``PREDV`` and only when the input
frame is neither NAD 83 nor ITRF2008: ``XTO08`` maps the lookup position to
ITRF2008 with it (``htdp.f:2740-2742``), and ``VTRANF_IERS`` turns the grid's
ITRF2008 velocity into the input frame with it (``htdp.f:7459-7461``). The
static offsets differ from the IGS set by up to a few centimetres, which moves
the grid lookup by that much; HTDP does it, so it is copied."""


HELMERT_SET_NAMES: Mapping[int, tuple[str, int]] = MappingProxyType(
    {
        # (name, htdp.f line of the comment it is copied from) - SETTP's own
        # heading over each /tranpa/ block, "*** From ITRF94 to <name>",
        # verbatim after the "to ".
        1: ("NAD 83", 3649),
        15: ("ITRF2008 (also IGS08 and IGb08)", 3917),
        16: ("ITRF2014 (also IGS14 and IGb14)", 3939),
        17: ("ITRF2020 (also IGS20 and IGb20)", 3962),
    }
)
"""What HTDP calls each transcribed Helmert row, by internal frame index.

The words of SETTP's own comment over the row, so the job record can name the
parameter set it prints the way NGS's source names it (work package W4,
docs/PLAN-wgs84.md section 3.6). ``tests/test_frame_disclosure.py`` reads the
cited line of the committed ``htdp.f`` back and requires it to be exactly
``*** From ITRF94 to `` followed by the name."""


# --------------------------------------------------------------------------
# Velocity grid 6, "eastern CONUS" (initvl.f:42981-47704).
# --------------------------------------------------------------------------

GRID6_LOWER_EAST_LONGITUDE = 250.0
"""``initvl.f:42981``: ``GRDLX( 6) / 250.00000000000 /``, degrees east."""

GRID6_UPPER_EAST_LONGITUDE = 294.0
"""``initvl.f:42982``: ``GRDUX( 6) / 294.00000000000 /``."""

GRID6_LOWER_LATITUDE = 24.0
"""``initvl.f:42983``: ``GRDLY( 6) /  24.00000000000 /``."""

GRID6_UPPER_LATITUDE = 50.0
"""``initvl.f:42984``: ``GRDUY( 6) /  50.00000000000 /`` - also the north
edge of region 6 (``initbd.f:39-40``), beyond which HTDP leaves this grid."""

GRID6_CELLS_EAST = 88
"""``initvl.f:42985``: ``ICNTX( 6) / 88 /`` - 88 cells, so 89 node columns."""

GRID6_CELLS_NORTH = 52
"""``initvl.f:42986``: ``ICNTY( 6) / 52 /`` - 52 cells, so 53 node rows."""

GRID6_NBASE = 128808
"""``initvl.f:42987``: ``NBASE( 6) /128808 /`` - the offset of grid 6 in the
flat ``/VGRID/ B(210000)`` array. Not used in arithmetic here (the window is
keyed by node), but the suite uses it to prove every node below sits at the
``B`` index ``IUNGRD`` (``htdp.f:1731-1744``) would read it from."""

WINDOW_I_RANGE = (37, 60)
"""Node columns transcribed, inclusive: east longitude 250 + (I - 1) * 0.5,
so 268.0 to 279.5 E (92.0 W to 80.5 W). A lookup cell is usable when both of
its node columns I and I + 1 lie in this range."""

WINDOW_J_RANGE = (34, 53)
"""Node rows transcribed, inclusive: latitude 24 + (J - 1) * 0.5, so 40.5 to
50.0 N. Row 53 is the grid's (and region 6's) north edge."""


def fortran_real(value: float) -> float:
    """``value`` rounded to IEEE single precision, as a Fortran REAL literal is.

    Round to nearest, ties to even, on a 24-bit significand - the rounding the
    compiler applies to ``-15.08`` in ``DATA B(...) / -15.08, ... /`` before
    the value is widened into the DOUBLE PRECISION array (review/wgs84-w0/
    RECON.md section 2, confirmed with a gfortran test program there). Done
    with ``math.frexp`` because the core may not import ``struct``.

    Only the normal single-precision range is accepted: every literal this is
    applied to is a velocity of a few tens of mm/yr, and a value outside the
    range would mean the transcription itself had gone wrong.
    """
    if value == 0.0:
        return 0.0
    if not math.isfinite(value) or not (2.0**-126 <= abs(value) < 2.0**128):
        raise ValueError(
            f"{value!r} is outside the normal single-precision range, so it "
            f"cannot be a velocity-grid literal from initvl.f. The "
            f"transcription in michspc/spc/htdp_data.py is damaged."
        )
    mantissa, exponent = math.frexp(value)
    # mantissa * 2**24 is exact (a power-of-two scaling), and round() on a
    # float rounds half to even on its exact binary value: IEEE's default.
    return math.ldexp(round(mantissa * 16777216.0), exponent - 24)


# Each node is (VN, VE, VU) in mm/yr RELATIVE TO ITRF2008 (htdp.f:424,
# "Compute the ITRF2008 velocity at a point in mm/yr"), exactly as initvl.f
# writes it. The file lists grid 6 column by column, so node (I, J) is at
# initvl.f line 42988 + (I - 1) * 53 + (J - 1); IUNGRD (htdp.f:1740-1741)
# reads it from B(NBASE + 3 * ((J - 1) * 89 + (I - 1)) + 1). Both are cited
# per node. The vertical component is 0.00 at every node of grid 6 - HTDP is
# "Horizontal" Time-Dependent Positioning (review/wgs84-w0/RECON.md section 3).
_GRID6_WINDOW_LITERALS: Mapping[tuple[int, int], tuple[float, float, float]] = {
    (37, 34): (-1.45, -14.99, 0.00),  # initvl.f:44929  B(137728)
    (37, 35): (-1.47, -15.08, 0.00),  # initvl.f:44930  B(137995)
    (37, 36): (-1.48, -15.18, 0.00),  # initvl.f:44931  B(138262)
    (37, 37): (-1.53, -15.26, 0.00),  # initvl.f:44932  B(138529)
    (37, 38): (-1.60, -15.33, 0.00),  # initvl.f:44933  B(138796)
    (37, 39): (-1.68, -15.43, 0.00),  # initvl.f:44934  B(139063)
    (37, 40): (-1.76, -15.55, 0.00),  # initvl.f:44935  B(139330)
    (37, 41): (-1.85, -15.70, 0.00),  # initvl.f:44936  B(139597)
    (37, 42): (-1.95, -15.89, 0.00),  # initvl.f:44937  B(139864)
    (37, 43): (-2.07, -16.10, 0.00),  # initvl.f:44938  B(140131)
    (37, 44): (-2.18, -16.32, 0.00),  # initvl.f:44939  B(140398)
    (37, 45): (-2.28, -16.51, 0.00),  # initvl.f:44940  B(140665)
    (37, 46): (-2.36, -16.69, 0.00),  # initvl.f:44941  B(140932)
    (37, 47): (-2.40, -16.80, 0.00),  # initvl.f:44942  B(141199)
    (37, 48): (-2.42, -16.85, 0.00),  # initvl.f:44943  B(141466)
    (37, 49): (-2.43, -16.87, 0.00),  # initvl.f:44944  B(141733)
    (37, 50): (-2.43, -16.85, 0.00),  # initvl.f:44945  B(142000)
    (37, 51): (-2.43, -16.79, 0.00),  # initvl.f:44946  B(142267)
    (37, 52): (-2.42, -16.70, 0.00),  # initvl.f:44947  B(142534)
    (37, 53): (-2.42, -16.56, 0.00),  # initvl.f:44948  B(142801)
    (38, 34): (-1.28, -15.06, 0.00),  # initvl.f:44982  B(137731)
    (38, 35): (-1.29, -15.17, 0.00),  # initvl.f:44983  B(137998)
    (38, 36): (-1.30, -15.29, 0.00),  # initvl.f:44984  B(138265)
    (38, 37): (-1.35, -15.38, 0.00),  # initvl.f:44985  B(138532)
    (38, 38): (-1.44, -15.43, 0.00),  # initvl.f:44986  B(138799)
    (38, 39): (-1.53, -15.51, 0.00),  # initvl.f:44987  B(139066)
    (38, 40): (-1.62, -15.62, 0.00),  # initvl.f:44988  B(139333)
    (38, 41): (-1.71, -15.76, 0.00),  # initvl.f:44989  B(139600)
    (38, 42): (-1.82, -15.94, 0.00),  # initvl.f:44990  B(139867)
    (38, 43): (-1.95, -16.14, 0.00),  # initvl.f:44991  B(140134)
    (38, 44): (-2.07, -16.35, 0.00),  # initvl.f:44992  B(140401)
    (38, 45): (-2.18, -16.54, 0.00),  # initvl.f:44993  B(140668)
    (38, 46): (-2.27, -16.70, 0.00),  # initvl.f:44994  B(140935)
    (38, 47): (-2.32, -16.82, 0.00),  # initvl.f:44995  B(141202)
    (38, 48): (-2.34, -16.89, 0.00),  # initvl.f:44996  B(141469)
    (38, 49): (-2.35, -16.91, 0.00),  # initvl.f:44997  B(141736)
    (38, 50): (-2.35, -16.90, 0.00),  # initvl.f:44998  B(142003)
    (38, 51): (-2.34, -16.84, 0.00),  # initvl.f:44999  B(142270)
    (38, 52): (-2.34, -16.75, 0.00),  # initvl.f:45000  B(142537)
    (38, 53): (-2.34, -16.61, 0.00),  # initvl.f:45001  B(142804)
    (39, 34): (-1.11, -15.12, 0.00),  # initvl.f:45035  B(137734)
    (39, 35): (-1.12, -15.23, 0.00),  # initvl.f:45036  B(138001)
    (39, 36): (-1.15, -15.33, 0.00),  # initvl.f:45037  B(138268)
    (39, 37): (-1.20, -15.41, 0.00),  # initvl.f:45038  B(138535)
    (39, 38): (-1.29, -15.48, 0.00),  # initvl.f:45039  B(138802)
    (39, 39): (-1.38, -15.57, 0.00),  # initvl.f:45040  B(139069)
    (39, 40): (-1.48, -15.68, 0.00),  # initvl.f:45041  B(139336)
    (39, 41): (-1.59, -15.83, 0.00),  # initvl.f:45042  B(139603)
    (39, 42): (-1.70, -16.00, 0.00),  # initvl.f:45043  B(139870)
    (39, 43): (-1.83, -16.18, 0.00),  # initvl.f:45044  B(140137)
    (39, 44): (-1.96, -16.37, 0.00),  # initvl.f:45045  B(140404)
    (39, 45): (-2.08, -16.55, 0.00),  # initvl.f:45046  B(140671)
    (39, 46): (-2.17, -16.71, 0.00),  # initvl.f:45047  B(140938)
    (39, 47): (-2.23, -16.83, 0.00),  # initvl.f:45048  B(141205)
    (39, 48): (-2.26, -16.90, 0.00),  # initvl.f:45049  B(141472)
    (39, 49): (-2.27, -16.94, 0.00),  # initvl.f:45050  B(141739)
    (39, 50): (-2.26, -16.93, 0.00),  # initvl.f:45051  B(142006)
    (39, 51): (-2.25, -16.88, 0.00),  # initvl.f:45052  B(142273)
    (39, 52): (-2.24, -16.78, 0.00),  # initvl.f:45053  B(142540)
    (39, 53): (-2.24, -16.65, 0.00),  # initvl.f:45054  B(142807)
    (40, 34): (-0.95, -15.16, 0.00),  # initvl.f:45088  B(137737)
    (40, 35): (-0.97, -15.26, 0.00),  # initvl.f:45089  B(138004)
    (40, 36): (-1.00, -15.34, 0.00),  # initvl.f:45090  B(138271)
    (40, 37): (-1.06, -15.42, 0.00),  # initvl.f:45091  B(138538)
    (40, 38): (-1.14, -15.51, 0.00),  # initvl.f:45092  B(138805)
    (40, 39): (-1.24, -15.61, 0.00),  # initvl.f:45093  B(139072)
    (40, 40): (-1.35, -15.74, 0.00),  # initvl.f:45094  B(139339)
    (40, 41): (-1.46, -15.89, 0.00),  # initvl.f:45095  B(139606)
    (40, 42): (-1.58, -16.05, 0.00),  # initvl.f:45096  B(139873)
    (40, 43): (-1.71, -16.22, 0.00),  # initvl.f:45097  B(140140)
    (40, 44): (-1.85, -16.40, 0.00),  # initvl.f:45098  B(140407)
    (40, 45): (-1.97, -16.56, 0.00),  # initvl.f:45099  B(140674)
    (40, 46): (-2.07, -16.70, 0.00),  # initvl.f:45100  B(140941)
    (40, 47): (-2.14, -16.81, 0.00),  # initvl.f:45101  B(141208)
    (40, 48): (-2.17, -16.90, 0.00),  # initvl.f:45102  B(141475)
    (40, 49): (-2.17, -16.95, 0.00),  # initvl.f:45103  B(141742)
    (40, 50): (-2.16, -16.94, 0.00),  # initvl.f:45104  B(142009)
    (40, 51): (-2.15, -16.90, 0.00),  # initvl.f:45105  B(142276)
    (40, 52): (-2.13, -16.82, 0.00),  # initvl.f:45106  B(142543)
    (40, 53): (-2.13, -16.69, 0.00),  # initvl.f:45107  B(142810)
    (41, 34): (-0.79, -15.19, 0.00),  # initvl.f:45141  B(137740)
    (41, 35): (-0.81, -15.29, 0.00),  # initvl.f:45142  B(138007)
    (41, 36): (-0.84, -15.36, 0.00),  # initvl.f:45143  B(138274)
    (41, 37): (-0.90, -15.43, 0.00),  # initvl.f:45144  B(138541)
    (41, 38): (-0.98, -15.54, 0.00),  # initvl.f:45145  B(138808)
    (41, 39): (-1.08, -15.66, 0.00),  # initvl.f:45146  B(139075)
    (41, 40): (-1.19, -15.79, 0.00),  # initvl.f:45147  B(139342)
    (41, 41): (-1.31, -15.94, 0.00),  # initvl.f:45148  B(139609)
    (41, 42): (-1.44, -16.10, 0.00),  # initvl.f:45149  B(139876)
    (41, 43): (-1.58, -16.26, 0.00),  # initvl.f:45150  B(140143)
    (41, 44): (-1.73, -16.42, 0.00),  # initvl.f:45151  B(140410)
    (41, 45): (-1.86, -16.56, 0.00),  # initvl.f:45152  B(140677)
    (41, 46): (-1.97, -16.68, 0.00),  # initvl.f:45153  B(140944)
    (41, 47): (-2.04, -16.78, 0.00),  # initvl.f:45154  B(141211)
    (41, 48): (-2.08, -16.87, 0.00),  # initvl.f:45155  B(141478)
    (41, 49): (-2.07, -16.93, 0.00),  # initvl.f:45156  B(141745)
    (41, 50): (-2.05, -16.94, 0.00),  # initvl.f:45157  B(142012)
    (41, 51): (-2.03, -16.91, 0.00),  # initvl.f:45158  B(142279)
    (41, 52): (-2.01, -16.84, 0.00),  # initvl.f:45159  B(142546)
    (41, 53): (-2.00, -16.71, 0.00),  # initvl.f:45160  B(142813)
    (42, 34): (-0.63, -15.23, 0.00),  # initvl.f:45194  B(137743)
    (42, 35): (-0.65, -15.32, 0.00),  # initvl.f:45195  B(138010)
    (42, 36): (-0.68, -15.40, 0.00),  # initvl.f:45196  B(138277)
    (42, 37): (-0.73, -15.48, 0.00),  # initvl.f:45197  B(138544)
    (42, 38): (-0.80, -15.58, 0.00),  # initvl.f:45198  B(138811)
    (42, 39): (-0.91, -15.70, 0.00),  # initvl.f:45199  B(139078)
    (42, 40): (-1.03, -15.84, 0.00),  # initvl.f:45200  B(139345)
    (42, 41): (-1.16, -15.99, 0.00),  # initvl.f:45201  B(139612)
    (42, 42): (-1.30, -16.15, 0.00),  # initvl.f:45202  B(139879)
    (42, 43): (-1.45, -16.30, 0.00),  # initvl.f:45203  B(140146)
    (42, 44): (-1.59, -16.44, 0.00),  # initvl.f:45204  B(140413)
    (42, 45): (-1.74, -16.55, 0.00),  # initvl.f:45205  B(140680)
    (42, 46): (-1.86, -16.65, 0.00),  # initvl.f:45206  B(140947)
    (42, 47): (-1.94, -16.74, 0.00),  # initvl.f:45207  B(141214)
    (42, 48): (-1.98, -16.83, 0.00),  # initvl.f:45208  B(141481)
    (42, 49): (-1.96, -16.90, 0.00),  # initvl.f:45209  B(141748)
    (42, 50): (-1.93, -16.94, 0.00),  # initvl.f:45210  B(142015)
    (42, 51): (-1.90, -16.92, 0.00),  # initvl.f:45211  B(142282)
    (42, 52): (-1.87, -16.86, 0.00),  # initvl.f:45212  B(142549)
    (42, 53): (-1.86, -16.74, 0.00),  # initvl.f:45213  B(142816)
    (43, 34): (-0.47, -15.27, 0.00),  # initvl.f:45247  B(137746)
    (43, 35): (-0.49, -15.37, 0.00),  # initvl.f:45248  B(138013)
    (43, 36): (-0.51, -15.45, 0.00),  # initvl.f:45249  B(138280)
    (43, 37): (-0.55, -15.52, 0.00),  # initvl.f:45250  B(138547)
    (43, 38): (-0.62, -15.62, 0.00),  # initvl.f:45251  B(138814)
    (43, 39): (-0.73, -15.74, 0.00),  # initvl.f:45252  B(139081)
    (43, 40): (-0.86, -15.89, 0.00),  # initvl.f:45253  B(139348)
    (43, 41): (-1.00, -16.04, 0.00),  # initvl.f:45254  B(139615)
    (43, 42): (-1.15, -16.20, 0.00),  # initvl.f:45255  B(139882)
    (43, 43): (-1.30, -16.34, 0.00),  # initvl.f:45256  B(140149)
    (43, 44): (-1.45, -16.46, 0.00),  # initvl.f:45257  B(140416)
    (43, 45): (-1.60, -16.56, 0.00),  # initvl.f:45258  B(140683)
    (43, 46): (-1.73, -16.63, 0.00),  # initvl.f:45259  B(140950)
    (43, 47): (-1.83, -16.70, 0.00),  # initvl.f:45260  B(141217)
    (43, 48): (-1.86, -16.78, 0.00),  # initvl.f:45261  B(141484)
    (43, 49): (-1.84, -16.87, 0.00),  # initvl.f:45262  B(141751)
    (43, 50): (-1.79, -16.93, 0.00),  # initvl.f:45263  B(142018)
    (43, 51): (-1.75, -16.93, 0.00),  # initvl.f:45264  B(142285)
    (43, 52): (-1.72, -16.87, 0.00),  # initvl.f:45265  B(142552)
    (43, 53): (-1.70, -16.76, 0.00),  # initvl.f:45266  B(142819)
    (44, 34): (-0.32, -15.33, 0.00),  # initvl.f:45300  B(137749)
    (44, 35): (-0.33, -15.43, 0.00),  # initvl.f:45301  B(138016)
    (44, 36): (-0.34, -15.50, 0.00),  # initvl.f:45302  B(138283)
    (44, 37): (-0.36, -15.57, 0.00),  # initvl.f:45303  B(138550)
    (44, 38): (-0.44, -15.66, 0.00),  # initvl.f:45304  B(138817)
    (44, 39): (-0.55, -15.78, 0.00),  # initvl.f:45305  B(139084)
    (44, 40): (-0.69, -15.93, 0.00),  # initvl.f:45306  B(139351)
    (44, 41): (-0.84, -16.09, 0.00),  # initvl.f:45307  B(139618)
    (44, 42): (-0.99, -16.24, 0.00),  # initvl.f:45308  B(139885)
    (44, 43): (-1.14, -16.38, 0.00),  # initvl.f:45309  B(140152)
    (44, 44): (-1.30, -16.48, 0.00),  # initvl.f:45310  B(140419)
    (44, 45): (-1.44, -16.56, 0.00),  # initvl.f:45311  B(140686)
    (44, 46): (-1.58, -16.62, 0.00),  # initvl.f:45312  B(140953)
    (44, 47): (-1.69, -16.67, 0.00),  # initvl.f:45313  B(141220)
    (44, 48): (-1.72, -16.76, 0.00),  # initvl.f:45314  B(141487)
    (44, 49): (-1.68, -16.86, 0.00),  # initvl.f:45315  B(141754)
    (44, 50): (-1.63, -16.93, 0.00),  # initvl.f:45316  B(142021)
    (44, 51): (-1.58, -16.94, 0.00),  # initvl.f:45317  B(142288)
    (44, 52): (-1.55, -16.89, 0.00),  # initvl.f:45318  B(142555)
    (44, 53): (-1.53, -16.78, 0.00),  # initvl.f:45319  B(142822)
    (45, 34): (-0.15, -15.39, 0.00),  # initvl.f:45353  B(137752)
    (45, 35): (-0.18, -15.51, 0.00),  # initvl.f:45354  B(138019)
    (45, 36): (-0.18, -15.57, 0.00),  # initvl.f:45355  B(138286)
    (45, 37): (-0.19, -15.62, 0.00),  # initvl.f:45356  B(138553)
    (45, 38): (-0.26, -15.70, 0.00),  # initvl.f:45357  B(138820)
    (45, 39): (-0.39, -15.83, 0.00),  # initvl.f:45358  B(139087)
    (45, 40): (-0.53, -15.98, 0.00),  # initvl.f:45359  B(139354)
    (45, 41): (-0.68, -16.13, 0.00),  # initvl.f:45360  B(139621)
    (45, 42): (-0.83, -16.28, 0.00),  # initvl.f:45361  B(139888)
    (45, 43): (-0.98, -16.41, 0.00),  # initvl.f:45362  B(140155)
    (45, 44): (-1.13, -16.50, 0.00),  # initvl.f:45363  B(140422)
    (45, 45): (-1.28, -16.57, 0.00),  # initvl.f:45364  B(140689)
    (45, 46): (-1.41, -16.62, 0.00),  # initvl.f:45365  B(140956)
    (45, 47): (-1.50, -16.68, 0.00),  # initvl.f:45366  B(141223)
    (45, 48): (-1.53, -16.76, 0.00),  # initvl.f:45367  B(141490)
    (45, 49): (-1.50, -16.86, 0.00),  # initvl.f:45368  B(141757)
    (45, 50): (-1.44, -16.94, 0.00),  # initvl.f:45369  B(142024)
    (45, 51): (-1.39, -16.96, 0.00),  # initvl.f:45370  B(142291)
    (45, 52): (-1.36, -16.90, 0.00),  # initvl.f:45371  B(142558)
    (45, 53): (-1.35, -16.79, 0.00),  # initvl.f:45372  B(142825)
    (46, 34): (0.01, -15.46, 0.00),  # initvl.f:45406  B(137755)
    (46, 35): (-0.03, -15.59, 0.00),  # initvl.f:45407  B(138022)
    (46, 36): (-0.03, -15.64, 0.00),  # initvl.f:45408  B(138289)
    (46, 37): (-0.05, -15.69, 0.00),  # initvl.f:45409  B(138556)
    (46, 38): (-0.12, -15.76, 0.00),  # initvl.f:45410  B(138823)
    (46, 39): (-0.24, -15.88, 0.00),  # initvl.f:45411  B(139090)
    (46, 40): (-0.39, -16.02, 0.00),  # initvl.f:45412  B(139357)
    (46, 41): (-0.53, -16.16, 0.00),  # initvl.f:45413  B(139624)
    (46, 42): (-0.67, -16.31, 0.00),  # initvl.f:45414  B(139891)
    (46, 43): (-0.82, -16.43, 0.00),  # initvl.f:45415  B(140158)
    (46, 44): (-0.97, -16.51, 0.00),  # initvl.f:45416  B(140425)
    (46, 45): (-1.11, -16.56, 0.00),  # initvl.f:45417  B(140692)
    (46, 46): (-1.23, -16.61, 0.00),  # initvl.f:45418  B(140959)
    (46, 47): (-1.31, -16.69, 0.00),  # initvl.f:45419  B(141226)
    (46, 48): (-1.33, -16.78, 0.00),  # initvl.f:45420  B(141493)
    (46, 49): (-1.30, -16.87, 0.00),  # initvl.f:45421  B(141760)
    (46, 50): (-1.25, -16.95, 0.00),  # initvl.f:45422  B(142027)
    (46, 51): (-1.20, -16.97, 0.00),  # initvl.f:45423  B(142294)
    (46, 52): (-1.18, -16.91, 0.00),  # initvl.f:45424  B(142561)
    (46, 53): (-1.17, -16.80, 0.00),  # initvl.f:45425  B(142828)
    (47, 34): (0.20, -15.48, 0.00),  # initvl.f:45459  B(137758)
    (47, 35): (0.13, -15.64, 0.00),  # initvl.f:45460  B(138025)
    (47, 36): (0.13, -15.68, 0.00),  # initvl.f:45461  B(138292)
    (47, 37): (0.10, -15.74, 0.00),  # initvl.f:45462  B(138559)
    (47, 38): (0.02, -15.82, 0.00),  # initvl.f:45463  B(138826)
    (47, 39): (-0.10, -15.92, 0.00),  # initvl.f:45464  B(139093)
    (47, 40): (-0.24, -16.05, 0.00),  # initvl.f:45465  B(139360)
    (47, 41): (-0.39, -16.18, 0.00),  # initvl.f:45466  B(139627)
    (47, 42): (-0.52, -16.31, 0.00),  # initvl.f:45467  B(139894)
    (47, 43): (-0.66, -16.42, 0.00),  # initvl.f:45468  B(140161)
    (47, 44): (-0.81, -16.49, 0.00),  # initvl.f:45469  B(140428)
    (47, 45): (-0.94, -16.55, 0.00),  # initvl.f:45470  B(140695)
    (47, 46): (-1.04, -16.61, 0.00),  # initvl.f:45471  B(140962)
    (47, 47): (-1.11, -16.69, 0.00),  # initvl.f:45472  B(141229)
    (47, 48): (-1.13, -16.78, 0.00),  # initvl.f:45473  B(141496)
    (47, 49): (-1.11, -16.87, 0.00),  # initvl.f:45474  B(141763)
    (47, 50): (-1.06, -16.94, 0.00),  # initvl.f:45475  B(142030)
    (47, 51): (-1.02, -16.96, 0.00),  # initvl.f:45476  B(142297)
    (47, 52): (-1.00, -16.91, 0.00),  # initvl.f:45477  B(142564)
    (47, 53): (-0.99, -16.80, 0.00),  # initvl.f:45478  B(142831)
    (48, 34): (0.42, -15.43, 0.00),  # initvl.f:45512  B(137761)
    (48, 35): (0.35, -15.59, 0.00),  # initvl.f:45513  B(138028)
    (48, 36): (0.31, -15.68, 0.00),  # initvl.f:45514  B(138295)
    (48, 37): (0.26, -15.77, 0.00),  # initvl.f:45515  B(138562)
    (48, 38): (0.18, -15.86, 0.00),  # initvl.f:45516  B(138829)
    (48, 39): (0.05, -15.96, 0.00),  # initvl.f:45517  B(139096)
    (48, 40): (-0.09, -16.07, 0.00),  # initvl.f:45518  B(139363)
    (48, 41): (-0.24, -16.18, 0.00),  # initvl.f:45519  B(139630)
    (48, 42): (-0.37, -16.30, 0.00),  # initvl.f:45520  B(139897)
    (48, 43): (-0.50, -16.39, 0.00),  # initvl.f:45521  B(140164)
    (48, 44): (-0.64, -16.46, 0.00),  # initvl.f:45522  B(140431)
    (48, 45): (-0.77, -16.52, 0.00),  # initvl.f:45523  B(140698)
    (48, 46): (-0.87, -16.60, 0.00),  # initvl.f:45524  B(140965)
    (48, 47): (-0.92, -16.69, 0.00),  # initvl.f:45525  B(141232)
    (48, 48): (-0.93, -16.78, 0.00),  # initvl.f:45526  B(141499)
    (48, 49): (-0.92, -16.87, 0.00),  # initvl.f:45527  B(141766)
    (48, 50): (-0.88, -16.93, 0.00),  # initvl.f:45528  B(142033)
    (48, 51): (-0.84, -16.95, 0.00),  # initvl.f:45529  B(142300)
    (48, 52): (-0.82, -16.90, 0.00),  # initvl.f:45530  B(142567)
    (48, 53): (-0.81, -16.79, 0.00),  # initvl.f:45531  B(142834)
    (49, 34): (0.64, -15.35, 0.00),  # initvl.f:45565  B(137764)
    (49, 35): (0.57, -15.53, 0.00),  # initvl.f:45566  B(138031)
    (49, 36): (0.51, -15.66, 0.00),  # initvl.f:45567  B(138298)
    (49, 37): (0.45, -15.78, 0.00),  # initvl.f:45568  B(138565)
    (49, 38): (0.35, -15.89, 0.00),  # initvl.f:45569  B(138832)
    (49, 39): (0.22, -15.98, 0.00),  # initvl.f:45570  B(139099)
    (49, 40): (0.08, -16.08, 0.00),  # initvl.f:45571  B(139366)
    (49, 41): (-0.06, -16.19, 0.00),  # initvl.f:45572  B(139633)
    (49, 42): (-0.20, -16.28, 0.00),  # initvl.f:45573  B(139900)
    (49, 43): (-0.33, -16.36, 0.00),  # initvl.f:45574  B(140167)
    (49, 44): (-0.47, -16.42, 0.00),  # initvl.f:45575  B(140434)
    (49, 45): (-0.60, -16.48, 0.00),  # initvl.f:45576  B(140701)
    (49, 46): (-0.69, -16.57, 0.00),  # initvl.f:45577  B(140968)
    (49, 47): (-0.73, -16.67, 0.00),  # initvl.f:45578  B(141235)
    (49, 48): (-0.74, -16.77, 0.00),  # initvl.f:45579  B(141502)
    (49, 49): (-0.72, -16.86, 0.00),  # initvl.f:45580  B(141769)
    (49, 50): (-0.69, -16.92, 0.00),  # initvl.f:45581  B(142036)
    (49, 51): (-0.66, -16.93, 0.00),  # initvl.f:45582  B(142303)
    (49, 52): (-0.64, -16.89, 0.00),  # initvl.f:45583  B(142570)
    (49, 53): (-0.63, -16.78, 0.00),  # initvl.f:45584  B(142837)
    (50, 34): (0.85, -15.27, 0.00),  # initvl.f:45618  B(137767)
    (50, 35): (0.78, -15.46, 0.00),  # initvl.f:45619  B(138034)
    (50, 36): (0.72, -15.62, 0.00),  # initvl.f:45620  B(138301)
    (50, 37): (0.64, -15.77, 0.00),  # initvl.f:45621  B(138568)
    (50, 38): (0.53, -15.90, 0.00),  # initvl.f:45622  B(138835)
    (50, 39): (0.40, -15.99, 0.00),  # initvl.f:45623  B(139102)
    (50, 40): (0.26, -16.09, 0.00),  # initvl.f:45624  B(139369)
    (50, 41): (0.12, -16.19, 0.00),  # initvl.f:45625  B(139636)
    (50, 42): (-0.02, -16.27, 0.00),  # initvl.f:45626  B(139903)
    (50, 43): (-0.15, -16.33, 0.00),  # initvl.f:45627  B(140170)
    (50, 44): (-0.29, -16.37, 0.00),  # initvl.f:45628  B(140437)
    (50, 45): (-0.41, -16.43, 0.00),  # initvl.f:45629  B(140704)
    (50, 46): (-0.50, -16.53, 0.00),  # initvl.f:45630  B(140971)
    (50, 47): (-0.53, -16.64, 0.00),  # initvl.f:45631  B(141238)
    (50, 48): (-0.54, -16.75, 0.00),  # initvl.f:45632  B(141505)
    (50, 49): (-0.53, -16.84, 0.00),  # initvl.f:45633  B(141772)
    (50, 50): (-0.50, -16.90, 0.00),  # initvl.f:45634  B(142039)
    (50, 51): (-0.48, -16.92, 0.00),  # initvl.f:45635  B(142306)
    (50, 52): (-0.46, -16.88, 0.00),  # initvl.f:45636  B(142573)
    (50, 53): (-0.45, -16.77, 0.00),  # initvl.f:45637  B(142840)
    (51, 34): (1.05, -15.20, 0.00),  # initvl.f:45671  B(137770)
    (51, 35): (0.98, -15.40, 0.00),  # initvl.f:45672  B(138037)
    (51, 36): (0.91, -15.58, 0.00),  # initvl.f:45673  B(138304)
    (51, 37): (0.82, -15.73, 0.00),  # initvl.f:45674  B(138571)
    (51, 38): (0.71, -15.86, 0.00),  # initvl.f:45675  B(138838)
    (51, 39): (0.58, -15.97, 0.00),  # initvl.f:45676  B(139105)
    (51, 40): (0.44, -16.08, 0.00),  # initvl.f:45677  B(139372)
    (51, 41): (0.30, -16.18, 0.00),  # initvl.f:45678  B(139639)
    (51, 42): (0.17, -16.26, 0.00),  # initvl.f:45679  B(139906)
    (51, 43): (0.03, -16.30, 0.00),  # initvl.f:45680  B(140173)
    (51, 44): (-0.09, -16.31, 0.00),  # initvl.f:45681  B(140440)
    (51, 45): (-0.19, -16.35, 0.00),  # initvl.f:45682  B(140707)
    (51, 46): (-0.27, -16.47, 0.00),  # initvl.f:45683  B(140974)
    (51, 47): (-0.32, -16.61, 0.00),  # initvl.f:45684  B(141241)
    (51, 48): (-0.33, -16.72, 0.00),  # initvl.f:45685  B(141508)
    (51, 49): (-0.33, -16.82, 0.00),  # initvl.f:45686  B(141775)
    (51, 50): (-0.31, -16.89, 0.00),  # initvl.f:45687  B(142042)
    (51, 51): (-0.30, -16.91, 0.00),  # initvl.f:45688  B(142309)
    (51, 52): (-0.28, -16.87, 0.00),  # initvl.f:45689  B(142576)
    (51, 53): (-0.27, -16.76, 0.00),  # initvl.f:45690  B(142843)
    (52, 34): (1.22, -15.14, 0.00),  # initvl.f:45724  B(137773)
    (52, 35): (1.17, -15.35, 0.00),  # initvl.f:45725  B(138040)
    (52, 36): (1.09, -15.53, 0.00),  # initvl.f:45726  B(138307)
    (52, 37): (0.99, -15.67, 0.00),  # initvl.f:45727  B(138574)
    (52, 38): (0.88, -15.81, 0.00),  # initvl.f:45728  B(138841)
    (52, 39): (0.75, -15.94, 0.00),  # initvl.f:45729  B(139108)
    (52, 40): (0.62, -16.07, 0.00),  # initvl.f:45730  B(139375)
    (52, 41): (0.48, -16.17, 0.00),  # initvl.f:45731  B(139642)
    (52, 42): (0.34, -16.25, 0.00),  # initvl.f:45732  B(139909)
    (52, 43): (0.21, -16.28, 0.00),  # initvl.f:45733  B(140176)
    (52, 44): (0.11, -16.28, 0.00),  # initvl.f:45734  B(140443)
    (52, 45): (0.03, -16.28, 0.00),  # initvl.f:45735  B(140710)
    (52, 46): (-0.05, -16.42, 0.00),  # initvl.f:45736  B(140977)
    (52, 47): (-0.10, -16.57, 0.00),  # initvl.f:45737  B(141244)
    (52, 48): (-0.13, -16.70, 0.00),  # initvl.f:45738  B(141511)
    (52, 49): (-0.13, -16.80, 0.00),  # initvl.f:45739  B(141778)
    (52, 50): (-0.12, -16.87, 0.00),  # initvl.f:45740  B(142045)
    (52, 51): (-0.11, -16.89, 0.00),  # initvl.f:45741  B(142312)
    (52, 52): (-0.10, -16.86, 0.00),  # initvl.f:45742  B(142579)
    (52, 53): (-0.09, -16.76, 0.00),  # initvl.f:45743  B(142846)
    (53, 34): (1.39, -15.11, 0.00),  # initvl.f:45777  B(137776)
    (53, 35): (1.32, -15.31, 0.00),  # initvl.f:45778  B(138043)
    (53, 36): (1.24, -15.50, 0.00),  # initvl.f:45779  B(138310)
    (53, 37): (1.14, -15.67, 0.00),  # initvl.f:45780  B(138577)
    (53, 38): (1.04, -15.82, 0.00),  # initvl.f:45781  B(138844)
    (53, 39): (0.92, -15.96, 0.00),  # initvl.f:45782  B(139111)
    (53, 40): (0.80, -16.06, 0.00),  # initvl.f:45783  B(139378)
    (53, 41): (0.67, -16.16, 0.00),  # initvl.f:45784  B(139645)
    (53, 42): (0.52, -16.23, 0.00),  # initvl.f:45785  B(139912)
    (53, 43): (0.39, -16.27, 0.00),  # initvl.f:45786  B(140179)
    (53, 44): (0.30, -16.27, 0.00),  # initvl.f:45787  B(140446)
    (53, 45): (0.23, -16.29, 0.00),  # initvl.f:45788  B(140713)
    (53, 46): (0.16, -16.40, 0.00),  # initvl.f:45789  B(140980)
    (53, 47): (0.10, -16.54, 0.00),  # initvl.f:45790  B(141247)
    (53, 48): (0.07, -16.67, 0.00),  # initvl.f:45791  B(141514)
    (53, 49): (0.06, -16.78, 0.00),  # initvl.f:45792  B(141781)
    (53, 50): (0.06, -16.85, 0.00),  # initvl.f:45793  B(142048)
    (53, 51): (0.07, -16.87, 0.00),  # initvl.f:45794  B(142315)
    (53, 52): (0.09, -16.85, 0.00),  # initvl.f:45795  B(142582)
    (53, 53): (0.09, -16.75, 0.00),  # initvl.f:45796  B(142849)
    (54, 34): (1.54, -15.10, 0.00),  # initvl.f:45830  B(137779)
    (54, 35): (1.44, -15.28, 0.00),  # initvl.f:45831  B(138046)
    (54, 36): (1.35, -15.48, 0.00),  # initvl.f:45832  B(138313)
    (54, 37): (1.26, -15.69, 0.00),  # initvl.f:45833  B(138580)
    (54, 38): (1.18, -15.86, 0.00),  # initvl.f:45834  B(138847)
    (54, 39): (1.10, -16.00, 0.00),  # initvl.f:45835  B(139114)
    (54, 40): (0.99, -16.08, 0.00),  # initvl.f:45836  B(139381)
    (54, 41): (0.85, -16.16, 0.00),  # initvl.f:45837  B(139648)
    (54, 42): (0.71, -16.22, 0.00),  # initvl.f:45838  B(139915)
    (54, 43): (0.57, -16.28, 0.00),  # initvl.f:45839  B(140182)
    (54, 44): (0.48, -16.29, 0.00),  # initvl.f:45840  B(140449)
    (54, 45): (0.41, -16.32, 0.00),  # initvl.f:45841  B(140716)
    (54, 46): (0.35, -16.41, 0.00),  # initvl.f:45842  B(140983)
    (54, 47): (0.30, -16.53, 0.00),  # initvl.f:45843  B(141250)
    (54, 48): (0.26, -16.65, 0.00),  # initvl.f:45844  B(141517)
    (54, 49): (0.25, -16.76, 0.00),  # initvl.f:45845  B(141784)
    (54, 50): (0.24, -16.83, 0.00),  # initvl.f:45846  B(142051)
    (54, 51): (0.25, -16.85, 0.00),  # initvl.f:45847  B(142318)
    (54, 52): (0.26, -16.83, 0.00),  # initvl.f:45848  B(142585)
    (54, 53): (0.27, -16.73, 0.00),  # initvl.f:45849  B(142852)
    (55, 34): (1.68, -15.11, 0.00),  # initvl.f:45883  B(137782)
    (55, 35): (1.57, -15.27, 0.00),  # initvl.f:45884  B(138049)
    (55, 36): (1.46, -15.48, 0.00),  # initvl.f:45885  B(138316)
    (55, 37): (1.35, -15.71, 0.00),  # initvl.f:45886  B(138583)
    (55, 38): (1.30, -15.90, 0.00),  # initvl.f:45887  B(138850)
    (55, 39): (1.28, -16.02, 0.00),  # initvl.f:45888  B(139117)
    (55, 40): (1.17, -16.09, 0.00),  # initvl.f:45889  B(139384)
    (55, 41): (1.03, -16.15, 0.00),  # initvl.f:45890  B(139651)
    (55, 42): (0.88, -16.21, 0.00),  # initvl.f:45891  B(139918)
    (55, 43): (0.76, -16.27, 0.00),  # initvl.f:45892  B(140185)
    (55, 44): (0.66, -16.30, 0.00),  # initvl.f:45893  B(140452)
    (55, 45): (0.59, -16.35, 0.00),  # initvl.f:45894  B(140719)
    (55, 46): (0.53, -16.43, 0.00),  # initvl.f:45895  B(140986)
    (55, 47): (0.48, -16.53, 0.00),  # initvl.f:45896  B(141253)
    (55, 48): (0.45, -16.64, 0.00),  # initvl.f:45897  B(141520)
    (55, 49): (0.43, -16.74, 0.00),  # initvl.f:45898  B(141787)
    (55, 50): (0.42, -16.80, 0.00),  # initvl.f:45899  B(142054)
    (55, 51): (0.42, -16.82, 0.00),  # initvl.f:45900  B(142321)
    (55, 52): (0.43, -16.79, 0.00),  # initvl.f:45901  B(142588)
    (55, 53): (0.43, -16.69, 0.00),  # initvl.f:45902  B(142855)
    (56, 34): (1.83, -15.12, 0.00),  # initvl.f:45936  B(137785)
    (56, 35): (1.69, -15.30, 0.00),  # initvl.f:45937  B(138052)
    (56, 36): (1.57, -15.49, 0.00),  # initvl.f:45938  B(138319)
    (56, 37): (1.49, -15.70, 0.00),  # initvl.f:45939  B(138586)
    (56, 38): (1.45, -15.88, 0.00),  # initvl.f:45940  B(138853)
    (56, 39): (1.43, -16.00, 0.00),  # initvl.f:45941  B(139120)
    (56, 40): (1.32, -16.08, 0.00),  # initvl.f:45942  B(139387)
    (56, 41): (1.19, -16.14, 0.00),  # initvl.f:45943  B(139654)
    (56, 42): (1.05, -16.20, 0.00),  # initvl.f:45944  B(139921)
    (56, 43): (0.93, -16.26, 0.00),  # initvl.f:45945  B(140188)
    (56, 44): (0.83, -16.31, 0.00),  # initvl.f:45946  B(140455)
    (56, 45): (0.76, -16.37, 0.00),  # initvl.f:45947  B(140722)
    (56, 46): (0.70, -16.45, 0.00),  # initvl.f:45948  B(140989)
    (56, 47): (0.65, -16.54, 0.00),  # initvl.f:45949  B(141256)
    (56, 48): (0.62, -16.64, 0.00),  # initvl.f:45950  B(141523)
    (56, 49): (0.60, -16.72, 0.00),  # initvl.f:45951  B(141790)
    (56, 50): (0.59, -16.78, 0.00),  # initvl.f:45952  B(142057)
    (56, 51): (0.59, -16.79, 0.00),  # initvl.f:45953  B(142324)
    (56, 52): (0.59, -16.75, 0.00),  # initvl.f:45954  B(142591)
    (56, 53): (0.59, -16.64, 0.00),  # initvl.f:45955  B(142858)
    (57, 34): (1.98, -15.13, 0.00),  # initvl.f:45989  B(137788)
    (57, 35): (1.83, -15.31, 0.00),  # initvl.f:45990  B(138055)
    (57, 36): (1.71, -15.51, 0.00),  # initvl.f:45991  B(138322)
    (57, 37): (1.63, -15.69, 0.00),  # initvl.f:45992  B(138589)
    (57, 38): (1.58, -15.86, 0.00),  # initvl.f:45993  B(138856)
    (57, 39): (1.54, -15.98, 0.00),  # initvl.f:45994  B(139123)
    (57, 40): (1.44, -16.06, 0.00),  # initvl.f:45995  B(139390)
    (57, 41): (1.32, -16.13, 0.00),  # initvl.f:45996  B(139657)
    (57, 42): (1.20, -16.19, 0.00),  # initvl.f:45997  B(139924)
    (57, 43): (1.09, -16.25, 0.00),  # initvl.f:45998  B(140191)
    (57, 44): (1.00, -16.31, 0.00),  # initvl.f:45999  B(140458)
    (57, 45): (0.93, -16.38, 0.00),  # initvl.f:46000  B(140725)
    (57, 46): (0.87, -16.46, 0.00),  # initvl.f:46001  B(140992)
    (57, 47): (0.83, -16.55, 0.00),  # initvl.f:46002  B(141259)
    (57, 48): (0.79, -16.64, 0.00),  # initvl.f:46003  B(141526)
    (57, 49): (0.77, -16.71, 0.00),  # initvl.f:46004  B(141793)
    (57, 50): (0.76, -16.75, 0.00),  # initvl.f:46005  B(142060)
    (57, 51): (0.75, -16.75, 0.00),  # initvl.f:46006  B(142327)
    (57, 52): (0.75, -16.70, 0.00),  # initvl.f:46007  B(142594)
    (57, 53): (0.75, -16.59, 0.00),  # initvl.f:46008  B(142861)
    (58, 34): (2.15, -15.11, 0.00),  # initvl.f:46042  B(137791)
    (58, 35): (1.99, -15.31, 0.00),  # initvl.f:46043  B(138058)
    (58, 36): (1.85, -15.50, 0.00),  # initvl.f:46044  B(138325)
    (58, 37): (1.77, -15.67, 0.00),  # initvl.f:46045  B(138592)
    (58, 38): (1.71, -15.83, 0.00),  # initvl.f:46046  B(138859)
    (58, 39): (1.64, -15.95, 0.00),  # initvl.f:46047  B(139126)
    (58, 40): (1.54, -16.04, 0.00),  # initvl.f:46048  B(139393)
    (58, 41): (1.44, -16.12, 0.00),  # initvl.f:46049  B(139660)
    (58, 42): (1.33, -16.18, 0.00),  # initvl.f:46050  B(139927)
    (58, 43): (1.24, -16.24, 0.00),  # initvl.f:46051  B(140194)
    (58, 44): (1.15, -16.31, 0.00),  # initvl.f:46052  B(140461)
    (58, 45): (1.09, -16.38, 0.00),  # initvl.f:46053  B(140728)
    (58, 46): (1.04, -16.46, 0.00),  # initvl.f:46054  B(140995)
    (58, 47): (0.99, -16.55, 0.00),  # initvl.f:46055  B(141262)
    (58, 48): (0.96, -16.63, 0.00),  # initvl.f:46056  B(141529)
    (58, 49): (0.93, -16.69, 0.00),  # initvl.f:46057  B(141796)
    (58, 50): (0.92, -16.73, 0.00),  # initvl.f:46058  B(142063)
    (58, 51): (0.91, -16.72, 0.00),  # initvl.f:46059  B(142330)
    (58, 52): (0.90, -16.66, 0.00),  # initvl.f:46060  B(142597)
    (58, 53): (0.90, -16.55, 0.00),  # initvl.f:46061  B(142864)
    (59, 34): (2.32, -15.10, 0.00),  # initvl.f:46095  B(137794)
    (59, 35): (2.17, -15.28, 0.00),  # initvl.f:46096  B(138061)
    (59, 36): (2.04, -15.47, 0.00),  # initvl.f:46097  B(138328)
    (59, 37): (1.93, -15.65, 0.00),  # initvl.f:46098  B(138595)
    (59, 38): (1.83, -15.80, 0.00),  # initvl.f:46099  B(138862)
    (59, 39): (1.74, -15.93, 0.00),  # initvl.f:46100  B(139129)
    (59, 40): (1.65, -16.02, 0.00),  # initvl.f:46101  B(139396)
    (59, 41): (1.55, -16.10, 0.00),  # initvl.f:46102  B(139663)
    (59, 42): (1.46, -16.17, 0.00),  # initvl.f:46103  B(139930)
    (59, 43): (1.38, -16.23, 0.00),  # initvl.f:46104  B(140197)
    (59, 44): (1.31, -16.30, 0.00),  # initvl.f:46105  B(140464)
    (59, 45): (1.25, -16.38, 0.00),  # initvl.f:46106  B(140731)
    (59, 46): (1.20, -16.46, 0.00),  # initvl.f:46107  B(140998)
    (59, 47): (1.16, -16.55, 0.00),  # initvl.f:46108  B(141265)
    (59, 48): (1.13, -16.62, 0.00),  # initvl.f:46109  B(141532)
    (59, 49): (1.10, -16.68, 0.00),  # initvl.f:46110  B(141799)
    (59, 50): (1.08, -16.70, 0.00),  # initvl.f:46111  B(142066)
    (59, 51): (1.06, -16.69, 0.00),  # initvl.f:46112  B(142333)
    (59, 52): (1.06, -16.62, 0.00),  # initvl.f:46113  B(142600)
    (59, 53): (1.05, -16.51, 0.00),  # initvl.f:46114  B(142867)
    (60, 34): (2.51, -15.08, 0.00),  # initvl.f:46148  B(137797)
    (60, 35): (2.37, -15.25, 0.00),  # initvl.f:46149  B(138064)
    (60, 36): (2.22, -15.44, 0.00),  # initvl.f:46150  B(138331)
    (60, 37): (2.09, -15.62, 0.00),  # initvl.f:46151  B(138598)
    (60, 38): (1.97, -15.78, 0.00),  # initvl.f:46152  B(138865)
    (60, 39): (1.86, -15.91, 0.00),  # initvl.f:46153  B(139132)
    (60, 40): (1.75, -16.01, 0.00),  # initvl.f:46154  B(139399)
    (60, 41): (1.66, -16.08, 0.00),  # initvl.f:46155  B(139666)
    (60, 42): (1.59, -16.15, 0.00),  # initvl.f:46156  B(139933)
    (60, 43): (1.52, -16.22, 0.00),  # initvl.f:46157  B(140200)
    (60, 44): (1.46, -16.29, 0.00),  # initvl.f:46158  B(140467)
    (60, 45): (1.41, -16.37, 0.00),  # initvl.f:46159  B(140734)
    (60, 46): (1.37, -16.46, 0.00),  # initvl.f:46160  B(141001)
    (60, 47): (1.33, -16.54, 0.00),  # initvl.f:46161  B(141268)
    (60, 48): (1.29, -16.61, 0.00),  # initvl.f:46162  B(141535)
    (60, 49): (1.26, -16.66, 0.00),  # initvl.f:46163  B(141802)
    (60, 50): (1.24, -16.68, 0.00),  # initvl.f:46164  B(142069)
    (60, 51): (1.22, -16.66, 0.00),  # initvl.f:46165  B(142336)
    (60, 52): (1.21, -16.59, 0.00),  # initvl.f:46166  B(142603)
    (60, 53): (1.21, -16.47, 0.00),  # initvl.f:46167  B(142870)
}


GRID6_WINDOW: Mapping[tuple[int, int], tuple[float, float, float]] = (
    MappingProxyType(
        {
            node: tuple(fortran_real(component) for component in literal)
            for node, literal in _GRID6_WINDOW_LITERALS.items()
        }
    )
)
"""The window's nodes as HTDP holds them: each REAL literal rounded to single
precision and widened. Keyed by HTDP's own (I, J) node indices; read-only."""


def _check_window_is_complete() -> None:
    """Refuse to import if the window has lost or gained a node.

    A missing node would surface only when a lookup reached it - as a
    KeyError, from inside a conversion. Loud at import beats that. if/raise,
    never assert: -O strips asserts.
    """
    expected = {
        (i, j)
        for i in range(WINDOW_I_RANGE[0], WINDOW_I_RANGE[1] + 1)
        for j in range(WINDOW_J_RANGE[0], WINDOW_J_RANGE[1] + 1)
    }
    if set(_GRID6_WINDOW_LITERALS) != expected:
        missing = sorted(expected - set(_GRID6_WINDOW_LITERALS))
        extra = sorted(set(_GRID6_WINDOW_LITERALS) - expected)
        raise ValueError(
            f"The HTDP velocity-grid window in michspc/spc/htdp_data.py is "
            f"not the rectangle I {WINDOW_I_RANGE[0]}..{WINDOW_I_RANGE[1]}, "
            f"J {WINDOW_J_RANGE[0]}..{WINDOW_J_RANGE[1]}: missing {missing}, "
            f"unexpected {extra}. Restore the transcription from initvl.f."
        )


_check_window_is_complete()
