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
from michspc.fileio import geoid  # noqa: E402
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


def test_the_selftests_vertcon_anchor_is_the_frozen_ncat_value():
    """The transcription check for the VERTCON anchor, same rule as the geoid's.

    ``anchor-22`` is DESIGN.md #22's anchor: 200.000 m NGVD 29 at
    43.0 N / 84.5 W converts to 199.860 m NAVD 88 per NCAT, so the shift is
    199.860 - 200.000 = -0.140 m. Rounded at the transcription, not in the
    check: both NCAT figures are printed to the millimetre, so their
    difference is exact at that precision.
    """
    from tests.fixtures.vertcon_anchors import NGVD29_TO_NAVD88_ANCHORS

    anchor = next(a for a in NGVD29_TO_NAVD88_ANCHORS if a.name == "anchor-22")

    assert selftest.VERTCON_ANCHOR_LATITUDE == anchor.latitude
    assert selftest.VERTCON_ANCHOR_LONGITUDE == anchor.longitude
    assert selftest.VERTCON_ANCHOR_SHIFT_M == round(
        anchor.target_height_m - anchor.source_height_m, 3
    )
    # The whole-job check's two ends (WP-V9): both are the fixture's own NCAT
    # figures, transcribed exactly.
    assert selftest.VERTCON_ANCHOR_SOURCE_HEIGHT_M == anchor.source_height_m
    assert selftest.VERTCON_ANCHOR_TARGET_HEIGHT_M == anchor.target_height_m


def test_the_vertical_conversion_check_fails_on_a_wrong_height(monkeypatch):
    """The bundle gate can see a wrong shift, not merely a missing module.

    Seeded with the sign-flipped outcome - the exact defect class #35 pinned
    before the reader existed - by pointing the expected value at it: the
    check must fail loudly, naming both figures.
    """
    monkeypatch.setattr(selftest, "VERTCON_ANCHOR_TARGET_HEIGHT_M", 200.140)

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_vertical_conversion()
    message = str(raised.value)
    assert "out by" in message
    assert "200.140" in message


def test_the_selftests_geoid12b_anchor_is_the_frozen_ngs_value():
    """The transcription check for the GEOID12B anchor, same rule as GEOID18's.

    ``==`` because the claim is "these are the same number", not "these agree
    to within something" (docs/method/METHOD.md section 4). The position is
    NOT the S2 crosscheck point: the GEOID12B lattice reuses the GEOID18
    ANCHOR positions (44.2542 N), where S2 sits at 44.252 N, and a tolerance
    here would have let that near-miss transcription slip through.
    """
    from tests.fixtures.geoid12b_anchors import GEOID12B_ANCHORS

    anchor = next(
        a
        for a in GEOID12B_ANCHORS
        if (a.latitude, a.longitude)
        == (selftest.GEOID12B_ANCHOR_LATITUDE, selftest.GEOID12B_ANCHOR_LONGITUDE)
    )

    assert selftest.GEOID12B_ANCHOR_LATITUDE == anchor.latitude
    assert selftest.GEOID12B_ANCHOR_LONGITUDE == anchor.longitude
    assert selftest.GEOID12B_ANCHOR_HEIGHT_M == anchor.geoid_height_m


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


def test_the_check_registry_holds_every_check_by_name():
    """A deleted CHECKS entry must fail a test, not merely shrink a tuple.

    Both tests that touch CHECKS are self-referential - they count or iterate
    whatever the tuple holds - so removing any single check left the suite
    green while the release notes went on claiming the bundle runs it
    (closing gate, MEDIUM 2; the DESIGN.md #38 finding-2 discipline, applied
    to this registry). The full ordered list is pinned: adding a check
    updates this list consciously, deleting one fails it. Falsified by
    removing the vertical-conversion entry: this test alone fails.
    """
    assert [name for name, _check in selftest.CHECKS] == [
        "version and application name",
        "bundled GEOID18 grid",
        "bundled VERTCON 3.0 grid pair",
        "vertical conversion against NGS NCAT",
        "bundled GEOID12B tile",
        "lazily imported dependencies",
        "Qt startup and bundled icon",
        "end-to-end conversion against NGS NCAT",
    ]


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
    monkeypatch.setattr(geoid, "GEOID18_TILE", tmp_path / "no-such-grid.bin")

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_geoid_grid()
    assert "not in this bundle" in str(raised.value)


def test_the_geoid_check_fails_when_the_height_is_wrong(monkeypatch):
    """The grid loads and authenticates, and still answers wrongly.

    This is the failure the checksum cannot see: a bundle where the tile is
    byte-identical and the program reads it through different code.
    """
    monkeypatch.setattr(
        geoid, "geoid_height", lambda lat, lon, grid=None: -27.927
    )

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_geoid_grid()
    message = str(raised.value)
    assert "-27.9270" in message
    assert "out by" in message


def test_the_vertcon_check_fails_when_a_grid_is_missing(tmp_path, monkeypatch):
    from michspc.fileio import vertcon

    monkeypatch.setattr(vertcon, "VERTCON3_TRN_TILE", tmp_path / "no-such-grid.b")

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_vertcon_grids()
    assert "not in this bundle" in str(raised.value)


def test_the_vertcon_check_fails_when_the_shift_is_wrong(monkeypatch):
    """The pair loads and authenticates, and still answers wrongly.

    The failure the checksums cannot see: byte-identical grids read through
    different code. The seeded value is the shift with its sign flipped - the
    exact defect class DESIGN.md #35 pinned before the reader existed.
    """
    from michspc.fileio import vertcon

    class WrongPair:
        def reading_at(self, latitude, longitude):
            return (0.140, 0.001)

    monkeypatch.setattr(vertcon, "load_shipped_grids", lambda: WrongPair())
    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_vertcon_grids()
    message = str(raised.value)
    assert "0.1400" in message
    assert "out by" in message


def test_the_geoid12b_check_fails_when_the_tile_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(geoid, "GEOID12B_TILE", tmp_path / "no-such-grid.bin")

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_geoid12b_tile()
    assert "not in this bundle" in str(raised.value)


def test_the_geoid12b_check_fails_on_a_tampered_tile(tmp_path, monkeypatch):
    """One flipped payload byte must fail the digest.

    This is the bundle-side twin of the suite's data/ pin: until this check,
    a GEOID12B tile corrupted during packaging passed every release gate,
    because the digest was only ever checked against the source tree
    (independent review of the vertical branch, MEDIUM 3).
    """
    tampered = bytearray(geoid.GEOID12B_TILE.read_bytes())
    tampered[100] ^= 0xFF
    path = tmp_path / "g2012bu3.bin"
    path.write_bytes(bytes(tampered))
    monkeypatch.setattr(geoid, "GEOID12B_TILE", path)

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_geoid12b_tile()
    assert "does not match" in str(raised.value)


def test_the_geoid12b_check_fails_when_the_height_is_wrong(monkeypatch):
    """The tile loads and authenticates, and still answers wrongly.

    The failure the checksum cannot see: a byte-identical tile read through
    different code - the same class the GEOID18 check's wrong-height test
    covers. (A swapped TILE is not this check's to catch: at the anchor
    position the two models differ by only 1.2 mm, inside the 2 mm tolerance.
    The suite's anti-swap pin in test_geoid.py holds that line, across the 18
    of 20 anchor positions where the models differ at the printed millimetre.)
    """
    monkeypatch.setattr(
        geoid, "geoid_height", lambda lat, lon, grid=None: -33.796
    )

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_geoid12b_tile()
    message = str(raised.value)
    assert "-33.7960" in message
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


def test_the_grids_are_found_beside_the_source_tree_when_not_frozen(monkeypatch):
    from michspc.fileio import ngs_grid

    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert ngs_grid.shipped_data_directory() == REPO_ROOT / "data"
    assert (REPO_ROOT / "data" / "g2018u3.bin").is_file()

    # Both policy layers resolve their files under the one shared locator -
    # the private copies each carried were extracted at the #38 merge gate.
    from michspc.fileio import vertcon

    assert geoid.GEOID18_TILE.parent == geoid.DATA_DIR
    assert vertcon.VERTCON3_TRN_TILE.parent == vertcon.DATA_DIR


def test_the_grids_are_found_inside_the_bundle_when_frozen(tmp_path, monkeypatch):
    """PyInstaller sets sys._MEIPASS; nothing else does.

    Without this branch the frozen program resolves its grids by walking up
    from a module path that only exists inside the archive - which happens to
    land in the right place today and is not a property to hold by coincidence.
    """
    from michspc.fileio import ngs_grid

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert ngs_grid.shipped_data_directory() == tmp_path / "data"


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
    # The rule is that the version is IMPORTED, not that the import line has a
    # particular shape - pinning the whole import list made this fail when the
    # 0.2.0 rename added APP_FULL_NAME and APP_PUBLISHER beside it, which is a
    # false alarm about a real rule.
    assert "from michspc import " in SPEC_SOURCE
    assert "__version__" in SPEC_SOURCE.split("\n\n")[0] or "__version__" in SPEC_SOURCE
    assert '__version__ = "' not in SPEC_SOURCE
    from michspc import __version__

    assert __version__ not in SPEC_SOURCE


def test_the_spec_bundles_the_geoid_tile_where_the_reader_looks():
    """``shipped_data_directory`` reads ``sys._MEIPASS/data``; the spec must put it there.

    The filename itself is no longer a literal in the spec - since WP-V5 the
    spec derives every geoid filename from ``geoid.ALL_GEOID_MODELS`` - so this
    pins the derivation and checks the record it derives from still names the
    tile the reader looks for.
    """
    assert 'DATA_DESTINATION = "data"' in SPEC_SOURCE
    assert "tile_filename for model in ALL_GEOID_MODELS" in SPEC_SOURCE
    assert "from michspc.fileio.geoid import ALL_GEOID_MODELS" in SPEC_SOURCE
    assert geoid.GEOID18_MODEL.tile_filename == "g2018u3.bin"
    assert geoid.GEOID18_TILE.name == "g2018u3.bin"


def test_the_spec_bundles_every_ngs_grid_the_source_tree_carries():
    """Every file in ``data/`` must be carried by the spec's derived list.

    ``data/`` holds exactly the NGS grids this program ships. Since WP-V5 the
    spec does not restate their names: it derives the geoid filenames from
    ``geoid.ALL_GEOID_MODELS`` and the VERTCON pair from the vertcon module's
    own tile constants, so a third geoid model cannot be added to the registry
    without the bundle following. This test holds the other direction - a file
    added to ``data/`` that no registry record and no vertcon constant names
    would build a bundle that looks complete and refuses the first job that
    needs it - and pins that the spec actually derives rather than restates.

    ``tools/build_release.py`` makes the equivalent comparison against the
    *built* bundle. This one fails in the suite, seconds after the omission,
    rather than twenty minutes into a release build.
    """
    from michspc.fileio import vertcon

    derived = {model.tile_filename for model in geoid.ALL_GEOID_MODELS} | {
        vertcon.VERTCON3_TRN_TILE.name,
        vertcon.VERTCON3_ERR_TILE.name,
    }
    on_disk = {
        source.name for source in (REPO_ROOT / "data").iterdir() if source.is_file()
    }
    assert on_disk == derived, (
        f"data/ and the registries disagree about what ships: only in data/ "
        f"{sorted(on_disk - derived)}, only in the registries "
        f"{sorted(derived - on_disk)}."
    )

    # And the spec builds its list from those same sources, not from a copy.
    assert "tile_filename for model in ALL_GEOID_MODELS" in SPEC_SOURCE
    assert "VERTCON3_TRN_TILE.name" in SPEC_SOURCE
    assert "VERTCON3_ERR_TILE.name" in SPEC_SOURCE


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

    # Comment lines are stripped first. The file documents the ISCC command in
    # a header comment, and that example necessarily shows a literal version -
    # which collided with this assertion the moment the version literal became
    # the same string the example used, failing the release gate on a comment.
    # The rule being enforced is about DIRECTIVES: no Inno directive may carry
    # a version this program would otherwise have to keep in step by hand.
    directives = "\n".join(
        line for line in inno.splitlines() if not line.lstrip().startswith(";")
    )
    assert f"AppVersion={__version__}" not in directives
    # autopf/autoprograms/autodesktop are the HKA-equivalent constants for a
    # per-user-or-admin install; a hardcoded Program Files path or HKLM write
    # fails outright in a per-user install.
    assert "{autopf}" in inno
    assert "{autoprograms}" in inno
    assert "PrivilegesRequiredOverridesAllowed=dialog" in inno
