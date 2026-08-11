"""Ellipsoid-height input through ``job.run`` (WP-E2).

The mode decides ONE thing and one thing only: what lands in the Z column.
Horizontal mode writes the height back exactly as supplied (the owner's
instruction, 2026-08-11); the two vertical modes write the orthometric height.
In BOTH the factors are computed from the orthometric height, because the
elevation factor is R / (R + H + N) and a height that already contains the
separation must not have it added a second time.

The anchors these pins sit on are in ``tests/test_ellipsoid_height.py`` and
``tests/fixtures/ellipsoid_height_anchors.py``. At the Houghton anchor NGS
prints N18 = -33.796 m, so a 200.000 m NAVD 88 point has an ellipsoid height
of 166.204 m, and converting that back must land on 200.000 m.
"""

from __future__ import annotations

import pytest

from michspc.fileio import formatting as fmt, geoid, pnezd
from michspc.job import (
    Direction,
    EllipsoidHeightReading,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc.convert import WarningCode
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.vertical import NAVD88, NGVD29, HeightKind
from michspc.spc.zones import MI_NORTH
from tests.fixtures.geoid_anchors import GEOID_ANCHORS

HOUGHTON_LATITUDE = 47.1211
HOUGHTON_LONGITUDE = -88.5694
N18_FIXTURE = next(
    a.geoid_height_m
    for a in GEOID_ANCHORS
    if a.latitude == HOUGHTON_LATITUDE and a.longitude == HOUGHTON_LONGITUDE
)

HOUGHTON_H_M = 200.000
HOUGHTON_ELLIPSOID_M = HOUGHTON_H_M + N18_FIXTURE  # 166.204

# The same derived bound the geoid-swap pins use: two NGS figures printed to
# 0.001 m plus the reader's measured sub-millimetre residual (DESIGN.md #37).
ANCHOR_TOLERANCE_M = 0.0015

# The mean earth radius the elevation factor divides by (spc/factors.py).
MEAN_EARTH_RADIUS_M = 6_372_000.0


def _vertical(**overrides) -> JobSettings:
    """Geodetic-input vertical-only, NAVD 88 identity, metres, GEOID18."""
    base = dict(
        input_path=None,
        output_directory=None,
        direction=Direction.VERTICAL_ONLY,
        source_zone=None,
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
        geoid_model=geoid.GEOID18_MODEL,
    )
    base.update(overrides)
    return JobSettings(**base)


def _horizontal(**overrides) -> JobSettings:
    """State Plane to geodetic: horizontal, no vertical question asked."""
    base = dict(
        input_path=None,
        output_directory=None,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_NORTH,
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geoid_model=geoid.GEOID18_MODEL,
    )
    base.update(overrides)
    return JobSettings(**base)


def _at_houghton(height: float, places: int = 3) -> pnezd.PnezdFile:
    return pnezd.parse_lines(
        [
            f"1,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},"
            f"{height:.{places}f},GNSS"
        ]
    )


# A State Plane point well inside MI North, carrying the same GNSS height.
_ZONE_ROW = [f"1,500000.0,8000000.0,{HOUGHTON_ELLIPSOID_M:.3f},GNSS"]


# ==========================================================================
# The vertical modes: the Z becomes the elevation.
# ==========================================================================


def test_a_vertical_job_converts_the_gnss_height_to_the_published_elevation():
    """The flagship. 166.204 m ellipsoid at Houghton becomes 200.000 m NAVD 88
    — DESIGN.md #50's own anchor, read the other way."""
    point = run(
        _vertical(input_height_kind=HeightKind.ELLIPSOID),
        source=_at_houghton(HOUGHTON_ELLIPSOID_M),
    ).points[0]

    assert point.output_elevation == pytest.approx(
        HOUGHTON_H_M, abs=ANCHOR_TOLERANCE_M
    )
    # It went UP by the separation. A sign error lands 68 m away.
    assert point.output_elevation > HOUGHTON_ELLIPSOID_M

    reading = point.ellipsoid_height
    assert reading is not None
    assert reading.geoid_model_name == "GEOID18"
    assert reading.vertical_datum_code == NAVD88.code
    assert reading.ellipsoid_height_m == pytest.approx(HOUGHTON_ELLIPSOID_M, abs=1e-9)
    # Exact against the shipped grid, not the fixture: the record must agree
    # with the grid it actually read.
    assert reading.geoid_height_m == geoid.geoid_height(
        HOUGHTON_LATITUDE,
        HOUGHTON_LONGITUDE,
        geoid.default_grid(geoid.GEOID18_MODEL),
    )
    assert reading.orthometric_height_m == pytest.approx(
        reading.ellipsoid_height_m - reading.geoid_height_m, abs=1e-12
    )


def test_the_identity_branch_cannot_overwrite_the_converted_height():
    """The design review's catch, pinned.

    The h -> H step rebinds ``elevation_m`` rather than assigning only
    ``height_m``, because the identity branch a few lines below re-reads
    ``elevation_m`` through ``apply_shift``. Assigning only ``height_m`` left
    the flagship same-datum job writing the raw ellipsoid height while
    reporting a conversion — the feature doing nothing at all, on the job it
    exists for. This asserts the Z actually MOVED, which is what that seeding
    fails.
    """
    point = run(
        _vertical(input_height_kind=HeightKind.ELLIPSOID),
        source=_at_houghton(HOUGHTON_ELLIPSOID_M),
    ).points[0]

    # The identity shift really did run, and really did shift by zero...
    assert point.vertical is not None
    assert point.vertical.shift_m == 0.0
    # ...and yet the Z is not the supplied height: h -> H ran before it.
    assert point.output_elevation - HOUGHTON_ELLIPSOID_M == pytest.approx(
        -N18_FIXTURE, abs=ANCHOR_TOLERANCE_M
    )


def test_a_modeled_shift_takes_the_derived_elevation_not_the_gnss_height():
    """NAVD 88 -> NGVD 29 from GNSS: h -> H first, VERTCON second.

    The order is the whole safety of it. VERTCON transforms an orthometric
    height; handing it an ellipsoid height would shift a number 34 m away from
    the one its grid was built for, and nothing downstream could notice.
    """
    point = run(
        _vertical(
            input_height_kind=HeightKind.ELLIPSOID, target_vertical_datum=NGVD29
        ),
        source=_at_houghton(HOUGHTON_ELLIPSOID_M),
    ).points[0]

    reading = point.ellipsoid_height
    assert reading is not None
    assert reading.orthometric_height_m == pytest.approx(
        HOUGHTON_H_M, abs=ANCHOR_TOLERANCE_M
    )
    # The Z is the derived elevation plus the modeled shift, not h plus it.
    assert point.output_elevation == pytest.approx(
        reading.orthometric_height_m + point.vertical.shift_m, abs=1e-9
    )
    # And #41's source-era factors used H, never h.
    assert point.factors.orthometric_height == pytest.approx(
        HOUGHTON_H_M, abs=ANCHOR_TOLERANCE_M
    )


@pytest.mark.parametrize("unit", [METERS, INTERNATIONAL_FEET])
def test_the_conversion_is_the_same_height_in_every_unit(unit):
    # Written to four decimals in the job's own unit, then compared against
    # THAT number rather than the unrounded one: in international feet the
    # fourth decimal is 30 micrometres, and comparing to the unrounded value
    # would be testing the test's formatting, not the program.
    written = f"{unit.from_meters(HOUGHTON_ELLIPSOID_M):.4f}"
    supplied = float(written)
    source = pnezd.parse_lines(
        [f"1,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},{written},GNSS"]
    )

    point = run(
        _vertical(
            input_height_kind=HeightKind.ELLIPSOID, input_unit=unit, output_unit=unit
        ),
        source=source,
    ).points[0]

    assert unit.to_meters(point.output_elevation) == pytest.approx(
        HOUGHTON_H_M, abs=ANCHOR_TOLERANCE_M
    )
    # The audit CSV's long-standing "Ellipsoid height (m)" cell reconstructs
    # the user's own number — the one cell that would expose a double-counted
    # separation immediately.
    assert point.factors.ellipsoid_height == pytest.approx(
        unit.to_meters(supplied), abs=1e-9
    )


# ==========================================================================
# Horizontal mode: the Z is untouched, the factors are corrected.
# ==========================================================================


def test_horizontal_mode_writes_the_supplied_height_back_unchanged():
    """The owner's instruction: horizontal mode never converts the Z.

    Compared as the WRITTEN STRING as well as the float, so this pins what a
    CAD import would actually receive.
    """
    source = pnezd.parse_lines(_ZONE_ROW)

    orthometric = run(_horizontal(), source=source).points[0]
    ellipsoid = run(
        _horizontal(input_height_kind=HeightKind.ELLIPSOID), source=source
    ).points[0]

    assert ellipsoid.output_elevation == orthometric.output_elevation
    assert fmt.coordinate(ellipsoid.output_elevation, METERS) == fmt.coordinate(
        orthometric.output_elevation, METERS
    )
    # Nothing was datum-tagged: horizontal mode asked no vertical question.
    assert ellipsoid.vertical is None
    # But the conversion DID happen, for the factors, and is on the record.
    assert ellipsoid.ellipsoid_height is not None


def test_horizontal_mode_stops_adding_the_separation_twice_to_the_factors():
    """The ~5 ppm the owner asked to have fixed, measured.

    The elevation factor is R / (R + H + N). Given an ellipsoid height h the
    correct denominator is R + h, because h IS H + N. Treating h as an
    orthometric height computes R / (R + h + N) instead — a denominator short
    by |N|, about 34 m in Michigan:

        delta = |N| / R ~ 34 / 6,372,000 ~ 5.3e-6

    The sign matters as much as the size: the wrong form makes the factor
    LARGER, so grid distances come out long, systematically, on every line.
    """
    source = pnezd.parse_lines(_ZONE_ROW)

    wrong = run(_horizontal(), source=source).points[0]
    right = run(
        _horizontal(input_height_kind=HeightKind.ELLIPSOID), source=source
    ).points[0]

    separation = right.factors.geoid_height
    assert separation is not None and separation < 0.0

    # The corrected factor is computed from h itself: H + N == h.
    assert right.factors.ellipsoid_height == pytest.approx(
        HOUGHTON_ELLIPSOID_M, abs=1e-9
    )
    assert right.factors.orthometric_height == pytest.approx(
        HOUGHTON_ELLIPSOID_M - separation, abs=1e-9
    )

    predicted = -separation / MEAN_EARTH_RADIUS_M
    measured = (
        wrong.factors.elevation_factor - right.factors.elevation_factor
    ) / right.factors.elevation_factor
    assert measured == pytest.approx(predicted, rel=1e-3)
    assert measured == pytest.approx(5.3e-6, abs=1.5e-6)
    # The uncorrected factor is the LARGER one — distances long, not short.
    assert wrong.factors.elevation_factor > right.factors.elevation_factor


def test_the_default_leaves_every_existing_job_alone():
    """ORTHOMETRIC is the default, and the default is the status quo.

    A job that never mentions the new setting must be identical to one that
    states ORTHOMETRIC explicitly — the regression floor for every job this
    program has ever run.
    """
    source = pnezd.parse_lines(_ZONE_ROW)

    silent = run(_horizontal(), source=source).points[0]
    explicit = run(
        _horizontal(input_height_kind=HeightKind.ORTHOMETRIC), source=source
    ).points[0]

    assert silent.output_elevation == explicit.output_elevation
    assert silent.factors == explicit.factors
    assert silent.ellipsoid_height is None and explicit.ellipsoid_height is None


# ==========================================================================
# The three refusals, all before any point converts.
# ==========================================================================


def test_ellipsoid_input_with_no_geoid_model_refuses():
    with pytest.raises(geoid.GeoidError) as caught:
        run(
            _vertical(input_height_kind=HeightKind.ELLIPSOID, geoid_model=None),
            source=_at_houghton(HOUGHTON_ELLIPSOID_M),
        )
    message = str(caught.value)
    assert "no geoid model" in message
    assert "orthometric heights" in message


def test_ellipsoid_input_across_a_geoid_change_refuses():
    """The owner's decision, 2026-08-11: the input model cancels out, so
    allowing it would state a conversion that changed no number."""
    with pytest.raises(geoid.GeoidError) as caught:
        run(
            _vertical(
                input_height_kind=HeightKind.ELLIPSOID,
                source_geoid_model=geoid.GEOID12B_MODEL,
                geoid_model=geoid.GEOID18_MODEL,
            ),
            source=_at_houghton(HOUGHTON_ELLIPSOID_M),
        )
    message = str(caught.value)
    assert "GEOID12B" in message and "GEOID18" in message
    assert "cancels out" in message
    assert "never on it" in message


def test_ellipsoid_input_whose_source_datum_is_not_the_models_refuses():
    """An ellipsoid height is in no vertical datum; the H derived from it is
    in the model's. Stating NGVD 29 as the INPUT datum would mislabel it
    before a single shift ran."""
    with pytest.raises(geoid.GeoidError) as caught:
        run(
            _vertical(
                input_height_kind=HeightKind.ELLIPSOID,
                source_vertical_datum=NGVD29,
                target_vertical_datum=NAVD88,
            ),
            source=_at_houghton(HOUGHTON_ELLIPSOID_M),
        )
    message = str(caught.value)
    assert "NGVD29" in message and "NAVD88" in message
    assert "no vertical datum at all" in message


def test_a_height_kind_impostor_refuses_by_type():
    """The #11-finding-1 class: True is not "the ellipsoid one"."""
    with pytest.raises(TypeError) as caught:
        run(
            _vertical(input_height_kind=True),
            source=_at_houghton(HOUGHTON_ELLIPSOID_M),
        )
    assert "HeightKind" in str(caught.value)


# ==========================================================================
# Coverage failure: the Z is refused in a vertical mode, written in horizontal.
# ==========================================================================


def test_a_point_off_the_geoid_tile_refuses_the_height_in_a_vertical_mode():
    """39.5 N is south of the tiles' 40.0 N edge. No N, so no H — and in a
    vertical mode that means no Z at all, rather than an unconverted ellipsoid
    height wearing a vertical datum label."""
    point = run(
        _vertical(input_height_kind=HeightKind.ELLIPSOID),
        source=pnezd.parse_lines(["1,39.5,-84.0,166.204,OFF"]),
    ).points[0]

    assert point.output_elevation is None
    assert point.ellipsoid_height is None
    raised = [
        w
        for w in point.warnings
        if w.code is WarningCode.ELLIPSOID_HEIGHT_UNCONVERTIBLE
    ]
    assert len(raised) == 1
    assert "ELLIPSOID height" in raised[0].message
    assert "No elevation is written" in raised[0].message


def test_the_same_failure_still_writes_the_z_in_horizontal_mode():
    """Horizontal mode passes the Z through even when the factors are lost —
    the owner's rule holds on the failure path too, and the warning says which
    of the two happened."""
    point = run(
        _horizontal(input_height_kind=HeightKind.ELLIPSOID),
        source=pnezd.parse_lines(["1,100000.0,10000000.0,166.204,OFF"]),
    ).points[0]

    assert point.output_elevation == pytest.approx(166.204, abs=1e-9)
    assert point.factors.combined_factor is None
    raised = [w for w in point.warnings if w.code is WarningCode.GEOID_UNAVAILABLE]
    assert len(raised) == 1
    assert "unconverted" in raised[0].message


# ==========================================================================
# The record's own arithmetic guard.
# ==========================================================================


def test_a_reading_whose_height_disagrees_with_its_ingredients_refuses():
    with pytest.raises(ValueError) as caught:
        EllipsoidHeightReading(
            geoid_model_name="GEOID18",
            vertical_datum_code="NAVD88",
            ellipsoid_height_m=166.204,
            geoid_height_m=-33.796,
            orthometric_height_m=132.408,  # h + N, the sign flip
        )
    assert "H = h - N" in str(caught.value)


def test_a_reading_naming_no_model_refuses():
    with pytest.raises(ValueError):
        EllipsoidHeightReading(
            geoid_model_name="   ",
            vertical_datum_code="NAVD88",
            ellipsoid_height_m=166.204,
            geoid_height_m=-33.796,
            orthometric_height_m=200.000,
        )
