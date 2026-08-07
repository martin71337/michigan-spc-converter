"""Probe 5: GUI state, enablement, staleness, clipboard, and file creation."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys, itertools
sys.path.insert(0, r"C:\claude-projects\coord-convert")

from PySide6.QtWidgets import QApplication
from michspc.gui.single_point import SinglePointTab
from michspc.gui.controls import UNCHOSEN, GEODETIC
from michspc.job import Direction, LongitudeConvention
from michspc.spc.zones import ALL_ZONES
from michspc.spc.units import ALL_UNITS

app = QApplication.instance() or QApplication([])


def set_data(combo, data):
    for i in range(combo.count()):
        if combo.itemData(i) is data or combo.itemData(i) == data:
            combo.setCurrentIndex(i)
            return
    raise AssertionError(data)


def tab():
    t = SinglePointTab()
    t._show_failure = lambda e: None
    t._set_clipboard = lambda s: setattr(t, "clip", s)
    t.clip = None
    return t


NORTH, CENTRAL, SOUTH = ALL_ZONES
FT, *_ = ALL_UNITS

print("=== A. enablement matrix ===")
t = tab()
print("initial convert enabled:", t.convert_button.isEnabled())
print("initial first_edit enabled:", t.first_edit.isEnabled(),
      "elev enabled:", t.elevation_edit.isEnabled())
print("initial labels:", t.first_label.text(), "/", t.second_label.text())

# geodetic->geodetic is not a conversion
set_data(t.from_zone, GEODETIC); set_data(t.to_zone, GEODETIC)
t.first_edit.setText("42.7325"); t.second_edit.setText("-84.5555")
print("geo->geo direction:", t.direction(), "convert enabled:", t.convert_button.isEnabled())
ok = t.convert()
print("geo->geo convert() returned:", ok, "| failure:", str(t.last_failure)[:60])

# geodetic direction without a longitude convention
t2 = tab()
set_data(t2.from_zone, GEODETIC); set_data(t2.to_zone, CENTRAL)
t2.first_edit.setText("42.7325"); t2.second_edit.setText("-84.5555")
print("geo->zone no convention: enabled:", t2.convert_button.isEnabled(),
      "longitude combo enabled:", t2.longitude_combo.isEnabled())
set_data(t2.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
print("after choosing convention: enabled:", t2.convert_button.isEnabled())

# zone->zone: longitude combo must be irrelevant
t3 = tab()
set_data(t3.from_zone, CENTRAL); set_data(t3.to_zone, SOUTH)
print("zone->zone longitude combo enabled:", t3.longitude_combo.isEnabled(),
      "label enabled:", t3.longitude_label.isEnabled())
t3.first_edit.setText("780000.000"); t3.second_edit.setText("13123359.580")
print("zone->zone convert enabled with no convention:", t3.convert_button.isEnabled())

print()
print("=== B. staleness: does a result survive a control change? ===")
t4 = tab()
set_data(t4.from_zone, CENTRAL); set_data(t4.to_zone, SOUTH)
t4.first_edit.setText("780000.000"); t4.second_edit.setText("13123359.580")
t4.elevation_edit.setText("800.00")
assert t4.convert(), t4.last_failure
before = t4.displayed_rows()
print("converted. INPUT zone row:", before[0], " OUTPUT easting:", dict(before)["Easting"])
# Now change every control.
set_data(t4.from_zone, NORTH)
set_data(t4.to_zone, NORTH)
set_data(t4.output_unit, ALL_UNITS[-1])
after = t4.displayed_rows()
print("controls now From/To =", t4.from_zone.currentText(), "/", t4.to_zone.currentText(),
      "output unit =", t4.output_unit.currentText())
print("panel unchanged?", before == after)
print("panel still says INPUT zone:", after[0], "| OUTPUT units:", dict(after)["Units"])
print("copy_all enabled:", t4.copy_all_button.isEnabled())
print("status line:", t4.status_label.text())

# staleness across a direction change that makes the layout invalid
t5 = tab()
set_data(t5.from_zone, CENTRAL); set_data(t5.to_zone, GEODETIC)
set_data(t5.longitude_combo, LongitudeConvention.POSITIVE_WEST)
t5.first_edit.setText("780000.000"); t5.second_edit.setText("13123359.580")
assert t5.convert(), t5.last_failure
lon_before = dict(t5.displayed_rows())["Longitude"]
set_data(t5.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
lon_after = dict(t5.displayed_rows())["Longitude"]
print("longitude shown before convention flip:", lon_before,
      "after flip (no reconvert):", lon_after,
      "| combo now:", t5.longitude_combo.currentText())

print()
print("=== C. failure clears the panel ===")
t6 = tab()
set_data(t6.from_zone, CENTRAL); set_data(t6.to_zone, SOUTH)
t6.first_edit.setText("780000.000"); t6.second_edit.setText("13123359.580")
assert t6.convert()
t6.second_edit.setText("not a number")
ok = t6.convert()
print("second convert ok:", ok, "| panel rows now:", len(t6.displayed_rows()),
      "| copy_all enabled:", t6.copy_all_button.isEnabled(),
      "| result:", t6.result)
print("status:", t6.status_label.text()[:110])

print()
print("=== D. clipboard ===")
t7 = tab()
set_data(t7.from_zone, CENTRAL); set_data(t7.to_zone, SOUTH)
t7.first_edit.setText("780000.000"); t7.second_edit.setText("13123359.580")
t7.elevation_edit.setText("800.00")
assert t7.convert(), t7.last_failure
rows = t7.displayed_rows()
mismatch = []
for i, (label, shown) in enumerate(rows):
    t7.copy_buttons[i].click()
    if t7.clip != shown:
        mismatch.append((i, label, shown, t7.clip))
print("per-value copy mismatches:", mismatch)
t7.copy_all_button.click()
allt = t7.clip
from michspc.gui.results_model import single_point_clipboard_text
print("copy_all == serialise(panel.sections):",
      allt == single_point_clipboard_text(t7.sections))
missing = [lbl for lbl, val in rows if f"{lbl}\t{val}" not in allt]
print("rows missing from copy-all:", missing)
print("copy on empty panel:", tab().copy_value(0), tab().copy_all())

print()
print("=== E. does the single-point path touch the filesystem? ===")
import michspc.fileio.exports as exports
import michspc.fileio.report as report
import builtins, pathlib, os as _os
opened = []
real_open = builtins.open
builtins.open = lambda *a, **k: (opened.append(a[:1]), real_open(*a, **k))[1]
real_mkdir = pathlib.Path.mkdir
pathlib.Path.mkdir = lambda self, *a, **k: opened.append(("mkdir", self)) or real_mkdir(self, *a, **k)
t8 = tab()
set_data(t8.from_zone, GEODETIC); set_data(t8.to_zone, CENTRAL)
set_data(t8.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
t8.first_edit.setText("42.7325"); t8.second_edit.setText("-84.5555")
t8.elevation_edit.setText("800.00")
assert t8.convert(), t8.last_failure
builtins.open = real_open
pathlib.Path.mkdir = real_mkdir
writes = [o for o in opened if o and str(o).find("g2018") < 0]
print("open()/mkdir calls during a single-point convert:", opened)
print("has SinglePointTab any attribute referencing exports/report/write:",
      [n for n in dir(t8) if "write" in n.lower() or "export" in n.lower()
       or "save" in n.lower() or "folder" in n.lower()])

print()
print("=== F. per-direction labels ===")
for src, tgt in ((UNCHOSEN, UNCHOSEN), (GEODETIC, CENTRAL), (CENTRAL, GEODETIC),
                 (CENTRAL, SOUTH), (UNCHOSEN, CENTRAL), (CENTRAL, UNCHOSEN),
                 (GEODETIC, UNCHOSEN)):
    tt = tab()
    set_data(tt.from_zone, src); set_data(tt.to_zone, tgt)
    print(f"{str(src)[:9]:>9} -> {str(tgt)[:9]:<9} labels={tt.first_label.text()!r},"
          f"{tt.second_label.text()!r} in_units={tt.input_unit_label.text()!r} "
          f"out_units={tt.output_unit_label.text()!r} "
          f"lonEnabled={tt.longitude_combo.isEnabled()} "
          f"editEnabled={tt.first_edit.isEnabled()}")
