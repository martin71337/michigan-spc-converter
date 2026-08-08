"""Re-analyse the captured discriminating points against more schemes.

No new network calls: reads geoid_decide/records.json (lat, lon, NGS truth).

Also answers the question the 20-anchor comparison raised: how many of the
frozen anchors actually sit where the two schemes DIFFER? If most have
fractional position < 0.5 the schemes are identical there and that comparison
was decided by a handful of points.
"""

from __future__ import annotations

import importlib.util
import json
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CAPTURE = HERE / "geoid18_120_discriminating_points.json"


def read_geoid():
    raw = (REPO / "data" / "g2018u3.bin").read_bytes()
    slat, wlon, dlat, dlon, nlat, nlon, ikind = struct.unpack_from("<4d3i", raw, 0)
    values = struct.unpack(f"<{nlat * nlon}f", raw[44:])
    return dict(slat=slat, wlon=wlon, dlat=dlat, dlon=dlon,
                nlat=nlat, nlon=nlon, values=values)


def cell(g, r, c):
    return g["values"][r * g["nlon"] + c]


def frac(g, lat, lon):
    east = lon + 360.0 if lon < 0 else lon
    return ((lat - g["slat"]) / g["dlat"], (east - g["wlon"]) / g["dlon"])


def lagrange3(v, x):
    v0, v1, v2 = v
    return (v0 * (x - 1.0) * (x - 2.0) / 2.0 + v1 * x * (2.0 - x)
            + v2 * x * (x - 1.0) / 2.0)


def lagrange4(v, x):
    """Cubic through four equally spaced points at x = 0,1,2,3."""
    v0, v1, v2, v3 = v
    return (v0 * (x - 1) * (x - 2) * (x - 3) / -6.0
            + v1 * x * (x - 2) * (x - 3) / 2.0
            + v2 * x * (x - 1) * (x - 3) / -2.0
            + v3 * x * (x - 1) * (x - 2) / 6.0)


def biquad(g, lat, lon, anchor):
    row, col = frac(g, lat, lon)
    if anchor == "floor":
        r0 = min(max(int(row) - 1, 0), g["nlat"] - 3)
        c0 = min(max(int(col) - 1, 0), g["nlon"] - 3)
    else:
        r0 = min(max(int(row + 0.5) - 1, 0), g["nlat"] - 3)
        c0 = min(max(int(col + 0.5) - 1, 0), g["nlon"] - 3)
    dr, dc = row - r0, col - c0
    rows = [lagrange3([cell(g, r0 + i, c0 + j) for j in range(3)], dc)
            for i in range(3)]
    return lagrange3(rows, dr)


def bicubic(g, lat, lon):
    """4x4 Lagrange, stencil straddling the containing cell (x in [1,2])."""
    row, col = frac(g, lat, lon)
    r0 = min(max(int(row) - 1, 0), g["nlat"] - 4)
    c0 = min(max(int(col) - 1, 0), g["nlon"] - 4)
    dr, dc = row - r0, col - c0
    rows = [lagrange4([cell(g, r0 + i, c0 + j) for j in range(4)], dc)
            for i in range(4)]
    return lagrange4(rows, dr)


def bilinear(g, lat, lon):
    row, col = frac(g, lat, lon)
    r0 = min(int(row), g["nlat"] - 2)
    c0 = min(int(col), g["nlon"] - 2)
    dr, dc = row - r0, col - c0
    v00, v01 = cell(g, r0, c0), cell(g, r0, c0 + 1)
    v10, v11 = cell(g, r0 + 1, c0), cell(g, r0 + 1, c0 + 1)
    s = v00 + (v01 - v00) * dc
    n = v10 + (v11 - v10) * dc
    return s + (n - s) * dr


SCHEMES = {
    "biquad-floor (SHIPS)": lambda g, la, lo: biquad(g, la, lo, "floor"),
    "biquad-nearest": lambda g, la, lo: biquad(g, la, lo, "nearest"),
    "bicubic-4x4": lambda g, la, lo: bicubic(g, la, lo),
    "bilinear": lambda g, la, lo: bilinear(g, la, lo),
}


def report(g, points, label):
    print(f"\n=== {label}, n={len(points)} ===")
    for name, fn in SCHEMES.items():
        res, signed, rounds = [], [], 0
        for p in points:
            v = fn(g, p["lat"], p["lon"])
            d = (v - p["truth"]) * 1000.0
            res.append(abs(d))
            signed.append(d)
            if round(v, 3) == round(p["truth"], 3):
                rounds += 1
        rms = (sum(x * x for x in res) / len(res)) ** 0.5
        print(f"  {name:<22} max {max(res):7.3f}  mean {sum(res)/len(res):6.3f}  "
              f"rms {rms:6.3f}  bias {sum(signed)/len(signed):+6.3f}  "
              f"roundsToNGS {rounds:3d}/{len(res)}")


def main():
    g = read_geoid()
    records = json.loads(CAPTURE.read_text(encoding="utf-8"))
    report(g, records, "120 discriminating points (fraction 0.90, high curvature)")

    # Now the frozen 20. How many even sit where the schemes differ?
    spec = importlib.util.spec_from_file_location(
        "geoid_anchors", REPO / "tests" / "fixtures" / "geoid_anchors.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["geoid_anchors"] = mod
    spec.loader.exec_module(mod)

    anchors = [{"lat": a.latitude, "lon": a.longitude,
                "truth": a.geoid_height_m} for a in mod.GEOID_ANCHORS]
    report(g, anchors, "the 20 frozen NGS geoid-API anchors")

    differ = 0
    print("\n  fractional position of each frozen anchor "
          "(schemes are IDENTICAL when both < 0.5):")
    for a in mod.GEOID_ANCHORS:
        row, col = frac(g, a.latitude, a.longitude)
        fr, fc = row % 1.0, col % 1.0
        d = fr >= 0.5 or fc >= 0.5
        differ += d
        print(f"    {a.latitude:8.4f},{a.longitude:9.4f}  f_row {fr:.3f}  "
              f"f_col {fc:.3f}  {'DIFFERS' if d else 'identical'}")
    print(f"\n  {differ} of {len(mod.GEOID_ANCHORS)} anchors can tell the two "
          f"schemes apart at all.")


if __name__ == "__main__":
    main()
