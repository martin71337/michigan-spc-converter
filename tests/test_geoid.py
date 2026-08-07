"""The GEOID18 grid reader, its interpolation, and the factor chain."""

from __future__ import annotations

import hashlib
import struct

import pytest

from michspc.fileio import geoid18
from michspc.spc.factors import (
    MEAN_EARTH_RADIUS_IFT,
    MEAN_EARTH_RADIUS_M,
    Factors,
    combined_factor,
    elevation_factor,
    factors_at,
)
from michspc.spc.units import INTERNATIONAL_FEET
from tests.fixtures.geoid_anchors import GEOID_ANCHORS

ANCHOR_IDS = [f"{a.latitude}/{a.longitude}" for a in GEOID_ANCHORS]

# NGS prints geoid heights to 0.001 m, so half a unit in the last place is
# 0.0005 m. Biquadratic interpolation reaches that floor (measured worst case
# 0.6 mm across the anchors); 1 mm leaves a little headroom above the
# quantization without admitting a genuinely worse scheme.
GEOID_TOLERANCE_M = 0.001


@pytest.fixture(scope="module")
def grid():
    return geoid18.load_grid()


# --------------------------------------------------------------------------
# The file itself.
# --------------------------------------------------------------------------


def test_the_shipped_grid_matches_the_pinned_checksum():
    """The grid is committed unmodified from NGS; prove it still is.

    A corrupted or substituted grid would produce plausible-looking geoid
    heights that nothing downstream could catch, so the file is pinned by hash
    rather than trusted.
    """
    digest = hashlib.sha256(geoid18.GEOID18_TILE.read_bytes()).hexdigest()
    assert digest == geoid18.GEOID18_TILE_SHA256


def test_the_header_matches_the_documented_format(grid):
    """GEOID18 CONUS grid #3: 40-58 N, 96-77 W, one arcminute, 1081 x 1141.

    Hand check of the extents from the header:
        north = 40 + (1081 - 1) * (1/60) = 40 + 18 = 58 N
        east  = 264 + (1141 - 1) * (1/60) = 264 + 19 = 283 E = 77 W
    """
    assert grid.south_latitude == pytest.approx(40.0)
    assert grid.west_longitude == pytest.approx(264.0)  # 96 W in the file's 0-360
    assert grid.latitude_spacing == pytest.approx(1.0 / 60.0, rel=1e-6)
    assert grid.longitude_spacing == pytest.approx(1.0 / 60.0, rel=1e-6)
    assert grid.row_count == 1081
    assert grid.column_count == 1141
    assert grid.north_latitude == pytest.approx(58.0, abs=1e-6)
    assert grid.east_longitude == pytest.approx(283.0, abs=1e-6)
    assert len(grid.values) == 1081 * 1141


def test_the_grid_covers_all_of_michigan(grid):
    """Every corner of every zone's extent must be inside the tile."""
    from michspc.spc.zones import ALL_ZONES

    for zone in ALL_ZONES:
        for latitude in (zone.lat_min, zone.lat_max):
            for longitude in (zone.lon_min, zone.lon_max):
                assert grid.contains(latitude, longitude), (
                    f"{zone.abbrev} corner {latitude}, {longitude} is outside "
                    f"the shipped geoid tile"
                )


# --------------------------------------------------------------------------
# Anchors: our interpolation against NGS's own geoid service.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", GEOID_ANCHORS, ids=ANCHOR_IDS)
def test_geoid_height_matches_ngs(anchor, grid):
    """Expected values computed by NGS, at deliberately off-node positions."""
    height = geoid18.geoid_height(anchor.latitude, anchor.longitude, grid)
    assert height == pytest.approx(anchor.geoid_height_m, abs=GEOID_TOLERANCE_M)


@pytest.mark.anchor
def test_biquadratic_beats_bilinear_against_ngs(grid):
    """The evidence that settled the interpolation choice (design log #8).

    NGS documents the scheme after all - NOAA TM NOS NGS-84 and INTG's own
    Fortran source both give biquadratic on a nearest-node 3x3, which the WP-V4
    gate established and DESIGN.md #8 now records. That confirms the choice this
    test pins. It also shows the ANCHORING here is not INTG's, which is a
    separate open item recorded in #8 and in
    ``ngs_grid.interpolate_biquadratic``; it is not what this test is about.

    Both candidates were implemented and measured against NGS's own service
    across the 20 Michigan anchors:

        bilinear      worst error 1.3 mm
        biquadratic   worst error 0.6 mm

    NGS publishes to 1 mm, so biquadratic sits at the quantization floor while
    bilinear is measurably worse. This test keeps that comparison live, so a
    future change that quietly switched schemes would show.
    """
    worst_bilinear = 0.0
    worst_biquadratic = 0.0
    for anchor in GEOID_ANCHORS:
        bilinear = grid.height_bilinear(anchor.latitude, anchor.longitude)
        biquadratic = grid.height_biquadratic(anchor.latitude, anchor.longitude)
        worst_bilinear = max(worst_bilinear, abs(bilinear - anchor.geoid_height_m))
        worst_biquadratic = max(
            worst_biquadratic, abs(biquadratic - anchor.geoid_height_m)
        )

    assert worst_biquadratic < worst_bilinear
    assert worst_biquadratic <= GEOID_TOLERANCE_M

    # And geoid_height() must actually be using the better one.
    for anchor in GEOID_ANCHORS[:3]:
        assert geoid18.geoid_height(
            anchor.latitude, anchor.longitude, grid
        ) == grid.height_biquadratic(anchor.latitude, anchor.longitude)


@pytest.mark.anchor
def test_every_michigan_geoid_height_is_negative(grid):
    """The sign convention, checked rather than trusted.

    The manual (PDF p. 57) puts the ellipsoid above the geoid throughout the
    conterminous United States. A positive geoid height for a Michigan point
    means the sign was flipped somewhere, which is a ~10 ppm error in every
    reduced distance and one of the defects recorded against the prior MATLAB
    tool.
    """
    for anchor in GEOID_ANCHORS:
        assert anchor.geoid_height_m < 0.0
        assert geoid18.geoid_height(anchor.latitude, anchor.longitude, grid) < 0.0

    # Across Michigan the value runs roughly -30 to -37 m.
    heights = [
        geoid18.geoid_height(a.latitude, a.longitude, grid) for a in GEOID_ANCHORS
    ]
    assert -40.0 < min(heights) < max(heights) < -25.0


def test_interpolation_reproduces_a_grid_node_exactly(grid):
    """At a node, both schemes must return that node's stored value.

    A quiet off-by-one in the row or column arithmetic would show here and
    almost nowhere else, since an interpolated value between neighbouring nodes
    still looks entirely reasonable.
    """
    # A node well inside the grid: row 200, column 300.
    row, column = 200, 300
    latitude = grid.south_latitude + row * grid.latitude_spacing
    longitude_east = grid.west_longitude + column * grid.longitude_spacing
    longitude = longitude_east - 360.0

    stored = grid.values[row * grid.column_count + column]

    assert grid.height_bilinear(latitude, longitude) == pytest.approx(stored, abs=1e-6)
    assert grid.height_biquadratic(latitude, longitude) == pytest.approx(
        stored, abs=1e-6
    )


def test_lagrange_quadratic_is_exact_on_a_quadratic():
    """_lagrange3 must reproduce any quadratic through its three nodes.

    Hand derivation with f(x) = 2x^2 - 3x + 5 at nodes 0, 1, 2:
        f(0) = 5, f(1) = 4, f(2) = 7
        f(0.5) = 2(0.25) - 1.5 + 5 = 4.0
        f(1.5) = 2(2.25) - 4.5 + 5 = 5.0
    """
    values = [5.0, 4.0, 7.0]
    assert geoid18._lagrange3(values, 0.0) == pytest.approx(5.0)
    assert geoid18._lagrange3(values, 1.0) == pytest.approx(4.0)
    assert geoid18._lagrange3(values, 2.0) == pytest.approx(7.0)
    assert geoid18._lagrange3(values, 0.5) == pytest.approx(4.0)
    assert geoid18._lagrange3(values, 1.5) == pytest.approx(5.0)


def test_longitude_convention_round_trips():
    """The file stores 0-360 east; the program uses signed, negative west."""
    assert geoid18._to_east_longitude(-84.5) == pytest.approx(275.5)
    assert geoid18._to_east_longitude(12.0) == pytest.approx(12.0)
    assert geoid18._to_signed_longitude(275.5) == pytest.approx(-84.5)
    assert geoid18._to_signed_longitude(12.0) == pytest.approx(12.0)


# --------------------------------------------------------------------------
# Refusals.
# --------------------------------------------------------------------------


def test_a_point_outside_the_tile_is_refused_by_name(grid):
    """Fails closed, and says what it means for the output."""
    with pytest.raises(geoid18.GeoidError) as caught:
        geoid18.geoid_height(35.0, -84.0, grid)  # Tennessee, south of the tile

    message = str(caught.value)
    assert "outside the GEOID18 tile" in message
    assert "no elevation or combined factor" in message


def test_a_truncated_grid_is_refused(tmp_path):
    original = geoid18.GEOID18_TILE.read_bytes()
    truncated = tmp_path / "short.bin"
    truncated.write_bytes(original[: 44 + 1000])

    with pytest.raises(geoid18.GeoidError, match="truncated or corrupt"):
        geoid18.load_grid(truncated)


def test_a_file_too_short_for_a_header_is_refused(tmp_path):
    stub = tmp_path / "stub.bin"
    stub.write_bytes(b"\x00" * 12)

    with pytest.raises(geoid18.GeoidError, match="too short"):
        geoid18.load_grid(stub)


def test_a_big_endian_grid_is_refused(tmp_path):
    """NGS also publishes a Unix (big-endian) form; reading it here would give
    garbage that still looked like numbers, so IKIND is checked."""
    header = struct.pack("<4d3i", 40.0, 264.0, 1 / 60, 1 / 60, 2, 2, 2)
    wrong = tmp_path / "be.bin"
    wrong.write_bytes(header + b"\x00" * 16)

    with pytest.raises(geoid18.GeoidError, match="IKIND"):
        geoid18.load_grid(wrong)


def test_a_missing_grid_is_refused_with_a_useful_message(tmp_path):
    with pytest.raises(geoid18.GeoidError, match="installation is incomplete"):
        geoid18.load_grid(tmp_path / "not-here.bin")


def test_checksum_verification_catches_a_tampered_grid(tmp_path):
    """``verify_checksum`` is opt-in on ``load_grid``; prove it works.

    The production path (``load_shipped_grid`` / ``default_grid``) turns it on
    unconditionally - see the finding-6 tests below.
    """
    original = bytearray(geoid18.GEOID18_TILE.read_bytes())
    original[100] ^= 0xFF  # flip a byte in the payload
    tampered = tmp_path / "tampered.bin"
    tampered.write_bytes(bytes(original))

    # It still loads and still produces numbers - which is exactly why the
    # checksum matters.
    geoid18.load_grid(tampered)

    with pytest.raises(geoid18.GeoidError, match="does not match"):
        geoid18.load_grid(tampered, verify_checksum=True)


# --------------------------------------------------------------------------
# Interim review gate finding 6 (docs/DESIGN.md amendment #11): the production
# path must authenticate the grid, and a header that preserves the payload
# length while re-shaping the grid must be refused.
# --------------------------------------------------------------------------


def _tile_with_header(
    tmp_path,
    name: str,
    south: float = 40.0,
    west: float = 264.0,
    dlat: float = 1 / 60,
    dlon: float = 1 / 60,
    rows: int = 1081,
    columns: int = 1141,
    ikind: int = 1,
):
    """The shipped tile's payload behind a header of our choosing.

    Built in tmp_path. ``data/g2018u3.bin`` is never modified; it is the NGS
    original and its hash is pinned.
    """
    payload = geoid18.GEOID18_TILE.read_bytes()[44:]
    path = tmp_path / name
    path.write_bytes(
        struct.pack("<4d3i", south, west, dlat, dlon, rows, columns, ikind) + payload
    )
    return path


def test_a_row_column_swap_survives_every_structural_check(tmp_path):
    """Anti-vacuousness for the geometry check below: the defect is real.

    The reviewer's counterexample. 1081 x 1141 and 1141 x 1081 have the same
    product, so the payload-length check - the only thing that ever looked at
    the counts - cannot tell them apart:

        1081 * 1141 = 1,233,421 cells = 4,933,684 bytes
        1141 * 1081 = 1,233,421 cells = 4,933,684 bytes

    Without the geometry check the file loads, and every lookup then comes from
    the wrong cell. At 43.0 N, 84.5 W the interim review gate measured
    -27.927000063 m against the true -33.084999085 m: a 5.158 m error that looks
    like an entirely ordinary Michigan geoid height. (Both figures are the
    reviewer's measurements, quoted as the record of the defect.)
    """
    swapped = _tile_with_header(tmp_path, "swapped.bin", rows=1141, columns=1081)

    # No expectation passed: this is the reader as any other tile would use it.
    grid_swapped = geoid18.load_grid(swapped)
    wrong = grid_swapped.height_biquadratic(43.0, -84.5)

    # 5 mm of slack on a 5.158 m discrepancy - loose enough not to pin the
    # reviewer's last digit, tight enough that only the transposed reading
    # produces it.
    assert wrong == pytest.approx(-27.927, abs=0.005)

    truth = geoid18.load_grid().height_biquadratic(43.0, -84.5)
    assert truth == pytest.approx(-33.085, abs=0.005)
    assert abs(truth - wrong) == pytest.approx(5.158, abs=0.01)


def test_a_row_column_swap_is_refused_when_the_tile_is_the_shipped_one(tmp_path):
    """Finding 6(b), pinned with the reviewer's own counterexample.

    Same file as the test above. Declaring which tile it is meant to be is what
    catches it, because the geometry is the only thing the transposition
    changes that anything can check.
    """
    swapped = _tile_with_header(tmp_path, "swapped.bin", rows=1141, columns=1081)

    with pytest.raises(geoid18.GeoidError) as caught:
        geoid18.load_grid(swapped, expect_geometry=geoid18.GEOID18_U3_GEOMETRY)

    message = str(caught.value)
    # Names what is wrong, with both numbers, and what it means for the output.
    assert "NLAT (row count): expected 1081, found 1141" in message
    assert "NLON (column count): expected 1141, found 1081" in message
    assert "wrong cell" in message

    # And the production entry point refuses it too, by the same rule.
    with pytest.raises(geoid18.GeoidError):
        geoid18.load_shipped_grid(swapped)


def test_the_production_path_authenticates_the_grid(tmp_path):
    """Finding 6(a): ``default_grid`` is what production calls, so it checks.

    Previously ``load_grid``'s ``verify_checksum`` defaulted to False and
    ``default_grid`` took that default, so the pin was enforced only by the test
    suite and the frozen bundle's self-test - never by the running program.

    Exercised through ``load_shipped_grid``, which is the policy ``default_grid``
    applies; ``default_grid`` itself is lru_cached on the shipped path and
    cannot be pointed at a test file.
    """
    original = bytearray(geoid18.GEOID18_TILE.read_bytes())
    original[100] ^= 0xFF  # flip a byte in the payload, leaving the header valid
    tampered = tmp_path / "tampered.bin"
    tampered.write_bytes(bytes(original))

    # Same file the unchecked reader accepted in
    # test_checksum_verification_catches_a_tampered_grid.
    geoid18.load_grid(tampered)

    with pytest.raises(geoid18.GeoidError, match="does not match"):
        geoid18.load_shipped_grid(tampered)

    # The real file passes both gates, so the check is not simply refusing
    # everything.
    assert geoid18.load_shipped_grid().row_count == 1081
    assert geoid18.default_grid().column_count == 1141


def test_the_canonical_geometry_is_the_one_the_readme_documents(grid):
    """The expectation must match the file, or it is just a second guess.

    GEOID18 CONUS grid #3: 40-58 N, 96-77 W, one arcminute, 1081 x 1141.
    Hand check of the extents from the counts alone:
        north = 40.0 + (1081 - 1) / 60 = 40 + 18 = 58 N
        east  = 264.0 + (1141 - 1) / 60 = 264 + 19 = 283 E = 283 - 360 = 77 W
    """
    expected = geoid18.GEOID18_U3_GEOMETRY

    assert expected.row_count == 1081
    assert expected.column_count == 1141
    assert expected.south_latitude + (expected.row_count - 1) * expected.latitude_spacing == pytest.approx(58.0)
    assert expected.west_longitude + (expected.column_count - 1) * expected.longitude_spacing == pytest.approx(283.0)

    # And it describes the file that actually ships.
    assert grid.row_count == expected.row_count
    assert grid.column_count == expected.column_count


def test_the_geometry_tolerance_admits_the_real_file_and_little_else(tmp_path):
    """The spacing cannot be compared exactly, so the slack must be justified.

    The shipped header stores one arcminute as the decimal literals
    0.016666666667 and 0.01666666666699, which differ from the double nearest
    1/60 by about 3.3e-13 degrees - so an exact test would reject the genuine
    NGS file. The tolerance is 1e-9 degrees, roughly 0.11 mm on the ground.

    Both halves are checked: the real spacings pass, and a spacing wrong by
    1e-7 degrees - still only about 1 cm, far smaller than any plausible header
    confusion - is refused.
    """
    # The real file, with the canonical expectation applied: accepted.
    geoid18.load_shipped_grid()

    nudged = _tile_with_header(tmp_path, "nudged.bin", dlat=1 / 60 + 1e-7)
    with pytest.raises(geoid18.GeoidError, match="DLAT"):
        geoid18.load_grid(nudged, expect_geometry=geoid18.GEOID18_U3_GEOMETRY)

    # A shifted origin is caught the same way.
    shifted = _tile_with_header(tmp_path, "shifted.bin", south=41.0)
    with pytest.raises(geoid18.GeoidError, match="SLAT"):
        geoid18.load_grid(shifted, expect_geometry=geoid18.GEOID18_U3_GEOMETRY)


def test_a_non_positive_or_non_finite_spacing_is_refused(tmp_path):
    """The interpolators divide by the spacing; zero or negative is nonsense.

    Checked in ``load_grid`` with no expectation passed, because this holds for
    any geoid grid, not just the shipped one.
    """
    for value, label in ((0.0, "DLAT"), (-1 / 60, "DLAT")):
        path = _tile_with_header(tmp_path, f"dlat{value}.bin", dlat=value)
        with pytest.raises(geoid18.GeoidError, match=label):
            geoid18.load_grid(path)

    path = _tile_with_header(tmp_path, "dlon_nan.bin", dlon=float("nan"))
    with pytest.raises(geoid18.GeoidError, match="DLON"):
        geoid18.load_grid(path)


def test_a_grid_too_small_to_interpolate_in_is_refused(tmp_path):
    """``height_biquadratic`` anchors a 3x3 block.

    With fewer than three rows its clamp ``min(max(int(row) - 1, 0),
    row_count - 3)`` goes negative, and Python's negative indexing would then
    read from the far end of the array instead of failing. A 2 x 2 grid is
    refused rather than silently interpolated backwards.
    """
    header = struct.pack("<4d3i", 40.0, 264.0, 1 / 60, 1 / 60, 2, 2, 1)
    path = tmp_path / "tiny.bin"
    path.write_bytes(header + struct.pack("<4f", -33.0, -33.1, -33.2, -33.3))

    with pytest.raises(geoid18.GeoidError, match="NLAT=2"):
        geoid18.load_grid(path)


def test_a_non_finite_payload_value_is_refused(tmp_path):
    """A NaN cell would become a NaN geoid height, then a NaN combined factor.

    Nothing downstream refuses a NaN - it is not an exception and not a number,
    and it would be printed in the audit file beside real values. Redundant with
    the checksum on the shipped tile, and not redundant for any other file
    ``load_grid`` is pointed at.
    """
    payload = bytearray(geoid18.GEOID18_TILE.read_bytes()[44:])
    payload[0:4] = struct.pack("<f", float("nan"))
    path = tmp_path / "nan.bin"
    path.write_bytes(
        struct.pack("<4d3i", 40.0, 264.0, 1 / 60, 1 / 60, 1081, 1141, 1) + bytes(payload)
    )

    with pytest.raises(geoid18.GeoidError, match="non-finite geoid height"):
        geoid18.load_grid(path)


# --------------------------------------------------------------------------
# The factor chain.
# --------------------------------------------------------------------------


def test_elevation_factor_hand_derivation():
    """Manual section 4.1: elevation factor = R / (R + H + N).

    Hand derivation for a point 300 m above the geoid in Michigan, geoid
    height -34 m:
        h = 300 + (-34) = 266 m
        EF = 6372000 / (6372000 + 266)
           = 6372000 / 6372266
           = 0.99995825...
    """
    factor = elevation_factor(300.0, -34.0)
    assert factor == pytest.approx(6_372_000.0 / 6_372_266.0, rel=1e-15)
    assert factor == pytest.approx(0.9999582, abs=1e-7)


def test_elevation_factor_is_below_one_above_the_ellipsoid():
    """Reducing a ground distance to the ellipsoid shortens it."""
    assert elevation_factor(300.0, -34.0) < 1.0
    # And a point below the ellipsoid lengthens it.
    assert elevation_factor(10.0, -34.0) > 1.0


def test_ignoring_the_geoid_height_costs_the_documented_5ppm():
    """Why the geoid grid is bundled rather than left to the user.

    The manual (PDF p. 57) states the failure to use geoid height introduces
    0.16 ppm per meter of geoid height, and that -30 m systematically affects
    all reduced distances by -4.8 ppm, about 1:208,000.

    Hand check at Michigan's typical -34 m:
        0.16 ppm/m * 34 m = 5.4 ppm
    """
    with_geoid = elevation_factor(300.0, -34.0)
    without_geoid = elevation_factor(300.0, 0.0)
    parts_per_million = (with_geoid - without_geoid) / without_geoid * 1e6

    assert parts_per_million == pytest.approx(5.4, abs=0.2)


def test_getting_the_geoid_sign_backwards_doubles_that_error():
    """The specific defect recorded against the prior MATLAB tool.

    Entering +34 instead of -34 is not a 5 ppm error but a 10.7 ppm one,
    because the height moves by twice the geoid separation.
    """
    correct = elevation_factor(300.0, -34.0)
    flipped = elevation_factor(300.0, +34.0)
    parts_per_million = (correct - flipped) / flipped * 1e6

    assert parts_per_million == pytest.approx(10.7, abs=0.3)


def test_the_two_printed_radii_are_interchangeable():
    """The manual prints R as "20,906,000 ft, or 6,372,000 m" (PDF p. 59).

    Those are not exactly equal - 20,906,000 international feet is 6,372,148.8 m
    - so the choice is bounded here rather than assumed. At a 300 m elevation
    the two differ in the elevation factor by about 1e-9, which cannot move a
    coordinate written to 0.001 ft.
    """
    metric = elevation_factor(300.0, -34.0, MEAN_EARTH_RADIUS_M)
    from_feet = elevation_factor(
        300.0, -34.0, INTERNATIONAL_FEET.to_meters(MEAN_EARTH_RADIUS_IFT)
    )
    assert abs(metric - from_feet) < 1e-8


def test_combined_factor_is_the_product():
    """Manual section 4.1 (PDF p. 59). The exact product, not the sum-minus-one
    approximation the manual offers for hand calculation."""
    assert combined_factor(0.9999089, 0.9999582) == pytest.approx(
        0.9999089 * 0.9999582, rel=1e-15
    )


def test_factors_at_assembles_a_complete_record():
    factors = factors_at(0.9999089, 300.0, -34.0)

    assert factors.has_elevation
    assert factors.ellipsoid_height == pytest.approx(266.0)
    assert factors.elevation_factor == pytest.approx(elevation_factor(300.0, -34.0))
    assert factors.combined_factor == pytest.approx(
        0.9999089 * factors.elevation_factor
    )


def test_a_missing_elevation_yields_none_not_a_fabricated_one():
    """The behaviour the owner specified: nothing plausible is invented.

    Returning 1.0 would claim the point sits on the ellipsoid. Returning the
    grid factor as the combined factor would claim the elevation contributes
    nothing. Both would travel onto a drawing looking like real numbers.
    """
    factors = factors_at(0.9999089, None, -34.0)

    assert not factors.has_elevation
    assert factors.elevation_factor is None
    assert factors.combined_factor is None
    assert factors.ellipsoid_height is None
    # The grid scale factor does not depend on elevation, so it is still given.
    assert factors.grid_scale_factor == 0.9999089


def test_a_missing_geoid_height_also_yields_none():
    factors = factors_at(0.9999089, 300.0, None)
    assert factors.elevation_factor is None
    assert factors.combined_factor is None


def test_factors_are_frozen():
    factors = factors_at(0.9999089, 300.0, -34.0)
    with pytest.raises(Exception):
        factors.combined_factor = 1.0  # type: ignore[misc]


def test_an_absurd_elevation_is_refused():
    with pytest.raises(ValueError, match="centre of the earth"):
        elevation_factor(-7_000_000.0, -34.0)


# --------------------------------------------------------------------------
# End to end: a real Michigan point through the whole chain.
# --------------------------------------------------------------------------


def test_a_real_point_through_the_whole_factor_chain(grid):
    """Lansing at 800 ft, converted and reduced, checked by hand.

    Lansing sits at roughly 42.7325 N, 84.5555 W, about 800 international feet
    above the geoid. Working in meters:

        H = 800 ift * 0.3048 = 243.84 m
        N = -33.637 m        (NGS GEOID18, frozen anchor)
        h = 243.84 - 33.637  = 210.203 m
        EF = 6372000 / 6372210.203 = 0.99996701

    The grid scale factor comes from the Michigan South projection. The combined
    factor is their product, and must be slightly below both, since both are
    below one here.
    """
    from michspc.spc.convert import project_point
    from michspc.spc.frames import NAD83_2011
    from michspc.spc.zones import MI_SOUTH

    latitude, longitude = 42.7325, -84.5555
    point = project_point(latitude, longitude, NAD83_2011, MI_SOUTH)

    orthometric = INTERNATIONAL_FEET.to_meters(800.0)
    geoid = geoid18.geoid_height(latitude, longitude, grid)

    assert orthometric == pytest.approx(243.84, abs=1e-9)
    assert geoid == pytest.approx(-33.637, abs=GEOID_TOLERANCE_M)

    factors = factors_at(point.target_scale_factor, orthometric, geoid)

    assert factors.ellipsoid_height == pytest.approx(210.203, abs=0.002)
    assert factors.elevation_factor == pytest.approx(0.99996701, abs=1e-8)
    assert factors.combined_factor == pytest.approx(
        point.target_scale_factor * factors.elevation_factor, rel=1e-15
    )
    assert factors.combined_factor < factors.elevation_factor
    assert factors.combined_factor < point.target_scale_factor
