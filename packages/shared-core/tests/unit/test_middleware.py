"""Tests for the reusable ASGI middleware."""

from __future__ import annotations

from shared_core.middleware import (
    CompressionMiddleware,
    InMemoryRateLimiter,
    LocalizationMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    TenantResolutionMiddleware,
    TimingMiddleware,
    parse_preferred_locale,
)
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


async def _ok(request):  # type: ignore[no-untyped-def]
    return JSONResponse({"ok": True})


async def _echo_state(request):  # type: ignore[no-untyped-def]
    return JSONResponse(
        {
            "organization_id": request.state.organization_id,
            "project_id": request.state.project_id,
        }
    )


async def _echo_locale(request):  # type: ignore[no-untyped-def]
    return JSONResponse({"locale": request.state.locale})


async def _large_response(request):  # type: ignore[no-untyped-def]
    return JSONResponse({"data": "x" * 5000})


def _build_app(middleware_cls, route_handler=_ok, **kwargs):  # type: ignore[no-untyped-def]
    app = Starlette(routes=[Route("/", route_handler)])
    app.add_middleware(middleware_cls, **kwargs)
    return app


def test_request_context_middleware_assigns_ids_when_absent() -> None:
    client = TestClient(_build_app(RequestContextMiddleware))

    response = client.get("/")

    assert response.headers["x-request-id"]
    assert response.headers["x-correlation-id"]


def test_request_context_middleware_honors_supplied_request_id() -> None:
    client = TestClient(_build_app(RequestContextMiddleware))

    response = client.get("/", headers={"X-Request-ID": "my-id"})

    assert response.headers["x-request-id"] == "my-id"
    assert response.headers["x-correlation-id"] == "my-id"


def test_timing_middleware_does_not_break_response() -> None:
    client = TestClient(_build_app(TimingMiddleware))

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_security_headers_middleware_adds_expected_headers() -> None:
    client = TestClient(_build_app(SecurityHeadersMiddleware))

    response = client.get("/")

    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "strict-transport-security" in response.headers


def test_compression_middleware_is_the_starlette_gzip_middleware() -> None:
    client = TestClient(_build_app(CompressionMiddleware, route_handler=_large_response))

    response = client.get("/", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200


def test_tenant_resolution_middleware_binds_headers_to_state() -> None:
    client = TestClient(_build_app(TenantResolutionMiddleware, route_handler=_echo_state))

    response = client.get("/", headers={"X-Organization-ID": "org-1", "X-Project-ID": "proj-1"})

    assert response.json() == {"organization_id": "org-1", "project_id": "proj-1"}


def test_tenant_resolution_middleware_defaults_to_none() -> None:
    client = TestClient(_build_app(TenantResolutionMiddleware, route_handler=_echo_state))

    response = client.get("/")

    assert response.json() == {"organization_id": None, "project_id": None}


def test_localization_middleware_resolves_supported_locale() -> None:
    client = TestClient(_build_app(LocalizationMiddleware, route_handler=_echo_locale))

    response = client.get("/", headers={"Accept-Language": "en-US,en;q=0.9"})

    assert response.json() == {"locale": "en"}


def test_localization_middleware_defaults_when_header_absent() -> None:
    client = TestClient(_build_app(LocalizationMiddleware, route_handler=_echo_locale))

    response = client.get("/")

    assert response.json() == {"locale": "en"}


def test_parse_preferred_locale_falls_back_for_unsupported_language() -> None:
    assert parse_preferred_locale("fr-FR,fr;q=0.9") == "en"


def test_parse_preferred_locale_handles_none() -> None:
    assert parse_preferred_locale(None) == "en"


def test_in_memory_rate_limiter_allows_up_to_the_limit() -> None:
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)

    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is False


def test_in_memory_rate_limiter_tracks_keys_independently() -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)

    assert limiter.allow("client-a") is True
    assert limiter.allow("client-b") is True
    assert limiter.allow("client-a") is False


def test_rate_limit_middleware_allows_requests_under_the_limit() -> None:
    client = TestClient(_build_app(RateLimitMiddleware, max_requests=5, window_seconds=60))

    for _ in range(5):
        assert client.get("/").status_code == 200


def test_rate_limit_middleware_blocks_requests_over_the_limit() -> None:
    client = TestClient(_build_app(RateLimitMiddleware, max_requests=2, window_seconds=60))

    client.get("/")
    client.get("/")
    response = client.get("/")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "AIIOS-RATE-0001"
