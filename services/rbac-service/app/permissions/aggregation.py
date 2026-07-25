"""Permission code conventions and scope matching.

Per docs/032 "PERMISSION MODEL"/"POLICY ENGINE" scope concepts
(Organization Scope, Project Scope). Mirrors
:func:`shared_core.security.rbac.has_scoped_permission`'s scope-match
semantics, adapted for this service's own persisted, dynamic
:class:`~shared_core.security.rbac.PermissionScope` value (shared-core's
version only matches its fixed ``Role``/``Permission`` enums).
"""

from __future__ import annotations

from uuid import UUID

from shared_core.security.rbac import PermissionScope


def permission_code(resource: str, action: str) -> str:
    """The canonical ``"{resource}:{action}"`` code convention every seeded
    and administrator-created permission uses.
    """
    return f"{resource}:{action}"


def scope_matches(
    scope: PermissionScope,
    *,
    resource_organization_id: UUID | None,
    context_organization_id: UUID | None,
    resource_project_id: UUID | None = None,
    context_project_id: UUID | None = None,
) -> bool:
    """Whether a permission of *scope* covers the resource identified by
    *resource_organization_id*/*resource_project_id*, given the caller's
    own *context_organization_id*/*context_project_id*.

    :attr:`PermissionScope.GLOBAL` always matches. :attr:`PermissionScope
    .ORGANIZATION` matches only within the same organization.
    :attr:`PermissionScope.PROJECT` additionally requires the same project.
    """
    if scope == PermissionScope.GLOBAL:
        return True
    if scope == PermissionScope.ORGANIZATION:
        return (
            resource_organization_id is not None
            and resource_organization_id == context_organization_id
        )
    if scope == PermissionScope.PROJECT:
        return (
            resource_organization_id is not None
            and resource_organization_id == context_organization_id
            and resource_project_id is not None
            and resource_project_id == context_project_id
        )
    return False


__all__ = ["permission_code", "scope_matches"]
