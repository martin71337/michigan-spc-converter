"""autozone-r0: ask NGS NCAT which zone it assigns to each probe point.

SPCS 83: production REST  https://geodesy.noaa.gov/api/ncat/llh  with NO
spcZone parameter -- NCAT then picks the zone itself and names it in
"spcZone".  inDatum == outDatum == NAD83(2011), so no transformation.

SPCS2022: beta NCAT web app (https://beta.ngs.noaa.gov/NCAT/), the same JSF
form review/nsrs-n0/capture_ncat_beta.py drives, input AND output
"NATRF2022 epoch 2020.00", zone list left on its empty "auto" option.

Every response is saved raw under raw/ncat_probe/.  Stdlib only.
Run:  py -I probe_ncat.py [83|22]
"""
from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw", "ncat_probe")
WORK = os.path.join(HERE, "work")
PREFIX = ""
UA = "MCX-autozone-recon/0.1 (owner: martin71337; survey software verification)"
PROD = "https://geodesy.noaa.gov/api/ncat/llh"
APP = "https://beta.ngs.noaa.gov/NCAT/"


def fetch(url, data=None, headers=None, opener=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA,
                                                         **(headers or {})})
    op = opener or urllib.request.build_opener()
    with op.open(req, timeout=120) as r:
        return r.read()


def save(name, body):
    os.makedirs(RAW, exist_ok=True)
    p = os.path.join(RAW, name)
    with open(p, "wb") as fh:
        fh.write(body)
    return hashlib.sha256(body).hexdigest()


def run83(points):
    out = []
    for i, pt in enumerate(points):
        q = urllib.parse.urlencode({"lat": "%.8f" % pt["lat"],
                                    "lon": "%.8f" % pt["lon"],
                                    "inDatum": "NAD83(2011)",
                                    "outDatum": "NAD83(2011)"})
        body = fetch(PROD + "?" + q)
        h = save(PREFIX + "spcs83_%03d.json" % i, body)
        try:
            z = json.loads(body).get("spcZone")
        except ValueError:
            z = "UNPARSEABLE"
        out.append(dict(pt, ncat_zone=z, raw=PREFIX + "spcs83_%03d.json" % i,
                        sha256=h))
        print(i, pt["tag"], z)
        time.sleep(0.4)
    return out


# --- beta JSF form (minimal transcription of capture_ncat_beta.py) -------
def form_fields(html, form_id):
    for m in re.finditer(r"<form\b.*?</form>", html, re.S):
        s = m.group(0)
        if 'id="%s"' % form_id not in s:
            continue
        fields = {}
        for inp in re.findall(r"<input[^>]*>", s):
            nm = re.search(r'name="([^"]*)"', inp)
            ty = re.search(r'type="([^"]*)"', inp)
            vl = re.search(r'value="([^"]*)"', inp)
            if not nm:
                continue
            t = (ty.group(1) if ty else "text").lower()
            if t in ("radio", "checkbox"):
                if "checked" in inp:
                    fields[nm.group(1)] = vl.group(1) if vl else "on"
                continue
            fields[nm.group(1)] = vl.group(1) if vl else ""
        for sel in re.finditer(
                r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', s, re.S):
            nm, inner = sel.group(1), sel.group(2)
            hit = (re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', inner)
                   or re.search(r'<option[^>]*value="([^"]*)"[^>]*selected',
                                inner))
            first = re.search(r'<option[^>]*value="([^"]*)"', inner)
            fields[nm] = hit.group(1) if hit else (first.group(1) if first else "")
        return fields
    raise SystemExit("form not found")


def dms(v, width):
    a = abs(v)
    d = int(a)
    m = int((a - d) * 60)
    s = (a - d - m / 60.0) * 3600
    return ("%0" + str(width) + "d %02d %08.5f") % (d, m, s)


def run22(points, indatum="NATRF2022 epoch 2020.00",
          outdatum="NATRF2022 epoch 2020.00"):
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(APP, headers={"User-Agent": UA})
    with op.open(req, timeout=120) as r:
        page = r.read().decode("utf-8", "replace")
        final_url = r.geturl()
    save("beta_app_page.html", page.encode("utf-8"))
    action = urllib.parse.urljoin(final_url, re.search(
        r'<form[^>]*id="tv1:f1"[^>]*action="([^"]+)"', page).group(1))
    base = form_fields(page, "tv1:f1")
    out = []
    for i, pt in enumerate(points):
        f = dict(base)
        lat, lon = pt["lat"], pt["lon"]
        f.update({
            "tv1:f1:cotype": "horz", "tv1:f1:proj1": "llh",
            "tv1:f1:lat_input": "%.8f" % lat, "tv1:f1:lon_input": "%.8f" % lon,
            "tv1:f1:lat_hinput": "%.8f" % lat, "tv1:f1:lon_hinput": "%.8f" % lon,
            "tv1:f1:latd": dms(lat, 2), "tv1:f1:lond": dms(lon, 3),
            "tv1:f1:latdir_input": "N", "tv1:f1:londir_input": "W",
            "tv1:f1:indatum_input": indatum,
            "tv1:f1:outdatum_input": outdatum,
            # zonelist left at the page's own default, 'Auto Pick (default zone)'
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "tv1:f1:cmdb",
            "javax.faces.partial.execute": "@all",
            "javax.faces.partial.render": "tv1:f1:messages tv1:f1:resultP",
            "tv1:f1:cmdb": "tv1:f1:cmdb",
        })
        body = fetch(action, data=urllib.parse.urlencode(f).encode(),
                     headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                              "Faces-Request": "partial/ajax",
                              "X-Requested-With": "XMLHttpRequest"}, opener=op)
        h = save(PREFIX + "spcs2022_%03d.html" % i, body)
        t = re.sub(r"<[^>]+>", "\n", body.decode("utf-8", "replace"))
        t = re.sub(r"\n\s*\n+", "\n", t)
        # The result panel was relabelled 'Converted Coordinate' (it read
        # 'Transformed Coordinate' at the 2026-08-29 capture).
        j = t.find("Converted Coordinate")
        blk = t[j:j + 3000] if j >= 0 else ""
        m = re.search(r"\nZone\n([^\n]*)", blk)
        z = (m.group(1).replace("\xa0", " ").strip() if m
             else ("NO ZONE ROW" if j >= 0 else "NO RESULT BLOCK"))
        nm = re.search(r"\nNorthing\n([^\n]*)", blk)
        msg = re.findall(r'ui-messages-\w+-(?:summary|detail)">([^<]*)',
                         body.decode("utf-8", "replace"))
        out.append(dict(pt, ncat_zone=z, raw=PREFIX + "spcs2022_%03d.html" % i,
                        northing=nm.group(1).replace("\xa0", " ").strip()
                        if nm else None, sha256=h, messages=msg))
        print(i, pt["tag"], z)
        time.sleep(1.0)
    return out


def main():
    which = sys.argv[1]
    src = sys.argv[2] if len(sys.argv) > 2 else "probe_points.json"
    global PREFIX
    PREFIX = "r2_" if src != "probe_points.json" else ""
    pts = json.load(open(os.path.join(WORK, src), encoding="utf-8"))
    if which == "83":
        res = run83(pts["spcs83"])
    else:
        res = run22(pts["spcs2022"])
    with open(os.path.join(WORK, "%sncat_%s.json" % (PREFIX, which)), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(res, fh, indent=1)


if __name__ == "__main__":
    main()
