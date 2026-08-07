"""Probe NCAT endpoints to establish response shape and /spc parameter semantics.

Probe 1: llh at a frozen-anchor point (2113, 42.95, -84.36666666666667) whose
expected output is already known verbatim (tests/fixtures/ncat_anchors.py:
N 161062.456 m, E 4000000.0 m). Confirms field names and that the API still
returns what the anchors froze.

Probe 2: /spc with that anchor's METER coordinates, units=m -> expect the
anchor's lat/lon back.

Probe 3: /spc with the anchor's US SURVEY FOOT coordinates, units=usft.
Probe 4: /spc with the anchor's INTERNATIONAL FOOT coordinates, units=ift.
Establishes empirically what the 'units' parameter accepts and means.
"""
import json
import sys
import time
import urllib.request
import urllib.parse

RAW = r"C:\claude-projects\coord-convert\review\ncat-crosscheck\raw"


def get(url, name):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                body = r.read().decode("utf-8")
            with open(rf"{RAW}\{name}.json", "w", encoding="utf-8") as f:
                f.write(body)
            return json.loads(body)
        except Exception as e:
            print(f"  attempt {attempt+1} failed: {e}", flush=True)
            time.sleep(2 * (attempt + 1))
    return None


base = "https://geodesy.noaa.gov/api/ncat"

print("PROBE 1: llh at anchor 2113 / 42.95 / -84.36666666666667")
r1 = get(
    f"{base}/llh?lat=42.95&lon=-84.36666666666667&inDatum=NAD83(2011)&outDatum=NAD83(2011)&spcZone=2113",
    "probe1_llh_anchor_2113",
)
print(json.dumps(r1, indent=2))
time.sleep(1)

print("PROBE 2: spc units=m, N=161062.456 E=4000000.0 zone 2113")
r2 = get(
    f"{base}/spc?northing=161062.456&easting=4000000.0&units=m&spcZone=2113&inDatum=NAD83(2011)&outDatum=NAD83(2011)",
    "probe2_spc_m_anchor_2113",
)
print(json.dumps(r2, indent=2))
time.sleep(1)

print("PROBE 3: spc units=usft, N=528419.075 E=13123333.333 zone 2113")
r3 = get(
    f"{base}/spc?northing=528419.075&easting=13123333.333&units=usft&spcZone=2113&inDatum=NAD83(2011)&outDatum=NAD83(2011)",
    "probe3_spc_usft_anchor_2113",
)
print(json.dumps(r3, indent=2))
time.sleep(1)

print("PROBE 4: spc units=ift, N=528420.131 E=13123359.58 zone 2113")
r4 = get(
    f"{base}/spc?northing=528420.131&easting=13123359.58&units=ift&spcZone=2113&inDatum=NAD83(2011)&outDatum=NAD83(2011)",
    "probe4_spc_ift_anchor_2113",
)
print(json.dumps(r4, indent=2))
