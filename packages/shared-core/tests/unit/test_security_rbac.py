"""Tests for the expanded RBAC package: scoped permission checks."""

from __future__ import annotations

from uuid import uuid4

from shared_core.enums import Permission, Role
from shared_core.security.rbac import PermissionScope, has_scoped_permission


def test_global_scope_grants_only_super_admin() -> None:
    assert (
        has_scoped_permission(Role.SUPER_ADMIN, Permission.READ, scope=PermissionScope.GLOBAL)
        is True
    )
    assert (
        has_scoped_permission(
            Role.ORGANIZATION_ADMIN, Permission.READ, scope=PermissionScope.GLOBAL
        )
        is False
    )


def test_global_scope_denied_without_permission() -> None:
    # SUPER_ADMIN has every permission, so use a role that lacks READ... but
    # SUPER_ADMIN always has it. Confirm the permission gate runs first by
    # checking a permission no role but SUPER_ADMIN has combined with a
    # non-super-admin role.
    assert (
        has_scoped_permission(Role.VIEWER, Permission.ADMIN, scope=PermissionScope.GLOBAL) is False
    )


def test_organization_scope_passes_for_matching_organization() -> None:
    org_id = uuid4()

    result = has_scoped_permission(
        Role.ORGANIZATION_ADMIN,
        Permission.UPDATE,
        scope=PermissionScope.ORGANIZATION,
        resource_organization_id=org_id,
        context_organization_id=org_id,
    )

    assert result is True


def test_organization_scope_fails_for_different_organization() -> None:
    result = has_scoped_permission(
        Role.ORGANIZATION_ADMIN,
        Permission.UPDATE,
        scope=PermissionScope.ORGANIZATION,
        resource_organization_id=uuid4(),
        context_organization_id=uuid4(),
    )

    assert result is False


def test_organization_scope_fails_without_context() -> None:
    result = has_scoped_permission(
        Role.ORGANIZATION_ADMIN,
        Permission.UPDATE,
        scope=PermissionScope.ORGANIZATION,
        resource_organization_id=uuid4(),
        context_organization_id=None,
    )

    assert result is False


def test_project_scope_passes_for_matching_project() -> None:
    project_id = uuid4()

    result = has_scoped_permission(
        Role.PROJECT_ADMIN,
        Permission.DELETE,
        scope=PermissionScope.PROJECT,
        resource_project_id=project_id,
        context_project_id=project_id,
    )

    assert result is True


def test_project_scope_fails_for_different_project() -> None:
    result = has_scoped_permission(
        Role.PROJECT_ADMIN,
        Permission.DELETE,
        scope=PermissionScope.PROJECT,
        resource_project_id=uuid4(),
        context_project_id=uuid4(),
    )

    assert result is False


def test_scoped_permission_denied_when_role_lacks_permission() -> None:
    org_id = uuid4()

    result = has_scoped_permission(
        Role.VIEWER,
        Permission.DELETE,
        scope=PermissionScope.ORGANIZATION,
        resource_organization_id=org_id,
        context_organization_id=org_id,
    )

    assert result is False
