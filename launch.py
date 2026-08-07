"""Frozen and source launches share this entry point.

PyInstaller freezes a *script*, not a module run with ``-m``
(docs/method/TOOLING.md). Keeping this the only entry point means the frozen
bundle and a source run take an identical code path — so a bug that only appears
in one of them has nowhere to hide.

Two modes, decided by the command line:

    michspc-spc-converter.exe                     open the window
    michspc-spc-converter.exe --selftest          check the bundle, exit 0 or 1

The self-test is the build gate on the shipped bundle (``michspc/selftest.py``),
and it must be reachable from the executable itself, because the bundle is the
one thing the test suite cannot run against.

Both imports are deferred into the branch that needs them. That is not
tidiness: the self-test's job includes reporting a *missing* PySide6 by name
rather than dying in a traceback before it starts, which it cannot do if this
module imports Qt on the way in.
"""

import sys


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)

    if "--selftest" in arguments:
        from michspc.selftest import main as selftest_main

        return selftest_main(arguments)

    from michspc.gui.app import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
