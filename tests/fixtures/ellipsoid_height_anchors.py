"""NGS published Michigan benchmarks carrying BOTH heights. Frozen anchors.

Every value below was captured verbatim from the National Geodetic Survey's
own benchmark service:

    https://geodesy.noaa.gov/api/nde/radial?lat=<lat>&lon=<lon>&radius=6&type=BM

Captured 2026-08-11. The raw JSON and the capture harness are committed at
``review/wp-e1-ellipsoid/``. **No test touches the network.**

Every mark here is a published NGS control point whose datasheet states an
**NAVD 88 orthometric height** and a **GEOID18 geoid height** for the same
position. That pairing is what makes them useful to the ellipsoid-height
feature: NGS's own ellipsoid height at the mark is

    h = H + N

so a program told ``h`` must give back ``H``.

**What these anchors do and do not prove.** They are NOT an independent
derivation of the geoid — NGS computed the published N from GEOID18, the same
model this program reads, so the two cannot disagree about the model itself.
What they exercise is the whole path at REAL PUBLISHED CONTROL rather than at
arbitrary sampled positions: the reader's interpolation at fourteen marks
spread over the entire state, in every zone, and the h -> H arithmetic on top
of it. The independent check of the geoid model is elsewhere in the suite —
``geoid_anchors.py`` and ``geoid_discriminating_anchors.py``, captured from
NGS's geoid service at off-node positions chosen to test interpolation.

**Why the tolerance is what it is, derived not chosen.** The input height is
built from the two published figures, so

    H_returned = h - N_ours = (H_pub + N_pub) - N_ours
               = H_pub + (N_pub - N_ours)

The published orthometric height's own precision cancels exactly, and the only
error left is the separation disagreement. Measured at capture time over all
fourteen marks, the worst was **0.75 mm** — and NGS prints N to 0.001 m, which
carries +/-0.0005 m of quantization on its own before the reader's sub-
millimetre residual (DESIGN.md #37) is counted. 0.0015 m is that bound.

Note the sign on every separation: negative, between about -33 and -37 m. In
the conterminous United States the ellipsoid lies ABOVE the geoid, so an
ellipsoid height is the SMALLER number and ``H = h - N`` makes a height
larger. A conversion that made a Michigan height smaller has the sign wrong.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkAnchor:
    """One NGS published mark, both heights, verbatim from the datasheet."""

    pid: str
    """NGS Permanent Identifier — the mark is retrievable and checkable."""

    region: str
    """Where in Michigan, for readability when a failure names one."""

    latitude: float
    longitude: float
    """Decimal degrees, negative west, as NGS publishes them."""

    orthometric_height_m: float
    """NAVD 88 ORTHO HEIGHT, metres."""

    geoid_height_m: float
    """GEOID18 GEOID HEIGHT, metres. Negative throughout Michigan."""

    @property
    def ellipsoid_height_m(self) -> float:
        """h = H + N — NGS's own pairing, and the INPUT a test supplies.

        Derived rather than stored: storing it would be a third figure that
        could drift out of step with the two it comes from, and this project
        does not store a derived value beside its ingredients.
        """
        return self.orthometric_height_m + self.geoid_height_m


BENCHMARK_ANCHORS: tuple[BenchmarkAnchor, ...] = (
    BenchmarkAnchor(
        pid="DI0214",
        region="Monroe / Lake Erie",
        latitude=41.9248747556,
        longitude=-83.4648434083,
        orthometric_height_m=193.786,
        geoid_height_m=-35.182,
    ),
    BenchmarkAnchor(
        pid="AA8055",
        region="Detroit",
        latitude=42.2973057056,
        longitude=-83.0943504917,
        orthometric_height_m=176.834,
        geoid_height_m=-34.556,
    ),
    BenchmarkAnchor(
        pid="AH7856",
        region="Lansing",
        latitude=42.6639722222,
        longitude=-84.5236138889,
        orthometric_height_m=274.408,
        geoid_height_m=-33.756,
    ),
    BenchmarkAnchor(
        pid="AB3074",
        region="Port Huron",
        latitude=42.9281408611,
        longitude=-82.4604858472,
        orthometric_height_m=182.545,
        geoid_height_m=-34.929,
    ),
    BenchmarkAnchor(
        pid="AJ5555",
        region="Grand Rapids",
        latitude=42.9887965778,
        longitude=-85.6743359056,
        orthometric_height_m=190.622,
        geoid_height_m=-33.607,
    ),
    BenchmarkAnchor(
        pid="AA2864",
        region="Muskegon",
        latitude=43.1541666667,
        longitude=-86.2155555556,
        orthometric_height_m=191.192,
        geoid_height_m=-33.734,
    ),
    BenchmarkAnchor(
        pid="AJ5551",
        region="Saginaw",
        latitude=43.4462216111,
        longitude=-83.8917247639,
        orthometric_height_m=184.317,
        geoid_height_m=-34.358,
    ),
    BenchmarkAnchor(
        pid="AC8294",
        region="Ludington",
        latitude=43.9505555556,
        longitude=-86.4422500000,
        orthometric_height_m=182.624,
        geoid_height_m=-35.411,
    ),
    BenchmarkAnchor(
        pid="DL6865",
        region="Traverse City",
        latitude=44.7440616167,
        longitude=-85.6077387417,
        orthometric_height_m=190.295,
        geoid_height_m=-34.591,
    ),
    BenchmarkAnchor(
        pid="DI1688",
        region="Alpena",
        latitude=45.0629800944,
        longitude=-83.4285741722,
        orthometric_height_m=182.255,
        geoid_height_m=-36.542,
    ),
    BenchmarkAnchor(
        pid="AC6039",
        region="Mackinaw City",
        latitude=45.7773166667,
        longitude=-84.7209111111,
        orthometric_height_m=179.108,
        geoid_height_m=-35.417,
    ),
    BenchmarkAnchor(
        pid="AC6345",
        region="Sault Ste. Marie",
        latitude=46.5013222222,
        longitude=-84.3725416667,
        orthometric_height_m=184.339,
        geoid_height_m=-36.616,
    ),
    BenchmarkAnchor(
        pid="AH7272",
        region="Marquette",
        latitude=46.5465796028,
        longitude=-87.3786514306,
        orthometric_height_m=187.936,
        geoid_height_m=-34.806,
    ),
    BenchmarkAnchor(
        pid="AB7623",
        region="Houghton",
        latitude=47.1364724917,
        longitude=-88.6201987778,
        orthometric_height_m=195.395,
        geoid_height_m=-33.514,
    ),
)


BENCHMARK_TOLERANCE_M = 0.0015
"""The derived bound, not a chosen one — see the module docstring.

Worst measured residual at capture time was 0.75 mm; NGS's own printing of the
separation carries +/-0.0005 m before the reader's sub-millimetre residual is
counted.
"""
