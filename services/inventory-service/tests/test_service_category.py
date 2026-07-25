"""Tests for :class:`AssetCategoryService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.asset_category import AssetCategoryRepository
from app.services.category import AssetCategoryService


def _service(db_session: AsyncSession) -> AssetCategoryService:
    return AssetCategoryService(AssetCategoryRepository(db_session))


async def test_create_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    category = await service.create(organization_id=org_id, name="Compute", description="d")
    assert category.name == "Compute"
    records = await service.list_for_org(org_id)
    assert [r.id for r in records] == [category.id]


async def test_create_duplicate_name_conflicts(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    await service.create(organization_id=org_id, name="Compute")
    with pytest.raises(ConflictError):
        await service.create(organization_id=org_id, name="Compute")


async def test_same_name_different_org_allowed(db_session: AsyncSession) -> None:
    service = _service(db_session)
    await service.create(organization_id=uuid.uuid4(), name="Compute")
    category = await service.create(organization_id=uuid.uuid4(), name="Compute")
    assert category.name == "Compute"


async def test_delete(db_session: AsyncSession) -> None:
    service = _service(db_session)
    category = await service.create(organization_id=uuid.uuid4(), name="Compute")
    await service.delete(category.id)
    with pytest.raises(NotFoundError):
        await service.delete(category.id)


__all__: list[str] = []
