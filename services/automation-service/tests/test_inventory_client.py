"""Tests for :class:`app.inventory.inventory_client.InventoryClient`
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

from app.inventory.inventory_client import InventoryClient
from tests.conftest import INVENTORY_SERVICE_BASE_URL


@pytest.fixture
async def inventory_client() -> AsyncIterator[InventoryClient]:
    async with httpx.AsyncClient() as client:
        yield InventoryClient(client, base_url=INVENTORY_SERVICE_BASE_URL)


class TestInventoryClient:
    async def test_get_asset_found(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        asset_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/assets/{asset_id}",
            json={"data": {"id": str(asset_id), "name": "asset-1"}},
        )
        asset = await inventory_client.get_asset(asset_id, caller_token="tok")
        assert asset is not None
        assert asset["name"] == "asset-1"

    async def test_get_asset_not_found_returns_none(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        asset_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/assets/{asset_id}", status_code=404
        )
        asset = await inventory_client.get_asset(asset_id, caller_token="tok")
        assert asset is None

    async def test_get_asset_forbidden_raises(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        asset_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/assets/{asset_id}", status_code=401
        )
        with pytest.raises(DependencyError, match="Not authorized"):
            await inventory_client.get_asset(asset_id, caller_token="tok")

    async def test_get_asset_server_error_raises(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        asset_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/assets/{asset_id}", status_code=500
        )
        with pytest.raises(DependencyError, match="HTTP 500"):
            await inventory_client.get_asset(asset_id, caller_token="tok")

    async def test_get_asset_unreachable_raises(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await inventory_client.get_asset(uuid.uuid4(), caller_token="tok")

    async def test_list_group_members(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        group_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/groups/{group_id}/members",
            json={"data": {"items": [{"id": "a"}, {"id": "b"}]}},
        )
        members = await inventory_client.list_group_members(group_id, caller_token="tok")
        assert len(members) == 2

    async def test_list_group_members_missing_group_raises(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        group_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/groups/{group_id}/members",
            status_code=404,
        )
        with pytest.raises(DependencyError, match="was not found"):
            await inventory_client.list_group_members(group_id, caller_token="tok")

    async def test_search_assets(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/search?q=web",
            json={"data": [{"id": "1"}]},
        )
        results = await inventory_client.search_assets(query="web", caller_token="tok")
        assert len(results) == 1

    async def test_search_assets_forbidden_raises(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/search?q=web", status_code=403
        )
        with pytest.raises(DependencyError, match="Not authorized"):
            await inventory_client.search_assets(query="web", caller_token="tok")

    async def test_search_assets_server_error_raises(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/search?q=web", status_code=500
        )
        with pytest.raises(DependencyError, match="HTTP 500"):
            await inventory_client.search_assets(query="web", caller_token="tok")

    async def test_search_assets_unreachable_raises(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await inventory_client.search_assets(query="web", caller_token="tok")

    async def test_search_assets_non_list_items_returns_empty(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/search?q=web",
            json={"data": {"items": "not-a-list"}},
        )
        results = await inventory_client.search_assets(query="web", caller_token="tok")
        assert results == []
