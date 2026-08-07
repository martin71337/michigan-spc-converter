"""Vertical datums, and the registry of transformations between them.

An orthometric height is meaningless without the vertical datum it is expressed
in. Across the Michigan window the VERTCON 3.0 grid runs from **-0.411640 m to
+0.348303 m** - it changes sign, so the difference is not a bias to be
subtracted out (docs/PLAN-vertical-datums.md section 2.7, measured). At the
typical Michigan value it is about half a foot, which is a boundary-relevant
amount on a sealed drawing when it lands in a Z column that looks exact. So
every height carried through this program is
tagged with its datum, and a pair of datums with no published transformation is
refused rather than passed through.

This module mirrors ``michspc/spc/frames.py``: typed records, an explicit
registry, and a ``require_*`` that refuses loudly instead of guessing. It is the
seam DESIGN.md amendments #22 and #32 asked for - NAPGD2022 arrives later as a
record plus grids plus a citation, not as an excavation.

**The sign convention, which is the dangerous part.** The VERTCON 3.0
transformation grid stores ``NAVD88 - NGVD29`` in **metres**, and that value is
**ADDED** to an NGVD 29 height to obtain the NAVD 88 height. The inverse is the
same grid with the sign reversed - one grid, one data path, two directions
(docs/PLAN-vertical-datums.md sections 2.3 and 2.4, both measured against NGS
NCAT before any of this code existed). This is the defect class the project has
already been burned by (DESIGN.md #1, MATLAB defect 2), so the direction is not
left to a comment: each record carries ``sign``, and
``VerticalTransformation.direction_statement`` writes the arithmetic out in
words **from that same sign**, so the record and the computation cannot disagree
about which way the shift goes.

**No file I/O, no Qt, no network.** The grid value is passed *in*, exactly as
``factors.factors_at`` takes the geoid height as a parameter rather than reading
the tile. The file layer reads ``.trn`` and ``.err``; this module knows only
what a grid value means once it has been read. That keeps every rule here
testable without the 2.4 MB grids present.

**Backwards compatibility is a requirement, not an assumption** (DESIGN.md
amendment #32). A job converted under this program in 2026 must still convert,
and still reproduce, after NAPGD2022 lands: a surveyor's older work does not
stop existing because NGS published something. Practically, **the registry keeps
every pair it has ever carried**. ``REQUIRED_VERTICAL_PAIRS`` states that as an
append-only list which may grow and may never shrink, and this module refuses to
import if the registry has lost one of them - so a deleted pair fails loudly at
startup rather than quietly at the first job that needs it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class VerticalDatumError(Exception):
    """Base class for every refusal in this module.

    Callers that only need "the vertical conversion was refused, say so" catch
    this; ``job.run`` and the interface distinguish the subclasses below,
    because a datum that is not usable yet and a pair that was never published
    are different things to tell a user.
    """


class VerticalDatumNotUsableError(VerticalDatumError):
    """Raised when a datum is declared in this module but not usable.

    NAPGD2022 is declared and not usable. It is not a typo and not a missing
    feature flag: no NAVD 88 to NAPGD2022 transformation product exists, and NGS
    NCAT returns an empty response for that request
    (docs/PLAN-vertical-datums.md section 1, V0 gate).
    """


class VerticalTransformationUnavailableError(VerticalDatumError):
    """Raised when no published transformation exists for a pair of datums.

    Not a warning and not a silent pass-through: leaving a height alone while
    calling it converted is exactly the failure the tier sentence exists to
    prevent.
    """


class VerticalDatumStatus(Enum):
    """Whether this program may actually convert heights in a datum.

    ``DECLARED_NOT_USABLE`` is a real state, not a placeholder: the datum exists
    in the record so that the refusal has something concrete to refuse and the
    shape of the eventual addition is visible - the role ``NATRF2022`` plays in
    ``frames.py``.
    """

    USABLE = "usable"
    DECLARED_NOT_USABLE = "declared but not usable"


@dataclass(frozen=True)
class VerticalDatum:
    """A vertical datum that a height can be expressed in."""

    code: str
    """Short token naming the datum, e.g. "NAVD88".

    Spelled the way NGS NCAT spells it. DESIGN.md amendment #22 records that
    NCAT's vertical transformation is driven by ``inVertDatum`` /
    ``outVertDatum``; it names those *parameters* and not their permitted
    values, so treat this as a deliberate convention chosen to match NCAT
    rather than a quoted token list - the point of it is that a datum named in
    one of this program's output files can be handed straight back to NCAT for
    checking. Confirm the exact spellings against NCAT when WP-V1 freezes the
    anchor lattice.
    """

    name: str
    citation: str
    status: VerticalDatumStatus

    @property
    def is_usable(self) -> bool:
        return self.status is VerticalDatumStatus.USABLE

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


NGVD29 = VerticalDatum(
    code="NGVD29",
    name="National Geodetic Vertical Datum of 1929",
    citation=(
        "NGS VERTCON 3.0 Digital Archive, geodesy.noaa.gov/pub/vertcon3/"
        "20190601release/, documented in NOAA Technical Report NOS NGS 68; "
        "NCAT vertical datum token NGVD29 (DESIGN.md #22)"
    ),
    status=VerticalDatumStatus.USABLE,
)

NAVD88 = VerticalDatum(
    code="NAVD88",
    name="North American Vertical Datum of 1988",
    citation=(
        "NGS VERTCON 3.0 Digital Archive, geodesy.noaa.gov/pub/vertcon3/"
        "20190601release/, documented in NOAA Technical Report NOS NGS 68; "
        "NCAT vertical datum token NAVD88 (DESIGN.md #22). The datum GEOID18 "
        "orthometric heights are defined against"
    ),
    status=VerticalDatumStatus.USABLE,
)

NAPGD2022 = VerticalDatum(
    code="NAPGD2022",
    name="North American-Pacific Geopotential Datum of 2022",
    citation=(
        "NGS NSRS modernization; GEOID2022 replaces GEOID18 and NAPGD2022 "
        "replaces NAVD 88 when it is released (DESIGN.md #22, #32)"
    ),
    status=VerticalDatumStatus.DECLARED_NOT_USABLE,
)
"""Declared but not yet usable.

No transformation to or from it exists as a published product, and NGS NCAT
returns an empty response for a NAVD88 to NAPGD2022 request - measured at the V0
gate (docs/PLAN-vertical-datums.md section 1). It is present so that the refusal
below has something concrete to refuse, and so the shape of the eventual
addition is visible. When it arrives it arrives as data: a status change here,
records in the registry below, and grids plus citations in the file layer.
"""


ALL_VERTICAL_DATUMS: tuple[VerticalDatum, ...] = (NGVD29, NAVD88, NAPGD2022)

_DATUMS_BY_CODE: Mapping[str, VerticalDatum] = MappingProxyType(
    {datum.code: datum for datum in ALL_VERTICAL_DATUMS}
)


def vertical_datum_by_code(code: str) -> VerticalDatum:
    """Look up a vertical datum by its code.

    Refuses an unknown code rather than guessing, and names what is available -
    the same contract as ``zones.zone_by_code`` and ``units.unit_by_code``.
    """
    key = str(code).strip()
    try:
        return _DATUMS_BY_CODE[key]
    except KeyError:
        known = ", ".join(f"{d.code} ({d.name})" for d in ALL_VERTICAL_DATUMS)
        raise KeyError(
            f"No vertical datum with code {code!r}. Known vertical datums "
            f"are: {known}."
        ) from None


# --------------------------------------------------------------------------
# Transformations.
#
# Model and release: VERTCON 3.0, release 20190601, from the VERTCON 3.0
# Digital Archive at geodesy.noaa.gov/pub/vertcon3/20190601release/Builds/
# ngvd29.navd88.conus/ and documented in NOAA Technical Report NOS NGS 68.
# Located, downloaded and checked at the V0 gate; file names, byte counts and
# SHA-256s are in docs/PLAN-vertical-datums.md section 2.1.
#
# NOT VERTCON 2.0, which is what both /PC_PROD/VERTCON/ and VDatum lead to.
# Measured against NCAT, 2.0 is off by up to 43.85 mm across Michigan where 3.0
# is off by 2.657 mm (plan section 2.6).
# --------------------------------------------------------------------------

_VERTCON3_MODEL = "VERTCON 3.0"
_VERTCON3_RELEASE = "20190601"

# The key names the NGS build the grid pair comes from - the directory name in
# the archive, not a file path. Resolving it to the actual .trn and .err files
# is the file layer's job; this module must not know what a file is.
_VERTCON3_CONUS_GRID_KEY = "ngvd29.navd88.conus"

# The per-point uncertainty is read from the companion error grid, not stated as
# a constant here, because it varies enormously: at 43.05 N, 86.20 W it is
# 0.3656 m against a modeled shift of -0.1466 m, which is 249% of the shift
# itself (plan section 2.8, measured against NCAT). A single job-level constant
# would understate that point by orders of magnitude while the shift beside it
# was printed to the millimetre.
#
# The BOUNDS quoted below are plan section 2.7's - the direct scan of the .err
# grid over the Michigan window, min +0.000004 m and max +0.365599 m. Plan
# section 2.8 summarises the same field as "0.001 m to 0.366 m, a factor of
# 366"; the two disagree at the floor, and 0.001 m is NCAT's printed resolution
# rather than a value the grid holds. This string is quoted verbatim into the
# job record (plan section 5.2), so it states what THIS program's reader can
# actually produce, which is the grid's own range. Flagged for the owner at the
# WP-V3 review gate (docs/DESIGN.md amendment #35); if section 2.8's figure is
# the authoritative one, this is the one line to change.
_VERTCON3_UNCERTAINTY_CITATION = (
    "Per-point one-sigma uncertainty from the companion VERTCON 3.0 error grid "
    "(.err), NOAA Technical Report NOS NGS 68. Measured across the Michigan "
    "window it ranges from 0.000004 m to 0.365599 m "
    "(docs/PLAN-vertical-datums.md section 2.7); the largest is 0.3656 m at "
    "43.05 N, 86.20 W, where the modeled shift is -0.1466 m - the uncertainty "
    "is 249% of the shift (section 2.8, measured against NGS NCAT)."
)

# NGS's own caveat, which must reach every output that carries a shifted height.
# DESIGN.md #22 records it as the top risk of this whole feature: a converted
# elevation looks exact, and this one is modeled.
_VERTCON3_CAVEAT = (
    "A VERTCON shift is MODELED, not measured. VERTCON cannot maintain the full "
    "vertical control accuracy of geodetic leveling: a published NAVD 88 "
    "benchmark value supersedes a modeled shift, and NGVD 29 network "
    "distortions of 20 cm or more exist (NGS, recorded in DESIGN.md #22). "
    "Agreement with NGS NCAT proves this program reads NGS's grid the way NGS "
    "reads it; NCAT is another implementation of the same model, not an "
    "independent measurement of the ground."
)

_IDENTITY_UNCERTAINTY_CITATION = (
    "No model is applied, so no modeled uncertainty is introduced. The height "
    "carries whatever uncertainty it arrived with."
)

_IDENTITY_CAVEAT = (
    "Source and target vertical datum are the same, so no shift is applied and "
    "the elevation is reported in the datum it was supplied in."
)


@dataclass(frozen=True)
class VerticalTransformation:
    """One published way to move a height from one vertical datum to another.

    An identity record - source and target the same datum - carries no model,
    no release and no grid, and its ``sign`` is 0. Identity is an explicit
    record rather than a ``source is target`` shortcut in the caller, because a
    NAVD 88 to NAVD 88 job is legitimate and the job record must be able to
    *state* "both datums NAVD 88, no shift applied" rather than have that fall
    out of an untested branch.
    """

    source: VerticalDatum
    target: VerticalDatum

    model: str | None
    """e.g. "VERTCON 3.0". ``None`` on an identity record, and that None is a
    statement - no model was applied - not a missing value."""

    release: str | None
    """e.g. "20190601". ``None`` on an identity record."""

    grid_key: str | None
    """Names the NGS grid build the file layer must load. ``None`` on an
    identity record: there is no grid to read, which is why ``apply_shift``
    refuses a grid value for one."""

    sign: int
    """+1, -1, or 0 for an identity.

    The shift applied to the source height is ``sign * grid_value``. The grid
    stores ``NAVD88 - NGVD29`` in metres, so NGVD 29 to NAVD 88 is +1 and the
    inverse is the same grid at -1 (plan sections 2.3 and 2.4, both measured
    against NCAT). Read ``direction_statement`` rather than this number: it is
    written from this number, so the two cannot disagree.
    """

    uncertainty_citation: str
    caveat: str

    def __post_init__(self) -> None:
        # if/raise, never assert: the suite and the shipped program both run
        # under -O, which strips asserts (DESIGN.md section 7).
        identity_fields = (self.model, self.release, self.grid_key)
        is_identity_shape = all(field is None for field in identity_fields)
        if not is_identity_shape and any(field is None for field in identity_fields):
            raise ValueError(
                f"Vertical transformation {self.source.code} -> "
                f"{self.target.code} is half-specified: model, release and "
                f"grid_key must be present together (a modeled transformation) "
                f"or absent together (an identity). Got model={self.model!r}, "
                f"release={self.release!r}, grid_key={self.grid_key!r}."
            )

        if self.sign not in (-1, 0, 1):
            raise ValueError(
                f"Vertical transformation {self.source.code} -> "
                f"{self.target.code} has sign {self.sign!r}. The sign selects "
                f"the direction the grid value is applied in and must be "
                f"exactly +1, -1, or 0 for an identity; it is not a scale "
                f"factor."
            )

        if is_identity_shape:
            if self.sign != 0:
                raise ValueError(
                    f"Vertical transformation {self.source.code} -> "
                    f"{self.target.code} has no grid but sign {self.sign}. An "
                    f"identity applies no grid value, so its sign is 0."
                )
            if self.source.code != self.target.code:
                # The dangerous one: an identity between two different datums
                # would silently relabel a height as though NGVD 29 and NAVD 88
                # were the same surface. They differ by about 0.15 m in
                # Michigan.
                raise ValueError(
                    f"Vertical transformation {self.source.code} -> "
                    f"{self.target.code} carries no grid, which would leave the "
                    f"height unchanged while relabelling its datum. Only a "
                    f"datum with itself may be an identity."
                )
        else:
            if self.sign == 0:
                raise ValueError(
                    f"Vertical transformation {self.source.code} -> "
                    f"{self.target.code} names grid {self.grid_key!r} but has "
                    f"sign 0, so the grid value would be discarded and the "
                    f"height left unchanged. A modeled transformation is +1 or "
                    f"-1."
                )
            if self.source.code == self.target.code:
                raise ValueError(
                    f"Vertical transformation {self.source.code} -> "
                    f"{self.target.code} is a datum with itself, yet names grid "
                    f"{self.grid_key!r}. Converting a datum to itself applies "
                    f"no shift."
                )

        for label, text in (
            ("uncertainty_citation", self.uncertainty_citation),
            ("caveat", self.caveat),
        ):
            if not text.strip():
                raise ValueError(
                    f"Vertical transformation {self.source.code} -> "
                    f"{self.target.code} has an empty {label}. Every record "
                    f"must be able to say what it does to a height and how well "
                    f"it is known; outputs quote these."
                )

    @property
    def is_identity(self) -> bool:
        """True when no grid is applied and the height is unchanged."""
        return self.grid_key is None

    @property
    def grid_quantity(self) -> str | None:
        """What the grid stores, in words. ``None`` for an identity.

        Derived from ``sign`` rather than stored, so it cannot drift from the
        arithmetic: the grid always stores the *positive* direction's
        difference, which is why the reverse record subtracts it.
        """
        if self.is_identity:
            return None
        if self.sign == 1:
            return f"{self.target.code} minus {self.source.code}"
        return f"{self.source.code} minus {self.target.code}"

    @property
    def direction_statement(self) -> str:
        """The arithmetic in words, written from ``sign``.

        This is what outputs quote. It exists so that reading a job record can
        never leave a surveyor unsure which way the shift went, and it is
        derived from the same field the computation uses so the record and the
        number are incapable of disagreeing.
        """
        if self.is_identity:
            return (
                f"Both elevations are {self.source.name} ({self.source.code}); "
                f"no shift is applied."
            )
        operator = "+" if self.sign == 1 else "-"
        return (
            f"{self.target.code} = {self.source.code} {operator} g, where g is "
            f"the {self.model} release {self.release} grid value in metres at "
            f"the point's horizontal position (grid {self.grid_key}, which "
            f"stores {self.grid_quantity})."
        )

    def __str__(self) -> str:
        return f"{self.source.code} -> {self.target.code}"


_IDENTITY_NAVD88 = VerticalTransformation(
    source=NAVD88,
    target=NAVD88,
    model=None,
    release=None,
    grid_key=None,
    sign=0,
    uncertainty_citation=_IDENTITY_UNCERTAINTY_CITATION,
    caveat=_IDENTITY_CAVEAT,
)

_IDENTITY_NGVD29 = VerticalTransformation(
    source=NGVD29,
    target=NGVD29,
    model=None,
    release=None,
    grid_key=None,
    sign=0,
    uncertainty_citation=_IDENTITY_UNCERTAINTY_CITATION,
    caveat=_IDENTITY_CAVEAT,
)

# Sign +1: the grid stores NAVD88 - NGVD29 in metres and it is ADDED to the
# NGVD 29 height. Anchored at 43.0 N, 84.5 W, where the grid gives -0.1402 m
# against NCAT's -0.1400 m - 0.2 mm apart, and NCAT prints only to the
# millimetre (plan section 2.3).
_NGVD29_TO_NAVD88 = VerticalTransformation(
    source=NGVD29,
    target=NAVD88,
    model=_VERTCON3_MODEL,
    release=_VERTCON3_RELEASE,
    grid_key=_VERTCON3_CONUS_GRID_KEY,
    sign=1,
    uncertainty_citation=_VERTCON3_UNCERTAINTY_CITATION,
    caveat=_VERTCON3_CAVEAT,
)

# Sign -1: the same grid, sign reversed. Verified against NCAT at five Michigan
# points, forward plus inverse summing to 0.00 mm at every one (plan section
# 2.4). One grid, one data path, two directions - not a second product.
_NAVD88_TO_NGVD29 = VerticalTransformation(
    source=NAVD88,
    target=NGVD29,
    model=_VERTCON3_MODEL,
    release=_VERTCON3_RELEASE,
    grid_key=_VERTCON3_CONUS_GRID_KEY,
    sign=-1,
    uncertainty_citation=_VERTCON3_UNCERTAINTY_CITATION,
    caveat=_VERTCON3_CAVEAT,
)


VERTICAL_TRANSFORMATIONS: Mapping[
    tuple[VerticalDatum, VerticalDatum], VerticalTransformation
] = MappingProxyType(
    {
        (NAVD88, NAVD88): _IDENTITY_NAVD88,
        (NGVD29, NGVD29): _IDENTITY_NGVD29,
        (NGVD29, NAVD88): _NGVD29_TO_NAVD88,
        (NAVD88, NGVD29): _NAVD88_TO_NGVD29,
    }
)
"""Every published pair this program carries, keyed by (source, target).

Read-only on purpose. A registry whose whole job is to keep every pair it has
ever carried (DESIGN.md #32) must not be something a later module can pop an
entry out of at runtime.
"""

# Resolution is by code, not by object identity, so a datum record rebuilt from
# a saved job still finds its transformation - the property
# ``frames.require_same_frame`` already has, and the reason a 2026 job still
# converts in 2030. Derived from the registry above, never maintained beside it.
_TRANSFORMATIONS_BY_CODE: Mapping[tuple[str, str], VerticalTransformation] = (
    MappingProxyType(
        {
            (source.code, target.code): transformation
            for (source, target), transformation in VERTICAL_TRANSFORMATIONS.items()
        }
    )
)


REQUIRED_VERTICAL_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("NAVD88", "NAVD88"),
        ("NGVD29", "NGVD29"),
        ("NGVD29", "NAVD88"),
        ("NAVD88", "NGVD29"),
    }
)
"""Pairs the registry must never lose. APPEND-ONLY: this list may grow, never shrink.

DESIGN.md amendment #32 states backwards compatibility as a requirement rather
than an assumption - a job converted in 2026 must still convert and still
reproduce after NAPGD2022 lands. This is that requirement written down where a
test, and the import check below, can enforce it. Adding NAPGD2022 later means
adding its pairs here; removing any line is the change #32 forbids.
"""


def _check_registry_keeps_every_required_pair() -> None:
    """Refuse to import if a pair required by #32 has been dropped.

    Loud at startup beats quiet at the first job that needed the missing pair.
    if/raise rather than assert, because -O strips asserts.
    """
    missing = sorted(REQUIRED_VERTICAL_PAIRS - set(_TRANSFORMATIONS_BY_CODE))
    if missing:
        dropped = ", ".join(f"{source} -> {target}" for source, target in missing)
        raise VerticalDatumError(
            f"The vertical transformation registry has lost pairs it is "
            f"required to keep: {dropped}. DESIGN.md amendment #32 requires "
            f"that every pair this program has ever carried keeps working, so "
            f"that a job converted years ago still converts and still "
            f"reproduces. Restore the record rather than removing it from "
            f"REQUIRED_VERTICAL_PAIRS."
        )


_check_registry_keeps_every_required_pair()


def _canonical(datum: VerticalDatum) -> VerticalDatum:
    """The registry's own record for this datum's code, when it has one.

    A record rebuilt from a saved job, or hand-built by a caller, must not be
    able to claim a status this module did not grant it - that is how an
    unusable datum would slip through. An unrecognised code is returned
    unchanged, so it reaches the pair refusal below, which names it.
    """
    return _DATUMS_BY_CODE.get(datum.code, datum)


def require_vertical_pair(
    source: VerticalDatum, target: VerticalDatum
) -> VerticalTransformation:
    """The published transformation for this pair, or a loud refusal.

    Called before any height is shifted. Two distinct refusals, because they
    mean different things to the user:

    * ``VerticalDatumNotUsableError`` - the datum is declared here but this
      program cannot yet convert heights in it (NAPGD2022 today).
    * ``VerticalTransformationUnavailableError`` - both datums are usable, but
      no transformation between them has been published or implemented.

    Never a silent pass-through. An unconverted height that is labelled as
    converted is a boundary-relevant error that looks entirely ordinary.

    Refuses a non-``VerticalDatum`` argument by name, for the reason
    docs/DESIGN.md amendment #11 finding 1 records against
    ``frames.require_same_frame``: this program's core records all carry
    ``code``, ``name`` and ``citation``, so a ``Zone``, a ``ReferenceFrame`` and
    a ``LinearUnit`` all duck-type through ``_canonical`` below and only fail
    several lines later on ``is_usable`` - as an ``AttributeError``, which walks
    straight through the ``except VerticalDatumError`` this module's own
    docstring tells callers to write. ``convert.project_point`` closed the same
    door with the same guard; this is that guard.
    """
    for label, datum in (("source", source), ("target", target)):
        if not isinstance(datum, VerticalDatum):
            raise TypeError(
                f"require_vertical_pair needs a michspc.spc.vertical."
                f"VerticalDatum as its {label}; got "
                f"{type(datum).__name__} ({datum!r}). Every record in this "
                f"core carries code, name and citation, so a zone, a reference "
                f"frame or a unit reaches this function without complaint and "
                f"would be asked whether it is a usable VERTICAL datum. Pass "
                f"michspc.spc.vertical.NGVD29 or NAVD88."
            )

    resolved_source = _canonical(source)
    resolved_target = _canonical(target)

    unusable: list[VerticalDatum] = []
    for datum in (resolved_source, resolved_target):
        if not datum.is_usable and datum.code not in {d.code for d in unusable}:
            unusable.append(datum)

    if unusable:
        offenders = " and ".join(d.code for d in unusable)
        verb = "are" if len(unusable) > 1 else "is"
        details = " ".join(f"{d.code} ({d.name}): {d.citation}." for d in unusable)
        usable = ", ".join(d.code for d in ALL_VERTICAL_DATUMS if d.is_usable)
        raise VerticalDatumNotUsableError(
            f"Cannot convert elevations from {resolved_source.code} to "
            f"{resolved_target.code}: {offenders} {verb} declared in this "
            f"program but not usable. {details} No published transformation "
            f"product exists, so any height this program reported in that datum "
            f"would be invented rather than converted. The vertical datums this "
            f"program can convert today are: {usable}."
        )

    try:
        return _TRANSFORMATIONS_BY_CODE[(resolved_source.code, resolved_target.code)]
    except KeyError:
        known = ", ".join(
            f"{s} -> {t}" for s, t in sorted(_TRANSFORMATIONS_BY_CODE)
        )
        raise VerticalTransformationUnavailableError(
            f"Cannot convert elevations from {resolved_source.code} to "
            f"{resolved_target.code}: no published vertical transformation "
            f"between these two datums is implemented. Registered pairs are: "
            f"{known}. Vertical datums differ by amounts that look like "
            f"ordinary elevations - across Michigan NGVD 29 and NAVD 88 differ "
            f"by anything from -0.412 m to +0.348 m - so passing a height "
            f"through unchanged would silently corrupt it. Convert within one "
            f"vertical datum, or "
            f"select a pair this program carries."
        ) from None


def signed_shift(
    *, grid_value_m: float | None, transformation: VerticalTransformation
) -> float:
    """The shift this transformation applies, in metres: ``sign * grid_value``.

    Keyword-only, and so is ``apply_shift`` below. A height and a grid value are
    both bare floats, and transposing them at a call site produces a plausible
    number rather than an error - 200.0 m and -0.1402 m swapped still return
    something that could be pasted into a Z column. Naming them at every call
    site is the cheapest way to make that transposition impossible.

    This is the one place the shift is computed. The output layers report the
    shift and the shifted height, and both come from here so they cannot be
    signed differently.
    """
    if transformation.is_identity:
        if grid_value_m is not None:
            raise ValueError(
                f"{transformation} applies no grid, so it cannot be given a "
                f"grid value ({grid_value_m!r}). Receiving one means a grid was "
                f"read for a pair that has none - check which transformation "
                f"was looked up."
            )
        return 0.0

    if grid_value_m is None:
        raise ValueError(
            f"{transformation} needs a grid value from {transformation.grid_key} "
            f"and was given none. A missing grid read is not a zero shift: "
            f"treating it as one would report an unconverted height as "
            f"converted. Refuse the point instead."
        )

    if not math.isfinite(grid_value_m):
        raise ValueError(
            f"{transformation} was given a non-finite grid value "
            f"({grid_value_m!r}). A grid cell that is not a finite number of "
            f"metres cannot be applied to a height."
        )

    return transformation.sign * grid_value_m


def apply_shift(
    height_m: float,
    *,
    grid_value_m: float | None,
    transformation: VerticalTransformation,
) -> float:
    """The height in the target datum, in metres.

    ``height_m`` is in ``transformation.source``; the result is in
    ``transformation.target``. The direction is
    ``transformation.direction_statement``, which is written from the same
    ``sign`` this function multiplies by.

    Metres in, metres out. The grid is published in metres (plan section 2.2),
    and the core computes in metres exactly as it does for the geoid; the unit
    conversion belongs at the file boundary, not here.
    """
    if not math.isfinite(height_m):
        raise ValueError(
            f"A height of {height_m!r} m is not a finite number and cannot be "
            f"shifted between vertical datums."
        )

    return height_m + signed_shift(
        grid_value_m=grid_value_m, transformation=transformation
    )
