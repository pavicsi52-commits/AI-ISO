"""Tests for :class:`app.services.slo.MonitoringSLOService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ComplianceStatus, SLOType
from app.models.monitoring_slo import MonitoringSLO
from app.repositories.monitoring_slo import MonitoringSLORepository
from app.services.slo import MonitoringSLOService
from tests.conftest import make_target


def _service(db_session: AsyncSession) -> MonitoringSLOService:
    return MonitoringSLOService(MonitoringSLORepository(db_session))


async def _create_slo(db_session: AsyncSession, service: MonitoringSLOService) -> MonitoringSLO:
    target = await make_target(db_session)
    now = datetime.now(UTC)
    return await service.create(
        organization_id=target.organization_id,
        target_id=target.id,
        slo_type=SLOType.LATENCY,
        objective_value=200.0,
        period_start=now - timedelta(days=30),
        period_end=now,
    )


class TestMonitoringSLOService:
    async def test_create_defaults_full_error_budget(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        slo = await _create_slo(db_session, service)
        assert slo.error_budget_remaining_percentage == 100.0
        assert slo.status == ComplianceStatus.COMPLIANT

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_target(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        slo = await _create_slo(db_session, service)
        slos = await service.list_for_target(slo.target_id)
        assert len(slos) == 1

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        slo = await _create_slo(db_session, service)
        slos = await service.list_for_org(slo.organization_id)
        assert len(slos) == 1

    async def test_update_actual_compliant(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        slo = await _create_slo(db_session, service)
        updated = await service.update_actual(
            slo.id, actual_value=150.0, error_budget_remaining_percentage=80.0
        )
        assert updated.status == ComplianceStatus.COMPLIANT

    async def test_update_actual_at_risk(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        slo = await _create_slo(db_session, service)
        updated = await service.update_actual(
            slo.id, actual_value=190.0, error_budget_remaining_percentage=10.0
        )
        assert updated.status == ComplianceStatus.AT_RISK

    async def test_update_actual_violated(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        slo = await _create_slo(db_session, service)
        updated = await service.update_actual(
            slo.id, actual_value=500.0, error_budget_remaining_percentage=0.0
        )
        assert updated.status == ComplianceStatus.VIOLATED
