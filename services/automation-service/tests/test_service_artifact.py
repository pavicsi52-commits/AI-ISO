"""Tests for :class:`app.services.artifact.AutomationArtifactService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_execution import AutomationExecution
from app.models.enums import ArtifactType, ExecutionMode, ExecutionStatus
from app.repositories.automation_artifact import AutomationArtifactRepository
from app.services.artifact import AutomationArtifactService
from tests.conftest import make_job


def _build_service(db_session: AsyncSession) -> AutomationArtifactService:
    return AutomationArtifactService(AutomationArtifactRepository(db_session))


async def _make_execution(db_session: AsyncSession) -> AutomationExecution:
    job = await make_job(db_session)
    execution = AutomationExecution(
        organization_id=job.organization_id,
        job_id=job.id,
        status=ExecutionStatus.COMPLETED,
        execution_mode=ExecutionMode.MANUAL,
    )
    db_session.add(execution)
    await db_session.flush()
    return execution


class TestAutomationArtifactService:
    async def test_create_and_list_for_execution(self, db_session: AsyncSession) -> None:
        execution = await _make_execution(db_session)
        service = _build_service(db_session)
        artifact = await service.create(
            execution.id,
            organization_id=execution.organization_id,
            artifact_type=ArtifactType.EXECUTION_REPORT,
            name="report.json",
            content={"summary": "ok"},
            checksum="abc123",
        )
        assert artifact.name == "report.json"

        artifacts = await service.list_for_execution(execution.id)
        assert len(artifacts) == 1
        assert artifacts[0].id == artifact.id

    async def test_list_for_execution_empty(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        assert await service.list_for_execution(uuid.uuid4()) == []
