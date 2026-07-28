"""Tests for :class:`app.services.synthetic_test.MonitoringSyntheticTestService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SyntheticCheckType
from app.repositories.monitoring_synthetic_test import MonitoringSyntheticTestRepository
from app.services.synthetic_test import MonitoringSyntheticTestService


def _service(db_session: AsyncSession) -> MonitoringSyntheticTestService:
    return MonitoringSyntheticTestService(MonitoringSyntheticTestRepository(db_session))


class TestMonitoringSyntheticTestService:
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        test = await service.create(
            organization_id=uuid.uuid4(),
            target_id=None,
            check_type=SyntheticCheckType.HTTP,
            name="ping-check",
            parameters={"url": "http://example.internal"},
            interval_seconds=300.0,
            is_active=True,
        )
        fetched = await service.get_by_id(test.id)
        assert fetched.name == "ping-check"

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        await service.create(
            organization_id=org_id,
            target_id=None,
            check_type=SyntheticCheckType.TCP,
            name="tcp-check",
            parameters={},
            interval_seconds=60.0,
            is_active=True,
        )
        tests = await service.list_for_org(org_id)
        assert len(tests) == 1

    async def test_list_all_active(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        await service.create(
            organization_id=uuid.uuid4(),
            target_id=None,
            check_type=SyntheticCheckType.DNS,
            name="dns-check",
            parameters={},
            interval_seconds=60.0,
            is_active=True,
        )
        active = await service.list_all_active()
        assert any(test.name == "dns-check" for test in active)
