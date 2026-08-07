"""Drive every pipeline through the program's REAL file path and compare to NCAT.

Entry point used (the same one the GUI uses, michspc/gui/window.py):
    settings = michspc.job.JobSettings(...)
    result   = michspc.job.run(settings)          # reads the input file itself
    paths    = michspc.fileio.exports.write_all(result)   # writes the ZIP
then the audit CSV (<stem>_full.csv) is parsed OUT OF THE ZIP.

Longitude convention selected for EVERY run: NEGATIVE_WEST (-84.37), matching
NCAT. Stated in each job record inside each ZIP.

No core math function is called directly anywhere in this script. The only
program imports are JobSettings/run/write_all plus the zone/unit registries
needed to construct settings (the same registries the GUI dropdowns use).

Truth values come exclusively from the raw JSON captures in raw/. Elevation
and combined factor truth are re-derived here from NCAT's scale factor, the
geoid API's N, the point's H, and the program's own cited earth radius
R = 6,372,000 m (michspc/spc/factors.py, NOAA Manual NOS NGS 5 PDF p. 59) --
that derivation is the check, so using the constant is not circular.
"""
import csv
import io
import json
import math
import os
import sys
import zipfile
from pathlib import Path

HERE = Path(r"C:\claude-projects\coord-convert\review\ncat-crosscheck")
REPO = Path(r"C:\claude-projects\coord-convert")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

from points_def import POINTS, NS_PROBE

from michspc.fileio import exports
from michspc.job import Direction, JobSettings, LongitudeConvention, run
from michspc.spc.units import unit_by_code
from michspc.spc.zones import zone_by_code

RAW = HERE / "raw"
INPUTS = HERE / "inputs"
OUTPUTS = HERE / "outputs"

R_MEAN = 6_372_000.0  # meters; the program's cited constant, re-derivation input

UNITS = ["m", "ift", "usft"]
UNIT_M = {"m": 1.0, "ift": 0.3048, "usft": 1200.0 / 3937.0}
UNIT_FIELD = {"m": ("spcNorthing_m", "spcEasting_m"),
              "ift": ("spcNorthing_ift", "spcEasting_ift"),
              "usft": ("spcNorthing_usft", "spcEasting_usft")}

TOL_LINEAR_M = 0.002        # single-leg northing/easting
TOL_LINEAR_CHAIN_M = 0.004  # chained zone-to-zone
TOL_GEOID_M = 0.002
TOL_SCALE = 2e-8
TOL_CONV_AS = 0.02          # arcseconds
TOL_EF = 2e-8               # derived-quantity class, same order as scale factor
TOL_CF = 2e-8

POINT = {pid: (zone, lat, lon, h) for pid, zone, lat, lon, h, _r in POINTS}
POINT["NS"] = (None, NS_PROBE[2], NS_PROBE[3], NS_PROBE[4])


def raw_json(name):
    p = RAW / f"{name}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def num(s):
    return float(str(s).replace(",", ""))


def dms_to_arcsec(text):
    """'01 05 03.07' or '-00 46 16.56' or '+01 05 03.07' -> signed arcseconds."""
    t = text.strip()
    sign = -1.0 if t.startswith("-") else 1.0
    t = t.lstrip("+-")
    d, m, s = t.split()
    return sign * (int(d) * 3600 + int(m) * 60 + float(s))


rows_out = []       # comparison.csv rows
warnings_log = []   # every warning the program emitted, per run
run_log = []        # what was run, with what settings


def compare(point, pipeline, unit, quantity, program, truth, tol, truth_src,
            delta_m=None):
    """Record one comparison. program/truth may be None -> BLOCKED row."""
    if program is None or truth is None:
        rows_out.append([point, pipeline, unit, quantity, program, truth,
                         "", "", tol, "BLOCKED", truth_src])
        return
    delta = program - truth
    status = "PASS" if abs(delta) <= tol else "FAIL"
    rows_out.append([point, pipeline, unit, quantity,
                     repr(program), repr(truth), f"{delta:.10g}",
                     "" if delta_m is None else f"{delta_m:.10g}",
                     tol, status, truth_src])


def parse_audit(zip_path):
    """Return {point_id: {column: value}} from the audit CSV inside the ZIP."""
    with zipfile.ZipFile(zip_path) as z:
        audit_name = [n for n in z.namelist() if n.endswith("_full.csv")][0]
        text = z.read(audit_name).decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    header = rows[0]
    out = {}
    for r in rows[1:]:
        if not r:
            continue
        out[r[0]] = dict(zip(header, r))
    return out


def run_job(tag, input_lines, direction, src_zone, tgt_zone, in_unit, out_unit):
    """Write the input file, run the job through the file path, return audit."""
    in_path = INPUTS / f"{tag}.csv"
    in_path.write_text("\r\n".join(input_lines) + "\r\n", encoding="utf-8")
    out_dir = OUTPUTS / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    settings = JobSettings(
        input_path=in_path,
        output_directory=out_dir,
        direction=direction,
        source_zone=zone_by_code(src_zone) if src_zone else None,
        target_zone=zone_by_code(tgt_zone) if tgt_zone else None,
        input_unit=unit_by_code(in_unit),
        output_unit=unit_by_code(out_unit),
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        apply_geoid=True,
    )
    result = run(settings)
    paths = exports.write_all(result, overwrite=True)
    zip_path = paths["archive"]

    run_log.append(
        f"{tag}: direction={direction.value!r}, source_zone={src_zone}, "
        f"target_zone={tgt_zone}, input_unit={in_unit}, output_unit={out_unit}, "
        f"longitude_convention=NEGATIVE_WEST, apply_geoid=True, "
        f"input={in_path.name}, zip={zip_path.name}"
    )
    for pid, w in result.warnings:
        warnings_log.append(f"{tag} / point {pid}: [{w.code.value}] {w.message}")
    return parse_audit(zip_path)


def truth_factors(pid, k_truth):
    """(N_api, EF_truth, CF_truth) re-derived from truth inputs, or Nones."""
    g = raw_json(f"geoid_{pid}")
    if g is None or "geoidHeight" not in g:
        return None, None, None
    n_api = float(g["geoidHeight"])
    h = POINT[pid][3]
    ef = R_MEAN / (R_MEAN + h + n_api)
    cf = None if k_truth is None else k_truth * ef
    return n_api, ef, cf


def compare_factor_block(pid, pipeline, unit, audit_row, zone_for_k):
    """Compare geoid height, EF, CF (and nothing else) for one audit row."""
    llh = raw_json(f"llh_{pid}_{zone_for_k}")
    k_truth = float(llh["spcScaleFactor"]) if llh else None
    n_api, ef_truth, cf_truth = truth_factors(pid, k_truth)

    gh = audit_row["Geoid height (m)"]
    compare(pid, pipeline, unit, "geoid_height_m",
            None if gh == "N/A" else float(gh), n_api, TOL_GEOID_M,
            f"geoid_{pid}.json")
    ef = audit_row["Elevation factor"]
    compare(pid, pipeline, unit, "elevation_factor",
            None if ef == "N/A" else float(ef), ef_truth, TOL_EF,
            f"geoid_{pid}.json + derivation R/(R+H+N)")
    cf = audit_row["Combined factor"]
    compare(pid, pipeline, unit, "combined_factor",
            None if cf == "N/A" else float(cf), cf_truth, TOL_CF,
            f"llh_{pid}_{zone_for_k}.json k * derived EF")


# ===========================================================================
# Pipeline 1: geodetic -> SPC, per zone, all three output units
# ===========================================================================
for zone in ("2111", "2112", "2113"):
    zone_pts = [p for p in POINTS if p[1] == zone]
    lines = [f"{pid},{lat:.6f},{lon:.6f},{h:.3f},NCAT crosscheck {pid}"
             for pid, _z, lat, lon, h, _r in zone_pts]
    for unit in UNITS:
        audit = run_job(f"p1_{zone}_{unit}", lines,
                        Direction.GEODETIC_TO_ZONE, None, zone, "m", unit)
        for pid, _z, lat, lon, h, _r in zone_pts:
            row = audit[pid]
            llh = raw_json(f"llh_{pid}_{zone}")
            nf, ef_ = UNIT_FIELD[unit]
            tol_u = TOL_LINEAR_M / UNIT_M[unit]
            src = f"llh_{pid}_{zone}.json"
            n_prog = float(row["Target northing"])
            e_prog = float(row["Target easting"])
            n_truth = num(llh[nf]) if llh else None
            e_truth = num(llh[ef_]) if llh else None
            compare(pid, "geodetic->SPC " + zone, unit, "northing",
                    n_prog, n_truth, tol_u, src,
                    delta_m=(n_prog - n_truth) * UNIT_M[unit] if llh else None)
            compare(pid, "geodetic->SPC " + zone, unit, "easting",
                    e_prog, e_truth, tol_u, src,
                    delta_m=(e_prog - e_truth) * UNIT_M[unit] if llh else None)
            compare(pid, "geodetic->SPC " + zone, unit, "grid_scale_factor",
                    float(row["Grid scale factor"]),
                    float(llh["spcScaleFactor"]) if llh else None,
                    TOL_SCALE, src)
            compare(pid, "geodetic->SPC " + zone, unit, "convergence_arcsec",
                    dms_to_arcsec(row["Convergence"]),
                    dms_to_arcsec(llh["spcConvergence"]) if llh else None,
                    TOL_CONV_AS, src)
            compare_factor_block(pid, "geodetic->SPC " + zone, unit, row, zone)

# ===========================================================================
# Pipeline 2: SPC -> geodetic, per zone, all three input units
# ===========================================================================
M_PER_DEG_LAT = 111132.95


def lon_m_per_deg(lat):
    return 111319.49 * math.cos(math.radians(lat))


for zone in ("2111", "2112", "2113"):
    zone_pts = [p for p in POINTS if p[1] == zone]
    for unit in UNITS:
        lines = []
        for pid, _z, lat, lon, h, _r in zone_pts:
            llh = raw_json(f"llh_{pid}_{zone}")
            nf, ef_ = UNIT_FIELD[unit]
            h_u = h / UNIT_M[unit]
            lines.append(f"{pid},{num(llh[nf]):.3f},{num(llh[ef_]):.3f},"
                         f"{h_u:.6f},NCAT crosscheck {pid}")
        audit = run_job(f"p2_{zone}_{unit}", lines,
                        Direction.ZONE_TO_GEODETIC, zone, None, unit, unit)
        for pid, _z, lat0, lon0, h, _r in zone_pts:
            row = audit[pid]
            spc = raw_json(f"spc_{pid}_{zone}_{unit}")
            src = f"spc_{pid}_{zone}_{unit}.json"
            lat_t = float(spc["destLat"]) if spc else None
            lon_t = float(spc["destLon"]) if spc else None
            lat_p = float(row["Target northing"])
            lon_p = float(row["Target easting"])
            tol_lat_deg = TOL_LINEAR_M / M_PER_DEG_LAT
            tol_lon_deg = TOL_LINEAR_M / lon_m_per_deg(lat0)
            compare(pid, "SPC->geodetic " + zone, unit, "latitude_deg",
                    lat_p, lat_t, tol_lat_deg, src,
                    delta_m=(lat_p - lat_t) * M_PER_DEG_LAT if spc else None)
            compare(pid, "SPC->geodetic " + zone, unit, "longitude_deg",
                    lon_p, lon_t, tol_lon_deg, src,
                    delta_m=(lon_p - lon_t) * lon_m_per_deg(lat0) if spc else None)
            llh = raw_json(f"llh_{pid}_{zone}")
            compare(pid, "SPC->geodetic " + zone, unit, "grid_scale_factor",
                    float(row["Grid scale factor"]),
                    float(llh["spcScaleFactor"]) if llh else None,
                    TOL_SCALE, f"llh_{pid}_{zone}.json")
            compare(pid, "SPC->geodetic " + zone, unit, "convergence_arcsec",
                    dms_to_arcsec(row["Convergence"]),
                    dms_to_arcsec(llh["spcConvergence"]) if llh else None,
                    TOL_CONV_AS, f"llh_{pid}_{zone}.json")
            compare_factor_block(pid, "SPC->geodetic " + zone, unit, row, zone)

# ===========================================================================
# Pipeline 3: zone-to-zone, all six directed pairs, all three units
# ===========================================================================
PAIRS = [("2111", "2112", "C2"), ("2112", "2111", "C2"),
         ("2112", "2113", "S2"), ("2113", "2112", "S2"),
         ("2111", "2113", "NS"), ("2113", "2111", "NS")]

for src_zone, tgt_zone, pid in PAIRS:
    _hz, lat, lon, h = POINT[pid]
    for unit in UNITS:
        llh_src = raw_json(f"llh_{pid}_{src_zone}")
        llh_tgt = raw_json(f"llh_{pid}_{tgt_zone}")
        nf, ef_ = UNIT_FIELD[unit]
        h_u = h / UNIT_M[unit]
        lines = [f"{pid},{num(llh_src[nf]):.3f},{num(llh_src[ef_]):.3f},"
                 f"{h_u:.6f},NCAT crosscheck {pid}"]
        tag = f"p3_{src_zone}_to_{tgt_zone}_{unit}"
        audit = run_job(tag, lines, Direction.ZONE_TO_ZONE,
                        src_zone, tgt_zone, unit, unit)
        row = audit[pid]
        pipe = f"zone {src_zone}->{tgt_zone}"
        tol_u = TOL_LINEAR_CHAIN_M / UNIT_M[unit]
        src_file = f"llh_{pid}_{src_zone}.json -> llh_{pid}_{tgt_zone}.json"
        n_prog = float(row["Target northing"])
        e_prog = float(row["Target easting"])
        n_truth = num(llh_tgt[nf])
        e_truth = num(llh_tgt[ef_])
        compare(pid, pipe, unit, "northing", n_prog, n_truth, tol_u, src_file,
                delta_m=(n_prog - n_truth) * UNIT_M[unit])
        compare(pid, pipe, unit, "easting", e_prog, e_truth, tol_u, src_file,
                delta_m=(e_prog - e_truth) * UNIT_M[unit])
        compare(pid, pipe, unit, "source_grid_scale_factor",
                float(row["Source grid scale factor"]),
                float(llh_src["spcScaleFactor"]), TOL_SCALE,
                f"llh_{pid}_{src_zone}.json")
        compare(pid, pipe, unit, "source_convergence_arcsec",
                dms_to_arcsec(row["Source convergence"]),
                dms_to_arcsec(llh_src["spcConvergence"]), TOL_CONV_AS,
                f"llh_{pid}_{src_zone}.json")
        compare(pid, pipe, unit, "grid_scale_factor",
                float(row["Grid scale factor"]),
                float(llh_tgt["spcScaleFactor"]), TOL_SCALE,
                f"llh_{pid}_{tgt_zone}.json")
        compare(pid, pipe, unit, "convergence_arcsec",
                dms_to_arcsec(row["Convergence"]),
                dms_to_arcsec(llh_tgt["spcConvergence"]), TOL_CONV_AS,
                f"llh_{pid}_{tgt_zone}.json")
        compare_factor_block(pid, pipe, unit, row, tgt_zone)

# ===========================================================================
# Write outputs
# ===========================================================================
with open(HERE / "comparison.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["point", "pipeline", "unit", "quantity", "program_value",
                "truth_value", "delta", "delta_m_equiv", "tolerance",
                "status", "truth_source"])
    w.writerows(rows_out)

(HERE / "warnings_observed.txt").write_text(
    ("\n".join(warnings_log) + "\n") if warnings_log else "none\n",
    encoding="utf-8")
(HERE / "run_log.txt").write_text("\n".join(run_log) + "\n", encoding="utf-8")

# Summary: max |delta| per quantity class (coords normalized to meters)
classes = {}
fails = []
for r in rows_out:
    point, pipeline, unit, quantity = r[0], r[1], r[2], r[3]
    status = r[9]
    if status == "BLOCKED":
        fails.append(("BLOCKED", r))
        continue
    delta = abs(float(r[6]))
    if quantity in ("northing", "easting"):
        cls = "linear_chained_m" if pipeline.startswith("zone ") else "linear_m"
        d = abs(float(r[7]))
    elif quantity in ("latitude_deg", "longitude_deg"):
        cls, d = "geodetic_m_equiv", abs(float(r[7]))
    elif "scale" in quantity:
        cls, d = "grid_scale_factor", delta
    elif "convergence" in quantity:
        cls, d = "convergence_arcsec", delta
    elif quantity == "geoid_height_m":
        cls, d = "geoid_height_m", delta
    elif quantity == "elevation_factor":
        cls, d = "elevation_factor", delta
    else:
        cls, d = "combined_factor", delta
    if cls not in classes or d > classes[cls][0]:
        classes[cls] = (d, point, pipeline, unit, quantity)
    if status == "FAIL":
        fails.append(("FAIL", r))

print(f"rows: {len(rows_out)}")
print("max |delta| per class:")
for cls, (d, point, pipeline, unit, q) in sorted(classes.items()):
    print(f"  {cls:22s} {d:.3e}  ({point}, {pipeline}, {unit}, {q})")
print(f"failures/blocked: {len(fails)}")
for kind, r in fails:
    print(f"  {kind}: {r}")
counts = {}
for r in rows_out:
    counts[r[9]] = counts.get(r[9], 0) + 1
print("status counts:", counts)
print(f"warnings observed: {len(warnings_log)} (see warnings_observed.txt)")
