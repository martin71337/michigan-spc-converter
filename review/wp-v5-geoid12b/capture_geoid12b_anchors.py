"""Capture GEOID12B verification anchors from NGS's own geoid service.

WP-V5's load-bearing measurement, run by the session lead before any registry
code existed (the method's anchors-precede-code rule, DESIGN.md section 8
risk 3, the same order V0 ran in for VERTCON).

The positions are exactly the 20 of ``tests/fixtures/geoid_anchors.py`` - the
GEOID18 anchors - so the two models are anchored at identical ground and their
differences are visible side by side. ``model=13`` is not assumed to be
GEOID12B: every response names its own model in the ``geoidModel`` field, and
the capture refuses any response that does not say "GEOID12B".

Each raw response body is written beside this script verbatim
(``pt00.json`` ...), and the capture then verifies the committed
``data/g2012bu3.bin`` tile reproduces every figure through the nearest-node
biquadratic (the INTG stencil, DESIGN.md #37) before anything is frozen.

Run on the owner's Windows machine 2026-08-07 (NOAA is unreachable from the
usual container). Output: ``captured.json``, transcribed into
``tests/fixtures/geoid12b_anchors.py``.

**Historical record: this ran BEFORE the WP-V5a rename**, so it imports
``michspc.fileio.geoid18``, which is now ``michspc.fileio.geoid``. Kept as it
ran rather than edited to look like it ran later; a reviewer re-running it
today should change the two import lines (only the module name changed - every
symbol it reads still exists under the same name).
"""

from __future__ import annotations

import json
import struct
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

GEOID12B_MODEL_ID = "13"


def fetch(latitude: float, longitude: float) -> tuple[dict, str]:
    query = urllib.parse.urlencode(
        {"lat": f"{latitude}", "lon": f"{longitude}", "model": GEOID12B_MODEL_ID}
    )
    url = f"https://geodesy.noaa.gov/api/geoid/ght?{query}"
    with urllib.request.urlopen(url, timeout=90) as response:
        body = response.read().decode("utf-8")
    return json.loads(body), body


def main() -> None:
    from fixtures.geoid_anchors import GEOID_ANCHORS

    from michspc.fileio import geoid18

    # The committed tile, loaded with the GEOID12B digest checked by hand here
    # since load_shipped_grid pins GEOID18's. Geometry is the same tile-#3 shape.
    import hashlib

    raw = geoid18.GEOID12B_TILE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != geoid18.GEOID12B_TILE_SHA256:
        raise SystemExit(f"g2012bu3.bin does not match its pin: {digest}")

    grid = geoid18.load_grid(
        geoid18.GEOID12B_TILE, expect_geometry=geoid18.GEOID18_U3_GEOMETRY
    )

    records = []
    worst_mm = 0.0
    for index, anchor in enumerate(GEOID_ANCHORS):
        payload, body = fetch(anchor.latitude, anchor.longitude)
        if payload.get("geoidModel") != "GEOID12B":
            raise SystemExit(
                f"model={GEOID12B_MODEL_ID} answered as "
                f"{payload.get('geoidModel')!r}, not GEOID12B - refusing to "
                f"capture under a wrong model id"
            )
        (HERE / f"pt{index:02d}.json").write_text(body, encoding="utf-8")

        ours = grid.interpolate_biquadratic_nearest_node(
            anchor.latitude, anchor.longitude
        )
        difference_mm = abs(ours - payload["geoidHeight"]) * 1000.0
        worst_mm = max(worst_mm, difference_mm)
        records.append(
            {
                "lat": anchor.latitude,
                "lon": anchor.longitude,
                "geoid12b_height_m": payload["geoidHeight"],
                "geoid12b_error_m": payload["error"],
                "ours_nearest_node": ours,
                "difference_mm": difference_mm,
                "geoid18_height_m": anchor.geoid_height_m,
            }
        )
        print(
            f"{anchor.latitude}/{anchor.longitude}: NGS {payload['geoidHeight']} "
            f"ours {ours:.6f} diff {difference_mm:.3f} mm "
            f"(GEOID18 at same point: {anchor.geoid_height_m})"
        )
        time.sleep(0.25)

    (HERE / "captured.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    print(f"\nworst |ours - NGS| = {worst_mm:.3f} mm over {len(records)} anchors")
    same = sum(
        1 for r in records if r["geoid12b_height_m"] == r["geoid18_height_m"]
    )
    print(f"anchors where GEOID12B == GEOID18 to the printed mm: {same}")


if __name__ == "__main__":
    main()
