"""Tests for :mod:`app.telemetry.tracing`'s span helpers.

Uses a real ``opentelemetry.sdk.trace.TracerProvider`` with an
in-memory exporter, matching this repository's established telemetry
test pattern (see ``services/inventory-service/tests
/test_telemetry_tracing.py``).
"""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from app.telemetry.tracing import (
    trace_classification,
    trace_discovery_job,
    trace_inventory_update,
    trace_performance_metrics,
    trace_protocol_execution,
    trace_synchronization,
    trace_topology_update,
)


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


def test_trace_discovery_job_includes_job_id_attribute() -> None:
    tracer, exporter = _provider()

    with trace_discovery_job(tracer, job_id="job-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "discovery.job"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("job_id") == "job-1"


def test_trace_protocol_execution_includes_protocol_attribute() -> None:
    tracer, exporter = _provider()

    with trace_protocol_execution(tracer, protocol="ssh"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "discovery.protocol_execution"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("protocol") == "ssh"


def test_trace_classification() -> None:
    tracer, exporter = _provider()

    with trace_classification(tracer, asset_id="a-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "discovery.classification"


def test_trace_synchronization() -> None:
    tracer, exporter = _provider()

    with trace_synchronization(tracer):
        pass

    assert exporter.get_finished_spans()[0].name == "discovery.synchronization"


def test_trace_topology_update() -> None:
    tracer, exporter = _provider()

    with trace_topology_update(tracer, job_id="job-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "discovery.topology_update"


def test_trace_inventory_update() -> None:
    tracer, exporter = _provider()

    with trace_inventory_update(tracer, asset_id="a-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "discovery.inventory_update"


def test_trace_performance_metrics() -> None:
    tracer, exporter = _provider()

    with trace_performance_metrics(tracer, job_id="job-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "discovery.performance_metrics"


__all__: list[str] = []
