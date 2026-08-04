"""Maintenance windows and blackout periods: recurrence expansion, availability.

Pure -- no database, no clock it was not handed.
``app/services/calendar.py`` supplies the database and the "now" around
these decisions.
"""

from __future__ import annotations

import calendar as _stdlib_calendar
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models.enums import RecurrenceKind

_MAX_OCCURRENCES = 366
"""A safety ceiling on how many occurrences one recurring entry expands
to in a single call. A daily recurrence with no ``recurrence_until`` and
a caller-supplied range spanning years would otherwise turn one
misconfigured calendar entry into an unbounded loop."""


def _add_months(moment: datetime, months: int) -> datetime:
    """*moment* advanced by *months* whole months, clamped to the target month's own length.

    January 31 plus one month is February 28 (or 29), not March 3 --
    the clamp is what keeps a monthly maintenance window from silently
    drifting into a different week of the month every few cycles.
    """
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, _stdlib_calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


_STEP_FOR: dict[RecurrenceKind, timedelta | None] = {
    RecurrenceKind.DAILY: timedelta(days=1),
    RecurrenceKind.WEEKLY: timedelta(weeks=1),
    RecurrenceKind.MONTHLY: None,
}


def expand_occurrences(
    *,
    starts_at: datetime,
    ends_at: datetime,
    recurrence: RecurrenceKind,
    recurrence_until: datetime | None,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[datetime, datetime]]:
    """Every concrete occurrence of a (possibly recurring) entry that touches a range.

    A non-recurring entry expands to at most its own one occurrence. A
    recurring one stops at whichever comes first: *recurrence_until*,
    *window_end*, or :data:`_MAX_OCCURRENCES` cycles -- an entry that
    outlives all three is a configuration error this function refuses to
    loop forever over rather than one it silently accepts.

    **Every occurrence is computed from the original *starts_at*, never
    from the previous occurrence.** A monthly entry on the 31st clamps
    to the 28th in February -- but must not then drift permanently onto
    the 28th for every month after: March has 31 days again, and a
    maintenance window anchored to "the 31st" belongs back on the 31st
    the moment the calendar allows it. Stepping from the last cursor
    instead of the original start would compound that clamp forever.
    """
    duration = ends_at - starts_at
    hard_stop = min(recurrence_until, window_end) if recurrence_until else window_end

    occurrences: list[tuple[datetime, datetime]] = []
    for count in range(_MAX_OCCURRENCES):
        if recurrence is RecurrenceKind.NONE:
            cursor_start = starts_at
        else:
            step = _STEP_FOR[recurrence]
            cursor_start = (
                starts_at + step * count if step is not None else _add_months(starts_at, count)
            )
        if cursor_start >= hard_stop:
            break
        cursor_end = cursor_start + duration
        if cursor_start < window_end and cursor_end > window_start:
            occurrences.append((cursor_start, cursor_end))
        if recurrence is RecurrenceKind.NONE:
            break
    return occurrences


def is_within_any(moment: datetime, occurrences: list[tuple[datetime, datetime]]) -> bool:
    """Whether *moment* falls inside any of a list of expanded occurrences."""
    return any(start <= moment < end for start, end in occurrences)


@dataclass(frozen=True, slots=True)
class AvailabilityCheck:
    """Whether a proposed window may book into a maintenance window."""

    is_available: bool
    reason: str | None


def check_availability(*, capacity_limit: int | None, current_bookings: int) -> AvailabilityCheck:
    """Whether a proposed booking fits inside a maintenance window's own capacity.

    Time containment is the caller's job -- this only answers the
    capacity question, once a window has already been established as
    the right one to check. ``capacity_limit=None`` is uncapped, not
    zero: an unconfigured limit must never read as "nothing may book
    here."
    """
    if capacity_limit is None:
        return AvailabilityCheck(is_available=True, reason=None)
    if current_bookings >= capacity_limit:
        return AvailabilityCheck(
            is_available=False,
            reason=f"Window is at capacity ({current_bookings}/{capacity_limit}).",
        )
    return AvailabilityCheck(is_available=True, reason=None)


__all__ = ["AvailabilityCheck", "check_availability", "expand_occurrences", "is_within_any"]
