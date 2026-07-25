"""Tests for :class:`app.services.role.RoleService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.business import BusinessRuleError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import RoleStatus, RoleType
from app.models.role_permission import RolePermission
from app.repositories.permission import PermissionRepository
from app.repositories.role import RoleRepository
from app.repositories.role_permission import RolePermissionRepository
from app.services.role import RoleService


class _Recorder:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)


def _service(db_session: AsyncSession, recorder: _Recorder | None = None) -> RoleService:
    return RoleService(
        RoleRepository(db_session),
        RolePermissionRepository(db_session),
        publish_event=recorder,
    )


async def test_create_role_publishes_event(db_session: AsyncSession) -> None:
    recorder = _Recorder()
    service = _service(db_session, recorder)

    role = await service.create(
        name="QA",
        code=f"qa-{uuid.uuid4().hex[:8]}",
        description=None,
        role_type=RoleType.CUSTOM,
        parent_role_id=None,
        priority=0,
        project_id=None,
        metadata={},
    )

    assert role.role_type == RoleType.CUSTOM
    assert any(e.event_name == "RoleCreated" for e in recorder.events)


async def test_create_role_with_unknown_parent_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)

    with pytest.raises(NotFoundError):
        await service.create(
            name="QA",
            code=f"qa-{uuid.uuid4().hex[:8]}",
            description=None,
            role_type=RoleType.CUSTOM,
            parent_role_id=uuid.uuid4(),
            priority=0,
            project_id=None,
            metadata={},
        )


async def test_create_role_with_valid_parent(db_session: AsyncSession) -> None:
    service = _service(db_session)
    parent = await service.create(
        name="Parent",
        code=f"parent-{uuid.uuid4().hex[:8]}",
        description=None,
        role_type=RoleType.CUSTOM,
        parent_role_id=None,
        priority=0,
        project_id=None,
        metadata={},
    )

    child = await service.create(
        name="Child",
        code=f"child-{uuid.uuid4().hex[:8]}",
        description=None,
        role_type=RoleType.CUSTOM,
        parent_role_id=parent.id,
        priority=0,
        project_id=None,
        metadata={},
    )

    assert child.parent_role_id == parent.id


async def test_get_by_id_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)

    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_update_role(db_session: AsyncSession) -> None:
    recorder = _Recorder()
    service = _service(db_session, recorder)
    role = await service.create(
        name="Original",
        code=f"r-{uuid.uuid4().hex[:8]}",
        description=None,
        role_type=RoleType.CUSTOM,
        parent_role_id=None,
        priority=0,
        project_id=None,
        metadata={},
    )

    updated = await service.update(
        role.id,
        name="Updated",
        description="New description",
        status=RoleStatus.INACTIVE,
        parent_role_id=None,
        priority=5,
        metadata={"k": "v"},
    )

    assert updated.name == "Updated"
    assert updated.status == RoleStatus.INACTIVE
    assert updated.priority == 5
    assert any(e.event_name == "RoleUpdated" for e in recorder.events)


async def test_update_role_reparent_to_unknown_parent_raises_not_found(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    role = await service.create(
        name="R",
        code=f"r-{uuid.uuid4().hex[:8]}",
        description=None,
        role_type=RoleType.CUSTOM,
        parent_role_id=None,
        priority=0,
        project_id=None,
        metadata={},
    )

    with pytest.raises(NotFoundError):
        await service.update(
            role.id,
            name=role.name,
            description=None,
            status=RoleStatus.ACTIVE,
            parent_role_id=uuid.uuid4(),
            priority=0,
            metadata={},
        )


async def test_update_role_reparent_creates_cycle_raises(db_session: AsyncSession) -> None:
    service = _service(db_session)
    parent = await service.create(
        name="Parent",
        code=f"parent-{uuid.uuid4().hex[:8]}",
        description=None,
        role_type=RoleType.CUSTOM,
        parent_role_id=None,
        priority=0,
        project_id=None,
        metadata={},
    )
    child = await service.create(
        name="Child",
        code=f"child-{uuid.uuid4().hex[:8]}",
        description=None,
        role_type=RoleType.CUSTOM,
        parent_role_id=parent.id,
        priority=0,
        project_id=None,
        metadata={},
    )

    with pytest.raises(BusinessRuleError):
        await service.update(
            parent.id,
            name=parent.name,
            description=None,
            status=RoleStatus.ACTIVE,
            parent_role_id=child.id,
            priority=0,
            metadata={},
        )


async def test_delete_role(db_session: AsyncSession) -> None:
    recorder = _Recorder()
    service = _service(db_session, recorder)
    role = await service.create(
        name="Temp",
        code=f"temp-{uuid.uuid4().hex[:8]}",
        description=None,
        role_type=RoleType.CUSTOM,
        parent_role_id=None,
        priority=0,
        project_id=None,
        metadata={},
    )

    await service.delete(role.id)

    with pytest.raises(NotFoundError):
        await service.get_by_id(role.id)
    assert any(e.event_name == "RoleDeleted" for e in recorder.events)


async def test_delete_system_role_raises_business_rule_error(db_session: AsyncSession) -> None:
    service = _service(db_session)
    platform_admin = await service.get_by_id(uuid.UUID("00000000-0000-0000-0000-000000000101"))
    assert platform_admin.is_system is True

    with pytest.raises(BusinessRuleError):
        await service.delete(platform_admin.id)


async def test_list_all_includes_seeded_roles(db_session: AsyncSession) -> None:
    service = _service(db_session)

    roles = await service.list_all()

    assert len(roles) >= 10


async def test_resolve_effective_permission_ids_aggregates_hierarchy(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    permissions = PermissionRepository(db_session)
    role_permissions = RolePermissionRepository(db_session)

    parent = await service.create(
        name="Parent",
        code=f"parent-{uuid.uuid4().hex[:8]}",
        description=None,
        role_type=RoleType.CUSTOM,
        parent_role_id=None,
        priority=0,
        project_id=None,
        metadata={},
    )
    child = await service.create(
        name="Child",
        code=f"child-{uuid.uuid4().hex[:8]}",
        description=None,
        role_type=RoleType.CUSTOM,
        parent_role_id=parent.id,
        priority=0,
        project_id=None,
        metadata={},
    )
    users_read = await permissions.get_by_code("users:read")
    users_write = await permissions.get_by_code("users:update")
    assert users_read is not None and users_write is not None
    await role_permissions.create(
        RolePermission(
            role_id=parent.id, permission_id=users_read.id, organization_id=DEFAULT_ORGANIZATION_ID
        )
    )
    await role_permissions.create(
        RolePermission(
            role_id=child.id, permission_id=users_write.id, organization_id=DEFAULT_ORGANIZATION_ID
        )
    )

    effective = await service.resolve_effective_permission_ids(child.id)

    assert effective == {users_read.id, users_write.id}
