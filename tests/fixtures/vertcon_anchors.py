"""NGS NCAT vertical transformations, captured once and frozen. Verification anchors.

Every value below was computed by the National Geodetic Survey's own Coordinate
Conversion and Transformation Tool (NCAT) and captured verbatim from its API:

    https://geodesy.noaa.gov/api/ncat/llh
        ?lat=<lat>&lon=<lon>&orthoHt=200.000
        &inDatum=NAD83(2011)&outDatum=NAD83(2011)
        &inVertDatum=<source>&outVertDatum=<target>

Captured 2026-08-07. Every response reported ``"vertconVersion": "3.0"``, which
is what says these anchors describe VERTCON **3.0** and not the superseded 2.0
that both /PC_PROD/VERTCON/ and VDatum lead to (docs/PLAN-vertical-datums.md
section 2.6). **No test touches the network** - that is the point of freezing
them.

The horizontal datums are set to the same realization deliberately, so NCAT
performs no horizontal transformation at all and the only thing that moves is
the height. What these anchors test is the VERTCON grid reader, its sign and its
uncertainty grid, and nothing else.

**The source height is 200.000 m at every point**, which is what makes these
transcribable: the shift is ``target_height_m - 200.000`` and can be read
straight off the two printed numbers by hand.

Precision NCAT prints, which sets the tolerance any value here can be held to:

    orthometric height   0.001 m
    sigma                0.001 m

So a single printed figure carries +/-0.0005 m of quantization on its own, and a
shift derived from two of them carries +/-0.001 m. A tolerance tighter than that
is measuring NCAT's rounding, not this program's arithmetic.

**What these anchors prove, stated plainly because the job record has to say it
too** (docs/PLAN-vertical-datums.md section 5.2): they prove MCX reads NGS's
grid the way NGS reads it. NCAT is another implementation of the same model, not
an independent measurement of the ground. Every other quantity in this program
is checked against an external truth; this one cannot be.

Provenance note, recorded rather than glossed
---------------------------------------------
The V0 gate ran an earlier 20-point lattice whose *script and coordinates* were
left in a session scratchpad and lost (plan section 2). This lattice was
re-captured from scratch on 2026-08-07 and is **not** that one. It was seeded
with every position the plan does record, so the recreation could be checked
against V0 rather than merely replacing it, and all six reproduce:

    the 43.0 N / 84.5 W anchor of DESIGN.md #22 and plan section 2.3
        200.000 NGVD29 -> 199.860 NAVD88, a -0.140 m shift.
    the five-point inverse set of plan section 2.4
        every forward and inverse shift matches the recorded table to the last
        printed digit, and every pair sums to 0.000 m.
    the largest-sigma point of plan section 2.8, 43.05 N / 86.20 W
        sigma 0.366 m, against a shift of -0.144 m - the uncertainty is larger
        than the shift, which is the disclosure fact that decided section 5.

**Two figures are NOT reproduced, and must not be cited as though they were.**
Plan section 2.5 names a Kalamazoo sigma of 0.0040 m and a Lansing sigma of
0.0070 m; this lattice gets 0.020 m and 0.008 m at the positions below. Those
are city-centre coordinates chosen here, and V0 did not record which
coordinates it used, so these are different points rather than a disagreement.
The interpolation asymmetry that section 2.5 established is therefore
**re-measured against this lattice in WP-V4**, where the reader exists, rather
than inherited from a figure whose position is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VertconAnchor:
    """One NCAT vertical transformation, verbatim."""

    name: str
    """Stable handle, so a failing test names the point rather than an index."""

    latitude: float
    longitude: float
    """Decimal degrees, negative west - the convention NCAT uses and we use."""

    source_datum: str
    target_datum: str
    """As NCAT spells them: NGVD29, NAVD88.

    Worth having in the fixture rather than implied by the tuple a record sits
    in: these are the exact tokens ``spc/vertical.py`` carries as
    ``VerticalDatum.code``, and that module's docstring asks for them to be
    confirmed against NCAT when this lattice is frozen. They are confirmed:
    every capture echoed ``srcVertDatum`` and ``destVertDatum`` back in these
    spellings.
    """

    source_height_m: float
    """200.000 at every anchor. Kept per-record rather than as a module
    constant so a record stays readable on its own and so a future capture at a
    different height does not silently inherit this one's."""

    target_height_m: float
    """What NCAT returned, to the 0.001 m it prints."""

    sigma_m: float
    """NCAT's ``sigOrthoht`` - the one-sigma uncertainty of the modeled shift,
    from the companion .err grid. Printed to 0.001 m."""

    note: str

    @property
    def shift_m(self) -> float:
        """The shift NCAT applied, in metres.

        Derived, never stored: storing it beside the two heights it comes from
        would be a second representation of one fact, and the two could drift.
        Carries +/-0.001 m of NCAT's printed quantization, being a difference of
        two figures printed to 0.001 m.
        """
        return self.target_height_m - self.source_height_m


# Precision NCAT prints each quantity to. Any tolerance in a test that consumes
# these anchors is built from these numbers, not chosen to pass.
NCAT_PRINTED = {
    "orthometric_height_m": 0.001,
    "sigma_m": 0.001,
}

SOURCE_HEIGHT_M = 200.000
"""The height every anchor was requested at. See ``VertconAnchor.source_height_m``."""


# ---------------------------------------------------------------------------
# NGVD 29 -> NAVD 88, 20 points.
#
# Spread across both peninsulas and all three Michigan zones. The first six are
# positions the plan itself records; the remaining fourteen sit deliberately off
# the grid's 0.05-degree nodes, so what they exercise is the interpolation
# scheme rather than a raw table lookup.
#
# Read the sign: the shift is NEGATIVE almost everywhere in Michigan - an NGVD 29
# height is LARGER than the same point's NAVD 88 height - but it changes sign in
# the eastern Upper Peninsula (sault, +0.040) and at Marquette (+0.034). That is
# why the difference is not a bias that could be subtracted out, and why a
# reader that got the sign backwards would still look plausible at most points.
# ---------------------------------------------------------------------------

NGVD29_TO_NAVD88_ANCHORS: tuple[VertconAnchor, ...] = (
    # 200.000 -> 199.860 is a -0.140 m shift: DESIGN.md #22's anchor, and the
    # single value that fixes sign = +1 in spc/vertical.py.
    VertconAnchor(name='anchor-22', latitude=43.0, longitude=-84.5, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.86, sigma_m=0.001, note='DESIGN.md #22 anchor; plan 2.3'),
    VertconAnchor(name='inverse-detroit', latitude=42.33, longitude=-83.05, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.829, sigma_m=0.003, note='plan 2.4 inverse set'),
    VertconAnchor(name='inverse-straits', latitude=45.87, longitude=-84.73, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.923, sigma_m=0.047, note='plan 2.4 inverse set'),
    VertconAnchor(name='inverse-marquette', latitude=46.54, longitude=-87.4, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=200.034, sigma_m=0.01, note='plan 2.4 inverse set'),
    VertconAnchor(name='inverse-traverse', latitude=44.76, longitude=-85.62, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.884, sigma_m=0.003, note='plan 2.4 inverse set'),
    # The disclosure point of plan section 2.8: sigma 0.366 m against a shift of
    # -0.144 m. The uncertainty is larger than the shift itself. This is the
    # anchor that settled section 5 - per-point sigma, not a job-level constant.
    VertconAnchor(name='max-sigma', latitude=43.05, longitude=-86.2, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.856, sigma_m=0.366, note='plan 2.8 largest Michigan sigma'),
    # The largest shift in the lattice: -0.396 m at Monroe, on the Ohio line.
    VertconAnchor(name='monroe', latitude=41.7583, longitude=-83.6417, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.604, sigma_m=0.031, note='South zone'),
    VertconAnchor(name='kalamazoo', latitude=42.2637, longitude=-85.5878, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.868, sigma_m=0.02, note='South zone; NOT plan 2.5s Kalamazoo position - see the module docstring'),
    VertconAnchor(name='lansing', latitude=42.7326, longitude=-84.5556, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.865, sigma_m=0.008, note='South zone; NOT plan 2.5s Lansing position - see the module docstring'),
    VertconAnchor(name='grand-rapids', latitude=42.9634, longitude=-85.6681, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.863, sigma_m=0.007, note='South zone'),
    VertconAnchor(name='flint', latitude=43.0125, longitude=-83.6875, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.847, sigma_m=0.01, note='South zone'),
    VertconAnchor(name='new-buffalo', latitude=41.6961, longitude=-86.8203, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.888, sigma_m=0.009, note='South zone, SW corner of the state'),
    VertconAnchor(name='saginaw', latitude=43.4194, longitude=-83.9508, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.84, sigma_m=0.02, note='Central zone'),
    VertconAnchor(name='houghton-lake', latitude=44.2542, longitude=-84.2247, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.867, sigma_m=0.004, note='Central zone'),
    VertconAnchor(name='ludington', latitude=43.9878, longitude=-86.2419, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.931, sigma_m=0.024, note='Central zone, Lake Michigan shore'),
    VertconAnchor(name='gaylord', latitude=45.0217, longitude=-84.6753, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.886, sigma_m=0.037, note='Central zone'),
    VertconAnchor(name='alpena', latitude=45.0561, longitude=-83.4322, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.841, sigma_m=0.006, note='Central zone, Lake Huron shore'),
    VertconAnchor(name='iron-river', latitude=46.0919, longitude=-88.6414, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.999, sigma_m=0.002, note='North zone, western UP'),
    # Positive shift: NAVD 88 is HIGHER than NGVD 29 here. See the sign note above.
    VertconAnchor(name='sault', latitude=46.4936, longitude=-84.3453, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=200.04, sigma_m=0.025, note='North zone, eastern UP'),
    VertconAnchor(name='houghton', latitude=47.1211, longitude=-88.5694, source_datum='NGVD29', target_datum='NAVD88', source_height_m=200.0, target_height_m=199.99, sigma_m=0.002, note='North zone, Keweenaw'),
)


# ---------------------------------------------------------------------------
# NAVD 88 -> NGVD 29, the same five points plan section 2.4 ran both ways.
#
# What these prove is that the inverse is ONE GRID, SIGN REVERSED, and not a
# second published product: at every point the forward and inverse shifts are
# equal and opposite to the last printed digit, so they sum to exactly 0.000 m.
# ``test_...round_trip`` is what holds that, and it is why spc/vertical.py can
# carry the reverse record as the same grid_key at sign = -1.
# ---------------------------------------------------------------------------

NAVD88_TO_NGVD29_ANCHORS: tuple[VertconAnchor, ...] = (
    VertconAnchor(name='inverse-detroit', latitude=42.33, longitude=-83.05, source_datum='NAVD88', target_datum='NGVD29', source_height_m=200.0, target_height_m=200.171, sigma_m=0.003, note='plan 2.4 inverse set'),
    VertconAnchor(name='inverse-straits', latitude=45.87, longitude=-84.73, source_datum='NAVD88', target_datum='NGVD29', source_height_m=200.0, target_height_m=200.077, sigma_m=0.047, note='plan 2.4 inverse set'),
    VertconAnchor(name='inverse-marquette', latitude=46.54, longitude=-87.4, source_datum='NAVD88', target_datum='NGVD29', source_height_m=200.0, target_height_m=199.966, sigma_m=0.01, note='plan 2.4 inverse set'),
    VertconAnchor(name='inverse-traverse', latitude=44.76, longitude=-85.62, source_datum='NAVD88', target_datum='NGVD29', source_height_m=200.0, target_height_m=200.116, sigma_m=0.003, note='plan 2.4 inverse set'),
    VertconAnchor(name='anchor-22', latitude=43.0, longitude=-84.5, source_datum='NAVD88', target_datum='NGVD29', source_height_m=200.0, target_height_m=200.14, sigma_m=0.001, note='plan 2.4 inverse set'),
)


ALL_VERTCON_ANCHORS: tuple[VertconAnchor, ...] = (
    NGVD29_TO_NAVD88_ANCHORS + NAVD88_TO_NGVD29_ANCHORS
)
