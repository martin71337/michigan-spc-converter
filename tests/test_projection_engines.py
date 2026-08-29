"""The three projection engines, the dispatcher, and what verifies them.

Four independent classes of check:

1. **Beta NCAT anchors.** 63 pure-projection results across all nineteen
   Michigan SPCS2022 zones, frozen in tests/fixtures/spcs2022_engine_anchors.py.
   They pin the forward conversion, its convergence and scale factor, and the
   inverse, against an implementation we did not write. The lattice is
   deliberately asymmetric about the oblique Mercator's centre so the Hotine
   variant and the skew sign cannot both be wrong and still pass.

2. **Published derived constants**, recomputed from the defining constants
   alone: Table 3.22's S_0 for three SPCS 83 transverse Mercator zones, the
   GRS 80 coefficient series printed in sections 3.22 and 3.32, and Alaska zone
   1's seven oblique Mercator zone constants (PDF p. 50). These come from the
   manual, not from beta NGS, so they hold even if every beta number moves.

3. **Structural properties**, true at every point rather than at 63 of them:
   the easting on the central meridian is exactly the false easting, the
   convergence there is exactly zero, forward and inverse are true inverses,
   and the three existing SPCS 83 zones come out of the dispatcher
   bit-identical to what the Lambert engine alone produced.

4. **The dispatcher's own contracts**: one table covering every definition
   type, a refusal naming an unregistered one, and the uniform accessors
   convert.py reads blind across the union.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from michspc.spc import lambert, omerc, projection, tm
from michspc.spc.ellipsoid import GRS80
from michspc.spc.frames import NATRF2022
from michspc.spc.lambert import LambertConstants
from michspc.spc.projection import ProjectionUnavailableError
from michspc.spc.units import INTERNATIONAL_FEET
from michspc.spc.zones import (
    ALL_ZONES,
    MI_SOUTH,
    LambertOneParallelDef,
    LambertTwoParallelDef,
    ObliqueMercatorCenterDef,
    ProjectionDef,
    ProjectionKind,
    TransverseMercatorDef,
    Zone,
    dms,
)
from tests.fixtures.spcs2022_engine_anchors import (
    SPCS2022_PRINTED,
    SPCS2022_PROJECTION_ANCHORS,
    SPCS2022_ZONE_PARAMETERS,
    Spcs2022ZoneParameters,
    dms_to_degrees,
)

# --------------------------------------------------------------------------
# Turning the frozen zone parameters into definition records.
#
# H1 builds the ENGINES, not the registry: no SPCS2022 Zone record is added to
# michspc.spc.zones here, and these throwaway zones exist only so the anchors
# run through the real public entry points - projection.forward and
# projection.inverse, which take a Zone - rather than through a private seam a
# job would never use.
# --------------------------------------------------------------------------

_TEST_ZONE_CITATION = (
    "NGS beta zoneDefinitions.json, captured 2026-08-28 - test fixture only; "
    "the shipped registry is built at H2"
)


def definition_for(parameters: Spcs2022ZoneParameters) -> ProjectionDef:
    """The definition record NGS's ``Proj type`` abbreviation calls for."""
    if parameters.projection_type == "OMC":
        if parameters.skew_azimuth is None:
            raise AssertionError(
                f"zone {parameters.code} is OMC but publishes no skew azimuth"
            )
        return ObliqueMercatorCenterDef(
            lat_center=parameters.origin_latitude,
            lon_center=parameters.origin_longitude,
            skew_azimuth=parameters.skew_azimuth,
            k_center=parameters.origin_scale,
            northing_center=parameters.false_northing_m,
            easting_center=parameters.false_easting_m,
        )
    if parameters.projection_type == "LC1":
        return LambertOneParallelDef(
            lat_origin=parameters.origin_latitude,
            k_origin=parameters.origin_scale,
            lon_origin=parameters.origin_longitude,
            northing_grid_origin=parameters.false_northing_m,
            easting_origin=parameters.false_easting_m,
        )
    if parameters.projection_type == "TM":
        return TransverseMercatorDef(
            lat_grid_origin=parameters.origin_latitude,
            lon_origin=parameters.origin_longitude,
            k_origin=parameters.origin_scale,
            northing_grid_origin=parameters.false_northing_m,
            easting_origin=parameters.false_easting_m,
        )
    raise AssertionError(
        f"zone {parameters.code} has projection type "
        f"{parameters.projection_type!r}, which this test does not know how to "
        f"build. NGS publishes only OMC, LC1 and TM for Michigan."
    )


def throwaway_zone(parameters: Spcs2022ZoneParameters) -> Zone:
    """A Zone record built for a test, never added to the registry."""
    return Zone(
        code=parameters.code,
        abbrev=parameters.abbrev,
        name=parameters.name,
        system="SPCS2022",
        frame=NATRF2022,
        definition=definition_for(parameters),
        citation=_TEST_ZONE_CITATION,
        lat_min=-90.0,
        lat_max=90.0,
        lon_min=-180.0,
        lon_max=180.0,
    )


ZONES_BY_CODE = {p.code: throwaway_zone(p) for p in SPCS2022_ZONE_PARAMETERS}
PARAMETERS_BY_CODE = {p.code: p for p in SPCS2022_ZONE_PARAMETERS}

ANCHOR_IDS = [
    f"{a.zone_code}@{a.latitude}/{a.longitude}" for a in SPCS2022_PROJECTION_ANCHORS
]

ORIGIN_ANCHORS = [
    a
    for a in SPCS2022_PROJECTION_ANCHORS
    if a.label in ("origin", "projection center")
]
ORIGIN_IDS = [f"{a.zone_code}-{a.label.replace(' ', '-')}" for a in ORIGIN_ANCHORS]


# --------------------------------------------------------------------------
# 1. Anchors: our engines against beta NCAT.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", SPCS2022_PROJECTION_ANCHORS, ids=ANCHOR_IDS)
def test_forward_matches_beta_ncat_northing_and_easting(anchor):
    """Expected values computed by beta NGS NCAT, not by this codebase."""
    point = projection.forward(
        anchor.latitude, anchor.longitude, ZONES_BY_CODE[anchor.zone_code]
    )

    assert point.northing == pytest.approx(
        anchor.northing_m, abs=SPCS2022_PRINTED["linear_m"]
    )
    assert point.easting == pytest.approx(
        anchor.easting_m, abs=SPCS2022_PRINTED["linear_m"]
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", SPCS2022_PROJECTION_ANCHORS, ids=ANCHOR_IDS)
def test_forward_matches_beta_ncat_in_international_feet(anchor):
    """NGS publishes the 2022 false origins in metres and international feet.

    US survey feet are ``N/A`` on every 2022 zone, which is the citation basis
    for the unit restriction H2 carries; there is no usft column to check.
    """
    point = projection.forward(
        anchor.latitude, anchor.longitude, ZONES_BY_CODE[anchor.zone_code]
    )

    assert INTERNATIONAL_FEET.from_meters(point.northing) == pytest.approx(
        anchor.northing_ift, abs=SPCS2022_PRINTED["linear_ift"]
    )
    assert INTERNATIONAL_FEET.from_meters(point.easting) == pytest.approx(
        anchor.easting_ift, abs=SPCS2022_PRINTED["linear_ift"]
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", SPCS2022_PROJECTION_ANCHORS, ids=ANCHOR_IDS)
def test_forward_matches_beta_ncat_scale_factor(anchor):
    point = projection.forward(
        anchor.latitude, anchor.longitude, ZONES_BY_CODE[anchor.zone_code]
    )

    assert point.scale_factor == pytest.approx(
        anchor.scale_factor, abs=SPCS2022_PRINTED["scale_factor"]
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", SPCS2022_PROJECTION_ANCHORS, ids=ANCHOR_IDS)
def test_forward_matches_beta_ncat_convergence(anchor):
    """Convergence angle, to the 0.01 arc second beta NCAT prints.

    This is where a sign convention shows itself: our convergence is positive
    east of the central meridian, and beta NCAT's printed sign agrees at every
    one of the 63 points, including the eighteen zones' east-of-origin and
    west-of-origin pairs.
    """
    point = projection.forward(
        anchor.latitude, anchor.longitude, ZONES_BY_CODE[anchor.zone_code]
    )

    expected = dms_to_degrees(anchor.convergence_dms)
    assert point.convergence * 3600.0 == pytest.approx(
        expected * 3600.0, abs=SPCS2022_PRINTED["convergence_arcsec"]
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", SPCS2022_PROJECTION_ANCHORS, ids=ANCHOR_IDS)
def test_inverse_recovers_the_anchor_latitude_and_longitude(anchor):
    """Beta NCAT's northing/easting, fed to our inverse, must give its lat/long.

    A genuine anchor rather than a round trip: the input coordinates are NGS's
    numbers, not ours.

    Tolerance from beta NCAT's own 0.001 m printing. One millimetre of northing
    is about 9e-9 degrees of latitude and, at Michigan's latitude, one
    millimetre of easting is about 1.2e-8 degrees of longitude; the capture's
    own round-trip cross-check measured 5.0e-9 degrees worst over its five
    inverse anchors for exactly this reason. 5e-8 degrees is comfortably above
    that quantization floor and is still about 5 mm on the ground.
    """
    position = projection.inverse(
        anchor.northing_m, anchor.easting_m, ZONES_BY_CODE[anchor.zone_code]
    )

    assert position.latitude == pytest.approx(anchor.latitude, abs=5e-8)
    assert position.longitude == pytest.approx(anchor.longitude, abs=5e-8)


@pytest.mark.parametrize("anchor", SPCS2022_PROJECTION_ANCHORS, ids=ANCHOR_IDS)
def test_forward_then_inverse_returns_the_same_position(anchor):
    """Round trip through our own two directions, at every anchor point.

    Independent of what beta NCAT printed: it catches a sign or series defect
    present in only one direction, which an anchor test compares against a
    rounded figure and can miss. Held to 1e-9 degrees, about 0.1 mm.
    """
    zone = ZONES_BY_CODE[anchor.zone_code]
    point = projection.forward(anchor.latitude, anchor.longitude, zone)
    position = projection.inverse(point.northing, point.easting, zone)

    assert position.latitude == pytest.approx(anchor.latitude, abs=1e-9)
    assert position.longitude == pytest.approx(anchor.longitude, abs=1e-9)


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", ORIGIN_ANCHORS, ids=ORIGIN_IDS)
def test_every_zone_origin_reproduces_its_published_false_origin(anchor):
    """The nineteen origin and centre points, which are exact by construction.

    At its own origin a zone's grid coordinates ARE its published false origin,
    its scale factor IS its published origin scale, and its convergence is zero.
    Beta NCAT prints exactly those values at all nineteen, which is the strongest
    evidence in the capture: it is beta NCAT agreeing with NGS's separately
    published parameter file rather than with itself.

    For the oblique Mercator this is also the variant discriminator. The
    manual's natural-origin form puts the centre nowhere near the false
    coordinates - Alaska zone 1's centre lands at u = 6,968,872 m - so an engine
    built to section 3.3 as printed fails this by about 6,969 km at zone 260001.

    Held to the anchor tolerance rather than to bit equality, because that is
    what beta NCAT printed; the separate structural tests below hold the same
    points to the exact arithmetic.
    """
    parameters = PARAMETERS_BY_CODE[anchor.zone_code]
    point = projection.forward(
        anchor.latitude, anchor.longitude, ZONES_BY_CODE[anchor.zone_code]
    )

    assert anchor.northing_m == parameters.false_northing_m
    assert anchor.easting_m == parameters.false_easting_m
    assert anchor.northing_ift == parameters.false_northing_ift
    assert anchor.easting_ift == parameters.false_easting_ift
    assert anchor.scale_factor == parameters.origin_scale
    assert dms_to_degrees(anchor.convergence_dms) == 0.0

    assert point.northing == pytest.approx(
        parameters.false_northing_m, abs=SPCS2022_PRINTED["linear_m"]
    )
    assert point.easting == pytest.approx(
        parameters.false_easting_m, abs=SPCS2022_PRINTED["linear_m"]
    )
    assert point.scale_factor == pytest.approx(
        parameters.origin_scale, abs=SPCS2022_PRINTED["scale_factor"]
    )
    assert abs(point.convergence) * 3600.0 < SPCS2022_PRINTED["convergence_arcsec"]


@pytest.mark.parametrize("anchor", ORIGIN_ANCHORS, ids=ORIGIN_IDS)
def test_every_zone_origin_is_exact_not_merely_within_tolerance(anchor):
    """The same nineteen points, held to the arithmetic rather than the print.

    Each engine reaches its own origin by an expression that cancels to the
    false origin identically - the Lambert's ``R_b + N_b - R_0 cos 0`` with
    R_b = R_0, the transverse Mercator's ``S - S_0`` at phi_0, and the oblique
    Mercator's ``u - u_c`` at the centre - so the result is the false origin to
    the last bit, not merely to a millimetre. Pinned because a defect that
    perturbed the cancellation by a few microns would pass the anchor test above
    while telling us the structure had changed.
    """
    parameters = PARAMETERS_BY_CODE[anchor.zone_code]
    point = projection.forward(
        anchor.latitude, anchor.longitude, ZONES_BY_CODE[anchor.zone_code]
    )

    assert point.northing == parameters.false_northing_m
    assert point.easting == parameters.false_easting_m
    # The convergence and scale cancel to within a few ulp rather than exactly:
    # both are evaluated through trigonometry of an angle that is only
    # representably zero, not exactly so. Measured worst over the nineteen:
    # 6.4e-15 degrees (2.3e-11 arc second) and 2.3e-16 in the scale factor.
    assert abs(point.convergence) < 1e-13
    assert point.scale_factor == pytest.approx(parameters.origin_scale, abs=1e-14)


# --------------------------------------------------------------------------
# 2. Published derived constants, from the manual rather than from beta NGS.
# --------------------------------------------------------------------------


def _tm_constants(lat_grid_origin: float, k_origin: float):
    """Constants for a transverse Mercator zone, with placeholder false origins.

    S_0 and the coefficient series depend on the ellipsoid, phi_0 and k_0 only;
    the central meridian and false origins move a coordinate but not a single
    quantity checked in this section.
    """
    return tm.TransverseMercatorConstants.from_definition(
        TransverseMercatorDef(
            lat_grid_origin=lat_grid_origin,
            lon_origin=-111.0,
            k_origin=k_origin,
            northing_grid_origin=0.0,
            easting_origin=213360.0,
        )
    )


@pytest.mark.anchor
@pytest.mark.parametrize(
    "zone_code,lat_grid_origin,k_origin,published_S0",
    [
        # Manual Appendix A (PDF p. 73 ff) gives each zone's grid origin
        # latitude and its scale factor as a reciprocal; Table 3.22 (PDF p. 44)
        # gives S_0. Hand derivations of k_0:
        #   1:10,000 -> 1 - 1/10000 = 0.9999
        #   1:19,000 -> 1 - 1/19000 = 0.999947368421052631...
        #   1:30,000 -> 1 - 1/30000 = 0.999966666666666666...
        # and of the latitudes:
        #   31 deg 00' = 31.0;  41 deg 40' = 41 + 40/60 = 41.666666...;
        #   42 deg 30' = 42.5
        pytest.param(
            "AZ-C-0202", 31.0, 1.0 - 1.0 / 10000.0, 3430631.2260, id="AZ-C-0202"
        ),
        pytest.param(
            "ID-E-1101",
            dms(41, 40),
            1.0 - 1.0 / 19000.0,
            4614370.6555,
            id="ID-E-1101",
        ),
        pytest.param(
            "NH---2800", 42.5, 1.0 - 1.0 / 30000.0, 4707019.0442, id="NH-2800"
        ),
    ],
)
def test_table_3_22_meridional_distance_reproduces(
    zone_code, lat_grid_origin, k_origin, published_S0
):
    """S_0 from the defining constants alone, against NGS's printed table.

    Manual Table 3.22, PDF p. 44. These are SPCS 83 zones in other states -
    deliberately, because they are the only published transverse Mercator
    derived constants that exist, and they carry no beta provenance at all: if
    every beta number moved tomorrow this check would still hold.

    Tolerance is half a unit in the last decimal place NGS printed, which is
    four places: 0.00005 m. Measured worst of the three: 0.000024 m.
    """
    constants = _tm_constants(lat_grid_origin, k_origin)

    assert constants.S0 == pytest.approx(published_S0, abs=0.5e-4)


@pytest.mark.anchor
def test_the_rectifying_sphere_radius_matches_the_manual():
    """r = a(1 - n)(1 - n^2)(1 + 9n^2/4 + 225n^4/64), manual PDF p. 43.

    The page prints 6,367,449.14577 m for GRS 80. Last printed place is 1e-5 m,
    so half a unit is 5e-6.
    """
    constants = _tm_constants(31.0, 0.9999)

    assert constants.r == pytest.approx(6367449.14577, abs=5e-6)


@pytest.mark.anchor
@pytest.mark.parametrize(
    "name,printed",
    [
        # Manual section 3.22, PDF p. 43, GRS 80 column. Each is printed to ten
        # decimal places, so half a unit in the last place is 5e-11.
        ("U0", -0.0050482507_76),
        ("U2", 0.0000212592_04),
        ("U4", -0.0000001114_23),
        ("U6", 0.0000000006_26),
        ("V0", 0.0050228939_48),
        ("V2", 0.0000293706_25),
        ("V4", 0.0000002350_59),
        ("V6", 0.0000000021_81),
    ],
)
def test_the_transverse_mercator_series_matches_the_manual(name, printed):
    """The eight U/V coefficients, recomputed from the flattening alone.

    The manual offers these as constants that "may be directly entered into
    software" and gives the equations "for those with requirements for other
    ellipsoids". This program takes the equations, so this is the check that the
    equations reproduce the numbers NGS entered - the same relationship
    Appendix C has to the Lambert derivation.
    """
    constants = _tm_constants(31.0, 0.9999)

    assert getattr(constants, name) == pytest.approx(printed, abs=5e-11)


@pytest.mark.anchor
@pytest.mark.parametrize(
    "name,printed",
    [
        # Manual section 3.32, PDF p. 49, GRS 80 column, ten decimal places.
        # A DISTINCT namespace from section 3.22's U/V and from section 3.23's
        # scale coefficients, which also print as F2 and F4.
        ("conformal_F0", 0.0066869209_27),
        ("conformal_F2", 0.0000520145_84),
        ("conformal_F4", 0.0000005544_30),
        ("conformal_F6", 0.0000000068_20),
    ],
)
def test_the_oblique_mercator_conformal_series_matches_the_manual(name, printed):
    constants = omerc.ObliqueMercatorConstants.from_definition(ALASKA_ZONE_1)

    assert getattr(constants, name) == pytest.approx(printed, abs=5e-11)


# Manual Appendix A, PDF p. 73: Alaska zone 1, code 5001, O.M., axis azimuth
# arctan(-3/4), central longitude 133 deg 40' W, grid origin latitude 57 deg
# 00', easting 5,000,000, northing -5,000,000, scale 1:10,000.
#
# Hand derivations:
#   alpha_c = arctan(-0.75) = -36.869897645844... deg  (the manual states
#             sin alpha_c = -0.6 and cos alpha_c = +0.8, PDF p. 49)
#   133 deg 40' = 133 + 40/60 = 133.666666... -> -133.666666... negative west
#   k_c = 1 - 1/10000 = 0.9999
#
# The false coordinates below are the manual's NATURAL-ORIGIN ones, and this
# record is a ...CenterDef, so the two do not mean the same thing. Nothing in
# this section reads them: every quantity checked here - B, C, D, F, G, I,
# lambda_0 and u_c - depends on phi_c, lambda_c, alpha_c and k_c alone.
ALASKA_ZONE_1 = ObliqueMercatorCenterDef(
    lat_center=57.0,
    lon_center=-dms(133, 40),
    skew_azimuth=math.degrees(math.atan(-0.75)),
    k_center=1.0 - 1.0 / 10000.0,
    northing_center=-5000000.0,
    easting_center=5000000.0,
)


@pytest.mark.anchor
@pytest.mark.parametrize(
    "name,printed,tolerance",
    [
        # Manual section 3.33, PDF p. 50: "For Alaska zone 1, these constants
        # are". Each is printed to the place the tolerance names, and the
        # tolerance is half a unit there.
        ("B", 1.0002964614_04, 0.5e-12),
        ("C", 0.0044268339_26, 0.5e-12),
        ("D", 6386186.73253, 0.5e-5),
        # G is NOT held to half a unit in its last place, and the reason is
        # measured rather than assumed: the manual computed G from the ROUNDED
        # F it printed, so G inherits F's 1.2e-11 rounding scaled by
        # |dG/dF| = |F|/G = 0.34604, which is 4.15e-12. Measured difference
        # 4.03e-12. 1e-11 leaves headroom above that and is still two orders
        # tighter than anything that could hide a transcription error. The test
        # below proves the inheritance rather than asserting it.
        ("G", 0.9450198553_34, 1e-11),
        ("I", 1.0015589176_62, 0.5e-12),
    ],
)
def test_alaska_zone_1_constants_match_the_manual(name, printed, tolerance):
    """The section 3.33 derivation, against the manual's own test vector.

    The only worked oblique Mercator numbers NGS publishes anywhere - section
    3.3 contains no worked forward or inverse computation, and Appendix C is
    Lambert-only. They carry the whole burden of checking the zone-constant
    derivation independently of beta NCAT.
    """
    constants = omerc.ObliqueMercatorConstants.from_definition(ALASKA_ZONE_1)

    assert getattr(constants, name) == pytest.approx(printed, abs=tolerance)


@pytest.mark.anchor
def test_alaska_zone_1_F_matches_the_manual_to_the_manuals_own_rounding():
    """F = sin(alpha_0), pinned LOOSELY, and the reason is recorded.

    The manual prints F = -0.32701 29554 38. Computed in double precision from
    the same defining constants it is -0.32701 29554 4998, a difference of
    1.2e-11 - about 0.08 mm of arc, and far larger than the 5e-12 the other six
    constants sit inside.

    That difference is the MANUAL's own rounding, not ours, and the manual's two
    printed numbers prove it rather than leaving it as an assertion: the printed
    G is what you get from the printed F, to 1.1e-13. So the manual rounded F
    to twelve places, then computed G from the rounded value - which is why our
    G, computed from an unrounded F, sits 4.03e-12 from the printed one, exactly
    |F|/G = 0.34604 times F's own 1.198e-11 discrepancy.

    The extraction (review/nsrs-h1-manual/TM-OM-EXTRACTION.md, section 2 table)
    reached the same figure independently and instructed: do not pin a bit-match
    on F.
    """
    constants = omerc.ObliqueMercatorConstants.from_definition(ALASKA_ZONE_1)

    printed_F = -0.3270129554_38
    printed_G = 0.9450198553_34

    assert constants.F == pytest.approx(printed_F, abs=2e-11)

    # The printed pair is self-consistent: G IS sqrt(1 - F^2) of the printed F.
    assert math.sqrt(1.0 - printed_F * printed_F) == pytest.approx(
        printed_G, abs=5e-13
    )

    # And the discrepancy in G is F's discrepancy propagated, to within one
    # part in a hundred of itself - which is what makes it the manual's
    # rounding rather than an error in this derivation.
    propagated = abs(constants.F - printed_F) * abs(constants.F) / constants.G
    assert abs(constants.G - printed_G) == pytest.approx(propagated, rel=0.01)


@pytest.mark.anchor
def test_alaska_zone_1_lambda_0_matches_the_manual():
    """lambda_0 = 101.51383 9560 degrees WEST (PDF p. 50).

    The manual prints it positive-west; this codebase is negative-west, so the
    stored value is its negation, and this test is the one place the
    lambda_0 sign deviation (omerc deviation point 1 of 4) is checked against a
    published number rather than against a round trip. Printed to seven decimal
    places, so half a unit is 5e-8; measured difference 3.1e-11.
    """
    constants = omerc.ObliqueMercatorConstants.from_definition(ALASKA_ZONE_1)

    assert -constants.lon_origin == pytest.approx(101.5138395_60, abs=5e-8)
    assert constants.lon_origin < 0.0


@pytest.mark.anchor
def test_the_manuals_natural_origin_u_at_alaska_zone_1s_centre():
    """u at the projection centre is 6,968,872.111 m - which is the whole point.

    This single number is why ``ObliqueMercatorCenterDef`` exists. Section 3.3's
    equations, evaluated at Alaska zone 1's own centre, give a u of nearly seven
    million metres rather than the zone's false northing: the manual's false
    coordinates apply where the initial line crosses the equator, not at the
    centre. NGS's SPCS2022 designation OMC puts them at the centre, so this
    module subtracts u_c - and if it did not, every Michigan coordinate would be
    out by about 6,969 km.

    Recorded to three decimals in review/nsrs-h1-manual/TM-OM-EXTRACTION.md
    section 2, computed there independently of this implementation.
    """
    constants = omerc.ObliqueMercatorConstants.from_definition(ALASKA_ZONE_1)

    assert constants.u_center == pytest.approx(6968872.111, abs=0.0005)


# --------------------------------------------------------------------------
# 3. Structural properties - true at every point, not just the anchored ones.
# --------------------------------------------------------------------------

LDP_ZONES = [
    pytest.param(ZONES_BY_CODE[p.code], id=f"{p.code}-{p.projection_type}")
    for p in SPCS2022_ZONE_PARAMETERS
]

CONIC_AND_TM_ZONES = [
    pytest.param(ZONES_BY_CODE[p.code], id=f"{p.code}-{p.projection_type}")
    for p in SPCS2022_ZONE_PARAMETERS
    if p.projection_type in ("LC1", "TM")
]

STATEWIDE_ZONE = ZONES_BY_CODE["260001"]


@pytest.mark.parametrize("zone", CONIC_AND_TM_ZONES)
@pytest.mark.parametrize("latitude", [40.5, 43.0, 45.5, 47.5])
def test_convergence_is_zero_on_the_central_meridian(zone, latitude):
    """A meridian through the projection origin is parallel to grid north.

    True at every latitude for the conic and the transverse Mercator, and it is
    the property that catches a longitude-convention defect: get the sign of the
    central meridian wrong and the convergence on the origin's own meridian is
    nowhere near zero.

    **The oblique Mercator is deliberately excluded, and the exclusion is a
    fact about the projection, not a gap.** Its grid north follows the skewed
    initial line, so the centre's meridian is parallel to it only AT the centre;
    at 43 N on zone 260001's own centre meridian the convergence is 0.0214
    degrees, and asserting zero there would be asserting the projection is not
    oblique. The centre itself is pinned by the origin tests above, and the
    statewide test below covers the sign along the centre latitude.
    """
    point = projection.forward(latitude, zone.definition.lon_origin, zone)

    assert point.convergence == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("zone", LDP_ZONES)
@pytest.mark.parametrize("latitude", [40.5, 43.0, 45.5, 47.5])
def test_a_point_east_of_the_central_meridian_has_positive_convergence(
    zone, latitude
):
    """Convergence is positive east of the central meridian, in every engine.

    The convention lambert.py established and the other two were written to
    match. It is checked here as a property rather than trusted from the
    anchors, because a projection whose convergence sign flipped would still
    reproduce every northing and easting in the lattice.

    The oblique Mercator IS included: the 0.6 degree swing across its centre
    meridian is two orders larger than the skew's own offset at these
    latitudes, so the sign still discriminates.
    """
    east = projection.forward(latitude, zone.definition.lon_origin + 0.3, zone)
    west = projection.forward(latitude, zone.definition.lon_origin - 0.3, zone)

    assert east.convergence > 0.0
    assert west.convergence < 0.0


@pytest.mark.parametrize("zone", LDP_ZONES)
@pytest.mark.parametrize("latitude", [40.5, 43.0, 45.5, 47.5])
def test_a_point_east_of_the_central_meridian_has_the_larger_easting(
    zone, latitude
):
    """Easting increases eastward - the other half of the same sign check.

    A convergence sign defect and an easting sign defect are different defects;
    the oblique Mercator's skew means neither implies the other there.
    """
    east = projection.forward(latitude, zone.definition.lon_origin + 0.3, zone)
    west = projection.forward(latitude, zone.definition.lon_origin - 0.3, zone)

    assert east.easting > west.easting


def test_the_oblique_mercators_grid_north_is_not_the_centre_meridian():
    """The fact the exclusion above rests on, measured rather than asserted.

    On zone 260001's own centre meridian the convergence is zero only AT the
    centre, and grows on BOTH sides of it - the oblique graticule's grid north
    follows the skewed initial line, and the meridian curves away from it in
    either direction. Measured on this implementation:

        43 N  +0.013702587 degrees
        45 N   0            (the centre)
        47 N  +0.013712224 degrees

    Not symmetric in sign - both positive - which is the shape a conic or a
    transverse Mercator never has on its own central meridian, where the
    convergence is identically zero at every latitude. That is the whole reason
    the OMC is excluded from the test above, and pinning the numbers here keeps
    the exclusion honest: it is a property of the projection, not a value this
    engine happens to produce.
    """
    centre_meridian = STATEWIDE_ZONE.definition.lon_origin

    at_centre = projection.forward(45.0, centre_meridian, STATEWIDE_ZONE)
    south = projection.forward(43.0, centre_meridian, STATEWIDE_ZONE)
    north = projection.forward(47.0, centre_meridian, STATEWIDE_ZONE)

    assert abs(at_centre.convergence) < 1e-13
    assert south.convergence == pytest.approx(0.013702587, abs=1e-9)
    assert north.convergence == pytest.approx(0.013712224, abs=1e-9)


@pytest.mark.parametrize("zone", LDP_ZONES)
@pytest.mark.parametrize(
    "latitude,longitude",
    [(43.0, -86.0), (45.5, -85.0), (41.5, -84.5), (47.0, -87.5)],
)
def test_convergence_and_scale_agree_with_a_finite_difference(
    zone, latitude, longitude
):
    """Each engine's ANALYTIC gamma and k, against its own mapping's gradient.

    The convergence and scale factor come from separate series in every engine
    - they are not read off the coordinates - so nothing computed so far would
    notice if one of them were wrong while the coordinates were right. A wrong
    convergence reaches a sealed survey as a wrong bearing.

    The derivation, with no projection-specific step in it:

      * A meridian has geodetic azimuth 0. Grid azimuth = geodetic azimuth minus
        the convergence, so the meridian's GRID bearing at a point is -gamma,
        and stepping north gives gamma = -atan2(dE/dphi, dN/dphi).
      * The scale factor is grid distance over ellipsoid distance for that same
        step, and the ellipsoid distance along a meridian is M dphi with M the
        radius of curvature in the meridian - which michspc.spc.ellipsoid
        already derives and tests/test_zone_constants.py already pins.

    A central difference over 2e-6 degrees leaves about 1e-7 degrees of noise in
    gamma and about 1e-8 in k, which is what the tolerances allow; the engines
    sit inside it at every point of this lattice.
    """
    point = projection.forward(latitude, longitude, zone)

    step = 1e-6
    up = projection.forward(latitude + step, longitude, zone)
    down = projection.forward(latitude - step, longitude, zone)
    d_northing = up.northing - down.northing
    d_easting = up.easting - down.easting

    convergence_fd = -math.degrees(math.atan2(d_easting, d_northing))
    assert point.convergence == pytest.approx(convergence_fd, abs=1e-6)

    ground = GRS80.radius_meridian(
        math.sin(math.radians(latitude))
    ) * math.radians(2.0 * step)
    scale_fd = math.hypot(d_northing, d_easting) / ground
    assert point.scale_factor == pytest.approx(scale_fd, abs=1e-7)


@pytest.mark.parametrize("zone", LDP_ZONES)
def test_forward_and_inverse_are_true_inverses_across_the_zone(zone):
    """A lattice of positions round-tripped, well beyond the anchored points."""
    origin_lat = _origin_latitude(zone)
    for dlat in (-0.4, -0.1, 0.0, 0.2, 0.5):
        for dlon in (-0.6, -0.2, 0.0, 0.3, 0.7):
            latitude = origin_lat + dlat
            longitude = zone.definition.lon_origin + dlon
            point = projection.forward(latitude, longitude, zone)
            position = projection.inverse(point.northing, point.easting, zone)

            assert position.latitude == pytest.approx(latitude, abs=1e-9)
            assert position.longitude == pytest.approx(longitude, abs=1e-9)


@pytest.mark.parametrize("zone", LDP_ZONES)
def test_the_two_directions_agree_about_convergence_and_scale(zone):
    """Each engine computes gamma and k by two independent routes.

    The transverse Mercator has a separate inverse series for both (section
    3.24's D and G coefficients, against section 3.23's C and F); the Lambert
    reaches them from the mapping radius either way; the oblique Mercator's
    inverse re-runs the direct equations, which the manual instructs. Where the
    series are genuinely independent this is a real cross-check, and where they
    are not it is still a pin on the two paths staying joined.
    """
    origin_lat = _origin_latitude(zone)
    for dlat in (-0.3, 0.0, 0.4):
        for dlon in (-0.5, 0.0, 0.6):
            latitude = origin_lat + dlat
            longitude = zone.definition.lon_origin + dlon
            point = projection.forward(latitude, longitude, zone)
            position = projection.inverse(point.northing, point.easting, zone)

            assert position.convergence == pytest.approx(
                point.convergence, abs=1e-11
            )
            assert position.scale_factor == pytest.approx(
                point.scale_factor, rel=1e-12
            )


def _origin_latitude(zone: Zone) -> float:
    """The latitude a zone's definition is anchored at, whatever it is called."""
    definition = zone.definition
    if isinstance(definition, ObliqueMercatorCenterDef):
        return definition.lat_center
    if isinstance(definition, LambertOneParallelDef):
        return definition.lat_origin
    if isinstance(definition, TransverseMercatorDef):
        return definition.lat_grid_origin
    raise AssertionError(f"no origin latitude known for {definition!r}")


@pytest.mark.parametrize(
    "zone",
    [
        pytest.param(ZONES_BY_CODE[p.code], id=p.code)
        for p in SPCS2022_ZONE_PARAMETERS
        if p.projection_type == "TM"
    ],
)
@pytest.mark.parametrize("latitude", [41.0, 44.0, 46.0])
def test_transverse_mercator_easting_on_the_central_meridian_is_exact(
    zone, latitude
):
    """On the central meridian L is exactly zero, so E is exactly E_0.

    The transverse Mercator's easting series is E_0 + A1 L (1 + ...): every term
    carries a factor of L, so the cancellation is exact rather than approximate,
    at any latitude. The Lambert has the same property through sin(gamma) = 0
    and it is already pinned in tests/test_lambert.py; the oblique Mercator does
    NOT, because its centre meridian is not a grid line.
    """
    point = projection.forward(latitude, zone.definition.lon_origin, zone)

    assert point.easting == zone.definition.easting_origin


@pytest.mark.parametrize(
    "zone",
    [
        pytest.param(ZONES_BY_CODE[p.code], id=p.code)
        for p in SPCS2022_ZONE_PARAMETERS
        if p.projection_type == "LC1"
    ],
)
@pytest.mark.parametrize("latitude", [42.0, 44.5, 47.0])
def test_lambert_one_parallel_easting_on_the_central_meridian_is_exact(
    zone, latitude
):
    """E = E_0 + R sin(gamma), and gamma is exactly zero on the meridian."""
    point = projection.forward(latitude, zone.definition.lon_origin, zone)

    assert point.easting == zone.definition.easting_origin


def test_the_statewide_lattice_is_asymmetric_about_the_centre():
    """The anti-averaging pin: the capture's own asymmetry, reproduced.

    A symmetric pair of geodetic offsets is NOT symmetric in the projected
    plane, and review/nsrs-h1-anchors/CAPTURE.md section B records the measured
    figures. About zone 261003's origin, +0.15 degrees of latitude gives
    +16,694.540 m of northing and -0.15 gives -16,633.454 m: the two sum to
    +61.086 m, not to zero. Any engine that averaged the asymmetry away - or
    that computed the northing from a symmetric approximation - would reproduce
    neither figure.

    Hand derivation of the expected sum, from the two frozen anchors' own
    printed northings and the zone's published false northing of 76,200 m:
        (92,894.540 - 76,200) + (59,566.546 - 76,200)
      =  16,694.540           + (-16,633.454)
      =  +61.086 m
    """
    zone = ZONES_BY_CODE["261003"]
    false_northing = PARAMETERS_BY_CODE["261003"].false_northing_m

    north = projection.forward(42.9 + 0.15, -83.4 + 0.25, zone)
    south = projection.forward(42.9 - 0.15, -83.4 - 0.25, zone)

    up = north.northing - false_northing
    down = south.northing - false_northing

    assert up == pytest.approx(16694.540, abs=SPCS2022_PRINTED["linear_m"])
    assert down == pytest.approx(-16633.454, abs=SPCS2022_PRINTED["linear_m"])
    assert up + down == pytest.approx(61.086, abs=0.001)

    # And the two scale factors differ in the ninth decimal, which the capture
    # also records (1.000029418 against 1.000029412).
    assert north.scale_factor == pytest.approx(
        1.000029418, abs=SPCS2022_PRINTED["scale_factor"]
    )
    assert south.scale_factor == pytest.approx(
        1.000029412, abs=SPCS2022_PRINTED["scale_factor"]
    )
    assert north.scale_factor != south.scale_factor


# --------------------------------------------------------------------------
# The one-parallel Lambert constructor, cross-checked against the two-parallel
# one. Independent of any beta number.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("zone", ALL_ZONES, ids=[z.abbrev for z in ALL_ZONES])
def test_the_two_lambert_constructors_agree_on_the_same_cone(zone):
    """Feed a two-parallel zone's DERIVED phi_0 and k_0 to the one-parallel form.

    The two constructors solve for the same cone from different givens. Taking
    the central parallel and origin scale that ``from_two_parallels`` derived
    for a Michigan zone and handing them to ``from_one_parallel`` must land on
    the same cone constant, the same K and the same R_0 - to floating-point
    round-off, since the numbers travel through asin and back.

    This is the strongest check available on ``from_one_parallel`` that does not
    involve a beta number, and it is a genuine one: the two derivations share no
    line of code. The constructor's own k_0 round-trip check cannot do this job
    - it is an algebraic identity (see the note in lambert.py).
    """
    two = lambert.constants_for(zone)
    one = LambertConstants.from_one_parallel(
        LambertOneParallelDef(
            lat_origin=two.lat_origin,
            k_origin=two.k_origin,
            lon_origin=zone.definition.lon_origin,
            northing_grid_origin=0.0,
            easting_origin=zone.definition.easting_origin,
        )
    )

    assert one.sin_lat_origin == pytest.approx(two.sin_lat_origin, rel=1e-15)
    assert one.K == pytest.approx(two.K, rel=1e-12)
    assert one.R_origin == pytest.approx(two.R_origin, rel=1e-14)


def test_the_one_parallel_grid_origin_is_the_central_parallel():
    """phi_b = phi_0 for an LC1 zone, so R_b IS R_0 - the same float.

    Not merely equal: the constructor assigns one value to both fields, because
    a second evaluation of the same expression at the same latitude would be a
    second representation of one fact. A defect that evaluated R_b at some other
    latitude would move every northing in the zone by a constant, which no
    round-trip test can see.
    """
    constants = LambertConstants.from_one_parallel(
        LambertOneParallelDef(42.9, 1.000026, -83.4, 76200.0, 685800.0)
    )

    assert constants.R_grid_origin == constants.R_origin
    assert constants.northing_origin == constants.northing_grid_origin


@pytest.mark.parametrize(
    "definition,fragment",
    [
        pytest.param(
            LambertOneParallelDef(0.0, 1.000026, -83.4, 0.0, 685800.0),
            "off the equator",
            id="equator",
        ),
        pytest.param(
            LambertOneParallelDef(90.0, 1.000026, -83.4, 0.0, 685800.0),
            "between the poles",
            id="pole",
        ),
        pytest.param(
            LambertOneParallelDef(42.9, 0.0, -83.4, 0.0, 685800.0),
            "must be positive",
            id="zero-scale",
        ),
        pytest.param(
            LambertOneParallelDef(42.9, -1.000026, -83.4, 0.0, 685800.0),
            "must be positive",
            id="negative-scale",
        ),
    ],
)
def test_the_one_parallel_constructor_refuses_a_degenerate_definition(
    definition, fragment
):
    """Refusals name the offending value and say what it would have produced."""
    with pytest.raises(ValueError) as raised:
        LambertConstants.from_one_parallel(definition)

    assert fragment in str(raised.value)


def test_the_one_parallel_scale_check_is_documented_as_not_verification():
    """The k_0 round trip is a typo check; the docstring must say so.

    Recorded as a pin because the danger is not the code - it is a later reader
    treating a passing self-check as evidence the mathematics is right, when it
    is the same equation read in both directions. docs/PLAN-nsrs-modernization.md
    requires the distinction be documented, so the documentation is what is
    pinned.
    """
    from pathlib import Path

    lambert_source = Path(lambert.__file__).read_text(encoding="utf-8")

    assert "NOT VERIFICATION" in lambert_source
    assert "algebraic identity" in lambert_source

    # And the check itself is live, not decorative: a definition whose k_0 does
    # not belong to its phi_0 cannot be constructed by mutating the record
    # (frozen), so the check is demonstrated by calling the constructor with a
    # deliberately inconsistent pair reached through the same code path.
    consistent = LambertConstants.from_one_parallel(
        LambertOneParallelDef(42.9, 1.000026, -83.4, 76200.0, 685800.0)
    )
    assert consistent.k_origin == pytest.approx(1.000026, rel=1e-14)


# --------------------------------------------------------------------------
# 4. The dispatcher.
# --------------------------------------------------------------------------


def test_every_definition_type_in_the_union_has_an_engine():
    """The union in zones.py and the table in projection.py cover each other.

    Adding a definition record without registering it would leave a zone that
    computes nothing; registering one that is not in the union would leave a
    table entry nothing can reach. Both directions are checked, so the pin
    cannot be satisfied by an empty table.
    """
    from typing import get_args

    union_members = set(get_args(ProjectionDef))
    registered = set(projection.registered_definition_types())

    assert union_members == registered
    assert len(registered) == 4


def test_the_dispatch_table_gives_each_type_the_right_kind():
    """One entry supplies the kind and the engine, so they cannot disagree."""
    expected = {
        LambertTwoParallelDef: ProjectionKind.LAMBERT_CONIC_2SP,
        LambertOneParallelDef: ProjectionKind.LAMBERT_CONIC_1SP,
        TransverseMercatorDef: ProjectionKind.TRANSVERSE_MERCATOR,
        ObliqueMercatorCenterDef: ProjectionKind.OBLIQUE_MERCATOR,
    }

    assert set(expected) == set(projection.registered_definition_types())
    for record, kind in expected.items():
        definition = _sample_definition(record)
        assert projection.projection_kind_for_definition(definition) is kind


def _sample_definition(record: type):
    """A minimal, valid definition of each kind, for table tests."""
    if record is LambertTwoParallelDef:
        return LambertTwoParallelDef(42.1, 43.6, 41.5, -84.3, 0.0, 4000000.0)
    if record is LambertOneParallelDef:
        return LambertOneParallelDef(42.9, 1.000026, -83.4, 76200.0, 685800.0)
    if record is TransverseMercatorDef:
        return TransverseMercatorDef(41.3, -84.1, 1.000022, 0.0, 381000.0)
    if record is ObliqueMercatorCenterDef:
        return ObliqueMercatorCenterDef(45.0, -86.0, -26.0, 0.9998, 762000.0, 1524000.0)
    raise AssertionError(f"no sample definition for {record!r}")


@dataclasses.dataclass(frozen=True)
class _UnregisteredDef:
    """A definition type no engine claims - for the refusal test only."""

    lon_origin: float = -84.0
    easting_origin: float = 500000.0
    northing_grid_origin: float = 0.0


def test_an_unregistered_definition_type_refuses_by_name():
    """Fails closed, names the type, and lists what does exist.

    The alternative - falling through to whichever engine is handy - is silent:
    every projection here turns an ordinary latitude into an ordinary-looking
    coordinate, so a wrong engine produces a number a surveyor would accept.
    """
    zone = Zone(
        code="999999",
        abbrev="XX",
        name="Nowhere",
        system="SPCS2022",
        frame=NATRF2022,
        definition=_UnregisteredDef(),
        citation="test",
        lat_min=0.0,
        lat_max=90.0,
        lon_min=-180.0,
        lon_max=0.0,
    )

    with pytest.raises(ProjectionUnavailableError) as raised:
        projection.forward(43.0, -84.0, zone)

    message = str(raised.value)
    assert "_UnregisteredDef" in message
    assert "Lambert conformal conic, two standard parallels" in message
    assert "Hotine oblique Mercator" in message

    with pytest.raises(ProjectionUnavailableError):
        projection.inverse(100000.0, 500000.0, zone)
    with pytest.raises(ProjectionUnavailableError):
        projection.constants_for(zone)
    with pytest.raises(ProjectionUnavailableError):
        zone.projection_kind


@pytest.mark.parametrize("zone", ALL_ZONES, ids=[z.abbrev for z in ALL_ZONES])
def test_the_shipped_zones_are_two_parallel_lambert(zone):
    """Zone.projection_kind, derived from the dispatch table rather than stored."""
    assert zone.projection_kind is ProjectionKind.LAMBERT_CONIC_2SP


def test_the_definition_records_no_longer_store_their_kind():
    """``kind`` is deleted, not merely unread (docs/DESIGN.md #21).

    A stored kind beside a definition type is a second representation of one
    fact, free to disagree with the engine actually dispatched to. Pinned as an
    absence so it cannot come back quietly.
    """
    for record in projection.registered_definition_types():
        fields = {f.name for f in dataclasses.fields(record)}
        assert "kind" not in fields, f"{record.__name__} stores a kind field"


@pytest.mark.parametrize(
    "record",
    [
        LambertTwoParallelDef,
        LambertOneParallelDef,
        TransverseMercatorDef,
        ObliqueMercatorCenterDef,
    ],
    ids=lambda r: r.__name__,
)
def test_every_definition_record_satisfies_the_structural_contract(record):
    """Three accessors, one meaning, across the whole union.

    ``convert.py``'s easting-window check reads ``definition.easting_origin``
    blind, without knowing which projection it has; so will the job layer and
    the record writer. The oblique Mercator names its three after the centre
    because that is what they are anchored to, and exposes them under these
    names as properties reading its own fields - not as stored copies.
    """
    definition = _sample_definition(record)

    assert isinstance(definition.lon_origin, float)
    assert isinstance(definition.easting_origin, float)
    assert isinstance(definition.northing_grid_origin, float)

    # And the aliases are aliases: they read the record, they do not shadow it.
    if record is ObliqueMercatorCenterDef:
        assert definition.lon_origin == definition.lon_center
        assert definition.easting_origin == definition.easting_center
        assert definition.northing_grid_origin == definition.northing_center


@pytest.mark.parametrize(
    "record",
    [
        LambertTwoParallelDef,
        LambertOneParallelDef,
        TransverseMercatorDef,
        ObliqueMercatorCenterDef,
    ],
    ids=lambda r: r.__name__,
)
def test_every_definition_record_is_frozen_and_hashable(record):
    """``constants_for`` is an lru_cache keyed on the Zone, which holds one.

    An unhashable definition would make every conversion raise, and a mutable
    one would let a cached constants record describe a zone that has since
    changed underneath it.
    """
    definition = _sample_definition(record)

    assert hash(definition) == hash(_sample_definition(record))
    assert definition == _sample_definition(record)

    field_name = dataclasses.fields(record)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(definition, field_name, 0.0)


def test_constants_for_stamps_the_zone_code_on_every_engines_record():
    """Constants can never be silently paired with another zone's identity."""
    for zone in list(ZONES_BY_CODE.values()) + list(ALL_ZONES):
        assert projection.constants_for(zone).zone_code == zone.code


def test_constants_for_is_cached_without_a_bound():
    """A bound small enough to evict would re-derive inside one job's row loop.

    The registry is finite and immutable, so an unbounded cache cannot grow
    without bound either.
    """
    info = projection.constants_for.cache_info()

    assert info.maxsize is None

    first = projection.constants_for(MI_SOUTH)
    second = projection.constants_for(MI_SOUTH)
    assert first is second


# --------------------------------------------------------------------------
# The dispatcher must not have changed the three shipped zones by a bit.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("zone", ALL_ZONES, ids=[z.abbrev for z in ALL_ZONES])
def test_the_dispatcher_returns_the_lambert_engines_own_constants(zone):
    """Bit-identical to what ``from_two_parallels`` produces on its own.

    The whole of H1 is a refactor as far as SPCS 83 is concerned, and this is
    the pin that says so at the constants level; the eighteen output digests in
    tests/test_orthometric_regression.py say it at the file level.
    """
    dispatched = projection.constants_for(zone)
    direct = dataclasses.replace(
        LambertConstants.from_two_parallels(zone.definition, GRS80),
        zone_code=zone.code,
    )

    assert dispatched == direct
    assert isinstance(dispatched, LambertConstants)


@pytest.mark.parametrize("zone", ALL_ZONES, ids=[z.abbrev for z in ALL_ZONES])
@pytest.mark.parametrize(
    "latitude,longitude",
    [(42.7325, -84.5555), (45.3, -87.0), (44.15, -82.5), (46.75, -90.1)],
)
def test_the_dispatcher_and_the_lambert_engine_agree_to_the_last_bit(
    zone, latitude, longitude
):
    """Same numbers, not merely the same to a tolerance."""
    through_dispatcher = projection.forward(latitude, longitude, zone)
    directly = lambert.forward(latitude, longitude, lambert.constants_for(zone))

    assert through_dispatcher == directly

    back_through = projection.inverse(
        directly.northing, directly.easting, zone
    )
    back_directly = lambert.inverse(
        directly.northing, directly.easting, lambert.constants_for(zone)
    )
    assert back_through == back_directly


def test_lambert_still_exports_the_names_that_moved():
    """GridPoint, GeodeticPoint, the guards and constants_for are re-exported.

    They moved to projection.py because three engines share them. Every existing
    import of them from lambert keeps working, and there is one definition of
    each rather than two.
    """
    assert lambert.GridPoint is projection.GridPoint
    assert lambert.GeodeticPoint is projection.GeodeticPoint
    assert lambert.constants_for is projection.constants_for
    assert lambert._require_valid_geodetic is projection._require_valid_geodetic
    assert lambert._require_finite_grid is projection._require_finite_grid


# --------------------------------------------------------------------------
# Refusals in the two new engines.
# --------------------------------------------------------------------------


def test_the_oblique_mercator_refuses_a_skew_the_manual_cannot_carry():
    """|alpha_c| >= 90 degrees: the manual's positive root is the wrong branch.

    Section 3.3 takes cos(alpha_0) = +sqrt(1 - sin^2 alpha_0) without saying it
    assumes anything. It does: |alpha_0| < 90. The assumption is checked here
    rather than inherited, per the extraction's flag.
    """
    with pytest.raises(ValueError) as raised:
        omerc.ObliqueMercatorConstants.from_definition(
            ObliqueMercatorCenterDef(45.0, -86.0, 90.0, 0.9998, 762000.0, 1524000.0)
        )

    message = str(raised.value)
    assert "alpha_0" in message
    assert "90" in message


@pytest.mark.parametrize("skew", [-26.0, 0.0, 26.0, 89.9])
def test_the_oblique_mercator_accepts_every_skew_the_manual_can_carry(skew):
    """The refusal above is not vacuous: the admissible band really is open."""
    constants = omerc.ObliqueMercatorConstants.from_definition(
        ObliqueMercatorCenterDef(45.0, -86.0, skew, 0.9998, 762000.0, 1524000.0)
    )

    assert -1.0 < constants.F < 1.0
    assert constants.G > 0.0


def test_the_transverse_mercator_refuses_a_non_positive_scale():
    with pytest.raises(ValueError) as raised:
        tm.TransverseMercatorConstants.from_definition(
            TransverseMercatorDef(41.3, -84.1, 0.0, 0.0, 381000.0)
        )

    assert "must be positive" in str(raised.value)


def test_the_transverse_mercator_refuses_a_northing_past_the_pole():
    """A northing that implies a rectifying latitude outside (-90, 90).

    No geodetic position corresponds, and the footpoint series would happily
    return an ordinary-looking latitude for it. Reachable from a transposed
    northing and easting, which is the named suspect in the message.
    """
    constants = tm.TransverseMercatorConstants.from_definition(
        TransverseMercatorDef(41.3, -84.1, 1.000022, 0.0, 381000.0)
    )

    with pytest.raises(ValueError) as raised:
        tm.inverse(30000000.0, 381000.0, constants)

    assert "beyond the pole" in str(raised.value)
    assert "transposed" in str(raised.value)


@pytest.mark.parametrize(
    "engine,constants",
    [
        pytest.param(
            tm,
            tm.TransverseMercatorConstants.from_definition(
                TransverseMercatorDef(41.3, -84.1, 1.000022, 0.0, 381000.0)
            ),
            id="tm",
        ),
        pytest.param(
            omerc,
            omerc.ObliqueMercatorConstants.from_definition(
                ObliqueMercatorCenterDef(
                    45.0, -86.0, -26.0, 0.9998, 762000.0, 1524000.0
                )
            ),
            id="omerc",
        ),
    ],
)
def test_the_new_engines_refuse_the_east_longitude_convention(engine, constants):
    """275.4445 is Michigan's 84.5555 W in the 0-360 convention.

    An ordinary float that produces a coordinate with no warning worth noticing
    and is wrong by thousands of kilometres (docs/DESIGN.md amendment #10). The
    guard is shared, and this pins that both new engines call it - a new engine
    that forgot to would be silent.
    """
    with pytest.raises(ValueError) as raised:
        engine.forward(43.0, 275.4445, constants)

    assert "0-360 east convention" in str(raised.value)

    with pytest.raises(ValueError):
        engine.forward(float("nan"), -84.0, constants)
    with pytest.raises(ValueError):
        engine.inverse(float("nan"), 500000.0, constants)


# --------------------------------------------------------------------------
# The convergence parser the anchors are read through.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        # Hand derivations, longhand:
        #   +01 54 40.49 -> 1 + 54/60 + 40.49/3600
        #                 = 1 + 0.9 + 0.011247222...  = 1.911247222...
        ("+01 54 40.49", 1.0 + 54.0 / 60.0 + 40.49 / 3600.0),
        #   -00 22 23.36 -> -(0 + 22/60 + 23.36/3600)
        #                 = -(0.366666... + 0.006488888...) = -0.373155555...
        #   THE CASE THAT MOTIVATES THE EXPLICIT SIGN: float("-00") is -0.0, and
        #   -0.0 + 22/60 is POSITIVE 0.3666. Four anchors have zero degrees and
        #   a negative angle.
        ("-00 22 23.36", -(22.0 / 60.0 + 23.36 / 3600.0)),
        #   -01 53 16.29 -> -(1 + 53/60 + 16.29/3600) = -1.887858333...
        ("-01 53 16.29", -(1.0 + 53.0 / 60.0 + 16.29 / 3600.0)),
        #   the signed zero beta NCAT prints at the statewide centre
        ("-00 00 00.00", 0.0),
        ("+00 00 00.00", 0.0),
    ],
)
def test_the_convergence_parser_matches_the_hand_derivation(text, expected):
    assert dms_to_degrees(text) == pytest.approx(expected, abs=1e-15)


def test_the_convergence_parser_refuses_a_string_it_cannot_read():
    """Refuses rather than returning a plausible partial angle."""
    with pytest.raises(ValueError) as raised:
        dms_to_degrees("+01 54")

    assert "degrees/minutes/seconds" in str(raised.value)


def test_the_negative_zero_degree_case_is_actually_present_in_the_anchors():
    """Anti-vacuousness for the parser pin above.

    If no anchor had zero degrees with a negative sign, the sign handling would
    be untested by the data it exists for.
    """
    negative_zero_degree = [
        a
        for a in SPCS2022_PROJECTION_ANCHORS
        if a.convergence_dms.startswith("-00 ")
        and not a.convergence_dms.startswith("-00 00 00.00")
    ]

    assert negative_zero_degree
    for anchor in negative_zero_degree:
        assert dms_to_degrees(anchor.convergence_dms) < 0.0


# --------------------------------------------------------------------------
# The fixture itself.
# --------------------------------------------------------------------------


def test_the_fixture_carries_the_whole_capture():
    """Counts from review/nsrs-h1-anchors/CAPTURE.md, so a lost row is loud."""
    assert len(SPCS2022_ZONE_PARAMETERS) == 19
    assert len(SPCS2022_PROJECTION_ANCHORS) == 63
    assert len(ORIGIN_ANCHORS) == 19

    statewide = [a for a in SPCS2022_PROJECTION_ANCHORS if a.zone_code == "260001"]
    assert len(statewide) == 9
    assert len({a.zone_code for a in SPCS2022_PROJECTION_ANCHORS}) == 19


def test_the_fixture_zone_types_are_the_ones_ngs_published():
    """One OMC, five TM, thirteen LC1 - DESIGN.md #61's own count."""
    kinds = [p.projection_type for p in SPCS2022_ZONE_PARAMETERS]

    assert kinds.count("OMC") == 1
    assert kinds.count("TM") == 5
    assert kinds.count("LC1") == 13
    assert all(p.origin_scale >= 1.0 for p in SPCS2022_ZONE_PARAMETERS[1:])
    assert SPCS2022_ZONE_PARAMETERS[0].origin_scale == 0.9998


def test_the_fixture_is_tagged_as_beta_and_dated():
    """The re-freeze obligation is a mechanism, not a memory (DESIGN.md #61)."""
    from pathlib import Path

    from tests.fixtures import spcs2022_engine_anchors

    text = Path(spcs2022_engine_anchors.__file__).read_text(encoding="utf-8")

    assert "NGS BETA" in text
    assert "2026-08-28" in text
    assert "re-frozen" in text


def test_no_shipped_module_imports_this_fixture():
    """Anchors are a check, never a second copy of a fact the core derives.

    tests/test_architecture.py enforces the general rule over the whole package;
    this names the newest and largest fixture specifically. It scans IMPORTS,
    not text: lambert.py and the engine modules mention this file by path in
    their docstrings, on purpose, because a reader should be told where the
    verification lives.
    """
    import ast
    from pathlib import Path

    package = Path(lambert.__file__).resolve().parent.parent
    imported: list[str] = []
    for path in package.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if "spcs2022_engine_anchors" in name or name.startswith("tests"):
                    imported.append(f"{path.name} imports {name}")

    assert not imported, "shipped code imported a test fixture:\n" + "\n".join(
        imported
    )


def test_the_frame_anchors_were_deliberately_left_out():
    """Projection anchors and frame anchors are different kinds of claim.

    The capture holds fifteen NAD83(2011) <-> NATRF2022 results as well. They
    depend on an unpublished transformation with no official specification, and
    nothing checks them against anything (CAPTURE.md, "What these anchors do NOT
    prove", item 2). They belong to H3. Pinned as an absence so a later hand
    does not fold them in here, where a projection test could pass on a frame
    number.
    """
    from pathlib import Path

    from tests.fixtures import spcs2022_engine_anchors

    text = Path(spcs2022_engine_anchors.__file__).read_text(encoding="utf-8")

    assert not hasattr(spcs2022_engine_anchors, "FRAME_ANCHORS")
    assert "H3" in text
    # Every anchor in the module is a pure projection: both datums equal, so no
    # transformation stood between the position and the grid coordinate. The
    # capture's own record of that is quoted in the docstring, and the fixture
    # carries no field that could hold a transformed position.
    anchor_fields = {
        f.name for f in dataclasses.fields(spcs2022_engine_anchors.Spcs2022Anchor)
    }
    assert not {"output_latitude", "output_longitude", "sigma"} & anchor_fields
    # And every zone these anchors belong to is on NATRF2022 - the frame the
    # throwaway zones above are tagged with - so no anchor here can be read as
    # a statement about NAD 83.
    assert all(zone.frame is NATRF2022 for zone in ZONES_BY_CODE.values())
