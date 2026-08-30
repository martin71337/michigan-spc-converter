"""Recon verification (review-only, NOT production code).

Strengthens the county->zone derivation beyond a single interior point:
samples a grid of points inside each county polygon and requires that EVERY
sampled point land in the SAME single SPCS2022 zone.  A county whose points
split across zones is reported -- that is the falsification this checks for.

Ring-level bounding boxes are precomputed so most of the ~200k zone vertices
are skipped per point.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")


def rings(g):
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    for p in polys:
        yield p[0], p[1:]


def bbox(ring):
    xs = [q[0] for q in ring]
    ys = [q[1] for q in ring]
    return min(xs), max(xs), min(ys), max(ys)


def prep(geom):
    """[(ext_bbox, ext_ring, [(hole_bbox, hole_ring)])] plus overall bbox."""
    out = []
    for e, hs in rings(geom):
        out.append((bbox(e), e, [(bbox(h), h) for h in hs]))
    xs = [b[0] for b, _, _ in out] + [b[1] for b, _, _ in out]
    ys = [b[2] for b, _, _ in out] + [b[3] for b, _, _ in out]
    return out, (min(xs), max(xs), min(ys), max(ys))


def hit_bbox(b, x, y):
    return b[0] <= x <= b[1] and b[2] <= y <= b[3]


def in_ring(x, y, r):
    ins = False
    n = len(r)
    j = n - 1
    for i in range(n):
        x1, y1 = r[i][0], r[i][1]
        x2, y2 = r[j][0], r[j][1]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) / (y2 - y1) * (x2 - x1):
                ins = not ins
        j = i
    return ins


def contains(prepped, x, y):
    parts, ob = prepped
    if not hit_bbox(ob, x, y):
        return False
    for b, e, hs in parts:
        if not hit_bbox(b, x, y):
            continue
        if in_ring(x, y, e) and not any(hit_bbox(hb, x, y) and in_ring(x, y, h)
                                        for hb, h in hs):
            return True
    return False


zones = json.load(open(os.path.join(RAW, "MI_SPCS2022_multizone_complete_18zones.geojson"), encoding="utf-8"))["features"]
counties = json.load(open(os.path.join(RAW, "MI_counties_tigerweb.geojson"), encoding="utf-8"))["features"]

Z = [(z["properties"]["ZoneCode"], z["properties"]["AbrvPart"],
      z["properties"]["NamePart"], prep(z["geometry"])) for z in zones]

N = int(sys.argv[1]) if len(sys.argv) > 1 else 14
rows = []
problems = []
total_pts = 0
for c in sorted(counties, key=lambda f: f["properties"]["BASENAME"]):
    p = c["properties"]
    cg = prep(c["geometry"])
    x0, x1, y0, y1 = cg[1]
    pts = []
    for i in range(N):
        for j in range(N):
            x = x0 + (x1 - x0) * (i + 0.5) / N
            y = y0 + (y1 - y0) * (j + 0.5) / N
            if contains(cg, x, y):
                pts.append((x, y))
    pts.append((float(p["INTPTLON"]), float(p["INTPTLAT"])))
    total_pts += len(pts)
    seen = {}
    for x, y in pts:
        hit = tuple(sorted(zc for zc, _, _, zp in Z if contains(zp, x, y)))
        seen[hit] = seen.get(hit, 0) + 1
    rows.append((p["BASENAME"], p["GEOID"], len(pts), seen))
    # Census county polygons extend into the Great Lakes; NGS zone polygons do
    # not.  Points hitting no zone are open water, not evidence of ambiguity.
    # The real question is whether the LAND points agree on one zone.
    land = {k: v for k, v in seen.items() if k}
    zc = {c2 for k in land for c2 in k}
    if len(zc) != 1 or any(len(k) != 1 for k in land):
        problems.append(rows[-1])

zn = {zc: (ab, nm) for zc, ab, nm, _ in Z}
print(f"counties tested: {len(rows)}   sample points: {total_pts}   grid: {N}x{N}")
print(f"counties whose IN-ZONE (land) points do NOT agree on one zone: {len(problems)}")
for name, geoid, npts, seen in problems:
    print(f"  {name} ({geoid}), {npts} pts:")
    for k, v in sorted(seen.items(), key=lambda kv: -kv[1]):
        lbl = ", ".join(f"{c2} {zn[c2][0]}" for c2 in k) or "NO ZONE"
        print(f"      {v:>5} pts -> {lbl}")

with open(os.path.join(HERE, "derived_county_zone.csv"), "w", encoding="utf-8") as f:
    f.write("county,state_county_fips,zone_code,zone_abbrev,zone_name,land_sample_points,unanimous\n")
    for name, geoid, npts, seen in rows:
        land = {k: v for k, v in seen.items() if k}
        zset = {c2 for k in land for c2 in k}
        uni = len(zset) == 1 and all(len(k) == 1 for k in land)
        zc = next(iter(zset)) if uni else ""
        ab, nm = zn.get(zc, ("", ""))
        nland = sum(v for k, v in seen.items() if k)
        f.write(f"{name},{geoid},{zc},{ab},{nm},{nland},{'yes' if uni else 'NO'}\n")
print("wrote derived_county_zone.csv")
