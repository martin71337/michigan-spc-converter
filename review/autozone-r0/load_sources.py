"""autozone-r0: load every captured boundary source into one metric frame.

Recon only. Reads the raw captures under raw/ (untrusted downloads, read as
data) and returns shapely geometries in EPSG:3078 (NAD83 / Michigan Oblique
Mercator, metres) so offsets between sources can be measured in metres.

Run with the scratch venv:  <venv>/python -I load_sources.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import zipfile
import io

import shapefile  # pyshp
from pyproj import Transformer
from shapely.geometry import Polygon, MultiPolygon, shape
from shapely.ops import unary_union, transform

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")

# MCL 54.231(3)-(5), Act 9 of 1964 as amended by 1988 PA 154 (raw/statute/).
NORTH = """Gogebic Ontonagon Houghton Keweenaw Baraga Iron Marquette Dickinson
Menominee Alger Delta Schoolcraft Luce Chippewa Mackinac""".split()
CENTRAL = """Emmet Cheboygan Presque_Isle Charlevoix Leelanau Antrim Otsego
Montmorency Alpena Benzie Grand_Traverse Kalkaska Crawford Oscoda Alcona
Manistee Wexford Missaukee Roscommon Ogemaw Iosco Mason Lake Osceola Clare
Gladwin Arenac""".split()
SOUTH = """Oceana Newaygo Mecosta Isabella Midland Bay Huron Muskegon Montcalm
Gratiot Saginaw Tuscola Sanilac Ottawa Kent Ionia Clinton Shiawassee Genesee
Lapeer St._Clair Allegan Barry Eaton Ingham Livingston Oakland Macomb
Van_Buren Kalamazoo Calhoun Jackson Washtenaw Wayne Berrien Cass St._Joseph
Branch Hillsdale Lenawee Monroe""".split()
STATUTE = {}
for code, names in (("2111", NORTH), ("2112", CENTRAL), ("2113", SOUTH)):
    for n in names:
        STATUTE[n.replace("_", " ")] = code

LL_TO_M = Transformer.from_crs("EPSG:4269", "EPSG:3078", always_xy=True)
M_TO_LL = Transformer.from_crs("EPSG:3078", "EPSG:4269", always_xy=True)


def norm(name: str) -> str:
    n = name.strip().replace("Saint ", "St. ")
    return n


def esri_rings_to_geom(rings):
    """Esri JSON rings -> shapely (outer rings clockwise, holes ccw)."""
    shells, holes = [], []
    for r in rings:
        if len(r) < 4:
            continue
        a = 0.0
        for (x1, y1), (x2, y2) in zip(r, r[1:]):
            a += (x2 - x1) * (y2 + y1)
        (shells if a > 0 else holes).append(Polygon(r))
    polys = []
    for s in shells:
        hs = [h for h in holes if s.contains(h.representative_point())]
        p = s
        for h in hs:
            p = p.difference(h)
        polys.append(p)
    return unary_union(polys)


def web_mercator_to_ll(x, y, z=None):
    R = 6378137.0
    lon = math.degrees(x / R)
    lat = math.degrees(2.0 * math.atan(math.exp(y / R)) - math.pi / 2.0)
    return lon, lat


def ll_to_m(g):
    return transform(lambda x, y, z=None: LL_TO_M.transform(x, y), g)


def counties_mgf():
    """State of Michigan 'County Boundaries-Extended' (MGF), EPSG:3078."""
    p = os.path.join(RAW, "mi_counties_extended", "counties_native.json")
    d = json.load(open(p, encoding="utf-8"))
    out = {}
    for f in d["features"]:
        out[norm(f["attributes"]["Name"])] = esri_rings_to_geom(
            f["geometry"]["rings"])
    return out, d


def counties_tiger():
    """Census TIGER/Line 2025 counties, STATEFP 26, NAD83 -> EPSG:3078."""
    p = os.path.join(RAW, "tiger", "tl_2025_us_county.zip")
    z = zipfile.ZipFile(p)
    shp = io.BytesIO(z.read("tl_2025_us_county.shp"))
    dbf = io.BytesIO(z.read("tl_2025_us_county.dbf"))
    shx = io.BytesIO(z.read("tl_2025_us_county.shx"))
    r = shapefile.Reader(shp=shp, dbf=dbf, shx=shx, encoding="latin-1")
    fields = [f[0] for f in r.fields[1:]]
    out, attrs = {}, {}
    for sr in r.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        if rec["STATEFP"] != "26":
            continue
        g = shape(sr.shape.__geo_interface__)
        out[norm(rec["NAME"])] = ll_to_m(g)
        attrs[norm(rec["NAME"])] = rec
    return out, attrs


def ngs_ldp():
    """NGS beta SPCS2022 multizone-complete polygons, Michigan, 3857 -> 3078.

    The service stores Web Mercator (WGS 84 sphere-projected). Inverse
    spherical Mercator is exact; the result is treated numerically as NAD83
    lat/long (no datum shift applied) -- see RECON.md on what that costs."""
    p = os.path.join(RAW, "ngs_fs", "mi_native.json")
    d = json.load(open(p, encoding="utf-8"))
    out = {}
    for f in d["features"]:
        g = esri_rings_to_geom(f["geometry"]["rings"])
        g = transform(web_mercator_to_ll, g)
        out[f["attributes"]["ZoneCode"]] = (f["attributes"]["AbrvFull"],
                                            ll_to_m(g))
    return out


def ngs_statewide():
    p = os.path.join(RAW, "ngs_fs", "mi_statewide_native.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding="utf-8"))
    f = d["features"][0]
    g = esri_rings_to_geom(f["geometry"]["rings"])
    return ll_to_m(transform(web_mercator_to_ll, g))


def ngs_2019_south():
    base = os.path.join(RAW, "ngs_mapdata", "x", "Michigan_data_2019-05-26",
                        "DataCommon")
    r = shapefile.Reader(os.path.join(base, "MI_S_SPCS83"))
    g = unary_union([shape(s.__geo_interface__) for s in r.shapes()])
    r2 = shapefile.Reader(os.path.join(base, "Michigan"))
    g2 = unary_union([shape(s.__geo_interface__) for s in r2.shapes()])
    return ll_to_m(g), ll_to_m(g2)


def esri_spcs83():
    p = os.path.join(RAW, "esri_spcs83", "mi.json")
    d = json.load(open(p, encoding="utf-8"))
    return {f["attributes"]["FIPSZONE"]: ll_to_m(
        esri_rings_to_geom(f["geometry"]["rings"])) for f in d["features"]}


def zones_from_counties(counties):
    missing = sorted(set(STATUTE) - set(counties))
    extra = sorted(set(counties) - set(STATUTE))
    z = {}
    for code in ("2111", "2112", "2113"):
        z[code] = unary_union([counties[n] for n, c in STATUTE.items()
                               if c == code and n in counties])
    return z, missing, extra


if __name__ == "__main__":
    m, _ = counties_mgf()
    t, _ = counties_tiger()
    print("MGF counties", len(m), "TIGER counties", len(t))
    for nm, c in (("MGF", m), ("TIGER", t)):
        z, miss, extra = zones_from_counties(c)
        print(nm, "missing", miss, "extra", extra)
    ldp = ngs_ldp()
    print("LDP zones", len(ldp))
