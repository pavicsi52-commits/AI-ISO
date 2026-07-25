"""Tests for :class:`app.services.audit.AssetAuditService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditOutcome
from app.repositories.asset_audit import AssetAuditRepository
from app.services.audit import AssetAuditService
from tests.conftest import make_managed_asset


def _build(db_session: AsyncSession) -> AssetAuditService:
    return AssetAuditService(AssetAuditRepository(db_session))


async def test_record_and_list_newest_first(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    await service.record(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        actor_id=uuid.uuid4(),
        action="create",
        after={"business_name": managed_asset.business_name},
    )
    await service.record(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        actor_id=None,
        action="update",
        outcome=AuditOutcome.FAILURE,
        reason="validation failed",
    )

    entries = await service.list_for_managed_asset(managed_asset.id)
    assert [entry.action for entry in entries] == ["update", "create"]
    assert entries[0].outcome == AuditOutcome.FAILURE
    assert entries[0].reason == "validation failed"
