"""Tests for :class:`app.secrets.credential_resolver.SecretCredentialResolver`
against real documented Secrets Management Service response shapes,
via ``pytest-httpx``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.secrets.credential_resolver import SecretCredentialResolver
from tests.conftest import SECRETS_SERVICE_BASE_URL


@pytest.fixture
async def resolver() -> AsyncIterator[SecretCredentialResolver]:
    async with httpx.AsyncClient() as client:
        yield SecretCredentialResolver(client, base_url=SECRETS_SERVICE_BASE_URL)


class TestSecretCredentialResolver:
    async def test_resolve_returns_value(
        self, httpx_mock: HTTPXMock, resolver: SecretCredentialResolver
    ) -> None:
        httpx_mock.add_response(
            url=f"{SECRETS_SERVICE_BASE_URL}/secrets/abc",
            json={"data": {"value": "s3cr3t"}},
        )
        value = await resolver.resolve("abc", caller_token="tok")
        assert value == "s3cr3t"

    async def test_resolve_not_found_raises(
        self, httpx_mock: HTTPXMock, resolver: SecretCredentialResolver
    ) -> None:
        httpx_mock.add_response(url=f"{SECRETS_SERVICE_BASE_URL}/secrets/missing", status_code=404)
        with pytest.raises(DependencyError, match="was not found"):
            await resolver.resolve("missing", caller_token="tok")

    async def test_resolve_forbidden_raises(
        self, httpx_mock: HTTPXMock, resolver: SecretCredentialResolver
    ) -> None:
        httpx_mock.add_response(url=f"{SECRETS_SERVICE_BASE_URL}/secrets/abc", status_code=403)
        with pytest.raises(DependencyError, match="Not authorized"):
            await resolver.resolve("abc", caller_token="tok")

    async def test_resolve_server_error_raises(
        self, httpx_mock: HTTPXMock, resolver: SecretCredentialResolver
    ) -> None:
        httpx_mock.add_response(url=f"{SECRETS_SERVICE_BASE_URL}/secrets/abc", status_code=500)
        with pytest.raises(DependencyError, match="HTTP 500"):
            await resolver.resolve("abc", caller_token="tok")

    async def test_resolve_unreachable_raises(
        self, httpx_mock: HTTPXMock, resolver: SecretCredentialResolver
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await resolver.resolve("abc", caller_token="tok")
