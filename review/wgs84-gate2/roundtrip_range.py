"""Measure HTDP's round-trip non-closure over the observation dates the job
record claims (DESIGN.md #70, interim gate 2 finding L3).

Run from the repository root:  python3 review/wgs84-gate2/roundtrip_range.py

Through michspc.spc.htdp, which reproduces NGS HTDP v3.6.0's printed output on
every frozen record (W1, interim gate 1), so this measures HTDP's own
arithmetic, unrounded. A position is carried out and back both ways
(to NAD 83 and back, and from NAD 83 and back) for every in-box position of
W0's lattice (review/wgs84-w0/htdp_truth.json), at heights 0 and 600 m
(Michigan's highest ground is about 603 m), for all five frames.

Dates: the Helmert runs on the calendar-year fraction and the velocity on
whole days in Julian years, so the non-closure has a within-year sawtooth that
peaks at the year's ends. Every year from FIRST to LAST is therefore sampled
on 1 and 2 January, 30 June and 1 July, and 30 and 31 December; a separate
daily sweep at the box corners (measured by the lead, 2026-10-21) confirmed
the worst days of each year are at its ends.

Writes review/wgs84-gate2/roundtrip_range_output.txt. Deterministic.
"""
import datetime
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from michspc.spc import htdp  # noqa: E402

FIRST, LAST = datetime.date(1990, 1, 1), datetime.date(2035, 12, 31)
FRAMES = (htdp.WGS84_G1762, htdp.WGS84_G2139, htdp.WGS84_G2296, htdp.ITRF2014, htdp.ITRF2020)


def _neu(a, b):
    # Metres on a sphere of the local radii: a measurement of a millimetre-
    # scale difference, where the radius approximation costs nothing.
    dn = (b[0] - a[0]) * math.pi / 180.0 * 6367000.0
    de = (b[1] - a[1]) * math.pi / 180.0 * 6388000.0 * math.cos(math.radians(a[0]))
    return abs(dn), abs(de), abs(b[2] - a[2])


def main() -> None:
    truth = json.loads((REPO / "review/wgs84-w0/htdp_truth.json").read_text(encoding="utf-8"))
    positions = [(float(p["lat"]), float(p["lon_east"])) for p in truth["lattice"] if p["in_box"]]
    dates = [
        datetime.date(year, month, day)
        for year in range(FIRST.year, LAST.year + 1)
        for month, day in ((1, 1), (1, 2), (6, 30), (7, 1), (12, 30), (12, 31))
    ]
    worst = [0.0, 0.0, 0.0]
    where = [None, None, None]
    count = 0
    for date in dates:
        epoch = htdp.ObservationEpoch(date)
        for lat, lon in positions:
            for height in (0.0, 600.0):
                for frame in FRAMES:
                    start = (lat, lon, height)
                    for out, back in ((htdp.to_nad83, htdp.from_nad83), (htdp.from_nad83, htdp.to_nad83)):
                        a = out(*start, frame, epoch)
                        b = back(a.latitude, a.longitude, a.ellipsoid_height, frame, epoch)
                        residual = _neu(start, (b.latitude, b.longitude, b.ellipsoid_height))
                        count += 1
                        for i in range(3):
                            if residual[i] > worst[i]:
                                worst[i] = residual[i]
                                where[i] = (date.isoformat(), lat, lon, height, frame.name.strip())
    lines = [
        f"first {FIRST.isoformat()}",
        f"last {LAST.isoformat()}",
        f"positions {len(positions)}",
        f"round_trips {count}",
    ]
    for i, axis in enumerate(("north", "east", "up")):
        lines.append(f"worst_{axis}_m {worst[i]:.3e} at {where[i]}")
    (REPO / "review/wgs84-gate2/roundtrip_range_output.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
