"""Tests for middleware.py and request.py."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode, Tracer
from shared_core.logging.context import bind_log_context, reset_log_context
from shared_core.telemetry.middleware import TracingMiddleware
from shared_core.telemetry.propagation import inject_context
from shared_core.telemetry.request import (
    current_correlation_id,
    current_request_id,
    tag_span_with_request_ids,
)
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


async def _ok(request):
    return JSONResponse({"ok": True})


async def _server_error(request):
    return JSONResponse({"ok": False}, status_code=500)


async def _raises(request):
    raise RuntimeError("boom")


def _build_app(tracer: Tracer, route_handler: Callable[..., Awaitable[JSONResponse]]) -> Starlette:
    app = Starlette(routes=[Route("/widgets/{id}", route_handler)])
    app.add_middleware(TracingMiddleware, tracer=tracer)
    return app


def _tracer_and_exporter() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


# --- middleware.py ---


def test_tracing_middleware_creates_a_span_named_after_method_and_path() -> None:
    tracer, exporter = _tracer_and_exporter()
    client = TestClient(_build_app(tracer, _ok))

    response = client.get("/widgets/123")

    assert response.status_code == 200
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "GET /widgets/123"


def test_tracing_middleware_tags_http_attributes() -> None:
    tracer, exporter = _tracer_and_exporter()
    client = TestClient(_build_app(tracer, _ok))

    client.get("/widgets/123")

    attributes = exporter.get_finished_spans()[0].attributes
    assert attributes is not None
    assert attributes["http.method"] == "GET"
    assert attributes["http.route"] == "/widgets/123"
    assert attributes["http.status_code"] == 200
    assert attributes["span.type"] == "http_request"


def test_tracing_middleware_marks_a_500_response_as_an_error_span() -> None:
    tracer, exporter = _tracer_and_exporter()
    client = TestClient(_build_app(tracer, _server_error))

    client.get("/widgets/123")

    span = exporter.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR


def test_tracing_middleware_marks_an_unhandled_exception_as_an_error_span() -> None:
    tracer, exporter = _tracer_and_exporter()
    client = TestClient(_build_app(tracer, _raises), raise_server_exceptions=False)

    client.get("/widgets/123")

    span = exporter.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR


def test_tracing_middleware_continues_a_propagated_upstream_trace() -> None:
    tracer, exporter = _tracer_and_exporter()
    client = TestClient(_build_app(tracer, _ok))

    with tracer.start_as_current_span("upstream-gateway") as upstream_span:
        expected_trace_id = upstream_span.get_span_context().trace_id
        headers = inject_context()

    client.get("/widgets/123", headers=headers)

    span = exporter.get_finished_spans()[0]
    span_context = span.get_span_context()
    assert span_context is not None
    assert span_context.trace_id == expected_trace_id


def test_tracing_middleware_leaves_non_http_scopes_untouched() -> None:
    tracer, _exporter = _tracer_and_exporter()

    async def inner_app(scope, receive, send):
        assert scope["type"] == "lifespan"

    middleware = TracingMiddleware(inner_app, tracer=tracer)

    async def _receive():
        return {"type": "lifespan.startup"}

    async def _send(message):
        pass

    asyncio.run(middleware({"type": "lifespan"}, _receive, _send))


# --- request.py ---


def test_tag_span_with_request_ids_sets_attributes_when_bound() -> None:
    tracer, exporter = _tracer_and_exporter()
    bind_log_context(request_id="req-1", correlation_id="corr-1")
    try:
        with tracer.start_as_current_span("op") as span:
            tag_span_with_request_ids(span)
    finally:
        reset_log_context()

    attributes = exporter.get_finished_spans()[0].attributes
    assert attributes is not None
    assert attributes["request_id"] == "req-1"
    assert attributes["correlation_id"] == "corr-1"


def test_tag_span_with_request_ids_is_a_noop_when_nothing_is_bound() -> None:
    tracer, exporter = _tracer_and_exporter()
    reset_log_context()

    with tracer.start_as_current_span("op") as span:
        tag_span_with_request_ids(span)

    attributes = exporter.get_finished_spans()[0].attributes
    assert attributes is not None
    assert "request_id" not in attributes
    assert "correlation_id" not in attributes


def test_current_request_and_correlation_id_read_the_bound_context() -> None:
    bind_log_context(request_id="req-2", correlation_id="corr-2")
    try:
        assert current_request_id() == "req-2"
        assert current_correlation_id() == "corr-2"
    finally:
        reset_log_context()


def test_current_request_and_correlation_id_are_none_with_no_context() -> None:
    reset_log_context()

    assert current_request_id() is None
    assert current_correlation_id() is None
