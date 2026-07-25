"""Queue decorators.

``@job`` only *marks* a function (attaching the queue name it wants to
handle); it can't subscribe on its own because subscribing is async and
this decorator runs synchronously at import time. Pass every decorated
function to :func:`register_jobs` at service startup to actually wire
the subscriptions -- the same "mark now, wire later" pattern
:mod:`shared_core.events.decorators` uses.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime

from shared_core.queue.consumer import Consumer, MessageHandler
from shared_core.queue.scheduler import ScheduledTask, TaskScheduler

_QUEUE_NAME_ATTR = "__queue_name__"

ScheduledFn = Callable[[], Awaitable[None]]


def job(queue_name: str) -> Callable[[MessageHandler], MessageHandler]:
    """Mark the decorated async function as a handler for *queue_name*.

    Doesn't subscribe by itself -- see :func:`register_jobs`.
    """

    def decorator(handler: MessageHandler) -> MessageHandler:
        setattr(handler, _QUEUE_NAME_ATTR, queue_name)
        return handler

    return decorator


def get_job_queue_name(handler: MessageHandler) -> str | None:
    """Return the queue name *handler* was decorated with, or ``None`` if it wasn't."""
    name = getattr(handler, _QUEUE_NAME_ATTR, None)
    return name if isinstance(name, str) else None


async def register_jobs(consumer: Consumer, handlers: Iterable[MessageHandler]) -> None:
    """Subscribe every ``@job``-decorated function in *handlers* to its queue name.

    Functions in *handlers* that weren't decorated with ``@job`` are skipped.
    """
    for handler in handlers:
        queue_name = get_job_queue_name(handler)
        if queue_name is None:
            continue
        await consumer.subscribe(queue_name, handler)


def scheduled(
    scheduler: TaskScheduler,
    name: str,
    *,
    cron: str | None = None,
    run_at: datetime | None = None,
) -> Callable[[ScheduledFn], ScheduledFn]:
    """Register the decorated async function as a scheduled task, immediately.

    Unlike ``@job``, this registers eagerly (at decoration time): a
    :class:`~shared_core.queue.scheduler.TaskScheduler` has no async
    setup step to defer to, so there's no "wire it up later" split needed.
    """

    def decorator(fn: ScheduledFn) -> ScheduledFn:
        scheduler.register(ScheduledTask(name=name, fn=fn, cron_expression=cron, run_at=run_at))
        return fn

    return decorator


__all__ = ["get_job_queue_name", "job", "register_jobs", "scheduled"]
