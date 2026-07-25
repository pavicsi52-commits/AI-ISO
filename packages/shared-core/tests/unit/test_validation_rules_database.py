"""Tests for database validation rules."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from shared_core.validation.rules import database


def test_check_foreign_key_passes_when_none() -> None:
    result = database.check_foreign_key(referenced_id=None, exists=False, reference_name="x")

    assert result.valid is True


def test_check_foreign_key_passes_when_exists() -> None:
    assert (
        database.check_foreign_key(
            referenced_id=uuid4(), exists=True, reference_name="organization"
        ).valid
        is True
    )


def test_check_foreign_key_fails_when_missing() -> None:
    result = database.check_foreign_key(
        referenced_id=uuid4(), exists=False, reference_name="organization"
    )

    assert result.valid is False
    assert "organization" in result.errors[0]


def test_check_duplicate_records_passes_for_single_match() -> None:
    assert database.check_duplicate_records(count=1, unique_field="email").valid is True


def test_check_duplicate_records_passes_for_no_match() -> None:
    assert database.check_duplicate_records(count=0, unique_field="email").valid is True


def test_check_duplicate_records_fails_for_multiple_matches() -> None:
    result = database.check_duplicate_records(count=3, unique_field="email")

    assert result.valid is False


def test_check_referential_integrity_fails_with_dependents() -> None:
    result = database.check_referential_integrity(has_dependents=True, resource_type="project")

    assert result.valid is False
    assert "project" in result.errors[0]


def test_check_referential_integrity_passes_without_dependents() -> None:
    assert database.check_referential_integrity(has_dependents=False).valid is True


def test_check_version_passes_for_matching_version() -> None:
    assert database.check_version(expected_version=3, actual_version=3).valid is True


def test_check_version_fails_for_mismatch() -> None:
    result = database.check_version(expected_version=3, actual_version=5)

    assert result.valid is False


def test_check_soft_delete_passes_for_active_record() -> None:
    assert database.check_soft_delete(is_active=True, deleted_at=None).valid is True


def test_check_soft_delete_fails_for_inactive_record() -> None:
    assert database.check_soft_delete(is_active=False, deleted_at=None).valid is False


def test_check_soft_delete_fails_for_deleted_record() -> None:
    result = database.check_soft_delete(is_active=True, deleted_at=datetime.now(UTC))

    assert result.valid is False


def test_check_tenant_isolation_passes_for_same_org() -> None:
    org_id = uuid4()

    assert (
        database.check_tenant_isolation(
            record_organization_id=org_id, context_organization_id=org_id
        ).valid
        is True
    )


def test_check_tenant_isolation_fails_for_different_org() -> None:
    result = database.check_tenant_isolation(
        record_organization_id=uuid4(), context_organization_id=uuid4()
    )

    assert result.valid is False


def test_check_tenant_isolation_fails_when_context_unset() -> None:
    result = database.check_tenant_isolation(
        record_organization_id=uuid4(), context_organization_id=None
    )

    assert result.valid is False
