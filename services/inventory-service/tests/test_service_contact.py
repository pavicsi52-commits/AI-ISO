"""Tests for :class:`AssetContactService`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.asset_contact import AssetContactRepository
from app.services.contact import AssetContactService
from tests.conftest import make_asset


def _service(db_session: AsyncSession) -> AssetContactService:
    return AssetContactService(AssetContactRepository(db_session))


async def test_add_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    contact = await service.add(
        asset.id,
        organization_id=asset.organization_id,
        name="Jane",
        email="jane@example.com",
        phone="555-1234",
        role="on-call",
    )
    assert contact.name == "Jane"
    records = await service.list_for_asset(asset.id)
    assert [r.id for r in records] == [contact.id]


async def test_remove(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    contact = await service.add(asset.id, organization_id=asset.organization_id, name="Jane")
    await service.remove(contact.id)
    assert await service.list_for_asset(asset.id) == []


__all__: list[str] = []
