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
    trace_connector_call,
    trace_execution_engine,
    trace_execution_timing,
    trace_inventory_resolution,
    trace_queue_operation,
    trace_secrets_access,
    trace_workflow_execution,
)


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


def test_trace_execution_engine_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_execution_engine(tracer, operation="dispatch", execution_id="e-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "automation.execution_engine"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "dispatch"
    assert spans[0].attributes.get("execution_id") == "e-1"


def test_trace_connector_call_includes_connector_type_attribute() -> None:
    tracer, exporter = _provider()

    with trace_connector_call(tracer, connector_type="ssh"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "automation.connector_call"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("connector_type") == "ssh"


def test_trace_workflow_execution() -> None:
    tracer, exporter = _provider()

    with trace_workflow_execution(tracer, node_id="n-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "automation.workflow_execution"


def test_trace_inventory_resolution() -> None:
    tracer, exporter = _provider()

    with trace_inventory_resolution(tracer, asset_id="a-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "automation.inventory_resolution"


def test_trace_secrets_access() -> None:
    tracer, exporter = _provider()

    with trace_secrets_access(tracer, secret_id="s-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "automation.secrets_access"


def test_trace_execution_timing_includes_job_id_attribute() -> None:
    tracer, exporter = _provider()

    with trace_execution_timing(tracer, job_id="j-1"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "automation.execution_timing"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("job_id") == "j-1"


def test_trace_queue_operation_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_queue_operation(tracer, operation="enqueue"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "automation.queue_operation"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "enqueue"


__all__: list[str] = []
