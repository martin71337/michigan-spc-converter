"""NGS NCAT results, captured once and frozen. Verification anchors.

Every value below was computed by the National Geodetic Survey's own Coordinate
Conversion and Transformation Tool (NCAT) and captured verbatim from its API:

    https://geodesy.noaa.gov/api/ncat/llh
        ?lat=<lat>&lon=<lon>
        &inDatum=nad83(2011)&outDatum=nad83(2011)&spcZone=<zone>

Captured 2026-08-05. The generator script is not part of the repository; these
values are the artifact. **No test touches the network** - that is the point of
freezing them.

Input and output datum are set to the same realization so NCAT performs a pure
coordinate *conversion* with no datum transformation. The SPCS 83 mapping
equations are realization-independent, so these anchors test our projection
mathematics and nothing else.

The lattice is 3x3 per zone, spanning each zone's latitude band (where the
Lambert scale factor varies) and its longitude range (where convergence varies),
with the middle column placed exactly on the central meridian - where the
easting must come out to the zone's false easting exactly, and the convergence
must be zero.

Precision NCAT prints, which sets the tolerance a value can be held to:
    northing, easting   0.001 m
    convergence         0.01 arc second
    grid scale factor   8 decimal places
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NcatAnchor:
    """One NCAT result, verbatim."""

    zone_code: str
    latitude: float
    longitude: float
    """Decimal degrees, negative west - the convention NCAT uses and we use."""

    northing_m: float
    easting_m: float
    northing_ift: float
    easting_ift: float
    northing_usft: float
    easting_usft: float
    convergence_dms: str
    convergence_deg: float
    scale_factor: float


# Precision NCAT prints each quantity to.
NCAT_PRINTED = {
    "linear_m": 0.001,
    "linear_ft": 0.001,
    "convergence_arcsec": 0.01,
    "scale_factor_dp": 8,
}


NCAT_ANCHORS: tuple[NcatAnchor, ...] = (

    NcatAnchor(
        zone_code="2111",
        latitude=45.3,
        longitude=-90.1,
        northing_m=62180.452,
        easting_m=7756903.663,
        northing_ift=204004.108,
        easting_ift=25449158.999,
        northing_usft=204003.7,
        easting_usft=25449108.101,
        convergence_dms="-02 14 26.34",
        convergence_deg=-2.24065,
        scale_factor=1.00004935,
    ),
    NcatAnchor(
        zone_code="2111",
        latitude=45.3,
        longitude=-87.0,
        northing_m=57426.499,
        easting_m=8000000.0,
        northing_ift=188407.147,
        easting_ift=26246719.16,
        northing_usft=188406.771,
        easting_usft=26246666.667,
        convergence_dms="00 00 00.00",
        convergence_deg=0.0,
        scale_factor=1.00004935,
    ),
    NcatAnchor(
        zone_code="2111",
        latitude=45.3,
        longitude=-83.6,
        northing_m=63144.946,
        easting_m=8266607.998,
        northing_ift=207168.458,
        easting_ift=27121417.317,
        northing_usft=207168.044,
        easting_usft=27121363.074,
        convergence_dms="02 27 26.95",
        convergence_deg=2.4574861111111113,
        scale_factor=1.00004935,
    ),
    NcatAnchor(
        zone_code="2111",
        latitude=46.75,
        longitude=-90.1,
        northing_m=223217.613,
        easting_m=7763204.507,
        northing_ift=732341.249,
        easting_ift=25469831.06,
        northing_usft=732339.784,
        easting_usft=25469780.12,
        convergence_dms="-02 14 26.34",
        convergence_deg=-2.24065,
        scale_factor=0.99993571,
    ),
    NcatAnchor(
        zone_code="2111",
        latitude=46.75,
        longitude=-87.0,
        northing_m=218586.877,
        easting_m=8000000.0,
        northing_ift=717148.548,
        easting_ift=26246719.16,
        northing_usft=717147.114,
        easting_usft=26246666.667,
        convergence_dms="00 00 00.00",
        convergence_deg=0.0,
        scale_factor=0.99993571,
    ),
    NcatAnchor(
        zone_code="2111",
        latitude=46.75,
        longitude=-83.6,
        northing_m=224157.108,
        easting_m=8259697.752,
        northing_ift=735423.582,
        easting_ift=27098745.907,
        northing_usft=735422.112,
        easting_usft=27098691.709,
        convergence_dms="02 27 26.95",
        convergence_deg=2.4574861111111113,
        scale_factor=0.99993571,
    ),
    NcatAnchor(
        zone_code="2111",
        latitude=48.15,
        longitude=-90.1,
        northing_m=378771.164,
        easting_m=7769290.796,
        northing_ift=1242687.545,
        easting_ift=25489799.199,
        northing_usft=1242685.06,
        easting_usft=25489748.219,
        convergence_dms="-02 14 26.34",
        convergence_deg=-2.24065,
        scale_factor=1.00043714,
    ),
    NcatAnchor(
        zone_code="2111",
        latitude=48.15,
        longitude=-87.0,
        northing_m=374259.451,
        easting_m=8000000.0,
        northing_ift=1227885.338,
        easting_ift=26246719.16,
        northing_usft=1227882.883,
        easting_usft=26246666.667,
        convergence_dms="00 00 00.00",
        convergence_deg=0.0,
        scale_factor=1.00043714,
    ),
    NcatAnchor(
        zone_code="2111",
        latitude=48.15,
        longitude=-83.6,
        northing_m=379686.512,
        easting_m=8253022.813,
        northing_ift=1245690.655,
        easting_ift=27076846.499,
        northing_usft=1245688.163,
        easting_usft=27076792.346,
        convergence_dms="02 27 26.95",
        convergence_deg=2.4574861111111113,
        scale_factor=1.00043714,
    ),
    NcatAnchor(
        zone_code="2112",
        latitude=43.7,
        longitude=-86.4,
        northing_m=44653.597,
        easting_m=5836087.863,
        northing_ift=146501.301,
        easting_ift=19147269.893,
        northing_usft=146501.008,
        easting_usft=19147231.599,
        convergence_dms="-01 26 10.90",
        convergence_deg=-1.4363611111111112,
        scale_factor=1.00014571,
    ),
    NcatAnchor(
        zone_code="2112",
        latitude=43.7,
        longitude=-84.36666666666667,
        northing_m=42598.912,
        easting_m=6000000.0,
        northing_ift=139760.212,
        easting_ift=19685039.37,
        northing_usft=139759.932,
        easting_usft=19685000.0,
        convergence_dms="00 00 00.00",
        convergence_deg=0.0,
        scale_factor=1.00014571,
    ),
    NcatAnchor(
        zone_code="2112",
        latitude=43.7,
        longitude=-83.1,
        northing_m=43396.295,
        easting_m=6102115.745,
        northing_ift=142376.295,
        easting_ift=20020064.78,
        northing_usft=142376.01,
        easting_usft=20020024.74,
        convergence_dms="00 53 41.22",
        convergence_deg=0.8947833333333333,
        scale_factor=1.00014571,
    ),
    NcatAnchor(
        zone_code="2112",
        latitude=44.8,
        longitude=-86.4,
        northing_m=166844.09,
        easting_m=5839151.728,
        northing_ift=547388.747,
        easting_ift=19157321.943,
        northing_usft=547387.652,
        easting_usft=19157283.629,
        convergence_dms="-01 26 10.90",
        convergence_deg=-1.4363611111111112,
        scale_factor=0.99991582,
    ),
    NcatAnchor(
        zone_code="2112",
        latitude=44.8,
        longitude=-84.36666666666667,
        northing_m=164827.812,
        easting_m=6000000.0,
        northing_ift=540773.662,
        easting_ift=19685039.37,
        northing_usft=540772.581,
        easting_usft=19685000.0,
        convergence_dms="00 00 00.00",
        convergence_deg=0.0,
        scale_factor=0.99991582,
    ),
    NcatAnchor(
        zone_code="2112",
        latitude=44.8,
        longitude=-83.1,
        northing_m=165610.29,
        easting_m=6100206.986,
        northing_ift=543340.845,
        easting_ift=20013802.446,
        northing_usft=543339.759,
        easting_usft=20013762.419,
        convergence_dms="00 53 41.22",
        convergence_deg=0.8947833333333333,
        scale_factor=0.99991582,
    ),
    NcatAnchor(
        zone_code="2112",
        latitude=45.85,
        longitude=-86.4,
        northing_m=283496.497,
        easting_m=5842076.728,
        northing_ift=930106.618,
        easting_ift=19166918.4,
        northing_usft=930104.758,
        easting_usft=19166880.067,
        convergence_dms="-01 26 10.90",
        convergence_deg=-1.4363611111111112,
        scale_factor=1.00003816,
    ),
    NcatAnchor(
        zone_code="2112",
        latitude=45.85,
        longitude=-84.36666666666667,
        northing_m=281516.885,
        easting_m=6000000.0,
        northing_ift=923611.828,
        easting_ift=19685039.37,
        northing_usft=923609.981,
        easting_usft=19685000.0,
        convergence_dms="00 00 00.00",
        convergence_deg=0.0,
        scale_factor=1.00003816,
    ),
    NcatAnchor(
        zone_code="2112",
        latitude=45.85,
        longitude=-83.1,
        northing_m=282285.133,
        easting_m=6098384.738,
        northing_ift=926132.327,
        easting_ift=20007823.942,
        northing_usft=926130.475,
        easting_usft=20007783.926,
        convergence_dms="00 53 41.22",
        convergence_deg=0.8947833333333333,
        scale_factor=1.00003816,
    ),
    NcatAnchor(
        zone_code="2113",
        latitude=41.75,
        longitude=-86.7,
        northing_m=30459.967,
        easting_m=3805931.93,
        northing_ift=99934.276,
        easting_ift=12486653.313,
        northing_usft=99934.076,
        easting_usft=12486628.34,
        convergence_dms="-01 35 16.45",
        convergence_deg=-1.5879027777777779,
        scale_factor=1.0001012,
    ),
    NcatAnchor(
        zone_code="2113",
        latitude=41.75,
        longitude=-84.36666666666667,
        northing_m=27770.583,
        easting_m=4000000.0,
        northing_ift=91110.837,
        easting_ift=13123359.58,
        northing_usft=91110.654,
        easting_usft=13123333.333,
        convergence_dms="00 00 00.00",
        convergence_deg=0.0,
        scale_factor=1.0001012,
    ),
    NcatAnchor(
        zone_code="2113",
        latitude=41.75,
        longitude=-82.5,
        northing_m=29491.829,
        easting_m=4155261.611,
        northing_ift=96757.968,
        easting_ift=13632748.069,
        northing_usft=96757.774,
        easting_usft=13632720.803,
        convergence_dms="01 16 13.16",
        convergence_deg=1.2703222222222221,
        scale_factor=1.0001012,
    ),
    NcatAnchor(
        zone_code="2113",
        latitude=42.95,
        longitude=-86.7,
        northing_m=163700.655,
        easting_m=3809625.523,
        northing_ift=537075.639,
        easting_ift=12498771.4,
        northing_usft=537074.564,
        easting_usft=12498746.403,
        convergence_dms="-01 35 16.45",
        convergence_deg=-1.5879027777777779,
        scale_factor=0.99990752,
    ),
    NcatAnchor(
        zone_code="2113",
        latitude=42.95,
        longitude=-84.36666666666667,
        northing_m=161062.456,
        easting_m=4000000.0,
        northing_ift=528420.131,
        easting_ift=13123359.58,
        northing_usft=528419.075,
        easting_usft=13123333.333,
        convergence_dms="00 00 00.00",
        convergence_deg=0.0,
        scale_factor=0.99990752,
    ),
    NcatAnchor(
        zone_code="2113",
        latitude=42.95,
        longitude=-82.5,
        northing_m=162750.942,
        easting_m=4152306.601,
        northing_ift=533959.784,
        easting_ift=13623053.152,
        northing_usft=533958.716,
        easting_usft=13623025.906,
        convergence_dms="01 16 13.16",
        convergence_deg=1.2703222222222221,
        scale_factor=0.99990752,
    ),
    NcatAnchor(
        zone_code="2113",
        latitude=44.15,
        longitude=-86.7,
        northing_m=296972.632,
        easting_m=3813319.983,
        northing_ift=974319.658,
        easting_ift=12510892.333,
        northing_usft=974317.709,
        easting_usft=12510867.311,
        convergence_dms="-01 35 16.45",
        convergence_deg=-1.5879027777777779,
        scale_factor=1.00015146,
    ),
    NcatAnchor(
        zone_code="2113",
        latitude=44.15,
        longitude=-84.36666666666667,
        northing_m=294385.631,
        easting_m=4000000.0,
        northing_ift=965832.122,
        easting_ift=13123359.58,
        northing_usft=965830.19,
        easting_usft=13123333.333,
        convergence_dms="00 00 00.00",
        convergence_deg=0.0,
        scale_factor=1.00015146,
    ),
    NcatAnchor(
        zone_code="2113",
        latitude=44.15,
        longitude=-82.5,
        northing_m=296041.35,
        easting_m=4149350.896,
        northing_ift=971264.27,
        easting_ift=13613355.959,
        northing_usft=971262.328,
        easting_usft=13613328.732,
        convergence_dms="01 16 13.16",
        convergence_deg=1.2703222222222221,
        scale_factor=1.00015146,
    ),
)
