# MCX - Martin Coordinate Exchange

Windows desktop tool for converting survey coordinates in Michigan. It reads a PNEZD file (point, northing, easting, elevation, description; no header row) and converts it between:

- the three Michigan SPCS 83 zones (North 2111, Central 2112, South 2113)
- the 19 Michigan SPCS2022 zones
- the three UTM zones over Michigan, 15N, 16N and 17N, on NAD 83(2011) or NATRF2022 (meters only)
- geodetic latitude/longitude (NAD 83(2011) or NATRF2022)

Conversions go between zones of the same datum, or to and from geodetic. Units are meters, international feet and, on SPCS 83 zones, US survey feet. Elevations can also be converted between NGVD 29 and NAVD 88 and between GEOID12B and GEOID18, and GNSS ellipsoid heights can be entered directly.

Each job writes a clean PNEZD file for CAD, an audit CSV (scale factor, convergence, elevation factor and combined factor per point) and a plain-text job record.

Not supported: UTM more than 4.8 degrees from a zone's central meridian, NAD 83 to NATRF2022 transformation, NAPGD2022 elevations, other states, NAD 27.

## Install

Download `mcx-<version>-setup.exe` from [Releases](https://github.com/martin71337/michigan-spc-converter/releases). Check it against `SHA256SUMS.txt` if you like.

## Accuracy

SPCS 83 math follows NOAA Manual NOS NGS 5 (`docs/NOAA_Manual_NOS_NGS_0005.pdf`). The SPCS2022 zones are built on NGS's pre-release definitions and NCAT v3, so treat them as provisional until NGS finalizes them. Check results against your own control before relying on them for a sealed survey.

## Run from source

Needs Python 3.14 and PySide6.

```bash
run.bat
```

```bash
py -m pytest
```

Design notes are in `docs/DESIGN.md`.
