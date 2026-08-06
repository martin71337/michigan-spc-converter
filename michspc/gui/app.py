"""Application entry point.

``launch.py`` — the single script the frozen bundle and a source run both go
through (docs/method/TOOLING.md) — imports ``main`` from here. The signature is
part of that contract: ``main() -> int``, returning a process exit code.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from michspc.gui.window import WINDOW_TITLE, MainWindow


def build_application(argv: list[str] | None = None) -> QApplication:
    """Return the process's QApplication, creating it only if there is none.

    A second QApplication in one process crashes the interpreter
    (docs/method/TOOLING.md), so this never assumes it is the first caller.
    """
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing

    application = QApplication(list(argv) if argv is not None else sys.argv)
    application.setApplicationName(WINDOW_TITLE)
    application.setOrganizationName("Michigan SPC Zone Converter")
    return application


def main(argv: list[str] | None = None) -> int:
    """Open the window and run the event loop. Returns the exit code.

    No stylesheet and no style override: the program wears whatever the native
    Windows widget style is, which is the presentation the owner chose
    (docs/method/METHOD.md section 5, "UI look").
    """
    application = build_application(argv)
    window = MainWindow()
    window.show()
    return int(application.exec())
