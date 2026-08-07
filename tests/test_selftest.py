"""The frozen bundle's self-test, checked from source.

The self-test exists to verify the one artifact the suite cannot run against
(``michspc/selftest.py``). That leaves two things this file has to hold:

1. **It works.** The entry point exists, ``--selftest`` reaches it, and every
   check passes when run from a source checkout. A self-test that has never run
   green from source would fail in the bundle for reasons that have nothing to
   do with the bundle.
2. **It is not vacuous.** Each check is shown failing against a deliberately
   broken program. A gate that cannot fail is not a gate.

And one more, which is really about honesty rather than about the self-test: the
NGS anchors the self-test carries are a **second copy** of numbers that live in
``tests/fixtures/ncat_crosscheck.py``. The bundle cannot import the fixtures, so
the copy is unavoidable; what is avoidable is the two drifting apart, and that is
pinned below with exact equality.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# MUST precede any Qt import (docs/method/TOOLING.md). The self-test builds a
# real QApplication, so importing it into this process needs the offscreen
# platform just as tests/test_gui.py does.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402

from michspc import selftest  # noqa: E402
from michspc.fileio import geoid18  # noqa: E402
from tests.fixtures.ncat_crosscheck import (  # noqa: E402
    CROSSCHECK_FORWARD,
    CROSSCHECK_GEOID,
    CROSSCHECK_POINTS,
    CROSSCHECK_TOLERANCES,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

FORWARD_BY_KEY = {(f.point_id, f.zone_code): f for f in CROSSCHECK_FORWARD}
GEOID_BY_ID = {g.point_id: g for g in CROSSCHECK_GEOID}
POINT_BY_ID = {p.point_id: p for p in CROSSCHECK_POINTS}


# --------------------------------------------------------------------------
# The duplicated anchors are the fixtures' own numbers, exactly.
# --------------------------------------------------------------------------


def test_the_selftests_geoid_anchor_is_the_frozen_ngs_value():
    """Exact equality, not approximate: this is a transcription check.

    ``==`` is right here because the claim is "these are the same number", not
    "these agree to within something". A tolerance would let a genuine
    transcription slip through (docs/method/METHOD.md section 4).
    """
    anchor = GEOID_BY_ID["S2"]

    assert selftest.GEOID_ANCHOR_LATITUDE == anchor.latitude
    assert selftest.GEOID_ANCHOR_LONGITUDE == anchor.longitude
    assert selftest.GEOID_ANCHOR_HEIGHT_M == anchor.geoid_height_m


def test_the_selftests_conversion_anchors_are_the_frozen_ncat_values():
    """Both ends of the frozen end-to-end check, against the fixture.

    The self-test converts the Cadillac point from Michigan South into Michigan
    Central. NCAT computed the position in both zones, so the input and the
    expected output are both NGS figures and neither is anything this program
    produced.
    """
    source = FORWARD_BY_KEY[("S2", selftest.SOURCE_ZONE_CODE)]
    target = FORWARD_BY_KEY[("S2", selftest.TARGET_ZONE_CODE)]

    assert selftest.SOURCE_ZONE_CODE == "2113"
    assert selftest.TARGET_ZONE_CODE == "2112"
    assert selftest.SOURCE_NORTHING_IFT == source.northing_ift
    assert selftest.SOURCE_EASTING_IFT == source.easting_ift
    assert selftest.TARGET_NORTHING_IFT == target.northing_ift
    assert selftest.TARGET_EASTING_IFT == target.easting_ift
    assert selftest.ANCHOR_ELEVATION_M == POINT_BY_ID["S2"].elevation_m


def test_the_selftests_tolerances_are_the_frozen_ones():
    assert selftest.LINEAR_TOLERANCE_M == CROSSCHECK_TOLERANCES["linear_m"]
    assert selftest.GEOID_TOLERANCE_M == CROSSCHECK_TOLERANCES["geoid_m"]


def test_the_end_to_end_tolerance_is_two_ncat_legs_plus_the_written_place():
    """Hand-derived, in the unit the export is written in.

    A zone-to-zone conversion carries an NCAT figure at both ends, so its budget
    is two legs of NCAT's 0.002 m rather than one: 0.004 m. The International
    foot is 0.3048 m exactly, so

        0.004 / 0.3048 = 0.0131233595800524... ft

    and the clean export writes feet to three decimal places, which can move a
    value by half of the last place it keeps, 0.0005 ft:

        0.0131233595800524 + 0.0005 = 0.0136233595800524 ft
    """
    assert selftest._zone_to_zone_tolerance_ift() == pytest.approx(
        0.0136233595800524, abs=1e-15
    )


# --------------------------------------------------------------------------
# It passes from source, through the entry point the executable uses.
# --------------------------------------------------------------------------


def test_every_check_passes_from_source():
    """The whole self-test, in process, with its transcript captured."""
    lines: list[str] = []
    selftest.run_selftest(lines.append)

    passed = [line for line in lines if line.startswith("PASS")]
    assert len(passed) == len(selftest.CHECKS)
    assert not [line for line in lines if line.startswith("FAIL")]


def test_the_launcher_dispatches_selftest_and_reports_it(tmp_path):
    """``launch.py --selftest`` - the exact command line the build gate runs.

    Driven through ``launch.main`` rather than by re-implementing the dispatch,
    because the thing being checked IS the dispatch. The report file is checked
    too: a windowed bundle has no console, so the report is the only place a
    failure could be read from (michspc/selftest.py).
    """
    import launch

    report = tmp_path / "nested" / "selftest.txt"
    exit_code = launch.main(["--selftest", "--report", str(report)])

    assert exit_code == 0
    transcript = report.read_text(encoding="utf-8")
    assert "SELF-TEST PASSED" in transcript
    for name, _check in selftest.CHECKS:
        assert name in transcript


def test_the_launcher_still_opens_the_window_without_the_flag(monkeypatch):
    """The ordinary launch is not disturbed by the new branch."""
    import launch

    called = {}

    def fake_gui_main():
        called["opened"] = True
        return 0

    monkeypatch.setattr("michspc.gui.app.main", fake_gui_main)

    assert launch.main([]) == 0
    assert called == {"opened": True}


def test_the_selftest_runs_as_its_own_process_and_exits_zero(tmp_path):
    """Exit code from the process itself, which is what the build gate reads.

    Run unpiped in the sense that matters: the child's own ``returncode``, not a
    pipeline's (docs/method/TOOLING.md).
    """
    report = tmp_path / "selftest.txt"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "launch.py"),
            "--selftest",
            "--report",
            str(report),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        timeout=300,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "SELF-TEST PASSED" in report.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Anti-vacuousness: each check, shown failing.
# --------------------------------------------------------------------------


def test_the_geoid_check_fails_when_the_tile_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(geoid18, "GEOID18_TILE", tmp_path / "no-such-grid.bin")

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_geoid_grid()
    assert "not in this bundle" in str(raised.value)


def test_the_geoid_check_fails_when_the_height_is_wrong(monkeypatch):
    """The grid loads and authenticates, and still answers wrongly.

    This is the failure the checksum cannot see: a bundle where the tile is
    byte-identical and the program reads it through different code.
    """
    monkeypatch.setattr(
        geoid18, "geoid_height", lambda lat, lon, grid=None: -27.927
    )

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_geoid_grid()
    message = str(raised.value)
    assert "-27.9270" in message
    assert "out by" in message


def test_the_lazy_import_check_fails_on_a_module_that_is_not_there(monkeypatch):
    monkeypatch.setattr(
        selftest,
        "LAZY_IMPORTS",
        selftest.LAZY_IMPORTS + ("michspc.no_such_module",),
    )

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_lazy_imports()
    assert "michspc.no_such_module" in str(raised.value)
    assert "hiddenimports" in str(raised.value)


def test_the_icon_check_fails_when_no_artwork_is_present(tmp_path, monkeypatch):
    from michspc.gui import icon

    monkeypatch.setattr(icon, "GENERATED_ICO", tmp_path / "not-built.ico")
    monkeypatch.setattr(icon, "MASTER_PNG", tmp_path / "no-master.png")

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_icon_resource()
    assert "no application icon" in str(raised.value)


def test_the_icon_check_refuses_the_png_fallback_inside_a_bundle(
    tmp_path, monkeypatch
):
    """A frozen bundle that fell back to the master PNG has lost the build step.

    From source the fallback is correct behaviour - a fresh clone must still
    show the artwork - so the refusal is conditional on being frozen, and that
    condition is what this pins.
    """
    from michspc.gui import icon

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(icon, "GENERATED_ICO", tmp_path / "not-built.ico")

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_icon_resource()
    assert "master artwork" in str(raised.value)


def test_the_end_to_end_check_fails_when_the_coordinate_moves(monkeypatch):
    """Move the expected northing by one foot; the check must notice.

    One foot is chosen because it is far outside the 0.0136 ft budget and far
    inside anything a human would spot by eye in a coordinate that large - the
    class of error this check exists for.
    """
    monkeypatch.setattr(
        selftest, "TARGET_NORTHING_IFT", selftest.TARGET_NORTHING_IFT + 1.0
    )

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_end_to_end_conversion()
    assert "NGS" in str(raised.value)
    assert "out by" in str(raised.value)


def test_the_selftest_main_reports_a_failure_and_exits_nonzero(tmp_path, monkeypatch):
    """The driver, not just the checks: a failure must reach the exit code."""

    def explode():
        raise selftest.SelfTestError("a deliberately broken check")

    monkeypatch.setattr(selftest, "CHECKS", (("broken check", explode),))

    report = tmp_path / "selftest.txt"
    assert selftest.main(["--selftest", "--report", str(report)]) == 1

    transcript = report.read_text(encoding="utf-8")
    assert "a deliberately broken check" in transcript
    assert "SELF-TEST FAILED" in transcript


def test_the_selftest_survives_a_bundle_with_no_console(monkeypatch, tmp_path):
    """``sys.stdout`` is None in a windowed PyInstaller bundle.

    Printing to it raises, and a self-test that crashes while reporting a
    failure reports nothing at all. The report file is what the build gate
    reads in that case, so both halves are checked here.
    """
    monkeypatch.setattr(sys, "stdout", None)

    report = tmp_path / "selftest.txt"
    assert selftest.main(["--selftest", "--report", str(report)]) == 0
    assert "SELF-TEST PASSED" in report.read_text(encoding="utf-8")


def test_an_unwritable_report_path_does_not_fail_a_passing_bundle(tmp_path):
    """The transcript is evidence; the exit code is the verdict.

    Turning a bundle that passed into one that failed because a log file could
    not be written would be the tier sentence applied backwards.
    """
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")

    assert selftest.main(["--selftest", "--report", str(blocker / "report.txt")]) == 0


# --------------------------------------------------------------------------
# The frozen program must find its own data. Both branches.
# --------------------------------------------------------------------------


def test_the_geoid_tile_is_found_beside_the_source_tree_when_not_frozen(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert geoid18._data_directory() == REPO_ROOT / "data"
    assert (REPO_ROOT / "data" / "g2018u3.bin").is_file()


def test_the_geoid_tile_is_found_inside_the_bundle_when_frozen(tmp_path, monkeypatch):
    """PyInstaller sets sys._MEIPASS; nothing else does.

    Without this branch the frozen program resolves its grid by walking up from
    a module path that only exists inside the archive - which happens to land in
    the right place today and is not a property to hold by coincidence.
    """
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert geoid18._data_directory() == tmp_path / "data"


# --------------------------------------------------------------------------
# The spec and the program must agree about where things are.
# --------------------------------------------------------------------------

SPEC_SOURCE = (REPO_ROOT / "michspc.spec").read_text(encoding="utf-8")


def test_the_spec_is_committed_and_freezes_the_launcher_script():
    """PyInstaller freezes a SCRIPT, never ``-m`` (docs/method/TOOLING.md)."""
    assert 'REPO_ROOT / "launch.py"' in SPEC_SOURCE
    assert "-m michspc" not in SPEC_SOURCE


def test_the_spec_reads_the_version_rather_than_restating_it():
    """One version literal in the project, and everything else reads it.

    A spec carrying its own copy is how a shipped binary comes to disagree with
    the tag it was released under (docs/method/TOOLING.md, repo hygiene).
    """
    assert "from michspc import APP_NAME, __version__" in SPEC_SOURCE
    assert '__version__ = "' not in SPEC_SOURCE
    from michspc import __version__

    assert __version__ not in SPEC_SOURCE


def test_the_spec_bundles_the_geoid_tile_where_the_reader_looks():
    """``_data_directory`` reads ``sys._MEIPASS/data``; the spec must put it there."""
    assert 'GEOID_TILE_DESTINATION = "data"' in SPEC_SOURCE
    assert '"g2018u3.bin"' in SPEC_SOURCE


def test_the_spec_bundles_the_icon_where_the_loader_looks():
    """``icon_candidates`` reads ``sys._MEIPASS/assets/icon/<name>``."""
    from michspc.gui import icon

    assert 'ICON_DESTINATION = "assets/icon"' in SPEC_SOURCE

    # And the loader really does look there, so the pin above is about the
    # right path rather than about a string that happens to appear in two
    # files. Checked against the frozen branch of icon_candidates directly.
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(sys, "_MEIPASS", "BUNDLE", raising=False)
        expected = Path("BUNDLE") / "assets" / "icon" / icon.GENERATED_ICO_NAME
        assert icon.icon_candidates()[0] == expected
    finally:
        monkeypatch.undo()


def test_the_spec_declares_every_lazily_imported_module():
    """The spec's hiddenimports and the self-test's list are the same list.

    Two copies of "what is imported late" would drift, and the drift would be
    invisible until a surveyor reached the feature that needs the missing one.
    """
    assert "hiddenimports = list(LAZY_IMPORTS)" in SPEC_SOURCE
    assert "from michspc.selftest import LAZY_IMPORTS" in SPEC_SOURCE
    assert "PySide6.QtWidgets" in selftest.LAZY_IMPORTS
    assert "michspc.fileio.report" in selftest.LAZY_IMPORTS


def test_the_spec_excludes_nothing():
    """docs/method/TOOLING.md: never exclude what a dependency imports lazily.

    The numpy-under-ezdxf trap - the bundle builds, and dies on first use. This
    project has no exclusion worth that risk, so the list is empty and stays
    empty.
    """
    assert "excludes=[]," in SPEC_SOURCE


# --------------------------------------------------------------------------
# The release script's gates.
# --------------------------------------------------------------------------


def test_the_release_gate_refuses_the_current_development_version():
    """The gate that stops a ``-dev`` build, run against the real literal.

    While ``michspc.__version__`` carries its marker this is a live
    demonstration; once the lead drops the marker for a release it becomes the
    ordinary case and the synthetic versions below carry the check.
    """
    from tools import build_release

    if build_release._RELEASE_VERSION.fullmatch(build_release.__version__):
        pytest.skip("the version literal is already a release number")

    with pytest.raises(build_release.BuildError) as raised:
        build_release.gate_version()
    assert "not a plain release number" in str(raised.value)


@pytest.mark.parametrize(
    "version,shippable",
    [
        ("0.1.0", True),
        ("1.0", True),
        ("12.4.7", True),
        ("0.1.0-dev", False),
        ("0.1.0dev", False),
        ("0.1.0-rc1", False),
        ("0.1.0+local", False),
        ("0.1.0 ", False),
        ("v0.1.0", False),
        ("", False),
    ],
)
def test_only_a_plain_number_is_a_shippable_version(version, shippable):
    """A whitelist, because the marker to catch is the one nobody thought of."""
    from tools import build_release

    assert bool(build_release._RELEASE_VERSION.fullmatch(version)) is shippable


def test_the_release_script_writes_its_checksums_last():
    """A build that dies partway must not leave something that reads as a release.

    The checksum file is the marker of completeness, so it is removed at the
    start of a run and written only after the installer exists.
    """
    from tools import build_release

    source = Path(build_release.__file__).read_text(encoding="utf-8")
    gates = source.index("version = gate_version()")
    checksums = source.index("checksums = gate_checksums(")
    installer = source.index("installer = gate_installer(")

    assert gates < installer < checksums
    assert "CHECKSUM_FILE.unlink(missing_ok=True)" in source


def test_the_release_script_runs_the_frozen_selftest_as_a_gate():
    """The bundle's own check is between the build and the installer.

    Not decoration: it is the only step in the whole script that says anything
    about the artifact that ships.
    """
    from tools import build_release

    source = Path(build_release.__file__).read_text(encoding="utf-8")
    build = source.index("gate_bundle()")
    frozen = source.index("gate_frozen_selftest()")
    installer = source.index("installer = gate_installer(")

    assert build < frozen < installer
    assert "--selftest" in source


def test_the_installer_script_freezes_one_appid_and_uses_hka_conventions():
    """docs/method/TOOLING.md: AppId generated once, never changed.

    A new GUID in a later release orphans every existing installation in
    Add/Remove Programs. It is pinned here as a literal so changing it fails the
    suite rather than passing quietly into a release.
    """
    inno = (REPO_ROOT / "installer" / "michspc.iss").read_text(encoding="utf-8")

    assert "AppId={{9D0F57AB-4394-41F2-8164-D40015E7A8B4}" in inno
    # Version comes in from the build script; the installer never restates it.
    assert "AppVersion={#AppVersion}" in inno
    from michspc import __version__

    assert f"AppVersion={__version__}" not in inno
    # autopf/autoprograms/autodesktop are the HKA-equivalent constants for a
    # per-user-or-admin install; a hardcoded Program Files path or HKLM write
    # fails outright in a per-user install.
    assert "{autopf}" in inno
    assert "{autoprograms}" in inno
    assert "PrivilegesRequiredOverridesAllowed=dialog" in inno
