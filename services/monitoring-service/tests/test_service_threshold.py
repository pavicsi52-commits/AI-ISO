"""Tests for :class:`app.services.threshold.MonitoringThresholdService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ThresholdType
from app.repositories.monitoring_threshold import MonitoringThresholdRepository
from app.services.threshold import MonitoringThresholdService
from tests.conftest import make_metric


def _service(db_session: AsyncSession) -> MonitoringThresholdService:
    return MonitoringThresholdService(MonitoringThresholdRepository(db_session))


class TestMonitoringThresholdService:
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        metric = await make_metric(db_session)
        threshold = await service.create(
            organization_id=metric.organization_id,
            metric_id=metric.id,
            threshold_type=ThresholdType.STATIC,
            informational=None,
            low=None,
            medium=None,
            high=80.0,
            critical=95.0,
            is_active=True,
        )
        fetched = await service.get_by_id(threshold.id)
        assert fetched.high == 80.0

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_metric_excludes_inactive(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        metric = await make_metric(db_session)
        await service.create(
            organization_id=metric.organization_id,
            metric_id=metric.id,
            threshold_type=ThresholdType.STATIC,
            informational=None,
            low=None,
            medium=None,
            high=80.0,
            critical=None,
            is_active=True,
        )
        await service.create(
            organization_id=metric.organization_id,
            metric_id=metric.id,
            threshold_type=ThresholdType.STATIC,
            informational=None,
            low=None,
            medium=None,
            high=90.0,
            critical=None,
            is_active=False,
        )
        active = await service.list_for_metric(metric.id)
        assert len(active) == 1
        assert active[0].high == 80.0
