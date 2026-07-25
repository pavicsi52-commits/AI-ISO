"""Monitoring framework metrics.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "METRICS
COLLECTION": Request Count, Response Time, Error Rate, Success Rate,
Queue Size, Worker Count, Database Connections, Redis Hit Ratio, Cache
Miss Ratio, Storage Usage, Workflow Duration, Automation Duration,
Validation Duration, AI Request Duration, Plugin Count, Connector Count.

Most of this list is already covered elsewhere and deliberately not
duplicated here: Request Count / Response Time by
``shared_core.metrics.standard.http_requests_total``/
``http_request_duration_seconds`` (Prompt 012); Queue Size / Worker
Count by ``shared_core.queue.metrics.queue_depth``/``queue_worker_count``
(Prompt 021); Redis Hit Ratio / Cache Miss Ratio by
``shared_core.cache.statistics.CacheStatistics`` (Prompt 019, computed
in-process rather than read back from a Prometheus counter). What's new
here is Prometheus instrumentation for subsystems that don't have their
own metrics module yet -- established now, the same way Prompt 012
pre-defined ``queue_messages_*`` years before Prompt 020/021 actually
instrumented them.
"""

from __future__ import annotations

from shared_core.metrics.registry import create_gauge, create_histogram

database_connections_in_use = create_gauge(
    "database_connections_in_use",
    "Database connections currently checked out of the pool.",
    labels=["service"],
)
storage_usage_bytes = create_gauge(
    "storage_usage_bytes", "Storage bytes currently used.", labels=["bucket"]
)
workflow_duration_seconds = create_histogram(
    "workflow_duration_seconds", "Time spent executing a workflow, in seconds.", labels=["workflow"]
)
automation_duration_seconds = create_histogram(
    "automation_duration_seconds",
    "Time spent executing an automation, in seconds.",
    labels=["automation"],
)
validation_duration_seconds = create_histogram(
    "validation_duration_seconds",
    "Time spent running a validation pipeline, in seconds.",
    labels=["layer"],
)
ai_request_duration_seconds = create_histogram(
    "ai_request_duration_seconds",
    "Time spent on an AI provider request, in seconds.",
    labels=["provider"],
)
plugin_count = create_gauge(
    "plugin_count", "Number of currently loaded plugins.", labels=["service"]
)
connector_count = create_gauge(
    "connector_count", "Number of currently registered connectors.", labels=["service"]
)


__all__ = [
    "ai_request_duration_seconds",
    "automation_duration_seconds",
    "connector_count",
    "database_connections_in_use",
    "plugin_count",
    "storage_usage_bytes",
    "validation_duration_seconds",
    "workflow_duration_seconds",
]
