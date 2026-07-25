"""Tests for :class:`app.discovery.credentials.CredentialResolver` --
live HTTP calls to the Secrets Management Service, mocked with
``pytest-httpx`` (no real secrets-management-service instance is
running in this environment; see the module's own docstring for why
this is the one dependency this service can't stand up locally).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient, ConnectError
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.discovery.credentials import CredentialResolver
from app.models.discovery_credential import DiscoveryCredential
from app.models.enums import CredentialType, ProtocolType
from app.scanners.base import ScanCredential

_BASE_URL = "http://secrets.internal"


def _credential(
    credential_type: CredentialType, *, username: str | None = "svc"
) -> DiscoveryCredential:
    return DiscoveryCredential(
        organization_id=uuid.uuid4(),
        name="test-credential",
        protocol=ProtocolType.SSH,
        credential_type=credential_type,
        secret_id=uuid.uuid4(),
        username=username,
    )


@pytest.mark.parametrize(
    ("credential_type", "expected_field"),
    [
        (CredentialType.SSH_KEY, "private_key"),
        (CredentialType.PASSWORD, "password"),
        (CredentialType.API_KEY, "token"),
        (CredentialType.TOKEN, "token"),
        (CredentialType.CERTIFICATE, "extra"),
    ],
)
async def test_resolve_shapes_value_by_credential_type(
    httpx_mock: HTTPXMock, credential_type: CredentialType, expected_field: str
) -> None:
    credential = _credential(credential_type)
    httpx_mock.add_response(
        url=f"{_BASE_URL}/secrets/{credential.secret_id}", json={"data": {"value": "s3cr3t"}}
    )
    async with AsyncClient() as client:
        resolver = CredentialResolver(client, base_url=_BASE_URL)
        result = await resolver.resolve(credential, caller_token="tok")

    assert isinstance(result, ScanCredential)
    assert result.username == "svc"
    if expected_field == "extra":
        assert result.extra == {"certificate": "s3cr3t"}
    else:
        assert getattr(result, expected_field) == "s3cr3t"


async def test_resolve_forwards_caller_token(httpx_mock: HTTPXMock) -> None:
    credential = _credential(CredentialType.PASSWORD)
    httpx_mock.add_response(json={"data": {"value": "hunter2"}})
    async with AsyncClient() as client:
        resolver = CredentialResolver(client, base_url=_BASE_URL)
        await resolver.resolve(credential, caller_token="my-token")

    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"] == "Bearer my-token"


async def test_resolve_not_found_raises_dependency_error(httpx_mock: HTTPXMock) -> None:
    credential = _credential(CredentialType.PASSWORD)
    httpx_mock.add_response(status_code=404)
    async with AsyncClient() as client:
        resolver = CredentialResolver(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await resolver.resolve(credential, caller_token="tok")


@pytest.mark.parametrize("status_code", [401, 403])
async def test_resolve_unauthorized_raises_dependency_error(
    httpx_mock: HTTPXMock, status_code: int
) -> None:
    credential = _credential(CredentialType.PASSWORD)
    httpx_mock.add_response(status_code=status_code)
    async with AsyncClient() as client:
        resolver = CredentialResolver(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await resolver.resolve(credential, caller_token="tok")


async def test_resolve_unexpected_status_raises_dependency_error(httpx_mock: HTTPXMock) -> None:
    credential = _credential(CredentialType.PASSWORD)
    httpx_mock.add_response(status_code=500)
    async with AsyncClient() as client:
        resolver = CredentialResolver(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await resolver.resolve(credential, caller_token="tok")


async def test_resolve_unreachable_raises_dependency_error(httpx_mock: HTTPXMock) -> None:
    credential = _credential(CredentialType.PASSWORD)
    httpx_mock.add_exception(ConnectError("connection refused"))
    async with AsyncClient() as client:
        resolver = CredentialResolver(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await resolver.resolve(credential, caller_token="tok")
