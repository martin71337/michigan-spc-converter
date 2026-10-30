"""U0 recon for docs/PLAN-utm-epsg.md: UTM via tm.py against frozen NCAT, PROJ, and EPSG.

Run from the repository root: py review/utm-u0/measure.py   (needs pyproj)

1. Every frozen production NCAT response in review/autozone-r0/raw/ncat_probe/
   that carries a UTM result is reproduced with michspc.spc.tm given UTM's
   defining constants; the worst residual per quantity is printed.
2. PROJ (EPSG 6344-6346) as a third opinion over Michigan's latitudes, at
   3.0, 4.6 and 5.0 degrees from each central meridian (the engine's domain
   limit), and the refusal just beyond it and at 8.5 degrees.
3. The EPSG dataset version, and each NAD83(2011) Michigan SPCS 83 CRS run
   against MCX's own zone record.
"""
import glob, json, os, sqlite3, sys

sys.path.insert(0, os.getcwd())
import pyproj
from pyproj import Transformer
from michspc.spc import projection, tm
from michspc.spc.ellipsoid import GRS80
from michspc.spc.zones import SPCS83_ZONES, TransverseMercatorDef


def utm(zone):
    d = TransverseMercatorDef(lat_grid_origin=0.0, lon_origin=6.0 * zone - 183.0,
                              k_origin=0.9996, northing_grid_origin=0.0,
                              easting_origin=500000.0)
    return tm.TransverseMercatorConstants.from_definition(d, GRS80)


def dms(text):
    parts = text.split()
    sign = -1 if parts[0].startswith("-") else 1
    return sign * (abs(float(parts[0])) + float(parts[1]) / 60 + float(parts[2]) / 3600)


worst = [0.0] * 4
count, zones = 0, {}
for path in sorted(glob.glob("review/autozone-r0/raw/ncat_probe/*.json")):
    r = json.load(open(path))
    if r.get("srcDatum") != "NAD83(2011)" or "utmNorthing" not in r:
        continue
    z = int(r["utmZone"].split()[-1])
    zones[z] = zones.get(z, 0) + 1
    g = tm.forward(float(r["destLat"]), float(r["destLon"]), utm(z))
    res = (abs(g.northing - float(r["utmNorthing"].replace(",", ""))),
           abs(g.easting - float(r["utmEasting"].replace(",", ""))),
           abs(g.scale_factor - float(r["utmScaleFactor"])),
           abs(g.convergence - dms(r["utmConvergence"])) * 3600)
    worst = [max(a, b) for a, b in zip(worst, res)]
    count += 1
print(f"NCAT: {count} responses {zones}; worst dN {worst[0]:.4f} m, dE {worst[1]:.4f} m, "
      f"dk {worst[2]:.1e}, dconv {worst[3]:.3f} arcsec")

for z, code in ((15, 6344), (16, 6345), (17, 6346)):
    t = Transformer.from_crs("EPSG:6318", f"EPSG:{code}", always_xy=True)
    cm = 6.0 * z - 183.0
    for band in (3.0, 4.6, tm.DOMAIN_LIMIT_DEGREES):
        w = 0.0
        for i in range(41):
            lat = 41.6 + i * 6.8 / 40
            for j in range(41):
                lon = cm - band + j * 2 * band / 40
                if not -90.5 <= lon <= -82.3:
                    continue
                e, n = t.transform(lon, lat)
                g = tm.forward(lat, lon, utm(z))
                w = max(w, abs(g.northing - n), abs(g.easting - e))
        print(f"PROJ EPSG {code}: within {band} deg of the meridian, worst {w * 1000:.3f} mm")
    # Beyond the engine's domain (tm.DOMAIN_LIMIT_DEGREES, DESIGN.md #72, the
    # UTM interim gate's MEDIUM 1) the engine refuses; the 8.5-degree row this
    # harness printed before the limit (2.9 mm) is now a refusal.
    for beyond in (tm.DOMAIN_LIMIT_DEGREES + 0.001, 8.5):
        try:
            tm.forward(45.0, cm + beyond, utm(z))
        except tm.TransverseMercatorDomainError:
            print(f"PROJ EPSG {code}: at {beyond} deg the engine refuses (domain limit)")
        else:
            print(f"PROJ EPSG {code}: at {beyond} deg the engine DID NOT refuse")

db = sqlite3.connect(os.path.join(pyproj.datadir.get_data_dir(), "proj.db"))
print("EPSG", db.execute("select value from metadata where key='EPSG.VERSION'").fetchone()[0],
      db.execute("select value from metadata where key='EPSG.DATE'").fetchone()[0])
pairs = {"2111": (6495, 6496), "2112": (6493, 6494), "2113": (6498, 6499)}
for zone in SPCS83_ZONES:
    for code, scale in zip(pairs[zone.code], (1.0, 0.3048)):
        t = Transformer.from_crs("EPSG:6318", f"EPSG:{code}", always_xy=True)
        lat0 = (zone.lat_min + zone.lat_max) / 2
        w = 0.0
        for dlat in (-1, 0, 1):
            for dlon in (-1.5, 0, 1.5):
                lat, lon = lat0 + dlat, zone.definition.lon_origin + dlon
                e, n = t.transform(lon, lat)
                g = projection.forward(lat, lon, zone)
                w = max(w, abs(e * scale - g.easting), abs(n * scale - g.northing))
        print(f"{zone.name} {zone.code} EPSG {code}: worst {w * 1000:.3f} mm")
