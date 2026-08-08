"""Capture the NGS NCAT vertical-transformation lattice for WP-V1.

Writes one raw JSON file per request into raw/, plus an index. Nothing is
computed here beyond naming the files: the fixtures are transcribed from the
raw captures, never from this script's arithmetic.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
RAW.mkdir(exist_ok=True)

BASE = "https://geodesy.noaa.gov/api/ncat/llh"
SOURCE_HEIGHT_M = 200.000

# 20 Michigan points. The first six are positions the plan itself records, so a
# faithful recreation must reproduce V0's numbers at them; the rest are spread
# across both peninsulas and all three zones, deliberately off the 0.05-degree
# grid nodes so they test interpolation rather than a table lookup.
LATTICE = [
    ("anchor-22",        43.0000, -84.5000, "DESIGN.md #22 anchor; plan 2.3"),
    ("inverse-detroit",  42.3300, -83.0500, "plan 2.4 inverse set"),
    ("inverse-straits",  45.8700, -84.7300, "plan 2.4 inverse set"),
    ("inverse-marquette",46.5400, -87.4000, "plan 2.4 inverse set"),
    ("inverse-traverse", 44.7600, -85.6200, "plan 2.4 inverse set"),
    ("max-sigma",        43.0500, -86.2000, "plan 2.8 largest Michigan sigma"),
    ("monroe",           41.7583, -83.6417, "South zone"),
    ("kalamazoo",        42.2637, -85.5878, "South zone; plan 2.5 names it"),
    ("lansing",          42.7326, -84.5556, "South zone; plan 2.5 names it"),
    ("grand-rapids",     42.9634, -85.6681, "South zone"),
    ("flint",            43.0125, -83.6875, "South zone"),
    ("new-buffalo",      41.6961, -86.8203, "South zone, SW corner of the state"),
    ("saginaw",          43.4194, -83.9508, "Central zone"),
    ("houghton-lake",    44.2542, -84.2247, "Central zone"),
    ("ludington",        43.9878, -86.2419, "Central zone, Lake Michigan shore"),
    ("gaylord",          45.0217, -84.6753, "Central zone"),
    ("alpena",           45.0561, -83.4322, "Central zone, Lake Huron shore"),
    ("iron-river",       46.0919, -88.6414, "North zone, western UP"),
    ("sault",            46.4936, -84.3453, "North zone, eastern UP"),
    ("houghton",         47.1211, -88.5694, "North zone, Keweenaw"),
]

# The five points plan 2.4 ran in both directions.
INVERSE_SET = [
    ("inverse-detroit",   42.3300, -83.0500),
    ("inverse-straits",   45.8700, -84.7300),
    ("inverse-marquette", 46.5400, -87.4000),
    ("inverse-traverse",  44.7600, -85.6200),
    ("anchor-22",         43.0000, -84.5000),
]


def fetch(name: str, lat: float, lon: float, in_vert: str, out_vert: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "lat": f"{lat:.10f}",
            "lon": f"{lon:.10f}",
            "orthoHt": f"{SOURCE_HEIGHT_M:.3f}",
            "inDatum": "NAD83(2011)",
            "outDatum": "NAD83(2011)",
            "inVertDatum": in_vert,
            "outVertDatum": out_vert,
        }
    )
    url = f"{BASE}?{query}"
    with urllib.request.urlopen(url, timeout=90) as response:
        body = response.read().decode("utf-8")
    payload = json.loads(body)
    stem = f"{name}_{in_vert}_to_{out_vert}"
    (RAW / f"{stem}.json").write_text(body, encoding="utf-8")
    (RAW / f"{stem}.url").write_text(url, encoding="utf-8")
    return payload


def main() -> None:
    index = []

    for name, lat, lon, note in LATTICE:
        payload = fetch(name, lat, lon, "NGVD29", "NAVD88")
        index.append(
            {
                "name": name,
                "kind": "forward",
                "latitude": lat,
                "longitude": lon,
                "note": note,
                "srcOrthoht": payload.get("srcOrthoht"),
                "destOrthoht": payload.get("destOrthoht"),
                "sigOrthoht": payload.get("sigOrthoht"),
                "vertconVersion": payload.get("vertconVersion"),
                "srcVertDatum": payload.get("srcVertDatum"),
                "destVertDatum": payload.get("destVertDatum"),
            }
        )
        print(f"{name:<20} {lat:>9.4f} {lon:>10.4f}  "
              f"{payload.get('srcOrthoht')} -> {payload.get('destOrthoht')}  "
              f"sig={payload.get('sigOrthoht')}")
        time.sleep(0.4)

    for name, lat, lon in INVERSE_SET:
        payload = fetch(name, lat, lon, "NAVD88", "NGVD29")
        index.append(
            {
                "name": name,
                "kind": "inverse",
                "latitude": lat,
                "longitude": lon,
                "note": "plan 2.4 inverse set",
                "srcOrthoht": payload.get("srcOrthoht"),
                "destOrthoht": payload.get("destOrthoht"),
                "sigOrthoht": payload.get("sigOrthoht"),
                "vertconVersion": payload.get("vertconVersion"),
                "srcVertDatum": payload.get("srcVertDatum"),
                "destVertDatum": payload.get("destVertDatum"),
            }
        )
        print(f"{name:<20} INVERSE  {payload.get('srcOrthoht')} -> "
              f"{payload.get('destOrthoht')}  sig={payload.get('sigOrthoht')}")
        time.sleep(0.4)

    (HERE / "index.json").write_text(
        json.dumps(index, indent=2), encoding="utf-8"
    )
    print(f"\ncaptured {len(index)} responses into {RAW}")


if __name__ == "__main__":
    main()
