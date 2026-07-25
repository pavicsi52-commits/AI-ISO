"""Workflow SDK metrics.

Per docs/028_Enterprise_Workflow_SDK.md.txt "METRICS": Workflow Count,
Execution Time, Task Duration, Success Rate, Failure Rate, Retry
Count, Rollback Count, Queue Time, Approval Time. Reuses
:mod:`shared_core.metrics.registry` directly (already namespaced,
already registered on the shared default registry) rather than a
second metrics system.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from shared_core.metrics.registry import create_counter, create_histogram

workflow_executions_total = create_counter(
    "workflow_executions_total", "Total workflow executions started.", labels=["workflow_id"]
)
workflow_success_total = create_counter(
    "workflow_success_total", "Total workflow executions that succeeded.", labels=["workflow_id"]
)
workflow_failure_total = create_counter(
    "workflow_failure_total", "Total workflow executions that failed.", labels=["workflow_id"]
)
workflow_retries_total = create_counter(
    "workflow_retries_total",
    "Total retry attempts across every node execution.",
    labels=["workflow_id"],
)
workflow_rollbacks_total = create_counter(
    "workflow_rollbacks_total", "Total workflow rollbacks executed.", labels=["workflow_id"]
)
workflow_execution_seconds = create_histogram(
    "workflow_execution_seconds",
    "Total workflow execution duration, in seconds.",
    labels=["workflow_id"],
)
workflow_task_duration_seconds = create_histogram(
    "workflow_task_duration_seconds",
    "One node's task duration, in seconds.",
    labels=["workflow_id", "node_type"],
)
workflow_queue_seconds = create_histogram(
    "workflow_queue_seconds",
    "Time a task spent queued before starting, in seconds.",
    labels=["workflow_id"],
)
workflow_approval_seconds = create_histogram(
    "workflow_approval_seconds",
    "Time an approval request took to resolve, in seconds.",
    labels=["workflow_id"],
)


def record_execution_started(workflow_id: str) -> None:
    """Increment the executions-started counter ("Workflow Count")."""
    workflow_executions_total.labels(workflow_id=workflow_id).inc()


def record_success(workflow_id: str, *, duration_seconds: float) -> None:
    """Increment the success counter and observe total duration ("Success Rate")."""
    workflow_success_total.labels(workflow_id=workflow_id).inc()
    workflow_execution_seconds.labels(workflow_id=workflow_id).observe(duration_seconds)


def record_failure(workflow_id: str, *, duration_seconds: float) -> None:
    """Increment the failure counter and observe total duration ("Failure Rate")."""
    workflow_failure_total.labels(workflow_id=workflow_id).inc()
    workflow_execution_seconds.labels(workflow_id=workflow_id).observe(duration_seconds)


def record_retry(workflow_id: str) -> None:
    """Increment the retry counter ("Retry Count")."""
    workflow_retries_total.labels(workflow_id=workflow_id).inc()


def record_rollback(workflow_id: str) -> None:
    """Increment the rollback counter ("Rollback Count")."""
    workflow_rollbacks_total.labels(workflow_id=workflow_id).inc()


def record_task_duration(workflow_id: str, node_type: str, duration_seconds: float) -> None:
    """Observe one task's duration ("Task Duration")."""
    workflow_task_duration_seconds.labels(workflow_id=workflow_id, node_type=node_type).observe(
        duration_seconds
    )


def record_queue_time(workflow_id: str, duration_seconds: float) -> None:
    """Observe how long a task waited queued before starting ("Queue Time")."""
    workflow_queue_seconds.labels(workflow_id=workflow_id).observe(duration_seconds)


def record_approval_time(workflow_id: str, duration_seconds: float) -> None:
    """Observe how long an approval took to resolve ("Approval Time")."""
    workflow_approval_seconds.labels(workflow_id=workflow_id).observe(duration_seconds)


@contextmanager
def measure_task(workflow_id: str, node_type: str) -> Iterator[None]:
    """Time a task's execution, recording it regardless of outcome ("Task Duration")."""
    start = time.perf_counter()
    try:
        yield
    finally:
        record_task_duration(workflow_id, node_type, time.perf_counter() - start)


__all__ = [
    "measure_task",
    "record_approval_time",
    "record_execution_started",
    "record_failure",
    "record_queue_time",
    "record_retry",
    "record_rollback",
    "record_success",
    "record_task_duration",
    "workflow_approval_seconds",
    "workflow_execution_seconds",
    "workflow_executions_total",
    "workflow_failure_total",
    "workflow_queue_seconds",
    "workflow_retries_total",
    "workflow_rollbacks_total",
    "workflow_success_total",
    "workflow_task_duration_seconds",
]
