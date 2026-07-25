"""Tests for :class:`AssetAttributeService`, including
``_validate_typed_value``'s branch for every :class:`CustomFieldType`.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_custom_field import AssetCustomField
from app.models.enums import CustomFieldType
from app.repositories.asset_attribute import AssetAttributeRepository
from app.repositories.asset_custom_field import AssetCustomFieldRepository
from app.services.attribute import AssetAttributeService
from tests.conftest import make_asset


def _service(db_session: AsyncSession) -> AssetAttributeService:
    return AssetAttributeService(
        AssetAttributeRepository(db_session), AssetCustomFieldRepository(db_session)
    )


async def _make_field(
    db_session: AsyncSession, *, organization_id: uuid.UUID, field_type: CustomFieldType
) -> AssetCustomField:
    field = AssetCustomField(
        organization_id=organization_id, name=f"field-{field_type.value}", field_type=field_type
    )
    db_session.add(field)
    await db_session.flush()
    return field


@pytest.mark.parametrize(
    ("field_type", "value"),
    [
        (CustomFieldType.STRING, "anything"),
        (CustomFieldType.INTEGER, "42"),
        (CustomFieldType.FLOAT, "3.14"),
        (CustomFieldType.BOOLEAN, "true"),
        (CustomFieldType.DATE, "2024-01-01"),
        (CustomFieldType.JSON, '{"a": 1}'),
    ],
)
async def test_set_valid_value(
    db_session: AsyncSession, field_type: CustomFieldType, value: str
) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    field = await _make_field(
        db_session, organization_id=asset.organization_id, field_type=field_type
    )
    attribute = await service.set(
        asset.id, organization_id=asset.organization_id, custom_field_id=field.id, value=value
    )
    assert attribute.value == value


@pytest.mark.parametrize(
    ("field_type", "value"),
    [
        (CustomFieldType.INTEGER, "not-an-int"),
        (CustomFieldType.FLOAT, "not-a-float"),
        (CustomFieldType.BOOLEAN, "not-a-bool"),
        (CustomFieldType.DATE, "not-a-date"),
        (CustomFieldType.JSON, "not-json"),
    ],
)
async def test_set_invalid_value_rejected(
    db_session: AsyncSession, field_type: CustomFieldType, value: str
) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    field = await _make_field(
        db_session, organization_id=asset.organization_id, field_type=field_type
    )
    with pytest.raises(ValidationError):
        await service.set(
            asset.id, organization_id=asset.organization_id, custom_field_id=field.id, value=value
        )


async def test_set_unknown_field_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    with pytest.raises(NotFoundError):
        await service.set(
            asset.id,
            organization_id=asset.organization_id,
            custom_field_id=uuid.uuid4(),
            value="x",
        )


async def test_set_updates_existing(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    field = await _make_field(
        db_session, organization_id=asset.organization_id, field_type=CustomFieldType.STRING
    )
    first = await service.set(
        asset.id, organization_id=asset.organization_id, custom_field_id=field.id, value="a"
    )
    second = await service.set(
        asset.id, organization_id=asset.organization_id, custom_field_id=field.id, value="b"
    )
    assert first.id == second.id
    records = await service.list_for_asset(asset.id)
    assert len(records) == 1
    assert records[0].value == "b"


async def test_remove(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    field = await _make_field(
        db_session, organization_id=asset.organization_id, field_type=CustomFieldType.STRING
    )
    attribute = await service.set(
        asset.id, organization_id=asset.organization_id, custom_field_id=field.id, value="a"
    )
    await service.remove(asset.id, attribute.id)
    assert await service.list_for_asset(asset.id) == []


async def test_remove_wrong_asset_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset1 = await make_asset(db_session, name="a1")
    asset2 = await make_asset(db_session, name="a2")
    field = await _make_field(
        db_session, organization_id=asset1.organization_id, field_type=CustomFieldType.STRING
    )
    attribute = await service.set(
        asset1.id, organization_id=asset1.organization_id, custom_field_id=field.id, value="a"
    )
    with pytest.raises(NotFoundError):
        await service.remove(asset2.id, attribute.id)


__all__: list[str] = []
