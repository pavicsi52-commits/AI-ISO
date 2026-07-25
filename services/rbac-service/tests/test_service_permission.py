"""Tests for :class:`app.services.permission.PermissionService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from shared_core.security.rbac import PermissionScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PermissionAction, PermissionStatus, ResourceType
from app.repositories.permission import PermissionRepository
from app.services.permission import PermissionService


class _Recorder:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)


def _service(db_session: AsyncSession, recorder: _Recorder | None = None) -> PermissionService:
    return PermissionService(PermissionRepository(db_session), publish_event=recorder)


async def test_create_permission_publishes_event(db_session: AsyncSession) -> None:
    recorder = _Recorder()
    service = _service(db_session, recorder)

    permission = await service.create(
        name="Custom Read",
        code=f"custom-{uuid.uuid4().hex[:8]}",
        description=None,
        category=None,
        resource=ResourceType.REPORTS,
        action=PermissionAction.READ,
        scope=PermissionScope.GLOBAL,
        permission_group_id=None,
        metadata={},
    )

    assert permission.resource == ResourceType.REPORTS
    assert any(e.event_name == "PermissionCreated" for e in recorder.events)


async def test_get_by_id_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)

    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_update_permission(db_session: AsyncSession) -> None:
    recorder = _Recorder()
    service = _service(db_session, recorder)
    permission = await service.create(
        name="Custom",
        code=f"custom-{uuid.uuid4().hex[:8]}",
        description=None,
        category=None,
        resource=ResourceType.REPORTS,
        action=PermissionAction.READ,
        scope=PermissionScope.GLOBAL,
        permission_group_id=None,
        metadata={},
    )

    updated = await service.update(
        permission.id,
        name="Renamed",
        description="desc",
        category="cat",
        status=PermissionStatus.DEPRECATED,
        permission_group_id=None,
        metadata={"k": "v"},
    )

    assert updated.name == "Renamed"
    assert updated.status == PermissionStatus.DEPRECATED
    assert updated.version == 2
    assert any(e.event_name == "PermissionUpdated" for e in recorder.events)


async def test_delete_permission(db_session: AsyncSession) -> None:
    recorder = _Recorder()
    service = _service(db_session, recorder)
    permission = await service.create(
        name="Custom",
        code=f"custom-{uuid.uuid4().hex[:8]}",
        description=None,
        category=None,
        resource=ResourceType.REPORTS,
        action=PermissionAction.READ,
        scope=PermissionScope.GLOBAL,
        permission_group_id=None,
        metadata={},
    )

    await service.delete(permission.id)

    with pytest.raises(NotFoundError):
        await service.get_by_id(permission.id)
    assert any(e.event_name == "PermissionDeleted" for e in recorder.events)


async def test_list_all_includes_seeded_catalog(db_session: AsyncSession) -> None:
    service = _service(db_session)

    permissions = await service.list_all()

    assert len(permissions) >= 320
