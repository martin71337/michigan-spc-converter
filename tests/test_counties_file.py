"""The shipped county file and its one reader, ``michspc.fileio.counties``.

The digest gate is tested by altering ONE coordinate of a copy; the structural
gates by altering copies read with ``verify_checksum=False`` (the only reason
that parameter exists). The file's provenance - a derived serialization of
TIGER 2025, byte-identical to nothing under ``review/`` (build gate 6) - and,
where the 84 MB TIGER zip is on this machine, its reproducibility.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from michspc.fileio import counties
from michspc.fileio.counties import CountyDataError
from michspc.spc.autozone import CountySet

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED = REPO_ROOT / "data" / counties.COUNTIES_FILENAME
TIGER_ZIP = REPO_ROOT / "review" / "autozone-r0" / "raw" / "tiger" / "tl_2025_us_county.zip"
DERIVE = REPO_ROOT / "review" / "autozone-z0" / "derive_counties.py"


def test_the_shipped_file_is_the_pinned_one():
    raw = SHIPPED.read_bytes()
    assert len(raw) == counties.COUNTIES_BYTES
    assert hashlib.sha256(raw).hexdigest() == counties.COUNTIES_SHA256
    assert b"\r" not in raw  # LF only: .gitattributes marks it -text


def test_the_gitattributes_keep_its_bytes():
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert f"data/{counties.COUNTIES_FILENAME} -text" in attributes


def test_it_loads_as_83_counties_with_unique_fips(tmp_path):
    county_set = counties.load_counties()
    assert isinstance(county_set, CountySet)
    assert len(county_set.counties) == 83
    assert len({c.fips for c in county_set.counties}) == 83
    assert county_set.source == counties.COUNTIES_SOURCE
    assert counties.default_counties() is counties.default_counties()


def test_every_vertex_is_tigers_own_double_unrounded():
    """The file states coordinates exactly as the shapefile stores them: TIGER
    publishes six decimal places of a degree, and repr round-trips the double,
    so no value carries more than six - and plenty carry exactly six, so the
    file was not rounded coarser either."""
    document = json.loads(SHIPPED.read_text(encoding="utf-8"))
    decimals = [
        len(repr(v).split(".")[1])
        for c in document["counties"]
        for r in c["rings"]
        for p in r
        for v in p
    ]
    assert max(decimals) == 6
    assert sum(d == 6 for d in decimals) > 100000
    assert sum(len(r) for c in document["counties"] for r in c["rings"]) == 72545


def _copy(tmp_path: Path, mutate) -> Path:
    document = json.loads(SHIPPED.read_text(encoding="utf-8"))
    mutate(document)
    path = tmp_path / counties.COUNTIES_FILENAME
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_one_altered_coordinate_is_refused_by_the_digest(tmp_path):
    # Move one vertex of Ingham by 1e-6 degree (about 0.1 m): the file is still
    # perfectly well-formed, so only the digest can catch it.
    text = SHIPPED.read_text(encoding="utf-8")
    original = "[-84.140794,42.485895]"
    assert text.count(original) >= 1, "pick a vertex present in the file"
    path = tmp_path / counties.COUNTIES_FILENAME
    path.write_bytes(text.replace(original, "[-84.140795,42.485895]", 1).encode("ascii"))
    with pytest.raises(CountyDataError, match="does not match the county file") as caught:
        counties.load_counties(path)
    assert counties.COUNTIES_SHA256 in str(caught.value)
    # ...and the same bytes pass the structural checks: the digest is the gate.
    counties.load_counties(path, verify_checksum=False)


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(CountyDataError, match="Could not read"):
        counties.load_counties(tmp_path / "absent.json")


@pytest.mark.parametrize(
    "mutate, problem",
    [
        (lambda d: d.update(format="something else"), "format tag"),
        (lambda d: d["counties"].pop(), "holds 82 counties"),
        (lambda d: d["counties"][1].update(fips=d["counties"][0]["fips"]), "more than one county has the fips"),
        (lambda d: d["counties"][1].update(name=d["counties"][0]["name"]), "more than one county has the name"),
        (lambda d: d["counties"][0].update(fips="39001"), "not a Michigan"),
        (lambda d: d["counties"][0]["rings"][0].pop(), "not closed"),
        (lambda d: d["counties"][0]["rings"][0].__setitem__(5, [float("nan"), 44.0]), "finite"),
        (lambda d: d["counties"][0]["rings"][0].__setitem__(5, [-84.0, 52.0]), "outside Michigan"),
        (lambda d: d["counties"][0]["rings"][0].__setitem__(5, [True, 44.0]), "finite"),
        (lambda d: d["counties"][0].update(rings=[]), "has no rings"),
        (lambda d: d["counties"][0].update(rings=[[[-84.0, 44.0], [-84.0, 44.0]]]), "fewer than 4"),
        (lambda d: d["counties"][73].update(name="Saint Clair"), "names counties differently"),
        (lambda d: d["counties"][0].update(fips="26999"), "disagree about which counties"),
    ],
)
def test_structural_refusals_name_the_problem(tmp_path, mutate, problem):
    path = _copy(tmp_path, mutate)
    with pytest.raises(CountyDataError) as caught:
        counties.load_counties(path, verify_checksum=False)
    assert problem in str(caught.value)
    assert str(path) in str(caught.value)


def test_the_county_at_index_73_is_st_clair():
    # The renaming case above edits index 73; pin that it is St. Clair (26147),
    # whose name the statute and TIGER both spell "St. Clair".
    document = json.loads(SHIPPED.read_text(encoding="utf-8"))
    assert document["counties"][73]["name"] == "St. Clair"
    assert document["counties"][73]["fips"] == "26147"


def test_the_file_is_byte_identical_to_nothing_under_review():
    # Build gate 6 refuses a bundled file whose bytes equal any review/ file.
    # Same rule, applied in the suite: compare against every review/ file of
    # the same size.
    size = SHIPPED.stat().st_size
    for path in (REPO_ROOT / "review").rglob("*"):
        if path.is_file() and path.stat().st_size == size:
            assert hashlib.sha256(path.read_bytes()).hexdigest() != counties.COUNTIES_SHA256, path


@pytest.mark.skipif(not TIGER_ZIP.is_file(), reason="TIGER zip (84 MB, git-ignored) not on this machine")
def test_the_derivation_reproduces_the_shipped_file(tmp_path):
    out = tmp_path / counties.COUNTIES_FILENAME
    result = subprocess.run(
        [sys.executable, "-I", str(DERIVE), str(TIGER_ZIP), str(out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert hashlib.sha256(out.read_bytes()).hexdigest() == counties.COUNTIES_SHA256
