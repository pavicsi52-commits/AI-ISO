"""Tests for :mod:`app.telemetry.tracing`'s span helpers.

Uses a real ``opentelemetry.sdk.trace.TracerProvider`` with an
in-memory exporter, matching this repository's established telemetry
test pattern (see ``services/project-service/tests/test_telemetry_tracing.py``).
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from app.telemetry.tracing import (
    trace_certificate_validation,
    trace_decryption,
    trace_encryption,
    trace_lease_operation,
    trace_provider_call,
    trace_rotation,
    trace_secret_access,
)


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


def test_trace_secret_access_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_secret_access(tracer, operation="read", actor_id="u-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "secret.access"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "read"
    assert spans[0].attributes.get("actor_id") == "u-1"


def test_trace_secret_access_masks_attributes_naming_a_secret() -> None:
    """Per ``shared_core.telemetry.span``'s own "never capture secrets"
    masking -- any attribute key containing a sensitive keyword (here,
    "secret") is redacted automatically, defense-in-depth for a service
    whose entire purpose is handling secrets.
    """
    tracer, exporter = _provider()

    with trace_secret_access(tracer, operation="read", secret_id="s-1"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("secret_id") == "***MASKED***"


def test_trace_encryption_produces_named_span() -> None:
    tracer, exporter = _provider()

    with trace_encryption(tracer, secret_id="s-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "secret.encrypt"


def test_trace_decryption_produces_named_span() -> None:
    tracer, exporter = _provider()

    with trace_decryption(tracer, secret_id="s-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "secret.decrypt"


def test_trace_rotation_includes_trigger_attribute() -> None:
    tracer, exporter = _provider()

    with trace_rotation(tracer, trigger="manual", secret_id="s-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "secret.rotation"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("trigger") == "manual"


def test_trace_lease_operation_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_lease_operation(tracer, operation="issue", lease_id="l-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "secret.lease"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "issue"


def test_trace_certificate_validation_produces_named_span() -> None:
    tracer, exporter = _provider()

    with trace_certificate_validation(tracer, certificate_id="c-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "secret.certificate_validation"


def test_trace_provider_call_includes_provider_type_attribute() -> None:
    tracer, exporter = _provider()

    with trace_provider_call(tracer, provider_type="hashicorp_vault"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "secret.provider_call"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("provider_type") == "hashicorp_vault"


def test_trace_helper_records_exception_and_reraises() -> None:
    tracer, exporter = _provider()

    with pytest.raises(ValueError, match="boom"), trace_encryption(tracer):
        raise ValueError("boom")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
