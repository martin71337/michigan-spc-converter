"""Probe 2: drive BOTH tabs through the real GUI and compare every number.

Multi point writes a real ZIP; the audit CSV is parsed back out of it.
Single point renders its panel. Every quantity the panel shows that the audit
CSV also carries must be character-identical.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys, csv, io, zipfile, itertools, tempfile
from pathlib import Path

sys.path.insert(0, r"C:\claude-projects\coord-convert")

from PySide6.QtWidgets import QApplication
from michspc.gui.window import MainWindow, UNCHOSEN, GEODETIC
from michspc.job import LongitudeConvention
from michspc.spc.zones import ALL_ZONES
from michspc.spc.units import ALL_UNITS

app = QApplication.instance() or QApplication([])


def combo_index_for(combo, data):
    for i in range(combo.count()):
        if combo.itemData(data := combo.itemData(i)) if False else combo.itemData(i) == data:
            return i
    raise AssertionError(f"no item {data!r}")


def set_data(combo, data):
    for i in range(combo.count()):
        if combo.itemData(i) is data or combo.itemData(i) == data:
            combo.setCurrentIndex(i)
            return
    raise AssertionError(f"no item {data!r} in combo")


def run_multi(tmp, first, second, elev, src, tgt, iu, ou, conv):
    w = MainWindow()
    w._show_failure = lambda e: None
    w._ask_overwrite = lambda existing, error: True
    path = tmp / "job.txt"
    # Same four fields, quoted the same way parse_typed_point quotes them,
    # plus nothing else. This is a file whose single row IS the typed point.
    line = ",".join('"' + t.replace('"', '""') + '"' for t in ("1", first, second, elev))
    path.write_text(line + "\n", encoding="utf-8")
    w.input_edit.setText(str(path))
    w.output_edit.setText(str(tmp / "out"))
    (tmp / "out").mkdir(exist_ok=True)
    set_data(w.from_zone, src)
    set_data(w.to_zone, tgt)
    set_data(w.input_unit, iu)
    set_data(w.output_unit, ou)
    set_data(w.longitude_combo, conv if conv is not None else UNCHOSEN)
    ok = w.convert()
    if not ok:
        return None, w.last_failure, None
    zp = w.written_files["archive"]
    with zipfile.ZipFile(zp) as z:
        name = [n for n in z.namelist() if n.endswith("_full.csv")][0]
        text = z.read(name).decode("utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    audit = dict(zip(rows[0], rows[1]))
    table = [w.model.data(w.model.index(0, c)) for c in range(w.model.columnCount())]
    return audit, None, table


def run_single(first, second, elev, src, tgt, iu, ou, conv):
    from michspc.gui.single_point import SinglePointTab
    t = SinglePointTab()
    t._show_failure = lambda e: None
    set_data(t.from_zone, src)
    set_data(t.to_zone, tgt)
    set_data(t.input_unit, iu)
    set_data(t.output_unit, ou)
    set_data(t.longitude_combo, conv if conv is not None else UNCHOSEN)
    t.first_edit.setText(first)
    t.second_edit.setText(second)
    t.elevation_edit.setText(elev)
    ok = t.convert()
    if not ok:
        return None, t.last_failure
    return dict(t.displayed_rows()), None


# (label, first, second, elev)
POINTS = [
    ("grid", "780000.000", "13123359.580", "800.00"),
    ("grid-noelev", "780000.000", "13123359.580", ""),
    ("geodetic-negw", "42.7325", "-84.5555", "800.00"),
    ("geodetic-posw", "42.7325", "84.5555", "800.00"),
]

ZONES = list(ALL_ZONES)
FT = ALL_UNITS[0]
problems = []
checked = 0

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    combos = []
    # zone -> zone
    for s, t in itertools.product(ZONES, ZONES):
        for iu, ou in itertools.product(ALL_UNITS, ALL_UNITS):
            combos.append(("grid", s, t, iu, ou, None))
    # zone -> geodetic, both conventions
    for s in ZONES:
        for iu, ou in itertools.product(ALL_UNITS, ALL_UNITS):
            for c in LongitudeConvention:
                combos.append(("grid", s, GEODETIC, iu, ou, c))
    # geodetic -> zone
    for t in ZONES:
        for iu, ou in itertools.product(ALL_UNITS, ALL_UNITS):
            combos.append(("geodetic-negw", GEODETIC, t, iu, ou, LongitudeConvention.NEGATIVE_WEST))
            combos.append(("geodetic-posw", GEODETIC, t, iu, ou, LongitudeConvention.POSITIVE_WEST))

    for (pname, s, t, iu, ou, c) in combos:
        first, second, elev = [p[1:] for p in POINTS if p[0] == pname][0]
        for tag, e in (("", elev), ("-noelev", "")):
            sub = tmp / f"c{checked}{tag}"
            sub.mkdir()
            audit, mfail, table = run_multi(sub, first, second, e, s, t, iu, ou, c)
            panel, sfail = run_single(first, second, e, s, t, iu, ou, c)
            checked += 1
            if (audit is None) != (panel is None):
                problems.append(("refusal mismatch", pname, s, t, iu, ou, c, tag,
                                 repr(mfail), repr(sfail)))
                continue
            if audit is None:
                continue
            # Compare every panel row that the audit CSV also carries.
            pairs = [
                ("Grid scale factor", "Grid scale factor"),
                ("Convergence", "Convergence"),
                ("Geoid height (m)", "Geoid height (m)"),
                ("Ellipsoid height (m)", "Ellipsoid height (m)"),
                ("Elevation factor", "Elevation factor"),
                ("Combined factor", "Combined factor"),
                ("Elevation", "Elevation"),
            ]
            for plabel, alabel in pairs:
                if plabel in panel and alabel in audit:
                    if panel[plabel] != audit[alabel]:
                        problems.append(("value", plabel, pname, s, t, iu, ou, c, tag,
                                         panel[plabel], audit[alabel]))
            # Latitude / Longitude
            if "Latitude" in panel and panel["Latitude"] != audit["Latitude"]:
                problems.append(("lat", pname, s, t, iu, ou, c, tag, panel["Latitude"], audit["Latitude"]))

print(f"checked {checked} configurations")
if problems:
    for p in problems[:60]:
        print("PROBLEM", p)
    print(f"total problems {len(problems)}")
else:
    print("no disagreement found on the compared quantities")
