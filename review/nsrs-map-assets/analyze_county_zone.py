"""Recon analysis (review-only, NOT production code).

Tests whether NGS's own SPCS2022 multizone-complete polygons resolve Michigan
counties cleanly: does each county's Census interior point fall in exactly one
of the 18 LDP zones?  Pure stdlib ray-casting point-in-polygon.

This DERIVES a county->zone table from two authorities' geometry.  It is NOT a
substitute for a published county->zone assignment; see MANIFEST.md.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")


def rings(geom):
    """Yield (exterior, [holes]) for Polygon/MultiPolygon coordinates."""
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    else:
        polys = geom["coordinates"]
    for p in polys:
        yield p[0], p[1:]


def in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            xint = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < xint:
                inside = not inside
    return inside


def contains(geom, x, y):
    for ext, holes in rings(geom):
        if in_ring(x, y, ext) and not any(in_ring(x, y, h) for h in holes):
            return True
    return False


zones = json.load(open(os.path.join(RAW, "MI_SPCS2022_multizone_complete_18zones.geojson"), encoding="utf-8"))["features"]
counties = json.load(open(os.path.join(RAW, "MI_counties_tigerweb.geojson"), encoding="utf-8"))["features"]

rows = []
multi = 0
none = 0
for c in sorted(counties, key=lambda f: f["properties"]["BASENAME"]):
    p = c["properties"]
    lat, lon = float(p["INTPTLAT"]), float(p["INTPTLON"])
    hits = [z["properties"] for z in zones if contains(z["geometry"], lon, lat)]
    if len(hits) > 1:
        multi += 1
    if not hits:
        none += 1
    rows.append((p["BASENAME"], p["GEOID"], [(h["ZoneCode"], h["AbrvPart"], h["NamePart"]) for h in hits]))

print(f"counties: {len(rows)}   in >1 zone: {multi}   in 0 zones: {none}")
print()
for name, geoid, hits in rows:
    tag = ", ".join(f"{z} {a} ({n})" for z, a, n in hits) or "!! NONE"
    flag = "  <-- MULTI" if len(hits) > 1 else ("  <-- NONE" if not hits else "")
    print(f"{name:<16} {geoid}  {tag}{flag}")

# zone -> counties
print()
print("=== derived zone -> counties")
by = {}
for name, geoid, hits in rows:
    for z, a, n in hits:
        by.setdefault((z, a, n), []).append(name)
for (z, a, n), names in sorted(by.items()):
    print(f"{z} {a:<6} {n:<14} ({len(names):>2}) {', '.join(sorted(names))}")
