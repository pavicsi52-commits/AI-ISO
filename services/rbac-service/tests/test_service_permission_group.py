"""Tests for :class:`app.services.permission_group.PermissionGroupService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PermissionGroupCategory
from app.repositories.permission_group import PermissionGroupRepository
from app.services.permission_group import PermissionGroupService


def _service(db_session: AsyncSession) -> PermissionGroupService:
    return PermissionGroupService(PermissionGroupRepository(db_session))


async def test_create_and_get_permission_group(db_session: AsyncSession) -> None:
    service = _service(db_session)

    group = await service.create(
        name="Infrastructure",
        code=f"infra-{uuid.uuid4().hex[:8]}",
        description="Infra permissions",
        category=PermissionGroupCategory.INFRASTRUCTURE,
        metadata={},
    )
    found = await service.get_by_id(group.id)

    assert found.id == group.id
    assert found.category == PermissionGroupCategory.INFRASTRUCTURE


async def test_get_by_id_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)

    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_list_all(db_session: AsyncSession) -> None:
    service = _service(db_session)
    group = await service.create(
        name="Security",
        code=f"sec-{uuid.uuid4().hex[:8]}",
        description=None,
        category=PermissionGroupCategory.SECURITY,
        metadata={},
    )

    groups = await service.list_all()

    assert group.id in {g.id for g in groups}
