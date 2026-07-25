"""Tests for events.py, queue.py, scheduler.py, telemetry.py, metrics.py,
audit.py, and health.py.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from aio_pika.abc import AbstractRobustConnection
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared_core.enums.health_status import HealthStatus
from shared_core.queue.manager import QueueManager
from shared_core.scheduler.schedule import ScheduleType
from shared_core.workflow import audit
from shared_core.workflow import metrics as workflow_metrics
from shared_core.workflow.events import (
    TaskCompletedEvent,
    WorkflowEvent,
    WorkflowStartedEvent,
    build_workflow_event,
)
from shared_core.workflow.health import build_health_report
from shared_core.workflow.queue import WorkflowTaskQueue
from shared_core.workflow.scheduler import (
    build_scheduled_workflow_job,
    cron_schedule,
    delayed_schedule,
    recurring_schedule,
)
from shared_core.workflow.telemetry import (
    trace_ai_request,
    trace_connector_execution,
    trace_workflow_execution,
    trace_workflow_step,
)


def _provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def _queue_name() -> str:
    return f"workflow.tasks.test.{uuid.uuid4().hex}"


# --- events.py ---


def test_workflow_started_event_has_the_expected_name_and_type() -> None:
    event = build_workflow_event(
        WorkflowStartedEvent, source_service="workflow-svc", execution_id="e1", workflow_id="wf-1"
    )

    assert event.event_name == "workflow.started"
    assert event.payload == {"execution_id": "e1", "workflow_id": "wf-1"}


def test_task_completed_event_includes_node_id_and_extra_payload() -> None:
    event = build_workflow_event(
        TaskCompletedEvent,
        source_service="workflow-svc",
        execution_id="e1",
        workflow_id="wf-1",
        node_id="n1",
        output="ok",
    )

    assert event.payload["node_id"] == "n1"
    assert event.payload["output"] == "ok"


def test_workflow_event_is_a_base_event_subclass() -> None:
    event = build_workflow_event(
        WorkflowStartedEvent, source_service="workflow-svc", execution_id="e1", workflow_id="wf-1"
    )

    assert isinstance(event, WorkflowEvent)


# --- queue.py, against the real RabbitMQ started by docker-compose.yml ---


async def test_workflow_task_queue_enqueue_and_consume_round_trip(
    queue_manager: QueueManager,
) -> None:
    task_queue = WorkflowTaskQueue(queue_manager, queue_name=_queue_name())
    await task_queue.declare()
    received: asyncio.Queue[tuple[str, str, dict[str, object]]] = asyncio.Queue()

    async def handler(execution_id: str, node_id: str, payload: dict[str, object]) -> None:
        await received.put((execution_id, node_id, payload))

    await task_queue.consume(handler)
    await task_queue.enqueue("e1", "n1", {"key": "value"})

    execution_id, node_id, payload = await asyncio.wait_for(received.get(), timeout=5)
    assert execution_id == "e1"
    assert node_id == "n1"
    assert payload == {"key": "value"}


# --- scheduler.py ---


async def test_build_scheduled_workflow_job_triggers_the_workflow() -> None:
    triggered: list[str] = []

    async def trigger(workflow_id: str) -> None:
        triggered.append(workflow_id)

    job = build_scheduled_workflow_job(
        job_name="run-wf-1",
        workflow_id="wf-1",
        schedule=cron_schedule("0 2 * * *"),
        trigger=trigger,
    )

    await job.fn(job)

    assert triggered == ["wf-1"]


def test_cron_schedule_builds_a_cron_expression_schedule() -> None:
    schedule = cron_schedule("0 2 * * *")

    assert schedule.schedule_type == ScheduleType.CRON_EXPRESSION
    assert schedule.cron_expression == "0 2 * * *"


def test_recurring_schedule_builds_a_fixed_rate_schedule() -> None:
    schedule = recurring_schedule(30)

    assert schedule.schedule_type == ScheduleType.FIXED_RATE


def test_delayed_schedule_builds_a_fixed_delay_schedule() -> None:
    schedule = delayed_schedule(15)

    assert schedule.schedule_type == ScheduleType.FIXED_DELAY


# --- telemetry.py ---


def test_trace_workflow_execution_creates_a_span() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with trace_workflow_execution(tracer, "wf-1"):
        pass

    assert len(exporter.get_finished_spans()) == 1


def test_trace_workflow_step_creates_a_span() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with trace_workflow_step(tracer, "wf-1", "step-1"):
        pass

    assert len(exporter.get_finished_spans()) == 1


def test_trace_connector_execution_is_reexported() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with trace_connector_execution(tracer, "ssh"):
        pass

    assert len(exporter.get_finished_spans()) == 1


def test_trace_ai_request_is_reexported() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with trace_ai_request(tracer, "openai"):
        pass

    assert len(exporter.get_finished_spans()) == 1


# --- metrics.py ---


def test_record_execution_started_increments() -> None:
    before = workflow_metrics.workflow_executions_total.labels(workflow_id="wf-1")._value.get()

    workflow_metrics.record_execution_started("wf-1")

    after = workflow_metrics.workflow_executions_total.labels(workflow_id="wf-1")._value.get()
    assert after == before + 1


def test_record_success_increments_and_observes() -> None:
    before = workflow_metrics.workflow_success_total.labels(workflow_id="wf-1")._value.get()

    workflow_metrics.record_success("wf-1", duration_seconds=1.5)

    after = workflow_metrics.workflow_success_total.labels(workflow_id="wf-1")._value.get()
    assert after == before + 1


def test_record_failure_increments_and_observes() -> None:
    before = workflow_metrics.workflow_failure_total.labels(workflow_id="wf-1")._value.get()

    workflow_metrics.record_failure("wf-1", duration_seconds=1.5)

    after = workflow_metrics.workflow_failure_total.labels(workflow_id="wf-1")._value.get()
    assert after == before + 1


def test_record_retry_and_rollback_increment() -> None:
    before_retry = workflow_metrics.workflow_retries_total.labels(workflow_id="wf-1")._value.get()
    before_rollback = workflow_metrics.workflow_rollbacks_total.labels(
        workflow_id="wf-1"
    )._value.get()

    workflow_metrics.record_retry("wf-1")
    workflow_metrics.record_rollback("wf-1")

    assert (
        workflow_metrics.workflow_retries_total.labels(workflow_id="wf-1")._value.get()
        == before_retry + 1
    )
    assert (
        workflow_metrics.workflow_rollbacks_total.labels(workflow_id="wf-1")._value.get()
        == before_rollback + 1
    )


def test_record_queue_time_and_approval_time_observe() -> None:
    workflow_metrics.record_queue_time("wf-1", 0.5)
    workflow_metrics.record_approval_time("wf-1", 10.0)


def test_measure_task_records_duration_regardless_of_outcome() -> None:
    with workflow_metrics.measure_task("wf-1", "task"):
        pass

    with pytest.raises(RuntimeError), workflow_metrics.measure_task("wf-1", "task"):
        raise RuntimeError("boom")


# --- audit.py ---


def test_audit_functions_do_not_raise() -> None:
    audit.audit_workflow_created("wf-1")
    audit.audit_workflow_updated("wf-1")
    audit.audit_workflow_deleted("wf-1")
    audit.audit_execution_started("e1", "wf-1")
    audit.audit_execution_completed("e1", "wf-1")
    audit.audit_execution_failed("e1", "wf-1", error="boom")
    audit.audit_rollback_executed("e1", "wf-1", node_ids=["a", "b"])
    audit.audit_approval_decision("r1", "n1", decision="approved", approver="alice")
    audit.audit_privileged_access("e1", "wf-1", operation="cancel", actor_id="alice")


def test_audit_all_exports_every_function() -> None:
    assert set(audit.__all__) == {
        "audit_approval_decision",
        "audit_execution_completed",
        "audit_execution_failed",
        "audit_execution_started",
        "audit_privileged_access",
        "audit_rollback_executed",
        "audit_workflow_created",
        "audit_workflow_deleted",
        "audit_workflow_updated",
    }


# --- health.py, against the real RabbitMQ started by docker-compose.yml ---


async def test_build_health_report_reflects_queue_status(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    report = await build_health_report(
        rabbitmq_connection, active_execution_count=2, registered_workflow_count=5
    )

    assert report.queue_status == HealthStatus.HEALTHY
    assert report.status == HealthStatus.HEALTHY
    assert report.active_execution_count == 2
    assert report.registered_workflow_count == 5
