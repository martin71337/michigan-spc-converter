"""H1 follow-up -- is frame_p05 real beta NCAT behaviour or a capture artifact?

Six requests, one session, throttled at 1/s, same harness and the same echo
checks as the lattice run:

  1. frame_p05 re-run, EXACTLY as captured: (43.8, -86.4),
     NAD83(2011) epoch 2010.00 -> NATRF2022 epoch 2020.00, no zone forced.
  2. four neighbours at +/-0.1 deg in each axis, same datum pair.
  3. frame_p04 (43.0, -84.5) re-run as a session control.

Writes new raw files and raw/p05_probe_manifest.json. It does NOT touch
anchors.json or raw/manifest.json -- the coordinator's instruction was to leave
every existing file alone, so the manifest entries go in a new file of the same
shape rather than being appended to the lattice manifest.

Run:  py -3 capture_p05_probe.py
"""

from __future__ import annotations

import json
import os
import sys

import h1_lib as H
from capture_h1_anchors import submit_llh, verify

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:      # pragma: no cover
    pass

IN, OUT = H.NAD83, H.NATRF

POINTS = [
    ("p05_rerun.html",      43.80, -86.40, "frame_p05 re-run, exact"),
    ("p05_nbr_lat_lo.html", 43.70, -86.40, "neighbour  lat -0.1"),
    ("p05_nbr_lat_hi.html", 43.90, -86.40, "neighbour  lat +0.1"),
    ("p05_nbr_lon_lo.html", 43.80, -86.50, "neighbour  lon -0.1"),
    ("p05_nbr_lon_hi.html", 43.80, -86.30, "neighbour  lon +0.1"),
    ("p04_control.html",    43.00, -84.50, "frame_p04 re-run, session control"),
]


def main():
    n = H.Ncat()
    n.open_app()
    print("beta NCAT app opened\n")

    rows = []
    for name, lat, lon, note in POINTS:
        rec, body = submit_llh(n, "p05probe_" + name, lat, lon,
                               indatum=IN, outdatum=OUT, note=note)
        if not body:
            rows.append({"name": name, "note": note, "failed": True,
                         "reason": rec["error"] or "no body"})
            print("FAILED %-22s %s" % (name, rec["error"]))
            continue
        tr = H.parse_transform(body)
        bad = verify(body, indatum=IN, outdatum=OUT, lat=lat, lon=lon, tr=tr)
        row = {
            "name": name,
            "note": note,
            "input_lat_dd": H.dd(lat),
            "input_lon_dd": H.dd(lon),
            "ncat_echo_lat": H.last_dd(tr["in_lat_cell"]),
            "ncat_echo_lon": H.last_dd(tr["in_lon_cell"]),
            "output_lat_dd": H.last_dd(tr["out_lat_cell"]),
            "output_lon_dd": H.last_dd(tr["out_lon_cell"]),
            "output_lat_cell": tr["out_lat_cell"],
            "output_lon_cell": tr["out_lon_cell"],
            "lat_change_sigma": tr["lat_change_sigma"],
            "lon_change_sigma": tr["lon_change_sigma"],
            "input_epoch": tr["in_epoch"],
            "output_epoch": tr["out_epoch"],
            "in_frame": tr["in_frame"],
            "out_frame": tr["out_frame"],
            "raw": rec["saved"],
            "sha256": rec["sha256"],
            "verified": not bad,
            "verify_notes": bad,
        }
        rows.append(row)
        print("%-22s %s , %s  ->  %s , %s   %s"
              % (name, row["input_lat_dd"], row["input_lon_dd"],
                 row["output_lat_dd"], row["output_lon_dd"],
                 "OK" if not bad else "REFUSED: " + "; ".join(bad)))

    n.write_manifest("p05_probe_manifest.json")

    # the frozen anchors, read but not written
    with open(os.path.join(H.HERE, "anchors.json"), encoding="utf-8") as fh:
        frozen = {r["name"]: r for r in json.load(fh)["frame_anchors"]}

    print("\n--- comparison against the frozen anchors")
    for probe_name, anchor_name in (("p05_rerun.html", "frame_p05.html"),
                                    ("p04_control.html", "frame_p04.html")):
        p = next(r for r in rows if r["name"] == probe_name)
        a = frozen[anchor_name]
        same = (p["output_lat_dd"] == a["output_lat_dd"]
                and p["output_lon_dd"] == a["output_lon_dd"]
                and p["lat_change_sigma"] == a["lat_change_sigma"]
                and p["lon_change_sigma"] == a["lon_change_sigma"])
        print("%s vs %s : %s" % (probe_name, anchor_name,
                                 "IDENTICAL" if same else "DIFFERENT"))
        print("   frozen  %s , %s" % (a["output_lat_dd"], a["output_lon_dd"]))
        print("   re-run  %s , %s" % (p["output_lat_dd"], p["output_lon_dd"]))
        print("   frozen  sigma lat %s" % a["lat_change_sigma"])
        print("   re-run  sigma lat %s" % p["lat_change_sigma"])
        print("   frozen  sigma lon %s" % a["lon_change_sigma"])
        print("   re-run  sigma lon %s" % p["lon_change_sigma"])

    out = os.path.join(H.RAW, "p05_probe_results.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rows, fh, indent=2, sort_keys=True)
    print("\nresults: %s" % out)


if __name__ == "__main__":
    main()
