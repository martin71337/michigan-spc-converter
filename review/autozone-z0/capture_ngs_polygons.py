"""Re-capture NGS's SPCS2022 zone polygons for Michigan (re-freeze harness).

    py -I review/autozone-z0/capture_ngs_polygons.py OUTPUT.json

Fetches the 18 Michigan features of NGS's "Beta SPCS2022 Multizone Complete
Zones Feature Layer View" (ArcGIS item 3e6a8ce23a814b62ae38993394669d8e) in
NAD83 geographic (outSR 4269), the query the autozone-r0 recon used for
review/autozone-r0/raw/ngs_fs/mi_4269.json (RECON.md section 2.1), writes the
response unmodified to OUTPUT, and prints its SHA-256 beside the frozen
capture's. A matching digest means NGS's polygons have not moved; any other
digest means re-running tests/test_autozone_tables.py against the new capture
and the full re-freeze cycle of docs/REFREEZE-NSRS.md. Never writes over the
frozen capture itself. Stdlib only.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SERVICE = (
    "https://services2.arcgis.com/C8EMgrsFcRFL6LrL/arcgis/rest/services/"
    "Alpha_SPCS2022_Multizone_Complete_Zones_Feature_Layer_View/FeatureServer/0/query"
)
FROZEN = Path(__file__).resolve().parents[1] / "autozone-r0" / "raw" / "ngs_fs" / "mi_4269.json"
FROZEN_SHA256 = "658c4ead203c9ed2a727a29aee8d88ecc834a750cb1c135a83ef710c7d3f2099"
UA = "MCX-autozone-refreeze/0.1 (owner: martin71337; survey software verification)"


def main() -> None:
    out = Path(sys.argv[1])
    if out.resolve() == FROZEN.resolve():
        raise SystemExit("refusing to overwrite the frozen capture")
    query = urllib.parse.urlencode(
        {"where": "StateAbrv='MI'", "outFields": "ZoneCode,AbrvFull", "outSR": "4269",
         "returnGeometry": "true", "geometryPrecision": "10", "orderByFields": "ZoneCode",
         "f": "json"}
    )
    request = urllib.request.Request(SERVICE + "?" + query, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=300) as response:
        body = response.read()
    out.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    print(f"fetched {len(body)} bytes, SHA-256 {digest}")
    print(f"frozen  SHA-256 {FROZEN_SHA256} -> {'UNCHANGED' if digest == FROZEN_SHA256 else 'DIFFERENT'}")


if __name__ == "__main__":
    main()
