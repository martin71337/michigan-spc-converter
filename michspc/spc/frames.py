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

**What this registry carries today is identities and nothing else**
(docs/DESIGN.md amendment #62, and the standing marker
docs/DEFERRED-NATRF2022-BRIDGE.md). Work WITHIN each frame is complete: the
three SPCS 83 zones on NAD83(2011), the nineteen SPCS2022 zones on NATRF2022,
any-to-any within either era, geodetic in and out on either frame. Work ACROSS
the two frames refuses, because NGS has not published the transformation - its
NCAT computes one from server-side parameters that are not in any published
document or shipped file, and the best public candidate set misses NCAT by
17 cm at one of twelve frozen Michigan anchors. A 17 cm disagreement with the
national tool is a boundary-moving amount, and shipping it is precisely what
this program exists to refuse.

**So a ``FrameTransformation`` here has no parameters yet, only an identity
shape**, exactly as ``VerticalTransformation``'s identity records carry no
model, no release and no grid. When the bridge lands (``helmert.py``, deferred
with it) the parameterized fields arrive as optional fields defaulting to
``None``, and every record below is unchanged by that addition.

**Backwards compatibility is a requirement, not an assumption** (DESIGN.md
amendment #32, stated there for the vertical registry and binding here for the
same reason). A job converted under this program must still convert, and still
reproduce, after NGS publishes: ``REQUIRED_FRAME_PAIRS`` states that as an
append-only list which may grow and may never shrink, and this module refuses to
import if the registry has lost one of them - so a deleted pair fails loudly at
startup rather than quietly at the first job that needed it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


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

    WGS 84 is declared and not usable. It is not a typo and not a missing
    feature flag: a WGS 84 position is not a NAD 83 position and is not a
    NATRF2022 position, no transformation from it is registered here, and the
    difference is metre-level in CONUS - boundary-moving by this project's own
    tier sentence (docs/DESIGN.md amendment #58).
    """


class FrameTransformationUnavailableError(FrameMismatchError):
    """Raised when no published transformation exists for a pair of frames.

    Not a warning and not a silent pass-through: leaving a latitude and
    longitude alone while calling it transformed is exactly the failure the
    tier sentence exists to prevent. NAD83(2011) to NATRF2022 raises this
    today (DESIGN.md #62).
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

    @property
    def is_usable(self) -> bool:
        return self.status is FrameStatus.USABLE

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


NAD83_2011 = ReferenceFrame(
    code="NAD83(2011)",
    name="North American Datum of 1983, 2011 realization",
    ellipsoid_name="GRS 80",
    citation="NOAA Manual NOS NGS 5, section 1.7, PDF p. 23",
    status=FrameStatus.USABLE,
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


WGS84 = ReferenceFrame(
    code="WGS84",
    name="World Geodetic System 1984",
    ellipsoid_name="WGS 84",
    citation=(
        "Declared so that this program can say NO to it by name. WGS 84 is not "
        "NAD 83 and is not NATRF2022: the frames are a metre or more apart in "
        "CONUS, which is boundary-moving by this program's own standard, and a "
        "handheld receiver's WGS 84 position pastes into a latitude/longitude "
        "field cleanly and converts to something plausible and wrong "
        "(docs/DESIGN.md amendment #58, which is why every geodetic selection "
        "on screen names its datum). No transformation to or from it is "
        "registered here, and this program has no data with which to compute "
        "one. Nothing in the program produces or accepts a coordinate in this "
        "frame; it exists in the registry because the fact that WGS 84 is a "
        "different frame is the fact a user most needs stated"
    ),
    status=FrameStatus.DECLARED_NOT_USABLE,
)
"""Declared and NOT usable - the live counterexample ``FrameNotUsableError``
needs, and a statement of fact rather than a placeholder.

It is refused BEFORE the pair lookup, so the message a user gets names the
frame and says why, rather than reporting a missing transformation and leaving
them to conclude that one might arrive.
"""


ALL_FRAMES: tuple[ReferenceFrame, ...] = (NAD83_2011, NATRF2022, WGS84)
"""Every frame this program declares, in DECLARATION order.

The order is the order an interface offers, exactly as ``Zone.allowed_units``
and ``ALL_GEOID_MODELS`` are, so it is a user-visible fact rather than an
accident of iteration - and it is pinned as one. Consumers that offer a choice
filter on ``is_usable``; the unusable member is in this tuple for the same
reason NAPGD2022 is in ``ALL_VERTICAL_DATUMS``.
"""

_FRAMES_BY_CODE: Mapping[str, ReferenceFrame] = MappingProxyType(
    {frame.code: frame for frame in ALL_FRAMES}
)


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
#
# Identities only, today. See this module's docstring and DESIGN.md #62: the
# NAD83(2011) <-> NATRF2022 bridge is deferred with its evidence recorded in
# docs/DEFERRED-NATRF2022-BRIDGE.md, and it is deferred because NGS has not
# published the transformation, not because it was not attempted.
# --------------------------------------------------------------------------

_IDENTITY_CITATION = (
    "Source and target frame are the same, so no transformation is applied and "
    "the position is reported in the frame it was supplied in. No published "
    "product is involved and none is needed."
)


@dataclass(frozen=True)
class FrameTransformation:
    """One published way to move a position from one reference frame to another.

    An identity record - source and target the same frame - carries no
    parameters at all, and today every record in the registry is one. Identity
    is an explicit record rather than a ``source is target`` shortcut in the
    caller, because a NAD83(2011) to NAD83(2011) job is legitimate and the
    outputs must be able to STATE "both frames NAD83(2011), no transformation
    applied" rather than have that fall out of an untested branch. That is the
    contract ``VerticalTransformation``'s identity records already hold.

    **The parameterized fields are deliberately absent, not defaulted to
    nothing.** When the bridge lands they arrive as optional fields defaulting
    to ``None`` and these records construct unchanged; a half-specified record
    is then caught the way ``VerticalTransformation.__post_init__`` catches one.
    Until then ``__post_init__`` below refuses any record that is not an
    identity, so this module cannot grow a silent pass-through between two
    different frames - which is the exact shape of the error it exists to
    prevent.
    """

    source: ReferenceFrame
    target: ReferenceFrame
    citation: str

    def __post_init__(self) -> None:
        # if/raise, never assert: the suite and the shipped program both run
        # under -O, which strips asserts (DESIGN.md section 7).
        if self.source.code != self.target.code:
            raise ValueError(
                f"Frame transformation {self.source.code} -> "
                f"{self.target.code} carries no parameters, which would leave "
                f"the position unchanged while relabelling its frame. "
                f"NAD83(2011) and NATRF2022 differ by one to two metres, so "
                f"that is a boundary-moving error that looks entirely "
                f"ordinary. Only a frame with itself may be an identity, and "
                f"an identity is all this registry carries today "
                f"(docs/DEFERRED-NATRF2022-BRIDGE.md, DESIGN.md #62)."
            )

        if not self.citation.strip():
            raise ValueError(
                f"Frame transformation {self.source.code} -> "
                f"{self.target.code} has an empty citation. Every record must "
                f"be able to say what it does to a position and on whose "
                f"authority; outputs quote these."
            )

    @property
    def is_identity(self) -> bool:
        """True when no transformation is applied and the position is unchanged.

        Derived from the record's own frames rather than stored, so it cannot
        drift from what ``__post_init__`` checked. Every record answers True
        today; the property is written so that it keeps answering correctly
        when parameterized records join it.
        """
        return self.source.code == self.target.code

    @property
    def direction_statement(self) -> str:
        """The transformation in words. What outputs quote.

        Written from the record's own fields for the reason
        ``VerticalTransformation.direction_statement`` is: a record and the
        sentence describing it must be incapable of disagreeing.
        """
        if self.is_identity:
            return (
                f"Both positions are in {self.source.name} "
                f"({self.source.code}); no frame transformation is applied."
            )
        # Unreachable while the registry carries identities only - and it is
        # written as a refusal rather than a guess so that a parameterized
        # record added without its own sentence fails loudly here instead of
        # printing a blank or a lie into a job record.
        raise NotImplementedError(
            f"Frame transformation {self.source.code} -> {self.target.code} "
            f"is not an identity, so it must state its own arithmetic. Add "
            f"that statement with the parameters "
            f"(docs/DEFERRED-NATRF2022-BRIDGE.md)."
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


FRAME_TRANSFORMATIONS: Mapping[
    tuple[ReferenceFrame, ReferenceFrame], FrameTransformation
] = MappingProxyType(
    {
        (NAD83_2011, NAD83_2011): _IDENTITY_NAD83_2011,
        (NATRF2022, NATRF2022): _IDENTITY_NATRF2022,
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
    }
)
"""Pairs the registry must never lose. APPEND-ONLY: may grow, never shrink.

DESIGN.md amendment #32 states backwards compatibility as a requirement rather
than an assumption - a job converted in one year must still convert and still
reproduce years later. This is that requirement written down where a test, and
the import check below, can enforce it. Adding the NAD83(2011) <-> NATRF2022
bridge later means ADDING its two pairs here; removing any line is the change
#32 forbids.
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
    """The registry's own record for this frame's code, when it has one.

    A record rebuilt from a saved job, or hand-built by a caller, must not be
    able to claim a status this module did not grant it - that is how an
    unusable frame would slip through, and a hand-built ``ReferenceFrame`` is
    a two-line thing to write. An unrecognised code is returned unchanged, so
    it reaches the pair refusal below, which names it.
    """
    return _FRAMES_BY_CODE.get(frame.code, frame)


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
    that frame's identity record.

    Two distinct refusals, because they mean different things to a user:

    * ``FrameNotUsableError`` - the frame is declared here but this program
      cannot carry coordinates in it (WGS 84 today). Checked FIRST, so the
      message names the frame rather than reporting a missing transformation
      and implying one might be coming.
    * ``FrameTransformationUnavailableError`` - both frames are usable, but no
      transformation between them is published or implemented (NAD83(2011) to
      NATRF2022 today, DESIGN.md #62).

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
        usable = ", ".join(f.code for f in ALL_FRAMES if f.is_usable)
        raise FrameNotUsableError(
            f"Cannot convert from {resolved_source.code} to "
            f"{resolved_target.code}: {offenders} {verb} declared in this "
            f"program but not usable. {details} Any coordinate this program "
            f"reported in that frame would be invented rather than converted. "
            f"The reference frames this program can carry today are: {usable}."
        )

    try:
        return _TRANSFORMATIONS_BY_CODE[(resolved_source.code, resolved_target.code)]
    except KeyError:
        known = ", ".join(f"{s} -> {t}" for s, t in sorted(_TRANSFORMATIONS_BY_CODE))
        raise FrameTransformationUnavailableError(
            f"Cannot convert from {resolved_source.code} to "
            f"{resolved_target.code}: no transformation between these two "
            f"reference frames is implemented. Registered paths are: {known}. "
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
        ) from None
