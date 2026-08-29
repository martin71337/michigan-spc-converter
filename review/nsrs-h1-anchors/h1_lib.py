"""Shared driver for the H1 anchor capture -- beta NCAT's JSF form.

NOT production code, and nothing in michspc/ may import it. It exists so every
file under review/nsrs-h1-anchors/raw/ can be reproduced by re-running the
scripts beside it.

The approach is inherited verbatim from review/nsrs-n0/capture_ncat_beta.py:
beta NCAT (https://beta.ngs.noaa.gov/NCAT/) is a JSF/PrimeFaces app with no
REST equivalent for NATRF2022, so the only way to measure it is to submit its
own form inside its own session. Known and accepted from N0: HTML digests are
NOT reproducible across fetches (fresh jsessionid + ViewState every time), so
a digest here attests to the saved file only.

Two things this module adds over the N0 harness, both because H1 issues ~80
requests where N0 issued 8:

  1. the ViewState is refreshed from every response (a JSF server keeps only a
     bounded number of logical views per session; reusing one stale token
     eighty times invites ViewExpiredException mid-lattice), and
  2. every response is checked for a result block and for the zone and datum
     strings the caller asked for -- a response that does not name them is
     recorded as FAILED and never parsed for numbers.
"""

from __future__ import annotations

import html as _html
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
N0 = os.path.abspath(os.path.join(HERE, os.pardir, "nsrs-n0"))
if N0 not in sys.path:
    sys.path.insert(0, N0)

import capture_lib as C  # noqa: E402  (shared hashing/manifest helper from N0)

APP = "https://beta.ngs.noaa.gov/NCAT/"
CAPTURE_DATE = "2026-08-28"
THROTTLE_S = 1.0

NATRF = "NATRF2022 epoch 2020.00"
NAD83 = "NAD83(2011) epoch 2010.00"


# ---------------------------------------------------------------- formatting

def dd(v: float) -> str:
    """Decimal degrees as the form's own inputnumber wants them."""
    return "%.6f" % v


def dms(v: float, width: int) -> str:
    """DDMMSS.ss with a space separator, magnitude only -- the form's mask.

    The page's own defaults are '37 15 03.24' (lat) and '092 30 37.44' (lon),
    so width is 2 for latitude and 3 for longitude.
    """
    total = round(abs(v) * 3600.0, 4)
    d = int(total // 3600)
    rem = total - d * 3600
    m = int(rem // 60)
    s = rem - m * 60
    if round(s, 2) >= 60.0:          # defensive; never fires on this lattice
        s -= 60.0
        m += 1
    if m >= 60:
        m -= 60
        d += 1
    return "%0*d %02d %05.2f" % (width, d, m, s)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(s: str | None) -> str | None:
    """HTML fragment -> one line of text, entities resolved, tags to ' | '."""
    if s is None:
        return None
    t = re.sub(r"<sup>.*?</sup>", "", s, flags=re.S)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = _html.unescape(t)
    t = t.replace(" ", " ")
    lines = [ln.strip() for ln in t.split("\n")]
    return " | ".join(ln for ln in lines if ln)


def strip_sep(s: str | None):
    """Remove thousands separators. Returns (value, did_strip)."""
    if s is None:
        return None, False
    if re.search(r"\d,\d\d\d", s):
        return re.sub(r"(?<=\d),(?=\d\d\d)", "", s), True
    return s, False


# ------------------------------------------------------------------- session

class Ncat:
    def __init__(self):
        jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        self.op.addheaders = [("User-Agent", C.USER_AGENT)]
        self.page0 = None
        self.action = None
        self.viewstate = None
        self.records = []
        self._last = 0.0

    # -- plumbing ---------------------------------------------------------

    def _throttle(self):
        dt = time.time() - self._last
        if dt < THROTTLE_S:
            time.sleep(THROTTLE_S - dt)
        self._last = time.time()

    def open_app(self):
        """Fetch the app page; set the base form, action URL and ViewState."""
        self._throttle()
        with self.op.open(APP, timeout=120) as r:
            page = r.read().decode("utf-8", "replace")
            url = r.geturl()
        self.page0 = page
        m = re.search(r'<form[^>]*id="tv1:f1"[^>]*action="([^"]+)"', page)
        if not m:
            raise SystemExit("form tv1:f1 not found -- the app changed shape")
        self.action = urllib.parse.urljoin(url, m.group(1))
        vs = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]*)"',
                       page)
        self.viewstate = vs.group(1) if vs else None
        return page

    def base_fields(self) -> dict:
        f = form_fields(self.page0, "tv1:f1")
        if self.viewstate:
            f["javax.faces.ViewState"] = self.viewstate
        return f

    def post(self, fields: dict, name: str, *, note: str = ""):
        """POST the form. Saves the raw body; records the manifest entry."""
        self._throttle()
        data = urllib.parse.urlencode(fields).encode("utf-8")
        req = urllib.request.Request(self.action, data=data, method="POST")
        req.add_header("Content-Type",
                       "application/x-www-form-urlencoded; charset=UTF-8")
        req.add_header("Faces-Request", "partial/ajax")
        req.add_header("X-Requested-With", "XMLHttpRequest")
        rec = {
            "name": name,
            "note": note,
            "url": scrub_url(self.action),
            "method": "POST",
            "captured": _now(),
            "status": None,
            "error": None,
            "bytes": None,
            "sha256": None,
            "saved": None,
            "post_fields": scrub_fields(fields),
        }
        body = None
        try:
            with self.op.open(req, timeout=180) as r:
                rec["status"] = r.status
                body = r.read().decode("utf-8", "replace")
        except Exception as exc:
            rec["error"] = "%s: %s" % (type(exc).__name__, exc)
        if body is not None:
            raw = body.encode("utf-8")
            rec["bytes"] = len(raw)
            rec["sha256"] = C.sha256_bytes(raw)
            os.makedirs(RAW, exist_ok=True)
            p = os.path.join(RAW, name)
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
            rec["saved"] = "raw/" + name
            vs = re.search(
                r'<update id="[^"]*javax\.faces\.ViewState[^"]*">'
                r'<!\[CDATA\[(.*?)\]\]></update>', body, re.S)
            if vs:
                self.viewstate = vs.group(1)
        self.records.append(rec)
        return rec, body

    def write_manifest(self, name: str = "manifest.json") -> str:
        os.makedirs(RAW, exist_ok=True)
        p = os.path.join(RAW, name)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(self.records, fh, indent=2, sort_keys=True)
        return p


def scrub_url(u: str) -> str:
    return re.sub(r";jsessionid=[0-9A-Fa-f]+", ";jsessionid=<REDACTED>", u)


def scrub_fields(f: dict) -> dict:
    out = {}
    for k, v in f.items():
        if k == "javax.faces.ViewState":
            out[k] = "<REDACTED session token>"
        else:
            out[k] = v
    return out


def form_fields(html_text: str, form_id: str) -> dict:
    """Every input/select default inside the named JSF form (N0's parser)."""
    for m in re.finditer(r"<form\b.*?</form>", html_text, re.S):
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


# ---------------------------------------------------------------- extraction

def span(html_text: str, suffix: str):
    m = re.search(r'<span id="[^"]*:%s"[^>]*>(.*?)</span>'
                  % re.escape(suffix), html_text, re.S)
    return clean(m.group(1)) if m else None


def has_result(html_text: str) -> bool:
    return ("Transformed Coordinate" in html_text
            and 'javax.faces.ViewState' in html_text)


def last_dd(cell: str | None):
    """The decimal-degree line of a lat/lon cell ('DMS | packed | dd')."""
    if not cell:
        return None
    parts = [p.strip() for p in cell.split("|")]
    return parts[-1] if parts else None


def parse_transform(html_text: str) -> dict:
    """The 'Transformed Coordinate' block: input, output, change +/- sigma."""
    return {
        "in_lat_cell": span(html_text, "l1i"),
        "in_lon_cell": span(html_text, "l3i"),
        "in_frame": span(html_text, "l71i"),
        "in_epoch": span(html_text, "l8i"),
        "out_lat_cell": span(html_text, "l1o"),
        "out_lon_cell": span(html_text, "l3o"),
        "out_frame": span(html_text, "l71o"),
        "out_epoch": span(html_text, "l8o"),
        "lat_change_sigma": span(html_text, "l1u"),
        "lon_change_sigma": span(html_text, "l3u"),
        "eht_change_sigma": span(html_text, "l5u"),
    }


_NE = re.compile(r"([-\d.,]+|N/A)\s*(m|ift|usft)")


def _ne(cell: str | None) -> dict:
    """'251022.875 m | 823565.864 ift | N/A usft' -> {'m':..,'ift':..}."""
    out = {"m": None, "ift": None, "usft": None, "raw": cell,
           "thousands_stripped": False}
    if not cell:
        return out
    for val, unit in _NE.findall(cell):
        v, did = strip_sep(val)
        out[unit] = v
        out["thousands_stripped"] = out["thousands_stripped"] or did
    return out


def parse_spc(html_text: str) -> dict:
    """The SPC panel of the 'Converted Coordinate' block."""
    return {
        "zone": span(html_text, "zone1"),
        "northing": _ne(span(html_text, "s2")),
        "easting": _ne(span(html_text, "s5")),
        "scale_factor": span(html_text, "s9"),
        "combined_factor": span(html_text, "s10"),
        "distortion": span(html_text, "s11"),
        "convergence": span(html_text, "s8"),
        "conv_lat_cell": span(html_text, "l11o"),
        "conv_lon_cell": span(html_text, "l31o"),
    }
