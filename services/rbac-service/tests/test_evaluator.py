"""Tests for :class:`app.evaluators.authorization_evaluator.AuthorizationEvaluator`.

The seeded ``viewer`` role (read on every resource) is used as a real,
already-persisted role wherever a simple baseline grant is needed,
alongside purpose-built custom roles/policies/resource grants for the
precedence tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.evaluators.authorization_evaluator import AuthorizationEvaluator
from app.models.enums import (
    AuthorizationDecision,
    PermissionAction,
    PolicyConditionType,
    PolicyEffect,
    ResourceType,
    SubjectType,
)
from app.models.organization_role import OrganizationRole
from app.models.project_role import ProjectRole
from app.models.role import Role
from app.models.user_role import UserRole
from app.repositories.authorization_audit import AuthorizationAuditRepository
from app.repositories.authorization_policy import AuthorizationPolicyRepository
from app.repositories.organization_role import OrganizationRoleRepository
from app.repositories.permission import PermissionRepository
from app.repositories.policy_assignment import PolicyAssignmentRepository
from app.repositories.policy_condition import PolicyConditionRepository
from app.repositories.project_role import ProjectRoleRepository
from app.repositories.resource_permission import ResourcePermissionRepository
from app.repositories.role import RoleRepository
from app.repositories.role_permission import RolePermissionRepository
from app.repositories.user_role import UserRoleRepository
from app.services.permission import PermissionService
from app.services.policy import ConditionInput, PolicyService
from app.services.resource_authorization import ResourceAuthorizationService
from app.services.role import RoleService

VIEWER_ROLE_ID = uuid.UUID("00000000-0000-0000-0000-000000000107")


def _policy_service(db_session: AsyncSession) -> PolicyService:
    return PolicyService(
        AuthorizationPolicyRepository(db_session),
        PolicyConditionRepository(db_session),
        PolicyAssignmentRepository(db_session),
    )


def _resource_service(db_session: AsyncSession) -> ResourceAuthorizationService:
    return ResourceAuthorizationService(ResourcePermissionRepository(db_session))


def _evaluator(db_session: AsyncSession) -> AuthorizationEvaluator:
    roles = RoleService(RoleRepository(db_session), RolePermissionRepository(db_session))
    return AuthorizationEvaluator(
        UserRoleRepository(db_session),
        OrganizationRoleRepository(db_session),
        ProjectRoleRepository(db_session),
        PermissionRepository(db_session),
        PolicyAssignmentRepository(db_session),
        roles,
        _policy_service(db_session),
        _resource_service(db_session),
        AuthorizationAuditRepository(db_session),
    )


async def _assign_viewer(db_session: AsyncSession, user_id: uuid.UUID) -> None:
    await UserRoleRepository(db_session).create(
        UserRole(user_id=user_id, role_id=VIEWER_ROLE_ID, organization_id=DEFAULT_ORGANIZATION_ID)
    )


async def test_evaluate_allows_when_role_grants_permission(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.ALLOW
    assert result.matched_permission_code == "users:read"


async def test_evaluate_denies_when_no_role_grants_permission(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.DELETE,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.DENY


async def test_evaluate_denies_user_with_no_roles(db_session: AsyncSession) -> None:
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=uuid.uuid4(),
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.DENY


async def test_evaluate_records_audit_entry(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    evaluator = _evaluator(db_session)

    await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    entries = await AuthorizationAuditRepository(db_session).list_recent_for_user(user_id)
    assert len(entries) == 1
    assert entries[0].decision == AuthorizationDecision.ALLOW


async def test_evaluate_expired_role_assignment_is_ignored(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    await UserRoleRepository(db_session).create(
        UserRole(
            user_id=user_id,
            role_id=VIEWER_ROLE_ID,
            organization_id=DEFAULT_ORGANIZATION_ID,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.DENY


async def test_evaluate_organization_scoped_role_only_applies_to_matching_org(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    await OrganizationRoleRepository(db_session).create(
        OrganizationRole(user_id=user_id, role_id=VIEWER_ROLE_ID, organization_id=org_id)
    )
    evaluator = _evaluator(db_session)

    matching = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=org_id,
        project_id=None,
        context={},
    )
    non_matching = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=uuid.uuid4(),
        project_id=None,
        context={},
    )

    assert matching.decision == AuthorizationDecision.ALLOW
    assert non_matching.decision == AuthorizationDecision.DENY


async def test_evaluate_resource_grant_overrides_rbac_deny(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    permission = await PermissionRepository(db_session).get_by_code("reports:delete")
    assert permission is not None
    await _resource_service(db_session).grant(
        resource_type=ResourceType.REPORTS,
        resource_id=resource_id,
        subject_type=SubjectType.USER,
        subject_id=user_id,
        permission_id=permission.id,
        is_owner=True,
        is_public=False,
        granted_by=None,
    )
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.DELETE,
        resource_type=ResourceType.REPORTS,
        resource_id=resource_id,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.ALLOW
    assert "owner" in result.reason.lower()


async def test_evaluate_policy_deny_overrides_rbac_allow(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    await _policy_service(db_session).create(
        name="Block Reads",
        code=f"block-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.DENY,
        resource_type=ResourceType.USERS,
        action=PermissionAction.READ,
        priority=999,
        conditions=[],
        subject_type=SubjectType.GLOBAL,
        subject_id=None,
        metadata={},
    )
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.DENY
    assert result.matched_policy_code is not None


async def test_evaluate_policy_with_unmet_condition_does_not_apply(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    await _policy_service(db_session).create(
        name="Deny From Blocked Country",
        code=f"geo-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.DENY,
        resource_type=ResourceType.USERS,
        action=PermissionAction.READ,
        priority=999,
        conditions=[
            ConditionInput(
                condition_type=PolicyConditionType.LOCATION_BASED,
                field=None,
                operator="equals",
                value={"allowed_countries": ["KP"]},
            )
        ],
        subject_type=SubjectType.GLOBAL,
        subject_id=None,
        metadata={},
    )
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={"country": "US"},
    )

    assert result.decision == AuthorizationDecision.ALLOW


async def test_evaluate_policy_scoped_to_role_only_applies_to_that_role(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    unrelated_role = await RoleRepository(db_session).create(
        Role(name="R", code=f"r-{uuid.uuid4().hex[:8]}", organization_id=DEFAULT_ORGANIZATION_ID)
    )
    await _policy_service(db_session).create(
        name="Scoped Deny",
        code=f"scoped-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.DENY,
        resource_type=ResourceType.USERS,
        action=PermissionAction.READ,
        priority=999,
        conditions=[],
        subject_type=SubjectType.ROLE,
        subject_id=unrelated_role.id,
        metadata={},
    )
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.ALLOW


async def test_effective_permission_codes_aggregates_role(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    evaluator = _evaluator(db_session)

    codes, role_codes = await evaluator.effective_permission_codes(
        user_id, organization_id=None, project_id=None
    )

    assert "users:read" in codes
    assert role_codes == ["viewer"]


async def test_effective_permission_codes_empty_for_user_with_no_roles(
    db_session: AsyncSession,
) -> None:
    evaluator = _evaluator(db_session)

    codes, role_codes = await evaluator.effective_permission_codes(
        uuid.uuid4(), organization_id=None, project_id=None
    )

    assert codes == []
    assert role_codes == []


async def test_evaluate_project_scoped_role_only_applies_to_matching_project(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    await ProjectRoleRepository(db_session).create(
        ProjectRole(
            user_id=user_id,
            role_id=VIEWER_ROLE_ID,
            project_id=project_id,
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )
    evaluator = _evaluator(db_session)

    matching = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=project_id,
        context={},
    )
    non_matching = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=uuid.uuid4(),
        context={},
    )

    assert matching.decision == AuthorizationDecision.ALLOW
    assert non_matching.decision == AuthorizationDecision.DENY


async def test_evaluate_with_no_matching_permission_in_catalog_denies(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    permission = await PermissionRepository(db_session).get_by_code("users:read")
    assert permission is not None
    await PermissionService(PermissionRepository(db_session)).delete(permission.id)
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.DENY
    assert result.matched_permission_code is None


async def test_evaluate_resource_id_given_but_no_grants_falls_back_to_rbac(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=uuid.uuid4(),
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.ALLOW
    assert result.reason == "Granted by role."


async def test_evaluate_policy_with_mismatched_resource_type_is_skipped(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    await _policy_service(db_session).create(
        name="Deny Reports",
        code=f"deny-reports-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.DENY,
        resource_type=ResourceType.REPORTS,
        action=None,
        priority=999,
        conditions=[],
        subject_type=SubjectType.GLOBAL,
        subject_id=None,
        metadata={},
    )
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.ALLOW


async def test_evaluate_policy_with_mismatched_action_is_skipped(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    await _policy_service(db_session).create(
        name="Deny Deletes",
        code=f"deny-delete-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.DENY,
        resource_type=ResourceType.USERS,
        action=PermissionAction.DELETE,
        priority=999,
        conditions=[],
        subject_type=SubjectType.GLOBAL,
        subject_id=None,
        metadata={},
    )
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.ALLOW


async def test_evaluate_policy_assigned_directly_to_user(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    await _policy_service(db_session).create(
        name="Deny This User",
        code=f"deny-user-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.DENY,
        resource_type=ResourceType.USERS,
        action=PermissionAction.READ,
        priority=999,
        conditions=[],
        subject_type=SubjectType.USER,
        subject_id=user_id,
        metadata={},
    )
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.DENY


async def test_evaluate_policy_assigned_to_role_user_actually_holds(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    await _assign_viewer(db_session, user_id)
    await _policy_service(db_session).create(
        name="Deny Viewers",
        code=f"deny-viewer-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.DENY,
        resource_type=ResourceType.USERS,
        action=PermissionAction.READ,
        priority=999,
        conditions=[],
        subject_type=SubjectType.ROLE,
        subject_id=VIEWER_ROLE_ID,
        metadata={},
    )
    evaluator = _evaluator(db_session)

    result = await evaluator.evaluate(
        user_id=user_id,
        action=PermissionAction.READ,
        resource_type=ResourceType.USERS,
        resource_id=None,
        organization_id=None,
        project_id=None,
        context={},
    )

    assert result.decision == AuthorizationDecision.DENY
