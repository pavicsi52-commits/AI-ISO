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
    trace_authorization_evaluation,
    trace_permission_cache,
    trace_permission_lookup,
    trace_policy_evaluation,
    trace_role_assignment,
)

SimpleTraceHelper = Callable[..., AbstractContextManager[Span]]
OperationTraceHelper = Callable[..., AbstractContextManager[Span]]

_SIMPLE_HELPERS: list[tuple[SimpleTraceHelper, str]] = [
    (trace_authorization_evaluation, "rbac.authorization.evaluate"),
    (trace_policy_evaluation, "rbac.policy.evaluate"),
    (trace_permission_lookup, "rbac.permission.lookup"),
]

_OPERATION_HELPERS: list[tuple[OperationTraceHelper, str]] = [
    (trace_role_assignment, "rbac.role.assignment"),
    (trace_permission_cache, "rbac.permission_cache"),
]


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


@pytest.mark.parametrize("helper,expected_name", _SIMPLE_HELPERS)
def test_simple_trace_helper_produces_a_named_span(
    helper: SimpleTraceHelper, expected_name: str
) -> None:
    tracer, exporter = _provider()

    with helper(tracer, user_id="u-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == expected_name
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("user_id") == "u-1"


@pytest.mark.parametrize("helper,expected_name", _OPERATION_HELPERS)
def test_operation_trace_helper_includes_operation_attribute(
    helper: OperationTraceHelper, expected_name: str
) -> None:
    tracer, exporter = _provider()

    with helper(tracer, operation="assign"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == expected_name
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "assign"


@pytest.mark.parametrize("helper,_expected_name", _SIMPLE_HELPERS)
def test_simple_trace_helper_records_exception_and_reraises(
    helper: SimpleTraceHelper, _expected_name: str
) -> None:
    tracer, exporter = _provider()

    with pytest.raises(ValueError, match="boom"), helper(tracer):
        raise ValueError("boom")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
