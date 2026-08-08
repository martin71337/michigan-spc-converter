"""Decide the GEOID18 anchoring question with a DISCRIMINATING sample.

The structural fact this design exploits. For a fractional row ``row = k + f``:

    floor anchoring    r0 = int(row) - 1 = k - 1        -> local x = f + 1
    nearest anchoring  r0 = int(row + 0.5) - 1
                       f < 0.5:  r0 = k - 1             -> local x = f + 1   IDENTICAL
                       f >= 0.5: r0 = k                 -> local x = f       DIFFERENT

So the two schemes AGREE EXACTLY whenever f < 0.5 in both directions, and can
only differ when f >= 0.5. Adding points at random fractional positions wastes
roughly three quarters of them. This samples where the schemes actually diverge,
and inside the cells whose curvature makes a quadratic stencil choice matter.

Truth: NGS's own geoid API, which prints to 0.001 m (+/-0.5 mm on one figure).
The discriminator is therefore not any single point but the aggregate over many
deliberately-chosen ones.
"""

from __future__ import annotations

import json
import struct
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "geoid_decide"
OUT.mkdir(exist_ok=True)

MICHIGAN = (41.7, 47.4, -90.2, -82.5)  # S, N, W, E
TARGET_FRACTION = 0.90                 # deep in the upper half of the cell
N_POINTS = 120


def read_geoid():
    raw = (REPO / "data" / "g2018u3.bin").read_bytes()
    slat, wlon, dlat, dlon, nlat, nlon, ikind = struct.unpack_from("<4d3i", raw, 0)
    values = struct.unpack(f"<{nlat * nlon}f", raw[44:])
    return dict(slat=slat, wlon=wlon, dlat=dlat, dlon=dlon,
                nlat=nlat, nlon=nlon, values=values)


def cell(g, r, c):
    return g["values"][r * g["nlon"] + c]


def lagrange3(v, x):
    v0, v1, v2 = v
    return (v0 * (x - 1.0) * (x - 2.0) / 2.0
            + v1 * x * (2.0 - x)
            + v2 * x * (x - 1.0) / 2.0)


def biquad(g, lat, lon, anchor):
    east = lon + 360.0 if lon < 0 else lon
    row = (lat - g["slat"]) / g["dlat"]
    col = (east - g["wlon"]) / g["dlon"]
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


def curvature(g, r, c):
    """Magnitude of the local second difference: where a quadratic choice bites."""
    d2r = abs(cell(g, r - 1, c) - 2 * cell(g, r, c) + cell(g, r + 1, c))
    d2c = abs(cell(g, r, c - 1) - 2 * cell(g, r, c) + cell(g, r, c + 1))
    return d2r + d2c


def michigan_nodes(g):
    s, n, w, e = MICHIGAN
    r_lo = int((s - g["slat"]) / g["dlat"]) + 2
    r_hi = int((n - g["slat"]) / g["dlat"]) - 2
    c_lo = int((w + 360.0 - g["wlon"]) / g["dlon"]) + 2
    c_hi = int((e + 360.0 - g["wlon"]) / g["dlon"]) - 2
    for r in range(r_lo, r_hi):
        for c in range(c_lo, c_hi):
            yield r, c


def fetch(lat, lon):
    q = urllib.parse.urlencode({"lat": f"{lat:.8f}", "lon": f"{lon:.8f}",
                                "model": "14"})
    url = f"https://geodesy.noaa.gov/api/geoid/ght?{q}"
    with urllib.request.urlopen(url, timeout=90) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body), body


def main():
    g = read_geoid()
    print(f"GEOID18 {g['nlat']}x{g['nlon']}, spacing {g['dlat']:.10f} deg")

    ranked = sorted(michigan_nodes(g), key=lambda rc: curvature(g, *rc),
                    reverse=True)
    chosen = ranked[:N_POINTS]
    print(f"selected the {len(chosen)} highest-curvature Michigan cells; "
          f"curvature range {curvature(g, *chosen[-1]):.6f} to "
          f"{curvature(g, *chosen[0]):.6f} m")

    records = []
    for i, (r, c) in enumerate(chosen):
        lat = g["slat"] + (r + TARGET_FRACTION) * g["dlat"]
        lon = g["wlon"] + (c + TARGET_FRACTION) * g["dlon"] - 360.0
        payload, body = fetch(lat, lon)
        (OUT / f"pt{i:03d}.json").write_text(body, encoding="utf-8")
        truth = payload["geoidHeight"]
        rec = {
            "lat": lat, "lon": lon, "truth": truth,
            "floor": biquad(g, lat, lon, "floor"),
            "nearest": biquad(g, lat, lon, "nearest"),
            "curvature": curvature(g, r, c),
        }
        records.append(rec)
        if i % 20 == 0:
            print(f"  {i:3d}/{len(chosen)}  {lat:.5f},{lon:.5f}  NGS {truth:.3f}  "
                  f"floor {rec['floor']:.4f}  nearest {rec['nearest']:.4f}")
        time.sleep(0.25)

    (OUT / "records.json").write_text(json.dumps(records, indent=2),
                                      encoding="utf-8")

    print(f"\n=== {len(records)} discriminating points, fraction "
          f"{TARGET_FRACTION} in BOTH directions ===")
    for scheme in ("floor", "nearest"):
        res = [abs(r[scheme] - r["truth"]) * 1000.0 for r in records]
        signed = [(r[scheme] - r["truth"]) * 1000.0 for r in records]
        within = sum(1 for x in res if x <= 0.5)
        rounds = sum(1 for r in records
                     if round(r[scheme], 3) == round(r["truth"], 3))
        rms = (sum(x * x for x in res) / len(res)) ** 0.5
        print(f"  {scheme:>8}:  max {max(res):7.3f}  mean {sum(res)/len(res):6.3f}  "
              f"rms {rms:6.3f}  bias {sum(signed)/len(signed):+6.3f}  "
              f"within0.5mm {within:3d}/{len(res)}  roundsToNGS {rounds:3d}/{len(res)}")

    better = sum(1 for r in records
                 if abs(r["floor"] - r["truth"]) < abs(r["nearest"] - r["truth"]))
    worse = sum(1 for r in records
                if abs(r["floor"] - r["truth"]) > abs(r["nearest"] - r["truth"]))
    tied = len(records) - better - worse
    print(f"\n  head to head: floor better {better}, nearest better {worse}, "
          f"tied {tied}")


if __name__ == "__main__":
    main()
