"""autozone-r0: measure the boundary sources against each other.

Writes work/analysis.json and prints the tables RECON.md quotes.
Run:  <venv>/python -I analyze.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops it
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import shapely
from shapely.geometry import Point, LineString, MultiLineString
from shapely.ops import unary_union, linemerge

import load_sources as L

HERE = L.HERE
WORK = os.path.join(HERE, "work")
os.makedirs(WORK, exist_ok=True)
OUT = {}


def nverts(g):
    return int(shapely.get_num_coordinates(g))


def shared_line(a, b, tol=0.5):
    """Common boundary of two adjacent polygons of ONE source."""
    ln = a.boundary.intersection(b.buffer(tol)).intersection(
        b.boundary.buffer(tol))
    return ln


def sample_offsets(line_a, geom_b_boundary, step=50.0):
    """Distance from points every `step` m along line_a to geom_b_boundary."""
    ds = []
    pts = []
    lines = getattr(line_a, "geoms", [line_a])
    for ln in lines:
        if ln.geom_type not in ("LineString", "LinearRing"):
            continue
        n = max(1, int(ln.length // step))
        for i in range(n + 1):
            p = ln.interpolate(i * step if i < n else ln.length)
            ds.append(p.distance(geom_b_boundary))
            pts.append(p)
    return ds, pts


def stats(ds):
    if not ds:
        return None
    s = sorted(ds)
    return dict(n=len(s), median=round(statistics.median(s), 3),
                p95=round(s[int(0.95 * (len(s) - 1))], 3),
                max=round(s[-1], 3))


def ll(p):
    lon, lat = L.M_TO_LL.transform(p.x, p.y)
    return round(lat, 6), round(lon, 6)


def main():
    mgf, _ = L.counties_mgf()
    tig, tattr = L.counties_tiger()
    zm, _, _ = L.zones_from_counties(mgf)
    zt, _, _ = L.zones_from_counties(tig)
    state_m = unary_union(list(mgf.values()))
    state_t = unary_union(list(tig.values()))

    # ---- sources: size, coverage, self-consistency --------------------
    def overlaps_gaps(cs):
        names = list(cs)
        ov = 0.0
        tree = shapely.STRtree([cs[n] for n in names])
        for i, n in enumerate(names):
            for j in tree.query(cs[n]):
                if j > i:
                    ov += cs[n].intersection(cs[names[j]]).area
        u = unary_union(list(cs.values()))
        holes = sum(shapely.Polygon(r).area for g in getattr(u, "geoms", [u])
                    for r in g.interiors)
        return ov, holes
    src = {}
    for nm, cs, st in (("MGF", mgf, state_m), ("TIGER", tig, state_t)):
        ov, holes = overlaps_gaps(cs)
        src[nm] = dict(counties=len(cs), vertices=sum(nverts(g) for g in cs.values()),
                       state_area_km2=round(st.area / 1e6, 1),
                       county_overlap_m2=round(ov, 1),
                       interior_holes_m2=round(holes, 1))
    tl_land = sum(r["ALAND"] for r in tattr.values()) / 1e6
    tl_water = sum(r["AWATER"] for r in tattr.values()) / 1e6
    src["TIGER"]["ALAND_km2"] = round(tl_land, 1)
    src["TIGER"]["AWATER_km2"] = round(tl_water, 1)
    sd = state_m.symmetric_difference(state_t)
    src["MGF_vs_TIGER_state_symdiff_km2"] = round(sd.area / 1e6, 3)
    src["MGF_vs_TIGER_state_outer_hausdorff_m"] = round(
        state_m.boundary.hausdorff_distance(state_t.boundary), 1)
    OUT["sources"] = src
    print(json.dumps(src, indent=1))

    # ---- SPCS 83 zones: each source's zone areas and internal lines ----
    z83 = {}
    for nm, z in (("MGF", zm), ("TIGER", zt)):
        z83[nm] = {c: dict(area_km2=round(g.area / 1e6, 1),
                           parts=len(getattr(g, "geoms", [g])),
                           vertices=nverts(g)) for c, g in z.items()}
    lines = {}
    for pair in (("2111", "2112"), ("2112", "2113"), ("2111", "2113")):
        a, b = pair
        lm = shared_line(zm[a], zm[b])
        lt = shared_line(zt[a], zt[b])
        lines[pair] = (lm, lt)
        z83["line_%s_%s" % pair] = dict(
            MGF_length_km=round(lm.length / 1e3, 2),
            TIGER_length_km=round(lt.length / 1e3, 2))
    OUT["spcs83_zones"] = z83
    print(json.dumps(z83, indent=1))

    # offsets MGF line -> TIGER zone boundary, and land/water split.
    # land mask = TIGER counties minus nothing? TIGER has no land polygon,
    # so the NGS 2019 'Michigan.shp' (Esri detailed, land-clipped) is used.
    s19, mich19 = L.ngs_2019_south()
    land = mich19.buffer(0)
    OUT["ngs2019_michigan_shp_area_km2"] = round(land.area / 1e6, 1)
    off = {}
    worst = {}
    for pair, (lm, lt) in lines.items():
        if lm.is_empty or lt.is_empty:
            off["%s/%s" % pair] = "zones do not touch"
            continue
        ds, pts = sample_offsets(lm, lt.buffer(0) if False else lt, 50.0)
        island = [land.contains(p) for p in pts]
        dl = [d for d, k in zip(ds, island) if k]
        dw = [d for d, k in zip(ds, island) if not k]
        off["%s/%s" % pair] = dict(all=stats(ds), land=stats(dl),
                                   water=stats(dw))
        if ds:
            i = max(range(len(ds)), key=ds.__getitem__)
            worst["%s/%s" % pair] = dict(offset_m=round(ds[i], 2),
                                         latlon=ll(pts[i]),
                                         on_land=island[i])
    OUT["spcs83_line_offset_MGF_to_TIGER_m"] = off
    OUT["spcs83_line_offset_worst"] = worst
    print(json.dumps(off, indent=1)); print(json.dumps(worst, indent=1))

    # zone disagreement area: area where MGF zone != TIGER zone
    dis = {}
    for c in zm:
        dis[c] = round(zm[c].symmetric_difference(zt[c]).area / 1e6, 4)
    OUT["spcs83_zone_symdiff_MGF_TIGER_km2"] = dis

    # NGS 2019 South polygon and Esri generalized zones vs MGF
    OUT["ngs2019_south"] = dict(
        vertices=nverts(s19), area_km2=round(s19.area / 1e6, 1),
        hausdorff_to_MGF_south_m=round(s19.boundary.hausdorff_distance(
            zm["2113"].boundary), 1),
        CS_line_offset_to_MGF=stats(sample_offsets(
            lines[("2112", "2113")][0], s19.boundary, 100.0)[0]),
        land_only_area_note="south zone land area")
    esri = L.esri_spcs83()
    OUT["esri_spcs83"] = {c: dict(vertices=nverts(g),
                                  area_km2=round(g.area / 1e6, 1))
                          for c, g in esri.items()}
    OUT["esri_spcs83"]["CS_line_offset_to_MGF"] = stats(sample_offsets(
        lines[("2112", "2113")][0], esri["2113"].boundary, 200.0)[0])
    print(json.dumps(OUT["ngs2019_south"], indent=1))
    print(json.dumps(OUT["esri_spcs83"], indent=1))

    # ---- SPCS2022 LDP zones -------------------------------------------
    ldp = L.ngs_ldp()
    lz = {c: g for c, (_, g) in ldp.items()}
    comp = {}
    for c, g in sorted(lz.items()):
        parts = []
        for n, cg in mgf.items():
            a = g.intersection(cg).area
            if a > 0:
                parts.append((n, round(a / cg.area, 4)))
        full = sorted(n for n, f in parts if f > 0.999)
        partial = sorted((n, f) for n, f in parts if 0.0005 < f <= 0.999)
        comp[c] = dict(abrv=ldp[c][0], vertices=nverts(g),
                       area_km2=round(g.area / 1e6, 1), counties=full,
                       partial_counties=partial)
    OUT["ldp_composition_vs_MGF"] = comp
    for c, v in comp.items():
        print(c, v["abrv"], v["vertices"], v["area_km2"], v["counties"],
              v["partial_counties"])
    # assignment of every county to exactly one LDP?
    county_to = {}
    for c, v in comp.items():
        for n in v["counties"]:
            county_to.setdefault(n, []).append(c)
    OUT["counties_not_wholly_in_one_ldp"] = sorted(
        set(mgf) - {n for n, v in county_to.items() if len(v) == 1})
    # overlaps / gaps among LDP polygons
    ov = []
    codes = sorted(lz)
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            x = lz[a].intersection(lz[b])
            if x.area > 1.0:
                ov.append((a, b, round(x.area, 1)))
    lu = unary_union(list(lz.values()))
    OUT["ldp_pairwise_overlap_m2_over_1m2"] = ov
    OUT["ldp_union_area_km2"] = round(lu.area / 1e6, 1)
    OUT["ldp_union_interior_holes_m2"] = round(sum(
        shapely.Polygon(r).area for g in getattr(lu, "geoms", [lu])
        for r in g.interiors), 1)
    OUT["ldp_union_minus_MGFstate_km2"] = round(lu.difference(state_m).area / 1e6, 3)
    OUT["MGFstate_minus_ldp_union_km2"] = round(state_m.difference(lu).area / 1e6, 3)
    OUT["ldp_union_minus_TIGERstate_km2"] = round(lu.difference(state_t).area / 1e6, 3)
    OUT["TIGERstate_minus_ldp_union_km2"] = round(state_t.difference(lu).area / 1e6, 3)
    OUT["ldp_vs_MGF_outer_hausdorff_m"] = round(
        lu.boundary.hausdorff_distance(state_m.boundary), 1)
    OUT["ldp_vs_TIGER_outer_hausdorff_m"] = round(
        lu.boundary.hausdorff_distance(state_t.boundary), 1)
    print("overlaps", ov)
    for k in ("ldp_union_area_km2", "ldp_union_interior_holes_m2",
              "ldp_union_minus_MGFstate_km2", "MGFstate_minus_ldp_union_km2",
              "ldp_union_minus_TIGERstate_km2", "TIGERstate_minus_ldp_union_km2",
              "ldp_vs_MGF_outer_hausdorff_m", "ldp_vs_TIGER_outer_hausdorff_m"):
        print(k, OUT[k])

    # LDP internal boundary offsets vs TIGER and MGF county edges
    tig_edges = unary_union([g.boundary for g in tig.values()])
    mgf_edges = unary_union([g.boundary for g in mgf.values()])
    internal = unary_union([lz[c].boundary for c in codes]).difference(
        lu.boundary.buffer(1.0))
    dT, ptsT = sample_offsets(linemerge(internal) if internal.geom_type ==
                              "MultiLineString" else internal, tig_edges, 100.0)
    dM, _ = sample_offsets(linemerge(internal) if internal.geom_type ==
                           "MultiLineString" else internal, mgf_edges, 100.0)
    OUT["ldp_internal_line_offset_to_TIGER_county_edges"] = stats(dT)
    OUT["ldp_internal_line_offset_to_MGF_county_edges"] = stats(dM)
    if dT:
        i = max(range(len(dT)), key=dT.__getitem__)
        OUT["ldp_internal_worst_vs_TIGER"] = dict(offset_m=round(dT[i], 2),
                                                  latlon=ll(ptsT[i]))
    print("LDP internal vs TIGER", OUT["ldp_internal_line_offset_to_TIGER_county_edges"])
    print("LDP internal vs MGF", OUT["ldp_internal_line_offset_to_MGF_county_edges"])
    print(OUT.get("ldp_internal_worst_vs_TIGER"))

    sw = L.ngs_statewide()
    if sw is not None:
        OUT["statewide_260001"] = dict(
            vertices=nverts(sw), area_km2=round(sw.area / 1e6, 1),
            minus_ldp_union_km2=round(sw.difference(lu).area / 1e6, 4),
            ldp_union_minus_it_km2=round(lu.difference(sw).area / 1e6, 4),
            hausdorff_to_ldp_union_m=round(sw.boundary.hausdorff_distance(
                lu.boundary), 2))
        print(OUT["statewide_260001"])

    # ---- simplification cost ------------------------------------------
    simp = {}
    for tol in (0.5, 1, 2, 5, 10, 25):
        row = {}
        for nm, zs in (("spcs83_MGF", zm), ("ldp_NGS", lz)):
            ss = {c: shapely.simplify(g, tol, preserve_topology=True)
                  for c, g in zs.items()}
            nv = sum(nverts(g) for g in ss.values())
            cs = sorted(ss)
            gap_ov = 0.0
            for i, a in enumerate(cs):
                for b in cs[i + 1:]:
                    gap_ov += ss[a].intersection(ss[b]).area
            u = unary_union(list(ss.values()))
            holes = sum(shapely.Polygon(r).area
                        for g in getattr(u, "geoms", [u]) for r in g.interiors)
            row[nm] = dict(vertices=nv, est_bytes_json=nv * 2 * 13,
                           overlap_m2=round(gap_ov, 1),
                           new_gaps_m2=round(holes, 1))
        simp[str(tol)] = row
    simp["unsimplified"] = dict(
        spcs83_MGF=sum(nverts(g) for g in zm.values()),
        ldp_NGS=sum(nverts(g) for g in lz.values()))
    OUT["simplification"] = simp
    print(json.dumps(simp, indent=1))

    with open(os.path.join(WORK, "analysis.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(OUT, fh, indent=1, default=str)


if __name__ == "__main__":
    main()
