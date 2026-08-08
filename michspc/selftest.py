"""The frozen bundle's self-test: the one check the test suite cannot make.

``py -m pytest`` runs against the source tree. It proves the *code* is right.
It says nothing about whether the thing that ships — a PyInstaller bundle with
its own copy of the interpreter, its own module archive, its own data files and
its own Qt plugin directory — contains everything that code needs. A bundle can
be built from a green suite and still be missing the GEOID18 tile, missing the
Qt platform plugin, or carrying a dependency that was excluded because nothing
imports it by name (docs/method/TOOLING.md, the numpy-under-ezdxf trap: the
bundle builds and dies on first use).

So the shipped executable answers ``--selftest`` by exercising itself:

1. every bundled NGS grid is present and authenticates: the GEOID18 tile
   against its pinned SHA-256 and canonical geometry, returning a geoid height
   NGS agrees with; the VERTCON 3.0 pair the same way, returning a shift NCAT
   agrees with; and the GEOID12B tile through the geoid model registry
   (WP-V5) - digest, geometry, and a height NGS's own geoid service agrees
   with;
2. every module the program reaches for lazily — PySide6 above all — actually
   imports out of the bundle;
3. Qt starts far enough to build a real ``QApplication`` and read the bundled
   icon back out;
4. one real conversion runs the whole production path, PNEZD file on disk ->
   ``job.run`` -> ``exports.write_all`` -> the ZIP -> the clean export parsed
   back, and lands on coordinates **NGS computed**, not on this program's own
   output.

``tools/build_release.py`` runs this against the freshly built bundle as a hard
gate. A bundle that fails its own self-test is not a release.

**Raises, never asserts.** The suite runs under ``-O`` and so does the shipped
bundle, which strips ``assert`` outright (docs/DESIGN.md section 7). Every check
below is an ``if``/``raise``.

**On the frozen anchors below.** They are transcribed from
``tests/fixtures/ncat_crosscheck.py``, which is itself transcribed from raw NGS
JSON captures. The duplication is deliberate and is the only one in this
program: ``tests/`` is not in the bundle, so a frozen self-test cannot import
the fixtures, and a self-test that checked the program against numbers the
program itself produced would be a program agreeing with itself.
``tests/test_selftest.py`` pins every constant here to the fixture it came from
with an exact ``==``, so the two copies cannot drift.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

from michspc import APP_NAME, __version__

SELFTEST_FLAG = "--selftest"
"""The command line that reaches this module. See ``launch.py``."""

REPORT_FLAG = "--report"
"""``--report <path>`` writes the transcript to a file.

A windowed PyInstaller bundle has no console: ``sys.stdout`` and ``sys.stderr``
are ``None``, so a failure message printed to them would go nowhere and the
build gate would see an exit code with no diagnosis. The build script always
passes this flag.
"""


class SelfTestError(Exception):
    """A check failed. The message names what, and what it means."""


# ---------------------------------------------------------------------------
# Frozen NGS anchors. Provenance in the module docstring; pinned to the test
# fixtures by tests/test_selftest.py.
# ---------------------------------------------------------------------------

# tests/fixtures/ncat_crosscheck.py, CrosscheckGeoid "S2" — NGS geoid API
# (geoid_S2.json), captured 2026-08-06. Cadillac, Michigan.
GEOID_ANCHOR_LATITUDE = 44.252
GEOID_ANCHOR_LONGITUDE = -85.4012
GEOID_ANCHOR_HEIGHT_M = -33.28

# The same position as NCAT computes it in Michigan South (2113) and in
# Michigan Central (2112), International feet — CrosscheckForward "S2",
# llh_S2_2113.json and llh_S2_2112.json. Both ends of the end-to-end check are
# therefore NGS figures: the input is what NCAT printed for this position in
# the source zone, the expected output what it printed in the target zone.
SOURCE_ZONE_CODE = "2113"
TARGET_ZONE_CODE = "2112"
SOURCE_NORTHING_IFT = 1004688.797
SOURCE_EASTING_IFT = 12852238.149
TARGET_NORTHING_IFT = 342726.604
TARGET_EASTING_IFT = 19413974.768

# CrosscheckPoint "S2" — the cross-check's own chosen orthometric height, not
# an NGS output. It is here so the conversion carries an elevation and the
# geoid, elevation and combined factors are actually computed.
ANCHOR_ELEVATION_M = 397.0

# tests/fixtures/vertcon_anchors.py, VertconAnchor "anchor-22" — NGS NCAT,
# captured 2026-08-07. DESIGN.md #22's anchor: 200.000 m NGVD 29 at
# 43.0 N / 84.5 W converts to 199.860 m NAVD 88, a -0.140 m shift.
VERTCON_ANCHOR_LATITUDE = 43.0
VERTCON_ANCHOR_LONGITUDE = -84.5
VERTCON_ANCHOR_SHIFT_M = -0.140

# tests/fixtures/geoid12b_anchors.py, the Cadillac-area anchor — NGS geoid API,
# model=13 (GEOID12B), captured 2026-08-07 (raw response in
# review/wp-v5-geoid12b/). NOT the same position as the GEOID18 anchor above:
# the GEOID12B lattice reuses the GEOID18 ANCHOR positions (44.2542), where
# the S2 crosscheck point is 44.252.
GEOID12B_ANCHOR_LATITUDE = 44.2542
GEOID12B_ANCHOR_LONGITUDE = -85.4012
GEOID12B_ANCHOR_HEIGHT_M = -33.285

# tests/fixtures/ncat_crosscheck.py, CROSSCHECK_TOLERANCES. NCAT publishes to
# 0.001 m, so one printed figure carries +-0.0005 m; 0.002 m is four times that.
LINEAR_TOLERANCE_M = 0.002
GEOID_TOLERANCE_M = 0.002


def _zone_to_zone_tolerance_ift() -> float:
    """The budget for a coordinate read back out of a written file, in feet.

    A zone-to-zone conversion is anchored by an NCAT figure at *both* ends, so
    it gets two legs of NCAT's quantization rather than one. The clean export
    writes feet to three decimal places, which moves a value by at most half of
    the last place it keeps, so that half-place is part of the budget too.
    """
    from michspc.spc.units import INTERNATIONAL_FEET

    return INTERNATIONAL_FEET.from_meters(2.0 * LINEAR_TOLERANCE_M) + 0.5e-3


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def check_version() -> str:
    """The bundle knows what it is."""
    if not __version__ or not APP_NAME:
        raise SelfTestError(
            "the bundle carries no version or no application name; "
            f"__version__={__version__!r}, APP_NAME={APP_NAME!r}. "
            "michspc/__init__.py did not make it into the bundle intact."
        )
    return f"{APP_NAME} {__version__}"


def check_geoid_grid() -> str:
    """The GEOID18 tile ships, authenticates, and answers like NGS.

    Three separate failures live here and they fail differently: the file can be
    absent from the bundle (a data-file line missing from ``michspc.spec``), it
    can be present and altered (the SHA-256 catches any changed byte, including
    a build step that "helpfully" translated line endings in a binary), or it
    can be present and intact and still be read wrongly. The last is why the
    height itself is checked against NGS rather than merely loading the grid.
    """
    from michspc.fileio import geoid

    tile = geoid.GEOID18_TILE
    if not tile.is_file():
        raise SelfTestError(
            f"the {geoid.GEOID_MODEL_NAME} grid is not in this bundle. "
            f"Looked for {tile}. Without it no elevation factor and no combined "
            f"factor can be computed for any point. The bundle is incomplete."
        )

    try:
        grid = geoid.load_shipped_grid()
    except geoid.GeoidError as error:
        raise SelfTestError(
            f"the bundled {geoid.GEOID_MODEL_NAME} grid did not pass its own "
            f"checks: {error}"
        ) from error

    try:
        height = geoid.geoid_height(
            GEOID_ANCHOR_LATITUDE, GEOID_ANCHOR_LONGITUDE, grid
        )
    except geoid.GeoidError as error:
        raise SelfTestError(
            f"the bundled {geoid.GEOID_MODEL_NAME} grid loaded but could not "
            f"be interpolated at {GEOID_ANCHOR_LATITUDE}, "
            f"{GEOID_ANCHOR_LONGITUDE}: {error}"
        ) from error

    difference = abs(height - GEOID_ANCHOR_HEIGHT_M)
    if difference > GEOID_TOLERANCE_M:
        raise SelfTestError(
            f"the bundled {geoid.GEOID_MODEL_NAME} grid returned "
            f"{height:.4f} m at {GEOID_ANCHOR_LATITUDE}, "
            f"{GEOID_ANCHOR_LONGITUDE}, where NGS's own geoid service returns "
            f"{GEOID_ANCHOR_HEIGHT_M:.3f} m - out by {difference:.4f} m, "
            f"against a tolerance of {GEOID_TOLERANCE_M} m. The grid in this "
            f"bundle is not being read the way the source tree reads it."
        )

    return (
        f"{geoid.GEOID_MODEL_NAME} tile authenticated "
        f"({grid.row_count} x {grid.column_count} cells) and returned "
        f"{height:.4f} m against NGS's {GEOID_ANCHOR_HEIGHT_M:.3f} m"
    )


def check_vertcon_grids() -> str:
    """The VERTCON 3.0 pair ships, authenticates, and answers like NCAT.

    The same three failure modes as the geoid check, doubled: either file can be
    absent, altered (the SHA-256 catches any changed byte), or intact and read
    wrongly - which is why the shift itself is checked against an NGS NCAT
    figure rather than the pair merely loading. Until the WP-V4 review gate the
    suite authenticated these files in ``data/`` and nothing authenticated them
    in the BUNDLE: a grid corrupted during packaging passed every release gate
    (independent review of the vertical branch, MEDIUM 3).
    """
    from michspc.fileio import vertcon

    for tile in (vertcon.VERTCON3_TRN_TILE, vertcon.VERTCON3_ERR_TILE):
        if not tile.is_file():
            raise SelfTestError(
                f"the {vertcon.VERTCON_MODEL_NAME} grid {tile.name} is not in "
                f"this bundle. Looked for {tile}. Without the pair no elevation "
                f"can be converted between NGVD 29 and NAVD 88. The bundle is "
                f"incomplete."
            )

    try:
        pair = vertcon.load_shipped_grids()
    except vertcon.VertconError as error:
        raise SelfTestError(
            f"the bundled {vertcon.VERTCON_MODEL_NAME} grids did not pass "
            f"their own checks: {error}"
        ) from error

    try:
        shift, _sigma = pair.reading_at(
            VERTCON_ANCHOR_LATITUDE, VERTCON_ANCHOR_LONGITUDE
        )
    except vertcon.VertconError as error:
        raise SelfTestError(
            f"the bundled {vertcon.VERTCON_MODEL_NAME} grids loaded but could "
            f"not be interpolated at {VERTCON_ANCHOR_LATITUDE}, "
            f"{VERTCON_ANCHOR_LONGITUDE}: {error}"
        ) from error

    difference = abs(shift - VERTCON_ANCHOR_SHIFT_M)
    if difference > LINEAR_TOLERANCE_M:
        raise SelfTestError(
            f"the bundled {vertcon.VERTCON_MODEL_NAME} grids returned a shift "
            f"of {shift:.4f} m at {VERTCON_ANCHOR_LATITUDE}, "
            f"{VERTCON_ANCHOR_LONGITUDE}, where NGS NCAT returns "
            f"{VERTCON_ANCHOR_SHIFT_M:.3f} m - out by {difference:.4f} m, "
            f"against a tolerance of {LINEAR_TOLERANCE_M} m. The grids in this "
            f"bundle are not being read the way the source tree reads them."
        )

    return (
        f"{vertcon.VERTCON_MODEL_NAME} pair authenticated and returned "
        f"{shift:.4f} m against NCAT's {VERTCON_ANCHOR_SHIFT_M:.3f} m"
    )


def check_geoid12b_tile() -> str:
    """The GEOID12B tile ships, authenticates, and answers like NGS.

    The same three failure modes as the GEOID18 check: absent from the bundle,
    present and altered (the SHA-256 catches any changed byte), or intact and
    read wrongly - which is why a height is checked against a frozen NGS
    figure rather than the tile merely loading. Until WP-V5 nothing read this
    tile and the digest was the only executable statement about it; the geoid
    model registry now loads it exactly the way a job that selects GEOID12B
    does, so this check exercises that path from inside the bundle.
    """
    import hashlib

    from michspc.fileio import geoid

    tile = geoid.GEOID12B_TILE
    if not tile.is_file():
        raise SelfTestError(
            f"the GEOID12B tile is not in this bundle. Looked for {tile}. "
            f"Without it no job that selects GEOID12B can compute an elevation "
            f"or combined factor. The bundle is incomplete."
        )

    digest = hashlib.sha256(tile.read_bytes()).hexdigest()
    if digest != geoid.GEOID12B_MODEL.sha256:
        raise SelfTestError(
            f"the bundled GEOID12B tile does not match the grid this program "
            f"was built against.\n  expected SHA-256 "
            f"{geoid.GEOID12B_MODEL.sha256}\n  found    SHA-256 {digest}\n"
            f"The file was corrupted or substituted during packaging."
        )

    try:
        grid = geoid.load_shipped_grid(tile, model=geoid.GEOID12B_MODEL)
    except geoid.GeoidError as error:
        raise SelfTestError(
            f"the bundled GEOID12B tile did not pass its own checks: {error}"
        ) from error

    try:
        height = geoid.geoid_height(
            GEOID12B_ANCHOR_LATITUDE, GEOID12B_ANCHOR_LONGITUDE, grid
        )
    except geoid.GeoidError as error:
        raise SelfTestError(
            f"the bundled GEOID12B tile loaded but could not be interpolated "
            f"at {GEOID12B_ANCHOR_LATITUDE}, {GEOID12B_ANCHOR_LONGITUDE}: "
            f"{error}"
        ) from error

    difference = abs(height - GEOID12B_ANCHOR_HEIGHT_M)
    if difference > GEOID_TOLERANCE_M:
        raise SelfTestError(
            f"the bundled GEOID12B tile returned {height:.4f} m at "
            f"{GEOID12B_ANCHOR_LATITUDE}, {GEOID12B_ANCHOR_LONGITUDE}, where "
            f"NGS's own geoid service returns {GEOID12B_ANCHOR_HEIGHT_M:.3f} m "
            f"- out by {difference:.4f} m, against a tolerance of "
            f"{GEOID_TOLERANCE_M} m. The grid in this bundle is not being read "
            f"the way the source tree reads it."
        )

    return (
        f"GEOID12B tile authenticated through the registry and returned "
        f"{height:.4f} m against NGS's {GEOID12B_ANCHOR_HEIGHT_M:.3f} m"
    )


#: Everything the program imports late, or imports only from one branch. A name
#: that is only ever reached from inside a function body is invisible to
#: PyInstaller's static analysis unless it is declared in ``michspc.spec``'s
#: ``hiddenimports``; this list and that one are pinned to each other by
#: ``tests/test_selftest.py``.
LAZY_IMPORTS: tuple[str, ...] = (
    # Imported inside function bodies in production code:
    #   exports.verify_round_trip -> michspc.fileio.pnezd
    #   exports.write_all         -> michspc.fileio.report
    "michspc.fileio.pnezd",
    "michspc.fileio.report",
    # The vertical-datum layer. Since WP-V6/V7 the shipped program DOES import
    # these (job.py and report.py, at module level), so they are statically
    # reachable - the declarations stay because this list's contract is the
    # names the bundle then PROVES it can import, and a module that later
    # went back to lazy would otherwise go missing with nothing noticing.
    # check_vertcon_grids below is what proves the pair authenticates from
    # inside the bundle.
    "michspc.fileio.ngs_grid",
    "michspc.fileio.vertcon",
    "michspc.spc.vertical",
    # The GUI, which the self-test itself never opens — so nothing else in this
    # process would notice if Qt were missing from the bundle.
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "michspc.gui.app",
    "michspc.gui.icon",
    "michspc.gui.window",
    "michspc.gui.results_model",
    # The single-point tab's four modules. They reach the frozen bundle
    # transitively, because window.py imports them at module level - but this
    # list's stated contract is the names the bundle then PROVES it can import,
    # and satisfying it only indirectly is how a lazily imported module goes
    # missing later without anything noticing (closing review gate).
    "michspc.gui.controls",
    "michspc.gui.single_point",
    "michspc.gui.result_panel",
    # The copy glyph. It is drawn with QPainter rather than loaded from a file
    # precisely so the bundle carries no new asset (amendment #27) - but the
    # module still has to be IN the bundle, and a missing one would show as a
    # row of buttons with no picture on them rather than as an error.
    "michspc.gui.copy_icon",
    # Degrees / minutes / seconds entry (amendment #28): the four boxes and the
    # composition behind them. fileio.dms is the one that matters most here -
    # it is the only module in the program that turns typed text into an angle.
    "michspc.gui.dms_entry",
    "michspc.fileio.dms",
    # Standard-library modules the shipped code paths reach for. Cheap to check
    # and they have been dropped from bundles before by an over-eager exclude.
    "csv",
    "zipfile",
    "hashlib",
    "struct",
    "zlib",
)


def check_lazy_imports() -> str:
    """Every deferred dependency actually imports, out of this bundle."""
    import importlib

    for name in LAZY_IMPORTS:
        try:
            importlib.import_module(name)
        except Exception as error:  # noqa: BLE001 — any failure is fatal here
            raise SelfTestError(
                f"{name} is not importable from this bundle: "
                f"{type(error).__name__}: {error}. It is imported lazily, so "
                f"nothing would have failed until a surveyor reached the "
                f"feature that needs it. Add it to hiddenimports in "
                f"michspc.spec, or stop excluding it."
            ) from error

    return f"{len(LAZY_IMPORTS)} lazily imported modules all resolved"


def check_icon_resource() -> str:
    """Qt starts, and the bundled icon is the one it finds.

    Building a real ``QApplication`` is the point: it forces Qt to locate its
    platform plugin inside the bundle, which is the failure a source run can
    never reproduce. ``QT_QPA_PLATFORM=offscreen`` is set first so no window
    server is needed (docs/method/TOOLING.md).
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtGui import QIcon

    from michspc.gui.app import build_application
    from michspc.gui.icon import GENERATED_ICO_NAME, icon_path

    build_application([f"{APP_NAME} --selftest"])

    found = icon_path()
    if found is None:
        raise SelfTestError(
            "no application icon is present in this bundle. "
            "michspc.spec must carry the generated "
            f"{GENERATED_ICO_NAME} as a data file."
        )

    frozen = getattr(sys, "_MEIPASS", None)
    if frozen is not None and found.suffix.lower() != ".ico":
        raise SelfTestError(
            f"the frozen bundle fell back to {found}, which is the source "
            f"tree's master artwork rather than the generated "
            f"{GENERATED_ICO_NAME}. The build step's output did not reach the "
            f"bundle, so Windows would show a scaled PNG at every size."
        )

    loaded = QIcon(str(found))
    if loaded.isNull():
        raise SelfTestError(
            f"the icon at {found} is present but Qt cannot decode it. It is "
            f"truncated, or it was copied through a text-mode transform."
        )

    sizes = sorted(size.width() for size in loaded.availableSizes())
    return f"Qt started and read {found.name}, sizes {sizes}"


def check_end_to_end_conversion() -> str:
    """One real job, all the way to the ZIP, against NGS's own figures.

    Michigan South -> Michigan Central for the Cadillac cross-check point, in
    International feet: the input northing and easting are what NCAT computed
    for that position in 2113, the expected output what it computed for the
    same position in 2112. Nothing this program produced appears on either
    side of the comparison.

    The path is the whole production path — a PNEZD file read off the disk,
    ``job.run``, ``exports.write_all`` staging and verifying a ZIP, and this
    program's own reader parsing the clean export back out of it — because that
    is what the surveyor runs, and because the file layer is where a frozen
    bundle's differences would show.
    """
    import zipfile

    from michspc.fileio import exports, pnezd
    from michspc.job import Direction, JobSettings, run
    from michspc.spc.units import INTERNATIONAL_FEET
    from michspc.spc.zones import zone_by_code

    elevation_ift = INTERNATIONAL_FEET.from_meters(ANCHOR_ELEVATION_M)

    with tempfile.TemporaryDirectory(prefix="michspc-selftest-") as workspace:
        folder = Path(workspace)
        source_file = folder / "selftest_S2.txt"
        source_file.write_text(
            f"S2,{SOURCE_NORTHING_IFT:.3f},{SOURCE_EASTING_IFT:.3f},"
            f"{elevation_ift:.3f},NCAT S2 Cadillac\n",
            encoding="utf-8",
            newline="",
        )

        settings = JobSettings(
            input_path=source_file,
            output_directory=folder / "out",
            direction=Direction.ZONE_TO_ZONE,
            source_zone=zone_by_code(SOURCE_ZONE_CODE),
            target_zone=zone_by_code(TARGET_ZONE_CODE),
            input_unit=INTERNATIONAL_FEET,
            output_unit=INTERNATIONAL_FEET,
            # A zone-to-zone job never consults a longitude, and the field has
            # no default anywhere in this program (docs/DESIGN.md section 7).
            longitude_convention=None,
        )

        try:
            result = run(settings)
            written = exports.write_all(result)
        except Exception as error:  # noqa: BLE001 — any failure is fatal here
            raise SelfTestError(
                f"a conversion that succeeds in the source tree failed in this "
                f"bundle: {type(error).__name__}: {error}"
            ) from error

        archive = written["archive"]
        if not archive.is_file():
            raise SelfTestError(
                f"the job reported writing {archive} and there is no file "
                f"there. The deliverable never reached the disk."
            )

        names = exports.member_names(result)
        with zipfile.ZipFile(archive) as opened:
            members = set(opened.namelist())
            missing = sorted(set(names.values()) - members)
            if missing:
                raise SelfTestError(
                    f"the archive this bundle wrote is missing {missing}. A "
                    f"job's three files travel together or not at all "
                    f"(docs/DESIGN.md amendment #17)."
                )
            clean_text = opened.read(names["pnezd"]).decode("utf-8")

        parsed = pnezd.parse_lines(clean_text.splitlines(), path=names["pnezd"])
        if len(parsed.rows) != 1:
            raise SelfTestError(
                f"the clean export holds {len(parsed.rows)} rows; the job "
                f"converted exactly one point."
            )

        row = parsed.rows[0]
        tolerance = _zone_to_zone_tolerance_ift()

        for label, produced, expected in (
            ("northing", row.northing, TARGET_NORTHING_IFT),
            ("easting", row.easting, TARGET_EASTING_IFT),
        ):
            difference = abs(produced - expected)
            if difference > tolerance:
                raise SelfTestError(
                    f"this bundle converted the Cadillac cross-check point "
                    f"from Michigan South to Michigan Central and produced a "
                    f"{label} of {produced:,.3f} international feet where NGS "
                    f"NCAT computes {expected:,.3f} - out by {difference:.4f} "
                    f"ft, against a tolerance of {tolerance:.4f} ft. The "
                    f"mathematics in this bundle does not agree with the "
                    f"mathematics the test suite verified."
                )

        if row.elevation is None:
            raise SelfTestError(
                "the elevation did not survive the conversion: the clean "
                "export's Z column is empty for a point whose Z was supplied."
            )

        elevation_error = abs(row.elevation - elevation_ift)
        if elevation_error > 0.5e-3:
            raise SelfTestError(
                f"the elevation came back as {row.elevation:,.3f} "
                f"international feet where {elevation_ift:,.3f} went in. "
                f"Orthometric height does not depend on the horizontal zone."
            )

        point = result.points[0]
        if point.factors.combined_factor is None:
            raise SelfTestError(
                "no combined factor was computed for a point that carries an "
                "elevation. The geoid lookup did not reach the bundled grid."
            )

    return (
        f"{SOURCE_ZONE_CODE} -> {TARGET_ZONE_CODE} through the file layer "
        f"matched NCAT to {abs(row.northing - TARGET_NORTHING_IFT):.4f} ft "
        f"northing and {abs(row.easting - TARGET_EASTING_IFT):.4f} ft easting "
        f"(combined factor {point.factors.combined_factor:.8f})"
    )


CHECKS: tuple[tuple[str, object], ...] = (
    ("version and application name", check_version),
    ("bundled GEOID18 grid", check_geoid_grid),
    ("bundled VERTCON 3.0 grid pair", check_vertcon_grids),
    ("bundled GEOID12B tile", check_geoid12b_tile),
    ("lazily imported dependencies", check_lazy_imports),
    ("Qt startup and bundled icon", check_icon_resource),
    ("end-to-end conversion against NGS NCAT", check_end_to_end_conversion),
)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_selftest(log=None) -> list[str]:
    """Run every check in order. Raises ``SelfTestError`` on the first failure.

    ``log`` is any callable taking one string, or None for silence. Returns the
    per-check summary lines, so a caller can record what passed rather than
    only that something did.
    """
    emit = log or (lambda line: None)
    emit(f"{APP_NAME} {__version__} - self-test")
    emit(f"frozen: {getattr(sys, 'frozen', False)}")
    emit(f"bundle: {getattr(sys, '_MEIPASS', '(running from source)')}")
    emit(f"python: {sys.version.split()[0]}")
    emit("")

    lines: list[str] = []
    for name, check in CHECKS:
        detail = check()
        line = f"PASS  {name}: {detail}"
        lines.append(line)
        emit(line)
    return lines


def main(argv: list[str] | None = None) -> int:
    """``--selftest [--report PATH]``. 0 on success, 1 on a named failure.

    Never raises out of itself: the exit code is the gate, and the message is
    the diagnosis. Both must survive a windowed bundle that has no console, so
    every write goes through ``_write``.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    report_path = _report_path(arguments)

    transcript: list[str] = []

    def emit(line: str) -> None:
        transcript.append(line)
        _write(line)

    try:
        run_selftest(emit)
    except SelfTestError as error:
        emit("")
        emit(f"FAIL  {error}")
        emit("")
        emit("SELF-TEST FAILED - this bundle is not a release.")
        _save(report_path, transcript)
        return 1
    except Exception as error:  # noqa: BLE001 — an unexpected failure is still a failure
        emit("")
        emit(f"FAIL  unexpected {type(error).__name__}: {error}")
        emit(traceback.format_exc())
        emit("SELF-TEST FAILED - this bundle is not a release.")
        _save(report_path, transcript)
        return 1

    emit("")
    emit(f"SELF-TEST PASSED - {len(CHECKS)} checks.")
    _save(report_path, transcript)
    return 0


def _report_path(arguments: list[str]) -> Path | None:
    """``--report PATH`` or ``--report=PATH``, if either was given."""
    for index, argument in enumerate(arguments):
        if argument == REPORT_FLAG and index + 1 < len(arguments):
            return Path(arguments[index + 1])
        if argument.startswith(REPORT_FLAG + "="):
            return Path(argument.split("=", 1)[1])
    return None


def _write(line: str) -> None:
    """Print, when there is anywhere to print to.

    A windowed PyInstaller bundle has ``sys.stdout is None``, and ``print`` to
    it raises. The self-test's whole job is to report a failure clearly, so it
    must not fail while reporting one.
    """
    stream = sys.stdout
    if stream is None:
        return
    try:
        stream.write(line + "\n")
        stream.flush()
    except (OSError, ValueError):
        pass


def _save(path: Path | None, transcript: list[str]) -> None:
    """Write the transcript, if a path was given. Failure to write is not fatal.

    The exit code has already been decided by the checks; losing the transcript
    would be unfortunate, but turning a passing bundle into a failing one over
    an unwritable report path would be worse.
    """
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(transcript) + "\n", encoding="utf-8")
    except OSError as error:
        _write(f"(the self-test report could not be written to {path}: {error})")
