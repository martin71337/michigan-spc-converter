"""Fetch every truth value from NCAT and the NGS geoid API.

Every raw JSON response is saved verbatim under raw/, one file per query,
named for the query. Nothing is fabricated: a query that fails after retries
is recorded as MISSING in raw/_failures.txt and the value stays absent.

Queries, all sequential at ~1/second:
  1. llh for each of the 12 points in its home zone.
  2. llh for the cross-zone pair points (C2@2111, S2@2112, NS@2111, NS@2113).
  3. geoid ght for each distinct location (12 + NS).
  4. spc (SPC -> geodetic direct truth) for each of the 12 points in each of
     the three units, using the coordinates NCAT itself printed in step 1.
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, r"C:\claude-projects\coord-convert\review\ncat-crosscheck")
from points_def import POINTS, NS_PROBE, EXTRA_ZONE_QUERIES

RAW = r"C:\claude-projects\coord-convert\review\ncat-crosscheck\raw"
BASE = "https://geodesy.noaa.gov/api"
FAILURES = []


def get(url, name):
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                body = r.read().decode("utf-8")
            with open(rf"{RAW}\{name}.json", "w", encoding="utf-8") as f:
                f.write(body)
            time.sleep(1.0)
            return json.loads(body)
        except Exception as e:
            last = e
            print(f"  {name}: attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(2.0 * (attempt + 1))
    FAILURES.append(f"{name}: {url} -> {last}")
    return None


def num(s):
    """NCAT prints numbers with thousands separators; strip them."""
    return float(str(s).replace(",", ""))


all_locs = {pid: (lat, lon) for pid, _z, lat, lon, _h, _r in POINTS}
all_locs["NS"] = (NS_PROBE[2], NS_PROBE[3])

# ---- 1 + 2: llh queries ---------------------------------------------------
llh_queries = [(pid, zone) for pid, zone, *_ in POINTS]
llh_queries += EXTRA_ZONE_QUERIES

llh_results = {}
for pid, zone in llh_queries:
    lat, lon = all_locs[pid]
    url = (f"{BASE}/ncat/llh?lat={lat}&lon={lon}"
           f"&inDatum=NAD83(2011)&outDatum=NAD83(2011)&spcZone={zone}")
    name = f"llh_{pid}_{zone}"
    print(f"llh {pid} zone {zone} ({lat}, {lon})", flush=True)
    r = get(url, name)
    if r is not None:
        llh_results[(pid, zone)] = r

# ---- 3: geoid queries -----------------------------------------------------
for pid, (lat, lon) in all_locs.items():
    url = f"{BASE}/geoid/ght?lat={lat}&lon={lon}"
    print(f"ght {pid} ({lat}, {lon})", flush=True)
    get(url, f"geoid_{pid}")

# ---- 4: spc direct truth, per unit, from NCAT's own printed coords --------
UNIT_FIELDS = {"m": ("spcNorthing_m", "spcEasting_m"),
               "ift": ("spcNorthing_ift", "spcEasting_ift"),
               "usft": ("spcNorthing_usft", "spcEasting_usft")}

for pid, zone, *_ in POINTS:
    r = llh_results.get((pid, zone))
    if r is None or "spcNorthing_m" not in r:
        FAILURES.append(f"spc_{pid}: no llh result to build the query from")
        continue
    for unit, (nf, ef) in UNIT_FIELDS.items():
        n = num(r[nf])
        e = num(r[ef])
        url = (f"{BASE}/ncat/spc?northing={n:.3f}&easting={e:.3f}&units={unit}"
               f"&spcZone={zone}&inDatum=NAD83(2011)&outDatum=NAD83(2011)")
        print(f"spc {pid} zone {zone} unit {unit}", flush=True)
        get(url, f"spc_{pid}_{zone}_{unit}")

with open(rf"{RAW}\_failures.txt", "w", encoding="utf-8") as f:
    if FAILURES:
        f.write("\n".join(FAILURES) + "\n")
    else:
        f.write("none\n")

print(f"done. failures: {len(FAILURES)}")
for line in FAILURES:
    print("  MISSING:", line)
