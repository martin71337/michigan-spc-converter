"""One full UTM job record per frame, for the owner to read (work package U4).

Run from the repository root:  py review/utm-u4/preview_records.py [--fixture]

Writes review/utm-u4/record_NAD83_2011.txt and record_NATRF2022.txt: a
geodetic -> UTM 16N job on each frame, at the first frozen NCAT anchor of that
frame, with an elevation of 200.000 m, normalised as the suite normalises a
record (the job folder as <ROOT>, the Generated line blanked, the Software line
at the frozen version). With --fixture it also rewrites
tests/fixtures/utm_records.py, the literal text tests/test_utm_jobs.py pins -
regenerate it only on purpose, and read the diff.
"""
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from michspc.fileio import exports  # noqa: E402
from michspc.job import Direction, JobSettings, LongitudeConvention, run  # noqa: E402
from michspc.spc.frames import NAD83_2011, NATRF2022  # noqa: E402
from michspc.spc.units import METERS  # noqa: E402
from michspc.spc.zones import zone_by_code  # noqa: E402
from tests.conftest import member_text, record_root_normalised  # noqa: E402
from tests.fixtures.utm_anchors import NAD83_2011_ANCHORS, NATRF2022_ANCHORS  # noqa: E402

CASES = (
    ("NAD83_2011", NAD83_2011, zone_by_code("16N"), NAD83_2011_ANCHORS[0]),
    ("NATRF2022", NATRF2022, zone_by_code("16N-2022"), NATRF2022_ANCHORS[0]),
)


def record_for(frame, zone, anchor) -> str:
    folder = Path(tempfile.mkdtemp()) / "rec"
    folder.mkdir()
    settings = JobSettings(
        input_path=folder / "in.csv", output_directory=folder,
        direction=Direction.GEODETIC_TO_ZONE, source_zone=None, target_zone=zone,
        input_unit=METERS, output_unit=METERS, geodetic_frame=frame,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    settings.input_path.write_text(
        f"1,{anchor.latitude},{anchor.longitude},200.000,P\n", encoding="utf-8"
    )
    archive = exports.write_all(run(settings))["archive"]
    text = record_root_normalised(member_text(archive, "_README.txt"), archive.parent)
    return re.sub(r"^Generated          .*$", "Generated          <normalised>", text, flags=re.M)


def main() -> None:
    here = Path(__file__).resolve().parent
    records = {}
    for name, frame, zone, anchor in CASES:
        records[name] = record_for(frame, zone, anchor)
        (here / f"record_{name}.txt").write_text(records[name], encoding="utf-8")
        print(f"wrote {here / f'record_{name}.txt'}")
    if "--fixture" in sys.argv:
        body = [
            '"""The whole UTM job record, one per frame - literal text, pinned (U4, DESIGN.md #72).',
            "",
            "Written by review/utm-u4/preview_records.py --fixture after the lead read",
            "each record line by line; tests/test_utm_jobs.py compares a fresh job's",
            "record to these exactly. Regenerate only on purpose, and read the diff.",
            '"""',
            "",
        ]
        for name, _f, _z, _a in CASES:
            body.append(f"{name}_UTM_RECORD = {records[name]!r}")
            body.append("")
        (ROOT / "tests" / "fixtures" / "utm_records.py").write_text("\n".join(body), encoding="utf-8")
        print("wrote tests/fixtures/utm_records.py")


if __name__ == "__main__":
    main()
