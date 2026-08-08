"""Settle how the .err grid is actually read, at the points that discriminate.

The 20-point lattice agreed with nearest-node biquadratic to 0.472 mm, but that
lattice was chosen geographically. A counterexample turned up at
42.475 N / 83.125 W: our reader gives -0.009652 m and NCAT returns +0.011 m.

So sample where the schemes DISAGREE WITH EACH OTHER most, and ask NCAT there.
That is the population that decides it; agreeing points carry no information.
"""

from __future__ import annotations

import json
import struct
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lead_check_vertcon import ERR, read_vertcon  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "err_decide"
OUT.mkdir(exist_ok=True)

MICHIGAN = (41.7, 47.4, -90.2, -82.5)
N_POINTS = 40


def cell(g, r, c):
    return g["values"][r * g["nlon"] + c]


def lagrange3(v, x):
    v0, v1, v2 = v
    return (v0 * (x - 1.0) * (x - 2.0) / 2.0 + v1 * x * (2.0 - x)
            + v2 * x * (x - 1.0) / 2.0)


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


def fetch_sigma(lat, lon):
    q = urllib.parse.urlencode({
        "lat": f"{lat:.8f}", "lon": f"{lon:.8f}", "orthoHt": "200.000",
        "inDatum": "NAD83(2011)", "outDatum": "NAD83(2011)",
        "inVertDatum": "NGVD29", "outVertDatum": "NAVD88"})
    url = f"https://geodesy.noaa.gov/api/ncat/llh?{q}"
    with urllib.request.urlopen(url, timeout=90) as r:
        body = r.read().decode("utf-8")
    return json.loads(body), body


def main():
    g = read_vertcon(ERR)
    s, n, w, e = MICHIGAN
    r_lo = int((s - g["slat"]) / g["dlat"]) + 2
    r_hi = int((n - g["slat"]) / g["dlat"]) - 2
    c_lo = int((w + 360.0 - g["wlon"]) / g["dlon"]) + 2
    c_hi = int((e + 360.0 - g["wlon"]) / g["dlon"]) - 2

    # Probe at fraction 0.9 in both directions, where the two anchorings differ,
    # and rank by how far apart the candidate schemes are from each other.
    candidates = []
    for r in range(r_lo, r_hi):
        for c in range(c_lo, c_hi):
            lat = g["slat"] + (r + 0.9) * g["dlat"]
            lon = g["wlon"] + (c + 0.9) * g["dlon"] - 360.0
            near = biquad(g, lat, lon, "nearest")
            bil = bilinear(g, lat, lon)
            candidates.append((abs(near - bil), lat, lon))
    candidates.sort(reverse=True)
    chosen = candidates[:N_POINTS]
    print(f"{len(chosen)} points where nearest-biquad and bilinear disagree most "
          f"({chosen[-1][0]*1000:.1f} to {chosen[0][0]*1000:.1f} mm apart)\n")

    rows = []
    for i, (_, lat, lon) in enumerate(chosen):
        payload, body = fetch_sigma(lat, lon)
        (OUT / f"p{i:03d}.json").write_text(body, encoding="utf-8")
        truth = float(payload["sigOrthoht"])
        rec = {
            "lat": lat, "lon": lon, "ncat": truth,
            "biquad_nearest": biquad(g, lat, lon, "nearest"),
            "biquad_floor": biquad(g, lat, lon, "floor"),
            "bilinear": bilinear(g, lat, lon),
        }
        rows.append(rec)
        print(f"  {lat:8.4f},{lon:9.4f}  NCAT {truth:7.3f}   "
              f"near {rec['biquad_nearest']:+9.5f}  "
              f"floor {rec['biquad_floor']:+9.5f}  "
              f"bilin {rec['bilinear']:+9.5f}")
        time.sleep(0.3)

    (OUT / "records.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    print(f"\n=== residual vs NCAT sigma, mm, n={len(rows)} ===")
    for k in ("biquad_nearest", "biquad_floor", "bilinear"):
        res = [abs(r[k] - r["ncat"]) * 1000.0 for r in rows]
        rounds = sum(1 for r in rows if round(r[k], 3) == round(r["ncat"], 3))
        neg = sum(1 for r in rows if r[k] < 0)
        rms = (sum(x * x for x in res) / len(res)) ** 0.5
        print(f"  {k:>16}: max {max(res):8.3f}  mean {sum(res)/len(res):7.3f}  "
              f"rms {rms:7.3f}  roundsToNCAT {rounds:2d}/{len(rows)}  negatives {neg}")


if __name__ == "__main__":
    main()
