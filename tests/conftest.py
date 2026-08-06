"""Shared test helpers.

A job's deliverable is a single ZIP archive (docs/DESIGN.md amendment #17), so
tests that want to inspect what was actually written read members out of it
rather than opening loose files.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest


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
