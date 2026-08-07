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

from michspc.fileio import formatting, geoid18, pnezd
from michspc.spc.convert import (
    ConversionWarning,
    PointConversion,
    WarningCode,
    convert_point,
    easting_looks_wrong_for_zone,
    project_point,
)
from michspc.spc.factors import Factors, factors_at
from michspc.spc.frames import NAD83_2011, ReferenceFrame
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

    # The sign and the worked example are what disambiguate; the attribution
    # tail ("as used by OPUS, NCAT, GPS and GIS" / "as used by NOAA Manual NOS
    # NGS 5") was dropped by the owner (docs/DESIGN.md amendments #16 note 2 and
    # #17). These strings are BOTH the dropdown's text and the job record's
    # "Longitude" line, and the owner decided the shorter wording for both: the
    # record states the conversion direction and each zone's defining constants
    # immediately around that line, so the convention is not left contextless.
    NEGATIVE_WEST = "negative west (-84.37)"
    POSITIVE_WEST = "positive west (84.37)"

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

    longitude_convention: LongitudeConvention | None
    """Which sign convention the file's longitudes use.

    **Required, with no default** (docs/DESIGN.md section 7). A default here is
    the failure the rule exists to prevent: a geodetic input file written
    positive west, converted as though it were negative west, lands 11,634,618 m
    away carrying nothing louder than an outside-zone-extent warning. The field
    is declared before the defaulted fields only because a frozen dataclass may
    not put a field without a default after one that has one.

    ``None`` is a statement, not an absence: "this job never consults the
    convention". Only a pure zone-to-zone job may say it - the grid coordinates
    on both ends carry no longitude - and ``run`` refuses any other direction
    that arrives with None rather than choosing one.
    """

    apply_geoid: bool = True

    geodetic_frame: ReferenceFrame = NAD83_2011
    """The reference frame a geodetic INPUT file's latitudes and longitudes are
    read as. Ignored when the input is State Plane, because a zone carries its
    own frame.

    Unlike the longitude convention this one does carry a default, and the
    reason is that the two risks are not comparable. The longitude sign is a
    real coin-flip - the manual uses one convention, every GPS and GIS the other
    - and getting it wrong throws a Michigan point about 340 miles, so
    docs/DESIGN.md section 7 forbids a default there. The frame is not a
    coin-flip today: every zone in the registry is NAD83(2011), NATRF2022 has no
    zones and no transformation (docs/DESIGN.md section 10), so the only way to
    reach a mismatch is for a caller to set this field to NATRF2022 on purpose -
    and ``project_point`` then refuses it, which is finding 1's whole point.

    It is a field on the settings rather than a constant inside the loop
    precisely so it is visible: the job record states the frame the input was
    interpreted as, because a record that does not say which frame it assumed is
    not a record.
    """


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

    input_sha256: str | None
    """SHA-256 of the bytes that were actually converted, or None.

    Comes from the reader, which hashes what it decoded (``pnezd.read``), and
    never from a second look at ``settings.input_path``. Hashing the path
    independently certified a file rather than a conversion: a caller supplying
    an in-memory ``source`` while pointing ``input_path`` at README.md produced
    a record that named README.md, carried the SHA-256 of the actual README,
    and stated "Format PNEZD, no header row" - a record of bytes that were never
    read, let alone converted (WP-R3 fix 2). The same shape existed on the
    ordinary path whenever the file was edited between the parse and the hash.

    ``None`` means the rows were handed to ``run`` already parsed, so no bytes
    passed through this program and there is nothing it can honestly certify.
    The job record says exactly that. It is never filled in with a guess.
    """

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
    """Hash a file on disk, in blocks.

    **Not what the job record uses.** The record's digest comes from the reader,
    which hashes the bytes it actually parsed (``pnezd.read``); a hash taken
    from a path afterwards describes whatever is at that path at that moment,
    which is a different thing and was WP-R3 fix 2. This remains for callers
    that genuinely want to hash a file - the GEOID18 tile check is one - and is
    kept here because that is where it has always lived.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(settings: JobSettings, source: pnezd.PnezdFile | None = None) -> JobResult:
    """Execute a job. Reads if no parsed file is supplied; never writes.

    When ``source`` is supplied the job converts those rows and nothing else, so
    the record's SHA-256 is that source's own digest - which is None unless the
    source came from ``pnezd.read``. It is never taken from
    ``settings.input_path``, because that path was not what was converted
    (WP-R3 fix 2).
    """
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

    if (
        settings.direction is not Direction.ZONE_TO_ZONE
        and settings.longitude_convention is None
    ):
        raise ValueError(
            "A conversion with geodetic coordinates on either end needs the "
            "longitude sign convention the file uses. It has no default: the "
            "manual writes Michigan's longitudes positive west and every GPS, "
            "GIS and NGS tool writes them negative west, the two are "
            "indistinguishable from the numbers alone, and choosing wrongly "
            "moves a Michigan point about 340 miles."
        )

    parsed = source or pnezd.read(settings.input_path)

    grid = geoid18.default_grid() if settings.apply_geoid else None

    points: list[ConvertedPoint] = []
    for row in parsed.rows:
        points.append(_convert_row(row, settings, grid))

    return JobResult(
        settings=settings,
        points=tuple(points),
        # The digest of the bytes the parser consumed, and nothing else. None
        # when the rows arrived already parsed - see JobResult.input_sha256.
        input_sha256=parsed.sha256,
        input_row_count=len(parsed.rows),
        skipped_blank_lines=parsed.skipped_blank_lines,
        geoid_model=geoid18.GEOID_MODEL_NAME if settings.apply_geoid else None,
    )


def _convert_row(
    row: pnezd.PnezdRow,
    settings: JobSettings,
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
            latitude,
            longitude,
            settings.geodetic_frame,
            settings.target_zone,
            context,
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
            )
            output_northing = settings.output_unit.from_meters(
                conversion.target_northing
            )
            output_easting = settings.output_unit.from_meters(conversion.target_easting)

    # Elevation is orthometric height: it does not change with the horizontal
    # zone. Only its unit changes - and it changes in EVERY direction,
    # including State Plane to geodetic.
    #
    # That last clause used to be an exception: the elevation was left in the
    # input unit when the horizontal columns became degrees, on the reasoning
    # that a geodetic export has no linear unit. It does: the Z column. Three
    # separate surfaces already said so - this class's own docstring, the audit
    # CSV's "in <in>, out <out>" label, and the job record's "Units out" line -
    # while the clean export wrote feet. A reader who re-imported the file as
    # the record instructs computed the elevation factor at 900 m instead of
    # 274.3 m, a 98 ppm error, and read a Z field 625.680 m from the truth.
    # The unit now follows the output unit end to end (WP-R2 fix A).
    elevation_m = (
        settings.input_unit.to_meters(row.elevation)
        if row.elevation is not None
        else None
    )
    output_elevation = (
        settings.output_unit.from_meters(elevation_m)
        if elevation_m is not None
        else None
    )

    geoid_height = None
    if grid is not None and elevation_m is not None:
        try:
            geoid_height = geoid18.geoid_height(
                conversion.latitude, conversion.longitude, grid
            )
        except geoid18.GeoidError as error:
            # Outside the shipped tile. The horizontal conversion is unaffected
            # and stands; only the elevation-dependent factors are unavailable,
            # and factors_at reports that as None rather than inventing one.
            #
            # It must also be SAID. Setting geoid_height to None on its own is
            # indistinguishable downstream from a point that carried no
            # elevation at all: the same two factor columns read N/A, and the
            # job record's ELEVATIONS section then listed this point under
            # "blank elevation field" - a falsehood about a point whose Z was
            # recorded. The warning carries the distinction to the audit CSV,
            # to the report's WARNINGS section, and to the screen (WP-R2 fix C).
            geoid_height = None
            warnings.append(
                ConversionWarning(
                    code=WarningCode.GEOID_UNAVAILABLE,
                    message=(
                        f"{context}: the elevation "
                        f"{row.elevation:,.3f} {settings.input_unit.code} was "
                        f"read from the file, but no {geoid18.GEOID_MODEL_NAME} "
                        f"geoid height is available at "
                        f"{conversion.latitude:.6f}, {conversion.longitude:.6f}, "
                        f"so the elevation factor and combined factor for this "
                        f"point are {formatting.NOT_AVAILABLE} rather than a "
                        f"number. The HORIZONTAL "
                        f"coordinate is unaffected and stands: it does not "
                        f"depend on elevation at all. Underlying reason: "
                        f"{error}"
                    ),
                )
            )

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
