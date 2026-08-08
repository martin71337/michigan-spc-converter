"""Replicate NOAA's own grid-row selection literally, then test it.

Transcribed from gov/noaa/ngs/grid/Vertcon.java (noaa-ngs/ncat-lib):

    double drow = (latitude - minlat) / (dlat / 2.0);
    int row2 = (int) drow + 1;
    int row = row2 % 2 != 0 ? (row2 + 1) / 2 - 1 : row2 / 2;
    row = row < 1 ? 1 : row;
    row = row > (height - 2) ? height - 2 : row;
    ...
    intpPoint[1] = (lat - minlat - dlat * (row - 1)) / dlat;
    getCells(gridfh, row - 1, col - 1, numRows, numCols);

Java's (int) truncates toward zero and its / on ints truncates too, so both are
reproduced exactly rather than with Python's floor semantics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lead_check_vertcon import ERR, TRN, lagrange3, read_vertcon  # noqa: E402


def java_int(x: float) -> int:
    """Java's (int) cast: truncate toward zero."""
    return int(x)


def java_div(a: int, b: int) -> int:
    """Java's integer division: truncate toward zero."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def noaa_index(value: float, minimum: float, delta: float, extent: int) -> int:
    """NOAA's getGridRow / getGridColumn, 1-based, transcribed literally."""
    d = (value - minimum) / (delta / 2.0)
    n2 = java_int(d) + 1
    n = java_div(n2 + 1, 2) - 1 if n2 % 2 != 0 else java_div(n2, 2)
    n = 1 if n < 1 else n
    n = extent - 2 if n > (extent - 2) else n
    return n


def noaa_value(g, lat: float, lon: float) -> float:
    east = lon + 360.0 if lon < 0 else lon
    row = noaa_index(lat, g["slat"], g["dlat"], g["nlat"])
    col = noaa_index(east, g["wlon"], g["dlon"], g["nlon"])
    # intpPoint, measured from the node BELOW the centred one
    y = (lat - g["slat"] - g["dlat"] * (row - 1)) / g["dlat"]
    x = (east - g["wlon"] - g["dlon"] * (col - 1)) / g["dlon"]
    # block starts at (row-1, col-1) in 1-based == (row-1, col-1) 0-based offset
    r0, c0 = row - 1, col - 1
    rows = [lagrange3([g["values"][(r0 + i) * g["nlon"] + (c0 + j)]
                       for j in range(3)], x) for i in range(3)]
    return lagrange3(rows, y)


def ours_nearest(g, lat, lon):
    east = lon + 360.0 if lon < 0 else lon
    row = (lat - g["slat"]) / g["dlat"]
    col = (east - g["wlon"]) / g["dlon"]
    r0 = min(max(int(row + 0.5) - 1, 0), g["nlat"] - 3)
    c0 = min(max(int(col + 0.5) - 1, 0), g["nlon"] - 3)
    dr, dc = row - r0, col - c0
    rows = [lagrange3([g["values"][(r0 + i) * g["nlon"] + (c0 + j)]
                       for j in range(3)], dc) for i in range(3)]
    return lagrange3(rows, dr)


def main():
    trn = read_vertcon(TRN)
    err = read_vertcon(ERR)

    # 1. Does NOAA's literal algorithm equal ours everywhere we sampled?
    print("=== NOAA literal vs our nearest-node, over a dense Michigan sweep ===")
    worst = 0.0
    worst_at = None
    checked = 0
    for ri in range(360, 480, 2):
        for ci in range(700, 850, 2):
            for fr, fc in ((0.13, 0.77), (0.5, 0.5), (0.9, 0.9), (0.5, 0.2)):
                lat = trn["slat"] + (ri + fr) * trn["dlat"]
                lon = trn["wlon"] + (ci + fc) * trn["dlon"] - 360.0
                a = noaa_value(trn, lat, lon)
                b = ours_nearest(trn, lat, lon)
                checked += 1
                if abs(a - b) > worst:
                    worst = abs(a - b)
                    worst_at = (round(lat, 4), round(lon, 4), fr, fc)
    print(f"  {checked} positions, max |NOAA - ours| = {worst:.12f} m")
    print(f"  worst at {worst_at}")

    # 2. The negative-sigma points, under NOAA's literal algorithm.
    print("\n=== the disputed points, NOAA's literal algorithm on .err ===")
    for lat, lon, ncat in [
        (42.475, -83.125, 0.011),
        (42.87, -83.81, None),
        (44.625, -88.275, 0.005),
        (43.375, -82.825, 0.001),
        (43.025, -86.275, 0.008),
    ]:
        n = noaa_value(err, lat, lon)
        o = ours_nearest(err, lat, lon)
        tag = f"NCAT {ncat}" if ncat is not None else "NCAT n/a"
        print(f"  {lat:8.3f},{lon:9.3f}  {tag:>10}   NOAA-literal {n:+.6f}   "
              f"ours {o:+.6f}   same={abs(n-o) < 1e-12}")


if __name__ == "__main__":
    main()
