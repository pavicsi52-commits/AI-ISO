"""Queue framework metrics.

Per docs/021_Enterprise_Queue_Framework.md.txt "METRICS": Published,
Consumed, Failed, Retried, Dead Letter, Processing Time, Queue Length,
Worker Count, Throughput, Prometheus Metrics.

Reuses :mod:`shared_core.metrics.standard`'s ``queue_messages_*``
counters (defined since Prompt 012; first actually instrumented by
Prompt 020's events layer, in ``events/metrics.py``). This prompt moves
that instrumentation down to where it structurally belongs --
:class:`~shared_core.queue.manager.QueueManager` itself, "the only place
any service talks to RabbitMQ directly" -- so every publish/consume/
retry/dead-letter through *any* caller (not just events) is counted.
``events/metrics.py``'s former manual calls to these same counters were
removed to avoid double-counting now that the queue layer beneath every
event publish/consume already records them; see that module's updated
docstring.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from shared_core.metrics.registry import create_counter, create_gauge, create_histogram
from shared_core.metrics.standard import (
    queue_messages_consumed_total,
    queue_messages_dead_lettered_total,
    queue_messages_failed_total,
    queue_messages_published_total,
)

queue_messages_retried_total = create_counter(
    "queue_messages_retried_total", "Total message redelivery attempts.", labels=["queue"]
)
queue_message_processing_seconds = create_histogram(
    "queue_message_processing_seconds",
    "Time spent in a consumer handler, in seconds.",
    labels=["queue"],
)
queue_worker_count = create_gauge(
    "queue_worker_count", "Number of active workers in a pool.", labels=["pool"]
)
queue_depth = create_gauge("queue_depth", "Number of ready messages in a queue.", labels=["queue"])


def record_published(queue_name: str) -> None:
    """Increment the published-messages counter for *queue_name* ("Published")."""
    queue_messages_published_total.labels(queue=queue_name).inc()


def record_consumed(queue_name: str) -> None:
    """Increment the consumed-messages counter for *queue_name* ("Consumed")."""
    queue_messages_consumed_total.labels(queue=queue_name).inc()


def record_failed(queue_name: str) -> None:
    """Increment the failed-messages counter for *queue_name* ("Failed")."""
    queue_messages_failed_total.labels(queue=queue_name).inc()


def record_retried(queue_name: str) -> None:
    """Increment the retry counter for *queue_name* ("Retried")."""
    queue_messages_retried_total.labels(queue=queue_name).inc()


def record_dead_lettered(queue_name: str) -> None:
    """Increment the dead-lettered counter for *queue_name* ("Dead Letter")."""
    queue_messages_dead_lettered_total.labels(queue=queue_name).inc()


def set_worker_count(pool_name: str, count: int) -> None:
    """Set the current worker gauge for *pool_name* ("Worker Count")."""
    queue_worker_count.labels(pool=pool_name).set(count)


def set_queue_depth(queue_name: str, depth: int) -> None:
    """Set the current queue-depth gauge for *queue_name* ("Queue Length")."""
    queue_depth.labels(queue=queue_name).set(depth)


@contextmanager
def measure_processing(queue_name: str) -> Iterator[None]:
    """Time a consumer handler call ("Processing Time"), recording it regardless of outcome."""
    start = time.perf_counter()
    try:
        yield
    finally:
        queue_message_processing_seconds.labels(queue=queue_name).observe(
            time.perf_counter() - start
        )


__all__ = [
    "measure_processing",
    "queue_depth",
    "queue_message_processing_seconds",
    "queue_messages_retried_total",
    "queue_worker_count",
    "record_consumed",
    "record_dead_lettered",
    "record_failed",
    "record_published",
    "record_retried",
    "set_queue_depth",
    "set_worker_count",
]
