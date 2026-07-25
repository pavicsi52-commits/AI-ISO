"""Tests for :class:`InventoryAuditService`, :class:`AssetHistoryService`,
and :class:`AssetVersionService`.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditOutcome
from app.repositories.asset_history import AssetHistoryRepository
from app.repositories.asset_version import AssetVersionRepository
from app.repositories.inventory_audit import InventoryAuditRepository
from app.services.audit import InventoryAuditService
from app.services.history import AssetHistoryService
from app.services.version import AssetVersionService
from tests.conftest import make_asset


async def test_audit_record_and_list(db_session: AsyncSession) -> None:
    service = InventoryAuditService(InventoryAuditRepository(db_session))
    asset = await make_asset(db_session)
    entry = await service.record(
        asset.id,
        organization_id=asset.organization_id,
        actor_id=uuid.uuid4(),
        action="update",
        outcome=AuditOutcome.SUCCESS,
        reason="test",
        before={"a": 1},
        after={"a": 2},
    )
    assert entry.action == "update"
    records = await service.list_for_asset(asset.id)
    assert [r.id for r in records] == [entry.id]


async def test_audit_record_with_no_asset(db_session: AsyncSession) -> None:
    service = InventoryAuditService(InventoryAuditRepository(db_session))
    entry = await service.record(
        None, organization_id=uuid.uuid4(), actor_id=None, action="bulk_admin_action"
    )
    assert entry.asset_id is None


async def test_history_record_and_list(db_session: AsyncSession) -> None:
    service = AssetHistoryService(AssetHistoryRepository(db_session))
    asset = await make_asset(db_session)
    entry = await service.record(
        asset.id,
        organization_id=asset.organization_id,
        actor_id=uuid.uuid4(),
        event_type="created",
        detail={"name": asset.name},
    )
    assert entry.event_type == "created"
    records = await service.list_for_asset(asset.id)
    assert [r.id for r in records] == [entry.id]


async def test_version_create_snapshot_increments(db_session: AsyncSession) -> None:
    service = AssetVersionService(AssetVersionRepository(db_session))
    asset = await make_asset(db_session)
    v1 = await service.create_snapshot(
        asset.id, organization_id=asset.organization_id, snapshot={"name": "a"}, created_by=None
    )
    v2 = await service.create_snapshot(
        asset.id, organization_id=asset.organization_id, snapshot={"name": "b"}, created_by=None
    )
    assert v1.version_number == 1
    assert v2.version_number == 2
    records = await service.list_for_asset(asset.id)
    assert len(records) == 2


async def test_version_get_by_number(db_session: AsyncSession) -> None:
    service = AssetVersionService(AssetVersionRepository(db_session))
    asset = await make_asset(db_session)
    created = await service.create_snapshot(
        asset.id, organization_id=asset.organization_id, snapshot={"name": "a"}, created_by=None
    )
    fetched = await service.get_by_number(asset.id, 1)
    assert fetched.id == created.id


async def test_version_get_by_number_not_found(db_session: AsyncSession) -> None:
    service = AssetVersionService(AssetVersionRepository(db_session))
    asset = await make_asset(db_session)
    with pytest.raises(NotFoundError):
        await service.get_by_number(asset.id, 99)


__all__: list[str] = []
