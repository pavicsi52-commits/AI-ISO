"""Tests for the core structured logging module: context, formatting, logger API."""

from __future__ import annotations

import json
import logging as stdlib_logging
import os
import sys
import threading

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared_core.exceptions import AIIOSException
from shared_core.logging import (
    JsonFormatter,
    LoggingConfigurationError,
    LogHandlerError,
    bind_log_context,
    bind_request_log_context,
    build_log_record,
    configure_logging,
    get_log_context,
    get_logger,
    get_request_log_context,
    reset_log_context,
    reset_request_log_context,
    resolve_log_level,
)
from shared_core.logging.logger import AIIOSLogger


def _make_record(msg: str = "hello", level: int = stdlib_logging.INFO) -> stdlib_logging.LogRecord:
    return stdlib_logging.LogRecord(
        name="app.test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


@pytest.fixture(autouse=True)
def _reset_contexts() -> None:
    reset_log_context()
    reset_request_log_context()
    yield
    reset_log_context()
    reset_request_log_context()


# --- context ---


def test_bind_log_context_merges_fields() -> None:
    bind_log_context(request_id="req-1", user_id="user-1")

    context = get_log_context()

    assert context.request_id == "req-1"
    assert context.user_id == "user-1"


def test_bind_log_context_is_additive() -> None:
    bind_log_context(request_id="req-1")
    bind_log_context(correlation_id="corr-1")

    context = get_log_context()

    assert context.request_id == "req-1"
    assert context.correlation_id == "corr-1"


def test_bind_log_context_supports_session_trace_span() -> None:
    bind_log_context(session_id="sess-1", trace_id="trace-1", span_id="span-1")

    context = get_log_context()

    assert context.session_id == "sess-1"
    assert context.trace_id == "trace-1"
    assert context.span_id == "span-1"


def test_reset_log_context_clears_all_fields() -> None:
    bind_log_context(request_id="req-1")
    reset_log_context()

    assert get_log_context().request_id is None


def test_bind_request_log_context_merges_fields() -> None:
    bind_request_log_context(method="GET", url="http://x/y")

    context = get_request_log_context()

    assert context.method == "GET"
    assert context.url == "http://x/y"


def test_reset_request_log_context_clears_all_fields() -> None:
    bind_request_log_context(method="GET")
    reset_request_log_context()

    assert get_request_log_context().method is None


# --- formatter (build_log_record) ---


def test_build_log_record_contains_every_required_field() -> None:
    record = _make_record()

    payload = build_log_record(record, service="svc", environment="testing")

    required_fields = {
        "timestamp",
        "level",
        "service",
        "environment",
        "hostname",
        "request_id",
        "correlation_id",
        "organization_id",
        "project_id",
        "user_id",
        "session_id",
        "trace_id",
        "span_id",
        "thread_id",
        "process_id",
        "method",
        "url",
        "status_code",
        "latency_ms",
        "ip_address",
        "user_agent",
        "message",
        "exception",
    }
    assert required_fields <= payload.keys()


def test_build_log_record_includes_context_fields() -> None:
    bind_log_context(request_id="req-1", correlation_id="corr-1", organization_id="org-1")
    bind_request_log_context(method="GET", url="http://x/y", ip_address="1.2.3.4")

    payload = build_log_record(_make_record(), service="svc", environment="testing")

    assert payload["request_id"] == "req-1"
    assert payload["correlation_id"] == "corr-1"
    assert payload["organization_id"] == "org-1"
    assert payload["method"] == "GET"
    assert payload["url"] == "http://x/y"
    assert payload["ip_address"] == "1.2.3.4"


def test_build_log_record_includes_process_and_thread_ids() -> None:
    payload = build_log_record(_make_record(), service="svc", environment="testing")

    assert payload["process_id"] == os.getpid()
    assert payload["thread_id"] == threading.get_ident()


def test_build_log_record_extra_fields_override_defaults() -> None:
    record = _make_record()
    record.extra_fields = {"status_code": 201, "latency_ms": 12.5}

    payload = build_log_record(record, service="svc", environment="testing")

    assert payload["status_code"] == 201
    assert payload["latency_ms"] == 12.5


def test_build_log_record_includes_exception_traceback() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = _make_record(msg="failed", level=stdlib_logging.ERROR)
        record.exc_info = sys.exc_info()

    payload = build_log_record(record, service="svc", environment="testing")

    assert "ValueError" in payload["exception"]


def test_build_log_record_uses_active_otel_span_trace_id() -> None:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("test-span"):
        payload = build_log_record(_make_record(), service="svc", environment="testing")

    assert payload["trace_id"] is not None
    assert payload["span_id"] is not None


# --- json_formatter ---


def test_json_formatter_includes_context_fields() -> None:
    bind_log_context(request_id="req-1", correlation_id="corr-1", organization_id="org-1")
    formatter = JsonFormatter(service="test-service", environment="testing")

    rendered = json.loads(formatter.format(_make_record()))

    assert rendered["message"] == "hello"
    assert rendered["service"] == "test-service"
    assert rendered["request_id"] == "req-1"
    assert rendered["correlation_id"] == "corr-1"
    assert rendered["organization_id"] == "org-1"


def test_json_formatter_masks_sensitive_extra_fields() -> None:
    formatter = JsonFormatter(service="test-service", environment="testing")
    record = _make_record()
    record.extra_fields = {"password": "hunter2", "safe_field": "visible"}

    rendered = json.loads(formatter.format(record))

    assert rendered["password"] == "***MASKED***"
    assert rendered["safe_field"] == "visible"


def test_json_formatter_masks_jwt_in_message() -> None:
    formatter = JsonFormatter(service="test-service", environment="testing")
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ"
    record = _make_record(msg=f"token was {jwt}")

    rendered = json.loads(formatter.format(record))

    assert jwt not in rendered["message"]
    assert "***MASKED***" in rendered["message"]


def test_json_formatter_includes_exception_traceback() -> None:
    formatter = JsonFormatter(service="test-service", environment="testing")
    try:
        raise ValueError("boom")
    except ValueError:
        record = _make_record(msg="failed", level=stdlib_logging.ERROR)
        record.exc_info = sys.exc_info()

    rendered = json.loads(formatter.format(record))

    assert "ValueError" in rendered["exception"]


# --- logger / AIIOSLogger ---


def test_resolve_log_level_maps_every_supported_name() -> None:
    assert resolve_log_level("TRACE") < stdlib_logging.DEBUG
    assert resolve_log_level("DEBUG") == stdlib_logging.DEBUG
    assert resolve_log_level("INFO") == stdlib_logging.INFO
    assert resolve_log_level("WARNING") == stdlib_logging.WARNING
    assert resolve_log_level("ERROR") == stdlib_logging.ERROR
    assert resolve_log_level("CRITICAL") == stdlib_logging.CRITICAL


def test_resolve_log_level_falls_back_to_info() -> None:
    assert resolve_log_level("NOT_A_LEVEL") == stdlib_logging.INFO


def test_get_logger_returns_an_aiios_logger() -> None:
    logger = get_logger("app.custom")

    assert isinstance(logger, AIIOSLogger)


def test_get_logger_upgrades_a_preexisting_plain_logger() -> None:
    plain = stdlib_logging.getLogger("app.preexisting.plain")
    plain.__class__ = stdlib_logging.Logger

    upgraded = get_logger("app.preexisting.plain")

    assert isinstance(upgraded, AIIOSLogger)
    assert upgraded is plain


def test_trace_emits_below_debug_and_respects_level_gate(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("app.trace.test")
    logger.setLevel(resolve_log_level("TRACE"))

    with caplog.at_level(resolve_log_level("TRACE"), logger="app.trace.test"):
        logger.trace("a trace message")

    assert any(record.getMessage() == "a trace message" for record in caplog.records)


def test_trace_is_suppressed_above_trace_level(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("app.trace.suppressed")
    logger.setLevel(stdlib_logging.DEBUG)

    with caplog.at_level(stdlib_logging.DEBUG, logger="app.trace.suppressed"):
        logger.trace("should not appear")

    assert not any(record.getMessage() == "should not appear" for record in caplog.records)


def test_audit_logs_at_info_with_audit_category(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("app.audit.test")

    with caplog.at_level(stdlib_logging.INFO, logger="app.audit.test"):
        logger.audit("user.created", actor_id="u1", resource="user:42")

    record = caplog.records[-1]
    assert record.levelname == "INFO"
    assert record.extra_fields["category"] == "audit"
    assert record.extra_fields["action"] == "user.created"
    assert record.extra_fields["actor_id"] == "u1"


def test_security_logs_at_warning_with_security_category(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("app.security.test")

    with caplog.at_level(stdlib_logging.WARNING, logger="app.security.test"):
        logger.security("failed_login", outcome="blocked")

    record = caplog.records[-1]
    assert record.levelname == "WARNING"
    assert record.extra_fields["category"] == "security"
    assert record.extra_fields["outcome"] == "blocked"


def test_performance_logs_at_info_with_performance_category(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = get_logger("app.performance.test")

    with caplog.at_level(stdlib_logging.INFO, logger="app.performance.test"):
        logger.performance("db_query", value=42.0, unit="ms")

    record = caplog.records[-1]
    assert record.levelname == "INFO"
    assert record.extra_fields["category"] == "performance"
    assert record.extra_fields["value"] == 42.0


def test_configure_logging_installs_json_formatter() -> None:
    configure_logging(service="test-service", environment="testing", level="DEBUG")

    root_logger = stdlib_logging.getLogger()

    assert root_logger.level == stdlib_logging.DEBUG
    assert len(root_logger.handlers) == 1
    assert isinstance(root_logger.handlers[0].formatter, JsonFormatter)


def test_configure_logging_supports_trace_level() -> None:
    configure_logging(service="test-service", environment="testing", level="TRACE")

    assert stdlib_logging.getLogger().level == resolve_log_level("TRACE")


def test_configure_logging_falls_back_to_info_for_unknown_level() -> None:
    configure_logging(service="test-service", environment="testing", level="NOT_A_LEVEL")

    assert stdlib_logging.getLogger().level == stdlib_logging.INFO


# --- exceptions ---


def test_logging_configuration_error_is_an_aiios_exception() -> None:
    assert isinstance(LoggingConfigurationError("bad config"), AIIOSException)


def test_log_handler_error_is_an_aiios_exception() -> None:
    assert isinstance(LogHandlerError("bad handler"), AIIOSException)
