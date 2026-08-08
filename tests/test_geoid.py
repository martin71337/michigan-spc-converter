"""The geoid grid reader, the model registry, interpolation, the factor chain."""

from __future__ import annotations

import hashlib
import struct

import pytest

from michspc.fileio import geoid
from michspc.spc.factors import (
    MEAN_EARTH_RADIUS_IFT,
    MEAN_EARTH_RADIUS_M,
    Factors,
    combined_factor,
    elevation_factor,
    factors_at,
)
from michspc.spc.units import INTERNATIONAL_FEET
from michspc.spc.vertical import NAVD88, NGVD29
from tests.fixtures.geoid12b_anchors import GEOID12B_ANCHORS
from tests.fixtures.geoid_anchors import GEOID_ANCHORS

ANCHOR_IDS = [f"{a.latitude}/{a.longitude}" for a in GEOID_ANCHORS]
ANCHOR_12B_IDS = [f"{a.latitude}/{a.longitude}" for a in GEOID12B_ANCHORS]

# NGS prints geoid heights to 0.001 m, so half a unit in the last place is
# 0.0005 m. Biquadratic interpolation reaches that floor (measured worst case
# 0.83 mm across these 20 anchors under the nearest-node anchoring WP-G1
# shipped, 0.6 mm under the floor anchoring it replaced - both inside the
# noise, which is why the anchoring is gated by the discriminating anchors
# below and not by these); 1 mm leaves a little headroom above the
# quantization without admitting a genuinely worse scheme.
GEOID_TOLERANCE_M = 0.001


@pytest.fixture(scope="module")
def grid():
    return geoid.load_grid()


@pytest.fixture(scope="module")
def grid12b():
    """The GEOID12B tile, through the same authenticated path a job takes."""
    return geoid.load_shipped_grid(model=geoid.GEOID12B_MODEL)


# --------------------------------------------------------------------------
# The file itself.
# --------------------------------------------------------------------------


def test_the_shipped_grid_matches_the_pinned_checksum():
    """The grid is committed unmodified from NGS; prove it still is.

    A corrupted or substituted grid would produce plausible-looking geoid
    heights that nothing downstream could catch, so the file is pinned by hash
    rather than trusted.
    """
    digest = hashlib.sha256(geoid.GEOID18_TILE.read_bytes()).hexdigest()
    assert digest == geoid.GEOID18_TILE_SHA256


def test_the_shipped_geoid12b_tile_matches_its_pinned_checksum():
    """The second geoid tile is committed unmodified too.

    Until the WP-V4 review gate this file had no executable check on its
    contents at all: ``michspc.spec`` bundled it, ``tests/test_selftest.py``
    compared its NAME against the spec's list and ``tools/build_release.py``
    checked that it was present. Its digest lived only in
    docs/PLAN-vertical-datums.md section 2.1, so altering one payload float
    inside it passed every check in the repo (WP-V4 review, MEDIUM 1).

    Since WP-V5 the digest lives in the runtime record
    (``GEOID12B_MODEL.sha256``, which this alias derives from) and every load
    through the registry authenticates against it; this test keeps the direct
    tile-against-pin comparison so a corrupted commit is named the moment it
    lands, not at the first job that selects GEOID12B.
    """
    digest = hashlib.sha256(geoid.GEOID12B_TILE.read_bytes()).hexdigest()
    assert digest == geoid.GEOID12B_TILE_SHA256


def test_the_registry_records_are_distinct_authenticated_and_navd88():
    """The registry pins, in one place - the WP-V5 shape of the old two-pins test.

    Exactly two models today, and every fact a record states must be checked
    against the tree it describes: distinct names (a registry keyed by name
    cannot hold a collision), distinct filenames, distinct digests (the tiles
    are byte-for-byte the same SIZE on the same tile #3 geometry, so a
    copy-paste that pinned GEOID18's digest twice would leave GEOID12B
    unauthenticated with nothing else to notice), each tile present in data/
    and hashing to its own record's digest, and both vertical datums NAVD 88 -
    the fact ``require_geoid_matches_datum`` makes load-bearing.
    """
    models = geoid.ALL_GEOID_MODELS
    assert len(models) == 2
    assert [m.name for m in models] == ["GEOID18", "GEOID12B"]

    assert len({m.name for m in models}) == len(models)
    assert len({m.tile_filename for m in models}) == len(models)
    assert len({m.sha256 for m in models}) == len(models)

    for model in models:
        tile = geoid.DATA_DIR / model.tile_filename
        assert tile.is_file(), f"{model.name}'s tile {tile} is not committed"
        digest = hashlib.sha256(tile.read_bytes()).hexdigest()
        assert digest == model.sha256, f"{model.name}'s tile does not match its pin"
        assert model.vertical_datum is NAVD88
        assert model.citation.strip(), f"{model.name} has no citation"

    # The anti-vacuousness half the old test held: same size, different bytes.
    assert geoid.GEOID18_TILE != geoid.GEOID12B_TILE
    assert geoid.GEOID18_TILE.stat().st_size == geoid.GEOID12B_TILE.stat().st_size
    assert geoid.GEOID18_TILE.read_bytes() != geoid.GEOID12B_TILE.read_bytes()


def test_the_module_constants_are_derived_from_the_records():
    """One authoritative representation: the aliases must BE the record fields.

    ``is`` where identity is expressible, because a second literal that merely
    compares equal today is exactly the drift the rule forbids
    (docs/DESIGN.md section 7).
    """
    assert geoid.GEOID18_TILE_SHA256 is geoid.GEOID18_MODEL.sha256
    assert geoid.GEOID12B_TILE_SHA256 is geoid.GEOID12B_MODEL.sha256
    assert geoid.GEOID18_U3_GEOMETRY is geoid.GEOID18_MODEL.geometry
    assert geoid.GEOID_MODEL_NAME is geoid.GEOID18_MODEL.name
    assert geoid.GEOID18_TILE == geoid.DATA_DIR / geoid.GEOID18_MODEL.tile_filename
    assert geoid.GEOID12B_TILE == geoid.DATA_DIR / geoid.GEOID12B_MODEL.tile_filename


def test_geoid_model_by_name_returns_records_and_refuses_unknowns():
    """The registry lookup, in the style of ``vertical_datum_by_code``."""
    assert geoid.geoid_model_by_name("GEOID18") is geoid.GEOID18_MODEL
    assert geoid.geoid_model_by_name("GEOID12B") is geoid.GEOID12B_MODEL
    # Incidental whitespace is not a different model.
    assert geoid.geoid_model_by_name(" GEOID18 ") is geoid.GEOID18_MODEL

    with pytest.raises(KeyError) as raised:
        geoid.geoid_model_by_name("GEOID2022")

    message = str(raised.value)
    assert "GEOID2022" in message
    assert "GEOID18" in message
    assert "GEOID12B" in message


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
    height = geoid.geoid_height(anchor.latitude, anchor.longitude, grid)
    assert height == pytest.approx(anchor.geoid_height_m, abs=GEOID_TOLERANCE_M)


@pytest.mark.anchor
def test_biquadratic_beats_bilinear_against_ngs(grid):
    """The evidence that settled the interpolation choice (design log #8).

    NGS documents the scheme after all - NOAA TM NOS NGS-84 and INTG's own
    Fortran source both give biquadratic on a nearest-node 3x3, which the WP-V4
    gate established and DESIGN.md #8 now records. Since WP-G1 (DESIGN.md #37)
    the anchoring is INTG's too; the anchoring is gated by the discriminating
    anchors below, not by this test, which is about the scheme.

    Both candidates were implemented and measured against NGS's own service
    across the 20 Michigan anchors:

        bilinear      worst error 1.3 mm
        biquadratic   worst error 0.83 mm (nearest-node; 0.6 mm floor-anchored)

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
        assert geoid.geoid_height(
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
        assert geoid.geoid_height(anchor.latitude, anchor.longitude, grid) < 0.0

    # Across Michigan the value runs roughly -30 to -37 m.
    heights = [
        geoid.geoid_height(a.latitude, a.longitude, grid) for a in GEOID_ANCHORS
    ]
    assert -40.0 < min(heights) < max(heights) < -25.0


# --------------------------------------------------------------------------
# GEOID12B: the registry's second model against NGS's own service (WP-V5).
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", GEOID12B_ANCHORS, ids=ANCHOR_12B_IDS)
def test_geoid12b_height_matches_ngs(anchor, grid12b):
    """Expected values computed by NGS's own geoid service, model 13.

    Same positions, same interpolation and the same 1 mm tolerance rationale as
    the GEOID18 anchors above: NGS prints to 0.001 m, the committed tile
    reproduced every figure at worst 0.543 mm at capture (the fixture's own
    measurement, before any registry code existed), and 1 mm leaves headroom
    over the quantization without admitting a genuinely worse reading.
    """
    height = geoid.geoid_height(anchor.latitude, anchor.longitude, grid12b)
    assert height == pytest.approx(anchor.geoid_height_m, abs=GEOID_TOLERANCE_M)


@pytest.mark.anchor
def test_a_swapped_tile_fails_the_other_models_anchors(grid, grid12b):
    """The ANTI-SWAP pin. Nothing structural can tell these two tiles apart.

    Byte-for-byte the same size, the same tile #3 geometry - so a GEOID18 tile
    served under the GEOID12B name (a mispinned record, a copied file in
    data/) passes every format check and differs only in what it answers. The
    fixtures discriminate: 18 of the 20 positions differ between the models at
    NGS's printed millimetre (tests/fixtures/geoid12b_anchors.py), so each
    grid read against the OTHER model's anchors must miss the printed figure
    at 10 or more of the 20, while matching its own set inside the anchor
    tolerance (the parametrized tests above).

    **Falsified with the swap that passes BOTH authentication gates**: the
    GEOID12B record's filename AND digest pointed at GEOID18's, so the load
    authenticates cleanly and only the answers are wrong - this test's own
    second assertion fails (3 misses where 10 are required). Pointing only
    the filename is NOT the falsification: the digest check then errors in
    fixture setup and this assertion never runs, which demonstrates the
    checksum pin, not this one (WP-V5 review gate, LOW 4 - an
    under-specified falsification is the #31 failure mode).
    """

    def printed_mm_misses(loaded, anchors):
        return sum(
            1
            for anchor in anchors
            if round(loaded.height_biquadratic(anchor.latitude, anchor.longitude), 3)
            != round(anchor.geoid_height_m, 3)
        )

    assert printed_mm_misses(grid, GEOID12B_ANCHORS) >= 10
    assert printed_mm_misses(grid12b, GEOID_ANCHORS) >= 10


def test_geoid12b_refusals_name_geoid12b(grid12b):
    """A refusal about the GEOID12B tile must not call it GEOID18.

    The dialect is per model since WP-V5; "outside the GEOID18 tile" for a
    lookup that consulted g2012bu3.bin would be a false statement about which
    grid refused.
    """
    with pytest.raises(geoid.GeoidError) as caught:
        grid12b.height_biquadratic(35.0, -84.0)  # Tennessee, south of the tile

    message = str(caught.value)
    assert "outside the GEOID12B tile" in message
    assert "GEOID18" not in message


def test_default_grid_is_cached_per_model():
    """One authenticated load per model per process, keyed on the record.

    ``default_grid()`` and ``default_grid(GEOID18_MODEL)`` must be ONE cache
    entry - the default is normalized before the cache, so the same 4.7 MB is
    not unpacked twice under two keys - and the GEOID12B entry is its own.
    """
    first = geoid.default_grid(geoid.GEOID12B_MODEL)
    assert geoid.default_grid(geoid.GEOID12B_MODEL) is first
    assert first.path.name == geoid.GEOID12B_MODEL.tile_filename

    assert geoid.default_grid() is geoid.default_grid(geoid.GEOID18_MODEL)
    assert geoid.default_grid() is not first


# --------------------------------------------------------------------------
# The latent datum guard (plan section 3.4). Nothing in production calls it
# until WP-V6; it is tested directly so it is proven before it is wired.
# --------------------------------------------------------------------------


def test_both_shipped_models_pass_the_datum_guard_against_navd88():
    """The live case: every model this program carries is NAVD 88 today."""
    for model in geoid.ALL_GEOID_MODELS:
        geoid.require_geoid_matches_datum(model, NAVD88)


def test_the_datum_guard_refuses_ngvd29_and_teaches_why():
    """DESIGN.md #32's rule, enforced: no two eras inside one number.

    An NGVD 29 orthometric height with a NAVD 88 geoid separation produces an
    elevation factor that looks exact and cites nothing. The refusal must name
    the model, name the datum, and say what to do instead.
    """
    with pytest.raises(geoid.GeoidError) as raised:
        geoid.require_geoid_matches_datum(geoid.GEOID18_MODEL, NGVD29)

    message = str(raised.value)
    assert "GEOID18" in message
    assert "NGVD29" in message
    assert "NAVD88" in message
    assert "two eras inside one number" in message

    with pytest.raises(geoid.GeoidError):
        geoid.require_geoid_matches_datum(geoid.GEOID12B_MODEL, NGVD29)


def test_the_datum_guard_refuses_impostor_records_by_name():
    """The #11-finding-1 duck-typing class, closed at this door too.

    Every core record carries ``name`` and ``citation``, so a ``VerticalDatum``
    passed as the model - or a model passed as the datum, or a ``Zone`` as
    either - would duck-type into the comparison and fail as an
    ``AttributeError`` (or worse, compare codes that both exist and pass).
    Falsified at the WP-V5 gate by deleting the isinstance guards: the swapped
    call below then raises AttributeError instead of TypeError.
    """
    from michspc.spc.zones import MI_SOUTH

    # A VerticalDatum where the model belongs.
    with pytest.raises(TypeError, match="GeoidModel"):
        geoid.require_geoid_matches_datum(NAVD88, NAVD88)

    # The two arguments transposed - the likeliest real mistake.
    with pytest.raises(TypeError):
        geoid.require_geoid_matches_datum(NAVD88, geoid.GEOID18_MODEL)

    # A model where the datum belongs.
    with pytest.raises(TypeError, match="VerticalDatum"):
        geoid.require_geoid_matches_datum(geoid.GEOID18_MODEL, geoid.GEOID12B_MODEL)

    # A Zone as either - the record class finding 1 was originally about.
    with pytest.raises(TypeError, match="GeoidModel"):
        geoid.require_geoid_matches_datum(MI_SOUTH, NAVD88)
    with pytest.raises(TypeError, match="VerticalDatum"):
        geoid.require_geoid_matches_datum(geoid.GEOID18_MODEL, MI_SOUTH)


# --------------------------------------------------------------------------
# The WP-G1 anchoring gate (DESIGN.md #37). The 20 anchors above cannot tell
# the two stencil anchorings apart - every candidate sits inside NGS's 0.001 m
# printing quantization on them, so the suite passed with geoid_height anchored
# either way (a #31-class pin, found by seeding exactly that defect at the
# WP-V4 gate). These anchors were frozen where the anchorings diverge, and
# they are what fails if the geoid is ever quietly moved off INTG's stencil.
# --------------------------------------------------------------------------


@pytest.mark.anchor
def test_geoid_height_rounds_to_ngs_at_every_discriminating_anchor(grid):
    """The exact pin #36 asked WP-G1 to freeze.

    At each of these 36 positions the nearest-node (INTG) stencil rounds to
    NGS's own printed figure and the floor-anchored stencil does not, so this
    test cannot pass under the anchoring 0.1.0 through 0.3.1 shipped.
    Falsified at the WP-G1 gate: with ``geoid_height`` seeded back to
    ``interpolate_biquadratic``, all 36 fail.
    """
    from tests.fixtures.geoid_discriminating_anchors import DISCRIMINATING_ANCHORS

    pins = [a for a in DISCRIMINATING_ANCHORS if a.discriminates]
    assert len(pins) == 36, "the pin set itself has been altered"

    for anchor in pins:
        height = geoid.geoid_height(anchor.latitude, anchor.longitude, grid)
        assert round(height, 3) == round(anchor.geoid_height_m, 3), (
            f"{anchor.latitude}, {anchor.longitude}: geoid_height gives "
            f"{height:.6f}, which does not round to NGS's printed "
            f"{anchor.geoid_height_m}. This position discriminates the stencil "
            f"anchoring - the INTG nearest-node stencil reproduces NGS here "
            f"and the floor-anchored one does not - so this failure means the "
            f"anchoring has moved off INTG's (DESIGN.md #37)."
        )


@pytest.mark.anchor
def test_nearest_node_beats_floor_where_the_anchorings_diverge(grid):
    """The aggregate half of the WP-G1 gate, over all 120 positions.

    The exact pin above names the 36 positions where the anchorings disagree
    about NGS's printed figure. This one holds the aggregate, so a change that
    somehow satisfied those 36 while degrading everywhere else would still
    show. Honest remainder, recorded in the fixture: at 19 of the 120 the
    floor anchoring rounds to NGS and nearest-node does not - printing-boundary
    noise against 36 the other way - and the aggregate is what decides.

    Measured (DESIGN.md #36, reproduced independently at the WP-G1 gate):

        floor-anchored   rms 0.715 mm   66/120 round to NGS's figure
        nearest-node     rms 0.454 mm   83/120
    """
    from tests.fixtures.geoid_discriminating_anchors import DISCRIMINATING_ANCHORS

    def stats(interpolate):
        residuals = [
            interpolate(a.latitude, a.longitude) - a.geoid_height_m
            for a in DISCRIMINATING_ANCHORS
        ]
        rms = (sum(r * r for r in residuals) / len(residuals)) ** 0.5
        rounds = sum(
            1
            for a in DISCRIMINATING_ANCHORS
            if round(interpolate(a.latitude, a.longitude), 3)
            == round(a.geoid_height_m, 3)
        )
        return rms, rounds

    shipped_rms, shipped_rounds = stats(
        lambda lat, lon: geoid.geoid_height(lat, lon, grid)
    )
    floor_rms, floor_rounds = stats(grid.interpolate_biquadratic)

    # What ships must be the nearest-node figures, to the tenth of a millimetre.
    assert shipped_rms == pytest.approx(0.000454, abs=5e-5)
    assert shipped_rounds == 83
    # And the floor stencil must remain measurably worse here - if this half
    # ever fails, the fixture's premise has changed and #37 must be revisited,
    # not the assertion loosened.
    assert floor_rms == pytest.approx(0.000715, abs=5e-5)
    assert floor_rounds == 66
    assert shipped_rms < floor_rms


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
    assert geoid._lagrange3(values, 0.0) == pytest.approx(5.0)
    assert geoid._lagrange3(values, 1.0) == pytest.approx(4.0)
    assert geoid._lagrange3(values, 2.0) == pytest.approx(7.0)
    assert geoid._lagrange3(values, 0.5) == pytest.approx(4.0)
    assert geoid._lagrange3(values, 1.5) == pytest.approx(5.0)


def test_longitude_convention_round_trips():
    """The file stores 0-360 east; the program uses signed, negative west."""
    assert geoid._to_east_longitude(-84.5) == pytest.approx(275.5)
    assert geoid._to_east_longitude(12.0) == pytest.approx(12.0)
    assert geoid._to_signed_longitude(275.5) == pytest.approx(-84.5)
    assert geoid._to_signed_longitude(12.0) == pytest.approx(12.0)


# --------------------------------------------------------------------------
# Refusals.
# --------------------------------------------------------------------------


def test_a_point_outside_the_tile_is_refused_by_name(grid):
    """Fails closed, and says what it means for the output."""
    with pytest.raises(geoid.GeoidError) as caught:
        geoid.geoid_height(35.0, -84.0, grid)  # Tennessee, south of the tile

    message = str(caught.value)
    assert "outside the GEOID18 tile" in message
    assert "no elevation or combined factor" in message


def test_a_truncated_grid_is_refused(tmp_path):
    original = geoid.GEOID18_TILE.read_bytes()
    truncated = tmp_path / "short.bin"
    truncated.write_bytes(original[: 44 + 1000])

    with pytest.raises(geoid.GeoidError, match="truncated or corrupt"):
        geoid.load_grid(truncated)


def test_a_file_too_short_for_a_header_is_refused(tmp_path):
    stub = tmp_path / "stub.bin"
    stub.write_bytes(b"\x00" * 12)

    with pytest.raises(geoid.GeoidError, match="too short"):
        geoid.load_grid(stub)


def test_a_big_endian_grid_is_refused(tmp_path):
    """NGS also publishes a Unix (big-endian) form; reading it here would give
    garbage that still looked like numbers, so IKIND is checked."""
    header = struct.pack("<4d3i", 40.0, 264.0, 1 / 60, 1 / 60, 2, 2, 2)
    wrong = tmp_path / "be.bin"
    wrong.write_bytes(header + b"\x00" * 16)

    with pytest.raises(geoid.GeoidError, match="IKIND"):
        geoid.load_grid(wrong)


def test_a_missing_grid_is_refused_with_a_useful_message(tmp_path):
    with pytest.raises(geoid.GeoidError, match="installation is incomplete"):
        geoid.load_grid(tmp_path / "not-here.bin")


def test_checksum_verification_catches_a_tampered_grid(tmp_path):
    """``verify_checksum`` is opt-in on ``load_grid``; prove it works.

    The production path (``load_shipped_grid`` / ``default_grid``) turns it on
    unconditionally - see the finding-6 tests below.
    """
    original = bytearray(geoid.GEOID18_TILE.read_bytes())
    original[100] ^= 0xFF  # flip a byte in the payload
    tampered = tmp_path / "tampered.bin"
    tampered.write_bytes(bytes(original))

    # It still loads and still produces numbers - which is exactly why the
    # checksum matters.
    geoid.load_grid(tampered)

    with pytest.raises(geoid.GeoidError, match="does not match"):
        geoid.load_grid(tampered, verify_checksum=True)


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
    payload = geoid.GEOID18_TILE.read_bytes()[44:]
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
    grid_swapped = geoid.load_grid(swapped)
    wrong = grid_swapped.height_biquadratic(43.0, -84.5)

    # 5 mm of slack on a 5.158 m discrepancy - loose enough not to pin the
    # reviewer's last digit, tight enough that only the transposed reading
    # produces it.
    assert wrong == pytest.approx(-27.927, abs=0.005)

    truth = geoid.load_grid().height_biquadratic(43.0, -84.5)
    assert truth == pytest.approx(-33.085, abs=0.005)
    assert abs(truth - wrong) == pytest.approx(5.158, abs=0.01)


def test_a_row_column_swap_is_refused_when_the_tile_is_the_shipped_one(tmp_path):
    """Finding 6(b), pinned with the reviewer's own counterexample.

    Same file as the test above. Declaring which tile it is meant to be is what
    catches it, because the geometry is the only thing the transposition
    changes that anything can check.
    """
    swapped = _tile_with_header(tmp_path, "swapped.bin", rows=1141, columns=1081)

    with pytest.raises(geoid.GeoidError) as caught:
        geoid.load_grid(swapped, expect_geometry=geoid.GEOID18_U3_GEOMETRY)

    message = str(caught.value)
    # Names what is wrong, with both numbers, and what it means for the output.
    assert "NLAT (row count): expected 1081, found 1141" in message
    assert "NLON (column count): expected 1141, found 1081" in message
    assert "wrong cell" in message

    # And the production entry point refuses it too, by the same rule.
    with pytest.raises(geoid.GeoidError):
        geoid.load_shipped_grid(swapped)


def test_the_production_path_authenticates_the_grid(tmp_path):
    """Finding 6(a): ``default_grid`` is what production calls, so it checks.

    Previously ``load_grid``'s ``verify_checksum`` defaulted to False and
    ``default_grid`` took that default, so the pin was enforced only by the test
    suite and the frozen bundle's self-test - never by the running program.

    Exercised through ``load_shipped_grid``, which is the policy ``default_grid``
    applies. The claim that ``default_grid`` actually routes through it is not
    left to this docstring: ``test_the_cached_grid_comes_through_the_authenticated_path``
    below pins the wiring itself.
    """
    original = bytearray(geoid.GEOID18_TILE.read_bytes())
    original[100] ^= 0xFF  # flip a byte in the payload, leaving the header valid
    tampered = tmp_path / "tampered.bin"
    tampered.write_bytes(bytes(original))

    # Same file the unchecked reader accepted in
    # test_checksum_verification_catches_a_tampered_grid.
    geoid.load_grid(tampered)

    with pytest.raises(geoid.GeoidError, match="does not match"):
        geoid.load_shipped_grid(tampered)

    # The real file passes both gates, so the check is not simply refusing
    # everything.
    assert geoid.load_shipped_grid().row_count == 1081
    assert geoid.default_grid().column_count == 1141


def test_the_cached_grid_comes_through_the_authenticated_path(monkeypatch):
    """``default_grid`` must not be a second, laxer loader.

    The test above proves ``load_shipped_grid`` enforces the checksum and the
    geometry; this one proves ``default_grid`` actually goes through it. Without
    this pin, ``default_grid`` rewired to call ``load_grid`` bare - both gates
    gone - left the whole suite green (found by the independent review of the
    vertical branch, which seeded exactly that; the identical pin already
    existed for ``vertcon.default_grids`` and this module lacked it). Cleared
    and reloaded so the lru_cache cannot hide which path was taken; the cache is
    cleared again afterwards so later tests do not share a grid loaded under
    the monkeypatch.
    """
    called: list[bool] = []
    real = geoid.load_shipped_grid

    def recording(*args, **kwargs):
        called.append(True)
        return real(*args, **kwargs)

    monkeypatch.setattr(geoid, "load_shipped_grid", recording)
    geoid.default_grid.cache_clear()
    try:
        geoid.default_grid()
        assert called == [True]
    finally:
        geoid.default_grid.cache_clear()


def test_the_canonical_geometry_is_the_one_the_readme_documents(grid):
    """The expectation must match the file, or it is just a second guess.

    GEOID18 CONUS grid #3: 40-58 N, 96-77 W, one arcminute, 1081 x 1141.
    Hand check of the extents from the counts alone:
        north = 40.0 + (1081 - 1) / 60 = 40 + 18 = 58 N
        east  = 264.0 + (1141 - 1) / 60 = 264 + 19 = 283 E = 283 - 360 = 77 W
    """
    expected = geoid.GEOID18_U3_GEOMETRY

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
    geoid.load_shipped_grid()

    nudged = _tile_with_header(tmp_path, "nudged.bin", dlat=1 / 60 + 1e-7)
    with pytest.raises(geoid.GeoidError, match="DLAT"):
        geoid.load_grid(nudged, expect_geometry=geoid.GEOID18_U3_GEOMETRY)

    # A shifted origin is caught the same way.
    shifted = _tile_with_header(tmp_path, "shifted.bin", south=41.0)
    with pytest.raises(geoid.GeoidError, match="SLAT"):
        geoid.load_grid(shifted, expect_geometry=geoid.GEOID18_U3_GEOMETRY)


def test_a_non_positive_or_non_finite_spacing_is_refused(tmp_path):
    """The interpolators divide by the spacing; zero or negative is nonsense.

    Checked in ``load_grid`` with no expectation passed, because this holds for
    any geoid grid, not just the shipped one.
    """
    for value, label in ((0.0, "DLAT"), (-1 / 60, "DLAT")):
        path = _tile_with_header(tmp_path, f"dlat{value}.bin", dlat=value)
        with pytest.raises(geoid.GeoidError, match=label):
            geoid.load_grid(path)

    path = _tile_with_header(tmp_path, "dlon_nan.bin", dlon=float("nan"))
    with pytest.raises(geoid.GeoidError, match="DLON"):
        geoid.load_grid(path)


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

    with pytest.raises(geoid.GeoidError, match="NLAT=2"):
        geoid.load_grid(path)


def test_a_non_finite_payload_value_is_refused(tmp_path):
    """A NaN cell would become a NaN geoid height, then a NaN combined factor.

    Nothing downstream refuses a NaN - it is not an exception and not a number,
    and it would be printed in the audit file beside real values. Redundant with
    the checksum on the shipped tile, and not redundant for any other file
    ``load_grid`` is pointed at.
    """
    payload = bytearray(geoid.GEOID18_TILE.read_bytes()[44:])
    payload[0:4] = struct.pack("<f", float("nan"))
    path = tmp_path / "nan.bin"
    path.write_bytes(
        struct.pack("<4d3i", 40.0, 264.0, 1 / 60, 1 / 60, 1081, 1141, 1) + bytes(payload)
    )

    with pytest.raises(geoid.GeoidError, match="non-finite geoid height"):
        geoid.load_grid(path)


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
    # The local was named ``geoid`` before the module rename (WP-V5a); it now
    # carries a suffix so it cannot shadow the ``geoid`` module it is read from.
    geoid_height_m = geoid.geoid_height(latitude, longitude, grid)

    assert orthometric == pytest.approx(243.84, abs=1e-9)
    assert geoid_height_m == pytest.approx(-33.637, abs=GEOID_TOLERANCE_M)

    factors = factors_at(point.target_scale_factor, orthometric, geoid_height_m)

    assert factors.ellipsoid_height == pytest.approx(210.203, abs=0.002)
    assert factors.elevation_factor == pytest.approx(0.99996701, abs=1e-8)
    assert factors.combined_factor == pytest.approx(
        point.target_scale_factor * factors.elevation_factor, rel=1e-15
    )
    assert factors.combined_factor < factors.elevation_factor
    assert factors.combined_factor < point.target_scale_factor
