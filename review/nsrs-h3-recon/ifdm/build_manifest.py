"""Consolidate every fetch of the IFDM2022 recon into one manifest.

Merges the per-family manifests written by the capture scripts, adds a
SHA-256 for every file actually on disk under raw/, and records the files that
were fetched and then deleted (with their digests) so the record is complete
without carrying 444 MB of controls in the repository.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")

# Fetched, digest recorded, file removed from the tree afterwards.
# Reproduce by re-running capture_ncat_download.py.
DELETED = [
    {"name": "nadcon5_grids__Nadcon5.zip", "bytes": 369574557,
     "sha256": "261f7923f211dd671034d91e567ecd1ea147daf91d17bc9b1785abc52e4f79d7",
     "why": "control download, proves the JSF POST mechanism; not IFDM material"},
    {"name": "vertcon3_grids__Vertcon3.zip", "bytes": 74496559,
     "sha256": "af54f857cb6a9e80cdc4ddb25f7939896ecece21c4e03d14a3403aaf031cd4b4",
     "why": "control download, proves the JSF POST mechanism; not IFDM material"},
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    fetches = []
    for mp in sorted(glob.glob(os.path.join(RAW, "*_manifest.json"))):
        fam = os.path.basename(mp)
        for rec in json.load(open(mp, encoding="utf-8")):
            fetches.append({
                "family": fam,
                "url": rec.get("url"),
                "method": rec.get("method"),
                "status": rec.get("status"),
                "error": rec.get("error"),
                "bytes": rec.get("bytes"),
                "content_length": (rec.get("headers") or {}).get("Content-Length"),
                "content_type": (rec.get("headers") or {}).get("Content-Type"),
                "content_disposition":
                    (rec.get("headers") or {}).get("Content-Disposition"),
                "last_modified": (rec.get("headers") or {}).get("Last-Modified"),
                "sha256": rec.get("sha256"),
                "saved": rec.get("saved"),
                "captured": rec.get("captured"),
                "button": rec.get("button"),
                "why": rec.get("why"),
            })

    files = []
    for root, _dirs, names in os.walk(RAW):
        for n in sorted(names):
            p = os.path.join(root, n)
            files.append({
                "path": os.path.relpath(p, HERE).replace("\\", "/"),
                "bytes": os.path.getsize(p),
                "sha256": sha256_file(p),
            })

    ok = sum(1 for f in fetches if f["status"] == 200)
    out = {
        "capture_date": "2026-08-29",
        "purpose": "H3 recon: what NGS publishes about IFDM2022",
        "counts": {
            "fetches": len(fetches),
            "http_200": ok,
            "http_404": sum(1 for f in fetches if f["status"] == 404),
            "other_or_error": sum(1 for f in fetches
                                  if f["status"] not in (200, 404)),
            "files_on_disk": len(files),
            "bytes_on_disk": sum(f["bytes"] for f in files),
        },
        "fetches": fetches,
        "files_on_disk": files,
        "fetched_then_deleted": DELETED,
    }
    p = os.path.join(HERE, "MANIFEST.json")
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)

    lines = ["IFDM2022 recon capture manifest -- 2026-08-29",
             "fetches=%d (200=%d, 404=%d, other/error=%d); files on disk=%d, %d bytes"
             % (len(fetches), ok, out["counts"]["http_404"],
                out["counts"]["other_or_error"], len(files),
                out["counts"]["bytes_on_disk"]), ""]
    lines.append("-- every fetch, in capture order per family --")
    for f in fetches:
        lines.append("%-6s %-4s %-9s %s" % (
            f["method"], f["status"], f["bytes"] if f["bytes"] is not None
            else f.get("content_length") or "-", f["url"]))
        if f.get("button"):
            lines.append("        button=%s  %s" % (
                f["button"], f.get("content_disposition") or ""))
        if f["sha256"]:
            lines.append("        sha256=%s" % f["sha256"])
        if f["error"]:
            lines.append("        error=%s" % f["error"])
        if f["saved"]:
            lines.append("        saved=%s" % f["saved"])
    lines.append("")
    lines.append("-- fetched, digest recorded, then deleted from the tree --")
    for d in DELETED:
        lines.append("  %s  %d bytes  sha256=%s" % (d["name"], d["bytes"], d["sha256"]))
        lines.append("      %s" % d["why"])
    lines.append("")
    lines.append("-- files on disk --")
    for f in files:
        lines.append("  %12d  %s  %s" % (f["bytes"], f["sha256"], f["path"]))
    t = os.path.join(HERE, "MANIFEST.txt")
    with open(t, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("wrote", p)
    print("wrote", t)
    print("fetches=%d 200=%d 404=%d files=%d bytes=%d"
          % (len(fetches), ok, out["counts"]["http_404"], len(files),
             out["counts"]["bytes_on_disk"]))


if __name__ == "__main__":
    main()
