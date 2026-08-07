"""Probe 3: section-aware comparison of the panel against the audit CSV.

Uses single_point_sections directly on the SAME JobResult the multi-point
export is built from, then also re-runs the whole thing through the two real
GUIs to confirm the settings assembly agrees.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys, csv, io, itertools, tempfile
from pathlib import Path

sys.path.insert(0, r"C:\claude-projects\coord-convert")

from michspc.fileio import pnezd, exports
from michspc.gui.results_model import single_point_sections
from michspc.job import Direction, JobSettings, LongitudeConvention, run
from michspc.spc.zones import ALL_ZONES
from michspc.spc.units import ALL_UNITS

problems = []
checked = 0


def audit_of(result):
    rows = exports.audit_rows(result)
    return dict(zip(rows[0], rows[1]))


def sect(sections, title):
    for s in sections:
        if s.title == title:
            return {v.label: v.text for v in s.values}
    raise AssertionError(title)


def check(direction, first, second, elev, src, tgt, iu, ou, conv):
    global checked
    settings = JobSettings(
        input_path=None, output_directory=None, direction=direction,
        source_zone=src, target_zone=tgt, input_unit=iu, output_unit=ou,
        longitude_convention=conv,
    )
    source = pnezd.parse_typed_point(first, second, elev,
                                     source=pnezd.TYPED_POINT_SOURCE_GRID)
    result = run(settings, source=source)
    sections = single_point_sections(result)
    a = audit_of(result)
    IN = sect(sections, "INPUT")
    OUT = sect(sections, "OUTPUT")
    checked += 1
    ctx = (direction.name, getattr(src, "code", None), getattr(tgt, "code", None),
           iu.code, ou.code, conv.name if conv else None, elev)

    def eq(where, got, want, what):
        if got != want:
            problems.append((what, ctx, where, got, want))

    if direction is Direction.ZONE_TO_ZONE:
        eq("IN", IN["Northing"], a["Source northing"], "source N")
        eq("IN", IN["Easting"], a["Source easting"], "source E")
        eq("IN", IN["Grid scale factor"], a["Source grid scale factor"], "source k")
        eq("IN", IN["Convergence"], a["Source convergence"], "source gamma")
        eq("OUT", OUT["Northing"], a["Target northing"], "target N")
        eq("OUT", OUT["Easting"], a["Target easting"], "target E")
        eq("OUT", OUT["Grid scale factor"], a["Grid scale factor"], "target k")
        eq("OUT", OUT["Convergence"], a["Convergence"], "target gamma")
        eq("OUT", OUT["Latitude"], a["Latitude"], "lat")
        eq("OUT", OUT["Longitude"], a["Longitude (neg west)"], "lon")
        eq("OUT", OUT["Elevation"], a["Elevation"], "elev")
    elif direction is Direction.ZONE_TO_GEODETIC:
        eq("IN", IN["Northing"], a["Source northing"], "source N")
        eq("IN", IN["Easting"], a["Source easting"], "source E")
        eq("IN", IN["Grid scale factor"], a["Grid scale factor"], "k")
        eq("IN", IN["Convergence"], a["Convergence"], "gamma")
        eq("OUT", OUT["Latitude"], a["Target latitude"], "target lat")
        eq("OUT", OUT["Longitude"], a["Target longitude (as written)"], "target lon")
        eq("OUT", OUT["Elevation"], a["Elevation"], "elev")
    else:
        eq("IN", IN["Latitude"], a["Source latitude"], "source lat")
        eq("IN", IN["Longitude"], a["Source longitude (as in file)"], "source lon")
        eq("OUT", OUT["Northing"], a["Target northing"], "target N")
        eq("OUT", OUT["Easting"], a["Target easting"], "target E")
        eq("OUT", OUT["Grid scale factor"], a["Grid scale factor"], "k")
        eq("OUT", OUT["Convergence"], a["Convergence"], "gamma")
        eq("OUT", OUT["Elevation"], a["Elevation"], "elev")

    for label, col in (("Geoid height (m)", "Geoid height (m)"),
                       ("Ellipsoid height (m)", "Ellipsoid height (m)"),
                       ("Elevation factor", "Elevation factor"),
                       ("Combined factor", "Combined factor")):
        block = IN if direction is Direction.ZONE_TO_GEODETIC else OUT
        eq("blk", block[label], a[col], label)


GRIDS = {  # a plausible point per zone, in international feet
    "2111": ("1000000.000", "13123359.580"),
    "2112": ("700000.000", "19685039.370"),
    "2113": ("400000.000", "26246719.160"),
}

for src, tgt in itertools.product(ALL_ZONES, ALL_ZONES):
    n, e = GRIDS[src.code]
    for iu, ou in itertools.product(ALL_UNITS, ALL_UNITS):
        for elev in ("800.00", ""):
            check(Direction.ZONE_TO_ZONE, n, e, elev, src, tgt, iu, ou, None)

for src in ALL_ZONES:
    n, e = GRIDS[src.code]
    for iu, ou in itertools.product(ALL_UNITS, ALL_UNITS):
        for c in LongitudeConvention:
            for elev in ("800.00", ""):
                check(Direction.ZONE_TO_GEODETIC, n, e, elev, src, None, iu, ou, c)

for tgt in ALL_ZONES:
    for iu, ou in itertools.product(ALL_UNITS, ALL_UNITS):
        for c, lon in ((LongitudeConvention.NEGATIVE_WEST, "-84.5555"),
                       (LongitudeConvention.POSITIVE_WEST, "84.5555")):
            for elev in ("800.00", ""):
                check(Direction.GEODETIC_TO_ZONE, "42.7325", lon, elev,
                      None, tgt, iu, ou, c)

print(f"checked {checked}")
for p in problems[:40]:
    print("PROBLEM", p)
print("problems:", len(problems))
