"""Tests for :class:`AssetTagService`."""

from __future__ import annotations

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.asset_tag import AssetTagRepository
from app.services.tag import AssetTagService
from tests.conftest import make_asset


def _service(db_session: AsyncSession) -> AssetTagService:
    return AssetTagService(AssetTagRepository(db_session))


async def test_assign_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    tag = await service.assign(asset.id, organization_id=asset.organization_id, label="prod")
    assert tag.label == "prod"
    records = await service.list_for_asset(asset.id)
    assert [r.id for r in records] == [tag.id]


async def test_assign_duplicate_label_conflicts(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    await service.assign(asset.id, organization_id=asset.organization_id, label="prod")
    with pytest.raises(ConflictError):
        await service.assign(asset.id, organization_id=asset.organization_id, label="prod")


async def test_assign_many_skips_existing(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    await service.assign(asset.id, organization_id=asset.organization_id, label="prod")
    assigned = await service.assign_many(
        asset.id, organization_id=asset.organization_id, labels=["prod", "web"]
    )
    assert {t.label for t in assigned} == {"prod", "web"}
    records = await service.list_for_asset(asset.id)
    assert len(records) == 2


async def test_remove(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    tag = await service.assign(asset.id, organization_id=asset.organization_id, label="prod")
    await service.remove(asset.id, tag.id)
    assert await service.list_for_asset(asset.id) == []


async def test_remove_wrong_asset_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset1 = await make_asset(db_session, name="a1")
    asset2 = await make_asset(db_session, name="a2")
    tag = await service.assign(asset1.id, organization_id=asset1.organization_id, label="prod")
    with pytest.raises(NotFoundError):
        await service.remove(asset2.id, tag.id)


__all__: list[str] = []
