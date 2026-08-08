"""The shared NGS binary-grid substrate, exercised on its own terms.

``tests/test_geoid.py`` drives this code through ``geoid``'s public API, which
is what proves the extraction changed no behaviour. These tests do the opposite:
they hand the substrate a grid that is **not** a geoid - a 3x3 lattice of made-up
numbers under a made-up dialect - so the parts that are genuinely generic are
pinned as generic rather than as an accident of the one caller that exists today.

That distinction is the point of the extraction (docs/PLAN-vertical-datums.md
section 3.2). The VERTCON reader WP-V4 adds needs the same header record, the
same geometry checking and both interpolators, and it must raise **its own**
exception class carrying **its own** wording - because ``michspc/job.py`` catches
``geoid.GeoidError`` by name and a shared base class would stop being caught.
The dialect seam is what makes that true, so it is tested here directly, with an
anti-vacuousness check proving a second dialect really does get its own class.

Every expected value below is derived by hand in the comment above it.
"""

from __future__ import annotations

import dataclasses
import math
import struct
from pathlib import Path

import pytest

from michspc.fileio import geoid, ngs_grid

# --------------------------------------------------------------------------
# A dialect and a grid that have nothing to do with geoid heights.
# --------------------------------------------------------------------------


class SampleError(Exception):
    """Stands in for the exception class a policy layer already owns."""


class OtherError(Exception):
    """A second one, used only to prove the first was not hard-coded."""


SAMPLE_DIALECT = ngs_grid.GridDialect(
    error=SampleError,
    model_name="TESTMODEL",
    grid_noun="a test grid",
    value_noun="test value",
    outside_consequence="Nothing can be said about that position.",
    geometry_consequence="The header does not describe the tile it claims to be.",
    payload_consequence="A non-finite cell would travel silently downstream.",
)

OTHER_DIALECT = dataclasses.replace(
    SAMPLE_DIALECT, error=OtherError, model_name="OTHERMODEL"
)


@dataclasses.dataclass(frozen=True)
class SampleGrid(ngs_grid.Grid):
    """The substrate's grid under a non-geoid dialect."""

    dialect = SAMPLE_DIALECT


# A 3x3 lattice on whole degrees, so every hand derivation below is exact in
# binary and can be pinned with ``==`` rather than a tolerance.
#
#   south 40 N, three rows one degree apart  -> 40, 41, 42 N
#   west  260 E, three columns one degree apart -> 260, 261, 262 E
#                                               = -100, -99, -98 signed
#
# Values, row-major, southernmost row first, each row west to east:
#
#       lon ->   -100    -99    -98
#   lat 42 N      60      90    130
#   lat 41 N      30      50     80
#   lat 40 N      10      20     40
LATTICE = (10.0, 20.0, 40.0, 30.0, 50.0, 80.0, 60.0, 90.0, 130.0)


def sample_grid(values=LATTICE, rows: int = 3, columns: int = 3) -> SampleGrid:
    return SampleGrid(
        path="<lattice>",
        south_latitude=40.0,
        west_longitude=260.0,
        latitude_spacing=1.0,
        longitude_spacing=1.0,
        row_count=rows,
        column_count=columns,
        values=values,
    )


# --------------------------------------------------------------------------
# The header record.
# --------------------------------------------------------------------------


def test_the_header_struct_is_the_44_byte_ngs_record():
    """Four real*8 then three int*4, little-endian.

    Hand derivation of the size: 4 * 8 + 3 * 4 = 32 + 12 = 44 bytes.
    """
    assert ngs_grid.HEADER.format == "<4d3i"
    assert ngs_grid.HEADER_BYTES == 44
    assert ngs_grid.HEADER.size == 4 * 8 + 3 * 4


def test_unpack_header_reads_the_seven_fields_in_order():
    """The field order is the format's, not a guess.

    Packed here in the documented order - SLAT, WLON, DLAT, DLON, NLAT, NLON,
    IKIND - and each must come back out of the named attribute that claims it.
    """
    raw = struct.pack("<4d3i", 24.0, 235.0, 0.05, 0.05, 521, 1181, 1)
    header = ngs_grid.unpack_header(raw)

    assert header.south_latitude == 24.0
    assert header.west_longitude == 235.0
    assert header.latitude_spacing == 0.05
    assert header.longitude_spacing == 0.05
    assert header.row_count == 521
    assert header.column_count == 1181
    assert header.ikind == 1


def test_unpack_header_reads_at_an_offset():
    """VERTCON brackets the same record with Fortran markers; GEOID18 does not.

    So the identical struct sits at byte 4 in one format and byte 0 in the
    other (docs/PLAN-vertical-datums.md section 2.2), and the offset is the only
    difference. Built here as VERTCON stores it: an int32 marker of 44, the
    record, then the closing marker.
    """
    record = struct.pack("<4d3i", 24.0, 235.0, 0.05, 0.05, 521, 1181, 1)
    raw = struct.pack("<i", 44) + record + struct.pack("<i", 44)

    assert len(raw) == 4 + 44 + 4 == 52
    assert ngs_grid.unpack_header(raw, 4) == ngs_grid.unpack_header(record, 0)
    assert ngs_grid.unpack_header(raw, 4).row_count == 521


# --------------------------------------------------------------------------
# Longitude convention and the Lagrange basis.
# --------------------------------------------------------------------------


def test_longitude_conversion_is_a_round_trip_either_way():
    """The files store 0-360 east; this program uses signed, negative west.

    Hand check: -84.5 W + 360 = 275.5 E, and 275.5 E - 360 = -84.5. A positive
    signed longitude is already east of Greenwich and is left alone.
    """
    assert ngs_grid.to_east_longitude(-84.5) == 275.5
    assert ngs_grid.to_east_longitude(-125.0) == 235.0
    assert ngs_grid.to_east_longitude(12.0) == 12.0
    assert ngs_grid.to_signed_longitude(275.5) == -84.5
    assert ngs_grid.to_signed_longitude(235.0) == -125.0
    assert ngs_grid.to_signed_longitude(12.0) == 12.0


def test_lagrange3_reproduces_a_quadratic_it_was_not_fitted_to():
    """Exactness on a quadratic is the whole claim of the basis.

    Hand derivation with g(x) = -x^2 + 4x + 1 at nodes 0, 1, 2:
        g(0) = 1, g(1) = -1 + 4 + 1 = 4, g(2) = -4 + 8 + 1 = 5
        g(0.25) = -0.0625 + 1 + 1 = 1.9375
        g(1.75) = -3.0625 + 7 + 1 = 4.9375
    """
    values = [1.0, 4.0, 5.0]
    assert ngs_grid.lagrange3(values, 0.0) == 1.0
    assert ngs_grid.lagrange3(values, 1.0) == 4.0
    assert ngs_grid.lagrange3(values, 2.0) == 5.0
    assert ngs_grid.lagrange3(values, 0.25) == pytest.approx(1.9375)
    assert ngs_grid.lagrange3(values, 1.75) == pytest.approx(4.9375)


def test_the_lagrange_weights_sum_to_one_everywhere():
    """A partition of unity, so a constant field stays constant.

    Hand derivation: with all three nodes equal to 1, the interpolant is
    L0 + L1 + L2 = (x-1)(x-2)/2 + x(2-x) + x(x-1)/2, which expands to
    (x^2 - 3x + 2)/2 + (2x - x^2) + (x^2 - x)/2 = 1 for every x.
    """
    for x in (-0.5, 0.0, 0.3, 1.0, 1.5, 2.0, 2.5):
        assert ngs_grid.lagrange3([1.0, 1.0, 1.0], x) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Geometry.
# --------------------------------------------------------------------------


def test_the_grid_extents_come_from_the_counts_and_the_spacing():
    """Hand check on the lattice above:

        north = 40 + (3 - 1) * 1 = 42 N
        east  = 260 + (3 - 1) * 1 = 262 E = 262 - 360 = -98
    """
    grid = sample_grid()
    assert grid.north_latitude == 42.0
    assert grid.east_longitude == 262.0
    assert ngs_grid.to_signed_longitude(grid.east_longitude) == -98.0


def test_contains_is_inclusive_at_every_edge():
    """The corners are inside, a hair beyond any of them is not.

    Extents are 40 to 42 N and -100 to -98, derived above.
    """
    grid = sample_grid()

    for latitude in (40.0, 42.0):
        for longitude in (-100.0, -98.0):
            assert grid.contains(latitude, longitude)

    assert not grid.contains(39.999, -99.0)
    assert not grid.contains(42.001, -99.0)
    assert not grid.contains(41.0, -100.001)
    assert not grid.contains(41.0, -97.999)


def test_a_node_is_reproduced_exactly_by_both_schemes():
    """At the centre node both schemes must return that node's stored value.

    The centre node is row 1, column 1 - 41 N, -99 - and the lattice stores
    50.0 there. Bilinear anchors its 2x2 at row 1 with dr = dc = 0 and returns
    the corner directly; biquadratic anchors its 3x3 at row 0 with dr = dc = 1,
    where the Lagrange weights are L0 = 0, L1 = 1, L2 = 0, so it selects the
    middle node.
    """
    grid = sample_grid()
    assert grid.interpolate_bilinear(41.0, -99.0) == 50.0
    assert grid.interpolate_biquadratic(41.0, -99.0) == 50.0


# --------------------------------------------------------------------------
# The two interpolators, which are genuinely different and must stay so.
# --------------------------------------------------------------------------


def test_bilinear_interpolation_hand_derived():
    """At 40.5 N, -99.75 the fractional indices are row 0.5, column 0.25.

    Bilinear anchors the 2x2 at row 0, column 0, so dr = 0.5 and dc = 0.25 over
    the corners v00 = 10, v01 = 20, v10 = 30, v11 = 50:

        south edge = 10 + (20 - 10) * 0.25 = 12.5
        north edge = 30 + (50 - 30) * 0.25 = 35.0
        result     = 12.5 + (35.0 - 12.5) * 0.5 = 12.5 + 11.25 = 23.75
    """
    # -99.75 is 260.25 E, one quarter of a cell east of the western edge.
    assert sample_grid().interpolate_bilinear(40.5, -99.75) == 23.75


def test_biquadratic_interpolation_hand_derived():
    """Same position, 3x3 Lagrange, anchored at row 0, column 0 by the clamp.

    Weights along a row at dc = 0.25:
        L0 = (0.25-1)(0.25-2)/2 = (-0.75)(-1.75)/2 =  0.65625
        L1 = 0.25 * (2 - 0.25)                     =  0.4375
        L2 = 0.25 * (0.25-1)/2                     = -0.09375   (sum 1.0)

    Applied to each row of the lattice:
        row 0 [10, 20, 40]:   6.5625 +  8.750 -  3.7500 = 11.5625
        row 1 [30, 50, 80]:  19.6875 + 21.875 -  7.5000 = 34.0625
        row 2 [60, 90, 130]: 39.3750 + 39.375 - 12.1875 = 66.5625

    Weights along the column at dr = 0.5:
        L0 = (0.5-1)(0.5-2)/2 = (-0.5)(-1.5)/2 =  0.375
        L1 = 0.5 * (2 - 0.5)                   =  0.75
        L2 = 0.5 * (0.5-1)/2                   = -0.125     (sum 1.0)

        11.5625*0.375 + 34.0625*0.75 - 66.5625*0.125
      =  4.3359375    + 25.546875    -  8.3203125
      = 21.5625
    """
    assert sample_grid().interpolate_biquadratic(40.5, -99.75) == 21.5625


def test_the_two_schemes_are_not_the_same_computation():
    """23.75 against 21.5625 at the same position - a 2.1875 difference.

    Both numbers are derived by hand in the two tests above. The pin matters
    because the substrate now offers both to two callers that want different
    ones (docs/PLAN-vertical-datums.md section 2.5: VERTCON's transformation
    grid is read biquadratically and its uncertainty grid bilinearly), so
    "simplify these into one" is exactly the change that must fail loudly.
    """
    grid = sample_grid()
    bilinear = grid.interpolate_bilinear(40.5, -99.75)
    biquadratic = grid.interpolate_biquadratic(40.5, -99.75)

    assert bilinear != biquadratic
    assert bilinear - biquadratic == 2.1875


def test_biquadratic_is_exact_on_a_field_quadratic_in_both_directions():
    """The property that makes the scheme worth its extra cells.

    A tensor product of Lagrange quadratics reproduces exactly any field that
    is a polynomial of degree at most two in each variable. Take

        f(r, c) = r^2 + c^2 + r*c

    over the integer nodes r, c in {0, 1, 2}:

        f(0,0)=0  f(0,1)=1  f(0,2)=4
        f(1,0)=1  f(1,1)=3  f(1,2)=7
        f(2,0)=4  f(2,1)=7  f(2,2)=12

    At r = 0.5, c = 0.25:
        f = 0.25 + 0.0625 + 0.125 = 0.4375

    Bilinear cannot reproduce it, and its error is derived too:
        south edge = 0 + (1 - 0) * 0.25 = 0.25
        north edge = 1 + (3 - 1) * 0.25 = 1.5
        result     = 0.25 + (1.5 - 0.25) * 0.5 = 0.875
    """
    quadratic = (0.0, 1.0, 4.0, 1.0, 3.0, 7.0, 4.0, 7.0, 12.0)
    grid = sample_grid(values=quadratic)

    assert grid.interpolate_biquadratic(40.5, -99.75) == pytest.approx(0.4375)
    assert grid.interpolate_bilinear(40.5, -99.75) == pytest.approx(0.875)


# --------------------------------------------------------------------------
# The dialect seam: the substrate speaks the caller's language and raises the
# caller's exception class.
# --------------------------------------------------------------------------


def test_a_position_outside_the_grid_is_refused_in_the_dialects_own_words():
    """The extents in the message are the ones derived above: 40-42 N, -100 to -98."""
    grid = sample_grid()

    with pytest.raises(SampleError) as caught:
        grid.interpolate_biquadratic(39.5, -99.0)

    assert str(caught.value) == (
        "Position 39.500000, -99.000000 is outside the TESTMODEL tile this "
        "program ships (40.0 to 42.0 N, -100.0 to -98.0). "
        "Nothing can be said about that position."
    )


def test_both_interpolators_refuse_an_outside_position():
    """Neither scheme is a way around the bounds check."""
    grid = sample_grid()
    for interpolate in (grid.interpolate_bilinear, grid.interpolate_biquadratic):
        with pytest.raises(SampleError):
            interpolate(41.0, -97.0)


def test_the_substrate_raises_the_dialects_class_and_not_a_shared_one():
    """Anti-vacuousness for the seam, and the reason the seam exists.

    ``michspc/job.py`` catches ``geoid.GeoidError`` by name. If the substrate
    raised a class of its own - even a base class - that except clause would
    stop catching, and a missing geoid height would escape as an unhandled
    exception instead of becoming a named refusal on one row. So the same
    substrate call, under two dialects, must raise two unrelated classes.
    """
    with pytest.raises(SampleError):
        ngs_grid.require_supported_ikind(SAMPLE_DIALECT, "<f>", 2)

    with pytest.raises(OtherError):
        ngs_grid.require_supported_ikind(OTHER_DIALECT, "<f>", 2)

    assert not issubclass(SampleError, OtherError)
    assert not issubclass(OtherError, SampleError)


def test_the_geoid_dialect_carries_the_class_job_py_catches():
    """The live instance of the property above.

    Stated here rather than left implicit: this one identity is what keeps
    ``except geoid.GeoidError`` in ``job.py`` and in ``selftest.py`` correct
    now that the refusals are raised from another module.
    """
    assert geoid.GEOID_DIALECT.error is geoid.GeoidError
    assert geoid.GEOID_DIALECT.model_name == geoid.GEOID_MODEL_NAME
    assert geoid.GeoidGrid.dialect is geoid.GEOID_DIALECT


# --------------------------------------------------------------------------
# Header refusals, on a grid that is not a geoid grid.
# --------------------------------------------------------------------------


def _readable(dialect=SAMPLE_DIALECT, south=40.0, west=260.0, dlat=1.0, dlon=1.0,
              rows=3, columns=3):
    ngs_grid.require_readable_header(
        dialect, "<f>", south, west, dlat, dlon, rows, columns
    )


def test_a_sane_header_passes_every_generic_check():
    """The checks below must not simply refuse everything."""
    _readable()


def test_a_non_positive_or_non_finite_spacing_is_refused_by_name():
    """The interpolators divide by the spacing, so zero is not a small number."""
    for dlat in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(SampleError, match="DLAT"):
            _readable(dlat=dlat)

    for dlon in (0.0, -1.0, float("nan")):
        with pytest.raises(SampleError, match="DLON"):
            _readable(dlon=dlon)


def test_the_spacing_refusal_uses_the_dialects_nouns():
    """A shared check must not produce a message about geoid heights."""
    with pytest.raises(SampleError) as caught:
        _readable(dlat=0.0)

    message = str(caught.value)
    assert "produce a non-finite test value" in message
    assert "is not a test grid" in message
    assert "geoid" not in message


def test_a_grid_too_small_for_the_stencil_is_refused():
    """Below three rows or columns the biquadratic clamp goes negative.

    ``MINIMUM_INTERPOLATION_SPAN`` is 3 because the 3x3 stencil needs three of
    each; the clamp ``min(max(int(row) - 1, 0), row_count - 3)`` evaluates to
    -1 for a two-row grid.
    """
    assert ngs_grid.MINIMUM_INTERPOLATION_SPAN == 3

    for rows in (0, 1, 2):
        with pytest.raises(SampleError, match=f"NLAT={rows}"):
            _readable(rows=rows)

    for columns in (0, 1, 2):
        with pytest.raises(SampleError, match=f"NLON={columns}"):
            _readable(columns=columns)

    _readable(rows=3, columns=3)


def test_the_stencil_refusal_is_not_ceremony():
    """Anti-vacuousness: a 2x2 grid does not fail, it reads the wrong cells.

    Python's negative indexing is what makes this quiet. On a 2x2 grid at
    40.5 N, -99.5 the fractional indices are row 0.5, column 0.5, and the clamp
    gives row0 = col0 = min(max(-1, 0), 2 - 3) = min(0, -1) = -1, so
    dr = dc = 1.5 and the stencil reads ``values[row * 2 + column]`` at indices
    that wrap around the end of a four-element array:

        (-1,-1) -> values[-3] = 2.0   (-1,0) -> values[-2] = 3.0
        (-1, 1) -> values[-1] = 4.0   ( 0,-1) -> values[-1] = 4.0
        ( 0, 0) -> values[ 0] = 1.0   ( 0, 1) -> values[ 1] = 2.0
        ( 1,-1) -> values[ 1] = 2.0   ( 1, 0) -> values[ 2] = 3.0
        ( 1, 1) -> values[ 3] = 4.0

    Row weights at dc = 1.5 are L0 = -0.125, L1 = 0.75, L2 = 0.375 (sum 1.0):
        row -1: 2(-0.125) + 3(0.75) + 4(0.375) = -0.25 + 2.25 + 1.5   = 3.5
        row  0: 4(-0.125) + 1(0.75) + 2(0.375) = -0.5  + 0.75 + 0.75  = 1.0
        row  1: 2(-0.125) + 3(0.75) + 4(0.375) = -0.25 + 2.25 + 1.5   = 3.5

    Column weights at dr = 1.5 are the same three:
        3.5(-0.125) + 1.0(0.75) + 3.5(0.375) = -0.4375 + 0.75 + 1.3125 = 1.625

    1.625 sits inside the range of the four stored values, so nothing anywhere
    downstream could tell it was assembled from wrapped indices. That is what
    the header check prevents.
    """
    tiny = sample_grid(values=(1.0, 2.0, 3.0, 4.0), rows=2, columns=2)

    assert tiny.interpolate_biquadratic(40.5, -99.5) == 1.625
    assert 1.0 < 1.625 < 4.0

    with pytest.raises(SampleError, match="NLAT=2"):
        _readable(rows=2, columns=2)


def test_a_latitude_that_is_not_a_latitude_is_refused():
    """SLAT outside -90..90, or non-finite, is the big-endian tell."""
    for south in (-90.001, 90.001, 999.0, float("nan"), float("inf")):
        with pytest.raises(SampleError, match="SLAT"):
            _readable(south=south)

    for south in (-90.0, 0.0, 90.0):
        _readable(south=south)


def test_a_westernmost_longitude_outside_0_360_is_refused():
    """The format stores WLON in degrees EAST on 0-360, never signed."""
    for west in (-0.001, -84.5, 360.001, float("nan")):
        with pytest.raises(SampleError, match="WLON"):
            _readable(west=west)

    for west in (0.0, 235.0, 360.0):
        _readable(west=west)


def test_an_unsupported_ikind_is_refused_before_anything_else_is_read():
    """IKIND is the endian marker: a big-endian grid read here yields numbers."""
    ngs_grid.require_supported_ikind(SAMPLE_DIALECT, "<f>", 1)

    for ikind in (0, 2, 16777216):
        with pytest.raises(SampleError, match=f"IKIND={ikind}"):
            ngs_grid.require_supported_ikind(SAMPLE_DIALECT, "<f>", ikind)


# --------------------------------------------------------------------------
# Canonical geometry.
# --------------------------------------------------------------------------

SAMPLE_GEOMETRY = ngs_grid.TileGeometry(
    south_latitude=24.0,
    west_longitude=235.0,
    latitude_spacing=0.05,
    longitude_spacing=0.05,
    row_count=521,
    column_count=1181,
    name="a test tile",
)
"""The VERTCON 3.0 CONUS geometry, used here purely as a non-geoid example
(docs/PLAN-vertical-datums.md section 2.2: 24-50 N, 235-294 E, 521 x 1181 at
0.05 degrees). Hand check of the extents:

    north = 24.0  + (521 - 1)  * 0.05 = 24  + 26 = 50 N
    east  = 235.0 + (1181 - 1) * 0.05 = 235 + 59 = 294 E = -66
"""


def _canonical(**overrides):
    fields = dict(
        south=24.0, west=235.0, dlat=0.05, dlon=0.05, rows=521, columns=1181
    )
    fields.update(overrides)
    ngs_grid.require_canonical_geometry(
        SAMPLE_DIALECT, "<f>", SAMPLE_GEOMETRY, **fields
    )


def test_the_declared_geometry_of_the_example_tile_checks_out_by_hand():
    """north = 24 + 520 * 0.05 = 50; east = 235 + 1180 * 0.05 = 294."""
    assert SAMPLE_GEOMETRY.south_latitude + (
        SAMPLE_GEOMETRY.row_count - 1
    ) * SAMPLE_GEOMETRY.latitude_spacing == pytest.approx(50.0)
    assert SAMPLE_GEOMETRY.west_longitude + (
        SAMPLE_GEOMETRY.column_count - 1
    ) * SAMPLE_GEOMETRY.longitude_spacing == pytest.approx(294.0)


def test_a_matching_header_passes_the_canonical_check():
    _canonical()


def test_every_mismatched_field_is_named_with_both_numbers():
    """A refusal that only said "wrong geometry" would not be actionable."""
    with pytest.raises(SampleError) as caught:
        _canonical(south=25.0, rows=1181, columns=521)

    message = str(caught.value)
    assert "does not have the geometry of a test tile" in message
    assert "SLAT (southernmost latitude): expected 24.0, found 25.0" in message
    assert "NLAT (row count): expected 521, found 1181" in message
    assert "NLON (column count): expected 1181, found 521" in message
    # And the dialect's own closing sentence, not a geoid one.
    assert message.endswith(SAMPLE_DIALECT.geometry_consequence)
    assert "geoid" not in message


def test_each_field_is_checked_independently():
    for override in (
        {"south": 24.5},
        {"west": 235.5},
        {"dlat": 0.1},
        {"dlon": 0.1},
        {"rows": 520},
        {"columns": 1180},
    ):
        with pytest.raises(SampleError):
            _canonical(**override)


def test_the_geometry_tolerance_admits_a_decimal_literal_and_nothing_coarser():
    """1e-9 degrees is about 0.11 mm on the ground - a disclosed convention.

    NGS writes one arcminute into its own headers as the decimal literals
    0.016666666667 and 0.01666666666699, which differ from the double nearest
    1/60 by about 3.3e-13 degrees, so an exact comparison would reject the
    genuine file. Hand check of both ends of the slack:

        |0.016666666667 - 1/60| = 3.3e-13  <  1e-9   -> admitted
        |1/60 + 1e-7    - 1/60| = 1.0e-7   >  1e-9   -> refused
    """
    assert ngs_grid.GEOMETRY_TOLERANCE_DEG == 1e-9
    assert abs(0.016666666667 - 1.0 / 60.0) < 1e-12
    assert abs(0.01666666666699 - 1.0 / 60.0) < 1e-12

    arcminute = ngs_grid.TileGeometry(
        south_latitude=40.0,
        west_longitude=264.0,
        latitude_spacing=1.0 / 60.0,
        longitude_spacing=1.0 / 60.0,
        row_count=1081,
        column_count=1141,
        name="an arcminute tile",
    )

    def check(dlat):
        ngs_grid.require_canonical_geometry(
            SAMPLE_DIALECT, "<f>", arcminute,
            40.0, 264.0, dlat, 0.01666666666699, 1081, 1141,
        )

    check(0.016666666667)

    with pytest.raises(SampleError, match="DLAT"):
        check(1.0 / 60.0 + 1e-7)


def test_a_non_finite_header_value_cannot_slip_through_the_tolerance():
    """``abs(nan - want) > tolerance`` is False, so nan needs its own branch."""
    assert not (abs(float("nan") - 24.0) > ngs_grid.GEOMETRY_TOLERANCE_DEG)

    with pytest.raises(SampleError, match="SLAT"):
        _canonical(south=float("nan"))


# --------------------------------------------------------------------------
# The payload.
# --------------------------------------------------------------------------


def test_a_finite_payload_passes():
    ngs_grid.require_finite_payload(SAMPLE_DIALECT, "<f>", LATTICE)


def test_a_non_finite_cell_is_refused_and_located():
    """The index in the message is the flat, row-major one.

    With a 3x3 lattice, the cell at row 1, column 2 is index 1 * 3 + 2 = 5.
    """
    values = list(LATTICE)
    values[5] = float("nan")

    with pytest.raises(SampleError) as caught:
        ngs_grid.require_finite_payload(SAMPLE_DIALECT, "<f>", tuple(values))

    assert str(caught.value) == (
        "<f> contains a non-finite test value (nan) at cell index 5. "
        "A non-finite cell would travel silently downstream."
    )


def test_infinities_are_refused_as_well_as_nan():
    """math.isfinite is the test, not a NaN-only comparison."""
    for bad in (float("inf"), float("-inf")):
        values = (1.0, bad, 3.0)
        with pytest.raises(SampleError, match="cell index 1"):
            ngs_grid.require_finite_payload(SAMPLE_DIALECT, "<f>", values)
        assert not math.isfinite(bad)


# --------------------------------------------------------------------------
# The substrate states no policy of its own.
# --------------------------------------------------------------------------


def test_the_substrate_defines_no_exception_class():
    """Deliberate: an exception here would be a second thing to catch.

    Every refusal is raised as the class its dialect carries, so a caller keeps
    exactly one exception type for its whole surface.
    """
    exceptions = [
        name
        for name, value in vars(ngs_grid).items()
        if isinstance(value, type) and issubclass(value, BaseException)
    ]
    assert exceptions == []


def test_the_substrate_names_no_model_file_or_checksum():
    """Filenames, checksums and geometries belong to the policy layers.

    A substrate that knew about ``g2018u3.bin`` would be a second place the
    shipped tile is described, which section 7 of DESIGN.md forbids.
    """
    source = (
        __import__("pathlib").Path(ngs_grid.__file__).read_text(encoding="utf-8")
    )
    assert "g2018u3" not in source
    assert geoid.GEOID18_TILE_SHA256 not in source

    names = set(vars(ngs_grid))
    assert "GEOID18_TILE" not in names
    assert "GEOID18_U3_GEOMETRY" not in names


def test_no_refusal_message_names_a_model():
    """The line the module docstring actually draws.

    Review gate, 2026-08-07, finding 2 (LOW): the docstring claimed the module
    carried "no wording that names a model", which its own prose contradicted -
    it names GEOID18 and VERTCON in comments, and must, because a tolerance
    chosen by measuring one file has to say which file (DESIGN.md section 7).
    The claim that is worth holding is narrower and is this one: **no message a
    user reads may name a model**, because such a message would be wrong for
    the other caller. Every model-specific word arrives from the dialect.

    Driven with a dialect naming a model that does not exist, so any leaked
    literal from the real ones shows up as its own name in the output.
    """
    import re

    source = Path(ngs_grid.__file__).read_text(encoding="utf-8")

    # Every string literal that is raised, i.e. the f-strings inside the
    # ``raise dialect.error(...)`` calls. Comments and docstrings are not
    # messages, so they are read out of the AST rather than the text.
    import ast

    raised: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Raise):
            for piece in ast.walk(node):
                if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                    raised.append(piece.value)

    assert raised, "no raised message literals found - the scanner is vacuous"

    for text in raised:
        for model in ("GEOID18", "GEOID12B", "VERTCON", "geoid", "g2018", "g2012"):
            assert model not in text, (
                f"a refusal in ngs_grid names {model!r}: {text!r}. That message "
                f"is wrong for every other caller of this substrate; the word "
                f"belongs in the caller's GridDialect."
            )

    # Anti-vacuousness: the scanner must actually see a model name when one is
    # present. ``geoid``'s own dialect carries several.
    assert "geoid height" in geoid.GEOID_DIALECT.value_noun
    assert re.search(r"GEOID18", geoid.GEOID_DIALECT.model_name)


def test_the_dialect_is_not_a_field_of_the_grid_record():
    """It is a property of the kind of grid, not of one loaded file.

    Kept a ClassVar so the constructor stays the eight data fields a reader
    actually parses out of a header and payload, and so two grids of the same
    kind cannot disagree about their own wording.
    """
    field_names = [f.name for f in dataclasses.fields(ngs_grid.Grid)]
    assert field_names == [
        "path",
        "south_latitude",
        "west_longitude",
        "latitude_spacing",
        "longitude_spacing",
        "row_count",
        "column_count",
        "values",
    ]
    assert "dialect" not in field_names
    assert [f.name for f in dataclasses.fields(geoid.GeoidGrid)] == field_names


def test_a_loaded_grid_is_frozen():
    """Core records are immutable (DESIGN.md section 4)."""
    grid = sample_grid()
    with pytest.raises(dataclasses.FrozenInstanceError):
        grid.south_latitude = 0.0  # type: ignore[misc]
