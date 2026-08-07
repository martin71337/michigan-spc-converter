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

from michspc.spc.lambert import (
    ApexLatitudeError,
    ConvergenceError,
    constants_for,
    forward,
    inverse,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS, US_SURVEY_FEET
from michspc.spc.zones import ALL_ZONES, MI_CENTRAL, MI_NORTH, MI_SOUTH, zone_by_code
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


# The closing review gate's apex-proximity counterexamples, per zone. Each
# triple is (zone, northing just inside the refused band, northing far enough
# below it to still convert), in INTERNATIONAL FEET on the central meridian -
# the units and the position the reviewer used. Michigan South's figures are the
# reviewer's own; the other two zones' were measured the same way, by walking
# down from the apex.
#
# The band exists because R' survives the `R_prime <= 0` apex guard by a few
# metres while the isometric latitude it implies is large enough that the
# manual's seed, (exp(2Q) - 1)/(exp(2Q) + 1), evaluates to exactly 1.0 - at
# which point Ellipsoid.isometric_latitude evaluated log((1 + 1)/(1 - 1)) and
# the core raised a bare ZeroDivisionError instead of refusing.
#
# The band's lower edge is ragged over a few metres, because at exp(2Q) ~ 1e16
# the +-1 in that expression is below the ulp of 2 there and the quotient snaps.
# Every refused value below was therefore verified individually rather than read
# off a threshold, and each converting value sits clear of the raggedness.
APEX_PROXIMITY_CASES = [
    # Apex at 23,068,134.156 ift. The reviewer's own two ZeroDivisionError
    # northings, and his probe at 23,067,900 ift that reported 89.999998.
    (MI_SOUTH, 23068134.1235, 23067900.0),
    (MI_SOUTH, 23068130.8433, 23067900.0),
    # Apex at 20,588,070.352 ift; the reviewer's measured window opens at
    # 20,588,016.882 ift, which is inside the refusal.
    (MI_NORTH, 20588016.882, 20587900.0),
    # Apex at 21,593,373.465 ift. The reviewer's quoted window opens at
    # 21,593,283.632 ift, but that particular northing lands on the ragged edge
    # and still converts, so the refused case is taken further in.
    (MI_CENTRAL, 21593330.0, 21593200.0),
]


@pytest.mark.parametrize(
    "zone, refused_ift, converts_ift",
    APEX_PROXIMITY_CASES,
    ids=[f"{z.abbrev}-{n:.0f}" for z, n, _ in APEX_PROXIMITY_CASES],
)
def test_inverse_refuses_the_band_just_below_the_cone_apex(
    zone, refused_ift, converts_ift
):
    """A bare ZeroDivisionError is not a refusal (closing review gate).

    The message must name the northing the surveyor typed, as the adjacent apex
    refusal does - the solver that detects the condition sees only Q, so a
    refusal naming Q alone would leave the reader nothing to check.
    """
    constants = constants_for(zone)
    easting = constants.easting_origin  # on the central meridian, E' = 0

    with pytest.raises(ApexLatitudeError) as caught:
        inverse(refused_ift * 0.3048, easting, constants)

    message = str(caught.value)
    # 0.3048 m per international foot exactly (michspc.spc.units); the message
    # prints the metres it was handed, so that is what must appear in it.
    assert repr(refused_ift * 0.3048) in message
    assert "apex of the projection cone" in message

    # And ApexLatitudeError must remain catchable as the ValueError the rest of
    # the program already handles for an unconvertible coordinate.
    assert isinstance(caught.value, ValueError)


@pytest.mark.parametrize(
    "zone, converts_ift",
    [(z, n) for z, _, n in APEX_PROXIMITY_CASES],
    ids=[f"{z.abbrev}-{n:.0f}" for z, _, n in APEX_PROXIMITY_CASES],
)
def test_inverse_still_converts_below_the_refused_band(zone, converts_ift):
    """The guard must not swallow northings that still have a latitude.

    The threshold is the representability of sin(phi), not a chosen margin, so
    everything below the band converts exactly as it did before. The reviewer's
    Michigan South probe at 23,067,900 ift is the case that pins this: it
    reported latitude 89.999998 before the fix and must still report it.
    """
    constants = constants_for(zone)
    position = inverse(converts_ift * 0.3048, constants.easting_origin, constants)

    # These northings sit a few tens of metres below a cone apex, so the only
    # honest expectation is "a latitude just short of 90 degrees, and not 90".
    assert 89.99 < position.latitude < 90.0


def test_inverse_still_refuses_at_and_beyond_the_apex_itself():
    """The reviewer's third Michigan South northing, above the apex.

    23,068,137.4037 ift x 0.3048 = 7,031,168.2806 m, against an apex at
    7,031,167.2907 m (R_b + N_b, MI South) - so R' is -0.99 m and the older,
    outer refusal is the one that must fire, unchanged by this fix.
    """
    constants = constants_for(MI_SOUTH)
    with pytest.raises(ValueError, match="at or beyond the apex"):
        inverse(23068137.4037 * 0.3048, constants.easting_origin, constants)


# --------------------------------------------------------------------------
# Interim gate finding #2 - the 0-360 east longitude counterexample.
#
# docs/DESIGN.md amendment #11 records this finding as "Fixed", and
# lambert.py's own docstring names the value. **No test in the suite contained
# 275.4445 until this one**, so the fix was never pinned: the closing gate
# seeded the pre-fix behaviour and 260 tests stayed green. That is what these
# tests close (WP-R4 task 1a).
# --------------------------------------------------------------------------


def test_forward_refuses_the_0_to_360_east_form_of_a_michigan_longitude():
    """275.4445 is 84.5555 W written in the 0-360 east convention.

    Hand-derived: -84.5555 + 360 = 275.4445 exactly. That is the state capitol
    reference position this program is anchored on (docs/DESIGN.md amendment
    #19), an entirely ordinary-looking float, and it must never convert.

    **What the unguarded call actually produces**, measured by removing the
    check and re-running - the reviewer's own figures, reproduced here:

        forward(42.7325, 275.4445) -> N  9,959,847.443079 m
                                      E -2,241,291.291873 m

    against the correct 136,920.027587 / 3,984,537.119006 m. That is
    11,629.74 km of horizontal error, delivered with no exception and nothing
    in the record to reveal it, because the convergence angle and grid scale
    factor come out perfectly self-consistent for the wrong meridian. It is
    the reason this refusal exists and the reason it is pinned.
    """
    constants = constants_for(MI_SOUTH)

    with pytest.raises(ValueError) as caught:
        forward(42.7325, 275.4445, constants)

    message = str(caught.value)
    # The refusal must name the offending value, per docs/DESIGN.md section 1.
    assert "275.4445" in message
    # And teach the fix: 275.4445 - 360 = -84.5555, printed to 6 places.
    assert "-84.555500" in message
    assert "0-360 east convention" in message


def test_the_longitude_domain_boundary_is_inclusive_at_exactly_plus_minus_180():
    """The implemented bound is ``-180.0 <= longitude <= 180.0``.

    Pinned because it is the edge the 0-360 refusal is measured from, and
    because an off-by-one-ulp change here is invisible in ordinary Michigan
    work: every real longitude this program sees is near -84.

    Exactly +-180 is the antimeridian, a real longitude, so it converts - the
    resulting Michigan coordinate is meaningless but that is the zone-extent
    warning's business, not this guard's. One ulp beyond is refused. The two
    probes are ``math.nextafter(180.0, 181.0)`` = 180.00000000000003 and its
    mirror, which is the smallest step a double can take past the bound.
    """
    constants = constants_for(MI_SOUTH)

    # Accepted, and returning a real number rather than an exception.
    for longitude in (-180.0, 180.0):
        point = forward(42.7325, longitude, constants)
        assert math.isfinite(point.northing)
        assert math.isfinite(point.easting)

    for longitude in (
        math.nextafter(180.0, 181.0),
        math.nextafter(-180.0, -181.0),
    ):
        with pytest.raises(ValueError, match="outside the range -180 to 180"):
            forward(42.7325, longitude, constants)


def test_the_latitude_guard_is_symmetric_and_excludes_both_poles():
    """The implemented bound is ``-90.0 < latitude < 90.0`` - strict, both ends.

    The existing refusal test covers +95 only. A sign error in the guard, or a
    ``<=`` at one end, would leave a pole convertible; at sin(phi) = +-1 the
    isometric latitude divides by zero. Both poles and both far-out values are
    checked so neither end can drift alone.
    """
    constants = constants_for(MI_SOUTH)

    for latitude in (90.0, -90.0, 95.0, -95.0, 180.0):
        with pytest.raises(ValueError, match="not a valid geodetic latitude"):
            forward(latitude, -84.5555, constants)
        # The refusal names the offending value.
        with pytest.raises(ValueError, match=str(latitude)):
            forward(latitude, -84.5555, constants)


# --------------------------------------------------------------------------
# Interim gate finding #3 - non-finite inputs.
#
# ``_require_valid_geodetic`` and ``_require_finite_grid`` were added by that
# finding's fix and recorded as "Fixed" in docs/DESIGN.md amendment #11. As
# with finding #2, no core-level test pinned either guard: the closing gate
# removed them and the suite stayed green, with ``forward`` returning a
# GridPoint carrying four NaNs (WP-R4 task 1b).
#
# What the unguarded calls actually produce, measured by removing each guard
# in turn:
#
#   forward(nan, nan)   GridPoint(northing=nan, easting=nan, convergence=nan,
#                                 scale_factor=nan)          - four NaNs
#   forward(nan, -84.5555)
#                       GridPoint(northing=nan, easting=nan,
#                                 convergence=-0.12850660858001875,
#                                 scale_factor=nan)  - a *plausible* angle
#                                 beside two NaN coordinates
#   forward(inf, ...)   bare ValueError("expected a finite input, got inf")
#                       out of the math module, naming nothing
#   inverse(nan, ...)   ApexLatitudeError about the cone apex - a confident
#                       and wrong diagnosis of a value that is not a number
#   inverse(1.4e5, inf) bare ValueError("expected a positive input, got 0.0")
#
# A NaN that reaches a GridPoint reaches the audit CSV beside real values.
# --------------------------------------------------------------------------

NON_FINITE = (float("nan"), float("inf"), float("-inf"))
NON_FINITE_IDS = ["nan", "inf", "-inf"]


@pytest.mark.parametrize("bad", NON_FINITE, ids=NON_FINITE_IDS)
def test_forward_refuses_a_non_finite_latitude(bad):
    """The refusal must name the value, not merely fail somewhere downstream."""
    constants = constants_for(MI_SOUTH)

    with pytest.raises(ValueError) as caught:
        forward(bad, -84.5555, constants)

    message = str(caught.value)
    assert repr(bad) in message
    assert "must both be finite numbers" in message


@pytest.mark.parametrize("bad", NON_FINITE, ids=NON_FINITE_IDS)
def test_forward_refuses_a_non_finite_longitude(bad):
    constants = constants_for(MI_SOUTH)

    with pytest.raises(ValueError) as caught:
        forward(42.7325, bad, constants)

    message = str(caught.value)
    assert repr(bad) in message
    assert "must both be finite numbers" in message


@pytest.mark.parametrize("bad", NON_FINITE, ids=NON_FINITE_IDS)
def test_inverse_refuses_a_non_finite_northing(bad):
    """Michigan South's false easting, with a northing that is not a number."""
    constants = constants_for(MI_SOUTH)

    with pytest.raises(ValueError) as caught:
        inverse(bad, 4000000.0, constants)

    message = str(caught.value)
    assert repr(bad) in message
    assert "must both be finite numbers" in message
    # Specifically NOT the apex refusal, which is what the unguarded code said.
    assert "apex" not in message


@pytest.mark.parametrize("bad", NON_FINITE, ids=NON_FINITE_IDS)
def test_inverse_refuses_a_non_finite_easting(bad):
    """136,920.027587 m north - the anchor position of docs/DESIGN.md #19."""
    constants = constants_for(MI_SOUTH)

    with pytest.raises(ValueError) as caught:
        inverse(136920.027586723, bad, constants)

    message = str(caught.value)
    assert repr(bad) in message
    assert "must both be finite numbers" in message
    assert "apex" not in message


@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_no_non_finite_value_can_reach_a_result_record(zone):
    """The property the two guards exist to hold, stated once per zone.

    Every combination of a non-finite latitude and longitude, and of a
    non-finite northing and easting, must raise - never return a record. A
    GridPoint or GeodeticPoint carrying a NaN is neither an exception nor a
    number: it propagates into the elevation and combined factors and lands in
    the audit file beside real values.
    """
    constants = constants_for(zone)
    finite_lat, finite_lon = 43.0, zone.definition.lon_origin
    finite_n = zone.definition.northing_grid_origin + 200000.0
    finite_e = zone.definition.easting_origin

    for bad in NON_FINITE:
        for latitude, longitude in (
            (bad, finite_lon),
            (finite_lat, bad),
            (bad, bad),
        ):
            with pytest.raises(ValueError):
                forward(latitude, longitude, constants)
        for northing, easting in ((bad, finite_e), (finite_n, bad), (bad, bad)):
            with pytest.raises(ValueError):
                inverse(northing, easting, constants)


def test_geodetic_and_grid_results_are_frozen():
    """Core result records are immutable (docs/DESIGN.md section 7)."""
    constants = constants_for(MI_SOUTH)
    point = forward(43.0, -84.0, constants)
    with pytest.raises(Exception):
        point.northing = 0.0  # type: ignore[misc]

    position = inverse(point.northing, point.easting, constants)
    with pytest.raises(Exception):
        position.latitude = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# The forward path's pole-proximity refusal.
#
# Found by the WP-R4 verification package, after the closing gate's apex
# finding had been fixed on the INVERSE path only. _require_valid_geodetic
# admits any latitude strictly inside (-90, 90), but sin() rounds to exactly
# +-1.0 over the last stretch below each pole and Ellipsoid.isometric_latitude
# then evaluates log((1 + 1) / (1 - 1)).
#
# Measured before the guard existed, MI South constants, longitude -84.5555:
#     89.99999939629086  ->  N 7031131.631 m          (converts, still does)
#     89.99999939629087  ->  ZeroDivisionError: division by zero
#    -89.9999999         ->  ValueError: expected a positive input, got 0.0
#                            (out of math.log, naming nothing)
# The band is about 6.04e-7 degrees, roughly 67 mm of latitude, at each pole.
# No Michigan survey reaches it; the rule it violated - no bare arithmetic
# error escapes the core, and a refusal names the offending item - has no
# latitude qualifier.
# ---------------------------------------------------------------------------

_POLE_PROXIMITY_LATITUDES = [
    89.99999939629087,
    89.9999999,
    -89.99999939629087,
    -89.9999999,
]


@pytest.mark.parametrize("latitude", _POLE_PROXIMITY_LATITUDES)
def test_forward_refuses_a_latitude_whose_sine_has_rounded_onto_a_pole(latitude):
    """A bare ZeroDivisionError must never escape forward()."""
    constants = constants_for(MI_SOUTH)

    with pytest.raises(ApexLatitudeError) as caught:
        forward(latitude, -84.5555, constants)

    message = str(caught.value)
    # The refusal names the number that was in the file, not its sine.
    assert repr(latitude) in message
    assert "pole" in message
    # Catchable as the ValueError every other refusal in this module is.
    assert isinstance(caught.value, ValueError)


def test_forward_still_converts_the_largest_latitude_whose_sine_is_representable():
    """The guard refuses only what the arithmetic cannot represent.

    Hand-derived by binary search against the arithmetic itself: the largest
    latitude whose sine is strictly below 1.0 in binary64 is
    89.99999939629086, and it converted before the guard and must still.
    """
    constants = constants_for(MI_SOUTH)

    point = forward(89.99999939629086, -84.5555, constants)

    # Hand-derived: unchanged by the guard - this is the value the unguarded
    # code produced, recorded when the band was measured.
    assert point.northing == pytest.approx(7031131.631, abs=0.001)


def test_the_pole_guard_leaves_an_ordinary_michigan_point_untouched():
    """Lansing, the program's standing worked example, is unaffected.

    Hand-derived from the Appendix A defining constants through section 3.12
    and 3.13; the same figures the WP-R1 package re-derived at 50 digits.
    """
    point = forward(42.7325, -84.5555, constants_for(MI_SOUTH))

    assert point.northing == pytest.approx(136920.027587, abs=1e-6)
    assert point.easting == pytest.approx(3984537.119006, abs=1e-6)
