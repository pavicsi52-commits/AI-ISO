"""Tests for :class:`app.scanners.cloud.azure_provider.AzureProvider`.

No real Azure subscription is reachable in this environment (see the
provider's own module docstring) -- every branch here is exercised
with ``pytest-httpx`` against the real OAuth2 token-acquisition and ARM
REST request/response logic.
"""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.scanners.base import ScanCredential
from app.scanners.cloud.azure_provider import AzureProvider
from app.scanners.enumeration import EnumerationError

_TIMEOUT_SECONDS = 10.0
_TENANT_ID = "11111111-1111-1111-1111-111111111111"
_SUBSCRIPTION_ID = "22222222-2222-2222-2222-222222222222"


def _credential() -> ScanCredential:
    return ScanCredential(
        username="client-id",
        password="client-secret",
        extra={"tenant_id": _TENANT_ID, "subscription_id": _SUBSCRIPTION_ID},
    )


def _mock_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"https://login.microsoftonline.com/{_TENANT_ID}/oauth2/v2.0/token",
        json={"access_token": "a-real-looking-token"},
    )


@pytest.mark.parametrize(
    "credential",
    [None, ScanCredential(username=None, password=None)],
)
async def test_enumerate_requires_client_credential(credential: ScanCredential | None) -> None:
    with pytest.raises(EnumerationError, match="client_id/client_secret"):
        await AzureProvider().enumerate(
            "sub", credential=credential, timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_requires_tenant_and_subscription() -> None:
    credential = ScanCredential(username="client-id", password="client-secret")
    with pytest.raises(EnumerationError, match="tenant_id"):
        await AzureProvider().enumerate(
            "sub", credential=credential, timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_lists_every_resource_type(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    # Registered with no `url=` filter, so pytest-httpx matches each
    # against the next GET request in real call order -- the provider
    # itself calls these eight endpoints in exactly this sequence (see
    # AzureProvider.enumerate's own body), each with a different,
    # resource-provider-specific api-version query param this test
    # doesn't need to duplicate.
    for name in [
        "rg-1",
        "vm-1",
        "vnet-1",
        "nsg-1",
        "lb-1",
        "storage-1",
        "sql-1",
        "aks-1",
    ]:
        httpx_mock.add_response(
            method="GET",
            json={
                "value": [
                    {
                        "name": name,
                        "id": f"/subscriptions/{_SUBSCRIPTION_ID}/resource/{name}",
                        "location": "eastus",
                    }
                ]
            },
        )

    resources = await AzureProvider().enumerate(
        "sub", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
    )
    names = {resource.name for resource in resources}
    assert names == {"rg-1", "vm-1", "vnet-1", "nsg-1", "lb-1", "storage-1", "sql-1", "aks-1"}
    resource_group = next(r for r in resources if r.name == "rg-1")
    assert resource_group.resource_type == "resource_group"
    assert resource_group.identity["location"] == "eastus"


async def test_enumerate_token_endpoint_unreachable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with pytest.raises(EnumerationError, match="token endpoint unreachable"):
        await AzureProvider().enumerate(
            "sub", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_token_request_denied(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"https://login.microsoftonline.com/{_TENANT_ID}/oauth2/v2.0/token",
        status_code=401,
    )
    with pytest.raises(EnumerationError, match="Azure authentication failed"):
        await AzureProvider().enumerate(
            "sub", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_token_response_missing_access_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"https://login.microsoftonline.com/{_TENANT_ID}/oauth2/v2.0/token",
        json={},
    )
    with pytest.raises(EnumerationError, match="did not contain an access_token"):
        await AzureProvider().enumerate(
            "sub", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_arm_401_raises_enumeration_error(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    httpx_mock.add_response(method="GET", status_code=401)
    with pytest.raises(EnumerationError, match="Azure authorization failed"):
        await AzureProvider().enumerate(
            "sub", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_arm_non_200_returns_empty_for_that_resource(
    httpx_mock: HTTPXMock,
) -> None:
    _mock_token(httpx_mock)
    # One 404 per real endpoint the provider calls -- _list() itself
    # tolerates a non-200 by returning [] and moving on to the *next*
    # resource type rather than aborting, so every one of the eight
    # calls needs its own registered response.
    for _ in range(8):
        httpx_mock.add_response(method="GET", status_code=404)
    resources = await AzureProvider().enumerate(
        "sub", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
    )
    assert resources == []


async def test_enumerate_arm_request_unreachable(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with pytest.raises(EnumerationError, match="ARM request"):
        await AzureProvider().enumerate(
            "sub", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )
