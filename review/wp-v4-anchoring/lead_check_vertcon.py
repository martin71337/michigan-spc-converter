"""Session lead's independent VERTCON measurement.

Written from the format spec, importing nothing from michspc and nothing from
the measurement agent's scripts. Scores four schemes on both grids against the
frozen NCAT lattice.

The question this settles: GEOID18 measurably prefers the floor-anchored
biquadratic that ships today (max 0.595 mm vs 0.830 nearest-node, measured
against NGS's geoid API). Does VERTCON prefer the other one? If so the two NGS
products differ in stencil convention and the substrate must offer both.
"""

from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TRN = REPO / "data" / "vertcon_3.0_20190601.ngvd29.navd88.conus.oht.trn.b"
ERR = REPO / "data" / "vertcon_3.0_20190601.ngvd29.navd88.conus.oht.err.b"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_vertcon(path: Path):
    """Parse the marker-bracketed NGS .b format, validating every marker."""
    raw = path.read_bytes()
    (m0,) = struct.unpack_from("<i", raw, 0)
    slat, wlon, dlat, dlon, nlat, nlon, ikind = struct.unpack_from("<4d3i", raw, 4)
    (m1,) = struct.unpack_from("<i", raw, 48)
    if m0 != 44 or m1 != 44:
        raise SystemExit(f"header markers {m0}/{m1}, expected 44/44")

    offset = 52
    row_bytes = nlon * 4
    values = []
    bad = 0
    for _ in range(nlat):
        (a,) = struct.unpack_from("<i", raw, offset)
        rowvals = struct.unpack_from(f"<{nlon}f", raw, offset + 4)
        (b,) = struct.unpack_from("<i", raw, offset + 4 + row_bytes)
        if a != row_bytes or b != row_bytes:
            bad += 1
        values.extend(rowvals)
        offset += 8 + row_bytes

    return dict(slat=slat, wlon=wlon, dlat=dlat, dlon=dlon, nlat=nlat,
                nlon=nlon, ikind=ikind, values=values,
                consumed=offset, size=len(raw), bad_markers=bad)


def lagrange3(v, x):
    v0, v1, v2 = v
    return (v0 * (x - 1.0) * (x - 2.0) / 2.0
            + v1 * x * (2.0 - x)
            + v2 * x * (x - 1.0) / 2.0)


def cell(g, r, c):
    return g["values"][r * g["nlon"] + c]


def frac(g, lat, lon):
    east = lon + 360.0 if lon < 0 else lon
    return ((lat - g["slat"]) / g["dlat"], (east - g["wlon"]) / g["dlon"])


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


def nearest(g, lat, lon):
    row, col = frac(g, lat, lon)
    return cell(g, int(row + 0.5), int(col + 0.5))


def score(g, anchors, truth, label):
    schemes = {
        "biquad-floor (substrate today)": lambda a: biquad(g, a.latitude, a.longitude, "floor"),
        "biquad-nearest-node":            lambda a: biquad(g, a.latitude, a.longitude, "nearest"),
        "bilinear":                       lambda a: bilinear(g, a.latitude, a.longitude),
        "nearest":                        lambda a: nearest(g, a.latitude, a.longitude),
    }
    print(f"\n=== {label} ===")
    results = {}
    for name, fn in schemes.items():
        res = []
        rounds = 0
        worst = None
        for a in anchors:
            v = fn(a)
            d = (v - truth(a)) * 1000.0
            res.append(abs(d))
            if round(v, 3) == round(truth(a), 3):
                rounds += 1
            if worst is None or abs(d) > abs(worst[1]):
                worst = (a.name, d)
        results[name] = (max(res), sum(res) / len(res), rounds, worst)
        print(f"  {name:<32} max {max(res):8.4f} mm  mean {sum(res)/len(res):7.4f} mm  "
              f"rounds-to-NCAT {rounds}/{len(anchors)}  worst {worst[0]} {worst[1]:+.3f}")
    return results


def main():
    trn = read_vertcon(TRN)
    err = read_vertcon(ERR)
    for name, g in (("trn", trn), ("err", err)):
        print(f"{name}: SLAT={g['slat']} WLON={g['wlon']} DLAT={g['dlat']} "
              f"NLAT={g['nlat']} NLON={g['nlon']} IKIND={g['ikind']} "
              f"bad_markers={g['bad_markers']} consumed={g['consumed']} "
              f"size={g['size']} match={g['consumed'] == g['size']}")

    fx = load_module(REPO / "tests" / "fixtures" / "vertcon_anchors.py",
                     "vertcon_anchors")
    fwd = fx.NGVD29_TO_NAVD88_ANCHORS

    score(trn, fwd, lambda a: a.shift_m, "trn grid vs NCAT shift, 20 points")
    score(err, fwd, lambda a: a.sigma_m, "err grid vs NCAT sigma, 20 points")

    # The node check: 43.0 N / 84.5 W should be an exact grid node.
    row, col = frac(trn, 43.0, -84.5)
    print(f"\n43.0 N/84.5 W fractional index: row={row:.6f} col={col:.6f} "
          f"(exact node = integral)")
    print(f"  raw node value        {cell(trn, int(round(row)), int(round(col))):.8f} m")
    print(f"  biquad-floor          {biquad(trn, 43.0, -84.5, 'floor'):.8f} m")
    print(f"  biquad-nearest        {biquad(trn, 43.0, -84.5, 'nearest'):.8f} m")
    print(f"  200.000 + value  =    {200.0 + biquad(trn, 43.0, -84.5, 'floor'):.6f} "
          f"(NCAT 199.860)")


if __name__ == "__main__":
    main()
