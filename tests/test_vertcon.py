"""The VERTCON 3.0 grid reader: markers, the pair, and the interpolation anchoring.

Every expected value below is derived by hand in the comment above it, or is a
frozen NGS NCAT figure from ``tests/fixtures/vertcon_anchors.py``. No test
touches the network.

The three properties this file exists to hold, in order of how much damage their
loss would do:

1. **A reading is never invented.** ``spc.vertical.signed_shift`` legitimately
   accepts ``grid_value_m=0.0``, because the transformation grid genuinely
   crosses zero inside Michigan, so a 0.0 fabricated by this reader would be
   indistinguishable from a real one and would report an unconverted height as
   converted. Every failure path must raise.
2. **The interpolation anchoring.** Both grids are read by a biquadratic whose
   3x3 stencil is anchored on the NEAREST NODE, which is not the anchoring
   GEOID18 uses. Getting that wrong does not fail; it produces shifts that are
   millimetres out and look entirely ordinary.
3. **The Fortran record markers.** GEOID18 has nothing equivalent, so this is the
   one NGS format in the program whose structure can be checked rather than
   assumed.
4. **A number that cannot be an uncertainty is never handed out as one.** The
   error grid interpolates below zero at a small fraction of Michigan positions.
   The raw model output stays readable under a name that says what it is; the
   accessor named ``sigma_m`` refuses, and says in the refusal that the shift is
   unaffected - because the wrong conclusion to draw is "the elevation is bad".
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import struct
from pathlib import Path

import pytest

from michspc.fileio import geoid18, ngs_grid, vertcon
from michspc.spc import vertical
from tests.fixtures.vertcon_anchors import (
    NAVD88_TO_NGVD29_ANCHORS,
    NGVD29_TO_NAVD88_ANCHORS,
)

FORWARD_IDS = [a.name for a in NGVD29_TO_NAVD88_ANCHORS]
INVERSE_IDS = [a.name for a in NAVD88_TO_NGVD29_ANCHORS]


# NCAT prints an orthometric height to 0.001 m, so a printed figure carries
# +/-0.0005 m of quantization. Each anchor's shift is ``target_height_m -
# 200.000``, and the 200.000 is the request input echoed back rather than a
# printed-and-rounded figure, so only ONE term of that difference is quantized:
# the bound on a correct reader is half a unit in the last place, not a whole
# one. Sigma is a single printed figure and carries the same half unit.
#
# Measured over the 20 forward anchors, both grids, with the scheme this module
# ships (nearest-node-anchored biquadratic):
#
#     .trn   max 0.4707 mm   mean 0.2070 mm
#     .err   max 0.4716 mm   mean 0.2149 mm
#
# Both sit just inside the quantization floor. The wrong variants do not:
#
#     .trn   floor-anchored biquadratic   8.4573 mm      bilinear  17.7262 mm
#     .err   floor-anchored biquadratic   3.0416 mm      bilinear   4.5468 mm
#
# So 0.0005 m discriminates by a factor of 6 against the nearest wrong scheme.
# **Do not loosen it.** At 2 mm it would admit bilinear on the uncertainty grid
# and at 5 mm the floor-anchored biquadratic, and it would stop telling the
# schemes apart - which is exactly the way DESIGN.md amendment #31's pin
# stopped discriminating while still passing.
NCAT_QUANTIZATION_M = 0.0005


@pytest.fixture(scope="module")
def grids():
    """The shipped pair, authenticated, loaded once for this module."""
    return vertcon.default_grids()


@pytest.fixture(scope="module")
def trn(grids):
    return grids.transformation


@pytest.fixture(scope="module")
def err(grids):
    return grids.uncertainty


# --------------------------------------------------------------------------
# Building VERTCON-shaped files by hand, so a structural refusal can be aimed
# at one byte without carrying a 2.4 MB copy of the real grid through every test.
# --------------------------------------------------------------------------

# A 3x3 lattice on the real grid's spacing, small enough to reason about and
# just large enough for the 3x3 biquadratic stencil.
#
#   south 24 N, three rows 0.05 apart      -> 24.00, 24.05, 24.10 N
#   west 235 E, three columns 0.05 apart   -> 235.00, 235.05, 235.10 E
#                                           = -125.00, -124.95, -124.90 signed
#
# Values, row-major, southernmost row first, each row west to east:
#
#       lon ->   -125.00  -124.95  -124.90
#   lat 24.10       6.0      9.0     13.0
#   lat 24.05       3.0      5.0      8.0
#   lat 24.00       1.0      2.0      4.0
TINY = (1.0, 2.0, 4.0, 3.0, 5.0, 8.0, 6.0, 9.0, 13.0)


def _vertcon_bytes(
    south: float = 24.0,
    west: float = 235.0,
    dlat: float = 0.05,
    dlon: float = 0.05,
    rows: int = 3,
    columns: int = 3,
    ikind: int = 1,
    values=TINY,
    header_open: int | None = None,
    header_close: int | None = None,
    row_open: dict[int, int] | None = None,
    row_close: dict[int, int] | None = None,
    tail: bytes = b"",
) -> bytes:
    """A file in the layout plan section 2.2 documents, corruptible one field at a time.

    Defaults produce a structurally perfect file. Every override exists so a test
    can break exactly one thing.
    """
    record = struct.pack("<4d3i", south, west, dlat, dlon, rows, columns, ikind)
    marker = 44 if header_open is None else header_open
    closing = 44 if header_close is None else header_close
    raw = struct.pack("<i", marker) + record + struct.pack("<i", closing)

    row_bytes = columns * 4
    row_open = row_open or {}
    row_close = row_close or {}
    for row in range(rows):
        payload = values[row * columns : (row + 1) * columns]
        raw += struct.pack("<i", row_open.get(row, row_bytes))
        raw += struct.pack(f"<{columns}f", *payload)
        raw += struct.pack("<i", row_close.get(row, row_bytes))

    return raw + tail


def _tiny(tmp_path: Path, name: str = "tiny.b", **overrides) -> Path:
    path = tmp_path / name
    path.write_bytes(_vertcon_bytes(**overrides))
    return path


def _load_tiny(tmp_path: Path, name: str = "tiny.b", kind=None, **overrides):
    return vertcon.load_grid(
        _tiny(tmp_path, name, **overrides), kind or vertcon.TransformationGrid
    )


# ==========================================================================
# The shipped files.
# ==========================================================================


def test_the_shipped_grids_match_their_pinned_checksums():
    """Both grids are committed unmodified from NGS; prove they still are.

    The substitution this catches is concrete rather than hypothetical: VERTCON
    2.0 is what the older NGS directory and VDatum both lead to, and it looks
    exactly like a VERTCON grid while disagreeing with NGS's own service by up to
    43.85 mm across Michigan (docs/PLAN-vertical-datums.md section 2.6).
    """
    assert (
        hashlib.sha256(vertcon.VERTCON3_TRN_TILE.read_bytes()).hexdigest()
        == vertcon.VERTCON3_TRN_SHA256
    )
    assert (
        hashlib.sha256(vertcon.VERTCON3_ERR_TILE.read_bytes()).hexdigest()
        == vertcon.VERTCON3_ERR_SHA256
    )


def test_the_two_pins_are_two_pins():
    """Anti-vacuousness: two different files must carry two different digests.

    A copy-paste that pinned the transformation grid's digest twice would leave
    the uncertainty grid unauthenticated while every checksum test still passed.
    """
    assert vertcon.VERTCON3_TRN_SHA256 != vertcon.VERTCON3_ERR_SHA256
    assert vertcon.VERTCON3_TRN_TILE != vertcon.VERTCON3_ERR_TILE
    assert (
        vertcon.VERTCON3_TRN_TILE.read_bytes()
        != vertcon.VERTCON3_ERR_TILE.read_bytes()
    )


def test_both_shipped_files_are_the_documented_length():
    """Hand derivation of 2,465,424 bytes from the header alone:

        bracketed header  = 4 + 44 + 4              =        52
        one row           = 4 + 1181 * 4 + 4        =     4,732
        521 rows          = 521 * 4732              = 2,465,372
        total             = 52 + 2,465,372          = 2,465,424

    which is the byte count docs/PLAN-vertical-datums.md section 2.1 records for
    each file.
    """
    assert 4 + 44 + 4 == vertcon.HEADER_BLOCK_BYTES == 52
    assert 4 + 1181 * 4 + 4 == 4732
    assert 52 + 521 * 4732 == 2465424

    assert vertcon.VERTCON3_TRN_TILE.stat().st_size == 2465424
    assert vertcon.VERTCON3_ERR_TILE.stat().st_size == 2465424


def test_the_header_sits_behind_a_marker_where_geoid18s_does_not():
    """The first four bytes are what tell the two NGS formats apart.

    VERTCON writes the Fortran record length, 44. GEOID18 writes the low half of
    SLAT = 40.0 as a little-endian double, whose first four bytes are zero. So a
    GEOID18 tile handed to this reader fails on byte 0 rather than being read as
    a VERTCON grid with a nonsense header.
    """
    for tile in (vertcon.VERTCON3_TRN_TILE, vertcon.VERTCON3_ERR_TILE):
        assert struct.unpack_from("<i", tile.read_bytes(), 0)[0] == 44

    assert struct.unpack_from("<i", geoid18.GEOID18_TILE.read_bytes(), 0)[0] == 0


def test_a_geoid18_tile_is_refused_by_this_reader():
    """The live consequence of the byte-0 difference above."""
    with pytest.raises(vertcon.VertconError) as caught:
        vertcon.load_grid(geoid18.GEOID18_TILE, vertcon.TransformationGrid)

    message = str(caught.value)
    assert "bad Fortran record marker at byte 0" in message
    assert "expected 44, found 0" in message


def test_every_fortran_marker_in_both_shipped_files_is_correct():
    """Read independently of the reader, so this measures the files.

    Header 44/44, then 521 rows each bracketed by NLON * 4 = 1181 * 4 = 4724, and
    the walk must land exactly on the end of the file. That is the check
    docs/PLAN-vertical-datums.md section 2.2 predicted and DESIGN.md amendment #22
    called a free structural check.
    """
    for tile in (vertcon.VERTCON3_TRN_TILE, vertcon.VERTCON3_ERR_TILE):
        raw = tile.read_bytes()
        assert struct.unpack_from("<i", raw, 0)[0] == 44
        assert struct.unpack_from("<i", raw, 48)[0] == 44

        rows, columns = 521, 1181
        row_bytes = columns * 4
        assert row_bytes == 4724

        offset = 52
        for row in range(rows):
            assert struct.unpack_from("<i", raw, offset)[0] == row_bytes, row
            offset += 4 + row_bytes
            assert struct.unpack_from("<i", raw, offset)[0] == row_bytes, row
            offset += 4

        assert offset == len(raw) == 2465424


def test_the_reader_consumes_the_whole_file(trn, err):
    """Every cell the header promises is present and was unpacked.

    521 * 1181 = 615,301 cells in each grid.
    """
    assert 521 * 1181 == 615301
    assert len(trn.values) == 615301
    assert len(err.values) == 615301


# ==========================================================================
# Geometry.
# ==========================================================================


def test_the_shipped_geometry_is_the_one_the_v0_gate_measured(trn, err):
    """24-50 N, 235-294 E (125 W to 66 W), 521 x 1181 at 0.05 degrees.

    Hand check of the extents from the counts:
        north = 24.0  + (521 - 1)  * 0.05 = 24  + 26 = 50 N
        east  = 235.0 + (1181 - 1) * 0.05 = 235 + 59 = 294 E = 294 - 360 = -66
    """
    for grid in (trn, err):
        assert grid.south_latitude == pytest.approx(24.0)
        assert grid.west_longitude == pytest.approx(235.0)
        assert grid.latitude_spacing == pytest.approx(0.05)
        assert grid.longitude_spacing == pytest.approx(0.05)
        assert grid.row_count == 521
        assert grid.column_count == 1181
        assert grid.north_latitude == pytest.approx(50.0, abs=1e-9)
        assert grid.east_longitude == pytest.approx(294.0, abs=1e-9)
        assert ngs_grid.to_signed_longitude(grid.east_longitude) == pytest.approx(
            -66.0, abs=1e-9
        )


def test_the_geometry_record_states_the_same_thing_the_files_do(trn):
    """The expectation record is not derived from the file it checks."""
    geometry = vertcon.VERTCON3_CONUS_GEOMETRY
    assert geometry.south_latitude == trn.south_latitude
    assert geometry.west_longitude == trn.west_longitude
    assert geometry.latitude_spacing == pytest.approx(trn.latitude_spacing)
    assert geometry.longitude_spacing == pytest.approx(trn.longitude_spacing)
    assert geometry.row_count == trn.row_count
    assert geometry.column_count == trn.column_count
    assert "VERTCON 3.0" in geometry.name


def test_one_grid_covers_every_corner_of_every_michigan_zone(grids):
    """The 84 W seam an earlier draft budgeted for does not exist.

    It was an artifact of VDatum's three-region split of the superseded VERTCON
    2.0 (plan sections 2.2 and 2.6). One CONUS grid reaches 50 N and 125 W
    against Michigan's 48.3 N and 90.5 W.
    """
    from michspc.spc.zones import ALL_ZONES

    for zone in ALL_ZONES:
        for latitude in (zone.lat_min, zone.lat_max):
            for longitude in (zone.lon_min, zone.lon_max):
                assert grids.contains(latitude, longitude), (
                    f"{zone.abbrev} corner {latitude}, {longitude} is outside "
                    f"the shipped VERTCON pair"
                )


def test_a_transposed_header_is_caught_by_length_alone_here(tmp_path):
    """Plan section 3.3: 521 x 1181 and 1181 x 521 do not share a product.

    Hand derivation of the two lengths:
        521 rows x 1181 cols:  52 + 521 * (8 + 1181*4) = 52 + 521 * 4732 = 2,465,424
        1181 rows x 521 cols:  52 + 1181 * (8 + 521*4) = 52 + 1181 * 2092 = 2,470,704

    They differ by 5,280 bytes, so unlike GEOID18 - where the geometry record was
    the only thing that could catch a swap (DESIGN.md amendment #11, finding 6) -
    the length check catches it here on its own, before any geometry expectation
    is consulted.
    """
    assert 52 + 521 * (8 + 1181 * 4) == 2465424
    assert 52 + 1181 * (8 + 521 * 4) == 2470704

    # Real file, header rewritten to claim the transposed shape. No geometry
    # expectation is passed, so only the length check can catch it.
    raw = bytearray(vertcon.VERTCON3_TRN_TILE.read_bytes())
    struct.pack_into("<2i", raw, 4 + 32, 1181, 521)
    swapped = tmp_path / "swapped.b"
    swapped.write_bytes(bytes(raw))

    with pytest.raises(vertcon.VertconError) as caught:
        vertcon.load_grid(swapped, vertcon.TransformationGrid)

    message = str(caught.value)
    assert "declares 1181 rows of 521 cells" in message
    assert "2470704" in message
    assert "2465424" in message


def test_the_geometry_record_still_earns_its_place(tmp_path):
    """Length cannot see SLAT, WLON or the spacings.

    A file claiming to start at 25 N rather than 24 N is exactly the right
    length, and every lookup in it is one degree out - about 111 km, which in
    Michigan is the difference between Lansing and Sault Ste. Marie's shift.
    """
    raw = bytearray(vertcon.VERTCON3_TRN_TILE.read_bytes())
    struct.pack_into("<d", raw, 4, 25.0)  # SLAT
    shifted = tmp_path / "shifted.b"
    shifted.write_bytes(bytes(raw))

    # Structurally perfect: no marker, length or payload check can see it.
    vertcon.load_grid(shifted, vertcon.TransformationGrid)

    with pytest.raises(vertcon.VertconError) as caught:
        vertcon.load_grid(
            shifted,
            vertcon.TransformationGrid,
            expect_geometry=vertcon.VERTCON3_CONUS_GEOMETRY,
        )

    assert "SLAT (southernmost latitude): expected 24.0, found 25.0" in str(
        caught.value
    )


# ==========================================================================
# The Fortran markers, as refusals.
# ==========================================================================


def test_a_bad_opening_header_marker_is_refused_by_byte(tmp_path):
    with pytest.raises(vertcon.VertconError) as caught:
        _load_tiny(tmp_path, header_open=40)

    message = str(caught.value)
    assert "bad Fortran record marker at byte 0" in message
    assert "expected 44, found 40" in message
    assert "It opens the header record." in message


def test_a_bad_closing_header_marker_is_refused_by_byte(tmp_path):
    """The closing marker sits at 4 + 44 = 48."""
    with pytest.raises(vertcon.VertconError) as caught:
        _load_tiny(tmp_path, header_close=48)

    message = str(caught.value)
    assert "bad Fortran record marker at byte 48" in message
    assert "expected 44, found 48" in message
    assert "It closes the header record." in message


def test_a_bad_row_marker_is_refused_and_the_row_is_named(tmp_path):
    """Row 1 of a 3 x 3 grid, opening marker.

    Hand derivation of its offset: the bracketed header is 52 bytes, one row is
    4 + 3*4 + 4 = 20 bytes, so row 1 opens at 52 + 20 = 72.
    """
    assert 4 + 3 * 4 + 4 == 20
    assert 52 + 20 == 72

    with pytest.raises(vertcon.VertconError) as caught:
        _load_tiny(tmp_path, row_open={1: 8})

    message = str(caught.value)
    assert "bad Fortran record marker at byte 72" in message
    assert "expected 12, found 8" in message
    assert "It opens row 1 of 3" in message


def test_a_bad_closing_row_marker_is_refused_too(tmp_path):
    """Row 2 closes at 52 + 2*20 + 4 + 12 = 52 + 40 + 16 = 108."""
    assert 52 + 2 * 20 + 4 + 12 == 108

    with pytest.raises(vertcon.VertconError) as caught:
        _load_tiny(tmp_path, row_close={2: 0})

    message = str(caught.value)
    assert "bad Fortran record marker at byte 108" in message
    assert "It closes row 2 of 3" in message


def test_the_row_markers_are_checked_on_every_row_not_just_the_first(tmp_path):
    """Anti-vacuousness: a loop that validated only row 0 would pass the tests above."""
    for row in range(3):
        with pytest.raises(vertcon.VertconError, match=f"row {row} of 3"):
            _load_tiny(tmp_path, f"row{row}.b", row_open={row: 999})


def test_a_marker_check_is_not_satisfied_by_a_plausible_wrong_value(tmp_path):
    """The marker must equal NLON * 4 exactly, not merely be positive.

    A big-endian file is the case that motivates this: its markers read as huge
    numbers rather than as garbage, and every value in it would otherwise be
    unpacked with the bytes reversed.
    """
    # 44 written big-endian reads little-endian as 44 << 24 = 738,197,504.
    assert struct.unpack("<i", struct.pack(">i", 44))[0] == 738197504

    with pytest.raises(vertcon.VertconError, match="found 738197504"):
        _load_tiny(tmp_path, header_open=738197504)


def test_a_trailing_byte_is_refused(tmp_path):
    """Nothing may follow the last row.

    A 3 x 3 file is 52 + 3 * 20 = 112 bytes; one more is not a rounding
    difference, it is a file this reader does not understand.
    """
    assert 52 + 3 * 20 == 112

    with pytest.raises(vertcon.VertconError) as caught:
        _load_tiny(tmp_path, tail=b"\x00")

    message = str(caught.value)
    assert "declares 3 rows of 3 cells" in message
    assert "112 bytes" in message
    assert "113 bytes" in message


def test_a_truncated_file_is_refused(tmp_path):
    path = tmp_path / "short.b"
    path.write_bytes(_vertcon_bytes()[:100])

    with pytest.raises(vertcon.VertconError, match="truncated"):
        vertcon.load_grid(path, vertcon.TransformationGrid)


def test_a_file_too_short_for_the_bracketed_header_is_refused(tmp_path):
    """52 bytes are needed before anything can be said about the file at all."""
    path = tmp_path / "stub.b"
    path.write_bytes(b"\x00" * 51)

    with pytest.raises(vertcon.VertconError) as caught:
        vertcon.load_grid(path, vertcon.TransformationGrid)

    message = str(caught.value)
    assert "only 51 bytes" in message
    assert "52-byte bracketed VERTCON 3.0 header" in message


def test_a_missing_file_is_refused_with_a_useful_message(tmp_path):
    with pytest.raises(vertcon.VertconError, match="installation is incomplete"):
        vertcon.load_grid(tmp_path / "not-here.b", vertcon.TransformationGrid)


# ==========================================================================
# Header refusals reached through this module's dialects.
# ==========================================================================


def test_a_big_endian_grid_is_refused_by_ikind(tmp_path):
    """IKIND is the endian marker; a big-endian grid read here yields numbers."""
    with pytest.raises(vertcon.VertconError, match="IKIND=16777216"):
        _load_tiny(tmp_path, ikind=16777216)


def test_a_non_positive_spacing_is_refused(tmp_path):
    for dlat in (0.0, -0.05):
        with pytest.raises(vertcon.VertconError, match="DLAT"):
            _load_tiny(tmp_path, f"dlat{dlat}.b", dlat=dlat)


def test_a_grid_too_small_for_the_stencil_is_refused(tmp_path):
    with pytest.raises(vertcon.VertconError, match="NLAT=2"):
        _load_tiny(tmp_path, rows=2, columns=2, values=(1.0, 2.0, 3.0, 4.0))


def test_a_checksum_mismatch_is_refused_and_names_both_digests(tmp_path):
    """One flipped byte in the payload of a real grid.

    Byte 60 sits inside row 0's first cell, past the 52-byte header block and
    past row 0's 4-byte opening marker.
    """
    raw = bytearray(vertcon.VERTCON3_TRN_TILE.read_bytes())
    raw[60] ^= 0xFF
    tampered = tmp_path / "tampered.b"
    tampered.write_bytes(bytes(raw))

    with pytest.raises(vertcon.VertconError) as caught:
        vertcon.load_grid(
            tampered,
            vertcon.TransformationGrid,
            expect_sha256=vertcon.VERTCON3_TRN_SHA256,
        )

    message = str(caught.value)
    assert vertcon.VERTCON3_TRN_SHA256 in message
    assert hashlib.sha256(bytes(raw)).hexdigest() in message
    assert "VERTCON 2.0" in message


def test_a_non_finite_payload_cell_is_refused_and_located(tmp_path):
    """Plan section 2.7 found none in either shipped file, over 23,120 Michigan
    cells per grid: no NaN, no infinity, no -88.8888 (that null is a VDatum GTX
    convention, absent from the NGS .b files). The check exists because
    ``load_grid`` accepts any path.

    The cell at row 1, column 2 of a 3 x 3 grid is flat index 1 * 3 + 2 = 5.
    """
    values = list(TINY)
    values[5] = float("nan")

    with pytest.raises(vertcon.VertconError) as caught:
        _load_tiny(tmp_path, values=tuple(values))

    message = str(caught.value)
    assert "non-finite vertical shift (nan) at cell index 5" in message


def test_an_infinity_is_refused_as_well_as_a_nan(tmp_path):
    values = list(TINY)
    values[0] = float("inf")

    with pytest.raises(vertcon.VertconError, match="cell index 0"):
        _load_tiny(tmp_path, values=tuple(values))


def test_the_uncertainty_grid_speaks_of_uncertainties_not_shifts(tmp_path):
    """The same substrate check, under the other dialect."""
    values = list(TINY)
    values[5] = float("nan")

    with pytest.raises(vertcon.VertconError) as caught:
        _load_tiny(tmp_path, values=tuple(values), kind=vertcon.UncertaintyGrid)

    assert "non-finite shift uncertainty (nan) at cell index 5" in str(caught.value)


def test_a_position_outside_the_grid_is_refused_by_name(trn, err):
    """Extents derived above: 24.0 to 50.0 N, -125.0 to -66.0."""
    with pytest.raises(vertcon.VertconError) as caught:
        trn.shift_m(60.0, -84.5)

    assert str(caught.value) == (
        "Position 60.000000, -84.500000 is outside the VERTCON 3.0 tile this "
        "program ships (24.0 to 50.0 N, -125.0 to -66.0). "
        "No NGVD 29 to NAVD 88 shift can be looked up, so the elevation cannot "
        "be moved between vertical datums. VERTCON 3.0 covers the conterminous "
        "United States only. Check the coordinate, the zone and the units."
    )

    with pytest.raises(vertcon.VertconError, match="No uncertainty can be looked up"):
        err.sigma_m(60.0, -84.5)


def test_load_grid_refuses_a_kind_it_does_not_know(tmp_path):
    """The two files are byte-identical in shape, so the caller must say which."""
    path = _tiny(tmp_path)

    with pytest.raises(TypeError, match="TransformationGrid or"):
        vertcon.load_grid(path, geoid18.GeoidGrid)


# ==========================================================================
# The pair.
# ==========================================================================


def test_the_shipped_pair_shares_geometry(grids):
    """NGS publishes the two on identical geometry (plan section 2.2)."""
    for attribute in (
        "south_latitude",
        "west_longitude",
        "latitude_spacing",
        "longitude_spacing",
        "row_count",
        "column_count",
    ):
        assert getattr(grids.transformation, attribute) == getattr(
            grids.uncertainty, attribute
        )


def test_a_mismatched_pair_is_refused_naming_every_field(tmp_path):
    """The failure this prevents is silent: one position's shift beside another
    position's sigma, both plausible.

    The uncertainty grid here starts one whole degree north of the
    transformation grid, so at any given latitude the sigma read from it belongs
    to a point about 111 km away.
    """
    transformation = vertcon.load_grid(
        _tiny(tmp_path, "t.b"), vertcon.TransformationGrid
    )
    uncertainty = vertcon.load_grid(
        _tiny(tmp_path, "u.b", south=25.0, dlon=0.1), vertcon.UncertaintyGrid
    )

    with pytest.raises(vertcon.VertconError) as caught:
        vertcon.VertconGridPair(
            transformation=transformation, uncertainty=uncertainty
        )

    message = str(caught.value)
    assert "SLAT (southernmost latitude): transformation grid 24.0" in message
    assert "uncertainty grid 25.0" in message
    assert "DLON (east-west spacing): transformation grid 0.05" in message
    assert "do not describe the same" in message


def test_every_paired_field_is_checked_independently(tmp_path):
    """Anti-vacuousness: one mismatch at a time, each caught on its own."""
    transformation = vertcon.load_grid(
        _tiny(tmp_path, "base.b"), vertcon.TransformationGrid
    )

    for index, override in enumerate(
        (
            {"south": 25.0},
            {"west": 236.0},
            {"dlat": 0.1},
            {"dlon": 0.1},
            {"rows": 4, "columns": 3, "values": TINY + (20.0, 30.0, 40.0)},
            {"rows": 3, "columns": 4, "values": tuple(range(12))},
        )
    ):
        uncertainty = vertcon.load_grid(
            _tiny(tmp_path, f"odd{index}.b", **override), vertcon.UncertaintyGrid
        )
        with pytest.raises(vertcon.VertconError):
            vertcon.VertconGridPair(
                transformation=transformation, uncertainty=uncertainty
            )


def test_a_matching_pair_is_accepted(tmp_path):
    """The check above must not simply refuse everything."""
    pair = vertcon.VertconGridPair(
        transformation=vertcon.load_grid(
            _tiny(tmp_path, "a.b"), vertcon.TransformationGrid
        ),
        uncertainty=vertcon.load_grid(
            _tiny(tmp_path, "b.b"), vertcon.UncertaintyGrid
        ),
    )
    assert pair.contains(24.05, -124.95)


def test_reading_at_returns_the_shift_and_its_sigma_together(grids):
    """The accessor callers reach for, so a shift is hard to report alone."""
    shift, sigma = grids.reading_at(43.0, -84.5)
    assert shift == grids.transformation.shift_m(43.0, -84.5)
    assert sigma == grids.uncertainty.sigma_m(43.0, -84.5)


def test_a_position_outside_refuses_before_either_half_is_returned(grids):
    """Not a shift with a missing sigma, and not a sigma with a missing shift."""
    with pytest.raises(vertcon.VertconError):
        grids.reading_at(60.0, -84.5)
    assert not grids.contains(60.0, -84.5)


def test_the_module_front_door_uses_the_shipped_pair(grids):
    assert vertcon.shift_and_sigma_m(43.0, -84.5) == grids.reading_at(43.0, -84.5)


def test_the_production_path_applies_both_gates_to_both_files(monkeypatch):
    """The checksum AND the geometry expectation, on each of the two grids.

    They fail differently and neither implies the other: the checksum catches any
    altered byte, the geometry check catches a file that is internally consistent
    and describes the wrong grid. No file can be built that passes one and fails
    the other - the checksum pins the exact bytes - so what is checked here is
    that ``load_shipped_grids`` actually asks for both.

    Seeding the defect is what put this test here: dropping ``expect_geometry``
    from the production path left the whole suite green, because every other
    geometry test passes the expectation itself.
    """
    calls: list[dict] = []
    real = vertcon.load_grid

    def recording(path, kind, expect_sha256=None, expect_geometry=None):
        calls.append(
            {
                "kind": kind,
                "sha256": expect_sha256,
                "geometry": expect_geometry,
                "path": path,
            }
        )
        return real(
            path,
            kind,
            expect_sha256=expect_sha256,
            expect_geometry=expect_geometry,
        )

    monkeypatch.setattr(vertcon, "load_grid", recording)
    vertcon.load_shipped_grids()

    assert len(calls) == 2

    transformation, uncertainty = calls
    assert transformation["kind"] is vertcon.TransformationGrid
    assert transformation["path"] == vertcon.VERTCON3_TRN_TILE
    assert transformation["sha256"] == vertcon.VERTCON3_TRN_SHA256
    assert transformation["geometry"] is vertcon.VERTCON3_CONUS_GEOMETRY

    assert uncertainty["kind"] is vertcon.UncertaintyGrid
    assert uncertainty["path"] == vertcon.VERTCON3_ERR_TILE
    assert uncertainty["sha256"] == vertcon.VERTCON3_ERR_SHA256
    assert uncertainty["geometry"] is vertcon.VERTCON3_CONUS_GEOMETRY


def test_the_cached_grids_come_through_the_authenticated_path(monkeypatch):
    """``default_grids`` must not be a second, laxer loader.

    Cleared and reloaded here so the cache cannot hide which path it took.
    """
    called: list[bool] = []
    real = vertcon.load_shipped_grids

    def recording(*args, **kwargs):
        called.append(True)
        return real(*args, **kwargs)

    monkeypatch.setattr(vertcon, "load_shipped_grids", recording)
    vertcon.default_grids.cache_clear()
    try:
        vertcon.default_grids()
        assert called == [True]
    finally:
        vertcon.default_grids.cache_clear()


def test_the_shipped_pair_is_loaded_once_per_process():
    """The same object, not an equal one: two loads would re-hash 4.8 MB per row."""
    assert vertcon.default_grids() is vertcon.default_grids()


# ==========================================================================
# THE INTERPOLATION ANCHORING. The pin this module exists for.
# ==========================================================================

# A position whose fractional indices are exact halves, so the two anchorings
# provably land on different stencils and the arithmetic can be done by hand.
#
# 42.875 N, 83.825 W is real ground in Michigan's South zone, between Ann Arbor
# and Brighton:
#
#     row = (42.875 - 24.0) / 0.05 = 18.875 / 0.05 = 377.5
#     col = (360 - 83.825 - 235.0) / 0.05 = 41.175 / 0.05 = 823.5
#
# floor anchoring       row0 = int(377.5) - 1       = 376, dr = 1.5
# nearest-node anchoring row0 = int(377.5 + 0.5) - 1 = 377, dr = 0.5
STENCIL_LATITUDE = 42.875
STENCIL_LONGITUDE = -83.825


def test_both_grids_are_read_by_the_nearest_node_anchored_biquadratic(trn, err):
    """The scheme, stated as a property of the module rather than of a lattice.

    Both accessors must be the nearest-node-anchored biquadratic, and must
    measurably not be either of the two variants that were plausible candidates.

    The uncertainty grid is exercised through ``modeled_error_raw_m`` rather than
    ``sigma_m`` because the interpolation is what is being pinned here, and at
    this position the interpolation comes out negative - so ``sigma_m`` correctly
    refuses. That refusal is asserted below, so this choice cannot quietly become
    a way of avoiding the check.
    """
    latitude, longitude = STENCIL_LATITUDE, STENCIL_LONGITUDE

    with pytest.raises(vertcon.VertconError, match="cannot be a one-sigma"):
        err.sigma_m(latitude, longitude)

    for grid, reading in ((trn, trn.shift_m), (err, err.modeled_error_raw_m)):
        assert reading(latitude, longitude) == (
            grid.interpolate_biquadratic_nearest_node(latitude, longitude)
        )
        assert reading(latitude, longitude) != grid.interpolate_biquadratic(
            latitude, longitude
        )
        assert reading(latitude, longitude) != grid.interpolate_bilinear(
            latitude, longitude
        )


def test_the_two_anchorings_choose_different_stencils_hand_derived(err):
    """Where the difference comes from, in one position and by hand.

    The two anchorings do not merely re-weight the same nine cells: they read
    NINE DIFFERENT CELLS. Floor anchoring takes rows 376-378 and columns 822-824;
    nearest-node takes rows 377-379 and columns 823-825. They overlap in four.

    The ``.err`` cells involved, read out of the shipped file, north at the top.
    The field falls steeply northward here, by two orders of magnitude across
    row 376 to row 378:

        row 379                             0.004238038  0.005114300  0.009665478
        row 378   0.004781750  0.002168453  0.003770013  0.015843086
        row 377   0.015405704  0.002830961  0.001872439  0.045489971
        row 376   0.057540737  0.121269755  0.247016445
        column        822          823          824          825

    FLOOR anchoring anchors at row 376, column 822 and evaluates at dr = dc = 1.5,
    so the target sits BEYOND the middle node. Lagrange weights at x = 1.5, from
    the basis in ``ngs_grid.lagrange3``:

        L0 = (1.5-1)(1.5-2)/2 = (0.5)(-0.5)/2 = -0.125
        L1 = 1.5 * (2 - 1.5)                  =  0.75
        L2 = 1.5 * (1.5-1)/2                  =  0.375      (sum 1.0)

    along each row, over columns 822, 823, 824:

        row 376: -0.125(0.057540737) + 0.75(0.121269755) + 0.375(0.247016445)
               = -0.007192592 + 0.090952316 + 0.092631167 =  0.176390891
        row 377: -0.125(0.015405704) + 0.75(0.002830961) + 0.375(0.001872439)
               = -0.001925713 + 0.002123221 + 0.000702165 =  0.000899673
        row 378: -0.125(0.004781750) + 0.75(0.002168453) + 0.375(0.003770013)
               = -0.000597719 + 0.001626340 + 0.001413755 =  0.002442376

    and down the column at dr = 1.5 with the same three weights, applied to rows
    376, 377, 378 in that order:

        -0.125(0.176390891) + 0.75(0.000899673) + 0.375(0.002442376)
      = -0.022048861 + 0.000674755 + 0.000915891 = -0.020458215

    NEAREST-NODE anchoring anchors at row 377, column 823 and evaluates at
    dr = dc = 0.5, so the target sits BETWEEN the first two nodes and the far one
    is subtracted rather than added:

        L0 = (0.5-1)(0.5-2)/2 = (-0.5)(-1.5)/2 =  0.375
        L1 = 0.5 * (2 - 0.5)                   =  0.75
        L2 = 0.5 * (0.5-1)/2                   = -0.125     (sum 1.0)

    along each row, over columns 823, 824, 825:

        row 377:  0.375(0.002830961) + 0.75(0.001872439) - 0.125(0.045489971)
               =  0.001061610 + 0.001404329 - 0.005686246 = -0.003220307
        row 378:  0.375(0.002168453) + 0.75(0.003770013) - 0.125(0.015843086)
               =  0.000813170 + 0.002827510 - 0.001980386 =  0.001660294
        row 379:  0.375(0.004238038) + 0.75(0.005114300) - 0.125(0.009665478)
               =  0.001589264 + 0.003835725 - 0.001208185 =  0.004216804

    and down the column at dr = 0.5:

         0.375(-0.003220307) + 0.75(0.001660294) - 0.125(0.004216804)
      = -0.001207615 + 0.001245221 - 0.000527101 = -0.000489495

    Forty-two times apart, at a position where the value is under a millimetre.
    Both derivations carry the rounding of the nine-decimal cell values quoted
    above, which is why they are held to 1e-8 rather than to the last bit.
    """
    latitude, longitude = STENCIL_LATITUDE, STENCIL_LONGITUDE

    floor_anchored = err.interpolate_biquadratic(latitude, longitude)
    nearest_node = err.interpolate_biquadratic_nearest_node(latitude, longitude)

    assert floor_anchored == pytest.approx(-0.020458215, abs=1e-8)
    assert nearest_node == pytest.approx(-0.000489495, abs=1e-8)
    assert abs(nearest_node - floor_anchored) > abs(nearest_node) * 40.0

    # The one that ships is the nearest-node one. Read through the raw accessor:
    # this position is one where the interpolant lands below zero, so ``sigma_m``
    # refuses it - which is the test above.
    assert err.modeled_error_raw_m(latitude, longitude) == nearest_node


@pytest.mark.anchor
def test_the_shipped_scheme_reproduces_every_ncat_figure_and_the_others_do_not(
    trn, err
):
    """The primary pin, exact and with no tolerance in it at all.

    NCAT prints to 0.001 m, so "does this reader reproduce NGS's own published
    figure" is a question with a yes-or-no answer: round the reading to three
    decimals and compare. Over the 20 frozen forward anchors:

        .trn  nearest-node biquadratic  20/20      floor-anchored 12/20
                                                   bilinear        6/20
        .err  nearest-node biquadratic  20/20      floor-anchored 14/20
                                                   bilinear       11/20

    A tolerance can be loosened until it stops discriminating - DESIGN.md
    amendment #31 is the record of a pin that did exactly that and kept passing.
    This one cannot be, because there is nothing in it to loosen.
    """

    def reproduced(read, truth) -> int:
        return sum(
            1
            for anchor in NGVD29_TO_NAVD88_ANCHORS
            if round(read(anchor.latitude, anchor.longitude), 3)
            == round(truth(anchor), 3)
        )

    shift = lambda anchor: anchor.shift_m  # noqa: E731
    sigma = lambda anchor: anchor.sigma_m  # noqa: E731

    assert reproduced(trn.shift_m, shift) == 20
    assert reproduced(err.sigma_m, sigma) == 20

    # Anti-vacuousness: the count must be able to come out below 20.
    assert reproduced(trn.interpolate_biquadratic, shift) == 12
    assert reproduced(trn.interpolate_bilinear, shift) == 6
    assert reproduced(err.interpolate_biquadratic, sigma) == 14
    assert reproduced(err.interpolate_bilinear, sigma) == 11


@pytest.mark.anchor
def test_the_wrong_anchoring_and_bilinear_both_fail_the_numeric_pin(trn, err):
    """The same discrimination against the 0.0005 m bound, with the measurements.

        .trn   nearest-node 0.4707 mm   floor 8.4573 mm   bilinear 17.7262 mm
        .err   nearest-node 0.4716 mm   floor 3.0416 mm   bilinear  4.5468 mm

    The margin against the nearest wrong scheme is a factor of six. That is what
    makes 0.0005 m a measurement rather than a round number chosen to pass
    (docs/PLAN-vertical-datums.md section 8, risk 8).
    """

    def worst(read, truth) -> float:
        return max(
            abs(read(a.latitude, a.longitude) - truth(a))
            for a in NGVD29_TO_NAVD88_ANCHORS
        )

    shift = lambda anchor: anchor.shift_m  # noqa: E731
    sigma = lambda anchor: anchor.sigma_m  # noqa: E731

    assert worst(trn.shift_m, shift) == pytest.approx(0.0004707, abs=1e-7)
    assert worst(err.sigma_m, sigma) == pytest.approx(0.0004716, abs=1e-7)
    assert worst(trn.shift_m, shift) < NCAT_QUANTIZATION_M
    assert worst(err.sigma_m, sigma) < NCAT_QUANTIZATION_M

    assert worst(trn.interpolate_biquadratic, shift) == pytest.approx(
        0.0084573, abs=1e-7
    )
    assert worst(trn.interpolate_bilinear, shift) == pytest.approx(0.0177262, abs=1e-7)
    assert worst(err.interpolate_biquadratic, sigma) == pytest.approx(
        0.0030416, abs=1e-7
    )
    assert worst(err.interpolate_bilinear, sigma) == pytest.approx(0.0045468, abs=1e-7)

    for wrong in (
        worst(trn.interpolate_biquadratic, shift),
        worst(trn.interpolate_bilinear, shift),
        worst(err.interpolate_biquadratic, sigma),
        worst(err.interpolate_bilinear, sigma),
    ):
        assert wrong > NCAT_QUANTIZATION_M * 6.0


def test_geoid18_keeps_the_other_anchoring():
    """The two NGS products differ, so neither anchoring may become a default.

    Measured against GEOID18's own frozen NGS geoid-API anchors, the anchoring
    that ships for the geoid is the better one there - 0.595 mm maximum against
    the nearest-node variant's 0.830, and 18 of 20 points inside NGS's 0.5 mm
    printing quantization against 17. GEOID18 is one arcminute over a smooth
    field where the choice barely registers; VERTCON is 0.05 degrees, three
    times coarser, over a rougher one where it is worth 8 mm.

    This test is why ``ngs_grid`` carries both variants rather than being
    "corrected" to one. Changing ``geoid18.geoid_height`` to match VERTCON would
    move a released, gated number (DESIGN.md amendment #8) in the wrong
    direction.
    """
    from tests.fixtures.geoid_anchors import GEOID_ANCHORS

    grid = geoid18.load_grid()

    shipped = [
        abs(grid.interpolate_biquadratic(a.latitude, a.longitude) - a.geoid_height_m)
        for a in GEOID_ANCHORS
    ]
    nearest_node = [
        abs(
            grid.interpolate_biquadratic_nearest_node(a.latitude, a.longitude)
            - a.geoid_height_m
        )
        for a in GEOID_ANCHORS
    ]

    assert max(shipped) == pytest.approx(0.000595, abs=1e-6)
    assert max(nearest_node) == pytest.approx(0.000830, abs=1e-6)
    assert max(shipped) < max(nearest_node)

    # And ``geoid_height`` must still be reading through the one it prefers, at
    # EVERY anchor. Checking one would be vacuous: the two anchorings coincide
    # wherever both fractional indices are below a half, which is about a
    # quarter of positions, and the first anchor is one of them. Seeding the
    # defect is what found that - the single-anchor version of this test passed
    # against ``geoid_height`` switched to nearest-node.
    distinguishing = 0
    for anchor in GEOID_ANCHORS:
        floor_anchored = grid.interpolate_biquadratic(anchor.latitude, anchor.longitude)
        other = grid.interpolate_biquadratic_nearest_node(
            anchor.latitude, anchor.longitude
        )
        assert (
            geoid18.geoid_height(anchor.latitude, anchor.longitude, grid)
            == floor_anchored
        )
        if other != floor_anchored:
            distinguishing += 1

    assert distinguishing >= 10, (
        "the anchors cannot tell the two anchorings apart, so the assertion "
        "above proves nothing"
    )

    # Recorded because it is a gap this test closes rather than one it found in
    # shipped code: tests/test_geoid.py holds the geoid anchors to 1 mm, and
    # nearest-node anchoring lands at 0.830 mm, so the geoid suite alone would
    # NOT notice geoid18 being re-anchored. This test is what would.
    assert max(nearest_node) < 0.001


# The two positions the WP-V4 review gate produced from its own sweep of
# Michigan at 0.01-degree spacing. That sweep is reproduced below rather than
# quoted: 41.6 to 48.4 N and 90.6 to 82.2 W inclusive is 681 x 841 = 572,721
# positions, and the grid this repository carries gives back the reviewer's
# 1,848 negatives and its worst value exactly.
#
# Every number in this section is reproduced from the committed grid by the test
# that states it. The single exception is NCAT's sigma at the second position,
# which is external and is labelled as such where it is used.
REVIEW_WORST_NEGATIVE = (42.87, -83.81)
REVIEW_NCAT_DISAGREEMENT = (42.475, -83.125)


def test_the_modeled_uncertainty_can_come_out_negative_and_is_not_clamped(err):
    """A real property of the published model, recorded rather than hidden.

    The stored cells are non-negative - the smallest in the whole CONUS grid is
    exactly 0.0 - but a Lagrange quadratic is not monotone within its cell, so
    where the field is steep the interpolant undershoots past zero. Swept over
    Michigan at the grid's own 0.05-degree spacing, offset half a cell so every
    sample is a cell centre: 114 of 22,848 positions come out negative, worst
    -0.009652 m at 42.475 N, 83.125 W. That sweep is this test, run against the
    committed grid, not a figure carried over from somewhere else.

    **NCAT does NOT return these negatives.** Asked directly at that point, NCAT
    returns +0.011 m where this reader gives -0.00965 m - a 20.7 mm
    disagreement. So at these positions this reader is wrong, and the earlier
    claim that "NCAT must produce the same negatives because we agree to
    0.472 mm" was an inference that measurement refuted.

    What the reader does about it is ``sigma_m``'s business and is pinned below:
    the raw interpolation stays available and unclamped, and the value is not
    handed out as an uncertainty.
    """
    assert min(err.values) == 0.0

    negative = 0
    samples = 0
    worst = 0.0
    worst_at = None

    # Integer cell indices, so no floating-point drift accumulates across the
    # sweep and the counts below are reproducible exactly.
    first_row = round((41.6 - err.south_latitude) / err.latitude_spacing)
    last_row = round((48.4 - err.south_latitude) / err.latitude_spacing)
    first_column = round(
        (360.0 - 90.6 - err.west_longitude) / err.longitude_spacing
    )
    last_column = round((360.0 - 82.2 - err.west_longitude) / err.longitude_spacing)

    for row in range(first_row, last_row):
        latitude = err.south_latitude + (row + 0.5) * err.latitude_spacing
        for column in range(first_column, last_column):
            longitude = (
                err.west_longitude + (column + 0.5) * err.longitude_spacing - 360.0
            )
            samples += 1
            value = err.modeled_error_raw_m(latitude, longitude)
            if value < 0.0:
                negative += 1
                if value < worst:
                    worst = value
                    worst_at = (round(latitude, 4), round(longitude, 4))

    assert samples == 22848
    assert negative == 114
    assert worst == pytest.approx(-0.009652, abs=1e-6)
    assert worst_at == REVIEW_NCAT_DISAGREEMENT

    # Not clamped, not floored, not replaced, not made positive.
    assert err.modeled_error_raw_m(42.475, -83.125) < 0.0


def test_the_review_gates_own_sweep_reproduces_from_the_committed_grid(err):
    """The reviewer's independent measurement, made checkable rather than quoted.

    Michigan at 0.01-degree spacing, 41.6 to 48.4 N by 90.6 to 82.2 W inclusive:

        681 latitudes  x  841 longitudes  =  572,721 positions

    Hand check of the counts: (48.4 - 41.6) / 0.01 = 680 steps, so 681 samples;
    (90.6 - 82.2) / 0.01 = 840 steps, so 841. The reviewer found 1,848 negatives
    there, worst -0.028879586 m at 42.87 N, 83.81 W, and that is what the grid
    this repository carries gives back.

    This exists because the suite previously cited external experiments - a
    40-point discrimination run and a 223,850-position sweep - whose coordinates
    and responses were never committed, so the claims could not be checked or
    regression-tested (WP-V4 review, MEDIUM 2). Those citations are gone. This
    one takes about 1.2 seconds and replaces a paragraph of assertion with a
    measurement.
    """
    negative = 0
    samples = 0
    worst = 0.0
    worst_at = None

    for i in range(681):
        latitude = 41.6 + i * 0.01
        for j in range(841):
            longitude = -90.6 + j * 0.01
            samples += 1
            value = err.modeled_error_raw_m(latitude, longitude)
            if value < 0.0:
                negative += 1
                if value < worst:
                    worst = value
                    worst_at = (round(latitude, 4), round(longitude, 4))

    assert samples == 572721
    assert negative == 1848
    assert worst == pytest.approx(-0.028879586, abs=1e-9)
    assert worst_at == REVIEW_WORST_NEGATIVE


def test_the_raw_error_reading_is_the_reviewers_own_figure_at_both_positions(err):
    """The WP-V4 review gate's two counterexamples, reproduced to the last digit.

    The two that matter out of the 1,848 the sweep above finds:

        42.87 N, 83.81 W    -0.028879586 m   the worst it found
        42.475 N, 83.125 W  -0.009651646 m   where NCAT returns +0.011 m
    """
    assert err.modeled_error_raw_m(*REVIEW_WORST_NEGATIVE) == pytest.approx(
        -0.028879586, abs=1e-9
    )
    assert err.modeled_error_raw_m(*REVIEW_NCAT_DISAGREEMENT) == pytest.approx(
        -0.009651646, abs=1e-9
    )


def test_the_three_schemes_diverge_at_the_reviewers_position(err):
    """The scheme separation, checkable offline, at 42.87 N / 83.81 W.

    The suite's discrimination between the three candidate interpolations rested
    on the 20 frozen NCAT anchors and on a 40-point external experiment that the
    repository does not hold - so that second claim could not be checked or
    regression-tested and has been removed from every docstring that made it
    (WP-V4 review, MEDIUM 2). This is the part of it that CAN be committed: at
    the reviewer's own uncovered position the three schemes give three different
    answers, and the differences are large enough that no rounding could unify
    them.

        nearest-node biquadratic   -0.028879586 m   what ships
        floor-anchored biquadratic -0.024203909 m
        bilinear                   +0.002618367 m

    It does not say which is right - the NCAT anchors say that. It says the
    schemes are distinguishable here, so a future edit that silently swapped one
    for another cannot pass unnoticed even at a position no anchor covers.
    """
    latitude, longitude = REVIEW_WORST_NEGATIVE

    nearest_node = err.modeled_error_raw_m(latitude, longitude)
    floor_anchored = err.interpolate_biquadratic(latitude, longitude)
    bilinear = err.interpolate_bilinear(latitude, longitude)

    assert nearest_node == pytest.approx(-0.028879586, abs=1e-9)
    assert floor_anchored == pytest.approx(-0.024203909, abs=1e-9)
    assert bilinear == pytest.approx(0.002618367, abs=1e-9)

    # Three distinct values, not three names for one. The closest pair differ by
    # 4.7 mm, an order of magnitude above the 0.5 mm NCAT quantization the anchor
    # pins are held to.
    assert abs(nearest_node - floor_anchored) > 0.004
    assert abs(floor_anchored - bilinear) > 0.026
    assert abs(nearest_node - bilinear) > 0.031

    # And bilinear does not go negative here, which is the property plan section
    # 2.5 had hold of and the reason it is worth saying that the choice between
    # them is settled by the NCAT lattice rather than by this position.
    assert bilinear > 0.0


def test_a_negative_reading_refuses_as_a_sigma_and_says_the_shift_still_stands(err):
    """The HIGH finding's pin: a negative is not returned through ``sigma_m``.

    Not clamping was right - a zero would be a fabricated reading, and this
    module's whole first requirement is that it never fabricates one - but
    returning a negative from a method named ``sigma_m`` is equally indefensible,
    because it puts a number that cannot be an uncertainty exactly where a user
    reads one (WP-V4 review, HIGH 1).

    The message has one clause that is not decoration: a caller reading a refusal
    about a point must not conclude the elevation is bad. It is not. The shift
    comes from the other grid and is untouched.
    """
    for latitude, longitude in (REVIEW_WORST_NEGATIVE, REVIEW_NCAT_DISAGREEMENT):
        raw = err.modeled_error_raw_m(latitude, longitude)
        assert raw < 0.0

        with pytest.raises(vertcon.VertconError) as caught:
            err.sigma_m(latitude, longitude)

        message = str(caught.value)
        assert f"{latitude:.6f}, {longitude:.6f}" in message
        assert repr(raw) in message
        assert "cannot be a one-sigma uncertainty" in message
        assert "THE SHIFT ITSELF IS STILL VALID AND UNAFFECTED" in message
        assert "clamped to zero" in message


def test_sigma_m_returns_the_reading_wherever_it_is_a_quantity(err):
    """Anti-vacuousness: the refusal must not have become a refusal of everything.

    43.0 N / 84.5 W is the amendment #22 anchor; 43.05 N / 86.20 W is the
    disclosure position where sigma is 255% of the shift (DESIGN.md #36; plan
    section 2.8's 249% used a shift figure corrected at the WP-V4 gate). Both are
    ordinary positive readings and must come straight through, identical to the
    raw one.
    """
    for latitude, longitude in ((43.0, -84.5), (43.05, -86.20)):
        assert err.sigma_m(latitude, longitude) == err.modeled_error_raw_m(
            latitude, longitude
        )
        assert err.sigma_m(latitude, longitude) > 0.0


def test_exactly_zero_is_a_reading_and_not_a_refusal():
    """The boundary, and why it falls where it does.

    The smallest cell stored in the shipped uncertainty grid is exactly 0.0, so a
    zero is something the published model genuinely produces - not a symptom of
    the interpolation leaving its range. Refusing it would refuse a real reading,
    which is the mirror image of the defect being fixed.
    """
    assert vertcon.sigma_is_physical(0.0)
    assert vertcon.sigma_is_physical(1e-9)
    assert not vertcon.sigma_is_physical(-1e-12)


def test_a_negative_sigma_does_not_cost_the_point_its_shift(grids):
    """``reading_at`` is not collateral damage: the shift survives the refusal.

    The shape is ``job.py``'s for a missing geoid height - the number is absent
    and the caller says why, rather than the point being discarded or a value
    invented. Here the shift is a real reading from the transformation grid and
    is completely independent of the uncertainty grid beside it.
    """
    for latitude, longitude in (REVIEW_WORST_NEGATIVE, REVIEW_NCAT_DISAGREEMENT):
        shift, sigma = grids.reading_at(latitude, longitude)

        assert sigma is None
        assert shift == grids.transformation.shift_m(latitude, longitude)
        assert shift < 0.0

    # 42.87 N, 83.81 W in full, so the surviving shift is a number and not just
    # "whatever the grid says".
    shift, sigma = grids.reading_at(*REVIEW_WORST_NEGATIVE)
    assert shift == pytest.approx(-0.119270416, abs=1e-9)
    assert sigma is None

    # And where the sigma is a quantity it is still returned, so the None above
    # is discriminating rather than universal.
    shift, sigma = grids.reading_at(43.05, -86.20)
    assert sigma == pytest.approx(0.3656, abs=0.001)


def test_the_front_door_reports_the_same_unavailability(grids):
    """``shift_and_sigma_m`` must not be a second, laxer path to the same pair."""
    assert vertcon.shift_and_sigma_m(*REVIEW_WORST_NEGATIVE) == grids.reading_at(
        *REVIEW_WORST_NEGATIVE
    )
    assert vertcon.shift_and_sigma_m(*REVIEW_WORST_NEGATIVE)[1] is None


def test_one_rule_decides_the_refusal_and_the_unavailability(grids, err):
    """The two paths cannot disagree about the same position.

    ``sigma_m`` raises and ``reading_at`` reports None, and if those decisions
    came from two separately written comparisons a position could be refused by
    one and reported by the other. Both ask ``sigma_is_physical``. Swept over the
    same Michigan cell centres as the sweep above, this checks the two agree at
    every one of them.
    """
    first_row = round((41.6 - err.south_latitude) / err.latitude_spacing)
    last_row = round((48.4 - err.south_latitude) / err.latitude_spacing)
    first_column = round(
        (360.0 - 90.6 - err.west_longitude) / err.longitude_spacing
    )
    last_column = round((360.0 - 82.2 - err.west_longitude) / err.longitude_spacing)

    disagreements = 0
    refused = 0
    for row in range(first_row, last_row):
        latitude = err.south_latitude + (row + 0.5) * err.latitude_spacing
        for column in range(first_column, last_column):
            longitude = (
                err.west_longitude + (column + 0.5) * err.longitude_spacing - 360.0
            )
            _, sigma = grids.reading_at(latitude, longitude)
            try:
                err.sigma_m(latitude, longitude)
            except vertcon.VertconError:
                refused += 1
                if sigma is not None:
                    disagreements += 1
            else:
                if sigma is None:
                    disagreements += 1

    assert disagreements == 0
    # Anti-vacuousness: the sweep must contain positions of both kinds.
    assert refused == 114


def test_the_pair_offers_no_way_to_take_half_a_reading(grids):
    """The LOW finding's structural pin (WP-V4 review, LOW 1).

    The pair used to carry ``shift_m`` and ``sigma_m`` as separate public
    methods, so a caller could take a shift at one position and a sigma at
    another through the pair itself - the reviewer's counterexample paired
    -0.143529 m at 43.05 N / 86.20 W with 0.000655 m at 43.00 N / 84.50 W, where
    the true figure is 0.365599 m: the uncertainty understated by 0.365 m with
    both numbers looking ordinary.

    Those two numbers are still readable, because reading one grid alone is
    legitimate - but only through ``.transformation`` and ``.uncertainty``, where
    the expression says which grid it came from and nothing suggests they are a
    pair. What is gone is the accessor that made the mistake look like using the
    pair correctly.
    """
    assert not hasattr(grids, "shift_m")
    assert not hasattr(grids, "sigma_m")
    assert not hasattr(grids, "modeled_error_raw_m")

    # The counterexample's ingredients, so this test fails if they stop being the
    # numbers that made it dangerous rather than merely if a name reappears.
    assert grids.transformation.shift_m(43.05, -86.20) == pytest.approx(
        -0.143529, abs=1e-6
    )
    assert grids.uncertainty.sigma_m(43.00, -84.50) == pytest.approx(
        0.000655, abs=1e-6
    )
    assert grids.uncertainty.sigma_m(43.05, -86.20) == pytest.approx(
        0.365599, abs=1e-6
    )

    # And the front door still hands both halves of ONE position over together.
    shift, sigma = grids.reading_at(43.05, -86.20)
    assert shift == pytest.approx(-0.143529, abs=1e-6)
    assert sigma == pytest.approx(0.365599, abs=1e-6)


# ==========================================================================
# NCAT anchors. Tolerances are PLACEHOLDERS; see the constant at the top.
# ==========================================================================


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", NGVD29_TO_NAVD88_ANCHORS, ids=FORWARD_IDS)
def test_the_shift_matches_ncat(anchor, trn):
    """The grid stores NAVD88 - NGVD29, so the shift is NCAT's own difference.

    Every anchor was requested at 200.000 m, which is what makes each expected
    value readable by hand off the fixture: the shift is
    ``target_height_m - 200.000``.
    """
    assert trn.shift_m(anchor.latitude, anchor.longitude) == pytest.approx(
        anchor.shift_m, abs=NCAT_QUANTIZATION_M
    )


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", NGVD29_TO_NAVD88_ANCHORS, ids=FORWARD_IDS)
def test_the_sigma_matches_ncat(anchor, err):
    """NCAT's ``sigOrthoht``, which comes from this same companion grid."""
    assert err.sigma_m(anchor.latitude, anchor.longitude) == pytest.approx(
        anchor.sigma_m, abs=NCAT_QUANTIZATION_M
    )


@pytest.mark.anchor
def test_the_design_22_anchor_fixes_the_sign(trn):
    """43.0 N, 84.5 W: 200.000 m NGVD 29 becomes 199.860 m NAVD 88.

    Hand derivation of NCAT's shift: 199.860 - 200.000 = -0.140 m. The grid reads
    -0.140196 m there, 0.2 mm away, and NCAT prints only to the millimetre
    (docs/PLAN-vertical-datums.md section 2.3).

    This is the single value that fixes ``sign = +1`` in ``spc/vertical.py``, and
    the sign/direction defect class this project was already burned by
    (DESIGN.md amendment #1, MATLAB defect 2). A reader with the sign backwards
    would report +0.140 here and it would look like an ordinary elevation
    difference.
    """
    anchor = next(a for a in NGVD29_TO_NAVD88_ANCHORS if a.name == "anchor-22")
    assert anchor.target_height_m == 199.860
    assert anchor.shift_m == pytest.approx(-0.140, abs=1e-12)

    shift = trn.shift_m(43.0, -84.5)
    assert shift < 0.0
    assert shift == pytest.approx(-0.140196, abs=1e-6)
    assert abs(shift - anchor.shift_m) < 0.0005


@pytest.mark.anchor
@pytest.mark.parametrize("anchor", NAVD88_TO_NGVD29_ANCHORS, ids=INVERSE_IDS)
def test_the_inverse_is_this_same_grid_sign_reversed(anchor, trn):
    """One grid, one data path, two directions (plan section 2.4).

    ``spc/vertical.py`` carries the reverse record as the same ``grid_key`` at
    sign -1, so the value this reader returns, negated, must reproduce NCAT's
    inverse transformation. At 43.0 N, 84.5 W NCAT returns 200.140 m, a shift of
    +0.140 m, against the forward -0.140.
    """
    reading = trn.shift_m(anchor.latitude, anchor.longitude)
    assert -reading == pytest.approx(
        anchor.shift_m, abs=NCAT_QUANTIZATION_M
    )


@pytest.mark.anchor
def test_the_forward_and_inverse_anchors_sum_to_zero():
    """NCAT's own figures, before this reader is involved at all.

    Plan section 2.4's table, reproduced by the frozen lattice: every point's
    forward and inverse shifts are equal and opposite to the last printed digit.
    That is what says the inverse is not a second published product.
    """
    forward = {a.name: a for a in NGVD29_TO_NAVD88_ANCHORS}
    for inverse in NAVD88_TO_NGVD29_ANCHORS:
        pair = forward[inverse.name]
        assert pair.shift_m + inverse.shift_m == pytest.approx(0.0, abs=1e-9)


@pytest.mark.anchor
def test_the_uncertainty_can_exceed_the_shift_it_qualifies(grids):
    """43.05 N, 86.20 W - the disclosure fact that decided plan section 5.

    NCAT reports sigma 0.366 m there against a shift of -0.144 m: the uncertainty
    is about 2.5 times the shift itself. A job-level constant would have hidden
    that while the shift beside it was printed to the millimetre (plan section
    2.8). This is why the pair is loaded as a pair.
    """
    shift, sigma = grids.reading_at(43.05, -86.20)

    assert sigma == pytest.approx(0.3656, abs=0.001)
    assert shift == pytest.approx(-0.1435, abs=0.001)
    assert sigma > abs(shift) * 2.0


@pytest.mark.anchor
def test_the_shift_changes_sign_inside_michigan(trn):
    """Which is why 0.0 is a legitimate reading, and why this reader may not invent one.

    From the frozen lattice: Monroe on the Ohio line is -0.396 m and Sault Ste.
    Marie in the eastern Upper Peninsula is +0.040 m. A continuous field that is
    negative at one Michigan point and positive at another passes through zero
    somewhere between them, so a 0.0 out of this reader is indistinguishable
    from a real reading - the reviewer's note that requirement 6 of this work
    package records.
    """
    monroe = trn.shift_m(41.7583, -83.6417)
    sault = trn.shift_m(46.4936, -84.3453)

    assert monroe < 0.0
    assert sault > 0.0
    assert min(trn.values) < 0.0 < max(trn.values)


# ==========================================================================
# A reading is never invented.
# ==========================================================================


def test_signed_shift_accepts_zero_so_a_fabricated_zero_would_be_invisible():
    """The core's contract, quoted here because it is what forces requirement 6.

    ``spc.vertical.signed_shift`` refuses ``None`` and refuses a non-finite
    value, and it accepts 0.0 without complaint - correctly, since the grid
    genuinely crosses zero. So there is no downstream check that could catch a
    zero this reader made up.
    """
    transformation = vertical.require_vertical_pair(vertical.NGVD29, vertical.NAVD88)

    assert (
        vertical.signed_shift(grid_value_m=0.0, transformation=transformation) == 0.0
    )

    with pytest.raises(ValueError):
        vertical.signed_shift(grid_value_m=None, transformation=transformation)
    with pytest.raises(ValueError):
        vertical.signed_shift(
            grid_value_m=float("nan"), transformation=transformation
        )


def test_no_malformed_file_yields_a_grid_of_zeros(tmp_path):
    """Every structural failure raises. None returns a readable grid.

    The battery is one entry per refusal this module implements at load time, so
    a future edit that added a fallback to any of them would have to defeat this
    test to land.
    """
    zeros = (0.0,) * 9
    cases = {
        "bad header marker": {"header_open": 0},
        "bad closing header marker": {"header_close": 0},
        "bad row marker": {"row_open": {2: 0}},
        "unsupported ikind": {"ikind": 2},
        "zero spacing": {"dlat": 0.0},
        "too few rows": {"rows": 2, "columns": 2, "values": (0.0,) * 4},
        "trailing bytes": {"tail": b"\x00\x00\x00\x00"},
        "non-finite cell": {"values": zeros[:4] + (float("nan"),) + zeros[5:]},
    }

    for name, overrides in cases.items():
        path = _tiny(tmp_path, f"{name.replace(' ', '_')}.b", **overrides)
        with pytest.raises(vertcon.VertconError):
            vertcon.load_grid(path, vertcon.TransformationGrid)


def test_an_all_zero_grid_passes_every_structural_check_and_the_checksum_stops_it(
    tmp_path,
):
    """The sharpest form of requirement 6, and the reason the checksum is not optional.

    A copy of the real transformation grid with every cell set to 0.0 is
    structurally perfect: correct length, correct markers on the header and all
    521 rows, correct geometry, and every cell finite. Nothing about its shape is
    wrong. It would report a zero shift for every point in Michigan - an
    unconverted height, labelled as converted.

    Only the SHA-256 catches it, which is why ``load_shipped_grids`` and
    ``default_grids`` pass one and why ``load_grid`` on its own is not the
    production path.
    """
    raw = bytearray(vertcon.VERTCON3_TRN_TILE.read_bytes())
    offset = 52
    for _ in range(521):
        offset += 4
        struct.pack_into("<1181f", raw, offset, *([0.0] * 1181))
        offset += 1181 * 4 + 4
    assert offset == len(raw)

    zeroed = tmp_path / "zeroed.b"
    zeroed.write_bytes(bytes(raw))

    # Structurally indistinguishable from the real thing.
    grid = vertcon.load_grid(
        zeroed,
        vertcon.TransformationGrid,
        expect_geometry=vertcon.VERTCON3_CONUS_GEOMETRY,
    )
    assert grid.shift_m(43.0, -84.5) == 0.0

    # The production path refuses it.
    with pytest.raises(vertcon.VertconError, match="expected SHA-256"):
        vertcon.load_shipped_grids(transformation_path=zeroed)


def test_every_except_clause_in_the_module_raises(tmp_path):
    """Structural pin: no failure may be swallowed into a value.

    Read out of the AST rather than the text, so a comment cannot satisfy it.
    Today there is exactly one handler in the module - the ``OSError`` around
    ``read_bytes`` - and it re-raises as a ``VertconError``.
    """
    tree = ast.parse(Path(vertcon.__file__).read_text(encoding="utf-8"))
    handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]

    assert handlers, "no except handlers found - the scanner is vacuous"
    for handler in handlers:
        assert any(
            isinstance(node, ast.Raise) for node in ast.walk(handler)
        ), "an except clause in vertcon.py does not raise; a swallowed failure "
        "here would become a fabricated grid value"


def test_the_module_defines_no_fallback_value_for_a_cell(tmp_path):
    """Anti-vacuousness for the rule above, stated behaviourally.

    Reading a grid whose file was deleted between the checks must raise rather
    than return anything at all.
    """
    path = _tiny(tmp_path)
    path.unlink()

    with pytest.raises(vertcon.VertconError):
        vertcon.load_grid(path, vertcon.TransformationGrid)


# ==========================================================================
# The dialect seam, and what the file layer must agree with the core about.
# ==========================================================================


def test_both_dialects_carry_the_class_this_modules_callers_catch():
    """``job.py`` will catch ``VertconError`` by name, as it catches ``GeoidError``.

    A refusal raised inside ``ngs_grid`` therefore has to BE that class, not a
    base of it and not a sibling. That is what the dialect's ``error`` field is
    for (``ngs_grid``'s module docstring).
    """
    assert vertcon.TransformationGrid.dialect.error is vertcon.VertconError
    assert vertcon.UncertaintyGrid.dialect.error is vertcon.VertconError
    assert not issubclass(vertcon.VertconError, geoid18.GeoidError)
    assert not issubclass(geoid18.GeoidError, vertcon.VertconError)


def test_the_two_dialects_speak_of_two_different_quantities():
    """One file holds shifts and the other holds uncertainties, and a refusal
    about a cell must say which."""
    transformation = vertcon.TransformationGrid.dialect
    uncertainty = vertcon.UncertaintyGrid.dialect

    assert transformation.value_noun == "vertical shift"
    assert uncertainty.value_noun == "shift uncertainty"
    assert transformation.grid_noun != uncertainty.grid_noun
    assert transformation.model_name == uncertainty.model_name == "VERTCON 3.0"


def test_no_vertcon_refusal_speaks_of_geoid_heights(tmp_path):
    """The substrate is shared; the words must not be.

    Driven through the paths that produce a substrate refusal, so this measures
    the messages a user would actually see rather than the dialect record.

    The IKIND refusal is included and is deliberately NOT required to name
    VERTCON: ``ngs_grid.require_supported_ikind`` takes no noun from the dialect
    at all, so its message names only the path and the byte order. That is the
    substrate keeping its own rule
    (``test_no_refusal_message_names_a_model``), not an omission here - and it
    still must not speak of geoid heights.
    """
    messages: list[str] = []

    with pytest.raises(vertcon.VertconError) as caught:
        _load_tiny(tmp_path, ikind=2)
    ikind_message = str(caught.value)
    messages.append(ikind_message)

    with pytest.raises(vertcon.VertconError) as caught:
        _load_tiny(tmp_path, "spacing.b", dlat=0.0)
    messages.append(str(caught.value))

    with pytest.raises(vertcon.VertconError) as caught:
        vertcon.load_grid(
            _tiny(tmp_path, "geom.b"),
            vertcon.TransformationGrid,
            expect_geometry=vertcon.VERTCON3_CONUS_GEOMETRY,
        )
    messages.append(str(caught.value))

    for message in messages:
        assert "geoid" not in message.lower()
        assert "GEOID18" not in message

    # Every message whose wording comes from the dialect names the model.
    dialect_worded = [m for m in messages if m is not ikind_message]
    assert len(dialect_worded) == 2
    for message in dialect_worded:
        assert "VERTCON" in message

    assert "IKIND=2" in ikind_message
    assert "VERTCON" not in ikind_message


def test_the_file_layer_and_the_core_agree_on_the_model_and_release():
    """Two modules name the same NGS product; they must spell it the same way.

    ``spc/vertical.py`` writes the model and release into the job record's
    direction statement, and this module writes them into refusals. One
    authoritative value would be better; since the core may not import the file
    layer and the file layer must not depend on the core to name a file, this
    test is what keeps the two literals from drifting.
    """
    transformation = vertical.require_vertical_pair(vertical.NGVD29, vertical.NAVD88)

    assert transformation.model == vertcon.VERTCON_MODEL_NAME == "VERTCON 3.0"
    assert transformation.release == vertcon.VERTCON_RELEASE == "20190601"


def test_the_cores_grid_key_names_the_files_this_module_ships():
    """``grid_key`` is the NGS build directory, and the file layer resolves it.

    ``spc/vertical.py`` deliberately carries no file path - it names the build,
    ``ngvd29.navd88.conus``, and leaves resolving it here. This is the link that
    makes that indirection safe rather than decorative.
    """
    transformation = vertical.require_vertical_pair(vertical.NGVD29, vertical.NAVD88)
    inverse = vertical.require_vertical_pair(vertical.NAVD88, vertical.NGVD29)

    assert transformation.grid_key == inverse.grid_key == "ngvd29.navd88.conus"
    assert transformation.grid_key in vertcon.VERTCON3_TRN_FILENAME
    assert transformation.grid_key in vertcon.VERTCON3_ERR_FILENAME
    assert vertcon.VERTCON_RELEASE in vertcon.VERTCON3_TRN_FILENAME


def test_the_shipped_filenames_are_ngss_own():
    """Committed unmodified and under NGS's own names, so each stays
    byte-comparable against its source (DESIGN.md section 3, plan section 2.1)."""
    assert (
        vertcon.VERTCON3_TRN_FILENAME
        == "vertcon_3.0_20190601.ngvd29.navd88.conus.oht.trn.b"
    )
    assert (
        vertcon.VERTCON3_ERR_FILENAME
        == "vertcon_3.0_20190601.ngvd29.navd88.conus.oht.err.b"
    )
    assert vertcon.VERTCON3_TRN_TILE.name == vertcon.VERTCON3_TRN_FILENAME
    assert vertcon.VERTCON3_ERR_TILE.name == vertcon.VERTCON3_ERR_FILENAME


# ==========================================================================
# Record shape.
# ==========================================================================


def test_the_loaded_grids_have_the_substrates_record_shape():
    """No extra field: the constructor stays the eight things a reader parses.

    The interpolation scheme in particular is NOT a field - it is a property of
    which class the grid is, so two grids of the same kind cannot disagree about
    how they are read.
    """
    expected = [f.name for f in dataclasses.fields(ngs_grid.Grid)]
    assert [f.name for f in dataclasses.fields(vertcon.TransformationGrid)] == expected
    assert [f.name for f in dataclasses.fields(vertcon.UncertaintyGrid)] == expected
    assert "dialect" not in expected
    assert "scheme" not in expected


def test_a_loaded_grid_is_frozen(tmp_path):
    """Core records are immutable (DESIGN.md section 4)."""
    grid = _load_tiny(tmp_path)
    with pytest.raises(dataclasses.FrozenInstanceError):
        grid.south_latitude = 0.0  # type: ignore[misc]


def test_the_pair_is_frozen(tmp_path):
    pair = vertcon.VertconGridPair(
        transformation=vertcon.load_grid(
            _tiny(tmp_path, "p.b"), vertcon.TransformationGrid
        ),
        uncertainty=vertcon.load_grid(
            _tiny(tmp_path, "q.b"), vertcon.UncertaintyGrid
        ),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        pair.transformation = None  # type: ignore[misc]
