"""Tests for :class:`app.services.rule.ValidationRuleService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationCheckType, ValidationResultStatus, ValidationSeverity
from app.repositories.validation_check import ValidationCheckRepository
from app.repositories.validation_rule import ValidationRuleRepository
from app.services.check import ValidationCheckService
from app.services.rule import ValidationRuleService


def _service(db_session: AsyncSession) -> ValidationRuleService:
    return ValidationRuleService(ValidationRuleRepository(db_session))


async def _make_check(db_session: AsyncSession) -> uuid.UUID:
    check = await ValidationCheckService(ValidationCheckRepository(db_session)).create(
        organization_id=uuid.uuid4(),
        category_id=None,
        check_type=ValidationCheckType.CONNECTIVITY,
        name="check",
        description=None,
        collector_key="connectivity",
        parameters={},
        timeout_seconds=30.0,
        retry_count=0,
    )
    return check.id


class TestValidationRuleService:
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        check_id = await _make_check(db_session)
        service = _service(db_session)
        rule = await service.create(
            organization_id=uuid.uuid4(),
            check_id=check_id,
            name="High disk usage",
            description=None,
            condition="disk_usage_percent > 90",
            result_status=ValidationResultStatus.FAILED,
            severity=ValidationSeverity.HIGH,
            weight=2.0,
            remediation_hint="Free up disk space.",
            priority=0,
        )
        fetched = await service.get_by_id(rule.id)
        assert fetched.severity == ValidationSeverity.HIGH

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_check_orders_by_priority(self, db_session: AsyncSession) -> None:
        check_id = await _make_check(db_session)
        service = _service(db_session)
        second = await service.create(
            organization_id=uuid.uuid4(),
            check_id=check_id,
            name="second",
            description=None,
            condition="true",
            result_status=ValidationResultStatus.WARNING,
            severity=ValidationSeverity.LOW,
            weight=1.0,
            remediation_hint=None,
            priority=1,
        )
        first = await service.create(
            organization_id=uuid.uuid4(),
            check_id=check_id,
            name="first",
            description=None,
            condition="true",
            result_status=ValidationResultStatus.FAILED,
            severity=ValidationSeverity.HIGH,
            weight=1.0,
            remediation_hint=None,
            priority=0,
        )
        rules = await service.list_for_check(check_id)
        assert [rule.id for rule in rules] == [first.id, second.id]
