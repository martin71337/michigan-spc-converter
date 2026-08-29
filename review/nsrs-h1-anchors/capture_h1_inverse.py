"""H1 family D -- the INVERSE anchors (SPC northing/easting/zone as INPUT).

beta NCAT DOES offer SPC as an input coordinate type, but driving it takes
five requests per point and two of them are not obvious. Both were found by
probe, and both are recorded because either one, silently wrong, yields a
plausible number that is not the answer to the question asked:

  1. Submitting from SPC-input mode WITHOUT tv1:f1:zonelistx2_input (the
     "Output SPC zone (optional)" control) makes the app return its
     "The page that you are attempting to access has expired or an error
     occurred" page. The control is labelled optional; omitting the FIELD is
     not the same as leaving the control unset, and the app throws.
  2. Posting the northing and easting on the submit alone is not enough: the
     app converts whatever lat/lon the bean already holds and projects THAT
     into the chosen zone. On the first attempt it returned latitude
     0.0000000000 with a northing of 19,261,562.580 m and a convergence of
     -18 35 553.55 -- garbage, but garbage that arrived with HTTP 200 and a
     correctly named zone. The northing/easting only reach the model through
     their own blur AJAX, which must fire BEFORE the zone valueChange.

So each point is: northing blur -> easting blur -> zone valueChange -> submit,
with the panel switched to SPC once at the top of the session. Every response
is checked: the zone must be named, the echoed northing/easting must be the
ones sent, and the frames must be the pair asked for.

Reads the forward results out of anchors.json and rewrites its
"inverse_anchors" section in place.

Run:  py -3 capture_h1_inverse.py
"""

from __future__ import annotations

import json
import os
import re
import sys

import h1_lib as H
from capture_h1_anchors import ZONE_TOKEN, near, switch_proj1

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:      # pragma: no cover
    pass

NATRF = H.NATRF

# One point from five different zones, spanning all three projection types:
# the statewide OMC center, an LC1 origin, a TM offset point, an LC1 origin in
# the UP, and an LC1 offset point at Isle Royale.
WANT = ["z260001_p9.html", "z261007_p1.html", "z261002_p2.html",
        "z261013_p1.html", "z261018_p3.html"]


def grouped(value: str) -> str:
    """'1333500.000' -> '1,333,500.000' -- the widget's own aSep=',' shape."""
    neg = value.startswith("-")
    v = value.lstrip("-")
    whole, _, frac = v.partition(".")
    out = "{:,}".format(int(whole))
    if frac:
        out += "." + frac
    return ("-" + out) if neg else out


def spc_fields(n, northing, easting, zone_token, *, indatum, outdatum,
               units="m"):
    f = n.base_fields()
    # the lat/lon panel no longer exists in the tree; do not post its fields
    for k in list(f):
        if (k.startswith("tv1:f1:lat") or k.startswith("tv1:f1:lon")
                or k.startswith("tv1:f1:zonelist_")):
            del f[k]
    f.update({
        "tv1:f1:cotype": "horz",
        "tv1:f1:proj1": "spc",
        "tv1:f1:spcsy": "spcs2022",
        "tv1:f1:northing_input": grouped(northing),
        "tv1:f1:northing_hinput": northing,
        "tv1:f1:easting_input": grouped(easting),
        "tv1:f1:easting_hinput": easting,
        "tv1:f1:units_input": units,
        "tv1:f1:units_focus": "",
        "tv1:f1:zonelist3_input": zone_token,
        "tv1:f1:zonelist3_focus": "",
        "tv1:f1:zonelist3_filter": "",
        # NOT optional as a FIELD, whatever the label says -- see the header
        "tv1:f1:zonelistx2_input": zone_token,
        "tv1:f1:zonelistx2_focus": "",
        "tv1:f1:zonelistx2_filter": "",
        "tv1:f1:indatum_input": indatum,
        "tv1:f1:outdatum_input": outdatum,
    })
    return f


def ajax(n, base, src, process, render, event, name, note):
    f = dict(base)
    f.update({
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": src,
        "javax.faces.partial.execute": process,
        "javax.faces.partial.render": render,
        "javax.faces.behavior.event": event,
    })
    return n.post(f, name, note=note)


def echoed(body, field):
    m = re.search(r'name="tv1:f1:%s"[^>]*value="([^"]*)"' % field, body)
    return m.group(1) if m else None


def main():
    ap = os.path.join(H.HERE, "anchors.json")
    with open(ap, encoding="utf-8") as fh:
        anchors = json.load(fh)
    by_name = {r["name"]: r for r in anchors["projection_anchors"]}

    anchors["inverse_anchors"] = []
    anchors["failures"] = [f for f in anchors["failures"]
                           if not f["name"].startswith(("inv_p", "inv2_p"))]

    n = H.Ncat()
    n.open_app()
    rec, _ = switch_proj1(n, "spc", "inv3_switch_proj1_spc.xml")
    print("fresh session; proj1 -> spc  status=%s bytes=%s"
          % (rec["status"], rec["bytes"]))
    anchors["inverse_probe"]["switch_raw"] = rec["saved"]
    anchors["inverse_probe"]["switch_sha256"] = rec["sha256"]
    anchors["inverse_probe"]["required_request_sequence"] = [
        "valueChange tv1:f1:proj1=spc (once per session)",
        "blur tv1:f1:northing",
        "blur tv1:f1:easting",
        "valueChange tv1:f1:zonelist3 (the input zone) -- AFTER the two blurs",
        "submit tv1:f1:cmdb, with tv1:f1:zonelistx2_input supplied",
    ]

    for i, w in enumerate(WANT, 1):
        src = by_name.get(w)
        if src is None:
            print("  MISSING forward anchor %s" % w)
            continue
        zt = ZONE_TOKEN[src["zone_code"]]
        base = spc_fields(n, src["northing_m"], src["easting_m"], zt,
                          indatum=NATRF, outdatum=NATRF)
        tag = "inv3_p%d" % i
        note = "inverse of %s" % src["name"]
        ajax(n, base, "tv1:f1:northing", "tv1:f1:northing", "tv1:f1:resultP",
             "blur", tag + "_1north.xml", note)
        ajax(n, base, "tv1:f1:easting", "tv1:f1:easting", "tv1:f1:resultP",
             "blur", tag + "_2east.xml", note)
        ajax(n, base, "tv1:f1:zonelist3", "tv1:f1:zonelist3",
             "tv1:f1:p1 tv1:f1:datums tv1:f1:resultP", "valueChange",
             tag + "_3zone.xml", note)

        f = dict(base)
        f.update({
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "tv1:f1:cmdb",
            "javax.faces.partial.execute": "@all",
            "javax.faces.partial.render": "@all",
            "tv1:f1:cmdb": "tv1:f1:cmdb",
        })
        name = tag + ".html"
        rec, body = n.post(f, name, note=note)
        if not body:
            anchors["failures"].append(
                {"name": name, "reason": rec["error"] or "no body"})
            print("  FAILED %s: %s" % (name, rec["error"]))
            continue

        tr = H.parse_transform(body)
        spc = H.parse_spc(body)
        en, ee = echoed(body, "northing_input"), echoed(body, "easting_input")
        bad = []
        if "has expired" in body:
            bad.append("NCAT returned its 'page has expired or an error "
                       "occurred' page")
        if not H.has_result(body):
            bad.append("no result block in response")
        if en is None or ee is None:
            bad.append("response does not echo the SPC input fields")
        else:
            if not near(en, src["northing_m"], 5e-4):
                bad.append("echoed northing %r, sent %r"
                           % (en, src["northing_m"]))
            if not near(ee, src["easting_m"], 5e-4):
                bad.append("echoed easting %r, sent %r"
                           % (ee, src["easting_m"]))
        if src["zone_code"] not in (spc["zone"] or ""):
            bad.append("zone panel says %r, forced %r"
                       % (spc["zone"], src["zone_code"]))
        if tr["in_frame"] != NATRF or tr["out_frame"] != NATRF:
            bad.append("frames are %r -> %r, asked %r -> %r"
                       % (tr["in_frame"], tr["out_frame"], NATRF, NATRF))

        row = {
            "name": name,
            "inverse_of": src["name"],
            "zone_code": src["zone_code"],
            "zone_token": zt,
            "input_northing_m": src["northing_m"],
            "input_easting_m": src["easting_m"],
            "input_units": "m",
            "echoed_northing": en,
            "echoed_easting": ee,
            "input_datum": NATRF,
            "output_datum": NATRF,
            "forward_input_lat_dd": src["input_lat_dd"],
            "forward_input_lon_dd": src["input_lon_dd"],
            "returned_lat_dd": H.last_dd(tr["out_lat_cell"]),
            "returned_lon_dd": H.last_dd(tr["out_lon_cell"]),
            "returned_lat_cell": tr["out_lat_cell"],
            "returned_lon_cell": tr["out_lon_cell"],
            "reprojected_zone": spc["zone"],
            "reprojected_northing_m": spc["northing"]["m"],
            "reprojected_easting_m": spc["easting"]["m"],
            "reprojected_scale_factor": spc["scale_factor"],
            "reprojected_convergence": spc["convergence"],
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
            print("  %-14s %-16s N %s E %s -> %s , %s   (forward input %s , %s)"
                  % (name, src["name"], src["northing_m"], src["easting_m"],
                     row["returned_lat_dd"], row["returned_lon_dd"],
                     row["forward_input_lat_dd"], row["forward_input_lon_dd"]))

    mp = n.write_manifest("inverse_manifest.json")
    anchors["counts"]["inverse_anchors"] = len(anchors["inverse_anchors"])
    anchors["counts"]["failures"] = len(anchors["failures"])
    anchors["counts"]["inverse_http_requests"] = len(n.records)
    with open(ap, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(anchors, fh, indent=2, sort_keys=True)
    print("\ninverse manifest: %s sha256 %s" % (mp, H.C.sha256_file(mp)))
    print("anchors rewritten: %s sha256 %s" % (ap, H.C.sha256_file(ap)))
    print("counts: %s" % anchors["counts"])


if __name__ == "__main__":
    main()
