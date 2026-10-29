"""Offscreen previews for the owner's screen review of U2 (DESIGN.md #72, D1-D3).

Run from the repository root with QT_QPA_PLATFORM=offscreen:
    py review/utm-u2/preview.py
Writes review/utm-u2/{multi,single}_{ift,m}.png: the FROM zone dropdown open
on each tab, with the input Units box on international feet and then metres,
so the EPSG code each row shows can be read beside the unit that selects it.
UTM rows are not in these lists: no dropdown offers UTM until work package U5.
"""
import os, sys
sys.path.insert(0, os.getcwd())
from michspc.gui import settings_store
from michspc.gui.app import build_application
from michspc.gui.window import MainWindow
from michspc.spc.units import INTERNATIONAL_FEET, METERS

app = build_application(["preview"])
win = MainWindow(store=settings_store.MemoryStore())
win.resize(900, 640)
win.show()
here = os.path.dirname(os.path.abspath(__file__))
for name, page, index in (("multi", win, 1), ("single", win.single_point, 0)):
    win.tabs.setCurrentIndex(index)
    for unit, tag in ((INTERNATIONAL_FEET, "ift"), (METERS, "m")):
        page.input_unit.setCurrentIndex(page.input_unit.findData(unit))
        app.processEvents()
        page.from_zone.showPopup()
        app.processEvents()
        view = page.from_zone.view()
        view.setMinimumWidth(520)
        view.window().resize(520, 590)
        app.processEvents()
        view.window().grab().save(os.path.join(here, f"{name}_{tag}.png"))
        page.from_zone.hidePopup()
        app.processEvents()
print("written:", sorted(f for f in os.listdir(here) if f.endswith(".png")))
