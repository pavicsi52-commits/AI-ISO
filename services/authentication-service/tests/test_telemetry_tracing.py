"""Tests for :mod:`app.telemetry.tracing`'s span helpers.

Uses a real ``opentelemetry.sdk.trace.TracerProvider`` with an
in-memory exporter, matching the rest of this repository's telemetry
test suites (:mod:`shared_core`'s own plugin/workflow integration
tests) rather than mocking the tracer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span, Tracer

from app.telemetry.tracing import (
    trace_login,
    trace_logout,
    trace_mfa,
    trace_password_reset,
    trace_session_creation,
    trace_token_validation,
)

TraceHelper = Callable[..., Iterator[Span]]

_HELPERS: list[tuple[TraceHelper, str]] = [
    (trace_login, "auth.login"),
    (trace_logout, "auth.logout"),
    (trace_session_creation, "auth.session.create"),
    (trace_token_validation, "auth.token.validate"),
    (trace_password_reset, "auth.password.reset"),
    (trace_mfa, "auth.mfa"),
]


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


@pytest.mark.parametrize("helper,expected_name", _HELPERS)
def test_trace_helper_produces_a_named_span(helper: TraceHelper, expected_name: str) -> None:
    tracer, exporter = _provider()

    with helper(tracer, user_id="u-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == expected_name
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("user_id") == "u-1"


@pytest.mark.parametrize("helper,_expected_name", _HELPERS)
def test_trace_helper_records_exception_and_reraises(
    helper: TraceHelper, _expected_name: str
) -> None:
    tracer, exporter = _provider()

    with pytest.raises(ValueError, match="boom"), helper(tracer):
        raise ValueError("boom")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
