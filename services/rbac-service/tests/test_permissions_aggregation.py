"""Tests for :mod:`app.permissions.aggregation`."""

from __future__ import annotations

import uuid

from shared_core.security.rbac import PermissionScope

from app.permissions.aggregation import permission_code, scope_matches


def test_permission_code_format() -> None:
    assert permission_code("users", "read") == "users:read"


def test_global_scope_always_matches() -> None:
    assert (
        scope_matches(
            PermissionScope.GLOBAL,
            resource_organization_id=None,
            context_organization_id=None,
        )
        is True
    )


def test_organization_scope_matches_same_org() -> None:
    org_id = uuid.uuid4()

    assert (
        scope_matches(
            PermissionScope.ORGANIZATION,
            resource_organization_id=org_id,
            context_organization_id=org_id,
        )
        is True
    )


def test_organization_scope_rejects_different_org() -> None:
    assert (
        scope_matches(
            PermissionScope.ORGANIZATION,
            resource_organization_id=uuid.uuid4(),
            context_organization_id=uuid.uuid4(),
        )
        is False
    )


def test_organization_scope_rejects_missing_resource_org() -> None:
    assert (
        scope_matches(
            PermissionScope.ORGANIZATION,
            resource_organization_id=None,
            context_organization_id=uuid.uuid4(),
        )
        is False
    )


def test_project_scope_requires_matching_org_and_project() -> None:
    org_id, project_id = uuid.uuid4(), uuid.uuid4()

    assert (
        scope_matches(
            PermissionScope.PROJECT,
            resource_organization_id=org_id,
            context_organization_id=org_id,
            resource_project_id=project_id,
            context_project_id=project_id,
        )
        is True
    )


def test_project_scope_rejects_matching_org_but_different_project() -> None:
    org_id = uuid.uuid4()

    assert (
        scope_matches(
            PermissionScope.PROJECT,
            resource_organization_id=org_id,
            context_organization_id=org_id,
            resource_project_id=uuid.uuid4(),
            context_project_id=uuid.uuid4(),
        )
        is False
    )


def test_project_scope_rejects_missing_project_ids() -> None:
    org_id = uuid.uuid4()

    assert (
        scope_matches(
            PermissionScope.PROJECT,
            resource_organization_id=org_id,
            context_organization_id=org_id,
        )
        is False
    )
