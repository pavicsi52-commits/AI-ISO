"""SLA clock arithmetic: due dates, pausing, elapsed time, breach.

Pure: every function here takes the moment it needs as an argument and
returns a value, never touching a database or a clock of its own. That
is what makes a breach explicable after the fact -- an SLA breached at
14:32 has to be reconstructable from the incident's own recorded
history, not from re-running logic against whatever time it is now.

**Business-hours arithmetic never adds minutes straight onto a
timestamp.** A four-hour, business-hours-only resolution SLA started at
16:00 on a Friday is due partway through Monday, not at 20:00 Friday --
and the only way to get that right is to walk the calendar forward,
skipping the hours the clock does not run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

MAX_WALK_DAYS = 3_650
"""Ceiling on how many calendar days :func:`add_business_minutes` will
walk forward. A business calendar with zero open days (misconfigured to
exclude every weekday) would otherwise loop until the process runs out
of memory; a decade is far more headroom than any real SLA needs and
still fails loudly rather than hanging."""


@dataclass(frozen=True, slots=True)
class BusinessCalendar:
    """When a business-hours SLA clock is actually running."""

    start_hour: int = 9
    end_hour: int = 17
    business_days: frozenset[int] = field(default_factory=lambda: frozenset({0, 1, 2, 3, 4}))
    """Monday=0 .. Sunday=6, matching :meth:`datetime.date.weekday`."""

    def is_open(self, moment: datetime) -> bool:
        """Whether the calendar is open at this instant."""
        return (
            moment.weekday() in self.business_days
            and self.start_hour <= moment.hour < self.end_hour
        )

    def next_open(self, moment: datetime) -> datetime:
        """The next instant the calendar is open, at or after *moment*."""
        current = moment
        for _ in range(MAX_WALK_DAYS * 24):
            if self.is_open(current):
                return current
            if current.weekday() not in self.business_days or current.hour >= self.end_hour:
                current = (current + timedelta(days=1)).replace(
                    hour=self.start_hour, minute=0, second=0, microsecond=0
                )
            else:
                current = current.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
        raise ValueError("No open business hour found within the walk ceiling; check the calendar.")


ALWAYS_OPEN = BusinessCalendar(start_hour=0, end_hour=24, business_days=frozenset(range(7)))
"""The 24x7 calendar, expressed as a business calendar with no closed
hours -- so 24x7 and business-hours SLAs share one code path rather than
one being a special case of the other."""


def add_business_minutes(start: datetime, minutes: int, *, calendar: BusinessCalendar) -> datetime:
    """Walk *minutes* of open time forward from *start*.

    Raises:
        ValueError: If *minutes* is negative, or the calendar has no
            open hours within :data:`MAX_WALK_DAYS`.
    """
    if minutes < 0:
        raise ValueError(f"minutes must be non-negative, got {minutes!r}.")

    current = calendar.next_open(start)
    remaining = timedelta(minutes=minutes)

    for _ in range(MAX_WALK_DAYS * 24):
        if remaining <= timedelta(0):
            return current
        # Built from midnight plus a timedelta rather than
        # ``current.replace(hour=calendar.end_hour)``: an end_hour of 24
        # (a calendar open through midnight, as ALWAYS_OPEN is) is not a
        # valid ``datetime`` hour, and ``.replace`` would raise on it.
        midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
        day_close = midnight + timedelta(hours=calendar.end_hour)
        room_today = day_close - current
        if room_today <= timedelta(0):
            current = calendar.next_open(current + timedelta(minutes=1))
            continue
        if remaining <= room_today:
            return current + remaining
        remaining -= room_today
        current = calendar.next_open(day_close)

    raise ValueError("Could not compute a due date within the walk ceiling; check the calendar.")


@dataclass(slots=True)
class ClockState:
    """The minimum an SLA clock needs to compute elapsed time and breach.

    A projection of the stored row, not the row itself -- this module
    never sees an ORM object.
    """

    started_at: datetime | None
    due_at: datetime | None
    paused_at: datetime | None
    paused_seconds_total: float
    met_at: datetime | None
    breached_at: datetime | None


def elapsed_seconds(state: ClockState, *, now: datetime) -> float:
    """How much running time has actually accumulated on this clock.

    Subtracts every pause, including one in progress right now.
    Deliberately excludes paused time: a clock paused waiting on a
    vendor's response must not count that wait as time this
    organization failed to meet its own SLA, or pausing would stop
    protecting anyone and would instead just make every SLA look worse
    the more honestly its pauses were recorded.
    """
    if state.started_at is None:
        return 0.0
    end = state.met_at or state.breached_at or now
    total = (end - state.started_at).total_seconds()
    paused = state.paused_seconds_total
    if state.paused_at is not None:
        paused += (end - state.paused_at).total_seconds()
    return max(0.0, total - paused)


def is_breached(state: ClockState, *, now: datetime) -> bool:
    """Whether this clock has run out, as of *now*.

    A clock already marked met or breached does not re-evaluate --
    reopening the question every time somebody reads the row would let
    a clock that was correctly met at 14:00 start reporting breached at
    14:05 because nothing advanced :attr:`ClockState.due_at` in the
    meantime.
    """
    if state.met_at is not None or state.breached_at is not None:
        return state.breached_at is not None
    if state.due_at is None or state.paused_at is not None:
        return False
    return now >= state.due_at


def warning_threshold_at(state: ClockState, *, warning_percent: int) -> datetime | None:
    """When a warning should fire, *warning_percent* of the way to due.

    Returns ``None`` before the clock has actually started -- a warning
    computed against a clock with no ``started_at`` would be measuring
    the gap to a due date that has not been anchored yet, which is not
    the same question as "is this SLA about to breach"."""
    if state.started_at is None or state.due_at is None:
        return None
    total = state.due_at - state.started_at
    return state.started_at + total * (warning_percent / 100.0)


def should_warn(state: ClockState, *, now: datetime, warning_percent: int) -> bool:
    """Whether a warning should fire now and has not already."""
    if state.met_at is not None or state.breached_at is not None:
        return False
    threshold = warning_threshold_at(state, warning_percent=warning_percent)
    return threshold is not None and now >= threshold


def due_at_for(
    started_at: datetime, target_minutes: int, *, is_24x7: bool, calendar: BusinessCalendar
) -> datetime:
    """Compute a clock's due date from its start.

    Routes through :func:`add_business_minutes` even for a 24x7 clock,
    via :data:`ALWAYS_OPEN` -- one code path, not two, so a bug in the
    business-hours walk cannot silently diverge from the 24x7 case that
    exercises it least.
    """
    active_calendar = ALWAYS_OPEN if is_24x7 else calendar
    return add_business_minutes(started_at, target_minutes, calendar=active_calendar)


def resume_paused_seconds(*, paused_at: datetime, resumed_at: datetime) -> float:
    """How much pause time one pause/resume cycle contributed.

    Raises:
        ValueError: If *resumed_at* precedes *paused_at* -- a clock
            cannot resume before it paused, and silently returning a
            negative duration would corrupt every future elapsed-time
            calculation for this clock.
    """
    if resumed_at < paused_at:
        raise ValueError("resumed_at must not precede paused_at.")
    return (resumed_at - paused_at).total_seconds()


def compliance_rate(*, met: int, breached: int) -> float:
    """SLA compliance as a percentage, 0-100.

    Pending clocks are excluded from both numerator and denominator on
    purpose: a clock still running has not yet succeeded or failed, and
    counting it as either would make the rate swing on nothing more than
    how many incidents happen to be open at read time.
    """
    total = met + breached
    return (met / total * 100.0) if total else 100.0
    # 100.0 with no data is a deliberate choice, not a fallback masking a
    # bug: zero measured SLAs is not evidence of failure, and reporting
    # 0% would say "we have never once met an SLA" about an organization
    # that has simply not had one come due yet.


def utcnow() -> datetime:
    """The current moment, timezone-aware.

    The one function in this module that is not pure -- kept here,
    named for exactly what it is, so every caller that needs "now" gets
    it from one place and a test can freeze time by monkeypatching this
    single function rather than hunting through the service layer.
    """
    return datetime.now(UTC)


__all__ = [
    "ALWAYS_OPEN",
    "MAX_WALK_DAYS",
    "BusinessCalendar",
    "ClockState",
    "add_business_minutes",
    "compliance_rate",
    "due_at_for",
    "elapsed_seconds",
    "is_breached",
    "resume_paused_seconds",
    "should_warn",
    "utcnow",
    "warning_threshold_at",
]
