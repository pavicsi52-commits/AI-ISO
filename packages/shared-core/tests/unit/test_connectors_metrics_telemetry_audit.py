"""Tests for metrics.py, telemetry.py, and audit.py."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared_core.connectors import audit
from shared_core.connectors import metrics as connector_metrics
from shared_core.connectors.telemetry import trace_operation


def _provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


# --- metrics.py ---


def test_record_connection_increments_the_counter() -> None:
    before = connector_metrics.connector_connections_total.labels(provider="ssh")._value.get()

    connector_metrics.record_connection("ssh")

    after = connector_metrics.connector_connections_total.labels(provider="ssh")._value.get()
    assert after == before + 1


def test_record_success_increments_and_observes_latency() -> None:
    before = connector_metrics.connector_success_total.labels(provider="ssh")._value.get()

    connector_metrics.record_success("ssh", latency_seconds=0.5)

    after = connector_metrics.connector_success_total.labels(provider="ssh")._value.get()
    assert after == before + 1


def test_record_success_without_latency_still_increments() -> None:
    before = connector_metrics.connector_success_total.labels(provider="rest")._value.get()

    connector_metrics.record_success("rest")

    after = connector_metrics.connector_success_total.labels(provider="rest")._value.get()
    assert after == before + 1


def test_record_failure_increments_the_counter() -> None:
    before = connector_metrics.connector_failure_total.labels(provider="ssh")._value.get()

    connector_metrics.record_failure("ssh")

    after = connector_metrics.connector_failure_total.labels(provider="ssh")._value.get()
    assert after == before + 1


def test_record_retry_increments_the_counter() -> None:
    before = connector_metrics.connector_retries_total.labels(provider="ssh")._value.get()

    connector_metrics.record_retry("ssh")

    after = connector_metrics.connector_retries_total.labels(provider="ssh")._value.get()
    assert after == before + 1


def test_record_bandwidth_adds_to_the_counter() -> None:
    before = connector_metrics.connector_bandwidth_bytes_total.labels(
        provider="sftp", direction="upload"
    )._value.get()

    connector_metrics.record_bandwidth("sftp", direction="upload", num_bytes=2048)

    after = connector_metrics.connector_bandwidth_bytes_total.labels(
        provider="sftp", direction="upload"
    )._value.get()
    assert after == before + 2048


def test_record_transfer_size_observes() -> None:
    connector_metrics.record_transfer_size("sftp", 4096)  # doesn't raise


def test_measure_command_records_duration_regardless_of_outcome() -> None:
    with connector_metrics.measure_command("ssh"):
        pass

    with pytest.raises(RuntimeError), connector_metrics.measure_command("ssh"):
        raise RuntimeError("boom")


def test_measure_inventory_records_duration() -> None:
    with connector_metrics.measure_inventory("ssh"):
        pass


def test_measure_discovery_records_duration() -> None:
    with connector_metrics.measure_discovery("ssh"):
        pass


# --- telemetry.py ---


async def test_trace_operation_creates_a_span_with_success_status() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    async with trace_operation(
        tracer, "ssh", provider="ssh", target="10.0.0.1", operation="connect"
    ):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes is not None
    assert spans[0].attributes["status"] == "success"
    assert spans[0].attributes["provider"] == "ssh"


async def test_trace_operation_records_error_status_and_reraises() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with pytest.raises(RuntimeError):
        async with trace_operation(
            tracer, "ssh", provider="ssh", target="10.0.0.1", operation="execute"
        ):
            raise RuntimeError("command failed")

    spans = exporter.get_finished_spans()
    assert spans[0].attributes is not None
    assert spans[0].attributes["status"] == "error"
    assert "command failed" in str(spans[0].attributes["error"])


# --- audit.py ---


def test_audit_functions_do_not_raise() -> None:
    audit.audit_connect("ssh", "10.0.0.1")
    audit.audit_authenticate("ssh", "10.0.0.1", outcome="success")
    audit.audit_command("ssh", "10.0.0.1", command="uptime", outcome="success")
    audit.audit_transfer("sftp", "10.0.0.1", direction="upload", path="/tmp/x", outcome="success")
    audit.audit_inventory("ssh", "10.0.0.1", outcome="success")
    audit.audit_discovery("ssh", "10.0.0.1", outcome="success")
    audit.audit_failure("ssh", "10.0.0.1", operation="connect", error="timed out")
    audit.audit_disconnect("ssh", "10.0.0.1")


def test_audit_all_exports_every_function() -> None:
    assert set(audit.__all__) == {
        "audit_authenticate",
        "audit_command",
        "audit_connect",
        "audit_disconnect",
        "audit_discovery",
        "audit_failure",
        "audit_inventory",
        "audit_transfer",
    }
