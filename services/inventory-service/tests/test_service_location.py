"""Tests for :class:`AssetLocationService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.asset_location import AssetLocationRepository
from app.services.location import AssetLocationService


def _service(db_session: AsyncSession) -> AssetLocationService:
    return AssetLocationService(AssetLocationRepository(db_session))


async def test_create_get_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    location = await service.create(
        organization_id=org_id,
        name="DC1",
        country="US",
        region="us-east",
        site="site1",
        building="b1",
        floor="1",
        room="101",
        rack="r1",
        rack_unit="u1",
        gps_latitude=1.23,
        gps_longitude=4.56,
    )
    assert location.name == "DC1"
    fetched = await service.get_by_id(location.id)
    assert fetched.id == location.id
    records = await service.list_for_org(org_id)
    assert [r.id for r in records] == [location.id]


async def test_get_by_id_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_delete(db_session: AsyncSession) -> None:
    service = _service(db_session)
    location = await service.create(organization_id=uuid.uuid4(), name="DC1")
    await service.delete(location.id)
    with pytest.raises(NotFoundError):
        await service.get_by_id(location.id)


__all__: list[str] = []
