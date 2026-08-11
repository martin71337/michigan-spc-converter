"""Ellipsoid-height input: the anchors, before the feature exists (WP-E1).

GNSS gives an ellipsoid height h; a plat needs an orthometric height H. The
conversion is H = h - N, with N the geoid separation at the point.

**This module is written BEFORE the production code, deliberately** — the
project's method holds that the work in a feature like this is the anchors,
not the arithmetic. The arithmetic is one subtraction; what has to be true is
that the separation it subtracts is NGS's, at the right position, with the
right sign.

Two independent bodies of truth, and they check different things:

1. **Fourteen NGS published Michigan benchmarks**
   (``tests/fixtures/ellipsoid_height_anchors.py``), each carrying an NAVD 88
   orthometric height AND a GEOID18 geoid height on its own datasheet. Their
   sum is NGS's own ellipsoid height at that mark, so feeding h must give
   back H. These exercise the whole path at real published control spread
   over the entire state.

2. **The Houghton geoid anchors**, which the geoid-to-geoid feature already
   pins in the forward direction (DESIGN.md #50). Ellipsoid input is the
   EXACT INVERSE of that arithmetic, and pinning both directions off one
   frozen figure is what stops a sign error from hiding: at Houghton
   N18 = -33.796, so h = 166.204 must give H = 200.000, which is #50's own
   number read the other way.

**The sign is the thing.** In the conterminous United States the ellipsoid
lies above the geoid, so N is negative throughout Michigan (about -33 to -37
m), h is the SMALLER number, and H = h - N makes a height LARGER by about 34
m. A conversion that made a Michigan height smaller has the sign backwards,
and it would be wrong by 68 m — which is why both directions are pinned and
why the falsification for these tests is h + N.
"""

from __future__ import annotations

import pytest

from michspc.fileio import geoid
from tests.fixtures.ellipsoid_height_anchors import (
    BENCHMARK_ANCHORS,
    BENCHMARK_TOLERANCE_M,
)
from tests.fixtures.geoid12b_anchors import GEOID12B_ANCHORS
from tests.fixtures.geoid_anchors import GEOID_ANCHORS

# The Houghton anchor, resolved from the frozen fixtures rather than retyped,
# exactly as tests/test_geoid_swap.py resolves it - so this file and #50's
# cannot drift apart about the same NGS figure.
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

# Two NGS figures printed to 0.001 m carry +/-0.0005 m apiece, and the
# reader's worst measured residual against NGS's own service is sub-millimetre
# (DESIGN.md #37). 0.0015 m is the derived bound, the same one #50 uses.
ANCHOR_TOLERANCE_M = 0.0015


# ==========================================================================
# The published benchmarks: h = H + N, so h - N must return H.
# ==========================================================================


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", BENCHMARK_ANCHORS, ids=lambda a: a.pid)
def test_our_separation_matches_the_published_one_at_every_mark(anchor):
    """The reader against NGS's own published GEOID18 figure at real control.

    This is the load-bearing half: once the separation agrees, the h -> H
    subtraction has nothing left to get wrong but its sign, which the next
    test pins.
    """
    ours = geoid.geoid_height(
        anchor.latitude, anchor.longitude, geoid.default_grid(geoid.GEOID18_MODEL)
    )

    assert ours == pytest.approx(anchor.geoid_height_m, abs=BENCHMARK_TOLERANCE_M)
    # Negative everywhere in Michigan - the ellipsoid is above the geoid.
    assert ours < 0.0


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", BENCHMARK_ANCHORS, ids=lambda a: a.pid)
def test_h_minus_n_returns_the_published_orthometric_height(anchor):
    """The whole conversion, at fourteen published marks across Michigan.

    The published orthometric height's own precision cancels out of this
    comparison — see the fixture module's derivation — so the tolerance is
    purely the separation disagreement.
    """
    ours = geoid.geoid_height(
        anchor.latitude, anchor.longitude, geoid.default_grid(geoid.GEOID18_MODEL)
    )

    recovered = anchor.ellipsoid_height_m - ours

    assert recovered == pytest.approx(
        anchor.orthometric_height_m, abs=BENCHMARK_TOLERANCE_M
    )
    # And it went UP: h is the smaller number in Michigan. This is the
    # assertion that fails loudly on h + N, where the other one could still
    # pass at a mark whose separation happened to be small.
    assert recovered > anchor.ellipsoid_height_m


def test_the_published_marks_span_the_state_and_all_three_zones():
    """An anchor set clustered in one county would prove much less.

    Guards the fixture itself: a future edit that dropped the Upper Peninsula
    marks would leave the suite green while halving what it covers.
    """
    latitudes = [a.latitude for a in BENCHMARK_ANCHORS]
    longitudes = [a.longitude for a in BENCHMARK_ANCHORS]

    assert len(BENCHMARK_ANCHORS) >= 14
    assert min(latitudes) < 42.0 and max(latitudes) > 47.0
    assert min(longitudes) < -88.0 and max(longitudes) > -83.0
    # Every PID distinct - a duplicated mark would inflate the count without
    # adding a position.
    assert len({a.pid for a in BENCHMARK_ANCHORS}) == len(BENCHMARK_ANCHORS)


# ==========================================================================
# The Houghton inverse: #50's own figure, read the other way.
# ==========================================================================


def test_the_houghton_anchor_inverts_the_geoid_swap_pin_under_geoid18():
    """h = 166.204 -> H = 200.000, hand-derived from the frozen figure.

    #50 pins 200.000 m under GEOID12B becoming 199.968 m under GEOID18. This
    is the same anchor from the other side: NGS's printed N18 is -33.796, so
    the ellipsoid height of a 200.000 m NAVD 88 point at Houghton is

        h = H + N = 200.000 + (-33.796) = 166.204

    and converting it back must land on 200.000 exactly.
    """
    assert N18_FIXTURE == -33.796  # the frozen figure this derivation used
    h = 200.000 + N18_FIXTURE
    assert h == pytest.approx(166.204, abs=1e-9)

    ours = geoid.geoid_height(
        HOUGHTON_LATITUDE, HOUGHTON_LONGITUDE, geoid.default_grid(geoid.GEOID18_MODEL)
    )
    recovered = h - ours

    assert recovered == pytest.approx(200.000, abs=ANCHOR_TOLERANCE_M)


def test_the_houghton_anchor_inverts_under_geoid12b_too():
    """The same point under the other model: N12B = -33.828, h = 166.172.

    Both models pinned, because the feature lets the user choose which one
    converts, and a model mix-up moves the height by the 32 mm between them.
    """
    assert N12B_FIXTURE == -33.828
    h = 200.000 + N12B_FIXTURE
    assert h == pytest.approx(166.172, abs=1e-9)

    ours = geoid.geoid_height(
        HOUGHTON_LATITUDE,
        HOUGHTON_LONGITUDE,
        geoid.default_grid(geoid.GEOID12B_MODEL),
    )
    recovered = h - ours

    assert recovered == pytest.approx(200.000, abs=ANCHOR_TOLERANCE_M)


def test_the_two_models_disagree_by_the_amount_50_recorded():
    """32 mm at Houghton — so choosing the wrong model is a real error, and
    the two anchors above are genuinely distinguishing rather than duplicates.
    """
    h = 166.204
    under_18 = h - geoid.geoid_height(
        HOUGHTON_LATITUDE, HOUGHTON_LONGITUDE, geoid.default_grid(geoid.GEOID18_MODEL)
    )
    under_12b = h - geoid.geoid_height(
        HOUGHTON_LATITUDE,
        HOUGHTON_LONGITUDE,
        geoid.default_grid(geoid.GEOID12B_MODEL),
    )

    assert under_18 - under_12b == pytest.approx(
        N12B_FIXTURE - N18_FIXTURE, abs=ANCHOR_TOLERANCE_M
    )
    assert abs(under_18 - under_12b) == pytest.approx(0.032, abs=ANCHOR_TOLERANCE_M)
