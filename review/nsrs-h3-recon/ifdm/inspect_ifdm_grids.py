"""Dump the structure of every IFDM2022 NetCDF grid, without interpreting it.

The grids are NetCDF-4, i.e. HDF5 containers, so this needs h5py. Run it with
an interpreter that has h5py:

    <venv>/Scripts/python.exe inspect_ifdm_grids.py <path-to-IFDM2022.zip>

Writes raw/grids/ifdm2022_headers.txt (human-readable) and
raw/grids/ifdm2022_headers.json (machine-readable), plus a per-member SHA-256
manifest. Nothing here is production code; it exists so the recon's claims
about coverage, quantity and units can be checked against the files.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import zipfile

import h5py
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "raw", "grids")


def jsonable(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    if isinstance(v, np.ndarray):
        if v.size <= 8:
            return [jsonable(x) for x in v.tolist()]
        return "<array shape=%s dtype=%s>" % (v.shape, v.dtype)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return repr(v)


def describe(f, name):
    info = {"member": name, "attrs": {}, "datasets": {}}
    for k, v in f.attrs.items():
        info["attrs"][k] = jsonable(v)

    def visit(path, obj):
        if isinstance(obj, h5py.Dataset):
            d = {
                "shape": list(obj.shape),
                "dtype": str(obj.dtype),
                "attrs": {k: jsonable(v) for k, v in obj.attrs.items()},
            }
            # First/last values of 1-D coordinate axes settle the geometry.
            if obj.ndim == 1 and obj.shape[0] > 0 and obj.dtype.kind in "fiu":
                a = obj[...]
                d["first"] = float(a[0])
                d["last"] = float(a[-1])
                d["n"] = int(a.shape[0])
                if a.shape[0] > 1:
                    d["step"] = float(a[1] - a[0])
            elif obj.ndim >= 2 and obj.dtype.kind == "f" and obj.size < 400_000_000:
                a = obj[...]
                finite = np.isfinite(a)
                d["finite_count"] = int(finite.sum())
                d["total_count"] = int(a.size)
                if finite.any():
                    d["min"] = float(np.nanmin(a[finite]))
                    d["max"] = float(np.nanmax(a[finite]))
            info["datasets"][path] = d

    f.visititems(visit)
    return info


def main():
    zp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        HERE, "raw", "ncat", "ifdm2022_grids__IFDM2022.zip")
    os.makedirs(OUT, exist_ok=True)
    z = zipfile.ZipFile(zp)
    members = [n for n in z.namelist() if n.lower().endswith(".nc")]
    members.sort()
    out = []
    lines = []
    lines.append("IFDM2022 grid archive: %s" % os.path.basename(zp))
    lines.append("archive sha256: %s" % hashlib.sha256(
        open(zp, "rb").read()).hexdigest() if os.path.getsize(zp) < (1 << 30)
        else "(too large to hash inline)")
    lines.append("")
    for n in members:
        data = z.read(n)
        dig = hashlib.sha256(data).hexdigest()
        with h5py.File(io.BytesIO(data), "r") as f:
            info = describe(f, n)
        info["sha256"] = dig
        info["uncompressed_bytes"] = len(data)
        out.append(info)
        lines.append("=" * 78)
        lines.append("%s   %d bytes   sha256=%s" % (n, len(data), dig))
        lines.append("-- file attributes --")
        for k, v in info["attrs"].items():
            lines.append("   %-28s %s" % (k, v))
        lines.append("-- datasets --")
        for path, d in info["datasets"].items():
            lines.append("   %s  shape=%s dtype=%s" % (path, d["shape"], d["dtype"]))
            for k in ("n", "first", "last", "step", "min", "max",
                      "finite_count", "total_count"):
                if k in d:
                    lines.append("      %-14s %s" % (k, d[k]))
            for k, v in d["attrs"].items():
                lines.append("      attr %-12s %s" % (k, v))
        lines.append("")
    txt = os.path.join(OUT, "ifdm2022_headers.txt")
    with open(txt, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    js = os.path.join(OUT, "ifdm2022_headers.json")
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
    print("wrote", txt)
    print("wrote", js)


if __name__ == "__main__":
    main()
