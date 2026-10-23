"""Layout previews of the Options / Auto zone GUI (work package Z4), for the owner.

**A layout preview, NOT the owner's screen review.** This drives the window on
Qt's OFFSCREEN platform and saves what ``QWidget.grab()`` renders. That
platform's fonts and metrics are not Windows' (docs/DESIGN.md amendment #31)
and it draws no native style, so widths, wrapping and row heights will differ
from his screen. What these images show is the ORDER and CONTENT of things -
which rows exist, what each is called, where Auto sits, what the Options
dialog asks - so the owner can see the shape before he runs the real build.
Every layout decision in Z4 still waits for his review on the real screen
(docs/PLAN-options-autozone.md section 5).

Run from the repository root:

    py review/autozone-z4/make_screens.py

It writes PNGs beside itself:

* ``a_options_dialog.png`` - the Options dialog on its defaults;
* ``b_single_point_defaults.png`` - the Single point tab as it opens (no date
  box: the default date source is "Today");
* ``c_multi_point_defaults.png`` - the Multi point tab as it opens;
* ``d_zone_list_open.png`` - a To list open from a latitude/longitude From,
  with the Auto entry at the top of the zone section;
* ``e_single_point_auto_result.png`` - an Auto single point result (Calhoun
  County -> Michigan South), showing the zone and county rows;
* ``f_multi_point_auto_table.png`` - a Multi point Auto table across two
  zones, with the Zone and County columns;
* ``g_enter_a_date.png`` - the Single point tab under "Enter a date on the
  tab" with a WGS 84 From selected: the date box shown, unanswered.

The windows read an IN-MEMORY Options store - never the registry - and the one
Multi point job writes into a temporary folder deleted afterwards; nothing is
written into the repository except the PNGs.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# The offscreen plugin reads fonts from a directory, not from the Windows font
# service: pointed at none, every glyph renders as a box. The system's own
# folder, where there is one (this is a preview, not a pin).
if Path(r"C:\Windows\Fonts").is_dir():
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from michspc.gui import controls, options, settings_store  # noqa: E402
from michspc.gui.app import build_application  # noqa: E402
from michspc.gui.options_dialog import OptionsDialog  # noqa: E402
from michspc.gui.window import MainWindow  # noqa: E402
from michspc.job import ObservationDateSource  # noqa: E402
from michspc.spc.frames import NAD83_2011, WGS84_G2296  # noqa: E402
from michspc.spc.zones import MI_SOUTH  # noqa: E402

# Never the owner's registry, even from a review script.
settings_store.set_store_factory(settings_store.MemoryStore)

NAD = controls.geodetic_choice(NAD83_2011)
G2296 = controls.geodetic_choice(WGS84_G2296)
AUTO_NAD = controls.auto_choice(NAD83_2011)


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
    app = build_application(["mcx-z4-screens"])
    # Named, because the offscreen font database's own fallback is a symbol
    # face on this machine. Segoe UI is what the real Windows plugin uses.
    from PySide6.QtGui import QFont

    app.setFont(QFont("Segoe UI", 9))

    # (a) the Options dialog, on its defaults.
    dialog = OptionsDialog(options.DEFAULT_OPTIONS)
    dialog.show()
    app.processEvents()
    save(dialog, "a_options_dialog.png")
    dialog.close()

    # (b) and (d), (e): the Single point tab.
    window = MainWindow()
    window.resize(1000, 980)
    tab = window.single_point
    refuse_dialogs(tab)
    window.tabs.setCurrentWidget(tab)
    window.show()
    app.processEvents()
    save(window, "b_single_point_defaults.png")

    choose(tab.from_zone, NAD)
    app.processEvents()
    tab.to_zone.showPopup()
    app.processEvents()
    save(tab.to_zone.view().window(), "d_zone_list_open.png")
    tab.to_zone.hidePopup()

    choose(tab.to_zone, AUTO_NAD)
    tab.first_edit.setText("42.250568")
    tab.second_edit.setText("84.954191")
    tab.elevation_edit.setText("280.000")
    if not tab.convert():
        raise SystemExit("the Auto single point did not convert")
    app.processEvents()
    save(window, "e_single_point_auto_result.png")

    # (g) "Enter a date on the tab", with a WGS 84 From: the box appears.
    chosen = options.DEFAULT_OPTIONS.with_groups(options.group_of(G2296))
    window.apply_options(
        options.Options(
            shown=chosen.shown,
            auto_frame=chosen.auto_frame,
            date_source=ObservationDateSource.ENTERED,
        )
    )
    choose(tab.from_zone, G2296)
    choose(tab.to_zone, MI_SOUTH)
    app.processEvents()
    save(window, "g_enter_a_date.png")
    window.close()

    # (c) and (f): the Multi point tab.
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        source = folder / "auto-points.csv"
        source.write_text(
            "1,42.250568,84.954191,280.000,CALHOUN\n"
            "2,44.682131,83.622405,190.000,ALCONA\n"
            "3,42.7325,84.5555,260.000,LANSING\n",
            encoding="utf-8",
        )
        multi = MainWindow()
        multi.resize(1200, 760)
        refuse_dialogs(multi)
        multi._ask_overwrite = lambda existing, error: True
        multi.tabs.setCurrentIndex(1)
        multi.show()
        app.processEvents()
        save(multi, "c_multi_point_defaults.png")
        multi.input_edit.setText(str(source))
        multi.output_edit.setText(str(folder))
        choose(multi.from_zone, NAD)
        choose(multi.to_zone, AUTO_NAD)
        if not multi.convert():
            raise SystemExit("the Multi point Auto job did not convert")
        app.processEvents()
        save(multi, "f_multi_point_auto_table.png")
        multi.close()


if __name__ == "__main__":
    main()
