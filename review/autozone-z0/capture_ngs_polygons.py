"""Re-capture NGS's SPCS2022 zone polygons for Michigan (re-freeze harness).

    py -I review/autozone-z0/capture_ngs_polygons.py OUTPUT.json

Fetches the 18 Michigan features of NGS's "Beta SPCS2022 Multizone Complete
Zones Feature Layer View" (ArcGIS item 3e6a8ce23a814b62ae38993394669d8e) in the
service's NATIVE spatial reference, Web Mercator (wkid 102100 / EPSG 3857) -
the geometry the autozone-r0 recon measured and tests/autozone_geometry.py
reads (inverse-projected on the sphere, no datum shift). The exact query, with
no ``outSR`` and no ``geometryPrecision`` so the server returns its stored
coordinates at its default precision:

    where=StateAbrv='MI'  outFields=ZoneCode,AbrvFull  returnGeometry=true
    orderByFields=ZoneCode  f=json

It reproduced review/autozone-r0/raw/ngs_fs/mi_native.json byte for byte on
2026-10-23 (7,382,157 bytes, SHA-256 0b400984...c7f7). It writes the response
unmodified to OUTPUT and prints its SHA-256 beside the frozen capture's. A
matching digest means NGS's polygons have not moved; any other digest means
re-running tests/test_autozone_tables.py against the new capture and the full
re-freeze cycle of docs/REFREEZE-NSRS.md. Never writes over the frozen capture
itself. Stdlib only.

Do NOT re-capture with ``outSR=4269``: the server then transforms WGS 84 ->
NAD 83 and every line moves about 0.9 m off TIGER's (gate-autozone-1 finding
2). review/autozone-r0/raw/ngs_fs/mi_4269.json is that capture, kept as the
recon's record and the suite's negative control, and verified against nothing.
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
FROZEN = Path(__file__).resolve().parents[1] / "autozone-r0" / "raw" / "ngs_fs" / "mi_native.json"
FROZEN_SHA256 = "0b40098476f55a04d8bd9f5b4b162b2f573cddf00e7054c39693b7441e3c7cf7"
UA = "MCX-autozone-refreeze/0.1 (owner: martin71337; survey software verification)"


def main() -> None:
    out = Path(sys.argv[1])
    if out.resolve() == FROZEN.resolve():
        raise SystemExit("refusing to overwrite the frozen capture")
    query = urllib.parse.urlencode(
        {"where": "StateAbrv='MI'", "outFields": "ZoneCode,AbrvFull",
         "returnGeometry": "true", "orderByFields": "ZoneCode", "f": "json"}
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
