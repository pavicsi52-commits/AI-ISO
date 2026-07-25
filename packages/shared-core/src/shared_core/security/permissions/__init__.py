"""Resource-scoped permission checks.

:mod:`shared_core.security.rbac` maps a role to the permissions it grants
in general; this module checks a permission against a *specific* resource
when ownership or explicit grants matter beyond what the role alone says
(e.g. "the resource owner may always update their own resource, even
without a role granting UPDATE").
"""

from __future__ import annotations

from uuid import UUID

from shared_core.enums.permission import Permission
from shared_core.enums.role import Role
from shared_core.security.rbac import ROLE_PERMISSIONS, has_permission


def can_access_resource(
    *,
    role: Role,
    permission: Permission,
    resource_owner_id: UUID | None = None,
    requester_id: UUID | None = None,
) -> bool:
    """Grant access if the role permits it, OR the requester owns the resource."""
    if has_permission(role, permission):
        return True
    return (
        resource_owner_id is not None
        and requester_id is not None
        and resource_owner_id == requester_id
    )


def effective_permissions(
    role: Role, *, explicit_grants: frozenset[Permission] = frozenset()
) -> frozenset[Permission]:
    """Return the union of a role's permissions and any explicitly-granted extras."""
    return ROLE_PERMISSIONS.get(role, frozenset()) | explicit_grants
