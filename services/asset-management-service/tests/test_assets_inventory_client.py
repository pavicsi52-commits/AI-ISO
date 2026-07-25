"""Tests for :class:`app.assets.inventory_client.InventoryClient` -- live
HTTP calls to the Inventory Service, mocked with ``pytest-httpx``.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient, ConnectError
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.assets.inventory_client import InventoryClient

_BASE_URL = "http://inventory.internal"


async def test_get_asset_summary_found(httpx_mock: HTTPXMock) -> None:
    inventory_asset_id = uuid.uuid4()
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE_URL}/inventory/assets/{inventory_asset_id}",
        json={"data": {"id": str(inventory_asset_id), "name": "web-01"}},
    )
    async with AsyncClient() as client:
        inventory = InventoryClient(client, base_url=_BASE_URL)
        summary = await inventory.get_asset_summary(inventory_asset_id, caller_token="tok")

    assert summary is not None
    assert summary["name"] == "web-01"


async def test_get_asset_summary_not_found(httpx_mock: HTTPXMock) -> None:
    inventory_asset_id = uuid.uuid4()
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE_URL}/inventory/assets/{inventory_asset_id}",
        status_code=404,
    )
    async with AsyncClient() as client:
        inventory = InventoryClient(client, base_url=_BASE_URL)
        summary = await inventory.get_asset_summary(inventory_asset_id, caller_token="tok")

    assert summary is None


@pytest.mark.parametrize("status_code", [401, 403])
async def test_get_asset_summary_unauthorized_raises(
    httpx_mock: HTTPXMock, status_code: int
) -> None:
    inventory_asset_id = uuid.uuid4()
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE_URL}/inventory/assets/{inventory_asset_id}",
        status_code=status_code,
    )
    async with AsyncClient() as client:
        inventory = InventoryClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await inventory.get_asset_summary(inventory_asset_id, caller_token="tok")


async def test_get_asset_summary_unexpected_status_raises(httpx_mock: HTTPXMock) -> None:
    inventory_asset_id = uuid.uuid4()
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE_URL}/inventory/assets/{inventory_asset_id}",
        status_code=500,
    )
    async with AsyncClient() as client:
        inventory = InventoryClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await inventory.get_asset_summary(inventory_asset_id, caller_token="tok")


async def test_get_asset_summary_unreachable_raises(httpx_mock: HTTPXMock) -> None:
    inventory_asset_id = uuid.uuid4()
    httpx_mock.add_exception(
        ConnectError("refused"),
        url=f"{_BASE_URL}/inventory/assets/{inventory_asset_id}",
    )
    async with AsyncClient() as client:
        inventory = InventoryClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await inventory.get_asset_summary(inventory_asset_id, caller_token="tok")
