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
    trace_execution_timing,
    trace_remediation_generation,
    trace_result_aggregation,
    trace_rule_execution,
    trace_scoring,
    trace_target_collection,
    trace_validation_engine,
)


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


def test_trace_validation_engine_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_validation_engine(tracer, operation="run"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "validation.engine"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "run"


def test_trace_rule_execution_includes_check_id_attribute() -> None:
    tracer, exporter = _provider()

    with trace_rule_execution(tracer, check_id="check-1"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "validation.rule_execution"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("check_id") == "check-1"


def test_trace_target_collection_includes_collector_key_attribute() -> None:
    tracer, exporter = _provider()

    with trace_target_collection(tracer, collector_key="connectivity"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "validation.target_collection"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("collector_key") == "connectivity"


def test_trace_result_aggregation() -> None:
    tracer, exporter = _provider()

    with trace_result_aggregation(tracer):
        pass

    assert exporter.get_finished_spans()[0].name == "validation.result_aggregation"


def test_trace_scoring() -> None:
    tracer, exporter = _provider()

    with trace_scoring(tracer):
        pass

    assert exporter.get_finished_spans()[0].name == "validation.scoring"


def test_trace_remediation_generation() -> None:
    tracer, exporter = _provider()

    with trace_remediation_generation(tracer):
        pass

    assert exporter.get_finished_spans()[0].name == "validation.remediation_generation"


def test_trace_execution_timing_includes_execution_id_attribute() -> None:
    tracer, exporter = _provider()

    with trace_execution_timing(tracer, execution_id="exec-1"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "validation.execution_timing"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("execution_id") == "exec-1"


__all__: list[str] = []
