"""Probe 1: attack parse_typed_point's quoting and number acceptance."""
import sys
sys.path.insert(0, r"C:\claude-projects\coord-convert")

from michspc.fileio import pnezd

CASES = [
    ("plain", "780000.000", "13123359.580", "800.00"),
    ("grouped-northing", "780,000.000", "13,123,359.580", "800.00"),
    ("embedded-quote", '780000"', "1", "2"),
    ("quote-pair", '"780000"', "13123359.580", "800.00"),
    ("csv-structure", '1","2","3', "13123359.580", "800.00"),
    ("newline", "780000\n13123359", "1", "2"),
    ("newline-quoted-break", '5"\n"6', "1", "2"),
    ("tab", "780000\t000", "13123359.580", "800.00"),
    ("underscore-pep515", "780_000.000", "13123359.580", "800.00"),
    ("unicode-digits", "\u0667\u0668\u0660\u0660\u0660\u0660", "13123359.580", "800.00"),
    ("unicode-minus", "\u221284.5555", "42.7325", "800.00"),
    ("nbsp", "\u00a0780000.000", "13123359.580", "800.00"),
    ("empty-first", "", "13123359.580", "800.00"),
    ("whitespace-first", "   ", "13123359.580", "800.00"),
    ("nan", "nan", "13123359.580", "800.00"),
    ("inf", "inf", "13123359.580", "800.00"),
    ("bom-first", "\ufeff780000.000", "13123359.580", "800.00"),
    ("backslash", "780000\\.000", "1", "2"),
    ("long", "7" * 400, "1", "2"),
    ("plus", "+780000.000", "13123359.580", "800.00"),
    ("sci", "7.8e5", "13123359.580", "800.00"),
    ("elev-blank", "780000.000", "13123359.580", ""),
    ("elev-dash", "780000.000", "13123359.580", "-"),
    ("elev-zero", "780000.000", "13123359.580", "0.00"),
    ("elev-grouped", "780000.000", "13123359.580", "1,800.00"),
    ("elev-none-word", "780000.000", "13123359.580", "NONE"),
    ("bad-grouping", "1,2", "13123359.580", "800.00"),
    ("trailing-comma-field", "780000.000,", "13123359.580", "800.00"),
    ("leading-zeros", "0780000.000", "13123359.580", "800.00"),
]

for name, a, b, c in CASES:
    try:
        pf = pnezd.parse_typed_point(a, b, c, source=pnezd.TYPED_POINT_SOURCE_GRID)
        r = pf.rows[0]
        print(f"OK   {name:24} id={r.point_id!r} N={r.northing!r} E={r.easting!r} "
              f"Z={r.elevation!r} desc={r.description!r} zero={r.elevation_was_zero}")
    except Exception as e:
        first = str(e).splitlines()[0] if str(e) else repr(e)
        print(f"REF  {name:24} {type(e).__name__}: {first[:150]}")
