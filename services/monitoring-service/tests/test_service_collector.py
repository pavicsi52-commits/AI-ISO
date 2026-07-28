"""Tests for :class:`app.services.collector.MonitoringCollectorService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MonitoringTargetType
from app.repositories.monitoring_collector import MonitoringCollectorRepository
from app.services.collector import MonitoringCollectorService


def _service(db_session: AsyncSession) -> MonitoringCollectorService:
    return MonitoringCollectorService(MonitoringCollectorRepository(db_session))


class TestMonitoringCollectorService:
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        collector = await service.create(
            organization_id=uuid.uuid4(),
            name="cpu-collector",
            collector_key="automation_job",
            target_types=[MonitoringTargetType.PHYSICAL_SERVER],
            parameters={"job_id": str(uuid.uuid4())},
            interval_seconds=30.0,
            is_active=True,
        )
        fetched = await service.get_by_id(collector.id)
        assert fetched.name == "cpu-collector"

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        await service.create(
            organization_id=org_id,
            name="connectivity-collector",
            collector_key="connectivity",
            target_types=[],
            parameters={},
            interval_seconds=60.0,
            is_active=True,
        )
        collectors = await service.list_for_org(org_id)
        assert len(collectors) == 1

    async def test_list_all_active_excludes_inactive(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        await service.create(
            organization_id=uuid.uuid4(),
            name="active",
            collector_key="dns",
            target_types=[],
            parameters={},
            interval_seconds=60.0,
            is_active=True,
        )
        await service.create(
            organization_id=uuid.uuid4(),
            name="inactive",
            collector_key="dns",
            target_types=[],
            parameters={},
            interval_seconds=60.0,
            is_active=False,
        )
        active = await service.list_all_active()
        assert all(c.is_active for c in active)
        assert any(c.name == "active" for c in active)
