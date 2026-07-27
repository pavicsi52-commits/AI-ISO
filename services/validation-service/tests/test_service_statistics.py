"""Tests for :class:`app.services.statistics.ValidationStatisticsService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    ValidationExecutionStatus,
    ValidationResultStatus,
    ValidationSeverity,
)
from app.models.validation_result import ValidationResult
from app.repositories.validation_execution import ValidationExecutionRepository
from app.repositories.validation_failure import ValidationFailureRepository
from app.repositories.validation_history import ValidationHistoryRepository
from app.repositories.validation_profile import ValidationProfileRepository
from app.repositories.validation_statistics import ValidationStatisticsRepository
from app.services.failure import ValidationFailureService
from app.services.statistics import ValidationStatisticsService
from tests.conftest import make_check, make_execution, make_profile, make_target


def _service(db_session: AsyncSession) -> ValidationStatisticsService:
    return ValidationStatisticsService(
        ValidationStatisticsRepository(db_session),
        ValidationProfileRepository(db_session),
        ValidationExecutionRepository(db_session),
        ValidationFailureRepository(db_session),
        ValidationHistoryRepository(db_session),
    )


class TestValidationStatisticsService:
    async def test_recompute_with_no_data(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        snapshot = await service.recompute(org_id)
        assert snapshot.total_profiles == 0
        assert snapshot.pass_rate == 0.0

    async def test_recompute_counts_profile_and_execution(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        check = await make_check(db_session, organization_id=org_id)
        profile = await make_profile(db_session, organization_id=org_id, check_ids=[check.id])
        target = await make_target(db_session, organization_id=org_id)
        execution = await make_execution(
            db_session, profile, [target], status=ValidationExecutionStatus.PASSED
        )
        execution.started_at = execution.created_at
        execution.finished_at = execution.created_at
        await ValidationExecutionRepository(db_session).update(execution)

        service = _service(db_session)
        snapshot = await service.recompute(org_id)
        assert snapshot.total_profiles == 1
        assert snapshot.total_executions == 1
        assert snapshot.pass_rate == 1.0

    async def test_get_for_org_recomputes_when_missing(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        snapshot = await service.get_for_org(org_id)
        assert snapshot.organization_id == org_id

    async def test_get_for_org_returns_cached_snapshot(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        first = await service.get_for_org(org_id)
        second = await service.get_for_org(org_id)
        assert first.id == second.id

    async def test_recompute_updates_existing_snapshot(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        first = await service.recompute(org_id)
        check = await make_check(db_session, organization_id=org_id)
        await make_profile(db_session, organization_id=org_id, check_ids=[check.id])
        second = await service.recompute(org_id)
        assert first.id == second.id
        assert second.total_profiles == 1

    async def test_top_failures_reflects_unresolved_severity(
        self, db_session: AsyncSession
    ) -> None:
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
            status=ValidationResultStatus.FAILED,
        )
        db_session.add(result)
        await db_session.flush()
        await ValidationFailureService(ValidationFailureRepository(db_session)).record(
            organization_id=org_id,
            result_id=result.id,
            severity=ValidationSeverity.CRITICAL,
            reason="reason",
        )

        service = _service(db_session)
        snapshot = await service.recompute(org_id)
        assert snapshot.top_failures.get("critical") == 1
