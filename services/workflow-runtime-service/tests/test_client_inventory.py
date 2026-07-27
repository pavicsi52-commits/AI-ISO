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
    async def test_resolve_group_members(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        group_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/groups/{group_id}/members",
            json={"data": [{"id": str(asset_id)}]},
        )
        members = await inventory_client.resolve_group_members(group_id)
        assert members == [asset_id]

    async def test_resolve_group_members_not_found_raises(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        group_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/groups/{group_id}/members",
            status_code=404,
        )
        with pytest.raises(DependencyError, match="HTTP 404"):
            await inventory_client.resolve_group_members(group_id)

    async def test_resolve_group_members_unreachable_raises(
        self, httpx_mock: HTTPXMock, inventory_client: InventoryClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await inventory_client.resolve_group_members(uuid.uuid4())
