"""The job record - the plain-text file that explains the exports.

The owner chose "full record, but factors summarized": everything about how the
conversion was performed, with per-point scale factors left to the audit CSV
rather than duplicated here. So this document carries what the CSV cannot -
provenance, settings, citations, summary statistics, and every warning - and
points at the CSV for the per-point detail.

It is written to be readable in Notepad by a surveyor who did not run the
conversion, six months later.
"""

from __future__ import annotations

import statistics
import textwrap
from datetime import date, datetime, timezone

from michspc import APP_NAME, __version__
from michspc.fileio import formatting as fmt
from michspc.fileio import vertcon
from michspc.fileio.exports import external_frame as _external_frame
from michspc.fileio.exports import pivot_frame as _pivot_frame
from michspc.fileio.geoid import geoid_model_by_name
from michspc.job import (
    Direction,
    JobResult,
    applied_frame_transformation,
    factors_geoid_model,
    factors_use_source_era,
    geoid_swap_models,
    is_zoneless,
)
from michspc.spc import htdp, htdp_data
from michspc.spc.convert import HeightConvention, WarningCode
from michspc.spc.factors import MEAN_EARTH_RADIUS_M
from michspc.spc.projection import constants_for
from michspc.spc.vertical import HeightKind, require_vertical_pair
from michspc.spc.zones import (
    SPCS2022_BOUNDS_CAPTURED,
    SPCS2022_BOUNDS_FILENAME,
    SPCS2022_BOUNDS_SHA256,
    SPCS2022_DEFINITIONS_CAPTURED,
    SPCS2022_DEFINITIONS_FILENAME,
    SPCS2022_DEFINITIONS_SHA256,
    SPCS2022_POLICY_CITATION,
    SPCS2022_ZONES,
    LambertOneParallelDef,
    LambertTwoParallelDef,
    ObliqueMercatorCenterDef,
    ProjectionKind,
    TransverseMercatorDef,
)

_RULE = "=" * 78
_THIN = "-" * 78

_WARNING_HEADINGS = {
    WarningCode.EASTING_UNLIKE_SELECTED_ZONE: (
        "COORDINATES MAY NOT BE IN THE SELECTED SOURCE ZONE"
    ),
    WarningCode.OUTSIDE_ZONE_EXTENT: "POINTS OUTSIDE THE TARGET ZONE'S AREA",
    WarningCode.GEOID_UNAVAILABLE: (
        "ELEVATION RECORDED, BUT NO GEOID HEIGHT AT THIS POSITION"
    ),
    # The two vertical codes fire only on a HORIZONTAL_AND_VERTICAL job, so
    # giving them headings here changes no horizontal record by a byte.
    WarningCode.VERTICAL_SHIFT_UNAVAILABLE: (
        "ELEVATION RECORDED, BUT NOT CONVERTIBLE BETWEEN VERTICAL DATUMS"
    ),
    WarningCode.VERTICAL_SIGMA_UNAVAILABLE: (
        "SHIFT APPLIED, BUT NO UNCERTAINTY COULD BE STATED FOR IT"
    ),
    # Fires only on a geoid-to-geoid job, so this heading changes no
    # pre-existing record by a byte.
    WarningCode.GEOID_SWAP_UNAVAILABLE: (
        "ELEVATION RECORDED, BUT NOT CONVERTIBLE BETWEEN GEOID MODELS"
    ),
    # A JOB-level warning (JobResult.job_warnings), raised only on a job in a
    # WGS 84 realization, so this heading changes no pre-existing record.
    WarningCode.REALIZATION_OUTSIDE_PERIOD_OF_USE: (
        "POSITIONS DATED OUTSIDE THEIR REALIZATION'S PERIOD OF USE"
    ),
}
"""Readable headings for the warning kinds this program currently raises.

Presentation only. It does NOT decide which warnings are printed - see
``_warning_codes_present``. A heading missing from this table changes how a
warning is introduced, never whether the surveyor is shown it.
"""


def _warning_codes_present(result: JobResult) -> list:
    """Every warning code this job actually raised, in the order to print.

    Driven by the warnings, not by ``_WARNING_HEADINGS``. Iterating the heading
    table instead would mean a warning kind added later, before anyone wrote it
    a heading, was counted in the "N warning(s)" total at the top of the section
    and then never printed underneath it - the report telling the surveyor that
    something is wrong and declining to say what. Latent rather than live today,
    because both current codes have headings; structural, because the next code
    added would activate it silently.

    Known kinds keep their declared order so the section reads the same way from
    job to job; anything unheaded follows, in the order it first appeared.
    """
    raised = []
    for _point_id, warning in result.warnings:
        if warning.code not in raised:
            raised.append(warning.code)

    known = [code for code in _WARNING_HEADINGS if code in raised]
    return known + [code for code in raised if code not in _WARNING_HEADINGS]


def _warning_heading(code) -> str:
    """A heading for a code, falling back to the code itself.

    The fallback is deliberately the raw code text rather than something
    generic like "OTHER": a surveyor reading an unfamiliar heading can search
    for it, and it is honest about being unpolished.
    """
    registered = _WARNING_HEADINGS.get(code)
    if registered is not None:
        return registered
    return str(getattr(code, "value", code)).replace("-", " ").replace("_", " ").upper()


def _input_format_block(settings) -> list[str]:
    """What the input file's five columns actually held, and in what units.

    Direction-aware, because the input is not always PNEZD. When a job starts
    from geodetic positions, columns two and three are a latitude and a
    longitude in decimal degrees - not a northing and an easting in the linear
    unit - and this block used to say otherwise in a document that is signed,
    filed and believed.

    That is the same confusion docs/DESIGN.md amendment #16 note 1 called "a
    correctness aid, not cosmetics" for the input hint on screen: the two
    layouts are indistinguishable from the numbers, because a geodetic file
    read as PNEZD yields a plausible coordinate rather than an error. The
    record has to describe the file that was actually read.

    The longitude sign convention is stated here as well as on the OUTPUT
    section's "Longitude" line. It is not a duplicate for its own sake: a
    reader who takes columns two and three as latitude and longitude has still
    not been told which way west is signed, and the two readings are 340 miles
    apart (docs/DESIGN.md section 7). The description of the file cannot be
    read without it.
    """
    unit = settings.input_unit
    geodetic_input = settings.direction in (
        Direction.GEODETIC_TO_ZONE,
        Direction.GEODETIC_TO_GEODETIC,
    ) or (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is None
    )
    if geodetic_input:
        return [
            "Format             Comma separated, no header row - NOT PNEZD",
            "                   point, latitude, longitude, elevation, description",
            "                   description is everything after the fourth comma",
            "                   Columns two and three are DECIMAL DEGREES, read",
            f"                   as {settings.longitude_convention.value}.",
            f"Units in           {unit.name} ({unit.code}) - the ELEVATION column only",
            "                   Columns two and three are degrees and carry no",
            "                   linear unit.",
            f"                   {unit.citation}",
        ]
    return [
        "Format             PNEZD, no header row",
        "                   point, northing, easting, elevation, description",
        "                   description is everything after the fourth comma",
        f"Units in           {unit.name} ({unit.code}) - northing, easting and elevation",
        f"                   {unit.citation}",
    ]


def _clean_export_block(settings, path=None) -> list[str]:
    """What the clean export's five columns hold. Direction-aware.

    ``path`` is the job's frame transformation, or None when none ran
    (``job.applied_frame_transformation``). On a job converting TO geodetic
    across one, the block names the frame the written positions are in; on a
    same-frame job it is byte-identical to what it always printed.

    "in the same PNEZD layout as the input" is true only of a zone-to-zone job.
    Converting TO geodetic writes a latitude and a longitude in columns two and
    three; converting FROM geodetic writes PNEZD out of a file that was never
    PNEZD going in. In both cases the old sentence described a file that is not
    on the disk, and this record is the only documentation the program produces
    (docs/DESIGN.md amendment #13).
    """
    unit = settings.output_unit
    if settings.direction is Direction.VERTICAL_ONLY:
        if settings.source_zone is None:
            return [
                "    The input reproduced with ONLY the elevation converted - the",
                "    same layout as the input: point, latitude, longitude,",
                "    elevation, description, no header row.",
                "    Columns two and three are DECIMAL DEGREES to 8 places -",
                "    exactly the positions the input supplied, unconverted, in",
                "    the input's own sign convention.",
                f"    The elevation column is {unit.name} ({unit.code}), in the",
                "    TARGET vertical datum named above.",
                "    Nothing else.",
            ]
        return [
            "    The input reproduced with ONLY the elevation converted - the",
            "    same PNEZD layout as the input: point, northing, easting,",
            "    elevation, description, no header row.",
            f"    Northing and easting are the INPUT coordinates, {unit.name}",
            f"    ({unit.code}), unconverted; the elevation column is the",
            "    converted height, in the TARGET vertical datum named above.",
            "    Nothing else. Extract this one and import it into CAD.",
        ]
    if settings.direction is Direction.GEODETIC_TO_GEODETIC:
        # Plan decision D7: always across a frame transformation, so the
        # frame of the written positions is always stated.
        return [
            "    The converted positions - NOT PNEZD, but the same layout as the",
            "    input: point, latitude, longitude, elevation, description, no",
            "    header row.",
            "    Columns two and three are DECIMAL DEGREES to 8 places, written",
            f"    {settings.longitude_convention.value}, and are positions in "
            f"{path.target.code}.",
            f"    The elevation column is {unit.name} ({unit.code}).",
            "    Nothing else.",
        ]
    if settings.direction is Direction.ZONE_TO_GEODETIC:
        block = [
            "    The converted positions - NOT PNEZD, and NOT the same layout as",
            "    the input: point, latitude, longitude, elevation, description,",
            "    no header row.",
            "    Columns two and three are DECIMAL DEGREES to 8 places, written",
            f"    {settings.longitude_convention.value}.",
            f"    The elevation column is {unit.name} ({unit.code}).",
            "    Nothing else.",
        ]
        if path is not None:
            # After the convention line: which frame those degrees are in,
            # the one thing a WGS 84 target adds to this file's meaning.
            block[5:5] = [
                f"    They are positions in {path.target.code}, not in the zone's",
                f"    {path.source.code} (see FRAME TRANSFORMATION).",
            ]
        return block
    if settings.direction is Direction.GEODETIC_TO_ZONE:
        opening = [
            "    The converted coordinates in PNEZD layout - which the INPUT file",
            "    was not: point, northing, easting, elevation, description, no",
            "    header row.",
        ]
    else:
        opening = [
            "    The converted coordinates, in the same PNEZD layout as the input:",
            "    point, northing, easting, elevation, description - no header row.",
        ]
    return opening + [
        f"    Northing, easting and elevation are {unit.name} ({unit.code}).",
        "    Nothing else. Extract this one and import it into CAD.",
    ]


_HEADING_LABEL_WIDTH = 26
"""The column the zone block's two heading lines put their value in.

"Reference frame" plus its padding, and "Projection" plus its padding, both
reach column 28 counting the two-space indent. Two widths in one block is not
tidy, but it is what this record has printed since 0.1.0 and every SPCS 83
record ever written is held to it byte for byte.
"""

_CONSTANT_LABEL_WIDTH = 28
"""The column the zone block's defining and derived constants line up in.

Two columns further right than the headings above, again because that is what
was printed before this block learned about a second era.
"""


def _zone_heading(label: str, value: str) -> str:
    """One of the zone block's two heading lines - frame, projection."""
    return f"  {label:<{_HEADING_LABEL_WIDTH}}{value}"


def _constant(label: str, value: str) -> str:
    """One defining or derived constant, in the block's own column."""
    return f"  {label:<{_CONSTANT_LABEL_WIDTH}}{value}"


def _degrees_north(value: float) -> str:
    """A latitude, in the block's house format."""
    return f"{value:.10f} deg N"


def _meters(value: float) -> str:
    """A false coordinate, in the block's house format."""
    return f"{value:,.4f} m"


def _central_meridian(longitude: float) -> str:
    """A central longitude, signed as this codebase carries it and glossed west.

    The gloss is not decoration: every published table this program was
    transcribed from prints these positive-west, and a reader checking the
    record against NGS has to be able to see the same number they are holding
    (docs/DESIGN.md section 7).
    """
    return f"{longitude:.10f} deg ({-longitude:.10f} deg west)"


def _projection_lines(kind: ProjectionKind) -> list[str]:
    """The "Projection" heading, wrapped under itself if the name is long.

    ``LAMBERT_CONIC_2SP``'s name fits on one line and the line is byte-identical
    to the one this record has always printed; ``LAMBERT_CONIC_1SP``'s does not
    fit, and the record is read in Notepad at 78 columns.
    """
    width = 78 - 2 - _HEADING_LABEL_WIDTH
    wrapped = textwrap.wrap(kind.value, width=width, break_long_words=False) or [""]
    lines = [_zone_heading("Projection", wrapped[0])]
    lines.extend(
        f"{'':<{2 + _HEADING_LABEL_WIDTH}}{line}" for line in wrapped[1:]
    )
    return lines


def _lambert_two_parallel_constants(zone) -> list[str]:
    """SPCS 83's form: two standard parallels, and a derived central parallel.

    Byte-identical to what this record has printed since 0.1.0, and pinned as
    literal text: every sealed SPCS 83 job in existence describes its zones in
    these words, and a second era arriving in this function must not restate
    them differently.
    """
    definition = zone.definition
    constants = constants_for(zone)
    return [
        _constant("Southern standard parallel", _degrees_north(definition.lat_south)),
        _constant("Northern standard parallel", _degrees_north(definition.lat_north)),
        _constant(
            "Latitude of grid origin", _degrees_north(definition.lat_grid_origin)
        ),
        _constant("Central meridian", _central_meridian(definition.lon_origin)),
        _constant("False northing", _meters(definition.northing_grid_origin)),
        _constant("False easting", _meters(definition.easting_origin)),
        _constant("Central parallel (derived)", _degrees_north(constants.lat_origin)),
        _constant("Scale at central parallel", f"{constants.k_origin:.12f}"),
    ]


def _lambert_one_parallel_constants(zone) -> list[str]:
    """SPCS2022's LC1 form: the central parallel and its scale are PUBLISHED.

    Both carry "(defining)", because on the two-parallel block above the same
    two quantities are labelled "(derived)" - a reader who knows one form has
    to be able to tell which they are looking at, and presenting a published
    constant as something this program computed would misstate where the number
    came from.

    The grid origin is stated too, and stated as the central parallel, because
    that is the LC1 fact a reader most needs: the false northing is assigned at
    phi_0 itself, so there is no separate origin latitude to look for
    (michspc.spc.zones.LambertOneParallelDef).
    """
    definition = zone.definition
    return [
        _constant(
            "Central parallel",
            f"{_degrees_north(definition.lat_origin)} (defining)",
        ),
        _constant(
            "Scale on central parallel", f"{definition.k_origin:.12f} (defining)"
        ),
        _constant(
            "Latitude of grid origin",
            f"{_degrees_north(definition.lat_origin)} (the central parallel)",
        ),
        _constant("Central meridian", _central_meridian(definition.lon_origin)),
        _constant("False northing", _meters(definition.northing_grid_origin)),
        _constant("False easting", _meters(definition.easting_origin)),
    ]


def _transverse_mercator_constants(zone) -> list[str]:
    """SPCS2022's TM form.

    phi_0 here is the GRID ORIGIN latitude, not a standard parallel, and the
    label says so: a transverse Mercator has no standard parallel at all, and
    the scale is defined on the central meridian instead (manual section 3.2,
    michspc.spc.zones.TransverseMercatorDef).
    """
    definition = zone.definition
    return [
        _constant(
            "Latitude of grid origin", _degrees_north(definition.lat_grid_origin)
        ),
        _constant("Central meridian", _central_meridian(definition.lon_origin)),
        _constant(
            "Scale on central meridian", f"{definition.k_origin:.12f} (defining)"
        ),
        _constant("False northing", _meters(definition.northing_grid_origin)),
        _constant("False easting", _meters(definition.easting_origin)),
    ]


def _oblique_mercator_constants(zone) -> list[str]:
    """SPCS2022's OMC form - false coordinates AT THE PROJECTION CENTRE.

    The variant is stated on the false northing and easting lines rather than
    left to be assumed, because the natural-origin Hotine assigns the same two
    numbers somewhere else entirely - for Alaska zone 1 the manual's own
    equations put the centre 6,968,872 m from the false northing - so "false
    northing" alone does not identify the quantity (michspc.spc.zones.
    ObliqueMercatorCenterDef, and DESIGN.md #61).

    The skew azimuth is signed and is NOT a longitude, so it is printed exactly
    as NGS publishes it, with the sense of the angle named.
    """
    definition = zone.definition
    return [
        _constant("Latitude of centre", _degrees_north(definition.lat_center)),
        _constant("Longitude of centre", _central_meridian(definition.lon_center)),
        _constant(
            "Skew azimuth",
            f"{definition.skew_azimuth:.10f} deg (clockwise from north)",
        ),
        _constant(
            "Scale at projection centre", f"{definition.k_center:.12f} (defining)"
        ),
        _constant(
            "False northing",
            f"{_meters(definition.northing_center)} at the projection centre",
        ),
        _constant(
            "False easting",
            f"{_meters(definition.easting_center)} at the projection centre",
        ),
    ]


_ZONE_CONSTANT_BLOCKS = {
    LambertTwoParallelDef: _lambert_two_parallel_constants,
    LambertOneParallelDef: _lambert_one_parallel_constants,
    TransverseMercatorDef: _transverse_mercator_constants,
    ObliqueMercatorCenterDef: _oblique_mercator_constants,
}
"""THE table that turns a definition record into the lines describing it.

Keyed on the record's type, exactly as ``michspc.spc.projection``'s engine
table is, and for the same reason: a fifth projection that can be COMPUTED but
not DESCRIBED must refuse rather than be described with another projection's
field names. Every field name below belongs to one projection only - a
transverse Mercator has no standard parallel, an oblique Mercator's false
coordinates are not at a grid origin - so a wrong block here is a record that
misdescribes a sealed job in plausible words.
"""


_SOURCE_PREFIX = "  Source: "

_UNWRAPPED_SOURCE_DEFINITIONS = (LambertTwoParallelDef,)
"""Definition types whose citation is printed whole, on one line.

FROZEN HISTORY, not a style choice. The SPCS 83 citation is 78 characters and
its line is 88, over the record's 78-column width, and it has been printed that
way in every sealed job since 0.1.0 - so it stays, byte for byte.

Every other kind wraps. A 2022 citation names two NGS captures with their URLs,
byte counts, dates and SHA-256 digests: about 700 characters, which on one line
is a horizontal scroll in the Notepad this document is written to be read in.
The line is per kind because the block already is; nothing shared changes.
"""


def _source_lines(zone) -> list[str]:
    """The zone's citation, whole or wrapped under itself.

    ``break_on_hyphens=False`` and ``break_long_words=False`` for the reason
    ``_labelled_paragraph`` carries them: a citation holds URLs and repository
    paths (``review/nsrs-n0/raw/zoneBounds.json``), and a URL or a path broken
    across a line in a sealed record is a wrong URL or a wrong path.
    """
    if type(zone.definition) in _UNWRAPPED_SOURCE_DEFINITIONS:
        return [f"{_SOURCE_PREFIX}{zone.citation}"]
    return textwrap.wrap(
        zone.citation,
        width=78,
        initial_indent=_SOURCE_PREFIX,
        subsequent_indent=" " * len(_SOURCE_PREFIX),
        break_long_words=False,
        break_on_hyphens=False,
    ) or [_SOURCE_PREFIX.rstrip()]


class ZoneBlockUnavailableError(ValueError):
    """No description is registered for this kind of zone definition.

    The ``ProjectionUnavailableError`` voice, in the document layer. This
    record is what a surveyor defends a sealed survey with; a zone it cannot
    describe is a zone it must not write about.
    """


def _zone_block(zone, label: str) -> list[str]:
    """A zone's full defining and derived constants, with citations.

    Per projection kind, dispatched on the definition record's type. The two
    heading lines and the citation are common to every kind; what a zone's
    constants ARE is not, and this block used to print the two-parallel Lambert
    field names over whatever it was handed - which raised ``AttributeError``
    on a one-parallel zone AFTER the coordinates had been computed, and would
    have printed a plausible, wrong block for any definition that happened to
    carry the same field names (docs/DESIGN.md amendment #21).
    """
    render = _ZONE_CONSTANT_BLOCKS.get(type(zone.definition))
    if render is None:
        described = ", ".join(
            record.__name__ for record in _ZONE_CONSTANT_BLOCKS
        )
        raise ZoneBlockUnavailableError(
            f"This job record cannot describe {zone.name} (zone {zone.code}, "
            f"{zone.system}): no block is registered for a zone definition of "
            f"type {type(zone.definition).__name__}. Every projection is "
            f"defined by different constants - a transverse Mercator has no "
            f"standard parallel, and an oblique Mercator's false coordinates "
            f"are at its centre rather than at a grid origin - so describing "
            f"this zone with another projection's field names would put a "
            f"plausible falsehood into a sealed record. The definitions this "
            f"record can describe are: {described}."
        )
    lines = [
        f"{label}: {zone.name}, zone {zone.code} ({zone.system})",
        _zone_heading("Reference frame", zone.frame.code),
    ]
    lines.extend(_projection_lines(zone.projection_kind))
    lines.extend(render(zone))
    lines.extend(_source_lines(zone))
    return lines


_LABEL_WIDTH = 19
"""The record's label column: "File               " is 19 characters, and every
labelled line in this document starts the same way."""


def _labelled_paragraph(label: str, text: str) -> list[str]:
    """A labelled line whose text wraps under itself, record-style.

    The registry's ``direction_statement``, ``uncertainty_citation`` and
    ``caveat`` are single authoritative sentences longer than a line, and they
    must be QUOTED - re-drafting them here would create a second account of
    what was done to a height, which is the drift ``direction_statement``
    exists to make impossible. So the sentence is wrapped, never reworded:
    the words and their order are the record's exactly.
    """
    # break_long_words=False: a URL in a quoted citation must never be
    # snapped mid-token by the wrapper - a broken URL in a sealed record is
    # a wrong URL (WP-V7 review gate, LOW 3).
    body = (
        textwrap.wrap(
            text,
            width=78 - _LABEL_WIDTH,
            break_long_words=False,
            break_on_hyphens=False,
        )
        or [""]
    )
    lines = [f"{label:<{_LABEL_WIDTH}}{body[0]}"]
    lines.extend(f"{'':<{_LABEL_WIDTH}}{line}" for line in body[1:])
    return lines


def _vertical_method_block(
    settings, transformation, result, *, zoneless: bool
) -> list[str]:
    """The METHOD section's account of the vertical transformation.

    ``zoneless`` is ``build_report``'s one flag for a job with no State Plane
    zone at either end, passed in rather than re-derived, so the Factor height
    paragraph cannot name a combined factor on a job that has none by a rule
    of its own (interim gate 2 of the WGS 84 build, finding H2).

    Everything quotable is quoted from the registry record (``spc/vertical``),
    which derives its words from the same ``sign`` the computation multiplies
    by - so this document and the arithmetic cannot disagree about direction.
    The grid filenames and digests are the ``fileio/vertcon`` constants the
    loader itself authenticates against, for the same reason.
    """
    lines: list[str] = []
    add = lines.append

    add("VERTICAL DATUM TRANSFORMATION")
    add("")
    lines.extend(_labelled_paragraph("Direction", transformation.direction_statement))
    if not transformation.is_identity:
        add(
            f"Model              {transformation.model} "
            f"release {transformation.release}"
        )
        # Both grids, each with its own digest: the shift and its uncertainty
        # come from two different files, and a record that named one would
        # certify half of what was read (plan section 5.2).
        add(f"Grids              {vertcon.VERTCON3_TRN_FILENAME}")
        add(f"                   SHA-256 {vertcon.VERTCON3_TRN_SHA256}")
        add(f"                   {vertcon.VERTCON3_ERR_FILENAME}")
        add(f"                   SHA-256 {vertcon.VERTCON3_ERR_SHA256}")
    lines.extend(
        _labelled_paragraph("Uncertainty", transformation.uncertainty_citation)
    )
    lines.extend(_labelled_paragraph("Caveat", transformation.caveat))
    if not transformation.is_identity:
        # The half-cell discontinuity, DESIGN.md #38: a property of NOAA's own
        # algorithm, carried in deliberately because NOAA is the authority,
        # and disclosed here because a job whose points straddle such a line
        # shows the step with nothing else to explain it.
        add("")
        lines.extend(
            _labelled_paragraph(
                "Interpolation",
                "The grid is interpolated the way NOAA's own published "
                "VERTCON software interpolates it: a 3x3 stencil centred on "
                "the nearest grid node. That scheme steps at half-cell lines "
                "- odd multiples of 0.025 degrees, exactly the round "
                "coordinate values surveyors type - and the modeled shift "
                "jumps there, by up to about 76 mm in Michigan. NGS NCAT "
                "reproduces the same steps, because it runs the same "
                "algorithm. Two points a fraction of a millimetre apart "
                "across such a line can therefore carry visibly different "
                "shifts, and that is the model's own behaviour, not an "
                "error in either point.",
            )
        )
    if (
        # The one shared statement of the era rule - job.factors_use_source_era
        # is what the computation itself branches on, so this sentence and the
        # arithmetic cannot drift apart (WP-V7 review gate, LOW 2).
        factors_use_source_era(settings, transformation)
        # ...and only when at least one point actually HAS factors: "were
        # computed from" is a claim about work done, and a job whose every
        # point was blank-Z or coverage-refused did none of it - the record
        # asserted it anyway (WP-V7 review gate, MEDIUM 3).
        and any(p.factors.elevation_factor is not None for p in result.points)
    ):
        # The #41 rule - now the per-side pairing's consequence - said out
        # loud: this is the one configuration where the factors do NOT use
        # the height the Z column carries, and a record that did not say
        # which height the factors came from would leave the audit CSV's
        # "how was this derived" question half answered. The model named is
        # the one the factors actually read (factors_geoid_model) - for
        # every #41-era call shape that is settings.geoid_model itself, and
        # for the per-side shape it is the input-side model, which is the
        # only model such a job has.
        factor_model = factors_geoid_model(settings, transformation)
        # A job with no zone has no grid scale factor and so no combined
        # factor - its SCALE FACTOR SUMMARY says exactly that - so the
        # paragraph names only the factor that exists, in the words W4b gave
        # the ELLIPSOID HEIGHT block and ELEVATIONS. Until interim gate 2
        # (H2) it said "The elevation and combined factors were computed"
        # here on every job, zone-less ones included, since #41.
        factors = (
            "The elevation factor was"
            if zoneless
            else "The elevation and combined factors were"
        )
        add("")
        lines.extend(
            _labelled_paragraph(
                "Factor height",
                f"{factors} computed from the "
                f"SOURCE-datum ({transformation.source.code}) height, not "
                f"from the shifted height the Z column carries. The "
                f"{factor_model.name} separations are defined "
                f"against {factor_model.vertical_datum.code} "
                f"heights, and combining a separation with a height from a "
                f"different era would mix two eras inside one number "
                f"(DESIGN.md #32, #41). The Z column carries the shifted, "
                f"{transformation.target.code} height wherever one was "
                f"written.",
            )
        )
    add("")
    return lines


def _ellipsoid_height_method_block(settings, model_name, path=None) -> list[str]:
    """The METHOD section's account of an ellipsoid-height input.

    ``path`` is the job's frame transformation, or None (``job.
    applied_frame_transformation``). Across one, three sentences of the
    same-frame account stop being true, and each is restated from the path's
    own frames (work package W4 of the WGS 84 build, plan decision D6): the
    supplied heights are above THEIR frame's ellipsoid, which for a WGS 84
    realization is not GRS 80; the h in H = h - N is the NAD 83 height, the
    supplied one carried there by the transformation when it was supplied in
    another frame, because the geoid models publish N against NAD 83; and a
    horizontal job's Z column carries the height transformed with the
    position, not the height exactly as supplied. On a same-frame job every
    line is byte-identical to what it always printed.

    Facts only, in ``_geoid_swap_method_block``'s shape and under the same
    standing instruction (the owner's, 2026-08-09, #33/#34/#45 extended to the
    written record): the model with its tile filename and digest resolved from
    the registry, the arithmetic, and the datum the derived heights are in.

    The mode paragraph is the load-bearing one, because the two modes do
    different things with the same conversion and the difference is invisible
    in the numbers alone: horizontal mode writes the Z column back exactly as
    supplied and uses the derived height only for the factors, while the
    vertical modes write the derived height. A reader holding only the clean
    export needs the record to say which of those produced it.
    """
    record = geoid_model_by_name(model_name)
    lines: list[str] = []
    add = lines.append

    add("ELLIPSOID HEIGHT CONVERSION")
    add("")
    if path is None:
        add(
            f"Input heights      stated as ELLIPSOID heights (above the GRS 80 "
            f"ellipsoid),"
        )
        add("                   as a GNSS receiver produces them.")
    else:
        lines.extend(
            _labelled_paragraph(
                "Input heights",
                f"stated as ELLIPSOID heights in {path.source.code} (above the "
                f"{path.source.ellipsoid_name} ellipsoid), as a GNSS receiver "
                f"produces them.",
            )
        )
    add(
        f"Geoid model        {record.name}, NGS grid tile "
        f"{record.tile_filename}"
    )
    add(f"                   SHA-256 {record.sha256}")
    if path is None:
        which_h = "h is the height the Z column supplied"
    else:
        # The NAD 83 h, always (plan D6, PointConversion.pivot_ellipsoid_height):
        # the supplied height itself when it was supplied in NAD 83, else the
        # supplied height carried there with the position.
        pivot = _pivot_frame(path).code
        which_h = (
            f"h is the {pivot} ellipsoid height (the height the Z column "
            f"supplied in {path.source.code}, transformed with the position "
            f"to {pivot}: {record.name} publishes N against {pivot})"
            if path.source.is_time_dependent
            else f"h is the {pivot} ellipsoid height the Z column supplied"
        )
    lines.extend(
        _labelled_paragraph(
            "Arithmetic",
            f"The orthometric height is derived at each point's own "
            f"horizontal position: H = h - N, where {which_h} and N is the "
            f"{record.name} geoid height there, "
            f"in metres. N is negative throughout Michigan, so H is the "
            f"LARGER number - about 34 m larger. The derived heights are in "
            f"{record.vertical_datum.code}, the datum {record.name} publishes "
            f"separations for; an ellipsoid height is in no vertical datum "
            f"itself.",
        )
    )
    if settings.vertical_mode.converts_elevations:
        lines.extend(
            _labelled_paragraph(
                "This job",
                "converts the elevations, so the Z column of every export "
                "carries the derived orthometric height, after any vertical "
                "datum shift stated below.",
            )
        )
    elif path is None:
        lines.extend(
            _labelled_paragraph(
                "This job",
                "is horizontal, so the Z column of every export carries the "
                "ELLIPSOID HEIGHT EXACTLY AS SUPPLIED, re-expressed into the "
                "output unit and otherwise unchanged. The derived orthometric "
                "height was used only to compute the elevation and combined "
                "factors, which is what it is for: the elevation factor is "
                "R / (R + H + N), so supplying h where H is expected would "
                "add the geoid separation to a height that already contains "
                "it.",
            )
        )
    else:
        # Plan decision D6: horizontal mode still never turns the height into
        # an elevation, but the height is part of the position, so its frame
        # changes with the job's. A geodetic-to-geodetic job has no zone and
        # so no combined factor.
        factors = (
            "the elevation factor"
            if settings.direction is Direction.GEODETIC_TO_GEODETIC
            else "the elevation and combined factors"
        )
        lines.extend(
            _labelled_paragraph(
                "This job",
                f"is horizontal, so the Z column of every export carries the "
                f"ELLIPSOID HEIGHT in {path.target.code}: the height the file "
                f"supplied in {path.source.code}, transformed with the "
                f"position (see FRAME TRANSFORMATION), re-expressed into the "
                f"output unit, and not converted to an elevation. The derived "
                f"orthometric height was used only to compute {factors}, "
                f"which is what it is for: the elevation factor is "
                f"R / (R + H + N), so supplying h where H is expected would "
                f"add the geoid separation to a height that already contains "
                f"it.",
            )
        )
    add("")
    return lines


def _geoid_swap_method_block(swap_models) -> list[str]:
    """The METHOD section's account of a geoid-to-geoid conversion.

    Facts only, stated plainly (the owner's instruction, 2026-08-09, the
    #33/#34/#45 ruling extended to the written record): the two models with
    their tile filenames and digests resolved from the registry - the same
    records the loader authenticates against - and the arithmetic. No
    caveat prose and no uncertainty lecture; the sigma surfaces simply read
    N/A.
    """
    source_record = geoid_model_by_name(swap_models[0].name)
    target_record = geoid_model_by_name(swap_models[1].name)
    lines: list[str] = []
    add = lines.append

    add("GEOID CHANGE")
    add("")
    add(
        f"Input geoid        {source_record.name}, NGS grid tile "
        f"{source_record.tile_filename}"
    )
    add(f"                   SHA-256 {source_record.sha256}")
    add(
        f"Output geoid       {target_record.name}, NGS grid tile "
        f"{target_record.tile_filename}"
    )
    add(f"                   SHA-256 {target_record.sha256}")
    lines.extend(
        _labelled_paragraph(
            "Arithmetic",
            f"The ellipsoid height is held fixed and the orthometric height "
            f"re-derived under the output model: H_out = H_in + N_in - "
            f"N_out, where N_in and N_out are the {source_record.name} and "
            f"{target_record.name} geoid heights at the point's horizontal "
            f"position, in metres. The Z column carries H_out; the _full.csv "
            f"export's Vertical shift column carries N_in - N_out per "
            f"point.",
        )
    )
    add("")
    return lines


def _geoid_swap_elevation_block(result, transformation, swap_models, unit) -> list[str]:
    """The ELEVATIONS section's account of a geoid-to-geoid conversion.

    The ``_factor_summary`` shape over the per-point geoid change, in the
    job's INPUT unit (the 2026-08-09 units rule; on this direction-less
    identity the input and output units can still differ on a
    Horizontal + Vertical job, and the shift columns follow the input one).
    The sigma line is the bare ``N/A`` of the summary shape - no number
    exists and nothing is attached to the absence (the owner's instruction,
    2026-08-09).
    """
    source_name = swap_models[0].name
    target_name = swap_models[1].name
    points = result.points
    swapped = [p for p in points if p.geoid_swap is not None]
    lines: list[str] = []
    add = lines.append

    if not swapped:
        lines.extend(
            textwrap.wrap(
                f"0 of {len(points)} points had their elevation re-derived "
                f"from {source_name} to {target_name}: no point carried a "
                f"convertible elevation. The causes are itemized above; any "
                f"that raise warnings are repeated under WARNINGS. The "
                f"_full.csv export's shift and sigma cells read "
                f"{fmt.NOT_AVAILABLE} for every point.",
                width=78,
            )
        )
        return lines

    lines.extend(
        textwrap.wrap(
            f"{len(swapped)} of {len(points)} points had their elevation "
            f"re-derived from the {source_name} geoid model to the "
            f"{target_name} geoid model; both vertical datums are "
            f"{transformation.source.code}, so no datum shift was applied "
            f"(see METHOD). Each point's geoid change is in the _full.csv "
            f"export's Vertical shift column. Summary across this job:",
            width=78,
        )
    )
    add("")

    shifts = [p.geoid_swap.shift_m for p in swapped]
    add(f"  Geoid change ({unit.code})")
    add(f"    minimum  {fmt.vertical_quantity(min(shifts), unit)}")
    add(f"    maximum  {fmt.vertical_quantity(max(shifts), unit)}")
    add(f"    mean     {fmt.vertical_quantity(statistics.fmean(shifts), unit)}")
    add("")
    sigma_summary_label = f"Shift one-sigma uncertainty ({unit.code})"
    add(f"  {sigma_summary_label:<33} {fmt.NOT_AVAILABLE}")
    return lines


def _vertical_elevation_block(result, transformation) -> list[str]:
    """The ELEVATIONS section's account of what the vertical conversion did.

    The record keeps a SUMMARY of the per-point sigma - min, max, mean, the
    shape ``_factor_summary`` uses for the scale factors - and leaves the
    per-point column to the audit CSV: the record says how uncertain this job
    was, the CSV says how uncertain each point was (plan section 5.1).
    """
    points = result.points
    converted = [p for p in points if p.vertical is not None]
    lines: list[str] = []
    add = lines.append

    if transformation.is_identity:
        lines.extend(
            textwrap.wrap(
                f"{len(converted)} of {len(points)} points carried an "
                f"elevation; both vertical datums are "
                f"{transformation.source.code}, so no shift was applied to "
                f"any of them (see METHOD). No model ran, so no modeled "
                f"uncertainty is introduced.",
                width=78,
            )
        )
        return lines

    if not converted:
        # "each point's shift ... are in the _full.csv export" is a claim
        # about cells that would all read N/A, and the sigma summary would
        # summarize nothing - the record asserted both anyway on a job whose
        # every point was blank-Z or coverage-refused (WP-V7 review gate,
        # MEDIUM 3). Say what happened instead.
        lines.extend(
            textwrap.wrap(
                f"0 of {len(points)} points had their elevation shifted from "
                f"{transformation.source.code} to "
                f"{transformation.target.code}: no point carried a "
                f"convertible elevation. The causes are itemized above; any "
                f"that raise warnings are repeated under WARNINGS. The "
                f"_full.csv export's shift and sigma "
                f"cells read {fmt.NOT_AVAILABLE} for every point.",
                width=78,
            )
        )
        return lines

    lines.extend(
        textwrap.wrap(
            f"{len(converted)} of {len(points)} points had their elevation "
            f"shifted from {transformation.source.code} to "
            f"{transformation.target.code}. The shift is MODELED, not "
            f"measured (see METHOD); each point's shift and its one-sigma "
            f"uncertainty are in the _full.csv export. Summary of the "
            f"uncertainty across this job:",
            width=78,
        )
    )
    add("")

    sigmas = [
        p.vertical.sigma_m for p in converted if p.vertical.sigma_m is not None
    ]
    # The summary reads in the JOB'S INPUT UNIT - the unit the elevations
    # were supplied in, matching the audit CSV's "Shift sigma (<unit>)"
    # column this summary summarizes (the owner's units instruction,
    # 2026-08-09). The min/max/mean are taken over the METRE values the
    # readings store and converted once for display: unit conversion is a
    # positive scale, so it cannot change which sigma is the minimum.
    unit = result.settings.input_unit
    sigma_summary_label = f"Shift one-sigma uncertainty ({unit.code})"
    if sigmas:
        # The _factor_summary shape exactly: label, then minimum / maximum /
        # mean - because across Michigan the sigma varies by a factor of
        # 91,000 (0.000004 m to 0.3656 m), a single figure here would
        # understate somebody's point by orders of magnitude (plan 5.1).
        add(f"  {sigma_summary_label}")
        add(f"    minimum  {fmt.vertical_quantity(min(sigmas), unit)}")
        add(f"    maximum  {fmt.vertical_quantity(max(sigmas), unit)}")
        add(f"    mean     {fmt.vertical_quantity(statistics.fmean(sigmas), unit)}")
    else:
        add(f"  {sigma_summary_label:<33} {fmt.NOT_AVAILABLE}")

    # Compared in METRES - the representation the readings store - not in the
    # display unit. The comparison is unit-invariant (both sides scale by the
    # same positive factor), so converting first would change nothing; it
    # would only make the rule look like it depends on a display choice.
    exceeds = [
        p
        for p in converted
        if p.vertical.sigma_m is not None
        and p.vertical.sigma_m > abs(p.vertical.shift_m)
    ]
    if exceeds:
        # A real Michigan case, not a hypothetical: at 43.05 N, 86.20 W the
        # sigma is 0.3656 m against a shift of -0.1435 m - 255% of the shift
        # (plan section 2.8). A summary alone would bury the points it
        # happens to; they are named.
        add("")
        add(
            f"  Points whose shift uncertainty EXCEEDS the shift itself "
            f"({len(exceeds)}):"
        )
        lines.extend(_point_id_block(exceeds))
        add("")
        add("  At each point above, the one-sigma uncertainty of the modeled")
        add("  shift is larger than the whole shift that was applied. The")
        add("  shifted elevation is still the model's best value there; the")
        add("  caveat under METHOD applies with its full force.")

    unstated = [p for p in converted if p.vertical.sigma_m is None]
    if unstated:
        # The negative-sigma region of DESIGN.md #36: the error model
        # interpolates below zero at ~0.43% of Michigan positions, a value
        # that cannot be a one-sigma. No uncertainty could be stated - never
        # a number - and the shift beside it is valid and unaffected.
        add("")
        add(
            f"  Points where no uncertainty could be stated "
            f"({len(unstated)}):"
        )
        lines.extend(_point_id_block(unstated))
        add("")
        add("  At these positions the VERTCON error model interpolates to a")
        add("  value that cannot be a one-sigma uncertainty, so no uncertainty")
        add(f"  could be stated - the Shift sigma cell reads {fmt.NOT_AVAILABLE!r}, never a")
        add("  number. THE SHIFT ITSELF IS VALID AND UNAFFECTED: it is read")
        add("  from the separate transformation grid, and the converted")
        add("  elevation stands. Each point is named again, with its position,")
        add("  under WARNINGS below.")

    return lines


# --------------------------------------------------------------------------
# The frame transformation (work package W4 of the WGS 84 build,
# docs/PLAN-wgs84.md section 3.6): present ONLY on a job whose positions HTDP
# carried between NAD83(2011) and a WGS 84 or ITRF frame, so every same-frame
# record is byte-identical to what it was. Every sentence is built from the
# job's own records - the registry's FrameTransformation and ReferenceFrame
# records, htdp_data's transcription, the job's ObservationEpoch and the
# points' own TransformHeight - so the record and the arithmetic cannot
# disagree. Facts only, no caveat prose (the owner's rule, DESIGN.md #50).
# --------------------------------------------------------------------------

HTDP_ANCHOR_RECORD_COUNT = "1,846"
"""How many of HTDP's printed records the suite holds this program to.

A literal, as "Twenty-seven" is in ``_method_spcs83``, and held by the suite
to the length of the fixture it describes
(``tests/fixtures/htdp_anchors.py``), which is where the anchors live."""

_HEIGHT_CONVENTION_FACTS = {
    # The measured figures are W0's, recorded in docs/DESIGN.md #70 ("Measured
    # for D6") and docs/PLAN-wgs84.md decision D6; the suite holds each one to
    # the text of #70. Stated as facts with their source, never as warnings
    # (the owner's no-disclaimer rule, DESIGN.md #50).
    HeightConvention.ELLIPSOID: (
        "The supplied height is part of the 3-D position HTDP transforms, and "
        "the ellipsoid height out is the {target} one, above the {target_ellipsoid} "
        "ellipsoid."
    ),
    HeightConvention.ORTHOMETRIC: (
        "An elevation belongs to no frame, so the transformation leaves the Z "
        "unchanged; HTDP was handed the elevation in place of the ellipsoid "
        "height. Measured: the horizontal result moves 1.2e-5 m per 40 m of "
        "height difference, so at most 0.012 mm where the geoid separation is "
        "about 35 m, as in Michigan (DESIGN.md #70)."
    ),
    HeightConvention.NOT_RECORDED: (
        "HTDP was handed an ellipsoid height of 0 m, and the Z stays blank. "
        "Measured: at 600 m of real height, Michigan's highest ground, the "
        "horizontal result moves at most 0.18 mm north and 0.13 mm east "
        "(DESIGN.md #70)."
    ),
}
"""What each height convention of plan decision D6 does, and what it costs.

Keyed by ``HeightConvention``, whose own value is the convention's name in
every output, so a convention added later without a sentence here refuses in
``_frame_transformation_block`` rather than printing nothing about it."""

ROUND_TRIP_MEASURED_FROM = date(1990, 1, 1)
ROUND_TRIP_MEASURED_TO = date(2035, 12, 31)
"""The observation dates the stated round-trip bound is measured to hold over.

Interim gate 2, finding L3: the figure had been stated as though it held at
every date the program accepts, back to 1907; the reviewer measured 1.13e-4 m
east at 1950 and 2.06e-4 m at 1908. W0 measured it over 1997.0 to 2026.8 only
(RECON.md section 5), which ends the day before this build's own date, so
every new job would have printed that its date was outside it. The lead
re-measured over 1990-01-01 to 2035-12-31 through ``michspc.spc.htdp``:
458,160 round trips (W0's 83 in-box positions, heights 0 and 600 m, all five
frames, both ways, six days a year at the year's ends and middle, where the
two clocks' sawtooth peaks), worst 8.519e-6 m north, 5.921e-5 m east and
1.886e-6 m up - inside the 9.2e-6 / 6.4e-5 / 4.3e-6 m W0 stated
(``review/wgs84-gate2/roundtrip_range.py`` and its committed output; the
suite holds these constants and the stated figures to that output). Past
2035 the east figure grows past 6.4e-5 m (6.92e-5 m by 2040-12-31 at the
north-west corner), so the range stops there."""

ROUND_TRIP_HEIGHT_FROM_M = -250.0
ROUND_TRIP_HEIGHT_TO_M = 610.0
"""The heights handed to HTDP that the stated round-trip bound holds over.

Interim gate 2 re-confirmation, N1: the non-closure grows linearly with the
height handed to HTDP (HTDP's velocity-to-angle radii carry no height term,
RECON.md section 5), and the east figure passes 6.4e-5 m at about 690 m. The
lead's measurement (``review/wgs84-gate2/roundtrip_range.py``) runs at -250,
0 and 650 m, so the ends of a linear growth bound every height between, and
the stated range sits inside it: Michigan's highest ground is about 603 m,
and -250 m leaves room for lakebed points below the ellipsoid."""

ROUND_TRIP_NON_CLOSURE = (
    "HTDP's forward and reverse transformations are not exact inverses. "
    "Measured on HTDP's own arithmetic, unrounded, for observation dates "
    "from 1990-01-01 to 2035-12-31 and heights handed to HTDP from -250 m to "
    "610 m, a Michigan position carried out and back fails to return by up "
    "to 9.2e-6 m north, 6.4e-5 m east and 4.3e-6 m up "
    "(review/wgs84-w0/RECON.md section 5, review/wgs84-gate2/, DESIGN.md "
    "#70). This program reproduces HTDP's arithmetic, and so its round trip "
    "too."
)
"""HTDP's own non-closure, as a fact (plan section 2.1: replicated, not
smoothed, on the owner's standing rule), with the dates it is measured to
hold over (``ROUND_TRIP_MEASURED_FROM`` / ``_TO``)."""


def _round_trip_paragraph(epoch: htdp.ObservationEpoch, points=()) -> str:
    """``ROUND_TRIP_NON_CLOSURE``, and the facts of where this job falls
    outside what it was measured over: the observation date, and the count of
    points handed HTDP a height outside the measured height range.

    A fact, not a caveat (DESIGN.md #50): the figure was measured for ranges
    of dates and heights, this job is or is not in them, and the record says
    which when it is not. No figure is offered outside them, because none was
    measured.
    """
    text = ROUND_TRIP_NON_CLOSURE
    if not ROUND_TRIP_MEASURED_FROM <= epoch.date <= ROUND_TRIP_MEASURED_TO:
        text += (
            f" This job's observation date, {epoch.date.isoformat()}, is "
            f"outside that range: the bound stated was measured for "
            f"observation dates {ROUND_TRIP_MEASURED_FROM.isoformat()} to "
            f"{ROUND_TRIP_MEASURED_TO.isoformat()} and does not cover this "
            f"date."
        )
    outside = sum(
        1
        for point in points
        if not (
            ROUND_TRIP_HEIGHT_FROM_M
            <= point.conversion.transform_height.height_for_transform_m
            <= ROUND_TRIP_HEIGHT_TO_M
        )
    )
    if outside:
        text += (
            f" {outside} of this job's {len(points)} points were handed HTDP "
            f"a height outside {ROUND_TRIP_HEIGHT_FROM_M:g} m to "
            f"{ROUND_TRIP_HEIGHT_TO_M:g} m, so the bound stated "
            f"does not cover them."
        )
    return text


def _htdp_software() -> str:
    """NGS HTDP's version, date and commit - from ``htdp_data``'s constants only."""
    return (
        f"NGS HTDP v{htdp_data.HTDP_VERSION} ({htdp_data.HTDP_VERSION_DATE}), "
        f"github.com/noaa-ngs/HTDP commit {htdp_data.HTDP_COMMIT}"
    )


def _htdp_verification() -> list[str]:
    """The two checks that hold this program's HTDP to NGS's, as paragraphs.

    Shared by the geodetic-to-geodetic METHOD section and, on a zone job, the
    FRAME TRANSFORMATION block's Verified line, so the claim is made in one
    set of words wherever it is made.
    """
    return [
        "This program's transcription of HTDP is held by its test suite to "
        "NGS's own Fortran source, committed unmodified at "
        "review/wgs84-w0/htdp-v3.6.0/: every constant transcribed must equal "
        "the one NGS wrote, number for number.",
        f"The transformation itself is checked against HTDP. NGS's source was "
        f"compiled and run, and {HTDP_ANCHOR_RECORD_COUNT} of its printed "
        f"records - every frame offered, both directions and the round trip, "
        f"across Michigan and its lakes - are held in the test suite as fixed "
        f"reference values. This software reproduces them to the digit HTDP "
        f"prints, 1e-10 degree and 1 mm.",
    ]


VERTCON_FORWARD_ANCHOR_COUNT = "Twenty"
VERTCON_INVERSE_ANCHOR_COUNT = "five"
GEOID_ANCHOR_COUNT = "Twenty"
BENCHMARK_ANCHOR_COUNT = "fourteen"
"""How many NGS truths the suite holds each vertical-job check to: literals,
as "Twenty-seven" is in ``_method_spcs83``, each held by the suite to the
length of the fixture it describes - ``vertcon_anchors``' two directions,
``geoid_anchors`` and ``geoid12b_anchors`` (twenty positions each), and
``ellipsoid_height_anchors``' published benchmarks (plan W4b)."""


def _vertical_verification(result, transformation, swap_models) -> list[str]:
    """The checks that hold a zone-less vertical job's arithmetic to NGS.

    Only those that verify work THIS job did (plan W4b, the #42 finding-3
    class): the geoid anchors for each model it read, the published
    benchmarks when it derived H from a GEOID18 h, and VERTCON's NCAT anchors
    when it applied a modeled datum shift. The VERTCON sentence keeps the
    wording ``_method_spcs83`` gives NCAT ("to within 0.5 mm - which is the
    precision NCAT publishes"), because it states the same kind of check.
    """
    settings = result.settings
    paragraphs: list[str] = []
    models = (
        [swap_models[0].name, swap_models[1].name]
        if swap_models is not None
        else ([result.geoid_model] if result.geoid_model else [])
    )
    if models:
        named = " and ".join(models)
        paragraphs.append(
            f"The geoid heights are checked against NGS's own geoid height "
            f"service. {GEOID_ANCHOR_COUNT} Michigan positions were computed "
            f"by NGS for each model this job read ({named}), and those "
            f"results are held in the test suite as fixed reference values. "
            f"This software reproduces them to within 1 mm, the precision NGS "
            f"publishes geoid heights to."
        )
    if (
        settings.input_height_kind is HeightKind.ELLIPSOID
        and result.geoid_model == "GEOID18"
    ):
        paragraphs.append(
            f"The ellipsoid-height arithmetic is checked at "
            f"{BENCHMARK_ANCHOR_COUNT} published NGS benchmarks whose "
            f"datasheets carry both an NAVD 88 height and a GEOID18 geoid "
            f"height: given h = H + N from those figures, this software "
            f"returns the published H to within 1.5 mm."
        )
    if transformation is not None and not transformation.is_identity:
        paragraphs.append(
            f"The vertical datum transformation is checked against the "
            f"National Geodetic Survey's own Coordinate Conversion and "
            f"Transformation Tool (NCAT). {VERTCON_FORWARD_ANCHOR_COUNT} "
            f"Michigan positions converted from NGVD 29 to NAVD 88 by NCAT, "
            f"and {VERTCON_INVERSE_ANCHOR_COUNT} converted from NAVD 88 to "
            f"NGVD 29, are held in the test suite as fixed reference values. "
            f"This software reproduces each shift to within 0.5 mm - which is "
            f"the precision NCAT publishes, so the agreement is as close as "
            f"the reference permits."
        )
    return paragraphs


def _method_without_a_zone(result, path, transformation, swap_models) -> list[str]:
    """The METHOD and verification sections of a job with no zone at either end.

    Two directions have none: geodetic to geodetic (plan D7), and a
    vertical-only job on geodetic positions. The same shape as
    ``_method_spcs83`` and ``_method_spcs2022`` - what ran, and HOW THIS
    SOFTWARE IS VERIFIED - saying what is true of a job with no zone: no
    projection ran, so no manual section, no zone constants and no NCAT
    projection anchors are named.

    * Geodetic to geodetic: the transformation is the conversion, and HTDP is
      its authority.
    * Vertical only (plan W4b; DESIGN.md #70): the horizontal coordinates are
      reproduced unconverted, and what runs is at each point's pivot - the
      input position itself, or the input carried to NAD83(2011) by HTDP -
      the geoid lookup and the vertical datum transformation. Until W4b this
      job printed the SPCS 83 Lambert prose, which described a projection it
      never ran.

    The verification names what verifies THIS job - HTDP's anchors when a
    frame transformation ran, and, in both directions, the vertical checks of
    ``_vertical_verification`` for the vertical work the job did - closing
    with the line every era's section closes with.
    """
    settings = result.settings
    lines: list[str] = []
    add = lines.append
    checks: list[str] = []
    if settings.direction is Direction.GEODETIC_TO_GEODETIC:
        lines.extend(
            _labelled_paragraph(
                "Authority",
                f"{_htdp_software()} - the frame transformation, which is the "
                f"whole of this job's "
                + (
                    # Interim gate 2 re-confirmation, N3: on a vertical-mode
                    # job the elevation is converted too (VERTCON, or
                    # H = h - N), so HTDP is the whole of the HORIZONTAL
                    # conversion only.
                    "horizontal conversion; the elevation conversion is "
                    "stated below. "
                    if settings.vertical_mode.converts_elevations
                    else "conversion. "
                )
                + "No State Plane coordinate system and no map projection is "
                "involved.",
            )
        )
        add("")
        lines.extend(
            _labelled_paragraph(
                "Ellipsoids",
                f"{path.source.code} on the {path.source.ellipsoid_name} "
                f"ellipsoid, {path.target.code} on the "
                f"{path.target.ellipsoid_name} ellipsoid: HTDP takes the "
                f"ellipsoid from the frame's name (htdp.f:3221-3224).",
            )
        )
        checks.extend(_htdp_verification())
        # And the vertical checks for whatever vertical work it ran - a geoid
        # read for the factors or for H, the benchmarks behind a GEOID18
        # h -> H, VERTCON on a modelled datum shift - exactly as a
        # vertical-only job names them (plan W4b, DESIGN.md #70: the record
        # named fewer checks than the job ran). A job that read no geoid
        # names HTDP's two checks alone, as it did at W4.
        checks.extend(_vertical_verification(result, transformation, swap_models))
    else:
        pivot = settings.geodetic_frame if path is None else _pivot_frame(path)
        where = (
            "which is the input position itself"
            if path is None
            else f"which is the input position carried from {path.source.code} "
            f"by the frame transformation stated below"
        )
        if swap_models is not None:
            looked_up = (
                f"the {swap_models[0].name} and {swap_models[1].name} geoid "
                f"heights are read there, and "
            )
        elif result.geoid_model:
            looked_up = f"the {result.geoid_model} geoid height is read there, and "
        else:
            looked_up = ""
        lines.extend(
            _labelled_paragraph(
                "Method",
                f"No map projection runs in this job: its positions are "
                f"geodetic, no State Plane zone is involved, and the "
                f"horizontal coordinates are reproduced unconverted. Each "
                f"point's elevation is converted at its {pivot.code} "
                f"position, {where}: {looked_up}the vertical datum "
                f"transformation stated below is applied.",
            )
        )
        if path is not None:
            checks.extend(_htdp_verification())
        checks.extend(_vertical_verification(result, transformation, swap_models))
    add("")
    if not checks:
        # Nothing was computed that NGS publishes a check for - an identity
        # datum pair with no geoid model - so no check is claimed.
        return lines
    add("HOW THIS SOFTWARE IS VERIFIED")
    add("")
    for paragraph in checks:
        lines.extend(textwrap.wrap(paragraph, width=78, break_long_words=False))
        add("")
    if len(checks) == 2:
        add("Both checks compare this software against NGS. Neither compares it")
        add("against itself.")
    elif len(checks) == 1:
        add("The check compares this software against NGS, not against itself.")
    else:
        add("Each check compares this software against NGS. None compares it")
        add("against itself.")
    add("")
    return lines


def _geodetic_frame_block(frame, label: str) -> list[str]:
    """A geodetic end's COORDINATE SYSTEMS block - the zone block's shape.

    A geodetic-to-geodetic job has no zone to describe, and an empty section
    would read as an omission, so each end states its frame the way a zone
    block states its zone: the frame, its ellipsoid, its epoch, and its
    citation.
    """
    epoch = (
        "the observation date (see FRAME TRANSFORMATION)"
        if frame.is_time_dependent
        else f"{fmt.exact_number(frame.reference_epoch)}, the frame's reference epoch"
    )
    lines = [
        f"{label}: geodetic positions (latitude / longitude)",
        _zone_heading("Reference frame", f"{frame.code} - {frame.name}"),
        _zone_heading("Ellipsoid", frame.ellipsoid_name),
        _zone_heading("Epoch", epoch),
    ]
    lines.extend(
        textwrap.wrap(
            frame.citation,
            width=78,
            initial_indent=_SOURCE_PREFIX,
            subsequent_indent=" " * len(_SOURCE_PREFIX),
            break_long_words=False,
            break_on_hyphens=False,
        )
    )
    return lines


def _helmert_lines(path, helmert_epoch) -> list[str]:
    """The two Helmert sets HTDP applied, printed from ``htdp_data``.

    Printed rather than only named because this record is what a job is
    reproduced from, and printed from the transcription the arithmetic reads
    - ``formatting.exact_number``, so each figure reads back as exactly the
    number NGS wrote - so there is no second copy that could drift. HTDP's
    position always runs through ITRF94 with the IGS set when NAD 83 is an
    end (htdp.f:3229-3231): the source frame's set negated, then the target
    frame's (``htdp._toit94``, ``_frit94``).
    """
    lines = _labelled_paragraph(
        "Helmert",
        f"HTDP's IGS-convention sets (SETTP's /tranpa/, htdp.f:3229), each "
        f"from ITRF94 to a frame, linearized, and evaluated at the input "
        f"epoch, {fmt.exact_number(helmert_epoch.decimal_year)}. The position "
        f"goes from {path.source.code} to ITRF94 by the first set below with "
        f"all fourteen parameters negated, then from ITRF94 to "
        f"{path.target.code} by the second. Rotations in arcseconds, as HTDP "
        f"stores them:",
    )
    for frame in (path.source, path.target):
        row = htdp_data.IGS_CONVENTION[frame.htdp_frame.iopt]
        name, _line = htdp_data.HELMERT_SET_NAMES[row.iopt]
        n = fmt.exact_number
        lines.extend(
            [
                f"  From ITRF94 to {name} - used for {frame.code}",
                f"    {row.source}, reference epoch {n(row.reference_epoch)}",
                f"    tx ty tz         {n(row.tx_m)}  {n(row.ty_m)}  {n(row.tz_m)}  m",
                f"    dtx dty dtz      {n(row.dtx_m_per_yr)}  {n(row.dty_m_per_yr)}  "
                f"{n(row.dtz_m_per_yr)}  m/yr",
                f"    rx ry rz         {n(row.rx_arcsec)}  {n(row.ry_arcsec)}  "
                f"{n(row.rz_arcsec)}  arcsec",
                f"    drx dry drz      {n(row.drx_arcsec_per_yr)}  "
                f"{n(row.dry_arcsec_per_yr)}  {n(row.drz_arcsec_per_yr)}  arcsec/yr",
                f"    scale dscale     {n(row.scale)}  {n(row.dscale_per_yr)}  /yr",
            ]
        )
    return lines


def _frame_transformation_block(result, path, *, verified: bool) -> list[str]:
    """The METHOD section's FRAME TRANSFORMATION block.

    ``verified`` adds the HTDP verification as a labelled paragraph - on a
    zone job, whose own HOW THIS SOFTWARE IS VERIFIED is about the
    projection; a geodetic-to-geodetic job carries it in its METHOD section
    instead (``_method_without_a_zone``).
    """
    settings = result.settings
    untransformed = [
        point.point_id
        for point in result.points
        if point.conversion.frame_transformation != path
    ]
    if untransformed:
        # Fail closed, as exports' audit rows do: this block states that HTDP
        # moved every point of the job, so a point it did not move - a result
        # assembled by hand - is refused rather than described.
        raise ValueError(
            f"This job record cannot state the frame transformation {path}: "
            f"point(s) {', '.join(untransformed[:5])} of the job carry no such "
            f"transformation, and the record would say they did."
        )
    epoch = htdp.ObservationEpoch(settings.observation_date)
    lines: list[str] = []
    add = lines.append

    def frame_text(frame) -> str:
        at = (
            "at the observation date"
            if frame.is_time_dependent
            else f"at its reference epoch {fmt.exact_number(frame.reference_epoch)}"
        )
        return (
            f"{frame.code} - {frame.name}, on the {frame.ellipsoid_name} "
            f"ellipsoid, {at}"
        )

    add("FRAME TRANSFORMATION")
    add("")
    lines.extend(_labelled_paragraph("From", frame_text(path.source)))
    lines.extend(_labelled_paragraph("To", frame_text(path.target)))
    lines.extend(
        _labelled_paragraph(
            "Observation date",
            f"{epoch.date.isoformat()}, decimal year "
            f"{fmt.exact_number(epoch.decimal_year)} - HTDP's own conversion of "
            f"the calendar date (htdp.f:7913-7919). One date for the whole "
            f"job: each of its {len(result.points)} point(s) is taken as "
            f"observed on it, because the input file carries no date of its "
            f"own.",
        )
    )
    lines.extend(
        _labelled_paragraph(
            "Software",
            f"{_htdp_software()}, as transcribed by this program "
            f"(michspc.spc.htdp).",
        )
    )
    add("")
    lines.extend(_labelled_paragraph("Direction", path.direction_statement))
    add("")
    helmert_epoch = epoch if path.source.is_time_dependent else htdp.NAD83_2011_EPOCH
    lines.extend(_helmert_lines(path, helmert_epoch))
    add("")

    spacing = (
        htdp_data.GRID6_UPPER_LATITUDE - htdp_data.GRID6_LOWER_LATITUDE
    ) / htdp_data.GRID6_CELLS_NORTH
    up_is_zero = all(node[2] == 0.0 for node in htdp_data.GRID6_WINDOW.values())
    velocity = (
        f"HTDP's model for its velocity region 6: a {spacing:g}-degree grid of "
        f"ITRF2008 velocities (initvl.f), interpolated bilinearly at the "
        f"point's position mapped to ITRF2008, then carried into "
        f"{path.target.code}, the output frame."
    )
    if up_is_zero:
        velocity += (
            " The grid's up velocity is 0.00 at every node this program "
            "carries, so the up rate is the two frames' own translation and "
            "scale rates."
        )
    if epoch.minutes == htdp.NAD83_2011_EPOCH.minutes:
        velocity += (
            f" The observation date is {epoch.date.isoformat()}, the day of "
            f"the {_pivot_frame(path).code} reference epoch, so the "
            f"propagation span is zero and HTDP applied no velocity: the "
            f"_full.csv export's velocity cells read {fmt.NOT_AVAILABLE}."
        )
    else:
        velocity += (
            f" Each point's velocity - north, east and up, mm/yr, in "
            f"{path.target.code} - is in the _full.csv export."
        )
    lines.extend(_labelled_paragraph("Velocity", velocity))
    add("")

    lines.extend(
        _labelled_paragraph(
            "Heights",
            "The height HTDP was handed, and its convention, is stated per "
            "point in the _full.csv export. This job:",
        )
    )
    used = [point.conversion.transform_height.convention for point in result.points]
    for convention in HeightConvention:
        count = used.count(convention)
        if not count:
            continue
        fact = _HEIGHT_CONVENTION_FACTS.get(convention)
        if fact is None:
            raise ValueError(
                f"This job record cannot state what the height convention "
                f"{convention.name} does: no sentence is registered for it, "
                f"and a convention the record could not describe would leave "
                f"{count} point(s) with a transformation it does not explain."
            )
        add(f"  {convention.value}:")
        lines.extend(
            textwrap.wrap(
                f"{count} of {len(result.points)} points. "
                + fact.format(
                    target=path.target.code,
                    target_ellipsoid=path.target.ellipsoid_name,
                ),
                width=78,
                initial_indent="    ",
                subsequent_indent="    ",
            )
        )
    add("")
    lines.extend(
        _labelled_paragraph("Round trip", _round_trip_paragraph(epoch, result.points))
    )
    if verified:
        add("")
        lines.extend(
            _labelled_paragraph("Verified", " ".join(_htdp_verification()))
        )
    add("")
    return lines


_MANUAL_SECTIONS = {
    ProjectionKind.LAMBERT_CONIC_2SP: "3.1",
    ProjectionKind.LAMBERT_CONIC_1SP: "3.1",
    ProjectionKind.TRANSVERSE_MERCATOR: "3.2",
    ProjectionKind.OBLIQUE_MERCATOR: "3.3",
}
"""Which chapter of the manual defines each projection's equations.

Every kind must be here. A kind missing from this table would be silently left
out of the Authority section, so the record would name fewer sets of equations
than the job actually used - a sealed document understating its own method -
and ``_equation_lines`` refuses instead.
"""

_SPCS2022_ZONE_CODES = frozenset(zone.code for zone in SPCS2022_ZONES)
"""The 2022 era, derived from the registry's own tuple rather than restated.

A zone added to ``SPCS2022_ZONES`` is in this set the moment it is added, so a
new 2022 zone cannot be described by the 1983 era's METHOD section.
"""


def _job_zones(settings) -> tuple:
    """Every zone this record DESCRIBES, source first.

    The same rule the COORDINATE SYSTEMS section applies a few lines above -
    including the target zone unless the job converts TO geodetic, where there
    is no target zone to describe and any value left in the field was not used.
    Deriving both sections from one rule means METHOD states the equations for
    exactly the zones the record set out, and cannot name a projection the
    document never showed the reader.

    A geodetic job has one zone; a zone-to-zone job has two; a vertical-only
    job on geodetic positions has none.
    """
    zones = []
    if settings.source_zone is not None:
        zones.append(settings.source_zone)
    if (
        settings.target_zone is not None
        and settings.direction is not Direction.ZONE_TO_GEODETIC
    ):
        zones.append(settings.target_zone)
    return tuple(zones)


def _equation_lines(zones) -> list[str]:
    """The manual sections this job's projections are computed from.

    Derived from the kinds ACTUALLY present, never a static list: a record that
    named all three sets of equations on a job that used one would be
    describing work that was not done, and one that named a fixed set would
    stop being true the first time a zone of another kind was selected.

    Kinds are listed in ``ProjectionKind``'s declaration order, so the section
    reads the same way from job to job.
    """
    present = [
        kind
        for kind in ProjectionKind
        if any(zone.projection_kind is kind for zone in zones)
    ]
    lines: list[str] = []
    for kind in present:
        section = _MANUAL_SECTIONS.get(kind)
        if section is None:
            known = ", ".join(
                f"{k.value} (section {s})" for k, s in _MANUAL_SECTIONS.items()
            )
            raise ValueError(
                f"This job record cannot state which equations converted it: "
                f"no manual section is registered for {kind.value}. A record "
                f"that silently omitted one projection's equations would "
                f"understate the method of a sealed job. Registered: {known}."
            )
        lines.extend(
            textwrap.wrap(
                f"section {section}  {kind.value}",
                width=78,
                initial_indent=" " * (_LABEL_WIDTH + 2),
                subsequent_indent=" " * (_LABEL_WIDTH + 2 + len(f"section {section}  ")),
                break_long_words=False,
            )
        )
    return lines


def _method_spcs83() -> list[str]:
    """The METHOD and verification sections for a job on the 1983 zones.

    BYTE-IDENTICAL to what this record has printed since 0.1.0, and pinned as
    literal text in the suite. Every sealed SPCS 83 job in existence carries
    these words; a second era arriving in this document must not reword them.
    """
    return [
        "Authority          NOAA Manual NOS NGS 5, State Plane Coordinate System",
        "                   of 1983 (Stem, January 1989; reprinted with minor",
        "                   corrections March 1990)",
        "",
        "Equations          The rigorous Lambert conformal conic mapping",
        "                   equations of section 3.1 - zone constants (3.12),",
        "                   direct conversion (3.13), inverse conversion (3.14).",
        "                   Exact at any latitude, with no approximation term.",
        "",
        "Ellipsoid          GRS 80, the ellipsoid of NAD 83 (manual section 1.7).",
        "                   Only the semimajor axis and the flattening are stored;",
        "                   every other constant is derived from those two.",
        "",
        "HOW THIS SOFTWARE IS VERIFIED",
        "",
        "The zone constants used above are not taken on trust. The manual",
        "publishes, in Appendix C, the constants NGS computed for every Lambert",
        "zone. This software stores only the DEFINING constants - the standard",
        "parallels, the grid origin, the central meridian - and derives the rest.",
        "Its test suite recomputes all of them and requires a match with NGS's",
        "published figures to the last decimal place NGS printed, for all three",
        "Michigan zones.",
        "",
        "The conversion itself is checked against the National Geodetic Survey's",
        "own Coordinate Conversion and Transformation Tool (NCAT). Twenty-seven",
        "positions spanning the three zones were converted by NCAT, and those",
        "results are held in the test suite as fixed reference values. This",
        "software reproduces them to within 0.5 mm - which is the precision NCAT",
        "publishes, so the agreement is as close as the reference permits.",
        "",
        "Both checks compare this software against NGS. Neither compares it",
        "against itself.",
        "",
    ]


def _method_spcs2022(zones) -> list[str]:
    """The METHOD and verification sections for a job on the 2022 zones.

    The same document in the same shape, saying what is true of THIS era. Four
    facts differ and every one of them matters to a reader checking the work:

    * the equations come from the same manual, but from up to three of its
      sections rather than always from 3.1;
    * the zone constants are not in Appendix C - they are NGS's own published
      SPCS2022 parameters, captured and digest-pinned, and the suite compares
      every stored field against that capture rather than recomputing anything;
    * the conversion is anchored to beta NCAT, not production NCAT; and
    * the anchors are pre-release. That is stated as the dated fact it is,
      with the re-freeze obligation named, because a reader of a sealed job
      six months from now must be able to tell which NGS products it rests on
      (docs/DESIGN.md #61, docs/REFREEZE-NSRS.md).

    The "Twenty-seven"/"three" of the 1983 arm becomes "Sixty-three"/"nineteen"
    here; both are literals in this module and both are held against the length
    of the fixture they describe by the suite, which is where the anchors live.
    """
    lines: list[str] = []
    add = lines.append

    lines.extend(
        _labelled_paragraph(
            "Authority",
            "NOAA Manual NOS NGS 5, State Plane Coordinate System of 1983 "
            "(Stem, January 1989; reprinted with minor corrections March "
            "1990) - the mapping equations, which SPCS2022 is projected with "
            "unchanged.",
        )
    )
    add("")
    lines.extend(
        _labelled_paragraph(
            "",
            f"{SPCS2022_POLICY_CITATION} - the policy authority for SPCS2022, "
            f"and the SPCS2022 Procedures its zones are designed under.",
        )
    )
    add("")
    lines.extend(
        _labelled_paragraph(
            "",
            "NGS SPCS2022 zone parameters and zone bounds, published at "
            "beta.ngs.noaa.gov and frozen in this repository (NGS beta):",
        )
    )
    # Each file with its own capture date and its own digest, from the same
    # constants the zone records cite - so the record and the registry cannot
    # state different provenance for the same numbers. The digest lines run
    # past 78 columns, as the geoid model's digest line already does: a
    # SHA-256 is not wrappable without becoming a different string.
    add(
        f"{'':<{_LABEL_WIDTH}}{SPCS2022_DEFINITIONS_FILENAME}, captured "
        f"{SPCS2022_DEFINITIONS_CAPTURED}"
    )
    add(f"{'':<{_LABEL_WIDTH}}SHA-256 {SPCS2022_DEFINITIONS_SHA256}")
    add(
        f"{'':<{_LABEL_WIDTH}}{SPCS2022_BOUNDS_FILENAME}, captured "
        f"{SPCS2022_BOUNDS_CAPTURED}"
    )
    add(f"{'':<{_LABEL_WIDTH}}SHA-256 {SPCS2022_BOUNDS_SHA256}")
    add("")

    lines.extend(
        _labelled_paragraph(
            "Equations",
            "The rigorous mapping equations of NOAA Manual NOS NGS 5, one set "
            "per projection this job uses:",
        )
    )
    lines.extend(_equation_lines(zones))
    add("")
    lines.extend(
        _labelled_paragraph(
            "Ellipsoid",
            "GRS 80 - the ellipsoid of NAD 83 and of NATRF2022 alike (NOAA "
            "Technical Report NOS NGS 62). Only the semimajor axis and the "
            "flattening are stored; every other constant is derived from "
            "those two.",
        )
    )
    add("")
    add("HOW THIS SOFTWARE IS VERIFIED")
    add("")
    lines.extend(
        textwrap.wrap(
            f"The zone constants used above are not taken on trust. This "
            f"software stores only the DEFINING constants NGS publishes - the "
            f"origin, the central meridian, the origin scale factor, the false "
            f"coordinates - and derives the rest. Its test suite reads NGS's "
            f"own captured files back and compares every stored field against "
            f"them, zone by zone: the defining constants against "
            f"{SPCS2022_DEFINITIONS_FILENAME} (SHA-256 "
            f"{SPCS2022_DEFINITIONS_SHA256}), and the published zone bounds "
            f"this program's warnings are measured against, against "
            f"{SPCS2022_BOUNDS_FILENAME} (SHA-256 {SPCS2022_BOUNDS_SHA256}).",
            width=78,
            break_long_words=False,
        )
    )
    add("")
    lines.extend(
        textwrap.wrap(
            f"The conversion itself is checked against the National Geodetic "
            f"Survey's own Coordinate Conversion and Transformation Tool "
            f"(NCAT). Sixty-three positions spanning all nineteen Michigan "
            f"SPCS2022 zones were converted by beta NCAT (captured "
            f"{SPCS2022_DEFINITIONS_CAPTURED}), and those results are held in "
            f"the test suite as fixed reference values. This software "
            f"reproduces them within the precision NCAT prints. The inverse is "
            f"checked at the same positions: each captured coordinate is "
            f"converted back, and the convergence angle and grid scale factor "
            f"reported there are held against the same printed NCAT values.",
            width=78,
            break_long_words=False,
        )
    )
    add("")
    lines.extend(
        textwrap.wrap(
            "Those anchors, and the zone parameters above, come from NGS's "
            "beta products, published ahead of the official SPCS2022 release "
            "for implementation. They are to be re-frozen against NGS's "
            "official release when it is published, and the difference "
            "measured (docs/REFREEZE-NSRS.md).",
            width=78,
            break_long_words=False,
        )
    )
    add("")
    add("Both checks compare this software against NGS. Neither compares it")
    add("against itself.")
    add("")
    return lines


def _method_and_verification(settings) -> list[str]:
    """The METHOD section, in the era of the zones this job actually uses.

    **A job cannot mix eras.** The 1983 zones are on NAD83(2011) and the 2022
    zones are on NATRF2022; ``frames.require_frame_path`` refuses that pair
    before any coordinate is converted, and ``job.run`` refuses it before the
    file is read (docs/DESIGN.md #62). This function does not rely on that
    assumption silently - it checks it, because a settings record can be built
    by hand and a document that quietly described half a job in the wrong era's
    words would be worse than a refusal.

    A job with NO zone at all is not described here: since plan W4b
    (DESIGN.md #70) ``build_report`` gives it ``_method_without_a_zone``,
    because the 1983 arm it used to take describes a projection such a job
    never runs. Called with no zone, this still returns the 1983 arm, as it
    always did - it is only no longer asked.
    """
    zones = _job_zones(settings)
    modern = [zone for zone in zones if zone.code in _SPCS2022_ZONE_CODES]
    legacy = [zone for zone in zones if zone.code not in _SPCS2022_ZONE_CODES]
    if modern and legacy:
        raise ValueError(
            f"This job names zones from two eras - "
            f"{', '.join(f'{z.name} ({z.code}, {z.system})' for z in legacy)} "
            f"and "
            f"{', '.join(f'{z.name} ({z.code}, {z.system})' for z in modern)} "
            f"- and they are on different reference frames, so no such "
            f"conversion exists to describe. NGS has not published the "
            f"NAD83(2011) to NATRF2022 transformation "
            f"(docs/DEFERRED-NATRF2022-BRIDGE.md); a conversion between the "
            f"eras is refused before any coordinate is computed."
        )
    if modern:
        return _method_spcs2022(modern)
    return _method_spcs83()


def build_report(result: JobResult) -> str:
    """Render the job record."""
    # The W3 -> W4 write guard (require_a_disclosable_job) was called here
    # until this record could state a frame transformation; it can now, in
    # the FRAME TRANSFORMATION block below, and the guard is gone.
    settings = result.settings
    if settings.input_path is None or settings.output_directory is None:
        # The record's INPUT block opens with "File" and its OUTPUT block opens
        # with "Folder". Neither line can be written from None, and neither may
        # be filled in with a plausible substitute: this record is what a sealed
        # survey is defended with, so a file name it never read or a folder it
        # never wrote to would be a falsehood in the one document that exists to
        # say what happened (docs/DESIGN.md section 1, amendment #26).
        # Name which one is actually missing. Saying "neither" when only one is
        # absent is a false diagnostic about the half-pathless state, which is
        # a state this program explicitly supports (closing review gate).
        missing = []
        if settings.input_path is None:
            missing.append("no input file")
        if settings.output_directory is None:
            missing.append("no output folder")
        raise ValueError(
            f"A job record names the input file it read and the folder it "
            f"wrote to, and this job states it had {' and '.join(missing)} "
            f"(input_path={settings.input_path!r}, "
            f"output_directory={settings.output_directory!r}). A job with no "
            f"file, such as a single typed point, is displayed rather than "
            f"recorded."
        )
    generated = datetime.now(timezone.utc).astimezone()

    # The vertical disclosure switch (WP-V7). Everything it gates below is
    # ADDITIVE and appears only on a job that converts elevations
    # (HORIZONTAL_AND_VERTICAL, or vertical-only): a horizontal job's record
    # is byte-identical to what this program has always written, which is the
    # WP-V6 gate's hard constraint on this package. The transformation is
    # resolved through the same registry lookup job.run performed, so the
    # record and the computation quote one record.
    vertical = settings.vertical_mode.converts_elevations
    transformation = (
        require_vertical_pair(
            settings.source_vertical_datum, settings.target_vertical_datum
        )
        if vertical
        else None
    )
    # (input model, output model) when this job converts BETWEEN geoid
    # models, else None - job.geoid_swap_models' one rule, so the record and
    # the computation cannot disagree about whether a swap ran. Every block
    # this gates is additive and swap-only: a job without a swap keeps every
    # byte it wrote before the feature.
    swap_models = geoid_swap_models(settings, transformation)
    # The frame transformation the rows applied, or None: job's one rule, so
    # every block this gates - all of them additive or reworded only on a
    # transformed job - and the computation cannot disagree about whether
    # HTDP ran. A same-frame record is byte-identical to what it always was.
    frame_path = applied_frame_transformation(settings)
    geodetic_to_geodetic = settings.direction is Direction.GEODETIC_TO_GEODETIC
    # Every job with no State Plane zone at either end: geodetic to geodetic,
    # and a vertical-only job on geodetic positions. The one condition every
    # zone-only sentence below is withheld on (plan W4b, DESIGN.md #70 - the
    # #42 finding-3 class: until W4b the vertical-only geodetic record printed
    # the SPCS 83 projection prose, "inside its zone" and "moved between
    # zones" about a job with no zone).
    # ``job.is_zoneless`` is the one statement of it, shared with the
    # interface's elevation hints (work package W5).
    zoneless = is_zoneless(settings.direction, settings.source_zone)
    # The model that derived H from h, or None when the Z column already held
    # elevations. Resolved through the same job-layer rule the computation
    # used, so the record cannot name a model the conversion did not read.
    ellipsoid_model_name = (
        factors_geoid_model(settings, transformation).name
        if settings.input_height_kind is HeightKind.ELLIPSOID
        else None
    )

    lines: list[str] = []
    add = lines.append

    add(_RULE)
    add(f"  {APP_NAME.upper()}")
    add("  COORDINATE CONVERSION JOB RECORD")
    add(_RULE)
    add("")
    add(f"Generated          {generated.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    add(f"Software           {APP_NAME} version {__version__}")
    add("")

    # ---------------------------------------------------------------- input
    add(_THIN)
    add("INPUT")
    add(_THIN)
    add(f"File               {settings.input_path}")
    if result.input_sha256:
        add(f"SHA-256            {result.input_sha256}")
    else:
        # No digest means no bytes passed through this program: the rows were
        # handed to the job already parsed. Saying so is the only honest line
        # available, and it is a great deal more honest than the hash of
        # whatever happens to sit at the path above - which is what this line
        # used to print, certifying a file that was never converted
        # (WP-R3 fix 2). The file name is left in place because it is what the
        # caller stated; the sentence below says what it is worth.
        add("SHA-256            not available")
        add("                   These coordinates were supplied to this program")
        add("                   already parsed, so it never read the file named")
        add("                   above and nothing here certifies its contents.")
    add(f"Coordinate rows    {result.input_row_count}")
    if result.skipped_blank_lines:
        add(f"Blank lines        {result.skipped_blank_lines} (skipped)")
    lines.extend(_input_format_block(settings))
    if vertical:
        # Which surface the file's Z column measures from. Stated with the
        # datum's full name: NGVD 29 and NAVD 88 heights differ by up to
        # 0.41 m across Michigan while looking identical, so the code alone
        # is a token a reader six months later may not place.
        source_datum = settings.source_vertical_datum
        add(f"Vertical datum     {source_datum.name} ({source_datum.code})")
    add("")

    # --------------------------------------------------------------- output
    add(_THIN)
    add("OUTPUT")
    add(_THIN)
    add(f"Folder             {settings.output_directory}")
    add(f"Conversion         {settings.direction.value}")
    if settings.direction is Direction.VERTICAL_ONLY:
        # The one direction whose OUTPUT is not a converted coordinate. Said
        # here, at the line a reader consults first, so nobody takes the
        # coordinate columns of the export for a conversion that happened.
        add("                   The horizontal coordinates are NOT converted:")
        add("                   the exports reproduce the input's coordinate")
        add("                   columns unchanged, and only the elevation is")
        add("                   converted, into the vertical datum below.")
    add(f"Units out          {settings.output_unit.name} ({settings.output_unit.code})")
    add(f"                   {settings.output_unit.citation}")
    if vertical:
        target_datum = settings.target_vertical_datum
        add(f"Vertical datum     {target_datum.name} ({target_datum.code})")
        add("                   Every elevation this job writes - including the")
        add("                   clean export's Z column - is expressed in this")
        add("                   datum.")
    if settings.longitude_convention is not None:
        # Present exactly when the job consulted one: every direction with
        # geodetic coordinates on either end, including a vertical-only job
        # reading a geodetic file. A zone-to-zone job and a vertical-only job
        # reading State Plane coordinates state None - the file carries no
        # longitudes - and the record honestly carries no Longitude line.
        add(f"Longitude          {settings.longitude_convention.value}")
    if settings.direction in (
        Direction.GEODETIC_TO_ZONE,
        Direction.GEODETIC_TO_GEODETIC,
    ) or (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is None
    ):
        # The one thing a geodetic input file cannot carry in its own columns.
        # A latitude and longitude mean nothing without the frame they are
        # expressed in, and reading NATRF2022 positions as NAD 83 is a one-to-
        # two metre error that looks entirely ordinary (docs/DESIGN.md section
        # 6). The core refuses a mismatch; this states what was assumed, so the
        # record answers the question rather than leaving a reader to guess.
        add(
            f"Reference frame    {settings.geodetic_frame.code} - "
            f"{settings.geodetic_frame.name}"
        )
        add("                   The latitudes and longitudes in the input file")
        add("                   were read as positions in this frame.")
    if frame_path is not None and settings.direction in (
        Direction.ZONE_TO_GEODETIC,
        Direction.GEODETIC_TO_GEODETIC,
    ):
        # The frame of the positions WRITTEN, on a job that writes them in a
        # frame other than its input's - the second half of the question the
        # line above answers. A same-frame job prints neither the line nor
        # the gap.
        written = frame_path.target
        add(f"Written in         {written.code} - {written.name}")
        add("                   The latitudes and longitudes written are")
        add("                   positions in this frame.")
    add("")
    add("Precision written:")
    add(f"  Coordinates and elevations  {settings.output_unit.decimals} decimal places")
    add("  Scale and combined factors  8 decimal places")
    add("  Convergence angles          degrees-minutes-seconds to 0.01 second")
    add("  Latitude and longitude      8 decimal places (about 1 mm)")
    add("")

    # ---------------------------------------------------------------- zones
    add(_THIN)
    add("COORDINATE SYSTEMS")
    add(_THIN)
    if (
        settings.direction is Direction.VERTICAL_ONLY
        and settings.source_zone is None
    ):
        # An empty section would read as an omission; the truth is that this
        # job involves no zone at all, and the record says so.
        add("The input is geodetic positions (latitude / longitude). No State")
        add("Plane coordinate system is involved in this job.")
        add("")
    if geodetic_to_geodetic:
        # No zone at either end, and none fabricated: each end's FRAME is
        # what this job's coordinate systems are (plan decision D7).
        lines.extend(_geodetic_frame_block(frame_path.source, "FROM"))
        add("")
        lines.extend(_geodetic_frame_block(frame_path.target, "TO"))
        add("")
        add("No State Plane coordinate system is involved in this job.")
        add("")
    if settings.source_zone is not None:
        lines.extend(_zone_block(settings.source_zone, "FROM"))
        add("")
    if settings.target_zone is not None and settings.direction is not Direction.ZONE_TO_GEODETIC:
        lines.extend(_zone_block(settings.target_zone, "TO"))
        add("")

    if (
        settings.source_zone is not None
        and settings.target_zone is not None
        and settings.source_zone is not settings.target_zone
    ):
        add("Both zones are on the same reference frame, so this conversion is an")
        add("exact re-projection of the same physical positions: no datum shift is")
        add("applied and none is needed. Converting back returns the original")
        add("coordinates to well under a millimetre.")
        add("")

    # -------------------------------------------------------------- method
    add(_THIN)
    add("METHOD")
    add(_THIN)
    if zoneless:
        # No projection ran: the projection era's prose - manual sections,
        # zone constants, NCAT's projection anchors - would describe work
        # this job did not do.
        lines.extend(
            _method_without_a_zone(result, frame_path, transformation, swap_models)
        )
    else:
        lines.extend(_method_and_verification(settings))
    if frame_path is not None:
        lines.extend(
            _frame_transformation_block(result, frame_path, verified=not zoneless)
        )

    if result.geoid_model:
        # Resolved through the registry so the tile name and digest printed
        # here are the record's own - a GEOID12B job must not be documented
        # with GEOID18's file and checksum (WP-V5). For a GEOID18 job every
        # character below is what this record printed before the registry.
        geoid_record = geoid_model_by_name(result.geoid_model)
        add(
            f"Geoid model        {geoid_record.name}, NGS grid tile "
            f"{geoid_record.tile_filename}"
        )
        add(f"                   SHA-256 {geoid_record.sha256}")
        add("                   Geoid heights are NEGATIVE throughout Michigan:")
        add("                   the ellipsoid lies above the geoid here.")
        add("")
        if zoneless:
            # This job's METHOD names no manual, so "manual section 4.1"
            # would point at nothing the record set out.
            add("Elevation factor   R / (R + H + N), NOAA Manual NOS NGS 5 section 4.1")
        else:
            add("Elevation factor   R / (R + H + N), manual section 4.1")
        add(f"                   R = {MEAN_EARTH_RADIUS_M:,.0f} m mean earth radius")
        # "from the input file" was true until WP-V6: a vertical job shifts
        # the height between datums BEFORE the factors are computed, so the H
        # here is the height the factors actually used, which the audit CSV
        # carries per point.
        add("                   H = orthometric height as used for the factors")
        add("                   N = geoid height, interpolated from the grid above")
        if not zoneless:
            # A job with no zone has no grid scale factor to multiply.
            add("Combined factor    grid scale factor x elevation factor")
        add("")
    else:
        add("Geoid model        not applied; no elevation or combined factors")
        add("                   were computed for this job.")
        add("")

    # Before the vertical account, because h -> H runs before the datum
    # shift does, and a METHOD section read top to bottom should be the order
    # the program actually worked in. Pinned.
    if ellipsoid_model_name is not None:
        lines.extend(
            _ellipsoid_height_method_block(
                settings, ellipsoid_model_name, frame_path
            )
        )

    if vertical:
        lines.extend(
            _vertical_method_block(
                settings, transformation, result, zoneless=zoneless
            )
        )
        if swap_models is not None:
            lines.extend(_geoid_swap_method_block(swap_models))

    # ------------------------------------------------------------- summary
    add(_THIN)
    add("SCALE FACTOR SUMMARY")
    add(_THIN)
    if settings.direction is Direction.VERTICAL_ONLY:
        # The factors' provenance in the one direction with no output zone.
        # Two different truths depending on the input system, and the record
        # must state the one that applies (the input-zone / no-zone split
        # job._convert_row computes by).
        if settings.source_zone is not None:
            add("No output zone exists in this mode, so the grid scale factor,")
            add("convergence and combined factor below are the INPUT zone's at")
            add("each point - exactly as a State Plane to geodetic job reports")
            add("them.")
        else:
            add("No State Plane zone is involved in this job, so no grid scale")
            add("factor and no combined factor exists for any point - those")
            add(f"cells read {fmt.NOT_AVAILABLE!r}, never a fabricated 1.0. The elevation")
            add("factor needs no zone and is still computed from the geoid")
            add("model at each position.")
        add("")
    elif geodetic_to_geodetic:
        # The vertical-only geodetic job's sentence, for the other direction
        # with no zone anywhere.
        add("No State Plane zone is involved in this job, so no grid scale")
        add("factor and no combined factor exists for any point - those")
        add(f"cells read {fmt.NOT_AVAILABLE!r}, never a fabricated 1.0. The elevation")
        add("factor needs no zone and is still computed from the geoid")
        add("model at each position.")
        add("")
    add("Per-point values are in the _full.csv export. Summary across this job:")
    add("")
    lines.extend(_factor_summary(result))
    add("")

    # ------------------------------------------------------------ elevation
    missing = result.points_without_elevation
    add(_THIN)
    add("ELEVATIONS")
    add(_THIN)
    # Three causes, and this section must not flatten them into one. The first
    # two are genuinely absent elevations. The THIRD is a point whose Z column
    # was read perfectly well, and whose factors are absent only because the
    # shipped GEOID18 tile does not reach its position. Describing that point
    # as having a blank Z field is a false statement in an audit document, and
    # it is the statement this section used to make (WP-R2 fix C).
    #
    # ``Factors.orthometric_height`` is what separates them: it is the height
    # the job read, present whether or not a geoid height was found, so a
    # factor-less point that still carries one is a geoid miss - OR, on a job
    # that applied no geoid model at all, simply a point nothing was looked up
    # for. Those are different statements and the record must make the right
    # one: "the grid does not reach this point" is false when no grid was ever
    # consulted, and the old wording made exactly that claim on a
    # geoid-disabled job (found at WP-V5, when the model name became the
    # result's own and the sentence would otherwise have read "the None grid").
    no_geoid = [p for p in missing if p.factors.orthometric_height is not None]
    absent = [p for p in missing if p.factors.orthometric_height is None]
    # The FOURTH cause, WP-V6's: the Z field was read perfectly well, but the
    # vertical shift could not be computed (the point sits outside the VERTCON
    # grids), so no target-datum height exists and the elevation was REFUSED
    # rather than passed through unshifted. Calling that a "blank elevation
    # field" would be a false statement about a populated field in an audit
    # document - the exact defect WP-R2 fix C removed for the geoid, arriving
    # through a new door (WP-V6 review gate, HIGH 1). ``row.elevation`` is what
    # separates it: None for a genuinely blank or zeroed field, present here.
    unshifted = [p for p in absent if p.row.elevation is not None]
    absent = [p for p in absent if p.row.elevation is None]

    if not missing:
        add(f"All {len(result.points)} points carried a usable elevation.")
    else:
        if absent:
            add(
                f"{len(absent)} of {len(result.points)} points had NO usable "
                f"elevation."
            )
        if unshifted and swap_models is not None:
            # A swap job consults no VERTCON grid; its only refusable lookup
            # is the geoid tiles, so the VERTCON sentence below would be a
            # false statement about a grid never read (the WP-R2 fix C
            # class). A job is either a swap or a datum shift - the
            # compound form refuses before any point converts - so the
            # branch is total.
            add(
                f"{len(unshifted)} of {len(result.points)} points carried an "
                f"elevation that could NOT be re-derived from "
                f"{swap_models[0].name} to {swap_models[1].name}: the point "
                f"lies outside the geoid tiles this program ships. The Z "
                f"field was read; the elevation is deliberately not written, "
                f"because the height in hand is stated against "
                f"{swap_models[0].name} and every elevation this job writes "
                f"is stated against {swap_models[1].name}."
            )
        elif (
            unshifted
            and ellipsoid_model_name is not None
            and not settings.vertical_mode.converts_elevations
        ):
            # HORIZONTAL: the Z column DOES carry these heights - passed
            # through, as this mode always does - so "deliberately not
            # written" would contradict the file sitting beside this record.
            # Only the factors were lost (closing gate, MEDIUM 2).
            add(
                f"{len(unshifted)} of {len(result.points)} points carried an "
                f"ellipsoid height with no geoid separation available: the "
                f"point lies outside the {ellipsoid_model_name} tile this "
                f"program ships. The Z column carries the ellipsoid height "
                f"exactly as supplied, unconverted, as it does for every "
                f"point of a horizontal job; what is missing is the "
                f"orthometric height H = h - N, and without it there is no "
                f"elevation factor and no combined factor for these points."
            )
        elif unshifted and ellipsoid_model_name is not None:
            # The THIRD cause of a refused-but-populated Z, and it needed its
            # own branch for the reason the swap branch above needed one: an
            # ellipsoid-input job that fails here read no VERTCON grid at all
            # - on an identity job none is even loaded - so the sentence below
            # would name a grid that was never consulted. The same WP-R2 fix C
            # class arriving through a third door, caught by the design review
            # before this feature shipped rather than by a gate afterwards.
            add(
                f"{len(unshifted)} of {len(result.points)} points carried an "
                f"ellipsoid height that could NOT be converted to an "
                f"orthometric height: the point lies outside the "
                f"{ellipsoid_model_name} tile this program ships, so no geoid "
                f"separation exists there and H = h - N has no value. The Z "
                f"field was read; the elevation is deliberately not written, "
                f"because the height in hand is measured from the ellipsoid "
                f"and every elevation this job writes is measured from the "
                f"geoid."
            )
        elif unshifted:
            add(
                f"{len(unshifted)} of {len(result.points)} points carried an "
                f"elevation that could NOT be converted between vertical "
                f"datums: the point lies outside the VERTCON grids. The Z "
                f"field was read; the elevation is deliberately not written, "
                f"because the height in hand is in the source vertical datum "
                f"and every elevation this job writes claims the target one."
            )
        if no_geoid and result.geoid_model:
            add(
                f"{len(no_geoid)} of {len(result.points)} points carried an "
                # A geoid miss with a model applied: result.geoid_model names
                # the grid that was actually consulted.
                f"elevation the {result.geoid_model} grid does not reach."
            )
        elif no_geoid:
            add(
                f"{len(no_geoid)} of {len(result.points)} points carried an "
                f"elevation, but no geoid model was applied to this job, so "
                f"no geoid height was looked up for any of them."
            )
        add("")
        if frame_path is None and not zoneless:
            add("For those points the elevation factor and combined factor are written")
            add(f"as {fmt.NOT_AVAILABLE!r} in the exports. They are NOT set to 1.0, and the grid")
            add("scale factor is not substituted for the combined factor: there is no")
            add("honest combined factor without an elevation, and a plausible-looking")
            add("number here would travel onto a drawing. The horizontal conversion is")
            add("unaffected - it does not depend on elevation at all.")
        else:
            # "does not depend on elevation at all" is false across a frame
            # transformation: HTDP is handed a height for every point, h = 0
            # where none was recorded (plan decision D6), and the result moves
            # with it. What remains true is stated, and the rest is pointed at.
            # A job with no zone has no grid scale factor, no combined factor
            # and no horizontal conversion to speak of (plan W4b).
            factors = (
                f"the elevation factor is written as {fmt.NOT_AVAILABLE!r} in "
                f"the exports. It is NOT set to 1.0. The positions do not use "
                f"it."
                if zoneless
                else f"the elevation factor and combined factor are written as "
                f"{fmt.NOT_AVAILABLE!r} in the exports. They are NOT set to "
                f"1.0, and the grid scale factor is not substituted for the "
                f"combined factor. The horizontal conversion does not use "
                f"these factors."
            )
            handed = (
                " The height each point's frame transformation was handed is "
                "stated under FRAME TRANSFORMATION, and per point in the "
                "_full.csv export."
                if frame_path is not None
                else ""
            )
            lines.extend(textwrap.wrap(f"For those points {factors}{handed}", width=78))
        add("")
        if absent:
            add("A Z field that is blank, or that holds exactly 0.00, is treated as")
            add("'not recorded'. Michigan's lowest natural point is Lake Erie at about")
            add("571 feet, so a genuine survey elevation of exactly zero does not")
            add("occur here. This is a stated convention of this program, not")
            add("something the source documents specify.")
            add("")
            blank = [p for p in absent if not p.row.elevation_was_zero]
            zeroed = [p for p in absent if p.row.elevation_was_zero]
            if blank:
                add(f"  Blank elevation field ({len(blank)}):")
                lines.extend(_point_id_block(blank))
            if zeroed:
                add(f"  Elevation field held exactly 0.00 ({len(zeroed)}):")
                lines.extend(_point_id_block(zeroed))
            if no_geoid and result.geoid_model:
                add("")
        if no_geoid and result.geoid_model:
            # Only when a model was applied: on a no-geoid-model job the count
            # line above already says why the factors are absent, and this
            # block's "position lies outside the grid tile" would be a false
            # statement about a lookup that never happened.
            add(
                f"  Elevation recorded, but no {result.geoid_model} geoid height at "
                f"this position ({len(no_geoid)}):"
            )
            lines.extend(_point_id_block(no_geoid))
            add("")
            add("  These Z fields were read and are written to the exports. They are")
            add("  NOT blank and they are NOT zero. What is missing is the geoid")
            add("  height, because the position lies outside the grid tile this")
            add("  program ships, and without it there is no elevation factor. The")
            add("  HORIZONTAL coordinate of each point is unaffected and stands: it")
            add("  does not depend on elevation at all. Each point is named again,")
            add("  with its position, under WARNINGS below.")
        if unshifted and swap_models is not None:
            add("")
            add(
                f"  Elevation recorded, but not convertible between geoid "
                f"models ({len(unshifted)}):"
            )
            lines.extend(_point_id_block(unshifted))
            add("")
            add("  These Z fields were read. They are NOT blank and they are NOT")
            add("  zero. The position lies outside the geoid tiles this program")
            add(
                f"  ships, so no {swap_models[0].name} or "
                f"{swap_models[1].name} geoid height exists there, and the"
            )
            add("  elevation is deliberately absent from the exports rather than")
            add("  written unconverted. The HORIZONTAL coordinate of each point is")
            add("  unaffected and stands. Each point is named again, with its")
            add("  position, under WARNINGS below.")
        elif (
            unshifted
            and ellipsoid_model_name is not None
            and not settings.vertical_mode.converts_elevations
        ):
            add("")
            add(
                f"  Ellipsoid height recorded and written, but no geoid "
                f"separation exists there ({len(unshifted)}):"
            )
            lines.extend(_point_id_block(unshifted))
            add("")
            add("  These Z fields were read. They are NOT blank and they are NOT")
            add("  zero, and they ARE written to the exports - horizontal mode")
            add("  carries the supplied height through unchanged. They hold")
            add(
                f"  ELLIPSOID heights, and the position lies outside the "
                f"{ellipsoid_model_name}"
            )
            add("  tile this program ships, so no geoid separation exists there")
            add("  and the orthometric height H = h - N could not be derived.")
            add("  Without it there is no elevation factor and no combined")
            add("  factor for these points. The HORIZONTAL coordinate of each")
            add("  point is unaffected and stands. Each point is named again,")
            add("  with its position, under WARNINGS below.")
        elif unshifted and ellipsoid_model_name is not None:
            # The detail block's copy of the third branch. The summary above
            # has the same three-way split; both had to gain it, because this
            # section states the same fact twice - once counted, once with the
            # points named - and a reader who scrolled to the named list would
            # otherwise be told about a grid the job never opened.
            add("")
            add(
                f"  Ellipsoid height recorded, but no geoid separation exists "
                f"there ({len(unshifted)}):"
            )
            lines.extend(_point_id_block(unshifted))
            add("")
            add("  These Z fields were read. They are NOT blank and they are NOT")
            add(
                f"  zero. They hold ELLIPSOID heights, and the position lies "
                f"outside the"
            )
            add(
                f"  {ellipsoid_model_name} tile this program ships, so no geoid "
                f"separation"
            )
            add("  exists there and H = h - N has no value. The elevation is")
            add("  deliberately absent from the exports rather than written")
            add("  unconverted: a height measured from the ellipsoid, sitting in a")
            add("  column of heights measured from the geoid, would look ordinary")
            add("  and be wrong by about 34 m. The HORIZONTAL coordinate of each")
            add("  point is unaffected and stands. Each point is named again, with")
            add("  its position, under WARNINGS below.")
        elif unshifted:
            add("")
            add(
                f"  Elevation recorded, but not convertible between vertical "
                f"datums ({len(unshifted)}):"
            )
            lines.extend(_point_id_block(unshifted))
            add("")
            add("  These Z fields were read. They are NOT blank and they are NOT")
            add("  zero. The position lies outside the VERTCON grids, so no shift")
            add("  to the target vertical datum exists, and the elevation is")
            add("  deliberately absent from the exports rather than written")
            add("  unconverted: an unconverted height in a column that claims the")
            add("  target datum would look ordinary and be wrong. The HORIZONTAL")
            add("  coordinate of each point is unaffected and stands. Each point is")
            add("  named again, with its position, under WARNINGS below.")
    if vertical:
        if lines and lines[-1] != "":
            # One separating blank, not two: some branches above already end
            # on one (WP-V7 review gate, LOW 4).
            add("")
        if swap_models is not None:
            lines.extend(
                _geoid_swap_elevation_block(
                    result, transformation, swap_models, settings.input_unit
                )
            )
        else:
            lines.extend(_vertical_elevation_block(result, transformation))
    add("")

    # ------------------------------------------------------------- warnings
    add(_THIN)
    add("WARNINGS")
    add(_THIN)
    all_warnings = result.warnings
    # Warnings about the JOB, not a point (JobResult.job_warnings): today only
    # the realization period of plan decision D9. JobResult.warnings does not
    # include them, so they are read here, beside it, and printed first,
    # because they are about every point at once. Empty on every same-frame
    # job, whose WARNINGS section is unchanged by a byte.
    job_warnings = result.job_warnings
    if not all_warnings and not job_warnings:
        if zoneless:
            # No zone, so no "inside its zone" to have been.
            add("None. Every point converted cleanly.")
        else:
            add("None. Every point converted cleanly, inside its zone.")
    else:
        if job_warnings:
            add(
                f"{len(all_warnings)} warning(s) across {len(result.points)} "
                f"points, and {len(job_warnings)} about the job as a whole."
            )
        else:
            add(f"{len(all_warnings)} warning(s) across {len(result.points)} points.")
        add("")
        add("A warning is not an error. Every point below was converted, and the")
        add("coordinate written for it is correct. A warning means something about")
        add("the job is worth a second look.")
        job_codes = []
        for warning in job_warnings:
            if warning.code not in job_codes:
                job_codes.append(warning.code)
        for code in job_codes:
            add("")
            add(f"  {_warning_heading(code)} (the whole job)")
            add("")
            for warning in job_warnings:
                if warning.code is code:
                    add(f"    {warning.message}")
        for code in _warning_codes_present(result):
            group = result.warnings_of(code)
            if not group:
                continue
            add("")
            add(f"  {_warning_heading(code)} ({len(group)} point(s))")
            add("")
            for point_id, warning in group[:20]:
                add(f"    {warning.message}")
            if len(group) > 20:
                add(f"    ... and {len(group) - 20} more; see the _full.csv export.")
    add("")

    # -------------------------------------------------------------- files
    add(_THIN)
    add("FILES WRITTEN")
    add(_THIN)
    from michspc.fileio.exports import member_names, output_stem

    stem = output_stem(result)
    names = member_names(result)

    add(f"This job wrote ONE file: {stem}.zip")
    add("")
    count = "four" if "pnezd_dms" in names else "three"
    add(f"It contains the {count} files below, and they are kept together on")
    if geodetic_to_geodetic:
        # No zone was involved; what the file was moved between is frames.
        add("purpose. A coordinate file that has been moved between reference")
        add("frames should not circulate without the record explaining how it")
        add(f"was derived, so the export is a single archive rather than {count}")
        add("loose files.")
    elif zoneless:
        # Vertical only on geodetic positions: nothing moved between zones or
        # frames; the file is the product of a conversion all the same.
        add("purpose. A coordinate file produced by a conversion should not")
        add("circulate without the record explaining how it was derived, so the")
        add(f"export is a single archive rather than {count} loose files.")
    else:
        add("purpose. A coordinate file that has been moved between zones should not")
        add("circulate without the record explaining how it was derived, so the")
        add(f"export is a single archive rather than {count} loose files.")
    add("")
    add(f"  {names['pnezd']}")
    lines.extend(_clean_export_block(settings, frame_path))
    add("")
    if "pnezd_dms" in names:
        # The DMS sibling (docs/DESIGN.md #67): the same rows, the position
        # restated. Says what it is for and what it is not, because a file
        # of angles in a PNEZD layout invites a CAD import it cannot survive.
        add(f"  {names['pnezd_dms']}")
        add("    The SAME rows as the file above - point, latitude, longitude,")
        add("    elevation, description, no header row - with the latitude and")
        add("    longitude restated as DEGREES MINUTES SECONDS to 5 places of a")
        add("    second and a hemisphere letter, N or S and E or W:")
        add("        42-43-57.00000 N   84-33-19.80000 W")
        add("    A DMS position has no sign convention to state. The elevation")
        add("    and description columns are identical to the file above.")
        add("    For reading and transcription. NOT for CAD import, and this")
        add("    program's own file reader will not read it back: it takes")
        add("    decimal degrees only. Convert from the _DD file.")
        add("")
    add(f"  {names['audit']}")
    if zoneless:
        # No zone: "both zones' coordinates" and "both convergence angles"
        # would describe columns that hold nothing for this job. A
        # vertical-only job holds its position in two frames only when HTDP
        # carried it to NAD83(2011) for the lookups.
        add("    Every computed quantity for every point, with a header row: the")
        position = (
            "position in both frames"
            if frame_path is not None
            else "position the file supplied"
        )
        add(f"    {position}, geoid and ellipsoid height, the")
        add("    elevation factor, and any warnings. No zone is involved, so the")
        add("    scale-factor and convergence columns read N/A. This is the file")
        add("    that answers 'how was this number derived' without re-running")
        add("    anything.")
    else:
        add("    Every computed quantity for every point, with a header row: both")
        add("    zones' coordinates, the geodetic position the conversion pivoted")
        add("    through, geoid and ellipsoid height, both convergence angles, the")
        add("    grid, elevation and combined factors, and any warnings. This is the")
        add("    file that answers 'how was this number derived' without re-running")
        add("    anything.")
    if frame_path is not None:
        external = _external_frame(frame_path).code
        heights = (
            " the ellipsoid height before and after it,"
            if settings.input_height_kind is HeightKind.ELLIPSOID
            else ""
        )
        # The last sentence is a claim about every heading of the audit CSV,
        # and it is pinned against the CELLS (tests/test_frame_disclosure.py,
        # interim gate 2 finding H1): each latitude, longitude and ellipsoid
        # height heading must name the frame its values are in. It said
        # "Every position" until that gate - false then of the four Source /
        # Target degree headings, and still not a claim the grid northings
        # could meet, which are in the zone their row's zone cell names.
        lines.extend(
            textwrap.wrap(
                f"For this job it also carries, per point and after "
                f"Description, the frame transformation: the path, the "
                f"observation date and its decimal year, the height "
                f"convention, the {external} position in decimal degrees and "
                f"in DMS,{heights} and the velocity HTDP applied. Every "
                f"latitude, longitude and ellipsoid height column names its "
                f"frame.",
                width=78,
                initial_indent="    ",
                subsequent_indent="    ",
            )
        )
    if vertical and swap_models is not None:
        add("    For this job it also carries, per point: both vertical datums,")
        add("    the elevation before the geoid change, the geoid change applied")
        add("    (the Vertical shift column; the Shift sigma column reads N/A),")
        add("    the source geoid model, and the geoid model the Z column and")
        add("    the factors are stated against.")
    elif vertical:
        add("    For this vertical job it also carries, per point: both vertical")
        add("    datums, the source-datum elevation before the shift, the modeled")
        add("    shift applied, its one-sigma uncertainty, and the geoid model")
        add("    the factors were computed from.")
        if settings.source_geoid_model is not None:
            add("    The Source geoid model column names the model the input")
            add("    elevations were stated against.")
    add("")
    add(f"  {names['report']}")
    add("    This file.")
    add("")
    add(_RULE)
    add("  END OF JOB RECORD")
    add(_RULE)

    return "\n".join(lines) + "\n"


def _point_id_block(points, per_line: int = 8) -> list[str]:
    """Point identifiers wrapped to a readable width."""
    ids = [p.point_id for p in points]
    lines = []
    for start in range(0, len(ids), per_line):
        lines.append("    " + ", ".join(ids[start : start + per_line]))
    return lines


def _factor_summary(result: JobResult) -> list[str]:
    """Minimum, maximum and mean of each factor, in value and parts per million."""
    lines = []

    def block(label: str, values) -> None:
        if not values:
            lines.append(f"  {label:<26} {fmt.NOT_AVAILABLE}")
            return
        low, high = min(values), max(values)
        mean = statistics.fmean(values)
        lines.append(f"  {label}")
        lines.append(
            f"    minimum  {fmt.factor(low):<14} "
            f"({fmt.signed_parts_per_million(low)} ppm)"
        )
        lines.append(
            f"    maximum  {fmt.factor(high):<14} "
            f"({fmt.signed_parts_per_million(high)} ppm)"
        )
        lines.append(
            f"    mean     {fmt.factor(mean):<14} "
            f"({fmt.signed_parts_per_million(mean)} ppm)"
        )

    block("Grid scale factor", result.grid_scale_factors)
    lines.append("")
    combined = result.combined_factors
    block("Combined factor", combined)
    if combined:
        lines.append("")
        lines.append(
            "  Multiply a ground distance by the combined factor to get the grid"
        )
        lines.append(
            "  distance; divide a grid distance by it to get ground. Divide a grid"
        )
        lines.append("  area by its square to get ground area (manual section 4.1).")
    else:
        lines.append("")
        # WHY the tuple is empty decides the sentence - saying "no point
        # carried a usable elevation" on a geodetic-input vertical-only job
        # whose every point carried one was a false statement in a sealed
        # record, contradicted by the ELEVATIONS section five lines below
        # (vertical-only gate, MEDIUM 1; the #42-finding-3 class). At HEAD
        # the implication held because grid_scale_factor was never None;
        # the no-zone path broke it and this sentence was not re-guarded.
        if result.settings.direction is Direction.VERTICAL_ONLY and (
            result.settings.source_zone is None
        ):
            lines.append(
                "  No combined factors exist for this job: no zone is involved"
            )
            lines.append(
                "  in a vertical-only conversion of geodetic positions, so there"
            )
            lines.append(
                "  is no grid scale factor to combine with the elevation factor."
            )
        elif result.settings.direction is Direction.GEODETIC_TO_GEODETIC:
            lines.append(
                "  No combined factors exist for this job: no zone is involved"
            )
            lines.append(
                "  in a geodetic-to-geodetic conversion, so there is no grid"
            )
            lines.append(
                "  scale factor to combine with the elevation factor."
            )
        else:
            lines.append(
                "  No combined factors were computed: no point carried a usable "
                "elevation."
            )
    return lines
