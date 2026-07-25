"""Tests for middleware.py."""

from __future__ import annotations

from datetime import UTC, datetime

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared_core.logging.context import get_log_context
from shared_core.scheduler.executor import ExecutionResult
from shared_core.scheduler.job import Job, JobType, build_job
from shared_core.scheduler.middleware import (
    ExecuteHandler,
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
from shared_core.scheduler.schedule import Schedule, ScheduleType


async def _noop(_job: Job) -> None:
    pass


def _job(**overrides: object) -> Job:
    return build_job(
        job_name="test-job",
        job_type=JobType.BACKGROUND,
        fn=_noop,
        schedule=Schedule(schedule_type=ScheduleType.IMMEDIATE),
        **overrides,
    )


def _success_result(job: Job, *, attempts: int = 1) -> ExecutionResult:
    now = datetime.now(UTC)
    return ExecutionResult(
        job_id=job.job_id, succeeded=True, attempts=attempts, started_at=now, finished_at=now
    )


def _provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


async def test_apply_middleware_runs_in_outermost_first_order() -> None:
    calls: list[str] = []

    async def outer(job: Job, next_handler: ExecuteHandler) -> ExecutionResult:
        calls.append("outer-before")
        result = await next_handler(job)
        calls.append("outer-after")
        return result

    async def inner(job: Job, next_handler: ExecuteHandler) -> ExecutionResult:
        calls.append("inner-before")
        result = await next_handler(job)
        calls.append("inner-after")
        return result

    async def handler(job: Job) -> ExecutionResult:
        calls.append("handler")
        return _success_result(job)

    wrapped = apply_middleware(handler, [outer, inner])
    await wrapped(_job())

    assert calls == ["outer-before", "inner-before", "handler", "inner-after", "outer-after"]


async def test_execution_logging_middleware_calls_through() -> None:
    job = _job()

    async def handler(job: Job) -> ExecutionResult:
        return _success_result(job)

    result = await execution_logging_middleware(job, handler)

    assert result.succeeded is True


async def test_correlation_id_middleware_binds_and_resets_context() -> None:
    job = _job(organization_id="org-1", project_id="proj-1")
    seen_correlation_id = None

    async def handler(job: Job) -> ExecutionResult:
        nonlocal seen_correlation_id
        seen_correlation_id = get_log_context().correlation_id
        return _success_result(job)

    await correlation_id_middleware(job, handler)

    assert seen_correlation_id == job.job_id
    assert get_log_context().correlation_id is None


async def test_error_handling_middleware_converts_an_exception_to_a_result() -> None:
    job = _job()

    async def handler(_job: Job) -> ExecutionResult:
        raise RuntimeError("boom")

    result = await error_handling_middleware(job, handler)

    assert result.succeeded is False
    assert result.attempts == 0
    assert "boom" in (result.error or "")


async def test_error_handling_middleware_passes_through_success() -> None:
    job = _job()

    async def handler(job: Job) -> ExecutionResult:
        return _success_result(job)

    result = await error_handling_middleware(job, handler)

    assert result.succeeded is True


async def test_metrics_collection_middleware_calls_through() -> None:
    job = _job()

    async def handler(job: Job) -> ExecutionResult:
        return _success_result(job, attempts=2)

    result = await metrics_collection_middleware(job, handler)

    assert result.attempts == 2


async def test_build_telemetry_middleware_creates_a_span() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)
    middleware = build_telemetry_middleware(tracer)
    job = _job()

    async def handler(job: Job) -> ExecutionResult:
        return _success_result(job)

    result = await middleware(job, handler)

    assert result.succeeded is True
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == f"scheduler.{job.job_name}"


async def test_build_audit_middleware_calls_through() -> None:
    middleware = build_audit_middleware("node-a")
    job = _job()

    async def handler(job: Job) -> ExecutionResult:
        return _success_result(job)

    result = await middleware(job, handler)

    assert result.succeeded is True


async def test_build_security_validation_middleware_denies_when_checker_rejects() -> None:
    async def checker(_job: Job) -> bool:
        return False

    middleware = build_security_validation_middleware(checker)
    job = _job()
    handler_called = False

    async def handler(job: Job) -> ExecutionResult:
        nonlocal handler_called
        handler_called = True
        return _success_result(job)

    result = await middleware(job, handler)

    assert result.succeeded is False
    assert result.attempts == 0
    assert handler_called is False


async def test_build_security_validation_middleware_allows_when_checker_approves() -> None:
    async def checker(_job: Job) -> bool:
        return True

    middleware = build_security_validation_middleware(checker)
    job = _job()

    async def handler(job: Job) -> ExecutionResult:
        return _success_result(job)

    result = await middleware(job, handler)

    assert result.succeeded is True


async def test_build_tenant_validation_middleware_denies_when_checker_rejects() -> None:
    async def checker(_job: Job) -> bool:
        return False

    middleware = build_tenant_validation_middleware(checker)
    job = _job()

    async def handler(job: Job) -> ExecutionResult:
        return _success_result(job)

    result = await middleware(job, handler)

    assert result.succeeded is False
    assert "Tenant" in (result.error or "")


async def test_build_tenant_validation_middleware_allows_when_checker_approves() -> None:
    async def checker(_job: Job) -> bool:
        return True

    middleware = build_tenant_validation_middleware(checker)
    job = _job()

    async def handler(job: Job) -> ExecutionResult:
        return _success_result(job)

    result = await middleware(job, handler)

    assert result.succeeded is True
