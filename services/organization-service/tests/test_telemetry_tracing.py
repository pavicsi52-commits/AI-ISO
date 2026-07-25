"""Tests for :mod:`app.telemetry.tracing`'s span helpers.

Uses a real ``opentelemetry.sdk.trace.TracerProvider`` with an
in-memory exporter, matching this repository's established telemetry
test pattern (see ``services/rbac-service/tests/test_telemetry_tracing.py``).
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
    trace_department_operation,
    trace_license_validation,
    trace_organization_crud,
    trace_quota_check,
)

OperationTraceHelper = Callable[..., AbstractContextManager[Span]]
AttributeOnlyTraceHelper = Callable[..., AbstractContextManager[Span]]

_OPERATION_HELPERS: list[tuple[OperationTraceHelper, str]] = [
    (trace_organization_crud, "organization.crud"),
    (trace_department_operation, "organization.department"),
]

_ATTRIBUTE_ONLY_HELPERS: list[tuple[AttributeOnlyTraceHelper, str]] = [
    (trace_quota_check, "organization.quota_check"),
    (trace_license_validation, "organization.license_validation"),
    (trace_analytics, "organization.analytics"),
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

    with helper(tracer, operation="create", organization_id="org-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == expected_name
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "create"
    assert spans[0].attributes.get("organization_id") == "org-1"


@pytest.mark.parametrize("helper,expected_name", _ATTRIBUTE_ONLY_HELPERS)
def test_attribute_only_trace_helper_produces_a_named_span(
    helper: AttributeOnlyTraceHelper, expected_name: str
) -> None:
    tracer, exporter = _provider()

    with helper(tracer, organization_id="org-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == expected_name
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("organization_id") == "org-1"


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
        if helper in (trace_organization_crud, trace_department_operation)
        else {}
    )

    with pytest.raises(ValueError, match="boom"), helper(tracer, **kwargs):
        raise ValueError("boom")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
