"""HTDP truth for work package W3's end-to-end pins, frozen from NGS's binary. Deterministic.

    python3 -I review/wgs84-w3/make_w3_anchors.py --capture BINARY   # drive HTDP, freeze
    python3 -I review/wgs84-w3/make_w3_anchors.py                    # write the fixture
    python3 -I review/wgs84-w3/make_w3_anchors.py --check            # exit 1 if it differs

Work package W3 of the WGS 84 build (docs/PLAN-wgs84.md sections 3.4 and 3.5)
connects ``michspc.spc.htdp`` to ``job.run``. Its end-to-end pins draw on the
frozen W0 and gate-1 anchors (``tests/fixtures/htdp_anchors.py``,
``htdp_near_tie_anchors.py``) wherever an anchor already holds the input the
pin needs. ONE input is not there, and it is the one the brief names: interim
gate 1's finding L5 (review/gate-wgs84-1/output.md), the vertical-only job on
WGS84(G2296) with the row ``1,43.0,-84.5,165.000`` and ellipsoid heights. The
reviewer saw that job, unguarded, write NAVD 88 198.085 m - h in WGS 84 taken
as h in NAD 83. The expected value of its successor pin is HTDP's own NAD 83 h
for that position, minus N from the program's GEOID18 reader; this file freezes
the first leg.

The record is captured for all five time-dependent frames MCX offers, each to
NAD 83(2011) at 2010.0 (the vertical-only job's pivot direction, plan D8), at
one observation date, 2025-06-15 - after every WGS 84 realization's period of
use began (G2296's on 2024-01-07). That date is inside G2296's period, so a
G2296 pin on it raises no realization warning; it is after G1762's and
G2139's periods ended, so those two raise the job-level warning of plan D9,
which changes no number. The same numbers are also captured the
other way - NAD 83(2011) at 2010.0 to each frame at 2025-06-15 - because the
W2 guard's successor pins put the reviewer's position through the
State Plane to geodetic direction as well, and its expected value is HTDP's
reverse output there.

**Independence.** The input is the reviewer's, chosen before ``michspc`` ran
it; the truth is the BINARY - NGS HTDP v3.6.0 compiled from the committed,
SHA-256-pinned source at review/wgs84-w0/htdp-v3.6.0/, refused unless its own
SHA-256 is W0's build. Nothing here imports ``michspc``. The suite never needs
the binary: the capture (``w3_truth.json``) is committed, and rendering reads
only it. ``tests/test_job_wgs84.py`` re-runs ``render()`` and requires the
committed fixture byte for byte.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
W0 = REPO / "review" / "wgs84-w0"
TRUTH = HERE / "w3_truth.json"
FIXTURE = REPO / "tests" / "fixtures" / "htdp_w3_anchors.py"

NAD83_DATE = (2010, 1, 1)
OBSERVED = (2025, 6, 15)
L5_INPUT = ("43.0", "84.5", "165.000")
"""Interim gate 1, finding L5: latitude, longitude POSITIVE WEST, ellipsoid h."""

FRAMES = (
    (10, "WGS84(G1762)"),
    (11, "WGS84(G2139)"),
    (12, "WGS84(G2296)"),
    (25, "ITRF2014"),
    (26, "ITRF2020"),
)
"""HTDP's MENU1 numbers (htdp.f:4704-4711, 4749-4753) and MCX's frame codes."""


def _load_drive():
    spec = importlib.util.spec_from_file_location("w0_drive", W0 / "drive_htdp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _drive(binary, m1, m2, observed, lines):
    """One TRFPOS file-option-3 run, calendar entry on both sides (GETMDY option 1)."""
    e_in = observed if m1 != 1 else NAD83_DATE
    e_out = observed if m2 != 1 else NAD83_DATE
    stdin = (
        f"4\nout.txt\n{m1}\n{m2}\n"
        f"1\n{e_in[1]} {e_in[2]} {e_in[0]}\n"
        f"1\n{e_out[1]} {e_out[2]} {e_out[0]}\n"
        "3\nin.txt\n0\n0\n"
    )
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "in.txt"), "w", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        done = subprocess.run(
            [binary], input=stdin.encode(), cwd=td, capture_output=True, timeout=300
        )
        raw = Path(td, "out.txt").read_bytes()
    return stdin, done.returncode, raw


def capture(binary):
    drive = _load_drive()
    w0 = json.loads((W0 / "htdp_truth.json").read_bytes())["provenance"]
    binary_sha = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    if binary_sha != w0["binary_sha256"]:
        raise SystemExit(f"binary {binary_sha} is not W0's build {w0['binary_sha256']}")
    sources = {
        name: hashlib.sha256((W0 / "htdp-v3.6.0" / name).read_bytes()).hexdigest()
        for name in sorted(w0["source_sha256"])
    }
    if sources != w0["source_sha256"]:
        raise SystemExit("the committed HTDP source is not W0's")
    runs = []
    for (menu, code), (m1, m2, name) in (
        (frame, direction)
        for direction in ((None, 1, "L5"), (1, None, "L5R"))
        for frame in FRAMES
    ):
        m1 = menu if m1 is None else m1
        m2 = menu if m2 is None else m2
        lines = [",".join(L5_INPUT) + f",{name}"]
        stdin, rc, raw = _drive(binary, m1, m2, OBSERVED, lines)
        _, outs = drive.parse_trfpos(raw)
        if rc != 0 or len(outs) != 1 or outs[0]["name"] != name or outs[0].get("outside"):
            raise SystemExit(f"{code}: exit {rc}, outputs {outs}")
        runs.append({
            "run_id": f"{name.lower()}_f{menu}_{OBSERVED[0]:04d}-{OBSERVED[1]:02d}-{OBSERVED[2]:02d}",
            "frame_code": code, "frame_in_menu": m1, "frame_out_menu": m2,
            "observation_date": list(OBSERVED), "stdin": stdin, "returncode": rc,
            "input_lines": lines, "outputs": outs,
            "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw": raw.decode("latin-1"),
        })
        print(code, outs[0], flush=True)
    try:
        compiler = subprocess.run(
            ["gfortran", "--version"], capture_output=True, text=True
        ).stdout.split("\n")[0]
    except OSError:
        compiler = "(gfortran not on PATH at capture)"
    truth = {
        "provenance": {
            "tool": w0["tool"], "repository": w0["repository"], "commit": w0["commit"],
            "source_sha256": sources, "binary_sha256": binary_sha,
            "binary_flags": w0["binary_flags"], "compiler_at_w0": w0["compiler"],
            "compiler_at_capture": compiler,
            "capture_utc": datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0).isoformat(),
            "input_from": "review/gate-wgs84-1/output.md, finding L5",
            "stdin_template": "4/out.txt/<in menu>/1/1/<m d y>/1/1 1 2010/3/in.txt/0/0",
        },
        "runs": runs,
    }
    TRUTH.write_text(json.dumps(truth, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {TRUTH.relative_to(REPO)}")


def render() -> str:
    raw = TRUTH.read_bytes()
    truth = json.loads(raw)
    prov = truth["provenance"]
    sources = "\n".join(
        f"    {name:<9} {digest}" for name, digest in sorted(prov["source_sha256"].items())
    )
    records = {"L5": [], "L5R": []}
    for run in truth["runs"]:
        (out,) = run["outputs"]
        lat_in, lonw_in, h_in = run["input_lines"][0].split(",")[:3]
        y, m, d = run["observation_date"]
        records[out["name"]].append(
            "    W3Record(\n"
            f"        run_id={json.dumps(run['run_id'])},\n"
            f"        frame_code={json.dumps(run['frame_code'])},\n"
            f"        frame_in_menu={run['frame_in_menu']},\n"
            f"        frame_out_menu={run['frame_out_menu']},\n"
            f"        observation_date=date({y}, {m}, {d}),\n"
            f"        stdin={json.dumps(run['stdin'])},\n"
            f"        raw_sha256={json.dumps(run['raw_sha256'])},\n"
            f"        lat_in={json.dumps(lat_in)},\n"
            f"        lonw_in={json.dumps(lonw_in)},\n"
            f"        h_in={json.dumps(h_in)},\n"
            f"        lat_out={json.dumps(out['lat'])},\n"
            f"        lonw_out={json.dumps(out['lonW'])},\n"
            f"        h_out={json.dumps(out['eht'])},\n"
            "    ),\n"
        )
    return (
        '"""NGS HTDP v3.6.0 TRFPOS output for work package W3\'s end-to-end pins, frozen.\n'
        "\n"
        "GENERATED - do not edit by hand. ``review/wgs84-w3/make_w3_anchors.py``\n"
        "writes this file from ``review/wgs84-w3/w3_truth.json`` and reproduces it byte\n"
        "for byte; ``tests/test_job_wgs84.py`` re-runs the generator and requires that.\n"
        "The generator's docstring says why these records and no others.\n"
        "\n"
        "Provenance (``w3_truth.json`` -> ``provenance``):\n"
        "\n"
        f"    tool       {prov['tool']}\n"
        f"    repository {prov['repository']}\n"
        f"    commit     {prov['commit']}\n"
        f"    compiler   {prov['compiler_at_capture']}\n"
        f"    build      {prov['binary_flags']}\n"
        f"    binary     sha256 {prov['binary_sha256']} (W0's build, checked at capture)\n"
        f"    captured   {prov['capture_utc']}\n"
        f"    truth file sha256 {hashlib.sha256(raw).hexdigest()}\n"
        f"    input      {prov['input_from']}\n"
        "\n"
        "    source SHA-256, the files committed unmodified at review/wgs84-w0/htdp-v3.6.0/:\n"
        f"{sources}\n"
        "\n"
        "Calendar entry on both sides, the NAD 83 side always 1 1 2010; the exact stdin\n"
        "of each run is stored with it. Inputs and outputs are HTDP's own strings,\n"
        "longitude POSITIVE WEST, output ``2f16.10,f10.3`` (htdp.f:3293) with leading\n"
        "blanks stripped.\n"
        '"""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "from dataclasses import dataclass\n"
        "from datetime import date\n"
        "\n"
        "\n"
        "@dataclass(frozen=True)\n"
        "class W3Record:\n"
        '    """One TRFPOS record between NAD 83(2011) at 2010.0 and a frame at ``observation_date``."""\n'
        "\n"
        "    run_id: str\n"
        "    frame_code: str\n"
        "    frame_in_menu: int\n"
        "    frame_out_menu: int\n"
        "    observation_date: date\n"
        "    stdin: str\n"
        "    raw_sha256: str\n"
        "    lat_in: str\n"
        "    lonw_in: str\n"
        "    h_in: str\n"
        "    lat_out: str\n"
        "    lonw_out: str\n"
        "    h_out: str\n"
        "\n"
        "\n"
        "L5_RECORDS: tuple[W3Record, ...] = (\n"
        + "".join(records["L5"])
        + ")\n"
        '"""Interim gate 1\'s L5 input, 43.0 N 84.5 W h 165.000 m, in each of the five\n'
        'frames, to NAD 83(2011) at 2010.0."""\n'
        "\n"
        "L5_REVERSE_RECORDS: tuple[W3Record, ...] = (\n"
        + "".join(records["L5R"])
        + ")\n"
        '"""The same numbers as a NAD 83(2011) position at 2010.0, to each of the five\n'
        'frames at the same observation date."""\n'
    )


def main(argv):
    if len(argv) >= 2 and argv[0] == "--capture":
        capture(argv[1])
        argv = argv[2:]
    text = render()
    if argv[:1] == ["--check"]:
        if FIXTURE.read_text(encoding="utf-8") != text:
            print("fixture differs from render()")
            return 1
        print("fixture matches")
        return 0
    FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
