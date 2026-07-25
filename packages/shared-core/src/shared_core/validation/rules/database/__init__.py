"""Database validation rules (docs/016 "DATABASE VALIDATION").

Pluggable, taking already-computed facts (does the referenced row exist?
what's the current version?) rather than querying anything themselves --
this framework has no opinion on *how* a service checks a foreign key,
only on how that check's outcome becomes a structured
:class:`~shared_core.validation.results.ValidationResult`. ``check_version``
and ``check_soft_delete`` pair naturally with
:class:`shared_core.base.version_mixin.VersionMixin` and
:class:`shared_core.base.soft_delete_mixin.SoftDeleteMixin` (Prompt 012).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.validation.results import ValidationResult


def check_foreign_key(
    *, referenced_id: UUID | None, exists: bool, reference_name: str
) -> ValidationResult:
    """Validate a foreign-key reference points to an existing row.

    A ``None`` reference (an optional foreign key left unset) is always valid.
    """
    if referenced_id is not None and not exists:
        return ValidationResult.fail(
            f"Referenced {reference_name} '{referenced_id}' does not exist."
        )
    return ValidationResult.ok()


def check_duplicate_records(*, count: int, unique_field: str) -> ValidationResult:
    """Validate a uniqueness constraint holds: at most one matching row."""
    if count > 1:
        return ValidationResult.fail(
            f"Found {count} duplicate records for '{unique_field}'; expected at most 1."
        )
    return ValidationResult.ok()


def check_referential_integrity(
    *, has_dependents: bool, resource_type: str = "resource"
) -> ValidationResult:
    """Validate a resource with dependents isn't deleted out from under them."""
    if has_dependents:
        return ValidationResult.fail(
            f"Cannot delete this {resource_type}: other records still reference it."
        )
    return ValidationResult.ok()


def check_version(*, expected_version: int, actual_version: int) -> ValidationResult:
    """Validate an optimistic-locking version matches (docs/007 "Version")."""
    if expected_version != actual_version:
        return ValidationResult.fail(
            f"Version mismatch: expected {expected_version}, found {actual_version}. "
            "The record was modified concurrently."
        )
    return ValidationResult.ok()


def check_soft_delete(*, is_active: bool, deleted_at: datetime | None) -> ValidationResult:
    """Validate a record hasn't been soft-deleted."""
    if not is_active or deleted_at is not None:
        return ValidationResult.fail("This record has been deleted.")
    return ValidationResult.ok()


def check_tenant_isolation(
    *, record_organization_id: UUID, context_organization_id: UUID | None
) -> ValidationResult:
    """Validate a database record belongs to the caller's tenant (organization)."""
    if context_organization_id is None or record_organization_id != context_organization_id:
        return ValidationResult.fail("This record does not belong to your organization.")
    return ValidationResult.ok()
