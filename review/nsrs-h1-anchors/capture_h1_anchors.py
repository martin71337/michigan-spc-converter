"""H1 -- freeze an SPCS2022 anchor lattice for Michigan from beta NCAT.

Four families, in order:

  A. statewide OM zone 260001, 9 points, deliberately ASYMMETRIC about the
     45 00 N / 86 00 W center (asymmetry is what discriminates the Hotine
     variant and the sign of the -26 deg skew);
  B. each of the 18 LDP zones, 3 points -- the zone origin and origin
     +(0.15, 0.25) and -(0.15, 0.25) -- zone forced every time;
  C. the frame transformation, NAD83(2011) epoch 2010.00 -> NATRF2022 epoch
     2020.00, 12 points, no zone forced, plus the reverse at 3 of them;
  D. the inverse: SPC northing/easting/zone as INPUT (beta NCAT does offer
     this -- see probe_inverse.py), 5 points fed back from A/B.

A, B and D are PURE PROJECTION: input datum AND output datum are both
NATRF2022 epoch 2020.00, so no frame transformation stands between the
geodetic position and the grid coordinate.

Nothing here is production code and nothing in michspc/ may import it.

Run:  py -3 capture_h1_anchors.py
"""

from __future__ import annotations

import json
import os
import sys

import h1_lib as H

# NCAT prints prime/double-prime (U+2032/U+2033) in its convergence values and
# this machine's console is cp1252. Print in UTF-8 or the run dies on the first
# angle -- and the point of a capture run is that nothing is silently lost.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:      # pragma: no cover
    pass

NATRF = H.NATRF
NAD83 = H.NAD83

# ---------------------------------------------------------------- the lattice

# A -- statewide OM zone. Eight asymmetric points plus the projection center.
STATEWIDE = [
    (42.10, -83.20, "Detroit area"),
    (41.90, -86.60, "far SW"),
    (43.60, -84.20, "mid-mitten"),
    (44.80, -87.40, "NW Lake Michigan"),
    (45.90, -84.70, "eastern UP"),
    (46.50, -87.60, "central UP"),
    (47.10, -88.60, "Keweenaw"),
    (48.10, -88.55, "Isle Royale"),
    (45.00, -86.00, "projection center"),
]

# B -- the 18 LDP zones. Origin latitude / origin west longitude, decimal
# degrees, converted from the DMS strings in review/nsrs-n0/FINDINGS.md 6.
LDP = [
    ("261001", "MI L11A", 41.30, -84.10),   # 41 18 N  084 06 W  TM  Ann Arbor
    ("261002", "MI L15D", 40.20, -83.15),   # 40 12 N  083 09 W  TM  Detroit
    ("261003", "MI L21F", 42.90, -83.40),   # 42 54 N  083 24 W  LC1 Flint
    ("261004", "MI L25S", 43.60, -83.65),   # 43 36 N  083 39 W  LC1 Saginaw
    ("261005", "MI L31R", 44.25, -84.15),   # 44 15 N  084 09 W  LC1 Roscommon
    ("261006", "MI L35T", 44.85, -84.05),   # 44 51 N  084 03 W  LC1 Thunder Bay
    ("261007", "MI L41Z", 42.10, -85.65),   # 42 06 N  085 39 W  LC1 Kalamazoo
    ("261008", "MI L45G", 42.80, -85.15),   # 42 48 N  085 09 W  LC1 Grand Rapids
    ("261009", "MI L51N", 43.45, -85.40),   # 43 27 N  085 24 W  LC1 Newaygo
    ("261010", "MI L55W", 44.15, -85.55),   # 44 09 N  085 33 W  LC1 Wexford
    ("261011", "MI L61L", 44.90, -85.45),   # 44 54 N  085 27 W  LC1 Leelanau
    ("261012", "MI L65C", 45.45, -84.45),   # 45 27 N  084 27 W  LC1 Cheboygan
    ("261013", "MI U11M", 46.20, -84.85),   # 46 12 N  084 51 W  LC1 Mackinac
    ("261014", "MI U21E", 45.15, -86.60),   # 45 09 N  086 36 W  TM  Escanaba
    ("261015", "MI U31Q", 44.70, -87.60),   # 44 42 N  087 36 W  TM  Marquette
    ("261016", "MI U41H", 45.50, -88.40),   # 45 30 N  088 24 W  TM  Houghton
    ("261017", "MI U51B", 46.70, -89.70),   # 46 42 N  089 42 W  LC1 Bessemer
    ("261018", "MI U61K", 48.00, -88.85),   # 48 00 N  088 51 W  LC1 Isle Royale
]

ZONE_TOKEN = {"260001": "260001-MI (Statewide)"}
for _code, _abrv, _a, _b in LDP:
    ZONE_TOKEN[_code] = "%s-%s (Multizone complete)" % (_code, _abrv)

# C -- the frame lattice.
FRAME = [
    (41.80, -83.50), (42.30, -83.10), (42.30, -86.20),
    (43.00, -84.50),                       # the N0 point -- consistency check
    (43.80, -86.40), (44.30, -84.70), (45.10, -83.50), (45.80, -84.70),
    (46.30, -85.50), (46.60, -87.40), (47.20, -88.50), (48.10, -88.60),
]
FRAME_REVERSE = [(43.00, -84.50), (42.30, -83.10), (47.20, -88.50)]


# ------------------------------------------------------------------- driving

def submit_llh(n, name, lat, lon, *, indatum, outdatum, zone_token=None,
               note=""):
    """One forward conversion from a geodetic position."""
    f = n.base_fields()
    f["tv1:f1:cotype"] = "horz"
    f["tv1:f1:proj1"] = "llh"
    f["tv1:f1:lat_input"] = H.dd(lat)
    f["tv1:f1:lon_input"] = H.dd(lon)
    f["tv1:f1:lat_hinput"] = H.dd(lat)
    f["tv1:f1:lon_hinput"] = H.dd(lon)
    f["tv1:f1:latd"] = H.dms(lat, 2)
    f["tv1:f1:lond"] = H.dms(lon, 3)
    f["tv1:f1:latdir_input"] = "N" if lat >= 0 else "S"
    f["tv1:f1:londir_input"] = "W" if lon < 0 else "E"
    f["tv1:f1:indatum_input"] = indatum
    f["tv1:f1:outdatum_input"] = outdatum
    if zone_token is not None:
        f["tv1:f1:zonelist_input"] = zone_token
    f.update({
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "tv1:f1:cmdb",
        "javax.faces.partial.execute": "@all",
        "javax.faces.partial.render": "@all",
        "tv1:f1:cmdb": "tv1:f1:cmdb",
    })
    return n.post(f, name, note=note)


def submit_spc_in(n, name, northing, easting, zone_token, *, indatum, outdatum,
                  units="m", note=""):
    """One INVERSE conversion: SPC northing/easting/zone in, geodetic out."""
    f = n.base_fields()
    f["tv1:f1:cotype"] = "horz"
    f["tv1:f1:proj1"] = "spc"
    f["tv1:f1:spcsy"] = "spcs2022"
    f["tv1:f1:northing_input"] = str(northing)
    f["tv1:f1:northing_hinput"] = str(northing)
    f["tv1:f1:easting_input"] = str(easting)
    f["tv1:f1:easting_hinput"] = str(easting)
    f["tv1:f1:units_input"] = units
    f["tv1:f1:zonelist3_input"] = zone_token
    f["tv1:f1:indatum_input"] = indatum
    f["tv1:f1:outdatum_input"] = outdatum
    f.update({
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "tv1:f1:cmdb",
        "javax.faces.partial.execute": "@all",
        "javax.faces.partial.render": "@all",
        "tv1:f1:cmdb": "tv1:f1:cmdb",
    })
    return n.post(f, name, note=note)


def switch_proj1(n, value, name):
    """Fire the PrimeFaces valueChange that rebuilds the input panel."""
    f = n.base_fields()
    f["tv1:f1:proj1"] = value
    f.update({
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "tv1:f1:proj1",
        "javax.faces.partial.execute": "tv1:f1:proj1",
        "javax.faces.partial.render": "tv1:f1:p1 tv1:f1:resultP",
        "javax.faces.behavior.event": "valueChange",
        "javax.faces.partial.event": "change",
    })
    return n.post(f, name, note="valueChange proj1=%s" % value)


# ---------------------------------------------------------------- verifying

def near(a, b, tol=1e-8):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def verify(body, *, indatum, outdatum, lat=None, lon=None, zone_code=None,
           spc=None, tr=None):
    """Every reason this response may not be trusted. Empty list == trusted."""
    bad = []
    if not H.has_result(body):
        return ["no result block in response"]
    if tr["in_frame"] != indatum:
        bad.append("input frame is %r, asked %r" % (tr["in_frame"], indatum))
    if tr["out_frame"] != outdatum:
        bad.append("output frame is %r, asked %r" % (tr["out_frame"], outdatum))
    if lat is not None and not near(H.last_dd(tr["in_lat_cell"]), lat):
        bad.append("echoed input lat %r, sent %r"
                   % (H.last_dd(tr["in_lat_cell"]), lat))
    if lon is not None and not near(H.last_dd(tr["in_lon_cell"]), lon):
        bad.append("echoed input lon %r, sent %r"
                   % (H.last_dd(tr["in_lon_cell"]), lon))
    if zone_code is not None:
        z = (spc or {}).get("zone") or ""
        if zone_code not in z:
            bad.append("zone panel says %r, forced %r" % (z, zone_code))
    return bad


# -------------------------------------------------------------------- main

def main():
    n = H.Ncat()
    n.open_app()
    print("beta NCAT app opened; action=%s\n" % H.scrub_url(n.action))

    anchors = {
        "capture_date": H.CAPTURE_DATE,
        "source": "https://beta.ngs.noaa.gov/NCAT/ (beta NCAT v3.0, JSF app)",
        "what_this_is": (
            "beta NCAT's own printed output, captured through its web form. "
            "It is that implementation's behaviour on 2026-08-28, NOT ground "
            "truth, and must be re-frozen at the official NGS release."),
        "value_convention": (
            "Every value is the string beta NCAT printed, verbatim, with two "
            "documented exceptions: the unit token ('m', 'ift') is split off "
            "into the field name, and any thousands separator would be "
            "stripped (each point records thousands_stripped)."),
        "projection_anchors": [],
        "frame_anchors": [],
        "inverse_anchors": [],
        "failures": [],
    }

    def record_projection(name, kind, zone_code, lat, lon, label, rec, body):
        if not body:
            anchors["failures"].append(
                {"name": name, "reason": rec["error"] or "no body"})
            print("  FAILED %s: %s" % (name, rec["error"]))
            return
        tr = H.parse_transform(body)
        spc = H.parse_spc(body)
        bad = verify(body, indatum=NATRF, outdatum=NATRF, lat=lat, lon=lon,
                     zone_code=zone_code, spc=spc, tr=tr)
        row = {
            "name": name,
            "kind": kind,
            "zone_code": zone_code,
            "zone_token": ZONE_TOKEN[zone_code],
            "label": label,
            "input_datum": NATRF,
            "output_datum": NATRF,
            "input_lat_dd": H.dd(lat),
            "input_lon_dd": H.dd(lon),
            "input_lat_dms": H.dms(lat, 2),
            "input_lon_dms": H.dms(lon, 3),
            "ncat_echo_lat": H.last_dd(tr["in_lat_cell"]),
            "ncat_echo_lon": H.last_dd(tr["in_lon_cell"]),
            "ncat_zone": spc["zone"],
            "northing_m": spc["northing"]["m"],
            "northing_ift": spc["northing"]["ift"],
            "northing_usft": spc["northing"]["usft"],
            "easting_m": spc["easting"]["m"],
            "easting_ift": spc["easting"]["ift"],
            "easting_usft": spc["easting"]["usft"],
            "scale_factor": spc["scale_factor"],
            "combined_factor": spc["combined_factor"],
            "convergence": spc["convergence"],
            "distortion": spc["distortion"],
            "thousands_stripped": bool(spc["northing"]["thousands_stripped"]
                                       or spc["easting"]["thousands_stripped"]),
            "raw": rec["saved"],
            "sha256": rec["sha256"],
            "verified": not bad,
            "verify_notes": bad,
        }
        if bad:
            anchors["failures"].append({"name": name, "reason": "; ".join(bad),
                                        "raw": rec["saved"]})
            print("  REFUSED %s: %s" % (name, "; ".join(bad)))
        else:
            anchors["projection_anchors"].append(row)
            print("  %-16s %-24s N %-14s E %-14s sf %s conv %s"
                  % (name, spc["zone"][:24] if spc["zone"] else "?",
                     row["northing_m"], row["easting_m"],
                     row["scale_factor"], row["convergence"]))

    # -- A: statewide -----------------------------------------------------
    print("### A. statewide OM zone 260001 -- 9 points, pure projection")
    for i, (lat, lon, label) in enumerate(STATEWIDE, 1):
        name = "z260001_p%d.html" % i
        rec, body = submit_llh(n, name, lat, lon, indatum=NATRF,
                               outdatum=NATRF, zone_token=ZONE_TOKEN["260001"],
                               note="statewide OMC, %s" % label)
        record_projection(name, "statewide", "260001", lat, lon, label,
                          rec, body)

    # -- B: the 18 LDPs ---------------------------------------------------
    print("\n### B. the 18 LDP zones -- origin and two offsets, pure projection")
    for code, abrv, olat, olon in LDP:
        pts = [(olat, olon, "origin"),
               (olat + 0.15, olon + 0.25, "origin +0.15/+0.25"),
               (olat - 0.15, olon - 0.25, "origin -0.15/-0.25")]
        for i, (lat, lon, label) in enumerate(pts, 1):
            name = "z%s_p%d.html" % (code, i)
            rec, body = submit_llh(n, name, round(lat, 6), round(lon, 6),
                                   indatum=NATRF, outdatum=NATRF,
                                   zone_token=ZONE_TOKEN[code],
                                   note="%s %s, %s" % (code, abrv, label))
            record_projection(name, "ldp", code, round(lat, 6), round(lon, 6),
                              label, rec, body)

    # -- C: the frame lattice ---------------------------------------------
    print("\n### C. frame transformation -- no zone forced")
    for direction, pts, prefix in (
            ("NAD83(2011)->NATRF2022", FRAME, "frame_p"),
            ("NATRF2022->NAD83(2011)", FRAME_REVERSE, "framerev_p")):
        ind = NAD83 if pts is FRAME else NATRF
        outd = NATRF if pts is FRAME else NAD83
        for i, (lat, lon) in enumerate(pts, 1):
            name = "%s%02d.html" % (prefix, i)
            rec, body = submit_llh(n, name, lat, lon, indatum=ind,
                                   outdatum=outd, note=direction)
            if not body:
                anchors["failures"].append(
                    {"name": name, "reason": rec["error"] or "no body"})
                print("  FAILED %s: %s" % (name, rec["error"]))
                continue
            tr = H.parse_transform(body)
            spc = H.parse_spc(body)
            bad = verify(body, indatum=ind, outdatum=outd, lat=lat, lon=lon,
                         spc=spc, tr=tr)
            row = {
                "name": name,
                "direction": direction,
                "input_datum": ind,
                "output_datum": outd,
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
                "auto_spc_zone": spc["zone"],
                "auto_spc_northing_m": spc["northing"]["m"],
                "auto_spc_easting_m": spc["easting"]["m"],
                "auto_spc_scale_factor": spc["scale_factor"],
                "auto_spc_convergence": spc["convergence"],
                "raw": rec["saved"],
                "sha256": rec["sha256"],
                "verified": not bad,
                "verify_notes": bad,
            }
            if bad:
                anchors["failures"].append(
                    {"name": name, "reason": "; ".join(bad),
                     "raw": rec["saved"]})
                print("  REFUSED %s: %s" % (name, "; ".join(bad)))
            else:
                anchors["frame_anchors"].append(row)
                print("  %-18s %s,%s -> %s,%s"
                      % (name, row["input_lat_dd"], row["input_lon_dd"],
                         row["output_lat_dd"], row["output_lon_dd"]))

    # -- D: the inverse ---------------------------------------------------
    print("\n### D. inverse -- SPC northing/easting/zone as INPUT")
    rec, body = switch_proj1(n, "spc", "inv_switch_proj1_spc.xml")
    anchors["inverse_probe"] = {
        "question": "does beta NCAT accept SPC (N/E/zone) as input?",
        "answer": "YES",
        "evidence": (
            "tv1:f1:proj1 offers llh|spc|utm|usng; the spc valueChange builds "
            "an input panel with tv1:f1:northing_input, tv1:f1:easting_input, "
            "tv1:f1:units_input (m|ift|usft), tv1:f1:spcsy "
            "(spcs2022|spc83|spc27, default spcs2022), tv1:f1:zonelist3_input "
            "(input zone, 955 options) and tv1:f1:zonelistx2_input (optional "
            "output zone)."),
        "raw": rec["saved"],
        "sha256": rec["sha256"],
    }

    # feed five forward results back in; expect the original lat/lon out
    picks = []
    want = ["z260001_p9.html", "z261007_p1.html", "z261002_p2.html",
            "z261013_p1.html", "z261018_p3.html"]
    by_name = {r["name"]: r for r in anchors["projection_anchors"]}
    for w in want:
        if w in by_name:
            picks.append(by_name[w])
    for i, src in enumerate(picks, 1):
        name = "inv_p%d.html" % i
        rec, body = submit_spc_in(
            n, name, src["northing_m"], src["easting_m"],
            ZONE_TOKEN[src["zone_code"]], indatum=NATRF, outdatum=NATRF,
            units="m", note="inverse of %s" % src["name"])
        if not body:
            anchors["failures"].append(
                {"name": name, "reason": rec["error"] or "no body"})
            print("  FAILED %s: %s" % (name, rec["error"]))
            continue
        tr = H.parse_transform(body)
        spc = H.parse_spc(body)
        bad = []
        if not H.has_result(body):
            bad.append("no result block in response")
        else:
            if tr["in_frame"] != NATRF or tr["out_frame"] != NATRF:
                bad.append("frames are %r -> %r, asked %r -> %r"
                           % (tr["in_frame"], tr["out_frame"], NATRF, NATRF))
            # The output SPC zone is left unset on an inverse run, so the
            # result panel's zone is NCAT's auto-pick and is recorded, not
            # checked. What IS checked is that the returned position is the
            # one the forward run started from.
        row = {
            "name": name,
            "inverse_of": src["name"],
            "zone_code": src["zone_code"],
            "zone_token": ZONE_TOKEN[src["zone_code"]],
            "input_northing_m": src["northing_m"],
            "input_easting_m": src["easting_m"],
            "input_units": "m",
            "expected_lat_dd": src["input_lat_dd"],
            "expected_lon_dd": src["input_lon_dd"],
            "returned_lat_dd": H.last_dd(tr["out_lat_cell"]),
            "returned_lon_dd": H.last_dd(tr["out_lon_cell"]),
            "returned_lat_cell": tr["out_lat_cell"],
            "returned_lon_cell": tr["out_lon_cell"],
            "ncat_zone": spc["zone"],
            "scale_factor": spc["scale_factor"],
            "convergence": spc["convergence"],
            "raw": rec["saved"],
            "sha256": rec["sha256"],
            "verified": not bad,
            "verify_notes": bad,
        }
        if bad:
            anchors["failures"].append({"name": name, "reason": "; ".join(bad),
                                        "raw": rec["saved"]})
            print("  REFUSED %s: %s" % (name, "; ".join(bad)))
        else:
            anchors["inverse_anchors"].append(row)
            print("  %-12s %s -> %s,%s (expected %s,%s)"
                  % (name, src["name"], row["returned_lat_dd"],
                     row["returned_lon_dd"], row["expected_lat_dd"],
                     row["expected_lon_dd"]))

    mp = n.write_manifest("manifest.json")
    anchors["counts"] = {
        "projection_anchors": len(anchors["projection_anchors"]),
        "frame_anchors": len(anchors["frame_anchors"]),
        "inverse_anchors": len(anchors["inverse_anchors"]),
        "failures": len(anchors["failures"]),
        "http_requests": len(n.records),
    }
    ap = os.path.join(H.HERE, "anchors.json")
    with open(ap, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(anchors, fh, indent=2, sort_keys=True)

    print("\nmanifest: %s  sha256 %s" % (mp, H.C.sha256_file(mp)))
    print("anchors : %s  sha256 %s" % (ap, H.C.sha256_file(ap)))
    print("counts  : %s" % anchors["counts"])


if __name__ == "__main__":
    main()
