"""Probe 9: prove the single-point path creates nothing, in a FRESH process.

Every filesystem-mutating call is intercepted before any michspc import.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys, builtins, pathlib, shutil, tempfile, io
BASE = sys.argv[1] if len(sys.argv) > 1 else r"C:\claude-projects\coord-convert"
sys.path.insert(0, BASE)

calls = []
_open = builtins.open
def open_spy(file, mode="r", *a, **k):
    calls.append(("open", str(file), mode))
    return _open(file, mode, *a, **k)
builtins.open = open_spy

for mod, name in ((os, "replace"), (os, "rename"), (os, "remove"), (os, "unlink"),
                  (os, "mkdir"), (os, "makedirs"), (os, "open")):
    orig = getattr(mod, name)
    def make(orig=orig, name=name):
        def spy(*a, **k):
            calls.append((f"os.{name}",) + tuple(str(x) for x in a[:2]))
            return orig(*a, **k)
        return spy
    setattr(mod, name, make())

for name in ("mkdir", "touch", "write_text", "write_bytes", "rename", "replace", "unlink"):
    orig = getattr(pathlib.Path, name)
    def makep(orig=orig, name=name):
        def spy(self, *a, **k):
            calls.append((f"Path.{name}", str(self)))
            return orig(self, *a, **k)
        return spy
    setattr(pathlib.Path, name, makep())

orig_tmp = tempfile.NamedTemporaryFile
def tmp_spy(*a, **k):
    calls.append(("NamedTemporaryFile",))
    return orig_tmp(*a, **k)
tempfile.NamedTemporaryFile = tmp_spy

from PySide6.QtWidgets import QApplication
from michspc.gui.single_point import SinglePointTab
from michspc.gui.controls import GEODETIC
from michspc.job import LongitudeConvention
from michspc.spc.zones import ALL_ZONES

app = QApplication.instance() or QApplication([])
NORTH, CENTRAL, SOUTH = ALL_ZONES


def set_data(combo, data):
    for i in range(combo.count()):
        if combo.itemData(i) is data or combo.itemData(i) == data:
            combo.setCurrentIndex(i); return
    raise AssertionError(data)


t = SinglePointTab()
t._show_failure = lambda e: None
t._set_clipboard = lambda s: None
calls.clear()

for src, tgt, a, b, conv in (
    (CENTRAL, SOUTH, "176200.000", "19685000.000", None),
    (CENTRAL, GEODETIC, "176200.000", "19685000.000", LongitudeConvention.NEGATIVE_WEST),
    (GEODETIC, CENTRAL, "43.800", "-84.367", LongitudeConvention.NEGATIVE_WEST),
):
    set_data(t.from_zone, src); set_data(t.to_zone, tgt)
    if conv:
        set_data(t.longitude_combo, conv)
    t.first_edit.setText(a); t.second_edit.setText(b)
    t.elevation_edit.setText("812.40")
    assert t.convert(), t.last_failure
    t.copy_all_button.click()
    for btn in t.copy_buttons:
        btn.click()

writes = [c for c in calls
          if c[0] != "open" or any(m in c[2] for m in ("w", "a", "x", "+"))]
print("filesystem calls during three single-point conversions:")
for c in calls:
    print("  ", c)
print("MUTATING calls:", writes)
print()
print("static: names imported by michspc.gui.single_point")
import ast
src = _open(os.path.join(BASE, "michspc", "gui", "single_point.py"), encoding="utf-8").read()
tree = ast.parse(src)
for n in ast.walk(tree):
    if isinstance(n, ast.ImportFrom):
        print("   from", n.module, "import", [a.name for a in n.names])
    elif isinstance(n, ast.Import):
        print("   import", [a.name for a in n.names])
print("mentions 'exports':", "exports" in src, "| 'report':", "report." in src,
      "| 'open(':", "open(" in src, "| 'Path':", "Path" in src)
