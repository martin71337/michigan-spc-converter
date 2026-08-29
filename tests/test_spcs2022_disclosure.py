"""What the job record SAYS about an SPCS2022 job (WP-H5).

Two claims live here, and the second is the reason the first has to be a
byte-for-byte literal:

* **A record must describe the projection it actually used.** Every projection
  is defined by different constants - a transverse Mercator has no standard
  parallel, an oblique Mercator's false coordinates are at its centre rather
  than at a grid origin, and a one-parallel Lambert's central parallel and
  scale are PUBLISHED where the two-parallel form's are derived. The block
  that describes a zone used to print the two-parallel field names over
  whatever it was handed, raising ``AttributeError`` on a 1SP zone after the
  coordinates were computed (docs/DESIGN.md amendment #21).

* **No SPCS 83 record may move by a byte.** Sealed surveys carry these words.
  The 1983 arm of both sections is therefore frozen here as literal text
  captured from the program BEFORE this work package touched it, so the second
  era cannot drift the first one while the suite stays green.

The counts the prose states - "Twenty-seven"/"three", "Sixty-three"/"nineteen"
- are literals in ``report.py``, because shipped code never imports the test
tree. They are held against the length of the fixtures and registry tuples they
describe here, which is the only place both can be seen at once.
"""

from __future__ import annotations

import dataclasses
import zipfile
from pathlib import Path

import pytest

from michspc.fileio import exports, report
from michspc.job import Direction, JobSettings, LongitudeConvention, run
from michspc.spc.frames import NATRF2022
from michspc.spc.units import INTERNATIONAL_FEET, METERS
from michspc.spc.zones import (
    MI_CENTRAL,
    MI_SOUTH,
    SPCS83_ZONES,
    SPCS2022_BOUNDS_FILENAME,
    SPCS2022_BOUNDS_SHA256,
    SPCS2022_DEFINITIONS_FILENAME,
    SPCS2022_DEFINITIONS_SHA256,
    SPCS2022_ZONES,
    ProjectionKind,
    zone_by_code,
)
from tests.fixtures.ncat_anchors import NCAT_ANCHORS
from tests.fixtures.spcs2022_engine_anchors import SPCS2022_PROJECTION_ANCHORS

GRAND_RAPIDS = zone_by_code("261008")  # LC1
KALAMAZOO = zone_by_code("261007")  # LC1
ANN_ARBOR = zone_by_code("261001")  # TM
STATEWIDE = zone_by_code("260001")  # OMC


# ==========================================================================
# Helpers: real jobs, through the same door the file tool uses.
# ==========================================================================


def _zone_to_zone(tmp_path, source, target, rows, **overrides) -> JobSettings:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "in.csv"
    path.write_text("\n".join(rows) + "\n", encoding="ascii")
    base = dict(
        input_path=path,
        output_directory=tmp_path / "out",
        direction=Direction.ZONE_TO_ZONE,
        source_zone=source,
        target_zone=target,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
    )
    base.update(overrides)
    return JobSettings(**base)


def _geodetic_to_zone(tmp_path, target, rows, **overrides) -> JobSettings:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "geo.csv"
    path.write_text("\n".join(rows) + "\n", encoding="ascii")
    base = dict(
        input_path=path,
        output_directory=tmp_path / "out",
        direction=Direction.GEODETIC_TO_ZONE,
        source_zone=None,
        target_zone=target,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        # The H3' gate: a 2022 zone is on NATRF2022, so a geodetic job against
        # one must SAY the file's positions are in that frame. NAD83(2011) -
        # the field's default - is refused before the file is read.
        geodetic_frame=NATRF2022,
    )
    base.update(overrides)
    return JobSettings(**base)


def _anchor(zone_code: str, label: str | None = None):
    """A frozen beta-NCAT anchor for this zone - by label, or the first one.

    The statewide zone's lattice has no anchor labelled "origin" (it is
    "projection center"), so the label is optional and the first anchor for the
    zone is a position known to be inside it.
    """
    for anchor in SPCS2022_PROJECTION_ANCHORS:
        if anchor.zone_code == zone_code and (label is None or anchor.label == label):
            return anchor
    raise AssertionError(f"no anchor for zone {zone_code} labelled {label!r}")


def _section(text: str, heading: str, until: str) -> str:
    """The record from one section heading to the rule above the next one."""
    lines = text.splitlines()
    start = lines.index(heading) - 1
    end = lines.index(until) - 1
    return "\n".join(lines[start:end])


def _systems_and_method(text: str) -> str:
    return _section(text, "COORDINATE SYSTEMS", "SCALE FACTOR SUMMARY")


# ==========================================================================
# The 1983 arm, frozen. Captured from the program BEFORE WP-H5 began.
# ==========================================================================

SPCS83_SYSTEMS_AND_METHOD = """\
------------------------------------------------------------------------------
COORDINATE SYSTEMS
------------------------------------------------------------------------------
FROM: Michigan South, zone 2113 (SPCS 83)
  Reference frame           NAD83(2011)
  Projection                Lambert conformal conic, two standard parallels
  Southern standard parallel  42.1000000000 deg N
  Northern standard parallel  43.6666666667 deg N
  Latitude of grid origin     41.5000000000 deg N
  Central meridian            -84.3666666667 deg (84.3666666667 deg west)
  False northing              0.0000 m
  False easting               4,000,000.0000 m
  Central parallel (derived)  42.8850151357 deg N
  Scale at central parallel   0.999906878420
  Source: NOAA Manual NOS NGS 5, Appendix A (PDF p. 77) and Appendix C (PDF pp. 103-104)

TO: Michigan Central, zone 2112 (SPCS 83)
  Reference frame           NAD83(2011)
  Projection                Lambert conformal conic, two standard parallels
  Southern standard parallel  44.1833333333 deg N
  Northern standard parallel  45.7000000000 deg N
  Latitude of grid origin     43.3166666667 deg N
  Central meridian            -84.3666666667 deg (84.3666666667 deg west)
  False northing              0.0000 m
  False easting               6,000,000.0000 m
  Central parallel (derived)  44.9433587575 deg N
  Scale at central parallel   0.999912706253
  Source: NOAA Manual NOS NGS 5, Appendix A (PDF p. 77) and Appendix C (PDF pp. 103-104)

Both zones are on the same reference frame, so this conversion is an
exact re-projection of the same physical positions: no datum shift is
applied and none is needed. Converting back returns the original
coordinates to well under a millimetre.

------------------------------------------------------------------------------
METHOD
------------------------------------------------------------------------------
Authority          NOAA Manual NOS NGS 5, State Plane Coordinate System
                   of 1983 (Stem, January 1989; reprinted with minor
                   corrections March 1990)

Equations          The rigorous Lambert conformal conic mapping
                   equations of section 3.1 - zone constants (3.12),
                   direct conversion (3.13), inverse conversion (3.14).
                   Exact at any latitude, with no approximation term.

Ellipsoid          GRS 80, the ellipsoid of NAD 83 (manual section 1.7).
                   Only the semimajor axis and the flattening are stored;
                   every other constant is derived from those two.

HOW THIS SOFTWARE IS VERIFIED

The zone constants used above are not taken on trust. The manual
publishes, in Appendix C, the constants NGS computed for every Lambert
zone. This software stores only the DEFINING constants - the standard
parallels, the grid origin, the central meridian - and derives the rest.
Its test suite recomputes all of them and requires a match with NGS's
published figures to the last decimal place NGS printed, for all three
Michigan zones.

The conversion itself is checked against the National Geodetic Survey's
own Coordinate Conversion and Transformation Tool (NCAT). Twenty-seven
positions spanning the three zones were converted by NCAT, and those
results are held in the test suite as fixed reference values. This
software reproduces them to within 0.5 mm - which is the precision NCAT
publishes, so the agreement is as close as the reference permits.

Both checks compare this software against NGS. Neither compares it
against itself.

Geoid model        GEOID18, NGS grid tile g2018u3.bin
                   SHA-256 cd2080f904d168e3356effffc535d5d0c9cd8c2a0019ddb4f40a0e2454ebe3b3
                   Geoid heights are NEGATIVE throughout Michigan:
                   the ellipsoid lies above the geoid here.

Elevation factor   R / (R + H + N), manual section 4.1
                   R = 6,372,000 m mean earth radius
                   H = orthometric height as used for the factors
                   N = geoid height, interpolated from the grid above
Combined factor    grid scale factor x elevation factor
"""


def test_an_spcs83_record_still_says_exactly_what_it_always_said(tmp_path):
    """The hard constraint on this work package, as literal text.

    Not "contains the same phrases" - the same bytes, in the same order, with
    the same padding. A per-kind block and an era branch are two places where
    the 1983 arm could drift while every phrase test still passed, and this
    record is what a sealed survey is defended with.
    """
    settings = _zone_to_zone(
        tmp_path,
        MI_SOUTH,
        MI_CENTRAL,
        ["101,200000.000,13000000.000,780.00,IRON PIPE"],
        input_unit=INTERNATIONAL_FEET,
        output_unit=INTERNATIONAL_FEET,
    )

    text = report.build_report(run(settings))

    assert _systems_and_method(text) == SPCS83_SYSTEMS_AND_METHOD


# ==========================================================================
# The zone block, per projection kind.
# ==========================================================================


def test_a_one_parallel_zone_calls_its_parallel_and_scale_DEFINING(tmp_path):
    """LC1's central parallel and scale are published, not computed.

    The two-parallel block labels the same two quantities "(derived)". A record
    that presented NGS's published constant as something this program worked
    out would misstate where the number came from - and the two blocks sit in
    the same document, so the distinction has to be visible in the words.
    """
    anchor = _anchor("261008")
    text = report.build_report(
        run(
            _zone_to_zone(
                tmp_path,
                GRAND_RAPIDS,
                KALAMAZOO,
                [f"101,{anchor.northing_m},{anchor.easting_m},250.00,ORIGIN"],
            )
        )
    )
    block = _systems_and_method(text)

    assert "FROM: Michigan Grand Rapids, zone 261008 (SPCS2022)" in block
    assert "  Reference frame           NATRF2022" in block
    # The kind's own name, from the one dispatch table - not a hardcoded
    # "Lambert conformal conic, two standard parallels".
    assert "Lambert conformal conic, central parallel and" in block
    assert "scale factor" in block
    # Hand-derived from zones.py: 42 deg 48' = 42.8, k_0 = 1.000018, and the
    # grid origin IS that parallel.
    assert "  Central parallel            42.8000000000 deg N (defining)" in block
    assert "  Scale on central parallel   1.000018000000 (defining)" in block
    assert (
        "  Latitude of grid origin     42.8000000000 deg N (the central parallel)"
        in block
    )
    assert "  Central meridian            -85.1500000000 deg (85.1500000000 deg west)" in block
    assert "  False northing              228,600.0000 m" in block
    assert "  False easting               1,409,700.0000 m" in block
    # And it does NOT describe an LC1 zone with the 2SP form's field names.
    assert "standard parallel" not in block
    assert "(derived)" not in block


def test_a_transverse_mercator_zone_names_the_central_meridian_scale(tmp_path):
    """TM has no standard parallel at all, and phi_0 is the GRID ORIGIN.

    Both are ways a 2SP-shaped block would misdescribe this zone in words a
    surveyor would accept without blinking.
    """
    anchor = _anchor("261001")
    text = report.build_report(
        run(
            _zone_to_zone(
                tmp_path,
                ANN_ARBOR,
                GRAND_RAPIDS,
                [f"101,{anchor.northing_m},{anchor.easting_m},250.00,ORIGIN"],
            )
        )
    )
    block = _systems_and_method(text)

    assert "FROM: Michigan Ann Arbor, zone 261001 (SPCS2022)" in block
    assert "  Projection                Transverse Mercator (Gauss-Kruger)" in block
    # Hand-derived from zones.py: 41 deg 18' = 41.3, CM 84 deg 06' W, k_0
    # 1.000022, false E 381,000 m, false N 0.
    assert "  Latitude of grid origin     41.3000000000 deg N" in block
    assert "  Central meridian            -84.1000000000 deg (84.1000000000 deg west)" in block
    assert "  Scale on central meridian   1.000022000000 (defining)" in block
    assert "  False northing              0.0000 m" in block
    assert "  False easting               381,000.0000 m" in block
    assert "standard parallel" not in block.split("TO:")[0]


def test_an_oblique_mercator_zone_says_its_false_origin_is_the_CENTRE(tmp_path):
    """The variant is part of the zone's identity (DESIGN.md #61).

    The natural-origin Hotine assigns the same two numbers where the initial
    line crosses the equator - thousands of kilometres from the centre - so
    "False northing 762,000 m" alone does not identify the quantity. The skew
    azimuth is signed and is not a longitude, so its sense is named too.
    """
    text = report.build_report(
        run(_geodetic_to_zone(tmp_path, STATEWIDE, ["201,45.0,-86.0,250.00,CENTRE"]))
    )
    block = _systems_and_method(text)

    assert "TO: Michigan, zone 260001 (SPCS2022)" in block
    assert "  Projection                Hotine oblique Mercator" in block
    # Hand-derived from zones.py: centre 45 N / 86 W, skew -26, k_c 0.9998,
    # false N/E 762,000 / 1,524,000 m AT THE CENTRE.
    assert "  Latitude of centre          45.0000000000 deg N" in block
    assert "  Longitude of centre         -86.0000000000 deg (86.0000000000 deg west)" in block
    assert "  Skew azimuth                -26.0000000000 deg (clockwise from north)" in block
    assert "  Scale at projection centre  0.999800000000 (defining)" in block
    assert "  False northing              762,000.0000 m at the projection centre" in block
    assert "  False easting               1,524,000.0000 m at the projection centre" in block


def test_every_2022_zone_can_be_described_without_raising(tmp_path):
    """All nineteen, through the public builder rather than by inspection.

    ``_zone_block`` raised ``AttributeError`` on a non-2SP zone AFTER the
    coordinates were computed - the failure mode #21 recorded - so "it renders"
    is a claim worth making for every zone the registry offers, not for the
    three that happen to be in the tests above.
    """
    for zone in SPCS2022_ZONES:
        anchor = _anchor(zone.code)
        text = report.build_report(
            run(
                _geodetic_to_zone(
                    tmp_path,
                    zone,
                    [f"1,{anchor.latitude},{anchor.longitude},250.00,P"],
                )
            )
        )
        block = _systems_and_method(text)
        assert f"TO: {zone.name}, zone {zone.code} (SPCS2022)" in block
        assert zone.projection_kind.value.split(",")[0] in block
        # The citation is WRAPPED on a 2022 zone, so it is checked by
        # reconstitution rather than by substring: every word of the registry's
        # citation, in order, with the line breaks collapsed. Wrapping may
        # re-space a citation; it may never drop a digest or a URL from one.
        assert " ".join(zone.citation.split()) in " ".join(block.split())


def test_no_line_of_a_2022_zone_block_runs_past_78_columns():
    """The record is read in Notepad, at the width the rest of it is written to.

    A 2022 citation names two NGS captures with their URLs, byte counts, dates
    and digests - about 700 characters, which unwrapped is one line the reader
    has to scroll sideways through to reach the digest they came for. The
    SPCS 83 citation stays on its own single 89-character line, which is frozen
    history and is pinned by the byte-identity tests above; this rule is the
    2022 kinds' and is checked over the WHOLE block, so the projection heading
    and the constants are held to it too.
    """
    for zone in SPCS2022_ZONES:
        for label in ("FROM", "TO"):
            for line in report._zone_block(zone, label):
                assert len(line) <= 78, (
                    f"{zone.name} ({zone.code}) block line is {len(line)} "
                    f"characters: {line!r}"
                )


def test_todays_wrapped_citation_carries_every_url_and_digest_whole():
    """What the real 2022 citation looks like once wrapped.

    Each URL, path and digest sits complete on one line - not merely present
    once the lines are joined back up. True today because the longest token in
    the citation (a 64-character digest) still fits the 68 columns the wrap
    leaves; the RULE that keeps it true at any length is pinned below, because
    this test alone cannot fail if the wrapper is told it may split them.
    """
    lines = report._zone_block(GRAND_RAPIDS, "FROM")

    for token in (
        "https://beta.ngs.noaa.gov/SPCS/json_data/zoneDefinitions.json",
        "https://beta.ngs.noaa.gov/SPCS/json_data/zoneBounds.json",
        "review/nsrs-n0/raw/zoneBounds.json",
        SPCS2022_DEFINITIONS_SHA256,
        SPCS2022_BOUNDS_SHA256,
    ):
        assert any(token in line for line in lines), f"{token} was broken across lines"


def test_a_citation_token_too_long_to_fit_is_never_split():
    """The rule, at a length that exercises it.

    A URL or a repository path snapped across two lines in a sealed record is a
    wrong URL and a wrong path: the reader's only way back to NGS's own file is
    to retype it, and a hyphenated path (``review/nsrs-n0/...``) broken at its
    hyphen is not even visibly broken.

    Today's citation cannot discriminate this - its longest token fits - so the
    zone here carries one that does not. An over-long line is the correct
    outcome: the wrapper puts the token on a line of its own rather than
    dividing it.
    """
    long_url = (
        "https://beta.ngs.noaa.gov/SPCS/json_data/"
        "zone-definitions-2022-official-release-michigan.json"
    )
    assert len(long_url) > 78 - len(report._SOURCE_PREFIX)
    zone = dataclasses.replace(
        GRAND_RAPIDS,
        citation=f"Defining constants from NGS's own published file, {long_url}, "
        f"captured 2027-01-01. NGS beta",
    )

    lines = report._source_lines(zone)

    assert any(long_url in line for line in lines), (
        f"the citation's URL was split across lines: {lines}"
    )


def test_an_spcs83_citation_is_still_one_unwrapped_line():
    """The other side of the per-kind rule, stated on its own.

    The byte-identity pins hold it too; this says why the 88-character line is
    deliberate, so nobody tidies it into the wrapped form and takes two sealed
    eras' records with it.
    """
    lines = report._zone_block(MI_SOUTH, "FROM")

    source = [line for line in lines if line.startswith("  Source:")]
    assert len(source) == 1
    assert source[0] == f"  Source: {MI_SOUTH.citation}"
    # Over the record's 78 columns, and printed that way since 0.1.0.
    assert len(source[0]) == 88


def test_a_zone_this_record_cannot_describe_is_refused_by_name():
    """Fail closed, in the document layer.

    A fifth projection could be COMPUTABLE before it is DESCRIBABLE - the
    dispatch tables are separate - and the wrong block would be a plausible
    falsehood rather than a visible error, because most of these records carry
    field names that read sensibly under another projection.
    """

    @dataclasses.dataclass(frozen=True)
    class UnknownDef:
        lon_origin: float = -85.0
        easting_origin: float = 0.0
        northing_grid_origin: float = 0.0

    zone = dataclasses.replace(GRAND_RAPIDS, definition=UnknownDef())

    with pytest.raises(report.ZoneBlockUnavailableError) as caught:
        report._zone_block(zone, "FROM")

    message = str(caught.value)
    assert "UnknownDef" in message
    assert "Michigan Grand Rapids" in message
    assert "LambertTwoParallelDef" in message
    assert "ObliqueMercatorCenterDef" in message


# ==========================================================================
# METHOD: the era branch.
# ==========================================================================


def test_a_2022_record_names_the_2022_authorities_and_both_captures(tmp_path):
    anchor = _anchor("261008")
    text = report.build_report(
        run(
            _zone_to_zone(
                tmp_path,
                GRAND_RAPIDS,
                KALAMAZOO,
                [f"101,{anchor.northing_m},{anchor.easting_m},250.00,ORIGIN"],
            )
        )
    )
    method = _section(text, "METHOD", "SCALE FACTOR SUMMARY")
    flat = " ".join(method.split())

    # The equations are still the manual's.
    assert "NOAA Manual NOS NGS 5" in method
    # The policy authority for the 2022 system, which the 1983 arm has no
    # reason to name.
    assert "NOAA Special Publication NOS NGS 13" in method
    # Both captures, each with its own date and its own digest.
    assert f"{SPCS2022_DEFINITIONS_FILENAME}, captured 2026-08-28" in method
    assert f"SHA-256 {SPCS2022_DEFINITIONS_SHA256}" in method
    assert f"{SPCS2022_BOUNDS_FILENAME}, captured 2026-08-29" in method
    assert f"SHA-256 {SPCS2022_BOUNDS_SHA256}" in method
    # The ellipsoid is shared by both frames, and the record says which
    # document establishes that rather than leaving it to be assumed.
    assert "GRS 80 - the ellipsoid of NAD 83 and of NATRF2022 alike" in flat
    assert "NOAA Technical Report NOS NGS 62" in method
    # The beta provenance, stated as the dated fact it is.
    assert "NGS beta" in method
    assert "beta NCAT" in method
    assert "re-frozen against NGS's official release" in flat
    assert "docs/REFREEZE-NSRS.md" in method
    # The closing sentence pattern survives the era branch.
    assert "Neither compares it" in method and "against itself." in method
    # And the 1983 arm's Appendix C claim is NOT made about a 2022 zone: NGS
    # publishes no Appendix C constants for these zones.
    assert "Appendix C" not in method


def test_the_equations_listed_are_the_ones_the_job_actually_used(tmp_path):
    """Derived from the zones present, never a static list of all three.

    A record that named the transverse Mercator equations on a job that used
    only the Lambert ones would describe work that was not done.
    """
    lc1_only = report.build_report(
        run(
            _geodetic_to_zone(
                tmp_path / "a",
                KALAMAZOO,
                ["1,42.1,-85.65,250.00,P"],
            )
        )
    )
    tm_only = report.build_report(
        run(
            _geodetic_to_zone(
                tmp_path / "b",
                ANN_ARBOR,
                ["1,41.3,-84.1,250.00,P"],
            )
        )
    )
    omc_only = report.build_report(
        run(
            _geodetic_to_zone(
                tmp_path / "c",
                STATEWIDE,
                ["1,45.0,-86.0,250.00,P"],
            )
        )
    )
    anchor = _anchor("261001")
    both = report.build_report(
        run(
            _zone_to_zone(
                tmp_path / "d",
                ANN_ARBOR,
                GRAND_RAPIDS,
                [f"1,{anchor.northing_m},{anchor.easting_m},250.00,P"],
            )
        )
    )

    assert "section 3.1" in lc1_only
    assert "section 3.2" not in lc1_only
    assert "section 3.3" not in lc1_only

    assert "section 3.2" in tm_only
    assert "section 3.1" not in tm_only
    assert "section 3.3" not in tm_only

    assert "section 3.3" in omc_only
    assert "section 3.1" not in omc_only
    assert "section 3.2" not in omc_only

    # A job using two kinds names both, in ProjectionKind's declaration order.
    method = _section(both, "METHOD", "SCALE FACTOR SUMMARY")
    assert method.index("section 3.1") < method.index("section 3.2")


def test_a_projection_with_no_registered_manual_section_is_refused(monkeypatch):
    """Anti-vacuousness for the table above.

    Without this, ``_MANUAL_SECTIONS`` could lose an entry and the record would
    quietly name one fewer set of equations than the job used.
    """
    monkeypatch.delitem(report._MANUAL_SECTIONS, ProjectionKind.OBLIQUE_MERCATOR)

    with pytest.raises(ValueError) as caught:
        report._equation_lines([STATEWIDE])

    assert "Hotine oblique Mercator" in str(caught.value)


def test_a_record_naming_zones_from_two_eras_refuses(tmp_path):
    """The assumption the era branch rests on, checked rather than trusted.

    ``job.run`` and ``frames.require_frame_path`` both refuse a cross-era job
    before any coordinate is computed, so this shape is unreachable through the
    program - but a settings record is two dozen lines to build by hand, and a
    document that described half a job in the wrong era's words would be worse
    than a refusal.
    """
    settings = _zone_to_zone(tmp_path, MI_SOUTH, GRAND_RAPIDS, ["1,0,0,0,P"])

    with pytest.raises(ValueError) as caught:
        report._method_and_verification(settings)

    message = str(caught.value)
    assert "Michigan South" in message
    assert "Michigan Grand Rapids" in message
    assert "NAD83(2011) to NATRF2022" in message


def test_a_job_with_no_zone_at_all_keeps_the_1983_arm(tmp_path):
    """A vertical-only job on geodetic positions involves no zone.

    It printed the 1983 METHOD text before this package and prints it still -
    part of the byte-identity constraint, and stated here because the era
    branch has to answer for the empty case rather than fall into it.
    """
    from michspc.job import VerticalMode
    from michspc.spc.vertical import NAVD88

    path = tmp_path / "v.csv"
    path.write_text("1,43.0,-84.5,200.000,P\n", encoding="ascii")
    settings = JobSettings(
        input_path=path,
        output_directory=tmp_path / "out",
        direction=Direction.VERTICAL_ONLY,
        source_zone=None,
        target_zone=None,
        input_unit=METERS,
        output_unit=METERS,
        longitude_convention=LongitudeConvention.NEGATIVE_WEST,
        vertical_mode=VerticalMode.VERTICAL,
        source_vertical_datum=NAVD88,
        target_vertical_datum=NAVD88,
    )

    text = report.build_report(run(settings))

    assert "Equations          The rigorous Lambert conformal conic mapping" in text
    assert "SPCS2022" not in _section(text, "METHOD", "SCALE FACTOR SUMMARY")


# ==========================================================================
# The counts in the prose are the counts in the fixtures.
# ==========================================================================

_NUMBER_WORDS = {
    3: "three",
    19: "nineteen",
    27: "Twenty-seven",
    63: "Sixty-three",
}


def test_the_verification_prose_counts_match_the_fixtures_they_describe():
    """Shipped code never imports the test tree, so the counts are literals.

    That is a deliberate seam, and this is the stitch across it: the only
    place where the sentence and the thing it counts can be compared. A fixture
    that grows or shrinks without the sentence following it makes the record
    state a number that is not true of the suite it describes.
    """
    source = Path(report.__file__).read_text(encoding="utf-8")

    assert _NUMBER_WORDS[len(NCAT_ANCHORS)] == "Twenty-seven"
    assert f"{_NUMBER_WORDS[len(NCAT_ANCHORS)]}" in source
    assert f"spanning the {_NUMBER_WORDS[len(SPCS83_ZONES)]} zones" in source

    assert _NUMBER_WORDS[len(SPCS2022_PROJECTION_ANCHORS)] == "Sixty-three"
    assert f"{_NUMBER_WORDS[len(SPCS2022_PROJECTION_ANCHORS)]} positions" in source
    assert (
        f"all {_NUMBER_WORDS[len(SPCS2022_ZONES)]} Michigan " in source
    )


# ==========================================================================
# End to end: file -> job.run -> ZIP -> the record read back out of it.
# ==========================================================================


def _record_from_archive(result) -> str:
    written = exports.write_all(result)
    with zipfile.ZipFile(written["archive"]) as archive:
        names = archive.namelist()
        assert len(names) == 3
        member = next(n for n in names if n.endswith("_README.txt"))
        return archive.read(member).decode("utf-8")


def test_a_2022_zone_to_zone_job_writes_a_verifiable_archive(tmp_path):
    """261008 -> 261007, both LC1, both on NATRF2022: same-frame, no bridge.

    ``write_all`` round-trips the clean export through this program's own
    reader and reads the staged archive back before renaming it, so reaching
    the assertions below IS the archive verifying.
    """
    anchor = _anchor("261008")
    result = run(
        _zone_to_zone(
            tmp_path,
            GRAND_RAPIDS,
            KALAMAZOO,
            [f"101,{anchor.northing_m},{anchor.easting_m},250.00,ORIGIN"],
        )
    )

    text = _record_from_archive(result)

    assert "FROM: Michigan Grand Rapids, zone 261008 (SPCS2022)" in text
    assert "TO: Michigan Kalamazoo, zone 261007 (SPCS2022)" in text
    assert text.count("(defining)") == 4  # two LC1 zones, two constants each
    assert "beta NCAT" in text
    # The era-shared sections still render around the new ones.
    assert "SCALE FACTOR SUMMARY" in text
    assert "ELEVATIONS" in text
    assert "WARNINGS" in text
    assert "FILES WRITTEN" in text
    assert "END OF JOB RECORD" in text
    assert "Grid scale factor" in text
    assert "Combined factor    grid scale factor x elevation factor" in text


def test_a_natrf2022_geodetic_job_writes_a_verifiable_archive(tmp_path):
    """Geodetic in, statewide oblique Mercator out, all within NATRF2022.

    The frame the file was read as is the one fact a latitude and longitude
    cannot carry in its own columns, and on this job it is NOT the default.
    """
    result = run(
        _geodetic_to_zone(tmp_path, STATEWIDE, ["201,45.0,-86.0,250.00,CENTRE"])
    )

    text = _record_from_archive(result)

    assert "Reference frame    NATRF2022 - North American Terrestrial" in text
    assert "TO: Michigan, zone 260001 (SPCS2022)" in text
    assert "at the projection centre" in text
    assert "section 3.3  Hotine oblique Mercator" in text
    assert "END OF JOB RECORD" in text


def test_an_spcs83_archive_still_carries_the_frozen_sections(tmp_path):
    """The byte-identity pin, through the ZIP rather than the builder.

    The record a surveyor actually opens is the one inside the archive.
    """
    result = run(
        _zone_to_zone(
            tmp_path,
            MI_SOUTH,
            MI_CENTRAL,
            ["101,200000.000,13000000.000,780.00,IRON PIPE"],
            input_unit=INTERNATIONAL_FEET,
            output_unit=INTERNATIONAL_FEET,
        )
    )

    text = _record_from_archive(result)

    assert _systems_and_method(text) == SPCS83_SYSTEMS_AND_METHOD
