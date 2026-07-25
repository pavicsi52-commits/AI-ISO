"""Integration tests for the global FastAPI exception handler."""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from shared_core.exceptions import (
    InternalError,
    NotFoundError,
    register_exception_handlers,
)
from shared_core.middleware import LocalizationMiddleware, RequestContextMiddleware
from starlette.testclient import TestClient


class _Item(BaseModel):
    name: str
    quantity: int


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(LocalizationMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/not-found")
    async def not_found() -> None:
        raise NotFoundError("widget id=42 missing from table widgets", details=["id=42"])

    @app.get("/internal")
    async def internal() -> None:
        raise InternalError("unexpected state: cache.size == -1")

    @app.get("/secret-leak")
    async def secret_leak() -> None:
        raise ValueError("db connection failed: password=hunter2 token=eyJabc.def.ghi")

    @app.post("/validated")
    async def validated(item: _Item) -> dict[str, str]:
        return {"name": item.name}

    @app.get("/crash-uncaught")
    async def crash_uncaught() -> None:
        raise RuntimeError("totally unexpected")

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def test_aiios_exception_returns_its_status_code(client: TestClient) -> None:
    response = client.get("/not-found")

    assert response.status_code == 404


def test_aiios_exception_response_follows_the_error_envelope(client: TestClient) -> None:
    response = client.get("/not-found")
    body = response.json()

    assert body["success"] is False
    assert body["error"]["code"] == "AIIOS-NF-0001"
    assert body["error"]["details"] == ["id=42"]
    assert "request_id" in body["meta"]


def test_aiios_exception_response_uses_user_message_not_internal_message(
    client: TestClient,
) -> None:
    response = client.get("/not-found")
    body = response.json()

    assert body["message"] == NotFoundError.default_user_message
    assert "widgets" not in body["message"]


def test_response_never_leaks_secrets_from_the_original_exception(client: TestClient) -> None:
    response = client.get("/secret-leak")
    body = response.json()

    assert "hunter2" not in str(body)
    assert "eyJabc" not in str(body)


def test_unmapped_exception_is_classified_by_the_mapper(client: TestClient) -> None:
    response = client.get("/secret-leak")

    # ValueError maps to ValidationError -> 400, per docs/015 "HTTP STATUS
    # MAPPING": "400 Validation".
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AIIOS-VAL-0001"


def test_truly_unexpected_exception_returns_500(client: TestClient) -> None:
    response = client.get("/crash-uncaught")
    body = response.json()

    assert response.status_code == 500
    assert body["error"]["code"] == "AIIOS-UNKNOWN-0001"
    assert "RuntimeError" not in str(body)


def test_undefined_route_returns_the_standard_envelope_not_fastapis_default(
    client: TestClient,
) -> None:
    response = client.get("/this-route-does-not-exist")
    body = response.json()

    assert response.status_code == 404
    assert body["error"]["code"] == "AIIOS-NF-0001"
    assert body["success"] is False


def test_request_validation_error_maps_to_validation_error(client: TestClient) -> None:
    response = client.post("/validated", json={"name": "widget"})  # missing "quantity"
    body = response.json()

    assert response.status_code == 400
    assert body["error"]["code"] == "AIIOS-VAL-0001"
    assert any("quantity" in detail for detail in body["error"]["details"])


def test_request_id_is_present_and_matches_the_response_header(client: TestClient) -> None:
    response = client.get("/not-found")

    assert response.json()["meta"]["request_id"] == response.headers["X-Request-ID"]


def test_localization_translates_the_response_message(client: TestClient) -> None:
    response = client.get("/not-found", headers={"Accept-Language": "es"})

    assert response.json()["message"] != NotFoundError.default_user_message


def test_localization_defaults_to_english_without_accept_language(client: TestClient) -> None:
    response = client.get("/not-found")

    assert response.json()["message"] == NotFoundError.default_user_message


def test_exception_is_logged_with_error_code_and_severity(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="shared_core.exceptions"):
        client.get("/not-found")

    record = next(r for r in caplog.records if r.name == "shared_core.exceptions")
    assert record.extra_fields["error_code"] == "AIIOS-NF-0001"
    assert record.extra_fields["severity"] == "low"
    assert record.levelname == "ERROR"


def test_critical_severity_exception_logs_at_critical_level(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="shared_core.exceptions"):
        client.get("/internal")

    record = next(r for r in caplog.records if r.name == "shared_core.exceptions")
    assert record.levelname == "CRITICAL"


def test_exception_log_includes_the_internal_message_and_stack_trace(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="shared_core.exceptions"):
        client.get("/not-found")

    record = next(r for r in caplog.records if r.name == "shared_core.exceptions")
    assert "widgets" in record.getMessage()
    assert record.exc_info is not None
