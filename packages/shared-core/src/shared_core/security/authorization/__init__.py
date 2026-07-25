"""Authorization orchestration: combines RBAC and the policy engine into one entry point.

Per docs/017_Enterprise_Security_Framework.md.txt's pipeline:
"Users -> Roles -> Permissions -> Policies -> Resources -> Actions".
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_core.enums.permission import Permission
from shared_core.enums.role import Role
from shared_core.security.policies import PolicyContext, PolicyEngine
from shared_core.security.rbac import has_permission


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    """The outcome of an authorization check."""

    granted: bool
    reason: str = ""


def authorize(
    *,
    role: Role,
    permission: Permission,
    policy_engine: PolicyEngine | None = None,
    policy_context: PolicyContext | None = None,
) -> AuthorizationResult:
    """Authorize an action.

    RBAC is checked first (fast, always required); any policies
    registered for the action are checked only if a *policy_engine* and
    *policy_context* are supplied -- both must pass.
    """
    if not has_permission(role, permission):
        return AuthorizationResult(
            granted=False, reason=f"Role '{role.value}' lacks '{permission.value}'."
        )
    if (
        policy_engine is not None
        and policy_context is not None
        and not policy_engine.evaluate(policy_context)
    ):
        return AuthorizationResult(granted=False, reason="Denied by policy.")
    return AuthorizationResult(granted=True)
