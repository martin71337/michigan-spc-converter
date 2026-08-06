"""The polynomial engine, and its agreement with the rigorous one.

The polynomial method is checked three ways:

1. Against the NCAT anchors directly - it must reach NGS's numbers by its own
   route, not merely agree with our other engine.
2. Against the rigorous engine over a dense lattice covering each zone, where
   both must land inside NGS's stated 0.5 mm fitting accuracy.
3. Outside the fitted band, where the design expects and tolerates divergence -
   tested explicitly so the limitation is documented by evidence rather than
   by comment, and so a future change that silently made it worse would show.
"""

from __future__ import annotations

import math

import pytest

from michspc.spc import agreement as ag
from michspc.spc import polynomial as poly
from michspc.spc.lambert import constants_for
from michspc.spc.lambert import forward as rigorous_forward
from michspc.spc.lambert import inverse as rigorous_inverse
from michspc.spc.zones import ALL_ZONES, MI_NORTH, MI_SOUTH, zone_by_code
from tests.fixtures.appendix_c import ALL_PUBLISHED
from tests.fixtures.ncat_anchors import NCAT_ANCHORS

ANCHOR_IDS = [f"{a.zone_code}@{a.latitude}/{a.longitude:.4f}" for a in NCAT_ANCHORS]


def engines_for(zone):
    return constants_for(zone), poly.coefficients_for(zone.code)


# --------------------------------------------------------------------------
# The coefficient tables themselves.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("published", ALL_PUBLISHED, ids=lambda p: p.zone_code)
def test_F1_equals_the_published_central_parallel_scale_factor(published):
    """Appendix C prints F(1) and ko as the same number for every zone.

    They are reached by different routes - ko from the rigorous zone-constant
    derivation, F(1) as the leading term of a fitted series - so this is a real
    consistency check across the two methods at the central parallel, using our
    independently derived k_origin as the third party.
    """
    coefficients = poly.coefficients_for(published.zone_code)
    constants = constants_for(zone_by_code(published.zone_code))

    assert coefficients.F[0] == published.ko
    assert constants.k_origin == pytest.approx(coefficients.F[0], abs=5e-13)


def test_michigan_north_needs_five_coefficients_and_the_others_four():
    """The manual fits only as many terms as a zone's size requires (PDF p. 54).

    Michigan North is large enough to need five; Central and South need four.
    Padding the shorter tables with zeros would be harmless arithmetically but
    would misrepresent what Appendix C publishes, so the tables carry exactly
    what is printed and this pins that.
    """
    assert len(poly.MI_NORTH_COEFFICIENTS.L) == 5
    assert len(poly.MI_NORTH_COEFFICIENTS.G) == 5
    assert len(poly.MI_CENTRAL_COEFFICIENTS.L) == 4
    assert len(poly.MI_CENTRAL_COEFFICIENTS.G) == 4
    assert len(poly.MI_SOUTH_COEFFICIENTS.L) == 4
    assert len(poly.MI_SOUTH_COEFFICIENTS.G) == 4

    for coefficients in poly.ALL_COEFFICIENTS:
        assert len(coefficients.F) == 3


def test_horner_evaluates_the_series_the_manual_writes():
    """_horner must produce c1 x + c2 x^2 + c3 x^3, with no constant term.

    Hand derivation with c = (2, 3, 5) and x = 10:
        2*10 + 3*100 + 5*1000 = 20 + 300 + 5000 = 5320
    """
    assert poly._horner((2.0, 3.0, 5.0), 10.0) == pytest.approx(5320.0, rel=1e-15)

    # And the degenerate cases, which the zone tables never hit but the
    # function must not silently mishandle.
    assert poly._horner((), 10.0) == 0.0
    assert poly._horner((7.0,), 3.0) == pytest.approx(21.0, rel=1e-15)


def test_coefficients_for_refuses_an_unknown_zone():
    with pytest.raises(KeyError, match="No Appendix C polynomial coefficients"):
        poly.coefficients_for("9999")


# --------------------------------------------------------------------------
# Anchors: the polynomial engine against NGS NCAT, by its own route.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", NCAT_ANCHORS, ids=ANCHOR_IDS)
def test_polynomial_forward_matches_ncat(anchor):
    """Held to 1.5 mm: NCAT's 0.5 mm printing plus NGS's 0.5 mm fitting accuracy.

    Looser than the rigorous engine's 1 mm because the polynomial method carries
    its own stated approximation error on top of NCAT's quantization.
    """
    zone = zone_by_code(anchor.zone_code)
    constants, coefficients = engines_for(zone)
    point = poly.forward(anchor.latitude, anchor.longitude, constants, coefficients)

    assert point.northing == pytest.approx(anchor.northing_m, abs=0.0015)
    assert point.easting == pytest.approx(anchor.easting_m, abs=0.0015)
    assert point.scale_factor == pytest.approx(anchor.scale_factor, abs=5e-8)


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", NCAT_ANCHORS, ids=ANCHOR_IDS)
def test_polynomial_inverse_recovers_the_anchor_position(anchor):
    """NGS's northing/easting through our polynomial inverse, back to lat/long."""
    zone = zone_by_code(anchor.zone_code)
    constants, coefficients = engines_for(zone)
    position = poly.inverse(
        anchor.northing_m, anchor.easting_m, constants, coefficients
    )

    # 1.5 mm of northing is about 1.4e-8 degrees of latitude.
    assert position.latitude == pytest.approx(anchor.latitude, abs=5e-8)
    assert position.longitude == pytest.approx(anchor.longitude, abs=5e-8)


# --------------------------------------------------------------------------
# Agreement between the engines, inside each zone.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_engines_agree_across_each_zone(zone):
    """Dense lattice over the zone's whole extent, held to NGS's 0.5 mm.

    Reports the worst separation on failure so a regression says how bad it got,
    not merely that it happened.
    """
    constants, coefficients = engines_for(zone)

    worst = 0.0
    worst_at = None
    for i in range(13):
        latitude = zone.lat_min + (zone.lat_max - zone.lat_min) * i / 12.0
        for j in range(13):
            longitude = zone.lon_min + (zone.lon_max - zone.lon_min) * j / 12.0
            a = rigorous_forward(latitude, longitude, constants)
            b = poly.forward(latitude, longitude, constants, coefficients)
            separation = ag.compare(a, b).distance
            if separation > worst:
                worst, worst_at = separation, (latitude, longitude)

    assert worst <= ag.AGREEMENT_TOLERANCE_M, (
        f"{zone.abbrev}: engines disagree by {worst * 1000:.4f} mm at "
        f"{worst_at}, above the {ag.AGREEMENT_TOLERANCE_M * 1000:.1f} mm tolerance"
    )


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_engines_agree_on_the_inverse_across_each_zone(zone):
    """Same lattice, driven backwards from grid coordinates."""
    constants, coefficients = engines_for(zone)

    worst_metres = 0.0
    for i in range(13):
        latitude = zone.lat_min + (zone.lat_max - zone.lat_min) * i / 12.0
        for j in range(13):
            longitude = zone.lon_min + (zone.lon_max - zone.lon_min) * j / 12.0
            grid = rigorous_forward(latitude, longitude, constants)
            a = rigorous_inverse(grid.northing, grid.easting, constants)
            b = poly.inverse(grid.northing, grid.easting, constants, coefficients)
            # Convert the latitude difference to meters for a comparable bound;
            # one degree of latitude is about 111,120 m in Michigan.
            worst_metres = max(worst_metres, abs(a.latitude - b.latitude) * 111120.0)

    assert worst_metres <= ag.AGREEMENT_TOLERANCE_M, (
        f"{zone.abbrev}: inverse engines disagree by {worst_metres * 1000:.4f} mm"
    )


# --------------------------------------------------------------------------
# The documented limitation, proven rather than asserted.
# --------------------------------------------------------------------------


def test_polynomial_degrades_far_outside_its_fitted_band():
    """The reason the rigorous engine is primary (docs/DESIGN.md section 5).

    Michigan North's coefficients were fit between roughly 45N and 48N. Evaluate
    them at Michigan South's latitudes - which is exactly what a cross-zone
    conversion asks of them - and the fit falls apart, while the rigorous
    equations remain exact.

    This test exists so the limitation is evidence, not a comment. If a future
    change made the polynomials appear to work everywhere, that would mean the
    two engines were no longer independent, and this test would fail.
    """
    constants, coefficients = engines_for(MI_NORTH)

    # About 3.5 degrees south of Michigan North's southern standard parallel.
    latitude, longitude = 42.0, -87.0
    a = rigorous_forward(latitude, longitude, constants)
    b = poly.forward(latitude, longitude, constants, coefficients)
    separation = ag.compare(a, b).distance

    assert separation > ag.AGREEMENT_TOLERANCE_M, (
        "Expected the polynomial fit to degrade well outside its band; it did "
        f"not (separation {separation * 1000:.4f} mm). Either the band is wider "
        "than documented or the two engines are no longer independent."
    )


def test_cross_zone_conversion_is_where_the_polynomial_method_actually_fails():
    """The concrete reason this program does not use the polynomial method alone.

    A cross-zone conversion evaluates the TARGET zone's polynomial at the
    SOURCE point's latitude. For a point near the top of Michigan North
    (48.4N) expressed in Michigan South coordinates, that is 4.7 degrees below
    the band Michigan South's coefficients were fit to.

    Measured 2026-08-05, target-zone polynomial against the rigorous equations,
    on each target zone's central meridian:

        point in   expressed as   latitude   polynomial error
        MI North   MI Central       48.40       408 mm
        MI North   MI South         48.40      3355 mm
        MI Central MI South         46.00       159 mm
        MI South   MI North         41.60       110 mm
        MI South   MI Central       41.60       147 mm
        MI Central MI North         43.50         4 mm

    Over three metres. The prior MATLAB tool this program replaces used the
    polynomial method alone; had this program done the same, a cross-zone
    conversion could have been wrong by that much with nothing to reveal it.

    This test pins the magnitude so the finding cannot quietly stop being true.
    """
    south_constants = constants_for(MI_SOUTH)
    south_coefficients = poly.coefficients_for(MI_SOUTH.code)

    latitude = 48.40
    longitude = MI_SOUTH.definition.lon_origin

    a = rigorous_forward(latitude, longitude, south_constants)
    b = poly.forward(latitude, longitude, south_constants, south_coefficients)
    separation = ag.compare(a, b).distance

    assert separation > 1.0, (
        f"Expected metre-scale polynomial error for a Michigan North latitude "
        f"in Michigan South coordinates; measured {separation:.4f} m. If this "
        f"has become small, verify the two engines are still independent."
    )


def test_agreement_reports_and_refuses():
    """require_agreement passes inside tolerance and names the point outside it."""
    inside = ag.Agreement(northing_difference=0.0001, easting_difference=0.0001)
    assert inside.within_tolerance
    ag.require_agreement(inside, "point 101")  # must not raise

    outside = ag.Agreement(northing_difference=0.02, easting_difference=0.0)
    assert not outside.within_tolerance
    with pytest.raises(ag.EngineDisagreementError, match="point 207"):
        ag.require_agreement(outside, "point 207")


def test_agreement_distance_is_the_euclidean_separation():
    """Hand derivation: a 3-4-5 triangle in millimetres."""
    a = ag.Agreement(northing_difference=0.003, easting_difference=0.004)
    assert a.distance == pytest.approx(0.005, rel=1e-15)
    assert "5.0000 mm" in a.describe()


def test_polynomial_refuses_an_impossible_latitude():
    constants, coefficients = engines_for(MI_SOUTH)
    with pytest.raises(ValueError, match="not a valid geodetic latitude"):
        poly.forward(95.0, -84.0, constants, coefficients)


def test_polynomial_inverse_refuses_beyond_the_cone_apex():
    constants, coefficients = engines_for(MI_SOUTH)
    beyond_apex = constants.northing_origin + constants.R_origin + 1.0
    with pytest.raises(ValueError, match="apex of the projection cone"):
        poly.inverse(beyond_apex, 4000000.0, constants, coefficients)
