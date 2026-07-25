"""Scheduler metrics.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "METRICS": Registered
Jobs, Running Jobs, Completed Jobs, Failed Jobs, Retry Count, Average
Duration, Longest Job, Worker Count, Queue Depth, Execution Rate,
Scheduler Uptime. "Export Prometheus metrics." Reuses
:mod:`shared_core.metrics.registry` directly (already namespaced,
already registered on the shared default registry) rather than a second
metrics system -- this module only defines the scheduler-specific
series and the setters that populate them. "Average Duration"/"Longest
Job" are both derivable from the ``scheduler_job_duration_seconds``
histogram (mean and max bucket, respectively) rather than needing two
separate series.
"""

from __future__ import annotations

from shared_core.metrics.registry import create_counter, create_gauge, create_histogram

scheduler_registered_jobs = create_gauge(
    "scheduler_registered_jobs", "Number of jobs currently registered."
)
scheduler_running_jobs = create_gauge(
    "scheduler_running_jobs", "Number of jobs currently executing."
)
scheduler_completed_jobs_total = create_counter(
    "scheduler_completed_jobs_total", "Total job executions that succeeded."
)
scheduler_failed_jobs_total = create_counter(
    "scheduler_failed_jobs_total", "Total job executions that failed."
)
scheduler_retries_total = create_counter(
    "scheduler_retries_total", "Total retry attempts across every job execution."
)
scheduler_job_duration_seconds = create_histogram(
    "scheduler_job_duration_seconds", "Job execution duration, in seconds."
)
scheduler_worker_count = create_gauge(
    "scheduler_worker_count", "Number of active scheduler worker nodes."
)
scheduler_queue_depth = create_gauge(
    "scheduler_queue_depth", "Number of due jobs currently queued."
)
scheduler_execution_rate = create_gauge(
    "scheduler_execution_rate", "Job executions per second, over the most recent window."
)
scheduler_uptime_seconds = create_gauge(
    "scheduler_uptime_seconds", "Seconds since this scheduler node started."
)


def record_registered(count: int) -> None:
    """Set the registered-jobs gauge ("Registered Jobs")."""
    scheduler_registered_jobs.set(count)


def record_running(count: int) -> None:
    """Set the running-jobs gauge ("Running Jobs")."""
    scheduler_running_jobs.set(count)


def record_duration(seconds: float) -> None:
    """Observe one job execution's duration ("Average Duration"/"Longest Job")."""
    scheduler_job_duration_seconds.observe(seconds)


def record_execution(*, succeeded: bool, duration_seconds: float, retries: int = 0) -> None:
    """Record one full execution's outcome in a single call.

    *retries* is the number of retry attempts beyond the first
    ("Retry Count").
    """
    if succeeded:
        scheduler_completed_jobs_total.inc()
    else:
        scheduler_failed_jobs_total.inc()
    record_duration(duration_seconds)
    if retries > 0:
        scheduler_retries_total.inc(retries)


def set_worker_count(count: int) -> None:
    """Set the active-worker gauge ("Worker Count")."""
    scheduler_worker_count.set(count)


def set_queue_depth(depth: int) -> None:
    """Set the queue-depth gauge ("Queue Depth")."""
    scheduler_queue_depth.set(depth)


def set_execution_rate(jobs_per_second: float) -> None:
    """Set the execution-rate gauge ("Execution Rate")."""
    scheduler_execution_rate.set(jobs_per_second)


def set_uptime_seconds(seconds: float) -> None:
    """Set the scheduler-uptime gauge ("Scheduler Uptime")."""
    scheduler_uptime_seconds.set(seconds)


__all__ = [
    "record_duration",
    "record_execution",
    "record_registered",
    "record_running",
    "scheduler_completed_jobs_total",
    "scheduler_execution_rate",
    "scheduler_failed_jobs_total",
    "scheduler_job_duration_seconds",
    "scheduler_queue_depth",
    "scheduler_registered_jobs",
    "scheduler_retries_total",
    "scheduler_running_jobs",
    "scheduler_uptime_seconds",
    "scheduler_worker_count",
    "set_execution_rate",
    "set_queue_depth",
    "set_uptime_seconds",
    "set_worker_count",
]
