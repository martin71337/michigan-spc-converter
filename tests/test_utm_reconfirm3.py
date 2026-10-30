"""The third narrowing re-confirmation's findings (DESIGN.md #72), pinned.

review/gate-utm-interim/reconfirm3-output.txt:

* R3-1 - a zone-to-zone coordinate written INTO a transverse Mercator zone at
  the edge of the allowance did not read back: the recovered forward and the
  inverse had the SAME allowance, so 4-decimal rounding pushed the read-back
  past it. Now two tiers (tm.WRITE_ALLOWANCE_DEGREES caps every write,
  tm.READ_ALLOWANCE_DEGREES admits every read), with the measured invariant
  READ > WRITE + READ_OVERSHOOT_MEASURED.
* R3-2 - the sign-convention sentence said "The file gives" on the Single
  point tab, and told a DMS entry to change a convention that does not apply
  to it.
* R3-3 - nothing pinned the outer bound of the recovered forward; seeding its
  allowance to a whole degree passed the suite.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from michspc.fileio import exports
from michspc.gui import controls, settings_store
from michspc.gui import single_point as single_point_module
from michspc.gui.app import build_application
from michspc.gui.window import MainWindow
from michspc.job import (
    Direction,
    EastOfGreenwichRefusal,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc import convert, projection, tm
from michspc.spc.frames import NAD83_2011, NATRF2022
from michspc.spc.projection import PositionOrigin
from michspc.spc.tm import (
    DOMAIN_LIMIT_DEGREES,
    READ_ALLOWANCE_DEGREES,
    WRITE_ALLOWANCE_DEGREES,
    TransverseMercatorDomainError,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.vertical import NAVD88, NGVD29
from michspc.spc.zones import ALL_ZONES, TransverseMercatorDef, zone_by_code
from tests.conftest import member_text

L = DOMAIN_LIMIT_DEGREES
A = WRITE_ALLOWANCE_DEGREES
UTM15, UTM16, UTM17 = (zone_by_code(c) for c in ("15N", "16N", "17N"))
MI_NORTH, MI_CENTRAL, MI_SOUTH = (zone_by_code(c) for c in ("2111", "2112", "2113"))
TM_ZONES = tuple(z for z in ALL_ZONES if isinstance(z.definition, TransverseMercatorDef))


def _at(meridian: float, distance: float) -> float:
    """The largest float longitude at most ``distance`` east of ``meridian``.

    ``meridian + distance`` can land one ulp beyond ``distance``; the domain
    check measures ``abs(longitude - meridian)``, so the tests step back to the
    last float it accepts.
    """
    longitude = meridian + distance
    while abs(longitude - meridian) > distance:
        longitude = math.nextafter(longitude, meridian)
    return longitude


def _job(tmp_path: Path, rows: str, **fields):
    base = dict(
        input_path=tmp_path / "in.csv",
        output_directory=tmp_path,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=None,
    )
    base.update(fields)
    settings = JobSettings(**base)
    settings.input_path.write_text(rows, encoding="utf-8")
    result = run(settings)
    return result, exports.write_all(result)["archive"]


# ==========================================================================
# R3-1 - the two tiers.
# ==========================================================================


def test_the_invariant_holds_and_is_measured():
    """READ > WRITE + the measured overshoot, with the constants as stated."""
    assert A == 1e-7
    assert READ_ALLOWANCE_DEGREES == 2e-7
    assert tm.READ_OVERSHOOT_MEASURED == 9.3e-10
    assert READ_ALLOWANCE_DEGREES > A + tm.READ_OVERSHOOT_MEASURED


def test_the_overshoot_is_what_the_docstring_states():
    """Re-measures READ_OVERSHOOT_MEASURED: every transverse Mercator zone,
    both sides of the meridian, written at exactly the limit plus the write
    allowance, rounded to 4 decimals in every unit the zone allows, read back
    by the inverse series. The worst lies within the stated figure, and above
    a tenth of it - so the stated number is a measurement, not a bound pulled
    from the air."""
    worst = 0.0
    for zone in TM_ZONES:
        constants = projection.constants_for(zone)
        meridian = zone.definition.lon_origin
        for k in range(0, 6801, 40):
            latitude = 41.6 + k * 0.001
            for side in (-1.0, 1.0):
                longitude = _at(meridian, side * (L + A)) if side > 0 else -_at(-meridian, L + A)
                grid = tm.forward_from(latitude, longitude, constants, PositionOrigin.RECOVERED)
                for unit in zone.allowed_units:
                    size = unit.meters_per_unit
                    northing = round(grid.northing / size, 4) * size
                    easting = round(grid.easting / size, 4) * size
                    back = tm._inverse_series(northing, easting, constants)
                    worst = max(worst, abs(back.longitude - meridian) - (L + A))
    assert tm.READ_OVERSHOOT_MEASURED / 10 < worst <= tm.READ_OVERSHOOT_MEASURED


# The reviewer's row and the eight other pairs it reproduced on.
REVIEWER_ROW = "1,-63665.6573,19302281.4939,200.0,P"
"""ZONE_TO_ZONE 2112 (ift) -> 17N: 43.1328 N, -85.8000000997 - written as
"1,4786755.1882,109573.2866,60.9600,P", which refused on every read path at
cf0c90e (reconfirm3-output.txt, R3-1)."""


def test_the_reviewers_row_writes_what_it_wrote(tmp_path):
    _result, archive = _job(
        tmp_path,
        REVIEWER_ROW + "\n",
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_CENTRAL,
        target_zone=UTM17,
        input_unit=INTERNATIONAL_FEET,
    )
    assert member_text(archive, f"{archive.stem}.csv").strip() == (
        "1,4786755.1882,109573.2866,60.9600,P"
    )


WRITTEN = "1,4786755.1882,109573.2866,60.9600,P\n"


def test_the_reviewers_row_reads_back_zone_to_geodetic(tmp_path):
    result, _ = _job(
        tmp_path,
        WRITTEN,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=UTM17,
        target_zone=None,
        geodetic_frame=NAD83_2011,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    assert result.points[0].conversion.longitude == pytest.approx(-85.8000001, abs=5e-9)


def test_the_reviewers_row_reads_back_vertical_only(tmp_path):
    result, _ = _job(
        tmp_path,
        WRITTEN,
        direction=Direction.VERTICAL_ONLY,
        source_zone=UTM17,
        target_zone=None,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    assert result.points[0].conversion.longitude == pytest.approx(-85.8000001, abs=5e-9)


@pytest.mark.parametrize("onward", [MI_CENTRAL, MI_SOUTH], ids=lambda z: z.code)
def test_the_reviewers_row_reads_back_to_its_source_and_onward(tmp_path, onward):
    result, _ = _job(
        tmp_path,
        WRITTEN,
        direction=Direction.ZONE_TO_ZONE,
        source_zone=UTM17,
        target_zone=onward,
        output_unit=INTERNATIONAL_FEET,
    )
    if onward is MI_CENTRAL:
        # Back to the job's own source: the row the reviewer started from.
        conversion = result.points[0].conversion
        assert conversion.target_northing == pytest.approx(-63665.6573 * 0.3048, abs=1e-3)
        assert conversion.target_easting == pytest.approx(19302281.4939 * 0.3048, abs=1e-3)


STRIP_PAIRS = (
    # (source, target) - the reviewer's nine (reconfirm3-output.txt, R3-1).
    ("2112", "17N"),
    ("2113", "16N"),
    ("2112", "16N"),
    ("2111", "17N"),
    ("2111", "15N"),
    ("260001", "16N-2022"),
    ("260001", "17N-2022"),
    ("261016", "15N-2022"),
    ("261001", "17N-2022"),
)


def _strip_coordinates(source, target):
    """Source coordinates whose zone-to-zone conversion into ``target`` lands
    at the very edge of the write allowance - where the strip lay.

    A latitude grid near the target's limit meridian, on the side facing the
    source zone: each position is projected into the source zone, written at
    4 decimals (metres), and kept when the conversion into the target lands
    within 2e-9 degrees of the write cap."""
    meridian = target.definition.lon_origin
    side = 1.0 if source.definition.lon_origin > meridian else -1.0
    found = []
    for k in range(0, 40):
        latitude = 42.0 + 0.15 * k
        for nudge in range(0, 30):
            distance = L + A - nudge * 4e-10
            longitude = _at(meridian, distance) if side > 0 else -_at(-meridian, distance)
            grid = projection.forward(latitude, longitude, source)
            northing, easting = round(grid.northing, 4), round(grid.easting, 4)
            try:
                result = convert.convert_point(northing, easting, source, target)
            except TransverseMercatorDomainError:
                continue
            if abs(result.longitude - meridian) > L + A - 2e-9:
                found.append((result, northing, easting))
                break
    return found


@pytest.mark.parametrize("pair", STRIP_PAIRS, ids=lambda p: f"{p[0]}-to-{p[1]}")
def test_every_coordinate_written_in_the_strip_reads_back(pair):
    """Fails with READ_ALLOWANCE_DEGREES seeded to the write allowance: the
    written coordinates' read-back longitudes lie past L + A."""
    source, target = (zone_by_code(code) for code in pair)
    found = _strip_coordinates(source, target)
    assert len(found) >= 10, "the sweep must reach the strip"
    past_the_write_cap = 0
    for result, src_northing, src_easting in found:
        northing = round(result.target_northing, 4)
        easting = round(result.target_easting, 4)
        same = convert.convert_point(northing, easting, target, target)
        if abs(same.longitude - target.definition.lon_origin) > L + A:
            past_the_write_cap += 1
        back = convert.convert_point(northing, easting, target, source)
        assert back.target_northing == pytest.approx(src_northing, abs=1e-3)
        assert back.target_easting == pytest.approx(src_easting, abs=1e-3)
    assert past_the_write_cap >= 1, "anti-vacuity: some read-back lies in the strip"


def test_a_chain_at_the_limit_never_refuses_and_never_creeps():
    """16N -> 2112 -> 16N -> 2113 -> 17N, and 16N -> 2113 -> 16N ten times,
    starting at exactly the limit east of 16N's meridian, written at 4
    decimals each hop. No hop refuses, and no 16N write lies past the write
    cap plus the measured overshoot."""
    for latitude in (42.0, 43.5, 45.0, 46.5, 48.0):
        start = projection.forward(latitude, _at(UTM16.definition.lon_origin, L), UTM16)
        northing, easting = round(start.northing, 4), round(start.easting, 4)
        zone = UTM16
        for hop in (MI_CENTRAL, UTM16, MI_SOUTH, UTM17):
            result = convert.convert_point(northing, easting, zone, hop)
            northing, easting = round(result.target_northing, 4), round(result.target_easting, 4)
            zone = hop
        northing, easting = round(start.northing, 4), round(start.easting, 4)
        for _ in range(10):
            there = convert.convert_point(northing, easting, UTM16, MI_SOUTH)
            back = convert.convert_point(
                round(there.target_northing, 4), round(there.target_easting, 4), MI_SOUTH, UTM16
            )
            reread = convert.convert_point(
                round(back.target_northing, 4), round(back.target_easting, 4), UTM16, UTM16
            )
            assert abs(reread.longitude - UTM16.definition.lon_origin) <= (
                L + A + tm.READ_OVERSHOOT_MEASURED
            )
            northing, easting = round(back.target_northing, 4), round(back.target_easting, 4)


def test_a_supplied_position_past_the_limit_still_refuses(tmp_path):
    longitude = UTM16.definition.lon_origin + L + A / 2
    with pytest.raises(TransverseMercatorDomainError):
        projection.forward(45.0, longitude, UTM16)
    with pytest.raises(TransverseMercatorDomainError):
        _job(
            tmp_path,
            f"1,45.0,{longitude!r},200.0,P\n",
            direction=Direction.GEODETIC_TO_ZONE,
            source_zone=None,
            target_zone=UTM16,
            geodetic_frame=NAD83_2011,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        )


# ==========================================================================
# R3-3 - the outer bound of each tier, pinned directly.
# ==========================================================================


@pytest.mark.parametrize("zone", TM_ZONES, ids=lambda z: z.code)
def test_each_tier_stops_where_it_says(zone):
    """Seeding either allowance to a degree fails here: the recovered forward
    refuses at L + 1.5A, the re-read forward and the inverse at L + 2.5A."""
    constants = projection.constants_for(zone)
    meridian = zone.definition.lon_origin
    for side in (-1.0, 1.0):
        def at(distance):
            return meridian + side * distance

        projection.forward(45.0, at(L + 0.5 * A), zone, origin=PositionOrigin.RECOVERED)
        with pytest.raises(TransverseMercatorDomainError):
            projection.forward(45.0, at(L + 1.5 * A), zone, origin=PositionOrigin.RECOVERED)
        projection.forward(45.0, at(L + 1.5 * A), zone, origin=PositionOrigin.REREAD)
        with pytest.raises(TransverseMercatorDomainError):
            projection.forward(45.0, at(L + 2.5 * A), zone, origin=PositionOrigin.REREAD)
        inside = tm._forward_series(45.0, at(L + 1.5 * A), constants)
        projection.inverse(inside.northing, inside.easting, zone)
        outside = tm._forward_series(45.0, at(L + 2.5 * A), constants)
        with pytest.raises(TransverseMercatorDomainError):
            projection.inverse(outside.northing, outside.easting, zone)


@pytest.mark.parametrize("distance", [L + 2 * A, 4.9], ids=["L+2A", "4.9"])
def test_a_state_plane_point_beyond_the_write_cap_refuses_into_utm(tmp_path, distance):
    """The reviewer's suggested pin: through convert_point and a ZONE_TO_ZONE
    job, a 2112 point at 4.8 + 2e-7 and at 4.9 degrees from 17N's meridian."""
    longitude = UTM17.definition.lon_origin - distance
    grid = projection.forward(44.3, longitude, MI_CENTRAL)
    with pytest.raises(TransverseMercatorDomainError):
        convert.convert_point(grid.northing, grid.easting, MI_CENTRAL, UTM17)
    with pytest.raises(TransverseMercatorDomainError):
        _job(
            tmp_path,
            f"1,{grid.northing!r},{grid.easting!r},200.0,P\n",
            direction=Direction.ZONE_TO_ZONE,
            source_zone=MI_CENTRAL,
            target_zone=UTM17,
        )


def test_both_tiers_agree_with_proj():
    """Nothing either tier accepts is outside 0.5 mm in position or 5e-9 in
    scale against PROJ (a third opinion; skips without pyproj)."""
    pyproj = pytest.importorskip("pyproj")
    worst_position = worst_scale = 0.0
    for zone, code in ((UTM15, 6344), (UTM16, 6345), (UTM17, 6346)):
        transformer = pyproj.Transformer.from_crs("EPSG:6318", f"EPSG:{code}", always_xy=True)
        proj = pyproj.Proj(f"EPSG:{code}")
        meridian = zone.definition.lon_origin
        for latitude in (41.6, 43.0, 44.5, 46.0, 47.5, 48.4):
            for side in (-1.0, 1.0):
                for origin, reach in (
                    (PositionOrigin.RECOVERED, L + A),
                    (PositionOrigin.REREAD, L + 2 * A),
                ):
                    longitude = meridian + side * reach * (1 - 1e-12)
                    ours = projection.forward(latitude, longitude, zone, origin=origin)
                    easting, northing = transformer.transform(longitude, latitude)
                    scale = proj.get_factors(longitude, latitude).meridional_scale
                    worst_position = max(
                        worst_position,
                        math.hypot(ours.northing - northing, ours.easting - easting),
                    )
                    worst_scale = max(worst_scale, abs(ours.scale_factor - scale))
    assert worst_position < 0.0005
    assert worst_scale < 5e-9


# ==========================================================================
# R3-2 - the sign-convention sentence, true for its source.
# ==========================================================================


def test_a_file_longitude_is_named_as_the_file_gives_it(tmp_path):
    with pytest.raises(EastOfGreenwichRefusal) as raised:
        _job(
            tmp_path,
            "1,43.0,84.5,200.0,P\n",
            direction=Direction.GEODETIC_TO_ZONE,
            source_zone=None,
            target_zone=UTM16,
            geodetic_frame=NAD83_2011,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        )
    message = str(raised.value)
    assert "The file gives longitude 84.500000, and this job reads longitudes as negative west" in message
    assert "The longitude entered" not in message
    assert raised.value.typed is False


@pytest.fixture(scope="module")
def qapp():
    application = build_application(["michspc-tests"])
    yield application
    application.processEvents()


@pytest.fixture
def tab(qapp):
    win = MainWindow(store=settings_store.MemoryStore())
    tab = win.single_point
    tab.shown = []
    tab._show_failure = tab.shown.append
    win.show()
    qapp.processEvents()
    yield tab
    win.close()


def _choose(combo, data):
    index = combo.findData(data)
    assert index >= 0, data
    combo.setCurrentIndex(index)


def _set_up(tab, convention):
    _choose(tab.from_zone, controls.geodetic_choice(NATRF2022))
    _choose(tab.to_zone, zone_by_code("261001"))
    _choose(tab.longitude_combo, convention)


@pytest.mark.parametrize(
    "convention, typed, signed",
    [
        (LongitudeConvention.NEGATIVE_WEST, "83.7", 83.7),
        (LongitudeConvention.POSITIVE_WEST, "-83.7", 83.7),
    ],
    ids=["negative-west", "positive-west"],
)
def test_a_typed_decimal_longitude_is_named_as_entered(tab, convention, typed, signed):
    _set_up(tab, convention)
    _choose(tab.angle_format, single_point_module.DECIMAL_PAGE)
    tab.first_edit.setText("42.3")
    tab.second_edit.setText(typed)
    assert tab.convert() is False
    message = str(tab.last_failure)
    assert (
        f"The longitude entered, {float(typed):.6f}, read as {convention.value}, "
        f"puts the point at {signed:.6f} - east of Greenwich"
    ) in message
    assert "The file gives" not in message
    assert "this file uses" not in message


@pytest.mark.parametrize(
    "convention", list(LongitudeConvention), ids=lambda c: c.name.lower()
)
def test_a_dms_east_longitude_names_the_letter_not_the_convention(tab, convention):
    """The reviewer's case: 42-18-00 N, 83-42-00 E, under BOTH conventions -
    the same sentence, because the convention does not apply to it."""
    _set_up(tab, convention)
    _choose(tab.angle_format, single_point_module.DMS_PAGE)
    for entry, (degrees, minutes, seconds, letter) in (
        (tab.first_dms, ("42", "18", "00", "N")),
        (tab.second_dms, ("83", "42", "00", "E")),
    ):
        entry.degrees.setText(degrees)
        entry.minutes.setText(minutes)
        entry.seconds.setText(seconds)
        _choose(entry.hemisphere, letter)
    assert tab.convert() is False
    message = str(tab.last_failure)
    assert (
        "The longitude was entered in degrees, minutes and seconds with the "
        "hemisphere letter E, which puts the point at 83.700000 - east of "
        "Greenwich, where no Michigan point is; every Michigan longitude is W. "
        "The longitude sign convention does not apply to an entry with a "
        "hemisphere letter: choose W."
    ) in message
    assert "The file gives" not in message
    assert "The longitude entered," not in message
    assert tab.shown and str(tab.shown[-1]) == message
