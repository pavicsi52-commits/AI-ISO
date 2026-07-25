"""Tests for :mod:`app.telemetry.tracing`'s span helpers.

Uses a real ``opentelemetry.sdk.trace.TracerProvider`` with an
in-memory exporter, matching this repository's established telemetry
test pattern (``services/authentication-service/tests
/test_telemetry_tracing.py``).
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
    trace_avatar_upload,
    trace_export,
    trace_import,
    trace_invitation,
    trace_profile_operation,
    trace_search,
)

TraceHelper = Callable[..., AbstractContextManager[Span]]

_SIMPLE_HELPERS: list[tuple[TraceHelper, str]] = [
    (trace_search, "user.search"),
    (trace_import, "user.import"),
    (trace_export, "user.export"),
    (trace_avatar_upload, "user.avatar.upload"),
]


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


@pytest.mark.parametrize("helper,expected_name", _SIMPLE_HELPERS)
def test_trace_helper_produces_a_named_span(helper: TraceHelper, expected_name: str) -> None:
    tracer, exporter = _provider()

    with helper(tracer, user_id="u-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == expected_name
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("user_id") == "u-1"


def test_trace_profile_operation_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_profile_operation(tracer, operation="update", user_id="u-1"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "user.profile"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "update"


def test_trace_invitation_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_invitation(tracer, operation="accept"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "user.invitation"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "accept"


@pytest.mark.parametrize("helper,_expected_name", _SIMPLE_HELPERS)
def test_trace_helper_records_exception_and_reraises(
    helper: TraceHelper, _expected_name: str
) -> None:
    tracer, exporter = _provider()

    with pytest.raises(ValueError, match="boom"), helper(tracer):
        raise ValueError("boom")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
