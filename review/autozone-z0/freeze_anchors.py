"""Z0: freeze the NCAT zone anchors into tests/fixtures/autozone_anchors.py.

    py -I review/autozone-z0/freeze_anchors.py

Reads every NCAT answer captured so far - this package's live queries
(work/anchor_ncat.json, raw/z0_*) and the autozone-r0 recon's (its round-1
fixed points, its 14 Great Lakes water points and its Keweenaw transect) -
classifies each point (land / water / outside Michigan, Keweenaw side), measures
its distance to the nearest zone line with the suite's own geometry
(tests/autozone_geometry.py), and writes the ones OUTSIDE the boundary bands
(50 m on land, 1 km in water and outside) as anchors. The rest are written as
EXCLUDED, each with its distance and the reason, so nothing captured is
silently dropped. NCAT's two systems disagreeing about the county near the
Osceola/Mecosta line (RECON.md section 5.3) are listed by name.

The fixture records, for each anchor, the raw capture file and its SHA-256; the
suite re-hashes the file and re-reads NCAT's zone out of it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

from michspc.spc import autozone_spcs83, autozone_spcs2022  # noqa: E402
from tests import autozone_geometry as geo  # noqa: E402

R0 = REPO / "review" / "autozone-r0"
OUT = REPO / "tests" / "fixtures" / "autozone_anchors.py"


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def code_of(ncat_zone):
    """'MI S-2113' -> '2113'; 'MI L45G-261008 (Multizone complete)' -> '261008';
    another state's zone or N/A -> None (Auto must refuse)."""
    if not ncat_zone or not ncat_zone.startswith("MI "):
        return None
    return ncat_zone.split("-")[-1].split(" ")[0]


def gather():
    rows = []
    z0 = json.loads((HERE / "work" / "anchor_ncat.json").read_text(encoding="utf-8"))
    for system, key in (("SPCS 83", "spcs83"), ("SPCS2022", "spcs2022")):
        for r in z0[key]:
            rows.append((system, r["tag"], r["lat"], r["lon"], r["ncat_zone"], HERE / "raw" / r["raw"], r["sha256"]))
    for system, name in (("SPCS 83", "ncat_83.json"), ("SPCS2022", "ncat_22.json")):
        for r in json.loads((R0 / "work" / name).read_text(encoding="utf-8")):
            if r["tag"].split()[0] in ("83CS0", "83NC0") or r["tag"].startswith("22L"):
                continue  # straddle probes of the MGF lines: in the band by design
            rows.append((system, r["tag"], r["lat"], r["lon"], r["ncat_zone"], R0 / "raw" / "ncat_probe" / r["raw"], r["sha256"]))
    for r in json.loads((R0 / "work" / "r2_ncat_22.json").read_text(encoding="utf-8")):
        if r["tag"].split()[0] in ("WATER", "KEWEENAW_TRANSECT"):
            rows.append(("SPCS2022", r["tag"], r["lat"], r["lon"], r["ncat_zone"], R0 / "raw" / "ncat_probe" / r["raw"], r["sha256"]))
    return rows


def classify(system, lat, lon, expected):
    """(category, distance_m, band_m) for one point."""
    edges = geo.edges_with_owners()
    outline = [(a, b) for a, b, owners in edges if len(owners) == 1]
    if expected is None:
        return "outside", geo.nearest_distance_m(lat, lon, outline, 20000.0), geo.WATER_BAND_M
    land = bool(geo.ngs_land_zones(lon, lat))
    if system == "SPCS 83":
        zone_of = {f: z.code for f, z in autozone_spcs83.SPCS83_ZONE_BY_FIPS.items()}
    else:
        zone_of = {f: z.code for f, z in autozone_spcs2022.LDP_ZONE_BY_FIPS.items()}
    keweenaw_zones = {"261016", "261018"}
    other = []
    for a, b, owners in edges:
        if len(owners) == 1:
            other.append((a, b))  # the outline: beyond it, Auto refuses
            continue
        zones = set()
        for f in owners:
            if system == "SPCS2022" and f == autozone_spcs2022.KEWEENAW_FIPS:
                zones |= keweenaw_zones
            else:
                zones.add(zone_of[f])
        if zones != {expected}:
            other.append((a, b))
    d = geo.nearest_distance_m(lat, lon, other, 20000.0)
    category = "land" if land else "water"
    if system == "SPCS2022" and expected in keweenaw_zones:
        my, _ = geo.metres_per_degree(lat)
        d = min(d, abs(lat - autozone_spcs2022.ISLE_ROYALE_SPLIT_LATITUDE) * my)
    return category, d, geo.LAND_BAND_M if land else geo.WATER_BAND_M


def main():
    anchors, excluded = [], []
    for system, tag, lat, lon, ncat_zone, raw, sha in gather():
        body = raw.read_bytes()
        if hashlib.sha256(body).hexdigest() != sha:
            raise SystemExit(f"{raw}: digest does not match the probe record")
        expected = code_of(ncat_zone)
        category, d, band = classify(system, lat, lon, expected)
        row = (tag, system, lat, lon, category, ncat_zone, expected, rel(raw), sha, round(d, 1))
        if d >= band:
            anchors.append(row)
        else:
            excluded.append(row + (f"{d:.1f} m from a zone line or Michigan's outline, inside the {band:.0f} m {category} band",))

    r4 = json.loads((R0 / "work" / "r4_ncat.json").read_text(encoding="utf-8"))
    disagree = []
    for key, label in (("spcs2022", "SPCS2022"), ("spcs83_beta", "SPCS 83 (beta NCAT)")):
        for r in r4[key]:
            disagree.append((label, r["tag"], r["lat"], r["lon"], r["ncat_zone"], rel(R0 / "raw" / "ncat_probe" / r["raw"])))

    lines = [
        '"""NCAT zone anchors for Auto zone - frozen NGS truth, NOT derived here.',
        "",
        "NGS beta: the SPCS2022 rows are beta NCAT's own answers (the web app at",
        "https://beta.ngs.noaa.gov/NCAT/, NATRF2022 epoch 2020.00 in and out, zone",
        "list on 'Auto Pick (default zone)'); re-freeze obligation in",
        "docs/REFREEZE-NSRS.md. The SPCS 83 rows are production NCAT",
        "(https://geodesy.noaa.gov/api/ncat/llh, NAD83(2011) in and out, no spcZone,",
        "so NCAT picks the zone itself; RECON.md section 5.1).",
        "",
        "Captured 2026-10-22: the autozone-r0 recon (review/autozone-r0/raw/ncat_probe/)",
        "and work package Z0 (review/autozone-z0/raw/, harness",
        "review/autozone-z0/capture_anchors.py). Written by",
        "review/autozone-z0/freeze_anchors.py; every row names its raw capture and",
        "that file's SHA-256, and tests/test_autozone_anchors.py re-hashes the file and",
        "re-reads NCAT's zone out of it rather than trusting the ``ncat_zone`` text.",
        "",
        "Each anchor is OUTSIDE the boundary bands where NCAT disagrees with itself",
        "and with the county sources (RECON.md section 5.3): >= 50 m from any zone",
        "line (or Michigan's outline) on land, >= 1 km in water and outside",
        "Michigan. ``distance_m`` is the generator's measurement, capped at 20,000",
        "(read: at least 20 km); the suite re-measures it. ``expected`` is the zone code NCAT gave, or None where NCAT",
        "gave another state's zone or N/A - Auto must refuse those.",
        "",
        "Categories: land / water (in Michigan, land by NGS's own land-only",
        "polygons), outside (not in any Michigan county).",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import NamedTuple",
        "",
        "",
        "class Anchor(NamedTuple):",
        "    tag: str",
        "    system: str  # 'SPCS 83' or 'SPCS2022'",
        "    latitude: float",
        "    longitude: float  # negative west",
        "    category: str  # 'land', 'water' or 'outside'",
        "    ncat_zone: str | None  # NCAT's own zone text",
        "    expected: str | None  # zone code, or None: Auto refuses",
        "    capture: str  # repository path of the raw NCAT response",
        "    sha256: str",
        "    distance_m: float",
        "",
        "",
        "ANCHORS: tuple[Anchor, ...] = (",
    ]
    for row in anchors:
        lines.append(f"    Anchor{row!r},")
    lines += [")", "", "", "EXCLUDED: tuple[tuple, ...] = ("]
    lines.append("    # (tag, system, lat, lon, category, ncat_zone, expected, capture, sha256, distance_m, reason)")
    for row in excluded:
        lines.append(f"    {row!r},")
    lines += [
        ")",
        '"""Captured NCAT answers NOT used as anchors: inside a boundary band."""',
        "",
        "",
        "NCAT_SELF_DISAGREEMENT: tuple[tuple, ...] = (",
        "    # (system, tag, lat, lon, ncat_zone, capture)",
    ]
    for row in disagree:
        lines.append(f"    {row!r},")
    lines += [
        ")",
        '"""RECON round 4 (RECON.md section 5.3): the same positions asked of both',
        "systems where TIGER and MGF disagree. At Osceola/Mecosta, 43.8154 N",
        "85.5337 W, 3-10 m inside Osceola County, NCAT says SPCS 83 South",
        "(Mecosta's zone) and SPCS2022 L55W (Osceola's); at Mason/Oceana, 43.8174 N",
        "86.2564 W, 3 m inside Mason, SPCS 83 South (Oceana's) and L55W (Mason's).",
        "NCAT's two systems disagree about which county those points are in. None",
        "is an anchor; all are inside the 50 m land band.\"\"\"",
        "",
    ]
    OUT.write_bytes(("\n".join(lines)).encode("ascii"))
    from collections import Counter

    print("anchors", len(anchors), Counter((r[1], r[4]) for r in anchors))
    print("excluded", len(excluded))
    for r in excluded:
        print("  ", r[0], r[1], r[-1])
    print("disagree", len(disagree))


if __name__ == "__main__":
    main()
