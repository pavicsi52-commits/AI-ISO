"""Schedule recurrence -- when a report next runs ("SCHEDULING").

Reuses ``shared_core.scheduler``'s own vetted cron parser and timezone
helpers rather than reimplementing either; only the fixed-frequency
cadences (hourly/daily/weekly/monthly) and the one-time case are
computed here, because those are simple enough that a cron round-trip
would obscure rather than clarify.

**Time zones are honoured, not assumed.** "Monthly on the 1st at 09:00"
in ``Europe/Berlin`` is a different instant in January than in July,
and a compliance report that silently drifts an hour twice a year is a
real defect. Fixed cadences advance in the schedule's own local zone
and are converted back to UTC, so the local wall-clock time is what
stays constant.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from shared_core.exceptions.validation import ValidationError
from shared_core.scheduler.cron import next_run_time, validate_cron
from shared_core.scheduler.timezone import validate_timezone

from app.models.enums import ScheduleFrequency

_MONTHS_IN_YEAR = 12


def _add_one_month(moment: datetime) -> datetime:
    """Advance one calendar month, clamping to the month's last day.

    January 31st + one month is February 28th (or 29th), not March 3rd.
    Rolling over would silently move a month-end report into the
    following month, which is exactly the kind of drift a monthly
    compliance report cannot tolerate.
    """
    year = moment.year + (1 if moment.month == _MONTHS_IN_YEAR else 0)
    month = 1 if moment.month == _MONTHS_IN_YEAR else moment.month + 1

    day = moment.day
    while day > 0:
        try:
            return moment.replace(year=year, month=month, day=day)
        except ValueError:
            day -= 1
    raise ValidationError(f"Could not advance {moment.isoformat()} by one month.")


def validate_schedule(
    frequency: ScheduleFrequency, cron_expression: str | None, timezone_name: str
) -> None:
    """Validate a schedule's own configuration.

    Raises:
        ValidationError: If the timezone is unknown, or a ``CRON``
            schedule has a missing or invalid expression.
    """
    try:
        validate_timezone(timezone_name)
    except Exception as exc:
        raise ValidationError(f"Unknown time zone {timezone_name!r}.") from exc

    if frequency is ScheduleFrequency.CRON:
        if not cron_expression:
            raise ValidationError("A cron schedule requires a cron_expression.")
        try:
            validate_cron(cron_expression)
        except Exception as exc:
            raise ValidationError(f"Invalid cron expression {cron_expression!r}: {exc}") from exc
    elif cron_expression:
        raise ValidationError(
            f"A {str(frequency)!r} schedule must not carry a cron_expression; "
            "use frequency=cron for expression-driven schedules."
        )


def compute_next_run(
    frequency: ScheduleFrequency,
    *,
    timezone_name: str = "UTC",
    cron_expression: str | None = None,
    starts_at: datetime,
    after: datetime | None = None,
) -> datetime | None:
    """The next run instant in UTC, or ``None`` if there is no next run.

    ``None`` means "this schedule is finished" -- which is the correct
    and only sensible answer for a one-time schedule that has already
    fired. Returning the past instead would make the worker re-run it
    forever.

    Raises:
        ValidationError: If the schedule's configuration is invalid.
    """
    validate_schedule(frequency, cron_expression, timezone_name)
    now = after or datetime.now(UTC)
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)

    if frequency is ScheduleFrequency.ONE_TIME:
        return starts_at if starts_at > now else None

    if frequency is ScheduleFrequency.CRON:
        assert cron_expression is not None
        anchor = max(now, starts_at - timedelta(microseconds=1))
        return next_run_time(cron_expression, now=anchor).astimezone(UTC)

    if starts_at > now:
        return starts_at

    zone = ZoneInfo(timezone_name)
    local_start = starts_at.astimezone(zone)
    local_now = now.astimezone(zone)

    candidate = local_start
    # Advancing step by step, rather than computing a multiplier, is
    # what keeps DST correct: each step is applied in local time, so a
    # 09:00 daily report stays at 09:00 across a transition.
    while candidate <= local_now:
        match frequency:
            case ScheduleFrequency.HOURLY:
                candidate = candidate + timedelta(hours=1)
            case ScheduleFrequency.DAILY:
                candidate = (candidate + timedelta(days=1)).replace(
                    hour=local_start.hour, minute=local_start.minute
                )
            case ScheduleFrequency.WEEKLY:
                candidate = (candidate + timedelta(weeks=1)).replace(
                    hour=local_start.hour, minute=local_start.minute
                )
            case ScheduleFrequency.MONTHLY:
                candidate = _add_one_month(candidate).replace(
                    hour=local_start.hour, minute=local_start.minute
                )
            case _:  # pragma: no cover -- every member handled above
                raise ValidationError(f"Unsupported frequency {frequency!r}.")
    return candidate.astimezone(UTC)


__all__ = ["compute_next_run", "validate_schedule"]
