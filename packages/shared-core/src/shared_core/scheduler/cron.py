"""Cron scheduling.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "CRON SUPPORT":
Seconds, Minutes, Hours, Day, Month, Weekday, Year (optional). "Validate
cron expressions before registration." Reuses
:func:`shared_core.queue.scheduler.validate_cron`/
:func:`~shared_core.queue.scheduler.next_run_time` directly (already
:mod:`croniter`-backed, already validated against
:mod:`shared_core.validation`'s cron rule) rather than reimplementing
cron parsing a second time -- wrapped only to translate
:mod:`shared_core.queue`'s own ``SchedulingError`` into this framework's
``InvalidScheduleError``, so a caller catching this framework's
exception hierarchy doesn't need to know cron validation happens to be
implemented via the queue package.
"""

from __future__ import annotations

from datetime import datetime

from shared_core.queue.exceptions import SchedulingError
from shared_core.queue.scheduler import next_run_time as _next_run_time
from shared_core.queue.scheduler import validate_cron as _validate_cron
from shared_core.scheduler.exceptions import InvalidScheduleError


def validate_cron(expression: str) -> None:
    """Ensure *expression* is a syntactically valid cron expression.

    Raises:
        InvalidScheduleError: If invalid.
    """
    try:
        _validate_cron(expression)
    except SchedulingError as exc:
        raise InvalidScheduleError(str(exc)) from exc


def next_run_time(expression: str, *, now: datetime | None = None) -> datetime:
    """Return the next UTC datetime *expression* fires at, strictly after *now*.

    Raises:
        InvalidScheduleError: If *expression* isn't a valid cron expression.
    """
    try:
        return _next_run_time(expression, now=now)
    except SchedulingError as exc:
        raise InvalidScheduleError(str(exc)) from exc


__all__ = ["next_run_time", "validate_cron"]
