"""Tests for :class:`app.services.target.ValidationTargetService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationTargetType
from app.repositories.validation_target import ValidationTargetRepository
from app.services.target import ValidationTargetService


def _service(db_session: AsyncSession) -> ValidationTargetService:
    return ValidationTargetService(ValidationTargetRepository(db_session))


class TestValidationTargetService:
    async def test_get_or_create_creates_new_target(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        target = await service.get_or_create(
            organization_id=uuid.uuid4(),
            project_id=None,
            target_type=ValidationTargetType.PHYSICAL_SERVER,
            external_id="server-1",
            name="Server One",
            target_metadata={"host": "10.0.0.1"},
        )
        assert target.external_id == "server-1"

    async def test_get_or_create_reuses_existing_target(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        first = await service.get_or_create(
            organization_id=org_id,
            project_id=None,
            target_type=ValidationTargetType.PHYSICAL_SERVER,
            external_id="server-1",
            name="Server One",
            target_metadata={"host": "10.0.0.1"},
        )
        second = await service.get_or_create(
            organization_id=org_id,
            project_id=None,
            target_type=ValidationTargetType.PHYSICAL_SERVER,
            external_id="server-1",
            name="Server One Renamed",
            target_metadata={"host": "10.0.0.2"},
        )
        assert second.id == first.id
        assert second.name == "Server One Renamed"
        assert second.target_metadata["host"] == "10.0.0.2"

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_by_ids(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        target = await service.get_or_create(
            organization_id=uuid.uuid4(),
            project_id=None,
            target_type=ValidationTargetType.VIRTUAL_MACHINE,
            external_id="vm-1",
            name="VM One",
            target_metadata={},
        )
        resolved = await service.list_by_ids([target.id])
        assert resolved == [target]

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        await service.get_or_create(
            organization_id=org_id,
            project_id=None,
            target_type=ValidationTargetType.CONTAINER,
            external_id="container-1",
            name="Container One",
            target_metadata={},
        )
        targets = await service.list_for_org(org_id)
        assert len(targets) == 1
