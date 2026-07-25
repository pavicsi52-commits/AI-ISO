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
    trace_asset_operation,
    trace_compliance,
    trace_cost_analysis,
    trace_dependency_query,
    trace_health_aggregation,
    trace_maintenance,
    trace_risk_analysis,
)


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


def test_trace_asset_operation_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_asset_operation(tracer, operation="create", managed_asset_id="a-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "asset_management.asset_operation"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "create"
    assert spans[0].attributes.get("managed_asset_id") == "a-1"


def test_trace_maintenance() -> None:
    tracer, exporter = _provider()

    with trace_maintenance(tracer, managed_asset_id="a-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "asset_management.maintenance"


def test_trace_compliance() -> None:
    tracer, exporter = _provider()

    with trace_compliance(tracer, managed_asset_id="a-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "asset_management.compliance"


def test_trace_risk_analysis() -> None:
    tracer, exporter = _provider()

    with trace_risk_analysis(tracer, managed_asset_id="a-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "asset_management.risk_analysis"


def test_trace_cost_analysis() -> None:
    tracer, exporter = _provider()

    with trace_cost_analysis(tracer, managed_asset_id="a-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "asset_management.cost_analysis"


def test_trace_dependency_query_includes_query_kind() -> None:
    tracer, exporter = _provider()

    with trace_dependency_query(tracer, query_kind="impact_analysis"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "asset_management.dependency_query"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("query_kind") == "impact_analysis"


def test_trace_health_aggregation() -> None:
    tracer, exporter = _provider()

    with trace_health_aggregation(tracer, managed_asset_id="a-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "asset_management.health_aggregation"


__all__: list[str] = []
