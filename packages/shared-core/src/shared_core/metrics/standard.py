"""Standard cross-cutting metrics every service can reuse instead of
inventing its own.
"""

from __future__ import annotations

from shared_core.metrics.registry import create_counter, create_histogram

http_requests_total = create_counter(
    "http_requests_total",
    "Total HTTP requests processed.",
    labels=["method", "path", "status_code"],
)

http_request_duration_seconds = create_histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    labels=["method", "path"],
)

queue_messages_published_total = create_counter(
    "queue_messages_published_total", "Total messages published to a queue.", labels=["queue"]
)

queue_messages_consumed_total = create_counter(
    "queue_messages_consumed_total", "Total messages successfully consumed.", labels=["queue"]
)

queue_messages_failed_total = create_counter(
    "queue_messages_failed_total", "Total messages that failed processing.", labels=["queue"]
)

queue_messages_dead_lettered_total = create_counter(
    "queue_messages_dead_lettered_total",
    "Total messages moved to a dead-letter queue.",
    labels=["queue"],
)

cache_hits_total = create_counter("cache_hits_total", "Total cache hits.", labels=["cache"])
cache_misses_total = create_counter("cache_misses_total", "Total cache misses.", labels=["cache"])
