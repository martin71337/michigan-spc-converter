"""Where do negative sigmas actually occur? Offline scan, no network.

If they only appear at fractional position ~0.5 -- the stencil tie-break, which
is numerically unstable and measure-zero -- they are an artifact. If they appear
across ordinary positions, they are a property of the scheme and need handling.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decide_err_scheme import biquad  # noqa: E402
from lead_check_vertcon import ERR, read_vertcon  # noqa: E402

MICHIGAN = (41.7, 47.4, -90.2, -82.5)
FRACTIONS = [0.05, 0.15, 0.25, 0.35, 0.45, 0.5, 0.55, 0.65, 0.75, 0.85, 0.95]


def main():
    g = read_vertcon(ERR)
    s, n, w, e = MICHIGAN
    r_lo = int((s - g["slat"]) / g["dlat"]) + 2
    r_hi = int((n - g["slat"]) / g["dlat"]) - 2
    c_lo = int((w + 360.0 - g["wlon"]) / g["dlon"]) + 2
    c_hi = int((e + 360.0 - g["wlon"]) / g["dlon"]) - 2

    print(f"{'f_row':>6} {'f_col':>6} {'tested':>8} {'negative':>9} {'worst':>11}")
    total_neg = 0
    total = 0
    for fr in FRACTIONS:
        for fc in FRACTIONS:
            neg = 0
            worst = 0.0
            count = 0
            for r in range(r_lo, r_hi, 3):
                for c in range(c_lo, c_hi, 3):
                    lat = g["slat"] + (r + fr) * g["dlat"]
                    lon = g["wlon"] + (c + fc) * g["dlon"] - 360.0
                    v = biquad(g, lat, lon, "nearest")
                    count += 1
                    if v < 0:
                        neg += 1
                        worst = min(worst, v)
            total += count
            total_neg += neg
            if neg:
                print(f"{fr:6.2f} {fc:6.2f} {count:8d} {neg:9d} {worst:11.6f}")
    print(f"\ntotal sampled {total}, negative {total_neg} "
          f"({100.0 * total_neg / total:.4f}%)")


if __name__ == "__main__":
    main()
