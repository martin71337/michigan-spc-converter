"""The zone registry: both eras, and the two frozen captures behind one of them.

Four kinds of check live here, and only the first is about numbers:

1. **The capture cross-check.** Every field of every SPCS2022 record is
   compared against NGS's own files, parsed here from the frozen copies whose
   SHA-256 digests the captures recorded - ``zoneDefinitions.json`` for the
   defining constants a coordinate is computed from, and ``zoneBounds.json``
   for the per-zone extent and easting bounds the warnings are measured
   against. This is the Appendix C pattern applied to the 2022 era: the
   registry must agree with the *authority*, not merely with a copy of the
   authority kept beside it in ``tests/fixtures``. A test that compared
   ``zones.py`` against ``spcs2022_engine_anchors.py`` would pass on a
   transcription error made consistently in both.

2. **The registry's own structural rules**: unique code, abbreviation AND name
   across both eras at once, and every easting range bracketing its own false
   easting - both import-time checks, driven directly here so their refusals
   have live counterexamples; hashability, which
   ``projection.constants_for``'s cache depends on; and the era tuples
   partitioning ``ALL_ZONES`` rather than being written out beside it.

3. **The two per-era policy fields** H2 introduced - ``allowed_units`` and
   ``easting_range_m`` - checked against the evidence that decided them: NGS
   publishes no US-survey-foot false origin for any 2022 zone, and NGS
   publishes a per-zone easting range for every one of them.

4. **The warning aids as behaviour**, not just as stored numbers: a point
   outside a zone's published easting range warns, one inside does not, and
   neither is ever a refusal (docs/DESIGN.md amendment #1).

The frozen captures are read HERE and nowhere else: ``michspc/spc/**`` is
stdlib-only and forbidden to import ``json`` (tests/test_architecture.py), so
the shipped registry is Python literals and only the suite parses NGS's files.

**NGS BETA.** Every 2022 figure checked here is pre-release - the definitions
captured 2026-08-28 and the bounds 2026-08-29 - and carries a re-freeze
obligation against NGS's official release.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import pytest

from michspc.spc.convert import easting_looks_wrong_for_zone
from michspc.spc.frames import NAD83_2011, NATRF2022
from michspc.spc.units import INTERNATIONAL_FEET, METERS, US_SURVEY_FEET
from michspc.spc.zones import (
    ALL_ZONES,
    SPCS2022_ZONES,
    SPCS83_ZONES,
    LambertOneParallelDef,
    LambertTwoParallelDef,
    ObliqueMercatorCenterDef,
    TransverseMercatorDef,
    Zone,
    ZoneRegistryError,
    _check_every_easting_range_brackets_its_false_easting,
    _check_zone_identifiers_are_unique,
    zone_by_code,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

RAW = REPO_ROOT / "review" / "nsrs-n0" / "raw"

DEFINITIONS_PATH = RAW / "zoneDefinitions.json"
DEFINITIONS_SHA256 = (
    "f222dac669503c8e25eb41d477bbb129b813b894b43e7d012effb9dc00bbc06a"
)
DEFINITIONS_BYTES = 632927
"""The digest and size N0 recorded when it fetched the definitions
(review/nsrs-n0/FINDINGS.md section 6, and review/nsrs-n0/raw/spcs_manifest.json).
Checked before anything is read from the file, so a cross-check can never run
against a capture that has been edited into agreement with the registry.
"""

BOUNDS_PATH = RAW / "zoneBounds.json"
BOUNDS_SHA256 = "040f9d5a6e4af2587cb8306d05829a0efefd17a482b37f55678e4ea861f48b66"
BOUNDS_BYTES = 654390
"""The same, for the per-zone bounding boxes, captured 2026-08-29 from
https://beta.ngs.noaa.gov/SPCS/json_data/zoneBounds.json.

A SECOND authority, and a genuinely independent one: it is computed from each
zone's polygon, not from its defining constants, so the checks it supports say
where NGS thinks a zone is used rather than restating where its origin is.
"""

# The exact NGS column names, from FINDINGS.md section 6 and the two files
# themselves. Typed out rather than read from the files, because a renamed
# column must fail loudly here rather than quietly stop being checked.
CODE = "Zone code"
ABBREV = "Zone abrv"
NAME = "Zone name"
ZONE_TYPE = "Zone type"
PROJ_TYPE = "Proj type"
ORIGIN_LAT = "Origin latitude"
ORIGIN_LON_EAST = "Origin longitude east"
ORIGIN_LON_WEST = "Origin longitude west"
SCALE = "Projection origin scale"
SKEW = "Skew azimuth (deg)"
FALSE_N_M = "False northing (m)"
FALSE_E_M = "False easting (m)"
FALSE_N_IFT = "False northing (ift)"
FALSE_E_IFT = "False easting (ift)"
DESIGN_BY = "Design by"
FRAME = "Reference frame"

# zoneBounds.json's columns. Its longitudes are already SIGNED decimal degrees
# ("-84.83"), unlike zoneDefinitions.json's "84 deg 06' W" - two files from the
# same authority in two notations, which is exactly why each is parsed by a
# reader written for it rather than by a shared guess.
MIN_LAT = "Min lat (deg)"
MAX_LAT = "Max lat (deg)"
MIN_LON_WEST = "Min lon west (deg)"
MAX_LON_WEST = "Max lon west (deg)"
MIN_LON_EAST = "Min lon east (deg)"
MAX_LON_EAST = "Max lon east (deg)"
MIN_EASTING_M = "Min easting (m)"
MAX_EASTING_M = "Max easting (m)"
MIN_NORTHING_M = "Min northing (m)"
MAX_NORTHING_M = "Max northing (m)"


def _load_json(path: Path, expect_sha256: str, expect_bytes: int) -> list[dict]:
    """Every row of one NGS file, after authenticating the bytes.

    Not cached deliberately: the authentication is the point, and both files
    together are under 1.3 MB.
    """
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert len(raw) == expect_bytes, (
        f"{path} is {len(raw)} bytes; the capture recorded {expect_bytes}."
    )
    assert digest == expect_sha256, (
        f"{path} hashes to {digest}, not the digest the capture recorded "
        f"({expect_sha256}). The frozen file has changed; re-run the capture "
        f"harness rather than editing this pin."
    )
    return json.loads(raw.decode("utf-8"))


def _load_capture() -> list[dict[str, str]]:
    """Every row of NGS's zone DEFINITIONS."""
    return _load_json(DEFINITIONS_PATH, DEFINITIONS_SHA256, DEFINITIONS_BYTES)


def _load_bounds() -> list[dict[str, str]]:
    """Every row of NGS's zone BOUNDS."""
    return _load_json(BOUNDS_PATH, BOUNDS_SHA256, BOUNDS_BYTES)


def _michigan(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """The nineteen Michigan rows of either file, in the file's own order.

    Selected by zone NAME and cross-checked against the code prefix, so neither
    selection alone decides which rows the registry is compared with.
    """
    by_name = [
        row
        for row in rows
        if row[NAME] == "Michigan" or row[NAME].startswith("Michigan ")
    ]
    by_code = [
        row
        for row in rows
        if row[CODE].startswith("2600") or row[CODE].startswith("2610")
    ]
    assert [row[CODE] for row in by_name] == [row[CODE] for row in by_code]
    return by_name


MICHIGAN_ROWS = _michigan(_load_capture())
ROWS_BY_CODE = {row[CODE]: row for row in MICHIGAN_ROWS}

MICHIGAN_BOUNDS = _michigan(_load_bounds())
BOUNDS_BY_CODE = {row[CODE]: row for row in MICHIGAN_BOUNDS}

DEGREE_SIGN = chr(0x00B0)
"""The degree sign NGS prints its angles with, spelled as a code point so this
source file stays ASCII - the rule tests/fixtures/spcs2022_engine_anchors.py
states for the SPCS2022 material.

NGS's file is UTF-8. Reading it under Windows' default code page turns this one
character into two (mojibake), which is why ``_load_capture`` decodes
explicitly and why an angle that fails to parse refuses instead of guessing."""

DMS = re.compile(r"^(\d+)" + DEGREE_SIGN + r"(\d+)'(?:(\d+(?:\.\d+)?)\")?([NSEW])$")


def parse_dms(text: str) -> float:
    """NGS's printed angle to signed decimal degrees, NEGATIVE WEST.

    ``45 deg 27' N`` -> 45 + 27/60 = 45.45, and ``84 deg 27' W`` -> -84.45.
    An east longitude keeps its sign, so ``275 deg 33' E`` -> +275.55; the
    caller reduces it. (NGS writes the degree sign itself; it is spelled out
    here only to keep this file ASCII.)

    Seconds are optional because NGS's format allows them, not because Michigan
    uses them - all nineteen Michigan angles are whole minutes, which
    ``test_every_michigan_angle_is_whole_minutes`` states outright so a parser
    bug in the seconds branch cannot hide behind never being exercised.

    Refuses anything it does not recognise rather than returning a plausible
    number: a silently mis-parsed origin is a zone in the wrong place.
    """
    match = DMS.match(text.strip())
    if match is None:
        raise ValueError(f"{text!r} is not an NGS degrees/minutes angle")
    degrees, minutes, seconds, hemisphere = match.groups()
    magnitude = int(degrees) + int(minutes) / 60.0 + float(seconds or 0.0) / 3600.0
    return -magnitude if hemisphere in ("S", "W") else magnitude


def parse_number(text: str) -> float:
    """``"1,638,300"`` -> 1638300.0. Every value in NGS's file is a string."""
    return float(text.replace(",", ""))


DEFINITION_FOR_PROJ_TYPE = {
    "OMC": ObliqueMercatorCenterDef,
    "LC1": LambertOneParallelDef,
    "TM": TransverseMercatorDef,
}
"""NGS's ``Proj type`` abbreviation to the definition record that IS it.

Glossed on NGS's zone-definitions page (captured 2026-08-28): "LC1 (Lambert
Conformal Conic, one parallel); TM (Transverse Mercator); OMC (Hotine Oblique
Mercator, center)". The record type is what ``michspc.spc.projection``
dispatches on, so this mapping is the link between NGS's word for a zone and
the mathematics MCX runs for it.
"""

def origin_latitude(definition) -> float:
    """The latitude a zone's grid origin (or projection centre) sits at.

    Every definition record has one, under three different names, because the
    three projections mean three different things by it - a central parallel, a
    grid-origin latitude, a projection centre.

    It lives in the SUITE and not in ``zones.py``: nothing the program does
    needs it. The extents used to be derived from it, and are not any more -
    they are NGS's own published bounding boxes now - so the only remaining
    caller is the cross-check below, which needs one name for "the latitude
    NGS's ``Origin latitude`` column should equal".

    Refuses an unknown record type rather than returning a plausible latitude.
    """
    if isinstance(definition, LambertOneParallelDef):
        return definition.lat_origin
    if isinstance(definition, (LambertTwoParallelDef, TransverseMercatorDef)):
        return definition.lat_grid_origin
    if isinstance(definition, ObliqueMercatorCenterDef):
        return definition.lat_center
    raise TypeError(f"no origin latitude for a {type(definition).__name__}")


ZONE_IDS = [f"{zone.code}-{zone.abbrev}" for zone in SPCS2022_ZONES]


# --------------------------------------------------------------------------
# 1. The capture cross-check.
# --------------------------------------------------------------------------


def test_the_frozen_capture_is_the_file_n0_measured():
    """Digest first, before any value is read out of it."""
    rows = _load_capture()
    assert len(rows) == 953, "NGS publishes 953 zones nationally (FINDINGS 6)"


def test_the_capture_carries_exactly_nineteen_michigan_zones():
    assert len(MICHIGAN_ROWS) == 19
    assert len(SPCS2022_ZONES) == 19


def test_the_registry_offers_the_capture_s_zones_in_the_capture_s_order():
    """Order is a user-visible fact - it is the order a dropdown will offer."""
    assert [zone.code for zone in SPCS2022_ZONES] == [
        row[CODE] for row in MICHIGAN_ROWS
    ]


def test_every_michigan_angle_is_whole_minutes():
    """Anti-vacuousness for ``parse_dms``'s optional-seconds branch.

    If NGS ever publishes seconds for a Michigan zone this fails, and the
    parser's untested branch gets exercised deliberately rather than by
    surprise.
    """
    for row in MICHIGAN_ROWS:
        for key in (ORIGIN_LAT, ORIGIN_LON_EAST, ORIGIN_LON_WEST):
            assert '"' not in row[key], f"{row[CODE]} {key} = {row[key]!r}"


@pytest.mark.anchor
@pytest.mark.parametrize("zone", SPCS2022_ZONES, ids=ZONE_IDS)
def test_every_registry_field_matches_the_frozen_capture(zone: Zone):
    """The whole transcription, field by field, against NGS's own file.

    Every constant a coordinate depends on is here: the origin latitude and
    longitude, the origin scale, the skew azimuth where there is one, and both
    false origins. If any one of them were typed wrong, this fails - and it
    fails against the authority rather than against a second copy.
    """
    row = ROWS_BY_CODE[zone.code]
    definition = zone.definition

    # Identity, in NGS's own strings.
    assert zone.abbrev == row[ABBREV]
    assert zone.name == row[NAME]
    assert zone.frame.code == row[FRAME] == "NATRF2022"

    # The projection: NGS's word, and the record MCX dispatches on.
    assert type(definition) is DEFINITION_FOR_PROJ_TYPE[row[PROJ_TYPE]], (
        f"{zone.code} is {row[PROJ_TYPE]} in NGS's file but carries a "
        f"{type(definition).__name__}"
    )

    # Origin latitude. The record's name for it depends on the projection, so
    # it is read through the same accessor the extent is built from.
    assert origin_latitude(definition) == pytest.approx(
        parse_dms(row[ORIGIN_LAT]), abs=1e-12
    )

    # Origin longitude, from the WEST column, negated - and the file's own EAST
    # column checked to agree, which is a free cross-check on the sign.
    west = parse_dms(row[ORIGIN_LON_WEST])
    east = parse_dms(row[ORIGIN_LON_EAST])
    assert definition.lon_origin == pytest.approx(west, abs=1e-12)
    assert definition.lon_origin == pytest.approx(east - 360.0, abs=1e-12)
    assert definition.lon_origin < 0.0, "Michigan is west of Greenwich"

    # The origin scale factor. Each record names it for its own projection.
    published_scale = float(row[SCALE])
    if isinstance(definition, ObliqueMercatorCenterDef):
        assert definition.k_center == published_scale
    else:
        assert definition.k_origin == published_scale

    # The skew azimuth: published for the statewide OMC alone, blank elsewhere.
    if isinstance(definition, ObliqueMercatorCenterDef):
        assert definition.skew_azimuth == float(row[SKEW])
    else:
        assert row[SKEW] == "", f"{zone.code} publishes a skew azimuth"

    # False origins, in metres, exact.
    assert definition.northing_grid_origin == parse_number(row[FALSE_N_M])
    assert definition.easting_origin == parse_number(row[FALSE_E_M])


@pytest.mark.parametrize("row", MICHIGAN_ROWS, ids=[r[CODE] for r in MICHIGAN_ROWS])
def test_the_capture_s_two_false_origin_columns_agree(row):
    """metres / 0.3048 == international feet, exactly, on every Michigan zone.

    NGS's zone-information page gives the design reason: "Many grid origin
    metric values (false northings and eastings) have been updated such that the
    international foot values are exact whole numbers ... See section 6.f.v of
    the SPCS2022 Procedures." This checks the claim on the data rather than
    trusting the sentence, and it is what makes the ift column usable as a
    cross-check on the metric column MCX actually stores.
    """
    for metric_key, foot_key in ((FALSE_N_M, FALSE_N_IFT), (FALSE_E_M, FALSE_E_IFT)):
        metres = parse_number(row[metric_key])
        feet = parse_number(row[foot_key])
        assert metres / INTERNATIONAL_FEET.meters_per_unit == pytest.approx(
            feet, rel=1e-12
        )
        assert feet == float(int(feet)), "an exact whole number of ift"


def test_the_capture_publishes_no_us_survey_foot_column():
    """The evidence behind the 2022 unit restriction, stated on the data.

    Half of it: NGS defines no false origin in US survey feet for ANY zone in
    the file, not merely for Michigan's. (The other half is beta NCAT printing
    ``N/A`` for usft on every SPCS2022 zone - review/nsrs-n0/FINDINGS.md 1.4.)
    """
    columns = {key for row in _load_capture() for key in row}
    assert FALSE_N_IFT in columns and FALSE_E_IFT in columns
    assert not [key for key in columns if "usft" in key.lower()]
    assert not [key for key in columns if "survey" in key.lower()]


def test_ngs_calls_the_michigan_zones_statewide_and_multizone_complete():
    """The two ``Zone type`` values, and which zone is the statewide one.

    Not stored on the record - it would be a second representation of the fact
    the extent and the projection already carry - but checked, because the
    statewide zone is the only one whose extent this program supplies by hand.
    """
    statewide = [row[CODE] for row in MICHIGAN_ROWS if row[ZONE_TYPE] == "Statewide"]
    assert statewide == ["260001"]
    assert {row[ZONE_TYPE] for row in MICHIGAN_ROWS} == {
        "Statewide",
        "Multizone complete",
    }
    assert {row[DESIGN_BY] for row in MICHIGAN_ROWS} == {"NGS", "State"}


@pytest.mark.parametrize("zone", SPCS2022_ZONES, ids=ZONE_IDS)
def test_every_2022_citation_names_its_row_and_its_capture(zone: Zone):
    """A citation that does not identify the row is not a citation.

    **Both** captures must be named, with their digests and their dates, because
    a 2022 record carries facts from both - the defining constants a coordinate
    is computed from, and the bounds its warnings are measured against. It must
    also carry the ``NGS beta`` token the re-freeze mechanism looks for, so a
    reader of a sealed job record can re-fetch and compare rather than take any
    of it on trust.
    """
    citation = zone.citation
    assert f"row 'Zone code' {zone.code}" in citation
    assert "NGS beta" in citation
    assert "NOS NGS 13" in citation

    assert DEFINITIONS_SHA256 in citation
    assert "zoneDefinitions.json" in citation
    assert "2026-08-28" in citation

    assert BOUNDS_SHA256 in citation
    assert "zoneBounds.json" in citation
    assert "2026-08-29" in citation


# --------------------------------------------------------------------------
# 2. The registry's structural rules.
# --------------------------------------------------------------------------


def test_all_zones_is_the_two_eras_concatenated():
    assert ALL_ZONES == SPCS83_ZONES + SPCS2022_ZONES
    assert len(ALL_ZONES) == 22


def test_the_two_eras_do_not_overlap():
    assert not set(SPCS83_ZONES) & set(SPCS2022_ZONES)


def test_each_era_carries_its_own_frame_and_system_spelling():
    for zone in SPCS83_ZONES:
        assert zone.frame is NAD83_2011
        assert zone.system == "SPCS 83"
    for zone in SPCS2022_ZONES:
        assert zone.frame is NATRF2022
        assert zone.system == "SPCS2022"


def test_the_two_system_spellings_are_ngs_s_own_and_are_different():
    """"SPCS 83" has a space; "SPCS2022" does not. Both are NGS's.

    These strings reach an audit column and a job record, so the difference is
    a fact about the outputs and not a style choice.
    """
    assert {zone.system for zone in ALL_ZONES} == {"SPCS 83", "SPCS2022"}
    assert "SPCS 2022" not in {zone.system for zone in ALL_ZONES}


def test_every_zone_is_reachable_by_code():
    for zone in ALL_ZONES:
        assert zone_by_code(zone.code) is zone


def test_every_zone_is_hashable_and_all_twenty_two_are_distinct():
    """``projection.constants_for`` caches on the Zone itself.

    ``allowed_units`` is a tuple rather than a set or a list precisely so this
    keeps working; a list there would raise ``TypeError`` on the first
    conversion, and a set would be unordered in a control the user reads.
    """
    for zone in ALL_ZONES:
        hash(zone)
    assert len({hash(zone) for zone in ALL_ZONES}) == 22
    assert len(set(ALL_ZONES)) == 22


@pytest.mark.parametrize("field_name", ["code", "abbrev", "name"])
def test_the_uniqueness_check_fires_on_a_collision_in_each_field(field_name):
    """The import-time check, driven with a deliberate collision.

    Anti-vacuousness: without this the check could be a no-op and the registry
    would still import. One seed per field, because a check that only looked at
    codes would pass the abbreviation and name collisions silently - and those
    are the dangerous ones, since the abbreviation names output files and the
    name is what a job record prints.
    """
    real = zone_by_code("2113")
    other = zone_by_code("261018")
    import dataclasses

    clash = dataclasses.replace(other, **{field_name: getattr(real, field_name)})

    with pytest.raises(ZoneRegistryError) as raised:
        _check_zone_identifiers_are_unique((real, clash))

    message = str(raised.value)
    assert field_name in message
    assert getattr(real, field_name) in message
    # Both offenders are named. Their shared field cannot tell them apart -
    # that is the whole complaint - so the systems they belong to are what the
    # assertion checks: the message has to say WHICH two zones collided.
    assert real.system in message
    assert other.system in message


def test_the_uniqueness_check_accepts_the_real_registry():
    """It already ran at import; running it again states what passing means."""
    _check_zone_identifiers_are_unique(ALL_ZONES)


def test_no_two_zones_share_a_code_an_abbreviation_or_a_name():
    """The property itself, independent of the function that enforces it."""
    for field_name in ("code", "abbrev", "name"):
        values = [getattr(zone, field_name) for zone in ALL_ZONES]
        assert len(set(values)) == len(values), f"duplicate {field_name}"


def test_origin_latitude_refuses_a_definition_type_it_does_not_know():
    """Fails closed rather than returning a plausible latitude."""

    class _Unknown:
        lon_origin = -84.0

    with pytest.raises(TypeError) as raised:
        origin_latitude(_Unknown())  # type: ignore[arg-type]
    assert "_Unknown" in str(raised.value)


def test_origin_latitude_reads_each_record_s_own_field():
    """One accessor, three field names, no stored duplicate."""
    assert origin_latitude(
        LambertOneParallelDef(43.0, 1.0, -84.0, 0.0, 0.0)
    ) == 43.0
    assert origin_latitude(
        TransverseMercatorDef(41.0, -84.0, 1.0, 0.0, 0.0)
    ) == 41.0
    assert origin_latitude(
        ObliqueMercatorCenterDef(45.0, -86.0, -26.0, 0.9998, 0.0, 0.0)
    ) == 45.0
    assert origin_latitude(
        LambertTwoParallelDef(42.0, 44.0, 41.5, -84.0, 0.0, 0.0)
    ) == 41.5


# --------------------------------------------------------------------------
# 3. The two per-era policy fields.
# --------------------------------------------------------------------------


def test_spcs83_zones_offer_all_three_units():
    """Unchanged from every release before this one."""
    for zone in SPCS83_ZONES:
        assert zone.allowed_units == (INTERNATIONAL_FEET, US_SURVEY_FEET, METERS)


def test_spcs2022_zones_offer_metres_and_international_feet_only():
    """NGS defines no US-survey-foot coordinate on a 2022 zone.

    The evidence is checked two tests up (no usft column anywhere in NGS's
    file) and in review/nsrs-n0/FINDINGS.md 1.4 (beta NCAT prints ``N/A``).
    """
    for zone in SPCS2022_ZONES:
        assert zone.allowed_units == (INTERNATIONAL_FEET, METERS)
        assert US_SURVEY_FEET not in zone.allowed_units


def test_every_zone_offers_at_least_one_unit_and_michigan_s_legislated_one():
    """An empty offering would leave a job with no writable unit at all."""
    for zone in ALL_ZONES:
        assert zone.allowed_units
        assert INTERNATIONAL_FEET in zone.allowed_units


def test_spcs83_keeps_its_four_hundred_kilometre_easting_range():
    """The window moved from convert.py to the record; the number did not.

    Written at the call site as ``_spcs83_easting_range(8000000.0)`` and so on,
    which names each zone's false easting a second time - checked here against
    the definition record that holds it authoritatively, and again at import by
    ``_check_every_easting_range_brackets_its_false_easting``.
    """
    for zone in SPCS83_ZONES:
        origin = zone.definition.easting_origin
        assert zone.easting_range_m == (origin - 400000.0, origin + 400000.0)


@pytest.mark.parametrize("zone", SPCS2022_ZONES, ids=ZONE_IDS)
def test_every_2022_easting_range_is_ngs_s_published_range(zone: Zone):
    """NGS publishes the bounds; this program does not invent them.

    ``zoneBounds.json``'s ``Min easting (m)`` / ``Max easting (m)``, which NGS
    computed from each zone's projected polygon "outward to 100 m ...
    precision". Exact equality, because both sides are whole hundreds of metres.
    """
    row = BOUNDS_BY_CODE[zone.code]
    assert zone.easting_range_m == (
        parse_number(row[MIN_EASTING_M]),
        parse_number(row[MAX_EASTING_M]),
    )


def test_the_published_easting_ranges_are_not_all_the_same():
    """Anti-vacuousness: nineteen ranges, not one range repeated.

    Including the case that makes the range worth having over the false easting
    alone - 261009 Newaygo and 261010 Wexford are assigned the SAME false
    easting (1,638,300 m) and NGS still publishes them different ranges, so the
    check has information the defining constants do not carry.
    """
    ranges = [zone.easting_range_m for zone in SPCS2022_ZONES]
    assert len(set(ranges)) == 19

    newaygo = zone_by_code("261009")
    wexford = zone_by_code("261010")
    assert (
        newaygo.definition.easting_origin == wexford.definition.easting_origin
    )
    assert newaygo.easting_range_m != wexford.easting_range_m


@pytest.mark.parametrize("zone", ALL_ZONES, ids=[z.code for z in ALL_ZONES])
def test_the_easting_warning_is_silent_inside_the_range_and_fires_outside_it(
    zone: Zone,
):
    """The behaviour, at the function a job actually calls. Both eras.

    Inside: the two bounds themselves and the false easting, which is where a
    point on the central meridian lands. Outside: one metre past each bound, so
    the test is about the boundary rather than about a comfortable margin.
    """
    lowest, highest = zone.easting_range_m

    for easting in (lowest, highest, zone.definition.easting_origin):
        assert not easting_looks_wrong_for_zone(easting, zone)

    for easting in (lowest - 1.0, highest + 1.0):
        assert easting_looks_wrong_for_zone(easting, zone)


def test_a_coordinate_from_a_distant_zone_is_noticed_across_the_2022_zones():
    """What the check is FOR, stated on the 2022 zones as a whole.

    Selecting the wrong source zone is the most likely real-world mistake with
    this program. Take each zone's own false easting and offer it as every other
    zone's data: count how many of those 342 mistaken pairs the published ranges
    catch. Neighbouring zones overlap by design - NGS's polygons are drawn to
    abut - so the honest number is not 342, and it is asserted rather than
    described, both to prove the check does real work and to record exactly how
    much it does.
    """
    caught = missed = 0
    for source in SPCS2022_ZONES:
        for target in SPCS2022_ZONES:
            if source is target:
                continue
            if easting_looks_wrong_for_zone(
                source.definition.easting_origin, target
            ):
                caught += 1
            else:
                missed += 1

    assert caught + missed == 342
    # Measured: 309 of the 342 mistaken pairs are caught by the easting alone,
    # 33 are not. The misses are overlapping or adjacent zones, where no easting
    # could separate them and the extent warning is what remains. Before H2's
    # rework the number was 0 - the check was switched off for every 2022 zone.
    assert caught == 309
    assert missed == 33


def test_the_none_branch_still_switches_the_check_off():
    """A zone with no recorded range must warn about nothing, not about
    everything.

    No registry zone is in that state, so the branch is exercised on a
    hand-built record - the contract kept alive for the next authority that
    publishes a zone without bounds. It matters which way the branch fails: a
    missing range that warned on every point would train the user to ignore the
    warning that catches a real wrong-zone file.
    """
    import dataclasses

    boundless = dataclasses.replace(zone_by_code("2113"), easting_range_m=None)

    assert boundless.easting_range_m is None
    for easting in (0.0, 4_000_000.0, -9_999_999.0, 1e12):
        assert not easting_looks_wrong_for_zone(easting, boundless)


def test_the_import_check_refuses_a_range_that_misses_its_false_easting():
    """Anti-vacuousness for the import-time structural check, both branches."""
    import dataclasses

    south = zone_by_code("2113")

    displaced = dataclasses.replace(
        south, easting_range_m=(6_000_000.0, 6_800_000.0)
    )
    with pytest.raises(ZoneRegistryError) as raised:
        _check_every_easting_range_brackets_its_false_easting((displaced,))
    assert "does not contain" in str(raised.value)
    assert south.code in str(raised.value)

    transposed = dataclasses.replace(
        south, easting_range_m=(4_400_000.0, 3_600_000.0)
    )
    with pytest.raises(ZoneRegistryError) as raised:
        _check_every_easting_range_brackets_its_false_easting((transposed,))
    assert "increasing order" in str(raised.value)

    # And it accepts the registry as it stands - it already ran at import.
    _check_every_easting_range_brackets_its_false_easting(ALL_ZONES)


# --------------------------------------------------------------------------
# 4. The extents: NGS's published bounding boxes.
# --------------------------------------------------------------------------


@pytest.mark.anchor
@pytest.mark.parametrize("zone", SPCS2022_ZONES, ids=ZONE_IDS)
def test_every_2022_extent_is_ngs_s_published_bounding_box(zone: Zone):
    """The four extent fields, against ``zoneBounds.json``, exactly.

    NGS's page: the latitude and longitude bounds "were computed outward from
    the zone polygon to 0.01 degree precision using floor and ceiling
    functions". They are hundredths of a degree on both sides, so equality is
    checked to a tolerance well inside that quantization rather than to bit
    identity, which decimal-to-binary conversion does not promise.

    The EAST longitude column is checked too, against the west one reduced by
    360 - the same free cross-check on the sign that the definitions get.
    """
    row = BOUNDS_BY_CODE[zone.code]

    assert zone.lat_min == pytest.approx(float(row[MIN_LAT]), abs=1e-9)
    assert zone.lat_max == pytest.approx(float(row[MAX_LAT]), abs=1e-9)
    assert zone.lon_min == pytest.approx(float(row[MIN_LON_WEST]), abs=1e-9)
    assert zone.lon_max == pytest.approx(float(row[MAX_LON_WEST]), abs=1e-9)

    assert float(row[MIN_LON_EAST]) - 360.0 == pytest.approx(
        float(row[MIN_LON_WEST]), abs=1e-9
    )
    assert float(row[MAX_LON_EAST]) - 360.0 == pytest.approx(
        float(row[MAX_LON_WEST]), abs=1e-9
    )


def test_the_bounds_capture_covers_the_same_nineteen_zones_by_the_same_codes():
    """The two files are joined on ``Zone code``; that join is checked, not
    assumed.

    A per-zone citation names one row number for both captures, so if the two
    files disagreed about which code is which zone, every bound would be
    attributed to the wrong definition and the citation would be false.
    """
    assert [row[CODE] for row in MICHIGAN_BOUNDS] == [
        row[CODE] for row in MICHIGAN_ROWS
    ]
    for code, row in BOUNDS_BY_CODE.items():
        assert row[NAME] == ROWS_BY_CODE[code][NAME]
        assert row[ABBREV] == ROWS_BY_CODE[code][ABBREV]


def test_the_statewide_extent_is_the_widest_and_covers_the_state():
    """NGS's statewide bounding box contains all eighteen low-distortion ones.

    Not a tautology about this program's records - it is a property of NGS's
    own polygons, and it is the reason the statewide zone can be offered for a
    job anywhere in Michigan. The SPCS 83 extents, drawn independently from the
    counties each 1983 zone covers, are checked to agree within a tenth of a
    degree, which is the precision they were rounded to.
    """
    statewide = zone_by_code("260001")
    assert (
        statewide.lat_min,
        statewide.lat_max,
        statewide.lon_min,
        statewide.lon_max,
    ) == (41.69, 48.31, -90.42, -82.12)

    for zone in SPCS2022_ZONES:
        if zone is statewide:
            continue
        assert statewide.lat_min <= zone.lat_min
        assert statewide.lat_max >= zone.lat_max
        assert statewide.lon_min <= zone.lon_min
        assert statewide.lon_max >= zone.lon_max

    michigan_lat = (
        min(zone.lat_min for zone in SPCS83_ZONES),
        max(zone.lat_max for zone in SPCS83_ZONES),
    )
    assert michigan_lat == pytest.approx((41.6, 48.4), abs=0.11)


def test_five_2022_grid_origins_lie_outside_their_own_zone_extent():
    """A grid origin is not a place, and NGS's bounds say so outright.

    Detroit's zone is defined about 40 deg 12' N and Ann Arbor's about
    41 deg 18' N - both in Ohio, below the state line - while the zones NGS
    draws start at 41.72 and 41.69 N. Three more origins sit over Lake Michigan
    or Wisconsin.

    Recorded rather than smoothed over, because it is the fact that makes "the
    extent contains its own origin" a WRONG invariant to assert - and because
    the disclosed envelope H2 first shipped was built outward FROM each origin,
    which is exactly why it put Detroit's zone extent in Ohio and left two of
    its corners off the south edge of the GEOID18 tile. NGS's polygons do not
    have that problem, and this test is the reason why in one line.

    Pinned as a set: an origin joining or leaving this list fails the test.
    """
    outside = {
        zone.code
        for zone in SPCS2022_ZONES
        if not (
            zone.lat_min <= origin_latitude(zone.definition) <= zone.lat_max
            and zone.lon_min <= zone.definition.lon_origin <= zone.lon_max
        )
    }
    assert outside == {"261001", "261002", "261014", "261015", "261016"}


@pytest.mark.parametrize("zone", ALL_ZONES, ids=[z.code for z in ALL_ZONES])
def test_every_extent_is_ordered_and_finite(zone: Zone):
    """A transposed pair would warn on every point instead of on none."""
    assert zone.lat_min < zone.lat_max
    assert zone.lon_min < zone.lon_max
    assert all(
        math.isfinite(value)
        for value in (zone.lat_min, zone.lat_max, zone.lon_min, zone.lon_max)
    )
