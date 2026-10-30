"""UTM through the job path, the written ZIP and the job record (U3-U4, DESIGN.md #72).

Work packages U3 and U4 of docs/PLAN-utm-epsg.md, built as one (the plan's
deviation note): every UTM conversion the owner asked for, end to end through
``job.run`` and ``exports.write_all``, against NGS's own numbers; the refusals
the frame registry and the unit gate owe a UTM job; the warnings; and the job
record's UTM wording - the Conversion line, the era check by frame, and the
METHOD arm a UTM job gets.

**Where every expected value comes from.** Nothing below is computed by this
program and then expected of it:

* UTM northing and easting: NCAT's printed values, in
  ``tests/fixtures/utm_anchors.py`` (production NCAT on NAD83(2011), beta NCAT
  on NATRF2022; the fixture is re-hashed and re-parsed from the frozen raw
  captures by ``tests/test_utm.py``).
* State Plane northing and easting: the SAME frozen NCAT responses, which
  print both grids for one position - so an SPCS 83 -> UTM job that turns
  NCAT's State Plane coordinate into NCAT's UTM coordinate is NGS against NGS,
  with this program in between. The raw files are read here directly; their
  digests are the fixture's, checked in tests/test_utm.py.
* Latitude and longitude: NCAT's printed decimal degrees in the same fixture.
* The WGS 84 case: HTDP's frozen NAD 83 pivot (tests/fixtures/htdp_w3_anchors.py,
  the L5 G2296 record), projected into 16N by the zone's own engine - the
  engine is held to NCAT independently above, so this pins the HTDP plumbing
  into a UTM zone, not the projection.

**Tolerances, derived** (NCAT prints metres to 0.001, so each printed value is
within 0.0005 m of its exact value):

* geodetic -> UTM: 0.0005 m (NCAT's rounding of the expected value) + 0.00001 m
  (NCAT's printed latitude/longitude, 1e-10 degree, is the input) + 0.00005 m
  (the clean export's four decimals) = 0.00056 m; ``GRID_TOL_M`` = 0.0006.
* zone -> zone: the input is ALSO rounded by NCAT, 0.0005 m per component;
  rotated through at most a few degrees of convergence difference and scaled
  by at most 1.0004, a component can carry 0.0005 x (cos + sin of that angle)
  x 1.0004 < 0.00053 m of it. Plus the output's 0.0005 and the file's 0.00005:
  0.00108 m; ``ZONE_TO_ZONE_TOL_M`` = 0.0011.
* UTM -> geodetic: 0.0005 m of input rounding is at most 0.0005 / 73,900 m per
  degree of longitude at 48.4 N = 6.8e-9 degree; NCAT's printed degree is
  within 5e-11, and the export's eight decimals add 5e-9: 1.19e-8;
  ``DEGREE_TOL`` = 1.25e-8.
"""

from __future__ import annotations

import csv
import datetime
import html
import io
import json
import re
from pathlib import Path

import pytest

from michspc.fileio import exports, report
from michspc.job import (
    AUTO_ZONE,
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc import projection
from michspc.spc.tm import TransverseMercatorDomainError
from michspc.spc.autozone import AutoZoneSystem, zones_choosable
from michspc.spc.convert import WarningCode
from michspc.spc.frames import (
    NAD83_2011,
    NATRF2022,
    WGS84_G2296,
    FrameMismatchError,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS, US_SURVEY_FEET
from michspc.spc.vertical import NAVD88, NGVD29, HeightKind
from michspc.spc.zones import (
    MI_CENTRAL,
    MI_SOUTH,
    SPCS83_ZONES,
    UTM_ZONES,
    grid_name,
    grid_names_phrase,
    zone_by_code,
)
from tests.conftest import member_text, record_root_normalised
from tests.fixtures.htdp_w3_anchors import L5_RECORDS
from tests.fixtures.utm_anchors import NAD83_2011_ANCHORS, NATRF2022_ANCHORS
from tests.fixtures.utm_records import (
    MIXED_SPCS2022_UTM_METHOD,
    MIXED_SPCS83_UTM_METHOD,
    NAD83_2011_UTM_RECORD,
    NATRF2022_UTM_RECORD,
)

GRID_TOL_M = 0.0006
ZONE_TO_ZONE_TOL_M = 0.0011
DEGREE_TOL = 1.25e-8

UTM16 = zone_by_code("16N")
UTM17 = zone_by_code("17N")
UTM15 = zone_by_code("15N")
UTM16_2022 = zone_by_code("16N-2022")
SPCS2022_261008 = zone_by_code("261008")


# --------------------------------------------------------------------------
# Helpers.
# --------------------------------------------------------------------------


def _job(tmp_path: Path, rows: str, name: str = "job", **fields) -> tuple:
    """Run and write one job; ``(result, archive)``."""
    folder = tmp_path / name
    folder.mkdir()
    base = dict(
        input_path=folder / "in.csv",
        output_directory=folder,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=None,
    )
    base.update(fields)
    settings = JobSettings(**base)
    settings.input_path.write_text(rows, encoding="utf-8")
    result = run(settings)
    return result, exports.write_all(result)["archive"]


def _clean_rows(archive: Path, suffix: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(member_text(archive, suffix), newline="")))


def _clean_member_suffix(zone) -> str:
    return f"_{zone.abbrev}.csv"


def _record(archive: Path) -> str:
    return member_text(archive, "_README.txt")


def _grid_rows(anchors) -> str:
    """One PNEZD row per anchor, NCAT's UTM northing and easting as printed."""
    return "".join(
        f"{i},{a.northing},{a.easting},,A{i}\n" for i, a in enumerate(anchors, 1)
    )


def _geodetic_rows(anchors) -> str:
    """One row per anchor, NCAT's latitude and signed longitude as printed."""
    return "".join(
        f"{i},{a.latitude},{a.longitude},,A{i}\n" for i, a in enumerate(anchors, 1)
    )


def _ncat_state_plane(anchor) -> tuple[str, str, str]:
    """(zone code, northing m, easting m) NCAT printed for this anchor's position.

    Production JSON: ``spcZone`` "MI C-2112", ``spcNorthing_m``
    "61,379.810". Beta page: the export row's "MI L45G-261008 | | N | | E".
    """
    if anchor.capture.endswith(".json"):
        raw = json.loads(Path(anchor.capture).read_text(encoding="utf-8"))
        code = raw["spcZone"].split("-")[-1]
        return (
            code,
            raw["spcNorthing_m"].replace(",", ""),
            raw["spcEasting_m"].replace(",", ""),
        )
    text = Path(anchor.capture).read_text(encoding="utf-8", errors="replace")
    flat = html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]+>", " | ", text)))
    found = re.search(
        r"\| 2020\.00 \| \| 2020\.00 \| \| MI [A-Z0-9]+-(\d{6}) \| \| ([\d.]+) "
        r"\| \| ([\d.]+) \|",
        flat,
    )
    assert found, anchor.capture
    return found.group(1), found.group(2), found.group(3)


def _by_state_plane_zone(anchors) -> dict[str, list]:
    """The anchors grouped by NCAT's State Plane zone, Michigan zones only."""
    groups: dict[str, list] = {}
    known = {zone.code for zone in SPCS83_ZONES} | {
        z.code for z in zones_choosable(AutoZoneSystem.SPCS2022)
    } | {"260001"}
    for anchor in anchors:
        code, _n, _e = _ncat_state_plane(anchor)
        if code in known:
            groups.setdefault(code, []).append(anchor)
    return groups


NAD83_GROUPS = _by_state_plane_zone(NAD83_2011_ANCHORS)
NATRF2022_GROUPS = _by_state_plane_zone(NATRF2022_ANCHORS)


def test_the_zone_to_zone_anchor_groups_are_what_they_were_built_on():
    """So the zone-to-zone pins cannot pass by iterating nothing.

    NAD83(2011): the three SPCS 83 zones, 204 anchors between them (the 212
    less the 8 NCAT placed in another state's zone or in none). NATRF2022: the
    five SPCS2022 zones the beta pages fall in, all 34.
    """
    assert sorted(NAD83_GROUPS) == ["2111", "2112", "2113"]
    assert sum(len(v) for v in NAD83_GROUPS.values()) == 204
    assert sorted(NATRF2022_GROUPS) == ["261001", "261008", "261010", "261016", "261018"]
    assert sum(len(v) for v in NATRF2022_GROUPS.values()) == 34


# --------------------------------------------------------------------------
# 1. Geodetic <-> UTM, on both frames, through the written ZIP.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "frame, anchors, suffix",
    [(NAD83_2011, NAD83_2011_ANCHORS, ""), (NATRF2022, NATRF2022_ANCHORS, "-2022")],
    ids=["NAD83(2011)", "NATRF2022"],
)
def test_geodetic_to_utm_reproduces_ncat_through_the_written_zip(
    tmp_path, frame, anchors, suffix
):
    for number in sorted({a.zone for a in anchors}):
        zone = zone_by_code(f"{number}N{suffix}")
        mine = [a for a in anchors if a.zone == number]
        _result, archive = _job(
            tmp_path,
            _geodetic_rows(mine),
            name=f"g2u{number}",
            direction=Direction.GEODETIC_TO_ZONE,
            source_zone=None,
            target_zone=zone,
            geodetic_frame=frame,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        )
        rows = _clean_rows(archive, _clean_member_suffix(zone))
        assert len(rows) == len(mine)
        for anchor, row in zip(mine, rows):
            assert float(row[1]) == pytest.approx(float(anchor.northing), abs=GRID_TOL_M)
            assert float(row[2]) == pytest.approx(float(anchor.easting), abs=GRID_TOL_M)


@pytest.mark.parametrize(
    "frame, anchors, suffix",
    [(NAD83_2011, NAD83_2011_ANCHORS, ""), (NATRF2022, NATRF2022_ANCHORS, "-2022")],
    ids=["NAD83(2011)", "NATRF2022"],
)
def test_utm_to_geodetic_reproduces_ncat_through_the_written_zip(
    tmp_path, frame, anchors, suffix
):
    for number in sorted({a.zone for a in anchors}):
        zone = zone_by_code(f"{number}N{suffix}")
        mine = [a for a in anchors if a.zone == number]
        result, archive = _job(
            tmp_path,
            _grid_rows(mine),
            name=f"u2g{number}",
            direction=Direction.ZONE_TO_GEODETIC,
            source_zone=zone,
            target_zone=None,
            geodetic_frame=frame,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        )
        assert result.settings.geodetic_frame is frame
        rows = _clean_rows(archive, "_GEODETIC_DD.csv")
        assert len(rows) == len(mine)
        for anchor, row in zip(mine, rows):
            assert float(row[1]) == pytest.approx(float(anchor.latitude), abs=DEGREE_TOL)
            assert float(row[2]) == pytest.approx(float(anchor.longitude), abs=DEGREE_TOL)
        # The positions written are in the zone's own frame, and the record
        # says which.
        assert f"Reference frame           {frame.code}" in _record(archive)


def test_wgs84_g2296_reaches_utm_16n_through_htdp(tmp_path):
    """WGS84(G2296), 43.0 N 84.5 W, 2025-06-15 -> NAD83(2011) UTM 16N.

    Expected: HTDP's frozen NAD 83 pivot for exactly this input (the L5 G2296
    record: 42.9999914726 N, 84.4999892398 W), projected into 16N. HTDP prints
    1e-10 degree, about 0.01 mm, so 0.0001 m holds both the pivot's print and
    the export's four decimals.
    """
    (record,) = [r for r in L5_RECORDS if r.frame_code == "WGS84(G2296)"]
    pivot = projection.forward(float(record.lat_out), -float(record.lonw_out), UTM16)
    _result, archive = _job(
        tmp_path,
        "1,43.0,84.5,165.000,P\n",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=UTM16,
        geodetic_frame=WGS84_G2296,
        observation_date=record.observation_date,
        longitude_convention=LongitudeConvention.POSITIVE_WEST,
    )
    (row,) = _clean_rows(archive, _clean_member_suffix(UTM16))
    assert float(row[1]) == pytest.approx(pivot.northing, abs=0.0001)
    assert float(row[2]) == pytest.approx(pivot.easting, abs=0.0001)
    assert "FRAME TRANSFORMATION" in _record(archive)


# --------------------------------------------------------------------------
# 2. Zone <-> zone: NCAT's State Plane coordinate in, NCAT's UTM out.
# --------------------------------------------------------------------------


def _zone_to_zone_case(groups, code, utm_suffix):
    anchors = groups[code]
    numbers = sorted({a.zone for a in anchors})
    return [(code, n, [a for a in anchors if a.zone == n], utm_suffix) for n in numbers]


CASES = [
    case
    for groups, suffix in ((NAD83_GROUPS, ""), (NATRF2022_GROUPS, "-2022"))
    for code in sorted(groups)
    for case in _zone_to_zone_case(groups, code, suffix)
]


@pytest.mark.parametrize(
    "spc_code, number, anchors, suffix", CASES, ids=[f"{c[0]}-{c[1]}N{c[3]}" for c in CASES]
)
def test_state_plane_to_utm_turns_ncats_spc_into_ncats_utm(
    tmp_path, spc_code, number, anchors, suffix
):
    source = zone_by_code(spc_code)
    target = zone_by_code(f"{number}N{suffix}")
    rows = "".join(
        f"{i},{_ncat_state_plane(a)[1]},{_ncat_state_plane(a)[2]},,A{i}\n"
        for i, a in enumerate(anchors, 1)
    )
    _result, archive = _job(
        tmp_path, rows, direction=Direction.ZONE_TO_ZONE,
        source_zone=source, target_zone=target,
    )
    written = _clean_rows(archive, _clean_member_suffix(target))
    for anchor, row in zip(anchors, written, strict=True):
        assert float(row[1]) == pytest.approx(float(anchor.northing), abs=ZONE_TO_ZONE_TOL_M)
        assert float(row[2]) == pytest.approx(float(anchor.easting), abs=ZONE_TO_ZONE_TOL_M)


@pytest.mark.parametrize(
    "spc_code, number, anchors, suffix", CASES, ids=[f"{c[0]}-{c[1]}N{c[3]}" for c in CASES]
)
def test_utm_to_state_plane_turns_ncats_utm_into_ncats_spc(
    tmp_path, spc_code, number, anchors, suffix
):
    source = zone_by_code(f"{number}N{suffix}")
    target = zone_by_code(spc_code)
    _result, archive = _job(
        tmp_path, _grid_rows(anchors), direction=Direction.ZONE_TO_ZONE,
        source_zone=source, target_zone=target,
    )
    written = _clean_rows(archive, _clean_member_suffix(target))
    for anchor, row in zip(anchors, written, strict=True):
        _code, northing, easting = _ncat_state_plane(anchor)
        assert float(row[1]) == pytest.approx(float(northing), abs=ZONE_TO_ZONE_TOL_M)
        assert float(row[2]) == pytest.approx(float(easting), abs=ZONE_TO_ZONE_TOL_M)


def test_utm_16n_to_17n_lands_on_ncats_17n(tmp_path):
    """The 31 zone 17 anchors, carried in from 16N.

    The 16N input is computed by the engine (an INPUT, written with repr so
    the file holds the doubles); the expected 17N values are NCAT's. The
    engine's own round trip is 1e-9 m, inside ``GRID_TOL_M``'s derivation.
    """
    mine = [a for a in NAD83_2011_ANCHORS if a.zone == 17]
    assert len(mine) == 31
    rows = ""
    for i, anchor in enumerate(mine, 1):
        p = projection.forward(float(anchor.latitude), float(anchor.longitude), UTM16)
        rows += f"{i},{p.northing!r},{p.easting!r},,A{i}\n"
    _result, archive = _job(
        tmp_path, rows, direction=Direction.ZONE_TO_ZONE,
        source_zone=UTM16, target_zone=UTM17,
    )
    for anchor, row in zip(mine, _clean_rows(archive, "_UTM17N.csv"), strict=True):
        assert float(row[1]) == pytest.approx(float(anchor.northing), abs=GRID_TOL_M)
        assert float(row[2]) == pytest.approx(float(anchor.easting), abs=GRID_TOL_M)


def test_every_natrf2022_utm_record_has_the_constants_of_its_nad83_twin():
    """What the NATRF2022 METHOD paragraph claims: the equations do not depend on the frame."""
    nad83 = [z for z in UTM_ZONES if z.frame is NAD83_2011]
    natrf = [z for z in UTM_ZONES if z.frame is NATRF2022]
    assert len(nad83) == len(natrf) == 3
    for a, b in zip(nad83, natrf, strict=True):
        assert a.definition == b.definition


# --------------------------------------------------------------------------
# 3. Refusals.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, target",
    [
        (UTM16, UTM16_2022),
        (UTM16_2022, UTM16),
        (UTM16, SPCS2022_261008),
        (SPCS2022_261008, UTM16),
        (MI_SOUTH, UTM16_2022),
    ],
    ids=["utm83-utm22", "utm22-utm83", "utm83-spcs2022", "spcs2022-utm83", "spcs83-utm22"],
)
def test_a_zone_to_zone_job_across_the_two_frames_refuses(tmp_path, source, target):
    with pytest.raises(FrameMismatchError):
        _job(tmp_path, "1,4861207.771,727674.227,,P\n", direction=Direction.ZONE_TO_ZONE,
             source_zone=source, target_zone=target)


def test_wgs84_into_a_natrf2022_utm_zone_refuses(tmp_path):
    with pytest.raises(FrameMismatchError):
        _job(
            tmp_path, "1,43.0,84.5,165.000,P\n", direction=Direction.GEODETIC_TO_ZONE,
            source_zone=None, target_zone=UTM16_2022, geodetic_frame=WGS84_G2296,
            observation_date=datetime.date(2025, 6, 15),
            longitude_convention=LongitudeConvention.POSITIVE_WEST,
        )


@pytest.mark.parametrize("unit", [INTERNATIONAL_FEET, US_SURVEY_FEET], ids=["ift", "usft"])
@pytest.mark.parametrize("side", ["source", "target"])
def test_a_utm_job_in_feet_refuses_with_utms_own_reason(tmp_path, unit, side):
    fields = (
        dict(source_zone=UTM16, target_zone=MI_CENTRAL, input_unit=unit, output_unit=INTERNATIONAL_FEET)
        if side == "source"
        else dict(source_zone=MI_CENTRAL, target_zone=UTM16, input_unit=INTERNATIONAL_FEET, output_unit=unit)
    )
    with pytest.raises(ValueError) as refused:
        _job(tmp_path, "1,100.0,200.0,,P\n", direction=Direction.ZONE_TO_ZONE, **fields)
    message = str(refused.value)
    assert message.startswith(
        f"NAD83(2011) / UTM zone 16N is defined in metres only, so this job's "
        f"{side} unit, {unit.name} ({unit.code}), cannot be used for it."
    )
    assert "its false easting is 500,000 m" in message
    assert "UTM zones may be read and written in: m (meters)." in message
    # Never the SPCS2022 sentence: that is a statement about NGS's SPCS2022
    # publication, false of UTM.
    assert "SPCS2022" not in message
    assert "does not publish" not in message


def test_the_natrf2022_ellipsoid_height_gate_covers_a_utm_2022_job(tmp_path):
    """The 0.7.0 closing gate's HIGH, on the new zones: refused by the same gate.

    The message is the gate's own, frame-named, exactly as for zone 261008.
    """
    attempts = iter(range(10))

    def attempt(zone):
        with pytest.raises(FrameMismatchError) as refused:
            _job(
                tmp_path, "1,43.0,-84.5,198.885,P\n", name=f"h{next(attempts)}",
                direction=Direction.GEODETIC_TO_ZONE, source_zone=None,
                target_zone=zone, geodetic_frame=NATRF2022,
                input_height_kind=HeightKind.ELLIPSOID,
                longitude_convention=LongitudeConvention.NEGATIVE_WEST,
            )
        return str(refused.value)

    assert attempt(UTM16_2022) == attempt(SPCS2022_261008)
    assert "ELLIPSOID input heights and works in NATRF2022" in attempt(UTM16_2022)


# --------------------------------------------------------------------------
# 4. Vertical, and Auto.
# --------------------------------------------------------------------------


def test_vertical_only_with_a_utm_source_moves_only_the_elevation(tmp_path):
    """NGVD 29 -> NAVD 88 on a UTM input: the same shift as the State Plane job at the same point.

    Expected: the elevation the SAME physical point gets on a MI-S
    vertical-only job (VERTCON is read at the position, whichever grid named
    it), and the northing and easting written back exactly as read.
    """
    position = projection.forward(43.0, -84.5, UTM16)
    spc = projection.forward(43.0, -84.5, MI_SOUTH)
    common = dict(
        direction=Direction.VERTICAL_ONLY, target_zone=None,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NGVD29, target_vertical_datum=NAVD88,
    )
    _r1, utm_archive = _job(
        tmp_path, f"1,{position.northing!r},{position.easting!r},200.000,P\n",
        name="vu", source_zone=UTM16, **common,
    )
    _r2, spc_archive = _job(
        tmp_path, f"1,{spc.northing!r},{spc.easting!r},200.000,P\n",
        name="vs", source_zone=MI_SOUTH, **common,
    )
    # A vertical-only archive is named for its mode, not a zone.
    (utm_row,) = _clean_rows(utm_archive, "_VERTICAL.csv")
    (spc_row,) = _clean_rows(spc_archive, "_VERTICAL.csv")
    assert utm_row[3] == spc_row[3]
    assert float(utm_row[3]) == pytest.approx(199.860, abs=0.0005)  # NCAT's, #22's anchor
    assert float(utm_row[1]) == pytest.approx(position.northing, abs=0.00005)
    assert float(utm_row[2]) == pytest.approx(position.easting, abs=0.00005)
    record = _record(utm_archive)
    assert "exactly as a UTM to geodetic job reports" in record
    assert "State Plane to geodetic job reports" not in record


def test_horizontal_and_vertical_from_utm_into_state_plane(tmp_path):
    """A UTM source, a State Plane target, NGVD 29 -> NAVD 88: both conversions run.

    Expected: NCAT's MI-S coordinate for 43.0 N 84.5 W is not frozen, so the
    horizontal half is held to the State Plane projection of the same position
    within the zone-to-zone tolerance, and the vertical half to NCAT's 199.860
    m (#22's live anchor at this position).
    """
    position = projection.forward(43.0, -84.5, UTM16)
    spc = projection.forward(43.0, -84.5, MI_SOUTH)
    _result, archive = _job(
        tmp_path, f"1,{position.northing!r},{position.easting!r},200.000,P\n",
        direction=Direction.ZONE_TO_ZONE, source_zone=UTM16, target_zone=MI_SOUTH,
        vertical_mode=VerticalMode.HORIZONTAL_AND_VERTICAL,
        source_vertical_datum=NGVD29, target_vertical_datum=NAVD88,
    )
    (row,) = _clean_rows(archive, "_MI-S.csv")
    assert float(row[1]) == pytest.approx(spc.northing, abs=0.0001)
    assert float(row[2]) == pytest.approx(spc.easting, abs=0.0001)
    assert float(row[3]) == pytest.approx(199.860, abs=0.0005)


@pytest.mark.parametrize("system", list(AutoZoneSystem))
def test_auto_never_chooses_a_utm_zone(system):
    chosen = zones_choosable(system)
    assert chosen
    assert not any(zone in UTM_ZONES for zone in chosen)
    assert all(grid_name(zone) == "State Plane" for zone in chosen)


# --------------------------------------------------------------------------
# 5. Warnings.
# --------------------------------------------------------------------------


def _codes(result) -> list:
    return [warning.code for _id, warning in result.warnings]


def test_a_state_plane_coordinate_fed_as_utm_refuses(tmp_path):
    """NCAT's Michigan Central coordinate (61,379.810 / 6,016,088.527 m) read
    as 16N lands 44 degrees from 16N's meridian. Since the interim gate's
    MEDIUM 1 the engine refuses there (tm.DOMAIN_LIMIT_DEGREES) - stronger than
    the easting warning this pinned before - and the refusal names the point,
    the zone, and, because the position is nowhere near Michigan, tells the
    surveyor to check the zone and units rather than to pick a UTM zone in the
    Atlantic."""
    with pytest.raises(TransverseMercatorDomainError) as refused:
        _job(
            tmp_path, "1,61379.810,6016088.527,,P\n", direction=Direction.ZONE_TO_GEODETIC,
            source_zone=UTM16, target_zone=None,
            longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        )
    message = str(refused.value)
    assert message.startswith("point 1 (NAD83(2011) / UTM zone 16N): ")
    assert "44.261839 degrees from the central meridian of zone 16N" in message
    assert "choose that zone" not in message
    assert "not a coordinate in this zone" in message


def test_a_utm_easting_out_of_range_still_warns_inside_the_domain():
    """The UTM easting range (500,000 m +/- 400 km) still stands. In a job a
    coordinate that far off is refused by the engine first - by the domain
    limit, or, where the inverse series turns over and recovers a longitude
    back inside it (an easting about 1.4 million metres or more off the false
    easting), by the inverse closure check (the re-confirmation's N1) - so the
    range is held here directly."""
    from michspc.spc.convert import easting_looks_wrong_for_zone

    assert easting_looks_wrong_for_zone(6016088.527, UTM16)
    assert easting_looks_wrong_for_zone(99999.0, UTM16)
    assert not easting_looks_wrong_for_zone(100000.0, UTM16)
    assert not easting_looks_wrong_for_zone(900000.0, UTM16)


def test_an_in_band_utm_point_raises_no_warning(tmp_path):
    anchor = NAD83_2011_ANCHORS[0]
    result, _archive = _job(
        tmp_path, f"1,{anchor.northing},{anchor.easting},,P\n",
        direction=Direction.ZONE_TO_ZONE, source_zone=UTM16, target_zone=MI_CENTRAL,
    )
    assert _codes(result) == []


def test_16n_stretched_to_82_5_w_warns_on_extent_only(tmp_path):
    """82.5 W is 4.5 degrees east of 16N's meridian: outside its band, inside
    its easting range, and - at 43.0 N, St. Clair County - inside Michigan, so
    the outside-Michigan warning does not fire. (The point was 42.5 N until
    the interim gate's MEDIUM 2 fix: that is Lake St. Clair on the Ontario
    side, in no Michigan county, and now warns as outside Michigan.)"""
    result, _archive = _job(
        tmp_path, "1,43.0,-82.5,,P\n", direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None, target_zone=UTM16, geodetic_frame=NAD83_2011,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    assert _codes(result) == [WarningCode.OUTSIDE_ZONE_EXTENT]


# --------------------------------------------------------------------------
# 6. Every sentence that names a grid names the right one.
# --------------------------------------------------------------------------


def test_grid_name_is_state_plane_for_everything_but_a_utm_zone():
    assert grid_name(UTM16) == grid_name(UTM16_2022) == "UTM"
    assert grid_name(MI_SOUTH) == grid_name(SPCS2022_261008) == "State Plane"
    # Not yet validated: the wording every such sentence always printed.
    assert grid_name(None) == grid_name("2113") == grid_name(AUTO_ZONE) == "State Plane"
    assert grid_names_phrase([MI_SOUTH, UTM16]) == "State Plane and UTM"
    assert grid_names_phrase([UTM16, UTM17]) == "UTM"
    assert grid_names_phrase([MI_SOUTH, MI_CENTRAL]) == "State Plane"


def test_auto_from_a_utm_input_names_utm_coordinates(tmp_path):
    with pytest.raises(ValueError, match="its input is UTM coordinates, and Auto chooses"):
        _job(tmp_path, "1,1.0,2.0,,P\n", direction=Direction.ZONE_TO_ZONE,
             source_zone=UTM16, target_zone=AUTO_ZONE, auto_frame=NAD83_2011)
    with pytest.raises(ValueError, match="its input is State Plane coordinates, and Auto"):
        _job(tmp_path, "1,1.0,2.0,,P\n", name="spc", direction=Direction.ZONE_TO_ZONE,
             source_zone=MI_SOUTH, target_zone=AUTO_ZONE, auto_frame=NAD83_2011)


def test_a_stray_longitude_convention_on_a_utm_vertical_only_job_names_utm(tmp_path):
    with pytest.raises(ValueError, match="A vertical-only job reading UTM coordinates was given"):
        _job(tmp_path, "1,1.0,2.0,200.0,P\n", direction=Direction.VERTICAL_ONLY,
             source_zone=UTM16, target_zone=None, vertical_mode=VerticalMode.VERTICAL,
             source_vertical_datum=NGVD29, target_vertical_datum=NAVD88,
             longitude_convention=LongitudeConvention.NEGATIVE_WEST)


def test_a_stray_geodetic_frame_on_a_utm_input_names_utm(tmp_path):
    with pytest.raises(ValueError, match="the input is UTM coordinates and nothing is written"):
        _job(tmp_path, "1,1.0,2.0,200.0,P\n", direction=Direction.VERTICAL_ONLY,
             source_zone=UTM16, target_zone=None, vertical_mode=VerticalMode.VERTICAL,
             source_vertical_datum=NGVD29, target_vertical_datum=NAVD88,
             geodetic_frame=NATRF2022)


def test_a_stray_observation_date_names_the_grids_the_job_reads(tmp_path):
    with pytest.raises(ValueError, match=r"it reads and writes only State Plane and UTM coordinates\."):
        _job(tmp_path, "1,1.0,2.0,,P\n", direction=Direction.ZONE_TO_ZONE,
             source_zone=MI_SOUTH, target_zone=UTM16,
             observation_date=datetime.date(2025, 6, 15))
    with pytest.raises(ValueError, match=r"it reads and writes only UTM coordinates\."):
        _job(tmp_path, "1,1.0,2.0,,P\n", name="uu", direction=Direction.ZONE_TO_ZONE,
             source_zone=UTM16, target_zone=UTM17,
             observation_date=datetime.date(2025, 6, 15))


def test_a_0_360_longitude_into_a_utm_zone_names_the_utm_conversion(tmp_path):
    with pytest.raises(ValueError, match="while the UTM conversion placed the point"):
        _job(tmp_path, "1,43.0,275.5,,P\n", direction=Direction.GEODETIC_TO_ZONE,
             source_zone=None, target_zone=UTM16, geodetic_frame=NAD83_2011,
             longitude_convention=LongitudeConvention.NEGATIVE_WEST)


# --------------------------------------------------------------------------
# 7. The record (U4).
# --------------------------------------------------------------------------


def _conversion_line(record: str) -> str:
    (line,) = [l for l in record.splitlines() if l.startswith("Conversion ")]
    return line


def test_the_conversion_line_names_utm_in_both_directions(tmp_path):
    anchor = NAD83_2011_ANCHORS[0]
    _r, to_utm = _job(
        tmp_path, f"1,{anchor.latitude},{anchor.longitude},,P\n", name="a",
        direction=Direction.GEODETIC_TO_ZONE, source_zone=None, target_zone=UTM16,
        geodetic_frame=NAD83_2011, longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    _r, from_utm = _job(
        tmp_path, f"1,{anchor.northing},{anchor.easting},,P\n", name="b",
        direction=Direction.ZONE_TO_GEODETIC, source_zone=UTM16, target_zone=None,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    _r, zone_to_zone = _job(
        tmp_path, f"1,{anchor.northing},{anchor.easting},,P\n", name="c",
        direction=Direction.ZONE_TO_ZONE, source_zone=UTM16, target_zone=MI_CENTRAL,
    )
    assert _conversion_line(_record(to_utm)) == "Conversion         geodetic to UTM"
    assert _conversion_line(_record(from_utm)) == "Conversion         UTM to geodetic"
    # "zone to zone" is true of a UTM end: a UTM zone is a zone, and the FROM
    # and TO blocks name each zone's system.
    assert _conversion_line(_record(zone_to_zone)) == "Conversion         zone to zone"


def test_a_state_plane_jobs_conversion_line_is_the_directions_value(tmp_path):
    _r, archive = _job(
        tmp_path, "1,43.0,-84.5,,P\n", direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None, target_zone=MI_SOUTH, geodetic_frame=NAD83_2011,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    assert _conversion_line(_record(archive)) == "Conversion         geodetic to State Plane"


def test_a_natrf2022_utm_zone_beside_an_spcs2022_zone_is_one_era(tmp_path):
    """The era is the FRAME's. Sorted by SPCS2022 code, this job raised at write."""
    code, northing, easting = _ncat_state_plane(NATRF2022_GROUPS["261008"][0])
    _r, archive = _job(
        tmp_path, f"1,{northing},{easting},,P\n", direction=Direction.ZONE_TO_ZONE,
        source_zone=zone_by_code(code), target_zone=UTM16_2022,
    )
    record = _record(archive)
    assert "The SPCS2022 zone:" in record
    assert "The UTM zone:" in record
    assert "Thirty-four" in record


def test_two_eras_in_one_hand_built_settings_record_still_refuse_in_the_record():
    """job.run refuses the pair first; the record checks it again, in the same words."""

    class Settings:
        source_zone = UTM16
        target_zone = SPCS2022_261008
        direction = Direction.ZONE_TO_ZONE
        auto_frame = None

    with pytest.raises(ValueError, match=r"^This job names zones from two eras - NAD83\(2011\) / UTM"):
        report._method_and_verification(Settings())


def test_the_utm_counts_the_record_prints_are_the_fixtures():
    assert report.UTM_NAD83_2011_ANCHOR_COUNT == len(NAD83_2011_ANCHORS) == 212
    assert report.UTM_NATRF2022_ANCHOR_COUNT == len(NATRF2022_ANCHORS) == 34
    assert report.UTM_NAD83_2011_ANCHOR_WORDS == "Two hundred twelve"
    assert report.UTM_NATRF2022_ANCHOR_WORDS == "Thirty-four"
    # The NCAT zones the paragraphs name.
    assert sorted({a.zone for a in NAD83_2011_ANCHORS}) == [16, 17]
    assert sorted({a.zone for a in NATRF2022_ANCHORS}) == [16]


SPCS83_ARM_SENTENCES = ("Lambert", "Appendix C", "Twenty-seven", "three Michigan zones",
                        "three\nMichigan zones", "spanning the three zones")


def _normalised(archive: Path) -> str:
    text = record_root_normalised(_record(archive), archive.parent)
    return re.sub(r"^Generated          .*$", "Generated          <normalised>", text, flags=re.M)


def _pure_utm_job(tmp_path, frame, zone, anchor):
    return _job(
        tmp_path, f"1,{anchor.latitude},{anchor.longitude},200.000,P\n", name="rec",
        direction=Direction.GEODETIC_TO_ZONE, source_zone=None, target_zone=zone,
        geodetic_frame=frame, longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )


@pytest.mark.parametrize(
    "frame, zone, anchors, expected",
    [
        (NAD83_2011, UTM16, NAD83_2011_ANCHORS, NAD83_2011_UTM_RECORD),
        (NATRF2022, UTM16_2022, NATRF2022_ANCHORS, NATRF2022_UTM_RECORD),
    ],
    ids=["NAD83(2011)", "NATRF2022"],
)
def test_the_whole_utm_record_is_pinned_per_frame(tmp_path, frame, zone, anchors, expected):
    _r, archive = _pure_utm_job(tmp_path, frame, zone, anchors[0])
    record = _normalised(archive)
    assert record == expected
    for sentence in SPCS83_ARM_SENTENCES:
        assert sentence not in record, sentence
    assert "State Plane" not in record.split("METHOD")[1].split("Geoid model")[0].replace(
        "State Plane Coordinate System of", ""
    )


_METHOD_HEAD = "METHOD\n" + "-" * 78 + "\n"


def _method_section(archive) -> str:
    """The record's METHOD section, from its first line to "Geoid model"."""
    text = _record(archive)
    start = text.index(_METHOD_HEAD) + len(_METHOD_HEAD)
    return text[start : text.index("Geoid model        ")]


@pytest.mark.parametrize(
    "source, target, northing, easting, expected",
    [
        # NCAT's own Michigan Central coordinate for anchor r3_spcs83_019.
        ("2112", "16N", "61379.810", "6016088.527", MIXED_SPCS83_UTM_METHOD),
        # Beta NCAT's own 261008 coordinate at 43.294 N, 85.319 W, frozen at
        # review/autozone-r0/raw/ncat_probe/spcs2022_000.html.
        ("261008", "16N-2022", "283508.506", "1396002.569", MIXED_SPCS2022_UTM_METHOD),
    ],
    ids=["SPCS83+UTM", "SPCS2022+UTM-2022"],
)
def test_the_mixed_records_method_section_is_pinned_whole(
    tmp_path, source, target, northing, easting, expected
):
    """The interim gate's LOW 1. The State Plane era's own verification block,
    under its subhead, then the UTM arm - each byte of it."""
    _result, archive = _job(
        tmp_path, f"1,{northing},{easting},200,P\n",
        direction=Direction.ZONE_TO_ZONE,
        source_zone=zone_by_code(source), target_zone=zone_by_code(target),
    )
    assert _method_section(archive) == expected
