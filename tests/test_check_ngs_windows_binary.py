"""The owner's NGS-binary check, tested without NGS's binary.

``review/wgs84-w0/check_ngs_windows_binary.py`` runs on the owner's Windows
machine against NGS's own ``htdp.exe`` - the one oracle nobody has run against
MCX's HTDP anchors (DESIGN.md #70, "still human"). It can only be trusted if
three things are true, and all three are testable here:

1. it hands HTDP exactly what the capture handed it - every run's stdin and
   every ``in.txt`` line, character for character;
2. it reads HTDP's output the way HTDP prints it, on Windows line endings
   too, and compares strings, never floats;
3. its verdict says what the docstring says it says.

The end-to-end tests stand a fake HTDP in for the binary - a Python script, run
as ``[python, fake.py]`` so the test runs on Windows as well - in a folder whose
name has spaces in it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "review" / "wgs84-w0" / "check_ngs_windows_binary.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_ngs_windows_binary", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load()
JOBS = checker.jobs_from_fixtures()


# ==========================================================================
# 1. It asks HTDP what the capture asked.
# ==========================================================================


def test_every_anchor_of_both_fixtures_is_driven():
    from tests.fixtures.htdp_anchors import HTDP_RUNS
    from tests.fixtures.htdp_near_tie_anchors import NEAR_TIE_RUNS

    assert len(JOBS) == len(HTDP_RUNS) + len(NEAR_TIE_RUNS) == 144
    ordinary = sum(len(j.records) for j in JOBS if j.fixture == "htdp_anchors")
    near = sum(len(j.records) for j in JOBS if j.fixture == "htdp_near_tie_anchors")
    assert (ordinary, near) == (1846, 382)


@pytest.mark.parametrize(
    "truth_file,fixture",
    [
        ("htdp_truth.json", "htdp_anchors"),
        ("near_tie_truth.json", "htdp_near_tie_anchors"),
    ],
)
def test_the_stdin_and_input_lines_are_the_captures_own(truth_file, fixture):
    """Character for character against the committed captures, not against the fixtures.

    Each fixture run keeps a subset of its capture run's records; HTDP treats
    each record independently, so the subset's lines must be exactly the
    capture's lines for those records, and the stdin exactly the capture's.
    """
    truth = json.loads(
        (REPO_ROOT / "review" / "wgs84-w0" / truth_file).read_text(encoding="utf-8")
    )
    by_id = {run["run_id"]: run for run in truth["runs"]}

    for job in (j for j in JOBS if j.fixture == fixture):
        captured = by_id[job.run_id]
        assert job.stdin == captured["stdin"], job.run_id
        assert set(checker.input_lines(job.records)) <= set(captured["input_lines"]), job.run_id


# ==========================================================================
# 2. It reads HTDP's print as printed.
# ==========================================================================


HTDP_OUT_CRLF = (
    " ***CAUTION: This file was processed using HTDP version 3.6.0  ***\r\n"
    " ***CAUTION: Coordinates in this file are in NAD_83(2011/CORS96/2007)***\r\n"
    "   43.8199914021   84.7699886492   601.071    P073H600\r\n"
    "   -1.0000000000   90.6000110961    -0.931    NEG ONE   \r\n"
    "P999H000 is outside of the modeled region.\r\n"
)


def test_the_parser_reads_htdps_records_on_windows_line_endings():
    printed = checker.parse_output(HTDP_OUT_CRLF)

    assert printed == {
        "P073H600": ("43.8199914021", "84.7699886492", "601.071"),
        "NEG ONE": ("-1.0000000000", "90.6000110961", "-0.931"),
    }


def test_the_banner_version_is_read_from_htdps_own_banner():
    banner = (
        " ********************************************************\r\n"
        "    HTDP (Horizontal Time-Dependent Positioning)         \r\n"
        "    SOFTWARE VERSION: 3.6.0   \r\n"
        "    VERSION DATE:     April 7, 2025       \r\n"
    )
    assert checker.banner_version(banner) == "3.6.0"
    assert checker.banner_version("no banner at all") is None


def _job(fixture="htdp_anchors", run_id="calfwd_2026-10-20"):
    return next(j for j in JOBS if j.fixture == fixture and j.run_id == run_id)


def _printed(job, change=None):
    """What HTDP would print for ``job``: the fixture's strings, with one changed."""
    printed = {r.name: (r.lat_out, r.lonw_out, r.h_out) for r in job.records}
    if change:
        name, index, value = change
        row = list(printed[name])
        row[index] = value
        printed[name] = tuple(row)
    return printed


def test_identical_strings_are_identical_and_a_last_digit_is_one_unit():
    job = _job()
    count, differences = checker.compare_job(job, _printed(job))
    assert (count, differences) == (24, [])

    count, differences = checker.compare_job(
        job, _printed(job, ("P073H600", 1, "84.7699886493"))
    )
    (d,) = differences
    assert (d.record, d.component, d.expected, d.got) == (
        "P073H600", "longitude", "84.7699886492", "84.7699886493"
    )
    assert d.units == Decimal("1")


def test_the_comparison_is_of_strings_not_floats():
    """``601.0710`` is the same float as ``601.071`` and not what HTDP prints."""
    job = _job()
    _count, differences = checker.compare_job(
        job, _printed(job, ("P073H600", 2, "601.0710"))
    )
    (d,) = differences
    assert d.component == "height" and d.units == 0


def test_a_height_difference_is_counted_in_millimetres():
    job = _job()
    _count, differences = checker.compare_job(
        job, _printed(job, ("P073H600", 2, "601.069"))
    )
    (d,) = differences
    assert d.units == Decimal("-2")


def test_a_record_htdp_did_not_print_is_a_difference():
    job = _job()
    printed = _printed(job)
    del printed["P073H600"]
    _count, differences = checker.compare_job(job, printed)
    (d,) = differences
    assert d.units is None and d.component == "record"


# ==========================================================================
# 3. The verdict is the docstring's.
# ==========================================================================


def _diff(units, fixture="htdp_anchors", record="R", run_id="run", in_scope=True,
          component="latitude"):
    return checker.Difference(
        fixture, run_id, record, component, "1.0", "1.0",
        None if units is None else Decimal(units), in_scope,
    )


def test_no_difference_agrees():
    assert checker.verdict([], 1846) == ("AGREES", [])


def test_one_unit_flips_at_the_stand_ins_rate_are_last_digit_only():
    """Six ordinary anchors and a hundred near ties: RECON's x87 stand-in, measured."""
    differences = [_diff("-1", record=f"P{n}") for n in range(6)]
    differences += [
        _diff("1" if n % 2 else "-1", fixture="htdp_near_tie_anchors", record=f"N{n}")
        for n in range(128)
    ]
    assert checker.verdict(differences, 1846) == ("LAST-DIGIT ONLY", [])


def test_more_than_one_unit_disagrees():
    outcome, reasons = checker.verdict([_diff("2")], 1846)
    assert outcome == "DISAGREES"
    assert "more than one in the last printed place" in reasons[0]


def test_a_missing_record_disagrees():
    outcome, reasons = checker.verdict([_diff(None)], 1846)
    assert outcome == "DISAGREES"
    assert "not printed" in reasons[0]


def test_more_than_one_percent_of_the_ordinary_anchors_is_a_pattern():
    """19 of 1,846 is over 1%; 18 is not. Ties are isolated; a rate is arithmetic."""
    eighteen = [_diff("1", record=f"P{n}") for n in range(18)]
    assert checker.verdict(eighteen, 1846)[0] == "LAST-DIGIT ONLY"

    outcome, reasons = checker.verdict(eighteen + [_diff("-1", record="P18")], 1846)
    assert outcome == "DISAGREES"
    assert "19 of 1846 ordinary anchors differ" in reasons[0]


def test_a_record_mcx_refuses_never_decides_the_verdict():
    """The x87 stand-in's EDGENOUT: 1,949 units, at HTDP's own region boundary."""
    refused = _diff("1949", fixture="htdp_near_tie_anchors", record="EDGENOUT",
                    in_scope=False)
    assert checker.verdict([refused], 1846) == ("LAST-DIGIT ONLY", [])
    assert checker.verdict([refused, _diff("2")], 1846)[0] == "DISAGREES"


def test_only_the_near_tie_edge_outside_records_are_out_of_scope():
    outside = [
        r.name
        for j in JOBS
        for r in j.records
        if checker.out_of_scope(r)
    ]
    assert len(outside) == 8
    assert all(name.startswith("EDGE") and name.endswith("OUT") for name in outside)


# ==========================================================================
# End to end, with a fake HTDP standing in for NGS's binary.
# ==========================================================================


FAKE_HTDP = r'''
import sys
from pathlib import Path

ANSWERS = {answers!r}
VERSION = {version!r}

stdin = sys.stdin.read()
print(" ********************************************************")
print("    HTDP (Horizontal Time-Dependent Positioning)")
print("    SOFTWARE VERSION: " + VERSION)
lines = Path("in.txt").read_text().splitlines()
with open("out.txt", "w", newline="\r\n") as out:
    out.write(" ***CAUTION: This file was processed using HTDP version 3.6.0  ***\n")
    for line in lines:
        name = line.split(",")[3]
        lat, lon, h = ANSWERS[name]
        out.write("%16s%16s%10s    %s\n" % (lat, lon, h, name))
'''


def _fake(tmp_path, jobs, version="3.6.0", change=None):
    folder = tmp_path / "Program Files (x86)" / "NGS HTDP"
    folder.mkdir(parents=True)
    answers = {}
    for job in jobs:
        for r in job.records:
            answers[r.name] = (r.lat_out, r.lonw_out, r.h_out)
    if change:
        name, index, value = change
        row = list(answers[name])
        row[index] = value
        answers[name] = tuple(row)
    script = folder / "fake htdp.py"
    script.write_text(FAKE_HTDP.format(answers=answers, version=version), encoding="utf-8")
    return script


def test_end_to_end_a_faithful_binary_agrees(tmp_path):
    jobs = [_job(), _job("htdp_near_tie_anchors", "neartie_12_1_0")]
    script = _fake(tmp_path, jobs)
    lines = []

    code = checker.check(script, jobs, lines.append, [sys.executable, str(script)])

    assert code == 0, lines
    assert "runs: 2; records compared: 30; identical: 30" in lines
    assert lines[-1] == "VERDICT: AGREES"


def test_end_to_end_a_two_unit_difference_disagrees_and_is_reported(tmp_path):
    jobs = [_job()]
    script = _fake(tmp_path, jobs, change=("P073H600", 0, "43.8199914023"))
    lines = []

    code = checker.check(script, jobs, lines.append, [sys.executable, str(script)])

    assert code == 1
    assert (
        "  DIFFERS  htdp_anchors calfwd_2026-10-20 P073H600 latitude: anchor "
        "43.8199914021  windows 43.8199914023  (+2 last-place units)"
    ) in lines
    assert "VERDICT: DISAGREES" in lines


def test_end_to_end_a_binary_that_is_not_v3_6_0_is_not_compared(tmp_path):
    jobs = [_job()]
    script = _fake(tmp_path, jobs, version="3.5.0")
    lines = []

    code = checker.check(script, jobs, lines.append, [sys.executable, str(script)])

    assert code == 2
    assert "COULD NOT RUN" in lines[-1] and "'3.5.0'" in lines[-1]


def test_a_path_with_no_binary_could_not_run(tmp_path):
    lines = []
    assert checker.check(tmp_path / "no htdp.exe", [_job()], lines.append) == 2
    assert lines == [f"COULD NOT RUN: no file at {tmp_path / 'no htdp.exe'}"]


def test_the_script_is_stdlib_only_and_imports_nothing_of_the_program():
    import ast

    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}, imported
