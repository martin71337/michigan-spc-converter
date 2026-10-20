"""W0 harness: drive the compiled NGS HTDP v3.6.0 binary and freeze its output.

Run with `python -I drive_htdp.py --htdp-src DIR --binary PATH --out htdp_truth.json
[--compare-binary LABEL=PATH ...]`. Stdlib only.

What it does
------------
* Builds a lattice of Michigan positions (the box lat 41.5..48.5, lon -90.6..-82.0,
  four corners, Isle Royale, Great Lakes water points, grid-node / cell-edge
  points, the 45-degree FRMXYZ height-formula switch) plus three "beyond the
  box" probes that straddle the only velocity-region boundary found nearby
  (the lat-50 north edge of HTDP region 6, initbd.f:37-40).
* For each WGS 84 / ITRF menu frame (8,9,10,11,12,24,25,26) and each epoch
  (1997.0, 2005.0, 2010.0, 2015.5, 2020.0, 2026.8), at heights 0/200/600 m:
    forward   frame@t        -> NAD 83(2011)@2010.0   (menu 1)
    reverse   NAD 83@2010.0  -> frame@t
    roundtrip the forward run's PRINTED output fed back through the reverse
* Calendar-date entry (GETMDY option 1, htdp.f:7886-7922) vs the same date as a
  decimal year (option 2, htdp.f:7924-7970), both directions, frame 12.
* HTDP velocity option 2 (VELOC) over the lattice, NAD 83 frame and ITRF2008.
* Every run is executed in a fresh empty temp directory; stdin is recorded
  verbatim. Optional --compare-binary runs re-execute every run with another
  build and record whether every output file is byte-identical.

The HTDP source tree is treated as untrusted data: this script only hashes its
.f files; the only thing executed is the already-built binary.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import tempfile

FRAMES = {  # menu number -> (internal iopt per MENU1 htdp.f:4677-4753, name)
    1: (1, "NAD_83(2011/CORS96/2007)"),
    8: (18, "WGS84(G1150)"),
    9: (19, "WGS84(G1674)"),
    10: (15, "WGS84(G1762)"),
    11: (16, "WGS84(G2139)"),
    12: (17, "WGS84(G2296)"),
    24: (15, "ITRF2008 or IGS08/IGb08"),
    25: (16, "ITRF2014 or IGS14/IGb14"),
    26: (17, "ITRF2020 or IGS20/IGb20"),
}
WGS_ITRF_FRAMES = [8, 9, 10, 11, 12, 24, 25, 26]
EPOCHS = ["1997.0", "2005.0", "2010.0", "2015.5", "2020.0", "2026.8"]
HEIGHTS = [0.0, 200.0, 600.0]
CALENDAR_DATES = [(1, 1, 2010), (12, 31, 2024), (2, 29, 2024), (3, 1, 2025),
                  (10, 20, 2026), (1, 1, 2025), (7, 2, 2015), (10, 19, 2026)]


def lattice():
    pts = []
    lats = [41.5 + k for k in range(8)]                    # 41.5 .. 48.5
    lons = [-90.6 + k * (8.6 / 7.0) for k in range(8)]     # -90.6 .. -82.0
    for i, la in enumerate(lats):
        for j, lo in enumerate(lons):
            pts.append((la, lo, "grid r%d c%d" % (i, j)))
    special = [
        (48.0, -88.9, "Isle Royale"),
        (47.85, -89.15, "Isle Royale SW (Windigo)"),
        (47.5, -87.5, "Lake Superior water"),
        (46.9, -85.0, "Lake Superior water east"),
        (43.5, -87.0, "Lake Michigan water"),
        (45.2, -86.6, "Lake Michigan north water"),
        (44.6, -82.6, "Lake Huron water"),
        (41.8, -82.6, "Lake Erie water"),
        (42.45, -82.7, "Lake St. Clair water"),
        (43.82, -84.77, "Clare"),
        (47.12, -88.57, "Houghton"),
        (42.33, -83.05, "Detroit"),
        (46.5, -84.35, "Sault Ste. Marie"),
        (44.0, -85.0, "velocity-grid node (nominal)"),
        (44.25, -85.25, "velocity-grid cell centre (nominal)"),
        (44.5, -85.75, "velocity-grid node (nominal) 2"),
        (45.0, -84.5, "45N exactly (FRMXYZ height switch htdp.f:957)"),
        (45.0001, -84.5, "just N of 45"),
        (44.9999, -84.5, "just S of 45"),
    ]
    pts.extend(special)
    beyond = [
        (49.9, -88.0, "BEYOND box: Ontario 49.9N (region 6 grid)"),
        (50.0, -88.0, "BEYOND box: 50.0N nominal (region 6 edge)"),
        (50.1, -88.0, "BEYOND box: Ontario 50.1N (region 14 plate)"),
    ]
    out = []
    for n, (la, lo, lab) in enumerate(pts):
        out.append({"id": "P%03d" % n, "lat": "%.6f" % la, "lon_east": "%.6f" % lo,
                    "label": lab, "in_box": True})
    for n, (la, lo, lab) in enumerate(beyond):
        out.append({"id": "B%03d" % n, "lat": "%.6f" % la, "lon_east": "%.6f" % lo,
                    "label": lab, "in_box": False})
    return out


def lattice_input_lines(lat_pts):
    lines = []
    for p in lat_pts:
        lonw = "%.6f" % (-float(p["lon_east"]))
        for h in HEIGHTS:
            name = "%sH%03d" % (p["id"], int(h))
            lines.append("%s,%s,%.3f,%s" % (p["lat"], lonw, h, name))
    return lines


DATA_RE = re.compile(r"^\s*(-?\d+\.\d{10})\s+(-?\d+\.\d{10})\s+(-?\d+\.\d{3})\s{4}(\S.*?)\s*$")
OUTSIDE_RE = re.compile(r"^\s*(\S+) is outside of the modeled region\.")
HDR_RE = re.compile(r"TRANSFORMING POSITIONS FROM (.{24}) \(EPOCH = (\d\d-\d\d-\d{4}) \(\s*([\d.]+)\)\)")
HDR2_RE = re.compile(r"^\s+TO (.{24}) \(EPOCH = (\d\d-\d\d-\d{4}) \(\s*([\d.]+)\)\)")


def epoch_stdin(entry):
    if isinstance(entry, (tuple, list)):
        m, d, y = entry
        return "1\n%d %d %d\n" % (m, d, y)
    return "2\n%s\n" % entry


def run_trfpos(binary, f_in, f_out, e_in, e_out, input_lines):
    stdin = ("4\nout.txt\n%d\n%d\n" % (f_in, f_out) + epoch_stdin(e_in)
             + epoch_stdin(e_out) + "3\nin.txt\n0\n0\n")
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "in.txt"), "w", newline="\n") as fh:
            fh.write("\n".join(input_lines) + "\n")
        cp = subprocess.run([binary], input=stdin.encode(), cwd=td,
                            capture_output=True, timeout=300)
        with open(os.path.join(td, "out.txt"), "rb") as fh:
            raw = fh.read()
    return stdin, cp.returncode, raw


def parse_trfpos(raw):
    text = raw.decode("latin1")
    outs, hdr = [], {}
    for line in text.splitlines():
        m = HDR_RE.search(line)
        if m:
            hdr["in_frame"], hdr["in_epoch_mdy"], hdr["in_epoch_dec"] = m.group(1).strip(), m.group(2), m.group(3)
            continue
        m = HDR2_RE.search(line)
        if m:
            hdr["out_frame"], hdr["out_epoch_mdy"], hdr["out_epoch_dec"] = m.group(1).strip(), m.group(2), m.group(3)
            continue
        m = DATA_RE.match(line)
        if m:
            outs.append({"name": m.group(4), "lat": m.group(1), "lonW": m.group(2), "eht": m.group(3)})
            continue
        m = OUTSIDE_RE.match(line)
        if m:
            outs.append({"name": m.group(1), "outside": True})
    return hdr, outs


def run_veloc(binary, f_menu, lat_pts):
    lines = ["%s,%s,%s" % (p["lat"], "%.6f" % (-float(p["lon_east"])), p["id"]) for p in lat_pts]
    stdin = "2\nvel.txt\n%d\n5\nvin.txt\n0\n0\n" % f_menu
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "vin.txt"), "w", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        cp = subprocess.run([binary], input=stdin.encode(), cwd=td, capture_output=True, timeout=300)
        with open(os.path.join(td, "vel.txt"), "rb") as fh:
            raw = fh.read()
    out = []
    for line in raw.decode("latin1").splitlines():
        m = re.match(r"^(\S+)\s+.*[NS]\s+.*[EW]\s+(-?\d+\.\d\d)\s+(-?\d+\.\d\d)\s+(-?\d+\.\d\d)\s*$", line)
        if m:
            out.append({"id": m.group(1), "vn": m.group(2), "ve": m.group(3), "vu": m.group(4)})
    return {"stdin": stdin, "input_lines": lines, "returncode": cp.returncode,
            "frame_menu": f_menu, "outputs": out, "raw_sha256": hashlib.sha256(raw).hexdigest()}


def read_git_head(src):
    """Read the checked-out commit as DATA (no git process inside the untrusted clone)."""
    try:
        with open(os.path.join(src, ".git", "HEAD"), encoding="ascii") as fh:
            head = fh.read().strip()
        if head.startswith("ref: "):
            ref = head[5:]
            p = os.path.join(src, ".git", *ref.split("/"))
            if os.path.exists(p):
                with open(p, encoding="ascii") as fh:
                    return fh.read().strip()
            with open(os.path.join(src, ".git", "packed-refs"), encoding="ascii") as fh:
                for line in fh:
                    if line.strip().endswith(" " + ref):
                        return line.split()[0]
            return None
        return head
    except OSError:
        return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--htdp-src", required=True)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--binary-flags", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--compare-binary", action="append", default=[],
                    help="LABEL|FLAGS|PATH: re-run every run and diff output bytes")
    args = ap.parse_args()

    lat_pts = lattice()
    base_lines = lattice_input_lines(lat_pts)

    plan = []  # (run_id, kind, f_in, f_out, e_in, e_out, lines or None(=roundtrip source))
    for fr in WGS_ITRF_FRAMES:
        for ep in EPOCHS:
            plan.append(("fwd_f%d_%s" % (fr, ep), "forward", fr, 1, ep, "2010.0", base_lines, None))
            plan.append(("rev_f%d_%s" % (fr, ep), "reverse", 1, fr, "2010.0", ep, base_lines, None))
            plan.append(("rt_f%d_%s" % (fr, ep), "roundtrip_reverse", 1, fr, "2010.0", ep, None,
                         "fwd_f%d_%s" % (fr, ep)))
    cal_lines = base_lines[:]  # whole lattice
    for (m, d, y) in CALENDAR_DATES:
        tag = "%04d-%02d-%02d" % (y, m, d)
        plan.append(("calfwd_%s" % tag, "calendar_forward", 12, 1, (m, d, y), "2010.0", cal_lines, None))
        plan.append(("calrev_%s" % tag, "calendar_reverse", 1, 12, "2010.0", (m, d, y), cal_lines, None))
        # same date as HTDP's own option-1 decimal year (htdp.f:7917-7919), repr'd
        import calendar
        doy = (datetime.date(y, m, d) - datetime.date(y, 1, 1)).days
        dec = repr(y + doy / (366.0 if calendar.isleap(y) else 365.0))
        plan.append(("decfwd_%s" % tag, "calendar_equiv_decimal_forward", 12, 1, dec, "2010.0", cal_lines, None))
        plan.append(("decrev_%s" % tag, "calendar_equiv_decimal_reverse", 1, 12, "2010.0", dec, cal_lines, None))

    runs, raws = [], {}
    by_id = {}
    for (rid, kind, fi, fo, ei, eo, lines, src) in plan:
        if src is not None:
            lines = ["%s,%s,%s,%s" % (o["lat"], o["lonW"], o["eht"], o["name"])
                     for o in by_id[src]["outputs"] if not o.get("outside")]
        stdin, rc, raw = run_trfpos(args.binary, fi, fo, ei, eo, lines)
        hdr, outs = parse_trfpos(raw)
        if len(outs) != len(lines):
            raise SystemExit("run %s: parsed %d outputs for %d inputs" % (rid, len(outs), len(lines)))
        rec = {"run_id": rid, "kind": kind, "frame_in_menu": fi, "frame_out_menu": fo,
               "frame_in_iopt": FRAMES[fi][0], "frame_out_iopt": FRAMES[fo][0],
               "epoch_in_entry": list(ei) if isinstance(ei, tuple) else ei,
               "epoch_out_entry": list(eo) if isinstance(eo, tuple) else eo,
               "header": hdr, "stdin": stdin, "returncode": rc,
               "roundtrip_source": src, "input_lines": lines, "outputs": outs,
               "raw_sha256": hashlib.sha256(raw).hexdigest()}
        runs.append(rec)
        by_id[rid] = rec
        raws[rid] = (fi, fo, ei, eo, lines, raw)
        print(rid, rc, hdr.get("in_epoch_mdy"), hdr.get("out_epoch_mdy"), len(outs), flush=True)

    vel = [run_veloc(args.binary, 1, lat_pts), run_veloc(args.binary, 24, lat_pts)]

    compares = []
    for spec in args.compare_binary:
        label, flags, path = spec.split("|", 2)
        nsame = ndiff = 0
        diffs = []
        for rid, (fi, fo, ei, eo, lines, raw) in raws.items():
            _, rc2, raw2 = run_trfpos(path, fi, fo, ei, eo, lines)
            if raw2 == raw:
                nsame += 1
            else:
                ndiff += 1
                _, o1 = parse_trfpos(raw)
                _, o2 = parse_trfpos(raw2)
                nd = [(a["name"], a, b) for a, b in zip(o1, o2) if a != b]
                diffs.append({"run_id": rid, "n_records_differing": len(nd), "examples": nd[:3]})
        v2 = [run_veloc(path, 1, lat_pts), run_veloc(path, 24, lat_pts)]
        vsame = all(a["raw_sha256"] == b["raw_sha256"] for a, b in zip(vel, v2))
        compares.append({"label": label, "flags": flags, "binary_sha256": sha256_file(path),
                         "runs_byte_identical": nsame, "runs_differing": ndiff, "diffs": diffs,
                         "velocity_runs_byte_identical": vsame})
        print("compare", label, nsame, ndiff, vsame, flush=True)

    src_hashes = {f: sha256_file(os.path.join(args.htdp_src, f))
                  for f in sorted(os.listdir(args.htdp_src)) if f.endswith(".f")}
    gfv = subprocess.run(["gfortran", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    commit = read_git_head(args.htdp_src)
    prov = {
        "tool": "NGS HTDP v3.6.0 (htdp.f:27-28 'April 7, 2025')",
        "repository": "https://github.com/noaa-ngs/HTDP",
        "commit": commit,
        "source_sha256": src_hashes,
        "compiler": gfv,
        "binary_path": args.binary,
        "binary_sha256": sha256_file(args.binary),
        "binary_flags": args.binary_flags,
        "capture_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "stdin_template_trfpos": "4\\nout.txt\\n<IN_MENU>\\n<OUT_MENU>\\n<EPOCH_IN>\\n<EPOCH_OUT>\\n3\\nin.txt\\n0\\n0\\n "
                                 "where <EPOCH> is '2\\n<decimal>' or '1\\n<m> <d> <y>'; the exact stdin of every run is stored in that run",
        "input_record_format": "LAT,LON_POSITIVE_WEST,EHT_M,NAME (TRFPOS option 3, htdp.f:3175-3294); "
                               "output format 2f16.10,f10.3 (htdp.f:3293), longitude positive west",
        "frames_menu_to_iopt": {str(k): v for k, v in FRAMES.items()},
        "heights_m": HEIGHTS,
        "comparison_builds": compares,
        "harness": "review/wgs84-w0/drive_htdp.py",
    }
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"provenance": prov, "lattice": lat_pts, "runs": runs, "velocity_runs": vel},
                  fh, indent=0, separators=(",", ":"))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
