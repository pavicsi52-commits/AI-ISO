"""Tests for :class:`app.clients.inventory_client.InventoryClient`
against real documented Inventory Service response shapes, via
``pytest-httpx``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.clients.inventory_client import InventoryClient
from tests.conftest import INVENTORY_SERVICE_BASE_URL


@pytest.fixture
async def inventory_client() -> AsyncIterator[InventoryClient]:
    async with httpx.AsyncClient() as client:
        yield InventoryClient(client, base_url=INVENTORY_SERVICE_BASE_URL, caller_token="tok")


class TestInventoryClient:
    async def test_get_asset_returns_record(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        asset_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/assets/{asset_id}",
            json={"data": {"id": str(asset_id), "status": "active"}},
        )
        asset = await inventory_client.get_asset(asset_id)
        assert asset["status"] == "active"

    async def test_get_asset_missing_raises(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        asset_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/assets/{asset_id}", status_code=404
        )
        with pytest.raises(DependencyError, match="HTTP 404"):
            await inventory_client.get_asset(asset_id)

    async def test_get_asset_unreachable_raises(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await inventory_client.get_asset(uuid.uuid4())
