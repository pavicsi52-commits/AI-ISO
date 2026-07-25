"""Tests for the request validation middleware."""

from __future__ import annotations

from fastapi import FastAPI
from shared_core.exceptions import register_exception_handlers
from shared_core.validation.middleware import RequestValidationMiddleware
from starlette.responses import JSONResponse
from starlette.testclient import TestClient


def _build_app(**middleware_kwargs):  # type: ignore[no-untyped-def]
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RequestValidationMiddleware, **middleware_kwargs)

    @app.get("/")
    @app.post("/")
    async def _ok() -> JSONResponse:
        return JSONResponse({"ok": True})

    return app


def test_passes_through_when_no_requirements_configured() -> None:
    client = TestClient(_build_app())

    response = client.get("/")

    assert response.status_code == 200


def test_passes_when_required_header_present() -> None:
    client = TestClient(_build_app(required_headers=["X-Api-Version"]))

    response = client.get("/", headers={"X-Api-Version": "1"})

    assert response.status_code == 200


def test_raises_when_required_header_missing() -> None:
    client = TestClient(
        _build_app(required_headers=["X-Api-Version"]), raise_server_exceptions=False
    )

    response = client.get("/")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AIIOS-VAL-0001"


def test_raises_when_body_exceeds_max_size() -> None:
    client = TestClient(_build_app(max_body_bytes=10), raise_server_exceptions=False)

    response = client.post("/", content=b"x" * 100)

    assert response.status_code == 400


async def test_middleware_call_passes_through_lifespan_scope() -> None:
    calls: list[str] = []

    async def inner_app(scope, receive, send):  # type: ignore[no-untyped-def]
        calls.append(scope["type"])

    middleware = RequestValidationMiddleware(inner_app)

    await middleware({"type": "lifespan"}, None, None)  # type: ignore[arg-type]

    assert calls == ["lifespan"]
