"""Write a spread of ORTHOMETRIC job archives and digest every member."""
import hashlib, sys, zipfile
from pathlib import Path
from michspc.fileio import exports, geoid
from michspc.job import (Direction, JobSettings, LongitudeConvention,
                         VerticalMode, run)
from michspc.spc.units import INTERNATIONAL_FEET, METERS, US_SURVEY_FEET
from michspc.spc.vertical import NAVD88, NGVD29
from michspc.spc.zones import MI_CENTRAL, MI_NORTH, MI_SOUTH

out_root = Path(sys.argv[1]); out_root.mkdir(parents=True, exist_ok=True)
ROWS = ("1,500000.000,8000000.000,900.000,PIN\n"
        "2,510000.000,8010000.000,0.00,ZEROED\n"
        "3,520000.000,8020000.000,,BLANK\n")

configs = []
for unit in (INTERNATIONAL_FEET, US_SURVEY_FEET, METERS):
    configs.append(("z2z", dict(direction=Direction.ZONE_TO_ZONE,
        source_zone=MI_NORTH, target_zone=MI_CENTRAL,
        input_unit=unit, output_unit=unit)))
    configs.append(("z2g", dict(direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH, target_zone=None,
        input_unit=unit, output_unit=unit)))
configs.append(("z2z_vert", dict(direction=Direction.ZONE_TO_ZONE,
    source_zone=MI_NORTH, target_zone=MI_CENTRAL,
    input_unit=INTERNATIONAL_FEET, output_unit=INTERNATIONAL_FEET,
    vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
    source_vertical_datum=NGVD29, target_vertical_datum=NAVD88)))
configs.append(("vert_only", dict(direction=Direction.VERTICAL_ONLY,
    source_zone=MI_NORTH, target_zone=None,
    input_unit=METERS, output_unit=METERS,
    vertical_mode=VerticalMode.VERTICAL,
    source_vertical_datum=NGVD29, target_vertical_datum=NAVD88)))
configs.append(("swap", dict(direction=Direction.VERTICAL_ONLY,
    source_zone=MI_NORTH, target_zone=None,
    input_unit=METERS, output_unit=METERS,
    vertical_mode=VerticalMode.VERTICAL,
    source_vertical_datum=NAVD88, target_vertical_datum=NAVD88,
    source_geoid_model=geoid.GEOID12B_MODEL,
    geoid_model=geoid.GEOID18_MODEL)))

digests = []
for name, cfg in configs:
    folder = out_root / name; folder.mkdir(exist_ok=True)
    src = folder / "in.csv"; src.write_text(ROWS, encoding="utf-8")
    base = dict(input_path=src, output_directory=folder,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST)
    base.update(cfg)
    # A vertical-only job reading State Plane states no convention: the file
    # carries no longitude column, so the program refuses one.
    if cfg.get("direction") is Direction.VERTICAL_ONLY:
        base["longitude_convention"] = None
    written = exports.write_all(run(JobSettings(**base)), overwrite=True)
    with zipfile.ZipFile(written["archive"]) as zf:
        for member in sorted(zf.namelist()):
            body = zf.read(member)
            digests.append(f"{name}/{member} "
                           f"{hashlib.sha256(body).hexdigest()}")
print("\n".join(digests))
