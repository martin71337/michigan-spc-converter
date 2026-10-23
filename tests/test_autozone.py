"""Auto zone's core: point-in-polygon, the on-line rule, refusals, speed.

Every expected value is hand-derived in a comment (the synthetic squares) or
taken from the county data's own topology and checked by an independent
even-odd test (``tests/autozone_geometry.plain_even_odd``), never by the code
under test agreeing with itself. The NCAT anchors are in
``test_autozone_anchors.py``; the tables against the statute and NGS's
polygons in ``test_autozone_tables.py``; the county file's loader in
``test_counties_file.py``.
"""

from __future__ import annotations

import math
import random
import time

import pytest

from michspc.fileio import counties as county_file
from michspc.spc import autozone as A
from michspc.spc import zones
from michspc.spc.autozone import (
    AutoZoneAmbiguousError,
    AutoZoneDataError,
    AutoZoneInputError,
    AutoZoneOutsideError,
    AutoZoneRefusal,
    AutoZoneSystem,
    County,
    CountySet,
    PreparedCounty,
    even_odd_contains,
    zone_for,
)
from tests import autozone_geometry as geo

SPCS83 = AutoZoneSystem.SPCS83
SPCS2022 = AutoZoneSystem.SPCS2022


@pytest.fixture(scope="module")
def shipped() -> CountySet:
    return county_file.load_counties()


def square(x0, y0, x1, y1, clockwise=True):
    ring = ((x0, y0), (x0, y1), (x1, y1), (x1, y0), (x0, y0))
    return ring if clockwise else tuple(reversed(ring))


def which(county_set: CountySet, lon, lat) -> list[str]:
    return [c.fips for c in county_set.containing(lon, lat)]


# ==========================================================================
# The even-odd rule, on shapes whose answers are obvious by eye.
# ==========================================================================


def test_holes_and_islands_by_even_odd_over_every_ring():
    # A 10x10 square with a 2x2 hole at (4..6, 4..6) and a separate 1x1 island
    # at (20..21, 0..1). Even-odd over all three rings: the hole is outside
    # (two crossings), the island inside (one), no ring marked as a hole.
    rings = (square(0, 0, 10, 10), square(4, 4, 6, 6, clockwise=False), square(20, 0, 21, 1))
    county = PreparedCounty.build(County("26999", "Test", rings))
    assert county.contains(1.0, 1.0)  # in the square, outside the hole
    assert not county.contains(5.0, 5.0)  # in the hole
    assert county.contains(20.5, 0.5)  # on the island
    assert not county.contains(15.0, 0.5)  # between square and island
    assert even_odd_contains(rings, 5.0, 5.0) is False
    assert even_odd_contains(rings, 1.0, 1.0) is True


def test_ring_orientation_does_not_matter():
    for clockwise in (True, False):
        county = PreparedCounty.build(County("26999", "T", (square(0, 0, 1, 1, clockwise),)))
        assert county.contains(0.5, 0.5)
        assert not county.contains(1.5, 0.5)


# Four unit squares meeting at (1, 1):
#
#     C (0..1, 1..2) | D (1..2, 1..2)
#     ---------------+---------------
#     A (0..1, 0..1) | B (1..2, 0..1)
#
# B and D are walked counter-clockwise, A and C clockwise, so each shared edge
# is stored in opposite directions by its two owners - the case the canonical
# edge order exists for.
QUAD = CountySet(
    [
        County("26001", "A", (square(0, 0, 1, 1),)),
        County("26003", "B", (square(1, 0, 2, 1, clockwise=False),)),
        County("26005", "C", (square(0, 1, 1, 2),)),
        County("26007", "D", (square(1, 1, 2, 2, clockwise=False),)),
    ],
    source="synthetic squares",
)


@pytest.mark.parametrize(
    "lon, lat, expected, why",
    [
        (1.0, 0.5, ["26003"], "on the A|B north-south line: the county EAST (B)"),
        (1.0, 1.5, ["26007"], "on the C|D north-south line: east (D)"),
        (0.5, 1.0, ["26005"], "on the A/C east-west line: the county NORTH (C)"),
        (1.5, 1.0, ["26007"], "on the B/D east-west line: north (D)"),
        (1.0, 1.0, ["26007"], "on the four-way corner: north-east (D)"),
        (0.0, 0.5, ["26001"], "on A's west outline: east of it is A"),
        (2.0, 0.5, [], "on B's east outline: east of it is outside"),
        (0.5, 0.0, ["26001"], "on A's south outline: north of it is A"),
        (0.5, 2.0, [], "on C's north outline: north of it is outside"),
        (0.0, 0.0, ["26001"], "A's south-west corner: north-east is A"),
        (2.0, 2.0, [], "D's north-east corner: north-east is outside"),
        (0.5, 0.5, ["26001"], "plainly inside A"),
    ],
)
def test_the_on_line_rule_east_then_north(lon, lat, expected, why):
    assert which(QUAD, lon, lat) == expected, why


def test_a_sloped_shared_edge_gives_an_exact_on_edge_point_to_one_county():
    # Two triangles sharing the sloped edge (0,0)-(1,3), walked in opposite
    # directions. The on-edge point at latitude 1 is longitude 1/3, computed
    # by the canonical formula itself so it is EXACTLY on the edge as the code
    # sees it: x = 0 + (1 - 0) * (1 - 0) / (3 - 0).
    west = County("26001", "W", (((0.0, 0.0), (-1.0, 3.0), (1.0, 3.0), (0.0, 0.0)),))
    east = County("26003", "E", (((0.0, 0.0), (1.0, 3.0), (2.0, 0.0), (0.0, 0.0)),))
    pair = CountySet([west, east], source="synthetic")
    x = 0.0 + (1.0 - 0.0) * (1.0 - 0.0) / (3.0 - 0.0)
    assert which(pair, x, 1.0) == ["26003"]  # on the line: the county east of it
    assert which(pair, math.nextafter(x, -1.0), 1.0) == ["26001"]


# ==========================================================================
# The rule on the real county lines.
# ==========================================================================


def _exact_on_edge_point(a, b):
    """A point the canonical crossing test sees as EXACTLY on edge a-b: the
    canonical lower endpoint first, latitude halfway, longitude by the same
    interpolation formula the program uses."""
    (xa, ya), (xb, yb) = sorted([a, b], key=lambda p: (p[1], p[0]))
    lat = (ya + yb) / 2.0
    return xa + (lat - ya) * (xb - xa) / (yb - ya), lat


def test_every_shared_county_line_point_lands_in_exactly_one_of_its_two_counties(shipped):
    """All 30,871 shared edges: a point exactly on each one - for a sloped edge
    the canonical interpolation at mid-latitude, for a horizontal one the
    midpoint - belongs to exactly one county, and it is one of the edge's two
    owners. The partition the even-odd rule promises, held on TIGER's own
    vertices rather than on a picture of them. (The endpoints are the vertex
    test's business: an endpoint can be a three-county junction, or sit on
    Michigan's outline where north-east of it is outside.)"""
    bad = []
    count = 0
    for a, b, owners in geo.edges_with_owners():
        if len(owners) != 2:
            continue
        if a[1] != b[1]:
            points = [_exact_on_edge_point(a, b)]
        else:
            points = [((a[0] + b[0]) / 2.0, a[1])]
        for lon, lat in points:
            got = which(shipped, lon, lat)
            if len(got) != 1 or got[0] not in owners:
                bad.append((lon, lat, sorted(owners), got))
        count += 1
    assert count == 30871
    assert not bad, bad[:5]


def test_a_point_on_the_eaton_ingham_line_goes_to_ingham_the_county_east(shipped):
    # Eaton (26045) is west of Ingham (26065); their common line is a
    # north-south range line near 84.60 W. On it, the rule says east: Ingham.
    shared = [
        (a, b)
        for a, b, owners in geo.edges_with_owners()
        if owners == {"26045", "26065"} and a[1] != b[1]
    ]
    assert len(shared) > 10
    for a, b in shared:
        lon, lat = _exact_on_edge_point(a, b)
        assert which(shipped, lon, lat) == ["26065"]
        # A centimetre either side, by the independent test: west is Eaton.
        assert geo.plain_even_odd(shipped.by_fips("26045").rings, lon - 1e-7, lat)
        assert geo.plain_even_odd(shipped.by_fips("26065").rings, lon + 1e-7, lat)


def test_a_point_on_the_alcona_iosco_line_goes_to_alcona_the_county_north(shipped):
    # Alcona (26001) is north of Iosco (26069); TIGER stores much of their
    # line as exactly horizontal edges (near 44.512 N). On each: north, Alcona.
    horizontal = [
        (a, b)
        for a, b, owners in geo.edges_with_owners()
        if owners == {"26001", "26069"} and a[1] == b[1]
    ]
    assert len(horizontal) > 10
    for a, b in horizontal:
        lon = (a[0] + b[0]) / 2.0
        assert which(shipped, lon, a[1]) == ["26001"]


def test_every_multi_county_vertex_goes_to_its_north_east_county(shipped):
    """The 115 vertices where three or four counties meet. Expected county:
    the one an independent even-odd test finds a hair north-east of the vertex
    (1e-7 degree east, 1e-12 north - the rule's 'east, then a far smaller step
    north'; the ratio must be smaller than any incident edge's slope, or a
    nearly-horizontal line leaving the vertex north-eastward would be crossed,
    which a ratio of 1e-2 was measured to do at 46.158691 N 86.615601 W)."""
    owners_at: dict = {}
    for a, b, owners in geo.edges_with_owners():
        for v in (a, b):
            owners_at.setdefault(v, set()).update(owners)
    corners = [v for v, o in owners_at.items() if len(o) >= 3]
    assert len(corners) == 115
    for lon, lat in corners:
        got = which(shipped, lon, lat)
        expected = [
            c.fips
            for c in shipped.counties
            if geo.plain_even_odd(c.rings, lon + 1e-7, lat + 1e-12)
        ]
        assert len(got) == 1 and got == expected, (lon, lat, got, expected)


# ==========================================================================
# The data has no overlap.
# ==========================================================================


def test_tiger_topology_every_edge_used_once_or_twice_never_twice_by_one_county():
    uses = geo.edge_use_counts()
    assert set(uses.values()) == {1, 2}
    assert sum(1 for n in uses.values() if n == 1) == 10720  # Michigan's outline
    for county in geo.county_document()["counties"]:
        seen = set()
        for ring in county["rings"]:
            for a, b in zip(ring[:-1], ring[1:]):
                key = frozenset((tuple(a), tuple(b)))
                assert key not in seen, county["name"]
                seen.add(key)


def test_no_point_of_a_statewide_grid_is_in_two_counties(shipped):
    # A 0.02-degree grid over the whole box TIGER's Michigan spans
    # (41.69-48.31 N, 90.42-82.12 W): about 137,000 points.
    in_two = []
    inside = 0
    lat = 41.69
    while lat <= 48.31:
        lon = -90.42
        while lon <= -82.12:
            got = shipped.containing(lon, lat)
            inside += len(got) == 1
            if len(got) > 1:
                in_two.append((lat, lon, [c.name for c in got]))
            lon += 0.02
        lat += 0.02
    assert not in_two, in_two[:5]
    assert inside > 60000  # Michigan, its water included, is most of the box


def test_the_binned_search_equals_the_plain_count_and_the_independent_test(shipped):
    """The latitude bins and the bounding-box prefilter are speed only: over
    random points, the binned answer equals the all-edges count and the
    suite's independent even-odd test, for every county whose box comes within
    0.1 degree of the point (the rest must simply be outside)."""
    rng = random.Random(20261022)
    for _ in range(4000):
        lon, lat = rng.uniform(-90.5, -82.0), rng.uniform(41.6, 48.4)
        binned = sorted(c.fips for c in shipped.containing(lon, lat))
        near = []
        for c in shipped.counties:
            xs = [p[0] for r in c.rings for p in r]
            ys = [p[1] for r in c.rings for p in r]
            if min(xs) - 0.1 <= lon <= max(xs) + 0.1 and min(ys) - 0.1 <= lat <= max(ys) + 0.1:
                near.append(c)
        plain = sorted(c.fips for c in near if even_odd_contains(c.rings, lon, lat))
        independent = sorted(c.fips for c in near if geo.plain_even_odd(c.rings, lon, lat))
        assert binned == plain == independent, (lon, lat)


# ==========================================================================
# zone_for: assignments and refusals.
# ==========================================================================


def test_zone_for_returns_the_registry_zone_by_identity_with_its_county(shipped):
    # Lansing, the Capitol: Ingham County; MCL 54.231(5) puts Ingham in the
    # south zone, and RECON section 2.2 puts it in L45G Grand Rapids.
    a = zone_for(42.7335, -84.5555, SPCS83, shipped)
    assert a == A.ZoneAssignment(zones.MI_SOUTH, "Ingham", "26065")
    assert a.zone is zones.MI_SOUTH
    b = zone_for(42.7335, -84.5555, SPCS2022, shipped)
    assert b.zone is zones.zone_by_code("261008") and b.county_fips == "26065"


def test_isle_royale_and_the_keweenaw_peninsula(shipped):
    # Both Keweenaw County; SPCS 83 North for both (MCL 54.231(3)); SPCS2022
    # U61K north of 47.65 N, U41H south of it.
    assert zone_for(48.0, -88.8, SPCS83, shipped).zone is zones.MI_NORTH
    assert zone_for(48.0, -88.8, SPCS2022, shipped).zone.code == "261018"
    assert zone_for(47.40, -88.0, SPCS2022, shipped).zone.code == "261016"
    assert zone_for(47.66, -88.4, SPCS2022, shipped).zone.code == "261018"  # water
    assert zone_for(47.64, -88.4, SPCS2022, shipped).zone.code == "261016"  # water


def test_auto_never_returns_the_statewide_zone(shipped):
    statewide = zones.zone_by_code("260001")
    rng = random.Random(7)
    for _ in range(3000):
        lat, lon = rng.uniform(41.7, 48.3), rng.uniform(-90.4, -82.1)
        try:
            assert zone_for(lat, lon, SPCS2022, shipped).zone is not statewide
        except AutoZoneOutsideError:
            pass


@pytest.mark.parametrize(
    "lat, lon, where",
    [
        (41.65, -83.55, "Toledo, Ohio"),
        (41.68, -86.25, "South Bend, Indiana"),
        (45.10, -87.63, "Marinette, Wisconsin"),
        (42.30, -83.00, "Windsor, Ontario"),
        (44.00, -87.50, "Lake Michigan, Wisconsin waters"),
        (41.80, -83.10, "Lake Erie, Ohio waters"),
        (0.0, 0.0, "the Gulf of Guinea"),
    ],
)
def test_a_point_in_no_michigan_county_is_refused_by_name(shipped, lat, lon, where):
    for system in AutoZoneSystem:
        with pytest.raises(AutoZoneOutsideError) as caught:
            zone_for(lat, lon, system, shipped)
        message = str(caught.value)
        assert f"latitude {lat:.8f}, longitude {lon:.8f}" in message
        assert "never assigns the nearest zone" in message
        assert county_file.COUNTIES_SOURCE in message
        assert caught.value.latitude == lat and caught.value.longitude == lon
        assert isinstance(caught.value, AutoZoneRefusal)


def test_a_positive_longitude_is_refused_with_the_sign_hint(shipped):
    with pytest.raises(AutoZoneOutsideError) as caught:
        zone_for(42.7335, 84.5555, SPCS83, shipped)
    assert "negative west" in str(caught.value)
    # No hint where negating the longitude would not land in Michigan either.
    with pytest.raises(AutoZoneOutsideError) as caught:
        zone_for(10.0, 84.5555, SPCS83, shipped)
    assert "check the sign" not in str(caught.value)


@pytest.mark.parametrize(
    "lat, lon",
    [
        (float("nan"), -84.5),
        (42.7, float("inf")),
        (True, -84.5),
        (42.7, "-84.5"),
        (None, -84.5),
        (90.5, -84.5),
        (42.7, -180.5),
    ],
)
def test_unusable_numbers_are_refused(shipped, lat, lon):
    with pytest.raises(AutoZoneInputError):
        zone_for(lat, lon, SPCS83, shipped)


def test_a_system_that_is_not_an_autozonesystem_is_refused(shipped):
    for system in ("SPCS 83", zones.MI_SOUTH, None):
        with pytest.raises(AutoZoneInputError):
            zone_for(42.7, -84.5, system, shipped)
    with pytest.raises(AutoZoneDataError):
        zone_for(42.7, -84.5, SPCS83, [shipped])


def test_a_point_two_counties_both_claim_is_refused_not_picked():
    # Two overlapping squares, both with real FIPS so the tables would have
    # rows: the overlap (0.5..1, 0..1) must refuse, naming both.
    overlap = CountySet(
        [
            County("26065", "Ingham", (square(0, 0, 1, 1),)),
            County("26045", "Eaton", (square(0.5, 0, 1.5, 1),)),
        ],
        source="synthetic overlap",
    )
    with pytest.raises(AutoZoneAmbiguousError) as caught:
        zone_for(0.75, 0.6, SPCS83, overlap)
    assert "Ingham (26065)" in str(caught.value) and "Eaton (26045)" in str(caught.value)
    assert zone_for(0.5, 0.25, SPCS83, overlap).county_name == "Ingham"


def test_a_county_with_no_table_row_is_refused():
    stray = CountySet([County("26999", "Nowhere", (square(0, 0, 1, 1),))], source="synthetic")
    with pytest.raises(AutoZoneDataError, match="no row"):
        zone_for(0.5, 0.5, SPCS83, stray)


def test_a_county_set_refuses_duplicates_impostors_and_emptiness():
    with pytest.raises(AutoZoneDataError, match="share FIPS"):
        CountySet([County("26001", "A", (square(0, 0, 1, 1),))] * 2, source="x")
    with pytest.raises(AutoZoneDataError):
        CountySet([("26001", "A")], source="x")
    with pytest.raises(AutoZoneDataError):
        CountySet([], source="x")


def test_require_tables_cover_refuses_a_missing_county_and_a_wrong_name(shipped):
    some = shipped.counties
    with pytest.raises(AutoZoneDataError, match="disagree about which counties"):
        A.require_tables_cover(CountySet(some[1:], source="short"))
    renamed = [County(c.fips, "Saint Clair" if c.fips == "26147" else c.name, c.rings) for c in some]
    with pytest.raises(AutoZoneDataError, match="Saint Clair"):
        A.require_tables_cover(CountySet(renamed, source="renamed"))
    A.require_tables_cover(shipped)  # and the shipped set passes


# ==========================================================================
# Speed, measured.
# ==========================================================================


def test_time_per_point_and_for_ten_thousand_points(shipped, capsys):
    rng = random.Random(3)
    points = [(rng.uniform(41.7, 48.3), rng.uniform(-90.4, -82.1)) for _ in range(10000)]
    start = time.perf_counter()
    for lat, lon in points:
        try:
            zone_for(lat, lon, SPCS83, shipped)
        except AutoZoneOutsideError:
            pass
    elapsed = time.perf_counter() - start
    with capsys.disabled():
        print(f"\nAuto zone: 10,000 points in {elapsed:.3f} s ({elapsed / 10000 * 1e6:.1f} us/point)")
    # Measured 0.08 s on the release machine. The bound is a regression
    # tripwire two orders of magnitude above that, not a performance claim.
    assert elapsed < 10.0
