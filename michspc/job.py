"""One conversion job, end to end.

Reads a coordinate file, converts every point, and produces the three outputs
the owner specified: a clean PNEZD export for CAD, a full-audit CSV, and a
plain-text job record explaining both.

This module is the only place that knows about all three layers at once. The
computation core knows nothing of files; the file layer knows nothing of zones;
this joins them and owns the unit conversion at the boundary.

Nothing here writes anything. ``run`` produces an immutable ``JobResult``; the
caller decides whether and where to commit it to disk. That keeps the whole
pipeline testable without a filesystem, and keeps the GUI's "preview then
convert" behaviour honest - what is previewed is what is written.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from michspc.fileio import geoid18, pnezd
from michspc.spc.convert import (
    ConversionWarning,
    PointConversion,
    WarningCode,
    convert_point,
    easting_looks_wrong_for_zone,
    project_point,
)
from michspc.spc.factors import Factors, factors_at
from michspc.spc.lambert import constants_for
from michspc.spc.units import LinearUnit
from michspc.spc.zones import Zone


class Direction(Enum):
    """What kind of conversion this job performs."""

    ZONE_TO_ZONE = "zone to zone"
    GEODETIC_TO_ZONE = "geodetic to State Plane"
    ZONE_TO_GEODETIC = "State Plane to geodetic"


class LongitudeConvention(Enum):
    """Which sign convention the input or output longitudes use.

    Deliberately has no default anywhere in the program. The manual and the
    owner's prior MATLAB tool use positive-west; NCAT, OPUS, GPS and every GIS
    use negative-west. Choosing wrongly throws a Michigan point about 340 miles,
    and the two are indistinguishable from the numbers alone, so the user states
    it every run (docs/DESIGN.md section 7).
    """

    NEGATIVE_WEST = "negative west (-84.37), as used by OPUS, NCAT, GPS and GIS"
    POSITIVE_WEST = "positive west (84.37), as used by NOAA Manual NOS NGS 5"

    def to_signed(self, longitude: float) -> float:
        return -longitude if self is LongitudeConvention.POSITIVE_WEST else longitude

    def from_signed(self, longitude: float) -> float:
        return -longitude if self is LongitudeConvention.POSITIVE_WEST else longitude


@dataclass(frozen=True)
class JobSettings:
    """Everything the user chose. Recorded verbatim in the job record."""

    input_path: Path
    output_directory: Path
    direction: Direction

    source_zone: Zone | None
    target_zone: Zone | None

    input_unit: LinearUnit
    output_unit: LinearUnit

    longitude_convention: LongitudeConvention = LongitudeConvention.NEGATIVE_WEST
    apply_geoid: bool = True


@dataclass(frozen=True)
class ConvertedPoint:
    """One point, converted, with the evidence for it."""

    row: pnezd.PnezdRow
    conversion: PointConversion
    factors: Factors

    output_northing: float
    output_easting: float
    """In the OUTPUT unit, ready to format."""

    output_elevation: float | None
    """In the output unit. Unchanged by the conversion - orthometric height does
    not depend on the horizontal zone - but re-expressed if the units differ."""

    warnings: tuple[ConversionWarning, ...] = field(default_factory=tuple)

    @property
    def point_id(self) -> str:
        return self.row.point_id


@dataclass(frozen=True)
class JobResult:
    """The complete outcome of a job. Immutable."""

    settings: JobSettings
    points: tuple[ConvertedPoint, ...]
    input_sha256: str
    input_row_count: int
    skipped_blank_lines: int
    geoid_model: str | None

    @property
    def warnings(self) -> tuple[tuple[str, ConversionWarning], ...]:
        """Every warning, paired with the point identifier that raised it."""
        return tuple(
            (point.point_id, warning)
            for point in self.points
            for warning in point.warnings
        )

    def warnings_of(self, code: WarningCode) -> tuple[tuple[str, ConversionWarning], ...]:
        return tuple((pid, w) for pid, w in self.warnings if w.code is code)

    @property
    def points_without_elevation(self) -> tuple[ConvertedPoint, ...]:
        return tuple(p for p in self.points if not p.factors.has_elevation)

    @property
    def combined_factors(self) -> tuple[float, ...]:
        return tuple(
            p.factors.combined_factor
            for p in self.points
            if p.factors.combined_factor is not None
        )

    @property
    def grid_scale_factors(self) -> tuple[float, ...]:
        return tuple(p.factors.grid_scale_factor for p in self.points)


def file_sha256(path: Path) -> str:
    """Hash the input file so the job record identifies exactly what was read.

    A job record that names a file but not its contents proves nothing six
    months later, when the file has been edited.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(settings: JobSettings, source: pnezd.PnezdFile | None = None) -> JobResult:
    """Execute a job. Reads if no parsed file is supplied; never writes."""
    if settings.direction is Direction.ZONE_TO_ZONE:
        if settings.source_zone is None or settings.target_zone is None:
            raise ValueError(
                "A zone-to-zone conversion needs both a source and a target "
                "zone. Neither is inferred from the coordinates."
            )
    elif settings.direction is Direction.GEODETIC_TO_ZONE:
        if settings.target_zone is None:
            raise ValueError("A geodetic conversion needs a target zone.")
    elif settings.source_zone is None:
        raise ValueError("Converting to geodetic needs the zone the file is in.")

    parsed = source or pnezd.read(settings.input_path)

    source_constants = (
        constants_for(settings.source_zone) if settings.source_zone else None
    )
    target_constants = (
        constants_for(settings.target_zone) if settings.target_zone else None
    )

    grid = geoid18.default_grid() if settings.apply_geoid else None

    points: list[ConvertedPoint] = []
    for row in parsed.rows:
        points.append(
            _convert_row(row, settings, source_constants, target_constants, grid)
        )

    return JobResult(
        settings=settings,
        points=tuple(points),
        input_sha256=file_sha256(settings.input_path)
        if settings.input_path.exists()
        else "",
        input_row_count=len(parsed.rows),
        skipped_blank_lines=parsed.skipped_blank_lines,
        geoid_model=geoid18.GEOID_MODEL_NAME if settings.apply_geoid else None,
    )


def _convert_row(
    row: pnezd.PnezdRow,
    settings: JobSettings,
    source_constants,
    target_constants,
    grid,
) -> ConvertedPoint:
    context = f"point {row.point_id}"
    warnings: list[ConversionWarning] = []

    if settings.direction is Direction.GEODETIC_TO_ZONE:
        # The file's "northing" and "easting" columns hold latitude and
        # longitude. The longitude is normalised to the program's signed
        # convention here, at the boundary, and nowhere else.
        latitude = row.northing
        longitude = settings.longitude_convention.to_signed(row.easting)
        conversion = project_point(
            latitude, longitude, settings.target_zone, context, target_constants
        )
        output_unit = settings.output_unit
        output_northing = output_unit.from_meters(conversion.target_northing)
        output_easting = output_unit.from_meters(conversion.target_easting)
    else:
        northing_m = settings.input_unit.to_meters(row.northing)
        easting_m = settings.input_unit.to_meters(row.easting)

        if easting_looks_wrong_for_zone(easting_m, settings.source_zone):
            warnings.append(
                ConversionWarning(
                    code=WarningCode.EASTING_UNLIKE_SELECTED_ZONE,
                    message=(
                        f"{context}: an easting of {row.easting:,.3f} "
                        f"{settings.input_unit.code} does not look like "
                        f"{settings.source_zone.name} data, whose eastings sit "
                        f"near {settings.input_unit.from_meters(settings.source_zone.definition.easting_origin):,.0f} "
                        f"{settings.input_unit.code}. Check that the source "
                        f"zone and the input units are the ones this file is "
                        f"actually in - selecting the wrong source zone is the "
                        f"easiest mistake to make with this program."
                    ),
                )
            )

        if settings.direction is Direction.ZONE_TO_GEODETIC:
            conversion = convert_point(
                northing_m,
                easting_m,
                settings.source_zone,
                settings.source_zone,
                context,
                source_constants,
                source_constants,
            )
            output_northing = conversion.latitude
            output_easting = settings.longitude_convention.from_signed(
                conversion.longitude
            )
        else:
            conversion = convert_point(
                northing_m,
                easting_m,
                settings.source_zone,
                settings.target_zone,
                context,
                source_constants,
                target_constants,
            )
            output_northing = settings.output_unit.from_meters(
                conversion.target_northing
            )
            output_easting = settings.output_unit.from_meters(conversion.target_easting)

    # Elevation is orthometric height: it does not change with the horizontal
    # zone. Only its unit changes.
    elevation_m = (
        settings.input_unit.to_meters(row.elevation)
        if row.elevation is not None
        else None
    )
    output_elevation = (
        settings.output_unit.from_meters(elevation_m)
        if elevation_m is not None
        and settings.direction is not Direction.ZONE_TO_GEODETIC
        else row.elevation
    )

    geoid_height = None
    if grid is not None and elevation_m is not None:
        try:
            geoid_height = geoid18.geoid_height(
                conversion.latitude, conversion.longitude, grid
            )
        except geoid18.GeoidError:
            # Outside the shipped tile. The horizontal conversion is unaffected
            # and stands; only the elevation-dependent factors are unavailable,
            # and factors_at reports that as None rather than inventing one.
            geoid_height = None

    factors = factors_at(
        conversion.target_scale_factor, elevation_m, geoid_height
    )

    return ConvertedPoint(
        row=row,
        conversion=conversion,
        factors=factors,
        output_northing=output_northing,
        output_easting=output_easting,
        output_elevation=output_elevation,
        warnings=tuple(warnings) + conversion.warnings,
    )
