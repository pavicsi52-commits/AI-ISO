"""Tests for shared type aliases."""

from __future__ import annotations

from uuid import UUID, uuid4

from shared_core.types import EntityId, TenantScope


def test_entity_id_is_uuid_alias() -> None:
    value: EntityId = uuid4()

    assert isinstance(value, UUID)


def test_tenant_scope_holds_organization_and_optional_project() -> None:
    org_id = uuid4()
    scope = TenantScope(organization_id=org_id)

    assert scope.organization_id == org_id
    assert scope.project_id is None


def test_tenant_scope_with_project() -> None:
    org_id = uuid4()
    project_id = uuid4()
    scope = TenantScope(organization_id=org_id, project_id=project_id)

    assert scope.project_id == project_id
