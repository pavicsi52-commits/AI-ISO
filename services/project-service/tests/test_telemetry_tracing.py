"""Tests for :mod:`app.telemetry.tracing`'s span helpers.

Uses a real ``opentelemetry.sdk.trace.TracerProvider`` with an
in-memory exporter, matching this repository's established telemetry
test pattern.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span, Tracer

from app.telemetry.tracing import (
    trace_analytics,
    trace_lifecycle_operation,
    trace_membership_change,
    trace_project_crud,
    trace_project_search,
    trace_settings_update,
)

OperationTraceHelper = Callable[..., AbstractContextManager[Span]]
AttributeOnlyTraceHelper = Callable[..., AbstractContextManager[Span]]

_OPERATION_HELPERS: list[tuple[OperationTraceHelper, str]] = [
    (trace_project_crud, "project.crud"),
    (trace_membership_change, "project.membership"),
    (trace_lifecycle_operation, "project.lifecycle"),
]

_ATTRIBUTE_ONLY_HELPERS: list[tuple[AttributeOnlyTraceHelper, str]] = [
    (trace_settings_update, "project.settings_update"),
    (trace_project_search, "project.search"),
    (trace_analytics, "project.analytics"),
]


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


@pytest.mark.parametrize("helper,expected_name", _OPERATION_HELPERS)
def test_operation_trace_helper_includes_operation_attribute(
    helper: OperationTraceHelper, expected_name: str
) -> None:
    tracer, exporter = _provider()

    with helper(tracer, operation="create", project_id="p-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == expected_name
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "create"
    assert spans[0].attributes.get("project_id") == "p-1"


@pytest.mark.parametrize("helper,expected_name", _ATTRIBUTE_ONLY_HELPERS)
def test_attribute_only_trace_helper_produces_a_named_span(
    helper: AttributeOnlyTraceHelper, expected_name: str
) -> None:
    tracer, exporter = _provider()

    with helper(tracer, project_id="p-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == expected_name
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("project_id") == "p-1"


@pytest.mark.parametrize(
    "helper",
    [helper for helper, _ in _OPERATION_HELPERS]
    + [helper for helper, _ in _ATTRIBUTE_ONLY_HELPERS],
)
def test_trace_helper_records_exception_and_reraises(
    helper: OperationTraceHelper | AttributeOnlyTraceHelper,
) -> None:
    tracer, exporter = _provider()
    kwargs = (
        {"operation": "create"}
        if helper in (trace_project_crud, trace_membership_change, trace_lifecycle_operation)
        else {}
    )

    with pytest.raises(ValueError, match="boom"), helper(tracer, **kwargs):
        raise ValueError("boom")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
