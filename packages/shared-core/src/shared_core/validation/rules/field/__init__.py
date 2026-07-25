"""Field-level validation rules (docs/016 "FIELD VALIDATORS").

Every service should import field validators from here, not from
:mod:`shared_core.validators.fields` directly -- this is the one place
that returns the validation framework's rich
:class:`~shared_core.validation.results.ValidationResult` (with
severity/suggestions/etc). The underlying regex/length/format logic for
UUID, email, hostname, IPv4/IPv6, MAC, port, domain, URL, password,
username, and the resource-name family is **not duplicated** here -- it
still lives in :mod:`shared_core.validators.fields` (Prompt 012); this
module only adapts each result into the richer shape. Phone, secret name,
license key, cron expression, CIDR, and semantic version are new.
"""

from __future__ import annotations

import ipaddress
import re

from shared_core.validation.results import ValidationResult
from shared_core.validators.fields import (
    validate_asset_name as _legacy_validate_asset_name,
)
from shared_core.validators.fields import (
    validate_domain as _legacy_validate_domain,
)
from shared_core.validators.fields import (
    validate_email as _legacy_validate_email,
)
from shared_core.validators.fields import (
    validate_hostname as _legacy_validate_hostname,
)
from shared_core.validators.fields import (
    validate_ipv4 as _legacy_validate_ipv4,
)
from shared_core.validators.fields import (
    validate_ipv6 as _legacy_validate_ipv6,
)
from shared_core.validators.fields import (
    validate_mac_address as _legacy_validate_mac_address,
)
from shared_core.validators.fields import (
    validate_organization_name as _legacy_validate_organization_name,
)
from shared_core.validators.fields import (
    validate_password as _legacy_validate_password,
)
from shared_core.validators.fields import (
    validate_playbook_name as _legacy_validate_playbook_name,
)
from shared_core.validators.fields import (
    validate_port as _legacy_validate_port,
)
from shared_core.validators.fields import (
    validate_project_name as _legacy_validate_project_name,
)
from shared_core.validators.fields import (
    validate_resource_name as _legacy_validate_resource_name,
)
from shared_core.validators.fields import (
    validate_url as _legacy_validate_url,
)
from shared_core.validators.fields import (
    validate_username as _legacy_validate_username,
)
from shared_core.validators.fields import (
    validate_uuid as _legacy_validate_uuid,
)
from shared_core.validators.results import ValidationResult as _LegacyValidationResult

_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
_PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{6,14}$")
_LICENSE_KEY_PATTERN = re.compile(r"^([A-Z0-9]{4,5}-){3,7}[A-Z0-9]{4,5}$")
_SECRET_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_CRON_FIELD_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_CRON_FIELD_LABELS = ("minute", "hour", "day of month", "month", "day of week")
_CRON_FIELD_COUNT = 5
_SECRET_NAME_MAX_LENGTH = 253


def _from_legacy(result: _LegacyValidationResult) -> ValidationResult:
    if result.valid:
        return ValidationResult.ok(warnings=list(result.warnings))
    return ValidationResult.fail(*result.errors)


def validate_uuid(value: str) -> ValidationResult:
    """Validate a UUID string."""
    return _from_legacy(_legacy_validate_uuid(value))


def validate_email(value: str) -> ValidationResult:
    """Validate an email address."""
    return _from_legacy(_legacy_validate_email(value))


def validate_hostname(value: str) -> ValidationResult:
    """Validate a DNS hostname."""
    return _from_legacy(_legacy_validate_hostname(value))


def validate_ipv4(value: str) -> ValidationResult:
    """Validate an IPv4 address."""
    return _from_legacy(_legacy_validate_ipv4(value))


def validate_ipv6(value: str) -> ValidationResult:
    """Validate an IPv6 address."""
    return _from_legacy(_legacy_validate_ipv6(value))


def validate_mac_address(value: str) -> ValidationResult:
    """Validate a MAC address."""
    return _from_legacy(_legacy_validate_mac_address(value))


def validate_domain(value: str) -> ValidationResult:
    """Validate a domain name."""
    return _from_legacy(_legacy_validate_domain(value))


def validate_url(value: str) -> ValidationResult:
    """Validate a URL."""
    return _from_legacy(_legacy_validate_url(value))


def validate_port(value: int) -> ValidationResult:
    """Validate a TCP/UDP port number."""
    return _from_legacy(_legacy_validate_port(value))


def validate_username(value: str) -> ValidationResult:
    """Validate a username."""
    return _from_legacy(_legacy_validate_username(value))


def validate_password(value: str) -> ValidationResult:
    """Validate password strength."""
    return _from_legacy(_legacy_validate_password(value))


def validate_organization_name(value: str) -> ValidationResult:
    """Validate an organization name."""
    return _from_legacy(_legacy_validate_organization_name(value))


def validate_project_name(value: str) -> ValidationResult:
    """Validate a project name."""
    return _from_legacy(_legacy_validate_project_name(value))


def validate_asset_name(value: str) -> ValidationResult:
    """Validate an asset name."""
    return _from_legacy(_legacy_validate_asset_name(value))


def validate_playbook_name(value: str) -> ValidationResult:
    """Validate a playbook name."""
    return _from_legacy(_legacy_validate_playbook_name(value))


def validate_team_name(value: str) -> ValidationResult:
    """Validate a team name."""
    return _from_legacy(_legacy_validate_resource_name(value, resource_type="team"))


def validate_job_name(value: str) -> ValidationResult:
    """Validate a job name."""
    return _from_legacy(_legacy_validate_resource_name(value, resource_type="job"))


def validate_workflow_name(value: str) -> ValidationResult:
    """Validate a workflow name."""
    return _from_legacy(_legacy_validate_resource_name(value, resource_type="workflow"))


def validate_phone(value: str) -> ValidationResult:
    """Validate a phone number in loose E.164 form (optional ``+``, 7-15 digits)."""
    if not _PHONE_PATTERN.match(value):
        return ValidationResult.fail(
            "Phone number must be 7-15 digits, optionally prefixed with '+'."
        )
    return ValidationResult.ok()


def validate_secret_name(value: str) -> ValidationResult:
    """Validate a secret's name (stricter than a resource name -- no spaces,
    since it's typically used as an identifier: an env var or Kubernetes
    Secret key name).
    """
    if not (1 <= len(value) <= _SECRET_NAME_MAX_LENGTH):
        return ValidationResult.fail(
            f"Secret name must be between 1 and {_SECRET_NAME_MAX_LENGTH} characters."
        )
    if not _SECRET_NAME_PATTERN.match(value):
        return ValidationResult.fail(
            "Secret name must start with a letter and contain only letters, "
            "digits, underscores, and hyphens."
        )
    return ValidationResult.ok()


def validate_license_key(value: str) -> ValidationResult:
    """Validate a license key: 4-8 dash-separated groups of 4-5 uppercase
    alphanumeric characters (e.g. ``ABCDE-12345-FGHIJ-67890``).
    """
    if not _LICENSE_KEY_PATTERN.match(value):
        return ValidationResult.fail(
            "License key must be 4-8 dash-separated groups of 4-5 uppercase "
            "letters/digits (e.g. 'ABCDE-12345-FGHIJ-67890')."
        )
    return ValidationResult.ok()


def validate_cidr(value: str) -> ValidationResult:
    """Validate a CIDR network (e.g. ``10.0.0.0/8``, ``2001:db8::/32``)."""
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        return ValidationResult.fail(f"Invalid CIDR notation: {exc}")
    return ValidationResult.ok()


def validate_semantic_version(value: str) -> ValidationResult:
    """Validate a semantic version string (https://semver.org)."""
    if not _SEMVER_PATTERN.match(value):
        return ValidationResult.fail(
            "Version must follow semantic versioning (e.g. '1.2.3', '1.2.3-rc.1')."
        )
    return ValidationResult.ok()


def _validate_cron_field(raw_field: str, *, min_value: int, max_value: int) -> bool:
    for entry in raw_field.split(","):
        step_base, _, step = entry.partition("/")
        value_part = step_base if "/" in entry else entry
        if "/" in entry and (not step.isdigit() or int(step) <= 0):
            return False
        if value_part == "*":
            continue
        if "-" in value_part:
            start, _, end = value_part.partition("-")
            if not (start.isdigit() and end.isdigit()):
                return False
            start_i, end_i = int(start), int(end)
            if not (min_value <= start_i <= end_i <= max_value):
                return False
        elif not value_part.isdigit() or not (min_value <= int(value_part) <= max_value):
            return False
    return True


def validate_cron_expression(value: str) -> ValidationResult:
    """Validate a standard 5-field cron expression (minute hour day month weekday)."""
    fields = value.split()
    if len(fields) != _CRON_FIELD_COUNT:
        return ValidationResult.fail(
            "Cron expression must have exactly 5 fields: minute hour day-of-month "
            "month day-of-week."
        )
    errors = [
        f"Invalid {label} field: '{raw_field}'."
        for raw_field, (lo, hi), label in zip(
            fields, _CRON_FIELD_BOUNDS, _CRON_FIELD_LABELS, strict=True
        )
        if not _validate_cron_field(raw_field, min_value=lo, max_value=hi)
    ]
    if errors:
        return ValidationResult.fail(*errors)
    return ValidationResult.ok()
