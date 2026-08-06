"""The conversion pipeline, frames, and the seams that keep it extensible."""

from __future__ import annotations

import math

import pytest

from michspc.spc import agreement as ag
from michspc.spc.convert import (
    PointConversion,
    WarningCode,
    convert_point,
    easting_looks_wrong_for_zone,
    project_point,
)
from michspc.spc.frames import (
    NAD83_2011,
    NATRF2022,
    FrameMismatchError,
    ReferenceFrame,
    require_same_frame,
)
from michspc.spc.lambert import constants_for
from michspc.spc.units import INTERNATIONAL_FEET
from michspc.spc.zones import ALL_ZONES, MI_CENTRAL, MI_NORTH, MI_SOUTH
from tests.fixtures.ncat_anchors import NCAT_ANCHORS

ZONE_PAIRS = [
    (source, target)
    for source in ALL_ZONES
    for target in ALL_ZONES
    if source is not target
]
PAIR_IDS = [f"{s.abbrev}->{t.abbrev}" for s, t in ZONE_PAIRS]


# --------------------------------------------------------------------------
# Frames: the refusal that prevents a silent metre-scale error.
# --------------------------------------------------------------------------


def test_same_frame_is_allowed():
    require_same_frame(NAD83_2011, NAD83_2011)  # must not raise


def test_crossing_frames_is_refused_loudly():
    """The single most important safety property (docs/DESIGN.md section 6).

    The refusal must name both frames and say why, not merely fail.
    """
    with pytest.raises(FrameMismatchError) as caught:
        require_same_frame(NAD83_2011, NATRF2022)

    message = str(caught.value)
    assert "NAD83(2011)" in message
    assert "NATRF2022" in message
    assert "no datum transformation" in message
    assert "one to two meters" in message


def test_frames_are_compared_by_code_not_identity():
    """A frame reconstructed from data must still be recognised as the same one.

    Otherwise a future registry that rebuilds frame records on load would start
    refusing perfectly ordinary same-frame conversions.
    """
    duplicate = ReferenceFrame(
        code="NAD83(2011)",
        name="rebuilt from data",
        ellipsoid_name="GRS 80",
        citation="synthetic",
    )
    require_same_frame(NAD83_2011, duplicate)  # must not raise


def test_convert_point_refuses_to_cross_frames():
    """The refusal is wired into the pipeline, not merely available in a module."""
    import dataclasses

    future_zone = dataclasses.replace(MI_SOUTH, frame=NATRF2022)
    with pytest.raises(FrameMismatchError):
        convert_point(160000.0, 4000000.0, MI_NORTH, future_zone)


# --------------------------------------------------------------------------
# Zone to zone: the core operation.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", NCAT_ANCHORS, ids=lambda a: f"{a.zone_code}@{a.latitude}")
def test_conversion_recovers_the_geodetic_position_ngs_published(anchor):
    """The pivot of every conversion, checked against NGS's own coordinates.

    Feeding NCAT's northing and easting into the pipeline must recover the
    latitude and longitude NCAT was given. If the pivot is right, both halves of
    a zone-to-zone conversion are right.
    """
    from michspc.spc.zones import zone_by_code

    zone = zone_by_code(anchor.zone_code)
    result = convert_point(anchor.northing_m, anchor.easting_m, zone, zone)

    assert result.latitude == pytest.approx(anchor.latitude, abs=5e-8)
    assert result.longitude == pytest.approx(anchor.longitude, abs=5e-8)


@pytest.mark.parametrize("source,target", ZONE_PAIRS, ids=PAIR_IDS)
def test_zone_to_zone_round_trips(source, target):
    """A -> B -> A must return the original coordinate.

    Run over a lattice inside the SOURCE zone, so every point is somewhere a
    real file could plausibly contain. Tolerance is 0.1 mm, far below the
    0.001 ft (0.3 mm) the program writes, so a round-trip can never move a
    published coordinate.
    """
    worst = 0.0
    for i in range(7):
        latitude = source.lat_min + (source.lat_max - source.lat_min) * i / 6.0
        for j in range(7):
            longitude = source.lon_min + (source.lon_max - source.lon_min) * j / 6.0
            start = project_point(latitude, longitude, source)

            there = convert_point(
                start.target_northing, start.target_easting, source, target
            )
            back = convert_point(
                there.target_northing, there.target_easting, target, source
            )

            worst = max(
                worst,
                abs(back.target_northing - start.target_northing),
                abs(back.target_easting - start.target_easting),
            )

    assert worst < 1e-4, f"{source.abbrev}->{target.abbrev} round-trip off by {worst:.3e} m"


@pytest.mark.parametrize("source,target", ZONE_PAIRS, ids=PAIR_IDS)
def test_zone_to_zone_preserves_the_geodetic_position(source, target):
    """Converting zones must not move the point on the earth.

    Both zones describe the same physical location in the same reference frame,
    so the geodetic pivot recovered from the target coordinates must match the
    one used to produce them.
    """
    latitude = (source.lat_min + source.lat_max) / 2.0
    longitude = (source.lon_min + source.lon_max) / 2.0

    start = project_point(latitude, longitude, source)
    moved = convert_point(start.target_northing, start.target_easting, source, target)
    checked = convert_point(
        moved.target_northing, moved.target_easting, target, target
    )

    assert checked.latitude == pytest.approx(latitude, abs=1e-9)
    assert checked.longitude == pytest.approx(longitude, abs=1e-9)


def test_converting_a_zone_to_itself_is_the_identity():
    """The degenerate case must not drift."""
    northing, easting = 160000.0, 4010000.0
    result = convert_point(northing, easting, MI_SOUTH, MI_SOUTH)

    assert result.target_northing == pytest.approx(northing, abs=1e-6)
    assert result.target_easting == pytest.approx(easting, abs=1e-6)


def test_a_real_cross_zone_conversion_carries_its_evidence():
    """A worked example, hand-checkable against the manual.

    A point in Lansing, Michigan (roughly 42.73 N, 84.55 W) is in the South
    zone. Expressed in Central zone coordinates it must land near that zone's
    6,000,000 m false easting, west of the shared 84 22' central meridian, and
    therefore carry a NEGATIVE convergence in both zones.

    Lansing is well south of the Central zone, so this is also a realistic
    example of a conversion that lands outside the target zone's polynomial
    band. It must still succeed - the rigorous equations are exact there - and
    must say what it did.
    """
    lansing = project_point(42.7325, -84.5555, MI_SOUTH)
    result = convert_point(
        lansing.target_northing, lansing.target_easting, MI_SOUTH, MI_CENTRAL
    )

    # Both zones share the 84 22' central meridian, so the convergence has the
    # same sign in both, and is negative because the point is west of it.
    assert result.source_convergence < 0.0
    assert result.target_convergence < 0.0

    # Central zone eastings sit near 6,000,000 m; South zone near 4,000,000 m.
    assert 5_980_000 < result.target_easting < 6_000_000
    assert 3_980_000 < result.source_easting < 4_000_000

    # The pivot is unchanged by the conversion.
    assert result.latitude == pytest.approx(42.7325, abs=1e-9)
    assert result.longitude == pytest.approx(-84.5555, abs=1e-9)

    # The record carries the evidence, not just the answer. The source zone's
    # inverse was cross-checked cleanly, since Lansing is comfortably inside
    # Michigan South's band.
    assert result.inverse_agreement is not None
    assert result.inverse_agreement.within_tolerance

    # The target side is out of band, so the polynomial is unreliable there and
    # the conversion says so rather than pretending otherwise.
    assert not result.forward_agreement.within_tolerance
    codes = {w.code for w in result.warnings}
    assert WarningCode.ENGINE_DISAGREEMENT_OUT_OF_BAND in codes


# --------------------------------------------------------------------------
# Warnings: reported, never a refusal.
# --------------------------------------------------------------------------


def test_out_of_band_engine_disagreement_warns_rather_than_refusing():
    """Design log #5: the rigorous engine is right there, so the conversion stands.

    A point at 48.4 N expressed in Michigan South coordinates puts the South
    zone's polynomial 4.7 degrees outside its fitted band, where it is known to
    be wrong by metres. The conversion must still succeed, using the rigorous
    result, and must say so.
    """
    result = project_point(48.40, -84.3666666667, MI_SOUTH, context="point 1201")

    codes = {w.code for w in result.warnings}
    assert WarningCode.ENGINE_DISAGREEMENT_OUT_OF_BAND in codes

    warning = next(
        w for w in result.warnings
        if w.code is WarningCode.ENGINE_DISAGREEMENT_OUT_OF_BAND
    )
    assert "point 1201" in warning.message
    assert "rigorous Lambert equations are exact here and were used" in warning.message
    # The measured discrepancy is carried, not just the fact of it.
    assert "mm" in warning.message


def test_in_band_engine_disagreement_would_refuse():
    """The other half of design log #5: inside the band, disagreement is a defect.

    Constructed directly rather than provoked, because the two engines do in
    fact agree everywhere in band - which is the point. This checks the policy
    itself: an in-band disagreement raises rather than warns.
    """
    from michspc.spc.convert import _check_engines

    bad = ag.Agreement(northing_difference=0.05, easting_difference=0.0)
    in_band_latitude = (MI_SOUTH.lat_min + MI_SOUTH.lat_max) / 2.0

    with pytest.raises(ag.EngineDisagreementError, match="point 42"):
        _check_engines(MI_SOUTH, in_band_latitude, bad, "point 42")


def test_point_outside_the_target_zone_extent_warns():
    """A project straddling a boundary must still convert."""
    # Upper Peninsula latitude, asked for South zone coordinates.
    result = project_point(47.0, -87.0, MI_SOUTH, context="point 7")

    codes = {w.code for w in result.warnings}
    assert WarningCode.OUTSIDE_ZONE_EXTENT in codes
    assert math.isfinite(result.target_northing)
    assert math.isfinite(result.target_easting)


def test_a_point_well_inside_its_zone_raises_no_warnings():
    """The common case must be quiet, or the warnings mean nothing."""
    result = project_point(42.7325, -84.5555, MI_SOUTH)
    assert result.warnings == ()


# --------------------------------------------------------------------------
# The zone-magnitude guard: the most likely real-world mistake.
# --------------------------------------------------------------------------


def test_easting_guard_accepts_coordinates_from_the_right_zone():
    for zone in ALL_ZONES:
        easting = zone.definition.easting_origin + 150000.0
        assert not easting_looks_wrong_for_zone(easting, zone)
        assert not easting_looks_wrong_for_zone(
            zone.definition.easting_origin - 150000.0, zone
        )


def test_easting_guard_catches_a_file_from_the_wrong_zone():
    """Michigan's false eastings are 2,000,000 m apart precisely so this works.

    A South zone easting (near 4,000,000 m) offered as Central zone data (near
    6,000,000 m) is two million metres out of place and must be noticed.
    """
    south_easting = MI_SOUTH.definition.easting_origin + 10000.0
    assert easting_looks_wrong_for_zone(south_easting, MI_CENTRAL)
    assert easting_looks_wrong_for_zone(south_easting, MI_NORTH)


def test_easting_guard_works_on_a_real_converted_coordinate():
    """Not a synthetic number: a genuine Lansing point in each zone."""
    lansing = project_point(42.7325, -84.5555, MI_SOUTH)
    assert not easting_looks_wrong_for_zone(lansing.target_easting, MI_SOUTH)
    assert easting_looks_wrong_for_zone(lansing.target_easting, MI_CENTRAL)


# --------------------------------------------------------------------------
# Result records.
# --------------------------------------------------------------------------


def test_conversion_results_are_frozen():
    result = project_point(42.7325, -84.5555, MI_SOUTH)
    with pytest.raises(Exception):
        result.target_northing = 0.0  # type: ignore[misc]


def test_geodetic_input_has_no_inverse_agreement():
    """No inverse step was performed, so there is nothing to report about one.

    None rather than a fabricated zero-difference Agreement, which would claim
    a check happened that did not (docs/DESIGN.md section 1, never fabricate).
    """
    result = project_point(42.7325, -84.5555, MI_SOUTH)
    assert result.inverse_agreement is None
    assert isinstance(result.forward_agreement, ag.Agreement)


def test_passing_precomputed_constants_gives_identical_results():
    """The per-file optimisation must not change a single digit."""
    source_constants = constants_for(MI_SOUTH)
    target_constants = constants_for(MI_CENTRAL)

    plain = convert_point(160000.0, 4010000.0, MI_SOUTH, MI_CENTRAL)
    cached = convert_point(
        160000.0,
        4010000.0,
        MI_SOUTH,
        MI_CENTRAL,
        source_constants=source_constants,
        target_constants=target_constants,
    )

    assert cached.target_northing == plain.target_northing
    assert cached.target_easting == plain.target_easting
    assert cached.latitude == plain.latitude
    assert cached.longitude == plain.longitude


# --------------------------------------------------------------------------
# Units at the boundary.
# --------------------------------------------------------------------------


def test_international_and_us_survey_feet_differ_by_the_documented_2ppm():
    """Why the unit must be stated in every output file.

    At Michigan South's 4,000,000 m false easting the two foot definitions
    disagree by about 26 feet. Hand derivation:
        4,000,000 / 0.3048        = 13,123,359.58 international feet
        4,000,000 / (1200/3937)   = 13,123,333.33 US survey feet
        difference                =        26.25 feet
    """
    from michspc.spc.units import US_SURVEY_FEET

    meters = 4_000_000.0
    international = INTERNATIONAL_FEET.from_meters(meters)
    survey = US_SURVEY_FEET.from_meters(meters)

    assert international == pytest.approx(13_123_359.58, abs=0.01)
    assert survey == pytest.approx(13_123_333.33, abs=0.01)
    assert international - survey == pytest.approx(26.25, abs=0.01)


def test_unit_round_trip_is_exact_enough_to_publish():
    """meters -> unit -> meters must not move a coordinate."""
    from michspc.spc.units import ALL_UNITS

    for unit in ALL_UNITS:
        for meters in (0.0, 4_000_000.0, 166_681.657):
            assert unit.to_meters(unit.from_meters(meters)) == pytest.approx(
                meters, abs=1e-9
            )
