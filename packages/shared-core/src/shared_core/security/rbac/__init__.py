"""RBAC (Role-Based Access Control).

Maps built-in :class:`~shared_core.enums.Role` values to
:class:`~shared_core.enums.Permission` sets (Prompt 012 baseline). Adds
organization/project/global scope-level checks per docs/017 "RBAC":
"Support Organization Level, Project Level, Global Level." Custom and
inherited roles are :mod:`shared_core.security.roles`'s concern -- this
module covers the fixed system roles every deployment starts with.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from shared_core.enums.permission import Permission
from shared_core.enums.role import Role

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.SUPER_ADMIN: frozenset(Permission),
    Role.ORGANIZATION_ADMIN: frozenset(
        {
            Permission.READ,
            Permission.CREATE,
            Permission.UPDATE,
            Permission.DELETE,
            Permission.EXECUTE,
            Permission.APPROVE,
            Permission.EXPORT,
            Permission.IMPORT,
        }
    ),
    Role.PROJECT_ADMIN: frozenset(
        {
            Permission.READ,
            Permission.CREATE,
            Permission.UPDATE,
            Permission.DELETE,
            Permission.EXECUTE,
            Permission.EXPORT,
        }
    ),
    Role.OPERATOR: frozenset(
        {Permission.READ, Permission.CREATE, Permission.UPDATE, Permission.EXECUTE}
    ),
    Role.VIEWER: frozenset({Permission.READ}),
    Role.AUDITOR: frozenset({Permission.READ, Permission.EXPORT}),
}


class PermissionScope(StrEnum):
    """The tenant scope a permission check is evaluated at."""

    GLOBAL = "global"
    ORGANIZATION = "organization"
    PROJECT = "project"


def has_permission(role: Role, permission: Permission) -> bool:
    """Return whether ``role`` grants ``permission``."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def has_any_permission(role: Role, permissions: set[Permission]) -> bool:
    """Return whether ``role`` grants at least one of ``permissions``."""
    return bool(ROLE_PERMISSIONS.get(role, frozenset()) & permissions)


def has_all_permissions(role: Role, permissions: set[Permission]) -> bool:
    """Return whether ``role`` grants every permission in ``permissions``."""
    return permissions.issubset(ROLE_PERMISSIONS.get(role, frozenset()))


def has_scoped_permission(
    role: Role,
    permission: Permission,
    *,
    scope: PermissionScope,
    resource_organization_id: UUID | None = None,
    context_organization_id: UUID | None = None,
    resource_project_id: UUID | None = None,
    context_project_id: UUID | None = None,
) -> bool:
    """Check both that ``role`` grants ``permission`` *and* that the tenant
    scope matches -- per docs/017 "TENANT SECURITY": "Strict Organization
    Isolation... Validate every request."

    - ``GLOBAL`` scope: only ``SUPER_ADMIN`` may act globally.
    - ``ORGANIZATION`` scope: the resource's organization must match the
      caller's organization context.
    - ``PROJECT`` scope: the resource's project must match the caller's
      project context.
    """
    if not has_permission(role, permission):
        return False
    if scope is PermissionScope.GLOBAL:
        return role is Role.SUPER_ADMIN
    if scope is PermissionScope.ORGANIZATION:
        return (
            context_organization_id is not None
            and context_organization_id == resource_organization_id
        )
    if scope is PermissionScope.PROJECT:
        return context_project_id is not None and context_project_id == resource_project_id
    return False
