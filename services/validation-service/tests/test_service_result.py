"""Tests for :class:`app.services.result.ValidationResultService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationResultStatus
from app.models.validation_result import ValidationResult
from app.models.validation_result_detail import ValidationResultDetail
from app.repositories.validation_result import ValidationResultRepository
from app.repositories.validation_result_detail import ValidationResultDetailRepository
from app.services.result import ValidationResultService
from tests.conftest import make_check, make_execution, make_profile, make_target


def _service(db_session: AsyncSession) -> ValidationResultService:
    return ValidationResultService(
        ValidationResultRepository(db_session), ValidationResultDetailRepository(db_session)
    )


class TestValidationResultService:
    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_execution_and_target(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        check = await make_check(db_session, organization_id=org_id)
        profile = await make_profile(db_session, organization_id=org_id, check_ids=[check.id])
        target = await make_target(db_session, organization_id=org_id)
        execution = await make_execution(db_session, profile, [target])

        result = ValidationResult(
            organization_id=org_id,
            execution_id=execution.id,
            target_id=target.id,
            check_id=check.id,
            check_type=check.check_type,
            status=ValidationResultStatus.PASSED,
        )
        db_session.add(result)
        await db_session.flush()

        service = _service(db_session)
        by_execution = await service.list_for_execution(execution.id)
        by_target = await service.list_for_target(target.id)
        assert len(by_execution) == 1
        assert len(by_target) == 1

    async def test_list_details(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        check = await make_check(db_session, organization_id=org_id)
        profile = await make_profile(db_session, organization_id=org_id, check_ids=[check.id])
        target = await make_target(db_session, organization_id=org_id)
        execution = await make_execution(db_session, profile, [target])
        result = ValidationResult(
            organization_id=org_id,
            execution_id=execution.id,
            target_id=target.id,
            check_id=check.id,
            check_type=check.check_type,
            status=ValidationResultStatus.PASSED,
        )
        db_session.add(result)
        await db_session.flush()
        detail = ValidationResultDetail(
            organization_id=org_id, result_id=result.id, key="latency_ms", value=12.5
        )
        db_session.add(detail)
        await db_session.flush()

        service = _service(db_session)
        details = await service.list_details(result.id)
        assert details == [detail]
