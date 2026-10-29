"""U0 recon, NATRF2022 half: beta NCAT's own UTM output against michspc.spc.tm.

Run from the repository root: py review/utm-u0/measure_natrf2022.py

Every frozen beta NCAT result page in review/autozone-r0/raw/ncat_probe/
(*spcs2022*.html, captured 2026-10-22, NGS beta) whose converted-coordinate
row is NATRF2022 epoch 2020.00 carries a UTM zone, northing, easting,
convergence and scale factor. The row is parsed from the page's own export
table, and each value is reproduced with tm.py given UTM's constants.
"""
import glob, html, os, re, sys

sys.path.insert(0, os.getcwd())
from michspc.spc import tm
from michspc.spc.ellipsoid import GRS80
from michspc.spc.zones import TransverseMercatorDef


def utm(zone):
    d = TransverseMercatorDef(lat_grid_origin=0.0, lon_origin=6.0 * zone - 183.0,
                              k_origin=0.9996, northing_grid_origin=0.0,
                              easting_origin=500000.0)
    return tm.TransverseMercatorConstants.from_definition(d, GRS80)


def dms(text):
    parts = text.split()
    sign = -1 if parts[0].startswith("-") else 1
    return sign * (abs(float(parts[0])) + float(parts[1]) / 60 + float(parts[2]) / 3600)


ROW = re.compile(
    r"\| 1 \| \| NATRF2022 epoch 2020\.00 \| \| NATRF2022 epoch 2020\.00 \|"
    r"(?:[^|]*\|){4}.*? \| \| (-?\d+\.\d+) \| \| N\d+\.\d+ \| \| (-?\d+\.\d+) \| \| W\d+\.\d+ \|"
    r" \| N/A \| \| N/A \|.*?\| UTM Zone (\d+) \| \| ([\d.]+) \| \| ([\d.]+) \|"
    r" \| ([+-]\d\d \d\d [\d.]+) \| \| ([\d.]+) \|"
)
"""The export table's first row: the OUTPUT latitude and longitude (the second
pair, after the input pair and its three N/A heights), then the UTM block."""

worst = [0.0] * 4
count, zones = 0, {}
for path in sorted(glob.glob("review/autozone-r0/raw/ncat_probe/*spcs2022*.html")):
    text = open(path, encoding="utf-8", errors="replace").read()
    flat = html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]+>", " | ", text)))
    m = ROW.search(flat)
    if not m:
        continue
    lat, lon, z = float(m.group(1)), float(m.group(2)), int(m.group(3))
    g = tm.forward(lat, lon, utm(z))
    res = (abs(g.northing - float(m.group(4))), abs(g.easting - float(m.group(5))),
           abs(g.scale_factor - float(m.group(7))), abs(g.convergence - dms(m.group(6))) * 3600)
    worst = [max(a, b) for a, b in zip(worst, res)]
    zones[z] = zones.get(z, 0) + 1
    count += 1
print(f"beta NCAT NATRF2022: {count} pages {zones}; worst dN {worst[0]:.4f} m, dE {worst[1]:.4f} m, "
      f"dk {worst[2]:.1e}, dconv {worst[3]:.3f} arcsec")
