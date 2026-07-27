"""Tests for :class:`app.services.exception.ValidationExceptionService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationExceptionStatus, ValidationResultStatus, ValidationSeverity
from app.models.validation_result import ValidationResult
from app.repositories.validation_exception import ValidationExceptionRepository
from app.repositories.validation_failure import ValidationFailureRepository
from app.services.exception import ValidationExceptionService
from app.services.failure import ValidationFailureService
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
        severity=ValidationSeverity.CRITICAL,
        reason="critical failure",
    )
    return failure.id


def _service(db_session: AsyncSession) -> ValidationExceptionService:
    return ValidationExceptionService(ValidationExceptionRepository(db_session))


class TestValidationExceptionService:
    async def test_request_and_list_for_failure(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        failure_id = await _make_failure(db_session, org_id)
        service = _service(db_session)
        exception = await service.request(
            organization_id=org_id,
            failure_id=failure_id,
            reason="accepted risk",
            requested_by=uuid.uuid4(),
            expires_at=None,
        )
        assert exception.status == ValidationExceptionStatus.PENDING
        exceptions = await service.list_for_failure(failure_id)
        assert len(exceptions) == 1

    async def test_list_pending_for_org(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        failure_id = await _make_failure(db_session, org_id)
        service = _service(db_session)
        await service.request(
            organization_id=org_id,
            failure_id=failure_id,
            reason="accepted risk",
            requested_by=uuid.uuid4(),
            expires_at=None,
        )
        pending = await service.list_pending_for_org(org_id)
        assert len(pending) == 1

    async def test_decide_approve(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        failure_id = await _make_failure(db_session, org_id)
        service = _service(db_session)
        exception = await service.request(
            organization_id=org_id,
            failure_id=failure_id,
            reason="accepted risk",
            requested_by=uuid.uuid4(),
            expires_at=None,
        )
        decided = await service.decide(
            exception.id, approve=True, decided_by=uuid.uuid4(), decision_reason="ok"
        )
        assert decided.status == ValidationExceptionStatus.APPROVED

    async def test_decide_reject(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        failure_id = await _make_failure(db_session, org_id)
        service = _service(db_session)
        exception = await service.request(
            organization_id=org_id,
            failure_id=failure_id,
            reason="accepted risk",
            requested_by=uuid.uuid4(),
            expires_at=None,
        )
        decided = await service.decide(
            exception.id, approve=False, decided_by=uuid.uuid4(), decision_reason="denied"
        )
        assert decided.status == ValidationExceptionStatus.REJECTED

    async def test_decide_already_decided_raises_conflict(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        failure_id = await _make_failure(db_session, org_id)
        service = _service(db_session)
        exception = await service.request(
            organization_id=org_id,
            failure_id=failure_id,
            reason="accepted risk",
            requested_by=uuid.uuid4(),
            expires_at=None,
        )
        await service.decide(
            exception.id, approve=True, decided_by=uuid.uuid4(), decision_reason=None
        )
        with pytest.raises(ConflictError):
            await service.decide(
                exception.id, approve=True, decided_by=uuid.uuid4(), decision_reason=None
            )

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())
