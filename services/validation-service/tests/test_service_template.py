"""Tests for :class:`app.services.template.ValidationTemplateService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationProfileType
from app.repositories.validation_template import ValidationTemplateRepository
from app.services.template import ValidationTemplateService


def _service(db_session: AsyncSession) -> ValidationTemplateService:
    return ValidationTemplateService(ValidationTemplateRepository(db_session))


class TestValidationTemplateService:
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        template = await service.create(
            organization_id=uuid.uuid4(),
            name="Baseline Security",
            description="A starter security profile.",
            profile_type=ValidationProfileType.SECURITY,
            template_content={"check_ids": []},
            authored_by="admin",
        )
        fetched = await service.get_by_id(template.id)
        assert fetched.name == "Baseline Security"

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        await service.create(
            organization_id=org_id,
            name="Template A",
            description=None,
            profile_type=ValidationProfileType.HEALTH,
            template_content={},
            authored_by=None,
        )
        templates = await service.list_for_org(org_id)
        assert len(templates) == 1
