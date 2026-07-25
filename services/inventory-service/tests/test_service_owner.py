"""Tests for :class:`AssetOwnerService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OwnerType
from app.repositories.asset_owner import AssetOwnerRepository
from app.services.owner import AssetOwnerService
from tests.conftest import make_asset


def _service(db_session: AsyncSession) -> AssetOwnerService:
    return AssetOwnerService(AssetOwnerRepository(db_session))


async def test_assign_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    principal_id = uuid.uuid4()
    owner = await service.assign(
        asset.id,
        organization_id=asset.organization_id,
        owner_type=OwnerType.BUSINESS_OWNER,
        principal_id=principal_id,
        name="Jane",
    )
    assert owner.owner_type == OwnerType.BUSINESS_OWNER
    records = await service.list_for_asset(asset.id)
    assert [r.id for r in records] == [owner.id]


async def test_assign_replaces_existing_role(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    first = await service.assign(
        asset.id, organization_id=asset.organization_id, owner_type=OwnerType.VENDOR, name="A"
    )
    second = await service.assign(
        asset.id, organization_id=asset.organization_id, owner_type=OwnerType.VENDOR, name="B"
    )
    assert first.id == second.id
    records = await service.list_for_asset(asset.id)
    assert len(records) == 1
    assert records[0].name == "B"


async def test_remove(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    owner = await service.assign(
        asset.id, organization_id=asset.organization_id, owner_type=OwnerType.DEPARTMENT
    )
    await service.remove(asset.id, owner.id)
    assert await service.list_for_asset(asset.id) == []


async def test_remove_wrong_asset_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset1 = await make_asset(db_session, name="a1")
    asset2 = await make_asset(db_session, name="a2")
    owner = await service.assign(
        asset1.id, organization_id=asset1.organization_id, owner_type=OwnerType.DEPARTMENT
    )
    with pytest.raises(NotFoundError):
        await service.remove(asset2.id, owner.id)


__all__: list[str] = []
