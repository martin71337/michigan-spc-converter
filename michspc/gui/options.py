"""The Options: window-level choices both tabs read (DESIGN.md #71, plan L7-L10).

Three questions, answered once for the window rather than per tab - the one
recorded reversal of #26/#43's "tabs share no state", on the owner's
instruction and for the Options only (plan L7):

1. **Which groups the four system lists show** - each zone system, and each
   geodetic frame's latitude/longitude entry. On by default except the
   time-dependent frames (the WGS 84 realizations and the ITRFs), decided by
   the frame record's own ``is_time_dependent``, never by a list of names.
2. **The Auto zone frame** - NAD83(2011) (SPCS 83 zones) or NATRF2022 (the
   SPCS2022 local zones), from ``job.AUTO_FRAMES``.
3. **Where the observation date comes from** - "today" (the default) or a
   date entered on the tab (plan O3).

``Options`` is one immutable value. ``visible_rows`` is the pure function
from it to which rows of a zone dropdown are shown; both tabs call it, so
they cannot filter differently. ``load_options`` / ``save_options`` are the
persistence, over the store seam in ``settings_store``.

**This module computes no domain value.** It decides what is offered, never
what a coordinate is; ``job.run`` stays the wall for every combination a
caller could still assemble by hand.
"""

from __future__ import annotations

from dataclasses import dataclass

from michspc.gui.controls import (
    GEODETIC_CHOICES,
    OFFERED_ZONES,
    UNCHOSEN,
    is_auto,
    is_geodetic,
)
from michspc.job import AUTO_FRAMES, ObservationDateSource
from michspc.spc.frames import ReferenceFrame
from michspc.spc.zones import Zone


@dataclass(frozen=True)
class ListGroup:
    """One group of entries the Options switch on or off as a whole.

    Exactly one of ``system`` (a zone system, ``Zone.system``) and ``frame``
    (a geodetic entry's frame) is set. ``label`` and ``key`` are derived from
    that record, so no name is typed twice.
    """

    system: str | None
    frame: ReferenceFrame | None

    @property
    def is_zone_group(self) -> bool:
        return self.system is not None

    @property
    def label(self) -> str:
        """What the Options dialog calls this group. Derived from the record."""
        if self.is_zone_group:
            return f"{self.system} zones"
        return f"{self.frame.code} latitude/longitude"

    @property
    def key(self) -> str:
        """The persistence key: the record's own string, under ``lists/``."""
        if self.is_zone_group:
            return f"lists/zones/{self.system}"
        return f"lists/geodetic/{self.frame.code}"

    @property
    def default_shown(self) -> bool:
        """On, except a time-dependent frame (plan section 1 item 1).

        Asked of the frame record (``ReferenceFrame.is_time_dependent``): the
        five WGS 84 / ITRF entries are off by default because a position in
        one of them means nothing until its observation date is stated, and
        the commonest slip is one row off the NAD83(2011) entry above them.
        """
        if self.is_zone_group:
            return True
        return not self.frame.is_time_dependent

    def holds(self, data) -> bool:
        """Whether a dropdown item belongs to this group."""
        if self.is_zone_group:
            if isinstance(data, Zone):
                return data.system == self.system
            if is_auto(data):
                return data.system.value == self.system
            return False
        return is_geodetic(data) and data.frame is self.frame


def _zone_systems() -> tuple[str, ...]:
    """The zone systems the dropdowns offer, in dropdown order.

    From ``controls.OFFERED_ZONES``, not the whole registry, so a system
    whose zones are registered but not yet offered (UTM until work package
    U5, DESIGN.md #72) gets no group that would switch nothing.
    """
    systems: list[str] = []
    for zone in OFFERED_ZONES:
        if zone.system not in systems:
            systems.append(zone.system)
    return tuple(systems)


LIST_GROUPS: tuple[ListGroup, ...] = (
    *(ListGroup(system=system, frame=None) for system in _zone_systems()),
    *(ListGroup(system=None, frame=choice.frame) for choice in GEODETIC_CHOICES),
)
"""Every group, in the dialog's order: the zone systems in registry order
(SPCS 83, then SPCS2022), then one geodetic group per offered frame in
``ALL_FRAMES`` declaration order. Derived from the registries, so a frame or
a zone system that arrives there arrives here."""

_GROUPS_BY_KEY = {group.key: group for group in LIST_GROUPS}


def group_of(data) -> ListGroup | None:
    """The group a dropdown item belongs to; None for the placeholder or a separator."""
    for group in LIST_GROUPS:
        if group.holds(data):
            return group
    return None


class OptionsError(ValueError):
    """An Options value that cannot exist: names the field and why."""


def options_problem(shown) -> str | None:
    """Why a set of shown groups cannot be accepted, or None (plan L8).

    At least one zone group and one geodetic group must stay on: with none,
    a dropdown would offer only its placeholder, and a list with nothing to
    choose looks answerable and is not.
    """
    groups = [_GROUPS_BY_KEY[key] for key in shown if key in _GROUPS_BY_KEY]
    if not any(group.is_zone_group for group in groups):
        return (
            "Switch on at least one group of State Plane zones: with none, the "
            "system lists would hold no zone to choose."
        )
    if not any(not group.is_zone_group for group in groups):
        return (
            "Switch on at least one latitude/longitude group: with none, the "
            "system lists would hold no geodetic position to choose."
        )
    return None


@dataclass(frozen=True)
class Options:
    """The window's Options. Immutable; replaced whole, never edited in place."""

    shown: frozenset[str]
    """The ``ListGroup.key`` of every group switched on."""

    auto_frame: ReferenceFrame
    """The frame Auto chooses zones in - one of ``job.AUTO_FRAMES``, by identity."""

    date_source: ObservationDateSource
    """Where a time-dependent job's observation date comes from (plan O3)."""

    def __post_init__(self) -> None:
        # if/raise, never assert: the suite runs under -O.
        if not isinstance(self.shown, frozenset):
            raise OptionsError(
                f"Options.shown must be a frozenset of group keys; got "
                f"{type(self.shown).__name__}."
            )
        unknown = sorted(key for key in self.shown if key not in _GROUPS_BY_KEY)
        if unknown:
            raise OptionsError(
                f"Options.shown names groups that do not exist: {unknown}. "
                f"The groups are: {[group.key for group in LIST_GROUPS]}."
            )
        problem = options_problem(self.shown)
        if problem is not None:
            raise OptionsError(problem)
        if not any(self.auto_frame is frame for frame, _system in AUTO_FRAMES):
            raise OptionsError(
                f"Options.auto_frame must be one of job.AUTO_FRAMES "
                f"({', '.join(frame.code for frame, _ in AUTO_FRAMES)}), the "
                f"registry's own record; got {self.auto_frame!r}."
            )
        if not isinstance(self.date_source, ObservationDateSource):
            raise OptionsError(
                f"Options.date_source must be an ObservationDateSource (TODAY "
                f"or ENTERED); got {self.date_source!r}."
            )

    def is_group_shown(self, group: ListGroup) -> bool:
        return group.key in self.shown

    def with_groups(self, *groups: ListGroup, shown: bool = True) -> "Options":
        """A copy with these groups switched on (or off). For callers and tests."""
        keys = {group.key for group in groups}
        new = self.shown | keys if shown else self.shown - keys
        return Options(
            shown=frozenset(new),
            auto_frame=self.auto_frame,
            date_source=self.date_source,
        )


DEFAULT_SHOWN = frozenset(group.key for group in LIST_GROUPS if group.default_shown)

DEFAULT_AUTO_FRAME = AUTO_FRAMES[0][0]
"""NAD83(2011) - the first ``job.AUTO_FRAMES`` record: today's zones."""

DEFAULT_DATE_SOURCE = ObservationDateSource.TODAY
"""Plan O3, the owner's decision: "today" unless he chooses to enter a date.
The reversal of PLAN-wgs84 D10's no-default rule, for this choice only
(DESIGN.md #71); an entered date is still never remembered."""

DEFAULT_OPTIONS = Options(
    shown=DEFAULT_SHOWN,
    auto_frame=DEFAULT_AUTO_FRAME,
    date_source=DEFAULT_DATE_SOURCE,
)


def is_shown(options: Options, data, *, is_source: bool) -> bool:
    """Whether a dropdown item is shown under these Options.

    * the placeholder - always;
    * an Auto entry - only on a TO combo (plan L1: a northing/easting does
      not say which zone it is in), only for the Options' Auto frame, and
      only while that system's zone group is shown ("shown only if that
      system's zone group is shown");
    * a zone or a geodetic entry - while its group is on.

    Anything else is refused: a dropdown item this rule cannot place is a
    wiring defect, and guessing "shown" would put it in front of the user.
    """
    if data == UNCHOSEN:
        return True
    group = group_of(data)
    if group is None:
        raise ValueError(
            f"options.is_shown cannot place the dropdown item {data!r} in any "
            f"Options group; every item zone_combo builds belongs to one."
        )
    if is_auto(data):
        if is_source or data.frame is not options.auto_frame:
            return False
    return options.is_group_shown(group)


def visible_rows(options: Options, items, *, is_source: bool) -> tuple[bool, ...]:
    """One shown/hidden flag per dropdown row, separators included.

    ``items`` is the combo's data in index order (``controls.combo_items``),
    a separator being None. A separator is shown exactly when it would sit
    BETWEEN two shown entries - placed before the next shown entry, provided
    an entry other than the placeholder is shown above it - so switching a
    group off never leaves two rules together, a rule at the top, or a rule
    at the bottom.
    """
    flags = [False] * len(items)
    pending: int | None = None
    seen_entry = False
    for index, data in enumerate(items):
        if data is None:
            if seen_entry:
                pending = index
            continue
        shown = is_shown(options, data, is_source=is_source)
        flags[index] = shown
        if shown and data != UNCHOSEN:
            if pending is not None:
                flags[pending] = True
                pending = None
            seen_entry = True
    return tuple(flags)


# --------------------------------------------------------------------------
# Persistence (plan L9). Three kinds of key, each read strictly.
# --------------------------------------------------------------------------

AUTO_FRAME_KEY = "auto_zone/frame"
DATE_SOURCE_KEY = "observation_date/source"
_TRUE = "true"
_FALSE = "false"


def _reset_message(name: str, raw, default_text: str) -> str:
    return (
        f"Options: the remembered value of \"{name}\" ({raw!r}) is not one MCX "
        f"recognises, so it was reset to its default ({default_text})."
    )


def load_options(store) -> tuple[Options, tuple[str, ...]]:
    """The remembered Options, and one message per value that had to be reset.

    A key that is absent is the default, silently - a first run is not an
    error. A key that is present and not exactly a value this program writes
    is reset to that key's default **and says so**, never crashes and never
    guesses (plan L9): ``"True"``, ``"1"`` or a frame code with a typo are all
    refused alike. A set of groups that would leave a list empty (L8) is reset
    to the default groups, also said. Every reset is written back, so the
    message is shown once rather than at every start.
    """
    messages: list[str] = []
    shown: set[str] = set()
    for group in LIST_GROUPS:
        raw = store.get(group.key)
        if raw is None:
            on = group.default_shown
        elif raw == _TRUE:
            on = True
        elif raw == _FALSE:
            on = False
        else:
            on = group.default_shown
            messages.append(
                _reset_message(
                    f"Show {group.label}", raw, "on" if on else "off"
                )
            )
            store.put(group.key, _TRUE if on else _FALSE)
        if on:
            shown.add(group.key)
    if options_problem(shown) is not None:
        messages.append(
            "Options: the remembered system lists would have left a list "
            "with nothing to choose, so every group was reset to its default."
        )
        shown = set(DEFAULT_SHOWN)
        for group in LIST_GROUPS:
            store.put(group.key, _TRUE if group.default_shown else _FALSE)

    raw = store.get(AUTO_FRAME_KEY)
    auto_frame = DEFAULT_AUTO_FRAME
    if raw is not None:
        matched = [frame for frame, _system in AUTO_FRAMES if frame.code == raw]
        if matched:
            auto_frame = matched[0]
        else:
            messages.append(
                _reset_message("Auto zone frame", raw, DEFAULT_AUTO_FRAME.code)
            )
            store.put(AUTO_FRAME_KEY, DEFAULT_AUTO_FRAME.code)

    raw = store.get(DATE_SOURCE_KEY)
    date_source = DEFAULT_DATE_SOURCE
    if raw is not None:
        matched = [source for source in ObservationDateSource if source.value == raw]
        if matched:
            date_source = matched[0]
        else:
            messages.append(
                _reset_message("Observation date", raw, DEFAULT_DATE_SOURCE.value)
            )
            store.put(DATE_SOURCE_KEY, DEFAULT_DATE_SOURCE.value)

    return (
        Options(
            shown=frozenset(shown), auto_frame=auto_frame, date_source=date_source
        ),
        tuple(messages),
    )


def save_options(store, options: Options) -> None:
    """Remember the three choices - and nothing else. Never a date (plan O3)."""
    for group in LIST_GROUPS:
        store.put(group.key, _TRUE if options.is_group_shown(group) else _FALSE)
    store.put(AUTO_FRAME_KEY, options.auto_frame.code)
    store.put(DATE_SOURCE_KEY, options.date_source.value)
