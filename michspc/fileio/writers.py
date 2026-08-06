"""Atomic file writing.

Two rules, both from docs/method/METHOD.md section 5:

* **Exports never silently clobber.** A write stages to a temporary file beside
  the destination and renames it into place, so an interrupted or failed write
  leaves the previous file intact rather than half-overwritten. Overwriting an
  existing file requires ``overwrite=True``; otherwise it is refused by name.

* **A writer refuses to produce a file its own reader would reject.** The PNEZD
  writer re-reads what it just built and parses it before the file is committed
  to its final name. A malformed export that only fails later, in CAD, on
  someone else's machine, is exactly the failure this prevents.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


class WriteError(Exception):
    """A file could not be written, or would have been unsafe to write."""


@contextlib.contextmanager
def staged_write(path: Path, overwrite: bool = False):
    """Yield a temporary path to write into; rename it onto ``path`` on success.

    The staging file is created in the destination's own directory, because
    ``os.replace`` is only atomic within a filesystem - staging in the system
    temp directory and moving across a drive boundary would silently degrade to
    a copy, and a copy can be interrupted half-written.

    If the body raises, the staged file is removed and the destination is left
    exactly as it was. That is what lets a failed export leave the previous
    job's output intact rather than a truncated replacement.
    """
    path = Path(path)

    if path.exists() and not overwrite:
        raise WriteError(
            f"{path} already exists. Nothing was written. Choose a different "
            f"output folder, or confirm the overwrite."
        )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise WriteError(f"Could not create {path.parent}: {error}") from error

    descriptor, staged_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".partial"
    )
    os.close(descriptor)
    staged = Path(staged_name)

    try:
        yield staged
        os.replace(staged, path)
    except OSError as error:
        with contextlib.suppress(OSError):
            staged.unlink()
        raise WriteError(f"Could not write {path}: {error}") from error
    except BaseException:
        with contextlib.suppress(OSError):
            staged.unlink()
        raise


def atomic_write_text(
    path: Path, content: str, overwrite: bool = False, newline: str = "\r\n"
) -> Path:
    """Write text to ``path`` via a staged temporary file and a rename.

    Windows line endings by default: these files are read by CAD packages and
    opened in Notepad on this platform, and a bare LF still confuses some of
    them.

    The temporary file is created in the destination's own directory, because
    ``os.replace`` is only atomic within a filesystem - staging in the system
    temp directory and moving across a drive boundary would silently degrade to
    a copy.
    """
    path = Path(path)

    if path.exists() and not overwrite:
        raise WriteError(
            f"{path} already exists. Nothing was written. Choose a different "
            f"output folder, or confirm the overwrite."
        )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise WriteError(f"Could not create {path.parent}: {error}") from error

    handle = None
    staged = None
    try:
        handle, staged_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".partial"
        )
        staged = Path(staged_name)
        with os.fdopen(handle, "w", encoding="utf-8", newline=newline) as stream:
            handle = None  # fdopen took ownership
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, path)
        staged = None
    except OSError as error:
        raise WriteError(f"Could not write {path}: {error}") from error
    finally:
        if handle is not None:
            os.close(handle)
        if staged is not None and staged.exists():
            try:
                staged.unlink()
            except OSError:
                pass

    return path


def write_csv_rows(
    path: Path, rows, overwrite: bool = False, delimiter: str = ","
) -> Path:
    """Write already-formatted string rows as CSV.

    Takes strings rather than numbers on purpose: all rounding happens in
    michspc.fileio.formatting, so the file and the screen cannot disagree about
    a value, and no float ever reaches a writer un-formatted.
    """
    lines = []
    for row in rows:
        cells = []
        for cell in row:
            text = "" if cell is None else str(cell)
            if delimiter in text or '"' in text or "\n" in text:
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        lines.append(delimiter.join(cells))

    return atomic_write_text(path, "\n".join(lines) + "\n", overwrite=overwrite)
