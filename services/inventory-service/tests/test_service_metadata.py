"""Tests for :class:`AssetMetadataService`."""

from __future__ import annotations

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.asset_metadata import AssetMetadataRepository
from app.services.metadata import AssetMetadataService
from tests.conftest import make_asset


def _service(db_session: AsyncSession) -> AssetMetadataService:
    return AssetMetadataService(AssetMetadataRepository(db_session))


async def test_set_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    entry = await service.set(asset.id, organization_id=asset.organization_id, key="k", value="v")
    assert entry.value == "v"
    records = await service.list_for_asset(asset.id)
    assert [r.id for r in records] == [entry.id]


async def test_set_duplicate_key_conflicts(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    await service.set(asset.id, organization_id=asset.organization_id, key="k", value="v")
    with pytest.raises(ConflictError):
        await service.set(asset.id, organization_id=asset.organization_id, key="k", value="v2")


async def test_remove(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    entry = await service.set(asset.id, organization_id=asset.organization_id, key="k", value="v")
    await service.remove(asset.id, entry.id)
    assert await service.list_for_asset(asset.id) == []


async def test_remove_wrong_asset_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset1 = await make_asset(db_session, name="a1")
    asset2 = await make_asset(db_session, name="a2")
    entry = await service.set(asset1.id, organization_id=asset1.organization_id, key="k", value="v")
    with pytest.raises(NotFoundError):
        await service.remove(asset2.id, entry.id)


__all__: list[str] = []
