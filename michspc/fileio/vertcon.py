"""NGS VERTCON 3.0 binary grid reader: the NGVD 29 to NAVD 88 shift, and its sigma.

An orthometric height is meaningless without the vertical datum it is expressed
in. VERTCON is NGS's model of the difference between the two datums a Michigan
surveyor meets: it stores ``NAVD88 - NGVD29`` in metres, and that value is
ADDED to an NGVD 29 height. Across Michigan the shift runs from about -0.41 m to
+0.35 m - it changes sign, so it is not a bias that could be subtracted out
(docs/PLAN-vertical-datums.md section 2.7). What that number *means* and which
way it is applied is ``michspc/spc/vertical.py``'s business; this module's only
job is to get it off the disk correctly.

**Two grids, and they are read as a pair.** NGS publishes the transformation
(``.trn``) beside a companion uncertainty grid (``.err``) on the identical
geometry. The uncertainty is not decoration: at 43.05 N, 86.20 W the modeled
shift is -0.1466 m and its one-sigma uncertainty is 0.3656 m, which is 249% of
the shift itself (plan section 2.8, measured against NGS NCAT). A shift reported
without it would be a modeled number wearing the clothes of a measured one. The
pair is loaded together and checked to share geometry, because a mismatched pair
would report one position's shift with another position's sigma.

**File format** (plan section 2.2, measured at the V0 gate). Unlike GEOID18 these
files carry Fortran unformatted record markers, so the same ``<4d3i`` header sits
at byte 4 rather than byte 0:

    offset 0    int32     Fortran record marker = 44      <- NOT in GEOID18
    offset 4    real*8    SLAT   southernmost latitude, degrees
    offset 12   real*8    WLON   westernmost longitude, degrees EAST (0-360)
    offset 20   real*8    DLAT   north-south spacing, degrees
    offset 28   real*8    DLON   east-west spacing, degrees
    offset 36   int*4     NLAT   number of rows, extending north from SLAT
    offset 40   int*4     NLON   number of columns, extending east from WLON
    offset 44   int*4     IKIND  always 1: real*4 data, and the endian marker
    offset 48   int32     Fortran record marker = 44
    then, per row:  int32 marker = NLON*4 | real*4[NLON] | int32 marker = NLON*4

Little-endian, IKIND = 1, values in METRES. The markers are a real structural
check and not ceremony: every one of them is validated here, and the file's
length is required to equal what its own header implies once the markers are
counted in. GEOID18 has nothing equivalent. A GEOID18 tile handed to this reader
is caught by the very first marker - the first four bytes of ``g2018u3.bin`` are
the low half of SLAT = 40.0, which is zero, not 44.

Plan section 2.2 also asked for a "bytes consumed equals file length" check after
the row walk. That check was written, and then removed at the WP-V4 review gate
as dead code: the length check above computes the same total from the same header
arithmetic before the walk begins, and the walk advances by a fixed stride, so
``offset == len(raw)`` is forced rather than tested. A refusal that cannot fire
is worse than no refusal, because it is read as a defence that is being kept
(WP-V4 review, LOW 2). The property itself is not lost - it is what the length
check asserts, and ``tests/test_vertcon.py`` walks both shipped files
independently of this reader and requires the walk to land on the last byte.

**INTERPOLATION: both grids are biquadratic, anchored on the NEAREST NODE.**
That is one measured choice with two parts, and the second part is the one that
is easy to get wrong. The scheme is the same tensor product of Lagrange
quadratics GEOID18 uses; the *anchoring* is not GEOID18's. GEOID18 places its 3x3
stencil at ``int(row) - 1``, which puts the target in the stencil's upper
interval; both VERTCON grids want it at ``int(row + 0.5) - 1``, which puts the
target in the middle. Measured against the 20 frozen NGS NCAT anchors:

    .trn   nearest-node   0.471 mm max      floor-anchored   8.457 mm max
    .err   nearest-node   0.472 mm max      floor-anchored   3.042 mm max
    .trn   bilinear      17.726 mm max
    .err   bilinear       4.547 mm max

Nearest-node anchoring reproduces NCAT's printed figure at 20 of 20 points on
both grids; nothing else reproduces it at more than 14. GEOID18 measurably
prefers the other anchoring on its own anchors (0.595 mm against 0.830), so the
two NGS products genuinely differ and ``ngs_grid`` carries both variants with
neither as a default.

**This supersedes docs/PLAN-vertical-datums.md section 2.5**, which recorded that
the ``.trn`` grid is biquadratic and the ``.err`` grid bilinear and asked for a
test that fails if the two are ever unified. That asymmetry was a real
measurement of the wrong thing: bilinear only beat "biquadratic" on the
uncertainty grid because it was being raced against a mis-anchored biquadratic.
With the stencil centred, both grids land below NCAT's own 0.5 mm printing
quantization. There is therefore no asymmetry to protect - what is pinned instead
is the anchoring, with the two wrong variants shown failing.

**No policy about heights lives here.** This module reads cells. It does not know
the sign convention, the direction, or that a shift is added rather than
subtracted; ``michspc/spc/vertical.py`` owns all of that and takes the grid value
as a parameter, exactly as ``factors.factors_at`` takes the geoid height. Stdlib
plus the substrate only: no Qt, no network.

**A reading is never faked.** Every failure path in this module raises; there is
no fallback value anywhere in it. That is a requirement rather than a style,
because ``spc.vertical.signed_shift`` legitimately accepts ``grid_value_m=0.0`` -
the ``.trn`` grid genuinely crosses zero inside Michigan - so a 0.0 invented here
would be indistinguishable from a real reading and would silently report an
unconverted height as converted.

**The same rule is why a negative uncertainty is refused rather than repaired.**
The uncertainty grid interpolates below zero at a small fraction of Michigan
positions (``UncertaintyGrid``), and a negative one-sigma is not a quantity.
Clamping it to 0.0 would fabricate certainty and taking its absolute value would
fabricate a figure, so ``UncertaintyGrid.sigma_m`` raises there while
``modeled_error_raw_m`` keeps the unfiltered model output readable under a name
that cannot be mistaken for an uncertainty. **The shift at such a position is
untouched and remains valid** - it comes from the other grid - so
``VertconGridPair.reading_at`` still reports it, with the sigma marked
unavailable in the shape ``job.py`` already uses for a missing geoid height.
"""

from __future__ import annotations

import hashlib
import struct
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from michspc.fileio import ngs_grid
from michspc.fileio.ngs_grid import TileGeometry


def _data_directory() -> Path:
    """Where the shipped grids live, frozen or from source.

    PyInstaller sets ``sys._MEIPASS`` to the directory it unpacked the bundle's
    data files into, and nothing else sets it (docs/method/TOOLING.md). A source
    run walks up from this module instead: fileio -> michspc -> the repository
    root, then ``data/``.

    Stated here rather than imported from ``geoid18``: that module is the GEOID18
    *policy* layer, this one is the VERTCON policy layer, and a sibling importing
    a sibling for a path would couple two models that share only a directory -
    and would break at the ``geoid18.py`` to ``geoid.py`` rename plan section 3.4
    calls for. The same three lines already appear in ``geoid18.py``,
    ``gui/icon.py`` and ``selftest.py``; extracting all four into the substrate is
    worth doing and is not this work package's to do, since ``ngs_grid.py`` is
    gated code.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "data"
    return Path(__file__).resolve().parent.parent.parent / "data"


DATA_DIR = _data_directory()

VERTCON3_TRN_FILENAME = "vertcon_3.0_20190601.ngvd29.navd88.conus.oht.trn.b"
VERTCON3_ERR_FILENAME = "vertcon_3.0_20190601.ngvd29.navd88.conus.oht.err.b"
"""NGS's own filenames, unmodified.

The files are committed exactly as published so each stays byte-comparable
against its source and its SHA-256 can be pinned (DESIGN.md section 3). The name
carries the model, the release date, the datum pair, the region and the quantity,
which is why it is not shortened.
"""

VERTCON3_TRN_TILE = DATA_DIR / VERTCON3_TRN_FILENAME
VERTCON3_ERR_TILE = DATA_DIR / VERTCON3_ERR_FILENAME

VERTCON3_TRN_SHA256 = "2bd703f760e8fbb96b48173f762a1e4bc2e4bd0357e1a26201a96bb7a96b1cbe"
"""SHA-256 of the unmodified NGS transformation grid.

Source: https://geodesy.noaa.gov/pub/vertcon3/20190601release/Builds/
        ngvd29.navd88.conus/vertcon_3.0_20190601.ngvd29.navd88.conus.oht.trn.b
Downloaded 2026-08-07, 2,465,424 bytes (docs/PLAN-vertical-datums.md section 2.1).

Pinned because a substituted grid produces plausible wrong shifts. The concrete
substitution this guards against is not hypothetical: VERTCON **2.0** is what
both /PC_PROD/VERTCON/ and VDatum lead to, and measured against NCAT it is off by
up to 43.85 mm across Michigan where 3.0 is off by 2.657 mm (plan section 2.6).
Nothing about a 2.0 file's shape would give it away.
"""

VERTCON3_ERR_SHA256 = "496355e8617b0f0cdfb0fad9f0f96c8215aabe44ccf7039514e124d22af492cc"
"""SHA-256 of the unmodified NGS uncertainty grid. Same source directory, same
2,465,424 bytes, downloaded the same day (plan section 2.1)."""


VERTCON_MODEL_NAME = "VERTCON 3.0"
VERTCON_RELEASE = "20190601"
"""Model and release, spelled as ``spc/vertical.py`` spells them.

Kept as literals here rather than imported from the core, because the file layer
must not depend on the core to name the file it is reading, and because these are
what a refusal message says. ``tests/test_vertcon.py`` pins the two spellings
against each other so they cannot drift.
"""


class VertconError(Exception):
    """A VERTCON grid could not be read, or does not cover the point asked for.

    One class for the whole surface, for the reason ``geoid18.GeoidError`` is one
    class: a caller keeps a single ``except`` clause, and the substrate raises
    exactly what that clause catches. This is the class carried in the dialects
    below, so a structural refusal raised inside ``ngs_grid`` *is* a
    ``VertconError`` rather than a sibling of one.
    """


# --------------------------------------------------------------------------
# The two dialects. Both carry VertconError; they differ in what one cell holds
# and in what losing it costs, because those are different sentences for the
# shift and for the uncertainty that qualifies it.
# --------------------------------------------------------------------------

_TRANSFORMATION_DIALECT = ngs_grid.GridDialect(
    error=VertconError,
    model_name=VERTCON_MODEL_NAME,
    grid_noun="a VERTCON transformation grid",
    value_noun="vertical shift",
    outside_consequence=(
        "No NGVD 29 to NAVD 88 shift can be looked up, so the elevation cannot "
        "be moved between vertical datums. VERTCON 3.0 covers the conterminous "
        "United States only. Check the coordinate, the zone and the units."
    ),
    geometry_consequence=(
        "A header that misdescribes the grid does not fail: it re-shapes it, and "
        "every shift then comes from the wrong cell. A shift is a tenth of a "
        "metre in Michigan and lands in a Z column that looks exact, so a wrong "
        "one would read as an ordinary elevation. Refused rather than applied."
    ),
    payload_consequence=(
        "Every cell of a VERTCON transformation grid is a real number of metres; "
        "a NaN or infinity would be added to a surveyed elevation and travel "
        "silently into the converted height, so the file is refused rather than "
        "read."
    ),
)

_UNCERTAINTY_DIALECT = ngs_grid.GridDialect(
    error=VertconError,
    model_name=VERTCON_MODEL_NAME,
    grid_noun="a VERTCON uncertainty grid",
    value_noun="shift uncertainty",
    outside_consequence=(
        "No uncertainty can be looked up for the modeled shift. A VERTCON shift "
        "is reported only together with the uncertainty that qualifies it, "
        "because across Michigan that uncertainty runs from a fraction of a "
        "millimetre to 0.366 m, so the point is refused rather than converted."
    ),
    geometry_consequence=(
        "A header that misdescribes the grid does not fail: it re-shapes it, and "
        "the uncertainty then comes from the wrong cell. Since the uncertainty "
        "varies by a factor of hundreds across Michigan, a wrong cell can "
        "understate it by orders of magnitude while the shift beside it is "
        "printed to the millimetre. Refused rather than reported."
    ),
    payload_consequence=(
        "Every cell of a VERTCON uncertainty grid is a real number of metres; a "
        "NaN or infinity would be printed beside a shift as the figure that "
        "qualifies it, so the file is refused rather than read."
    ),
)


VERTCON3_CONUS_GEOMETRY = TileGeometry(
    south_latitude=24.0,
    west_longitude=235.0,  # 125 W in the file's 0-360 east convention
    latitude_spacing=0.05,
    longitude_spacing=0.05,
    row_count=521,
    column_count=1181,
    name="VERTCON 3.0 NGVD29 to NAVD88 CONUS grid (release 20190601)",
)
"""The geometry both shipped grids are known to have.

Source: the header of each file, read at the V0 gate and recorded in
docs/PLAN-vertical-datums.md section 2.2. Checkable by hand from the counts:

    north = 24.0  + (521 - 1)  * 0.05 = 24  + 26 = 50 N
    east  = 235.0 + (1181 - 1) * 0.05 = 235 + 59 = 294 E = 66 W

**One CONUS grid covers all of Michigan.** Michigan reaches 48.3 N and 90.5 W,
well inside 50 N and 125 W, so the 84 W seam an earlier draft of the plan
budgeted for does not exist - it was an artifact of VDatum's three-region split
of the superseded VERTCON 2.0 (plan sections 2.2 and 2.6).

**Why this record exists, given that the length check is stronger here than it is
for GEOID18.** 521 x 1181 and 1181 x 521 do not share a product, so a transposed
header is caught by file length alone - unlike GEOID18, where the geometry record
was the only thing that could catch it (DESIGN.md amendment #11, finding 6). The
record still earns its place for SLAT, WLON and the spacings, none of which the
length can see: a file claiming to start at 24 N when it starts at 25 N is the
right length and every lookup in it is one degree out.
"""


FORTRAN_MARKER = struct.Struct("<i")
"""The int32 record-length marker Fortran unformatted output writes around each
record. Little-endian, like the payload."""

MARKER_BYTES = FORTRAN_MARKER.size  # 4

HEADER_BLOCK_BYTES = MARKER_BYTES + ngs_grid.HEADER_BYTES + MARKER_BYTES
"""The bracketed header record: 4 + 44 + 4 = 52 bytes (plan section 2.2)."""

HEADER_OFFSET = MARKER_BYTES
"""Where the ``<4d3i`` record itself starts. ``ngs_grid.unpack_header`` takes
this as its ``offset``; GEOID18 passes 0."""

VALUE_BYTES = 4
"""One real*4 cell. IKIND = 1 is what says the cells are real*4, and
``require_supported_ikind`` refuses anything else."""


def _require_marker(path: Path, offset: int, found: int, expected: int, what: str) -> None:
    """Refuse a Fortran record marker that does not say what it must.

    if/raise rather than assert: the suite and the shipped program both run under
    ``-O``, which strips asserts (DESIGN.md section 7). This check is the
    structural gate the whole format hangs on, so it must survive optimisation.
    """
    if found != expected:
        raise VertconError(
            f"{path} has a bad Fortran record marker at byte {offset}: expected "
            f"{expected}, found {found}. {what} A {VERTCON_MODEL_NAME} grid "
            f"brackets every record with its own length as an int32, so a marker "
            f"that disagrees means the file is truncated, corrupt, written in "
            f"the big-endian byte order this reader does not handle, or is not "
            f"a VERTCON grid at all. Refused rather than read from the wrong "
            f"offset, which would produce ordinary-looking numbers."
        )


def sigma_is_physical(value_m: float) -> bool:
    """Whether an interpolated uncertainty is a quantity at all.

    Stated once because two places act on it and they must not be able to
    disagree: ``UncertaintyGrid.sigma_m``, which refuses, and
    ``VertconGridPair.reading_at``, which reports the sigma as unavailable. If
    the two rules drifted apart a position could be refused by one path and
    reported by the other, which is the same value arriving two ways - the thing
    DESIGN.md section 7 forbids.

    A one-sigma uncertainty is non-negative by definition. **Exactly 0.0 is
    admitted**, and that is not a boundary nicety: the smallest cell in the whole
    shipped uncertainty grid IS 0.0, so zero is a reading the model genuinely
    produces rather than an artifact of the interpolation leaving its range.
    """
    return value_m >= 0.0


@dataclass(frozen=True)
class TransformationGrid(ngs_grid.Grid):
    """The ``.trn`` grid: ``NAVD88 - NGVD29`` in metres.

    Read by the nearest-node-anchored biquadratic - see the module docstring for
    the measurement, and ``ngs_grid.interpolate_biquadratic`` for why GEOID18
    does not use the same anchoring.
    """

    dialect = _TRANSFORMATION_DIALECT

    def shift_m(self, latitude: float, longitude: float) -> float:
        """The modeled shift at a position, in metres.

        Signed as the grid stores it: ``NAVD88 - NGVD29``. Which direction that
        gets applied in belongs to ``spc.vertical``, not here. Metres, because
        that is the unit the file is published in (plan section 2.2); the
        conversion to a job's linear unit happens at the output boundary.

        The one accessor this class has, and it names no scheme in its own
        signature, so a caller cannot ask for the wrong one by accident.

        **This reads ONE grid at ONE position.** It is not half of a reading: a
        shift means little without the uncertainty that qualifies it, and a shift
        taken here beside a sigma taken at some other position would understate
        that uncertainty by up to 0.366 m with both numbers looking ordinary.
        Take the pair through ``VertconGridPair.reading_at``; reach for this only
        when the transformation grid alone is genuinely what is wanted.
        """
        return self.interpolate_biquadratic_nearest_node(latitude, longitude)


@dataclass(frozen=True)
class UncertaintyGrid(ngs_grid.Grid):
    """The ``.err`` grid: the one-sigma uncertainty of the modeled shift, metres.

    Read by the same nearest-node-anchored biquadratic as the transformation
    grid beside it. That the two match is a measured result and not a
    simplification: 0.472 mm against NCAT here and 0.471 mm there, both below
    NCAT's 0.5 mm printing quantization, where the floor-anchored variant reaches
    3.042 mm and bilinear 4.547 mm. Plan section 2.5's contrary finding is
    superseded and the module docstring says why.

    **One property the plan was right to worry about, and it survives the
    correction: this grid does not interpolate to a non-negative field.** The
    stored cells are non-negative - the smallest is exactly 0.0 - but a Lagrange
    quadratic is not monotone within its cell, so where the field is steep the
    interpolant undershoots past zero. Measured over Michigan at the grid's own
    0.05-degree spacing, offset half a cell, 22,848 positions: **114 return a
    negative value, worst -0.009652 m at 42.475 N, 83.125 W.** Bilinear would
    return none, and that is the whole of what plan section 2.5 had hold of.
    That sweep is not a claim about an experiment run elsewhere: it is
    ``tests/test_vertcon.py``, run against the committed grid on every suite run.

    A second sweep is committed beside it, the WP-V4 review gate's own: Michigan
    at 0.01-degree spacing, **1,848 negatives among 572,721 positions**, worst
    -0.028879586 m. Its two named positions are what the refusal below is aimed
    at:

        42.87 N, 83.81 W    -0.028879586 m, the worst the reviewer's sweep found
        42.475 N, 83.125 W  -0.009651646 m, where NCAT returns +0.011 m

    **NCAT does NOT return these negatives - that was checked, not inferred.**
    An earlier draft of this docstring reasoned that because the reader agrees
    with NCAT to 0.472 mm, NCAT must produce the same negatives and they are the
    published model's rather than ours. That inference is false. Asked directly
    at 42.475 N / 83.125 W, where this reader gives -0.00965 m, **NCAT returns
    +0.011 m** - a 20.7 mm disagreement, far outside anything else measured here.
    So at these positions this reader is wrong, not merely ugly.

    It is still not a reason to read this grid bilinearly. What is committed and
    checkable says so: over the 20 frozen NCAT anchors this scheme's worst
    residual is 0.4716 mm and bilinear's is 4.5468 mm, and this scheme reproduces
    NCAT's printed figure at 20 of 20 points against bilinear's 11. Trading that
    for the negatives would be a bad trade - although note honestly that at
    42.475 N / 83.125 W bilinear gives 0.010947 m, which does round to NCAT's
    0.011: the negatives are where the two schemes' overall ranking does not
    hold, which is why those positions refuse rather than being reported.

    **What the file layer does about it, decided at the WP-V4 review gate.** A
    reader may not clamp, so it does not: ``modeled_error_raw_m`` returns the
    unfiltered interpolation, negatives included, under a name that cannot be
    read as an uncertainty, and ``sigma_m`` refuses. Refusing is not the same as
    losing the point - the shift is a different grid and is unaffected, and
    ``VertconGridPair.reading_at`` still reports it with the sigma marked
    unavailable. How that unavailability is *shown* remains WP-V7's, and the
    owner's; what is settled here is only that a number which cannot be a
    one-sigma will not be handed out as one.
    """

    dialect = _UNCERTAINTY_DIALECT

    def modeled_error_raw_m(self, latitude: float, longitude: float) -> float:
        """The error grid interpolated at a position, raw and unfiltered, metres.

        The nearest-node-anchored biquadratic applied to the ``.err`` grid and
        returned exactly as it comes out, **including the values that are
        negative** - the class docstring says where, how often and how far.

        **Deliberately not named for sigma.** A negative number is not a
        one-sigma uncertainty, and the whole of the defect this method exists to
        answer was a method named ``sigma_m`` handing one out. A caller who wants
        to say what the model produced asks for it here, where the name says the
        value is model output rather than a quantity; a caller who wants an
        uncertainty asks ``sigma_m`` and is refused when there is none.

        Nothing is clamped and nothing is made positive. Zero would state a
        certainty the model does not have; ``abs()`` would state a figure nothing
        has measured - the undershoot is not a sign error and there is no
        evidence the reflected magnitude is the truth.

        **This reads ONE grid at ONE position**, exactly as
        ``TransformationGrid.shift_m`` does, and the same warning applies: a
        value from here does not qualify a shift read at some other position.
        """
        return self.interpolate_biquadratic_nearest_node(latitude, longitude)

    def sigma_m(self, latitude: float, longitude: float) -> float:
        """The one-sigma uncertainty of the modeled shift, in metres.

        **Fails closed where the model leaves the physically valid range.** A
        one-sigma uncertainty is non-negative by definition, so where
        ``modeled_error_raw_m`` comes out below zero this raises rather than
        returning it. Not clamping was right - a zero here would be a fabricated
        reading, which this module must never produce - but returning a negative
        through a method with this name is equally indefensible: it puts a number
        that cannot be an uncertainty exactly where a user reads one.

        The refusal states that the shift is unaffected, in as many words,
        because the conclusion a caller must not draw is "the elevation is bad".
        It is not. The shift comes from the transformation grid and nothing in it
        depends on this value; what is unavailable is the confidence figure.

        **This reads ONE grid at ONE position.** See
        ``VertconGridPair.reading_at`` for why the two halves are taken together.
        """
        value = self.modeled_error_raw_m(latitude, longitude)
        if not sigma_is_physical(value):
            raise VertconError(
                f"The {VERTCON_MODEL_NAME} error model interpolates to "
                f"{value!r} m at {latitude:.6f}, {longitude:.6f}, which cannot "
                f"be a one-sigma uncertainty: an uncertainty is never negative. "
                f"Every cell stored in the uncertainty grid is non-negative, but "
                f"the biquadratic is not monotone inside a cell, so where the "
                f"field is steep and close to zero the interpolation undershoots "
                f"past it. "
                f"THE SHIFT ITSELF IS STILL VALID AND UNAFFECTED: it is read "
                f"from the separate transformation grid and nothing about it "
                f"depends on this value. What is unavailable at this position is "
                f"the stated confidence in that shift, not the shift. Refused "
                f"rather than clamped to zero, which would claim a certainty the "
                f"model does not have, and rather than made positive, which "
                f"would state a figure nothing has measured."
            )
        return value


@dataclass(frozen=True)
class VertconGridPair:
    """The transformation grid and its companion uncertainty grid, together.

    Loaded and carried as a pair rather than as two independent grids, because
    the shift and the sigma are one reading: a shift published without its
    uncertainty is a modeled number presented as a measured one, which is the top
    risk DESIGN.md amendment #22 records against this whole feature. At 43.05 N,
    86.20 W the uncertainty is 249% of the shift (plan section 2.8).

    The constructor requires the two to share geometry. A mismatched pair would
    not fail anywhere downstream: it would report one position's shift beside
    another position's sigma, both plausible.

    **``reading_at`` is the only value accessor this class has**, and that is a
    correction rather than an original design. It carried ``shift_m`` and
    ``sigma_m`` as separate public methods, which let a caller take a shift at
    one position and a sigma at another through the pair itself - the reviewer's
    counterexample paired -0.143529 m at 43.05 N / 86.20 W with 0.000655 m at
    43.00 N / 84.50 W, where the true figure is 0.365599 m, understating the
    uncertainty by 0.365 m with both numbers looking entirely ordinary (WP-V4
    review, LOW 1). The pair now offers no way to take half a reading. Reading
    one grid alone is still possible and still legitimate - through
    ``.transformation`` or ``.uncertainty``, where the expression itself says
    which grid is being read and no pairing is implied.
    """

    transformation: TransformationGrid
    uncertainty: UncertaintyGrid

    def __post_init__(self) -> None:
        # if/raise, never assert: -O strips asserts (DESIGN.md section 7), and
        # this is the check that makes the pair a pair.
        mismatches: list[str] = []
        for label, attribute in (
            ("SLAT (southernmost latitude)", "south_latitude"),
            ("WLON (westernmost longitude, east of Greenwich)", "west_longitude"),
            ("DLAT (north-south spacing)", "latitude_spacing"),
            ("DLON (east-west spacing)", "longitude_spacing"),
            ("NLAT (row count)", "row_count"),
            ("NLON (column count)", "column_count"),
        ):
            trn = getattr(self.transformation, attribute)
            err = getattr(self.uncertainty, attribute)
            if trn != err:
                mismatches.append(
                    f"  {label}: transformation grid {trn!r}, uncertainty grid "
                    f"{err!r}"
                )

        if mismatches:
            raise VertconError(
                f"The {VERTCON_MODEL_NAME} transformation grid "
                f"{self.transformation.path} and uncertainty grid "
                f"{self.uncertainty.path} do not describe the same "
                f"geometry:\n" + "\n".join(mismatches) + "\n"
                f"NGS publishes them on identical geometry. A mismatched pair "
                f"does not fail when it is read: it reports one position's shift "
                f"beside a different position's uncertainty, and both look "
                f"ordinary. Refused rather than paired."
            )

    def contains(self, latitude: float, longitude: float) -> bool:
        """Whether both grids cover the position.

        Both, not either. They share geometry by the check above, so this is one
        question; asking it of both is what keeps that true if the check is ever
        weakened.
        """
        return self.transformation.contains(
            latitude, longitude
        ) and self.uncertainty.contains(latitude, longitude)

    def reading_at(
        self, latitude: float, longitude: float
    ) -> tuple[float, float | None]:
        """``(shift_m, sigma_m)`` at one position, both in metres.

        The front door, and the only value accessor this class has. Taking both
        in one call is what makes it awkward to report a shift and forget the
        figure that qualifies it, and impossible to pair the two from different
        positions - see the class docstring. A position outside the grids refuses
        here rather than yielding one of the two.

        **``sigma`` is ``None`` where the error model interpolates to a negative
        value**, which is not an uncertainty (``UncertaintyGrid.sigma_m``). The
        shift is still returned and is still valid: it is read from the
        transformation grid and nothing in it depends on the uncertainty. That
        shape - the number absent, the point kept - is the one ``job.py`` already
        uses for a point whose elevation is real but whose geoid height is not
        available, where it sets the height to None and says so in a warning
        rather than inventing a value or discarding the point. A caller that
        needs to explain the absence gets the model's own words by calling
        ``uncertainty.sigma_m`` and the raw figure from
        ``uncertainty.modeled_error_raw_m``.

        No ``try`` around either read, deliberately: an outside-the-grid refusal
        from ``.err`` must reach the caller, and a handler here that turned it
        into a ``None`` sigma would swallow it. The negative case is decided by
        asking ``sigma_is_physical`` directly - the same rule ``sigma_m`` raises
        on - so the two cannot answer differently.
        """
        shift = self.transformation.shift_m(latitude, longitude)
        raw = self.uncertainty.modeled_error_raw_m(latitude, longitude)
        return (shift, raw if sigma_is_physical(raw) else None)


def _unpack_payload(path: Path, raw: bytes, rows: int, columns: int) -> tuple[float, ...]:
    """Every cell, row-major, with the Fortran marker on each row validated.

    Southernmost row first, each row west to east - the order the substrate's
    ``Grid._value`` indexes. Each row is bracketed by an int32 holding the row's
    length in bytes, ``NLON * 4``.

    Raises on anything it cannot read. There is deliberately no fallback: a cell
    this function invented would be indistinguishable from a real reading,
    because the ``.trn`` grid genuinely takes every value including zero inside
    Michigan.
    """
    row_bytes = columns * VALUE_BYTES
    expected_total = HEADER_BLOCK_BYTES + rows * (MARKER_BYTES + row_bytes + MARKER_BYTES)
    if len(raw) != expected_total:
        raise VertconError(
            f"{path} declares {rows} rows of {columns} cells, which is "
            f"{expected_total} bytes with the Fortran record markers "
            f"({HEADER_BLOCK_BYTES} for the bracketed header, then {rows} rows "
            f"of {MARKER_BYTES} + {row_bytes} + {MARKER_BYTES}), but the file is "
            f"{len(raw)} bytes. It is truncated, corrupt, or does not have the "
            f"shape its own header claims."
        )

    row_format = struct.Struct(f"<{columns}f")
    values: list[float] = []
    offset = HEADER_BLOCK_BYTES
    for row in range(rows):
        leading = FORTRAN_MARKER.unpack_from(raw, offset)[0]
        _require_marker(
            path,
            offset,
            leading,
            row_bytes,
            f"It opens row {row} of {rows}, counting north from SLAT.",
        )
        offset += MARKER_BYTES

        values.extend(row_format.unpack_from(raw, offset))
        offset += row_bytes

        trailing = FORTRAN_MARKER.unpack_from(raw, offset)[0]
        _require_marker(
            path,
            offset,
            trailing,
            row_bytes,
            f"It closes row {row} of {rows}, counting north from SLAT.",
        )
        offset += MARKER_BYTES

    # No bytes-consumed check after this loop, and its absence is deliberate.
    # Plan section 2.2 asked for one and it was written; the WP-V4 review gate
    # showed it could not fail. ``expected_total`` above is
    # HEADER_BLOCK_BYTES + rows * (MARKER + row_bytes + MARKER), the loop runs
    # exactly ``rows`` times and advances by exactly that stride, and the file
    # has already been required to be ``expected_total`` bytes - so
    # ``offset == len(raw)`` is arithmetic, not a test, and no input can reach
    # the refusal. It was advertised as an independent structural gate and was
    # not one, which is worse than not having it: a dead check reads as a
    # defence in place. What the two would have said between them is said by the
    # length check, and ``tests/test_vertcon.py`` walks both shipped files with
    # its own arithmetic, independent of this function, and requires that walk to
    # land on the last byte.
    return tuple(values)


def load_grid(
    path: Path,
    kind: type[TransformationGrid] | type[UncertaintyGrid],
    expect_sha256: str | None = None,
    expect_geometry: TileGeometry | None = None,
) -> TransformationGrid | UncertaintyGrid:
    """Read one VERTCON 3.0 ``.b`` grid.

    ``kind`` is ``TransformationGrid`` or ``UncertaintyGrid``. It selects the
    dialect a refusal speaks and, with it, the interpolation scheme the loaded
    grid will read by - the two files are byte-identical in shape and tell you
    nothing about which quantity they hold, so the caller has to say.

    ``expect_sha256`` re-hashes the whole 2.4 MB file. ``expect_geometry``
    additionally requires the header to describe a named, known tile. Both are
    optional so this function stays usable for a VERTCON build this program does
    not ship; the production path passes both, and that path is
    ``load_shipped_grids``.

    Every refusal raises ``VertconError``. Nothing here returns a substitute
    value.
    """
    if kind not in (TransformationGrid, UncertaintyGrid):
        raise TypeError(
            f"load_grid needs michspc.fileio.vertcon.TransformationGrid or "
            f"UncertaintyGrid as its kind; got {kind!r}. The two VERTCON files "
            f"have the identical shape and differ only in what a cell means and "
            f"how it must be interpolated, so the caller states which one it is "
            f"reading."
        )

    path = Path(path)
    dialect = kind.dialect

    try:
        raw = path.read_bytes()
    except OSError as error:
        raise VertconError(
            f"Could not read the {VERTCON_MODEL_NAME} grid at {path}: {error}. "
            f"This file ships with the program; if it is missing the "
            f"installation is incomplete."
        ) from error

    if len(raw) < HEADER_BLOCK_BYTES:
        raise VertconError(
            f"{path} is only {len(raw)} bytes, too short to contain the "
            f"{HEADER_BLOCK_BYTES}-byte bracketed {VERTCON_MODEL_NAME} header "
            f"({MARKER_BYTES}-byte Fortran marker, {ngs_grid.HEADER_BYTES}-byte "
            f"record, {MARKER_BYTES}-byte marker). The file is truncated or is "
            f"not a VERTCON grid."
        )

    if expect_sha256 is not None:
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expect_sha256:
            raise VertconError(
                f"{path} does not match the {VERTCON_MODEL_NAME} grid this "
                f"program was built against.\n  expected SHA-256 "
                f"{expect_sha256}\n  found    SHA-256 {digest}\n"
                f"The substitution this catches is a real one: VERTCON 2.0 is "
                f"what the older NGS directory and VDatum both lead to, and it "
                f"disagrees with NGS's own service by up to 43.85 mm across "
                f"Michigan while looking exactly like a VERTCON grid. Shifts "
                f"from an unverified grid are refused."
            )

    # The first structural statement the file makes. Checked before the header
    # is unpacked, because if the markers are wrong the header is not at byte 4
    # and everything read from there is fiction. It is also what distinguishes
    # this format from GEOID18's: the first four bytes of g2018u3.bin are the low
    # half of SLAT = 40.0, which is zero, not 44.
    _require_marker(
        path,
        0,
        FORTRAN_MARKER.unpack_from(raw, 0)[0],
        ngs_grid.HEADER_BYTES,
        "It opens the header record.",
    )
    _require_marker(
        path,
        MARKER_BYTES + ngs_grid.HEADER_BYTES,
        FORTRAN_MARKER.unpack_from(raw, MARKER_BYTES + ngs_grid.HEADER_BYTES)[0],
        ngs_grid.HEADER_BYTES,
        "It closes the header record.",
    )

    header = ngs_grid.unpack_header(raw, HEADER_OFFSET)
    south = header.south_latitude
    west = header.west_longitude
    dlat = header.latitude_spacing
    dlon = header.longitude_spacing
    rows = header.row_count
    columns = header.column_count

    ngs_grid.require_supported_ikind(dialect, path, header.ikind)
    ngs_grid.require_readable_header(
        dialect, path, south, west, dlat, dlon, rows, columns
    )

    if expect_geometry is not None:
        ngs_grid.require_canonical_geometry(
            dialect, path, expect_geometry, south, west, dlat, dlon, rows, columns
        )

    values = _unpack_payload(path, raw, rows, columns)

    # Plan section 2.7: there are no sentinels and no non-finite values in either
    # shipped file - measured, 0 of 23,120 Michigan cells per grid, and no
    # -88.8888 (that null is a VDatum GTX convention absent from the NGS .b
    # files). The check is here because load_grid accepts any path.
    ngs_grid.require_finite_payload(dialect, path, values)

    return kind(
        path=path,
        south_latitude=south,
        west_longitude=west,
        latitude_spacing=dlat,
        longitude_spacing=dlon,
        row_count=rows,
        column_count=columns,
        values=values,
    )


def load_shipped_grids(
    transformation_path: Path | None = None,
    uncertainty_path: Path | None = None,
) -> VertconGridPair:
    """Load the pair this program ships, fully authenticated.

    The production policy in one place: each file's SHA-256 must match the pinned
    digest of the unmodified NGS file, **and** each header must describe the
    geometry those tiles are known to have, **and** the two must agree with each
    other. Three gates that fail differently - the checksum catches any altered
    byte, the geometry check catches a file that is internally consistent and
    describes the wrong grid, and the pairing check catches two files that are
    each individually fine and are not companions.

    Takes paths only so the checks themselves can be exercised against a
    deliberately tampered copy in a test. Nothing in the program passes one.
    """
    transformation = load_grid(
        transformation_path or VERTCON3_TRN_TILE,
        TransformationGrid,
        expect_sha256=VERTCON3_TRN_SHA256,
        expect_geometry=VERTCON3_CONUS_GEOMETRY,
    )
    uncertainty = load_grid(
        uncertainty_path or VERTCON3_ERR_TILE,
        UncertaintyGrid,
        expect_sha256=VERTCON3_ERR_SHA256,
        expect_geometry=VERTCON3_CONUS_GEOMETRY,
    )
    return VertconGridPair(transformation=transformation, uncertainty=uncertainty)


@lru_cache(maxsize=1)
def default_grids() -> VertconGridPair:
    """The shipped pair, loaded once per process.

    A file of several thousand points would otherwise re-read, re-hash and
    re-unpack two 2.4 MB files per row.

    **Authenticated**, for the reason ``geoid18.default_grid`` is: this is the
    path production actually takes, so it takes the checked one. The alternative
    is a running program that trusts whatever bytes are on disk, which is
    DESIGN.md amendment #11's finding 6.
    """
    return load_shipped_grids()


def shift_and_sigma_m(
    latitude: float,
    longitude: float,
    grids: VertconGridPair | None = None,
) -> tuple[float, float | None]:
    """``(shift_m, sigma_m)`` at a position, both metres, from the shipped pair.

    The module's front door, shaped like ``geoid18.geoid_height``. The shift is
    ``NAVD88 - NGVD29`` as the grid stores it; ``spc.vertical.apply_shift`` is
    what decides which way it goes and says so in words.

    ``sigma`` is ``None`` where the error model interpolates to a value that
    cannot be an uncertainty; the shift beside it is unaffected. See
    ``VertconGridPair.reading_at``.
    """
    grids = grids or default_grids()
    return grids.reading_at(latitude, longitude)
