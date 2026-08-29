"""SPCS2022 Michigan: NGS's published zone parameters, and beta NCAT's own
projection results, captured once and frozen. Verification anchors.

**NGS BETA. Capture date 2026-08-28.** Everything in this module came from
pre-release NGS products and MUST be re-frozen against NGS's official release;
see "What these anchors do NOT prove" at the bottom of this docstring, and
review/nsrs-h1-anchors/CAPTURE.md, which is the full capture record.

Two independent kinds of fact live here, and they are not interchangeable:

1. ``SPCS2022_ZONE_PARAMETERS`` - the nineteen Michigan zones' DEFINING
   constants, transcribed from NGS's own ``zoneDefinitions.json``
   (632,927 bytes, SHA-256
   ``f222dac669503c8e25eb41d477bbb129b813b894b43e7d012effb9dc00bbc06a``,
   Last-Modified 2026-06-01), by way of the nineteen Michigan rows extracted
   verbatim to ``review/nsrs-n0/raw/spcs/michigan_zones.json`` (SHA-256
   ``8db63d1fe83ebc74700f0d2040da12a18c08a55c0dbafbec8aafe738e6142edb``) and
   tabulated in ``review/nsrs-n0/FINDINGS.md`` section 6. NGS states on that
   page: "All parameters are exact values."

2. ``SPCS2022_PROJECTION_ANCHORS`` - 63 results beta NCAT computed, captured by
   driving its own form (there is no REST surface that accepts any NATRF2022
   token). Harness: ``review/nsrs-h1-anchors/capture_h1_anchors.py``; per-request
   manifest with a SHA-256 per saved response:
   ``review/nsrs-h1-anchors/raw/manifest.json``; machine-readable summary:
   ``review/nsrs-h1-anchors/anchors.json`` (SHA-256
   ``76d2b61e57d2b9ddeb5466bcc3add92907f687efe8221cd0914c595707390a2d``), which
   is the file these values were transcribed from. Each anchor names the saved
   response it came from in its ``capture`` field.

Input datum and output datum were both ``NATRF2022 epoch 2020.00`` on every one
of the 63, so no frame transformation stands between the geodetic position and
the grid coordinate: these anchor the PROJECTION mathematics and nothing else.
The fifteen frame-transformation anchors in the same capture are deliberately
NOT here - they belong to H3, they are a different kind of claim, and mixing
them into a projection fixture would let a projection test pass on a frame
number.

**No test touches the network** - that is the point of freezing them.

The lattice is deliberately ASYMMETRIC about the statewide zone's centre
(review/nsrs-h1-anchors/CAPTURE.md section A), because a symmetric lattice
cannot discriminate the Hotine variant or the sign of the -26 degree skew, and
those are exactly the conventions this project's defect history says get
inherited wrong. Each of the eighteen low-distortion zones contributes its
origin plus a point at origin +(0.15, 0.25) degrees and one at -(0.15, 0.25):
the two are NOT symmetric in the projected plane, and the anchors capture that
- about 261003 the two northings sum to +61.086 m rather than to zero, and the
two scale factors differ in the ninth decimal. An engine that averaged the
asymmetry away would fail here.

Values are as beta NCAT printed them, with two documented transformations:

* the unit token is split off into the field name, so ``"251022.875 m"`` becomes
  ``northing_m=251022.875``; and
* the degree, prime and double-prime glyphs are dropped from the convergence
  string, so ``"+01 deg 54' 40.49\""`` is stored as ``"+01 54 40.49"``. The
  digits, their order and the sign character are untouched. This matches the
  form tests/fixtures/ncat_anchors.py already stores convergence in, and keeps
  every source file in this repository ASCII.

``usft`` is ``N/A`` on all 63 - NGS publishes the 2022 false origins in metres
and international feet only - so there is no US-survey-foot column here. Every
``Combined factor`` is ``N/A`` and every ``Distortion`` is ``+N/A ppm``, because
no height was supplied.

Precision beta NCAT prints, which is what sets the tolerance a value can be held
to; the derivation is written out in SPCS2022_PRINTED below.

**What these anchors do NOT prove.** Read this before using any number here to
accept or reject a computation. The full list is in
review/nsrs-h1-anchors/CAPTURE.md; the load-bearing items are:

1. They are BETA NCAT's implementation on 2026-08-28, not ground truth. NGS's
   beta REST API is known to fail open (``200 OK`` carrying ``N/A``), and a beta
   service is entitled to be wrong. The difference against NGS's official
   release must be MEASURED at re-freeze, never assumed to be zero.
2. The nineteen origin and centre points are the strongest evidence in the set,
   and they are a different claim from the rest: at those points beta NCAT
   reproduces NGS's separately published false origins and origin scale factors
   exactly, so two independent NGS artifacts agree. The off-origin points rest
   on beta NCAT alone.
3. There is no second opinion available. No production NGS service speaks
   SPCS2022, so nothing here was cross-checked against an independent source the
   way the SPCS 83 anchors were.
4. Four zone origins (261002 Detroit at 40 deg 12' N, and 261014/261015/261016)
   lie outside Michigan, over Ohio, Lake Michigan or Wisconsin. They are grid
   origins, not places, and are not field-checkable.
5. Nothing vertical was captured, and the frozen digests pin the saved bytes
   only - beta NCAT embeds a fresh session token in every page, so re-fetching
   does not reproduce them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Spcs2022ZoneParameters:
    """One Michigan SPCS2022 zone's published defining constants.

    Field names here are this program's, not NGS's; NGS's own column names are
    ``Zone code``, ``Zone abrv``, ``Zone name``, ``Proj type``,
    ``Origin latitude``, ``Origin longitude west``, ``Projection origin scale``,
    ``Skew azimuth (deg)``, ``False northing (m)``, ``False easting (m)``,
    ``False northing (ift)`` and ``False easting (ift)``, and every value in
    that file is a string carrying thousands separators and degree symbols.
    """

    code: str
    abbrev: str
    """NGS writes this with an underscore (``MI_L45G``) in the JSON and with a
    space (``MI L45G``) in NCAT. Both are sanctioned; neither is canonical. The
    JSON's spelling is what is stored."""

    name: str
    projection_type: str
    """NGS's abbreviation: ``OMC`` (Hotine oblique Mercator, center), ``LC1``
    (Lambert conformal conic, one parallel) or ``TM`` (transverse Mercator)."""

    origin_latitude: float
    """Decimal degrees north. NGS prints DMS; the conversion is in a comment
    beside each value."""

    origin_longitude: float
    """Decimal degrees, NEGATIVE WEST. NGS prints it twice, positive-west and
    east-of-Greenwich, and the two agree; the west one is transcribed and
    negated."""

    origin_scale: float
    skew_azimuth: float | None
    """Decimal degrees. Published for the statewide oblique Mercator only; the
    column is empty for all eighteen low-distortion zones, and is None here."""

    false_northing_m: float
    false_easting_m: float
    false_northing_ift: float
    false_easting_ift: float
    """NGS publishes no US-survey-foot false origin for any 2022 zone."""


@dataclass(frozen=True)
class Spcs2022Anchor:
    """One beta NCAT projection result, verbatim."""

    zone_code: str
    label: str
    """The capture harness's own name for the point - ``origin``,
    ``origin +0.15/+0.25``, or a place name on the statewide lattice."""

    latitude: float
    longitude: float
    """Decimal degrees, negative west - the convention beta NCAT echoed back and
    the one this program uses."""

    northing_m: float
    easting_m: float
    northing_ift: float
    easting_ift: float
    scale_factor: float
    convergence_dms: str
    """Sign, degrees, minutes, seconds, as printed. Beta NCAT prints a SIGNED
    ZERO at the statewide centre (``-00 00 00.00``), so the sign character is
    not meaningful at zero; and its formatter does not normalise seconds past
    60 (an out-of-domain probe printed ``-18 35 553.55``). Neither affects any
    anchor here, and both are recorded so a parser is not written assuming
    otherwise."""

    capture: str
    """The saved response this row was read from, under
    review/nsrs-h1-anchors/."""


SPCS2022_PRINTED = {
    # Beta NCAT prints linear values to 0.001, in metres and in international
    # feet alike. A figure printed to three decimals carries +/-0.0005 of
    # quantization on its own, so that is the tightest a printed figure can be
    # held to and it is what these anchors are held to. (The SPCS 83 anchors in
    # ncat_anchors.py allow 0.001 m, a little headroom above the same floor;
    # this is the stricter choice, and the measured worst case across all 63
    # anchors is 4.994e-4 m - inside the floor, which is what agreement to
    # better than the printed precision looks like.)
    "linear_m": 0.0005,
    "linear_ift": 0.0005,
    # Convergence is printed to 0.01 arc second; half a unit there is 0.005.
    "convergence_arcsec": 0.005,
    # The grid scale factor is printed to nine decimal places, so the
    # quantization interval is 1e-9 and a printed figure can be held to HALF of
    # that - 5e-10 - and no looser. An earlier draft allowed a full 1e-9, which
    # is twice the limit the printed precision supports: the interim H1+H2 gate
    # showed that at that tolerance an engine result of 0.99985823075 passes
    # against NGS's printed 0.999858230 even though it prints as 0.999858231,
    # i.e. a value that DISAGREES with NGS at NGS's own precision. Tightened to
    # the half-quantum bound.
    #
    # Measured worst across all 63 anchors: 4.9673e-10, at zone 261006's
    # +0.15/+0.25 point - inside the bound by 0.65%, which is close and is
    # EXPECTED to be close rather than lucky. NGS's printed 1.000034419 is the
    # rounding of a true value near ...4185, and this engine computes
    # 1.000034418503; a value sitting almost exactly on a rounding boundary
    # necessarily shows a deviation approaching half a quantum, and cannot
    # exceed it while still printing the same string. Four of the 63 sit above
    # 4.9e-10 for that reason, none above 5e-10, and all 63 print IDENTICALLY
    # to NGS at nine decimals - which is the statement this tolerance exists to
    # make.
    "scale_factor": 5e-10,
}
"""Tolerances, each derived from the precision beta NCAT printed - never chosen
to make a test pass. A printed figure cannot be held to more than half a unit in
its last place, and holding it to less would let a real error hide."""


def dms_to_degrees(text: str) -> float:
    """Parse a printed convergence string into decimal degrees.

    ``"+01 54 40.49"`` -> 1 + 54/60 + 40.49/3600 = 1.911247222...

    Sixty-three anchors carry one of these, so they are parsed rather than
    transcribed a second time as decimals; the parser is pinned in
    tests/test_projection_engines.py against hand-derived values covering a
    positive angle, a negative one, and beta NCAT's signed zero, and against
    the failure that motivates the explicit sign handling: ``float("-00")`` is
    ``-0.0``, but ``-0.0 + 22/60`` is POSITIVE, so a parser that folds the sign
    into the degrees term alone gets every negative angle with zero degrees
    wrong - which is four of the anchors here.
    """
    parts = text.split()
    if len(parts) != 3:
        raise ValueError(
            f"{text!r} is not a printed degrees/minutes/seconds triple; "
            f"expected three whitespace-separated fields, got {len(parts)}."
        )
    sign = -1.0 if parts[0].lstrip().startswith("-") else 1.0
    degrees = abs(float(parts[0]))
    minutes = float(parts[1])
    seconds = float(parts[2])
    return sign * (degrees + minutes / 60.0 + seconds / 3600.0)


SPCS2022_ZONE_PARAMETERS: tuple[Spcs2022ZoneParameters, ...] = (
    Spcs2022ZoneParameters(
        code='260001',
        abbrev='MI',
        name='Michigan',
        projection_type='OMC',
        # 45 deg 00' N: 45 + 0/60 = 45.0
        origin_latitude=45.0,
        # 86 deg 00' W: -(86 + 0/60) = -86.0
        origin_longitude=-86.0,
        origin_scale=0.999800,
        skew_azimuth=-26.0,
        false_northing_m=762000.0,
        false_easting_m=1524000.0,
        false_northing_ift=2500000.0,
        false_easting_ift=5000000.0,
    ),
    Spcs2022ZoneParameters(
        code='261001',
        abbrev='MI_L11A',
        name='Michigan Ann Arbor',
        projection_type='TM',
        # 41 deg 18' N: 41 + 18/60 = 41.3
        origin_latitude=41.3,
        # 84 deg 06' W: -(84 + 6/60) = -84.1
        origin_longitude=-84.1,
        origin_scale=1.000022,
        skew_azimuth=None,
        false_northing_m=0.0,
        false_easting_m=381000.0,
        false_northing_ift=0.0,
        false_easting_ift=1250000.0,
    ),
    Spcs2022ZoneParameters(
        code='261002',
        abbrev='MI_L15D',
        name='Michigan Detroit',
        projection_type='TM',
        # 40 deg 12' N: 40 + 12/60 = 40.2
        origin_latitude=40.2,
        # 83 deg 09' W: -(83 + 9/60) = -83.15
        origin_longitude=-83.15,
        origin_scale=1.000024,
        skew_azimuth=None,
        false_northing_m=0.0,
        false_easting_m=495300.0,
        false_northing_ift=0.0,
        false_easting_ift=1625000.0,
    ),
    Spcs2022ZoneParameters(
        code='261003',
        abbrev='MI_L21F',
        name='Michigan Flint',
        projection_type='LC1',
        # 42 deg 54' N: 42 + 54/60 = 42.9
        origin_latitude=42.9,
        # 83 deg 24' W: -(83 + 24/60) = -83.4
        origin_longitude=-83.4,
        origin_scale=1.000026,
        skew_azimuth=None,
        false_northing_m=76200.0,
        false_easting_m=685800.0,
        false_northing_ift=250000.0,
        false_easting_ift=2250000.0,
    ),
    Spcs2022ZoneParameters(
        code='261004',
        abbrev='MI_L25S',
        name='Michigan Saginaw',
        projection_type='LC1',
        # 43 deg 36' N: 43 + 36/60 = 43.6
        origin_latitude=43.6,
        # 83 deg 39' W: -(83 + 39/60) = -83.65
        origin_longitude=-83.65,
        origin_scale=1.000012,
        skew_azimuth=None,
        false_northing_m=228600.0,
        false_easting_m=723900.0,
        false_northing_ift=750000.0,
        false_easting_ift=2375000.0,
    ),
    Spcs2022ZoneParameters(
        code='261005',
        abbrev='MI_L31R',
        name='Michigan Roscommon',
        projection_type='LC1',
        # 44 deg 15' N: 44 + 15/60 = 44.25
        origin_latitude=44.25,
        # 84 deg 09' W: -(84 + 9/60) = -84.15
        origin_longitude=-84.15,
        origin_scale=1.000029,
        skew_azimuth=None,
        false_northing_m=76200.0,
        false_easting_m=990600.0,
        false_northing_ift=250000.0,
        false_easting_ift=3250000.0,
    ),
    Spcs2022ZoneParameters(
        code='261006',
        abbrev='MI_L35T',
        name='Michigan Thunder Bay',
        projection_type='LC1',
        # 44 deg 51' N: 44 + 51/60 = 44.85
        origin_latitude=44.85,
        # 84 deg 03' W: -(84 + 3/60) = -84.05
        origin_longitude=-84.05,
        origin_scale=1.000031,
        skew_azimuth=None,
        false_northing_m=190500.0,
        false_easting_m=1028700.0,
        false_northing_ift=625000.0,
        false_easting_ift=3375000.0,
    ),
    Spcs2022ZoneParameters(
        code='261007',
        abbrev='MI_L41Z',
        name='Michigan Kalamazoo',
        projection_type='LC1',
        # 42 deg 06' N: 42 + 6/60 = 42.1
        origin_latitude=42.1,
        # 85 deg 39' W: -(85 + 39/60) = -85.65
        origin_longitude=-85.65,
        origin_scale=1.000024,
        skew_azimuth=None,
        false_northing_m=76200.0,
        false_easting_m=1333500.0,
        false_northing_ift=250000.0,
        false_easting_ift=4375000.0,
    ),
    Spcs2022ZoneParameters(
        code='261008',
        abbrev='MI_L45G',
        name='Michigan Grand Rapids',
        projection_type='LC1',
        # 42 deg 48' N: 42 + 48/60 = 42.8
        origin_latitude=42.8,
        # 85 deg 09' W: -(85 + 9/60) = -85.15
        origin_longitude=-85.15,
        origin_scale=1.000018,
        skew_azimuth=None,
        false_northing_m=228600.0,
        false_easting_m=1409700.0,
        false_northing_ift=750000.0,
        false_easting_ift=4625000.0,
    ),
    Spcs2022ZoneParameters(
        code='261009',
        abbrev='MI_L51N',
        name='Michigan Newaygo',
        projection_type='LC1',
        # 43 deg 27' N: 43 + 27/60 = 43.45
        origin_latitude=43.45,
        # 85 deg 24' W: -(85 + 24/60) = -85.4
        origin_longitude=-85.4,
        origin_scale=1.000025,
        skew_azimuth=None,
        false_northing_m=76200.0,
        false_easting_m=1638300.0,
        false_northing_ift=250000.0,
        false_easting_ift=5375000.0,
    ),
    Spcs2022ZoneParameters(
        code='261010',
        abbrev='MI_L55W',
        name='Michigan Wexford',
        projection_type='LC1',
        # 44 deg 09' N: 44 + 9/60 = 44.15
        origin_latitude=44.15,
        # 85 deg 33' W: -(85 + 33/60) = -85.55
        origin_longitude=-85.55,
        origin_scale=1.000034,
        skew_azimuth=None,
        false_northing_m=190500.0,
        false_easting_m=1638300.0,
        false_northing_ift=625000.0,
        false_easting_ift=5375000.0,
    ),
    Spcs2022ZoneParameters(
        code='261011',
        abbrev='MI_L61L',
        name='Michigan Leelanau',
        projection_type='LC1',
        # 44 deg 54' N: 44 + 54/60 = 44.9
        origin_latitude=44.9,
        # 85 deg 27' W: -(85 + 27/60) = -85.45
        origin_longitude=-85.45,
        origin_scale=1.000025,
        skew_azimuth=None,
        false_northing_m=76200.0,
        false_easting_m=1905000.0,
        false_northing_ift=250000.0,
        false_easting_ift=6250000.0,
    ),
    Spcs2022ZoneParameters(
        code='261012',
        abbrev='MI_L65C',
        name='Michigan Cheboygan',
        projection_type='LC1',
        # 45 deg 27' N: 45 + 27/60 = 45.45
        origin_latitude=45.45,
        # 84 deg 27' W: -(84 + 27/60) = -84.45
        origin_longitude=-84.45,
        origin_scale=1.000025,
        skew_azimuth=None,
        false_northing_m=190500.0,
        false_easting_m=2019300.0,
        false_northing_ift=625000.0,
        false_easting_ift=6625000.0,
    ),
    Spcs2022ZoneParameters(
        code='261013',
        abbrev='MI_U11M',
        name='Michigan Mackinac',
        projection_type='LC1',
        # 46 deg 12' N: 46 + 12/60 = 46.2
        origin_latitude=46.2,
        # 84 deg 51' W: -(84 + 51/60) = -84.85
        origin_longitude=-84.85,
        origin_scale=1.000011,
        skew_azimuth=None,
        false_northing_m=76200.0,
        false_easting_m=381000.0,
        false_northing_ift=250000.0,
        false_easting_ift=1250000.0,
    ),
    Spcs2022ZoneParameters(
        code='261014',
        abbrev='MI_U21E',
        name='Michigan Escanaba',
        projection_type='TM',
        # 45 deg 09' N: 45 + 9/60 = 45.15
        origin_latitude=45.15,
        # 86 deg 36' W: -(86 + 36/60) = -86.6
        origin_longitude=-86.6,
        origin_scale=1.000012,
        skew_azimuth=None,
        false_northing_m=0.0,
        false_easting_m=685800.0,
        false_northing_ift=0.0,
        false_easting_ift=2250000.0,
    ),
    Spcs2022ZoneParameters(
        code='261015',
        abbrev='MI_U31Q',
        name='Michigan Marquette',
        projection_type='TM',
        # 44 deg 42' N: 44 + 42/60 = 44.7
        origin_latitude=44.7,
        # 87 deg 36' W: -(87 + 36/60) = -87.6
        origin_longitude=-87.6,
        origin_scale=1.000038,
        skew_azimuth=None,
        false_northing_m=0.0,
        false_easting_m=952500.0,
        false_northing_ift=0.0,
        false_easting_ift=3125000.0,
    ),
    Spcs2022ZoneParameters(
        code='261016',
        abbrev='MI_U41H',
        name='Michigan Houghton',
        projection_type='TM',
        # 45 deg 30' N: 45 + 30/60 = 45.5
        origin_latitude=45.5,
        # 88 deg 24' W: -(88 + 24/60) = -88.4
        origin_longitude=-88.4,
        origin_scale=1.000042,
        skew_azimuth=None,
        false_northing_m=0.0,
        false_easting_m=1295400.0,
        false_northing_ift=0.0,
        false_easting_ift=4250000.0,
    ),
    Spcs2022ZoneParameters(
        code='261017',
        abbrev='MI_U51B',
        name='Michigan Bessemer',
        projection_type='LC1',
        # 46 deg 42' N: 46 + 42/60 = 46.7
        origin_latitude=46.7,
        # 89 deg 42' W: -(89 + 42/60) = -89.7
        origin_longitude=-89.7,
        origin_scale=1.000036,
        skew_azimuth=None,
        false_northing_m=114300.0,
        false_easting_m=1600200.0,
        false_northing_ift=375000.0,
        false_easting_ift=5250000.0,
    ),
    Spcs2022ZoneParameters(
        code='261018',
        abbrev='MI_U61K',
        name='Michigan Isle Royale',
        projection_type='LC1',
        # 48 deg 00' N: 48 + 0/60 = 48.0
        origin_latitude=48.0,
        # 88 deg 51' W: -(88 + 51/60) = -88.85
        origin_longitude=-88.85,
        origin_scale=1.000026,
        skew_azimuth=None,
        false_northing_m=76200.0,
        false_easting_m=1866900.0,
        false_northing_ift=250000.0,
        false_easting_ift=6125000.0,
    ),
)
"""The nineteen Michigan SPCS2022 zones, in NGS's own order: the statewide
oblique Mercator first, then the eighteen low-distortion zones by code."""


SPCS2022_PROJECTION_ANCHORS: tuple[Spcs2022Anchor, ...] = (
    Spcs2022Anchor(
        zone_code='260001',
        label='Detroit area',
        latitude=42.100000,
        longitude=-83.200000,
        northing_m=443768.217,
        easting_m=1755596.782,
        northing_ift=1455932.472,
        easting_ift=5759831.962,
        scale_factor=0.999858230,
        convergence_dms='+01 54 40.49',
        capture='raw/z260001_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='260001',
        label='far SW',
        latitude=41.900000,
        longitude=-86.600000,
        northing_m=417769.740,
        easting_m=1474269.524,
        northing_ift=1370635.628,
        easting_ift=4836842.270,
        scale_factor=1.000270716,
        convergence_dms='-00 22 23.36',
        capture='raw/z260001_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='260001',
        label='mid-mitten',
        latitude=43.600000,
        longitude=-84.200000,
        northing_m=608056.647,
        easting_m=1669305.544,
        northing_ift=1994936.507,
        easting_ift=5476724.225,
        scale_factor=0.999849004,
        convergence_dms='+01 14 53.92',
        capture='raw/z260001_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='260001',
        label='NW Lake Michigan',
        latitude=44.800000,
        longitude=-87.400000,
        northing_m=740734.526,
        easting_m=1413252.847,
        northing_ift=2430231.383,
        easting_ift=4636656.322,
        scale_factor=0.999945690,
        convergence_dms='-00 59 25.81',
        capture='raw/z260001_p4.html',
    ),
    Spcs2022Anchor(
        zone_code='260001',
        label='eastern UP',
        latitude=45.900000,
        longitude=-84.700000,
        northing_m=862829.994,
        easting_m=1624868.041,
        northing_ift=2830807.068,
        easting_ift=5330931.894,
        scale_factor=1.000023585,
        convergence_dms='+00 55 51.20',
        capture='raw/z260001_p5.html',
    ),
    Spcs2022Anchor(
        zone_code='260001',
        label='central UP',
        latitude=46.500000,
        longitude=-87.600000,
        northing_m=929914.111,
        easting_m=1401203.127,
        northing_ift=3050899.316,
        easting_ift=4597123.120,
        scale_factor=0.999816572,
        convergence_dms='-01 09 05.48',
        capture='raw/z260001_p6.html',
    ),
    Spcs2022Anchor(
        zone_code='260001',
        label='Keweenaw',
        latitude=47.100000,
        longitude=-88.600000,
        northing_m=998601.613,
        easting_m=1326671.208,
        northing_ift=3276252.012,
        easting_ift=4352595.826,
        scale_factor=0.999866553,
        convergence_dms='-01 53 16.29',
        capture='raw/z260001_p7.html',
    ),
    Spcs2022Anchor(
        zone_code='260001',
        label='Isle Royale',
        latitude=48.100000,
        longitude=-88.550000,
        northing_m=1109582.833,
        easting_m=1334062.199,
        northing_ift=3640363.625,
        easting_ift=4376844.485,
        scale_factor=0.999803779,
        convergence_dms='-01 51 25.87',
        capture='raw/z260001_p8.html',
    ),
    Spcs2022Anchor(
        zone_code='260001',
        label='projection center',
        latitude=45.000000,
        longitude=-86.000000,
        northing_m=762000.000,
        easting_m=1524000.000,
        northing_ift=2500000.000,
        easting_ift=5000000.000,
        scale_factor=0.999800000,
        convergence_dms='-00 00 00.00',
        capture='raw/z260001_p9.html',
    ),
    Spcs2022Anchor(
        zone_code='261001',
        label='origin',
        latitude=41.300000,
        longitude=-84.100000,
        northing_m=0.000,
        easting_m=381000.000,
        northing_ift=0.000,
        easting_ift=1250000.000,
        scale_factor=1.000022000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261001_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261001',
        label='origin +0.15/+0.25',
        latitude=41.450000,
        longitude=-83.850000,
        northing_m=16689.711,
        easting_m=401890.558,
        northing_ift=54756.270,
        easting_ift=1318538.575,
        scale_factor=1.000027368,
        convergence_dms='+00 09 55.77',
        capture='raw/z261001_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261001',
        label='origin -0.15/-0.25',
        latitude=41.150000,
        longitude=-84.350000,
        northing_m=-16628.977,
        easting_m=360013.491,
        northing_ift=-54557.011,
        easting_ift=1181146.623,
        scale_factor=1.000027418,
        convergence_dms='-00 09 52.23',
        capture='raw/z261001_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261002',
        label='origin',
        latitude=40.200000,
        longitude=-83.150000,
        northing_m=0.000,
        easting_m=495300.000,
        northing_ift=0.000,
        easting_ift=1625000.000,
        scale_factor=1.000024000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261002_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261002',
        label='origin +0.15/+0.25',
        latitude=40.350000,
        longitude=-82.900000,
        northing_m=16686.390,
        easting_m=516539.589,
        northing_ift=54745.373,
        easting_ift=1694683.692,
        scale_factor=1.000029551,
        convergence_dms='+00 09 42.71',
        capture='raw/z261002_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261002',
        label='origin -0.15/-0.25',
        latitude=40.050000,
        longitude=-83.400000,
        northing_m=-16626.007,
        easting_m=473966.591,
        northing_ift=-54547.267,
        easting_ift=1555008.501,
        scale_factor=1.000029600,
        convergence_dms='-00 09 39.11',
        capture='raw/z261002_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261003',
        label='origin',
        latitude=42.900000,
        longitude=-83.400000,
        northing_m=76200.000,
        easting_m=685800.000,
        northing_ift=250000.000,
        easting_ift=2250000.000,
        scale_factor=1.000026000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261003_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261003',
        label='origin +0.15/+0.25',
        latitude=43.050000,
        longitude=-83.150000,
        northing_m=92894.540,
        easting_m=706169.274,
        northing_ift=304772.113,
        easting_ift=2316828.327,
        scale_factor=1.000029418,
        convergence_dms='+00 10 12.65',
        capture='raw/z261003_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261003',
        label='origin -0.15/-0.25',
        latitude=42.750000,
        longitude=-83.650000,
        northing_m=59566.546,
        easting_m=665331.735,
        northing_ift=195428.301,
        easting_ift=2182846.899,
        scale_factor=1.000029412,
        convergence_dms='-00 10 12.65',
        capture='raw/z261003_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261004',
        label='origin',
        latitude=43.600000,
        longitude=-83.650000,
        northing_m=228600.000,
        easting_m=723900.000,
        northing_ift=750000.000,
        easting_ift=2375000.000,
        scale_factor=1.000012000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261004_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261004',
        label='origin +0.15/+0.25',
        latitude=43.750000,
        longitude=-83.400000,
        northing_m=245296.398,
        easting_m=744035.832,
        northing_ift=804778.210,
        easting_ift=2441062.440,
        scale_factor=1.000015418,
        convergence_dms='+00 10 20.66',
        capture='raw/z261004_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261004',
        label='origin -0.15/-0.25',
        latitude=43.450000,
        longitude=-83.900000,
        northing_m=211964.781,
        easting_m=703663.872,
        northing_ift=695422.510,
        easting_ift=2308608.504,
        scale_factor=1.000015412,
        convergence_dms='-00 10 20.66',
        capture='raw/z261004_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261005',
        label='origin',
        latitude=44.250000,
        longitude=-84.150000,
        northing_m=76200.000,
        easting_m=990600.000,
        northing_ift=250000.000,
        easting_ift=3250000.000,
        scale_factor=1.000029000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261005_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261005',
        label='origin +0.15/+0.25',
        latitude=44.400000,
        longitude=-83.900000,
        northing_m=92898.611,
        easting_m=1010516.959,
        northing_ift=304785.470,
        easting_ift=3315344.354,
        scale_factor=1.000032418,
        convergence_dms='+00 10 28.01',
        capture='raw/z261005_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261005',
        label='origin -0.15/-0.25',
        latitude=44.100000,
        longitude=-84.400000,
        northing_m=59562.624,
        easting_m=970581.543,
        northing_ift=195415.432,
        easting_ift=3184322.647,
        scale_factor=1.000032412,
        convergence_dms='-00 10 28.01',
        capture='raw/z261005_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261006',
        label='origin',
        latitude=44.850000,
        longitude=-84.050000,
        northing_m=190500.000,
        easting_m=1028700.000,
        northing_ift=625000.000,
        easting_ift=3375000.000,
        scale_factor=1.000031000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261006_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261006',
        label='origin +0.15/+0.25',
        latitude=45.000000,
        longitude=-83.800000,
        northing_m=207200.412,
        easting_m=1048412.356,
        northing_ift=679791.379,
        easting_ift=3439673.084,
        scale_factor=1.000034419,
        convergence_dms='+00 10 34.73',
        capture='raw/z261006_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261006',
        label='origin -0.15/-0.25',
        latitude=44.700000,
        longitude=-84.300000,
        northing_m=173860.845,
        easting_m=1008885.049,
        northing_ift=570409.596,
        easting_ift=3309990.320,
        scale_factor=1.000034412,
        convergence_dms='-00 10 34.73',
        capture='raw/z261006_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261007',
        label='origin',
        latitude=42.100000,
        longitude=-85.650000,
        northing_m=76200.000,
        easting_m=1333500.000,
        northing_ift=250000.000,
        easting_ift=4375000.000,
        scale_factor=1.000024000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261007_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261007',
        label='origin +0.15/+0.25',
        latitude=42.250000,
        longitude=-85.400000,
        northing_m=92892.099,
        easting_m=1354131.955,
        northing_ift=304764.103,
        easting_ift=4442690.142,
        scale_factor=1.000027417,
        convergence_dms='+00 10 03.38',
        capture='raw/z261007_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261007',
        label='origin -0.15/-0.25',
        latitude=41.950000,
        longitude=-85.900000,
        northing_m=59568.836,
        easting_m=1312770.564,
        northing_ift=195435.812,
        easting_ift=4306990.040,
        scale_factor=1.000027412,
        convergence_dms='-00 10 03.38',
        capture='raw/z261007_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261008',
        label='origin',
        latitude=42.800000,
        longitude=-85.150000,
        northing_m=228600.000,
        easting_m=1409700.000,
        northing_ift=750000.000,
        easting_ift=4625000.000,
        scale_factor=1.000018000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261008_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261008',
        label='origin +0.15/+0.25',
        latitude=42.950000,
        longitude=-84.900000,
        northing_m=245294.106,
        easting_m=1430102.171,
        northing_ift=804770.691,
        easting_ift=4691936.255,
        scale_factor=1.000021417,
        convergence_dms='+00 10 11.50',
        capture='raw/z261008_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261008',
        label='origin -0.15/-0.25',
        latitude=42.650000,
        longitude=-85.400000,
        northing_m=211966.963,
        easting_m=1389199.027,
        northing_ift=695429.668,
        easting_ift=4557739.589,
        scale_factor=1.000021412,
        convergence_dms='-00 10 11.50',
        capture='raw/z261008_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261009',
        label='origin',
        latitude=43.450000,
        longitude=-85.400000,
        northing_m=76200.000,
        easting_m=1638300.000,
        northing_ift=250000.000,
        easting_ift=5375000.000,
        scale_factor=1.000025000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261009_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261009',
        label='origin +0.15/+0.25',
        latitude=43.600000,
        longitude=-85.150000,
        northing_m=92896.168,
        easting_m=1658486.312,
        northing_ift=304777.455,
        easting_ift=5441228.058,
        scale_factor=1.000028418,
        convergence_dms='+00 10 18.95',
        capture='raw/z261009_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261009',
        label='origin -0.15/-0.25',
        latitude=43.300000,
        longitude=-85.650000,
        northing_m=59564.995,
        easting_m=1618013.669,
        northing_ift=195423.211,
        easting_ift=5308443.796,
        scale_factor=1.000028412,
        convergence_dms='-00 10 18.95',
        capture='raw/z261009_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261010',
        label='origin',
        latitude=44.150000,
        longitude=-85.550000,
        northing_m=190500.000,
        easting_m=1638300.000,
        northing_ift=625000.000,
        easting_ift=5375000.000,
        scale_factor=1.000034000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261010_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261010',
        label='origin +0.15/+0.25',
        latitude=44.300000,
        longitude=-85.300000,
        northing_m=207198.399,
        easting_m=1658250.953,
        northing_ift=679784.773,
        easting_ift=5440455.882,
        scale_factor=1.000037418,
        convergence_dms='+00 10 26.89',
        capture='raw/z261010_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261010',
        label='origin -0.15/-0.25',
        latitude=44.000000,
        longitude=-85.800000,
        northing_m=173862.830,
        easting_m=1618247.732,
        northing_ift=570416.109,
        easting_ift=5309211.721,
        scale_factor=1.000037412,
        convergence_dms='-00 10 26.89',
        capture='raw/z261010_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261011',
        label='origin',
        latitude=44.900000,
        longitude=-85.450000,
        northing_m=76200.000,
        easting_m=1905000.000,
        northing_ift=250000.000,
        easting_ift=6250000.000,
        scale_factor=1.000025000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261011_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261011',
        label='origin +0.15/+0.25',
        latitude=45.050000,
        longitude=-85.200000,
        northing_m=92900.459,
        easting_m=1924695.086,
        northing_ift=304791.532,
        easting_ift=6314616.423,
        scale_factor=1.000028419,
        convergence_dms='+00 10 35.28',
        capture='raw/z261011_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261011',
        label='origin -0.15/-0.25',
        latitude=44.750000,
        longitude=-85.700000,
        northing_m=59560.799,
        easting_m=1885202.229,
        northing_ift=195409.445,
        easting_ift=6185046.685,
        scale_factor=1.000028412,
        convergence_dms='-00 10 35.28',
        capture='raw/z261011_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261012',
        label='origin',
        latitude=45.450000,
        longitude=-84.450000,
        northing_m=190500.000,
        easting_m=2019300.000,
        northing_ift=625000.000,
        easting_ift=6625000.000,
        scale_factor=1.000025000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261012_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261012',
        label='origin +0.15/+0.25',
        latitude=45.600000,
        longitude=-84.200000,
        northing_m=207202.067,
        easting_m=2038805.420,
        northing_ift=679796.808,
        easting_ift=6688994.160,
        scale_factor=1.000028419,
        convergence_dms='+00 10 41.37',
        capture='raw/z261012_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261012',
        label='origin -0.15/-0.25',
        latitude=45.300000,
        longitude=-84.700000,
        northing_m=173859.185,
        easting_m=1999690.901,
        northing_ift=570404.151,
        easting_ift=6560665.685,
        scale_factor=1.000028413,
        convergence_dms='-00 10 41.37',
        capture='raw/z261012_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261013',
        label='origin',
        latitude=46.200000,
        longitude=-84.850000,
        northing_m=76200.000,
        easting_m=381000.000,
        northing_ift=250000.000,
        easting_ift=1250000.000,
        scale_factor=1.000011000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261013_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261013',
        label='origin +0.15/+0.25',
        latitude=46.350000,
        longitude=-84.600000,
        northing_m=92904.008,
        easting_m=400243.602,
        northing_ift=304803.175,
        easting_ift=1313135.177,
        scale_factor=1.000014419,
        convergence_dms='+00 10 49.58',
        capture='raw/z261013_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261013',
        label='origin -0.15/-0.25',
        latitude=46.050000,
        longitude=-85.100000,
        northing_m=59557.201,
        easting_m=361651.379,
        northing_ift=195397.640,
        easting_ift=1186520.274,
        scale_factor=1.000014413,
        convergence_dms='-00 10 49.58',
        capture='raw/z261013_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261014',
        label='origin',
        latitude=45.150000,
        longitude=-86.600000,
        northing_m=0.000,
        easting_m=685800.000,
        northing_ift=0.000,
        easting_ift=2250000.000,
        scale_factor=1.000012000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261014_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261014',
        label='origin +0.15/+0.25',
        latitude=45.300000,
        longitude=-86.350000,
        northing_m=16701.034,
        easting_m=705408.808,
        northing_ift=54793.419,
        easting_ift=2314333.361,
        scale_factor=1.000016726,
        convergence_dms='+00 10 39.72',
        capture='raw/z261014_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261014',
        label='origin -0.15/-0.25',
        latitude=45.000000,
        longitude=-86.850000,
        northing_m=-16639.777,
        easting_m=666088.055,
        northing_ift=-54592.446,
        easting_ift=2185328.263,
        scale_factor=1.000016776,
        convergence_dms='-00 10 36.40',
        capture='raw/z261014_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261015',
        label='origin',
        latitude=44.700000,
        longitude=-87.600000,
        northing_m=0.000,
        easting_m=952500.000,
        northing_ift=0.000,
        easting_ift=3125000.000,
        scale_factor=1.000038000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261015_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261015',
        label='origin +0.15/+0.25',
        latitude=44.850000,
        longitude=-87.350000,
        northing_m=16700.150,
        easting_m=972263.824,
        northing_ift=54790.517,
        easting_ift=3189841.942,
        scale_factor=1.000042801,
        convergence_dms='+00 10 34.73',
        capture='raw/z261015_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261015',
        label='origin -0.15/-0.25',
        latitude=44.550000,
        longitude=-87.850000,
        northing_m=-16638.896,
        easting_m=932633.853,
        northing_ift=-54589.552,
        easting_ift=3059822.354,
        scale_factor=1.000042851,
        convergence_dms='-00 10 31.38',
        capture='raw/z261015_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261016',
        label='origin',
        latitude=45.500000,
        longitude=-88.400000,
        northing_m=0.000,
        easting_m=1295400.000,
        northing_ift=0.000,
        easting_ift=4250000.000,
        scale_factor=1.000042000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261016_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261016',
        label='origin +0.15/+0.25',
        latitude=45.650000,
        longitude=-88.150000,
        northing_m=16702.556,
        easting_m=1314888.382,
        northing_ift=54798.411,
        easting_ift=4313938.263,
        scale_factor=1.000046667,
        convergence_dms='+00 10 43.58',
        capture='raw/z261016_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261016',
        label='origin -0.15/-0.25',
        latitude=45.350000,
        longitude=-88.650000,
        northing_m=-16641.304,
        easting_m=1275807.846,
        northing_ift=-54597.455,
        easting_ift=4185721.280,
        scale_factor=1.000046717,
        convergence_dms='-00 10 40.27',
        capture='raw/z261016_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261017',
        label='origin',
        latitude=46.700000,
        longitude=-89.700000,
        northing_m=114300.000,
        easting_m=1600200.000,
        northing_ift=375000.000,
        easting_ift=5250000.000,
        scale_factor=1.000036000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261017_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261017',
        label='origin +0.15/+0.25',
        latitude=46.850000,
        longitude=-89.450000,
        northing_m=131005.862,
        easting_m=1619267.868,
        northing_ift=429809.259,
        easting_ift=5312558.621,
        scale_factor=1.000039419,
        convergence_dms='+00 10 55.00',
        capture='raw/z261017_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261017',
        label='origin -0.15/-0.25',
        latitude=46.550000,
        longitude=-89.950000,
        northing_m=97655.295,
        easting_m=1581026.227,
        northing_ift=320391.389,
        easting_ift=5187093.921,
        scale_factor=1.000039413,
        convergence_dms='-00 10 55.00',
        capture='raw/z261017_p3.html',
    ),
    Spcs2022Anchor(
        zone_code='261018',
        label='origin',
        latitude=48.000000,
        longitude=-88.850000,
        northing_m=76200.000,
        easting_m=1866900.000,
        northing_ift=250000.000,
        easting_ift=6125000.000,
        scale_factor=1.000026000,
        convergence_dms='+00 00 00.00',
        capture='raw/z261018_p1.html',
    ),
    Spcs2022Anchor(
        zone_code='261018',
        label='origin +0.15/+0.25',
        latitude=48.150000,
        longitude=-88.600000,
        northing_m=92909.380,
        easting_m=1885502.707,
        northing_ift=304820.801,
        easting_ift=6186032.504,
        scale_factor=1.000029420,
        convergence_dms='+00 11 08.83',
        capture='raw/z261018_p2.html',
    ),
    Spcs2022Anchor(
        zone_code='261018',
        label='origin -0.15/-0.25',
        latitude=47.850000,
        longitude=-89.100000,
        northing_m=59551.554,
        easting_m=1848189.127,
        northing_ift=195379.113,
        easting_ift=6063612.621,
        scale_factor=1.000029413,
        convergence_dms='-00 11 08.83',
        capture='raw/z261018_p3.html',
    ),
)
"""All 63 pure-projection anchors: nine on the statewide oblique Mercator, and
three on each of the eighteen low-distortion zones."""
