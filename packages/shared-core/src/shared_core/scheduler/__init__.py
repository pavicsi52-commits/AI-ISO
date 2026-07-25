"""Enterprise Scheduler Framework.

Per docs/026_Enterprise_Scheduler_Framework.md.txt. A centralized
scheduler for recurring, delayed, event-triggered, and one-time jobs,
built entirely on primitives this monorepo already has: cron/scheduling
computation on :mod:`shared_core.queue.scheduler`, distributed locking
and leader election on :mod:`shared_core.cache.locks`, retry/backoff on
:mod:`shared_core.queue.retry`, delivery on :mod:`shared_core.queue`,
health status on :mod:`shared_core.monitoring`, and metrics on
:mod:`shared_core.metrics`.

The most common entry point is :func:`~shared_core.scheduler.factory.create_scheduler_framework`,
which wires every module below into one running
:class:`~shared_core.scheduler.manager.SchedulerManager`.

``@cron`` (the job-declaration decorator) is deliberately not
re-exported here: it would shadow this package's own ``cron`` submodule
(:mod:`shared_core.scheduler.cron`), which Python auto-binds as a
package attribute on import. Reach it via
``shared_core.scheduler.decorators.cron`` instead -- the same
resolution :mod:`shared_core.telemetry` uses for its ``trace``/``span``
decorators vs. submodules.
"""

from __future__ import annotations

from shared_core.scheduler.audit import (
    audit_cancellation,
    audit_deletion,
    audit_execution,
    audit_modification,
    audit_pause,
    audit_registration,
    audit_resume,
    audit_retry,
)
from shared_core.scheduler.calendar import CalendarRule, parse_calendar_rule
from shared_core.scheduler.cron import next_run_time, validate_cron
from shared_core.scheduler.decorators import (
    JobDecoratorMetadata,
    build_job_from_decorated,
    delay,
    exclusive,
    interval,
    once,
    retryable,
    scheduled,
    timeout,
)
from shared_core.scheduler.dependency import DependencyGraph, JobDependency, JobStatusLookup
from shared_core.scheduler.engine import SchedulerEngine, compute_next_run
from shared_core.scheduler.exceptions import (
    DependencyNotSatisfiedError,
    InvalidScheduleError,
    JobExecutionError,
    JobNotFoundError,
    JobTimeoutError,
    LeaderElectionError,
    MaintenanceWindowActiveError,
)
from shared_core.scheduler.executor import ExecutionResult, JobExecutor
from shared_core.scheduler.factory import create_scheduler_framework
from shared_core.scheduler.failover import FailoverCoordinator, NodeFailureHandler
from shared_core.scheduler.health import SchedulerHealthReport, build_health_report
from shared_core.scheduler.heartbeat import HeartbeatRegistry, HeartbeatSender, NodeHeartbeat
from shared_core.scheduler.helpers import format_duration, is_due, job_summary
from shared_core.scheduler.history import HistoryEntry, HistoryStore
from shared_core.scheduler.job import Job, JobFn, JobType, build_job, new_job_id
from shared_core.scheduler.leader import LeaderElection, cluster_has_leader
from shared_core.scheduler.locking import exclusive_job_execution, job_lock_key
from shared_core.scheduler.manager import SchedulerManager, new_node_id
from shared_core.scheduler.metrics import (
    record_duration,
    record_execution,
    record_registered,
    record_running,
    scheduler_completed_jobs_total,
    scheduler_execution_rate,
    scheduler_failed_jobs_total,
    scheduler_job_duration_seconds,
    scheduler_queue_depth,
    scheduler_registered_jobs,
    scheduler_retries_total,
    scheduler_running_jobs,
    scheduler_uptime_seconds,
    scheduler_worker_count,
    set_execution_rate,
    set_queue_depth,
    set_uptime_seconds,
    set_worker_count,
)
from shared_core.scheduler.middleware import (
    ExecuteHandler,
    ExecuteMiddleware,
    PermissionChecker,
    TenantChecker,
    apply_middleware,
    build_audit_middleware,
    build_security_validation_middleware,
    build_telemetry_middleware,
    build_tenant_validation_middleware,
    correlation_id_middleware,
    error_handling_middleware,
    execution_logging_middleware,
    metrics_collection_middleware,
)
from shared_core.scheduler.queue import (
    DEFAULT_JOB_QUEUE_NAME,
    JobIdHandler,
    JobQueue,
    build_due_job_message,
    job_id_from_message,
)
from shared_core.scheduler.registry import JobRegistry
from shared_core.scheduler.retry import (
    RetryPolicy,
    compute_backoff_delay,
    is_retryable,
    job_retry_policy,
)
from shared_core.scheduler.schedule import Schedule, ScheduleType
from shared_core.scheduler.timezone import convert_timezone, localize, to_utc, validate_timezone
from shared_core.scheduler.worker import Worker

__all__ = [
    "DEFAULT_JOB_QUEUE_NAME",
    "CalendarRule",
    "DependencyGraph",
    "DependencyNotSatisfiedError",
    "ExecuteHandler",
    "ExecuteMiddleware",
    "ExecutionResult",
    "FailoverCoordinator",
    "HeartbeatRegistry",
    "HeartbeatSender",
    "HistoryEntry",
    "HistoryStore",
    "InvalidScheduleError",
    "Job",
    "JobDecoratorMetadata",
    "JobDependency",
    "JobExecutionError",
    "JobExecutor",
    "JobFn",
    "JobIdHandler",
    "JobNotFoundError",
    "JobQueue",
    "JobRegistry",
    "JobStatusLookup",
    "JobTimeoutError",
    "JobType",
    "LeaderElection",
    "LeaderElectionError",
    "MaintenanceWindowActiveError",
    "NodeFailureHandler",
    "NodeHeartbeat",
    "PermissionChecker",
    "RetryPolicy",
    "Schedule",
    "ScheduleType",
    "SchedulerEngine",
    "SchedulerHealthReport",
    "SchedulerManager",
    "TenantChecker",
    "Worker",
    "apply_middleware",
    "audit_cancellation",
    "audit_deletion",
    "audit_execution",
    "audit_modification",
    "audit_pause",
    "audit_registration",
    "audit_resume",
    "audit_retry",
    "build_audit_middleware",
    "build_due_job_message",
    "build_health_report",
    "build_job",
    "build_job_from_decorated",
    "build_security_validation_middleware",
    "build_telemetry_middleware",
    "build_tenant_validation_middleware",
    "cluster_has_leader",
    "compute_backoff_delay",
    "compute_next_run",
    "convert_timezone",
    "correlation_id_middleware",
    "create_scheduler_framework",
    "delay",
    "error_handling_middleware",
    "exclusive",
    "exclusive_job_execution",
    "execution_logging_middleware",
    "format_duration",
    "interval",
    "is_due",
    "is_retryable",
    "job_id_from_message",
    "job_lock_key",
    "job_retry_policy",
    "job_summary",
    "localize",
    "metrics_collection_middleware",
    "new_job_id",
    "new_node_id",
    "next_run_time",
    "once",
    "parse_calendar_rule",
    "record_duration",
    "record_execution",
    "record_registered",
    "record_running",
    "retryable",
    "scheduled",
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
    "timeout",
    "to_utc",
    "validate_cron",
    "validate_timezone",
]
