"""Where the Options are remembered between runs, behind a seam (plan L9, O3).

**The one place this program persists anything**, and it persists exactly
three facts: which groups the system lists show, the Auto zone frame, and
WHERE the observation date comes from. Never a date itself (plan O3: "the
choice is remembered; the date is not"), never a zone, a unit, a file or a
folder - those are answered per job, in words on the screen, before Convert.

In production the store is ``QSettings`` in its native format, per user:
``HKCU\\Software\\DMARTIN\\MCX - Martin Coordinate Exchange`` on Windows
(organisation ``APP_PUBLISHER``, application the window title). The suite
must never read or write the owner's real registry - a test that passed or
failed on his saved options would be measuring his machine, not the program
(recon section 5) - so every window asks ``default_store()``, and the suite's
conftest installs ``MemoryStore`` as the factory before any test runs. A test
pins that the production factory is not the one installed, and that it was
never called (``PRODUCTION_STORES_BUILT``).

**No Qt import at module level**, deliberately: tests/conftest.py imports
this module for every test in the suite, most of which never touch Qt, and
``QSettings`` is imported only when a production store is actually built.

The stored values are strings, read back strictly by ``options.load_options``
(the "loaders validate as strictly as the UI" rule): anything it does not
recognise falls back to that key's default and says so on the status line.
"""

from __future__ import annotations

from michspc import APP_FULL_NAME, APP_NAME, APP_PUBLISHER

ORGANIZATION = APP_PUBLISHER
APPLICATION = f"{APP_NAME} - {APP_FULL_NAME}"
"""The two names ``QSettings`` keys the native store by. ``APPLICATION`` is
the window title's own derivation (``window.WINDOW_TITLE``; a test pins the
two equal), which is also what ``app.build_application`` names the
application, so the key is the one the plan states (L9)."""


class MemoryStore:
    """A store that lives in a dict: the suite's, and the offscreen previews'."""

    def __init__(self, values: dict | None = None) -> None:
        self.values: dict[str, object] = dict(values or {})

    def get(self, key: str):
        return self.values.get(key)

    def put(self, key: str, value: str) -> None:
        self.values[key] = value


class QSettingsStore:
    """``QSettings`` behind the two-method store interface.

    ``ini_path`` None is the production store (native format, user scope);
    a path makes an INI-file store, which is how the suite tests this adapter
    without going near the registry.
    """

    def __init__(self, ini_path=None) -> None:
        from PySide6.QtCore import QSettings

        if ini_path is None:
            self._settings = QSettings(
                QSettings.Format.NativeFormat,
                QSettings.Scope.UserScope,
                ORGANIZATION,
                APPLICATION,
            )
        else:
            self._settings = QSettings(str(ini_path), QSettings.Format.IniFormat)

    def get(self, key: str):
        return self._settings.value(key)

    def put(self, key: str, value: str) -> None:
        self._settings.setValue(key, value)
        self._settings.sync()


PRODUCTION_STORES_BUILT = 0
"""How many times ``production_store`` has run in this process. The suite pins
it at zero: a nonzero count under pytest means a test reached the owner's
real registry."""


def production_store() -> QSettingsStore:
    """The owner's real, per-user store. Never built under the suite."""
    global PRODUCTION_STORES_BUILT
    PRODUCTION_STORES_BUILT += 1
    return QSettingsStore()


_factory = production_store


def store_factory():
    """The factory ``default_store`` calls - ``production_store`` outside tests."""
    return _factory


def set_store_factory(factory):
    """Install ``factory`` as what ``default_store`` calls; returns the previous one."""
    global _factory
    previous = _factory
    _factory = factory
    return previous


def default_store():
    """The store a window reads its Options from when none is handed in."""
    return _factory()
