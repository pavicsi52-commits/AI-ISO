"""Tests for :class:`app.services.rule.MonitoringRuleService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.monitoring.thresholds import ThresholdLevel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MonitoringRuleType
from app.repositories.monitoring_rule import MonitoringRuleRepository
from app.services.rule import MonitoringRuleService
from tests.conftest import make_metric


def _service(db_session: AsyncSession) -> MonitoringRuleService:
    return MonitoringRuleService(MonitoringRuleRepository(db_session))


class TestMonitoringRuleService:
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        metric = await make_metric(db_session)
        rule = await service.create(
            organization_id=metric.organization_id,
            metric_id=metric.id,
            rule_type=MonitoringRuleType.METRIC,
            name="cpu-spike",
            description=None,
            condition="value > 90",
            severity=ThresholdLevel.HIGH,
            window_seconds=None,
            escalation_after_seconds=None,
        )
        fetched = await service.get_by_id(rule.id)
        assert fetched.name == "cpu-spike"

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_metric(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        metric = await make_metric(db_session)
        await service.create(
            organization_id=metric.organization_id,
            metric_id=metric.id,
            rule_type=MonitoringRuleType.METRIC,
            name="rule-1",
            description=None,
            condition="value > 1",
            severity=ThresholdLevel.LOW,
            window_seconds=None,
            escalation_after_seconds=None,
        )
        rules = await service.list_for_metric(metric.id)
        assert len(rules) == 1

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        metric = await make_metric(db_session)
        await service.create(
            organization_id=metric.organization_id,
            metric_id=metric.id,
            rule_type=MonitoringRuleType.COMPOSITE,
            name="rule-2",
            description="desc",
            condition="value > 2",
            severity=ThresholdLevel.MEDIUM,
            window_seconds=60.0,
            escalation_after_seconds=120.0,
        )
        rules = await service.list_for_org(metric.organization_id)
        assert len(rules) == 1
