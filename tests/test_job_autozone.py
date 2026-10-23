"""Work package Z2: Auto zone in ``job.run`` (docs/PLAN-options-autozone.md).

What is pinned here, each against a value that does not come from the code
under test:

1. **The settings.** ``AUTO_ZONE`` is a typed singleton, legal only as the
   target of ``GEODETIC_TO_ZONE``, and requires ``auto_frame`` (the registry's
   NAD83(2011) or NATRF2022 record, by identity); a stray ``auto_frame`` is
   refused by name. Every refusal is pinned at its message.
2. **The frame rule (L2).** Every pairing of input frame and Auto frame that
   has no registered path is refused with ``frames.require_frame_path``'s OWN
   message - compared character for character, so the job cannot have grown a
   second, weaker check.
3. **The unit gate** checks the output unit against EVERY zone the Auto frame
   can choose, before the file is read.
4. **Per point.** The zone is NCAT's (the frozen Z0 anchors, both systems, in
   one mixed-zone file per system), the projected point is the fixed-zone
   job's point of that zone FIELD FOR FIELD (bit-identical, ``repr`` equal)
   except that an Auto point carries no OUTSIDE_ZONE_EXTENT warning; a file
   with ANY point in no county refuses the WHOLE job, naming every such
   point; and a WGS 84 position's zone is chosen at its NAD 83 pivot -
   including at a constructed point where the two positions straddle a zone
   line.
5. **The observation date source** (L10): stray refused, TODAY held to the
   LOCAL date (``today_local``), never the UTC one.
6. **The write guard's successors**: Z2's guard refused to write an Auto
   job; Z3 removed it, and an Auto job now writes (its outputs are pinned in
   tests/test_autozone_outputs.py).
"""

from __future__ import annotations

import copy
import dataclasses
import datetime
import pickle
from pathlib import Path

import pytest

from michspc import job
from michspc.fileio import exports, pnezd, report
from michspc.job import (
    AUTO_ZONE,
    AutoZoneUnplacedPointsError,
    AutoZone,
    Direction,
    JobSettings,
    LongitudeConvention,
    ObservationDateSource,
    VerticalMode,
    run,
)
from michspc.spc import autozone, convert
from michspc.spc.convert import WarningCode
from michspc.spc.autozone import (
    AutoZoneDataError,
    AutoZoneSystem,
    County,
    CountySet,
    zones_choosable,
)
from michspc.spc.frames import (
    ITRF2014,
    ITRF2020,
    NAD83_2011,
    NATRF2022,
    WGS84,
    WGS84_G1762,
    WGS84_G2139,
    WGS84_G2296,
    FrameNotUsableError,
    FrameTransformationUnavailableError,
    require_frame_path,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS, US_SURVEY_FEET
from michspc.spc.vertical import NAVD88
from michspc.spc.zones import (
    MI_CENTRAL,
    MI_NORTH,
    MI_SOUTH,
    SPCS83_ZONES,
    SPCS2022_ZONES,
    zone_by_code,
)
from tests import autozone_geometry as geo
from tests.fixtures.autozone_anchors import ANCHORS

FIVE = (WGS84_G1762, WGS84_G2139, WGS84_G2296, ITRF2014, ITRF2020)
DATE = datetime.date(2025, 6, 15)
NEG = LongitudeConvention.NEGATIVE_WEST


def settings(**fields) -> JobSettings:
    base = dict(
        input_path=None,
        output_directory=None,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=AUTO_ZONE,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=NEG,
        auto_frame=NAD83_2011,
    )
    base.update(fields)
    return JobSettings(**base)


def source(*rows: tuple) -> pnezd.PnezdFile:
    """A parsed PNEZD file from (id, latitude, longitude, elevation-or-None)."""
    lines = []
    for point_id, lat, lon, z in rows:
        lines.append(f"{point_id},{lat!r},{lon!r},{'' if z is None else repr(z)},D\n")
    return pnezd.parse_lines(lines)


EXTENT = WarningCode.OUTSIDE_ZONE_EXTENT


def _no_extent(warnings):
    return tuple(w for w in warnings if w.code is not EXTENT)


def assert_bit_identical(auto_point, fixed_point) -> bool:
    """The precise claim: every ConvertedPoint field identical - coordinates,
    factors, the whole conversion record - field for field and through repr
    (so -0.0 and the last bit both count), EXCEPT that the Auto point carries
    no OUTSIDE_ZONE_EXTENT warning, in ``warnings`` or in
    ``conversion.warnings``, where the fixed-zone point may (the lead's
    ruling on Z2 finding 6). Returns whether the fixed point had one, so a
    caller can prove the exception was exercised."""
    assert fixed_point.auto_zone is None
    assert not any(w.code is EXTENT for w in auto_point.warnings)
    assert not any(w.code is EXTENT for w in auto_point.conversion.warnings)
    expected = dataclasses.replace(
        fixed_point,
        conversion=dataclasses.replace(
            fixed_point.conversion,
            warnings=_no_extent(fixed_point.conversion.warnings),
        ),
        warnings=_no_extent(fixed_point.warnings),
    )
    for f in dataclasses.fields(type(auto_point)):
        if f.name == "auto_zone":
            continue
        a, b = getattr(auto_point, f.name), getattr(expected, f.name)
        assert a == b, f.name
        assert repr(a) == repr(b), f.name
    return len(fixed_point.warnings) != len(expected.warnings)


# --------------------------------------------------------------------------
# 1. The sentinel and the settings.
# --------------------------------------------------------------------------


def test_auto_zone_is_a_typed_singleton_and_neither_none_nor_a_zone():
    assert isinstance(AUTO_ZONE, AutoZone)
    assert AUTO_ZONE is not None
    assert not isinstance(AUTO_ZONE, type(MI_SOUTH))
    assert copy.copy(AUTO_ZONE) is AUTO_ZONE
    assert copy.deepcopy(AUTO_ZONE) is AUTO_ZONE
    assert pickle.loads(pickle.dumps(AUTO_ZONE)) is AUTO_ZONE
    assert repr(AUTO_ZONE) == "AUTO_ZONE"
    assert list(AutoZone) == [AUTO_ZONE]


def test_a_string_is_not_auto_zone():
    with pytest.raises(
        TypeError, match="JobSettings.target_zone must be a michspc.spc.zones.Zone"
    ) as caught:
        run(settings(target_zone="auto"), source((1, 43.0, -84.5, None)))
    assert "pass michspc.job.AUTO_ZONE (the object, not a string)" in str(caught.value)


def test_auto_zone_as_the_source_is_refused():
    with pytest.raises(ValueError) as caught:
        run(
            settings(
                direction=Direction.ZONE_TO_ZONE,
                source_zone=AUTO_ZONE,
                target_zone=MI_SOUTH,
                auto_frame=None,
                longitude_convention=None,
            ),
            source((1, 100.0, 200.0, None)),
        )
    assert str(caught.value) == (
        "JobSettings.source_zone was AUTO_ZONE. Auto chooses a zone from a "
        "latitude and longitude, so it can only be the TARGET of a "
        "geodetic-to-State Plane job: a northing and easting do not say "
        "which zone they are in - Michigan's zones overlap in grid "
        "coordinates - so the zone an input is in is never inferred. "
        "State the zone the coordinates are in."
    )


@pytest.mark.parametrize(
    "direction, source_zone, reason",
    [
        (
            Direction.ZONE_TO_ZONE,
            MI_SOUTH,
            "its input is State Plane coordinates, and Auto chooses a zone "
            "from a latitude and longitude only (docs/PLAN-options-autozone.md L1)",
        ),
        (
            Direction.ZONE_TO_GEODETIC,
            MI_SOUTH,
            "its output is a latitude and longitude, so no zone is projected into",
        ),
        (
            Direction.VERTICAL_ONLY,
            MI_SOUTH,
            "no output horizontal system exists in this mode, so no zone is "
            "projected into",
        ),
        (
            Direction.VERTICAL_ONLY,
            None,
            "no output horizontal system exists in this mode, so no zone is "
            "projected into",
        ),
        (
            Direction.GEODETIC_TO_GEODETIC,
            None,
            "its output is a latitude and longitude, so no zone is projected into",
        ),
    ],
)
def test_auto_zone_is_the_target_of_geodetic_to_zone_only(direction, source_zone, reason):
    with pytest.raises(ValueError) as caught:
        run(
            settings(
                direction=direction,
                source_zone=source_zone,
                vertical_mode=(
                    VerticalMode.VERTICAL
                    if direction is Direction.VERTICAL_ONLY
                    else VerticalMode.HORIZONTAL
                ),
            ),
            source((1, 43.0, -84.5, None)),
        )
    assert str(caught.value) == (
        f"A {direction.name} job was given target_zone=AUTO_ZONE, but Auto "
        f"zone is the output of a GEODETIC_TO_ZONE job only - it chooses each "
        f"point's zone from that point's latitude and longitude - and this "
        f"job {reason}. State the zone, or None where this direction has no "
        f"zone."
    )


def test_auto_zone_without_an_auto_frame_is_refused():
    with pytest.raises(ValueError) as caught:
        run(settings(auto_frame=None), source((1, 43.0, -84.5, None)))
    assert str(caught.value) == (
        "A job with target_zone=AUTO_ZONE needs auto_frame, the frame Auto "
        "chooses zones in: NAD83(2011), whose zones are the three SPCS 83 "
        "zones, or NATRF2022, whose zones are the eighteen SPCS2022 "
        "low-distortion zones. It has no default: the two systems put the "
        "same point in different zones with different coordinates."
    )


def test_a_stray_auto_frame_is_refused_by_name_beside_a_fixed_zone():
    with pytest.raises(ValueError) as caught:
        run(settings(target_zone=MI_SOUTH), source((1, 43.0, -84.5, None)))
    assert str(caught.value) == (
        "A GEODETIC_TO_ZONE job with target_zone=Michigan South (2113) was "
        "given auto_frame=NAD83(2011), which only an Auto job "
        "(target_zone=AUTO_ZONE) reads. No zone is chosen from a position in "
        "this job, so the frame would be one the job record could print and "
        "the conversion never used. Pass auto_frame=None."
    )


def test_a_stray_auto_frame_is_refused_by_name_where_there_is_no_target_zone():
    with pytest.raises(ValueError) as caught:
        run(
            settings(
                direction=Direction.ZONE_TO_GEODETIC,
                source_zone=MI_SOUTH,
                target_zone=None,
                auto_frame=NATRF2022,
            ),
            source((1, 100.0, 200.0, None)),
        )
    assert str(caught.value) == (
        "A ZONE_TO_GEODETIC job with target_zone=None was given "
        "auto_frame=NATRF2022, which only an Auto job (target_zone=AUTO_ZONE) "
        "reads. No zone is chosen from a position in this job, so the frame "
        "would be one the job record could print and the conversion never "
        "used. Pass auto_frame=None."
    )


def test_an_auto_frame_that_is_not_a_frame_is_a_type_error():
    with pytest.raises(TypeError) as caught:
        run(settings(auto_frame=MI_SOUTH), source((1, 43.0, -84.5, None)))
    assert str(caught.value).startswith(
        "JobSettings.auto_frame must be a michspc.spc.frames.ReferenceFrame - "
        "NAD83_2011 or NATRF2022; got Zone ("
    )


@pytest.mark.parametrize(
    "frame",
    [WGS84_G2296, dataclasses.replace(NAD83_2011), dataclasses.replace(NATRF2022)],
    ids=["wgs84", "nad83-copy", "natrf-copy"],
)
def test_an_auto_frame_must_be_the_registry_record_of_an_auto_system(frame):
    with pytest.raises(ValueError) as caught:
        run(settings(auto_frame=frame), source((1, 43.0, -84.5, None)))
    assert str(caught.value) == (
        f"{frame.code} is not a frame Auto chooses zones in. Auto chooses "
        f"among the SPCS 83 zones on NAD83(2011) or the SPCS2022 "
        f"low-distortion zones on NATRF2022; pass "
        f"michspc.spc.frames.NAD83_2011 or michspc.spc.frames.NATRF2022 - the "
        f"registry's own record, not a copy of it."
    )


def test_a_stray_source_zone_beside_auto_names_auto_in_its_message():
    with pytest.raises(ValueError, match="through target_zone=AUTO_ZONE"):
        run(settings(source_zone=MI_SOUTH), source((1, 43.0, -84.5, None)))


# --------------------------------------------------------------------------
# 2. The frame rule (L2): the same refusal require_frame_path raises.
# --------------------------------------------------------------------------


def _frames_own_refusal(source_frame, target_frame):
    with pytest.raises(FrameTransformationUnavailableError) as caught:
        require_frame_path(source_frame, target_frame)
    return str(caught.value)


@pytest.mark.parametrize(
    "input_frame, auto_frame, dated",
    [
        (NAD83_2011, NATRF2022, False),
        (NATRF2022, NAD83_2011, False),
        (WGS84_G2296, NATRF2022, True),
        (WGS84_G1762, NATRF2022, True),
        (ITRF2020, NATRF2022, True),
        (ITRF2014, NATRF2022, True),
    ],
    ids=lambda v: getattr(v, "code", str(v)),
)
def test_a_cross_frame_auto_job_meets_the_frame_registrys_own_refusal(
    input_frame, auto_frame, dated
):
    expected = _frames_own_refusal(input_frame, auto_frame)
    if {input_frame.code, auto_frame.code} == {NAD83_2011.code, NATRF2022.code}:
        assert "docs/DEFERRED-NATRF2022-BRIDGE.md" in expected
    with pytest.raises(FrameTransformationUnavailableError) as caught:
        run(
            settings(
                geodetic_frame=input_frame,
                auto_frame=auto_frame,
                observation_date=DATE if dated else None,
            ),
            # Before the file is read: no source and no file.
            None,
        )
    assert str(caught.value) == expected


def test_the_bare_wgs84_label_is_refused_as_unusable():
    with pytest.raises(FrameNotUsableError):
        run(settings(geodetic_frame=WGS84), None)


# --------------------------------------------------------------------------
# 3. The unit gate: every zone the Auto frame can choose.
# --------------------------------------------------------------------------


def test_zones_choosable_is_what_the_county_tables_can_return():
    assert zones_choosable(AutoZoneSystem.SPCS83) == (MI_NORTH, MI_CENTRAL, MI_SOUTH)
    local = zones_choosable(AutoZoneSystem.SPCS2022)
    statewide = zone_by_code("260001")
    assert len(local) == 18
    assert statewide not in local
    assert set(local) == set(SPCS2022_ZONES) - {statewide}
    assert zone_by_code("261018") in local  # Isle Royale, by the rule only


def test_auto_on_natrf2022_refuses_us_survey_feet_before_the_file_is_read(tmp_path):
    missing = tmp_path / "never-read.csv"
    with pytest.raises(ValueError) as caught:
        run(
            settings(
                input_path=missing,
                geodetic_frame=NATRF2022,
                auto_frame=NATRF2022,
                output_unit=US_SURVEY_FEET,
            )
        )
    message = str(caught.value)
    names = ", ".join(f"{z.name} ({z.code})" for z in zones_choosable(AutoZoneSystem.SPCS2022))
    assert message.startswith(
        "Auto zone in NATRF2022 chooses each point's zone among the 18 SPCS2022 "
        "zones it can assign, and 18 of them do not publish coordinates in "
        f"US survey feet (usft): {names}. This job's target unit cannot be "
        "used, because a point landing in one of those zones would be written "
        "in a unit its zone does not define. Auto SPCS2022 jobs may be "
        "written in: ift (International feet), m (meters). NGS publishes every "
        "SPCS2022 zone's false origin in metres and international feet only"
    )


@pytest.mark.parametrize("unit", [METERS, INTERNATIONAL_FEET])
def test_auto_on_natrf2022_accepts_the_units_ngs_publishes(unit):
    anchor = next(a for a in ANCHORS if a.system == "SPCS2022" and a.expected == "261008")
    result = run(
        settings(geodetic_frame=NATRF2022, auto_frame=NATRF2022, output_unit=unit),
        source((1, anchor.latitude, anchor.longitude, None)),
    )
    assert result.points[0].auto_zone.zone.code == "261008"


def test_auto_on_nad83_accepts_us_survey_feet_which_every_spcs83_zone_publishes():
    assert all(US_SURVEY_FEET in z.allowed_units for z in SPCS83_ZONES)
    result = run(settings(output_unit=US_SURVEY_FEET), source((1, 42.250568, -84.954191, None)))
    assert result.points[0].auto_zone.zone is MI_SOUTH


# --------------------------------------------------------------------------
# 4. Per point: NCAT's zone, the fixed-zone point bit for bit, refusals.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "system, frame",
    [("SPCS 83", NAD83_2011), ("SPCS2022", NATRF2022)],
    ids=["spcs83", "spcs2022"],
)
def test_a_mixed_zone_file_takes_ncats_zone_at_every_anchor_and_the_fixed_zone_point(
    system, frame
):
    """Every frozen in-Michigan NCAT anchor of the system, land and Great
    Lakes water, in ONE file. Each point is in NCAT's zone and is the
    fixed-zone job's point of that zone, field for field (warnings aside by
    exactly the extent code)."""
    anchors = [a for a in ANCHORS if a.system == system and a.expected is not None]
    rows = [
        (f"A{i}", a.latitude, a.longitude, 200.0 if i % 2 else None)
        for i, a in enumerate(anchors)
    ]
    result = run(settings(geodetic_frame=frame, auto_frame=frame), source(*rows))

    assert [p.point_id for p in result.points] == [r[0] for r in rows]
    converted = {p.point_id: p for p in result.points}
    zones_seen = set()
    for (point_id, _lat, _lon, _), anchor in zip(rows, anchors):
        point = converted[point_id]
        assert point.auto_zone.zone.code == anchor.expected, anchor.tag
        assert point.auto_zone.zone is point.conversion.target_zone
        county = _county_from_tag(anchor.tag)
        if county is not None:
            assert (point.auto_zone.county_fips, point.auto_zone.county_name) == county
        zones_seen.add(anchor.expected)

    # Every zone the system can choose is exercised by this one file.
    assert zones_seen == {z.code for z in zones_choosable(autozone.AutoZoneSystem(system))}

    # The fixed-zone job of each zone, over the SAME file (so every row,
    # line number included, is the same row): each point Auto put in that
    # zone is that job's point.
    compared = extent_exercised = 0
    for code in sorted(zones_seen):
        zone = zone_by_code(code)
        fixed = run(
            settings(geodetic_frame=frame, target_zone=zone, auto_frame=None),
            source(*rows),
        )
        assert len(fixed.points) == len(rows)
        for fixed_point in fixed.points:
            auto_point = converted[fixed_point.point_id]
            if auto_point.auto_zone.zone is zone:
                extent_exercised += assert_bit_identical(auto_point, fixed_point)
                compared += 1
    assert compared == len(converted)
    if system == "SPCS 83":
        # Five SPCS 83 anchors lie in a county of their zone yet outside the
        # zone's approximate extent box: the fixed job warns, Auto does not.
        assert extent_exercised == 5
    else:
        assert extent_exercised == 0


@pytest.mark.parametrize(
    "system, frame",
    [("SPCS 83", NAD83_2011), ("SPCS2022", NATRF2022)],
    ids=["spcs83", "spcs2022"],
)
def test_a_file_with_outside_anchors_refuses_the_whole_job_naming_every_one(system, frame):
    """Every anchor of the system, the outside-Michigan ones among them: the
    house rule - the whole job is refused, and EVERY unplaceable point is
    named with its position, in file order."""
    anchors = [a for a in ANCHORS if a.system == system]
    rows = [(f"A{i}", a.latitude, a.longitude, None) for i, a in enumerate(anchors)]
    outside = [(r[0], r[1], r[2]) for r, a in zip(rows, anchors) if a.expected is None]
    assert len(outside) == 7
    with pytest.raises(AutoZoneUnplacedPointsError) as caught:
        run(settings(geodetic_frame=frame, auto_frame=frame), source(*rows))
    assert caught.value.points == tuple(outside)
    assert caught.value.frame is frame
    listed = "; ".join(
        f"point {pid} at latitude {lat:.8f}, longitude {lon:.8f} - in no Michigan county"
        for pid, lat, lon in outside
    )
    assert str(caught.value) == (
        f"Auto could not choose a zone for 7 point(s) of this job, so nothing "
        f"was converted. Positions tested, in {frame.code}: {listed}. No zone "
        f"is assigned to a point in no Michigan county (US Census TIGER/Line "
        f"2025 counties, Great Lakes waters included), and Auto never assigns "
        f"the nearest zone or picks between two counties that both claim a "
        f"point. Check these coordinates, remove the points from the file, or "
        f"choose the zone yourself."
    )


def _county_from_tag(tag):
    # 'COUNTY 26001 Alcona' -> ('26001', 'Alcona'); other tags name no county.
    if not tag.startswith("COUNTY "):
        return None
    _, fips, name = tag.split(" ", 2)
    return fips, name


def test_only_the_extent_code_is_removed_and_the_projection_call_is_the_fixed_ones(monkeypatch):
    """``project_point`` emits only OUTSIDE_ZONE_EXTENT today, so after the
    Auto filter its warning tuple is always empty and two defects would be
    invisible: a filter that drops EVERY warning, and a different context
    string handed to the projection. A wrapper adds one other warning, built
    from the context the job passed, to every projection; it must survive on
    the Auto point and match the fixed-zone job's exactly."""
    real = job.project_point

    def with_extra(latitude, longitude, frame, zone, context, **kwargs):
        conversion = real(latitude, longitude, frame, zone, context, **kwargs)
        extra = convert.ConversionWarning(
            code=WarningCode.EASTING_UNLIKE_SELECTED_ZONE, message=f"{context}: probe"
        )
        return dataclasses.replace(conversion, warnings=conversion.warnings + (extra,))

    monkeypatch.setattr(job, "project_point", with_extra)
    rows = [(1, *CALHOUN, None), (2, 44.682131, -83.622405, 250.0)]
    auto = run(settings(), source(*rows))
    for point in auto.points:
        probes = [w for w in point.conversion.warnings if w.message.endswith(": probe")]
        assert [w.message for w in probes] == [f"point {point.point_id}: probe"]
        fixed = run(
            settings(target_zone=point.auto_zone.zone, auto_frame=None), source(*rows)
        )
        assert_bit_identical(
            point, next(p for p in fixed.points if p.point_id == point.point_id)
        )


def test_a_non_auto_job_carries_no_auto_fields():
    result = run(
        settings(target_zone=MI_SOUTH, auto_frame=None),
        source((1, 42.250568, -84.954191, 250.0)),
    )
    assert result.points[0].auto_zone is None


def test_a_file_entirely_outside_michigan_names_both_points():
    with pytest.raises(AutoZoneUnplacedPointsError) as caught:
        run(settings(), source((1, 41.0, -80.0, None), (2, 41.65, -83.55, 5.0)))
    assert caught.value.points == (("1", 41.0, -80.0), ("2", 41.65, -83.55))
    assert (
        "point 1 at latitude 41.00000000, longitude -80.00000000 - in no Michigan "
        "county; point 2 at latitude 41.65000000, longitude -83.55000000 - in no "
        "Michigan county."
    ) in str(caught.value)


def test_one_bad_point_among_good_ones_refuses_the_whole_job():
    with pytest.raises(AutoZoneUnplacedPointsError, match="for 1 point\\(s\\)"):
        run(settings(), source((1, 42.250568, -84.954191, None), (2, 41.0, -80.0, None)))


def _square(fips, name, lon, lat, half):
    ring = (
        (lon - half, lat - half),
        (lon + half, lat - half),
        (lon + half, lat + half),
        (lon - half, lat + half),
        (lon - half, lat - half),
    )
    return County(fips=fips, name=name, rings=(ring,))


def test_a_position_two_counties_claim_refuses_the_job_naming_both_counties(monkeypatch):
    overlapping = CountySet(
        [_square("26025", "Calhoun", -84.95, 42.25, 0.1), _square("26077", "Kalamazoo", -84.9, 42.25, 0.1)],
        source="two overlapping test squares",
    )
    monkeypatch.setattr(job.county_file, "default_counties", lambda: overlapping)
    with pytest.raises(AutoZoneUnplacedPointsError) as caught:
        run(settings(), source((1, 42.25, -84.92, None), (2, 42.25, -85.02, None)))
    assert str(caught.value).startswith(
        "Auto could not choose a zone for 1 point(s) of this job, so nothing was "
        "converted. Positions tested, in NAD83(2011): point 1 at latitude "
        "42.25000000, longitude -84.92000000 - inside more than one county "
        "polygon (Calhoun (26025), Kalamazoo (26077)). No zone is assigned to a "
        "point in no Michigan county (two overlapping test squares,"
    )


def test_county_data_the_tables_do_not_know_refuses_the_whole_job(monkeypatch):
    """A data fault is not a fact about one point: it refuses the job."""
    unknown = CountySet([_square("99999", "Nowhere", -84.95, 42.25, 0.1)], source="test")
    monkeypatch.setattr(job.county_file, "default_counties", lambda: unknown)
    with pytest.raises(AutoZoneDataError, match="Nowhere County \\(99999\\) has no row"):
        run(settings(), source((1, 42.25, -84.95, None)))


# WGS 84 / ITRF through HTDP: the zone is chosen at the NAD 83 pivot.

CALHOUN = (42.250568, -84.954191)  # the Z0 anchor 'COUNTY 26025 Calhoun', 2113


@pytest.mark.parametrize("frame", FIVE, ids=lambda f: f.code)
def test_a_wgs84_or_itrf_position_converts_as_the_fixed_zone_job_does(frame):
    """Deep inside one county (the anchor is >= 20 km from any zone line,
    and the HTDP shift is ~1.3 m), so the input and its pivot are in the
    same county: Calhoun, MI South. The point is the fixed MI South job's."""
    rows = [(1, *CALHOUN, 250.0), (2, *CALHOUN, None)]
    auto = run(settings(geodetic_frame=frame, observation_date=DATE), source(*rows))
    fixed = run(
        settings(geodetic_frame=frame, observation_date=DATE, target_zone=MI_SOUTH, auto_frame=None),
        source(*rows),
    )
    for a, f in zip(auto.points, fixed.points, strict=True):
        assert a.auto_zone.zone is MI_SOUTH
        assert (a.auto_zone.county_fips, a.auto_zone.county_name) == ("26025", "Calhoun")
        assert a.conversion.is_transformed
        assert_bit_identical(a, f)


# A constructed straddle (found by a search over the county edges, then
# checked here with the suite's own even-odd test, independent of michspc):
# in Saginaw Bay, on the SPCS 83 Central/South line between Arenac (MI
# Central) and Huron (MI South). The WGS84(G2296) position dated 2025-06-15
# is 0.45 m on the ARENAC side; HTDP carries it 0.99 m south and 0.85 m east,
# to a NAD 83 pivot 0.86 m on the HURON side. So the input's zone is Central
# and the pivot's is South, and only the pivot's is right (plan L4).
STRADDLE = (44.150940052, -83.213086196)


def _independent_county(lat, lon):
    return [
        (c["fips"], c["name"])
        for c in geo.county_document()["counties"]
        if geo.plain_even_odd(c["rings"], lon, lat)
    ]


def test_the_zone_is_chosen_at_the_nad83_pivot_where_the_two_positions_straddle_a_zone_line():
    result = run(
        settings(geodetic_frame=WGS84_G2296, observation_date=DATE),
        source((7, *STRADDLE, None)),
    )
    (point,) = result.points
    pivot = (point.conversion.latitude, point.conversion.longitude)
    assert pivot != STRADDLE
    assert _independent_county(*STRADDLE) == [("26011", "Arenac")]
    assert _independent_county(*pivot) == [("26063", "Huron")]
    assert point.auto_zone.zone is MI_SOUTH
    assert (point.auto_zone.county_fips, point.auto_zone.county_name) == ("26063", "Huron")

    fixed = run(
        settings(
            geodetic_frame=WGS84_G2296,
            observation_date=DATE,
            target_zone=MI_SOUTH,
            auto_frame=None,
        ),
        source((7, *STRADDLE, None)),
    )
    assert_bit_identical(point, fixed.points[0])


def test_a_refused_wgs84_job_names_the_pivot_and_the_frame_it_came_from():
    with pytest.raises(AutoZoneUnplacedPointsError) as caught:
        run(
            settings(geodetic_frame=WGS84_G2296, observation_date=DATE),
            source((9, 41.65, -83.55, None), (10, *CALHOUN, None)),
        )
    ((pid, lat, lon),) = caught.value.points
    assert pid == "9" and caught.value.frame is NAD83_2011
    assert (lat, lon) != (41.65, -83.55)
    assert str(caught.value).startswith(
        f"Auto could not choose a zone for 1 point(s) of this job, so nothing "
        f"was converted. Positions tested, in NAD83(2011) (each WGS84(G2296) "
        f"position as HTDP carried it there): point 9 at latitude {lat:.8f}, "
        f"longitude {lon:.8f} - in no Michigan county."
    )


def test_an_auto_job_does_not_need_the_county_file_when_it_is_not_auto(monkeypatch):
    def refuse():
        raise AssertionError("a fixed-zone job read the county file")

    monkeypatch.setattr(job.county_file, "default_counties", refuse)
    run(settings(target_zone=MI_SOUTH, auto_frame=None), source((1, *CALHOUN, None)))


# --------------------------------------------------------------------------
# 5. The observation date source (L10).
# --------------------------------------------------------------------------

LOCAL = datetime.date(2026, 10, 21)
UTC = datetime.date(2026, 10, 22)  # a Michigan evening: UTC is already tomorrow


@pytest.fixture
def evening(monkeypatch):
    monkeypatch.setattr(job, "_local_and_utc_dates", lambda: (LOCAL, UTC))


def test_today_local_is_the_local_date_and_today_stays_the_later(evening):
    assert job.today_local() == LOCAL
    assert job.today() == UTC


def _dated(date, date_source, **fields):
    return settings(
        target_zone=MI_SOUTH,
        auto_frame=None,
        geodetic_frame=WGS84_G2296,
        observation_date=date,
        observation_date_source=date_source,
        **fields,
    )


def test_today_is_accepted_on_the_local_date(evening):
    result = run(_dated(LOCAL, ObservationDateSource.TODAY), source((1, *CALHOUN, None)))
    assert result.settings.observation_date_source is ObservationDateSource.TODAY


def test_today_is_refused_on_the_utc_date(evening):
    with pytest.raises(ValueError) as caught:
        run(_dated(UTC, ObservationDateSource.TODAY), source((1, *CALHOUN, None)))
    assert str(caught.value) == (
        "observation_date_source is TODAY, but observation_date is 2026-10-22 "
        "and the day this job runs is 2026-10-21 (the local calendar date). "
        "TODAY means the date the job ran, so the two must be the same date: "
        "a date carried over from an earlier session, or a UTC date taken for "
        "the local one, would be recorded as the date the job ran when it is "
        "not. State ENTERED for a date that was typed, or pass today's local "
        "date."
    )


def test_today_is_refused_on_an_earlier_date(evening):
    with pytest.raises(ValueError, match="observation_date_source is TODAY"):
        run(_dated(DATE, ObservationDateSource.TODAY), source((1, *CALHOUN, None)))


@pytest.mark.parametrize("date", [DATE, LOCAL, UTC])
def test_entered_takes_any_date_the_future_rule_allows(evening, date):
    run(_dated(date, ObservationDateSource.ENTERED), source((1, *CALHOUN, None)))


def test_entered_is_still_refused_in_the_future(evening):
    with pytest.raises(ValueError, match="is after the day this job runs"):
        run(
            _dated(UTC + datetime.timedelta(days=1), ObservationDateSource.ENTERED),
            source((1, *CALHOUN, None)),
        )


def test_a_stray_observation_date_source_is_refused_by_name():
    with pytest.raises(ValueError) as caught:
        run(
            settings(
                target_zone=MI_SOUTH,
                auto_frame=None,
                observation_date_source=ObservationDateSource.TODAY,
            ),
            source((1, *CALHOUN, None)),
        )
    assert str(caught.value) == (
        "A GEODETIC_TO_ZONE job was given observation_date_source=TODAY, but "
        "no frame this job reads is time-dependent, so it states no "
        "observation date and there is no date whose source could be "
        "recorded. A source stated for a job that used no date would put a "
        "sentence about a date into a record of a conversion that never read "
        "one. Pass observation_date_source=None."
    )


def test_a_stray_date_and_source_together_raise_the_date_refusal_first():
    with pytest.raises(ValueError, match="was given observation_date=2025-06-15"):
        run(
            settings(
                target_zone=MI_SOUTH,
                auto_frame=None,
                observation_date=DATE,
                observation_date_source=ObservationDateSource.ENTERED,
            ),
            source((1, *CALHOUN, None)),
        )


def test_an_observation_date_source_must_be_the_enum(evening):
    with pytest.raises(TypeError, match="must be an ObservationDateSource"):
        run(_dated(LOCAL, "today"), source((1, *CALHOUN, None)))


def test_the_core_accepts_a_date_without_its_source_by_decision(evening):
    """FINAL, the session lead's ruling at Z4 (plan L10 asked for the source
    to be required; this is the recorded deviation): the core keeps
    ``observation_date_source`` optional beside a date. A frozen W4 record
    digest and about 180 core tests state a date with no source, and a record
    without one says nothing false - it prints the date line exactly as
    before the source existed. The interface always sends one beside a date
    on both tabs, which tests/test_gui_options.py pins
    (``test_both_tabs_send_a_source_whenever_they_send_a_date``)."""
    run(_dated(LOCAL, None), source((1, *CALHOUN, None)))


# --------------------------------------------------------------------------
# 6. The write guard's successors (Z2's guard, removed at Z3).
#
# Z2 refused to write an Auto job (exports.require_a_disclosed_zone) until Z3
# could disclose it. Z3 built the disclosure and removed the guard, on the
# W3 -> W4 precedent; these two pins are the guard's successors. What an Auto
# archive holds is pinned in detail in tests/test_autozone_outputs.py.
# --------------------------------------------------------------------------


def _written_auto_result(tmp_path, text):
    path = tmp_path / "pts.csv"
    path.write_bytes(text.encode("ascii"))
    return run(settings(input_path=path, output_directory=tmp_path))


def test_an_auto_job_is_written_and_states_each_points_zone(tmp_path):
    """The job the guard refused now writes: one clean file per zone used
    (Calhoun -> MI-S and the Alcona anchor -> MI-C, NCAT's own zones), and
    the record states the Auto TO block naming both."""
    result = _written_auto_result(
        tmp_path,
        f"1,{CALHOUN[0]},{CALHOUN[1]},250.0,A\r\n2,44.682131,-83.622405,,B\r\n",
    )
    assert len(result.points) == 2
    written = exports.write_all(result)
    assert written["archive"].name == "pts_AUTO-SPCS83.zip"
    import zipfile

    with zipfile.ZipFile(written["archive"]) as archive:
        assert archive.namelist() == [
            "pts_AUTO-SPCS83_MI-C.csv",
            "pts_AUTO-SPCS83_MI-S.csv",
            "pts_AUTO-SPCS83_full.csv",
            "pts_AUTO-SPCS83_README.txt",
        ]
        assert archive.read("pts_AUTO-SPCS83_MI-C.csv").decode().startswith("2,")
        assert archive.read("pts_AUTO-SPCS83_MI-S.csv").decode().startswith("1,")
        record = archive.read("pts_AUTO-SPCS83_README.txt").decode()
    assert "TO: Auto zone - each point in the zone of its county (SPCS 83)\n" in record
    assert "    Michigan Central, zone 2112 (MI-C): 1 point\n" in record
    assert "    Michigan South, zone 2113 (MI-S): 1 point\n" in record
    assert report.build_report(result).split("\n")[6:] == record.split("\n")[6:]


def test_the_write_guard_is_gone(tmp_path):
    """Removed, not left dormant: nothing could switch it back on."""
    assert not hasattr(exports, "require_a_disclosed_zone")
    assert not hasattr(exports, "UndisclosedAutoZoneError")
    path = tmp_path / "pts.csv"
    path.write_bytes(f"1,{CALHOUN[0]},{CALHOUN[1]},250.0,A\r\n".encode("ascii"))
    result = run(settings(input_path=path, output_directory=tmp_path, target_zone=MI_SOUTH, auto_frame=None))
    written = exports.write_all(result)
    assert written["archive"].name == "pts_MI-S.zip"
