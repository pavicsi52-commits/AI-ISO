"""Extra coverage for helpers.py, trace.py, propagation.py, and logs.py edge cases."""

from __future__ import annotations

import pytest
from opentelemetry import propagate
from opentelemetry import trace as trace_api
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared_core.logging.context import get_log_context, reset_log_context
from shared_core.telemetry.exceptions import PropagationError
from shared_core.telemetry.helpers import (
    format_span_id,
    format_trace_id,
    is_valid_span_id,
    is_valid_trace_id,
)
from shared_core.telemetry.logs import correlate_logs_with_span
from shared_core.telemetry.propagation import extract_context, inject_context
from shared_core.telemetry.trace import is_traced

# --- helpers.py ---


def test_format_trace_id_produces_a_32_character_lowercase_hex_string() -> None:
    formatted = format_trace_id(255)

    assert formatted == "000000000000000000000000000000ff"
    assert len(formatted) == 32


def test_format_span_id_produces_a_16_character_lowercase_hex_string() -> None:
    formatted = format_span_id(255)

    assert formatted == "00000000000000ff"
    assert len(formatted) == 16


def test_is_valid_trace_id_accepts_a_wellformed_nonzero_id() -> None:
    assert is_valid_trace_id(format_trace_id(12345)) is True


def test_is_valid_trace_id_rejects_the_all_zero_id() -> None:
    assert is_valid_trace_id(format_trace_id(0)) is False


def test_is_valid_trace_id_rejects_the_wrong_length() -> None:
    assert is_valid_trace_id("abc") is False


def test_is_valid_trace_id_rejects_non_hex_characters() -> None:
    assert is_valid_trace_id("z" * 32) is False


def test_is_valid_span_id_accepts_a_wellformed_nonzero_id() -> None:
    assert is_valid_span_id(format_span_id(999)) is True


def test_is_valid_span_id_rejects_the_all_zero_id() -> None:
    assert is_valid_span_id(format_span_id(0)) is False


def test_is_valid_span_id_rejects_the_wrong_length() -> None:
    assert is_valid_span_id("abc") is False


# --- trace.py ---


def test_is_traced_is_false_with_no_active_span() -> None:
    assert is_traced() is False


def test_is_traced_is_true_inside_an_active_span() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("op"):
        assert is_traced() is True


# --- logs.py ---


def test_correlate_logs_with_span_binds_trace_and_span_ids() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    try:
        with tracer.start_as_current_span("op") as span:
            correlate_logs_with_span(span)
            context = get_log_context()
            span_context = span.get_span_context()
            assert context.trace_id == format_trace_id(span_context.trace_id)
            assert context.span_id == format_span_id(span_context.span_id)
    finally:
        reset_log_context()


def test_correlate_logs_with_span_is_a_noop_for_a_non_recording_span() -> None:
    reset_log_context()

    correlate_logs_with_span(trace_api.INVALID_SPAN)

    assert get_log_context().trace_id is None


# --- propagation.py error handling ---


def test_inject_context_wraps_a_propagator_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(carrier: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(propagate, "inject", _raise)

    with pytest.raises(PropagationError):
        inject_context({})


def test_extract_context_wraps_a_propagator_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(carrier: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(propagate, "extract", _raise)

    with pytest.raises(PropagationError):
        extract_context({})
