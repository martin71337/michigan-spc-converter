"""The anchor that gates WP1.

NOAA Manual NOS NGS 5 publishes, for every Lambert zone, both the *defining*
constants (Appendix A / C) and the *derived* constants NGS computed from them
(Appendix C). Our registry stores only the defining constants. This module
proves that michspc.spc.lambert reproduces every published derived constant from
those defining constants alone, for all three Michigan zones.

That makes this an independent check in the strongest available sense: the
expected values were computed by NGS in the 1980s, published in a document
committed to this repository, and transcribed into tests/fixtures/appendix_c.py
without passing through any code of ours.

Tolerance is half a unit in the last decimal place NGS printed. A published
figure cannot be held to more than that, and holding it to less would let a real
error hide.
"""

from __future__ import annotations

import math

import pytest

from michspc.spc.ellipsoid import GRS80, Ellipsoid
from michspc.spc.lambert import LambertConstants, constants_for, forward
from michspc.spc.zones import MI_CENTRAL, MI_NORTH, MI_SOUTH, ALL_ZONES
from tests.fixtures.appendix_c import (
    ALL_PUBLISHED,
    MI_CENTRAL_PUBLISHED,
    MI_NORTH_PUBLISHED,
    MI_SOUTH_PUBLISHED,
    PRINTED_DECIMALS,
    PublishedConstants,
)

ZONE_PAIRS = [
    pytest.param(MI_NORTH, MI_NORTH_PUBLISHED, id="MI-N-2111"),
    pytest.param(MI_CENTRAL, MI_CENTRAL_PUBLISHED, id="MI-C-2112"),
    pytest.param(MI_SOUTH, MI_SOUTH_PUBLISHED, id="MI-S-2113"),
]


def tolerance_for(quantity: str) -> float:
    """Half a unit in the last decimal place NGS printed."""
    return 0.5 * 10.0 ** (-PRINTED_DECIMALS[quantity])


# --------------------------------------------------------------------------
# The ellipsoid the zone constants are built on.
# --------------------------------------------------------------------------


@pytest.mark.anchor
def test_grs80_semiminor_axis_matches_the_manual():
    """Manual section 1.7, PDF p. 23, publishes b alongside a and 1/f.

    Hand derivation:
      f = 1 / 298.25722210088
      b = a(1 - f) = 6378137 * (1 - 1/298.25722210088)

    The manual states b = 6,356,752.3141403 m "to 14 significant digits", which
    puts the last printed figure at 1e-7 m; half a unit there is 5e-8.
    """
    assert GRS80.b == pytest.approx(6356752.3141403, abs=5e-8)


@pytest.mark.anchor
def test_grs80_eccentricity_squared_is_within_the_manuals_own_rounding():
    """The manual's printed 1/f and e^2 are very slightly inconsistent.

    Manual p. 23 prints both to 14 significant digits, each correctly rounded
    from the exact GRS 80 values:

        1/f = 298.25722210088          (exact: 298.257222100882711...)
        e^2 = 0.0066943800229034       (exact: 0.006694380022903416...)

    Deriving e^2 from the *printed* 1/f rather than the exact one gives
    0.006694380022903476 - about 1.5 units in e^2's last printed place, or
    6.0e-17 absolute. The two published figures cannot both be reproduced from
    one another at full printed precision; that is an artifact of independent
    rounding, not an error in either.

    We keep fidelity to the committed source and use the printed 1/f, because
    that is the number a reader checking our work against the manual would use.
    The consequence is bounded and measured by the test below.
    """
    e2_from_printed_inv_f = 0.006694380022903476
    assert GRS80.e2 == pytest.approx(e2_from_printed_inv_f, abs=1e-18)

    # And it sits within 1.5 units of the last place of the manual's printed e^2.
    assert abs(GRS80.e2 - 0.0066943800229034) < 1.0e-16


@pytest.mark.anchor
def test_the_ellipsoid_rounding_choice_cannot_move_a_coordinate():
    """Bound the consequence of the rounding above, rather than assuming it.

    Recomputes Michigan coordinates on an ellipsoid built from the unrounded
    GRS 80 flattening and compares against our manual-faithful one, at the
    corners and centre of every zone's extent. If the choice of printed versus
    exact 1/f could ever move a coordinate by a meaningful amount, this fails.

    Measured worst case across all three zones: 9.3e-10 m, under one nanometer
    - six orders of magnitude below the 0.5 mm tolerance the two computation
    engines are held to.
    """
    exact = Ellipsoid(
        name="GRS 80 (unrounded flattening)",
        a=6378137.0,
        inv_f=298.257222100882711,
        citation="GRS 80 derived value, unrounded; used for bounding only",
    )

    worst = 0.0
    for zone in ALL_ZONES:
        manual_constants = constants_for(zone)
        exact_constants = constants_for(zone, exact)
        latitudes = (zone.lat_min, (zone.lat_min + zone.lat_max) / 2.0, zone.lat_max)
        for latitude in latitudes:
            for longitude in (zone.lon_min, zone.lon_max):
                a = forward(latitude, longitude, manual_constants)
                b = forward(latitude, longitude, exact_constants)
                worst = max(
                    worst,
                    abs(a.northing - b.northing),
                    abs(a.easting - b.easting),
                )

    assert worst < 1e-8, (
        f"Ellipsoid rounding moved a coordinate by {worst:.3e} m, which is "
        f"larger than expected and needs investigating."
    )


# --------------------------------------------------------------------------
# Every published derived constant, all three zones.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("zone,published", ZONE_PAIRS)
def test_central_parallel_matches_published(zone, published: PublishedConstants):
    """Bo, the latitude whose sine is the cone constant. Appendix C prints 10 dp."""
    constants = constants_for(zone)
    assert constants.lat_origin == pytest.approx(published.Bo, abs=tolerance_for("Bo"))


@pytest.mark.anchor
@pytest.mark.parametrize("zone,published", ZONE_PAIRS)
def test_sine_of_central_parallel_matches_published(zone, published):
    """SinBo, the cone constant itself. Appendix C prints 12 dp."""
    constants = constants_for(zone)
    assert constants.sin_lat_origin == pytest.approx(
        published.SinBo, abs=tolerance_for("SinBo")
    )


@pytest.mark.anchor
@pytest.mark.parametrize("zone,published", ZONE_PAIRS)
def test_mapping_radius_at_equator_matches_published(zone, published):
    """K. Appendix C prints 4 dp, so 0.05 mm."""
    constants = constants_for(zone)
    assert constants.K == pytest.approx(published.K, abs=tolerance_for("K"))


@pytest.mark.anchor
@pytest.mark.parametrize("zone,published", ZONE_PAIRS)
def test_mapping_radius_at_grid_origin_matches_published(zone, published):
    """Rb. Appendix C prints 4 dp."""
    constants = constants_for(zone)
    assert constants.R_grid_origin == pytest.approx(published.Rb, abs=tolerance_for("Rb"))


@pytest.mark.anchor
@pytest.mark.parametrize("zone,published", ZONE_PAIRS)
def test_mapping_radius_at_central_parallel_matches_published(zone, published):
    """Ro. Appendix C prints 4 dp."""
    constants = constants_for(zone)
    assert constants.R_origin == pytest.approx(published.Ro, abs=tolerance_for("Ro"))


@pytest.mark.anchor
@pytest.mark.parametrize("zone,published", ZONE_PAIRS)
def test_northing_at_projection_origin_matches_published(zone, published):
    """No = Rb + Nb - Ro. Appendix C prints 4 dp.

    Michigan's Nb is 0 in all three zones, so No is simply Rb - Ro; for MI South
    that is 7,031,167.2907 - 6,877,323.4058 = 153,843.8849, against a published
    153,843.8848. The one-unit difference in the last place is the published
    figures' own rounding, which is exactly what the tolerance allows for.
    """
    constants = constants_for(zone)
    assert constants.northing_origin == pytest.approx(
        published.No, abs=tolerance_for("No")
    )


@pytest.mark.anchor
@pytest.mark.parametrize("zone,published", ZONE_PAIRS)
def test_scale_factor_at_central_parallel_matches_published(zone, published):
    """ko. Appendix C prints 12 dp.

    Appendix C also prints ko as F(1), the leading coefficient of the polynomial
    grid scale factor series - the same number reached by an entirely different
    route. WP2 checks that agreement.
    """
    constants = constants_for(zone)
    assert constants.k_origin == pytest.approx(published.ko, abs=tolerance_for("ko"))


@pytest.mark.anchor
@pytest.mark.parametrize("zone,published", ZONE_PAIRS)
def test_meridian_radius_at_origin_matches_published(zone, published):
    """Mo = ko * a(1 - e^2) / (1 - e^2 sin^2 Bo)^(3/2). Appendix C prints 4 dp."""
    constants = constants_for(zone)
    assert constants.M_origin == pytest.approx(published.Mo, abs=tolerance_for("Mo"))


@pytest.mark.anchor
@pytest.mark.parametrize("zone,published", ZONE_PAIRS)
def test_geometric_mean_radius_at_origin_matches_published(zone, published):
    """ro = ko * sqrt(M * N) at Bo. Appendix C prints it whole, so 0.5 m."""
    constants = constants_for(zone)
    assert constants.r_origin == pytest.approx(published.ro, abs=tolerance_for("ro"))


# --------------------------------------------------------------------------
# Internal consistency checks the manual's own redundancy makes available.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_K_agrees_from_both_standard_parallels(zone):
    """The manual gives K twice, in terms of each standard parallel.

    Section 3.12 (PDF p. 37):

        K = a cos(phi_s) exp(Q_s sin phi_0) / (W_s sin phi_0)
        K = a cos(phi_n) exp(Q_n sin phi_0) / (W_n sin phi_0)

    from_two_parallels uses the southern form. The northern form is computed
    here independently; equality is a free check on sin(phi_0), Q and W all at
    once, since an error in any of them would break the agreement.
    """
    constants = constants_for(zone)
    definition = zone.definition

    sin_n = math.sin(math.radians(definition.lat_north))
    cos_n = math.cos(math.radians(definition.lat_north))
    W_n = GRS80.W(sin_n)
    Q_n = GRS80.isometric_latitude(sin_n)

    K_from_north = (
        GRS80.a
        * cos_n
        * math.exp(Q_n * constants.sin_lat_origin)
        / (W_n * constants.sin_lat_origin)
    )

    # Both forms are exact in theory; the difference is floating-point noise on
    # a quantity of order 1.2e7 m, so a relative tolerance near machine epsilon.
    assert K_from_north == pytest.approx(constants.K, rel=1e-14)


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_scale_factor_is_unity_at_both_standard_parallels(zone):
    """The defining property of the two standard parallels.

    A Lambert conformal conic with two standard parallels has, by construction,
    grid scale factor exactly 1 where the cone cuts the ellipsoid. Nothing in
    from_two_parallels asserts this; it falls out of the derivation, so it is a
    genuine independent check on K, sin(phi_0) and the scale factor equation
    together.
    """
    constants = constants_for(zone)

    for latitude in (zone.definition.lat_south, zone.definition.lat_north):
        sin_lat = math.sin(math.radians(latitude))
        Q = GRS80.isometric_latitude(sin_lat)
        R = constants.K / math.exp(Q * constants.sin_lat_origin)
        k = constants._scale_factor(sin_lat, R)
        assert k == pytest.approx(1.0, abs=1e-14), (
            f"{zone.abbrev}: scale factor at standard parallel {latitude} "
            f"should be exactly 1, got {k!r}"
        )


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_scale_factor_at_central_parallel_is_below_unity(zone):
    """Between the standard parallels the cone lies inside the ellipsoid.

    So k < 1 there, minimised at the central parallel. Appendix C's published ko
    values are all just under 1 (0.99990 to 0.99991 for Michigan), which this
    checks the sign and rough magnitude of independently of the exact value.
    """
    constants = constants_for(zone)
    assert 0.9998 < constants.k_origin < 1.0


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_central_parallel_lies_between_the_standard_parallels(zone):
    """A structural sanity check on sin(phi_0).

    The central parallel is where the cone is furthest inside the ellipsoid, so
    it must fall strictly between the two standard parallels. A sign error or a
    swapped pair in the sin(phi_0) derivation would violate this.
    """
    constants = constants_for(zone)
    assert zone.definition.lat_south < constants.lat_origin < zone.definition.lat_north


def test_lambert_constants_are_frozen():
    """Core result records are immutable (docs/DESIGN.md section 7)."""
    constants = constants_for(MI_SOUTH)
    with pytest.raises(Exception):
        constants.K = 1.0  # type: ignore[misc]


def test_from_two_parallels_is_reusable_without_a_registry_zone():
    """The constructor takes a definition, not a Zone.

    This is the seam that lets a future coordinate system arrive as data: any
    LambertTwoParallelDef produces working constants without the registry
    knowing about it (docs/DESIGN.md section 6).
    """
    constants = LambertConstants.from_two_parallels(MI_SOUTH.definition)
    assert constants.sin_lat_origin == pytest.approx(
        MI_SOUTH_PUBLISHED.SinBo, abs=tolerance_for("SinBo")
    )
