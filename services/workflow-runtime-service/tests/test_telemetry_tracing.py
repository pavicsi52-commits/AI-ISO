"""Tests for :mod:`app.telemetry.tracing`'s span helpers.

Uses a real ``opentelemetry.sdk.trace.TracerProvider`` with an
in-memory exporter, matching this repository's established telemetry
test pattern.
"""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from app.telemetry.tracing import (
    trace_approval,
    trace_checkpoint,
    trace_node_execution,
    trace_queue_processing,
    trace_replay,
    trace_rollback,
    trace_state_transition,
    trace_workflow_runtime,
)


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


def test_trace_workflow_runtime_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_workflow_runtime(tracer, operation="run", instance_id="i-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "workflow_runtime.instance"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "run"
    assert spans[0].attributes.get("instance_id") == "i-1"


def test_trace_node_execution_includes_node_id_attribute() -> None:
    tracer, exporter = _provider()

    with trace_node_execution(tracer, node_id="task"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "workflow_runtime.node_execution"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("node_id") == "task"


def test_trace_queue_processing() -> None:
    tracer, exporter = _provider()

    with trace_queue_processing(tracer, queue_name="workflow_execution_queue"):
        pass

    assert exporter.get_finished_spans()[0].name == "workflow_runtime.queue_processing"


def test_trace_checkpoint() -> None:
    tracer, exporter = _provider()

    with trace_checkpoint(tracer, instance_id="i-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "workflow_runtime.checkpoint"


def test_trace_replay() -> None:
    tracer, exporter = _provider()

    with trace_replay(tracer, instance_id="i-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "workflow_runtime.replay"


def test_trace_rollback() -> None:
    tracer, exporter = _provider()

    with trace_rollback(tracer, instance_id="i-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "workflow_runtime.rollback"


def test_trace_approval_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_approval(tracer, operation="decide"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "workflow_runtime.approval"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "decide"


def test_trace_state_transition_includes_to_status_attribute() -> None:
    tracer, exporter = _provider()

    with trace_state_transition(tracer, to_status="running"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "workflow_runtime.state_transition"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("to_status") == "running"


__all__: list[str] = []
