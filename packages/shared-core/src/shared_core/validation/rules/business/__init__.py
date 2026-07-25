"""Business validation rules (docs/016 "BUSINESS VALIDATION").

Per docs/016 "DO NOT IMPLEMENT": "Business Services" -- these are
reusable, *pluggable* rule functions that take the already-computed
fact (does this exist? does the caller own it? is the quota exceeded?)
as a parameter, never the business/database logic that computes it. A
service supplies its own existence-check, ownership lookup, or quota
count; this module only turns that fact into a structured
:class:`~shared_core.validation.results.ValidationResult`.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from shared_core.validation.base import ValidationSeverity
from shared_core.validation.results import ValidationResult


def check_unique_name(
    name: str, *, exists: bool, resource_type: str = "resource"
) -> ValidationResult:
    """Validate *name* is unique. *exists* is the caller's own existence check result."""
    if exists:
        return ValidationResult.fail(f"A {resource_type} named '{name}' already exists.")
    return ValidationResult.ok()


def check_resource_ownership(
    *, resource_owner_id: UUID, requester_id: UUID | None
) -> ValidationResult:
    """Validate the requester owns the resource."""
    if requester_id is None or resource_owner_id != requester_id:
        return ValidationResult.fail(
            "You do not own this resource.", severity=ValidationSeverity.ERROR
        )
    return ValidationResult.ok()


def check_organization_isolation(
    *, resource_organization_id: UUID, context_organization_id: UUID | None
) -> ValidationResult:
    """Validate a resource belongs to the caller's organization."""
    if context_organization_id is None or resource_organization_id != context_organization_id:
        return ValidationResult.fail("This resource belongs to a different organization.")
    return ValidationResult.ok()


def check_project_isolation(
    *, resource_project_id: UUID, context_project_id: UUID | None
) -> ValidationResult:
    """Validate a resource belongs to the caller's project."""
    if context_project_id is None or resource_project_id != context_project_id:
        return ValidationResult.fail("This resource belongs to a different project.")
    return ValidationResult.ok()


def check_license(*, permitted: bool, feature: str = "this feature") -> ValidationResult:
    """Validate the caller's license permits *feature*."""
    if not permitted:
        return ValidationResult.fail(f"Your license does not permit {feature}.")
    return ValidationResult.ok()


def check_dependency(*, satisfied: bool, dependency_name: str) -> ValidationResult:
    """Validate a required dependency is satisfied."""
    if not satisfied:
        return ValidationResult.fail(f"Required dependency '{dependency_name}' is not satisfied.")
    return ValidationResult.ok()


def check_duplicate_prevention(candidate: Any, *, existing: Iterable[Any]) -> ValidationResult:
    """Validate *candidate* would not duplicate an item already in *existing*."""
    if candidate in existing:
        return ValidationResult.fail("This would create a duplicate entry.")
    return ValidationResult.ok()


def check_quota(*, current: int, limit: int, resource_type: str = "resource") -> ValidationResult:
    """Validate *current* usage has not reached *limit*."""
    if current >= limit:
        return ValidationResult.fail(
            f"{resource_type.capitalize()} quota exceeded ({current}/{limit})."
        )
    return ValidationResult.ok()


def check_approval_required(*, approved: bool, action: str = "this action") -> ValidationResult:
    """Validate an action requiring approval has been approved."""
    if not approved:
        return ValidationResult.fail(
            f"{action.capitalize()} requires approval before it can proceed.",
            severity=ValidationSeverity.WARNING,
        )
    return ValidationResult.ok()


def check_maintenance_window(
    *, now: datetime, window_start: datetime, window_end: datetime
) -> ValidationResult:
    """Validate *now* does not fall within an active maintenance window."""
    if window_start <= now <= window_end:
        return ValidationResult.fail(
            f"This action is blocked during the maintenance window "
            f"({window_start.isoformat()} - {window_end.isoformat()})."
        )
    return ValidationResult.ok()
