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


def test_the_selftests_spcs2022_anchor_is_the_frozen_beta_ncat_value():
    """The transcription check for the SPCS2022 anchor. Exact, like the rest.

    The bundle cannot import ``tests/``, so its SPCS2022 anchor is a second
    copy of one row of ``tests/fixtures/spcs2022_engine_anchors.py``. The copy
    is beta-derived, which is why ``michspc/selftest.py`` carries the ``NGS
    beta`` token and appears in docs/REFREEZE-NSRS.md - re-freezing the fixture
    without re-freezing this would leave the shipped bundle checking itself
    against a superseded number.

    ``==`` because the claim is "these are the same number", not "these agree
    to within something" (docs/method/METHOD.md section 4).
    """
    from tests.fixtures.spcs2022_engine_anchors import SPCS2022_PROJECTION_ANCHORS

    anchor = next(
        a
        for a in SPCS2022_PROJECTION_ANCHORS
        if a.zone_code == selftest.SPCS2022_ZONE_CODE
        and a.label == "origin -0.15/-0.25"
    )

    assert selftest.SPCS2022_ZONE_CODE == "261008"
    assert selftest.SPCS2022_ANCHOR_LATITUDE == anchor.latitude
    assert selftest.SPCS2022_ANCHOR_LONGITUDE == anchor.longitude
    assert selftest.SPCS2022_ANCHOR_NORTHING_M == anchor.northing_m
    assert selftest.SPCS2022_ANCHOR_EASTING_M == anchor.easting_m
    assert selftest.SPCS2022_ANCHOR_SCALE_FACTOR == anchor.scale_factor


def test_the_selftests_spcs2022_anchor_is_not_a_zone_origin():
    """An origin reproduces the false origin without projecting anything.

    Zone 261008's origin is published at N 228,600 m / E 1,409,700 m, and an
    engine that returned the false origin for every input would satisfy a check
    written at the origin. The self-test's anchor must therefore be one of the
    off-origin points - stated here rather than left to the reader of a
    latitude.
    """
    zone = selftest_zone(selftest.SPCS2022_ZONE_CODE)

    assert selftest.SPCS2022_ANCHOR_LATITUDE != zone.definition.lat_origin
    assert selftest.SPCS2022_ANCHOR_LONGITUDE != zone.definition.lon_origin
    assert (
        selftest.SPCS2022_ANCHOR_NORTHING_M != zone.definition.northing_grid_origin
    )
    assert selftest.SPCS2022_ANCHOR_EASTING_M != zone.definition.easting_origin


def test_the_selftests_spcs2022_tolerances_are_the_frozen_printed_ones():
    from tests.fixtures.spcs2022_engine_anchors import SPCS2022_PRINTED

    assert selftest.SPCS2022_LINEAR_TOLERANCE_M == SPCS2022_PRINTED["linear_m"]
    assert selftest.SPCS2022_SCALE_TOLERANCE == SPCS2022_PRINTED["scale_factor"]


def selftest_zone(code):
    from michspc.spc.zones import zone_by_code

    return zone_by_code(code)


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
        "ellipsoid height conversion",
        "lazily imported dependencies",
        "Qt startup and bundled icon",
        "end-to-end conversion against NGS NCAT",
        "SPCS2022 conversion against beta NGS NCAT",
        "cross-frame refusal",
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


def michspc_modules_imported_inside_function_bodies() -> dict[str, set[str]]:
    """Every ``michspc`` module imported from inside a function body, by file.

    The audit ``LAZY_IMPORTS`` used to be: a person reading the tree and
    remembering to add what they found. That is how the VERTCON data came to
    ship with no reader in the bundle (docs/DESIGN.md #38), and how the three
    projection engines would have shipped as a dispatcher with no mathematics.
    This walks the syntax tree instead.

    An import inside a function body is invisible to PyInstaller unless the
    spec declares it, so every one of these must be in ``LAZY_IMPORTS`` - which
    ``michspc.spec`` uses as its ``hiddenimports`` and which the frozen bundle
    then proves it can actually import.

    ``michspc/selftest.py`` is excluded, and the exclusion is the point rather
    than a convenience: its own deferred imports are executed by the checks
    themselves, so one missing from a bundle fails the self-test directly and
    by name. Everything else in the program is imported at a moment no gate is
    watching.
    """
    import ast
    import importlib.util

    def resolves_to_a_module(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, AttributeError, ValueError):
            return False

    found: dict[str, set[str]] = {}
    for path in sorted((REPO_ROOT / "michspc").rglob("*.py")):
        if path.name == "selftest.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules: set[str] = set()
        for scope in ast.walk(tree):
            if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(scope):
                if isinstance(node, ast.Import):
                    modules.update(
                        alias.name
                        for alias in node.names
                        if alias.name.startswith("michspc")
                    )
                elif isinstance(node, ast.ImportFrom):
                    if node.level or not (node.module or "").startswith("michspc"):
                        continue
                    for alias in node.names:
                        candidate = f"{node.module}.{alias.name}"
                        modules.add(
                            candidate
                            if resolves_to_a_module(candidate)
                            else node.module
                        )
        if modules:
            found[path.relative_to(REPO_ROOT).as_posix()] = modules
    return found


def test_every_module_imported_inside_a_function_body_is_declared_lazy():
    """The audit, as a mechanism rather than as a reading (work package N8).

    Falsified by deleting ``michspc.spc.projection`` from LAZY_IMPORTS: this
    test alone fails, naming zones.py as the file that imports it.
    """
    declared = set(selftest.LAZY_IMPORTS)
    by_file = michspc_modules_imported_inside_function_bodies()

    undeclared = {
        source: sorted(modules - declared)
        for source, modules in by_file.items()
        if modules - declared
    }
    assert not undeclared, (
        f"these modules are imported from inside a function body and are not "
        f"in michspc.selftest.LAZY_IMPORTS: {undeclared}. PyInstaller's static "
        f"analysis cannot see them, so the bundle would build and die the "
        f"first time a surveyor reached the feature that needs one."
    )


def test_the_function_body_import_scan_finds_the_ones_that_are_known():
    """Named, so a scanner quietly matching nothing cannot pass this file.

    These seven are the deferred imports as of 0.7.0: the two the export layer
    reaches for, the one the job record reaches back for, the three projection
    engines behind the dispatch table, and the dispatcher the zone registry
    asks for its own projection kind.
    """
    everything = set()
    for modules in michspc_modules_imported_inside_function_bodies().values():
        everything |= modules

    assert {
        "michspc.fileio.pnezd",
        "michspc.fileio.report",
        "michspc.fileio.exports",
        "michspc.spc.lambert",
        "michspc.spc.tm",
        "michspc.spc.omerc",
        "michspc.spc.projection",
    } <= everything


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


def test_the_spcs2022_check_fails_when_the_coordinate_moves(monkeypatch):
    """Move the expected northing by one metre; the check must notice.

    One metre is far outside the 0.0005 m budget and small enough to be an
    entirely ordinary-looking coordinate - the class of error this check exists
    for. The message must state how far the point landed, in metres, because
    that is what tells a reader whether the bundle picked the wrong engine
    (hundreds of metres) or the right one with a wrong constant.
    """
    monkeypatch.setattr(
        selftest,
        "SPCS2022_ANCHOR_NORTHING_M",
        selftest.SPCS2022_ANCHOR_NORTHING_M + 1.0,
    )

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_spcs2022_conversion()
    message = str(raised.value)
    assert "beta NCAT" in message
    assert "m away" in message


def test_the_spcs2022_check_fails_on_a_wrong_scale_factor(monkeypatch):
    """A coordinate can be right while the factor a distance is scaled by is not.

    Seeded at one part in a hundred million - far below anything visible in a
    coordinate, and 20,000 times the 5e-10 the printed precision supports.
    """
    monkeypatch.setattr(
        selftest,
        "SPCS2022_ANCHOR_SCALE_FACTOR",
        selftest.SPCS2022_ANCHOR_SCALE_FACTOR + 1e-8,
    )

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_spcs2022_conversion()
    assert "grid scale factor" in str(raised.value)


def test_the_frame_refusal_check_fails_when_the_registry_refusal_is_gone(
    monkeypatch,
):
    """Seeded with the defect it exists for: a bundle that ACCEPTS the crossing.

    ``frames.require_frame_path`` is replaced with one that hands back an
    identity for any pair - which is precisely what a lost registry entry, or a
    future edit that registered the bridge before it was verified, would look
    like from inside the bundle. The check must refuse, and name both frames.

    **``convert`` is imported first, deliberately.** It binds
    ``require_frame_path`` at ITS import, so whether this patch reaches the
    public path depends on whether ``michspc.spc.convert`` was already imported
    when the patch was applied - which depends on which tests ran before. That
    is a test whose meaning changes with collection order; importing it here
    fixes the binding, so this test seeds the REGISTRY call and only that.
    """
    from michspc.spc import convert, frames

    assert convert.require_frame_path is frames.require_frame_path
    monkeypatch.setattr(
        frames,
        "require_frame_path",
        lambda source, target: "a transformation that does not exist",
    )

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_frame_refusal()
    message = str(raised.value)
    assert "ACCEPTED" in message
    assert "NAD83(2011)" in message
    assert "NATRF2022" in message


def test_the_frame_refusal_check_fails_on_the_wrong_exception_class(monkeypatch):
    """The class is load-bearing, not only the fact that something was raised.

    ``michspc.job`` and the GUI both catch ``FrameMismatchError`` by name, so a
    refusal raised as some other exception reaches the surveyor as a crash
    rather than as an explanation - the shape of the WP-V2 dialect finding
    (docs/DESIGN.md #35).

    Both call sites are seeded, one per parametrized half, because check 11 now
    asks two different objects the same question: ``convert``'s own binding on
    the public path, and ``frames``' on the registry. Seeding only one leaves
    the other's ``except`` clause unexercised - and which one gets seeded was,
    before this split, an accident of import order.
    """
    from michspc.spc import convert, frames

    def wrong_class(source, target):
        raise RuntimeError("no path")

    # The public path first: convert's own binding, patched in place.
    monkeypatch.setattr(convert, "require_frame_path", wrong_class)
    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_frame_refusal()
    message = str(raised.value)
    assert "RuntimeError" in message
    assert "projecting" in message
    monkeypatch.undo()

    # Then the registry loop, with the public path left working.
    monkeypatch.setattr(frames, "require_frame_path", wrong_class)
    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_frame_refusal()
    message = str(raised.value)
    assert "RuntimeError" in message
    assert "converting NAD83(2011) to NATRF2022" in message


def test_the_frame_refusal_check_fails_when_the_public_gate_is_bypassed(
    monkeypatch,
):
    """The closing gate's LOW, seeded with the reviewer's own mutation.

    ``convert.py`` binds ``require_frame_path`` at import, so replacing
    ``michspc.spc.convert.require_frame_path`` with a no-op leaves the registry
    refusing perfectly while the public conversion path stops asking it - the
    accidental-removal case. Under that mutation
    ``project_point(NAD83_2011 -> zone 261008)`` returns a coordinate about
    1.235 m from the right one, and BOTH frozen checks used to stay green.

    Check 11 must now fail, naming the frames and the coordinate it accepted.
    """
    from michspc.spc import convert

    monkeypatch.setattr(
        convert, "require_frame_path", lambda source, target: None
    )

    # The mutation really does open the public path - the premise, stated
    # rather than assumed.
    from michspc.spc.frames import NAD83_2011
    from michspc.spc.zones import zone_by_code

    crossed = convert.project_point(
        selftest.SPCS2022_ANCHOR_LATITUDE,
        selftest.SPCS2022_ANCHOR_LONGITUDE,
        NAD83_2011,
        zone_by_code(selftest.SPCS2022_ZONE_CODE),
    )
    assert crossed.target_northing is not None

    with pytest.raises(selftest.SelfTestError) as raised:
        selftest.check_frame_refusal()
    message = str(raised.value)
    assert "PROJECTED" in message
    assert "NAD83(2011)" in message
    assert "public conversion path" in message


def test_the_frame_refusal_check_passes_only_while_conversion_still_works():
    """A gate that refuses everything would satisfy the refusal check alone.

    The pairing is the point: ``check_frame_refusal`` says the crossing is
    refused **at ``convert.project_point``, the public entry a job uses**, and
    ``check_spcs2022_conversion`` - which goes through that same function -
    says a same-frame conversion is not. Both are in CHECKS, and this states
    why neither is sufficient by itself.

    Until the 0.7.0 closing gate check 11 asked the registry alone, and this
    docstring claimed the pairing covered the shared gate. It did not: a no-op
    at the call site passed both. The claim and the check moved together.
    """
    assert "cross-frame refusal" in dict(
        (name, check) for name, check in selftest.CHECKS
    )
    assert "SPCS2022 conversion against beta NGS NCAT" in dict(
        (name, check) for name, check in selftest.CHECKS
    )

    from michspc.spc.frames import NATRF2022, require_frame_path

    # The same gate the SPCS2022 check runs through, within one frame.
    assert require_frame_path(NATRF2022, NATRF2022) is not None
    assert selftest.check_frame_refusal()


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


# --------------------------------------------------------------------------
# The NGS beta acknowledgement gate (work package N8).
# --------------------------------------------------------------------------


def test_the_beta_gate_refuses_a_release_without_the_acknowledgement():
    """The promise docs/REFREEZE-NSRS.md records, driven directly.

    Run against the REAL repository, so while this tree carries beta-derived
    artifacts the refusal is demonstrated rather than simulated. When the
    re-freeze is done and no artifact carries the token, this test asserts the
    other half - that the gate then passes and asks for nothing.
    """
    from tools import build_release

    tagged = build_release.tagged_beta_artifacts()

    if not tagged:
        assert build_release.gate_beta_acknowledgement(False) == []
        return

    with pytest.raises(build_release.BuildError) as raised:
        build_release.gate_beta_acknowledgement(False)
    message = str(raised.value)
    assert "--acknowledge-ngs-beta" in message
    assert "docs/REFREEZE-NSRS.md" in message
    assert "Nothing has been built." in message
    for artifact in tagged:
        assert artifact in message


def test_the_beta_gate_lists_every_tagged_artifact_when_acknowledged(capsys):
    """The flag suppresses nothing: it prints what it is acknowledging.

    The artifacts named here are the beta surface as of 0.7.0 - the zone
    registry, the frame registry, the job record's SPCS2022 prose, the anchor
    fixture, and the frozen self-test's own transcribed anchor. A sixth is
    fine; these five disappearing would mean the scan stopped working rather
    than the repository being clean (the shape
    tests/test_refreeze_inventory.py uses for the same reason).
    """
    from tools import build_release

    acknowledged = build_release.gate_beta_acknowledgement(True)
    printed = capsys.readouterr().out

    assert acknowledged == build_release.tagged_beta_artifacts()
    assert set(acknowledged) >= {
        "michspc/spc/zones.py",
        "michspc/spc/frames.py",
        "michspc/fileio/report.py",
        "michspc/selftest.py",
        "tests/fixtures/spcs2022_engine_anchors.py",
    }
    for artifact in acknowledged:
        assert artifact in printed
    assert "docs/REFREEZE-NSRS.md" in printed


def test_the_acknowledgement_reaches_the_checksum_file():
    """A release's own evidence must say what era it was built from.

    The comment lines begin with ``#``, which every ``sha256sum``-style checker
    ignores, so recording the acknowledgement cannot break verification of the
    installer's digest.
    """
    from tools import build_release

    assert build_release.beta_acknowledgement_lines([]) == []

    lines = build_release.beta_acknowledgement_lines(
        ["michspc/spc/zones.py", "tests/fixtures/spcs2022_engine_anchors.py"]
    )
    text = "\n".join(lines)

    assert "--acknowledge-ngs-beta" in text
    assert "docs/REFREEZE-NSRS.md" in text
    assert "michspc/spc/zones.py" in text
    assert "tests/fixtures/spcs2022_engine_anchors.py" in text
    for line in lines:
        assert line == "" or line.startswith("#")


def test_the_build_gates_beta_scan_is_the_inventory_tests_scan(tmp_path):
    """Two implementations of one rule, held together.

    ``tools/build_release.py`` must not import ``tests/`` - a build tool that
    depended on the suite would refuse to run where the suite is not installed,
    and would make the gate depend on the thing it gates - so the scan exists
    twice. Twice means it can drift, and a drifted build-tool scan would find
    nothing and let a beta release through silently.

    Checked on the real repository AND on synthetic trees covering each rule
    the scanners share: both casings of the token, the roots that are scanned,
    the root that is not, and the binary suffixes that are skipped.
    """
    from tests import test_refreeze_inventory as inventory
    from tools import build_release

    assert build_release.BETA_TOKENS == inventory.BETA_TOKENS
    assert tuple(build_release.BETA_SCANNED_ROOTS) == tuple(inventory.SCANNED_ROOTS)

    assert build_release.tagged_beta_artifacts() == sorted(
        inventory.tagged_files(REPO_ROOT)
    )

    (tmp_path / "michspc" / "spc").mkdir(parents=True)
    (tmp_path / "michspc" / "spc" / "tagged.py").write_text(
        "# captured 2027-01-01. NGS beta\n", encoding="utf-8"
    )
    (tmp_path / "michspc" / "spc" / "shouted.py").write_text(
        '"""**NGS BETA.**"""\n', encoding="utf-8"
    )
    (tmp_path / "michspc" / "spc" / "ordinary.py").write_text(
        "# nothing pre-release here\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "anchors.py").write_text(
        "# NGS beta\n", encoding="utf-8"
    )
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / "capture.py").write_text("# NGS beta\n", encoding="utf-8")
    (tmp_path / "michspc" / "grid.bin").write_bytes(b"NGS beta")

    assert build_release.tagged_beta_artifacts(tmp_path) == sorted(
        inventory.tagged_files(tmp_path)
    )
    assert build_release.tagged_beta_artifacts(tmp_path) == [
        "michspc/spc/shouted.py",
        "michspc/spc/tagged.py",
        "tests/fixtures/anchors.py",
    ]


def test_the_beta_gate_runs_immediately_after_the_version_gate():
    """Ordering, for the same reason the version gate is first: cost.

    Both refusals are about a decision rather than about an artifact, so they
    belong before twenty minutes of building. The suite, the bundle and the
    installer all run after them.
    """
    from tools import build_release

    source = Path(build_release.__file__).read_text(encoding="utf-8")
    version = source.index("version = gate_version()")
    beta = source.index("acknowledged_beta = gate_beta_acknowledgement(")
    tree = source.index("revision = gate_clean_tree()")
    # Indented, so this finds the CALL in main's try block rather than the
    # definition further up the file.
    suite = source.index("\n        gate_test_suite()")

    assert version < beta < tree < suite
    assert "--acknowledge-ngs-beta" in source


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
