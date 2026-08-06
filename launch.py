"""Frozen and source launches share this entry point.

PyInstaller freezes a *script*, not a module run with ``-m``
(docs/method/TOOLING.md). Keeping this two-liner as the only entry point means
the frozen bundle and a source run take an identical code path — so a bug that
only appears in one of them has nowhere to hide.
"""

from michspc.gui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
