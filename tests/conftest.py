"""Shared test helpers.

A job's deliverable is a single ZIP archive (docs/DESIGN.md amendment #17), so
tests that want to inspect what was actually written read members out of it
rather than opening loose files.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from michspc.gui import settings_store

# The Options store (plan L9, DESIGN.md #71): EVERY window this suite builds
# reads and writes an in-memory store, never the owner's real per-user
# registry key. Installed at import, before any test module is collected, so
# a window built at module level is covered too; each call returns a fresh
# empty store, so every window opens on the defaults. Pinned by
# tests/test_gui_options.py::test_the_suite_never_builds_the_real_store.
settings_store.set_store_factory(settings_store.MemoryStore)


def wgs84_build_store() -> settings_store.MemoryStore:
    """A store holding the Options the WGS 84 build's GUI tests were written under.

    Those tests (W5, DESIGN.md #70) pin the five WGS 84 / ITRF entries in the
    lists and the observation date box on the tab. Since the Options build
    (DESIGN.md #71) both are Options - the five groups off by default and
    "Today" as the date source - so their fixtures switch the five ON and the
    date to "Enter a date on the tab" through the Options seam itself (a
    remembered store, read by the window as the owner's would be), and every
    assertion they make stands unweakened. Imported lazily: the options module
    imports Qt, and most of the suite never does.
    """
    from michspc.gui import options
    from michspc.job import ObservationDateSource

    time_dependent = [
        group
        for group in options.LIST_GROUPS
        if not group.is_zone_group and group.frame.is_time_dependent
    ]
    chosen = options.Options(
        shown=options.DEFAULT_OPTIONS.with_groups(*time_dependent).shown,
        auto_frame=options.DEFAULT_AUTO_FRAME,
        date_source=ObservationDateSource.ENTERED,
    )
    store = settings_store.MemoryStore()
    options.save_options(store, chosen)
    return store


def archive_members(archive: Path) -> dict[str, str]:
    """Every member of a written export, decoded, keyed by name.

    Reads through zipfile rather than trusting a path convention, so a test
    asserting "the export contains X" is asserting about the file on disk and
    not about how the test thinks the file was named.
    """
    with zipfile.ZipFile(archive) as handle:
        return {
            name: handle.read(name).decode("utf-8") for name in handle.namelist()
        }


def member_text(archive: Path, suffix: str) -> str:
    """The one member whose name ends with ``suffix``.

    Fails loudly on zero or several matches rather than silently picking one,
    since a test that reads the wrong member would still pass for the wrong
    reason.
    """
    members = archive_members(archive)
    matches = [name for name in members if name.endswith(suffix)]
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one member ending {suffix!r} in {archive.name}, "
            f"found {matches or 'none'} among {sorted(members)}"
        )
    return members[matches[0]]


def extract_member(archive: Path, suffix: str, into: Path) -> Path:
    """Write one member out to a real file and return its path.

    This is what the surveyor actually does with the export - unzip it, then
    hand the PNEZD file to CAD - so tests that check the export round-trips
    through this program's own reader go the same way rather than parsing the
    text in memory.
    """
    members = archive_members(archive)
    matches = [name for name in members if name.endswith(suffix)]
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one member ending {suffix!r} in {archive.name}, "
            f"found {matches or 'none'} among {sorted(members)}"
        )
    into.mkdir(parents=True, exist_ok=True)
    destination = into / matches[0]
    destination.write_text(members[matches[0]], encoding="utf-8", newline="")
    return destination


@pytest.fixture
def read_member():
    """Fixture form of ``member_text``, for readability in test bodies."""
    return member_text


# The two record lines that carry an absolute path (michspc/fileio/report.py,
# "File" and "Folder"). Their 19-character label column is the report's own.
_PATH_LINE_LABELS = ("File               ", "Folder             ")


def record_root_normalised(text: str, root: Path) -> str:
    r"""``text`` with the temporary ``root`` replaced by ``<ROOT>``, and the
    remaining separators on the File and Folder lines written as ``/``.

    The record digests in the suite were frozen on Linux, where the path
    below the root is ``<ROOT>/job/in.csv``; on Windows the same record says
    ``<ROOT>\job\in.csv``. That difference is the platform's path spelling,
    not the program's output, so it is normalised - but ONLY on the two lines
    that carry a path, and only on lines that begin with the label followed
    by ``<ROOT>``: a backslash anywhere else in a record is still compared
    exactly. On Linux this is a no-op (a POSIX path has no backslash), so the
    frozen digests are compared there exactly as before.
    """
    text = text.replace(str(root), "<ROOT>")
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if line.startswith(tuple(label + "<ROOT>" for label in _PATH_LINE_LABELS)):
            lines[index] = line.replace("\\", "/")
    return "\n".join(lines)
