"""Job declaration decorators.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "DECORATORS":
``@scheduled``, ``@cron``, ``@interval``, ``@delay``, ``@once``,
``@retryable``, ``@exclusive``, ``@timeout``.

Each decorator only *marks* a plain async function with scheduling/
execution metadata (attaching it to the function object, the same
"mark now, wire later" pattern as :mod:`shared_core.queue.decorators`'s
``@job``) -- it can't register the function as a running :class:`~shared_core.scheduler.job.Job`
by itself, since building one also needs a ``job_name``/``job_type`` and
(usually) a :class:`~shared_core.scheduler.registry.JobRegistry` to
register into. Pass a decorated function to :func:`build_job_from_decorated`
at service startup to actually build the :class:`~shared_core.scheduler.job.Job`.
Decorators stack: a function may carry ``@cron``, ``@retryable``, and
``@timeout`` all at once, each only setting its own piece of metadata.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from shared_core.queue.retry import RetryPolicy
from shared_core.scheduler.job import Job, JobFn, JobType, build_job
from shared_core.scheduler.schedule import Schedule, ScheduleType

_METADATA_ATTR = "__scheduler_metadata__"


@dataclass(slots=True)
class JobDecoratorMetadata:
    """Scheduling/execution metadata accumulated on a decorated function."""

    schedule: Schedule | None = None
    retry_policy: RetryPolicy | None = None
    exclusive: bool = False
    timeout_seconds: float | None = None


def _metadata_of(fn: JobFn) -> JobDecoratorMetadata:
    existing = getattr(fn, _METADATA_ATTR, None)
    if isinstance(existing, JobDecoratorMetadata):
        return existing
    created = JobDecoratorMetadata()
    setattr(fn, _METADATA_ATTR, created)
    return created


def scheduled(schedule: Schedule) -> Callable[[JobFn], JobFn]:
    """Mark the decorated function with an arbitrary :class:`Schedule` ("@scheduled")."""

    def decorator(fn: JobFn) -> JobFn:
        _metadata_of(fn).schedule = schedule
        return fn

    return decorator


def cron(expression: str) -> Callable[[JobFn], JobFn]:
    """Mark the decorated function to run on a cron schedule ("@cron")."""

    def decorator(fn: JobFn) -> JobFn:
        _metadata_of(fn).schedule = Schedule(
            schedule_type=ScheduleType.CRON_EXPRESSION, cron_expression=expression
        )
        return fn

    return decorator


def interval(seconds: float) -> Callable[[JobFn], JobFn]:
    """Mark the decorated function to run every *seconds*, at a fixed rate ("@interval")."""

    def decorator(fn: JobFn) -> JobFn:
        _metadata_of(fn).schedule = Schedule(
            schedule_type=ScheduleType.FIXED_RATE, interval=timedelta(seconds=seconds)
        )
        return fn

    return decorator


def delay(seconds: float) -> Callable[[JobFn], JobFn]:
    """Mark the decorated function to run *seconds* after its previous run finishes ("@delay")."""

    def decorator(fn: JobFn) -> JobFn:
        _metadata_of(fn).schedule = Schedule(
            schedule_type=ScheduleType.FIXED_DELAY, delay=timedelta(seconds=seconds)
        )
        return fn

    return decorator


def once(*, run_at: datetime | None = None) -> Callable[[JobFn], JobFn]:
    """Mark the decorated function to run exactly one time ("@once").

    Runs as soon as scheduled if *run_at* isn't given, or at that exact
    time otherwise.
    """

    def decorator(fn: JobFn) -> JobFn:
        _metadata_of(fn).schedule = (
            Schedule(schedule_type=ScheduleType.SCHEDULED_TIME, run_at=run_at)
            if run_at is not None
            else Schedule(schedule_type=ScheduleType.IMMEDIATE)
        )
        return fn

    return decorator


def retryable(
    *,
    max_attempts: int = 3,
    backoff_base_seconds: float | None = None,
    backoff_max_seconds: float | None = None,
) -> Callable[[JobFn], JobFn]:
    """Mark the decorated function's retry policy ("@retryable")."""

    def decorator(fn: JobFn) -> JobFn:
        kwargs: dict[str, Any] = {"max_attempts": max_attempts}
        if backoff_base_seconds is not None:
            kwargs["backoff_base_seconds"] = backoff_base_seconds
        if backoff_max_seconds is not None:
            kwargs["backoff_max_seconds"] = backoff_max_seconds
        _metadata_of(fn).retry_policy = RetryPolicy(**kwargs)
        return fn

    return decorator


def exclusive(fn: JobFn) -> JobFn:
    """Mark the decorated function as requiring the exclusive-execution lock ("@exclusive")."""
    _metadata_of(fn).exclusive = True
    return fn


def timeout(seconds: float) -> Callable[[JobFn], JobFn]:
    """Mark the decorated function's execution timeout ("@timeout")."""

    def decorator(fn: JobFn) -> JobFn:
        _metadata_of(fn).timeout_seconds = seconds
        return fn

    return decorator


def build_job_from_decorated(
    fn: JobFn, *, job_name: str, job_type: JobType, **overrides: Any
) -> Job:
    """Build a :class:`Job` from a decorator-annotated function.

    A function carrying no scheduling decorator at all defaults to
    ``IMMEDIATE``. *overrides* are forwarded to
    :func:`~shared_core.scheduler.job.build_job` and win over any
    decorator-derived value with the same name.
    """
    meta = _metadata_of(fn)
    fields: dict[str, Any] = {}
    if meta.retry_policy is not None:
        fields["retry_policy"] = meta.retry_policy
    if meta.timeout_seconds is not None:
        fields["timeout_seconds"] = meta.timeout_seconds
    metadata = dict(overrides.pop("metadata", {}))
    if meta.exclusive:
        metadata["exclusive"] = True
    if metadata:
        fields["metadata"] = metadata
    fields.update(overrides)
    schedule = meta.schedule or Schedule(schedule_type=ScheduleType.IMMEDIATE)
    return build_job(job_name=job_name, job_type=job_type, fn=fn, schedule=schedule, **fields)


__all__ = [
    "JobDecoratorMetadata",
    "build_job_from_decorated",
    "cron",
    "delay",
    "exclusive",
    "interval",
    "once",
    "retryable",
    "scheduled",
    "timeout",
]
