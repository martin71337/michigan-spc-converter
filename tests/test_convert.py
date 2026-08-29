"""The conversion pipeline, frames, and the seams that keep it extensible."""

from __future__ import annotations

import inspect
import math

import pytest

from michspc.spc.convert import (
    PointConversion,
    WarningCode,
    convert_point,
    easting_looks_wrong_for_zone,
    from_geodetic,
    project_point,
    to_geodetic,
)
from michspc.spc.frames import (
    ALL_FRAMES,
    FRAME_TRANSFORMATIONS,
    NAD83_2011,
    NATRF2022,
    REQUIRED_FRAME_PAIRS,
    WGS84,
    FrameMismatchError,
    FrameNotUsableError,
    FrameStatus,
    FrameTransformation,
    FrameTransformationUnavailableError,
    ReferenceFrame,
    frame_by_code,
    require_frame_path,
)
from michspc.spc.units import INTERNATIONAL_FEET
from michspc.spc.zones import (
    ALL_ZONES,
    SPCS2022_ZONES,
    SPCS83_ZONES,
    MI_CENTRAL,
    MI_NORTH,
    MI_SOUTH,
)
from tests.fixtures.ncat_anchors import NCAT_ANCHORS
from tests.fixtures.spcs2022_engine_anchors import (
    SPCS2022_PRINTED,
    SPCS2022_PROJECTION_ANCHORS,
)


def _ordered_pairs(zones):
    return [
        (source, target)
        for source in zones
        for target in zones
        if source is not target
    ]


ZONE_PAIRS = _ordered_pairs(SPCS83_ZONES)
PAIR_IDS = [f"{s.abbrev}->{t.abbrev}" for s, t in ZONE_PAIRS]

SPCS2022_PAIRS = _ordered_pairs(SPCS2022_ZONES)
SPCS2022_PAIR_IDS = [f"{s.abbrev}->{t.abbrev}" for s, t in SPCS2022_PAIRS]

CROSS_ERA_PAIRS = [
    (source, target)
    for source in ALL_ZONES
    for target in ALL_ZONES
    if source.frame is not target.frame
]
"""Every ordered pair whose two zones are in different reference frames.

Six of the twenty-two zones' 462 ordered pairs are within SPCS 83, 342 within
SPCS2022, and the remaining 114 cross the eras. Those 114 must REFUSE today:
NAD83(2011) and NATRF2022 differ by one to two metres over North America, and
no transformation between them is implemented (H3). This is honest behaviour,
not a gap being papered over, and it is pinned below so that when H3 lands the
change is a deliberate edit to a test that says what it is.
"""


# --------------------------------------------------------------------------
# Frames: the refusal that prevents a silent metre-scale error.
# --------------------------------------------------------------------------


def test_same_frame_returns_that_frames_identity_record():
    """SUPERSEDES ``test_same_frame_is_allowed`` (docs/DESIGN.md #62).

    Same call, one gate later: ``require_same_frame`` returned nothing and is
    deleted, and ``require_frame_path`` returns the registry record that says
    what was done. The property being pinned is unchanged - a job within one
    frame must not be refused - and the record is now checked as well, because
    a gate that returns a path can be asked which path it returned.

    Both usable frames are pinned, not only NAD 83: NATRF2022 became usable at
    #62, and a job entirely within it (the nineteen SPCS2022 zones) must run.
    """
    for frame in (NAD83_2011, NATRF2022):
        path = require_frame_path(frame, frame)
        assert path.is_identity
        assert path.source is frame and path.target is frame
        assert frame.code in path.direction_statement


def test_crossing_frames_is_refused_loudly():
    """The single most important safety property (docs/DESIGN.md section 6).

    SUPERSEDES the ``require_same_frame`` version of this test (#62). The same
    concrete call, now expecting the narrower
    ``FrameTransformationUnavailableError`` - which is a ``FrameMismatchError``,
    so every existing catch site still catches it.

    The refusal must name both frames and say why, not merely fail, and the
    "why" is now a fact about NGS rather than about this program's schedule:
    NGS has not published the transformation
    (docs/DEFERRED-NATRF2022-BRIDGE.md). Both facts are pinned because both are
    what a surveyor needs in order to decide what to do next.
    """
    with pytest.raises(FrameTransformationUnavailableError) as caught:
        require_frame_path(NAD83_2011, NATRF2022)

    message = str(caught.value)
    assert "NAD83(2011)" in message
    assert "NATRF2022" in message
    assert "no transformation between these two" in message
    # The stake, in the units the record uses. A metre-scale error that looks
    # ordinary is the whole reason this refusal exists.
    assert "one to two metres" in message
    # Whose gap this is. Without this sentence a reader would reasonably read
    # the refusal as "MCX has not got round to it".
    assert "NGS has not published" in message
    assert "DEFERRED-NATRF2022-BRIDGE.md" in message
    # And the exits, both of them.
    assert "Convert within a single frame" in message
    assert "when NGS publishes" in message


def test_the_refusal_is_still_catchable_as_the_base_class():
    """Narrowing the exception must not break any existing catch site.

    ``FrameMismatchError`` is what ``job.run``'s callers, the GUI and the older
    pins name. The two new subclasses are refinements of it, not replacements,
    and a caller that catches the base must keep catching both.
    """
    with pytest.raises(FrameMismatchError):
        require_frame_path(NAD83_2011, NATRF2022)
    with pytest.raises(FrameMismatchError):
        require_frame_path(WGS84, NAD83_2011)


def test_frames_are_compared_by_code_not_identity():
    """A frame reconstructed from data must still be recognised as the same one.

    Otherwise a future registry that rebuilds frame records on load would start
    refusing perfectly ordinary same-frame conversions.

    SUPERSEDED CONSTRUCTION (#62): the synthetic record now has to state a
    status, because ``status`` is a required field with no default. It states
    the WRONG one deliberately - a rebuilt record claiming NAD 83 is unusable -
    and the call must still succeed, because ``_canonical`` resolves by code to
    the registry's own record. A rebuilt record may not grant itself a status,
    and it may not take one away either.
    """
    duplicate = ReferenceFrame(
        code="NAD83(2011)",
        name="rebuilt from data",
        ellipsoid_name="GRS 80",
        citation="synthetic",
        status=FrameStatus.DECLARED_NOT_USABLE,
    )
    path = require_frame_path(NAD83_2011, duplicate)  # must not raise

    assert path is FRAME_TRANSFORMATIONS[(NAD83_2011, NAD83_2011)]


def test_a_frame_that_is_not_usable_is_refused_before_the_pair_is_looked_up():
    """WGS 84: the live counterexample for ``FrameNotUsableError`` (#62).

    The ORDER is the point, and it is pinned rather than left to reading the
    function. A frame this program cannot carry must be named as such - "WGS 84
    is not a frame this program can carry" - and not reported as a missing
    transformation, which would tell a user that one might be published for it
    one day. Nothing in this program produces a WGS 84 coordinate, and no
    transformation from it is registered.

    Why WGS 84 at all: docs/DESIGN.md amendment #58. A handheld receiver's
    WGS 84 position pastes into a latitude/longitude field cleanly and converts
    to something plausible and wrong, and the frames are a metre or more apart
    in CONUS.
    """
    with pytest.raises(FrameNotUsableError) as caught:
        require_frame_path(WGS84, NAD83_2011)

    message = str(caught.value)
    assert "WGS84" in message
    assert "not usable" in message
    # #58's reason, carried on the record's own citation and quoted here.
    assert "metre or more apart in CONUS" in message
    # It names what CAN be used, rather than leaving the user to guess.
    assert "NAD83(2011)" in message and "NATRF2022" in message

    # The other end, and both ends at once: same class, same ordering.
    with pytest.raises(FrameNotUsableError):
        require_frame_path(NATRF2022, WGS84)
    with pytest.raises(FrameNotUsableError):
        require_frame_path(WGS84, WGS84)


def test_an_unusable_frame_has_no_identity_of_its_own():
    """The second lock on WGS 84, behind the usability check.

    Deliberate registry design: an unusable frame gets NO registered path, not
    even an identity. If the usability check above were ever deleted, a WGS 84
    to WGS 84 job would still have to get past a missing registry entry rather
    than quietly succeeding as an identity - which would let a WGS 84
    coordinate through this program labelled as converted.
    """
    assert ("WGS84", "WGS84") not in {
        (source.code, target.code) for source, target in FRAME_TRANSFORMATIONS
    }
    assert not WGS84.is_usable


def test_every_usable_frame_has_its_identity_and_nothing_else_is_registered():
    """Completeness in both directions - the pin that says what H3 shipped.

    Every USABLE frame must carry its own identity, or a legitimate job within
    that frame would be refused. And NO non-identity path may exist, which is
    the half that matters for the tier: this package deliberately ships the
    frames restructure WITHOUT the NAD83(2011) <-> NATRF2022 bridge
    (docs/DESIGN.md #62, docs/DEFERRED-NATRF2022-BRIDGE.md), and a
    transformation added without its anchors, its gate and its amendment would
    move boundaries. It cannot arrive here silently.
    """
    usable = [frame for frame in ALL_FRAMES if frame.is_usable]
    assert usable == [NAD83_2011, NATRF2022]

    for frame in usable:
        assert (frame, frame) in FRAME_TRANSFORMATIONS

    for (source, target), path in FRAME_TRANSFORMATIONS.items():
        assert source.code == target.code, (
            f"{source.code} -> {target.code} is a non-identity path. Adding "
            f"one is DESIGN.md #62's deferred work and needs its own amendment."
        )
        assert path.is_identity


def test_the_registry_keeps_every_pair_it_is_required_to_keep():
    """DESIGN.md #32's append-only guarantee, driven directly.

    The import-time check runs the same comparison; this drives it as data so
    that a dropped record is a named failure rather than an import error whose
    traceback points at the module.
    """
    registered = {
        (source.code, target.code) for source, target in FRAME_TRANSFORMATIONS
    }
    missing = REQUIRED_FRAME_PAIRS - registered
    assert not missing, f"the registry lost required pairs: {sorted(missing)}"


def test_the_import_time_check_refuses_a_registry_that_lost_a_pair():
    """The guard itself, exercised rather than trusted.

    Called with the module's own private check after removing a pair from what
    it compares against is not possible from outside, so the pair set is what
    is perturbed: a required pair the registry does not carry must raise, with
    the pair named and #32 cited.
    """
    from michspc.spc import frames as frames_module

    original = frames_module.REQUIRED_FRAME_PAIRS
    try:
        frames_module.REQUIRED_FRAME_PAIRS = frozenset(
            original | {("NAD83(2011)", "NATRF2022")}
        )
        with pytest.raises(FrameMismatchError) as caught:
            frames_module._check_registry_keeps_every_required_pair()
    finally:
        frames_module.REQUIRED_FRAME_PAIRS = original

    message = str(caught.value)
    assert "NAD83(2011) -> NATRF2022" in message
    assert "#32" in message

    # And the real registry still passes it.
    frames_module._check_registry_keeps_every_required_pair()


def test_require_frame_path_refuses_a_record_that_is_not_a_frame():
    """The #11-finding-1 class, closed on this gate too.

    Every record in this core carries ``code``, ``name`` and ``citation``, so a
    ``Zone``, a ``VerticalDatum`` and a ``LinearUnit`` all duck-type through
    the code lookup and would only fail later on ``is_usable`` - as an
    ``AttributeError``, which walks straight through the
    ``except FrameMismatchError`` callers write. Passing ``source_zone`` where
    ``source_zone.frame`` was meant is one character.
    """
    from michspc.spc.vertical import NAVD88

    impostors = [
        (MI_SOUTH, "a zone"),
        (NAVD88, "a vertical datum"),
        (INTERNATIONAL_FEET, "a linear unit"),
    ]
    for impostor, what in impostors:
        with pytest.raises(TypeError, match="ReferenceFrame") as caught:
            require_frame_path(impostor, NAD83_2011)  # type: ignore[arg-type]
        assert type(impostor).__name__ in str(caught.value), what

        with pytest.raises(TypeError, match="ReferenceFrame"):
            require_frame_path(NAD83_2011, impostor)  # type: ignore[arg-type]


def test_a_frame_transformation_between_two_different_frames_will_not_construct():
    """The registry cannot grow a silent pass-through.

    A record with no parameters whose two frames differ would leave a position
    untouched while relabelling its frame - one to two metres, invisible in the
    numbers. It refuses at construction, so the mistake cannot reach the
    registry at all.
    """
    with pytest.raises(ValueError, match="one to two metres"):
        FrameTransformation(
            source=NAD83_2011, target=NATRF2022, citation="wishful thinking"
        )


def test_a_frame_transformation_must_carry_a_citation():
    """Every record must be able to say on whose authority it acts."""
    with pytest.raises(ValueError, match="citation"):
        FrameTransformation(source=NAD83_2011, target=NAD83_2011, citation="   ")


def test_all_frames_is_in_declaration_order():
    """The order an interface offers (H6's dropdown source), pinned as a fact.

    ``ALL_FRAMES`` is the source the geodetic selections are built from, so its
    order is user-visible rather than an accident of iteration - the property
    ``Zone.allowed_units`` and ``ALL_GEOID_MODELS`` already carry. The unusable
    member is IN the tuple, as NAPGD2022 is in ``ALL_VERTICAL_DATUMS``;
    consumers that offer a choice filter on ``is_usable``.
    """
    assert ALL_FRAMES == (NAD83_2011, NATRF2022, WGS84)
    assert [frame.code for frame in ALL_FRAMES] == [
        "NAD83(2011)",
        "NATRF2022",
        "WGS84",
    ]
    assert [frame.is_usable for frame in ALL_FRAMES] == [True, True, False]


def test_frames_are_looked_up_by_code_and_an_unknown_one_is_refused():
    """The contract ``zone_by_code`` and ``vertical_datum_by_code`` share."""
    for frame in ALL_FRAMES:
        assert frame_by_code(frame.code) is frame
    assert frame_by_code("  NAD83(2011)  ") is NAD83_2011

    with pytest.raises(KeyError) as caught:
        frame_by_code("NAD27")
    assert "NAD83(2011)" in str(caught.value)


def test_natrf2022s_citation_carries_its_authority_and_its_beta_provenance():
    """The frame that became usable at #62 must say what it is and where from.

    Two independent things, both required: the DEFINITIONAL authority (NOAA
    Technical Report NOS NGS 62, digest-pinned in the repository), and the
    fact that everything this program carries FOR the frame is pre-release -
    the ``NGS beta`` token the re-freeze mechanism looks for, with its capture
    date, exactly as every 2022 zone's citation carries it.
    """
    citation = NATRF2022.citation
    assert "NOAA Technical Report NOS NGS 62" in citation
    assert "b0d25a26d827daf6ff01c8ba8d96ee66b12ca200be335f72732f10794d2ae72a" in citation
    assert "NGS beta" in citation
    assert "2026-08-28" in citation
    # And it states, on the record itself, that the bridge is not registered.
    assert "NGS has not published one" in citation


def test_convert_point_refuses_to_cross_frames():
    """The refusal is wired into the pipeline, not merely available in a module."""
    import dataclasses

    future_zone = dataclasses.replace(MI_SOUTH, frame=NATRF2022)
    with pytest.raises(FrameMismatchError):
        convert_point(160000.0, 4000000.0, MI_NORTH, future_zone)


def test_a_natrf2022_geodetic_position_is_refused_by_project_point():
    """Interim review gate finding 1 (docs/DESIGN.md amendment #11), pinned.

    The reviewer's counterexample verbatim: treat 42.73250000, -84.55550000 as a
    NATRF2022 position and ask for Michigan South coordinates. Before the fix
    that returned

        N = 136920.027586723 m,  E = 3984537.119005890 m

    with no warning of any kind (numbers measured by the reviewer, quoted here
    as the record of the defect - not as an expected value). Those are the
    NAD 83 numbers. Nothing in them shows that the input was in a different
    frame, and docs/DESIGN.md section 6 puts the untransformed difference at one
    to two metres - a boundary-moving error on a sealed drawing.

    ``convert_point`` has refused this since the beginning, because both zones
    carry a frame. A bare latitude and longitude carries none, which is exactly
    why the frame has to be supplied and checked here too.
    """
    with pytest.raises(FrameMismatchError) as caught:
        project_point(42.73250000, -84.55550000, NATRF2022, MI_SOUTH)

    message = str(caught.value)
    # The refusal names both frames and what it would cost to ignore it.
    assert "NATRF2022" in message
    assert "NAD83(2011)" in message
    assert "one to two" in message


def test_the_same_position_in_the_zones_own_frame_still_converts():
    """The refusal must be about the frame, not about the position.

    Same latitude and longitude as the counterexample above, tagged NAD83(2011)
    - the frame every zone in the registry is in. It must convert, and land in
    Michigan South: eastings there sit near the zone's 4,000,000 m false
    easting (zones.py MI_SOUTH), and the point is inside the zone's area so it
    must raise no warning.
    """
    result = project_point(42.73250000, -84.55550000, NAD83_2011, MI_SOUTH)

    assert result.frame is NAD83_2011
    assert result.warnings == ()
    assert 3_900_000 < result.target_easting < 4_100_000
    assert math.isfinite(result.target_northing)


def test_a_natrf2022_position_projects_into_a_2022_zone_and_matches_ngs():
    """The other half of #62, and the half that is easy to lose.

    NATRF2022 is USABLE now: a geodetic position stated in it, projected into a
    zone defined on it, must CONVERT - and must land where NGS's own tool put
    it. If the frames restructure had made NATRF2022 unusable, or had failed to
    register its identity, this would refuse and nineteen zones would be
    unreachable from a latitude and longitude.

    The oracle is the frozen beta NCAT capture, not a number retyped here: the
    anchor is looked up from ``tests.fixtures.spcs2022_engine_anchors``, whose
    values came from NGS's own printed output (capture record:
    review/nsrs-h1-anchors/CAPTURE.md). Held to half of NCAT's printed
    quantization, ``SPCS2022_PRINTED["linear_m"]``, which is what the
    projection suite holds every anchor to.

    Zone 261008 (Michigan Grand Rapids), all three of its captured points,
    including the two off-origin ones - the origin alone would pass on a
    projection that only reproduced the false origin.
    """
    from michspc.spc.zones import zone_by_code

    zone = zone_by_code("261008")
    assert zone.frame is NATRF2022

    anchors = [a for a in SPCS2022_PROJECTION_ANCHORS if a.zone_code == "261008"]
    assert len(anchors) == 3

    for anchor in anchors:
        result = project_point(anchor.latitude, anchor.longitude, NATRF2022, zone)

        assert result.frame is NATRF2022
        assert result.target_northing == pytest.approx(
            anchor.northing_m, abs=SPCS2022_PRINTED["linear_m"]
        ), anchor.capture
        assert result.target_easting == pytest.approx(
            anchor.easting_m, abs=SPCS2022_PRINTED["linear_m"]
        ), anchor.capture


def test_project_point_will_not_accept_a_position_with_no_frame():
    """No default, and no way to fall through to one.

    The frame cannot be inferred from the numbers, so omitting it is a
    ``TypeError`` from the signature itself, and passing something that is not a
    frame is refused by name rather than being duck-typed into silence. A
    ``Zone`` is the likeliest wrong thing to pass, since it also has a ``.code``.
    """
    with pytest.raises(TypeError):
        project_point(42.7325, -84.5555, MI_SOUTH)  # type: ignore[call-arg]

    with pytest.raises(TypeError, match="reference frame"):
        project_point(42.7325, -84.5555, MI_SOUTH, MI_SOUTH)  # type: ignore[arg-type]


def test_every_conversion_record_is_tagged_with_its_frame():
    """docs/DESIGN.md section 4: the pivot is a position tagged with its frame.

    Both entry points must carry it, so a job record can state which frame the
    coordinates were interpreted as rather than leaving a reader to assume.
    """
    projected = project_point(42.7325, -84.5555, NAD83_2011, MI_SOUTH)
    converted = convert_point(160000.0, 4010000.0, MI_SOUTH, MI_CENTRAL)

    assert projected.frame is NAD83_2011
    assert converted.frame is MI_SOUTH.frame is NAD83_2011


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
            start = project_point(latitude, longitude, NAD83_2011, source)

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

    start = project_point(latitude, longitude, NAD83_2011, source)
    moved = convert_point(start.target_northing, start.target_easting, source, target)
    checked = convert_point(
        moved.target_northing, moved.target_easting, target, target
    )

    assert checked.latitude == pytest.approx(latitude, abs=1e-9)
    assert checked.longitude == pytest.approx(longitude, abs=1e-9)


# --------------------------------------------------------------------------
# SPCS2022, and the one thing that behaves differently from SPCS 83 here.
#
# Michigan's three SPCS 83 zones overlap, so any pair of them describes very
# nearly the same piece of ground and the round trip closes to floating-point
# noise everywhere. The nineteen 2022 zones do not: Bessemer's low-distortion
# zone and Detroit's are 7.8 degrees of longitude apart, and converting a
# Bessemer coordinate into Detroit's transverse Mercator evaluates the manual's
# section 3.2 series that far from its own central meridian.
#
# **That series is truncated, so its closure degrades with distance from the
# central meridian, and it does so steeply.** Measured on tm.py directly
# (tests/test_projection_engines.py has the table): a forward-and-back through
# one TM zone closes to 5e-7 m at 1 degree off the central meridian, 5.4e-5 m
# at 4 degrees, and 1.14e-2 m at 7.8 degrees. It is not a defect - every series
# term the manual publishes is kept - it is what the method is.
#
# So these two tests hold each POINT to one of two bounds, decided by whether
# the point lies inside the TARGET zone's own longitude extent. No constant is
# invented for the split: the zone's extent is the extent already on the record.
# Both regimes are exercised on every pair, and both bounds are measurements.
# --------------------------------------------------------------------------

SPCS2022_ROUND_TRIP_IN_ZONE_M = 1e-4
"""0.1 mm, the same bound the SPCS 83 pairs are held to, for a point inside the
target zone's own longitude extent. Measured worst across the whole matrix in
that regime: 3.08e-6 m - thirty times inside it."""

SPCS2022_ROUND_TRIP_OUT_OF_ZONE_M = 0.02
"""20 mm for a point OUTSIDE the target zone's extent, where the transverse
Mercator series truncation dominates. Measured worst across the whole matrix:
1.149e-2 m, at Bessemer's north-west corner converted into Detroit's zone, 7.8
degrees from that zone's central meridian.

This bound is deliberately looser than anything this program writes (0.001 ft
is 0.3 mm), and it is recorded rather than tuned: it is a **fact about
converting a coordinate into a low-distortion zone designed for somewhere
else**, and a surveyor doing that is outside every zone's design intent. What
protects a real job is the extent warning, which fires on exactly these points.
"""


def _lattice(zone, steps=5):
    """A steps x steps lattice over a zone's extent, corners included."""
    for i in range(steps):
        latitude = zone.lat_min + (zone.lat_max - zone.lat_min) * i / (steps - 1)
        for j in range(steps):
            longitude = zone.lon_min + (zone.lon_max - zone.lon_min) * j / (steps - 1)
            yield latitude, longitude


@pytest.mark.parametrize("source,target", SPCS2022_PAIRS, ids=SPCS2022_PAIR_IDS)
def test_spcs2022_zone_to_zone_round_trips(source, target):
    """A -> B -> A over all 342 ordered SPCS2022 pairs.

    Both ends are NATRF2022, so ``convert_point`` runs the whole pipeline -
    inverse in the source zone's projection, forward in the target's - across
    every combination of the oblique Mercator, the thirteen one-parallel
    Lamberts and the five transverse Mercators. Mixed-projection pairs are the
    point: an error in one engine's inverse that its own forward happens to
    undo would survive a same-projection round trip and die here.

    Tolerances per the two regimes above.
    """
    for latitude, longitude in _lattice(source):
        start = project_point(latitude, longitude, NATRF2022, source)

        there = convert_point(
            start.target_northing, start.target_easting, source, target
        )
        back = convert_point(
            there.target_northing, there.target_easting, target, source
        )

        error = max(
            abs(back.target_northing - start.target_northing),
            abs(back.target_easting - start.target_easting),
        )

        in_zone = target.lon_min <= longitude <= target.lon_max
        bound = (
            SPCS2022_ROUND_TRIP_IN_ZONE_M
            if in_zone
            else SPCS2022_ROUND_TRIP_OUT_OF_ZONE_M
        )
        assert error < bound, (
            f"{source.abbrev}->{target.abbrev} at {latitude}, {longitude} "
            f"({'inside' if in_zone else 'outside'} the target's extent) "
            f"round-trips off by {error:.3e} m"
        )


def test_the_strict_round_trip_regime_is_actually_reached():
    """Anti-vacuousness: the tight bound is not applied to nothing.

    If every 2022 pair fell outside the target's extent at every lattice point,
    the test above would be 342 applications of the loose bound and would say
    almost nothing. Count the points that land in the strict regime, and assert
    both regimes are populated.
    """
    strict = loose = 0
    for source, target in SPCS2022_PAIRS:
        for _latitude, longitude in _lattice(source):
            if target.lon_min <= longitude <= target.lon_max:
                strict += 1
            else:
                loose += 1

    assert strict > 0 and loose > 0
    # 342 pairs x 25 lattice points = 8,550 checks in all.
    assert strict + loose == 342 * 25


@pytest.mark.parametrize("source,target", SPCS2022_PAIRS, ids=SPCS2022_PAIR_IDS)
def test_spcs2022_zone_to_zone_preserves_the_geodetic_position(source, target):
    """Converting between 2022 zones must not move the point on the earth.

    One point per pair - the centre of the source zone's extent - recovered
    from the target coordinates. Same two regimes; measured worst 2.6e-11 deg
    inside the target's extent and 2.5e-8 deg (2.8 mm) outside it.
    """
    latitude = (source.lat_min + source.lat_max) / 2.0
    longitude = (source.lon_min + source.lon_max) / 2.0

    start = project_point(latitude, longitude, NATRF2022, source)
    moved = convert_point(start.target_northing, start.target_easting, source, target)
    checked = convert_point(
        moved.target_northing, moved.target_easting, target, target
    )

    in_zone = target.lon_min <= longitude <= target.lon_max
    bound = 1e-9 if in_zone else 1e-7

    assert checked.latitude == pytest.approx(latitude, abs=bound)
    assert checked.longitude == pytest.approx(longitude, abs=bound)


def test_every_cross_era_pair_refuses():
    """SPCS 83 to SPCS2022, and back, in either direction: refused, all 114.

    Not a limitation being hidden - it is the frame refusal doing exactly what
    DESIGN.md section 6 says it is for, and the alternative is a coordinate
    that looks entirely ordinary and is one to two metres out. The refusal
    names both frames.

    The count is asserted so this cannot pass by iterating an empty list, and
    so the arithmetic is on the record: 22 zones give 462 ordered pairs, of
    which 3x2 = 6 are SPCS 83 internal and 19x18 = 342 are SPCS2022 internal,
    leaving 2 x 3 x 19 = 114 crossing.
    """
    assert len(CROSS_ERA_PAIRS) == 114
    assert len(ZONE_PAIRS) == 6
    assert len(SPCS2022_PAIRS) == 342

    for source, target in CROSS_ERA_PAIRS:
        with pytest.raises(FrameMismatchError) as caught:
            convert_point(200000.0, source.definition.easting_origin, source, target)
        message = str(caught.value)
        assert source.frame.code in message
        assert target.frame.code in message


def test_a_geodetic_position_cannot_be_projected_into_the_other_era_s_zone():
    """The same rule on the geodetic-input door (``project_point``).

    An NAD 83 latitude and longitude projected with a 2022 zone's constants is
    the amendment #11 finding-1 error with a new zone list; and a NATRF2022
    position projected into an SPCS 83 zone is the same error reversed.
    """
    with pytest.raises(FrameMismatchError):
        project_point(43.0, -84.5, NAD83_2011, SPCS2022_ZONES[0])
    with pytest.raises(FrameMismatchError):
        project_point(43.0, -84.5, NATRF2022, MI_SOUTH)


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
    example of a conversion that lands outside the target zone's intended area.
    It must still succeed - the rigorous equations are exact there - and must
    say what it did.
    """
    lansing = project_point(42.7325, -84.5555, NAD83_2011, MI_SOUTH)
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

    # Lansing at 42.7325 N is south of Michigan Central's area, which starts at
    # 43.5 (zones.py MI_CENTRAL.lat_min), so the conversion says so rather than
    # presenting the coordinate without comment.
    codes = {w.code for w in result.warnings}
    assert WarningCode.OUTSIDE_ZONE_EXTENT in codes


# --------------------------------------------------------------------------
# Warnings: reported, never a refusal.
# --------------------------------------------------------------------------


def test_a_far_out_of_area_point_still_converts_and_says_so():
    """A point far from its target zone must convert, and must be flagged.

    48.4 N is Upper Peninsula latitude; asked for Michigan South coordinates it
    is more than four degrees north of that zone's area. The rigorous equations
    are exact there, so the conversion stands - but the surveyor is told, since
    distortion grows with distance from the zone and another zone almost
    certainly suits the point better.

    This is the only remaining warning class for an out-of-area point. The
    engine-disagreement warning that used to accompany it went with the
    polynomial method (docs/DESIGN.md amendment #14).
    """
    result = project_point(
        48.40, -84.3666666667, NAD83_2011, MI_SOUTH, context="point 1201"
    )

    codes = {w.code for w in result.warnings}
    assert WarningCode.OUTSIDE_ZONE_EXTENT in codes

    warning = next(
        w for w in result.warnings if w.code is WarningCode.OUTSIDE_ZONE_EXTENT
    )
    assert "point 1201" in warning.message
    assert "computed correctly" in warning.message

    # And the coordinate itself is real, not a placeholder.
    assert math.isfinite(result.target_northing)
    assert math.isfinite(result.target_easting)


def test_point_outside_the_target_zone_extent_warns():
    """A project straddling a boundary must still convert."""
    # Upper Peninsula latitude, asked for South zone coordinates.
    result = project_point(47.0, -87.0, NAD83_2011, MI_SOUTH, context="point 7")

    codes = {w.code for w in result.warnings}
    assert WarningCode.OUTSIDE_ZONE_EXTENT in codes
    assert math.isfinite(result.target_northing)
    assert math.isfinite(result.target_easting)


def test_a_point_well_inside_its_zone_raises_no_warnings():
    """The common case must be quiet, or the warnings mean nothing."""
    result = project_point(42.7325, -84.5555, NAD83_2011, MI_SOUTH)
    assert result.warnings == ()


# --------------------------------------------------------------------------
# The zone-magnitude guard: the most likely real-world mistake.
# --------------------------------------------------------------------------


def test_easting_guard_accepts_coordinates_from_the_right_zone():
    # SPCS 83 only, because +/- 150,000 m about the false easting is a
    # statement about the 1983 design's own 400 km window. The 2022 zones carry
    # NGS's published per-zone easting range instead, and are checked against
    # that file in tests/test_zone_registry.py.
    for zone in SPCS83_ZONES:
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
    lansing = project_point(42.7325, -84.5555, NAD83_2011, MI_SOUTH)
    assert not easting_looks_wrong_for_zone(lansing.target_easting, MI_SOUTH)
    assert easting_looks_wrong_for_zone(lansing.target_easting, MI_CENTRAL)


# --------------------------------------------------------------------------
# Result records.
# --------------------------------------------------------------------------


def test_conversion_results_are_frozen():
    result = project_point(42.7325, -84.5555, NAD83_2011, MI_SOUTH)
    with pytest.raises(Exception):
        result.target_northing = 0.0  # type: ignore[misc]


def test_geodetic_input_reports_the_zone_as_both_source_and_target():
    """No inverse step is performed, so there is no separate source zone.

    The record says so rather than leaving the field empty or inventing a
    source the user never chose.
    """
    result = project_point(42.7325, -84.5555, NAD83_2011, MI_SOUTH)
    assert result.source_zone is MI_SOUTH
    assert result.target_zone is MI_SOUTH
    assert result.source_northing == result.target_northing
    assert result.source_easting == result.target_easting


@pytest.mark.parametrize(
    "function", [to_geodetic, from_geodetic, convert_point, project_point]
)
def test_no_public_conversion_function_accepts_caller_supplied_constants(function):
    """The 4,231 km seam, pinned shut (docs/DESIGN.md amendment #11 finding 5).

    A ``constants=`` parameter lets a caller name one zone and hand in another
    zone's ``LambertConstants``. Nothing downstream compares the two, so the
    mispairing is silent. Measured:

        project_point(42.7325, -84.5555, NAD83_2011, MI_SOUTH,
                      target_constants=constants_for(MI_NORTH))
            -> -224978.383266 N, 8200514.325070 E  (meters)

    against the correct 136920.027587 N, 3984537.119006 E - the point moved
    4,231 km, with no refusal and no warning. The predecessor of this test
    passed matched constants and asserted the digits were identical, which
    exercised only the one pairing that is harmless and locked the seam in.

    ``constants_for`` is lru_cached, so deriving the constants inside each call
    costs nothing a caller could have saved by passing them.
    """
    parameters = inspect.signature(function).parameters

    assert not [name for name in parameters if "constants" in name], (
        f"{function.__name__} accepts {sorted(parameters)}; a constants "
        f"parameter has been re-introduced"
    )


def test_a_zone_is_the_only_way_to_name_a_projection():
    """The positive half of the pin: the zone alone still produces the answer.

    The reviewer's Lansing position in Michigan South, derived here from the
    section 3.12 and 3.13 equations at 50 significant decimal digits, from the
    Appendix A defining constants alone (phi_s = 42-06, phi_n = 43-40,
    phi_b = 41-30, lambda_0 = -84-22, N_b = 0, E_0 = 4,000,000 m):

        sin phi_0 = 0.68052925991183034786
        K         = 12061671.83848264505673 m
        R_b       =  7031167.29066513148358 m
        R         =  6894264.60365083245725 m
        gamma     = (-84.5555 + 84.3666...) sin phi_0 = -0.12850660858001729735 deg
        N = R_b + N_b - R cos gamma =  136920.02758672257815 m
        E = E_0 + R sin gamma       = 3984537.11900588955191 m

    Production agrees to 1.7e-10 m, so 1e-6 m is a loose bound on double
    arithmetic rather than a tolerance on the mathematics.
    """
    result = project_point(42.7325, -84.5555, NAD83_2011, MI_SOUTH)

    assert result.target_northing == pytest.approx(136920.027586722578, abs=1e-6)
    assert result.target_easting == pytest.approx(3984537.119005889552, abs=1e-6)


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
