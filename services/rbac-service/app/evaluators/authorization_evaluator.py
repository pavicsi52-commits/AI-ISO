"""The authorization decision engine.

Per docs/032 "AUTHORIZATION EVALUATION": Evaluate User, Role,
Permissions, Policies, Conditions, Resource Ownership, Tenant,
Environment. Return: Decision (Allow/Deny), Reason. This is the
DB-backed orchestrator :mod:`app.roles.hierarchy`,
:mod:`app.policies.engine`, and :mod:`app.resources.ownership`'s pure
functions feed into -- it is what backs both ``POST
/authorization/evaluate`` and ``GET /users/{id}/permissions``.

Precedence, most to least authoritative:

1. An explicit resource-instance grant/deny
   (:mod:`app.resources.ownership`) -- deny always wins, an explicit
   allow overrides a role-based deny.
2. The highest-priority matching :class:`~app.models.authorization_policy
   .AuthorizationPolicy` whose conditions hold -- again, whichever
   effect it carries (allow or deny) wins outright.
3. The role/permission baseline: does any of the user's active,
   unexpired role assignments (aggregated through the hierarchy) grant
   the permission matching this resource/action.

Every evaluation is recorded to
:class:`~app.models.authorization_audit.AuthorizationAuditEntry`
("AUDIT": Authorization Decisions), and a deny publishes
:class:`~app.events.rbac_events.AuthorizationDeniedEvent`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.security.policies import PolicyContext

from app.constants import DEFAULT_ORGANIZATION_ID
from app.events.rbac_events import AuthorizationDeniedEvent
from app.models.authorization_audit import AuthorizationAuditEntry
from app.models.enums import (
    AssignmentStatus,
    AuthorizationDecision,
    PermissionAction,
    PolicyEffect,
    ResourceType,
    SubjectType,
)
from app.permissions.aggregation import permission_code
from app.policies.engine import compile_policy
from app.repositories.authorization_audit import AuthorizationAuditRepository
from app.repositories.organization_role import OrganizationRoleRepository
from app.repositories.permission import PermissionRepository
from app.repositories.policy_assignment import PolicyAssignmentRepository
from app.repositories.project_role import ProjectRoleRepository
from app.repositories.user_role import UserRoleRepository
from app.resources.ownership import resolve_resource_decision
from app.services.policy import PolicyService
from app.services.resource_authorization import ResourceAuthorizationService
from app.services.role import RoleService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class EvaluationResult:
    """The outcome of one authorization evaluation."""

    __slots__ = ("decision", "matched_permission_code", "matched_policy_code", "reason")

    def __init__(
        self,
        *,
        decision: AuthorizationDecision,
        reason: str,
        matched_permission_code: str | None = None,
        matched_policy_code: str | None = None,
    ) -> None:
        self.decision = decision
        self.reason = reason
        self.matched_permission_code = matched_permission_code
        self.matched_policy_code = matched_policy_code


class AuthorizationEvaluator:
    """Decides allow/deny for one user/action/resource, and resolves the
    effective permission matrix for a user/scope.
    """

    def __init__(
        self,
        user_roles: UserRoleRepository,
        organization_roles: OrganizationRoleRepository,
        project_roles: ProjectRoleRepository,
        permissions: PermissionRepository,
        policy_assignments: PolicyAssignmentRepository,
        roles: RoleService,
        policies: PolicyService,
        resources: ResourceAuthorizationService,
        audit: AuthorizationAuditRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._user_roles = user_roles
        self._organization_roles = organization_roles
        self._project_roles = project_roles
        self._permissions = permissions
        self._policy_assignments = policy_assignments
        self._roles = roles
        self._policies = policies
        self._resources = resources
        self._audit = audit
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def _applicable_role_ids(
        self, user_id: UUID, *, organization_id: UUID | None, project_id: UUID | None
    ) -> set[UUID]:
        now = datetime.now(UTC)

        def _still_active(status: AssignmentStatus, expires_at: datetime | None) -> bool:
            return status == AssignmentStatus.ACTIVE and (expires_at is None or expires_at > now)

        role_ids: set[UUID] = {
            r.role_id
            for r in await self._user_roles.list_for_user(user_id)
            if _still_active(r.status, r.expires_at)
        }
        if organization_id is not None:
            role_ids |= {
                r.role_id
                for r in await self._organization_roles.list_for_user(user_id)
                if r.organization_id == organization_id and _still_active(r.status, r.expires_at)
            }
        if project_id is not None:
            role_ids |= {
                r.role_id
                for r in await self._project_roles.list_for_user(user_id)
                if r.project_id == project_id and _still_active(r.status, r.expires_at)
            }
        return role_ids

    async def effective_permission_codes(
        self, user_id: UUID, *, organization_id: UUID | None, project_id: UUID | None
    ) -> tuple[list[str], list[str]]:
        """Return ``(permission_codes, role_codes)`` -- *user_id*'s full effective
        access at this scope ("User Permission Matrix", "Permission Aggregation").
        """
        role_ids = await self._applicable_role_ids(
            user_id, organization_id=organization_id, project_id=project_id
        )
        permission_ids: set[UUID] = set()
        role_codes: list[str] = []
        for role_id in role_ids:
            role = await self._roles.get_by_id(role_id)
            role_codes.append(role.code)
            permission_ids |= await self._roles.resolve_effective_permission_ids(role_id)
        codes = [p.code for p in await self._permissions.list_by_ids(list(permission_ids))]
        return sorted(codes), sorted(role_codes)

    async def evaluate(
        self,
        *,
        user_id: UUID,
        action: PermissionAction,
        resource_type: ResourceType,
        resource_id: UUID | None,
        organization_id: UUID | None,
        project_id: UUID | None,
        context: dict[str, object],
        ip_address: str | None = None,
    ) -> EvaluationResult:
        """Decide whether *user_id* may *action* *resource_type*[/*resource_id*]."""
        role_ids = await self._applicable_role_ids(
            user_id, organization_id=organization_id, project_id=project_id
        )

        code = permission_code(str(resource_type), str(action))
        permission = await self._permissions.get_by_code(code)

        rbac_allowed = False
        if permission is not None:
            for role_id in role_ids:
                granted = await self._roles.resolve_effective_permission_ids(role_id)
                if permission.id in granted:
                    rbac_allowed = True
                    break

        result = EvaluationResult(
            decision=AuthorizationDecision.ALLOW if rbac_allowed else AuthorizationDecision.DENY,
            reason=("Granted by role." if rbac_allowed else "No role grants this permission."),
            matched_permission_code=code if permission is not None else None,
        )

        if resource_id is not None and permission is not None:
            grants = await self._resources.grants_for_resource(resource_type, resource_id)
            resource_decision = resolve_resource_decision(
                grants, permission_id=permission.id, user_id=user_id, user_role_ids=role_ids
            )
            if resource_decision.decided:
                result = EvaluationResult(
                    decision=(
                        AuthorizationDecision.ALLOW
                        if resource_decision.allowed
                        else AuthorizationDecision.DENY
                    ),
                    reason=resource_decision.reason,
                    matched_permission_code=code,
                )

        policy_context = PolicyContext(
            action=str(action),
            attributes={
                **context,
                "user_id": str(user_id),
                "resource_type": str(resource_type),
                "resource_id": str(resource_id) if resource_id else None,
                "organization_id": str(organization_id) if organization_id else None,
                "project_id": str(project_id) if project_id else None,
                "ip_address": ip_address,
            },
        )
        for entry in await self._policies.list_active():
            policy = entry.policy
            if policy.resource_type is not None and policy.resource_type != resource_type:
                continue
            if policy.action is not None and policy.action != action:
                continue
            if not await self._policy_applies_to_subject(policy.id, user_id, role_ids):
                continue
            compiled = compile_policy(policy, entry.conditions)
            if compiled.predicate(policy_context):
                result = EvaluationResult(
                    decision=(
                        AuthorizationDecision.ALLOW
                        if policy.effect == PolicyEffect.ALLOW
                        else AuthorizationDecision.DENY
                    ),
                    reason=f"Matched policy '{policy.code}'.",
                    matched_permission_code=result.matched_permission_code,
                    matched_policy_code=policy.code,
                )
                break

        await self._record_audit(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            ip_address=ip_address,
        )
        if result.decision == AuthorizationDecision.DENY:
            await self._publish(
                AuthorizationDeniedEvent(
                    source_service="rbac-service",
                    payload={"user_id": str(user_id), "action": str(action)},
                )
            )
        return result

    async def _policy_applies_to_subject(
        self, policy_id: UUID, user_id: UUID, role_ids: set[UUID]
    ) -> bool:
        applicable = await self._policy_assignments.list_applicable(
            subject_type=SubjectType.USER, subject_id=user_id
        )
        if any(a.policy_id == policy_id for a in applicable):
            return True
        for role_id in role_ids:
            role_matches = await self._policy_assignments.list_applicable(
                subject_type=SubjectType.ROLE, subject_id=role_id
            )
            if any(a.policy_id == policy_id for a in role_matches):
                return True
        return False

    async def _record_audit(
        self,
        *,
        user_id: UUID,
        action: PermissionAction,
        resource_type: ResourceType,
        resource_id: UUID | None,
        result: EvaluationResult,
        ip_address: str | None,
    ) -> None:
        await self._audit.create(
            AuthorizationAuditEntry(
                user_id=user_id,
                action=str(action),
                resource_type=resource_type,
                resource_id=resource_id,
                decision=result.decision,
                reason=result.reason,
                ip_address=ip_address,
                context={
                    "matched_permission_code": result.matched_permission_code,
                    "matched_policy_code": result.matched_policy_code,
                },
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )


__all__ = ["AuthorizationEvaluator", "EvaluationResult"]
