"""Execution middleware.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "MIDDLEWARE":
Execution Logging, Telemetry Integration, Audit Integration, Security
Validation, Tenant Validation, Correlation IDs, Error Handling, Metrics
Collection. A middleware chain wrapping
:meth:`shared_core.scheduler.executor.JobExecutor.execute` -- the same
``apply_middleware``/``_bind`` chain shape as
:mod:`shared_core.notifications.middleware`.

"Security Validation"/"Tenant Validation" are pluggable hooks this
framework calls but does not itself police (docs/026 "DO NOT
IMPLEMENT": Authentication) -- the embedding service supplies the
actual permission/tenant policy as a callback.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from opentelemetry.trace import Tracer

from shared_core.logging.context import bind_log_context, reset_log_context
from shared_core.logging.logger import get_logger
from shared_core.scheduler import metrics as scheduler_metrics
from shared_core.scheduler.audit import audit_execution
from shared_core.scheduler.executor import ExecutionResult
from shared_core.scheduler.job import Job
from shared_core.telemetry.scheduler import trace_scheduler_job

logger = get_logger("shared_core.scheduler")

ExecuteHandler = Callable[[Job], Awaitable[ExecutionResult]]
ExecuteMiddleware = Callable[[Job, ExecuteHandler], Awaitable[ExecutionResult]]
PermissionChecker = Callable[[Job], Awaitable[bool]]
TenantChecker = Callable[[Job], Awaitable[bool]]


def apply_middleware(
    handler: ExecuteHandler, middlewares: list[ExecuteMiddleware]
) -> ExecuteHandler:
    """Wrap *handler* in every middleware, outermost first ("the chain")."""
    for middleware in reversed(middlewares):
        handler = _bind(middleware, handler)
    return handler


def _bind(middleware: ExecuteMiddleware, next_handler: ExecuteHandler) -> ExecuteHandler:
    async def wrapped(job: Job) -> ExecutionResult:
        return await middleware(job, next_handler)

    return wrapped


def _denied_result(job: Job, reason: str) -> ExecutionResult:
    now = datetime.now(UTC)
    return ExecutionResult(
        job_id=job.job_id,
        succeeded=False,
        attempts=0,
        started_at=now,
        finished_at=now,
        error=reason,
    )


async def execution_logging_middleware(job: Job, next_handler: ExecuteHandler) -> ExecutionResult:
    """Log the start and outcome of every job execution ("Execution Logging")."""
    logger.info(
        "Starting job execution.",
        extra={"extra_fields": {"job_id": job.job_id, "job_name": job.job_name}},
    )
    result = await next_handler(job)
    logger.info(
        "Finished job execution.",
        extra={
            "extra_fields": {
                "job_id": job.job_id,
                "succeeded": result.succeeded,
                "attempts": result.attempts,
            }
        },
    )
    return result


async def correlation_id_middleware(job: Job, next_handler: ExecuteHandler) -> ExecutionResult:
    """Bind the job's id/tenant fields to the log context for the run ("Correlation IDs")."""
    bind_log_context(
        correlation_id=job.job_id,
        organization_id=job.organization_id,
        project_id=job.project_id,
    )
    try:
        return await next_handler(job)
    finally:
        reset_log_context()


async def error_handling_middleware(job: Job, next_handler: ExecuteHandler) -> ExecutionResult:
    """Convert any exception escaping the chain into a failed result ("Error Handling").

    :class:`~shared_core.scheduler.executor.JobExecutor` already turns a
    job's own failures into a non-raising :class:`ExecutionResult`; this
    is defense-in-depth against a bug in an *outer* middleware itself
    raising, so one broken middleware can't take down the whole worker's
    message loop.
    """
    try:
        return await next_handler(job)
    except Exception as exc:
        logger.exception("Unhandled error in the execution middleware chain.")
        return _denied_result(job, f"Middleware chain error: {exc}")


async def metrics_collection_middleware(job: Job, next_handler: ExecuteHandler) -> ExecutionResult:
    """Record every execution's outcome to Prometheus ("Metrics Collection")."""
    result = await next_handler(job)
    scheduler_metrics.record_execution(
        succeeded=result.succeeded,
        duration_seconds=result.duration_seconds,
        retries=max(result.attempts - 1, 0),
    )
    return result


def build_telemetry_middleware(tracer: Tracer) -> ExecuteMiddleware:
    """Build a middleware wrapping every execution in a root trace ("Telemetry Integration")."""

    async def middleware(job: Job, next_handler: ExecuteHandler) -> ExecutionResult:
        with trace_scheduler_job(
            tracer, job.job_name, job_id=job.job_id, job_type=job.job_type.value
        ):
            return await next_handler(job)

    return middleware


def build_audit_middleware(worker_node_id: str) -> ExecuteMiddleware:
    """Build a middleware that audit-logs every execution's outcome ("Audit Integration")."""

    async def middleware(job: Job, next_handler: ExecuteHandler) -> ExecutionResult:
        result = await next_handler(job)
        audit_execution(
            job.job_id,
            worker_node_id=worker_node_id,
            outcome="success" if result.succeeded else "failure",
            attempts=result.attempts,
            error=result.error,
        )
        return result

    return middleware


def build_security_validation_middleware(checker: PermissionChecker) -> ExecuteMiddleware:
    """Build a middleware denying execution unless *checker* approves ("Security Validation")."""

    async def middleware(job: Job, next_handler: ExecuteHandler) -> ExecutionResult:
        if not await checker(job):
            return _denied_result(job, "Permission denied.")
        return await next_handler(job)

    return middleware


def build_tenant_validation_middleware(checker: TenantChecker) -> ExecuteMiddleware:
    """Build a middleware denying execution unless *checker* approves the job's tenant."""

    async def middleware(job: Job, next_handler: ExecuteHandler) -> ExecutionResult:
        if not await checker(job):
            return _denied_result(job, "Tenant validation failed.")
        return await next_handler(job)

    return middleware


__all__ = [
    "ExecuteHandler",
    "ExecuteMiddleware",
    "PermissionChecker",
    "TenantChecker",
    "apply_middleware",
    "build_audit_middleware",
    "build_security_validation_middleware",
    "build_telemetry_middleware",
    "build_tenant_validation_middleware",
    "correlation_id_middleware",
    "error_handling_middleware",
    "execution_logging_middleware",
    "metrics_collection_middleware",
]
