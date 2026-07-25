"""Tests for business validation rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from shared_core.validation.base import ValidationSeverity
from shared_core.validation.rules import business


def test_check_unique_name_fails_when_exists() -> None:
    result = business.check_unique_name("widget", exists=True, resource_type="widget")

    assert result.valid is False
    assert "widget" in result.errors[0]


def test_check_unique_name_passes_when_not_exists() -> None:
    assert business.check_unique_name("widget", exists=False).valid is True


def test_check_resource_ownership_passes_for_owner() -> None:
    owner_id = uuid4()

    assert (
        business.check_resource_ownership(resource_owner_id=owner_id, requester_id=owner_id).valid
        is True
    )


def test_check_resource_ownership_fails_for_non_owner() -> None:
    result = business.check_resource_ownership(resource_owner_id=uuid4(), requester_id=uuid4())

    assert result.valid is False


def test_check_resource_ownership_fails_when_requester_unset() -> None:
    result = business.check_resource_ownership(resource_owner_id=uuid4(), requester_id=None)

    assert result.valid is False


def test_check_organization_isolation_passes_for_same_org() -> None:
    org_id = uuid4()

    assert (
        business.check_organization_isolation(
            resource_organization_id=org_id, context_organization_id=org_id
        ).valid
        is True
    )


def test_check_organization_isolation_fails_for_different_org() -> None:
    result = business.check_organization_isolation(
        resource_organization_id=uuid4(), context_organization_id=uuid4()
    )

    assert result.valid is False


def test_check_project_isolation_passes_for_same_project() -> None:
    project_id = uuid4()

    assert (
        business.check_project_isolation(
            resource_project_id=project_id, context_project_id=project_id
        ).valid
        is True
    )


def test_check_project_isolation_fails_for_different_project() -> None:
    result = business.check_project_isolation(
        resource_project_id=uuid4(), context_project_id=uuid4()
    )

    assert result.valid is False


def test_check_license_passes_when_permitted() -> None:
    assert business.check_license(permitted=True).valid is True


def test_check_license_fails_when_not_permitted() -> None:
    result = business.check_license(permitted=False, feature="SSO")

    assert result.valid is False
    assert "SSO" in result.errors[0]


def test_check_dependency_passes_when_satisfied() -> None:
    assert business.check_dependency(satisfied=True, dependency_name="db").valid is True


def test_check_dependency_fails_when_not_satisfied() -> None:
    result = business.check_dependency(satisfied=False, dependency_name="redis")

    assert result.valid is False
    assert "redis" in result.errors[0]


def test_check_duplicate_prevention_fails_for_duplicate() -> None:
    result = business.check_duplicate_prevention("a", existing=["a", "b"])

    assert result.valid is False


def test_check_duplicate_prevention_passes_for_new_item() -> None:
    assert business.check_duplicate_prevention("c", existing=["a", "b"]).valid is True


def test_check_quota_fails_at_limit() -> None:
    result = business.check_quota(current=10, limit=10, resource_type="project")

    assert result.valid is False
    assert "10/10" in result.errors[0]


def test_check_quota_passes_below_limit() -> None:
    assert business.check_quota(current=5, limit=10).valid is True


def test_check_approval_required_fails_when_not_approved() -> None:
    result = business.check_approval_required(approved=False, action="deploy to production")

    assert result.valid is False
    assert result.severity == ValidationSeverity.WARNING


def test_check_approval_required_passes_when_approved() -> None:
    assert business.check_approval_required(approved=True).valid is True


def test_check_maintenance_window_fails_when_inside_window() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    result = business.check_maintenance_window(
        now=now,
        window_start=now - timedelta(hours=1),
        window_end=now + timedelta(hours=1),
    )

    assert result.valid is False


def test_check_maintenance_window_passes_when_outside_window() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    result = business.check_maintenance_window(
        now=now,
        window_start=now + timedelta(hours=1),
        window_end=now + timedelta(hours=2),
    )

    assert result.valid is True
