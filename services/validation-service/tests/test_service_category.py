"""Tests for :class:`app.services.category.ValidationCategoryService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationType
from app.repositories.validation_category import ValidationCategoryRepository
from app.services.category import ValidationCategoryService


def _service(db_session: AsyncSession) -> ValidationCategoryService:
    return ValidationCategoryService(ValidationCategoryRepository(db_session))


class TestValidationCategoryService:
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        category = await service.create(
            organization_id=uuid.uuid4(),
            name="Security",
            description=None,
            validation_type=ValidationType.SECURITY,
        )
        fetched = await service.get_by_id(category.id)
        assert fetched.validation_type == ValidationType.SECURITY

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        await service.create(
            organization_id=org_id,
            name="Health",
            description=None,
            validation_type=ValidationType.HEALTH,
        )
        categories = await service.list_for_org(org_id)
        assert len(categories) == 1
