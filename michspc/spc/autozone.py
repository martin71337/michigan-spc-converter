"""Auto zone: which State Plane zone a latitude/longitude falls in, by county.

**The rule is the law's, not a geometry of this program's choosing**
(docs/PLAN-options-autozone.md L3). Both Michigan systems are unions of whole
counties, and Michigan's counties extend into the Great Lakes:

* SPCS 83: MCL 54.231(3)-(5) defines each zone as "the area included in the
  following counties" (``michspc.spc.autozone_spcs83``).
* SPCS2022: NGS's eighteen low-distortion zones are unions of Census TIGER
  county lines, measured to 0.026 m, with one split - Keweenaw County's Isle
  Royale is its own zone (``michspc.spc.autozone_spcs2022``). The statewide
  zone 260001 is never chosen (owner's decision, plan section 1 item 2).

So a position is assigned by finding the ONE county polygon it lies in and
reading that county's zone from the system's table. A position in no county is
refused by name (L5): never the nearest zone, never a guess.

**Stdlib only, no file I/O** (tests/test_architecture.py). The polygons are
handed in as ``County`` records, already read and authenticated by
``michspc.fileio.counties`` - the only reader of the shipped county file.

Coordinates: decimal degrees, **longitude negative west**, as everywhere in
this codebase (docs/DESIGN.md section 7). A polygon vertex is
``(longitude, latitude)``, the order the county file stores it. Point-in-polygon
is planar on (longitude, latitude): the county lines are straight segments
between vertices TIGER publishes densely (72,545 for Michigan), and the
difference between a straight segment in degrees and a geodesic is far below
the source's own positional uncertainty (RECON.md section 4).

The point-in-polygon rule
-------------------------

**Even-odd crossing count over every ring of the county** - outer rings, holes
and islands alike, with no orientation needed - casting a ray due east from the
point. An edge between two vertices counts as crossed when

    y_low <= latitude < y_high   and   longitude < x_at(latitude)

where the edge's endpoints are first put in a canonical order (the one with the
smaller latitude first, longitude breaking a tie) and ``x_at`` is evaluated from
that canonical order. Horizontal edges never count.

Two consequences, both deliberate:

* **Deterministic on a line.** A point exactly on a county line belongs to the
  county it would be in after an infinitesimal step EAST; if it is still on a
  line after that (the line runs exactly east-west), after a further
  infinitesimally smaller step NORTH. So a point on a north-south line goes to
  the county east of it, a point on an east-west line to the county north of
  it, and a point exactly on a corner where four counties meet goes to the
  north-east one. This is the half-open crossing rule; it is written down
  because MCL 54.234 permits either zone for a tract on a line and leaves a
  point exactly on it undefined (RECON.md section 3), and this program must
  still give one answer, the same every time.
* **One county, not two.** Adjacent counties store a shared line with the same
  vertices (TIGER is topological: every one of Michigan's 41,591 county edges
  is used by exactly one county, on the state's outline, or by exactly two).
  Because the crossing test is computed from the canonical order, both counties
  evaluate the shared edge to the bit-identical crossing decision, and the
  point falls on one side of it for both. Even so, ``zone_for`` does not rely on
  that: it tests EVERY candidate county and refuses a point that two counties
  both claim, rather than picking one.

Speed: each county keeps its bounding box (the prefilter) and its edges binned
by latitude, so a point is tested only against the few edges whose latitude
span covers it. ``tests/test_autozone.py`` holds the binned search equal to the
plain all-edges count, and measures the time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping

from michspc.spc import autozone_spcs83, autozone_spcs2022
from michspc.spc.zones import SPCS83_ZONES, SPCS2022_ZONES, Zone

Vertex = tuple[float, float]
"""``(longitude, latitude)``, decimal degrees, longitude negative west."""

Ring = tuple[Vertex, ...]


# --------------------------------------------------------------------------
# Refusals.
# --------------------------------------------------------------------------


class AutoZoneRefusal(Exception):
    """Base class for every refusal in this module.

    A caller that only needs "Auto could not choose a zone for this point, say
    why" catches this. The subclasses separate what a surveyor is told
    differently. Carries the refused position as data (``latitude``,
    ``longitude``; decimal degrees, negative west) so a caller that knows which
    point of a file it was can name it in its own words; both are None on a
    refusal that is not about a position (a malformed county set).
    """

    def __init__(
        self,
        message: str,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> None:
        super().__init__(message)
        self.latitude = latitude
        self.longitude = longitude


class AutoZoneInputError(AutoZoneRefusal):
    """A latitude, longitude or system that is not a usable value."""


class AutoZoneOutsideError(AutoZoneRefusal):
    """The position is in no Michigan county, land or Great Lakes water."""


class AutoZoneAmbiguousError(AutoZoneRefusal):
    """Two or more county polygons both contain the position.

    Never resolved by picking one: it would mean the county data overlaps, and
    the zone would then depend on the order the counties were tested in. The
    shipped data has no overlap (tested); this refusal is the guard for the day
    a re-derived file does.
    """


class AutoZoneDataError(AutoZoneRefusal):
    """The county records or the zone tables are inconsistent with each other."""


# --------------------------------------------------------------------------
# The system an Auto zone is chosen in.
# --------------------------------------------------------------------------


class AutoZoneSystem(Enum):
    """Which State Plane system Auto chooses a zone in.

    The values are the registry's own ``Zone.system`` strings, so a chosen
    zone's system can be checked against the system asked for by equality.
    """

    SPCS83 = "SPCS 83"
    SPCS2022 = "SPCS2022"


@dataclass(frozen=True)
class ZoneAssignment:
    """The zone Auto chose for one position, and the county that decided it.

    ``zone`` is a record from ``michspc.spc.zones`` itself, by identity - never
    a copy - so every fact about the zone (constants, units, frame) is the
    registry's.
    """

    zone: Zone
    county_name: str
    """TIGER's county name, e.g. "St. Clair" (the county file's NAME field)."""

    county_fips: str
    """The five-digit county FIPS code, state 26 first, e.g. "26147"."""


# --------------------------------------------------------------------------
# County polygons.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class County:
    """One county's polygon, as the county file stores it.

    ``rings`` are every ring of the county's polygon - outer boundaries, holes
    and islands alike, in the file's order - each a closed sequence of
    ``(longitude, latitude)`` vertices whose last vertex repeats its first.
    The even-odd rule needs no ring to be marked as a hole.
    """

    fips: str
    name: str
    rings: tuple[Ring, ...]


_Edge = tuple[float, float, float, float]
"""A non-horizontal edge in canonical order: (x_low, y_low, x_high, y_high),
y_low < y_high."""


def _canonical_edges(rings: Iterable[Ring]) -> list[_Edge]:
    """Every non-horizontal edge of every ring, lower endpoint first.

    The canonical order is what makes the crossing decision for an edge shared
    by two counties bit-identical in both: each county may walk that edge in
    the opposite direction, and without the reordering the interpolated
    crossing longitude would be computed from the endpoints in two different
    orders and could differ in its last bit.
    """
    edges: list[_Edge] = []
    for ring in rings:
        for (xa, ya), (xb, yb) in zip(ring[:-1], ring[1:]):
            if ya == yb:
                continue  # a horizontal edge is never crossed by an eastward ray
            if (ya, xa) < (yb, xb):
                edges.append((xa, ya, xb, yb))
            else:
                edges.append((xb, yb, xa, ya))
    return edges


def _crosses(edge: _Edge, longitude: float, latitude: float) -> bool:
    """Whether a ray due east from the point crosses this canonical edge.

    The half-open rule: the edge's lower endpoint is included and its upper one
    excluded, and a point exactly on the edge (``longitude == x``) is NOT
    counted - which is what puts a point on a line in the county east (then
    north) of it. See the module docstring.
    """
    x0, y0, x1, y1 = edge
    if not (y0 <= latitude < y1):
        return False
    x = x0 + (latitude - y0) * (x1 - x0) / (y1 - y0)
    return longitude < x


def even_odd_contains(rings: Iterable[Ring], longitude: float, latitude: float) -> bool:
    """The plain all-edges even-odd test, with no index.

    The reference the binned search in ``PreparedCounty.contains`` is held
    equal to; also usable on any polygon (the suite recomputes NGS's zone
    membership with it).
    """
    inside = False
    for edge in _canonical_edges(rings):
        if _crosses(edge, longitude, latitude):
            inside = not inside
    return inside


_EDGES_PER_BIN = 8
"""Target edges per latitude bin. A speed knob only - the result is the same
for any value, which the suite holds over random points."""


@dataclass(frozen=True)
class PreparedCounty:
    """A county with its bounding box and its edges binned by latitude."""

    county: County
    min_longitude: float
    min_latitude: float
    max_longitude: float
    max_latitude: float
    _bin_height: float = field(repr=False)
    _bins: tuple[tuple[_Edge, ...], ...] = field(repr=False)

    @classmethod
    def build(cls, county: County) -> "PreparedCounty":
        xs = [x for ring in county.rings for x, _ in ring]
        ys = [y for ring in county.rings for _, y in ring]
        min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
        edges = _canonical_edges(county.rings)
        count = max(1, len(edges) // _EDGES_PER_BIN)
        height = (max_y - min_y) / count if max_y > min_y else 1.0
        bins: list[list[_Edge]] = [[] for _ in range(count)]
        for edge in edges:
            # An edge goes into every bin its latitude span touches. The bin
            # index is a monotone function of latitude (a subtraction and a
            # division by a positive constant are monotone in IEEE
            # arithmetic), so the bin a query latitude maps to always holds
            # every edge whose span contains that latitude.
            first = _bin_index(edge[1], min_y, height, count)
            last = _bin_index(edge[3], min_y, height, count)
            for k in range(first, last + 1):
                bins[k].append(edge)
        return cls(
            county=county,
            min_longitude=min_x,
            min_latitude=min_y,
            max_longitude=max_x,
            max_latitude=max_y,
            _bin_height=height,
            _bins=tuple(tuple(b) for b in bins),
        )

    def in_box(self, longitude: float, latitude: float) -> bool:
        """The prefilter. INCLUSIVE on every side: a point on the box's west
        edge can be inside the county by the on-line rule."""
        return (
            self.min_longitude <= longitude <= self.max_longitude
            and self.min_latitude <= latitude <= self.max_latitude
        )

    def contains(self, longitude: float, latitude: float) -> bool:
        if not self.in_box(longitude, latitude):
            return False
        k = _bin_index(latitude, self.min_latitude, self._bin_height, len(self._bins))
        inside = False
        for edge in self._bins[k]:
            if _crosses(edge, longitude, latitude):
                inside = not inside
        return inside


def _bin_index(latitude: float, min_latitude: float, height: float, count: int) -> int:
    k = int((latitude - min_latitude) / height)
    return 0 if k < 0 else (count - 1 if k >= count else k)


class CountySet:
    """The prepared counties ``zone_for`` searches, plus where they came from.

    Built once per process by ``michspc.fileio.counties`` (the shipped file is
    read and authenticated there) and reused for every point. ``source`` is the
    one-line description of the county data that a refusal names, e.g.
    "US Census TIGER/Line 2025 counties".
    """

    def __init__(self, counties: Iterable[County], source: str) -> None:
        prepared = []
        seen: dict[str, County] = {}
        for county in counties:
            if not isinstance(county, County):
                raise AutoZoneDataError(
                    f"A county set holds County records only; got "
                    f"{type(county).__name__} ({county!r})."
                )
            if county.fips in seen:
                raise AutoZoneDataError(
                    f"Two county records share FIPS {county.fips}: "
                    f"{seen[county.fips].name} and {county.name}. The zone "
                    f"tables are keyed by FIPS, so this would make a zone "
                    f"depend on which record was read last."
                )
            seen[county.fips] = county
            prepared.append(PreparedCounty.build(county))
        if not prepared:
            raise AutoZoneDataError("A county set must hold at least one county.")
        self._prepared: tuple[PreparedCounty, ...] = tuple(prepared)
        self.source = source

    @property
    def counties(self) -> tuple[County, ...]:
        return tuple(p.county for p in self._prepared)

    def by_fips(self, fips: str) -> County:
        for p in self._prepared:
            if p.county.fips == fips:
                return p.county
        raise KeyError(fips)

    def containing(self, longitude: float, latitude: float) -> list[County]:
        """EVERY county whose polygon contains the point, in data order."""
        return [p.county for p in self._prepared if p.contains(longitude, latitude)]


# --------------------------------------------------------------------------
# The assignment.
# --------------------------------------------------------------------------


def _require_number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AutoZoneInputError(
            f"Auto zone needs the {what} as a number of decimal degrees; got "
            f"{type(value).__name__} ({value!r})."
        )
    number = float(value)
    if not math.isfinite(number):
        raise AutoZoneInputError(
            f"Auto zone needs a finite {what}; got {value!r}."
        )
    return number


def _position_text(latitude: float, longitude: float) -> str:
    return f"latitude {latitude:.8f}, longitude {longitude:.8f}"


def zone_for(
    latitude: float,
    longitude: float,
    system: AutoZoneSystem,
    counties: CountySet,
) -> ZoneAssignment:
    """The zone of ``system`` that the county containing the position belongs to.

    ``latitude`` and ``longitude`` are decimal degrees, **longitude negative
    west**, in the frame of the system asked for (NAD83(2011) for SPCS 83,
    NATRF2022 for SPCS2022 - plan L4; this function cannot check that, and the
    caller states it). Refuses, never guesses:

    * ``AutoZoneInputError`` - not a finite number, latitude beyond +/-90 or
      longitude beyond +/-180, or ``system`` not an ``AutoZoneSystem``;
    * ``AutoZoneOutsideError`` - in no Michigan county (outside Michigan, or in
      another state's or Canada's water). The nearest zone is never offered;
    * ``AutoZoneAmbiguousError`` - two county polygons both contain it;
    * ``AutoZoneDataError`` - the county has no row in the system's table.
    """
    lat = _require_number(latitude, "latitude")
    lon = _require_number(longitude, "longitude")
    if not -90.0 <= lat <= 90.0:
        raise AutoZoneInputError(
            f"Latitude {lat!r} is not between -90 and 90 degrees.",
            latitude=lat,
            longitude=lon,
        )
    if not -180.0 <= lon <= 180.0:
        raise AutoZoneInputError(
            f"Longitude {lon!r} is not between -180 and 180 degrees. Auto zone "
            f"takes a signed longitude, negative west.",
            latitude=lat,
            longitude=lon,
        )
    if not isinstance(system, AutoZoneSystem):
        raise AutoZoneInputError(
            f"Auto zone needs an AutoZoneSystem (SPCS83 or SPCS2022); got "
            f"{type(system).__name__} ({system!r}).",
            latitude=lat,
            longitude=lon,
        )
    if not isinstance(counties, CountySet):
        raise AutoZoneDataError(
            f"Auto zone needs the loaded CountySet; got {type(counties).__name__}.",
            latitude=lat,
            longitude=lon,
        )

    found = counties.containing(lon, lat)
    if not found:
        hint = ""
        if lon > 0.0 and counties.containing(-lon, lat):
            hint = (
                " The longitude is positive (east of Greenwich); Michigan's "
                "longitudes are negative here (negative west), and the same "
                "number negated would be inside Michigan - check the sign "
                "convention of the input."
            )
        raise AutoZoneOutsideError(
            f"The point at {_position_text(lat, lon)} is in no Michigan "
            f"county ({counties.source}, Great Lakes waters included), so "
            f"Auto cannot choose a {system.value} zone for it. Auto never "
            f"assigns the nearest zone: a point outside Michigan or in "
            f"another state's or Canada's water has no Michigan zone. Check "
            f"the coordinate, or choose the zone yourself.{hint}",
            latitude=lat,
            longitude=lon,
        )
    if len(found) > 1:
        names = ", ".join(f"{c.name} ({c.fips})" for c in found)
        raise AutoZoneAmbiguousError(
            f"The point at {_position_text(lat, lon)} lies inside more than "
            f"one county polygon - {names} - in {counties.source}. The county "
            f"data overlaps there, and Auto refuses rather than pick one of "
            f"them: the zone would depend on the order the counties were "
            f"tested in. Choose the zone yourself.",
            latitude=lat,
            longitude=lon,
        )
    county = found[0]

    if system is AutoZoneSystem.SPCS83:
        table: Mapping[str, Zone] = autozone_spcs83.SPCS83_ZONE_BY_FIPS
        zone = table.get(county.fips)
    else:
        zone = autozone_spcs2022.ldp_zone(county.fips, lat)
    if zone is None:
        raise AutoZoneDataError(
            f"{county.name} County ({county.fips}) has no row in the "
            f"{system.value} county table, so no zone can be read for the "
            f"point at {_position_text(lat, lon)}. The county data and the "
            f"table disagree about which counties exist.",
            latitude=lat,
            longitude=lon,
        )
    if zone.system != system.value:
        raise AutoZoneDataError(
            f"The {system.value} table maps {county.name} County to "
            f"{zone}, which is a {zone.system} zone.",
            latitude=lat,
            longitude=lon,
        )
    return ZoneAssignment(zone=zone, county_name=county.name, county_fips=county.fips)


def zones_choosable(system: AutoZoneSystem) -> tuple[Zone, ...]:
    """Every zone ``zone_for`` can return for ``system``, in registry order.

    Read from the same tables ``zone_for`` reads - the SPCS 83 county table,
    and the SPCS2022 table plus the Isle Royale zone its rule adds - so a
    caller that must check something against EVERY zone Auto might choose
    (``job``'s unit gate, work package Z2) asks the rule itself rather than a
    second list that could drift from it. Never includes the statewide
    SPCS2022 zone 260001, which Auto never chooses.
    """
    if not isinstance(system, AutoZoneSystem):
        raise AutoZoneInputError(
            f"zones_choosable needs an AutoZoneSystem (SPCS83 or SPCS2022); "
            f"got {type(system).__name__} ({system!r})."
        )
    if system is AutoZoneSystem.SPCS83:
        used = set(autozone_spcs83.SPCS83_ZONE_BY_FIPS.values())
        registry = SPCS83_ZONES
    else:
        used = set(autozone_spcs2022.LDP_ZONE_BY_FIPS.values()) | {
            autozone_spcs2022.ISLE_ROYALE_ZONE
        }
        registry = SPCS2022_ZONES
    return tuple(zone for zone in registry if zone in used)


def require_tables_cover(counties: CountySet) -> None:
    """Refuse a county set and the zone tables that do not name the same counties.

    Both directions, by FIPS, and the county NAME each table row states must be
    the name the county data gives that FIPS: the statute lists counties by
    name, the data by FIPS, and this is where the two are joined. Called by the
    loader once, so a mismatch fails at load, not at the first point that lands
    in the missing county.
    """
    data = {c.fips: c.name for c in counties.counties}
    for label, names in (
        ("SPCS 83", autozone_spcs83.COUNTY_NAME_BY_FIPS),
        ("SPCS2022", autozone_spcs2022.COUNTY_NAME_BY_FIPS),
    ):
        missing = sorted(set(data) - set(names))
        extra = sorted(set(names) - set(data))
        if missing or extra:
            raise AutoZoneDataError(
                f"The {label} county table and {counties.source} disagree "
                f"about which counties exist: in the data only {missing}, in "
                f"the table only {extra}."
            )
        wrong = sorted(
            f"{fips}: table {names[fips]!r}, data {data[fips]!r}"
            for fips in data
            if names[fips] != data[fips]
        )
        if wrong:
            raise AutoZoneDataError(
                f"The {label} county table names counties differently from "
                f"{counties.source}: {'; '.join(wrong)}."
            )
