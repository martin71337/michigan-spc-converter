"""Shared capture helper for the N0 measurement work package.

Not production code. Lives under review/ so every raw capture in
review/nsrs-n0/raw/ can be reproduced by re-running the scripts beside it.

Every fetch records: URL, HTTP status, byte count, SHA-256, capture timestamp.
Nothing is silently swallowed -- an HTTP error is captured as a finding, with
its body saved, because a refusal from NGS is evidence about the API contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
CAPTURE_DATE = "2026-08-28"

USER_AGENT = "MCX-N0-capture/1.0 (Michigan SPC converter; measurement only)"


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


def fetch(url: str, *, timeout: int = 60, method: str = "GET"):
    """Fetch a URL. Returns a record dict; never raises on HTTP status.

    record = {url, method, status, reason, headers, body (bytes or None),
              bytes, sha256, error, captured}
    """
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "*/*")
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
    }
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            rec["status"] = resp.status
            rec["reason"] = resp.reason
            rec["headers"] = dict(resp.headers.items())
            if method == "GET":
                body = resp.read()
                rec["body"] = body
                rec["bytes"] = len(body)
                rec["sha256"] = sha256_bytes(body)
            else:
                rec["bytes"] = None
    except urllib.error.HTTPError as exc:
        rec["status"] = exc.code
        rec["reason"] = exc.reason
        rec["headers"] = dict(exc.headers.items()) if exc.headers else {}
        try:
            body = exc.read()
        except Exception:  # pragma: no cover - defensive
            body = b""
        rec["body"] = body
        rec["bytes"] = len(body)
        rec["sha256"] = sha256_bytes(body)
        rec["error"] = "HTTPError %s %s" % (exc.code, exc.reason)
    except Exception as exc:  # URLError, timeout, TLS
        rec["error"] = "%s: %s" % (type(exc).__name__, exc)
    return rec


def head(url: str, *, timeout: int = 60):
    """HEAD request -- for files too large to download."""
    return fetch(url, timeout=timeout, method="HEAD")


def save(rec: dict, name: str, *, subdir: str = "") -> str | None:
    """Save a record's body under raw/<subdir>/<name>. Returns the path."""
    if rec.get("body") is None:
        return None
    d = os.path.join(RAW, subdir) if subdir else RAW
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    with open(path, "wb") as fh:
        fh.write(rec["body"])
    return path


def describe(rec: dict, path: str | None = None) -> str:
    bits = ["%s %s" % (rec["method"], rec["url"])]
    bits.append("  status=%s %s" % (rec["status"], rec["reason"] or ""))
    if rec["error"]:
        bits.append("  error=%s" % rec["error"])
    if rec["bytes"] is not None:
        bits.append("  bytes=%s sha256=%s" % (rec["bytes"], rec["sha256"]))
    cl = rec["headers"].get("Content-Length")
    ct = rec["headers"].get("Content-Type")
    lm = rec["headers"].get("Last-Modified")
    if cl:
        bits.append("  Content-Length=%s" % cl)
    if ct:
        bits.append("  Content-Type=%s" % ct)
    if lm:
        bits.append("  Last-Modified=%s" % lm)
    if path:
        bits.append("  saved=%s" % os.path.relpath(path, HERE))
    return "\n".join(bits)


def write_manifest(records: list, name: str) -> str:
    """Write a JSON manifest of a capture family (bodies excluded)."""
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


def preview(rec: dict, n: int = 400) -> str:
    if rec.get("body") is None:
        return "(no body)"
    try:
        return rec["body"][:n].decode("utf-8", "replace")
    except Exception:
        return repr(rec["body"][:n])
