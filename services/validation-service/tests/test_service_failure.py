"""Tests for :class:`app.services.failure.ValidationFailureService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationResultStatus, ValidationSeverity
from app.models.validation_result import ValidationResult
from app.repositories.validation_failure import ValidationFailureRepository
from app.repositories.validation_result import ValidationResultRepository
from app.services.failure import ValidationFailureService
from tests.conftest import make_check, make_execution, make_profile, make_target


def _service(db_session: AsyncSession) -> ValidationFailureService:
    return ValidationFailureService(ValidationFailureRepository(db_session))


async def _make_result(db_session: AsyncSession, org_id: uuid.UUID) -> ValidationResult:
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
        status=ValidationResultStatus.FAILED,
    )
    db_session.add(result)
    await db_session.flush()
    return await ValidationResultRepository(db_session).require_by_id(result.id)


class TestValidationFailureService:
    async def test_record_and_list_for_result(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        result = await _make_result(db_session, org_id)
        service = _service(db_session)
        await service.record(
            organization_id=org_id,
            result_id=result.id,
            severity=ValidationSeverity.HIGH,
            reason="disk usage too high",
        )
        failures = await service.list_for_result(result.id)
        assert len(failures) == 1

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_unresolved_for_org(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        result = await _make_result(db_session, org_id)
        service = _service(db_session)
        failure = await service.record(
            organization_id=org_id,
            result_id=result.id,
            severity=ValidationSeverity.MEDIUM,
            reason="reason",
        )
        unresolved = await service.list_unresolved_for_org(org_id)
        assert len(unresolved) == 1

        resolved = await service.resolve(failure.id, resolved_by=uuid.uuid4())
        assert resolved.is_resolved is True
        assert await service.list_unresolved_for_org(org_id) == []
