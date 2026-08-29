"""Drive the beta NCAT "Download IFDM2022 Grids" JSF button.

The beta NCAT app (https://beta.ngs.noaa.gov/NCAT/) carries three grid
download buttons in one JSF form (id tv1:j_idt564):

    tv1:j_idt564:j_idt584   Download Nadcon5 Grids   (doc: TR NOS NGS 63)
    tv1:j_idt564:j_idt592   Download Vertcon3 Grids  (doc: TR NOS NGS 68)
    tv1:j_idt564:j_idt597   Download IFDM2022 Grids  (NO doc link on page)

Also tv1:j_idt564:j_idt574 = Download NCAT (the jar + CLI).

A JSF commandButton is a plain form POST: every field of the form plus the
button's own name, plus javax.faces.ViewState, on the session the GET
established. So: GET the page with a cookie jar, scrape the ViewState and the
form action, POST the button.

All three grid buttons are exercised, not just IFDM2022 -- Nadcon5 and
Vertcon3 are the controls that prove the POST mechanism works, so an IFDM2022
failure can be read as a fact about IFDM2022 rather than about this script.
"""

from __future__ import annotations

import http.cookiejar
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture_lib as cl

BASE = "https://beta.ngs.noaa.gov/NCAT/"

BUTTONS = [
    ("ncat_jar", "tv1:j_idt564:j_idt574", "Download NCAT"),
    ("nadcon5_grids", "tv1:j_idt564:j_idt584", "Download Nadcon5 Grids"),
    ("vertcon3_grids", "tv1:j_idt564:j_idt592", "Download Vertcon3 Grids"),
    ("ifdm2022_grids", "tv1:j_idt564:j_idt597", "Download IFDM2022 Grids"),
]

FORM_ID = "tv1:j_idt564"


def build_opener():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", cl.USER_AGENT), ("Accept", "*/*")]
    return op, jar


def main():
    records = []
    op, jar = build_opener()

    # 1. GET the page on a live session.
    req = urllib.request.Request(BASE)
    with op.open(req, timeout=90) as resp:
        page = resp.read()
        page_url = resp.geturl()
    rec = {
        "url": BASE,
        "method": "GET",
        "captured": cl._now(),
        "status": 200,
        "reason": "OK",
        "headers": {},
        "body": page,
        "bytes": len(page),
        "sha256": cl.sha256_bytes(page),
        "error": None,
        "final_url": page_url,
        "note": "session GET establishing jsessionid for the JSF POSTs",
    }
    p = cl.save(rec, "ncat_session_page.html", subdir="ncat")
    print(cl.describe(rec, p))
    records.append((rec, p))

    text = page.decode("utf-8", "replace")
    vs = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', text)
    action = re.search(
        r'<form id="%s"[^>]*action="([^"]+)"' % re.escape(FORM_ID), text
    )
    if not vs or not action:
        print("FAILED to scrape ViewState or form action -- page shape changed")
        cl.write_manifest(records, "ncat_download_manifest.json")
        return
    view_state = vs.group(1)
    post_url = urllib.parse.urljoin(page_url, action.group(1))
    print("\nViewState=%s\nPOST url=%s\ncookies=%s\n" % (
        view_state, post_url, [c.name for c in jar]))

    # 2. POST each button.
    for name, btn_id, label in BUTTONS:
        fields = [
            (FORM_ID, FORM_ID),
            (btn_id, label),
            ("javax.faces.ViewState", view_state),
        ]
        body = urllib.parse.urlencode(fields).encode("utf-8")
        req = urllib.request.Request(post_url, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Referer", page_url)
        rec = {
            "url": post_url,
            "method": "POST",
            "captured": cl._now(),
            "status": None,
            "reason": None,
            "headers": {},
            "body": None,
            "bytes": None,
            "sha256": None,
            "error": None,
            "final_url": None,
            "button": btn_id,
            "button_label": label,
        }
        try:
            with op.open(req, timeout=600) as resp:
                rec["status"] = resp.status
                rec["reason"] = resp.reason
                rec["headers"] = dict(resp.headers.items())
                rec["final_url"] = resp.geturl()
                b = resp.read()
                rec["body"] = b
                rec["bytes"] = len(b)
                rec["sha256"] = cl.sha256_bytes(b)
        except urllib.error.HTTPError as exc:
            rec["status"] = exc.code
            rec["reason"] = exc.reason
            rec["headers"] = dict(exc.headers.items()) if exc.headers else {}
            try:
                b = exc.read()
            except Exception:
                b = b""
            rec["body"] = b
            rec["bytes"] = len(b)
            rec["sha256"] = cl.sha256_bytes(b)
            rec["error"] = "HTTPError %s %s" % (exc.code, exc.reason)
        except Exception as exc:
            rec["error"] = "%s: %s" % (type(exc).__name__, exc)

        ext = ".bin"
        cd = rec["headers"].get("Content-Disposition", "")
        m = re.search(r'filename="?([^";]+)"?', cd)
        if m:
            ext = "__" + m.group(1)
        elif "html" in (rec["headers"].get("Content-Type") or ""):
            ext = ".html"
        path = cl.save(rec, name + ext, subdir="ncat")
        print(cl.describe(rec, path))
        if rec.get("body") and rec["bytes"] < 4000:
            print("  preview:", cl.preview(rec, 600).replace("\n", " ")[:600])
        print()
        records.append((rec, path))

    p = cl.write_manifest(records, "ncat_download_manifest.json")
    print("manifest:", p)


if __name__ == "__main__":
    main()
