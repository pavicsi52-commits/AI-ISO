"""The scheduling lifecycle: job/execution transitions, and next-due computation.

**Reuses ``shared_core.scheduler`` directly rather than reimplementing
cron or calendar math** -- per docs/054's own "Use every previously
implemented platform framework. Do NOT redesign the platform."
:func:`compute_next_run_at` is a thin adapter from this service's own
persisted :class:`~app.models.trigger.JobTrigger` shape onto
:class:`shared_core.scheduler.schedule.Schedule` /
:func:`shared_core.scheduler.engine.compute_next_run`, which already
implements every ``SCHEDULE TYPE`` this service exposes except the
month/quarter/year-granularity calendar rules docs/054 additionally asks
for (docs/026's own ``CalendarRule`` is a weekly weekday/time-of-day
window only) -- :func:`calendar_rule_to_cron` covers exactly that gap by
translating a friendly calendar config into a cron expression, so even
that path still runs through :mod:`shared_core.scheduler.cron`, not a
second date-math implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from shared_core.exceptions.validation import ValidationError
from shared_core.scheduler.cron import next_run_time
from shared_core.scheduler.engine import compute_next_run as _shared_compute_next_run
from shared_core.scheduler.exceptions import InvalidScheduleError
from shared_core.scheduler.schedule import Schedule as SharedSchedule
from shared_core.scheduler.schedule import ScheduleType as SharedScheduleType

from app.models.enums import CalendarRuleKind, ExecutionStatus, JobPriority, ScheduledJobStatus

_MAX_HOLIDAY_SKIPS = 366
"""A safety ceiling on how many candidate dates a holiday-aware
computation will skip past in one call -- a business-day schedule with
every day of the year configured as a holiday is a configuration error
this refuses to loop forever over, the same reasoning 053's
``expand_occurrences`` applies to its own ``_MAX_OCCURRENCES``."""

# ---- job definition lifecycle ---------------------------------------------

ALLOWED_JOB_TRANSITIONS: dict[ScheduledJobStatus, frozenset[ScheduledJobStatus]] = {
    ScheduledJobStatus.REGISTERED: frozenset(
        {ScheduledJobStatus.ACTIVE, ScheduledJobStatus.DELETED}
    ),
    ScheduledJobStatus.ACTIVE: frozenset(
        {ScheduledJobStatus.PAUSED, ScheduledJobStatus.DISABLED, ScheduledJobStatus.DELETED}
    ),
    ScheduledJobStatus.PAUSED: frozenset(
        {ScheduledJobStatus.ACTIVE, ScheduledJobStatus.DISABLED, ScheduledJobStatus.DELETED}
    ),
    ScheduledJobStatus.DISABLED: frozenset({ScheduledJobStatus.ACTIVE, ScheduledJobStatus.DELETED}),
    ScheduledJobStatus.DELETED: frozenset(),
}
"""``DELETED`` is a true dead end -- a deleted job is re-created, not
resurrected, the same reasoning every prior AI-IOS lifecycle applies to
its own terminal states."""


def validate_job_transition(current: ScheduledJobStatus, target: ScheduledJobStatus) -> None:
    """Confirm *target* is reachable from *current*.

    Raises:
        ValidationError: If it is not.
    """
    if target not in ALLOWED_JOB_TRANSITIONS[current]:
        allowed = (
            ", ".join(sorted(str(one) for one in ALLOWED_JOB_TRANSITIONS[current])) or "nothing"
        )
        raise ValidationError(
            f"A job that is {current!s} cannot move to {target!s}. Allowed from here: {allowed}."
        )


# ---- execution lifecycle ---------------------------------------------------

ALLOWED_EXECUTION_TRANSITIONS: dict[ExecutionStatus, frozenset[ExecutionStatus]] = {
    ExecutionStatus.QUEUED: frozenset(
        {
            ExecutionStatus.RUNNING,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.SKIPPED,
            ExecutionStatus.BLOCKED,
            ExecutionStatus.WAITING,
        }
    ),
    ExecutionStatus.WAITING: frozenset({ExecutionStatus.QUEUED, ExecutionStatus.CANCELLED}),
    ExecutionStatus.BLOCKED: frozenset({ExecutionStatus.QUEUED, ExecutionStatus.CANCELLED}),
    ExecutionStatus.RUNNING: frozenset(
        {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.TIMED_OUT,
            ExecutionStatus.PAUSED,
        }
    ),
    ExecutionStatus.PAUSED: frozenset({ExecutionStatus.RUNNING, ExecutionStatus.CANCELLED}),
    ExecutionStatus.FAILED: frozenset({ExecutionStatus.RECOVERED}),
    ExecutionStatus.TIMED_OUT: frozenset({ExecutionStatus.RECOVERED}),
    ExecutionStatus.COMPLETED: frozenset(),
    ExecutionStatus.CANCELLED: frozenset(),
    ExecutionStatus.SKIPPED: frozenset(),
    ExecutionStatus.RECOVERED: frozenset(),
}
"""``COMPLETED``, ``CANCELLED``, ``SKIPPED``, and ``RECOVERED`` are dead
ends for *this* execution row -- a retry after ``FAILED``/``TIMED_OUT``
opens a *new* execution (a fresh attempt), the same reasoning every
prior AI-IOS retryable-workflow lifecycle applies; ``RECOVERED`` marks
the failed attempt's own row as the thing that got recovered, not a
state work continues in."""


def validate_execution_transition(current: ExecutionStatus, target: ExecutionStatus) -> None:
    """Confirm *target* is reachable from *current*.

    Raises:
        ValidationError: If it is not.
    """
    if target not in ALLOWED_EXECUTION_TRANSITIONS[current]:
        allowed = (
            ", ".join(sorted(str(one) for one in ALLOWED_EXECUTION_TRANSITIONS[current]))
            or "nothing"
        )
        raise ValidationError(
            f"An execution that is {current!s} cannot move to {target!s}. "
            f"Allowed from here: {allowed}."
        )


# ---- calendar rule -> cron translation -------------------------------------

_CRON_WEEKDAY_DEFAULT = 1
"""Monday, in cron's own 0=Sunday..6=Saturday convention -- the default
weekday a ``WEEKLY`` rule fires on when *config* does not say."""


def calendar_rule_to_cron(kind: CalendarRuleKind, config: dict[str, object]) -> str:
    """Translate a friendly calendar recurrence into a 5-field cron expression.

    *config* keys, all optional except where noted: ``minute`` (0-59,
    default 0), ``hour`` (0-23, default 0), ``day_of_month`` (1-31,
    default 1, used by ``MONTHLY``/``QUARTERLY``/``YEARLY``), ``month``
    (1-12, default 1, used by ``YEARLY``), ``weekday`` (0-6, Sunday=0,
    used by ``WEEKLY``), ``cron_expression`` (required for ``CUSTOM``,
    used verbatim).

    Every value this produces is handed straight to
    :func:`shared_core.scheduler.cron.next_run_time` -- this function
    only ever builds the expression string, it never computes a due time
    itself.

    Raises:
        ValidationError: If *kind* is ``CUSTOM`` and *config* carries no
            ``cron_expression``, or ``NONE`` (which has no cron form --
            a non-recurring window has nothing to translate).
    """
    if kind is CalendarRuleKind.CUSTOM:
        expression = config.get("cron_expression")
        if not isinstance(expression, str) or not expression.strip():
            raise ValidationError("A CUSTOM calendar rule requires a 'cron_expression'.")
        return expression

    if kind is CalendarRuleKind.NONE:
        raise ValidationError("A calendar rule of NONE has no recurring cron form.")

    minute = int(config.get("minute", 0))  # type: ignore[arg-type]
    hour = int(config.get("hour", 0))  # type: ignore[arg-type]
    day_of_month = int(config.get("day_of_month", 1))  # type: ignore[arg-type]
    month = int(config.get("month", 1))  # type: ignore[arg-type]
    weekday = int(config.get("weekday", _CRON_WEEKDAY_DEFAULT))  # type: ignore[arg-type]

    builders: dict[CalendarRuleKind, str] = {
        CalendarRuleKind.DAILY: f"{minute} {hour} * * *",
        CalendarRuleKind.BUSINESS_DAYS: f"{minute} {hour} * * 1-5",
        CalendarRuleKind.WEEKENDS: f"{minute} {hour} * * 0,6",
        CalendarRuleKind.WEEKLY: f"{minute} {hour} * * {weekday}",
        CalendarRuleKind.MONTHLY: f"{minute} {hour} {day_of_month} * *",
        CalendarRuleKind.QUARTERLY: f"{minute} {hour} {day_of_month} 1,4,7,10 *",
        CalendarRuleKind.YEARLY: f"{minute} {hour} {day_of_month} {month} *",
    }
    return builders[kind]


# ---- next-due computation ---------------------------------------------------

_SHARED_SCHEDULE_TYPE_MAP: dict[str, SharedScheduleType] = {
    "one_time": SharedScheduleType.SCHEDULED_TIME,
    "recurring": SharedScheduleType.FIXED_RATE,
    "cron": SharedScheduleType.CRON_EXPRESSION,
    "interval": SharedScheduleType.FIXED_RATE,
}
"""The three trigger types whose next-due computation maps directly onto
an existing :class:`~shared_core.scheduler.schedule.ScheduleType` with
no translation needed. ``calendar``/``custom_schedule`` are deliberately
absent -- docs/054's ``CalendarRuleKind`` (daily/weekly/monthly/
quarterly/yearly/business-days/weekends) is a different, richer concept
than :mod:`shared_core.scheduler.calendar`'s own ``CalendarRule`` (a
single recurring weekly weekday/time-of-day window only), so those two
route through :func:`calendar_rule_to_cron` onto the *cron* machinery
below instead of the shared framework's own calendar handling.
``dependency_driven``, ``manual_trigger``, and ``maintenance_window``
are also absent -- none of the three ever has a computed next-due time;
see this function's own docstring."""

_CALENDAR_LIKE_TRIGGER_TYPES = frozenset({"calendar", "custom_schedule"})
_NO_COMPUTED_RUN_TRIGGER_TYPES = frozenset(
    {"dependency_driven", "manual_trigger", "maintenance_window", "event_driven"}
)


@dataclass(frozen=True, slots=True)
class TriggerInput:
    """Exactly the fields of a :class:`~app.models.trigger.JobTrigger`
    :func:`compute_next_run_at` needs, decoupled from the ORM row."""

    trigger_type: str
    cron_expression: str | None = None
    run_at: datetime | None = None
    interval_seconds: float | None = None
    calendar_rule: CalendarRuleKind | None = None
    calendar_config: dict[str, object] | None = None


def compute_next_run_at(
    trigger: TriggerInput,
    *,
    now: datetime,
    timezone_name: str = "UTC",
    last_run: datetime | None = None,
) -> datetime | None:
    """Compute one trigger's own next due time in UTC, or ``None`` if it has none.

    ``EVENT_DRIVEN``, ``DEPENDENCY_DRIVEN``, ``MANUAL_TRIGGER``, and
    ``MAINTENANCE_WINDOW`` triggers always return ``None`` here -- none
    of the four fires from a clock. An event-driven trigger fires when
    its named event arrives; a dependency-driven job's eligibility is
    evaluated each sweep tick against :mod:`app.dependencies.engine`; a
    manual trigger only ever fires through
    ``POST /scheduler/jobs/{id}/run``; a maintenance-window trigger fires
    when its :class:`~app.models.maintenance.MaintenanceWindow` actually
    opens, which a sweep watches directly rather than pre-computing.

    Raises:
        ValidationError: If the trigger is missing a field its own type
            requires, or its cron/calendar configuration is invalid.
    """
    if trigger.trigger_type in _NO_COMPUTED_RUN_TRIGGER_TYPES:
        return None

    if trigger.trigger_type in _CALENDAR_LIKE_TRIGGER_TYPES:
        if trigger.calendar_rule is None:
            raise ValidationError(f"A {trigger.trigger_type!r} trigger requires a 'calendar_rule'.")
        cron_expression = calendar_rule_to_cron(
            trigger.calendar_rule, trigger.calendar_config or {}
        )
        try:
            return next_run_time(cron_expression, now=now)
        except InvalidScheduleError as exc:
            raise ValidationError(str(exc)) from exc

    shared_type = _SHARED_SCHEDULE_TYPE_MAP.get(trigger.trigger_type)
    if shared_type is None:
        raise ValidationError(f"Unrecognised trigger type {trigger.trigger_type!r}.")

    interval = (
        timedelta(seconds=trigger.interval_seconds)
        if trigger.interval_seconds is not None
        else None
    )

    try:
        shared_schedule = SharedSchedule(
            schedule_type=shared_type,
            cron_expression=trigger.cron_expression,
            run_at=trigger.run_at,
            interval=interval,
        )
        return _shared_compute_next_run(
            shared_schedule, now=now, timezone_name=timezone_name, last_run=last_run
        )
    except InvalidScheduleError as exc:
        raise ValidationError(str(exc)) from exc


def next_business_run_at(
    cron_expression: str, *, now: datetime, holidays: frozenset[date]
) -> datetime:
    """The next time *cron_expression* fires that does not fall on a holiday.

    Raises:
        ValidationError: If every candidate within
            :data:`_MAX_HOLIDAY_SKIPS` attempts lands on a holiday --
            almost certainly a holiday calendar covering every day of
            the relevant period, a configuration error worth surfacing
            rather than looping past silently.
    """
    candidate = now
    for _ in range(_MAX_HOLIDAY_SKIPS):
        try:
            candidate = next_run_time(cron_expression, now=candidate)
        except InvalidScheduleError as exc:
            raise ValidationError(str(exc)) from exc
        if candidate.date() not in holidays:
            return candidate
    raise ValidationError(
        f"No non-holiday run time found for {cron_expression!r} within "
        f"{_MAX_HOLIDAY_SKIPS} candidate days."
    )


# ---- maintenance-window dispatch suppression -----------------------------


def is_dispatch_suppressed(
    *, priority: JobPriority, active_window_allows_override: dict[str, bool] | None
) -> bool:
    """Whether at least one currently-active maintenance window blocks dispatch.

    *active_window_allows_override* maps each currently-active window's
    id to its own ``allow_critical_override`` flag -- empty or ``None``
    means no window is active, so nothing is suppressed. Dispatch is
    suppressed unless *every* active window either allows a critical
    override and this job is ``CRITICAL``.
    """
    if not active_window_allows_override:
        return False
    if priority is not JobPriority.CRITICAL:
        return True
    return not all(active_window_allows_override.values())


__all__ = [
    "ALLOWED_EXECUTION_TRANSITIONS",
    "ALLOWED_JOB_TRANSITIONS",
    "TriggerInput",
    "calendar_rule_to_cron",
    "compute_next_run_at",
    "is_dispatch_suppressed",
    "next_business_run_at",
    "validate_execution_transition",
    "validate_job_transition",
]
