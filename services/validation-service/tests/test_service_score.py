"""Tests for :class:`app.services.score.ValidationScoreService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_score import ValidationScore
from app.repositories.validation_score import ValidationScoreRepository
from app.services.score import ValidationScoreService
from tests.conftest import make_execution, make_profile, make_target


class TestValidationScoreService:
    async def test_get_for_execution_returns_none_when_uncomputed(
        self, db_session: AsyncSession
    ) -> None:
        service = ValidationScoreService(ValidationScoreRepository(db_session))
        assert await service.get_for_execution(uuid.uuid4()) is None

    async def test_get_for_execution_returns_score(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        profile = await make_profile(db_session, organization_id=org_id)
        target = await make_target(db_session, organization_id=org_id)
        execution = await make_execution(db_session, profile, [target])
        db_session.add(
            ValidationScore(
                organization_id=org_id,
                execution_id=execution.id,
                overall_score=87.5,
                computed_at=datetime.now(UTC),
            )
        )
        await db_session.flush()

        service = ValidationScoreService(ValidationScoreRepository(db_session))
        score = await service.get_for_execution(execution.id)
        assert score is not None
        assert score.overall_score == 87.5
