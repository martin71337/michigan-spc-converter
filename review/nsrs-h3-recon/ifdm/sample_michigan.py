"""Sample the IFDM2022 global velocity grid at the 12 frozen frame anchors.

Measurement, not a model: this reads the published nodes surrounding each
anchor and reports them raw, plus a plain bilinear value, so the recon can say
what magnitude an IFDM term could possibly contribute at Michigan latitudes
over a ten-year span. It deliberately does NOT claim to reproduce NGS's own
interpolation -- NGS's scheme for these grids is not documented in anything
captured here.

Run with an interpreter that has h5py.
"""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile

import h5py
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP = os.path.join(HERE, "raw", "ncat", "ifdm2022_grids__IFDM2022.zip")
ANCHORS = os.path.normpath(os.path.join(
    HERE, "..", "..", "nsrs-h1-anchors", "anchors.json"))
OUT = os.path.join(HERE, "raw", "grids")


def main():
    a = json.load(open(ANCHORS, encoding="utf-8"))
    pts = [(r["name"], float(r["input_lat_dd"]), float(r["input_lon_dd"]))
           for r in a["frame_anchors"]
           if r.get("direction") == "NAD83(2011)->NATRF2022"]

    z = zipfile.ZipFile(ZIP)
    data = z.read("IFDM2022/IFDM2022_vel_svel.nc")
    lines = []
    rows = []
    with h5py.File(io.BytesIO(data), "r") as f:
        lat = f["lat"][...]
        lon = f["lon"][...]
        for name, la, lo in pts:
            loe = lo % 360.0
            i = int(np.searchsorted(lat, la) - 1)
            j = int(np.searchsorted(lon, loe) - 1)
            fy = (la - lat[i]) / (lat[i + 1] - lat[i])
            fx = (loe - lon[j]) / (lon[j + 1] - lon[j])
            rec = {"anchor": name, "lat": la, "lon_west_neg": lo,
                   "lon_east": loe,
                   "cell_lat": [float(lat[i]), float(lat[i + 1])],
                   "cell_lon_east": [float(lon[j]), float(lon[j + 1])]}
            for var in ("ve", "vn", "vu", "se", "sn", "su"):
                blk = f[var][i:i + 2, j:j + 2]
                v = (blk[0, 0] * (1 - fy) * (1 - fx) + blk[1, 0] * fy * (1 - fx)
                     + blk[0, 1] * (1 - fy) * fx + blk[1, 1] * fy * fx)
                rec[var + "_nodes_mm_yr"] = [[float(x) for x in r] for r in blk]
                rec[var + "_bilinear_mm_yr"] = float(v)
            rows.append(rec)
            lines.append(
                "%-16s lat=%8.4f lon=%9.4f  ve=%+8.4f vn=%+8.4f vu=%+8.4f mm/yr"
                "   (x10 yr: dE=%+7.1f dN=%+7.1f dU=%+7.1f mm)"
                % (name, la, lo, rec["ve_bilinear_mm_yr"],
                   rec["vn_bilinear_mm_yr"], rec["vu_bilinear_mm_yr"],
                   rec["ve_bilinear_mm_yr"] * 10, rec["vn_bilinear_mm_yr"] * 10,
                   rec["vu_bilinear_mm_yr"] * 10))

    os.makedirs(OUT, exist_ok=True)
    txt = os.path.join(OUT, "michigan_velocity_samples.txt")
    with open(txt, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("IFDM2022_vel_svel.nc sampled at the 12 frozen frame anchors\n")
        fh.write("grid: lat -90..90 step 0.1, lon 0..360 step 0.1, "
                 "units mm/yr, crs epsg:9990\n")
        fh.write("bilinear on the enclosing 2x2 nodes; NGS's own scheme for "
                 "these grids is NOT documented in anything captured here\n\n")
        fh.write("\n".join(lines) + "\n")
    js = os.path.join(OUT, "michigan_velocity_samples.json")
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rows, fh, indent=2, sort_keys=True)
    print("\n".join(lines))
    print("\nwrote", txt)
    print("wrote", js)


if __name__ == "__main__":
    main()
