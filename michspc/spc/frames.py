"""Reference frames, and the registry of transformations between them.

A geodetic position is meaningless without the frame it is expressed in. Every
position carried through this program is therefore tagged, and a pair of frames
with no published transformation is refused rather than passed through.

That refusal is the single most important safety property in the program. NAD 83
is being replaced by NATRF2022; the two differ by one to two metres. Passing
coordinates between them as though they were the same thing would produce
numbers that look entirely ordinary and are wrong by more than the width of a
road. See docs/DESIGN.md section 6.

**This module mirrors ``michspc/spc/vertical.py``**, which was written from the
shape this one had: typed records carrying an explicit status, an explicit
registry keyed by ``(source, target)``, an append-only list of pairs the
registry may never lose, and a ``require_*`` that refuses loudly instead of
guessing. The two modules answer the same question about the two halves of a
coordinate - which surface is this height on, which frame is this position in -
so they are deliberately the same shape.

**What this registry carries** (docs/DESIGN.md amendments #62 and #70):

* **Identities**, one per plate-fixed usable frame. Work WITHIN each frame is
  complete: the three SPCS 83 zones on NAD83(2011), the nineteen SPCS2022
  zones on NATRF2022, any-to-any within either era, geodetic in and out on
  either frame.
* **NGS HTDP v3.6.0's transformation between NAD83(2011) and five
  time-dependent frames** - WGS84(G1762), WGS84(G2139), WGS84(G2296), ITRF2014
  and ITRF2020 - in both directions (docs/PLAN-wgs84.md, work package W2).
  NGS publishes that whole path as open source, and ``htdp.py`` transcribes
  it; these records name the path and hold no parameter of it, because the
  two frames' ``htdp_frame`` records determine it completely and
  ``htdp_data`` is the one authoritative representation of its numbers.
  The conversion pipeline APPLIES them (``convert.py``, work package W3): a
  WGS 84 or ITRF end is moved to or from NAD83(2011) by ``htdp`` exactly once,
  and the NAD 83 position is the pivot every zone and grid reads.

Work across NAD83(2011) and NATRF2022 refuses, because NGS has not published
the transformation - its NCAT computes one from server-side parameters that are
not in any published document or shipped file, and the best public candidate
set misses NCAT by 17 cm at one of twelve frozen Michigan anchors. A 17 cm
disagreement with the national tool is a boundary-moving amount, and shipping
it is precisely what this program exists to refuse
(docs/DEFERRED-NATRF2022-BRIDGE.md). WGS 84 or ITRF against NATRF2022 refuses
for the same reason (plan decision D3), and one WGS 84 or ITRF frame against
another is not offered (plan decision D4).

**Backwards compatibility is a requirement, not an assumption** (DESIGN.md
amendment #32, stated there for the vertical registry and binding here for the
same reason). A job converted under this program must still convert, and still
reproduce, after NGS publishes: ``REQUIRED_FRAME_PAIRS`` states that as an
append-only list which may grow and may never shrink, and this module refuses to
import if the registry has lost one of them - so a deleted pair fails loudly at
startup rather than quietly at the first job that needed it.
"""

from __future__ import annotations

import dataclasses
import datetime
import math
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from michspc.spc import htdp, htdp_data


class FrameMismatchError(Exception):
    """Base class for every refusal in this module.

    Callers that only need "the conversion was refused because of the frames,
    say so" catch this - ``job.run``, the GUI, and the pinned safety tests all
    do. The two subclasses below are distinguished where it matters, because a
    frame this program cannot use at all and a pair of usable frames with no
    published transformation between them are different things to tell a
    surveyor.

    Kept as the base under its original name deliberately: it is what every
    existing catch site names, and narrowing it would silently stop catching
    the refusal it was written for.
    """


class FrameNotUsableError(FrameMismatchError):
    """Raised when a frame is declared in this module but not usable.

    A bare "WGS 84" is declared and not usable. It is not a typo and not a
    missing feature flag: the label does not say WHICH realization a position
    is in, nor when it was observed, and both decide where the position is -
    while the same label is also what many data collectors print on NAD 83
    output. The five named realizations and ITRF frames this program does
    carry are separate records (docs/DESIGN.md amendment #70, plan decision
    D2), and the refusal names them.
    """


class FrameTransformationUnavailableError(FrameMismatchError):
    """Raised when no usable transformation exists for a pair of frames.

    Not a warning and not a silent pass-through: leaving a latitude and
    longitude alone while calling it transformed is exactly the failure the
    tier sentence exists to prevent. NAD83(2011) to NATRF2022 raises this
    today (DESIGN.md #62); so do the pairs plan decisions D3 and D4 do not
    offer, and - at the conversion pipeline - a registered path whose method
    it has no arithmetic for (``convert.require_an_applicable_path``).
    """


class FrameRecordMismatchError(FrameMismatchError):
    """Raised when a frame record names a registered frame but states other facts.

    A ``ReferenceFrame`` whose ``code`` is a registry code is a claim to BE that
    frame, and its other fields - ellipsoid, epoch kind, reference epoch, HTDP
    frame, status, name, citation - are a second copy of facts the registry
    already holds. When the copy disagrees, the code says one frame and the
    fields another: ``dataclasses.replace(WGS84_G2296, code="NAD83(2011)")`` is
    a time-dependent, WGS 84-ellipsoid, HTDP-G2296 record calling itself NAD 83
    (interim gate 1 of the WGS 84 build, finding L4). Before the gate it was
    silently replaced by the registry's record at the frame gate and carried
    on, uncorrected, everywhere else - the job ran as a NAD 83 identity and the
    record printed the WGS 84 name beside the NAD 83 code.

    A subclass of ``FrameMismatchError`` rather than a ``TypeError``, because
    the argument IS a well-formed ``ReferenceFrame``: the likeliest source is
    data - a record rebuilt from a saved job, then edited - not a programming
    mistake, and every caller already turns ``FrameMismatchError`` into a
    refusal the user reads. ``TypeError`` stays what it is in this module: an
    argument that is not a ``ReferenceFrame`` at all.
    """


class FrameStatus(Enum):
    """Whether this program may actually carry coordinates in a frame.

    ``DECLARED_NOT_USABLE`` is a real state, not a placeholder: the frame is in
    the record so that the refusal has something concrete to refuse and so the
    registry states the fact users most need to be told - the role
    ``NAPGD2022`` plays in ``vertical.py``.

    NATRF2022 was ``DECLARED_NOT_USABLE`` in everything but name until the
    SPCS2022 zones landed. It is USABLE now: nineteen Michigan zones are
    defined on it and a job may be converted entirely within it. What is
    refused is not the frame, it is the BRIDGE between the frames - a
    distinction this enum exists to keep visible, because collapsing the two
    would either forbid legitimate 2022 work or permit an untransformed
    crossing.
    """

    USABLE = "usable"
    DECLARED_NOT_USABLE = "declared but not usable"


class FrameEpochKind(Enum):
    """Whether a frame's coordinates hold still, or need the date they were observed.

    The question a frame record must answer before a position in it can be
    moved anywhere, and the reason it is a REQUIRED field (the ``FrameStatus``
    precedent, DESIGN.md #62): a default would let a frame be added without the
    question being asked, and the wrong answer is a centimetres-per-year error
    that grows silently.

    * ``PLATE_FIXED`` - the frame is attached to a tectonic plate and its
      coordinates are published at one REFERENCE EPOCH (``reference_epoch``):
      NAD83(2011) at 2010.0, NATRF2022 at 2020.0. A coordinate in it carries no
      date of its own.
    * ``TIME_DEPENDENT`` - a global frame (WGS 84, ITRF) in which a Michigan
      point moves about 17 mm a year against NAD 83 (review/wgs84-w0/RECON.md
      section 3), so a position in it means nothing until the date it was
      observed is stated. It has no reference epoch: the observation epoch is
      supplied per job (docs/PLAN-wgs84.md decision D10).
    """

    PLATE_FIXED = "plate-fixed, at a published reference epoch"
    TIME_DEPENDENT = "time-dependent, at the epoch the position was observed"


_HTDP_ELLIPSOID_NAMES: Mapping[str, str] = MappingProxyType(
    {
        htdp.GRS80.elpsd: "GRS 80",
        htdp.WGS84_ELLIPSOID.elpsd: "WGS 84",
    }
)
"""How a frame record spells the ellipsoid HTDP loads for it.

HTDP chooses the ellipsoid from the frame's NAME (``htdp.f:3221-3224``), and
``htdp.HtdpFrame.ellipsoid`` derives it the same way, so for a frame HTDP
carries the HTDP record is the authority and ``ReferenceFrame.ellipsoid_name``
must agree with it - checked in ``ReferenceFrame.__post_init__``, never
trusted as two typed strings. This table is only the spelling: HTDP's
five-character token against the wording this program's records use.
"""


@dataclass(frozen=True)
class ReferenceFrame:
    """A geodetic reference frame."""

    code: str
    name: str
    ellipsoid_name: str
    citation: str
    status: FrameStatus
    """REQUIRED, with no default, mirroring ``VerticalDatum.status``.

    A default would mean a frame record could be built - by a later module, by
    a rebuilt saved job, by a test - that this module never granted a status
    to, and the default would inevitably be USABLE. ``_canonical`` below closes
    the same door from the other side.
    """

    epoch_kind: FrameEpochKind
    """REQUIRED, with no default, for the reason ``status`` is: see
    ``FrameEpochKind``. ``__post_init__`` refuses a kind that disagrees with
    ``reference_epoch`` or with HTDP's own classification of the frame."""

    reference_epoch: float | None
    """REQUIRED, with no default. The decimal year a PLATE-FIXED frame's
    coordinates are published at, and ``None`` for a TIME-DEPENDENT one, whose
    epoch is the observation's, not the frame's. Stated as the published
    figure (NAD83(2011) 2010.0, NATRF2022 2020.0) rather than a date because
    that is how the defining documents state it; for NAD83(2011) it is checked
    against ``htdp.NAD83_2011_EPOCH``, the epoch the arithmetic actually uses,
    so the record and the computation cannot state two epochs."""

    htdp_frame: htdp.HtdpFrame | None
    """REQUIRED, with no default. The frame as NGS's HTDP v3.6.0 carries it
    (``htdp.py``), or ``None`` for a frame HTDP does not carry - NATRF2022,
    which is in no HTDP menu, and the bare WGS 84 label, which names no
    realization HTDP could be asked about. Where present it is the authority
    for the ellipsoid and for whether the frame is time-dependent, and
    ``__post_init__`` holds this record to it."""

    def __post_init__(self) -> None:
        # if/raise, never assert: the suite and the shipped program both run
        # under -O, which strips asserts (DESIGN.md section 7).
        if not isinstance(self.epoch_kind, FrameEpochKind):
            raise TypeError(
                f"Reference frame {self.code!r} states epoch_kind "
                f"{self.epoch_kind!r}, which is not a FrameEpochKind. Whether "
                f"the frame is plate-fixed or time-dependent decides whether a "
                f"position in it needs an observation date; state "
                f"FrameEpochKind.PLATE_FIXED or FrameEpochKind.TIME_DEPENDENT."
            )

        if self.epoch_kind is FrameEpochKind.PLATE_FIXED:
            epoch = self.reference_epoch
            if (
                isinstance(epoch, bool)
                or not isinstance(epoch, (int, float))
                or not math.isfinite(epoch)
            ):
                raise ValueError(
                    f"Reference frame {self.code!r} is plate-fixed but states "
                    f"reference_epoch {epoch!r}. A plate-fixed frame's "
                    f"coordinates are published at one reference epoch, a "
                    f"decimal year (NAD83(2011) 2010.0, NATRF2022 2020.0), and "
                    f"the record must state it."
                )
        elif self.reference_epoch is not None:
            raise ValueError(
                f"Reference frame {self.code!r} is time-dependent but states "
                f"reference_epoch {self.reference_epoch!r}. A time-dependent "
                f"frame has no epoch of its own: a position in it is at the "
                f"date it was observed, which each job states. A reference "
                f"epoch here would be a second, contradicting answer to that "
                f"question. Pass reference_epoch=None."
            )

        carried = self.htdp_frame
        if carried is None:
            return
        if not isinstance(carried, htdp.HtdpFrame) or carried not in (
            htdp.ALL_HTDP_FRAMES
        ):
            offered = ", ".join(frame.name for frame in htdp.ALL_HTDP_FRAMES)
            raise TypeError(
                f"Reference frame {self.code!r} states htdp_frame "
                f"{carried!r}, which is not one of the frames michspc.spc.htdp "
                f"carries ({offered}). Pass one of htdp's own records, or None "
                f"for a frame HTDP does not carry."
            )

        expected_ellipsoid = _HTDP_ELLIPSOID_NAMES.get(carried.ellipsoid.elpsd)
        if self.ellipsoid_name != expected_ellipsoid:
            raise ValueError(
                f"Reference frame {self.code!r} states ellipsoid "
                f"{self.ellipsoid_name!r}, but HTDP carries it as "
                f"{carried.name!r} on the {carried.ellipsoid.elpsd} ellipsoid "
                f"({expected_ellipsoid!r} in this program's records). HTDP "
                f"chooses the ellipsoid from the frame's name "
                f"(htdp.f:3221-3224), and an ellipsoid height means a "
                f"different place on each, so the record must state the one "
                f"the arithmetic uses."
            )

        htdp_time_dependent = carried in htdp.TIME_DEPENDENT_FRAMES
        if htdp_time_dependent is not (
            self.epoch_kind is FrameEpochKind.TIME_DEPENDENT
        ):
            raise ValueError(
                f"Reference frame {self.code!r} states epoch_kind "
                f"{self.epoch_kind.name}, but HTDP carries it as "
                f"{carried.name!r}, which michspc.spc.htdp treats as "
                f"{'time-dependent' if htdp_time_dependent else 'plate-fixed'}"
                f". The record must agree with the arithmetic about whether a "
                f"position in this frame needs an observation date."
            )

        if (
            carried is htdp.NAD83_2011
            and self.reference_epoch != htdp.NAD83_2011_EPOCH.decimal_year
        ):
            raise ValueError(
                f"Reference frame {self.code!r} is carried as HTDP's "
                f"{carried.name!r} but states reference epoch "
                f"{self.reference_epoch!r}; the HTDP arithmetic holds every "
                f"NAD83(2011) position at "
                f"{htdp.NAD83_2011_EPOCH.decimal_year!r} "
                f"(htdp.NAD83_2011_EPOCH, docs/PLAN-wgs84.md decision D1). "
                f"The record and the computation must state one epoch."
            )

    @property
    def is_usable(self) -> bool:
        return self.status is FrameStatus.USABLE

    @property
    def is_time_dependent(self) -> bool:
        """True when a position in this frame needs its observation epoch."""
        return self.epoch_kind is FrameEpochKind.TIME_DEPENDENT

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


NAD83_2011 = ReferenceFrame(
    code="NAD83(2011)",
    name="North American Datum of 1983, 2011 realization",
    ellipsoid_name="GRS 80",
    citation="NOAA Manual NOS NGS 5, section 1.7, PDF p. 23",
    status=FrameStatus.USABLE,
    epoch_kind=FrameEpochKind.PLATE_FIXED,
    # Reference epoch 2010.00: NOAA Technical Report NOS NGS 62, Table 1
    # ("NAD 83(2011/PA11/MA11) epoch 2010.00"), printed p. 20, PDF p. 29 of the
    # copy frozen at review/nsrs-h3-recon/ifdm/raw/pubs/NOAA_TR_NOS_NGS_0062.pdf.
    # The epoch NGS, OPUS, NCAT and the CORS network publish it at
    # (docs/PLAN-wgs84.md decision D1); checked against htdp.NAD83_2011_EPOCH.
    reference_epoch=2010.0,
    htdp_frame=htdp.NAD83_2011,  # htdp.f:4677-4678, MENU1 frame 1
)
"""The frame SPCS 83 coordinates are expressed in.

The mapping equations themselves are realization-independent - NAD83(1986),
NAD83(HARN) and NAD83(2011) all use the same projection - so this program's
projection math is unaffected by the realization. The realization matters when
a position is moved between frames, which is why the record names the HTDP
frame it is carried as - "NAD_83(2011/CORS96/2007)", North America plate
fixed (``htdp.f:4757``) - and its reference epoch.
"""


NATRF2022 = ReferenceFrame(
    code="NATRF2022",
    name="North American Terrestrial Reference Frame of 2022",
    ellipsoid_name="GRS 80",
    citation=(
        "NOAA Technical Report NOS NGS 62, 'Blueprint for the Modernized NSRS, "
        "Part 1: Geometric Coordinates and Terrestrial Reference Frames', "
        "version of 2021-04-20 - the definitional document: NATRF2022 is one of "
        "the four plate-fixed frames replacing NAD 83, defined relative to "
        "ITRF2020 by the EPP2022 plate rotation model, on the GRS 80 ellipsoid. "
        "Captured 2026-08-29, 4,505,404 bytes, SHA-256 b0d25a26d827daf6ff01c8ba"
        "8d96ee66b12ca200be335f72732f10794d2ae72a, frozen at "
        "review/nsrs-h3-recon/ifdm/raw/pubs/NOAA_TR_NOS_NGS_0062.pdf. The zone "
        "definitions and the projection anchors this program carries for it are "
        "pre-release: NGS beta, captured 2026-08-28 (review/nsrs-n0/, "
        "review/nsrs-h1-anchors/). No transformation between this frame and "
        "NAD83(2011) is registered - NGS has not published one "
        "(docs/DEFERRED-NATRF2022-BRIDGE.md, DESIGN.md #62)"
    ),
    status=FrameStatus.USABLE,
    epoch_kind=FrameEpochKind.PLATE_FIXED,
    # Reference epoch 2020.00: TR NOS NGS 62 section 6, printed p. 18, PDF
    # p. 27 ("The epoch t0 will be 2020.00, and will be identical for all four
    # NSRS TRFs"), and Table 1, printed p. 20, PDF p. 29 ("(N/P/C/M)ATRF2022
    # epoch 2020.00"), in the frozen copy cited above.
    reference_epoch=2020.0,
    # HTDP v3.6.0 does not carry NATRF2022: it is in no line of MENU1
    # (htdp.f:4757-4778).
    htdp_frame=None,
)
"""Usable, and a job may run entirely within it.

The nineteen Michigan SPCS2022 zones are defined on this frame (``zones.py``),
their projection mathematics is anchored against beta NCAT's own results to
NCAT's printed precision, and a geodetic position stated in this frame projects
into any of them. What does NOT exist is the bridge to NAD83(2011): that is a
property of the PAIR, held in the registry below, not a property of this frame.

The status changed at DESIGN.md #62. Before the 2022 zones landed this record
existed only so the refusal had something to refuse; now it carries real work,
and the refusal that remains is the cross-frame one.
"""


# --------------------------------------------------------------------------
# The time-dependent frames HTDP carries to and from NAD83(2011)
# (docs/PLAN-wgs84.md section 1, the owner's decisions 1 and 2; DESIGN.md #70).
#
# Every one is HTDP v3.6.0, github.com/noaa-ngs/HTDP commit
# 59fdbe6b7cf5fabf79f901801ecdc33e7ca2095c, as michspc.spc.htdp transcribes it.
# The ellipsoid follows the frame's name (htdp.f:3221-3224): WGS84(...) frames
# are on the WGS 84 ellipsoid, the ITRF frames on GRS 80 - and the
# ReferenceFrame check above holds each record to that.
# --------------------------------------------------------------------------

_HTDP_SOURCE = (
    f"NGS HTDP v{htdp_data.HTDP_VERSION} ({htdp_data.HTDP_VERSION_DATE}), "
    f"github.com/noaa-ngs/HTDP commit {htdp_data.HTDP_COMMIT}, committed "
    f"unmodified at review/wgs84-w0/htdp-v3.6.0/"
)

_NGA_IMPLEMENTATION_SOURCES = (
    "NGA, ICG-17 Working Group D presentation, 2023; EPSG 9756 and 10607; "
    "IGSMAIL-8444 (docs/PLAN-wgs84.md decision D9)"
)

_WGS84_IN_USE_FROM: Mapping[str, datetime.date] = MappingProxyType(
    {
        # NGA's implementation dates, _NGA_IMPLEMENTATION_SOURCES above
        # (docs/PLAN-wgs84.md decision D9; DESIGN.md #70).
        "WGS84(G1762)": datetime.date(2013, 10, 16),
        "WGS84(G2139)": datetime.date(2021, 1, 3),
        "WGS84(G2296)": datetime.date(2024, 1, 7),
    }
)
"""The first day of each WGS 84 realization's period of use, by frame code.

THE one statement of these dates: each record's citation below prints its
date from this table, and ``realization_period_of_use`` derives every period
from it - including where each period ENDS, which is the day before the next
realization's first day, never a second typed list - so the dates a job is
warned against and the date its record cites cannot differ. The ITRF frames
have no NGA period of use and are deliberately absent.
"""


WGS84_G1762 = ReferenceFrame(
    code="WGS84(G1762)",
    name="World Geodetic System 1984, realization G1762",
    ellipsoid_name="WGS 84",
    citation=(
        f"{_HTDP_SOURCE}: MENU1 frame 10, 'WGS84(G1762)' (htdp.f:4704-4705), "
        f"carried with ITRF2008's parameters ('WGS84(G1762)  "
        f"ITRF2008=IGS08=IGb08 used', htdp.f:4767), on the WGS 84 ellipsoid "
        f"by its name (htdp.f:3221-3224). Implemented by NGA on "
        f"{_WGS84_IN_USE_FROM['WGS84(G1762)'].isoformat()} "
        f"({_NGA_IMPLEMENTATION_SOURCES})"
    ),
    status=FrameStatus.USABLE,
    epoch_kind=FrameEpochKind.TIME_DEPENDENT,
    reference_epoch=None,
    htdp_frame=htdp.WGS84_G1762,
)

WGS84_G2139 = ReferenceFrame(
    code="WGS84(G2139)",
    name="World Geodetic System 1984, realization G2139",
    ellipsoid_name="WGS 84",
    citation=(
        f"{_HTDP_SOURCE}: MENU1 frame 11, 'WGS84(G2139)' (htdp.f:4707-4708), "
        f"carried with ITRF2014's parameters ('WGS84(G2139)  "
        f"ITRF2014=IGS14=IGb14 used', htdp.f:4768), on the WGS 84 ellipsoid "
        f"by its name (htdp.f:3221-3224). Implemented by NGA on "
        f"{_WGS84_IN_USE_FROM['WGS84(G2139)'].isoformat()} "
        f"({_NGA_IMPLEMENTATION_SOURCES})"
    ),
    status=FrameStatus.USABLE,
    epoch_kind=FrameEpochKind.TIME_DEPENDENT,
    reference_epoch=None,
    htdp_frame=htdp.WGS84_G2139,
)

WGS84_G2296 = ReferenceFrame(
    code="WGS84(G2296)",
    name="World Geodetic System 1984, realization G2296",
    ellipsoid_name="WGS 84",
    citation=(
        f"{_HTDP_SOURCE}: MENU1 frame 12, 'WGS84(G2296)' (htdp.f:4710-4711), "
        f"carried with ITRF2020's parameters ('WGS84(G2296)  "
        f"ITRF2020=IGS20=IGb20=ITRF2020-u2023 used', htdp.f:4769), on the "
        f"WGS 84 ellipsoid by its name (htdp.f:3221-3224). Implemented by NGA "
        f"on {_WGS84_IN_USE_FROM['WGS84(G2296)'].isoformat()} "
        f"({_NGA_IMPLEMENTATION_SOURCES})"
    ),
    status=FrameStatus.USABLE,
    epoch_kind=FrameEpochKind.TIME_DEPENDENT,
    reference_epoch=None,
    htdp_frame=htdp.WGS84_G2296,
)

ITRF2014 = ReferenceFrame(
    code="ITRF2014",
    name="International Terrestrial Reference Frame 2014",
    ellipsoid_name="GRS 80",
    citation=(
        f"{_HTDP_SOURCE}: MENU1 frame 25, 'ITRF2014 or IGS14/IGb14' "
        f"(htdp.f:4749-4750, menu text htdp.f:4776), on the GRS 80 ellipsoid "
        f"by its name (htdp.f:3221-3224). Offered by name for precise point "
        f"positioning output, beside the WGS 84 realization that shares its "
        f"parameters (docs/PLAN-wgs84.md section 1, the owner's decision 2)"
    ),
    status=FrameStatus.USABLE,
    epoch_kind=FrameEpochKind.TIME_DEPENDENT,
    reference_epoch=None,
    htdp_frame=htdp.ITRF2014,
)

ITRF2020 = ReferenceFrame(
    code="ITRF2020",
    name="International Terrestrial Reference Frame 2020",
    ellipsoid_name="GRS 80",
    citation=(
        f"{_HTDP_SOURCE}: MENU1 frame 26, 'ITRF2020 or IGS20/IGb20' "
        f"(htdp.f:4752-4753, menu text htdp.f:4777-4778), on the GRS 80 "
        f"ellipsoid by its name (htdp.f:3221-3224). Offered by name for "
        f"precise point positioning output, beside the WGS 84 realization "
        f"that shares its parameters (docs/PLAN-wgs84.md section 1, the "
        f"owner's decision 2)"
    ),
    status=FrameStatus.USABLE,
    epoch_kind=FrameEpochKind.TIME_DEPENDENT,
    reference_epoch=None,
    htdp_frame=htdp.ITRF2020,
)


_TIME_DEPENDENT_OFFERED: tuple[ReferenceFrame, ...] = (
    WGS84_G1762,
    WGS84_G2139,
    WGS84_G2296,
    ITRF2014,
    ITRF2020,
)
"""The five, in the owner's order (plan section 1). Named once so the bare
WGS 84 refusal and the registry below are built from exactly these, never a
typed copy."""


WGS84 = ReferenceFrame(
    code="WGS84",
    name="World Geodetic System 1984, realization not stated",
    ellipsoid_name="WGS 84",
    citation=(
        "Declared so that this program can say NO to a bare 'WGS 84' by name "
        "(docs/DESIGN.md amendments #58 and #70, docs/PLAN-wgs84.md decision "
        "D2). A position labelled only 'WGS 84' cannot be converted, because "
        "the label leaves unstated the two facts that decide where the "
        "position is: WHICH realization it is in - the realizations from "
        "G730 on differ from one another by up to about 9 cm in Michigan, and "
        "the original 1987 realization sits about 1.1 m from them (HTDP "
        "v3.6.0 at 43.82 N 84.77 W, epoch 2010.0; DESIGN.md #70) - "
        "and WHEN it was observed, since a position in a global frame moves "
        "about 17 mm a year against NAD 83 in Michigan "
        "(review/wgs84-w0/RECON.md section 3). The same label is also what "
        "many data collectors print on output that is really NAD 83, and "
        "reading NAD 83 as WGS 84 moves a point by about 1.3 m "
        "(docs/PLAN-wgs84.md section 6) - a plausible, wrong answer with "
        "nothing in the numbers to show it. The realizations this program "
        "carries are separate records, each naming its realization"
    ),
    status=FrameStatus.DECLARED_NOT_USABLE,
    epoch_kind=FrameEpochKind.TIME_DEPENDENT,
    reference_epoch=None,
    # No HTDP frame: the label names no realization HTDP could be asked about.
    htdp_frame=None,
)
"""Declared and NOT usable - the live counterexample ``FrameNotUsableError``
needs, and a statement of fact rather than a placeholder.

It is refused BEFORE the pair lookup, so the message a user gets names the
frame, says why, and names the five realizations to choose from, rather than
reporting a missing transformation and leaving them to conclude that one might
arrive for the bare label.
"""


ALL_FRAMES: tuple[ReferenceFrame, ...] = (
    NAD83_2011,
    NATRF2022,
    WGS84,
    *_TIME_DEPENDENT_OFFERED,
)
"""Every frame this program declares, in DECLARATION order.

The order is the order an interface offers, exactly as ``Zone.allowed_units``
and ``ALL_GEOID_MODELS`` are, so it is a user-visible fact rather than an
accident of iteration - and it is pinned as one. Consumers that offer a choice
filter on ``is_usable``; the unusable member is in this tuple for the same
reason NAPGD2022 is in ``ALL_VERTICAL_DATUMS``.

The five time-dependent frames are APPENDED after the three that were here
before them (DESIGN.md #70, plan W2) rather than inserted beside the bare
WGS 84 label: every existing position in the tuple keeps its index, and the
two frames a zone lives on stay first, as the dropdown has always shown them.
"""

_FRAMES_BY_CODE: Mapping[str, ReferenceFrame] = MappingProxyType(
    {frame.code: frame for frame in ALL_FRAMES}
)


def _check_frame_codes_are_unique() -> None:
    """Refuse to import if two frames share a code: lookups are by code."""
    if len(_FRAMES_BY_CODE) != len(ALL_FRAMES):
        codes = [frame.code for frame in ALL_FRAMES]
        repeated = sorted({code for code in codes if codes.count(code) > 1})
        raise FrameMismatchError(
            f"Reference frame codes must be unique, because every lookup and "
            f"every registry key is by code; repeated: {', '.join(repeated)}."
        )


_check_frame_codes_are_unique()


def frame_by_code(code: str) -> ReferenceFrame:
    """Look up a reference frame by its code.

    Refuses an unknown code rather than guessing, and names what is available -
    the same contract as ``zones.zone_by_code``, ``units.unit_by_code`` and
    ``vertical.vertical_datum_by_code``.
    """
    key = str(code).strip()
    try:
        return _FRAMES_BY_CODE[key]
    except KeyError:
        known = ", ".join(f"{f.code} ({f.name})" for f in ALL_FRAMES)
        raise KeyError(
            f"No reference frame with code {code!r}. Known reference frames "
            f"are: {known}."
        ) from None


# --------------------------------------------------------------------------
# Transformations.
# --------------------------------------------------------------------------

_IDENTITY_CITATION = (
    "Source and target frame are the same, so no transformation is applied and "
    "the position is reported in the frame it was supplied in. No published "
    "product is involved and none is needed."
)


class FrameTransformationMethod(Enum):
    """How a registered path moves a position. Stated, never inferred.

    ``IDENTITY`` is never STORED on a record: an identity has no arithmetic to
    name, and it is the record's own two frames that make it one. It is what
    ``FrameTransformation.applied_method`` reports for an identity, so a job
    record can name the method of every path in one vocabulary.

    ``HTDP_V3_6_0`` is NGS's HTDP v3.6.0 as ``michspc.spc.htdp`` transcribes
    it. The record carries the method and NOTHING of its parameters: HTDP's
    path is fully determined by the two frames' ``htdp_frame`` records, and
    ``htdp_data`` is the one authoritative representation of its numbers. A
    copy of the Helmert set here would be a second representation that could
    drift from the one the arithmetic reads.
    """

    IDENTITY = "identity"
    HTDP_V3_6_0 = f"NGS HTDP v{htdp_data.HTDP_VERSION}"


@dataclass(frozen=True)
class FrameTransformation:
    """One published way to move a position from one reference frame to another.

    An identity record - source and target the same frame - carries no
    method and no parameters at all. Identity is an explicit record rather than
    a ``source is target`` shortcut in the caller, because a NAD83(2011) to
    NAD83(2011) job is legitimate and the outputs must be able to STATE "both
    frames NAD83(2011), no transformation applied" rather than have that fall
    out of an untested branch. That is the contract ``VerticalTransformation``'s
    identity records already hold.

    A non-identity record must state its ``method``, and today the only method
    is HTDP v3.6.0 between NAD83(2011) and one time-dependent frame HTDP
    carries. ``__post_init__`` refuses every other shape - in particular a
    non-identity record with no method, which would leave the position
    unchanged while relabelling its frame: the exact error this module exists
    to prevent.
    """

    source: ReferenceFrame
    target: ReferenceFrame
    citation: str
    method: FrameTransformationMethod | None = None
    """``None`` on an identity, and only there; see ``FrameTransformationMethod``.

    Defaulted so the identity records construct exactly as they always have
    (shape unchanged). A default of ``None`` cannot let a non-identity record
    through: ``__post_init__`` refuses one that states no method."""

    def __post_init__(self) -> None:
        # if/raise, never assert: the suite and the shipped program both run
        # under -O, which strips asserts (DESIGN.md section 7).
        if self.method is not None and not isinstance(
            self.method, FrameTransformationMethod
        ):
            raise TypeError(
                f"Frame transformation {self.source.code} -> "
                f"{self.target.code} states method {self.method!r}, which is "
                f"not a FrameTransformationMethod."
            )

        if self.source.code == self.target.code:
            if self.method is not None:
                raise ValueError(
                    f"Frame transformation {self.source.code} -> "
                    f"{self.target.code} is an identity - the same frame at "
                    f"both ends - but states method {self.method.name}. An "
                    f"identity applies no arithmetic and states no method; "
                    f"that it is one follows from its two frames "
                    f"(applied_method reports IDENTITY), so a stated method "
                    f"would be a second answer that could disagree."
                )
        else:
            if self.method is None or self.method is (
                FrameTransformationMethod.IDENTITY
            ):
                raise ValueError(
                    f"Frame transformation {self.source.code} -> "
                    f"{self.target.code} states "
                    f"{'no method' if self.method is None else 'the identity method'}"
                    f", which would leave the position unchanged while "
                    f"relabelling its frame. NAD83(2011) and NATRF2022 differ "
                    f"by one to two metres, and WGS 84 and NAD83(2011) by "
                    f"about a metre in each of north, east and up in Michigan "
                    f"(review/wgs84-w0/RECON.md section 3), so that is a "
                    f"boundary-moving error that looks entirely ordinary. "
                    f"Only a frame with itself may be an identity; a path "
                    f"between two frames must state the method that moves "
                    f"the position."
                )
            if self.method is FrameTransformationMethod.HTDP_V3_6_0:
                self._require_an_htdp_pair()

        if not self.citation.strip():
            raise ValueError(
                f"Frame transformation {self.source.code} -> "
                f"{self.target.code} has an empty citation. Every record must "
                f"be able to say what it does to a position and on whose "
                f"authority; outputs quote these."
            )

    def _require_an_htdp_pair(self) -> None:
        """An HTDP record: NAD83(2011) at one end, a time-dependent HTDP frame at the other.

        Exactly the paths ``htdp.transform`` carries and nothing wider: HTDP
        could move a position between two global frames, or carry NATRF2022 if
        it were in its menu, and this program offers neither (plan decisions
        D3 and D4).
        """
        ends = (self.source, self.target)
        nad83_ends = [
            end
            for end in ends
            if end.code == NAD83_2011.code and end.htdp_frame is htdp.NAD83_2011
        ]
        others = [end for end in ends if end not in nad83_ends]
        if (
            len(nad83_ends) != 1
            or len(others) != 1
            or not others[0].is_time_dependent
            or others[0].htdp_frame is None
        ):
            raise ValueError(
                f"Frame transformation {self.source.code} -> "
                f"{self.target.code} states method "
                f"{FrameTransformationMethod.HTDP_V3_6_0.name}, but HTDP's "
                f"path here runs only between {NAD83_2011.code} and one "
                f"time-dependent frame HTDP carries "
                f"({', '.join(f.code for f in _TIME_DEPENDENT_OFFERED)}): "
                f"exactly one end must be {NAD83_2011.code} and the other a "
                f"time-dependent frame with an htdp_frame "
                f"(docs/PLAN-wgs84.md decisions D3 and D4)."
            )

    @property
    def is_identity(self) -> bool:
        """True when no transformation is applied and the position is unchanged.

        Derived from the record's own frames rather than stored, so it cannot
        drift from what ``__post_init__`` checked.
        """
        return self.source.code == self.target.code

    @property
    def applied_method(self) -> FrameTransformationMethod:
        """The method this record applies: ``IDENTITY``, derived, or the stated one."""
        if self.is_identity:
            return FrameTransformationMethod.IDENTITY
        return self.method

    @property
    def direction_statement(self) -> str:
        """The transformation in words. What outputs quote.

        Written from the record's own fields for the reason
        ``VerticalTransformation.direction_statement`` is: a record and the
        sentence describing it must be incapable of disagreeing. Facts only,
        no caveats (the owner's rule, DESIGN.md #50).
        """
        if self.is_identity:
            return (
                f"Both positions are in {self.source.name} "
                f"({self.source.code}); no frame transformation is applied."
            )
        if self.method is FrameTransformationMethod.HTDP_V3_6_0:
            return self._htdp_direction_statement()
        # Unreachable: __post_init__ admits no other non-identity record. A
        # refusal rather than a guess, so a method added without its own
        # sentence fails loudly here instead of printing a blank or a lie into
        # a job record.
        raise ValueError(
            f"Frame transformation {self.source.code} -> {self.target.code} "
            f"states method {self.method!r}, which has no direction "
            f"statement. Add one written from the record's fields."
        )

    def _htdp_direction_statement(self) -> str:
        """HTDP's direction-specific composition, from the frames' own records.

        HTDP evaluates the Helmert at the INPUT epoch and then propagates the
        position with the OUTPUT frame's velocity (``htdp.f:3229-3273``;
        review/wgs84-w0/RECON.md section 1.4) - so the two directions are not
        mirror images, and each sentence says which it is.
        """
        source, target = self.source, self.target
        if source.is_time_dependent:
            source_epoch = "at the observation epoch"
            target_epoch = f"at its reference epoch {target.reference_epoch!r}"
            helmert_at = "the observation epoch"
            span = f"from the observation epoch to {target.reference_epoch!r}"
        else:
            source_epoch = f"at its reference epoch {source.reference_epoch!r}"
            target_epoch = "at the observation epoch"
            helmert_at = f"{source.reference_epoch!r}"
            span = f"from {source.reference_epoch!r} to the observation epoch"
        if target.is_time_dependent:
            velocity = (
                f"the {target.code} velocity, which includes the full motion "
                f"of the North American plate"
            )
        else:
            velocity = (
                f"the {target.code} velocity, which is the small intraplate "
                f"motion left in a plate-fixed frame"
            )
        return (
            f"The position is transformed from {source.name} ({source.code}) "
            f"{source_epoch} to {target.name} ({target.code}) {target_epoch} "
            f"by {_HTDP_SOURCE}. HTDP evaluates the 14-parameter Helmert "
            f"transformation at the input epoch, {helmert_at}, and then "
            f"propagates the position {span} with the output frame's velocity: "
            f"{velocity}, from HTDP's ITRF2008 velocity grid for its region 6, "
            f"interpolated bilinearly. When the observation date is "
            f"{htdp.NAD83_2011_EPOCH.date.isoformat()} the span is zero and "
            f"HTDP applies the Helmert transformation alone."
        )

    def __str__(self) -> str:
        return f"{self.source.code} -> {self.target.code}"


_IDENTITY_NAD83_2011 = FrameTransformation(
    source=NAD83_2011,
    target=NAD83_2011,
    citation=_IDENTITY_CITATION,
)

_IDENTITY_NATRF2022 = FrameTransformation(
    source=NATRF2022,
    target=NATRF2022,
    citation=_IDENTITY_CITATION,
)

# There is deliberately NO identity for WGS84. An unusable frame gets no
# registered path of any kind, so that removing the usability check could never
# leave a WGS 84 job quietly running as an identity - it would still have to
# get past a missing registry entry. Pinned.
#
# And deliberately NO identity for the five time-dependent frames either
# (plan W2). Every grid this program reads a position against - GEOID18,
# GEOID12B, VERTCON 3.0 - is published against NAD 83, so even a job that
# leaves a WGS 84 position in its own frame needs it carried to NAD83(2011)
# first. Work package W3 decided how such a job runs (plan D8): the
# vertical-only job's pivot is found through the frame's registered path to
# NAD83(2011) (``convert.pivot_path``), never through an identity - so an
# identity here could only ever be the WGS 84 position looked up in a NAD 83
# grid. Pinned.


def _htdp_citation(source: ReferenceFrame, target: ReferenceFrame) -> str:
    other = target if source.code == NAD83_2011.code else source
    return (
        f"{_HTDP_SOURCE}, transcribed by michspc.spc.htdp: TRFPOS "
        f"(htdp.f:3175-3294) between {NAD83_2011.code} at epoch "
        f"{NAD83_2011.reference_epoch!r} (docs/PLAN-wgs84.md decision D1) and "
        f"{other.code}. Reproduced to HTDP's printed digit on every frozen "
        f"anchor in tests/fixtures/htdp_anchors.py (review/wgs84-w0/)"
    )


def _htdp_pair(
    source: ReferenceFrame, target: ReferenceFrame
) -> FrameTransformation:
    return FrameTransformation(
        source=source,
        target=target,
        citation=_htdp_citation(source, target),
        method=FrameTransformationMethod.HTDP_V3_6_0,
    )


_HTDP_TRANSFORMATIONS: tuple[FrameTransformation, ...] = tuple(
    record
    for frame in _TIME_DEPENDENT_OFFERED
    for record in (_htdp_pair(frame, NAD83_2011), _htdp_pair(NAD83_2011, frame))
)
"""Ten records: each time-dependent frame to NAD83(2011), and back."""


FRAME_TRANSFORMATIONS: Mapping[
    tuple[ReferenceFrame, ReferenceFrame], FrameTransformation
] = MappingProxyType(
    {
        (NAD83_2011, NAD83_2011): _IDENTITY_NAD83_2011,
        (NATRF2022, NATRF2022): _IDENTITY_NATRF2022,
        **{
            (record.source, record.target): record
            for record in _HTDP_TRANSFORMATIONS
        },
    }
)
"""Every path this program carries, keyed by (source, target).

Read-only on purpose. A registry whose whole job is to keep every pair it has
ever carried (DESIGN.md #32) must not be something a later module can pop an
entry out of at runtime.
"""

# Resolution is by code, not by object identity, so a frame record rebuilt from
# a saved job still finds its path - the property ``require_same_frame`` had
# from the beginning, and the reason a job converted today still converts after
# a later release rebuilds these records. Derived from the registry above,
# never maintained beside it.
_TRANSFORMATIONS_BY_CODE: Mapping[tuple[str, str], FrameTransformation] = (
    MappingProxyType(
        {
            (source.code, target.code): transformation
            for (source, target), transformation in FRAME_TRANSFORMATIONS.items()
        }
    )
)


REQUIRED_FRAME_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("NAD83(2011)", "NAD83(2011)"),
        ("NATRF2022", "NATRF2022"),
        # Appended by the WGS 84 build, plan W2 (DESIGN.md #70): HTDP v3.6.0
        # between NAD83(2011) and each time-dependent frame, both directions.
        ("WGS84(G1762)", "NAD83(2011)"),
        ("NAD83(2011)", "WGS84(G1762)"),
        ("WGS84(G2139)", "NAD83(2011)"),
        ("NAD83(2011)", "WGS84(G2139)"),
        ("WGS84(G2296)", "NAD83(2011)"),
        ("NAD83(2011)", "WGS84(G2296)"),
        ("ITRF2014", "NAD83(2011)"),
        ("NAD83(2011)", "ITRF2014"),
        ("ITRF2020", "NAD83(2011)"),
        ("NAD83(2011)", "ITRF2020"),
    }
)
"""Pairs the registry must never lose. APPEND-ONLY: may grow, never shrink.

DESIGN.md amendment #32 states backwards compatibility as a requirement rather
than an assumption - a job converted in one year must still convert and still
reproduce years later. This is that requirement written down where a test, and
the import check below, can enforce it. Adding the NAD83(2011) <-> NATRF2022
bridge later means ADDING its two pairs here; removing any line is the change
#32 forbids. The ten HTDP pairs are typed out as codes rather than derived from
the registry, deliberately: a list derived from the thing it checks could
never find that thing incomplete.
"""


def _check_registry_keeps_every_required_pair() -> None:
    """Refuse to import if a pair required by #32 has been dropped.

    Loud at startup beats quiet at the first job that needed the missing pair.
    if/raise rather than assert, because -O strips asserts.
    """
    missing = sorted(REQUIRED_FRAME_PAIRS - set(_TRANSFORMATIONS_BY_CODE))
    if missing:
        dropped = ", ".join(f"{source} -> {target}" for source, target in missing)
        raise FrameMismatchError(
            f"The frame transformation registry has lost pairs it is required "
            f"to keep: {dropped}. DESIGN.md amendment #32 requires that every "
            f"pair this program has ever carried keeps working, so that a job "
            f"converted years ago still converts and still reproduces. Restore "
            f"the record rather than removing it from REQUIRED_FRAME_PAIRS."
        )


_check_registry_keeps_every_required_pair()


def _canonical(frame: ReferenceFrame) -> ReferenceFrame:
    """The registry's own record for this frame's code - or a refusal.

    A record rebuilt from a saved job, or hand-built by a caller, must not be
    able to claim a status this module did not grant it - that is how an
    unusable frame would slip through, and a hand-built ``ReferenceFrame`` is
    a two-line thing to write. Nor may it state any OTHER fact the registry's
    record does not: until interim gate 1 of the WGS 84 build (finding L4)
    this function silently substituted the registry's record for a
    disagreeing one, so the frame gate answered for the registry's frame while
    every caller downstream still held - and could read - the caller's.
    Now a record whose code names a registry frame resolves only when it is
    EQUAL to that frame's record, field for field, and otherwise is refused,
    naming the fields that disagree. Equal means equal in value: a record
    rebuilt from data that states the registry's facts resolves, though it is
    not the same object.

    An unrecognised code is returned unchanged, so it reaches the pair refusal
    below, which names it.
    """
    registered = _FRAMES_BY_CODE.get(frame.code)
    if registered is None:
        return frame
    if frame == registered:
        return registered
    differing = [
        field.name
        for field in dataclasses.fields(ReferenceFrame)
        if getattr(frame, field.name) != getattr(registered, field.name)
    ]

    def shown(value: object) -> str:
        text = repr(value)
        return text if len(text) <= 70 else text[:67] + "..."

    details = "; ".join(
        f"{name} {shown(getattr(frame, name))}, where the registry states "
        f"{shown(getattr(registered, name))}"
        for name in differing
    )
    raise FrameRecordMismatchError(
        f"The reference frame record passed as {frame.code!r} is not this "
        f"program's record for {frame.code}: its {', '.join(differing)} "
        f"{'differ' if len(differing) > 1 else 'differs'} ({details}). A "
        f"record that carries a registered frame's code must state exactly "
        f"that frame's facts. A disagreeing copy says one frame in its code "
        f"and another in its ellipsoid, epoch or HTDP frame, and which of the "
        f"two a conversion followed would depend on which field it read - "
        f"for NAD 83 and WGS 84 a metre or more apart. Use "
        f"michspc.spc.frames.frame_by_code({frame.code!r})."
    )


def resolve_frame(frame: ReferenceFrame) -> ReferenceFrame:
    """The registry's record for ``frame``, refusing a disagreeing copy.

    The public form of the check ``require_frame_path`` makes on both its
    arguments, for a caller that takes a frame and keeps it without asking for
    a path - ``convert.geodetic_position``, whose result carries the frame into
    the job record. It answers only whether the record is consistent with the
    registry: an unrecognised code comes back unchanged, and whether the frame
    is USABLE is not asked here.
    """
    if not isinstance(frame, ReferenceFrame):
        raise TypeError(
            f"resolve_frame needs a michspc.spc.frames.ReferenceFrame; got "
            f"{type(frame).__name__} ({frame!r})."
        )
    return _canonical(frame)


@dataclass(frozen=True)
class RealizationPeriod:
    """A WGS 84 realization's period of use, derived from ``_WGS84_IN_USE_FROM``.

    ``first_day`` is NGA's implementation date. ``last_day`` is the day before
    the NEXT realization's implementation date - NGA replaces one realization
    with the next, so the next one's start is this one's end - and None for
    the newest, whose period has not ended. ``succeeded_by`` is that next
    realization's code, or None.
    """

    first_day: datetime.date
    last_day: datetime.date | None
    succeeded_by: str | None

    def contains(self, day: datetime.date) -> bool:
        """Whether ``day`` falls inside the period, both ends inclusive."""
        if day < self.first_day:
            return False
        return self.last_day is None or day <= self.last_day


def realization_period_of_use(frame: ReferenceFrame) -> RealizationPeriod | None:
    """A WGS 84 realization's period of use, or None for a frame with none.

    None for every frame that has no such period - the ITRF frames, NAD 83,
    NATRF2022 - which is a statement, not an absence: plan decision D9 warns
    about an observation dated OUTSIDE its realization's period of use, and
    only the NGA realizations have one. The end of each period is DERIVED
    from the one table of start dates (``_WGS84_IN_USE_FROM``), ordered by
    date: G1762 runs to the day before G2139 began, G2139 to the day before
    G2296 began, and G2296 has no end yet. Asked of the registry's record
    (``resolve_frame``), so a disagreeing copy is refused rather than looked
    up by its code.
    """
    code = resolve_frame(frame).code
    first_day = _WGS84_IN_USE_FROM.get(code)
    if first_day is None:
        return None
    later = sorted(
        (start, other)
        for other, start in _WGS84_IN_USE_FROM.items()
        if start > first_day
    )
    if not later:
        return RealizationPeriod(first_day=first_day, last_day=None, succeeded_by=None)
    next_start, next_code = later[0]
    return RealizationPeriod(
        first_day=first_day,
        last_day=next_start - datetime.timedelta(days=1),
        succeeded_by=next_code,
    )


def realization_in_use_from(frame: ReferenceFrame) -> datetime.date | None:
    """The first day of a WGS 84 realization's period of use, or None."""
    period = realization_period_of_use(frame)
    return period.first_day if period is not None else None


def _realizations_message() -> str:
    """The sentence that tells a user which named frames to choose from."""
    offered = [frame for frame in _TIME_DEPENDENT_OFFERED if frame.is_usable]
    names = ", ".join(frame.code for frame in offered[:-1])
    return (
        f"Choose the realization the position is actually in: {names} or "
        f"{offered[-1].code}."
    )


def _no_path_message(source: ReferenceFrame, target: ReferenceFrame) -> str:
    """Why this particular pair has no registered path - true for THIS pair.

    Each refusal states only what is true of the pair it is printed for: the
    unpublished NAD83(2011) <-> NATRF2022 bridge (DESIGN.md #62), HTDP's
    silence on NATRF2022 (plan decision D3), the global-to-global pairs this
    program does not offer (plan decision D4), the time-dependent frame with
    no identity (plan W2), and a generic sentence for anything else - which
    names no fact it cannot know.
    """
    prefix = (
        f"Cannot convert from {source.code} to {target.code}: no "
        f"transformation between these two reference frames is implemented."
    )
    codes = {source.code, target.code}
    known_td = {frame.code for frame in _TIME_DEPENDENT_OFFERED}

    if codes == {NAD83_2011.code, NATRF2022.code}:
        known = ", ".join(f"{s} -> {t}" for s, t in sorted(_TRANSFORMATIONS_BY_CODE))
        return (
            f"{prefix} Registered paths are: {known}. "
            f"Coordinates differ between NAD83(2011) and NATRF2022 by one to "
            f"two metres - more than the width of a road, and nothing in the "
            f"numbers shows it - so passing them through unchanged would "
            f"silently corrupt them. NGS has not published the "
            f"NAD83(2011) <-> NATRF2022 transformation: its own NCAT computes "
            f"one from server-side parameters that appear in no published "
            f"document or shipped file, and the best public candidate set "
            f"misses NCAT by 17 cm at one of twelve frozen Michigan anchors "
            f"(docs/DEFERRED-NATRF2022-BRIDGE.md; docs/DESIGN.md amendment "
            f"#62). Convert within a single frame - every zone in one era, and "
            f"geodetic in and out of it, works today - or wait: this "
            f"transformation lands when NGS publishes it."
        )

    if NATRF2022.code in codes and codes & known_td and len(codes) == 2:
        (global_code,) = codes & known_td
        return (
            f"{prefix} NGS's HTDP v{htdp_data.HTDP_VERSION}, which carries "
            f"{global_code} to and from {NAD83_2011.code}, does not carry "
            f"{NATRF2022.code} at all (it is in no line of HTDP's frame menu, "
            f"htdp.f:4757-4778). Going through {NAD83_2011.code} instead would "
            f"need the {NAD83_2011.code} <-> {NATRF2022.code} transformation, "
            f"and NGS has not published one (docs/DEFERRED-NATRF2022-BRIDGE.md; "
            f"docs/DESIGN.md amendment #62; docs/PLAN-wgs84.md decision D3). "
            f"Passing the position through unchanged would silently corrupt "
            f"it. This program's path for a position in {global_code} is to "
            f"{NAD83_2011.code}, the frame the SPCS 83 zones are defined on; "
            f"{NATRF2022.code} work needs a position already stated in "
            f"{NATRF2022.code}."
        )

    if codes <= known_td and len(codes) == 2:
        return (
            f"{prefix} No State Plane zone is defined on {source.code} or on "
            f"{target.code}, so the only conversion this program offers for a "
            f"position in either is to or from {NAD83_2011.code} "
            f"(docs/PLAN-wgs84.md decision D4). Convert via "
            f"{NAD83_2011.code} instead: {source.code} to {NAD83_2011.code}, "
            f"then {NAD83_2011.code} to {target.code}."
        )

    if codes <= known_td and len(codes) == 1:
        return (
            f"Cannot keep a position in {source.code}: no identity is "
            f"registered for it. {source.code} is a time-dependent frame, and "
            f"every grid this program reads a position against - the GEOID18 "
            f"and GEOID12B geoid models and the VERTCON 3.0 grids - is "
            f"published against {NAD83_2011.code}, so even a job that leaves "
            f"the position in {source.code} needs it carried to "
            f"{NAD83_2011.code} first, and this program does that through the "
            f"registered {source.code} -> {NAD83_2011.code} path, never an "
            f"identity (docs/PLAN-wgs84.md decision D8). Converting one "
            f"{source.code} position to another {source.code} position is "
            f"not a conversion."
        )

    known = ", ".join(f"{s} -> {t}" for s, t in sorted(_TRANSFORMATIONS_BY_CODE))
    return (
        f"Cannot convert from {source.code} to {target.code}: no "
        f"transformation between these two reference frames is registered. "
        f"Registered paths are: {known}. Passing a position between two "
        f"frames unchanged while relabelling it would silently corrupt it."
    )


def require_frame_path(
    source: ReferenceFrame, target: ReferenceFrame
) -> FrameTransformation:
    """The registered path for this pair of frames, or a loud refusal.

    Called on every conversion, and it replaces ``require_same_frame``: one
    gate per path, returning the record that describes what was done, rather
    than a check that returns nothing and a separate lookup that could
    disagree with it.

    Within one frame the zone-to-zone conversion is an exact, reversible
    re-projection of the same physical position, and this function returns
    that frame's identity record. Between NAD83(2011) and a time-dependent
    frame it returns the HTDP record, which the conversion pipeline applies
    (``convert.require_an_applicable_path``, work package W3).

    Two distinct refusals, because they mean different things to a user:

    * ``FrameNotUsableError`` - the frame is declared here but this program
      cannot carry coordinates in it (the bare WGS 84 label). Checked FIRST,
      so the message names the frame and the realizations to choose instead,
      rather than reporting a missing transformation and implying one might be
      coming for the bare label.
    * ``FrameTransformationUnavailableError`` - both frames are usable, but no
      transformation between them is registered, with the reason true for
      that pair (``_no_path_message``).

    Never a silent pass-through. An untransformed position labelled as
    transformed is a boundary-relevant error that looks entirely ordinary.

    Refuses a non-``ReferenceFrame`` argument by name, for the reason
    docs/DESIGN.md amendment #11 finding 1 records: this program's core records
    all carry ``code``, ``name`` and ``citation``, so a ``Zone``, a
    ``VerticalDatum`` and a ``LinearUnit`` all duck-type through ``_canonical``
    and would only fail several lines later on ``is_usable`` - as an
    ``AttributeError``, which walks straight through the
    ``except FrameMismatchError`` every caller of this module writes. Passing
    ``source_zone`` where ``source_zone.frame`` was meant is the likeliest
    version of that mistake, and it is one character.
    """
    for label, frame in (("source", source), ("target", target)):
        if not isinstance(frame, ReferenceFrame):
            raise TypeError(
                f"require_frame_path needs a michspc.spc.frames."
                f"ReferenceFrame as its {label}; got "
                f"{type(frame).__name__} ({frame!r}). Every record in this "
                f"core carries code, name and citation, so a zone, a vertical "
                f"datum or a unit reaches this function without complaint and "
                f"would be asked whether it is a usable reference FRAME. Pass "
                f"michspc.spc.frames.NAD83_2011, or a zone's own .frame."
            )

    resolved_source = _canonical(source)
    resolved_target = _canonical(target)

    unusable: list[ReferenceFrame] = []
    for frame in (resolved_source, resolved_target):
        if not frame.is_usable and frame.code not in {f.code for f in unusable}:
            unusable.append(frame)

    if unusable:
        offenders = " and ".join(f.code for f in unusable)
        verb = "are" if len(unusable) > 1 else "is"
        details = " ".join(f"{f.code} ({f.name}): {f.citation}." for f in unusable)
        # The bare WGS 84 label (plan decision D2): an unusable time-dependent
        # frame is one whose realization is unstated, and the way on is to
        # name it. Asked of the record, not of its code.
        choose = (
            f" {_realizations_message()}"
            if any(f.is_time_dependent for f in unusable)
            else ""
        )
        usable = ", ".join(f.code for f in ALL_FRAMES if f.is_usable)
        raise FrameNotUsableError(
            f"Cannot convert from {resolved_source.code} to "
            f"{resolved_target.code}: {offenders} {verb} declared in this "
            f"program but not usable. {details} Any coordinate this program "
            f"reported in that frame would be invented rather than converted."
            f"{choose} The reference frames this program can carry are: "
            f"{usable}."
        )

    try:
        return _TRANSFORMATIONS_BY_CODE[(resolved_source.code, resolved_target.code)]
    except KeyError:
        raise FrameTransformationUnavailableError(
            _no_path_message(resolved_source, resolved_target)
        ) from None
