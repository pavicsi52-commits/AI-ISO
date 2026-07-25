"""Tests for the RBAC service's repositories, against real Postgres.

The seed migration's 10 system roles / 320 permissions / 871 grants
are already present in every test's SAVEPOINT-isolated session (see
``tests/conftest.py``'s module docstring) -- several tests below
exercise lookups against that seeded data directly rather than
creating their own fixtures for it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.authorization_audit import AuthorizationAuditEntry
from app.models.authorization_policy import AuthorizationPolicy
from app.models.enums import (
    AuthorizationDecision,
    PermissionAction,
    PolicyConditionType,
    ResourceType,
    RoleType,
    SubjectType,
)
from app.models.organization_role import OrganizationRole
from app.models.permission_cache import PermissionCacheEntry
from app.models.permission_group import PermissionGroup
from app.models.policy_assignment import PolicyAssignment
from app.models.policy_condition import PolicyCondition
from app.models.project_role import ProjectRole
from app.models.resource_permission import ResourcePermission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user_role import UserRole
from app.repositories.authorization_audit import AuthorizationAuditRepository
from app.repositories.authorization_policy import AuthorizationPolicyRepository
from app.repositories.organization_role import OrganizationRoleRepository
from app.repositories.permission import PermissionRepository
from app.repositories.permission_cache import PermissionCacheRepository
from app.repositories.permission_group import PermissionGroupRepository
from app.repositories.policy_assignment import PolicyAssignmentRepository
from app.repositories.policy_condition import PolicyConditionRepository
from app.repositories.project_role import ProjectRoleRepository
from app.repositories.resource_permission import ResourcePermissionRepository
from app.repositories.role import RoleRepository
from app.repositories.role_permission import RolePermissionRepository
from app.repositories.user_role import UserRoleRepository

_ORG = DEFAULT_ORGANIZATION_ID


async def test_role_repository_get_by_code_finds_seeded_system_role(
    db_session: AsyncSession,
) -> None:
    repo = RoleRepository(db_session)

    role = await repo.get_by_code("platform_administrator")

    assert role is not None
    assert role.is_system is True
    assert role.role_type == RoleType.SYSTEM


async def test_role_repository_list_all_includes_seeded_roles(db_session: AsyncSession) -> None:
    repo = RoleRepository(db_session)

    roles = await repo.list_all()

    assert len(roles) >= 10
    assert {r.code for r in roles} >= {"viewer", "auditor", "operator"}


async def test_role_repository_list_children(db_session: AsyncSession) -> None:
    repo = RoleRepository(db_session)
    parent = await repo.create(
        Role(name="Parent", code=f"parent-{uuid.uuid4().hex[:8]}", organization_id=_ORG)
    )
    child = await repo.create(
        Role(
            name="Child",
            code=f"child-{uuid.uuid4().hex[:8]}",
            parent_role_id=parent.id,
            organization_id=_ORG,
        )
    )

    children = await repo.list_children(parent.id)

    assert [c.id for c in children] == [child.id]


async def test_permission_repository_get_by_code_finds_seeded_permission(
    db_session: AsyncSession,
) -> None:
    repo = PermissionRepository(db_session)

    permission = await repo.get_by_code("users:read")

    assert permission is not None
    assert permission.resource == ResourceType.USERS
    assert permission.action == PermissionAction.READ


async def test_permission_repository_list_by_resource(db_session: AsyncSession) -> None:
    repo = PermissionRepository(db_session)

    permissions = await repo.list_by_resource(ResourceType.USERS)

    assert len(permissions) == 16  # one per PermissionAction
    assert all(p.resource == ResourceType.USERS for p in permissions)


async def test_permission_repository_list_by_ids(db_session: AsyncSession) -> None:
    repo = PermissionRepository(db_session)
    seeded = await repo.get_by_code("users:read")
    assert seeded is not None

    found = await repo.list_by_ids([seeded.id])

    assert [p.id for p in found] == [seeded.id]


async def test_permission_repository_list_all(db_session: AsyncSession) -> None:
    repo = PermissionRepository(db_session)

    permissions = await repo.list_all()

    assert len(permissions) == 320


async def test_permission_group_repository_lookups(db_session: AsyncSession) -> None:
    repo = PermissionGroupRepository(db_session)
    group = await repo.create(
        PermissionGroup(name="Infra", code=f"infra-{uuid.uuid4().hex[:8]}", organization_id=_ORG)
    )

    found = await repo.get_by_code(group.code)
    all_groups = await repo.list_all()

    assert found is not None
    assert found.id == group.id
    assert group.id in {g.id for g in all_groups}


async def test_role_permission_repository_lookups(db_session: AsyncSession) -> None:
    roles = RoleRepository(db_session)
    permissions = PermissionRepository(db_session)
    repo = RolePermissionRepository(db_session)
    role = await roles.create(
        Role(name="R", code=f"r-{uuid.uuid4().hex[:8]}", organization_id=_ORG)
    )
    permission = await permissions.get_by_code("users:read")
    assert permission is not None
    grant = await repo.create(
        RolePermission(role_id=role.id, permission_id=permission.id, organization_id=_ORG)
    )

    found = await repo.get(role.id, permission.id)
    listed = await repo.list_for_role(role.id)

    assert found is not None
    assert found.id == grant.id
    assert [g.id for g in listed] == [grant.id]


async def test_user_role_repository_lookups(db_session: AsyncSession) -> None:
    roles = RoleRepository(db_session)
    repo = UserRoleRepository(db_session)
    role = await roles.create(
        Role(name="R", code=f"r-{uuid.uuid4().hex[:8]}", organization_id=_ORG)
    )
    user_id = uuid.uuid4()
    assignment = await repo.create(UserRole(user_id=user_id, role_id=role.id, organization_id=_ORG))

    found = await repo.get(user_id, role.id)
    listed = await repo.list_for_user(user_id)

    assert found is not None and found.id == assignment.id
    assert [a.id for a in listed] == [assignment.id]


async def test_organization_role_repository_lookups(db_session: AsyncSession) -> None:
    roles = RoleRepository(db_session)
    repo = OrganizationRoleRepository(db_session)
    role = await roles.create(
        Role(name="R", code=f"r-{uuid.uuid4().hex[:8]}", organization_id=_ORG)
    )
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    assignment = await repo.create(
        OrganizationRole(user_id=user_id, role_id=role.id, organization_id=org_id)
    )

    found = await repo.get(user_id, role.id, org_id)
    listed = await repo.list_for_user(user_id)

    assert found is not None and found.id == assignment.id
    assert [a.id for a in listed] == [assignment.id]


async def test_project_role_repository_lookups(db_session: AsyncSession) -> None:
    roles = RoleRepository(db_session)
    repo = ProjectRoleRepository(db_session)
    role = await roles.create(
        Role(name="R", code=f"r-{uuid.uuid4().hex[:8]}", organization_id=_ORG)
    )
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    assignment = await repo.create(
        ProjectRole(user_id=user_id, role_id=role.id, project_id=project_id, organization_id=_ORG)
    )

    found = await repo.get(user_id, role.id, project_id)
    listed = await repo.list_for_user(user_id)

    assert found is not None and found.id == assignment.id
    assert [a.id for a in listed] == [assignment.id]


async def test_resource_permission_repository_lookups(db_session: AsyncSession) -> None:
    permissions = PermissionRepository(db_session)
    repo = ResourcePermissionRepository(db_session)
    permission = await permissions.get_by_code("reports:read")
    assert permission is not None
    resource_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    grant = await repo.create(
        ResourcePermission(
            resource_type=ResourceType.REPORTS,
            resource_id=resource_id,
            subject_type=SubjectType.USER,
            subject_id=subject_id,
            permission_id=permission.id,
            organization_id=_ORG,
        )
    )

    for_resource = await repo.list_for_resource(ResourceType.REPORTS, resource_id)
    for_subject = await repo.list_for_subject(SubjectType.USER, subject_id)

    assert [g.id for g in for_resource] == [grant.id]
    assert [g.id for g in for_subject] == [grant.id]


async def test_authorization_policy_repository_lookups(db_session: AsyncSession) -> None:
    repo = AuthorizationPolicyRepository(db_session)
    policy = await repo.create(
        AuthorizationPolicy(
            name="P", code=f"p-{uuid.uuid4().hex[:8]}", priority=500, organization_id=_ORG
        )
    )

    found = await repo.get_by_code(policy.code)
    active = await repo.list_active()

    assert found is not None and found.id == policy.id
    assert active[0].priority >= active[-1].priority  # highest priority first
    assert policy.id in {p.id for p in active}


async def test_policy_condition_repository_list_for_policy(db_session: AsyncSession) -> None:
    policies = AuthorizationPolicyRepository(db_session)
    repo = PolicyConditionRepository(db_session)
    policy = await policies.create(
        AuthorizationPolicy(name="P", code=f"p-{uuid.uuid4().hex[:8]}", organization_id=_ORG)
    )
    condition = await repo.create(
        PolicyCondition(
            policy_id=policy.id,
            condition_type=PolicyConditionType.CUSTOM,
            operator="equals",
            organization_id=_ORG,
        )
    )

    listed = await repo.list_for_policy(policy.id)

    assert [c.id for c in listed] == [condition.id]


async def test_policy_assignment_repository_list_applicable(db_session: AsyncSession) -> None:
    policies = AuthorizationPolicyRepository(db_session)
    repo = PolicyAssignmentRepository(db_session)
    policy = await policies.create(
        AuthorizationPolicy(name="P", code=f"p-{uuid.uuid4().hex[:8]}", organization_id=_ORG)
    )
    user_id = uuid.uuid4()
    user_assignment = await repo.create(
        PolicyAssignment(
            policy_id=policy.id,
            subject_type=SubjectType.USER,
            subject_id=user_id,
            organization_id=_ORG,
        )
    )

    for_policy = await repo.list_for_policy(policy.id)
    applicable = await repo.list_applicable(subject_type=SubjectType.USER, subject_id=user_id)
    not_applicable = await repo.list_applicable(
        subject_type=SubjectType.USER, subject_id=uuid.uuid4()
    )

    assert [a.id for a in for_policy] == [user_assignment.id]
    assert user_assignment.id in {a.id for a in applicable}
    assert user_assignment.id not in {a.id for a in not_applicable}


async def test_policy_assignment_repository_global_applies_to_everyone(
    db_session: AsyncSession,
) -> None:
    policies = AuthorizationPolicyRepository(db_session)
    repo = PolicyAssignmentRepository(db_session)
    policy = await policies.create(
        AuthorizationPolicy(name="P", code=f"p-{uuid.uuid4().hex[:8]}", organization_id=_ORG)
    )
    global_assignment = await repo.create(
        PolicyAssignment(
            policy_id=policy.id,
            subject_type=SubjectType.GLOBAL,
            subject_id=None,
            organization_id=_ORG,
        )
    )

    applicable = await repo.list_applicable(subject_type=SubjectType.USER, subject_id=uuid.uuid4())

    assert global_assignment.id in {a.id for a in applicable}


async def test_permission_cache_repository_get_for_user(db_session: AsyncSession) -> None:
    repo = PermissionCacheRepository(db_session)
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    entry = await repo.create(
        PermissionCacheEntry(
            user_id=user_id,
            permissions=["users:read"],
            computed_at=now,
            expires_at=now + timedelta(minutes=5),
            organization_id=_ORG,
        )
    )

    found = await repo.get_for_user(user_id, _ORG, None)

    assert found is not None
    assert found.id == entry.id


async def test_authorization_audit_repository_list_recent_for_user(
    db_session: AsyncSession,
) -> None:
    repo = AuthorizationAuditRepository(db_session)
    user_id = uuid.uuid4()
    for _ in range(3):
        await repo.create(
            AuthorizationAuditEntry(
                user_id=user_id,
                action="read",
                decision=AuthorizationDecision.ALLOW,
                organization_id=_ORG,
            )
        )

    recent = await repo.list_recent_for_user(user_id, limit=2)

    assert len(recent) == 2
    assert all(e.user_id == user_id for e in recent)
