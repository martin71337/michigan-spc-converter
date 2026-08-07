"""Where the application icon comes from, and what happens when it is absent.

The icon is **derived, never committed** (docs/DESIGN.md amendment #15 note 1):
``tools/make_icon.py`` renders the six Windows sizes from the owner's master
artwork into build output. This module is the reading half of that arrangement,
and it is deliberately forgiving in one specific way: a source checkout that has
never run the build step must still launch. A missing icon is a cosmetic
shortfall, not a reason to refuse to open a window, and this is the one place in
the program where falling back rather than refusing is the correct behaviour —
nothing about a coordinate depends on it.

The search order is most-derived first:

1. the generated ``.ico`` inside a frozen bundle, when running frozen;
2. the generated ``.ico`` in the repository's build output;
3. the master PNG itself, which is committed, so a fresh clone still shows the
   right artwork at whatever size Qt scales it to.

If none of those exist the icon is null, which Qt accepts and draws as the
platform default.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon

GENERATED_ICO_NAME = "mcx.ico"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
"""michspc/gui/icon.py -> michspc/gui -> michspc -> the repository root."""

GENERATED_ICO = REPO_ROOT / "build" / "icon" / GENERATED_ICO_NAME
"""What ``tools/make_icon.py`` writes by default. The two are pinned to each
other by ``tests/test_icon.py``, so moving one without the other fails the
suite rather than silently losing the icon."""

MASTER_PNG = REPO_ROOT / "assets" / "icon" / "mcx-1024.png"
"""The committed master artwork, used as the fallback."""


def _bundle_root() -> Path | None:
    """The frozen bundle's unpacked data directory, or None if not frozen.

    PyInstaller sets ``sys._MEIPASS``; nothing else does, and a source run must
    not guess at a path that only exists inside a bundle
    (docs/method/TOOLING.md).
    """
    location = getattr(sys, "_MEIPASS", None)
    return Path(location) if location else None


def icon_candidates() -> tuple[Path, ...]:
    """Every place the icon may live, in the order they are preferred."""
    candidates: list[Path] = []
    bundle = _bundle_root()
    if bundle is not None:
        candidates.append(bundle / "assets" / "icon" / GENERATED_ICO_NAME)
    candidates.append(GENERATED_ICO)
    candidates.append(MASTER_PNG)
    return tuple(candidates)


def icon_path() -> Path | None:
    """The first candidate that exists, or None."""
    for candidate in icon_candidates():
        if candidate.is_file():
            return candidate
    return None


def application_icon() -> QIcon:
    """The window icon. Never raises, and never blocks the window opening.

    Returns a null ``QIcon`` when no artwork can be found — including when the
    file exists but Qt cannot decode it, which ``QIcon`` reports by being null
    rather than by raising.
    """
    found = icon_path()
    if found is None:
        return QIcon()
    return QIcon(str(found))
