"""Session lead's independent check of the biquadratic anchoring rule.

Does NOT import michspc's interpolators. Parses the GEOID18 tile directly and
implements both anchoring schemes from scratch, then scores each against the
frozen NGS geoid API anchors -- the same external truth amendment #8 used.

The question: is `row0 = int(row) - 1` (ships today) or `row0 = round(row) - 1`
(nearest-node) the scheme that matches NGS?
"""

from __future__ import annotations

import importlib.util
import struct
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    import sys
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses looks the module up by name
    spec.loader.exec_module(module)
    return module


def read_geoid(path: Path):
    raw = path.read_bytes()
    slat, wlon, dlat, dlon, nlat, nlon, ikind = struct.unpack_from("<4d3i", raw, 0)
    payload = raw[44:]
    assert len(payload) == nlat * nlon * 4, (len(payload), nlat * nlon * 4)
    values = struct.unpack(f"<{nlat * nlon}f", payload)
    return dict(slat=slat, wlon=wlon, dlat=dlat, dlon=dlon,
                nlat=nlat, nlon=nlon, ikind=ikind, values=values)


def lagrange3(v, x):
    v0, v1, v2 = v
    return (v0 * (x - 1.0) * (x - 2.0) / 2.0
            + v1 * x * (2.0 - x)
            + v2 * x * (x - 1.0) / 2.0)


def cell(g, r, c):
    return g["values"][r * g["nlon"] + c]


def frac_indices(g, lat, lon):
    east = lon + 360.0 if lon < 0 else lon
    row = (lat - g["slat"]) / g["dlat"]
    col = (east - g["wlon"]) / g["dlon"]
    return row, col


def biquad(g, lat, lon, anchor):
    row, col = frac_indices(g, lat, lon)
    if anchor == "floor":            # what ships today
        r0 = min(max(int(row) - 1, 0), g["nlat"] - 3)
        c0 = min(max(int(col) - 1, 0), g["nlon"] - 3)
    elif anchor == "nearest":        # nearest-node centring
        r0 = min(max(int(row + 0.5) - 1, 0), g["nlat"] - 3)
        c0 = min(max(int(col + 0.5) - 1, 0), g["nlon"] - 3)
    else:
        raise ValueError(anchor)
    dr, dc = row - r0, col - c0
    rows = [lagrange3([cell(g, r0 + i, c0 + j) for j in range(3)], dc)
            for i in range(3)]
    return lagrange3(rows, dr), dr, dc


def bilinear(g, lat, lon):
    row, col = frac_indices(g, lat, lon)
    r0 = min(int(row), g["nlat"] - 2)
    c0 = min(int(col), g["nlon"] - 2)
    dr, dc = row - r0, col - c0
    v00, v01 = cell(g, r0, c0), cell(g, r0, c0 + 1)
    v10, v11 = cell(g, r0 + 1, c0), cell(g, r0 + 1, c0 + 1)
    south = v00 + (v01 - v00) * dc
    north = v10 + (v11 - v10) * dc
    return south + (north - south) * dr


def main():
    g = read_geoid(REPO / "data" / "g2018u3.bin")
    print(f"GEOID18 header: SLAT={g['slat']} WLON={g['wlon']} "
          f"DLAT={g['dlat']:.12f} NLAT={g['nlat']} NLON={g['nlon']} "
          f"IKIND={g['ikind']}")

    anchors_mod = load_module(REPO / "tests" / "fixtures" / "geoid_anchors.py",
                              "geoid_anchors")
    anchors = anchors_mod.GEOID_ANCHORS
    print(f"{len(anchors)} frozen NGS geoid-API anchors\n")

    schemes = {
        "biquad-floor (SHIPS TODAY)": lambda la, lo: biquad(g, la, lo, "floor")[0],
        "biquad-nearest":             lambda la, lo: biquad(g, la, lo, "nearest")[0],
        "bilinear":                   lambda la, lo: bilinear(g, la, lo),
    }

    print(f"{'anchor':>22} {'NGS':>9} " + " ".join(f"{n.split()[0]:>16}" for n in schemes))
    stats = {n: [] for n in schemes}
    dr_range = []
    for a in anchors:
        row = f"{a.latitude:8.4f},{a.longitude:9.4f} {a.geoid_height_m:9.3f} "
        _, dr, dc = biquad(g, a.latitude, a.longitude, "floor")
        dr_range.append((dr, dc))
        for name, fn in schemes.items():
            v = fn(a.latitude, a.longitude)
            res_mm = (v - a.geoid_height_m) * 1000.0
            stats[name].append(abs(res_mm))
            row += f"{res_mm:>16.3f}"
        print(row)

    print("\n--- residual vs NGS published geoid height, mm ---")
    for name in schemes:
        s = stats[name]
        within = sum(1 for x in s if x <= 0.5)
        print(f"{name:>28}   max {max(s):8.3f}   mean {sum(s)/len(s):8.3f}   "
              f"within +/-0.5mm {within}/{len(s)}")

    print("\n--- where the shipped scheme puts the point in its stencil ---")
    drs = [d for d, _ in dr_range] + [c for _, c in dr_range]
    print(f"local coordinate range under floor anchoring: "
          f"[{min(drs):.4f}, {max(drs):.4f}]   (centre of a 3-node stencil is 1.0)")


if __name__ == "__main__":
    main()
