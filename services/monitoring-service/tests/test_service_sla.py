"""Tests for :class:`app.services.sla.MonitoringSLAService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ComplianceStatus, SLAType
from app.models.monitoring_sla import MonitoringSLA
from app.repositories.monitoring_sla import MonitoringSLARepository
from app.services.sla import MonitoringSLAService
from tests.conftest import make_target


def _service(db_session: AsyncSession) -> MonitoringSLAService:
    return MonitoringSLAService(MonitoringSLARepository(db_session))


async def _create_sla(db_session: AsyncSession, service: MonitoringSLAService) -> MonitoringSLA:
    target = await make_target(db_session)
    now = datetime.now(UTC)
    return await service.create(
        organization_id=target.organization_id,
        target_id=target.id,
        sla_type=SLAType.AVAILABILITY,
        objective_percentage=99.9,
        period_start=now - timedelta(days=30),
        period_end=now,
    )


class TestMonitoringSLAService:
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        sla = await _create_sla(db_session, service)
        fetched = await service.get_by_id(sla.id)
        assert fetched.status == ComplianceStatus.COMPLIANT

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_target(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        sla = await _create_sla(db_session, service)
        slas = await service.list_for_target(sla.target_id)
        assert len(slas) == 1

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        sla = await _create_sla(db_session, service)
        slas = await service.list_for_org(sla.organization_id)
        assert len(slas) == 1

    async def test_update_actual_compliant(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        sla = await _create_sla(db_session, service)
        updated = await service.update_actual(sla.id, actual_percentage=99.95)
        assert updated.status == ComplianceStatus.COMPLIANT

    async def test_update_actual_at_risk(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        sla = await _create_sla(db_session, service)
        updated = await service.update_actual(sla.id, actual_percentage=99.5)
        assert updated.status == ComplianceStatus.AT_RISK

    async def test_update_actual_violated(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        sla = await _create_sla(db_session, service)
        updated = await service.update_actual(sla.id, actual_percentage=90.0)
        assert updated.status == ComplianceStatus.VIOLATED
