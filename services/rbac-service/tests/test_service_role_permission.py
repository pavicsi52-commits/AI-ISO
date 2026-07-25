"""Tests for :class:`app.services.role_permission.RolePermissionService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.role import Role
from app.repositories.permission import PermissionRepository
from app.repositories.role import RoleRepository
from app.repositories.role_permission import RolePermissionRepository
from app.services.role_permission import RolePermissionService


def _service(db_session: AsyncSession) -> RolePermissionService:
    return RolePermissionService(
        RolePermissionRepository(db_session),
        RoleRepository(db_session),
        PermissionRepository(db_session),
    )


async def _make_role(db_session: AsyncSession) -> Role:
    return await RoleRepository(db_session).create(
        Role(name="R", code=f"r-{uuid.uuid4().hex[:8]}", organization_id=DEFAULT_ORGANIZATION_ID)
    )


async def test_grant_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    permission = await PermissionRepository(db_session).get_by_code("users:read")
    assert permission is not None

    await service.grant(role.id, permission.id, granted_by=None)
    grants = await service.list_for_role(role.id)

    assert [g.permission_id for g in grants] == [permission.id]


async def test_grant_unknown_role_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    permission = await PermissionRepository(db_session).get_by_code("users:read")
    assert permission is not None

    with pytest.raises(NotFoundError):
        await service.grant(uuid.uuid4(), permission.id, granted_by=None)


async def test_grant_unknown_permission_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)

    with pytest.raises(NotFoundError):
        await service.grant(role.id, uuid.uuid4(), granted_by=None)


async def test_grant_duplicate_raises_conflict(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    permission = await PermissionRepository(db_session).get_by_code("users:read")
    assert permission is not None
    await service.grant(role.id, permission.id, granted_by=None)

    with pytest.raises(ConflictError):
        await service.grant(role.id, permission.id, granted_by=None)


async def test_revoke(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    permission = await PermissionRepository(db_session).get_by_code("users:read")
    assert permission is not None
    await service.grant(role.id, permission.id, granted_by=None)

    await service.revoke(role.id, permission.id)

    assert await service.list_for_role(role.id) == []


async def test_revoke_not_granted_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    permission = await PermissionRepository(db_session).get_by_code("users:read")
    assert permission is not None

    with pytest.raises(NotFoundError):
        await service.revoke(role.id, permission.id)
