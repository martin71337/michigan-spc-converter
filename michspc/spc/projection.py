"""One door to every projection engine.

A zone's ``definition`` record says which projection it is - by its Python type,
and by nothing else. This module holds the single table that turns that type
into the three things a caller needs: the ``ProjectionKind`` label, the
constructor that derives the zone constants, and the forward and inverse
mapping functions. One entry supplies all four, so the name a job record prints
and the mathematics it describes are incapable of disagreeing.

That was not true before. ``LambertTwoParallelDef`` carried a ``kind`` field
that nothing read (docs/DESIGN.md amendment #21: "``ProjectionKind`` is declared
and read nowhere"), and ``convert.py`` imported ``lambert.forward`` by name, so
a second projection could only arrive by editing every call site. The field is
deleted and the imports go through here.

**The public surface:**

    constants_for(zone)                -> the zone's constants record, cached
    forward(latitude, longitude, zone) -> GridPoint
    inverse(northing, easting, zone)   -> GeodeticPoint

Every engine answers in the same units and conventions, which are the ones
``lambert`` established and the other two were written to match:

  * Latitudes and longitudes at the API boundary are decimal degrees.
  * Longitude is signed, NEGATIVE WEST. Each engine marks the places where the
    manual's positive-west convention is converted.
  * Linear units are meters.
  * Convergence is decimal degrees, positive east of the central meridian.

``GridPoint``, ``GeodeticPoint`` and the two input guards live here rather than
in ``lambert`` because all three engines produce and consume them. ``lambert``
re-exports them under their old names so existing imports keep working.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Mapping, NamedTuple

from michspc.spc.ellipsoid import GRS80, Ellipsoid
from michspc.spc.zones import (
    LambertOneParallelDef,
    LambertTwoParallelDef,
    ObliqueMercatorCenterDef,
    ProjectionKind,
    TransverseMercatorDef,
    Zone,
)

if TYPE_CHECKING:  # pragma: no cover - annotations only
    # The engines import this module, so naming their constants records at
    # runtime would be a cycle. ``from __future__ import annotations`` makes
    # every annotation below a string, so the union costs nothing at import and
    # a reader still sees what ``constants_for`` returns.
    from michspc.spc.lambert import LambertConstants
    from michspc.spc.omerc import ObliqueMercatorConstants
    from michspc.spc.tm import TransverseMercatorConstants

    ProjectionConstants = (
        LambertConstants | TransverseMercatorConstants | ObliqueMercatorConstants
    )


class ProjectionUnavailableError(NotImplementedError):
    """No engine is registered for this kind of zone definition.

    Fails closed, and names the type it was handed alongside the projections
    that do exist - the ``require_vertical_pair`` voice (michspc.spc.vertical).
    A zone carrying an unregistered definition must refuse rather than fall
    through to whichever engine happens to be imported: every projection here
    produces an ordinary-looking coordinate from an ordinary-looking latitude,
    so the wrong engine is silent by construction.

    A ``NotImplementedError`` because that is what it is - a capability this
    program does not have - and it is still an ``Exception``, so no caller
    catching broadly lets it pass.
    """


@dataclass(frozen=True)
class GridPoint:
    """A point on the grid, with the two quantities that describe the grid there."""

    northing: float
    """Meters."""

    easting: float
    """Meters."""

    convergence: float
    """Decimal degrees, positive east of the central meridian."""

    scale_factor: float
    """Grid scale factor at the point (dimensionless)."""


@dataclass(frozen=True)
class GeodeticPoint:
    """A geodetic position, with the grid quantities that apply at it."""

    latitude: float
    """Decimal degrees north."""

    longitude: float
    """Decimal degrees, NEGATIVE WEST."""

    convergence: float
    """Decimal degrees, positive east of the central meridian."""

    scale_factor: float
    """Grid scale factor at the point (dimensionless)."""


def _require_valid_geodetic(latitude: float, longitude: float) -> None:
    """Refuse a latitude or longitude that is out of domain or not a number.

    Every engine calls this. Neither an engine cross-check nor the zone-extent
    warning can protect against a bad input here, because every engine is handed
    the same bad value and agrees perfectly on the wrong answer - so the check
    has to happen before any of them runs.

    The longitude domain matters more than it looks. This program uses signed
    longitude, negative west; the geoid grid and many datasets use the 0-360
    east convention, in which Michigan's 84.5555 W is 275.4445. That value is a
    perfectly ordinary float, it produces a coordinate with no warning worth
    noticing, and it is wrong by thousands of kilometres. Found by the interim
    review gate; see docs/DESIGN.md amendment #10.
    """
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError(
            f"Latitude {latitude!r} and longitude {longitude!r} must both be "
            f"finite numbers. A coordinate that is not a number cannot be "
            f"projected, and must never be written to a file."
        )
    if not -90.0 < latitude < 90.0:
        raise ValueError(
            f"Latitude {latitude} is not a valid geodetic latitude; it must lie "
            f"strictly between -90 and 90 degrees."
        )
    if not -180.0 <= longitude <= 180.0:
        raise ValueError(
            f"Longitude {longitude} is outside the range -180 to 180. This "
            f"program uses SIGNED longitude, negative west - Michigan runs from "
            f"about -83 to -90. A value between 180 and 360 is the 0-360 east "
            f"convention: subtract 360 from it ({longitude - 360.0:.6f} here). "
            f"Converting it as given would place the point thousands of "
            f"kilometres away."
        )


def _require_finite_grid(northing: float, easting: float) -> None:
    """Refuse a grid coordinate that is not a number, before it is inverted."""
    if not math.isfinite(northing) or not math.isfinite(easting):
        raise ValueError(
            f"Northing {northing!r} and easting {easting!r} must both be finite "
            f"numbers. Check the input file for a blank or corrupt coordinate."
        )


class ProjectionEngine(NamedTuple):
    """Everything one kind of zone definition needs, in one entry.

    A tuple rather than four parallel dictionaries, so a projection cannot be
    half-registered: the kind, the constants and the two mapping functions are
    added or absent together.
    """

    kind: ProjectionKind
    constants_from: Callable[..., "ProjectionConstants"]
    """``(definition, ellipsoid) -> constants record`` for that engine."""

    forward: Callable[[float, float, "ProjectionConstants"], GridPoint]
    inverse: Callable[[float, float, "ProjectionConstants"], GeodeticPoint]


@lru_cache(maxsize=None)
def _engines() -> Mapping[type, ProjectionEngine]:
    """THE dispatch table, keyed on the definition record's type.

    Built on first use rather than at import, because each engine module imports
    ``GridPoint`` and the input guards from here. The dependency runs one way at
    import time (engines -> this module) and the other way at call time (this
    module -> engines), so every module in the core stays importable on its own
    and there is still exactly one table.

    Read-only: a ``MappingProxyType`` over a dict built once, so no caller can
    register a fifth projection at runtime and no test can leave one behind.
    """
    from michspc.spc import lambert, omerc, tm

    return MappingProxyType(
        {
            LambertTwoParallelDef: ProjectionEngine(
                kind=ProjectionKind.LAMBERT_CONIC_2SP,
                constants_from=lambert.LambertConstants.from_two_parallels,
                forward=lambert.forward,
                inverse=lambert.inverse,
            ),
            LambertOneParallelDef: ProjectionEngine(
                kind=ProjectionKind.LAMBERT_CONIC_1SP,
                constants_from=lambert.LambertConstants.from_one_parallel,
                forward=lambert.forward,
                inverse=lambert.inverse,
            ),
            TransverseMercatorDef: ProjectionEngine(
                kind=ProjectionKind.TRANSVERSE_MERCATOR,
                constants_from=tm.TransverseMercatorConstants.from_definition,
                forward=tm.forward,
                inverse=tm.inverse,
            ),
            ObliqueMercatorCenterDef: ProjectionEngine(
                kind=ProjectionKind.OBLIQUE_MERCATOR,
                constants_from=omerc.ObliqueMercatorConstants.from_definition,
                forward=omerc.forward,
                inverse=omerc.inverse,
            ),
        }
    )


def registered_definition_types() -> tuple[type, ...]:
    """Every definition type the dispatcher can compute, in table order.

    Public so the suite can check the table against ``zones.ProjectionDef``
    without reaching into a private name - a projection added to the union and
    forgotten here would otherwise only be found by a zone that refuses.
    """
    return tuple(_engines())


def _engine_for(definition: object) -> ProjectionEngine:
    """The engine for this definition record, or a refusal naming its type."""
    engine = _engines().get(type(definition))
    if engine is None:
        implemented = ", ".join(
            f"{entry.kind.value} ({record.__name__})"
            for record, entry in _engines().items()
        )
        raise ProjectionUnavailableError(
            f"No projection engine is registered for a zone definition of type "
            f"{type(definition).__name__} ({definition!r}). This program cannot "
            f"convert a coordinate in a projection it does not implement, and "
            f"must not fall through to another one: every projection here turns "
            f"an ordinary latitude into an ordinary-looking coordinate, so the "
            f"wrong engine would be silent. The projections implemented are: "
            f"{implemented}."
        )
    return engine


def projection_kind_for_definition(definition: object) -> ProjectionKind:
    """Which projection this definition record is, from the dispatch table.

    ``Zone.projection_kind`` is this function; it lives here so the kind and the
    engine come out of one entry.
    """
    return _engine_for(definition).kind


@lru_cache(maxsize=None)
def constants_for(zone: Zone, ellipsoid: Ellipsoid = GRS80) -> ProjectionConstants:
    """Derive the working constants for a registry zone, once.

    Dispatches on ``type(zone.definition)`` and returns that engine's own
    constants record - ``LambertConstants``, ``TransverseMercatorConstants`` or
    ``ObliqueMercatorConstants``. Each carries the zone's code, stamped here.

    Cached, so a file of several thousand points does not re-derive the same
    constants per row. The cache is what made it possible to delete the
    ``constants=`` parameters the conversion functions used to accept: callers
    now get the per-file efficiency for free and have no way to pair one zone's
    constants with another zone's identity (docs/DESIGN.md amendment #11).

    ``maxsize=None`` rather than a bound: the zone registry is finite and
    immutable, so the cache cannot grow without bound, and a bound small enough
    to evict would silently re-derive constants inside a single job's row loop.

    Zone and Ellipsoid are both frozen dataclasses and therefore hashable, so
    they are usable as cache keys directly.
    """
    constants = _engine_for(zone.definition).constants_from(
        zone.definition, ellipsoid
    )
    return replace(constants, zone_code=zone.code)


def forward(latitude: float, longitude: float, zone: Zone) -> GridPoint:
    """Geodetic to grid, in whichever projection this zone is.

    Decimal degrees in, meters out; longitude negative west.
    """
    return _engine_for(zone.definition).forward(
        latitude, longitude, constants_for(zone)
    )


def inverse(northing: float, easting: float, zone: Zone) -> GeodeticPoint:
    """Grid to geodetic, in whichever projection this zone is.

    Meters in, decimal degrees out; longitude negative west.
    """
    return _engine_for(zone.definition).inverse(
        northing, easting, constants_for(zone)
    )
