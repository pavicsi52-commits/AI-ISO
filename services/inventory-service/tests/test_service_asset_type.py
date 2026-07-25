"""Tests for :class:`AssetTypeDefinitionService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.asset_type import AssetTypeDefinitionRepository
from app.services.asset_type import AssetTypeDefinitionService


def _service(db_session: AsyncSession) -> AssetTypeDefinitionService:
    return AssetTypeDefinitionService(AssetTypeDefinitionRepository(db_session))


async def test_create_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    definition = await service.create(
        organization_id=org_id,
        code="virtual_machine",
        name="Virtual Machine",
        description="d",
        category_id=None,
        icon="vm",
        is_system=True,
    )
    assert definition.code == "virtual_machine"
    assert definition.is_system is True
    records = await service.list_for_org(org_id)
    assert [r.id for r in records] == [definition.id]


async def test_create_duplicate_code_conflicts(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    await service.create(organization_id=org_id, code="vm", name="VM")
    with pytest.raises(ConflictError):
        await service.create(organization_id=org_id, code="vm", name="VM 2")


__all__: list[str] = []
