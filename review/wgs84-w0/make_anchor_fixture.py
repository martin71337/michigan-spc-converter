"""Generate tests/fixtures/htdp_anchors.py from the frozen HTDP truth. Deterministic.

    python3 -I review/wgs84-w0/make_anchor_fixture.py          # write the fixture
    python3 -I review/wgs84-w0/make_anchor_fixture.py --check  # exit 1 if it differs

Reads ``htdp_truth.json`` (the frozen output of NGS HTDP v3.6.0 compiled from
the committed source, W0) as DATA and writes a discriminating subset of it as a
Python fixture. Rerunning it must reproduce the committed fixture byte for
byte; ``tests/test_htdp.py`` runs ``render()`` and requires exactly that, so
the fixture can never drift from the capture it claims to be a subset of.

Selection rules, all stated in the fixture's own docstring as well:

1. **Frames.** Only runs whose two frames are both ones MCX offers: NAD 83(2011)
   (menu 1) against WGS84(G1762), (G2139), (G2296), ITRF2014 or ITRF2020
   (menus 10, 11, 12, 25, 26). Menus 8, 9 and 24 are not offered.
2. **Epochs.** MCX takes a calendar date and nothing else (owner's decision,
   docs/PLAN-wgs84.md section 1). A run entered as a decimal year is kept only
   if that decimal year is EXACTLY what HTDP's calendar entry produces for some
   date - the same DATE and the same MINS, compared as floats and integers.
   1997.0, 2005.0, 2010.0 and 2020.0 are 1 January and qualify. 2015.5 is not
   a calendar date's DATE. 2026.8 IS the DATE of 2026-10-20, but HTDP's
   decimal entry runs its velocity clock from 2026-10-19 (RECON.md section
   1.5), so its MINS is not that date's and the run is excluded. The
   ``calendar_equiv_decimal_*`` runs are decimal-entry probes of GETMDY option
   2, which MCX does not have; their calendar twins are kept instead.
3. **Positions.** The beyond-box probes B001 (50.0 N) and B002 (50.1 N) are not
   anchors: their velocity lookup is at or north of region 6's edge, which MCX
   refuses (they are refusal pins in the suite). In every kept run, 24 named
   positions are kept: the four box corners, Isle Royale twice, the seven
   lake-water points, Clare, Houghton, Detroit and Sault Ste. Marie, the three
   velocity-grid node and cell-centre probes, the three 45 N FRMXYZ switch
   probes, and B000 at 49.9 N, the top row of the window. Each position is kept
   at ONE of HTDP's three heights, rotated by position and by (realization,
   epoch) group, so every run carries all three heights and every position
   meets all three across the fixture. A run and its round trip keep the same
   records, so the round trip can be chained; WGS84(G2139) and ITRF2014, and
   WGS84(G2296) and ITRF2020, keep the same records, so the ellipsoid
   difference between each pair can be compared record for record.
4. **Discriminators.** Every record of the applicable truth whose printed
   output W0's own transcription (``experiment.py``) changes when HTDP's
   truncated pi (htdp.f:2766) is replaced by the full one. That substitution
   moves a printed digit on only a few dozen records in the whole capture, so
   a positional subset would catch it only by luck. The records are selected
   with W0's independent code, never with ``michspc``, and their expected
   values are HTDP's printed strings like every other record's. A
   discriminator found in a round trip brings its forward record with it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TRUTH = HERE / "htdp_truth.json"
FIXTURE = REPO / "tests" / "fixtures" / "htdp_anchors.py"

OFFERED_MENUS = (1, 10, 11, 12, 25, 26)
NOT_ANCHORS = ("B001", "B002")
KEPT_POSITIONS = (
    "P000", "P007", "P056", "P063",  # box corners
    "P064", "P065",  # Isle Royale, Isle Royale SW (Windigo)
    "P066", "P067", "P068", "P069", "P070", "P071", "P072",  # lake water
    "P073", "P074", "P075", "P076",  # Clare, Houghton, Detroit, Sault Ste. Marie
    "P077", "P078", "P079",  # velocity-grid node and cell-centre probes
    "P080", "P081", "P082",  # 45 N exactly, just north, just south
    "B000",  # 49.9 N, the window's top row of cells
)
HEIGHT_TAGS = ("H000", "H200", "H600")
KINDS = ("forward", "reverse", "roundtrip_reverse", "calendar_forward", "calendar_reverse")


def _load_experiment():
    spec = importlib.util.spec_from_file_location("w0_experiment", HERE / "experiment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _calendar_equivalent(ex, entry):
    """(y, m, d) when HTDP's calendar entry gives exactly this entry's DATE and MINS."""
    if isinstance(entry, list):
        month, day, year = entry
        return (year, month, day)
    date, mins, (month, day, year) = ex.getmdy(entry)
    cal_date, cal_mins, _ = ex.getmdy([month, day, year])
    if date == cal_date and mins == cal_mins:
        return (year, month, day)
    return None


def _why_not_calendar(ex, entry):
    """The reason a decimal entry has no calendar twin, in words."""
    import datetime

    date, _, (month, day, year) = ex.getmdy(entry)
    clock_day = datetime.date(year, month, day)
    for candidate in (clock_day, clock_day + datetime.timedelta(days=1)):
        if ex.getmdy([candidate.month, candidate.day, candidate.year])[0] == date:
            if candidate != clock_day:
                return (
                    f"decimal {entry} is the DATE of {candidate.isoformat()}, but HTDP's "
                    f"decimal entry runs the velocity clock from {clock_day.isoformat()}"
                )
    return f"decimal {entry} is not the DATE of any calendar date"


REALIZATION = {10: 0, 11: 1, 25: 1, 12: 2, 26: 2}
"""WGS84(G2139) and ITRF2014 share HTDP's iopt 16, and WGS84(G2296) and ITRF2020
iopt 17: each pair is given the same height rotation, so the suite can compare
the two members record for record and see the ellipsoid alone."""


def _group_key(run):
    """Runs that share a (realization, epoch) group: a round trip keeps its
    forward's records, and an ITRF run keeps its WGS 84 twin's."""
    frame = REALIZATION[run["frame_in_menu"] if run["frame_in_menu"] != 1 else run["frame_out_menu"]]
    if run["kind"].startswith("calendar"):
        epoch = run["run_id"].split("_", 1)[1]
    else:
        epoch = run["run_id"].split("_", 2)[2]
    return (frame, epoch)


def _discriminators(ex, runs):
    """Records whose printed output W0's experiment changes under math.pi."""
    found = set()
    truncated = ex.RAD2DEG
    try:
        ex.RAD2DEG = 180.0 / math.pi
        for run in runs:
            for line, out in zip(run["input_lines"], run["outputs"]):
                lat_s, lonw_s, h_s, name = line.split(",", 3)
                if name[:4] in NOT_ANCHORS:
                    continue
                r = ex.trfpos_record(
                    lat_s, lonw_s, h_s, run["frame_in_menu"], run["frame_out_menu"],
                    run["epoch_in_entry"], run["epoch_out_entry"],
                )
                if ex.fmt(r[0], r[1], r[2]) != (out["lat"], out["lonW"], out["eht"]):
                    found.add((run["run_id"], name))
    finally:
        ex.RAD2DEG = truncated
    return found


def _q(text):
    return json.dumps(text)


def render() -> str:
    ex = _load_experiment()
    raw = TRUTH.read_bytes()
    truth = json.loads(raw)
    prov = truth["provenance"]

    applicable = []
    excluded = []
    for run in truth["runs"]:
        if run["frame_in_menu"] not in OFFERED_MENUS or run["frame_out_menu"] not in OFFERED_MENUS:
            continue
        if run["kind"] not in KINDS:
            excluded.append((run["run_id"], "decimal-entry probe of GETMDY option 2"))
            continue
        e_in = _calendar_equivalent(ex, run["epoch_in_entry"])
        e_out = _calendar_equivalent(ex, run["epoch_out_entry"])
        if e_in is None or e_out is None:
            entry = run["epoch_in_entry"] if e_in is None else run["epoch_out_entry"]
            excluded.append((run["run_id"], _why_not_calendar(ex, entry)))
            continue
        nad_side_epoch = e_in if run["frame_in_menu"] == 1 else e_out
        if nad_side_epoch != (2010, 1, 1):
            raise SystemExit("unexpected NAD 83 epoch in " + run["run_id"])
        observed = e_in if run["frame_in_menu"] != 1 else e_out
        applicable.append((run, observed))

    discriminating = _discriminators(ex, [run for run, _ in applicable])
    # A round trip's record is chained from its forward run's record of the
    # same name, so a discriminator in a round trip brings its forward twin.
    by_id = {run["run_id"]: run for run, _ in applicable}
    twins = {
        (by_id[run_id]["roundtrip_source"], name)
        for run_id, name in discriminating
        if by_id[run_id]["roundtrip_source"]
    } - discriminating

    groups = sorted({_group_key(run) for run, _ in applicable}, key=str)
    group_rank = {g: k for k, g in enumerate(groups)}
    position_rank = {p: k for k, p in enumerate(KEPT_POSITIONS)}

    run_blocks = []
    n_records = 0
    n_discriminators = 0
    n_twins = 0
    for run, observed in applicable:
        g = group_rank[_group_key(run)]
        wanted = {
            p + HEIGHT_TAGS[(position_rank[p] + g) % 3] for p in KEPT_POSITIONS
        }
        rows = []
        for line, out in zip(run["input_lines"], run["outputs"]):
            lat_s, lonw_s, h_s, name = line.split(",", 3)
            if out["name"] != name:
                raise SystemExit("record order mismatch in " + run["run_id"])
            if out.get("outside"):
                raise SystemExit("an 'outside' record in an applicable run: " + run["run_id"])
            mined = (run["run_id"], name) in discriminating
            twin = (run["run_id"], name) in twins and name not in wanted
            if name not in wanted and not mined and not twin:
                continue
            n_records += 1
            n_discriminators += mined
            n_twins += twin
            rows.append(
                f"            R({_q(name)}, {_q(lat_s)}, {_q(lonw_s)}, {_q(h_s)}, "
                f"{_q(out['lat'])}, {_q(out['lonW'])}, {_q(out['eht'])}),"
                + ("  # truncated-pi discriminator" if mined else "")
                + ("  # forward record of a round-trip discriminator" if twin else "")
            )
        y, m, d = observed
        run_blocks.append(
            "    HtdpRun(\n"
            f"        run_id={_q(run['run_id'])},\n"
            f"        kind={_q(run['kind'])},\n"
            f"        frame_in_menu={run['frame_in_menu']},\n"
            f"        frame_out_menu={run['frame_out_menu']},\n"
            f"        observation_date=date({y}, {m}, {d}),\n"
            f"        roundtrip_source={_q(run['roundtrip_source']) if run['roundtrip_source'] else None},\n"
            f"        stdin={_q(run['stdin'])},\n"
            f"        raw_sha256={_q(run['raw_sha256'])},\n"
            "        records=(\n" + "\n".join(rows) + "\n        ),\n"
            "    ),"
        )

    n_all = sum(len(run["outputs"]) for run in truth["runs"])
    n_applicable = sum(len(run["outputs"]) for run, _ in applicable)
    sources = "\n".join(
        f"    {name:9s} {digest}" for name, digest in sorted(prov["source_sha256"].items())
    )
    excluded_text = "\n".join(f"    {rid:24s} {why}" for rid, why in excluded)
    header = f'''"""NGS HTDP v3.6.0 TRFPOS output, frozen: the anchors ``michspc.spc.htdp`` must reproduce.

GENERATED - do not edit by hand. ``review/wgs84-w0/make_anchor_fixture.py``
writes this file from ``review/wgs84-w0/htdp_truth.json`` and reproduces it byte
for byte; ``tests/test_htdp.py`` re-runs the generator and requires that.

Provenance (``htdp_truth.json`` -> ``provenance``):

    tool       {prov["tool"]}
    repository {prov["repository"]}
    commit     {prov["commit"]}
    compiler   {prov["compiler"]}
    build      {prov["binary_flags"]}
    binary     sha256 {prov["binary_sha256"]}
    captured   {prov["capture_utc"]}
    truth file sha256 {hashlib.sha256(raw).hexdigest()}

    source SHA-256, the files committed unmodified at review/wgs84-w0/htdp-v3.6.0/:
{sources}

The exact stdin of every run is stored with it below. Its form is

    4 / out.txt / <in menu> / <out menu> / <epoch in> / <epoch out> / 3 / in.txt / 0 / 0

with each epoch either ``2`` then a decimal year, or ``1`` then ``m d y``: menu
option 4 (TRFPOS), file option 3 (records ``LAT,LON_POSITIVE_WEST,EHT,NAME``).
Output is HTDP's ``2f16.10,f10.3`` (htdp.f:3293), longitude POSITIVE WEST, and
the strings below are exactly what HTDP printed, leading blanks stripped.

**What these prove.** That MCX's transcription reproduces NGS's program to its
printed digit. The truth is HTDP itself (the owner's rule: replicate NOAA, the
authority); nothing here is an independent measurement of the ground, and NGS's
own 32-bit Windows build was not run (RECON.md section 4).

**Why a subset, and which.** The capture holds {n_all:,} records. Of those, {n_applicable:,}
are on frames MCX offers at an epoch a calendar date can produce; this file
keeps {n_records} of them in {len(run_blocks)} runs - every offered frame, both directions and the
round trip, at every calendar-equivalent epoch of the capture, and all sixteen
calendar-date runs. Per run it keeps 24 named positions (the box corners, Isle
Royale twice, seven lake-water points, Clare, Houghton, Detroit, Sault Ste.
Marie, three velocity-grid probes, the three 45 N FRMXYZ switch probes and B000
at 49.9 N), each at one height rotated across 0, 200 and 600 m. Added to those
are {n_discriminators} records selected because the truncated pi of htdp.f:2766 moves their
printed digit - picked with W0's independent ``experiment.py``, never with
``michspc`` - and the {n_twins} forward records those in round trips are chained
from. The full selection rule is the generator's docstring.

Runs left out, and why:

{excluded_text}

The beyond-box probes B001 (50.0 N) and B002 (50.1 N) are refusal cases, not
anchors: their velocity lookup is at or north of region 6's edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class HtdpRecord:
    """One TRFPOS record, input and output, as HTDP read and printed them."""

    name: str
    """W0's lattice id plus the height tag, e.g. ``P073H200`` (Clare, 200 m)."""

    lat_in: str
    lonw_in: str
    """POSITIVE WEST, as HTDP reads it."""

    h_in: str
    lat_out: str
    lonw_out: str
    """POSITIVE WEST, as HTDP prints it."""

    h_out: str


R = HtdpRecord


@dataclass(frozen=True)
class HtdpRun:
    """One HTDP run: a frame pair, an epoch pair, and the records kept from it."""

    run_id: str
    kind: str
    frame_in_menu: int
    frame_out_menu: int
    observation_date: date
    """The date of the non-NAD 83 side. The NAD 83 side is always 2010-01-01,
    entered to HTDP as the decimal year 2010.0, which HTDP's calendar entry of
    2010-01-01 reproduces exactly (DATE and MINS both)."""

    roundtrip_source: str | None
    """For a round trip, the forward run whose printed output is its input."""

    stdin: str
    raw_sha256: str
    """SHA-256 of HTDP's raw output file for the run, as captured."""

    records: tuple[HtdpRecord, ...]


HTDP_RUNS: tuple[HtdpRun, ...] = (
'''
    return header + "\n".join(run_blocks) + "\n)\n"


def main(argv):
    text = render()
    if "--check" in argv:
        current = FIXTURE.read_text(encoding="utf-8") if FIXTURE.exists() else ""
        if current != text:
            print("tests/fixtures/htdp_anchors.py differs from the generator's output")
            return 1
        print("tests/fixtures/htdp_anchors.py is reproduced byte for byte")
        return 0
    FIXTURE.write_bytes(text.encode("utf-8"))
    print(f"wrote {FIXTURE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
