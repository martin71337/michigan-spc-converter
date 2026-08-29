"""N0 item 1 + item 3 -- beta NCAT (v3.0): frame and geopotential transformation.

Two surfaces are probed, and they are NOT the same thing:

  (a) the REST API  https://beta.ngs.noaa.gov/api/ncat/llh  -- legacy tokens only
  (b) the web app   https://beta.ngs.noaa.gov/NCAT/         -- JSF/PrimeFaces,
      server-rendered, whose datum dropdown DOES offer NATRF2022.

(b) has no REST equivalent on beta, so it is driven here the only way it can be
driven: by submitting its own form with its own ViewState, inside a session.
That is a MEASUREMENT harness, not a dependency. Nothing in MCX may call this.

Every probe -- including every failure -- is saved, because a refusal from NGS
documents the API's actual contract.

Run:  py -3 capture_ncat_beta.py
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import re
import urllib.parse
import urllib.request

import capture_lib as C

APP = "https://beta.ngs.noaa.gov/NCAT/"
SUB = "ncat"

BETA_REST = "https://beta.ngs.noaa.gov/api/ncat/llh"
PROD_REST = "https://geodesy.noaa.gov/api/ncat/llh"

# The Michigan test point used throughout the MCX record.
LAT, LON = 43.0, -84.5


# --------------------------------------------------------------------------
# (a) REST probes
# --------------------------------------------------------------------------

def rest_probes():
    """Probe the REST surface for modernized-NSRS tokens. Records failures."""
    out = []
    horiz_out = [
        "NATRF2022", "NATRF2022(2020.00)", "NATRF2022 epoch 2020.00",
        "NATRF2022 2020.00", "NATRF2022(2020.0)", "NA2022", "natrf2022",
        "NATRF", "MATRF2022", "CATRF2022", "PATRF2022",
        "ITRF2020", "IGS20", "WGS84",
        # controls: tokens known good on the legacy surface
        "NAD83(2011)", "NAD27", "NAD83(NSRS2007)",
    ]
    for base in (BETA_REST, PROD_REST):
        for tok in horiz_out:
            q = urllib.parse.urlencode({
                "lat": LAT, "lon": LON,
                "inDatum": "NAD83(2011)", "outDatum": tok,
            })
            out.append((C.fetch(base + "?" + q, timeout=45), None))
    # vertical / geopotential tokens
    vert = [
        ("NAVD88", "NAPGD2022"), ("NAVD88", "NAPGD2022(2022)"),
        ("NAVD88", "GEOID2022"), ("NAVD88", "NAPGD"), ("NAVD88", "napgd2022"),
        ("NGVD29", "NAPGD2022"),
        ("NGVD29", "NAVD88"),          # baseline control -- must succeed
        ("NAVD88", "NGVD29"),          # baseline control -- must succeed
    ]
    for base in (BETA_REST, PROD_REST):
        for vin, vout in vert:
            q = urllib.parse.urlencode({
                "lat": LAT, "lon": LON,
                "inDatum": "NAD83(2011)", "outDatum": "NAD83(2011)",
                "orthoHt": 200.0, "inVertDatum": vin, "outVertDatum": vout,
            })
            out.append((C.fetch(base + "?" + q, timeout=45), None))
    return out


# --------------------------------------------------------------------------
# (b) the JSF app
# --------------------------------------------------------------------------

def _opener():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", C.USER_AGENT)]
    return op


def get(op, url):
    with op.open(url, timeout=90) as r:
        return r.read().decode("utf-8", "replace"), r.geturl()


def post(op, url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type",
                   "application/x-www-form-urlencoded; charset=UTF-8")
    req.add_header("Faces-Request", "partial/ajax")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    with op.open(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


def form_fields(html, form_id):
    """Every input/select default inside the named JSF form."""
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
            if hit:
                fields[nm] = hit.group(1)
            else:
                first = re.search(r'<option[^>]*value="([^"]*)"', inner)
                fields[nm] = first.group(1) if first else ""
        return fields
    raise SystemExit("form %s not found" % form_id)


def convert(op, page, action, *, indatum, outdatum, zone=None,
            cotype="horz", proj1="llh", proj2=None, height=None, units="m"):
    f = form_fields(page, "tv1:f1")
    f["tv1:f1:cotype"] = cotype
    f["tv1:f1:proj1"] = proj1
    f["tv1:f1:lat_input"] = "%.6f" % LAT
    f["tv1:f1:lon_input"] = "%.6f" % LON
    f["tv1:f1:lat_hinput"] = "%.6f" % LAT
    f["tv1:f1:lon_hinput"] = "%.6f" % LON
    f["tv1:f1:latd"] = "43 00 00.00"
    f["tv1:f1:lond"] = "084 30 00.00"
    f["tv1:f1:latdir_input"] = "N"
    f["tv1:f1:londir_input"] = "W"
    f["tv1:f1:indatum_input"] = indatum
    f["tv1:f1:outdatum_input"] = outdatum
    if zone is not None:
        f["tv1:f1:zonelist_input"] = zone
    if proj2 is not None:
        f["tv1:f1:proj2"] = proj2
    if height is not None:
        f["tv1:f1:height_input"] = str(height)
        f["tv1:f1:height_hinput"] = str(height)
        f["tv1:f1:unitsx_input"] = units
    f.update({
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "tv1:f1:cmdb",
        "javax.faces.partial.execute": "@all",
        "javax.faces.partial.render": "@all",
        "tv1:f1:cmdb": "tv1:f1:cmdb",
    })
    return post(op, action, f)


def strip(html):
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&")
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t


def result_block(text):
    """The 'Transformed Coordinate' .. 'Export Results to' span of the page."""
    i = text.find("Transformed Coordinate")
    j = text.find("Export Results to", i)
    return text[i:j] if i >= 0 and j > i else "(no result block found)"


def main():
    d = os.path.join(C.RAW, SUB)
    os.makedirs(d, exist_ok=True)

    print("### REST probes (item 1 + item 3)")
    rest = rest_probes()
    recs = []
    for i, (r, _) in enumerate(rest):
        name = "rest_%02d.json" % i
        p = C.save(r, name, subdir=SUB)
        recs.append((r, p))
        body = C.preview(r, 200).replace("\n", " ")
        ok = '"error"' not in body
        print(("  OK  " if ok else "  --  "), r["url"][:140])
        print("        ", body[:150])
    C.write_manifest(recs, "ncat_rest_probes_manifest.json")

    print("\n### JSF app (item 1)")
    op = _opener()
    page, url = get(op, APP)
    p = os.path.join(d, "ncat_beta_app_page.html")
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(page)
    print("  app page saved: %s bytes sha256 %s" %
          (os.path.getsize(p), C.sha256_file(p)))
    action = urllib.parse.urljoin(
        url, re.search(r'<form[^>]*id="tv1:f1"[^>]*action="([^"]+)"',
                       page).group(1))

    cases = [
        ("nad83_2011_to_natrf2022_llh",
         dict(indatum="NAD83(2011) epoch 2010.00",
              outdatum="NATRF2022 epoch 2020.00")),
        ("natrf2022_to_nad83_2011_llh",
         dict(indatum="NATRF2022 epoch 2020.00",
              outdatum="NAD83(2011) epoch 2010.00")),
        ("nad83_2011_to_natrf2022_spc_260001",
         dict(indatum="NAD83(2011) epoch 2010.00",
              outdatum="NATRF2022 epoch 2020.00",
              zone="260001-MI (Statewide)")),
        ("nad83_2011_to_natrf2022_spc_261007",
         dict(indatum="NAD83(2011) epoch 2010.00",
              outdatum="NATRF2022 epoch 2020.00",
              zone="261007-MI L41Z (Multizone complete)")),
        ("nad83_2011_to_natrf2022_spc_261002",
         dict(indatum="NAD83(2011) epoch 2010.00",
              outdatum="NATRF2022 epoch 2020.00",
              zone="261002-MI L15D (Multizone complete)")),
        ("natrf2022_to_natrf2022_spc_261008",
         dict(indatum="NATRF2022 epoch 2020.00",
              outdatum="NATRF2022 epoch 2020.00",
              zone="261008-MI L45G (Multizone complete)")),
        # item 3: a height carried through the app, orthometric
        ("nad83_2011_to_natrf2022_orthoht200",
         dict(indatum="NAD83(2011) epoch 2010.00",
              outdatum="NATRF2022 epoch 2020.00",
              cotype="horzh", proj2="htOht", height=200.0, units="m")),
        ("nad83_2011_to_natrf2022_eht200",
         dict(indatum="NAD83(2011) epoch 2010.00",
              outdatum="NATRF2022 epoch 2020.00",
              cotype="horzh", proj2="htEht", height=200.0, units="m")),
    ]
    for name, kw in cases:
        resp = convert(op, page, action, **kw)
        ph = os.path.join(d, name + ".html")
        with open(ph, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(resp)
        txt = strip(resp)
        pt = os.path.join(d, name + ".txt")
        with open(pt, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(txt)
        print("\n--- %s  (%s bytes, sha256 %s)" %
              (name, os.path.getsize(ph), C.sha256_file(ph)))
        print(result_block(txt)[:1800])


if __name__ == "__main__":
    main()
