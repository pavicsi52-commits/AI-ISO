"""Tests for :class:`AssetLabelService`."""

from __future__ import annotations

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.asset_label import AssetLabelRepository
from app.services.label import AssetLabelService
from tests.conftest import make_asset


def _service(db_session: AsyncSession) -> AssetLabelService:
    return AssetLabelService(AssetLabelRepository(db_session))


async def test_set_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    label = await service.set(
        asset.id, organization_id=asset.organization_id, key="tier", value="1", namespace="k8s"
    )
    assert label.key == "tier"
    assert label.namespace == "k8s"
    records = await service.list_for_asset(asset.id)
    assert [r.id for r in records] == [label.id]


async def test_set_duplicate_key_conflicts(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    await service.set(asset.id, organization_id=asset.organization_id, key="tier", value="1")
    with pytest.raises(ConflictError):
        await service.set(asset.id, organization_id=asset.organization_id, key="tier", value="2")


async def test_same_key_different_namespace_allowed(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    await service.set(
        asset.id, organization_id=asset.organization_id, key="tier", value="1", namespace="a"
    )
    label = await service.set(
        asset.id, organization_id=asset.organization_id, key="tier", value="2", namespace="b"
    )
    assert label.value == "2"


async def test_remove(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    label = await service.set(
        asset.id, organization_id=asset.organization_id, key="tier", value="1"
    )
    await service.remove(asset.id, label.id)
    assert await service.list_for_asset(asset.id) == []


async def test_remove_wrong_asset_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset1 = await make_asset(db_session, name="a1")
    asset2 = await make_asset(db_session, name="a2")
    label = await service.set(
        asset1.id, organization_id=asset1.organization_id, key="tier", value="1"
    )
    with pytest.raises(NotFoundError):
        await service.remove(asset2.id, label.id)


__all__: list[str] = []
