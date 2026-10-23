"""One conversion job, end to end.

Reads a coordinate file, converts every point, and produces the three outputs
the owner specified: a clean PNEZD export for CAD, a full-audit CSV, and a
plain-text job record explaining both.

This module is the only place that knows about all three layers at once. The
computation core knows nothing of files; the file layer knows nothing of zones;
this joins them and owns the unit conversion at the boundary.

Nothing here writes anything. ``run`` produces an immutable ``JobResult``; the
caller decides whether and where to commit it to disk. That keeps the whole
pipeline testable without a filesystem, and keeps the GUI's "preview then
convert" behaviour honest - what is previewed is what is written.
"""

from __future__ import annotations

import datetime
import hashlib
import math
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path

from michspc.fileio import counties as county_file
from michspc.fileio import formatting, geoid, pnezd, vertcon
from michspc.spc import htdp
from michspc.spc.autozone import (
    AutoZoneAmbiguousError,
    AutoZoneOutsideError,
    AutoZoneSystem,
    CountySet,
    ZoneAssignment,
    zone_for,
    zones_choosable,
)
from michspc.spc.convert import (
    ConversionWarning,
    HeightConvention,
    PointConversion,
    TransformHeight,
    WarningCode,
    convert_point,
    easting_looks_wrong_for_zone,
    geodetic_position,
    geodetic_to_geodetic,
    pivot_path,
    project_point,
    require_an_applicable_path,
    zone_to_geodetic,
)
from michspc.spc.factors import Factors, factors_at
from michspc.spc.frames import (
    NAD83_2011,
    NATRF2022,
    FrameMismatchError,
    FrameTransformation,
    FrameTransformationUnavailableError,
    ReferenceFrame,
    realization_period_of_use,
    require_frame_path,
)
from michspc.spc.units import LinearUnit
from michspc.spc.vertical import (
    HeightKind,
    VerticalDatum,
    VerticalTransformation,
    apply_shift,
    require_vertical_pair,
    signed_shift,
)
from michspc.spc.zones import Zone


class Direction(Enum):
    """What kind of conversion this job performs."""

    ZONE_TO_ZONE = "zone to zone"
    GEODETIC_TO_ZONE = "geodetic to State Plane"
    ZONE_TO_GEODETIC = "State Plane to geodetic"
    VERTICAL_ONLY = "vertical only"
    """The ONLY conversion performed is the vertical datum shift (the owner's
    feature of 2026-08-09). The user states an INPUT horizontal system - a
    zone, carried in ``source_zone`` exactly as ``ZONE_TO_GEODETIC`` does, or
    geodetic positions, stated as ``source_zone=None`` - and NO output system:
    ``target_zone`` must be None, and supplying one refuses, because no output
    horizontal system exists in this mode. The exports reproduce the input's
    coordinate columns unchanged (``output_unit`` must equal ``input_unit``
    for the same reason) and only the elevation moves. Requires
    ``VerticalMode.VERTICAL``, and is required by it - ``run`` refuses either
    without the other."""

    GEODETIC_TO_GEODETIC = "geodetic to geodetic"
    """Latitude and longitude in, latitude and longitude out, across a frame
    transformation (docs/PLAN-wgs84.md decision D7): a WGS 84 or ITRF position
    to NAD83(2011), or the reverse - HTDP's own core use. The input is in
    ``geodetic_frame`` and the output in ``target_geodetic_frame``, and the
    pair must be a registered NON-identity path: the same frame at both ends
    converts nothing, and every other pair refuses with the frame registry's
    own reason. No zone takes part; ``source_zone`` and ``target_zone`` must
    both be None.

    Pairs with ``VerticalMode.HORIZONTAL`` and with
    ``HORIZONTAL_AND_VERTICAL`` (a WGS 84 GNSS position and height in, a
    NAD 83 position and a NAVD 88 elevation out), never with ``VERTICAL`` -
    which pairs with ``VERTICAL_ONLY`` alone, as it always has."""


class VerticalMode(Enum):
    """Whether this job converts elevations between vertical datums.

    ``HORIZONTAL`` is today's behaviour, exactly: no vertical datum is asked
    for, nothing is tagged, and the Z column is re-expressed in the output unit
    but never shifted (DESIGN.md #35; plan section 1, the owner's decision that
    horizontal mode is unchanged). ``HORIZONTAL_AND_VERTICAL`` additionally
    moves every elevation from the source vertical datum to the target one
    through the registry in ``michspc/spc/vertical.py``, and reports the
    modeled shift and its per-point uncertainty beside it. ``VERTICAL`` moves
    ONLY the elevation - the same shift, the same reading, the same refusal
    shapes as ``HORIZONTAL_AND_VERTICAL``, applied by the same code - while
    the horizontal coordinates pass through unchanged; it pairs with
    ``Direction.VERTICAL_ONLY`` and with nothing else.
    """

    HORIZONTAL = "horizontal"
    HORIZONTAL_AND_VERTICAL = "horizontal and vertical"
    VERTICAL = "vertical"

    @property
    def converts_elevations(self) -> bool:
        """Whether this mode shifts elevations between vertical datums.

        The one authoritative statement of which modes carry a vertical
        conversion, read by every surface that gates a vertical block (the
        audit CSV's columns, the job record's METHOD section, the results
        table's headings) - so a mode added later cannot leave one surface
        silently horizontal.
        """
        return self is not VerticalMode.HORIZONTAL


class LongitudeConvention(Enum):
    """Which sign convention the input or output longitudes use.

    Deliberately has no default anywhere in the program. The manual and the
    owner's prior MATLAB tool use positive-west; NCAT, OPUS, GPS and every GIS
    use negative-west. Choosing wrongly throws a Michigan point about 340 miles,
    and the two are indistinguishable from the numbers alone, so the user states
    it every run (docs/DESIGN.md section 7).
    """

    # The attribution tail ("as used by OPUS, NCAT, GPS and GIS" / "as used by
    # NOAA Manual NOS NGS 5") went at #16 note 2 and #17; the worked example
    # ("(-84.37)" / "(84.37)") went at #28, both at the owner's direction. The
    # sign word alone names the convention completely - "negative west" IS the
    # definition, not an abbreviation of one.
    #
    # These strings are BOTH the dropdown's text and the job record's
    # "Longitude" line, and the owner has twice chosen one wording for both
    # rather than a short label beside a long record entry. The worked example
    # now lives in the dropdown's tooltip, where it teaches the person making
    # the choice without following the choice into every document.
    # Positive west is listed FIRST at the owner's request (docs/DESIGN.md
    # amendment #30). Declaration order is what the dropdown offers, because
    # controls.longitude_combo iterates the enum rather than carrying its own
    # list - so his own convention now sits at the top of it, above the
    # preselected entry he reaches for. Nothing in the program branches on
    # member order; `to_signed` and `from_signed` test identity.
    POSITIVE_WEST = "positive west"
    NEGATIVE_WEST = "negative west"

    def to_signed(self, longitude: float) -> float:
        return -longitude if self is LongitudeConvention.POSITIVE_WEST else longitude

    def from_signed(self, longitude: float) -> float:
        return -longitude if self is LongitudeConvention.POSITIVE_WEST else longitude


class AutoZone(Enum):
    """The Auto zone statement: "choose each point's zone from its position".

    Its one member, ``AUTO_ZONE``, is what ``JobSettings.target_zone`` holds
    on an Auto job (docs/PLAN-options-autozone.md section 3, work package
    Z2). It is deliberately NOT None - None already means "this direction
    has no zone at that end" - and NOT a ``Zone``: no one zone's constants,
    units or frame describe an Auto job, and a sentinel that duck-typed as a
    zone would let ``settings.target_zone.frame`` and friends read facts
    that are false for most of the job's points (the #11-finding-1 lesson).
    An Enum member, so it is a typed singleton that survives ``copy``,
    ``deepcopy`` and ``pickle`` as itself, and every test of it is by
    identity: ``settings.target_zone is AUTO_ZONE``.

    Legal only as the TARGET of a ``GEODETIC_TO_ZONE`` job (plan L1): a
    northing and easting do not say which zone they are in, so Auto is never
    an input. It requires ``JobSettings.auto_frame``.
    """

    AUTO = "auto"

    def __repr__(self) -> str:
        return "AUTO_ZONE"


AUTO_ZONE = AutoZone.AUTO
"""The Auto zone sentinel. See ``AutoZone``."""


AUTO_FRAMES: tuple[tuple[ReferenceFrame, AutoZoneSystem], ...] = (
    (NAD83_2011, AutoZoneSystem.SPCS83),
    (NATRF2022, AutoZoneSystem.SPCS2022),
)
"""The frames Auto chooses zones in, each with the zone system it chooses
among (plan section 1 item 3: an Options setting, NAD83(2011) or NATRF2022).
Checked at import against the zones themselves: every zone Auto can choose
for a system must be defined on that system's frame, so the pairing is a
fact the registry confirms, never an assumption."""


def _check_auto_frames() -> None:
    """Refuse to import a frame/system pairing the zones contradict.

    if/raise, never assert: the suite runs under -O.
    """
    for frame, system in AUTO_FRAMES:
        for zone in zones_choosable(system):
            if zone.frame is not frame:
                raise ValueError(
                    f"AUTO_FRAMES pairs {frame.code} with {system.value}, but "
                    f"{zone.name} ({zone.code}), a zone Auto can choose in "
                    f"{system.value}, is defined on {zone.frame.code}."
                )


_check_auto_frames()


def auto_zone_system(frame: ReferenceFrame) -> AutoZoneSystem:
    """The zone system Auto chooses among in ``frame`` (by identity), or a refusal."""
    for candidate, system in AUTO_FRAMES:
        if frame is candidate:
            return system
    raise ValueError(
        f"{_frame_label(frame)} is not a frame Auto chooses zones in. Auto "
        f"chooses among the SPCS 83 zones on {NAD83_2011.code} or the "
        f"SPCS2022 low-distortion zones on {NATRF2022.code}; pass "
        f"michspc.spc.frames.NAD83_2011 or michspc.spc.frames.NATRF2022 - "
        f"the registry's own record, not a copy of it."
    )


class ObservationDateSource(Enum):
    """Where a job's observation date came from (plan L10 and O3).

    ``TODAY``: the local calendar date the job ran (the Options default) -
    which ``run`` holds equal to ``today_local()``. ``ENTERED``: a date the
    user typed in Options. Stated beside ``JobSettings.observation_date``
    exactly when that date is, and refused by name when it is not; the job
    record prints it (work package Z3).
    """

    TODAY = "today"
    ENTERED = "entered"


@dataclass(frozen=True)
class JobSettings:
    """Everything the user chose. Recorded verbatim in the job record."""

    input_path: Path | None
    """The file these coordinates were read from.

    **Required, with no default**, the idiom ``longitude_convention`` already
    uses below. ``None`` is a statement, not an absence: "this job came from no
    file". A single typed point says exactly that, and the alternative - a
    fabricated placeholder path - is the plausible default docs/DESIGN.md
    section 1 forbids, because it would put a file name that was never read into
    the job record's INPUT block (amendment #26).

    Every read of this field is guarded, and each guard raises its own layer's
    error rather than letting ``None`` travel: ``run`` needs it only when no
    parsed source was handed in, and ``exports.output_stem`` and
    ``report.build_report`` refuse without it.
    """

    output_directory: Path | None
    """The folder this job's archive is written into.

    **Required, with no default**, and ``None`` is again a statement: "this job
    produces no file". The single-point path converts and displays, writing
    nothing at all, so it has no folder to name and does not invent one.
    ``run`` never reads this field; ``exports.archive_path`` and
    ``report.build_report`` refuse without it (amendment #26).
    """

    direction: Direction

    source_zone: Zone | None
    target_zone: Zone | None

    input_unit: LinearUnit
    output_unit: LinearUnit

    longitude_convention: LongitudeConvention | None
    """Which sign convention the file's longitudes use.

    **Required, with no default** (docs/DESIGN.md section 7). A default here is
    the failure the rule exists to prevent: a geodetic input file written
    positive west, converted as though it were negative west, lands 11,634,618 m
    away carrying nothing louder than an outside-zone-extent warning. The field
    is declared before the defaulted fields only because a frozen dataclass may
    not put a field without a default after one that has one.

    ``None`` is a statement, not an absence: "this job never consults the
    convention". Only a pure zone-to-zone job may say it - the grid coordinates
    on both ends carry no longitude - and ``run`` refuses any other direction
    that arrives with None rather than choosing one.
    """

    geoid_model: geoid.GeoidModel | None = geoid.GEOID18_MODEL
    """The geoid model whose separations this job's factors are computed from.

    Replaces ``apply_geoid: bool`` (WP-V5, docs/PLAN-vertical-datums.md section
    3.5): a bool could say only that *some* geoid was applied, and the job
    record then named the model from a module constant that a second model
    made ambiguous. The record chosen here is the one the audit CSV and the
    job record report, so the settings and the outputs cannot disagree about
    which grid the factors came from.

    ``None`` is a statement, not an absence - "no geoid was applied to this
    job" - the idiom ``input_path`` and ``output_directory`` already use. No
    interface offers it (the owner's "no none", plan section 5); it is a
    capability of the core, kept so report.py's "Geoid model not applied"
    branch stays honest and tested rather than dead.
    """

    geodetic_frame: ReferenceFrame = NAD83_2011
    """The reference frame this job's GEODETIC end is expressed in.

    Read at both geodetic ends, not only the input one: on
    ``GEODETIC_TO_ZONE`` it is the frame the file's latitudes and longitudes
    are read as, and on ``ZONE_TO_GEODETIC`` it is the frame the latitudes and
    longitudes written out are in - the source zone's own frame, or one of the
    WGS 84 and ITRF frames HTDP carries it to. On ``GEODETIC_TO_GEODETIC`` it
    is the INPUT frame (``target_geodetic_frame`` is the output's), and on a
    ``VERTICAL_ONLY`` job with geodetic input the frame the positions are in.
    Unread by ``ZONE_TO_ZONE`` and by ``VERTICAL_ONLY`` with a zone input,
    where every end is a zone carrying its own frame - and so a value other
    than the default there is refused by name rather than ignored (interim
    gate 1 of the WGS 84 build, finding I1), as a stray zone is.

    **NATRF2022 is now a legitimate value** (docs/DESIGN.md amendment #62). It
    was not when this field was written: NATRF2022 had no zones and setting
    this field to it was, in the words this docstring used to carry, the only
    way to reach a mismatch on purpose. Nineteen Michigan SPCS2022 zones are
    defined on it now, and a geodetic job against one of them states NATRF2022
    here and converts. What refuses is the pair, not the frame: the
    NAD83(2011) <-> NATRF2022 bridge is deferred with NGS's own transformation
    unpublished (docs/DEFERRED-NATRF2022-BRIDGE.md), so a frame that disagrees
    with the zone at the other end is refused by
    ``_require_a_registered_frame_path`` before the file is read, and by
    ``convert.require_frame_path`` again at every point. The WGS 84 and ITRF
    frames registered by the WGS 84 build (docs/DESIGN.md #70) pass that gate
    against an SPCS 83 zone or NAD83(2011): their positions are transformed
    by HTDP v3.6.0 to or from NAD83(2011) (plan W3), and the job then needs
    ``observation_date``.

    **The default is now load-bearing in a way it was not**, and this is worth
    stating rather than discovering: it is NAD83(2011), which is right for
    every SPCS 83 job and WRONG for every 2022-zone geodetic job. Wrong here
    means refused, never converted - the gate above - so the cost of the
    default is a refusal a caller must answer, not a coordinate. It stays a
    default because changing it would silently move every existing caller's
    job, and because the frame is still not the coin-flip the longitude sign
    is: the manual uses one longitude convention and every GPS and GIS the
    other, the two are indistinguishable from the numbers, and choosing wrongly
    throws a Michigan point about 340 miles, which is why docs/DESIGN.md
    section 7 forbids a default THERE.

    It is a field on the settings rather than a constant inside the loop
    precisely so it is visible: the job record states the frame the input was
    interpreted as, because a record that does not say which frame it assumed is
    not a record.
    """

    vertical_mode: VerticalMode = VerticalMode.HORIZONTAL
    """Whether elevations are converted between vertical datums.

    Defaults to ``HORIZONTAL`` because that default preserves every existing
    caller's behaviour exactly - it is today's job, and it asserts nothing
    about a vertical datum. The GUI toggle that offers the other mode is
    WP-V8's (docs/PLAN-vertical-datums.md section 4.1).
    """

    source_vertical_datum: VerticalDatum | None = None
    """The vertical datum the input file's elevations are expressed in.

    ``None`` is a statement, not an absence - "this job does not consult a
    vertical datum" - the idiom ``longitude_convention`` established. Only a
    ``HORIZONTAL`` job may say it, and a ``HORIZONTAL_AND_VERTICAL`` job must
    not arrive without it: NGVD 29 and NAVD 88 heights differ by up to 0.41 m
    across Michigan while looking identical, so ``run`` refuses rather than
    assumes, in both directions (a vertical job missing a datum, and a
    horizontal job supplied with one).
    """

    target_vertical_datum: VerticalDatum | None = None
    """The vertical datum the output elevations are expressed in.

    Same contract as ``source_vertical_datum``: ``None`` is the statement a
    horizontal job makes, and ``run`` refuses every other combination.
    """

    source_geoid_model: geoid.GeoidModel | None = None
    """The geoid model the INPUT elevations are stated against, or None.

    The owner's per-side feature (2026-08-09): on a vertical job the input
    and output geoid models are chosen separately, so ``geoid_model`` above
    is the OUTPUT side and this field is the INPUT side. ``None`` is a
    statement, not an absence - "no input-side geoid model is stated" -
    which is every job this program ran before the field existed.

    The rules ``run`` enforces, in the order it enforces them:

    * a HORIZONTAL job refuses this field outright: no vertical question was
      asked, so an input-side geoid model answers nothing;
    * each side's model must match its own side's vertical datum (the
      per-side form of DESIGN.md #32's two-eras rule);
    * BOTH sides carrying a model on a NON-identity transformation refuses:
      that job would compound a modeled datum shift with a modeled geoid
      change inside one Z column, and the honest form is two jobs;
    * both sides carrying DIFFERENT models on an IDENTITY transformation is
      the geoid-to-geoid conversion: the ellipsoid height is held fixed and
      the orthometric height re-derived under the output model,
      ``H_out = H_in + N_in - N_out`` (``GeoidSwapReading``). The same model
      on both sides is exactly the identity job this program always ran -
      no swap step, no new record.

    Compatibility (superseding DESIGN.md #41's either-endpoint contortion by
    GENERALIZATION): a pre-existing call shape that put a SOURCE-era model in
    ``geoid_model`` on a modeled job - NAVD88 -> NGVD29 with GEOID18, the one
    configuration #41 existed for - is normalized to this field internally
    (``per_side_geoid_models``), so every #41-era call keeps working and the
    old ``factors_use_source_era`` outcome falls out of per-side pairing
    rather than a special rule.
    """

    input_height_kind: HeightKind = HeightKind.ORTHOMETRIC
    """What the input Z column HOLDS - an elevation, or a GNSS height.

    ORTHOMETRIC by default, and the default is load-bearing: it is what every
    survey file this program has read contained and what it assumed silently
    before this field existed, so every pre-existing job is unchanged to the
    byte. This is one of the few defaults in the program, and it earns its
    place the way ``VerticalMode.HORIZONTAL`` does - the default member IS the
    status quo, so nothing is assumed that was not already being assumed.

    ELLIPSOID says the Z column holds heights above the GRS 80 ellipsoid, as a
    GNSS receiver produces them. The program then computes H = h - N at each
    point from the job's geoid model, and what it DOES with H depends on the
    mode - the only place in this feature where the mode matters:

    * **HORIZONTAL**: the Z column is written back exactly as supplied (the
      owner's instruction, 2026-08-11) and only the FACTORS change. That is
      not cosmetic: the elevation factor is R / (R + H + N), so a height that
      already contains the separation gets it added twice, which in Michigan
      is ~34 m of denominator - about **5 ppm** on every combined factor, a
      third of a foot in ten miles, always the same direction.
    * **HORIZONTAL_AND_VERTICAL and VERTICAL**: H is the height, and it goes
      on to the datum shift and into the Z column, datum-tagged.

    The rules ``run`` enforces:

    * ELLIPSOID with no geoid model on either side refuses - there is no N,
      so there is no H;
    * ELLIPSOID on a vertical job whose ``source_vertical_datum`` is not the
      model's own datum refuses: an ellipsoid height is in no vertical datum,
      and the H derived from it is in the MODEL's, so any other input datum
      would mislabel it before a single shift ran;
    * ELLIPSOID on a geoid-to-geoid job refuses. The input model cancels out
      of ``(h - N_in) + (N_in - N_out)``, so the input selection changes no
      number - and the record would state a conversion "from GEOID12B" of a
      height that was never on GEOID12B, a false sentence in an audit
      document (the owner's decision, 2026-08-11).
    """

    observation_date: datetime.date | None = None
    """The calendar date the job's WGS 84 or ITRF positions were observed.

    **Required exactly when a frame this job's direction reads is
    time-dependent** - WGS84(G1762), (G2139), (G2296), ITRF2014 or ITRF2020 -
    and refused by name when none is: a date stated for a job that never
    reads one would print an observation epoch into a record of a job that
    used none, the stray-field class of the 0.7.0 closing gate. No default
    date exists, because a Michigan point moves about 17 mm a year against
    NAD 83 in those frames (review/wgs84-w0/RECON.md section 3) and a guessed
    date is a guessed position.

    One date per job (docs/PLAN-wgs84.md decision D10): a PNEZD file has no
    column for it, so every point in the file is taken as observed on it.
    A real calendar date only (decision D9): a ``datetime.date``, never a
    ``datetime.datetime`` (HTDP's calendar entry means 00:00 UTC, so a time of
    day would be dropped without a word), and never a date after the day the
    job runs.
    """

    target_geodetic_frame: ReferenceFrame | None = None
    """The OUTPUT frame of a ``GEODETIC_TO_GEODETIC`` job, and of nothing else.

    Required by that direction and refused by name on every other, where no
    second geodetic end exists: ``geodetic_frame`` is the one geodetic end of
    every other direction, and a second frame stated beside it would be a
    frame the job record could print and the conversion never used.
    """

    auto_frame: ReferenceFrame | None = None
    """The frame an Auto job chooses its zones in, and of nothing else.

    Required exactly when ``target_zone`` is ``AUTO_ZONE`` and refused by
    name otherwise (the stray-field class). ``NAD83_2011`` chooses among the
    three SPCS 83 zones, ``NATRF2022`` among the eighteen SPCS2022
    low-distortion zones (``AUTO_FRAMES``) - matched by identity, the
    registry's own record. The input's ``geodetic_frame`` must have a
    registered path to it: NAD83(2011) input, or one of the five WGS 84 /
    ITRF frames through HTDP, for ``NAD83_2011``; NATRF2022 input only for
    ``NATRF2022``. Every other pairing is refused by
    ``frames.require_frame_path``'s own cross-frame message (plan L2).
    """

    observation_date_source: ObservationDateSource | None = None
    """How ``observation_date`` was obtained: TODAY or ENTERED (plan L10).

    Stated only beside an observation date, and refused by name on a job that
    reads no time-dependent frame, as a stray date is. When TODAY, the date
    must equal ``today_local()``. **Not yet required** when a date is: the
    two interface tabs do not send it until work package Z4, and the frozen
    WGS 84 disclosure pins build settings without it, so None is still
    accepted beside a date. The record prints it since work package Z3
    (``report._observation_date_source_text``: "the date the job ran
    (Options default)" or "entered by the user"); with None it prints the
    date line exactly as before, so every frozen record digest holds. Z4
    decides whether it becomes required.
    """


_IDENTITY_SIGMA_REASON = (
    "no modeled transformation was applied, so no model uncertainty exists"
)
"""Why an identity reading carries no sigma. NOT sigma 0.0: a zero would state
that the conversion's uncertainty was measured and found to be nothing, when in
truth no model ran and there is no model uncertainty to state - fabricating a
zero uncertainty is the same class of invented number as fabricating a zero
shift, and this program refuses both."""


@dataclass(frozen=True)
class VerticalReading:
    """The vertical half of one converted point: what moved the Z, how far,
    and how well that movement is known.

    ``sigma_m`` and ``sigma_unavailable_reason`` are exclusive by construction,
    because the two absences they distinguish must never blur: an identity job
    has no sigma because *no model ran*, and a modeled job at a position where
    the error grid interpolates negative has no sigma because *the model's
    output there cannot be an uncertainty* (docs/DESIGN.md #36). A bare None
    with no reason would collapse those into one silence.

    WP-V7 is the disclosure of these fields: the job record (report.py) states
    the datums, the direction, the shift summary and the sigma summary; the
    audit CSV (exports.py) carries the per-point datums, source elevation,
    shift and sigma; and the Single point panel (results_model.py) shows the
    shift and sigma as rows of their own. A sigma-less modeled reading also
    carries ``WarningCode.VERTICAL_SIGMA_UNAVAILABLE`` beside it, so every
    surface inherits the disclosure through the warning pipeline rather than
    each reading this record's reason field on its own.
    """

    transformation: VerticalTransformation
    """The registry record this shift was applied under. Checked against the
    job's settings per row (``_require_transformation_matches_settings``), not
    merely carried - the #36 reviewer note that ``apply_shift`` takes a bare
    float, so nothing downstream could notice a mismatch on its own."""

    shift_m: float
    """The shift APPLIED to the source height, metres:
    ``sign * grid_value``, from ``spc.vertical.signed_shift`` - never the raw
    grid value, whose sign is the same in both directions. Exactly 0.0 for an
    identity."""

    sigma_m: float | None
    """One-sigma uncertainty of the modeled shift, metres, from the companion
    error grid. None when no uncertainty exists or none can be stated - the
    reason beside it says which."""

    sigma_unavailable_reason: str | None
    """Why ``sigma_m`` is None, when it is. None when a sigma is present."""

    def __post_init__(self) -> None:
        # if/raise, never assert: the suite and the shipped program run
        # under -O, which strips asserts (docs/DESIGN.md section 7).
        if not isinstance(self.transformation, VerticalTransformation):
            # The #11-finding-1 guard, matching every neighbouring field: a
            # string spelling "NGVD29 -> NAVD88" duck-types deep into an
            # output layer before anything asks it for a direction_statement
            # (WP-V6 review gate, MEDIUM 4).
            raise TypeError(
                f"VerticalReading.transformation must be a "
                f"michspc.spc.vertical.VerticalTransformation record; got "
                f"{type(self.transformation).__name__} "
                f"({self.transformation!r}). The record is what the output "
                f"layers quote - its direction_statement, model, release and "
                f"caveat - so a stand-in cannot say what was done to the "
                f"height."
            )
        if self.sigma_m is None and self.sigma_unavailable_reason is None:
            raise ValueError(
                "A VerticalReading with no sigma must say why - an identity "
                "carries no model uncertainty, a negative interpolation "
                "cannot be one - so sigma_unavailable_reason is required "
                "whenever sigma_m is None. A silent absence is "
                "indistinguishable from a value nobody looked up."
            )
        if self.sigma_m is not None and self.sigma_unavailable_reason is not None:
            raise ValueError(
                f"A VerticalReading carries sigma_m={self.sigma_m!r} AND a "
                f"reason it is unavailable "
                f"({self.sigma_unavailable_reason!r}). These contradict each "
                f"other: one of them is false, and an output layer could "
                f"print either."
            )
        if self.sigma_m is not None and not vertcon.sigma_is_physical(self.sigma_m):
            # The one rule, stated once (vertcon.sigma_is_physical) and now
            # applied at its third site, so this record and the reader cannot
            # disagree about what a sigma is. A negative one-sigma reaching a
            # screen is the defect #36 spent a work package refusing; this
            # frozen record is what WP-V7's output layer will print from
            # (WP-V6 review gate, MEDIUM 4). NaN fails this check too - it
            # compares False against zero - and +inf falls to the next one.
            raise ValueError(
                f"A VerticalReading cannot carry sigma_m={self.sigma_m!r}: a "
                f"one-sigma uncertainty is a non-negative, finite number of "
                f"metres. Where the error model interpolates below zero, pass "
                f"sigma_m=None with the reason - never the raw figure under "
                f"this name (michspc.fileio.vertcon.UncertaintyGrid)."
            )
        if self.sigma_m is not None and not math.isfinite(self.sigma_m):
            raise ValueError(
                f"A VerticalReading cannot carry sigma_m={self.sigma_m!r}: a "
                f"non-finite value is not an uncertainty, and printed beside "
                f"a shift it would read as one."
            )
        if (
            self.sigma_unavailable_reason is not None
            and not self.sigma_unavailable_reason.strip()
        ):
            # The rule VerticalTransformation.__post_init__ already applies to
            # its citation and caveat: an empty reason is a silence wearing
            # the shape of an explanation.
            raise ValueError(
                "A VerticalReading's sigma_unavailable_reason is empty. The "
                "reason is what an output layer prints in place of the "
                "number; an empty one collapses the two absences this field "
                "exists to distinguish."
            )


@dataclass(frozen=True)
class EllipsoidHeightReading:
    """The h -> H half of one converted point: the model, the separation it
    read, and both heights.

    Recorded whenever an ellipsoid height was converted, in EVERY mode - the
    horizontal modes convert it too, for the factors, even though the Z column
    keeps the height as supplied (the owner's instruction). The arithmetic:

        H = h - N

    with N the geoid separation at the point's own position, negative
    throughout Michigan, so H is about 34 m LARGER than h here. The datum of H
    is the MODEL's, not anything the user typed - which is why the model's
    datum code is carried on the record rather than derived later from
    settings that may name a different one.

    ``__post_init__`` enforces the arithmetic, in ``GeoidSwapReading``'s
    idiom: a record whose stated orthometric height disagrees with its own two
    ingredients cannot be constructed, so a sign error cannot be recorded as
    though it were intended.
    """

    geoid_model_name: str
    """The model that supplied N, e.g. "GEOID18"."""

    vertical_datum_code: str
    """The model's own vertical datum - the datum H is in. NAVD88 for both
    shipped models."""

    ellipsoid_height_m: float
    """h in NAD83(2011), metres: exactly as supplied, converted to metres - or,
    on a job whose positions are in a WGS 84 or ITRF frame, the supplied h
    after it was transformed with the position to NAD83(2011) (plan decision
    D6; ``PointConversion.pivot_ellipsoid_height``), because N is published
    against NAD 83. The smaller number."""

    geoid_height_m: float
    """N at the point's pivot position, metres. Negative in Michigan."""

    orthometric_height_m: float
    """H = h - N, metres. Enforced against its ingredients below."""

    def __post_init__(self) -> None:
        for name in ("geoid_model_name", "vertical_datum_code"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"EllipsoidHeightReading.{name} must be a non-empty "
                    f"string naming what was used; got {value!r}."
                )
        for name in (
            "ellipsoid_height_m",
            "geoid_height_m",
            "orthometric_height_m",
        ):
            value = getattr(self, name)
            if not isinstance(value, float) or not math.isfinite(value):
                raise ValueError(
                    f"EllipsoidHeightReading.{name} must be a finite float in "
                    f"metres; got {value!r}."
                )
        expected = self.ellipsoid_height_m - self.geoid_height_m
        if abs(self.orthometric_height_m - expected) > 1e-12:
            raise ValueError(
                f"EllipsoidHeightReading states an orthometric height of "
                f"{self.orthometric_height_m!r} m, but its own ingredients "
                f"give H = h - N = {self.ellipsoid_height_m!r} - "
                f"{self.geoid_height_m!r} = {expected!r} m. The record must "
                f"agree with its own arithmetic; a height and a separation "
                f"are both bare floats, and adding where the rule subtracts "
                f"is wrong by twice the separation - about 68 m in Michigan."
            )


@dataclass(frozen=True)
class GeoidSwapReading:
    """The geoid-to-geoid half of one converted point: which two models, the
    two separations read at the pivot, and the value that moved the height.

    Exists only on an IDENTITY vertical job whose two sides state different
    geoid models (the owner's feature, 2026-08-09). The arithmetic it
    records: the ellipsoid height h = H + N is a property of the point, not
    of the model, so holding it fixed and changing N re-derives the
    orthometric height under the output model:

        H_out = H_in + N_in - N_out

    ``shift_m`` is exactly ``n_source_m - n_target_m`` - the value ADDED to
    the input height - and ``__post_init__`` enforces that arithmetic, so a
    record whose stated shift disagrees with its own ingredients cannot be
    constructed. The datum ``VerticalReading`` beside this one stays the
    identity record: both are true - the datum did not change, the geoid did.
    """

    source_model_name: str
    """The input-side model's ``GeoidModel.name``, e.g. "GEOID12B"."""

    target_model_name: str
    """The output-side model's name - the model the Z column is stated
    against, and the model the factors were computed from."""

    n_source_m: float
    """The input model's geoid separation at the pivot, metres. Negative
    throughout Michigan."""

    n_target_m: float
    """The output model's geoid separation at the same pivot, metres."""

    shift_m: float
    """``n_source_m - n_target_m``, metres: what was ADDED to the input
    height. Enforced against the two separations at construction."""

    def __post_init__(self) -> None:
        # if/raise, never assert: the suite and the shipped program run
        # under -O, which strips asserts (docs/DESIGN.md section 7).
        for label, name in (
            ("source_model_name", self.source_model_name),
            ("target_model_name", self.target_model_name),
        ):
            if not isinstance(name, str) or not name.strip():
                # The #11-finding-1 guard for this record's likeliest
                # impostor: a GeoidModel RECORD passed where its name
                # belongs would print "GeoidModel(name='GEOID18', ...)" into
                # a label a surveyor reads.
                raise TypeError(
                    f"GeoidSwapReading.{label} must be the geoid model's own "
                    f"non-empty name string; got {type(name).__name__} "
                    f"({name!r}). Pass model.name, not the record."
                )
        for label, value in (
            ("n_source_m", self.n_source_m),
            ("n_target_m", self.n_target_m),
            ("shift_m", self.shift_m),
        ):
            if not isinstance(value, float) or not math.isfinite(value):
                raise ValueError(
                    f"GeoidSwapReading.{label} must be a finite number of "
                    f"metres; got {value!r}. A non-finite separation cannot "
                    f"move a height."
                )
        if self.source_model_name == self.target_model_name:
            raise ValueError(
                f"GeoidSwapReading names {self.source_model_name!r} on both "
                f"sides. The same model on both sides is the ordinary "
                f"identity job - no swap step runs and no swap record "
                f"exists - so a record claiming one is a wiring defect."
            )
        if abs(self.shift_m - (self.n_source_m - self.n_target_m)) > 1e-12:
            # The one place the swap arithmetic is defined; every surface
            # reports shift_m, so a record that disagreed with its own
            # ingredients would print a number nothing derived.
            raise ValueError(
                f"GeoidSwapReading.shift_m ({self.shift_m!r}) does not equal "
                f"n_source_m - n_target_m "
                f"({self.n_source_m!r} - {self.n_target_m!r} = "
                f"{self.n_source_m - self.n_target_m!r}). The shift IS that "
                f"difference - H_out = H_in + N_in - N_out - and a record "
                f"carrying any other number is wrong by construction."
            )


@dataclass(frozen=True)
class ConvertedPoint:
    """One point, converted, with the evidence for it."""

    row: pnezd.PnezdRow
    conversion: PointConversion
    factors: Factors

    output_northing: float
    output_easting: float
    """In the OUTPUT unit, ready to format."""

    output_elevation: float | None
    """In the output unit.

    For a HORIZONTAL job this is the input elevation re-expressed if the units
    differ, and nothing else - orthometric height does not depend on the
    horizontal zone. For a HORIZONTAL_AND_VERTICAL job it is the SHIFTED
    height, expressed in the target vertical datum ``vertical`` names:
    docs/PLAN-vertical-datums.md section 3.6 explicitly repeals the "unchanged
    by the conversion" sentence this field carried for the Z column. None when
    the point carried no elevation - or when the vertical shift was
    unavailable (``WarningCode.VERTICAL_SHIFT_UNAVAILABLE``), because an
    unconverted height printed as converted is the tier sentence's failure
    mode.

    An ELLIPSOID Z on a job with a frame transformation (plan decision D6) is
    the ellipsoid height in the job's OUTPUT frame on a horizontal job - the
    height transformed with the position - and H = h(NAD 83) - N on a
    vertical one; an ORTHOMETRIC Z is never moved by the transformation.
    """

    vertical: VerticalReading | None = None
    """The vertical transformation evidence for this point, or None.

    None on every point of a HORIZONTAL job, on a vertical job's point that
    carried no elevation (there is no height to shift), and on a point whose
    shift was unavailable (the warning beside it says so).
    """

    ellipsoid_height: EllipsoidHeightReading | None = None
    """The h -> H evidence for this point, or None.

    Present exactly when this point's height was supplied as an ellipsoid
    height and the geoid tile covered its position - in ANY mode, including
    horizontal, where the conversion still happens for the factors even
    though the Z column keeps the ellipsoid height. None on every
    orthometric-input point, on a point with no height at all, and on one
    whose position the tile does not cover, where the warning says so.
    """

    geoid_swap: GeoidSwapReading | None = None
    """The geoid-to-geoid evidence for this point, or None.

    Present exactly when a geoid change moved this point's elevation: an
    identity vertical job whose two sides state different geoid models, on a
    point whose elevation was read and whose position both tiles cover. None
    everywhere else - including a swap job's point whose elevation was
    refused for coverage, where ``vertical`` is None too and the warning
    says why.
    """

    warnings: tuple[ConversionWarning, ...] = field(default_factory=tuple)

    auto_zone: ZoneAssignment | None = None
    """On an Auto job, the zone chosen for this point and the county that chose it.

    ``auto_zone.zone`` is the registry record the point was projected into -
    the same record as ``conversion.target_zone`` - with the county's name
    and FIPS beside it (plan O2: the record names each point's zone and
    county as facts). None on every point of a job that is not Auto, so
    every existing output is unchanged.
    """

    @property
    def point_id(self) -> str:
        return self.row.point_id


class AutoZoneUnplacedPointsError(ValueError):
    """An Auto job with points no zone could be chosen for: the WHOLE job is refused.

    The house rule (lead's review of work package Z2): every horizontal per-row
    refusal in this program refuses the job - a latitude or longitude out of
    range, a position outside HTDP's velocity grid - and Auto follows it. A
    point in no Michigan county, or claimed by two county polygons, is never
    given the nearest zone (plan L5) and is never silently dropped from the
    output; the job converts nothing, and the message names EVERY such point,
    with the position tested and its frame, so the file can be corrected in
    one pass. ``points`` carries them as data: ``(point id, latitude,
    longitude)``, signed decimal degrees, negative west, in ``frame``.
    """

    def __init__(
        self,
        message: str,
        *,
        points: tuple[tuple[str, float, float], ...],
        frame: ReferenceFrame,
    ) -> None:
        super().__init__(message)
        self.points = points
        self.frame = frame


@dataclass(frozen=True)
class _UnplacedPoint:
    """One row Auto could not place - collected by ``run``, never returned."""

    point_id: str
    latitude: float
    longitude: float
    frame: ReferenceFrame
    reason: str
    transformed_from: ReferenceFrame | None


class _AutoZoneUnplaced(Exception):
    """``_convert_row``'s private signal to ``run``'s row loop: this row has no zone.

    Caught ONLY there, which collects every such row and then raises
    ``AutoZoneUnplacedPointsError`` for the whole job. Nothing is skipped.
    """

    def __init__(self, point: _UnplacedPoint) -> None:
        super().__init__(point.reason)
        self.point = point


@dataclass(frozen=True)
class JobResult:
    """The complete outcome of a job. Immutable."""

    settings: JobSettings
    points: tuple[ConvertedPoint, ...]

    input_sha256: str | None
    """SHA-256 of the bytes that were actually converted, or None.

    Comes from the reader, which hashes what it decoded (``pnezd.read``), and
    never from a second look at ``settings.input_path``. Hashing the path
    independently certified a file rather than a conversion: a caller supplying
    an in-memory ``source`` while pointing ``input_path`` at README.md produced
    a record that named README.md, carried the SHA-256 of the actual README,
    and stated "Format PNEZD, no header row" - a record of bytes that were never
    read, let alone converted (WP-R3 fix 2). The same shape existed on the
    ordinary path whenever the file was edited between the parse and the hash.

    ``None`` means the rows were handed to ``run`` already parsed, so no bytes
    passed through this program and there is nothing it can honestly certify.
    The job record says exactly that. It is never filled in with a guess.
    """

    input_row_count: int
    skipped_blank_lines: int
    geoid_model: str | None

    job_warnings: tuple[ConversionWarning, ...] = ()
    """Warnings about the JOB rather than about any one point.

    Today exactly one kind: ``WarningCode.REALIZATION_OUTSIDE_PERIOD_OF_USE``
    (plan decision D9), a fact about the frame and the observation date that
    is the same for every point (decision D10), so it is raised once here
    rather than repeated on every row. Not part of ``warnings`` above, whose
    every entry is paired with the point that raised it; the job record and
    the interface's warnings field read this alongside it (work packages W4
    and W5). Empty on every job without a time-dependent frame, so every
    existing job is unchanged.
    """

    @property
    def warnings(self) -> tuple[tuple[str, ConversionWarning], ...]:
        """Every warning, paired with the point identifier that raised it."""
        return tuple(
            (point.point_id, warning)
            for point in self.points
            for warning in point.warnings
        )

    def warnings_of(self, code: WarningCode) -> tuple[tuple[str, ConversionWarning], ...]:
        return tuple((pid, w) for pid, w in self.warnings if w.code is code)

    @property
    def points_without_elevation(self) -> tuple[ConvertedPoint, ...]:
        return tuple(p for p in self.points if not p.factors.has_elevation)

    @property
    def combined_factors(self) -> tuple[float, ...]:
        return tuple(
            p.factors.combined_factor
            for p in self.points
            if p.factors.combined_factor is not None
        )

    @property
    def grid_scale_factors(self) -> tuple[float, ...]:
        # None is skipped exactly as combined_factors skips it: a vertical-only
        # job with geodetic input has no zone anywhere, so its points carry no
        # grid scale factor - an absence, never a fabricated 1.0.
        return tuple(
            p.factors.grid_scale_factor
            for p in self.points
            if p.factors.grid_scale_factor is not None
        )


def file_sha256(path: Path) -> str:
    """Hash a file on disk, in blocks.

    **Not what the job record uses.** The record's digest comes from the reader,
    which hashes the bytes it actually parsed (``pnezd.read``); a hash taken
    from a path afterwards describes whatever is at that path at that moment,
    which is a different thing and was WP-R3 fix 2. This remains for callers
    that genuinely want to hash a file - the GEOID18 tile check is one - and is
    kept here because that is where it has always lived.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


_STRAY_ZONE_FIELDS = {
    # field -> (the direction that never reads it, what that direction does)
    "source_zone": (
        Direction.GEODETIC_TO_ZONE,
        "the input is a latitude and longitude, so no zone is inverted",
    ),
    "target_zone": (
        Direction.ZONE_TO_GEODETIC,
        "the output is a latitude and longitude, so no zone is projected into",
    ),
}


def _stray_zone_message(settings: JobSettings, field: str) -> str:
    """Why a zone field this direction never reads is refused, not ignored.

    Ignoring it is what this program did until the 0.7.0 closing gate, and the
    gate showed what it costs: a ``GEODETIC_TO_ZONE`` job carrying a stale
    ``source_zone`` converts through the target zone alone - correctly - and
    then the job record, which derives its zone blocks from these SETTINGS
    rather than from the conversion that ran, prints a FROM block for a zone
    nothing was projected from, and states that the two zones share a frame and
    that "this conversion is an exact re-projection". No projection from that
    zone occurred. The archive round-trips and the record is authoritative, so
    a false work history escapes inside a document written to defend a survey.

    Refused at the settings, in the same block as the missing-zone refusals,
    because it is a fact about the settings and costs nothing to check. The
    other repair - deriving the record's zones from the ``PointConversion``
    instead - was not taken here: it moves an authority the record has had
    since 0.1.0, and this refusal closes the hole without moving it.
    """
    direction, because = _STRAY_ZONE_FIELDS[field]
    stray = getattr(settings, field)
    other = "target_zone" if field == "source_zone" else "source_zone"
    kept = getattr(settings, other)
    kept_text = (
        f"{other}=AUTO_ZONE (each point's own zone)"
        if kept is AUTO_ZONE
        else f"{other}={kept.name} ({kept.code})"
    )
    return (
        f"A {direction.name} job was given {field}={stray.name} "
        f"({stray.code}), which this direction never reads: {because}. The "
        f"conversion would run through {kept_text} "
        f"alone, and the job record - which derives its zone blocks from "
        f"these settings, not from the conversion that ran - would print a "
        f"block for {stray.name} and call the job an exact re-projection "
        f"between the two zones. That record is the document a surveyor keeps "
        f"to defend the job, so a zone that took no part in it is refused "
        f"here rather than ignored. Pass {field}=None."
    )


_AUTO_TARGET_REASONS = {
    Direction.ZONE_TO_ZONE: (
        "its input is State Plane coordinates, and Auto chooses a zone from a "
        "latitude and longitude only (docs/PLAN-options-autozone.md L1)"
    ),
    Direction.ZONE_TO_GEODETIC: (
        "its output is a latitude and longitude, so no zone is projected into"
    ),
    Direction.VERTICAL_ONLY: (
        "no output horizontal system exists in this mode, so no zone is "
        "projected into"
    ),
    Direction.GEODETIC_TO_GEODETIC: (
        "its output is a latitude and longitude, so no zone is projected into"
    ),
}


def _require_auto_zone_settings(settings: JobSettings) -> None:
    """The Auto zone statement's own refusals, before anything else reads a zone.

    Work package Z2 (docs/PLAN-options-autozone.md L1, L2). In order:

    * ``AUTO_ZONE`` as ``source_zone`` - never: a northing and easting do not
      say which zone they are in (the zones overlap in grid coordinates);
    * ``AUTO_ZONE`` as ``target_zone`` of any direction but
      ``GEODETIC_TO_ZONE``;
    * ``AUTO_ZONE`` without ``auto_frame``; ``auto_frame`` without
      ``AUTO_ZONE`` (the stray-field class, by name);
    * an ``auto_frame`` that is not a ``ReferenceFrame`` (TypeError), or not
      the registry's own NAD83(2011) or NATRF2022 record, by identity.

    The pairing of ``auto_frame`` with the input's ``geodetic_frame`` is NOT
    checked here: it is the frame gate's, through the same
    ``frames.require_frame_path`` refusal a fixed-zone job meets.
    """
    if settings.source_zone is AUTO_ZONE:
        raise ValueError(
            "JobSettings.source_zone was AUTO_ZONE. Auto chooses a zone from a "
            "latitude and longitude, so it can only be the TARGET of a "
            "geodetic-to-State Plane job: a northing and easting do not say "
            "which zone they are in - Michigan's zones overlap in grid "
            "coordinates - so the zone an input is in is never inferred. "
            "State the zone the coordinates are in."
        )
    auto_target = settings.target_zone is AUTO_ZONE
    if auto_target and settings.direction is not Direction.GEODETIC_TO_ZONE:
        raise ValueError(
            f"A {settings.direction.name} job was given target_zone=AUTO_ZONE, "
            f"but Auto zone is the output of a "
            f"{Direction.GEODETIC_TO_ZONE.name} job only - it chooses each "
            f"point's zone from that point's latitude and longitude - and "
            f"this job {_AUTO_TARGET_REASONS[settings.direction]}. State the "
            f"zone, or None where this direction has no zone."
        )
    if settings.auto_frame is None:
        if auto_target:
            raise ValueError(
                f"A job with target_zone=AUTO_ZONE needs auto_frame, the frame "
                f"Auto chooses zones in: {NAD83_2011.code}, whose zones are "
                f"the three SPCS 83 zones, or {NATRF2022.code}, whose zones "
                f"are the eighteen SPCS2022 low-distortion zones. It has no "
                f"default: the two systems put the same point in different "
                f"zones with different coordinates."
            )
        return
    if not auto_target:
        zone = settings.target_zone
        stated = (
            f"target_zone={zone.name} ({zone.code})"
            if isinstance(zone, Zone)
            else "target_zone=None"
        )
        raise ValueError(
            f"A {settings.direction.name} job with {stated} was given "
            f"auto_frame={_frame_label(settings.auto_frame)}, which only an "
            f"Auto job (target_zone=AUTO_ZONE) reads. No zone is chosen from "
            f"a position in this job, so the frame would be one the job "
            f"record could print and the conversion never used. Pass "
            f"auto_frame=None."
        )
    if not isinstance(settings.auto_frame, ReferenceFrame):
        raise TypeError(
            f"JobSettings.auto_frame must be a michspc.spc.frames."
            f"ReferenceFrame - NAD83_2011 or NATRF2022; got "
            f"{type(settings.auto_frame).__name__} ({settings.auto_frame!r})."
        )
    auto_zone_system(settings.auto_frame)  # refuses any other record


def _height_frame(settings: JobSettings) -> ReferenceFrame:
    """The reference frame this job's positions - and so its heights - are in.

    One reader for a fact that is spread across four directions, so the
    ellipsoid-height gate below cannot ask the question one way and the
    conversion answer it another:

    * ``GEODETIC_TO_ZONE`` - ``geodetic_frame``, the frame the file's latitudes
      and longitudes are read as (and, past the frame gate, the target zone's);
    * ``ZONE_TO_GEODETIC`` and ``ZONE_TO_ZONE`` - the source zone's own frame;
    * ``VERTICAL_ONLY`` - the source zone's frame with a zone input, and
      ``geodetic_frame`` with a geodetic one;
    * ``GEODETIC_TO_GEODETIC`` - ``geodetic_frame``, the INPUT frame: the Z
      column is read in it, and is carried from it to NAD83(2011) for
      ``H = h - N`` whichever end NAD83(2011) is.

    Called only after the direction block has established that the fields each
    direction needs are present.
    """
    if settings.direction is Direction.GEODETIC_TO_ZONE:
        return settings.geodetic_frame
    if settings.source_zone is not None:
        return settings.source_zone.frame
    return settings.geodetic_frame


def run(settings: JobSettings, source: pnezd.PnezdFile | None = None) -> JobResult:
    """Execute a job. Reads if no parsed file is supplied; never writes.

    When ``source`` is supplied the job converts those rows and nothing else, so
    the record's SHA-256 is that source's own digest - which is None unless the
    source came from ``pnezd.read``. It is never taken from
    ``settings.input_path``, because that path was not what was converted
    (WP-R3 fix 2).
    """
    # Interim gate 1 of the WGS 84 build, finding I2: a zone field holding
    # something that is not a zone - a frame record is the likeliest, and
    # JobSettings(target_zone=WGS84_G2296) reads plausibly - used to fail as
    # an AttributeError deep in the gates below, which walks through every
    # ``except FrameMismatchError`` a caller writes. A TypeError naming it,
    # before anything else reads the field.
    for name in ("source_zone", "target_zone"):
        value = getattr(settings, name)
        if value is not None and value is not AUTO_ZONE and not isinstance(value, Zone):
            raise TypeError(
                f"JobSettings.{name} must be a michspc.spc.zones.Zone, or None "
                f"where the direction has no zone at that end; got "
                f"{type(value).__name__} ({value!r}). A reference frame is not "
                f"a zone: a geodetic end's frame is stated in geodetic_frame."
                + (
                    " To have each point's zone chosen from its position, "
                    "pass michspc.job.AUTO_ZONE (the object, not a string)."
                    if name == "target_zone"
                    else ""
                )
            )
    _require_auto_zone_settings(settings)

    if settings.direction is Direction.ZONE_TO_ZONE:
        if settings.source_zone is None or settings.target_zone is None:
            raise ValueError(
                "A zone-to-zone conversion needs both a source and a target "
                "zone. Neither is inferred from the coordinates."
            )
    elif settings.direction is Direction.GEODETIC_TO_ZONE:
        if settings.target_zone is None:
            raise ValueError("A geodetic conversion needs a target zone.")
        if settings.source_zone is not None:
            raise ValueError(_stray_zone_message(settings, "source_zone"))
    elif settings.direction is Direction.VERTICAL_ONLY:
        if settings.target_zone is not None:
            raise ValueError(
                f"A vertical-only job was given target_zone "
                f"{settings.target_zone.name}, but no output horizontal "
                f"system exists in this mode: the only conversion performed "
                f"is the vertical datum shift, and the exports reproduce the "
                f"input's coordinate columns unchanged. State "
                f"target_zone=None; to convert the coordinates as well, run "
                f"a zone-to-zone job with "
                f"VerticalMode.HORIZONTAL_AND_VERTICAL."
            )
        if settings.output_unit != settings.input_unit:
            raise ValueError(
                f"A vertical-only job's exports reproduce the input's "
                f"coordinate columns exactly, so its output unit must equal "
                f"its input unit - re-expressing "
                f"{settings.input_unit.code} values in "
                f"{settings.output_unit.code} would alter every column the "
                f"export promises to mirror. Got "
                f"input_unit={settings.input_unit.code}, "
                f"output_unit={settings.output_unit.code}. To change units, "
                f"run a horizontal or horizontal-and-vertical job, whose "
                f"exports state the output unit rather than mirroring the "
                f"input."
            )
        # ``source_zone`` is the input system: a Zone for a PNEZD file, or
        # None for geodetic positions - exactly the existing source_zone
        # idiom, so no third field exists to disagree with it.
    elif settings.direction is Direction.GEODETIC_TO_GEODETIC:
        stray = [
            name
            for name in ("source_zone", "target_zone")
            if getattr(settings, name) is not None
        ]
        if stray:
            raise ValueError(_stray_geodetic_to_geodetic_zone_message(settings, stray))
        if settings.target_geodetic_frame is None:
            raise ValueError(
                "A geodetic-to-geodetic job needs the frame its output "
                "positions are wanted in, target_geodetic_frame, beside the "
                "frame its input positions are in, geodetic_frame. Neither "
                "is inferred: a WGS 84 and a NAD 83 position of one point "
                "differ by about 1.3 m in Michigan and look alike."
            )
    else:
        if settings.source_zone is None:
            raise ValueError(
                "Converting to geodetic needs the zone the file is in."
            )
        if settings.target_zone is not None:
            raise ValueError(_stray_zone_message(settings, "target_zone"))

    # Two settings-level gates, slotted here - after the zone-presence block
    # above, before every refusal that follows. Both are facts about the
    # SETTINGS rather than about a row, so both must fire before the file is
    # read rather than once per point. The sequence below is EXTENDED at this
    # point and never reordered: which refusal a doubly-invalid job raises is
    # a pinned property.
    #
    # The WGS 84 build (docs/PLAN-wgs84.md, work package W3) extends it in
    # three places, each a fact about the settings: the stray frame fields
    # first, beside the stray-zone refusals they mirror; the frame path, which
    # now returns the record the rows will apply; and the observation date,
    # straight after it, because whether a date is required is a property of
    # the path just found.
    _require_no_stray_frame_fields(settings)
    frame_path = _require_a_registered_frame_path(settings)
    epoch, job_warnings = _require_the_observation_date(settings, frame_path)
    _require_units_the_zones_publish(settings)
    _require_a_convertible_ellipsoid_height_frame(settings)

    # Which jobs consult the longitude sign convention. A vertical-only job
    # reads longitudes from the file ONLY when its input is geodetic; with a
    # zone input the file carries none and none are written, so that job
    # states None exactly as a zone-to-zone job does.
    consults_longitude = settings.direction in (
        Direction.GEODETIC_TO_ZONE,
        Direction.ZONE_TO_GEODETIC,
        Direction.GEODETIC_TO_GEODETIC,
    ) or (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is None
    )
    if consults_longitude and settings.longitude_convention is None:
        raise ValueError(
            "A conversion with geodetic coordinates on either end needs the "
            "longitude sign convention the file uses. It has no default: the "
            "manual writes Michigan's longitudes positive west and every GPS, "
            "GIS and NGS tool writes them negative west, the two are "
            "indistinguishable from the numbers alone, and choosing wrongly "
            "moves a Michigan point about 340 miles."
        )
    if (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is not None
        and settings.longitude_convention is not None
    ):
        raise ValueError(
            f"A vertical-only job reading State Plane coordinates was given "
            f"a longitude sign convention "
            f"({settings.longitude_convention.value!r}). The input file "
            f"carries no longitude column and none is written - the pivot "
            f"latitude and longitude are computed from the zone, in the "
            f"program's own signed convention - so a convention stated here "
            f"would be an answer to a question this job never asks, exactly "
            f"as a zone-to-zone job states None. Pass "
            f"longitude_convention=None."
        )

    # Every vertical-settings refusal fires here, before any file is read and
    # long before any point converts (docs/PLAN-vertical-datums.md section
    # 3.5). None for a horizontal job; the registry's record for a vertical
    # one.
    transformation = _require_vertical_settings(settings)

    if source is None and settings.input_path is None:
        # ``input_path`` is None only because the caller stated this job came
        # from no file, and no rows arrived either - so there is nothing to
        # convert and nothing to read. Refused rather than defaulted: a
        # placeholder path here would send pnezd.read at a file nobody named
        # (docs/DESIGN.md section 1, amendment #26).
        raise ValueError(
            "This job has no input file and no parsed rows, so there is "
            "nothing to convert. Either give JobSettings an input_path, or "
            "hand run() a source - michspc.fileio.pnezd.parse_typed_point "
            "builds one from a single typed coordinate."
        )

    parsed = source or pnezd.read(settings.input_path)

    if settings.geoid_model is not None and not isinstance(
        settings.geoid_model, geoid.GeoidModel
    ):
        # The #11-finding-1 class, at this field's likeliest call site: the
        # argument replaced ``apply_geoid: bool``, so ``geoid_model=True`` is
        # the exact habit a caller carries forward - and truthiness would
        # accept it here, then fail attribute-by-attribute somewhere inside
        # the loader. if/raise, never assert (-O strips asserts).
        raise TypeError(
            f"JobSettings.geoid_model must be a michspc.fileio.geoid."
            f"GeoidModel record, or None to state that no geoid is applied; "
            f"got {type(settings.geoid_model).__name__} "
            f"({settings.geoid_model!r}). In particular True is not 'the "
            f"default model' - that was apply_geoid's contract, retired by "
            f"WP-V5. Pass geoid.GEOID18_MODEL, geoid.GEOID12B_MODEL, or a "
            f"record from geoid.geoid_model_by_name()."
        )

    if (
        settings.geoid_model is not None
        and settings.geoid_model not in geoid.ALL_GEOID_MODELS
    ):
        # Registry membership, checked BEFORE any point converts. The loaders
        # deliberately accept a hand-built record (the suite exercises
        # tampered tiles through one), but a JOB may not: report.py resolves
        # the record back from the registry by name to cite the tile and its
        # digest, so a non-registry record would convert every point and then
        # fail with a bare KeyError at the record write - a whole conversion
        # discarded at the last step, found by the WP-V5 review gate (LOW 1).
        # Membership is by equality, so a caller who rebuilt a record with a
        # registry model's exact facts is accepted: identical facts ARE the
        # model. What is refused is a record whose facts the registry does
        # not hold - a model this program cannot cite.
        known = ", ".join(model.name for model in geoid.ALL_GEOID_MODELS)
        raise ValueError(
            f"JobSettings.geoid_model {settings.geoid_model.name!r} is not a "
            f"registered geoid model, so the job record could not cite its "
            f"tile and checksum. A job converts only against the models this "
            f"program ships: {known}. Use the records in "
            f"michspc.fileio.geoid, or geoid_model_by_name()."
        )

    if settings.source_geoid_model is not None and not isinstance(
        settings.source_geoid_model, geoid.GeoidModel
    ):
        # The impostor guard ``geoid_model`` carries above, for the input
        # side: the two fields are chosen by parallel dropdowns, so the same
        # habits reach both. if/raise, never assert (-O strips asserts).
        raise TypeError(
            f"JobSettings.source_geoid_model must be a michspc.fileio.geoid."
            f"GeoidModel record, or None to state that no input-side geoid "
            f"model is stated; got "
            f"{type(settings.source_geoid_model).__name__} "
            f"({settings.source_geoid_model!r}). Pass geoid.GEOID18_MODEL, "
            f"geoid.GEOID12B_MODEL, or a record from "
            f"geoid.geoid_model_by_name()."
        )

    if (
        settings.source_geoid_model is not None
        and settings.source_geoid_model not in geoid.ALL_GEOID_MODELS
    ):
        # Registry membership, the geoid_model rule above verbatim: the job
        # record cites the input model's tile and digest from the registry,
        # so a model the registry does not hold cannot be documented.
        known = ", ".join(model.name for model in geoid.ALL_GEOID_MODELS)
        raise ValueError(
            f"JobSettings.source_geoid_model "
            f"{settings.source_geoid_model.name!r} is not a registered geoid "
            f"model, so the job record could not cite its tile and checksum. "
            f"A job converts only against the models this program ships: "
            f"{known}. Use the records in michspc.fileio.geoid, or "
            f"geoid_model_by_name()."
        )

    if transformation is None and settings.source_geoid_model is not None:
        # A horizontal job asked no vertical question, so an input-side
        # geoid model answers nothing - the mirror of the vertical-datum
        # refusal, arriving at the new field. Silently ignoring it would let
        # a caller believe the input elevations' geoid statement was used.
        raise ValueError(
            f"This job is horizontal-only, but source_geoid_model "
            f"({settings.source_geoid_model.name}) was supplied. An "
            f"input-side geoid model exists to convert elevations between "
            f"geoid models, and a horizontal job converts no elevation at "
            f"all. Set vertical_mode to a mode that converts elevations, or "
            f"state None; a horizontal job's factors come from geoid_model "
            f"alone."
        )

    if (
        transformation is not None
        and not transformation.is_identity
        and settings.geoid_model is not None
        and settings.source_geoid_model is not None
    ):
        # The compound-job refusal: a modeled datum shift AND a geoid change
        # inside one Z column would stack two modeled corrections with no
        # surface stating either alone. The honest form is two jobs, each
        # with its own record - and the refusal says so rather than picking
        # an order of application nobody stated. Guarded before the
        # per-side era checks below, because the advice here (split the job)
        # is the one that survives whichever era pairing arrives with it -
        # today only NAVD 88 has published models, so this fires ahead of a
        # NAPGD2022-era registry rather than after it.
        raise ValueError(
            f"This job states a geoid model on BOTH sides "
            f"(source_geoid_model={settings.source_geoid_model.name}, "
            f"geoid_model={settings.geoid_model.name}) of a modeled vertical "
            f"transformation ({transformation.source.code} -> "
            f"{transformation.target.code}). That would compound a modeled "
            f"datum shift with a modeled geoid change inside one elevation, "
            f"and no output could say which correction moved the height. "
            f"Run two jobs: convert between the geoid models in an identity "
            f"job ({transformation.source.code} -> "
            f"{transformation.source.code}), then convert the datum with "
            f"one geoid model stated."
        )

    if transformation is not None and settings.source_geoid_model is not None:
        # The per-side form of DESIGN.md #32's two-eras rule: the INPUT
        # model's separations must be published for the INPUT elevations'
        # own datum, because H_in + N_in is the ellipsoid height only when
        # the two share an era. The output side keeps the guard below.
        model = settings.source_geoid_model
        if model.vertical_datum.code != settings.source_vertical_datum.code:
            raise geoid.GeoidError(
                f"The {model.name} geoid model publishes separations for "
                f"heights in {model.vertical_datum.code}, and this job's "
                f"INPUT elevations are "
                f"{settings.source_vertical_datum.code}, so there is no "
                f"input height its separations can honestly combine with - "
                f"an ellipsoid height built from the two would mix eras "
                f"inside one number (DESIGN.md #32). State an input-side "
                f"model published for "
                f"{settings.source_vertical_datum.code} heights, or none."
            )

    if transformation is not None and settings.geoid_model is not None:
        # Plan section 3.5's fourth refusal, WIDENED at the WP-V6 review gate
        # (DESIGN.md #41, superseding the plan's target-datum-only rule): the
        # geoid model's datum must match EITHER endpoint of the vertical
        # conversion, because the factors are computed from the height in the
        # model's own era - the shifted height when the target matches, the
        # source height when the source does (_convert_row). The plan's rule
        # would have refused NAVD88 -> NGVD29 outright, dead-ending WP-V8's
        # dropdowns for every NGVD 29 target with advice no interface offers;
        # under this rule both modeled directions carry a NAVD 88 leg and
        # work with both shipped models, and the era mixing #32 forbids never
        # happens. What still refuses: a pair whose endpoints BOTH differ
        # from the model's datum - today, only an NGVD29 -> NGVD29 identity
        # job with a geoid model attached, where no NAVD 88 height exists at
        # any stage. After the job's own geoid_model guards above, so a geoid
        # impostor is still refused by the job's own message first.
        model = settings.geoid_model
        endpoint_codes = {
            settings.source_vertical_datum.code,
            settings.target_vertical_datum.code,
        }
        if model.vertical_datum.code not in endpoint_codes:
            raise geoid.GeoidError(
                f"The {model.name} geoid model publishes separations for "
                f"heights in {model.vertical_datum.code}, but no stage of "
                f"this job's elevations is in that datum "
                f"({settings.source_vertical_datum.code} -> "
                f"{settings.target_vertical_datum.code}), so there is no "
                f"height the model's separations can honestly combine with - "
                f"an elevation factor built from the two would mix eras "
                f"inside one number (DESIGN.md #32). Run this job in "
                f"horizontal mode, which converts the coordinates and "
                f"carries the elevation through unchanged, or convert the "
                f"elevations to {model.vertical_datum.code} in a job that "
                f"targets it."
            )

    # ------------------------------------------------------------------
    # Ellipsoid input's refusals, all before any point converts (the owner's
    # feature, 2026-08-11). They sit here, after the geoid-model guards
    # above, so a model impostor is still refused by its own message first
    # and these never fire on a nonsense record.
    # ------------------------------------------------------------------
    if not isinstance(settings.input_height_kind, HeightKind):
        raise TypeError(
            f"JobSettings.input_height_kind must be a HeightKind stating what "
            f"the Z column holds; got "
            f"{type(settings.input_height_kind).__name__} "
            f"({settings.input_height_kind!r}). In particular True is not "
            f"'the ellipsoid one'."
        )

    if settings.input_height_kind is HeightKind.ELLIPSOID:
        ellipsoid_model = factors_geoid_model(settings, transformation)
        if ellipsoid_model is None:
            raise geoid.GeoidError(
                "This job states that its input heights are ELLIPSOID "
                "heights, but it carries no geoid model on either side. An "
                "ellipsoid height is measured from the GRS 80 ellipsoid; "
                "turning it into an elevation needs the geoid separation N at "
                "each point, and with no model there is none - so there is no "
                "orthometric height to compute, to write, or to build a "
                "factor from. Choose a geoid model, or state that the Z "
                "column holds orthometric heights."
            )

        if geoid_swap_models(settings, transformation) is not None:
            raise geoid.GeoidError(
                f"This job states ELLIPSOID input heights AND a geoid change "
                f"({settings.source_geoid_model.name} -> "
                f"{settings.geoid_model.name}). Those two cannot be combined, "
                f"and not because the arithmetic fails - because it makes the "
                f"input model meaningless. An ellipsoid height is on no geoid "
                f"model at all, so (h - N_in) + (N_in - N_out) is just "
                f"h - N_out: the input model cancels out and changes no "
                f"number this job produces, while every output would state a "
                f"conversion FROM {settings.source_geoid_model.name} of a "
                f"height that was never on it. State "
                f"{settings.geoid_model.name} on both sides to get "
                f"orthometric heights on {settings.geoid_model.name}."
            )

        if transformation is not None:
            source_code = settings.source_vertical_datum.code
            if ellipsoid_model.vertical_datum.code != source_code:
                raise geoid.GeoidError(
                    f"This job states ELLIPSOID input heights and an INPUT "
                    f"vertical datum of {source_code}. An ellipsoid height is "
                    f"measured from the GRS 80 ellipsoid and is in no "
                    f"vertical datum at all; the orthometric height this "
                    f"program derives from it is in the datum its geoid model "
                    f"publishes separations for - "
                    f"{ellipsoid_model.vertical_datum.code} for "
                    f"{ellipsoid_model.name} - so an input datum of "
                    f"{source_code} would label a "
                    f"{ellipsoid_model.vertical_datum.code} height as a "
                    f"{source_code} one before a single shift was applied. "
                    f"State {ellipsoid_model.vertical_datum.code} as the "
                    f"input vertical datum (and {source_code} as the OUTPUT "
                    f"datum if {source_code} elevations are what you need), "
                    f"or state that the Z column holds orthometric heights."
                )


    # The factors' grid: the one side whose height and separation share an
    # era (factors_geoid_model - output side preferred, else input side).
    # For every pre-existing call shape this is settings.geoid_model's own
    # grid, bit for bit: the #41-era NAVD88 -> NGVD29 shape normalizes its
    # model to the input side and this reads the same record back.
    factors_model = factors_geoid_model(settings, transformation)
    grid = (
        geoid.default_grid(factors_model) if factors_model is not None else None
    )

    # The geoid-to-geoid conversion's two grids, loaded once per job exactly
    # as the factors grid above is. None on every job that is not a swap -
    # including the same model stated on both sides, which is the ordinary
    # identity job with no swap step.
    swap_models = geoid_swap_models(settings, transformation)
    swap_grids = (
        _GeoidSwapGrids(
            source_model=swap_models[0],
            target_model=swap_models[1],
            source_grid=geoid.default_grid(swap_models[0]),
            target_grid=geoid.default_grid(swap_models[1]),
        )
        if swap_models is not None
        else None
    )

    # The VERTCON pair, loaded ONCE per job exactly as the geoid grid above is
    # - not per row (two 2.4 MB files re-read per point), and NOT for an
    # identity: an identity applies no grid, apply_shift refuses a grid value
    # for one, and a NAVD 88 to NAVD 88 job must succeed with the VERTCON
    # files absent entirely.
    vertcon_grids = (
        vertcon.default_grids()
        if transformation is not None and not transformation.is_identity
        else None
    )

    # The county polygons, read and authenticated once per process, and only
    # for an Auto job: a fixed-zone job never touches the county file, so it
    # converts with the file absent exactly as it always did.
    county_set = (
        county_file.default_counties() if settings.target_zone is AUTO_ZONE else None
    )

    points: list[ConvertedPoint] = []
    unplaced: list[_UnplacedPoint] = []
    for row in parsed.rows:
        try:
            points.append(
                _convert_row(
                    row,
                    settings,
                    grid,
                    transformation,
                    vertcon_grids,
                    swap_grids,
                    frame_path=frame_path,
                    epoch=epoch,
                    county_set=county_set,
                )
            )
        except _AutoZoneUnplaced as signal:
            # Collected, not skipped: the loop runs on only so the refusal
            # below can name EVERY row Auto cannot place, and then the whole
            # job is refused (the house rule; plan L5).
            unplaced.append(signal.point)
    if unplaced:
        raise _unplaced_points_refusal(unplaced, county_set)

    return JobResult(
        settings=settings,
        points=tuple(points),
        # The digest of the bytes the parser consumed, and nothing else. None
        # when the rows arrived already parsed - see JobResult.input_sha256.
        input_sha256=parsed.sha256,
        input_row_count=len(parsed.rows),
        skipped_blank_lines=parsed.skipped_blank_lines,
        # The NAME of the model the factors were actually computed from, not
        # the record: JobResult's contract predates the registry and
        # report.py resolves the record back through geoid_model_by_name.
        # For every pre-existing call shape this is settings.geoid_model's
        # own name; since the per-side feature it is the factors side's, so
        # a job whose only model is input-side (geoid_model=None,
        # source_geoid_model=GEOID18) names the grid its factors really
        # came from rather than claiming no geoid was applied.
        geoid_model=(
            factors_model.name if factors_model is not None else None
        ),
        job_warnings=job_warnings,
    )


@dataclass(frozen=True)
class _GeoidSwapGrids:
    """A swap job's two models with their loaded grids - run()'s per-job
    wiring, handed to ``_convert_row`` so the tiles are read once per job,
    not per row."""

    source_model: geoid.GeoidModel
    target_model: geoid.GeoidModel
    source_grid: object
    target_grid: object


def _stray_geodetic_to_geodetic_zone_message(
    settings: JobSettings, stray: list[str]
) -> str:
    """Why a zone on a geodetic-to-geodetic job is refused, not ignored.

    ``_stray_zone_message``'s rule, for the direction with no zone at either
    end: a zone the conversion never touches would still reach the job record,
    which derives its zone blocks from these settings.
    """
    named = " and ".join(
        f"{name}={getattr(settings, name).name} ({getattr(settings, name).code})"
        for name in stray
    )
    return (
        f"A {Direction.GEODETIC_TO_GEODETIC.name} job was given {named}, which "
        f"this direction never reads: the input and the output are both "
        f"latitudes and longitudes, so no zone is inverted or projected into. "
        f"The job record derives its zone blocks from these settings, not "
        f"from the conversion that ran, so it would print a block for a zone "
        f"that took no part in the job. Pass "
        f"{' and '.join(f'{name}=None' for name in stray)}."
    )


def _reads_geodetic_frame(settings: JobSettings) -> bool:
    """Whether this job's direction has a geodetic end, and so reads ``geodetic_frame``."""
    return settings.direction in (
        Direction.GEODETIC_TO_ZONE,
        Direction.ZONE_TO_GEODETIC,
        Direction.GEODETIC_TO_GEODETIC,
    ) or (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is None
    )


def _frame_label(frame: object) -> str:
    code = getattr(frame, "code", None)
    return code if isinstance(code, str) else repr(frame)


def _require_no_stray_frame_fields(settings: JobSettings) -> None:
    """Refuse a frame field this job's direction never reads, by name.

    The 0.7.0 closing gate's stray-zone MEDIUM, applied to the two frame
    fields (docs/PLAN-wgs84.md section 3.5, "from the lead's W2 probe";
    interim gate 1 of the WGS 84 build, finding I1). A ``ZONE_TO_ZONE`` job -
    or a ``VERTICAL_ONLY`` job reading State Plane coordinates - given a
    ``geodetic_frame`` of WGS84(G2296) runs, ignores it, and converts
    correctly; but the field is a statement about where the job's positions
    are, the job never made that statement true, and a later surface that
    printed it would describe a frame nothing was in. ``target_geodetic_frame``
    is read only by ``GEODETIC_TO_GEODETIC``.

    ``geodetic_frame`` is DEFAULTED to NAD83(2011), so the test is "differs
    from the default", in value: a caller that rebuilt the default record
    field for field has stated nothing. Both interface tabs already set the
    field only when a side is geodetic (``controls.geodetic_frame_for``), so
    this refuses nothing they build.
    """
    if (
        settings.direction is not Direction.GEODETIC_TO_GEODETIC
        and settings.target_geodetic_frame is not None
    ):
        raise ValueError(
            f"A {settings.direction.name} job was given target_geodetic_frame="
            f"{_frame_label(settings.target_geodetic_frame)}, which only a "
            f"{Direction.GEODETIC_TO_GEODETIC.name} job reads: this "
            f"direction's one geodetic end, if it has one, is geodetic_frame. "
            f"A second frame stated here would be one the job record could "
            f"print and the conversion never used. Pass "
            f"target_geodetic_frame=None."
        )
    if not _reads_geodetic_frame(settings) and settings.geodetic_frame != NAD83_2011:
        reading = (
            "both ends are zones"
            if settings.direction is Direction.ZONE_TO_ZONE
            else "the input is State Plane coordinates and nothing is written "
            "as latitude and longitude"
        )
        raise ValueError(
            f"A {settings.direction.name} job was given geodetic_frame="
            f"{_frame_label(settings.geodetic_frame)}, which this job never "
            f"reads: {reading}, and each zone carries its own frame. The "
            f"conversion would run in the zones' frame and ignore the field, "
            f"while the field states that this job's positions are in "
            f"{_frame_label(settings.geodetic_frame)} - a frame nothing in the "
            f"job is in. Refused here rather than ignored, as a stray zone is. "
            f"Leave geodetic_frame at its default, {NAD83_2011.code}."
        )


def _require_a_registered_frame_path(
    settings: JobSettings,
) -> FrameTransformation | None:
    """The frame path this job's rows will apply - or a refusal, before the file is read.

    ``convert.project_point``, ``convert.zone_to_geodetic`` and the other
    conversion functions each pass their own ends through
    ``frames.require_frame_path``, so a cross-frame job could never produce a
    wrong coordinate. What it could do before this gate existed is read the
    file, convert forty rows, and fail on the forty-first only because that is
    when the loop reached it - a whole-job refusal announced as though it were
    about one point. It is about the settings, so it fires here.

    The pair this checks is the one the settings alone can put in disagreement:
    ``geodetic_frame`` names the frame a geodetic END is in, and the zone (or
    the second geodetic frame) at the other end carries its own:

    * ``GEODETIC_TO_ZONE`` - the file's latitudes and longitudes are read as
      ``geodetic_frame`` and projected into ``target_zone``;
    * ``ZONE_TO_GEODETIC`` - ``source_zone``'s coordinates are inverted into
      the zone's own frame and written out in ``geodetic_frame``. A 2022-zone
      job left on the NAD83(2011) default refuses: there is no published
      NATRF2022 <-> NAD83(2011) path, and writing NATRF2022 positions under a
      NAD83(2011) label is one to two metres, invisible in the numbers;
    * ``GEODETIC_TO_GEODETIC`` - ``geodetic_frame`` to ``target_geodetic_frame``,
      and only across a registered NON-identity path (plan decision D7): the
      same frame at both ends converts nothing, and is refused rather than
      run as a conversion that changed no number;
    * ``VERTICAL_ONLY`` with a GEODETIC input - ``convert.pivot_path``: the
      frame's identity when it is plate-fixed, its HTDP path to NAD83(2011)
      when it is time-dependent (plan decision D8), and the bare WGS 84 label
      refused by name. Until the 0.7.0 closing gate this direction was skipped
      entirely, and a ``VERTICAL_ONLY`` job stating ``WGS84`` certified a NAVD
      88 elevation under a record reading "Reference frame WGS84". The same
      function is the per-point gate in ``convert.geodetic_position``
      (interim gate 1, finding L5), so the two cannot choose different paths.

    ``ZONE_TO_ZONE`` and ``VERTICAL_ONLY`` with a zone input are not checked
    here and return None: every end is a zone, and ``convert_point`` gates the
    pair itself.

    The refusal is ``frames``' own, raised by ``require_frame_path`` and
    propagated UNTOUCHED - it already names both frames, the metre-scale stake,
    NGS's unpublished transformation and the ways out, and wrapping it would
    hide the ``FrameMismatchError`` subclasses callers are told to catch.

    **Since work package W3 a registered path is an APPLIED one.** The record
    found here is returned, and ``run`` hands it to every row, so the
    observation date the path requires is decided from the same record the
    rows apply. It still passes ``convert.require_an_applicable_path``, the
    single point where a path whose method this program cannot run is
    refused - the W2 guard's successor.
    """
    if settings.direction is Direction.GEODETIC_TO_ZONE:
        # An Auto job's zones are all on its auto_frame (AUTO_FRAMES, checked
        # at import), so the pair is the input frame against that frame - the
        # same require_frame_path refusal a fixed zone on it would meet.
        target_frame = (
            settings.auto_frame
            if settings.target_zone is AUTO_ZONE
            else settings.target_zone.frame
        )
        path = require_frame_path(settings.geodetic_frame, target_frame)
    elif settings.direction is Direction.ZONE_TO_GEODETIC:
        path = require_frame_path(
            settings.source_zone.frame, settings.geodetic_frame
        )
    elif settings.direction is Direction.GEODETIC_TO_GEODETIC:
        path = require_frame_path(
            settings.geodetic_frame, settings.target_geodetic_frame
        )
        if path.is_identity:
            raise FrameTransformationUnavailableError(
                f"A {Direction.GEODETIC_TO_GEODETIC.name} job was given "
                f"{path.source.code} at both ends. Nothing would be converted: "
                f"every position would come back exactly as it went in, under "
                f"a record stating a conversion. Geodetic to geodetic exists "
                f"only across a frame transformation - a WGS 84 or ITRF frame "
                f"to or from {NAD83_2011.code} (docs/PLAN-wgs84.md decision "
                f"D7). To convert within {path.source.code}, choose a zone at "
                f"one end."
            )
    elif (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is None
    ):
        path = pivot_path(settings.geodetic_frame)
    else:
        return None

    return require_an_applicable_path(path)


def applied_frame_transformation(settings: JobSettings) -> FrameTransformation | None:
    """The frame transformation this job's rows applied, or None when none ran.

    THE one statement, for the outputs, of whether a job is TRANSFORMED - read
    by every surface W4 of the WGS 84 build made conditional (the job record's
    FRAME TRANSFORMATION block, the audit CSV's frame columns, the frame-aware
    sentences), so no surface can decide it differently. It is the record
    ``_require_a_registered_frame_path`` returns, which is the record ``run``
    hands every row: a non-identity HTDP path, or None for an identity and for
    a job with no geodetic end at all. Derived from the SETTINGS, not from the
    points, so an empty transformed job is still described as one.

    Called on the settings of a job that has run, so it cannot refuse; on
    settings that never ran it refuses exactly as ``run`` would.
    """
    path = _require_a_registered_frame_path(settings)
    if path is None or path.is_identity:
        return None
    return path


def is_zoneless(direction: Direction, source_zone) -> bool:
    """Whether a job of this direction and input zone has no State Plane zone.

    True for ``GEODETIC_TO_GEODETIC``, and for ``VERTICAL_ONLY`` on geodetic
    positions (``source_zone`` None). Such a job has no grid scale factor, no
    convergence and no combined factor - nothing to project through - so every
    zone-only statement about it is false.

    THE one statement of that rule (work package W5 of the WGS 84 build). It
    was a local in ``report.build_report``, where plan W4b introduced it to
    withhold the zone-only record sentences; the interface asks it too - the
    elevation hints that name the combined factor - so the two cannot drift.
    Takes the direction and the input zone rather than ``JobSettings`` because
    the interface asks it of a form that is not yet a job.
    """
    return direction is Direction.GEODETIC_TO_GEODETIC or (
        direction is Direction.VERTICAL_ONLY and source_zone is None
    )


def today() -> datetime.date:
    """The day this job runs, for the observation date's future-date check.

    THE one seam the suite controls (``monkeypatch.setattr(job, "today",
    ...)``); nothing else in the program reads a clock for this. It is the
    LATER of the local date and the UTC date: HTDP's calendar entry means
    00:00 UTC (``htdp.f:7879-7880``), and a GNSS processor dates an
    observation in UTC, so a Michigan evening session is already tomorrow's
    date in UTC. Taking the later of the two means a date that is today in
    either clock is never refused as being in the future, and a date after
    both still is.

    The two clocks are read through ``_local_and_utc_dates``, so the suite can
    set them apart and pin the "later of the two" rule itself (interim gate 2,
    finding L1): in a UTC container they are one clock, and west of UTC -
    Michigan - the later is UTC, so no test of ``today`` against the local
    date alone can tell ``max`` from ``min``.
    """
    local, utc = _local_and_utc_dates()
    return max(local, utc)


def today_local() -> datetime.date:
    """The LOCAL calendar date this job runs - what "today" means as an observation date.

    Plan L10: an ``ObservationDateSource.TODAY`` date is the date the job ran
    in Michigan, not ``today``'s later-of-local-and-UTC, which exists only so
    a date that is today in either clock is never refused as being in the
    future. A Michigan evening job is already tomorrow in UTC; recording
    that as "the date the job ran" would be a false sentence. Read through
    ``_local_and_utc_dates`` so the suite can set the two clocks apart.
    """
    local, _utc = _local_and_utc_dates()
    return local


def _local_and_utc_dates() -> tuple[datetime.date, datetime.date]:
    """``(local date, UTC date)`` now: ``today``'s two clocks, and nothing else."""
    return (
        datetime.date.today(),
        datetime.datetime.now(datetime.timezone.utc).date(),
    )


def _time_dependent_frames_read(
    settings: JobSettings, frame_path: FrameTransformation | None
) -> tuple[ReferenceFrame, ...]:
    """The time-dependent frames this job's path actually reads - the registry's records.

    Read from the path ``_require_a_registered_frame_path`` returned, never
    from the settings' own records: the path's two ends are the registry's,
    so whether a frame is time-dependent is asked where the registry states
    it (interim gate 1, finding L4). A job with no path (zone-only) reads no
    geodetic frame at all.
    """
    if frame_path is None:
        return ()
    ends = (frame_path.source,) if frame_path.is_identity else (
        frame_path.source,
        frame_path.target,
    )
    return tuple(end for end in ends if end.is_time_dependent)


def _require_the_observation_date(
    settings: JobSettings, frame_path: FrameTransformation | None
) -> tuple[htdp.ObservationEpoch | None, tuple[ConversionWarning, ...]]:
    """The job's observation epoch and its job-level warnings, or a refusal.

    Plan decisions D9 and D10, all before the file is read:

    * the type: a ``datetime.date`` and nothing else. A ``datetime.datetime``
      IS a ``datetime.date`` to Python and is refused by name, because HTDP's
      calendar entry has no time of day and the time would be dropped without
      a word;
    * required when the path reads a time-dependent frame, refused by name
      when it does not (the stray-field class);
    * not after the day the job runs (``today``): an observation cannot be in
      the future, and HTDP would compute one without complaint;
    * HTDP's own year rule (``htdp.ObservationEpoch``: after 1906, within its
      minute clock), refused in HTDP's words;
    * a WARNING, not a refusal, when the date falls OUTSIDE the stated WGS 84
      realization's period of use (``frames.realization_period_of_use``,
      derived from the one table of start dates: each period ends the day
      before the next realization began). Reprocessed data can legitimately
      carry a later realization than the one broadcast that day, and software
      can keep labelling with an older one. No warning for
      ITRF, which has no NGA period of use. Raised once for the job
      (``JobResult.job_warnings``), because one date covers every point.
      Worded per direction: on a path INTO NAD83(2011) the realization is the
      input's label, on a path OUT of it the output the job was asked for
      (interim gate 2, finding L2).
    """
    date = settings.observation_date
    if date is not None and (
        isinstance(date, datetime.datetime) or not isinstance(date, datetime.date)
    ):
        raise TypeError(
            f"JobSettings.observation_date must be a datetime.date - the "
            f"calendar date the positions were observed - and nothing else; "
            f"got {type(date).__name__} ({date!r}). "
            + (
                "A datetime carries a time of day, and HTDP's calendar entry "
                "means 00:00 UTC on the date, so the time would be dropped "
                "without a word. Pass its .date()."
                if isinstance(date, datetime.datetime)
                else "A decimal year or a string is not accepted: the date is "
                "converted the way HTDP converts a calendar date "
                "(docs/PLAN-wgs84.md section 1, the owner's decision 3)."
            )
        )

    source = settings.observation_date_source
    if source is not None and not isinstance(source, ObservationDateSource):
        raise TypeError(
            f"JobSettings.observation_date_source must be an "
            f"ObservationDateSource - TODAY or ENTERED - stating how the "
            f"observation date was obtained, or None; got "
            f"{type(source).__name__} ({source!r})."
        )

    read = _time_dependent_frames_read(settings, frame_path)
    if not read:
        if date is None and source is not None:
            raise ValueError(
                f"A {settings.direction.name} job was given "
                f"observation_date_source={source.name}, but no frame this "
                f"job reads is time-dependent, so it states no observation "
                f"date and there is no date whose source could be recorded. "
                f"A source stated for a job that used no date would put a "
                f"sentence about a date into a record of a conversion that "
                f"never read one. Pass observation_date_source=None."
            )
        if date is not None:
            raise ValueError(
                f"A {settings.direction.name} job was given observation_date="
                f"{date.isoformat()}, but no frame this job reads is "
                f"time-dependent, so no date enters any arithmetic: "
                + (
                    f"its positions are in {frame_path.source.code}, a "
                    f"plate-fixed frame published at its reference epoch."
                    if frame_path is not None
                    else "it reads and writes only State Plane coordinates."
                )
                + " A date stated for a job that used none would put an "
                f"observation epoch into a record of a conversion that never "
                f"read one. Pass observation_date=None."
            )
        return None, ()

    names = " and ".join(frame.code for frame in read)
    if date is None:
        raise ValueError(
            f"This job has positions in {names}, a time-dependent frame, at "
            f"one end, and was given no observation_date. In {names} a Michigan "
            f"point moves "
            f"about 17 mm a year against {NAD83_2011.code}, so the position "
            f"means nothing until the date it was observed is stated, and "
            f"there is no default date to assume. State the calendar date the "
            f"positions were observed (one date for the whole job, "
            f"docs/PLAN-wgs84.md decision D10)."
        )
    running = today()
    if date > running:
        raise ValueError(
            f"observation_date {date.isoformat()} is after the day this job "
            f"runs ({running.isoformat()}). An observation cannot be in the "
            f"future, and HTDP would compute a position for one without "
            f"complaint, moved by the plate motion of time that has not "
            f"passed (docs/PLAN-wgs84.md decision D9). Check the date."
        )
    if source is ObservationDateSource.TODAY:
        local = today_local()
        if date != local:
            raise ValueError(
                f"observation_date_source is TODAY, but observation_date is "
                f"{date.isoformat()} and the day this job runs is "
                f"{local.isoformat()} (the local calendar date). TODAY means "
                f"the date the job ran, so the two must be the same date: a "
                f"date carried over from an earlier session, or a UTC date "
                f"taken for the local one, would be recorded as the date the "
                f"job ran when it is not. State ENTERED for a date that was "
                f"typed, or pass today's local date."
            )
    epoch = htdp.ObservationEpoch(date)

    warnings: list[ConversionWarning] = []
    for frame in read:
        period = realization_period_of_use(frame)
        if period is None or period.contains(date):
            continue
        span = (
            f"from {period.first_day.isoformat()} to "
            f"{period.last_day.isoformat()} (NGA replaced it with "
            f"{period.succeeded_by} on "
            f"{(period.last_day + datetime.timedelta(days=1)).isoformat()})"
            if period.last_day is not None
            else f"from {period.first_day.isoformat()}, with no end yet"
        )
        when = (
            f"before NGA put {frame.code} into use"
            if date < period.first_day
            else f"after NGA had replaced {frame.code} with {period.succeeded_by}"
        )
        if frame is frame_path.source:
            # Into NAD83(2011): the realization is the one the INPUT is
            # labelled with, and the question is whether the label is right.
            # Worded for both tabs (closing gate of the WGS 84 build, finding
            # L3): the Single point tab has no file, and the realization is a
            # property of the positions however they arrived. The sentence
            # states what the period of use means - the realization in use on
            # the date - and no more: it once said "a receiver on that date
            # was not broadcasting it", and receivers broadcast nothing.
            why = (
                f"{when}, so {frame.code} was not the realization in use on "
                f"that date. "
                + (
                    "Reprocessed data can legitimately carry a later realization"
                    if date < period.first_day
                    else "Software can legitimately keep labelling output with "
                    "an older realization"
                )
            )
            message = (
                f"The positions are stated in {frame.code} and dated "
                f"{date.isoformat()}, outside {frame.code}'s period of use, "
                f"which is {span}. The date is {why}, so the job is converted "
                f"as stated - but positions labelled with the wrong "
                f"realization look exactly like this. Check which realization "
                f"the positions are in."
            )
        else:
            # Out of NAD83(2011): the input is NAD 83 and carries no
            # realization label at all; the realization is the OUTPUT the
            # job was asked for (interim gate 2, finding L2 - the one message
            # used to say the positions were "stated in" it).
            message = (
                f"This job writes its positions in {frame.code}, the "
                f"realization requested as its output, at the observation "
                f"date {date.isoformat()} - outside {frame.code}'s period of "
                f"use, which is {span}. The date is {when}, so {frame.code} "
                f"was not the realization in use on that date. The job is "
                f"converted as requested. Check that {frame.code} is the "
                f"realization wanted for positions observed on that date."
            )
        warnings.append(
            ConversionWarning(
                code=WarningCode.REALIZATION_OUTSIDE_PERIOD_OF_USE,
                message=message,
            )
        )
    return epoch, tuple(warnings)


def _require_a_convertible_ellipsoid_height_frame(settings: JobSettings) -> None:
    """Refuse an ELLIPSOID height in a frame with no path to the geoid models' frame.

    **The 0.7.0 closing gate's HIGH, generalized by plan decision D6.**
    ``H = h - N`` is arithmetic on two numbers that must be measured from the
    SAME ellipsoid, and which ellipsoid an ``h`` is measured from is a
    property of the reference frame. Every geoid model this program carries
    is an NGS HYBRID model, whose separations N are published against
    NAD 83(2011). So the rule is: the height's frame must have a registered
    path to NAD83(2011), because the height is carried along that path before
    N is subtracted - an identity for NAD83(2011) itself, HTDP for the WGS 84
    and ITRF frames (``_convert_row`` subtracts N from the NAD 83 h,
    ``PointConversion.pivot_ellipsoid_height``).

    **NATRF2022 still refuses, with its message unchanged.** Feed a hybrid
    model a height measured from the NATRF2022 ellipsoid and the subtraction
    silently mixes two realizations. The size of it is not a matter of
    opinion: at 43.0 N, 84.5 W the frozen NGS capture puts one physical point
    at 200.000 m above the NAD 83(2011) ellipsoid and 198.885 m above the
    NATRF2022 one, 1.115 m apart (``review/nsrs-n0/FINDINGS.md``). The
    reviewer's concrete job - a vertical-only job at zone 261008 with
    h = 198.885 m - escaped an elevation of 231.970 m NAVD 88 where the answer
    is 233.085 m. There is no published path to carry it, so it fails closed,
    here, with the other settings gates and before the file is read. Raised
    as ``FrameTransformationUnavailableError`` because that is what this is,
    and every caller already catches ``FrameMismatchError`` for it.

    **ORTHOMETRIC input on a 2022 zone is deliberately NOT caught.** An
    elevation is a height above the geoid, not above any frame's ellipsoid, so
    the job is honest and it keeps converting. The residual is real and
    recorded rather than hidden: the factors rebuild h as H + N in the NAD 83
    realization, which is ~0.175 ppm in the combined factor - the owner-accepted
    fact of docs/DESIGN.md #61, three orders below the 5.9 ppm the
    ellipsoid-height feature was built to correct.

    The message names no single model on purpose. The offending pairing is the
    frame against the whole registry, and this gate runs before the job's model
    records have been validated - so it states what is true of every model
    rather than reaching for one.
    """
    if settings.input_height_kind is not HeightKind.ELLIPSOID:
        return

    frame = _height_frame(settings)
    models = ", ".join(model.name for model in geoid.ALL_GEOID_MODELS)
    if frame.code == NATRF2022.code:
        raise FrameTransformationUnavailableError(
            f"This job states ELLIPSOID input heights and works in {frame.code}. "
            f"An ellipsoid height is measured from the ellipsoid of one "
            f"particular realization, and the two realizations do not put it in "
            f"the same place: at 43.0 N, 84.5 W one physical point is 200.000 m "
            f"above the {NAD83_2011.code} ellipsoid and 198.885 m above the "
            f"{frame.code} one - 1.115 m apart (frozen NGS capture, "
            f"review/nsrs-n0/FINDINGS.md). Every geoid model this program carries "
            f"({models}) publishes its separations N against {NAD83_2011.code}, "
            f"so H = h - N computed from a {frame.code} height is out by that "
            f"1.115 m - a metre-scale elevation wearing a vertical datum's label, "
            f"with nothing in the number to show it. Moving the height between "
            f"the realizations needs the {NAD83_2011.code} <-> {frame.code} "
            f"transformation, and NGS has not published one "
            f"(docs/DEFERRED-NATRF2022-BRIDGE.md, docs/DESIGN.md amendment #62). "
            f"Two ways on: state that the Z column holds ORTHOMETRIC elevations - "
            f"an elevation is a height above the geoid, not above a frame's "
            f"ellipsoid, and every 2022 zone converts one today - or wait, as the "
            f"cross-frame conversions do, for NGS to publish the transformation."
        )

    # Every other frame: the rule itself. Only NATRF2022 can fail it among
    # settings the frame gate has already accepted, but it is asked of the
    # registry rather than assumed, so a frame added later without a path to
    # NAD83(2011) refuses here too instead of reaching H = h - N.
    try:
        require_frame_path(frame, NAD83_2011)
    except FrameMismatchError as refusal:
        raise FrameTransformationUnavailableError(
            f"This job states ELLIPSOID input heights in "
            f"{_frame_label(frame)}, and there is no registered path from "
            f"{_frame_label(frame)} to {NAD83_2011.code}, the frame every "
            f"geoid model this program carries ({models}) publishes its "
            f"separations N against. H = h - N needs h and N measured from "
            f"the same ellipsoid, so with no way to carry the height to "
            f"{NAD83_2011.code} there is no orthometric height to compute. "
            f"The frame registry's reason: {refusal}"
        ) from None


def _require_units_the_zones_publish(settings: JobSettings) -> None:
    """Refuse a unit the zone's own publishing authority does not define.

    ``Zone.allowed_units`` is the authoritative statement of what a coordinate
    in that zone may be written in, and this is the gate that enforces it on a
    job. It is the authoritative half of the owner's units decision; the
    interface's own filtering is a convenience over the same tuple, and a
    filter that a caller can bypass is not a rule.

    **Which unit governs which end**, decided here and stated rather than left
    to the reader, because the two units do not both govern coordinates in
    every direction:

    * ``ZONE_TO_ZONE`` - ``input_unit`` governs the source zone's coordinates
      and ``output_unit`` the target zone's. Both ends checked.
    * ``ZONE_TO_GEODETIC`` - ``input_unit`` governs the source zone's
      coordinates. The output columns are degrees; ``output_unit`` governs only
      the Z column, and an elevation is not a coordinate in the zone's grid, so
      there is no zone for it to be checked against. Source end only.
    * ``GEODETIC_TO_ZONE`` - the mirror: ``output_unit`` governs the target
      zone's coordinates, ``input_unit`` governs only the input Z column.
      Target end only. (``source_zone`` is unread by this direction; it is not
      checked, because checking it would refuse a job over a field that
      changes no number.)
    * ``VERTICAL_ONLY`` - the input system is ``source_zone``, or None for
      geodetic input, and the exports mirror the input columns. The units are
      already required to be equal by the block in ``run``, so checking
      ``input_unit`` against the input zone checks both.

    The refusal names the zone, the unit, the units the zone does publish, and
    the authority - NGS publishes every SPCS2022 false origin in metres and
    international feet only, and beta NCAT prints ``N/A`` for the US survey
    foot on every 2022 zone. The survey foot is 2 ppm from the international
    foot, about 26 feet at a four-million-metre easting, and a coordinate
    written in it could be checked against no published NGS figure.
    """
    ends: list[tuple[str, Zone, LinearUnit]] = []

    if settings.direction is Direction.ZONE_TO_ZONE:
        ends.append(("source", settings.source_zone, settings.input_unit))
        ends.append(("target", settings.target_zone, settings.output_unit))
    elif settings.direction is Direction.ZONE_TO_GEODETIC:
        ends.append(("source", settings.source_zone, settings.input_unit))
    elif settings.direction is Direction.GEODETIC_TO_ZONE:
        if settings.target_zone is AUTO_ZONE:
            _require_a_unit_every_auto_zone_publishes(settings)
        else:
            ends.append(("target", settings.target_zone, settings.output_unit))
    elif settings.direction is Direction.VERTICAL_ONLY:
        if settings.source_zone is not None:
            ends.append(("source", settings.source_zone, settings.input_unit))

    for label, zone, unit in ends:
        if unit in zone.allowed_units:
            continue
        allowed = ", ".join(f"{u.code} ({u.name})" for u in zone.allowed_units)
        # The SPCS2022 sentence is stated only for an SPCS2022 zone. Every
        # refusal this gate can raise today IS one - the SPCS 83 zones carry
        # all three units - but a message that explained a 2022 restriction on
        # some other system's zone would be a false sentence in a refusal, the
        # class this project has repeatedly had to go back and delete.
        if zone.system == "SPCS2022":
            authority = (
                " NGS publishes every SPCS2022 zone's false origin in metres "
                "and international feet only, and NCAT prints N/A for the US "
                "survey foot on every one of them; the survey foot is 2 ppm "
                "from the international foot, about 26 feet at a "
                "four-million-metre easting, so a coordinate written in it "
                "could be checked against no published figure."
            )
        else:
            authority = ""
        raise ValueError(
            f"{zone.name} ({zone.system}) does not publish coordinates in "
            f"{unit.name} ({unit.code}), so this job's {label} unit cannot be "
            f"used for it. {zone.system} zones may be read and written in: "
            f"{allowed}.{authority} The zone's authority: {zone.citation}."
        )


def _require_a_unit_every_auto_zone_publishes(settings: JobSettings) -> None:
    """The unit gate for an Auto job: the output unit against EVERY zone Auto can choose.

    Before the file is read, so the answer cannot depend on which zones the
    file's points happen to land in: a job that would write one point in US
    survey feet in an SPCS2022 zone is refused whole, as a fixed-zone job on
    that zone is (recon section 7 item 7 - the gate an Auto job would
    otherwise skip silently). The zones are ``autozone.zones_choosable``,
    read from the county tables ``zone_for`` itself reads.
    """
    system = auto_zone_system(settings.auto_frame)
    zones = zones_choosable(system)
    unit = settings.output_unit
    refusing = [zone for zone in zones if unit not in zone.allowed_units]
    if not refusing:
        return
    allowed = [
        u for u in zones[0].allowed_units if all(u in z.allowed_units for z in zones)
    ]
    allowed_text = ", ".join(f"{u.code} ({u.name})" for u in allowed)
    named = ", ".join(f"{zone.name} ({zone.code})" for zone in refusing)
    if system is AutoZoneSystem.SPCS2022:
        authority = (
            " NGS publishes every SPCS2022 zone's false origin in metres and "
            "international feet only, and NCAT prints N/A for the US survey "
            "foot on every one of them; the survey foot is 2 ppm from the "
            "international foot, so a coordinate written in it could be "
            "checked against no published figure."
        )
    else:
        authority = ""
    raise ValueError(
        f"Auto zone in {settings.auto_frame.code} chooses each point's zone "
        f"among the {len(zones)} {system.value} zones it can assign, and "
        f"{len(refusing)} of them do not publish coordinates in {unit.name} "
        f"({unit.code}): {named}. This job's target unit cannot be used, "
        f"because a point landing in one of those zones would be written in "
        f"a unit its zone does not define. Auto {system.value} jobs may be "
        f"written in: {allowed_text}.{authority} The zones' authority: "
        f"{refusing[0].citation}."
    )


def _require_vertical_settings(
    settings: JobSettings,
) -> VerticalTransformation | None:
    """The vertical transformation this job will apply per point, or None.

    Every settings-level vertical refusal, in one place, before any point
    converts (docs/PLAN-vertical-datums.md section 3.5):

    * a vertical job missing either datum - refused naming which, in the style
      of the longitude-convention refusal;
    * a HORIZONTAL job SUPPLIED with either datum - refused too: a datum
      handed to a job that will never apply or record it is a contradiction,
      and silently ignoring it would let a caller believe an elevation
      conversion happened (the mirror of longitude_convention's None-is-a-
      statement rule);
    * a non-``VerticalDatum`` in either field - the #11-finding-1 impostor
      class, refused by name exactly as ``geoid_model`` is beside it;
    * ``require_vertical_pair``'s own two refusals (a datum declared but not
      usable; a pair with no published transformation) propagate UNTOUCHED -
      they already name the offending datum and teach, and wrapping them
      would hide the classes ``spc.vertical`` tells callers to catch.
    """
    mode = settings.vertical_mode
    if not isinstance(mode, VerticalMode):
        # The #11-finding-1 class for this field: `vertical_mode=True` is the
        # habit a boolean toggle teaches, and `is` comparison would silently
        # treat any impostor as a mode nobody chose. if/raise, never assert.
        raise TypeError(
            f"JobSettings.vertical_mode must be a michspc.job.VerticalMode; "
            f"got {type(mode).__name__} ({mode!r}). In particular True is "
            f"not 'vertical on': an impostor compares unequal to every "
            f"member and would be treated as whichever branch its identity "
            f"check happened to miss. Pass VerticalMode.HORIZONTAL, "
            f"VerticalMode.HORIZONTAL_AND_VERTICAL, or "
            f"VerticalMode.VERTICAL."
        )

    # VERTICAL and VERTICAL_ONLY require each other, in both directions.
    # A vertical-only direction under any other mode either converts nothing
    # (HORIZONTAL) or promises a horizontal conversion this direction does
    # not perform; a VERTICAL mode on any other direction would silently
    # decide whether that job's coordinates move. Refused rather than
    # reconciled, in the style of the rest of this matrix.
    if (
        settings.direction is Direction.VERTICAL_ONLY
        and mode is not VerticalMode.VERTICAL
    ):
        raise ValueError(
            f"This job's direction is "
            f"{Direction.VERTICAL_ONLY.value!r} but its vertical_mode is "
            f"{mode.value!r}. A vertical-only job performs exactly one "
            f"conversion - the vertical datum shift - and the two fields "
            f"must state it together: Direction.VERTICAL_ONLY with "
            f"VerticalMode.VERTICAL. Any other mode either converts no "
            f"elevation or claims a horizontal conversion this direction "
            f"does not perform, so guessing which the caller meant would "
            f"decide what happens to every coordinate in the job."
        )
    if (
        mode is VerticalMode.VERTICAL
        and settings.direction is not Direction.VERTICAL_ONLY
    ):
        raise ValueError(
            f"This job's vertical_mode is {VerticalMode.VERTICAL.value!r} "
            f"but its direction is {settings.direction.value!r}. "
            f"VerticalMode.VERTICAL converts elevations and nothing else, so "
            f"it pairs only with Direction.VERTICAL_ONLY; a job that also "
            f"converts coordinates states "
            f"VerticalMode.HORIZONTAL_AND_VERTICAL."
        )

    fields = (
        ("source_vertical_datum", settings.source_vertical_datum),
        ("target_vertical_datum", settings.target_vertical_datum),
    )
    for label, datum in fields:
        if datum is not None and not isinstance(datum, VerticalDatum):
            raise TypeError(
                f"JobSettings.{label} must be a michspc.spc.vertical."
                f"VerticalDatum record, or None to state that this job does "
                f"not consult a vertical datum; got {type(datum).__name__} "
                f"({datum!r}). Every record in this program's core carries "
                f"code, name and citation, so a zone, a reference frame or a "
                f"geoid model duck-types a long way before failing on an "
                f"attribute nobody catches (docs/DESIGN.md amendment #11, "
                f"finding 1). Pass michspc.spc.vertical.NGVD29 or NAVD88."
            )

    if mode is VerticalMode.HORIZONTAL:
        supplied = [label for label, datum in fields if datum is not None]
        if supplied:
            names = " and ".join(supplied)
            verb = "were" if len(supplied) > 1 else "was"
            raise ValueError(
                f"This job is horizontal-only, but {names} {verb} supplied. "
                f"A horizontal job never applies or records a vertical "
                f"datum, so accepting one would let a caller believe an "
                f"elevation conversion happened when none did - an "
                f"unconverted height wearing a datum tag is exactly the "
                f"ordinary-looking wrong number this program refuses. Set "
                f"vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL to "
                f"convert elevations, or state None for both datums."
            )
        return None

    missing = [label for label, datum in fields if datum is None]
    if missing:
        names = " and ".join(missing)
        verb = "were" if len(missing) > 1 else "was"
        raise ValueError(
            # mode.value spells the job: "horizontal and vertical" or
            # "vertical". One raise for both modes - the same code path on
            # purpose, so the two cannot come to refuse differently.
            f"A {mode.value} job needs both vertical datums, and "
            f"{names} {verb} not stated. Neither has a default: NGVD 29 and "
            f"NAVD 88 heights differ by up to 0.41 m across Michigan while "
            f"looking identical, so assuming a datum would silently relabel "
            f"every elevation in the job. Pass michspc.spc.vertical.NGVD29 "
            f"or NAVD88 for each."
        )

    return require_vertical_pair(
        settings.source_vertical_datum, settings.target_vertical_datum
    )


def _require_transformation_matches_settings(
    transformation: VerticalTransformation, settings: JobSettings
) -> None:
    """The datum tag is CHECKED, not carried (DESIGN.md #36 reviewer note).

    ``apply_shift`` takes a bare float, so nothing downstream could notice a
    transformation looked up for one pair of datums being applied to a job
    that stated another - the shifted height would look entirely ordinary.
    ``run`` passes down the record ``require_vertical_pair`` returned for the
    settings' own datums; this holds that wiring at the point of use, by
    ``code``, the rule the registry itself resolves by. if/raise, never
    assert: the suite and the shipped program run under -O.
    """
    stated_source = settings.source_vertical_datum
    stated_target = settings.target_vertical_datum
    source_code = stated_source.code if stated_source is not None else None
    target_code = stated_target.code if stated_target is not None else None
    if (
        transformation.source.code != source_code
        or transformation.target.code != target_code
    ):
        raise ValueError(
            f"The vertical transformation applied to this row converts "
            f"{transformation.source.code} -> {transformation.target.code}, "
            f"but the job's settings state {source_code} -> {target_code}. "
            f"Applying it would move every elevation between datums nobody "
            f"chose, and nothing downstream could tell: the shift is a bare "
            f"number and the shifted height looks ordinary. The record must "
            f"be the one require_vertical_pair returned for the settings' "
            f"own datums."
        )


def _require_geodetic_in_range(
    latitude: float,
    longitude: float,
    longitude_as_written: float,
    settings: JobSettings,
    context: str,
) -> None:
    """Refuse a latitude or longitude no signed geodetic position can carry.

    Placed here - the single entry point where the file's longitude sign
    convention is applied - rather than left to the core, so the refusal can
    name the row, the value as the file wrote it, and the convention in
    force, none of which ``lambert._require_valid_geodetic`` (which guards
    the same domain and still runs after this) can see.

    Recorded against DESIGN.md #38's note to WP-V6: the NGS grid readers
    accept 0-360 east longitudes silently - ``to_east_longitude`` adjusts
    only negatives, so ``shift_m(43.0, 275.5)`` equals
    ``shift_m(43.0, -84.5)`` byte-identically. Through ``job.run`` the
    horizontal conversion's own domain gate already refused such a value
    before any grid was consulted; this refusal keeps that property stated
    at the boundary that owns it instead of inherited from the projection's
    internals, and says which ROW is wrong, which a file of thousands of
    points needs.

    The bounds are the core's exactly - latitude strictly inside (-90, 90),
    longitude within [-180, 180] - so no value can pass here and refuse
    there, or the reverse. NaN fails both comparisons and is refused too.
    """
    convention = settings.longitude_convention.value
    if not (-90.0 < latitude < 90.0):
        raise ValueError(
            f"{context}: the latitude column reads {latitude!r}, which is "
            f"not a geodetic latitude - it must lie strictly between -90 and "
            f"90 degrees. Check that the file's second column really holds "
            f"latitudes in decimal degrees, and that the latitude and "
            f"longitude columns are not swapped. Refused rather than "
            f"converted, because a coordinate computed from it would look "
            f"ordinary and be meaningless."
        )
    if not (-180.0 <= longitude <= 180.0):
        advice = (
            f"Subtract 360 from it ({longitude - 360.0:.6f} here), or export "
            f"the file again with signed longitudes."
            if 180.0 < longitude < 360.0
            else "Correct the file, or the convention selected for it."
        )
        raise ValueError(
            f"{context}: the longitude column reads {longitude_as_written!r}, "
            f"which under the '{convention}' convention this job states is a "
            f"signed longitude of {longitude!r} - outside the -180 to 180 "
            f"range a signed longitude can have. A value between 180 and 360 "
            f"is the 0-360 EAST convention, which this program deliberately "
            f"does not read from a file: 275.5 east and -84.5 both name the "
            f"same meridian, and the NGS grid files use 0-360 internally, so "
            f"an unconverted 0-360 longitude would look up plausible geoid "
            f"and VERTCON values while the State Plane conversion placed the "
            f"point thousands of kilometres away. " + advice
        )


def per_side_geoid_models(
    settings: JobSettings, transformation: VerticalTransformation | None
) -> tuple[geoid.GeoidModel | None, geoid.GeoidModel | None]:
    """``(input-side model, output-side model)`` for this job, normalized.

    THE one statement of the per-side pairing (the owner's feature,
    2026-08-09), read by the computation, the factors rule, the swap
    detection and the record, so no two of them can pair differently.

    The normalization SUPERSEDES DESIGN.md #41's either-endpoint contortion
    by generalization: each side's model must match its own side's datum.
    The one pre-existing call shape that put a source-era model in
    ``geoid_model`` - a modeled transformation whose SOURCE datum is the
    model's era but whose target is not (NAVD88 -> NGVD29 with GEOID18, the
    configuration #41 widened the rule for) - is treated as the input-side
    model here, so every #41-era caller keeps working, its factors and
    outputs bit-identical, and ``factors_use_source_era`` becomes a
    consequence of the pairing rather than a parallel rule.
    """
    source_model = settings.source_geoid_model
    output_model = settings.geoid_model
    if (
        transformation is not None
        and not transformation.is_identity
        and output_model is not None
        and source_model is None
        and output_model.vertical_datum.code == transformation.source.code
        and output_model.vertical_datum.code != transformation.target.code
    ):
        return output_model, None
    return source_model, output_model


def factors_geoid_model(
    settings: JobSettings, transformation: VerticalTransformation | None
) -> geoid.GeoidModel | None:
    """The model this job's factors are computed from, or None.

    The side whose height and separation share an era: the OUTPUT side where
    it has a model - the factors then describe the height the Z column
    carries - else the INPUT side, else no model at all (the factors read
    N/A). One statement, shared by ``run``, the record and the audit CSV's
    "Geoid model" column, so they cannot name different grids.
    """
    source_model, output_model = per_side_geoid_models(settings, transformation)
    return output_model if output_model is not None else source_model


def geoid_swap_models(
    settings: JobSettings, transformation: VerticalTransformation | None
) -> tuple[geoid.GeoidModel, geoid.GeoidModel] | None:
    """``(input model, output model)`` when this job converts BETWEEN geoid
    models, else None.

    A geoid-to-geoid conversion is exactly: an identity vertical
    transformation (the datum does not change) with a model stated on each
    side and the two models different. The same model on both sides is the
    ordinary identity job - no swap step, no record - and a modeled
    transformation with both sides stated was refused before any point
    converted (``run``'s compound-job refusal).
    """
    if transformation is None or not transformation.is_identity:
        return None
    source_model, output_model = per_side_geoid_models(settings, transformation)
    if source_model is None or output_model is None:
        return None
    if source_model == output_model:
        return None
    return source_model, output_model


def factors_use_source_era(
    settings: JobSettings, transformation: VerticalTransformation | None
) -> bool:
    """Whether this job's factors are computed from the SOURCE-datum height.

    The #41 either-endpoint rule's one configuration where the factors do not
    use the height the Z column carries - now a CONSEQUENCE of the per-side
    pairing (``per_side_geoid_models``): the factors follow the one side
    that has a model, and on a modeled transformation only the input side
    can honestly hold one whose era is the source datum's. Stated once and
    called from both the computation (``_convert_row``) and the record
    (``report.py``'s Factor height paragraph), so the sentence and the
    arithmetic cannot drift apart (WP-V7 review gate, LOW 2; one
    authoritative representation per fact).
    """
    if transformation is None or transformation.is_identity:
        return False
    source_model, output_model = per_side_geoid_models(settings, transformation)
    return output_model is None and source_model is not None


def _transform_height(
    settings: JobSettings,
    frame_path: FrameTransformation | None,
    elevation_m: float | None,
) -> TransformHeight | None:
    """What HTDP is handed for this row, or None on a path that runs no HTDP.

    Plan decision D6, one rule per case: a blank or exactly-zero Z - the
    reader's "not recorded" (``pnezd``), which arrives here as None - is
    NOT_RECORDED and is transformed at h = 0; an ELLIPSOID Z is transformed
    with the position; an ORTHOMETRIC Z is handed in place of h and passes
    unchanged. ``elevation_m`` is metres, the file's own Z.
    """
    if frame_path is None or frame_path.is_identity:
        return None
    if elevation_m is None:
        return TransformHeight(HeightConvention.NOT_RECORDED, None)
    if settings.input_height_kind is HeightKind.ELLIPSOID:
        return TransformHeight(HeightConvention.ELLIPSOID, elevation_m)
    return TransformHeight(HeightConvention.ORTHOMETRIC, elevation_m)


def written_geodetic_position(conversion: PointConversion) -> tuple[float, float]:
    """The latitude and longitude a job with a geodetic OUTPUT writes, signed.

    The position in the frame the path ENDS in: the WGS 84 or ITRF position
    when the path carries the pivot out to one (``external_position``), the
    NAD 83 pivot otherwise - including every same-frame job, whose columns are
    the pivot exactly as before. Writing the pivot under a WGS 84 job's label
    is the silent pass-through the W2 guard existed to stop.

    Public since work package W4, because it is also the position the
    geodetic exports STATE: ``exports`` builds the DMS sibling from it and
    every verifier checks the written files against it, so the file layer and
    the conversion cannot come to mean different positions by "the target"
    (docs/PLAN-wgs84.md section 3.6, the verifier hazard).
    """
    path = conversion.frame_transformation
    if path is not None and path.target.is_time_dependent:
        external = conversion.external_position
        return external.latitude, external.longitude
    return conversion.latitude, conversion.longitude


def _unconverted_ellipsoid_z_sentence(conversion: PointConversion) -> str:
    """What a horizontal job's Z holds when no geoid separation could be read."""
    if conversion.is_transformed:
        return (
            f"The Z column carries the ellipsoid height transformed with the "
            f"position into {conversion.frame_transformation.target.code}, not "
            f"converted to an elevation, and the elevation and combined "
            f"factors read "
        )
    return (
        "The Z column carries the ellipsoid height as supplied, unconverted, "
        "and the elevation and combined factors read "
    )


def _point_named_htdp_refusal(
    error: htdp.HtdpRefusal,
    context: str,
    settings: JobSettings,
    frame_path: FrameTransformation | None,
    geodetic_input: bool,
) -> htdp.HtdpRefusal:
    """An HTDP refusal raised for one row, restated for that row.

    Interim gate 2 of the WGS 84 build, finding L4: through ``job.run`` the
    velocity-window refusal named no point - one bad row refused a whole
    file with nothing to find it by - and on a path out of NAD 83 it labelled
    the NAD83(2011) pivot with the target frame and advised checking a
    longitude sign the file never held. The frame is now the position's own
    (the path's SOURCE end, the position ``convert`` hands HTDP in either
    direction), the point is named, and the advice is the one that applies
    to where the position came from: the file's longitude convention on a
    geodetic input, the zone and unit on a grid input.

    **The type is kept**: a ``HtdpVelocityGridError`` comes back as one, and
    every other ``HtdpRefusal`` as its own class, with this row's context
    prefixed. Chosen over wrapping in ``ValueError`` (which the per-row
    refusals around it raise) because every caller that already catches the
    HTDP family - by ``HtdpRefusal`` or by the subclass - keeps catching it,
    and a refusal of the TRANSFORMATION stays distinguishable from a refusal
    of the file's contents. The cost, recorded for W5: ``HtdpRefusal``
    subclasses neither ``ValueError`` nor ``FrameMismatchError``, so the GUI
    must catch it explicitly. Both tabs catch ``Exception`` around
    ``job.run`` today and show its message in full, so nothing escapes; W5
    must keep it that way.
    """
    if (
        not isinstance(error, htdp.HtdpVelocityGridError)
        or error.reason is None
        or frame_path is None
        or frame_path.is_identity
        or error.position_frame != frame_path.source.htdp_frame.name
    ):
        # The defect-only node refusal, any other HTDP refusal, or a
        # position whose frame is not the one this function would name:
        # HTDP's own words, which name their own frame, with the point.
        return type(error)(f"{context}: {error}")
    frame = frame_path.source
    # Worded for BOTH tabs (closing gate of the WGS 84 build, finding L3).
    # The Single point tab reaches this refusal with a typed point, so the
    # sentences name no file. And on its DMS entry the hemisphere letter, not
    # the longitude convention, decides the sign, so the advice does not
    # presume the convention decided it: it asks for the signs to be checked
    # - the refused position above is printed signed, so a wrong one is
    # visible - and states the job's convention as the fact it is (the DMS
    # page composes its text in that convention too, ``fileio.dms``). Chosen
    # over telling the core how the point was typed: no computation reads the
    # entry form, and a settings field nothing computes from is the
    # stray-field class this module refuses elsewhere.
    if geodetic_input:
        origin = "the supplied position"
        advice = (
            f"Check that the point is in Michigan, and that its latitude and "
            f"longitude carry the right signs: this job reads longitudes "
            f"written {settings.longitude_convention.value}, and a latitude "
            f"or longitude whose sign is the wrong way round lands on the "
            f"other side of the world."
        )
    else:
        origin = (
            f"the position the {settings.source_zone.name} northing and "
            f"easting give"
        )
        advice = (
            f"Check that the point is in Michigan, and that the northing and "
            f"easting are {settings.source_zone.name} coordinates in "
            f"{settings.input_unit.code}."
        )
    return htdp.HtdpVelocityGridError(
        f"{context}: cannot transform {origin} - latitude "
        f"{error.latitude:.6f}, longitude {error.longitude:.6f} (signed, "
        f"negative west), in {frame.code} - to {frame_path.target.code}: "
        f"{error.reason} {advice}",
        latitude=error.latitude,
        longitude=error.longitude,
        position_frame=error.position_frame,
        reason=error.reason,
    )


def _unplaced_points_refusal(
    unplaced: list[_UnplacedPoint], county_set: CountySet
) -> AutoZoneUnplacedPointsError:
    """The whole-job refusal naming every row Auto could not place."""
    frame = unplaced[0].frame
    carried = unplaced[0].transformed_from
    via = (
        f" (each {carried.code} position as HTDP carried it there)"
        if carried is not None
        else ""
    )
    listed = "; ".join(
        f"point {p.point_id} at latitude {p.latitude:.8f}, longitude "
        f"{p.longitude:.8f} - {p.reason}"
        for p in unplaced
    )
    return AutoZoneUnplacedPointsError(
        f"Auto could not choose a zone for {len(unplaced)} point(s) of this "
        f"job, so nothing was converted. Positions tested, in "
        f"{frame.code}{via}: {listed}. No zone is assigned to a point in no "
        f"Michigan county ({county_set.source}, Great Lakes waters included), "
        f"and Auto never assigns the nearest zone or picks between two "
        f"counties that both claim a point. Check these coordinates, remove "
        f"the points from the file, or choose the zone yourself.",
        points=tuple((p.point_id, p.latitude, p.longitude) for p in unplaced),
        frame=frame,
    )


def _auto_zone_for(
    row: pnezd.PnezdRow,
    latitude: float,
    longitude: float,
    settings: JobSettings,
    county_set: CountySet | None,
    context: str,
    transform_arguments: dict,
) -> tuple[ZoneAssignment, tuple[float, float]]:
    """The zone Auto chooses for one point, and the position it was chosen at.

    Plan L4: the position is the point's own in the Auto frame - the input
    itself for NAD83(2011) or NATRF2022 input, and the NAD83(2011) pivot
    HTDP carries a WGS 84 or ITRF position to - found by
    ``convert.geodetic_position``, the function the vertical-only job reads
    its pivot with, through the same ``pivot_path``. Its frame is then
    required to BE the Auto frame (a second gate behind the settings' frame
    gate). A position in no county, or claimed by two, is signalled to
    ``run`` (``_AutoZoneUnplaced``), which collects every such row and then
    refuses the whole job; every other failure refuses the job at once.
    """
    if not isinstance(county_set, CountySet):
        raise TypeError(
            f"{context}: an Auto job converts only against the loaded county "
            f"set; got {type(county_set).__name__}."
        )
    position = geodetic_position(
        latitude, longitude, settings.geodetic_frame, context, **transform_arguments
    )
    if position.frame is not settings.auto_frame:
        raise FrameTransformationUnavailableError(
            f"{context}: Auto chooses zones in {settings.auto_frame.code}, but "
            f"this point's position is in {position.frame.code}, and no zone "
            f"is chosen from a position in another frame."
        )
    system = auto_zone_system(settings.auto_frame)
    try:
        assignment = zone_for(position.latitude, position.longitude, system, county_set)
    except (AutoZoneOutsideError, AutoZoneAmbiguousError) as error:
        if isinstance(error, AutoZoneAmbiguousError):
            claimed = ", ".join(
                f"{c.name} ({c.fips})"
                for c in county_set.containing(position.longitude, position.latitude)
            )
            reason = f"inside more than one county polygon ({claimed})"
        else:
            reason = "in no Michigan county"
        raise _AutoZoneUnplaced(
            _UnplacedPoint(
                point_id=row.point_id,
                latitude=position.latitude,
                longitude=position.longitude,
                frame=position.frame,
                reason=reason,
                transformed_from=(
                    settings.geodetic_frame if position.is_transformed else None
                ),
            )
        ) from error
    return assignment, (position.latitude, position.longitude)


def _convert_row(
    row: pnezd.PnezdRow,
    settings: JobSettings,
    grid,
    transformation: VerticalTransformation | None,
    vertcon_grids: vertcon.VertconGridPair | None,
    swap_grids: _GeoidSwapGrids | None = None,
    *,
    frame_path: FrameTransformation | None = None,
    epoch: htdp.ObservationEpoch | None = None,
    county_set: CountySet | None = None,
) -> ConvertedPoint:
    context = f"point {row.point_id}"
    warnings: list[ConversionWarning] = []
    auto_assignment: ZoneAssignment | None = None

    geodetic_input = settings.direction in (
        Direction.GEODETIC_TO_ZONE,
        Direction.GEODETIC_TO_GEODETIC,
    ) or (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is None
    )

    # The Z in metres, as the file states it - computed here, before the
    # conversion, because a frame transformation needs the height it is
    # handed (plan decision D6). Only its unit is touched; every rule below
    # about what the Z becomes is unchanged.
    elevation_m = (
        settings.input_unit.to_meters(row.elevation)
        if row.elevation is not None
        else None
    )
    transform_height = _transform_height(settings, frame_path, elevation_m)
    # Keyword arguments for the conversion call: an epoch and a height only
    # on a path that runs HTDP, and nothing at all on a same-frame one, whose
    # call is then exactly the call it always was.
    transform_arguments = (
        dict(epoch=epoch, height=transform_height)
        if transform_height is not None
        else {}
    )

    # An HTDP refusal names the point and the position's own frame, and
    # advises only what applies to where that position came from (interim
    # gate 2 of the WGS 84 build, finding L4): HTDP itself knows neither
    # the row nor whether its input was typed into the file or derived from
    # a grid coordinate.
    try:
        if geodetic_input:
            # The file's "northing" and "easting" columns hold latitude and
            # longitude. The longitude is normalised to the program's signed
            # convention here, at the boundary, and nowhere else.
            latitude = row.northing
            longitude = settings.longitude_convention.to_signed(row.easting)
            _require_geodetic_in_range(
                latitude, longitude, row.easting, settings, context
            )
            if settings.direction is Direction.GEODETIC_TO_ZONE:
                if settings.target_zone is AUTO_ZONE:
                    # Work package Z2: the zone is chosen from the position
                    # in the Auto frame - AFTER any HTDP transformation - and
                    # the point is then projected into it by exactly the call
                    # a fixed-zone job makes, so an Auto point is the
                    # fixed-zone point of its zone, field for field.
                    auto_assignment, chosen_at = _auto_zone_for(
                        row,
                        latitude,
                        longitude,
                        settings,
                        county_set,
                        context,
                        transform_arguments,
                    )
                    target_zone = auto_assignment.zone
                else:
                    target_zone = settings.target_zone
                conversion = project_point(
                    latitude,
                    longitude,
                    settings.geodetic_frame,
                    target_zone,
                    context,
                    **transform_arguments,
                )
                if auto_assignment is not None:
                    # The lead's ruling on Z2 finding 6: no OUTSIDE_ZONE_EXTENT
                    # on an Auto point. Its zone was chosen by the statute's
                    # county rule, so a warning from the zone's approximate
                    # extent box would be false on it. Removed from the
                    # conversion record too, so no surface can reach it.
                    # Fixed-zone jobs are untouched.
                    conversion = replace(
                        conversion,
                        warnings=tuple(
                            w
                            for w in conversion.warnings
                            if w.code is not WarningCode.OUTSIDE_ZONE_EXTENT
                        ),
                    )
                if auto_assignment is not None and (
                    conversion.latitude,
                    conversion.longitude,
                ) != chosen_at:
                    # if/raise, never assert (-O). The zone must have been
                    # chosen at exactly the position that was projected; a
                    # difference would mean the two calls took different
                    # frame paths, and the zone would be the zone of some
                    # other position.
                    raise FrameTransformationUnavailableError(
                        f"{context}: the Auto zone was chosen at latitude "
                        f"{chosen_at[0]!r}, longitude {chosen_at[1]!r}, but "
                        f"the position projected into {target_zone.name} was "
                        f"latitude {conversion.latitude!r}, longitude "
                        f"{conversion.longitude!r}. Refused: the zone must be "
                        f"the zone of the position converted."
                    )
                output_unit = settings.output_unit
                output_northing = output_unit.from_meters(conversion.target_northing)
                output_easting = output_unit.from_meters(conversion.target_easting)
            elif settings.direction is Direction.GEODETIC_TO_GEODETIC:
                # Plan decision D7. No zone: the output columns are the position
                # in the TARGET frame, in the file's own longitude convention.
                conversion = geodetic_to_geodetic(
                    latitude,
                    longitude,
                    settings.geodetic_frame,
                    settings.target_geodetic_frame,
                    context,
                    **transform_arguments,
                )
                out_latitude, out_longitude = written_geodetic_position(conversion)
                output_northing = out_latitude
                output_easting = settings.longitude_convention.from_signed(
                    out_longitude
                )
            else:
                # VERTICAL_ONLY, geodetic input. No zone exists anywhere in this
                # job, and none is fabricated: the position record carries the
                # pivot for the grid lookups and None for every zone-derived
                # quantity, so the grid scale and combined factors downstream are
                # honestly absent rather than invented. The output coordinate
                # columns are the INPUT values, unchanged - the mirror this
                # direction promises - including the longitude exactly as the
                # file wrote it, in its own convention.
                #
                # On a WGS 84 or ITRF input (plan decision D8) the position record's
                # pivot is the input carried to NAD83(2011) - what every grid is
                # read at - while the columns still mirror the input exactly.
                conversion = geodetic_position(
                    latitude,
                    longitude,
                    settings.geodetic_frame,
                    context,
                    **transform_arguments,
                )
                output_northing = row.northing
                output_easting = row.easting
        else:
            northing_m = settings.input_unit.to_meters(row.northing)
            easting_m = settings.input_unit.to_meters(row.easting)

            if easting_looks_wrong_for_zone(easting_m, settings.source_zone):
                warnings.append(
                    ConversionWarning(
                        code=WarningCode.EASTING_UNLIKE_SELECTED_ZONE,
                        message=(
                            f"{context}: an easting of {row.easting:,.3f} "
                            f"{settings.input_unit.code} does not look like "
                            f"{settings.source_zone.name} data, whose eastings sit "
                            f"near {settings.input_unit.from_meters(settings.source_zone.definition.easting_origin):,.0f} "
                            # "this file" was wrong the moment a typed point could
                            # raise this warning: the single-point tab has no file,
                            # and this is the likeliest warning a typed point
                            # produces. Worded for both callers (closing review
                            # gate, docs/DESIGN.md amendment #26).
                            f"{settings.input_unit.code}. Check that the source "
                            f"zone and the input units are the ones these "
                            f"coordinates are actually in - selecting the wrong "
                            f"source zone is the easiest mistake to make with this "
                            f"program."
                        ),
                    )
                )

            if settings.direction is Direction.ZONE_TO_GEODETIC:
                # Within one frame, zone_to_geodetic IS convert_point with the
                # source zone at both ends, the call this branch always made. Into
                # a WGS 84 or ITRF frame it carries the pivot there with HTDP, and
                # the columns written are that frame's position, not the pivot's.
                conversion = zone_to_geodetic(
                    northing_m,
                    easting_m,
                    settings.source_zone,
                    settings.geodetic_frame,
                    context,
                    **transform_arguments,
                )
                out_latitude, out_longitude = written_geodetic_position(conversion)
                output_northing = out_latitude
                output_easting = settings.longitude_convention.from_signed(
                    out_longitude
                )
            elif settings.direction is Direction.VERTICAL_ONLY:
                # VERTICAL_ONLY, zone input. The pivot latitude and longitude the
                # grid lookups need come from inverse-projecting through the
                # INPUT zone - the same machinery, and the same source-zone-twice
                # call, ZONE_TO_GEODETIC uses above, so the factors sit under the
                # input zone exactly as that direction's do (there is no target
                # zone in either). The output coordinate columns are the INPUT
                # values, unchanged: the settings guarantee output_unit equals
                # input_unit, so no re-expression could be hiding in them.
                conversion = convert_point(
                    northing_m,
                    easting_m,
                    settings.source_zone,
                    settings.source_zone,
                    context,
                )
                output_northing = row.northing
                output_easting = row.easting
            else:
                conversion = convert_point(
                    northing_m,
                    easting_m,
                    settings.source_zone,
                    settings.target_zone,
                    context,
                )
                output_northing = settings.output_unit.from_meters(
                    conversion.target_northing
                )
                output_easting = settings.output_unit.from_meters(
                    conversion.target_easting
                )
    except htdp.HtdpRefusal as error:
        raise _point_named_htdp_refusal(
            error, context, settings, frame_path, geodetic_input
        ) from error

    # Elevation is orthometric height: it does not change with the horizontal
    # zone. Only its unit changes - and it changes in EVERY direction,
    # including State Plane to geodetic.
    #
    # That last clause used to be an exception: the elevation was left in the
    # input unit when the horizontal columns became degrees, on the reasoning
    # that a geodetic export has no linear unit. It does: the Z column. Three
    # separate surfaces already said so - this class's own docstring, the audit
    # CSV's "in <in>, out <out>" label, and the job record's "Units out" line -
    # while the clean export wrote feet. A reader who re-imported the file as
    # the record instructs computed the elevation factor at 900 m instead of
    # 274.3 m, a 98 ppm error, and read a Z field 625.680 m from the truth.
    # The unit now follows the output unit end to end (WP-R2 fix A).
    # (``elevation_m`` itself is computed above, before the conversion, since
    # the WGS 84 build: a frame transformation is handed the height.)

    # ----------------------------------------------------------------------
    # Ellipsoid height in, orthometric height out - H = h - N (the owner's
    # feature, 2026-08-11).
    #
    # ``supplied_m`` keeps the height exactly as the file gave it, because
    # HORIZONTAL MODE WRITES THAT NUMBER BACK UNCHANGED (the owner's
    # instruction: "in horizontal only mode, the elevations should be passed
    # through unchanged, regardless of the input"). Everything else works from
    # ``elevation_m``, and the point of rebinding it HERE, before anything
    # reads it, is the invariant that establishes:
    #
    #     from this line down, elevation_m is an ORTHOMETRIC height in metres,
    #     on every path, in every mode.
    #
    # That invariant is why the eight places below need no edit at all.
    # Assigning only ``height_m`` instead would have been silently overwritten
    # a few lines later by the identity branch's ``apply_shift(elevation_m,
    # ...)`` - on the flagship same-datum job the feature would have done
    # nothing at all - and would have fed a raw ellipsoid height to VERTCON and
    # to #41's source-era factor path. Found by the design review before the
    # code was written; pinned by
    # ``test_the_identity_branch_cannot_overwrite_the_converted_height``.
    #
    # ``grid`` is the right grid to read: with the swap refused for ellipsoid
    # input (``run``), the h -> H model IS ``factors_geoid_model`` in every
    # accepted configuration, and ``grid`` is loaded from exactly that record.
    # ----------------------------------------------------------------------
    supplied_m = elevation_m
    if (
        conversion.transform_height is not None
        and conversion.transform_height.convention is HeightConvention.ELLIPSOID
    ):
        # Plan decision D6, the one place it bites. An ellipsoid height is part
        # of the 3-D position, so it was transformed WITH it: the Z a
        # horizontal job writes is the height in the job's OUTPUT frame -
        # HTDP's own output height - and every H = h - N below uses the
        # NAD83(2011) h, because every geoid model publishes N against
        # NAD 83. #54's "horizontal passes the Z through unchanged" still
        # holds in the sense #54 meant: the height is never turned into an
        # elevation; only its frame changes, because the job's frame did.
        supplied_m = conversion.target_frame_ellipsoid_height
        elevation_m = conversion.pivot_ellipsoid_height
    ellipsoid_reading: EllipsoidHeightReading | None = None
    if settings.input_height_kind is HeightKind.ELLIPSOID and elevation_m is not None:
        model = factors_geoid_model(settings, transformation)
        if grid is None or model is None:
            raise ValueError(
                f"{context}: the input heights are stated as ellipsoid heights "
                f"but this job carries no geoid model, so no geoid separation "
                f"exists to convert them with. run() refuses this combination "
                f"before any point converts; reaching it here is an internal "
                f"wiring defect."
            )
        try:
            separation_m = geoid.geoid_height(
                conversion.latitude, conversion.longitude, grid
            )
        except geoid.GeoidError as error:
            # No separation, so no orthometric height. In the vertical modes
            # that refuses the Z outright - those modes exist to produce a
            # datum-tagged elevation and there is none. In horizontal mode the
            # Z is the supplied ellipsoid height and still goes out unchanged;
            # only the factors are lost, which is the GEOID_UNAVAILABLE shape
            # that path has always had. The horizontal coordinate stands
            # either way.
            elevation_m = None
            warnings.append(
                ConversionWarning(
                    code=(
                        WarningCode.ELLIPSOID_HEIGHT_UNCONVERTIBLE
                        if settings.vertical_mode.converts_elevations
                        else WarningCode.GEOID_UNAVAILABLE
                    ),
                    message=(
                        f"{context}: the height {row.elevation:,.3f} "
                        f"{settings.input_unit.code} was supplied as an "
                        f"ELLIPSOID height, but no {model.name} geoid height "
                        f"is available at {conversion.latitude:.6f}, "
                        f"{conversion.longitude:.6f}, so the orthometric "
                        f"height H = h - N could not be computed for it. "
                        + (
                            "No elevation is written for this point and its "
                            "elevation and combined factors read "
                            if settings.vertical_mode.converts_elevations
                            else _unconverted_ellipsoid_z_sentence(conversion)
                        )
                        + f"{formatting.NOT_AVAILABLE}. The HORIZONTAL "
                        f"coordinate is unaffected and stands: it does not "
                        f"depend on elevation at all. Underlying reason: "
                        f"{error}"
                    ),
                )
            )
        else:
            orthometric_m = elevation_m - separation_m
            ellipsoid_reading = EllipsoidHeightReading(
                geoid_model_name=model.name,
                vertical_datum_code=model.vertical_datum.code,
                ellipsoid_height_m=elevation_m,
                geoid_height_m=separation_m,
                orthometric_height_m=orthometric_m,
            )
            elevation_m = orthometric_m

    # ----------------------------------------------------------------------
    # Vertical shift - plan section 3.6 step 3, and it MUST run before the
    # geoid lookup and the factors below, because GEOID18/GEOID12B N and the
    # elevation factor are defined against the TARGET-era (NAVD 88) height.
    # The ordering's effect on the elevation factor is ~0.02 ppm - negligible,
    # and nobody should mistake the factor for the reason. The reason is the
    # Z VALUE ITSELF: an unshifted height is out by ~0.46 ft across Michigan
    # (plan section 3.6).
    #
    # ``height_m`` is the height everything downstream uses - the geoid gate,
    # the factors, and the Z column. For a horizontal job it IS elevation_m,
    # untouched, so that path is byte-identical to what shipped.
    # ----------------------------------------------------------------------
    height_m = elevation_m
    vertical_reading: VerticalReading | None = None
    geoid_swap_reading: GeoidSwapReading | None = None
    if transformation is None and settings.vertical_mode.converts_elevations:
        # The mirror of _require_transformation_matches_settings (WP-V6 review
        # gate, LOW 6): that check catches the wrong record arriving, this
        # catches NO record arriving on settings that promise a shift. Without
        # it an unshifted source-datum height flows into a Z column the
        # settings claim is target-datum, with no reading and no warning -
        # unreachable through run(), which always derives the record from the
        # same settings, but this function is the thing the check exists to
        # hold, not run()'s good manners.
        raise ValueError(
            f"{context}: this job's settings state a vertical conversion "
            f"({settings.source_vertical_datum.code} -> "
            f"{settings.target_vertical_datum.code}) but no transformation "
            f"record was supplied to apply it. Refused rather than writing "
            f"an unconverted {settings.source_vertical_datum.code} height "
            f"into a Z column that would claim "
            f"{settings.target_vertical_datum.code}."
        )
    if transformation is not None:
        _require_transformation_matches_settings(transformation, settings)
        if elevation_m is not None:
            if transformation.is_identity:
                # An identity reads NO grid - apply_shift refuses a grid value
                # for one - and shifts by exactly 0.0, so the height is
                # bit-identical. Sigma is None WITH a reason, never 0.0: no
                # model ran, so there is no model uncertainty to state.
                height_m = apply_shift(
                    elevation_m, grid_value_m=None, transformation=transformation
                )
                vertical_reading = VerticalReading(
                    transformation=transformation,
                    shift_m=0.0,
                    sigma_m=None,
                    sigma_unavailable_reason=_IDENTITY_SIGMA_REASON,
                )
                if swap_grids is not None:
                    # The geoid-to-geoid conversion (the owner's feature,
                    # 2026-08-09): both separations at the SAME pivot, the
                    # ellipsoid height held fixed, the orthometric height
                    # re-derived under the output model -
                    # H_out = H_in + N_in - N_out. Runs only on an identity
                    # (a modeled transformation with both sides stated was
                    # refused before any point converted), so the datum
                    # reading above stays the identity record: both are
                    # true - the datum did not change, the geoid did.
                    try:
                        n_source = geoid.geoid_height(
                            conversion.latitude,
                            conversion.longitude,
                            swap_grids.source_grid,
                        )
                        n_target = geoid.geoid_height(
                            conversion.latitude,
                            conversion.longitude,
                            swap_grids.target_grid,
                        )
                    except geoid.GeoidError:
                        # Outside a tile - the VERTICAL_SHIFT_UNAVAILABLE
                        # shape exactly: the height in hand is stated
                        # against the INPUT model and every elevation this
                        # job writes claims the OUTPUT one, so no Z is
                        # written, the reading is withdrawn (a shift row
                        # beside an absent Z would claim an output that was
                        # not written), and the coordinates stand.
                        height_m = None
                        vertical_reading = None
                        warnings.append(
                            ConversionWarning(
                                code=WarningCode.GEOID_SWAP_UNAVAILABLE,
                                message=(
                                    f"{context}: the elevation "
                                    f"{row.elevation:,.3f} "
                                    f"{settings.input_unit.code} was "
                                    f"supplied, but "
                                    f"{conversion.latitude:.6f}, "
                                    f"{conversion.longitude:.6f} is "
                                    f"outside the geoid tiles this "
                                    f"program ships, so the "
                                    f"elevation cannot be re-derived from "
                                    f"{swap_grids.source_model.name} to "
                                    f"{swap_grids.target_model.name} "
                                    f"there. The elevation was NOT "
                                    f"converted: rather than print the "
                                    f"{swap_grids.source_model.name} "
                                    f"height in a Z column whose job "
                                    f"names "
                                    f"{swap_grids.target_model.name}, "
                                    f"this point's output elevation is "
                                    f"blank and its elevation and "
                                    f"combined factors are "
                                    f"{formatting.NOT_AVAILABLE}. The "
                                    f"HORIZONTAL coordinates are "
                                    f"unaffected and stand: they do not "
                                    f"depend on elevation at all."
                                ),
                            )
                        )
                    else:
                        swap_shift = n_source - n_target
                        height_m = height_m + swap_shift
                        geoid_swap_reading = GeoidSwapReading(
                            source_model_name=swap_grids.source_model.name,
                            target_model_name=swap_grids.target_model.name,
                            n_source_m=n_source,
                            n_target_m=n_target,
                            shift_m=swap_shift,
                        )
            else:
                if vertcon_grids is None:
                    # run() loads the pair once for every modeled job; a None
                    # arriving here is a wiring defect, and shift_and_sigma_m's
                    # own default would paper over it by silently loading the
                    # pair per row - "loaded ONCE per job" held as a guarantee
                    # rather than a convention (WP-V6 review gate, LOW 8).
                    raise ValueError(
                        f"{context}: a modeled vertical transformation "
                        f"({transformation}) reached the row with no VERTCON "
                        f"grid pair. run() loads the pair once per job; this "
                        f"is an internal wiring defect, not a data problem."
                    )
                if not vertcon_grids.contains(
                    conversion.latitude, conversion.longitude
                ):
                    # Outside the pair's coverage - decided by asking, not by
                    # catching: a VertconError from the read below is now a
                    # STRUCTURAL failure (a broken grid object) and propagates
                    # loudly, where the old catch-all claimed "the grids do
                    # not cover this point" for a truncated file too - a false
                    # headline over a true footnote (WP-V6 review gate, LOW
                    # 7). The GEOID_UNAVAILABLE shape: the horizontal result
                    # stands, and the elevation is REFUSED rather than passed
                    # through unshifted. The height this program holds is in
                    # the SOURCE datum and every vertical output of this job
                    # claims the target one, so height_m goes to None: no Z
                    # is written, and the elevation-dependent factors read
                    # N/A rather than being built from a height in the wrong
                    # era.
                    height_m = None
                    warnings.append(
                        ConversionWarning(
                            code=WarningCode.VERTICAL_SHIFT_UNAVAILABLE,
                            message=(
                                f"{context}: the elevation "
                                f"{row.elevation:,.3f} "
                                f"{settings.input_unit.code} was supplied, "
                                f"but the {transformation.model} grids do "
                                f"not cover "
                                f"{conversion.latitude:.6f}, "
                                f"{conversion.longitude:.6f}, so no "
                                f"{transformation.source.code} -> "
                                f"{transformation.target.code} shift can be "
                                f"looked up there. The elevation was NOT "
                                f"converted: rather than print the "
                                f"unconverted {transformation.source.code} "
                                f"height in a Z column that claims "
                                f"{transformation.target.code}, this point's "
                                f"output elevation is blank and its "
                                f"elevation and combined factors are "
                                f"{formatting.NOT_AVAILABLE}. The HORIZONTAL "
                                f"coordinates are unaffected and stand: they "
                                f"do not depend on elevation at all."
                            ),
                        )
                    )
                else:
                    grid_value_m, sigma_m = vertcon.shift_and_sigma_m(
                        conversion.latitude, conversion.longitude, vertcon_grids
                    )
                    height_m = apply_shift(
                        elevation_m,
                        grid_value_m=grid_value_m,
                        transformation=transformation,
                    )
                    reason = None
                    if sigma_m is None:
                        # The error model interpolated negative here - a
                        # value that cannot be a one-sigma (DESIGN.md #36).
                        # Distinguished from the identity's None by a reason
                        # that names the position and points at the raw
                        # figure; the shift beside it comes from the other
                        # grid and is unaffected.
                        raw = vertcon_grids.uncertainty.modeled_error_raw_m(
                            conversion.latitude, conversion.longitude
                        )
                        reason = (
                            f"the {transformation.model} error model "
                            f"interpolates to a value that cannot be a "
                            f"one-sigma uncertainty at "
                            f"{conversion.latitude:.6f}, "
                            f"{conversion.longitude:.6f} (raw model output "
                            f"{raw!r} m, readable via michspc.fileio."
                            f"vertcon.UncertaintyGrid.modeled_error_raw_m). "
                            f"The shift is read from the separate "
                            f"transformation grid and is unaffected."
                        )
                        # And it must be SAID, not merely recorded on the
                        # frozen reading: DESIGN.md #41 instructed WP-V7 not
                        # to assume a warning already flags this, so this
                        # warning is what makes the missing sigma reach every
                        # surface - the record's WARNINGS section, the audit
                        # CSV's warnings column, and the GUI warnings field -
                        # through the one pipeline they all already read. The
                        # identity's sigma-less reading raises NO warning: its
                        # absence is stated by the record's METHOD text ("no
                        # shift is applied"), and warning about a state the
                        # user chose would teach nothing.
                        warnings.append(
                            ConversionWarning(
                                code=WarningCode.VERTICAL_SIGMA_UNAVAILABLE,
                                message=(
                                    f"{context}: at "
                                    f"{conversion.latitude:.6f}, "
                                    f"{conversion.longitude:.6f} no one-sigma "
                                    f"uncertainty can be stated for the "
                                    f"{transformation.source.code} -> "
                                    f"{transformation.target.code} shift: "
                                    f"the {transformation.model} error model "
                                    f"interpolates to a value there that is "
                                    f"not physical as an uncertainty (a "
                                    f"negative one-sigma is not a quantity). "
                                    f"THE SHIFT ITSELF IS VALID AND "
                                    f"UNAFFECTED - it is read from the "
                                    f"separate transformation grid - so this "
                                    f"point's elevation IS converted and "
                                    f"written; only its sigma reads "
                                    f"{formatting.NOT_AVAILABLE}, never a "
                                    f"number."
                                    # The raw model figure and its accessor
                                    # path stay on the reading's
                                    # sigma_unavailable_reason and OUT of
                                    # every output: printing -0.00965 in a
                                    # record a surveyor compares against
                                    # NCAT's +0.011 manufactures the exact
                                    # confusion #36's refusal exists to
                                    # prevent, and a sealed document is no
                                    # place for a Python attribute path
                                    # (WP-V7 review gate, MEDIUM 1).
                                ),
                            )
                        )
                    vertical_reading = VerticalReading(
                        transformation=transformation,
                        shift_m=signed_shift(
                            grid_value_m=grid_value_m,
                            transformation=transformation,
                        ),
                        sigma_m=sigma_m,
                        sigma_unavailable_reason=reason,
                    )

    # The Z that gets WRITTEN, and the one line where the mode decides
    # anything about it. Horizontal mode passes the supplied height through
    # untouched - the owner's instruction - so a GNSS file converted in
    # horizontal mode keeps its ellipsoid heights in the Z column and gains
    # only correct factors. The vertical modes write the orthometric height,
    # shifted. With ORTHOMETRIC input the two are the same value and every
    # pre-existing job is byte-identical.
    written_m = height_m if settings.vertical_mode.converts_elevations else supplied_m
    output_elevation = (
        settings.output_unit.from_meters(written_m)
        if written_m is not None
        else None
    )

    # ----------------------------------------------------------------------
    # The height the FACTORS use - era consistency (DESIGN.md #41, superseding
    # plan section 3.5's target-datum-only rule). The geoid separation N is
    # defined against the geoid model's own vertical datum (NAVD 88 for both
    # shipped models), so h = H + N is honest only when H is in that same
    # datum. For an NGVD29 -> NAVD88 job that is the SHIFTED height, which is
    # why the shift precedes the factors; for a NAVD88 -> NGVD29 job it is the
    # SOURCE height - using the shifted NGVD 29 height there would mix the
    # eras by exactly the shift (~0.02 ppm in the factor; small, but wrong in
    # a number this program prints to its last digit). A job whose geoid
    # model matches NEITHER endpoint datum was refused before any point
    # converted (_require_vertical_settings). A coverage-refused point keeps
    # factor_height_m None deliberately: its factors read N/A with the
    # warning, era-splitting a half-failed point would be cleverness in an
    # audit trail.
    # ----------------------------------------------------------------------
    factor_height_m = height_m
    if (
        vertical_reading is not None
        and height_m is not None
        and factors_use_source_era(settings, vertical_reading.transformation)
    ):
        factor_height_m = elevation_m

    geoid_height = None
    if grid is not None and factor_height_m is not None:
        # The model `grid` was loaded from, named the same way `run` chose it,
        # so the warning below cannot name a model this point did not consult.
        # Non-None whenever `grid` is: `run` derives one from the other.
        factors_model = factors_geoid_model(settings, transformation)
        geoid_model_consulted = (
            factors_model.name if factors_model is not None else "geoid"
        )
        try:
            geoid_height = geoid.geoid_height(
                conversion.latitude, conversion.longitude, grid
            )
        except geoid.GeoidError as error:
            # Outside the shipped tile. The horizontal conversion is unaffected
            # and stands; only the elevation-dependent factors are unavailable,
            # and factors_at reports that as None rather than inventing one.
            #
            # It must also be SAID. Setting geoid_height to None on its own is
            # indistinguishable downstream from a point that carried no
            # elevation at all: the same two factor columns read N/A, and the
            # job record's ELEVATIONS section then listed this point under
            # "blank elevation field" - a falsehood about a point whose Z was
            # recorded. The warning carries the distinction to the audit CSV,
            # to the report's WARNINGS section, and to the screen (WP-R2 fix C).
            geoid_height = None
            warnings.append(
                ConversionWarning(
                    code=WarningCode.GEOID_UNAVAILABLE,
                    message=(
                        f"{context}: the elevation "
                        # Not "read from the file": a typed point has none.
                        f"{row.elevation:,.3f} {settings.input_unit.code} was "
                        # The model this job actually consulted - the FACTORS
                        # side, which is the side `grid` was loaded from. It
                        # was `settings.geoid_model` until per-side selection
                        # (DESIGN.md #50) made that a different question: on a
                        # NAVD 88 -> NGVD 29 job the output side has no model
                        # at all (NGVD 29 has none), the factors run off the
                        # INPUT side, and naming settings.geoid_model here
                        # raised AttributeError on None instead of warning.
                        f"supplied, but no {geoid_model_consulted} "
                        f"geoid height is available at "
                        f"{conversion.latitude:.6f}, {conversion.longitude:.6f}, "
                        f"so the elevation factor and combined factor for this "
                        f"point are {formatting.NOT_AVAILABLE} rather than a "
                        f"number. The HORIZONTAL "
                        f"coordinate is unaffected and stands: it does not "
                        f"depend on elevation at all. Underlying reason: "
                        f"{error}"
                    ),
                )
            )

    # The height in the geoid model's own era - plan section 3.6 step 5 as
    # amended by #41. For a horizontal job factor_height_m is elevation_m
    # untouched, so nothing changes.
    factors = factors_at(
        conversion.target_scale_factor, factor_height_m, geoid_height
    )

    return ConvertedPoint(
        row=row,
        conversion=conversion,
        factors=factors,
        output_northing=output_northing,
        output_easting=output_easting,
        output_elevation=output_elevation,
        vertical=vertical_reading,
        ellipsoid_height=ellipsoid_reading,
        geoid_swap=geoid_swap_reading,
        warnings=tuple(warnings) + conversion.warnings,
        auto_zone=auto_assignment,
    )
