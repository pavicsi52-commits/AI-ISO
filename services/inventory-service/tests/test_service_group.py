"""Tests for :class:`AssetGroupService`, including static vs. dynamic
membership resolution.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import GroupType
from app.repositories.asset import AssetRepository
from app.repositories.asset_group import AssetGroupRepository
from app.services.group import AssetGroupService
from tests.conftest import make_asset


def _service(db_session: AsyncSession) -> AssetGroupService:
    return AssetGroupService(AssetGroupRepository(db_session), AssetRepository(db_session))


async def test_create_static_group_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    asset = await make_asset(db_session, organization_id=org_id)
    group = await service.create(organization_id=org_id, name="static", member_asset_ids=[asset.id])
    assert group.group_type == GroupType.STATIC
    records = await service.list_for_org(org_id)
    assert [r.id for r in records] == [group.id]


async def test_create_duplicate_name_conflicts(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    await service.create(organization_id=org_id, name="g1")
    with pytest.raises(ConflictError):
        await service.create(organization_id=org_id, name="g1")


async def test_resolve_members_static(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    asset1 = await make_asset(db_session, organization_id=org_id, name="a1")
    asset2 = await make_asset(db_session, organization_id=org_id, name="a2")
    group = await service.create(
        organization_id=org_id, name="static", member_asset_ids=[asset1.id, asset2.id]
    )
    members = await service.resolve_members(group.id)
    assert {m.id for m in members} == {asset1.id, asset2.id}


async def test_resolve_members_dynamic_rule(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    prod = await make_asset(db_session, organization_id=org_id, name="prod-1")
    prod.environment = "production"
    other = await make_asset(db_session, organization_id=org_id, name="dev-1")
    other.environment = "development"
    await db_session.flush()

    group = await service.create(
        organization_id=org_id,
        name="prod-only",
        group_type=GroupType.DYNAMIC,
        rule={"field": "environment", "operator": "eq", "value": "production"},
    )
    members = await service.resolve_members(group.id)
    assert [m.id for m in members] == [prod.id]


async def test_resolve_members_rule_based_ne_operator(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    prod = await make_asset(db_session, organization_id=org_id, name="prod-1")
    prod.environment = "production"
    other = await make_asset(db_session, organization_id=org_id, name="dev-1")
    other.environment = "development"
    await db_session.flush()

    group = await service.create(
        organization_id=org_id,
        name="non-prod",
        group_type=GroupType.RULE_BASED,
        rule={"field": "environment", "operator": "ne", "value": "production"},
    )
    members = await service.resolve_members(group.id)
    assert [m.id for m in members] == [other.id]


async def test_resolve_members_rule_unknown_field_matches_nothing(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    await make_asset(db_session, organization_id=org_id)
    group = await service.create(
        organization_id=org_id,
        name="bad-rule",
        group_type=GroupType.DYNAMIC,
        rule={"field": "nonexistent_field", "operator": "eq", "value": "x"},
    )
    assert await service.resolve_members(group.id) == []


async def test_resolve_members_rule_unknown_operator_matches_nothing(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    asset = await make_asset(db_session, organization_id=org_id)
    asset.environment = "production"
    await db_session.flush()
    group = await service.create(
        organization_id=org_id,
        name="bad-op",
        group_type=GroupType.DYNAMIC,
        rule={"field": "environment", "operator": "contains", "value": "production"},
    )
    assert await service.resolve_members(group.id) == []


async def test_add_and_remove_member(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    asset = await make_asset(db_session, organization_id=org_id)
    group = await service.create(organization_id=org_id, name="static")
    await service.add_member(group.id, asset.id)
    members = await service.resolve_members(group.id)
    assert [m.id for m in members] == [asset.id]

    await service.remove_member(group.id, asset.id)
    assert await service.resolve_members(group.id) == []


async def test_add_member_idempotent(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    asset = await make_asset(db_session, organization_id=org_id)
    group = await service.create(organization_id=org_id, name="static")
    await service.add_member(group.id, asset.id)
    await service.add_member(group.id, asset.id)
    members = await service.resolve_members(group.id)
    assert len(members) == 1


async def test_delete(db_session: AsyncSession) -> None:
    service = _service(db_session)
    group = await service.create(organization_id=uuid.uuid4(), name="g1")
    await service.delete(group.id)
    with pytest.raises(NotFoundError):
        await service.delete(group.id)


__all__: list[str] = []
