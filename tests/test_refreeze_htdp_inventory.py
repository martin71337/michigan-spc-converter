"""The HTDP re-freeze checklist is a MECHANISM, not a memory (DESIGN.md #70).

MCX's WGS 84 and ITRF conversions reproduce NGS's HTDP v3.6.0, one commit of
it, and everything that holds them to it - the transcribed constants, the
frozen anchors, the job record's measured figures, the frozen bundle's own
anchor, the tripwire's frozen value - was taken from that commit. When NGS
publishes another, every one of those must be recaptured
(``docs/REFREEZE-HTDP.md``). This module is the half of that obligation that
cannot be forgotten: it reads the tree and the document and requires them to
agree, both ways, on the pattern of ``tests/test_refreeze_inventory.py``.

**The token is the commit id itself**, ``htdp_data.HTDP_COMMIT``, not a word
chosen for the purpose. So when a re-freeze moves ``HTDP_COMMIT`` to a new
release, every artifact still carrying the old id stops carrying the token,
direction two below fails, and it names each artifact not yet recaptured.

The scanner and the row parser are exercised against synthetic inputs as well
as against the real repository, because a scanner that silently found nothing
would pass every assertion here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from michspc.spc import htdp_data
from tests.test_refreeze_inventory import _BACKTICKED, _TABLE_HEADING, artifact_rows

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = REPO_ROOT / "docs" / "REFREEZE-HTDP.md"

HTDP_TOKEN = htdp_data.HTDP_COMMIT
"""The commit the program transcribes - the one statement of it."""

SCANNED_ROOTS = ("michspc", "tests/fixtures", "tools")
"""Where an HTDP-derived artifact may live: the shipped program, the frozen
NGS truth the suite holds it to, and the tools - the tripwire carries the
frozen commit it watches. ``review/`` is deliberately NOT scanned: it holds
NGS's source, the captures of its binary, and the harnesses that re-create
them, named in the document's second table."""


def tagged_files(root: Path, token: str = HTDP_TOKEN, scanned=SCANNED_ROOTS) -> set[str]:
    """Every scanned text file carrying ``token``, as repo-relative POSIX paths.

    The same rules as the NSRS scanner: text files only, ``.pyc`` and ``.bin``
    skipped, and a file that does not decode as UTF-8 skipped rather than
    guessed at - the token is ASCII hexadecimal.
    """
    found: set[str] = set()
    for prefix in scanned:
        base = root / prefix
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix in {".pyc", ".pyo", ".bin"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if token in text:
                found.add(path.relative_to(root).as_posix())
    return found


def _document() -> str:
    return CHECKLIST.read_text(encoding="utf-8")


def _test_function_exists(pin: str) -> bool:
    """``tests/x.py::name`` names a real top-level test function in a real file."""
    path, _sep, name = pin.partition("::")
    source = REPO_ROOT / path
    if not source.is_file():
        return False
    if not name:
        return True
    tree = ast.parse(source.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.FunctionDef) and node.name == name for node in tree.body
    )


# ==========================================================================
# The document states the obligation.
# ==========================================================================


def test_the_checklist_exists_and_states_the_four_steps():
    document = _document()

    assert HTDP_TOKEN in document
    assert f"HTDP v{htdp_data.HTDP_VERSION}" in document
    assert "DESIGN.md **#70**" in document
    assert "docs/PLAN-wgs84.md" in document
    assert "## The trigger" in document
    assert "tools/nsrs_tripwire.py" in document
    for step in (
        "1. **Recapture W0 with `review/wgs84-w0/drive_htdp.py`.**",
        "2. **Regenerate the fixtures with their generators.**",
        "3. **Re-run the transcription pins and every gate.**",
        "4. **Re-release consciously.**",
    ):
        assert step in document
    assert "review/wgs84-w0/check_ngs_windows_binary.py" in document


def test_every_path_the_checklist_names_exists():
    """A standing document that sends a reader to a file that is not there rots."""
    document = _document()
    named = {
        match.split()[0]
        for match in _BACKTICKED.findall(document)
        if match.startswith(("review/", "docs/", "tests/", "michspc/", "tools/"))
        # Written by the tripwire when it fires, and a placeholder for the
        # next release's source directory: neither exists until then.
        and not match.startswith("review/tripwire/")
        and "<" not in match
        and "*" not in match  # the scanned roots, as globs
    }
    assert "review/wgs84-w0/drive_htdp.py" in named
    missing = sorted(
        path for path in named if not (REPO_ROOT / path.split("::")[0]).exists()
    )
    assert not missing, missing


# ==========================================================================
# The two directions.
# ==========================================================================


def test_every_htdp_derived_file_in_the_tree_is_listed():
    """Direction one: the checklist cannot MISS an artifact."""
    listed = {row["artifact"] for row in artifact_rows(_document())}
    missing = sorted(tagged_files(REPO_ROOT) - listed)

    assert not missing, (
        f"these files carry HTDP's frozen commit {HTDP_TOKEN} and are not "
        f"listed in {CHECKLIST.name}: {missing}. Every HTDP-derived artifact "
        f"needs its recapture and its authenticating pin written down, or it "
        f"is missed when NGS changes HTDP."
    )


def test_every_listed_artifact_exists_and_still_carries_the_commit():
    """Direction two: the checklist cannot OUTLIVE an artifact - or a re-freeze."""
    rows = artifact_rows(_document())
    assert rows, "the checklist's artifact table parsed to nothing"

    for row in rows:
        path = REPO_ROOT / row["artifact"]
        assert path.is_file(), f"{CHECKLIST.name} lists {row['artifact']}, which does not exist"
        assert HTDP_TOKEN in path.read_text(encoding="utf-8"), (
            f"{CHECKLIST.name} lists {row['artifact']} as HTDP-derived, but it "
            f"does not carry the commit michspc.spc.htdp_data transcribes, "
            f"{HTDP_TOKEN}. Either it was recaptured from a different HTDP "
            f"and the transcription was not (or the reverse), or it lost its "
            f"provenance."
        )


def test_every_row_names_a_recapture_and_a_pin_that_exist():
    for row in artifact_rows(_document()):
        recapture = _BACKTICKED.search(row["harness"])
        assert recapture is not None, f"no recapture path on the {row['artifact']} row"
        assert (REPO_ROOT / recapture.group(1)).is_file(), recapture.group(1)

        pin = _BACKTICKED.search(row["pin"])
        assert pin is not None, f"no pin named on the {row['artifact']} row"
        assert _test_function_exists(pin.group(1)), (
            f"{row['artifact']}'s authenticating pin {pin.group(1)} does not exist"
        )
        assert row["carries"], f"the {row['artifact']} row says nothing it carries"


def test_the_artifacts_actually_expected_today_are_all_there():
    """Named, so that a scanner quietly matching nothing cannot pass.

    The HTDP surface as of W6: the transcription (constants and arithmetic),
    the frame registry, the job record's measured figures, the bundle's own
    anchor, the three fixtures and the tripwire. A tenth is fine - it must be
    listed - but these disappearing would mean the scan stopped working.
    """
    assert tagged_files(REPO_ROOT) >= {
        "michspc/spc/htdp_data.py",
        "michspc/spc/htdp.py",
        "michspc/spc/frames.py",
        "michspc/fileio/report.py",
        "michspc/selftest.py",
        "tests/fixtures/htdp_anchors.py",
        "tests/fixtures/htdp_near_tie_anchors.py",
        "tests/fixtures/htdp_w3_anchors.py",
        "tools/nsrs_tripwire.py",
    }


def test_the_job_records_htdp_figures_are_the_ones_the_row_describes():
    """report.py's row is about real constants: they exist and quote HTDP's figures."""
    from michspc.fileio import report

    assert report.HTDP_ANCHOR_RECORD_COUNT == "1,846"
    assert "9.2e-6 m north" in report.ROUND_TRIP_NON_CLOSURE
    assert report.ROUND_TRIP_HEIGHT_TO_M == 610.0


# ==========================================================================
# Anti-vacuousness.
# ==========================================================================


def test_the_scanner_finds_a_tagged_file_in_each_root(tmp_path):
    for prefix in SCANNED_ROOTS:
        (tmp_path / prefix).mkdir(parents=True, exist_ok=True)
        (tmp_path / prefix / "new.py").write_text(
            f"# from HTDP commit {HTDP_TOKEN}\n", encoding="utf-8"
        )
    (tmp_path / "michspc" / "ordinary.py").write_text("# nothing\n", encoding="utf-8")

    assert tagged_files(tmp_path) == {f"{prefix}/new.py" for prefix in SCANNED_ROOTS}


def test_the_scanner_ignores_review_and_binaries(tmp_path):
    (tmp_path / "review" / "wgs84-w0").mkdir(parents=True)
    (tmp_path / "review" / "wgs84-w0" / "htdp_truth.json").write_text(
        HTDP_TOKEN, encoding="utf-8"
    )
    (tmp_path / "michspc").mkdir()
    (tmp_path / "michspc" / "cached.pyc").write_text(HTDP_TOKEN, encoding="utf-8")

    assert tagged_files(tmp_path) == set()


def test_a_file_carrying_an_older_commit_is_not_tagged(tmp_path):
    """The re-freeze case: an artifact left on the previous HTDP stops matching.

    Seeded as a file carrying v3.5.0's commit (``1dbd6a15...``, the tag
    ``v3.5.0`` on github.com/noaa-ngs/HTDP): it is not tagged, so a row for it
    fails direction two.
    """
    (tmp_path / "michspc").mkdir()
    (tmp_path / "michspc" / "stale.py").write_text(
        "# from HTDP commit 1dbd6a1513bbfa067fd9f2c977f8c42e5d8cfbc4\n", encoding="utf-8"
    )

    assert tagged_files(tmp_path) == set()


@pytest.mark.parametrize(
    "pin,exists",
    [
        ("tests/test_htdp.py", True),
        ("tests/test_htdp.py::test_the_generator_reproduces_the_fixture_byte_for_byte", True),
        ("tests/test_htdp.py::test_no_such_test", False),
        ("tests/test_no_such_file.py", False),
    ],
)
def test_the_pin_check_tells_a_real_test_from_a_misnamed_one(pin, exists):
    assert _test_function_exists(pin) is exists


def test_the_row_parser_is_the_nsrs_checklists():
    """One format, one parser: the NSRS document's, imported, not copied."""
    rows = artifact_rows(
        "\n".join(
            [
                _TABLE_HEADING,
                "| Artifact | What | Recapture | Pin |",
                "| --- | --- | --- | --- |",
                "| `michspc/spc/htdp_data.py` | constants | `h.f` | `tests/t.py` |",
            ]
        )
    )
    assert [row["artifact"] for row in rows] == ["michspc/spc/htdp_data.py"]
