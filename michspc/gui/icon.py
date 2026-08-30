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
2. the generated ``.ico`` in the repository's build output, **unless the master
   artwork is newer than it** — see below;
3. the master PNG itself, which is committed, so a fresh clone still shows the
   right artwork at whatever size Qt scales it to.

If none of those exist the icon is null, which Qt accepts and draws as the
platform default.

**The staleness rule, and the incident that produced it.** On 2026-08-29, during
the owner's screen review of the H6 dropdowns, every source run of this program
was showing the COMPASS ROSE — the artwork replaced at 0.6.4 (amendment #60) by
the survey monument. Nothing was wrong with the master: ``build/icon/mcx.ico``
had been generated on 2026-08-11, two weeks before the monument was drawn, and
"most-derived first" preferred it forever. A derived file is only more derived
while it is derived from the CURRENT source; after that it is simply older.

So on a source run the generated ``.ico`` is skipped when the master's mtime is
strictly newer than its own, and the master is used instead. Strictly newer, so
a file written in the same second as its source is still trusted — the build
step writes the ``.ico`` after reading the PNG, so equal times mean current.

**The frozen bundle's candidate is deliberately NOT subject to this.** A bundle
is assembled in one operation by the release build's own gate, from the artwork
present at that moment, and it contains no master PNG to compare against; there
is no staleness question to answer, and inventing one would put a filesystem
comparison in the path of the shipped program for no fact it could learn.
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


def generated_ico_is_stale() -> bool:
    """True when the built ``.ico`` is older than the artwork it comes from.

    Both files must exist for the question to mean anything: with no master
    there is nothing to be out of date with, and with no generated file there
    is nothing to skip.

    Forgiving by construction, like everything else in this module - an
    unreadable timestamp answers False, so the worst a filesystem oddity can do
    is leave the previous behaviour in place rather than take the icon away.
    """
    try:
        if not (GENERATED_ICO.is_file() and MASTER_PNG.is_file()):
            return False
        return MASTER_PNG.stat().st_mtime > GENERATED_ICO.stat().st_mtime
    except OSError:
        return False


def icon_path() -> Path | None:
    """The first candidate that exists, skipping a stale generated ``.ico``.

    "Stale" is the module docstring's rule: on a SOURCE run, a generated file
    older than the master it was rendered from is not more derived, it is just
    older, and the 0.6.4 artwork spent two weeks hidden behind one.
    """
    stale = generated_ico_is_stale()
    for candidate in icon_candidates():
        if stale and candidate == GENERATED_ICO:
            continue
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
