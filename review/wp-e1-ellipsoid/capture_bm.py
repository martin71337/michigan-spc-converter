"""Capture NGS published benchmarks carrying BOTH an NAVD 88 orthometric
height and a GEOID18 geoid height, spread across Michigan's three zones."""
import json, urllib.request, time

SEEDS = [
    ("Monroe / Lake Erie",      41.92, -83.40),
    ("Detroit",                 42.33, -83.05),
    ("Lansing",                 42.73, -84.56),
    ("Grand Rapids",            42.96, -85.67),
    ("Port Huron",              42.97, -82.43),
    ("Muskegon",                43.23, -86.24),
    ("Saginaw",                 43.42, -83.95),
    ("Ludington",               43.95, -86.45),
    ("Traverse City",           44.76, -85.62),
    ("Alpena",                  45.06, -83.43),
    ("Mackinaw City",           45.78, -84.73),
    ("Sault Ste. Marie",        46.50, -84.35),
    ("Marquette",               46.55, -87.40),
    ("Houghton",                47.12, -88.57),
]
URL = ("https://geodesy.noaa.gov/api/nde/radial"
       "?lat={lat}&lon={lon}&radius=6&type=BM")

out = []
for name, lat, lon in SEEDS:
    try:
        with urllib.request.urlopen(URL.format(lat=lat, lon=lon), timeout=45) as fh:
            data = json.load(fh)
    except Exception as exc:
        print(f"{name}: FAILED {exc}")
        continue
    good = [
        r for r in data
        if r.get("orthoHt") and r.get("geoidHt")
        and (r.get("vertDatum") or "").strip() == "NAVD 88"
        and (r.get("geoidModel") or "").strip() == "GEOID18"
    ]
    # the mark with the most decimal places on its orthometric height
    good.sort(key=lambda r: (-len(r["orthoHt"].split(".")[-1]), r["pid"]))
    if good:
        r = good[0]
        r["_seed"] = name
        out.append(r)
        print(f"{name}: {r['pid']} H={r['orthoHt']} N={r['geoidHt']} "
              f"lat={r['lat']} lon={r['lon']}")
    else:
        print(f"{name}: none usable of {len(data)}")
    time.sleep(0.4)

with open("bm_capture.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2)
print(f"\ncaptured {len(out)}")
