"""Tests for :class:`app.services.parameter.AutomationParameterService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.automation_job import AutomationJobRepository
from app.repositories.automation_parameter import AutomationParameterRepository
from app.services.parameter import AutomationParameterService
from tests.conftest import make_job


def _build_service(db_session: AsyncSession) -> AutomationParameterService:
    return AutomationParameterService(
        AutomationParameterRepository(db_session), AutomationJobRepository(db_session)
    )


class TestAutomationParameterService:
    async def test_create_and_list_for_job(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        parameter = await service.create(
            job.id,
            name="hostname",
            parameter_type="string",
            required=True,
            default_value=None,
            description="Target hostname",
        )
        assert parameter.job_id == job.id
        assert parameter.organization_id == job.organization_id

        parameters = await service.list_for_job(job.id)
        assert len(parameters) == 1
        assert parameters[0].name == "hostname"

    async def test_list_for_job_empty(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        assert await service.list_for_job(uuid.uuid4()) == []

    async def test_create_for_missing_job_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.create(
                uuid.uuid4(),
                name="p1",
                parameter_type="string",
                required=False,
                default_value=None,
                description=None,
            )

    async def test_delete(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        parameter = await service.create(
            job.id,
            name="p1",
            parameter_type="string",
            required=False,
            default_value="x",
            description=None,
        )
        await service.delete(parameter.id)
        remaining = await service.list_for_job(job.id)
        assert remaining == []
