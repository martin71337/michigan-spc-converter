"""Layout previews of the WGS 84 build's GUI (work package W5), for the owner.

**A layout preview, NOT the owner's screen review.** This drives both tabs on
Qt's OFFSCREEN platform and saves what ``QWidget.grab()`` renders. That
platform's fonts and metrics are not Windows': it answers 12 px for every
font family's line height where the Windows plugin answers 16 for Segoe UI
(docs/DESIGN.md amendment #31), and it draws no native style. Widths, wrapping
and row heights here will differ from his screen. What these images are good
for is the ORDER and CONTENT of things - which rows exist, what each is
labelled, where the observation date sits, how the dropdown is grouped - so
the owner can see the shape before he runs the real build. Every layout
decision in W5 still waits for his review on the real screen
(docs/PLAN-wgs84.md section 3.7; section 7, "still human").

Run from the repository root:

    python3 review/wgs84-w5/make_screens.py

It writes PNGs beside itself:

* ``a_single_point_wgs84_to_zone.png`` - a WGS84(G2296) geodetic -> Michigan
  South single-point result, both positions frame-labelled;
* ``b_date_unanswered.png`` - the same form before the observation date is
  answered: the date shows "— choose —" and Convert is disabled;
* ``c_multi_point_g2g_table.png`` - a Multi point geodetic-to-geodetic
  (WGS84(G2296) -> NAD83(2011)) result table, headings naming the frame;
* ``d_realization_warning.png`` - a G2296 job dated 2012-06-15, before G2296
  came into use, with the job-level warning in the warnings field;
* ``e_zone_dropdown.png`` - the zone dropdown's list, showing the separated
  block of five WGS 84 / ITRF entries.

The script converts through the real ``job.run`` and writes one archive into a
temporary folder it deletes afterwards; nothing is written into the
repository except the PNGs. The lead decides whether those are committed.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QDate  # noqa: E402

from michspc.gui import controls  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.window import MainWindow  # noqa: E402
from michspc.spc.frames import NAD83_2011, WGS84_G2296  # noqa: E402
from michspc.spc.vertical import HeightKind  # noqa: E402
from michspc.spc.zones import MI_SOUTH  # noqa: E402

G2296 = controls.geodetic_choice(WGS84_G2296)
NAD = controls.geodetic_choice(NAD83_2011)


def choose(combo, data) -> None:
    index = combo.findData(data)
    if index < 0:
        raise SystemExit(f"{combo!r} has no entry for {data!r}")
    combo.setCurrentIndex(index)


def save(widget, name: str) -> Path:
    path = HERE / name
    if not widget.grab().save(str(path)):
        raise SystemExit(f"could not write {path}")
    print(f"wrote {path.relative_to(ROOT)}")
    return path


def refuse_dialogs(page) -> None:
    """Headless: a modal failure box would block, so a refusal stops the run."""

    def stop(error):
        raise SystemExit(f"unexpected refusal: {error}")

    page._show_failure = stop


def main() -> None:
    app = build_application(["mcx-w5-screens"])

    # (b) then (a): the Single point form, unanswered date, then converted.
    window = MainWindow()
    window.resize(1000, 980)
    tab = window.single_point
    refuse_dialogs(tab)
    window.tabs.setCurrentWidget(tab)
    window.show()
    choose(tab.from_zone, G2296)
    choose(tab.to_zone, MI_SOUTH)
    choose(tab.height_kind_combo, HeightKind.ELLIPSOID)
    tab.first_edit.setText("42.7325")
    tab.second_edit.setText("84.5555")
    tab.elevation_edit.setText("200.000")
    app.processEvents()
    if tab.convert_button.isEnabled():
        raise SystemExit("Convert is enabled with the date unanswered")
    save(window, "b_date_unanswered.png")

    tab.observation_date_edit.setDate(QDate(2025, 6, 15))
    if not tab.convert():
        raise SystemExit("the WGS 84 single point did not convert")
    app.processEvents()
    save(window, "a_single_point_wgs84_to_zone.png")

    # (d) the realization warning: G2296 dated before it came into use.
    tab.observation_date_edit.setDate(QDate(2012, 6, 15))
    if not tab.convert():
        raise SystemExit("the out-of-period job did not convert")
    if not tab.result.job_warnings:
        raise SystemExit("no realization warning was raised")
    app.processEvents()
    save(window, "d_realization_warning.png")

    # (e) the dropdown list itself.
    choose(tab.to_zone, controls.UNCHOSEN)
    tab.to_zone.showPopup()
    app.processEvents()
    save(tab.to_zone.view().window(), "e_zone_dropdown.png")
    tab.to_zone.hidePopup()
    window.close()

    # (c) the Multi point geodetic-to-geodetic table.
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        source = folder / "wgs84-points.csv"
        source.write_text(
            "1,42.7325,84.5555,200.000,LANSING\n"
            "2,43.6150,84.2470,190.500,MIDLAND\n"
            "3,42.3314,83.0458,183.000,DETROIT\n",
            encoding="utf-8",
        )
        multi = MainWindow()
        multi.resize(1200, 760)
        refuse_dialogs(multi)
        multi._ask_overwrite = lambda existing, error: True
        multi.tabs.setCurrentIndex(1)
        multi.show()
        multi.input_edit.setText(str(source))
        multi.output_edit.setText(str(folder))
        choose(multi.from_zone, G2296)
        choose(multi.to_zone, NAD)
        multi.observation_date_edit.setDate(QDate(2025, 6, 15))
        if not multi.convert():
            raise SystemExit("the Multi point G2G job did not convert")
        app.processEvents()
        save(multi, "c_multi_point_g2g_table.png")
        multi.close()


if __name__ == "__main__":
    main()
