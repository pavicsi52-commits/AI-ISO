"""Tests for :class:`app.services.check.ValidationCheckService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationCheckType
from app.repositories.validation_check import ValidationCheckRepository
from app.services.check import ValidationCheckService


def _service(db_session: AsyncSession) -> ValidationCheckService:
    return ValidationCheckService(ValidationCheckRepository(db_session))


class TestValidationCheckService:
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        check = await service.create(
            organization_id=uuid.uuid4(),
            category_id=None,
            check_type=ValidationCheckType.DISK_USAGE,
            name="Disk Usage",
            description=None,
            collector_key="automation_job",
            parameters={"job_id": str(uuid.uuid4())},
            timeout_seconds=30.0,
            retry_count=1,
        )
        fetched = await service.get_by_id(check.id)
        assert fetched.collector_key == "automation_job"

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        await service.create(
            organization_id=org_id,
            category_id=None,
            check_type=ValidationCheckType.CPU,
            name="CPU",
            description=None,
            collector_key="automation_job",
            parameters={},
            timeout_seconds=30.0,
            retry_count=0,
        )
        checks = await service.list_for_org(org_id)
        assert len(checks) == 1

    async def test_list_by_ids_skips_missing(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        check = await service.create(
            organization_id=uuid.uuid4(),
            category_id=None,
            check_type=ValidationCheckType.MEMORY,
            name="Memory",
            description=None,
            collector_key="automation_job",
            parameters={},
            timeout_seconds=30.0,
            retry_count=0,
        )
        resolved = await service.list_by_ids([check.id, uuid.uuid4()])
        assert resolved == [check]

    async def test_list_by_ids_empty_returns_empty(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        assert await service.list_by_ids([]) == []
