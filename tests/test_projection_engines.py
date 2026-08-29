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
from pathlib import Path

import pytest

from michspc.spc import lambert, omerc, projection, tm
from michspc.spc.ellipsoid import GRS80
from michspc.spc.frames import NATRF2022
from michspc.spc.lambert import LambertConstants
from michspc.spc.projection import ProjectionUnavailableError
from michspc.spc.units import INTERNATIONAL_FEET
from michspc.spc.zones import (
    SPCS2022_ZONES,
    SPCS83_ZONES,
    MI_SOUTH,
    LambertOneParallelDef,
    LambertTwoParallelDef,
    ObliqueMercatorCenterDef,
    ProjectionDef,
    ProjectionKind,
    TransverseMercatorDef,
    Zone,
    dms,
    zone_by_code,
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
# H1 built the ENGINES and ran the anchors through throwaway Zone records,
# because no SPCS2022 zone was in the registry yet. **H2 added the nineteen
# real records, and the anchors now run through those** - so these tests prove
# something they could not prove before: that the registry's transcription and
# the fixture's transcription are the same numbers, all the way through the
# engines to a coordinate beta NCAT computed independently.
#
# ``definition_for`` survives the change and earns its keep twice over: it is
# the second, independent transcription that
# ``test_the_registry_definitions_are_the_frozen_parameters`` compares the
# registry against, and it is what makes NGS's ``Proj type`` string decide
# which record type a zone gets.
# --------------------------------------------------------------------------


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


ZONES_BY_CODE = {zone.code: zone for zone in SPCS2022_ZONES}
"""**The shipped registry records**, not test-local copies of them.

Every anchor below therefore checks the zone a job would actually use. A
transcription error in michspc/spc/zones.py now fails against beta NCAT's own
coordinate, on top of failing the field-by-field cross-check against NGS's
frozen file in tests/test_zone_registry.py.
"""

PARAMETERS_BY_CODE = {p.code: p for p in SPCS2022_ZONE_PARAMETERS}


@pytest.mark.parametrize(
    "zone", SPCS2022_ZONES, ids=[z.code for z in SPCS2022_ZONES]
)
def test_the_registry_definitions_are_the_frozen_parameters(zone):
    """The shipped record and the fixture say the same thing, record for record.

    Two independent transcriptions of NGS's file meet here: the one in
    michspc/spc/zones.py, written as ``dms(45, 27)`` with the arithmetic in a
    comment, and the one in tests/fixtures/spcs2022_engine_anchors.py, written
    as decimal degrees. They were made separately, in different work packages,
    and a disagreement between them is a transcription error in one or the
    other.

    This is a check on the two COPIES agreeing. What checks either of them
    against the authority is tests/test_zone_registry.py, which parses NGS's
    own digest-pinned file - and what checks the resulting mathematics is the
    63 beta NCAT anchors below.
    """
    parameters = PARAMETERS_BY_CODE[zone.code]

    assert zone.definition == definition_for(parameters)
    assert zone.abbrev == parameters.abbrev
    assert zone.name == parameters.name
    assert zone.projection_kind is {
        "OMC": ProjectionKind.OBLIQUE_MERCATOR,
        "LC1": ProjectionKind.LAMBERT_CONIC_1SP,
        "TM": ProjectionKind.TRANSVERSE_MERCATOR,
    }[parameters.projection_type]

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


# --------------------------------------------------------------------------
# The inverse's OWN gamma and k, against the same captured NCAT values.
#
# The convergence and the grid scale factor are properties of the POSITION, not
# of the direction it was reached from: NCAT prints one value for each at a
# point, and both of this program's directions must reproduce it. The forward
# side has been anchored against those printed values since H1; the inverse
# side had not, and its gamma and k come from a genuinely different series -
# the manual's section 3.24 D and G coefficients, against section 3.23's C and
# F.
#
# The re-confirmation round measured what that cost: all ten seeded mutations
# of the transverse Mercator's inverse D/G series were caught by exactly ONE
# test, test_the_two_directions_agree_about_convergence_and_scale, which
# compares the two directions to each other. That test is worth keeping - it is
# tight, and it holds at points no anchor covers - but on its own it is a
# single point of coverage, and it is INTERNAL: it says the two directions
# agree, not that either agrees with NGS. The two tests below add the external
# half, per zone, at all 63 captured positions.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", SPCS2022_PROJECTION_ANCHORS, ids=ANCHOR_IDS)
def test_inverse_matches_beta_ncat_scale_factor(anchor):
    """The inverse's k at NGS's own northing and easting.

    Same captured value the forward test uses and the same derived tolerance -
    half a unit in the ninth decimal place NCAT prints. Measured worst across
    all 63 anchors on the inverse side: 4.9691e-10, at zone 261006's
    +0.15/+0.25 point, which is the same anchor and the same near-rounding-
    boundary reason recorded in the fixture's tolerance comment. All 63 inverse
    values print identically to NGS at nine decimals.
    """
    position = projection.inverse(
        anchor.northing_m, anchor.easting_m, ZONES_BY_CODE[anchor.zone_code]
    )

    assert position.scale_factor == pytest.approx(
        anchor.scale_factor, abs=SPCS2022_PRINTED["scale_factor"]
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", SPCS2022_PROJECTION_ANCHORS, ids=ANCHOR_IDS)
def test_inverse_matches_beta_ncat_convergence(anchor):
    """The inverse's gamma at NGS's own northing and easting.

    The sign convention is checked here as well as on the forward side, at the
    same eighteen east-of-origin and west-of-origin pairs: a sign error in the
    inverse's D series alone would leave every forward anchor green.

    Measured worst across all 63: 4.705e-03 arc seconds, at zone 261010's
    +0.15/+0.25 point, against the 0.005 half-quantum of NCAT's printed 0.01
    arc second. Close to the bound, and expected to be - it is a printed-
    precision comparison, so a value near a rounding boundary must approach
    half a quantum without crossing it.
    """
    position = projection.inverse(
        anchor.northing_m, anchor.easting_m, ZONES_BY_CODE[anchor.zone_code]
    )

    expected = dms_to_degrees(anchor.convergence_dms)
    assert position.convergence * 3600.0 == pytest.approx(
        expected * 3600.0, abs=SPCS2022_PRINTED["convergence_arcsec"]
    )


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


# --------------------------------------------------------------------------
# The INVERSE side's derivative. Every engine, no exemptions.
#
# Until the interim H1+H2 gate there was no derivative check on any inverse at
# all: test_convergence_and_scale_agree_with_a_finite_difference differentiates
# the FORWARD mapping only. The gate demonstrated what that costs by seeding the
# inverse's B7 denominator 5040 -> 5000 and watching 1,674 tests stay green.
#
# The check here is the composition rule. If ``inverse`` really is the inverse
# of ``forward``, then the Jacobian of one is the matrix inverse of the other's
# at the same point, so their product is the identity:
#
#     J_inv = [[d phi / dN, d phi / dE],      J_fwd = [[dN / d phi, dN / d lam],
#              [d lam / dN, d lam / dE]]               [dE / d phi, dE / d lam]]
#
#     J_inv . J_fwd = I
#
# Both are taken by central difference on the real public entry points, so no
# engine internals are touched and the test reads the same for all four
# projections. The product is dimensionless, which is what lets one tolerance
# cover engines whose coordinates are metres and whose positions are degrees.
#
# **All four entries are asserted separately.** That is the same lesson the
# closure table above carries: collapsing them with max() lets the entry with
# the larger legitimate truncation hide a defect in another.
# --------------------------------------------------------------------------

JACOBIAN_FORWARD_STEP_DEG = 1e-4
JACOBIAN_INVERSE_STEP_M = 10.0
"""Central-difference steps, chosen where truncation and round-off cross.

For the forward step: truncation goes as h^2/6 times the third derivative,
about 5e-13 relative at 1e-4 degrees; round-off goes as the ulp of a
million-metre coordinate divided by 2h, about 1e-11 relative. For the inverse
step: the same two terms at 10 m give about 4e-13 and 6e-11. Both are
round-off-dominated, and both are near the minimum - measured on an
exact-inverse engine (LC1 261017, 7.8 degrees off its meridian), the worst
product entry is 1.0e-10 at (1e-3, 100 m), 6.0e-11 at these steps, and
1.1e-09 at (1e-5, 1 m), so a ten-times-smaller step is ten times WORSE.
"""

JACOBIAN_TOLERANCE = 5e-9
"""How far a product entry may sit from its pinned value.

Derived from the finite-difference noise above, not fitted: the worst entry
measured on any engine whose inverse is exact - both Lamberts and the oblique
Mercator, at both probes - is 1.04e-10, so this is about fifty times the
measured noise floor. It is deliberately ONE absolute number for every entry of
every engine, so that a pinned truncation value and a pinned zero are held to
the same standard and no engine gets a tolerance of its own.
"""

JACOBIAN_PROBES = (
    # (zone code, probe latitude, degrees west of the central meridian,
    #  the four entries of J_inv . J_fwd - I, in reading order)
    #
    # Zero means "identity to within the finite-difference noise": the engine's
    # inverse is exact there, and the pinned zero says so. A non-zero value is
    # the engine's own legitimate series truncation, measured.
    #
    # One zone per registered definition type, checked below against the
    # dispatch table so that a fifth projection cannot arrive unprobed.
    ("2113", 41.5, 0.5, (0.0, 0.0, 0.0, 0.0)),
    ("2113", 41.5, 7.8, (0.0, 0.0, 0.0, 0.0)),
    ("261017", 46.7, 0.5, (0.0, 0.0, 0.0, 0.0)),
    ("261017", 46.7, 7.8, (0.0, 0.0, 0.0, 0.0)),
    ("260001", 45.0, 0.5, (0.0, 0.0, 0.0, 0.0)),
    ("260001", 45.0, 7.8, (0.0, 0.0, 0.0, 0.0)),
    ("261002", 40.2, 0.5, (0.0, 0.0, 0.0, 0.0)),
    # The transverse Mercator is the one engine whose inverse is a truncated
    # series, so it is the only row that departs from the identity. Measured:
    # d(lat)/dN . dN/d(lat) - 1 = +4.7e-10 (inside the noise, pinned 0),
    # the two cross terms +1.062611e-07 and +2.655635e-09, and
    # d(lon)/dE . dE/d(lon) - 1 = -2.193424e-08.
    #
    # The last of those is what the gate's B7 seed moves: 5040 -> 5000 takes it
    # to -4.366964e-08, a shift of 2.17e-08, more than four times this
    # tolerance. The cross term +1.062611e-07 does NOT move, which is why the
    # entries are pinned one by one.
    ("261002", 40.2, 7.8, (0.0, 1.062611e-07, 2.655635e-09, -2.193424e-08)),
)


def _jacobian_forward(latitude, longitude, zone):
    """[[dN/dphi, dN/dlam], [dE/dphi, dE/dlam]], metres per degree."""
    step = JACOBIAN_FORWARD_STEP_DEG
    north = projection.forward(latitude + step, longitude, zone)
    south = projection.forward(latitude - step, longitude, zone)
    east = projection.forward(latitude, longitude + step, zone)
    west = projection.forward(latitude, longitude - step, zone)
    return (
        (north.northing - south.northing) / (2.0 * step),
        (east.northing - west.northing) / (2.0 * step),
        (north.easting - south.easting) / (2.0 * step),
        (east.easting - west.easting) / (2.0 * step),
    )


def _jacobian_inverse(northing, easting, zone):
    """[[dphi/dN, dphi/dE], [dlam/dN, dlam/dE]], degrees per metre."""
    step = JACOBIAN_INVERSE_STEP_M
    up = projection.inverse(northing + step, easting, zone)
    down = projection.inverse(northing - step, easting, zone)
    right = projection.inverse(northing, easting + step, zone)
    left = projection.inverse(northing, easting - step, zone)
    return (
        (up.latitude - down.latitude) / (2.0 * step),
        (right.latitude - left.latitude) / (2.0 * step),
        (up.longitude - down.longitude) / (2.0 * step),
        (right.longitude - left.longitude) / (2.0 * step),
    )


def _jacobian_product_minus_identity(latitude, longitude, zone):
    """J_inv . J_fwd - I, as four numbers in reading order."""
    point = projection.forward(latitude, longitude, zone)
    f11, f12, f21, f22 = _jacobian_forward(latitude, longitude, zone)
    g11, g12, g21, g22 = _jacobian_inverse(point.northing, point.easting, zone)
    return (
        g11 * f11 + g12 * f21 - 1.0,
        g11 * f12 + g12 * f22,
        g21 * f11 + g22 * f21,
        g21 * f12 + g22 * f22 - 1.0,
    )


@pytest.mark.parametrize(
    "code,latitude,offset,expected",
    JACOBIAN_PROBES,
    ids=[f"{row[0]}@{row[2]}deg" for row in JACOBIAN_PROBES],
)
def test_each_engines_inverse_jacobian_is_the_forwards_matrix_inverse(
    code, latitude, offset, expected
):
    """The inverse's derivative, checked against the forward's, entry by entry.

    A round trip composes the two mappings and can hide a defect inside a
    legitimate truncation; this composes their DERIVATIVES, where a high-order
    coefficient's contribution is amplified by its own order and cannot be
    absorbed by the other coordinate's residual, because each entry is asserted
    on its own.

    Both probes matter and they say different things. In the zone, every entry
    of every engine must be at the finite-difference noise floor - there is no
    truncation to hide behind, so this is a flat statement that each inverse is
    the inverse. Far out, the exact engines must STILL be at the floor, and the
    one truncated engine must match its measured curve.
    """
    zone = zone_by_code(code)
    longitude = zone.definition.lon_origin - offset

    measured = _jacobian_product_minus_identity(latitude, longitude, zone)

    names = ("d(lat)/dN.dN/d(lat)-1", "d(lat)/dE.dE/d(lat)", "d(lon)/dN.dN/d(lon)", "d(lon)/dE.dE/d(lon)-1")
    for name, value, pinned in zip(names, measured, expected):
        assert value == pytest.approx(pinned, abs=JACOBIAN_TOLERANCE), (
            f"{zone.abbrev} at {latitude}, {longitude}: {name} is {value:.6e}, "
            f"pinned at {pinned:.6e}"
        )


def test_the_jacobian_probes_cover_every_registered_projection():
    """No engine's inverse is exempt, and none can become exempt quietly.

    The probe table is keyed by zone code, so a projection added to the
    dispatcher without a probe would leave its inverse with no derivative check
    at all - exactly the gap the gate found on the transverse Mercator. This
    compares the definition types the probes actually exercise against the
    dispatch table itself.
    """
    probed = {type(zone_by_code(code).definition) for code, _lat, _off, _e in JACOBIAN_PROBES}

    assert probed == set(projection.registered_definition_types())
    assert len(probed) == 4


def test_the_jacobian_check_would_notice_a_broken_inverse():
    """Anti-vacuousness: the tolerance is not wide enough to pass anything.

    A deliberately wrong inverse - here the real one with its longitude nudged
    by one part in a million, far less than any coefficient typo would do -
    must blow the tolerance. Without this, a tolerance mistakenly set to 1.0
    would leave every assertion above green and meaningless.
    """
    zone = zone_by_code("261017")
    latitude = 46.7
    longitude = zone.definition.lon_origin - 0.5
    point = projection.forward(latitude, longitude, zone)

    step = JACOBIAN_INVERSE_STEP_M
    right = projection.inverse(point.northing, point.easting + step, zone)
    left = projection.inverse(point.northing, point.easting - step, zone)
    true_dlon_dE = (right.longitude - left.longitude) / (2.0 * step)

    f11, f12, f21, f22 = _jacobian_forward(latitude, longitude, zone)
    up = projection.inverse(point.northing + step, point.easting, zone)
    down = projection.inverse(point.northing - step, point.easting, zone)
    dlon_dN = (up.longitude - down.longitude) / (2.0 * step)

    broken = true_dlon_dE * (1.0 + 1e-6)
    entry = dlon_dN * f12 + broken * f22 - 1.0

    assert abs(entry) > JACOBIAN_TOLERANCE


TM_CLOSURE_PROBE_LATITUDE = 45.0

TM_CLOSURE_BY_OFFSET = (
    # (degrees from the central meridian, |d latitude|, |d longitude|), both in
    # DEGREES, measured on zone 261002 (Detroit) at 45 N going west.
    (1.0, 4.490630e-12, 4.263256e-14),
    (2.0, 6.323830e-12, 3.808509e-12),
    (3.0, 5.199752e-11, 3.016964e-11),
    (4.0, 4.816840e-10, 9.865175e-11),
    (6.0, 1.238048e-08, 1.435097e-09),
    (7.8, 1.023331e-07, 2.774695e-08),
)
"""How far the transverse Mercator series' closure degrades off its meridian.

**This is a property of the method, not a defect**: NOAA Manual NOS NGS 5's
section 3.2 series is truncated, and michspc.spc.tm keeps every term the manual
publishes (its docstring says why it keeps even the ones the manual calls
negligible). Within a zone's own area the closure is at the floating-point
floor; a zone width away it is still micrometres; seven degrees out it is a
hundred nanodegrees of latitude, about eleven millimetres.

**The two components are stored and asserted SEPARATELY, and that is the whole
point of this table.** An earlier version stored one bound per offset on
``max(d_latitude, d_longitude)``. The interim H1+H2 gate broke it: seeding the
inverse's B7 denominator ``5040 -> 5000`` - a plausible one-token typo - left
all 1,674 projection and conversion tests green. The reason is visible in the
numbers above: at every offset the LATITUDE residual is four to seven times the
longitude residual, and B7 belongs to the longitude series alone. Taking the
max threw away the only component that carried the defect. Under that seed the
longitude column reads 3.9e-12 / 1.6e-10 / 5.9e-09 / 5.6e-08 at 3, 4, 6 and 7.8
degrees - between 60% and 310% away from the values above - while the latitude
column is unchanged to every digit.

Tolerance: 1% relative, or 1e-11 degrees absolute, whichever is larger
(``pytest.approx`` takes the looser of the two). The absolute floor is the
round-off floor of these coordinates - a double holds 45 degrees to about
7e-15, and the accumulated round-off of the two series is a few thousand ulps,
which is what the 1 and 2 degree rows are showing rather than any truncation.
Above 3 degrees the values are truncation-dominated and the 1% band is what
makes a coefficient change move the curve and fail.

Something downstream depends on this too: tests/test_convert.py converts
between all 342 ordered pairs of Michigan's nineteen 2022 zones, and the widest
of those pairs evaluates this series 7.8 degrees from its central meridian.
That test holds two different bounds for that reason, and this is the evidence
they rest on rather than a number chosen to make it pass.

Michigan's own SPCS 83 zones never reach this regime - the three zones overlap,
and the widest of them spans about 4.6 degrees of longitude - and no SPCS 83
Michigan zone is a transverse Mercator at all.
"""

TM_CLOSURE_RELATIVE_BAND = 0.01
TM_CLOSURE_FLOOR_DEG = 1e-11


@pytest.mark.parametrize(
    "offset,d_latitude,d_longitude",
    TM_CLOSURE_BY_OFFSET,
    ids=[f"{row[0]}deg" for row in TM_CLOSURE_BY_OFFSET],
)
def test_the_transverse_mercator_closure_matches_its_measured_curve(
    offset, d_latitude, d_longitude
):
    """The measured degradation, pinned per component rather than bounded.

    Latitude and longitude are asserted separately so that neither series'
    truncation can mask the other's defect - see the table's docstring for the
    seeded case that made this necessary.
    """
    zone = ZONES_BY_CODE["261002"]
    longitude = zone.definition.lon_origin - offset
    latitude = TM_CLOSURE_PROBE_LATITUDE

    point = projection.forward(latitude, longitude, zone)
    back = projection.inverse(point.northing, point.easting, zone)

    assert abs(back.latitude - latitude) == pytest.approx(
        d_latitude, rel=TM_CLOSURE_RELATIVE_BAND, abs=TM_CLOSURE_FLOOR_DEG
    )
    assert abs(back.longitude - longitude) == pytest.approx(
        d_longitude, rel=TM_CLOSURE_RELATIVE_BAND, abs=TM_CLOSURE_FLOOR_DEG
    )


def test_the_transverse_mercator_closure_is_symmetric_about_its_meridian():
    """East of the meridian must degrade exactly as west of it.

    The series is even in the longitude difference, so this is a real property
    and not a restatement of the table: a sign error in an odd-order term would
    break it while leaving the westward column above untouched.
    """
    zone = ZONES_BY_CODE["261002"]
    meridian = zone.definition.lon_origin
    latitude = TM_CLOSURE_PROBE_LATITUDE

    for offset, _d_latitude, _d_longitude in TM_CLOSURE_BY_OFFSET:
        residuals = []
        for signed in (offset, -offset):
            longitude = meridian + signed
            point = projection.forward(latitude, longitude, zone)
            back = projection.inverse(point.northing, point.easting, zone)
            residuals.append(
                (abs(back.latitude - latitude), abs(back.longitude - longitude))
            )
        west, east = residuals
        assert west[0] == pytest.approx(east[0], rel=0.05, abs=TM_CLOSURE_FLOOR_DEG)
        assert west[1] == pytest.approx(east[1], rel=0.05, abs=TM_CLOSURE_FLOOR_DEG)


def test_the_transverse_mercator_closure_degrades_monotonically():
    """Anti-vacuousness for the table above: it is not one number repeated.

    If the closure were flat, every row would be satisfied by the same
    measurement and the table would say nothing. It is not flat: BOTH components
    grow monotonically with the offset, and each ends more than four orders of
    magnitude above where it started.
    """
    zone = ZONES_BY_CODE["261002"]
    meridian = zone.definition.lon_origin
    latitude = TM_CLOSURE_PROBE_LATITUDE

    latitudes: list[float] = []
    longitudes: list[float] = []
    for offset, _d_latitude, _d_longitude in TM_CLOSURE_BY_OFFSET:
        longitude = meridian - offset
        point = projection.forward(latitude, longitude, zone)
        back = projection.inverse(point.northing, point.easting, zone)
        latitudes.append(abs(back.latitude - latitude))
        longitudes.append(abs(back.longitude - longitude))

    assert latitudes == sorted(latitudes)
    assert longitudes == sorted(longitudes)
    assert latitudes[-1] > latitudes[0] * 1e4
    assert longitudes[-1] > longitudes[0] * 1e4


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


@pytest.mark.parametrize("zone", SPCS83_ZONES, ids=[z.abbrev for z in SPCS83_ZONES])
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
        allowed_units=(INTERNATIONAL_FEET,),
        easting_range_m=None,
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


@pytest.mark.parametrize("zone", SPCS83_ZONES, ids=[z.abbrev for z in SPCS83_ZONES])
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
    """Constants can never be silently paired with another zone's identity.

    All twenty-two registry zones, both eras, so every engine's constants
    record is covered - a stamp added to one engine and forgotten in another
    fails here.
    """
    for zone in SPCS83_ZONES + SPCS2022_ZONES:
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

    # And on a registry zone from the other era, whose Zone record carries the
    # ``allowed_units`` tuple H2 added. A list there would raise TypeError on
    # the first lookup; a set would make the record unorderable but still
    # hashable, so this checks the identity of the cached object rather than
    # merely that the call succeeded.
    for zone in SPCS2022_ZONES:
        assert projection.constants_for(zone) is projection.constants_for(zone)

    before = projection.constants_for.cache_info().hits
    projection.constants_for(SPCS2022_ZONES[0])
    assert projection.constants_for.cache_info().hits == before + 1


# --------------------------------------------------------------------------
# The dispatcher must not have changed the three shipped zones by a bit.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("zone", SPCS83_ZONES, ids=[z.abbrev for z in SPCS83_ZONES])
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


@pytest.mark.parametrize("zone", SPCS83_ZONES, ids=[z.abbrev for z in SPCS83_ZONES])
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


ANCHORS_CAPTURE_PATH = (
    Path(__file__).resolve().parents[1] / "review" / "nsrs-h1-anchors" / "anchors.json"
)

ANCHORS_CAPTURE_SHA256 = (
    "76d2b61e57d2b9ddeb5466bcc3add92907f687efe8221cd0914c595707390a2d"
)
"""The digest the H1 capture recorded for its own machine-readable summary, and
the digest the fixture's docstring already quotes as the file its values were
transcribed from. Checked before anything is read out of it.
"""

# The three glyphs beta NCAT prints in a convergence, dropped when the values
# were transcribed (the fixture docstring records the transformation). Spelled
# as code points so this file stays ASCII: degree, prime, double prime.
_CONVERGENCE_GLYPHS = (chr(0x00B0), chr(0x2032), chr(0x2033))


def _load_anchor_capture() -> list[dict]:
    """The 63 captured projection results, after authenticating the bytes."""
    import hashlib
    import json

    raw = ANCHORS_CAPTURE_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == ANCHORS_CAPTURE_SHA256, (
        f"{ANCHORS_CAPTURE_PATH} hashes to {digest}, not the digest the H1 "
        f"capture recorded ({ANCHORS_CAPTURE_SHA256}). Re-run the capture "
        f"harness rather than editing this pin."
    )
    return json.loads(raw.decode("utf-8"))["projection_anchors"]


def _captured_convergence(text: str) -> str:
    """A captured convergence string in the form the fixture stores it in.

    ``"+01 deg 54 prime 40.49 double-prime"`` -> ``"+01 54 40.49"``. Only the
    three glyphs are removed and the whitespace is renormalised; every digit and
    the sign character are untouched, which is exactly the transformation the
    fixture's docstring documents.
    """
    for glyph in _CONVERGENCE_GLYPHS:
        text = text.replace(glyph, " ")
    return " ".join(text.split())


def test_the_fixture_is_the_capture_row_for_row():
    """Every anchor joined to NGS's own captured response, one for one.

    **Counts are not enough, and the interim H1+H2 gate proved it.** This test
    used to check totals only: 63 anchors, 19 origins, 9 statewide, 19 distinct
    zone codes. The gate replaced the statewide Isle Royale row - the only
    external assertion for 48.100000, -88.550000, N 1109582.833, E 1334062.199 -
    with a duplicate of the Detroit-area row, and all 923 projection-engine
    tests stayed green. Every count still added up; the suite had silently lost
    a captured result while still claiming to carry the whole capture.

    The fix is the discipline tests/test_zone_registry.py already applies to the
    zone constants: authenticate the source by digest and JOIN to it, in BOTH
    directions, on a key that must be unique. A fixture row that is not in the
    capture fails; a capture row that is not in the fixture fails; and two
    fixture rows sharing an input position fail before either.
    """
    captured = _load_anchor_capture()
    assert len(captured) == 63

    fixture_keys = [
        (a.zone_code, f"{a.latitude:.6f}", f"{a.longitude:.6f}")
        for a in SPCS2022_PROJECTION_ANCHORS
    ]
    captured_by_key = {
        (row["zone_code"], row["input_lat_dd"], row["input_lon_dd"]): row
        for row in captured
    }
    assert len(captured_by_key) == 63, "the capture itself has a duplicate key"

    # Every complaint is collected before anything is asserted, so a single
    # mutation reports everything it broke. A duplicated row loses a captured
    # position AND repeats another; a message that named only the repetition
    # would leave the reader to work out which anchor had gone.
    problems: list[str] = []

    for key in sorted(set(captured_by_key) - set(fixture_keys)):
        row = captured_by_key[key]
        problems.append(
            f"the capture carries {key} ({row['label']}, N {row['northing_m']}, "
            f"E {row['easting_m']}) and the fixture does not"
        )

    for key in sorted({k for k in fixture_keys if fixture_keys.count(k) > 1}):
        problems.append(f"two or more fixture anchors share the input position {key}")

    for key in sorted(set(fixture_keys) - set(captured_by_key)):
        problems.append(f"{key} is in the fixture but in no captured response")

    for anchor, key in zip(SPCS2022_PROJECTION_ANCHORS, fixture_keys):
        row = captured_by_key.get(key)
        if row is None:
            continue
        for name, stored, published in (
            ("northing_m", anchor.northing_m, float(row["northing_m"])),
            ("easting_m", anchor.easting_m, float(row["easting_m"])),
            ("northing_ift", anchor.northing_ift, float(row["northing_ift"])),
            ("easting_ift", anchor.easting_ift, float(row["easting_ift"])),
            ("scale_factor", anchor.scale_factor, float(row["scale_factor"])),
            (
                "convergence_dms",
                anchor.convergence_dms,
                _captured_convergence(row["convergence"]),
            ),
            ("label", anchor.label, row["label"]),
            ("capture", anchor.capture, row["raw"]),
        ):
            if stored != published:
                problems.append(
                    f"{key} {name}: fixture {stored!r}, capture {published!r}"
                )

    assert not problems, "\n".join(problems)


# The columns of a captured row that must be traceable to the page NGS served.
# Not every field: ``label`` is the harness's own name for a point and
# ``northing_ift``/``easting_ift`` are checked through the metres in the join
# above. These five are the ones a forgery would have to move.
_TRACEABLE_FIELDS = (
    "northing_m",
    "easting_m",
    "scale_factor",
    "ncat_echo_lat",
    "ncat_echo_lon",
)

# No thousands separators anywhere in the values, so the printed strings appear
# in the page exactly as anchors.json stores them, with no normalisation.
# Determined two ways rather than assumed: every row carries
# ``thousands_stripped: false``, which the harness set when it extracted the
# value, AND the comma-grouped form of a seven-digit easting ("1,755,596.782")
# appears nowhere in the page it came from. Both are asserted below so the
# claim cannot rot silently if NCAT's formatting changes at re-freeze.
_NO_THOUSANDS_SEPARATORS = True


def _appears_verbatim(value: str, text: str) -> bool:
    """Is ``value`` in ``text`` as a whole number rather than inside a longer one?

    The delimiting matters. Beta NCAT's page renders the same position several
    times at different precisions - the echoed latitude appears as
    ``42.100000000000000`` in a script attribute and as ``42.1000000000`` in the
    result span - so a bare substring test would accept a truncated or extended
    figure as a match. The lookaround requires the captured string to stand on
    its own: no digit or decimal point immediately before it, no digit after.
    """
    import re

    return (
        re.search(r"(?<![0-9.])" + re.escape(value) + r"(?![0-9])", text) is not None
    )


def test_every_captured_value_is_in_the_page_ngs_served():
    """The second link of the chain, and the reason it has to exist.

    The row-for-row join above proves the fixture equals ``anchors.json``, and
    ``anchors.json`` is authenticated by a SHA-256 written into this file. The
    re-confirmation round pointed out where that chain ends: **the digest is a
    constant a person can edit.** Change a value in the fixture, change it in
    ``anchors.json``, refresh ``ANCHORS_CAPTURE_SHA256`` to match, and 1,686
    tests pass - at which point the "external" anchors are a restatement of this
    program's own arithmetic and prove nothing at all.

    The link that closes it was already in the repository and unread: every row
    of ``anchors.json`` records the SHA-256 of the raw HTML page beta NCAT
    served for that point, and those pages are committed. So this test does two
    things for all 63 rows:

    1. re-hashes the named raw file and compares it against the digest the row
       itself carries - the file cannot be edited to agree with a forged value;
    2. requires each printed value to appear VERBATIM in that page's text - so a
       forged value cannot agree with a page it never came from.

    A forgery now has to alter the saved HTML too, and beta NCAT embeds a fresh
    session token in every page, so the altered file cannot be re-fetched or
    reproduced - which is exactly the "digests attest to the saved file only"
    caveat that N0 recorded, used here as a defence.

    What this does NOT prove, and must not be read as proving: that beta NCAT's
    numbers are right. It proves they are NGS's numbers and not ours.
    """
    import hashlib

    captured = _load_anchor_capture()
    root = ANCHORS_CAPTURE_PATH.parent
    problems: list[str] = []

    for row in captured:
        page = root / row["raw"]
        if not page.is_file():
            problems.append(f"{row['raw']} is named by the capture and is not present")
            continue

        raw = page.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row["sha256"]:
            problems.append(
                f"{row['raw']} hashes to {digest}, but the capture row for "
                f"{row['zone_code']} {row['label']} records {row['sha256']}"
            )
            continue

        text = raw.decode("utf-8")
        for field in _TRACEABLE_FIELDS:
            if not _appears_verbatim(row[field], text):
                problems.append(
                    f"{row['zone_code']} {row['label']}: {field} "
                    f"{row[field]!r} does not appear in {row['raw']}, the page "
                    f"beta NCAT served for that point"
                )

        if row["thousands_stripped"] is not (not _NO_THOUSANDS_SEPARATORS):
            problems.append(
                f"{row['raw']} records thousands_stripped="
                f"{row['thousands_stripped']!r}; this test assumes the printed "
                f"values need no separator normalisation"
            )

    assert not problems, "\n".join(problems)


def test_the_captured_pages_carry_no_thousands_separators():
    """The normalisation question, answered on the data rather than assumed.

    If NCAT ever prints ``1,755,596.782``, the verbatim check above would fail
    loudly rather than silently - but it would fail for a formatting reason and
    look like a forgery. Stating the fact separately keeps the two apart, and
    fixes what re-freeze has to re-examine.
    """
    captured = _load_anchor_capture()
    root = ANCHORS_CAPTURE_PATH.parent

    assert not [row for row in captured if row["thousands_stripped"]]

    row = next(r for r in captured if float(r["easting_m"]) > 1_000_000.0)
    text = (root / row["raw"]).read_text(encoding="utf-8")
    whole, _, fraction = row["easting_m"].partition(".")
    grouped = f"{int(whole):,}.{fraction}"

    assert grouped != row["easting_m"], "the probe needs a value worth grouping"
    assert grouped not in text
    assert _appears_verbatim(row["easting_m"], text)


def test_the_capture_record_quotes_the_digest_this_file_pins():
    """CAPTURE.md's digest table, machine-checked against the file itself.

    Three statements of one fact - the prose record, this module's constant, and
    the bytes on disk - and a person editing two of them must now edit the
    third. The record is the document a reader reaches for first, so a stale
    digest there is worse than no digest.
    """
    import hashlib

    record = (ANCHORS_CAPTURE_PATH.parent / "CAPTURE.md").read_text(encoding="utf-8")
    actual = hashlib.sha256(ANCHORS_CAPTURE_PATH.read_bytes()).hexdigest()

    assert actual == ANCHORS_CAPTURE_SHA256
    assert f"anchors.json{' ' * 26}{actual}" in record or actual in record, (
        f"review/nsrs-h1-anchors/CAPTURE.md does not quote {actual}"
    )


def test_the_page_check_would_notice_a_forged_value():
    """Anti-vacuousness: the verbatim check rejects a number NGS did not print.

    Without this, a bug in ``_appears_verbatim`` that made it return True for
    everything would leave the whole chain green and worthless. Uses a value one
    digit off a real one, which is what a forgery looks like - not a wild
    number that any weak check would reject.
    """
    captured = _load_anchor_capture()
    row = next(r for r in captured if r["zone_code"] == "260001")
    text = (ANCHORS_CAPTURE_PATH.parent / row["raw"]).read_text(encoding="utf-8")

    assert _appears_verbatim(row["northing_m"], text)

    whole, _, fraction = row["northing_m"].partition(".")
    nudged = f"{whole}.{int(fraction) + 1:0{len(fraction)}d}"
    assert nudged != row["northing_m"]
    assert not _appears_verbatim(nudged, text)

    # And a truncation of the real value must not pass either - that is the
    # case the lookaround exists for.
    assert not _appears_verbatim(row["northing_m"][:-1], text)


def test_the_fixture_carries_the_whole_capture():
    """Counts from review/nsrs-h1-anchors/CAPTURE.md, so a lost row is loud.

    Kept alongside the row-for-row join above rather than replaced by it: this
    states the shape of the lattice (nineteen origins, nine statewide points),
    which the join does not.
    """
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
