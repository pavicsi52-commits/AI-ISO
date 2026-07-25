"""Task scheduling.

Per docs/021_Enterprise_Queue_Framework.md.txt "DELAYED JOBS": Cron,
Recurring. "After Time" and "Specific Date" are one-shot delays, covered
directly by :mod:`shared_core.queue.delay` /
:meth:`shared_core.queue.producer.Producer.publish_scheduled`; this
module is what tracks *repeating* (cron) and future one-shot schedules
and reports which are currently due, independent of any specific queue.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from croniter import croniter

from shared_core.logging.logger import get_logger
from shared_core.queue.exceptions import SchedulingError
from shared_core.validation.rules.field import validate_cron_expression

logger = get_logger("shared_core.queue.scheduler")

TaskFn = Callable[[], Awaitable[None]]

_DEFAULT_ANCHOR_LOOKBACK = timedelta(minutes=1)


def validate_cron(expression: str) -> None:
    """Ensure *expression* is a syntactically valid 5-field cron expression.

    Raises:
        SchedulingError: If invalid.
    """
    result = validate_cron_expression(expression)
    if not result.valid:
        raise SchedulingError(
            f"Invalid cron expression '{expression}': {'; '.join(result.errors)}."
        )


def next_run_time(expression: str, *, now: datetime | None = None) -> datetime:
    """Return the next UTC datetime *expression* fires at, strictly after *now*.

    Raises:
        SchedulingError: If *expression* isn't a valid cron expression.
    """
    validate_cron(expression)
    reference = now or datetime.now(UTC)
    result: datetime = croniter(expression, reference).get_next(datetime)
    return result


@dataclass(slots=True)
class ScheduledTask:
    """One task registered with a :class:`TaskScheduler` -- recurring (cron) or one-shot."""

    name: str
    fn: TaskFn
    cron_expression: str | None = None
    run_at: datetime | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.cron_expression is None and self.run_at is None:
            raise SchedulingError(f"Task '{self.name}' must set either cron_expression or run_at.")
        if self.cron_expression is not None:
            validate_cron(self.cron_expression)


@dataclass(slots=True)
class TaskScheduler:
    """Tracks registered tasks and reports which are due ("Cron" / "Recurring").

    Purely a due-task tracker -- callers drive it by polling
    :meth:`run_due` on their own interval (e.g. from a
    :class:`~shared_core.queue.worker.WorkerPool` worker), rather than
    this class owning its own event loop or timer.
    """

    _tasks: dict[str, ScheduledTask] = field(default_factory=dict)
    _last_checked: dict[str, datetime] = field(default_factory=dict)
    _last_run: dict[str, datetime] = field(default_factory=dict)

    def register(self, task: ScheduledTask) -> None:
        """Register (or replace) a scheduled task."""
        self._tasks[task.name] = task

    def unregister(self, name: str) -> None:
        """Remove a registered task, if present."""
        self._tasks.pop(name, None)
        self._last_checked.pop(name, None)
        self._last_run.pop(name, None)

    def due_tasks(self, *, now: datetime | None = None) -> list[ScheduledTask]:
        """Return every enabled task whose schedule has come due since it was last checked."""
        reference = now or datetime.now(UTC)
        due = [
            task for task in self._tasks.values() if task.enabled and self._is_due(task, reference)
        ]
        for task in self._tasks.values():
            if task.enabled:
                self._last_checked[task.name] = reference
        return due

    def _is_due(self, task: ScheduledTask, reference: datetime) -> bool:
        if task.cron_expression is not None:
            anchor = self._last_checked.get(task.name, reference - _DEFAULT_ANCHOR_LOOKBACK)
            next_fire: datetime = croniter(task.cron_expression, anchor).get_next(datetime)
            return next_fire <= reference
        if task.run_at is None:  # pragma: no cover -- enforced by __post_init__
            raise SchedulingError(f"Task '{task.name}' has neither cron_expression nor run_at.")
        return task.run_at <= reference and task.name not in self._last_run

    async def run_due(self, *, now: datetime | None = None) -> int:
        """Run every currently-due task, recording it as last-run.

        A single task's exception is logged and does not stop the rest.

        Returns:
            The number of tasks actually run.
        """
        reference = now or datetime.now(UTC)
        ran = 0
        for task in self.due_tasks(now=reference):
            self._last_run[task.name] = reference
            try:
                await task.fn()
                ran += 1
            except Exception:
                logger.warning("scheduled task failed", extra={"extra_fields": {"task": task.name}})
        return ran


__all__ = ["ScheduledTask", "TaskScheduler", "next_run_time", "validate_cron"]
