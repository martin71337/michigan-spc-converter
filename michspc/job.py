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

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from michspc.fileio import formatting, geoid, pnezd, vertcon
from michspc.spc.convert import (
    ConversionWarning,
    PointConversion,
    WarningCode,
    convert_point,
    easting_looks_wrong_for_zone,
    geodetic_position,
    project_point,
)
from michspc.spc.factors import Factors, factors_at
from michspc.spc.frames import NAD83_2011, ReferenceFrame
from michspc.spc.units import LinearUnit
from michspc.spc.vertical import (
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
    """The reference frame a geodetic INPUT file's latitudes and longitudes are
    read as. Ignored when the input is State Plane, because a zone carries its
    own frame.

    Unlike the longitude convention this one does carry a default, and the
    reason is that the two risks are not comparable. The longitude sign is a
    real coin-flip - the manual uses one convention, every GPS and GIS the other
    - and getting it wrong throws a Michigan point about 340 miles, so
    docs/DESIGN.md section 7 forbids a default there. The frame is not a
    coin-flip today: every zone in the registry is NAD83(2011), NATRF2022 has no
    zones and no transformation (docs/DESIGN.md section 10), so the only way to
    reach a mismatch is for a caller to set this field to NATRF2022 on purpose -
    and ``project_point`` then refuses it, which is finding 1's whole point.

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
    """

    vertical: VerticalReading | None = None
    """The vertical transformation evidence for this point, or None.

    None on every point of a HORIZONTAL job, on a vertical job's point that
    carried no elevation (there is no height to shift), and on a point whose
    shift was unavailable (the warning beside it says so).
    """

    warnings: tuple[ConversionWarning, ...] = field(default_factory=tuple)

    @property
    def point_id(self) -> str:
        return self.row.point_id


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


def run(settings: JobSettings, source: pnezd.PnezdFile | None = None) -> JobResult:
    """Execute a job. Reads if no parsed file is supplied; never writes.

    When ``source`` is supplied the job converts those rows and nothing else, so
    the record's SHA-256 is that source's own digest - which is None unless the
    source came from ``pnezd.read``. It is never taken from
    ``settings.input_path``, because that path was not what was converted
    (WP-R3 fix 2).
    """
    if settings.direction is Direction.ZONE_TO_ZONE:
        if settings.source_zone is None or settings.target_zone is None:
            raise ValueError(
                "A zone-to-zone conversion needs both a source and a target "
                "zone. Neither is inferred from the coordinates."
            )
    elif settings.direction is Direction.GEODETIC_TO_ZONE:
        if settings.target_zone is None:
            raise ValueError("A geodetic conversion needs a target zone.")
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
    elif settings.source_zone is None:
        raise ValueError("Converting to geodetic needs the zone the file is in.")

    # Which jobs consult the longitude sign convention. A vertical-only job
    # reads longitudes from the file ONLY when its input is geodetic; with a
    # zone input the file carries none and none are written, so that job
    # states None exactly as a zone-to-zone job does.
    consults_longitude = settings.direction in (
        Direction.GEODETIC_TO_ZONE,
        Direction.ZONE_TO_GEODETIC,
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

    grid = (
        geoid.default_grid(settings.geoid_model)
        if settings.geoid_model is not None
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

    points: list[ConvertedPoint] = []
    for row in parsed.rows:
        points.append(
            _convert_row(row, settings, grid, transformation, vertcon_grids)
        )

    return JobResult(
        settings=settings,
        points=tuple(points),
        # The digest of the bytes the parser consumed, and nothing else. None
        # when the rows arrived already parsed - see JobResult.input_sha256.
        input_sha256=parsed.sha256,
        input_row_count=len(parsed.rows),
        skipped_blank_lines=parsed.skipped_blank_lines,
        # The NAME, not the record: JobResult's contract predates the registry
        # and report.py resolves the record back through geoid_model_by_name.
        geoid_model=(
            settings.geoid_model.name if settings.geoid_model is not None else None
        ),
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


def factors_use_source_era(
    settings: JobSettings, transformation: VerticalTransformation | None
) -> bool:
    """Whether this job's factors are computed from the SOURCE-datum height.

    The #41 either-endpoint rule's one configuration where the factors do not
    use the height the Z column carries: a modeled transformation whose
    SOURCE datum is the geoid model's own era (NAVD88 -> NGVD29 with either
    shipped model). Stated once and called from both the computation
    (``_convert_row``) and the record (``report.py``'s Factor height
    paragraph), so the sentence and the arithmetic cannot drift apart
    (WP-V7 review gate, LOW 2; one authoritative representation per fact).
    """
    return (
        transformation is not None
        and not transformation.is_identity
        and settings.geoid_model is not None
        and settings.geoid_model.vertical_datum.code
        == transformation.source.code
        != transformation.target.code
    )


def _convert_row(
    row: pnezd.PnezdRow,
    settings: JobSettings,
    grid,
    transformation: VerticalTransformation | None,
    vertcon_grids: vertcon.VertconGridPair | None,
) -> ConvertedPoint:
    context = f"point {row.point_id}"
    warnings: list[ConversionWarning] = []

    geodetic_input = settings.direction is Direction.GEODETIC_TO_ZONE or (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is None
    )

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
            conversion = project_point(
                latitude,
                longitude,
                settings.geodetic_frame,
                settings.target_zone,
                context,
            )
            output_unit = settings.output_unit
            output_northing = output_unit.from_meters(conversion.target_northing)
            output_easting = output_unit.from_meters(conversion.target_easting)
        else:
            # VERTICAL_ONLY, geodetic input. No zone exists anywhere in this
            # job, and none is fabricated: the position record carries the
            # pivot for the grid lookups and None for every zone-derived
            # quantity, so the grid scale and combined factors downstream are
            # honestly absent rather than invented. The output coordinate
            # columns are the INPUT values, unchanged - the mirror this
            # direction promises - including the longitude exactly as the
            # file wrote it, in its own convention.
            conversion = geodetic_position(
                latitude, longitude, settings.geodetic_frame, context
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
            conversion = convert_point(
                northing_m,
                easting_m,
                settings.source_zone,
                settings.source_zone,
                context,
            )
            output_northing = conversion.latitude
            output_easting = settings.longitude_convention.from_signed(
                conversion.longitude
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
            output_easting = settings.output_unit.from_meters(conversion.target_easting)

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
    elevation_m = (
        settings.input_unit.to_meters(row.elevation)
        if row.elevation is not None
        else None
    )

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

    output_elevation = (
        settings.output_unit.from_meters(height_m)
        if height_m is not None
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
                        # The model this job actually consulted: grid is only
                        # ever non-None when settings.geoid_model is a record.
                        f"supplied, but no {settings.geoid_model.name} "
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
        warnings=tuple(warnings) + conversion.warnings,
    )
