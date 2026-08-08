"""Verify the plan 2.7 window figures, the zero-crossing, and the sentinel scan."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lead_check_vertcon import ERR, TRN, read_vertcon  # noqa: E402


def window_indices(g, south, north, west, east):
    """Node indices whose position lies inside the window."""
    for r in range(g["nlat"]):
        lat = g["slat"] + r * g["dlat"]
        if not (south <= lat <= north):
            continue
        for c in range(g["nlon"]):
            lon = g["wlon"] + c * g["dlon"] - 360.0
            if west <= lon <= east:
                yield r, c, lat, lon


def main():
    trn = read_vertcon(TRN)
    err = read_vertcon(ERR)

    # plan 2.7's Michigan window
    S, N, W, E = 41.6, 48.4, -90.6, -82.2

    for label, g, plan_min, plan_max in (
        ("trn", trn, -0.411640, +0.348303),
        ("err", err, +0.000004, +0.365599),
    ):
        vals = []
        neg = pos = zero = 0
        lo = hi = None
        for r, c, lat, lon in window_indices(g, S, N, W, E):
            v = g["values"][r * g["nlon"] + c]
            vals.append(v)
            if v < 0:
                neg += 1
            elif v > 0:
                pos += 1
            else:
                zero += 1
            if lo is None or v < lo[0]:
                lo = (v, lat, lon)
            if hi is None or v > hi[0]:
                hi = (v, lat, lon)
        print(f"\n{label}: {len(vals)} nodes in the Michigan window")
        print(f"  min {lo[0]:+.6f} at {lo[1]:.2f} N, {abs(lo[2]):.2f} W   "
              f"plan 2.7 says {plan_min:+.6f}   match={abs(lo[0]-plan_min) < 5e-7}")
        print(f"  max {hi[0]:+.6f} at {hi[1]:.2f} N, {abs(hi[2]):.2f} W   "
              f"plan 2.7 says {plan_max:+.6f}   match={abs(hi[0]-plan_max) < 5e-7}")
        print(f"  sign census: {neg} negative, {pos} positive, {zero} exactly zero")

    # Whole-file scan: non-finite values and the sentinels the plan says are absent.
    print("\n--- whole-file scan, both grids ---")
    for label, g in (("trn", trn), ("err", err)):
        nonfinite = sum(1 for v in g["values"] if not math.isfinite(v))
        zeros = sum(1 for v in g["values"] if v == 0.0)
        sentinels = {
            s: sum(1 for v in g["values"] if abs(v - s) < 1e-9)
            for s in (-88.8888, 9999.0, -9999.0, 999.0)
        }
        print(f"  {label}: non-finite {nonfinite}   exact zeros {zeros}   "
              f"sentinels {sentinels}")

    # The two headers must be identical, or a pair could mismatch silently.
    keys = ("slat", "wlon", "dlat", "dlon", "nlat", "nlon", "ikind")
    same = all(trn[k] == err[k] for k in keys)
    print(f"\nheaders identical across the pair: {same}")


if __name__ == "__main__":
    main()
