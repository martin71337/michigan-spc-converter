"""The WGS 84 and ITRF frames in the registry, and the guard that kept them unapplied.

Work package W2 of the WGS 84 build (docs/PLAN-wgs84.md section 3.3,
decisions D2-D4; docs/DESIGN.md #70). Three things are pinned here:

1. **The records.** Five new usable frames, each stating whether it is
   plate-fixed or time-dependent and which HTDP frame it is carried as, held
   to HTDP's own record of the ellipsoid and the classification; the bare
   WGS 84 label still declared and not usable; ten HTDP paths, each stating
   its method and nothing of HTDP's parameters.
2. **The refusals, pair by pair.** Every message must be true for the pair it
   is printed for: the #62 facts for NAD83(2011) <-> NATRF2022 only, HTDP's
   silence on NATRF2022 for the global frames against it (D3), the
   not-offered sentence for two global frames (D4), the missing identity for
   one global frame against itself.
3. **The safety guard** - the most important item. The registry returns the
   HTDP records, and nothing in the conversion applies them yet. Without the
   guard a WGS 84 position would be projected, or written, as though it were
   NAD 83: about 1.3 m in Michigan, wearing the right label. So every
   registered non-identity path refuses at ``convert.py``'s call sites and at
   ``job.run``'s settings gate, before the file is read; pinned end to end
   through ``job.run`` with real files, per direction.

   SUPERSEDED at work package W3 (DESIGN.md #70): the conversion now applies
   the HTDP records, so section 4's guard pins have successors on the same
   inputs, pinned as TRANSFORMED against HTDP's printed output; each names the
   W2 pin it replaces.

Every expected value is derived in the comment above it (docs/method/METHOD.md
section 4).
"""

from __future__ import annotations

import dataclasses
import datetime
import math
from pathlib import Path

import pytest

from michspc.fileio import exports
from michspc.job import Direction, JobSettings, LongitudeConvention, VerticalMode, run
from michspc.spc import convert, frames, htdp, htdp_data
from michspc.spc.convert import project_point
from michspc.spc.frames import (
    ALL_FRAMES,
    FRAME_TRANSFORMATIONS,
    ITRF2014,
    ITRF2020,
    NAD83_2011,
    NATRF2022,
    REQUIRED_FRAME_PAIRS,
    WGS84,
    WGS84_G1762,
    WGS84_G2139,
    WGS84_G2296,
    FrameEpochKind,
    FrameMismatchError,
    FrameNotUsableError,
    FrameStatus,
    FrameTransformation,
    FrameTransformationMethod,
    FrameTransformationUnavailableError,
    ReferenceFrame,
    require_frame_path,
)
from michspc.spc.units import METERS
from michspc.spc.vertical import NAVD88, NGVD29, HeightKind
from michspc.spc.zones import MI_SOUTH

REPO = Path(__file__).resolve().parents[1]

# The five, in the owner's order (plan section 1), and the HTDP record each is
# carried as - htdp.py's own, from MENU1 (htdp.f:4704-4711, 4749-4753).
TIME_DEPENDENT = (
    (WGS84_G1762, htdp.WGS84_G1762),
    (WGS84_G2139, htdp.WGS84_G2139),
    (WGS84_G2296, htdp.WGS84_G2296),
    (ITRF2014, htdp.ITRF2014),
    (ITRF2020, htdp.ITRF2020),
)
FIVE = tuple(frame for frame, _ in TIME_DEPENDENT)
FIVE_IDS = [frame.code for frame in FIVE]

# Every ordered pair of two DIFFERENT global frames: 5 x 4 = 20 (plan D4).
GLOBAL_PAIRS = [(a, b) for a in FIVE for b in FIVE if a is not b]
GLOBAL_PAIR_IDS = [f"{a.code}->{b.code}" for a, b in GLOBAL_PAIRS]

# The ten HTDP pairs, both directions (plan section 3.3).
HTDP_PAIRS = [(f, NAD83_2011) for f in FIVE] + [(NAD83_2011, f) for f in FIVE]
HTDP_PAIR_IDS = [f"{a.code}->{b.code}" for a, b in HTDP_PAIRS]


# ==========================================================================
# 1. The records.
# ==========================================================================


@pytest.mark.parametrize(("frame", "carried"), TIME_DEPENDENT, ids=FIVE_IDS)
def test_each_new_frame_is_usable_time_dependent_and_carried_by_htdp(frame, carried):
    """Usable, time-dependent, no reference epoch, carried as HTDP's own record.

    Expected from the plan (section 3.3): all five are USABLE and
    time-dependent, a time-dependent frame has no reference epoch of its own
    (its epoch is the observation's), and each is the htdp.py record of the
    same MENU1 entry.
    """
    assert frame.is_usable
    assert frame.status is FrameStatus.USABLE
    assert frame.epoch_kind is FrameEpochKind.TIME_DEPENDENT
    assert frame.is_time_dependent
    assert frame.reference_epoch is None
    assert frame.htdp_frame is carried
    assert frames.frame_by_code(frame.code) is frame


def test_the_codes_are_exactly_the_plans():
    """The strings a job record and a saved job will carry; typed from the plan."""
    assert [frame.code for frame in FIVE] == [
        "WGS84(G1762)",
        "WGS84(G2139)",
        "WGS84(G2296)",
        "ITRF2014",
        "ITRF2020",
    ]


@pytest.mark.parametrize(("frame", "carried"), TIME_DEPENDENT, ids=FIVE_IDS)
def test_the_ellipsoid_follows_the_frames_name_as_htdp_chooses_it(frame, carried):
    """WGS84(...) on the WGS 84 ellipsoid, ITRF on GRS 80 - HTDP's rule.

    htdp.f:3221-3224 loads 'WGS84' when the frame name's first five characters
    are 'WGS84' and 'GRS80' otherwise. So the three WGS84(...) frames state
    "WGS 84" and the two ITRF frames "GRS 80", and each agrees with what
    ``htdp.HtdpFrame.ellipsoid`` derives from the name.
    """
    expected = "WGS 84" if frame.code.startswith("WGS84") else "GRS 80"
    assert frame.ellipsoid_name == expected
    assert carried.ellipsoid is (
        htdp.WGS84_ELLIPSOID if expected == "WGS 84" else htdp.GRS80
    )


def test_the_plate_fixed_frames_state_their_reference_epochs():
    """NAD83(2011) at 2010.0 (TR NOS NGS 62 Table 1; plan D1), NATRF2022 at 2020.0.

    NAD83(2011)'s figure is held to ``htdp.NAD83_2011_EPOCH``, the epoch the
    arithmetic uses: 2010-01-01 through HTDP's calendar arithmetic is
    2010 + 0/365 = 2010.0 exactly. NATRF2022 is carried by no HTDP frame
    (it is in no MENU1 line), so its HTDP record is None.
    """
    assert NAD83_2011.epoch_kind is FrameEpochKind.PLATE_FIXED
    assert NAD83_2011.reference_epoch == 2010.0
    assert NAD83_2011.reference_epoch == htdp.NAD83_2011_EPOCH.decimal_year
    assert NAD83_2011.htdp_frame is htdp.NAD83_2011

    assert NATRF2022.epoch_kind is FrameEpochKind.PLATE_FIXED
    assert NATRF2022.reference_epoch == 2020.0
    assert NATRF2022.htdp_frame is None


def test_natrf2022s_reference_epoch_is_in_the_frozen_definitional_document():
    """The 2020.0 is NGS's, not typed from memory.

    The passage extract of the frozen TR NOS NGS 62 (its PDF is SHA-256 cited
    on the NATRF2022 record) carries section 6's sentence "The epoch t0 will
    be 2020.00", and Table 1's "epoch 2010.00" for NAD 83(2011).
    """
    passages = (
        REPO / "review/nsrs-h3-recon/ifdm/raw/pubs/TR62_passages.txt"
    ).read_text(encoding="utf-8")
    assert "The epoch t0 will be 2020.00" in passages
    assert "epoch 2010.00" in passages


def test_the_bare_wgs84_label_stays_declared_and_not_usable():
    """Plan D2: the bare label is refused, and carries no HTDP frame.

    It is time-dependent - every WGS 84 realization is - and names no
    realization HTDP could be asked about.
    """
    assert WGS84.code == "WGS84"
    assert WGS84.status is FrameStatus.DECLARED_NOT_USABLE
    assert not WGS84.is_usable
    assert WGS84.is_time_dependent
    assert WGS84.reference_epoch is None
    assert WGS84.htdp_frame is None


def test_no_frame_citation_still_says_there_is_no_data_for_wgs84():
    """#70 supersedes #58's "this program has no data with which to compute one".

    True of the data in hand when written, false since htdp.py. No record may
    keep saying it.
    """
    for frame in ALL_FRAMES:
        assert "no data" not in frame.citation, frame.code
    source = (REPO / "michspc/spc/frames.py").read_text(encoding="utf-8")
    assert "has no data" not in source


@pytest.mark.parametrize(
    ("frame", "menu_lines", "parameters", "implemented"),
    [
        (WGS84_G1762, "htdp.f:4704-4705", "ITRF2008", "2013-10-16"),
        (WGS84_G2139, "htdp.f:4707-4708", "ITRF2014", "2021-01-03"),
        (WGS84_G2296, "htdp.f:4710-4711", "ITRF2020", "2024-01-07"),
        (ITRF2014, "htdp.f:4749-4750", None, None),
        (ITRF2020, "htdp.f:4752-4753", None, None),
    ],
    ids=FIVE_IDS,
)
def test_each_citation_names_htdp_its_menu_lines_and_for_wgs84_ngas_date(
    frame, menu_lines, parameters, implemented
):
    """Who says so, and where: HTDP v3.6.0 at its commit, the MENU1 lines.

    The menu lines are htdp.py's own citations of the same records; the
    parameters are MENU1's text ("WGS84(G1762)  ITRF2008=IGS08=IGb08 used",
    htdp.f:4767-4769); the implementation dates are NGA's (plan D9).
    """
    citation = frame.citation
    assert htdp_data.HTDP_COMMIT in citation
    assert f"v{htdp_data.HTDP_VERSION}" in citation
    assert menu_lines in citation
    assert "htdp.f:3221-3224" in citation  # the ellipsoid rule
    if parameters is not None:
        assert f"{parameters}=" in citation
        assert f"Implemented by NGA on {implemented}" in citation
        assert "IGSMAIL-8444" in citation


# The ReferenceFrame consistency checks, each with the record it refuses.


def test_a_wgs84_realization_stated_on_grs80_will_not_construct():
    """The one-authoritative-representation check: HTDP's ellipsoid wins.

    WGS84(G2296) is on the WGS 84 ellipsoid by its name (htdp.f:3224), so a
    record typing "GRS 80" for it disagrees with the arithmetic and refuses -
    and ITRF2020 typed "WGS 84" refuses the other way.
    """
    with pytest.raises(ValueError, match="htdp.f:3221-3224"):
        dataclasses.replace(WGS84_G2296, ellipsoid_name="GRS 80")
    with pytest.raises(ValueError, match="ellipsoid"):
        dataclasses.replace(ITRF2020, ellipsoid_name="WGS 84")


def test_a_frame_whose_epoch_kind_disagrees_with_htdp_will_not_construct():
    """htdp.TIME_DEPENDENT_FRAMES decides; the record must agree with it."""
    with pytest.raises(ValueError, match="time-dependent"):
        dataclasses.replace(
            WGS84_G2296,
            epoch_kind=FrameEpochKind.PLATE_FIXED,
            reference_epoch=2010.0,
        )
    with pytest.raises(ValueError, match="plate-fixed"):
        dataclasses.replace(
            NAD83_2011,
            epoch_kind=FrameEpochKind.TIME_DEPENDENT,
            reference_epoch=None,
        )


def test_the_epoch_fields_must_agree_with_each_other():
    """Plate-fixed needs a reference epoch; time-dependent must state none."""
    with pytest.raises(ValueError, match="reference_epoch None"):
        dataclasses.replace(NATRF2022, reference_epoch=None)
    with pytest.raises(ValueError, match="reference_epoch True"):
        dataclasses.replace(NATRF2022, reference_epoch=True)
    with pytest.raises(ValueError, match="reference_epoch nan"):
        dataclasses.replace(NATRF2022, reference_epoch=float("nan"))
    with pytest.raises(ValueError, match="Pass reference_epoch=None"):
        dataclasses.replace(ITRF2014, reference_epoch=2014.0)
    with pytest.raises(TypeError, match="FrameEpochKind"):
        dataclasses.replace(NATRF2022, epoch_kind="plate-fixed")


def test_nad83s_reference_epoch_must_be_the_one_htdp_computes_with():
    """2010.0 is stated twice - record and htdp.NAD83_2011_EPOCH - so it is checked."""
    with pytest.raises(ValueError, match="one epoch"):
        dataclasses.replace(NAD83_2011, reference_epoch=2020.0)


def test_a_frame_htdp_does_not_carry_here_will_not_construct():
    """Only htdp.py's own six records; ITRF2008 is in MENU1 but not offered."""
    itrf2008 = htdp.HtdpFrame(menu=24, iopt=15, htdp_name="ITRF2008 or IGS08/IGb08 ")
    with pytest.raises(TypeError, match="not one of the frames"):
        dataclasses.replace(ITRF2014, htdp_frame=itrf2008)
    with pytest.raises(TypeError, match="not one of the frames"):
        dataclasses.replace(ITRF2014, htdp_frame="ITRF2014")


# ==========================================================================
# 2. The transformation records.
# ==========================================================================


@pytest.mark.parametrize(("source", "target"), HTDP_PAIRS, ids=HTDP_PAIR_IDS)
def test_each_htdp_pair_is_registered_required_and_returned(source, target):
    """Ten records, each returned by the gate and each required by #32.

    ``require_frame_path`` returns the record rather than refusing (plan 3.3);
    it states HTDP v3.6.0 as its method; and the pair is in the append-only
    REQUIRED_FRAME_PAIRS, so it cannot be dropped silently.
    """
    path = require_frame_path(source, target)
    assert path is FRAME_TRANSFORMATIONS[(source, target)]
    assert not path.is_identity
    assert path.method is FrameTransformationMethod.HTDP_V3_6_0
    assert path.applied_method is FrameTransformationMethod.HTDP_V3_6_0
    assert (source.code, target.code) in REQUIRED_FRAME_PAIRS
    assert htdp_data.HTDP_COMMIT in path.citation


def test_required_pairs_were_appended_not_replaced():
    """#32: the two identities are still required; ten appended beside them."""
    assert ("NAD83(2011)", "NAD83(2011)") in REQUIRED_FRAME_PAIRS
    assert ("NATRF2022", "NATRF2022") in REQUIRED_FRAME_PAIRS
    # 2 identities + 5 frames x 2 directions = 12.
    assert len(REQUIRED_FRAME_PAIRS) == 12


def test_the_import_check_catches_a_lost_htdp_pair(monkeypatch):
    """Seeded: the registry loses WGS84(G2296) -> NAD83(2011); the check names it."""
    doctored = dict(frames._TRANSFORMATIONS_BY_CODE)
    del doctored[("WGS84(G2296)", "NAD83(2011)")]
    monkeypatch.setattr(frames, "_TRANSFORMATIONS_BY_CODE", doctored)
    with pytest.raises(FrameMismatchError) as caught:
        frames._check_registry_keeps_every_required_pair()
    assert "WGS84(G2296) -> NAD83(2011)" in str(caught.value)
    assert "#32" in str(caught.value)


@pytest.mark.parametrize("frame", (*FIVE, WGS84), ids=[*FIVE_IDS, "WGS84"])
def test_no_time_dependent_frame_has_an_identity(frame):
    """Plan W2 item 5: no identity for the five, none for bare WGS 84.

    W3 routes a vertical-only job on one of the five through its HTDP path to
    NAD83(2011) instead (plan D8, ``convert.pivot_path``), never an identity.
    """
    assert (frame.code, frame.code) not in frames._TRANSFORMATIONS_BY_CODE
    assert (frame, frame) not in FRAME_TRANSFORMATIONS


def test_the_record_carries_no_htdp_parameter():
    """One authoritative representation: htdp_data holds the numbers.

    The record's fields are exactly the two frames, the citation and the
    method - nothing a Helmert set or a velocity grid could be copied into.
    """
    names = [field.name for field in dataclasses.fields(FrameTransformation)]
    assert names == ["source", "target", "citation", "method"]


def test_an_identity_states_no_method():
    """The method of an identity is derived (IDENTITY), never stated."""
    for method in FrameTransformationMethod:
        with pytest.raises(ValueError, match="states no method"):
            FrameTransformation(
                source=NAD83_2011,
                target=NAD83_2011,
                citation="synthetic",
                method=method,
            )
    identity = FRAME_TRANSFORMATIONS[(NAD83_2011, NAD83_2011)]
    assert identity.method is None
    assert identity.applied_method is FrameTransformationMethod.IDENTITY


def test_a_non_identity_record_must_state_a_moving_method():
    """No method, or the identity method, between two frames is a pass-through."""
    for method in (None, FrameTransformationMethod.IDENTITY):
        with pytest.raises(ValueError, match="unchanged while relabelling"):
            FrameTransformation(
                source=WGS84_G2296,
                target=NAD83_2011,
                citation="synthetic",
                method=method,
            )
    with pytest.raises(TypeError, match="FrameTransformationMethod"):
        FrameTransformation(
            source=WGS84_G2296,
            target=NAD83_2011,
            citation="synthetic",
            method="HTDP_V3_6_0",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("source", "target"),
    [
        # Two time-dependent frames: HTDP could, this program does not (D4).
        (WGS84_G1762, WGS84_G2296),
        (ITRF2020, WGS84_G2296),
        # NATRF2022 at either end: HTDP does not carry it (D3).
        (NATRF2022, WGS84_G2296),
        (NAD83_2011, NATRF2022),
        # The bare label: no HTDP frame.
        (WGS84, NAD83_2011),
    ],
)
def test_an_htdp_record_must_be_nad83_against_one_carried_global_frame(
    source, target
):
    with pytest.raises(ValueError, match="exactly one end must be NAD83"):
        FrameTransformation(
            source=source,
            target=target,
            citation="synthetic",
            method=FrameTransformationMethod.HTDP_V3_6_0,
        )


def test_an_htdp_record_needs_a_citation():
    with pytest.raises(ValueError, match="empty citation"):
        FrameTransformation(
            source=WGS84_G2296,
            target=NAD83_2011,
            citation="  ",
            method=FrameTransformationMethod.HTDP_V3_6_0,
        )


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_the_forward_direction_statement_is_htdps_composition(frame):
    """Global -> NAD 83: Helmert at the observation epoch, then NAD 83's velocity.

    htdp.f:3230-3231 evaluates the Helmert at DATE1, the input epoch; the
    velocity is the OUTPUT frame's (htdp.f:3249-3273) - for NAD83(2011), a
    plate-fixed frame, the small intraplate residual (RECON.md section 1.4).
    """
    statement = FRAME_TRANSFORMATIONS[(frame, NAD83_2011)].direction_statement
    assert f"({frame.code}) at the observation epoch" in statement
    assert "(NAD83(2011)) at its reference epoch 2010.0" in statement
    assert "at the input epoch, the observation epoch" in statement
    assert "from the observation epoch to 2010.0" in statement
    assert "the NAD83(2011) velocity, which is the small intraplate" in statement
    assert "full motion" not in statement
    assert htdp_data.HTDP_COMMIT in statement


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_the_reverse_direction_statement_is_htdps_composition(frame):
    """NAD 83 -> global: Helmert at 2010.0, then the global frame's full plate motion."""
    statement = FRAME_TRANSFORMATIONS[(NAD83_2011, frame)].direction_statement
    assert "(NAD83(2011)) at its reference epoch 2010.0" in statement
    assert f"({frame.code}) at the observation epoch" in statement
    assert "at the input epoch, 2010.0" in statement
    assert "from 2010.0 to the observation epoch" in statement
    assert f"the {frame.code} velocity, which includes the full motion" in statement
    assert "intraplate" not in statement


def test_direction_statements_carry_no_caveat():
    """Facts only, the owner's rule (DESIGN.md #50)."""
    for source, target in HTDP_PAIRS:
        statement = FRAME_TRANSFORMATIONS[(source, target)].direction_statement.lower()
        for word in ("caution", "warning", "approximate", "may be", "should"):
            assert word not in statement, (source.code, target.code, word)


# ==========================================================================
# 3. The refusals, each true for its own pair.
# ==========================================================================


@pytest.mark.parametrize("other", (NAD83_2011, NATRF2022, *FIVE))
def test_the_bare_label_is_refused_first_by_name_against_every_frame(other):
    """Plan D2: FrameNotUsableError, never a missing-path message - even against
    a named realization - and it names the five to choose from."""
    for source, target in ((WGS84, other), (other, WGS84)):
        with pytest.raises(FrameNotUsableError) as caught:
            require_frame_path(source, target)
        message = str(caught.value)
        assert "WHICH realization" in message
        for frame in FIVE:
            assert frame.code in message


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_natrf2022_against_a_global_frame_says_htdp_does_not_carry_it(frame):
    """Plan D3, both directions: HTDP's silence, and the unpublished bridge.

    Distinguishing content pinned both ways: the D3 facts present, the D4
    sentence and the #62 NCAT measurement (true only of NAD83 <-> NATRF2022)
    absent.
    """
    for source, target in ((NATRF2022, frame), (frame, NATRF2022)):
        with pytest.raises(FrameTransformationUnavailableError) as caught:
            require_frame_path(source, target)
        message = str(caught.value)
        assert f"carries {frame.code} to and from NAD83(2011)" in message
        assert "does not carry NATRF2022 at all" in message
        assert "NGS has not published one" in message
        assert "decision D3" in message
        assert "decision D4" not in message
        assert "17 cm" not in message


def test_nad83_against_natrf2022_keeps_the_62_facts_and_nothing_of_htdp():
    """The #62 message is unchanged in content, and says nothing of D3 or D4."""
    for source, target in ((NAD83_2011, NATRF2022), (NATRF2022, NAD83_2011)):
        with pytest.raises(FrameTransformationUnavailableError) as caught:
            require_frame_path(source, target)
        message = str(caught.value)
        assert "one to two metres" in message
        assert "17 cm at one of twelve frozen Michigan anchors" in message
        assert "DEFERRED-NATRF2022-BRIDGE.md" in message
        assert "HTDP" not in message
        assert "decision D3" not in message and "decision D4" not in message


@pytest.mark.parametrize(("source", "target"), GLOBAL_PAIRS, ids=GLOBAL_PAIR_IDS)
def test_two_global_frames_are_not_offered_and_the_way_round_is_named(source, target):
    """Plan D4, all twenty ordered pairs: no zone on either; via NAD83(2011)."""
    with pytest.raises(FrameTransformationUnavailableError) as caught:
        require_frame_path(source, target)
    message = str(caught.value)
    assert (
        f"No State Plane zone is defined on {source.code} or on {target.code}"
        in message
    )
    assert "decision D4" in message
    assert (
        f"Convert via NAD83(2011) instead: {source.code} to NAD83(2011), then "
        f"NAD83(2011) to {target.code}." in message
    )
    assert "NATRF2022" not in message
    assert "NGS has not published" not in message


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_a_global_frame_against_itself_refuses_at_the_missing_identity(frame):
    """A vertical-only job's identity lookup (plan W2 item 7), true for it."""
    with pytest.raises(FrameTransformationUnavailableError) as caught:
        require_frame_path(frame, frame)
    message = str(caught.value)
    assert f"Cannot keep a position in {frame.code}" in message
    assert "no identity is registered" in message
    assert "decision D8" in message
    assert "decision D4" not in message and "17 cm" not in message


def test_an_unrecognised_frame_gets_a_message_that_claims_nothing_it_cannot_know():
    """A hand-built frame no registry knows: no NATRF, HTDP or D-number facts."""
    nad27 = ReferenceFrame(
        code="NAD27",
        name="hand-built by this test",
        ellipsoid_name="Clarke 1866",
        citation="synthetic",
        status=FrameStatus.USABLE,
        epoch_kind=FrameEpochKind.PLATE_FIXED,
        reference_epoch=1927.0,
        htdp_frame=None,
    )
    with pytest.raises(FrameTransformationUnavailableError) as caught:
        require_frame_path(nad27, NAD83_2011)
    message = str(caught.value)
    assert "NAD27" in message and "is registered" in message
    for claim in ("17 cm", "HTDP", "decision D", "NGS has not published"):
        assert claim not in message


# ==========================================================================
# 4. The safety guard, and its successor.
#
# SUPERSEDED (DESIGN.md #70, plan W3). Under W2 every registered HTDP path
# REFUSED at ``convert.require_a_connected_path`` and at the job's settings
# gate, because nothing applied one. W3 connects the arithmetic, so each W2
# guard pin below has a successor on the SAME inputs, now pinned as
# TRANSFORMED against HTDP's own printed output (tests/fixtures/
# htdp_w3_anchors.py: interim gate 1's L5 position, 43.0 N 84.5 W h 165 m, in
# every frame, both directions, captured from NGS's binary) - and, beside
# each, the refusal that keeps the guard's purpose: no epoch, no conversion.
# None of the W2 pins was deleted silently; each successor says which it
# replaces. The full W3 suite is tests/test_job_wgs84.py.
# ==========================================================================

from michspc.spc.convert import (  # noqa: E402
    HeightConvention,
    TransformHeight,
    require_an_applicable_path,
)
from michspc.spc.zones import Zone  # noqa: E402
from tests.fixtures.htdp_w3_anchors import (  # noqa: E402
    L5_RECORDS,
    L5_REVERSE_RECORDS,
)

L5_BY_CODE = {record.frame_code: record for record in L5_RECORDS}
L5R_BY_CODE = {record.frame_code: record for record in L5_REVERSE_RECORDS}
L5_DATE = datetime.date(2025, 6, 15)
L5_EPOCH = htdp.ObservationEpoch(L5_DATE)


def test_the_stake_a_pass_through_would_cost_is_a_metre_and_more():
    """Anti-vacuity: the guard is preventing a real, boundary-moving error.

    HTDP's own transformation (htdp.py) of 43.0 N, 84.5 W, h = 0 from
    WGS84(G2296) on 2026-01-01 to NAD83(2011) at 2010.0 moves the position
    about 0.95 m south and 0.88 m east - 1.30 m horizontally, measured by the
    lead's brief and RECON.md section 3 ("about a metre north, a metre west").
    Converted to metres with 111,132 m per degree of latitude and
    111,320 cos(43 deg) per degree of longitude, which is good to well under a
    percent at this size.
    """
    result = htdp.to_nad83(
        43.0,
        -84.5,
        0.0,
        htdp.WGS84_G2296,
        htdp.ObservationEpoch(datetime.date(2026, 1, 1)),
    )
    north = (result.latitude - 43.0) * 111_132.0
    east = (result.longitude + 84.5) * 111_320.0 * math.cos(math.radians(43.0))
    assert 1.2 < math.hypot(north, east) < 1.4


def test_the_applicable_path_point_passes_identities_and_every_htdp_record():
    """SUPERSEDES test_the_guard_passes_identities_and_refuses_every_htdp_record.

    The W2 guard refused all ten HTDP records; its successor
    (``require_an_applicable_path``) passes them, because W3 applies them -
    and still refuses what the guard existed to refuse: a non-identity record
    whose method the pipeline has no arithmetic for, which would otherwise be
    run as though it were an identity. No such record can be CONSTRUCTED
    (``FrameTransformation.__post_init__``), so one is forged past it with
    ``object.__setattr__``: the G2296 record relabelled IDENTITY, still
    joining two different frames.
    """
    for frame in (NAD83_2011, NATRF2022):
        identity = FRAME_TRANSFORMATIONS[(frame, frame)]
        assert require_an_applicable_path(identity) is identity
    for source, target in HTDP_PAIRS:
        record = FRAME_TRANSFORMATIONS[(source, target)]
        assert require_an_applicable_path(record) is record

    forged = dataclasses.replace(FRAME_TRANSFORMATIONS[(WGS84_G2296, NAD83_2011)])
    object.__setattr__(forged, "method", FrameTransformationMethod.IDENTITY)
    assert not forged.is_identity
    with pytest.raises(FrameTransformationUnavailableError) as caught:
        require_an_applicable_path(forged)
    message = str(caught.value)
    assert "has no arithmetic for it" in message
    assert "WGS84(G2296)" in message and "NAD83(2011)" in message
    with pytest.raises(TypeError, match="never treated as an identity"):
        require_an_applicable_path(None)  # type: ignore[arg-type]


def _ellipsoid(value: float) -> TransformHeight:
    return TransformHeight(HeightConvention.ELLIPSOID, value)


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_project_point_transforms_a_global_position_into_an_spcs83_zone(frame):
    """SUPERSEDES test_project_point_refuses_a_global_position_into_an_spcs83_zone.

    The reviewer-style input, 43.0 / -84.5 in a global frame into MI-S, now
    with the date and height HTDP needs: h = 165.000 m on 2025-06-15. The
    pivot must be HTDP's NAD 83 output, at HTDP's printed digit (1e-10 deg,
    1 mm: the W1 acceptance standard) - frozen from the binary, never from
    michspc - and the grid coordinate must be that pivot projected, exactly,
    since project_point projects its own pivot.
    """
    truth = L5_BY_CODE[frame.code]
    conversion = project_point(
        43.0, -84.5, frame, MI_SOUTH, epoch=L5_EPOCH, height=_ellipsoid(165.0)
    )
    assert f"{conversion.latitude:.10f}" == truth.lat_out
    assert f"{-conversion.longitude:.10f}" == truth.lonw_out
    assert f"{conversion.pivot_ellipsoid_height:.3f}" == truth.h_out
    assert conversion.frame is NAD83_2011
    assert conversion.external_position.frame is frame
    assert (conversion.external_position.latitude, conversion.external_position.longitude) == (
        43.0,
        -84.5,
    )
    plain = project_point(conversion.latitude, conversion.longitude, NAD83_2011, MI_SOUTH)
    assert conversion.target_northing == plain.target_northing
    assert conversion.target_easting == plain.target_easting

    # The guard's purpose, kept: no epoch, no projection.
    with pytest.raises(ValueError) as caught:
        project_point(43.0, -84.5, frame, MI_SOUTH, height=_ellipsoid(165.0))
    assert f"observation epoch of the {frame.code} position" in str(caught.value)


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_convert_point_still_refuses_a_zone_pair_across_an_htdp_path(frame):
    """SUPERSEDES test_convert_point_refuses_a_zone_pair_across_an_htdp_path.

    Same inputs: MI-S's own record with its frame replaced. Still REFUSED, in
    both orders - zone to zone never crosses a frame transformation, because
    no State Plane zone is defined on a WGS 84 or ITRF frame (plan D4) - but
    with W3's reason, not W2's "not yet connected".
    """
    on_global = dataclasses.replace(MI_SOUTH, frame=frame)
    for source, target in ((MI_SOUTH, on_global), (on_global, MI_SOUTH)):
        with pytest.raises(FrameTransformationUnavailableError) as caught:
            convert.convert_point(200_000.0, 4_000_000.0, source, target)
        message = str(caught.value)
        assert "zone to zone" in message and "decision D4" in message
        assert "not yet connected" not in message


# End to end through job.run, with real files.


def _settings(tmp_path: Path, **overrides) -> JobSettings:
    fields = dict(
        input_path=tmp_path / "points.csv",
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=MI_SOUTH,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        geodetic_frame=WGS84_G2296,
    )
    fields.update(overrides)
    return JobSettings(**fields)


def _mi_south_row(height: str = "200.000") -> str:
    """A real MI-S coordinate of 43.0 N, 84.5 W, as an input row.

    An input, not an expected value: the NAD 83 position projected into MI-S
    by the program's own projection, so the row is plausible State Plane data
    exactly where the reviewer's geodetic point is. Written with repr, so the
    file holds the projected doubles exactly.
    """
    point = project_point(43.0, -84.5, NAD83_2011, MI_SOUTH)
    return f"1,{point.target_northing!r},{point.target_easting!r},{height},P\n"


def _assert_refused_before_reading_and_nothing_written(settings, expected):
    """Refused with ``expected``, nothing written, and the same before the file exists.

    The run goes through the whole public path a job takes - ``job.run`` then
    ``exports.write_all`` - so "nothing written" means the archive path, not
    only that ``run`` returned no result. Then the input file is deleted and
    the same refusal must come back: it fires at the settings, before
    ``pnezd.read`` is ever asked for the file.
    """
    with pytest.raises(expected) as caught:
        exports.write_all(run(settings))
    out = settings.output_directory
    assert not out.exists() or not any(out.iterdir())
    message = str(caught.value)

    settings.input_path.unlink()
    with pytest.raises(expected):
        exports.write_all(run(settings))
    assert not out.exists() or not any(out.iterdir())
    return message


# Half of HTDP's print unit in latitude (1e-10 deg), carried into grid metres:
# 0.5e-10 deg x (pi/180) x 6.39e6 m (the meridian radius of curvature at 43 N,
# which is the largest radius the projection scales a latitude step by here)
# = 5.6e-6 m; a longitude step is no larger (cos 43 < 1). The grid N and E
# each take at most both steps, rotated by the convergence and scaled by
# k < 1.0001, so each component of the projected difference is at most
# 2 x 5.6e-6 x 1.0001 = 1.12e-5 m. Rounded up.
GRID_TOLERANCE_M = 1.2e-5


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_job_geodetic_to_zone_on_a_global_frame_converts(tmp_path, frame):
    """SUPERSEDES test_job_geodetic_to_zone_on_a_global_frame_refuses.

    Same job: GEODETIC_TO_ZONE, 43.0 / -84.5, target MI-S, Z 165.000 - now
    with the observation date. The Z is ORTHOMETRIC (the default kind), so
    HTDP is handed H = 165.000 in place of h, which is exactly the frozen
    record's input height. The expected grid coordinate is HTDP's printed NAD 83
    output projected by the program's own NCAT-verified projection - two
    independent legs - within GRID_TOLERANCE_M per component (derived above).
    The Z is unchanged (plan D6).
    """
    truth = L5_BY_CODE[frame.code]
    settings = _settings(tmp_path, geodetic_frame=frame, observation_date=L5_DATE)
    settings.input_path.write_text("1,43.0,-84.5,165.000,P\n", encoding="utf-8")
    (point,) = run(settings).points
    expected = project_point(
        float(truth.lat_out), -float(truth.lonw_out), NAD83_2011, MI_SOUTH
    )
    assert abs(point.output_northing - expected.target_northing) <= GRID_TOLERANCE_M
    assert abs(point.output_easting - expected.target_easting) <= GRID_TOLERANCE_M
    assert point.output_elevation == 165.0
    assert point.conversion.transform_height.convention is HeightConvention.ORTHOMETRIC

    # The guard's purpose, kept: no date, no conversion - before the file.
    undated = _settings(tmp_path, geodetic_frame=frame)
    message = _assert_refused_before_reading_and_nothing_written(undated, ValueError)
    assert f"has positions in {frame.code}" in message
    assert "no observation_date" in message


# Half of HTDP's print unit, 0.5e-10 deg, plus the bound on the projection
# round trip measured in the test itself (1e-11 deg): HTDP's map is a
# near-identity shift (its Jacobian differs from 1 by about 1e-6), so an
# input moved by the round trip moves the output by the same to within
# rounding.
GEODETIC_TOLERANCE_DEG = 0.5e-10 + 1e-11


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_job_zone_to_geodetic_into_a_global_frame_converts(tmp_path, frame):
    """SUPERSEDES test_job_zone_to_geodetic_into_a_global_frame_refuses.

    Same job: MI-S in, geodetic_frame = <global> out - the direction no
    per-point gate could see under W2. The input row is the reverse record's
    NAD 83 input (43.0 N 84.5 W) projected into MI-S by the program, so the
    job's inverse gives that position back to within the round trip, and the
    written latitude and longitude must be HTDP's printed output in the
    global frame - not the NAD 83 pivot, which is what W2 refused to write
    under a WGS 84 label.
    """
    truth = L5R_BY_CODE[frame.code]
    settings = _settings(
        tmp_path,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        geodetic_frame=frame,
        observation_date=L5_DATE,
    )
    settings.input_path.write_text(_mi_south_row("165.000"), encoding="utf-8")
    (point,) = run(settings).points
    # The round trip of the input, measured: the bound GEODETIC_TOLERANCE_DEG
    # assumes.
    assert abs(point.conversion.latitude - 43.0) <= 1e-11
    assert abs(point.conversion.longitude + 84.5) <= 1e-11
    assert abs(point.output_northing - float(truth.lat_out)) <= GEODETIC_TOLERANCE_DEG
    assert abs(-point.output_easting - float(truth.lonw_out)) <= GEODETIC_TOLERANCE_DEG
    assert point.output_northing != point.conversion.latitude

    undated = _settings(
        tmp_path,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        geodetic_frame=frame,
    )
    message = _assert_refused_before_reading_and_nothing_written(undated, ValueError)
    assert f"has positions in {frame.code}" in message


@pytest.mark.parametrize("frame", FIVE, ids=FIVE_IDS)
def test_job_vertical_only_on_a_global_frame_converts_through_its_path(tmp_path, frame):
    """SUPERSEDES test_job_vertical_only_on_a_global_frame_refuses_at_the_missing_identity.

    Same job: VERTICAL_ONLY, geodetic input in <global>, NGVD 29 to NAVD 88,
    Z 165.000 (orthometric). No identity is registered for the frame, and none
    is added (pinned in section 2): the pivot is found through the frame's
    HTDP path to NAD 83 (plan D8), so it must be HTDP's printed NAD 83 output
    - at HTDP's printed digit - and the columns must mirror the input exactly.
    """
    truth = L5_BY_CODE[frame.code]
    settings = _settings(
        tmp_path,
        direction=Direction.VERTICAL_ONLY,
        target_zone=None,
        geodetic_frame=frame,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
        observation_date=L5_DATE,
    )
    settings.input_path.write_text("1,43.0,-84.5,165.000,P\n", encoding="utf-8")
    (point,) = run(settings).points
    assert f"{point.conversion.latitude:.10f}" == truth.lat_out
    assert f"{-point.conversion.longitude:.10f}" == truth.lonw_out
    assert (point.output_northing, point.output_easting) == (43.0, -84.5)
    assert point.conversion.external_position.frame is frame
    assert point.vertical is not None
    with pytest.raises(FrameTransformationUnavailableError):
        require_frame_path(frame, frame)


@pytest.mark.parametrize(
    ("direction", "mode"),
    [
        (Direction.GEODETIC_TO_ZONE, VerticalMode.HORIZONTAL),
        (Direction.GEODETIC_TO_ZONE, VerticalMode.HORIZONTAL_AND_VERTICAL),
        (Direction.ZONE_TO_GEODETIC, VerticalMode.HORIZONTAL),
        (Direction.VERTICAL_ONLY, VerticalMode.VERTICAL),
    ],
    ids=["g2z-horizontal", "g2z-vertical", "z2g-horizontal", "vertical-only"],
)
def test_job_with_ellipsoid_heights_on_wgs84_g2296_converts(tmp_path, direction, mode):
    """SUPERSEDES test_job_with_ellipsoid_heights_on_wgs84_g2296_refuses.

    The four ELLIPSOID-height jobs W2 refused at the frame gate now convert,
    and the height takes the path plan D6 sets, against HTDP's printed h:

    * GEODETIC_TO_ZONE, horizontal: the Z written is the ellipsoid height in
      the OUTPUT frame, NAD 83 - HTDP's 166.099 m for 165.000 m in G2296;
    * GEODETIC_TO_ZONE and VERTICAL_ONLY, vertical: the Z written is
      H = h(NAD 83) - N, with N from the program's GEOID18 reader at HTDP's
      printed NAD 83 pivot (the gate's L5 job, which the unguarded seed wrote
      as 198.085 - h in WGS 84 taken as h in NAD 83);
    * ZONE_TO_GEODETIC, horizontal: the Z is a NAD 83 h (the zone's frame),
      and the Z written is HTDP's reverse output in G2296, 163.901 m.

    Each within half of HTDP's 1 mm print unit, plus 1e-6 m for N read at the
    program's unrounded pivot rather than the printed one (the two are within
    5e-11 deg, about 6 um, and N changes by well under 1e-6 m over that).
    """
    from michspc.fileio import geoid

    overrides = dict(
        direction=direction,
        geodetic_frame=WGS84_G2296,
        input_height_kind=HeightKind.ELLIPSOID,
        vertical_mode=mode,
        observation_date=L5_DATE,
    )
    if mode is not VerticalMode.HORIZONTAL:
        overrides.update(
            source_vertical_datum=NAVD88, target_vertical_datum=NAVD88
        )
    if direction is Direction.ZONE_TO_GEODETIC:
        overrides.update(source_zone=MI_SOUTH, target_zone=None)
        row = _mi_south_row("165.000")
    elif direction is Direction.VERTICAL_ONLY:
        overrides.update(target_zone=None)
        row = "1,43.0,-84.5,165.000,P\n"
    else:
        row = "1,43.0,-84.5,165.000,P\n"
    settings = _settings(tmp_path, **overrides)
    settings.input_path.write_text(row, encoding="utf-8")
    (point,) = run(settings).points
    tolerance = 0.0005 + 1e-6

    if direction is Direction.ZONE_TO_GEODETIC:
        truth = L5R_BY_CODE[WGS84_G2296.code]
        assert abs(point.output_elevation - float(truth.h_out)) <= tolerance
        return
    truth = L5_BY_CODE[WGS84_G2296.code]
    if mode is VerticalMode.HORIZONTAL:
        assert abs(point.output_elevation - float(truth.h_out)) <= tolerance
        return
    separation = geoid.geoid_height(
        float(truth.lat_out),
        -float(truth.lonw_out),
        geoid.default_grid(geoid.GEOID18_MODEL),
    )
    expected = float(truth.h_out) - separation
    assert abs(point.output_elevation - expected) <= tolerance
    # The reviewer's unguarded figure is more than a metre away.
    assert abs(point.output_elevation - 198.085) > 1.0


def test_the_same_jobs_on_nad83_still_convert(tmp_path):
    """The control: the frames transform, the NAD 83 jobs are untouched.

    The reviewer's GEODETIC_TO_ZONE job, identical but for geodetic_frame =
    NAD83(2011) and no date, converts as an identity; so does its
    ZONE_TO_GEODETIC mirror. Neither carries any transformation evidence.
    """
    settings = _settings(tmp_path, geodetic_frame=NAD83_2011)
    settings.input_path.write_text("1,43.0,-84.5,200.000,P\n", encoding="utf-8")
    result = run(settings)
    assert len(result.points) == 1
    assert not result.points[0].conversion.is_transformed

    mirror = _settings(
        tmp_path,
        direction=Direction.ZONE_TO_GEODETIC,
        source_zone=MI_SOUTH,
        target_zone=None,
        geodetic_frame=NAD83_2011,
    )
    mirror.input_path.write_text(_mi_south_row(), encoding="utf-8")
    (point,) = run(mirror).points
    assert not point.conversion.is_transformed
    assert isinstance(MI_SOUTH, Zone)


# ==========================================================================
# 5. A record's code is tied to the registry record it names.
#
# Interim gate 1 of the WGS 84 build, finding L4. A ReferenceFrame whose code
# is a registry code but whose other fields differ is a second, disagreeing
# copy of that frame's facts. ``frames._canonical`` used to substitute the
# registry's record silently - so the frame gate answered for NAD 83 while the
# caller's WGS 84 fields travelled on, and the job record printed
# "Reference frame NAD83(2011) - World Geodetic System 1984, realization
# G2296". Now it refuses, naming the fields; an EQUAL record still resolves.
# ==========================================================================

from michspc.spc.frames import FrameRecordMismatchError, resolve_frame  # noqa: E402

# The reviewer's two counterexamples, verbatim.
NAD83_NAMED_G2296 = dataclasses.replace(WGS84_G2296, code="NAD83(2011)")
G2296_NAMED_ITRF2020 = dataclasses.replace(ITRF2020, code="WGS84(G2296)")


def test_a_record_that_disagrees_with_the_registry_still_constructs():
    """The refusal is at use, not construction: each fake is self-consistent.

    WGS84(G2296)'s own fields under NAD 83's code: time-dependent, WGS 84
    ellipsoid, HTDP frame G2296 - all mutually consistent, so
    ``__post_init__`` (which checks the record against itself and HTDP) has
    nothing to object to. Only the registry knows the code means another frame.
    """
    assert NAD83_NAMED_G2296.htdp_frame is htdp.WGS84_G2296
    assert NAD83_NAMED_G2296.is_time_dependent
    assert G2296_NAMED_ITRF2020.ellipsoid_name == "GRS 80"


@pytest.mark.parametrize(
    "fake,differing",
    [
        # replace(WGS84_G2296, code=NAD83) keeps G2296's name, ellipsoid
        # ("WGS 84" against NAD 83's "GRS 80"), citation, epoch kind
        # (TIME_DEPENDENT against PLATE_FIXED), reference epoch (None against
        # 2010.0) and HTDP frame (G2296 against NAD_83(2011)); status is USABLE
        # on both, so it is the one field NOT named.
        (
            NAD83_NAMED_G2296,
            ["name", "ellipsoid_name", "citation", "epoch_kind", "reference_epoch", "htdp_frame"],
        ),
        # replace(ITRF2020, code=G2296): name, ellipsoid ("GRS 80" against
        # "WGS 84"), citation and HTDP frame (ITRF2020 against G2296) differ;
        # both are USABLE and TIME_DEPENDENT with no reference epoch.
        (G2296_NAMED_ITRF2020, ["name", "ellipsoid_name", "citation", "htdp_frame"]),
    ],
    ids=["G2296-as-NAD83", "ITRF2020-as-G2296"],
)
def test_require_frame_path_refuses_a_record_that_disagrees_with_its_code(fake, differing):
    registered = frames.frame_by_code(fake.code)
    for source, target in ((fake, NAD83_2011), (NAD83_2011, fake), (fake, fake)):
        with pytest.raises(FrameRecordMismatchError) as caught:
            require_frame_path(source, target)
        message = str(caught.value)
        assert f"passed as {fake.code!r}" in message
        assert f"its {', '.join(differing)} differ " in message
        for name in differing:
            assert f"{name} {getattr(fake, name)!r}"[:60] in message, name
    # A FrameMismatchError, so every existing catch site refuses it.
    assert issubclass(FrameRecordMismatchError, FrameMismatchError)
    assert registered != fake


def test_project_point_and_geodetic_position_refuse_the_disagreeing_record():
    """Both convert entry points that take a frame from a caller."""
    with pytest.raises(FrameRecordMismatchError):
        project_point(43.0, -84.5, NAD83_NAMED_G2296, MI_SOUTH)
    with pytest.raises(FrameRecordMismatchError):
        convert.geodetic_position(43.0, -84.5, NAD83_NAMED_G2296)
    with pytest.raises(FrameRecordMismatchError):
        resolve_frame(G2296_NAMED_ITRF2020)


def test_a_geodetic_to_zone_job_on_the_disagreeing_record_refuses(tmp_path):
    """The reviewer's job: GEODETIC_TO_ZONE, geodetic_frame = G2296-as-NAD83.

    Before the fix this ran as a NAD 83 identity and wrote an archive whose
    record named the WGS 84 realization beside the NAD 83 code. Now the
    settings gate refuses it before the file is read, and nothing is written.
    """
    settings = _settings(tmp_path, geodetic_frame=NAD83_NAMED_G2296)
    settings.input_path.write_text("1,43.0,-84.5,200.000,P\n", encoding="utf-8")
    message = _assert_refused_before_reading_and_nothing_written(
        settings, FrameRecordMismatchError
    )
    assert "ellipsoid_name" in message and "htdp_frame" in message


def test_a_vertical_only_geodetic_job_on_the_disagreeing_record_refuses(tmp_path):
    settings = _settings(
        tmp_path,
        direction=Direction.VERTICAL_ONLY,
        target_zone=None,
        geodetic_frame=NAD83_NAMED_G2296,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NGVD29,
        target_vertical_datum=NAVD88,
    )
    settings.input_path.write_text("1,43.0,-84.5,200.000,P\n", encoding="utf-8")
    _assert_refused_before_reading_and_nothing_written(settings, FrameRecordMismatchError)


def test_a_record_equal_in_value_resolves_and_the_conversion_carries_the_registrys(tmp_path):
    """The control: equal is not identical, and equal resolves.

    A field-for-field copy of NAD83(2011) - what a registry rebuilding records
    from data would produce - is a distinct object, resolves to the registry's
    record, and the conversion carries THAT record, so nothing downstream ever
    holds a caller's copy.
    """
    copy = dataclasses.replace(NAD83_2011)
    assert copy == NAD83_2011 and copy is not NAD83_2011
    assert resolve_frame(copy) is NAD83_2011
    assert require_frame_path(copy, NAD83_2011) is FRAME_TRANSFORMATIONS[(NAD83_2011, NAD83_2011)]
    assert project_point(43.0, -84.5, copy, MI_SOUTH).frame is NAD83_2011
    assert convert.geodetic_position(43.0, -84.5, copy).frame is NAD83_2011

    settings = _settings(tmp_path, geodetic_frame=copy)
    settings.input_path.write_text("1,43.0,-84.5,200.000,P\n", encoding="utf-8")
    assert len(run(settings).points) == 1


def test_an_unregistered_code_is_not_this_checks_business():
    """A code the registry does not know comes back unchanged: the pair refusal names it."""
    nad27 = ReferenceFrame(
        code="NAD27",
        name="hand-built by this test",
        ellipsoid_name="Clarke 1866",
        citation="synthetic",
        status=FrameStatus.USABLE,
        epoch_kind=FrameEpochKind.PLATE_FIXED,
        reference_epoch=1927.0,
        htdp_frame=None,
    )
    assert resolve_frame(nad27) is nad27
    with pytest.raises(TypeError):
        resolve_frame(MI_SOUTH)
