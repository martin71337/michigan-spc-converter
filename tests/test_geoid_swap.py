"""The geoid-to-geoid conversion (the owner's per-side feature, 2026-08-09).

On a vertical job the input and output geoid models are chosen separately
(``JobSettings.source_geoid_model`` beside the existing ``geoid_model``), and
an IDENTITY job whose two sides state different models converts between them:
the ellipsoid height is held fixed and the orthometric height re-derived
under the output model, H_out = H_in + N_in - N_out.

The truth the pins sit on, hand-derived from BOTH committed fixture sets -
the same 20 NGS positions, printed by NGS to 0.001 m
(tests/fixtures/geoid_anchors.py and geoid12b_anchors.py). At the Houghton
anchor, 47.1211 N / -88.5694 W:

    N18  = -33.796 m   (NGS's printed GEOID18 figure)
    N12B = -33.828 m   (NGS's printed GEOID12B figure)

so a GEOID12B -> GEOID18 swap shifts a height by

    N_in - N_out = -33.828 - (-33.796) = -0.032 m

and 200.000 m becomes 199.968 m; the reverse swap lands at 200.032 m. The
shipped grids' own difference at that position is -0.032343 m - inside
0.0015 m of the fixture figure, the bound two 0.5 mm print quantizations
plus the reader's measured sub-millimetre residual allow - and the job's
swap shift is pinned EQUAL to that grid difference exactly, because the swap
reads the very grids ``geoid.default_grid`` serves.

The other half of the feature is what did NOT change: every pre-existing job
shape - horizontal, and every #41-era vertical shape - states
``source_geoid_model=None`` and keeps every byte of every surface, and the
#41 either-endpoint behaviour (NAVD88 -> NGVD29 with GEOID18 in
``geoid_model``) is reproduced exactly by the normalization that supersedes
it (``job.per_side_geoid_models``).

No Codex gate ran over this feature (the owner's instruction): these
hand-derived pins and the falsification table in the session record carry
the weight instead.
"""

from __future__ import annotations

import csv
import os

# MUST precede any Qt import: ``results_model`` imports PySide6 at module
# level, and the platform plugin is chosen at import time
# (docs/method/TOOLING.md).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402

from michspc.fileio import exports, formatting as fmt, geoid, pnezd  # noqa: E402
from michspc.fileio.report import build_report  # noqa: E402
from michspc.gui import results_model  # noqa: E402
from michspc.job import (
    Direction,
    GeoidSwapReading,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    factors_use_source_era,
    geoid_swap_models,
    per_side_geoid_models,
    run,
)
from michspc.spc.convert import WarningCode
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.vertical import NAVD88, NGVD29, require_vertical_pair
from tests.fixtures.geoid12b_anchors import GEOID12B_ANCHORS
from tests.fixtures.geoid_anchors import GEOID_ANCHORS

# The Houghton anchor position, present in BOTH fixture sets at the same
# coordinates - resolved from the fixtures rather than retyped, so this file
# cannot drift from the captured NGS truth.
HOUGHTON_LATITUDE = 47.1211
HOUGHTON_LONGITUDE = -88.5694
N18_FIXTURE = next(
    a.geoid_height_m
    for a in GEOID_ANCHORS
    if a.latitude == HOUGHTON_LATITUDE and a.longitude == HOUGHTON_LONGITUDE
)
N12B_FIXTURE = next(
    a.geoid_height_m
    for a in GEOID12B_ANCHORS
    if a.latitude == HOUGHTON_LATITUDE and a.longitude == HOUGHTON_LONGITUDE
)

# -0.032 m: the 12B -> 18 swap shift as NGS's printed figures give it.
FIXTURE_SWAP_SHIFT_M = N12B_FIXTURE - N18_FIXTURE

# Two NGS figures each printed to 0.001 m carry +/-0.0005 m of quantization
# apiece, and the reader's worst measured residual against NGS's service is
# sub-millimetre (DESIGN.md #37), so 0.0015 m is the derived bound - not a
# chosen one.
SWAP_TOLERANCE_M = 0.0015


def _swap_source(
    elevation: str = "200.000", point_id: str = "101"
) -> pnezd.PnezdFile:
    return pnezd.parse_lines(
        [
            f"{point_id},{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},"
            f"{elevation},SWAP"
        ]
    )


def _swap_settings(**overrides) -> JobSettings:
    """A geodetic-input vertical-only GEOID12B -> GEOID18 swap, metres:
    identity datum pair NAVD 88 -> NAVD 88, input model GEOID12B, output
    model GEOID18."""
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
        source_geoid_model=geoid.GEOID12B_MODEL,
    )
    base.update(overrides)
    return JobSettings(**base)


def _grid_difference_m(source_model, target_model) -> float:
    """N_in - N_out at Houghton from the shipped grids themselves - the very
    lookups the job performs, so the pin below is exact, not approximate."""
    n_in = geoid.geoid_height(
        HOUGHTON_LATITUDE, HOUGHTON_LONGITUDE, geoid.default_grid(source_model)
    )
    n_out = geoid.geoid_height(
        HOUGHTON_LATITUDE, HOUGHTON_LONGITUDE, geoid.default_grid(target_model)
    )
    return n_in - n_out


# ==========================================================================
# The Houghton pins: both directions, exact against our grids AND within the
# fixture-derived bound of NGS's printed figures.
# ==========================================================================


def test_the_12b_to_18_swap_moves_200_to_199_968_at_houghton():
    """The forward pin. 200.000 m stated against GEOID12B becomes 199.968 m
    stated against GEOID18 (fixture arithmetic: -33.828 - (-33.796) =
    -0.032), and the job's swap shift EQUALS the shipped grids' own
    difference at the point - a swap that read the same grid twice, or
    flipped the subtraction, cannot satisfy both."""
    result = run(_swap_settings(), source=_swap_source())
    point = result.points[0]
    swap = point.geoid_swap

    assert swap is not None
    assert swap.source_model_name == "GEOID12B"
    assert swap.target_model_name == "GEOID18"

    # Exact against the grids the job read.
    expected_shift = _grid_difference_m(
        geoid.GEOID12B_MODEL, geoid.GEOID18_MODEL
    )
    assert swap.shift_m == expected_shift
    assert point.output_elevation == 200.0 + expected_shift

    # And within the derived bound of the fixture-quantized -0.032.
    assert swap.shift_m == pytest.approx(
        FIXTURE_SWAP_SHIFT_M, abs=SWAP_TOLERANCE_M
    )
    assert point.output_elevation == pytest.approx(
        200.0 + FIXTURE_SWAP_SHIFT_M, abs=SWAP_TOLERANCE_M
    )
    # 199.968, to the written precision.
    assert fmt.coordinate(point.output_elevation, METERS) == "199.9677"

    # The two separations on the reading are the grids' own values, and the
    # record's arithmetic holds by construction.
    assert swap.n_source_m == geoid.geoid_height(
        HOUGHTON_LATITUDE,
        HOUGHTON_LONGITUDE,
        geoid.default_grid(geoid.GEOID12B_MODEL),
    )
    assert swap.n_target_m == geoid.geoid_height(
        HOUGHTON_LATITUDE,
        HOUGHTON_LONGITUDE,
        geoid.default_grid(geoid.GEOID18_MODEL),
    )

    # The datum reading stays the identity record - both statements are
    # true: the datum did not change, the geoid did.
    assert point.vertical is not None
    assert point.vertical.transformation.is_identity
    assert point.vertical.shift_m == 0.0
    assert point.vertical.sigma_m is None


def test_the_reverse_swap_moves_200_to_200_032_at_houghton():
    """The 18 -> 12B direction: the same two grids, the subtraction the
    other way round, landing at 200.032. A sign convention error passes one
    direction and fails the other, which is what this pair of tests buys."""
    result = run(
        _swap_settings(
            geoid_model=geoid.GEOID12B_MODEL,
            source_geoid_model=geoid.GEOID18_MODEL,
        ),
        source=_swap_source(),
    )
    point = result.points[0]
    swap = point.geoid_swap

    assert swap is not None
    assert swap.source_model_name == "GEOID18"
    assert swap.target_model_name == "GEOID12B"
    expected_shift = _grid_difference_m(
        geoid.GEOID18_MODEL, geoid.GEOID12B_MODEL
    )
    assert swap.shift_m == expected_shift
    assert point.output_elevation == 200.0 + expected_shift
    assert point.output_elevation == pytest.approx(
        200.0 - FIXTURE_SWAP_SHIFT_M, abs=SWAP_TOLERANCE_M
    )
    assert fmt.coordinate(point.output_elevation, METERS) == "200.0323"


def test_the_two_directions_round_trip_exactly():
    """One pair of grids, one subtraction, two directions: the forward and
    reverse swap shifts are exact negations, so a height swapped there and
    back reproduces bit-for-bit (the sums are the same two floats)."""
    forward = run(_swap_settings(), source=_swap_source()).points[0]
    reverse = run(
        _swap_settings(
            geoid_model=geoid.GEOID12B_MODEL,
            source_geoid_model=geoid.GEOID18_MODEL,
        ),
        source=_swap_source(),
    ).points[0]
    assert forward.geoid_swap.shift_m == -reverse.geoid_swap.shift_m


def test_the_swap_runs_in_horizontal_and_vertical_mode_too():
    """The swap is a property of the identity pair with two models, not of
    the vertical-only direction: a GEODETIC_TO_ZONE job in
    HORIZONTAL_AND_VERTICAL mode swaps identically - the same pivot, the
    same grids, the same shift bitwise."""
    from michspc.spc.zones import MI_NORTH

    vertical_only = run(_swap_settings(), source=_swap_source()).points[0]
    with_zone = run(
        _swap_settings(
            direction=Direction.GEODETIC_TO_ZONE,
            target_zone=MI_NORTH,
            vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        ),
        source=_swap_source(),
    ).points[0]

    assert with_zone.geoid_swap is not None
    assert with_zone.geoid_swap.shift_m == vertical_only.geoid_swap.shift_m
    assert with_zone.output_elevation == vertical_only.output_elevation
    # And this direction has a zone, so the factors exist - computed from
    # the OUTPUT side: the post-swap height with the output model's grid.
    assert with_zone.factors.elevation_factor is not None


def test_the_factors_come_from_the_output_side_of_a_swap():
    """Output side preferred: the factors' geoid height is the OUTPUT
    model's separation, and the ellipsoid height they use equals
    H_in + N_in - the held-fixed quantity - because
    (H_in + N_in - N_out) + N_out = H_in + N_in."""
    from michspc.spc.zones import MI_NORTH

    point = run(
        _swap_settings(
            direction=Direction.GEODETIC_TO_ZONE,
            target_zone=MI_NORTH,
            vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        ),
        source=_swap_source(),
    ).points[0]
    swap = point.geoid_swap

    assert point.factors.geoid_height == swap.n_target_m
    assert point.factors.ellipsoid_height == pytest.approx(
        200.0 + swap.n_source_m, abs=1e-9
    )
    # result.geoid_model names the factors' model: the output side.
    assert point.factors.geoid_height == geoid.geoid_height(
        HOUGHTON_LATITUDE,
        HOUGHTON_LONGITUDE,
        geoid.default_grid(geoid.GEOID18_MODEL),
    )


# ==========================================================================
# The #47 rule: the shift displays in the job's INPUT unit.
# ==========================================================================


def test_the_swap_shift_displays_in_international_feet():
    """An ift job's swap shift renders in ift at the unit's own 3 places.

    Hand-derivation: the grids' difference at Houghton is -0.032343 m
    (pinned exact above), and -0.032343 / 0.3048 = -0.106112 -> "-0.106".
    (The fixture-quantized -0.032 alone would give 0.032/0.3048 = 0.10499
    -> "-0.105"; the shipped grids' extra 0.3 mm - inside the fixtures'
    0.5 mm print quantization - carries the third decimal to -0.106, which
    is why the pin is stated against the reader's own exact value and the
    literal is derived from IT.)"""
    result = run(
        _swap_settings(
            input_unit=INTERNATIONAL_FEET, output_unit=INTERNATIONAL_FEET
        ),
        source=_swap_source(elevation="656.168"),
    )
    point = result.points[0]
    swap = point.geoid_swap

    rendered = fmt.vertical_quantity(swap.shift_m, INTERNATIONAL_FEET)
    assert rendered == "-0.106"
    # And the metre value underneath is still the grids' own difference -
    # the internals stay metres, only the presentation converts (#47).
    assert swap.shift_m == _grid_difference_m(
        geoid.GEOID12B_MODEL, geoid.GEOID18_MODEL
    )


# ==========================================================================
# Same model on both sides: exactly the pre-feature identity job.
# ==========================================================================


def test_same_model_both_sides_is_bitwise_the_prefeature_identity_job():
    """GEOID18 stated on both sides (what the GUI emits when nothing is
    changed) is NO swap: no step runs, no record exists, and every output
    is bit-identical to the pre-feature shape that stated no input side at
    all."""
    prefeature = run(
        _swap_settings(source_geoid_model=None), source=_swap_source()
    ).points[0]
    both_sides = run(
        _swap_settings(source_geoid_model=geoid.GEOID18_MODEL),
        source=_swap_source(),
    ).points[0]

    assert both_sides.geoid_swap is None
    assert prefeature.geoid_swap is None
    assert both_sides.output_elevation == prefeature.output_elevation
    assert both_sides.output_elevation == 200.0
    assert both_sides.factors == prefeature.factors
    assert both_sides.vertical == prefeature.vertical


# ==========================================================================
# The refusal matrix additions - every one named, every one teaching.
# ==========================================================================


def test_a_horizontal_job_refuses_an_input_side_geoid_model():
    from michspc.spc.zones import MI_SOUTH

    settings = _swap_settings(
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        vertical_mode=VerticalMode.HORIZONTAL,
        source_vertical_datum=None,
        target_vertical_datum=None,
        geoid_model=geoid.GEOID18_MODEL,
        source_geoid_model=geoid.GEOID12B_MODEL,
    )
    with pytest.raises(ValueError) as caught:
        run(settings, source=pnezd.parse_lines(["101,166625.0,3989128.0,200.0,H"]))
    message = str(caught.value)
    assert "horizontal-only" in message
    assert "source_geoid_model" in message
    assert "GEOID12B" in message


def test_both_sides_on_a_modeled_transformation_refuse_teaching_two_jobs():
    """The compound-job refusal: a modeled datum shift AND a geoid change
    inside one Z column is two modeled corrections no surface could state
    alone. Reachable today with GEOID18 on both sides of NAVD88 -> NGVD29;
    guarded now so NAPGD2022's models arrive behind it, not ahead of it."""
    settings = _swap_settings(
        source_vertical_datum=NAVD88,
        target_vertical_datum=NGVD29,
        geoid_model=geoid.GEOID18_MODEL,
        source_geoid_model=geoid.GEOID18_MODEL,
    )
    with pytest.raises(ValueError) as caught:
        run(settings, source=_swap_source())
    message = str(caught.value)
    assert "BOTH sides" in message
    assert "two jobs" in message
    assert "NAVD88 -> NGVD29" in message


def test_an_input_model_from_another_era_refuses_naming_the_side():
    """The per-side form of #32: GEOID12B publishes NAVD 88 separations, so
    it cannot be the input side of a job whose input elevations are
    NGVD 29."""
    settings = _swap_settings(
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
        geoid_model=None,
        source_geoid_model=geoid.GEOID12B_MODEL,
    )
    with pytest.raises(geoid.GeoidError) as caught:
        run(settings, source=_swap_source())
    message = str(caught.value)
    assert "INPUT elevations" in message
    assert "NGVD29" in message
    assert "GEOID12B" in message


def test_an_impostor_input_model_is_refused_by_name():
    """The #11-finding-1 guard at the new field: True is the habit a boolean
    toggle teaches, and NAVD88 is the likeliest record impostor."""
    for impostor in (True, NAVD88):
        settings = _swap_settings(source_geoid_model=impostor)
        with pytest.raises(TypeError) as caught:
            run(settings, source=_swap_source())
        assert "source_geoid_model" in str(caught.value)


def test_a_non_registry_input_model_is_refused_before_converting():
    counterfeit = geoid.GeoidModel(
        name="GEOID99",
        tile_filename="g1999u3.bin",
        sha256="0" * 64,
        geometry=geoid.GEOID18_MODEL.geometry,
        vertical_datum=NAVD88,
        citation="a record the registry does not hold",
    )
    settings = _swap_settings(source_geoid_model=counterfeit)
    with pytest.raises(ValueError) as caught:
        run(settings, source=_swap_source())
    message = str(caught.value)
    assert "GEOID99" in message
    assert "not a registered geoid model" in message


# ==========================================================================
# The normalization: the #41 either-endpoint behaviour, reproduced exactly.
# ==========================================================================


def _navd88_to_ngvd29_settings(**overrides) -> JobSettings:
    base = dict(
        source_vertical_datum=NAVD88,
        target_vertical_datum=NGVD29,
    )
    base.update(overrides)
    return _swap_settings(**base)


def test_the_old_and_new_navd88_to_ngvd29_shapes_are_bitwise_identical():
    """The normalization equivalence pin: the #41-era shape (GEOID18 in
    geoid_model, no input side stated) and the per-side shape (GEOID18 as
    source_geoid_model, geoid_model None - what the GUI now emits for an
    NGVD 29 target) produce identical factors and outputs bitwise, and both
    name GEOID18 as the factors' model."""
    old_shape = run(
        _navd88_to_ngvd29_settings(
            geoid_model=geoid.GEOID18_MODEL, source_geoid_model=None
        ),
        source=_swap_source(),
    )
    new_shape = run(
        _navd88_to_ngvd29_settings(
            geoid_model=None, source_geoid_model=geoid.GEOID18_MODEL
        ),
        source=_swap_source(),
    )

    old_point, new_point = old_shape.points[0], new_shape.points[0]
    assert new_point.output_elevation == old_point.output_elevation
    assert new_point.factors == old_point.factors
    assert new_point.vertical.shift_m == old_point.vertical.shift_m
    assert new_point.vertical.sigma_m == old_point.vertical.sigma_m
    assert new_point.geoid_swap is None and old_point.geoid_swap is None
    assert old_shape.geoid_model == "GEOID18"
    assert new_shape.geoid_model == "GEOID18"


def test_the_normalization_makes_factors_use_source_era_a_consequence():
    """per_side_geoid_models treats the #41 shape's model as input-side, and
    factors_use_source_era reads the pairing: True for both NAVD88 -> NGVD29
    shapes, False for the forward direction and for every identity."""
    modeled = require_vertical_pair(NAVD88, NGVD29)
    identity = require_vertical_pair(NAVD88, NAVD88)

    old_shape = _navd88_to_ngvd29_settings(
        geoid_model=geoid.GEOID18_MODEL, source_geoid_model=None
    )
    assert per_side_geoid_models(old_shape, modeled) == (
        geoid.GEOID18_MODEL,
        None,
    )
    assert factors_use_source_era(old_shape, modeled) is True

    new_shape = _navd88_to_ngvd29_settings(
        geoid_model=None, source_geoid_model=geoid.GEOID18_MODEL
    )
    assert factors_use_source_era(new_shape, modeled) is True

    forward = _swap_settings(
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
        geoid_model=geoid.GEOID18_MODEL,
        source_geoid_model=None,
    )
    assert factors_use_source_era(
        forward, require_vertical_pair(NGVD29, NAVD88)
    ) is False
    assert factors_use_source_era(_swap_settings(), identity) is False

    # And a swap is detected exactly when both sides differ on an identity.
    assert geoid_swap_models(_swap_settings(), identity) == (
        geoid.GEOID12B_MODEL,
        geoid.GEOID18_MODEL,
    )
    assert geoid_swap_models(old_shape, modeled) is None
    assert (
        geoid_swap_models(
            _swap_settings(source_geoid_model=geoid.GEOID18_MODEL), identity
        )
        is None
    )


def test_the_new_shape_writes_the_record_the_old_shape_wrote(tmp_path):
    """The #41 Factor height paragraph survives the shape change: a job
    whose ONLY model is input-side still names GEOID18 as the factors'
    model rather than crashing on geoid_model=None or claiming no geoid
    was applied (the #42-finding-3 class this pin exists to hold shut)."""
    input_path = tmp_path / "job.csv"
    input_path.write_text(
        f"101,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},200.000,ERA\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = run(
        _navd88_to_ngvd29_settings(
            geoid_model=None,
            source_geoid_model=geoid.GEOID18_MODEL,
            input_path=input_path,
            output_directory=out_dir,
        )
    )
    text = build_report(result)
    assert "Factor height" in text
    assert "The GEOID18 separations are defined" in text
    assert "Geoid model        GEOID18" in text
    assert "not applied" not in text


# ==========================================================================
# Coverage: outside the geoid tiles, the elevation refuses and stands aside.
# ==========================================================================


def test_a_point_outside_the_geoid_tiles_refuses_the_swap_and_stands():
    """39.5 N is south of the shipped tiles' 40.0 N edge. The elevation is
    refused - never written under the output model's name unswapped - the
    readings are withdrawn, the coordinates stand, and the warning teaches."""
    source = pnezd.parse_lines(["901,39.5,-84.5,200.000,OUTSIDE"])
    result = run(_swap_settings(), source=source)
    point = result.points[0]

    assert point.output_elevation is None
    assert point.geoid_swap is None
    assert point.vertical is None
    assert point.output_northing == source.rows[0].northing
    assert point.output_easting == source.rows[0].easting

    raised = [
        w
        for w in point.warnings
        if w.code is WarningCode.GEOID_SWAP_UNAVAILABLE
    ]
    assert len(raised) == 1
    message = raised[0].message
    assert "GEOID12B" in message and "GEOID18" in message
    assert "NOT converted" in message
    assert "unaffected and stand" in message


def test_the_record_names_the_geoid_tiles_not_vertcon_for_a_swap_refusal(
    tmp_path,
):
    """A swap job consults no VERTCON grid, so its coverage refusal must not
    claim one - the WP-R2 fix C class, held shut at the new door."""
    input_path = tmp_path / "job.csv"
    input_path.write_text(
        "901,39.5,-84.5,200.000,OUTSIDE\n", encoding="utf-8"
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = run(
        _swap_settings(input_path=input_path, output_directory=out_dir)
    )
    text = build_report(result)

    assert "not convertible between geoid models" in text
    assert "outside the geoid tiles" in text
    assert "VERTCON grids" not in text


# ==========================================================================
# Disclosure: the written archive, end to end through files.
# ==========================================================================


def _written_swap_job(tmp_path, line: str, **overrides):
    input_path = tmp_path / "swapjob.csv"
    input_path.write_text(line + "\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    settings = _swap_settings(
        input_path=input_path, output_directory=out_dir, **overrides
    )
    result = run(settings)
    written = exports.write_all(result)
    return result, written["archive"]


def _audit(archive):
    from tests.conftest import member_text

    text = member_text(archive, "_full.csv")
    rows = list(csv.reader(text.splitlines()))
    return rows[0], rows[1:]


def test_the_audit_csv_discloses_both_models_and_the_swap_shift(tmp_path):
    result, archive = _written_swap_job(
        tmp_path, f"101,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},200.000,SWAP"
    )
    header, rows = _audit(archive)
    audit = dict(zip(header, rows[0]))
    point = result.points[0]

    # The new column sits beside the existing one: source first, then the
    # factors/output side, then the geoid height they govern.
    at = header.index("Source geoid model")
    assert header[at + 1] == "Geoid model"
    assert header[at + 2] == "Geoid height (m)"
    assert audit["Source geoid model"] == "GEOID12B"
    assert audit["Geoid model"] == "GEOID18"

    # The shift column carries the SWAP shift - the value that moved the
    # height - and the sigma is N/A: NGS publishes no error model for the
    # difference between two of its geoid models.
    assert audit["Vertical shift (m)"] == fmt.vertical_quantity(
        point.geoid_swap.shift_m, METERS
    )
    assert audit["Vertical shift (m)"] == "-0.0323"
    assert audit["Shift sigma (m)"] == fmt.NOT_AVAILABLE
    # Both datum columns state the identity pair.
    assert audit["Source vertical datum"] == "NAVD88"
    assert audit["Target vertical datum"] == "NAVD88"
    # And the Z column is the swapped height.
    assert audit["Elevation"] == "199.9677"
    assert audit[f"Source elevation (m)"] == "200.0000"


def test_the_record_carries_the_geoid_change_block_facts_only(tmp_path):
    """The GEOID CHANGE block: both models with their tile filenames and
    digests from the registry, and the arithmetic sentence. FACTS ONLY -
    the owner's instruction (2026-08-09, the #33/#34/#45 ruling extended to
    the written record): no leveled-vs-GNSS caveat, no uncertainty lecture.
    The absence is pinned by vocabulary below."""
    result, archive = _written_swap_job(
        tmp_path, f"101,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},200.000,SWAP"
    )
    text = build_report(result)

    assert "GEOID CHANGE" in text
    assert (
        "Input geoid        GEOID12B, NGS grid tile g2012bu3.bin" in text
    )
    assert f"SHA-256 {geoid.GEOID12B_MODEL.sha256}" in text
    assert (
        "Output geoid       GEOID18, NGS grid tile g2018u3.bin" in text
    )
    assert f"SHA-256 {geoid.GEOID18_MODEL.sha256}" in text
    # Compared with the record's own hand-wrapping collapsed, so the pin is
    # about the sentence, not about where the 78-column wrapper broke it.
    flattened = " ".join(text.split())
    assert "H_out = H_in + N_in - N_out" in flattened
    assert "ellipsoid height is held fixed" in flattened

    # The ELEVATIONS summary: swapped count, min/max/mean of the swap shift
    # in the input unit (#47), and the sigma line as the bare N/A of the
    # summary shape.
    assert "1 of 1 points had their elevation re-derived from the GEOID12B" in text
    assert "Geoid change (m)" in text
    assert "minimum  -0.0323" in text
    assert "maximum  -0.0323" in text
    assert "mean     -0.0323" in text
    assert "Shift one-sigma uncertainty (m)" in text


def test_the_swap_record_carries_no_disclaimer_vocabulary(tmp_path):
    """The ABSENCE pin (the owner's mid-feature instruction, 2026-08-09):
    no disclaimers on any user-facing surface, the written record included.
    The caveat vocabulary the dropped paragraph would carry must not appear
    anywhere in a swap job's record. Falsified by seeding the paragraph
    back into the GEOID CHANGE block: this test alone fails."""
    result, _archive = _written_swap_job(
        tmp_path, f"101,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},200.000,SWAP"
    )
    text = build_report(result)

    for banned in ("GNSS", "leveled", "benchmark", "disagreement", "cannot know"):
        assert banned not in text, (
            f"a swap job's record must not carry disclaimer prose; found "
            f"{banned!r}"
        )


def test_every_existing_job_shape_gains_no_column_and_no_block(tmp_path):
    """The regression pin: a horizontal job and a #41-era vertical job -
    both stating source_geoid_model=None - carry no Source geoid model
    column and no GEOID CHANGE block. Their surfaces are the pre-feature
    ones; the whole existing suite passing unchanged is the byte-level
    floor under this, and this pin names the two facts that would break
    first."""
    from michspc.spc.zones import MI_CENTRAL, MI_SOUTH

    # Horizontal.
    input_path = tmp_path / "hz.csv"
    input_path.write_text("101,176200.000,19685000.000,812.40,PIPE\n", encoding="utf-8")
    out_dir = tmp_path / "hzout"
    out_dir.mkdir()
    hz = run(
        JobSettings(
            input_path=input_path,
            output_directory=out_dir,
            direction=Direction.ZONE_TO_ZONE,
            source_zone=MI_CENTRAL,
            target_zone=MI_SOUTH,
            input_unit=INTERNATIONAL_FEET,
            output_unit=INTERNATIONAL_FEET,
            longitude_convention=None,
        )
    )
    written = exports.write_all(hz)
    header, _rows = _audit(written["archive"])
    assert "Source geoid model" not in header
    assert "GEOID CHANGE" not in build_report(hz)

    # #41-era vertical: NAVD88 -> NGVD29 with GEOID18 in geoid_model.
    v_input = tmp_path / "v41.csv"
    v_input.write_text(
        f"101,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},200.000,ERA\n",
        encoding="utf-8",
    )
    v_out = tmp_path / "v41out"
    v_out.mkdir()
    v41 = run(
        _navd88_to_ngvd29_settings(
            geoid_model=geoid.GEOID18_MODEL,
            source_geoid_model=None,
            input_path=v_input,
            output_directory=v_out,
        )
    )
    v_written = exports.write_all(v41)
    v_header, _v_rows = _audit(v_written["archive"])
    assert "Source geoid model" not in v_header
    assert "Geoid model" in v_header
    assert "GEOID CHANGE" not in build_report(v41)


# ==========================================================================
# The panel: the shift row names the MODELS on a swap job.
# ==========================================================================


def test_the_panel_names_the_models_and_reads_na_for_sigma():
    result = run(_swap_settings(), source=_swap_source())
    sections = results_model.single_point_sections(result)
    point = result.points[0]

    output = next(s for s in sections if s.title == results_model.OUTPUT_TITLE)
    labels = [v.label for v in output.values]
    assert "Geoid change GEOID12B -> GEOID18 (m)" in labels

    by_label = {v.label: v.text for v in output.values}
    assert by_label["Geoid change GEOID12B -> GEOID18 (m)"] == (
        fmt.vertical_quantity(point.geoid_swap.shift_m, METERS)
    )
    assert by_label["Geoid change GEOID12B -> GEOID18 (m)"] == "-0.0323"
    assert by_label[exports.vertical_sigma_heading(METERS)] == fmt.NOT_AVAILABLE
    # The datum-labelled shift row is REPLACED, not doubled: the datum did
    # not move, so no "Vertical shift NAVD88 -> NAVD88" row appears.
    assert not any(label.startswith("Vertical shift") for label in labels)
    # The elevation rows carry the (identity) datum tag AND the geoid the
    # height is on, in a parenthesis of its own after the unit one - the
    # owner's instruction of 2026-08-10 (docs/DESIGN.md #52). Each side names
    # ITS OWN model, so the two rows are told apart by the one thing that
    # differs between them; untagged they were the same string over two
    # different heights.
    assert "Elevation (NAVD88, m) (GEOID18)" in by_label
    assert "Elevation (NAVD88, m)" not in by_label

    source = next(s for s in sections if s.title == results_model.INPUT_TITLE)
    input_labels = {v.label for v in source.values}
    assert "Elevation (NAVD88, m) (GEOID12B)" in input_labels
    assert "Elevation (NAVD88, m)" not in input_labels


def test_the_multi_table_cells_mirror_the_audit_csv_for_a_swap(tmp_path):
    """The two surfaces share exports.vertical_shift_and_sigma_m, and this
    holds them together through real strings: the on-screen table's shift
    and sigma cells equal the audit CSV's for a swap job."""
    result, archive = _written_swap_job(
        tmp_path,
        f"101,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},200.000,SWAP",
    )
    header, rows = _audit(archive)
    audit = dict(zip(header, rows[0]))

    table_rows = results_model.row_strings(result)
    columns = results_model.columns_for(result)
    shift_at = columns.index(exports.vertical_shift_heading(METERS))
    sigma_at = columns.index(exports.vertical_sigma_heading(METERS))

    assert table_rows[0][shift_at] == audit["Vertical shift (m)"]
    assert table_rows[0][sigma_at] == audit["Shift sigma (m)"]
    assert table_rows[0][shift_at] == "-0.0323"
    assert table_rows[0][sigma_at] == fmt.NOT_AVAILABLE


def test_the_table_heading_names_the_output_geoid_on_a_swap_job():
    """The owner's instruction, 2026-08-10 (docs/DESIGN.md #52).

    The table has ONE elevation column and it holds the converted height, so
    the heading names the OUTPUT model - the model those cells are on. The
    geoid sits in its own parenthesis after the unit one, his words.
    """
    result = run(_swap_settings(), source=_swap_source())

    columns = results_model.columns_for(result)
    assert "Elevation (NAVD88, m) (GEOID18)" in columns
    assert "Elevation (NAVD88, m)" not in columns

    # The heading a cell is under and the panel label for the same value are
    # ONE template (`_datum_elevation_label`), so the two surfaces cannot word
    # this differently - the property #26 established for these two tabs.
    sections = results_model.single_point_sections(result)
    output = next(s for s in sections if s.title == results_model.OUTPUT_TITLE)
    panel = {v.label for v in output.values}
    at = columns.index("Elevation (NAVD88, m) (GEOID18)")
    assert columns[at] in panel


def test_the_same_model_on_both_sides_names_no_geoid_anywhere():
    """No swap, no tag. Identity datums with ONE model is the ordinary job
    ``geoid_swap_models`` returns None for; a tag there would name a model
    that changed nothing, and would appear on jobs that ran before the
    feature existed.
    """
    result = run(
        _swap_settings(source_geoid_model=geoid.GEOID18_MODEL),
        source=_swap_source(),
    )

    assert "Elevation (NAVD88, m)" in results_model.columns_for(result)
    assert results_model.table_geoid_model_name(result) is None

    labels = {
        value.label
        for section in results_model.single_point_sections(result)
        for value in section.values
    }
    assert "Elevation (NAVD88, m)" in labels
    assert not any("GEOID18" in label for label in labels)


def test_a_modeled_datum_shift_names_no_geoid_on_its_elevation_rows():
    """NGVD 29 -> NAVD 88 is not a geoid conversion and must not read as one.

    The leveled height it produces does not depend on the hybrid model
    (DESIGN.md #50's recorded geodetic fact), and the two rows are already
    told apart by their datum codes. This is the pin that keeps the tag from
    spreading to every vertical job.
    """
    result = run(
        _swap_settings(
            source_vertical_datum=NGVD29,
            target_vertical_datum=NAVD88,
            source_geoid_model=None,
            geoid_model=geoid.GEOID18_MODEL,
        ),
        source=_swap_source(),
    )

    columns = results_model.columns_for(result)
    assert "Elevation (NAVD88, m)" in columns
    assert results_model.table_geoid_model_name(result) is None

    labels = {
        value.label
        for section in results_model.single_point_sections(result)
        for value in section.values
    }
    assert {"Elevation (NGVD29, m)", "Elevation (NAVD88, m)"} <= labels
    assert not any("GEOID" in label for label in labels)


def test_a_geoid_refusal_names_the_side_the_grid_was_read_from():
    """The GEOID_UNAVAILABLE warning must name the model actually consulted.

    Per-side selection (#50) split one question into two, and this warning
    kept naming ``settings.geoid_model`` - the OUTPUT side. On a
    NAVD 88 -> NGVD 29 job the output side has no model at all (NGVD 29 has
    none), so the factors run off the INPUT side and ``settings.geoid_model``
    is None: naming it raised ``AttributeError: 'NoneType' object has no
    attribute 'name'`` and took the whole job down instead of warning about
    one point. This is the GUI's DEFAULT state for that datum pair - the
    output selector grays itself and emits None - so it needed only a point
    off the tile to reach.

    The point: 39.5 N is BELOW the GEOID18 CONUS grid #3's south edge of
    40.0 N (``geoid.GEOID18_U3_GEOMETRY``), and VERTCON 3.0's CONUS grid
    covers it, so the vertical shift succeeds and the geoid lookup is the
    only thing that refuses - which is the order that reaches this branch.
    """
    settings = _swap_settings(
        source_vertical_datum=NAVD88,
        target_vertical_datum=NGVD29,
        source_geoid_model=geoid.GEOID18_MODEL,
        geoid_model=None,
    )
    assert geoid.GEOID18_U3_GEOMETRY.south_latitude == 40.0
    assert settings.geoid_model is None

    result = run(settings, source=pnezd.parse_lines(["1,39.5,-84.0,200.000,OFF"]))

    messages = [
        warning.message
        for _row, warning in result.warnings
        if warning.code is WarningCode.GEOID_UNAVAILABLE
    ]
    assert len(messages) == 1
    # The INPUT side's model - the one `grid` was loaded from.
    assert "no GEOID18 geoid height is available" in messages[0]
    # And the point still converted: only the factors are unavailable. The
    # elevation is the closing gate's own stated expected result for this
    # input (Codex, 2026-08-11, the single MEDIUM of the 0.5.0 gate). It is
    # this program's VERTCON reading at the point, so it pins the value
    # against regression - it is not an independent check OF the value, which
    # the frozen NCAT anchors elsewhere in the suite are.
    point = result.points[0]
    assert point.factors.combined_factor is None
    assert point.output_elevation == pytest.approx(200.20998242497444, abs=1e-9)


# ==========================================================================
# GeoidSwapReading's own contract.
# ==========================================================================


def test_a_swap_reading_whose_shift_disagrees_with_its_ingredients_refuses():
    with pytest.raises(ValueError) as caught:
        GeoidSwapReading(
            source_model_name="GEOID12B",
            target_model_name="GEOID18",
            n_source_m=-33.828,
            n_target_m=-33.796,
            shift_m=+0.032,  # the sign flip the arithmetic guard exists for
        )
    assert "H_out = H_in + N_in - N_out" in str(caught.value)


def test_a_swap_reading_naming_one_model_twice_refuses():
    with pytest.raises(ValueError):
        GeoidSwapReading(
            source_model_name="GEOID18",
            target_model_name="GEOID18",
            n_source_m=-33.796,
            n_target_m=-33.796,
            shift_m=0.0,
        )


def test_a_swap_reading_refuses_a_record_where_a_name_belongs():
    with pytest.raises(TypeError) as caught:
        GeoidSwapReading(
            source_model_name=geoid.GEOID12B_MODEL,
            target_model_name="GEOID18",
            n_source_m=-33.828,
            n_target_m=-33.796,
            shift_m=-0.032,
        )
    assert "model.name" in str(caught.value)
