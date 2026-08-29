"""Cross-check the frozen anchors, and finish anchors.json's bookkeeping.

Four checks, none of which the capture itself could make:

  0. Every anchor's raw response file is still present and still hashes to the
     SHA-256 the manifest recorded for it.
  1. Every LDP origin point must come back as EXACTLY the published false
     northing and false easting, with EXACTLY the published projection origin
     scale factor and zero convergence. The published values come from
     zoneDefinitions.json via review/nsrs-n0/FINDINGS.md section 6, which is a
     different source from the NCAT app -- so this is NCAT's projection agreeing
     with NGS's own parameter file, not with itself.
  2. Every inverse anchor must return the latitude and longitude its forward
     run started from.
  3. The reverse frame runs must be the exact negation of the forward runs at
     the same point (the property N0 observed at one point; here at three).

Run:  py -3 check_anchors.py
"""

from __future__ import annotations

import json
import os
import sys

import h1_lib as H

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:      # pragma: no cover
    pass

# code -> (false northing m, false easting m, origin scale factor)
# review/nsrs-n0/FINDINGS.md section 6, from zoneDefinitions.json.
PUBLISHED = {
    "260001": (762000, 1524000, "0.999800"),
    "261001": (0, 381000, "1.000022"),
    "261002": (0, 495300, "1.000024"),
    "261003": (76200, 685800, "1.000026"),
    "261004": (228600, 723900, "1.000012"),
    "261005": (76200, 990600, "1.000029"),
    "261006": (190500, 1028700, "1.000031"),
    "261007": (76200, 1333500, "1.000024"),
    "261008": (228600, 1409700, "1.000018"),
    "261009": (76200, 1638300, "1.000025"),
    "261010": (190500, 1638300, "1.000034"),
    "261011": (76200, 1905000, "1.000025"),
    "261012": (190500, 2019300, "1.000025"),
    "261013": (76200, 381000, "1.000011"),
    "261014": (0, 685800, "1.000012"),
    "261015": (0, 952500, "1.000038"),
    "261016": (0, 1295400, "1.000042"),
    "261017": (114300, 1600200, "1.000036"),
    "261018": (76200, 1866900, "1.000026"),
}


def main():
    here = H.HERE
    ap = os.path.join(here, "anchors.json")
    with open(ap, encoding="utf-8") as fh:
        a = json.load(fh)

    problems = []

    # 0 -- every anchor's raw file is still there and still hashes the same
    n_raw = 0
    for sec in ("projection_anchors", "frame_anchors", "inverse_anchors"):
        for r in a[sec]:
            path = os.path.join(here, r["raw"])
            if not os.path.exists(path):
                problems.append("%s: raw file %s is missing" % (r["name"], r["raw"]))
                continue
            if H.C.sha256_file(path) != r["sha256"]:
                problems.append("%s: raw file %s no longer matches its recorded "
                                "SHA-256" % (r["name"], r["raw"]))
            n_raw += 1
    print("0. raw files present and digest-matching: %d checked" % n_raw)

    # 1 -- origins against the published parameters
    origins = [r for r in a["projection_anchors"] if r["label"] in
               ("origin", "projection center")]
    for r in origins:
        fn, fe, sf = PUBLISHED[r["zone_code"]]
        if float(r["northing_m"]) != float(fn):
            problems.append("%s northing %s != published FN %s"
                            % (r["name"], r["northing_m"], fn))
        if float(r["easting_m"]) != float(fe):
            problems.append("%s easting %s != published FE %s"
                            % (r["name"], r["easting_m"], fe))
        if float(r["scale_factor"]) != float(sf):
            problems.append("%s scale %s != published k0 %s"
                            % (r["name"], r["scale_factor"], sf))
        if r["convergence"].replace("+", "").replace("-", "") not in (
                "00° 00′ 00.00″",):
            problems.append("%s convergence %r is not zero at the origin"
                            % (r["name"], r["convergence"]))
    print("1. origins vs published parameters: %d checked" % len(origins))

    # 2 -- inverse round-trip
    worst = 0.0
    for r in a["inverse_anchors"]:
        dlat = abs(float(r["returned_lat_dd"]) - float(r["forward_input_lat_dd"]))
        dlon = abs(float(r["returned_lon_dd"]) - float(r["forward_input_lon_dd"]))
        worst = max(worst, dlat, dlon)
        if max(dlat, dlon) > 1e-7:
            problems.append("%s round-trip off by %.3e deg"
                            % (r["name"], max(dlat, dlon)))
    print("2. inverse round-trip: %d checked, worst %.3e deg (~%.2f mm)"
          % (len(a["inverse_anchors"]), worst, worst * 111320.0 * 1000))

    # 3 -- reverse frame runs are the exact negation
    fwd = {(r["input_lat_dd"], r["input_lon_dd"]): r for r in a["frame_anchors"]
           if r["direction"].startswith("NAD83")}
    rev = [r for r in a["frame_anchors"] if r["direction"].startswith("NATRF")]
    checked = 0
    for r in rev:
        f = fwd.get((r["input_lat_dd"], r["input_lon_dd"]))
        if f is None:
            problems.append("%s has no forward partner" % r["name"])
            continue
        checked += 1
        for k in ("lat", "lon"):
            d_f = float(f["output_%s_dd" % k]) - float(f["input_%s_dd" % k])
            d_r = float(r["output_%s_dd" % k]) - float(r["input_%s_dd" % k])
            if abs(d_f + d_r) > 1e-10:
                problems.append("%s %s shift %+.10f vs forward %+.10f -- not "
                                "an exact negation" % (r["name"], k, d_r, d_f))
    print("3. reverse == exact negation: %d pairs checked" % checked)

    # bookkeeping: replace the running request count with the real ones
    man = os.path.join(H.RAW, "manifest.json")
    inv = os.path.join(H.RAW, "inverse_manifest.json")
    with open(man, encoding="utf-8") as fh:
        n_lattice = len(json.load(fh))
    with open(inv, encoding="utf-8") as fh:
        n_inverse = len(json.load(fh))
    a["counts"] = {
        "projection_anchors": len(a["projection_anchors"]),
        "frame_anchors": len(a["frame_anchors"]),
        "inverse_anchors": len(a["inverse_anchors"]),
        "failures": len(a["failures"]),
        "http_requests_lattice_session": n_lattice,
        "http_requests_inverse_session": n_inverse,
    }
    a["cross_checks"] = {
        "raw_files_present_and_digest_matching": "%d of %d anchors" % (
            n_raw, len(a["projection_anchors"]) + len(a["frame_anchors"])
            + len(a["inverse_anchors"])),
        "origins_vs_published_parameters": "%d origin points reproduce the "
            "published false northing, false easting and origin scale factor "
            "exactly, with zero convergence" % len(origins),
        "inverse_round_trip": "worst %.3e deg (~%.2f mm) over %d points"
            % (worst, worst * 111320.0 * 1000, len(a["inverse_anchors"])),
        "reverse_frame_exact_negation": "%d pairs, exact to every printed digit"
            % checked,
        "problems": problems,
    }
    with open(ap, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(a, fh, indent=2, sort_keys=True)

    print("\nproblems: %d" % len(problems))
    for p in problems:
        print("   ", p)
    print("\ncounts: %s" % a["counts"])
    print("manifest.json          sha256 %s" % H.C.sha256_file(man))
    print("inverse_manifest.json  sha256 %s" % H.C.sha256_file(inv))
    print("anchors.json           sha256 %s" % H.C.sha256_file(ap))


if __name__ == "__main__":
    main()
