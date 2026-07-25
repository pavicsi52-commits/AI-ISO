"""Tests for :class:`app.services.role_assignment.RoleAssignmentService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import SubjectType
from app.models.role import Role
from app.repositories.organization_role import OrganizationRoleRepository
from app.repositories.project_role import ProjectRoleRepository
from app.repositories.role import RoleRepository
from app.repositories.user_role import UserRoleRepository
from app.services.role_assignment import RoleAssignmentService


class _Recorder:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)


def _service(db_session: AsyncSession, recorder: _Recorder | None = None) -> RoleAssignmentService:
    return RoleAssignmentService(
        UserRoleRepository(db_session),
        OrganizationRoleRepository(db_session),
        ProjectRoleRepository(db_session),
        RoleRepository(db_session),
        publish_event=recorder,
    )


async def _make_role(db_session: AsyncSession) -> Role:
    return await RoleRepository(db_session).create(
        Role(name="R", code=f"r-{uuid.uuid4().hex[:8]}", organization_id=DEFAULT_ORGANIZATION_ID)
    )


async def test_assign_global_scope(db_session: AsyncSession) -> None:
    recorder = _Recorder()
    service = _service(db_session, recorder)
    role = await _make_role(db_session)
    user_id = uuid.uuid4()

    assignment = await service.assign(
        user_id,
        role.id,
        scope_type=SubjectType.GLOBAL,
        scope_id=None,
        expires_at=None,
        assigned_by=None,
    )

    assert assignment.scope_type == SubjectType.GLOBAL
    assert any(e.event_name == "RoleAssigned" for e in recorder.events)


async def test_assign_unknown_role_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)

    with pytest.raises(NotFoundError):
        await service.assign(
            uuid.uuid4(),
            uuid.uuid4(),
            scope_type=SubjectType.GLOBAL,
            scope_id=None,
            expires_at=None,
            assigned_by=None,
        )


async def test_assign_duplicate_global_raises_conflict(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    user_id = uuid.uuid4()
    await service.assign(
        user_id,
        role.id,
        scope_type=SubjectType.GLOBAL,
        scope_id=None,
        expires_at=None,
        assigned_by=None,
    )

    with pytest.raises(ConflictError):
        await service.assign(
            user_id,
            role.id,
            scope_type=SubjectType.GLOBAL,
            scope_id=None,
            expires_at=None,
            assigned_by=None,
        )


async def test_assign_organization_scope_requires_scope_id(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)

    with pytest.raises(ValidationError):
        await service.assign(
            uuid.uuid4(),
            role.id,
            scope_type=SubjectType.ORGANIZATION,
            scope_id=None,
            expires_at=None,
            assigned_by=None,
        )


async def test_assign_organization_scope(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    org_id = uuid.uuid4()

    assignment = await service.assign(
        uuid.uuid4(),
        role.id,
        scope_type=SubjectType.ORGANIZATION,
        scope_id=org_id,
        expires_at=None,
        assigned_by=None,
    )

    assert assignment.scope_type == SubjectType.ORGANIZATION
    assert assignment.scope_id == org_id


async def test_assign_project_scope_requires_scope_id(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)

    with pytest.raises(ValidationError):
        await service.assign(
            uuid.uuid4(),
            role.id,
            scope_type=SubjectType.PROJECT,
            scope_id=None,
            expires_at=None,
            assigned_by=None,
        )


async def test_assign_project_scope(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    project_id = uuid.uuid4()

    assignment = await service.assign(
        uuid.uuid4(),
        role.id,
        scope_type=SubjectType.PROJECT,
        scope_id=project_id,
        expires_at=None,
        assigned_by=None,
    )

    assert assignment.scope_type == SubjectType.PROJECT
    assert assignment.scope_id == project_id


async def test_remove_global_assignment(db_session: AsyncSession) -> None:
    recorder = _Recorder()
    service = _service(db_session, recorder)
    role = await _make_role(db_session)
    user_id = uuid.uuid4()
    await service.assign(
        user_id,
        role.id,
        scope_type=SubjectType.GLOBAL,
        scope_id=None,
        expires_at=None,
        assigned_by=None,
    )

    await service.remove(user_id, role.id, scope_type=SubjectType.GLOBAL, scope_id=None)

    assert await service.list_for_user(user_id) == []
    assert any(e.event_name == "RoleRemoved" for e in recorder.events)


async def test_remove_missing_assignment_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)

    with pytest.raises(NotFoundError):
        await service.remove(uuid.uuid4(), role.id, scope_type=SubjectType.GLOBAL, scope_id=None)


async def test_assign_duplicate_organization_raises_conflict(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    user_id, org_id = uuid.uuid4(), uuid.uuid4()
    await service.assign(
        user_id,
        role.id,
        scope_type=SubjectType.ORGANIZATION,
        scope_id=org_id,
        expires_at=None,
        assigned_by=None,
    )

    with pytest.raises(ConflictError):
        await service.assign(
            user_id,
            role.id,
            scope_type=SubjectType.ORGANIZATION,
            scope_id=org_id,
            expires_at=None,
            assigned_by=None,
        )


async def test_assign_duplicate_project_raises_conflict(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    user_id, project_id = uuid.uuid4(), uuid.uuid4()
    await service.assign(
        user_id,
        role.id,
        scope_type=SubjectType.PROJECT,
        scope_id=project_id,
        expires_at=None,
        assigned_by=None,
    )

    with pytest.raises(ConflictError):
        await service.assign(
            user_id,
            role.id,
            scope_type=SubjectType.PROJECT,
            scope_id=project_id,
            expires_at=None,
            assigned_by=None,
        )


async def test_assign_unsupported_scope_raises_validation_error(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)

    with pytest.raises(ValidationError):
        await service.assign(
            uuid.uuid4(),
            role.id,
            scope_type=SubjectType.USER,
            scope_id=None,
            expires_at=None,
            assigned_by=None,
        )


async def test_remove_missing_organization_assignment_raises_not_found(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)

    with pytest.raises(NotFoundError):
        await service.remove(
            uuid.uuid4(), role.id, scope_type=SubjectType.ORGANIZATION, scope_id=uuid.uuid4()
        )


async def test_remove_missing_project_assignment_raises_not_found(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)

    with pytest.raises(NotFoundError):
        await service.remove(
            uuid.uuid4(), role.id, scope_type=SubjectType.PROJECT, scope_id=uuid.uuid4()
        )


async def test_remove_unsupported_scope_raises_validation_error(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)

    with pytest.raises(ValidationError):
        await service.remove(uuid.uuid4(), role.id, scope_type=SubjectType.USER, scope_id=None)


async def test_remove_organization_scope_requires_scope_id(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)

    with pytest.raises(ValidationError):
        await service.remove(
            uuid.uuid4(), role.id, scope_type=SubjectType.ORGANIZATION, scope_id=None
        )


async def test_remove_project_scope_requires_scope_id(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)

    with pytest.raises(ValidationError):
        await service.remove(uuid.uuid4(), role.id, scope_type=SubjectType.PROJECT, scope_id=None)


async def test_remove_organization_scope(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    user_id, org_id = uuid.uuid4(), uuid.uuid4()
    await service.assign(
        user_id,
        role.id,
        scope_type=SubjectType.ORGANIZATION,
        scope_id=org_id,
        expires_at=None,
        assigned_by=None,
    )

    await service.remove(user_id, role.id, scope_type=SubjectType.ORGANIZATION, scope_id=org_id)

    assert await service.list_for_user(user_id) == []


async def test_remove_project_scope(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    user_id, project_id = uuid.uuid4(), uuid.uuid4()
    await service.assign(
        user_id,
        role.id,
        scope_type=SubjectType.PROJECT,
        scope_id=project_id,
        expires_at=None,
        assigned_by=None,
    )

    await service.remove(user_id, role.id, scope_type=SubjectType.PROJECT, scope_id=project_id)

    assert await service.list_for_user(user_id) == []


async def test_list_for_user_aggregates_all_scopes(db_session: AsyncSession) -> None:
    service = _service(db_session)
    role = await _make_role(db_session)
    user_id = uuid.uuid4()
    await service.assign(
        user_id,
        role.id,
        scope_type=SubjectType.GLOBAL,
        scope_id=None,
        expires_at=None,
        assigned_by=None,
    )
    await service.assign(
        user_id,
        role.id,
        scope_type=SubjectType.ORGANIZATION,
        scope_id=uuid.uuid4(),
        expires_at=None,
        assigned_by=None,
    )
    await service.assign(
        user_id,
        role.id,
        scope_type=SubjectType.PROJECT,
        scope_id=uuid.uuid4(),
        expires_at=None,
        assigned_by=None,
    )

    assignments = await service.list_for_user(user_id)

    assert len(assignments) == 3
    assert {a.scope_type for a in assignments} == {
        SubjectType.GLOBAL,
        SubjectType.ORGANIZATION,
        SubjectType.PROJECT,
    }
