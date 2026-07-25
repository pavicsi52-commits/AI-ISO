"""Tests for :class:`AssetClassService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_category import AssetCategory
from app.repositories.asset_class import AssetClassRepository
from app.services.asset_class import AssetClassService


def _service(db_session: AsyncSession) -> AssetClassService:
    return AssetClassService(AssetClassRepository(db_session))


async def _make_category(db_session: AsyncSession, *, organization_id: uuid.UUID) -> AssetCategory:
    category = AssetCategory(organization_id=organization_id, name="Compute")
    db_session.add(category)
    await db_session.flush()
    return category


async def test_create_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    category = await _make_category(db_session, organization_id=org_id)
    asset_class = await service.create(
        category_id=category.id, organization_id=org_id, name="Server", description="d"
    )
    assert asset_class.name == "Server"
    records = await service.list_for_category(category.id)
    assert [r.id for r in records] == [asset_class.id]


async def test_create_duplicate_name_in_category_conflicts(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    category = await _make_category(db_session, organization_id=org_id)
    await service.create(category_id=category.id, organization_id=org_id, name="Server")
    with pytest.raises(ConflictError):
        await service.create(category_id=category.id, organization_id=org_id, name="Server")


async def test_delete(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    category = await _make_category(db_session, organization_id=org_id)
    asset_class = await service.create(
        category_id=category.id, organization_id=org_id, name="Server"
    )
    await service.delete(asset_class.id)


__all__: list[str] = []
