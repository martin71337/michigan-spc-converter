"""Re-measure the polynomial agreement band and hold the stored values to it.

`Zone.band_lat_min` / `band_lat_max` decide whether a disagreement between the
two engines is a defect or the polynomial method's known degradation. They are
measured values (docs/DESIGN.md amendment #6), and a stored measurement that is
never re-taken is a stored guess.

These tests re-derive the true band from the code itself and fail if the stored
band has drifted outside it. The stored band must always be a **subset** of the
measured one - conservative in the direction that matters, since claiming a
wider band than reality is what turns expected degradation into a spurious hard
refusal.

Marked slow: the sweep is a few thousand conversions per zone.
"""

from __future__ import annotations

import pytest

from michspc.spc import agreement as ag
from michspc.spc import polynomial as poly
from michspc.spc.convert import _within_fitted_band
from michspc.spc.lambert import constants_for
from michspc.spc.lambert import forward as rigorous_forward
from michspc.spc.zones import ALL_ZONES, MI_CENTRAL, MI_SOUTH

# Step for the latitude sweep. Fine enough to locate each edge to a hundredth of
# a degree, which is well below the rounding applied to the stored values.
_STEP = 0.005


def worst_disagreement_at(zone, latitude: float) -> float:
    """Largest engine separation at this latitude, across the zone's longitudes.

    Swept across longitude rather than taken on the central meridian alone,
    because the polynomial's northing term picks up an ``E' tan(gamma/2)``
    contribution that grows away from the meridian.
    """
    constants = constants_for(zone)
    coefficients = poly.coefficients_for(zone.code)

    worst = 0.0
    for i in range(9):
        longitude = zone.lon_min + (zone.lon_max - zone.lon_min) * i / 8.0
        rigorous = rigorous_forward(latitude, longitude, constants)
        polynomial = poly.forward(latitude, longitude, constants, coefficients)
        worst = max(worst, ag.compare(rigorous, polynomial).distance)
    return worst


def measure_band(zone) -> tuple[float, float]:
    """The latitude range where the engines agree within NGS's 0.5 mm."""
    low = high = None
    latitude = 38.0
    while latitude < 52.0:
        if worst_disagreement_at(zone, latitude) <= ag.AGREEMENT_TOLERANCE_M:
            if low is None:
                low = latitude
            high = latitude
        latitude += _STEP
    return low, high


@pytest.mark.slow
@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_stored_band_lies_inside_the_measured_band(zone):
    """The stored band may never claim more than the measurement supports.

    Measured 2026-08-05, worst case across each zone's full longitude span:

        MI North    44.192 to 48.901   stored 44.25 to 48.85
        MI Central  43.236 to 46.128   stored 43.30 to 46.05
        MI South    41.403 to 44.312   stored 41.45 to 44.25
    """
    measured_low, measured_high = measure_band(zone)

    assert measured_low is not None, f"{zone.abbrev}: found no agreement band at all"
    assert zone.band_lat_min >= measured_low, (
        f"{zone.abbrev}: stored band starts at {zone.band_lat_min}, below the "
        f"measured {measured_low:.3f} - it claims agreement where there is none"
    )
    assert zone.band_lat_max <= measured_high, (
        f"{zone.abbrev}: stored band ends at {zone.band_lat_max}, above the "
        f"measured {measured_high:.3f} - it claims agreement where there is none"
    )


@pytest.mark.slow
@pytest.mark.parametrize("zone", ALL_ZONES, ids=lambda z: z.abbrev)
def test_the_engines_really_do_agree_everywhere_in_the_stored_band(zone):
    """The property the stored band exists to guarantee.

    If this holds, then an in-band disagreement genuinely means one engine is
    wrong, and refusing there is correct.
    """
    latitude = zone.band_lat_min
    worst = 0.0
    while latitude <= zone.band_lat_max:
        worst = max(worst, worst_disagreement_at(zone, latitude))
        latitude += _STEP

    assert worst <= ag.AGREEMENT_TOLERANCE_M, (
        f"{zone.abbrev}: engines disagree by {worst * 1000:.4f} mm inside the "
        f"stored band, which would make an in-band refusal a false alarm"
    )


def test_the_band_is_not_the_same_thing_as_the_zone_extent():
    """The defect this whole mechanism was introduced to fix.

    Michigan South covers up to 44.3 N but its polynomials only hold to
    44.312 N; Michigan Central covers to 46.0 N against a band ending at
    46.128 N. Using the geographic extent as the enforcement band - with the
    outward slack the first implementation applied - pushed the enforced range
    past where the polynomial is valid and turned expected degradation into a
    hard refusal. The two must stay distinct.
    """
    assert MI_SOUTH.band_lat_max < MI_SOUTH.lat_max + 0.1
    assert MI_CENTRAL.band_lat_max < MI_CENTRAL.lat_max + 0.15

    # And the band must never be derived from the extent by a fixed offset.
    offsets = {
        round(zone.band_lat_max - zone.lat_max, 3) for zone in ALL_ZONES
    }
    assert len(offsets) > 1, (
        "every zone's band sits at the same offset from its extent, which "
        "suggests it was computed from the extent rather than measured"
    )


def test_within_fitted_band_uses_the_band_and_not_the_extent():
    """Direct check on the predicate itself."""
    # Inside the extent but outside the band: 44.28 N in Michigan South.
    assert MI_SOUTH.lat_min <= 44.28 <= MI_SOUTH.lat_max
    assert not _within_fitted_band(MI_SOUTH, 44.28)

    # Outside the extent but inside the band: 41.5 N in Michigan Central's
    # neighbour to the south is not relevant; use Michigan North, whose band
    # reaches 44.25 while its extent starts at 45.0.
    from michspc.spc.zones import MI_NORTH

    assert 44.5 < MI_NORTH.lat_min
    assert _within_fitted_band(MI_NORTH, 44.5)

    # And the ordinary case.
    assert _within_fitted_band(MI_SOUTH, 42.7)
