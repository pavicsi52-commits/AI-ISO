"""Tests for :class:`app.services.history.ValidationHistoryService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationExecutionStatus
from app.repositories.validation_history import ValidationHistoryRepository
from app.services.history import ValidationHistoryService
from tests.conftest import make_execution, make_profile, make_target


class TestValidationHistoryService:
    async def test_record_and_list_for_target(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        profile = await make_profile(db_session, organization_id=org_id)
        target = await make_target(db_session, organization_id=org_id)
        execution = await make_execution(db_session, profile, [target])
        service = ValidationHistoryService(ValidationHistoryRepository(db_session))
        await service.record(
            organization_id=org_id,
            target_id=target.id,
            execution_id=execution.id,
            status=ValidationExecutionStatus.PASSED,
            score=95.0,
        )
        history = await service.list_for_target(target.id)
        assert len(history) == 1
        assert history[0].score == 95.0
