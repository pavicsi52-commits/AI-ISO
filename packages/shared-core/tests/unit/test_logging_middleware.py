"""Tests for the request/response logging middleware."""

from __future__ import annotations

import logging

import pytest
from shared_core.logging.middleware import RequestLoggingMiddleware
from shared_core.logging.request_context import get_request_log_context
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


async def _ok(request):  # type: ignore[no-untyped-def]
    return JSONResponse({"ok": True})


async def _echo_request_context(request):  # type: ignore[no-untyped-def]
    context = get_request_log_context()
    return JSONResponse(
        {"method": context.method, "url": context.url, "user_agent": context.user_agent}
    )


async def _boom(request):  # type: ignore[no-untyped-def]
    raise ValueError("boom")


def _build_app(route_handler=_ok):  # type: ignore[no-untyped-def]
    app = Starlette(routes=[Route("/", route_handler)])
    app.add_middleware(RequestLoggingMiddleware)
    return app


def test_binds_request_context_during_the_call() -> None:
    client = TestClient(_build_app(_echo_request_context))

    response = client.get("/", headers={"User-Agent": "test-agent"})

    assert response.json()["method"] == "GET"
    assert response.json()["user_agent"] == "test-agent"


def test_resets_request_context_after_the_call() -> None:
    client = TestClient(_build_app(_echo_request_context))

    client.get("/")

    assert get_request_log_context().method is None


def test_logs_request_started_and_completed(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(_build_app(_ok))

    with caplog.at_level(logging.INFO, logger="shared_core.request"):
        client.get("/")

    messages = [r.getMessage() for r in caplog.records]
    assert "request.started" in messages
    assert "request.completed" in messages


def test_logs_status_code_and_latency_on_completion(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(_build_app(_ok))

    with caplog.at_level(logging.INFO, logger="shared_core.request"):
        client.get("/")

    completed = next(r for r in caplog.records if r.getMessage() == "request.completed")
    assert completed.extra_fields["status_code"] == 200
    assert isinstance(completed.extra_fields["latency_ms"], float)


def test_excludes_unsafe_headers_from_the_started_log(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(_build_app(_ok))

    with caplog.at_level(logging.INFO, logger="shared_core.request"):
        client.get("/", headers={"Authorization": "Bearer secret-token", "Cookie": "session=abc"})

    started = next(r for r in caplog.records if r.getMessage() == "request.started")
    headers = {k.lower(): v for k, v in started.extra_fields["headers"].items()}
    assert "authorization" not in headers
    assert "cookie" not in headers


def test_records_status_code_500_when_the_handler_raises(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(_build_app(_boom), raise_server_exceptions=False)

    with caplog.at_level(logging.INFO, logger="shared_core.request"):
        client.get("/")

    completed = next(r for r in caplog.records if r.getMessage() == "request.completed")
    assert completed.extra_fields["status_code"] == 500


async def test_passes_through_non_http_scopes_untouched() -> None:
    calls: list[str] = []

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        calls.append(scope["type"])

    middleware = RequestLoggingMiddleware(app)

    await middleware({"type": "lifespan"}, None, None)  # type: ignore[arg-type]

    assert calls == ["lifespan"]
