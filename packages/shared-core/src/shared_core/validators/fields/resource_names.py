"""Resource name field validation.

Projects, organizations, assets, and playbooks all share the same naming
rule, so each is a thin wrapper around :func:`validate_resource_name`
rather than duplicating the pattern.
"""

from __future__ import annotations

import re

from shared_core.constants import ValidationConstants
from shared_core.validators.results import ValidationResult

_RESOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")


def validate_resource_name(value: str, *, resource_type: str = "resource") -> ValidationResult:
    """Validate a human-facing resource name shared by most entity types."""
    if not (
        ValidationConstants.NAME_MIN_LENGTH <= len(value) <= ValidationConstants.NAME_MAX_LENGTH
    ):
        return ValidationResult.fail(
            f"{resource_type.capitalize()} name must be between "
            f"{ValidationConstants.NAME_MIN_LENGTH} and {ValidationConstants.NAME_MAX_LENGTH} "
            "characters."
        )
    if not _RESOURCE_NAME_PATTERN.match(value):
        return ValidationResult.fail(
            f"{resource_type.capitalize()} name must start with a letter or digit and contain "
            "only letters, digits, spaces, underscores, hyphens, and dots."
        )
    return ValidationResult.ok()


def validate_project_name(value: str) -> ValidationResult:
    """Validate a project name."""
    return validate_resource_name(value, resource_type="project")


def validate_organization_name(value: str) -> ValidationResult:
    """Validate an organization name."""
    return validate_resource_name(value, resource_type="organization")


def validate_asset_name(value: str) -> ValidationResult:
    """Validate an asset name."""
    return validate_resource_name(value, resource_type="asset")


def validate_playbook_name(value: str) -> ValidationResult:
    """Validate a playbook name."""
    return validate_resource_name(value, resource_type="playbook")
