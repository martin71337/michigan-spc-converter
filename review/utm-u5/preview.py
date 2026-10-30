"""Offscreen previews for the owner's screen review of U5 (DESIGN.md #72, D6).

Run from the repository root with QT_QPA_PLATFORM=offscreen:
    py review/utm-u5/preview.py
Writes, into review/utm-u5/:

  {single,multi}_dropdown_{ift,m}.png  the FROM zone dropdown open on each tab,
      scrolled to its end so the UTM block shows, with the input Units box on
      international feet and then metres (a NAD83(2011) UTM row names its
      metre EPSG code either way; a NATRF2022 UTM row names none).
  options.png        the Options dialog, with its "UTM zones" group.
  single_result.png  the Single point tab after NAD83(2011) geodetic ->
      NAD83(2011) / UTM zone 16N at the production NCAT anchor 43.8138851900 N,
      84.4055193200 W (NCAT: N 4,854,473.717 m, E 708,662.368 m).
  multi_result.png   the Multi point tab after a UTM 16N -> Michigan Central
      (2112) job on the same anchor's NCAT UTM coordinate.

Offscreen rendering, not the Windows plugin: fonts and sizes differ on the
real screen, which is what the owner's review is for.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.getcwd())
from michspc.gui import controls, settings_store  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.options_dialog import OptionsDialog  # noqa: E402
from michspc.gui.window import MainWindow  # noqa: E402
from michspc.spc.frames import NAD83_2011  # noqa: E402
from michspc.spc.units import INTERNATIONAL_FEET, METERS  # noqa: E402
from michspc.spc.zones import zone_by_code  # noqa: E402

LATITUDE, LONGITUDE = "43.8138851900", "84.4055193200"  # positive west
NORTHING, EASTING = "4854473.717", "708662.368"

app = build_application(["preview"])
win = MainWindow(store=settings_store.MemoryStore())
win._show_failure = lambda error: print("REFUSED:", error)
win.single_point._show_failure = lambda error: print("REFUSED:", error)
win._ask_overwrite = lambda existing, error: True
win.resize(900, 640)
win.show()
here = os.path.dirname(os.path.abspath(__file__))


def choose(combo, data):
    combo.setCurrentIndex(combo.findData(data))


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
        view.scrollToBottom()
        app.processEvents()
        view.window().grab().save(os.path.join(here, f"{name}_dropdown_{tag}.png"))
        page.from_zone.hidePopup()
        app.processEvents()

dialog = OptionsDialog(win.options, win)
dialog.show()
app.processEvents()
dialog.grab().save(os.path.join(here, "options.png"))
dialog.close()

tab = win.single_point
win.tabs.setCurrentIndex(0)
choose(tab.from_zone, controls.geodetic_choice(NAD83_2011))
choose(tab.to_zone, zone_by_code("16N"))
tab.first_edit.setText(LATITUDE)
tab.second_edit.setText(LONGITUDE)
tab.convert()
app.processEvents()
win.grab().save(os.path.join(here, "single_result.png"))

folder = tempfile.mkdtemp()
source = os.path.join(folder, "utm16n.csv")
with open(source, "w", encoding="utf-8") as handle:
    handle.write(f"1,{NORTHING},{EASTING},,A\n")
win.tabs.setCurrentIndex(1)
win.input_edit.setText(source)
win.output_edit.setText(folder)
choose(win.from_zone, zone_by_code("16N"))
choose(win.to_zone, zone_by_code("2112"))
choose(win.output_unit, METERS)
win.convert()
app.processEvents()
win.grab().save(os.path.join(here, "multi_result.png"))
print("written:", sorted(f for f in os.listdir(here) if f.endswith(".png")))
