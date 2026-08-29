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
from datetime import datetime, timezone

from michspc import APP_NAME, __version__
from michspc.fileio import formatting as fmt
from michspc.fileio import vertcon
from michspc.fileio.geoid import geoid_model_by_name
from michspc.job import (
    Direction,
    JobResult,
    factors_geoid_model,
    factors_use_source_era,
    geoid_swap_models,
)
from michspc.spc.convert import WarningCode
from michspc.spc.factors import MEAN_EARTH_RADIUS_M
from michspc.spc.projection import constants_for
from michspc.spc.vertical import HeightKind, require_vertical_pair

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
    geodetic_input = settings.direction is Direction.GEODETIC_TO_ZONE or (
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


def _clean_export_block(settings) -> list[str]:
    """What the clean export's five columns hold. Direction-aware.

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
    if settings.direction is Direction.ZONE_TO_GEODETIC:
        return [
            "    The converted positions - NOT PNEZD, and NOT the same layout as",
            "    the input: point, latitude, longitude, elevation, description,",
            "    no header row.",
            "    Columns two and three are DECIMAL DEGREES to 8 places, written",
            f"    {settings.longitude_convention.value}.",
            f"    The elevation column is {unit.name} ({unit.code}).",
            "    Nothing else.",
        ]
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


def _zone_block(zone, label: str) -> list[str]:
    """A zone's full defining and derived constants, with citations."""
    definition = zone.definition
    constants = constants_for(zone)
    return [
        f"{label}: {zone.name}, zone {zone.code} ({zone.system})",
        f"  Reference frame           {zone.frame.code}",
        f"  Projection                Lambert conformal conic, two standard parallels",
        f"  Southern standard parallel  {definition.lat_south:.10f} deg N",
        f"  Northern standard parallel  {definition.lat_north:.10f} deg N",
        f"  Latitude of grid origin     {definition.lat_grid_origin:.10f} deg N",
        f"  Central meridian            {definition.lon_origin:.10f} deg "
        f"({-definition.lon_origin:.10f} deg west)",
        f"  False northing              {definition.northing_grid_origin:,.4f} m",
        f"  False easting               {definition.easting_origin:,.4f} m",
        f"  Central parallel (derived)  {constants.lat_origin:.10f} deg N",
        f"  Scale at central parallel   {constants.k_origin:.12f}",
        f"  Source: {zone.citation}",
    ]


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


def _vertical_method_block(settings, transformation, result) -> list[str]:
    """The METHOD section's account of the vertical transformation.

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
        add("")
        lines.extend(
            _labelled_paragraph(
                "Factor height",
                f"The elevation and combined factors were computed from the "
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


def _ellipsoid_height_method_block(settings, model_name) -> list[str]:
    """The METHOD section's account of an ellipsoid-height input.

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
    add(
        f"Input heights      stated as ELLIPSOID heights (above the GRS 80 "
        f"ellipsoid),"
    )
    add("                   as a GNSS receiver produces them.")
    add(
        f"Geoid model        {record.name}, NGS grid tile "
        f"{record.tile_filename}"
    )
    add(f"                   SHA-256 {record.sha256}")
    lines.extend(
        _labelled_paragraph(
            "Arithmetic",
            f"The orthometric height is derived at each point's own "
            f"horizontal position: H = h - N, where h is the height the Z "
            f"column supplied and N is the {record.name} geoid height there, "
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
    else:
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


def build_report(result: JobResult) -> str:
    """Render the job record."""
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
    if settings.direction is Direction.GEODETIC_TO_ZONE or (
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
    add("Authority          NOAA Manual NOS NGS 5, State Plane Coordinate System")
    add("                   of 1983 (Stem, January 1989; reprinted with minor")
    add("                   corrections March 1990)")
    add("")
    add("Equations          The rigorous Lambert conformal conic mapping")
    add("                   equations of section 3.1 - zone constants (3.12),")
    add("                   direct conversion (3.13), inverse conversion (3.14).")
    add("                   Exact at any latitude, with no approximation term.")
    add("")
    add("Ellipsoid          GRS 80, the ellipsoid of NAD 83 (manual section 1.7).")
    add("                   Only the semimajor axis and the flattening are stored;")
    add("                   every other constant is derived from those two.")
    add("")
    add("HOW THIS SOFTWARE IS VERIFIED")
    add("")
    add("The zone constants used above are not taken on trust. The manual")
    add("publishes, in Appendix C, the constants NGS computed for every Lambert")
    add("zone. This software stores only the DEFINING constants - the standard")
    add("parallels, the grid origin, the central meridian - and derives the rest.")
    add("Its test suite recomputes all of them and requires a match with NGS's")
    add("published figures to the last decimal place NGS printed, for all three")
    add("Michigan zones.")
    add("")
    add("The conversion itself is checked against the National Geodetic Survey's")
    add("own Coordinate Conversion and Transformation Tool (NCAT). Twenty-seven")
    add("positions spanning the three zones were converted by NCAT, and those")
    add("results are held in the test suite as fixed reference values. This")
    add("software reproduces them to within 0.5 mm - which is the precision NCAT")
    add("publishes, so the agreement is as close as the reference permits.")
    add("")
    add("Both checks compare this software against NGS. Neither compares it")
    add("against itself.")
    add("")

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
        add("Elevation factor   R / (R + H + N), manual section 4.1")
        add(f"                   R = {MEAN_EARTH_RADIUS_M:,.0f} m mean earth radius")
        # "from the input file" was true until WP-V6: a vertical job shifts
        # the height between datums BEFORE the factors are computed, so the H
        # here is the height the factors actually used, which the audit CSV
        # carries per point.
        add("                   H = orthometric height as used for the factors")
        add("                   N = geoid height, interpolated from the grid above")
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
            _ellipsoid_height_method_block(settings, ellipsoid_model_name)
        )

    if vertical:
        lines.extend(_vertical_method_block(settings, transformation, result))
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
        add("For those points the elevation factor and combined factor are written")
        add(f"as {fmt.NOT_AVAILABLE!r} in the exports. They are NOT set to 1.0, and the grid")
        add("scale factor is not substituted for the combined factor: there is no")
        add("honest combined factor without an elevation, and a plausible-looking")
        add("number here would travel onto a drawing. The horizontal conversion is")
        add("unaffected - it does not depend on elevation at all.")
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
    if not all_warnings:
        add("None. Every point converted cleanly, inside its zone.")
    else:
        add(f"{len(all_warnings)} warning(s) across {len(result.points)} points.")
        add("")
        add("A warning is not an error. Every point below was converted, and the")
        add("coordinate written for it is correct. A warning means something about")
        add("the job is worth a second look.")
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
    add("It contains the three files below, and they are kept together on")
    add("purpose. A coordinate file that has been moved between zones should not")
    add("circulate without the record explaining how it was derived, so the")
    add("export is a single archive rather than three loose files.")
    add("")
    add(f"  {names['pnezd']}")
    lines.extend(_clean_export_block(settings))
    add("")
    add(f"  {names['audit']}")
    add("    Every computed quantity for every point, with a header row: both")
    add("    zones' coordinates, the geodetic position the conversion pivoted")
    add("    through, geoid and ellipsoid height, both convergence angles, the")
    add("    grid, elevation and combined factors, and any warnings. This is the")
    add("    file that answers 'how was this number derived' without re-running")
    add("    anything.")
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
        else:
            lines.append(
                "  No combined factors were computed: no point carried a usable "
                "elevation."
            )
    return lines
