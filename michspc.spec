# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the Michigan SPC Zone Converter.

Committed, not generated. ``pyinstaller`` can write a spec for you; a written
one drifts from the program the moment anything moves, and this file carries
four decisions that have to be reviewable rather than rediscovered.

Build it through the gated script, never by hand for a release::

    py tools/build_release.py

**One folder, not one file.** One-file is the friendlier thing to *hand* to
someone — but nothing is handed over here. The deliverable is an Inno Setup
installer (docs/DESIGN.md amendment #13), and the surveyor launches the program
from the Start menu, so the folder is never seen. What one-folder buys is worth
having: the program starts immediately instead of unpacking a ~200 MB bundle to
a temporary directory on every launch, and — the reason that decides it — the
bundled GEOID18 tile sits on disk as an ordinary file that can be listed,
checksummed and compared against NGS's published SHA-256 by anyone who wants to
audit what the program is computing with. A one-file build hides that inside the
executable until the moment it runs. For a tool whose output supports a sealed
survey, a verifiable grid beats a tidy folder.

**The version is read, never restated.** ``michspc/__init__.py`` holds the only
version literal in the project (docs/method/TOOLING.md); this file imports it
and builds the Windows version resource from it, so the file properties Explorer
shows and the number the release gate checks cannot disagree.

**The icon is derived here, from the committed master.** ``tools/make_icon.py``
runs as part of the build rather than a hand-made ``.ico`` being committed, so
the artwork has exactly one authoritative representation (docs/DESIGN.md
amendment #15 note 1).

**Nothing is excluded.** ``excludes`` is deliberately empty. Excluding a module
that a dependency imports lazily produces a bundle that builds cleanly and dies
the first time a user reaches that feature — the numpy-under-ezdxf trap recorded
in docs/method/TOOLING.md. The disk this saves is not worth the failure mode it
buys, and the self-test below is what proves the bundle is complete.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve()  # noqa: F821 — PyInstaller injects SPECPATH

# The spec runs in PyInstaller's interpreter, whose sys.path does not
# necessarily include the project.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from michspc import APP_FULL_NAME, APP_NAME, APP_PUBLISHER, __version__  # noqa: E402
from michspc.selftest import LAZY_IMPORTS  # noqa: E402
from tools import make_icon  # noqa: E402

EXECUTABLE_NAME = "mcx"

# ---------------------------------------------------------------------------
# Data files. Destination paths are load-bearing: the running program looks for
# each of these at a specific place under sys._MEIPASS, and
# tests/test_selftest.py pins this file's destinations to those lookups.
# ---------------------------------------------------------------------------

DATA_DESTINATION = "data"
"""``michspc.fileio.ngs_grid.shipped_data_directory`` reads sys._MEIPASS/data;
both the geoid and VERTCON policy layers resolve their grids through it."""

# Every NGS grid the bundle carries, each under NGS's own filename so an auditor
# can list it, hash it and compare it against NGS's published file without
# unpacking anything (see the one-folder decision in the module docstring).
#
# The GEOID12B tile and the two VERTCON 3.0 grids are committed and bundled by
# WP-V1 (docs/PLAN-vertical-datums.md section 2.1). GEOID12B is not yet read by
# any code - the geoid model registry that reaches it is WP-V5 - and it is
# bundled now rather than later so that the file, its checksum and the build
# wiring all land in one reviewable step.
#
# Each of the four digests is pinned in code and checked by the suite, not merely
# recorded in the plan: geoid.GEOID18_TILE_SHA256, geoid.GEOID12B_TILE_SHA256,
# vertcon.VERTCON3_TRN_SHA256 and vertcon.VERTCON3_ERR_SHA256. This list is names
# only - a name is what PyInstaller needs - so nothing here can stand in for that.
NGS_GRID_FILENAMES = (
    "g2018u3.bin",  # GEOID18 CONUS tile #3
    "g2012bu3.bin",  # GEOID12B CONUS tile #3, same geometry
    "vertcon_3.0_20190601.ngvd29.navd88.conus.oht.trn.b",  # the shift
    "vertcon_3.0_20190601.ngvd29.navd88.conus.oht.err.b",  # its uncertainty
)

NGS_GRID_SOURCES = [REPO_ROOT / "data" / name for name in NGS_GRID_FILENAMES]

ICON_DESTINATION = "assets/icon"
"""``michspc.gui.icon.icon_candidates`` reads
sys._MEIPASS/assets/icon/coord-convert.ico."""

missing = [str(path) for path in NGS_GRID_SOURCES if not path.is_file()]
if missing:
    raise SystemExit(
        "NGS grid files are missing from the source tree: "
        + ", ".join(missing)
        + ". These ship with the program: without the geoid tile the bundle "
        "cannot compute an elevation or combined factor for any point, and "
        "without the VERTCON pair it cannot convert a height between vertical "
        "datums. The self-test would refuse the build anyway."
    )

# Derived here so a bundle can never ship yesterday's artwork.
ICON_FILE = make_icon.generate()

datas = [(str(path), DATA_DESTINATION) for path in NGS_GRID_SOURCES]
datas.append((str(ICON_FILE), ICON_DESTINATION))

# ---------------------------------------------------------------------------
# Deferred imports. PyInstaller's analysis does follow imports inside function
# bodies, but every one of these is reached only from inside one, so a change in
# its analyser would silently drop them. They are declared rather than trusted,
# and the list is michspc.selftest's own — the same names the frozen bundle then
# proves it can actually import.
# ---------------------------------------------------------------------------

hiddenimports = list(LAZY_IMPORTS)


# ---------------------------------------------------------------------------
# Windows version resource, built from the one version literal.
# ---------------------------------------------------------------------------


def _version_tuple(text):
    """``"1.2.3"`` -> ``(1, 2, 3, 0)``. A Windows version is four integers.

    A pre-release marker (``1.2.3-dev``) is stripped for the numeric tuple,
    which has nowhere to put it; the full string still goes into the text
    fields, so a developer build says what it is. The release gate refuses to
    build at all while the marker is present (docs/method/METHOD.md section 6),
    so a shipped executable never relies on this.
    """
    numbers = []
    for part in text.split("-")[0].split(".")[:4]:
        numbers.append(int(part) if part.isdigit() else 0)
    while len(numbers) < 4:
        numbers.append(0)
    return tuple(numbers)


from PyInstaller.utils.win32.versioninfo import (  # noqa: E402
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

_numeric = _version_tuple(__version__)

version_resource = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=_numeric,
        prodvers=_numeric,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,  # VOS_NT_WINDOWS32
        fileType=0x1,  # VFT_APP
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",  # US English, Unicode
                    [
                        StringStruct("CompanyName", APP_PUBLISHER),
                        StringStruct("FileDescription", f"{APP_NAME} - {APP_FULL_NAME}"),
                        StringStruct("FileVersion", __version__),
                        StringStruct("InternalName", EXECUTABLE_NAME),
                        StringStruct(
                            "LegalCopyright",
                            "Contains NGS GEOID18 data, a work of the United "
                            "States Government.",
                        ),
                        StringStruct("OriginalFilename", f"{EXECUTABLE_NAME}.exe"),
                        StringStruct("ProductName", f"{APP_NAME} - {APP_FULL_NAME}"),
                        StringStruct("ProductVersion", __version__),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)


# ---------------------------------------------------------------------------
# The bundle. launch.py is a SCRIPT: PyInstaller cannot freeze `-m package`
# (docs/method/TOOLING.md), and the same script is what a source run executes.
# ---------------------------------------------------------------------------

a = Analysis(  # noqa: F821
    [str(REPO_ROOT / "launch.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],  # deliberately empty; see the module docstring
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXECUTABLE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed executables trip antivirus heuristics; not worth it
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_FILE),
    version=version_resource,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=EXECUTABLE_NAME,
)
