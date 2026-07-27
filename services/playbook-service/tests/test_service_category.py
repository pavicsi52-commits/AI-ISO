"""Tests for :class:`app.services.category.PlaybookCategoryService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.playbook_category import PlaybookCategoryRepository
from app.services.category import PlaybookCategoryService


def _build_service(db_session: AsyncSession) -> PlaybookCategoryService:
    return PlaybookCategoryService(PlaybookCategoryRepository(db_session))


class TestPlaybookCategoryService:
    async def test_create_and_get_by_id(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        category = await service.create(
            organization_id=uuid.uuid4(), name="networking", description="Network automation"
        )
        fetched = await service.get_by_id(category.id)
        assert fetched.name == "networking"

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        await service.create(organization_id=org_id, name="c1", description=None)
        await service.create(organization_id=org_id, name="c2", description=None)
        categories = await service.list_for_org(org_id)
        assert {c.name for c in categories} == {"c1", "c2"}

    async def test_delete(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        category = await service.create(organization_id=uuid.uuid4(), name="c1", description=None)
        await service.delete(category.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(category.id)
