"""Tests for :class:`AssetCustomFieldService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CustomFieldType
from app.repositories.asset_custom_field import AssetCustomFieldRepository
from app.services.custom_field import AssetCustomFieldService


def _service(db_session: AsyncSession) -> AssetCustomFieldService:
    return AssetCustomFieldService(AssetCustomFieldRepository(db_session))


async def test_create_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    field = await service.create(
        organization_id=org_id,
        name="warranty_expiry",
        description="d",
        field_type=CustomFieldType.DATE,
        is_required=True,
        validation_rule={"min": "2020-01-01"},
    )
    assert field.field_type == CustomFieldType.DATE
    assert field.is_required is True
    records = await service.list_for_org(org_id)
    assert [r.id for r in records] == [field.id]


async def test_create_duplicate_name_conflicts(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    await service.create(organization_id=org_id, name="warranty_expiry")
    with pytest.raises(ConflictError):
        await service.create(organization_id=org_id, name="warranty_expiry")


__all__: list[str] = []
