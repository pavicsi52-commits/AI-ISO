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
    trace_aggregation,
    trace_collectors,
    trace_dependency_resolution,
    trace_health_calculation,
    trace_metric_processing,
    trace_rule_evaluation,
    trace_time_series_storage,
)


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


def test_trace_collectors_includes_collector_key_attribute() -> None:
    tracer, exporter = _provider()

    with trace_collectors(tracer, collector_key="connectivity"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "monitoring.collectors"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("collector_key") == "connectivity"


def test_trace_metric_processing() -> None:
    tracer, exporter = _provider()

    with trace_metric_processing(tracer):
        pass

    assert exporter.get_finished_spans()[0].name == "monitoring.metric_processing"


def test_trace_aggregation() -> None:
    tracer, exporter = _provider()

    with trace_aggregation(tracer):
        pass

    assert exporter.get_finished_spans()[0].name == "monitoring.aggregation"


def test_trace_rule_evaluation_includes_rule_id_attribute() -> None:
    tracer, exporter = _provider()

    with trace_rule_evaluation(tracer, rule_id="rule-1"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "monitoring.rule_evaluation"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("rule_id") == "rule-1"


def test_trace_time_series_storage() -> None:
    tracer, exporter = _provider()

    with trace_time_series_storage(tracer):
        pass

    assert exporter.get_finished_spans()[0].name == "monitoring.time_series_storage"


def test_trace_dependency_resolution_includes_target_id_attribute() -> None:
    tracer, exporter = _provider()

    with trace_dependency_resolution(tracer, target_id="target-1"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "monitoring.dependency_resolution"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("target_id") == "target-1"


def test_trace_health_calculation_includes_target_id_attribute() -> None:
    tracer, exporter = _provider()

    with trace_health_calculation(tracer, target_id="target-1"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "monitoring.health_calculation"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("target_id") == "target-1"


__all__: list[str] = []
