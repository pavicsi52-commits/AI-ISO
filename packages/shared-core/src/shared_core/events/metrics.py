"""Event framework metrics.

Per docs/020_Enterprise_Event_Framework.md.txt "METRICS": Publish Rate,
Consume Rate, Processing Time, Error Rate, Queue Depth, Dead Letter
Count.

As of docs/021_Enterprise_Queue_Framework.md.txt, ``queue_messages_*``
(published/consumed/failed/retried/dead_lettered, from
:mod:`shared_core.metrics.standard`) are instrumented directly inside
:class:`shared_core.queue.manager.QueueManager` -- "the only place any
service talks to RabbitMQ directly" -- so every event publish/consume
(which always flows through it) is already counted there. This module
previously called those same counters itself (Prompt 020, before the
queue layer instrumented them); those calls were removed once the queue
layer took over, to avoid double-counting every event publish/consume
twice under the same ``queue=events.<event_name>`` label. What remains
here is genuinely event-specific: latency measured at the
``EventManager`` boundary (including validation/middleware time, not
just the raw broker round trip) and event-replay counts, neither of
which the queue layer has any visibility into.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from shared_core.events.publisher import EventPublisher
from shared_core.metrics.registry import create_counter, create_histogram
from shared_core.metrics.standard import queue_messages_failed_total

events_replayed_total = create_counter(
    "events_replayed_total", "Total events re-published via replay.", labels=["event_name"]
)
event_publish_latency_seconds = create_histogram(
    "event_publish_latency_seconds", "Time spent publishing an event, in seconds.", labels=["queue"]
)
event_consume_latency_seconds = create_histogram(
    "event_consume_latency_seconds",
    "Time spent in a subscriber handler, in seconds.",
    labels=["queue"],
)


def record_replayed(event_name: str, *, count: int) -> None:
    """Increment the replayed counter for *event_name* by *count*."""
    events_replayed_total.labels(event_name=event_name).inc(count)


def record_internal_failure(event_name: str) -> None:
    """Increment the failed-messages counter for an :class:`~shared_core.events.base.InternalEvent`.

    Internal events dispatch in-process (never through
    :class:`shared_core.queue.manager.QueueManager`, which records this
    same counter for every *other* event type) -- callers must only call
    this for a genuinely internal event, or a non-internal failure would
    be double-counted alongside the queue layer's own recording.
    """
    queue_messages_failed_total.labels(queue=EventPublisher.queue_name_for(event_name)).inc()


@contextmanager
def measure_publish(event_name: str) -> Iterator[None]:
    """Time a publish call ("Processing Time"). Publish/failure counts are recorded by
    :class:`shared_core.queue.manager.QueueManager` itself -- see module docstring.
    """
    queue = EventPublisher.queue_name_for(event_name)
    start = time.perf_counter()
    try:
        yield
    finally:
        event_publish_latency_seconds.labels(queue=queue).observe(time.perf_counter() - start)


@contextmanager
def measure_consume(event_name: str) -> Iterator[None]:
    """Time a subscriber handler call. Consume/failure counts are recorded by
    :class:`shared_core.queue.manager.QueueManager` itself -- see module docstring.
    """
    queue = EventPublisher.queue_name_for(event_name)
    start = time.perf_counter()
    try:
        yield
    finally:
        event_consume_latency_seconds.labels(queue=queue).observe(time.perf_counter() - start)


__all__ = [
    "event_consume_latency_seconds",
    "event_publish_latency_seconds",
    "events_replayed_total",
    "measure_consume",
    "measure_publish",
    "record_internal_failure",
    "record_replayed",
]
