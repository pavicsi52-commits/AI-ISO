"""Tests for :class:`AssetStatusHistoryService`, :class:`AssetHealthHistoryService`,
and :class:`AssetLifecycleHistoryService`.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AssetStatus, HealthStatus, LifecycleState
from app.repositories.asset_health_history import AssetHealthHistoryRepository
from app.repositories.asset_lifecycle_history import AssetLifecycleHistoryRepository
from app.repositories.asset_status_history import AssetStatusHistoryRepository
from app.services.health_history import AssetHealthHistoryService
from app.services.lifecycle_history import AssetLifecycleHistoryService
from app.services.status_history import AssetStatusHistoryService
from tests.conftest import make_asset


async def test_status_history_record_and_list(db_session: AsyncSession) -> None:
    service = AssetStatusHistoryService(AssetStatusHistoryRepository(db_session))
    asset = await make_asset(db_session)
    entry = await service.record(
        asset.id,
        organization_id=asset.organization_id,
        previous_status=AssetStatus.DISCOVERED,
        new_status=AssetStatus.MANAGED,
        changed_by=uuid.uuid4(),
        reason="onboarded",
    )
    assert entry.new_status == AssetStatus.MANAGED
    records = await service.list_for_asset(asset.id)
    assert [r.id for r in records] == [entry.id]


async def test_health_history_record_and_list(db_session: AsyncSession) -> None:
    service = AssetHealthHistoryService(AssetHealthHistoryRepository(db_session))
    asset = await make_asset(db_session)
    entry = await service.record(
        asset.id,
        organization_id=asset.organization_id,
        health_status=HealthStatus.WARNING,
        detail="cpu high",
    )
    assert entry.health_status == HealthStatus.WARNING
    records = await service.list_for_asset(asset.id)
    assert [r.id for r in records] == [entry.id]


async def test_lifecycle_history_record_and_list(db_session: AsyncSession) -> None:
    service = AssetLifecycleHistoryService(AssetLifecycleHistoryRepository(db_session))
    asset = await make_asset(db_session)
    entry = await service.record(
        asset.id,
        organization_id=asset.organization_id,
        previous_state=LifecycleState.PLANNED,
        new_state=LifecycleState.OPERATIONAL,
        transitioned_by=uuid.uuid4(),
        notes="went live",
    )
    assert entry.new_state == LifecycleState.OPERATIONAL
    records = await service.list_for_asset(asset.id)
    assert [r.id for r in records] == [entry.id]


__all__: list[str] = []
