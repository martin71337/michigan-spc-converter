"""The re-freeze checklist is a MECHANISM, not a memory (DESIGN.md #61).

This program ships numbers derived from NGS products that NGS has published as
beta, ahead of the official SPCS2022 / NATRF2022 release. The owner's recorded
decision permits that; what it depends on is that every such number can be
found again and re-checked when NGS publishes. Every beta-derived artifact
therefore carries the literal token ``NGS beta`` with its capture date, and
``docs/REFREEZE-NSRS.md`` maps each one to the harness that recaptures it and
the pin that authenticates it.

**A checklist maintained by hand rots in both directions**, and both failures
are silent:

* an artifact gains the token and nobody adds its row, so at re-freeze it is
  simply missed - beta numbers stay in a sealed-work program after the
  official values exist; and
* an artifact loses the token, or is renamed or deleted, and its row survives -
  so the checklist sends the next reader to recapture something that is not
  there, and looks complete while doing it.

So this module reads BOTH the tree and the document and requires them to agree.
The scanners are pure functions over paths and text, exercised against
synthetic inputs below as well as against the real repository, because a
scanner that silently found nothing would pass every assertion here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = REPO_ROOT / "docs" / "REFREEZE-NSRS.md"

BETA_TOKENS = ("NGS beta", "NGS BETA")
"""The literal this mechanism looks for, in both the casings the repository
uses - prose says "NGS beta", a section heading shouts it."""

SCANNED_ROOTS = ("michspc", "tests/fixtures")
"""Where a beta-derived artifact may live.

``michspc`` is the shipped program: registry records, citations, and the job
record's own prose. ``tests/fixtures`` is where frozen NGS truth lives. The
review harnesses under ``review/`` are deliberately NOT scanned - they are the
recapture machinery and NGS's own captured bytes, named in the document's
second table, and they carry NGS's wording rather than this program's token.
"""

_TABLE_HEADING = "## Tagged artifacts"
_BACKTICKED = re.compile(r"`([^`]+)`")


def tagged_files(root: Path, scanned=SCANNED_ROOTS) -> set[str]:
    """Every scanned file carrying a beta token, as repo-relative POSIX paths.

    Text files only, and a file that cannot be decoded as UTF-8 is skipped
    rather than guessed at: the token is ASCII, so a file the token could hide
    in is a file that decodes.
    """
    found: set[str] = set()
    for prefix in scanned:
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
                found.add(path.relative_to(root).as_posix())
    return found


def artifact_rows(document: str) -> list[dict[str, str]]:
    """The rows of the checklist's "Tagged artifacts" table.

    The document states this format and calls it load-bearing: inside that
    section, a table row's FIRST cell is a backticked repository path and
    nothing else. The header row and the ``| --- |`` separator are skipped by
    that same rule - neither holds a backticked path.
    """
    rows: list[dict[str, str]] = []
    in_section = False
    for line in document.splitlines():
        if line.startswith("## "):
            in_section = line.strip() == _TABLE_HEADING
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        first = _BACKTICKED.fullmatch(cells[0])
        if first is None:
            continue
        rows.append(
            {
                "artifact": first.group(1),
                "carries": cells[1],
                "harness": cells[2],
                "pin": cells[3],
            }
        )
    return rows


def _document() -> str:
    return CHECKLIST.read_text(encoding="utf-8")


# ==========================================================================
# The two directions.
# ==========================================================================


def test_the_checklist_exists_and_states_what_re_freezing_is():
    document = _document()

    assert "docs/PLAN-nsrs-modernization.md" in document
    assert "DESIGN.md" in document
    # The trigger and the gate the plan promises, both named rather than
    # assumed: the flag does not exist yet, and the document says so.
    assert "The trigger" in document
    assert "N8" in document
    assert "acknowledgement flag" in document


def test_every_tagged_file_in_the_tree_is_listed_in_the_checklist():
    """Direction one: the checklist cannot MISS an artifact."""
    listed = {row["artifact"] for row in artifact_rows(_document())}
    found = tagged_files(REPO_ROOT)

    missing = sorted(found - listed)
    assert not missing, (
        f"these files carry an NGS beta token and are not listed in "
        f"{CHECKLIST.name}: {missing}. Every beta-derived artifact needs its "
        f"recapture harness and its authenticating pin written down, or it is "
        f"missed when NGS publishes."
    )


def test_every_listed_artifact_still_exists_and_still_carries_the_token():
    """Direction two: the checklist cannot OUTLIVE an artifact."""
    rows = artifact_rows(_document())
    assert rows, "the checklist's artifact table parsed to nothing"

    for row in rows:
        path = REPO_ROOT / row["artifact"]
        assert path.is_file(), (
            f"{CHECKLIST.name} lists {row['artifact']}, which does not exist. "
            f"A row that outlives its artifact sends the next reader to "
            f"recapture something that is not there."
        )
        text = path.read_text(encoding="utf-8")
        assert any(token in text for token in BETA_TOKENS), (
            f"{CHECKLIST.name} lists {row['artifact']} as beta-derived, but "
            f"the file no longer carries an NGS beta token. Either the "
            f"artifact was re-frozen - in which case the row goes, with a "
            f"DESIGN.md amendment - or the token was lost."
        )


def test_every_row_names_a_harness_and_a_pin_that_exist():
    """A row is only worth having if both of the paths on it are real."""
    for row in artifact_rows(_document()):
        harness = _BACKTICKED.search(row["harness"])
        assert harness is not None, f"no harness path on the {row['artifact']} row"
        assert (REPO_ROOT / harness.group(1)).is_file(), (
            f"{row['artifact']}'s recapture harness {harness.group(1)} does "
            f"not exist"
        )

        pin = _BACKTICKED.search(row["pin"])
        assert pin is not None, f"no pin named on the {row['artifact']} row"
        pin_path = pin.group(1).split("::")[0]
        assert (REPO_ROOT / pin_path).is_file(), (
            f"{row['artifact']}'s authenticating pin {pin_path} does not exist"
        )

        assert row["carries"], f"the {row['artifact']} row says nothing about what it carries"


def test_the_artifacts_actually_expected_today_are_all_there():
    """Named, so that a scanner quietly matching nothing cannot pass.

    These four are the beta surface as of H5: the zone registry, the frame
    registry, the job record's SPCS2022 prose, and the anchor fixture. A fifth
    is fine - it must simply be listed - but these four disappearing would mean
    the scan stopped working rather than the repository being clean.
    """
    found = tagged_files(REPO_ROOT)

    assert "michspc/spc/zones.py" in found
    assert "michspc/spc/frames.py" in found
    assert "michspc/fileio/report.py" in found
    assert "tests/fixtures/spcs2022_engine_anchors.py" in found


# ==========================================================================
# Anti-vacuousness: both scanners, fed inputs that must fail.
# ==========================================================================


def test_the_scanner_finds_a_tagged_file_it_has_not_seen_before(tmp_path):
    """An unlisted artifact must be FOUND, not merely absent from a list."""
    (tmp_path / "michspc" / "spc").mkdir(parents=True)
    (tmp_path / "michspc" / "spc" / "new_registry.py").write_text(
        "# captured 2027-01-01. NGS beta\n", encoding="utf-8"
    )
    (tmp_path / "michspc" / "spc" / "ordinary.py").write_text(
        "# nothing pre-release here\n", encoding="utf-8"
    )

    found = tagged_files(tmp_path)

    assert found == {"michspc/spc/new_registry.py"}


def test_the_scanner_finds_the_shouted_casing_too(tmp_path):
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "anchors.py").write_text(
        '"""**NGS BETA. Capture date 2027-01-01.**"""\n', encoding="utf-8"
    )

    assert tagged_files(tmp_path) == {"tests/fixtures/anchors.py"}


def test_the_scanner_ignores_files_outside_the_scanned_roots(tmp_path):
    """``review/`` holds NGS's own captured bytes and the harnesses.

    They are named in the document's second table, not the first, and pulling
    them into this one would make the checklist a list of every file that
    mentions the word.
    """
    (tmp_path / "review" / "nsrs-n0").mkdir(parents=True)
    (tmp_path / "review" / "nsrs-n0" / "capture.py").write_text(
        "# NGS beta\n", encoding="utf-8"
    )

    assert tagged_files(tmp_path) == set()


def test_the_row_parser_reads_the_documents_own_format():
    rows = artifact_rows(
        "\n".join(
            [
                "# heading",
                "| `not/in/a/section.py` | x | `h.py` | `t.py` |",
                _TABLE_HEADING,
                "| Artifact | What | Harness | Pin |",
                "| --- | --- | --- | --- |",
                "| `michspc/spc/zones.py` | records | `review/c.py` | `tests/t.py` |",
                "## Something else",
                "| `after/the/section.py` | x | `h.py` | `t.py` |",
            ]
        )
    )

    assert [row["artifact"] for row in rows] == ["michspc/spc/zones.py"]
    assert rows[0]["harness"] == "`review/c.py`"
    assert rows[0]["pin"] == "`tests/t.py`"


def test_a_stale_row_is_visible_to_the_parser():
    """The shape direction two catches: a row for a file that is gone."""
    rows = artifact_rows(
        "\n".join(
            [
                _TABLE_HEADING,
                "| Artifact | What | Harness | Pin |",
                "| --- | --- | --- | --- |",
                "| `michspc/spc/deleted_registry.py` | gone | `review/c.py` | `tests/t.py` |",
            ]
        )
    )

    assert rows[0]["artifact"] == "michspc/spc/deleted_registry.py"
    assert not (REPO_ROOT / rows[0]["artifact"]).exists()


@pytest.mark.parametrize(
    "line",
    [
        "| Artifact | What it carries | Recapture harness | Authenticating pin |",
        "| --- | --- | --- | --- |",
        "| michspc/spc/zones.py | unbackticked | `h.py` | `t.py` |",
        "| `a.py` and `b.py` | two paths in one cell | `h.py` | `t.py` |",
    ],
)
def test_the_row_parser_rejects_a_first_cell_that_is_not_one_backticked_path(line):
    """The format the document declares, enforced rather than described.

    A row whose first cell is not exactly one backticked path is not a row -
    which is how the header and separator are skipped without naming them, and
    why a cell naming two files cannot half-register both.
    """
    assert artifact_rows("\n".join([_TABLE_HEADING, line])) == []
