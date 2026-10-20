"""Near-tie and window-edge anchors for michspc.spc.htdp, frozen from NGS's binary. Deterministic.

    python3 -I review/wgs84-w0/make_near_tie_anchors.py --capture BINARY   # search, drive HTDP, freeze
    python3 -I review/wgs84-w0/make_near_tie_anchors.py                    # write the fixture
    python3 -I review/wgs84-w0/make_near_tie_anchors.py --check            # exit 1 if it differs

A companion to ``make_anchor_fixture.py``, written for interim gate 1 of the
WGS 84 build (review/gate-wgs84-1/output.md, findings L2 and L3).

**L2: why near ties.** The 1,846 positional anchors of
``tests/fixtures/htdp_anchors.py`` hold the transcription to HTDP's printed
digit, but a printed digit only moves when the exact result crosses a
rounding tie, and positions chosen for their geography almost never sit
within an ulp of one. So a change of an ulp or so in the ORDER of HTDP's
operations - the reviewer's seeds S15 (``ylat + (ylat2 - ylat1)`` in NEWCOR)
and S26 (``math.radians`` for HTDP's ``(xlat*3600)/rhosec``) - left all 1,846
green. This file's near-tie records are inputs TUNED so that the exact result
of one component lies on one of the two doubles adjacent to a rounding tie of
HTDP's print (``2f16.10,f10.3``, htdp.f:3293): a difference of one ulp in the
right direction flips the printed digit, and each component is probed from
both sides.

**L3: why edges.** The velocity window refuses lookups outside its cells, and
the gate found nothing probing the last accepted cell or the first refused one
on any edge. The edge records are inputs tuned so that the ITRF2008 lookup
position PREDV computes falls either side of each window edge (east 279.5 E,
west 268.0 E, south 40.5 N) and of the 50.0 N north edge: two adjacent input
doubles, found by bisection, whose lookups lie a few ulps inside and outside.
HTDP itself accepts all of them - its grid 6 runs 250-294 E, 24-50 N - so its
printed value is frozen for every one; MCX accepts the inside record (and must
reproduce HTDP there) and refuses the outside one (its own scope).

**Independence.** Every input is chosen with W0's ``experiment.py`` - the
transcription W0 wrote before ``michspc.spc.htdp`` existed - and never with
``michspc``. The truth is the BINARY: every record below was run through NGS
HTDP v3.6.0 compiled from the committed source, and its printed output is what
the fixture states. ``experiment.py``'s own print must agree with the binary's
on every record (the capture refuses otherwise), which is the evidence that
its unrounded value - from which each record's distance from its tie is
stated - is HTDP's. The suite never needs the binary: the capture
(``near_tie_truth.json``) is committed, and rendering reads only it and
``experiment.py``.

**Determinism.** The search draws from ``random.Random`` seeded with fixed
strings, so ``--capture`` reproduces the same inputs on any machine;
rendering reproduces the committed fixture byte for byte, and
``tests/test_htdp.py`` requires that.

The selection, per HTDP direction (all ten: NAD 83(2011), menu 1, against
menus 10, 11, 12, 25 and 26, each way):

* six runs, each at its own observation date drawn from 2000-01-01 to
  2034-12-31 (never 2010-01-01, where HTDP applies no velocity and NEWCOR -
  S15's routine - does not run);
* in each run, for latitude, longitude and height in turn, a position drawn
  from the Michigan box (41.6-48.4 N, 82.1-90.5 W) and a height, and two
  records: the input whose result comes closest to the tie nearest the drawn
  position's result from BELOW, and the one that comes closest from ABOVE,
  among the SCAN_ULPS input doubles either side of the crossing (``_bracket``).
  For latitude and longitude these are usually the two doubles adjacent to the
  tie; the height passes through HTDP's Cartesian round trip and gets within
  about 1e-9 m. 10 x 6 x 3 x 2 = 360 near-tie records.

Plus the window edges, two directions (WGS84(G2296) to NAD 83 and NAD 83 to
ITRF2014) x four edges x inside and outside = 16 records; and the reviewer's
own six counterexamples (S15 once, S26 five times), recovered from the
gate's deterministic fuzz, at their own frames and dates.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import math
import os
import random
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TRUTH = HERE / "near_tie_truth.json"
W0_TRUTH = HERE / "htdp_truth.json"
FIXTURE = REPO / "tests" / "fixtures" / "htdp_near_tie_anchors.py"

PAIRS = tuple((m, 1) for m in (10, 11, 12, 25, 26)) + tuple((1, m) for m in (10, 11, 12, 25, 26))
RUNS_PER_PAIR = 6
COMPONENTS = ("LA", "LO", "HT")  # latitude, longitude (positive west), height
DECIMALS = (10, 10, 3)  # HTDP's 2f16.10,f10.3 (htdp.f:3293)
NAD83_DATE = (2010, 1, 1)
EDGE_PAIRS = ((12, 1, (2025, 6, 15)), (1, 25, (2025, 6, 15)))
EDGES = ("E", "W", "S", "N")
SCAN_ULPS = 200
"""Input doubles evaluated either side of a tie crossing (see ``_bracket``)."""

# The gate's own counterexamples, recovered from its fuzz (fuzz_small.py: the
# (pair, seed) tasks i*50+k, record k of 3,000) by replaying the seeds through
# michspc with each seed applied and listing every record whose print moved:
# (seed, menu in, menu out, date, lat, lon positive west, height).
GATE1 = (
    ("S26", 10, 1, (2002, 1, 20), "44.16073757508377", "84.2231097333896", "0.0"),
    ("S26", 10, 1, (1995, 1, 28), "45.00005377942753", "89.46078879147638", "0.0"),
    ("S26", 25, 1, (2026, 10, 1), "42.757733086988175", "90.95031453635029", "76.48566873467087"),
    ("S26", 25, 1, (2034, 1, 3), "45.00007767533613", "86.07399523500962", "0.0"),
    ("S15", 1, 12, (2022, 7, 23), "44.269962536263435", "82.54369826118517", "0.0"),
    ("S26", 1, 25, (2033, 12, 6), "44.9999521625992", "83.50785611478302", "4532.693697117842"),
)


def _load_experiment():
    spec = importlib.util.spec_from_file_location("w0_experiment", HERE / "experiment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mdy(ymd):
    y, m, d = ymd
    return [m, d, y]


def _entries(m1, m2, date):
    e1 = _mdy(date) if m1 != 1 else _mdy(NAD83_DATE)
    e2 = _mdy(date) if m2 != 1 else _mdy(NAD83_DATE)
    return e1, e2


def _evaluate(ex, m1, m2, date, inputs):
    """experiment.py's unrounded (lat, lonW, h) for one record: its TRFPOS."""
    e1, e2 = _entries(m1, m2, date)
    lat, lonw, h, _ = ex.trfpos_record(
        repr(inputs[0]), repr(inputs[1]), repr(inputs[2]), m1, m2, e1, e2
    )
    return lat, lonw, h


def _lookup(ex, m1, m2, date, inputs):
    """experiment.py's ITRF2008 velocity-lookup position (rlat, rlon west), in radians.

    ``trfpos_record``'s own steps up to PREDV's call (htdp.f:3216-3249), then
    PREDV's lookup (htdp.f:7425-7439), composed from experiment.py's functions
    in that order - and stopping there, because past a window edge
    experiment.py, like michspc, has no velocity to read.
    """
    e1, _ = _entries(m1, m2, date)
    c = ex.Const()
    iopt1, name1 = ex.FRAMES[m1]
    iopt2, name2 = ex.FRAMES[m2]
    date1, _, _ = ex.getmdy(e1)
    tab = ex.TRANPA if (iopt1 == 1 or iopt2 == 1) else ex.TRANPA1
    ylat = (float(repr(inputs[0])) * 3600.0) / ex.RHOSEC
    ylon = (float(repr(inputs[1])) * 3600.0) / ex.RHOSEC
    c.elpsd = ex.frame_ellipsoid(name1)
    x, y, z = ex.toxyz(c, ylat, -ylon, float(repr(inputs[2])))
    x2 = ex.frit94(tab, ex.toit94(tab, (x, y, z), date1, iopt1), date1, iopt2)
    c.elpsd = ex.frame_ellipsoid(name2)
    ylat1, elon1, eht1 = ex.frmxyz(c, *x2)
    ylon1 = -elon1
    if ylon1 < 0.0:
        ylon1 = ylon1 + ex.TWOPI
    if iopt1 == 15:
        return ylat1, ylon1
    X, Y, Z = ex.toxyz(c, ylat1, -ylon1, eht1)
    return ex.xto08(c, X, Y, Z, date1, iopt1)


def _tie_in_cell(value: float, decimals: int) -> Fraction:
    """The rounding tie inside ``value``'s print unit: (k + 1/2) / 10**decimals.

    ``k`` is the print unit at or below the exact value of the double, so the
    tie is the one decision point of ``%.{decimals}f`` between k and k + 1.
    """
    scale = 10 ** decimals
    k = math.floor(Fraction(value) * scale)
    return (Fraction(k) + Fraction(1, 2)) / scale


def _bracket(ex, m1, m2, date, base, component):
    """Two inputs whose result in ``component`` is the double just below and just above a tie."""
    decimals = DECIMALS[COMPONENTS.index(component)]
    c = COMPONENTS.index(component)
    out0 = _evaluate(ex, m1, m2, date, base)
    tie = _tie_in_cell(out0[c], decimals)
    # experiment.py's result is increasing in its own input component (a
    # latitude in moves the latitude out, and so on), so bisect the INPUT, from
    # a bracket around the first-order estimate, down to two adjacent doubles
    # whose results lie either side of the tie. The result is not a smooth
    # function of the input at the ulp: it passes through HTDP's Cartesian
    # round trip, whose own rounding is a few result ulps for the latitude and
    # about 1e-9 m for the height. So the crossing is only where to look: the
    # SCAN_ULPS input doubles either side of it are all evaluated, and the
    # records are the inputs whose results come closest to the tie from below
    # and from above - for latitude and longitude, typically the very doubles
    # adjacent to the tie.
    estimate = base[c] + float(tie - Fraction(out0[c]))
    width = 1e-6 if component == "HT" else 1e-11

    def value(x):
        probe = list(base)
        probe[c] = x
        return Fraction(_evaluate(ex, m1, m2, date, probe)[c])

    lo, hi = estimate - width, estimate + width
    if not (value(lo) < tie < value(hi)):
        return None, tie
    while math.nextafter(lo, hi) != hi:
        mid = lo + (hi - lo) / 2.0
        if mid in (lo, hi):
            break
        if value(mid) < tie:
            lo = mid
        else:
            hi = mid
    best = {}
    x = lo
    for _ in range(SCAN_ULPS):
        x = math.nextafter(x, -math.inf)
    for _ in range(2 * SCAN_ULPS + 2):
        y = value(x)
        side = "B" if y < tie else "A" if y > tie else None
        if side and (side not in best or abs(y - tie) < abs(best[side][1] - tie)):
            best[side] = (x, y)
        x = math.nextafter(x, math.inf)
    if set(best) != {"B", "A"}:
        return None, tie
    found = {}
    for side, (x, _) in best.items():
        probe = list(base)
        probe[c] = x
        found[side] = tuple(probe)
    return found, tie


def _edge_bracket(ex, m1, m2, date, base, edge):
    """Two adjacent input doubles whose lookups fall either side of a window edge.

    GRDWEI's own arithmetic decides the side (htdp.f:1603-1611): posx = (2 pi -
    rlon) 180 / pi and posy = rlat 180 / pi, in degrees of east longitude and
    latitude; the cell is inside when 268.0 <= posx < 279.5 and 40.5 <= posy <
    50.0 (nodes I 37-60, J 34-53), and the region edge refuses rlat at or
    north of 50.0 N.
    """
    pi = ex.PI
    twopi = ex.TWOPI

    def coordinate(lookup):
        rlat, rlon = lookup
        return (twopi - rlon) * 180.0 / pi if edge in "EW" else rlat * 180.0 / pi

    target = {"E": 279.5, "W": 268.0, "S": 40.5, "N": 50.0}[edge]
    inside_is_below = edge in "EN"
    c = 1 if edge in "EW" else 0
    lookup0 = _lookup(ex, m1, m2, date, base)
    offset = target - coordinate(lookup0)
    # The lookup coordinate increases with input latitude, and with input
    # EAST longitude - the input is positive west, so it decreases with that.
    sign = -1.0 if c == 1 else 1.0
    estimate = base[c] + sign * offset

    def value(x):
        probe = list(base)
        probe[c] = x
        return coordinate(_lookup(ex, m1, m2, date, probe))

    # lo is the input whose lookup coordinate is below the edge, hi above it.
    lo, hi = estimate - sign * 1e-6, estimate + sign * 1e-6
    if not (value(lo) < target <= value(hi)):
        raise SystemExit(f"no edge bracket for edge {edge} of {m1}->{m2}")
    while math.nextafter(lo, hi) != hi:
        mid = lo + (hi - lo) / 2.0
        if mid in (lo, hi):
            break
        if value(mid) < target:
            lo = mid
        else:
            hi = mid
    below, above = list(base), list(base)
    below[c], above[c] = lo, hi
    inside, outside = (below, above) if inside_is_below else (above, below)
    return {"IN": tuple(inside), "OUT": tuple(outside)}


def search(ex):
    """Every run to capture: (run_id, purpose, m1, m2, date, [(name, inputs, meta)])."""
    plan = []
    for m1, m2 in PAIRS:
        for r in range(RUNS_PER_PAIR):
            rng = random.Random(f"mcx near tie {m1} {m2} {r}")
            while True:
                date = datetime.date(2000, 1, 1) + datetime.timedelta(days=rng.randint(0, 12783))
                if date != datetime.date(*NAD83_DATE):
                    break
            ymd = (date.year, date.month, date.day)
            records = []
            for component in COMPONENTS:
                for _attempt in range(20):
                    base = (
                        rng.uniform(41.6, 48.4),
                        rng.uniform(82.1, 90.5),
                        rng.choice((0.0, 200.0, 600.0, rng.uniform(-30.0, 700.0))),
                    )
                    found, tie = _bracket(ex, m1, m2, ymd, base, component)
                    if found:
                        break
                else:
                    raise SystemExit(f"no bracket for {m1}->{m2} run {r} {component}")
                for side in ("B", "A"):
                    name = f"NT{PAIRS.index((m1, m2)):02d}{r}{component}{side}"
                    records.append((name, found[side], {"component": component, "side": side}))
            plan.append((f"neartie_{m1}_{m2}_{r}", "near_tie", m1, m2, ymd, records))
    for m1, m2, ymd in EDGE_PAIRS:
        records = []
        for edge in EDGES:
            base = {
                "E": (44.0, 80.6, 0.0), "W": (44.0, 91.9, 200.0),
                "S": (40.6, 85.0, 0.0), "N": (49.9, 88.0, 200.0),
            }[edge]
            found = _edge_bracket(ex, m1, m2, ymd, base, edge)
            for side in ("IN", "OUT"):
                records.append((f"EDGE{edge}{side}", found[side], {"edge": edge, "side": side}))
        plan.append((f"edge_{m1}_{m2}", "window_edge", m1, m2, ymd, records))
    for k, (seed, m1, m2, ymd, lat, lonw, h) in enumerate(GATE1):
        records = [(f"GATE1{seed}N{k}", (float(lat), float(lonw), float(h)), {"seed": seed})]
        plan.append((f"gate1_{seed.lower()}_{k}", "gate1_counterexample", m1, m2, ymd, records))
    return plan


def _drive(binary, m1, m2, ymd, lines):
    """One TRFPOS file-option-3 run of the binary, calendar entry on both sides."""
    e_in = ymd if m1 != 1 else NAD83_DATE
    e_out = ymd if m2 != 1 else NAD83_DATE
    stdin = (
        f"4\nout.txt\n{m1}\n{m2}\n"
        f"1\n{e_in[1]} {e_in[2]} {e_in[0]}\n"
        f"1\n{e_out[1]} {e_out[2]} {e_out[0]}\n"
        "3\nin.txt\n0\n0\n"
    )
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "in.txt"), "w", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        done = subprocess.run([binary], input=stdin.encode(), cwd=td, capture_output=True, timeout=300)
        raw = Path(td, "out.txt").read_bytes()
    return stdin, done.returncode, raw


def capture(binary):
    spec = importlib.util.spec_from_file_location("w0_drive", HERE / "drive_htdp.py")
    drive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drive)
    ex = _load_experiment()
    w0 = json.loads(W0_TRUTH.read_bytes())["provenance"]
    binary_sha = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    if binary_sha != w0["binary_sha256"]:
        raise SystemExit(f"binary {binary_sha} is not W0's build {w0['binary_sha256']}")
    sources = {
        name: hashlib.sha256((HERE / "htdp-v3.6.0" / name).read_bytes()).hexdigest()
        for name in sorted(w0["source_sha256"])
    }
    if sources != w0["source_sha256"]:
        raise SystemExit("the committed HTDP source is not W0's")
    runs = []
    for run_id, purpose, m1, m2, ymd, records in search(ex):
        lines = [f"{repr(x[0])},{repr(x[1])},{repr(x[2])},{name}" for name, x, _ in records]
        stdin, rc, raw = _drive(binary, m1, m2, ymd, lines)
        _, outs = drive.parse_trfpos(raw)
        if rc != 0 or len(outs) != len(lines):
            raise SystemExit(f"{run_id}: exit {rc}, {len(outs)} outputs for {len(lines)} inputs")
        for (name, _, _), out in zip(records, outs):
            if out["name"] != name or out.get("outside"):
                raise SystemExit(f"{run_id}: unexpected output {out}")
        runs.append({
            "run_id": run_id, "purpose": purpose, "frame_in_menu": m1, "frame_out_menu": m2,
            "observation_date": list(ymd), "stdin": stdin, "returncode": rc,
            "input_lines": lines, "selection": [meta for _, _, meta in records],
            "outputs": outs, "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw": raw.decode("latin-1"),
        })
        print(run_id, len(outs), flush=True)
    try:
        compiler = subprocess.run(["gfortran", "--version"], capture_output=True, text=True).stdout.split("\n")[0]
    except OSError:
        compiler = "(gfortran not on PATH at capture)"
    truth = {
        "provenance": {
            "tool": w0["tool"], "repository": w0["repository"], "commit": w0["commit"],
            "source_sha256": sources, "binary_sha256": binary_sha,
            "binary_flags": w0["binary_flags"], "compiler_at_w0": w0["compiler"],
            "compiler_at_capture": compiler,
            "capture_utc": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
            "selected_with": "review/wgs84-w0/experiment.py (W0's independent transcription), "
                             "never michspc; see review/wgs84-w0/make_near_tie_anchors.py",
            "stdin_template": "4/out.txt/<in menu>/<out menu>/1/<m d y>/1/<m d y>/3/in.txt/0/0",
        },
        "runs": runs,
    }
    TRUTH.write_text(json.dumps(truth, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {TRUTH.relative_to(REPO)}")


def _fmt(values):
    lat, lonw, h = values
    return ("%16.10f" % lat).strip(), ("%16.10f" % lonw).strip(), ("%10.3f" % h).strip()


def _q(text):
    return json.dumps(text)


def render() -> str:
    ex = _load_experiment()
    raw = TRUTH.read_bytes()
    truth = json.loads(raw)
    prov = truth["provenance"]
    blocks = []
    counts = {"near_tie": 0, "window_edge": 0, "gate1_counterexample": 0}
    worst = Fraction(0)
    for run in truth["runs"]:
        m1, m2 = run["frame_in_menu"], run["frame_out_menu"]
        ymd = tuple(run["observation_date"])
        rows = []
        for line, meta, out in zip(run["input_lines"], run["selection"], run["outputs"]):
            lat_s, lonw_s, h_s, name = line.split(",", 3)
            inputs = (float(lat_s), float(lonw_s), float(h_s))
            printed = (out["lat"], out["lonW"], out["eht"])
            outside = run["purpose"] == "window_edge" and meta["side"] == "OUT"
            if not outside:
                # Outside the window experiment.py, like michspc, has no
                # velocity to read; HTDP's print there is provenance only.
                values = _evaluate(ex, m1, m2, ymd, inputs)
                if _fmt(values) != printed:
                    raise SystemExit(
                        f"{run['run_id']} {name}: experiment.py prints {_fmt(values)}, HTDP {printed}"
                    )
            if run["purpose"] == "near_tie":
                c = COMPONENTS.index(meta["component"])
                tie = _tie_in_cell(values[c], DECIMALS[c])
                margin = (Fraction(values[c]) - tie) * 10 ** DECIMALS[c]
                if (margin < 0) is not (meta["side"] == "B") or abs(margin) > Fraction(1, 1000):
                    raise SystemExit(f"{run['run_id']} {name}: not a near tie ({float(margin)!r})")
                worst = max(worst, abs(margin))
                role = f"tie {meta['component']} {'below' if meta['side'] == 'B' else 'above'}"
                note = f"{float(margin):+.3e}"
            elif run["purpose"] == "window_edge":
                rlat, rlon = _lookup(ex, m1, m2, ymd, inputs)
                coord = (ex.TWOPI - rlon) * 180.0 / ex.PI if meta["edge"] in "EW" else rlat * 180.0 / ex.PI
                target = {"E": 279.5, "W": 268.0, "S": 40.5, "N": 50.0}[meta["edge"]]
                inside_is_below = meta["edge"] in "EN"
                if (coord < target) is not (inside_is_below is not outside):
                    raise SystemExit(f"{run['run_id']} {name}: lookup {coord!r} on the wrong side")
                role = f"edge {meta['edge']} {'outside' if outside else 'inside'}"
                note = repr(coord)
            else:
                role = f"gate1 {meta['seed']}"
                note = ""
            counts[run["purpose"]] += 1
            rows.append(
                f"            T({_q(name)}, {_q(lat_s)}, {_q(lonw_s)}, {_q(h_s)}, "
                f"{_q(out['lat'])}, {_q(out['lonW'])}, {_q(out['eht'])}, {_q(role)}, {_q(note)}),"
            )
        y, m, d = ymd
        blocks.append(
            "    NearTieRun(\n"
            f"        run_id={_q(run['run_id'])},\n"
            f"        purpose={_q(run['purpose'])},\n"
            f"        frame_in_menu={m1},\n"
            f"        frame_out_menu={m2},\n"
            f"        observation_date=date({y}, {m}, {d}),\n"
            f"        stdin={_q(run['stdin'])},\n"
            f"        raw_sha256={_q(run['raw_sha256'])},\n"
            "        records=(\n" + "\n".join(rows) + "\n        ),\n"
            "    ),"
        )
    sources = "\n".join(f"    {name:9s} {digest}" for name, digest in sorted(prov["source_sha256"].items()))
    header = f'''"""NGS HTDP v3.6.0 TRFPOS output at rounding ties and window edges, frozen.

GENERATED - do not edit by hand. ``review/wgs84-w0/make_near_tie_anchors.py``
writes this file from ``review/wgs84-w0/near_tie_truth.json`` and reproduces it
byte for byte; ``tests/test_htdp.py`` re-runs the generator and requires that.
The generator's docstring is the full selection rule.

Provenance (``near_tie_truth.json`` -> ``provenance``):

    tool       {prov["tool"]}
    repository {prov["repository"]}
    commit     {prov["commit"]}
    compiler   {prov["compiler_at_capture"]}
    build      {prov["binary_flags"]}
    binary     sha256 {prov["binary_sha256"]} (W0's build, checked at capture)
    captured   {prov["capture_utc"]}
    truth file sha256 {hashlib.sha256(raw).hexdigest()}

    source SHA-256, the files committed unmodified at review/wgs84-w0/htdp-v3.6.0/:
{sources}

Every run is calendar entry on both sides (GETMDY option 1), the NAD 83 side
always 1 1 2010; its exact stdin is stored with it. Output strings are HTDP's
``2f16.10,f10.3`` (htdp.f:3293), longitude POSITIVE WEST, leading blanks
stripped.

**Interim gate 1 of the WGS 84 build, findings L2 and L3.** {counts["near_tie"]} near-tie
records: in each of {len(PAIRS) * RUNS_PER_PAIR} runs ({RUNS_PER_PAIR} per HTDP direction, all ten directions),
for latitude, longitude and height, the input whose result comes closest to a
rounding tie of HTDP's print from below and the one closest from above -
usually the two doubles adjacent to the tie. The ``note`` of each is W0's
``experiment.py``'s signed distance of its unrounded result from the tie, in
print units; the largest is {float(worst):.3e}. A change of an ulp or so in the
right direction flips the printed digit. {counts["window_edge"]} window-edge records: for two directions and each
of the east, west, south and north edges, two ADJACENT input doubles whose
ITRF2008 lookups fall either side of the edge, a few ulps from it - the
``note`` is that lookup coordinate, in degrees as GRDWEI computes it
(htdp.f:1603-1604). HTDP computes all of them (its grid 6 spans
250-294 E, 24-50 N); MCX must reproduce the inside ones and refuse the
outside ones. And the {counts["gate1_counterexample"]} counterexamples the gate's reviewer reported for
seeds S15 and S26, at their own frames and dates.

Inputs were chosen with W0's independent ``experiment.py``, never with
``michspc``, and ``experiment.py``'s print agrees with HTDP's on every record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class NearTieRecord:
    """One TRFPOS record, as HTDP read and printed it, and why it was chosen."""

    name: str
    lat_in: str
    lonw_in: str
    """POSITIVE WEST, as HTDP reads it."""

    h_in: str
    lat_out: str
    lonw_out: str
    """POSITIVE WEST, as HTDP prints it."""

    h_out: str
    role: str
    """``tie LA below`` (latitude, the double below the tie), ``tie HT above``,
    ``edge E inside``, ``edge N outside``, ``gate1 S26`` ..."""

    note: str
    """For a tie, the signed distance from the tie in print units; for an
    edge, the lookup coordinate in degrees; empty for a gate-1 record."""


T = NearTieRecord


@dataclass(frozen=True)
class NearTieRun:
    """One HTDP run: a frame pair, a date, and its records."""

    run_id: str
    purpose: str
    frame_in_menu: int
    frame_out_menu: int
    observation_date: date
    """The date of the non-NAD 83 side; the NAD 83 side is 2010-01-01."""

    stdin: str
    raw_sha256: str
    records: tuple[NearTieRecord, ...]


NEAR_TIE_RUNS: tuple[NearTieRun, ...] = (
'''
    return header + "\n".join(blocks) + "\n)\n"


def main(argv):
    if "--capture" in argv:
        capture(argv[argv.index("--capture") + 1])
        return 0
    text = render()
    if "--check" in argv:
        current = FIXTURE.read_text(encoding="utf-8") if FIXTURE.exists() else ""
        if current != text:
            print("tests/fixtures/htdp_near_tie_anchors.py differs from the generator's output")
            return 1
        print("tests/fixtures/htdp_near_tie_anchors.py is reproduced byte for byte")
        return 0
    FIXTURE.write_bytes(text.encode("utf-8"))
    print(f"wrote {FIXTURE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
