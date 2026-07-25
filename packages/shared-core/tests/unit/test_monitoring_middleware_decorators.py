"""Tests for middleware.py and decorators.py."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from shared_core.monitoring.application import ApplicationStatistics
from shared_core.monitoring.decorators import monitored, track_errors
from shared_core.monitoring.middleware import ApplicationMonitoringMiddleware
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


def _build_app(
    statistics: ApplicationStatistics, route_handler: Callable[..., Awaitable[JSONResponse]]
) -> Starlette:
    app = Starlette(routes=[Route("/", route_handler)])
    app.add_middleware(ApplicationMonitoringMiddleware, statistics=statistics)
    return app


# --- middleware.py ---


def test_application_monitoring_middleware_records_a_successful_request() -> None:
    statistics = ApplicationStatistics()
    client = TestClient(_build_app(statistics, _ok))

    response = client.get("/")

    assert response.status_code == 200
    assert statistics.request_count == 1
    assert statistics.error_count == 0


def test_application_monitoring_middleware_records_a_500_response_as_an_error() -> None:
    statistics = ApplicationStatistics()
    client = TestClient(_build_app(statistics, _server_error))

    response = client.get("/")

    assert response.status_code == 500
    assert statistics.request_count == 1
    assert statistics.error_count == 1


async def test_application_monitoring_middleware_passes_through_non_http_scopes() -> None:
    statistics = ApplicationStatistics()
    inner_called = False

    async def inner_app(scope, receive, send):
        nonlocal inner_called
        inner_called = True

    middleware = ApplicationMonitoringMiddleware(inner_app, statistics=statistics)

    async def _receive():
        return {"type": "lifespan.startup"}

    async def _send(message):
        pass

    await middleware({"type": "lifespan"}, _receive, _send)

    assert inner_called is True
    assert statistics.request_count == 0


def test_application_monitoring_middleware_records_an_unhandled_exception() -> None:
    statistics = ApplicationStatistics()
    client = TestClient(_build_app(statistics, _raises), raise_server_exceptions=False)

    client.get("/")

    assert statistics.exception_count == 1
    assert statistics.request_count == 1


# --- decorators.py ---


async def test_monitored_records_a_successful_call() -> None:
    statistics = ApplicationStatistics()

    @monitored(statistics)
    async def handler() -> str:
        return "done"

    result = await handler()

    assert result == "done"
    assert statistics.request_count == 1
    assert statistics.exception_count == 0


async def test_monitored_records_and_reraises_an_exception() -> None:
    statistics = ApplicationStatistics()

    @monitored(statistics)
    async def handler() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await handler()

    assert statistics.request_count == 1
    assert statistics.exception_count == 1


async def test_track_errors_reraises_without_recording_on_success() -> None:
    statistics = ApplicationStatistics()

    @track_errors(statistics)
    async def handler() -> str:
        return "done"

    result = await handler()

    assert result == "done"
    assert statistics.error_count == 0


async def test_track_errors_records_and_reraises_an_exception() -> None:
    statistics = ApplicationStatistics()

    @track_errors(statistics)
    async def handler() -> None:
        raise ValueError("bad")

    with pytest.raises(ValueError, match="bad"):
        await handler()

    assert statistics.error_count == 1
