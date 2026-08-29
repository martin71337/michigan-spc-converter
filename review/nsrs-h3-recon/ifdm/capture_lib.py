"""Shared capture helper for the H3 IFDM2022 recon.

Copied from review/nsrs-n0/capture_lib.py with the raw/ root repointed here
and POST support added (the beta NCAT download buttons are JSF form submits).

Not production code. Every fetch records URL, HTTP status, byte count,
SHA-256, capture timestamp. HTTP errors are captured as evidence, never
swallowed -- a refusal from NGS is a fact about the published record.
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
CAPTURE_DATE = "2026-08-29"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MCX-H3-IFDM-capture/1.0 "
    "(Michigan SPC converter; measurement only)"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, *, timeout=90, method="GET", data=None, headers=None, cookies=None):
    """Fetch a URL. Returns a record dict; never raises on HTTP status."""
    body_bytes = None
    if data is not None:
        if isinstance(data, dict):
            body_bytes = urllib.parse.urlencode(data).encode("utf-8")
        else:
            body_bytes = data
    req = urllib.request.Request(url, data=body_bytes, method=method)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "*/*")
    if body_bytes is not None and not (headers or {}).get("Content-Type"):
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if cookies:
        req.add_header("Cookie", "; ".join("%s=%s" % kv for kv in cookies.items()))
    rec = {
        "url": url,
        "method": method,
        "captured": _now(),
        "status": None,
        "reason": None,
        "headers": {},
        "body": None,
        "bytes": None,
        "sha256": None,
        "error": None,
        "final_url": None,
    }
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            rec["status"] = resp.status
            rec["reason"] = resp.reason
            rec["headers"] = dict(resp.headers.items())
            rec["final_url"] = resp.geturl()
            if method != "HEAD":
                b = resp.read()
                rec["body"] = b
                rec["bytes"] = len(b)
                rec["sha256"] = sha256_bytes(b)
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
        rec["sha256"] = sha256_bytes(b)
        rec["error"] = "HTTPError %s %s" % (exc.code, exc.reason)
    except Exception as exc:
        rec["error"] = "%s: %s" % (type(exc).__name__, exc)
    return rec


def head(url, *, timeout=90):
    return fetch(url, timeout=timeout, method="HEAD")


def save(rec, name, *, subdir=""):
    if rec.get("body") is None:
        return None
    d = os.path.join(RAW, subdir) if subdir else RAW
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    with open(path, "wb") as fh:
        fh.write(rec["body"])
    return path


def describe(rec, path=None):
    bits = ["%s %s" % (rec["method"], rec["url"])]
    bits.append("  status=%s %s" % (rec["status"], rec["reason"] or ""))
    if rec["error"]:
        bits.append("  error=%s" % rec["error"])
    if rec["bytes"] is not None:
        bits.append("  bytes=%s sha256=%s" % (rec["bytes"], rec["sha256"]))
    for h in ("Content-Length", "Content-Type", "Content-Disposition", "Last-Modified"):
        v = rec["headers"].get(h)
        if v:
            bits.append("  %s=%s" % (h, v))
    if rec.get("final_url") and rec["final_url"] != rec["url"]:
        bits.append("  final_url=%s" % rec["final_url"])
    if path:
        bits.append("  saved=%s" % os.path.relpath(path, HERE).replace("\\", "/"))
    return "\n".join(bits)


def write_manifest(records, name):
    out = []
    for rec, path in records:
        r = {k: v for k, v in rec.items() if k != "body"}
        r["saved"] = os.path.relpath(path, HERE).replace("\\", "/") if path else None
        out.append(r)
    os.makedirs(RAW, exist_ok=True)
    p = os.path.join(RAW, name)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
    return p


def preview(rec, n=400):
    if rec.get("body") is None:
        return "(no body)"
    return rec["body"][:n].decode("utf-8", "replace")
