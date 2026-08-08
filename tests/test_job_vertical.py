"""WP-V6: the vertical datum wiring in ``michspc.job``.

What is tested here, and against what truth:

* The settings refusals of docs/PLAN-vertical-datums.md section 3.5, extended
  by the session lead: a vertical job missing a datum, a HORIZONTAL job
  supplied with one, the registry's own two refusal classes propagating
  untouched, the geoid-vs-target-datum guard, and the #11-finding-1 impostor
  guards on the new fields.
* The order of operations of plan section 3.6 - shift before geoid lookup
  before factors - pinned by recording what ``factors_at`` actually receives.
* End-to-end elevations against the frozen NGS NCAT anchors of
  ``tests/fixtures/vertcon_anchors.py``. NCAT is another implementation of the
  same VERTCON model, not a measurement of the ground; what these prove is
  that a whole job reads NGS's grid the way NGS reads it.
* The per-point failure shape: outside VERTCON coverage, the horizontal result
  stands and the elevation is refused rather than passed through unshifted.
* The DESIGN.md #38 longitude-boundary note assigned to WP-V6: a 0-360 east
  longitude in a geodetic file refuses at the job boundary, naming the row and
  the convention, and never reaches the NGS grid readers as a "valid"
  position.

Tolerances are derived, not chosen to pass: NCAT prints heights and sigmas to
0.001 m, so an anchor's shift (a difference of two printed figures) carries
+/-0.001 m of quantization, and the reader's own measured worst residual
against the 20 anchors is 0.4716 mm (tests/test_vertcon.py). 0.0005 m is the
bound test_vertcon already holds shifts to, and a job's output elevation is
exactly 200.000 + shift at these anchors, so the same bound applies to it.
"""

from __future__ import annotations

import pytest

from michspc import job as jobmod
from michspc.fileio import geoid, pnezd, vertcon
from michspc.job import (
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    VerticalReading,
    run,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.vertical import (
    NAPGD2022,
    NAVD88,
    NGVD29,
    VerticalDatum,
    VerticalDatumNotUsableError,
    VerticalDatumStatus,
    VerticalTransformationUnavailableError,
)
from michspc.spc.zones import MI_CENTRAL, MI_SOUTH
from tests.fixtures.vertcon_anchors import (
    NAVD88_TO_NGVD29_ANCHORS,
    NCAT_PRINTED,
    NGVD29_TO_NAVD88_ANCHORS,
)

# The bound test_vertcon.py already holds every anchor's shift to - NCAT's
# half-printed-unit, which the reader's measured 0.4716 mm worst residual sits
# inside. See the module docstring for the derivation.
SHIFT_TOLERANCE_M = 0.0005

ANCHOR_22 = next(a for a in NGVD29_TO_NAVD88_ANCHORS if a.name == "anchor-22")
ANCHOR_22_INVERSE = next(
    a for a in NAVD88_TO_NGVD29_ANCHORS if a.name == "anchor-22"
)
MAX_SIGMA = next(a for a in NGVD29_TO_NAVD88_ANCHORS if a.name == "max-sigma")


def _geodetic_source(
    latitude: float,
    longitude: float,
    elevation: str = "200.000",
    point_id: str = "101",
) -> pnezd.PnezdFile:
    """One geodetic row, decimal degrees negative west, Z in the input unit."""
    return pnezd.parse_lines(
        [f"{point_id},{latitude},{longitude},{elevation},VERT TEST"]
    )


def _vertical_settings(**overrides) -> JobSettings:
    """A geodetic-input vertical job, NGVD 29 -> NAVD 88, metres in and out.

    Geodetic input because the anchors carry latitude and longitude, so no
    State Plane coordinate has to be derived to sit a point exactly on one.
    """
    base = dict(
        input_path=None,
        output_directory=None,
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    base.update(overrides)
    return JobSettings(**base)


def _horizontal_settings(**overrides) -> JobSettings:
    base = dict(
        vertical_mode=VerticalMode.HORIZONTAL,
        source_vertical_datum=None,
        target_vertical_datum=None,
    )
    base.update(overrides)
    return _vertical_settings(**base)


# ==========================================================================
# Settings refusals - all before any point converts (plan section 3.5).
# ==========================================================================


def test_the_default_settings_are_horizontal_with_no_datums():
    """The defaults preserve today's behaviour exactly: a caller that never
    heard of vertical datums gets the job it always got, with nothing tagged
    and every point's ``vertical`` None."""
    settings = _horizontal_settings()
    assert settings.vertical_mode is VerticalMode.HORIZONTAL
    assert settings.source_vertical_datum is None
    assert settings.target_vertical_datum is None

    # And by DEFAULT, not just when stated: the field defaults themselves.
    fields = {f.name: f for f in JobSettings.__dataclass_fields__.values()}
    assert fields["vertical_mode"].default is VerticalMode.HORIZONTAL
    assert fields["source_vertical_datum"].default is None
    assert fields["target_vertical_datum"].default is None

    result = run(settings, source=_geodetic_source(43.0, -84.5))
    point = result.points[0]
    assert point.vertical is None
    # Metres in, metres out: 200.000 exactly, untouched.
    assert point.output_elevation == 200.0


@pytest.mark.parametrize(
    "missing, kept",
    [
        ("source_vertical_datum", "target_vertical_datum"),
        ("target_vertical_datum", "source_vertical_datum"),
    ],
)
def test_a_vertical_job_missing_one_datum_is_refused_naming_it(missing, kept):
    """Plan section 3.5's first refusal, in the longitude-convention style:
    name what is missing, say there is no default, say why assuming would be
    dangerous."""
    settings = _vertical_settings(**{missing: None})

    with pytest.raises(ValueError) as caught:
        run(settings, source=_geodetic_source(43.0, -84.5))

    message = str(caught.value)
    # Names the missing field and not the one that was stated, so a user with
    # one datum chosen is not told to go check both.
    assert missing in message
    assert kept not in message
    assert "0.41 m" in message


def test_a_vertical_job_missing_both_datums_names_both():
    settings = _vertical_settings(
        source_vertical_datum=None, target_vertical_datum=None
    )

    with pytest.raises(ValueError) as caught:
        run(settings, source=_geodetic_source(43.0, -84.5))

    message = str(caught.value)
    assert "source_vertical_datum" in message
    assert "target_vertical_datum" in message


@pytest.mark.parametrize(
    "supplied",
    [
        {"source_vertical_datum": NGVD29},
        {"target_vertical_datum": NAVD88},
        {"source_vertical_datum": NGVD29, "target_vertical_datum": NAVD88},
    ],
)
def test_a_horizontal_job_with_a_datum_supplied_is_refused(supplied):
    """The mirror of the longitude None-statement rule: a datum handed to a
    job that will never apply or record it is a contradiction, and silently
    ignoring it would let a caller believe an elevation conversion happened.
    Falsified at the WP-V6 build by deleting this refusal: this test failed
    (the job ran, elevations unshifted, datums silently dropped) while the
    rest of the suite stayed green."""
    settings = _horizontal_settings(**supplied)

    with pytest.raises(ValueError) as caught:
        run(settings, source=_geodetic_source(43.0, -84.5))

    message = str(caught.value)
    for label in supplied:
        assert label in message
    assert "horizontal" in message.lower()
    assert "HORIZONTAL_AND_VERTICAL" in message


def test_the_registry_refusal_for_an_unusable_datum_propagates_untouched():
    """``require_vertical_pair``'s own class reaches the caller - not a
    wrapper, because spc.vertical tells callers to catch these by name."""
    settings = _vertical_settings(
        source_vertical_datum=NAVD88, target_vertical_datum=NAPGD2022
    )

    with pytest.raises(VerticalDatumNotUsableError) as caught:
        run(settings, source=_geodetic_source(43.0, -84.5))

    assert "NAPGD2022" in str(caught.value)


def test_the_registry_refusal_for_an_unpublished_pair_propagates_untouched():
    """A usable datum the registry has no pair for - the second refusal class,
    reachable only with a hand-built record, which is exactly what a future
    datum arriving without its transformation would be."""
    fake = VerticalDatum(
        code="IGLD85",
        name="A usable datum no transformation is registered for",
        citation="hand-built for this test",
        status=VerticalDatumStatus.USABLE,
    )
    settings = _vertical_settings(target_vertical_datum=fake)

    with pytest.raises(VerticalTransformationUnavailableError) as caught:
        run(settings, source=_geodetic_source(43.0, -84.5))

    assert "IGLD85" in str(caught.value)


def test_vertical_mode_refuses_the_boolean_impostor():
    """``vertical_mode=True`` is the habit a boolean toggle teaches, and an
    ``is`` comparison would silently treat it as some mode nobody chose."""
    settings = _vertical_settings(vertical_mode=True)

    with pytest.raises(TypeError, match="VerticalMode"):
        run(settings, source=_geodetic_source(43.0, -84.5))


@pytest.mark.parametrize(
    "field_name, impostor",
    [
        ("source_vertical_datum", MI_SOUTH),  # a Zone: carries code/name/citation
        ("target_vertical_datum", True),
        ("source_vertical_datum", "NGVD29"),  # the code where the record belongs
    ],
)
def test_the_datum_fields_refuse_impostor_records_by_name(field_name, impostor):
    """The #11-finding-1 class, closed at these two fields exactly as it is
    closed on ``geoid_model`` beside them."""
    settings = _vertical_settings(**{field_name: impostor})

    with pytest.raises(TypeError) as caught:
        run(settings, source=_geodetic_source(43.0, -84.5))

    message = str(caught.value)
    assert field_name in message
    assert "VerticalDatum" in message


def test_a_navd88_to_ngvd29_job_computes_factors_from_the_source_era_height(
    monkeypatch,
):
    """The either-endpoint rule (DESIGN.md #41, superseding plan section
    3.5's target-datum-only guard, which would have refused this job outright
    and dead-ended WP-V8's dropdowns for every NGVD 29 target). Both shipped
    geoid models publish NAVD 88 separations; in a NAVD88 -> NGVD29 job the
    NAVD 88 height is the SOURCE height, so the factors are computed from it
    - the era-consistent choice, and more correct than the plan's rule, which
    would have handed the shifted NGVD 29 height to a NAVD 88 separation.
    Falsified at the WP-V6 gate-fix round by deleting the factor-era
    override: the recorded height came back shifted (200.1402) and this test
    failed."""
    recorded: list[float] = []
    real_factors_at = jobmod.factors_at

    def recording_factors_at(scale, height, geoid_height, *args, **kwargs):
        recorded.append(height)
        return real_factors_at(scale, height, geoid_height, *args, **kwargs)

    monkeypatch.setattr(jobmod, "factors_at", recording_factors_at)

    settings = _vertical_settings(
        source_vertical_datum=NAVD88,
        target_vertical_datum=NGVD29,
        # geoid_model left at its GEOID18 default - the likeliest real call.
    )
    result = run(settings, source=_geodetic_source(43.0, -84.5))
    point = result.points[0]

    # The job succeeds, the Z column is the SHIFTED (NGVD 29) height...
    assert point.output_elevation == pytest.approx(
        ANCHOR_22_INVERSE.target_height_m, abs=SHIFT_TOLERANCE_M
    )
    # ...and the factors were built from the SOURCE (NAVD 88) height, which
    # is the input 200.000 - NOT the shifted value the Z column carries.
    assert len(recorded) == 1
    assert recorded[0] == 200.0
    assert recorded[0] != point.output_elevation
    assert point.factors.elevation_factor is not None
    assert point.factors.combined_factor is not None


def test_an_ngvd29_target_vertical_job_with_no_geoid_model_is_legitimate():
    """geoid_model=None remains a legitimate configuration for this job: the
    shift is applied, and the elevation-dependent factors are N/A because
    nothing was looked up - not because anything refused."""
    settings = _vertical_settings(
        source_vertical_datum=NAVD88,
        target_vertical_datum=NGVD29,
        geoid_model=None,
    )
    result = run(settings, source=_geodetic_source(43.0, -84.5))
    point = result.points[0]

    # 200.000 NAVD88 -> 200.140 NGVD29 at anchor-22's position (the frozen
    # inverse anchor). The shift is applied even though no geoid is.
    assert point.output_elevation == pytest.approx(
        ANCHOR_22_INVERSE.target_height_m, abs=SHIFT_TOLERANCE_M
    )
    assert point.vertical is not None
    # No geoid model, so no elevation factor - N/A is honest, a number here
    # would have mixed eras.
    assert point.factors.elevation_factor is None
    assert point.factors.combined_factor is None


def test_a_navd88_target_vertical_job_passes_the_geoid_guard():
    result = run(_vertical_settings(), source=_geodetic_source(43.0, -84.5))
    point = result.points[0]
    assert point.factors.elevation_factor is not None
    assert point.factors.combined_factor is not None


def test_an_identity_ngvd29_job_with_a_geoid_model_is_refused():
    """The one configuration the widened either-endpoint rule still refuses
    (DESIGN.md #41): NGVD29 -> NGVD29 shifts nothing, so no NAVD 88 height
    exists at ANY stage of the job, and a NAVD 88 separation has nothing
    honest to combine with. The refusal's advice is achievable - run the job
    in horizontal mode - unlike the plan-era message, whose remedies were a
    geoid model that does not exist and a setting no interface offers
    (WP-V6 review gate, MEDIUM 5). Falsified by deleting the either-endpoint
    guard: this test fails."""
    settings = _vertical_settings(
        source_vertical_datum=NGVD29, target_vertical_datum=NGVD29
    )

    with pytest.raises(geoid.GeoidError) as caught:
        run(settings, source=_geodetic_source(43.0, -84.5))

    message = str(caught.value)
    assert "no stage of this job's elevations" in message
    assert "horizontal mode" in message
    assert "GEOID18" in message


# ==========================================================================
# End-to-end anchors: file -> job.run -> converted elevation, against NCAT.
# ==========================================================================


def test_anchor_22_converts_200_ngvd29_to_navd88_in_metres():
    """DESIGN.md #22's anchor through the whole job: 200.000 m NGVD 29 at
    43.0 N, 84.5 W becomes 199.860 m NAVD 88. This is the single value that
    fixes sign = +1; a sign flip lands at 200.140 and misses by 280x the
    tolerance. Falsified at the WP-V6 build by negating the sign at the
    wiring call site: this test failed at 200.1402 against 199.8600."""
    result = run(_vertical_settings(), source=_geodetic_source(43.0, -84.5))
    point = result.points[0]

    assert point.output_elevation == pytest.approx(
        ANCHOR_22.target_height_m, abs=SHIFT_TOLERANCE_M
    )
    assert point.vertical is not None
    assert point.vertical.shift_m == pytest.approx(
        ANCHOR_22.shift_m, abs=SHIFT_TOLERANCE_M
    )
    assert point.vertical.sigma_m is not None
    assert point.vertical.sigma_unavailable_reason is None


def test_anchor_22_in_international_feet_output():
    """The same anchor with the Z column written in international feet: the
    shift happens in metres and only the boundary re-expresses it, so the
    output times 0.3048 must land on the metric anchor to the same bound."""
    result = run(
        _vertical_settings(output_unit=INTERNATIONAL_FEET),
        source=_geodetic_source(43.0, -84.5),
    )
    point = result.points[0]

    assert point.output_elevation * 0.3048 == pytest.approx(
        ANCHOR_22.target_height_m, abs=SHIFT_TOLERANCE_M
    )


def test_the_inverse_direction_matches_its_anchor():
    """One grid, sign reversed: 200.000 m NAVD 88 -> 200.140 m NGVD 29 at the
    same position (frozen inverse anchor). geoid_model=None because the job
    targets NGVD 29 - the refusal above is the reason, not an accident."""
    settings = _vertical_settings(
        source_vertical_datum=NAVD88,
        target_vertical_datum=NGVD29,
        geoid_model=None,
    )
    result = run(settings, source=_geodetic_source(43.0, -84.5))
    point = result.points[0]

    assert point.output_elevation == pytest.approx(
        ANCHOR_22_INVERSE.target_height_m, abs=SHIFT_TOLERANCE_M
    )
    assert point.vertical.shift_m == pytest.approx(
        ANCHOR_22_INVERSE.shift_m, abs=SHIFT_TOLERANCE_M
    )


def test_forward_then_inverse_round_trips_to_the_input():
    """(200 + g) - g, with g read from the same grid cell both times. The
    intermediate travels through a full-precision repr in the second file, so
    the only error possible is one IEEE add and one subtract - bounded far
    below anything a Z column can carry."""
    forward = run(_vertical_settings(), source=_geodetic_source(43.0, -84.5))
    z_navd88 = forward.points[0].output_elevation

    inverse = run(
        _vertical_settings(
            source_vertical_datum=NAVD88,
            target_vertical_datum=NGVD29,
            geoid_model=None,
        ),
        source=_geodetic_source(43.0, -84.5, elevation=repr(z_navd88)),
    )
    z_back = inverse.points[0].output_elevation

    # Hand-derived bound: one add and one subtract of a ~0.14 m value against
    # 200 m costs at most a few ulps of 200, ~3e-14 m each.
    assert abs(z_back - 200.0) < 1e-9


def test_every_forward_anchor_reproduces_through_a_full_job():
    """All 20 frozen NGVD 29 -> NAVD 88 anchors, converted in ONE job from one
    file - the path a real coordinate file takes, not twenty single-point
    calls. Every output elevation must land on NCAT's printed figure within
    the derived bound. Anchors in the north raise outside-zone-extent
    warnings against MI_SOUTH; a warning is not a refusal and the elevations
    do not depend on the zone."""
    lines = [
        f"P{i:02d},{a.latitude},{a.longitude},200.000,{a.name}"
        for i, a in enumerate(NGVD29_TO_NAVD88_ANCHORS)
    ]
    result = run(_vertical_settings(), source=pnezd.parse_lines(lines))

    assert len(result.points) == len(NGVD29_TO_NAVD88_ANCHORS)
    for point, anchor in zip(result.points, NGVD29_TO_NAVD88_ANCHORS):
        assert point.output_elevation == pytest.approx(
            anchor.target_height_m, abs=SHIFT_TOLERANCE_M
        ), anchor.name


def test_the_max_sigma_anchor_carries_its_sigma_per_point():
    """The disclosure point that decided plan section 5: at 43.05 N, 86.20 W
    the sigma is 0.366 m against a shift of -0.144 m - larger than the shift
    itself. The per-point reading must carry it; a job-level constant would
    have hidden it."""
    result = run(
        _vertical_settings(),
        source=_geodetic_source(MAX_SIGMA.latitude, MAX_SIGMA.longitude),
    )
    point = result.points[0]

    assert point.vertical.sigma_m == pytest.approx(
        MAX_SIGMA.sigma_m, abs=NCAT_PRINTED["sigma_m"]
    )
    assert point.vertical.shift_m == pytest.approx(
        MAX_SIGMA.shift_m, abs=SHIFT_TOLERANCE_M
    )
    assert point.output_elevation == pytest.approx(
        MAX_SIGMA.target_height_m, abs=SHIFT_TOLERANCE_M
    )
    # The disclosure itself: the uncertainty exceeds the shift's magnitude.
    assert point.vertical.sigma_m > abs(point.vertical.shift_m)


# ==========================================================================
# Identity pairs: no grid is read, the elevation is bit-identical.
# ==========================================================================


def test_an_identity_job_reads_no_grid_and_leaves_the_elevation_bit_identical(
    monkeypatch,
):
    """NAVD 88 -> NAVD 88 must succeed with the VERTCON files unreadable,
    because an identity applies no grid (``apply_shift`` refuses a grid value
    for one). ``default_grids`` is replaced with a tripwire, so any read at
    all fails this test loudly."""

    def _must_not_load():
        raise AssertionError(
            "an identity vertical job read the VERTCON grids"
        )

    monkeypatch.setattr(vertcon, "default_grids", _must_not_load)

    settings = _vertical_settings(
        source_vertical_datum=NAVD88, target_vertical_datum=NAVD88
    )
    result = run(settings, source=_geodetic_source(43.0, -84.5))
    point = result.points[0]

    # Bit-identical to the horizontal job's Z, not merely close: the shift is
    # exactly 0.0 and 200.0 + 0.0 is exact.
    horizontal = run(
        _horizontal_settings(), source=_geodetic_source(43.0, -84.5)
    )
    assert point.output_elevation == horizontal.points[0].output_elevation
    assert point.output_elevation == 200.0

    assert point.vertical is not None
    assert point.vertical.shift_m == 0.0
    assert point.vertical.transformation.is_identity


def test_an_identity_reading_is_distinguishable_from_a_negative_sigma_reading():
    """Both carry sigma None; the reasons must tell them apart (DESIGN.md #36
    and the WP-V6 brief). Identity: no model ran, so no model uncertainty
    exists - NOT sigma 0.0, which would fabricate a measured certainty."""
    identity = run(
        _vertical_settings(
            source_vertical_datum=NAVD88, target_vertical_datum=NAVD88
        ),
        source=_geodetic_source(43.0, -84.5),
    ).points[0]

    assert identity.vertical.sigma_m is None
    assert (
        identity.vertical.sigma_unavailable_reason
        == "no modeled transformation was applied, so no model uncertainty exists"
    )

    # The negative-sigma position of DESIGN.md #36: the .err grid
    # interpolates to -0.009651646 m at 42.475 N, 83.125 W, which cannot be a
    # one-sigma. The shift is unaffected and still reported.
    negative = run(
        _vertical_settings(), source=_geodetic_source(42.475, -83.125)
    ).points[0]

    assert negative.vertical.sigma_m is None
    reason = negative.vertical.sigma_unavailable_reason
    assert reason is not None
    assert reason != identity.vertical.sigma_unavailable_reason
    assert "42.475000" in reason and "-83.125000" in reason
    assert "modeled_error_raw_m" in reason
    # The shift and the converted elevation are present regardless.
    assert isinstance(negative.vertical.shift_m, float)
    assert negative.output_elevation is not None


def test_a_vertical_reading_may_not_be_silent_about_a_missing_sigma():
    """The __post_init__ pairing rule, both directions."""
    transformation = jobmod.require_vertical_pair(NGVD29, NAVD88)

    with pytest.raises(ValueError, match="must say why"):
        VerticalReading(
            transformation=transformation,
            shift_m=-0.14,
            sigma_m=None,
            sigma_unavailable_reason=None,
        )

    with pytest.raises(ValueError, match="contradict"):
        VerticalReading(
            transformation=transformation,
            shift_m=-0.14,
            sigma_m=0.001,
            sigma_unavailable_reason="also absent, somehow",
        )


# ==========================================================================
# The section 3.6 ordering pin, and the datum-tag check.
# ==========================================================================


def test_factors_receive_the_shifted_height_not_the_input_height(monkeypatch):
    """THE ordering pin for plan section 3.6: step 3 (shift) precedes step 5
    (factors). ``factors_at`` is wrapped to record the orthometric height it
    is handed; in a vertical job that must be the SHIFTED metres - the exact
    value the Z column reports - and not the input 200.000. Falsified at the
    WP-V6 build by reordering (computing factors from ``elevation_m``): the
    recorded height came back 200.0 and this test failed."""
    recorded: list[float] = []
    real_factors_at = jobmod.factors_at

    def recording_factors_at(scale, height, geoid_height, *args, **kwargs):
        recorded.append(height)
        return real_factors_at(scale, height, geoid_height, *args, **kwargs)

    monkeypatch.setattr(jobmod, "factors_at", recording_factors_at)

    result = run(_vertical_settings(), source=_geodetic_source(43.0, -84.5))
    point = result.points[0]

    assert len(recorded) == 1
    # The height the factors saw IS the height the Z column reports (metres
    # out, so they are the same number), and it is not the unshifted input.
    assert recorded[0] == point.output_elevation
    assert recorded[0] != 200.0
    assert recorded[0] == pytest.approx(
        ANCHOR_22.target_height_m, abs=SHIFT_TOLERANCE_M
    )


def test_every_point_of_a_vertical_job_carries_the_settings_own_pair():
    """The datum tag is CHECKED, not carried (#36 reviewer note): the
    transformation on every reading is the record for the settings' own
    datums. If the wiring ever re-derived or crossed pairs, this is the pin
    that names it."""
    lines = [
        f"P{i:02d},{a.latitude},{a.longitude},200.000,{a.name}"
        for i, a in enumerate(NGVD29_TO_NAVD88_ANCHORS[:5])
    ]
    settings = _vertical_settings()
    result = run(settings, source=pnezd.parse_lines(lines))

    for point in result.points:
        assert point.vertical is not None
        assert (
            point.vertical.transformation.source.code
            == settings.source_vertical_datum.code
        )
        assert (
            point.vertical.transformation.target.code
            == settings.target_vertical_datum.code
        )


def test_a_transformation_for_the_wrong_pair_is_refused_at_the_row():
    """The check itself, exercised directly: hand ``_convert_row`` a
    transformation that is not the settings' pair and it must refuse, because
    ``apply_shift`` takes a bare float and nothing downstream could notice."""
    settings = _vertical_settings()  # states NGVD29 -> NAVD88
    wrong = jobmod.require_vertical_pair(NAVD88, NGVD29)  # the reverse record
    row = _geodetic_source(43.0, -84.5).rows[0]

    with pytest.raises(ValueError) as caught:
        jobmod._convert_row(
            row, settings, None, wrong, vertcon.default_grids()
        )

    message = str(caught.value)
    assert "NAVD88 -> NGVD29" in message
    assert "NGVD29 -> NAVD88" in message


# ==========================================================================
# Per-point failure: outside VERTCON coverage, and elevation-less points.
# ==========================================================================


def test_a_point_outside_vertcon_coverage_keeps_its_horizontal_result():
    """The GEOID_UNAVAILABLE shape, for the shift: 52.0 N is north of the
    CONUS grid's 50 N edge (VERTCON3_CONUS_GEOMETRY), so no shift exists
    there. The horizontal coordinates stand; the elevation is NOT converted
    and NOT passed through unshifted - the Z is blank, the factors N/A, and
    the warning says all of that. Falsified at the WP-V6 build by making the
    branch pass the elevation through unshifted: this test failed on
    output_elevation."""
    settings = _vertical_settings()
    result = run(settings, source=_geodetic_source(52.0, -84.5))
    point = result.points[0]

    # The horizontal result stands, identical to a horizontal job's.
    horizontal = run(
        _horizontal_settings(), source=_geodetic_source(52.0, -84.5)
    ).points[0]
    assert point.output_northing == horizontal.output_northing
    assert point.output_easting == horizontal.output_easting

    # The elevation is refused, not passed through: an unconverted NGVD 29
    # height in a Z column claiming NAVD 88 is the tier sentence's failure.
    assert point.output_elevation is None
    assert point.vertical is None
    assert point.factors.elevation_factor is None
    assert point.factors.combined_factor is None
    # The grid scale factor does not depend on elevation and is still there.
    assert point.factors.grid_scale_factor == pytest.approx(
        horizontal.factors.grid_scale_factor
    )

    from michspc.spc.convert import WarningCode

    raised = [
        w
        for w in point.warnings
        if w.code is WarningCode.VERTICAL_SHIFT_UNAVAILABLE
    ]
    assert len(raised) == 1
    message = raised[0].message
    assert "52.000000" in message
    assert "NOT converted" in message
    assert "HORIZONTAL" in message and "stand" in message


# ==========================================================================
# The WP-V6 review gate's findings, each pinned (DESIGN.md #41).
# ==========================================================================


def test_the_record_does_not_call_a_coverage_refused_z_field_blank(tmp_path):
    """The gate's HIGH 1: a two-point vertical job whose second point sits
    outside VERTCON coverage produced a job record listing that point under
    "Blank elevation field" - a false statement about a populated field in a
    sealed audit document, WP-R2 fix C's defect through a new door. The
    record must name the fourth cause as its own: the Z was read, and the
    elevation was refused rather than converted. Falsified by reverting the
    report bucketing: the false sentence returns and this test fails."""
    from michspc.fileio import report

    input_path = tmp_path / "vertical.csv"
    input_path.write_text(
        "201,43.0,-84.5,200.000,IN COVERAGE\n"
        "202,52.0,-84.5,300.000,OUT OF COVERAGE\n",
        encoding="utf-8",
    )
    settings = _vertical_settings(
        input_path=input_path, output_directory=tmp_path / "out"
    )
    result = run(settings)
    text = report.build_report(result)

    # Neither point's Z field is blank or zero, so the blank/zero buckets
    # must not appear at all - point 202's field read 300.000.
    assert "Blank elevation field" not in text
    assert "held exactly 0.00" not in text
    # The fourth cause is named as its own, with the point under it.
    assert "not convertible between vertical datums" in text
    assert "202" in text
    assert "deliberately absent" in text


@pytest.mark.parametrize(
    "bad_sigma",
    [-0.5, float("nan"), float("inf")],
    ids=["negative", "nan", "inf"],
)
def test_a_vertical_reading_refuses_a_sigma_that_is_not_one(bad_sigma):
    """The gate's MEDIUM 4: this frozen record is what WP-V7's output layer
    prints from, and a negative one-sigma reaching a screen is the defect #36
    spent a work package refusing. vertcon.sigma_is_physical is the one rule,
    now applied at its third site so the record and the reader cannot
    disagree."""
    from michspc.spc.vertical import require_vertical_pair

    transformation = require_vertical_pair(NGVD29, NAVD88)
    with pytest.raises(ValueError, match="sigma"):
        VerticalReading(
            transformation=transformation,
            shift_m=-0.14,
            sigma_m=bad_sigma,
            sigma_unavailable_reason=None,
        )


def test_a_vertical_reading_refuses_an_empty_reason_and_a_string_record():
    """The rest of MEDIUM 4: an empty reason is a silence wearing the shape of
    an explanation (the rule VerticalTransformation applies to its own
    citation and caveat), and a string spelling "NGVD29 -> NAVD88" duck-types
    deep into an output layer before anything asks it for a
    direction_statement."""
    from michspc.spc.vertical import require_vertical_pair

    transformation = require_vertical_pair(NGVD29, NAVD88)
    with pytest.raises(ValueError, match="empty"):
        VerticalReading(
            transformation=transformation,
            shift_m=-0.14,
            sigma_m=None,
            sigma_unavailable_reason="   ",
        )
    with pytest.raises(TypeError, match="VerticalTransformation"):
        VerticalReading(
            transformation="NGVD29 -> NAVD88",
            shift_m=-0.14,
            sigma_m=0.001,
            sigma_unavailable_reason=None,
        )


def test_a_row_on_vertical_settings_with_no_transformation_is_refused():
    """The gate's LOW 6, the mirror of the datum-tag check: settings that
    promise a shift with NO record to apply it would otherwise write an
    unshifted source-datum height into a Z column claiming the target datum,
    with no reading and no warning. Unreachable through run(), which derives
    the record from the same settings - this holds the function itself."""
    row = _geodetic_source(43.0, -84.5).rows[0]

    with pytest.raises(ValueError) as caught:
        jobmod._convert_row(
            row,
            _vertical_settings(),
            None,
            transformation=None,
            vertcon_grids=None,
        )

    message = str(caught.value)
    assert "no transformation record" in message
    assert "NGVD29" in message and "NAVD88" in message


def test_a_structural_grid_failure_is_not_reported_as_a_coverage_gap(monkeypatch):
    """The gate's LOW 7: coverage is decided by asking (pair.contains), so a
    VertconError raised by the READ is structural - a broken grid object -
    and must propagate loudly rather than being caught and headlined as "the
    grids do not cover this point" over a true footnote."""

    class BrokenPair:
        def contains(self, latitude, longitude):
            return True

        def reading_at(self, latitude, longitude):
            raise vertcon.VertconError("the transformation grid is truncated")

    monkeypatch.setattr(vertcon, "default_grids", lambda: BrokenPair())

    with pytest.raises(vertcon.VertconError, match="truncated"):
        run(_vertical_settings(), source=_geodetic_source(43.0, -84.5))


def test_an_elevation_less_point_in_a_vertical_job_is_unchanged_from_today():
    """No height, no shift to apply: vertical None, Z None, and exactly the
    warnings a horizontal job raises - nothing invented, nothing added."""
    source = pnezd.parse_lines(["CP-4,43.0,-84.5,,NO ELEVATION"])
    vertical = run(_vertical_settings(), source=source).points[0]
    horizontal = run(_horizontal_settings(), source=source).points[0]

    assert vertical.output_elevation is None
    assert vertical.vertical is None
    assert vertical.factors.elevation_factor is None
    assert [w.code for w in vertical.warnings] == [
        w.code for w in horizontal.warnings
    ]


def test_a_horizontal_zone_to_zone_job_is_untouched_by_the_new_fields():
    """The sacred regression, in-suite: a default-settings zone-to-zone job
    carries vertical None on every point and a Z that is the input
    re-expressed. (The byte-level check against the pre-WP-V6 commit was run
    at the build: clean PNEZD, audit CSV and job record identical.)"""
    source = pnezd.parse_lines(
        ["101,780000.000,13123359.580,800.00,IRON PIPE"]
    )
    settings = JobSettings(
        input_path=None,
        output_directory=None,
        direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_SOUTH,
        target_zone=MI_CENTRAL,
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
        longitude_convention=None,
    )
    result = run(settings, source=source)
    point = result.points[0]

    assert point.vertical is None
    # 800 ift -> 243.84 m -> 800 ift; only IEEE rounding possible.
    assert point.output_elevation == pytest.approx(800.0, abs=1e-9)


# ==========================================================================
# The #38 longitude-boundary note: what holds the line, documented.
#
# Checked first, as the brief required: the core's own domain gate
# (lambert._require_valid_geodetic, pinned in tests/test_lambert.py) already
# REFUSES - not warns - any latitude outside (-90, 90) or longitude outside
# [-180, 180] before a coordinate is computed, and the vertical shift runs
# after the horizontal conversion, so a 0-360 longitude could never reach the
# NGS grid readers through job.run even before WP-V6. What was missing is a
# refusal that names the ROW and the CONVENTION IN FORCE - the things only
# the job layer knows - so WP-V6 adds one at the single entry point where the
# convention is applied, with the same bounds as the core's gate.
# ==========================================================================


def test_a_0_360_longitude_is_refused_naming_the_row_and_the_convention():
    """43.0 N, 275.5 "east" is anchor-22's position in the 0-360 convention.
    Unrefused, the NGS readers would accept it silently - shift_m(43.0, 275.5)
    equals shift_m(43.0, -84.5) byte-identically (DESIGN.md #38) - while the
    State Plane conversion placed the point thousands of kilometres away."""
    settings = _vertical_settings()

    with pytest.raises(ValueError) as caught:
        run(settings, source=_geodetic_source(43.0, 275.5))

    message = str(caught.value)
    assert "point 101" in message
    assert "275.5" in message
    assert "negative west" in message
    assert "-84.5" in message  # the subtract-360 advice names the fix


def test_the_same_0_360_longitude_is_refused_under_positive_west_too():
    """Under positive west, 275.5 becomes signed -275.5 - differently wrong,
    equally refused, and the message names the convention that was in force
    so the user can see which reading produced the out-of-range value."""
    settings = _vertical_settings(
        longitude_convention=LongitudeConvention.POSITIVE_WEST
    )

    with pytest.raises(ValueError) as caught:
        run(settings, source=_geodetic_source(43.0, 275.5))

    message = str(caught.value)
    assert "point 101" in message
    assert "positive west" in message


def test_an_out_of_domain_latitude_is_refused_naming_the_row():
    settings = _horizontal_settings()

    with pytest.raises(ValueError) as caught:
        run(settings, source=_geodetic_source(95.0, -84.5))

    message = str(caught.value)
    assert "point 101" in message
    assert "latitude" in message.lower()
    assert "95.0" in message


def test_a_0_360_longitude_never_reaches_the_vertcon_reader(monkeypatch):
    """The property the #38 note asked WP-V6 to secure, held executable: the
    refusal fires before any per-point grid read, so the reader that would
    have accepted 275.5 silently is never consulted with it."""
    consulted: list[tuple[float, float]] = []
    real = vertcon.shift_and_sigma_m

    def recording(latitude, longitude, grids=None):
        consulted.append((latitude, longitude))
        return real(latitude, longitude, grids)

    monkeypatch.setattr(vertcon, "shift_and_sigma_m", recording)

    with pytest.raises(ValueError):
        run(_vertical_settings(), source=_geodetic_source(43.0, 275.5))

    assert consulted == []


def test_an_in_range_geodetic_position_still_converts():
    """The refusal must not catch anything legitimate: the exact boundary
    values and ordinary Michigan positions all pass."""
    for latitude, longitude in [
        (43.0, -84.5),
        (41.7, -180.0),  # boundary: refused only OUTSIDE [-180, 180]
        (41.7, 180.0),
    ]:
        result = run(
            _horizontal_settings(),
            source=_geodetic_source(latitude, longitude),
        )
        assert len(result.points) == 1
