"""Probe 8: INPUT-side units by hand, stale-text-under-new-labels, warnings text."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
sys.path.insert(0, r"C:\claude-projects\coord-convert")

from PySide6.QtWidgets import QApplication
from michspc.gui.single_point import SinglePointTab
from michspc.gui.controls import GEODETIC, UNCHOSEN
from michspc.job import LongitudeConvention
from michspc.spc.zones import ALL_ZONES
from michspc.spc.units import ALL_UNITS

app = QApplication.instance() or QApplication([])
NORTH, CENTRAL, SOUTH = ALL_ZONES
IFT, USFT, M = None, None, None
for u in ALL_UNITS:
    print("unit:", u.name, u.code, "decimals", u.decimals)
IFT = ALL_UNITS[0]
METERS = [u for u in ALL_UNITS if u.code in ("m", "M")][0]


def set_data(combo, data):
    for i in range(combo.count()):
        if combo.itemData(i) is data or combo.itemData(i) == data:
            combo.setCurrentIndex(i); return
    raise AssertionError(data)


def tab():
    t = SinglePointTab(); t._show_failure = lambda e: None
    t._set_clipboard = lambda s: None
    return t


print("\n=== A. GEODETIC_TO_ZONE INPUT elevation/units with in!=out ===")
t = tab()
set_data(t.from_zone, GEODETIC); set_data(t.to_zone, CENTRAL)
set_data(t.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
set_data(t.input_unit, IFT); set_data(t.output_unit, METERS)
t.first_edit.setText("43.800"); t.second_edit.setText("-84.367")
t.elevation_edit.setText("812.40")
assert t.convert(), t.last_failure
for s in t.sections:
    print(f"[{s.title}]")
    for v in s.values:
        print(f"   {v.label:24} {v.text}")

print("\n=== B. ZONE_TO_GEODETIC INPUT block with in=ift out=m ===")
t2 = tab()
set_data(t2.from_zone, CENTRAL); set_data(t2.to_zone, GEODETIC)
set_data(t2.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
set_data(t2.input_unit, IFT); set_data(t2.output_unit, METERS)
t2.first_edit.setText("176200.000"); t2.second_edit.setText("19685000.000")
t2.elevation_edit.setText("812.40")
assert t2.convert(), t2.last_failure
for s in t2.sections:
    print(f"[{s.title}]")
    for v in s.values:
        print(f"   {v.label:24} {v.text}")

print("\n=== C. stale typed text under relabelled fields ===")
t3 = tab()
set_data(t3.from_zone, CENTRAL); set_data(t3.to_zone, SOUTH)
t3.first_edit.setText("176200.000"); t3.second_edit.setText("19685000.000")
t3.elevation_edit.setText("812.40")
assert t3.convert(), t3.last_failure
set_data(t3.from_zone, GEODETIC)
set_data(t3.longitude_combo, LongitudeConvention.NEGATIVE_WEST)
print("labels now:", t3.first_label.text(), t3.second_label.text())
print("boxes still hold:", t3.first_edit.text(), "/", t3.second_edit.text())
print("convert enabled:", t3.convert_button.isEnabled())
ok = t3.convert()
print("convert() ->", ok)
if ok:
    for s in t3.sections:
        print(f"[{s.title}]")
        for v in s.values:
            print(f"   {v.label:24} {v.text[:90]}")
else:
    print("refused:", str(t3.last_failure)[:300])

print("\n=== D. how the typed point id shows up in a warning ===")
t4 = tab()
set_data(t4.from_zone, NORTH); set_data(t4.to_zone, SOUTH)
t4.first_edit.setText("176200.000"); t4.second_edit.setText("19685000.000")
t4.elevation_edit.setText("812.40")
assert t4.convert(), t4.last_failure
w = dict(t4.displayed_rows())["Warnings"]
print(w[:700])
print("--- status tooltip:", t4.status_label.toolTip()[:200])
