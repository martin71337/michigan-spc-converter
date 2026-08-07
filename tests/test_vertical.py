"""Vertical datums, the transformation registry, and the sign convention.

Every expected value below is hand-derived in the comment above it, from the
VERTCON 3.0 grid values and NGS NCAT results measured at the V0 gate and
recorded in docs/PLAN-vertical-datums.md section 2. None of them is read back
from this program's own output.

The load-bearing property in this file is the **direction of the shift**. NGVD 29
and NAVD 88 differ across Michigan by amounts that look like ordinary
elevations, so a sign error produces a Z column that is plausible and wrong by
about twice the shift - roughly a foot at the Michigan average. It is the defect
class the project has already been burned by (DESIGN.md #1, MATLAB defect 2),
and plan section 8 names it as risk 3.

No grid file is touched here. The grid value is a parameter, exactly as
``factors.factors_at`` takes the geoid height as one, so every rule in
``michspc/spc/vertical.py`` is checkable without the 2.4 MB grids present.
"""

from __future__ import annotations

import math

import pytest

from michspc.spc import frames, units, zones
from michspc.spc.vertical import (
    ALL_VERTICAL_DATUMS,
    NAPGD2022,
    NAVD88,
    NGVD29,
    REQUIRED_VERTICAL_PAIRS,
    VERTICAL_TRANSFORMATIONS,
    VerticalDatum,
    VerticalDatumError,
    VerticalDatumNotUsableError,
    VerticalDatumStatus,
    VerticalTransformation,
    VerticalTransformationUnavailableError,
    apply_shift,
    require_vertical_pair,
    signed_shift,
    vertical_datum_by_code,
)

# A datum this program does not carry, used to reach the "no published
# transformation" refusal without inventing a fake status for a real datum.
# IGLD 85 is a real vertical datum for the Great Lakes and is deliberately out
# of scope (plan section 1); it is orthometric-in-name-only - dynamic heights -
# which is exactly why a pair with it must refuse rather than be improvised.
IGLD85 = VerticalDatum(
    code="IGLD85",
    name="International Great Lakes Datum of 1985",
    citation="synthetic test record; deliberately out of scope, plan section 1",
    status=VerticalDatumStatus.USABLE,
)


# --------------------------------------------------------------------------
# The sign convention. This is the section that matters.
# --------------------------------------------------------------------------


def test_the_ngvd29_to_navd88_anchor_at_43n_84_5w():
    """Plan section 2.3, the anchor amendment #22 measured live against NCAT.

    The VERTCON 3.0 transformation grid stores NAVD88 - NGVD29 in metres, and at
    43.0 N, 84.5 W it reads -0.1402 m (plan section 2.3, our reader,
    biquadratic). It is ADDED to the source height:

        H(NAVD 88) = H(NGVD 29) + g
                   = 200.0000 + (-0.1402)
                   = 199.8598 m

    NCAT, queried live for 200.000 m NGVD 29 at that position, answered
    199.860 m (DESIGN.md #22, re-measured at the V0 gate). NCAT prints to the
    millimetre, so its 199.860 carries +/- 0.0005 m; our 199.8598 sits 0.0002 m
    - 0.2 mm - from it, which is plan section 2.3's measured figure.

    A sign error here would give 200.0000 + 0.1402 = 200.1402 m: 0.28 m from
    NCAT, and a number that looks like any other elevation.
    """
    transformation = require_vertical_pair(NGVD29, NAVD88)

    height = apply_shift(
        200.0000, grid_value_m=-0.1402, transformation=transformation
    )

    assert height == 199.8598
    # Against NGS's own service, to the millimetre it prints.
    assert abs(height - 199.860) < 0.0005


def test_the_shift_itself_is_the_grid_value_at_sign_plus_one():
    """The reported shift and the applied shift are one computation.

    Forward is sign +1, so the shift IS the grid value: -0.1402 m. If the
    record's shift column and the Z column were computed separately they could
    be signed differently, and the audit CSV would then disagree with the export
    it ships beside.
    """
    transformation = require_vertical_pair(NGVD29, NAVD88)

    assert transformation.sign == 1
    assert signed_shift(grid_value_m=-0.1402, transformation=transformation) == -0.1402


def test_a_positive_grid_value_raises_the_height_going_forward():
    """Plan section 2.4, 46.54 N 87.40 W - the one Michigan anchor that is positive.

    NCAT gives NGVD29 -> NAVD88 = +0.0340 m there. Forward:

        300.0000 + 0.0340 = 300.0340 m NAVD 88

    This is the pin that a sign flip cannot survive by coincidence: with the
    sign reversed the same input gives 299.9660 m, on the other side of the
    input, so the test fails on direction rather than on magnitude.
    """
    transformation = require_vertical_pair(NGVD29, NAVD88)

    height = apply_shift(300.0000, grid_value_m=0.0340, transformation=transformation)

    assert height == 300.0340
    assert height > 300.0000


def test_the_inverse_is_the_same_grid_with_the_sign_reversed():
    """Plan section 2.4: verified against NCAT at five points, sum 0.00 mm each.

    NAVD88 -> NGVD29 is the same grid at sign -1, so the same -0.1402 m grid
    value is SUBTRACTED:

        H(NGVD 29) = H(NAVD 88) - g
                   = 199.8598 - (-0.1402)
                   = 200.0000 m

    which is the height the forward test started from.
    """
    transformation = require_vertical_pair(NAVD88, NGVD29)

    assert transformation.sign == -1
    assert signed_shift(grid_value_m=-0.1402, transformation=transformation) == 0.1402

    height = apply_shift(
        199.8598, grid_value_m=-0.1402, transformation=transformation
    )
    assert height == 200.0000


def test_both_directions_read_one_grid():
    """One grid, one data path, two directions (plan section 2.4).

    If the reverse record ever named a second grid, the two directions could
    drift apart and a round trip would stop closing. They share the grid key,
    the model and the release.
    """
    forward = require_vertical_pair(NGVD29, NAVD88)
    reverse = require_vertical_pair(NAVD88, NGVD29)

    assert forward.grid_key == reverse.grid_key
    assert forward.model == reverse.model == "VERTCON 3.0"
    assert forward.release == reverse.release == "20190601"
    assert forward.sign == -reverse.sign


# Plan section 2.4's five NCAT-verified Michigan points: the NGVD29 -> NAVD88
# shift NCAT reported at each. The inverse at every one summed to 0.00 mm.
NCAT_MICHIGAN_SHIFTS_M = (
    (43.00, -84.50, -0.1400),
    (42.33, -83.05, -0.1710),
    (45.87, -84.73, -0.0770),
    (46.54, -87.40, +0.0340),
    (44.76, -85.62, -0.1160),
)


@pytest.mark.parametrize(
    ("latitude", "longitude", "grid_value_m"),
    NCAT_MICHIGAN_SHIFTS_M,
    ids=[f"{lat}N{abs(lon)}W" for lat, lon, _ in NCAT_MICHIGAN_SHIFTS_M],
)
def test_round_trip_returns_the_original_height_exactly(
    latitude: float, longitude: float, grid_value_m: float
):
    """NGVD29 -> NAVD88 -> NGVD29 restores the height, at each of the five points.

    Hand-derived, and it is derivable without knowing g: forward adds
    ``+1 * g`` and the inverse adds ``-1 * g`` to the same grid value, so the
    two shifts are equal and opposite by construction:

        (H + g) - g = H

    Pinned with ``==`` rather than a tolerance, because the claim is "nothing
    moved". IEEE 754 doubles make that exact for these magnitudes: g is at most
    0.171 and H is 512.0, a power of two whose neighbouring doubles are far
    finer than g, so the addition and its inverse round back to the same value.
    """
    forward = require_vertical_pair(NGVD29, NAVD88)
    reverse = require_vertical_pair(NAVD88, NGVD29)

    navd88 = apply_shift(512.0, grid_value_m=grid_value_m, transformation=forward)
    back = apply_shift(navd88, grid_value_m=grid_value_m, transformation=reverse)

    assert back == 512.0
    # And the round trip actually went somewhere: no anchor in the set is zero.
    assert navd88 != 512.0


def test_the_direction_statement_is_written_from_the_sign_it_applies():
    """The record can never be unsure which way the shift went.

    ``direction_statement`` is what the job record quotes, and it is derived
    from the same ``sign`` field ``apply_shift`` multiplies by, so the words and
    the arithmetic are incapable of disagreeing. This test states the link the
    other way round: the operator in the sentence must predict the direction a
    positive grid value moves the height.
    """
    for transformation in (
        require_vertical_pair(NGVD29, NAVD88),
        require_vertical_pair(NAVD88, NGVD29),
    ):
        statement = transformation.direction_statement
        moved = apply_shift(
            100.0, grid_value_m=1.0, transformation=transformation
        )

        # "NAVD88 = NGVD29 + g" must mean a positive g raises the height.
        if f"{transformation.target.code} = {transformation.source.code} + g" in statement:
            assert moved == 101.0
        elif (
            f"{transformation.target.code} = {transformation.source.code} - g"
            in statement
        ):
            assert moved == 99.0
        else:  # pragma: no cover - the statement stopped naming its own arithmetic
            pytest.fail(
                f"direction_statement does not state the arithmetic: {statement!r}"
            )


def test_the_direction_statement_names_what_the_grid_stores():
    """Plan section 2.3: the grid stores NAVD88 - NGVD29, in both directions.

    The reverse record subtracts that same quantity rather than storing a second
    grid of its own, and the sentence has to say so - otherwise a reader of the
    job record cannot tell whether a negative shift means the grid was negative
    or the direction was reversed.
    """
    forward = require_vertical_pair(NGVD29, NAVD88)
    reverse = require_vertical_pair(NAVD88, NGVD29)

    assert forward.grid_quantity == "NAVD88 minus NGVD29"
    assert reverse.grid_quantity == "NAVD88 minus NGVD29"
    assert "stores NAVD88 minus NGVD29" in forward.direction_statement
    assert "stores NAVD88 minus NGVD29" in reverse.direction_statement


# --------------------------------------------------------------------------
# Identity pairs: explicit records, not a shortcut.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("datum", (NAVD88, NGVD29), ids=("NAVD88", "NGVD29"))
def test_a_datum_with_itself_is_an_explicit_registered_record(datum: VerticalDatum):
    """Plan section 3.1: a NAVD 88 -> NAVD 88 job is legitimate.

    It is a record so that the job record can *state* "both datums NAVD 88, no
    shift applied" rather than have that fall out of an untested ``source is
    target`` branch in a caller.
    """
    transformation = require_vertical_pair(datum, datum)

    assert transformation.is_identity
    assert transformation.source.code == transformation.target.code == datum.code
    assert transformation.model is None
    assert transformation.release is None
    assert transformation.grid_key is None
    assert transformation.sign == 0
    assert "no shift is applied" in transformation.direction_statement
    assert datum.name in transformation.direction_statement


@pytest.mark.parametrize("datum", (NAVD88, NGVD29), ids=("NAVD88", "NGVD29"))
def test_an_identity_applies_no_shift(datum: VerticalDatum):
    """H out = H in, exactly, and the shift reported beside it is 0.0 m.

    There is no grid to read for an identity, so the grid value is None - which
    is a statement ("no grid was applied"), the idiom this repo already uses for
    an absent input path.
    """
    transformation = require_vertical_pair(datum, datum)

    assert signed_shift(grid_value_m=None, transformation=transformation) == 0.0
    assert (
        apply_shift(287.4310, grid_value_m=None, transformation=transformation)
        == 287.4310
    )


@pytest.mark.parametrize("datum", (NAVD88, NGVD29), ids=("NAVD88", "NGVD29"))
def test_an_identity_refuses_a_grid_value(datum: VerticalDatum):
    """Being handed a grid value means the wrong transformation was looked up.

    Silently discarding it would hide that; silently applying it would shift a
    height between a datum and itself.
    """
    transformation = require_vertical_pair(datum, datum)

    with pytest.raises(ValueError) as caught:
        apply_shift(287.4310, grid_value_m=-0.1402, transformation=transformation)

    assert "applies no grid" in str(caught.value)


# --------------------------------------------------------------------------
# Refusals: two distinct kinds.
# --------------------------------------------------------------------------


def test_an_unpublished_pair_refuses_and_names_the_pair():
    """Both datums usable, no transformation between them: refuse loudly.

    IGLD 85 stands in for the general case - a datum record exists and its pair
    has not been published. The refusal must name the offending pair, list what
    is registered, and say what ignoring it would cost, in the style of
    ``frames.require_same_frame``.
    """
    with pytest.raises(VerticalTransformationUnavailableError) as caught:
        require_vertical_pair(IGLD85, NAVD88)

    message = str(caught.value)
    assert "IGLD85" in message
    assert "NAVD88" in message
    assert "no published vertical transformation" in message
    assert "NGVD29 -> NAVD88" in message  # what IS registered
    assert "silently corrupt" in message


def test_the_reverse_unpublished_pair_refuses_too():
    """The refusal is about the pair, not about which side the stranger is on."""
    with pytest.raises(VerticalTransformationUnavailableError) as caught:
        require_vertical_pair(NAVD88, IGLD85)

    assert "IGLD85" in str(caught.value)


def test_napgd2022_refuses_as_declared_but_not_usable():
    """Plan section 1: NCAT returns an empty response for NAVD88 -> NAPGD2022.

    NAPGD2022 is here for the reason NATRF2022 is in ``frames.py`` - so the
    refusal has something concrete to refuse and the shape of the eventual
    addition is visible. It must refuse as *not usable*, which tells the user
    "not yet, and not by anyone", rather than as an unpublished pair, which
    invites them to look for the missing grid.
    """
    with pytest.raises(VerticalDatumNotUsableError) as caught:
        require_vertical_pair(NAVD88, NAPGD2022)

    message = str(caught.value)
    assert "NAPGD2022" in message
    assert "not usable" in message
    assert "invented" in message
    # It names what can be converted today instead of leaving the user stuck.
    assert "NGVD29, NAVD88" in message


def test_the_two_refusals_are_distinguishable():
    """A caller must be able to tell "not yet" from "never published".

    They are separate exception types, both catchable as one base for callers
    that only need "the vertical conversion was refused".
    """
    with pytest.raises(VerticalDatumNotUsableError) as not_usable:
        require_vertical_pair(NGVD29, NAPGD2022)
    with pytest.raises(VerticalTransformationUnavailableError) as unpublished:
        require_vertical_pair(NGVD29, IGLD85)

    assert not isinstance(not_usable.value, VerticalTransformationUnavailableError)
    assert not isinstance(unpublished.value, VerticalDatumNotUsableError)
    assert isinstance(not_usable.value, VerticalDatumError)
    assert isinstance(unpublished.value, VerticalDatumError)


def test_napgd2022_with_itself_is_still_refused():
    """An identity is not a loophole into an unusable datum.

    Converting NAPGD2022 to NAPGD2022 applies no shift, so it looks harmless -
    but it would let a job label its heights NAPGD2022, and this program cannot
    establish that datum. DESIGN.md #32: a conversion whose datum cannot be
    established refuses; it does not assume.
    """
    with pytest.raises(VerticalDatumNotUsableError):
        require_vertical_pair(NAPGD2022, NAPGD2022)


def test_a_rebuilt_datum_record_cannot_grant_itself_a_status():
    """Fail closed against a record that claims to be usable and is not.

    A saved job, a future loader, or a caller could rebuild a ``VerticalDatum``
    from its code. The status that governs is this module's, not the one on the
    record handed in - otherwise the NAPGD2022 refusal could be walked around by
    constructing the datum by hand.
    """
    forged = VerticalDatum(
        code="NAPGD2022",
        name="rebuilt from data",
        citation="synthetic",
        status=VerticalDatumStatus.USABLE,
    )

    with pytest.raises(VerticalDatumNotUsableError):
        require_vertical_pair(NAVD88, forged)


def test_datums_are_matched_by_code_not_by_object_identity():
    """A datum rebuilt from a saved job must still find its transformation.

    Same property ``frames.require_same_frame`` has, and the mechanism by which
    a job converted in 2026 still converts once records are reloaded rather than
    imported.
    """
    rebuilt = VerticalDatum(
        code="NGVD29",
        name="rebuilt from data",
        citation="synthetic",
        status=VerticalDatumStatus.USABLE,
    )

    transformation = require_vertical_pair(rebuilt, NAVD88)

    assert transformation.sign == 1
    assert transformation.grid_key == "ngvd29.navd88.conus"


def test_vertical_datum_by_code_refuses_an_unknown_code_and_names_the_known_ones():
    """Same contract as ``zone_by_code`` and ``unit_by_code``."""
    assert vertical_datum_by_code("NAVD88") is NAVD88
    assert vertical_datum_by_code("  NGVD29 ") is NGVD29

    with pytest.raises(KeyError) as caught:
        vertical_datum_by_code("NAVD 88")

    message = str(caught.value)
    assert "NAVD88" in message
    assert "NGVD29" in message


# --------------------------------------------------------------------------
# The registry keeps every pair it has ever carried (DESIGN.md #32).
# --------------------------------------------------------------------------


def test_the_registry_carries_every_pair_it_is_required_to_keep():
    """DESIGN.md amendment #32, stated as a requirement rather than assumed.

    The four pairs are written out here by hand rather than read from the
    module, so this test is an independent statement of the requirement and not
    a mirror of whatever the registry happens to contain. A job converted in
    2026 must still convert after NAPGD2022 lands, which means none of these
    four may ever disappear.
    """
    required = {
        ("NAVD88", "NAVD88"),
        ("NGVD29", "NGVD29"),
        ("NGVD29", "NAVD88"),
        ("NAVD88", "NGVD29"),
    }

    registered = {
        (source.code, target.code) for source, target in VERTICAL_TRANSFORMATIONS
    }
    assert required <= registered

    # And the module's own append-only requirement list says the same thing, so
    # the check that runs at import is checking the right set.
    assert REQUIRED_VERTICAL_PAIRS == required


def test_every_required_pair_actually_resolves():
    """Present in the mapping is not the same as reachable through the gate."""
    for source_code, target_code in REQUIRED_VERTICAL_PAIRS:
        source = vertical_datum_by_code(source_code)
        target = vertical_datum_by_code(target_code)

        transformation = require_vertical_pair(source, target)

        assert transformation.source.code == source_code
        assert transformation.target.code == target_code


def test_the_registry_cannot_be_emptied_at_runtime():
    """A registry whose job is to keep every pair must not be mutable.

    Read-only mapping: a later module cannot pop a pair out of it, deliberately
    or by accident, and leave a previously convertible job unconvertible.
    """
    with pytest.raises(TypeError):
        VERTICAL_TRANSFORMATIONS[(NGVD29, NAVD88)] = None  # type: ignore[index]
    with pytest.raises(AttributeError):
        VERTICAL_TRANSFORMATIONS.pop((NGVD29, NAVD88))  # type: ignore[attr-defined]


def test_every_registered_pair_is_between_usable_datums():
    """A registered pair naming an unusable datum would contradict the refusal.

    It would be reachable through ``require_vertical_pair`` only by removing the
    usability gate, so this states the invariant the gate's ordering relies on.
    """
    for source, target in VERTICAL_TRANSFORMATIONS:
        assert source.is_usable
        assert target.is_usable


def test_every_declared_datum_is_either_usable_or_refused_by_name():
    """No datum sits in the registry in an undefined third state."""
    for datum in ALL_VERTICAL_DATUMS:
        assert datum.status in (
            VerticalDatumStatus.USABLE,
            VerticalDatumStatus.DECLARED_NOT_USABLE,
        )
        assert datum.citation.strip()

    assert NAPGD2022.status is VerticalDatumStatus.DECLARED_NOT_USABLE
    assert NGVD29.is_usable
    assert NAVD88.is_usable


# --------------------------------------------------------------------------
# Disclosure: every modeled record carries its uncertainty and NGS's caveat.
# --------------------------------------------------------------------------


def test_every_modeled_record_carries_its_uncertainty_and_the_supersession_caveat():
    """DESIGN.md #22's top risk: a modeled shift laundered into an exact number.

    The caveat is NGS's own and is not optional: published NAVD 88 benchmark
    values supersede a modeled shift, and NGVD 29 network distortions of 20 cm
    or more exist. Plan section 2.8 proves that is not boilerplate - at
    43.05 N, 86.20 W in Michigan the uncertainty is 0.3656 m against a modeled
    shift of -0.1466 m: 0.3656 / 0.1466 = 2.494, so 249% of the shift itself.

    The BOUNDS pinned below are plan section 2.7's direct scan of the .err grid
    over the Michigan window - min +0.000004 m, max +0.365599 m - and not
    section 2.8's "0.001 m to 0.366 m", which the two sections disagree about.
    0.001 m is NCAT's printed resolution, not a value the grid holds, and this
    string is quoted verbatim into the job record, so it must state what this
    program's own reader can produce. Review gate finding 3 (DESIGN.md #35).
    """
    for transformation in VERTICAL_TRANSFORMATIONS.values():
        assert transformation.uncertainty_citation.strip()
        assert transformation.caveat.strip()

    modeled = require_vertical_pair(NGVD29, NAVD88)
    assert "MODELED" in modeled.caveat
    assert "benchmark" in modeled.caveat
    assert "20 cm" in modeled.caveat
    assert "0.365599" in modeled.uncertainty_citation
    assert "0.000004" in modeled.uncertainty_citation
    assert "249%" in modeled.uncertainty_citation
    # The superseded floor must not come back: it overstates the smallest
    # uncertainty this reader can report by a factor of 250.
    assert "0.001 m to" not in modeled.uncertainty_citation

    identity = require_vertical_pair(NAVD88, NAVD88)
    assert "no shift is applied" in identity.caveat
    assert "No model is applied" in identity.uncertainty_citation


# --------------------------------------------------------------------------
# Records that would be dangerous cannot be constructed.
# --------------------------------------------------------------------------


def test_an_identity_between_two_different_datums_cannot_be_built():
    """The worst record in this module's shape: it relabels without converting.

    A grid-less record from NGVD 29 to NAVD 88 would leave the height untouched
    and call it NAVD 88 - about 0.15 m of silent error in Michigan, in the Z
    column of a sealed drawing.
    """
    with pytest.raises(ValueError) as caught:
        VerticalTransformation(
            source=NGVD29,
            target=NAVD88,
            model=None,
            release=None,
            grid_key=None,
            sign=0,
            uncertainty_citation="synthetic",
            caveat="synthetic",
        )

    assert "leave the height unchanged" in str(caught.value)


def test_a_modeled_record_with_sign_zero_cannot_be_built():
    """Sign 0 would discard the grid value it just named."""
    with pytest.raises(ValueError) as caught:
        VerticalTransformation(
            source=NGVD29,
            target=NAVD88,
            model="VERTCON 3.0",
            release="20190601",
            grid_key="ngvd29.navd88.conus",
            sign=0,
            uncertainty_citation="synthetic",
            caveat="synthetic",
        )

    assert "sign 0" in str(caught.value)


@pytest.mark.parametrize("sign", (2, -2, 1000, -1000))
def test_the_sign_is_a_direction_not_a_scale_factor(sign: int):
    """A sign of 2 would double every shift and still look like a valid record."""
    with pytest.raises(ValueError) as caught:
        VerticalTransformation(
            source=NGVD29,
            target=NAVD88,
            model="VERTCON 3.0",
            release="20190601",
            grid_key="ngvd29.navd88.conus",
            sign=sign,
            uncertainty_citation="synthetic",
            caveat="synthetic",
        )

    assert "not a scale factor" in str(caught.value)


def test_a_half_specified_record_cannot_be_built():
    """Model, release and grid key travel together or not at all.

    A record naming a grid but no release would produce a job record that cannot
    say which release of VERTCON produced the number in it.
    """
    with pytest.raises(ValueError) as caught:
        VerticalTransformation(
            source=NGVD29,
            target=NAVD88,
            model="VERTCON 3.0",
            release=None,
            grid_key="ngvd29.navd88.conus",
            sign=1,
            uncertainty_citation="synthetic",
            caveat="synthetic",
        )

    assert "half-specified" in str(caught.value)


def test_a_record_with_no_caveat_cannot_be_built():
    """Outputs quote these fields; an empty one is a silent disclosure gap."""
    with pytest.raises(ValueError) as caught:
        VerticalTransformation(
            source=NGVD29,
            target=NAVD88,
            model="VERTCON 3.0",
            release="20190601",
            grid_key="ngvd29.navd88.conus",
            sign=1,
            uncertainty_citation="synthetic",
            caveat="   ",
        )

    assert "empty caveat" in str(caught.value)


# --------------------------------------------------------------------------
# The shift application refuses rather than fabricating.
# --------------------------------------------------------------------------


def test_a_missing_grid_value_is_not_a_zero_shift():
    """A point outside the grid must refuse, never pass through.

    Returning the height unchanged would report an unconverted elevation as
    converted - the same silent pass-through ``frames.py`` exists to prevent,
    one level down.
    """
    transformation = require_vertical_pair(NGVD29, NAVD88)

    with pytest.raises(ValueError) as caught:
        apply_shift(200.0, grid_value_m=None, transformation=transformation)

    message = str(caught.value)
    assert "not a zero shift" in message
    assert "ngvd29.navd88.conus" in message


@pytest.mark.parametrize(
    "bad", (float("nan"), float("inf"), float("-inf")), ids=("nan", "inf", "-inf")
)
def test_a_non_finite_grid_value_refuses(bad: float):
    """A NaN would propagate into the Z column as an empty-looking cell."""
    transformation = require_vertical_pair(NGVD29, NAVD88)

    with pytest.raises(ValueError) as caught:
        apply_shift(200.0, grid_value_m=bad, transformation=transformation)

    assert "non-finite grid value" in str(caught.value)


@pytest.mark.parametrize(
    "bad", (float("nan"), float("inf")), ids=("nan", "inf")
)
def test_a_non_finite_height_refuses(bad: float):
    transformation = require_vertical_pair(NGVD29, NAVD88)

    with pytest.raises(ValueError) as caught:
        apply_shift(bad, grid_value_m=-0.1402, transformation=transformation)

    assert "not a finite number" in str(caught.value)


def test_the_height_and_the_grid_value_cannot_be_transposed_by_position():
    """Two bare floats, and swapping them yields a plausible elevation.

    ``apply_shift(-0.1402, 200.0, t)`` would return 199.8598's evil twin and
    nothing would complain, so the grid value and the transformation are
    keyword-only. This states that as a contract rather than a convention.
    """
    transformation = require_vertical_pair(NGVD29, NAVD88)

    with pytest.raises(TypeError):
        apply_shift(200.0, -0.1402, transformation)  # type: ignore[misc]
    with pytest.raises(TypeError):
        signed_shift(-0.1402, transformation)  # type: ignore[misc]


def test_the_result_is_metres_in_metres_out():
    """No unit conversion happens here.

    The grid is published in metres (plan section 2.2) and the core computes in
    metres, exactly as it does for the geoid; feet exist only at the file
    boundary. A shift of -0.1402 m is about -0.46 ft, and a module that quietly
    returned feet would be out by a factor of 3.28 in a column that looks
    ordinary.
    """
    transformation = require_vertical_pair(NGVD29, NAVD88)

    # 0.0 m in, so the result is the shift alone, in whatever unit it is in.
    shifted = apply_shift(0.0, grid_value_m=-0.1402, transformation=transformation)

    assert shifted == -0.1402
    assert math.isclose(shifted / 0.3048, -0.4600, abs_tol=0.0005)  # ft, for scale


# ---------------------------------------------------------------------------
# Review gate, 2026-08-07, finding 1 (MEDIUM). Pinned with the reviewer's own
# counterexample. See docs/DESIGN.md amendment #35.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "impostor, what",
    [
        (frames.NAD83_2011, "a reference frame"),
        (zones.MI_SOUTH, "a zone"),
        (units.INTERNATIONAL_FEET, "a linear unit"),
    ],
)
def test_a_record_that_is_not_a_vertical_datum_is_refused_by_name(impostor, what):
    """Every record in this core carries code, name and citation.

    So ``_canonical`` reads ``.code`` off a Zone, a ReferenceFrame or a
    LinearUnit without complaint, and the call only failed several lines later
    on ``.is_usable`` - as an AttributeError, which is not a refusal, names
    nothing, and walks straight through the ``except VerticalDatumError`` this
    module's docstring tells callers to write.

    This is the pattern DESIGN.md amendment #11 finding 1 recorded against
    ``frames.require_same_frame`` ("a Zone duck-types straight through; both
    carry .code"), whose fix is the isinstance guard at
    ``michspc/spc/convert.py`` in ``project_point``. The guard here is that one.

    The message must name the offending type, per DESIGN.md section 7: a
    refusal that does not say what arrived teaches nothing.
    """
    with pytest.raises(TypeError) as raised:
        require_vertical_pair(impostor, NAVD88)

    message = str(raised.value)
    assert type(impostor).__name__ in message, what
    assert "VerticalDatum" in message
    assert "NGVD29" in message and "NAVD88" in message

    # ... and in the target position too, which is a separate argument.
    with pytest.raises(TypeError):
        require_vertical_pair(NGVD29, impostor)


def test_the_impostor_guard_runs_before_anything_reads_is_usable():
    """The refusal must not depend on the impostor happening to lack a field.

    A record carrying BOTH ``code`` and a truthy ``is_usable`` would otherwise
    sail past the guard the AttributeError was accidentally providing, and be
    resolved by code against the real registry - returning a real
    transformation for an object that is not a vertical datum at all.
    """

    class ForgedDatum:
        code = "NAVD88"
        name = "North American Vertical Datum of 1988"
        citation = "forged"
        is_usable = True

    with pytest.raises(TypeError):
        require_vertical_pair(ForgedDatum(), NAVD88)
