"""Tests for :class:`app.services.audit.MonitoringAuditService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.monitoring_audit import MonitoringAuditEntryRepository
from app.services.audit import MonitoringAuditService


def _service(db_session: AsyncSession) -> MonitoringAuditService:
    return MonitoringAuditService(MonitoringAuditEntryRepository(db_session))


class TestMonitoringAuditService:
    async def test_record_and_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        await service.record(
            organization_id=org_id,
            actor_id=actor_id,
            action="create_threshold",
            entity_type="MonitoringThreshold",
            entity_id=uuid.uuid4(),
            reason="initial configuration",
            details={"high": 90.0},
        )
        entries = await service.list_for_org(org_id)
        assert len(entries) == 1
        assert entries[0].action == "create_threshold"
