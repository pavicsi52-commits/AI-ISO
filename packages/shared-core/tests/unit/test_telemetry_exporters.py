"""Tests for exporters.py."""

from __future__ import annotations

import json

import pytest
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExportResult,
)
from shared_core.telemetry.exceptions import ExporterConfigurationError
from shared_core.telemetry.exporters import (
    JsonFileSpanExporter,
    console_exporter,
    create_exporter,
    json_file_exporter,
    otlp_exporter,
)


def test_console_exporter_returns_a_console_span_exporter() -> None:
    assert isinstance(console_exporter(), ConsoleSpanExporter)


def test_json_file_exporter_writes_one_json_line_per_finished_span(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "spans.jsonl"
    exporter = json_file_exporter(path)
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("do-work") as span:
        span.set_attribute("widget_id", "123")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["name"] == "do-work"
    assert record["attributes"]["widget_id"] == "123"
    assert len(record["trace_id"]) == 32
    assert len(record["span_id"]) == 16


def test_json_file_exporter_appends_across_multiple_export_calls(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "spans.jsonl"
    exporter = json_file_exporter(path)
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("first"):
        pass
    with tracer.start_as_current_span("second"):
        pass

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_json_file_exporter_returns_failure_on_an_unwritable_path() -> None:
    exporter = JsonFileSpanExporter("/nonexistent-dir-xyz/spans.jsonl")

    result = exporter.export([])

    assert result == SpanExportResult.FAILURE


def test_otlp_exporter_requires_a_non_empty_endpoint() -> None:
    with pytest.raises(ExporterConfigurationError):
        otlp_exporter(endpoint="")


def test_otlp_exporter_builds_a_real_otlp_span_exporter() -> None:
    exporter = otlp_exporter(endpoint="http://localhost:4318/v1/traces")

    assert isinstance(exporter, OTLPSpanExporter)


def test_create_exporter_dispatches_by_name() -> None:
    assert isinstance(create_exporter("console"), ConsoleSpanExporter)
    assert isinstance(create_exporter("json", json_path="x.jsonl"), JsonFileSpanExporter)


def test_create_exporter_rejects_an_unknown_type() -> None:
    with pytest.raises(ExporterConfigurationError):
        create_exporter("jaeger")
