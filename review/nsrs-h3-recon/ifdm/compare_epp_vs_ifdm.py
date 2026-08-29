"""Is the IFDM2022 velocity field the same thing as the EPP2022 rotation?

Both describe how a point on the North American plate moves. The EPP2022
rotation is the RIGID plate rotation the beta NATRF2022 page publishes; the
IFDM2022 grid is a measured velocity field. If NATRF2022 rotates with the
plate, the part of a point's ITRF2020 motion that NATRF2022 does NOT absorb is
the difference between the two -- the intra-frame deformation. This script
measures that difference at the 12 frozen Michigan anchors.

Measurement only, no production code, no claim about what NCAT actually does.
Run with an interpreter that has h5py.
"""

from __future__ import annotations

import io
import json
import math
import os
import zipfile

import h5py
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP = os.path.join(HERE, "raw", "ncat", "ifdm2022_grids__IFDM2022.zip")
SAMPLES = os.path.join(HERE, "raw", "grids", "michigan_velocity_samples.json")
OUT = os.path.join(HERE, "raw", "grids")

A = 6378137.0
F = 1.0 / 298.257222101
E2 = F * (2.0 - F)
RHOSEC = math.degrees(1.0) * 3600.0
MAS = 1.0 / 1000.0 / RHOSEC  # radians per milliarcsecond

# EPP2022 North American plate rotation, mas/yr
# (frozen capture epp2022-beta-values.csv, via frame_experiment.py)
WX, WY, WZ = 0.046, -0.704, -0.047


def geodetic_to_ecef(lat_deg, lon_deg, h=0.0):
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = A / math.sqrt(1.0 - E2 * math.sin(lat) ** 2)
    return ((n + h) * math.cos(lat) * math.cos(lon),
            (n + h) * math.cos(lat) * math.sin(lon),
            (n * (1.0 - E2) + h) * math.sin(lat))


def epp_velocity_enu(lat_deg, lon_deg):
    """Rigid-plate surface velocity from the EPP2022 rotation, m/yr in ENU."""
    wx, wy, wz = WX * MAS, WY * MAS, WZ * MAS  # rad/yr
    x, y, z = geodetic_to_ecef(lat_deg, lon_deg)
    vx = wy * z - wz * y
    vy = wz * x - wx * z
    vz = wx * y - wy * x
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    e = -math.sin(lo) * vx + math.cos(lo) * vy
    n = (-math.sin(la) * math.cos(lo) * vx - math.sin(la) * math.sin(lo) * vy
         + math.cos(la) * vz)
    u = (math.cos(la) * math.cos(lo) * vx + math.cos(la) * math.sin(lo) * vy
         + math.sin(la) * vz)
    return e, n, u


def main():
    rows = json.load(open(SAMPLES, encoding="utf-8"))
    lines = []
    lines.append("EPP2022 rigid rotation vs IFDM2022 measured velocity, "
                 "at the 12 frozen Michigan frame anchors")
    lines.append("EPP2022 NA plate rotation: wx=%+.3f wy=%+.3f wz=%+.3f mas/yr"
                 % (WX, WY, WZ))
    lines.append("IFDM values bilinear from IFDM2022_vel_svel.nc "
                 "(0.1 deg global grid, mm/yr, crs epsg:9990)")
    lines.append("")
    lines.append("%-16s %18s %18s %18s" % (
        "anchor", "IFDM  (vE,vN) mm/yr", "EPP   (vE,vN) mm/yr",
        "IFDM-EPP     mm/yr"))
    out = []
    for r in rows:
        la, lo = r["lat"], r["lon_west_neg"]
        ie, iN = r["ve_bilinear_mm_yr"], r["vn_bilinear_mm_yr"]
        ee, en, _eu = epp_velocity_enu(la, lo)
        ee, en = ee * 1000.0, en * 1000.0  # m/yr -> mm/yr
        de, dn = ie - ee, iN - en
        lines.append("%-16s  %+8.3f %+8.3f   %+8.3f %+8.3f   %+8.3f %+8.3f"
                     % (r["anchor"], ie, iN, ee, en, de, dn))
        out.append({"anchor": r["anchor"], "lat": la, "lon": lo,
                    "ifdm_ve_mm_yr": ie, "ifdm_vn_mm_yr": iN,
                    "epp_ve_mm_yr": ee, "epp_vn_mm_yr": en,
                    "residual_ve_mm_yr": de, "residual_vn_mm_yr": dn,
                    "residual_over_10yr_mm": [de * 10, dn * 10]})
    lines.append("")
    lines.append("residual over a 10-year span (mm):")
    for o in out:
        lines.append("  %-16s dE=%+8.2f  dN=%+8.2f" % (
            o["anchor"], o["residual_over_10yr_mm"][0],
            o["residual_over_10yr_mm"][1]))
    txt = "\n".join(lines)
    print(txt)
    with open(os.path.join(OUT, "epp_vs_ifdm_michigan.txt"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(txt + "\n")
    with open(os.path.join(OUT, "epp_vs_ifdm_michigan.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
