"""Architectural boundaries, enforced by AST scan rather than by comment.

A layering rule that lives only in prose decays. These scans read the actual
import statements of every shipped module and fail the suite when a boundary is
crossed.

Each rule is paired with an **anti-vacuousness check** that runs the same
scanner against synthetic source containing the violation, proving the scanner
can actually see one. A scanner that cannot fail proves nothing, and a suite
full of scanners that silently pass everything is worse than no scanners at all.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "michspc"

# Modules the computation core is forbidden to depend on. PySide6 because the
# core must remain usable headless and testable without a display; the file and
# format modules because reading and writing belong to michspc.fileio, which
# owns every external format (docs/DESIGN.md section 9).
CORE_FORBIDDEN_IMPORTS = frozenset(
    {
        "PySide6",
        "shiboken6",
        "csv",
        "struct",
        "json",
        "sqlite3",
        "pickle",
        "urllib",
        "requests",
        "socket",
        "pyproj",
        "numpy",
    }
)

# The file layer may read and write, but must not reach up into the interface.
FILEIO_FORBIDDEN_IMPORTS = frozenset({"PySide6", "shiboken6"})


def python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def imported_top_level_names(source: str, filename: str) -> set[str]:
    """Every top-level module name this source imports.

    ``import a.b.c`` and ``from a.b import c`` both yield ``a``. Relative
    imports yield nothing, since they cannot cross a package boundary upward.
    """
    tree = ast.parse(source, filename=filename)
    names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import, stays inside the package
                continue
            if node.module:
                names.add(node.module.split(".")[0])

    return names


def imported_dotted_paths(source: str, filename: str) -> set[str]:
    """Full dotted module paths, for checking intra-package layering."""
    tree = ast.parse(source, filename=filename)
    paths: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                paths.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and not node.level:
                paths.add(node.module)

    return paths


# --------------------------------------------------------------------------
# The core is pure.
# --------------------------------------------------------------------------


def test_computation_core_imports_no_forbidden_module():
    """michspc/spc/** is stdlib-only computation.

    No Qt, no file formats, no network, no third-party geodesy. This is what
    lets the core be tested exhaustively without a display or a filesystem, and
    what keeps every number traceable to the manual rather than to a library.
    """
    violations = []
    for path in python_files(PACKAGE_ROOT / "spc"):
        names = imported_top_level_names(path.read_text(encoding="utf-8"), str(path))
        for forbidden in sorted(names & CORE_FORBIDDEN_IMPORTS):
            violations.append(f"{path.relative_to(REPO_ROOT)} imports {forbidden}")

    assert not violations, "computation core reached outside itself:\n" + "\n".join(
        violations
    )


def test_computation_core_does_not_import_the_outer_layers():
    """The core must not know that file I/O or a GUI exist."""
    violations = []
    for path in python_files(PACKAGE_ROOT / "spc"):
        paths = imported_dotted_paths(path.read_text(encoding="utf-8"), str(path))
        for dotted in sorted(paths):
            if dotted.startswith(("michspc.fileio", "michspc.gui")):
                violations.append(f"{path.relative_to(REPO_ROOT)} imports {dotted}")

    assert not violations, "computation core imported an outer layer:\n" + "\n".join(
        violations
    )


def test_file_layer_does_not_import_the_interface():
    """michspc/fileio/** must be usable without Qt."""
    violations = []
    for path in python_files(PACKAGE_ROOT / "fileio"):
        source = path.read_text(encoding="utf-8")
        names = imported_top_level_names(source, str(path))
        for forbidden in sorted(names & FILEIO_FORBIDDEN_IMPORTS):
            violations.append(f"{path.relative_to(REPO_ROOT)} imports {forbidden}")
        for dotted in sorted(imported_dotted_paths(source, str(path))):
            if dotted.startswith("michspc.gui"):
                violations.append(f"{path.relative_to(REPO_ROOT)} imports {dotted}")

    assert not violations, "file layer reached into the interface:\n" + "\n".join(
        violations
    )


def test_shipped_code_never_imports_the_test_tree():
    """Verification fixtures must not become production data.

    tests/fixtures holds Appendix C's published derived constants and NGS's NCAT
    results. Their entire value is being an independent check; if shipped code
    imported them they would become a second authoritative representation of
    facts the core derives for itself (docs/DESIGN.md section 7).
    """
    violations = []
    for path in python_files(PACKAGE_ROOT):
        source = path.read_text(encoding="utf-8")
        names = imported_top_level_names(source, str(path))
        if "tests" in names:
            violations.append(str(path.relative_to(REPO_ROOT)))

    assert not violations, "shipped code imported the test tree:\n" + "\n".join(
        violations
    )


# --------------------------------------------------------------------------
# Naming.
# --------------------------------------------------------------------------


def test_no_package_shadows_a_standard_library_module():
    """A package named io/ shadows the stdlib (docs/method/TOOLING.md).

    The file layer is named ``fileio`` for exactly this reason. This checks the
    whole package tree rather than that one case, so the next such collision is
    caught when it is introduced rather than when it breaks something.
    """
    stdlib = set(sys.stdlib_module_names)
    # Names we accept: the distribution package itself, and subpackage names
    # that are not stdlib modules.
    violations = []
    for path in PACKAGE_ROOT.rglob("__init__.py"):
        if "__pycache__" in path.parts:
            continue
        package_name = path.parent.name
        if package_name == "michspc":
            continue
        if package_name in stdlib:
            violations.append(
                f"{path.parent.relative_to(REPO_ROOT)} shadows the stdlib "
                f"module {package_name!r}"
            )

    assert not violations, "\n".join(violations)


def test_production_code_contains_no_load_bearing_asserts():
    """The suite runs under -O, which strips assert statements entirely.

    An assert in shipped code is therefore a check that silently vanishes in one
    of the two modes this program must be correct in. Validation uses if/raise
    (docs/method/METHOD.md section 4).
    """
    violations = []
    for path in python_files(PACKAGE_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno} uses assert"
                )

    assert not violations, (
        "assert statements in shipped code are stripped by -O:\n"
        + "\n".join(violations)
    )


def test_no_source_file_carries_a_utf8_byte_order_mark():
    """PowerShell 5.1 writes a BOM by default, and a BOM breaks ast.parse.

    Earned the hard way: a PowerShell edit to zones.py prepended U+FEFF, which
    Python's importer tolerates (it reads source as utf-8-sig) but ast.parse on
    utf-8 text does not - so the architecture scanners above blew up while the
    program itself still ran. That is the worst kind of failure: the checks
    break while the thing they check appears fine.

    docs/method/TOOLING.md flags Set-Content's ANSI/BOM defaults; this makes the
    rule machine-enforced rather than remembered.
    """
    offenders = []
    for path in sorted(REPO_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts or ".git" in path.parts:
            continue
        head = path.read_bytes()[:3]
        if head == b"\xef\xbb\xbf":
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, (
        "byte order marks found - rewrite these files as UTF-8 without BOM:\n"
        + "\n".join(offenders)
    )


# --------------------------------------------------------------------------
# Anti-vacuousness: prove each scanner can actually see a violation.
# --------------------------------------------------------------------------


def test_bom_scanner_detects_a_byte_order_mark(tmp_path):
    """The scanner above, run against a file that genuinely has one."""
    good = tmp_path / "clean.py"
    good.write_bytes(b'"""ok."""\n')
    bad = tmp_path / "marked.py"
    bad.write_bytes(b"\xef\xbb\xbf" + b'"""not ok."""\n')

    assert good.read_bytes()[:3] != b"\xef\xbb\xbf"
    assert bad.read_bytes()[:3] == b"\xef\xbb\xbf"

    # And confirm the failure mode that motivated the rule: ast.parse chokes on
    # BOM-prefixed text read as plain utf-8.
    with pytest.raises(SyntaxError):
        ast.parse(bad.read_text(encoding="utf-8"), filename=str(bad))
    ast.parse(good.read_text(encoding="utf-8"), filename=str(good))


def test_import_scanner_detects_a_plain_import():
    source = "import PySide6\n"
    assert "PySide6" in imported_top_level_names(source, "<synthetic>")


def test_import_scanner_detects_a_dotted_import():
    source = "import PySide6.QtWidgets\n"
    assert "PySide6" in imported_top_level_names(source, "<synthetic>")


def test_import_scanner_detects_a_from_import():
    source = "from PySide6.QtWidgets import QApplication\n"
    assert "PySide6" in imported_top_level_names(source, "<synthetic>")


def test_import_scanner_detects_an_import_nested_inside_a_function():
    """A deferred import is still a dependency.

    ast.walk descends into function bodies, so an import hidden inside a
    function to dodge a layering rule is still caught.
    """
    source = "def render():\n    import PySide6\n    return PySide6\n"
    assert "PySide6" in imported_top_level_names(source, "<synthetic>")


def test_import_scanner_detects_an_aliased_import():
    source = "import PySide6 as qt\n"
    assert "PySide6" in imported_top_level_names(source, "<synthetic>")


def test_import_scanner_ignores_relative_imports():
    """Relative imports cannot cross upward out of a package, so they are safe.

    Checked so the scanner's silence on them is a deliberate property rather
    than an accident nobody noticed.
    """
    source = "from . import lambert\nfrom .zones import MI_SOUTH\n"
    assert imported_top_level_names(source, "<synthetic>") == set()


def test_dotted_path_scanner_detects_a_layering_violation():
    source = "from michspc.fileio.pnezd import read\n"
    assert "michspc.fileio.pnezd" in imported_dotted_paths(source, "<synthetic>")


def test_assert_scanner_detects_an_assert():
    """The scanner used by test_production_code_contains_no_load_bearing_asserts."""
    tree = ast.parse("def f(x):\n    assert x > 0\n    return x\n")
    found = [n for n in ast.walk(tree) if isinstance(n, ast.Assert)]
    assert len(found) == 1


def test_assert_scanner_detects_an_assert_nested_in_a_class_method():
    tree = ast.parse("class C:\n    def m(self):\n        assert False\n")
    found = [n for n in ast.walk(tree) if isinstance(n, ast.Assert)]
    assert len(found) == 1


def test_the_scanners_actually_saw_some_files():
    """Guard against the whole suite passing because it scanned nothing.

    If a refactor moved the package or broke the path arithmetic above, every
    scan would iterate over an empty list and report success. This makes that
    failure mode loud.
    """
    core_files = python_files(PACKAGE_ROOT / "spc")
    all_files = python_files(PACKAGE_ROOT)

    assert len(core_files) >= 6, f"only found {len(core_files)} core modules"
    assert len(all_files) >= 9, f"only found {len(all_files)} package modules"
    assert (PACKAGE_ROOT / "spc" / "lambert.py") in core_files
