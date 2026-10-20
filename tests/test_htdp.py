"""HTDP v3.6.0's frame transformation: the anchors, the transcription, the refusals.

``michspc.spc.htdp`` is a transcription of NGS's own program, and this file
holds it to that program from two sides:

1. **The anchors** (``tests/fixtures/htdp_anchors.py``): HTDP's printed output,
   frozen from NGS's source compiled in the container, reproduced to the
   printed digit - 1e-10 degree, 1 mm - by formatting this module's result the
   way HTDP writes it (``2f16.10,f10.3``, ``htdp.f:3293``, longitude positive
   west) and comparing STRINGS, latitude, longitude and height separately. A
   ``max()`` over components would let one component's agreement hide another's
   failure (DESIGN.md #62, the H1-H2 gate's lesson).
2. **The transcription**: the committed Fortran is re-parsed here as data and
   every constant ``htdp_data`` carries must equal the one NGS wrote, number
   for number; the source files themselves are SHA-256 pinned.

3. **The near ties and window edges** (``tests/fixtures/htdp_near_tie_anchors.py``,
   interim gate 1 of the WGS 84 build, L2 and L3): records whose result sits
   beside a rounding tie of HTDP's print, so that an ulp's change in the order
   of operations is seen, and records either side of every edge of the
   velocity window, frozen from the same binary.

Then the facts that do not show in a single anchor: the ellipsoid follows the
frame's name, HTDP's calendar arithmetic, the window that bounds this module's
scope (with the proof from NGS's source that nothing outside it - another
velocity region, an earthquake, the postseismic grid - can reach a position
inside it), every refusal, and HTDP's own round-trip non-closure, replicated
rather than repaired.

Every expected value is either one of HTDP's printed strings or is derived in
the comment above it from the source (docs/method/METHOD.md section 4).
"""

from __future__ import annotations

import datetime
import functools
import hashlib
import importlib.util
import math
import re
from fractions import Fraction
from pathlib import Path

import pytest

from michspc.spc import frames, htdp, htdp_data
from tests.fixtures.htdp_anchors import HTDP_RUNS
from tests.fixtures.htdp_near_tie_anchors import NEAR_TIE_RUNS

REPO_ROOT = Path(__file__).resolve().parent.parent
W0 = REPO_ROOT / "review" / "wgs84-w0"
SOURCE = W0 / "htdp-v3.6.0"

RUNS_BY_ID = {run.run_id: run for run in HTDP_RUNS}
RUN_IDS = [run.run_id for run in HTDP_RUNS]


def _lines(name: str) -> list[str]:
    """A committed HTDP source file as lines; index 0 is line 1."""
    return (SOURCE / name).read_text(encoding="latin-1").split("\n")


def htdp_print(result: htdp.HtdpResult) -> tuple[str, str, str]:
    """``result`` as HTDP writes it: ``2f16.10,f10.3`` (htdp.f:3293).

    Longitude POSITIVE west, as HTDP prints it; leading blanks stripped, as the
    frozen strings are.
    """
    return (
        ("%16.10f" % result.latitude).strip(),
        ("%16.10f" % (-result.longitude)).strip(),
        ("%10.3f" % result.ellipsoid_height).strip(),
    )


def run_record(run, lat_in: str, lonw_in: str, h_in: str) -> htdp.HtdpResult:
    """One record of ``run`` through the public entry point, as a job would."""
    return htdp.transform(
        float(lat_in),
        -float(lonw_in),  # HTDP's input is positive west; this module's is not
        float(h_in),
        htdp.frame_by_menu(run.frame_in_menu),
        htdp.frame_by_menu(run.frame_out_menu),
        htdp.ObservationEpoch(run.observation_date),
    )


@functools.lru_cache(maxsize=None)
def computed(run_id: str) -> tuple[tuple[str, tuple[str, str, str], tuple[str, str, str]], ...]:
    """(name, ours, HTDP's) for every record of a run, computed once."""
    run = RUNS_BY_ID[run_id]
    out = []
    for record in run.records:
        ours = htdp_print(run_record(run, record.lat_in, record.lonw_in, record.h_in))
        theirs = (record.lat_out, record.lonw_out, record.h_out)
        out.append((record.name, ours, theirs))
    return tuple(out)


def _mismatches(run_id: str, component: int) -> list[str]:
    return [
        f"{name}: ours {ours[component]} HTDP {theirs[component]}"
        for name, ours, theirs in computed(run_id)
        if ours[component] != theirs[component]
    ]


# --------------------------------------------------------------------------
# (a) Every anchor, to HTDP's printed digit, one component at a time.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("run_id", RUN_IDS)
def test_anchor_latitude_is_htdps_printed_latitude(run_id):
    bad = _mismatches(run_id, 0)
    assert not bad, f"{run_id}: {len(bad)} latitudes differ from HTDP's print: {bad[:5]}"


@pytest.mark.parametrize("run_id", RUN_IDS)
def test_anchor_longitude_is_htdps_printed_longitude(run_id):
    bad = _mismatches(run_id, 1)
    assert not bad, f"{run_id}: {len(bad)} longitudes differ from HTDP's print: {bad[:5]}"


@pytest.mark.parametrize("run_id", RUN_IDS)
def test_anchor_height_is_htdps_printed_height(run_id):
    bad = _mismatches(run_id, 2)
    assert not bad, f"{run_id}: {len(bad)} heights differ from HTDP's print: {bad[:5]}"


def test_the_fixture_covers_every_frame_direction_epoch_and_calendar_run():
    """The coverage the fixture's docstring claims, checked rather than trusted.

    From the generator's rules: five offered frames (HTDP menus 10, 11, 12, 25,
    26) x forward, reverse and round trip x the four calendar-equivalent
    epochs of the capture (1 January of 1997, 2005, 2010 and 2020) = 60 runs,
    plus the 16 calendar-date runs (8 dates x 2 directions, all WGS84(G2296),
    menu 12) = 76.
    """
    triples = {
        (run.kind, run.frame_in_menu if run.frame_in_menu != 1 else run.frame_out_menu,
         run.observation_date)
        for run in HTDP_RUNS
        if not run.kind.startswith("calendar")
    }
    expected = {
        (kind, menu, datetime.date(year, 1, 1))
        for kind in ("forward", "reverse", "roundtrip_reverse")
        for menu in (10, 11, 12, 25, 26)
        for year in (1997, 2005, 2010, 2020)
    }
    assert triples == expected

    calendar = sorted(
        (run.kind, run.observation_date) for run in HTDP_RUNS if run.kind.startswith("calendar")
    )
    dates = [
        datetime.date(2010, 1, 1), datetime.date(2015, 7, 2), datetime.date(2024, 2, 29),
        datetime.date(2024, 12, 31), datetime.date(2025, 1, 1), datetime.date(2025, 3, 1),
        datetime.date(2026, 10, 19), datetime.date(2026, 10, 20),
    ]
    assert calendar == sorted(
        (kind, d) for kind in ("calendar_forward", "calendar_reverse") for d in dates
    )
    assert len(HTDP_RUNS) == 76

    # Every run carries all three heights and the named positions: corners
    # P000 P007 P056 P063, Isle Royale P064, the lakes P066-P072, the 45 N
    # FRMXYZ probes P080-P082, and B000 at 49.9 N.
    must = {"P000", "P007", "P056", "P063", "P064", "P066", "P067", "P068", "P069",
            "P070", "P071", "P072", "P080", "P081", "P082", "B000"}
    for run in HTDP_RUNS:
        names = {record.name for record in run.records}
        assert {n[4:] for n in names} >= {"H000", "H200", "H600"}, run.run_id
        assert {n[:4] for n in names} >= must, run.run_id
    total = sum(len(run.records) for run in HTDP_RUNS)
    assert 1500 <= total <= 2100, total


def test_the_generator_reproduces_the_fixture_byte_for_byte():
    """The fixture is a subset of the capture, not a copy kept beside it.

    ``review/wgs84-w0/make_anchor_fixture.py`` re-reads the frozen truth and
    must write exactly the committed file.
    """
    spec = importlib.util.spec_from_file_location(
        "make_anchor_fixture", W0 / "make_anchor_fixture.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = (REPO_ROOT / "tests" / "fixtures" / "htdp_anchors.py").read_text(encoding="utf-8")
    assert module.render() == fixture


def test_the_frozen_truth_is_the_capture_w0_recorded():
    # SHA-256 of review/wgs84-w0/htdp_truth.json as committed by W0, quoted in
    # the fixture's own provenance block.
    digest = hashlib.sha256((W0 / "htdp_truth.json").read_bytes()).hexdigest()
    assert digest == "101fd84019cc1480c9fb11ddc372a0303f1d71f530446d2080fd211e01419fb2"


# --------------------------------------------------------------------------
# (f) The round trip: HTDP's own non-closure, replicated.
# --------------------------------------------------------------------------

ROUND_TRIPS = [run.run_id for run in HTDP_RUNS if run.kind == "roundtrip_reverse"]


@pytest.mark.parametrize("run_id", ROUND_TRIPS)
def test_the_round_trip_chains_to_htdps_own_round_trip(run_id):
    """Forward, print, reverse the PRINTED numbers, print: HTDP's round-trip record.

    W0 fed HTDP's printed forward output back into HTDP. Chained here from the
    ORIGINAL input through this module twice, with HTDP's print rounding in
    between, the result must be HTDP's round-trip record string for string -
    including where that record fails to return to the original input.
    """
    rt = RUNS_BY_ID[run_id]
    forward = RUNS_BY_ID[rt.roundtrip_source]
    originals = {record.name: record for record in forward.records}
    for record in rt.records:
        start = originals[record.name]
        assert (record.lat_in, record.lonw_in, record.h_in) == (
            start.lat_out, start.lonw_out, start.h_out
        ), record.name
        printed = htdp_print(run_record(forward, start.lat_in, start.lonw_in, start.h_in))
        back = htdp_print(run_record(rt, *printed))
        assert back == (record.lat_out, record.lonw_out, record.h_out), (run_id, record.name)


def test_the_frozen_round_trips_include_records_that_do_not_close():
    """Anti-vacuity for the round-trip pin: HTDP's own records DO fail to close.

    RECON.md section 5: HTDP's arithmetic is not exactly invertible (two
    clocks, radii without a height term, a negated linearized Helmert), so on
    some records the printed round trip lands a print unit or more from where
    it started. This counts such records in the FIXTURE only - it never calls
    ``htdp`` and would pass against any module. What it establishes is that
    ``test_the_round_trip_chains_to_htdps_own_round_trip`` above is asked to
    reproduce non-closing records, not only closing ones; that test is the one
    that holds this module to HTDP's non-closure.

    RENAMED at interim gate 1 of the WGS 84 build (finding L7): it was
    ``test_htdps_round_trip_does_not_close_and_neither_does_this_one``, a name
    claiming a check of this module that the body never made.
    """
    non_closing = 0
    for run_id in ROUND_TRIPS:
        rt = RUNS_BY_ID[run_id]
        forward = RUNS_BY_ID[rt.roundtrip_source]
        originals = {record.name: record for record in forward.records}
        for record in rt.records:
            start = originals[record.name]
            if (float(record.lat_out), float(record.lonw_out), float(record.h_out)) != (
                float(start.lat_in), float(start.lonw_in), float(start.h_in)
            ):
                non_closing += 1
    assert non_closing > 0


# --------------------------------------------------------------------------
# (g) Near ties and window edges: the last place, and the window's own edges.
#
# Interim gate 1 of the WGS 84 build, findings L2 and L3. The 1,846 anchors
# above were chosen by position, and a printed digit only moves when the exact
# result crosses a rounding tie - so a change of one ulp in the ORDER of HTDP's
# operations left them all green (the reviewer's seeds S15 and S26). These
# records were TUNED, with W0's independent experiment.py and never with this
# module, so that one component's exact result sits beside a tie of HTDP's
# print, from below and from above; and so that the velocity lookup sits
# either side of each window edge. Their expected strings are the binary's
# (review/wgs84-w0/make_near_tie_anchors.py, near_tie_truth.json).
# --------------------------------------------------------------------------

NEAR_TIE_BY_ID = {run.run_id: run for run in NEAR_TIE_RUNS}
NEAR_TIE_IDS = [run.run_id for run in NEAR_TIE_RUNS]
NEAR_TIE_DIRECTIONS = [
    (menu, 1) for menu in (10, 11, 12, 25, 26)
] + [(1, menu) for menu in (10, 11, 12, 25, 26)]


def _near_tie_inside(record) -> bool:
    # Every record but a window-edge OUTSIDE one is a position MCX transforms.
    return not record.role.endswith("outside")


@functools.lru_cache(maxsize=None)
def near_tie_computed(run_id: str):
    """(record, ours, HTDP's) for every record MCX accepts, computed once."""
    run = NEAR_TIE_BY_ID[run_id]
    out = []
    for record in run.records:
        if not _near_tie_inside(record):
            continue
        ours = htdp_print(run_record(run, record.lat_in, record.lonw_in, record.h_in))
        out.append((record, ours, (record.lat_out, record.lonw_out, record.h_out)))
    return tuple(out)


def _near_tie_mismatches(run_id: str, component: int) -> list[str]:
    return [
        f"{record.name} ({record.role}): ours {ours[component]} HTDP {theirs[component]}"
        for record, ours, theirs in near_tie_computed(run_id)
        if ours[component] != theirs[component]
    ]


@pytest.mark.parametrize("run_id", NEAR_TIE_IDS)
def test_near_tie_latitude_is_htdps_printed_latitude(run_id):
    bad = _near_tie_mismatches(run_id, 0)
    assert not bad, f"{run_id}: {bad}"


@pytest.mark.parametrize("run_id", NEAR_TIE_IDS)
def test_near_tie_longitude_is_htdps_printed_longitude(run_id):
    bad = _near_tie_mismatches(run_id, 1)
    assert not bad, f"{run_id}: {bad}"


@pytest.mark.parametrize("run_id", NEAR_TIE_IDS)
def test_near_tie_height_is_htdps_printed_height(run_id):
    bad = _near_tie_mismatches(run_id, 2)
    assert not bad, f"{run_id}: {bad}"


def test_the_near_tie_generator_reproduces_its_fixture_byte_for_byte():
    """The drift guard, as for the positional anchors: render() == the file."""
    spec = importlib.util.spec_from_file_location(
        "make_near_tie_anchors", W0 / "make_near_tie_anchors.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = (REPO_ROOT / "tests" / "fixtures" / "htdp_near_tie_anchors.py").read_text(
        encoding="utf-8"
    )
    assert module.render() == fixture


def test_the_near_tie_capture_is_the_one_frozen():
    # SHA-256 of review/wgs84-w0/near_tie_truth.json as committed with the
    # gate-1 fixes, quoted in the fixture's own provenance block.
    digest = hashlib.sha256((W0 / "near_tie_truth.json").read_bytes()).hexdigest()
    assert digest == "0de61a57afd317cbb14492a74e088875afa05c616b2fe8865abbe3b5a5c9f348"
    fixture = (REPO_ROOT / "tests" / "fixtures" / "htdp_near_tie_anchors.py").read_text(
        encoding="utf-8"
    )
    assert f"truth file sha256 {digest}" in fixture


def test_the_near_ties_cover_every_direction_component_and_side():
    """The coverage the generator's docstring claims, checked, not trusted.

    Ten HTDP directions (menu 1 against 10, 11, 12, 25 and 26, each way) x six
    runs = 60 near-tie runs, each holding exactly one record per component
    (LA latitude, LO longitude, HT height) per side (below, above): 360
    records. No run is dated 2010-01-01, where HTDP runs no velocity and
    NEWCOR - where S15 lives - is never called.
    """
    tie_runs = [run for run in NEAR_TIE_RUNS if run.purpose == "near_tie"]
    assert len(tie_runs) == 60
    by_direction: dict[tuple[int, int], int] = {}
    for run in tie_runs:
        key = (run.frame_in_menu, run.frame_out_menu)
        by_direction[key] = by_direction.get(key, 0) + 1
        assert run.observation_date != datetime.date(2010, 1, 1), run.run_id
        roles = sorted(record.role for record in run.records)
        assert roles == sorted(
            f"tie {c} {side}" for c in ("LA", "LO", "HT") for side in ("below", "above")
        ), run.run_id
    assert by_direction == {direction: 6 for direction in NEAR_TIE_DIRECTIONS}


def _tie_distance(value: float, decimals: int) -> Fraction:
    """Signed distance of ``value`` from the rounding tie inside its print unit.

    In print units. ``%.{decimals}f`` rounds the exact value of the double, so
    its one decision point between the print units k and k + 1 is
    (k + 1/2) / 10**decimals, k = floor(value * 10**decimals).
    """
    scale = 10**decimals
    k = math.floor(Fraction(value) * scale)
    return Fraction(value) * scale - (Fraction(k) + Fraction(1, 2))


def test_every_near_tie_is_a_near_tie_as_this_module_computes_it():
    """Anti-vacuity: the records sit at a tie in THIS module's arithmetic too.

    The fixture's ``note`` is experiment.py's distance; recomputed here from
    this module's unrounded result, each record must lie on its stated side of
    its tie and within 1e-3 of a print unit of it. In practice the latitude
    and longitude records lie a few result ulps from their tie at most (one
    ulp is about 7e-15 degree here, 7e-5 of a print unit), and the height
    records within about 1e-9 m (1e-6 of a print unit), the granularity of
    HTDP's Cartesian round trip - so a change of that size, in the right
    direction, flips the printed digit. That is what makes them see S15 and
    S26.

    Worth knowing when reading which records catch S15: it is invisible on
    every to-NAD 83 path. There NEWCOR's second time is ITREF, so
    ``ylat2 == ylat`` exactly, and both ``ylat + ylat - ylat1`` and
    ``ylat + (ylat - ylat1)`` are exact in double precision - the two
    groupings cannot differ. Only the from-NAD 83 records can see it.
    """
    far = []
    for run in NEAR_TIE_RUNS:
        if run.purpose != "near_tie":
            continue
        for record in run.records:
            _, component, side = record.role.split()
            result = run_record(run, record.lat_in, record.lonw_in, record.h_in)
            value, decimals = {
                "LA": (result.latitude, 10),
                "LO": (-result.longitude, 10),
                "HT": (result.ellipsoid_height, 3),
            }[component]
            distance = _tie_distance(value, decimals)
            on_side = distance < 0 if side == "below" else distance > 0
            if not on_side or abs(distance) > Fraction(1, 1000):
                far.append(f"{record.name}: {float(distance):+.3e}")
            # And experiment.py's stated distance agrees with ours.
            assert float(distance) == pytest.approx(float(record.note), rel=1e-2, abs=1e-12), (
                record.name
            )
    assert not far, far


# The reviewer's own counterexamples (review/gate-wgs84-1/output.md, L2),
# recovered from the gate's deterministic fuzz: HTDP's print at each, frozen
# from the binary. S26 at the first is the one the reviewer quoted: HTDP
# prints 44.1607289389, ``math.radians`` gives ...388.
GATE1_COUNTEREXAMPLES = [
    ("GATE1S26N0", 10, 1, datetime.date(2002, 1, 20), "44.16073757508377", "84.2231097333896", "0.0", "44.1607289389"),
    ("GATE1S26N1", 10, 1, datetime.date(1995, 1, 28), "45.00005377942753", "89.46078879147638", "0.0", "45.0000453443"),
    ("GATE1S26N2", 25, 1, datetime.date(2026, 10, 1), "42.757733086988175", "90.95031453635029", "76.48566873467087", "42.7577255755"),
    ("GATE1S26N3", 25, 1, datetime.date(2034, 1, 3), "45.00007767533613", "86.07399523500962", "0.0", "45.0000691472"),
    ("GATE1S15N4", 1, 12, datetime.date(2022, 7, 23), "44.269962536263435", "82.54369826118517", "0.0", "44.2699714973"),
    ("GATE1S26N5", 1, 25, datetime.date(2033, 12, 6), "44.9999521625992", "83.50785611478302", "4532.693697117842", "44.9999611493"),
]


@pytest.mark.parametrize(
    "name,menu_in,menu_out,observed,lat,lonw,h,htdp_lat",
    GATE1_COUNTEREXAMPLES,
    ids=[row[0] for row in GATE1_COUNTEREXAMPLES],
)
def test_the_gate1_counterexamples_print_as_htdp_prints_them(
    name, menu_in, menu_out, observed, lat, lonw, h, htdp_lat
):
    (record,) = [
        record for run in NEAR_TIE_RUNS for record in run.records if record.name == name
    ]
    (run,) = [run for run in NEAR_TIE_RUNS if record in run.records]
    assert (run.frame_in_menu, run.frame_out_menu, run.observation_date) == (
        menu_in, menu_out, observed
    )
    assert (record.lat_in, record.lonw_in, record.h_in, record.lat_out) == (lat, lonw, h, htdp_lat)
    assert htdp_print(run_record(run, lat, lonw, h))[0] == htdp_lat


# --------------------------------------------------------------------------
# (b) The transcription, number for number against the committed Fortran.
# --------------------------------------------------------------------------

# SHA-256 of each committed source file, from W0's capture
# (htdp_truth.json -> provenance.source_sha256, RECON.md header).
SOURCE_SHA256 = {
    "htdp.f": "97a46675b4fb9de24152ed70fc3a34f72017e90cb77e4994696dfd5dffb75271",
    "initbd.f": "66da175e3cb7a979b3179633a2517b194f14286e47f154bffca9760315de696d",
    "initeq.f": "c2d92dec9d9c3402589c8a9d9aa873ddaefb2925577b38be252475c71cd0eac9",
    "initps.f": "543eb7c650f8f9a8047bbf66e8cdddd205c32512ee46e069a0765e0b97655945",
    "initvl.f": "06455583630018c888db5f6828e55972b80477548df92790a3e5a30483dc1e56",
}


@pytest.mark.parametrize("name", sorted(SOURCE_SHA256))
def test_the_committed_htdp_source_is_the_pinned_bytes(name):
    assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == SOURCE_SHA256[name]


def test_the_committed_source_is_every_fortran_file_and_no_other():
    assert sorted(p.name for p in SOURCE.glob("*.f")) == sorted(SOURCE_SHA256)


_SETTP_FIELDS = {
    "tx": "tx_m", "ty": "ty_m", "tz": "tz_m",
    "dtx": "dtx_m_per_yr", "dty": "dty_m_per_yr", "dtz": "dtz_m_per_yr",
    "rx": "rx_arcsec", "ry": "ry_arcsec", "rz": "rz_arcsec",
    "drx": "drx_arcsec_per_yr", "dry": "dry_arcsec_per_yr", "drz": "drz_arcsec_per_yr",
    "scale": "scale", "dscale": "dscale_per_yr", "refepc": "reference_epoch",
}
_ROTATIONS = {"rx", "ry", "rz", "drx", "dry", "drz"}
_SETTP_LINE = re.compile(
    r"^\s+(?P<name>tx|ty|tz|dtx|dty|dtz|rx|ry|rz|drx|dry|drz|scale|dscale|refepc)"
    r"(?P<iers>1?)\(\s*(?P<iopt>\d+)\)\s*=\s*"
    r"(?P<lit>[-+]?(?:\d+\.?\d*|\.\d+)(?:[dD][-+]?\d+)?)\s*(?P<div>/\s*rhosec)?\s*(?:!.*)?$"
)


def _fortran_double(literal: str) -> float:
    """A Fortran DOUBLE PRECISION literal (``0.10201d-9``) as Python reads it."""
    return float(literal.replace("d", "e").replace("D", "e"))


def test_the_helmert_sets_are_settp_number_for_number():
    """Both conventions, frames 1, 15, 16, 17: every field, its unit, its line.

    SETTP runs from htdp.f:3618 to the end of its IERS block before frit94 at
    4475. Each field must be assigned exactly once there, equal the transcribed
    value, carry ``/ rhosec`` exactly when it is a rotation or a rotation rate,
    and sit inside the line range the record cites.
    """
    lines = _lines("htdp.f")
    found: dict[tuple[bool, int, str], list[tuple[int, str, bool]]] = {}
    for number in range(3618, 4475):
        match = _SETTP_LINE.match(lines[number - 1])
        if match and int(match["iopt"]) in (1, 15, 16, 17):
            key = (match["iers"] == "1", int(match["iopt"]), match["name"])
            found.setdefault(key, []).append((number, match["lit"], match["div"] is not None))

    checked = 0
    for iers, table in ((False, htdp_data.IGS_CONVENTION), (True, htdp_data.IERS_CONVENTION)):
        assert sorted(table) == [1, 15, 16, 17]
        for iopt, params in table.items():
            assert params.iopt == iopt
            first, last = (int(x) for x in params.source.split(":")[1].split("-"))
            for name, attribute in _SETTP_FIELDS.items():
                hits = found.get((iers, iopt, name), [])
                assert len(hits) == 1, (iers, iopt, name, hits)
                number, literal, divided = hits[0]
                assert first <= number <= last, (iers, iopt, name, number, params.source)
                assert getattr(params, attribute) == _fortran_double(literal), (
                    iers, iopt, name, literal
                )
                assert divided == (name in _ROTATIONS), (iers, iopt, name)
                checked += 1
    assert checked == 2 * 4 * 15


def test_rotations_are_divided_by_rhosec_exactly_once_at_use():
    # SETTP stores rx(1) = 0.02579d0 / rhosec (htdp.f:3658): one division of
    # the arcsecond literal by RHOSEC = (180*3600)/PI (htdp.f:165). The
    # property must be that same single division, bit for bit.
    params = htdp_data.IGS_CONVENTION[1]
    assert params.rx_rad == 0.02579 / ((180.0 * 3600.0) / (4.0 * math.atan(1.0)))
    # HTDP's own earlier-value comment on that line: "!Previous 1.25033d-7
    # rad" - so the literal is ARCSECONDS, not the "mas" htdp.f:3650 claims.
    assert abs(params.rx_rad - 1.25033e-7) < 5e-13


_NODE_LINE = re.compile(
    r"^\s+DATA B\(\s*(\d+)\), B\(\s*(\d+)\), B\(\s*(\d+)\) /\s*(\S+),\s*(\S+),\s*(\S+) /\s*$"
)


def _single_from_text(text: str) -> float:
    """A Fortran REAL literal rounded to single precision EXACTLY, from its text.

    Independent of ``htdp_data.fortran_real``, which goes decimal -> double ->
    single: here the decimal is rounded once, as the compiler does, by exact
    rational arithmetic - so a double-rounding case would show as a mismatch.
    """
    q = Fraction(text)
    if q == 0:
        return 0.0
    sign = -1 if q < 0 else 1
    q = abs(q)
    e = q.numerator.bit_length() - q.denominator.bit_length()
    while Fraction(2) ** e > q:
        e -= 1
    while Fraction(2) ** (e + 1) <= q:
        e += 1
    # 2**e <= q < 2**(e+1); a 24-bit significand puts the last place at 2**(e-23).
    n = round(q / Fraction(2) ** (e - 23))  # round half to even
    return sign * float(n * Fraction(2) ** (e - 23))


def test_the_velocity_window_is_initvl_number_for_number():
    """All 480 nodes: each at its initvl.f line and B index, each value its literal.

    Node (I, J) is at initvl.f line 42988 + (I - 1) * 53 + (J - 1) (the file
    walks grid 6 column by column from line 42988, after the header at
    42981-42987), and IUNGRD (htdp.f:1740-1741) reads it from
    B(NBASE + 3 * ((J - 1) * (ICNTX + 1) + (I - 1)) + 1) with NBASE = 128808
    and ICNTX + 1 = 89.
    """
    lines = _lines("initvl.f")
    literals = htdp_data._GRID6_WINDOW_LITERALS
    assert len(literals) == 480 == len(htdp_data.GRID6_WINDOW)
    for (i, j), literal in literals.items():
        number = 42988 + (i - 1) * 53 + (j - 1)
        match = _NODE_LINE.match(lines[number - 1])
        assert match, (i, j, number)
        assert int(match[1]) == 128808 + 3 * ((j - 1) * 89 + (i - 1)) + 1, (i, j)
        texts = (match[4], match[5], match[6])
        assert literal == tuple(float(t) for t in texts), (i, j, texts)
        assert htdp_data.GRID6_WINDOW[(i, j)] == tuple(_single_from_text(t) for t in texts), (
            i, j, texts
        )


def test_the_velocity_grid_header_is_initvl():
    header = "\n".join(_lines("initvl.f")[42980:42987])  # lines 42981-42987
    for token, value in (
        ("GRDLX", htdp_data.GRID6_LOWER_EAST_LONGITUDE),
        ("GRDUX", htdp_data.GRID6_UPPER_EAST_LONGITUDE),
        ("GRDLY", htdp_data.GRID6_LOWER_LATITUDE),
        ("GRDUY", htdp_data.GRID6_UPPER_LATITUDE),
        ("ICNTX", htdp_data.GRID6_CELLS_EAST),
        ("ICNTY", htdp_data.GRID6_CELLS_NORTH),
        ("NBASE", htdp_data.GRID6_NBASE),
    ):
        match = re.search(token + r"\( 6\) /\s*([0-9.]+)\s*/", header)
        assert match, token
        assert float(match[1]) == value, token
    # The header values are all exact in single precision (250, 294, 24, 50
    # are integers below 2**24), so REAL-literal rounding does not touch them.
    for value in (250.0, 294.0, 24.0, 50.0):
        assert _single_from_text(repr(value)) == value


def test_fortran_real_rounds_to_single_precision_half_to_even():
    # 1 + 2**-24 lies exactly halfway between the single-precision neighbours
    # 1 and 1 + 2**-23; ties go to the even significand, which is 1.
    assert htdp_data.fortran_real(1.0 + 2.0**-24) == 1.0
    # 1 + 3 * 2**-24 lies halfway between 1 + 2**-23 (odd) and 1 + 2**-22
    # (even): it goes up to 1 + 2**-22.
    assert htdp_data.fortran_real(1.0 + 3 * 2.0**-24) == 1.0 + 2.0**-22
    # -15.08 as a single is -15.079999923706055 (exact rational rounding of
    # the text, independent of the function under test).
    assert htdp_data.fortran_real(-15.08) == _single_from_text("-15.08") == -15.079999923706055
    assert htdp_data.fortran_real(0.0) == 0.0


def _line(name: str, number: int) -> str:
    return _lines(name)[number - 1]


def test_model_and_inline_constants_are_htdp_f():
    """Each constant ``htdp_data`` cites, read back off the line it cites."""
    assert re.fullmatch(r"\s+A = 6378137\.D0\s*", _line("htdp.f", 151))
    assert htdp_data.SEMI_MAJOR_AXIS_M == 6378137.0
    m = re.fullmatch(r"\s+F = 1\.D0 / ([0-9.]+)D0\s*", _line("htdp.f", 152))
    assert m and float(m[1]) == htdp_data.GRS80_INVERSE_FLATTENING
    m = re.fullmatch(
        r"\s+IF \(ELPSD \.EQ\. 'WGS84'\) F = 1\.D0 / ([0-9.]+)D0\s*", _line("htdp.f", 154)
    )
    assert m and float(m[1]) == htdp_data.WGS84_INVERSE_FLATTENING
    assert "PI = 4.D0 * DATAN(1.D0)" in _line("htdp.f", 164)
    assert htdp_data.PI == 4.0 * math.atan(1.0)
    assert "RHOSEC = (180.D0 * 3600.D0) / PI" in _line("htdp.f", 165)
    assert "TWOPI = PI + PI" in _line("htdp.f", 166)
    m = re.search(r"rad2deg = 180\.d0/([0-9.]+)d0", _line("htdp.f", 2766))
    assert m and float(m[1]) == htdp_data.TRUNCATED_PI
    assert "parameter(maxint=10,tol=1.d-13)" in _line("htdp.f", 926)
    assert (htdp_data.FRMXYZ_MAX_ITERATIONS, htdp_data.FRMXYZ_TOLERANCE) == (10, 1.0e-13)
    assert "if(dabs(glat).le.0.7854d0) then" in _line("htdp.f", 957)
    assert htdp_data.FRMXYZ_HEIGHT_SWITCH_RAD == 0.7854
    assert "DTIME = DBLE(MIN - ITREF) / 525960.D0" in _line("htdp.f", 7322)
    assert htdp_data.MINUTES_PER_JULIAN_YEAR == 525960.0
    assert [_line("htdp.f", n).split("=")[1].strip() for n in (169, 170, 171)] == ["2010", "1", "1"]
    assert htdp_data.VELOCITY_REFERENCE_DATE == (2010, 1, 1)
    assert "IF(IYEAR .le. 1906) THEN" in _line("htdp.f", 7891)
    assert htdp_data.EARLIEST_YEAR_EXCLUSIVE == 1906
    assert "HTDP_version = '3.6.0'" in _line("htdp.f", 27)
    assert "Version_date = 'April 7, 2025'" in _line("htdp.f", 28)
    assert (htdp_data.HTDP_VERSION, htdp_data.HTDP_VERSION_DATE) == ("3.6.0", "April 7, 2025")


# Every line citation into the committed Fortran, in the three modules that
# make them. Interim gate 1 of the WGS 84 build (finding L1) found ten wrong
# ones - _toit94's comments each a line late, _newcor's likewise, NAD 83's
# MENU1 entry citing the blank line above it - and nothing checked them, since
# only SETTP's citations were read back. A citation is
#
#   FILE:N  or  FILE:N-M     FILE one of htdp.f, initvl.f, initbd.f, initeq.f,
#                            initps.f
#
# optionally continued by further numbers that name more lines of the SAME
# file ("htdp.f:3229 and 3264", "``htdp.f:3245``, ``3276-3283``"), and, in
# htdp.py only, the short form "# :N" or "# :N-M" on a code line, which that
# module uses for htdp.f where the full form would overflow the line. What can
# be checked mechanically, and is: the cited line exists and is not blank, and
# for a range the first and last lines both exist, both are non-blank, and the
# range runs forwards. A one-line-late citation onto a blank line - every one
# L1 named whose target was blank - fails it; a citation onto a wrong but
# non-blank line needs a reader, and the reviewer paired all 127 single-line
# citations by hand.
_CITED_FILES = ("htdp.f", "initvl.f", "initbd.f", "initeq.f", "initps.f")
_CITATION_CONTINUATION = (
    r"(?:(?:``)?\s*(?:,|\band\b)\s*(?:``)?\d{1,6}(?:-\d{1,6})?(?![\d.]))*"
)
_FULL_CITATION = re.compile(
    r"\b(htdp\.f|initvl\.f|initbd\.f|initeq\.f|initps\.f):"
    r"(\d{1,6}(?:-\d{1,6})?" + _CITATION_CONTINUATION + ")"
)
_SHORT_CITATION = re.compile(r"#\s*:(\d{1,6}(?:-\d{1,6})?" + _CITATION_CONTINUATION + ")")
_CITED_NUMBER = re.compile(r"(\d{1,6})(?:-(\d{1,6}))?")
_CITING_MODULES = ("htdp.py", "htdp_data.py", "frames.py")


def _citations(
    module: str, text: str | None = None
) -> list[tuple[int, str, int, int | None]]:
    """(module line, cited file, first line, last line or None) for every citation.

    ``text`` stands in for the module's source, so the checker itself can be
    shown a known-bad citation (interim gate 1 re-confirmation, N2).
    """
    if text is None:
        text = (REPO_ROOT / "michspc" / "spc" / module).read_text(encoding="utf-8")
    found = []
    for number, line in enumerate(text.split("\n"), 1):
        specs = [(m[1], m[2]) for m in _FULL_CITATION.finditer(line)]
        if module == "htdp.py":
            specs += [("htdp.f", m[1]) for m in _SHORT_CITATION.finditer(line)]
        for cited, spec in specs:
            for first, last in _CITED_NUMBER.findall(spec):
                found.append((number, cited, int(first), int(last) if last else None))
    return found


def _bad_citations(
    module: str, sources: dict[str, list[str]], text: str | None = None
) -> list[str]:
    bad = []
    for number, cited, first, last in _citations(module, text):
        lines = sources[cited]

        def blank_or_missing(k: int) -> bool:
            return not 1 <= k <= len(lines) or not lines[k - 1].strip()

        if (
            blank_or_missing(first)
            or (last is not None and (last < first or blank_or_missing(last)))
        ):
            span = f"{first}-{last}" if last is not None else f"{first}"
            bad.append(f"{module}:{number} cites {cited}:{span}")
    return bad


@pytest.mark.parametrize("module", _CITING_MODULES)
def test_every_fortran_line_citation_names_a_real_non_blank_line(module):
    sources = {name: _lines(name) for name in _CITED_FILES}
    # Anti-vacuity: each module makes citations the parser sees. htdp_data.py
    # alone carries 480 initvl.f node citations, so its floor is that.
    floor = {"htdp.py": 150, "htdp_data.py": 480, "frames.py": 10}[module]
    assert len(_citations(module)) >= floor, module
    bad = _bad_citations(module, sources)
    assert not bad, bad


def test_the_citation_check_flags_the_citations_it_exists_to_flag():
    """The checker, shown known-bad citations, names each one and only those.

    Interim gate 1's re-confirmation (N2): the parser was pinned, the verdict
    was not - replacing ``bad.append`` with ``pass``, or dropping the
    blank-line test, left the suite green. Each probe below is derived from
    the committed htdp.f (the next test asserts 4676, 7378 and 4677; 4678 is
    the non-blank ``nframe(1)`` line, and 8,949 lines is the file's length):

    * line 1, ``htdp.f:4676-4677`` - 4676 is blank: L1's own wrong citation;
    * line 2, ``htdp.f:7378`` - blank: L1's ``_newcor`` citation;
    * line 3, ``htdp.f:4614-4603`` - a reversed range;
    * line 4, ``htdp.f:99999`` - past the end of the file;
    * line 5, ``# :7378`` - the short form onto the same blank line;
    * line 6, ``htdp.f:4677-4678`` - correct (``iframe(1) = 1`` and the
      ``nframe(1)`` line), so it must NOT be flagged.
    """
    sources = {name: _lines(name) for name in _CITED_FILES}
    text = "\n".join(
        (
            "a = 1  # htdp.f:4676-4677",
            "b = 2  # htdp.f:7378",
            "c = 3  # htdp.f:4614-4603",
            "d = 4  # htdp.f:99999",
            "e = 5  # :7378",
            "f = 6  # htdp.f:4677-4678",
        )
    )
    assert _bad_citations("htdp.py", sources, text) == [
        "htdp.py:1 cites htdp.f:4676-4677",
        "htdp.py:2 cites htdp.f:7378",
        "htdp.py:3 cites htdp.f:4614-4603",
        "htdp.py:4 cites htdp.f:99999",
        "htdp.py:5 cites htdp.f:7378",
    ]


def test_the_citation_check_sees_each_form_it_claims_to():
    """The parser, on the forms L1's citations took, before and after the fix.

    Each probe line is checked against the real htdp.f: 4676 and 7378 are
    blank (the lines L1 found cited), 4611 and 7386 are blank, 4677 is
    ``iframe(1) = 1`` and 7387 is ``YLAT3 = YLAT + YLAT2 - YLAT1``.
    """
    sources = {name: _lines(name) for name in _CITED_FILES}
    assert not sources["htdp.f"][4676 - 1].strip()
    assert not sources["htdp.f"][7378 - 1].strip()
    assert sources["htdp.f"][4677 - 1].strip() == "iframe(1) = 1"
    assert sources["htdp.f"][7387 - 1].strip() == "YLAT3 = YLAT + YLAT2 - YLAT1"
    probes = {
        "# htdp.f:4676-4677": [("htdp.f", 4676, 4677)],
        "x  # :7380-7381": [("htdp.f", 7380, 7381)],
        "(``htdp.f:3245``, ``3276-3283``)": [("htdp.f", 3245, None), ("htdp.f", 3276, 3283)],
        "htdp.f:3229 and 3264": [("htdp.f", 3229, None), ("htdp.f", 3264, None)],
        "initvl.f:42988 B(128809)": [("initvl.f", 42988, None)],
    }
    for line, expected in probes.items():
        got = []
        for m in _FULL_CITATION.finditer(line):
            got += [(m[1], int(a), int(b) if b else None) for a, b in _CITED_NUMBER.findall(m[2])]
        for m in _SHORT_CITATION.finditer(line):
            got += [("htdp.f", int(a), int(b) if b else None) for a, b in _CITED_NUMBER.findall(m[1])]
        assert got == expected, line


def test_the_frames_are_menu1s_own():
    """Menu number, internal index and 24-character name, as MENU1 assigns them."""
    lines = _lines("htdp.f")
    iframe, nframe = {}, {}
    for number in range(4667, 4797):
        m = re.match(r"\s+iframe\(\s*(\d+)\)\s*=\s*(\d+)", lines[number - 1])
        if m:
            iframe[int(m[1])] = int(m[2])
        m = re.match(r"\s+nframe\(\s*(\d+)\)\s*=\s*'(.{24})'", lines[number - 1])
        if m:
            nframe[int(m[1])] = m[2]
    assert [f.menu for f in htdp.ALL_HTDP_FRAMES] == [1, 10, 11, 12, 25, 26]
    for frame in htdp.ALL_HTDP_FRAMES:
        assert iframe[frame.menu] == frame.iopt, frame
        assert nframe[frame.menu] == frame.htdp_name, frame


def _regions_1_to_6() -> dict[int, list[tuple[float, float]]]:
    """Region polygons 1-6 from initbd.f: (lat, east lon) vertices, via NPOINT."""
    text = (SOURCE / "initbd.f").read_text(encoding="latin-1")
    npoint = {int(a): int(b) for a, b in re.findall(r"NPOINT\(\s*(\d+)\)\s*/\s*(\d+)\s*/", text)}
    vertex = {
        int(k): (float(x), float(y))
        for k, x, y in re.findall(
            r"DATA\s+X\(\s*(\d+)\), Y\(\s*\d+\) /\s*([0-9.]+),\s*([0-9.]+)\s*/", text
        )
    }
    return {
        region: [vertex[k] for k in range(npoint[region], npoint[region + 1])]
        for region in range(1, 7)
    }


# The window in degrees, from htdp_data's node ranges: east longitude
# 250 + (I - 1) * 0.5 for I 37..60 is 268.0..279.5, latitude 24 + (J - 1) * 0.5
# for J 34..53 is 40.5..50.0.
WINDOW_EAST = (268.0, 279.5)
WINDOW_LAT = (40.5, 50.0)


def test_the_window_is_the_rectangle_the_node_ranges_say():
    i0, i1 = htdp_data.WINDOW_I_RANGE
    j0, j1 = htdp_data.WINDOW_J_RANGE
    assert (250.0 + (i0 - 1) * 0.5, 250.0 + (i1 - 1) * 0.5) == WINDOW_EAST
    assert (24.0 + (j0 - 1) * 0.5, 24.0 + (j1 - 1) * 0.5) == WINDOW_LAT


def test_inside_the_window_getreg_can_only_answer_region_6():
    """Why ``_window_cell`` may stand in for GETREG (htdp.f:277-303).

    GETREG tests regions 1, 2, 3, ... in order and takes the first containing
    the point. Regions 1-5 all lie west of 253 E, so nothing in the window
    (268.0 E and east of it) can be in one; region 6 is the rectangle 24-50 N,
    250-294 E, which contains the whole window - its north edge 50.0 being
    refused by the window check itself.
    """
    regions = _regions_1_to_6()
    for region in range(1, 6):
        assert max(lon for _, lon in regions[region]) < WINDOW_EAST[0], region
    lats = [lat for lat, _ in regions[6]]
    lons = [lon for _, lon in regions[6]]
    assert len(regions[6]) == 4
    assert (min(lats), max(lats)) == (24.0, 50.0)
    assert (min(lons), max(lons)) == (250.0, 294.0)
    assert min(lats) < WINDOW_LAT[0] and WINDOW_LAT[1] <= max(lats)
    assert min(lons) < WINDOW_EAST[0] and WINDOW_EAST[1] < max(lons)


def test_no_earthquake_or_postseismic_term_can_reach_the_window():
    """Why COMPSN's earthquake loop and PSDISP are not transcribed.

    COMPSN (htdp.f:7333-7359) applies earthquake I only within EQRAD(I) of its
    epicentre, by HTDP's flat distance: DDLAT = (YLAT - EQLATR) * RADMER,
    DDLON = (YLON - EQLONR) * RADPAR, radii at the epicentre's latitude on the
    current (GRS 80) ellipsoid, longitudes positive west in radians. That
    distance is separable, so its minimum over a rectangle is at the clamped
    point. COMPSN runs at the output-frame position, a few metres from the
    lookup position the window bounds; the rectangle is widened by 0.01 degree
    (about a kilometre) to cover that. Every earthquake must stay outside.

    PSDISP (htdp.f:8132-8141) applies only inside its one grid, 210-225 E,
    60-66 N (initps.f:10-13), which the window is nowhere near.
    """
    text = (SOURCE / "initeq.f").read_text(encoding="latin-1")
    assert re.search(r"DATA NUMEQ\s*/\s*33\s*/", text)
    field = {
        name: {int(k): float(v) for k, v in re.findall(name + r"\(\s*(\d+)\)\s*/\s*([-0-9.E+]+)\s*/", text)}
        for name in ("EQLATR", "EQLONR", "EQRAD")
    }
    assert all(sorted(field[name]) == list(range(1, 34)) for name in field)
    margin = 0.01
    lat_lo, lat_hi = (math.radians(WINDOW_LAT[0] - margin), math.radians(WINDOW_LAT[1] + margin))
    # Positive-west radians of the window's east longitudes.
    w_lo = math.radians(360.0 - (WINDOW_EAST[1] + margin))
    w_hi = math.radians(360.0 - (WINDOW_EAST[0] - margin))
    closest = math.inf
    for k in range(1, 34):
        eqlat = htdp_data.fortran_real(field["EQLATR"][k])  # REAL literals
        eqlon = htdp_data.fortran_real(field["EQLONR"][k])
        eqrad = htdp_data.fortran_real(field["EQRAD"][k])
        radmer, radpar = htdp._radii(eqlat, htdp.GRS80)
        dlat = (min(max(eqlat, lat_lo), lat_hi) - eqlat) * radmer
        dlon = (min(max(eqlon, w_lo), w_hi) - eqlon) * radpar
        closest = min(closest, math.sqrt(dlat * dlat + dlon * dlon) - eqrad)
    assert closest > 500_000.0, closest  # metres beyond the nearest radius

    ps = "\n".join(_lines("initps.f")[9:13])  # initps.f:10-13
    bounds = [float(v) for v in re.findall(r"PSG[LU][XY]\( 1\) /\s*([0-9.]+)\s*/", ps)]
    assert bounds == [210.0, 225.0, 60.0, 66.0]
    assert WINDOW_EAST[1] < bounds[0] or WINDOW_EAST[0] > bounds[1]


# --------------------------------------------------------------------------
# (c) The ellipsoid follows the frame name.
# --------------------------------------------------------------------------


def test_the_ellipsoid_follows_the_frame_name():
    # htdp.f:3221-3224: WGS84 when the name begins 'WGS84', else GRS80.
    for frame in (htdp.WGS84_G1762, htdp.WGS84_G2139, htdp.WGS84_G2296):
        assert frame.ellipsoid is htdp.WGS84_ELLIPSOID, frame
    for frame in (htdp.NAD83_2011, htdp.ITRF2014, htdp.ITRF2020):
        assert frame.ellipsoid is htdp.GRS80, frame
    # htdp.f:152 and 154.
    assert htdp.GRS80.f == 1.0 / 298.257222101
    assert htdp.WGS84_ELLIPSOID.f == 1.0 / 298.257223563


def test_same_helmert_different_ellipsoid_differs_exactly_as_htdps_prints_do():
    """WGS84(G2296) and ITRF2020 share every Helmert parameter (both iopt 17).

    So any difference between their outputs from identical input numbers is
    the ellipsoid alone. HTDP prints a difference on some records and not on
    others; this module must differ on exactly the same records, the same
    way - and the pairing must exist in the fixture for the claim to mean
    anything.
    """
    pairs = [("f12", "f26"), ("f11", "f25")]
    differing = 0
    compared = 0
    for wgs, itrf in pairs:
        for run in HTDP_RUNS:
            if wgs not in run.run_id or run.kind.startswith("calendar"):
                continue
            twin = RUNS_BY_ID[run.run_id.replace(wgs, itrf)]
            theirs_a = {r.name: (r.lat_in, r.lonw_in, r.h_in, r.lat_out, r.lonw_out, r.h_out)
                        for r in run.records}
            theirs_b = {r.name: (r.lat_in, r.lonw_in, r.h_in, r.lat_out, r.lonw_out, r.h_out)
                        for r in twin.records}
            ours_a = {name: o for name, o, _ in computed(run.run_id)}
            ours_b = {name: o for name, o, _ in computed(twin.run_id)}
            for name in sorted(set(theirs_a) & set(theirs_b)):
                if theirs_a[name][:3] != theirs_b[name][:3]:
                    continue  # round trips start from different inputs
                compared += 1
                htdp_differs = theirs_a[name][3:] != theirs_b[name][3:]
                ours_differ = ours_a[name] != ours_b[name]
                assert ours_differ == htdp_differs, (run.run_id, name)
                differing += htdp_differs
    assert compared > 100 and differing > 0, (compared, differing)


@pytest.mark.parametrize("direction", ["to_nad83", "from_nad83"])
def test_the_ellipsoid_difference_has_its_hand_derived_size(direction):
    """About 0.1 mm north at 45 degrees, from the two flattenings alone.

    Derivation. WGS 84's f is 1/298.257223563 and GRS 80's 1/298.257222101
    (htdp.f:154, 152); e2 = f(2 - f) (htdp.f:161), so
        d(e2) = 2 (1 - f) df,  df = 1/298.257223563 - 1/298.257222101
              = -1.462e-6 / (298.257223563 * 298.257222101) = -1.6435e-11,
        d(e2) = -3.2847e-11.
    The same (lat, h) on an ellipsoid with e2 larger by d(e2) is, to first
    order, the point displaced north by a sin(lat) cos(lat) d(e2) / ... :
    with N = a / W, dN/d(e2) = a sin^2 / 2 (W ~ 1), the Cartesian change is
    dp = (a sin^2 / 2) cos d(e2), dz = (a sin^2 / 2 - a) sin d(e2), and its
    north component -sin dp + cos dz = -a sin cos d(e2).
    Forward (same numbers read on WGS 84 vs on GRS 80, output both on GRS 80):
    G2296 minus ITRF2020 north = -a sin cos d(e2) = +a/2 sin(2 lat) 3.2847e-11
    = +1.0475e-4 m at 45 N. Reverse (the same XYZ read back on WGS 84 vs GRS
    80): the opposite sign. Up: -a sin^2 d(e2) / 2 = +5.24e-5 m forward at 45 N.
    First order in d(e2), neglecting e2-relative terms: held to 2 percent.
    """
    epoch = htdp.ObservationEpoch(datetime.date(2020, 1, 1))
    lat, lon, h = 45.0, -84.5, 200.0
    call = getattr(htdp, direction)
    a = call(lat, lon, h, htdp.WGS84_G2296, epoch)
    b = call(lat, lon, h, htdp.ITRF2020, epoch)
    m_radius = 6378137.0 * (1 - 0.00669438) / (1 - 0.00669438 * 0.5) ** 1.5  # GRS80 M at 45
    north = math.radians(a.latitude - b.latitude) * m_radius
    up = a.ellipsoid_height - b.ellipsoid_height
    sign = 1.0 if direction == "to_nad83" else -1.0
    assert north == pytest.approx(sign * 1.0475e-4, rel=0.02)
    assert up == pytest.approx(sign * 5.24e-5, rel=0.02)


# --------------------------------------------------------------------------
# (d) HTDP's calendar arithmetic, hand-derived from IYMDMJ and GETMDY.
# --------------------------------------------------------------------------


def test_iymdmj_hand_derived():
    """IYMDMJ (htdp.f:8056-8081), by hand, at the dates the build leans on.

    2010-01-01: month < 3, so IYRP = 2009, IMOP = 13. A = int(20.09) = 20;
      B = 2 - 20 + int(5.0) = -13; C = int(365.25 * 2009) = int(733787.25) =
      733787; D = int(30.6001 * 14) = int(428.4014) = 428;
      MJD = -13 + 733787 + 428 + 1 - 679006 = 55197.
    2024-02-29: IYRP = 2023, IMOP = 14. A = 20, B = -13,
      C = int(738900.75) = 738900, D = int(30.6001 * 15) = int(459.0015) = 459;
      MJD = -13 + 738900 + 459 + 29 - 679006 = 60369.
    2024-01-01: IYRP 2023, IMOP 13: -13 + 738900 + 428 + 1 - 679006 = 60310.
    2025-01-01: IYRP 2024, C = int(739266.0) = 739266:
      -13 + 739266 + 428 + 1 - 679006 = 60676.
    2025-03-01: month 3, so IYRP = 2025, IMOP = 3; C = int(739631.25) = 739631,
      D = int(30.6001 * 4) = int(122.4004) = 122;
      MJD = -13 + 739631 + 122 + 1 - 679006 = 60735.
    2026-01-01: IYRP 2025, IMOP 13: -13 + 739631 + 428 + 1 - 679006 = 61041.
    2026-10-20: IYRP 2026, IMOP 10; C = int(739996.5) = 739996,
      D = int(30.6001 * 11) = int(336.6011) = 336;
      MJD = -13 + 739996 + 336 + 20 - 679006 = 61333.
    2027-01-01: IYRP 2026, IMOP 13: -13 + 739996 + 428 + 1 - 679006 = 61406.
    """
    for ymd, mjd in (
        ((2010, 1, 1), 55197), ((2024, 2, 29), 60369), ((2024, 1, 1), 60310),
        ((2025, 1, 1), 60676), ((2025, 3, 1), 60735), ((2026, 1, 1), 61041),
        ((2026, 10, 20), 61333), ((2027, 1, 1), 61406),
    ):
        assert htdp._iymdmj(*ymd) == mjd, ymd
        assert htdp.ObservationEpoch(datetime.date(*ymd)).mjd == mjd


def test_decimal_year_and_minutes_hand_derived():
    """GETMDY option 1 (htdp.f:7913-7920): DATE = y + (MJD - MJD0)/(MJD1 - MJD0).

    From the MJDs of test_iymdmj_hand_derived:
    2010-01-01: 2010 + 0/365 = 2010.0; MINS = 55197 * 1440 = 79,483,680.
    2024-02-29: 2024 + (60369 - 60310)/(60676 - 60310) = 2024 + 59/366;
                MINS = 60369 * 1440 = 86,931,360.
    2025-03-01: 2025 + (60735 - 60676)/(61041 - 60676) = 2025 + 59/365;
                MINS = 60735 * 1440 = 87,458,400.
    2026-10-20: 2026 + (61333 - 61041)/(61406 - 61041) = 2026 + 292/365, which
                is 2026.8 exactly in rational terms and in floating point;
                MINS = 61333 * 1440 = 88,319,520.
    """
    cases = (
        ((2010, 1, 1), 2010.0, 79_483_680),
        ((2024, 2, 29), 2024.0 + 59.0 / 366.0, 86_931_360),
        ((2025, 3, 1), 2025.0 + 59.0 / 365.0, 87_458_400),
        ((2026, 10, 20), 2026.8, 88_319_520),
    )
    for ymd, decimal_year, minutes in cases:
        epoch = htdp.ObservationEpoch(datetime.date(*ymd))
        assert epoch.decimal_year == decimal_year, ymd
        assert epoch.minutes == minutes, ymd
    # HTDP printed these DATEs to 4 places in its headers (htdp_truth.json):
    # 02-29-2024 (2024.1612), 03-01-2025 (2025.1616), 10-20-2026 (2026.8000).
    assert round(htdp.ObservationEpoch(datetime.date(2024, 2, 29)).decimal_year, 4) == 2024.1612
    assert round(htdp.ObservationEpoch(datetime.date(2025, 3, 1)).decimal_year, 4) == 2025.1616


def test_itref_and_the_nad83_epoch_are_2010_january_1():
    # htdp.f:169-173: ITREF = MJD(2010-01-01) * 24 * 60 = 55197 * 1440.
    assert htdp.ITREF == 79_483_680
    # The NAD 83 side of W0's runs was entered as decimal 2010.0. GETMDY
    # option 2 (htdp.f:7941-7963) takes DATE = 2010.0 as typed and, with a
    # zero day fraction, MINS = MJD(2010, 1, 1) * 1440 = ITREF. Calendar entry
    # of 2010-01-01 gives DATE = 2010 + 0/365 and the same MINS: identical.
    assert htdp.NAD83_2011_EPOCH.date == datetime.date(2010, 1, 1)
    assert htdp.NAD83_2011_EPOCH.decimal_year == 2010.0
    assert htdp.NAD83_2011_EPOCH.minutes == htdp.ITREF


def test_the_result_states_htdps_clocks_and_which_epoch_the_helmert_used():
    """Forward 2026-10-20 to 2010-01-01: the velocity clock runs backwards.

    MIN2 - MIN1 = (55197 - 61333) * 1440 = -6136 * 1440 = -8,835,840 minutes;
    in HTDP's Julian years, -8,835,840 / 525,960 = -6136 / 365.25
    = -16.7994524... The Helmert is evaluated at the INPUT epoch both ways
    (htdp.f:3230-3231).
    """
    epoch = htdp.ObservationEpoch(datetime.date(2026, 10, 20))
    forward = htdp.to_nad83(43.82, -84.77, 200.0, htdp.WGS84_G2296, epoch)
    assert forward.helmert_epoch == epoch
    assert forward.velocity_clock_minutes == -8_835_840
    assert forward.velocity_clock_years == pytest.approx(-6136 / 365.25, abs=1e-12)
    assert forward.velocity is not None
    reverse = htdp.from_nad83(43.82, -84.77, 200.0, htdp.WGS84_G2296, epoch)
    assert reverse.helmert_epoch == htdp.NAD83_2011_EPOCH
    assert reverse.velocity_clock_minutes == 8_835_840
    assert (reverse.source_frame, reverse.target_frame) == (htdp.NAD83_2011, htdp.WGS84_G2296)


def test_the_same_day_is_the_helmert_and_no_velocity():
    # htdp.f:3245 and 3276-3283: min1 == min2, so no PREDV and no NEWCOR.
    epoch = htdp.ObservationEpoch(datetime.date(2010, 1, 1))
    result = htdp.to_nad83(43.82, -84.77, 200.0, htdp.ITRF2020, epoch)
    assert result.velocity is None
    assert result.velocity_clock_minutes == 0


def test_the_reported_velocity_is_the_grid_node_in_the_output_frame():
    """Reverse to WGS84(G1762) at a grid node: the velocity is the node's own.

    Clare's neighbour P077, 44.0 N 85.0 W, is grid node I = (275 - 250)/0.5 + 1
    = 51, J = (44 - 24)/0.5 + 1 = 41: initvl.f:45678,
    ``DATA B(139639), ... /    0.30, -16.18,   0.00 /``. WGS84(G1762) is
    ITRF2008 itself (iopt 15), the grid's own frame, so the velocity HTDP
    applies there is the grid's, carried 15 -> 1 by PREDV and 1 -> 15 by
    TRFPOS, at two Cartesian positions a few metres apart: an identity to far
    below 1e-4 mm/yr. The lookup lands a few metres off the node, where the
    neighbouring nodes' weight is ~1e-4 and they differ by ~0.2 mm/yr: also
    below 1e-4. Single-precision literals: 0.30 -> 0.30000001192..., -16.18 ->
    -16.18000030517578.
    """
    result = htdp.from_nad83(
        44.0, -85.0, 0.0, htdp.WGS84_G1762, htdp.ObservationEpoch(datetime.date(2020, 1, 1))
    )
    assert result.velocity is not None
    assert result.velocity.north_mm_per_yr == pytest.approx(0.30000001192092896, abs=1e-4)
    assert result.velocity.east_mm_per_yr == pytest.approx(-16.18000030517578, abs=1e-4)
    assert result.velocity.up_mm_per_yr == pytest.approx(0.0, abs=1e-4)


# --------------------------------------------------------------------------
# (e) Refusals, each with what it says.
# --------------------------------------------------------------------------

EPOCH_2020 = htdp.ObservationEpoch(datetime.date(2020, 1, 1))


@pytest.mark.parametrize("call", ["to_nad83", "from_nad83"])
def test_north_of_region_6_is_refused_never_extrapolated(call):
    # W0's beyond-box probe B002, 50.1 N 88.0 W: its ITRF2008 lookup is north
    # of region 6's 50.0 N edge (initbd.f:39-40), where HTDP leaves the grid
    # for a plate model this program does not carry.
    with pytest.raises(htdp.HtdpVelocityGridError) as raised:
        getattr(htdp, call)(50.1, -88.0, 0.0, htdp.WGS84_G2296, EPOCH_2020)
    message = str(raised.value)
    assert "50.100000" in message and "-88.000000" in message
    assert "50.0 N" in message and "never extrapolates" in message


def test_the_50_north_probe_is_refused_where_its_lookup_crosses_the_edge():
    # B001, 50.0 N in NAD 83: carried to G2296 it is ~1 m further north, then
    # read as NAD 83 and mapped to ITRF2008 by PREDV - another ~1 m north - so
    # the lookup is past 50.0 N and refused. Forward from G2296 at 50.0 N the
    # NAD 83 output is ~1 m SOUTH, the lookup lands in the top row of cells,
    # and HTDP's own record is reproduced (49.9999910309, W0 capture).
    with pytest.raises(htdp.HtdpVelocityGridError):
        htdp.from_nad83(50.0, -88.0, 0.0, htdp.WGS84_G2296, EPOCH_2020)
    forward = htdp.to_nad83(50.0, -88.0, 0.0, htdp.WGS84_G2296, EPOCH_2020)
    assert htdp_print(forward)[0] == "49.9999910309"


@pytest.mark.parametrize(
    "lat,lon,why",
    [
        # 93.0 W is 267.0 E: I = int((267 - 250)/0.5) + 1 = 35 < 37.
        (44.0, -93.0, "west of the window"),
        # 80.0 W is 280.0 E: I = int(30/0.5) + 1 = 61, and I + 1 > 60.
        (44.0, -80.0, "east of the window"),
        # 40.0 N: J = int(16/0.5) + 1 = 33 < 34.
        (40.0, -85.0, "south of the window"),
        # A positive-west longitude typed as this program's negative-west one:
        # 85.0 E, the other side of the world.
        (44.0, 85.0, "longitude sign"),
    ],
)
def test_outside_the_transcribed_window_is_refused(lat, lon, why):
    with pytest.raises(htdp.HtdpVelocityGridError) as raised:
        htdp.to_nad83(lat, lon, 0.0, htdp.ITRF2020, EPOCH_2020)
    message = str(raised.value)
    assert f"{lat:.6f}" in message and f"{lon:.6f}" in message, why
    assert "40.5 N to 50.0 N" in message and "92.0 W to 80.5 W" in message, why
    assert "negative west" in message, why
    assert "ITRF2020" in message, why


def test_the_window_refuses_on_the_same_day_too():
    # HTDP does no velocity lookup on the same day (htdp.f:3276-3283); this
    # program refuses the same positions anyway, so acceptance never depends
    # on the date.
    same_day = htdp.ObservationEpoch(datetime.date(2010, 1, 1))
    with pytest.raises(htdp.HtdpVelocityGridError):
        htdp.to_nad83(44.0, -93.0, 0.0, htdp.WGS84_G2139, same_day)


# --------------------------------------------------------------------------
# The window's own edges (interim gate 1 of the WGS 84 build, finding L3).
#
# The window, from htdp_data: nodes I 37-60 and J 34-53 transcribed. GRDVEC
# reads cell (i, j) from nodes i, i + 1 and j, j + 1 (htdp.f:1685-1692), so the
# accepted cells are i 37-59 and j 34-52. GRDWEI's index is
# i = int((posx - 250) / 0.5) + 1 and j = int((posy - 24) / 0.5) + 1
# (htdp.f:1610-1611), so cell i spans posx [250 + (i - 1) 0.5, 250 + i 0.5):
#
#   accepted  268.0 <= posx < 279.5  (92.0 W to 80.5 W)
#             40.5  <= posy < 50.0
#   and, separately, region 6's north edge: rlat < 50.0 N in radians as
#   GETBDY converts it (htdp.f:271, initbd.f:39-40).
#
# The window's north row and region 6's edge coincide at the double - at the
# edge's own radian value posy is exactly 50.0, one ulp below it 49.99...99 -
# so through a lookup position each check MASKS the other (the reviewer's S16
# and S17). They are therefore pinned apart: the cell rule on its own
# function, ``_cell_is_in_window``, and the region edge by the refusal it
# alone writes ("the northern edge of HTDP's velocity region 6").
# --------------------------------------------------------------------------

WINDOW_REFUSAL = "outside the part of HTDP's velocity grid this program carries"
REGION_REFUSAL = "the northern edge of HTDP's velocity region 6"


@pytest.mark.parametrize(
    "i,j,accepted,edge",
    [
        (37, 34, True, "south-west cell, both lowest accepted indices"),
        (59, 52, True, "north-east cell, both highest accepted indices"),
        (37, 52, True, "north-west cell"),
        (59, 34, True, "south-east cell"),
        (36, 40, False, "west: node 36 is not transcribed"),
        (60, 40, False, "east: cell 60 needs node 61 (the reviewer's S16b)"),
        (40, 33, False, "south: node 33 is not transcribed"),
        (40, 53, False, "north row: cell 53 needs node 54 (the reviewer's S16)"),
    ],
)
def test_the_window_accepts_exactly_the_cells_whose_four_nodes_are_transcribed(
    i, j, accepted, edge
):
    assert htdp._cell_is_in_window(i, j) is accepted, edge
    corners = {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)}
    assert (corners <= set(htdp_data.GRID6_WINDOW)) is accepted, edge


def _grdwei_posx(rlon: float) -> float:
    # htdp.f:1603, POSX = (TWOPI - YLON) * 180.D0 / PI: east longitude, degrees.
    return (htdp_data.TWOPI - rlon) * 180.0 / htdp_data.PI


def _grdwei_posy(rlat: float) -> float:
    # htdp.f:1604, POSY = YLAT * 180.D0 / PI.
    return rlat * 180.0 / htdp_data.PI


def _adjacent_doubles_across(f, target: float, guess: float) -> tuple[float, float]:
    """Adjacent doubles (lo, hi) about ``guess`` with f(lo) < target <= f(hi); f increasing."""
    lo, hi = guess - 1e-9, guess + 1e-9
    assert f(lo) < target <= f(hi)
    while math.nextafter(lo, hi) != hi:
        mid = lo + (hi - lo) / 2.0
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return lo, hi


def _cell_or_refusal(rlat: float, rlon: float):
    try:
        return htdp._window_cell(rlat, rlon, htdp.WGS84_G2296, 44.0, -85.0)
    except htdp.HtdpVelocityGridError as refusal:
        return str(refusal)


def _east_edge_lookup(east_deg: float, rlat: float):
    """The two lookup longitudes either side of ``east_deg``, as radians WEST."""
    # rlon as a function of increasing east longitude decreases, so search in
    # -rlon, where posx increases.
    lo, hi = _adjacent_doubles_across(
        lambda minus_rlon: _grdwei_posx(-minus_rlon),
        east_deg,
        -(htdp_data.TWOPI - east_deg * htdp_data.PI / 180.0),
    )
    return rlat, -lo, -hi  # posx below the edge at -lo, at or above it at -hi


# The other coordinate of each edge probe sits mid-cell, well away from any
# index boundary: 44.25 N is row j = int(20.25 / 0.5) + 1 = 41, and 275.25 E
# (84.75 W) column i = int(25.25 / 0.5) + 1 = 51.
MID_LAT_RAD = 44.25 * 3600.0 / htdp_data.RHOSEC
MID_LON_RAD = htdp_data.TWOPI - 275.25 * htdp_data.PI / 180.0


def test_east_edge_last_accepted_and_first_refused_lookup():
    # posx just below 279.5 is cell i = 59 (nodes 59 and 60): accepted. posx at
    # or above 279.5 is cell 60, which needs node 61: refused by the window.
    rlat, below, at_or_above = _east_edge_lookup(279.5, MID_LAT_RAD)
    assert _grdwei_posx(below) < 279.5 <= _grdwei_posx(at_or_above)
    accepted = _cell_or_refusal(rlat, below)
    assert accepted[:2] == (59, 41), accepted
    refused = _cell_or_refusal(rlat, at_or_above)
    assert isinstance(refused, str) and WINDOW_REFUSAL in refused, refused
    assert REGION_REFUSAL not in refused


def test_west_edge_last_accepted_and_first_refused_lookup():
    # posx at or above 268.0 is cell i = 37: accepted. Below it, cell 36, whose
    # node 36 is not transcribed: refused by the window.
    rlat, below, at_or_above = _east_edge_lookup(268.0, MID_LAT_RAD)
    assert _grdwei_posx(below) < 268.0 <= _grdwei_posx(at_or_above)
    accepted = _cell_or_refusal(rlat, at_or_above)
    assert accepted[:2] == (37, 41), accepted
    refused = _cell_or_refusal(rlat, below)
    assert isinstance(refused, str) and WINDOW_REFUSAL in refused, refused


def _north_lookups(north_deg: float):
    lo, hi = _adjacent_doubles_across(
        _grdwei_posy, north_deg, north_deg * 3600.0 / htdp_data.RHOSEC
    )
    return lo, hi  # posy below north_deg at lo, at or above it at hi


def test_south_edge_last_accepted_and_first_refused_lookup():
    # posy at or above 40.5 is row j = 34: accepted. Below it, row 33: refused.
    below, at_or_above = _north_lookups(40.5)
    assert _grdwei_posy(below) < 40.5 <= _grdwei_posy(at_or_above)
    accepted = _cell_or_refusal(at_or_above, MID_LON_RAD)
    assert accepted[:2] == (51, 34), accepted
    refused = _cell_or_refusal(below, MID_LON_RAD)
    assert isinstance(refused, str) and WINDOW_REFUSAL in refused, refused


def test_north_edge_last_accepted_lookup_and_the_region_edge_refusal():
    # posy just below 50.0 is row j = 52 (nodes 52 and 53): accepted, and its
    # rlat is below region 6's edge. At posy 50.0 - the edge's own radian value
    # - both checks refuse; the refusal must be the REGION's, which this check
    # alone writes. With the region check removed (S17) the window's north row
    # still refuses, but with the window's words.
    below, at_or_above = _north_lookups(50.0)
    assert _grdwei_posy(below) < 50.0 <= _grdwei_posy(at_or_above)
    assert at_or_above == htdp._REGION6_NORTH_EDGE_RAD
    accepted = _cell_or_refusal(below, MID_LON_RAD)
    assert accepted[:2] == (51, 52), accepted
    refused = _cell_or_refusal(at_or_above, MID_LON_RAD)
    assert isinstance(refused, str) and REGION_REFUSAL in refused, refused


@pytest.mark.parametrize("call", ["to_nad83", "from_nad83"])
def test_north_of_region_6_is_refused_by_the_region_edge_by_name(call):
    # 50.1 N (W0's B002): lookup rows past the window AND past region 6. The
    # refusal is the region's - it names the edge and the plate model HTDP
    # goes to beyond it - not the window's generic one (S17's signature).
    with pytest.raises(htdp.HtdpVelocityGridError) as raised:
        getattr(htdp, call)(50.1, -88.0, 0.0, htdp.WGS84_G2296, EPOCH_2020)
    assert REGION_REFUSAL in str(raised.value)
    assert WINDOW_REFUSAL not in str(raised.value)


def test_the_reviewers_east_edge_point_is_refused_by_the_window():
    # The reviewer's S16b input: 44.0 N, 80.4 W in WGS84(G2296) on 2020-01-01.
    # Its lookup is about 279.6 E, cell i = int(29.6 / 0.5) + 1 = 60, which
    # needs node 61: refused by the window check, in the window's words.
    with pytest.raises(htdp.HtdpVelocityGridError) as raised:
        htdp.to_nad83(44.0, -80.4, 0.0, htdp.WGS84_G2296, EPOCH_2020)
    message = str(raised.value)
    assert WINDOW_REFUSAL in message, message
    assert "not part of the transcription" not in message


def test_an_untranscribed_node_is_a_refusal_never_a_key_error():
    """L3's root: a wrong window check must still fail CLOSED, in this family.

    Node (61, 40) is one column east of the transcription (I 37-60).
    """
    with pytest.raises(htdp.HtdpVelocityGridError) as raised:
        htdp._window_node(61, 40)
    assert "I = 61, J = 40" in str(raised.value)
    assert htdp._window_node(60, 53) == htdp_data.GRID6_WINDOW[(60, 53)]


def test_an_off_by_one_window_still_fails_closed_through_the_pipeline(monkeypatch):
    """The reviewer's S16b, simulated wholesale: a window that accepts everything.

    With the cell check made to accept every cell, 44.0 N 80.4 W reaches cell
    60 and its node 61. Before the gate-1 fix that escaped as ``KeyError
    (61, 40)``, through every ``except HtdpRefusal``; it must be the module's
    own refusal, naming the node.
    """
    monkeypatch.setattr(htdp, "_cell_is_in_window", lambda i, j: True)
    with pytest.raises(htdp.HtdpVelocityGridError) as raised:
        htdp.to_nad83(44.0, -80.4, 0.0, htdp.WGS84_G2296, EPOCH_2020)
    assert "I = 61" in str(raised.value)


EDGE_RECORDS = [
    (run.run_id, record.name)
    for run in NEAR_TIE_RUNS
    if run.purpose == "window_edge"
    for record in run.records
]


@pytest.mark.parametrize("run_id,name", EDGE_RECORDS, ids=[f"{r}-{n}" for r, n in EDGE_RECORDS])
def test_at_each_window_edge_the_inside_input_is_htdp_and_the_outside_one_refused(run_id, name):
    """The edges through the public path, at inputs frozen from the binary.

    Two adjacent input doubles per edge and direction, whose ITRF2008 lookups
    (experiment.py's, the fixture's ``note``) fall either side of it. HTDP
    computes both - its grid 6 runs 250-294 E, 24-50 N; MCX must print HTDP's
    numbers for the inside one and refuse the outside one, with the window's
    words on the east, west and south and the region edge's on the north.
    """
    run = NEAR_TIE_BY_ID[run_id]
    (record,) = [r for r in run.records if r.name == name]
    _, edge, side = record.role.split()
    lookup = float(record.note)
    target = {"E": 279.5, "W": 268.0, "S": 40.5, "N": 50.0}[edge]
    inside_is_below = edge in "EN"
    assert (lookup < target) is (inside_is_below is (side == "inside")), record
    if side == "inside":
        assert htdp_print(run_record(run, record.lat_in, record.lonw_in, record.h_in)) == (
            record.lat_out, record.lonw_out, record.h_out
        )
        return
    with pytest.raises(htdp.HtdpVelocityGridError) as raised:
        run_record(run, record.lat_in, record.lonw_in, record.h_in)
    expected = REGION_REFUSAL if edge == "N" else WINDOW_REFUSAL
    assert expected in str(raised.value), str(raised.value)


def test_every_edge_and_direction_has_its_pair_of_edge_records():
    edges = {
        (run.frame_in_menu, run.frame_out_menu, record.role)
        for run in NEAR_TIE_RUNS
        if run.purpose == "window_edge"
        for record in run.records
    }
    assert edges == {
        (m1, m2, f"edge {edge} {side}")
        for m1, m2 in ((12, 1), (1, 25))
        for edge in "EWSN"
        for side in ("inside", "outside")
    }


def test_frmxyz_non_convergence_is_refused_where_htdp_would_stop_666():
    # A height of -6,300 km puts the point ~70 km from the earth's centre,
    # where FRMXYZ's iteration on tan(lat) (htdp.f:942-946) cannot settle in
    # eleven passes; HTDP stops (STOP 666, htdp.f:3246).
    with pytest.raises(htdp.HtdpConvergenceError) as raised:
        htdp.to_nad83(44.0, -85.0, -6_300_000.0, htdp.WGS84_G2296, EPOCH_2020)
    message = str(raised.value)
    assert "STOP 666" in message and "44.0" in message and "-85.0" in message


def test_frmxyz_on_the_polar_axis_is_refused():
    with pytest.raises(htdp.HtdpConvergenceError):
        htdp._frmxyz(0.0, 0.0, 6_356_752.0, htdp.GRS80)


@pytest.mark.parametrize(
    "frame",
    [
        # ITRF2008 is in HTDP's MENU1 (24, iopt 15) but not offered.
        htdp.HtdpFrame(menu=24, iopt=15, htdp_name="ITRF2008 or IGS08/IGb08 "),
        # The likeliest W2 slip: this program's own frame record, not HTDP's.
        frames.WGS84,
        frames.NAD83_2011,
        "WGS84(G2296)",
        12,
    ],
)
def test_a_frame_not_in_the_table_is_refused(frame):
    with pytest.raises(htdp.HtdpFrameError) as raised:
        htdp.to_nad83(43.82, -84.77, 200.0, frame, EPOCH_2020)
    message = str(raised.value)
    assert "WGS84(G2296)" in message and "ITRF2020" in message  # names what is offered


def test_frame_by_menu_refuses_an_unoffered_menu_number():
    for menu in (8, 9, 24, 0, "12"):
        with pytest.raises(htdp.HtdpFrameError):
            htdp.frame_by_menu(menu)
    assert htdp.frame_by_menu(12) is htdp.WGS84_G2296


def test_the_same_frame_both_ends_is_refused():
    with pytest.raises(htdp.HtdpFrameError) as raised:
        htdp.to_nad83(43.82, -84.77, 200.0, htdp.NAD83_2011, EPOCH_2020)
    assert "both NAD_83(2011/CORS96/2007)" in str(raised.value)


def test_neither_end_nad83_is_refused():
    with pytest.raises(htdp.HtdpFrameError) as raised:
        htdp.transform(43.82, -84.77, 200.0, htdp.WGS84_G2296, htdp.ITRF2020, EPOCH_2020)
    message = str(raised.value)
    assert "one side must be NAD 83(2011)" in message and "D4" in message


@pytest.mark.parametrize(
    "epoch",
    [datetime.date(2020, 1, 1), 2020.0, "2020-01-01", None],
)
def test_an_epoch_that_is_not_an_observation_epoch_is_refused(epoch):
    with pytest.raises(htdp.HtdpEpochError) as raised:
        htdp.to_nad83(43.82, -84.77, 200.0, htdp.WGS84_G2296, epoch)
    assert "ObservationEpoch" in str(raised.value)


@pytest.mark.parametrize(
    "value",
    [datetime.datetime(2020, 1, 1, 12, 0), "2020-01-01", 2020.5, None],
)
def test_an_observation_epoch_is_a_calendar_date_and_nothing_else(value):
    with pytest.raises(htdp.HtdpEpochError) as raised:
        htdp.ObservationEpoch(value)
    assert "calendar date" in str(raised.value)


def test_htdps_own_year_limit_holds():
    # htdp.f:7891: IF(IYEAR .le. 1906) refuses - including 1906 itself.
    with pytest.raises(htdp.HtdpEpochError) as raised:
        htdp.ObservationEpoch(datetime.date(1906, 12, 31))
    assert "1907" in str(raised.value)
    assert htdp.ObservationEpoch(datetime.date(1907, 1, 1)).decimal_year == 1907.0


def test_a_date_beyond_htdps_integer_clock_is_refused():
    # MINS = MJD * 1440 in a 4-byte INTEGER (htdp.f:7920) tops out at
    # 2**31 - 1 = 2,147,483,647, i.e. MJD 1,491,308, about the year 5941.
    # 9999-12-31 is MJD ~2.97 million: refused. 5000-01-01 is MJD ~1.15
    # million: accepted.
    with pytest.raises(htdp.HtdpEpochError):
        htdp.ObservationEpoch(datetime.date(9999, 12, 31))
    assert htdp.ObservationEpoch(datetime.date(5000, 1, 1)).minutes < 2**31 - 1


@pytest.mark.parametrize(
    "lat,lon,h",
    [
        (math.nan, -84.77, 200.0),
        (43.82, math.inf, 200.0),
        (43.82, -84.77, math.nan),
        (True, -84.77, 200.0),
        ("43.82", -84.77, 200.0),
        (91.0, -84.77, 200.0),
        (43.82, -361.0, 200.0),
    ],
)
def test_a_coordinate_that_is_not_a_number_on_the_earth_is_refused(lat, lon, h):
    with pytest.raises(htdp.HtdpInputError):
        htdp.to_nad83(lat, lon, h, htdp.WGS84_G2296, EPOCH_2020)


def test_every_refusal_is_one_family():
    for cls in (
        htdp.HtdpFrameError,
        htdp.HtdpEpochError,
        htdp.HtdpInputError,
        htdp.HtdpVelocityGridError,
        htdp.HtdpConvergenceError,
    ):
        assert issubclass(cls, htdp.HtdpRefusal)


def test_the_lookup_position_uses_the_iers_set_as_xto08_does():
    """A structural pin, because no printed record can show this choice.

    XTO08 maps a WGS84(G2139)/(G2296)/ITRF lookup position to ITRF2008 with
    the IERS block (htdp.f:2740-2742). Composed frame -> ITRF94 -> ITRF2008,
    the IGS and IERS blocks describe the SAME frame-to-frame transformation:
    their static offsets from ITRF94 differ by centimetres, but those cancel
    in the composite, which agrees to about 3e-9 m (measured at W1). So the
    choice moves the grid lookup by nanometres and no anchor can see it - the
    W1 falsification seed that swapped the block went uncaught by every anchor.
    What CAN be held is the code path: the lookup must be the IERS composite
    bit for bit, and (on these positions) not the IGS one.
    """
    differs = 0
    for iopt in (16, 17):
        for lat in (41.5, 43.82, 45.0, 47.12):
            xyz = htdp._toxyz(math.radians(lat), math.radians(-84.77), 200.0, htdp.GRS80)
            got = htdp._xto08(xyz, 2020.0, iopt, htdp.GRS80)
            for table, name in ((htdp_data.IERS_CONVENTION, "iers"), (htdp_data.IGS_CONVENTION, "igs")):
                x2 = htdp._frit94(table, htdp._toit94(table, xyz, 2020.0, iopt), 2020.0, 15)
                rlat, elon, _ = htdp._frmxyz(*x2, htdp.GRS80)
                wlon = -elon + (htdp_data.TWOPI if -elon < 0.0 else 0.0)
                if name == "iers":
                    assert got == (rlat, wlon), (iopt, lat)
                else:
                    differs += got != (rlat, wlon)
    assert differs > 0
