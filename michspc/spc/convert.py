"""The conversion pipeline.

One point in, one immutable record out, carrying not just the answer but the
evidence for it: the geodetic pivot, both zones' convergence and scale factor,
and every warning raised along the way.

The pipeline shape (docs/DESIGN.md section 4):

    (source zone, N, E) --inverse--> geodetic --forward--> (target zone, N, E)

Both steps go through michspc.spc.projection, which dispatches on the zone's
own definition record to the engine for that projection - the rigorous Lambert
conformal conic equations of NOAA Manual NOS NGS 5 section 3.1 for every SPCS 83
zone, and sections 3.2 and 3.3 for the transverse and oblique Mercator zones.
Nothing here names an engine: a zone in a projection this program does not
implement refuses by name in the dispatcher rather than being computed by
whichever engine happened to be imported.

**On verification.** An earlier design computed every coordinate a second time
by the manual's section 3.4 polynomial coefficient method and cross-checked the
two at runtime. That engine was removed (docs/DESIGN.md amendment #14): it
carried NGS's own stated 0.5 mm fitting error, degraded to metres outside each
zone's fitted band, and required a special-case policy to stay quiet - which
made it a second thing to verify rather than a check. What verifies this code is
external and lives in the test suite: 27 frozen NGS NCAT anchors, and every
published Appendix C derived constant reproduced from the defining constants
alone.

**Frame transformations** (docs/PLAN-wgs84.md sections 3.4 and 3.5, decisions
D5 and D6; docs/DESIGN.md #70). A geodetic end may be in one of the five
time-dependent frames the registry carries - WGS84(G1762), (G2139), (G2296),
ITRF2014 and ITRF2020 - and then its position is moved to or from NAD83(2011)
at 2010.0 by NGS HTDP v3.6.0 (``michspc.spc.htdp``), exactly once, on the side
the registered path requires:

    WGS 84/ITRF geodetic --HTDP--> NAD 83 pivot --forward--> (zone, N, E)
    (zone, N, E) --inverse--> NAD 83 pivot --HTDP--> WGS 84/ITRF geodetic
    WGS 84/ITRF geodetic <--HTDP--> NAD 83 geodetic

**The pivot is ALWAYS the NAD 83(2011) position** (plan D5):
``PointConversion.latitude`` and ``longitude`` keep meaning the position in
the zone's frame, so the projection, the extent check and every grid this
program reads (GEOID18, GEOID12B, VERTCON 3.0 - all published against NAD 83)
see exactly what they always saw. The WGS 84 or ITRF position travels beside
the pivot as a second, frame-tagged position (``ExternalPosition``), with the
evidence for the transformation. A same-frame conversion carries none of it
and is bit-identical to what this module produced before the frames existed.

All linear values in this module are meters. Unit conversion happens at the file
boundary, not here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum

from michspc.spc import htdp
from michspc.spc.frames import (
    NAD83_2011,
    FrameTransformation,
    FrameTransformationMethod,
    FrameTransformationUnavailableError,
    ReferenceFrame,
    require_frame_path,
    resolve_frame,
)
from michspc.spc.projection import forward as project_forward
from michspc.spc.projection import inverse as project_inverse
from michspc.spc.zones import Zone, grid_name

class WarningCode(Enum):
    """Machine-readable warning kinds, so the report can group them."""

    OUTSIDE_ZONE_EXTENT = "outside-zone-extent"
    EASTING_UNLIKE_SELECTED_ZONE = "easting-unlike-selected-zone"
    GEOID_UNAVAILABLE = "geoid-unavailable"
    """A point carried a usable elevation but the geoid grid does not cover it.

    Raised by michspc.job, not by this module - nothing here reads a file - but
    the code lives with the others because a job's warnings are one list and
    the audit CSV and the job record group them by this one enum.

    Without it a geoid miss is silent: the elevation and combined factors read
    N/A exactly as they do for a blank Z column, and the job record then lists
    the point under "blank elevation field", which is a false statement about a
    point whose elevation was recorded perfectly well.
    """

    VERTICAL_SHIFT_UNAVAILABLE = "vertical-shift-unavailable"
    """A vertical job's point carried a usable elevation, but the VERTCON grid
    pair does not cover its position, so the elevation was NOT converted.

    Raised by michspc.job, like GEOID_UNAVAILABLE above. The horizontal
    coordinates are unaffected and stand; the point's output elevation is
    left blank rather than filled with the unshifted source-datum height,
    because an unconverted height printed in a Z column labelled with the
    target datum is exactly the ordinary-looking wrong number this program
    exists to refuse. VERTCON 3.0's CONUS grid covers all of Michigan
    (docs/PLAN-vertical-datums.md section 2.2), so this is only reachable for
    a point already far outside the zone extents - but "unreachable in
    practice" is not a reason to pass a height through silently when it is
    reached.
    """

    VERTICAL_SIGMA_UNAVAILABLE = "vertical-sigma-unavailable"
    """A vertical job's point was shifted, but no one-sigma uncertainty can be
    stated for the shift: the VERTCON error model interpolates below zero at
    the point's position, and a negative number is not an uncertainty
    (docs/DESIGN.md #36).

    Raised by michspc.job, like the two codes above. THE SHIFT ITSELF IS VALID
    AND UNAFFECTED - it comes from the separate transformation grid - so the
    point's elevation IS converted and written; only the sigma cell reads N/A.

    This code exists because DESIGN.md #41 recorded that the disclosure layer
    (WP-V7) must not assume a warning already flags the missing sigma: the
    reading carries its reason, but a reason on a frozen record reaches no
    surface on its own. Raising it here makes every surface - the job record's
    WARNINGS section, the audit CSV's warnings column, and the GUI warnings
    field - inherit the disclosure through the one warning pipeline they all
    already read, rather than each growing its own special case.

    NOT raised for an identity transformation: an identity carries no sigma
    because no model ran, which is a statement the job record's METHOD text
    makes ("no shift is applied"), not a condition worth warning about.
    """

    GEOID_SWAP_UNAVAILABLE = "geoid-swap-unavailable"
    """A geoid-to-geoid job's point carried a usable elevation, but one of the
    two geoid tiles does not cover its position, so the elevation was NOT
    re-derived under the output geoid model.

    Raised by michspc.job, like the three codes above, and shaped exactly as
    VERTICAL_SHIFT_UNAVAILABLE is: the horizontal coordinates are unaffected
    and stand, and the point's output elevation is left blank rather than
    filled with the input-model height, because a height stated against one
    geoid model printed in a Z column whose job names another is the same
    ordinary-looking wrong number. Both shipped tiles cover all of Michigan
    with room to spare (docs/DESIGN.md section 3), so this is only reachable
    for a point already far outside the state - but "unreachable in practice"
    is not a reason to pass a height through silently when it is reached.
    """

    ELLIPSOID_HEIGHT_UNCONVERTIBLE = "ellipsoid-height-unconvertible"
    """A point's height was supplied as an ELLIPSOID height in one of the
    vertical modes, but the geoid tile does not cover its position, so
    H = h - N could not be computed and no orthometric height exists for it.

    Distinct from GEOID_UNAVAILABLE on purpose, and the distinction is the
    whole point of a separate code: GEOID_UNAVAILABLE costs a point its
    FACTORS and its Z still goes out, while this costs it the Z ITSELF. The
    vertical modes exist to produce a datum-tagged elevation; there is none
    here, and writing the unconverted ellipsoid height into a Z column those
    modes label with a vertical datum would be a height roughly 34 m wrong in
    Michigan wearing the right label - the ordinary-looking wrong number this
    project is built against.

    Horizontal mode raises GEOID_UNAVAILABLE for the same failure instead,
    because there the Z is the supplied height passed through unchanged (the
    owner's instruction) and only the factors are lost - which is exactly what
    that older code has always meant.
    """

    REALIZATION_OUTSIDE_PERIOD_OF_USE = "realization-outside-period-of-use"
    """A WGS 84 realization was stated for an observation dated outside that
    realization's period of use (docs/PLAN-wgs84.md decision D9): before NGA
    put it into use, or on or after the day NGA replaced it with the next
    realization (``frames.realization_period_of_use``).

    A WARNING, not a refusal: reprocessed data can legitimately carry a later
    realization than the one broadcast on the day, and software can keep
    labelling output with an older one, so the date and the realization
    disagreeing is a thing to look at, not proof of an error. It
    is also exactly what a mislabelled file looks like, which is why it is
    said at all. The conversion runs, as HTDP runs it, at the date stated.

    **Raised by michspc.job, and raised ONCE PER JOB** - carried on
    ``JobResult.job_warnings``, never on a point. It is a fact about two
    settings (the frame and the observation date), and one date covers every
    point in the file (plan D10), so a copy on every row would say one thing
    a thousand times and bury the per-point warnings that really do differ
    from row to row. Not raised for ITRF2014 or ITRF2020, which have no NGA
    period of use.
    """


@dataclass(frozen=True)
class ConversionWarning:
    """Something the surveyor should look at, which is not a reason to refuse."""

    code: WarningCode
    message: str


class HeightConvention(Enum):
    """Which height HTDP was handed for a point's frame transformation (plan D6).

    HTDP moves a 3-D position, so it needs an ellipsoid height, and a PNEZD Z
    column does not always hold one. The three cases, each recorded per point
    so the job record can state which a job used:

    * ``ELLIPSOID`` - the Z is an ellipsoid height, part of the 3-D position,
      and it is transformed WITH the position: the height out is the output
      frame's. Passing a WGS 84 h through into a NAD 83 job unchanged would be
      about a metre wrong under the right label.
    * ``ORTHOMETRIC`` - the Z is an elevation, which is a height above the
      geoid and belongs to no frame, so it passes UNCHANGED. HTDP is handed H
      in place of h. Measured cost (DESIGN.md #70): the horizontal result
      moves 1.2e-5 m per 40 m of height error, and |N| is about 35 m in
      Michigan, so at most 0.012 mm.
    * ``NOT_RECORDED`` - the Z is blank or exactly zero, the reader's "not
      recorded" (``pnezd``), so there is no height at all: HTDP is handed
      h = 0 and the Z stays blank. Measured cost: at 600 m of real height,
      Michigan's highest ground, at most 0.18 mm north and 0.13 mm east.

    These are disclosed facts, not caveats (the owner's no-disclaimer rule,
    DESIGN.md #50).
    """

    ELLIPSOID = "ellipsoid height, transformed with the position"
    ORTHOMETRIC = "orthometric height, used in place of the ellipsoid height"
    NOT_RECORDED = "no height recorded, transformed at an ellipsoid height of 0 m"


@dataclass(frozen=True)
class TransformHeight:
    """The height handed to a frame transformation, and what kind it is.

    One record rather than a float and a flag beside it, because the two are
    one fact: a number means nothing to HTDP until it says whether it is an
    ellipsoid height, and "not recorded" has no number at all - which is
    exactly what ``value_m=None`` states. ``__post_init__`` refuses every
    other pairing, so a blank Z cannot be handed in as 0.0 and a real height
    cannot be dropped silently.
    """

    convention: HeightConvention
    value_m: float | None
    """Metres. None exactly when the convention is NOT_RECORDED."""

    def __post_init__(self) -> None:
        # if/raise, never assert: the suite and the shipped program run
        # under -O, which strips asserts (docs/DESIGN.md section 7).
        if not isinstance(self.convention, HeightConvention):
            raise TypeError(
                f"TransformHeight.convention must be a HeightConvention "
                f"stating what the height is; got "
                f"{type(self.convention).__name__} ({self.convention!r})."
            )
        if self.convention is HeightConvention.NOT_RECORDED:
            if self.value_m is not None:
                raise ValueError(
                    f"A TransformHeight that states no height was recorded "
                    f"carries value_m={self.value_m!r}. A height that was not "
                    f"recorded has no value; pass value_m=None, and the "
                    f"transformation is run at h = 0 by the convention itself."
                )
            return
        value = self.value_m
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(
                f"A TransformHeight of convention {self.convention.name} must "
                f"carry a finite height in metres; got {value!r}. A point "
                f"with no height is stated as HeightConvention.NOT_RECORDED, "
                f"never as a number nobody measured."
            )

    @property
    def height_for_transform_m(self) -> float:
        """The ellipsoid height HTDP is handed: the value, or 0.0 when none was recorded."""
        if self.convention is HeightConvention.NOT_RECORDED:
            return 0.0
        return float(self.value_m)


@dataclass(frozen=True)
class ExternalPosition:
    """A geodetic position in the job's WGS 84 or ITRF frame, tagged with it.

    The position on the far side of the frame transformation from the NAD 83
    pivot (plan D5): the INPUT as given on a job that reads this frame, or
    HTDP's output on a job that writes it. Always in a time-dependent frame -
    the only frames a registered non-identity path reaches - and at the job's
    observation epoch, which the ``PointConversion`` carrying this record
    states beside it.
    """

    frame: ReferenceFrame
    """The registry's own record for the frame (never a caller's copy)."""

    latitude: float
    longitude: float
    """Decimal degrees, longitude NEGATIVE WEST."""

    ellipsoid_height: float | None
    """Metres above ``frame``'s ellipsoid as HTDP uses it - present only when
    the point's height was an ELLIPSOID height and so was transformed with
    the position. None otherwise: an elevation is in no frame, and a blank Z
    has no height to state."""

    def __post_init__(self) -> None:
        if not isinstance(self.frame, ReferenceFrame):
            raise TypeError(
                f"ExternalPosition.frame must be a michspc.spc.frames."
                f"ReferenceFrame; got {type(self.frame).__name__} "
                f"({self.frame!r}). A position without its frame is the "
                f"metre-scale ambiguity this record exists to remove."
            )
        if not self.frame.is_time_dependent:
            raise ValueError(
                f"ExternalPosition.frame is {self.frame.code}, a plate-fixed "
                f"frame. The external position is the WGS 84 or ITRF end of a "
                f"frame transformation; a plate-fixed position is a pivot, "
                f"and is carried as one."
            )
        for name in ("latitude", "longitude"):
            value = getattr(self, name)
            if not isinstance(value, float) or not math.isfinite(value):
                raise ValueError(
                    f"ExternalPosition.{name} must be a finite float in "
                    f"degrees; got {value!r}."
                )
        height = self.ellipsoid_height
        if height is not None and (
            not isinstance(height, float) or not math.isfinite(height)
        ):
            raise ValueError(
                f"ExternalPosition.ellipsoid_height must be a finite float in "
                f"metres, or None; got {height!r}."
            )


@dataclass(frozen=True)
class PointConversion:
    """The full record of one point's conversion. Immutable.

    Every zone-derived field - the two zones, the four convergence and scale
    quantities, and the grid coordinates - is None on a record built by
    ``geodetic_position`` or ``geodetic_to_geodetic``: those conversions
    involve no zone anywhere, and this program does not fabricate one. The
    geodetic pivot is the one thing such a record always carries.

    The five frame-transformation fields at the end are None together on
    every same-frame conversion - defaulted, so every construction site that
    predates them, and every byte of every same-frame output, is unchanged -
    and present together on a conversion that ran HTDP. ``__post_init__``
    holds them to each other and to the pivot.
    """

    source_zone: Zone | None
    target_zone: Zone | None

    frame: ReferenceFrame
    """The reference frame this position is expressed in.

    A geodetic position is meaningless without it (docs/DESIGN.md section 4:
    the pivot of every conversion is "a geodetic position tagged with its
    reference frame"). Carried on the record so the job record can state which
    frame the numbers were interpreted as, rather than leaving a reader to
    assume NAD 83 - the assumption that is a one-to-two metre error when it is
    wrong.

    This is the frame of the PIVOT, ``latitude`` and ``longitude`` below. On a
    transformed conversion that is always NAD83(2011) (plan D5), and the WGS 84
    or ITRF frame is ``external_position.frame``.
    """

    source_northing: float | None
    source_easting: float | None
    """Meters, in the source zone. None on a no-zone record."""

    latitude: float
    longitude: float
    """The geodetic pivot. Decimal degrees, longitude negative west."""

    target_northing: float | None
    target_easting: float | None
    """Meters, in the target zone. None on a no-zone record."""

    source_convergence: float | None
    source_scale_factor: float | None
    target_convergence: float | None
    target_scale_factor: float | None

    warnings: tuple[ConversionWarning, ...] = field(default_factory=tuple)

    external_position: ExternalPosition | None = None
    """The WGS 84 or ITRF position, on a transformed conversion; else None."""

    frame_transformation: FrameTransformation | None = None
    """The registry's record of the path applied, on a transformed conversion."""

    htdp_result: htdp.HtdpResult | None = None
    """What HTDP returned and the facts it states - the velocity applied, the
    Helmert's epoch, the clock span - on a transformed conversion."""

    observation_epoch: htdp.ObservationEpoch | None = None
    """The epoch of the external position, on a transformed conversion."""

    transform_height: TransformHeight | None = None
    """The height HTDP was handed and its convention (plan D6)."""

    def __post_init__(self) -> None:
        # if/raise, never assert: the suite and the shipped program run
        # under -O, which strips asserts (docs/DESIGN.md section 7).
        evidence = {
            "external_position": self.external_position,
            "frame_transformation": self.frame_transformation,
            "htdp_result": self.htdp_result,
            "observation_epoch": self.observation_epoch,
            "transform_height": self.transform_height,
        }
        present = [name for name, value in evidence.items() if value is not None]
        if not present:
            return
        if len(present) != len(evidence):
            missing = [name for name in evidence if name not in present]
            raise ValueError(
                f"A PointConversion carries {', '.join(present)} but not "
                f"{', '.join(missing)}. A frame transformation's evidence is "
                f"one fact: the position on the far side of the path, the "
                f"path, what HTDP returned, the epoch and the height it was "
                f"handed are present together or not at all - a record "
                f"carrying half of them would let an output state a "
                f"transformation it cannot describe."
            )
        _require_consistent_transformation_evidence(self)

    @property
    def is_transformed(self) -> bool:
        """True when a frame transformation ran for this point."""
        return self.frame_transformation is not None

    @property
    def target_frame_ellipsoid_height(self) -> float | None:
        """The ellipsoid height in the path's TARGET frame, when one was transformed.

        HTDP's own output height. On a job that writes the time-dependent
        frame it is that frame's h; on one that writes NAD83(2011) it is the
        NAD 83 h. None unless the height was an ELLIPSOID height.
        """
        if not self.is_transformed or (
            self.transform_height.convention is not HeightConvention.ELLIPSOID
        ):
            return None
        return self.htdp_result.ellipsoid_height

    @property
    def pivot_ellipsoid_height(self) -> float | None:
        """The ellipsoid height in NAD83(2011) - the pivot's - when one was transformed.

        What ``H = h - N`` must use (plan D6): every geoid model this program
        carries publishes N against NAD 83(2011). Derived, never stored: on a
        path INTO NAD 83 it is HTDP's output height, on a path OUT of it the
        height that was handed in.
        """
        if not self.is_transformed or (
            self.transform_height.convention is not HeightConvention.ELLIPSOID
        ):
            return None
        if self.frame_transformation.target.is_time_dependent:
            return self.transform_height.value_m
        return self.htdp_result.ellipsoid_height


def _require_consistent_transformation_evidence(record: PointConversion) -> None:
    """Hold a transformed record's five fields to each other and to its pivot.

    Each stored copy of a number must equal the number HTDP produced or was
    handed, so a wiring defect - the pivot taken from the wrong side, the
    epoch of one job carried on another's points - cannot be constructed.
    """
    path = record.frame_transformation
    result = record.htdp_result
    external = record.external_position
    height = record.transform_height
    epoch = record.observation_epoch
    for name, value, kind in (
        ("frame_transformation", path, FrameTransformation),
        ("htdp_result", result, htdp.HtdpResult),
        ("external_position", external, ExternalPosition),
        ("transform_height", height, TransformHeight),
        ("observation_epoch", epoch, htdp.ObservationEpoch),
    ):
        if not isinstance(value, kind):
            raise TypeError(
                f"PointConversion.{name} must be a {kind.__name__}; got "
                f"{type(value).__name__} ({value!r})."
            )
    if path.is_identity:
        raise ValueError(
            f"PointConversion states a frame transformation, but the record "
            f"is the identity {path}. An identity moves nothing, so a "
            f"transformed record built on one would claim arithmetic that "
            f"never ran."
        )
    forward = path.source.is_time_dependent
    global_end = path.source if forward else path.target
    nad83_end = path.target if forward else path.source
    problems = []
    if external.frame.code != global_end.code:
        problems.append(
            f"the external position is in {external.frame.code}, but the "
            f"path's time-dependent end is {global_end.code}"
        )
    if record.frame.code != nad83_end.code:
        problems.append(
            f"the pivot is tagged {record.frame.code}, but the path's "
            f"plate-fixed end is {nad83_end.code}"
        )
    if (result.source_frame, result.target_frame) != (
        path.source.htdp_frame,
        path.target.htdp_frame,
    ):
        problems.append(
            f"HTDP ran {result.source_frame.name} -> "
            f"{result.target_frame.name}, which is not the path {path}"
        )
    observed = result.source_epoch if forward else result.target_epoch
    if observed != epoch:
        problems.append(
            f"HTDP ran at {observed}, but the record states epoch {epoch}"
        )
    output = (record.latitude, record.longitude) if forward else (
        external.latitude,
        external.longitude,
    )
    if output != (result.latitude, result.longitude):
        problems.append(
            f"the {'pivot' if forward else 'external position'} is not "
            f"HTDP's output position"
        )
    if height.convention is HeightConvention.ELLIPSOID:
        expected = height.value_m if forward else result.ellipsoid_height
        if external.ellipsoid_height != expected:
            problems.append(
                f"the external ellipsoid height {external.ellipsoid_height!r} "
                f"is not the height {'handed to' if forward else 'returned by'} "
                f"HTDP ({expected!r})"
            )
    elif external.ellipsoid_height is not None:
        problems.append(
            f"the external position states an ellipsoid height, but the "
            f"height handed to HTDP was {height.convention.name}, which is "
            f"not transformed"
        )
    if problems:
        raise ValueError(
            "A transformed PointConversion disagrees with itself: "
            + "; ".join(problems)
            + ". Every stored number must be the one HTDP produced or was "
            "handed."
        )


def require_an_applicable_path(path: FrameTransformation) -> FrameTransformation:
    """The single point where a registered frame path is applied or refused.

    Successor to the WGS 84 build's W2 guard, ``require_a_connected_path``,
    which refused every non-identity path while nothing applied one
    (docs/PLAN-wgs84.md, work package W2). Since work package W3 this module
    applies HTDP v3.6.0's paths (``_apply_frame_path``), so what remains to
    refuse is a path whose METHOD has no arithmetic here: a record the
    registry might carry one day - a NAD83(2011) <-> NATRF2022 bridge, say -
    must not reach the pipeline and be treated as an identity because nothing
    knew how to run it. That is a SILENT PASS-THROUGH, the one failure this
    program exists to refuse.

    Called at every site that asks the registry for a path - ``convert_point``,
    ``project_point``, ``zone_to_geodetic``, ``geodetic_to_geodetic``,
    ``geodetic_position``, ``job.run``'s settings gate, and the interface's
    ``frames_have_a_path`` - so that the interface and the gate cannot disagree
    about which paths run.

    Fail-closed: a non-record (a gate that returned nothing) is a defect, not
    a frame condition, and is a ``TypeError``; a registered record whose method
    this module does not apply is ``FrameTransformationUnavailableError``,
    which every caller already catches as ``FrameMismatchError``.
    """
    if not isinstance(path, FrameTransformation):
        raise TypeError(
            f"The frame gate returned {type(path).__name__} ({path!r}) where a "
            f"michspc.spc.frames.FrameTransformation was required. A frame "
            f"path that cannot say what it does to a position is never treated "
            f"as an identity."
        )
    if path.is_identity:
        return path
    if path.method is FrameTransformationMethod.HTDP_V3_6_0:
        return path
    raise FrameTransformationUnavailableError(
        f"Cannot convert from {path.source.code} to {path.target.code}: the "
        f"registered transformation between them states the method "
        f"{path.applied_method.value!r}, and this program's conversion "
        f"pipeline has no arithmetic for it. Converting without it would pass "
        f"the {path.source.code} position through unchanged under a "
        f"{path.target.code} label, with nothing in the numbers to show it."
    )


def _require_transform_arguments(
    path: FrameTransformation,
    epoch: object,
    height: object,
    function: str,
) -> None:
    """Required when the path runs HTDP, refused when it does not; never defaulted.

    An observation epoch or a transform height handed to a same-frame
    conversion answers a question that conversion never asks, and accepting it
    silently would let a caller believe the date was used: the stray-field
    class of the 0.7.0 closing gate. A missing epoch on a time-dependent frame
    is a refusal naming the frame, because a WGS 84 or ITRF position means
    nothing until the date it was observed is stated - Michigan moves about
    17 mm a year against NAD 83 (review/wgs84-w0/RECON.md section 3).
    """
    if path.is_identity:
        stray = [
            name
            for name, value in (("epoch", epoch), ("height", height))
            if value is not None
        ]
        if stray:
            raise ValueError(
                f"{function} was given {' and '.join(stray)} for a conversion "
                f"within {path.source.code}, where no frame transformation "
                f"runs. An observation epoch and a transform height exist "
                f"only for HTDP's path between NAD83(2011) and a WGS 84 or "
                f"ITRF frame; stated here they would answer a question this "
                f"conversion never asks. Pass None."
            )
        return
    global_end = path.source if path.source.is_time_dependent else path.target
    if epoch is None:
        raise ValueError(
            f"{function} needs the observation epoch of the {global_end.code} "
            f"position: {global_end.code} is a time-dependent frame, in which "
            f"a Michigan point moves about 17 mm a year against "
            f"{NAD83_2011.code}, so the position means nothing until the date "
            f"it was observed is stated. It has no default. Pass "
            f"epoch=htdp.ObservationEpoch(<the date observed>)."
        )
    if not isinstance(epoch, htdp.ObservationEpoch):
        raise TypeError(
            f"{function}'s epoch must be a michspc.spc.htdp.ObservationEpoch "
            f"built from the calendar date the {global_end.code} position was "
            f"observed; got {type(epoch).__name__} ({epoch!r})."
        )
    if height is None:
        raise ValueError(
            f"{function} needs the height handed to HTDP for the "
            f"{path.source.code} -> {path.target.code} transformation, with "
            f"its convention - an ellipsoid height, an elevation used in its "
            f"place, or none recorded (convert.TransformHeight). It has no "
            f"default: which one it is decides whether the height is "
            f"transformed with the position."
        )
    if not isinstance(height, TransformHeight):
        raise TypeError(
            f"{function}'s height must be a michspc.spc.convert."
            f"TransformHeight stating the height and its convention; got "
            f"{type(height).__name__} ({height!r})."
        )


def _apply_frame_path(
    path: FrameTransformation,
    latitude: float,
    longitude: float,
    epoch: htdp.ObservationEpoch | None,
    height: TransformHeight | None,
) -> tuple[float, float, dict]:
    """Run the registered path once: ``(pivot latitude, pivot longitude, evidence)``.

    ``latitude`` and ``longitude`` are the position at the path's SOURCE. An
    identity returns them unchanged with no evidence - the same-frame
    conversion, bit for bit. An HTDP path calls ``htdp`` exactly once, in the
    direction the path runs, and the pivot is whichever end is NAD83(2011)
    (plan D5).

    **The HTDP frames come from the registry's record, never from a caller's**
    (interim gate 1, finding L4): ``path`` is the record ``require_frame_path``
    returned, whose two ends are the registry's own frame records, so
    ``htdp_frame`` and ``is_time_dependent`` are read where the registry
    stated them.
    """
    if path.is_identity:
        return latitude, longitude, {}
    in_frame = height.height_for_transform_m
    transformed_height = height.convention is HeightConvention.ELLIPSOID
    if path.source.is_time_dependent:
        result = htdp.to_nad83(
            latitude, longitude, in_frame, path.source.htdp_frame, epoch
        )
        external = ExternalPosition(
            frame=path.source,
            latitude=float(latitude),
            longitude=float(longitude),
            ellipsoid_height=(
                float(height.value_m) if transformed_height else None
            ),
        )
        pivot = (result.latitude, result.longitude)
    else:
        result = htdp.from_nad83(
            latitude, longitude, in_frame, path.target.htdp_frame, epoch
        )
        external = ExternalPosition(
            frame=path.target,
            latitude=result.latitude,
            longitude=result.longitude,
            ellipsoid_height=(
                result.ellipsoid_height if transformed_height else None
            ),
        )
        pivot = (latitude, longitude)
    evidence = dict(
        external_position=external,
        frame_transformation=path,
        htdp_result=result,
        observation_epoch=epoch,
        transform_height=height,
    )
    return pivot[0], pivot[1], evidence


def _require_zone(zone: object, label: str, function: str) -> Zone:
    """Interim gate 1, finding I2: a non-Zone where a Zone belongs is a TypeError.

    It used to surface as an ``AttributeError`` several lines in, on
    ``.frame`` - which walks straight through every ``except
    FrameMismatchError`` a caller writes. A frame record passed where its zone
    was meant is the likeliest version, and it reads plausibly.
    """
    if not isinstance(zone, Zone):
        raise TypeError(
            f"{function} needs a michspc.spc.zones.Zone as its {label}; got "
            f"{type(zone).__name__} ({zone!r}). A reference frame, a vertical "
            f"datum or a unit is not a zone, and this conversion needs the "
            f"zone's projection constants. Pass a record from "
            f"michspc.spc.zones."
        )
    return zone


def _check_extent(zone: Zone, latitude: float, longitude: float, context: str):
    """Warn when a point falls outside the zone's intended area.

    Never a refusal. A project legitimately straddling a zone boundary must
    still convert (docs/DESIGN.md amendment #1).
    """
    outside_latitude = not (zone.lat_min <= latitude <= zone.lat_max)
    outside_longitude = not (zone.lon_min <= longitude <= zone.lon_max)
    if not (outside_latitude or outside_longitude):
        return None

    return ConversionWarning(
        code=WarningCode.OUTSIDE_ZONE_EXTENT,
        message=(
            f"{context}: {latitude:.6f}, {longitude:.6f} lies outside the area "
            f"{zone.name} covers ({zone.lat_min:.1f} to {zone.lat_max:.1f} N, "
            f"{zone.lon_min:.1f} to {zone.lon_max:.1f} E). The coordinate is "
            f"computed correctly, but distortion grows with distance from the "
            f"zone and another zone may suit this point better."
        ),
    )


def easting_looks_wrong_for_zone(easting: float, zone: Zone) -> bool:
    """Does this easting plausibly belong to this zone at all?

    Michigan's three SPCS 83 zones have false eastings 2,000,000 m apart
    precisely so a coordinate reveals its own zone (manual PDF p. 18: "Selecting
    different grid origins ... so the coordinate user could determine the zone
    from the magnitude of the coordinate"). Selecting the wrong source zone is
    the most likely real-world mistake with this program, and it is cheap to
    notice.

    **The range is the zone's own** (``Zone.easting_range_m``), because it is a
    property of the coordinate system and not of this function. SPCS 83 derives
    it, +/- 400 km about the false easting; SPCS2022 does not have to, because
    NGS publishes each zone's easting bounds outright, projected outward from
    the zone polygon. The registry record carries the source for each.

    A zone whose range is ``None`` has no usable bounds recorded, and this
    returns False for it rather than inventing a threshold. No zone in the
    registry is in that state today; the branch exists because the next
    authority to publish a zone may not publish bounds for it, and a missing
    range must switch the warning off rather than produce a wrong one.

    Takes meters. Never a refusal: it raises a warning, never blocks a job
    (docs/DESIGN.md amendment #1).
    """
    bounds = zone.easting_range_m
    if bounds is None:
        return False
    lowest, highest = bounds
    return not (lowest <= easting <= highest)


def to_geodetic(
    northing: float,
    easting: float,
    zone: Zone,
    context: str = "point",
) -> tuple[float, float, float, float, tuple[ConversionWarning, ...]]:
    """Grid to geodetic.

    Returns (latitude, longitude, convergence, scale_factor, warnings).
    """
    position = project_inverse(northing, easting, zone)

    return (
        position.latitude,
        position.longitude,
        position.convergence,
        position.scale_factor,
        (),
    )


def from_geodetic(
    latitude: float,
    longitude: float,
    zone: Zone,
    context: str = "point",
) -> tuple[float, float, float, float, tuple[ConversionWarning, ...]]:
    """Geodetic to grid.

    Returns (northing, easting, convergence, scale_factor, warnings).
    """
    point = project_forward(latitude, longitude, zone)

    warnings: list[ConversionWarning] = []
    extent_warning = _check_extent(
        zone, latitude, longitude, f"{context} (into {zone.abbrev})"
    )
    if extent_warning:
        warnings.append(extent_warning)

    return (
        point.northing,
        point.easting,
        point.convergence,
        point.scale_factor,
        tuple(warnings),
    )


def convert_point(
    northing: float,
    easting: float,
    source_zone: Zone,
    target_zone: Zone,
    context: str = "point",
) -> PointConversion:
    """Convert one point from one zone to another.

    Both zones must be in the same reference frame; crossing frames is refused
    (michspc.spc.frames). Linear values are meters.

    A zone is the only thing this function accepts; its constants are derived
    from it here. Callers used to be able to hand in precomputed
    ``LambertConstants`` for speed, which made it possible to name one zone and
    supply another's constants - a 4,231 km error with no refusal and no warning
    (docs/DESIGN.md amendment #11 finding 5). ``constants_for`` is cached, so
    the speed that seam bought is now free.

    **Zone to zone never crosses a frame transformation.** The registry
    carries non-identity paths - NGS HTDP v3.6.0 between NAD83(2011) and the
    WGS 84 and ITRF frames (DESIGN.md #70) - but no State Plane zone is
    defined on a WGS 84 or ITRF frame (plan decision D4), so a zone pair that
    reaches one is not a pair of this program's zones, and it is refused
    rather than run without the observation epoch HTDP would need. Every zone
    in the registry sits on NAD83(2011) or NATRF2022; this refusal is what
    keeps that from being an assumption.
    """
    source_zone = _require_zone(source_zone, "source zone", "convert_point")
    target_zone = _require_zone(target_zone, "target zone", "convert_point")
    path = require_an_applicable_path(
        require_frame_path(source_zone.frame, target_zone.frame)
    )
    if not path.is_identity:
        raise FrameTransformationUnavailableError(
            f"Cannot convert from {source_zone.name} ({path.source.code}) to "
            f"{target_zone.name} ({path.target.code}) zone to zone: the "
            f"frames are joined only by a frame transformation "
            f"({path.applied_method.value}), and no State Plane zone is "
            f"defined on a WGS 84 or ITRF frame (docs/PLAN-wgs84.md decision "
            f"D4) - so one of these is not a zone this program carries. A "
            f"WGS 84 or ITRF position enters and leaves this program as "
            f"latitude and longitude, converted to or from "
            f"{NAD83_2011.code} with its observation date."
        )

    latitude, longitude, source_convergence, source_scale, warnings_in = to_geodetic(
        northing, easting, source_zone, context
    )

    (
        target_northing,
        target_easting,
        target_convergence,
        target_scale,
        warnings_out,
    ) = from_geodetic(latitude, longitude, target_zone, context)

    return PointConversion(
        source_zone=source_zone,
        target_zone=target_zone,
        frame=source_zone.frame,
        source_northing=northing,
        source_easting=easting,
        latitude=latitude,
        longitude=longitude,
        target_northing=target_northing,
        target_easting=target_easting,
        source_convergence=source_convergence,
        source_scale_factor=source_scale,
        target_convergence=target_convergence,
        target_scale_factor=target_scale,
        warnings=warnings_in + warnings_out,
    )


def project_point(
    latitude: float,
    longitude: float,
    source_frame: ReferenceFrame,
    target_zone: Zone,
    context: str = "point",
    *,
    epoch: htdp.ObservationEpoch | None = None,
    height: TransformHeight | None = None,
) -> PointConversion:
    """Convert a geodetic position into a zone's grid coordinates.

    The geodetic-input case. No inverse step is performed, so the source zone is
    the target zone.

    ``source_frame`` is the reference frame the latitude and longitude are
    expressed in, and it is **required with no default**. A latitude and
    longitude alone do not say which frame they belong to, and NAD 83 and
    NATRF2022 differ by one to two metres over North America; projecting a
    NATRF2022 position with the SPCS 83 constants yields a coordinate that looks
    entirely ordinary and is wrong by more than the width of a road. The
    equivalent zone-to-zone refusal has existed since the beginning
    (``convert_point``); this closes the geodetic-input door on the same rule.
    See docs/DESIGN.md sections 4 and 6, and amendment #11 finding 1.

    Refuses with ``FrameMismatchError`` if no registered path joins the
    position's frame to the target zone's frame.

    **A WGS 84 or ITRF position is transformed first** (plan W3): when the
    registered path is HTDP's - one of the five time-dependent frames into an
    SPCS 83 zone - the position goes to NAD83(2011) at 2010.0 by
    ``htdp.to_nad83`` and that pivot is projected. ``epoch`` (the date the
    position was observed) and ``height`` (what HTDP is handed, and its
    convention) are then REQUIRED, keyword-only, and refused on a same-frame
    projection. The result's ``latitude`` and ``longitude`` are the NAD 83
    pivot; the position as given is ``external_position``.
    """
    if not isinstance(source_frame, ReferenceFrame):
        raise TypeError(
            f"project_point needs the reference frame the geodetic position is "
            f"expressed in, as its third argument; got "
            f"{type(source_frame).__name__} ({source_frame!r}). A latitude and "
            f"longitude do not carry their own frame, and the frame decides "
            f"whether the resulting {grid_name(target_zone)} coordinate is "
            f"right or is one "
            f"to two metres out. Pass michspc.spc.frames.NAD83_2011 for an "
            f"NAD 83 position."
        )

    target_zone = _require_zone(target_zone, "target zone", "project_point")

    # The site a WGS 84 or ITRF position reaches first - WGS84(G2296) into an
    # SPCS 83 zone is a REGISTERED path - and projecting its latitude and
    # longitude unchanged would put a WGS 84 position on the NAD 83 grid,
    # about 1.3 m out in Michigan. So the path is applied, once, before the
    # projection: the pivot projected is always in the zone's own frame.
    path = require_an_applicable_path(
        require_frame_path(source_frame, target_zone.frame)
    )
    _require_transform_arguments(path, epoch, height, "project_point")
    pivot_latitude, pivot_longitude, evidence = _apply_frame_path(
        path, latitude, longitude, epoch, height
    )

    (
        northing,
        easting,
        convergence,
        scale,
        warnings,
    ) = from_geodetic(pivot_latitude, pivot_longitude, target_zone, context)

    return PointConversion(
        source_zone=target_zone,
        target_zone=target_zone,
        # The registry's own record, which the frame gate has just required
        # the caller's to equal (frames._canonical): every reader downstream
        # reads the facts the gate checked, never a caller's copy of them.
        # The TARGET end, because the pivot is in the zone's frame - on an
        # identity the two ends are one record, so a same-frame projection
        # carries exactly the record it always did.
        frame=path.target,
        source_northing=northing,
        source_easting=easting,
        latitude=pivot_latitude,
        longitude=pivot_longitude,
        target_northing=northing,
        target_easting=easting,
        source_convergence=convergence,
        source_scale_factor=scale,
        target_convergence=convergence,
        target_scale_factor=scale,
        warnings=warnings,
        **evidence,
    )


def zone_to_geodetic(
    northing: float,
    easting: float,
    source_zone: Zone,
    target_frame: ReferenceFrame,
    context: str = "point",
    *,
    epoch: htdp.ObservationEpoch | None = None,
    height: TransformHeight | None = None,
) -> PointConversion:
    """A zone's grid coordinates out to a geodetic position in ``target_frame``.

    The State Plane to geodetic case. Within one frame it is exactly what
    ``job.run`` has always done for that direction - ``convert_point`` with
    the source zone at both ends, returned unchanged, bit for bit - so every
    same-frame job is untouched. When ``target_frame`` is one of the WGS 84 or
    ITRF frames, the inverse gives the NAD83(2011) pivot and ``htdp.from_nad83``
    carries it to that frame at ``epoch``: the position the job writes is then
    ``external_position``, and ``latitude``/``longitude`` stay the pivot every
    grid lookup reads (plan D5).

    ``epoch`` and ``height`` are required on that path and refused on a
    same-frame one, as ``project_point`` requires them.
    """
    source_zone = _require_zone(source_zone, "source zone", "zone_to_geodetic")
    if not isinstance(target_frame, ReferenceFrame):
        raise TypeError(
            f"zone_to_geodetic needs the reference frame the geodetic position "
            f"is wanted in, as its fourth argument; got "
            f"{type(target_frame).__name__} ({target_frame!r}). Pass "
            f"michspc.spc.frames.NAD83_2011, or the zone's own .frame."
        )
    path = require_an_applicable_path(
        require_frame_path(source_zone.frame, target_frame)
    )
    _require_transform_arguments(path, epoch, height, "zone_to_geodetic")
    base = convert_point(northing, easting, source_zone, source_zone, context)
    if path.is_identity:
        return base
    pivot_latitude, pivot_longitude, evidence = _apply_frame_path(
        path, base.latitude, base.longitude, epoch, height
    )
    return replace(
        base,
        frame=path.source,
        latitude=pivot_latitude,
        longitude=pivot_longitude,
        **evidence,
    )


def geodetic_to_geodetic(
    latitude: float,
    longitude: float,
    source_frame: ReferenceFrame,
    target_frame: ReferenceFrame,
    context: str = "point",
    *,
    epoch: htdp.ObservationEpoch | None = None,
    height: TransformHeight | None = None,
) -> PointConversion:
    """A geodetic position from one frame to another, across a registered HTDP path.

    Plan decision D7: WGS 84 or ITRF positions in and NAD83(2011) positions
    out, or the reverse - HTDP's own core use, and the conversion most people
    asking for "WGS 84" need. No zone takes part, so every zone-derived field
    is None, as on ``geodetic_position``. The pivot (``latitude``,
    ``longitude``) is the NAD 83 end, input or output; ``external_position``
    is the WGS 84 or ITRF end.

    **Only across a registered NON-identity path.** A position "converted" to
    its own frame is not a conversion, and is refused rather than returned
    unchanged as though something ran. Every other unavailable pair - the
    bare WGS 84 label, one global frame against another (D4), anything against
    NATRF2022 (D3) - refuses with ``frames``' own pair-specific message.
    ``epoch`` and ``height`` are always required here, because every path this
    function accepts runs HTDP.
    """
    for label, frame in (("source", source_frame), ("target", target_frame)):
        if not isinstance(frame, ReferenceFrame):
            raise TypeError(
                f"geodetic_to_geodetic needs a michspc.spc.frames."
                f"ReferenceFrame as its {label} frame; got "
                f"{type(frame).__name__} ({frame!r}). A latitude and "
                f"longitude do not carry their own frame."
            )
    path = require_an_applicable_path(require_frame_path(source_frame, target_frame))
    if path.is_identity:
        raise FrameTransformationUnavailableError(
            f"Cannot convert a {path.source.code} geodetic position to "
            f"{path.target.code} geodetic: it is the same frame at both ends, "
            f"so nothing would be converted, and returning the position "
            f"unchanged as though a conversion ran would be a record of work "
            f"that never happened. Geodetic to geodetic exists only across a "
            f"frame transformation - a WGS 84 or ITRF frame to or from "
            f"{NAD83_2011.code} (docs/PLAN-wgs84.md decision D7)."
        )
    _require_transform_arguments(path, epoch, height, "geodetic_to_geodetic")
    pivot_latitude, pivot_longitude, evidence = _apply_frame_path(
        path, latitude, longitude, epoch, height
    )
    nad83_end = path.target if path.source.is_time_dependent else path.source
    return PointConversion(
        source_zone=None,
        target_zone=None,
        frame=nad83_end,
        source_northing=None,
        source_easting=None,
        latitude=pivot_latitude,
        longitude=pivot_longitude,
        target_northing=None,
        target_easting=None,
        source_convergence=None,
        source_scale_factor=None,
        target_convergence=None,
        target_scale_factor=None,
        warnings=(),
        **evidence,
    )


def pivot_path(source_frame: ReferenceFrame) -> FrameTransformation:
    """The path from a geodetic position's own frame to the frame of its pivot.

    For the vertical-only job on geodetic input (plan decision D8), which
    converts no position and yet needs one: every grid it reads - the geoid
    models, VERTCON - is published against NAD 83. So:

    * a plate-fixed frame's pivot is the position itself - its IDENTITY
      record, which also refuses a frame the registry does not carry;
    * a time-dependent frame's pivot is the position carried to NAD83(2011)
      by its registered HTDP path. The registry deliberately holds NO
      identity for these frames (plan W2), and none is added: a position
      left in WGS 84 and looked up in a NAD 83 grid is the error this exists
      to prevent;
    * the bare WGS 84 label is refused by name, by ``require_frame_path``.

    Asked of the REGISTRY's record (``resolve_frame``), never of the caller's,
    so a disagreeing copy is refused before its epoch kind is read (interim
    gate 1, finding L4). One statement, read by ``geodetic_position`` and by
    ``job.run``'s settings gate, so the two gates on this direction (interim
    gate 1, finding L5) cannot choose different paths.
    """
    frame = resolve_frame(source_frame)
    if frame.is_time_dependent:
        return require_an_applicable_path(require_frame_path(frame, NAD83_2011))
    return require_an_applicable_path(require_frame_path(frame, frame))


def geodetic_position(
    latitude: float,
    longitude: float,
    source_frame: ReferenceFrame,
    context: str = "point",
    *,
    epoch: htdp.ObservationEpoch | None = None,
    height: TransformHeight | None = None,
) -> PointConversion:
    """A geodetic position with no zone on either end.

    Exists for the vertical-only job whose input is geodetic
    (``michspc.job``, ``Direction.VERTICAL_ONLY`` with ``source_zone=None``):
    the vertical shift and the geoid lookup need the pivot latitude and
    longitude, and nothing in that job involves a State Plane zone. Every
    zone-derived field is None - never a fabricated zone, whose scale factor
    and convergence would be plausible numbers describing a projection nobody
    chose. ``factors_at`` accepts the None scale factor and reports the grid
    scale and combined factors as absent while still computing the elevation
    factor, which needs no zone.

    ``source_frame`` is required with no default, exactly as
    ``project_point`` requires it and for the same reason: a latitude and
    longitude alone do not say which frame they belong to, and the NGS grids
    this position is looked up in are published against NAD 83. No projection
    runs here, so no extent warning can be raised - there is no zone to have
    an extent.

    **Its own frame gate** (interim gate 1 of the WGS 84 build, finding L5).
    This function used to ask no frame question at all, so a vertical-only job
    had one gate, at its settings, where every other direction has two: with
    the settings branch removed, a WGS84(G2296) ellipsoid-height job wrote
    NAVD 88 198.085 m, its WGS 84 h taken as NAD 83's - about 1.07 m low. Now
    the position goes through ``pivot_path``: a plate-fixed frame's identity,
    or a time-dependent frame's HTDP path to NAD83(2011) (plan D8), with the
    bare WGS 84 label and every unregistered frame refused by name. On that
    path the pivot (``latitude``, ``longitude``) is the NAD 83 position the
    grids are read at, and ``external_position`` is the input exactly as
    given; ``epoch`` and ``height`` are required there and refused elsewhere.
    """
    if not isinstance(source_frame, ReferenceFrame):
        raise TypeError(
            f"geodetic_position needs the reference frame the position is "
            f"expressed in, as its third argument; got "
            f"{type(source_frame).__name__} ({source_frame!r}). A latitude "
            f"and longitude do not carry their own frame. Pass "
            f"michspc.spc.frames.NAD83_2011 for an NAD 83 position."
        )
    # pivot_path resolves the record first, so a record that names a
    # registered frame must BE that frame's record (interim gate 1, finding
    # L4) before anything reads its epoch kind - and the result carries the
    # registry's record, never the caller's.
    path = pivot_path(source_frame)
    _require_transform_arguments(path, epoch, height, "geodetic_position")
    pivot_latitude, pivot_longitude, evidence = _apply_frame_path(
        path, latitude, longitude, epoch, height
    )

    return PointConversion(
        source_zone=None,
        target_zone=None,
        # The pivot's frame: the identity's one record, or NAD83(2011) at the
        # end of the HTDP path.
        frame=path.target,
        source_northing=None,
        source_easting=None,
        latitude=pivot_latitude,
        longitude=pivot_longitude,
        target_northing=None,
        target_easting=None,
        source_convergence=None,
        source_scale_factor=None,
        target_convergence=None,
        target_scale_factor=None,
        warnings=(),
        **evidence,
    )
