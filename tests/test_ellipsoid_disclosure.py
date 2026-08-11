"""What the written outputs SAY about an ellipsoid-height conversion (WP-E3).

The rule this package exists to hold: a surveyor reading only the files, six
months later, must be able to tell what kind of height went in and what came
out. That is not decoration on a job whose Z column can differ by 34 m
depending on the answer.

The two disclosures that carry the most weight, because the numbers alone
cannot distinguish them:

* a HORIZONTAL job writes the ellipsoid height straight back into the Z
  column, so the record must say so plainly - the export looks exactly like an
  elevation export and is not one;
* a point off the geoid tile in a vertical mode gets no Z at all, and the
  ELEVATIONS section must not explain that with the VERTCON sentence, because
  on an identity job no VERTCON grid was ever loaded. That sentence would be
  the WP-R2-fix-C class of falsehood arriving through a third door, and the
  design review caught it before this feature shipped.
"""

from __future__ import annotations

import csv

import pytest

from michspc.fileio import exports, geoid, pnezd
from michspc.fileio.report import build_report
from michspc.job import (
    Direction,
    JobSettings,
    LongitudeConvention,
    VerticalMode,
    run,
)
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.vertical import NAVD88, NGVD29, HeightKind
from michspc.spc.zones import MI_NORTH
from tests.fixtures.geoid_anchors import GEOID_ANCHORS

HOUGHTON_LATITUDE = 47.1211
HOUGHTON_LONGITUDE = -88.5694
N18_FIXTURE = next(
    a.geoid_height_m
    for a in GEOID_ANCHORS
    if a.latitude == HOUGHTON_LATITUDE and a.longitude == HOUGHTON_LONGITUDE
)
HOUGHTON_ELLIPSOID_M = 200.000 + N18_FIXTURE


def _vertical(tmp_path=None, **overrides) -> JobSettings:
    base = dict(
        input_path=(tmp_path / "in.csv") if tmp_path else None,
        output_directory=(tmp_path / "out") if tmp_path else None,
        direction=Direction.VERTICAL_ONLY,
        source_zone=None,
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
        geoid_model=geoid.GEOID18_MODEL,
    )
    base.update(overrides)
    return JobSettings(**base)


def _horizontal(tmp_path=None, **overrides) -> JobSettings:
    base = dict(
        input_path=(tmp_path / "in.csv") if tmp_path else None,
        output_directory=(tmp_path / "out") if tmp_path else None,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_NORTH,
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geoid_model=geoid.GEOID18_MODEL,
    )
    base.update(overrides)
    return JobSettings(**base)


def _at_houghton(height: float) -> pnezd.PnezdFile:
    return pnezd.parse_lines(
        [f"1,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},{height:.3f},GNSS"]
    )


_ZONE_ROW = [f"1,500000.0,8000000.0,{HOUGHTON_ELLIPSOID_M:.3f},GNSS"]


# ==========================================================================
# The job record.
# ==========================================================================


def test_the_record_states_the_conversion_the_model_and_the_digest(tmp_path):
    text = build_report(
        run(
            _vertical(tmp_path, input_height_kind=HeightKind.ELLIPSOID),
            source=_at_houghton(HOUGHTON_ELLIPSOID_M),
        )
    )

    assert "ELLIPSOID HEIGHT CONVERSION" in text
    assert "H = h - N" in " ".join(text.split())
    assert "GEOID18" in text
    assert geoid.GEOID18_MODEL.tile_filename in text
    assert geoid.GEOID18_MODEL.sha256 in text
    # The datum of the derived heights is the MODEL's, and the record says so
    # rather than leaving a reader to assume it from the datum dropdowns.
    assert "NAVD88" in text
    assert "in no vertical datum" in " ".join(text.split())


def test_the_record_says_a_horizontal_job_wrote_the_height_back_unchanged(tmp_path):
    """The load-bearing sentence. A horizontal ellipsoid export is
    indistinguishable from an elevation export by inspection."""
    text = build_report(
        run(
            _horizontal(tmp_path, input_height_kind=HeightKind.ELLIPSOID),
            source=pnezd.parse_lines(_ZONE_ROW),
        )
    )

    # The record wraps its paragraphs, so the phrases are checked against
    # whitespace-normalised text rather than against one wrapped line.
    flat = " ".join(text.split())
    assert "ELLIPSOID HEIGHT CONVERSION" in text
    assert "ELLIPSOID HEIGHT EXACTLY AS SUPPLIED" in flat
    assert "used only to compute the elevation and combined factors" in flat


def test_the_record_says_a_vertical_job_wrote_the_derived_elevation(tmp_path):
    text = build_report(
        run(
            _vertical(tmp_path, input_height_kind=HeightKind.ELLIPSOID),
            source=_at_houghton(HOUGHTON_ELLIPSOID_M),
        )
    )

    flat = " ".join(text.split())
    assert "carries the derived orthometric height" in flat
    assert "EXACTLY AS SUPPLIED" not in flat


def test_the_ellipsoid_block_precedes_the_vertical_datum_block(tmp_path):
    """h -> H runs before the datum shift, and the record reads in the order
    the program worked in."""
    text = build_report(
        run(
            _vertical(
                tmp_path,
                input_height_kind=HeightKind.ELLIPSOID,
                target_vertical_datum=NGVD29,
            ),
            source=_at_houghton(HOUGHTON_ELLIPSOID_M),
        )
    )

    assert text.index("ELLIPSOID HEIGHT CONVERSION") < text.index(
        "VERTICAL DATUM TRANSFORMATION"
    )


def test_an_orthometric_job_says_nothing_about_ellipsoid_heights(tmp_path):
    """The regression floor: every job that predates this feature is
    untouched, and the block is absent by construction rather than by luck."""
    text = build_report(run(_horizontal(tmp_path), source=pnezd.parse_lines(_ZONE_ROW)))

    assert "ELLIPSOID HEIGHT CONVERSION" not in text
    assert "H = h - N" not in text


def test_a_point_off_the_tile_is_not_blamed_on_the_vertcon_grids(tmp_path):
    """The design review's catch, pinned.

    An identity job loads no VERTCON grid at all, so "the point lies outside
    the VERTCON grids" would name a grid that was never read - the WP-R2
    fix C class through a third door.
    """
    text = build_report(
        run(
            _vertical(tmp_path, input_height_kind=HeightKind.ELLIPSOID),
            source=pnezd.parse_lines(["1,39.5,-84.0,166.204,OFF"]),
        )
    )

    flat = " ".join(text.split())
    assert "outside the VERTCON grids" not in flat
    assert "could NOT be converted to an orthometric height" in flat
    assert "GEOID18 tile this program ships" in flat
    assert "no geoid separation exists there" in flat
    # And it is not called a blank field either - the Z was read perfectly.
    assert "had NO usable elevation" not in flat


# ==========================================================================
# The audit CSV.
# ==========================================================================


def test_the_audit_csv_names_the_input_height_kind_in_every_mode():
    for settings, source in (
        (
            _horizontal(input_height_kind=HeightKind.ELLIPSOID),
            pnezd.parse_lines(_ZONE_ROW),
        ),
        (
            _vertical(input_height_kind=HeightKind.ELLIPSOID),
            _at_houghton(HOUGHTON_ELLIPSOID_M),
        ),
    ):
        result = run(settings, source=source)
        header = exports.audit_columns(result)
        row = exports.audit_rows(result)[1]
        cells = dict(zip(header, row))

        assert "Input height kind" in header
        assert cells["Input height kind"] == "ellipsoid"


def test_the_vertical_audit_row_keeps_its_arithmetic_closed():
    """Source elevation + Vertical shift = Elevation, still, with the supplied
    ellipsoid height in a column of its own.

    That is why "Source elevation" holds the DERIVED pre-shift height rather
    than the raw h: this column has always meant "what the shift was applied
    to", and the shift was applied to H.
    """
    result = run(
        _vertical(
            input_height_kind=HeightKind.ELLIPSOID, target_vertical_datum=NGVD29
        ),
        source=_at_houghton(HOUGHTON_ELLIPSOID_M),
    )
    header = exports.audit_columns(result)
    cells = dict(zip(header, exports.audit_rows(result)[1]))

    assert "Ellipsoid height in (m)" in header
    assert float(cells["Ellipsoid height in (m)"]) == pytest.approx(
        HOUGHTON_ELLIPSOID_M, abs=0.0002
    )
    source_elevation = float(cells["Source elevation (m)"])
    shift = float(cells["Vertical shift (m)"])
    elevation = float(cells["Elevation"])
    assert source_elevation + shift == pytest.approx(elevation, abs=0.0002)
    # The supplied height is NOT what the shift was applied to.
    assert source_elevation != pytest.approx(HOUGHTON_ELLIPSOID_M, abs=1.0)


def test_the_ellipsoid_height_column_reconstructs_the_supplied_value():
    """The consistency check the CSV has displayed since 0.1.0."""
    result = run(
        _vertical(input_height_kind=HeightKind.ELLIPSOID),
        source=_at_houghton(HOUGHTON_ELLIPSOID_M),
    )
    cells = dict(zip(exports.audit_columns(result), exports.audit_rows(result)[1]))

    assert float(cells["Ellipsoid height (m)"]) == pytest.approx(
        HOUGHTON_ELLIPSOID_M, abs=0.0002
    )


def test_an_orthometric_job_gains_no_column_at_all():
    """The standing rule (#17): a pre-existing job's CSV layout does not
    move by a byte. Asserted as an exact header, not a membership test."""
    horizontal = run(_horizontal(), source=pnezd.parse_lines(_ZONE_ROW))
    assert "Input height kind" not in exports.audit_columns(horizontal)
    assert "Ellipsoid height in (m)" not in exports.audit_columns(horizontal)

    vertical = run(_vertical(), source=_at_houghton(200.0))
    assert "Input height kind" not in exports.audit_columns(vertical)
    assert "Ellipsoid height in (m)" not in exports.audit_columns(vertical)


@pytest.mark.parametrize("unit", [METERS, INTERNATIONAL_FEET])
def test_the_new_columns_carry_the_input_unit(unit):
    """#47's rule: the vertical columns are in the job's INPUT unit, and the
    heading and the value cannot claim different ones."""
    places = 4 if unit is METERS else 3
    written = f"{unit.from_meters(HOUGHTON_ELLIPSOID_M):.{places}f}"
    result = run(
        _vertical(
            input_height_kind=HeightKind.ELLIPSOID,
            input_unit=unit,
            output_unit=unit,
        ),
        source=pnezd.parse_lines(
            [f"1,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},{written},GNSS"]
        ),
    )
    header = exports.audit_columns(result)
    cells = dict(zip(header, exports.audit_rows(result)[1]))

    heading = f"Ellipsoid height in ({unit.code})"
    assert heading in header
    assert float(cells[heading]) == pytest.approx(float(written), abs=0.0011)


def test_the_clean_export_still_holds_five_headerless_fields(tmp_path):
    """Nothing this feature adds may reach the CAD import."""
    input_path = tmp_path / "gnss.csv"
    input_path.write_text(
        f"1,{HOUGHTON_LATITUDE},{HOUGHTON_LONGITUDE},"
        f"{HOUGHTON_ELLIPSOID_M:.3f},GNSS\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    out.mkdir()
    result = run(
        _vertical(
            input_height_kind=HeightKind.ELLIPSOID,
            input_path=input_path,
            output_directory=out,
        )
    )
    written = exports.write_all(result)

    import zipfile

    with zipfile.ZipFile(written["archive"]) as zf:
        name = exports.member_names(result)["pnezd"]
        text = zf.read(name).decode("utf-8")

    rows = [r for r in csv.reader(text.splitlines()) if r]
    assert len(rows) == 1
    assert len(rows[0]) == 5
    assert "ellipsoid" not in text.lower()
