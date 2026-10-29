"""Offscreen previews for the owner's screen review of R1 (DESIGN.md #73).

Run from the repository root with QT_QPA_PLATFORM=offscreen:
    py review/refusal-r1/preview.py
Writes review/refusal-r1/dialog.png and window.png: the owner's case
(49.0 N, 86.0 W, Auto on NAD83(2011)) on the Single point tab.
"""
import os, sys
sys.path.insert(0, os.getcwd())
from PySide6.QtWidgets import QMessageBox
from michspc.gui import controls, settings_store
from michspc.gui.app import build_application
from michspc.gui.window import MainWindow
from michspc.spc.frames import NAD83_2011

app = build_application(["preview"])
win = MainWindow(store=settings_store.MemoryStore())
captured = []
tab = win.single_point
tab._show_failure = captured.append
win.resize(900, 640)
win.show()
win.tabs.setCurrentWidget(tab)
tab.from_zone.setCurrentIndex(tab.from_zone.findData(controls.geodetic_choice(NAD83_2011)))
tab.to_zone.setCurrentIndex(tab.to_zone.findData(controls.auto_choice(NAD83_2011)))
tab.first_edit.setText("49.0")
tab.second_edit.setText("86.0")
app.processEvents()
tab.convert()
app.processEvents()
here = os.path.dirname(os.path.abspath(__file__))
win.grab().save(os.path.join(here, "window.png"))
box = QMessageBox(win)
box.setIcon(QMessageBox.Icon.Critical)
box.setWindowTitle("MCX — single point — conversion refused")
controls.fill_failure_dialog(box, captured[0])
box.show()
app.processEvents()
box.grab().save(os.path.join(here, "dialog.png"))
print("status:", tab.status_label.text(), "| window min width", win.minimumSizeHint().width())
