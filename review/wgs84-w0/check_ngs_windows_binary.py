"""Run NGS's OWN Windows htdp.exe over MCX's frozen HTDP anchors and compare, digit for digit.

    py review\\wgs84-w0\\check_ngs_windows_binary.py "C:\\path to\\htdp.exe"
    py review\\wgs84-w0\\check_ngs_windows_binary.py "C:\\path to\\htdp.exe" --report result.txt

Stdlib only, so plain ``py`` on Windows runs it; nothing is installed and
nothing in ``michspc`` is imported. Run it from anywhere: it finds the
fixtures beside itself. Paths with spaces are fine (the binary is started with
an argument list, never through a shell, and HTDP is only ever given the
relative names ``in.txt`` and ``out.txt`` inside a fresh temporary folder).

**Why this exists.** MCX's WGS 84 and ITRF conversions are held to HTDP
v3.6.0's printed output, and that output was captured from HTDP compiled in a
Linux container with gfortran on x86_64, whose double arithmetic is SSE2 (W0,
``review/wgs84-w0/RECON.md``). NGS's own Windows build is different: NGS
builds it ``gfortran -DNGS_PC_ENV -static -m32`` (its ``pc_build_readme.txt``,
quoted in RECON.md section 4),
32-bit, so its floating point is the x87's 80-bit registers. That build could
not be run in the container. **The x87 stand-in that could be run flipped the
last printed digit on 11 of 176 runs, one record each, by one unit of the 10th
decimal of a degree (RECON.md section 4).** So whether NGS's shipped binary
prints what MCX's anchors say it prints is the one part of the oracle nobody
has checked. This script is that check, for the owner's machine (DESIGN.md
#70, "still human"; docs/PLAN-wgs84.md section 7).

**What it does.** For every run in ``tests/fixtures/htdp_anchors.py`` (1,846
records, 76 runs) and ``tests/fixtures/htdp_near_tie_anchors.py`` (382
records), it writes the run's inputs to ``in.txt`` exactly as the capture did
(``LAT,LON_POSITIVE_WEST,EHT,NAME``, one record a line), feeds ``htdp.exe``
the run's recorded stdin character for character (TRFPOS, menu option 4, file
option 3), reads ``out.txt`` back, and compares HTDP's printed latitude,
longitude and height for each record with the fixture's - as STRINGS, the
digits HTDP printed, never as floats. It first reads the binary's banner and
refuses one that is not v3.6.0.

**How to read the result.**

* ``AGREES`` - every printed string identical. NGS's Windows build and the
  container's oracle are the same oracle at every anchor. Exit code 0.
* ``LAST-DIGIT ONLY`` - some records differ, every difference that bears on
  MCX is exactly ONE unit in the last printed place (1e-10 degree, about
  0.01 mm; or 0.001 m of height), and too few of the ordinary anchors differ
  to be a pattern. That is what RECON section 4's x87 stand-in showed, and
  what extended precision does at a rounding tie: the exact result sat within
  a hair of the boundary between two printed values, and 80-bit and 64-bit
  arithmetic landed on opposite sides of it. It is NOT a disagreement about
  the transformation; MCX's anchors and NGS's Windows program then differ at
  those records by the print's own resolution, which every verification
  statement MCX makes already allows. Expect it most in the near-tie fixture:
  those 382 inputs were TUNED to sit within an ulp or so of a tie (their
  ``note`` is the distance, in print units), so a flip there is the test
  working. Among the 1,846 ordinary anchors it should be rare. Exit code 0,
  with every difference listed.
* ``DISAGREES`` - any one of:
  - a difference of MORE than one unit in the last printed place, in any
    component of any record MCX converts;
  - a SYSTEMATIC pattern: more than 1% of the 1,846 ordinary anchors
    differing at all. Ties are isolated events, so a rate far above the
    stand-in's (below) is arithmetic, not rounding;
  - a record HTDP did not print, or printed in a form this script cannot
    read, or a run that produced no ``out.txt``.
  Any of these is a real disagreement between NGS's program and the anchors
  MCX is held to, and the WGS 84 release waits on it. Exit code 1.
* Could not run (no binary there, the banner is not v3.6.0, a run timed out):
  exit code 2. Nothing is concluded.

**Records MCX refuses do not decide the verdict.** Eight near-tie records
(role ``edge ... outside``) are inputs whose velocity lookup falls just
outside MCX's transcribed window; MCX refuses them, so no number it produces
depends on what HTDP prints for them. They are compared and listed, apart.
Two of them straddle HTDP's OWN region boundary at 50.0 N, where a lookup an
ulp to the north is computed from a different velocity model - so a build
that rounds differently there may print a different answer by centimetres.
That is HTDP's behaviour beyond Michigan, not a disagreement about it.

**What the x87 stand-in gives, measured here on 2026-10-21** (W0's build
``gfortran -O0 -mfpmath=387 -std=legacy -w *.f``, the same source): 2,093 of
2,228 records identical; 6 of the 1,846 ordinary anchors and 128 near-tie
records differ by exactly one unit; one record, ``EDGENOUT`` of run
``edge_12_1`` (refused by MCX, at the 50.0 N boundary), differs by 1,949
units of latitude. Verdict ``LAST-DIGIT ONLY``. And against the SSE2 build the
fixtures were captured from: 2,228 of 2,228 identical, ``AGREES`` - which is
the check that this script drives HTDP exactly as the capture did. If NGS's
``htdp.exe`` lands near the stand-in, it is the result RECON predicted.

Each difference is reported with its run, record, component, both strings and
its size in last-place units, signed (Windows minus anchor).
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"

EXPECTED_VERSION = "3.6.0"
"""htdp.f:27, ``HTDP_version = '3.6.0'``; printed in the banner (htdp.f:73-78)."""

RUN_TIMEOUT_S = 300

# HTDP's TRFPOS output record, 2f16.10,f10.3,4x,a (htdp.f:3292-3293), the
# same pattern W0's drive_htdp.py read the capture with. Trailing blanks and a
# CR are tolerated: splitlines() removes the CRLF, \s*$ anything left.
DATA_RE = re.compile(
    r"^\s*(-?\d+\.\d{10})\s+(-?\d+\.\d{10})\s+(-?\d+\.\d{3})\s{4}(\S.*?)\s*$"
)
VERSION_RE = re.compile(r"SOFTWARE VERSION:\s*(\S+)")

LAST_PLACE = {
    "latitude": Decimal("1e-10"),
    "longitude": Decimal("1e-10"),
    "height": Decimal("1e-3"),
}
"""One unit of HTDP's last printed place, per component (2f16.10,f10.3)."""

SYSTEMATIC_FRACTION = 0.01
"""More than 1% of the ordinary anchors differing is a pattern rather than
ties. RECON section 4's x87 stand-in differed on 11 of 45,408 records; on this
script's 1,846 ordinary anchors it differs on 6 (0.33%)."""


def out_of_scope(record) -> bool:
    """A record MCX refuses: a near-tie input whose lookup is outside its window."""
    return getattr(record, "role", "").endswith("outside")


@dataclass(frozen=True)
class Job:
    """One HTDP run to repeat: the recorded stdin, and the records it read."""

    fixture: str
    run_id: str
    stdin: str
    records: tuple  # the fixture's own record objects


@dataclass(frozen=True)
class Difference:
    fixture: str
    run_id: str
    record: str
    component: str
    expected: str
    got: str | None
    units: Decimal | None
    """Signed, Windows minus anchor, in last-place units; None when unreadable."""

    in_scope: bool = True
    """False for a record MCX refuses (``out_of_scope``): listed, never decisive."""


class CouldNotRun(Exception):
    """The binary could not be run as HTDP v3.6.0. Nothing is concluded."""


def load_fixture(name: str):
    """Import a fixture module by path - this script must not need ``tests`` importable."""
    path = FIXTURES / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_mcx_fixture_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


def jobs_from_fixtures() -> list[Job]:
    anchors = load_fixture("htdp_anchors")
    near_ties = load_fixture("htdp_near_tie_anchors")
    jobs = [
        Job("htdp_anchors", run.run_id, run.stdin, tuple(run.records))
        for run in anchors.HTDP_RUNS
    ]
    jobs += [
        Job("htdp_near_tie_anchors", run.run_id, run.stdin, tuple(run.records))
        for run in near_ties.NEAR_TIE_RUNS
    ]
    return jobs


def input_lines(records) -> list[str]:
    """``in.txt`` exactly as the capture wrote it: the strings HTDP read, then the name."""
    return [f"{r.lat_in},{r.lonw_in},{r.h_in},{r.name}" for r in records]


def parse_output(text: str) -> dict[str, tuple[str, str, str]]:
    """HTDP's printed records by name: ``{name: (lat, lonw, h)}``. CRLF-safe."""
    printed: dict[str, tuple[str, str, str]] = {}
    for line in text.splitlines():
        match = DATA_RE.match(line)
        if match:
            printed[match.group(4)] = (match.group(1), match.group(2), match.group(3))
    return printed


def banner_version(stdout: str) -> str | None:
    match = VERSION_RE.search(stdout)
    return match.group(1) if match else None


def compare_job(job: Job, printed: dict[str, tuple[str, str, str]]) -> tuple[int, list[Difference]]:
    """``(records compared, differences)`` for one run, string against string."""
    differences: list[Difference] = []
    for record in job.records:
        expected = {
            "latitude": record.lat_out,
            "longitude": record.lonw_out,
            "height": record.h_out,
        }
        scope = not out_of_scope(record)
        got = printed.get(record.name)
        if got is None:
            differences.append(
                Difference(job.fixture, job.run_id, record.name, "record",
                           "printed", None, None, scope)
            )
            continue
        for component, value in zip(("latitude", "longitude", "height"), got):
            if value == expected[component]:
                continue
            units = (Decimal(value) - Decimal(expected[component])) / LAST_PLACE[component]
            differences.append(
                Difference(job.fixture, job.run_id, record.name, component,
                           expected[component], value, units, scope)
            )
    return len(job.records), differences


def verdict(differences: list[Difference], ordinary_count: int) -> tuple[str, list[str]]:
    """``("AGREES" | "LAST-DIGIT ONLY" | "DISAGREES", reasons)``, by the docstring's rules.

    Only in-scope differences decide; a record MCX refuses is listed by the
    caller and never makes the verdict worse or better.
    """
    deciding = [d for d in differences if d.in_scope]
    if not differences:
        return "AGREES", []
    reasons: list[str] = []
    for d in deciding:
        if d.units is None:
            reasons.append(f"{d.fixture} {d.run_id} {d.record}: not printed or not readable")
        elif abs(d.units) > 1:
            reasons.append(
                f"{d.fixture} {d.run_id} {d.record} {d.component}: "
                f"{d.units:+} units, more than one in the last printed place"
            )
    differing = {(d.run_id, d.record) for d in deciding if d.fixture == "htdp_anchors"}
    if ordinary_count and len(differing) > SYSTEMATIC_FRACTION * ordinary_count:
        reasons.append(
            f"{len(differing)} of {ordinary_count} ordinary anchors differ, more "
            f"than {SYSTEMATIC_FRACTION:.0%}: a pattern, not rounding ties"
        )
    return ("DISAGREES" if reasons else "LAST-DIGIT ONLY"), reasons


def tally(differences: list[Difference]) -> list[str]:
    """Per fixture and component, how many one-unit differences of each sign. Information only."""
    lines = []
    for fixture in ("htdp_anchors", "htdp_near_tie_anchors"):
        for component in LAST_PLACE:
            chosen = [
                d for d in differences
                if d.in_scope and d.fixture == fixture and d.component == component
                and d.units is not None and abs(d.units) == 1
            ]
            if chosen:
                up = sum(1 for d in chosen if d.units > 0)
                lines.append(
                    f"  {fixture} {component}: {len(chosen)} one-unit "
                    f"differences, {up} up, {len(chosen) - up} down"
                )
    return lines


def run_htdp(command: list[str], stdin: str, lines: list[str]) -> tuple[str, str | None]:
    """Run HTDP once in a fresh folder: ``(stdout, out.txt text or None)``.

    ``command`` is ``[path to htdp.exe]``; it is a list so the suite can stand
    a fake HTDP in for the binary (``[python, fake.py]``) on any platform.
    """
    with tempfile.TemporaryDirectory(prefix="mcx-htdp-check-") as folder:
        work = Path(folder)
        # LF line endings, as the capture wrote in.txt (drive_htdp.py).
        (work / "in.txt").write_bytes(("\n".join(lines) + "\n").encode("ascii"))
        try:
            completed = subprocess.run(
                list(command),
                input=stdin.encode("ascii"),
                cwd=str(work),
                capture_output=True,
                timeout=RUN_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as error:
            raise CouldNotRun(
                f"HTDP did not finish within {RUN_TIMEOUT_S} s; it is probably "
                f"waiting for input the recorded stdin does not give it"
            ) from error
        stdout = completed.stdout.decode("latin-1")
        output = work / "out.txt"
        text = output.read_bytes().decode("latin-1") if output.is_file() else None
    return stdout, text


def check(binary: Path, jobs: list[Job] | None = None, log=print,
          command: list[str] | None = None) -> int:
    """Run every job and report. Returns the exit code the docstring states."""
    if not binary.is_file():
        log(f"COULD NOT RUN: no file at {binary}")
        return 2
    jobs = jobs if jobs is not None else jobs_from_fixtures()
    command = command or [str(binary)]

    compared = 0
    ordinary_count = 0
    differences: list[Difference] = []
    try:
        for index, job in enumerate(jobs):
            stdout, text = run_htdp(command, job.stdin, input_lines(job.records))
            if index == 0:
                version = banner_version(stdout)
                if version != EXPECTED_VERSION:
                    raise CouldNotRun(
                        f"the binary's banner says SOFTWARE VERSION {version!r}; "
                        f"the anchors are HTDP {EXPECTED_VERSION}'s, so a "
                        f"comparison with any other version means nothing"
                    )
            if text is None:
                compared += len(job.records)
                if job.fixture == "htdp_anchors":
                    ordinary_count += len(job.records)
                differences.extend(
                    Difference(job.fixture, job.run_id, r.name, "record",
                               "printed", None, None)
                    for r in job.records
                )
                log(f"  {job.run_id}: HTDP wrote no out.txt")
                continue
            count, found = compare_job(job, parse_output(text))
            compared += count
            if job.fixture == "htdp_anchors":
                ordinary_count += count
            differences.extend(found)
    except CouldNotRun as error:
        log(f"COULD NOT RUN: {error}")
        return 2

    matched = compared - len({(d.fixture, d.run_id, d.record) for d in differences})
    log(f"HTDP binary: {binary}")
    log(f"runs: {len(jobs)}; records compared: {compared}; identical: {matched}")
    for title, wanted in (
        ("records MCX converts", True),
        ("records MCX refuses (outside its window; listed, not decisive)", False),
    ):
        chosen = [d for d in differences if d.in_scope is wanted]
        if not chosen:
            continue
        log(f"differences, {title}:")
        for d in chosen:
            if d.units is None:
                log(f"  MISSING  {d.fixture} {d.run_id} {d.record}")
            else:
                log(
                    f"  DIFFERS  {d.fixture} {d.run_id} {d.record} {d.component}: "
                    f"anchor {d.expected}  windows {d.got}  "
                    f"({d.units:+} last-place units)"
                )
    for line in tally(differences):
        log(line)
    outcome, reasons = verdict(differences, ordinary_count)
    log(f"VERDICT: {outcome}")
    for reason in reasons:
        log(f"  - {reason}")
    return 1 if outcome == "DISAGREES" else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("binary", type=Path, help="NGS's htdp.exe (v3.6.0)")
    parser.add_argument("--report", type=Path, help="also write the result here")
    arguments = parser.parse_args(argv)

    lines: list[str] = []

    def log(line: str) -> None:
        lines.append(line)
        print(line, flush=True)

    code = check(arguments.binary, log=log)
    if arguments.report is not None:
        arguments.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
