"""The one sanctioned release build. First failure aborts.

    py tools/build_release.py

There is no other supported way to produce a release. Running PyInstaller or
ISCC by hand is fine for diagnosing something; it does not produce a release,
because a release is the artifact **plus** the evidence that every gate passed
(docs/method/METHOD.md section 6).

The gates, in order, each one refusing loudly by name:

    1  version sanity      no ``-dev`` marker, and no tag already using it
    2  NGS beta            refuses while any artifact is beta-derived, unless
                           --acknowledge-ngs-beta is passed
    3  working tree clean  a release must be reproducible from a commit
    4  test suite          py -m pytest AND py -O -m pytest, both green
    5  icon                regenerated from the committed master artwork
    6  bundle              PyInstaller, from the committed michspc.spec
    7  self-test           the FROZEN bundle checks itself - hard gate
    8  installer           Inno Setup
    9  checksums           SHA-256 of every shipped artifact

Gate 7 is the one that cannot be moved. The suite proves the source is right;
only the bundle can prove the bundle is right, and it is the bundle that goes
to the surveyor. A bundle that fails its own self-test is not a release.

**A partial build never looks like a release.** The checksum file is the last
thing written and the first thing deleted, so a run that dies at gate 6 leaves
an output directory with no checksums in it rather than a plausible-looking
half-release. Nothing is committed, tagged or uploaded from here: the session
lead does that, having read what this printed.

What this script does NOT do, deliberately: no user manual is built or checked.
Amendment #13 dropped the manual, so METHOD.md section 5's doc-freshness gate
has nothing to check. That is a recorded deviation, not an omission.

Building a beta-era release::

    py tools/build_release.py --acknowledge-ngs-beta

Gate 2 refuses while any file under ``michspc/`` or ``tests/fixtures/`` carries
the literal token ``NGS beta`` and that flag is absent, so shipping pre-release
NGS numbers is a conscious act on the command line rather than a default
(docs/REFREEZE-NSRS.md; docs/DESIGN.md amendment #61). The flag does not
suppress anything: it prints every tagged artifact it is acknowledging, and the
run's ``SHA256SUMS.txt`` records the acknowledgement beside the digests.

Diagnostics::

    py tools/build_release.py --check-tools    are PyInstaller and ISCC here?
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

_RELEASE_VERSION = re.compile(r"\d+(?:\.\d+)*")
"""What a shippable version literal may look like: digits and dots only."""

REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from michspc import APP_NAME, __version__  # noqa: E402

EXECUTABLE_NAME = "mcx"
SPEC_FILE = REPO_ROOT / "michspc.spec"
INNO_SCRIPT = REPO_ROOT / "installer" / "michspc.iss"

BUNDLE_DIR = REPO_ROOT / "dist" / EXECUTABLE_NAME
FROZEN_EXE = BUNDLE_DIR / f"{EXECUTABLE_NAME}.exe"
INSTALLER_DIR = REPO_ROOT / "dist" / "installer"
CHECKSUM_FILE = INSTALLER_DIR / "SHA256SUMS.txt"
SELFTEST_REPORT = INSTALLER_DIR / "selftest.txt"

ISCC = Path(
    os.environ.get("LOCALAPPDATA", "")
) / "Programs" / "Inno Setup 6" / "ISCC.exe"
"""Where Inno Setup 6 puts its command-line compiler on this machine
(docs/method/TOOLING.md). Overridable with the ISCC environment variable for a
machine that installed it elsewhere."""

SELFTEST_TIMEOUT_SECONDS = 300
"""A hard timeout on the frozen self-test.

The bundle is built windowed (``console=False`` in michspc.spec), and an
unhandled exception before the self-test's own error handling is reached would
put PyInstaller's traceback dialog on screen - which waits for a click that a
build script will never give it. The timeout turns that hang into a failure.
"""


class BuildError(Exception):
    """A gate refused. The message says which, and what to do about it."""


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def announce(number: int, title: str) -> None:
    print(f"\n=== GATE {number}: {title} " + "=" * max(0, 46 - len(title)))


def run(command: list[str], what: str, cwd: Path = REPO_ROOT, timeout=None) -> str:
    """Run a command and return its output. A non-zero exit code aborts.

    The child's exit code is read from the child itself, never from a pipeline
    (docs/method/TOOLING.md: ``pytest | tail`` reports the pipe's status and has
    hidden a real failure here before). ``subprocess`` gives us the process's own
    ``returncode`` with the output captured separately, which is the same
    guarantee as running unpiped.
    """
    print(f"    $ {' '.join(command)}")
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise BuildError(f"{what}: {command[0]} is not on this machine ({error}).")
    except subprocess.TimeoutExpired:
        raise BuildError(
            f"{what}: no result after {timeout} seconds. Killed. A build step "
            f"that hangs is a failure - it usually means something is waiting "
            f"on a dialog or on standard input."
        )

    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        tail = "\n".join(output.strip().splitlines()[-40:])
        raise BuildError(
            f"{what}: exit code {completed.returncode}.\n"
            f"--- last 40 lines of output ---\n{tail}"
        )
    return output


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# The gates
# ---------------------------------------------------------------------------


def gate_version() -> str:
    """No pre-release marker, and no tag already carrying this number.

    The ``-dev`` marker is how the project keeps the shipped number space
    unambiguous between releases (docs/method/METHOD.md section 6): every commit
    that is not a release says so in the one place the version lives. Dropping
    it is a deliberate act by the session lead at the release gate, not
    something a build script does on its behalf.
    """
    announce(1, "version sanity")
    version = __version__
    print(f"    michspc.__version__ = {version!r}")

    # A release version is digits and dots and nothing else. Written as a
    # whitelist rather than a list of known markers - "-dev", "rc1", "+local",
    # "0.1.0 " - because the failure to catch is the marker nobody thought of.
    if not _RELEASE_VERSION.fullmatch(version):
        raise BuildError(
            f"michspc.__version__ is {version!r}, which is not a plain release "
            f"number: a release version is digits separated by dots and "
            f"nothing else, so any pre-release marker (a '-dev' suffix in "
            f"particular) refuses here. Drop the marker in "
            f"michspc/__init__.py - the ONE place the version is written - "
            f"commit that change, and run this again. Nothing has been built."
        )

    existing = run(["git", "tag", "--list"], "reading git tags").split()
    for candidate in (version, f"v{version}"):
        if candidate in existing:
            raise BuildError(
                f"tag {candidate!r} already exists in this repository, so "
                f"version {version} has been released. A shipped number is "
                f"never reused: a second binary answering to the same version "
                f"makes every bug report ambiguous. Bump "
                f"michspc/__init__.py. Nothing has been built."
            )

    print(f"    clean release number, unused by any tag: {version}")
    return version


BETA_ACKNOWLEDGEMENT_FLAG = "--acknowledge-ngs-beta"
"""The command line that lets a beta-era release be built at all."""

BETA_TOKENS = ("NGS beta", "NGS BETA")
"""The literal that marks a beta-derived artifact, in both the casings the
repository uses - prose says "NGS beta", a heading shouts it."""

BETA_SCANNED_ROOTS = ("michspc", "tests/fixtures")
"""Where a beta-derived artifact may live: the shipped program, and the frozen
NGS truth the suite holds it to. ``review/`` is deliberately not scanned - it
is the recapture machinery and NGS's own captured bytes, carrying NGS's wording
rather than this program's token."""


def tagged_beta_artifacts(root: Path = REPO_ROOT) -> list[str]:
    """Every scanned file carrying a beta token, as repo-relative POSIX paths.

    **This is a second implementation of ``tests/test_refreeze_inventory.py``'s
    ``tagged_files``, and the duplication is deliberate**: a build tool that
    imported the test suite would refuse to run wherever the suite is not
    installed, and would make the gate depend on the thing it is gating. The
    rule is identical - the same tokens, the same roots, the same skips - and
    ``tests/test_selftest.py`` pins the two scanners against each other, on the
    real repository and on synthetic trees, so they cannot drift.

    Text files only, and a file that cannot be decoded as UTF-8 is skipped
    rather than guessed at: the token is ASCII, so a file the token could hide
    in is a file that decodes.
    """
    found: list[str] = []
    for prefix in BETA_SCANNED_ROOTS:
        base = root / prefix
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix in {".pyc", ".bin"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if any(token in text for token in BETA_TOKENS):
                found.append(path.relative_to(root).as_posix())
    return sorted(found)


def gate_beta_acknowledgement(acknowledged: bool) -> list[str]:
    """Refuse a beta-era release unless it was asked for by name.

    MCX ships numbers derived from NGS products NGS has published as BETA
    (docs/DESIGN.md amendment #61: the owner's recorded decision to build ahead
    of NGS's official rollout). Those numbers reach sealed work, and every one
    of them must be re-frozen when NGS publishes - which is what
    docs/REFREEZE-NSRS.md and its inventory test exist for. This gate is the
    third leg: it makes each beta-era release a deliberate act, exactly as the
    ``-dev`` marker makes each release deliberate, rather than something that
    happens by default because nobody remembered.

    It is not a suppression flag. When the acknowledgement is given, every
    tagged artifact is printed and the run's checksum file records what was
    acknowledged, so the release's own evidence says what era it came from.

    Returns the tagged artifacts, for the checksum manifest. An empty list
    means the re-freeze is complete and there is nothing to acknowledge - the
    ordinary state this project expects to return to.
    """
    announce(2, "NGS beta artifacts")
    tagged = tagged_beta_artifacts()

    if not tagged:
        print(
            "    no artifact carries an NGS beta token; nothing to acknowledge"
        )
        if acknowledged:
            print(
                f"    ({BETA_ACKNOWLEDGEMENT_FLAG} was passed and was not "
                f"needed - if docs/REFREEZE-NSRS.md still lists artifacts, its "
                f"own test will say so)"
            )
        return []

    if not acknowledged:
        listing = "\n".join(f"      {name}" for name in tagged)
        raise BuildError(
            f"{len(tagged)} artifact(s) in this tree carry the literal token "
            f"'NGS beta':\n{listing}\n"
            f"These hold numbers derived from NGS products that NGS has "
            f"published as PRE-RELEASE, and a coordinate computed from them "
            f"can reach a sealed survey. Building a release from them is "
            f"permitted (docs/DESIGN.md amendment #61) and is a decision, not "
            f"a default: pass {BETA_ACKNOWLEDGEMENT_FLAG} to say so. Read "
            f"docs/REFREEZE-NSRS.md first - if NGS has published since, the "
            f"answer is to re-freeze rather than to acknowledge. Nothing has "
            f"been built."
        )

    print(f"    {BETA_ACKNOWLEDGEMENT_FLAG} given; acknowledging:")
    for name in tagged:
        print(f"      {name}")
    print("    re-freeze obligation: docs/REFREEZE-NSRS.md")
    return tagged


def gate_clean_tree() -> str:
    """A release must be reproducible from a commit, not from a desk."""
    announce(3, "working tree clean")
    dirty = run(["git", "status", "--porcelain"], "reading git status").strip()
    if dirty:
        raise BuildError(
            "the working tree has uncommitted changes:\n"
            + dirty
            + "\nA release built from an uncommitted tree cannot be rebuilt "
            "from its own tag, so the binary a surveyor holds would correspond "
            "to no revision of this program. Commit or stash first."
        )

    revision = run(["git", "rev-parse", "HEAD"], "reading HEAD").strip()
    print(f"    clean at {revision}")
    return revision


def gate_test_suite() -> None:
    """Both run modes, each one's own exit code, neither piped.

    ``-O`` strips ``assert`` statements. pytest's own assertion rewriting
    survives it, so the suite is not vacuous under ``-O`` (docs/DESIGN.md
    amendment #10) - but production code containing a load-bearing assert would
    behave differently between the two, which is exactly what running both
    catches.
    """
    announce(4, "test suite, both run modes")
    for arguments, label in (
        (["-m", "pytest"], "py -m pytest"),
        (["-O", "-m", "pytest"], "py -O -m pytest"),
    ):
        output = run([sys.executable, *arguments, "-q"], f"the test suite ({label})")
        summary = [line for line in output.strip().splitlines() if " passed" in line]
        print(f"    {label}: {summary[-1] if summary else 'green'}")


def gate_icon() -> Path:
    """Regenerate the ``.ico`` from the committed master artwork.

    Run as its own process rather than imported, so the sanctioned command in
    docs/DESIGN.md amendment #15 is the one that is actually exercised and its
    exit code is checked.
    """
    announce(5, "application icon")
    run(
        [sys.executable, str(REPO_ROOT / "tools" / "make_icon.py")],
        "generating the application icon",
    )
    from tools.make_icon import DEFAULT_OUTPUT

    if not DEFAULT_OUTPUT.is_file():
        raise BuildError(
            f"the icon build reported success and {DEFAULT_OUTPUT} is not there."
        )
    print(f"    {DEFAULT_OUTPUT} ({DEFAULT_OUTPUT.stat().st_size:,} bytes)")
    return DEFAULT_OUTPUT


def gate_bundle() -> Path:
    """PyInstaller, from the committed spec, into a clean output directory."""
    announce(6, "PyInstaller bundle")
    if not SPEC_FILE.is_file():
        raise BuildError(f"the committed spec is missing: {SPEC_FILE}")

    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)

    started = time.monotonic()
    run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC_FILE)],
        "the PyInstaller build",
        timeout=1800,
    )
    if not FROZEN_EXE.is_file():
        raise BuildError(
            f"PyInstaller exited 0 and produced no executable at {FROZEN_EXE}."
        )

    # Derived from the source tree rather than restated as a list: data/ holds
    # exactly the NGS grids this program ships, so a grid added there and
    # forgotten in michspc.spec fails here instead of shipping as a bundle that
    # refuses the first job needing it. The self-test would catch the geoid tile
    # a moment later; it is checked here as well because a missing data file is
    # a spec defect, not a program defect.
    bundled_data = BUNDLE_DIR / "_internal" / "data"
    absent = sorted(
        source.name
        for source in (REPO_ROOT / "data").iterdir()
        if source.is_file() and not (bundled_data / source.name).is_file()
    )
    if absent:
        raise BuildError(
            f"the bundle is missing NGS grid files that data/ carries: "
            f"{', '.join(absent)}. Expected them under {bundled_data}. The "
            f"spec derives NGS_GRID_FILENAMES from geoid.ALL_GEOID_MODELS "
            f"and vertcon's tile constants, so a missing file means a grid "
            f"landed in data/ without a registry record - add the record, "
            f"not a filename literal."
        )

    print(
        f"    {FROZEN_EXE} in {time.monotonic() - started:.0f} s; "
        f"bundle {sum(p.stat().st_size for p in BUNDLE_DIR.rglob('*') if p.is_file()):,} bytes"
    )
    return FROZEN_EXE


def gate_frozen_selftest() -> None:
    """The bundle checks itself. HARD GATE.

    Everything before this proves the source tree is sound. This is the only
    step that says anything about the artifact that ships.
    """
    announce(7, "frozen bundle self-test")
    SELFTEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    SELFTEST_REPORT.unlink(missing_ok=True)

    completed = subprocess.run(
        [str(FROZEN_EXE), "--selftest", "--report", str(SELFTEST_REPORT)],
        cwd=str(BUNDLE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=SELFTEST_TIMEOUT_SECONDS,
    )

    transcript = (
        SELFTEST_REPORT.read_text(encoding="utf-8")
        if SELFTEST_REPORT.is_file()
        else (completed.stdout or "") + (completed.stderr or "")
    )
    for line in transcript.strip().splitlines():
        print(f"    | {line}")

    if completed.returncode != 0:
        raise BuildError(
            f"the frozen bundle failed its own self-test (exit code "
            f"{completed.returncode}). The transcript is above and in "
            f"{SELFTEST_REPORT}. A bundle that cannot verify itself is not a "
            f"release, whatever the test suite says about the source."
        )
    if "SELF-TEST PASSED" not in transcript:
        raise BuildError(
            f"the frozen bundle exited 0 without reporting a pass. Either the "
            f"self-test did not run or its transcript was lost; both are "
            f"failures. Report: {SELFTEST_REPORT}"
        )


def gate_installer(version: str) -> Path:
    """Inno Setup. Absent compiler is a refusal, never a skip."""
    announce(8, "Inno Setup installer")
    compiler = Path(os.environ.get("ISCC") or ISCC)
    if not compiler.is_file():
        raise BuildError(
            f"the Inno Setup 6 command-line compiler is not at {compiler}. "
            f"The installer IS the deliverable (docs/DESIGN.md amendment #13), "
            f"so a build without one is not a partial release - it is no "
            f"release at all. Install Inno Setup 6, or point the ISCC "
            f"environment variable at ISCC.exe. The bundle in "
            f"{BUNDLE_DIR} is built and self-tested; nothing else was written."
        )

    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
    installer = INSTALLER_DIR / f"{EXECUTABLE_NAME}-{version}-setup.exe"
    installer.unlink(missing_ok=True)

    run(
        [
            str(compiler),
            f"/DAppVersion={version}",
            f"/DSourceDir={BUNDLE_DIR}",
            f"/DOutputDir={INSTALLER_DIR}",
            str(INNO_SCRIPT),
        ],
        "the Inno Setup compile",
        timeout=1800,
    )

    if not installer.is_file():
        raise BuildError(
            f"ISCC exited 0 and there is no installer at {installer}."
        )
    print(f"    {installer} ({installer.stat().st_size:,} bytes)")
    return installer


def beta_acknowledgement_lines(acknowledged: list[str]) -> list[str]:
    """The trailing comment the checksum file carries on a beta-era build.

    A separate function because it is the one part of gate 9 that can be
    checked without a built bundle - and because the alternative, a checksum
    file whose beta provenance depends on a branch nothing exercises, is how a
    release comes to be silent about what it was built from.

    Empty when nothing was acknowledged: an ordinary release's checksum file is
    byte-identical to what it was before this gate existed.
    """
    if not acknowledged:
        return []
    return [
        "",
        f"# Built with {BETA_ACKNOWLEDGEMENT_FLAG}: this release carries "
        f"numbers derived",
        "# from NGS PRE-RELEASE (beta) products, to be re-frozen against NGS's",
        "# official release - docs/REFREEZE-NSRS.md. Acknowledged artifacts:",
        *(f"#   {name}" for name in acknowledged),
    ]


def gate_checksums(
    installer: Path,
    version: str,
    revision: str,
    acknowledged_beta: list[str] | None = None,
) -> Path:
    """SHA-256 of everything that ships. Written last, on purpose.

    Its absence is what tells a later reader that a build died partway. The
    format is the ``sha256sum`` one - digest, two spaces, name - so it can be
    checked with any standard tool as well as by eye against a GitHub Release.

    ``acknowledged_beta`` is gate 2's list. When it is not empty the file gains
    a trailing comment naming the acknowledgement and every artifact it covers:
    a checksum file is what a reader reaches for years later to establish what
    a binary was, and "this release was built from pre-release NGS products"
    belongs beside the digests rather than only in a build log nobody kept.
    Comment lines begin with ``#``, which every ``sha256sum``-style checker
    ignores, so the file stays machine-checkable.
    """
    announce(9, "SHA-256 of every shipped artifact")
    CHECKSUM_FILE.unlink(missing_ok=True)

    from michspc.fileio.geoid import ALL_GEOID_MODELS
    from michspc.fileio.vertcon import (
        VERTCON3_ERR_FILENAME,
        VERTCON3_ERR_SHA256,
        VERTCON3_TRN_FILENAME,
        VERTCON3_TRN_SHA256,
    )

    artifacts = [installer]
    lines = [
        f"# {APP_NAME} {version}",
        f"# built {time.strftime('%Y-%m-%d %H:%M:%S')} from git {revision}",
        "#",
        "# The installer is the release artifact. The NGS grid digests below",
        "# are the tiles the bundle carries, restated here so each can be",
        "# checked against NGS's own published file without unpacking",
        "# anything.",
        "",
    ]
    for artifact in artifacts:
        digest = sha256_of(artifact)
        lines.append(f"{digest}  {artifact.name}")
        print(f"    {digest}  {artifact.name}")

    # Every NGS grid the bundle carries, from the same registries the spec
    # derives its bundling list from - a fifth grid cannot be added without
    # this manifest following (WP-V5 review gate, LOW 6; previously GEOID18
    # alone was manifested and re-hashed here).
    shipped_grids = [
        (model.tile_filename, model.sha256, f"bundled NGS {model.name} tile")
        for model in ALL_GEOID_MODELS
    ] + [
        (VERTCON3_TRN_FILENAME, VERTCON3_TRN_SHA256, "bundled NGS VERTCON 3.0 shift grid"),
        (VERTCON3_ERR_FILENAME, VERTCON3_ERR_SHA256, "bundled NGS VERTCON 3.0 uncertainty grid"),
    ]
    for filename, pinned, label in shipped_grids:
        bundled_tile = BUNDLE_DIR / "_internal" / "data" / filename
        bundled_digest = sha256_of(bundled_tile)
        if bundled_digest != pinned:
            raise BuildError(
                f"{filename} inside the bundle hashes to {bundled_digest}, "
                f"not the pinned {pinned}. Nothing is written."
            )
        lines.append(f"{bundled_digest}  {filename}  ({label})")
        print(f"    {bundled_digest}  {filename}  ({label})")

    lines.extend(beta_acknowledgement_lines(acknowledged_beta or []))

    CHECKSUM_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return CHECKSUM_FILE


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def check_tools() -> int:
    """Report what the build needs and whether it is here. Builds nothing."""
    print(f"{APP_NAME} {__version__} - build tool check\n")
    print(f"    python      {sys.version.split()[0]}  ({sys.executable})")

    try:
        import PyInstaller

        print(f"    PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("    PyInstaller MISSING - pip install pyinstaller")

    compiler = Path(os.environ.get("ISCC") or ISCC)
    print(f"    ISCC        {'found' if compiler.is_file() else 'MISSING'}: {compiler}")
    print(f"    spec        {'found' if SPEC_FILE.is_file() else 'MISSING'}: {SPEC_FILE}")
    print(f"    installer   {'found' if INNO_SCRIPT.is_file() else 'MISSING'}: {INNO_SCRIPT}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check-tools",
        action="store_true",
        help="report whether PyInstaller and Inno Setup are present, then stop",
    )
    parser.add_argument(
        BETA_ACKNOWLEDGEMENT_FLAG,
        action="store_true",
        help=(
            "build even though artifacts carry NGS beta tokens; every one is "
            "printed and recorded in SHA256SUMS.txt (docs/REFREEZE-NSRS.md)"
        ),
    )
    arguments = parser.parse_args(argv)

    if arguments.check_tools:
        return check_tools()

    print(f"{APP_NAME} - release build")
    started = time.monotonic()

    # Before anything: no stale checksum file may survive a failed run and be
    # mistaken for this one's.
    CHECKSUM_FILE.unlink(missing_ok=True)

    try:
        version = gate_version()
        acknowledged_beta = gate_beta_acknowledgement(
            arguments.acknowledge_ngs_beta
        )
        revision = gate_clean_tree()
        gate_test_suite()
        gate_icon()
        gate_bundle()
        gate_frozen_selftest()
        installer = gate_installer(version)
        checksums = gate_checksums(
            installer, version, revision, acknowledged_beta
        )
    except BuildError as error:
        print(f"\nBUILD ABORTED\n\n{error}\n")
        return 1

    beta_note = (
        f"    NGS beta   {len(acknowledged_beta)} artifact(s) acknowledged; "
        f"docs/REFREEZE-NSRS.md\n"
        if acknowledged_beta
        else ""
    )
    print(
        f"\n=== BUILD COMPLETE in {time.monotonic() - started:.0f} s ==============\n"
        f"    installer  {installer}\n"
        f"    checksums  {checksums}\n"
        f"    self-test  {SELFTEST_REPORT}\n"
        f"{beta_note}\n"
        f"Not yet released. The session lead tags {version}, writes the release "
        f"notes naming what was verified, and uploads the installer and its "
        f"checksum (docs/DESIGN.md amendment #13). The install proof is human: "
        f"install on a clean profile and run one real job end to end "
        f"(docs/method/METHOD.md section 6)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
