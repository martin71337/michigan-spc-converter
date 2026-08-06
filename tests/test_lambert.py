"""The Lambert engine against NGS's own implementation, and against itself.

Two independent classes of check:

1. **Anchors.** 27 lattice points across the three Michigan zones, computed by
   NGS's NCAT service and frozen in tests/fixtures/ncat_anchors.py. These pin
   our forward conversion, convergence angle and grid scale factor against an
   authority we did not write.

2. **Structural properties.** Facts that must hold by construction - the
   easting on the central meridian is exactly the false easting, convergence
   there is exactly zero, forward and inverse are true inverses. These catch
   whole classes of error that a lattice of anchors can miss, and they hold at
   every point rather than at 27 of them.
"""

from __future__ import annotations

import math

import pytest

from michspc.spc.lambert import constants_for, forward, inverse, ConvergenceError
from michspc.spc.units import INTERNATIONAL_FEET, METERS, US_SURVEY_FEET
from michspc.spc.zones import ALL_ZONES, MI_SOUTH, zone_by_code
from tests.fixtures.ncat_anchors import NCAT_ANCHORS

# NCAT prints linear values to 0.001 m, so a published figure carries +/-0.0005 m
# of quantization on its own. 0.001 m leaves a little headroom above that while
# still being far tighter than the 0.0005 m the two engines are held to.
LINEAR_TOLERANCE_M = 0.001

# NCAT prints convergence to 0.01 arc second.
CONVERGENCE_TOLERANCE_DEG = 0.01 / 3600.0

# NCAT prints the grid scale factor to 8 decimal places.
SCALE_FACTOR_TOLERANCE = 0.5e-8

ANCHOR_IDS = [
    f"{a.zone_code}@{a.latitude}/{a.longitude:.4f}" for a in NCAT_ANCHORS
]


# --------------------------------------------------------------------------
# Anchors: our forward conversion against NGS NCAT.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", NCAT_ANCHORS, ids=ANCHOR_IDS)
def test_forward_matches_ncat_northing_and_easting(anchor):
    """Expected values computed by NGS NCAT, not by this codebase."""
    constants = constants_for(zone_by_code(anchor.zone_code))
    point = forward(anchor.latitude, anchor.longitude, constants)

    assert point.northing == pytest.approx(anchor.northing_m, abs=LINEAR_TOLERANCE_M)
    assert point.easting == pytest.approx(anchor.easting_m, abs=LINEAR_TOLERANCE_M)


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", NCAT_ANCHORS, ids=ANCHOR_IDS)
def test_forward_matches_ncat_convergence(anchor):
    """Convergence angle, to the 0.01 arc second NCAT prints."""
    constants = constants_for(zone_by_code(anchor.zone_code))
    point = forward(anchor.latitude, anchor.longitude, constants)

    assert point.convergence == pytest.approx(
        anchor.convergence_deg, abs=CONVERGENCE_TOLERANCE_DEG
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", NCAT_ANCHORS, ids=ANCHOR_IDS)
def test_forward_matches_ncat_scale_factor(anchor):
    """Grid scale factor, to the 8 decimal places NCAT prints."""
    constants = constants_for(zone_by_code(anchor.zone_code))
    point = forward(anchor.latitude, anchor.longitude, constants)

    assert point.scale_factor == pytest.approx(
        anchor.scale_factor, abs=SCALE_FACTOR_TOLERANCE
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", NCAT_ANCHORS, ids=ANCHOR_IDS)
def test_inverse_recovers_the_anchor_latitude_and_longitude(anchor):
    """NCAT's northing/easting, fed to our inverse, must give back its lat/long.

    This is a genuine anchor rather than a round-trip: the input coordinates are
    NGS's numbers, not ours. Tolerance is set by NCAT's own 0.001 m printing -
    one millimetre of northing is about 9e-9 degrees of latitude, so 5e-8
    degrees is comfortably above the quantization floor and still about 5 mm.
    """
    constants = constants_for(zone_by_code(anchor.zone_code))
    position = inverse(anchor.northing_m, anchor.easting_m, constants)

    assert position.latitude == pytest.approx(anchor.latitude, abs=5e-8)
    assert position.longitude == pytest.approx(anchor.longitude, abs=5e-8)


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", NCAT_ANCHORS, ids=ANCHOR_IDS)
def test_unit_conversions_match_ncat(anchor):
    """NCAT publishes each point in meters, International feet and US survey feet.

    The three are the same physical position under three unit definitions, so
    this pins michspc.spc.units against NGS's own arithmetic. It is the check
    that would catch the International/US survey foot confusion - a 2 ppm error
    worth about 26 feet at Michigan South's false easting.
    """
    constants = constants_for(zone_by_code(anchor.zone_code))
    point = forward(anchor.latitude, anchor.longitude, constants)

    # 0.001 ft is finer than 0.001 m, so allow the tighter of the two floors
    # plus NCAT's own rounding: 0.005 ft is about 1.5 mm.
    foot_tolerance = 0.005

    assert INTERNATIONAL_FEET.from_meters(point.northing) == pytest.approx(
        anchor.northing_ift, abs=foot_tolerance
    )
    assert INTERNATIONAL_FEET.from_meters(point.easting) == pytest.approx(
        anchor.easting_ift, abs=foot_tolerance
    )
    assert US_SURVEY_FEET.from_meters(point.northing) == pytest.approx(
        anchor.northing_usft, abs=foot_tolerance
    )
    assert US_SURVEY_FEET.from_meters(point.easting) == pytest.approx(
        anchor.easting_usft, abs=foot_tolerance
    )
    assert METERS.from_meters(point.easting) == point.easting


# --------------------------------------------------------------------------
# Structural properties - true at every point, not just the 27 anchored ones.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_easting_on_the_central_meridian_is_exactly_the_false_easting(zone):
    """gamma = 0 on the central meridian, so E = E_0 + R sin(0) = E_0.

    Exact equality, not approximate: sin(0.0) is exactly 0.0 in IEEE754, so any
    departure means the convergence angle was not exactly zero - which would
    mean a sign or offset error in the longitude handling.
    """
    constants = constants_for(zone)
    for latitude in (zone.lat_min, zone.lat_max):
        point = forward(latitude, zone.definition.lon_origin, constants)
        assert point.easting == zone.definition.easting_origin
        assert point.convergence == 0.0


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_northing_at_the_projection_origin_matches_the_derived_constant(zone):
    """On the central meridian at the central parallel, N must equal N_0."""
    constants = constants_for(zone)
    point = forward(
        constants.lat_origin, zone.definition.lon_origin, constants
    )
    assert point.northing == pytest.approx(constants.northing_origin, abs=1e-9)


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_convergence_is_positive_east_of_the_central_meridian(zone):
    """Sign convention, stated once and checked.

    East of the central meridian grid north lies west of true north, giving a
    positive convergence in the manual's sign convention. NCAT agrees: at
    43N/84W in Michigan South, one degree east of the 84 22' central meridian,
    it reports +00 14 58.30.
    """
    constants = constants_for(zone)
    latitude = (zone.lat_min + zone.lat_max) / 2.0
    east = forward(latitude, zone.definition.lon_origin + 1.0, constants)
    west = forward(latitude, zone.definition.lon_origin - 1.0, constants)

    assert east.convergence > 0.0
    assert west.convergence < 0.0
    assert east.convergence == pytest.approx(-west.convergence, rel=1e-12)


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_forward_and_inverse_are_true_inverses(zone):
    """Round-trip over a dense lattice covering the whole zone extent.

    The manual notes (PDF p. 35) that these are one-to-one mappings and "the
    inverse computation must reproduce the original values". Tolerance is set
    near the floating-point floor rather than at a survey tolerance, because
    anything larger would let a real defect hide inside it.
    """
    constants = constants_for(zone)

    worst_lat = 0.0
    worst_lon = 0.0
    for i in range(9):
        latitude = zone.lat_min + (zone.lat_max - zone.lat_min) * i / 8.0
        for j in range(9):
            longitude = zone.lon_min + (zone.lon_max - zone.lon_min) * j / 8.0
            point = forward(latitude, longitude, constants)
            back = inverse(point.northing, point.easting, constants)
            worst_lat = max(worst_lat, abs(back.latitude - latitude))
            worst_lon = max(worst_lon, abs(back.longitude - longitude))

    # 1e-11 degrees is about 1 micrometre of ground distance.
    assert worst_lat < 1e-11, f"worst latitude round-trip error {worst_lat:.3e} deg"
    assert worst_lon < 1e-11, f"worst longitude round-trip error {worst_lon:.3e} deg"


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_forward_and_inverse_agree_on_convergence_and_scale_factor(zone):
    """The two routes to gamma and k must give the same answer.

    forward() computes convergence from the longitude difference and the scale
    factor from the geodetic latitude; inverse() computes convergence from the
    grid geometry and the scale factor from the recovered latitude. They are
    different expressions and must still agree.
    """
    constants = constants_for(zone)
    latitude = (zone.lat_min + zone.lat_max) / 2.0
    longitude = (zone.lon_min + zone.lon_max) / 2.0

    point = forward(latitude, longitude, constants)
    back = inverse(point.northing, point.easting, constants)

    assert back.convergence == pytest.approx(point.convergence, abs=1e-12)
    assert back.scale_factor == pytest.approx(point.scale_factor, rel=1e-14)


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_scale_factor_is_symmetric_about_the_central_parallel(zone):
    """k depends on distance from the central parallel, not on longitude.

    On a Lambert projection the grid scale factor is constant along a parallel.
    A defect that leaked longitude into the scale factor would break this.
    """
    constants = constants_for(zone)
    latitude = (zone.lat_min + zone.lat_max) / 2.0

    factors = [
        forward(latitude, longitude, constants).scale_factor
        for longitude in (zone.lon_min, zone.definition.lon_origin, zone.lon_max)
    ]
    for factor in factors[1:]:
        assert factor == pytest.approx(factors[0], rel=1e-14)


# --------------------------------------------------------------------------
# Refusals. The program fails closed rather than inventing a plausible answer.
# --------------------------------------------------------------------------


def test_forward_refuses_an_impossible_latitude():
    constants = constants_for(MI_SOUTH)
    with pytest.raises(ValueError, match="not a valid geodetic latitude"):
        forward(95.0, -84.0, constants)


def test_inverse_refuses_a_northing_beyond_the_cone_apex():
    """Past the apex there is no geodetic position to return.

    The refusal names the likely cause - transposed northing and easting, or the
    wrong zone or unit - because those are what actually produce such a value.
    """
    constants = constants_for(MI_SOUTH)
    beyond_apex = constants.R_grid_origin + constants.northing_grid_origin + 1.0
    with pytest.raises(ValueError, match="apex of the projection cone"):
        inverse(beyond_apex, 4000000.0, constants)


def test_geodetic_and_grid_results_are_frozen():
    """Core result records are immutable (docs/DESIGN.md section 7)."""
    constants = constants_for(MI_SOUTH)
    point = forward(43.0, -84.0, constants)
    with pytest.raises(Exception):
        point.northing = 0.0  # type: ignore[misc]

    position = inverse(point.northing, point.easting, constants)
    with pytest.raises(Exception):
        position.latitude = 0.0  # type: ignore[misc]
