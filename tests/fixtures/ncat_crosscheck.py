"""NGS NCAT and geoid results from the 2026-08-06 live cross-check, frozen.

Companion to ``ncat_anchors.py``, which freezes the 2026-08-05 lattice. These
are the thirteen fresh points of the closing cross-check, chosen to share no
latitude and no longitude with that lattice (see
``review/ncat-crosscheck/points.md`` for each point's rationale).

Every value below was computed by the National Geodetic Survey and captured
verbatim from its APIs on **2026-08-06**:

    https://geodesy.noaa.gov/api/ncat/llh
        ?lat=<lat>&lon=<lon>
        &inDatum=NAD83(2011)&outDatum=NAD83(2011)&spcZone=<zone>

    https://geodesy.noaa.gov/api/ncat/spc
        ?northing=<n>&easting=<e>&units=<m|ift|usft>&spcZone=<zone>
        &inDatum=NAD83(2011)&outDatum=NAD83(2011)

    https://geodesy.noaa.gov/api/geoid/ght?lat=<lat>&lon=<lon>

**Input and output datum are set to the same realization** in every NCAT
query, so NCAT performs a pure coordinate *conversion* with no datum
transformation. The SPCS 83 mapping equations are realization-independent, so
these anchors test projection mathematics and nothing else.

The verbatim responses were captured to ``review/ncat-crosscheck/raw/``;
the ``source`` field on every record below names the file it came from. Each
number here was transcribed from that JSON - none was recomputed by this
program. The only arithmetic applied to a captured value is stripping NCAT's
thousands separators (``"7,952,379.960"`` -> ``7952379.96``) and converting
the convergence angle NCAT prints as a DMS string into decimal degrees, which
``convergence_dms`` carries alongside so the transcription is checkable.

**No test touches the network** - that is the point of freezing them.

Precision NGS prints, which sets the tolerance a value can be held to:
    northing, easting   0.001 m / 0.001 ft
    latitude, longitude 10 decimal places
    convergence         0.01 arc second
    grid scale factor   8 decimal places
    geoid height        0.001 m
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrosscheckPoint:
    """One of the thirteen locations, and the job inputs chosen for it.

    The latitude, longitude and elevation are **inputs the cross-check chose**
    (review/ncat-crosscheck/points_def.py), not NGS outputs. The elevation is a
    realistic Michigan orthometric height in metres, used as the Z column of
    the PNEZD files the end-to-end tests write.
    """

    point_id: str
    home_zone: str | None
    """The zone the point sits in. None for NS, which lies between the North
    and South bands and belongs to neither."""

    latitude: float
    longitude: float
    """Decimal degrees, negative west."""

    elevation_m: float
    rationale: str


@dataclass(frozen=True)
class CrosscheckForward:
    """One NCAT ``llh`` result - geodetic in, State Plane out. Verbatim."""

    point_id: str
    zone_code: str
    latitude: float
    longitude: float
    """The query position. Decimal degrees, negative west."""

    northing_m: float
    easting_m: float
    northing_ift: float
    easting_ift: float
    northing_usft: float
    easting_usft: float
    convergence_dms: str
    """Exactly as NCAT printed it."""

    convergence_deg: float
    """``convergence_dms`` in decimal degrees. Sign on the whole quantity."""

    scale_factor: float
    source: str
    """The raw capture this record was transcribed from."""


@dataclass(frozen=True)
class CrosscheckInverse:
    """One NCAT ``spc`` result - State Plane in, geodetic out. Verbatim.

    The northing and easting are the ones NCAT itself printed for this point in
    ``CrosscheckForward``, rounded to the 3 decimal places NCAT publishes and
    fed back to it. So both ends of this record are NGS's numbers.
    """

    point_id: str
    zone_code: str
    unit_code: str
    """``m``, ``ift`` or ``usft`` - the unit the query coordinates are in."""

    northing: float
    easting: float
    """In ``unit_code``. What was sent to NCAT."""

    latitude: float
    longitude: float
    """What NCAT returned. Decimal degrees, negative west, 10 places."""

    source: str


@dataclass(frozen=True)
class CrosscheckGeoid:
    """One NGS GEOID18 separation for one of the thirteen locations."""

    point_id: str
    latitude: float
    longitude: float
    geoid_height_m: float
    """Negative throughout the conterminous United States."""

    error_m: float
    """NGS's own stated uncertainty for the model at this point."""

    source: str


# Tolerances the 2026-08-06 live run established, and passed at, over all 666
# comparisons in review/ncat-crosscheck/comparison.csv.
CROSSCHECK_TOLERANCES = {
    "linear_m": 0.002,
    "geoid_m": 0.002,
    "scale_factor": 2e-8,
    "convergence_arcsec": 0.02,
}
"""One NCAT leg of quantization is +-0.0005 m; 0.002 m is four times that.

A zone-to-zone conversion has an NCAT figure at BOTH ends, so its budget is
twice the single-leg one - which is what the live run used and passed at.
"""


CROSSCHECK_POINTS: tuple[CrosscheckPoint, ...] = (

    CrosscheckPoint(
        point_id="N1",
        home_zone="2111",
        latitude=45.105,
        longitude=-87.605,
        elevation_m=180.0,
        rationale="Menominee - southern edge of the North zone band, west of the CM",
    ),
    CrosscheckPoint(
        point_id="N2",
        home_zone="2111",
        latitude=48.05,
        longitude=-88.55,
        elevation_m=190.0,
        rationale="Isle Royale - northern latitude extreme, far-west longitude",
    ),
    CrosscheckPoint(
        point_id="N3",
        home_zone="2111",
        latitude=46.4953,
        longitude=-84.3453,
        elevation_m=183.0,
        rationale="Sault Ste. Marie - realistic city where a survey job could sit, far east",
    ),
    CrosscheckPoint(
        point_id="N4",
        home_zone="2111",
        latitude=47.1211,
        longitude=-88.5694,
        elevation_m=275.0,
        rationale="Houghton - high latitude, Keweenaw, west of the CM",
    ),
    CrosscheckPoint(
        point_id="C1",
        home_zone="2112",
        latitude=43.6,
        longitude=-86.45,
        elevation_m=200.0,
        rationale="Silver Lake / Mears - southern edge of the Central band, west extreme",
    ),
    CrosscheckPoint(
        point_id="C2",
        home_zone="2112",
        latitude=45.9,
        longitude=-84.72,
        elevation_m=190.0,
        rationale="Brevort near the Straits - northern edge of the Central band; N/C pair point",
    ),
    CrosscheckPoint(
        point_id="C3",
        home_zone="2112",
        latitude=44.7631,
        longitude=-85.6206,
        elevation_m=187.0,
        rationale="Traverse City - realistic city where a survey job could sit",
    ),
    CrosscheckPoint(
        point_id="C4",
        home_zone="2112",
        latitude=44.3,
        longitude=-83.5,
        elevation_m=181.0,
        rationale="Tawas area - eastern longitude extreme of the Central zone",
    ),
    CrosscheckPoint(
        point_id="S1",
        home_zone="2113",
        latitude=41.9,
        longitude=-86.55,
        elevation_m=220.0,
        rationale="Niles/Buchanan - southern latitude extreme, west side",
    ),
    CrosscheckPoint(
        point_id="S2",
        home_zone="2113",
        latitude=44.252,
        longitude=-85.4012,
        elevation_m=397.0,
        rationale="Cadillac - northern edge of the South band, high elevation; C/S pair point",
    ),
    CrosscheckPoint(
        point_id="S3",
        home_zone="2113",
        latitude=42.3314,
        longitude=-83.0458,
        elevation_m=183.0,
        rationale="Detroit - realistic city where a survey job could sit, east side",
    ),
    CrosscheckPoint(
        point_id="S4",
        home_zone="2113",
        latitude=42.78,
        longitude=-86.05,
        elevation_m=190.0,
        rationale="Holland area - west side, mid-band",
    ),
    CrosscheckPoint(
        point_id="NS",
        home_zone=None,
        latitude=44.65,
        longitude=-85.5,
        elevation_m=310.0,
        rationale="Kalkaska area - between the North and South bands; probes whether NCAT accepts a point in both 2111 and 2113 for the N<->S pair",
    ),
)


CROSSCHECK_FORWARD: tuple[CrosscheckForward, ...] = (

    CrosscheckForward(
        point_id="N1",
        zone_code="2111",
        latitude=45.105,
        longitude=-87.605,
        northing_m=35935.015,
        easting_m=7952379.96,
        northing_ift=117897.031,
        easting_ift=26090485.434,
        northing_usft=117896.795,
        easting_usft=26090433.253,
        convergence_dms="-00 26 14.24",
        convergence_deg=-0.4372888888888889,
        scale_factor=1.00011284,
        source="llh_N1_2111.json",
    ),
    CrosscheckForward(
        point_id="N2",
        zone_code="2111",
        latitude=48.05,
        longitude=-88.55,
        northing_m=364265.841,
        easting_m=7884405.849,
        northing_ift=1195097.904,
        easting_ift=25867473.259,
        northing_usft=1195095.513,
        easting_usft=25867421.524,
        convergence_dms="-01 07 13.17",
        convergence_deg=-1.120325,
        scale_factor=1.00038104,
        source="llh_N2_2111.json",
    ),
    CrosscheckForward(
        point_id="N3",
        zone_code="2111",
        latitude=46.4953,
        longitude=-84.3453,
        northing_m=193687.687,
        easting_m=8203742.69,
        northing_ift=635458.291,
        easting_ift=26915166.305,
        northing_usft=635457.02,
        easting_usft=26915112.474,
        convergence_dms="01 55 07.65",
        convergence_deg=1.9187916666666665,
        scale_factor=0.99990954,
        source="llh_N3_2111.json",
    ),
    CrosscheckForward(
        point_id="N4",
        zone_code="2111",
        latitude=47.1211,
        longitude=-88.5694,
        northing_m=261019.506,
        easting_m=7880914.336,
        northing_ift=856363.207,
        easting_ift=25856018.162,
        northing_usft=856361.494,
        easting_usft=25855966.45,
        convergence_dms="-01 08 03.65",
        convergence_deg=-1.1343472222222222,
        scale_factor=1.00000944,
        source="llh_N4_2111.json",
    ),
    CrosscheckForward(
        point_id="C1",
        zone_code="2112",
        latitude=43.6,
        longitude=-86.45,
        northing_m=33647.176,
        easting_m=5831772.715,
        northing_ift=110390.997,
        easting_ift=19133112.583,
        northing_usft=110390.776,
        easting_usft=19133074.317,
        convergence_dms="-01 28 18.06",
        convergence_deg=-1.4716833333333335,
        scale_factor=1.00018455,
        source="llh_C1_2112.json",
    ),
    CrosscheckForward(
        point_id="C2",
        zone_code="2112",
        latitude=45.9,
        longitude=-84.72,
        northing_m=287134.307,
        easting_m=5972579.018,
        northing_ift=942041.691,
        easting_ift=19595075.52,
        northing_usft=942039.807,
        easting_usft=19595036.33,
        convergence_dms="-00 14 58.55",
        convergence_deg=-0.24959722222222222,
        scale_factor=1.00005242,
        source="llh_C2_2112.json",
    ),
    CrosscheckForward(
        point_id="C3",
        zone_code="2112",
        latitude=44.7631,
        longitude=-85.6206,
        northing_m=161494.864,
        easting_m=5900736.89,
        northing_ift=529838.792,
        easting_ift=19359373.0,
        northing_usft=529837.732,
        easting_usft=19359334.281,
        convergence_dms="-00 53 08.84",
        convergence_deg=-0.8857888888888888,
        scale_factor=0.99991763,
        source="llh_C3_2112.json",
    ),
    CrosscheckForward(
        point_id="C4",
        zone_code="2112",
        latitude=44.3,
        longitude=-83.5,
        northing_m=109639.182,
        easting_m=6069157.798,
        northing_ift=359708.601,
        easting_ift=19911935.032,
        northing_usft=359707.881,
        easting_usft=19911895.208,
        convergence_dms="00 36 43.99",
        convergence_deg=0.6122194444444444,
        scale_factor=0.9999753,
        source="llh_C4_2112.json",
    ),
    CrosscheckForward(
        point_id="S1",
        zone_code="2113",
        latitude=41.9,
        longitude=-86.55,
        northing_m=46781.481,
        easting_m=3818836.874,
        northing_ift=153482.55,
        easting_ift=12528992.369,
        northing_usft=153482.243,
        easting_usft=12528967.311,
        convergence_dms="-01 29 08.96",
        convergence_deg=-1.4858222222222224,
        scale_factor=1.00005334,
        source="llh_S1_2113.json",
    ),
    CrosscheckForward(
        point_id="S2",
        zone_code="2113",
        latitude=44.252,
        longitude=-85.4012,
        northing_m=306229.145,
        easting_m=3917362.188,
        northing_ift=1004688.797,
        easting_ift=12852238.149,
        northing_usft=1004686.788,
        easting_usft=12852212.444,
        convergence_dms="-00 42 14.51",
        convergence_deg=-0.7040305555555555,
        scale_factor=1.00019267,
        source="llh_S2_2113.json",
    ),
    CrosscheckForward(
        point_id="S3",
        zone_code="2113",
        latitude=42.3314,
        longitude=-83.0458,
        northing_m=93204.175,
        easting_m=4108855.599,
        northing_ift=305787.975,
        easting_ift=13480497.371,
        northing_usft=305787.363,
        easting_usft=13480470.41,
        convergence_dms="00 53 56.00",
        convergence_deg=0.8988888888888888,
        scale_factor=0.99995325,
        source="llh_S3_2113.json",
    ),
    CrosscheckForward(
        point_id="S4",
        zone_code="2113",
        latitude=42.78,
        longitude=-86.05,
        northing_m=143555.78,
        easting_m=3862272.453,
        northing_ift=470983.529,
        easting_ift=12671497.55,
        northing_usft=470982.587,
        easting_usft=12671472.207,
        convergence_dms="-01 08 44.01",
        convergence_deg=-1.1455583333333332,
        scale_factor=0.99990855,
        source="llh_S4_2113.json",
    ),
    CrosscheckForward(
        point_id="C2",
        zone_code="2111",
        latitude=45.9,
        longitude=-84.72,
        northing_m=126655.312,
        easting_m=8176896.616,
        northing_ift=415535.799,
        easting_ift=26827088.635,
        northing_usft=415534.968,
        easting_usft=26827034.98,
        convergence_dms="01 38 52.66",
        convergence_deg=1.647961111111111,
        scale_factor=0.99992532,
        source="llh_C2_2111.json",
    ),
    CrosscheckForward(
        point_id="S2",
        zone_code="2112",
        latitude=44.252,
        longitude=-85.4012,
        northing_m=104463.069,
        easting_m=5917379.509,
        northing_ift=342726.604,
        easting_ift=19413974.768,
        northing_usft=342725.919,
        easting_usft=19413935.94,
        convergence_dms="-00 43 50.89",
        convergence_deg=-0.7308027777777778,
        scale_factor=0.99998497,
        source="llh_S2_2112.json",
    ),
    CrosscheckForward(
        point_id="NS",
        zone_code="2111",
        latitude=44.65,
        longitude=-85.5,
        northing_m=-13694.788,
        easting_m=8119017.252,
        northing_ift=-44930.408,
        easting_ift=26637195.709,
        northing_usft=-44930.318,
        easting_usft=26637142.435,
        convergence_dms="01 05 03.07",
        convergence_deg=1.084186111111111,
        scale_factor=1.00030493,
        source="llh_NS_2111.json",
    ),
    CrosscheckForward(
        point_id="NS",
        zone_code="2113",
        latitude=44.65,
        longitude=-85.5,
        northing_m=350565.501,
        easting_m=3910066.054,
        northing_ift=1150149.28,
        easting_ift=12828300.701,
        northing_usft=1150146.98,
        easting_usft=12828275.044,
        convergence_dms="-00 46 16.56",
        convergence_deg=-0.7712666666666668,
        scale_factor=1.00038446,
        source="llh_NS_2113.json",
    ),
)


CROSSCHECK_INVERSE: tuple[CrosscheckInverse, ...] = (

    CrosscheckInverse(
        point_id="N1",
        zone_code="2111",
        unit_code="m",
        northing=35935.015,
        easting=7952379.96,
        latitude=45.1050000005,
        longitude=-87.6050000034,
        source="spc_N1_2111_m.json",
    ),
    CrosscheckInverse(
        point_id="N1",
        zone_code="2111",
        unit_code="ift",
        northing=117897.031,
        easting=26090485.434,
        latitude=45.105000001,
        longitude=-87.6049999998,
        source="spc_N1_2111_ift.json",
    ),
    CrosscheckInverse(
        point_id="N1",
        zone_code="2111",
        unit_code="usft",
        northing=117896.795,
        easting=26090433.253,
        latitude=45.1050000004,
        longitude=-87.6049999999,
        source="spc_N1_2111_usft.json",
    ),
    CrosscheckInverse(
        point_id="N2",
        zone_code="2111",
        unit_code="m",
        northing=364265.841,
        easting=7884405.849,
        latitude=48.05,
        longitude=-88.5500000042,
        source="spc_N2_2111_m.json",
    ),
    CrosscheckInverse(
        point_id="N2",
        zone_code="2111",
        unit_code="ift",
        northing=1195097.904,
        easting=25867473.259,
        latitude=48.0500000013,
        longitude=-88.5499999996,
        source="spc_N2_2111_ift.json",
    ),
    CrosscheckInverse(
        point_id="N2",
        zone_code="2111",
        unit_code="usft",
        northing=1195095.513,
        easting=25867421.524,
        latitude=48.0499999991,
        longitude=-88.5499999998,
        source="spc_N2_2111_usft.json",
    ),
    CrosscheckInverse(
        point_id="N3",
        zone_code="2111",
        unit_code="m",
        northing=193687.687,
        easting=8203742.69,
        latitude=46.4952999999,
        longitude=-84.3452999954,
        source="spc_N3_2111_m.json",
    ),
    CrosscheckInverse(
        point_id="N3",
        zone_code="2111",
        unit_code="ift",
        northing=635458.291,
        easting=26915166.305,
        latitude=46.4953000008,
        longitude=-84.3452999984,
        source="spc_N3_2111_ift.json",
    ),
    CrosscheckInverse(
        point_id="N3",
        zone_code="2111",
        unit_code="usft",
        northing=635457.02,
        easting=26915112.474,
        latitude=46.4953000007,
        longitude=-84.3453000011,
        source="spc_N3_2111_usft.json",
    ),
    CrosscheckInverse(
        point_id="N4",
        zone_code="2111",
        unit_code="m",
        northing=261019.506,
        easting=7880914.336,
        latitude=47.121100004,
        longitude=-88.5693999965,
        source="spc_N4_2111_m.json",
    ),
    CrosscheckInverse(
        point_id="N4",
        zone_code="2111",
        unit_code="ift",
        northing=856363.207,
        easting=25856018.162,
        latitude=47.1210999995,
        longitude=-88.5693999993,
        source="spc_N4_2111_ift.json",
    ),
    CrosscheckInverse(
        point_id="N4",
        zone_code="2111",
        unit_code="usft",
        northing=856361.494,
        easting=25855966.45,
        latitude=47.1210999987,
        longitude=-88.5693999991,
        source="spc_N4_2111_usft.json",
    ),
    CrosscheckInverse(
        point_id="C1",
        zone_code="2112",
        unit_code="m",
        northing=33647.176,
        easting=5831772.715,
        latitude=43.6000000005,
        longitude=-86.4500000035,
        source="spc_C1_2112_m.json",
    ),
    CrosscheckInverse(
        point_id="C1",
        zone_code="2112",
        unit_code="ift",
        northing=110390.997,
        easting=19133112.583,
        latitude=43.5999999995,
        longitude=-86.4499999998,
        source="spc_C1_2112_ift.json",
    ),
    CrosscheckInverse(
        point_id="C1",
        zone_code="2112",
        unit_code="usft",
        northing=110390.776,
        easting=19133074.317,
        latitude=43.5999999989,
        longitude=-86.4499999989,
        source="spc_C1_2112_usft.json",
    ),
    CrosscheckInverse(
        point_id="C2",
        zone_code="2112",
        unit_code="m",
        northing=287134.307,
        easting=5972579.018,
        latitude=45.8999999963,
        longitude=-84.720000006,
        source="spc_C2_2112_m.json",
    ),
    CrosscheckInverse(
        point_id="C2",
        zone_code="2112",
        unit_code="ift",
        northing=942041.691,
        easting=19595075.52,
        latitude=45.9000000001,
        longitude=-84.7199999997,
        source="spc_C2_2112_ift.json",
    ),
    CrosscheckInverse(
        point_id="C2",
        zone_code="2112",
        unit_code="usft",
        northing=942039.807,
        easting=19595036.33,
        latitude=45.9000000003,
        longitude=-84.7199999991,
        source="spc_C2_2112_usft.json",
    ),
    CrosscheckInverse(
        point_id="C3",
        zone_code="2112",
        unit_code="m",
        northing=161494.864,
        easting=5900736.89,
        latitude=44.7631000028,
        longitude=-85.6206000058,
        source="spc_C3_2112_m.json",
    ),
    CrosscheckInverse(
        point_id="C3",
        zone_code="2112",
        unit_code="ift",
        northing=529838.792,
        easting=19359373.0,
        latitude=44.7631000011,
        longitude=-85.6206000007,
        source="spc_C3_2112_ift.json",
    ),
    CrosscheckInverse(
        point_id="C3",
        zone_code="2112",
        unit_code="usft",
        northing=529837.732,
        easting=19359334.281,
        latitude=44.7631000002,
        longitude=-85.6206000017,
        source="spc_C3_2112_usft.json",
    ),
    CrosscheckInverse(
        point_id="C4",
        zone_code="2112",
        unit_code="m",
        northing=109639.182,
        easting=6069157.798,
        latitude=44.3000000042,
        longitude=-83.4999999968,
        source="spc_C4_2112_m.json",
    ),
    CrosscheckInverse(
        point_id="C4",
        zone_code="2112",
        unit_code="ift",
        northing=359708.601,
        easting=19911935.032,
        latitude=44.3000000005,
        longitude=-83.4999999999,
        source="spc_C4_2112_ift.json",
    ),
    CrosscheckInverse(
        point_id="C4",
        zone_code="2112",
        unit_code="usft",
        northing=359707.881,
        easting=19911895.208,
        latitude=44.2999999989,
        longitude=-83.5000000004,
        source="spc_C4_2112_usft.json",
    ),
    CrosscheckInverse(
        point_id="S1",
        zone_code="2113",
        unit_code="m",
        northing=46781.481,
        easting=3818836.874,
        latitude=41.8999999987,
        longitude=-86.5500000009,
        source="spc_S1_2113_m.json",
    ),
    CrosscheckInverse(
        point_id="S1",
        zone_code="2113",
        unit_code="ift",
        northing=153482.55,
        easting=12528992.369,
        latitude=41.9000000009,
        longitude=-86.5500000002,
        source="spc_S1_2113_ift.json",
    ),
    CrosscheckInverse(
        point_id="S1",
        zone_code="2113",
        unit_code="usft",
        northing=153482.243,
        easting=12528967.311,
        latitude=41.9000000008,
        longitude=-86.5500000002,
        source="spc_S1_2113_usft.json",
    ),
    CrosscheckInverse(
        point_id="S2",
        zone_code="2113",
        unit_code="m",
        northing=306229.145,
        easting=3917362.188,
        latitude=44.2519999966,
        longitude=-85.4011999966,
        source="spc_S2_2113_m.json",
    ),
    CrosscheckInverse(
        point_id="S2",
        zone_code="2113",
        unit_code="ift",
        northing=1004688.797,
        easting=12852238.149,
        latitude=44.2519999995,
        longitude=-85.401199999,
        source="spc_S2_2113_ift.json",
    ),
    CrosscheckInverse(
        point_id="S2",
        zone_code="2113",
        unit_code="usft",
        northing=1004686.788,
        easting=12852212.444,
        latitude=44.2520000005,
        longitude=-85.401200001,
        source="spc_S2_2113_usft.json",
    ),
    CrosscheckInverse(
        point_id="S3",
        zone_code="2113",
        unit_code="m",
        northing=93204.175,
        easting=4108855.599,
        latitude=42.3314000023,
        longitude=-83.0457999962,
        source="spc_S3_2113_m.json",
    ),
    CrosscheckInverse(
        point_id="S3",
        zone_code="2113",
        unit_code="ift",
        northing=305787.975,
        easting=13480497.371,
        latitude=42.3314000003,
        longitude=-83.0458000001,
        source="spc_S3_2113_ift.json",
    ),
    CrosscheckInverse(
        point_id="S3",
        zone_code="2113",
        unit_code="usft",
        northing=305787.363,
        easting=13480470.41,
        latitude=42.3313999992,
        longitude=-83.0458000002,
        source="spc_S3_2113_usft.json",
    ),
    CrosscheckInverse(
        point_id="S4",
        zone_code="2113",
        unit_code="m",
        northing=143555.78,
        easting=3862272.453,
        latitude=42.7800000037,
        longitude=-86.0500000018,
        source="spc_S4_2113_m.json",
    ),
    CrosscheckInverse(
        point_id="S4",
        zone_code="2113",
        unit_code="ift",
        northing=470983.529,
        easting=12671497.55,
        latitude=42.7800000005,
        longitude=-86.0499999987,
        source="spc_S4_2113_ift.json",
    ),
    CrosscheckInverse(
        point_id="S4",
        zone_code="2113",
        unit_code="usft",
        northing=470982.587,
        easting=12671472.207,
        latitude=42.7800000005,
        longitude=-86.0499999987,
        source="spc_S4_2113_usft.json",
    ),
)


CROSSCHECK_GEOID: tuple[CrosscheckGeoid, ...] = (

    CrosscheckGeoid(
        point_id="N1",
        latitude=45.105,
        longitude=-87.605,
        geoid_height_m=-36.994,
        error_m=0.032,
        source="geoid_N1.json",
    ),
    CrosscheckGeoid(
        point_id="N2",
        latitude=48.05,
        longitude=-88.55,
        geoid_height_m=-34.777,
        error_m=0.061,
        source="geoid_N2.json",
    ),
    CrosscheckGeoid(
        point_id="N3",
        latitude=46.4953,
        longitude=-84.3453,
        geoid_height_m=-36.636,
        error_m=0.032,
        source="geoid_N3.json",
    ),
    CrosscheckGeoid(
        point_id="N4",
        latitude=47.1211,
        longitude=-88.5694,
        geoid_height_m=-33.796,
        error_m=0.034,
        source="geoid_N4.json",
    ),
    CrosscheckGeoid(
        point_id="C1",
        latitude=43.6,
        longitude=-86.45,
        geoid_height_m=-34.731,
        error_m=0.045,
        source="geoid_C1.json",
    ),
    CrosscheckGeoid(
        point_id="C2",
        latitude=45.9,
        longitude=-84.72,
        geoid_height_m=-35.396,
        error_m=0.034,
        source="geoid_C2.json",
    ),
    CrosscheckGeoid(
        point_id="C3",
        latitude=44.7631,
        longitude=-85.6206,
        geoid_height_m=-34.67,
        error_m=0.033,
        source="geoid_C3.json",
    ),
    CrosscheckGeoid(
        point_id="C4",
        latitude=44.3,
        longitude=-83.5,
        geoid_height_m=-35.254,
        error_m=0.041,
        source="geoid_C4.json",
    ),
    CrosscheckGeoid(
        point_id="S1",
        latitude=41.9,
        longitude=-86.55,
        geoid_height_m=-33.937,
        error_m=0.038,
        source="geoid_S1.json",
    ),
    CrosscheckGeoid(
        point_id="S2",
        latitude=44.252,
        longitude=-85.4012,
        geoid_height_m=-33.28,
        error_m=0.031,
        source="geoid_S2.json",
    ),
    CrosscheckGeoid(
        point_id="S3",
        latitude=42.3314,
        longitude=-83.0458,
        geoid_height_m=-34.547,
        error_m=0.031,
        source="geoid_S3.json",
    ),
    CrosscheckGeoid(
        point_id="S4",
        latitude=42.78,
        longitude=-86.05,
        geoid_height_m=-33.399,
        error_m=0.032,
        source="geoid_S4.json",
    ),
    CrosscheckGeoid(
        point_id="NS",
        latitude=44.65,
        longitude=-85.5,
        geoid_height_m=-34.137,
        error_m=0.037,
        source="geoid_NS.json",
    ),
)
