"""Test the .err reader at CELL CENTRES, where nearest-node anchoring is worst.

At fractional position 0.5 the nearest-node stencil is evaluated at the edge of
its range, x = 0.5. That is where the implementer found 114 Michigan cells whose
interpolated sigma goes NEGATIVE. A negative one-sigma is not a quantity, so
either NGS produces them too (and this is a disclosure problem) or our scheme is
wrong there (and it is a defect). NCAT settles it.
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
from decide_err_scheme import bilinear, biquad, fetch_sigma  # noqa: E402
from lead_check_vertcon import ERR, read_vertcon  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "err_centres"
OUT.mkdir(exist_ok=True)

MICHIGAN = (41.7, 47.4, -90.2, -82.5)


def main():
    g = read_vertcon(ERR)
    s, n, w, e = MICHIGAN
    r_lo = int((s - g["slat"]) / g["dlat"]) + 2
    r_hi = int((n - g["slat"]) / g["dlat"]) - 2
    c_lo = int((w + 360.0 - g["wlon"]) / g["dlon"]) + 2
    c_hi = int((e + 360.0 - g["wlon"]) / g["dlon"]) - 2

    centres = []
    negatives = []
    for r in range(r_lo, r_hi):
        for c in range(c_lo, c_hi):
            lat = g["slat"] + (r + 0.5) * g["dlat"]
            lon = g["wlon"] + (c + 0.5) * g["dlon"] - 360.0
            v = biquad(g, lat, lon, "nearest")
            centres.append((v, lat, lon))
            if v < 0:
                negatives.append((v, lat, lon))
    negatives.sort()
    print(f"{len(centres)} Michigan cell centres; "
          f"{len(negatives)} give a NEGATIVE sigma under nearest-node biquad")
    if negatives:
        print(f"  worst {negatives[0][0]:.6f} m at "
              f"{negatives[0][1]:.4f} N, {abs(negatives[0][2]):.4f} W")

    # The 12 worst negatives, plus 12 ordinary centres for contrast.
    sample = negatives[:12] + centres[::max(1, len(centres) // 12)][:12]

    rows = []
    for i, (v, lat, lon) in enumerate(sample):
        payload, body = fetch_sigma(lat, lon)
        (OUT / f"c{i:03d}.json").write_text(body, encoding="utf-8")
        truth = float(payload["sigOrthoht"])
        rec = {"lat": lat, "lon": lon, "ncat": truth,
               "biquad_nearest": biquad(g, lat, lon, "nearest"),
               "biquad_floor": biquad(g, lat, lon, "floor"),
               "bilinear": bilinear(g, lat, lon)}
        rows.append(rec)
        flag = "  <-- NEGATIVE" if rec["biquad_nearest"] < 0 else ""
        print(f"  {lat:8.4f},{lon:9.4f}  NCAT {truth:7.3f}   "
              f"near {rec['biquad_nearest']:+9.5f}  "
              f"floor {rec['biquad_floor']:+9.5f}  "
              f"bilin {rec['bilinear']:+9.5f}{flag}")
        time.sleep(0.3)

    (OUT / "records.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    print(f"\n=== residual vs NCAT sigma at cell centres, mm, n={len(rows)} ===")
    for k in ("biquad_nearest", "biquad_floor", "bilinear"):
        res = [abs(r[k] - r["ncat"]) * 1000.0 for r in rows]
        rounds = sum(1 for r in rows if round(r[k], 3) == round(r["ncat"], 3))
        rms = (sum(x * x for x in res) / len(res)) ** 0.5
        print(f"  {k:>16}: max {max(res):8.3f}  mean {sum(res)/len(res):7.3f}  "
              f"rms {rms:7.3f}  roundsToNCAT {rounds:2d}/{len(rows)}")


if __name__ == "__main__":
    main()
