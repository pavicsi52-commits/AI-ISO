"""Tests for :class:`app.services.remediation.ValidationRemediationService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RemediationActionType, ValidationResultStatus, ValidationSeverity
from app.models.validation_result import ValidationResult
from app.repositories.validation_failure import ValidationFailureRepository
from app.repositories.validation_remediation import ValidationRemediationRepository
from app.services.failure import ValidationFailureService
from app.services.remediation import ValidationRemediationService
from tests.conftest import make_check, make_execution, make_profile, make_target


async def _make_failure(db_session: AsyncSession, org_id: uuid.UUID) -> uuid.UUID:
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
    failure = await ValidationFailureService(ValidationFailureRepository(db_session)).record(
        organization_id=org_id,
        result_id=result.id,
        severity=ValidationSeverity.HIGH,
        reason="failure",
    )
    return failure.id


def _service(db_session: AsyncSession) -> ValidationRemediationService:
    return ValidationRemediationService(ValidationRemediationRepository(db_session))


class TestValidationRemediationService:
    async def test_suggest_and_list_for_failure(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        failure_id = await _make_failure(db_session, org_id)
        service = _service(db_session)
        remediation = await service.suggest(
            organization_id=org_id,
            failure_id=failure_id,
            action_type=RemediationActionType.RECOMMENDED_FIX,
            description="Free up disk space.",
        )
        assert remediation.is_applied is False
        remediations = await service.list_for_failure(failure_id)
        assert len(remediations) == 1

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        failure_id = await _make_failure(db_session, org_id)
        service = _service(db_session)
        await service.suggest(
            organization_id=org_id,
            failure_id=failure_id,
            action_type=RemediationActionType.MANUAL_ACTION,
            description="Investigate manually.",
        )
        remediations = await service.list_for_org(org_id)
        assert len(remediations) == 1

    async def test_mark_applied(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        failure_id = await _make_failure(db_session, org_id)
        service = _service(db_session)
        remediation = await service.suggest(
            organization_id=org_id,
            failure_id=failure_id,
            action_type=RemediationActionType.AUTOMATION_INTEGRATION,
            description="Run cleanup job.",
            automation_job_key="cleanup-job",
        )
        applied = await service.mark_applied(remediation.id, applied_by=uuid.uuid4())
        assert applied.is_applied is True
        assert applied.applied_at is not None

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())
