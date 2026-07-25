"""Tests for :class:`app.discovery.inventory_sync.InventorySyncClient` --
live HTTP calls to the Inventory Service, mocked with ``pytest-httpx``.
"""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import AsyncClient, ConnectError
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.discovery.inventory_sync import InventorySyncClient
from app.models.discovery_asset import DiscoveryAsset
from app.models.discovery_relationship import DiscoveryRelationship
from app.models.enums import AssetClassification, DiscoveryRelationshipType

_BASE_URL = "http://inventory.internal"


def _asset() -> DiscoveryAsset:
    return DiscoveryAsset(
        organization_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        result_id=uuid.uuid4(),
        name="host-1",
        asset_type="server",
        classification=AssetClassification.COMPUTE,
        fingerprint={"vendor": "Acme"},
    )


async def test_sync_asset_created(httpx_mock: HTTPXMock) -> None:
    asset_id = uuid.uuid4()
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/inventory/assets",
        status_code=201,
        json={"data": {"id": str(asset_id)}},
    )
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        inventory_id, created = await sync.sync_asset(
            _asset(),
            organization_id=uuid.uuid4(),
            caller_token="tok",
            identifiers={"hostname": "host-1"},
        )
    assert inventory_id == asset_id
    assert created is True


async def test_sync_asset_conflict_reconciles_existing(httpx_mock: HTTPXMock) -> None:
    existing_id = str(uuid.uuid4())
    httpx_mock.add_response(
        method="POST", url=f"{_BASE_URL}/inventory/assets", status_code=409, json={}
    )
    httpx_mock.add_response(
        method="GET",
        url=re.compile(rf"^{re.escape(_BASE_URL)}/inventory/search"),
        json={
            "data": {
                "items": [
                    {
                        "id": existing_id,
                        "status": "active",
                        "health": "healthy",
                        "lifecycle_state": "production",
                        "criticality": "medium",
                    }
                ]
            }
        },
    )
    httpx_mock.add_response(
        method="PUT",
        url=f"{_BASE_URL}/inventory/assets/{existing_id}",
        json={"data": {"id": existing_id}},
    )
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        inventory_id, created = await sync.sync_asset(
            _asset(),
            organization_id=uuid.uuid4(),
            caller_token="tok",
            identifiers={"hostname": "host-1"},
        )
    assert str(inventory_id) == existing_id
    assert created is False


async def test_sync_asset_conflict_with_no_search_match_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=f"{_BASE_URL}/inventory/assets", status_code=409)
    httpx_mock.add_response(
        method="GET",
        url=re.compile(rf"^{re.escape(_BASE_URL)}/inventory/search"),
        json={"data": {"items": []}},
    )
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await sync.sync_asset(
                _asset(),
                organization_id=uuid.uuid4(),
                caller_token="tok",
                identifiers={"hostname": "host-1"},
            )


@pytest.mark.parametrize("status_code", [401, 403])
async def test_sync_asset_unauthorized_raises(httpx_mock: HTTPXMock, status_code: int) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{_BASE_URL}/inventory/assets", status_code=status_code
    )
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await sync.sync_asset(
                _asset(), organization_id=uuid.uuid4(), caller_token="tok", identifiers={}
            )


async def test_sync_asset_unexpected_status_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=f"{_BASE_URL}/inventory/assets", status_code=500)
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await sync.sync_asset(
                _asset(), organization_id=uuid.uuid4(), caller_token="tok", identifiers={}
            )


async def test_sync_asset_unreachable_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(ConnectError("refused"), url=f"{_BASE_URL}/inventory/assets")
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await sync.sync_asset(
                _asset(), organization_id=uuid.uuid4(), caller_token="tok", identifiers={}
            )


async def test_sync_asset_search_unreachable_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=f"{_BASE_URL}/inventory/assets", status_code=409)
    httpx_mock.add_exception(
        ConnectError("refused"),
        url=re.compile(rf"^{re.escape(_BASE_URL)}/inventory/search"),
    )
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await sync.sync_asset(
                _asset(), organization_id=uuid.uuid4(), caller_token="tok", identifiers={}
            )


async def test_sync_asset_search_failure_status_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=f"{_BASE_URL}/inventory/assets", status_code=409)
    httpx_mock.add_response(
        method="GET",
        url=re.compile(rf"^{re.escape(_BASE_URL)}/inventory/search"),
        status_code=500,
    )
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await sync.sync_asset(
                _asset(), organization_id=uuid.uuid4(), caller_token="tok", identifiers={}
            )


async def test_sync_asset_reconcile_update_failure_raises(httpx_mock: HTTPXMock) -> None:
    existing_id = str(uuid.uuid4())
    httpx_mock.add_response(method="POST", url=f"{_BASE_URL}/inventory/assets", status_code=409)
    httpx_mock.add_response(
        method="GET",
        url=re.compile(rf"^{re.escape(_BASE_URL)}/inventory/search"),
        json={
            "data": {
                "items": [
                    {
                        "id": existing_id,
                        "status": "active",
                        "health": "healthy",
                        "lifecycle_state": "production",
                        "criticality": "medium",
                    }
                ]
            }
        },
    )
    httpx_mock.add_response(
        method="PUT", url=f"{_BASE_URL}/inventory/assets/{existing_id}", status_code=500
    )
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await sync.sync_asset(
                _asset(), organization_id=uuid.uuid4(), caller_token="tok", identifiers={}
            )


def _relationship() -> DiscoveryRelationship:
    return DiscoveryRelationship(
        organization_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        source_discovery_asset_id=uuid.uuid4(),
        target_discovery_asset_id=uuid.uuid4(),
        relationship_type=DiscoveryRelationshipType.RUNS_ON,
    )


@pytest.mark.parametrize("status_code", [201, 409])
async def test_sync_relationship_tolerates_created_or_conflict(
    httpx_mock: HTTPXMock, status_code: int
) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{_BASE_URL}/inventory/relationships", status_code=status_code
    )
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        await sync.sync_relationship(
            _relationship(),
            organization_id=uuid.uuid4(),
            source_inventory_asset_id=uuid.uuid4(),
            target_inventory_asset_id=uuid.uuid4(),
            caller_token="tok",
        )


@pytest.mark.parametrize("status_code", [401, 403])
async def test_sync_relationship_unauthorized_raises(
    httpx_mock: HTTPXMock, status_code: int
) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{_BASE_URL}/inventory/relationships", status_code=status_code
    )
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await sync.sync_relationship(
                _relationship(),
                organization_id=uuid.uuid4(),
                source_inventory_asset_id=uuid.uuid4(),
                target_inventory_asset_id=uuid.uuid4(),
                caller_token="tok",
            )


async def test_sync_relationship_unexpected_status_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{_BASE_URL}/inventory/relationships", status_code=500
    )
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await sync.sync_relationship(
                _relationship(),
                organization_id=uuid.uuid4(),
                source_inventory_asset_id=uuid.uuid4(),
                target_inventory_asset_id=uuid.uuid4(),
                caller_token="tok",
            )


async def test_sync_relationship_unreachable_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(ConnectError("refused"))
    async with AsyncClient() as client:
        sync = InventorySyncClient(client, base_url=_BASE_URL)
        with pytest.raises(DependencyError):
            await sync.sync_relationship(
                _relationship(),
                organization_id=uuid.uuid4(),
                source_inventory_asset_id=uuid.uuid4(),
                target_inventory_asset_id=uuid.uuid4(),
                caller_token="tok",
            )
